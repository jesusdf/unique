[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family" direction="mysql → postgresql" kind=article order=6 -->

# `DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL

**Problem.** `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR
'-')` de-duplicates `x` and orders the *numeric* values before joining them.

**Solution.**

```sql
-- corpus case my-groupconcat-distinct-numord
SELECT GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-') AS g
FROM (SELECT 2 x UNION ALL SELECT 10 UNION ALL SELECT 1 UNION ALL SELECT 2) t
```

The `DISTINCT` is moved into a derived table
(`SELECT DISTINCT x FROM …`) so the outer `STRING_AGG` can `ORDER BY` the raw
numeric `x` directly, bounded to a single un-grouped aggregation (the same
restructuring `pg-distinct-on` uses).

**Discussion.** PostgreSQL's `STRING_AGG` requires its
`ORDER BY` key to equal the `DISTINCT`-ed argument. Casting `x` to `TEXT` (to
`DISTINCT`) and then ordering by that same text key sorts **lexically**
(`'10' < '2'`), not numerically — a different order than MySQL's.

> **Note** faithful — live-verified MySQL/PostgreSQL/Oracle =
> `'10-2-1'`. Oracle (native `LISTAGG(DISTINCT …)`) and T-SQL (warned degrade,
> `STRING_AGG` has no `DISTINCT`) do not need this restructuring.

**See Also.** [`my-groupconcat-distinct-numord`](../../../tests/fixtures/challenge/challenge_mysql.sql).
