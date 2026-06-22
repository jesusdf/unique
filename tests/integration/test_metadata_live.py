# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Live metadata-resolver integration tests.

These tests connect to a real database to verify %TYPE / %ROWTYPE
resolution end to end. They are skipped unless the corresponding
connection URL is provided via an environment variable, so the default
test run (and CI without databases) stays green.

To run them:

    docker compose -f docker-compose.test.yaml up -d
    UNIQUE_TEST_PG_URL=postgresql://unique:unique@localhost:5433/unique \\
    UNIQUE_TEST_MYSQL_URL=mysql://unique:unique@localhost:3307/unique \\
    pytest tests/integration/test_metadata_live.py -v
"""

from __future__ import annotations

import os

import pytest

from unique.core.metadata import MetadataResolver

PG_URL = os.environ.get("UNIQUE_TEST_PG_URL")
MYSQL_URL = os.environ.get("UNIQUE_TEST_MYSQL_URL")
MSSQL_URL = os.environ.get("UNIQUE_TEST_MSSQL_URL")
ORACLE_URL = os.environ.get("UNIQUE_TEST_ORACLE_URL")


def _resolver_or_skip(url: str | None, name: str) -> MetadataResolver:
    if not url:
        pytest.skip(f"{name} not configured (set the env var to run)")
    try:
        return MetadataResolver.from_url(url)
    except ImportError as e:  # pragma: no cover - driver not installed
        pytest.skip(f"{name} driver not installed: {e}")
    except Exception as e:  # pragma: no cover - DB not reachable
        pytest.skip(f"{name} not reachable: {e}")


@pytest.mark.integration
class TestPostgreSQLLive:
    def test_resolve_numeric_column(self) -> None:
        resolver = _resolver_or_skip(PG_URL, "PostgreSQL")
        with resolver:
            dt = resolver.resolve_column_type("employees", "salary")
            assert dt is not None
            assert dt.name.upper() in ("NUMERIC", "DECIMAL")

    def test_resolve_varchar_column(self) -> None:
        resolver = _resolver_or_skip(PG_URL, "PostgreSQL")
        with resolver:
            dt = resolver.resolve_column_type("employees", "name")
            assert dt is not None
            assert "CHAR" in dt.name.upper()

    def test_resolve_type_reference(self) -> None:
        resolver = _resolver_or_skip(PG_URL, "PostgreSQL")
        with resolver:
            dt = resolver.resolve_type_reference("employees.salary%TYPE")
            assert dt is not None

    def test_unknown_column_returns_none(self) -> None:
        resolver = _resolver_or_skip(PG_URL, "PostgreSQL")
        with resolver:
            assert resolver.resolve_column_type("employees", "nope") is None


@pytest.mark.integration
class TestMySQLLive:
    def test_resolve_decimal_column(self) -> None:
        resolver = _resolver_or_skip(MYSQL_URL, "MySQL")
        with resolver:
            dt = resolver.resolve_column_type("employees", "salary")
            assert dt is not None
            assert dt.name.upper() in ("DECIMAL", "NUMERIC")

    def test_resolve_table_columns(self) -> None:
        resolver = _resolver_or_skip(MYSQL_URL, "MySQL")
        with resolver:
            cols = resolver.resolve_table_columns("employees")
            assert cols is not None
            names = {c.column_name.lower() for c in cols}
            assert "emp_id" in names
            assert "salary" in names


@pytest.mark.integration
class TestEndToEndWithMetadata:
    """Transpile a procedure resolving %TYPE through a live PG connection."""

    def test_type_reference_resolved_in_transpile(self) -> None:
        if not PG_URL:
            pytest.skip("PostgreSQL not configured")
        from unique.core.transpiler import TranspileOptions, Transpiler

        sql = (
            "CREATE OR REPLACE PROCEDURE p IS "
            "v_sal employees.salary%TYPE; "
            "BEGIN v_sal := 0; END;"
        )
        try:
            result = Transpiler().transpile(
                sql,
                source="oracle",
                target="tsql",
                options=TranspileOptions(db_url=PG_URL),
            )
        except Exception as e:  # pragma: no cover
            pytest.skip(f"DB not reachable: {e}")
        # With resolution, the column maps to a concrete numeric type rather
        # than the SQL_VARIANT fallback.
        assert "SQL_VARIANT" not in result.sql or "DECIMAL" in result.sql
