# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Validate transpiled SQL against real database engines (syntax only).

These tests transpile representative snippets to each target dialect and ask
the *actual* engine whether the output is valid, catching dialect violations
our own emitter might miss. They are skipped unless the matching connection
URL is provided, so the default run and CI-without-databases stay green.

To run locally::

    docker compose -f docker-compose.test.yaml up -d
    UNIQUE_TEST_MSSQL_URL="mssql://sa:Unique_Strong!Pass1@localhost:1433/master" \\
    UNIQUE_TEST_PG_URL="postgresql://unique:unique@localhost:5433/unique" \\
    UNIQUE_TEST_MYSQL_URL="mysql://unique:unique@localhost:3307/unique" \\
    pytest tests/integration/test_live_syntax.py -v
"""

from __future__ import annotations

import os

import pytest
from helpers.live_validation import make_validator

from unique.core.transpiler import transpile

_URLS = {
    "tsql": os.environ.get("UNIQUE_TEST_MSSQL_URL"),
    "oracle": os.environ.get("UNIQUE_TEST_ORACLE_URL"),
    "postgresql": os.environ.get("UNIQUE_TEST_PG_URL"),
    "mysql": os.environ.get("UNIQUE_TEST_MYSQL_URL"),
}

# Targets validated live, now that procedural fixtures exist for all four
# engines and the validators understand each engine's routine syntax
# (MySQL DELIMITER blocks, PostgreSQL dollar-quoted bodies).
_LIVE_TARGETS = ["tsql", "oracle", "mysql", "postgresql"]

# (source_dialect, source_sql) snippets that exercise constructs known to be
# easy to mistranslate. Each is transpiled to every configured target and the
# output is validated against that engine. Snippets are self-contained (they
# create any object they use) so syntax validation needs no seeded schema.
#
# The optional third element restricts which targets a snippet is validated
# against. It's used to skip cases that are legitimately invalid on a given
# engine (not a transpiler bug) — e.g. a bare ``SELECT 1`` has no FROM clause,
# which Oracle rejects (it needs ``FROM dual``).
_ALL = {"tsql", "oracle", "postgresql", "mysql"}
_NO_ORACLE = _ALL - {"oracle"}

_SNIPPETS = [
    ("postgresql", "CREATE TABLE IF NOT EXISTS t (id INT, name TEXT)", _ALL),
    ("postgresql", "SELECT 1; SELECT 2;", _NO_ORACLE),
    (
        "tsql",
        "CREATE TABLE t (id INT IDENTITY(1,1) PRIMARY KEY, n NVARCHAR(50))",
        _ALL,
    ),
    ("tsql", "SELECT 1 AS a, 2 AS b", _NO_ORACLE),
    ("oracle", "rem a comment\nrem another\nSELECT 1 AS x FROM dual", _ALL),
    ("mysql", "CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY)", _ALL),
    (
        "postgresql",
        "CREATE TABLE t (a INT, b INT); CREATE INDEX ix ON t (a)",
        _ALL,
    ),
    (
        "tsql",
        "CREATE TABLE t (id INT, total AS (id * 2) PERSISTED)",
        _ALL,
    ),
]


def _validator_or_skip(dialect: str):  # type: ignore[no-untyped-def]
    url = _URLS.get(dialect)
    if not url:
        pytest.skip(f"{dialect} validator not configured (set the env var)")
    try:
        return make_validator(dialect, url)
    except ImportError as e:  # pragma: no cover - driver not installed
        pytest.skip(f"driver for {dialect} not installed: {e}")
    except Exception as e:  # pragma: no cover - engine not reachable/ready
        # A connection/setup failure is an environment problem, not a
        # transpiler bug; skip so it doesn't mask real validation results.
        pytest.skip(f"could not connect to {dialect} engine: {e}")


@pytest.mark.parametrize("target", _LIVE_TARGETS)
@pytest.mark.parametrize("source,sql,valid_targets", _SNIPPETS)
def test_transpiled_output_is_valid(
    source: str, sql: str, valid_targets: set, target: str
) -> None:
    if source == target:
        pytest.skip("no transpilation needed")
    if target not in valid_targets:
        pytest.skip(f"snippet not applicable to {target}")
    validator = _validator_or_skip(target)
    try:
        result = transpile(sql, source, target)
        out = result.sql
        if not out.strip() or out.lstrip().startswith("--"):
            pytest.skip("output is comment-only; nothing to validate")
        verdict = validator.validate(out)
        assert verdict.ok, (
            f"{source} -> {target} produced invalid SQL:\n{out}\n"
            f"Engine error: {verdict.error}"
        )
    finally:
        validator.close()


# The full procedural fixture, transpiled and validated against the live
# engine. This is the real test of the stored-procedure surface: the whole
# script (DDL + ~50 routines wrapped in DELIMITER blocks) must load into the
# engine without a syntax error.
_FIXTURE_DIR = (
    __import__("pathlib").Path(__file__).parent.parent / "fixtures" / "procedures"
)


@pytest.mark.parametrize("target", _LIVE_TARGETS)
def test_procedures_fixture_is_valid_live(target: str) -> None:
    if target == "tsql":
        pytest.skip("T-SQL is the source fixture; nothing to transpile")
    fixture = _FIXTURE_DIR / "procedures_sqlserver.sql"
    if not fixture.is_file():
        pytest.skip("T-SQL procedures fixture not present")
    validator = _validator_or_skip(target)
    try:
        out = transpile(fixture.read_text(encoding="utf-8"), "tsql", target).sql
        verdict = validator.validate(out)
        assert verdict.ok, (
            f"tsql -> {target} procedures fixture is invalid:\n"
            f"Engine error: {verdict.error}"
        )
    finally:
        validator.close()
