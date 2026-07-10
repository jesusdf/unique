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


class TestCaseStatement:
    _SRC = (
        "create or replace FUNCTION f_ex(m_tipo IN VARCHAR2) RETURN NUMBER IS\n"
        "    m_cnt NUMBER(9);\nBEGIN\n"
        "    CASE m_tipo\n"
        "        WHEN 'E' THEN RETURN 1;\n"
        "        WHEN 'P' THEN\n"
        "            SELECT COUNT(*) INTO m_cnt FROM f_tax WHERE t = m_tipo;\n"
        "            RETURN m_cnt;\n"
        "        ELSE\n            RETURN 0;\n"
        "    END CASE;\nEND f_ex;\n/"
    )

    def test_case_statement_becomes_if_chain(self) -> None:
        # The PL/SQL CASE *statement* used to desync the whole routine
        # (sqlglot: 'Expected END after CASE').
        tsql = _flat(_t(self._SRC, "tsql"))
        assert "IF @m_tipo = 'E'" in tsql, tsql
        assert "ELSE IF @m_tipo = 'P'" in tsql, tsql
        assert "END CASE" not in tsql.upper(), tsql
        pg = _flat(_t(self._SRC, "postgresql"))
        assert "IF m_tipo = 'E' THEN" in pg, pg
        assert "ELSIF m_tipo = 'P' THEN" in pg, pg
        my = _flat(_t(self._SRC, "mysql"))
        assert "ELSEIF m_tipo = 'P' THEN" in my, my

    def test_searched_case_statement(self) -> None:
        src = (
            "BEGIN\n    CASE\n        WHEN 1 = 1 THEN\n"
            "            UPDATE t_z SET x = 1;\n"
            "        ELSE\n            UPDATE t_z SET x = 2;\n"
            "    END CASE;\nEND;\n/"
        )
        out = _flat(_t(src, "postgresql"))
        assert "IF 1 = 1 THEN" in out, out
        assert re.search(r"(?i)ELSE\s+UPDATE t_z SET x = 2", out), out


class TestOracleCatalogOnTsql:
    def test_table_less_drop_index_resolves_table(self) -> None:
        # Oracle's DROP INDEX names only the index; T-SQL requires the
        # table (error 159) — resolved from sys.indexes at run time.
        # Live-validated on MSSQL (executes and is idempotent), 2026-07-10.
        src = (
            "DECLARE v_exists NUMBER;\nBEGIN\n"
            "    SELECT count(*) INTO v_exists FROM user_indexes"
            " WHERE index_name = 'IX_H_F10';\n"
            "    IF v_exists = 1 THEN\n"
            "        execute immediate 'DROP INDEX IX_H_F10';\n"
            "    END IF;\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "FROM sys.indexes WHERE name = 'IX_H_F10'" in out, out
        assert "OBJECT_NAME(object_id)" in out, out
        assert "EXEC(N'DROP INDEX [IX_H_F10] ON [' + @uq_ixtbl" in out, out
        assert "user_indexes" not in out, out

    def test_unsized_varchar_parameters(self) -> None:
        src = (
            "create or replace FUNCTION f_id(m_t IN VARCHAR2) RETURN VARCHAR2"
            " IS\nBEGIN\n    RETURN m_t;\nEND;\n/"
        )
        tsql = _t(src, "tsql")
        # Bare NVARCHAR silently truncates to length 1.
        assert "@m_t NVARCHAR(4000)" in tsql, tsql
        assert "RETURNS NVARCHAR(4000)" in tsql, tsql
        my = _t(src, "mysql")
        # Bare VARCHAR is a MySQL syntax error.
        assert "m_t TEXT" in my, my
        assert "RETURNS TEXT" in my, my


class TestPgRowLoopDeclaration:
    def test_implicit_loop_variable_gets_record_declaration(self) -> None:
        # plpgsql requires the row-loop variable to be declared (PL/SQL
        # declares it implicitly). Live-validated idempotent, 2026-07-10.
        src = (
            "BEGIN FOR X IN (SELECT COUNT(*) TOTAL FROM h_wc WHERE l='x')"
            " LOOP\n    IF X.TOTAL = 0 THEN\n"
            "        INSERT INTO h_wc(l) VALUES ('x');\n"
            "    END IF;\nEND LOOP; END;\n/"
        )
        out = _t(src, "postgresql")
        flat = _flat(out)
        assert "DO $$" in flat, out
        assert re.search(r"(?i)DECLARE\s+X record;", flat), out
        assert flat.index("X record;") < flat.index("FOR X IN"), out


class TestWave10Classes:
    def test_index_nulls_emulation_stripped(self) -> None:
        # sqlglot pairs Oracle index keys with CASE WHEN col IS NULL
        # ordering emulation; a T-SQL index key cannot be an expression.
        src = "CREATE INDEX ix1 ON h_log (accion, tipo);"
        out = _flat(_t(src, "tsql"))
        assert "CASE" not in out.upper(), out
        assert re.search(r"(?i)ON h_log\s*\(accion, tipo\)", out), out
        # The guarded/embedded path strips it too.
        guarded = (
            "DECLARE v_e NUMBER;\nBEGIN\n"
            "    SELECT count(*) INTO v_e FROM user_indexes"
            " WHERE index_name = 'IX1';\n"
            "    IF v_e = 0 THEN\n"
            "        execute immediate 'CREATE INDEX ix1 ON h_log (accion, tipo)';\n"
            "    END IF;\nEND;\n/"
        )
        out2 = _flat(_t(guarded, "tsql"))
        assert "CASE" not in out2.upper(), out2

    def test_multicolumn_drop(self) -> None:
        src = "ALTER TABLE d_idi DROP (descripcion, textoplano);"
        pg = _flat(_t(src, "postgresql"))
        assert "DROP COLUMN descripcion, DROP COLUMN textoplano" in pg, pg
        my = _flat(_t(src, "mysql"))
        assert "DROP COLUMN descripcion, DROP COLUMN textoplano" in my, my
        ts = _flat(_t(src, "tsql"))
        assert "DROP COLUMN descripcion, textoplano" in ts, ts

    def test_mysql_errno_magnitude(self) -> None:
        src = (
            "create or replace PROCEDURE p_e AS\nBEGIN\n"
            "    UPDATE t_z SET x = 1;\n"
            "EXCEPTION WHEN OTHERS THEN\n"
            "    RAISE_APPLICATION_ERROR(-20001, 'boom');\nEND;\n/"
        )
        out = _flat(_t(src, "mysql"))
        assert "MYSQL_ERRNO = 20001" in out, out
        assert "MYSQL_ERRNO = - " not in out, out

    def test_pipelined_function_becomes_carrier(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f_pipe (v_e IN VARCHAR2)\n"
            "RETURN pkg_t.t_tab PIPELINED\nAS\n    newrow pkg_t.t_row;\n"
            "BEGIN\n    PIPE ROW (newrow);\n    RETURN;\nEND;\n/"
        )
        for target in ("mysql", "tsql", "postgresql"):
            result = Transpiler().transpile(src, "oracle", target)
            body = [
                line
                for line in result.sql.splitlines()
                if line.strip() and not line.lstrip().startswith("--")
            ]
            assert not body, (target, result.sql)
            assert any(
                "carrier" in w.message or "preserved" in w.message
                for w in result.warnings
            ), (target, result.warnings)

    def test_blob_column_add_sizes_varbinary(self) -> None:
        src = "ALTER TABLE d_diar ADD firma BLOB NULL;"
        assert "LONGBLOB" in _t(src, "mysql")
        assert "VARBINARY(MAX)" in _t(src, "tsql")
        assert "BYTEA" in _t(src, "postgresql")

    def test_standalone_scalars_on_tsql(self) -> None:
        pairs = (
            ("SELECT 'a' || CHR(38) || 'b' FROM t_l;", "CHAR(38)"),
            (
                "SELECT s FROM t_s ORDER BY TO_NUMBER(ser_id) ASC;",
                "CAST(ser_id AS DECIMAL(38, 10))",
            ),
            (
                "SELECT MONTHS_BETWEEN(f1, f2) FROM t_h;",
                "DATEDIFF(MONTH, f2, f1)",
            ),
        )
        for src, expected in pairs:
            out = _flat(_t(src, "tsql"))
            assert expected in out, (src, out)

    def test_pg_reserved_column_and_toplevel_noop(self) -> None:
        src = "CREATE TABLE t_tx (data_ep DATE, session_user VARCHAR2(100));"
        out = _t(src, "postgresql")
        assert '"session_user"' in out, out
        carrier = "BEGIN\n    DBMS_SCHEDULER.ENABLE(NAME => 'J1');\nEND;\n/"
        out2 = _t(carrier, "postgresql")
        body = [
            line
            for line in out2.splitlines()
            if line.strip() and not line.lstrip().startswith("--")
        ]
        assert not body, out2


class TestDynamicSqlAndRowcount:
    def test_constant_execute_immediate_unwraps(self) -> None:
        # PostgreSQL has no top-level EXECUTE '<sql>'; a constant dynamic
        # statement is just that statement on every target.
        src = (
            "BEGIN\n    EXECUTE IMMEDIATE 'DELETE FROM E_CONF WHERE D LIKE "
            "''tipo%'' OR D LIKE ''ordenf''';\nEND;\n/"
        )
        for target in ("postgresql", "tsql", "mysql"):
            out = _flat(_t(src, target))
            assert "DELETE FROM E_CONF WHERE D LIKE 'tipo%'" in out, (target, out)
            assert "EXECUTE" not in out.upper(), (target, out)

    def test_sql_rowcount_maps_to_at_at_rowcount(self) -> None:
        src = (
            "BEGIN\n    LOOP\n        DELETE FROM e_c WHERE x = 1;\n"
            "        IF SQL%ROWCOUNT = 0 THEN\n            EXIT;\n"
            "        END IF;\n    END LOOP;\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "IF @@ROWCOUNT = 0" in out, out


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
