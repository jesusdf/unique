[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`PIVOT` / `UNPIVOT`" direction="tsql/oracle → postgresql/mysql" kind=article order=1 -->

# `PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL

**Problem.** `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows
into columns for a small, explicit set of pivot values, aggregating `arg` per
value.

**Solution.**

```sql
-- corpus case reda-ts-pivot
CREATE TABLE t (dept VARCHAR(1), v INT);
SELECT * FROM (SELECT dept, v FROM t) src PIVOT (SUM(v) FOR dept IN ([A],[B])) pv
-- Oracle:  ... src PIVOT (SUM(v) FOR dept IN ('A' AS A, 'B' AS B)) ...
-- PostgreSQL/MySQL:
--   SELECT SUM(CASE WHEN dept = 'A' THEN v END) AS A,
--          SUM(CASE WHEN dept = 'B' THEN v END) AS B
--   FROM (SELECT dept, v FROM t) src
-- Live (rows A/1, A/2, B/5): PIVOT = one row (A=3, B=5); the old silent drop
-- returned the 3 raw rows instead.
```

T-SQL keeps its native `PIVOT`; Oracle re-spells the
`IN`-list with explicit aliases (`PIVOT (SUM(v) FOR dept IN ('A' AS A, 'B' AS
B))`). PostgreSQL/MySQL get a conditional-aggregation derived table —
`SUM(CASE WHEN dept = 'A' THEN v END) AS A` per pivot value, grouped by every
source column that is neither the pivot column nor the aggregate argument.
When the source's projected columns are not visible (a bare table or
`SELECT *`), the grouping columns cannot be determined and the relation
degrades to a warned carrier instead (`emit_relations.py::_emit_pivot_relation`).

**Discussion.** PostgreSQL and MySQL have no `PIVOT`
operator at all. Oracle keeps `PIVOT` natively but needs an explicit
`'v' AS v` alias in the `IN`-list so its output columns are named like
T-SQL's default `[v]` bracket naming.

> **Note** faithful when the source projection is visible.
> `[limit]` (warned carrier) otherwise. The original conversion silently
> **dropped the whole `PIVOT` operator** with no warning — a defect this
> lowering replaced.

**See Also.** [`reda-ts-pivot`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) · [§2](../../03-unsupported.md) (T-SQL
PIVOT/UNPIVOT row).
