# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Nightly differential *execution* over the procedures fixture (audit A10-P1).

``test_live_syntax.test_procedures_fixture_is_valid_live`` proves the transpiled
routines *compile*; this proves each enrolled routine *does the same thing*. For
every ``RoutineCase`` in ``procedures_fe_spec.ROUTINE_CASES`` it seeds the fixed
inputs, creates + runs the routine from the ORIGINAL T-SQL on SQL Server and from
the freshly transpiled output on each target, and compares the observable effect
(a scalar return, OUT params, result set(s), or table state) with the same
``normalize_rows`` comparator ``test_challenge_live`` / ``test_corpus_results_live``
use.

Key departure from ``test_challenge_live``: it skips on *any* warning, but almost
every procedure carries at least ``UNIQUE-1193`` (SET NOCOUNT ON dropped), so a
blanket skip would compare nothing. Here the gate is a per-code BENIGN allowlist
(``BENIGN_WARNINGS`` = {1193, 1196}); any other code is a documented degrade and
skips-with-reason (that is how proc_13's SQL_VARIANT 1152 and the RAISERROR procs'
MySQL 1163 keep from being false failures).

Serial only (shared engines, shared table names) — connections are opened once
per module and reused, and every seed table + the routine are dropped before AND
after each case (DDL auto-commits on MySQL/Oracle). Skipped entirely unless the
``UNIQUE_TEST_*_URL`` env vars are set, so the offline suite stays green; it runs
in the nightly ``challenge-live`` workflow against the four live containers.

Brief A10-P3 additions: ``RoutineCase.freeze_func1`` pins the fixture's
``func1()`` clock stub to a fixed constant on both engines before the case runs
(``procedures_fe_spec.freeze_func1_sql``), making its dependents deterministic;
``resultset_tail`` calls a ``table_state`` routine whose body ALSO ends in a
bare ``SELECT`` (the secondary result set is discarded, not compared — see
``_call_table_state_with_rs_tail``); ``targets`` restricts a case to a subset
of ``TARGETS`` when it is comparable on some but hits an unrelated, documented
defect on another (see ``proc_26`` in ``procedures_fe_spec.py``).
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from tests.functional_equivalence.engine_runner import connect
from tests.helpers.corpus_diff import normalize_rows, urls_from_env
from tests.helpers.procedures_fe_spec import (
    BENIGN_WARNINGS,
    ROUTINE_CASES,
    RoutineCase,
    call_argument,
    extract_table_ddl,
    freeze_func1_sql,
    identity_column,
    param_order,
    positional_args,
    seed_literal,
)
from unique.core.sql_split import split_statements
from unique.core.transpiler import transpile

# T-SQL is the source of every fixture routine; these are the compare targets.
TARGETS: tuple[str, ...] = ("oracle", "postgresql", "mysql")

# A per-code allowlist would over-admit UNIQUE-1231 (a generic fallback code
# covering many unrelated messages, e.g. the embedded-DML raw-sqlglot
# fallback — NOT benign); this maps a code to the exact benign MESSAGE
# prefixes seen so far (brief A10-P3: the "OPTION (RECOMPILE) dropped"
# message says outright it only affects the execution plan).
_BENIGN_MESSAGE_PREFIXES: dict[str, tuple[str, ...]] = {
    "UNIQUE-1231": ("T-SQL query hint OPTION (RECOMPILE) has no portable equivalent",),
}


def _is_benign(code: str, message: str) -> bool:
    if code in BENIGN_WARNINGS:
        return True
    return any(message.startswith(p) for p in _BENIGN_MESSAGE_PREFIXES.get(code, ()))


_PARAMS = [
    (case, target) for case in ROUTINE_CASES for target in (case.targets or TARGETS)
]


@pytest.fixture(scope="module")
def engines() -> Any:
    """Open one connection per available engine, reused across all cases."""
    urls = urls_from_env()
    conns: dict[str, Any] = {}
    for eng in ("tsql", *TARGETS):
        url = urls.get(eng)
        if not url:
            continue
        with contextlib.suppress(Exception):  # driver / DB unavailable -> skip below
            conns[eng] = connect(eng, url)
    yield conns
    for conn in conns.values():
        with contextlib.suppress(Exception):
            conn.close()


# --------------------------------------------------------------------------- #
# Thin, engine-specific execution helpers.
# --------------------------------------------------------------------------- #
def _run_script(conn: Any, engine: str, sql: str) -> None:
    for stmt in split_statements(sql, engine):
        if not stmt.strip():
            continue
        cur = conn.cursor()
        try:
            cur.execute(stmt)
        finally:
            cur.close()
    conn.commit()


def _exec_quiet(conn: Any, stmt: str) -> None:
    """Run a teardown statement, swallowing failures (a stale/absent object)."""
    cur = conn.cursor()
    try:
        cur.execute(stmt)
        conn.commit()
    except Exception:  # noqa: BLE001 - best-effort teardown
        with contextlib.suppress(Exception):
            conn.rollback()
    finally:
        cur.close()


def _drop_routine(conn: Any, engine: str, object_kind: str, name: str) -> None:
    kw = "FUNCTION" if object_kind == "function" else "PROCEDURE"
    if engine == "tsql":
        _exec_quiet(conn, f"DROP {kw} IF EXISTS dbo.{name}")
    elif engine == "postgresql":
        _exec_quiet(conn, f"DROP {kw} IF EXISTS {name} CASCADE")
    elif engine == "mysql":
        _exec_quiet(conn, f"DROP {kw} IF EXISTS {name}")
    else:  # oracle: no IF EXISTS
        _exec_quiet(conn, f"DROP {kw} {name}")


def _drop_table(conn: Any, engine: str, table: str) -> None:
    if engine == "oracle":
        _exec_quiet(conn, f"DROP TABLE {table} CASCADE CONSTRAINTS")
    else:
        _exec_quiet(conn, f"DROP TABLE IF EXISTS {table}")


def _drop_func1(conn: Any, engine: str) -> None:
    if engine == "tsql":
        _exec_quiet(conn, "DROP FUNCTION IF EXISTS dbo.func1")
    elif engine == "postgresql":
        _exec_quiet(conn, "DROP FUNCTION IF EXISTS func1() CASCADE")
    elif engine == "mysql":
        _exec_quiet(conn, "DROP FUNCTION IF EXISTS func1")
    else:  # oracle: no IF EXISTS
        _exec_quiet(conn, "DROP FUNCTION func1")


def _freeze_func1(conn: Any, engine: str) -> None:
    """Pin ``func1()`` to a fixed constant on *engine* (brief A10-P3)."""
    _run_script(conn, engine, freeze_func1_sql(engine))


def _teardown(conn: Any, engine: str, case: RoutineCase) -> None:
    with contextlib.suppress(Exception):  # clear an aborted PG transaction first
        conn.rollback()
    _drop_routine(conn, engine, case.object_kind, case.name)
    for seed in case.seed:
        _drop_table(conn, engine, seed.name)
    if case.freeze_func1:
        _drop_func1(conn, engine)


def _seed(conn: Any, engine: str, case: RoutineCase) -> None:
    for seed in case.seed:
        ddl = extract_table_ddl(seed.name)
        if engine != "tsql":
            ddl = transpile(ddl, "tsql", engine).sql
        _run_script(conn, engine, ddl)
        if not seed.rows:
            continue
        idcol = identity_column(seed.name)
        stmts: list[str] = []
        if engine == "tsql" and idcol:
            stmts.append(f"SET IDENTITY_INSERT {seed.name} ON")
        for row in seed.rows:
            cols = ", ".join(row)
            vals = ", ".join(seed_literal(row[c], engine) for c in row)
            stmts.append(f"INSERT INTO {seed.name} ({cols}) VALUES ({vals})")
        if engine == "tsql" and idcol:
            stmts.append(f"SET IDENTITY_INSERT {seed.name} OFF")
        for stmt in stmts:
            cur = conn.cursor()
            try:
                cur.execute(stmt)
            finally:
                cur.close()
        conn.commit()


def _scalar_call(engine: str, name: str, arg_sql: str) -> str:
    if engine == "tsql":
        return f"SELECT dbo.{name}({arg_sql})"
    if engine == "oracle":
        return f"SELECT {name}({arg_sql}) FROM dual"
    return f"SELECT {name}({arg_sql})"


def _call_table_state(conn: Any, engine: str, case: RoutineCase) -> None:
    args = positional_args(case, engine)
    cur = conn.cursor()
    try:
        if engine == "postgresql":
            placeholders = ", ".join(["%s"] * len(args))
            cur.execute(f"CALL {case.name}({placeholders})", args)
        elif engine == "tsql":
            cur.callproc(f"dbo.{case.name}", tuple(args))
        else:  # oracle / mysql
            cur.callproc(case.name, tuple(args))
    finally:
        cur.close()
    conn.commit()


def _call_table_state_with_rs_tail(conn: Any, engine: str, case: RoutineCase) -> None:
    """Like ``_call_table_state``, for a routine whose body ALSO ends in a bare
    ``SELECT`` (``case.resultset_tail``, brief A10-P3) — that secondary result
    set is not compared here (A10-P2 owns result-set comparison), only called
    and discarded, per engine:

    - **oracle**: the transpiler synthesizes a trailing ``RESULT_CURSOR OUT
      SYS_REFCURSOR`` param; bind a plain ``Cursor`` object to it (never
      ``cur.var(oracledb.CURSOR)`` — that hangs against this stack, per the
      A10-P design probe) and never fetch from it.
    - **postgresql**: the procedure gets a trailing ``INOUT result_cursor
      refcursor`` param; pass a throwaway portal name and never ``FETCH`` it.
    - **tsql / mysql**: the SELECT comes back as an ordinary pending result
      set on the same cursor — ``fetchall()`` (mysql: plus draining any
      further ``nextset()``) discards it before the connection is reused.
    """
    args = positional_args(case, engine)
    cur = conn.cursor()
    try:
        if engine == "postgresql":
            placeholders = ", ".join(["%s"] * len(args) + ["%s"])
            cur.execute(f"CALL {case.name}({placeholders})", (*args, "fe_rs_probe"))
        elif engine == "oracle":
            out_cur = conn.cursor()
            cur.callproc(case.name, [*args, out_cur])
        elif engine == "mysql":
            cur.callproc(case.name, tuple(args))
            with contextlib.suppress(Exception):
                cur.fetchall()
            while cur.nextset():
                pass
        else:  # tsql
            cur.callproc(f"dbo.{case.name}", tuple(args))
            with contextlib.suppress(Exception):
                cur.fetchall()
    finally:
        cur.close()
    conn.commit()


def _call_out(conn: Any, engine: str, case: RoutineCase) -> list[tuple]:
    """Call an OUT/INOUT-param procedure and read the output values, in param order.

    T-SQL ``OUTPUT`` params are INOUT (the caller passes a value in and the
    routine may read it before overwriting), so an ``out_params`` slot also
    takes its ``case.args`` input when one is given — that is how proc_14, whose
    body reads ``@query``, is exercised faithfully (pass ``@query='base'`` in and
    read ``'base flt'`` back). A slot with no ``args`` entry passes NULL in, i.e.
    a plain write-only observation.
    """
    order = param_order(case.name)
    out_pos = {order.index(p) for p in case.out_params}
    cur = conn.cursor()
    try:
        if engine == "tsql":
            import pymssql

            args = [
                (
                    pymssql.output(str, call_argument(case.args.get(p), engine))
                    if i in out_pos
                    else call_argument(case.args.get(p), engine)
                )
                for i, p in enumerate(order)
            ]
            returned = cur.callproc(f"dbo.{case.name}", tuple(args))
            values = tuple(returned[i] for i in sorted(out_pos))
        elif engine == "oracle":
            import oracledb

            binds: list[Any] = []
            outvars = {}
            for i, p in enumerate(order):
                if i in out_pos:
                    v = cur.var(oracledb.STRING, 4000)
                    in_val = call_argument(case.args.get(p), engine)
                    if in_val is not None:  # IN OUT: seed the caller's input value
                        v.setvalue(0, in_val)
                    outvars[i] = v
                    binds.append(v)
                else:
                    binds.append(call_argument(case.args.get(p), engine))
            cur.callproc(case.name, binds)
            values = tuple(outvars[i].getvalue() for i in sorted(out_pos))
        elif engine == "mysql":
            args = [
                call_argument(case.args.get(p), engine) for p in order
            ]  # INOUT slots seed @_proc_i with the input value
            cur.callproc(case.name, tuple(args))
            selects = ", ".join(f"@_{case.name}_{i}" for i in sorted(out_pos))
            cur.execute(f"SELECT {selects}")
            values = tuple(cur.fetchone())
        else:  # postgresql
            placeholders = ", ".join(["%s"] * len(order))
            binds = [call_argument(case.args.get(p), engine) for p in order]
            cur.execute(f"CALL {case.name}({placeholders})", binds)
            row = cur.fetchone()
            # plpgsql returns INOUT params in declared order among themselves.
            values = tuple(row[k] for k in range(len(sorted(out_pos))))
    finally:
        cur.close()
    conn.commit()
    return [values]


def _call_resultset(conn: Any, engine: str, case: RoutineCase) -> list[list[tuple]]:
    """Call a result-set procedure and capture its result sets, in order.

    A bare T-SQL result ``SELECT`` is lowered differently per target, so the
    capture differs (audit design §2): Oracle appends one ``SYS_REFCURSOR`` OUT
    param per result set — bind a **plain ``Cursor``** object (``cur.var(CURSOR)``
    hangs on this stack); PostgreSQL appends one ``refcursor`` INOUT — pass a
    portal-name literal and ``FETCH ALL FROM`` it in the same transaction (B56);
    MySQL and the T-SQL source stream the sets back directly (callproc / EXEC, then
    fetch, ``nextset`` between sets). Exactly ``case.result_sets`` sets are taken on
    every engine — the count is the same on all (one per bare result SELECT), which
    also drops MySQL's trailing OK-packet set.
    """
    n = case.result_sets
    order = param_order(case.name)
    in_args = positional_args(case, engine)
    cur = conn.cursor()
    sets: list[list[tuple]] = []
    try:
        if engine == "oracle":
            outs = [conn.cursor() for _ in range(n)]
            cur.callproc(case.name, [*in_args, *outs])
            sets = [list(o.fetchall()) for o in outs]
        elif engine == "postgresql":
            portals = [f"{case.name}_rc{i + 1}" for i in range(n)]
            placeholders = ", ".join(["%s"] * (len(in_args) + n))
            cur.execute(f"CALL {case.name}({placeholders})", [*in_args, *portals])
            for portal in portals:
                cur.execute(f'FETCH ALL FROM "{portal}"')
                sets.append(list(cur.fetchall()))
        elif engine == "tsql":
            arg_sql = ", ".join(seed_literal(case.args.get(p), "tsql") for p in order)
            cur.execute(f"EXEC dbo.{case.name} {arg_sql}")
            for _ in range(n):
                sets.append(list(cur.fetchall()))
                cur.nextset()
        else:  # mysql
            cur.callproc(case.name, tuple(in_args))
            for _ in range(n):
                sets.append(list(cur.fetchall()))
                cur.nextset()
    finally:
        cur.close()
    conn.commit()
    return sets


def _run_case(
    conn: Any, engine: str, case: RoutineCase, routine_sql: str, *, fold: bool
) -> list[list[tuple]]:
    """Seed, create, exercise and observe *case* on *engine*; return probe results."""
    _teardown(conn, engine, case)
    try:
        if case.freeze_func1:
            _freeze_func1(conn, engine)
        _seed(conn, engine, case)
        _run_script(conn, engine, routine_sql)
        if case.kind == "scalar":
            cur = conn.cursor()
            try:
                cur.execute(
                    _scalar_call(engine, case.name, ", ".join(case.scalar_args))
                )
                rows = cur.fetchall()
            finally:
                cur.close()
            return [normalize_rows(rows, empty_as_null=fold)]
        if case.kind == "out":
            rows = _call_out(conn, engine, case)
            return [normalize_rows(rows, empty_as_null=fold)]
        if case.kind == "resultset":
            sets = _call_resultset(conn, engine, case)
            return [normalize_rows(s, empty_as_null=fold) for s in sets]
        # table_state
        if case.resultset_tail:
            _call_table_state_with_rs_tail(conn, engine, case)
        else:
            _call_table_state(conn, engine, case)
        results: list[list[tuple]] = []
        for probe in case.probes:
            cur = conn.cursor()
            try:
                cur.execute(probe)
                rows = cur.fetchall()
            finally:
                cur.close()
            results.append(normalize_rows(rows, empty_as_null=fold))
        return results
    finally:
        _teardown(conn, engine, case)


@pytest.mark.integration
@pytest.mark.parametrize(
    "case,target",
    _PARAMS,
    ids=[f"{c.name}[tsql->{t}]" for c, t in _PARAMS],
)
def test_routine_effect_matches(engines: Any, case: RoutineCase, target: str) -> None:
    """The transpiled routine must produce the SAME observable effect as the source."""
    if "tsql" not in engines or target not in engines:
        pytest.skip(f"needs live URLs for tsql and {target}")

    result = transpile(case.source_sql, "tsql", target)
    non_benign = sorted(
        {w.code for w in result.warnings if not _is_benign(w.code, w.message)}
    )
    if non_benign:
        # A documented degrade (e.g. 1152 SQL_VARIANT, 1163 RAISERROR args, 1191
        # OUTPUT dropped) is not result-comparable — same contract as the corpus.
        pytest.skip(f"{case.name} -> {target}: documented degrade {non_benign}")

    fold = target == "oracle"  # Oracle folds '' -> NULL; fold both sides alike
    source = _run_case(engines["tsql"], "tsql", case, case.source_sql, fold=fold)
    target_result = _run_case(engines[target], target, case, result.sql, fold=fold)

    assert source == target_result, (
        f"{case.name} tsql -> {target}: transpiled routine ran but its observable "
        f"effect differs from the source — a semantic bug.\n"
        f"  source: {source}\n"
        f"  target: {target_result}\n"
        f"  output: {result.sql!r}"
    )
