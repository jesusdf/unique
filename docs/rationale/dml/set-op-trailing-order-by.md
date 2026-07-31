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

**Discussion.** This is not a cross-engine gap — every
target supports `ORDER BY` on a set-operation result — so there is no
engine-level reason to drop it; the entry is here because the earlier
conversion **silently dropped** the `ORDER BY` on every target (a real
defect, not an approved limit).

> **Note** faithful — the earlier silent drop made an ordered
> result unordered with no warning.

**See Also.** [`reda-ts-setop-orderby`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
