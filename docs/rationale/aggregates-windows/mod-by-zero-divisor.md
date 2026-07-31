[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Numeric division, cast rounding, and zero-divisor semantics" direction="mysql → tsql/oracle/postgresql" kind=article order=14 -->

# `MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle

**Problem.** MySQL's `MOD`/`%` returns `NULL` when the divisor is `0`
(`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a
division-by-zero error, and Oracle's `MOD` returns the **dividend**
unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same
input, all different from MySQL's.

**Solution.**

```sql
-- corpus case my-mod-zero
SELECT 5 MOD 0 IS NULL AS r
-- mysql -> oracle: CASE WHEN 0 = 0 THEN NULL ELSE MOD(5, 0) END IS NULL AS r
-- mysql -> tsql:   CASE WHEN 0 = 0 THEN NULL ELSE 5 % 0 END IS NULL AS r
```

The divisor is tested first: `CASE WHEN <divisor> = 0 THEN NULL ELSE
<native MOD/%> END`. The native operator only ever runs on a non-zero
divisor, so MySQL's `NULL` result is reproduced on every other target —
including Oracle, where the un-guarded native `MOD(5,0)` would otherwise
silently return `5`, flipping `IS NULL` from true to false.

**Discussion.** The guard is unconditional, even when the divisor is a
literal the transpiler could in principle prove non-zero at compile time
(`my-mod-edge`'s `MOD(0, 5)`, whose divisor is `5`) — a single uniform rule
that always emits the `CASE` is simpler than one that special-cases a
provably-safe literal, at the cost of one dead branch on those inputs.

> **Note** faithful — live-verified `5 MOD 0 IS NULL` is `1` on
> Oracle.

**See Also.** [`my-mod-zero`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-mod-edge`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
`tests/integration/test_challenge.py` (`TestMysqlModByZero`) ·
`tests/integration/test_challenge_assertions_mysql.py`.
