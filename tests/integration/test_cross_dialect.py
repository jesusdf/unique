"""Integration tests for cross-dialect SQL transpilation.

These tests verify end-to-end transpilation between all supported
dialect pairs, covering DQL, DML, DDL, functions, and edge cases.
"""

import re

import pytest

from unique.core.transpiler import Transpiler

# All 12 directional pairs (4 dialects × 3 targets each)
ALL_PAIRS = [
    (s, t)
    for s in ("tsql", "oracle", "postgresql", "mysql")
    for t in ("tsql", "oracle", "postgresql", "mysql")
    if s != t
]

TARGETS = ("tsql", "oracle", "postgresql", "mysql")


class TestCrossDialectSelect:
    """Basic SELECT statements across all dialect pairs."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_star(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        result = transpiler.transpile("SELECT * FROM users", source, target)
        assert "SELECT" in result.sql
        assert "users" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_where(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        result = transpiler.transpile(
            "SELECT id, name FROM users WHERE id = 1",
            source,
            target,
        )
        assert "WHERE" in result.sql
        assert "id" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_join(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT a.id, b.name FROM a INNER JOIN b ON a.id = b.a_id"
        result = transpiler.transpile(sql, source, target)
        assert "JOIN" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_order_by(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM users ORDER BY name ASC"
        result = transpiler.transpile(sql, source, target)
        assert "ORDER BY" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_group_by(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT dept, COUNT(*) FROM emp GROUP BY dept"
        result = transpiler.transpile(sql, source, target)
        assert "GROUP BY" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_distinct(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT DISTINCT name FROM users"
        result = transpiler.transpile(sql, source, target)
        assert "DISTINCT" in result.sql


class TestCrossDialectLimit:
    """LIMIT/TOP/ROWNUM conversions."""

    @pytest.mark.parametrize("target", TARGETS)
    def test_tsql_top_to_target(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT TOP 10 * FROM users",
            "tsql",
            target,
        )
        assert "users" in result.sql
        # Every target should produce valid output (no raw None)
        assert "None" not in result.sql or "/* UNIQUE:" in result.sql

    @pytest.mark.parametrize("target", TARGETS)
    def test_pg_limit_to_target(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users LIMIT 10",
            "postgresql",
            target,
        )
        assert "users" in result.sql

    @pytest.mark.parametrize("target", TARGETS)
    def test_pg_limit_offset_to_target(
        self, transpiler: Transpiler, target: str
    ) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users LIMIT 10 OFFSET 20",
            "postgresql",
            target,
        )
        assert "users" in result.sql


class TestCrossDialectDML:
    """INSERT, UPDATE, DELETE across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_insert(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "INSERT INTO t (a, b) VALUES (1, 'x')",
            source,
            target,
        )
        assert "INSERT INTO" in result.sql
        assert "(a, b)" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_update(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "UPDATE t SET a = 1 WHERE id = 5",
            source,
            target,
        )
        assert "UPDATE" in result.sql
        assert "SET" in result.sql
        assert "WHERE" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_delete(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "DELETE FROM t WHERE id = 1",
            source,
            target,
        )
        assert "DELETE" in result.sql
        assert "WHERE" in result.sql


class TestCrossDialectFunctions:
    """Function translation across dialects."""

    @pytest.mark.parametrize("target", ("postgresql", "mysql", "oracle"))
    def test_isnull_from_tsql(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT ISNULL(name, 'default') FROM t",
            "tsql",
            target,
        )
        sql_upper = result.sql.upper()
        assert "COALESCE" in sql_upper or "NVL" in sql_upper

    @pytest.mark.parametrize("target", ("tsql", "mysql", "postgresql"))
    def test_nvl_from_oracle(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT NVL(name, 'default') FROM t",
            "oracle",
            target,
        )
        sql_upper = result.sql.upper()
        assert "COALESCE" in sql_upper or "ISNULL" in sql_upper or "NVL" in sql_upper

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_count_star(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile("SELECT COUNT(*) FROM t", source, target)
        assert "COUNT" in result.sql.upper()


class TestCrossDialectCTE:
    """Common Table Expressions across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_simple_cte(self, transpiler: Transpiler, source: str, target: str) -> None:
        sql = "WITH cte AS (SELECT id FROM users) SELECT * FROM cte"
        result = transpiler.transpile(sql, source, target)
        assert "WITH" in result.sql.upper()
        assert "cte" in result.sql.lower()


class TestCrossDialectSubquery:
    """Subqueries across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_subquery_in_where(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM t WHERE id IN (SELECT id FROM t2)"
        result = transpiler.transpile(sql, source, target)
        assert "SELECT" in result.sql


class TestCrossDialectDDL:
    """CREATE TABLE across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_create_table(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "CREATE TABLE users (id INT, name VARCHAR(100))"
        result = transpiler.transpile(sql, source, target)
        assert "CREATE TABLE" in result.sql.upper()
        assert "users" in result.sql

    def test_identity_column_to_postgresql(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT IDENTITY(1,1) NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "SERIAL" in result.sql.upper()

    def test_identity_column_to_mysql(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT IDENTITY(1,1) NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "mysql")
        assert "AUTO_INCREMENT" in result.sql.upper()

    def test_identity_column_to_oracle(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT IDENTITY(1,1) NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "oracle")
        assert "GENERATED" in result.sql.upper()
        assert "IDENTITY" in result.sql.upper()

    def test_explicit_null_not_forced_not_null(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (name VARCHAR(50) NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        # An explicit NULL must not become NOT NULL.
        assert "NOT NULL" not in result.sql.upper()

    def test_column_default_preserved(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (status INT DEFAULT 0)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "DEFAULT 0" in result.sql
        # No stray UNIQUE comment wrapper around the default value.
        assert "/* UNIQUE" not in result.sql

    def test_rowguidcol_stripped(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (rowguid UNIQUEIDENTIFIER ROWGUIDCOL NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "ROWGUIDCOL" not in result.sql.upper()
        assert "CREATE TABLE" in result.sql.upper()

    def test_user_defined_domain_type_preserved(self, transpiler: Transpiler) -> None:
        # A T-SQL user-defined type [dbo].[Name] must keep its name, not
        # collapse to the literal USER-DEFINED.
        sql = "CREATE TABLE t ([col] [dbo].[Name] NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "USER-DEFINED" not in result.sql.upper()
        assert "Name" in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_table_level_primary_key(self, transpiler: Transpiler, target: str) -> None:
        sql = "CREATE TABLE t (id INT, CONSTRAINT pk PRIMARY KEY (id))"
        result = transpiler.transpile(sql, "tsql", target)
        assert "PRIMARY KEY" in result.sql.upper()

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_table_level_foreign_key(self, transpiler: Transpiler, target: str) -> None:
        sql = (
            "CREATE TABLE t (cust_id INT, "
            "CONSTRAINT fk FOREIGN KEY (cust_id) REFERENCES customers (id))"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "FOREIGN KEY" in result.sql.upper()
        assert "REFERENCES" in result.sql.upper()

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_foreign_key_reference_strips_dbo_schema(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # The T-SQL default schema "dbo" has no meaning on the other engines.
        # It is already stripped from the table being created; a FOREIGN KEY
        # that REFERENCES a dbo-qualified table must be stripped the same way,
        # otherwise the emitted DDL points at a non-existent schema/database.
        sql = (
            "CREATE TABLE dbo.t (cust_id INT, "
            "CONSTRAINT fk FOREIGN KEY (cust_id) "
            "REFERENCES dbo.customer (id))"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "REFERENCES" in result.sql.upper()
        # The reference must name the bare table, not the dbo-qualified one.
        assert "dbo.customer" not in result.sql
        assert "customer" in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_table_level_unique_and_check(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = (
            "CREATE TABLE t (id INT, age INT, "
            "CONSTRAINT uq UNIQUE (id), CONSTRAINT chk CHECK (age > 0))"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "UNIQUE" in result.sql.upper()
        assert "CHECK" in result.sql.upper()

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_create_view_strips_dbo_schema(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # The "dbo" default schema is meaningless on the other engines. Both the
        # view name and the tables referenced in its body must lose the prefix,
        # or the emitted DDL names a non-existent schema/database.
        sql = (
            "CREATE VIEW dbo.v_totals AS "
            "SELECT il.invoice_id, SUM(il.line_total) AS net "
            "FROM dbo.invoice_line il GROUP BY il.invoice_id"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "dbo." not in result.sql
        assert "v_totals" in result.sql
        assert "invoice_line" in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_create_sequence_strips_dbo_schema(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = "CREATE SEQUENCE dbo.s AS INT START WITH 1 INCREMENT BY 1"
        result = transpiler.transpile(sql, "tsql", target)
        # MySQL has no sequences; it may degrade, but must not emit dbo.s.
        assert "dbo.s" not in result.sql

    def test_mysql_binary_column_attribute_stripped(
        self, transpiler: Transpiler
    ) -> None:
        # MySQL "<char type> BINARY" column attribute is not portable and
        # breaks sqlglot; it must be stripped so the table parses.
        sql = "CREATE TABLE t (pwd VARCHAR(40) BINARY DEFAULT NULL)"
        result = transpiler.transpile(sql, "mysql", "postgresql")
        assert "CREATE TABLE" in result.sql.upper()
        assert "VARCHAR(40)" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    def test_mysql_binary_type_preserved(self, transpiler: Transpiler) -> None:
        # The BINARY(n) data type must NOT be stripped.
        sql = "CREATE TABLE t (data BINARY(16))"
        result = transpiler.transpile(sql, "mysql", "postgresql")
        assert "BINARY(16)" in result.sql.upper()

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
    def test_computed_column_preserved(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # A computed column (AS (expr) PERSISTED) must not silently collapse to
        # a plain VARCHAR. PostgreSQL, MySQL and Oracle all require an explicit
        # type before a generated column, which T-SQL computed columns don't
        # declare; real-engine validation confirmed MySQL rejects the typeless
        # form too. So every target gets a documented comment instead of
        # invalid SQL, placed outside the (valid) column list.
        sql = "CREATE TABLE t (a INT, b INT, total AS (a + b) PERSISTED)"
        result = transpiler.transpile(sql, "tsql", target)
        assert "total VARCHAR" not in result.sql.upper()
        assert "GENERATED ALWAYS AS" not in result.sql.upper()
        assert "UNIQUE:" in result.sql
        assert "total" in result.sql
        assert ",\n)" not in result.sql  # CREATE TABLE stays valid


class TestTSQLIdioms:
    """Regression tests for T-SQL output idioms (reported issues)."""

    def test_create_table_if_not_exists_uses_object_id_guard(
        self, transpiler: Transpiler
    ) -> None:
        # T-SQL has no CREATE TABLE IF NOT EXISTS; use an OBJECT_ID guard.
        sql = "CREATE TABLE IF NOT EXISTS t (id INT)"
        result = transpiler.transpile(sql, "postgresql", "tsql")
        assert "IF NOT EXISTS" not in result.sql.upper().replace("IS NULL", "")
        assert "OBJECT_ID" in result.sql
        assert "CREATE TABLE t" in result.sql

    def test_create_table_if_not_exists_inline_elsewhere(
        self, transpiler: Transpiler
    ) -> None:
        sql = "CREATE TABLE IF NOT EXISTS t (id INT)"
        for target in ("postgresql", "mysql"):
            result = transpiler.transpile(sql, "postgresql", target)
            assert "IF NOT EXISTS" in result.sql.upper()
            assert "OBJECT_ID" not in result.sql

    def test_tsql_statements_not_terminated_with_semicolon(
        self, transpiler: Transpiler
    ) -> None:
        # Idiomatic T-SQL relies on GO between batches, not ';' terminators,
        # and must never emit ';' immediately followed by GO.
        sql = "SELECT 1; SELECT 2;"
        result = transpiler.transpile(sql, "postgresql", "tsql")
        assert ";\nGO" not in result.sql
        assert "; GO" not in result.sql
        assert "GO" in result.sql  # batches still separated

    def test_no_go_after_comment_batches(self, transpiler: Transpiler) -> None:
        # Consecutive Oracle 'rem' comments must not each be followed by GO.
        sql = "rem Comment 1\nrem Comment 2\nrem Comment 3\nSELECT 1 FROM dual;"
        result = transpiler.transpile(sql, "oracle", "tsql")
        assert "GO" not in result.sql.split("SELECT")[0]
        # All three comments preserved.
        for n in ("Comment 1", "Comment 2", "Comment 3"):
            assert n in result.sql

    def test_other_dialects_keep_semicolon(self, transpiler: Transpiler) -> None:
        sql = "SELECT 1; SELECT 2;"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert result.sql.count(";") >= 2

    def test_no_go_after_comment_only_output(self, transpiler: Transpiler) -> None:
        # Unsupported statements we turn into '-- UNIQUE:' comments must not be
        # followed by GO either, even though their batch isn't a COMMENT batch.
        sql = "SET statement_timeout = 0;\nSET lock_timeout = 0;\nSELECT 1;"
        result = transpiler.transpile(sql, "postgresql", "tsql")
        assert not re.search(r"--[^\n]*\nGO", result.sql)


class TestPortableTypes:
    """Data-type names are mapped to the target dialect (found via live val)."""

    def test_nvarchar_to_postgres(self, transpiler: Transpiler) -> None:
        # PostgreSQL has no NVARCHAR/NCHAR.
        sql = "CREATE TABLE x (n NVARCHAR(50), m NCHAR(10))"
        out = transpiler.transpile(sql, "tsql", "postgresql").sql.upper()
        assert "NVARCHAR" not in out and "NCHAR" not in out
        assert "VARCHAR(50)" in out and "CHAR(10)" in out

    def test_uniqueidentifier_per_dialect(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE x (u UNIQUEIDENTIFIER)"
        assert "CHAR(36)" in transpiler.transpile(sql, "tsql", "mysql").sql
        assert "UUID" in transpiler.transpile(sql, "tsql", "postgresql").sql.upper()
        assert "RAW(16)" in transpiler.transpile(sql, "tsql", "oracle").sql.upper()

    def test_no_double_parens_on_mapped_length(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE x (u UNIQUEIDENTIFIER)"
        out = transpiler.transpile(sql, "tsql", "mysql").sql
        assert "(36)(" not in out

    def test_pg_types_to_tsql(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE x (flag BOOLEAN, data BYTEA)"
        out = transpiler.transpile(sql, "postgresql", "tsql").sql.upper()
        assert "BIT" in out and "VARBINARY" in out
        assert "BOOLEAN" not in out and "BYTEA" not in out


class TestPortableIndex:
    """CREATE INDEX output stays valid in the target (found via live val)."""

    def test_no_case_expression_in_tsql_index(self, transpiler: Transpiler) -> None:
        # sqlglot emulates PG NULLS ordering with a CASE expression that is
        # invalid in a T-SQL index column list; it must be collapsed.
        out = transpiler.transpile("CREATE INDEX ix ON t (a)", "postgresql", "tsql").sql
        assert "CASE" not in out.upper()
        assert "ON t(a)" in out.replace(" ", "").replace("ONt", "ON t")

    def test_multi_column_tsql_index(self, transpiler: Transpiler) -> None:
        out = transpiler.transpile(
            "CREATE INDEX ix ON t (a, b)", "postgresql", "tsql"
        ).sql
        assert "CASE" not in out.upper()

    def test_no_case_expression_for_mysql_or_oracle_index(
        self, transpiler: Transpiler
    ) -> None:
        # The CASE emulation is invalid for MySQL and Oracle too.
        for target in ("mysql", "oracle"):
            out = transpiler.transpile(
                "CREATE INDEX ix ON t (a)", "postgresql", target
            ).sql
            assert "CASE" not in out.upper(), target


class TestComputedColumnPortability:
    """Generated columns without a declared type (found via live val)."""

    def test_pg_and_oracle_get_documented_comment(self, transpiler: Transpiler) -> None:
        sql = "CREATE TABLE t (id INT, total AS (id * 2) PERSISTED)"
        for target in ("postgresql", "oracle"):
            out = transpiler.transpile(sql, "tsql", target).sql
            assert ",\n)" not in out  # valid CREATE TABLE, no dangling comma
            assert "UNIQUE:" in out
            assert "GENERATED ALWAYS AS" not in out.upper()

    def test_mysql_also_gets_comment(self, transpiler: Transpiler) -> None:
        # Real-engine validation showed MySQL rejects a typeless generated
        # column too, so it also gets a documented comment.
        sql = "CREATE TABLE t (id INT, total AS (id * 2) PERSISTED)"
        out = transpiler.transpile(sql, "tsql", "mysql").sql
        assert "UNIQUE:" in out
        assert "GENERATED ALWAYS AS" not in out.upper()

    def test_terminator_not_swallowed_by_trailing_comment(
        self, transpiler: Transpiler
    ) -> None:
        sql = "CREATE TABLE t (id INT, total AS (id * 2) PERSISTED)"
        out = transpiler.transpile(sql, "tsql", "postgresql").sql
        assert ");" in out
        assert not out.rstrip().endswith(";")  # ends with the comment


class TestDDLPassthrough:
    """ALTER TABLE / CREATE INDEX / CREATE SEQUENCE round-trip via sqlglot."""

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_alter_add_foreign_key(self, transpiler: Transpiler, target: str) -> None:
        sql = (
            "ALTER TABLE orders ADD CONSTRAINT fk FOREIGN KEY (cust_id) "
            "REFERENCES customers (id)"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "ALTER TABLE" in result.sql.upper()
        assert "FOREIGN KEY" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_alter_add_primary_key(self, transpiler: Transpiler, target: str) -> None:
        sql = "ALTER TABLE products ADD CONSTRAINT pk PRIMARY KEY (id)"
        result = transpiler.transpile(sql, "tsql", target)
        assert "PRIMARY KEY" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_alter_add_column(self, transpiler: Transpiler, target: str) -> None:
        sql = "ALTER TABLE t ADD COLUMN extra INT"
        result = transpiler.transpile(sql, "tsql", target)
        assert "ALTER TABLE" in result.sql.upper()
        assert "EXTRA" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_create_index(self, transpiler: Transpiler, target: str) -> None:
        sql = "CREATE INDEX idx ON customers (last_name, first_name)"
        result = transpiler.transpile(sql, "tsql", target)
        assert "CREATE INDEX" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql"])
    def test_create_sequence(self, transpiler: Transpiler, target: str) -> None:
        sql = "CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1"
        result = transpiler.transpile(sql, "tsql", target)
        assert "CREATE SEQUENCE" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    @pytest.mark.parametrize("keyword", ["CLUSTERED", "NONCLUSTERED"])
    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
    def test_clustered_index_keyword_dropped(
        self, transpiler: Transpiler, keyword: str, target: str
    ) -> None:
        sql = f"CREATE {keyword} INDEX idx ON t (a)"
        result = transpiler.transpile(sql, "tsql", target)
        assert "CREATE INDEX" in result.sql.upper()
        assert keyword not in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    def test_include_index_kept_for_postgresql(self, transpiler: Transpiler) -> None:
        sql = "CREATE INDEX idx ON t (a) INCLUDE (b, c)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "INCLUDE" in result.sql.upper()

    @pytest.mark.parametrize("target", ["mysql", "oracle"])
    def test_include_index_flagged_elsewhere(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = "CREATE INDEX idx ON t (a) INCLUDE (b, c)"
        result = transpiler.transpile(sql, "tsql", target)
        assert "CREATE INDEX" in result.sql.upper()
        assert "INCLUDE" in result.sql  # in the explanatory comment
        assert "does not support INCLUDE" in result.sql

    def test_filtered_index_kept_for_postgresql(self, transpiler: Transpiler) -> None:
        sql = "CREATE INDEX idx ON t (a) WHERE a > 0"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "WHERE" in result.sql.upper()

    @pytest.mark.parametrize("target", ["mysql", "oracle"])
    def test_filtered_index_flagged_elsewhere(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = "CREATE INDEX idx ON t (a) WHERE a > 0"
        result = transpiler.transpile(sql, "tsql", target)
        assert "does not support filtered indexes" in result.sql

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
    def test_index_physical_options_stripped(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # T-SQL physical storage options have no portable equivalent.
        sql = (
            "CREATE NONCLUSTERED INDEX ix ON s.customer (email ASC) "
            "WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF)"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "CREATE INDEX" in result.sql.upper()
        assert "PAD_INDEX" not in result.sql.upper()
        # The table reference (ON s.customer) must survive.
        assert "customer" in result.sql.lower()

    def test_create_sequence_mysql_documented(self, transpiler: Transpiler) -> None:
        # MySQL has no sequences; emit a documented comment, not invalid SQL.
        sql = "CREATE SEQUENCE seq START WITH 1"
        result = transpiler.transpile(sql, "tsql", "mysql")
        assert "AUTO_INCREMENT" in result.sql
        assert result.sql.lstrip().startswith("--")

    def test_use_statement_to_mysql(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile("USE [mydb]", "tsql", "mysql")
        assert "USE" in result.sql.upper()
        assert "mydb" in result.sql

    @pytest.mark.parametrize("target", ["postgresql", "oracle"])
    def test_use_statement_documented_where_unsupported(
        self, transpiler: Transpiler, target: str
    ) -> None:
        result = transpiler.transpile("USE [mydb]", "tsql", target)
        assert result.sql.lstrip().startswith("--")
        assert "mydb" in result.sql

    @pytest.mark.parametrize("target", ["oracle", "postgresql"])
    def test_merge_native(self, transpiler: Transpiler, target: str) -> None:
        sql = (
            "MERGE INTO target t USING source s ON (t.id = s.id) "
            "WHEN MATCHED THEN UPDATE SET t.val = s.val "
            "WHEN NOT MATCHED THEN INSERT (id, val) VALUES (s.id, s.val)"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert "MERGE" in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    def test_merge_to_mysql_documented(self, transpiler: Transpiler) -> None:
        sql = (
            "MERGE INTO target t USING source s ON (t.id = s.id) "
            "WHEN MATCHED THEN UPDATE SET t.val = s.val"
        )
        result = transpiler.transpile(sql, "tsql", "mysql")
        # MySQL has no MERGE: documented comment, not invalid SQL.
        assert result.sql.lstrip().startswith("--")
        assert "ON DUPLICATE KEY UPDATE" in result.sql

    def test_connect_by_kept_for_oracle(self, transpiler: Transpiler) -> None:
        sql = (
            "SELECT employee_id FROM employees "
            "START WITH manager_id IS NULL "
            "CONNECT BY PRIOR employee_id = manager_id"
        )
        result = transpiler.transpile(sql, "oracle", "oracle")
        assert "CONNECT BY" in result.sql.upper()

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "tsql"])
    def test_connect_by_documented_elsewhere(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = (
            "SELECT employee_id FROM employees "
            "START WITH manager_id IS NULL "
            "CONNECT BY PRIOR employee_id = manager_id"
        )
        result = transpiler.transpile(sql, "oracle", target)
        # The hierarchical clause must not be silently dropped.
        assert result.sql.lstrip().startswith("--")
        assert "RECURSIVE" in result.sql.upper()
        assert "CONNECT BY" in result.sql.upper()

    def test_select_into_table_to_mysql(self, transpiler: Transpiler) -> None:
        # T-SQL SELECT ... INTO <table> creates a table; MySQL uses
        # CREATE TABLE AS SELECT. The INTO must not be dropped.
        sql = "SELECT a, b INTO new_table FROM src WHERE id > 0"
        result = transpiler.transpile(sql, "tsql", "mysql")
        assert "CREATE TABLE" in result.sql.upper()
        assert "new_table" in result.sql

    @pytest.mark.parametrize("target", ["postgresql", "oracle"])
    def test_select_into_table_preserved(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = "SELECT a, b INTO new_table FROM src"
        result = transpiler.transpile(sql, "tsql", target)
        assert "new_table" in result.sql
        assert "INTO" in result.sql.upper()

    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_for_update_lock_preserved(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # A row lock must not be silently dropped.
        result = transpiler.transpile("SELECT a FROM t FOR UPDATE", "oracle", target)
        assert "FOR UPDATE" in result.sql.upper()

    def test_qualify_translated(self, transpiler: Transpiler) -> None:
        # QUALIFY has no PostgreSQL equivalent; sqlglot rewrites it as a
        # subquery + WHERE. It must not be dropped.
        sql = "SELECT a, ROW_NUMBER() OVER (ORDER BY a) rn FROM t QUALIFY rn = 1"
        result = transpiler.transpile(sql, "oracle", "postgresql")
        assert "ROW_NUMBER()" in result.sql.upper()
        assert "WHERE" in result.sql.upper()


class TestOutputReturning:
    """T-SQL OUTPUT <-> PostgreSQL/Oracle RETURNING; MySQL has neither."""

    @pytest.mark.parametrize("target", ["postgresql", "oracle"])
    def test_output_insert_to_returning(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = "INSERT INTO t (a) OUTPUT INSERTED.id VALUES (1)"
        result = transpiler.transpile(sql, "tsql", target)
        assert "RETURNING" in result.sql.upper()
        assert "id" in result.sql

    def test_output_delete_preserves_where(self, transpiler: Transpiler) -> None:
        # Critical: the OUTPUT clause must not cause the WHERE to be dropped
        # (which would delete the whole table).
        sql = "DELETE FROM t OUTPUT DELETED.id WHERE a = 1"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "WHERE" in result.sql.upper()
        assert "a = 1" in result.sql
        assert "RETURNING" in result.sql.upper()

    def test_output_update_preserves_where(self, transpiler: Transpiler) -> None:
        sql = "UPDATE t SET a = 1 OUTPUT INSERTED.id WHERE b = 2"
        result = transpiler.transpile(sql, "tsql", "oracle")
        assert "WHERE" in result.sql.upper()
        assert "b = 2" in result.sql
        assert "RETURNING" in result.sql.upper()

    def test_output_to_mysql_documented(self, transpiler: Transpiler) -> None:
        sql = "DELETE FROM t OUTPUT DELETED.id WHERE a = 1"
        result = transpiler.transpile(sql, "tsql", "mysql")
        # WHERE preserved, OUTPUT documented (MySQL has no OUTPUT/RETURNING).
        assert "WHERE" in result.sql.upper()
        assert "a = 1" in result.sql
        assert "no OUTPUT/RETURNING" in result.sql

    def test_returning_to_tsql_output(self, transpiler: Transpiler) -> None:
        sql = "INSERT INTO t (a) VALUES (1) RETURNING id"
        result = transpiler.transpile(sql, "postgresql", "tsql")
        assert "OUTPUT" in result.sql.upper()

    def test_returning_to_mysql_documented(self, transpiler: Transpiler) -> None:
        sql = "INSERT INTO t (a) VALUES (1) RETURNING id"
        result = transpiler.transpile(sql, "postgresql", "mysql")
        assert "no RETURNING" in result.sql


class TestConvertStyle:
    """T-SQL CONVERT(type, value, style) date-style codes."""

    @pytest.mark.parametrize(
        "target,fmt_fn",
        [
            ("postgresql", "TO_CHAR"),
            ("mysql", "DATE_FORMAT"),
            ("oracle", "TO_CHAR"),
        ],
    )
    def test_convert_style_120(
        self, transpiler: Transpiler, target: str, fmt_fn: str
    ) -> None:
        sql = "SELECT CONVERT(VARCHAR, d, 120) FROM t"
        result = transpiler.transpile(sql, "tsql", target)
        assert fmt_fn in result.sql.upper()
        # The value and style must be preserved (not truncated to CONVERT()).
        assert "CONVERT(VARCHAR)" not in result.sql.upper()
        assert "d" in result.sql

    def test_convert_style_103_uk_date(self, transpiler: Transpiler) -> None:
        sql = "SELECT CONVERT(VARCHAR(10), d, 103) FROM t"
        result = transpiler.transpile(sql, "tsql", "mysql")
        # Style 103 is dd/mm/yyyy.
        assert "%d/%m/%Y" in result.sql


class TestCrossDialectExpressions:
    """Complex expressions across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_case_expression(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT CASE WHEN id > 10 THEN 'big' ELSE 'small' END FROM t"
        result = transpiler.transpile(sql, source, target)
        assert "CASE" in result.sql.upper()
        assert "WHEN" in result.sql.upper()

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_between(self, transpiler: Transpiler, source: str, target: str) -> None:
        sql = "SELECT * FROM t WHERE id BETWEEN 1 AND 10"
        result = transpiler.transpile(sql, source, target)
        # Should produce valid output (BETWEEN or equivalent)
        assert "SELECT" in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_like(self, transpiler: Transpiler, source: str, target: str) -> None:
        sql = "SELECT * FROM t WHERE name LIKE '%test%'"
        result = transpiler.transpile(sql, source, target)
        assert "SELECT" in result.sql


class TestMultipleStatements:
    """Multi-statement scripts."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_two_statements(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM a; SELECT * FROM b;"
        result = transpiler.transpile(sql, source, target)
        # Both tables should appear in output
        assert "a" in result.sql.lower()
        assert "b" in result.sql.lower()
