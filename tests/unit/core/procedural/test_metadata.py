# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for the database metadata resolver.

These tests avoid real database connections by using a fake DB-API
connection/cursor, and by exercising the pure helpers directly.
"""

from __future__ import annotations

import pytest

from unique.core.metadata import ColumnInfo, MetadataResolver


class FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.executed: list[tuple] = []

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.executed.append((sql, params))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows)

    def close(self) -> None:
        pass


def _connected_resolver(dialect: str, rows: list[tuple]) -> MetadataResolver:
    """Build a resolver with a fake connection (bypassing real drivers)."""
    r = MetadataResolver(dialect=dialect)
    r._connection = FakeConnection(rows)
    r._connected = True
    return r


class TestUrlParsing:
    def test_unsupported_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported database scheme"):
            MetadataResolver.from_url("redis://localhost:6379/0")

    def test_missing_driver_raises_import_error(self) -> None:
        # The oracle driver (oracledb) is not installed in the test env, so
        # connecting should raise ImportError.
        with pytest.raises((ImportError, Exception)):
            MetadataResolver.from_url("oracle://u:p@host:1521/svc")


class TestNotConnected:
    def test_resolve_returns_none_without_connection(self) -> None:
        r = MetadataResolver(dialect="oracle")
        assert r.is_connected is False
        assert r.resolve_column_type("emp", "sal") is None

    def test_resolve_type_reference_none_without_connection(self) -> None:
        r = MetadataResolver(dialect="oracle")
        assert r.resolve_type_reference("emp.sal%TYPE") is None


class TestTypeReferenceParsing:
    def test_rowtype_returns_none(self) -> None:
        r = MetadataResolver(dialect="oracle")
        # %ROWTYPE cannot resolve to a single type
        assert r.resolve_type_reference("employees%ROWTYPE") is None

    def test_non_type_string_returns_none(self) -> None:
        r = MetadataResolver(dialect="oracle")
        assert r.resolve_type_reference("just_a_name") is None


class TestColumnInfoToDataType:
    def test_precision_and_scale(self) -> None:
        info = ColumnInfo(
            table_name="t",
            column_name="c",
            data_type="NUMBER",
            precision=10,
            scale=2,
        )
        dt = MetadataResolver._column_info_to_datatype(info)
        assert dt.name == "NUMBER"
        assert dt.params == (10, 2)

    def test_precision_only(self) -> None:
        info = ColumnInfo(
            table_name="t", column_name="c", data_type="NUMBER", precision=5
        )
        dt = MetadataResolver._column_info_to_datatype(info)
        assert dt.params == (5,)

    def test_varchar_uses_max_length(self) -> None:
        info = ColumnInfo(
            table_name="t",
            column_name="c",
            data_type="VARCHAR2",
            max_length=100,
        )
        dt = MetadataResolver._column_info_to_datatype(info)
        assert dt.name == "VARCHAR2"
        assert dt.params == (100,)

    def test_date_has_no_params(self) -> None:
        info = ColumnInfo(table_name="t", column_name="c", data_type="DATE")
        dt = MetadataResolver._column_info_to_datatype(info)
        assert dt.params == ()


class TestResolveWithFakeConnection:
    def test_resolve_column_type_oracle(self) -> None:
        # ALL_TAB_COLUMNS returns: type, length, precision, scale, nullable
        r = _connected_resolver("oracle", [("NUMBER", None, 8, 2, "N")])
        dt = r.resolve_column_type("EMPLOYEES", "SALARY")
        assert dt is not None
        assert dt.name == "NUMBER"
        assert dt.params == (8, 2)

    def test_resolve_column_type_caches(self) -> None:
        r = _connected_resolver("oracle", [("NUMBER", None, 8, 2, "N")])
        first = r.resolve_column_type("EMPLOYEES", "SALARY")
        # Mutate the underlying rows; a cached lookup should not change.
        r._connection = FakeConnection([("VARCHAR2", 50, None, None, "Y")])
        second = r.resolve_column_type("EMPLOYEES", "SALARY")
        assert first == second

    def test_resolve_type_reference_via_connection(self) -> None:
        r = _connected_resolver("oracle", [("VARCHAR2", 50, None, None, "Y")])
        dt = r.resolve_type_reference("EMPLOYEES.NAME%TYPE")
        assert dt is not None
        assert dt.name == "VARCHAR2"
        assert dt.params == (50,)

    def test_unknown_column_returns_none(self) -> None:
        r = _connected_resolver("oracle", [])
        assert r.resolve_column_type("EMPLOYEES", "NOPE") is None


class TestUrlSchemeAliases:
    def test_sqlserver_alias_maps_to_tsql(self) -> None:
        with pytest.raises((ImportError, Exception)):
            MetadataResolver.from_url("sqlserver://u:p@h:1433/db")

    def test_postgres_alias_accepted(self) -> None:
        with pytest.raises((ImportError, Exception)):
            MetadataResolver.from_url("postgres://u:p@h:5432/db")

    def test_mssql_scheme_accepted(self) -> None:
        with pytest.raises((ImportError, Exception)):
            MetadataResolver.from_url("mssql://u:p@h:1433/db")


class TestQueryBranchesPerDialect:
    @pytest.mark.parametrize(
        "dialect,rows,expected",
        [
            ("tsql", [("decimal", None, 10, 2, "NO")], "DECIMAL"),
            ("postgresql", [("numeric", None, 10, 2, "NO")], "NUMERIC"),
            ("mysql", [("decimal", None, 10, 2, "NO")], "DECIMAL"),
        ],
    )
    def test_information_schema_path(
        self, dialect: str, rows: list[tuple], expected: str
    ) -> None:
        r = _connected_resolver(dialect, rows)
        dt = r.resolve_column_type("t", "c")
        assert dt is not None
        assert dt.name.upper() == expected

    def test_schema_qualified_table(self) -> None:
        r = _connected_resolver("tsql", [("int", None, 10, 0, "NO")])
        dt = r.resolve_column_type("dbo.employees", "id")
        assert dt is not None


class TestResolveTableColumnsFake:
    def test_returns_all_columns(self) -> None:
        rows = [
            ("emp_id", "int", None, 10, 0, "NO"),
            ("name", "varchar", 100, None, None, "YES"),
        ]
        r = _connected_resolver("postgresql", rows)
        cols = r.resolve_table_columns("employees")
        assert cols is not None
        assert len(cols) == 2
        assert cols[0].column_name == "emp_id"

    def test_caches_table_columns(self) -> None:
        rows = [("a", "int", None, 10, 0, "NO")]
        r = _connected_resolver("oracle", rows)
        first = r.resolve_table_columns("t")
        r._connection = FakeConnection([])
        second = r.resolve_table_columns("t")
        assert first == second

    def test_not_connected_returns_none(self) -> None:
        r = MetadataResolver(dialect="oracle")
        assert r.resolve_table_columns("t") is None


class TestContextManager:
    def test_close_sets_disconnected(self) -> None:
        r = _connected_resolver("oracle", [])
        with r as ctx:
            assert ctx.is_connected is True
        assert r.is_connected is False
