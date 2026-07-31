[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Month arithmetic and month-end semantics" direction="mysql → all" kind=article order=5 direction-inferred=true -->

# MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target

**Problem.** MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts
**complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')`
= `1`, not `2`, because the end's day-of-month (`10`) has not reached the
start's (`15`) — the final partial month does not count.

**Solution.**

```sql
-- my-timestampdiff-mon, mysql → tsql
SELECT TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10') AS r;
-- =>
SELECT (DATEDIFF(MONTH, '2020-01-15', '2020-03-10')
        - CASE WHEN DATEADD(MONTH, DATEDIFF(MONTH, '2020-01-15', '2020-03-10'), '2020-01-15')
               > '2020-03-10' THEN 1 ELSE 0 END) AS r;

-- my-timestampdiff-mon-pgora, mysql → postgresql
SELECT TIMESTAMPDIFF(MONTH, '2020-01-31', '2020-03-30') AS r;
-- =>
SELECT (((EXTRACT(YEAR FROM DATE '2020-03-30') * 12 + EXTRACT(MONTH FROM DATE '2020-03-30'))
       - (EXTRACT(YEAR FROM DATE '2020-01-31') * 12 + EXTRACT(MONTH FROM DATE '2020-01-31')))
       - CASE WHEN DATE '2020-01-31' + (…) * INTERVAL '1 month' > DATE '2020-03-30'
              THEN 1 ELSE 0 END) AS r;
```

A shared helper (`_complete_period_adjust`,
`emit_functions.py:179`) drops the incomplete final period from any
year/quarter/month boundary count: it re-adds the boundary count as an
interval to `start` and subtracts 1 whenever that overshoots `end`.

**Discussion.** T-SQL `DATEDIFF(MONTH, …)`, and the
naïve `(year*12 + month)` boundary difference used for PostgreSQL/Oracle,
both count **calendar-boundary crossings**, not complete periods —
`DATEDIFF(MONTH, '2020-01-15', '2020-03-10')` = `2` (January→February,
February→March boundaries), overcounting by exactly the incomplete final
period. The gap was found and fixed once for the T-SQL target
(`my-timestampdiff-mon`), then found again on PostgreSQL/Oracle
(`my-timestampdiff-mon-pgora`) — the boundary-count rewrite used there had not
inherited the same adjustment.

> **Note** faithful — live-verified `1` (T-SQL) and the
> PG/Oracle case verified against MySQL's own `1` (was silently `2` before the
> fix). No warning; a plain `DATEDIFF`-sourced batch (T-SQL boundary counting,
> not MySQL complete-period counting) deliberately keeps the unadjusted
> boundary count.

**See Also.** Corpus [`my-timestampdiff-mon`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-timestampdiff-mon-pgora`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
`emit_functions.py::_complete_period_adjust` (docstring) ·
`emit_functions.py::_emit_date_diff`.

---
