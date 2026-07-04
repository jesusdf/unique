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


class TestOracleSystimestamp:
    """Oracle ``SYSTIMESTAMP`` (the native FE schema's ``created_at``/
    ``updated_at`` default) has no equivalent on the other engines and used to
    leak as an invalid ``SYSTIMESTAMP()`` call — invalid even on Oracle, which
    takes no parens. It must map to each target's current-timestamp form."""

    def setup_method(self) -> None:
        self.t = Transpiler()

    _DDL = "CREATE TABLE t (created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL)"

    def test_ddl_default_to_postgresql(self) -> None:
        out = self.t.transpile(self._DDL, "oracle", "postgresql").sql
        assert "SYSTIMESTAMP" not in out.upper()
        assert "DEFAULT CURRENT_TIMESTAMP" in out
        _valid(out, "postgresql")

    def test_ddl_default_to_mysql(self) -> None:
        out = self.t.transpile(self._DDL, "oracle", "mysql").sql
        assert "SYSTIMESTAMP" not in out.upper()
        assert "CURRENT_TIMESTAMP" in out
        _valid(out, "mysql")

    def test_ddl_default_to_tsql(self) -> None:
        out = self.t.transpile(self._DDL, "oracle", "tsql").sql
        assert "SYSTIMESTAMP" not in out.upper()
        assert "GETDATE()" in out
        _valid(out, "tsql")

    def test_procedural_assignment_to_postgresql(self) -> None:
        # The trigger body ``:NEW.updated_at := SYSTIMESTAMP`` goes through the
        # procedural pipeline; it must map too (dual-pipeline symmetry).
        proc = (
            "CREATE OR REPLACE PROCEDURE p IS\nBEGIN\n"
            "    UPDATE t SET updated_at = SYSTIMESTAMP;\n"
            "END;"
        )
        out = self.t.transpile(proc, "oracle", "postgresql").sql
        assert "SYSTIMESTAMP" not in out.upper()
        assert "CURRENT_TIMESTAMP" in out.upper()


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

    def test_unconstrained_decimal_becomes_number(self) -> None:
        # A bare Oracle DECIMAL is NUMBER(38, 0) and rounds to an integer. Once
        # the (p, s) is stripped for a parameter/RETURN, DECIMAL must become
        # NUMBER (unconstrained -> keeps the value's scale), or a tax function
        # returning net * 0.10 = 5.55 comes back as 6.
        fn = (
            "CREATE FUNCTION fn_tax(net DECIMAL(12, 2)) RETURNS DECIMAL(12, 2)\n"
            "DETERMINISTIC\nBEGIN\n    RETURN net * 0.10;\nEND"
        )
        out = self.t.transpile(fn, "mysql", "oracle").sql
        assert "net IN NUMBER" in out
        assert "RETURN NUMBER" in out
        assert "DECIMAL" not in out


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


class TestOracleBareNumberToInteger:
    """Oracle's unqualified ``NUMBER`` (no precision) is used for integer
    ids/counts. It must map to an integer type so identity/PK/FK columns are
    valid — a DECIMAL can't be AUTO_INCREMENT on MySQL nor match a SERIAL PK on
    PostgreSQL (the oracle→{mysql,postgresql} live DDL failures). ``NUMBER(p,s)``
    keeps its DECIMAL mapping."""

    def setup_method(self) -> None:
        self.t = Transpiler()

    _DDL = (
        "CREATE TABLE invoice (\n"
        "  id NUMBER GENERATED ALWAYS AS IDENTITY,\n"
        "  customer_id NUMBER NOT NULL,\n"
        "  unit_price NUMBER(10, 2) NOT NULL,\n"
        "  CONSTRAINT fk FOREIGN KEY (customer_id) REFERENCES customer (id)\n"
        ")"
    )

    def test_identity_and_fk_to_mysql(self) -> None:
        out = self.t.transpile(self._DDL, "oracle", "mysql").sql
        assert "id BIGINT AUTO_INCREMENT" in out
        assert "customer_id BIGINT" in out
        # A qualified NUMBER(p,s) is still a decimal.
        assert "unit_price DECIMAL(10, 2)" in out
        assert "DECIMAL AUTO_INCREMENT" not in out
        _valid(out, "mysql")

    def test_identity_and_fk_to_postgresql(self) -> None:
        out = self.t.transpile(self._DDL, "oracle", "postgresql").sql
        # BIGSERIAL (int8) so the BIGINT FK column matches.
        assert "id BIGSERIAL" in out
        assert "customer_id BIGINT" in out
        assert "unit_price DECIMAL(10, 2)" in out or "unit_price NUMERIC(10, 2)" in out
        _valid(out, "postgresql")

    def test_bare_decimal_from_tsql_source_unchanged(self) -> None:
        # A bare DECIMAL from a non-Oracle source keeps its meaning (no coercion).
        out = self.t.transpile(
            "CREATE TABLE t (amount DECIMAL)", "tsql", "postgresql"
        ).sql
        assert "BIGINT" not in out.upper()
        assert "amount DECIMAL" in out or "amount NUMERIC" in out
