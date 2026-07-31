[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Operator precedence" direction="postgresql/tsql → oracle/mysql" kind=article order=20 -->

# Unary bitwise `~x`/NOT → Oracle `-(x) - 1`, MySQL `CAST(~x AS SIGNED)`

**Problem.** PostgreSQL and T-SQL's unary bitwise NOT (`~x`) has no direct
spelling on Oracle at all (PL/SQL has no bitwise NOT operator or built-in),
and MySQL's `~x` operates on an *unsigned* 64-bit integer, so a plain `~5`
there returns a huge unsigned complement rather than the signed `-6` the
source engine intended.

**Solution.**

```sql
-- corpus cases pg-bitnot, pg-bit-negative, ts-bitops
SELECT ~5 AS r
-- postgresql/tsql -> oracle:
SELECT -(5) - 1 AS r FROM DUAL;
-- postgresql/tsql -> mysql:
SELECT CAST(~5 AS SIGNED) AS r;
```

**Discussion.** `-(x) - 1` is the two's-complement identity for bitwise
NOT expressed in plain arithmetic (`~x = -x - 1` for any integer `x`),
which Oracle can compute natively with no bitwise operator at all — the
same identity Oracle's binary `AND`/`OR` emulation (`BITAND`, and an
`OR`/`XOR` built from it) on this page's sibling entries already leans on.
MySQL keeps its own native `~` operator, but the *unsigned* result it
naturally produces is cast back to `SIGNED` to recover the two's-complement
negative value a PostgreSQL/T-SQL source expression expects.

> **Note** faithful — live-verified `~5` = `-6` on PostgreSQL/T-SQL;
> `-(5) - 1` = `-6` on Oracle, and `CAST(~5 AS SIGNED)` = `-6` on MySQL
> (its own bare `~5` would instead print as a large unsigned number). No
> warning.

**See Also.** Corpus [`pg-bitnot`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-bit-negative`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`test_challenge_assertions_postgresql.py` (`pg-bitnot`, `pg-bit-negative`),
`test_challenge_assertions_sqlserver.py` (`ts-bitops`) ·
[Bitwise/arithmetic operator-precedence parentheses](bitwise-arithmetic-precedence-parens.md)
(the sibling entry for binary bitwise operators' precedence, as opposed to
this unary operator's missing spelling).
