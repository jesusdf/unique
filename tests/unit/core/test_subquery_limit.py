"""Regression tests for bugs the corpus × live-execution sweep surfaced.

Derived-table aliases and joined subqueries were dropped by the IR converter,
and a T-SQL ``OFFSET … FETCH NEXT n`` leaked ``LIMIT None``. These are pinned as
fast unit tests (no live DB) so they also guard the plain suite.
"""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestDerivedTableAlias:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_derived_table_alias_preserved(self) -> None:
        for target in ("postgresql", "oracle", "mysql", "tsql"):
            out = self.t.transpile(
                "SELECT c.x FROM (SELECT 1 AS x) c", "tsql", target
            ).sql
            assert " c" in out and "FROM (" in out, (target, out)
            _valid(out, target)

    def test_union_derived_table_alias_preserved(self) -> None:
        out = self.t.transpile(
            "SELECT COUNT(*) AS n FROM (SELECT 1 AS x UNION SELECT 2) c",
            "tsql",
            "mysql",
        ).sql
        # MySQL rejects a derived table without its own alias.
        assert ") c" in out
        _valid(out, "mysql")


class TestJoinedSubquery:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_joined_subquery_not_dropped(self) -> None:
        sql = (
            "SELECT a.x FROM (SELECT 1 AS x) a "
            "INNER JOIN (SELECT 1 AS y) b ON a.x = b.y"
        )
        for target in ("postgresql", "oracle", "mysql", "tsql"):
            out = self.t.transpile(sql, "tsql", target).sql
            # The joined subquery and its alias must both survive.
            assert "SELECT 1 AS y" in out, (target, out)
            assert "INNER JOIN  " not in out, (target, out)
            _valid(out, target)


class TestOffsetFetchLimit:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_offset_fetch_no_none_leak(self) -> None:
        sql = "SELECT x FROM t ORDER BY x OFFSET 5 ROWS FETCH NEXT 10 ROWS ONLY"
        for target in ("postgresql", "mysql", "oracle"):
            out = self.t.transpile(sql, "tsql", target).sql
            assert "None" not in out, (target, out)
            assert "10" in out
            _valid(out, target)
