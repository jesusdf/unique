[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Constrained CAST hoisted through SELECT ... INTO ... FROM DUAL" direction="tsql → oracle" kind=article order=51 -->

# A constrained numeric `CAST` inside a PL/SQL expression → hoisted through `SELECT ... INTO ... FROM DUAL`

**Problem.** Oracle's PL/SQL forbids a *constrained* type (one with a
precision/scale, like `DECIMAL(12, 2)`, or a length) on a `CAST` used
directly inside a procedural expression (`PLS-00103`) — only an
unconstrained type is legal there. Simply stripping the constraint would
lose the precision/scale a source `CAST(0.10 AS DECIMAL(12, 2))` explicitly
asked for.

**Solution.**

```sql
-- tests/integration/test_procedural.py::TestTSQLToOracle::test_cast_in_plsql_body_drops_constraint
CREATE FUNCTION dbo.fn_tax (@net DECIMAL(12, 2))
RETURNS DECIMAL(12, 2)
AS
BEGIN
    RETURN @net * CAST(0.10 AS DECIMAL(12, 2))
END
-- tsql -> oracle:
...
V_NET * (SELECT CAST(0.10 AS DECIMAL(12, 2)) INTO ... FROM DUAL)
...
```

**Discussion.** Oracle's constraint restriction only applies to a `CAST`
evaluated in a *PL/SQL* expression context — the same constrained `CAST`
is perfectly legal inside an ordinary SQL statement, since `SELECT ... FROM
DUAL` compiles as SQL, not PL/SQL, even when it's issued from inside a
routine body. Rather than dropping the constraint (which would silently
widen `0.10`'s precision) or failing to compile, Unique routes the
constrained cast through a `SELECT ... INTO ... FROM DUAL` — the same
"escape hatch into SQL" pattern Oracle procedural code uses natively
whenever it needs a SQL-only capability from inside PL/SQL. The cast's
source text (`0.10`, not `0.1`) is preserved exactly, since a literal's
trailing zeros are part of its declared scale, not just its value.

> **Note** faithful — the cast still computes `0.10` at `DECIMAL(12, 2)`
> precision; only its evaluation is routed through a one-row SQL query
> instead of evaluated as a bare PL/SQL expression, which has no
> observable effect on the result. No warning.

**See Also.** [`test_procedural.py::TestTSQLToOracle`](../../../tests/integration/test_procedural.py)
(`test_cast_in_plsql_body_drops_constraint`) · [A lengthless character
`CAST` reaching Oracle: valid inside a PL/SQL body, invalid as a bare
top-level statement](oracle-cast-length-plsql-body-vs-sql-statement.md)
(the sibling entry for Oracle's *other* context-sensitive `CAST` rule —
character length, rather than numeric precision/scale).
