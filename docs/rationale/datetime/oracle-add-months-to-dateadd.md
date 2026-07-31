[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Month arithmetic and month-end semantics" direction="oracle → tsql/postgresql/mysql" kind=article order=2 -->

# ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)

**Problem.** Oracle's `ADD_MONTHS` sticks to the *target* month's last day
whenever the operand is its own month's last day —
`ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. T-SQL's `DATEADD(MONTH, n,
d)`, MySQL's `DATE_ADD(d, INTERVAL n MONTH)`, and PostgreSQL's `d + n *
INTERVAL '1 month'` are all *day-preserving* instead, clamping only when the
target month is too short: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29`,
not `2020-03-31`. A verbatim copy of the arithmetic reproduces the wrong
rule — this is the reverse of the entry above, and needs the same kind of
compensation in the opposite direction.

**Solution.**

```sql
-- oracle -> mysql / tsql / postgresql
SELECT ADD_MONTHS(d, 1) AS r FROM t;
-- => mysql
SELECT CASE WHEN d = LAST_DAY(d) THEN LAST_DAY(DATE_ADD(d, INTERVAL 1 MONTH)) ELSE DATE_ADD(d, INTERVAL 1 MONTH) END AS r
FROM t;
-- => tsql
SELECT CASE WHEN d = EOMONTH(d) THEN EOMONTH(DATEADD(MONTH, 1, d)) ELSE DATEADD(MONTH, 1, d) END AS r
FROM t
-- => postgresql
SELECT CASE WHEN d = CAST(DATE_TRUNC('month', d) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       THEN CAST(DATE_TRUNC('month', (d + 1 * INTERVAL '1 month')) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       ELSE CAST((d + 1 * INTERVAL '1 month') AS DATE) END AS r
FROM t;
```

A literal ISO date operand into PostgreSQL additionally needs an explicit
`DATE '…'` type: PostgreSQL's `DATE_TRUNC` has no unique overload for an
untyped string (`"date_trunc(unknown, unknown) is not unique"`), so the
literal is wrapped before the rewrite runs; a column operand is left
untyped, since it is already typed:

```sql
-- oracle -> postgresql
SELECT ADD_MONTHS(DATE '2020-01-31', 1) AS r;
-- =>
SELECT CASE WHEN DATE '2020-01-31' = CAST(DATE_TRUNC('month', DATE '2020-01-31') + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       THEN CAST(DATE_TRUNC('month', (DATE '2020-01-31' + 1 * INTERVAL '1 month')) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)
       ELSE CAST((DATE '2020-01-31' + 1 * INTERVAL '1 month') AS DATE) END AS r;
```

Each target's own last-day primitive (`LAST_DAY` on MySQL, `EOMONTH` on
T-SQL, the `DATE_TRUNC('month', …) + INTERVAL '1 month' - INTERVAL '1 day'`
build on PostgreSQL) is used both to test "is the operand its own month's
last day" and to compute the sticky result — a `CASE WHEN` of the same
shape as the forward direction above, mirrored.

**Discussion.** Only Oracle's date arithmetic sticks to the last day; every
other engine's month-add is a pure day-preserving offset. Reproducing
Oracle's rule on a target that lacks it natively requires testing the
operand against its own month's last day and branching — no single
expression encodes "day-preserving, except when the operand started on a
month boundary" directly.

> **Note** faithful — reproduces the same sticky last-day mechanism as the
> forward direction: all three non-Oracle targets get the `CASE WHEN` wrap
> with each target's own last-day marker, including the PG-typed-literal
> case above. No warning.

**See Also.** [`test_add_months_preserves_sticky_last_day`](../../../tests/integration/test_rc1a_mappings.py), [`TestOracleAddMonthsPgTypedLiteral`](../../../tests/integration/test_challenge.py) ·
`src/unique/core/converter/emit_functions.py` (`ADD_MONTHS` branch, docstring) ·
Corpus [`ora-add-months`](../../../tests/fixtures/challenge/challenge_oracle.sql).

---
