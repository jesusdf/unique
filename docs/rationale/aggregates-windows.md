# Aggregates and window functions

Window frames, ordered aggregates, string aggregation, `DISTINCT ON`, and
boolean aggregates — the constructs where "sum/count/rank a group of rows"
diverges most between engines. See [README.md](README.md) for the entry
format and sourcing rules.

## Window frame modes

### `GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL

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

**See Also.** [`pg-window-groups-frame`](../../tests/fixtures/challenge/challenge_postgresql.sql) · [§3.25](../03-unsupported.md) ·
[`UNIQUE-1077`](../reference/warnings.md#unique-1077).

## Ordered aggregates

### Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL

**Problem.** `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an
**aggregate**, not a window function: it returns one row per group, taking
`x` from the row(s) whose `y` is the dense-rank extreme.

**Solution.**

```sql
-- corpus case reda-ora-keep-denserank
SELECT MAX(x) KEEP (DENSE_RANK LAST ORDER BY y) AS r
FROM (SELECT 10 x, 1 y FROM DUAL UNION ALL SELECT 20, 2 FROM DUAL
      UNION ALL SELECT 5, 2 FROM DUAL) t
-- Oracle (live): [(20)]. The old, now-replaced PG rewrite gave a running
-- max per row, [(10),(20),(20)] — a different result set entirely.
```

The whole `KEEP (...)` expression is preserved as a
warned `UNIQUE:` carrier comment on every non-Oracle target, replacing the
earlier (incorrect) windowed rewrite.

**Discussion.** None of the three targets has an
"aggregate keyed by another column's extremal rank" construct. The tempting
rewrite — a windowed `MAX(x) OVER (ORDER BY y)` — is a **different**
computation: it returns a running maximum on every input row, not one value
per group, so it silently changes both the row count and the result.

> **Warning** Not faithful — no computed value is produced on
> PostgreSQL/T-SQL/MySQL; the user must supply an equivalent manually. Faithful
> on Oracle (native).

**See Also.** [`reda-ora-keep-denserank`](../../tests/fixtures/challenge/challenge_oracle.sql) · [§3.3b](../03-unsupported.md).

## Boolean aggregates and `FILTER`

### `agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle

**Problem.** PostgreSQL's `FILTER (WHERE p)` restricts which rows an
aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y >
5`) without a separate subquery or `CASE`; none of the other three engines
parse the clause at all (T-SQL error 102, "incorrect syntax").

**Solution.**

```sql
-- test_pg_source_wave1.py::TestAggregateFilterRewrite
select count(*) filter (where c <> 0) from t;
-- -> tsql: SELECT COUNT(CASE WHEN c <> 0 THEN 1 END) FROM t

select sum(x) filter (where y > 5) from t;
-- -> mysql / oracle: SELECT SUM(CASE WHEN y > 5 THEN x END) FROM t
```

Every `agg(x) FILTER (WHERE p)` rewrites to `agg(CASE WHEN p THEN x
END)` — the `CASE`'s implicit `ELSE NULL` reproduces "this row is excluded
from the aggregate" for any aggregate that already ignores `NULL` (`SUM`,
`COUNT`, `AVG`, `MIN`, `MAX`, …). `COUNT(*) FILTER (WHERE p)` has no column
to guard, so the `CASE`'s `THEN` branch counts a literal `1` instead.

**Discussion.** T-SQL, MySQL, and Oracle all reject `FILTER` as a syntax
error at parse time — there is no native spelling to fall back to on any of
them. The `CASE`-wrap rewrite works because every standard aggregate already
treats a `NULL` input as "not counted," so feeding it `NULL` on the
filtered-out rows is exactly equivalent to never seeing those rows at all.

> **Note** faithful — same aggregate value; corpus case
> `pg-filter-subquery` (`COUNT(*) FILTER` against a correlated-subquery
> threshold) is the standalone FILTER-alone case this rewrite is built from,
> and the `bool_or(...) FILTER (...)` entry below composes it with a second,
> independent rewrite.

**See Also.** [`pg-filter-subquery`](../../tests/fixtures/challenge/challenge_postgresql.sql) · `tests/integration/test_pg_source_wave1.py` (`TestAggregateFilterRewrite`).

### `bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle

**Problem.** `(a > 1)::int` and `bool_or(pred)` both need a
predicate's truth value used as an ordinary scalar (a `CAST` operand, or an
aggregate argument).

**Solution.** The predicate is wrapped in a `CASE WHEN … THEN 1 ELSE
0 END` — `CAST(a > 1 AS INT)` becomes `CASE WHEN a > 1 THEN 1 ELSE 0 END`.

**Discussion.** T-SQL and Oracle have no boolean value
type: a predicate cannot appear as a `CAST` operand (T-SQL error 156, Oracle
`ORA-02000`) or as a bare aggregate argument.

> **Note** faithful (same integer value).

**See Also.** [`pg-bool-to-int-cast`](../../tests/fixtures/challenge/challenge_postgresql.sql).

### `bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle

**Problem.** `bool_or(a > 5) FILTER (WHERE b = 1)` combines the
boolean-aggregate value wrapping above with `FILTER`'s
`agg(CASE WHEN cond THEN arg END)` rewrite in a single expression.

**Solution.**

```sql
-- corpus case pg-boolagg-filter
SELECT bool_or(a > 5) FILTER (WHERE b = 1) AS r
FROM (VALUES (10,1),(2,1),(3,2)) v(a,b)
-- T-SQL/Oracle: MAX(CAST(CASE WHEN b = 1 THEN CASE WHEN a > 5 THEN 1 ELSE 0 END END AS INT))
-- (pinned assertion checks "WHEN a > 5 THEN 1" present, "FILTER"/"bool_or" absent)
```

The 1/0 wrap is applied inside the `FILTER` rewrite's
`CASE`, so the emitted form contains `WHEN a > 5 THEN 1` (never a bare
`FILTER`/`bool_or` token) on T-SQL and Oracle.

**Discussion.** Composing the two rewrites naively feeds
the FILTER `CASE`'s `THEN` branch the *raw* predicate (`a > 5`) instead of the
1/0-wrapped form, which T-SQL rejects the same way a bare `CAST` operand is
rejected (no boolean value type in a `CASE` `THEN` position).

> **Note** faithful — result 1 (true).

**See Also.** [`pg-boolagg-filter`](../../tests/fixtures/challenge/challenge_postgresql.sql) (component cases verified independently:
[`pg-bool-to-int-cast`](../../tests/fixtures/challenge/challenge_postgresql.sql), and the FILTER-alone rewrite around
[`pg-filter-subquery`](../../tests/fixtures/challenge/challenge_postgresql.sql)).

## `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

### `DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL

**Problem.** `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR
'-')` de-duplicates `x` and orders the *numeric* values before joining them.

**Solution.**

```sql
-- corpus case my-groupconcat-distinct-numord
SELECT GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-') AS g
FROM (SELECT 2 x UNION ALL SELECT 10 UNION ALL SELECT 1 UNION ALL SELECT 2) t
```

The `DISTINCT` is moved into a derived table
(`SELECT DISTINCT x FROM …`) so the outer `STRING_AGG` can `ORDER BY` the raw
numeric `x` directly, bounded to a single un-grouped aggregation (the same
restructuring `pg-distinct-on` uses).

**Discussion.** PostgreSQL's `STRING_AGG` requires its
`ORDER BY` key to equal the `DISTINCT`-ed argument. Casting `x` to `TEXT` (to
`DISTINCT`) and then ordering by that same text key sorts **lexically**
(`'10' < '2'`), not numerically — a different order than MySQL's.

> **Note** faithful — live-verified MySQL/PostgreSQL/Oracle =
> `'10-2-1'`. Oracle (native `LISTAGG(DISTINCT …)`) and T-SQL (warned degrade,
> `STRING_AGG` has no `DISTINCT`) are unaffected by this specific fix.

**See Also.** [`my-groupconcat-distinct-numord`](../../tests/fixtures/challenge/challenge_mysql.sql).

### `CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL

**Problem.** `string_agg(x::text, ',' ORDER BY x)` casts the
aggregate argument to `TEXT` before joining.

**Solution.** The cast is portabilized to a bounded type per target:
`CAST(x AS VARCHAR2(4000))` on Oracle, `CAST(x AS NVARCHAR(MAX))` on T-SQL.

**Discussion.** Oracle's `LISTAGG` rejects a `CLOB`
argument and T-SQL's `STRING_AGG` rejects `TEXT`/`NTEXT` — both need a
bounded string type.

> **Note** faithful — live-verified `'1,2'`.

**See Also.** [`pg-stragg-order`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-string-agg-order`](../../tests/fixtures/challenge/challenge_postgresql.sql).

### `ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL

**Problem.** `ANY_VALUE(x)` returns an arbitrary (implementation
picked) value from the group — used to satisfy a functional-dependency
`GROUP BY` without an aggregate wrapper.

**Solution.** PostgreSQL 16+ keeps the native `ANY_VALUE` (the
sibling `GROUP_CONCAT`→`STRING_AGG` in the same statement works too, live
`(1,'1,2')`); T-SQL degrades the call to a documented carrier + warning.

**Discussion.** T-SQL has no `ANY_VALUE` function and no
equivalent "pick one, unspecified which" aggregate.

> **Warning** `[limit]` on T-SQL — approved degrade, no faithful
> substitute exists.

**See Also.** [`my-any-value`](../../tests/fixtures/challenge/challenge_mysql.sql) · [§2.1](../03-unsupported.md) (unmapped
built-in scalar functions).

### Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL

**Problem.** Oracle allows `LISTAGG` to be used as a **window**
function (`OVER (PARTITION BY …)`), producing a running string aggregation —
one output row per input row, not one per group.

**Solution.** Degrades to a `NULL` value plus an annotation carrier.

**Discussion.** T-SQL's `STRING_AGG` and MySQL's
`GROUP_CONCAT` can never appear with an `OVER` clause; PostgreSQL rejects an
`ORDER BY`-carrying aggregate used as a window function outright.

> **Warning** `[limit]` — approved degrade.

**See Also.** [`ora-listagg-over`](../../tests/fixtures/challenge/challenge_oracle.sql) · [§2](../03-unsupported.md) (windowed
string aggregation row) · [`UNIQUE-1076`](../reference/warnings.md#unique-1076).

## `DISTINCT ON`

### PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle

**Problem.** `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b`
returns exactly **one** row per distinct `a` — the first one under the
`ORDER BY`.

**Solution.**

```sql
-- corpus case pg-distinct-on
SELECT DISTINCT ON (a) a, b FROM (VALUES (1,10),(1,20),(2,5),(2,7)) v(a,b)
ORDER BY a, b
-- T-SQL/MySQL/Oracle: SELECT ... FROM (SELECT a, b,
--   ROW_NUMBER() OVER (PARTITION BY a ORDER BY b) AS uq_rn FROM ...) x
--   WHERE uq_rn = 1
```

A `ROW_NUMBER() OVER (PARTITION BY a ORDER BY …) AS
uq_rn` derived table, filtered to `uq_rn = 1` in the outer query — reproduces
"one row per `a`, first by the given order" exactly.

**Discussion.** None of the other three engines has
`DISTINCT ON`. A plain `SELECT DISTINCT a, b` is not equivalent: it returns
every distinct `(a, b)` **pair**, not one row per `a` — a different row
count whenever a given `a` has more than one `b`.

> **Note** faithful — PG native = `[(1,10),(2,5)]`; the old
> `SELECT DISTINCT` mistranslation gave `[(1,10),(1,20),(2,5),(2,7)]` on the
> other three engines (a real defect this rewrite fixed).

**See Also.** [`pg-distinct-on`](../../tests/fixtures/challenge/challenge_postgresql.sql).

## Numeric division, cast rounding, and zero-divisor semantics

Three related but distinct per-engine divergences around plain arithmetic,
gathered here because an aggregate divisor (`SUM(x)/COUNT(x)`) is the most
common place they surface, even though the compensation applies to any
division or cast, aggregate or not.

### Integer-truncating vs. decimal division (cross-engine)

**Problem.** `/` truncates two integer operands to an integer on
PostgreSQL and T-SQL (`5 / 2` is `2`), but MySQL and Oracle always return a
decimal (`5 / 2` is `2.5`) — crossing that line without compensation
silently changes the value. `AVG` is division in disguise for the same
purpose: T-SQL's `AVG` returns the argument's own type, so `AVG` over an
integer column truncates *before* dividing (`AVG(1,2)` = `1`, not `1.5`)
while MySQL/Oracle/PostgreSQL always average as decimal.

**Solution.**

```sql
-- literal operands
SELECT 5 / 2 AS r
-- postgresql -> mysql:  SELECT (5 DIV 2) AS r;
-- postgresql -> oracle: SELECT TRUNC(5 / 2) AS r FROM DUAL;
-- mysql -> postgresql:  SELECT (5 * 1.0 / NULLIF(2, 0)) AS r;
-- oracle -> tsql:       SELECT (5 * 1.0 / 2) AS r

-- declared integer variables (test_func_compensation.py::test_integer_division_declared_variables_procedural)
CREATE PROCEDURE p AS BEGIN DECLARE @a INT; DECLARE @b INT; DECLARE @r INT; SET @r = @a / @b; END
-- tsql -> oracle: V_R := TRUNC(V_A / V_B);
-- tsql -> mysql:  SET v_r = (v_a DIV v_b);

-- corpus case my-avg-int / pg-avg-int
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t
-- mysql/postgresql -> tsql: SELECT AVG((x) * 1.0) FROM (...) t
```

Going from an integer-truncating source to a decimal-only engine
compensates by truncating the *target* too (`DIV` on MySQL, `TRUNC(...)` on
Oracle); going the other way forces the dividend decimal (`* 1.0`) so the
target's own truncation never fires. The same `* 1.0` promotion is applied
to an `AVG` argument whenever the source always averages as decimal and the
target is T-SQL. MySQL's `/` also never raises on a zero divisor (`x / 0` is
`NULL`, not an error); that NULL-safety is preserved on every other target
by wrapping the divisor in `NULLIF(divisor, 0)`, independent of whether the
division is an aggregate's own divisor or an ordinary expression — the two
compensations combine additively when both apply:

```sql
-- corpus case my-sum-div-count
SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t
-- mysql -> postgresql/tsql: SUM(x) * 1.0 / NULLIF(COUNT(x), 0)

-- test_challenge.py::TestMysqlSafeDivision
SELECT a / b FROM t
-- mysql -> oracle: SELECT a / NULLIF(b, 0) FROM t;              -- Oracle already divides as decimal, only the guard is needed
-- mysql -> tsql:   SELECT (a * 1.0 / NULLIF(b, 0)) FROM t       -- T-SQL truncates too, so both compensations apply
```

**Discussion.** Three independent per-engine behaviors compose here:
whether `/` truncates or floats (PostgreSQL and T-SQL truncate; MySQL and
Oracle always float), whether `AVG` inherits its argument's type (T-SQL
only) or always averages as decimal (the other three), and whether division
by zero raises (PostgreSQL/T-SQL/Oracle) or returns `NULL` (MySQL only).
Each is read off the source dialect and compensated independently per
target; for a literal-operand division no schema is needed, and inside a
procedure body the same compensation applies to a declared integer
*variable* once its type is known from the `DECLARE`.

> **Note** faithful — `my-sum-div-count` live-verified `1.5`;
> `test_func_compensation.py`'s literal and declared-variable division tests
> pin the exact value on both sides of the truncating/decimal split;
> `TestMysqlSafeDivision` pins the NULL-safety preservation (and the
> guardrail-7 unread-args false-warning this also silences); `my-avg-int` /
> `pg-avg-int` / `my-avg-precision2` pin the `AVG` promotion.

**See Also.** [`my-sum-div-count`](../../tests/fixtures/challenge/challenge_mysql.sql), [`my-avg-int`](../../tests/fixtures/challenge/challenge_mysql.sql), [`my-avg-precision2`](../../tests/fixtures/challenge/challenge_mysql.sql), [`pg-avg-int`](../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`tests/integration/test_func_compensation.py` (`test_integer_division_literals_preserved`, `test_integer_division_declared_variables_procedural`) ·
`tests/integration/test_challenge.py` (`TestMysqlDecimalDivision`, `TestMysqlSafeDivision`, `TestTsqlAvgIntegerPromotion`).

### `CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL

**Problem.** Casting a fractional value to an integer type rounds
half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` =
`8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's
`CAST`/`CONVERT` to an integer type always **truncates** (a plain
`CAST(2.7 AS INT)` would give `2`).

**Solution.**

```sql
-- corpus case pg-cast-int / pg-cast-round-half
SELECT CAST(2.7 AS INT) AS r    -- postgresql -> tsql: SELECT CAST(ROUND(2.7, 0) AS INT) AS r
SELECT 7.5 :: int AS r          -- postgresql -> tsql: SELECT CAST(ROUND(7.5, 0) AS INT) AS r

-- corpus case my-cast-int
SELECT CAST(2.7 AS SIGNED) AS r -- mysql -> tsql: SELECT CAST(ROUND(2.7, 0) AS BIGINT) AS r
```

Every fractional-literal `CAST(... AS <integer type>)` reaching a T-SQL
target is wrapped in `ROUND(x, 0)` before the cast (T-SQL's own `ROUND`
rounds half-away-from-zero, matching the source). A non-fractional literal
(`CAST(5 AS INT)`) is left untouched — no `ROUND` wrapper when there is
nothing to compensate.

**Discussion.** This is the mirror image of the division split above, but
for the cast operator instead of `/`: PostgreSQL's and MySQL's
numeric-to-integer casts round, T-SQL's truncates, and there is no `CAST`
variant on T-SQL that rounds instead — `ROUND` has to be composed in by
hand ahead of the truncating cast.

> **Note** faithful — live-verified `3`, not `2` (and `8`, not `7`,
> for the exact-half case).

**See Also.** [`pg-cast-int`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`pg-cast-round-half`](../../tests/fixtures/challenge/challenge_postgresql.sql), [`my-cast-int`](../../tests/fixtures/challenge/challenge_mysql.sql) ·
`tests/integration/test_challenge.py` (`TestTsqlCastIntRounds`).

### `MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle

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

**See Also.** [`my-mod-zero`](../../tests/fixtures/challenge/challenge_mysql.sql), [`my-mod-edge`](../../tests/fixtures/challenge/challenge_mysql.sql) ·
`tests/integration/test_challenge.py` (`TestMysqlModByZero`) ·
`tests/integration/test_challenge_assertions_mysql.py`.

## Topics left out for lack of source support

- **CI-DISTINCT collation carrier inside the `GROUP_CONCAT`/`STRING_AGG`
  family specifically** — the corpus has a general case-insensitive-collation
  carrier for `DISTINCT`/`ORDER BY` (`my-distinct-case`,
  `docs/03-unsupported.md` §3.14), but no case combining it with a string
  aggregate's own `DISTINCT`/`ORDER BY` clause, so no dedicated entry is made
  here to avoid inventing an example.
