# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""M4 Oracle-source closing waves (2026-07-10, bigtest.sql classes).

Each test pins one live-measured defect class from executing the transpiled
13 MB Oracle dump: exception scope on T-SQL/MySQL, trigger headers
(UPDATE OF / WHEN), event predicates, pseudo-row INTO targets, ELSEIF,
Oracle builtins, the ROWNUM top-n idiom and call-argument hygiene.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(src: str, target: str) -> str:
    return Transpiler().transpile(src, "oracle", target).sql


def _flat(sql: str) -> str:
    return " ".join(sql.split())


class TestExceptionScope:
    _SRC = (
        "create or replace PROCEDURE p_pi(p_no IN NUMBER, p_ing OUT NUMBER)\n"
        "AS\nBEGIN\n"
        "    SELECT ningreso INTO p_ing FROM a_ing WHERE numorden = p_no;\n"
        "EXCEPTION\n    WHEN NO_DATA_FOUND THEN\n        p_ing := NULL;\n"
        "END;\n/"
    )

    def test_tsql_try_contains_protected_statements(self) -> None:
        out = _flat(_t(self._SRC, "tsql"))
        # The old flattener emitted an empty BEGIN TRY (syntax error) with
        # the protected SELECT outside it.
        assert re.search(r"(?i)BEGIN TRY\s+SELECT @p_ing = ningreso", out), out
        assert not re.search(r"(?i)BEGIN TRY\s+END TRY", out), out

    def test_mysql_handler_wraps_block_with_not_found(self) -> None:
        out = _flat(_t(self._SRC, "mysql"))
        assert "DECLARE EXIT HANDLER FOR NOT FOUND" in out, out
        # Handler first, then the protected statement, inside one block.
        assert out.index("EXIT HANDLER") < out.index("SELECT ningreso"), out

    def test_mysql_generic_handler_for_others(self) -> None:
        src = self._SRC.replace("NO_DATA_FOUND", "OTHERS")
        out = _flat(_t(src, "mysql"))
        assert "DECLARE EXIT HANDLER FOR SQLEXCEPTION" in out, out


class TestTriggerHeaders:
    def test_update_of_column_list(self) -> None:
        src = (
            "create or replace TRIGGER trg_h AFTER UPDATE OF nombre, sip "
            "ON a_h FOR EACH ROW\nBEGIN\n"
            "    INSERT INTO f_ev (tipo) VALUES ('H');\nEND;\n/"
        )
        # It used to shred the header ('DECLARE @of NOMBRE; DECLARE @, SIP;').
        tsql = _flat(_t(src, "tsql"))
        assert "IF UPDATE(nombre) OR UPDATE(sip)" in tsql, tsql
        assert "@of" not in tsql, tsql
        pg = _t(src, "postgresql")
        assert "AFTER UPDATE OF nombre, sip ON a_h" in pg, pg
        ora = _t(src, "oracle")
        assert "AFTER UPDATE OF nombre, sip ON a_h" in ora, ora
        my = Transpiler().transpile(src, "oracle", "mysql")
        assert "AFTER UPDATE ON a_h" in my.sql, my.sql
        assert any("UPDATE OF" in w.message for w in my.warnings), my.warnings

    def test_when_clause_becomes_if(self) -> None:
        src = (
            "create or replace TRIGGER trg_w AFTER INSERT ON t_d FOR EACH ROW\n"
            "WHEN (NEW.tipo = 'C')\nBEGIN\n"
            "    INSERT INTO t_log (op) VALUES ('I');\nEND;\n/"
        )
        for target in ("mysql", "postgresql"):
            out = _flat(_t(src, target))
            assert re.search(r"(?i)IF NEW\s*\.\s*tipo = 'C' THEN", out), (target, out)
            assert "DECLARE NEW" not in out, (target, out)


class TestEventPredicates:
    _SRC = (
        "create or replace TRIGGER trg_m AFTER INSERT OR UPDATE ON t_d "
        "FOR EACH ROW\nBEGIN\n"
        "    IF INSERTING THEN\n        INSERT INTO t_log (op) VALUES ('I');\n"
        "    END IF;\n"
        "    IF UPDATING('estado') THEN\n"
        "        INSERT INTO t_log (op) VALUES ('U');\n    END IF;\nEND;\n/"
    )

    def test_postgresql_uses_tg_op(self) -> None:
        out = _flat(_t(self._SRC, "postgresql"))
        assert "(TG_OP = 'INSERT')" in out, out
        assert (
            "(TG_OP = 'UPDATE' AND NEW.estado IS DISTINCT FROM OLD.estado)" in out
        ), out

    def test_mysql_resolves_statically_per_event_variant(self) -> None:
        out = _t(self._SRC, "mysql")
        ins, upd = out.split("CREATE TRIGGER trg_m_upd")
        assert "IF (1 = 1) THEN" in ins and "IF (1 = 0) THEN" in ins, out
        assert "(NOT (NEW.estado <=> OLD.estado))" in upd, out

    def test_mysql_uses_elseif(self) -> None:
        src = (
            "create or replace TRIGGER trg_e AFTER INSERT ON t_d FOR EACH ROW\n"
            "BEGIN\n"
            "    IF NEW.a = 1 THEN\n        INSERT INTO t_log (op) VALUES ('1');\n"
            "    ELSIF NEW.a = 2 THEN\n"
            "        INSERT INTO t_log (op) VALUES ('2');\n    END IF;\nEND;\n/"
        )
        out = _flat(_t(src, "mysql"))
        assert "ELSEIF" in out, out
        assert not re.search(r"\bELSIF\b", out), out


class TestPseudoRowIntoTargets:
    _SRC = (
        "create or replace TRIGGER trg_pa BEFORE UPDATE ON u_pam FOR EACH ROW\n"
        "BEGIN\n"
        "    SELECT familia, grupo INTO :NEW.familia, :NEW.grupo\n"
        "    FROM s_art WHERE idarticulo = :NEW.idarticulo;\nEND;\n/"
    )

    def test_postgresql_assigns_record_fields(self) -> None:
        out = _flat(_t(self._SRC, "postgresql"))
        assert "INTO NEW.familia, NEW.grupo" in out, out
        assert ": NEW" not in out, out

    def test_mysql_routes_through_session_variables(self) -> None:
        out = _flat(_t(self._SRC, "mysql"))
        assert "INTO @uq_sel0, @uq_sel1" in out, out
        assert "SET NEW.familia = @uq_sel0;" in out, out
        assert "SET NEW.grupo = @uq_sel1;" in out, out

    def test_call_arguments_map_pseudo_rows(self) -> None:
        src = (
            "create or replace TRIGGER trg_r AFTER INSERT ON t_r FOR EACH ROW\n"
            "BEGIN\n    svp_reg_pro(:NEW.rcn_id, :NEW.usuariomod);\nEND;\n/"
        )
        for target in ("mysql", "postgresql"):
            out = _flat(_t(src, target))
            assert "CALL svp_reg_pro(NEW.rcn_id, NEW.usuariomod);" in out, (
                target,
                out,
            )


class TestOracleBuiltinsOnTsql:
    def test_error_context_and_sys_context(self) -> None:
        src = (
            "create or replace PROCEDURE p_x AS\nBEGIN\n"
            "    UPDATE t_c SET x = 1;\n"
            "EXCEPTION WHEN OTHERS THEN\n"
            "    RAISE_APPLICATION_ERROR(-20001, SQLCODE || ' ' || SQLERRM);\n"
            "END;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "ERROR_MESSAGE()" in out, out
        assert "CAST(ERROR_NUMBER() AS NVARCHAR(20))" in out, out
        # Expression message goes through a variable (RAISERROR takes only
        # literals/variables), and the error code is never the message.
        assert re.search(r"DECLARE @unique_errmsg1 NVARCHAR\(2048\) =", out), out
        assert "RAISERROR(@unique_errmsg1, 16, 1);" in out, out

    def test_chr_trunc_and_lob_helpers(self) -> None:
        src = (
            "create or replace PROCEDURE p_t(p_fecha IN DATE, p_min IN NUMBER, "
            "p_c IN OUT VARCHAR2) AS\n    v_crlf VARCHAR2(4);\nBEGIN\n"
            "    v_crlf := CHR(13) || CHR(10);\n"
            "    p_c := UTL_RAW.CAST_TO_VARCHAR2(DBMS_LOB.SUBSTR(p_c, 4000, 1));\n"
            "    UPDATE t_z SET x = TRUNC(p_min / 60, 0)"
            " WHERE f >= TRUNC(p_fecha);\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "CHAR( 13 ) + CHAR( 10 )" in out.replace("CHAR(13)", "CHAR( 13 )"), out
        assert "CONVERT(VARCHAR(MAX), SUBSTRING(@p_c, 1, 4000) )" in out, out
        assert "ROUND(@p_min / 60, 0, 1)" in out, out
        assert "CAST(@p_fecha AS DATE)" in out, out

    def test_rownum_top_idiom(self) -> None:
        src = (
            "create or replace PROCEDURE p_ev(p_t IN VARCHAR2, p_o OUT VARCHAR2)"
            " AS\nBEGIN\n"
            "    SELECT st INTO p_o FROM (\n"
            "        SELECT st FROM f_ev WHERE tipo = p_t ORDER BY idev DESC\n"
            "    ) WHERE ROWNUM = 1;\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "( SELECT TOP (1) st FROM f_ev" in out, out
        assert "ROWNUM" not in out.upper(), out

    def test_call_args_renamed_and_strings_untouched(self) -> None:
        src = (
            "DECLARE\n    v_codigo VARCHAR2(10);\nBEGIN\n"
            "    v_codigo := 'X';\n"
            "    svp_tipo_ins(v_codigo);\n"
            "    dbms_output.put_line('v_codigo = ' || v_codigo);\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "EXEC svp_tipo_ins @codigo;" in out, out
        assert "'v_codigo = ' + @codigo" in out, out


class TestPgLoopVarShadowing:
    def test_shadowed_row_loop_variable_renamed(self) -> None:
        src = (
            "create or replace PROCEDURE p_l AS\n    X NUMBER(9);\nBEGIN\n"
            "    X := 5;\n"
            "    FOR X IN (SELECT COUNT(*) TOTAL FROM k_tip) LOOP\n"
            "        IF X.TOTAL > 0 THEN\n            UPDATE t_z SET x = 1;\n"
            "        END IF;\n    END LOOP;\nEND;\n/"
        )
        out = _flat(_t(src, "postgresql"))
        assert "FOR X_rec IN" in out, out
        assert "X_rec.TOTAL" in out, out
        # The declared scalar keeps its own uses.
        assert "X := 5;" in out, out
