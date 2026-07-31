[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Trimming" direction="cross-engine" kind=article order=9 direction-inferred=true -->

# Character-set `TRIM(chars FROM string)` → Oracle

**Problem.** `TRIM([BOTH|LEADING|TRAILING] chars FROM string)` strips every
occurrence of any character in `chars` from the string (both ends by
default). MySQL, PostgreSQL and T-SQL (2022+) all accept an arbitrary
multi-character `chars` set this way; MySQL additionally accepts the same
call spelled `TRIM(chars, string)`.

**Solution.**

```sql
-- TRIM(chars FROM string), mysql → oracle
SELECT TRIM('x' FROM col) FROM t1;
-- =>
SELECT LTRIM(RTRIM(col, 'x'), 'x')
FROM t1;

-- same source, mysql → tsql (native pass-through)
SELECT TRIM('x' FROM col) FROM t1;
```

For an Oracle target only, the call is rewritten to nested `LTRIM(RTRIM(col,
set), set)`; a `LEADING`/`TRAILING`-only call rewrites to a single
`LTRIM`/`RTRIM` instead. Every other target keeps the native `TRIM(chars
FROM string)` spelling untouched.

**Discussion.** Oracle's own `TRIM(BOTH char FROM string)` accepts only a
**single** trim character — a multi-character set raises `ORA-30001` ("this
function requires a single character trim set"). `LTRIM`/`RTRIM`, by
contrast, treat their second argument as a genuine multi-character set on
every engine, matching MySQL/PostgreSQL/T-SQL's `TRIM(chars FROM …)` reading
exactly — nesting the two sidesteps the Oracle-only single-character
restriction rather than working around a missing feature. The rewrite
applies whenever the **target** is Oracle, regardless of the source
dialect — MySQL, PostgreSQL and T-SQL source forms all route through the
same nested `LTRIM`/`RTRIM` rewrite when targeting Oracle.

> **Note** faithful — live-verified `'hello'` from `TRIM('x' FROM
> 'xxhelloxx')` on MySQL, reproduced as `'hello'` by `LTRIM(RTRIM('xxhelloxx',
> 'x'), 'x')` on Oracle. No warning.

**See Also.** [`TestWave188IfBareCondTrimTwoArg::test_two_arg_trim_oracle`](../../../tests/integration/test_pg_source_wave1.py)
(pinned; an inline MySQL-source fixture, not a `challenge_*.sql` corpus case) ·
`emit_functions.py:2124-2146` (docstring).

---
