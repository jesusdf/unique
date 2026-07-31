[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Dynamic SQL INTO capture" direction="oracle → tsql/postgresql" kind=article order=42 -->

# `EXECUTE IMMEDIATE '<sql>' INTO x` (Oracle) → a two-statement T-SQL capture

**Problem.** Oracle's `EXECUTE IMMEDIATE '<sql>' INTO x` runs a dynamic
query and captures its single-row result directly into a variable —
PostgreSQL's `EXECUTE '<sql>' INTO x` is the same idiom natively. T-SQL's
dynamic-SQL execution (`sp_executesql`, or a plain `EXEC`) has no `INTO`
clause at all: `EXEC sp_executesql @s INTO @x` is not valid T-SQL syntax.

**Solution.**

```sql
-- oracle source
CREATE OR REPLACE PROCEDURE p AS
  x NUMBER;
BEGIN
  EXECUTE IMMEDIATE 'SELECT c1 FROM t' INTO x;
END;
/
-- oracle -> tsql (~344 statements on the real dump used this shape):
CREATE OR ALTER PROCEDURE p
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @x DECIMAL;
    DECLARE @_dyn_result_1 TABLE (c1 NVARCHAR(4000));
    INSERT INTO @_dyn_result_1 EXEC sp_executesql 'SELECT c1 FROM t';
    SELECT TOP (1) @x = c1 FROM @_dyn_result_1;
END

-- oracle -> postgresql (native, single statement):
EXECUTE 'SELECT c1 FROM t' INTO x;
```

**Discussion.** T-SQL's dynamic-SQL execution is a *statement*, not an
expression with an `INTO` clause, so there is nowhere on the `EXEC
sp_executesql` call itself to attach a capture. Unique instead splits the
capture into two statements: the dynamic query's result set is inserted
into a synthesized table variable (`@_dyn_result_N`, typed from the query's
own projection), and a follow-up `SELECT TOP (1) @x = c1 FROM
@_dyn_result_N` pulls the single row into the target variable — the same
"first row wins" semantics `INTO` has on Oracle and PostgreSQL when the
query returns exactly one row. PostgreSQL and Oracle both keep their native
single-statement form unchanged, since both already have their own `INTO`
clause on dynamic execution.

> **Note** faithful — the captured value is identical; only T-SQL needs the
> extra table-variable hop, since it has no expression-level capture on
> dynamic SQL. No warning.

**See Also.** [`test_trigger_predicates_scheduler.py`](../../../tests/integration/test_trigger_predicates_scheduler.py)
(`test_execute_immediate_into_tsql_capture`,
`test_execute_immediate_into_postgres_native`,
`test_execute_immediate_into_oracle_identity`).
