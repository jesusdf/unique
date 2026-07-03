"""Boolean literals and CURRENT_TIMESTAMP() defaults (audit S1-9 / S1-10).

T-SQL and Oracle (pre-23c) have no boolean literals in SQL contexts:
TRUE/FALSE must become 1/0. PostgreSQL rejects the parenthesized
``CURRENT_TIMESTAMP()`` in DDL defaults.
"""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestBooleanLiterals:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_where_true_to_tsql(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE active = TRUE", "postgresql", "tsql"
        ).sql
        assert "TRUE" not in out.upper()
        assert "active = 1" in out
        _valid(out, "tsql")

    def test_where_false_to_oracle(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE active = FALSE", "postgresql", "oracle"
        ).sql
        assert "FALSE" not in out.upper()
        assert "active = 0" in out
        _valid(out, "oracle")

    def test_boolean_default_to_tsql(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (ok BOOLEAN DEFAULT TRUE)", "postgresql", "tsql"
        ).sql
        assert "DEFAULT 1" in out
        assert "TRUE" not in out.upper()
        _valid(out, "tsql")

    def test_boolean_kept_for_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT * FROM t WHERE active = TRUE", "mysql", "postgresql"
        ).sql
        assert "active = TRUE" in out
        _valid(out, "postgresql")


class TestCurrentTimestampDefault:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_parens_stripped_for_postgresql(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (ts DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "mysql",
            "postgresql",
        ).sql
        assert "CURRENT_TIMESTAMP()" not in out
        assert "DEFAULT CURRENT_TIMESTAMP" in out
        _valid(out, "postgresql")

    def test_parens_stripped_for_oracle(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (ts DATETIME DEFAULT CURRENT_TIMESTAMP)",
            "mysql",
            "oracle",
        ).sql
        assert "CURRENT_TIMESTAMP()" not in out
        _valid(out, "oracle")


class TestOracleParameterTypes:
    """Oracle formal parameters must use unconstrained types (S1-11)."""

    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_sized_parameter_types_are_unconstrained(self) -> None:
        proc = (
            "CREATE PROCEDURE dbo.upd @id INT, @pct DECIMAL(5,2), "
            "@name NVARCHAR(50) AS BEGIN "
            "UPDATE p SET v = @pct WHERE id = @id; END"
        )
        out = self.t.transpile(proc, "tsql", "oracle").sql
        header = out.split("AS")[0]
        # PLS-00103: length/precision are not allowed on formal parameters.
        assert "V_ID IN NUMBER" in header
        assert "V_PCT IN NUMBER" in header
        assert "V_NAME IN NVARCHAR2" in header
        assert "(10)" not in header
        assert "(5, 2)" not in header and "(5,2)" not in header
        assert "(50)" not in header

    def test_function_return_type_unconstrained(self) -> None:
        fn = (
            "CREATE FUNCTION dbo.fmt (@s NVARCHAR(100)) "
            "RETURNS NVARCHAR(100) AS BEGIN RETURN @s; END"
        )
        out = self.t.transpile(fn, "tsql", "oracle").sql
        header = out.split("IS")[0].split("AS")[0]
        assert "(100)" not in header

    def test_table_column_types_keep_size(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (name NVARCHAR(50))", "tsql", "oracle"
        ).sql
        # Only *parameters* lose constraints; column DDL keeps them.
        assert "NVARCHAR2(50)" in out


class TestBitDefaultToBoolean:
    """T-SQL BIT DEFAULT 0/1 -> PostgreSQL BOOLEAN needs a boolean default.

    PostgreSQL rejects "BOOLEAN DEFAULT 1" (integer default on a boolean
    column) — found on the FE harness's first live run (product.is_active).
    """

    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_bit_default_one_to_postgresql(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (is_active BIT NOT NULL DEFAULT 1)",
            "tsql",
            "postgresql",
        ).sql
        assert "BOOLEAN" in out
        assert "DEFAULT TRUE" in out
        assert "DEFAULT 1" not in out
        _valid(out, "postgresql")

    def test_bit_default_zero_to_postgresql(self) -> None:
        out = self.t.transpile(
            "CREATE TABLE t (is_paid BIT NOT NULL DEFAULT (0))",
            "tsql",
            "postgresql",
        ).sql
        assert "DEFAULT FALSE" in out
        _valid(out, "postgresql")

    def test_bit_default_untouched_for_mysql(self) -> None:
        # MySQL maps BIT -> BIT/TINYINT semantics where 0/1 defaults are fine.
        out = self.t.transpile(
            "CREATE TABLE t (is_active BIT NOT NULL DEFAULT 1)",
            "tsql",
            "mysql",
        ).sql
        assert "DEFAULT 1" in out


class TestBitLiteralCoercion:
    """0/1 literals written to a BIT column become TRUE/FALSE on PostgreSQL.

    The CREATE TABLE statements in the same script declare which columns are
    BIT; an INSERT/UPDATE that writes integer 0/1 into them must emit boolean
    literals (PostgreSQL: 'column is of type boolean but expression is of
    type integer', found on the live FE run).
    """

    SCRIPT = (
        "CREATE TABLE dbo.product (\n"
        "    id INT NOT NULL,\n"
        "    qty INT NOT NULL,\n"
        "    is_active BIT NOT NULL DEFAULT 1\n"
        ")\nGO\n"
        "INSERT INTO dbo.product (id, qty, is_active) VALUES (1, 1, 1)\nGO\n"
        "UPDATE dbo.product SET is_active = 0, qty = 0 WHERE id = 1\nGO\n"
    )

    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_insert_and_update_coerced_for_postgresql(self) -> None:
        out = self.t.transpile(self.SCRIPT, "tsql", "postgresql").sql
        assert "VALUES (1, 1, TRUE)" in out
        assert "is_active = FALSE" in out
        # Non-BIT columns keep their integer literals.
        assert "qty = 0" in out

    def test_mysql_keeps_integer_literals(self) -> None:
        out = self.t.transpile(self.SCRIPT, "tsql", "mysql").sql
        assert "VALUES (1, 1, 1)" in out

    def test_procedure_body_insert_coerced_for_postgresql(self) -> None:
        # The INSERT inside a procedure body goes through the procedural
        # pipeline's embedded-DML path; it must coerce 0/1 on BIT columns too
        # (found on the live FE run: create_invoice writes is_paid = 0).
        script = (
            "CREATE TABLE dbo.invoice (\n"
            "    id INT NOT NULL,\n"
            "    is_paid BIT NOT NULL DEFAULT 0\n"
            ")\nGO\n"
            "CREATE PROCEDURE dbo.mk @id INT AS BEGIN\n"
            "    INSERT INTO dbo.invoice (id, is_paid) VALUES (@id, 0);\n"
            "END\nGO\n"
        )
        out = self.t.transpile(script, "tsql", "postgresql").sql
        assert "VALUES (v_id, FALSE)" in out, out
