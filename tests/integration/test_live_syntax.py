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
    # --- standalone DML/DDL constructs from the 2026-07-02 audit (S1/S2),
    # validated live so the emitter's output is confirmed against each engine.
    # S1-10: a CURRENT_TIMESTAMP DDL default (T-SQL TIMESTAMP is ROWVERSION, so
    # this also confirms the DATETIME2 remap).
    (
        "postgresql",
        "CREATE TABLE t (id INT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        _ALL,
    ),
    # S1-9: a boolean literal default (T-SQL BIT DEFAULT 1, MySQL TINYINT).
    ("postgresql", "CREATE TABLE t (active BOOLEAN DEFAULT TRUE)", _ALL),
    # A CHECK constraint must survive to every engine.
    ("tsql", "CREATE TABLE t (n INT CHECK (n > 0))", _ALL),
    # S1-2: Oracle ``(+)`` outer join -> LEFT/RIGHT OUTER JOIN … ON.
    (
        "oracle",
        "CREATE TABLE a (id INT); CREATE TABLE b (id INT); "
        "SELECT a.id FROM a, b WHERE a.id = b.id(+)",
        _ALL,
    ),
    # S1-5: ROWNUM row-limit -> LIMIT / FETCH FIRST / TOP.
    ("oracle", "CREATE TABLE t (x INT); SELECT x FROM t WHERE ROWNUM <= 5", _ALL),
    # S1-7: ILIKE -> each engine's case-insensitive match.
    (
        "postgresql",
        "CREATE TABLE t (name VARCHAR(50)); SELECT name FROM t WHERE name ILIKE 'a%'",
        _ALL,
    ),
    # S1-8 / S2-1: GROUP_CONCAT <-> STRING_AGG <-> LISTAGG.
    (
        "mysql",
        "CREATE TABLE t (name VARCHAR(50)); "
        "SELECT GROUP_CONCAT(name SEPARATOR ',') AS c FROM t",
        _ALL,
    ),
    (
        "postgresql",
        "CREATE TABLE t (name VARCHAR(50)); SELECT STRING_AGG(name, ',') AS c FROM t",
        _ALL,
    ),
    # S1-4: DATEADD -> DATE_ADD / interval arithmetic.
    ("tsql", "CREATE TABLE t (d DATE); SELECT DATEADD(day, 7, d) AS d2 FROM t", _ALL),
    # S1-1: identifier quoting translated (a reserved word as an identifier).
    ("mysql", "CREATE TABLE `order` (`id` INT); SELECT `id` FROM `order`", _ALL),
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
        # The Oracle validator queries USER_ERRORS (Oracle compiles PL/SQL
        # lazily) and recompiles to settle forward dependencies; the full
        # procedures fixture now transpiles to valid Oracle.
        assert verdict.ok, (
            f"tsql -> {target} procedures fixture is invalid:\n"
            f"Engine error: {verdict.error}"
        )
    finally:
        validator.close()


def test_pg_result_set_proc_call_returns_rows_live() -> None:
    """B56: a T-SQL result-set procedure (bare ``SELECT``) transpiled to
    PostgreSQL must be *callable*, not merely compilable — the bare ``SELECT``
    becomes an ``INOUT refcursor`` the caller ``FETCH``es. The compile-only
    gate passes the old bare-SELECT form, which throws SQLSTATE 42601 ("query
    has no destination for result data") at CALL. So this test CALLs the
    procedure with a bound cursor portal and reads the rows back, comparing
    them against the source's result set."""
    url = _URLS.get("postgresql")
    if not url:
        pytest.skip("postgresql validator not configured (set the env var)")
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover - driver not installed
        pytest.skip(f"psycopg not installed: {e}")

    tsql = (
        "CREATE PROCEDURE dbo.unq_b56 @a INT AS BEGIN "
        "SELECT @a AS x, @a + 1 AS y; END"
    )
    out = transpile(tsql, "tsql", "postgresql").sql
    assert "INOUT result_cursor refcursor" in out, out
    assert "OPEN result_cursor FOR" in out, out
    drop = "DROP PROCEDURE IF EXISTS unq_b56(int, refcursor)"
    try:
        conn = psycopg.connect(url, autocommit=True)
    except Exception as e:  # pragma: no cover - engine not reachable
        pytest.skip(f"could not connect to postgresql engine: {e}")
    try:
        with conn.cursor() as cur:
            cur.execute(drop)  # clear a prior crash's leftover
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(out)
            # A refcursor portal lives only inside its transaction; bind a name
            # in and FETCH the rows the procedure OPENed.
            cur.execute("CALL unq_b56(5, 'unq_b56_rc')")
            cur.execute("FETCH ALL FROM unq_b56_rc")
            rows = cur.fetchall()
        conn.rollback()
        assert rows == [(5, 6)], f"expected [(5, 6)], got {rows}\n{out}"
    finally:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(drop)
        conn.close()


def test_oracle_validator_catches_lazy_invalid_procedure() -> None:
    """The Oracle validator must fail an object that CREATE's but compiles
    INVALID (Oracle's lazy PL/SQL compilation) — not just an execute error."""
    validator = _validator_or_skip("oracle")
    try:
        # IF EXISTS(subquery) is invalid in PL/SQL (PLS-00204); CREATE still
        # succeeds and leaves the procedure INVALID.
        bad = (
            "CREATE OR REPLACE PROCEDURE unq_lazy_bad AS BEGIN "
            "IF EXISTS (SELECT NULL FROM dual) THEN NULL; END IF; END;\n/"
        )
        assert not validator.validate(bad).ok, "lazy-INVALID proc must not pass"
        good = "CREATE OR REPLACE PROCEDURE unq_lazy_ok AS BEGIN NULL; END;\n/"
        assert validator.validate(good).ok, "a valid proc must still pass"
    finally:
        validator.close()


def test_oracle_native_boolean_var_is_valid_live() -> None:
    """B45: a pg-source PL/SQL BOOLEAN variable transpiled to Oracle must
    keep TRUE/FALSE in its initializer, a parameter default, an assignment
    and a comparison — folding to 1/0 there is PLS-00382 (Oracle's native
    BOOLEAN rejects a NUMBER value), and the previous fold compiled this
    live INVALID. Live-verified via USER_ERRORS (Oracle compiles PL/SQL
    lazily, so a mere CREATE succeeding is not proof of validity)."""
    validator = _validator_or_skip("oracle")
    try:
        src = (
            "create function unq_b45_f(p boolean default true) "
            "returns boolean language plpgsql as $$\n"
            "declare b boolean := true;\n"
            "begin\n"
            "  b := false;\n"
            "  if b = true then\n    b := p;\n  end if;\n"
            "  return b;\nend $$;"
        )
        out = transpile(src, "postgresql", "oracle").sql
        assert "TRUE" in out, out
        assert ":= 1" not in out and "= 1" not in out, out
        verdict = validator.validate(out)
        assert (
            verdict.ok
        ), f"invalid Oracle output:\n{out}\nEngine error: {verdict.error}"
    finally:
        validator.close()
