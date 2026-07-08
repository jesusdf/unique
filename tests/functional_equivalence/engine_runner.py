# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Run a transpiled scenario against a live engine and read its final state.

This is the *driver* layer of the functional-equivalence harness: it executes
the transpiled schema + scenario on a real database and reads each table back as
column->value dicts for ``state_check`` to compare against ``expected_state.yaml``.

It is deliberately thin and engine-specific only where it must be:

- statement splitting: the transpiler emits T-SQL ``GO`` batch separators for
  the T-SQL target and ``;``-terminated statements (with PL/SQL ``/`` block
  terminators for Oracle) for the others. ``split_statements`` handles both.
- connection + cursor: created from a URL via the driver chosen per dialect,
  mirroring ``tests/helpers/live_validation.py``.

No driver is imported at module load, so importing this file never fails for a
missing driver; the connect call raises and the test skips.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tests.helpers.sql_split import split_statements

__all__ = ["TABLES", "EngineRunner", "connect", "split_statements"]

# Tables read back, in FK-safe order (not required for reads, but stable).
TABLES = ("customer", "product", "invoice", "invoice_line", "payment", "app_flag")


@dataclass
class EngineRunner:
    """Executes statements and reads tables on one live connection.

    ``connection`` is any DB-API 2.0 connection. ``placeholder`` and quoting are
    not needed: the harness runs the transpiler's own output and reads with
    simple ``SELECT * FROM <table> ORDER BY id``.
    """

    connection: Any
    dialect: str

    def execute_script(self, sql: str) -> None:
        for stmt in split_statements(sql, self.dialect):
            cur = self.connection.cursor()
            try:
                cur.execute(stmt)
            finally:
                cur.close()
        self.connection.commit()

    def read_table(self, name: str) -> list[dict[str, Any]]:
        cur = self.connection.cursor()
        try:
            cur.execute(f"SELECT * FROM {name} ORDER BY id")
            columns = [d[0].lower() for d in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]
        finally:
            cur.close()

    def drop_all_objects(self) -> None:
        """Best-effort teardown of every user view, function and procedure in the
        schema (tables are dropped separately by the caller). The FE fixtures are
        re-runnable via their own DROP guards, but a source whose guard degrades
        to a comment (Oracle's catalog-driven DROP block) would otherwise leave
        functions/views behind and fail the next same-target pair with an
        "already exists" error. Querying the catalog keeps this engine-agnostic
        and robust to overloaded routines."""
        for stmt in self._object_drop_statements():
            cur = self.connection.cursor()
            try:
                cur.execute(stmt)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
            finally:
                cur.close()

    def _object_drop_statements(self) -> list[str]:
        """Catalog-driven DROP statements for views + routines, per engine."""

        def query(sql: str) -> list[tuple[Any, ...]]:
            cur = self.connection.cursor()
            try:
                cur.execute(sql)
                return list(cur.fetchall())
            except Exception:
                self.connection.rollback()
                return []
            finally:
                cur.close()

        if self.dialect == "postgresql":
            views = [
                f"DROP VIEW IF EXISTS {v} CASCADE"
                for (v,) in query(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema = 'public'"
                )
            ]
            # regprocedure renders the full signature, so overloaded routines
            # each drop cleanly (a bare name would be "not unique").
            routines = [
                f"DROP {'PROCEDURE' if kind == 'p' else 'FUNCTION'} "
                f"IF EXISTS {sig} CASCADE"
                for sig, kind in query(
                    "SELECT p.oid::regprocedure::text, p.prokind FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public'"
                )
            ]
            return views + routines
        if self.dialect == "mysql":
            views = [
                f"DROP VIEW IF EXISTS {v}"
                for (v,) in query(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema = DATABASE()"
                )
            ]
            routines = [
                f"DROP {rtype} IF EXISTS {name}"
                for name, rtype in query(
                    "SELECT routine_name, routine_type FROM "
                    "information_schema.routines WHERE routine_schema = DATABASE()"
                )
            ]
            return views + routines
        if self.dialect == "oracle":
            return [
                f"DROP {otype} {name}"
                for name, otype in query(
                    "SELECT object_name, object_type FROM user_objects "
                    "WHERE object_type IN ('VIEW', 'FUNCTION', 'PROCEDURE', "
                    "'PACKAGE', 'TRIGGER')"
                )
            ]
        if self.dialect == "tsql":
            drops: list[str] = []
            for name, xtype in query(
                "SELECT name, type FROM sys.objects "
                "WHERE type IN ('V', 'P', 'FN', 'IF', 'TF')"
            ):
                kind = (
                    "VIEW"
                    if xtype.strip() == "V"
                    else ("PROCEDURE" if xtype.strip() == "P" else "FUNCTION")
                )
                drops.append(f"DROP {kind} IF EXISTS {name}")
            return drops
        return []


def connect(dialect: str, url: str) -> Any:
    """Open a DB-API connection for ``dialect`` from a URL.

    Drivers are imported lazily so a missing driver raises ImportError (the
    caller skips). Mirrors the driver choices in
    ``tests/helpers/live_validation.py``.
    """
    if dialect == "postgresql":
        try:
            import psycopg  # psycopg 3

            return psycopg.connect(url)
        except ImportError:
            import psycopg2

            return psycopg2.connect(_pg_url_for_psycopg2(url))
    if dialect == "mysql":
        try:
            import pymysql

            return _connect_mysql(url, pymysql)
        except ImportError:
            import mysql.connector  # type: ignore[import-untyped]

            return _connect_mysql_connector(url, mysql.connector)
    if dialect == "oracle":
        import oracledb

        return _connect_oracle(url, oracledb)
    if dialect == "tsql":
        return _connect_tsql(url)
    raise ValueError(f"unknown dialect: {dialect}")


def _connect_tsql(url: str) -> Any:
    """Connect to SQL Server. A full ODBC connection string (``DRIVER={…};…``)
    uses pyodbc directly; a ``mssql://user:pass@host:port/db`` URL prefers pymssql
    (its wheel bundles FreeTDS, no system driver) and falls back to pyodbc + the
    MS ODBC driver — so the harness runs under either driver set (local or CI)."""
    if "://" not in url:
        import pyodbc

        return pyodbc.connect(url)
    m = re.match(
        r"(?:mssql|tsql|sqlserver)(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)",
        url,
    )
    if not m:
        raise ValueError(f"unparseable SQL Server URL: {url}")
    user, pwd, host, port, db = m.groups()
    try:
        import pymssql
    except ImportError:
        import pyodbc

        conn_str = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={host},{port or 1433};DATABASE={db};"
            f"UID={user};PWD={pwd};TrustServerCertificate=yes;"
        )
        return pyodbc.connect(conn_str)
    return pymssql.connect(
        server=host, port=int(port or 1433), user=user, password=pwd, database=db
    )


def _pg_url_for_psycopg2(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _connect_mysql(url: str, pymysql: Any) -> Any:
    # mysql://user:pass@host:port/db
    m = re.match(r"mysql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable MySQL URL: {url}")
    user, pwd, host, port, db = m.groups()
    return pymysql.connect(
        user=user,
        password=pwd,
        host=host,
        port=int(port or 3306),
        database=db,
    )


def _connect_mysql_connector(url: str, connector: Any) -> Any:
    # Fallback driver (CI installs mysql-connector-python, not pymysql).
    m = re.match(r"mysql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable MySQL URL: {url}")
    user, pwd, host, port, db = m.groups()
    return connector.connect(
        user=user,
        password=pwd,
        host=host,
        port=int(port or 3306),
        database=db,
        autocommit=False,
    )


def _connect_oracle(url: str, oracledb: Any) -> Any:
    # oracle://user:pass@host:port/service
    m = re.match(r"oracle(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable Oracle URL: {url}")
    user, pwd, host, port, service = m.groups()
    dsn = oracledb.makedsn(host, int(port or 1521), service_name=service)
    return oracledb.connect(user=user, password=pwd, dsn=dsn)
