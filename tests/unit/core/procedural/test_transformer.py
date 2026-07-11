# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

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

    def test_varchar_max_to_oracle_bounded_varchar2(self) -> None:
        # VARCHAR(MAX) -> a bounded VARCHAR2, not CLOB: a CLOB cannot be a
        # comparison/join key in PL/SQL (ORA-22848), and these columns are used
        # as predicates in real procedures.
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_data_type(DataType(name="VARCHAR", params=(-1,)))
        assert result.name == "VARCHAR2(4000)"
        nresult = t._transform_data_type(DataType(name="NVARCHAR", params=(-1,)))
        assert nresult.name == "NVARCHAR2(2000)"

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

    def test_varbinary_max_maps_to_lob_types(self) -> None:
        # The plain name map would carry the MAX through: RAW(MAX) and
        # VARBINARY(MAX) are invalid on Oracle/MySQL, BYTEA takes no size.
        for target, expected in (
            ("oracle", "BLOB"),
            ("mysql", "LONGBLOB"),
            ("postgresql", "BYTEA"),
        ):
            t = ProceduralTransformer("tsql", target)
            result = t._transform_data_type(DataType(name="VARBINARY", params=(-1,)))
            assert result.name == expected, target
            assert result.params == (), target

    def test_varbinary_sized_keeps_size_where_valid(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        result = t._transform_data_type(DataType(name="VARBINARY", params=(200,)))
        assert result.name == "RAW"
        assert result.params == (200,)

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

    def test_try_catch_to_oracle_keeps_both_bodies(self) -> None:
        # The old transform rebuilt an ExceptionBlock from the CATCH alone and
        # silently dropped the TRY body; the node now survives whole and the
        # Oracle EMITTER renders BEGIN ... EXCEPTION WHEN OTHERS ... END;.
        t = ProceduralTransformer("tsql", "oracle")
        node = TryCatchBlock(
            try_body=(RawSQL(sql="INSERT INTO t (a) VALUES (1)", reason="x"),),
            catch_body=(RawSQL(sql="PRINT 1", reason="x"),),
        )
        result = t._transform_node(node)
        assert isinstance(result, TryCatchBlock)
        assert result.try_body and result.catch_body

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
    def test_sysdate_to_current_timestamp_pg(self) -> None:
        # CURRENT_TIMESTAMP is the shared mapping layer's spelling for
        # PG/MySQL (standard SQL, valid in both).
        t = ProceduralTransformer("oracle", "postgresql")
        result = t._transform_node(RawSQL(sql="v := SYSDATE", reason="x"))
        assert "CURRENT_TIMESTAMP" in result.sql

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

    def test_getdate_to_current_timestamp_mysql(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        result = t._transform_node(RawSQL(sql="x = GETDATE()", reason="x"))
        assert "CURRENT_TIMESTAMP" in result.sql

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

    def test_nvl2_to_case(self) -> None:
        t = ProceduralTransformer("oracle", "tsql")
        out = t._transform_node(RawSQL(sql="NVL2(p, p, 'x')", reason="x"))
        assert out.sql == "CASE WHEN p IS NOT NULL THEN p ELSE 'x' END"

    def test_nvl2_not_touched_to_oracle(self) -> None:
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="NVL2(p, a, b)", reason="x"))
        assert "NVL2" in out.sql


class TestOracleDateFormat:
    def test_to_char_to_mysql_date_format(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        out = t._transform_node(RawSQL(sql="TO_CHAR(d, 'YYYY-MM-DD')", reason="x"))
        assert out.sql == "DATE_FORMAT(d, '%Y-%m-%d')"

    def test_to_char_with_time(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        out = t._transform_node(
            RawSQL(sql="TO_CHAR(d, 'YYYY-MM-DD HH24:MI:SS')", reason="x")
        )
        assert out.sql == "DATE_FORMAT(d, '%Y-%m-%d %H:%i:%s')"

    def test_to_date_to_mysql_str_to_date(self) -> None:
        t = ProceduralTransformer("oracle", "mysql")
        out = t._transform_node(
            RawSQL(sql="TO_DATE('2020-01-01', 'YYYY-MM-DD')", reason="x")
        )
        assert out.sql == "STR_TO_DATE('2020-01-01', '%Y-%m-%d')"

    def test_to_char_numeric_untouched(self) -> None:
        # Single-arg TO_CHAR (numeric to string) has no format to map.
        t = ProceduralTransformer("oracle", "mysql")
        out = t._transform_node(RawSQL(sql="TO_CHAR(salary)", reason="x"))
        assert out.sql == "TO_CHAR(salary)"

    def test_to_char_to_postgresql_unchanged(self) -> None:
        # PostgreSQL uses the same format patterns as Oracle.
        t = ProceduralTransformer("oracle", "postgresql")
        out = t._transform_node(RawSQL(sql="TO_CHAR(d, 'YYYY-MM-DD')", reason="x"))
        assert out.sql == "TO_CHAR(d, 'YYYY-MM-DD')"

    def test_mysql_date_format_to_oracle(self) -> None:
        t = ProceduralTransformer("mysql", "oracle")
        out = t._transform_node(RawSQL(sql="DATE_FORMAT(d, '%Y-%m-%d')", reason="x"))
        assert out.sql == "TO_CHAR(d, 'YYYY-MM-DD')"

    def test_mysql_date_format_with_time(self) -> None:
        t = ProceduralTransformer("mysql", "postgresql")
        out = t._transform_node(RawSQL(sql="DATE_FORMAT(d, '%Y-%m-%d %T')", reason="x"))
        assert out.sql == "TO_CHAR(d, 'YYYY-MM-DD HH24:MI:SS')"

    def test_mysql_str_to_date_to_oracle(self) -> None:
        t = ProceduralTransformer("mysql", "oracle")
        out = t._transform_node(
            RawSQL(sql="STR_TO_DATE('2020-01-01', '%Y-%m-%d')", reason="x")
        )
        assert out.sql == "TO_DATE('2020-01-01', 'YYYY-MM-DD')"


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
        # T-SQL DATEDIFF counts day BOUNDARIES (23:00 -> 01:00 next day is
        # 1); Oracle's raw (b - a) is fractional for timestamps.
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DATEDIFF(day, a, b)", reason="x"))
        assert out.sql == "(TRUNC(CAST(b AS DATE)) - TRUNC(CAST(a AS DATE)))"

    def test_datediff_month_to_oracle(self) -> None:
        # Month-boundary count, not fractional MONTHS_BETWEEN.
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="DATEDIFF(month, a, b)", reason="x"))
        assert "MONTHS_BETWEEN" not in out.sql
        assert (
            "((EXTRACT(YEAR FROM b) * 12 + EXTRACT(MONTH FROM b)) - "
            "(EXTRACT(YEAR FROM a) * 12 + EXTRACT(MONTH FROM a)))" in out.sql
        )

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
        assert out.sql == ("((TRUNC(CAST(y AS DATE)) - TRUNC(CAST(x AS DATE))) + 1)")


class TestMySQLStringConcat:
    """T-SQL ``+`` string concatenation becomes MySQL ``CONCAT(...)``.

    ``+`` is ambiguous in T-SQL (arithmetic vs. string concat). A ``+`` chain
    is treated as concatenation only when one operand is a string literal; pure
    arithmetic is left untouched. ``N'...'`` prefixes are dropped.
    """

    def _mysql(self) -> ProceduralTransformer:
        return ProceduralTransformer("tsql", "mysql")

    def test_simple_concat(self) -> None:
        out = self._mysql()._transform_node(RawSQL(sql="@a + N' ' + @b", reason="x"))
        assert out.sql == "CONCAT(v_a, ' ', v_b)"

    def test_literal_prefix_dropped(self) -> None:
        out = self._mysql()._transform_node(RawSQL(sql="@a + N'@'", reason="x"))
        assert "N'" not in out.sql
        assert out.sql == "CONCAT(v_a, '@')"

    def test_nested_inside_function(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(
                sql="REPLACE(COALESCE(@c, @a + '@' + @b), '\"', '')",
                reason="x",
            )
        )
        assert "CONCAT(v_a, '@', v_b)" in out.sql
        assert "+ '@' +" not in out.sql

    def test_pure_arithmetic_untouched(self) -> None:
        out = self._mysql()._transform_node(RawSQL(sql="@a + @b", reason="x"))
        assert "CONCAT" not in out.sql
        assert "+" in out.sql

    def test_numeric_literal_untouched(self) -> None:
        out = self._mysql()._transform_node(RawSQL(sql="@a + 1", reason="x"))
        assert "CONCAT" not in out.sql

    def test_other_targets_keep_plus(self) -> None:
        # The conversion is MySQL-only; PostgreSQL keeps its own '||' handling
        # via sqlglot and must not be routed through CONCAT here.
        t = ProceduralTransformer("tsql", "oracle")
        out = t._transform_node(RawSQL(sql="@a + 'x'", reason="x"))
        assert "CONCAT(" not in out.sql


class TestMySQLCleanDML:
    """dbo. qualifiers and T-SQL table hints are removed for MySQL."""

    def _mysql(self) -> ProceduralTransformer:
        return ProceduralTransformer("tsql", "mysql")

    def test_dbo_stripped_from_table_in_select(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="SELECT x FROM dbo.tbl_5 AS c WHERE c.x = 1", reason="x")
        )
        assert "dbo." not in out.sql
        assert "FROM tbl_5" in out.sql

    def test_dbo_stripped_from_update(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="UPDATE dbo.tbl_6 SET a = 1 WHERE b = 2", reason="x")
        )
        assert "dbo." not in out.sql

    def test_nolock_hint_removed(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="SELECT x FROM dbo.t WITH (NOLOCK) WHERE y = 1", reason="x")
        )
        assert "NOLOCK" not in out.sql
        assert "dbo." not in out.sql

    def test_dbo_stripped_from_function_call(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="SELECT dbo.func1()", reason="x")
        )
        assert "dbo." not in out.sql
        # Identifier case is preserved (not upper-cased by a sqlglot round-trip).
        assert "func1" in out.sql

    def test_clean_dml_is_noop_without_dbo_or_hint(self) -> None:
        # A fragment with no dbo/hint must be returned untouched (no sqlglot
        # reflow, e.g. INTERVAL literals must not be requoted).
        out = self._mysql()._transform_node(
            RawSQL(sql="DATE_ADD(d, INTERVAL 2 HOUR)", reason="x")
        )
        assert out.sql == "DATE_ADD(d, INTERVAL 2 HOUR)"


class TestMySQLTypeAndFuncMapping:
    """Non-portable T-SQL scalar types/functions map to MySQL equivalents."""

    def _mysql(self) -> ProceduralTransformer:
        return ProceduralTransformer("tsql", "mysql")

    def test_convert_to_cast(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="CONVERT(VARCHAR(20), @col_17)", reason="x")
        )
        assert "CONVERT" not in out.sql
        assert "CAST(v_col_17 AS CHAR(20))" in out.sql

    def test_convert_with_date_style(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="CONVERT(DATETIME, '2020-01-01 00:00:00', 120)", reason="x")
        )
        assert "STR_TO_DATE(" in out.sql
        assert "CONVERT" not in out.sql

    def test_hashbytes_to_sha2(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="HASHBYTES('SHA2_256', @payload)", reason="x")
        )
        assert "HASHBYTES" not in out.sql
        assert "SHA2(" in out.sql

    def test_cast_max_collapsed_to_char(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="CAST(NULL AS NVARCHAR(MAX))", reason="x")
        )
        assert "(MAX)" not in out.sql.upper()
        assert "CAST(NULL AS CHAR)" in out.sql

    def test_sized_cast_preserved(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="CAST(@x AS VARCHAR(50))", reason="x")
        )
        # A concrete length must survive (only MAX is collapsed).
        assert "50" in out.sql


class TestMySQLSqlVariantType:
    def test_sql_variant_param_becomes_longtext(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE PROCEDURE dbo.p\n"
            "    @v SQL_VARIANT = NULL\n"
            "AS\n"
            "BEGIN\n"
            "    SET @v = NULL\n"
            "END"
        )
        out = Transpiler().transpile(src, source="tsql", target="mysql").sql
        # SQL_VARIANT maps to the LONGTEXT carrier, with the original preserved
        # in a /* UNIQUE */ comment for documentation and round-tripping.
        assert "LONGTEXT" in out
        assert "/* UNIQUE: SQL_VARIANT */" in out


class TestMySQLHashAndStringVarConcat:
    """HASHBYTES-in-CONVERT unwrapping and string-variable concatenation."""

    def test_convert_hashbytes_unwraps_to_sha2(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        out = t._transform_node(
            RawSQL(
                sql="CONVERT(nvarchar(max), HASHBYTES('SHA2_256', x), 2)",
                reason="x",
            )
        )
        # The spurious DATE_FORMAT/CONVERT wrapper is dropped; SHA2 already
        # returns the hex string.
        assert "DATE_FORMAT" not in out.sql
        assert out.sql.strip() == "SHA2(x, 256)"

    def test_plus_between_string_vars_becomes_concat(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        # Two declared string variables: '+' must be concatenation even with no
        # string literal present.
        t._string_vars = {"v_a", "v_b"}
        out = t._transform_node(RawSQL(sql="v_a + v_b", reason="x"))
        assert out.sql == "CONCAT(v_a, v_b)"

    def test_plus_between_non_string_vars_stays_arithmetic(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        # No string vars registered -> '+' is arithmetic, left untouched.
        out = t._transform_node(RawSQL(sql="v_a + v_b", reason="x"))
        assert "CONCAT" not in out.sql
        assert "+" in out.sql

    def test_string_var_registered_from_function_param(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE FUNCTION dbo.f(@payload nvarchar(max), @secret nvarchar(400))\n"
            "RETURNS nvarchar(max)\n"
            "AS\n"
            "BEGIN\n"
            "    RETURN CONVERT(nvarchar(max), "
            "HASHBYTES('SHA2_256', @payload + @secret), 2)\n"
            "END"
        )
        out = Transpiler().transpile(src, source="tsql", target="mysql").sql
        assert "SHA2(CONCAT(v_payload, v_secret), 256)" in out
        assert "DATE_FORMAT" not in out


class TestMySQLStringSplit:
    """T-SQL STRING_SPLIT maps to a MySQL JSON_TABLE expansion."""

    def _mysql(self) -> ProceduralTransformer:
        return ProceduralTransformer("tsql", "mysql")

    def test_string_split_becomes_json_table(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="SELECT value FROM STRING_SPLIT(v_s, v_delim)", reason="x")
        )
        assert "STRING_SPLIT" not in out.sql
        assert "JSON_TABLE(" in out.sql
        # The 'value' column must be preserved so callers keep working.
        assert "value" in out.sql

    def test_string_split_preserves_value_column_usage(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(
                sql="SELECT LTRIM(RTRIM(value)) AS item "
                "FROM STRING_SPLIT(v_s, v_delim)",
                reason="x",
            )
        )
        assert "JSON_TABLE(" in out.sql
        assert "value" in out.sql
        assert "STRING_SPLIT" not in out.sql

    def test_no_string_split_left_untouched(self) -> None:
        out = self._mysql()._transform_node(
            RawSQL(sql="SELECT a FROM t WHERE b = 1", reason="x")
        )
        assert "JSON_TABLE" not in out.sql


class TestUniqueTypePreservationComment:
    """Unknown/non-portable types preserve the original in a /* UNIQUE */ tag."""

    def test_unresolved_pct_type_oracle_to_tsql(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE PROCEDURE p (\n"
            "    V_SALA IN H_SALASTELDET.SALA%TYPE DEFAULT NULL\n"
            ") AS\nBEGIN\n    NULL;\nEND;"
        )
        out = Transpiler().transpile(src, source="oracle", target="tsql").sql
        assert "SQL_VARIANT /* UNIQUE: H_SALASTELDET.SALA%TYPE */" in out

    def test_unresolved_pct_type_oracle_to_mysql(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE PROCEDURE p (\n"
            "    V_SALA IN H_SALASTELDET.SALA%TYPE DEFAULT NULL\n"
            ") AS\nBEGIN\n    NULL;\nEND;"
        )
        out = Transpiler().transpile(src, source="oracle", target="mysql").sql
        assert "LONGTEXT /* UNIQUE: H_SALASTELDET.SALA%TYPE */" in out

    def test_sql_variant_preserves_original(self) -> None:
        t = ProceduralTransformer("tsql", "mysql")
        dt = t._transform_data_type(DataType(name="SQL_VARIANT"))
        assert dt.name == "LONGTEXT"
        assert dt.origin_comment == "SQL_VARIANT"

    def test_common_type_has_no_comment(self) -> None:
        # A type with a faithful equivalent must NOT get a UNIQUE comment.
        t = ProceduralTransformer("tsql", "mysql")
        dt = t._transform_data_type(DataType(name="INT"))
        assert dt.origin_comment is None


class TestDroppedSetOptionPreserved:
    """A dropped dialect-specific SET option is documented and never leaves an
    empty block."""

    def _out(self, target: str) -> str:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE PROCEDURE dbo.p\n"
            "    @c NVARCHAR(50) = NULL\n"
            "AS\nBEGIN\n"
            "    IF (@c IS NOT NULL)\n"
            "        SET NOCOUNT ON\n"
            "    SELECT 1\n"
            "END"
        )
        return Transpiler().transpile(src, "tsql", target).sql

    def test_mysql_documents_and_fills_empty_if(self) -> None:
        out = self._out("mysql")
        # The original is preserved as a comment...
        assert "/* UNIQUE: SET NOCOUNT ON" in out
        # ...and the otherwise-empty IF body gets a MySQL no-op.
        assert "DO 0;" in out
        # No empty IF remains.
        assert "THEN\n    END IF" not in out.replace("        ", "    ")

    def test_oracle_uses_null_noop(self) -> None:
        out = self._out("oracle")
        assert "/* UNIQUE: SET NOCOUNT ON" in out
        assert "NULL;" in out

    def test_non_empty_if_unaffected(self) -> None:
        from unique.core.transpiler import Transpiler

        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    IF (1 = 1)\n        SELECT 1\n"
            "END"
        )
        out = Transpiler().transpile(src, "tsql", "mysql").sql
        # A real body must NOT get a spurious no-op.
        assert "DO 0;" not in out
