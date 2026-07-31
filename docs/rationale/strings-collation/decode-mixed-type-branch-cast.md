[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="DECODE mixed-type branches" direction="oracle → postgresql/tsql/mysql" kind=article order=23 -->

# Oracle `DECODE` with mixed-type result branches → `CASE` with a `CAST` inserted to unify types

**Problem.** Oracle's `DECODE(expr, search1, result1, ..., default)`
tolerates result branches of different types — a string in one branch, a
number in another — since Oracle resolves the whole expression's type
loosely at runtime. `DECODE` translates to `CASE WHEN ... THEN ... END`
everywhere else, but PostgreSQL, T-SQL, and MySQL's `CASE` requires every
branch to share (or be implicitly convertible to) one common result type —
a mixed-type `CASE` is a compile-time type error on a target that enforces
it strictly.

**Solution.**

```sql
-- corpus case reda-ora-decode-mixed-type
SELECT DECODE(1, 1, 'a', 99) AS r
-- oracle -> postgresql:
SELECT CASE WHEN 1 = 1 THEN 'a' ELSE CAST(99 AS TEXT) END AS r;
-- oracle -> tsql:
SELECT CASE WHEN 1 = 1 THEN 'a' ELSE CAST(99 AS VARCHAR(4000)) END AS r
-- oracle -> mysql (looser CASE typing — no CAST needed):
SELECT CASE WHEN 1 = 1 THEN 'a' ELSE 99 END AS r;
```

**Discussion.** Unique reads the first non-`NULL` branch's result type as
the `CASE` expression's overall type, then inserts an explicit `CAST` on
every other branch whose own literal type differs, so the generated `CASE`
type-checks on a strict target the same way Oracle's own loosely-typed
`DECODE` already resolved. MySQL's `CASE` is lenient enough about mixed
literal types that no `CAST` is needed there — the same rewrite applies,
it just never needs the extra cast to satisfy MySQL's grammar.

> **Note** faithful — every branch still returns the same value Oracle's
> `DECODE` would have, just consistently typed as a string on the two
> strict targets; live-verified `'a'` for the matching branch, `'99'` for
> the default on PostgreSQL/T-SQL. No warning.

**See Also.** Corpus [`reda-ora-decode-mixed-type`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
`test_challenge_assertions_oracle.py` (`reda-ora-decode-mixed-type`).
