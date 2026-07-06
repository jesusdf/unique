# Copyright (c) 2026 Jesús Diéguez Fernández
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
        # _connect_mssql connects with autocommit disabled under either driver.
        self._conn = _connect_mssql(url)

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
        # In the non-isolated path we must undo every object the script
        # creates (tables *and* routines/triggers/views), or a leftover
        # procedure makes the next run fail with "already exists" (1304). DDL
        # auto-commits, so a rollback can't help.
        created: list[tuple[str, str]] = []
        try:
            for stmt in _split_mysql_statements(sql):
                if not _is_executable(stmt):
                    continue
                if not isolated:
                    obj = _mysql_created_object(stmt)
                    if obj is not None:
                        created.append(obj)
                cur.execute(stmt)
                # Fully drain every result set the statement produced, otherwise
                # the next execute() raises "Commands out of sync" (2014). A
                # statement can yield multiple result sets; consume them all.
                self._drain(cur)
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            if isolated:
                with contextlib.suppress(Exception):
                    cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
            else:
                # FK checks off so parent/child drop order doesn't matter.
                with contextlib.suppress(Exception):
                    cur.execute("SET FOREIGN_KEY_CHECKS=0")
                for kind, name in reversed(created):
                    with contextlib.suppress(Exception):
                        cur.execute(f"DROP {kind} IF EXISTS `{name}`")
                with contextlib.suppress(Exception):
                    cur.execute("SET FOREIGN_KEY_CHECKS=1")
            cur.close()

    @staticmethod
    def _drain(cur: object) -> None:
        """Consume every pending result set on a cursor.

        Both pymysql and mysql-connector raise "Commands out of sync" (2014) on
        the next execute() if a statement's result sets are left unread. Read
        the current set, then walk ``nextset()`` until there are none left.
        """
        with contextlib.suppress(Exception):
            cur.fetchall()  # type: ignore[attr-defined]
        nextset = getattr(cur, "nextset", None)
        if nextset is None:
            return
        while True:
            try:
                has_more = nextset()
            except Exception:
                break
            if not has_more:
                break
            with contextlib.suppress(Exception):
                cur.fetchall()  # type: ignore[attr-defined]

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
        # Oracle's driver rejects a trailing '/' terminator and only runs one
        # statement per execute(). PL/SQL blocks contain ';' inside their body,
        # so we split on the SQL*Plus '/' terminator (a line of just '/') rather
        # than on every ';'.
        statements = [s for s in _split_oracle_statements(sql) if _is_executable(s)]
        created = _objects_created(sql)
        compilable = _oracle_compilable_objects(sql)
        self._drop_all(created + compilable)  # pre-clean any leftovers
        cur = self._conn.cursor()
        try:
            for stmt in statements:
                cur.execute(stmt.strip())
            # Oracle compiles PL/SQL objects *lazily*: CREATE succeeds even when
            # the body is invalid (the object is left INVALID), so executing the
            # DDL without error is not proof the routine is valid. Query the
            # compile errors so a broken procedure/function/trigger/package is
            # reported instead of silently passing.
            compile_error = self._first_compile_error(compilable)
            if compile_error is not None:
                return ValidationResult(
                    ok=False, error=f"{compile_error}\n--- sql ---\n{sql}"
                )
            return ValidationResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return ValidationResult(ok=False, error=f"{e}\n--- sql ---\n{sql}")
        finally:
            cur.close()
            self._drop_all(created + compilable)

    def _first_compile_error(self, compilable: list[tuple[str, str]]) -> str | None:
        """Return the first PL/SQL compile error on a created object, or None."""
        if not compilable:
            return None
        cur = self._conn.cursor()
        try:
            for _kind, name in compilable:
                cur.execute(
                    "SELECT type, line, text FROM user_errors "
                    "WHERE name = :n ORDER BY sequence",
                    {"n": name},
                )
                row = cur.fetchone()
                if row is not None:
                    etype, line, text = row
                    return (
                        f"{etype} {name} compiled INVALID "
                        f"(line {line}): {text.strip()}"
                    )
            return None
        finally:
            cur.close()

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

    def _flush_default(chunk: str) -> None:
        # A default-delimiter section holds several statements separated by
        # ';'. Split them (line comments stripped so a ';' in a comment does
        # not split) and keep each non-empty piece as its own statement, since
        # the driver executes one statement per call.
        for part in _strip_line_comments(chunk).split(";"):
            if part.strip():
                statements.append(part)

    for raw_line in sql.splitlines():
        stripped = raw_line.strip()
        # A "DELIMITER X" line switches the active terminator.
        if stripped.upper().startswith("DELIMITER "):
            # Flush anything pending under the previous delimiter. Under the
            # default ';' delimiter that pending text is many statements, so it
            # must be split; a custom-delimiter block is a single statement.
            pending = "\n".join(buf)
            if current_delim == ";":
                _flush_default(pending)
            elif pending.strip():
                statements.append(pending.strip())
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
        _flush_default(tail)
    elif tail.strip():
        statements.append(tail.strip())
    return statements


_MYSQL_CREATE_RE = re.compile(
    r"(?is)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:DEFINER\s*=\s*\S+\s+)?"
    r"(?:TEMPORARY\s+)?(TABLE|PROCEDURE|FUNCTION|TRIGGER|VIEW|EVENT)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([A-Za-z0-9_]+)"
)


def _mysql_created_object(stmt: str) -> tuple[str, str] | None:
    """Return ``(kind, name)`` for the object a MySQL statement creates.

    Used to undo objects in the non-isolated validation path. ``kind`` is the
    keyword accepted by ``DROP`` (``TABLE``/``PROCEDURE``/``FUNCTION``/
    ``TRIGGER``/``VIEW``/``EVENT``).
    """
    m = _MYSQL_CREATE_RE.search(stmt)
    if not m:
        return None
    return m.group(1).upper(), m.group(2)


def _drop_leading_comment_lines(text: str) -> str:
    """Drop leading blank and ``--`` comment lines from a chunk.

    Used so a PL/SQL block preceded by degraded guard comments is still
    recognized by its ``CREATE PROCEDURE`` / ``BEGIN`` head.
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (
        not lines[i].strip() or lines[i].lstrip().startswith("--")
    ):
        i += 1
    return "\n".join(lines[i:])


_PLSQL_HEAD_RE = re.compile(
    r"(?is)^\s*(?:CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE|TYPE)\b|DECLARE\b|BEGIN\b)"
)


def _split_oracle_statements(sql: str) -> list[str]:
    """Split an Oracle script into statements, honoring the '/' terminator.

    SQL*Plus terminates each statement with a line containing only ``/``. That
    is the only reliable boundary for PL/SQL blocks (``CREATE PROCEDURE`` /
    ``TRIGGER`` / anonymous ``BEGIN … END;``), whose bodies contain ``;``.
    python-oracledb executes one statement per call and wants:

    - no trailing ``/`` (it is not SQL), so the terminator lines are dropped;
    - no trailing ``;`` on a plain SQL statement (ORA-00911), so it is stripped;
    - the trailing ``;`` **kept** on a PL/SQL block (it closes ``END;``).

    A chunk between terminators may still hold several ``;``-separated plain
    statements (e.g. leading ``CREATE TABLE``s), so non-PL/SQL chunks are split
    on ``;`` too.
    """
    chunks = re.split(r"(?m)^[ \t]*/[ \t]*$", sql)
    statements: list[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        # A CREATE PROCEDURE/TRIGGER is often preceded by degraded ``--`` guard
        # comments (e.g. the ``IF OBJECT_ID`` existence check). Skip leading
        # blank/comment lines before deciding whether the chunk is PL/SQL.
        body = _drop_leading_comment_lines(chunk)
        if _PLSQL_HEAD_RE.match(body):
            # A PL/SQL block: one statement, keep its terminating ';'.
            statements.append(body.strip())
        else:
            # Plain SQL: may be several ';'-separated statements; strip the
            # terminator ';' from each (comments stripped so a ';' inside one
            # does not split).
            for part in _strip_line_comments(chunk).split(";"):
                if part.strip():
                    statements.append(part.strip())
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
    """Connect to SQL Server, preferring pymssql (root-free, its wheel bundles
    FreeTDS) and falling back to pyodbc + the MS ODBC driver."""
    from urllib.parse import urlparse

    p = urlparse(url)
    host = p.hostname or "localhost"
    port = int(p.port or 1433)
    db = (p.path or "/").lstrip("/") or "master"
    user = p.username or "sa"
    pwd = p.password or ""
    try:
        import pymssql

        return pymssql.connect(
            server=host, port=port, user=user, password=pwd, database=db
        )
    except ImportError:
        import pyodbc

        conn_str = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={host},{port};DATABASE={db};"
            f"UID={user};PWD={pwd};TrustServerCertificate=yes;"
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

    # Keep any surrounding quote (``"order"``/``[order]``/`` `order` ``) so the
    # DROP re-quotes a reserved-word name (``DROP TABLE "order"``, not the
    # invalid bare ``DROP TABLE order``).
    _name = r"([`\"\[]?[A-Za-z_]\w*[`\"\]]?)"
    tables = re.findall(
        r"(?i)\bCREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?" + _name,
        sql,
    )
    indexes = re.findall(r"(?i)\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+" + _name, sql)
    out: list[tuple[str, str]] = [("INDEX", n) for n in indexes]
    out += [("TABLE", n) for n in tables]
    return out


def _oracle_compilable_objects(sql: str) -> list[tuple[str, str]]:
    """CREATE'd PL/SQL objects (procedure/function/trigger/package) a snippet
    defines. Used to query USER_ERRORS (Oracle compiles them lazily) and to
    drop them afterwards. Names are upper-cased and unquoted to match the data
    dictionary's storage of unquoted identifiers.
    """
    import re

    out: list[tuple[str, str]] = []
    for kind, name in re.findall(
        r"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
        r"(PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b(?:\s+BODY)?\s+"
        r'(?:"?\w+"?\s*\.\s*)?"?(\w+)"?',
        sql,
    ):
        out.append((kind.upper(), name.upper()))
    return out
