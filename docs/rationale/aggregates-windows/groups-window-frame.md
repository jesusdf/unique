[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Window frame modes" direction="oracle/postgresql → tsql/mysql" kind=article order=1 -->

# `GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL

**Problem.** `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND
CURRENT ROW)` frames the window by *peer groups* — every row sharing the same
`ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`)
or by value distance (`RANGE`).

**Solution.**

```sql
-- corpus case pg-window-groups-frame
SELECT x, SUM(x) OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) AS s
FROM (VALUES (1),(2),(2),(3)) v(x)
```

On T-SQL/MySQL the framed aggregate degrades to a
warned `NULL` carrier rather than emitting the invalid `GROUPS` clause
(T-SQL error 102 / MySQL error 1235). Oracle and PostgreSQL keep the native
`GROUPS` frame unchanged.

**Discussion.** T-SQL and MySQL implement only the `ROWS`
and `RANGE` frame units (SQL:2011's `GROUPS` mode is missing entirely). When
the `ORDER BY` key has ties, a `GROUPS` frame spans a whole peer group at
once; no combination of `ROWS`/`RANGE` reproduces that boundary, so a rewrite
would silently change which rows are aggregated together.

> **Warning** Not faithful on T-SQL/MySQL — the value is replaced
> by a warned `NULL` carrier. Faithful on Oracle and PostgreSQL.

**See Also.** [`pg-window-groups-frame`](../../../tests/fixtures/challenge/challenge_postgresql.sql) · [§3.25](../../03-unsupported.md) ·
[`UNIQUE-1077`](../../reference/warnings.md#unique-1077).
