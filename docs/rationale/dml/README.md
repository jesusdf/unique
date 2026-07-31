[← All rationale topics](../README.md)

# DML: PIVOT/UNPIVOT, MERGE, DELETE, row values

`PIVOT`/`UNPIVOT` relation rewrites, `MERGE`/upsert lowering, multi-table
`DELETE`, multi-join `UPDATE`, row caps, row-value comparisons,
`OUTPUT`/`RETURNING`, set-operation `ORDER BY`, Oracle's join-mark/`ROWNUM`/
`DUAL` idioms as a *source*, PostgreSQL's portable row-source rewrites
(`VALUES`/`generate_series`), and parenthesized-structure
unwrapping/shielding in `FROM`. See [README.md](../README.md) for the entry
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

| [`PIVOT` / `UNPIVOT`](#pivot--unpivot) | [`MERGE` / upsert lowering](#merge--upsert-lowering) | [Multi-table `DELETE`](#multi-table-delete) | [Multi-join `UPDATE`](#multi-join-update) | [`OUTPUT` / `RETURNING`](#output--returning) | [Set-operation `ORDER BY`](#set-operation-order-by) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction) | [Recursive CTE synthesis](#recursive-cte-synthesis) | [Conditional expression translation](#conditional-expression-translation) | [Literal parsing recovery](#literal-parsing-recovery) |
|---|---|---|---|---|---|---|---|---|---|

#### `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](pivot.md) | tsql/oracle → postgresql/mysql | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

#### `MERGE` / upsert lowering

| Article | Direction | Description |
|---|---|---|
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](merge-when-not-matched-by-source.md) | tsql → oracle/postgresql | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |
| [Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold](merge-matched-update-delete-fold.md) | tsql → oracle | A T-SQL `MERGE` may carry two conditional `WHEN MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`. |
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](merge-with-leading-cte.md) | tsql → oracle/mysql | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |

#### Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](delete-top-n-row-cap.md) | tsql → oracle/postgresql/mysql | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |

#### Multi-join `UPDATE`

| Article | Direction | Description |
|---|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](multi-join-update-from.md) | tsql/postgresql → oracle/postgresql/mysql | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |

#### `OUTPUT` / `RETURNING`

| Article | Direction | Description |
|---|---|---|
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](output-to-returning.md) | tsql → oracle/postgresql | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |
| [`OUTPUT … INTO` redirect (T-SQL) → PostgreSQL](output-into-redirect.md) | tsql → postgresql | `OUTPUT INSERTED.a INTO log(a)` redirects the output rows into a second table instead of returning them to the caller. |

#### Set-operation `ORDER BY`

| Article | Direction | Description |
|---|---|---|
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](set-op-trailing-order-by.md) | tsql → oracle/postgresql/mysql | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

#### Conditional expression translation

| Article | Direction | Description |
|---|---|---|
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](iif-to-case-or-native.md) | tsql/mysql → oracle/postgresql | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |

#### Literal parsing recovery

| Article | Direction | Description |
|---|---|---|
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](money-literal-shorthand.md) | tsql → oracle/postgresql/mysql | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |

### T-SQL as target

| [`PIVOT` / `UNPIVOT`](#pivot--unpivot-1) | [Multi-table `DELETE`](#multi-table-delete-1) | [Row-value comparisons](#row-value-comparisons) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-1) | [Portable row-source rewrites (PostgreSQL)](#portable-row-source-rewrites-postgresql) | [Recursive CTE synthesis](#recursive-cte-synthesis-1) | [Positional GROUP BY resolved to a column name](#positional-group-by-resolved-to-a-column-name) |
|---|---|---|---|---|---|---|

#### `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

#### Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](multi-table-delete-join.md) | mysql → tsql/oracle/postgresql | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |

#### Row-value comparisons

| Article | Direction | Description |
|---|---|---|
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](row-value-inequality.md) | oracle/postgresql/mysql → tsql | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [Row-value `IN` (Oracle) → T-SQL](row-value-in.md) | oracle → tsql | `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN` list, valid on Oracle/PostgreSQL/MySQL. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Portable row-source rewrites (PostgreSQL)

| Article | Direction | Description |
|---|---|---|
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](from-values-to-union-all.md) | postgresql → all | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](from-generate-series.md) | postgresql → all | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |

#### Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

#### Positional GROUP BY resolved to a column name

| Article | Direction | Description |
|---|---|---|
| [`GROUP BY 1` (positional ordinal) → the actual `SELECT`-list column name](group-by-ordinal-resolved.md) | postgresql → tsql | PostgreSQL accepts a positional ordinal in `GROUP BY` — `GROUP BY 1` groups by whatever the first `SELECT`-list expression is. |

### Oracle as source

| [`PIVOT` / `UNPIVOT`](#pivot--unpivot-2) | [Row-value comparisons](#row-value-comparisons-1) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-2) |
|---|---|---|

#### `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](pivot.md) | tsql/oracle → postgresql/mysql | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

#### Row-value comparisons

| Article | Direction | Description |
|---|---|---|
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](row-value-inequality.md) | oracle/postgresql/mysql → tsql | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [Row-value `IN` (Oracle) → T-SQL](row-value-in.md) | oracle → tsql | `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN` list, valid on Oracle/PostgreSQL/MySQL. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

### Oracle as target

| [`PIVOT` / `UNPIVOT`](#pivot--unpivot-3) | [`MERGE` / upsert lowering](#merge--upsert-lowering-1) | [Multi-table `DELETE`](#multi-table-delete-2) | [Multi-join `UPDATE`](#multi-join-update-1) | [`OUTPUT` / `RETURNING`](#output--returning-1) | [Set-operation `ORDER BY`](#set-operation-order-by-1) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-3) | [Portable row-source rewrites (PostgreSQL)](#portable-row-source-rewrites-postgresql-1) | [Recursive CTE synthesis](#recursive-cte-synthesis-2) | [Conditional expression translation](#conditional-expression-translation-1) | [Literal parsing recovery](#literal-parsing-recovery-1) |
|---|---|---|---|---|---|---|---|---|---|---|

#### `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

#### `MERGE` / upsert lowering

| Article | Direction | Description |
|---|---|---|
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](merge-when-not-matched-by-source.md) | tsql → oracle/postgresql | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |
| [Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold](merge-matched-update-delete-fold.md) | tsql → oracle | A T-SQL `MERGE` may carry two conditional `WHEN MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`. |
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](merge-with-leading-cte.md) | tsql → oracle/mysql | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |

#### Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](multi-table-delete-join.md) | mysql → tsql/oracle/postgresql | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](delete-top-n-row-cap.md) | tsql → oracle/postgresql/mysql | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |

#### Multi-join `UPDATE`

| Article | Direction | Description |
|---|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](multi-join-update-from.md) | tsql/postgresql → oracle/postgresql/mysql | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |

#### `OUTPUT` / `RETURNING`

| Article | Direction | Description |
|---|---|---|
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](output-to-returning.md) | tsql → oracle/postgresql | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |

#### Set-operation `ORDER BY`

| Article | Direction | Description |
|---|---|---|
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](set-op-trailing-order-by.md) | tsql → oracle/postgresql/mysql | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Portable row-source rewrites (PostgreSQL)

| Article | Direction | Description |
|---|---|---|
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](from-values-to-union-all.md) | postgresql → all | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](from-generate-series.md) | postgresql → all | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |

#### Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

#### Conditional expression translation

| Article | Direction | Description |
|---|---|---|
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](iif-to-case-or-native.md) | tsql/mysql → oracle/postgresql | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |

#### Literal parsing recovery

| Article | Direction | Description |
|---|---|---|
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](money-literal-shorthand.md) | tsql → oracle/postgresql/mysql | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |

### PostgreSQL as source

| [Multi-join `UPDATE`](#multi-join-update-2) | [Row-value comparisons](#row-value-comparisons-2) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-4) | [Portable row-source rewrites (PostgreSQL)](#portable-row-source-rewrites-postgresql-2) | [Positional GROUP BY resolved to a column name](#positional-group-by-resolved-to-a-column-name-1) |
|---|---|---|---|---|

#### Multi-join `UPDATE`

| Article | Direction | Description |
|---|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](multi-join-update-from.md) | tsql/postgresql → oracle/postgresql/mysql | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |

#### Row-value comparisons

| Article | Direction | Description |
|---|---|---|
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](row-value-inequality.md) | oracle/postgresql/mysql → tsql | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Portable row-source rewrites (PostgreSQL)

| Article | Direction | Description |
|---|---|---|
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](from-values-to-union-all.md) | postgresql → all | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](from-generate-series.md) | postgresql → all | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |

#### Positional GROUP BY resolved to a column name

| Article | Direction | Description |
|---|---|---|
| [`GROUP BY 1` (positional ordinal) → the actual `SELECT`-list column name](group-by-ordinal-resolved.md) | postgresql → tsql | PostgreSQL accepts a positional ordinal in `GROUP BY` — `GROUP BY 1` groups by whatever the first `SELECT`-list expression is. |

### PostgreSQL as target

| [`PIVOT` / `UNPIVOT`](#pivot--unpivot-4) | [`MERGE` / upsert lowering](#merge--upsert-lowering-2) | [Multi-table `DELETE`](#multi-table-delete-3) | [Multi-join `UPDATE`](#multi-join-update-3) | [`OUTPUT` / `RETURNING`](#output--returning-2) | [Set-operation `ORDER BY`](#set-operation-order-by-2) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-5) | [Portable row-source rewrites (PostgreSQL)](#portable-row-source-rewrites-postgresql-3) | [Recursive CTE synthesis](#recursive-cte-synthesis-3) | [Conditional expression translation](#conditional-expression-translation-2) | [Literal parsing recovery](#literal-parsing-recovery-2) |
|---|---|---|---|---|---|---|---|---|---|---|

#### `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](pivot.md) | tsql/oracle → postgresql/mysql | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

#### `MERGE` / upsert lowering

| Article | Direction | Description |
|---|---|---|
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](merge-when-not-matched-by-source.md) | tsql → oracle/postgresql | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |

#### Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](multi-table-delete-join.md) | mysql → tsql/oracle/postgresql | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](delete-top-n-row-cap.md) | tsql → oracle/postgresql/mysql | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |

#### Multi-join `UPDATE`

| Article | Direction | Description |
|---|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](multi-join-update-from.md) | tsql/postgresql → oracle/postgresql/mysql | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |

#### `OUTPUT` / `RETURNING`

| Article | Direction | Description |
|---|---|---|
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](output-to-returning.md) | tsql → oracle/postgresql | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |
| [`OUTPUT … INTO` redirect (T-SQL) → PostgreSQL](output-into-redirect.md) | tsql → postgresql | `OUTPUT INSERTED.a INTO log(a)` redirects the output rows into a second table instead of returning them to the caller. |

#### Set-operation `ORDER BY`

| Article | Direction | Description |
|---|---|---|
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](set-op-trailing-order-by.md) | tsql → oracle/postgresql/mysql | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Portable row-source rewrites (PostgreSQL)

| Article | Direction | Description |
|---|---|---|
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](from-values-to-union-all.md) | postgresql → all | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](from-generate-series.md) | postgresql → all | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |

#### Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

#### Conditional expression translation

| Article | Direction | Description |
|---|---|---|
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](iif-to-case-or-native.md) | tsql/mysql → oracle/postgresql | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |

#### Literal parsing recovery

| Article | Direction | Description |
|---|---|---|
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](money-literal-shorthand.md) | tsql → oracle/postgresql/mysql | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |

### MySQL as source

| [Multi-table `DELETE`](#multi-table-delete-4) | [Row-value comparisons](#row-value-comparisons-3) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-6) | [Recursive CTE synthesis](#recursive-cte-synthesis-4) | [Conditional expression translation](#conditional-expression-translation-3) |
|---|---|---|---|---|

#### Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](multi-table-delete-join.md) | mysql → tsql/oracle/postgresql | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |

#### Row-value comparisons

| Article | Direction | Description |
|---|---|---|
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](row-value-inequality.md) | oracle/postgresql/mysql → tsql | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

#### Conditional expression translation

| Article | Direction | Description |
|---|---|---|
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](iif-to-case-or-native.md) | tsql/mysql → oracle/postgresql | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |

### MySQL as target

| [`PIVOT` / `UNPIVOT`](#pivot--unpivot-5) | [`MERGE` / upsert lowering](#merge--upsert-lowering-3) | [Multi-table `DELETE`](#multi-table-delete-5) | [Multi-join `UPDATE`](#multi-join-update-4) | [Set-operation `ORDER BY`](#set-operation-order-by-3) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-7) | [Portable row-source rewrites (PostgreSQL)](#portable-row-source-rewrites-postgresql-4) | [Recursive CTE synthesis](#recursive-cte-synthesis-5) | [Literal parsing recovery](#literal-parsing-recovery-3) |
|---|---|---|---|---|---|---|---|---|

#### `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](pivot.md) | tsql/oracle → postgresql/mysql | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

#### `MERGE` / upsert lowering

| Article | Direction | Description |
|---|---|---|
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](merge-with-leading-cte.md) | tsql → oracle/mysql | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |

#### Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](delete-top-n-row-cap.md) | tsql → oracle/postgresql/mysql | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |

#### Multi-join `UPDATE`

| Article | Direction | Description |
|---|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](multi-join-update-from.md) | tsql/postgresql → oracle/postgresql/mysql | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |

#### Set-operation `ORDER BY`

| Article | Direction | Description |
|---|---|---|
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](set-op-trailing-order-by.md) | tsql → oracle/postgresql/mysql | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

#### Portable row-source rewrites (PostgreSQL)

| Article | Direction | Description |
|---|---|---|
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](from-values-to-union-all.md) | postgresql → all | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](from-generate-series.md) | postgresql → all | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |

#### Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

#### Literal parsing recovery

| Article | Direction | Description |
|---|---|---|
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](money-literal-shorthand.md) | tsql → oracle/postgresql/mysql | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |

### Cross-engine / multi-directional

| [Set-operation `ORDER BY`](#set-operation-order-by-4) | [Oracle join syntax and row limits (source direction)](#oracle-join-syntax-and-row-limits-source-direction-8) | [Parenthesized-structure unwrapping and shielding](#parenthesized-structure-unwrapping-and-shielding) | [Set-operation `ALL` quantifier](#set-operation-all-quantifier) |
|---|---|---|---|

#### Set-operation `ORDER BY`

| Article | Direction | Description |
|---|---|---|
| [`ORDER BY` inside a joined derived table (any source) → T-SQL: kept only with a row cap](derived-table-order-by-to-tsql.md) | cross-engine | A derived table used as a join operand can carry its own `ORDER BY` — e.g. to pick or arrange the rows it contributes — separately from any `ORDER BY` on the outer query. |

#### Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [Oracle `(+)` outer-join mark → explicit `LEFT JOIN … ON`; comma joins → `CROSS JOIN`](oracle-outer-join-mark.md) | cross-engine | Oracle's legacy join syntax has no `JOIN` keyword at all: tables are comma-listed in `FROM`, and `col(+)` on one side of a `WHERE` predicate marks that table as the *optional* (outer) side of the join — the row is still produced, NULL-extended, when no match exists. |
| [`ROWNUM <= n` (Oracle) → `LIMIT` / `TOP` / `FETCH FIRST`](oracle-rownum-row-cap.md) | cross-engine | Oracle's `ROWNUM` is a pseudo-column numbering rows as they are produced; `WHERE ROWNUM <= n` is Oracle's idiom for capping a result to `n` rows — with no ordering guarantee unless paired with an `ORDER BY` (the `ROWNUM` filter applies before any sort). |

#### Parenthesized-structure unwrapping and shielding

| Article | Direction | Description |
|---|---|---|
| [Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded](parenthesized-set-op-arms.md) | cross-engine | `(SELECT …) UNION ALL (SELECT …)` parenthesizes each arm of a set operation — often just for readability, but sometimes because one arm carries its own `ORDER BY`/`LIMIT` that must apply to *that arm alone*, not to the combined result. |
| [Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table](parenthesized-join-groups.md) | cross-engine | Two different `FROM`-clause shapes both need restructuring, for opposite reasons: a **parenthesized join group** — `FROM (t1 JOIN t2 ON …), t3` — groups a join tree for readability with no semantic effect of its own; a **column-aliased table reference** — PostgreSQL's `tbl AS alias(col1, col2)` — renames the table's columns positionally, a real semantic operation most targets cannot spell against a plain table reference at all. |

#### Set-operation `ALL` quantifier

| Article | Direction | Description |
|---|---|---|
| [`INTERSECT ALL` / `EXCEPT ALL` → Oracle / T-SQL](intersect-except-all.md) | cross-engine | `INTERSECT ALL` and `EXCEPT ALL` compare rows the same way as the plain `INTERSECT`/`EXCEPT`, but **keep duplicates**: `INTERSECT ALL` returns `min(count in left, count in right)` copies of each matching row, and `EXCEPT ALL` returns `max(count in left − count in right, 0)` copies. |

## All articles by type

## `PIVOT` / `UNPIVOT`

| Article | Direction | Description |
|---|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](pivot.md) | tsql/oracle → postgresql/mysql | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](unpivot.md) | tsql/oracle → all | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |

## `MERGE` / upsert lowering

| Article | Direction | Description |
|---|---|---|
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](merge-when-not-matched-by-source.md) | tsql → oracle/postgresql | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |
| [Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold](merge-matched-update-delete-fold.md) | tsql → oracle | A T-SQL `MERGE` may carry two conditional `WHEN MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`. |
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](merge-with-leading-cte.md) | tsql → oracle/mysql | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |

## Multi-table `DELETE`

| Article | Direction | Description |
|---|---|---|
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](multi-table-delete-join.md) | mysql → tsql/oracle/postgresql | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](delete-top-n-row-cap.md) | tsql → oracle/postgresql/mysql | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |

## Multi-join `UPDATE`

| Article | Direction | Description |
|---|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](multi-join-update-from.md) | tsql/postgresql → oracle/postgresql/mysql | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |

## Row-value comparisons

| Article | Direction | Description |
|---|---|---|
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](row-value-inequality.md) | oracle/postgresql/mysql → tsql | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [Row-value `IN` (Oracle) → T-SQL](row-value-in.md) | oracle → tsql | `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN` list, valid on Oracle/PostgreSQL/MySQL. |

## `OUTPUT` / `RETURNING`

| Article | Direction | Description |
|---|---|---|
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](output-to-returning.md) | tsql → oracle/postgresql | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |
| [`OUTPUT … INTO` redirect (T-SQL) → PostgreSQL](output-into-redirect.md) | tsql → postgresql | `OUTPUT INSERTED.a INTO log(a)` redirects the output rows into a second table instead of returning them to the caller. |

## Set-operation `ORDER BY`

| Article | Direction | Description |
|---|---|---|
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](set-op-trailing-order-by.md) | tsql → oracle/postgresql/mysql | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |
| [`ORDER BY` inside a joined derived table (any source) → T-SQL: kept only with a row cap](derived-table-order-by-to-tsql.md) | cross-engine | A derived table used as a join operand can carry its own `ORDER BY` — e.g. to pick or arrange the rows it contributes — separately from any `ORDER BY` on the outer query. |

## Oracle join syntax and row limits (source direction)

| Article | Direction | Description |
|---|---|---|
| [Oracle join syntax and row limits (source direction)](oracle-join-source-overview.md) | overview | The entries below run **from** Oracle. |
| [Oracle `(+)` outer-join mark → explicit `LEFT JOIN … ON`; comma joins → `CROSS JOIN`](oracle-outer-join-mark.md) | cross-engine | Oracle's legacy join syntax has no `JOIN` keyword at all: tables are comma-listed in `FROM`, and `col(+)` on one side of a `WHERE` predicate marks that table as the *optional* (outer) side of the join — the row is still produced, NULL-extended, when no match exists. |
| [`ROWNUM <= n` (Oracle) → `LIMIT` / `TOP` / `FETCH FIRST`](oracle-rownum-row-cap.md) | cross-engine | Oracle's `ROWNUM` is a pseudo-column numbering rows as they are produced; `WHERE ROWNUM <= n` is Oracle's idiom for capping a result to `n` rows — with no ordering guarantee unless paired with an `ORDER BY` (the `ROWNUM` filter applies before any sort). |
| [`FROM DUAL` synthesis and removal (bidirectional)](from-dual.md) | oracle ↔ all | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |

## Portable row-source rewrites (PostgreSQL)

| Article | Direction | Description |
|---|---|---|
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](from-values-to-union-all.md) | postgresql → all | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](from-generate-series.md) | postgresql → all | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |

## Parenthesized-structure unwrapping and shielding

| Article | Direction | Description |
|---|---|---|
| [Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded](parenthesized-set-op-arms.md) | cross-engine | `(SELECT …) UNION ALL (SELECT …)` parenthesizes each arm of a set operation — often just for readability, but sometimes because one arm carries its own `ORDER BY`/`LIMIT` that must apply to *that arm alone*, not to the combined result. |
| [Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table](parenthesized-join-groups.md) | cross-engine | Two different `FROM`-clause shapes both need restructuring, for opposite reasons: a **parenthesized join group** — `FROM (t1 JOIN t2 ON …), t3` — groups a join tree for readability with no semantic effect of its own; a **column-aliased table reference** — PostgreSQL's `tbl AS alias(col1, col2)` — renames the table's columns positionally, a real semantic operation most targets cannot spell against a plain table reference at all. |

## Set-operation `ALL` quantifier

| Article | Direction | Description |
|---|---|---|
| [`INTERSECT ALL` / `EXCEPT ALL` → Oracle / T-SQL](intersect-except-all.md) | cross-engine | `INTERSECT ALL` and `EXCEPT ALL` compare rows the same way as the plain `INTERSECT`/`EXCEPT`, but **keep duplicates**: `INTERSECT ALL` returns `min(count in left, count in right)` copies of each matching row, and `EXCEPT ALL` returns `max(count in left − count in right, 0)` copies. |

## Recursive CTE synthesis

| Article | Direction | Description |
|---|---|---|
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](recursive-cte-keyword-and-column-list.md) | tsql/mysql → all | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |

## Positional GROUP BY resolved to a column name

| Article | Direction | Description |
|---|---|---|
| [`GROUP BY 1` (positional ordinal) → the actual `SELECT`-list column name](group-by-ordinal-resolved.md) | postgresql → tsql | PostgreSQL accepts a positional ordinal in `GROUP BY` — `GROUP BY 1` groups by whatever the first `SELECT`-list expression is. |

## Conditional expression translation

| Article | Direction | Description |
|---|---|---|
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](iif-to-case-or-native.md) | tsql/mysql → oracle/postgresql | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |

## Literal parsing recovery

| Article | Direction | Description |
|---|---|---|
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](money-literal-shorthand.md) | tsql → oracle/postgresql/mysql | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |
