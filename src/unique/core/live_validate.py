# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Optional live validation of transpiled output against a real engine.

The sqlglot-based output gate is the fast first line, but sqlglot is more
lenient than the real engines — forms it accepts can still be rejected live
(the residue class documented in ``docs/TODO.md`` §2 P1). When a target-engine
URL is supplied (``TranspileOptions.validate_live_url``), every emitted
statement the engine rejects is degraded to a documented carrier carrying the
engine's actual error, so no invalid output ever ships silently.

Validation is side-effect free per engine:

- **T-SQL**: ``SET PARSEONLY ON`` (pure parse, no execution).
- **PostgreSQL**: each statement runs inside a savepoint that is rolled back.
- **MySQL**: statements run in a throwaway database that is dropped after.
- **Oracle**: not supported yet (no side-effect-free validation channel:
  DDL autocommits and a throwaway schema needs DBA rights) — raises
  ``UnsupportedLiveValidationError``.
"""

from __future__ import annotations

import re
import uuid

#: SQLSTATEs / errnos that mark the STATEMENT ITSELF as malformed for the
#: engine. Environmental errors (missing tables/columns on the validation
#: database) must NOT degrade perfectly good SQL — same classification the
#: validity sweep uses.
_PG_SYNTAX_STATES = frozenset({"42601", "42P02", "42809", "0A000", "42P18", "42804"})
_MYSQL_SYNTAX_ERRNOS = frozenset({1064, 1149, 1327, 1584})


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
