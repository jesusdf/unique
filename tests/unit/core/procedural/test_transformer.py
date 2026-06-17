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

"""Tests for the procedural transformer."""

from __future__ import annotations

from unique.core.ast_nodes import (
    AssignmentStatement,
    CreateProcedureStatement,
    DataType,
    DeclareStatement,
    RawSQL,
    SetVariableStatement,
    TryCatchBlock,
)
from unique.core.procedural.transformer import ProceduralTransformer


class TestVariableNaming:
    def test_tsql_to_oracle_uppercase_prefix(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        assert t._transform_var_name("@userId") == "V_USERID"

    def test_tsql_to_postgresql_lowercase_prefix(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        assert t._transform_var_name("@userId") == "v_userid"

    def test_oracle_to_tsql_adds_at_sign(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        result = t._transform_var_name("V_USERID")
        assert result.startswith("@")

    def test_same_dialect_unchanged(self) -> None:
        t = ProceduralTransformer("tsql", "tsql")
        assert t._transform_var_name("@x") == "@x"


class TestSystemVariables:
    def test_rowcount_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        assert t._transform_system_var("@@ROWCOUNT") == "SQL%ROWCOUNT"

    def test_rowcount_to_postgresql(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        assert t._transform_system_var("@@ROWCOUNT") == "ROW_COUNT"

    def test_unknown_system_var_commented(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_system_var("@@SERVERNAME")
        assert "@@SERVERNAME" in result


class TestDataTypeMapping:
    def test_int_to_oracle_number(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_data_type(DataType(name="INT"))
        assert result.name == "NUMBER"

    def test_nvarchar_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_data_type(DataType(name="NVARCHAR", params=(50,)))
        assert result.name == "NVARCHAR2"
        assert result.params == (50,)

    def test_varchar_max_to_oracle_clob(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_data_type(DataType(name="VARCHAR", params=(-1,)))
        assert result.name == "CLOB"

    def test_varchar_max_to_postgresql_text(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        result = t._transform_data_type(DataType(name="VARCHAR", params=(-1,)))
        assert result.name == "TEXT"

    def test_oracle_number_to_tsql(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        result = t._transform_data_type(DataType(name="NUMBER"))
        assert result.name == "DECIMAL"

    def test_oracle_varchar2_to_tsql(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        result = t._transform_data_type(DataType(name="VARCHAR2", params=(100,)))
        assert result.name == "NVARCHAR"

    def test_type_reference_to_tsql_becomes_sql_variant(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        result = t._transform_data_type(DataType(name="emp.sal%TYPE"))
        assert result.name == "SQL_VARIANT"
        assert len(t.warnings) >= 1

    def test_uniqueidentifier_to_postgresql_uuid(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        result = t._transform_data_type(DataType(name="UNIQUEIDENTIFIER"))
        assert result.name == "UUID"


class TestStatementTransforms:
    def test_set_variable_to_oracle_assignment(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        node = SetVariableStatement(name="@x", value=RawSQL(sql="1", reason="x"))
        result = t._transform_node(node)
        assert isinstance(result, AssignmentStatement)
        assert result.target == "V_X"

    def test_oracle_assignment_to_tsql_set(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        node = AssignmentStatement(target="V_X", value=RawSQL(sql="1", reason="x"))
        result = t._transform_node(node)
        assert isinstance(result, SetVariableStatement)

    def test_try_catch_to_oracle_exception(self) -> None:
        from unique.core.ast_nodes import ExceptionBlock

        t = ProceduralTransformer("tsql", "oracle")
        node = TryCatchBlock(
            try_body=(),
            catch_body=(RawSQL(sql="PRINT 1", reason="x"),),
        )
        result = t._transform_node(node)
        assert isinstance(result, ExceptionBlock)

    def test_declare_transforms_name_and_type(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        node = DeclareStatement(name="@cnt", data_type=DataType(name="INT"))
        result = t._transform_node(node)
        assert isinstance(result, DeclareStatement)
        assert result.name == "V_CNT"
        assert result.data_type.name == "NUMBER"

    def test_procedure_gets_or_replace_for_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        node = CreateProcedureStatement(name="p", parameters=(), body=())
        result = t._transform_node(node)
        assert isinstance(result, CreateProcedureStatement)
        assert result.or_replace is True


class TestFunctionMapping:
    def test_getdate_to_sysdate_in_raw_sql(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        node = RawSQL(sql="GETDATE()", reason="x")
        result = t._transform_node(node)
        assert "SYSDATE" in result.sql

    def test_isnull_to_nvl(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        node = RawSQL(sql="ISNULL(a, b)", reason="x")
        result = t._transform_node(node)
        assert "NVL" in result.sql
