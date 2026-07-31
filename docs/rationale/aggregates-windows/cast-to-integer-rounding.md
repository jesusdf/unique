[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Numeric division, cast rounding, and zero-divisor semantics" direction="postgresql/mysql → tsql" kind=article order=13 -->

# `CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL

**Problem.** Casting a fractional value to an integer type rounds
half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` =
`8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's
`CAST`/`CONVERT` to an integer type always **truncates** (a plain
`CAST(2.7 AS INT)` would give `2`).

**Solution.**

```sql
-- corpus case pg-cast-int / pg-cast-round-half
SELECT CAST(2.7 AS INT) AS r    -- postgresql -> tsql: SELECT CAST(ROUND(2.7, 0) AS INT) AS r
SELECT 7.5 :: int AS r          -- postgresql -> tsql: SELECT CAST(ROUND(7.5, 0) AS INT) AS r

-- corpus case my-cast-int
SELECT CAST(2.7 AS SIGNED) AS r -- mysql -> tsql: SELECT CAST(ROUND(2.7, 0) AS BIGINT) AS r
```

Every fractional-literal `CAST(... AS <integer type>)` reaching a T-SQL
target is wrapped in `ROUND(x, 0)` before the cast (T-SQL's own `ROUND`
rounds half-away-from-zero, matching the source). A non-fractional literal
(`CAST(5 AS INT)`) is left untouched — no `ROUND` wrapper when there is
nothing to compensate.

**Discussion.** This is the mirror image of the division split above, but
for the cast operator instead of `/`: PostgreSQL's and MySQL's
numeric-to-integer casts round, T-SQL's truncates, and there is no `CAST`
variant on T-SQL that rounds instead — `ROUND` has to be composed in by
hand ahead of the truncating cast.

> **Note** faithful — live-verified `3`, not `2` (and `8`, not `7`,
> for the exact-half case).

**See Also.** [`pg-cast-int`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-cast-round-half`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`my-cast-int`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
`tests/integration/test_challenge.py` (`TestTsqlCastIntRounds`).
