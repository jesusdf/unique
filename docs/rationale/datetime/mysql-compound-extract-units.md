[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Compound EXTRACT units" direction="mysql → all" kind=article order=9 -->

# MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets

**Problem.** MySQL's `EXTRACT` accepts several **compound** units —
`YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack
two or more calendar fields into a single decimal-weighted number in one
call. No other engine's `EXTRACT`/`DATEPART` has an equivalent unit; there
is nothing to rename them to.

**Solution.**

```sql
-- my-extract-compound, mysql → postgresql / oracle / tsql
SELECT EXTRACT(YEAR_MONTH FROM NOW()), EXTRACT(DAY_HOUR FROM NOW());

-- => postgresql / oracle
SELECT (EXTRACT(YEAR FROM CURRENT_TIMESTAMP) * 100 + EXTRACT(MONTH FROM CURRENT_TIMESTAMP)),
       (EXTRACT(DAY FROM CURRENT_TIMESTAMP) * 100 + EXTRACT(HOUR FROM CURRENT_TIMESTAMP));

-- => tsql
SELECT (DATEPART(YEAR, GETDATE()) * 100 + DATEPART(MONTH, GETDATE())),
       (DATEPART(DAY, GETDATE()) * 100 + DATEPART(HOUR, GETDATE()));
```

Each compound unit is rebuilt from its component single-field extracts,
combined with the same positional decimal weight MySQL itself uses:
`YEAR_MONTH` is `YEAR * 100 + MONTH` (MySQL's own value for
March 2024 is `202403`), `DAY_HOUR` is `DAY * 100 + HOUR`, and the wider
compound units (`DAY_MINUTE`, `DAY_SECOND`, …) extend the same pattern with
an additional `* 100` per extra field. Live-verified `202403` / `1510` on
all four engines.

**Discussion.** MySQL's compound units aren't a different spelling of an
existing construct — they're MySQL's own convention for packing multiple
calendar fields into one number, with no counterpart unit name on
PostgreSQL, Oracle or T-SQL to map to. Reconstructing the value from single
-field `EXTRACT`/`DATEPART` calls, combined the same way MySQL itself
combines them, reproduces the exact number every target would need a
compound-unit `EXTRACT` to produce directly. This is a different mechanism
from the "Multi-field PostgreSQL `INTERVAL` decomposition" entry in this
topic: that one decomposes an interval *value* string (`INTERVAL '1 year 2
months 3 days'`) into arithmetic; this one reconstructs an `EXTRACT` *unit*
that has no target equivalent at all.

> **Note** faithful — live-verified `202403` (`YEAR_MONTH` for March 2024)
> and `1510` (`DAY_HOUR` for day 15, hour 10) identically on MySQL and the
> rebuilt PostgreSQL/Oracle/T-SQL forms.

**See Also.** Corpus [`my-extract-compound`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestCompoundExtract`](../../../tests/integration/test_challenge.py) ·
[Multi-field PostgreSQL INTERVAL decomposition](postgresql-interval-decomposition.md),
the sibling mechanism for an interval value rather than an `EXTRACT` unit.
