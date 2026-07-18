# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""RC-2 — functional-equivalence compensations (silent wrong results).

Integer division: PG/T-SQL truncate two integer operands (5 / 2 = 2), MySQL/
Oracle return a decimal (2.5). For integer *literal* operands the value is
knowable without schema, so the emitter compensates. (Column/variable operands
need declared types — only reachable in the procedural pipeline.)
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source, target).sql


def test_integer_division_literals_preserved() -> None:
    # PG 5/2 = 2 must stay 2 on the decimal-division engines.
    assert "5 DIV 2" in _t("SELECT 5 / 2 AS r", "postgresql", "mysql")
    assert "TRUNC(5 / 2)" in _t("SELECT 5 / 2 AS r", "postgresql", "oracle")
    # MySQL 5/2 = 2.5 must stay decimal on the integer-division engines.
    assert "5 * 1.0 / 2" in _t("SELECT 5 / 2 AS r", "mysql", "postgresql")
    assert "5 * 1.0 / 2" in _t("SELECT 5 / 2 AS r", "oracle", "tsql")


def test_integer_division_same_class_unchanged() -> None:
    # Both integer-division engines: no compensation.
    assert "5 / 2" in _t("SELECT 5 / 2 AS r", "postgresql", "tsql")
    # Both decimal-division engines: no compensation.
    out = _t("SELECT 5 / 2 AS r", "mysql", "oracle")
    assert "DIV" not in out and "TRUNC" not in out and "1.0" not in out, out


def test_oracle_concat_null_literal_dropped() -> None:
    # Oracle || treats NULL as '' ('a'||NULL||'b' = 'ab'); other engines
    # propagate NULL, so the NULL literal is dropped to keep the value.
    from unique.core.transpiler import Transpiler

    r = Transpiler().transpile(
        "SELECT 'a' || NULL || 'b' AS r FROM DUAL", "oracle", "postgresql"
    )
    assert "'a' || 'b'" in r.sql and "NULL" not in r.sql.upper(), r.sql
    assert r.warnings, "the compensation must be annotated"
