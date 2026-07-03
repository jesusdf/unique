"""ILIKE and string-aggregation translation (audit 2026-07-02, S1-7/S1-8/S2-1)."""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestIlike:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_ilike_to_mysql_becomes_like_with_warning(self) -> None:
        result = self.t.transpile(
            "SELECT * FROM t WHERE name ILIKE '%a%'", "postgresql", "mysql"
        )
        assert "ILIKE" not in result.sql.upper()
        assert "name LIKE '%a%'" in result.sql
        assert result.warnings  # collation-dependence must be signalled
        _valid(result.sql, "mysql")

    def test_ilike_to_tsql_becomes_like(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE name ILIKE '%a%'", "postgresql", "tsql"
        ).sql
        assert "ILIKE" not in out.upper()
        assert "LIKE" in out
        _valid(out, "tsql")

    def test_ilike_to_oracle_uses_upper(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE name ILIKE '%a%'", "postgresql", "oracle"
        ).sql
        assert "ILIKE" not in out.upper()
        assert "UPPER(name) LIKE UPPER('%a%')" in out
        _valid(out, "oracle")

    def test_ilike_kept_for_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE name ILIKE '%a%'", "postgresql", "postgresql"
        ).sql
        assert "ILIKE" in out
        _valid(out, "postgresql")


class TestStringAggregation:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_group_concat_to_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT GROUP_CONCAT(name SEPARATOR ', ') FROM t", "mysql", "postgresql"
        ).sql
        assert "STRING_AGG(name, ', ')" in out
        assert "GROUP_CONCAT" not in out
        _valid(out, "postgresql")

    def test_group_concat_default_separator_to_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT GROUP_CONCAT(name) FROM t", "mysql", "postgresql"
        ).sql
        # MySQL's default separator is ','.
        assert "STRING_AGG(name, ',')" in out
        _valid(out, "postgresql")

    def test_string_agg_to_mysql_uses_separator_keyword(self) -> None:
        out = self.t.transpile(
            "SELECT STRING_AGG(name, ',') FROM t", "postgresql", "mysql"
        ).sql
        # GROUP_CONCAT(name, ',') concatenates ',' onto every value — wrong.
        assert "GROUP_CONCAT(name SEPARATOR ',')" in out
        _valid(out, "mysql")

    def test_group_concat_to_oracle_listagg(self) -> None:
        out = self.t.transpile(
            "SELECT GROUP_CONCAT(name SEPARATOR '; ') FROM t", "mysql", "oracle"
        ).sql
        assert "LISTAGG(name, '; ') WITHIN GROUP (ORDER BY name)" in out
        _valid(out, "oracle")

    def test_string_agg_to_tsql(self) -> None:
        out = self.t.transpile(
            "SELECT STRING_AGG(name, ',') FROM t", "postgresql", "tsql"
        ).sql
        assert "STRING_AGG(name, ',')" in out
        _valid(out, "tsql")
