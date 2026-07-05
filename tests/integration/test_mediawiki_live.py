# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Execute the transpiled MediaWiki schema against real engines (live DDL).

Unlike ``test_external_schemas.py`` (which only parses the output with sqlglot),
this runs the transpiled 64-table schema against an actual database and checks
every statement executes. Skipped unless the matching ``UNIQUE_TEST_*_URL`` is
set, so the default run and CI-without-databases stay green.

To run locally::

    docker compose -f docker-compose.test.yaml up -d   # or the running stack
    UNIQUE_TEST_PG_URL=postgresql://unique:unique@localhost:5433/unique \\
    UNIQUE_TEST_MYSQL_URL=mysql://unique:unique@localhost:3307/unique \\
    UNIQUE_TEST_ORACLE_URL=oracle://system:...@localhost:1521/FREEPDB1 \\
    UNIQUE_TEST_MSSQL_URL=mssql://sa:...@localhost:1433/master \\
    pytest tests/integration/test_mediawiki_live.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from helpers.live_validation import make_validator

from unique.core.transpiler import transpile

_URLS = {
    "tsql": os.environ.get("UNIQUE_TEST_MSSQL_URL"),
    "oracle": os.environ.get("UNIQUE_TEST_ORACLE_URL"),
    "postgresql": os.environ.get("UNIQUE_TEST_PG_URL"),
    "mysql": os.environ.get("UNIQUE_TEST_MYSQL_URL"),
}
_LIVE_TARGETS = ["tsql", "oracle", "mysql", "postgresql"]

_MW_DIR = Path(__file__).parent.parent / "fixtures" / "real_world" / "mediawiki"
_SCHEMAS = [
    ("mysql-tables.sql", "mysql"),
    ("postgres-tables.sql", "postgresql"),
    ("sqlite-tables.sql", "sqlite"),
]

# Green live: mysql -> {postgresql, oracle, tsql} and sqlite -> postgresql.
# The remaining pairs all reduce to one *intrinsic* impedance (see
# docs/03-unsupported.md): the PostgreSQL/SQLite schemas index columns declared
# as unbounded TEXT/BLOB, and MySQL/SQL Server/Oracle cannot index an unbounded
# binary/text column (MediaWiki's own MySQL schema uses VARBINARY(255) for
# exactly these). Not a transpiler bug — a source-schema/target-engine mismatch.
_KNOWN_GAPS = {
    ("postgresql", "mysql"),
    ("postgresql", "oracle"),
    ("postgresql", "tsql"),
    ("sqlite", "mysql"),
    ("sqlite", "oracle"),
    ("sqlite", "tsql"),
}


def _validator_or_skip(dialect: str):  # type: ignore[no-untyped-def]
    url = _URLS.get(dialect)
    if not url:
        pytest.skip(f"{dialect} validator not configured (set the env var)")
    try:
        return make_validator(dialect, url)
    except ImportError as e:  # pragma: no cover - driver not installed
        pytest.skip(f"driver for {dialect} not installed: {e}")
    except Exception as e:  # pragma: no cover - engine not reachable
        pytest.skip(f"could not connect to {dialect} engine: {e}")


@pytest.mark.parametrize("target", _LIVE_TARGETS)
@pytest.mark.parametrize("fixture,source", _SCHEMAS)
def test_mediawiki_schema_executes_live(fixture: str, source: str, target: str) -> None:
    if source == target:
        pytest.skip("no transpilation needed")
    if (source, target) in _KNOWN_GAPS:
        pytest.skip(f"{source}->{target}: documented MediaWiki gap (see TODO)")
    validator = _validator_or_skip(target)
    try:
        out = transpile((_MW_DIR / fixture).read_text(encoding="utf-8"), source, target)
        verdict = validator.validate(out.sql)
        assert verdict.ok, (
            f"MediaWiki {source} -> {target} failed to execute live:\n"
            f"Engine error: {verdict.error}"
        )
    finally:
        validator.close()
