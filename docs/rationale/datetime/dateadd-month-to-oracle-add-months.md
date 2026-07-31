[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Month arithmetic and month-end semantics" direction="tsql/postgresql/mysql → oracle" kind=article order=1 -->

# DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS

**Problem.** T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d,
INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the
day-of-month* and clamp down only when the target month is shorter:
`DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`).

**Solution.**

```sql
-- reda-ts-addmonths-lastday, tsql → oracle
SELECT DATEADD(MONTH, 1, CAST('2020-02-29' AS DATE)) AS d;
-- =>
SELECT ADD_MONTHS(DATE '2020-02-29', 1)
  - (EXTRACT(DAY FROM ADD_MONTHS(DATE '2020-02-29', 1))
     - LEAST(EXTRACT(DAY FROM DATE '2020-02-29'),
             EXTRACT(DAY FROM LAST_DAY(ADD_MONTHS(DATE '2020-02-29', 1)))))
  AS d
FROM DUAL;
```

The Oracle month/quarter/year path
(`oracle_month_add_daypreserving`, `src/unique/core/mappings.py:1164`)
subtracts the extra days `ADD_MONTHS` stepped past, computed with
`LEAST(day, target-month-length)` so the operand's time-of-day is preserved
(a subtractive fix-up rather than rebuilding from `TRUNC`-to-first-of-month).

**Discussion.** Oracle's `ADD_MONTHS` has a different,
stickier rule: when the operand *is* its own month's last day, the result is
forced to the *target* month's last day too — `ADD_MONTHS('2020-02-29', 1)` =
`2020-03-31`. A bare `ADD_MONTHS` call therefore silently overshoots by the
extra days it stuck past the source's day-of-month (corpus
`reda-ts-addmonths-lastday`).

> **Note** faithful — live-verified `2020-03-29` on all four
> engines (also mid-month, day-31-into-a-30-day-month, leap year, quarter and
> subtraction variants; corpus header). No warning; the compensation is applied
> unconditionally since a column operand may hold a month-end date at runtime.
> The reverse direction (Oracle `ADD_MONTHS` as source) is **not** a bare
> copy either — see the sibling entry below: a target's plain
> `DATEADD`/interval-add is day-preserving, not sticky, so it needs its own
> `CASE WHEN` compensation to reproduce Oracle's stickier rule.

**See Also.** Corpus [`reda-ts-addmonths-lastday`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ora-add-months`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
[`oracle_month_add_daypreserving`](../../../src/unique/core/mappings.py) (docstring).

---
