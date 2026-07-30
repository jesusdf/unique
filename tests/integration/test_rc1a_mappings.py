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
        return "-- UNIQUE-" not in out
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


def test_power_translates_everywhere() -> None:
    # POWER/`^`/SQUARE model exponentiation; every engine has POWER(x, y).
    for src, expr in [
        ("mysql", "POWER(2, 3)"),
        ("postgresql", "2 ^ 3"),
        ("tsql", "SQUARE(3)"),
    ]:
        out = _t(f"SELECT {expr} AS r", src, "oracle")
        assert "POWER(" in out.upper(), (src, out)
        assert _ok(out, "oracle"), (src, out)


def test_cot_and_pi_on_oracle() -> None:
    assert "1 / TAN(1)" in _t("SELECT COT(1) AS r", "mysql", "oracle")
    assert "ACOS(-1)" in _t("SELECT PI() AS r", "mysql", "oracle")


def test_ln_and_atan2_to_tsql() -> None:
    # T-SQL has no LN (its 1-arg LOG is natural log) and spells atan2 ATN2.
    out = _t("SELECT LN(2) AS r", "mysql", "tsql")
    assert "LOG(2)" in out and "LN(" not in out.upper(), out
    assert "ATN2(1, 1)" in _t("SELECT ATAN2(1, 1) AS r", "mysql", "tsql")


def test_date_functions_map_faithfully() -> None:
    # LAST_DAY/QUARTER/DAYNAME have exact target forms (live-verified).
    assert "EOMONTH(d)" in _t("SELECT LAST_DAY(d) AS r FROM t", "oracle", "tsql")
    assert "DATE_TRUNC('month'" in _t(
        "SELECT LAST_DAY(d) AS r FROM t", "oracle", "postgresql"
    )
    assert "DATEPART(QUARTER, d)" in _t(
        "SELECT QUARTER(d) AS r FROM t", "mysql", "tsql"
    )
    assert "TO_CHAR(d, 'Q')" in _t("SELECT QUARTER(d) AS r FROM t", "mysql", "oracle")
    assert "DATENAME(WEEKDAY, d)" in _t(
        "SELECT DAYNAME(d) AS r FROM t", "mysql", "tsql"
    )


def test_oracle_math_gaps() -> None:
    assert "180 / ACOS(-1)" in _t("SELECT DEGREES(x) AS r FROM t", "mysql", "oracle")
    assert "ACOS(-1) / 180" in _t("SELECT RADIANS(x) AS r FROM t", "mysql", "oracle")
    assert "DBMS_RANDOM.VALUE" in _t("SELECT RAND() AS r", "mysql", "oracle")
    assert "RPAD(s, LENGTH(s) * 3, s)" in _t(
        "SELECT REPEAT(s, 3) AS r FROM t", "mysql", "oracle"
    )


def test_stuff_median_jsonarrayagg() -> None:
    assert "OVERLAY('abcdef' PLACING 'XYZ' FROM 2 FOR 3)" in _t(
        "SELECT STUFF('abcdef', 2, 3, 'XYZ') AS r", "tsql", "postgresql"
    )
    assert "INSERT('abcdef', 2, 3, 'XYZ')" in _t(
        "SELECT STUFF('abcdef', 2, 3, 'XYZ') AS r", "tsql", "mysql"
    )
    assert "SUBSTR(" in _t("SELECT STUFF('abcdef', 2, 3, 'XYZ') AS r", "tsql", "oracle")
    assert "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)" in _t(
        "SELECT MEDIAN(x) AS r FROM t", "oracle", "postgresql"
    )
    assert "JSON_AGG(x)" in _t(
        "SELECT JSON_ARRAYAGG(x) AS r FROM t", "mysql", "postgresql"
    )


def test_elt_and_field_to_case_chains() -> None:
    elt = _t("SELECT ELT(2, 'a', 'b', 'c') AS r", "mysql", "postgresql")
    assert "CASE 2 WHEN 1 THEN 'a' WHEN 2 THEN 'b'" in elt, elt
    assert "ELT" not in elt.upper(), elt
    field = _t("SELECT FIELD('b', 'a', 'b') AS r", "mysql", "oracle")
    assert "CASE 'b' WHEN 'a' THEN 1 WHEN 'b' THEN 2 ELSE 0 END" in field, field


def test_add_months_preserves_sticky_last_day() -> None:
    # Oracle's sticky last-day rule (live-verified vs Oracle on pg/mysql/tsql).
    for tgt, marker in [
        ("mysql", "LAST_DAY"),
        ("tsql", "EOMONTH"),
        ("postgresql", "DATE_TRUNC"),
    ]:
        out = _t("SELECT ADD_MONTHS(d, 1) AS r FROM t", "oracle", tgt)
        assert "CASE WHEN" in out and marker in out, (tgt, out)
        assert "ADD_MONTHS" not in out.upper(), (tgt, out)
