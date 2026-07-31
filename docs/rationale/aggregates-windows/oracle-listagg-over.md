[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family" direction="oracle → tsql/postgresql/mysql" kind=article order=9 -->

# Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL

**Problem.** Oracle allows `LISTAGG` to be used as a **window**
function (`OVER (PARTITION BY …)`), producing a running string aggregation —
one output row per input row, not one per group.

**Solution.** Degrades to a `NULL` value plus an annotation carrier.

**Discussion.** T-SQL's `STRING_AGG` and MySQL's
`GROUP_CONCAT` can never appear with an `OVER` clause; PostgreSQL rejects an
`ORDER BY`-carrying aggregate used as a window function outright.

> **Warning** `[limit]` — approved degrade.

**See Also.** [`ora-listagg-over`](../../../tests/fixtures/challenge/challenge_oracle.sql) · [§2](../../03-unsupported.md) (windowed
string aggregation row) · [`UNIQUE-1076`](../../reference/warnings.md#unique-1076).
