# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""RC-1a — real mappings for built-ins that have a faithful target form.

These functions used to degrade to a carrier on the target that lacks them;
they have an exact rewrite, so they now translate instead. (RIGHT → Oracle is
deliberately *not* here: SUBSTR(s, -n) diverges from RIGHT at the n=0 / n>len
edges, so it keeps degrading honestly.)
"""

from __future__ import annotations

import sqlglot

from unique.core.transpiler import Transpiler

_SG = {"mysql": "mysql", "tsql": "tsql", "oracle": "oracle", "postgresql": "postgres"}


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source, target).sql


def _ok(out: str, target: str) -> bool:
    try:
        sqlglot.parse(out, read=_SG[target], error_level=sqlglot.ErrorLevel.RAISE)
        return "-- UNIQUE:" not in out
    except Exception:
        return False


def test_left_maps_to_substr_on_oracle() -> None:
    out = _t("SELECT LEFT('hello', 2) AS r", "mysql", "oracle")
    assert "SUBSTR('hello', 1, 2)" in out, out
    assert "LEFT" not in out.upper(), out
    assert _ok(out, "oracle")


def test_space_maps_on_oracle_and_postgresql() -> None:
    assert "RPAD(' ', 3)" in _t("SELECT SPACE(3) AS r", "tsql", "oracle")
    out = _t("SELECT SPACE(3) AS r", "tsql", "postgresql")
    assert "REPEAT(' ', 3)" in out, out
    assert _ok(out, "postgresql")


def test_left_unchanged_where_native() -> None:
    # PostgreSQL/MySQL/T-SQL have LEFT natively — do not rewrite it.
    out = _t("SELECT LEFT('h', 2) AS r", "mysql", "postgresql")
    assert "LEFT('h', 2)" in out, out
