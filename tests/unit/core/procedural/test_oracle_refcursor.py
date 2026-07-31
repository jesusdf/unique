"""A T-SQL procedure that returns a result set via a bare ``SELECT`` becomes,
on Oracle, a ``SYS_REFCURSOR`` OUT parameter opened FOR that query.

This preserves the query (the caller adapts the call to read the cursor) instead
of a carrier, where the whole body would also need a manual rewrite. Validated
against real Oracle in the procedures-fixture live test.
"""

import re

from unique.core.transpiler import Transpiler

t = Transpiler()


def _oracle(tsql: str) -> str:
    return t.transpile(tsql, "tsql", "oracle").sql


class TestResultSetToRefCursor:
    def test_bare_select_becomes_open_refcursor(self) -> None:
        # (sqlglot is not a reliable PL/SQL validator — OPEN … FOR / SYS_REFCURSOR
        # are validated against a real Oracle in the procedures-fixture live test.)
        out = _oracle("CREATE PROCEDURE p AS BEGIN SELECT a, b FROM t END")
        up = out.upper()
        assert "RESULT_CURSOR OUT SYS_REFCURSOR" in up, out
        assert "OPEN RESULT_CURSOR FOR SELECT A, B FROM T" in up, out

    def test_select_in_if_is_wrapped(self) -> None:
        out = _oracle(
            "CREATE PROCEDURE p AS BEGIN IF @x > 0 BEGIN SELECT a FROM t END END"
        )
        assert "OPEN RESULT_CURSOR FOR SELECT" in out.upper(), out

    def test_multiple_result_sets_get_distinct_cursors(self) -> None:
        out = _oracle(
            "CREATE PROCEDURE p AS\nBEGIN\n"
            "    SELECT a FROM t\n"
            "    SELECT b FROM u\nEND"
        )
        up = out.upper()
        assert "RESULT_CURSOR OUT SYS_REFCURSOR" in up, out
        assert "RESULT_CURSOR_2 OUT SYS_REFCURSOR" in up, out
        assert "OPEN RESULT_CURSOR FOR" in up and "OPEN RESULT_CURSOR_2 FOR" in up, out

    def test_select_into_is_not_a_result_set(self) -> None:
        # A SELECT with INTO assigns variables; it must stay a SELECT … INTO,
        # not become a ref cursor.
        out = _oracle(
            "CREATE PROCEDURE p AS BEGIN DECLARE @v INT " "SELECT @v = a FROM t END"
        )
        assert "SYS_REFCURSOR" not in out.upper(), out
        assert "INTO" in out.upper()


def _pg_from_tsql(tsql: str) -> str:
    return t.transpile(tsql, "tsql", "postgresql").sql


class TestResultSetToRefCursorPostgres:
    """B56: a T-SQL procedure that returns a result set via a bare ``SELECT``
    becomes, on PostgreSQL, an ``INOUT refcursor`` parameter opened FOR that
    query — the same treatment Oracle gets. A bare ``SELECT`` inside a plpgsql
    procedure compiles but throws SQLSTATE 42601 ("query has no destination for
    result data") at CALL; the compile-only gate never caught it. Validated
    against real PostgreSQL in the procedures-fixture live test."""

    def test_bare_select_becomes_open_refcursor(self) -> None:
        out = _pg_from_tsql("CREATE PROCEDURE p AS BEGIN SELECT a, b FROM t END")
        low = out.lower()
        assert "inout result_cursor refcursor" in low, out
        assert "open result_cursor for select a, b from t" in low, out
        # The runtime-invalid bare result SELECT (no destination) is gone.
        assert not re.search(r"(?im)^\s*select a, b from t", out), out

    def test_select_in_if_is_wrapped(self) -> None:
        out = _pg_from_tsql(
            "CREATE PROCEDURE p AS BEGIN IF @x > 0 BEGIN SELECT a FROM t END END"
        )
        assert "open result_cursor for select" in out.lower(), out

    def test_multiple_result_sets_get_distinct_cursors(self) -> None:
        out = _pg_from_tsql(
            "CREATE PROCEDURE p AS\nBEGIN\n"
            "    SELECT a FROM t\n"
            "    SELECT b FROM u\nEND"
        )
        low = out.lower()
        assert "inout result_cursor refcursor" in low, out
        assert "inout result_cursor_2 refcursor" in low, out
        assert (
            "open result_cursor for" in low and "open result_cursor_2 for" in low
        ), out

    def test_select_into_is_not_a_result_set(self) -> None:
        # A SELECT with INTO assigns variables; it must stay a SELECT … INTO,
        # not become a ref cursor.
        out = _pg_from_tsql(
            "CREATE PROCEDURE p AS BEGIN DECLARE @v INT " "SELECT @v = a FROM t END"
        )
        assert "refcursor" not in out.lower(), out


class TestResultSetRefcursorCallSitePostgres:
    """B56: a same-script CALL of a procedure whose signature gained an
    ``INOUT refcursor`` must gain the matching portal argument(s) and a FETCH,
    else the call keeps the old arity and fails. Mirrors the Oracle call-site
    adapter; the added cursor argument is flagged (no-silent-loss)."""

    def test_call_gains_portal_and_fetch(self) -> None:
        src = (
            "DELIMITER //\n"
            "create procedure sel1(x int)\n"
            "begin\n"
            "  select x + 1 as y;\n"
            "end//\n"
            "DELIMITER ;\n"
            "call sel1(7);\n"
        )
        res = t.transpile(src, "mysql", "postgresql")
        low = res.sql.lower()
        assert "call sel1(7, 'sel1_rc1');" in low, res.sql
        assert "fetch all from sel1_rc1;" in low, res.sql
        assert any(
            "refcursor argument" in w.message for w in res.warnings
        ), res.warnings


def _pg(oracle: str) -> object:
    return t.transpile(oracle, "oracle", "postgresql")


class TestOracleRefcursorToPostgres:
    """Oracle ``SYS_REFCURSOR`` OUT parameter → PostgreSQL ``refcursor``
    (the direct equivalent; ``OPEN v FOR <q>`` is valid PL/pgSQL). Before the
    B36 fix the bare ``SYS_REFCURSOR`` name leaked past ``_transform_data_type``
    and the output gate degraded the whole routine (UNIQUE-1151)."""

    def test_out_param_becomes_refcursor(self) -> None:
        res = _pg(
            "CREATE OR REPLACE PROCEDURE p (result_cursor OUT SYS_REFCURSOR)\n"
            "IS\nBEGIN\n    OPEN result_cursor FOR SELECT a, b FROM t;\nEND;"
        )
        up = res.sql.upper()
        assert "REFCURSOR" in up, res.sql
        assert "SYS_REFCURSOR" not in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql

    def test_local_refcursor_declaration_becomes_refcursor(self) -> None:
        res = _pg(
            "CREATE OR REPLACE PROCEDURE p\nIS\n    v_cur SYS_REFCURSOR;\n"
            "BEGIN\n    OPEN v_cur FOR SELECT a FROM t;\nEND;"
        )
        up = res.sql.upper()
        assert "SYS_REFCURSOR" not in up, res.sql
        assert "REFCURSOR" in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql
