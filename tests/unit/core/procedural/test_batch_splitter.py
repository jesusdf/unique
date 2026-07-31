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

    def test_top_level_begin_try_is_procedural(self) -> None:
        # A batch-level ``BEGIN TRY … END TRY BEGIN CATCH … END CATCH`` (common
        # in migration scripts) is procedural control flow: route it to the
        # procedural engine so the TRY/CATCH is lowered per target (PG DO $$
        # EXCEPTION, Oracle BEGIN EXCEPTION), not mangled by the DML pipeline.
        sql = (
            "BEGIN TRY\n"
            "    INSERT INTO t (id) VALUES (1)\n"
            "END TRY\n"
            "BEGIN CATCH\n"
            "    INSERT INTO log_t (msg) VALUES (ERROR_MESSAGE())\n"
            "END CATCH"
        )
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_top_level_begin_try_with_leading_comment_is_procedural(self) -> None:
        # A leading comment must not defeat the recognizer (comments are trivia,
        # stripped before classification).
        sql = (
            "/* guard */\nBEGIN TRY\nSELECT 1\nEND TRY\n"
            "BEGIN CATCH\nSELECT 2\nEND CATCH"
        )
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_begin_transaction_then_try_is_procedural(self) -> None:
        # The common migration idiom opens the transaction BEFORE the TRY
        # (``BEGIN TRANSACTION`` then ``BEGIN TRY``). The prefix must not
        # defeat the recognizer (user report 2026-07-29: the whole batch
        # degraded to a comment carrier and the guarded UPDATE was lost).
        for opener in ("BEGIN TRANSACTION", "BEGIN TRAN", "BEGIN TRANSACTION;"):
            sql = (
                f"{opener}\n\n"
                "BEGIN TRY\n"
                "    UPDATE t SET x = 1\n"
                "    COMMIT TRANSACTION\n"
                "END TRY\n"
                "BEGIN CATCH\n"
                "    ROLLBACK TRANSACTION\n"
                "END CATCH"
            )
            assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL, opener

    def test_begin_transaction_without_try_not_reclassified(self) -> None:
        # A plain transactional DML batch (no TRY) keeps its current routing;
        # the new prefix tolerance is scoped to the TRY/CATCH idiom.
        sql = "BEGIN TRANSACTION\nUPDATE t SET x = 1\nCOMMIT TRANSACTION"
        assert classify_batch(sql, "tsql") != BatchType.PROCEDURAL

    def test_begin_try_only_recognized_for_tsql(self) -> None:
        # ``BEGIN TRY`` is a T-SQL-only construct; the recognizer must not fire
        # for other source dialects (they never emit it).
        sql = "BEGIN TRY\nSELECT 1\nEND TRY\nBEGIN CATCH\nSELECT 2\nEND CATCH"
        assert classify_batch(sql, "postgresql") != BatchType.PROCEDURAL
        assert classify_batch(sql, "mysql") != BatchType.PROCEDURAL

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


class TestOracleSplitLineCreateHeader:
    """`create or replace\\nPROCEDURE …` (keywords on separate lines, common
    in codegen'd scripts) must still enter PL/SQL mode — the line-bound head
    regex missed it and the splitter cut the routine at each declaration ';'
    (audit 2026-07-08 D9; ~170 statements on the real dump)."""

    _SQL = (
        "create or replace \n"
        "PROCEDURE my_proc(\n"
        "-- <codegen>\n"
        "--   <nombre>x</nombre>\n"
        "-- </codegen>\n"
        "\tp_a  \tt1.c1%TYPE\n"
        ")\n"
        "AS\n"
        "\tv_x  \tt1.c3%TYPE;\n"
        "\tv_y  \tt1.c4%TYPE;\n"
        "BEGIN\n"
        "\tSELECT c3 INTO v_x FROM t1 WHERE c1 = p_a;\n"
        "END my_proc;\n"
        "/\n"
    )

    def test_whole_routine_is_one_procedural_batch(self) -> None:
        batches = BatchSplitter.split(self._SQL, "oracle")
        executable = [b for b in batches if b.batch_type != BatchType.COMMENT]
        assert len(executable) == 1, [b.sql[:40] for b in executable]
        b = executable[0]
        assert b.batch_type == BatchType.PROCEDURAL
        assert "v_y" in b.sql and "END my_proc" in b.sql


class TestOracleCommentBlindHeadWindow:
    """B44: ``plsql_start.search(head_window)`` scanned the last 3 raw source
    lines verbatim, so a comment merely *mentioning* ``CREATE PROCEDURE``
    (a codegen header quoting old/deprecated code, an explanatory note)
    tripped PL/SQL mode exactly like the real construct would — folding the
    following, unrelated ``;``-terminated statements into one batch that
    then waits forever for a lone ``/`` that never comes.
    """

    def test_line_comment_mentioning_create_procedure_does_not_trip_plsql(
        self,
    ) -> None:
        sql = (
            "-- codegen header\n"
            "-- EXECUTE([CREATE PROCEDURE my_proc AS SELECT 1])\n"
            "SELECT 1 FROM DUAL;\n"
            "SELECT 2 FROM DUAL;\n"
        )
        batches = BatchSplitter.split(sql, "oracle")
        executable = [b for b in batches if b.batch_type != BatchType.COMMENT]
        assert len(executable) == 2, [b.sql for b in executable]
        # The leading comment attaches to the statement it precedes (a
        # comment is trivia, not a batch of its own) — the split itself, not
        # the comment's placement, is what B44 fixes.
        assert executable[0].sql.rstrip().endswith("SELECT 1 FROM DUAL")
        assert executable[1].sql.strip() == "SELECT 2 FROM DUAL"

    def test_block_comment_mentioning_create_procedure_does_not_trip_plsql(
        self,
    ) -> None:
        sql = (
            "/* CREATE PROCEDURE legacy_proc is deprecated */\n"
            "SELECT 1 FROM DUAL;\n"
            "SELECT 2 FROM DUAL;\n"
        )
        batches = BatchSplitter.split(sql, "oracle")
        executable = [b for b in batches if b.batch_type != BatchType.COMMENT]
        assert len(executable) == 2, [b.sql for b in executable]
        assert executable[0].sql.rstrip().endswith("SELECT 1 FROM DUAL")
        assert executable[1].sql.strip() == "SELECT 2 FROM DUAL"

    def test_real_create_procedure_still_trips_plsql(self) -> None:
        # Neighbor test: the fix must not make the splitter comment-blind to
        # a REAL PL/SQL head — only to one that exists solely inside a
        # comment.
        sql = "CREATE PROCEDURE p AS\nBEGIN\n  NULL;\nEND;\n/\n"
        batches = BatchSplitter.split(sql, "oracle")
        executable = [b for b in batches if b.batch_type != BatchType.COMMENT]
        assert len(executable) == 1, [b.sql for b in executable]
        assert "BEGIN" in executable[0].sql and "END" in executable[0].sql


class TestPostgresqlDollarQuoteCommentAware:
    """B42 follow-up: ``_split_postgresql``'s dollar-quote closing-tag search
    used a blind ``str.find`` that does not skip ``--`` comments/string
    literals, unlike its sibling scanners (``similarity.py``'s
    ``_find_close_tag`` already guards against exactly this). A ``$$``-shaped
    sequence sitting inside a ``--`` comment BEFORE the routine's real
    closing ``$$`` matched as the closing tag, ending the dollar-quoted body
    early and shredding the rest of the routine into orphan batches — a real,
    reproducible desync, not merely a theoretical one.
    """

    def test_dollar_like_text_in_nested_comment_does_not_close_early(self) -> None:
        sql = (
            "CREATE OR REPLACE FUNCTION f1() RETURNS INT LANGUAGE plpgsql AS $$\n"
            "BEGIN\n"
            "    -- UNIQUE-9999: some nested note mentioning $$ delimiters\n"
            "    RETURN 1;\n"
            "END;\n"
            "$$;\n"
        )
        batches = BatchSplitter.split(sql, "postgresql")
        assert len(batches) == 1, [b.sql for b in batches]
        assert batches[0].sql.rstrip().endswith("$$;"), batches[0].sql
        assert "END;" in batches[0].sql

    def test_realistic_carrier_between_two_real_functions(self) -> None:
        # The actual B42 shape: a commented-out unsupported-construct carrier
        # (its own fake $$ open/close, both inside -- lines) sitting between
        # two real dollar-quoted functions must not disturb either one.
        sql = (
            "CREATE OR REPLACE FUNCTION f1() RETURNS INT LANGUAGE plpgsql AS $$\n"
            "BEGIN\n"
            "    RETURN 1;\n"
            "END;\n"
            "$$;\n"
            "\n"
            "-- UNIQUE-1160: something degraded\n"
            "-- The non-portable translation is commented out below for review:\n"
            "-- DO $$\n"
            "-- BEGIN\n"
            "--     NULL;\n"
            "-- END $$;\n"
            "\n"
            "CREATE OR REPLACE FUNCTION f2() RETURNS INT LANGUAGE plpgsql AS $$\n"
            "BEGIN\n"
            "    RETURN 2;\n"
            "END;\n"
            "$$;\n"
        )
        batches = BatchSplitter.split(sql, "postgresql")
        assert len(batches) == 2, [b.sql for b in batches]
        assert batches[0].sql.rstrip().endswith("$$;"), batches[0].sql
        assert "FUNCTION f1" in batches[0].sql
        assert batches[1].sql.rstrip().endswith("$$;"), batches[1].sql
        assert "FUNCTION f2" in batches[1].sql
        assert "UNIQUE-1160" in batches[1].sql
