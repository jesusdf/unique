# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""End-to-end procedural transpilation tests.

These exercise the full pipeline (split -> classify -> parse -> transform
-> emit) on representative procedures drawn from real-world patterns.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _transpile(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestTSQLToOracle:
    def test_procedure_body_translated(self) -> None:
        sql = (
            "CREATE PROCEDURE dbo.upd_user\n"
            "    @id INT,\n"
            "    @name NVARCHAR(50)\n"
            "AS\n"
            "BEGIN\n"
            "    SET NOCOUNT ON\n"
            "    DECLARE @now DATETIME = GETDATE()\n"
            "    IF @id > 0\n"
            "    BEGIN\n"
            "        UPDATE users SET name = @name, modified = @now WHERE id = @id\n"
            "    END\n"
            "END"
        )
        out = _transpile(sql, "tsql", "oracle")
        assert "CREATE OR REPLACE PROCEDURE" in out
        # Parameters converted to Oracle naming/types
        assert "V_ID" in out
        assert "NUMBER" in out
        # IF block became PL/SQL form
        assert "END IF;" in out
        # Body is not empty
        assert "UPDATE" in out

    def test_assignment_becomes_colon_equals(self) -> None:
        sql = "CREATE PROCEDURE p @x INT AS BEGIN " "SET @x = @x + 1 " "END"
        out = _transpile(sql, "tsql", "oracle")
        assert ":=" in out

    def test_cast_in_plsql_body_drops_constraint(self) -> None:
        # Oracle PL/SQL CAST rejects a constrained type (PLS-00103) and DECIMAL;
        # it must become an unconstrained NUMBER.
        sql = (
            "CREATE FUNCTION dbo.fn_tax (@net DECIMAL(12, 2))\n"
            "RETURNS DECIMAL(12, 2)\n"
            "AS\nBEGIN\n"
            "    RETURN @net * CAST(0.10 AS DECIMAL(12, 2))\n"
            "END"
        )
        out = _transpile(sql, "tsql", "oracle")
        assert "CAST ( 0.10 AS NUMBER )" in out
        assert "DECIMAL" not in out

    IDENTITY_PROC = (
        "CREATE TABLE dbo.invoice (\n"
        "  id INT IDENTITY(1,1) NOT NULL,\n"
        "  customer_id INT NOT NULL,\n"
        "  CONSTRAINT pk_invoice PRIMARY KEY (id)\n"
        ")\n"
        "GO\n"
        "CREATE PROCEDURE dbo.create_invoice @customer_id INT\n"
        "AS\nBEGIN\n"
        "    DECLARE @new_id INT;\n"
        "    INSERT INTO dbo.invoice (customer_id) VALUES (@customer_id);\n"
        "    SET @new_id = SCOPE_IDENTITY();\n"
        "    INSERT INTO dbo.invoice_line (invoice_id) VALUES (@new_id);\n"
        "END\nGO"
    )

    def test_scope_identity_becomes_returning_into(self) -> None:
        # Oracle has no SCOPE_IDENTITY(); the id is captured on the INSERT via
        # RETURNING <idcol> INTO <var>, and the separate assignment is dropped.
        out = _transpile(self.IDENTITY_PROC, "tsql", "oracle")
        assert (
            "INSERT INTO invoice (customer_id) VALUES (V_CUSTOMER_ID) "
            "RETURNING id INTO V_NEW_ID" in out
        )
        # The broken placeholder assignment must be gone.
        assert "CURRVAL" not in out
        assert "V_NEW_ID :=" not in out
        assert "SET V_NEW_ID" not in out

    def test_oracle_bare_proc_call_becomes_call(self) -> None:
        # Oracle invokes a procedure by bare name inside a block (no CALL
        # keyword); PG/MySQL need CALL name(args). It must not fall through to
        # EmbeddedDML (sqlglot would mangle it to a bare NAME(args)).
        src = "BEGIN\n    create_invoice(2, 1, 1);\nEND;"
        assert "CALL create_invoice(2, 1, 1)" in _transpile(src, "oracle", "postgresql")
        assert "CALL create_invoice(2, 1, 1)" in _transpile(src, "oracle", "mysql")

    def test_call_wraps_iso_date_argument(self) -> None:
        # A stored proc's DATE parameter receiving an ISO string must be wrapped
        # in an ANSI DATE literal for the Oracle call (ORA-01861 otherwise).
        sql = (
            "CREATE PROCEDURE dbo.create_invoice\n"
            "    @customer_id INT, @issued_on DATE, @qty INT\n"
            "AS\nBEGIN\n    SELECT 1\nEND\nGO\n"
            "EXEC dbo.create_invoice 2, '2024-02-01', 1\nGO"
        )
        out = _transpile(sql, "tsql", "oracle")
        assert "create_invoice(2, DATE '2024-02-01', 1)" in out

    def test_returning_into_preserved_from_pg_source(self) -> None:
        # sqlglot drops the ``INTO <var>`` of a RETURNING clause; it must be
        # peeled and re-appended, or Oracle raises ORA-00925.
        sql = (
            "CREATE PROCEDURE create_invoice(p_customer_id INTEGER)\n"
            "LANGUAGE plpgsql AS $$\n"
            "DECLARE\n    v_new_id INTEGER;\n"
            "BEGIN\n"
            "    INSERT INTO invoice (customer_id) VALUES (p_customer_id)\n"
            "    RETURNING id INTO v_new_id;\n"
            "END;\n$$;"
        )
        out = _transpile(sql, "postgresql", "oracle")
        assert "RETURNING id INTO v_new_id" in out

    def test_scope_identity_unknown_table_left_alone(self) -> None:
        # With no harvested identity column, nothing is merged (no crash).
        sql = (
            "CREATE PROCEDURE dbo.p @x INT\n"
            "AS\nBEGIN\n"
            "    DECLARE @new_id INT;\n"
            "    INSERT INTO dbo.mystery (x) VALUES (@x);\n"
            "    SET @new_id = SCOPE_IDENTITY();\n"
            "END\nGO"
        )
        out = _transpile(sql, "tsql", "oracle")
        assert "RETURNING" not in out


class TestOracleToTSQL:
    def test_procedure_body_translated(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE upd_user(\n"
            "    p_id IN NUMBER,\n"
            "    p_name IN VARCHAR2\n"
            ") IS\n"
            "    v_now DATE := SYSDATE;\n"
            "BEGIN\n"
            "    IF p_id > 0 THEN\n"
            "        UPDATE users SET name = p_name, modified = v_now "
            "WHERE id = p_id;\n"
            "    END IF;\n"
            "END;"
        )
        out = _transpile(sql, "oracle", "tsql")
        assert "CREATE PROCEDURE" in out
        # Oracle params converted to T-SQL @variables
        assert "@p_id" in out
        # IF block became T-SQL form
        assert "BEGIN" in out
        assert "UPDATE" in out

    def test_type_reference_without_db_becomes_sql_variant(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p IS "
            "v_x employees.salary%TYPE; "
            "BEGIN v_x := 1; END;"
        )
        result = Transpiler().transpile(sql, source="oracle", target="tsql")
        assert "SQL_VARIANT" in result.sql
        # A warning should flag the unresolved %TYPE
        assert any("TYPE" in w.message.upper() for w in result.warnings)

    def test_dbms_output_becomes_print(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "DBMS_OUTPUT.PUT_LINE('hello'); "
            "END;"
        )
        out = _transpile(sql, "oracle", "tsql")
        assert "PRINT" in out


class TestTSQLToMySQL:
    def test_variables_and_types_converted(self) -> None:
        sql = (
            "CREATE PROCEDURE p\n"
            "    @id INT,\n"
            "    @uid UNIQUEIDENTIFIER\n"
            "AS\n"
            "BEGIN\n"
            "    DECLARE @n INT\n"
            "    SET @n = @id + 1\n"
            "END"
        )
        out = _transpile(sql, "tsql", "mysql")
        # No T-SQL @ sigils on local variables
        assert "@id" not in out
        assert "v_id" in out
        # UNIQUEIDENTIFIER mapped to CHAR(36)
        assert "CHAR(36)" in out
        # MySQL DECLARE keyword present
        assert "DECLARE v_n" in out


class TestOracleToPostgreSQL:
    def test_types_and_structure(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p(p_id IN NUMBER) IS\n"
            "    v_d DATE := SYSDATE;\n"
            "BEGIN\n"
            "    IF p_id > 0 THEN\n"
            "        UPDATE t SET d = v_d WHERE id = p_id;\n"
            "    END IF;\n"
            "END;"
        )
        out = _transpile(sql, "oracle", "postgresql")
        assert "LANGUAGE plpgsql" in out
        assert "NUMERIC" in out
        assert "TIMESTAMP" in out
        assert "END IF;" in out


class TestOracleToMySQL:
    def test_types_and_declare(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p(p_id IN NUMBER) IS\n"
            "    v_name VARCHAR2(50);\n"
            "BEGIN\n"
            "    v_name := 'x';\n"
            "END;"
        )
        out = _transpile(sql, "oracle", "mysql")
        assert "DECIMAL" in out
        assert "VARCHAR(50)" in out
        assert "DECLARE v_name" in out
        # MySQL assignment uses SET
        assert "SET v_name =" in out


class TestPostgreSQLAsSource:
    def test_header_consumed_not_parsed_as_vars(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p(p_id INTEGER)\n"
            "LANGUAGE plpgsql\n"
            "AS $$\n"
            "DECLARE\n"
            "    v_n INTEGER;\n"
            "BEGIN\n"
            "    v_n := p_id;\n"
            "END;\n"
            "$$;"
        )
        out = _transpile(sql, "postgresql", "tsql")
        # The LANGUAGE/AS/$$ header must not leak in as declarations
        assert "plpgsql" not in out
        assert "@as" not in out.lower()
        assert "DECLARE @v_n" in out or "DECLARE @n" in out

    def test_raise_notice_becomes_print(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p()\n"
            "LANGUAGE plpgsql AS $$\n"
            "BEGIN\n"
            "    RAISE NOTICE 'hello';\n"
            "END;\n"
            "$$;"
        )
        out = _transpile(sql, "postgresql", "tsql")
        assert "PRINT 'hello'" in out
        assert "RAISERROR" not in out


class TestMySQLAsSource:
    def test_function_characteristics_consumed(self) -> None:
        # MySQL routine characteristics (DETERMINISTIC, READS SQL DATA, ...)
        # between the signature and BEGIN must not become junk declarations.
        sql = (
            "CREATE FUNCTION f(p INT) RETURNS DECIMAL(5,2)\n"
            "    DETERMINISTIC\n"
            "    READS SQL DATA\n"
            "BEGIN\n"
            "    DECLARE v DECIMAL(5,2);\n"
            "    SET v = p * 2;\n"
            "    RETURN v;\n"
            "END"
        )
        out = _transpile(sql, "mysql", "tsql")
        assert "DETERMINISTIC" not in out
        assert "READS SQL DATA" not in out
        # MySQL local vars/params gain T-SQL's ``@`` sigil (declaration + body).
        assert "DECLARE @v" in out
        assert "RETURN @v" in out
        assert "@v = @p * 2" in out

    def test_routine_not_fragmented_without_delimiter(self) -> None:
        from unique.core.batch_splitter import BatchSplitter

        sql = (
            "CREATE PROCEDURE p(IN p_id INT)\n"
            "BEGIN\n"
            "    DECLARE v_n INT DEFAULT 0;\n"
            "    SET v_n = p_id;\n"
            "    UPDATE t SET x = v_n WHERE id = p_id;\n"
            "END\n"
        )
        batches = [b for b in BatchSplitter.split(sql, "mysql") if not b.is_empty]
        assert len(batches) == 1

    def test_parameters_and_body_to_oracle(self) -> None:
        sql = (
            "CREATE PROCEDURE p(IN p_id INT, OUT p_out VARCHAR(50))\n"
            "BEGIN\n"
            "    DECLARE v_n INT DEFAULT 0;\n"
            "    IF p_id > 0 THEN\n"
            "        SET v_n = 1;\n"
            "    END IF;\n"
            "END\n"
        )
        out = _transpile(sql, "mysql", "oracle")
        assert "PROCEDURE p" in out
        assert "p_id IN" in out
        assert "p_out OUT" in out
        # MySQL SET assignment becomes Oracle :=
        assert "v_n := 1;" in out
        assert "END IF;" in out

    def test_set_assignment_to_tsql(self) -> None:
        sql = (
            "CREATE PROCEDURE p(IN p_id INT)\n"
            "BEGIN\n"
            "    DECLARE v_n INT DEFAULT 0;\n"
            "    SET v_n = p_id;\n"
            "END\n"
        )
        out = _transpile(sql, "mysql", "tsql")
        assert "SET v_n = p_id;" in out or "SET @v_n = @p_id;" in out


class TestDynamicSQL:
    SRC = (
        "CREATE OR REPLACE PROCEDURE p(p_id IN NUMBER, p_name IN VARCHAR2)\n"
        "IS\n"
        "    v_stmt VARCHAR2(200);\n"
        "BEGIN\n"
        "    v_stmt := 'UPDATE t SET name = :1 WHERE id = :2';\n"
        "    EXECUTE IMMEDIATE v_stmt USING p_name, p_id;\n"
        "END;"
    )

    def test_oracle_to_postgresql_keeps_using(self) -> None:
        out = _transpile(self.SRC, "oracle", "postgresql")
        assert "USING" in out
        assert "EXECUTE v_stmt USING" in out

    def test_oracle_to_tsql_uses_sp_executesql(self) -> None:
        out = _transpile(self.SRC, "oracle", "tsql")
        assert "sp_executesql" in out
        assert "@p1" in out and "@p2" in out

    def test_oracle_to_mysql_prepare_workflow(self) -> None:
        out = _transpile(self.SRC, "oracle", "mysql")
        assert "PREPARE" in out
        assert "DEALLOCATE PREPARE" in out
        assert "USING" in out

    def test_oracle_round_trip_keeps_using(self) -> None:
        out = _transpile(self.SRC, "oracle", "oracle")
        assert "EXECUTE IMMEDIATE" in out
        assert "USING" in out


class TestStandaloneExec:
    """A standalone EXEC proc (not inside a CREATE PROCEDURE body) must also
    become CALL proc(args) on the other engines, with named args turned
    positional and OUTPUT dropped — not left as raw T-SQL EXEC."""

    _EXEC = (
        "EXEC dbo.create_invoice @customer_id = 2, @issued_on = '2024-02-01', "
        "@product_a = 1, @qty_a = 1, @product_b = 2, @qty_b = 1"
    )

    def test_standalone_exec_to_postgresql(self) -> None:
        out = _transpile(self._EXEC, "tsql", "postgresql")
        assert "CALL create_invoice(" in out
        assert "EXEC" not in out.upper().split("--")[0]

    def test_standalone_exec_to_mysql(self) -> None:
        out = _transpile(self._EXEC, "tsql", "mysql")
        assert "CALL create_invoice(" in out

    def test_standalone_exec_to_oracle(self) -> None:
        out = _transpile(self._EXEC, "tsql", "oracle")
        assert "create_invoice(" in out.lower()
        assert "EXEC " not in out.upper().split("--")[0]
        # Oracle runs a procedure call inside a PL/SQL block.
        assert "BEGIN" in out.upper()
        assert "END;" in out.upper()


class TestExecOutputCapture:
    """A batch that DECLAREs a variable and captures a procedure's OUTPUT
    parameter into it (``EXEC p @out = @v OUTPUT``) must become the target's
    OUT/INOUT call form inside a procedural block, with the batch variable
    carried through to later statements."""

    _BATCH = (
        "DECLARE @new_id INT;\n"
        "EXEC create_invoice @customer_id = 1, @new_id = @new_id OUTPUT;\n"
        "UPDATE log SET last_id = @new_id;"
    )

    def test_output_capture_to_postgresql(self) -> None:
        out = _transpile(self._BATCH, "tsql", "postgresql")
        assert "DO $$" in out
        assert "DECLARE" in out.upper()
        # The OUT arg is passed as the CALL's INOUT slot and reused afterwards.
        assert "CALL create_invoice(" in out
        assert "new_id => v_new_id" in out
        assert "last_id = v_new_id" in out
        assert "OUTPUT" not in out.upper()
        assert "-- UNIQUE:" not in out

    def test_output_capture_to_oracle(self) -> None:
        out = _transpile(self._BATCH, "tsql", "oracle")
        assert "BEGIN" in out.upper() and "END;" in out.upper()
        assert "create_invoice(" in out.lower()
        assert "V_NEW_ID" in out.upper()
        assert "OUTPUT" not in out.upper()
        assert "-- UNIQUE:" not in out


class TestTopLevelPrintAndSet:
    """A standalone (top-level) PRINT / ``SET @var = …`` is procedural: PRINT
    becomes each engine's message form and the assignment is translated, instead
    of a DML 'Unhandled expression' carrier."""

    def test_print_to_oracle(self) -> None:
        out = _transpile("PRINT 'hi'", "tsql", "oracle")
        assert "DBMS_OUTPUT.PUT_LINE('hi')" in out
        assert "-- UNIQUE:" not in out

    def test_print_to_postgresql_is_wrapped(self) -> None:
        # RAISE NOTICE is PL/pgSQL-only, so it needs the DO $$ … $$ wrapper.
        out = _transpile("PRINT 'hi'", "tsql", "postgresql")
        assert "DO $$" in out
        assert "RAISE NOTICE '%', 'hi'" in out

    def test_print_to_mysql_is_bare_select(self) -> None:
        out = _transpile("PRINT 'hi'", "tsql", "mysql")
        assert "SELECT 'hi'" in out
        assert "DO $$" not in out

    def test_set_var_assignment_translated(self) -> None:
        out = _transpile("DECLARE @v INT;\nSET @v = 5", "tsql", "oracle")
        assert "V_V := 5" in out
        assert "-- UNIQUE:" not in out


class TestExecNamedArgs:
    """A T-SQL ``EXEC proc @name = value`` uses named-parameter syntax; Oracle and
    PostgreSQL spell it ``proc(name => value)`` — the ``@`` sigil dropped and the
    name kept as the formal parameter (not renamed to a V_ local variable)."""

    SRC = "EXEC SVP_WEBMENU @idmenu=23904, @cmd='NEXT-MED', @orden=20\n" "go"

    def test_oracle_named_args_use_arrow(self) -> None:
        out = _transpile(self.SRC, "tsql", "oracle")
        assert "idmenu => 23904" in out
        assert "cmd => 'NEXT-MED'" in out
        assert "orden => 20" in out
        assert "@" not in out  # sigil dropped
        assert "V_IDMENU" not in out  # not renamed as a local variable
        assert "20 go" not in out.lower()  # the GO batch terminator is not leaked

    def test_postgresql_named_args_use_arrow(self) -> None:
        out = _transpile(self.SRC, "tsql", "postgresql")
        assert "CALL SVP_WEBMENU(" in out
        assert "idmenu => 23904" in out
        assert "20 go" not in out.lower()

    def test_named_arg_rhs_variable_still_transformed(self) -> None:
        # The LHS becomes the parameter name; an RHS variable value keeps its own
        # @var -> V_var transform.
        out = _transpile("DECLARE @v INT;\nEXEC myproc @a=@v", "tsql", "oracle")
        assert "a => V_V" in out


class TestTSQLExecToMySQL:
    """T-SQL EXEC has three shapes that must map to different MySQL forms."""

    def _proc(self, body: str) -> str:
        return f"CREATE PROCEDURE dbo.p AS\nBEGIN\n    {body}\nEND"

    def test_named_procedure_becomes_call(self) -> None:
        out = _transpile(self._proc("EXEC proc_13 @a OUTPUT, 'x', @b"), "tsql", "mysql")
        assert "CALL proc_13(" in out
        # The OUTPUT keyword has no inline MySQL equivalent and is dropped.
        assert "OUTPUT" not in out
        # A named call must not be funneled into the dynamic-SQL workflow.
        assert "PREPARE" not in out

    def test_sp_executesql_becomes_prepare_workflow(self) -> None:
        out = _transpile(
            self._proc("EXEC sp_executesql @sql, N'@p int', @p = @v"),
            "tsql",
            "mysql",
        )
        assert "PREPARE _dyn FROM @_stmt" in out
        assert "DEALLOCATE PREPARE _dyn" in out
        # The literal sp_executesql keyword must not leak into executable
        # MySQL (it may still be named in the explanatory -- comment).
        code = out.split("--")[0]
        assert "sp_executesql" not in code
        # Dropped parameter bindings are flagged, not silently lost.
        assert "UNIQUE:" in out

    def test_dynamic_string_uses_prepare(self) -> None:
        out = _transpile(self._proc("EXEC (@sql)"), "tsql", "mysql")
        assert "PREPARE _dyn FROM @_stmt" in out
        assert "sp_executesql" not in out


class TestCursorsAndLoops:
    SRC = (
        "CREATE OR REPLACE PROCEDURE p(p_c IN NUMBER)\n"
        "IS\n"
        "    CURSOR c IS SELECT id FROM orders WHERE cust = p_c;\n"
        "    v_id NUMBER;\n"
        "BEGIN\n"
        "    OPEN c;\n"
        "    LOOP\n"
        "        FETCH c INTO v_id;\n"
        "        EXIT WHEN c%NOTFOUND;\n"
        "        UPDATE orders SET done = 1 WHERE id = v_id;\n"
        "    END LOOP;\n"
        "    CLOSE c;\n"
        "END;"
    )

    def test_cursor_decl_tsql_no_double_semicolon(self) -> None:
        out = _transpile(self.SRC, "oracle", "tsql")
        assert ";;" not in out
        assert "DECLARE @c CURSOR FOR" in out

    def test_cursor_decl_postgresql_syntax(self) -> None:
        out = _transpile(self.SRC, "oracle", "postgresql")
        assert ";;" not in out
        assert "c CURSOR FOR" in out

    def test_exit_when_notfound_tsql(self) -> None:
        out = _transpile(self.SRC, "oracle", "tsql")
        # EXIT WHEN cur%NOTFOUND must keep its condition, not become a bare
        # BREAK.
        assert "@@FETCH_STATUS <> 0" in out
        assert "BREAK" in out

    def test_exit_when_notfound_postgresql(self) -> None:
        out = _transpile(self.SRC, "oracle", "postgresql")
        assert "EXIT WHEN NOT FOUND" in out

    def test_unconditional_loop_tsql_becomes_while(self) -> None:
        out = _transpile(self.SRC, "oracle", "tsql")
        assert "WHILE 1=1" in out or "WHILE 1 = 1" in out

    def test_for_cursor_loop_expanded_in_tsql(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "FOR rec IN (SELECT id FROM t) LOOP "
            "INSERT INTO log VALUES (rec.id); "
            "END LOOP; END;"
        )
        out = _transpile(src, "oracle", "tsql")
        # Expanded to an explicit T-SQL cursor with full lifecycle.
        assert "DECLARE rec_cur CURSOR" in out
        assert "OPEN rec_cur" in out
        assert "@@FETCH_STATUS = 0" in out
        assert "CLOSE rec_cur" in out
        assert "DEALLOCATE rec_cur" in out

    def test_for_cursor_loop_expanded_in_mysql(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "FOR rec IN (SELECT id FROM t) LOOP "
            "INSERT INTO log VALUES (rec.id); "
            "END LOOP; END;"
        )
        out = _transpile(src, "oracle", "mysql")
        assert "DECLARE rec_cur CURSOR FOR" in out
        assert "CONTINUE HANDLER FOR NOT FOUND" in out
        assert "OPEN rec_cur" in out
        assert "CLOSE rec_cur" in out

    def test_for_cursor_loop_native_in_postgresql(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "FOR rec IN (SELECT id FROM t) LOOP "
            "INSERT INTO log VALUES (rec.id); "
            "END LOOP; END;"
        )
        out = _transpile(src, "oracle", "postgresql")
        assert "FOR rec IN" in out
        assert "LOOP" in out


class TestRoundTripStability:
    def test_tsql_to_oracle_to_tsql_preserves_structure(self) -> None:
        sql = (
            "CREATE PROCEDURE p @x INT AS BEGIN " "DECLARE @y INT; SET @y = @x; " "END"
        )
        oracle = _transpile(sql, "tsql", "oracle")
        back = _transpile(oracle, "oracle", "tsql")
        assert "CREATE PROCEDURE" in back
        assert "DECLARE" in back


class TestUniqueCommentRestore:
    """A construct with no target equivalent is documented as a
    ``/* UNIQUE: <orig> -- <src>-only … */`` comment on the forward pass; when
    transpiled back to its source engine, the original must be restored rather
    than left as a comment."""

    def test_identity_insert_documented_then_restored(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "SET IDENTITY_INSERT dbo.t ON; "
            "INSERT INTO t VALUES (1) "
            "END"
        )
        # Forward: T-SQL -> Oracle documents it (and records it is tsql-only).
        oracle = _transpile(src, "tsql", "oracle")
        assert "UNIQUE:" in oracle
        assert "IDENTITY_INSERT" in oracle
        assert "tsql-only" in oracle
        # Back to T-SQL: the original statement is restored.
        back = _transpile(oracle, "oracle", "tsql")
        assert "SET IDENTITY_INSERT dbo.t ON" in back
        assert "UNIQUE:" not in back

    def test_not_restored_on_a_different_target(self) -> None:
        # Oracle -> PostgreSQL (not the source engine) keeps the documentation;
        # the tsql-only construct must stay inside the note, never injected as an
        # executable statement.
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "SET IDENTITY_INSERT dbo.t ON; "
            "INSERT INTO t VALUES (1) "
            "END"
        )
        oracle = _transpile(src, "tsql", "oracle")
        pg = _transpile(oracle, "oracle", "postgresql")
        assert "UNIQUE:" in pg
        for line in pg.splitlines():
            if "IDENTITY_INSERT" in line:
                assert "UNIQUE:" in line


class TestTSQLAssignmentSelect:
    """SELECT @v = expr (T-SQL variable assignment) must become SELECT ... INTO,
    not a column alias (which would silently drop the assignment)."""

    def test_single_assignment_to_mysql(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @x INT "
            "SELECT @x = col FROM t WHERE id = 1 "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "INTO v_x" in out
        assert "col AS v_x" not in out

    def test_multiple_assignment_to_oracle(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @x INT "
            "SELECT @x = a, @y = b FROM t "
            "END"
        )
        out = _transpile(src, "tsql", "oracle")
        assert "INTO V_X, V_Y" in out.replace("  ", " ")

    def test_assignment_to_postgresql(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @x INT "
            "SELECT @x = col FROM t "
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "INTO v_x" in out

    def test_normal_select_not_treated_as_assignment(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN " "SELECT a, b FROM t WHERE x = 1 " "END"
        out = _transpile(src, "tsql", "mysql")
        # A WHERE equality must not be mistaken for an assignment.
        assert "INTO" not in out
        assert "WHERE x = 1" in out

    def test_aggregate_assignment(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @n INT "
            "SELECT @n = COUNT(*) FROM t WHERE active = 1 "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "INTO v_n" in out
        assert "COUNT" in out.upper()


class TestOutputClauseToMySQL:
    """INSERT ... OUTPUT ... INTO @var must not become invalid RETURNING on
    MySQL (which has no RETURNING/OUTPUT)."""

    def test_output_into_var_is_documented_not_returning(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @id INT "
            "INSERT INTO t (a) OUTPUT inserted.id INTO @id VALUES (1) "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        # No invalid executable RETURNING clause (it only appears, if at all,
        # inside the explanatory comment).
        code_lines = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("RETURNING" not in ln for ln in code_lines)
        # Base INSERT preserved and the dropped clause documented.
        assert "INSERT INTO t (a) VALUES (1)" in out
        assert "-- UNIQUE: MySQL has no RETURNING/OUTPUT" in out

    def test_output_maps_to_returning_on_postgresql(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @id INT "
            "INSERT INTO t (a) OUTPUT inserted.id INTO @id VALUES (1) "
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        # PostgreSQL supports RETURNING, so it must be kept.
        assert "RETURNING" in out


class TestTableVariableToMySQL:
    """T-SQL table variables have no DECLARE form in MySQL; they become a
    CREATE TEMPORARY TABLE in the body, and the following statements survive."""

    def test_table_variable_becomes_temp_table(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @tmp TABLE (id INT, name NVARCHAR(50)) "
            "INSERT INTO @tmp (id) VALUES (1) "
            "SELECT id FROM @tmp "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        # No invalid table-variable DECLARE.
        assert "DECLARE v_tmp TABLE" not in out
        # A temporary table with mapped column types.
        assert "CREATE TEMPORARY TABLE v_tmp" in out
        assert "VARCHAR(50)" in out
        # The statements after the declaration must be preserved.
        assert "INSERT INTO v_tmp (id) VALUES (1)" in out
        assert "SELECT id FROM v_tmp" in out

    def test_uniqueidentifier_column_is_mapped(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @t TABLE (g UNIQUEIDENTIFIER) "
            "SELECT g FROM @t "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "UNIQUEIDENTIFIER" not in out


class TestInsertValuesSelectBoundary:
    """INSERT ... VALUES (...) followed by SELECT must be two statements, not a
    mis-parsed INSERT ... SELECT that drops the SELECT."""

    def test_insert_values_then_select_preserved(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "INSERT INTO t (id) VALUES (1) "
            "SELECT id FROM t "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "INSERT INTO t (id) VALUES (1)" in out
        assert "SELECT id FROM t" in out

    def test_insert_select_stays_together(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "INSERT INTO t (a, b) SELECT x, y FROM src "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        # A genuine INSERT ... SELECT must remain a single statement.
        assert "INSERT INTO t (a, b) SELECT x, y FROM src" in out.replace("  ", " ")


class TestTryCatchToMySQL:
    """T-SQL TRY/CATCH must become a MySQL DECLARE ... HANDLER, not an
    Oracle/PG EXCEPTION block (which MySQL rejects)."""

    SRC = (
        "CREATE PROCEDURE dbo.p AS BEGIN "
        "BEGIN TRY "
        "INSERT INTO t (a) VALUES (1) "
        "END TRY "
        "BEGIN CATCH "
        "SELECT 1 "
        "END CATCH "
        "END"
    )

    def test_mysql_uses_handler_not_exception(self) -> None:
        out = _transpile(self.SRC, "tsql", "mysql")
        assert "DECLARE EXIT HANDLER FOR SQLEXCEPTION" in out
        # The Oracle/PG EXCEPTION syntax must not leak into MySQL.
        assert "WHEN OTHERS THEN" not in out

    def test_handler_precedes_try_body(self) -> None:
        out = _transpile(self.SRC, "tsql", "mysql")
        handler_pos = out.find("DECLARE EXIT HANDLER")
        insert_pos = out.find("INSERT INTO t")
        # The handler must be declared before the protected statements.
        assert 0 <= handler_pos < insert_pos

    def test_oracle_still_uses_exception(self) -> None:
        out = _transpile(self.SRC, "tsql", "oracle")
        assert "EXCEPTION" in out
        assert "WHEN OTHERS THEN" in out


class TestPostgreSQLProcedureFixes:
    """Bugs fixed while generating the PostgreSQL procedures fixture."""

    def test_dbo_stripped_from_table_and_call(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @f INT = dbo.func1() "
            "SELECT a FROM dbo.t WHERE id = 1 "
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "dbo." not in out.replace("-- ", "")
        assert "FROM t" in out
        assert "func1()" in out.replace(" ", "")

    def test_procedure_name_dbo_stripped(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN SELECT 1 END"
        out = _transpile(src, "tsql", "postgresql")
        assert "PROCEDURE p" in out
        assert "dbo.p" not in out

    def test_sql_variant_carrier(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p @v SQL_VARIANT = NULL AS BEGIN " "SET @v = NULL END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "TEXT /* UNIQUE: SQL_VARIANT */" in out

    def test_newsequentialid_maps_to_gen_random_uuid(self) -> None:
        out = _transpile(
            "CREATE TABLE t (id UNIQUEIDENTIFIER DEFAULT NEWSEQUENTIALID())",
            "tsql",
            "postgresql",
        )
        assert "gen_random_uuid()" in out
        assert "NEWSEQUENTIALID" not in out

    def test_convert_hashbytes_in_return(self) -> None:
        src = (
            "CREATE FUNCTION dbo.f(@p NVARCHAR(MAX)) RETURNS NVARCHAR(MAX) AS "
            "BEGIN "
            "RETURN CONVERT(nvarchar(max), HASHBYTES('SHA2_256', @p), 2) "
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "SHA256" in out.upper()
        assert "HASHBYTES" not in out.upper()
        assert "CONVERT" not in out.upper()

    def test_output_into_maps_to_returning(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "DECLARE @id INT "
            "INSERT INTO t (a) OUTPUT inserted.id INTO @id VALUES (1) "
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "RETURNING id" in out
        assert "inserted." not in out


class TestAssignmentSelectBoundary:
    """A multi-line assignment-SELECT must not absorb the comment and the
    statements that follow it (a parser boundary bug)."""

    def test_following_statements_not_absorbed(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN\n"
            "    SELECT\n"
            "        @x = col\n"
            "    FROM t\n"
            "    WHERE id = @id\n"
            "\n"
            "    -- a note\n"
            "    SET @y = 1\n"
            "    INSERT INTO u (a) VALUES (1)\n"
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        # The assignment-select becomes SELECT ... INTO.
        assert "INTO v_x" in out
        # The comment and both following statements survive as separate stmts.
        assert "-- a note" in out
        assert "v_y := 1;" in out
        assert "INSERT INTO u (a) VALUES (1)" in out

    def test_set_does_not_swallow_following_dml(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN\n"
            "    SET @y = 1\n"
            "    INSERT INTO u (a) VALUES (1)\n"
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "v_y := 1;" in out
        assert "INSERT INTO u (a) VALUES (1)" in out


class TestPostgreSQLStringConcat:
    """T-SQL string `+` becomes the `||` operator on PostgreSQL (not `+`,
    which errors on text), while numeric `+` is left alone."""

    def test_string_concat_uses_pipes(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p @code NVARCHAR(50) AS BEGIN "
            "DECLARE @msg NVARCHAR(200) "
            "SET @msg = 'Error: ' + @code + '!' "
            "END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "'Error: ' || v_code || '!'" in out
        assert "+ v_code" not in out

    def test_numeric_addition_unchanged(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN " "DECLARE @n INT SET @n = 1 + 2 + 3 END"
        out = _transpile(src, "tsql", "postgresql")
        assert "1 + 2 + 3" in out
        assert "||" not in out

    def test_concat_with_string_var_no_literal(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p @a NVARCHAR(10), @b NVARCHAR(10) AS BEGIN "
            "DECLARE @c NVARCHAR(20) SET @c = @a + @b END"
        )
        out = _transpile(src, "tsql", "postgresql")
        # Two known string vars concatenated -> ||, not numeric +.
        assert "v_a || v_b" in out


class TestParameterlessRoutineParens:
    """MySQL and PostgreSQL require the parameter parentheses even when a
    routine takes no parameters; Oracle allows them to be omitted."""

    FUNC = "CREATE FUNCTION dbo.f() RETURNS INT AS BEGIN RETURN 1 END"
    PROC = "CREATE PROCEDURE dbo.p AS BEGIN SELECT 1 END"

    def test_mysql_function_has_empty_parens(self) -> None:
        out = _transpile(self.FUNC, "tsql", "mysql")
        assert "CREATE FUNCTION f()" in out

    def test_mysql_procedure_has_empty_parens(self) -> None:
        out = _transpile(self.PROC, "tsql", "mysql")
        assert "CREATE PROCEDURE p()" in out

    def test_postgresql_function_has_empty_parens(self) -> None:
        out = _transpile(self.FUNC, "tsql", "postgresql")
        assert "FUNCTION f()" in out

    def test_postgresql_procedure_has_empty_parens(self) -> None:
        out = _transpile(self.PROC, "tsql", "postgresql")
        assert "PROCEDURE p()" in out

    def test_mysql_function_with_params_unchanged(self) -> None:
        src = "CREATE FUNCTION dbo.f(@a INT) RETURNS INT AS BEGIN RETURN @a END"
        out = _transpile(src, "tsql", "mysql")
        # The parameter list is still emitted normally (no doubled parens).
        assert "f()" not in out
        assert "v_a INT" in out


class TestInlineTableValuedFunction:
    """T-SQL inline table-valued functions (RETURNS TABLE) have no faithful
    uniform equivalent; they must be documented and commented out, never
    emitted as invalid executable SQL."""

    SRC = (
        "CREATE FUNCTION dbo.f(@s NVARCHAR(MAX)) "
        "RETURNS TABLE AS "
        "RETURN (SELECT value AS item FROM STRING_SPLIT(@s, ','))"
    )

    def test_mysql_documents_and_comments_out(self) -> None:
        out = _transpile(self.SRC, "tsql", "mysql")
        assert "-- UNIQUE: inline table-valued function" in out
        # No executable RETURNS TABLE leaks (only commented lines).
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("RETURNS TABLE" not in ln for ln in code)

    def test_postgresql_documents_and_comments_out(self) -> None:
        out = _transpile(self.SRC, "tsql", "postgresql")
        assert "-- UNIQUE: inline table-valued function" in out
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("RETURNS TABLE" not in ln for ln in code)


class TestBareReturnInProcedure:
    """A bare RETURN (early exit) in a T-SQL procedure is illegal in a MySQL
    procedure body ('RETURN is only allowed in a FUNCTION'); it becomes LEAVE
    of a labeled block. Oracle/PostgreSQL keep a plain RETURN."""

    SRC = (
        "CREATE PROCEDURE dbo.p @x INT AS BEGIN " "IF @x < 0 RETURN " "SELECT @x " "END"
    )

    def test_mysql_uses_leave_with_label(self) -> None:
        out = _transpile(self.SRC, "tsql", "mysql")
        assert "proc_exit: BEGIN" in out
        assert "LEAVE proc_exit;" in out
        # No bare RETURN; leaks (it is invalid in a MySQL procedure).
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all(ln.strip() != "RETURN;" for ln in code)

    def test_following_statement_not_absorbed(self) -> None:
        # The SELECT after the bare RETURN must survive as its own statement.
        out = _transpile(self.SRC, "tsql", "mysql")
        assert "SELECT v_x;" in out

    def test_oracle_keeps_plain_return(self) -> None:
        out = _transpile(self.SRC, "tsql", "oracle")
        assert "RETURN;" in out
        assert "LEAVE" not in out

    def test_no_label_when_no_bare_return(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN SELECT 1 END"
        out = _transpile(src, "tsql", "mysql")
        assert "proc_exit" not in out

    def test_function_return_value_preserved(self) -> None:
        # A parenthesized subquery return value is kept (not treated as a bare
        # RETURN swallowing a SELECT).
        src = (
            "CREATE FUNCTION dbo.f() RETURNS INT AS BEGIN "
            "RETURN (SELECT COUNT(*) FROM t) END"
        )
        out = _transpile(src, "tsql", "mysql")
        normalized = " ".join(out.split())
        assert (
            "RETURN ( SELECT COUNT( * ) FROM t )" in normalized
        )  # COUNT( collapsed: MariaDB rejects 'COUNT (' without IGNORE_SPACE
        assert "LEAVE" not in out


class TestReturnValueInProcedure:
    """A T-SQL procedure RETURN <value> (a status code) has no MySQL
    equivalent; it becomes LEAVE with the value documented. In a function,
    RETURN <value> is valid and kept."""

    def test_return_value_in_procedure_becomes_leave(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p @x INT AS BEGIN "
            "IF @x IS NULL RETURN NULL "
            "SELECT @x "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "LEAVE proc_exit;" in out
        assert "discarded procedure RETURN value" in out
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        # No executable RETURN in the procedure (only LEAVE).
        assert all(not ln.strip().startswith("RETURN") for ln in code)

    def test_return_value_in_function_kept(self) -> None:
        src = (
            "CREATE FUNCTION dbo.f(@x INT) RETURNS INT AS BEGIN "
            "IF @x IS NULL RETURN 0 "
            "RETURN @x "
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "RETURN 0;" in out
        assert "RETURN v_x;" in out
        assert "LEAVE" not in out


class TestInlineCommentInCapturedExpression:
    """A line comment inside a captured multi-line expression must become a
    block comment, otherwise flattening to one line comments out the rest of
    the statement (breaking a CASE / the following statement)."""

    def test_line_comments_in_case_become_block(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN\n"
            "    SET @c = (SELECT CASE WHEN @x = 1 THEN 2  -- aaa\n"
            "                          WHEN @x = 0 THEN 1  -- bbb\n"
            "                          ELSE 0 END)          -- ccc\n"
            "    IF @c = 2\n"
            "        SELECT 1\n"
            "END"
        )
        out = _transpile(src, "tsql", "mysql")
        # The inline comments are preserved as block comments...
        assert "/* aaa */" in out
        assert "/* bbb */" in out
        # ...and no executable line stays open due to a trailing -- comment:
        # the CASE closes and the following IF is intact.
        assert "ELSE 0 END" in out
        assert "IF v_c = 2 THEN" in out
        # No '--' line comment survives inside the SET expression line.
        set_line = next(ln for ln in out.splitlines() if ln.strip().startswith("SET"))
        assert "--" not in set_line


class TestRaiserrorToMySQLSignal:
    """RAISERROR/THROW must become a valid MySQL SIGNAL: MESSAGE_TEXT is a
    string and a numeric message id goes to MYSQL_ERRNO, not a raw arg tuple."""

    def test_numeric_message_id(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN RAISERROR (16947, 16, 1) END"
        out = _transpile(src, "tsql", "mysql")
        assert "MESSAGE_TEXT = 'Application error'" in out
        assert "MYSQL_ERRNO = 16947" in out
        # The invalid tuple form must not appear.
        assert "MESSAGE_TEXT = (" not in out

    def test_string_message(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN " "RAISERROR ('Custom message', 16, 1) END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "MESSAGE_TEXT = 'Custom message'" in out
        assert "MESSAGE_TEXT = (" not in out

    def test_oracle_uses_first_arg_only(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN " "RAISERROR ('boom', 16, 1) END"
        out = _transpile(src, "tsql", "oracle")
        assert "RAISE_APPLICATION_ERROR(-20001, 'boom')" in out


class TestTableValuedFunctionInFrom:
    """A table-valued function used in FROM is invalid on MySQL (no TVFs);
    such a statement is commented out with a note. JSON_TABLE and the
    STRING_SPLIT->JSON_TABLE rewrite are valid table sources and kept."""

    def test_user_tvf_in_from_commented(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p @s NVARCHAR(200) AS BEGIN "
            "SELECT item FROM dbo.func5(@s, ',') END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "table-valued function in FROM" in out
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("FUNC5" not in ln.upper() for ln in code)

    def test_string_split_in_from_kept(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p @s NVARCHAR(MAX) AS BEGIN "
            "SELECT value FROM STRING_SPLIT(@s, ',') END"
        )
        out = _transpile(src, "tsql", "mysql")
        # STRING_SPLIT is rewritten to JSON_TABLE, a valid FROM source.
        assert "table-valued function in FROM" not in out
        assert "JSON_TABLE" in out

    def test_normal_select_not_flagged(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "SELECT a FROM t WHERE id IN (SELECT x FROM u) END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "table-valued function in FROM" not in out


class TestTransactionControl:
    """BEGIN TRAN / COMMIT / ROLLBACK / SAVE map per dialect instead of being
    mis-parsed as a BEGIN...END block or a bare statement."""

    def test_begin_transaction_mysql(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN BEGIN TRANSACTION COMMIT END"
        out = _transpile(src, "tsql", "mysql")
        assert "START TRANSACTION;" in out
        assert "COMMIT;" in out
        assert "TRANSACTION AS" not in out

    def test_begin_transaction_documented_for_oracle_pg(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN BEGIN TRAN UPDATE t SET a = 1 COMMIT END"
        for target in ("oracle", "postgresql"):
            out = _transpile(src, "tsql", target)
            assert "BEGIN TRANSACTION dropped" in out
            assert "COMMIT;" in out

    def test_rollback_to_savepoint(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN SAVE TRANSACTION sp "
            "ROLLBACK TRANSACTION sp END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "SAVEPOINT sp;" in out
        assert "ROLLBACK TO SAVEPOINT sp;" in out

    def test_roundtrip_tsql_preserves(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN BEGIN TRANSACTION COMMIT END"
        out = _transpile(src, "tsql", "tsql")
        assert "BEGIN TRANSACTION;" in out
        assert "COMMIT;" in out


class TestWaitFor:
    """WAITFOR DELAY maps to each engine's sleep; WAITFOR TIME is documented."""

    def test_delay_to_mysql(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN WAITFOR DELAY '00:00:05' END"
        out = _transpile(src, "tsql", "mysql")
        assert "DO SLEEP(5);" in out
        assert "WAITFOR" not in out

    def test_delay_to_postgresql(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN WAITFOR DELAY '00:01:30' END"
        out = _transpile(src, "tsql", "postgresql")
        assert "PERFORM pg_sleep(90);" in out

    def test_delay_to_oracle(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN WAITFOR DELAY '00:00:02' END"
        out = _transpile(src, "tsql", "oracle")
        assert "DBMS_LOCK.SLEEP(2);" in out

    def test_time_documented(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN WAITFOR TIME '23:00:00' END"
        out = _transpile(src, "tsql", "mysql")
        assert "WAITFOR TIME" in out and "no mysql equivalent" in out


class TestSetIdentityInsert:
    """SET IDENTITY_INSERT has no portable equivalent: emit a documented
    comment instead of the previously mis-parsed 'IDENTITY_INSERT AS t'."""

    def test_documented_comment(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "SET IDENTITY_INSERT t ON "
            "INSERT INTO t (id, a) VALUES (1, 2) "
            "SET IDENTITY_INSERT t OFF END"
        )
        out = _transpile(src, "tsql", "mysql")
        assert "SET IDENTITY_INSERT t ON" in out
        assert "SET IDENTITY_INSERT t OFF" in out
        assert "IDENTITY_INSERT AS" not in out
        # The INSERT must not absorb the trailing SET as a table alias.
        assert "AS `SET`" not in out


class TestErrorGlobalInCondition:
    """@@ERROR/@@TRANCOUNT have no faithful non-T-SQL equivalent; in a
    condition they must not leave a syntactically broken operand."""

    def test_error_in_if_mysql(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "UPDATE t SET a = 1 IF @@ERROR <> 0 RETURN END"
        )
        out = _transpile(src, "tsql", "mysql")
        # Valid neutral operand + documenting comment, not a bare /* @@ERROR */.
        assert "IF 0 /* UNIQUE: @@ERROR" in out
        assert "IF /* @@ERROR */" not in out

    def test_error_in_if_postgresql(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "UPDATE t SET a = 1 IF @@ERROR <> 0 RETURN END"
        )
        out = _transpile(src, "tsql", "postgresql")
        assert "IF 0 /* UNIQUE: @@ERROR" in out
        assert "SQLSTATE" not in out

    def test_error_in_if_oracle_uses_sqlcode(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS BEGIN "
            "UPDATE t SET a = 1 IF @@ERROR <> 0 RETURN END"
        )
        out = _transpile(src, "tsql", "oracle")
        assert "IF SQLCODE <> 0" in out

    def test_trancount_not_broken(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN IF @@TRANCOUNT > 0 COMMIT END"
        for target in ("mysql", "postgresql"):
            out = _transpile(src, "tsql", target)
            assert "IF 0 /* UNIQUE: @@TRANCOUNT" in out


class TestCarrierTypeRestoration:
    """A non-portable type lowered to a carrier with the original preserved in a
    /* UNIQUE: <orig> */ comment is restored on a reverse/onward transpilation:
    the original returns where the target supports it, and a carrier is
    re-applied where it doesn't."""

    def _decl_line(self, sql: str, var: str) -> str:
        return next(ln.strip() for ln in sql.splitlines() if var in ln)

    def test_sql_variant_round_trips_to_tsql(self) -> None:
        carrier = _transpile(
            "CREATE PROCEDURE p AS BEGIN DECLARE @v SQL_VARIANT END",
            "tsql",
            "postgresql",
        )
        assert "TEXT /* UNIQUE: SQL_VARIANT */" in carrier
        back = _transpile(
            carrier.replace("CREATE OR REPLACE", "CREATE"), "postgresql", "tsql"
        )
        line = self._decl_line(back, "@v")
        assert "SQL_VARIANT" in line
        assert "/* UNIQUE:" not in line  # no redundant carrier comment

    def test_sql_variant_recarriered_for_other_target(self) -> None:
        carrier = _transpile(
            "CREATE PROCEDURE p AS BEGIN DECLARE @v SQL_VARIANT END",
            "tsql",
            "postgresql",
        ).replace("CREATE OR REPLACE", "CREATE")
        mysql = _transpile(carrier, "postgresql", "mysql")
        assert "LONGTEXT /* UNIQUE: SQL_VARIANT */" in mysql
        oracle = _transpile(carrier, "postgresql", "oracle")
        assert "ANYDATA /* UNIQUE: SQL_VARIANT */" in oracle

    def test_type_reference_round_trips_to_oracle(self) -> None:
        carrier = _transpile(
            "CREATE PROCEDURE p AS v_x emp.sal%TYPE; BEGIN NULL; END;",
            "oracle",
            "mysql",
        )
        assert "/* UNIQUE: emp.sal%TYPE */" in carrier
        back = _transpile(carrier, "mysql", "oracle")
        line = self._decl_line(back, "v_x")
        assert "emp.sal%TYPE" in line
        assert "/* UNIQUE:" not in line

    def test_non_carrier_comment_not_treated_as_type(self) -> None:
        # A regular type followed by an unrelated comment must be unaffected.
        out = _transpile(
            "CREATE PROCEDURE p AS BEGIN DECLARE @n INT END", "tsql", "postgresql"
        )
        assert "v_n INTEGER" in out


class TestPerEngineRoutineSurface:
    """Guards the per-engine emitter overrides that have thin test coverage:
    Oracle's RETURN clause + explicit IN on function params, and the PRINT /
    RAISERROR mappings for each engine. These caught a regression during the
    per-engine emitter refactor."""

    FUNC = "CREATE FUNCTION dbo.f(@a INT) RETURNS INT AS BEGIN RETURN @a END"

    def test_oracle_function_uses_return_not_returns(self) -> None:
        out = _transpile(self.FUNC, "tsql", "oracle")
        # Unconstrained in RETURN position: NUMBER(10) is PLS-00103
        # (audit 2026-07-02, S1-11).
        assert "\nRETURN NUMBER" in out
        assert "RETURN NUMBER(10)" not in out
        assert "RETURNS" not in out

    def test_oracle_function_param_is_in(self) -> None:
        out = _transpile(self.FUNC, "tsql", "oracle")
        # Unconstrained in parameter position (audit 2026-07-02, S1-11).
        assert "IN NUMBER" in out
        assert "IN NUMBER(10)" not in out

    def test_print_per_engine(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN PRINT 'hi' END"
        assert "PRINT 'hi';" in _transpile(src, "tsql", "tsql")
        assert "DBMS_OUTPUT.PUT_LINE('hi');" in _transpile(src, "tsql", "oracle")
        assert "RAISE NOTICE '%', 'hi';" in _transpile(src, "tsql", "postgresql")
        assert "SELECT 'hi';" in _transpile(src, "tsql", "mysql")

    def test_raiserror_per_engine(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN RAISERROR('boom', 16, 1) END"
        assert "RAISERROR(" in _transpile(src, "tsql", "tsql")
        assert "RAISE_APPLICATION_ERROR(-20001, 'boom');" in _transpile(
            src, "tsql", "oracle"
        )
        assert "RAISE EXCEPTION '%', 'boom';" in _transpile(src, "tsql", "postgresql")
        assert "SIGNAL SQLSTATE '45000'" in _transpile(src, "tsql", "mysql")


class TestBracketedRoutineHeaders:
    """T-SQL bracket-quoted routine names and types must be translated.

    SSMS-generated scripts quote everything: CREATE FUNCTION [dbo].[fn]
    (@p [tinyint]) RETURNS [nvarchar](15). The brackets are T-SQL-only
    quoting (audit S1-1); leaking them into another engine's routine
    header is invalid SQL there (found on AdventureWorksLT).
    """

    SQL = (
        "CREATE FUNCTION [dbo].[ufnGetStatusText](@Status [tinyint])\n"
        "RETURNS [nvarchar](15)\n"
        "AS\n"
        "BEGIN\n"
        "    DECLARE @ret [nvarchar](15);\n"
        "    SET @ret = 'x';\n"
        "    RETURN @ret\n"
        "END"
    )

    def _executable(self, out: str) -> str:
        return "\n".join(
            line for line in out.splitlines() if not line.lstrip().startswith("--")
        )

    def test_postgresql_header_unbracketed_and_types_mapped(self) -> None:
        out = _transpile(self.SQL, "tsql", "postgresql")
        body = self._executable(out)
        assert "[" not in body, out
        assert "ufnGetStatusText" in out
        # dbo has no meaning on PostgreSQL; the routine lands unqualified.
        assert "dbo." not in body
        assert "VARCHAR(15)" in out
        assert "SMALLINT" in out  # tinyint

    def test_mysql_header_unbracketed_and_types_mapped(self) -> None:
        out = _transpile(self.SQL, "tsql", "mysql")
        body = self._executable(out)
        assert "[" not in body, out
        assert "ufnGetStatusText" in out
        assert "VARCHAR(15)" in out
        assert "TINYINT" in out

    def test_oracle_header_unbracketed_and_types_mapped(self) -> None:
        out = _transpile(self.SQL, "tsql", "oracle")
        body = self._executable(out)
        assert "[" not in body, out
        assert "ufnGetStatusText".upper() in out.upper()
        assert "NVARCHAR2" in out
        # tinyint -> NUMBER; the parameter position is unconstrained (S1-11).
        assert "V_STATUS IN NUMBER" in out


class TestBacktickedTriggerHeaders:
    """MySQL backtick-quoted trigger headers must be translated.

    The procedural lexer used to have no backtick tokenization, so
    CREATE TRIGGER `ins_film` ... ON `film` shredded into fragments
    (found on the sakila schema).
    """

    SQL = (
        "CREATE TRIGGER `ins_film` AFTER INSERT ON `film` FOR EACH ROW BEGIN\n"
        "    INSERT INTO film_text (film_id, title)\n"
        "        VALUES (new.film_id, new.title);\n"
        "  END;;\n"
    )

    def test_postgresql_trigger_header(self) -> None:
        out = _transpile(self.SQL, "mysql", "postgresql")
        body = "\n".join(
            line for line in out.splitlines() if not line.lstrip().startswith("--")
        )
        assert "`" not in body, out
        assert "ins_film" in out
        assert "ON film" in out

    def test_tsql_trigger_header(self) -> None:
        out = _transpile(self.SQL, "mysql", "tsql")
        body = "\n".join(
            line for line in out.splitlines() if not line.lstrip().startswith("--")
        )
        assert "`" not in body, out
        assert "ins_film" in out

    def test_oracle_trigger_header(self) -> None:
        out = _transpile(self.SQL, "mysql", "oracle")
        body = "\n".join(
            line for line in out.splitlines() if not line.lstrip().startswith("--")
        )
        assert "`" not in body, out
        assert "ins_film" in out.lower()


class TestAssignmentSelectDboStrip:
    """The dbo. qualifier must be stripped from assignment-select bodies on
    every non-T-SQL target, not only Oracle (PostgreSQL has no dbo schema; a
    MySQL qualifier names a database). Found via the FE S2-3 scenario."""

    SQL = (
        "CREATE PROCEDURE dbo.p @id INT AS BEGIN "
        "DECLARE @amt DECIMAL(12,2); "
        "SELECT @amt = amount FROM dbo.payment WHERE invoice_id = @id; "
        "END"
    )

    def test_postgresql_select_into_has_no_dbo(self) -> None:
        out = _transpile(self.SQL, "tsql", "postgresql")
        assert "dbo" not in out, out
        assert "FROM payment" in out

    def test_mysql_select_into_has_no_dbo(self) -> None:
        out = _transpile(self.SQL, "tsql", "mysql")
        assert "dbo" not in out, out
        assert "FROM payment" in out


class TestMySQLFunctionCallSpacing:
    """MySQL/MariaDB reject a space between a built-in function name and its
    parenthesis under the default sql_mode (no IGNORE_SPACE): the procedural
    pipeline's token-joined expressions emitted 'CAST ( ... )', which broke
    fn_tax on the live FE run."""

    def test_cast_has_no_space_before_paren(self) -> None:
        sql = (
            "CREATE FUNCTION dbo.fn_tax (@net DECIMAL(12, 2))\n"
            "RETURNS DECIMAL(12, 2)\n"
            "AS\nBEGIN\n"
            "    RETURN @net * CAST(0.10 AS DECIMAL(12, 2));\n"
            "END"
        )
        out = _transpile(sql, "tsql", "mysql")
        assert "CAST(" in out.replace("CAST  (", "CAST (")
        assert not re.search(r"(?i)\bCAST\s+\(", out), out


class TestLastInsertIdCrossDialect:
    """The 'last generated id' function differs per engine (T-SQL
    SCOPE_IDENTITY / PostgreSQL LASTVAL / MySQL LAST_INSERT_ID). It must be
    translated regardless of source, not only from T-SQL (the MySQL native
    FE fixture captures it in create_invoice — a live-run finding)."""

    def _proc(self, get_id_call: str) -> str:
        return (
            "CREATE PROCEDURE mk()\n"
            "BEGIN\n"
            "    DECLARE v_id INT;\n"
            "    INSERT INTO t (a) VALUES (1);\n"
            f"    SET v_id = {get_id_call};\n"
            "END"
        )

    def test_mysql_last_insert_id_to_postgresql(self) -> None:
        out = _transpile(self._proc("LAST_INSERT_ID()"), "mysql", "postgresql")
        assert "LASTVAL()" in out.upper()
        assert "LAST_INSERT_ID" not in out.upper()

    def test_mysql_last_insert_id_roundtrip(self) -> None:
        out = _transpile(self._proc("LAST_INSERT_ID()"), "mysql", "mysql")
        # Tolerate the token-joiner's cosmetic inner-paren space (valid MariaDB).
        assert "LAST_INSERT_ID(" in out.upper()
        assert "LASTVAL" not in out.upper()

    def test_postgresql_lastval_to_mysql(self) -> None:
        proc = (
            "CREATE PROCEDURE mk()\n"
            "LANGUAGE plpgsql AS $$\n"
            "DECLARE v_id INT;\n"
            "BEGIN\n"
            "    INSERT INTO t (a) VALUES (1);\n"
            "    v_id := LASTVAL();\n"
            "END;\n$$;"
        )
        out = _transpile(proc, "postgresql", "mysql")
        assert "LAST_INSERT_ID()" in out.upper()
        assert "LASTVAL" not in out.upper()


class TestOracleAnonymousBlock:
    """A top-level Oracle anonymous block (``BEGIN … END;``) — the re-runnable
    DROP guard the native Oracle FE fixture opens with — used to fall to the
    sqlglot DML path and mangle into invalid fragments (``FOR r IN (...) AS
    LOOP;``, ``END AS LOOP;``, ``-- UNIQUE: … Transaction``). It must instead
    route to the procedural engine: faithfully to a PostgreSQL ``DO $$ … $$``
    block (which supports anonymous blocks, cursor FOR-loops and dynamic
    EXECUTE), and to a documented degradation on MySQL (which cannot run
    procedural code outside a stored routine) — never invalid SQL."""

    BLOCK = (
        "BEGIN\n"
        "    FOR r IN (\n"
        "        SELECT 'DROP TABLE ' || table_name AS cmd\n"
        "        FROM user_tables\n"
        "        WHERE table_name IN ('PAYMENT', 'INVOICE')\n"
        "    ) LOOP\n"
        "        EXECUTE IMMEDIATE r.cmd;\n"
        "    END LOOP;\n"
        "END;"
    )

    def test_to_postgresql_do_block(self) -> None:
        out = _transpile(self.BLOCK, "oracle", "postgresql")
        upper = out.upper()
        # Wrapped in a PL/pgSQL DO block (anonymous blocks need one on PG).
        assert "DO $$" in upper
        assert "$$;" in out
        # Cursor FOR-loop survives.
        assert "FOR R IN" in upper
        assert "END LOOP" in upper
        # Oracle's EXECUTE IMMEDIATE becomes PL/pgSQL EXECUTE (dynamic SQL).
        assert "EXECUTE IMMEDIATE" not in upper
        assert re.search(r"(?i)\bEXECUTE\s+r\s*\.\s*cmd", out), out
        # None of the old mangled fragments.
        assert "AS LOOP" not in upper
        assert "UNIQUE: UNHANDLED" not in upper

    def test_to_mysql_degrades_with_warning(self) -> None:
        result = Transpiler().transpile(self.BLOCK, source="oracle", target="mysql")
        code = result.sql.split("--")[0].split("/*")[0]
        # No bare, top-level procedural code leaks as executable MySQL.
        assert "FOR R IN" not in code.upper()
        assert "EXECUTE IMMEDIATE" not in code.upper()
        # The loss is documented in the result object (no silent loss).
        assert result.warnings or result.unsupported
        # A carrier comment preserves the original for the reader.
        assert "UNIQUE:" in result.sql

    def test_oracle_roundtrip_stays_valid(self) -> None:
        out = _transpile(self.BLOCK, "oracle", "oracle")
        upper = out.upper()
        assert upper.strip().startswith("BEGIN")
        assert "FOR R IN" in upper
        assert "EXECUTE IMMEDIATE" in upper
        assert "END LOOP;" in upper
        assert "AS LOOP" not in upper


class TestStandaloneCall:
    """A standalone ``CALL proc(args)`` (a scenario invoking a stored procedure
    from a MySQL/PostgreSQL source) must become each target's call form, not an
    ``-- UNIQUE: Unhandled expression type: Command`` comment (which silently
    dropped the call — the FE-harness blocker for the pg↔mysql pairs)."""

    CALL = "CALL create_invoice(2, '2024-02-01', 1, 1, 2, 1);"

    def _code(self, sql: str) -> str:
        return "\n".join(
            line for line in sql.split("\n") if not line.strip().startswith("--")
        )

    def test_mysql_to_postgresql_keeps_call(self) -> None:
        out = _transpile(self.CALL, "mysql", "postgresql")
        assert "CALL create_invoice(2, '2024-02-01', 1, 1, 2, 1)" in out
        assert "Unhandled expression" not in out

    def test_postgresql_to_mysql_keeps_call(self) -> None:
        out = _transpile(self.CALL, "postgresql", "mysql")
        assert "CALL create_invoice(2, '2024-02-01', 1, 1, 2, 1)" in out
        assert "Unhandled expression" not in out

    def test_mysql_to_oracle_wraps_in_block(self) -> None:
        out = _transpile(self.CALL, "mysql", "oracle")
        code = self._code(out)
        # Oracle invokes by bare name inside a PL/SQL block, no CALL keyword.
        assert "create_invoice(2, '2024-02-01', 1, 1, 2, 1)" in code
        assert "BEGIN" in code.upper() and "END;" in code.upper()
        assert "CALL " not in code.upper()

    def test_mysql_to_tsql_uses_exec(self) -> None:
        out = _transpile(self.CALL, "mysql", "tsql")
        code = self._code(out)
        assert "EXEC create_invoice 2, '2024-02-01', 1, 1, 2, 1" in code
        assert "CALL " not in code.upper()


class TestReturningIntoCaptureToMySQL:
    """PostgreSQL ``INSERT … RETURNING id INTO v`` captures a generated id.
    MySQL has no RETURNING, so it must become ``INSERT …; SET v =
    LAST_INSERT_ID();`` — not a dropped capture that leaves ``v`` NULL (the
    create_invoice failure on the postgresql→mysql live run)."""

    PROC = (
        "CREATE PROCEDURE mk() LANGUAGE plpgsql AS $$\n"
        "DECLARE v_new_id INT;\n"
        "BEGIN\n"
        "    INSERT INTO invoice (customer_id) VALUES (1) RETURNING id INTO v_new_id;\n"
        "    INSERT INTO line (invoice_id) VALUES (v_new_id);\n"
        "END;\n$$;"
    )

    def test_returning_into_becomes_last_insert_id(self) -> None:
        out = _transpile(self.PROC, "postgresql", "mysql")
        code = "\n".join(
            line for line in out.split("\n") if not line.strip().startswith("--")
        )
        assert "RETURNING" not in code.upper()
        assert "SET v_new_id = LAST_INSERT_ID()" in code
        # The INSERT itself is preserved.
        assert "INSERT INTO invoice" in code

    def test_returning_into_preserved_for_postgresql(self) -> None:
        # pg->pg keeps the native RETURNING … INTO (no LAST_INSERT_ID).
        out = _transpile(self.PROC, "postgresql", "postgresql")
        assert "LAST_INSERT_ID" not in out.upper()
        assert "RETURNING" in out.upper()


class TestOracleCatalogDropBlock:
    """The Oracle re-runnable DROP guard queries the data dictionary
    (USER_TABLES / USER_OBJECTS). Those views exist on no other engine, so even
    a syntactically valid PostgreSQL DO $$ block fails at runtime — it must
    degrade to a documented comment on every non-Oracle target (the harness
    recreates a clean schema itself)."""

    BLOCK = (
        "BEGIN\n"
        "    FOR r IN (SELECT 'DROP TABLE ' || table_name AS cmd\n"
        "              FROM user_tables WHERE table_name IN ('T')) LOOP\n"
        "        EXECUTE IMMEDIATE r.cmd;\n"
        "    END LOOP;\n"
        "END;"
    )

    def _code(self, sql: str) -> str:
        return "\n".join(
            line for line in sql.split("\n") if not line.strip().startswith("--")
        )

    def test_degrades_on_postgresql(self) -> None:
        result = Transpiler().transpile(
            self.BLOCK, source="oracle", target="postgresql"
        )
        # No executable reference to the Oracle catalog view.
        assert "user_tables" not in self._code(result.sql).lower()
        assert "UNIQUE:" in result.sql
        assert result.warnings or result.unsupported

    def test_degrades_on_mysql(self) -> None:
        result = Transpiler().transpile(self.BLOCK, source="oracle", target="mysql")
        assert "user_tables" not in self._code(result.sql).lower()
        assert result.warnings or result.unsupported
