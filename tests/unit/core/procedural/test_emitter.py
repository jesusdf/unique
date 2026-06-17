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

"""Tests for the procedural emitter."""

from __future__ import annotations

from unique.core.ast_nodes import (
    AssignmentStatement,
    CreateProcedureStatement,
    CursorOperation,
    DataType,
    DeclareStatement,
    IfStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SetVariableStatement,
    WhileStatement,
)
from unique.core.procedural.emitter import ProceduralEmitter


class TestDataType:
    def test_type_with_params(self) -> None:
        e = ProceduralEmitter("oracle")
        assert e._emit_data_type(DataType(name="NUMBER", params=(10, 2))) == (
            "NUMBER(10, 2)"
        )

    def test_type_with_max(self) -> None:
        e = ProceduralEmitter("tsql")
        assert e._emit_data_type(DataType(name="VARCHAR", params=(-1,))) == (
            "VARCHAR(MAX)"
        )

    def test_type_without_params(self) -> None:
        e = ProceduralEmitter("oracle")
        assert e._emit_data_type(DataType(name="DATE")) == "DATE"


class TestDeclare:
    def test_tsql_declare(self) -> None:
        e = ProceduralEmitter("tsql")
        node = DeclareStatement(name="@x", data_type=DataType(name="INT"))
        assert e._emit_declare(node) == "DECLARE @x INT;"

    def test_oracle_declare_no_declare_keyword(self) -> None:
        e = ProceduralEmitter("oracle")
        node = DeclareStatement(name="v_x", data_type=DataType(name="NUMBER"))
        result = e._emit_declare(node)
        assert result == "v_x NUMBER;"

    def test_declare_with_default_tsql(self) -> None:
        e = ProceduralEmitter("tsql")
        node = DeclareStatement(
            name="@x",
            data_type=DataType(name="INT"),
            default=RawSQL(sql="0", reason="x"),
        )
        assert "= 0" in e._emit_declare(node)

    def test_declare_with_default_oracle(self) -> None:
        e = ProceduralEmitter("oracle")
        node = DeclareStatement(
            name="v_x",
            data_type=DataType(name="NUMBER"),
            default=RawSQL(sql="0", reason="x"),
        )
        assert ":= 0" in e._emit_declare(node)


class TestAssignment:
    def test_tsql_uses_set(self) -> None:
        e = ProceduralEmitter("tsql")
        node = AssignmentStatement(target="@x", value=RawSQL(sql="1", reason="x"))
        assert e._emit_assignment(node) == "SET @x = 1;"

    def test_oracle_uses_colon_equals(self) -> None:
        e = ProceduralEmitter("oracle")
        node = AssignmentStatement(target="v_x", value=RawSQL(sql="1", reason="x"))
        assert e._emit_assignment(node) == "v_x := 1;"


class TestIf:
    def test_tsql_if_uses_begin_end(self) -> None:
        e = ProceduralEmitter("tsql")
        node = IfStatement(
            condition=RawSQL(sql="@x > 0", reason="c"),
            then_body=(PrintStatement(expression=RawSQL(sql="'hi'", reason="x")),),
        )
        out = e._emit_if(node)
        assert "IF @x > 0" in out
        assert "BEGIN" in out
        assert "END" in out

    def test_oracle_if_uses_then_end_if(self) -> None:
        e = ProceduralEmitter("oracle")
        node = IfStatement(
            condition=RawSQL(sql="x > 0", reason="c"),
            then_body=(ReturnStatement(),),
        )
        out = e._emit_if(node)
        assert "THEN" in out
        assert "END IF;" in out

    def test_oracle_if_else(self) -> None:
        e = ProceduralEmitter("oracle")
        node = IfStatement(
            condition=RawSQL(sql="x > 0", reason="c"),
            then_body=(ReturnStatement(),),
            else_body=(ReturnStatement(),),
        )
        out = e._emit_if(node)
        assert "ELSE" in out


class TestWhile:
    def test_tsql_while(self) -> None:
        e = ProceduralEmitter("tsql")
        node = WhileStatement(
            condition=RawSQL(sql="@x > 0", reason="c"),
            body=(ReturnStatement(),),
        )
        out = e._emit_while(node)
        assert "WHILE @x > 0" in out
        assert "BEGIN" in out

    def test_oracle_while_uses_loop(self) -> None:
        e = ProceduralEmitter("oracle")
        node = WhileStatement(
            condition=RawSQL(sql="x > 0", reason="c"),
            body=(ReturnStatement(),),
        )
        out = e._emit_while(node)
        assert "LOOP" in out
        assert "END LOOP;" in out


class TestPrint:
    def test_tsql_print(self) -> None:
        e = ProceduralEmitter("tsql")
        node = PrintStatement(expression=RawSQL(sql="'hi'", reason="x"))
        assert e._emit_print(node) == "PRINT 'hi';"

    def test_oracle_dbms_output(self) -> None:
        e = ProceduralEmitter("oracle")
        node = PrintStatement(expression=RawSQL(sql="'hi'", reason="x"))
        assert e._emit_print(node) == "DBMS_OUTPUT.PUT_LINE('hi');"

    def test_postgresql_raise_notice(self) -> None:
        e = ProceduralEmitter("postgresql")
        node = PrintStatement(expression=RawSQL(sql="'hi'", reason="x"))
        assert "RAISE NOTICE" in e._emit_print(node)


class TestRaiseError:
    def test_tsql_raiserror(self) -> None:
        e = ProceduralEmitter("tsql")
        node = RaiseErrorStatement(message=RawSQL(sql="'oops'", reason="x"))
        assert "RAISERROR" in e._emit_raise_error(node)

    def test_oracle_raise_application_error(self) -> None:
        e = ProceduralEmitter("oracle")
        node = RaiseErrorStatement(message=RawSQL(sql="'oops'", reason="x"))
        assert "RAISE_APPLICATION_ERROR" in e._emit_raise_error(node)


class TestCursorOps:
    def test_tsql_fetch_uses_next_from(self) -> None:
        e = ProceduralEmitter("tsql")
        node = CursorOperation(
            operation="FETCH", cursor_name="c", into_vars=("@a", "@b")
        )
        out = e._emit_cursor_op(node)
        assert "FETCH NEXT FROM c" in out
        assert "INTO @a, @b" in out

    def test_oracle_fetch(self) -> None:
        e = ProceduralEmitter("oracle")
        node = CursorOperation(operation="FETCH", cursor_name="c", into_vars=("v_a",))
        out = e._emit_cursor_op(node)
        assert "FETCH c INTO v_a" in out

    def test_close(self) -> None:
        e = ProceduralEmitter("oracle")
        node = CursorOperation(operation="CLOSE", cursor_name="c")
        assert e._emit_cursor_op(node) == "CLOSE c;"


class TestProcedureStructure:
    def _proc(self) -> CreateProcedureStatement:
        return CreateProcedureStatement(
            name="p",
            parameters=(
                ParameterDefinition(
                    name="@id", data_type=DataType(name="INT"), direction="IN"
                ),
            ),
            body=(SetVariableStatement(name="@id", value=RawSQL(sql="1", reason="x")),),
        )

    def test_tsql_procedure_structure(self) -> None:
        e = ProceduralEmitter("tsql")
        out = e.emit(self._proc())
        assert "CREATE PROCEDURE p" in out
        assert "AS" in out
        assert "BEGIN" in out
        assert out.rstrip().endswith("END")

    def test_oracle_procedure_structure(self) -> None:
        e = ProceduralEmitter("oracle")
        out = e.emit(self._proc())
        assert "PROCEDURE p" in out
        assert out.rstrip().endswith("END;")

    def test_postgresql_procedure_uses_dollar_quoting(self) -> None:
        e = ProceduralEmitter("postgresql")
        out = e.emit(self._proc())
        assert "$$" in out
        assert "LANGUAGE plpgsql" in out
