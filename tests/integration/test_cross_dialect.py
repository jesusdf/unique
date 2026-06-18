"""Integration tests for cross-dialect SQL transpilation.

These tests verify end-to-end transpilation between all supported
dialect pairs, covering DQL, DML, DDL, functions, and edge cases.
"""

import pytest

from unique.core.transpiler import Transpiler

# All 12 directional pairs (4 dialects × 3 targets each)
ALL_PAIRS = [
    (s, t)
    for s in ("tsql", "oracle", "postgresql", "mysql")
    for t in ("tsql", "oracle", "postgresql", "mysql")
    if s != t
]

TARGETS = ("tsql", "oracle", "postgresql", "mysql")


class TestCrossDialectSelect:
    """Basic SELECT statements across all dialect pairs."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_star(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        result = transpiler.transpile("SELECT * FROM users", source, target)
        assert "SELECT" in result.sql
        assert "users" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_where(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        result = transpiler.transpile(
            "SELECT id, name FROM users WHERE id = 1",
            source,
            target,
        )
        assert "WHERE" in result.sql
        assert "id" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_join(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT a.id, b.name FROM a INNER JOIN b ON a.id = b.a_id"
        result = transpiler.transpile(sql, source, target)
        assert "JOIN" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_order_by(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM users ORDER BY name ASC"
        result = transpiler.transpile(sql, source, target)
        assert "ORDER BY" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_group_by(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT dept, COUNT(*) FROM emp GROUP BY dept"
        result = transpiler.transpile(sql, source, target)
        assert "GROUP BY" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_distinct(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT DISTINCT name FROM users"
        result = transpiler.transpile(sql, source, target)
        assert "DISTINCT" in result.sql


class TestCrossDialectLimit:
    """LIMIT/TOP/ROWNUM conversions."""

    @pytest.mark.parametrize("target", TARGETS)
    def test_tsql_top_to_target(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT TOP 10 * FROM users",
            "tsql",
            target,
        )
        assert "users" in result.sql
        # Every target should produce valid output (no raw None)
        assert "None" not in result.sql or "/* UNIQUE:" in result.sql

    @pytest.mark.parametrize("target", TARGETS)
    def test_pg_limit_to_target(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users LIMIT 10",
            "postgresql",
            target,
        )
        assert "users" in result.sql

    @pytest.mark.parametrize("target", TARGETS)
    def test_pg_limit_offset_to_target(
        self, transpiler: Transpiler, target: str
    ) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users LIMIT 10 OFFSET 20",
            "postgresql",
            target,
        )
        assert "users" in result.sql


class TestCrossDialectDML:
    """INSERT, UPDATE, DELETE across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_insert(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "INSERT INTO t (a, b) VALUES (1, 'x')",
            source,
            target,
        )
        assert "INSERT INTO" in result.sql
        assert "(a, b)" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_update(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "UPDATE t SET a = 1 WHERE id = 5",
            source,
            target,
        )
        assert "UPDATE" in result.sql
        assert "SET" in result.sql
        assert "WHERE" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_delete(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "DELETE FROM t WHERE id = 1",
            source,
            target,
        )
        assert "DELETE" in result.sql
        assert "WHERE" in result.sql


class TestCrossDialectFunctions:
    """Function translation across dialects."""

    @pytest.mark.parametrize("target", ("postgresql", "mysql", "oracle"))
    def test_isnull_from_tsql(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT ISNULL(name, 'default') FROM t",
            "tsql",
            target,
        )
        sql_upper = result.sql.upper()
        assert "COALESCE" in sql_upper or "NVL" in sql_upper

    @pytest.mark.parametrize("target", ("tsql", "mysql", "postgresql"))
    def test_nvl_from_oracle(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT NVL(name, 'default') FROM t",
            "oracle",
            target,
        )
        sql_upper = result.sql.upper()
        assert "COALESCE" in sql_upper or "ISNULL" in sql_upper or "NVL" in sql_upper

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_count_star(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile("SELECT COUNT(*) FROM t", source, target)
        assert "COUNT" in result.sql.upper()


class TestCrossDialectCTE:
    """Common Table Expressions across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_simple_cte(self, transpiler: Transpiler, source: str, target: str) -> None:
        sql = "WITH cte AS (SELECT id FROM users) SELECT * FROM cte"
        result = transpiler.transpile(sql, source, target)
        assert "WITH" in result.sql.upper()
        assert "cte" in result.sql.lower()


class TestCrossDialectSubquery:
    """Subqueries across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_subquery_in_where(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM t WHERE id IN (SELECT id FROM t2)"
        result = transpiler.transpile(sql, source, target)
        assert "SELECT" in result.sql


class TestCrossDialectDDL:
    """CREATE TABLE across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_create_table(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "CREATE TABLE users (id INT, name VARCHAR(100))"
        result = transpiler.transpile(sql, source, target)
        assert "CREATE TABLE" in result.sql.upper()
        assert "users" in result.sql

    def test_identity_column_to_postgresql(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT IDENTITY(1,1) NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "SERIAL" in result.sql.upper()

    def test_identity_column_to_mysql(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT IDENTITY(1,1) NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "mysql")
        assert "AUTO_INCREMENT" in result.sql.upper()

    def test_identity_column_to_oracle(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT IDENTITY(1,1) NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "oracle")
        assert "GENERATED" in result.sql.upper()
        assert "IDENTITY" in result.sql.upper()

    def test_explicit_null_not_forced_not_null(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (name VARCHAR(50) NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        # An explicit NULL must not become NOT NULL.
        assert "NOT NULL" not in result.sql.upper()

    def test_column_default_preserved(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (status INT DEFAULT 0)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "DEFAULT 0" in result.sql
        # No stray UNIQUE comment wrapper around the default value.
        assert "/* UNIQUE" not in result.sql

    def test_rowguidcol_stripped(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (rowguid UNIQUEIDENTIFIER ROWGUIDCOL NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "ROWGUIDCOL" not in result.sql.upper()
        assert "CREATE TABLE" in result.sql.upper()


class TestCrossDialectExpressions:
    """Complex expressions across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_case_expression(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT CASE WHEN id > 10 THEN 'big' ELSE 'small' END FROM t"
        result = transpiler.transpile(sql, source, target)
        assert "CASE" in result.sql.upper()
        assert "WHEN" in result.sql.upper()

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_between(self, transpiler: Transpiler, source: str, target: str) -> None:
        sql = "SELECT * FROM t WHERE id BETWEEN 1 AND 10"
        result = transpiler.transpile(sql, source, target)
        # Should produce valid output (BETWEEN or equivalent)
        assert "SELECT" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_like(self, transpiler: Transpiler, source: str, target: str) -> None:
        sql = "SELECT * FROM t WHERE name LIKE '%test%'"
        result = transpiler.transpile(sql, source, target)
        assert "SELECT" in result.sql


class TestMultipleStatements:
    """Multi-statement scripts."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_two_statements(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM a; SELECT * FROM b;"
        result = transpiler.transpile(sql, source, target)
        # Both tables should appear in output
        assert "a" in result.sql.lower()
        assert "b" in result.sql.lower()
