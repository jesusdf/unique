[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Empty-needle search guard" direction="mysql → tsql" kind=article order=24 direction-inferred=true -->

# MySQL `LOCATE('', s)` (always `1`) → T-SQL guarded `CASE`

**Problem.** MySQL's `LOCATE(needle, haystack)` special-cases an empty
needle: `LOCATE('', s)` is always `1`, regardless of `s`, treating the
empty string as matching at the very start. T-SQL's `CHARINDEX('',
haystack)` has no such special case — it returns `0` (not found) for an
empty needle on most engine versions, the opposite answer.

**Solution.**

```sql
-- corpus case my-locate-empty
SELECT LOCATE('', s) AS r FROM t
-- mysql -> tsql:
SELECT CASE WHEN '' = '' THEN 1 ELSE CHARINDEX('', s) END AS r
FROM t
```

**Discussion.** Rather than special-casing the literal empty string at
translation time (which would only help when the needle is a compile-time
constant), Unique emits a runtime guard: the `CASE` tests whether the
needle argument is empty and returns `1` directly when it is, falling back
to `CHARINDEX` unchanged otherwise — so the guard works identically whether
the needle is a literal or a column/variable whose value isn't known until
query time.

> **Note** faithful — live-verified `LOCATE('', 'abc') = 1` on MySQL,
> reproduced by the guarded `CASE` on T-SQL; a non-empty needle falls
> through to `CHARINDEX` unchanged, matching MySQL's own non-empty
> behavior. No warning.

**See Also.** Corpus [`my-locate-empty`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
`test_challenge_assertions_mysql.py` (`my-locate-empty`, `my-locate-empty2`).
