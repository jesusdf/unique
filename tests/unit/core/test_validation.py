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


class TestBareAndTypoStatements:
    """N3: lenient parses that are not statements must be flagged."""

    def test_bare_alias_is_flagged(self) -> None:
        issues = validate_source("banana banana", "tsql")
        assert issues and "not a valid SQL statement" in issues[0].message

    def test_create_typo_kind_is_flagged(self) -> None:
        issues = validate_source("CREATE TALBE t (id INT)", "tsql")
        assert issues and "TALBE" in issues[0].message

    def test_unmodeled_but_real_kinds_stay_clean(self) -> None:
        for sql in (
            "CREATE SYNONYM s FOR t",
            "CREATE TABLE t (id INT)",
            "GRANT SELECT ON t TO u",
            "SET NOCOUNT ON",
        ):
            assert not validate_source(sql, "tsql"), sql

    def test_pg_table_shorthand_is_not_flagged(self) -> None:
        # B20/N13: PostgreSQL's ``TABLE t`` is valid shorthand for
        # ``SELECT * FROM t`` — it parses to the exact bare-Alias shape as
        # garbage ("banana banana"), so it needs a dialect-conditional
        # whitelist rather than a blanket bare-statement rejection.
        assert validate_source("TABLE t", "postgresql") == []

    def test_pg_table_shorthand_still_flagged_on_other_dialects(self) -> None:
        # No such shorthand exists outside PostgreSQL — "TABLE t" there is the
        # same garbage as "banana banana".
        for dialect in ("tsql", "oracle", "mysql"):
            issues = validate_source("TABLE t", dialect)
            assert issues and "not a valid SQL statement" in issues[0].message, dialect

    def test_banana_still_rejected_on_postgresql(self) -> None:
        # The whitelist must not open the door to arbitrary bare Alias shapes.
        issues = validate_source("banana banana", "postgresql")
        assert issues and "not a valid SQL statement" in issues[0].message

    def test_dollar_money_shaped_column_flagged_on_non_tsql(self) -> None:
        # N8/B9: ``Column(table=$12, this=Literal(50))`` is T-SQL's real
        # money-literal shorthand ($12.50) but the identical shape on a
        # dialect with no such shorthand is garbage.
        issues = validate_source("SELECT $12.50 AS price;", "oracle")
        assert issues and "not a valid column reference" in issues[0].message
        issues = validate_source("SELECT $12.50 AS price;", "mysql")
        assert issues and "not a valid column reference" in issues[0].message

    def test_dollar_money_literal_not_flagged_on_tsql(self) -> None:
        # The same shape on T-SQL IS the real money literal — valid input.
        assert validate_source("SELECT $12.50 AS price;", "tsql") == []
