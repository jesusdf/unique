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

# Tables read back, in FK-safe order (not required for reads, but stable).
TABLES = ("customer", "product", "invoice", "invoice_line", "payment")


def split_statements(sql: str, dialect: str) -> list[str]:
    """Split a transpiled script into individually executable statements.

    - T-SQL: batches separated by a line containing only ``GO``.
    - Oracle: PL/SQL blocks terminated by a line containing only ``/``; plain
      statements terminated by ``;``.
    - PostgreSQL / MySQL: statements terminated by ``;`` at the top level, but a
      dollar-quoted (``$$ … $$``) or ``BEGIN … END`` routine body may contain
      inner ``;`` — those are kept together.

    The goal is robustness for the canonical scenario, not a full SQL splitter.
    """
    if dialect == "tsql":
        parts = re.split(r"(?im)^\s*GO\s*$", sql)
        return [p.strip() for p in parts if p.strip()]

    if dialect == "oracle":
        return _split_oracle(sql)

    if dialect == "mysql":
        return _split_mysql(sql)

    return _split_semicolons(sql, dollar_quote=(dialect == "postgresql"))


def _split_mysql(sql: str) -> list[str]:
    """Split a MySQL script, honoring ``DELIMITER`` directives.

    Routine bodies are wrapped in ``DELIMITER // … END // … DELIMITER ;`` so the
    inner ``;`` don't split them. We segment the script by the active delimiter,
    dropping the directives, and fall back to ``;``/BEGIN…END splitting for the
    plain regions.
    """
    statements: list[str] = []
    delimiter = ";"
    buf: list[str] = []

    def flush_plain(text: str) -> None:
        statements.extend(_split_semicolons(text, dollar_quote=False))

    for raw_line in sql.splitlines():
        directive = re.match(r"(?i)^\s*DELIMITER\s+(\S+)\s*$", raw_line)
        if directive:
            # Flush whatever accumulated under the previous delimiter.
            chunk = "\n".join(buf)
            buf = []
            if delimiter == ";":
                flush_plain(chunk)
            else:
                statements.extend(_split_on_token(chunk, delimiter))
            delimiter = directive.group(1)
            continue
        buf.append(raw_line)

    chunk = "\n".join(buf)
    if delimiter == ";":
        flush_plain(chunk)
    else:
        statements.extend(_split_on_token(chunk, delimiter))
    return [s for s in statements if s.strip()]


def _split_on_token(text: str, token: str) -> list[str]:
    """Split ``text`` on a literal delimiter token (e.g. ``//``), trimming it."""
    parts = text.split(token)
    return [p.strip() for p in parts if p.strip()]


def _split_oracle(sql: str) -> list[str]:
    """Split Oracle script on ``/`` block terminators and top-level ``;``."""
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip() == "/":
            block = "\n".join(buf).strip()
            if block:
                statements.append(block)
            buf = []
            continue
        buf.append(line)
    tail = "\n".join(buf).strip()
    if tail:
        # Any remaining plain statements are ;-separated.
        statements.extend(_split_semicolons(tail, dollar_quote=False))
    return [s for s in statements if s.strip()]


def _split_semicolons(sql: str, *, dollar_quote: bool) -> list[str]:
    """Split on top-level ``;``, keeping $$-quoted / BEGIN…END bodies intact."""
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False
    in_string = False
    depth_begin = 0
    i = 0
    text = sql
    while i < len(text):
        ch = text[i]
        two = text[i : i + 2]
        # Skip comments outside of strings/dollar-quotes so an apostrophe or the
        # word BEGIN/END inside a comment can't desync the splitter.
        if not in_dollar and not in_string:
            if two == "--":
                nl = text.find("\n", i)
                end = len(text) if nl == -1 else nl
                buf.append(text[i:end])
                i = end
                continue
            if two == "/*":
                close = text.find("*/", i + 2)
                end = len(text) if close == -1 else close + 2
                buf.append(text[i:end])
                i = end
                continue
        if dollar_quote and two == "$$":
            in_dollar = not in_dollar
            buf.append(two)
            i += 2
            continue
        if ch == "'" and not in_dollar:
            in_string = not in_string
        if not in_dollar and not in_string:
            # Track BEGIN/END nesting (MySQL routine bodies have no $$).
            word = re.match(r"(?i)\b(BEGIN|END)\b", text[i:])
            if word:
                kw = word.group(1).upper()
                if kw == "BEGIN":
                    depth_begin += 1
                elif kw == "END" and depth_begin > 0:
                    depth_begin -= 1
        if ch == ";" and not in_dollar and not in_string and depth_begin == 0:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


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
        import pymysql

        return _connect_mysql(url, pymysql)
    if dialect == "oracle":
        import oracledb

        return _connect_oracle(url, oracledb)
    if dialect == "tsql":
        import pyodbc

        return pyodbc.connect(url)
    raise ValueError(f"unknown dialect: {dialect}")


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


def _connect_oracle(url: str, oracledb: Any) -> Any:
    # oracle://user:pass@host:port/service
    m = re.match(r"oracle(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable Oracle URL: {url}")
    user, pwd, host, port, service = m.groups()
    dsn = oracledb.makedsn(host, int(port or 1521), service_name=service)
    return oracledb.connect(user=user, password=pwd, dsn=dsn)
