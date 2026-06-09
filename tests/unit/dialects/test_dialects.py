"""Tests for individual dialect plugins."""

from unique.core.ast_nodes import SelectStatement
from unique.dialects.mysql import MySQLDialect
from unique.dialects.oracle import OracleDialect
from unique.dialects.postgresql import PostgreSQLDialect
from unique.dialects.tsql import TSQLDialect


class TestTSQLDialect:
    def setup_method(self) -> None:
        self.dialect = TSQLDialect()

    def test_name(self) -> None:
        assert self.dialect.name == "tsql"

    def test_parse_select(self) -> None:
        nodes = self.dialect.parse("SELECT TOP 5 * FROM users")
        assert len(nodes) == 1
        assert isinstance(nodes[0], SelectStatement)

    def test_emit_select(self) -> None:
        nodes = self.dialect.parse("SELECT * FROM users WHERE id = 1")
        sql = self.dialect.emit(nodes)
        assert "SELECT" in sql
        assert "users" in sql

    def test_supported_features(self) -> None:
        features = self.dialect.supported_features()
        assert "select" in features
        assert "insert" in features
        assert "top" in features


class TestOracleDialect:
    def setup_method(self) -> None:
        self.dialect = OracleDialect()

    def test_name(self) -> None:
        assert self.dialect.name == "oracle"

    def test_parse_select(self) -> None:
        nodes = self.dialect.parse("SELECT * FROM dual")
        assert len(nodes) == 1
        assert isinstance(nodes[0], SelectStatement)

    def test_emit_select(self) -> None:
        nodes = self.dialect.parse("SELECT * FROM users WHERE id = 1")
        sql = self.dialect.emit(nodes)
        assert "SELECT" in sql

    def test_supported_features(self) -> None:
        features = self.dialect.supported_features()
        assert "select" in features
        assert "sequences" in features


class TestPostgreSQLDialect:
    def setup_method(self) -> None:
        self.dialect = PostgreSQLDialect()

    def test_name(self) -> None:
        assert self.dialect.name == "postgresql"

    def test_parse_select_limit(self) -> None:
        nodes = self.dialect.parse("SELECT * FROM users LIMIT 10")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.limit is not None

    def test_emit_select(self) -> None:
        nodes = self.dialect.parse("SELECT * FROM users")
        sql = self.dialect.emit(nodes)
        assert "SELECT" in sql

    def test_supported_features(self) -> None:
        features = self.dialect.supported_features()
        assert "select" in features
        assert "returning_clause" in features


class TestMySQLDialect:
    def setup_method(self) -> None:
        self.dialect = MySQLDialect()

    def test_name(self) -> None:
        assert self.dialect.name == "mysql"

    def test_parse_select(self) -> None:
        nodes = self.dialect.parse("SELECT * FROM users LIMIT 10")
        stmt = nodes[0]
        assert isinstance(stmt, SelectStatement)

    def test_emit_select(self) -> None:
        nodes = self.dialect.parse("INSERT INTO t (a) VALUES (1)")
        sql = self.dialect.emit(nodes)
        assert "INSERT INTO t (a)" in sql

    def test_supported_features(self) -> None:
        features = self.dialect.supported_features()
        assert "select" in features
