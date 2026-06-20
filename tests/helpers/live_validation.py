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

"""Validate transpiled SQL against a real database engine, syntax-only.

This is the test-side counterpart to the idea of checking output against the
target engine's *actual* grammar instead of our own assumptions. Each
validator parses/compiles the SQL without committing changes:

- **SQL Server**: ``SET NOEXEC ON`` makes the server parse and compile every
  statement but execute none — perfect for catching syntax/dialect errors
  (e.g. ``CREATE TABLE IF NOT EXISTS``) non-destructively.
- **PostgreSQL / MySQL**: run inside a transaction that is always rolled back.
- **Oracle**: not yet wired (no free official image); left as future work.

Validators are created from a connection URL and are skipped by the tests
when the URL/driver is unavailable, so the default suite stays green.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one SQL string against an engine."""

    ok: bool
    error: str | None = None


class SyntaxValidator:
    """Base class: subclasses implement :meth:`validate` for one engine."""

    dialect: str = ""

    def validate(self, sql: str) -> ValidationResult:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - overridden when needed
        pass


class MSSQLValidator(SyntaxValidator):
    """Validate T-SQL by executing inside a rolled-back transaction.

    Running the statements for real (then rolling back) resolves object names,
    so dependent DDL works -- e.g. ``CREATE TABLE`` followed by a
    ``CREATE INDEX`` on it in a later ``GO`` batch. Nothing is committed.
    ``GO`` is a client-side batch separator, so we split on it and run the
    batches in order on one connection/transaction.
    """

    dialect = "tsql"

    def __init__(self, url: str) -> None:
        import pyodbc  # noqa: F401 - imported for its availability

        self._conn = _connect_mssql(url)
        self._conn.autocommit = False

    def validate(self, sql: str) -> ValidationResult:
        cur = self._conn.cursor()
        try:
            for batch in _split_go(sql):
                if _is_executable(batch):
                    cur.execute(batch)
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001 - report engine complaint
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            with contextlib.suppress(Exception):
                self._conn.rollback()
            cur.close()

    def close(self) -> None:
        self._conn.close()


class PostgresValidator(SyntaxValidator):
    """Validate PostgreSQL by executing inside a rolled-back transaction."""

    dialect = "postgresql"

    def __init__(self, url: str) -> None:
        try:
            import psycopg  # psycopg 3

            self._conn = psycopg.connect(url, autocommit=False)
            self._driver = "psycopg"
        except ImportError:
            import psycopg2

            self._conn = psycopg2.connect(_normalize_pg_url(url))
            self._conn.autocommit = False
            self._driver = "psycopg2"

    def validate(self, sql: str) -> ValidationResult:
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            self._conn.rollback()
            cur.close()

    def close(self) -> None:
        self._conn.close()


class MySQLValidator(SyntaxValidator):
    """Validate MySQL by executing in a throwaway database.

    MySQL commits DDL implicitly, so a transaction rollback can't undo a
    CREATE TABLE. To validate dependent DDL (CREATE TABLE then CREATE INDEX on
    it) without leaking state, each ``validate`` call runs in a fresh,
    uniquely-named database that is dropped afterwards.
    """

    dialect = "mysql"

    def __init__(self, url: str) -> None:
        try:
            import pymysql

            self._conn = _connect_mysql(url, pymysql)
        except ImportError:
            import mysql.connector  # type: ignore[import-untyped]

            self._conn = _connect_mysql_connector(url, mysql.connector)
        self._conn.autocommit = True

    def validate(self, sql: str) -> ValidationResult:
        import uuid

        dbname = f"unique_val_{uuid.uuid4().hex[:12]}"
        cur = self._conn.cursor()
        try:
            cur.execute(f"CREATE DATABASE {dbname}")
            cur.execute(f"USE {dbname}")
            for stmt in _split_semicolons(sql):
                if _is_executable(stmt):
                    cur.execute(stmt)
                    with contextlib.suppress(Exception):
                        cur.fetchall()
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            with contextlib.suppress(Exception):
                cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
            cur.close()

    def close(self) -> None:
        self._conn.close()


def make_validator(dialect: str, url: str) -> SyntaxValidator:
    """Construct the validator for ``dialect`` from a connection URL."""
    if dialect == "tsql":
        return MSSQLValidator(url)
    if dialect == "postgresql":
        return PostgresValidator(url)
    if dialect == "mysql":
        return MySQLValidator(url)
    raise ValueError(f"No live validator for dialect {dialect!r}")


# --- helpers ---------------------------------------------------------------


def _split_go(sql: str) -> list[str]:
    """Split T-SQL on ``GO`` batch separators (line-only)."""
    import re

    return re.split(r"(?im)^\s*GO\s*$", sql)


def _is_executable(stmt: str) -> bool:
    """Whether a statement has real SQL (not blank/comment-only).

    A fragment that is only blank lines and ``--`` comments must not be sent
    to the engine, which would reject it as a syntax error.
    """
    for line in stmt.strip().splitlines():
        s = line.strip()
        if s and not s.startswith("--"):
            return True
    return False


def _split_semicolons(sql: str) -> list[str]:
    """Naive ';' split for simple validation statements (no PL bodies)."""
    return sql.split(";")


def _normalize_pg_url(url: str) -> str:
    # psycopg2 accepts the standard libpq URL form directly.
    return url


def _connect_mysql(url: str, pymysql: object):  # type: ignore[no-untyped-def]
    from urllib.parse import urlparse

    p = urlparse(url)
    return pymysql.connect(  # type: ignore[attr-defined]
        host=p.hostname or "localhost",
        port=p.port or 3306,
        user=p.username or "root",
        password=p.password or "",
        database=(p.path or "/").lstrip("/") or None,
        autocommit=False,
    )


def _connect_mysql_connector(url: str, connector):  # type: ignore[no-untyped-def]
    from urllib.parse import urlparse

    p = urlparse(url)
    return connector.connect(
        host=p.hostname or "localhost",
        port=p.port or 3306,
        user=p.username or "root",
        password=p.password or "",
        database=(p.path or "/").lstrip("/") or None,
        autocommit=False,
    )


def _connect_mssql(url: str):  # type: ignore[no-untyped-def]
    from urllib.parse import urlparse

    import pyodbc

    p = urlparse(url)
    driver = "{ODBC Driver 18 for SQL Server}"
    conn_str = (
        f"DRIVER={driver};"
        f"SERVER={p.hostname or 'localhost'},{p.port or 1433};"
        f"DATABASE={(p.path or '/').lstrip('/') or 'master'};"
        f"UID={p.username or 'sa'};PWD={p.password or ''};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=False)
