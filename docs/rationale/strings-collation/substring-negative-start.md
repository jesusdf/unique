[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Repeat, substring and splice" direction="cross-engine" kind=article order=8 direction-inferred=true -->

# SUBSTRING negative/zero start semantics per engine

**Problem.** T-SQL and PostgreSQL `SUBSTRING(s, start, len)` treat a
`start < 1` as counting *backwards from the length*: out-of-range leading
positions still consume `len`, they just don't emit characters for them.
`SUBSTRING('hello', 0, 3)` = `'he'` (positions 0, 1, 2 requested; position 0
doesn't exist, so only 1–2 are returned — 2 characters, not 3).

**Solution.**

```sql
-- reda-ts-substring-zero-start, tsql → mysql / oracle
SELECT SUBSTRING('hello', 0, 3) AS r;
-- => both targets
SELECT SUBSTR('hello', 1, 2) AS r;

-- pg-substr-zero, postgresql → mysql / oracle (same rebase, PG source)
SELECT SUBSTRING('abcdef', 0, 3) AS r;
-- =>
SELECT SUBSTR('abcdef', 1, 2) AS r;
```

A `start <= 0` argument is rebased to T-SQL/PostgreSQL
semantics for MySQL and Oracle: `start` becomes `1` and `len` is reduced by
`1 - start` (the count of out-of-range leading positions that no longer need
representing).

The 2-argument form (`SUBSTRING(s, start)`, no length) gets the equivalent
treatment: a `start <= 0` on PostgreSQL (which runs from the beginning) is
rewritten to an explicit `start = 1` for MySQL/Oracle/T-SQL, none of which
share PostgreSQL's "runs from the start" reading of an out-of-range start:

```sql
-- pg-fsubstr, postgresql → tsql / oracle / mysql
SELECT substring('abc', 0);
-- => tsql
SELECT SUBSTRING('abc', 1, LEN('abc'));
-- => oracle
SELECT SUBSTR('abc', 1) FROM DUAL;
-- => mysql
SELECT SUBSTR('abc', 1);
```

**Discussion.** MySQL's `SUBSTRING(s, 0, n)` treats
position `0` as simply invalid and returns `''` (empty). Oracle's `SUBSTR(s,
0, n)` instead **clamps** `0` up to `1` and returns `n` characters from
there — `SUBSTR('hello', 0, 3)` = `'hel'`. Three engines, three different
results for the same call shape, and the original code passed the call
through unchanged with no warning (`reda-ts-substring-zero-start`, class
`func`; live: tsql=`'he'`, pg=`'he'`, mysql=`''`, oracle=`'hel'`).

> **Note** faithful — live-verified `'he'` (tsql) / `'he'`
> (pg source) reproduced as `'he'` on MySQL/Oracle post-rebase (was `''` /
> `'hel'` before the fix); `('abc','abc','bc')` verified on all three for the
> 2-arg form. No warning.

**See Also.** Corpus [`reda-ts-substring-zero-start`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`pg-substr-zero`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-fsubstr`](../../../tests/fixtures/challenge/challenge_postgresql.sql) · [`TestPgSubstringZeroStart`](../../../tests/integration/test_challenge.py)
(pinned).

---
