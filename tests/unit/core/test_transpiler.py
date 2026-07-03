"""Tests for the Transpiler orchestrator and convenience function."""

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
