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

"""Tests for the procedural SQL parser."""

from __future__ import annotations

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    DeclareStatement,
    IfStatement,
    WhileStatement,
)
from unique.core.procedural.parser import ProceduralParser


def _parse(sql: str, dialect: str = "tsql"):
    return ProceduralParser(dialect).parse(sql)


class TestTSQLProcedure:
    def test_parenless_parameters(self) -> None:
        sql = "CREATE PROCEDURE dbo.P @a INT, @b NVARCHAR(50) AS BEGIN SELECT 1 END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, CreateProcedureStatement)
        assert len(result.node.parameters) == 2
        assert result.node.parameters[0].name == "@a"
        assert result.node.parameters[1].name == "@b"

    def test_schema_captured(self) -> None:
        sql = "CREATE PROCEDURE dbo.MyProc AS BEGIN SELECT 1 END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, CreateProcedureStatement)
        assert result.node.name == "MyProc"
        assert result.node.schema == "dbo"

    def test_declare_in_body(self) -> None:
        sql = "CREATE PROCEDURE p AS BEGIN DECLARE @x INT; END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, CreateProcedureStatement)
        declares = [s for s in result.node.body if isinstance(s, DeclareStatement)]
        assert len(declares) == 1
        assert declares[0].name == "@x"

    def test_if_block(self) -> None:
        sql = "CREATE PROCEDURE p AS BEGIN " "IF @x > 0 BEGIN SELECT 1 END " "END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, CreateProcedureStatement)
        ifs = [s for s in result.node.body if isinstance(s, IfStatement)]
        assert len(ifs) == 1

    def test_if_else(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN "
            "IF @x > 0 BEGIN SELECT 1 END ELSE BEGIN SELECT 2 END "
            "END"
        )
        result = _parse(sql, "tsql")
        ifs = [s for s in result.node.body if isinstance(s, IfStatement)]
        assert len(ifs) == 1
        assert len(ifs[0].else_body) > 0

    def test_while_loop(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN "
            "WHILE @x > 0 BEGIN SET @x = @x - 1 END "
            "END"
        )
        result = _parse(sql, "tsql")
        whiles = [s for s in result.node.body if isinstance(s, WhileStatement)]
        assert len(whiles) == 1

    def test_alter_procedure(self) -> None:
        sql = "ALTER PROCEDURE dbo.P AS BEGIN SELECT 1 END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, AlterProcedureStatement)


class TestTSQLFunction:
    def test_function_with_return_type(self) -> None:
        sql = "CREATE FUNCTION dbo.F(@x INT) RETURNS INT AS BEGIN RETURN @x END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, CreateFunctionStatement)
        assert result.node.return_type is not None


class TestTSQLTrigger:
    def test_trigger_parsed(self) -> None:
        sql = "CREATE TRIGGER trg ON dbo.tbl AFTER INSERT AS " "BEGIN SELECT 1 END"
        result = _parse(sql, "tsql")
        assert isinstance(result.node, CreateTriggerStatement)
        assert "INSERT" in result.node.events


class TestPLSQLProcedure:
    def test_parameters_with_in_out(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p(a IN NUMBER, b OUT VARCHAR2) IS "
            "BEGIN NULL; END;"
        )
        result = _parse(sql, "oracle")
        assert isinstance(result.node, CreateProcedureStatement)
        assert len(result.node.parameters) == 2
        assert result.node.parameters[0].direction == "IN"
        assert result.node.parameters[1].direction == "OUT"

    def test_or_replace_flag(self) -> None:
        sql = "CREATE OR REPLACE PROCEDURE p IS BEGIN NULL; END;"
        result = _parse(sql, "oracle")
        assert isinstance(result.node, CreateProcedureStatement)
        assert result.node.or_replace is True

    def test_declare_section(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p IS "
            "v_x NUMBER(10); v_y VARCHAR2(50); "
            "BEGIN NULL; END;"
        )
        result = _parse(sql, "oracle")
        declares = [s for s in result.node.body if isinstance(s, DeclareStatement)]
        assert len(declares) == 2

    def test_type_reference_in_declaration(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p IS "
            "v_sal employees.salary%TYPE; "
            "BEGIN NULL; END;"
        )
        result = _parse(sql, "oracle")
        declares = [s for s in result.node.body if isinstance(s, DeclareStatement)]
        assert len(declares) == 1
        assert "%TYPE" in declares[0].data_type.name

    def test_if_elsif_else(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "IF x > 1 THEN NULL; ELSIF x > 0 THEN NULL; ELSE NULL; END IF; "
            "END;"
        )
        result = _parse(sql, "oracle")
        ifs = [s for s in result.node.body if isinstance(s, IfStatement)]
        assert len(ifs) == 1

    def test_while_loop(self) -> None:
        sql = (
            "CREATE OR REPLACE PROCEDURE p IS BEGIN "
            "WHILE x > 0 LOOP x := x - 1; END LOOP; "
            "END;"
        )
        result = _parse(sql, "oracle")
        whiles = [s for s in result.node.body if isinstance(s, WhileStatement)]
        assert len(whiles) == 1


class TestSemicolonLessTSQL:
    def test_table_variable_does_not_hang(self) -> None:
        # Regression: DECLARE @t TABLE (...) previously caused an infinite
        # loop in data-type parsing.
        sql = "CREATE PROCEDURE p AS BEGIN " "DECLARE @r TABLE (id INT); SELECT 1 END"
        result = _parse(sql, "tsql")
        assert result.node is not None
        assert len(result.node.body) >= 1

    def test_multiple_statements_without_semicolons(self) -> None:
        # T-SQL allows newline-separated statements without semicolons.
        sql = (
            "CREATE PROCEDURE p AS BEGIN\n"
            "DECLARE @x INT\n"
            "SET @x = 1\n"
            "IF @x > 0 BEGIN PRINT 'hi' END\n"
            "RETURN\n"
            "END"
        )
        result = _parse(sql, "tsql")
        kinds = [type(s).__name__ for s in result.node.body]
        assert "DeclareStatement" in kinds
        assert "IfStatement" in kinds
        assert "ReturnStatement" in kinds

    def test_set_assignment_distinguished_from_update_set(self) -> None:
        # "SET @v = ..." is an assignment; "UPDATE t SET col = ..." is not.
        sql = (
            "CREATE PROCEDURE p AS BEGIN\n"
            "UPDATE t SET col = 1 WHERE id = 2\n"
            "SET @v = 3\n"
            "END"
        )
        result = _parse(sql, "tsql")
        kinds = [type(s).__name__ for s in result.node.body]
        # The UPDATE and the assignment must be separate statements.
        assert "EmbeddedDML" in kinds
        assert "SetVariableStatement" in kinds


class TestTriggerPredicates:
    def test_if_update_column_predicate(self) -> None:
        # IF UPDATE(col) is a trigger predicate (a function call), not the
        # start of an UPDATE statement; its body must not be swallowed.
        sql = (
            "CREATE TRIGGER t ON tbl AFTER UPDATE AS BEGIN\n"
            "  IF UPDATE(isonline)\n"
            "  BEGIN\n"
            "    INSERT INTO log VALUES (1);\n"
            "  END\n"
            "END"
        )
        result = _parse(sql, "tsql")

        # Locate the IF node.
        from unique.core.ast_nodes import IfStatement

        def find_if(node: object) -> object | None:
            if isinstance(node, IfStatement):
                return node
            for f in getattr(node, "__dataclass_fields__", {}):
                v = getattr(node, f)
                items = v if isinstance(v, tuple) else (v,)
                for x in items:
                    if hasattr(x, "__dataclass_fields__"):
                        found = find_if(x)
                        if found:
                            return found
            return None

        iff = find_if(result.node)
        assert iff is not None
        assert "UPDATE" in iff.condition.sql
        assert "isonline" in iff.condition.sql
        # The INSERT must be in the body, not merged into the condition.
        body_kinds = [type(s).__name__ for s in iff.then_body]
        assert "EmbeddedDML" in body_kinds


class TestMultiVariableDeclare:
    def test_single_declare_multiple_vars(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN "
            "DECLARE @a INT, @b VARCHAR(10), @c DATETIME; "
            "SELECT 1 END"
        )
        result = _parse(sql, "tsql")
        decls = [s for s in result.node.body if type(s).__name__ == "StatementList"]
        # The multi-variable DECLARE expands to a StatementList of 3.
        assert len(decls) == 1
        assert len(decls[0].statements) == 3
        names = [d.name for d in decls[0].statements]
        assert names == ["@a", "@b", "@c"]

    def test_multi_declare_with_default(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN "
            "DECLARE @a INT = 0, @b INT = 5; "
            "SELECT 1 END"
        )
        result = _parse(sql, "tsql")
        sl = [s for s in result.node.body if type(s).__name__ == "StatementList"]
        assert len(sl) == 1
        assert len(sl[0].statements) == 2
        assert sl[0].statements[0].default is not None

    def test_single_var_declare_unchanged(self) -> None:
        sql = "CREATE PROCEDURE p AS BEGIN DECLARE @a INT; SELECT 1 END"
        result = _parse(sql, "tsql")
        decls = [s for s in result.node.body if type(s).__name__ == "DeclareStatement"]
        assert len(decls) == 1


class TestConsecutiveDML:
    def test_consecutive_deletes_split(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN\n"
            "  DELETE FROM a WHERE x = 1\n"
            "  DELETE FROM b WHERE y = 2\n"
            "  SELECT 1\n"
            "END"
        )
        result = _parse(sql, "tsql")
        dml = [s for s in result.node.body if type(s).__name__ == "EmbeddedDML"]
        assert len(dml) == 3

    def test_insert_select_stays_together(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN\n"
            "  INSERT INTO t (a, b)\n"
            "  SELECT a, b FROM src\n"
            "END"
        )
        result = _parse(sql, "tsql")
        dml = [s for s in result.node.body if type(s).__name__ == "EmbeddedDML"]
        assert len(dml) == 1
        assert "INSERT" in dml[0].sql and "SELECT" in dml[0].sql

    def test_insert_values_then_update_split(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS BEGIN\n"
            "  INSERT INTO t VALUES (1, 2)\n"
            "  UPDATE t SET x = 1\n"
            "END"
        )
        result = _parse(sql, "tsql")
        dml = [s for s in result.node.body if type(s).__name__ == "EmbeddedDML"]
        assert len(dml) == 2

    def test_update_from_stays_together(self) -> None:
        # T-SQL UPDATE ... FROM: the FROM continues the UPDATE.
        sql = (
            "CREATE PROCEDURE p AS BEGIN\n"
            "  UPDATE t SET x = s.y\n"
            "  FROM t JOIN s ON t.id = s.id\n"
            "END"
        )
        result = _parse(sql, "tsql")
        dml = [s for s in result.node.body if type(s).__name__ == "EmbeddedDML"]
        assert len(dml) == 1


class TestErrorHandling:
    def test_set_option_without_semicolon_keeps_body(self) -> None:
        # Regression: "SET NOCOUNT ON" without a trailing semicolon must not
        # consume the rest of the procedure body.
        sql = "CREATE PROCEDURE p AS BEGIN " "SET NOCOUNT ON " "DECLARE @x INT; " "END"
        result = _parse(sql, "tsql")
        declares = [s for s in result.node.body if isinstance(s, DeclareStatement)]
        assert len(declares) == 1

    def test_unparseable_returns_node(self) -> None:
        # Even garbage should not raise; it falls back to RawSQL.
        result = _parse("CREATE PROCEDURE", "tsql")
        assert result.node is not None

    def test_no_infinite_loop_on_malformed(self) -> None:
        # Regression: malformed input must terminate.
        sql = "CREATE PROCEDURE p AS BEGIN @ @ @ ; END"
        result = _parse(sql, "tsql")
        assert result.node is not None
