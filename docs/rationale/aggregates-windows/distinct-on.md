[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="`DISTINCT ON`" direction="postgresql → tsql/oracle/mysql" kind=article order=10 -->

# PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle

**Problem.** `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b`
returns exactly **one** row per distinct `a` — the first one under the
`ORDER BY`.

**Solution.**

```sql
-- corpus case pg-distinct-on
SELECT DISTINCT ON (a) a, b FROM (VALUES (1,10),(1,20),(2,5),(2,7)) v(a,b)
ORDER BY a, b
-- T-SQL/MySQL/Oracle: SELECT ... FROM (SELECT a, b,
--   ROW_NUMBER() OVER (PARTITION BY a ORDER BY b) AS uq_rn FROM ...) x
--   WHERE uq_rn = 1
```

A `ROW_NUMBER() OVER (PARTITION BY a ORDER BY …) AS
uq_rn` derived table, filtered to `uq_rn = 1` in the outer query — reproduces
"one row per `a`, first by the given order" exactly.

**Discussion.** None of the other three engines has
`DISTINCT ON`. A plain `SELECT DISTINCT a, b` is not equivalent: it returns
every distinct `(a, b)` **pair**, not one row per `a` — a different row
count whenever a given `a` has more than one `b`.

> **Note** faithful — PG native = `[(1,10),(2,5)]`; the old
> `SELECT DISTINCT` mistranslation gave `[(1,10),(1,20),(2,5),(2,7)]` on the
> other three engines (a real defect this rewrite fixed).

**See Also.** [`pg-distinct-on`](../../../tests/fixtures/challenge/challenge_postgresql.sql).
