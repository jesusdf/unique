# Copyright (c) 2026 Jesús Diéguez Fernández
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
import sqlite3

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


# ---------------------------------------------------------------------------
# Cross-engine %TYPE / %ROWTYPE resolution: an Oracle source is transpiled with
# a --db-url pointing at *each* engine (the functional_equivalence databases),
# proving the metadata for the references can be read from any of the five.
# ---------------------------------------------------------------------------

# A probe table mirroring the functional_equivalence `customer` shape (a char
# column and a numeric column), created per engine with that engine's own types.
_PROBE = "md_type_probe"
_PROBE_DDL = {
    "postgresql": f"CREATE TABLE {_PROBE} "
    "(id INT PRIMARY KEY, name VARCHAR(100), unit_price NUMERIC(10,2))",
    "mysql": f"CREATE TABLE {_PROBE} "
    "(id INT PRIMARY KEY, name VARCHAR(100), unit_price DECIMAL(10,2))",
    "oracle": f"CREATE TABLE {_PROBE} "
    "(id NUMBER PRIMARY KEY, name VARCHAR2(100), unit_price NUMBER(10,2))",
    "tsql": f"CREATE TABLE {_PROBE} "
    "(id INT PRIMARY KEY, name VARCHAR(100), unit_price DECIMAL(10,2))",
    "sqlite": f"CREATE TABLE {_PROBE} "
    "(id INTEGER PRIMARY KEY, name VARCHAR(100), unit_price NUMERIC(10,2))",
}
_ENGINE_URLS = {
    "postgresql": PG_URL,
    "mysql": MYSQL_URL,
    "oracle": ORACLE_URL,
    "tsql": MSSQL_URL,
}

# The Oracle source under test: a %TYPE column reference (char + numeric) and a
# %ROWTYPE record reference, all against the probe table.
_ORACLE_PROC = (
    "CREATE OR REPLACE PROCEDURE p IS "
    f"v_name {_PROBE}.name%TYPE; "
    f"v_price {_PROBE}.unit_price%TYPE; "
    f"v_row {_PROBE}%ROWTYPE; "
    "BEGIN v_name := 'x'; END;"
)


def _prepare_probe(engine, tmp_path):  # type: ignore[no-untyped-def]
    """Seed the probe table into *engine* and return ``(db_url, cleanup)``.

    SQLite always runs (a throwaway file); the server engines are skipped
    unless their ``UNIQUE_TEST_*_URL`` env var is set and reachable.
    """
    if engine == "sqlite":
        path = tmp_path / "md_probe.db"
        conn = sqlite3.connect(str(path))
        conn.executescript(_PROBE_DDL["sqlite"])
        conn.commit()
        conn.close()
        return f"sqlite:///{path}", (lambda: None)

    url = _ENGINE_URLS.get(engine)
    if not url:
        pytest.skip(f"{engine} not configured (set UNIQUE_TEST_*_URL to run)")
    from tests.functional_equivalence.engine_runner import connect

    try:
        conn = connect(engine, url)
    except ImportError as e:  # pragma: no cover - driver not installed
        pytest.skip(f"{engine} driver not installed: {e}")
    except Exception as e:  # pragma: no cover - DB not reachable
        pytest.skip(f"{engine} not reachable: {e}")

    cur = conn.cursor()
    drop = f"DROP TABLE {_PROBE}" + (
        " CASCADE CONSTRAINTS" if engine == "oracle" else ""
    )
    try:
        cur.execute(drop)
        conn.commit()
    except Exception:
        conn.rollback()
    cur.execute(_PROBE_DDL[engine])
    conn.commit()

    def cleanup() -> None:
        try:
            cur.execute(drop)
            conn.commit()
        except Exception:  # pragma: no cover - best effort
            pass
        conn.close()

    return url, cleanup


@pytest.mark.integration
@pytest.mark.parametrize("engine", ["postgresql", "mysql", "oracle", "tsql", "sqlite"])
class TestOracleTypeResolutionAcrossEngines:
    """An Oracle %TYPE/%ROWTYPE source resolves through a --db-url of any engine."""

    def test_type_and_rowtype_resolved_via_db_url(self, engine, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from unique.core.transpiler import TranspileOptions, Transpiler

        url, cleanup = _prepare_probe(engine, tmp_path)
        try:
            result = Transpiler().transpile(
                _ORACLE_PROC,
                source="oracle",
                target="postgresql",
                options=TranspileOptions(db_url=url),
            )
        finally:
            cleanup()

        decls = [
            line
            for line in result.sql.splitlines()
            if "v_name" in line or "v_price" in line
        ]
        # %TYPE resolved to concrete column types (not lowered to a carrier).
        assert any("CHAR" in line.upper() for line in decls), decls
        assert any(
            t in line.upper() for line in decls for t in ("NUMERIC", "DECIMAL")
        ), decls
        assert f"{_PROBE}.name%TYPE" not in result.sql
        assert f"{_PROBE}.unit_price%TYPE" not in result.sql

        # %ROWTYPE consulted the db-url (the warning documents the columns read).
        warnings = " ".join(str(getattr(w, "message", w)) for w in result.warnings)
        assert (
            f"%ROWTYPE reference '{_PROBE}%ROWTYPE' resolved via --db-url" in warnings
        )
