# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for the batch splitter."""

from __future__ import annotations

from unique.core.batch_splitter import BatchSplitter, BatchType, classify_batch


class TestTSQLSplitting:
    def test_split_on_go(self) -> None:
        sql = "SELECT 1;\nGO\nSELECT 2;\nGO"
        batches = BatchSplitter.split(sql, "tsql")
        assert len(batches) == 2

    def test_go_not_split_inside_statement(self) -> None:
        sql = "SELECT 'GONE';"
        batches = BatchSplitter.split(sql, "tsql")
        assert len(batches) == 1

    def test_go_inside_block_comment_is_not_a_separator(self) -> None:
        # A GO on its own line inside a /* … */ block comment must not split the
        # batch — a naive line split would break the comment and transpile its
        # (commented-out) content as live code.
        sql = "/*\nGO\nCREATE TABLE t (a INT)\nGO\n*/\nSELECT 1"
        batches = [b for b in BatchSplitter.split(sql, "tsql") if not b.is_empty]
        assert len(batches) == 1
        assert "/*" in batches[0].sql and "*/" in batches[0].sql

    def test_go_inside_string_literal_is_not_a_separator(self) -> None:
        sql = "SELECT 'x\nGO\ny'\nGO\nSELECT 2"
        batches = [b for b in BatchSplitter.split(sql, "tsql") if not b.is_empty]
        assert len(batches) == 2

    def test_empty_batches_dropped(self) -> None:
        sql = "SELECT 1;\nGO\n\nGO\nSELECT 2;"
        batches = BatchSplitter.split(sql, "tsql")
        assert len(batches) == 2

    def test_print_and_set_var_are_procedural(self) -> None:
        from unique.core.batch_splitter import BatchType, classify_batch

        # PRINT and a ``SET @var = …`` assignment are procedural (converted),
        # while a session option like SET NOEXEC / ANSI_PADDING is documented.
        assert classify_batch("PRINT 'hi'", "tsql") is BatchType.PROCEDURAL
        assert classify_batch("SET @v = 5", "tsql") is BatchType.PROCEDURAL
        assert classify_batch("SET NOEXEC ON", "tsql") is BatchType.SET_OPTION
        assert classify_batch("SET ANSI_PADDING ON", "tsql") is BatchType.SET_OPTION
        assert classify_batch("SET NOCOUNT ON", "tsql") is BatchType.SET_OPTION

    def test_split_on_lowercase_go(self) -> None:
        # GO is a case-insensitive batch terminator; a lowercase ``go`` after an
        # EXEC must not be absorbed into the statement.
        sql = "EXEC myproc @a=1\ngo\nSELECT 2\nGo"
        batches = [b for b in BatchSplitter.split(sql, "tsql") if not b.is_empty]
        assert len(batches) == 2
        assert "go" not in batches[0].sql.lower()


class TestOracleSplitting:
    def test_split_on_slash(self) -> None:
        sql = "BEGIN\n  NULL;\nEND;\n/\nSELECT 1 FROM dual;\n/"
        batches = BatchSplitter.split(sql, "oracle")
        assert len(batches) == 2

    def test_split_plain_statements_on_semicolon(self) -> None:
        # A script with no slash separators must still split on semicolons.
        sql = (
            "CREATE TABLE a (id NUMBER);\n"
            "CREATE TABLE b (id NUMBER);\n"
            "CREATE INDEX i ON a (id);"
        )
        batches = [b for b in BatchSplitter.split(sql, "oracle") if not b.is_empty]
        assert len(batches) == 3
        assert all(b.batch_type == BatchType.DDL for b in batches)

    def test_plsql_block_not_split_by_inner_semicolons(self) -> None:
        sql = (
            "CREATE TABLE t (id NUMBER);\n"
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "BEGIN\n"
            "  UPDATE t SET id = 1;\n"
            "  IF id > 0 THEN NULL; END IF;\n"
            "END;\n"
            "/\n"
            "INSERT INTO t VALUES (1);"
        )
        batches = [b for b in BatchSplitter.split(sql, "oracle") if not b.is_empty]
        kinds = [b.batch_type.name for b in batches]
        assert "PROCEDURAL" in kinds
        # The procedure stays in one batch despite its inner semicolons.
        proc = [b for b in batches if b.batch_type == BatchType.PROCEDURAL]
        assert len(proc) == 1
        assert "END IF" in proc[0].sql

    def test_sqlplus_directives_kept_separate(self) -> None:
        sql = "SET FEEDBACK 1;\nSET PAGESIZE 100;\nCREATE TABLE t (id NUMBER);"
        batches = [b for b in BatchSplitter.split(sql, "oracle") if not b.is_empty]
        assert len(batches) == 3

    def test_rem_and_prompt_lines_preserved_as_comments(self) -> None:
        # SQL*Plus 'rem' / 'prompt' lines must not corrupt the following
        # statement's batch, and must be preserved as SQL comments rather
        # than dropped (they carry copyright notices, progress messages).
        sql = (
            "rem Copyright notice\n"
            "prompt Creating table...\n"
            "CREATE TABLE t (id NUMBER);"
        )
        batches = BatchSplitter.split(sql, "oracle")
        comments = [b for b in batches if b.batch_type == BatchType.COMMENT]
        assert len(comments) == 2
        assert comments[0].sql == "-- Copyright notice"
        assert comments[1].sql == "-- PROMPT: Creating table..."
        # The CREATE TABLE is its own clean DDL batch.
        ddl = [b for b in batches if b.batch_type == BatchType.DDL]
        assert len(ddl) == 1
        assert ddl[0].sql.upper().startswith("CREATE TABLE")

    def test_bare_rem_becomes_empty_comment(self) -> None:
        sql = "rem\nCREATE TABLE t (id NUMBER);"
        batches = BatchSplitter.split(sql, "oracle")
        comments = [b for b in batches if b.batch_type == BatchType.COMMENT]
        assert len(comments) == 1
        assert comments[0].sql == "--"


class TestMySQLSplitting:
    def test_delimiter_change(self) -> None:
        sql = (
            "DELIMITER //\n"
            "CREATE PROCEDURE p()\nBEGIN\n  SELECT 1;\nEND//\n"
            "DELIMITER ;"
        )
        batches = BatchSplitter.split(sql, "mysql")
        assert len(batches) >= 1
        # The procedure body should be in one batch
        assert any("CREATE PROCEDURE" in b.sql for b in batches)

    def test_routine_without_delimiter_stays_one_batch(self) -> None:
        # Without a DELIMITER change, inner semicolons must not split the
        # routine into fragments.
        sql = (
            "CREATE PROCEDURE p(IN x INT)\n"
            "BEGIN\n"
            "  DECLARE v INT DEFAULT 0;\n"
            "  SET v = x;\n"
            "  UPDATE t SET c = v WHERE id = x;\n"
            "END\n"
        )
        batches = [b for b in BatchSplitter.split(sql, "mysql") if not b.is_empty]
        assert len(batches) == 1
        assert batches[0].batch_type == BatchType.PROCEDURAL

    def test_plain_statements_still_split(self) -> None:
        sql = "INSERT INTO t VALUES (1);\nINSERT INTO t VALUES (2);"
        batches = [b for b in BatchSplitter.split(sql, "mysql") if not b.is_empty]
        assert len(batches) == 2


class TestClassification:
    def test_procedural_tsql(self) -> None:
        sql = "CREATE PROCEDURE dbo.x AS BEGIN SELECT 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_alter_procedure_is_procedural(self) -> None:
        sql = "ALTER PROCEDURE dbo.x AS BEGIN SELECT 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_procedural_oracle_with_or_replace(self) -> None:
        sql = "CREATE OR REPLACE PROCEDURE x IS BEGIN NULL; END;"
        assert classify_batch(sql, "oracle") == BatchType.PROCEDURAL

    def test_function_is_procedural(self) -> None:
        sql = "CREATE FUNCTION dbo.f() RETURNS INT AS BEGIN RETURN 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_trigger_is_procedural(self) -> None:
        sql = "CREATE TRIGGER t ON tbl AFTER INSERT AS BEGIN SELECT 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_exec_proc_is_procedural(self) -> None:
        # A standalone EXEC of a stored procedure is a procedural call (it must
        # become CALL proc(...) on the other engines), not plain DML.
        sql = "EXEC dbo.create_invoice @customer_id = 2, @new_id = @x OUTPUT"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_execute_keyword_is_procedural(self) -> None:
        sql = "EXECUTE dbo.do_thing 1, 2"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_batch_declare_is_procedural(self) -> None:
        # A batch-level DECLARE (a variable, then statements using it) is an
        # anonymous procedural block, not DML.
        sql = "DECLARE @x INT;\nEXEC dbo.p @out = @x OUTPUT;"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_exec_system_proc_not_procedural(self) -> None:
        # System stored procedures (sp_*) are handled specially by the DML
        # pipeline (documented/passed through), so they must NOT be routed to
        # the procedural engine.
        sql = "EXEC sp_addextendedproperty @name = 'x'"
        assert classify_batch(sql, "tsql") != BatchType.PROCEDURAL

    def test_dml_select(self) -> None:
        assert classify_batch("SELECT * FROM t", "tsql") == BatchType.DML

    def test_dml_insert(self) -> None:
        assert classify_batch("INSERT INTO t VALUES (1)", "tsql") == BatchType.DML

    def test_ddl_create_table(self) -> None:
        assert classify_batch("CREATE TABLE t (id INT)", "tsql") == BatchType.DDL

    def test_set_option(self) -> None:
        assert classify_batch("SET NOCOUNT ON", "tsql") == BatchType.SET_OPTION

    def test_empty(self) -> None:
        assert classify_batch("", "tsql") == BatchType.EMPTY

    def test_comment_only(self) -> None:
        assert classify_batch("-- just a comment", "tsql") == BatchType.COMMENT

    def test_block_comment_wrapping_code_is_comment(self) -> None:
        # A /* … */ block that wraps commented-out code (even a CREATE PROCEDURE)
        # is a COMMENT, not procedural — otherwise the whole block is emitted as
        # mangled procedural code (a trailing '*/;' + carrier).
        sql = "/*\nCREATE PROCEDURE p AS BEGIN SELECT 1 END\nGO\n*/"
        assert classify_batch(sql, "tsql") == BatchType.COMMENT

    def test_leading_block_comment_does_not_hide_the_statement(self) -> None:
        # A /* section header */ before a real statement must not be taken as the
        # first "statement"; the batch is classified by what follows the comment.
        assert (
            classify_batch("/* header */\nSET ANSI_NULLS ON", "tsql")
            == BatchType.SET_OPTION
        )
        assert (
            classify_batch(
                "/* header */\nIF OBJECT_ID('dbo.f', 'FN') IS NOT NULL\n"
                "  DROP FUNCTION dbo.f",
                "tsql",
            )
            == BatchType.SET_OPTION
        )


class TestBatchProperties:
    def test_is_empty_for_whitespace(self) -> None:
        batches = BatchSplitter.split("   \n  ", "tsql")
        assert all(b.is_empty for b in batches) or not batches

    def test_is_empty_for_comment_only(self) -> None:
        sql = "-- comment\n-- another"
        batches = BatchSplitter.split(sql, "tsql")
        assert all(b.is_empty for b in batches)


class TestSqlPlusSetDirectives:
    """SQL*Plus ``SET <option>`` directives (audit 2026-07-08 sweep: ~940
    invalid statements per direction on the real Oracle dump)."""

    def test_serveroutput_is_its_own_set_option_batch(self) -> None:
        # The directive is line-oriented (no ';'); it must not glue to the
        # following block and corrupt it.
        sql = "SET SERVEROUTPUT ON\nBEGIN\n  NULL;\nEND;\n/"
        batches = BatchSplitter.split(sql, "oracle")
        assert batches[0].batch_type == BatchType.SET_OPTION
        assert batches[0].sql.strip() == "SET SERVEROUTPUT ON"
        assert batches[1].batch_type == BatchType.PROCEDURAL
        assert batches[1].sql.lstrip().upper().startswith("BEGIN")

    def test_directive_with_semicolon_also_peels(self) -> None:
        batches = BatchSplitter.split("SET DEFINE OFF;\nSELECT 1 FROM DUAL;", "oracle")
        assert batches[0].batch_type == BatchType.SET_OPTION
        assert batches[1].batch_type == BatchType.DML

    def test_update_set_clause_is_not_a_directive(self) -> None:
        # A line starting with SET *inside* a statement is the UPDATE's SET
        # clause, never a SQL*Plus directive.
        sql = "UPDATE t\nSET col = 1\nWHERE id = 2;"
        batches = BatchSplitter.split(sql, "oracle")
        assert len(batches) == 1
        assert batches[0].batch_type == BatchType.DML
        assert "SET col = 1" in batches[0].sql

    def test_set_transaction_is_real_sql_not_a_directive(self) -> None:
        # SET TRANSACTION / SET CONSTRAINTS are Oracle SQL statements, not
        # SQL*Plus options; they must not be commented out as directives.
        batches = BatchSplitter.split("SET TRANSACTION READ ONLY;", "oracle")
        assert len(batches) == 1
        assert batches[0].batch_type != BatchType.SET_OPTION


class TestOracleBlockCommentAwareness:
    """A commented-out PL/SQL block (with '/' terminator lines INSIDE the
    /* */ comment) must not desync the splitter (real-dump finding,
    2026-07-09: an orphan '*/ INSERT ...' batch shipped as garbage)."""

    _SQL = (
        "/*\n"
        "BEGIN\n"
        "    NULL;\n"
        "END;\n"
        "/\n"
        "*/\n"
        "\n"
        "INSERT INTO t (id) SELECT 1 FROM DUAL "
        "WHERE NOT EXISTS (SELECT NULL FROM t WHERE id = 1);\n"
    )

    def test_slash_inside_block_comment_does_not_split(self) -> None:
        batches = BatchSplitter.split(self._SQL, "oracle")
        executable = [b for b in batches if b.batch_type != BatchType.COMMENT]
        assert len(executable) == 1
        b = executable[0]
        assert b.batch_type == BatchType.DML
        assert b.sql.lstrip().startswith(("/*", "INSERT"))
        assert "NOT EXISTS" in b.sql
        # No orphan '*/' fragment batch.
        assert not any(x.sql.lstrip().startswith("*/") for x in batches)

    def test_directive_inside_block_comment_ignored(self) -> None:
        sql = "/*\nSET SERVEROUTPUT ON\n*/\nSELECT 1 FROM DUAL;\n"
        batches = BatchSplitter.split(sql, "oracle")
        assert not any(b.batch_type == BatchType.SET_OPTION for b in batches)
