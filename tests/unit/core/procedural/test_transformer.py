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

    def test_uniqueidentifier_to_mysql_char36(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        result = t._transform_data_type(DataType(name="UNIQUEIDENTIFIER"))
        assert result.name == "CHAR"
        assert result.params == (36,)

    def test_int_to_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        assert t._transform_data_type(DataType(name="INT")).name == "INT"

    def test_varchar_max_to_mysql_longtext(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        result = t._transform_data_type(DataType(name="VARCHAR", params=(-1,)))
        assert result.name == "LONGTEXT"

    def test_oracle_number_to_postgresql(self) -> None:
        t = ProceduralTransformer("oracle", "postgresql")
        assert t._transform_data_type(DataType(name="NUMBER")).name == "NUMERIC"

    def test_oracle_date_to_postgresql_timestamp(self) -> None:
        t = ProceduralTransformer("oracle", "postgresql")
        assert t._transform_data_type(DataType(name="DATE")).name == "TIMESTAMP"

    def test_oracle_varchar2_to_mysql(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        result = t._transform_data_type(DataType(name="VARCHAR2", params=(80,)))
        assert result.name == "VARCHAR"
        assert result.params == (80,)

    def test_oracle_number_to_mysql_decimal(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        assert t._transform_data_type(DataType(name="NUMBER")).name == "DECIMAL"


class TestMySQLVariableNaming:
    def test_tsql_to_mysql_strips_at_sign(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        assert t._transform_var_name("@userId") == "v_userid"

    def test_tsql_to_mysql_var_in_sql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        assert t._transform_var_in_sql("@a + @b") == "v_a + v_b"


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

    def test_isnull_to_coalesce_pg(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        result = t._transform_node(RawSQL(sql="ISNULL(a, b)", reason="x"))
        assert "COALESCE" in result.sql

    def test_isnull_to_ifnull_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        result = t._transform_node(RawSQL(sql="ISNULL(a, b)", reason="x"))
        assert "IFNULL" in result.sql

    def test_len_to_char_length_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        result = t._transform_node(RawSQL(sql="LEN(name)", reason="x"))
        assert "CHAR_LENGTH" in result.sql

    def test_nvl_to_coalesce_oracle_pg(self) -> None:
        t = ProceduralTransformer("oracle", "postgresql")
        result = t._transform_node(RawSQL(sql="NVL(x, y)", reason="x"))
        assert "COALESCE" in result.sql

    def test_substr_to_substring_oracle_mysql(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        result = t._transform_node(RawSQL(sql="SUBSTR(s, 1, 3)", reason="x"))
        assert "SUBSTRING" in result.sql

    def test_identity_mapping_not_doubled(self) -> None:
        # UPPER -> UPPER must not be mangled.
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_node(RawSQL(sql="UPPER(name)", reason="x"))
        assert result.sql == "UPPER(name)"


class TestNiladicDatetime:
    def test_sysdate_to_now_pg(self) -> None:
        t = ProceduralTransformer("oracle", "postgresql")
        result = t._transform_node(RawSQL(sql="v := SYSDATE", reason="x"))
        assert "NOW()" in result.sql

    def test_sysdate_to_getdate_tsql(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        result = t._transform_node(RawSQL(sql="v := SYSDATE", reason="x"))
        assert "GETDATE()" in result.sql

    def test_getdate_to_sysdate_no_parens(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_node(RawSQL(sql="x = GETDATE()", reason="x"))
        # Oracle SYSDATE takes no parentheses.
        assert "SYSDATE" in result.sql
        assert "SYSDATE()" not in result.sql

    def test_getdate_to_now_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        result = t._transform_node(RawSQL(sql="x = GETDATE()", reason="x"))
        assert "NOW()" in result.sql

    def test_now_to_getdate_pg_tsql(self) -> None:
        t = ProceduralTransformer("postgresql", "tsql")
        result = t._transform_node(RawSQL(sql="x := NOW()", reason="x"))
        assert "GETDATE()" in result.sql


class TestLastInsertedId:
    def test_scope_identity_to_postgresql(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_node(RawSQL(sql="SET @x = SCOPE_IDENTITY()", reason="x"))
        assert "LASTVAL()" in out.sql

    def test_scope_identity_to_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(RawSQL(sql="SET @x = SCOPE_IDENTITY()", reason="x"))
        assert "LAST_INSERT_ID()" in out.sql

    def test_scope_identity_to_oracle_documented(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="SET @x = SCOPE_IDENTITY()", reason="x"))
        assert "SCOPE_IDENTITY" not in out.sql.replace("/* SCOPE_IDENTITY", "").replace(
            "SCOPE_IDENTITY()", ""
        )
        assert "CURRVAL" in out.sql

    def test_identity_sysvar_to_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_system_var("@@IDENTITY")
        assert out == "LAST_INSERT_ID()"

    def test_identity_sysvar_to_postgresql(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_system_var("@@IDENTITY")
        assert out == "LASTVAL()"

    def test_rowcount_sysvar_to_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        assert t._transform_system_var("@@ROWCOUNT") == "ROW_COUNT()"


class TestStringAggregation:
    def test_string_agg_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="STRING_AGG(name, ',')", reason="x"))
        assert out.sql == "LISTAGG(name, ',')"

    def test_string_agg_to_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(RawSQL(sql="STRING_AGG(name, ',')", reason="x"))
        assert out.sql == "GROUP_CONCAT(name SEPARATOR ',')"

    def test_listagg_to_tsql(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        out = t._transform_node(RawSQL(sql="LISTAGG(name, ',')", reason="x"))
        assert out.sql == "STRING_AGG(name, ',')"

    def test_group_concat_to_oracle(self) -> None:
        t = ProceduralTransformer("mysql", "oracle")
        out = t._transform_node(
            RawSQL(sql="GROUP_CONCAT(name SEPARATOR ',')", reason="x")
        )
        assert out.sql == "LISTAGG(name, ',')"

    def test_comma_inside_string_literal_not_split(self) -> None:
        # Regression: a comma inside a quoted separator must not be treated
        # as an argument separator.
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="CHARINDEX(',', haystack)", reason="x"))
        assert out.sql == "INSTR(haystack, ',')"


class TestDecode:
    def test_decode_with_default(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        out = t._transform_node(
            RawSQL(sql="DECODE(s, 1, 'a', 2, 'b', 'c')", reason="x")
        )
        assert out.sql == ("CASE WHEN s = 1 THEN 'a' WHEN s = 2 THEN 'b' ELSE 'c' END")

    def test_decode_without_default(self) -> None:
        t = ProceduralTransformer("oracle", "postgresql")
        out = t._transform_node(RawSQL(sql="DECODE(x, 1, 'a', 2, 'b')", reason="x"))
        assert out.sql == "CASE WHEN x = 1 THEN 'a' WHEN x = 2 THEN 'b' END"

    def test_decode_single_pair(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        out = t._transform_node(RawSQL(sql="DECODE(x, 1, 'one')", reason="x"))
        assert out.sql == "CASE WHEN x = 1 THEN 'one' END"

    def test_decode_not_touched_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DECODE(x, 1, 'a')", reason="x"))
        # Not an Oracle source: leave DECODE alone.
        assert "DECODE" in out.sql


class TestSubstringPosition:
    def test_charindex_to_oracle_reorders(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="CHARINDEX(n, h)", reason="x"))
        assert out.sql == "INSTR(h, n)"

    def test_charindex_to_mysql_same_order(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(RawSQL(sql="CHARINDEX(n, h)", reason="x"))
        assert out.sql == "LOCATE(n, h)"

    def test_charindex_to_postgresql(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_node(RawSQL(sql="CHARINDEX(n, h)", reason="x"))
        assert out.sql == "STRPOS(h, n)"

    def test_instr_to_tsql_reorders(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        out = t._transform_node(RawSQL(sql="INSTR(h, n)", reason="x"))
        assert out.sql == "CHARINDEX(n, h)"

    def test_locate_to_oracle_reorders(self) -> None:
        t = ProceduralTransformer("mysql", "oracle")
        out = t._transform_node(RawSQL(sql="LOCATE(n, h)", reason="x"))
        assert out.sql == "INSTR(h, n)"

    def test_start_position_preserved(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="CHARINDEX(n, h, 5)", reason="x"))
        assert out.sql == "INSTR(h, n, 5)"


class TestDateAdd:
    def test_dateadd_day_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DATEADD(day, 5, d)", reason="x"))
        assert out.sql == "(d + 5)"

    def test_dateadd_month_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DATEADD(month, 3, d)", reason="x"))
        assert "ADD_MONTHS(d, 3)" in out.sql

    def test_dateadd_to_postgresql_interval(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_node(RawSQL(sql="DATEADD(day, 5, d)", reason="x"))
        assert "INTERVAL '5 DAY'" in out.sql

    def test_dateadd_to_mysql_date_add(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(RawSQL(sql="DATEADD(hour, 2, d)", reason="x"))
        assert "DATE_ADD(d, INTERVAL 2 HOUR)" in out.sql

    def test_dateadd_negative_value(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_node(RawSQL(sql="DATEADD(week, -1, d)", reason="x"))
        assert "-1 WEEK" in out.sql

    def test_dateadd_unknown_part_left_alone(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_node(RawSQL(sql="DATEADD(microsecond, 1, d)", reason="x"))
        # Unrecognized part: leave the original call for manual handling.
        assert "DATEADD" in out.sql


class TestDateDiff:
    def test_datediff_day_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DATEDIFF(day, a, b)", reason="x"))
        assert out.sql == "(b - a)"

    def test_datediff_month_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DATEDIFF(month, a, b)", reason="x"))
        assert "MONTHS_BETWEEN(b, a)" in out.sql

    def test_datediff_day_to_postgresql(self) -> None:
        t = ProceduralTransformer("tsql", "postgresql")
        out = t._transform_node(RawSQL(sql="DATEDIFF(day, a, b)", reason="x"))
        assert "::date" in out.sql

    def test_datediff_day_to_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(RawSQL(sql="DATEDIFF(day, a, b)", reason="x"))
        assert out.sql == "DATEDIFF(b, a)"

    def test_datediff_hour_to_mysql_timestampdiff(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(RawSQL(sql="DATEDIFF(hour, a, b)", reason="x"))
        assert "TIMESTAMPDIFF(HOUR, a, b)" in out.sql

    def test_nested_dateadd_datediff(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(
            RawSQL(sql="DATEADD(day, 1, DATEDIFF(day, x, y))", reason="x")
        )
        assert out.sql == "((y - x) + 1)"
