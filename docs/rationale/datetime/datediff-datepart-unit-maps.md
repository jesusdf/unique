[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Truncation and unit maps" direction="cross-engine" kind=article order=8 direction-inferred=true -->

# DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms

**Problem.** T-SQL `DATEDIFF(QUARTER, d1, d2)` and `DATEDIFF(WEEK,
d1, d2)` are valid, translatable unit spellings; `DATEPART(WEEKDAY, d)`
returns the day-of-week under the session's `@@DATEFIRST` setting (default:
Sunday = 1).

**Solution.**

```sql
-- reda-ts-datediff-quarter, tsql → mysql
SELECT DATEDIFF(QUARTER, CAST('2020-01-01' AS DATE), CAST('2020-12-31' AS DATE)) AS r;
-- =>
SELECT ((YEAR(CAST('2020-12-31' AS DATE)) * 4 + QUARTER(CAST('2020-12-31' AS DATE)))
      - (YEAR(CAST('2020-01-01' AS DATE)) * 4 + QUARTER(CAST('2020-01-01' AS DATE)))) AS r;
```

`QUARTER` is reconstructed as a boundary count over `(year*4 + quarter)`,
and `WEEK` as `FLOOR(day-count / 7)`, on every target — this reproduces
T-SQL's calendar-boundary counting (how many quarter/week boundaries lie
between the two dates), not an elapsed-duration count.

`DATEPART(WEEKDAY, d)` is rewritten as a DATEFIRST-independent expression
computed from a known reference Sunday (the same approach PostgreSQL's own
`EXTRACT(DOW)` uses) and carries an explicit caveat, since `@@DATEFIRST` is a
**session** setting Unique cannot observe at transpile time:

```sql
-- reda-ts-datepart-weekday, tsql → postgresql
SELECT DATEPART(WEEKDAY, CAST('2020-06-15' AS DATE)) AS r;
-- =>
SELECT (EXTRACT(DOW FROM CAST('2020-06-15' AS DATE)) + 1)
  /* UNIQUE: DATEPART(WEEKDAY) is @@DATEFIRST-dependent; converted assuming
     the session default (Sunday=1) */ AS r;
```

MySQL emits `DAYOFWEEK(d)` directly (already Sunday=1) and Oracle computes it
via `MOD` arithmetic over a known reference Sunday (`1970-01-04`) — both
DATEFIRST-independent.

**Discussion.** *Why QUARTER/WEEK need reconstruction.* None of the target
engines expose a single function that counts elapsed quarters or weeks the
way T-SQL's `DATEDIFF(QUARTER, …)`/`DATEDIFF(WEEK, …)` do, so the
transpiled SQL rebuilds the count arithmetically from each engine's own
year/quarter/day extraction functions. `DATEADD(QUARTER)` and
`DATEADD(WEEK)` map onto native interval arithmetic on every target and need
no such rebuild — only the diff direction requires it.

*Why WEEKDAY needs its own rewrite.* No target's `EXTRACT`/`DATEPART`
exposes a field literally named `WEEKDAY`, and even the closest equivalents
(PostgreSQL's `EXTRACT(DOW)`, MySQL's `DAYOFWEEK`) number the days
differently, so the value has to be computed from a day-of-week arithmetic
expression tied to a known reference Sunday, then offset to match T-SQL's
1-based, Sunday-first numbering.

> **Note** faithful for QUARTER/WEEK — same boundary-count value on every
> target. **Warned** for WEEKDAY: the emitted value assumes the T-SQL
> default `@@DATEFIRST = 7` (week starts Sunday); a session that has changed
> `DATEFIRST` will see a different T-SQL result than the transpiled output,
> since Unique has no visibility into session state.

**See Also.** Corpus [`reda-ts-datediff-quarter`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`reda-ts-datepart-weekday`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`pg-extract-dow`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestExtractFieldTranslation`](../../../tests/integration/test_challenge.py) (pinned) ·
`emit_functions.py::_emit_date_diff`, `emit_functions.py::_weekday_extract_expr`
· [`UNIQUE-1083`](../../reference/warnings.md#unique-1083) ·
[`EXTRACT(field FROM x)` ↔ T-SQL `DATEPART(field, x)` for the standard
fields](extract-datepart-standard-fields.md) (the common-field respelling
this article's QUARTER/WEEK/WEEKDAY reconstructions are the exception to).
