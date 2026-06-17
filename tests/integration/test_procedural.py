# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""End-to-end procedural transpilation tests.

These exercise the full pipeline (split -> classify -> parse -> transform
-> emit) on representative procedures drawn from real-world patterns.
"""

from __future__ import annotations

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

    def test_for_cursor_loop_flagged_in_tsql(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "FOR rec IN (SELECT id FROM t) LOOP "
            "INSERT INTO log VALUES (rec.id); "
            "END LOOP; END;"
        )
        out = _transpile(src, "oracle", "tsql")
        assert "UNIQUE: no implicit cursor FOR-loop" in out

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
