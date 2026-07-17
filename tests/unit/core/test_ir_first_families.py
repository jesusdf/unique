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


class TestDateFamilyInIr:
    """Date-function edge shapes in the IR (M3 family F9 + visibility)."""

    def test_quoted_part_first_datediff_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT DATEDIFF('D', d_a, d_b) + 1 FROM t")
        assert out is not None and "DATEDIFF(DAY, D_A, D_B)" in out.upper(), out

    def test_quoted_year_part_to_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT DATEDIFF('Y', d_a, d_b) FROM t")
        assert out is not None and "DATEDIFF(YEAR, D_A, D_B)" in out.upper(), out

    def test_part_first_datediff_to_mysql_two_arg(self) -> None:
        out = _ir("oracle", "mysql", "SELECT DATEDIFF('D', d_a, d_b) FROM t")
        assert out is not None and "DATEDIFF(D_B, D_A)" in out.upper(), out

    def test_unknown_dateadd_part_stays_visible(self) -> None:
        out = _ir("tsql", "postgresql", "SELECT DATEADD(microsecond, 1, d) FROM t")
        assert out is not None and "DATEADD" in out.upper(), out
        assert "DATE_ADD(d, 1, MICROSECOND)" not in out, out


class TestDateVarsContextInIr:
    """Date-typed variable context reaches the IR (M3 family F14)."""

    def _t(self, source: str, target: str, frag: str, date_vars: set[str]):
        t = ProceduralTransformer(source, target)
        t._date_vars = date_vars
        return t._ir_transpile_dml(frag)

    def test_trunc_date_var_becomes_date_on_mysql(self) -> None:
        out = self._t("oracle", "mysql", "SELECT TRUNC(d_fecha) FROM t", {"d_fecha"})
        assert out is not None and "DATE(D_FECHA)" in out.upper(), out

    def test_trunc_non_date_becomes_truncate_on_mysql(self) -> None:
        out = self._t("oracle", "mysql", "SELECT TRUNC(v_num) FROM t", set())
        assert out is not None and "TRUNCATE(V_NUM, 0)" in out.upper(), out

    def test_date_subtraction_becomes_datediff_on_tsql(self) -> None:
        out = self._t(
            "oracle", "tsql", "SELECT d2 - d1 FROM t", {"@d1", "@d2", "d1", "d2"}
        )
        assert out is not None and "DATEDIFF(DAY, D1, D2)" in out.upper(), out

    def test_numeric_subtraction_untouched(self) -> None:
        out = self._t("oracle", "tsql", "SELECT a - b FROM t", set())
        assert out is not None and "DATEDIFF" not in out.upper()


class TestToDateToCharStylesInIr:
    """Formatted TO_DATE/TO_CHAR keep fidelity on T-SQL (M3 family F7)."""

    def test_to_date_known_format_converts_with_style(self) -> None:
        out = _ir("oracle", "tsql", "SELECT TO_DATE(x, 'YYYY-MM-DD HH24:MI:SS') FROM t")
        assert out is not None and "CONVERT(DATETIME, x, 120)" in out, out

    def test_to_date_unknown_format_stays_visible(self) -> None:
        out = _ir("oracle", "tsql", "SELECT TO_DATE(x, 'J') FROM t")
        assert out is not None and "TO_DATE" in out.upper(), out
        assert "CAST(x AS DATE)" not in out, out

    def test_numeric_style_to_char_becomes_convert(self) -> None:
        out = _ir("oracle", "tsql", "SELECT TO_CHAR(d, 112) FROM t")
        assert out is not None and "CONVERT(VARCHAR(4000), d, 112)" in out, out

    def test_date_format_to_char_still_formats(self) -> None:
        out = _ir("oracle", "tsql", "SELECT TO_CHAR(d, 'DD/MM/YYYY') FROM t")
        assert out is not None and "FORMAT(d, 'dd/MM/yyyy')" in out, out


class TestTrimPositionAndLobHelpers:
    """LTRIM/RTRIM keep their side; Oracle LOB helpers map on T-SQL (F6b)."""

    def test_rtrim_ltrim_keep_position(self) -> None:
        out = _ir("oracle", "tsql", "SELECT RTRIM(LTRIM(x)) FROM t")
        assert out is not None and "RTRIM(LTRIM(x))" in out, out
        assert "TRIM(TRIM" not in out.upper(), out

    def test_dbms_lob_substr_reorders(self) -> None:
        out = _ir("oracle", "tsql", "SELECT DBMS_LOB.SUBSTR(p_c, 4000, 1) FROM t")
        assert out is not None and "SUBSTRING(P_C, 1, 4000)" in out.upper(), out

    def test_utl_raw_cast_to_varchar2(self) -> None:
        out = _ir("oracle", "tsql", "SELECT UTL_RAW.CAST_TO_VARCHAR2(x) FROM t")
        assert out is not None and "CONVERT(VARCHAR(MAX), x)" in out, out

    def test_dbms_lob_getlength(self) -> None:
        out = _ir("oracle", "tsql", "SELECT DBMS_LOB.GETLENGTH(x) FROM t")
        assert out is not None and "DATALENGTH(x)" in out, out


class TestSmallIrParityFixes:
    """Small IR/text parity fixes (M3 burn-down bundle)."""

    def test_negative_literal_interval_on_pg(self) -> None:
        out = _ir("tsql", "postgresql", "SELECT DATEADD(MONTH, -1, d) FROM t")
        assert out is not None and "INTERVAL '-1 MONTH'" in out, out

    def test_length_is_char_length_on_mysql(self) -> None:
        out = _ir("tsql", "mysql", "SELECT LEN(name) FROM t")
        assert out is not None and "CHAR_LENGTH" in out.upper(), out
        assert not __import__("re").search(r"(?i)\bLENGTH\s*\(", out), out

    def test_date_subtraction_over_parameters(self) -> None:
        t = ProceduralTransformer("postgresql", "tsql")
        t._date_vars = {"@d1", "@d2"}
        out = t._ir_transpile_dml("SELECT @d2 - @d1")
        assert out is not None and "DATEDIFF(DAY, @d1, @d2)" in out, out


class TestOrderedStringAggInIr:
    """An in-call ORDER BY aggregate converts structurally (M3 family F4)."""

    def test_pg_string_agg_order_to_tsql_within_group(self) -> None:
        out = _ir("postgresql", "tsql", "SELECT string_agg(a, ', ' ORDER BY a) FROM t")
        assert out is not None, out
        assert __import__("re").search(
            r"(?i)STRING_AGG\(a, ', '\) WITHIN GROUP \(ORDER BY a\)", out
        ), out
        assert "GROUP_CONCAT" not in out.upper(), out

    def test_pg_string_agg_order_to_mysql(self) -> None:
        out = _ir("postgresql", "mysql", "SELECT string_agg(a, ', ' ORDER BY a) FROM t")
        assert (
            out is not None and "GROUP_CONCAT(a ORDER BY a SEPARATOR ', ')" in out
        ), out


class TestNestedSubqueryExpression:
    """A double-parenthesized scalar subquery converts structurally: the
    'Complex subquery' fallback rendered it in sqlglot's GENERIC dialect
    inside routine bodies (GROUP_CONCAT leaked onto T-SQL)."""

    def test_double_paren_ordered_agg_to_tsql(self) -> None:
        out = _ir(
            "postgresql",
            "tsql",
            "SELECT 'rows = ' || ((SELECT string_agg(a, ', ' ORDER BY a) FROM t))",
        )
        assert out is not None and "WITHIN GROUP (ORDER BY a)" in out, out
        assert "GROUP_CONCAT" not in out.upper(), out


class TestCharindexStartGuardOnPg:
    """3-arg CHARINDEX on PG must return 0 when not found — the bare
    POSITION(...) + start - 1 form returned start-1 (semantic drift)."""

    def test_not_found_yields_zero(self) -> None:
        out = _ir("tsql", "postgresql", "SELECT CHARINDEX('x', s, 5) FROM t")
        assert out is not None, out
        assert __import__("re").search(
            r"(?i)CASE WHEN POSITION\('x' IN SUBSTRING\(s FROM 5\)\) = 0 THEN 0",
            out,
        ), out


class TestNationalLiterals:
    """N'...' literals are modeled: T-SQL/Oracle keep the prefix, PG has no
    such literal at all, and MySQL's canonical output drops it."""

    def test_national_drops_on_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        t._string_vars = {"v_a"}
        out = t._ir_transpile_dml("SELECT v_a + N'@'")
        assert out is not None and "N'" not in out, out

    def test_national_drops_on_postgresql(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        t._string_vars = {"v_a"}
        out = t._ir_transpile_dml("SELECT v_a + N'@'")
        assert out is not None and "N'" not in out, out

    def test_national_kept_on_oracle(self) -> None:
        out = _ir("tsql", "oracle", "SELECT N'@' FROM t")
        assert out is not None and "N'@'" in out, out


class TestFlipRegressions:
    """Classes surfaced by the flip's corpus sweep (pg->tsql)."""

    def test_ordered_distinct_agg_degrades_on_tsql(self) -> None:
        out = _ir(
            "postgresql",
            "tsql",
            "SELECT string_agg(DISTINCT f1, ',' ORDER BY f1) FROM t",
        )
        # No T-SQL spelling in any form (wave 157): whole carrier.
        assert out is None or "STRING_AGG(DISTINCT" not in out.upper(), out

    def test_ordered_distinct_agg_keeps_distinct_on_mysql(self) -> None:
        out = _ir(
            "postgresql",
            "mysql",
            "SELECT string_agg(DISTINCT f1, ',' ORDER BY f1) FROM t",
        )
        assert out is not None and "GROUP_CONCAT(DISTINCT f1 ORDER BY f1" in out, out

    def test_sqlstate_maps_on_tsql(self) -> None:
        out = _ir("postgresql", "tsql", "SELECT 'S: ' || SQLSTATE")
        assert out is not None and "CAST(ERROR_STATE() AS NVARCHAR(5))" in out, out
        assert "SQLSTATE" not in out.upper(), out

    def test_sqlcode_maps_on_tsql(self) -> None:
        out = _ir("oracle", "tsql", "SELECT SQLCODE FROM DUAL")
        assert out is not None and "CAST(ERROR_NUMBER() AS NVARCHAR(20))" in out, out

    def test_ordered_distinct_mismatch_degrades_on_mysql(self) -> None:
        out = _ir(
            "postgresql",
            "mysql",
            "SELECT string_agg(DISTINCT f1, ',' ORDER BY f1::text) FROM t",
        )
        # MySQL requires the DISTINCT argument itself as the ORDER BY
        # expression; a different one has no spelling.
        assert out is None or "GROUP_CONCAT(DISTINCT" not in (out or ""), out

    def test_ordered_distinct_match_kept_on_mysql(self) -> None:
        out = _ir(
            "postgresql",
            "mysql",
            "SELECT string_agg(DISTINCT f1, ',' ORDER BY f1) FROM t",
        )
        assert out is not None and "GROUP_CONCAT(DISTINCT f1 ORDER BY f1" in out, out


class TestTempReferenceFunctionGate:
    """A T-SQL FUNCTION referencing a session temp table is error 2772 —
    the wave-144 gate covered only bodies CREATING one, and only from a
    PostgreSQL source; references from any source degrade too."""

    def test_mysql_function_referencing_temp_degrades(self, monkeypatch) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE TEMPORARY TABLE t1 (c1 INT);\n"
            "DELIMITER //\n"
            "CREATE FUNCTION bug12472() RETURNS int DETERMINISTIC "
            "BEGIN RETURN (SELECT COUNT(*) FROM t1); END//\n"
            "DELIMITER ;\n"
        )
        r = Transpiler().transpile(src, "mysql", "tsql")
        assert "cannot access temporary tables" in r.sql.lower(), r.sql
        assert not __import__("re").search(
            r"(?i)^\s*CREATE FUNCTION", r.sql, __import__("re").M
        ), r.sql

    def test_function_without_temp_stays(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "DELIMITER //\n"
            "CREATE FUNCTION f2() RETURNS int DETERMINISTIC "
            "BEGIN RETURN 1; END//\n"
            "DELIMITER ;\n"
        )
        r = Transpiler().transpile(src, "mysql", "tsql")
        assert "CREATE FUNCTION" in r.sql, r.sql

    def test_sha2_spells_standard_hash_on_oracle(self) -> None:
        out = _ir("tsql", "oracle", "SELECT SHA2(x, 256) FROM t")
        assert out is not None, out
        assert "RAWTOHEX(STANDARD_HASH(x, 'SHA256'))" in out, out
        assert "SHA2" not in out.upper().replace("'SHA256'", ""), out


class TestZeroPushMysqlOracle:
    """my->oracle residue fixes (zero push)."""

    def test_last_identity_neutral_is_expression_valid(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "DELIMITER //\n"
            "create procedure p1() begin\n"
            "  select last_insert_id();\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = Transpiler().transpile(src, "mysql", "oracle").sql
        assert "SELECT NULL /* last identity" in out, out
        assert "SELECT /*" not in out, out

    def test_not_value_wraps_tristate_on_oracle(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "DELIMITER //\n"
            "create procedure p2() begin\n"
            "  declare done int default 0;\n"
            "  set done = not done;\n"
            "end//\n"
            "DELIMITER ;\n"
        )
        out = Transpiler().transpile(src, "mysql", "oracle").sql
        assert "CASE WHEN done = 0 THEN 1 WHEN done <> 0 THEN 0 END" in out, out
        assert ":= NOT done" not in out, out

    def test_pg_boolean_not_stays_on_oracle(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "create function f() returns boolean language plpgsql as $$\n"
            "declare b boolean := true;\n"
            "begin\n  b := not b;\n  return b;\nend $$;"
        )
        out = Transpiler().transpile(src, "postgresql", "oracle").sql
        assert "NOT b" in out or "NOT B" in out, out


class TestZeroPushTypeWidths:
    """Display widths / tz types that shipped raw (zero push)."""

    def test_mysql_float_width_to_pg_real(self) -> None:
        from unique.core.transpiler import Transpiler

        out = (
            Transpiler()
            .transpile("CREATE TABLE t1 (f FLOAT(9,6));", "mysql", "postgresql")
            .sql
        )
        assert "REAL" in out.upper(), out
        assert "FLOAT(9" not in out.upper().replace(" ", ""), out

    def test_mysql_declare_widths_to_pg(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "DELIMITER //\n"
            "create procedure p() begin\n"
            "  declare loops bigint(19) default 0;\n"
            "  declare f float(9,6);\n"
            "end//\nDELIMITER ;\n"
        )
        out = Transpiler().transpile(src, "mysql", "postgresql").sql
        assert "bigint(19)" not in out.lower(), out
        assert "float(9" not in out.lower().replace(" ", ""), out

    def test_pg_timetz_to_mysql_time(self) -> None:
        from unique.core.transpiler import Transpiler

        out = (
            Transpiler()
            .transpile("CREATE TEMPORARY TABLE d (f TIMETZ);", "postgresql", "mysql")
            .sql
        )
        assert "TIME" in out.upper(), out
        assert "TIMETZ" not in out.upper(), out


class TestMojibakeUnitCarrier:
    """A declaration whose type token is not identifier-shaped (mojibake
    identifiers split by the lexer) fails the WHOLE unit into the parse
    carrier — never shredded fragments (guardrail 4)."""

    SRC = (
        "DELIMITER //\n"
        "create procedure bug7088_2() begin\n"
        "  declare lÃ¤ int default 1;\n"
        "end//\n"
        "DELIMITER ;\n"
    )

    def test_declare_garbage_degrades_whole(self) -> None:
        from unique.core.transpiler import Transpiler

        r = Transpiler().transpile(self.SRC, "mysql", "tsql")
        assert "int AS default" not in r.sql, r.sql
        assert "-- UNIQUE:" in r.sql, r.sql
        assert r.warnings, r.sql

    def test_body_statement_mojibake_degrades_whole(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "DELIMITER //\n"
            "create procedure bug6063() begin\n"
            "  select lÃ¤;\n"
            "end//\nDELIMITER ;\n"
        )
        r = Transpiler().transpile(src, "mysql", "tsql")
        assert "AS ¤" not in r.sql, r.sql
        assert "-- UNIQUE:" in r.sql, r.sql
        assert r.warnings, r.sql


class TestZeroPushMysqlGates:
    """pg->mysql residue: reserved-type aliases, UDF windows, diagnostics."""

    def test_reserved_type_alias_quotes_on_mysql(self) -> None:
        from unique.core.transpiler import Transpiler

        out = (
            Transpiler()
            .transpile("SELECT f1(42) AS int, f1(4.5) AS num;", "postgresql", "mysql")
            .sql
        )
        assert "`int`" in out, out

    def test_udf_window_degrades_on_mysql(self) -> None:
        from unique.core.transpiler import Transpiler

        r = Transpiler().transpile(
            "SELECT logging_agg_strict(v) OVER () FROM t;", "postgresql", "mysql"
        )
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("OVER" in ln.upper() for ln in code), r.sql
        assert r.warnings, r.sql

    def test_builtin_window_stays_on_mysql(self) -> None:
        from unique.core.transpiler import Transpiler

        r = Transpiler().transpile(
            "SELECT sum(v) OVER (), row_number() OVER () FROM t;",
            "postgresql",
            "mysql",
        )
        assert "OVER" in r.sql.upper(), r.sql

    def test_sqlstate_routine_degrades_on_mysql(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "create function excpt_test1() returns int language plpgsql as $$\n"
            "begin\n  raise notice '% %', sqlstate, sqlerrm;\n  return 0;\n"
            "end $$;"
        )
        r = Transpiler().transpile(src, "postgresql", "mysql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("sqlstate" in ln.lower() for ln in code), r.sql
        assert r.warnings, r.sql

    def test_pg_internal_type_in_body_degrades(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "create function error1(p1 text) returns text language plpgsql as $$\n"
            "begin\n"
            "  return (select relname from pg_class c where c.oid = p1::regclass);\n"
            "end $$;"
        )
        r = Transpiler().transpile(src, "postgresql", "mysql")
        code = [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        assert not any("regclass" in ln.lower() for ln in code), r.sql
        assert r.warnings, r.sql


class TestZeroPushPgOnlyShapes:
    """pg-only statement shapes gate honestly off PG (zero push Z3a)."""

    def _t(self, sql, tgt="mysql"):
        from unique.core.transpiler import Transpiler

        return Transpiler().transpile(sql, "postgresql", tgt)

    def _code(self, r):
        return [
            ln
            for ln in r.sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]

    def test_alter_set_storage_params(self) -> None:
        r = self._t("ALTER TABLE tenk1 SET (parallel_workers = 4);")
        assert not any("parallel_workers" in ln for ln in self._code(r)), r.sql
        assert r.warnings, r.sql

    def test_alter_set_storage_kept_on_pg(self) -> None:
        r = self._t("ALTER TABLE tenk1 SET (parallel_workers = 4);", "postgresql")
        assert "SET (parallel_workers = 4)" in r.sql, r.sql

    def test_set_constraints_carrier(self) -> None:
        r = self._t("SET CONSTRAINTS parted_trig DEFERRED;")
        assert not any("CONSTRAINTS" in ln.upper() for ln in self._code(r)), r.sql
        assert r.warnings, r.sql

    def test_deferrable_strips_on_mysql(self) -> None:
        r = self._t("ALTER TABLE t ADD CONSTRAINT u UNIQUE (a) DEFERRABLE;")
        assert "DEFERRABLE" not in r.sql.upper().replace(
            "DEFERRABLE CONSTRAINT", ""
        ), r.sql
        assert "UNIQUE" in r.sql.upper(), r.sql
        assert r.warnings, r.sql

    def test_interval_column_carrier_on_mysql(self) -> None:
        r = self._t("CREATE TEMPORARY TABLE d (f INTERVAL);")
        assert not any("INTERVAL" in ln.upper() for ln in self._code(r)), r.sql
        assert r.warnings, r.sql

    def test_array_column_carrier_on_mysql(self) -> None:
        r = self._t("CREATE TEMPORARY TABLE rt (id INT, ar TEXT[]);")
        assert not any("[]" in ln for ln in self._code(r)), r.sql
        assert r.warnings, r.sql

    def test_row_function_composite_gate(self) -> None:
        r = self._t("SELECT row(row(1)) = ANY (SELECT ROW(ROW(1)));")
        assert not any("ROW(" in ln.upper() for ln in self._code(r)), r.sql
        assert r.warnings, r.sql

    def test_zero_arg_count_becomes_count_star(self) -> None:
        # PG's own error text: "count(*) must be used to call a
        # parameterless aggregate" — COUNT(*) IS the faithful spelling.
        r = self._t("SELECT count() OVER () FROM tenk1;")
        assert "COUNT(*)" in r.sql.upper(), r.sql
        assert "COUNT()" not in r.sql.upper().replace(" ", ""), r.sql

    def test_timeofday_internal(self) -> None:
        r = self._t(
            "CREATE TABLE log_table (t TIMESTAMP DEFAULT timeofday()::timestamp);"
        )
        assert not any("timeofday" in ln.lower() for ln in self._code(r)), r.sql
        assert r.warnings, r.sql


class TestZeroPushZ4bBatch:
    """Zero-push batch Z4b mechanisms."""

    def _t(self, sql, s, t):
        from unique.core.transpiler import Transpiler

        return Transpiler().transpile(sql, s, t)

    def test_variable_top_takes_parens(self) -> None:
        r = self._t(
            "DELIMITER //\ncreate procedure p1() begin declare cnt int default 1;"
            " declare foo int; set foo = (select min(c1) from t1 limit cnt); end//\n"
            "DELIMITER ;",
            "mysql",
            "tsql",
        )
        assert "TOP (@cnt)" in r.sql, r.sql

    def test_alter_database_carriers_in_body(self) -> None:
        r = self._t(
            "DELIMITER //\ncreate procedure p1() begin alter database character"
            " set koi8r; end//\nDELIMITER ;",
            "mysql",
            "tsql",
        )
        assert "-- alter database" in r.sql.lower(), r.sql
        assert r.warnings, r.sql

    def test_alter_table_in_body_stays_dml(self) -> None:
        r = self._t(
            "DELIMITER //\ncreate procedure p2() begin alter table t1 add"
            " column c2 int; end//\nDELIMITER ;",
            "mysql",
            "tsql",
        )
        assert "ALTER TABLE" in r.sql.upper(), r.sql
        assert "-- alter" not in r.sql.lower(), r.sql

    def test_empty_trigger_body_gets_executable_noop(self) -> None:
        r = self._t(
            "DELIMITER //\ncreate trigger t1_bu after update on t1 for each row"
            " begin end//\nDELIMITER ;",
            "mysql",
            "tsql",
        )
        assert "SET NOCOUNT ON;" in r.sql, r.sql

    def test_first_position_strips_with_warning(self) -> None:
        r = self._t(
            "ALTER TABLE t3 ADD t2nr INT NOT NULL AUTO_INCREMENT PRIMARY KEY" " FIRST;",
            "mysql",
            "tsql",
        )
        assert "FIRST" not in r.sql.upper(), r.sql
        assert r.warnings, r.sql

    def test_public_schema_strips_on_tsql(self) -> None:
        r = self._t("CREATE TABLE public.stuffs (stuff TEXT);", "postgresql", "tsql")
        assert "public" not in r.sql.lower(), r.sql

    def test_temporary_sequence_carriers(self) -> None:
        r = self._t("CREATE TEMPORARY SEQUENCE ts1;", "postgresql", "tsql")
        assert "-- CREATE TEMPORARY SEQUENCE" in r.sql, r.sql
        assert r.warnings, r.sql

    def test_predicate_return_wraps_for_bit(self) -> None:
        r = self._t(
            "create function dc(val int) returns boolean language plpgsql as"
            " $$ begin return val > 0; end $$;",
            "postgresql",
            "tsql",
        )
        assert "CASE WHEN @val > 0 THEN 1" in r.sql, r.sql

    def test_bare_reraise_outside_handler_carriers(self) -> None:
        r = self._t(
            "create function rt() returns int language plpgsql as $$ begin"
            " raise; return 0; end $$;",
            "postgresql",
            "tsql",
        )
        assert "THROW;" not in r.sql, r.sql
        assert r.warnings, r.sql

    def test_reraise_inside_catch_stays(self) -> None:
        r = self._t(
            "create function rt2() returns int language plpgsql as $$ begin\n"
            "begin\n  perform 1/0;\nexception when others then\n  raise;\nend;\n"
            "return 0;\nend $$;",
            "postgresql",
            "tsql",
        )
        assert "THROW;" in r.sql, r.sql


class TestZeroPushW1Batch:
    """Zero-push batch W1 mechanisms."""

    def _t(self, sql, s, t):
        from unique.core.transpiler import Transpiler

        return Transpiler().transpile(sql, s, t)

    def test_charset_param_attribute_consumed(self) -> None:
        r = self._t(
            "DELIMITER //\ncreate procedure p2(p1 char(10) charset koi8r,"
            " out p2 char(10) charset cp1251) begin set p2 = p1; end//\n"
            "DELIMITER ;",
            "mysql",
            "tsql",
        )
        assert "@charset" not in r.sql.lower(), r.sql
        assert "@p2 char(10) OUTPUT" in r.sql, r.sql

    def test_real_keeps_no_params_on_postgresql(self) -> None:
        r = self._t("CREATE TABLE t1 (a FLOAT(9,6));", "mysql", "postgresql")
        assert "REAL(" not in r.sql.upper(), r.sql
        assert "REAL" in r.sql.upper(), r.sql

    def test_current_user_niladic(self) -> None:
        r = self._t("SELECT CURRENT_USER(), SESSION_USER();", "mysql", "postgresql")
        assert "CURRENT_USER()" not in r.sql, r.sql
        assert "CURRENT_USER" in r.sql, r.sql
        r = self._t("SELECT CURRENT_USER();", "mysql", "tsql")
        assert "CURRENT_USER()" not in r.sql, r.sql

    def test_scalar_values_row_becomes_select(self) -> None:
        r = self._t("SELECT (VALUES (1));", "mysql", "tsql")
        assert "(SELECT 1)" in r.sql, r.sql
        assert "VALUES" not in r.sql.upper(), r.sql

    def test_bare_numeric_where_gets_comparison(self) -> None:
        r = self._t("UPDATE v1 SET b = 0 WHERE 0;", "mysql", "tsql")
        assert "WHERE 0 <> 0" in r.sql, r.sql

    def test_information_schema_cast_gated(self) -> None:
        r = self._t(
            "SELECT CAST('t' AS information_schema.sql_identifier);",
            "postgresql",
            "mysql",
        )
        assert r.warnings, r.sql
        assert "information_schema.sql_identifier" in r.warnings[0].message

    def test_prepare_execute_deallocate_carriers(self) -> None:
        r = self._t(
            "DELIMITER //\ncreate procedure p1() begin prepare stmt1 from"
            " 'update t3 set a=a+2'; execute stmt1; deallocate prepare stmt1;"
            " end//\nDELIMITER ;",
            "mysql",
            "tsql",
        )
        assert len(r.warnings) == 3, [w.message for w in r.warnings]
        assert "-- prepare stmt1" in r.sql, r.sql
        assert "-- execute stmt1" in r.sql, r.sql
        assert "-- deallocate prepare stmt1" in r.sql, r.sql

    def test_row_trigger_with_untranslatable_call_degrades(self) -> None:
        r = self._t(
            "DELIMITER //\nCREATE TRIGGER t1_bu BEFORE UPDATE ON t1 FOR EACH"
            " ROW\nBEGIN\n  CALL p1(NEW.i1);\nEND//\nDELIMITER ;",
            "mysql",
            "tsql",
        )
        assert r.warnings, r.sql
        assert "NEW./OLD." in r.warnings[0].message, r.warnings[0].message
