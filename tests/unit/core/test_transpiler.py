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

    def test_system_procedure_becomes_comment(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(
            "EXEC sys.sp_addextendedproperty @name=N'x', @value=N'y'",
            source="tsql",
            target="oracle",
        )
        assert result.sql.lstrip().startswith("--")
        assert "sp_addextendedproperty" in result.sql
        assert any("System procedure" in u for u in result.unsupported)

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
            transpiler.transpile("SELECT 1", source="sqlite", target="tsql")

    def test_unknown_target_raises(self, transpiler: Transpiler) -> None:
        with pytest.raises(UnknownDialectError):
            transpiler.transpile("SELECT 1", source="tsql", target="sqlite")

    def test_available_dialects(self, transpiler: Transpiler) -> None:
        dialects = transpiler.available_dialects()
        assert len(dialects) == 4
        assert "tsql" in dialects

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
