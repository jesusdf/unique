[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Subquery-in-expression assignment restructuring" direction="tsql → oracle" kind=article order=39 -->

# T-SQL subquery-in-expression assignment → Oracle `SELECT ... INTO ... FROM DUAL`

**Problem.** T-SQL lets a variable assignment's right-hand side embed a
subquery directly, either as the whole expression or nested inside another
call: `SET @x = (SELECT MAX(a) FROM t)`, or
`DECLARE @x INT = (SELECT MAX(a) FROM t)` as an initializer. PL/SQL's `:=`
assignment operator forbids a subquery anywhere in its right-hand
expression (`PLS-00405: subquery not allowed in this context`) — the
literal translation does not compile on Oracle.

**Solution.**

```sql
-- tests/unit/core/procedural/test_oracle_subquery_assign.py
CREATE PROCEDURE p AS
BEGIN
  DECLARE @x INT
  SET @x = (SELECT MAX(a) FROM rt WHERE b = 1)
END
-- tsql -> oracle:
CREATE OR REPLACE PROCEDURE p
IS
    V_X NUMBER(10);
BEGIN
    SELECT (SELECT MAX(a) FROM rt WHERE b = 1) INTO V_X FROM DUAL;
END;
/
```

A subquery nested inside another call (`SET @x = COALESCE((SELECT MAX(a)
FROM rt), -1)`) restructures the same way, keeping the surrounding
expression intact around the `SELECT ... INTO`. A declaration initialized
from a subquery (`DECLARE @x INT = (SELECT MAX(a) FROM rt)`) can't become a
`SELECT ... INTO` in place either — Oracle's declare section allows only a
`:=` literal/expression initializer, not a query — so the variable is
declared bare and the `SELECT ... INTO` is hoisted to the first executable
statement in the body, ahead of every use of the variable:

```sql
-- tests/unit/core/procedural/test_oracle_subquery_assign.py
CREATE PROCEDURE p AS
BEGIN
  DECLARE @x INT = (SELECT MAX(a) FROM rt)
  SET @x = @x + 1
END
-- tsql -> oracle:
CREATE OR REPLACE PROCEDURE p
IS
    V_X NUMBER(10);
BEGIN
    SELECT (SELECT MAX(a) FROM rt) INTO V_X FROM DUAL;
    V_X := V_X + 1;
END;
/
```

An assignment with no subquery in it (`SET @x = 5`) is untouched — it stays
a plain `V_X := 5;`.

**Discussion.** The `SELECT expr INTO x FROM DUAL` form sidesteps
`PLS-00405` because the subquery lives inside a `SELECT` list, a context
Oracle always allows a query in, rather than inside a `:=` expression. It
also preserves the source's assignment semantics exactly: a T-SQL scalar
subquery that matches zero rows leaves the variable `NULL` (no error), and
`SELECT ... FROM DUAL` does the same — unlike `SELECT ... INTO` without
`FROM DUAL` against a real table, which would raise `NO_DATA_FOUND` on zero
rows and `TOO_MANY_ROWS` on more than one. `FROM DUAL` keeps the statement
a single-row query regardless of how many rows the subquery itself touches.

> **Note** faithful — live-verified: the restructured `SELECT ... INTO ...
> FROM DUAL` compiles and preserves the source assignment's NULL-on-no-match
> behavior.

**See Also.** [`TestOracleSubqueryAssignment`, `TestOracleSubqueryDeclareInit`](../../../tests/unit/core/procedural/test_oracle_subquery_assign.py) ·
[From DUAL](../dml/from-dual.md), the sibling mechanism for a table-less
`SELECT` that needs no assignment target.
