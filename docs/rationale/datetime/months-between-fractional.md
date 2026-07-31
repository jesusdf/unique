[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Month arithmetic and month-end semantics" direction="oracle → tsql" kind=article order=10 -->

# Oracle `MONTHS_BETWEEN` fractional value → T-SQL exact `CASE` formula

**Problem.** Oracle's `MONTHS_BETWEEN(date1, date2)` returns a
**fractional** number of months: whole months plus `(day1 - day2) / 31` for
the remainder, collapsing to a whole number only when both dates are the
last day of their month or share the same day-of-month. T-SQL has no
equivalent function — a naive translation to `DATEDIFF(MONTH, ...)` would
give an *integer* count of calendar-month boundaries crossed, a
structurally different (and less precise) number, not just a formatting
difference.

**Solution.**

```sql
-- ora-months-between-val, oracle → tsql
SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL;
-- =>
SELECT CASE
  WHEN DAY(CAST('2020-03-10' AS DATE)) = DAY(CAST('2020-01-15' AS DATE))
    OR (DAY(CAST('2020-03-10' AS DATE)) = DAY(EOMONTH(CAST('2020-03-10' AS DATE)))
        AND DAY(CAST('2020-01-15' AS DATE)) = DAY(EOMONTH(CAST('2020-01-15' AS DATE))))
  THEN DATEDIFF(MONTH, CAST('2020-01-15' AS DATE), CAST('2020-03-10' AS DATE))
  ELSE DATEDIFF(MONTH, CAST('2020-01-15' AS DATE), CAST('2020-03-10' AS DATE))
       + (DAY(CAST('2020-03-10' AS DATE)) - DAY(CAST('2020-01-15' AS DATE))) / 31.0
END AS r;
```

The `CASE` reproduces Oracle's own rule directly: `DATEDIFF(MONTH, ...)`
supplies the whole-month count in every branch, and the fractional
remainder `(day1 - day2) / 31.0` is added only when neither date is a
month's last day (`EOMONTH`) and the two days-of-month differ — Oracle's
own condition for returning a whole number rather than a fraction.
Live-verified `1.83871` for `MONTHS_BETWEEN(2020-03-10, 2020-01-15)`, and
`1.0` when both dates fall on a month-end.

**Discussion.** `MONTHS_BETWEEN`'s fractional remainder is a real part of
Oracle's return value, not a rounding artifact — an integer `DATEDIFF`
boundary count would silently change the value's *precision class*, not
merely its display, for any pair of dates that don't happen to land on the
same day-of-month or a month-end. The `CASE` formula is built to match
Oracle's documented rule exactly, including its month-end special case
(where the fraction *should* collapse to `0`, matching Oracle's own
whole-number return there instead of leaving a spurious fractional
remainder from unequal month lengths).

> **Note** faithful — live-verified: `MONTHS_BETWEEN(DATE '2020-03-10',
> DATE '2020-01-15')` = `1.83871...` on Oracle, matched exactly by the
> `CASE` formula on T-SQL; both return `1.0` when the two dates share a
> day-of-month or are both month-ends.

**See Also.** Corpus [`ora-months-between-val`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
[`TestMonthsBetweenFractional`](../../../tests/integration/test_challenge.py).
