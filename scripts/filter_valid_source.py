#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Keep only the statements the SOURCE engine itself accepts.

The PostgreSQL regression suite deliberately includes invalid SQL (it tests
the server's error paths), which would count against the transpiler in a
validity sweep. This filter executes each statement of FILE against the live
source engine (PostgreSQL, savepoint-per-statement against an empty database
— missing objects are fine, syntax-class rejections are not) and writes only
the accepted statements, giving the sweep an honest denominator.

Usage:
    UNIQUE_TEST_PG_URL=postgresql://… scripts/filter_valid_source.py \
        fixtures-corpus/pg_corpus_all.sql -o fixtures-corpus/pg_corpus_valid.sql
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.helpers.sql_split import is_executable, split_statements  # noqa: E402

#: SQLSTATEs that mean the statement itself is malformed / uses an unknown
#: feature — the same syntax-class set the validity sweep uses for PG.
_SYNTAX_STATES = frozenset({"42601", "42P02", "42809", "0A000", "42P18", "42804"})


def filter_pg(sql: str, url: str) -> tuple[list[str], int]:
    """Return (kept statements, rejected count) per live PostgreSQL."""
    import re

    import psycopg

    dsn = url.replace("postgresql://", "postgres://")

    def connect():  # noqa: ANN202
        conn = psycopg.connect(dsn)
        conn.autocommit = False
        return conn, conn.cursor()

    conn, cur = connect()
    kept: list[str] = []
    rejected = 0
    try:
        for stmt in split_statements(sql, "postgresql"):
            if not is_executable(stmt):
                kept.append(stmt)
                continue
            # COPY is client protocol (copy-in/out mode), not portable SQL
            # material — executing it wedges the connection.
            if re.match(r"(?is)\s*COPY\b", stmt):
                rejected += 1
                continue
            try:
                cur.execute("SAVEPOINT s1")
                cur.execute(stmt.encode())
                kept.append(stmt)
                cur.execute("ROLLBACK TO SAVEPOINT s1")
            except psycopg.OperationalError:
                # A statement wedged the session: reconnect and drop it.
                rejected += 1
                with contextlib.suppress(Exception):
                    conn.close()
                conn, cur = connect()
            except psycopg.Error as e:
                state = e.sqlstate or ""
                # Missing objects/columns on the empty DB are expected and
                # say nothing about the statement's validity.
                if state in _SYNTAX_STATES:
                    rejected += 1
                else:
                    kept.append(stmt)
                with contextlib.suppress(psycopg.Error):
                    cur.execute("ROLLBACK TO SAVEPOINT s1")
        conn.rollback()
    finally:
        with contextlib.suppress(Exception):
            conn.close()
    return kept, rejected


def _mysql_units(sql: str) -> list[str]:
    """Split a mysql-source script into executable units.

    ``DELIMITER X … X … DELIMITER ;`` blocks (stored-routine bodies in
    standard client format) are ONE unit each; the rest splits on the
    shared statement splitter."""
    units: list[str] = []
    plain: list[str] = []
    lines = sql.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"(?i)^\s*DELIMITER\s+(\S+)\s*$", lines[i])
        if m and m.group(1) != ";":
            if plain:
                units.extend(split_statements("\n".join(plain), "mysql"))
                plain = []
            delim = m.group(1)
            body: list[str] = []
            i += 1
            while i < len(lines) and not re.match(
                r"(?i)^\s*DELIMITER\s+;\s*$", lines[i]
            ):
                body.append(lines[i])
                i += 1
            unit = "\n".join(body).strip()
            if unit.endswith(delim):
                unit = unit[: -len(delim)].rstrip()
            if unit:
                units.append(unit)
            i += 1
            continue
        plain.append(lines[i])
        i += 1
    if plain:
        units.extend(split_statements("\n".join(plain), "mysql"))
    return units


def filter_mysql(sql: str, url: str) -> tuple[list[str], int]:
    """Return (kept statements, rejected count) per live MySQL.

    MySQL auto-commits DDL, so statements run in a throwaway database
    that is dropped afterwards. Only parse-class rejections (1064)
    disqualify a statement; missing objects on the empty database are
    expected and say nothing about validity."""
    import pymysql

    m = re.match(r"mysql://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)", url)
    if not m:
        raise SystemExit(f"unparseable mysql url: {url}")
    user, password, host, port, _db = m.groups()
    dbname = "unique_filter_tmp"

    def connect():  # noqa: ANN202
        conn = pymysql.connect(host=host, port=int(port), user=user, password=password)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {dbname}")
        cur.execute(f"USE {dbname}")
        return conn, cur

    conn, cur = connect()
    kept: list[str] = []
    rejected = 0
    try:
        for stmt in _mysql_units(sql):
            if not is_executable(stmt):
                kept.append(stmt)
                continue
            try:
                cur.execute(stmt)
            except pymysql.err.MySQLError as e:
                errno = e.args[0] if e.args else 0
                if errno == 1064:
                    rejected += 1
                    continue
                if errno in (2006, 2013):  # connection lost: reconnect
                    with contextlib.suppress(Exception):
                        conn.close()
                    conn, cur = connect()
                kept.append(stmt)
            else:
                kept.append(stmt)
    finally:
        with contextlib.suppress(Exception):
            cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        with contextlib.suppress(Exception):
            conn.close()
    return kept, rejected


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument(
        "--dialect",
        choices=("postgresql", "mysql"),
        default="postgresql",
        help="source engine to validate against",
    )
    args = parser.parse_args()

    if args.dialect == "mysql":
        url = os.environ.get("UNIQUE_TEST_MYSQL_URL")
        if not url:
            print("UNIQUE_TEST_MYSQL_URL is not set", file=sys.stderr)
            return 2
        sql = args.file.read_text(encoding="utf-8")
        kept, rejected = filter_mysql(sql, url)
        out_parts = []
        for s in kept:
            if "\n" in s and re.match(r"(?is)\s*CREATE\s", s) and ";" in s:
                out_parts.append(f"DELIMITER //\n{s.rstrip(';')}//\nDELIMITER ;")
            else:
                out_parts.append(s.rstrip("; \n") + ";")
        args.out.write_text("\n".join(out_parts) + "\n")
        print(f"kept {len(kept)} statements, rejected {rejected} source-invalid")
        return 0

    url = os.environ.get("UNIQUE_TEST_PG_URL")
    if not url:
        print("UNIQUE_TEST_PG_URL is not set", file=sys.stderr)
        return 2
    sql = args.file.read_text(encoding="utf-8")
    kept, rejected = filter_pg(sql, url)
    args.out.write_text(";\n".join(s.rstrip("; \n") for s in kept) + ";\n")
    print(f"kept {len(kept)} statements, rejected {rejected} source-invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
