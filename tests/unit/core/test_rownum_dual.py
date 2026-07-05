"""Oracle ROWNUM and FROM dual (audit 2026-07-02, S1-5 / S1-6).

``WHERE ROWNUM <= n`` must become the target's row-limit idiom; ``FROM dual``
must be dropped for engines where it names a non-existent relation.
"""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestRownum:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_rownum_lte_to_postgresql_limit(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE ROWNUM <= 5", "oracle", "postgresql"
        ).sql
        assert "ROWNUM" not in out.upper()
        assert "LIMIT 5" in out
        assert "WHERE" not in out.upper()
        _valid(out, "postgresql")

    def test_rownum_lt_to_mysql_limit(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE ROWNUM < 6", "oracle", "mysql"
        ).sql
        assert "ROWNUM" not in out.upper()
        assert "LIMIT 5" in out
        _valid(out, "mysql")

    def test_rownum_to_tsql_top(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE ROWNUM <= 5", "oracle", "tsql"
        ).sql
        assert "ROWNUM" not in out.upper()
        assert "TOP 5" in out
        _valid(out, "tsql")

    def test_rownum_anded_with_predicate(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE status = 'A' AND ROWNUM <= 10",
            "oracle",
            "postgresql",
        ).sql
        assert "ROWNUM" not in out.upper()
        assert "WHERE status = 'A'" in out
        assert "LIMIT 10" in out
        _valid(out, "postgresql")

    def test_unrewritable_rownum_is_signalled(self) -> None:
        result = self.t.transpile("SELECT ROWNUM, x FROM t", "oracle", "postgresql")
        # ROWNUM in the select list has no simple LIMIT equivalent; the
        # conversion must be signalled, never silently passed through.
        assert result.warnings or result.unsupported


class TestFromDual:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_dual_dropped_for_postgresql(self) -> None:
        out = self.t.transpile("SELECT 1 FROM dual", "oracle", "postgresql").sql
        assert "DUAL" not in out.upper()
        _valid(out, "postgresql")

    def test_dual_dropped_for_tsql(self) -> None:
        out = self.t.transpile("SELECT SYSDATE FROM dual", "oracle", "tsql").sql
        assert "DUAL" not in out.upper()
        _valid(out, "tsql")

    def test_dual_kept_for_mysql(self) -> None:
        # MySQL accepts FROM DUAL; keeping it is faithful.
        out = self.t.transpile("SELECT 1 FROM dual", "oracle", "mysql").sql
        _valid(out, "mysql")

    def test_tableless_select_gets_dual_for_oracle(self) -> None:
        # The reverse of dropping DUAL: a table-less SELECT is invalid Oracle
        # (ORA-00923), so a T-SQL ``SELECT 1`` must gain ``FROM DUAL``.
        out = self.t.transpile("SELECT 1", "tsql", "oracle").sql
        assert "FROM DUAL" in out.upper()
        _valid(out, "oracle")

    def test_tableless_select_null_with_comment_to_oracle(self) -> None:
        # Regression: "-- c\nSELECT NULL\nGO" emitted ``SELECT NULL`` with no
        # FROM (invalid Oracle); the comment must survive and DUAL be added.
        out = self.t.transpile("-- c\nselect null\ngo", "tsql", "oracle").sql
        assert "-- c" in out
        assert "SELECT NULL" in out.upper()
        assert "FROM DUAL" in out.upper()
        _valid(out, "oracle")

    def test_tableless_select_dual_from_mysql(self) -> None:
        out = self.t.transpile("SELECT SYSDATE()", "mysql", "oracle").sql
        assert "FROM DUAL" in out.upper()
        _valid(out, "oracle")

    def test_select_with_from_unchanged_for_oracle(self) -> None:
        # A SELECT that already has a FROM must not get a spurious DUAL.
        out = self.t.transpile("SELECT id FROM t", "tsql", "oracle").sql
        assert "DUAL" not in out.upper()
        _valid(out, "oracle")


class TestLimitToTsql:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_limit_to_tsql_emits_top(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t ORDER BY id LIMIT 5", "mysql", "tsql"
        ).sql
        # v0.7.0 reduced the row limit to a comment — silent row-limit loss.
        assert "SELECT TOP 5" in out
        assert "/*" not in out
        assert "LIMIT" not in out.upper()
        _valid(out, "tsql")

    def test_limit_offset_to_tsql_uses_offset_fetch(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t ORDER BY id LIMIT 5 OFFSET 10", "mysql", "tsql"
        ).sql
        assert "OFFSET 10 ROWS" in out
        assert "FETCH NEXT 5 ROWS ONLY" in out
        _valid(out, "tsql")
