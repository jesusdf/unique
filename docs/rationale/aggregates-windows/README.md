[← All rationale topics](../README.md)

# Aggregates and window functions

Window frames, ordered aggregates, string aggregation, `DISTINCT ON`, and
boolean aggregates — the constructs where "sum/count/rank a group of rows"
diverges most between engines. See [README.md](../README.md) for the entry
format and sourcing rules.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## By engine

Each article grouped by the engine it converts **from** and **to** (derived from the `direction` metadata). Cross-engine articles — no single source/target — are listed once at the end.

| Engine | As source | As target |
|---|---|---|
| T-SQL | [as source](#t-sql-as-source) | [as target](#t-sql-as-target) |
| Oracle | [as source](#oracle-as-source) | [as target](#oracle-as-target) |
| PostgreSQL | [as source](#postgresql-as-source) | [as target](#postgresql-as-target) |
| MySQL | [as source](#mysql-as-source) | [as target](#mysql-as-target) |
| Cross-engine | [multi-directional](#cross-engine--multi-directional) |  |

### T-SQL as source

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](tsql-cast-int-truncation-reverse.md) | tsql → postgresql/oracle/mysql | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

### T-SQL as target

| [Window frame modes](#window-frame-modes) | [Ordered aggregates](#ordered-aggregates) | [Boolean aggregates and `FILTER`](#boolean-aggregates-and-filter) | [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family) | [`DISTINCT ON`](#distinct-on) | [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-1) |
|---|---|---|---|---|---|

#### Window frame modes

| Article | Direction | Description |
|---|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](groups-window-frame.md) | oracle/postgresql → tsql/mysql | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |

#### Ordered aggregates

| Article | Direction | Description |
|---|---|---|
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](oracle-keep-dense-rank.md) | oracle → tsql/postgresql/mysql | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |

#### Boolean aggregates and `FILTER`

| Article | Direction | Description |
|---|---|---|
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](filter-clause.md) | postgresql → tsql/oracle/mysql | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](bool-or-and-value-wrapping.md) | postgresql → tsql/oracle | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](bool-or-filter-composition.md) | postgresql → tsql/oracle | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](cast-folding-listagg-string-agg.md) | postgresql → tsql/oracle | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](any-value-to-tsql.md) | postgresql/mysql → tsql | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](oracle-listagg-over.md) | oracle → tsql/postgresql/mysql | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |

#### `DISTINCT ON`

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](distinct-on.md) | postgresql → tsql/oracle/mysql | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](cast-to-integer-rounding.md) | postgresql/mysql → tsql | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](mod-by-zero-divisor.md) | mysql → tsql/oracle/postgresql | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |

### Oracle as source

| [Window frame modes](#window-frame-modes-1) | [Ordered aggregates](#ordered-aggregates-1) | [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family-1) |
|---|---|---|

#### Window frame modes

| Article | Direction | Description |
|---|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](groups-window-frame.md) | oracle/postgresql → tsql/mysql | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |

#### Ordered aggregates

| Article | Direction | Description |
|---|---|---|
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](oracle-keep-dense-rank.md) | oracle → tsql/postgresql/mysql | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](oracle-listagg-over.md) | oracle → tsql/postgresql/mysql | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |

### Oracle as target

| [Boolean aggregates and `FILTER`](#boolean-aggregates-and-filter-1) | [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family-2) | [`DISTINCT ON`](#distinct-on-1) | [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-2) |
|---|---|---|---|

#### Boolean aggregates and `FILTER`

| Article | Direction | Description |
|---|---|---|
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](filter-clause.md) | postgresql → tsql/oracle/mysql | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](bool-or-and-value-wrapping.md) | postgresql → tsql/oracle | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](bool-or-filter-composition.md) | postgresql → tsql/oracle | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](cast-folding-listagg-string-agg.md) | postgresql → tsql/oracle | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [An unordered MySQL `GROUP_CONCAT` → Oracle `LISTAGG` gains a synthesized `WITHIN GROUP (ORDER BY <arg>)`](group-concat-synthesized-within-group-oracle.md) | mysql → oracle | MySQL's `GROUP_CONCAT(expr SEPARATOR sep)` needs no ordering clause — an unordered call is valid MySQL, with whatever order the engine happens to produce. |

#### `DISTINCT ON`

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](distinct-on.md) | postgresql → tsql/oracle/mysql | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](mod-by-zero-divisor.md) | mysql → tsql/oracle/postgresql | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](tsql-cast-int-truncation-reverse.md) | tsql → postgresql/oracle/mysql | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

### PostgreSQL as source

| [Window frame modes](#window-frame-modes-2) | [Boolean aggregates and `FILTER`](#boolean-aggregates-and-filter-2) | [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family-3) | [`DISTINCT ON`](#distinct-on-2) | [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-3) |
|---|---|---|---|---|

#### Window frame modes

| Article | Direction | Description |
|---|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](groups-window-frame.md) | oracle/postgresql → tsql/mysql | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |

#### Boolean aggregates and `FILTER`

| Article | Direction | Description |
|---|---|---|
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](filter-clause.md) | postgresql → tsql/oracle/mysql | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](bool-or-and-value-wrapping.md) | postgresql → tsql/oracle | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](bool-or-filter-composition.md) | postgresql → tsql/oracle | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](cast-folding-listagg-string-agg.md) | postgresql → tsql/oracle | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](any-value-to-tsql.md) | postgresql/mysql → tsql | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |

#### `DISTINCT ON`

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](distinct-on.md) | postgresql → tsql/oracle/mysql | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](cast-to-integer-rounding.md) | postgresql/mysql → tsql | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |

### PostgreSQL as target

| [Ordered aggregates](#ordered-aggregates-2) | [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family-4) | [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-4) |
|---|---|---|

#### Ordered aggregates

| Article | Direction | Description |
|---|---|---|
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](oracle-keep-dense-rank.md) | oracle → tsql/postgresql/mysql | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [`DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL](distinct-numeric-order-by.md) | mysql → postgresql | `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-')` de-duplicates `x` and orders the *numeric* values before joining them. |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](oracle-listagg-over.md) | oracle → tsql/postgresql/mysql | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](mod-by-zero-divisor.md) | mysql → tsql/oracle/postgresql | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](tsql-cast-int-truncation-reverse.md) | tsql → postgresql/oracle/mysql | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

### MySQL as source

| [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family-5) | [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-5) |
|---|---|

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [`DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL](distinct-numeric-order-by.md) | mysql → postgresql | `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-')` de-duplicates `x` and orders the *numeric* values before joining them. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](any-value-to-tsql.md) | postgresql/mysql → tsql | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |
| [An unordered MySQL `GROUP_CONCAT` → Oracle `LISTAGG` gains a synthesized `WITHIN GROUP (ORDER BY <arg>)`](group-concat-synthesized-within-group-oracle.md) | mysql → oracle | MySQL's `GROUP_CONCAT(expr SEPARATOR sep)` needs no ordering clause — an unordered call is valid MySQL, with whatever order the engine happens to produce. |

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](cast-to-integer-rounding.md) | postgresql/mysql → tsql | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](mod-by-zero-divisor.md) | mysql → tsql/oracle/postgresql | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |

### MySQL as target

| [Window frame modes](#window-frame-modes-3) | [Ordered aggregates](#ordered-aggregates-3) | [Boolean aggregates and `FILTER`](#boolean-aggregates-and-filter-3) | [`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family](#group_concat--string_agg--listagg-family-6) | [`DISTINCT ON`](#distinct-on-3) | [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-6) |
|---|---|---|---|---|---|

#### Window frame modes

| Article | Direction | Description |
|---|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](groups-window-frame.md) | oracle/postgresql → tsql/mysql | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |

#### Ordered aggregates

| Article | Direction | Description |
|---|---|---|
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](oracle-keep-dense-rank.md) | oracle → tsql/postgresql/mysql | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |

#### Boolean aggregates and `FILTER`

| Article | Direction | Description |
|---|---|---|
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](filter-clause.md) | postgresql → tsql/oracle/mysql | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |

#### `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](oracle-listagg-over.md) | oracle → tsql/postgresql/mysql | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |

#### `DISTINCT ON`

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](distinct-on.md) | postgresql → tsql/oracle/mysql | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](tsql-cast-int-truncation-reverse.md) | tsql → postgresql/oracle/mysql | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

### Cross-engine / multi-directional

| [Numeric division, cast rounding, and zero-divisor semantics](#numeric-division-cast-rounding-and-zero-divisor-semantics-7) | [Math functions with no shared spelling](#math-functions-with-no-shared-spelling) |
|---|---|

#### Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [Integer-truncating vs. decimal division (cross-engine)](integer-vs-decimal-division.md) | cross-engine | `/` truncates two integer operands to an integer on PostgreSQL and T-SQL (`5 / 2` is `2`), but MySQL and Oracle always return a decimal (`5 / 2` is `2.5`) — crossing that line without compensation silently changes the value. |

#### Math functions with no shared spelling

| Article | Direction | Description |
|---|---|---|
| [Math functions with no shared spelling: `LOG` argument order, `COT`, `PI()`, `TRUNC(x, n)`](math-function-per-engine-spelling.md) | cross-engine | Several ordinary scalar math functions differ across engines in ways a rename table alone can't bridge — an argument order flip, a missing function entirely, or a same-name function with different rounding behavior. |

## All articles by type

## Window frame modes

| Article | Direction | Description |
|---|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](groups-window-frame.md) | oracle/postgresql → tsql/mysql | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |

## Ordered aggregates

| Article | Direction | Description |
|---|---|---|
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](oracle-keep-dense-rank.md) | oracle → tsql/postgresql/mysql | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |

## Boolean aggregates and `FILTER`

| Article | Direction | Description |
|---|---|---|
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](filter-clause.md) | postgresql → tsql/oracle/mysql | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](bool-or-and-value-wrapping.md) | postgresql → tsql/oracle | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](bool-or-filter-composition.md) | postgresql → tsql/oracle | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |

## `GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family

| Article | Direction | Description |
|---|---|---|
| [`DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL](distinct-numeric-order-by.md) | mysql → postgresql | `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-')` de-duplicates `x` and orders the *numeric* values before joining them. |
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](cast-folding-listagg-string-agg.md) | postgresql → tsql/oracle | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](any-value-to-tsql.md) | postgresql/mysql → tsql | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](oracle-listagg-over.md) | oracle → tsql/postgresql/mysql | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |
| [An unordered MySQL `GROUP_CONCAT` → Oracle `LISTAGG` gains a synthesized `WITHIN GROUP (ORDER BY <arg>)`](group-concat-synthesized-within-group-oracle.md) | mysql → oracle | MySQL's `GROUP_CONCAT(expr SEPARATOR sep)` needs no ordering clause — an unordered call is valid MySQL, with whatever order the engine happens to produce. |

## `DISTINCT ON`

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](distinct-on.md) | postgresql → tsql/oracle/mysql | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |

## Numeric division, cast rounding, and zero-divisor semantics

| Article | Direction | Description |
|---|---|---|
| [Numeric division, cast rounding, and zero-divisor semantics](numeric-division-overview.md) | overview | Three related but distinct per-engine divergences around plain arithmetic, gathered here because an aggregate divisor (`SUM(x)/COUNT(x)`) is the most common place they surface, even though the compensation applies to any division or cast, aggregate or not. |
| [Integer-truncating vs. decimal division (cross-engine)](integer-vs-decimal-division.md) | cross-engine | `/` truncates two integer operands to an integer on PostgreSQL and T-SQL (`5 / 2` is `2`), but MySQL and Oracle always return a decimal (`5 / 2` is `2.5`) — crossing that line without compensation silently changes the value. |
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](cast-to-integer-rounding.md) | postgresql/mysql → tsql | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](mod-by-zero-divisor.md) | mysql → tsql/oracle/postgresql | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](tsql-cast-int-truncation-reverse.md) | tsql → postgresql/oracle/mysql | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

## Topics left out for lack of source support

| Article | Direction | Description |
|---|---|---|
| [Topics left out for lack of source support](topics-left-out.md) | overview | - **CI-DISTINCT collation carrier inside the `GROUP_CONCAT`/`STRING_AGG` family specifically** — the corpus has a general case-insensitive-collation carrier for `DISTINCT`/`ORDER BY` (`my-distinct-case`, `docs/03-unsupported.md` §3.14), but no case combining it with a string aggregate's own `DISTINCT`/`ORDER BY` clause, so no dedicated entry is made here to avoid inventing an example. |

## Math functions with no shared spelling

| Article | Direction | Description |
|---|---|---|
| [Math functions with no shared spelling: `LOG` argument order, `COT`, `PI()`, `TRUNC(x, n)`](math-function-per-engine-spelling.md) | cross-engine | Several ordinary scalar math functions differ across engines in ways a rename table alone can't bridge — an argument order flip, a missing function entirely, or a same-name function with different rounding behavior. |
