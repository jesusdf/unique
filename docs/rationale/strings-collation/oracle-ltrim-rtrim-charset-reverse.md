[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Trimming" direction="oracle → tsql/postgresql/mysql" kind=article order=22 -->

# Oracle `LTRIM(s, chars)`/`RTRIM(s, chars)` → `TRIM(LEADING/TRAILING chars FROM s)`

**Problem.** This is the reverse of [Character-set `TRIM(chars FROM
string)` → Oracle](trim-chars-from-string-to-oracle.md): Oracle's own
`LTRIM`/`RTRIM` already accept a multi-character trim set as their second
argument natively. T-SQL, PostgreSQL, and MySQL all support the same
one-sided trim through the standard `TRIM(LEADING|TRAILING chars FROM
string)` form instead of a positional `LTRIM(s, chars)` call — so an
Oracle-source `LTRIM`/`RTRIM` with a character-set argument needs
re-spelling, not just a name change, when the target isn't Oracle.

**Solution.**

```sql
-- corpus cases ora-ltrim-set, ora-rtrim-chars
SELECT LTRIM('xxabc', 'x') AS r
-- oracle -> tsql / postgresql / mysql:
SELECT TRIM(LEADING 'x' FROM 'xxabc') AS r

SELECT RTRIM('axxx', 'x') AS r
-- oracle -> tsql / postgresql / mysql:
SELECT TRIM(TRAILING 'x' FROM 'axxx') AS r
```

**Discussion.** `LTRIM`/`RTRIM` with no second argument (trimming plain
whitespace) is unaffected — this rewrite only fires when Oracle's
character-set argument is present, since a plain single-argument
`LTRIM(s)` already has an identical spelling on every target. The `LEADING`/
`TRAILING` keyword is chosen from which of the two functions was called,
reproducing the one-sided trim Oracle's own `LTRIM`/`RTRIM` names imply.

> **Note** faithful — live-verified `'hello'` from `LTRIM('xxhelloxx',
> 'x')` on Oracle, reproduced as `'hello'` by `TRIM(LEADING 'x' FROM
> 'xxhelloxx')` on every other target. No warning.

**See Also.** Corpus [`ora-ltrim-set`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`ora-rtrim-chars`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
`test_challenge_assertions_oracle.py` (`ora-ltrim-set`, `ora-rtrim-chars`,
`ora-trim-translate`) · [Character-set `TRIM(chars FROM string)` →
Oracle](trim-chars-from-string-to-oracle.md) (the forward direction this
mirrors).
