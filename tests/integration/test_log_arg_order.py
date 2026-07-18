# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""RC-2 — LOG argument order (a silent wrong-result across the T-SQL boundary).

Every engine normalises ``LOG`` to the canonical ``LOG(base, x)`` in the IR, but
T-SQL *spells* it ``LOG(x, base)``. The emitter therefore swaps the two
arguments only when the target is T-SQL, so the base-b logarithm is preserved
rather than silently computing a different value.
"""

from __future__ import annotations

import pytest

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source, target).sql


@pytest.mark.parametrize("source", ["mysql", "postgresql", "oracle"])
def test_log_to_tsql_swaps_to_x_base(source: str) -> None:
    # LOG(2, 8) = log base 2 of 8 = 3; T-SQL spells that LOG(8, 2).
    out = _t("SELECT LOG(2, 8) AS r", source, "tsql")
    assert "LOG(8, 2)" in out, out


@pytest.mark.parametrize("target", ["mysql", "postgresql", "oracle"])
def test_log_from_tsql_restores_base_x(target: str) -> None:
    # T-SQL LOG(2, 8) = log of 2 to base 8; canonical LOG(base, x) is LOG(8, 2).
    out = _t("SELECT LOG(2, 8) AS r", "tsql", target)
    assert "LOG(8, 2)" in out, out


def test_log_between_non_tsql_is_unchanged() -> None:
    out = _t("SELECT LOG(2, 8) AS r", "mysql", "postgresql")
    assert "LOG(2, 8)" in out, out


def test_single_arg_log_is_not_swapped() -> None:
    # One-arg LOG (natural log) has no base argument to reorder.
    out = _t("SELECT LOG(x) AS r FROM t", "postgresql", "tsql")
    assert "LOG(x)" in out, out
