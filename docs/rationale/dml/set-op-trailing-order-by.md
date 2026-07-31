[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Set-operation `ORDER BY`" direction="tsql → oracle/postgresql/mysql" kind=article order=13 -->

# Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL

**Problem.** `SELECT … EXCEPT SELECT … ORDER BY a` orders the
**combined** result of the whole set operation.

**Solution.**

```sql
-- corpus case reda-ts-setop-orderby (schematic: SELECT ... EXCEPT SELECT ... ORDER BY a)
-- PostgreSQL: ... EXCEPT ... ORDER BY a ASC NULLS FIRST
-- Oracle:     ... MINUS  ... ORDER BY a ASC NULLS FIRST
-- MySQL:      ... ORDER BY a ASC
```

The `ORDER BY` is preserved on the whole set
operation: PostgreSQL/MySQL keep `EXCEPT`/`UNION` as-is; Oracle's `EXCEPT`
spells `MINUS`.

**Discussion.** The `ORDER BY` binds to the combined result of the whole
set operation on every target engine, so nothing about its scope changes —
only its ordering semantics need attention. T-SQL sorts `NULL` first in
ascending order; PostgreSQL and Oracle sort `NULL` last by default, so the
output adds an explicit `ASC NULLS FIRST` on those two engines to reproduce
T-SQL's row order. MySQL already sorts `NULL` first in ascending order, so
a plain `ASC` reproduces the same order with no extra clause needed.

> **Note** faithful — same rows, same order, on every target.

**See Also.** [`reda-ts-setop-orderby`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
