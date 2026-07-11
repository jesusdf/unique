# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the shared statement splitter (tests/helpers/sql_split.py).

One splitter serves the FE engine runner, the live validators and the validity
sweep. The E1 cases (audit 2026-07-08 doc 03) are the regression core: the old
per-module splitters broke on ';' or '--' inside string literals, silently
mis-splitting any script whose data contained them.
"""

from __future__ import annotations

from tests.helpers.sql_split import split_statements


class TestSemicolonQuoteAwareness:
    """E1 regressions: separators inside literals must not split."""

    def test_semicolon_inside_string_does_not_split(self) -> None:
        sql = "INSERT INTO t (v) VALUES ('A=1;B=0');\nSELECT 1;"
        stmts = split_statements(sql, "mysql")
        assert len(stmts) == 2
        assert stmts[0] == "INSERT INTO t (v) VALUES ('A=1;B=0')"
        assert stmts[1] == "SELECT 1"

    def test_doubled_quote_escape_keeps_string_closed(self) -> None:
        sql = "INSERT INTO t (v) VALUES ('it''s;fine');\nSELECT 1;"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2
        assert "it''s;fine" in stmts[0]

    def test_line_comment_marker_inside_string_survives(self) -> None:
        sql = "INSERT INTO t (v) VALUES ('a--b;c');\nSELECT 1;"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2
        assert "'a--b;c'" in stmts[0]

    def test_semicolon_inside_line_comment_does_not_split(self) -> None:
        sql = "SELECT 1 -- trailing; not a separator\nFROM t;\nSELECT 2;"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2

    def test_semicolon_inside_block_comment_does_not_split(self) -> None:
        sql = "SELECT 1 /* a;b */ FROM t;\nSELECT 2;"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2

    def test_mysql_backslash_escaped_quote(self) -> None:
        # MySQL's default sql_mode treats \' as an escaped quote inside a
        # string; the splitter must not see the string as closed there.
        sql = r"INSERT INTO t (v) VALUES ('a\';b');" + "\nSELECT 1;"
        stmts = split_statements(sql, "mysql")
        assert len(stmts) == 2
        assert stmts[1] == "SELECT 1"

    def test_backslash_is_literal_outside_mysql(self) -> None:
        # PostgreSQL standard strings: backslash is a plain character; the
        # quote after it closes the string.
        sql = "INSERT INTO t (v) VALUES ('a\\');\nSELECT 1;"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2


class TestDialectShapes:
    def test_tsql_splits_on_go_lines_only(self) -> None:
        sql = "SELECT 'GO' AS g\nGO\nSELECT 2\nGO\n"
        stmts = split_statements(sql, "tsql")
        assert len(stmts) == 2
        assert "'GO'" in stmts[0]

    def test_pg_dollar_quoted_body_stays_whole(self) -> None:
        sql = (
            "CREATE OR REPLACE FUNCTION f() RETURNS trigger LANGUAGE plpgsql "
            "AS $$\nBEGIN\n    SELECT 1;\n    SELECT 2;\nEND;\n$$;\n"
            "SELECT 3;"
        )
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2
        assert "SELECT 1;" in stmts[0] and "SELECT 2;" in stmts[0]

    def test_mysql_delimiter_block_is_one_statement(self) -> None:
        sql = (
            "CREATE TABLE t (id INT);\n"
            "DELIMITER $$\n"
            "CREATE PROCEDURE p()\nBEGIN\n    SELECT 1;\nEND$$\n"
            "DELIMITER ;\n"
            "INSERT INTO t VALUES (1);\n"
        )
        stmts = split_statements(sql, "mysql")
        assert len(stmts) == 3
        assert stmts[1].startswith("CREATE PROCEDURE p()")
        assert all("DELIMITER" not in s.upper() for s in stmts)

    def test_oracle_slash_terminates_block(self) -> None:
        sql = (
            "CREATE TABLE t (id NUMBER(10));\n"
            "BEGIN\n    INSERT INTO t VALUES (1);\nEND;\n/\n"
            "SELECT 1 FROM dual;\n"
        )
        stmts = split_statements(sql, "oracle")
        assert len(stmts) == 3
        assert stmts[1].startswith("BEGIN")
        assert stmts[1].rstrip().endswith("END;")

    def test_oracle_leading_comment_keeps_plsql_block_whole(self) -> None:
        sql = "-- header\nBEGIN\n    NULL;\n    NULL;\nEND;\n/\n"
        stmts = split_statements(sql, "oracle")
        assert len(stmts) == 1
        assert "NULL;" in stmts[0]

    def test_identifier_containing_begin_or_end_does_not_desync_depth(self) -> None:
        # 'trend' contains END and 'xbegin' ends with BEGIN; neither is the
        # keyword, so the ';' after each must still split.
        sql = "SELECT trend FROM t;\nUPDATE t SET xbegin = 1;\nSELECT 2;"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 3


class TestTransactionalBegin:
    """PostgreSQL's transactional ``BEGIN;`` / ``BEGIN TRANSACTION;`` is not
    a block opener: treating it as BEGIN…END depth glued 78% of the PG
    regression corpus into one 475k-char pseudo-statement (2026-07-11)."""

    def test_bare_begin_semicolon_does_not_open_a_block(self) -> None:
        out = split_statements("begin;\nselect 1;\n-- don't\nselect 2;", "postgresql")
        assert len(out) == 3, out

    def test_begin_transaction_and_work(self) -> None:
        out = split_statements(
            "BEGIN TRANSACTION;\nselect 1;\nCOMMIT;\nBEGIN WORK;\nselect 2;\nCOMMIT;",
            "postgresql",
        )
        assert len(out) == 6, out

    def test_do_block_begin_still_tracks_depth(self) -> None:
        out = split_statements(
            "DO $$\nBEGIN\n  UPDATE t SET a = 1;\nEND $$;\nselect 9;",
            "postgresql",
        )
        assert len(out) == 2, out
