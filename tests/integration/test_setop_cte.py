# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""A CTE directly preceding a set-op chain must survive conversion (B52).

sqlglot attaches a leading ``WITH`` to the OUTERMOST set-operation node
itself (``Union``/``Intersect``/``Except``), never to the first arm's own
``Select`` — verified across all four source dialects and both plain and
``ALL`` forms. ``_convert_union`` (``src/unique/core/converter/convert.py``)
never read that arg, so the CTE **definition** vanished from the output while
the arms kept referencing the (now undefined) CTE name — invalid output with
no warning (the UNIQUE-1228 unread-args tripwire only semi-warns: an
``internal:`` message, easy to miss, and only in ``warn``/``gate`` mode).

Every test here would fail against the pre-fix code: the CTE name would still
appear as a bare reference inside a ``FROM``/set-op arm, but never followed by
``AS (`` — i.e. never actually *defined*.
"""

from __future__ import annotations

import os
import re

import pytest
import sqlglot

from unique.core.transpiler import transpile

_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}

_ALL_TARGETS = ["tsql", "oracle", "postgresql", "mysql"]


def _assert_parses(sql: str, target: str) -> None:
    sqlglot.parse(
        sql, read=_SQLGLOT_DIALECT[target], error_level=sqlglot.ErrorLevel.RAISE
    )


def _assert_cte_defined(out: str, name: str) -> None:
    """The CTE must be an actual *definition* (``name AS (``), not merely a
    dangling reference left over from the arms after the definition was
    dropped — the exact shape of the B52 bug."""
    assert re.search(rf"\b{name}\b\s*\(?[^()]*\)?\s*AS\s*\(", out, re.I), out
    assert "WITH" in out.upper()


# --------------------------------------------------------------------------- #
# 1. Reproduce across the set-op node family and all four source dialects.   #
# --------------------------------------------------------------------------- #


class TestCtePreservedAcrossSetOpFamily:
    """UNION / INTERSECT / EXCEPT, plain and ALL, from every source dialect
    that can parse a leading CTE onto the chain."""

    @pytest.mark.parametrize(
        "source,op_sql",
        [
            ("tsql", "UNION"),
            ("tsql", "UNION ALL"),
            ("tsql", "INTERSECT"),
            ("tsql", "EXCEPT"),
            ("mysql", "UNION"),
            ("mysql", "UNION ALL"),
            ("mysql", "INTERSECT"),
            ("mysql", "INTERSECT ALL"),
            ("mysql", "EXCEPT"),
            ("oracle", "UNION"),
            ("oracle", "UNION ALL"),
            ("oracle", "INTERSECT"),
            ("oracle", "MINUS"),
            ("postgresql", "UNION"),
            ("postgresql", "UNION ALL"),
            ("postgresql", "INTERSECT"),
            ("postgresql", "INTERSECT ALL"),
            ("postgresql", "EXCEPT"),
            ("postgresql", "EXCEPT ALL"),
        ],
    )
    @pytest.mark.parametrize("target", _ALL_TARGETS)
    def test_cte_survives_setop_chain(
        self, source: str, op_sql: str, target: str
    ) -> None:
        sql = (
            f"WITH cte AS (SELECT 1 AS a) SELECT a FROM cte {op_sql} SELECT a FROM cte"
        )
        result = transpile(sql, source, target)
        _assert_cte_defined(result.sql, "cte")
        _assert_parses(result.sql, target)
        # The UNIQUE-1228 unread-args tripwire (semi-warned "internal: unread
        # sqlglot arg 'with'/'with_'...") must be GONE now that ``with`` is
        # actually consumed.
        assert not any("unread sqlglot arg" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# 2. CTE shapes: single / multiple / RECURSIVE.                              #
# --------------------------------------------------------------------------- #


class TestCteShapes:
    def test_multiple_ctes_all_survive(self) -> None:
        sql = (
            "WITH a AS (SELECT 1 AS x), b AS (SELECT 2 AS x) "
            "SELECT x FROM a UNION SELECT x FROM b"
        )
        out = transpile(sql, "tsql", "oracle").sql
        _assert_cte_defined(out, "a")
        _assert_cte_defined(out, "b")
        _assert_parses(out, "oracle")

    @pytest.mark.parametrize("target", _ALL_TARGETS)
    def test_recursive_cte_survives_setop_chain(self, target: str) -> None:
        # PostgreSQL requires the explicit RECURSIVE keyword; MySQL infers it
        # like Oracle/T-SQL but the source dialect can only be one at a time,
        # so this uses PostgreSQL as the recursion-explicit source.
        sql = (
            "WITH RECURSIVE cte AS ("
            "SELECT 1 AS a UNION ALL SELECT a + 1 FROM cte WHERE a < 3"
            ") SELECT a FROM cte UNION SELECT a FROM cte"
        )
        out = transpile(sql, "postgresql", target).sql
        _assert_cte_defined(out, "cte")
        _assert_parses(out, target)


# --------------------------------------------------------------------------- #
# 3. Composition with B50's T-SQL INTERSECT ALL / EXCEPT ALL rewrite.        #
# --------------------------------------------------------------------------- #


class TestCteComposesWithTsqlSetopAllRewrite:
    """A CTE ahead of an INTERSECT ALL/EXCEPT ALL bound for T-SQL must
    compose with the ROW_NUMBER-pairing rewrite (``Transformer.
    _gate_tsql_setop_all``): the CTE stays defined AND the pairing is
    applied — never the CTE silently dropped, whichever path a given shape
    takes."""

    def test_cte_preserved_and_pairing_applied(self) -> None:
        sql = (
            "WITH t1 AS (SELECT a FROM (SELECT 1 AS a UNION ALL SELECT 1 "
            "UNION ALL SELECT 2) x), t2 AS (SELECT a FROM (SELECT 1 AS a) y) "
            "SELECT a FROM t1 INTERSECT ALL SELECT a FROM t2"
        )
        result = transpile(sql, "postgresql", "tsql")
        out = result.sql
        _assert_cte_defined(out, "t1")
        _assert_cte_defined(out, "t2")
        assert "INTERSECT ALL" not in out
        assert "ROW_NUMBER()" in out
        assert "\nINTERSECT\n" in out
        _assert_parses(out, "tsql")
        # The rewrite is a faithful structural transform, not a degrade.
        assert result.warnings == []
        assert result.unsupported == []
        # The CTE must be defined BEFORE its first reference (outside the
        # pairing subquery) — a naive re-attach could park it in the wrong
        # place and still "contain" the text without it being valid SQL.
        assert out.index("t1 AS (") < out.index("FROM t1")

    def test_unreachable_shape_degrades_whole_with_cte_intact(self) -> None:
        # An ALL op immediately followed by more chained set operations is
        # outside the bounded rewrite (see test_setop_all.py); it must fall
        # back to a WHOLE, honest degrade carrier that still carries the CTE
        # text — never a fragment that silently drops it.
        sql = (
            "WITH cte AS (SELECT 1 AS a) "
            "SELECT a FROM cte INTERSECT ALL SELECT a FROM cte "
            "UNION SELECT a FROM cte"
        )
        result = transpile(sql, "postgresql", "tsql")
        assert result.warnings, "an unrewritable ALL-op chain must warn"
        assert result.unsupported
        assert "preserved as a comment" in result.sql
        assert "cte" in result.sql
        assert "AS (" in result.sql
        for line in result.sql.splitlines():
            assert line.strip() == "" or line.strip().startswith("--"), result.sql


# --------------------------------------------------------------------------- #
# 4. Live value verification (skipped without the matching engine URL).      #
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
class TestCteSetopLiveValues:
    """The transpiled output must return the identical result set the source
    would, on every real engine — a syntax-only check would miss a CTE that
    parses but resolves to the wrong (or an empty) row set."""

    @pytest.mark.parametrize("target", _ALL_TARGETS)
    def test_plain_union_dedups_through_cte(self, target: str) -> None:
        if not _URLS[target]:
            pytest.skip(f"engine URL for {target} not set")
        sql = "WITH t AS (SELECT 1 AS a) SELECT a FROM t UNION SELECT a FROM t"
        out = transpile(sql, "postgresql", target).sql
        assert _run_rows(target, out) == [(1,)]

    @pytest.mark.parametrize("target", _ALL_TARGETS)
    def test_intersect_all_through_cte_keeps_min_duplicate_count(
        self, target: str
    ) -> None:
        if not _URLS[target]:
            pytest.skip(f"engine URL for {target} not set")
        sql = (
            "WITH t1 AS (SELECT a FROM (SELECT 1 AS a UNION ALL SELECT 1 "
            "UNION ALL SELECT 2) x), t2 AS (SELECT a FROM (SELECT 1 AS a) y) "
            "SELECT a FROM t1 INTERSECT ALL SELECT a FROM t2"
        )
        out = transpile(sql, "postgresql", target).sql
        assert _run_rows(target, out) == [(1,)]

    @pytest.mark.parametrize("target", _ALL_TARGETS)
    def test_except_all_through_cte_keeps_difference_duplicate_count(
        self, target: str
    ) -> None:
        if not _URLS[target]:
            pytest.skip(f"engine URL for {target} not set")
        sql = (
            "WITH t1 AS (SELECT a FROM (SELECT 1 AS a UNION ALL SELECT 1 "
            "UNION ALL SELECT 2) x), t2 AS (SELECT a FROM (SELECT 1 AS a) y) "
            "SELECT a FROM t1 EXCEPT ALL SELECT a FROM t2"
        )
        out = transpile(sql, "postgresql", target).sql
        assert _run_rows(target, out) == [(1,), (2,)]
