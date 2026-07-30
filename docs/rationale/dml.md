# DML: PIVOT/UNPIVOT, MERGE, DELETE, row values

`PIVOT`/`UNPIVOT` relation rewrites, `MERGE`/upsert lowering, multi-table
`DELETE`, row caps, row-value comparisons, `OUTPUT`/`RETURNING`, and
set-operation `ORDER BY`. See [README.md](README.md) for the entry format and
sourcing rules.

## `PIVOT` / `UNPIVOT`

### `PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL

**Source semantics.** `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows
into columns for a small, explicit set of pivot values, aggregating `arg` per
value.
**Why there is no direct mapping.** PostgreSQL and MySQL have no `PIVOT`
operator at all. Oracle keeps `PIVOT` natively but needs an explicit
`'v' AS v` alias in the `IN`-list so its output columns are named like
T-SQL's default `[v]` bracket naming.
**What Unique emits.** T-SQL keeps its native `PIVOT`; Oracle re-spells the
`IN`-list with explicit aliases (`PIVOT (SUM(v) FOR dept IN ('A' AS A, 'B' AS
B))`). PostgreSQL/MySQL get a conditional-aggregation derived table —
`SUM(CASE WHEN dept = 'A' THEN v END) AS A` per pivot value, grouped by every
source column that is neither the pivot column nor the aggregate argument.
When the source's projected columns are not visible (a bare table or
`SELECT *`), the grouping columns cannot be determined and the relation
degrades to a warned carrier instead (`emit_relations.py::_emit_pivot_relation`).
**Divergence & warning.** Faithful when the source projection is visible.
`[limit]` (warned carrier) otherwise. The original conversion silently
**dropped the whole `PIVOT` operator** with no warning — a defect this
lowering replaced.
**References.** `reda-ts-pivot` · `docs/03-unsupported.md` §2 (T-SQL
PIVOT/UNPIVOT row).

```sql
-- corpus case reda-ts-pivot
CREATE TABLE t (dept VARCHAR(1), v INT);
SELECT * FROM (SELECT dept, v FROM t) src PIVOT (SUM(v) FOR dept IN ([A],[B])) pv
-- Oracle:  ... src PIVOT (SUM(v) FOR dept IN ('A' AS A, 'B' AS B)) ...
-- PostgreSQL/MySQL:
--   SELECT SUM(CASE WHEN dept = 'A' THEN v END) AS A,
--          SUM(CASE WHEN dept = 'B' THEN v END) AS B
--   FROM (SELECT dept, v FROM t) src
-- Live (rows A/1, A/2, B/5): PIVOT = one row (A=3, B=5); the old silent drop
-- returned the 3 raw rows instead.
```

### `UNPIVOT` (T-SQL / Oracle) → all targets

**Source semantics.** `UNPIVOT (val FOR col IN (a, b))` turns columns `a`,
`b` into row pairs `(col, val)` — `col` carrying the *name* of the source
column, `val` its value.
**Why there is no direct mapping.** Unique renders `UNPIVOT` as a `UNION
ALL` (one arm per unpivoted column, `NULL`s excluded to match `UNPIVOT`'s
default) on **every** target, never the native `UNPIVOT` operator — even on
Oracle and T-SQL, which have one. The reason is the *name-column value*:
native `UNPIVOT` re-derives it from the `IN`-list identifier, and Oracle
folds an unquoted identifier to upper case, so Oracle's native `UNPIVOT`
yields `'A'` where T-SQL's yields `'a'` for the same source. The `UNION ALL`
rewrite instead emits an explicit string literal cased exactly as the
*source* engine would produce it, so the value matches across engines
(`emit_relations.py::_emit_unpivot_relation` docstring).
**What Unique emits.** `SELECT <carried cols>, '<name>' AS col, <col> AS val
FROM <source> WHERE <col> IS NOT NULL` unioned per unpivoted column. When the
source's carried columns are not visible (no projection to name), it
degrades to a warned carrier instead.
**Divergence & warning.** Faithful — values verified equal on
Oracle/PostgreSQL/MySQL. `[limit]` (warned carrier) when the source
projection is invisible.
**References.** `ts-unpivot`, `ora-unpivot`.

```sql
-- corpus case ora-unpivot (Oracle folds unquoted 'a'/'b' to 'A'/'B')
SELECT id,col,val FROM (SELECT 1 id,10 a,20 b FROM DUAL) UNPIVOT (val FOR col IN (a,b))
-- rewritten everywhere as:
--   SELECT id, 'A' AS col, a AS val FROM (...) WHERE a IS NOT NULL
--   UNION ALL
--   SELECT id, 'B' AS col, b AS val FROM (...) WHERE b IS NOT NULL
-- (name-column literal cased 'A'/'B' — matching Oracle's own upper-case fold —
-- not the lower-case 'a'/'b' a T-SQL source would produce for the same shape)
```

## `MERGE` / upsert lowering

### `WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle

**Source semantics.** T-SQL's `MERGE` can act on target rows that have **no**
matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`)
— an anti-join over the `ON` predicate.
**Why there is no direct mapping.** `WHEN NOT MATCHED BY SOURCE` exists
nowhere else (PostgreSQL only gained it in 17, and Unique's PG target does
not assume 17; Oracle's `MERGE` has no such clause at all).
**What Unique emits.** Each `WHEN NOT MATCHED BY SOURCE` clause becomes a
**follow-up statement** — `UPDATE`/`DELETE … WHERE NOT EXISTS (SELECT 1 FROM
<using> WHERE <on>) [AND (<condition>)]` — run after the `MERGE`. Because the
follow-up's anti-join addresses exactly the rows the `MERGE` itself cannot
touch, the two-statement split is value-equivalent to a single native
statement (`emit.py::_merge_extended_clauses` docstring).
**Divergence & warning.** Faithful — live-verified identical final rows on
T-SQL/Oracle/PostgreSQL.
**References.** `ts-merge-full`.

```sql
-- corpus case ts-merge-full
MERGE tgt USING src ON tgt.id = src.id
  WHEN MATCHED AND src.n > 0 THEN UPDATE SET n = src.n
  WHEN MATCHED THEN DELETE
  WHEN NOT MATCHED BY TARGET THEN INSERT (id, n) VALUES (src.id, src.n)
  WHEN NOT MATCHED BY SOURCE THEN DELETE;
```

### Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold

**Source semantics.** A T-SQL `MERGE` may carry two conditional `WHEN
MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`.
**Why there is no direct mapping.** Oracle's `MERGE` grammar allows only a
**single** `WHEN MATCHED` clause; conditional forms are spelled as an
`UPDATE … WHERE` plus a trailing `DELETE WHERE` tail on the same clause, not
two separate `WHEN` branches — and critically, Oracle's `DELETE WHERE`
evaluates against the **post-update** row, while T-SQL evaluates the
original (pre-update) row.
**What Unique emits.** The pair folds into one Oracle `UPDATE` (whose `SET`
keeps the old value via `CASE` where the update should not apply) plus a
spliced `DELETE WHERE` tail — but **only** when the fold is value-safe: the
`DELETE` condition must reference no target column the `UPDATE` assigns. When
it does (the post-update semantics would delete rows T-SQL keeps), the whole
`MERGE` degrades to a carrier + warning instead of shipping silently-wrong
output.
**Divergence & warning.** Faithful in the safe shape (live-verified
identical rows). Full warned carrier in the unsafe shape.
**References.** `docs/03-unsupported.md` §3.6 (MERGE clause composition,
audit 2026-07-24).

### A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL

**Source semantics.** `WITH src AS (…) MERGE INTO t USING src ON … WHEN
MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s
`USING` source is itself a named CTE.
**Why there is no direct mapping.** Oracle forbids a leading `WITH` before
`MERGE` (`ORA-00928`). MySQL has no `MERGE` at all — Unique's MySQL upsert
lowering (`INSERT … SELECT … ON DUPLICATE KEY UPDATE`) referenced the CTE
name (`src`) in its `SELECT … FROM src`, but on its own dropped the `WITH src
AS (…)` that defines it, leaving `src` undefined (MySQL error 1146).
**What Unique emits.** The CTE body is **inlined** at its use site instead
of kept as a separate `WITH`: Oracle's `MERGE INTO t USING (<cte body>) src
…`, MySQL's `INSERT INTO t (…) SELECT … FROM (<cte body>) AS src`.
**Divergence & warning.** Faithful — both targets now produce a valid,
value-equivalent statement instead of an undefined-relation error.
**References.** `reda-ts-cte-merge`.

```sql
-- corpus case reda-ts-cte-merge
WITH src AS (SELECT id, v FROM s)
MERGE INTO t USING src ON t.id = src.id
  WHEN MATCHED THEN UPDATE SET t.v = src.v
  WHEN NOT MATCHED THEN INSERT (id, v) VALUES (src.id, src.v)
-- Oracle:  MERGE INTO t USING (SELECT id AS id, v AS v FROM s) src ON ...
-- MySQL:   INSERT INTO t (id, v)
--          SELECT ... FROM (SELECT id AS id, v AS v FROM s) AS src
--          ON DUPLICATE KEY UPDATE ...
```

## Multi-table `DELETE`

### Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle

**Source semantics.** `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1`
deletes rows from `t1` filtered by a join against `t2`.
**Why there is no direct mapping.** Each of the three targets spells a
join-filtered delete differently: PostgreSQL has no `DELETE … JOIN`, only
`DELETE … USING`; T-SQL spells it `DELETE t1 FROM t1, t2 WHERE …` (a
comma-join, not an `INNER JOIN`); Oracle's `DELETE` has no multi-table form
at all.
**What Unique emits.** PostgreSQL: `DELETE FROM t1 USING t2 WHERE …`. T-SQL:
`DELETE t1 FROM t1, t2 WHERE …` (comma-joined, per `_emit_delete`). Oracle:
`DELETE FROM t1 WHERE EXISTS (SELECT 1 FROM t2 WHERE …)` — exact when the
`WHERE` clause **is** the join condition (the target's own columns stay
visible inside the correlated subquery).
**Divergence & warning.** Faithful on all three.
**References.** `my-multitable-delete-join`, `reda-ts-delete-join`.

```sql
-- corpus case my-multitable-delete-join
DELETE t1 FROM redb_d1 t1 JOIN redb_d2 t2 ON t1.id = t2.id WHERE t2.flag = 1
-- PostgreSQL: DELETE FROM redb_d1 t1 USING redb_d2 t2 WHERE t1.id = t2.id AND t2.flag = 1
-- T-SQL:      DELETE t1 FROM redb_d1 t1, redb_d2 t2 WHERE t1.id = t2.id AND t2.flag = 1
-- Oracle:     DELETE FROM redb_d1 t1
--             WHERE EXISTS (SELECT 1 FROM redb_d2 t2 WHERE t1.id = t2.id AND t2.flag = 1)
```

### `DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL

**Source semantics.** `DELETE TOP (n) FROM t WHERE …` caps the delete to `n`
**arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP`
without an `ORDER BY`, which `DELETE` cannot carry).
**Why there is no direct mapping.** None of the other three engines has a
`TOP`-style row cap on `DELETE` in the same syntactic position; each needs a
different mechanism to bound the row count.
**What Unique emits.** Per-target row-cap forms (`emit_relations.py::_DELETE_CAP`):
MySQL trails `LIMIT n`; Oracle folds `ROWNUM <= n` into the `WHERE`;
PostgreSQL selects `n` candidate rows by `ctid` in a subquery
(`WHERE ctid IN (SELECT ctid FROM t WHERE … LIMIT n)`, since PostgreSQL's
`DELETE` has no `LIMIT`). All four cap the delete to `n` arbitrary matching
rows — faithful to `TOP`'s own unordered semantics.
**Divergence & warning.** Faithful. The earlier defect **silently dropped**
`TOP (n)` altogether, deleting every matching row instead of capping at `n`.
**References.** `reda-ts-delete-top`.

```sql
-- corpus case reda-ts-delete-top
DELETE TOP (2) FROM t WHERE a > 0
-- MySQL:      DELETE FROM t WHERE a > 0 LIMIT 2
-- Oracle:     DELETE FROM t WHERE a > 0 AND ROWNUM <= 2
-- PostgreSQL: DELETE FROM t WHERE ctid IN (SELECT ctid FROM t WHERE a > 0 LIMIT 2)
```

## Row-value comparisons

### Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL

**Source semantics.** `(a, b) > (1, 5)` is a lexicographic row-value
comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND
b > 5`.
**Why there is no direct mapping.** T-SQL has no row-value comparison syntax
at all; the tuple literal is rejected outright (error 4145, "non-boolean
type … where a condition is expected"). PostgreSQL, Oracle and MySQL all
accept it natively.
**What Unique emits.** T-SQL gets the comparison expanded lexicographically:
`a > 1 OR (a = 1 AND (b > 5))`.
**Divergence & warning.** Faithful — PG native result `(3,4)`.
**References.** `pg-row-value-comparison`.

```sql
-- corpus case pg-row-value-comparison
SELECT * FROM t WHERE (a, b) > (1, 5)
-- T-SQL: WHERE a > 1 OR (a = 1 AND (b > 5))
```

### Row-value `IN` (Oracle) → T-SQL

**Source semantics.** `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN`
list, valid on Oracle/PostgreSQL/MySQL.
**Why there is no direct mapping.** T-SQL has no row-constructor `IN` either
(the same error 4145 as the inequality case above).
**What Unique emits.** Expanded to an `OR`-of-`AND`-pairs form:
`(a = 1 AND b = 2) OR (a = 3 AND b = 4)`.
**Divergence & warning.** Faithful.
**References.** `reda-ora-rowvalue-in` (neighbour of `pg-row-value-comparison`).

## `OUTPUT` / `RETURNING`

### `INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier

**Source semantics.** T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a
result set of the affected rows' before/after values alongside the DML.
**Why there is no direct mapping.** PostgreSQL's `RETURNING` is a direct,
faithful equivalent (`INSERTED`→the new row, `DELETED`→the old row — a
`DELETE` only ever exposes `DELETED`). Oracle's `RETURNING` clause, though
named the same, is **PL/SQL-only**: it must target `INTO` bind variables and
cannot stand alone in a plain SQL statement (`ORA-63809` otherwise), so a
standalone `OUTPUT` has no Oracle equivalent at all.
**What Unique emits.** PostgreSQL: `RETURNING` with the `INSERTED`/`DELETED`
qualifier stripped from each item (`_prefix_tsql_output_items` performs the
reverse: it re-adds the qualifier when going the other direction). Oracle:
the `INSERT`/`UPDATE`/`DELETE` itself still runs; the `OUTPUT` result set is
documented in a carrier + warning rather than attempted.
**Divergence & warning.** Faithful on PostgreSQL. `[limit]` on Oracle — the
DML effect is preserved, the returned result set is not.
**References.** `ts-insert-output`, `ts-update-output` ·
`docs/03-unsupported.md` §3.7 (the MySQL side of the same gap).

```sql
-- corpus case ts-insert-output
INSERT INTO t (n) OUTPUT INSERTED.id, INSERTED.n VALUES (10), (20)
-- PostgreSQL: INSERT INTO t (n) VALUES (10), (20) RETURNING id, n
-- Oracle: the INSERT runs; OUTPUT is documented in a carrier (no RETURNING
-- result set — ORA-63809 forbids a standalone one)
```

### `OUTPUT … INTO` redirect (T-SQL) → PostgreSQL

**Source semantics.** `OUTPUT INSERTED.a INTO log(a)` redirects the output
rows into a second table instead of returning them to the caller.
**Why there is no direct mapping.** PostgreSQL's `RETURNING` only ever
returns a result set to the caller; it has no `INTO <table>` redirect form.
**What Unique emits.** The plain `OUTPUT INSERTED.a` (no `INTO`) form maps
cleanly to `RETURNING a` (the `INSERTED.` qualifier is stripped, as above).
The `INTO log(a)` redirect itself has no PostgreSQL equivalent and is
dropped with a warning, rather than leaking the invalid `RETURNING
INSERTED.a` (PostgreSQL rejects `INSERTED` as an unqualified relation).
**Divergence & warning.** `[limit]` — the redirect into `log` is lost; the
base `INSERT` and its plain-`RETURNING` value are faithful.
**References.** `reda-ts-output-into`.

```sql
-- corpus case reda-ts-output-into
INSERT INTO t (a) OUTPUT INSERTED.a INTO log(a) VALUES (1)
-- PostgreSQL: INSERT INTO t (a) VALUES (1) RETURNING a
-- (the INTO log(a) redirect is dropped with a warning, not silently)
```

## Set-operation `ORDER BY`

### Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL

**Source semantics.** `SELECT … EXCEPT SELECT … ORDER BY a` orders the
**combined** result of the whole set operation.
**Why there is no direct mapping.** This is not a cross-engine gap — every
target supports `ORDER BY` on a set-operation result — so there is no
engine-level reason to drop it; the entry is here because the earlier
conversion **silently dropped** the `ORDER BY` on every target (a real
defect, not an approved limit).
**What Unique emits.** The `ORDER BY` is preserved on the whole set
operation: PostgreSQL/MySQL keep `EXCEPT`/`UNION` as-is; Oracle's `EXCEPT`
spells `MINUS`.
**Divergence & warning.** Faithful — the earlier silent drop made an ordered
result unordered with no warning.
**References.** `reda-ts-setop-orderby`.

```sql
-- corpus case reda-ts-setop-orderby (schematic: SELECT ... EXCEPT SELECT ... ORDER BY a)
-- PostgreSQL: ... EXCEPT ... ORDER BY a ASC NULLS FIRST
-- Oracle:     ... MINUS  ... ORDER BY a ASC NULLS FIRST
-- MySQL:      ... ORDER BY a ASC
```
