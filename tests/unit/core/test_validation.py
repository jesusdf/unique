# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Source-syntax validation (unique.core.validation)."""

from __future__ import annotations

from unique.core.validation import validate_source


class TestValidateSource:
    def test_valid_sql_has_no_issues(self) -> None:
        sql = "SELECT * FROM t WHERE x = 1\nGO\nINSERT INTO u VALUES (1)"
        assert validate_source(sql, "tsql") == []

    def test_unclosed_paren_reported_with_line(self) -> None:
        issues = validate_source("SELECT 1\nGO\nSELECT * FROM (SELECT 1", "tsql")
        assert len(issues) == 1
        assert issues[0].line == 3
        assert "Expecting )" in issues[0].message

    def test_create_procedure_without_go_is_reported(self) -> None:
        # A CREATE PROCEDURE must start its own batch (a missing GO). It is reported
        # at the CREATE PROCEDURE line rather than silently mistranspiled.
        issues = validate_source(
            "INSERT INTO t (a) VALUES (1)\nCREATE PROCEDURE p AS BEGIN SELECT 1 END",
            "tsql",
        )
        assert len(issues) == 1
        assert issues[0].line == 2
        assert "CREATE PROCEDURE" in issues[0].snippet

    def test_sqlplus_prompt_is_not_a_syntax_error(self) -> None:
        assert validate_source("PROMPT loading data\nGO\nSELECT 1", "tsql") == []

    def test_transpiler_handled_construct_not_flagged(self) -> None:
        # Constructs the transpiler preprocesses (sqlglot Command-fallbacks them, no
        # raise) must not be reported as syntax errors.
        for sql in (
            "ALTER TABLE t ALTER COLUMN c VARCHAR(100) NULL",
            "CREATE TABLE t (a INT) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]",
            "CREATE PROCEDURE p @x INT AS BEGIN SET @x = 1 END",
        ):
            assert validate_source(sql, "tsql") == [], sql

    def test_issue_str_is_human_readable(self) -> None:
        (issue,) = validate_source("SELECT FROM WHERE", "tsql")
        text = str(issue)
        assert "line 1" in text and "<Token" not in text

    def test_procedural_control_flow_not_flagged(self) -> None:
        # BEGIN TRY / batch BEGIN…END / IF…ELSE are valid T-SQL that sqlglot
        # cannot parse — they must not be reported as syntax errors.
        for sql in (
            "BEGIN TRANSACTION\nBEGIN TRY\n  UPDATE t SET x = 1\n"
            "END TRY\nBEGIN CATCH\nEND CATCH",
            "IF 1 = 1 PRINT 'hi' ELSE PRINT 'bye'",
            "WHILE @i < 10 BEGIN SET @i = @i + 1 END",
        ):
            assert validate_source(sql, "tsql") == [], sql

    def test_multi_statement_batch_not_flagged(self) -> None:
        # Two statements in one batch with no semicolon between them is valid
        # T-SQL that sqlglot cannot parse as a unit — not a syntax error.
        sql = "SELECT a FROM t\nUPDATE t SET a = 1 WHERE a IS NULL"
        assert validate_source(sql, "tsql") == []

    def test_garbage_is_flagged(self) -> None:
        # sqlglot leniently parses a bare token as a Column and errors on multi-word
        # junk; both are garbage, not valid SQL, and must be reported.
        assert validate_source("asdfnjkasdjkasdjkasf", "tsql")
        assert validate_source("asdf jkl qwer zxcv", "tsql")
        assert validate_source("42", "tsql")

    def test_commented_out_procedure_not_flagged(self) -> None:
        # A CREATE PROCEDURE inside a block comment is not real code; the missing-GO
        # heuristic must see through the (unclosed-in-slice) comment.
        sql = "/*\nSELECT 1\nCREATE PROCEDURE p AS BEGIN SELECT 1 END\n*/\nSELECT 2"
        assert validate_source(sql, "tsql") == []
