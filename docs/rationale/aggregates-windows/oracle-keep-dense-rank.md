[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Ordered aggregates" direction="oracle → tsql/postgresql/mysql" kind=article order=2 -->

# Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL

**Problem.** `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an
**aggregate**, not a window function: it returns one row per group, taking
`x` from the row(s) whose `y` is the dense-rank extreme.

**Solution.**

```sql
-- corpus case reda-ora-keep-denserank
SELECT MAX(x) KEEP (DENSE_RANK LAST ORDER BY y) AS r
FROM (SELECT 10 x, 1 y FROM DUAL UNION ALL SELECT 20, 2 FROM DUAL
      UNION ALL SELECT 5, 2 FROM DUAL) t
-- Oracle (live): [(20)]. The old, now-replaced PG rewrite gave a running
-- max per row, [(10),(20),(20)] — a different result set entirely.
```

The whole `KEEP (...)` expression is preserved as a
warned `UNIQUE:` carrier comment on every non-Oracle target, replacing the
earlier (incorrect) windowed rewrite.

**Discussion.** None of the three targets has an
"aggregate keyed by another column's extremal rank" construct. The tempting
rewrite — a windowed `MAX(x) OVER (ORDER BY y)` — is a **different**
computation: it returns a running maximum on every input row, not one value
per group, so it silently changes both the row count and the result.

> **Warning** Not faithful — no computed value is produced on
> PostgreSQL/T-SQL/MySQL; the user must supply an equivalent manually. Faithful
> on Oracle (native).

**See Also.** [`reda-ora-keep-denserank`](../../../tests/fixtures/challenge/challenge_oracle.sql) · [§3.3b](../../03-unsupported.md).
