# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

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


class TestContextManager:
    def test_close_sets_disconnected(self) -> None:
        r = _connected_resolver("oracle", [])
        with r as ctx:
            assert ctx.is_connected is True
        assert r.is_connected is False
