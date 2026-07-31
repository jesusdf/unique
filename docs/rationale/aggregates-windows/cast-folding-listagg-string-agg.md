[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family" direction="postgresql → tsql/oracle" kind=article order=7 -->

# `CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL

**Problem.** `string_agg(x::text, ',' ORDER BY x)` casts the
aggregate argument to `TEXT` before joining.

**Solution.** The cast is portabilized to a bounded type per target:
`CAST(x AS VARCHAR2(4000))` on Oracle, `CAST(x AS NVARCHAR(MAX))` on T-SQL.

**Discussion.** Oracle's `LISTAGG` rejects a `CLOB`
argument and T-SQL's `STRING_AGG` rejects `TEXT`/`NTEXT` — both need a
bounded string type.

> **Note** faithful — live-verified `'1,2'`.

**See Also.** [`pg-stragg-order`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-string-agg-order`](../../../tests/fixtures/challenge/challenge_postgresql.sql).
