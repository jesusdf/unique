# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Functional-equivalence test against real engines.

The gold-standard transpiler test: author the scenario once in T-SQL, let the
transpiler generate the PostgreSQL / MySQL / Oracle variants, run all of them on
real databases, and assert each reaches the *same* engine-agnostic final state
(``expected_state.yaml``). This makes the transpiler the system under test.

These tests are **skipped unless** the matching connection URL env var is set,
exactly like ``tests/integration/test_live_syntax.py``:

    UNIQUE_TEST_PG_URL     postgresql://unique:unique@localhost:5433/unique
    UNIQUE_TEST_MYSQL_URL  mysql://unique:unique@localhost:3307/unique
    UNIQUE_TEST_ORACLE_URL oracle://system:oracle@localhost:1521/FREEPDB1
    UNIQUE_TEST_MSSQL_URL   (the T-SQL identity run; optional)

Bring the databases up with:

    docker compose -f docker-compose.test.yaml up -d

then run:

    UNIQUE_TEST_PG_URL=... UNIQUE_TEST_MYSQL_URL=... \\
    pytest tests/functional_equivalence/test_functional_equivalence_live.py -v

Phase 1: T-SQL source → {PostgreSQL, MySQL, Oracle} (+ T-SQL identity). The pure
read+compare mechanics are covered without any engine in
``test_engine_runner.py`` (SQLite) and ``test_state_check.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.functional_equivalence.engine_runner import (
    TABLES,
    EngineRunner,
    connect,
)
from tests.functional_equivalence.state_check import (
    check_state,
    load_expected_state,
)
from unique.core.transpiler import transpile

_HERE = Path(__file__).parent
_SCHEMA = (_HERE / "schema" / "canonical.sql").read_text()
_SCENARIO = (_HERE / "scenario" / "canonical.sql").read_text()
_EXPECTED = load_expected_state(_HERE / "expected_state.yaml")

# The canonical source dialect for Phase 1.
_SOURCE = "tsql"

# target -> connection URL env var.
_URL_ENV = {
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
}

# Phase 1 targets: the three transpiled engines plus the T-SQL identity run.
_TARGETS = ["postgresql", "mysql", "oracle", "tsql"]


def _transpile_for(target: str) -> tuple[str, str]:
    """Return (schema_sql, scenario_sql) for ``target``.

    For the T-SQL identity run the canonical source is used unchanged.
    """
    if target == _SOURCE:
        return _SCHEMA, _SCENARIO
    schema = transpile(_SCHEMA, source=_SOURCE, target=target).sql
    scenario = transpile(_SCENARIO, source=_SOURCE, target=target).sql
    return schema, scenario


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
    """Best-effort teardown so the run is repeatable. Order respects FKs."""
    for table in reversed(TABLES):
        for stmt in (
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


@pytest.mark.parametrize("target", _TARGETS)
def test_functional_equivalence(target: str) -> None:
    """Run the transpiled schema+scenario on ``target`` and assert it reaches
    the engine-agnostic expected state."""
    runner = _runner_or_skip(target)
    try:
        _drop_all(runner)
        schema_sql, scenario_sql = _transpile_for(target)
        runner.execute_script(schema_sql)
        runner.execute_script(scenario_sql)

        mismatches = check_state(_EXPECTED, lambda name: runner.read_table(name))
        assert (
            mismatches == []
        ), f"{target} diverged from the expected state:\n" + "\n".join(
            str(m) for m in mismatches
        )
    finally:
        _drop_all(runner)
        runner.connection.close()
