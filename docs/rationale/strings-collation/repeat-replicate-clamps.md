[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Repeat, substring and splice" direction="cross-engine" kind=article order=7 direction-inferred=true -->

# Negative/zero REPEAT/REPLICATE clamps

**Problem.** PostgreSQL `repeat(s, n)` and MySQL `REPEAT(s, n)` with
`n <= 0` return an empty string `''`.

**Solution.**

```sql
-- pg-repeat-negative, postgresql → tsql
SELECT repeat('ab', -1) AS r;
-- =>
SELECT REPLICATE('ab', CASE WHEN ROUND(-1, 0) < 0 THEN 0 ELSE ROUND(-1, 0) END) AS r;
-- => oracle
SELECT '' /* UNIQUE: Oracle stores an empty string as NULL (docs/03-unsupported.md) */ AS r
FROM DUAL;
```

T-SQL clamps the count to `0` before calling
`REPLICATE` (`REPLICATE` of `0` is `''`, matching PostgreSQL); Oracle keeps
its own `RPAD` emulation and warns, since the Oracle-side result is `NULL`
either way (the `'' ≡ NULL` limit, not a clamp bug).

**Discussion.** T-SQL's `REPLICATE(s, n)` and the
`RPAD(s, LENGTH(s)*n, s)` emulation used for Oracle both return `NULL` for a
negative count, not `''` — a different value class entirely, and on Oracle,
compounded by Oracle's own `'' ≡ NULL` (above), so an Oracle target *cannot*
represent PostgreSQL/MySQL's `''` result distinctly from `NULL` regardless of
the clamp.

> **Note** faithful on T-SQL (clamped to `''`, matching
> PostgreSQL/MySQL). **Warned limit** on Oracle — not a clamp defect, the same
> `'' ≡ NULL` limit documented above.

**See Also.** Corpus [`pg-repeat-negative`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[§2](../../03-unsupported.md), "Empty string as a distinct value → Oracle" ·
[`UNIQUE-1082`](../../reference/warnings.md#unique-1082).

---
