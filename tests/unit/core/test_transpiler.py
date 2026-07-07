"""Tests for the Transpiler orchestrator and convenience function."""

import re

import pytest

from unique.core.errors import UnknownDialectError
from unique.core.transpiler import Transpiler, TranspileResult, transpile


class TestTranspiler:
    def test_simple_transpile(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users",
            source="tsql",
            target="postgresql",
        )
        assert isinstance(result, TranspileResult)
        assert "SELECT" in result.sql
        assert "users" in result.sql

    def test_join_parts_glues_comment_to_next(self, transpiler: Transpiler) -> None:
        # _join_parts accumulates pieces and joins once (O(n) — a prior O(n²)
        # ``out += …`` dominated huge scripts). A comment part glues to the
        # following executable part with a newline (no batch separator), while
        # two executable parts get the target's separator.
        parts = [("-- note", True), ("SELECT 1", False), ("SELECT 2", False)]
        out = transpiler._join_parts(parts, "postgresql")
        assert out == "-- note\nSELECT 1\n\nSELECT 2"
        # T-SQL uses GO between executable parts, still no GO after the comment.
        out_tsql = transpiler._join_parts(parts, "tsql")
        assert out_tsql == "-- note\nSELECT 1\nGO\n\nSELECT 2"

    def test_repeated_lossy_statements_scale(self, transpiler: Transpiler) -> None:
        # Many identical carriers must not blow up (the carrier↔warning
        # reconciliation is now deduped per unique fragment): every occurrence is
        # still emitted, and the run completes without O(n²) reconciliation.
        stmt = "EXEC sys.sp_addextendedproperty @name=N'x', @value=N'y'"
        script = "\nGO\n".join([stmt] * 200)
        result = transpiler.transpile(script, source="tsql", target="oracle")
        # Every occurrence is preserved (none dropped by the dedup).
        assert result.sql.count("sp_addextendedproperty") >= 200

    def test_if_not_exists_create_guard_transpiles_ddl(
        self, transpiler: Transpiler
    ) -> None:
        # IF NOT EXISTS (<catalog query>) CREATE TABLE X: the catalog condition
        # has no cross-engine form, so keep the intent — transpile the CREATE.
        sql = (
            "IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'X')\n"
            "CREATE TABLE X (id INT)"
        )
        out = transpiler.transpile(sql, source="tsql", target="postgresql").sql
        assert "CREATE TABLE X" in out
        assert "-- UNIQUE:" not in out
        assert "sys.objects" not in out

    def test_if_not_exists_begin_end_with_print(self, transpiler: Transpiler) -> None:
        # A guard body opening with a diagnostic PRINT before the DDL: the PRINT
        # is dropped, the DDL transpiled (not degraded to a Command carrier).
        sql = (
            "IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'X')\n"
            "BEGIN\n    PRINT 'Creating X'\n    CREATE TABLE X (id INT)\nEND"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "CREATE TABLE X" in out
        assert "PRINT" not in out
        assert "-- UNIQUE:" not in out

    def test_if_exists_drop_guard_is_idempotent(self, transpiler: Transpiler) -> None:
        sql = "IF EXISTS (SELECT * FROM sys.objects WHERE name = 'X')\nDROP TABLE X"
        out = transpiler.transpile(sql, source="tsql", target="postgresql").sql
        assert "DROP TABLE IF EXISTS X" in out
        assert "-- UNIQUE:" not in out

    def test_if_not_exists_alter_add_column(self, transpiler: Transpiler) -> None:
        sql = (
            "IF NOT EXISTS (SELECT * FROM syscolumns WHERE id = OBJECT_ID('X') "
            "AND name = 'c')\nALTER TABLE X ADD c INT"
        )
        out = transpiler.transpile(sql, source="tsql", target="postgresql").sql
        assert "ALTER TABLE X ADD COLUMN c" in out
        assert "-- UNIQUE:" not in out

    def test_oracle_alter_add_column_is_idempotent(
        self, transpiler: Transpiler
    ) -> None:
        # A syscolumns-guarded ADD COLUMN must stay re-runnable on Oracle: add the
        # column only when user_tab_columns shows it absent (Oracle DDL cannot be
        # conditional, so via EXECUTE IMMEDIATE). Regression: the guard used to be
        # dropped, leaving a bare ALTER that fails on re-run (ORA-01430).
        sql = (
            "IF NOT EXISTS (SELECT * FROM syscolumns WHERE id = OBJECT_ID('X') "
            "AND name = 'c')\nALTER TABLE X ADD c INT"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "unique_guard" in out
        assert "user_tab_columns" in out.lower()
        assert "TABLE_NAME = 'X'" in out.upper()
        assert "COLUMN_NAME = 'C'" in out.upper()
        assert "-- UNIQUE:" not in out

    def test_oracle_alter_add_constraint_is_idempotent(
        self, transpiler: Transpiler
    ) -> None:
        # A guarded ADD CONSTRAINT (FK/PK/UNIQUE) probes user_constraints by name.
        sql = (
            "IF NOT EXISTS (SELECT * FROM sys.objects WHERE name = 'fk_x')\n"
            "ALTER TABLE X ADD CONSTRAINT fk_x FOREIGN KEY (a) REFERENCES Y (id)"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "unique_guard" in out
        assert "user_constraints" in out.lower()
        assert "CONSTRAINT_NAME = 'FK_X'" in out.upper()

    def test_block_comment_with_code_emitted_verbatim(
        self, transpiler: Transpiler
    ) -> None:
        # A /* … */ block wrapping (commented-out) procedural code is emitted
        # verbatim — no trailing '*/;' and no could-not-translate carrier.
        sql = "/*\nCREATE PROCEDURE p AS BEGIN SELECT 1 END\nGO\n*/"
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "*/;" not in out
        assert "could not translate" not in out
        assert out.strip().endswith("*/")

    def test_cte_before_insert_is_preserved(self, transpiler: Transpiler) -> None:
        # ``WITH cte AS (…) INSERT … SELECT … FROM cte`` (T-SQL's ;WITH idiom): the
        # CTE parses onto the INSERT and used to be dropped, leaving a dangling
        # ``FROM cte``. It must survive to every target.
        sql = (
            ";WITH mycte AS (SELECT 'x' AS k, 1 AS v)\n"
            "INSERT INTO t (k, v) SELECT k, v FROM mycte"
        )
        for target in ("oracle", "postgresql", "mysql"):
            out = transpiler.transpile(sql, source="tsql", target=target).sql
            assert "mycte" in out and "WITH" in out.upper(), target
            assert "INSERT INTO" in out.upper(), target

    def test_leading_semicolon_with_comment_is_not_a_carrier(
        self, transpiler: Transpiler
    ) -> None:
        # A comment before a ``;`` makes sqlglot yield an empty exp.Semicolon
        # statement; it must be dropped, not emitted as an "unhandled" carrier.
        out = transpiler.transpile(
            "/* header */\n;\nSELECT 1", source="tsql", target="oracle"
        ).sql
        assert "Unhandled expression type" not in out

    def test_leading_comments_rehomed_into_routine(
        self, transpiler: Transpiler
    ) -> None:
        # SQL Server keeps comments before CREATE PROCEDURE as part of the stored
        # module; Oracle/PostgreSQL/MySQL store a routine from CREATE on and drop
        # them, so they move inside — right after the CREATE (the declaration
        # section), before the body's declarations — to survive the round-trip.
        src = (
            "-- Autor: X\n-- Fecha: Y\n"
            "CREATE PROCEDURE dbo.p @x INT AS BEGIN SET @x = @x + 1 END"
        )
        for target in ("oracle", "postgresql", "mysql"):
            out = transpiler.transpile(src, source="tsql", target=target).sql
            # Present, and moved inside — not left dangling before the CREATE.
            assert "-- Autor: X" in out and "-- Fecha: Y" in out, target
            assert not out.lstrip().startswith("--"), target
        # On Oracle it lands in the declaration section (after the header, before
        # BEGIN), i.e. right after the CREATE rather than down in the body.
        oracle = transpiler.transpile(src, source="tsql", target="oracle").sql
        assert oracle.index("-- Autor: X") < oracle.index("BEGIN")

    def test_leading_comments_kept_before_create_for_tsql(
        self, transpiler: Transpiler
    ) -> None:
        # T-SQL preserves the pre-CREATE comments as part of the module: keep them.
        out = transpiler.transpile(
            "-- Autor: X\nCREATE PROCEDURE dbo.p @x INT AS BEGIN SET @x = 1 END",
            source="tsql",
            target="tsql",
        ).sql
        assert out.lstrip().startswith("-- Autor: X")

    def test_textimage_on_filegroup_stripped(self, transpiler: Transpiler) -> None:
        # TEXTIMAGE_ON <filegroup> (LOB storage placement) makes sqlglot fall back
        # to a Command, losing the whole CREATE TABLE; it is stripped pre-parse so
        # the table transpiles.
        sql = (
            "CREATE TABLE [S].[T] ([a] [int] NOT NULL, [b] [nvarchar](9) NULL) "
            "ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "Unhandled expression type: Command" not in out, out
        assert "CREATE TABLE" in out.upper() and "TEXTIMAGE_ON" not in out.upper()

    def test_alter_add_constraint_with_nocheck_stripped(
        self, transpiler: Transpiler
    ) -> None:
        # "ALTER TABLE t WITH NOCHECK ADD CONSTRAINT …": the WITH NOCHECK modifier
        # makes sqlglot fall back to a Command; it is stripped so the constraint
        # transpiles (with a warning that the target validates existing rows).
        sql = "ALTER TABLE [S].[T] WITH NOCHECK ADD CONSTRAINT [c] CHECK (([x] > 0))"
        result = transpiler.transpile(sql, source="tsql", target="oracle")
        assert "Unhandled expression type: Command" not in result.sql, result.sql
        assert "CONSTRAINT" in result.sql.upper() and "CHECK" in result.sql.upper()
        assert any("NOCHECK" in w.message for w in result.warnings), result.warnings

    def test_alter_column_to_oracle_modify(self, transpiler: Transpiler) -> None:
        # T-SQL "ALTER COLUMN c <type> [NULL|NOT NULL]" -> Oracle MODIFY(...).
        # sqlglot alone can't parse the nullability suffix (Command) and emits an
        # invalid "ALTER COLUMN … SET DATA TYPE" for the type change.
        out = transpiler.transpile(
            "ALTER TABLE dbo.t ALTER COLUMN c VARCHAR(100) NOT NULL",
            source="tsql",
            target="oracle",
        ).sql
        assert out.strip() == "ALTER TABLE t MODIFY (c VARCHAR2(100) NOT NULL);"

    def test_alter_column_varbinary_max_omits_redundant_null(
        self, transpiler: Transpiler
    ) -> None:
        # VARBINARY(MAX) -> BLOB (no size); the redundant NULL is omitted on Oracle
        # (explicit NULL raises ORA-01451 when the column is already nullable), with
        # a warning so the nullability directive is not silently lost.
        result = transpiler.transpile(
            "ALTER TABLE dbo.t ALTER COLUMN c VARBINARY(MAX) NULL",
            source="tsql",
            target="oracle",
        )
        assert result.sql.strip() == "ALTER TABLE t MODIFY (c BLOB);"
        assert any("nullability" in w.message.lower() for w in result.warnings)

    def test_alter_column_postgres_type_then_nullability(
        self, transpiler: Transpiler
    ) -> None:
        out = transpiler.transpile(
            "ALTER TABLE dbo.t ALTER COLUMN c INT NOT NULL",
            source="tsql",
            target="postgresql",
        ).sql
        assert "ALTER COLUMN c TYPE INT" in out
        assert "ALTER COLUMN c SET NOT NULL" in out

    def test_alter_column_mysql_modify_column(self, transpiler: Transpiler) -> None:
        out = transpiler.transpile(
            "ALTER TABLE dbo.t ALTER COLUMN c VARCHAR(50) NULL",
            source="tsql",
            target="mysql",
        ).sql
        assert out.strip() == "ALTER TABLE t MODIFY COLUMN c VARCHAR(50) NULL;"

    def test_guarded_alter_column_keeps_header_comment(
        self, transpiler: Transpiler
    ) -> None:
        # A section-header comment before a catalog-guarded ALTER COLUMN survives
        # and the ALTER still transpiles (the comment used to leave it a Command
        # carrier, because the guard re-attaches it ahead of the ALTER).
        sql = (
            "-- section header\n"
            "IF EXISTS (SELECT * FROM syscolumns WHERE id = object_id('dbo.t') "
            "AND name = 'c')\n"
            "    ALTER TABLE dbo.t ALTER COLUMN c VARCHAR(100) NULL\n"
            "ELSE\n    PRINT 'skip'"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "-- section header" in out
        assert "MODIFY (c VARCHAR2(100))" in out
        assert "Unhandled expression type: Command" not in out

    def test_create_schema_oracle_documented_carrier(
        self, transpiler: Transpiler
    ) -> None:
        # T-SQL CREATE SCHEMA (here as EXEC('…') dynamic SQL) has no Oracle form —
        # a schema is a database user — so it degrades to a documented carrier with
        # a CREATE USER hint, not a bare "Unhandled Execute".
        result = transpiler.transpile(
            "EXEC('CREATE SCHEMA [myschema] AUTHORIZATION [dbo]')",
            source="tsql",
            target="oracle",
        )
        assert "CREATE USER myschema" in result.sql
        assert "Unhandled expression type" not in result.sql
        assert any("CREATE SCHEMA" in u for u in result.unsupported)

    def test_create_schema_postgres_and_mysql(self, transpiler: Transpiler) -> None:
        # PostgreSQL/MySQL have CREATE SCHEMA; emit an idempotent one and drop the
        # T-SQL owner (AUTHORIZATION) with a warning.
        for target in ("postgresql", "mysql"):
            result = transpiler.transpile(
                "CREATE SCHEMA myschema AUTHORIZATION dbo",
                source="tsql",
                target=target,
            )
            assert result.sql.strip() == "CREATE SCHEMA IF NOT EXISTS myschema;"
            assert any("AUTHORIZATION" in w.message for w in result.warnings)

    def test_if_guard_with_else_keeps_then_branch(self, transpiler: Transpiler) -> None:
        # SSMA emits ``IF NOT EXISTS (…) <DDL> ELSE PRINT '… already exists'``;
        # only the THEN branch is a real statement — the ELSE PRINT is dropped,
        # not dragged into the DDL (which would degrade to a Command carrier).
        sql = (
            "IF NOT EXISTS (SELECT * FROM syscolumns WHERE name = 'fecha')\n"
            "    ALTER TABLE dbo.T ADD fecha DATETIME NULL\n"
            "ELSE\n    PRINT '[!] Warning: la columna ya existe'"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "ALTER TABLE T ADD fecha" in out
        assert "ELSE" not in out
        assert "-- UNIQUE:" not in out

    def test_guard_preserves_leading_comment(self, transpiler: Transpiler) -> None:
        # A section header preceding an IF NOT EXISTS guard must survive (the head
        # regex consumes the comment lines; they are re-attached, not dropped).
        sql = (
            "-- CREACION DE LA TABLA t\n"
            "IF NOT EXISTS (SELECT * FROM sysobjects WHERE id = object_id('t'))\n"
            "    CREATE TABLE dbo.t (id INT NOT NULL)"
        )
        for target in ("oracle", "postgresql", "mysql"):
            out = transpiler.transpile(sql, source="tsql", target=target).sql
            assert "-- CREACION DE LA TABLA t" in out, target
            assert "CREATE TABLE t" in out

    def test_procedural_preserves_leading_comment_block(
        self, transpiler: Transpiler
    ) -> None:
        # A comment header preceding a procedural CREATE (the procedural parser
        # starts at the keyword and drops it) is re-attached, once, not lost.
        sql = (
            "-- <codegen>\n"
            "--   <nombre>TRG_X</nombre>\n"
            "-- </codegen>\n"
            "CREATE OR REPLACE TRIGGER trg_x BEFORE INSERT ON t FOR EACH ROW\n"
            "BEGIN\n  :NEW.id := 1;\nEND;\n/"
        )
        for target in ("postgresql", "tsql", "mysql", "oracle"):
            out = transpiler.transpile(sql, source="oracle", target=target).sql
            assert out.count("<codegen>") == 1, target

    def test_constraint_check_state_toggle(self, transpiler: Transpiler) -> None:
        # ALTER TABLE t {CHECK|NOCHECK} CONSTRAINT c -> enable/disable per target.
        enable = "ALTER TABLE X WITH CHECK CHECK CONSTRAINT fk"
        disable = "ALTER TABLE X NOCHECK CONSTRAINT fk"
        assert (
            "ENABLE CONSTRAINT fk"
            in transpiler.transpile(enable, source="tsql", target="oracle").sql
        )
        assert (
            "DISABLE CONSTRAINT fk"
            in transpiler.transpile(disable, source="tsql", target="oracle").sql
        )
        assert (
            "VALIDATE CONSTRAINT fk"
            in transpiler.transpile(enable, source="tsql", target="postgresql").sql
        )
        # MySQL has no equivalent: preserved as a restorable note, not dropped.
        mysql_out = transpiler.transpile(disable, source="tsql", target="mysql").sql
        assert "/* UNIQUE:" in mysql_out
        assert "NOCHECK CONSTRAINT fk" in mysql_out

    def test_add_default_constraint(self, transpiler: Transpiler) -> None:
        # T-SQL ``ADD [CONSTRAINT n] DEFAULT v FOR c`` -> each engine's
        # set-column-default form (Oracle MODIFY, others ALTER COLUMN SET).
        sql = "ALTER TABLE X ADD CONSTRAINT df DEFAULT 0 FOR c"
        assert (
            "ALTER COLUMN c SET DEFAULT 0"
            in transpiler.transpile(sql, source="tsql", target="postgresql").sql
        )
        assert (
            "ALTER COLUMN c SET DEFAULT 0"
            in transpiler.transpile(sql, source="tsql", target="mysql").sql
        )
        assert (
            "MODIFY c DEFAULT 0"
            in transpiler.transpile(sql, source="tsql", target="oracle").sql
        )

    def test_add_default_non_portable_value_falls_back(
        self, transpiler: Transpiler
    ) -> None:
        # A default whose value has no clean target form (NEWID()) must document,
        # not emit invalid SQL.
        sql = "ALTER TABLE X ADD DEFAULT (NEWID()) FOR rowguid"
        out = transpiler.transpile(sql, source="tsql", target="mysql").sql
        assert "-- UNIQUE:" in out
        assert "CHAR()" not in out

    def test_comments_preserved_dml_path(self, transpiler: Transpiler) -> None:
        # DML/DDL comments were dropped by the sqlglot->IR conversion; they must
        # now survive tsql->oracle (leading, between, trailing, and inline).
        sql = (
            "-- header note\n"
            "SELECT 1;\n"
            "-- between note\n"
            "SELECT 2 -- trailing note\n"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        for note in ("header note", "between note", "trailing note"):
            assert note in out, note

    def test_comment_before_go_preserved(self, transpiler: Transpiler) -> None:
        sql = "SELECT 1\n-- note before go\nGO\nSELECT 2"
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        assert "note before go" in out

    def test_inline_create_table_comment_preserved(
        self, transpiler: Transpiler
    ) -> None:
        sql = "CREATE TABLE t (\n  id INT, -- the id\n  n VARCHAR(10)\n)"
        out = transpiler.transpile(sql, source="tsql", target="postgresql").sql
        assert "the id" in out

    def test_oracle_slash_only_after_plsql_blocks(self, transpiler: Transpiler) -> None:
        # Oracle's ``/`` executes the buffer: it must follow a PL/SQL block but
        # never a plain ``;``-terminated statement (which it would re-run).
        sql = (
            "UPDATE t SET a = 1 WHERE id = 2;\nGO\n"
            "CREATE PROCEDURE p AS BEGIN SELECT 1; END;\nGO\n"
            "INSERT INTO t (a) VALUES (3);\nGO"
        )
        out = transpiler.transpile(sql, source="tsql", target="oracle").sql
        lines = [ln.strip() for ln in out.splitlines()]
        # Exactly one ``/`` — the one after the procedure's END;.
        assert lines.count("/") == 1
        slash_idx = lines.index("/")
        assert lines[slash_idx - 1] == "END;"

    def test_oracle_trailing_plsql_block_gets_slash(
        self, transpiler: Transpiler
    ) -> None:
        # A PL/SQL block as the *last* batch still needs its ``/`` to run.
        out = transpiler.transpile(
            "CREATE PROCEDURE p AS BEGIN SELECT 1; END;",
            source="tsql",
            target="oracle",
        ).sql
        assert out.rstrip().endswith("/")

    def test_oracle_no_trailing_slash_after_plain_dml(
        self, transpiler: Transpiler
    ) -> None:
        out = transpiler.transpile(
            "UPDATE t SET a = 1 WHERE id = 2", source="tsql", target="oracle"
        ).sql
        assert "/" not in out
        assert out.rstrip().endswith(";")

    def test_sqlite_trigger_to_targets(self, transpiler: Transpiler) -> None:
        # A SQLite row-level trigger routes through the procedural engine and
        # translates to each target's trigger form (Phase 3).
        trg = (
            "CREATE TRIGGER trg AFTER INSERT ON orders\n"
            "FOR EACH ROW\n"
            "BEGIN\n"
            "  UPDATE stats SET total = total + NEW.amount WHERE id = NEW.cat_id;\n"
            "END"
        )
        # Oracle: PL/SQL trigger with :NEW.
        oracle = transpiler.transpile(trg, source="sqlite", target="oracle").sql
        assert "CREATE OR REPLACE TRIGGER trg" in oracle
        assert ":NEW.amount" in oracle
        assert "-- UNIQUE:" not in oracle
        # MySQL: DELIMITER-wrapped trigger with NEW.
        mysql = transpiler.transpile(trg, source="sqlite", target="mysql").sql
        assert "CREATE TRIGGER trg" in mysql
        assert "NEW.amount" in mysql
        assert "-- UNIQUE:" not in mysql
        # PostgreSQL: trigger function + CREATE TRIGGER.
        pg = transpiler.transpile(trg, source="sqlite", target="postgresql").sql
        assert "RETURNS TRIGGER" in pg
        assert "CREATE OR REPLACE TRIGGER trg" in pg
        assert "-- UNIQUE:" not in pg

    def test_sqlite_source_function_mappings(self, transpiler: Transpiler) -> None:
        # SQLite-only functions rewrite to each target's form (Phase 2).
        def out(sql: str, tgt: str) -> str:
            return transpiler.transpile(sql, source="sqlite", target=tgt).sql

        assert "LASTVAL()" in out("SELECT last_insert_rowid()", "postgresql")
        assert "LAST_INSERT_ID()" in out("SELECT last_insert_rowid()", "mysql")
        assert "CURRENT_TIMESTAMP" in out("SELECT datetime('now')", "postgresql")
        assert "SYSDATE" in out("SELECT datetime('now')", "oracle")
        assert "CURRENT_DATE" in out("SELECT date('now')", "mysql")
        assert "RANDOM()" in out("SELECT random()", "postgresql")
        assert "DBMS_RANDOM.VALUE" in out("SELECT random()", "oracle")

    def test_system_procedure_becomes_comment(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "EXEC sys.sp_addextendedproperty @name=N'x', @value=N'y'",
            source="tsql",
            target="oracle",
        )
        assert result.sql.lstrip().startswith("--")
        assert "sp_addextendedproperty" in result.sql
        assert any("System procedure" in u for u in result.unsupported)

    def test_custom_sp_prefixed_proc_becomes_a_call(
        self, transpiler: Transpiler
    ) -> None:
        # The sp_ prefix is not actually reserved: user procedures use it too
        # (this repo's own sp_helperproc/sp_customproc synonym helpers, for one). An
        # unknown sp_* is a real call, not dropped as a system procedure.
        result = transpiler.transpile(
            "exec sp_customproc 'dbo', 'sample_obj', 'bs_sample'",
            source="tsql",
            target="oracle",
        )
        assert "sp_customproc('dbo', 'sample_obj', 'bs_sample')" in result.sql
        assert "system procedure" not in result.sql.lower()
        assert not any("System procedure" in u for u in result.unsupported)

    def test_system_procedure_passthrough_same_dialect(
        self, transpiler: Transpiler
    ) -> None:
        # tsql -> tsql should not apply the cross-dialect system-procedure
        # rewrite (no "no oracle/... equivalent" note).
        result = transpiler.transpile(
            "EXEC sp_rename 'a', 'b'", source="tsql", target="tsql"
        )
        assert not any("System procedure" in u for u in result.unsupported)

    def test_same_dialect_skips_transform(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "SELECT * FROM t WHERE id = 1",
            source="postgresql",
            target="postgresql",
        )
        assert "SELECT" in result.sql
        assert len(result.warnings) == 0

    def test_unknown_source_raises(self, transpiler: Transpiler) -> None:
        with pytest.raises(UnknownDialectError):
            transpiler.transpile("SELECT 1", source="db2", target="tsql")

    def test_unknown_target_raises(self, transpiler: Transpiler) -> None:
        with pytest.raises(UnknownDialectError):
            transpiler.transpile("SELECT 1", source="tsql", target="db2")

    def test_available_dialects(self, transpiler: Transpiler) -> None:
        dialects = transpiler.available_dialects()
        # Four full engines + SQLite (import-only source).
        assert len(dialects) == 5
        assert "tsql" in dialects
        assert "sqlite" in dialects

    def test_sqlite_is_source_only(self, transpiler: Transpiler) -> None:
        assert transpiler.source_only_dialects() == ["sqlite"]

    def test_sqlite_source_transpiles(self, transpiler: Transpiler) -> None:
        # SQLite as a source is a first-class DML/DDL path.
        out = transpiler.transpile(
            "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, n TEXT);",
            source="sqlite",
            target="postgresql",
        ).sql
        assert "CREATE TABLE t" in out
        assert "-- UNIQUE:" not in out

    def test_sqlite_rejected_as_target(self, transpiler: Transpiler) -> None:
        from unique.core.errors import UnsupportedFeatureError

        with pytest.raises(UnsupportedFeatureError, match="import-only"):
            transpiler.transpile("SELECT 1", source="tsql", target="sqlite")

    def test_top_to_limit(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "SELECT TOP 5 * FROM users",
            source="tsql",
            target="postgresql",
        )
        assert "LIMIT 5" in result.sql
        assert "TOP" not in result.sql

    def test_insert_preserves_columns(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "INSERT INTO t (a, b) VALUES (1, 2)",
            source="tsql",
            target="mysql",
        )
        assert "(a, b)" in result.sql
        assert "VALUES" in result.sql

    def test_update_cross_dialect(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "UPDATE users SET name = 'test' WHERE id = 1",
            source="tsql",
            target="postgresql",
        )
        assert "UPDATE users" in result.sql
        assert "SET" in result.sql
        assert "WHERE" in result.sql

    def test_delete_cross_dialect(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "DELETE FROM users WHERE id = 1",
            source="mysql",
            target="oracle",
        )
        assert "DELETE FROM" in result.sql


class TestTranspileResult:
    def test_has_warnings_false(self) -> None:
        result = TranspileResult(sql="SELECT 1")
        assert result.has_warnings is False

    def test_has_warnings_true(self) -> None:
        from unique.core.transformer import TransformWarning

        result = TranspileResult(
            sql="SELECT 1",
            warnings=[TransformWarning("msg", "feat", "tsql", "pg")],
        )
        assert result.has_warnings is True

    def test_has_unsupported(self) -> None:
        result = TranspileResult(sql="SELECT 1", unsupported=["GOTO"])
        assert result.has_unsupported is True


class TestConvenienceFunction:
    def test_transpile_function(self) -> None:
        result = transpile(
            "SELECT * FROM users WHERE id = 1",
            source="tsql",
            target="mysql",
        )
        assert isinstance(result, TranspileResult)
        assert "SELECT" in result.sql


class TestMySQLDelimiterWrapping:
    """MySQL compound routines must be wrapped in a DELIMITER block."""

    SRC = (
        "CREATE PROCEDURE dbo.p\n"
        "    @a NVARCHAR(MAX) OUTPUT\n"
        "AS\n"
        "BEGIN\n"
        "    SET @a = NULL\n"
        "    IF @a IS NOT NULL\n"
        "        SET @a = @a + N'x'\n"
        "END"
    )

    def test_procedure_wrapped_in_delimiter(self, transpiler: Transpiler) -> None:
        out = transpiler.transpile(self.SRC, source="tsql", target="mysql").sql
        assert "DELIMITER $$" in out
        assert "DELIMITER ;" in out
        # The routine body terminates with END$$ (not END; before the wrapper).
        assert "END$$" in out

    def test_delimiters_are_balanced(self, transpiler: Transpiler) -> None:
        out = transpiler.transpile(self.SRC, source="tsql", target="mysql").sql
        assert out.count("DELIMITER $$") == out.count("DELIMITER ;")
        assert out.count("DELIMITER $$") == out.count("END$$")

    def test_leading_comments_kept_above_delimiter(
        self, transpiler: Transpiler
    ) -> None:
        src = (
            "IF OBJECT_ID(N'dbo.p', N'P') IS NULL\n"
            "    EXEC (N'CREATE PROCEDURE dbo.p AS SELECT 1')\n"
            "GO\n" + self.SRC
        )
        out = transpiler.transpile(src, source="tsql", target="mysql").sql
        # The guard becomes a leading comment; it must precede DELIMITER $$.
        delim_pos = out.index("DELIMITER $$")
        assert "--" in out[:delim_pos]

    def test_plain_dml_not_wrapped(self, transpiler: Transpiler) -> None:
        out = transpiler.transpile(
            "SELECT * FROM users", source="tsql", target="mysql"
        ).sql
        assert "DELIMITER" not in out

    def test_function_wrapped_in_delimiter(self, transpiler: Transpiler) -> None:
        src = (
            "CREATE FUNCTION dbo.f(@x INT)\n"
            "RETURNS INT\n"
            "AS\n"
            "BEGIN\n"
            "    RETURN @x + 1\n"
            "END"
        )
        out = transpiler.transpile(src, source="tsql", target="mysql").sql
        assert "DELIMITER $$" in out
        assert "DELIMITER ;" in out


class TestQuotedIdentifierOff:
    """Under T-SQL SET QUOTED_IDENTIFIER OFF, double-quoted text is a string
    literal, not an identifier; the transpiler tracks the setting across
    batches and rewrites "..." to '...' before parsing."""

    def test_double_quote_becomes_string(self) -> None:
        src = "SET QUOTED_IDENTIFIER OFF\nGO\n" 'SELECT a FROM t WHERE name = "John"'
        out = transpile(src, source="tsql", target="mysql").sql
        assert "= 'John'" in out
        assert '"John"' not in out

    def test_on_keeps_identifier(self) -> None:
        # Default (ON): a double-quoted name stays an identifier.
        out = transpile(
            'SELECT a FROM t WHERE "name" = 1', source="tsql", target="mysql"
        ).sql
        assert "'name'" not in out

    def test_off_then_on_resets(self) -> None:
        src = (
            "SET QUOTED_IDENTIFIER OFF\nGO\n"
            'SELECT "x" AS c\nGO\n'
            "SET QUOTED_IDENTIFIER ON\nGO\n"
            'SELECT "y" AS c'
        )
        out = transpile(src, source="tsql", target="mysql").sql
        assert "'x' AS c" in out  # OFF: string literal
        assert "'y'" not in out  # ON: identifier again


class TestTSQLDropGuards:
    """T-SQL 'IF OBJECT_ID(...) IS NOT NULL DROP ...' cleanup guards.

    They used to degrade to comments, so a transpiled schema was not
    re-runnable (first live FE run: 'relation "invoice_seq" already
    exists'). The guarded DROP maps to the target's own conditional form.
    """

    def setup_method(self) -> None:
        self.t = Transpiler()

    GUARD = (
        "IF OBJECT_ID(N'dbo.invoice_seq', N'SO') IS NOT NULL\n"
        "    DROP SEQUENCE dbo.invoice_seq\nGO"
    )

    def test_postgresql_drop_if_exists(self) -> None:
        out = self.t.transpile(self.GUARD, "tsql", "postgresql").sql
        assert "DROP SEQUENCE IF EXISTS invoice_seq" in out
        assert "OBJECT_ID" not in out

    def test_mysql_sequence_guard_stays_documented(self) -> None:
        # MySQL has no sequences at all; the guard stays a documented note.
        out = self.t.transpile(self.GUARD, "tsql", "mysql").sql
        assert "DROP SEQUENCE" not in [
            line for line in out.splitlines() if not line.lstrip().startswith("--")
        ]

    def test_mysql_drop_table_if_exists(self) -> None:
        sql = (
            "IF OBJECT_ID(N'dbo.customer', N'U') IS NOT NULL\n"
            "    DROP TABLE dbo.customer\nGO"
        )
        out = self.t.transpile(sql, "tsql", "mysql").sql
        assert "DROP TABLE IF EXISTS customer" in out

    def test_oracle_guarded_drop_block(self) -> None:
        out = self.t.transpile(self.GUARD, "tsql", "oracle").sql
        assert "EXECUTE IMMEDIATE 'DROP SEQUENCE invoice_seq'" in out
        assert "WHEN OTHERS THEN" in out

    def test_procedure_guard_to_postgresql(self) -> None:
        sql = (
            "IF OBJECT_ID(N'dbo.create_invoice', N'P') IS NOT NULL\n"
            "    DROP PROCEDURE dbo.create_invoice\nGO"
        )
        out = self.t.transpile(sql, "tsql", "postgresql").sql
        assert "DROP PROCEDURE IF EXISTS create_invoice" in out


class TestCreateSequence:
    """CREATE SEQUENCE with a T-SQL ``AS <type>`` clause.

    T-SQL and PostgreSQL accept ``CREATE SEQUENCE s AS INT ...``; Oracle does
    not (ORA-03048: 'AS' is not valid following the sequence name), so the type
    clause must be dropped for Oracle.
    """

    def setup_method(self) -> None:
        self.t = Transpiler()

    SEQ = (
        "CREATE SEQUENCE dbo.invoice_seq\n"
        "    AS INT\n    START WITH 1\n    INCREMENT BY 1"
    )

    def test_oracle_drops_as_type(self) -> None:
        out = self.t.transpile(self.SEQ, "tsql", "oracle").sql
        assert "CREATE SEQUENCE invoice_seq" in out
        # No 'AS <type>' clause survives (would be ORA-03048).
        assert not re.search(r"(?i)\bSEQUENCE\s+invoice_seq\s+AS\b", out)
        assert "START WITH 1" in out
        assert "INCREMENT BY 1" in out

    def test_postgresql_keeps_valid_sequence(self) -> None:
        out = self.t.transpile(self.SEQ, "tsql", "postgresql").sql
        assert "CREATE SEQUENCE invoice_seq" in out
        assert "START WITH 1" in out


class TestOracleDateLiterals:
    """ISO date/datetime strings inserted into DATE columns.

    Oracle has no default that reads a bare '2024-01-15' as a date
    (ORA-01861), so a string literal written to a harvested date column is
    wrapped in an ANSI DATE/TIMESTAMP literal. Other targets accept the ISO
    string implicitly and are left unchanged.
    """

    def setup_method(self) -> None:
        self.t = Transpiler()

    SCHEMA = (
        "CREATE TABLE dbo.evt (\n"
        "  id INT IDENTITY(1,1) NOT NULL,\n"
        "  d DATE NOT NULL,\n"
        "  ts DATETIME NULL\n"
        ");\n"
    )
    INSERT = (
        "INSERT INTO dbo.evt (d, ts) VALUES ('2024-01-15', '2024-01-15 10:30:00');\n"
    )

    def test_oracle_wraps_date_and_timestamp(self) -> None:
        out = self.t.transpile(self.SCHEMA + self.INSERT, "tsql", "oracle").sql
        assert "DATE '2024-01-15'" in out
        assert "TIMESTAMP '2024-01-15 10:30:00'" in out
        # The bare string must not survive for the date column.
        assert "('2024-01-15'" not in out

    def test_oracle_update_wraps_date(self) -> None:
        upd = "UPDATE dbo.evt SET d = '2024-03-01' WHERE id = 1;\n"
        out = self.t.transpile(self.SCHEMA + upd, "tsql", "oracle").sql
        assert "d = DATE '2024-03-01'" in out

    def test_non_date_column_untouched(self) -> None:
        # A string into a non-date column stays a plain string literal.
        sql = self.SCHEMA + "INSERT INTO dbo.evt (d) VALUES ('2024-01-15');\n"
        out = self.t.transpile(sql, "tsql", "oracle").sql
        assert "DATE '2024-01-15'" in out

    def test_postgresql_leaves_iso_string(self) -> None:
        out = self.t.transpile(self.SCHEMA + self.INSERT, "tsql", "postgresql").sql
        assert "'2024-01-15'" in out
        assert "DATE '2024-01-15'" not in out

    def test_oracle_cast_to_date_becomes_ansi_literal(self) -> None:
        # A PostgreSQL DATE literal transpiles as CAST('…' AS DATE); Oracle
        # can't implicitly convert that string (ORA-01861), so emit DATE '…'.
        sql = (
            "CREATE TABLE evt (id INT GENERATED ALWAYS AS IDENTITY, d DATE NOT NULL);\n"
            "INSERT INTO evt (d) VALUES (DATE '2024-01-15');\n"
        )
        out = self.t.transpile(sql, "postgresql", "oracle").sql
        assert "DATE '2024-01-15'" in out
        assert "CAST('2024-01-15' AS DATE)" not in out
