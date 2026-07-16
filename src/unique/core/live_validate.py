# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Optional live validation of transpiled output against a real engine.

The sqlglot-based output gate is the fast first line, but sqlglot is more
lenient than the real engines — forms it accepts can still be rejected live
(the residue class documented in ``docs/TODO.md`` §2 P1). When a target-engine
URL is supplied (``TranspileOptions.validate_live_url``), every emitted
statement the engine rejects is degraded to a documented carrier carrying the
engine's actual error, so no *invalid* output ever ships silently.

**Critical blind spot (user, 2026-07-17):** this catches INVALID output, not
SILENT DATA LOSS. A statement that dropped a clause, an arm, or a row but is
still syntactically valid PASSES live validation (e.g. wave 85's clobbered
set-op chain emitted valid SQL missing data). Live validation is therefore
NEVER the sole check — it complements, never replaces, the no-silent-loss
gates, the differential audits, and human review of what each degrade drops.

Validation is side-effect free per engine:

- **T-SQL**: ``SET PARSEONLY ON`` (pure parse, no execution).
- **PostgreSQL**: each statement runs inside a savepoint that is rolled back.
- **MySQL**: statements run in a throwaway database that is dropped after.
- **Oracle**: ``DBMS_SQL.PARSE`` without EXECUTE (syntax + semantics, no
  execution) for DML/SELECT; DDL is SKIPPED (Oracle runs DDL at parse
  time, so it cannot be validated side-effect free) — returned as
  accepted rather than executed.
"""

from __future__ import annotations

import contextlib
import re
import uuid

#: SQLSTATEs / errnos that mark the STATEMENT ITSELF as malformed for the
#: engine. Environmental errors (missing tables/columns on the validation
#: database) must NOT degrade perfectly good SQL — same classification the
#: validity sweep uses.
_PG_SYNTAX_STATES = frozenset({"42601", "42P02", "42809", "0A000", "42P18", "42804"})
_MYSQL_SYNTAX_ERRNOS = frozenset({1064, 1149, 1327, 1584})
#: ORA codes for a malformed statement (not a missing object). Mirrors the
#: validity sweep's classification.
_ORACLE_SYNTAX_CODES = frozenset(
    {900, 904, 907, 911, 922, 923, 928, 933, 936, 1756, 6550}
)
_DDL_HEAD = re.compile(
    r"(?is)^\s*(?:CREATE|ALTER|DROP|TRUNCATE|COMMENT|GRANT|REVOKE|RENAME)"
)


class UnsupportedLiveValidationError(RuntimeError):
    """Raised when the target engine has no side-effect-free validator."""


def validate_statements(
    url: str, target: str, statements: list[str]
) -> list[str | None]:
    """Run *statements* against the engine at *url*; per statement return
    ``None`` when accepted or the engine's error text when rejected."""
    if target == "tsql":
        return _validate_tsql(url, statements)
    if target == "postgresql":
        return _validate_postgresql(url, statements)
    if target == "mysql":
        return _validate_mysql(url, statements)
    if target == "oracle":
        return _validate_oracle(url, statements)
    raise UnsupportedLiveValidationError(
        f"live validation is not supported for target {target!r} "
        "(no side-effect-free channel)"
    )


def _validate_tsql(url: str, statements: list[str]) -> list[str | None]:
    import pymssql

    m = re.match(r"mssql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable MSSQL URL: {url!r}")
    user, password, host, port, db = m.groups()
    conn = pymssql.connect(  # type: ignore[call-overload]
        server=host,
        port=int(port or 1433),
        user=user,
        password=password,
        database=db,
        autocommit=True,
    )
    cur = conn.cursor()
    cur.execute("SET PARSEONLY ON")
    results: list[str | None] = []
    for st in statements:
        try:
            cur.execute(st)
            results.append(None)
        except Exception as e:  # noqa: BLE001 - the verdict IS the error
            code = e.args[0] if e.args and isinstance(e.args[0], int) else None
            # 911: USE of an absent database — environmental, not syntax.
            results.append(None if code == 911 else str(e))
    cur.execute("SET PARSEONLY OFF")
    conn.close()
    return results


def _validate_postgresql(url: str, statements: list[str]) -> list[str | None]:
    import psycopg

    results: list[str | None] = []
    with psycopg.connect(url, autocommit=False) as conn:
        cur = conn.cursor()
        # Validation runs, not result consumption: a statement that
        # legitimately produces millions of rows (generate_series perf
        # tests) OOMed the CLIENT once the transpiler stopped breaking it
        # (2026-07-16, 32GiB host). A canceled statement is not a syntax
        # error, so the timeout classifies as environmental (no gap).
        cur.execute("SET statement_timeout = 3000")
        for st in statements:
            cur.execute("SAVEPOINT uq_lv")
            try:
                cur.execute(st)
                results.append(None)
            except Exception as e:  # noqa: BLE001
                state = getattr(e, "sqlstate", None)
                results.append(str(e) if state in _PG_SYNTAX_STATES else None)
            try:
                cur.execute("ROLLBACK TO uq_lv")
            except Exception:  # noqa: BLE001 - session died; fresh tx
                conn.rollback()
        conn.rollback()
    return results


def _validate_mysql(url: str, statements: list[str]) -> list[str | None]:
    import pymysql  # type: ignore[import-untyped]

    m = re.match(r"mysql(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable MySQL URL: {url!r}")
    user, password, host, port, _db = m.groups()
    conn = pymysql.connect(
        host=host,
        port=int(port or 3306),
        user=user,
        password=password,
        autocommit=True,
    )
    dbname = f"unique_lv_{uuid.uuid4().hex[:10]}"
    cur = conn.cursor()
    results: list[str | None] = []
    try:
        cur.execute(f"CREATE DATABASE {dbname}")
        cur.execute(f"USE {dbname}")
        for st in statements:
            try:
                cur.execute(st)
                while cur.nextset():
                    pass
                results.append(None)
            except Exception as e:  # noqa: BLE001
                errno = e.args[0] if e.args and isinstance(e.args[0], int) else 0
                results.append(str(e) if errno in _MYSQL_SYNTAX_ERRNOS else None)
    finally:
        try:
            cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        finally:
            conn.close()
    return results


def _validate_oracle(url: str, statements: list[str]) -> list[str | None]:
    import oracledb

    m = re.match(r"oracle(?:\+\w+)?://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url)
    if not m:
        raise ValueError(f"unparseable Oracle URL: {url!r}")
    user, password, host, port, service = m.groups()
    conn = oracledb.connect(
        user=user, password=password, dsn=f"{host}:{int(port or 1521)}/{service}"
    )
    results: list[str | None] = []
    for st in statements:
        code = st.strip().rstrip(";").rstrip("/").strip()
        if not code or _DDL_HEAD.match(code):
            # DBMS_SQL.PARSE executes DDL — cannot validate side-effect free.
            results.append(None)
            continue
        cur = conn.cursor()
        handle = None
        try:
            handle = cur.callfunc("DBMS_SQL.OPEN_CURSOR", int)
            cur.callproc("DBMS_SQL.PARSE", [handle, code, 1])  # 1 = NATIVE
            results.append(None)
        except Exception as e:  # noqa: BLE001 - the verdict IS the error
            num = getattr(e, "args", [None])[0]
            ora = getattr(num, "code", None)
            if ora is None:
                mm = re.search(r"ORA-(\d+)", str(e))
                ora = int(mm.group(1)) if mm else None
            results.append(str(e) if ora in _ORACLE_SYNTAX_CODES else None)
        finally:
            if handle is not None:
                with contextlib.suppress(Exception):
                    cur.callproc("DBMS_SQL.CLOSE_CURSOR", [handle])
    conn.close()
    return results
