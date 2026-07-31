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

`TO_DAYS(d)` is defined as a day count against the notional epoch
`0000-01-01`, which is re-expressed against `1970-01-01` — a value every
engine parses identically — offset by the known constant `719528`
(`TO_DAYS('1970-01-01')`).

**Discussion.** `TO_DAYS(d)` is equivalent to a day-count difference
against `DATE '0000-01-01'`, but year `0000` is rejected by every other
engine — PostgreSQL raises `DatetimeFieldOverflow`, T-SQL raises
"Conversion failed" (241), and Oracle's `DATE` literal range is `-4713..9999`
(`ORA-01841`) and would in any case put the value on the Julian calendar for
pre-1582 dates, two days off the proleptic Gregorian count MySQL uses. A
literal `0000-01-01` epoch is therefore unusable on any target, which is why
the rebase against `1970-01-01` is needed rather than a direct copy.

> **Note** faithful — the rebase is an exact algebraic
> identity (day counts from any two fixed epochs differ by a constant), so the
> result matches MySQL's `TO_DAYS` for any post-Gregorian-reform date. No
> warning.

**See Also.** Corpus [`my-to-days-year-zero`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
`convert.py::_rebase_to_days` (docstring).

---
