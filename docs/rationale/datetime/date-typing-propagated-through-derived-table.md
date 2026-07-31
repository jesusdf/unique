[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="DATE typing propagated through a derived table" direction="oracle → tsql/mysql/postgresql" kind=article order=12 -->

# An Oracle `DATE` literal inside a derived-table projection → its typing survives to the outer column reference

**Problem.** `SELECT ShipDate - OrderDate FROM (SELECT DATE '2020-01-10'
ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x` computes a day count on
Oracle, since `DATE - DATE` is arithmetic there. If the inner projection's
`DATE '...'` typing is lost once it crosses into the derived table's own
column list — read back outside only as an untyped string — the outer
subtraction becomes a text-minus-text operation instead: a live runtime
error on PostgreSQL ("operator does not exist: text - text") and silent
numeric coercion to `0` on MySQL, neither of which is the 9-day answer
Oracle itself produces.

**Solution.**

```sql
-- fixture challenge_oracle.sql, corpus case reda-ora-date-literal-subquery
SELECT ShipDate - OrderDate AS d
FROM (SELECT DATE '2020-01-10' ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x
-- oracle -> tsql:
SELECT DATEDIFF(DAY, OrderDate, ShipDate) AS d
FROM (SELECT CAST('2020-01-10' AS DATE) AS ShipDate, CAST('2020-01-01' AS DATE) AS OrderDate) x
-- oracle -> mysql:
SELECT DATEDIFF(ShipDate, OrderDate) AS d
FROM (SELECT CAST('2020-01-10' AS DATE) AS ShipDate, CAST('2020-01-01' AS DATE) AS OrderDate
FROM DUAL) x;
-- oracle -> postgresql:
SELECT (ShipDate - OrderDate) AS d
FROM (SELECT DATE '2020-01-10' AS ShipDate, DATE '2020-01-01' AS OrderDate) x;
```

**Discussion.** Two things have to happen together for this to come out
right. First, the derived table's own projection keeps its `DATE` typing
explicit on every target — a `CAST(... AS DATE)` on T-SQL/MySQL, PostgreSQL's
native `DATE '...'` literal — rather than degrading to a bare string once
it's inside a subquery's `SELECT` list. Second, that inferred `DATE` type
has to be remembered for the *outer* column references (`ShipDate`,
`OrderDate` used outside the derived table), so the outer subtraction knows
it's operating on dates and can be spelled as each target's own day-count
subtraction (`DATEDIFF(DAY, ...)` on T-SQL, `DATEDIFF(...)` — different
argument order — on MySQL, native `-` on PostgreSQL/Oracle) instead of
falling back to a plain, ungoverned `-`. The same propagation carries
through a CTE and across more than one level of subquery nesting, since a
pass-through column reference doesn't reset what's known about its type.

> **Note** faithful — live-verified `9` (days) on every target, matching
> Oracle's own `DATE - DATE` result; before this propagation, the same
> query raised on PostgreSQL and silently returned `0` on MySQL — a defect
> the sweep that surfaced this row found already fixed on inspection, not
> an open issue.

**See Also.** Corpus [`reda-ora-date-literal-subquery`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
[Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp −
timestamp](temporal-plus-minus-arithmetic.md) (the sibling mechanism for
direct date arithmetic, as opposed to typing that must survive a subquery
boundary first).
