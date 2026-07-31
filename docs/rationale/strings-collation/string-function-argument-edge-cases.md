[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Repeat, substring and splice" direction="cross-engine" kind=article order=15 direction-inferred=true -->

# String-function positional-argument edge cases: negative `LEFT`, T-SQL `LEN` trailing spaces, MySQL fractional rounding

**Problem.** `LEFT`/`SUBSTRING`/`REPEAT`'s position and length arguments,
and T-SQL `LEN`, each have one engine-specific edge-case rule that a literal
translation would silently drop: PostgreSQL's `LEFT(s, -n)` means something
different from a plain clamp, T-SQL's `LEN` counts differently from every
other engine's length function, and MySQL rounds a fractional numeric
argument where the other engines truncate it.

**Solution.**

PostgreSQL's `LEFT(s, -n)` returns *"all but the last `|n|` characters"* —
not an error, not `''` — so translating it to MySQL (whose `LEFT` returns
`''` for any negative length) needs a rebase, not a clamp:

```sql
-- pg-left-neg, postgresql → mysql
SELECT LEFT('abc', -1) AS r;
-- =>
SELECT LEFT('abc', GREATEST(CHAR_LENGTH('abc') + -1, 0)) AS r;
```

`GREATEST(CHAR_LENGTH(s) + n, 0)` recovers the same "all but the last `|n|`"
result on MySQL (`'ab'` here), clamped to `0` only once the negative length
would exceed the string's own length. A *positive* length is never touched
by this rewrite.

T-SQL's `LEN` excludes trailing spaces (`LEN('abc   ')` = `3`); MySQL's
`CHAR_LENGTH` and Oracle/PostgreSQL's `LENGTH` count them (`6`). Going off
T-SQL, the argument is trimmed first so the count still matches:

```sql
-- ts-len-trailing, tsql → oracle / postgresql / mysql
SELECT LEN('abc   ') AS r;
-- => oracle / postgresql (the literal folds directly to T-SQL's value)
SELECT 3 AS r;
-- => a column argument keeps the runtime emulation
SELECT LENGTH(RTRIM(c)) AS r FROM t;
```

The reverse direction — Oracle/PostgreSQL's trailing-space-counting
`LENGTH` reaching T-SQL — appends a sentinel character before subtracting
it back off, since `LEN` itself cannot be told to stop trimming:

```sql
-- ora-length-trailing, oracle → tsql
SELECT LENGTH('abc   ') AS r FROM DUAL;
-- =>
SELECT LEN('abc   ' + '.') - 1 AS r;
```

MySQL rounds a fractional `SUBSTRING`/`LEFT`/`REPEAT` position or length
argument to the nearest integer; Oracle, T-SQL and PostgreSQL all truncate
it instead. A MySQL source with a literal fractional argument is
pre-rounded so every target keeps MySQL's own reading:

```sql
-- my-substr-float, mysql → oracle / tsql
SELECT SUBSTRING('hello', 2.9, 2.9) AS r;
-- => oracle
SELECT SUBSTR('hello', 3, 3) AS r FROM DUAL;
-- => tsql
SELECT SUBSTRING('hello', 3, 3) AS r;
```

The same rounding applies to `REPEAT`'s count argument, via T-SQL's
`REPLICATE`, which additionally needs the negative/zero clamp from the
sibling entry, [Negative/zero REPEAT/REPLICATE
clamps](repeat-replicate-clamps.md):

```sql
-- my-repeat-float, mysql → tsql
SELECT REPEAT('ab', 2.9) AS r;
-- =>
SELECT REPLICATE('ab', CASE WHEN ROUND(2.9, 0) < 0 THEN 0 ELSE ROUND(2.9, 0) END) AS r;
```

**Discussion.** These are three independent engine-specific argument rules,
not one mechanism, but they land in the same functions (`LEFT`,
`SUBSTRING`, `LEN`/`LENGTH`) and the same "pre-adjust the argument before
emitting the target's native call" shape: PostgreSQL's negative-`LEFT`
idiom has no equivalent keyword on MySQL, so the transpiler reconstructs
the *value* with an equivalent expression instead; T-SQL's `LEN` trims
trailing whitespace as part of its own definition (unrelated to any
locale/collation setting), so matching it elsewhere means trimming the
argument explicitly, and reproducing it *from* another engine means adding
back a non-space character so the count survives `LEN`'s own trim; MySQL's
argument-rounding (as opposed to truncation) is a numeric-coercion rule
specific to how MySQL casts a `DOUBLE` argument to the integer position
`SUBSTRING`/`REPEAT`/`LEFT` expect.

A literal fractional argument folds to its already-rounded value at
transpile time (as shown above); a non-literal (column or expression)
argument keeps the runtime `ROUND(...)`/`RTRIM(...)` wrapper instead, since
its value isn't known until execution.

> **Note** faithful — live-verified: `LEFT('abc', -1)` = `'ab'` on
> PostgreSQL and the rebased MySQL form; `LEN('abc   ')` = `3` and
> `LENGTH('abc   ' || '.') - 1` = `6` match across all four engines;
> `SUBSTRING('hello', 2.9, 2.9)` = `'llo'` on MySQL and the pre-rounded
> Oracle/T-SQL forms.

**See Also.** Corpus [`pg-left-neg`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`ts-len-trailing`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`ora-length-trailing`](../../../tests/fixtures/challenge/challenge_oracle.sql),
[`my-substr-float`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-repeat-float`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestPgLeftNegative`](../../../tests/integration/test_challenge.py),
[`TestTsqlLenTrailingSpaces`](../../../tests/integration/test_challenge.py),
[`TestSubstringFloatArgs`](../../../tests/integration/test_challenge.py),
[`TestNegativeLengthStringFns`](../../../tests/integration/test_challenge.py) ·
[Negative/zero REPEAT/REPLICATE clamps](repeat-replicate-clamps.md), for the
negative-count-to-empty-string half of the same functions.
