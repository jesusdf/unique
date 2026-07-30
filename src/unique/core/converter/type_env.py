# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Minimal type environment for derived-table columns (feature B30).

Oracle ``SELECT d2 - d1 FROM (SELECT DATE '…' d1, DATE '…' d2 …)`` loses the
DATE typing of the projected literals once they become derived-table columns,
so the outer ``d2 - d1`` cannot be spelled as the target's day-count
(``DATEDIFF`` on T-SQL/MySQL) and ships an invalid raw subtraction.

This module infers the temporal type (``"date"`` / ``"timestamp"``) of a
derived table's projected columns and tags the outer references to them, so the
existing temporal-operator rewrites (the ``date ± int`` / ``ts − ts`` family) in
:mod:`emit_expr` fire on derived columns exactly as they do on literals.

It is deliberately bounded — the only projection shapes it understands are:

* a temporal literal (a sqlglot ``DATE '…'`` wrapper, or a CAST to DATE),
* a CAST to a date/timestamp type, and
* a pass-through column reference (resolved against the source relation's own
  inferred types).

Anything else stays unknown and keeps the current behavior. No general type
inference and no engine round-trip.
"""

from __future__ import annotations

import dataclasses
from typing import cast

from ..ast_nodes import (
    Alias,
    ASTNode,
    CastExpression,
    ColumnRef,
    CTEDefinition,
    FunctionCall,
    SelectStatement,
    SubqueryExpression,
    TableRef,
)

DATE = "date"
TIMESTAMP = "timestamp"

#: CAST target types that denote a date+time value (mirrors emit_expr's
#: ``_DATETIME_CAST_TYPES``; a plain DATE is tracked separately as ``DATE``).
_DATETIME_TYPE_NAMES = frozenset(
    {"DATETIME", "DATETIME2", "TIMESTAMP", "SMALLDATETIME", "DATETIMEOFFSET"}
)


def _expr_temporal_kind(expr: ASTNode, src: dict[str, str]) -> str | None:
    """The temporal kind of a projection expression, or None if not inferable.

    ``src`` is the source relation's own ``{column: kind}`` env, used to resolve
    a pass-through column reference.
    """
    # A DATE literal: sqlglot models ``DATE '…'`` as ``DATE_STR_TO_DATE('…')``.
    if isinstance(expr, FunctionCall) and expr.name.upper() == "DATE_STR_TO_DATE":
        return DATE
    # A CAST to a temporal type (PostgreSQL's ``DATE '…'`` parses this way, and
    # any explicit ``CAST(x AS DATE/TIMESTAMP)`` projection qualifies too).
    if isinstance(expr, CastExpression):
        name = expr.target_type.name.split("(")[0].strip().upper()
        if name == "DATE":
            return DATE
        if name in _DATETIME_TYPE_NAMES:
            return TIMESTAMP
    # A pass-through column reference resolves to the source relation's type.
    if isinstance(expr, ColumnRef):
        return src.get(expr.name.lower())
    return None


def _source_env(query: SelectStatement) -> dict[str, str]:
    """Column types visible from ``query``'s FROM relation (single-relation
    only — JOINs leave it unresolved to avoid mis-attributing a column)."""
    if query.joins:
        return {}
    fc = query.from_clause
    if isinstance(fc, SubqueryExpression):
        return dict(fc.column_types)
    if isinstance(fc, TableRef) and query.ctes:
        target = (fc.name or "").lower()
        for cte in query.ctes:
            if (cte.name or "").lower() == target:
                return _cte_types(cte)
    return {}


def infer_column_types(query: SelectStatement) -> dict[str, str]:
    """Infer ``{output_column_lower: kind}`` for a SELECT's projection."""
    src = _source_env(query)
    out: dict[str, str] = {}
    for col in query.columns:
        if isinstance(col, Alias):
            name, expr = col.name, col.expression
        elif isinstance(col, ColumnRef):
            name, expr = col.name, col
        else:
            continue
        kind = _expr_temporal_kind(expr, src)
        if kind and name:
            out[name.lower()] = kind
    return out


def _cte_types(cte: CTEDefinition) -> dict[str, str]:
    """Column types a CTE exposes. An explicit column-alias list
    (``WITH x(a, b) AS …``) renames positionally and is left unresolved."""
    if cte.columns:
        return {}
    return infer_column_types(cte.query)


def _tag(node: object, env: dict[str, str]) -> object:
    """Return ``node`` with every unqualified ColumnRef whose name is in ``env``
    tagged with its inferred type. A nested query is its own scope and is left
    untouched (its columns resolve against a different relation)."""
    if isinstance(node, ColumnRef):
        if node.table is None and node.inferred_type is None:
            kind = env.get(node.name.lower())
            if kind:
                return dataclasses.replace(node, inferred_type=kind)
        return node
    if isinstance(node, (SelectStatement, SubqueryExpression)):
        return node
    if isinstance(node, tuple):
        new = tuple(_tag(v, env) for v in node)
        return new if any(a is not b for a, b in zip(new, node, strict=True)) else node
    if isinstance(node, ASTNode):
        changes: dict[str, object] = {}
        for f in dataclasses.fields(node):
            old = getattr(node, f.name)
            new_v = _tag(old, env)
            if new_v is not old:
                changes[f.name] = new_v
        return dataclasses.replace(node, **changes) if changes else node  # type: ignore[arg-type]
    return node


def tag_temporal_columns(select: SelectStatement) -> SelectStatement:
    """Tag the SELECT's projection ColumnRefs with types inferred from its
    single FROM relation (a derived table or a CTE). Identity when nothing
    resolves, so it is safe to apply to every converted SELECT."""
    env = _source_env(select)
    if not env:
        return select
    new_cols = tuple(_tag(c, env) for c in select.columns)
    if any(a is not b for a, b in zip(new_cols, select.columns, strict=True)):
        return dataclasses.replace(
            select, columns=cast("tuple[ASTNode, ...]", new_cols)
        )
    return select
