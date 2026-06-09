"""Tests for the shared converter (parse_sql and emit_sql)."""

import pytest

from unique.core.ast_nodes import (
    BinaryOp,
    BinaryOperator,
    ColumnRef,
    CreateTableStatement,
    DeleteStatement,
    FunctionCall,
    InsertStatement,
    LimitClause,
    Literal,
    SelectStatement,
    Star,
    TableRef,
    UpdateStatement,
)
from unique.core.converter import emit_sql, parse_sql

# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseSelectBasic:
    def test_select_star(self) -> None:
        nodes = parse_sql("SELECT * FROM users", "tsql")
        assert len(nodes) == 1
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert any(isinstance(c, Star) for c in stmt.columns)
        assert isinstance(stmt.from_clause, TableRef)
        assert stmt.from_clause.name == "users"

    def test_select_columns(self) -> None:
        nodes = parse_sql("SELECT id, name FROM users", "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.columns) == 2

    def test_select_where(self) -> None:
        nodes = parse_sql("SELECT * FROM t WHERE id = 1", "mysql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.where is not None
        assert isinstance(stmt.where, BinaryOp)
        assert stmt.where.operator == BinaryOperator.EQ

    def test_select_distinct(self) -> None:
        nodes = parse_sql("SELECT DISTINCT name FROM users", "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.distinct is True

    def test_select_order_by(self) -> None:
        nodes = parse_sql("SELECT * FROM t ORDER BY name ASC, id DESC", "tsql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.order_by) == 2

    def test_select_group_by_having(self) -> None:
        nodes = parse_sql(
            "SELECT dept, COUNT(*) as cnt FROM emp GROUP BY dept HAVING COUNT(*) > 5",
            "postgresql",
        )
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.group_by) > 0
        assert stmt.having is not None


class TestParseSelectLimit:
    def test_tsql_top(self) -> None:
        nodes = parse_sql("SELECT TOP 10 * FROM users", "tsql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.limit is not None
        assert isinstance(stmt.limit.limit, Literal)
        assert stmt.limit.limit.value == 10

    def test_postgresql_limit_offset(self) -> None:
        nodes = parse_sql("SELECT * FROM t LIMIT 20 OFFSET 5", "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.limit is not None
        assert stmt.limit.limit is not None
        assert stmt.limit.offset is not None

    def test_mysql_limit(self) -> None:
        nodes = parse_sql("SELECT * FROM t LIMIT 10", "mysql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.limit is not None


class TestParseSelectJoin:
    def test_inner_join(self) -> None:
        sql = "SELECT * FROM a INNER JOIN b ON a.id = b.a_id"
        nodes = parse_sql(sql, "tsql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.joins) == 1

    def test_left_join(self) -> None:
        sql = "SELECT * FROM a LEFT JOIN b ON a.id = b.a_id"
        nodes = parse_sql(sql, "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.joins) == 1

    def test_multiple_joins(self) -> None:
        sql = (
            "SELECT * FROM a "
            "INNER JOIN b ON a.id = b.a_id "
            "LEFT JOIN c ON b.id = c.b_id"
        )
        nodes = parse_sql(sql, "mysql")
        stmt = nodes[0]
        assert len(stmt.joins) == 2


class TestParseSelectCTE:
    def test_with_clause(self) -> None:
        sql = "WITH cte AS (SELECT 1 AS val) SELECT * FROM cte"
        nodes = parse_sql(sql, "tsql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.ctes) == 1
        assert stmt.ctes[0].name == "cte"


class TestParseFunctions:
    def test_coalesce(self) -> None:
        nodes = parse_sql("SELECT COALESCE(a, b, c) FROM t", "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        col = stmt.columns[0]
        assert isinstance(col, FunctionCall)
        assert col.name.upper() == "COALESCE"
        assert len(col.args) == 3

    def test_count_star(self) -> None:
        nodes = parse_sql("SELECT COUNT(*) FROM t", "mysql")
        stmt = nodes[0]
        col = stmt.columns[0]
        assert isinstance(col, FunctionCall)

    def test_isnull_becomes_coalesce(self) -> None:
        """sqlglot normalizes ISNULL to COALESCE internally."""
        nodes = parse_sql("SELECT ISNULL(a, 0) FROM t", "tsql")
        stmt = nodes[0]
        col = stmt.columns[0]
        assert isinstance(col, FunctionCall)
        assert col.name.upper() == "COALESCE"
        assert len(col.args) == 2


class TestParseInsert:
    def test_insert_values(self) -> None:
        nodes = parse_sql("INSERT INTO t (a, b) VALUES (1, 'x')", "tsql")
        stmt = nodes[0]
        assert isinstance(stmt, InsertStatement)
        assert stmt.table.name == "t"
        assert stmt.columns == ("a", "b")
        assert len(stmt.values) == 1
        assert len(stmt.values[0]) == 2

    def test_insert_multiple_rows(self) -> None:
        nodes = parse_sql("INSERT INTO t (a) VALUES (1), (2), (3)", "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, InsertStatement)
        assert len(stmt.values) == 3

    def test_insert_select(self) -> None:
        nodes = parse_sql("INSERT INTO t2 (a) SELECT a FROM t1", "mysql")
        stmt = nodes[0]
        assert isinstance(stmt, InsertStatement)
        assert stmt.select is not None
        assert isinstance(stmt.select, SelectStatement)


class TestParseUpdate:
    def test_simple_update(self) -> None:
        nodes = parse_sql("UPDATE t SET a = 1 WHERE id = 5", "tsql")
        stmt = nodes[0]
        assert isinstance(stmt, UpdateStatement)
        assert stmt.table.name == "t"
        assert len(stmt.assignments) == 1
        assert stmt.where is not None


class TestParseDelete:
    def test_simple_delete(self) -> None:
        nodes = parse_sql("DELETE FROM t WHERE id = 1", "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, DeleteStatement)
        assert stmt.table.name == "t"
        assert stmt.where is not None


class TestParseCreateTable:
    def test_create_table(self) -> None:
        sql = "CREATE TABLE users (id INT, name VARCHAR(100))"
        nodes = parse_sql(sql, "postgresql")
        stmt = nodes[0]
        assert isinstance(stmt, CreateTableStatement)
        assert stmt.table.name == "users"
        assert len(stmt.columns) >= 2


class TestParseMultipleStatements:
    def test_two_statements(self) -> None:
        sql = "SELECT 1; SELECT 2;"
        nodes = parse_sql(sql, "tsql")
        assert len(nodes) == 2


# ---------------------------------------------------------------------------
# Emission tests
# ---------------------------------------------------------------------------


class TestEmitSelect:
    def test_simple_select(self) -> None:
        stmt = SelectStatement(
            columns=(Star(),),
            from_clause=TableRef(name="users"),
        )
        sql = emit_sql([stmt], "postgresql")
        assert "SELECT" in sql
        assert "*" in sql
        assert "users" in sql

    def test_select_with_where(self) -> None:
        stmt = SelectStatement(
            columns=(ColumnRef(name="id"),),
            from_clause=TableRef(name="t"),
            where=BinaryOp(
                operator=BinaryOperator.EQ,
                left=ColumnRef(name="id"),
                right=Literal(value=1),
            ),
        )
        sql = emit_sql([stmt], "mysql")
        assert "WHERE" in sql
        assert "id = 1" in sql

    def test_select_limit_postgresql(self) -> None:
        stmt = SelectStatement(
            columns=(Star(),),
            from_clause=TableRef(name="t"),
            limit=LimitClause(limit=Literal(value=10)),
        )
        sql = emit_sql([stmt], "postgresql")
        assert "LIMIT 10" in sql

    def test_select_limit_mysql(self) -> None:
        stmt = SelectStatement(
            columns=(Star(),),
            from_clause=TableRef(name="t"),
            limit=LimitClause(limit=Literal(value=5)),
        )
        sql = emit_sql([stmt], "mysql")
        assert "LIMIT 5" in sql


class TestEmitInsert:
    def test_insert_with_columns(self) -> None:
        stmt = InsertStatement(
            table=TableRef(name="t"),
            columns=("a", "b"),
            values=((Literal(value=1), Literal(value="x")),),
        )
        sql = emit_sql([stmt], "postgresql")
        assert "INSERT INTO t (a, b)" in sql
        assert "VALUES" in sql


class TestEmitUpdate:
    def test_update_with_where(self) -> None:
        stmt = UpdateStatement(
            table=TableRef(name="t"),
            assignments=(("name", Literal(value="new")),),
            where=BinaryOp(
                operator=BinaryOperator.EQ,
                left=ColumnRef(name="id"),
                right=Literal(value=1),
            ),
        )
        sql = emit_sql([stmt], "mysql")
        assert "UPDATE t" in sql
        assert "SET name = 'new'" in sql
        assert "WHERE" in sql


class TestEmitDelete:
    def test_delete_with_where(self) -> None:
        stmt = DeleteStatement(
            table=TableRef(name="t"),
            where=BinaryOp(
                operator=BinaryOperator.EQ,
                left=ColumnRef(name="id"),
                right=Literal(value=1),
            ),
        )
        sql = emit_sql([stmt], "postgresql")
        assert "DELETE FROM t" in sql
        assert "WHERE" in sql


class TestRoundTrip:
    """Parse then emit should produce functionally equivalent SQL."""

    @pytest.mark.parametrize(
        "sql,dialect",
        [
            ("SELECT * FROM users", "postgresql"),
            ("SELECT id, name FROM t WHERE id > 10", "mysql"),
            ("INSERT INTO t (a) VALUES (1)", "tsql"),
            ("UPDATE t SET a = 1 WHERE id = 1", "oracle"),
            ("DELETE FROM t WHERE id = 1", "postgresql"),
        ],
    )
    def test_round_trip_preserves_structure(self, sql: str, dialect: str) -> None:
        nodes = parse_sql(sql, dialect)
        output = emit_sql(nodes, dialect)
        # Re-parse the output to verify it's valid
        nodes2 = parse_sql(output, dialect)
        assert len(nodes2) == len(nodes)
        assert type(nodes2[0]) is type(nodes[0])
