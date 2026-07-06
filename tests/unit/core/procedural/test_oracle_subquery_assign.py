"""Oracle PL/SQL forbids a subquery inside an expression (PLS-00405).

A `SET @x = (SELECT …)` / `SET @x = COALESCE((SELECT …), d)` in a procedure body
must be emitted as `SELECT <expr> INTO x FROM DUAL;`, not `x := (SELECT …);`.
The `FROM DUAL` scalar form also yields NULL when the subquery matches no row,
matching T-SQL's assignment semantics (no NO_DATA_FOUND). Validated live.
"""

from unique.core.transpiler import Transpiler

t = Transpiler()


def _oracle_body(tsql_body: str) -> str:
    sql = f"CREATE PROCEDURE p AS\nBEGIN\n  DECLARE @x INT\n  {tsql_body}\nEND"
    return t.transpile(sql, "tsql", "oracle").sql


class TestOracleSubqueryAssignment:
    def test_bare_subquery_becomes_select_into(self) -> None:
        out = _oracle_body("SET @x = (SELECT MAX(a) FROM rt WHERE b = 1)")
        assert "INTO V_X FROM DUAL" in out.upper(), out
        # the invalid `:= (SELECT …)` form must not survive
        assert ":= ( SELECT" not in out and ":= (SELECT" not in out, out

    def test_subquery_nested_in_expression(self) -> None:
        out = _oracle_body("SET @x = COALESCE((SELECT MAX(a) FROM rt), -1)")
        assert "INTO V_X FROM DUAL" in out.upper(), out
        assert "COALESCE" in out.upper()

    def test_plain_assignment_unchanged(self) -> None:
        # No subquery -> ordinary `:=`, not a SELECT INTO.
        out = _oracle_body("SET @x = 5")
        assert "V_X := 5" in out.upper(), out
        assert "INTO" not in out.upper()


class TestOracleSubqueryDeclareInit:
    """A declaration initialised from a subquery is invalid in Oracle's declare
    section (PLS-00405); the variable is declared bare and the SELECT … INTO is
    hoisted to the top of the body."""

    def test_declare_init_from_subquery_is_hoisted(self) -> None:
        sql = (
            "CREATE PROCEDURE p AS\nBEGIN\n"
            "  DECLARE @x INT = (SELECT MAX(a) FROM rt)\n"
            "  SET @x = @x + 1\nEND"
        )
        out = t.transpile(sql, "tsql", "oracle").sql
        up = out.upper()
        # bare declaration in the IS section (no ':=' subquery init there)
        assert "V_X NUMBER(10);" in up, out
        # the init moved into the body as a SELECT … INTO
        assert "SELECT ( SELECT MAX ( A ) FROM RT ) INTO V_X FROM DUAL" in up, out
        # it must precede the use of V_X
        assert up.index("INTO V_X FROM DUAL") < up.index("V_X := V_X + 1"), out
