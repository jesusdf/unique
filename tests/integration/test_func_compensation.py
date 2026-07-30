# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""RC-2 — functional-equivalence compensations (silent wrong results).

Integer division: PG/T-SQL truncate two integer operands (5 / 2 = 2), MySQL/
Oracle return a decimal (2.5). Integer *literal* operands are compensated
without schema; declared integer variables are compensated in the procedural
pipeline, where their types are known.

Concat NULL handling: T-SQL '+', PG '||' and MySQL CONCAT propagate NULL, but
Oracle's || treats NULL as ''. A NULL literal from an Oracle source is dropped;
a nullable string variable into an Oracle target is guarded with a CASE so the
source's NULL result survives.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source, target).sql


def test_integer_division_literals_preserved() -> None:
    # PG 5/2 = 2 must stay 2 on the decimal-division engines.
    assert "5 DIV 2" in _t("SELECT 5 / 2 AS r", "postgresql", "mysql")
    assert "TRUNC(5 / 2)" in _t("SELECT 5 / 2 AS r", "postgresql", "oracle")
    # MySQL 5/2 = 2.5 must stay decimal on the integer-division engines. MySQL's
    # NULL-safe division also wraps the divisor in NULLIF (see TestMysqlSafeDivision).
    assert "5 * 1.0 / NULLIF(2, 0)" in _t("SELECT 5 / 2 AS r", "mysql", "postgresql")
    assert "5 * 1.0 / 2" in _t("SELECT 5 / 2 AS r", "oracle", "tsql")


def test_integer_division_same_class_unchanged() -> None:
    # Both integer-division engines: no compensation.
    assert "5 / 2" in _t("SELECT 5 / 2 AS r", "postgresql", "tsql")
    # Both decimal-division engines: no compensation.
    out = _t("SELECT 5 / 2 AS r", "mysql", "oracle")
    assert "DIV" not in out and "TRUNC" not in out and "1.0" not in out, out


def test_integer_division_declared_variables_procedural() -> None:
    # In a stored procedure the operand types are known from the DECLAREs, so
    # integer division over integer-declared variables is compensated too.
    proc = (
        "CREATE PROCEDURE p AS BEGIN "
        "DECLARE @a INT; DECLARE @b INT; DECLARE @r INT; "
        "SET @r = @a / @b; END"
    )
    out = _t(proc, "tsql", "oracle")
    assert "TRUNC(V_A / V_B)" in out, out
    assert "DIV" in _t(proc, "tsql", "mysql")


def test_integer_division_decimal_variable_not_compensated() -> None:
    # A DECIMAL(p, s>0) operand is not integer — the scale lives in
    # DataType.params, so it must not be mistaken for an integer and wrapped.
    proc = (
        "CREATE PROCEDURE p AS BEGIN "
        "DECLARE @a DECIMAL(10,2); DECLARE @b INT; DECLARE @r DECIMAL(10,2); "
        "SET @r = @a / @b; END"
    )
    out = _t(proc, "tsql", "oracle")
    assert "V_A / V_B" in out and "TRUNC(V_A / V_B)" not in out, out


def test_concat_null_propagation_preserved_into_oracle() -> None:
    # T-SQL '+', PG '||' and MySQL CONCAT yield NULL when any operand is NULL;
    # Oracle's || treats NULL as ''. When a nullable string variable is an
    # operand, the concat is guarded so Oracle reproduces the source's NULL.
    proc = (
        "CREATE PROCEDURE p AS BEGIN "
        "DECLARE @a VARCHAR(10); DECLARE @b VARCHAR(10); DECLARE @r VARCHAR(20); "
        "SET @r = @a + @b; END"
    )
    out = _t(proc, "tsql", "oracle")
    assert (
        "CASE WHEN V_A IS NULL OR V_B IS NULL THEN NULL ELSE V_A || V_B END" in out
    ), out


def test_concat_literals_not_guarded_into_oracle() -> None:
    # String literals are never NULL — no guard, just a plain concat.
    proc = (
        "CREATE PROCEDURE p AS BEGIN " "DECLARE @r VARCHAR(20); SET @r = 'x' + 'y'; END"
    )
    out = _t(proc, "tsql", "oracle")
    assert "'x' || 'y'" in out and "CASE" not in out, out


def test_concat_null_propagation_native_on_pg_target() -> None:
    # PG's || already propagates NULL, so no guard is added.
    proc = (
        "CREATE PROCEDURE p AS BEGIN "
        "DECLARE @a VARCHAR(10); DECLARE @b VARCHAR(10); DECLARE @r VARCHAR(20); "
        "SET @r = @a + @b; END"
    )
    out = _t(proc, "tsql", "postgresql")
    assert "v_a || v_b" in out and "CASE" not in out, out


def test_oracle_concat_null_literal_dropped() -> None:
    # Oracle || treats NULL as '' ('a'||NULL||'b' = 'ab'); other engines
    # propagate NULL, so the NULL literal is dropped to keep the value.
    from unique.core.transpiler import Transpiler

    r = Transpiler().transpile(
        "SELECT 'a' || NULL || 'b' AS r FROM DUAL", "oracle", "postgresql"
    )
    assert "'a' || 'b'" in r.sql and "NULL" not in r.sql.upper(), r.sql
    assert r.warnings, "the compensation must be annotated"
