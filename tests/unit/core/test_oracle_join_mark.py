"""Oracle ``(+)`` outer joins and comma joins (audit 2026-07-02, S1-2).

``b.id(+)`` marks ``b`` as the optional side of a LEFT OUTER JOIN. It must be
rewritten as an explicit ``LEFT JOIN ... ON``; v0.7.0 emitted ``INNER JOIN``
with no ON clause — a syntax error on PostgreSQL *and* a silent LEFT->INNER
semantic change. Bare comma joins must stay CROSS JOINs, not become INNER
JOINs without ON.
"""

import sqlglot

from unique.core.transpiler import Transpiler


def _valid(sql: str, dialect: str) -> None:
    read = {
        "tsql": "tsql",
        "postgresql": "postgres",
        "mysql": "mysql",
        "oracle": "oracle",
    }
    sqlglot.parse(sql, read=read[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestOracleJoinMark:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_left_join_mark_to_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT a.x, b.y FROM a, b WHERE a.id = b.id(+)",
            "oracle",
            "postgresql",
        ).sql
        assert "LEFT JOIN b" in out
        assert "ON a.id = b.id" in out
        assert "(+)" not in out
        _valid(out, "postgresql")

    def test_join_mark_with_extra_predicate(self) -> None:
        out = self.t.transpile(
            "SELECT a.x FROM a, b WHERE a.id = b.id(+) AND a.t = 'x'",
            "oracle",
            "mysql",
        ).sql
        assert "LEFT JOIN b" in out
        assert "ON a.id = b.id" in out
        assert "WHERE" in out and "a.t = 'x'" in out
        _valid(out, "mysql")

    def test_comma_join_stays_cross_join(self) -> None:
        out = self.t.transpile(
            "SELECT a.x FROM a, b WHERE a.id = b.id", "oracle", "postgresql"
        ).sql
        # No ON clause exists, so INNER JOIN would be a syntax error; the
        # faithful spelling of a comma join is CROSS JOIN + WHERE.
        assert "INNER JOIN" not in out
        assert "CROSS JOIN b" in out
        assert "WHERE a.id = b.id" in out
        _valid(out, "postgresql")

    def test_explicit_joins_unaffected(self) -> None:
        out = self.t.transpile(
            "SELECT a.x FROM a JOIN b ON a.id = b.id", "oracle", "postgresql"
        ).sql
        assert "JOIN b" in out and "ON a.id = b.id" in out
        _valid(out, "postgresql")

    def test_join_using_preserved(self) -> None:
        out = self.t.transpile(
            "SELECT a.x FROM a JOIN b USING (id)", "postgresql", "mysql"
        ).sql
        # v0.7.0 dropped USING entirely, yielding JOIN with no condition.
        assert "USING (id)" in out
        _valid(out, "mysql")

    def test_join_using_to_tsql_becomes_on(self) -> None:
        out = self.t.transpile(
            "SELECT a.x FROM a JOIN b USING (id)", "postgresql", "tsql"
        ).sql
        # T-SQL has no USING; the single-join case is rewritten as ON.
        assert "USING" not in out.upper()
        assert "ON a.id = b.id" in out
        _valid(out, "tsql")
