# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""IR expression-pipeline parity with the procedural text path (M3-final).

Each class covers one family migrated off the text rewriters: the IR must
produce the text path's live-validated forms so scalar fragments can route
IR-first (docs/TODO.md §2 P0). These call the IR directly — no
UNIQUE_IR_FIRST needed — so the coverage is always on.
"""

from __future__ import annotations

from unique.core.procedural.transformer import ProceduralTransformer


def _ir(source: str, target: str, fragment: str) -> str | None:
    return ProceduralTransformer(source, target)._ir_transpile_dml(fragment)


class TestSharedFuncMapInIr:
    """The IR consults the shared PROCEDURAL_FUNC_MAPS pair renames."""

    def test_oracle_chr_to_tsql_char(self) -> None:
        out = _ir("oracle", "tsql", "SELECT CHR(13) FROM DUAL")
        assert out is not None and "CHAR(13)" in out
        assert "CHR(" not in out

    def test_oracle_chr_to_mysql_char(self) -> None:
        out = _ir("oracle", "mysql", "SELECT CHR(13) FROM DUAL")
        assert out is not None and "CHAR(13)" in out


class TestLastIdentityInIr:
    """The source's last-identity call maps to the target's expression."""

    def test_mysql_last_insert_id_to_postgresql(self) -> None:
        out = _ir("mysql", "postgresql", "SELECT LAST_INSERT_ID()")
        assert out is not None and "LASTVAL()" in out.upper()
        assert "LAST_INSERT_ID" not in out.upper()

    def test_postgresql_lastval_to_mysql(self) -> None:
        out = _ir("postgresql", "mysql", "SELECT LASTVAL()")
        assert out is not None and "LAST_INSERT_ID()" in out.upper()

    def test_foreign_named_function_untouched(self) -> None:
        # A pg script calling LAST_INSERT_ID() names a UDF, not the global.
        out = _ir("postgresql", "tsql", "SELECT LAST_INSERT_ID(a) FROM t")
        assert out is None or "SCOPE_IDENTITY" not in (out or "").upper()


class TestErrorMessageInIr:
    """ERROR_MESSAGE()/SQLERRM map across engines (exception context)."""

    def test_tsql_error_message_to_postgresql(self) -> None:
        out = _ir("tsql", "postgresql", "SELECT 'E: ' + ERROR_MESSAGE()")
        assert out is not None and "SQLERRM" in out
        assert "ERROR_MESSAGE" not in out.upper()

    def test_tsql_error_message_to_oracle(self) -> None:
        out = _ir("tsql", "oracle", "SELECT ERROR_MESSAGE()")
        assert out is not None and "SQLERRM" in out

    def test_pg_sqlerrm_to_tsql(self) -> None:
        out = _ir("postgresql", "tsql", "SELECT 'E: ' || SQLERRM")
        assert out is not None and "ERROR_MESSAGE()" in out
        assert "SQLERRM" not in out.upper()


class TestToNumberInIr:
    """Oracle's bare TO_NUMBER(x) is a decimal cast off Oracle."""

    def test_to_number_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT TO_NUMBER(c) FROM t")
        assert out is not None and "CAST(c AS DECIMAL(38, 10))" in out
        assert "TO_NUMBER" not in out.upper()

    def test_to_number_stays_on_oracle(self) -> None:
        out = _ir("postgresql", "oracle", "SELECT TO_NUMBER(c, '999') FROM t")
        assert out is None or "TO_NUMBER" in out.upper()


class TestTriggerShellIdiomsIrFirst:
    """Trigger-shell spellings survive IR-first routing (M3 family F5/F10/F11).

    Event predicates (INSERTING/UPDATING/UPDATE(col)) are trigger-shell
    context the source parse would corrupt (UPDATE(col) parses as DML) —
    those fragments skip the IR and keep the text path's mapping. Oracle's
    :NEW./:OLD. row-ref spelling applies to IR output too.
    """

    def _probe(self, monkeypatch, src_sql: str, source: str, target: str) -> str:
        import pytest  # noqa: F401 - fixture-injected monkeypatch

        monkeypatch.setenv("UNIQUE_IR_FIRST", "1")
        from unique.core.transpiler import Transpiler

        return Transpiler().transpile(src_sql, source, target).sql

    def test_tsql_update_predicate_not_corrupted(self, monkeypatch) -> None:
        src = (
            "CREATE TRIGGER trg ON t AFTER UPDATE AS\n"
            "BEGIN\n"
            "    IF UPDATE(col_32)\n"
            "    BEGIN\n"
            "        INSERT INTO log (a) VALUES (1);\n"
            "    END\n"
            "END\n"
            "GO\n"
        )
        out = self._probe(monkeypatch, src, "tsql", "postgresql")
        assert "IS DISTINCT FROM" in out, out
        assert "UPDATE SET" not in out, out

    def test_oracle_inserting_maps_to_tg_op(self, monkeypatch) -> None:
        src = (
            "CREATE OR REPLACE TRIGGER trg_m AFTER INSERT OR UPDATE ON t_d\n"
            "FOR EACH ROW\n"
            "BEGIN\n"
            "    IF INSERTING THEN\n"
            "        INSERT INTO t_log (op) VALUES ('I');\n"
            "    END IF;\n"
            "END;\n"
            "/\n"
        )
        out = self._probe(monkeypatch, src, "oracle", "postgresql")
        assert "(TG_OP = 'INSERT')" in out, out
        assert "INSERTING" not in out.upper(), out

    def test_mysql_new_ref_spells_colon_new_on_oracle(self, monkeypatch) -> None:
        src = (
            "CREATE TRIGGER trg_c BEFORE INSERT ON invoice_line\n"
            "FOR EACH ROW\n"
            "BEGIN\n"
            "    SET NEW.line_total = NEW.qty * NEW.unit_price;\n"
            "END;\n"
        )
        out = self._probe(monkeypatch, src, "mysql", "oracle")
        assert ":NEW.line_total := :NEW.qty * :NEW.unit_price" in out, out
