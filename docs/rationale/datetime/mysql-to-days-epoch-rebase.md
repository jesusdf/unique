[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Epoch rebasing" direction="mysql → all" kind=article order=6 direction-inferred=true -->

# MySQL TO_DAYS year-0000 epoch rebase

**Problem.** MySQL `TO_DAYS(d)` returns the count of days since a
notional `0000-01-01`.

**Solution.**

```sql
-- my-to-days-year-zero, mysql → postgresql / tsql / oracle
SELECT TO_DAYS('2020-01-01') AS d;
-- =>
SELECT (CAST(DATE '2020-01-01' AS DATE) - CAST(DATE '1970-01-01' AS DATE)) + 719528 AS d;
```

`_rebase_to_days` (`convert.py:3271`) recognises the
`DATEDIFF(x, DATE '0000-01-01', DAY) + 1` shape and re-expresses it against
`1970-01-01` — a value every engine parses identically — offset by the known
constant `719528` (`TO_DAYS('1970-01-01')`).

**Discussion.** sqlglot lowers `TO_DAYS(d)` to
`DATEDIFF(d, DATE '0000-01-01', DAY) + 1`, but year `0000` is rejected by
every other engine — PostgreSQL raises `DatetimeFieldOverflow`, T-SQL raises
"Conversion failed" (241), and Oracle's `DATE` literal range is `-4713..9999`
(`ORA-01841`) and would in any case put the value on the Julian calendar for
pre-1582 dates, two days off the proleptic Gregorian count MySQL uses. This
produced a hard runtime error on every target with no warning
(`my-to-days-year-zero`).

> **Note** faithful — the rebase is an exact algebraic
> identity (day counts from any two fixed epochs differ by a constant), so the
> result matches MySQL's `TO_DAYS` for any post-Gregorian-reform date. No
> warning.

**See Also.** Corpus [`my-to-days-year-zero`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
`convert.py::_rebase_to_days` (docstring).

---
