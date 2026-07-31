[← Date/time arithmetic and formatting](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=datetime type="Truncation and unit maps" direction="postgresql → tsql/oracle" kind=article order=3 -->

# PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week

**Problem.** PostgreSQL `date_trunc('week', ts)` truncates to the
start of the ISO week — **Monday** — and `date_trunc('quarter', ts)` to the
first day of the quarter. Oracle's own `TRUNC(date, fmt)` and T-SQL's
`DATETRUNC` (2022+) spell the same units differently.

**Solution.**

```sql
-- pg-date-trunc-week, postgresql → oracle / tsql
SELECT date_trunc('week', DATE '2020-06-17') AS d;
-- => oracle
SELECT TRUNC(DATE '2020-06-17', 'IW') AS d FROM DUAL;
-- => tsql
SELECT DATETRUNC(ISO_WEEK, CAST('2020-06-17' AS DATE)) AS d;
```

Each PostgreSQL `DATE_TRUNC` unit maps to Oracle's valid `TRUNC` code —
`'week'` → `'IW'` (the ISO, Monday-based week, matching PostgreSQL) — and to
T-SQL's `DATETRUNC` part, substituting `ISO_WEEK` for `week` so the
Sunday/Monday mismatch does not leak through.

The same mapping backs `EXTRACT(WEEK|QUARTER FROM …)` /
`DATE_PART`: Oracle's `EXTRACT` rejects both `WEEK` and `QUARTER`, so they
route through `TO_CHAR(d, 'IW'|'Q')` instead; MySQL's native
`EXTRACT(WEEK)` follows the DBMS's `default_week_format` (off by one from
ISO) and T-SQL's `DATEPART(WEEK)` is `@@DATEFIRST`-dependent, so both are
overridden with an explicit ISO form (`WEEK(d, 3)` mode 3 = ISO 8601 /
`DATEPART(ISO_WEEK, d)`):

```sql
-- pg-date-part, postgresql → oracle / mysql / tsql
SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15');
-- => oracle
SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'IW')), TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'Q')) FROM DUAL;
-- => mysql
SELECT WEEK(CAST('2020-06-15' AS DATE), 3), ...
-- => tsql
SELECT DATEPART(ISO_WEEK, CAST('2020-06-15' AS DATE)), ...
```

**Discussion.** Oracle's `TRUNC` format models are not
PostgreSQL's spelling: `TRUNC(d, 'WEEK')` raises `ORA-01898` (invalid format
model) and `TRUNC(d, 'QUARTER')`/`'MINUTE'` raise `ORA-01821`. T-SQL's
`DATETRUNC(week, …)` starts the week on **Sunday**, one day off PostgreSQL's
Monday-based ISO week, so a bare unit copy silently returns the wrong date
(`2020-06-14` instead of `2020-06-15` for `date_trunc('week', DATE
'2020-06-17')`).

> **Note** faithful — live-verified equal on all four
> engines, including the ISO year-boundary edge case (`pg-week-2016`:
> `2016-01-01` is ISO week 53 of 2015 on PostgreSQL/MySQL/T-SQL once forced to
> the ISO form). MySQL's `date_trunc('week', …)` equivalent (no native
> truncation unit) is built from `WEEKDAY()` instead (Monday=0) and is likewise
> faithful. No warning.

**See Also.** Corpus [`pg-date-trunc-week`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-date-part`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-week`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-week-2016`](../../../tests/fixtures/challenge/challenge_postgresql.sql) · [`TestExtractFieldTranslation`](../../../tests/integration/test_challenge.py)
(pinned) · `emit_functions.py:2338-2419` (docstring, "Date truncation").

---
