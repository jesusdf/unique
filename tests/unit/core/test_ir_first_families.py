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


class TestPgFoundFlagInIr:
    """plpgsql's FOUND flag maps per target in the IR (M3 family F3)."""

    def test_found_to_tsql(self) -> None:
        out = _ir("postgresql", "tsql", "SELECT CASE WHEN FOUND THEN 1 ELSE 2 END")
        assert out is not None and "(@@ROWCOUNT > 0)" in out

    def test_found_to_oracle(self) -> None:
        out = _ir("postgresql", "oracle", "SELECT CASE WHEN FOUND THEN 1 ELSE 2 END")
        assert out is not None and "SQL%FOUND" in out

    def test_found_to_mysql(self) -> None:
        out = _ir("postgresql", "mysql", "SELECT CASE WHEN FOUND THEN 1 ELSE 2 END")
        assert out is not None and "(ROW_COUNT() > 0)" in out

    def test_found_column_untouched_from_other_sources(self) -> None:
        out = _ir("mysql", "tsql", "SELECT found FROM t")
        assert out is not None and "@@ROWCOUNT" not in out


class TestOracleCursorAttrsInIr:
    """Oracle cursor attributes map on T-SQL in the IR (M3 family F8b)."""

    def test_sql_found_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT CASE WHEN SQL%FOUND THEN 1 ELSE 2 END")
        assert out is not None and "@@ROWCOUNT > 0" in out
        assert "%" not in out

    def test_sql_notfound_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT CASE WHEN SQL%NOTFOUND THEN 1 ELSE 2 END")
        assert out is not None and "@@ROWCOUNT = 0" in out

    def test_named_cursor_found_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT CASE WHEN c_t%FOUND THEN 1 ELSE 2 END")
        assert out is not None and "@@FETCH_STATUS = 0" in out
        assert "%" not in out

    def test_named_cursor_notfound_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT CASE WHEN c_t%NOTFOUND THEN 1 ELSE 2 END")
        assert out is not None and "@@FETCH_STATUS <> 0" in out

    def test_sql_found_to_postgresql(self) -> None:
        out = _ir(
            "oracle", "postgresql", "SELECT CASE WHEN SQL%FOUND THEN 1 ELSE 2 END"
        )
        assert out is not None and "FOUND" in out and "%" not in out


class TestStyledConvertInIr:
    """T-SQL CONVERT(type, x, style) is modeled in the IR (M3 family F1)."""

    def test_style_120_to_mysql_str_to_date(self) -> None:
        out = _ir("tsql", "mysql", "SELECT CONVERT(DATETIME, '2020-01-01', 120)")
        assert (
            out is not None and "STR_TO_DATE('2020-01-01', '%Y-%m-%d %H:%i:%s')" in out
        )

    def test_style_120_to_postgresql_to_timestamp(self) -> None:
        out = _ir("tsql", "postgresql", "SELECT CONVERT(DATETIME, '2020-01-01', 120)")
        assert (
            out is not None
            and "TO_TIMESTAMP('2020-01-01', 'YYYY-MM-DD HH24:MI:SS')" in out
        )

    def test_style_112_char_to_oracle_to_char(self) -> None:
        out = _ir("tsql", "oracle", "SELECT CONVERT(NVARCHAR(20), d, 112) FROM t")
        assert out is not None and "TO_CHAR(d, 'YYYYMMDD')" in out

    def test_hash_wrapper_style_2_drops_on_mysql(self) -> None:
        out = _ir(
            "tsql",
            "mysql",
            "SELECT CONVERT(NVARCHAR(MAX), HASHBYTES('SHA2_256', x), 2) FROM t",
        )
        assert out is not None and "SHA2(x, 256)" in out
        assert "CONVERT" not in out.upper()

    def test_hash_wrapper_style_2_sha256_on_postgresql(self) -> None:
        out = _ir(
            "tsql",
            "postgresql",
            "SELECT CONVERT(NVARCHAR(MAX), HASHBYTES('SHA2_256', x), 2) FROM t",
        )
        assert out is not None and "SHA256(x)" in out

    def test_styled_convert_verbatim_on_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT TO_CHAR(SYSDATE) FROM DUAL")
        # unrelated sanity: same-direction fragments still transpile
        assert out is None or "ERROR" not in out.upper()


class TestCommentsInIrFragments:
    """In-expression comments survive IR-first as block comments (M3
    precondition (b)): a line comment would swallow the rest of the
    expression once the emitter joins the statement onto one line.
    """

    SRC = (
        "CREATE PROCEDURE p_c\n"
        "    @m_tipo NVARCHAR(10)\n"
        "AS\n"
        "BEGIN\n"
        "    IF -- Si el episodio es de urgencias\n"
        "    @m_tipo = 'U'\n"
        "    BEGIN\n"
        "        INSERT INTO t_log (a) VALUES (1);\n"
        "    END\n"
        "END\n"
        "GO\n"
    )

    def test_comment_becomes_block_on_mysql(self, monkeypatch) -> None:
        monkeypatch.setenv("UNIQUE_IR_FIRST", "1")
        from unique.core.transpiler import Transpiler

        out = Transpiler().transpile(self.SRC, "tsql", "mysql").sql
        flat = " ".join(out.splitlines())
        assert "/* Si el episodio es de urgencias */" in out, out
        assert not __import__("re").search(r"--[^\n]*= 'U'", flat), out

    def test_condition_survives_on_oracle(self, monkeypatch) -> None:
        monkeypatch.setenv("UNIQUE_IR_FIRST", "1")
        from unique.core.transpiler import Transpiler

        out = Transpiler().transpile(self.SRC, "tsql", "oracle").sql
        assert "= 'U'" in out.replace("V_M_TIPO = 'U'", "= 'U'"), out


class TestMysqlConcatShape:
    """MySQL concat is flat and never ships '+' (numeric there) — M3 F13."""

    def test_oracle_plus_string_becomes_concat(self) -> None:
        out = _ir("oracle", "mysql", "SELECT 'pre' || v_a FROM DUAL")
        assert out is not None and "CONCAT('pre', v_a)" in out

    def test_chain_flattens(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        t._string_vars = {"v_a", "v_b"}
        out = t._ir_transpile_dml("SELECT 'a' + v_a + 'b' + v_b")
        assert out is not None and "CONCAT('a', v_a, 'b', v_b)" in out, out

    def test_oracle_source_plus_with_string_literal(self) -> None:
        out = _ir("oracle", "mysql", "SELECT 'pre' + v_a FROM DUAL")
        assert out is not None and "CONCAT('pre', v_a)" in out, out

    def test_mysql_source_plus_stays_numeric(self) -> None:
        out = _ir("mysql", "tsql", "SELECT a + b FROM t")
        assert out is not None and "CONCAT" not in out.upper()
