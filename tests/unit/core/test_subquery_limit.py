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


class TestMultiArmSetOp:
    """A UNION of 3+ arms dropped every middle arm (found by the differential
    result test: source returned {1,2}, target {1,3})."""

    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_three_and_four_way_union_keep_all_arms(self) -> None:
        for sql, arms in [
            ("SELECT 1 AS x UNION SELECT 2 UNION SELECT 3", 3),
            ("SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4", 4),
        ]:
            for target in ("postgresql", "oracle", "mysql", "tsql"):
                out = self.t.transpile(sql, "tsql", target).sql
                assert out.upper().count("SELECT") == arms, (target, out)
                assert "UNIQUE:" not in out
                _valid(out, target)

    def test_except_intersect_are_transpiled(self) -> None:
        # exp.Except/exp.Intersect are not exp.Union subclasses, so they used to
        # miss the dispatch to _convert_union and degrade to a carrier.
        for sql in (
            "SELECT 1 EXCEPT SELECT 2",
            "SELECT 3 EXCEPT SELECT 2 EXCEPT SELECT 1",
            "SELECT 1 INTERSECT SELECT 1",
        ):
            for target in ("postgresql", "oracle", "mysql", "tsql"):
                out = self.t.transpile(sql, "tsql", target).sql
                assert "UNIQUE:" not in out, (target, out)
                _valid(out, target)
        # Oracle spells EXCEPT as MINUS.
        assert (
            "MINUS"
            in self.t.transpile(
                "SELECT 1 EXCEPT SELECT 2", "tsql", "oracle"
            ).sql.upper()
        )
