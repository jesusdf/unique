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

The `QUARTER`/`WEEK` gap was closed by extending
`_emit_date_diff`'s unit handling — `QUARTER` as a boundary count over
`(year*4 + quarter)`, `WEEK` as `FLOOR(day-count / 7)` — on every target.

`DATEPART(WEEKDAY, d)` now routes through the shared `_weekday_extract_expr`
helper (the same DATEFIRST-/NLS-independent rewrite as PostgreSQL's
`EXTRACT(DOW)`, computed from a known reference Sunday) and carries an
explicit caveat, since `@@DATEFIRST` is a **session** setting Unique cannot
observe at transpile time:

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

**Discussion.** *Why there is no direct mapping (QUARTER/WEEK).* This was not
an inherent engine gap but an implementation hole: `_emit_date_diff`'s
per-target second/minute/hour lookup (`{"HOUR": 3600, "MINUTE": 60, "SECOND":
1}[unit]`) only covered those three units. A `QUARTER` or `WEEK` unit raised
an uncaught Python `KeyError`, which the transpile catch-all swallowed and
surfaced as a `/* TRANSPILATION ERROR: QUARTER */` carrier shipping the raw,
untranslated T-SQL `DATEDIFF` — invalid on MySQL/Oracle
(`reda-ts-datediff-quarter`, class `crash`). `DATEADD(QUARTER)`/`DATEADD(WEEK)`
already worked; only `DATEDIFF`'s unit table was incomplete.

*Why there is no direct mapping (WEEKDAY).* No target's `EXTRACT`/`DATEPART`
has a `DAYOFWEEK` field under that name — mapping it there raised a live
error on all three (PostgreSQL "unit dayofweek not recognized", MySQL 1064,
Oracle `ORA-00907`) with no warning (`reda-ts-datepart-weekday`, class
`invalid`).

> **Note** faithful (QUARTER/WEEK — no crash, no carrier,
> same boundary-count value). **Warned** for WEEKDAY: the emitted value
> assumes the T-SQL default `@@DATEFIRST = 7` (week starts Sunday); a session
> that has changed `DATEFIRST` will see a different T-SQL result the transpiled
> output cannot track, since Unique has no visibility into session state.

**See Also.** Corpus [`reda-ts-datediff-quarter`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`reda-ts-datepart-weekday`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`pg-extract-dow`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestExtractFieldTranslation`](../../../tests/integration/test_challenge.py) (pinned) ·
`emit_functions.py::_emit_date_diff`, `emit_functions.py::_weekday_extract_expr`
· [`UNIQUE-1083`](../../reference/warnings.md#unique-1083).
