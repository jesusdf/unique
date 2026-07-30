# Aggregates and window functions

Window frames, ordered aggregates, string aggregation, `DISTINCT ON`, and
boolean aggregates — the constructs where "sum/count/rank a group of rows"
diverges most between engines. See [README.md](README.md) for the entry
format and sourcing rules.

## Window frame modes

### `GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL

**Source semantics.** `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND
CURRENT ROW)` frames the window by *peer groups* — every row sharing the same
`ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`)
or by value distance (`RANGE`).
**Why there is no direct mapping.** T-SQL and MySQL implement only the `ROWS`
and `RANGE` frame units (SQL:2011's `GROUPS` mode is missing entirely). When
the `ORDER BY` key has ties, a `GROUPS` frame spans a whole peer group at
once; no combination of `ROWS`/`RANGE` reproduces that boundary, so a rewrite
would silently change which rows are aggregated together.
**What Unique emits.** On T-SQL/MySQL the framed aggregate degrades to a
warned `NULL` carrier rather than emitting the invalid `GROUPS` clause
(T-SQL error 102 / MySQL error 1235). Oracle and PostgreSQL keep the native
`GROUPS` frame unchanged.
**Divergence & warning.** Not faithful on T-SQL/MySQL — the value is replaced
by a warned `NULL` carrier. Faithful on Oracle and PostgreSQL.
**References.** `pg-window-groups-frame` · `docs/03-unsupported.md` §3.25.

```sql
-- corpus case pg-window-groups-frame
SELECT x, SUM(x) OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) AS s
FROM (VALUES (1),(2),(2),(3)) v(x)
```

## Ordered aggregates

### Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL

**Source semantics.** `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an
**aggregate**, not a window function: it returns one row per group, taking
`x` from the row(s) whose `y` is the dense-rank extreme.
**Why there is no direct mapping.** None of the three targets has an
"aggregate keyed by another column's extremal rank" construct. The tempting
rewrite — a windowed `MAX(x) OVER (ORDER BY y)` — is a **different**
computation: it returns a running maximum on every input row, not one value
per group, so it silently changes both the row count and the result.
**What Unique emits.** The whole `KEEP (...)` expression is preserved as a
warned `UNIQUE:` carrier comment on every non-Oracle target, replacing the
earlier (incorrect) windowed rewrite.
**Divergence & warning.** Not faithful — no computed value is produced on
PostgreSQL/T-SQL/MySQL; the user must supply an equivalent manually. Faithful
on Oracle (native).
**References.** `reda-ora-keep-denserank` · `docs/03-unsupported.md` §3.3b.

```sql
-- corpus case reda-ora-keep-denserank
SELECT MAX(x) KEEP (DENSE_RANK LAST ORDER BY y) AS r
FROM (SELECT 10 x, 1 y FROM DUAL UNION ALL SELECT 20, 2 FROM DUAL
      UNION ALL SELECT 5, 2 FROM DUAL) t
-- Oracle (live): [(20)]. The old, now-replaced PG rewrite gave a running
-- max per row, [(10),(20),(20)] — a different result set entirely.
```

## Boolean aggregates and `FILTER`

### `bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle

**Source semantics.** `(a > 1)::int` and `bool_or(pred)` both need a
predicate's truth value used as an ordinary scalar (a `CAST` operand, or an
aggregate argument).
**Why there is no direct mapping.** T-SQL and Oracle have no boolean value
type: a predicate cannot appear as a `CAST` operand (T-SQL error 156, Oracle
`ORA-02000`) or as a bare aggregate argument.
**What Unique emits.** The predicate is wrapped in a `CASE WHEN … THEN 1 ELSE
0 END` — `CAST(a > 1 AS INT)` becomes `CASE WHEN a > 1 THEN 1 ELSE 0 END`.
**Divergence & warning.** Faithful (same integer value).
**References.** `pg-bool-to-int-cast`.

### `bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle

**Source semantics.** `bool_or(a > 5) FILTER (WHERE b = 1)` combines the
boolean-aggregate value wrapping above with `FILTER`'s
`agg(CASE WHEN cond THEN arg END)` rewrite in a single expression.
**Why there is no direct mapping.** Composing the two rewrites naively feeds
the FILTER `CASE`'s `THEN` branch the *raw* predicate (`a > 5`) instead of the
1/0-wrapped form, which T-SQL rejects the same way a bare `CAST` operand is
rejected (no boolean value type in a `CASE` `THEN` position).
**What Unique emits.** The 1/0 wrap is applied inside the `FILTER` rewrite's
`CASE`, so the emitted form contains `WHEN a > 5 THEN 1` (never a bare
`FILTER`/`bool_or` token) on T-SQL and Oracle.
**Divergence & warning.** Faithful — result 1 (true).
**References.** `pg-boolagg-filter` (component cases verified independently:
`pg-bool-to-int-cast`, and the FILTER-alone rewrite around
`pg-filter-subquery`).

```sql
-- corpus case pg-boolagg-filter
SELECT bool_or(a > 5) FILTER (WHERE b = 1) AS r
FROM (VALUES (10,1),(2,1),(3,2)) v(a,b)
-- T-SQL/Oracle: MAX(CAST(CASE WHEN b = 1 THEN CASE WHEN a > 5 THEN 1 ELSE 0 END END AS INT))
-- (pinned assertion checks "WHEN a > 5 THEN 1" present, "FILTER"/"bool_or" absent)
```

## `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

### `DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL

**Source semantics.** `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR
'-')` de-duplicates `x` and orders the *numeric* values before joining them.
**Why there is no direct mapping.** PostgreSQL's `STRING_AGG` requires its
`ORDER BY` key to equal the `DISTINCT`-ed argument. Casting `x` to `TEXT` (to
`DISTINCT`) and then ordering by that same text key sorts **lexically**
(`'10' < '2'`), not numerically — a different order than MySQL's.
**What Unique emits.** The `DISTINCT` is moved into a derived table
(`SELECT DISTINCT x FROM …`) so the outer `STRING_AGG` can `ORDER BY` the raw
numeric `x` directly, bounded to a single un-grouped aggregation (the same
restructuring `pg-distinct-on` uses).
**Divergence & warning.** Faithful — live-verified MySQL/PostgreSQL/Oracle =
`'10-2-1'`. Oracle (native `LISTAGG(DISTINCT …)`) and T-SQL (warned degrade,
`STRING_AGG` has no `DISTINCT`) are unaffected by this specific fix.
**References.** `my-groupconcat-distinct-numord`.

```sql
-- corpus case my-groupconcat-distinct-numord
SELECT GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-') AS g
FROM (SELECT 2 x UNION ALL SELECT 10 UNION ALL SELECT 1 UNION ALL SELECT 2) t
```

### `CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL

**Source semantics.** `string_agg(x::text, ',' ORDER BY x)` casts the
aggregate argument to `TEXT` before joining.
**Why there is no direct mapping.** Oracle's `LISTAGG` rejects a `CLOB`
argument and T-SQL's `STRING_AGG` rejects `TEXT`/`NTEXT` — both need a
bounded string type.
**What Unique emits.** The cast is portabilized to a bounded type per target:
`CAST(x AS VARCHAR2(4000))` on Oracle, `CAST(x AS NVARCHAR(MAX))` on T-SQL.
**Divergence & warning.** Faithful — live-verified `'1,2'`.
**References.** `pg-stragg-order`, `pg-string-agg-order`.

### `ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL

**Source semantics.** `ANY_VALUE(x)` returns an arbitrary (implementation
picked) value from the group — used to satisfy a functional-dependency
`GROUP BY` without an aggregate wrapper.
**Why there is no direct mapping.** T-SQL has no `ANY_VALUE` function and no
equivalent "pick one, unspecified which" aggregate.
**What Unique emits.** PostgreSQL 16+ keeps the native `ANY_VALUE` (the
sibling `GROUP_CONCAT`→`STRING_AGG` in the same statement works too, live
`(1,'1,2')`); T-SQL degrades the call to a documented carrier + warning.
**Divergence & warning.** `[limit]` on T-SQL — approved degrade, no faithful
substitute exists.
**References.** `my-any-value` · `docs/03-unsupported.md` §2.1 (unmapped
built-in scalar functions).

### Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL

**Source semantics.** Oracle allows `LISTAGG` to be used as a **window**
function (`OVER (PARTITION BY …)`), producing a running string aggregation —
one output row per input row, not one per group.
**Why there is no direct mapping.** T-SQL's `STRING_AGG` and MySQL's
`GROUP_CONCAT` can never appear with an `OVER` clause; PostgreSQL rejects an
`ORDER BY`-carrying aggregate used as a window function outright.
**What Unique emits.** Degrades to a `NULL` value plus an annotation carrier.
**Divergence & warning.** `[limit]` — approved degrade.
**References.** `ora-listagg-over` · `docs/03-unsupported.md` §2 (windowed
string aggregation row).

## `DISTINCT ON`

### PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle

**Source semantics.** `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b`
returns exactly **one** row per distinct `a` — the first one under the
`ORDER BY`.
**Why there is no direct mapping.** None of the other three engines has
`DISTINCT ON`. A plain `SELECT DISTINCT a, b` is not equivalent: it returns
every distinct `(a, b)` **pair**, not one row per `a` — a different row
count whenever a given `a` has more than one `b`.
**What Unique emits.** A `ROW_NUMBER() OVER (PARTITION BY a ORDER BY …) AS
uq_rn` derived table, filtered to `uq_rn = 1` in the outer query — reproduces
"one row per `a`, first by the given order" exactly.
**Divergence & warning.** Faithful — PG native = `[(1,10),(2,5)]`; the old
`SELECT DISTINCT` mistranslation gave `[(1,10),(1,20),(2,5),(2,7)]` on the
other three engines (a real defect this rewrite fixed).
**References.** `pg-distinct-on`.

```sql
-- corpus case pg-distinct-on
SELECT DISTINCT ON (a) a, b FROM (VALUES (1,10),(1,20),(2,5),(2,7)) v(a,b)
ORDER BY a, b
-- T-SQL/MySQL/Oracle: SELECT ... FROM (SELECT a, b,
--   ROW_NUMBER() OVER (PARTITION BY a ORDER BY b) AS uq_rn FROM ...) x
--   WHERE uq_rn = 1
```

## MySQL NULL-safe division (aggregate-adjacent)

### `SUM(x) / COUNT(x)` decimal + NULL-safe division (MySQL) → PostgreSQL / T-SQL

**Source semantics.** MySQL's `/` is always decimal division (two integers
still give a fractional result) and is NULL-safe: dividing by zero yields
`NULL` rather than raising.
**Why there is no direct mapping.** PostgreSQL and T-SQL truncate the
division of two integer operands (`SUM(x)/COUNT(x)` would silently floor to
an integer), and both **raise** on division by zero instead of returning
`NULL`. This is expression-level arithmetic, but it surfaces most often
around an aggregate divisor (`COUNT`), so it lives here rather than in
`dml.md`.
**What Unique emits.** The dividend is forced to decimal (`* 1.0`) and the
divisor is wrapped in `NULLIF(…, 0)`, giving
`SUM(x) * 1.0 / NULLIF(COUNT(x), 0)`. The `NULLIF` wrap is applied to every
MySQL-source `/` reaching a non-safe target (PostgreSQL/T-SQL/Oracle), not
only aggregate divisors.
**Divergence & warning.** Faithful — live-verified `1.5`.
**References.** `my-sum-div-count` · `tests/integration/test_challenge.py`
(`TestMysqlDecimalDivision`, `TestMysqlSafeDivision`).

```sql
-- corpus case my-sum-div-count
SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t
-- PostgreSQL/T-SQL: SUM(x) * 1.0 / NULLIF(COUNT(x), 0)
```

## Topics left out for lack of source support

- **CI-DISTINCT collation carrier inside the `GROUP_CONCAT`/`STRING_AGG`
  family specifically** — the corpus has a general case-insensitive-collation
  carrier for `DISTINCT`/`ORDER BY` (`my-distinct-case`,
  `docs/03-unsupported.md` §3.14), but no case combining it with a string
  aggregate's own `DISTINCT`/`ORDER BY` clause, so no dedicated entry is made
  here to avoid inventing an example.
