# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

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
    "postgresql": os.environ.get("UNIQUE_TEST_PG_URL"),
    "mysql": os.environ.get("UNIQUE_TEST_MYSQL_URL"),
}

# (source_dialect, source_sql) snippets that exercise constructs known to be
# easy to mistranslate. Each is transpiled to every configured target and the
# output is validated against that engine.
_SNIPPETS = [
    ("postgresql", "CREATE TABLE IF NOT EXISTS t (id INT, name TEXT)"),
    ("postgresql", "SELECT 1; SELECT 2;"),
    ("tsql", "CREATE TABLE t (id INT IDENTITY(1,1) PRIMARY KEY, n NVARCHAR(50))"),
    ("tsql", "SELECT TOP 5 * FROM t WHERE n IS NOT NULL"),
    ("oracle", "rem a comment\nrem another\nSELECT 1 FROM dual"),
    ("mysql", "CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY)"),
    ("postgresql", "INSERT INTO t (id) VALUES (1) RETURNING id"),
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


@pytest.mark.parametrize("target", ["tsql", "postgresql", "mysql"])
@pytest.mark.parametrize("source,sql", _SNIPPETS)
def test_transpiled_output_is_valid(source: str, sql: str, target: str) -> None:
    if source == target:
        pytest.skip("no transpilation needed")
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
