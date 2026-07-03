"""Identifier quoting must be translated between engines, never stripped
(audit 2026-07-02, S1-1). `` `x` `` (MySQL) <-> "x" (PG/Oracle) <-> [x]
(T-SQL). Stripping turns reserved-word identifiers into syntax errors and
changes case-folding semantics on PostgreSQL/Oracle.
"""

import sqlglot

from unique.core.transpiler import Transpiler


def _valid(sql: str, dialect: str) -> None:
    read = {
        "tsql": "tsql",
        "oracle": "oracle",
        "postgresql": "postgres",
        "mysql": "mysql",
    }
    sqlglot.parse(sql, read=read[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestIdentifierQuoting:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_mysql_backticks_to_postgresql_double_quotes(self) -> None:
        out = self.t.transpile(
            "SELECT `select`, `from` FROM `order`", "mysql", "postgresql"
        ).sql
        assert '"select"' in out
        assert '"from"' in out
        assert '"order"' in out
        assert "`" not in out
        _valid(out, "postgresql")

    def test_tsql_brackets_to_mysql_backticks(self) -> None:
        out = self.t.transpile(
            "SELECT [select] FROM [order] WHERE [key] = 1", "tsql", "mysql"
        ).sql
        assert "`select`" in out
        assert "`order`" in out
        assert "`key`" in out
        assert "[" not in out
        _valid(out, "mysql")

    def test_postgresql_quotes_to_tsql_brackets(self) -> None:
        out = self.t.transpile('SELECT "select" FROM "order"', "postgresql", "tsql").sql
        assert "[select]" in out
        assert "[order]" in out
        _valid(out, "tsql")

    def test_qualified_quoted_column(self) -> None:
        out = self.t.transpile(
            "SELECT `order`.`key` FROM `order`", "mysql", "postgresql"
        ).sql
        assert '"order"."key"' in out
        _valid(out, "postgresql")

    def test_quoted_alias_preserved(self) -> None:
        out = self.t.transpile(
            "SELECT id AS `select` FROM t", "mysql", "postgresql"
        ).sql
        assert 'AS "select"' in out
        _valid(out, "postgresql")

    def test_quoted_schema_qualifier(self) -> None:
        out = self.t.transpile(
            'SELECT id FROM "my schema"."order"', "postgresql", "mysql"
        ).sql
        assert "`my schema`.`order`" in out
        _valid(out, "mysql")

    def test_create_table_with_quoted_columns(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE `order` (`key` INT NOT NULL, plain INT)",
            "mysql",
            "postgresql",
        ).sql
        assert '"order"' in out
        assert '"key"' in out
        _valid(out, "postgresql")

    def test_unquoted_identifiers_stay_unquoted(self) -> None:
        out = self.t.transpile(
            "SELECT id, name FROM users WHERE id = 1", "tsql", "postgresql"
        ).sql
        assert '"' not in out
        _valid(out, "postgresql")
