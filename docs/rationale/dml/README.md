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
