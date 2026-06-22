# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Database metadata resolver for type references.

Provides optional database connectivity to resolve metadata-dependent
constructs such as Oracle %TYPE and %ROWTYPE references, mapping them
to concrete data types from the actual database schema.

Supported connection URL formats:
  - SQL Server:  mssql://user:pass@host:port/database
  - Oracle:      oracle://user:pass@host:port/service
  - PostgreSQL:  postgresql://user:pass@host:port/database
  - MySQL:       mysql://user:pass@host:port/database
"""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from unique.core.ast_nodes import DataType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnInfo:
    """Information about a database column."""

    table_name: str
    column_name: str
    data_type: str
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    is_nullable: bool = True


@dataclass
class MetadataCache:
    """Cache for resolved metadata to avoid repeated queries."""

    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    tables: dict[str, list[ColumnInfo]] = field(default_factory=dict)


class MetadataResolver:
    """Resolves database metadata for type references.

    Connects to a source database to look up column types, enabling
    accurate resolution of Oracle %TYPE and %ROWTYPE references and
    other metadata-dependent constructs.

    Usage:
        resolver = MetadataResolver.from_url("oracle://user:pass@host/db")
        data_type = resolver.resolve_column_type("EMPLOYEES", "SALARY")
    """

    def __init__(self, dialect: str) -> None:
        self._dialect = dialect
        self._connection: Any = None
        self._cache = MetadataCache()
        self._connected = False

    @classmethod
    def from_url(cls, url: str) -> MetadataResolver:
        """Create a MetadataResolver from a connection URL.

        Args:
            url: Database connection URL.

        Returns:
            A configured MetadataResolver instance.

        Raises:
            ValueError: If the URL scheme is not supported.
            ImportError: If the required database driver is not installed.
        """
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

        dialect_map = {
            "mssql": "tsql",
            "sqlserver": "tsql",
            "oracle": "oracle",
            "postgresql": "postgresql",
            "postgres": "postgresql",
            "mysql": "mysql",
        }

        dialect = dialect_map.get(scheme)
        if not dialect:
            raise ValueError(
                f"Unsupported database scheme: {scheme}. "
                f"Supported: {', '.join(dialect_map.keys())}"
            )

        resolver = cls(dialect=dialect)
        resolver._connect(url, parsed)
        return resolver

    def _connect(self, url: str, parsed: Any) -> None:
        """Establish database connection based on dialect."""
        try:
            if self._dialect == "tsql":
                self._connect_tsql(parsed)
            elif self._dialect == "oracle":
                self._connect_oracle(parsed)
            elif self._dialect == "postgresql":
                self._connect_postgresql(parsed)
            elif self._dialect == "mysql":
                self._connect_mysql(parsed)
            self._connected = True
            logger.info("Connected to %s database", self._dialect)
        except ImportError as e:
            logger.warning("Database driver not installed: %s", e)
            raise
        except Exception as e:
            logger.warning("Failed to connect to database: %s", e)
            raise

    def _connect_tsql(self, parsed: Any) -> None:
        """Connect to SQL Server using pyodbc."""
        import pyodbc

        host = parsed.hostname or "localhost"
        port = parsed.port or 1433
        database = parsed.path.lstrip("/") if parsed.path else "master"
        user = parsed.username or ""
        password = parsed.password or ""

        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={host},{port};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password}"
        )
        self._connection = pyodbc.connect(conn_str)

    def _connect_oracle(self, parsed: Any) -> None:
        """Connect to Oracle using oracledb."""
        import oracledb

        host = parsed.hostname or "localhost"
        port = parsed.port or 1521
        service = parsed.path.lstrip("/") if parsed.path else "ORCL"
        user = parsed.username or ""
        password = parsed.password or ""

        dsn = oracledb.makedsn(host, port, service_name=service)
        self._connection = oracledb.connect(user=user, password=password, dsn=dsn)

    def _connect_postgresql(self, parsed: Any) -> None:
        """Connect to PostgreSQL using psycopg."""
        import psycopg

        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        database = parsed.path.lstrip("/") if parsed.path else "postgres"
        user = parsed.username or ""
        password = parsed.password or ""

        self._connection = psycopg.connect(
            host=host, port=port, dbname=database, user=user, password=password
        )

    def _connect_mysql(self, parsed: Any) -> None:
        """Connect to MySQL using mysql-connector-python."""
        import mysql.connector

        host = parsed.hostname or "localhost"
        port = parsed.port or 3306
        database = parsed.path.lstrip("/") if parsed.path else ""
        user = parsed.username or ""
        password = parsed.password or ""

        self._connection = mysql.connector.connect(
            host=host, port=port, database=database, user=user, password=password
        )

    @property
    def is_connected(self) -> bool:
        """Whether a database connection is active."""
        return self._connected

    def resolve_column_type(self, table: str, column: str) -> DataType | None:
        """Resolve a column reference to its concrete data type.

        This is used to resolve Oracle %TYPE references like
        `EMPLOYEES.SALARY%TYPE` → `NUMBER(8,2)`.

        Args:
            table: The table name (may include schema prefix).
            column: The column name.

        Returns:
            A DataType if resolved, None if the column is not found.
        """
        cache_key = f"{table}.{column}".upper()
        if cache_key in self._cache.columns:
            cached = self._cache.columns[cache_key]
            return self._column_info_to_datatype(cached)

        if not self._connected:
            logger.debug("No database connection for type resolution")
            return None

        info = self._query_column_type(table, column)
        if info:
            self._cache.columns[cache_key] = info
            return self._column_info_to_datatype(info)

        return None

    def resolve_table_columns(self, table: str) -> list[ColumnInfo] | None:
        """Resolve all columns of a table (for %ROWTYPE).

        Args:
            table: The table name (may include schema prefix).

        Returns:
            A list of ColumnInfo objects, or None if the table is not found.
        """
        cache_key = table.upper()
        if cache_key in self._cache.tables:
            return self._cache.tables[cache_key]

        if not self._connected:
            return None

        columns = self._query_table_columns(table)
        if columns:
            self._cache.tables[cache_key] = columns
        return columns

    def resolve_type_reference(self, type_ref: str) -> DataType | None:
        """Resolve a %TYPE or %ROWTYPE reference string.

        Args:
            type_ref: A string like "TABLE.COLUMN%TYPE" or "TABLE%ROWTYPE".

        Returns:
            A DataType if resolved, None otherwise.
        """
        match = re.match(r"^(.+?)\.(.+?)%TYPE$", type_ref, re.IGNORECASE)
        if match:
            table, column = match.group(1), match.group(2)
            return self.resolve_column_type(table, column)

        match = re.match(r"^(.+?)%ROWTYPE$", type_ref, re.IGNORECASE)
        if match:
            logger.debug("%%ROWTYPE reference cannot be resolved to a single type")
            return None

        return None

    def _query_column_type(self, table: str, column: str) -> ColumnInfo | None:
        """Query the database for a column's type information."""
        if not self._connection:
            return None

        try:
            cursor = self._connection.cursor()

            # Split schema.table if present
            parts = table.split(".")
            schema_name = parts[0] if len(parts) > 1 else None
            table_name = parts[-1]

            if self._dialect == "oracle":
                sql = """
                    SELECT DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE,
                           NULLABLE
                    FROM ALL_TAB_COLUMNS
                    WHERE UPPER(TABLE_NAME) = UPPER(:1)
                      AND UPPER(COLUMN_NAME) = UPPER(:2)
                """
                params: tuple[str, ...] = (table_name, column)
                if schema_name:
                    sql += " AND UPPER(OWNER) = UPPER(:3)"
                    params = (table_name, column, schema_name)
                cursor.execute(sql, params)

            elif self._dialect == "tsql":
                sql = """
                    SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE UPPER(TABLE_NAME) = UPPER(?)
                      AND UPPER(COLUMN_NAME) = UPPER(?)
                """
                params_list = [table_name, column]
                if schema_name:
                    sql += " AND UPPER(TABLE_SCHEMA) = UPPER(?)"
                    params_list.append(schema_name)
                cursor.execute(sql, params_list)

            elif self._dialect in ("postgresql", "mysql"):
                sql = """
                    SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE UPPER(TABLE_NAME) = UPPER(%s)
                      AND UPPER(COLUMN_NAME) = UPPER(%s)
                """
                params_pg = [table_name, column]
                if schema_name:
                    sql += " AND UPPER(TABLE_SCHEMA) = UPPER(%s)"
                    params_pg.append(schema_name)
                cursor.execute(sql, params_pg)

            row = cursor.fetchone()
            cursor.close()

            if row:
                return ColumnInfo(
                    table_name=table_name,
                    column_name=column,
                    data_type=str(row[0]),
                    max_length=row[1] if row[1] else None,
                    precision=row[2] if row[2] else None,
                    scale=row[3] if row[3] else None,
                    is_nullable=str(row[4]).upper() in ("Y", "YES", "TRUE", "1"),
                )

        except Exception as e:
            logger.warning("Failed to query column type: %s", e)

        return None

    def _query_table_columns(self, table: str) -> list[ColumnInfo] | None:
        """Query all columns for a table."""
        if not self._connection:
            return None

        try:
            cursor = self._connection.cursor()
            parts = table.split(".")
            table_name = parts[-1]

            if self._dialect == "oracle":
                sql = """
                    SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
                           DATA_PRECISION, DATA_SCALE, NULLABLE
                    FROM ALL_TAB_COLUMNS
                    WHERE UPPER(TABLE_NAME) = UPPER(:1)
                    ORDER BY COLUMN_ID
                """
                cursor.execute(sql, (table_name,))
            else:
                sql = """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE UPPER(TABLE_NAME) = UPPER(%s)
                    ORDER BY ORDINAL_POSITION
                """
                cursor.execute(sql, (table_name,))

            rows = cursor.fetchall()
            cursor.close()

            if rows:
                return [
                    ColumnInfo(
                        table_name=table_name,
                        column_name=str(row[0]),
                        data_type=str(row[1]),
                        max_length=row[2] if row[2] else None,
                        precision=row[3] if row[3] else None,
                        scale=row[4] if row[4] else None,
                        is_nullable=str(row[5]).upper() in ("Y", "YES", "TRUE", "1"),
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.warning("Failed to query table columns: %s", e)

        return None

    @staticmethod
    def _column_info_to_datatype(info: ColumnInfo) -> DataType:
        """Convert a ColumnInfo to a DataType node."""
        params: list[int] = []
        name = info.data_type.upper()

        if info.precision is not None:
            params.append(info.precision)
            if info.scale is not None and info.scale > 0:
                params.append(info.scale)
        elif info.max_length is not None and info.max_length > 0:
            if name in (
                "VARCHAR",
                "VARCHAR2",
                "NVARCHAR",
                "NVARCHAR2",
                "CHAR",
                "NCHAR",
                "RAW",
                "VARBINARY",
            ):
                params.append(info.max_length)

        return DataType(name=name, params=tuple(params))

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            with contextlib.suppress(Exception):
                self._connection.close()
            self._connected = False

    def __enter__(self) -> MetadataResolver:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
