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

import sqlglot

from unique.core.transpiler import Transpiler


def _t(src: str, target: str) -> str:
    return Transpiler().transpile(src, "oracle", target).sql


def _flat(sql: str) -> str:
    return " ".join(sql.split())


class TestExceptionScope:
    _SRC = (
        "create or replace PROCEDURE p_pi(p_no IN NUMBER, p_ing OUT NUMBER)\n"
        "AS\nBEGIN\n"
        "    SELECT nregistro INTO p_ing FROM a_reg WHERE numlinea = p_no;\n"
        "EXCEPTION\n    WHEN NO_DATA_FOUND THEN\n        p_ing := NULL;\n"
        "END;\n/"
    )

    def test_tsql_try_contains_protected_statements(self) -> None:
        out = _flat(_t(self._SRC, "tsql"))
        # The old flattener emitted an empty BEGIN TRY (syntax error) with
        # the protected SELECT outside it.
        assert re.search(r"(?i)BEGIN TRY\s+SELECT @p_ing = nregistro", out), out
        assert not re.search(r"(?i)BEGIN TRY\s+END TRY", out), out

    def test_mysql_handler_wraps_block_with_not_found(self) -> None:
        out = _flat(_t(self._SRC, "mysql"))
        assert "DECLARE EXIT HANDLER FOR NOT FOUND" in out, out
        # Handler first, then the protected statement, inside one block.
        assert out.index("EXIT HANDLER") < out.index("SELECT nregistro"), out

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
        "    FROM s_elem WHERE idelemento = :NEW.idelemento;\nEND;\n/"
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
            "BEGIN\n    prc_reg_pro(:NEW.rcn_id, :NEW.moduser);\nEND;\n/"
        )
        for target in ("mysql", "postgresql"):
            out = _flat(_t(src, target))
            assert "CALL prc_reg_pro(NEW.rcn_id, NEW.moduser);" in out, (
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
        assert re.search(r"CHAR\s*\(\s*13\s*\)\s*\+\s*CHAR\s*\(\s*10\s*\)", out), out
        assert "CHR" not in out.upper(), out
        assert re.search(
            r"CONVERT\(VARCHAR\(MAX\), SUBSTRING\(@p_c, 1, 4000\)\s*\)", out
        ), out
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
            "    prc_tipo_ins(v_codigo);\n"
            "    dbms_output.put_line('v_codigo = ' || v_codigo);\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "EXEC prc_tipo_ins @codigo;" in out, out
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
        src = "ALTER TABLE d_lang DROP (descripcion, textolargo);"
        pg = _flat(_t(src, "postgresql"))
        assert "DROP COLUMN descripcion, DROP COLUMN textolargo" in pg, pg
        my = _flat(_t(src, "mysql"))
        assert "DROP COLUMN descripcion, DROP COLUMN textolargo" in my, my
        ts = _flat(_t(src, "tsql"))
        assert "DROP COLUMN descripcion, textolargo" in ts, ts

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


class TestWave11Classes:
    def test_alter_modify_per_target(self) -> None:
        # Neither Oracle MODIFY form parses in sqlglot; the shared rewriter
        # owns the per-target spelling (both pipelines).
        src = "ALTER TABLE d_tb MODIFY r1 NUMBER(9) NULL;"
        ts = _flat(_t(src, "tsql"))
        assert "ALTER COLUMN r1 NUMERIC(9) NULL" in ts, ts
        pg = _flat(_t(src, "postgresql"))
        assert "ALTER COLUMN r1 TYPE NUMERIC(9)" in pg, pg
        assert "ALTER COLUMN r1 DROP NOT NULL" in pg, pg
        my = _flat(_t(src, "mysql"))
        assert "MODIFY COLUMN r1 DECIMAL(9) NULL" in my, my

    def test_alter_modify_inside_guard(self) -> None:
        src = (
            "DECLARE v_e NUMBER;\nBEGIN\n"
            "    SELECT count(*) INTO v_e FROM user_tab_cols"
            " WHERE table_name = 'D_TB' AND column_name = 'R1';\n"
            "    IF v_e = 1 THEN\n"
            "        execute immediate"
            " 'ALTER TABLE D_TB MODIFY R1 NUMBER(9) NULL';\n"
            "    END IF;\nEND;\n/"
        )
        ts = _flat(_t(src, "tsql"))
        assert "ALTER COLUMN R1 NUMERIC(9) NULL" in ts, ts
        # The probe reads the native catalog with matching semantics.
        assert (
            "FROM sys.columns WHERE OBJECT_NAME(object_id) = 'D_TB'"
            " AND name = 'R1'" in ts
        ), ts
        pg = _flat(_t(src, "postgresql"))
        assert "ALTER COLUMN R1 TYPE NUMERIC(9)" in pg, pg
        assert (
            "FROM information_schema.columns WHERE table_name = lower('D_TB')"
            " AND column_name = lower('R1')" in pg
        ), pg

    def test_alter_trigger_enable_per_target(self) -> None:
        src = (
            "BEGIN\n    IF 1 = 1 THEN\n"
            "        ALTER TRIGGER tri_ref_upd ENABLE;\n"
            "    END IF;\nEND;\n/"
        )
        ts = _flat(_t(src, "tsql"))
        assert "FROM sys.triggers WHERE name = 'tri_ref_upd'" in ts, ts
        assert "ENABLE TRIGGER [tri_ref_upd]" in ts, ts
        pg = _flat(_t(src, "postgresql"))
        assert "FROM pg_trigger WHERE tgname = lower('tri_ref_upd')" in pg, pg
        assert "EXECUTE COALESCE((SELECT format(" in pg, pg


class TestWave12And13Classes:
    def test_exec_expression_argument_hoisted(self) -> None:
        # T-SQL EXEC arguments accept only literals/variables; a GETDATE()
        # value (Oracle SYSDATE) made whole seeding batches invalid.
        src = "BEGIN\n    PRC_MED_INS(V_ID=>1, V_modstamp=>SYSDATE);\nEND;\n/"
        out = _flat(_t(src, "tsql"))
        assert re.search(r"DECLARE @uq_now\d+ DATETIME = GETDATE\(\);", out), out
        assert re.search(r"@V_modstamp = @uq_now\d+", out), out
        assert "= GETDATE()" not in out.split("EXEC", 1)[1], out

    def test_named_association_lhs_not_renamed(self) -> None:
        # A local named like the callee's parameter turned 'V_ID => V_ID'
        # into '@id => @id' and the T-SQL spelling into '@@id'.
        src = (
            "DECLARE\n   V_ID NUMBER(9,0);\nBEGIN\n    V_ID := -1;\n"
            "    PRC_MED_INS(V_ID=>V_ID, V_tipo=>'LEU');\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert "@V_ID = @id" in out, out
        assert "@@" not in out, out

    def test_rownum_derived_table_gets_alias(self) -> None:
        src = (
            "create or replace PROCEDURE p_ev(p_t IN VARCHAR2, p_o OUT NUMBER)"
            " AS\n    v_s NUMBER(1);\nBEGIN\n"
            "    SELECT st INTO v_s FROM (\n"
            "        SELECT st FROM f_ev WHERE tipo = p_t ORDER BY idev DESC\n"
            "    ) WHERE ROWNUM = 1;\n    p_o := v_s;\nEND;\n/"
        )
        out = _flat(_t(src, "tsql"))
        assert re.search(r"ORDER BY idev DESC \) AS uq_top;", out), out

    def test_derived_table_alias_synthesized(self) -> None:
        # Only Oracle allows an alias-less derived table.
        src = (
            "INSERT INTO d_conf (a, b)\n"
            "SELECT SEQ_d_conf.NEXTVAL, idc\n"
            "FROM (select idc from d_conf group by idc order by idc);"
        )
        ts = _flat(_t(src, "tsql"))
        assert ") uq_dt" in ts, ts
        # ORDER BY without TOP drops inside the derived table on T-SQL.
        assert "ORDER BY" not in ts.upper(), ts
        pg = _flat(_t(src, "postgresql"))
        assert ") uq_dt" in pg, pg
        my = _flat(_t(src, "mysql"))
        assert ") uq_dt" in my, my

    def test_sequence_refs_per_target(self) -> None:
        src = "INSERT INTO t_x (id) SELECT seq_x.NEXTVAL FROM t_y;"
        assert "NEXT VALUE FOR seq_x" in _t(src, "tsql")
        assert "nextval('seq_x')" in _t(src, "postgresql")


class TestDynamicSqlAndRowcount:
    def test_constant_execute_immediate_unwraps(self) -> None:
        # PostgreSQL has no top-level EXECUTE '<sql>'; a constant dynamic
        # statement is just that statement on every target.
        src = (
            "BEGIN\n    EXECUTE IMMEDIATE 'DELETE FROM E_CONF WHERE D LIKE "
            "''tipo%'' OR D LIKE ''lineaf''';\nEND;\n/"
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


class TestOracleScalarsOnTsqlWave16:
    """Scalar leaks measured in the 2026-07-11 sweep (error 195/156 on the
    live engine): EXTRACT reaching T-SQL (no such builtin — DATEPART),
    numeric 2-arg TRUNC, RPAD/LPAD (sqlglot canonicalizes to Pad, which
    emitted as a phantom PAD()), EMPTY_BLOB/EMPTY_CLOB initializers, and
    TO_NUMBER inside procedural raw expressions."""

    def test_extract_standalone_becomes_datepart(self) -> None:
        out = _t("UPDATE t SET a = EXTRACT(YEAR FROM d);", "tsql")
        assert re.search(r"(?i)DATEPART\s*\(\s*YEAR\s*,", out), out
        assert "EXTRACT" not in out.upper(), out

    def test_extract_procedural_becomes_datepart(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_x(m_out OUT NUMBER) AS\n"
            "BEGIN\n"
            "  m_out := EXTRACT(YEAR FROM SYSDATE) - EXTRACT(MONTH FROM SYSDATE);\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?i)DATEPART\s*\(\s*YEAR\s*,", out), out
        assert re.search(r"(?i)DATEPART\s*\(\s*MONTH\s*,", out), out
        assert "EXTRACT" not in out.upper(), out

    def test_trunc_two_arg_numeric(self) -> None:
        out = _t("SELECT TRUNC(m / 60, 0) FROM t;", "tsql")
        assert re.search(r"(?i)ROUND\s*\(.*,\s*0\s*,\s*1\s*\)", out), out
        assert "TRUNC" not in out.upper(), out
        out_my = _t("SELECT TRUNC(m / 60, 0) FROM t;", "mysql")
        assert re.search(r"(?i)TRUNCATE\s*\(.*,\s*0\s*\)", out_my), out_my

    def test_rpad_lpad(self) -> None:
        out = _t("SELECT RPAD(c, 5, 'x') FROM t;", "tsql")
        assert re.search(r"(?i)LEFT\s*\(", out), out
        assert re.search(r"(?i)REPLICATE\s*\(", out), out
        assert "PAD" not in re.sub(r"(?i)REPLICATE", "", out).upper(), out
        out_l = _t("SELECT LPAD(c, 5, '0') FROM t;", "tsql")
        # LPAD builds from LEFT(REPLICATE(...)) so a multi-char pad aligns.
        assert re.search(r"(?i)LEFT\s*\(\s*REPLICATE", out_l), out_l
        # PG/MySQL keep the native spelling — never the canonical PAD().
        out_pg = _t("SELECT RPAD(c, 5, 'x') FROM t;", "postgresql")
        assert re.search(r"(?i)RPAD\s*\(", out_pg), out_pg
        out_my = _t("SELECT LPAD(c, 5, '0') FROM t;", "mysql")
        assert re.search(r"(?i)LPAD\s*\(", out_my), out_my

    def test_empty_blob_clob(self) -> None:
        out = _t("UPDATE t SET a = EMPTY_BLOB(), b = EMPTY_CLOB();", "tsql")
        assert "EMPTY_BLOB" not in out.upper(), out
        assert "EMPTY_CLOB" not in out.upper(), out
        assert "0x" in out, out

    def test_to_number_in_procedural_raw(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_n(m_out OUT NUMBER, m_c IN VARCHAR2) AS\n"
            "BEGIN\n"
            "  IF TO_NUMBER(m_c) > 5 THEN\n"
            "    m_out := TO_NUMBER(m_c);\n"
            "  END IF;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "TO_NUMBER" not in out.upper(), out
        assert re.search(r"(?i)CAST\s*\(\s*@m_c\s+AS\s+DECIMAL", out), out
        # And never the broken bare-CAST rename: CAST(x) without AS.
        assert not re.search(r"(?i)CAST\s*\(\s*@m_c\s*\)", out), out


class TestFormattedToDateToCharWave17:
    """Formatted TO_CHAR/TO_DATE in procedural raw expressions (5x live,
    2026-07-11): TO_CHAR(x, 'fmt') has a faithful T-SQL spelling via FORMAT
    with the .NET model (the DML pipeline already owns the token
    translation); TO_DATE(x, 'fmt') maps to CONVERT(DATETIME, x, style) for
    the common unambiguous formats. Unknown formats stay visible."""

    def test_to_char_with_date_format(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_f(m_out OUT VARCHAR2, m_d IN DATE) AS\n"
            "BEGIN\n"
            "  m_out := to_char(m_d, 'DD/MM/YYYY HH24:MI:SS');\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert re.search(
            r"(?i)FORMAT\s*\(\s*@m_d\s*,\s*'dd/MM/yyyy HH:mm:ss'", out
        ), out
        assert "TO_CHAR" not in out.upper(), out

    def test_to_date_literal_with_format(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_f2(m_ok OUT NUMBER, m_d IN DATE) AS\n"
            "BEGIN\n"
            "  IF m_d >= TO_DATE('01/01/2017 00:00:00', 'DD/MM/YYYY HH24:MI:SS') THEN\n"
            "    m_ok := 1;\n"
            "  END IF;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "TO_DATE" not in out.upper(), out
        assert re.search(
            r"(?i)CONVERT\s*\(\s*DATETIME\s*,\s*'01/01/2017 00:00:00'\s*,\s*103\s*\)",
            out,
        ), out

    def test_to_date_iso_format(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_f3(m_out OUT NUMBER, m_c IN VARCHAR2) AS\n"
            "BEGIN\n"
            "  m_out := DATEPART(YEAR, TO_DATE(m_c, 'YYYY-MM-DD'));\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "TO_DATE" not in out.upper(), out
        assert re.search(
            r"(?i)CONVERT\s*\(\s*DATETIME\s*,\s*@m_c\s*,\s*120\s*\)", out
        ), out

    def test_unknown_format_stays_visible(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_f4(m_out OUT DATE, m_c IN VARCHAR2) AS\n"
            "BEGIN\n"
            "  m_out := TO_DATE(m_c, 'J');\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "TO_DATE" in out.upper(), out

    def test_numeric_to_char_mask_is_not_formatted_as_date(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_f5(m_out OUT VARCHAR2, m_n IN NUMBER) AS\n"
            "BEGIN\n"
            "  m_out := TO_CHAR(m_n, '99999');\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        # A numeric mask through the date-token table would be garbage;
        # it must not become FORMAT(x, '<date tokens>').
        assert not re.search(r"(?i)FORMAT\s*\(\s*@m_n\s*,\s*'[^']*[dMyHms]", out), out


class TestRawGuidDefaultOnPg:
    """Oracle ``RAW(16) DEFAULT SYS_GUID()`` maps types to BYTEA but the
    default to gen_random_uuid() — a uuid, which PostgreSQL rejects against
    a bytea column (42804, live 2x). The default must produce bytea."""

    def test_bytea_column_gets_bytea_default(self) -> None:
        out = _t(
            "CREATE TABLE h_x (IDL RAW(16) DEFAULT SYS_GUID() NOT NULL, "
            "LANG VARCHAR2(5));",
            "postgresql",
        )
        assert "BYTEA" in out.upper(), out
        assert re.search(
            r"(?i)DEFAULT\s+DECODE\s*\(\s*REPLACE\s*\(\s*gen_random_uuid\(\)::TEXT",
            out,
        ), out

    def test_non_bytea_uuid_default_untouched(self) -> None:
        # A VARCHAR2(36) guid column keeps a text-typed default instead.
        out = _t(
            "CREATE TABLE h_y (IDL VARCHAR2(40) DEFAULT SYS_GUID());",
            "postgresql",
        )
        assert "DECODE" not in out.upper(), out


class TestEmbeddedAlterAddColumns:
    """An ALTER unwrapped from a constant EXECUTE IMMEDIATE (or written
    directly in a block) took the raw-sqlglot fallback, whose oracle→pg
    output spells Oracle's multi-column ADD as ``ADD COLUMNS (…)`` —
    invalid everywhere (42601 live). Routed through the IR passthrough
    emitter, which owns _portable_alter_add."""

    _SRC = (
        "DECLARE\n"
        "  V_X VARCHAR2(100);\n"
        "BEGIN\n"
        "  EXECUTE IMMEDIATE 'ALTER TABLE a_pre ADD (OBS CLOB, NUM NUMBER(9))';\n"
        "END;\n/"
    )

    def test_add_columns_never_reaches_pg(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert "ADD COLUMNS" not in out.upper(), out
        assert re.search(r"(?i)ADD\s+OBS\s+TEXT", out), out
        assert re.search(r"(?i)ADD\s+NUM\s+", out), out

    def test_add_columns_never_reaches_mysql_or_tsql(self) -> None:
        for target in ("mysql", "tsql"):
            out = _t(self._SRC, target)
            assert "ADD COLUMNS" not in out.upper(), (target, out)


class TestNestedBlockLoopRecordOnPg:
    """A cursor FOR loop inside a NESTED begin/end block: the auto-declared
    plpgsql record landed inside the nested block's body as a bare
    ``X record;`` statement (42601 live) — the PG anonymous-block emitter
    did its own shallow declaration split instead of the shared
    _split_declarations (whose pull_nested hoists from nested bodies)."""

    _SRC = (
        "DECLARE\n"
        "  V_PL VARCHAR2(10);\n"
        "BEGIN\n"
        "  V_PL := 'A';\n"
        "  BEGIN\n"
        "    FOR X IN (SELECT COUNT(*) TOTAL FROM t WHERE c = V_PL) LOOP\n"
        "      IF X.TOTAL = 0 THEN\n"
        "        NULL;\n"
        "      END IF;\n"
        "    END LOOP;\n"
        "  END;\n"
        "END;\n/"
    )

    def test_record_declaration_hoists_to_declare_section(self) -> None:
        out = _t(self._SRC, "postgresql")
        head, _, body = out.partition("BEGIN")
        assert re.search(r"(?i)\bX record;", head), out
        assert not re.search(r"(?i)\bX record;", body), out


class TestSysdateWithEmptyParens:
    """Real dumps carry ``SYSDATE()`` — invalid even on Oracle (a client
    code generator emitted it), so sqlglot's RAISE parse fails and the WARN
    fallback built ``CURRENT_TIMESTAMP AS ()`` (42601 live). parse_sql now
    retries a failed oracle parse with the niladic spelling normalized, and
    the procedural now-pattern accepts the empty parens."""

    def test_embedded_insert_value(self) -> None:
        src = (
            "DECLARE\n"
            "  v_n NUMERIC;\n"
            "BEGIN\n"
            "  insert into t values(1, SYSDATE(), 0);\n"
            "END;\n/"
        )
        out = _t(src, "postgresql")
        assert "AS ()" not in out, out
        assert "SYSDATE" not in out.upper(), out
        assert re.search(r"(?i)CURRENT_TIMESTAMP", out), out

    def test_procedural_assignment(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_sd(m_out OUT DATE) AS\n"
            "BEGIN\n"
            "  m_out := SYSDATE();\n"
            "END;\n/"
        )
        for target, idiom in (
            ("postgresql", "CURRENT_TIMESTAMP"),
            ("tsql", "GETDATE()"),
        ):
            out = _t(src, target)
            assert "SYSDATE" not in out.upper(), (target, out)
            assert idiom in out.upper(), (target, out)

    def test_standalone_insert(self) -> None:
        out = _t("insert into t values(1, SYSDATE(), 0);", "postgresql")
        assert "AS ()" not in out, out
        assert "SYSDATE" not in out.upper(), out


class TestCaseInsensitiveVarRename:
    """Oracle identifiers are case-insensitive; the oracle→tsql variable
    rename map matched case-sensitively, so a body reference written in a
    different case than its declaration kept the bare name (error 128
    live: PRINT inside CATCH referencing v_x while the map holds V_X)."""

    def test_lowercase_reference_is_renamed(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_ci(V_TIPO IN VARCHAR2) AS\n"
            "BEGIN\n"
            "  BEGIN\n"
            "    UPDATE t SET c = 1 WHERE x = V_TIPO;\n"
            "  EXCEPTION\n"
            "    WHEN NO_DATA_FOUND THEN\n"
            "      dbms_output.put_line('No existe ' || v_tipo);\n"
            "  END;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert not re.search(r"(?<![@\w])v_tipo\b", out), out
        assert out.count("@tipo") >= 2, out

    def test_string_literal_mentioning_the_name_is_untouched(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_ci2(V_TIPO IN VARCHAR2) AS\n"
            "BEGIN\n"
            "  dbms_output.put_line('el valor de v_tipo es ' || v_tipo);\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "'el valor de v_tipo es '" in out, out


class TestCursorAttributesOnTsql:
    """Oracle cursor attributes leaking raw into T-SQL (4145 live:
    ``WHILE C_X % FOUND``). Named-cursor %FOUND/%NOTFOUND read
    @@FETCH_STATUS; the implicit SQL%FOUND/%NOTFOUND read @@ROWCOUNT."""

    def test_named_cursor_found(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_cf AS\n"
            "  CURSOR c_t IS SELECT a FROM t;\n"
            "  v_a NUMBER;\n"
            "BEGIN\n"
            "  OPEN c_t;\n"
            "  FETCH c_t INTO v_a;\n"
            "  WHILE c_t%FOUND LOOP\n"
            "    FETCH c_t INTO v_a;\n"
            "  END LOOP;\n"
            "  CLOSE c_t;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "%" not in out.replace("%TYPE", ""), out
        assert re.search(r"(?i)@@FETCH_STATUS\s*=\s*0", out), out

    def test_implicit_sql_found(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_sf(m_ok OUT NUMBER) AS\n"
            "BEGIN\n"
            "  UPDATE t SET a = 1 WHERE b = 2;\n"
            "  IF SQL%NOTFOUND THEN\n"
            "    m_ok := 0;\n"
            "  END IF;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "SQL%" not in out.upper().replace(" ", ""), out
        assert re.search(r"(?i)@@ROWCOUNT\s*=\s*0", out), out


class TestRowtypeLoopVarDoubleAt:
    """The cursor FOR-loop variable may ALSO be declared explicitly as
    ``<cur>%ROWTYPE`` (real dump). The var rename then turns ``C.X`` into
    ``@C.X`` before the loop expansion rewrites record refs, which
    prefixed a second ``@`` (live 137: '@@C_SERIES_serie'). The expansion
    now consumes an existing ``@``."""

    _SRC = (
        "CREATE OR REPLACE PROCEDURE p_rt(m_td IN VARCHAR2, m_out OUT VARCHAR2) AS\n"
        "  CURSOR CUR_S IS SELECT SERIE, ACTIVO FROM f_serie WHERE TD = m_td;\n"
        "  C_S CUR_S%ROWTYPE;\n"
        "  STR_S VARCHAR2(2000);\n"
        "BEGIN\n"
        "  FOR C_S IN CUR_S LOOP\n"
        "    STR_S := STR_S || '''' || C_S.SERIE || '''';\n"
        "  END LOOP;\n"
        "  m_out := STR_S;\n"
        "END;\n/"
    )

    def test_no_double_at_variable(self) -> None:
        out = _t(self._SRC, "tsql")
        assert "@@C_S_serie" not in out, out
        assert re.search(r"(?<!@)@C_S_serie\b", out), out


class TestRepeatedLoopVarSingleDeclare:
    """Several cursor FOR loops reusing the same record name in one routine
    each emitted their own ``DECLARE @X_col`` — T-SQL DECLARE is
    batch-scoped, so the second is error 134 (live: 5x @X_total). Only the
    first loop declares; later loops reuse the variable."""

    _SRC = (
        "CREATE OR REPLACE PROCEDURE p_2l(m_a IN VARCHAR2) AS\n"
        "BEGIN\n"
        "  FOR X IN (SELECT COUNT(*) TOTAL FROM t1 WHERE a = m_a) LOOP\n"
        "    IF X.TOTAL = 0 THEN NULL; END IF;\n"
        "  END LOOP;\n"
        "  FOR X IN (SELECT COUNT(*) TOTAL FROM t2 WHERE a = m_a) LOOP\n"
        "    IF X.TOTAL = 0 THEN NULL; END IF;\n"
        "  END LOOP;\n"
        "END;\n/"
    )

    def test_single_declare_per_variable(self) -> None:
        out = _t(self._SRC, "tsql")
        declares = re.findall(r"(?i)DECLARE\s+@X_total\b", out)
        assert len(declares) == 1, out
        # Both loops still fetch into it.
        assert len(re.findall(r"(?i)INTO\s+@X_total\b", out)) >= 2, out


class TestRpadLpadInRawExpressions:
    """RPAD/LPAD in a procedural raw expression (a RETURN value live) has
    no T-SQL builtin; build it from REPLICATE like the IR emitter does."""

    def test_rpad_three_arg(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f_rp(p_c IN VARCHAR2) RETURN VARCHAR2 AS\n"
            "BEGIN\n"
            "  RETURN RPAD(p_c, 10, 'x');\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "RPAD" not in out.upper(), out
        assert re.search(r"(?i)LEFT\s*\(.*REPLICATE", out), out

    def test_lpad_two_arg_pads_spaces(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f_lp(p_c IN VARCHAR2) RETURN VARCHAR2 AS\n"
            "BEGIN\n"
            "  RETURN LPAD(p_c, 10);\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "LPAD" not in out.upper(), out
        assert re.search(r"(?i)LEFT\s*\(\s*REPLICATE\s*\(\s*' '", out), out


class TestBareReturnInPgTriggerFunction:
    """Oracle's bare ``RETURN;`` (leave the trigger) inside a trigger body:
    a plpgsql trigger function must return NEW/OLD/NULL — bare RETURN is
    'missing expression' (42601 live). It now returns what the function's
    trailing default returns (NEW row-level, NULL set-based)."""

    _SRC = (
        "CREATE OR REPLACE TRIGGER trg_r\n"
        "AFTER UPDATE ON t_e FOR EACH ROW\n"
        "DECLARE\n"
        "  v_x NUMBER;\n"
        "BEGIN\n"
        "  BEGIN\n"
        "    SELECT a INTO v_x FROM t2 WHERE b = :NEW.id;\n"
        "  EXCEPTION\n"
        "    WHEN NO_DATA_FOUND THEN\n"
        "      RETURN;\n"
        "  END;\n"
        "  UPDATE t3 SET c = v_x WHERE id = :NEW.id;\n"
        "END;\n/"
    )

    def test_bare_return_returns_new(self) -> None:
        out = _t(self._SRC, "postgresql")
        fn_body = out[out.index("$$") : out.rindex("$$")]
        assert not re.search(r"(?im)^\s*RETURN\s*;", fn_body), out
        assert len(re.findall(r"(?i)RETURN NEW\s*;", fn_body)) >= 2, out


class TestAliasedSingleTableUpdateOnTsql:
    """Oracle ``UPDATE t alias SET … WHERE alias.col`` (3x live): T-SQL
    rejects a bare alias after the target table — the aliased form is
    ``UPDATE alias SET … FROM t alias``. The correlated ROWNUM=1 subquery
    must also become TOP 1 on the way."""

    _SRC = (
        "UPDATE t_pue ep\n"
        "SET idimp = (SELECT i.idimp FROM t_imp i\n"
        "             WHERE i.imp = ep.imp AND ROWNUM = 1)\n"
        "WHERE EXISTS (SELECT 1 FROM t_imp i WHERE i.imp = ep.imp);"
    )

    def test_tsql_uses_update_from_form(self) -> None:
        out = _t(self._SRC, "tsql")
        assert not re.search(r"(?i)UPDATE\s+t_pue\s+(AS\s+)?ep\b", out), out
        assert re.search(r"(?i)FROM\s+t_pue\s+(AS\s+)?ep\b", out), out
        assert "ROWNUM" not in out.upper(), out
        assert re.search(r"(?i)TOP\s*\(?\s*1", out), out
        sqlglot.parse(out, read="tsql")

    def test_pg_keeps_valid_aliased_update(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert "ROWNUM" not in out.upper(), out
        sqlglot.parse(out, read="postgres")


class TestTsqlFunctionEmptyParens:
    """T-SQL requires the parameter parentheses on CREATE FUNCTION even
    with no parameters (live: CREATE FUNCTION NOW / RETURNS DATETIME —
    error 102 near RETURNS). Procedures stay paren-less."""

    def test_parameterless_function_gets_parens(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f_now RETURN DATE AS\n"
            "BEGIN\n"
            "  RETURN SYSDATE;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        # Oracle's idempotent CREATE OR REPLACE maps to T-SQL's CREATE OR ALTER;
        # the parameterless function still gets its required () parens.
        assert re.search(
            r"(?i)CREATE\s+OR\s+ALTER\s+FUNCTION\s+f_now\s*\(\s*\)", out
        ), out

    def test_parameterless_procedure_stays_bare(self) -> None:
        src = "CREATE OR REPLACE PROCEDURE p_now AS\n" "BEGIN\n" "  NULL;\n" "END;\n/"
        out = _t(src, "tsql")
        assert not re.search(r"(?i)CREATE\s+PROCEDURE\s+p_now\s*\(", out), out


class TestQuotedDatepartOnTsql:
    """Oracle-style quoted dateparts reaching T-SQL DATEDIFF/DATEADD
    (live 1023: DATEDIFF('Y', a, b)) — T-SQL takes bare keywords."""

    def test_quoted_year_part(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_dd(m_e OUT NUMBER, m_a IN DATE,"
            " m_b IN DATE) AS\n"
            "BEGIN\n"
            "  m_e := DATEDIFF('Y', m_a, m_b);\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?i)DATEDIFF\s*\(\s*YEAR\s*,", out), out
        assert not re.search(r"(?i)DATEDIFF\s*\(\s*'", out), out


class TestBooleanVarCondition:
    """Oracle PL/SQL BOOLEAN variables are used directly as conditions;
    T-SQL BIT needs a comparison (live 4145: IF NOT @b). A condition that
    is just ``[NOT] @var`` gains ``= 1`` (NOT binds the comparison)."""

    _SRC = (
        "CREATE OR REPLACE PROCEDURE p_b(m_out OUT NUMBER) AS\n"
        "  bexc BOOLEAN;\n"
        "BEGIN\n"
        "  bexc := TRUE;\n"
        "  IF NOT bexc THEN\n"
        "    m_out := 0;\n"
        "  END IF;\n"
        "  WHILE bexc LOOP\n"
        "    m_out := 1;\n"
        "  END LOOP;\n"
        "END;\n/"
    )

    def test_bare_boolean_conditions_compare_to_1(self) -> None:
        out = _t(self._SRC, "tsql")
        assert re.search(r"(?i)IF\s+NOT\s+@bexc\s*=\s*1", out), out
        assert re.search(r"(?i)WHILE\s+@bexc\s*=\s*1", out), out


class TestLocalShadowingParameter:
    """Oracle allows a local variable shadowing a same-named parameter;
    T-SQL forbids the re-DECLARE (live 134). T-SQL parameters are
    assignable local copies, so the parameter itself plays the local's
    role: the duplicate DECLARE is dropped with a note."""

    _SRC = (
        "CREATE OR REPLACE PROCEDURE p_sh(P_PAT IN VARCHAR2, m_out OUT VARCHAR2) AS\n"
        "  P_PAT VARCHAR2(100);\n"
        "BEGIN\n"
        "  P_PAT := 'x';\n"
        "  m_out := P_PAT;\n"
        "END;\n/"
    )

    def test_duplicate_declare_is_dropped(self) -> None:
        out = _t(self._SRC, "tsql")
        assert len(re.findall(r"(?i)DECLARE\s+@p_pat\b", out)) == 0, out
        assert re.search(r"(?i)@p_pat\s*=\s*'x'", out), out


class TestDistinctInAssignmentSelect:
    """Oracle ``SELECT DISTINCT a, b INTO v1, v2`` became
    ``SELECT @v1 = distinct a, @v2 = b`` (live 156) — DISTINCT must hoist
    ahead of the first assignment."""

    _SRC = (
        "CREATE OR REPLACE PROCEDURE p_d(m_a OUT NUMBER, m_b OUT VARCHAR2) AS\n"
        "BEGIN\n"
        "  SELECT DISTINCT mov.orden, his.nif INTO m_a, m_b\n"
        "  FROM f_mov mov INNER JOIN a_his his ON his.n = mov.n\n"
        "  WHERE mov.x = 1;\n"
        "END;\n/"
    )

    def test_distinct_hoisted(self) -> None:
        out = _t(self._SRC, "tsql")
        assert re.search(r"(?i)SELECT\s+DISTINCT\s+@m_a\s*=", out), out
        assert not re.search(r"(?i)=\s*distinct\b", out), out


class TestOracleQQuotedLiterals:
    """Oracle q-quoted literals (q'[…]', q'{…}', …) must lex as ONE string
    and convert to standard quoting (live: EXEC sp_executesql q '[ … ]' —
    error 102). The content's single quotes are doubled."""

    def test_q_bracket_literal(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_q5(m_out OUT VARCHAR2) AS\n"
            "BEGIN\n"
            "  m_out := q'[it's a test]';\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "q'" not in out.lower(), out
        assert "'it''s a test'" in out, out

    def test_q_brace_literal_in_condition(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_q6(m_a IN VARCHAR2, m_o OUT NUMBER) AS\n"
            "BEGIN\n"
            "  IF m_a = q'{x}' THEN\n"
            "    m_o := 1;\n"
            "  END IF;\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "q'" not in out.lower(), out
        assert "'x'" in out, out


class TestTwoArgSubstringOnTsql:
    """Oracle SUBSTR(s, p) means "from p to the end" (negative p counts
    from the end); T-SQL SUBSTRING requires 3 arguments (live 174). The
    2-arg form gains an explicit length and a sign-aware start."""

    def test_positive_start(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f_ss(p_c IN VARCHAR2) RETURN VARCHAR2 AS\n"
            "BEGIN\n"
            "  RETURN SUBSTR(p_c, 3);\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert not re.search(r"(?i)SUBSTRING\s*\(\s*@p_c\s*,\s*3\s*\)", out), out
        assert re.search(r"(?i)LEN\s*\(", out), out

    def test_nested_call_argument(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f_ss2(p_c IN VARCHAR2, p_n IN NUMBER)\n"
            "RETURN VARCHAR2 AS\n"
            "BEGIN\n"
            "  RETURN SUBSTR(RPAD(p_c, 10, 'x') || p_c,"
            " GREATEST(-LENGTH(p_c), -p_n));\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        # No 2-arg SUBSTRING may remain (T-SQL requires 3 args).
        for m in re.finditer(r"(?is)\bSUBSTRING\s*\(", out):
            depth, args, i = 1, 1, m.end()
            while i < len(out) and depth:
                c = out[i]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif c == "," and depth == 1:
                    args += 1
                i += 1
            assert args >= 3, out


class TestDynamicRoutineDdlStaysDynamic:
    """A constant EXECUTE IMMEDIATE whose statement is routine DDL
    (CREATE PROCEDURE/FUNCTION/TRIGGER) must NOT unwrap inline: neither
    PG nor T-SQL allows routine DDL inside a block (live: a q-quoted
    CREATE PROCEDURE guarded by a count probe — 42601 on PG, 156 on
    T-SQL). It stays dynamic, with a warning that the routine text needs
    manual conversion."""

    _SRC = (
        "DECLARE\n"
        "  v_count NUMBER;\n"
        "BEGIN\n"
        "  SELECT COUNT(*) INTO v_count FROM all_objects WHERE object_name = 'P_X';\n"
        "  IF v_count = 0 THEN\n"
        "    EXECUTE IMMEDIATE q'[CREATE PROCEDURE p_x (p_a OUT NUMBER) AS\n"
        "      BEGIN p_a := NULL; END]';\n"
        "  END IF;\n"
        "END;\n/"
    )

    def test_pg_keeps_execute(self) -> None:
        out = _t(self._SRC, "postgresql")
        body = out[out.index("$$") :] if "$$" in out else out
        assert not re.search(r"(?im)^\s*CREATE\s+PROCEDURE", body), out
        assert re.search(r"(?i)EXECUTE\s+'", out) or "-- UNIQUE:" in out, out

    def test_tsql_keeps_dynamic_exec(self) -> None:
        out = _t(self._SRC, "tsql")
        assert not re.search(r"(?im)^\s*CREATE\s+PROCEDURE\s+p_x", out), out
        assert re.search(r"(?i)EXEC|sp_executesql", out) or "-- UNIQUE:" in out, out

    def test_warning_is_raised(self) -> None:
        from unique.core.transpiler import Transpiler

        r = Transpiler().transpile(self._SRC, "oracle", "postgresql")
        assert any("routine DDL" in str(w) for w in r.warnings), r.warnings


class TestPrefixStripCollision:
    """Oracle param ``p_x`` + local ``v_p_x``: stripping the local's
    ``v_`` prefix collided both onto ``@p_x`` (live 134 — and a silent
    aliasing risk). On collision the local keeps its full source name."""

    _SRC = (
        "CREATE OR REPLACE FUNCTION f_cc(p_pat VARCHAR2) RETURN VARCHAR2 IS\n"
        "  v_p_pat VARCHAR2(100);\n"
        "BEGIN\n"
        "  v_p_pat := RTRIM(LTRIM(p_pat));\n"
        "  RETURN v_p_pat;\n"
        "END;\n/"
    )

    def test_local_keeps_distinct_name(self) -> None:
        out = _t(self._SRC, "tsql")
        assert len(re.findall(r"(?i)DECLARE\s+@", out)) == 1, out
        assert re.search(r"(?i)DECLARE\s+@v_p_pat\b", out), out
        assert re.search(
            r"(?i)@v_p_pat\s*=\s*RTRIM\s*\(\s*LTRIM\s*\(\s*@p_pat", out
        ), out


class TestFinalMergeScalarsWave22:
    """The last three live failures (2026-07-11): a numeric-style TO_CHAR
    (client code ported FROM T-SQL: TO_CHAR(x, 112) means CONVERT style
    112), a client UDF inside sqlglot-emitted MERGE passthrough text
    (which the shared dbo. decision never saw), and REGEXP_LIKE — no SQL
    Server 2022 form, so it degrades honestly via the gate."""

    def test_numeric_style_to_char(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_ns(p_fn IN DATE, m_o OUT VARCHAR2) AS\n"
            "BEGIN\n"
            "  m_o := TO_CHAR(p_fn, 112);\n"
            "END;\n/"
        )
        out = _t(src, "tsql")
        assert "TO_CHAR" not in out.upper(), out
        assert re.search(
            r"(?i)CONVERT\s*\(\s*VARCHAR\(4000\)\s*,\s*@p_fn\s*,\s*112\s*\)", out
        ), out

    def test_udf_inside_merge_is_qualified(self) -> None:
        src = (
            "MERGE INTO t_dst USING (SELECT a, my_datefn(b) AS fv FROM t_src) s\n"
            "ON (t_dst.a = s.a)\n"
            "WHEN MATCHED THEN UPDATE SET t_dst.fv = s.fv;"
        )
        out = _t(src, "tsql")
        assert re.search(r"(?i)dbo\.my_datefn\s*\(", out), out

    def test_regexp_like_degrades_honestly(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "INSERT INTO t_cfg (k)\n"
            "SELECT 'x' FROM DUAL WHERE NOT EXISTS (\n"
            "  SELECT 1 FROM t_h h WHERE REGEXP_LIKE(h.valor, '^\\d+$'));"
        )
        r = Transpiler().transpile(src, "oracle", "tsql")
        assert not re.search(r"(?im)^\s*[^-].*REGEXP_LIKE", r.sql), r.sql
        assert r.warnings or r.unsupported, (r.sql, r.warnings)
