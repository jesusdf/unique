# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""INTERSECT ALL / EXCEPT ALL across all four targets (brief B50).

Before this fix, ``INTERSECT ALL`` / ``EXCEPT ALL`` silently fell back to
the plain (distinct) spelling on Oracle and T-SQL, with **zero warnings** —
duplicate rows collapsed with no signal (postgresql -> oracle emitted plain
``INTERSECT``, dropping the ALL quantifier entirely).

Engine facts, live-verified (not assumed) before implementing:

* PostgreSQL and MySQL (8.0.31+, live engine here is 8.4) support the ALL
  form natively both ways — pre-existing (commit 7053dfac).
* Oracle 21c+ supports ``INTERSECT ALL`` / ``MINUS ALL`` natively; verified
  live on the 23c test engine with duplicate-bearing data.
* T-SQL has **no** ALL form on either operator — verified live on the test
  SQL Server engine: ``The 'ALL' version of the INTERSECT operator is not
  supported``. The fix rewrites the common (two-arm) shape with the classic
  ROW_NUMBER pairing (see ``Transformer._gate_tsql_setop_all`` for the
  mechanics) and degrades WHOLE, with a warning, for the rare chain shapes
  the rewrite cannot reach safely — never the silent dedup.
"""

from __future__ import annotations

import os

import pytest
import sqlglot

from unique.core.transpiler import transpile

_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}


def _assert_parses(sql: str, target: str) -> None:
    sqlglot.parse(
        sql, read=_SQLGLOT_DIALECT[target], error_level=sqlglot.ErrorLevel.RAISE
    )


# Duplicate-bearing arms: t1 has {1: 2 copies, 2: 1 copy}, t2 has {1: 1 copy}.
# INTERSECT ALL keeps min(count) per value -> just one row (1,).
# EXCEPT ALL keeps max(count_left - count_right, 0) -> (1,) and (2,).
INTERSECT_ALL_SRC = (
    "SELECT a FROM (SELECT 1 AS a UNION ALL SELECT 1 UNION ALL SELECT 2) t1 "
    "INTERSECT ALL SELECT a FROM (SELECT 1 AS a) t2"
)
EXCEPT_ALL_SRC = (
    "SELECT a FROM (SELECT 1 AS a UNION ALL SELECT 1 UNION ALL SELECT 2) t1 "
    "EXCEPT ALL SELECT a FROM (SELECT 1 AS a) t2"
)


class TestIntersectExceptAllNativeTargets:
    """PostgreSQL, MySQL and (as of this fix) Oracle keep the ALL
    quantifier natively."""

    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_intersect_all_preserved(self, target: str) -> None:
        out = transpile(INTERSECT_ALL_SRC, "postgresql", target).sql
        assert "INTERSECT ALL" in out
        _assert_parses(out, target)

    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_except_all_preserved(self, target: str) -> None:
        out = transpile(EXCEPT_ALL_SRC, "postgresql", target).sql
        assert "EXCEPT ALL" in out
        _assert_parses(out, target)

    def test_intersect_all_reaches_oracle_native(self) -> None:
        out = transpile(INTERSECT_ALL_SRC, "postgresql", "oracle").sql
        assert "INTERSECT ALL" in out
        # The Oracle-only ``FROM DUAL`` injection proves this went through
        # real Oracle-dialect emission, not an identity pass-through (the
        # ALL spelling alone doesn't discriminate: pg source and Oracle
        # target spell INTERSECT ALL the same way).
        assert "FROM DUAL" in out
        _assert_parses(out, "oracle")

    def test_except_all_reaches_oracle_as_minus_all(self) -> None:
        out = transpile(EXCEPT_ALL_SRC, "postgresql", "oracle").sql
        assert "MINUS ALL" in out
        assert "EXCEPT" not in out  # Oracle never spells it EXCEPT
        _assert_parses(out, "oracle")

    def test_oracle_source_minus_all_passes_through_natively(self) -> None:
        out = transpile(
            "SELECT a FROM t1 MINUS ALL SELECT a FROM t2", "oracle", "oracle"
        ).sql
        assert "MINUS ALL" in out
        _assert_parses(out, "oracle")

    def test_mysql_source_intersect_all_reaches_oracle_native(self) -> None:
        out = transpile(
            "SELECT a FROM t1 INTERSECT ALL SELECT a FROM t2", "mysql", "oracle"
        ).sql
        assert "INTERSECT ALL" in out
        _assert_parses(out, "oracle")


class TestIntersectExceptAllTsqlRewrite:
    """T-SQL has no ALL form on either operator (live-verified: SQL Server
    rejects the syntax outright). The bounded two-arm case is rewritten with
    the ROW_NUMBER pairing rather than degraded — assert the source ALL
    spelling is GONE (an identity transpiler leaves it untouched and fails
    every assertion here) and the pairing landed."""

    def test_intersect_all_rewritten_with_row_number_pairing(self) -> None:
        out = transpile(INTERSECT_ALL_SRC, "postgresql", "tsql").sql
        assert "INTERSECT ALL" not in out
        assert "ROW_NUMBER()" in out
        assert "PARTITION BY" in out
        assert "\nINTERSECT\n" in out
        _assert_parses(out, "tsql")

    def test_except_all_rewritten_with_row_number_pairing(self) -> None:
        out = transpile(EXCEPT_ALL_SRC, "postgresql", "tsql").sql
        assert "EXCEPT ALL" not in out
        assert "ROW_NUMBER()" in out
        assert "\nEXCEPT\n" in out
        _assert_parses(out, "tsql")

    def test_rewrite_is_faithful_not_a_degrade(self) -> None:
        # A structural rewrite that reproduces the exact row multiset is not
        # a loss — it must not carry a warning/unsupported entry (those are
        # reserved for the genuine degrade path, tested below).
        result = transpile(INTERSECT_ALL_SRC, "postgresql", "tsql")
        assert result.warnings == []
        assert result.unsupported == []

    def test_multi_column_partitions_on_every_output_column(self) -> None:
        sql = (
            "SELECT a, b FROM (SELECT 1 AS a, 'x' AS b UNION ALL SELECT 1, 'x') t1 "
            "INTERSECT ALL SELECT a, b FROM (SELECT 1 AS a, 'x' AS b) t2"
        )
        out = transpile(sql, "postgresql", "tsql").sql
        assert "PARTITION BY a, b" in out
        _assert_parses(out, "tsql")


class TestIntersectExceptAllTsqlFallbackDegrade:
    """Shapes the bounded rewrite cannot reach safely (an ALL op
    immediately followed by more chained set operations, or a column list
    the rewrite cannot partition on) must degrade WHOLE with a warning —
    never fall back to the plain, duplicate-collapsing spelling."""

    def test_all_op_followed_by_more_chain_degrades_with_warning(self) -> None:
        sql = "SELECT a FROM t1 INTERSECT ALL SELECT a FROM t2 UNION SELECT a FROM t3"
        result = transpile(sql, "postgresql", "tsql")
        assert result.warnings, "an unrewritable ALL-op chain must warn"
        assert result.unsupported
        # The original ALL-bearing source is preserved for the reader...
        assert "INTERSECT ALL" in result.sql
        assert "preserved as a comment" in result.sql
        # ...and nothing executable (in particular no bare, dedup-ing
        # INTERSECT/UNION) is shipped in its place.
        for line in result.sql.splitlines():
            assert line.strip() == "" or line.strip().startswith("--"), result.sql

    def test_star_columns_degrade_with_warning(self) -> None:
        sql = "SELECT * FROM t1 INTERSECT ALL SELECT * FROM t2"
        result = transpile(sql, "postgresql", "tsql")
        assert result.warnings
        assert result.unsupported
        assert "INTERSECT ALL" in result.sql
        for line in result.sql.splitlines():
            assert line.strip() == "" or line.strip().startswith("--"), result.sql


class TestIntersectExceptAllEmbeddedPipeline:
    """Dual-pipeline symmetry rule: embedded DML inside a routine body must
    go through the same IR pipeline as standalone DML."""

    def test_intersect_all_rewritten_inside_tsql_function_body(self) -> None:
        sql = (
            "CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN (SELECT COUNT(*) "
            f"FROM ({INTERSECT_ALL_SRC}) q); END; $$ LANGUAGE plpgsql;"
        )
        out = transpile(sql, "postgresql", "tsql").sql
        assert "INTERSECT ALL" not in out
        assert "ROW_NUMBER()" in out

    def test_except_all_native_inside_oracle_function_body(self) -> None:
        sql = (
            "CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN (SELECT COUNT(*) "
            f"FROM ({EXCEPT_ALL_SRC}) q); END; $$ LANGUAGE plpgsql;"
        )
        out = transpile(sql, "postgresql", "oracle").sql
        assert "MINUS ALL" in out


# --------------------------------------------------------------------------- #
# Live value verification (skipped without the matching engine URL)          #
# --------------------------------------------------------------------------- #

_URLS = {
    "postgresql": os.environ.get("UNIQUE_TEST_PG_URL"),
    "mysql": os.environ.get("UNIQUE_TEST_MYSQL_URL"),
    "oracle": os.environ.get("UNIQUE_TEST_ORACLE_URL"),
    "tsql": os.environ.get("UNIQUE_TEST_MSSQL_URL"),
}


def _run_rows(target: str, sql: str) -> list[tuple]:
    from tests.functional_equivalence.engine_runner import connect

    conn = connect(target, _URLS[target])  # type: ignore[arg-type]
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = sorted(tuple(row) for row in cur.fetchall())
        conn.rollback()
        return rows
    finally:
        conn.close()


@pytest.mark.integration
class TestIntersectExceptAllLiveValues:
    """The transpiled output must not just parse — it must return the exact
    duplicate-preserving multiset on the real engine. This is the mandatory
    live-verification step for B50 (a syntax-only check would have missed
    the original defect: the plain INTERSECT/MINUS spelling is also valid
    syntax, it just returns the wrong rows)."""

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle", "tsql"])
    def test_intersect_all_keeps_min_duplicate_count(self, target: str) -> None:
        if not _URLS[target]:
            pytest.skip(f"engine URL for {target} not set")
        out = transpile(INTERSECT_ALL_SRC, "postgresql", target).sql
        assert _run_rows(target, out) == [(1,)]

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle", "tsql"])
    def test_except_all_keeps_difference_duplicate_count(self, target: str) -> None:
        if not _URLS[target]:
            pytest.skip(f"engine URL for {target} not set")
        out = transpile(EXCEPT_ALL_SRC, "postgresql", target).sql
        assert _run_rows(target, out) == [(1,), (2,)]

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle", "tsql"])
    def test_intersect_all_multi_column_partition_live(self, target: str) -> None:
        if not _URLS[target]:
            pytest.skip(f"engine URL for {target} not set")
        sql = (
            "SELECT a, b FROM (SELECT 1 AS a, 'x' AS b UNION ALL SELECT 1, 'x' "
            "UNION ALL SELECT 1, 'x' UNION ALL SELECT 1, 'y' "
            "UNION ALL SELECT 2, 'z') t1 "
            "INTERSECT ALL SELECT a, b FROM (SELECT 1 AS a, 'x' AS b "
            "UNION ALL SELECT 1, 'y') t2"
        )
        out = transpile(sql, "postgresql", target).sql
        assert _run_rows(target, out) == [(1, "x"), (1, "y")]
