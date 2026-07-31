[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Boolean aggregates and `FILTER`" direction="postgresql → tsql/oracle" kind=article order=5 -->

# `bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle

**Problem.** `bool_or(a > 5) FILTER (WHERE b = 1)` combines the
boolean-aggregate value wrapping above with `FILTER`'s
`agg(CASE WHEN cond THEN arg END)` rewrite in a single expression.

**Solution.**

```sql
-- corpus case pg-boolagg-filter
SELECT bool_or(a > 5) FILTER (WHERE b = 1) AS r
FROM (VALUES (10,1),(2,1),(3,2)) v(a,b)
-- T-SQL/Oracle: MAX(CAST(CASE WHEN b = 1 THEN CASE WHEN a > 5 THEN 1 ELSE 0 END END AS INT))
-- (pinned assertion checks "WHEN a > 5 THEN 1" present, "FILTER"/"bool_or" absent)
```

The 1/0 wrap is applied inside the `FILTER` rewrite's
`CASE`, so the emitted form contains `WHEN a > 5 THEN 1` (never a bare
`FILTER`/`bool_or` token) on T-SQL and Oracle.

**Discussion.** Composing the two rewrites naively feeds
the FILTER `CASE`'s `THEN` branch the *raw* predicate (`a > 5`) instead of the
1/0-wrapped form, which T-SQL rejects the same way a bare `CAST` operand is
rejected (no boolean value type in a `CASE` `THEN` position).

> **Note** faithful — result 1 (true).

**See Also.** [`pg-boolagg-filter`](../../../tests/fixtures/challenge/challenge_postgresql.sql) (component cases verified independently:
[`pg-bool-to-int-cast`](../../../tests/fixtures/challenge/challenge_postgresql.sql), and the FILTER-alone rewrite around
[`pg-filter-subquery`](../../../tests/fixtures/challenge/challenge_postgresql.sql)).
