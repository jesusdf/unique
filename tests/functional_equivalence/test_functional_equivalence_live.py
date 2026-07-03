# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Functional-equivalence test against real engines — the 4x4 matrix.

The gold-standard transpiler test. The repository stores only the **canonical
native fixtures**, one per dialect (``schema/<dialect>.sql`` +
``scenario/<dialect>.sql``), each authored idiomatically. The transpiled
cross-dialect variants are produced **on the fly** here, never committed.

For every (source, target) pair in {tsql, postgresql, mysql, oracle} squared:

- source == target: run the native fixture directly (also checks each fixture is
  correct and exercises that dialect's emitter identity path).
- source != target: transpile the source's native schema + scenario to the
  target and run that.

Then read every table on the target and assert it matches the engine-agnostic
``expected_state.yaml``. All 16 pairs reaching the same state == functional
equivalence: the scenario, authored once per engine, means the same thing on all
of them regardless of which engine it was written for.

Each pair is **skipped** unless the target engine's connection URL env var is
set (so partial local runs work), exactly like ``test_live_syntax.py``:

    UNIQUE_TEST_MSSQL_URL   (T-SQL / SQL Server)
    UNIQUE_TEST_PG_URL      (PostgreSQL)
    UNIQUE_TEST_MYSQL_URL   (MySQL)
    UNIQUE_TEST_ORACLE_URL  (Oracle)

Bring the databases up with ``docker compose -f docker-compose.test.yaml up -d``
and see ``HARNESS.md`` for the full runbook.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.functional_equivalence.engine_runner import TABLES, EngineRunner, connect
from tests.functional_equivalence.state_check import check_state, load_expected_state
from unique.core.transpiler import transpile

_HERE = Path(__file__).parent
_EXPECTED = load_expected_state(_HERE / "expected_state.yaml")

_DIALECTS = ("tsql", "postgresql", "mysql", "oracle")

# dialect -> connection URL env var (the engine that runs the transpiled SQL).
_URL_ENV = {
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
}

# All 16 (source, target) pairs.
_PAIRS = [(s, t) for s in _DIALECTS for t in _DIALECTS]


def _native(kind: str, dialect: str) -> str:
    """Read a committed native fixture (kind is 'schema' or 'scenario')."""
    return (_HERE / kind / f"{dialect}.sql").read_text()


def _scripts_for(source: str, target: str) -> tuple[str, ...]:
    """The scripts to run on ``target``: the native fixtures when
    source==target, otherwise schema+scenario transpiled *as one script* (on
    the fly). One transpile call matters: the transpiler harvests
    cross-statement knowledge from the script (alias types, BIT columns) that
    the scenario's DML depends on."""
    if source == target:
        return (_native("schema", source), _native("scenario", source))
    combined = _native("schema", source) + "\n" + _native("scenario", source)
    return (transpile(combined, source=source, target=target).sql,)


def _runner_or_skip(target: str) -> EngineRunner:
    url = os.environ.get(_URL_ENV[target])
    if not url:
        pytest.skip(f"{target} not configured (set {_URL_ENV[target]})")
    try:
        conn = connect(target, url)
    except ImportError as e:  # pragma: no cover - driver not installed
        pytest.skip(f"driver for {target} not installed: {e}")
    except Exception as e:  # pragma: no cover - engine not reachable
        pytest.skip(f"could not connect to {target}: {e}")
    return EngineRunner(connection=conn, dialect=target)


def _drop_all(runner: EngineRunner) -> None:
    """Best-effort teardown so each pair starts clean. Order respects FKs."""
    for table in reversed(TABLES):
        for stmt in (
            f"DROP TABLE IF EXISTS {table} CASCADE",
            f"DROP TABLE IF EXISTS {table}",
            f"DROP TABLE {table}",
        ):
            cur = runner.connection.cursor()
            try:
                cur.execute(stmt)
                runner.connection.commit()
                break
            except Exception:
                runner.connection.rollback()
            finally:
                cur.close()


@pytest.mark.parametrize(
    "source,target",
    _PAIRS,
    ids=[f"{s}->{t}" for s, t in _PAIRS],
)
def test_functional_equivalence(source: str, target: str) -> None:
    """Run the (transpiled) scenario for ``source`` on ``target`` and assert it
    reaches the engine-agnostic expected state."""
    runner = _runner_or_skip(target)
    try:
        _drop_all(runner)
        for script in _scripts_for(source, target):
            runner.execute_script(script)

        # Set-based / statement-level transition-table triggers (T-SQL's
        # inserted/deleted, PostgreSQL's REFERENCING … TABLE + trigger function)
        # are a documented divergence on MySQL and Oracle: their bodies arrive
        # as carrier comments, so the values they maintain are out of scope
        # there. The PostgreSQL target (faithful transition-table rewrite) and
        # every native run assert the full state.
        ignore_triggers = source in ("tsql", "postgresql") and target in (
            "mysql",
            "oracle",
        )
        mismatches = check_state(
            _EXPECTED,
            runner.read_table,
            ignore_trigger_maintained=ignore_triggers,
        )
        assert (
            mismatches == []
        ), f"{source}->{target} diverged from the expected state:\n" + "\n".join(
            str(m) for m in mismatches
        )
    finally:
        _drop_all(runner)
        runner.connection.close()
