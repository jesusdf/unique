[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Storage and physical options" direction="tsql → oracle/mysql" kind=article order=12 -->

# T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL

**Problem.** `FILLFACTOR` reserves free space per index page for
future inserts — a physical storage tuning knob with no logical effect on
query results.

**Solution.**

```sql
-- corpus case reda-ts-index-fillfactor-mysql
CREATE INDEX ix ON t (a) WITH (FILLFACTOR = 80)
-- MySQL: CREATE INDEX ix ON t(a)   -- FILLFACTOR dropped, warned
```

The clause is dropped, with a `UNIQUE:` carrier +
warning, leaving a plain `CREATE INDEX ix ON t (a)`.

**Discussion.** Oracle and MySQL have no `FILLFACTOR`
concept on `CREATE INDEX`.

> **Note** faithful in result (no logical difference —
> `FILLFACTOR` never affects query results, only storage layout). The MySQL
> path had a real defect: the `WITH (FILLFACTOR = 80)` option text was folded
> **into** the index's key-part parentheses (`CREATE INDEX ix ON t ((a) WITH
> (FILLFACTOR=80))`) rather than dropped, producing invalid SQL (MySQL error
> 1064) with no warning — now fixed to match the Oracle path's clean drop.

**See Also.** [`reda-ts-index-fillfactor-mysql`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1014`](../../reference/warnings.md#unique-1014).
