#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Measure transpilation validity against real engines (audit doc 04, M0).

Transpiles a SQL script to one or more target dialects, executes the output
statement-by-statement on the live engines (the ``docker-compose.test.yaml``
stack), classifies each failure as a **syntax-class** error (a transpiler
defect) or an **expected** error (missing schema/data — the sweep runs against
empty databases), and reports a per-direction validity percentage plus the
most frequent syntax-error groups with sample statements.

This number — not "the fixture is green" — is the definition of done for
transpilation work (see skills/SKILL-development-workflow.md).

Usage:
    scripts/validity_sweep.py FILE [--from DIALECT] [--to t1,t2] [--max N]

Engine URLs come from the standard env vars (UNIQUE_TEST_PG_URL,
UNIQUE_TEST_MYSQL_URL, UNIQUE_TEST_MSSQL_URL, UNIQUE_TEST_ORACLE_URL); a
direction whose engine URL is unset is skipped. SQL Server is checked with
``SET PARSEONLY ON`` (pure parse, no state); MySQL runs in a throwaway
database; Oracle runs in a throwaway schema (needs a DBA-ish user such as
``system``) so created objects never leak.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# The transpiler's sqlglot fallbacks log parse noise on stderr; the sweep's
# verdicts come from the real engines, so keep the output clean.
logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.helpers.sql_split import is_executable, split_statements  # noqa: E402
from unique.core.detection import detect_dialect  # noqa: E402
from unique.core.transpiler import Transpiler  # noqa: E402

ENV_URLS = {
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
}

DIALECTS = ("tsql", "oracle", "postgresql", "mysql")

#: PostgreSQL SQLSTATEs that indicate the *statement itself* is malformed or
#: uses a feature/function that does not exist on PG — transpiler defects.
#: Undefined tables/columns/schemas are expected on an empty database.
PG_SYNTAX_STATES = frozenset({"42601", "42P02", "42809", "0A000", "42P18", "42804"})
PG_EXPECTED_STATES = frozenset(
    {"42P01", "42703", "3F000", "42P07", "23503", "23505", "42883", "42704"}
)

#: MySQL errnos: 1064 parse error, 1149 syntax, 1327 undeclared variable,
#: 1305 missing function/procedure counts as expected (schema not loaded).
MYSQL_SYNTAX_ERRNOS = frozenset({1064, 1149, 1327, 1584})

#: Oracle: ORA codes for malformed statements; any PLS- compile error is a
#: syntax-class failure too. Missing objects/users are expected.
ORACLE_SYNTAX_CODES = frozenset({900, 907, 911, 922, 923, 928, 933, 936, 1756, 6550})
ORACLE_EXPECTED_CODES = frozenset(
    {942, 904, 955, 1418, 1430, 1435, 1918, 2264, 2275, 2289, 3405, 4043, 4080}
)


@dataclass
class DirectionReport:
    """Per-direction sweep result."""

    target: str
    total: int = 0
    ok: int = 0
    syntax: int = 0
    expected: int = 0
    other: int = 0
    groups: Counter = field(default_factory=Counter)
    samples: dict[str, list[str]] = field(default_factory=dict)
    transpile_seconds: float = 0.0
    warning_count: int = 0

    @property
    def validity(self) -> float:
        """Fraction of statements that are not syntax-class failures."""
        return 1.0 - (self.syntax / self.total) if self.total else 1.0

    def record_failure(self, cls: str, group: str, statement: str) -> None:
        if cls == "SYNTAX":
            self.syntax += 1
            self.groups[group] += 1
            bucket = self.samples.setdefault(group, [])
            if len(bucket) < 2:
                bucket.append(statement.replace("\n", " ")[:180])
        elif cls == "expected":
            self.expected += 1
        else:
            self.other += 1


def classify_pg(sqlstate: str | None) -> str:
    if sqlstate in PG_SYNTAX_STATES:
        return "SYNTAX"
    if sqlstate in PG_EXPECTED_STATES:
        return "expected"
    return "other"


def classify_mysql(errno: int) -> str:
    if errno in MYSQL_SYNTAX_ERRNOS:
        return "SYNTAX"
    return "expected"


def classify_oracle(message: str) -> str:
    # ORA-06550 wraps ANY PL/SQL compile problem: a missing routine/table
    # (empty-database noise) reports as PLS-00201 / a nested ORA-00942, while
    # genuine malformed code reports structural PLS codes (e.g. PLS-00103).
    # Check the expected-nested shapes first. Trade-off: an undeclared
    # *variable* is also PLS-00201; a schema-less run cannot tell it from a
    # missing procedure, so those land in "expected" too.
    if re.search(r"PLS-00201\b|PL/SQL: ORA-00942\b|PLS-00905\b", message):
        return "expected"
    m = re.search(r"(ORA|PLS)-(\d+)", message)
    if not m:
        return "other"
    kind, num = m.group(1), int(m.group(2))
    if kind == "PLS" or num in ORACLE_SYNTAX_CODES:
        return "SYNTAX"
    if num in ORACLE_EXPECTED_CODES:
        return "expected"
    return "other"


def _error_group(message: str) -> str:
    """A stable, low-cardinality key for grouping similar errors."""
    return re.sub(r"\s+", " ", message).strip()[:90]


# --- per-engine execution ---------------------------------------------------


def sweep_postgresql(url: str, statements: list[str], report: DirectionReport) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=False) as conn:
        cur = conn.cursor()
        for st in statements:
            cur.execute("SAVEPOINT s")
            try:
                cur.execute(st)
                report.ok += 1
            except Exception as e:  # noqa: BLE001 - engine verdicts drive the report
                code = getattr(e, "sqlstate", None)
                report.record_failure(
                    classify_pg(code), f"{code}: {_error_group(str(e))}", st
                )
            try:
                cur.execute("ROLLBACK TO s")
            except Exception:  # noqa: BLE001 - session died; start a fresh tx
                conn.rollback()
        conn.rollback()


def sweep_mysql(url: str, statements: list[str], report: DirectionReport) -> None:
    import uuid

    import pymysql

    m = re.match(r"mysql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"Unparseable MySQL URL: {url!r}")
    user, password, host, port, _db = m.groups()
    conn = pymysql.connect(
        host=host, port=int(port or 3306), user=user, password=password, autocommit=True
    )
    dbname = f"unique_sweep_{uuid.uuid4().hex[:10]}"
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE DATABASE {dbname}")
        cur.execute(f"USE {dbname}")
        for st in statements:
            try:
                cur.execute(st)
                while cur.nextset():
                    pass
                report.ok += 1
            except Exception as e:  # noqa: BLE001
                errno = e.args[0] if e.args and isinstance(e.args[0], int) else 0
                report.record_failure(
                    classify_mysql(errno), f"{errno}: {_error_group(str(e))}", st
                )
    finally:
        with contextlib.suppress(Exception):  # best-effort cleanup
            cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        conn.close()


def sweep_tsql(url: str, statements: list[str], report: DirectionReport) -> None:
    import pymssql

    m = re.match(r"mssql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"Unparseable MSSQL URL: {url!r}")
    user, password, host, port, db = m.groups()
    conn = pymssql.connect(
        server=host,
        port=int(port or 1433),
        user=user,
        password=password,
        database=db,
        autocommit=True,
    )
    cur = conn.cursor()
    # Pure parse check: no binding, no state, missing tables don't error.
    cur.execute("SET PARSEONLY ON")
    for st in statements:
        try:
            cur.execute(st)
            report.ok += 1
        except Exception as e:  # noqa: BLE001 - under PARSEONLY every error is syntax
            # ...except 911 (USE of a database that doesn't exist), which is
            # environmental: the statement parsed, the target DB is absent.
            code = e.args[0] if e.args and isinstance(e.args[0], int) else None
            if code == 911:
                report.expected += 1
                continue
            report.record_failure("SYNTAX", _error_group(str(e)), st)
    cur.execute("SET PARSEONLY OFF")
    conn.close()


def sweep_oracle(url: str, statements: list[str], report: DirectionReport) -> None:
    import uuid

    import oracledb

    m = re.match(r"oracle(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"Unparseable Oracle URL: {url!r}")
    user, password, host, port, service = m.groups()

    def _connect():  # noqa: ANN202 - reconnect helper (session kills)
        c = oracledb.connect(
            user=user,
            password=password,
            dsn=f"{host}:{int(port or 1521)}/{service}",
        )
        return c, c.cursor()

    conn, cur = _connect()
    schema = f"UNIQUE_SWEEP_{uuid.uuid4().hex[:8].upper()}"
    isolated = False
    try:
        cur.execute(f"CREATE USER {schema} IDENTIFIED BY sweep_{schema[-8:]}")
        cur.execute(f"ALTER USER {schema} QUOTA UNLIMITED ON USERS")
        cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {schema}")
        isolated = True
    except Exception:  # noqa: BLE001 - fall back to the connected schema
        print(
            f"  [oracle] could not create throwaway schema {schema}; "
            "objects the sweep creates will leak into the connected schema",
            file=sys.stderr,
        )
    routine_re = re.compile(
        r"(?is)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
        r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\s+(?:\w+\.)?\"?(\w+)"
    )
    owner = (schema if isolated else user).upper()
    conn_lost = ("DPY-1001", "DPY-4011", "ORA-03113", "ORA-03114", "ORA-03135")
    try:
        for st in statements:
            try:
                cur.execute(st)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if any(code in msg for code in conn_lost):
                    # A wild statement killed the server session: reconnect,
                    # count it as OTHER (not the statement's syntax), go on.
                    with contextlib.suppress(Exception):
                        conn.close()
                    conn, cur = _connect()
                    if isolated:
                        with contextlib.suppress(Exception):
                            cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {schema}")
                    report.other += 1
                    continue
                report.record_failure(classify_oracle(msg), _error_group(msg), st)
                continue
            # Oracle compiles PL/SQL lazily: CREATE succeeds even for a broken
            # body (the object is left INVALID). Query the compile errors so a
            # broken routine is not counted as ok (same as the live validator).
            routine = routine_re.match(st)
            if routine:
                cur.execute(
                    "SELECT text FROM all_errors "
                    "WHERE owner = :o AND name = :n AND attribute = 'ERROR' "
                    "ORDER BY sequence",
                    o=owner,
                    n=routine.group(1).upper(),
                )
                errors = " ".join(row[0] for row in cur.fetchall())
                if errors:
                    report.record_failure(
                        classify_oracle(errors), _error_group(errors), st
                    )
                    continue
            report.ok += 1
        conn.rollback()
    finally:
        if isolated:
            with contextlib.suppress(Exception):  # best-effort cleanup
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {user}")
                cur.execute(f"DROP USER {schema} CASCADE")
        conn.close()


SWEEPERS = {
    "postgresql": sweep_postgresql,
    "mysql": sweep_mysql,
    "tsql": sweep_tsql,
    "oracle": sweep_oracle,
}


# --- orchestration ----------------------------------------------------------


def run_direction(
    sql: str, source: str, target: str, url: str, max_statements: int
) -> DirectionReport:
    report = DirectionReport(target=target)
    t0 = time.time()
    result = Transpiler().transpile(sql, source, target)
    report.transpile_seconds = time.time() - t0
    report.warning_count = len(result.warnings)
    statements = [s for s in split_statements(result.sql, target) if is_executable(s)]
    if max_statements:
        statements = statements[:max_statements]
    report.total = len(statements)
    SWEEPERS[target](url, statements, report)
    return report


def print_report(name: str, source: str, report: DirectionReport) -> None:
    print(
        f"\n== {name}: {source} -> {report.target} — "
        f"validity {report.validity:.1%} "
        f"({report.total} stmts: {report.ok} ok, {report.syntax} syntax, "
        f"{report.expected} expected-missing, {report.other} other; "
        f"{report.warning_count} warnings, "
        f"transpiled in {report.transpile_seconds:.1f}s)"
    )
    for group, count in report.groups.most_common(12):
        print(f"  {count:6}x  {group}")
        for sample in report.samples.get(group, []):
            print(f"           e.g. {sample}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", type=Path, help="SQL script(s) to sweep")
    parser.add_argument("--from", dest="source", default="auto", help="source dialect")
    parser.add_argument(
        "--to",
        dest="targets",
        default="",
        help="comma-separated target dialects (default: all except the source)",
    )
    parser.add_argument(
        "--max",
        dest="max_statements",
        type=int,
        default=0,
        help="cap statements per direction (0 = no cap)",
    )
    args = parser.parse_args()

    exit_code = 0
    for path in args.files:
        sql = path.read_text()
        source = args.source
        if source == "auto":
            detected = detect_dialect(sql)
            if detected.dialect is None:
                print(
                    f"{path.name}: could not detect the source dialect", file=sys.stderr
                )
                exit_code = 2
                continue
            source = detected.dialect
        targets = (
            [t.strip() for t in args.targets.split(",") if t.strip()]
            if args.targets
            else [d for d in DIALECTS if d != source]
        )
        for target in targets:
            url = os.environ.get(ENV_URLS[target], "")
            if not url:
                env_var = ENV_URLS[target]
                print(f"{path.name}: {source}->{target} skipped ({env_var} unset)")
                continue
            report = run_direction(sql, source, target, url, args.max_statements)
            print_report(path.name, source, report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
