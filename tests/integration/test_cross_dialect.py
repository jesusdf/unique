"""Integration tests for cross-dialect SQL transpilation.

These tests verify end-to-end transpilation between all supported
dialect pairs, covering DQL, DML, DDL, functions, and edge cases.
"""

import re

import pytest

from tests.helpers.validity import assert_translated, executable_lines
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
        assert_translated(result.sql, target, present=("SELECT", "users"))

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_where(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        result = transpiler.transpile(
            "SELECT id, name FROM users WHERE id = 1",
            source,
            target,
        )
        assert_translated(result.sql, target, present=("WHERE", "id"))

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_join(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT a.id, b.name FROM a INNER JOIN b ON a.id = b.a_id"
        result = transpiler.transpile(sql, source, target)
        assert_translated(result.sql, target, present=("JOIN b", "ON a.id = b.a_id"))

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_join_with_alias_not_duplicated(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        # A joined table with an alias must not emit the alias twice
        # ("t2 b b"): _emit_table_ref already renders the alias.
        sql = "SELECT a.x FROM t1 a INNER JOIN t2 b ON a.id = b.id"
        result = transpiler.transpile(sql, source, target)
        assert "b b" not in result.sql

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_order_by(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT * FROM users ORDER BY name ASC"
        result = transpiler.transpile(sql, source, target)
        assert_translated(result.sql, target, present=("ORDER BY name",))

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_group_by(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT dept, COUNT(*) FROM emp GROUP BY dept"
        result = transpiler.transpile(sql, source, target)
        assert_translated(result.sql, target, present=("COUNT(*)", "GROUP BY dept"))

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_select_distinct(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        sql = "SELECT DISTINCT name FROM users"
        result = transpiler.transpile(sql, source, target)
        assert_translated(result.sql, target, present=("DISTINCT name",))


class TestCrossDialectLimit:
    """LIMIT/TOP/ROWNUM conversions."""

    @pytest.mark.parametrize("target", TARGETS)
    def test_tsql_top_to_target(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT TOP 10 * FROM users",
            "tsql",
            target,
        )
        idiom = {
            "tsql": "TOP 10",
            "postgresql": "LIMIT 10",
            "mysql": "LIMIT 10",
            "oracle": "FETCH FIRST 10 ROWS ONLY",
        }[target]
        absent = () if target == "tsql" else ("TOP",)
        assert_translated(result.sql, target, present=(idiom,), absent=absent)

    @pytest.mark.parametrize("target", TARGETS)
    def test_pg_limit_to_target(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users LIMIT 10",
            "postgresql",
            target,
        )
        idiom = {
            "tsql": "TOP 10",
            "postgresql": "LIMIT 10",
            "mysql": "LIMIT 10",
            "oracle": "FETCH FIRST 10 ROWS ONLY",
        }[target]
        absent = () if target in ("postgresql", "mysql") else ("LIMIT",)
        assert_translated(result.sql, target, present=(idiom,), absent=absent)

    @pytest.mark.parametrize("target", TARGETS)
    def test_pg_limit_offset_to_target(
        self, transpiler: Transpiler, target: str
    ) -> None:
        result = transpiler.transpile(
            "SELECT * FROM users LIMIT 10 OFFSET 20",
            "postgresql",
            target,
        )
        idioms = {
            "tsql": ("OFFSET 20 ROWS", "FETCH NEXT 10 ROWS ONLY"),
            "postgresql": ("LIMIT 10", "OFFSET 20"),
            "mysql": ("LIMIT 10", "OFFSET 20"),
            "oracle": ("OFFSET 20 ROWS", "FETCH FIRST 10 ROWS ONLY"),
        }[target]
        assert_translated(result.sql, target, present=idioms)


class TestCrossDialectDML:
    """INSERT, UPDATE, DELETE across dialects."""

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_insert(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "INSERT INTO t (a, b) VALUES (1, 'x')",
            source,
            target,
        )
        assert_translated(
            result.sql, target, present=("INSERT INTO", "(a, b)", "(1, 'x')")
        )

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
    def test_where_and_or_not_emitted_as_function(
        self, transpiler: Transpiler, source: str, target: str
    ) -> None:
        # A top-level AND/OR in a WHERE must stay an infix operator, not become
        # a function call "AND(a, b)" (exp.And is also an exp.Func, so the
        # function branch must not capture it).
        result = transpiler.transpile(
            "UPDATE t SET a = 1 WHERE x = 1 AND y = 2",
            source,
            target,
        )
        assert "AND(" not in result.sql.upper().replace(" ", "")
        assert "AND" in result.sql.upper()

    @pytest.mark.parametrize("source,target", ALL_PAIRS)
    def test_delete(self, transpiler: Transpiler, source: str, target: str) -> None:
        result = transpiler.transpile(
            "DELETE FROM t WHERE id = 1",
            source,
            target,
        )
        assert "DELETE" in result.sql
        assert "WHERE" in result.sql

    # ---- UPDATE ... FROM ... JOIN (cross-table update) ----
    # T-SQL expresses a cross-table update as UPDATE t SET t.c = s.c FROM t
    # JOIN s ON ...; the source table and join condition MUST survive, in each
    # engine's idiomatic form. Losing them (emitting a bare "UPDATE t SET
    # c = s.c") is a correctness bug: it references an undefined alias and
    # updates every row.

    _UPDATE_FROM_JOIN = (
        "UPDATE il SET il.unit_price = p.unit_price "
        "FROM invoice_line il "
        "INNER JOIN product p ON p.id = il.product_id"
    )

    def test_update_from_join_to_postgresql_uses_from(
        self, transpiler: Transpiler
    ) -> None:
        result = transpiler.transpile(self._UPDATE_FROM_JOIN, "tsql", "postgresql")
        sql = result.sql.upper()
        # PostgreSQL: UPDATE invoice_line SET unit_price = p.unit_price
        #             FROM product p WHERE p.id = il.product_id
        assert "FROM PRODUCT" in sql
        assert "P.UNIT_PRICE" in sql
        # The join predicate must be carried (as a WHERE in PostgreSQL).
        assert "P.ID" in sql and "PRODUCT_ID" in sql

    def test_update_from_join_to_mysql_keeps_join(self, transpiler: Transpiler) -> None:
        result = transpiler.transpile(self._UPDATE_FROM_JOIN, "tsql", "mysql")
        sql = result.sql.upper()
        # MySQL: UPDATE invoice_line JOIN product p ON ... SET ...
        assert "JOIN PRODUCT" in sql
        assert "P.UNIT_PRICE" in sql
        assert "ON " in sql and "PRODUCT_ID" in sql

    def test_update_from_join_to_oracle_no_from_keyword(
        self, transpiler: Transpiler
    ) -> None:
        result = transpiler.transpile(self._UPDATE_FROM_JOIN, "tsql", "oracle")
        sql = result.sql.upper()
        # Oracle has no UPDATE ... FROM; the source must still be referenced
        # (correlated subquery or MERGE), so the product table and its key
        # column have to appear, and there must be no bare "FROM PRODUCT"
        # dangling after SET.
        assert "PRODUCT" in sql
        assert "PRODUCT_ID" in sql
        # The assigned value must not reference an alias that no longer exists
        # as a bare "SET ... = P.UNIT_PRICE" with nothing defining P.
        assert "/* UNIQUE" not in result.sql or "PRODUCT" in result.sql


class TestCrossDialectFunctions:
    """Function translation across dialects."""

    @pytest.mark.parametrize("target", ("postgresql", "mysql", "oracle"))
    def test_user_function_call_strips_dbo_schema(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # A call to a dbo-qualified user function (dbo.fn_tax(...)) must drop the
        # dbo. schema on the other engines, like any other object reference.
        result = transpiler.transpile(
            "SELECT dbo.fn_tax(net) FROM t",
            "tsql",
            target,
        )
        assert "dbo.fn_tax" not in result.sql
        assert "fn_tax" in result.sql.lower()

    @pytest.mark.parametrize("target", ("postgresql", "mysql", "oracle"))
    def test_isnull_from_tsql(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT ISNULL(name, 'default') FROM t",
            "tsql",
            target,
        )
        assert_translated(
            result.sql,
            target,
            present=("COALESCE(name, 'default')",),
            absent=("ISNULL",),
        )

    @pytest.mark.parametrize("target", ("tsql", "mysql", "postgresql"))
    def test_nvl_from_oracle(self, transpiler: Transpiler, target: str) -> None:
        result = transpiler.transpile(
            "SELECT NVL(name, 'default') FROM t",
            "oracle",
            target,
        )
        assert_translated(
            result.sql,
            target,
            present=("COALESCE(name, 'default')",),
            absent=("NVL",),
        )

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

    @pytest.mark.parametrize("target", ["tsql", "postgresql", "mysql"])
    def test_oracle_organization_index_table_converted(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # ORGANIZATION INDEX/HEAP is an Oracle physical-storage clause that
        # sqlglot cannot parse, degrading the whole CREATE TABLE (columns and
        # constraints included) to a commented passthrough. The clause carries
        # no logical schema, so it must be stripped (with a documented
        # carrier + warning) and the table converted normally (found on the
        # HR sample schema's countries table).
        sql = (
            "CREATE TABLE countries\n"
            "    ( country_id      CHAR(2)\n"
            "       CONSTRAINT  country_id_nn NOT NULL\n"
            "    , country_name    VARCHAR2(60)\n"
            "    , CONSTRAINT     country_c_id_pk\n"
            "        PRIMARY KEY (country_id)\n"
            "    )\n"
            "    ORGANIZATION INDEX;"
        )
        result = transpiler.transpile(sql, "oracle", target)
        assert_translated(result.sql, target, absent=("ORGANIZATION",))
        # The table must be *converted*, not degraded to a commented
        # passthrough: CREATE TABLE and the PK must be executable lines.
        body = executable_lines(result.sql)
        assert "CREATE TABLE" in body.upper(), result.sql
        assert "PRIMARY KEY" in body.upper(), result.sql
        assert "UNIQUE:" in result.sql, result.sql
        assert result.warnings, "dropped physical clause must be signalled"

    @pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
    def test_table_level_primary_key_clustered_with_options(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # The full SSMS-generated constraint form (AdventureWorksLT): the
        # CLUSTERED hint, the WITH (...) storage options and the ON [filegroup]
        # clause are T-SQL physical hints with no meaning elsewhere. sqlglot's
        # non-T-SQL writers render them as bogus comma-separated column-list
        # items ("PRIMARY KEY, CLUSTERED (...), WITH (...), ON ..."), so they
        # must be stripped before re-transpiling the fragment.
        sql = (
            "CREATE TABLE [SalesLT].[PD](\n"
            "  [PDID] [int] NOT NULL,\n"
            "  [Desc] [nvarchar](400) NOT NULL,\n"
            "  CONSTRAINT [PK_PD] PRIMARY KEY CLUSTERED ([PDID] ASC)\n"
            "  WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, "
            "IGNORE_DUP_KEY = OFF) ON [PRIMARY]\n"
            ") ON [PRIMARY]"
        )
        result = transpiler.transpile(sql, "tsql", target)
        assert_translated(
            result.sql,
            target,
            present=("PRIMARY KEY",),
            absent=("CLUSTERED", "PAD_INDEX"),
        )

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
        # Binary data must survive, mapped to the target's binary type — not left
        # as ``BINARY(16)`` (PostgreSQL has no BINARY type; it uses BYTEA, which
        # takes no length).
        sql = "CREATE TABLE t (data BINARY(16))"
        result = transpiler.transpile(sql, "mysql", "postgresql")
        assert "BYTEA" in result.sql.upper()
        assert "BINARY(16)" not in result.sql.upper()

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
        # The physical hint is stripped from the executable index but preserved
        # in a restorable /* UNIQUE: … */ note (no silent loss).
        executable = result.sql.split("/* UNIQUE:")[0]
        assert keyword not in executable.upper()
        assert "/* UNIQUE:" in result.sql
        assert keyword in result.sql.upper()
        assert "-- UNIQUE: Unhandled" not in result.sql

    @pytest.mark.parametrize("keyword", ["CLUSTERED", "NONCLUSTERED"])
    @pytest.mark.parametrize("target", ["postgresql", "oracle", "mysql"])
    def test_physical_index_clause_round_trips_to_tsql(
        self, transpiler: Transpiler, keyword: str, target: str
    ) -> None:
        # A physical hint stripped on the forward pass is restored on the way
        # back to T-SQL from the /* UNIQUE: … */ note (like %TYPE).
        original = f"CREATE {keyword} INDEX ix ON t (a)"
        forward = transpiler.transpile(original, "tsql", target).sql
        back = transpiler.transpile(forward, target, "tsql").sql
        assert f"CREATE {keyword} INDEX" in back.upper()
        assert "/* UNIQUE:" not in back  # note consumed by the restore

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
        # Storage options are stripped from the executable index but preserved
        # in a restorable /* UNIQUE: … */ note (no silent loss).
        executable = result.sql.split("/* UNIQUE:")[0]
        assert "PAD_INDEX" not in executable.upper()
        assert "PAD_INDEX" in result.sql.upper()
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


class TestMySQLSourceDDL:
    """MySQL-specific column types must map to valid target types.

    Found on the sakila sample schema: unsigned integer types leaked as
    sqlglot's internal names (USMALLINT/UTINYINT/UMEDIUMINT), YEAR and
    MySQL TIMESTAMP (parsed as TIMESTAMPTZ) reached engines that reject
    them, ENUM lost its value list silently, and a named inline UNIQUE KEY
    re-emitted as "UNIQUE name (col)" which only MySQL accepts.
    """

    TABLE = (
        "CREATE TABLE film (\n"
        "  film_id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,\n"
        "  votes MEDIUMINT UNSIGNED NOT NULL,\n"
        "  language_id TINYINT UNSIGNED NOT NULL,\n"
        "  release_year YEAR DEFAULT NULL,\n"
        "  last_update TIMESTAMP NOT NULL,\n"
        "  rating ENUM('G','PG','PG-13','R','NC-17') DEFAULT 'G',\n"
        "  PRIMARY KEY (film_id),\n"
        "  UNIQUE KEY idx_votes (votes)\n"
        ");"
    )

    @pytest.mark.parametrize("target", ["tsql", "oracle", "postgresql"])
    def test_types_mapped_and_output_parses(
        self, transpiler: Transpiler, target: str
    ) -> None:
        result = transpiler.transpile(self.TABLE, "mysql", target)
        absent = ["USMALLINT", "UTINYINT", "UMEDIUMINT", " YEAR ", "ENUM"]
        if target != "postgresql":  # TIMESTAMPTZ is native PostgreSQL
            absent.append("TIMESTAMPTZ")
        assert_translated(result.sql, target, absent=tuple(absent))
        body = executable_lines(result.sql)
        assert "CREATE TABLE" in body.upper(), result.sql

    @pytest.mark.parametrize("target", ["tsql", "oracle", "postgresql"])
    def test_enum_becomes_check_constraint(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # The value list is the ENUM's semantics; it must survive as a CHECK,
        # not be dropped.
        result = transpiler.transpile(self.TABLE, "mysql", target)
        body = executable_lines(result.sql)
        assert "CHECK" in body.upper(), result.sql
        assert "'PG-13'" in body, result.sql

    @pytest.mark.parametrize("target", ["tsql", "oracle", "postgresql"])
    def test_named_inline_unique_key_is_a_constraint(
        self, transpiler: Transpiler, target: str
    ) -> None:
        result = transpiler.transpile(self.TABLE, "mysql", target)
        body = executable_lines(result.sql)
        assert re.search(r"(?i)CONSTRAINT\s+\S*idx_votes\S*\s+UNIQUE", body), result.sql

    @pytest.mark.parametrize("target", ["tsql", "oracle", "postgresql"])
    def test_drop_schema_keeps_name(self, transpiler: Transpiler, target: str) -> None:
        # "DROP SCHEMA IF EXISTS sakila" parses with only the db part set;
        # the emitter used to render a dangling "sakila." qualifier.
        result = transpiler.transpile("DROP SCHEMA IF EXISTS sakila;", "mysql", target)
        assert "sakila." not in result.sql
        assert "sakila" in result.sql

    @pytest.mark.parametrize("target", ["tsql", "oracle", "postgresql"])
    def test_charset_introducer_stripped(
        self, transpiler: Transpiler, target: str
    ) -> None:
        # _utf8' ' is a MySQL charset introducer; other engines reject it.
        sql = "SELECT CONCAT(a, _utf8' ', b) FROM t;"
        result = transpiler.transpile(sql, "mysql", target)
        assert_translated(result.sql, target, present=("' '",), absent=("_utf8",))


class TestTSQLAliasTypes:
    """T-SQL alias types (CREATE TYPE x FROM base) resolve to their base.

    The other engines have no alias types (PostgreSQL DOMAINs are close but
    not emitted today), so a column typed [dbo].[Name] must be emitted with
    the alias's base type, harvested from the CREATE TYPE statements in the
    same script (found on AdventureWorksLT, where dbo.Name columns leaked
    into every target and broke MySQL parsing).
    """

    SQL = (
        "CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL\n"
        "GO\n"
        "CREATE TABLE [SalesLT].[Customer](\n"
        "\t[CustomerID] [int] NOT NULL,\n"
        "\t[FirstName] [dbo].[Name] NOT NULL\n"
        ")\n"
        "GO\n"
    )

    @pytest.mark.parametrize(
        "target,expected_type",
        [
            ("postgresql", "VARCHAR(50)"),
            ("mysql", "VARCHAR(50)"),
            ("oracle", "NVARCHAR2(50)"),
        ],
    )
    def test_alias_column_resolves_to_base_type(
        self, transpiler: Transpiler, target: str, expected_type: str
    ) -> None:
        result = transpiler.transpile(self.SQL, "tsql", target)
        body = executable_lines(result.sql)
        assert "dbo.Name" not in body, result.sql
        assert expected_type in body, result.sql

    def test_alias_without_definition_left_untouched(
        self, transpiler: Transpiler
    ) -> None:
        # No CREATE TYPE in the script: nothing to resolve against, the
        # qualified type name passes through as before.
        sql = "CREATE TABLE t ([col] [dbo].[Name] NOT NULL)"
        result = transpiler.transpile(sql, "tsql", "postgresql")
        assert "Name" in result.sql


class TestOracleAlterAddParenthesized:
    """Oracle ALTER TABLE ADD ( ... ) must unwrap for the other engines.

    sqlglot renders the parenthesized form as "ADD COLUMNS (...)", which no
    other engine parses (found on the HR sample schema, where every
    PK/FK/CHECK arrives as ALTER TABLE ADD (CONSTRAINT ...)).
    """

    @pytest.mark.parametrize("target", ["tsql", "postgresql", "mysql"])
    def test_single_constraint_unwrapped(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = (
            "ALTER TABLE countries\n"
            "ADD ( CONSTRAINT countr_reg_fk\n"
            "         FOREIGN KEY (region_id)\n"
            "          REFERENCES regions(region_id)\n"
            "    );"
        )
        result = transpiler.transpile(sql, "oracle", target)
        assert_translated(
            result.sql,
            target,
            present=("ADD CONSTRAINT countr_reg_fk", "FOREIGN KEY"),
            absent=("ADD COLUMNS",),
        )

    @pytest.mark.parametrize("target", ["tsql", "postgresql", "mysql"])
    def test_multiple_columns_unwrapped(
        self, transpiler: Transpiler, target: str
    ) -> None:
        sql = "ALTER TABLE t ADD (a NUMBER(3), b VARCHAR2(10));"
        result = transpiler.transpile(sql, "oracle", target)
        assert_translated(result.sql, target, absent=("ADD COLUMNS",))
        body = executable_lines(result.sql).upper()
        assert re.search(r"ADD\s+A\b", body), result.sql
        assert re.search(r"ADD\s+B\b|,\s*B\b", body), result.sql


class TestIntegerDisplayWidthToPostgres:
    """MySQL integer display widths (TINYINT(1), INT(11)) must not survive
    into PostgreSQL types (SMALLINT(1) is a syntax error there; found on the
    live FE run of the MySQL native fixture)."""

    @pytest.mark.parametrize(
        "src_type", ["TINYINT(1)", "SMALLINT(4)", "INT(11)", "BIGINT(20)"]
    )
    def test_display_width_dropped(self, transpiler: Transpiler, src_type: str) -> None:
        result = transpiler.transpile(
            f"CREATE TABLE t (c {src_type} NOT NULL);", "mysql", "postgresql"
        )
        assert_translated(result.sql, target="postgresql")
        body = executable_lines(result.sql)
        assert not re.search(
            r"(?i)\b(SMALLINT|INTEGER|INT|BIGINT)\s*\(", body
        ), result.sql
