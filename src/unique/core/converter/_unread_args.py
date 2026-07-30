# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unread-args tripwire for the DML converter (audit 2026-07-24 T1, brief B2).

Guardrail 7 says converting a sqlglot node must account for **every** key in
``node.args``: convert it, or degrade with a warning — never let an unread arg
fall on the floor. N1 (``ON CONFLICT``), N3 (MERGE ``OUTPUT`` tail) and N4
(``DO NOTHING``) all shipped silently because a ``_convert_*`` never read the
arg that carried the construct.

This module makes that check mechanical. At the single conversion dispatch
point (:func:`unique.core.converter.convert.convert_expression`) a node's
``args`` dict is swapped for a :class:`_ReadTrackingArgs` mapping for the
duration of its ``_convert_*`` call. On return, any semantic key that was
never read — and is not on the per-node-type allowlist — is reported.

Modes (env ``UNIQUE_UNREAD_ARGS``):

* ``off``  — no tracking (zero overhead).
* ``warn`` — default; every residue key adds a ``result.warnings`` entry.
* ``gate`` — as ``warn`` plus raise :class:`UnreadArgError`, degrading the
  whole statement to the documented carrier (the transpiler's DML handler
  catches it and preserves the original SQL).

The ``--sweep`` mode of ``scripts/unread_args_sweep.py`` runs the standard
fixtures in ``warn`` mode and prints the unique ``(NodeType, arg)`` pairs.
"""

from __future__ import annotations

import contextvars
import os
from collections.abc import Callable, ItemsView, Iterator, KeysView, ValuesView
from typing import Any

import sqlglot.expressions as exp

from unique.core.ast_nodes import ASTNode

#: Feature tag on the emitted ``TransformWarning`` (also the sweep filter).
WARNING_FEATURE = "unread_args"


class UnreadArgError(Exception):
    """Raised in ``gate`` mode when a converter left a semantic arg unread."""


def unread_args_mode() -> str:
    """Return the active tripwire mode (``off`` / ``warn`` / ``gate``)."""
    mode = os.environ.get("UNIQUE_UNREAD_ARGS", "warn").strip().lower()
    return mode if mode in ("off", "warn", "gate") else "warn"


# --------------------------------------------------------------------------- #
# Warning sink — a per-conversion list drained by the DML transpiler.
# --------------------------------------------------------------------------- #

_SINK: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "unread_arg_sink", default=None
)


def reset_sink() -> None:
    """Start a fresh sink for one ``parse_sql`` run."""
    _SINK.set([])


def drain_sink() -> list[str]:
    """Return and clear the accumulated warning messages."""
    msgs = _SINK.get()
    _SINK.set([])
    return list(msgs) if msgs else []


def _emit(message: str) -> None:
    sink = _SINK.get()
    if sink is None:
        sink = []
        _SINK.set(sink)
    sink.append(message)


# --------------------------------------------------------------------------- #
# Read-tracking mapping.
# --------------------------------------------------------------------------- #


class _ReadTrackingArgs(dict[str, Any]):
    """A ``node.args`` dict that records which keys the converter accessed.

    Every keyed read (``[]``, ``.get``, ``in``) marks the key read; any bulk
    enumeration (``.keys``/``.values``/``.items``/iteration) marks **all**
    keys read, since a converter/generator that walks the whole dict — e.g. a
    ``RawSQL``/``PassthroughSQL`` fallback re-rendering the node — drops
    nothing. Writes fall through to ``dict`` unchanged (so ``node.set(...)``
    during conversion is preserved).
    """

    def __init__(self, real: dict[str, Any]) -> None:
        super().__init__(real)
        self.read_keys: set[str] = set()

    def __getitem__(self, key: str) -> Any:
        self.read_keys.add(key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        self.read_keys.add(key)
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.read_keys.add(key)
        return super().__contains__(key)

    def _mark_all(self) -> None:
        self.read_keys.update(super().keys())

    def keys(self) -> KeysView[str]:  # type: ignore[override]
        self._mark_all()
        return super().keys()

    def values(self) -> ValuesView[Any]:  # type: ignore[override]
        self._mark_all()
        return super().values()

    def items(self) -> ItemsView[str, Any]:  # type: ignore[override]
        self._mark_all()
        return super().items()

    def __iter__(self) -> Iterator[str]:
        self._mark_all()
        return super().__iter__()


# --------------------------------------------------------------------------- #
# Allowlist — built empirically from scripts/unread_args_sweep.py over
# tests/fixtures/ (sql, corpus, real_world, challenge), all 12 directions.
# Each entry is a key a ``_convert_*`` legitimately ignores, with a one-line
# justification. Semantic clause-carrying keys (Insert.conflict, Merge.output,
# …) are deliberately absent so they still warn — that is the point.
# --------------------------------------------------------------------------- #

ALLOWED_UNREAD: dict[str, frozenset[str]] = {
    # sqlglot's ``safe=True`` marks the CONCAT() function form (vs the ``||``
    # operator); the converter models concatenation structurally per target,
    # so the flag carries no droppable construct.
    "Concat": frozenset({"safe"}),
    # ``Create.properties`` is deliberately NOT allowlisted (RED seed
    # 2026-07-24): the CREATE TABLE path reads it structurally and the CREATE
    # VIEW path collects the view modifiers (SCHEMABINDING, ALGORITHM=,
    # DEFINER=, …) — re-attached natively where the target supports them,
    # warned carriers elsewhere — so an unread ``properties`` warns again.
    # A MySQL charset introducer (``_utf8mb4'…'``): ``this`` is the charset
    # name, dropped when the literal is carried cross-engine (MySQL-specific,
    # no portable form). The literal itself (``expression``) is converted.
    "Introducer": frozenset({"this"}),
    # sqlglot ≥30.12 populates ``Window.args['over']`` with the bare keyword
    # marker ``'OVER'`` (a rendering flag, not a droppable construct — the real
    # window spec lives in ``partition_by`` / ``order`` / ``spec``, all read by
    # the emitter). Without this every window function false-fired the tripwire
    # (challenge pg-window-over-falsewarn, sqlglot 30.11→30.14 regression).
    "Window": frozenset({"over"}),
}


def _is_empty(value: Any) -> bool:
    """Whether an arg value carries no construct.

    sqlglot fills a node's ``args`` with sentinels for absent optional
    clauses: ``None`` for an absent child, ``False`` for an unset presence
    flag (``ignore``/``overwrite``/``exists``/…), and an empty container for
    an absent list. None of these carry a droppable construct, so an unread
    one is never a defect — a *set* flag (``ignore=True``) is not empty and
    still warns.
    """
    if value is None or value is False:
        return True
    return isinstance(value, (list, tuple, dict, set)) and not value


def report_unread_args(
    expr: exp.Expression, tracked: _ReadTrackingArgs, mode: str
) -> None:
    """Report semantic keys the converter left unread on ``expr``.

    Appends one warning per residue key to the sink; in ``gate`` mode raises
    :class:`UnreadArgError` after recording them.
    """
    node_type = type(expr).__name__
    allowed = ALLOWED_UNREAD.get(node_type, frozenset())
    residue: list[str] = []
    for key, value in dict.items(tracked):
        if key in tracked.read_keys:
            continue
        if key in allowed:
            continue
        if _is_empty(value):
            continue
        residue.append(key)
    if not residue:
        return
    for key in residue:
        _emit(
            f"internal: unread sqlglot arg '{key}' on {node_type} — "
            "construct may be dropped"
        )
    if mode == "gate":
        raise UnreadArgError(f"unread sqlglot arg(s) {residue} on {node_type}")


def dispatch_tracked(
    expr: exp.Expression, impl: Callable[[exp.Expression], ASTNode]
) -> ASTNode:
    """Run ``impl(expr)`` with ``expr.args`` read-tracked, then report residue.

    This is the single instrumentation point wired into
    :func:`convert_expression`. In ``off`` mode it is a straight passthrough.
    """
    mode = unread_args_mode()
    if mode == "off":
        return impl(expr)
    tracked = _ReadTrackingArgs(expr.args)
    expr.args = tracked
    node = impl(expr)
    report_unread_args(expr, tracked, mode)
    return node
