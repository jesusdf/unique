# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

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
import re
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
        # Prefer an isolated throwaway database so DDL can't leak between
        # validations. That needs the global CREATE privilege; if the connected
        # user lacks it (e.g. a least-privilege user scoped to one schema), fall
        # back to validating in the current database and dropping any tables the
        # snippet creates, mirroring the Oracle validator's cleanup approach.
        isolated = False
        try:
            cur.execute(f"CREATE DATABASE {dbname}")
            cur.execute(f"USE {dbname}")
            isolated = True
        except Exception:
            isolated = False
        created_tables: list[str] = []
        try:
            for stmt in _split_mysql_statements(sql):
                if not _is_executable(stmt):
                    continue
                if not isolated:
                    m = re.search(
                        r"(?is)\bCREATE\s+(?:TEMPORARY\s+)?TABLE\s+"
                        r"(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([A-Za-z0-9_]+)",
                        stmt,
                    )
                    if m:
                        created_tables.append(m.group(1))
                cur.execute(stmt)
                with contextlib.suppress(Exception):
                    cur.fetchall()
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            if isolated:
                with contextlib.suppress(Exception):
                    cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
            else:
                for tbl in reversed(created_tables):
                    with contextlib.suppress(Exception):
                        cur.execute(f"DROP TABLE IF EXISTS {tbl}")
            cur.close()

    def close(self) -> None:
        self._conn.close()


class OracleValidator(SyntaxValidator):
    """Validate Oracle by executing statements and dropping what they create.

    Oracle commits DDL implicitly, so a transaction rollback can't undo a
    CREATE TABLE. The validation snippets create objects with fixed names, so
    we drop any table/index they create both before (idempotent) and after the
    run to keep the schema clean and the validation repeatable.
    """

    dialect = "oracle"

    def __init__(self, url: str) -> None:
        import oracledb  # type: ignore[import-untyped]

        user, password, dsn = _parse_oracle_url(url)
        self._conn = oracledb.connect(user=user, password=password, dsn=dsn)
        self._conn.autocommit = False

    def validate(self, sql: str) -> ValidationResult:
        # Oracle's driver rejects a trailing ';' / '/' terminator on a single
        # statement, and only runs one statement per execute().
        statements = [s for s in _split_semicolons(sql) if _is_executable(s)]
        created = _objects_created(sql)
        self._drop_all(created)  # pre-clean in case a prior run left objects
        cur = self._conn.cursor()
        try:
            for stmt in statements:
                cur.execute(stmt.strip())
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            cur.close()
            self._drop_all(created)

    def _drop_all(self, created: list[tuple[str, str]]) -> None:
        cur = self._conn.cursor()
        for kind, name in created:
            with contextlib.suppress(Exception):
                cur.execute(f"DROP {kind} {name}")
                self._conn.commit()
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
    if dialect == "oracle":
        return OracleValidator(url)
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


def _strip_line_comments(sql: str) -> str:
    """Remove ``-- ...`` line comments (to end of line) from each line.

    This prevents a ``;`` inside a comment from being treated as a statement
    separator, and keeps comment text from reaching the engine.
    """
    out = []
    for line in sql.splitlines():
        idx = line.find("--")
        out.append(line if idx == -1 else line[:idx])
    return "\n".join(out)


def _split_semicolons(sql: str) -> list[str]:
    """Split on ';' for simple validation statements (no PL bodies).

    Line comments are stripped first so a ';' inside a comment doesn't split a
    statement.
    """
    return _strip_line_comments(sql).split(";")


def _split_mysql_statements(sql: str) -> list[str]:
    """Split a MySQL script into executable statements, honoring DELIMITER.

    A compound routine is wrapped as ``DELIMITER $$ <body>$$ DELIMITER ;`` so a
    ``;`` inside the body doesn't terminate it. A driver (PyMySQL / mysql-
    connector) executes one statement per call and does not understand the
    client-side ``DELIMITER`` command, so we parse the blocks ourselves:

    - Inside a ``DELIMITER $$`` block, the whole body up to the ``$$`` custom
      delimiter is one statement (the ``DELIMITER`` lines and trailing ``$$``
      are removed before execution).
    - Outside a block, statements are split on ``;``.
    """
    statements: list[str] = []
    current_delim = ";"
    buf: list[str] = []
    for raw_line in sql.splitlines():
        stripped = raw_line.strip()
        # A "DELIMITER X" line switches the active terminator.
        if stripped.upper().startswith("DELIMITER "):
            # Flush anything pending under the previous delimiter.
            pending = "\n".join(buf).strip()
            if pending:
                statements.append(pending)
            buf = []
            current_delim = stripped.split(None, 1)[1].strip()
            continue
        buf.append(raw_line)
        # When the active delimiter is custom ($$), a line ending with it
        # closes the current statement.
        if current_delim != ";" and stripped.endswith(current_delim):
            joined = "\n".join(buf)
            # Drop the trailing custom delimiter.
            joined = joined.rstrip()[: -len(current_delim)]
            if joined.strip():
                statements.append(joined.strip())
            buf = []
    # Remaining buffer: split on ';' (default delimiter section).
    tail = "\n".join(buf)
    if current_delim == ";":
        for part in _strip_line_comments(tail).split(";"):
            if part.strip():
                statements.append(part)
    elif tail.strip():
        statements.append(tail.strip())
    return statements


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


def _parse_oracle_url(url: str) -> tuple[str, str, str]:
    """Parse ``oracle://user:pass@host:port/service`` into (user, pwd, dsn).

    The DSN is the Easy Connect form ``host:port/service_name`` that
    python-oracledb accepts in thin mode (no Oracle client needed).
    """
    from urllib.parse import urlparse

    p = urlparse(url)
    host = p.hostname or "localhost"
    port = p.port or 1521
    service = (p.path or "/").lstrip("/") or "FREEPDB1"
    dsn = f"{host}:{port}/{service}"
    return p.username or "system", p.password or "", dsn


def _objects_created(sql: str) -> list[tuple[str, str]]:
    """Find tables/indexes a snippet creates, so they can be dropped after.

    Returns (kind, name) pairs, indexes first so dependent drops don't fail.
    """
    import re

    tables = re.findall(
        r"(?i)\bCREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)",
        sql,
    )
    indexes = re.findall(r"(?i)\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+([A-Za-z_]\w*)", sql)
    out: list[tuple[str, str]] = [("INDEX", n) for n in indexes]
    out += [("TABLE", n) for n in tables]
    return out
