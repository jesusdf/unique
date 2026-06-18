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
