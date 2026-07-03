"""Boolean literals and CURRENT_TIMESTAMP() defaults (audit S1-9 / S1-10).

T-SQL and Oracle (pre-23c) have no boolean literals in SQL contexts:
TRUE/FALSE must become 1/0. PostgreSQL rejects the parenthesized
``CURRENT_TIMESTAMP()`` in DDL defaults.
"""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestBooleanLiterals:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_where_true_to_tsql(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE active = TRUE", "postgresql", "tsql"
        ).sql
        assert "TRUE" not in out.upper()
        assert "active = 1" in out
        _valid(out, "tsql")

    def test_where_false_to_oracle(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE active = FALSE", "postgresql", "oracle"
        ).sql
        assert "FALSE" not in out.upper()
        assert "active = 0" in out
        _valid(out, "oracle")

    def test_boolean_default_to_tsql(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (ok BOOLEAN DEFAULT TRUE)", "postgresql", "tsql"
        ).sql
        assert "DEFAULT 1" in out
        assert "TRUE" not in out.upper()
        _valid(out, "tsql")

    def test_boolean_kept_for_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE active = TRUE", "mysql", "postgresql"
        ).sql
        assert "active = TRUE" in out
        _valid(out, "postgresql")


class TestCurrentTimestampDefault:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_parens_stripped_for_postgresql(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (ts DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "mysql",
            "postgresql",
        ).sql
        assert "CURRENT_TIMESTAMP()" not in out
        assert "DEFAULT CURRENT_TIMESTAMP" in out
        _valid(out, "postgresql")

    def test_parens_stripped_for_oracle(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (ts DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "mysql",
            "oracle",
        ).sql
        assert "CURRENT_TIMESTAMP()" not in out
        _valid(out, "oracle")
