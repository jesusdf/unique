[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Portable row-source rewrites (PostgreSQL)" direction="postgresql → all" kind=article order=20 -->

# `FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)

**Problem.** PostgreSQL's `generate_series(start, stop[, step])` is a
set-returning function usable directly as a `FROM` item (or, via an
implicit lateral unnest, in the `SELECT` list) — a compact way to
manufacture one row per integer (or per date, with an `INTERVAL` step) in a
range.

**Solution.**

```sql
-- corpus case pg-srf-in-select
SELECT g, g*g FROM generate_series(1,3) g
-- Oracle:
SELECT g, g * g
FROM (SELECT (1) + (LEVEL - 1) AS g FROM DUAL CONNECT BY LEVEL <= (3) - (1) + 1) g;
-- T-SQL:
SELECT g, g * g
FROM (SELECT TOP ((3) - (1) + 1) (1) + (ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1) AS g
      FROM sys.all_objects) g
-- MySQL: whole-statement carrier + warning (UNIQUE-1003) — no table functions.

-- corpus case pg-bulk-insert (an INSERT ... SELECT source, same rewrite)
CREATE TABLE t (a INT); INSERT INTO t SELECT generate_series(1, 1000)
-- Oracle/T-SQL: the same CONNECT BY / sys.all_objects rewrite, live-executed
-- — 1000 rows land in t. MySQL: same UNIQUE-1003 carrier.
```

Oracle: a `CONNECT BY LEVEL <= <count>` walk from `DUAL`, offset by `start +
(LEVEL - 1)`. T-SQL: a `ROW_NUMBER() OVER (ORDER BY (SELECT NULL))` walk
over `sys.all_objects` (a system catalog with enough rows to cover any
practical range), capped with `TOP <count>` and offset the same way. Both
preserve `WITH ORDINALITY`'s row index as the `ROW_NUMBER()`/`LEVEL` itself
when requested, and a date-range call (`generate_series(date, date,
INTERVAL 'n' day)`) gets the same numeric walk with `DATE + (LEVEL-1)*n`
(Oracle) / `DATEADD(DAY, …, …)` (T-SQL) applied on top. MySQL has no
table-function/set-returning mechanism at all (`JSON_TABLE` cannot
manufacture rows from a range) and no recursive-CTE-in-`FROM` fallback, so
the whole statement degrades to a documented carrier.

**Discussion.** No target has a literal `generate_series` equivalent:
Oracle's row-generation idiom is the `CONNECT BY LEVEL` walk from `DUAL`;
T-SQL has no built-in numbers table, so Unique manufactures one from
`sys.all_objects`; MySQL has neither mechanism usable inline in `FROM`.

> **Note** faithful on Oracle/T-SQL — corpus `pg-srf-in-select` rows
> (1,1)/(2,4)/(3,9) live-verified; `pg-bulk-insert`'s 1000-row `INSERT …
> SELECT` live-executed. `[limit]` (warned carrier) on MySQL.

**See Also.** [`pg-srf-in-select`, `pg-bulk-insert`, `pg-gen-series-ord`,
`pg-gen-series-date`, `pg-generate-series`](../../../tests/fixtures/challenge/challenge_postgresql.sql)
· [`test_challenge.py::TestGenerateSeriesFrom`](../../../tests/integration/test_challenge.py).
