# DML: PIVOT/UNPIVOT, MERGE, DELETE, row values

`PIVOT`/`UNPIVOT` relation rewrites, `MERGE`/upsert lowering, multi-table
`DELETE`, multi-join `UPDATE`, row caps, row-value comparisons,
`OUTPUT`/`RETURNING`, set-operation `ORDER BY`, Oracle's join-mark/`ROWNUM`/
`DUAL` idioms as a *source*, PostgreSQL's portable row-source rewrites
(`VALUES`/`generate_series`), and parenthesized-structure
unwrapping/shielding in `FROM`. See [README.md](README.md) for the entry
format and sourcing rules.

## `PIVOT` / `UNPIVOT`

### `PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL

**Problem.** `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows
into columns for a small, explicit set of pivot values, aggregating `arg` per
value.

**Solution.**

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

T-SQL keeps its native `PIVOT`; Oracle re-spells the
`IN`-list with explicit aliases (`PIVOT (SUM(v) FOR dept IN ('A' AS A, 'B' AS
B))`). PostgreSQL/MySQL get a conditional-aggregation derived table —
`SUM(CASE WHEN dept = 'A' THEN v END) AS A` per pivot value, grouped by every
source column that is neither the pivot column nor the aggregate argument.
When the source's projected columns are not visible (a bare table or
`SELECT *`), the grouping columns cannot be determined and the relation
degrades to a warned carrier instead (`emit_relations.py::_emit_pivot_relation`).

**Discussion.** PostgreSQL and MySQL have no `PIVOT`
operator at all. Oracle keeps `PIVOT` natively but needs an explicit
`'v' AS v` alias in the `IN`-list so its output columns are named like
T-SQL's default `[v]` bracket naming.

> **Note** faithful when the source projection is visible.
> `[limit]` (warned carrier) otherwise. The original conversion silently
> **dropped the whole `PIVOT` operator** with no warning — a defect this
> lowering replaced.

**See Also.** [`reda-ts-pivot`](../../tests/fixtures/challenge/challenge_sqlserver.sql) · [§2](../03-unsupported.md) (T-SQL
PIVOT/UNPIVOT row).

### `UNPIVOT` (T-SQL / Oracle) → all targets

**Problem.** `UNPIVOT (val FOR col IN (a, b))` turns columns `a`,
`b` into row pairs `(col, val)` — `col` carrying the *name* of the source
column, `val` its value.

**Solution.**

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

`SELECT <carried cols>, '<name>' AS col, <col> AS val
FROM <source> WHERE <col> IS NOT NULL` unioned per unpivoted column. When the
source's carried columns are not visible (no projection to name), it
degrades to a warned carrier instead.

**Discussion.** Unique renders `UNPIVOT` as a `UNION
ALL` (one arm per unpivoted column, `NULL`s excluded to match `UNPIVOT`'s
default) on **every** target, never the native `UNPIVOT` operator — even on
Oracle and T-SQL, which have one. The reason is the *name-column value*:
native `UNPIVOT` re-derives it from the `IN`-list identifier, and Oracle
folds an unquoted identifier to upper case, so Oracle's native `UNPIVOT`
yields `'A'` where T-SQL's yields `'a'` for the same source. The `UNION ALL`
rewrite instead emits an explicit string literal cased exactly as the
*source* engine would produce it, so the value matches across engines
(`emit_relations.py::_emit_unpivot_relation` docstring).

> **Note** faithful — values verified equal on
> Oracle/PostgreSQL/MySQL. `[limit]` (warned carrier) when the source
> projection is invisible.

**See Also.** [`ts-unpivot`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ora-unpivot`](../../tests/fixtures/challenge/challenge_oracle.sql).

## `MERGE` / upsert lowering

### `WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle

**Problem.** T-SQL's `MERGE` can act on target rows that have **no**
matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`)
— an anti-join over the `ON` predicate.

**Solution.**

```sql
-- corpus case ts-merge-full
MERGE tgt USING src ON tgt.id = src.id
  WHEN MATCHED AND src.n > 0 THEN UPDATE SET n = src.n
  WHEN MATCHED THEN DELETE
  WHEN NOT MATCHED BY TARGET THEN INSERT (id, n) VALUES (src.id, src.n)
  WHEN NOT MATCHED BY SOURCE THEN DELETE;
```

Each `WHEN NOT MATCHED BY SOURCE` clause becomes a
**follow-up statement** — `UPDATE`/`DELETE … WHERE NOT EXISTS (SELECT 1 FROM
<using> WHERE <on>) [AND (<condition>)]` — run after the `MERGE`. Because the
follow-up's anti-join addresses exactly the rows the `MERGE` itself cannot
touch, the two-statement split is value-equivalent to a single native
statement (`emit.py::_merge_extended_clauses` docstring).

**Discussion.** `WHEN NOT MATCHED BY SOURCE` exists
nowhere else (PostgreSQL only gained it in 17, and Unique's PG target does
not assume 17; Oracle's `MERGE` has no such clause at all).

> **Note** faithful — live-verified identical final rows on
> T-SQL/Oracle/PostgreSQL.

**See Also.** [`ts-merge-full`](../../tests/fixtures/challenge/challenge_sqlserver.sql).

### Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold

**Problem.** A T-SQL `MERGE` may carry two conditional `WHEN
MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`.

**Solution.** The pair folds into one Oracle `UPDATE` (whose `SET`
keeps the old value via `CASE` where the update should not apply) plus a
spliced `DELETE WHERE` tail — but **only** when the fold is value-safe: the
`DELETE` condition must reference no target column the `UPDATE` assigns. When
it does (the post-update semantics would delete rows T-SQL keeps), the whole
`MERGE` degrades to a carrier + warning instead of shipping silently-wrong
output.

**Discussion.** Oracle's `MERGE` grammar allows only a
**single** `WHEN MATCHED` clause; conditional forms are spelled as an
`UPDATE … WHERE` plus a trailing `DELETE WHERE` tail on the same clause, not
two separate `WHEN` branches — and critically, Oracle's `DELETE WHERE`
evaluates against the **post-update** row, while T-SQL evaluates the
original (pre-update) row.

> **Note** faithful in the safe shape (live-verified
> identical rows). Full warned carrier in the unsafe shape.

**See Also.** [§3.6](../03-unsupported.md) (MERGE clause composition,
audit 2026-07-24).

### A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL

**Problem.** `WITH src AS (…) MERGE INTO t USING src ON … WHEN
MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s
`USING` source is itself a named CTE.

**Solution.**

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

The CTE body is **inlined** at its use site instead
of kept as a separate `WITH`: Oracle's `MERGE INTO t USING (<cte body>) src
…`, MySQL's `INSERT INTO t (…) SELECT … FROM (<cte body>) AS src`.

**Discussion.** Oracle forbids a leading `WITH` before
`MERGE` (`ORA-00928`). MySQL has no `MERGE` at all — Unique's MySQL upsert
lowering (`INSERT … SELECT … ON DUPLICATE KEY UPDATE`) referenced the CTE
name (`src`) in its `SELECT … FROM src`, but on its own dropped the `WITH src
AS (…)` that defines it, leaving `src` undefined (MySQL error 1146).

> **Note** faithful — both targets now produce a valid,
> value-equivalent statement instead of an undefined-relation error.

**See Also.** [`reda-ts-cte-merge`](../../tests/fixtures/challenge/challenge_sqlserver.sql).

## Multi-table `DELETE`

### Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle

**Problem.** `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1`
deletes rows from `t1` filtered by a join against `t2`.

**Solution.**

```sql
-- corpus case my-multitable-delete-join
DELETE t1 FROM redb_d1 t1 JOIN redb_d2 t2 ON t1.id = t2.id WHERE t2.flag = 1
-- PostgreSQL: DELETE FROM redb_d1 t1 USING redb_d2 t2 WHERE t1.id = t2.id AND t2.flag = 1
-- T-SQL:      DELETE t1 FROM redb_d1 t1, redb_d2 t2 WHERE t1.id = t2.id AND t2.flag = 1
-- Oracle:     DELETE FROM redb_d1 t1
--             WHERE EXISTS (SELECT 1 FROM redb_d2 t2 WHERE t1.id = t2.id AND t2.flag = 1)
```

PostgreSQL: `DELETE FROM t1 USING t2 WHERE …`. T-SQL:
`DELETE t1 FROM t1, t2 WHERE …` (comma-joined, per `_emit_delete`). Oracle:
`DELETE FROM t1 WHERE EXISTS (SELECT 1 FROM t2 WHERE …)` — exact when the
`WHERE` clause **is** the join condition (the target's own columns stay
visible inside the correlated subquery).

**Discussion.** Each of the three targets spells a
join-filtered delete differently: PostgreSQL has no `DELETE … JOIN`, only
`DELETE … USING`; T-SQL spells it `DELETE t1 FROM t1, t2 WHERE …` (a
comma-join, not an `INNER JOIN`); Oracle's `DELETE` has no multi-table form
at all.

> **Note** faithful on all three.

**See Also.** [`my-multitable-delete-join`](../../tests/fixtures/challenge/challenge_mysql.sql), [`reda-ts-delete-join`](../../tests/fixtures/challenge/challenge_sqlserver.sql).

### `DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL

**Problem.** `DELETE TOP (n) FROM t WHERE …` caps the delete to `n`
**arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP`
without an `ORDER BY`, which `DELETE` cannot carry).

**Solution.**

```sql
-- corpus case reda-ts-delete-top
DELETE TOP (2) FROM t WHERE a > 0
-- MySQL:      DELETE FROM t WHERE a > 0 LIMIT 2
-- Oracle:     DELETE FROM t WHERE a > 0 AND ROWNUM <= 2
-- PostgreSQL: DELETE FROM t WHERE ctid IN (SELECT ctid FROM t WHERE a > 0 LIMIT 2)
```

Per-target row-cap forms (`emit_relations.py::_DELETE_CAP`):
MySQL trails `LIMIT n`; Oracle folds `ROWNUM <= n` into the `WHERE`;
PostgreSQL selects `n` candidate rows by `ctid` in a subquery
(`WHERE ctid IN (SELECT ctid FROM t WHERE … LIMIT n)`, since PostgreSQL's
`DELETE` has no `LIMIT`). All four cap the delete to `n` arbitrary matching
rows — faithful to `TOP`'s own unordered semantics.

**Discussion.** None of the other three engines has a
`TOP`-style row cap on `DELETE` in the same syntactic position; each needs a
different mechanism to bound the row count.

> **Note** faithful. The earlier defect **silently dropped**
> `TOP (n)` altogether, deleting every matching row instead of capping at `n`.

**See Also.** [`reda-ts-delete-top`](../../tests/fixtures/challenge/challenge_sqlserver.sql).

## Multi-join `UPDATE`

### Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL

**Problem.** `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d
ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter
off two or more joined tables the `UPDATE` itself never lists as its target
— the sibling mechanism to this page's multi-table `DELETE` above, but for
`UPDATE`.

**Solution.**

```sql
-- pinning tests: test_embedded_dml_ir.py::test_multijoin_cross_table_update_rewrites_for_oracle,
-- test_cross_dialect.py::TestCrossDialectDML, test_ir_first_families.py::TestZeroPushW3Batch
UPDATE t SET t.total = d.amount + c.fee
FROM t JOIN detail d ON d.tid = t.id JOIN charges c ON c.did = d.id
WHERE t.status = 1
-- Oracle:
UPDATE t
SET total = (SELECT d.amount + c.fee FROM detail d INNER JOIN charges c
             ON c.did = d.id WHERE d.tid = t.id)
WHERE EXISTS (SELECT 1 FROM detail d INNER JOIN charges c ON c.did = d.id
              WHERE d.tid = t.id) AND t.status = 1;
-- MySQL:
UPDATE t
INNER JOIN detail d ON d.tid = t.id
INNER JOIN charges c ON c.did = d.id
SET t.total = d.amount + c.fee
WHERE t.status = 1;
-- PostgreSQL:
UPDATE t
SET total = d.amount + c.fee
FROM detail d, charges c
WHERE d.tid = t.id AND c.did = d.id AND t.status = 1;

-- Live-verified (seed t(1,_,1) (2,_,1) (3,_,0); detail(10,1,100) (20,2,200);
-- charges(100,10,5) (200,20,7)): all four engines — Oracle, MySQL,
-- PostgreSQL and the T-SQL source itself — land on the identical rows
-- (1, 105, 1), (2, 207, 1), (3, 0, 0); row 3 (status=0) is untouched.
```

When the source itself spells its extra tables with a comma instead of an
explicit `JOIN … ON` (PostgreSQL's own `UPDATE v1 SET … FROM city_view v2
WHERE …`), the MySQL target mirrors that shape too — a comma-joined
`UPDATE t1, t2 SET …` — rather than always synthesizing an `INNER JOIN`:

```sql
-- pinning tests: test_ir_first_families.py::TestZeroPushW3Batch
--   (test_self_join_update_from_mysql_multi_table, test_comma_source_update_from_mysql)
UPDATE city_view AS v1 SET country_name = v2.country_name
FROM city_view AS v2 WHERE v2.city_name = 'B' AND v1.city_name = 'L'
-- MySQL:
UPDATE city_view v1, city_view v2
SET v1.country_name = v2.country_name
WHERE v2.city_name = 'B' AND v1.city_name = 'L';
```

A related but distinct problem shows up in the *other* direction. Oracle's
`UPDATE t alias SET …` can carry its own cross-table logic inside a
correlated scalar subquery (Oracle allows a bare alias with no `AS`), but
T-SQL's grammar rejects `UPDATE <table> <alias>` outright — the aliased
form must be spelled `UPDATE <alias> SET … FROM <table> <alias>`. Going
from Oracle to T-SQL, Unique restructures the statement into that form and
converts any `ROWNUM = 1` inside the subquery to `TOP 1` on the way:

```sql
-- pinning test: test_oracle_source_m4_wave.py::TestAliasedSingleTableUpdateOnTsql
UPDATE t_pue ep
SET idimp = (SELECT i.idimp FROM t_imp i WHERE i.imp = ep.imp AND ROWNUM = 1)
WHERE EXISTS (SELECT 1 FROM t_imp i WHERE i.imp = ep.imp)
-- T-SQL:
UPDATE ep
SET idimp = (SELECT TOP 1 i.idimp FROM t_imp i WHERE i.imp = ep.imp)
FROM t_pue AS ep
WHERE EXISTS (SELECT 1 FROM t_imp i WHERE i.imp = ep.imp)

-- Live-verified (seed t_pue(1,imp=10) (2,imp=20) (3,imp=30);
-- t_imp(imp=10,idimp=555) (imp=10,idimp=556) (imp=20,idimp=777)):
-- T-SQL lands (1,10,555) (2,20,777) (3,30,NULL) — row 1's TOP 1 picks one
-- of its two matching t_imp rows (arbitrary, no ORDER BY), row 3 has no
-- match so EXISTS is false and it stays untouched.
```

**Discussion.** Oracle has no `UPDATE … FROM` at all — the multi-join
source moves into a correlated scalar subquery in the `SET` list (the same
join tree evaluated once per candidate row), guarded by a matching `EXISTS`
in `WHERE` so a row with no join partner keeps its old value instead of
being set to `NULL`. MySQL's `UPDATE` has its own native multi-table join
grammar (`UPDATE t1 JOIN t2 ON … SET …`, or the comma form `UPDATE t1, t2
SET …`), so Unique renders the join tree there directly instead of through
a subquery — and reuses the source's own join spelling (explicit `JOIN …
ON` in, `JOIN … ON` out; comma in, comma out) rather than normalizing to
one shape, since both are valid MySQL `UPDATE`-join forms. PostgreSQL keeps
its own native `UPDATE … FROM … WHERE` form, needing only the join tree
flattened into the comma-separated `FROM` list with the `ON` predicates
folded into `WHERE`.

> **Note** faithful — live-verified identical final rows on Oracle, MySQL,
> PostgreSQL and T-SQL for the multi-join case (seed above). The
> Oracle-source aliased single-table form is faithful in the same
> "arbitrary row" sense as this page's `DELETE TOP (n)` and (below)
> `ROWNUM <= n` entries: `ROWNUM = 1`/`TOP 1` with no `ORDER BY` picks
> whichever matching row the engine produces first, not one specific row —
> live-verified `TOP 1` picks a real matching row on T-SQL.

**See Also.** [`test_embedded_dml_ir.py`](../../tests/integration/test_embedded_dml_ir.py),
[`test_cross_dialect.py::TestCrossDialectDML`](../../tests/integration/test_cross_dialect.py),
[`test_ir_first_families.py::TestZeroPushW3Batch`](../../tests/unit/core/test_ir_first_families.py),
[`test_oracle_source_m4_wave.py::TestAliasedSingleTableUpdateOnTsql`](../../tests/integration/test_oracle_source_m4_wave.py)
· "Multi-table `DELETE … JOIN`" entry above (sibling mechanism).

## Row-value comparisons

### Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL

**Problem.** `(a, b) > (1, 5)` is a lexicographic row-value
comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND
b > 5`.

**Solution.**

```sql
-- corpus case pg-row-value-comparison
SELECT * FROM t WHERE (a, b) > (1, 5)
-- T-SQL: WHERE a > 1 OR (a = 1 AND (b > 5))
```

T-SQL gets the comparison expanded lexicographically:
`a > 1 OR (a = 1 AND (b > 5))`.

**Discussion.** T-SQL has no row-value comparison syntax
at all; the tuple literal is rejected outright (error 4145, "non-boolean
type … where a condition is expected"). PostgreSQL, Oracle and MySQL all
accept it natively.

> **Note** faithful — PG native result `(3,4)`.

**See Also.** [`pg-row-value-comparison`](../../tests/fixtures/challenge/challenge_postgresql.sql).

### Row-value `IN` (Oracle) → T-SQL

**Problem.** `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN`
list, valid on Oracle/PostgreSQL/MySQL.

**Solution.** Expanded to an `OR`-of-`AND`-pairs form:
`(a = 1 AND b = 2) OR (a = 3 AND b = 4)`.

**Discussion.** T-SQL has no row-constructor `IN` either
(the same error 4145 as the inequality case above).

> **Note** faithful.

**See Also.** [`reda-ora-rowvalue-in`](../../tests/fixtures/challenge/challenge_oracle.sql) (neighbour of [`pg-row-value-comparison`](../../tests/fixtures/challenge/challenge_postgresql.sql)).

## `OUTPUT` / `RETURNING`

### `INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier

**Problem.** T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a
result set of the affected rows' before/after values alongside the DML.

**Solution.**

```sql
-- corpus case ts-insert-output
INSERT INTO t (n) OUTPUT INSERTED.id, INSERTED.n VALUES (10), (20)
-- PostgreSQL: INSERT INTO t (n) VALUES (10), (20) RETURNING id, n
-- Oracle: the INSERT runs; OUTPUT is documented in a carrier (no RETURNING
-- result set — ORA-63809 forbids a standalone one)
```

PostgreSQL: `RETURNING` with the `INSERTED`/`DELETED`
qualifier stripped from each item (`_prefix_tsql_output_items` performs the
reverse: it re-adds the qualifier when going the other direction). Oracle:
the `INSERT`/`UPDATE`/`DELETE` itself still runs; the `OUTPUT` result set is
documented in a carrier + warning rather than attempted.

**Discussion.** PostgreSQL's `RETURNING` is a direct,
faithful equivalent (`INSERTED`→the new row, `DELETED`→the old row — a
`DELETE` only ever exposes `DELETED`). Oracle's `RETURNING` clause, though
named the same, is **PL/SQL-only**: it must target `INTO` bind variables and
cannot stand alone in a plain SQL statement (`ORA-63809` otherwise), so a
standalone `OUTPUT` has no Oracle equivalent at all.

> **Note** faithful on PostgreSQL. `[limit]` on Oracle — the
> DML effect is preserved, the returned result set is not.

**See Also.** [`ts-insert-output`](../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-update-output`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§3.7](../03-unsupported.md) (the MySQL side of the same gap) ·
[`UNIQUE-1212`](../reference/warnings.md#unique-1212).

### `OUTPUT … INTO` redirect (T-SQL) → PostgreSQL

**Problem.** `OUTPUT INSERTED.a INTO log(a)` redirects the output
rows into a second table instead of returning them to the caller.

**Solution.**

```sql
-- corpus case reda-ts-output-into
INSERT INTO t (a) OUTPUT INSERTED.a INTO log(a) VALUES (1)
-- PostgreSQL: INSERT INTO t (a) VALUES (1) RETURNING a
-- (the INTO log(a) redirect is dropped with a warning, not silently)
```

The plain `OUTPUT INSERTED.a` (no `INTO`) form maps
cleanly to `RETURNING a` (the `INSERTED.` qualifier is stripped, as above).
The `INTO log(a)` redirect itself has no PostgreSQL equivalent and is
dropped with a warning, rather than leaking the invalid `RETURNING
INSERTED.a` (PostgreSQL rejects `INSERTED` as an unqualified relation).

**Discussion.** PostgreSQL's `RETURNING` only ever
returns a result set to the caller; it has no `INTO <table>` redirect form.

> **Warning** `[limit]` — the redirect into `log` is lost; the
> base `INSERT` and its plain-`RETURNING` value are faithful.

**See Also.** [`reda-ts-output-into`](../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1137`](../reference/warnings.md#unique-1137) ·
[`UNIQUE-1139`](../reference/warnings.md#unique-1139).

## Set-operation `ORDER BY`

### Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL

**Problem.** `SELECT … EXCEPT SELECT … ORDER BY a` orders the
**combined** result of the whole set operation.

**Solution.**

```sql
-- corpus case reda-ts-setop-orderby (schematic: SELECT ... EXCEPT SELECT ... ORDER BY a)
-- PostgreSQL: ... EXCEPT ... ORDER BY a ASC NULLS FIRST
-- Oracle:     ... MINUS  ... ORDER BY a ASC NULLS FIRST
-- MySQL:      ... ORDER BY a ASC
```

The `ORDER BY` is preserved on the whole set
operation: PostgreSQL/MySQL keep `EXCEPT`/`UNION` as-is; Oracle's `EXCEPT`
spells `MINUS`.

**Discussion.** This is not a cross-engine gap — every
target supports `ORDER BY` on a set-operation result — so there is no
engine-level reason to drop it; the entry is here because the earlier
conversion **silently dropped** the `ORDER BY` on every target (a real
defect, not an approved limit).

> **Note** faithful — the earlier silent drop made an ordered
> result unordered with no warning.

**See Also.** [`reda-ts-setop-orderby`](../../tests/fixtures/challenge/challenge_sqlserver.sql).

### `ORDER BY` inside a joined derived table (any source) → T-SQL: kept only with a row cap

**Problem.** A derived table used as a join operand can carry its own
`ORDER BY` — e.g. to pick or arrange the rows it contributes — separately
from any `ORDER BY` on the outer query.

**Solution.**

```sql
-- pinning tests: test_ir_first_families.py::TestZeroPushW3Batch
--   (test_join_derived_table_order_by_stripped_tsql,
--    test_join_derived_table_order_by_kept_with_limit)
SELECT * FROM a FULL OUTER JOIN (SELECT * FROM b ORDER BY b.i DESC) d ON a.i = d.i
-- T-SQL:
SELECT * FROM a FULL OUTER JOIN (SELECT * FROM b) d ON a.i = d.i
-- (the ORDER BY is dropped — no TOP/OFFSET/FOR XML alongside it)

SELECT * FROM a JOIN (SELECT * FROM b ORDER BY c LIMIT 5) d ON a.x = d.x
-- T-SQL:
SELECT * FROM a INNER JOIN (SELECT TOP 5 * FROM b ORDER BY c ASC) d ON a.x = d.x
-- (kept — TOP makes the ORDER BY legal)
```

Live-verified: `SELECT * FROM (SELECT 1 AS i ORDER BY i DESC) d` fails on
SQL Server with error 1033, "The ORDER BY clause is invalid in views,
inline functions, derived tables, subqueries, and common table expressions,
unless TOP, OFFSET or FOR XML is also specified." Unique strips a bare
`ORDER BY` inside a derived table rather than shipping that error, and
keeps it whenever a `LIMIT`/`TOP`/`OFFSET` travels alongside it.

**Discussion.** T-SQL is the only one of the four target engines with this
restriction — PostgreSQL, MySQL and Oracle all accept an unqualified
`ORDER BY` inside a derived table. It is also not a real semantic loss:
standard SQL never guarantees a subquery's row order survives into its
consumer without an explicit `TOP`/`LIMIT`/`OFFSET` riding along, so a bare
`ORDER BY` inside a derived table that is only ever joined (never capped)
has no observable effect on the final result set on *any* engine — dropping
it for T-SQL removes dead syntax, not meaning.

> **Note** faithful — live-verified T-SQL syntax error (above) confirms the
> drop is required, not stylistic; the same "a row cap is what makes an
> otherwise-meaningless order meaningful" reasoning as this page's
> `DELETE TOP (n)` entry above and `ROWNUM <= n` entry below, applied here
> to a derived table instead of a `DELETE`/`SELECT`.

**See Also.** [`test_ir_first_families.py::TestZeroPushW3Batch`](../../tests/unit/core/test_ir_first_families.py).

## Oracle join syntax and row limits (source direction)

The entries below run **from** Oracle. The rest of this page (and
[§7](../03-unsupported.md) "To Oracle") documents the opposite direction —
a T-SQL/PostgreSQL comma-join or parenthesized join tree flattened *onto*
Oracle — which is a different mechanism (Oracle's `FROM` grammar rejects a
parenthesized join tree, ORA-00907); do not confuse the two.

### Oracle `(+)` outer-join mark → explicit `LEFT JOIN … ON`; comma joins → `CROSS JOIN`

**Problem.** Oracle's legacy join syntax has no `JOIN` keyword at all: tables
are comma-listed in `FROM`, and `col(+)` on one side of a `WHERE` predicate
marks that table as the *optional* (outer) side of the join — the row is
still produced, NULL-extended, when no match exists.

**Solution.**

```sql
-- pinning test: tests/unit/core/test_oracle_join_mark.py::TestOracleJoinMark
-- (no challenge-corpus case yet)
SELECT a.x, b.y FROM ta a, tb b WHERE a.id = b.id(+)
-- PostgreSQL / MySQL / T-SQL:
SELECT a.x, b.y FROM ta a LEFT JOIN tb b ON a.id = b.id

-- a comma join with no (+) mark at all:
SELECT a.x FROM a, b WHERE a.id = b.id
-- -> FROM a CROSS JOIN b WHERE a.id = b.id   (not INNER JOIN: there is no ON)
```

Live-verified (Oracle, PostgreSQL, MySQL, T-SQL; seed rows `ta(1,'a1')
(2,'a2') (3,'a3')`, `tb(1,'b1') (2,'b2')`): all four return `('a1','b1')
('a2','b2') ('a3', NULL)` for the query above — the unmatched `ta` row keeps
its NULL-extended `b.y`.

**Discussion.** `(+)` and the bare comma join are Oracle-only syntax with no
target-engine equivalent, so the join must be reconstructed explicitly. A
comma join carries no `ON` clause to promote into `INNER JOIN`, so it becomes
`CROSS JOIN` (the faithful unfiltered Cartesian product) plus the original
predicate in `WHERE`, never a guessed `INNER JOIN` — emitting `INNER JOIN` with
no `ON` is invalid on every target, and inferring one from an unrelated
`WHERE` predicate would silently change which rows survive. `(+)` similarly
becomes an explicit `LEFT JOIN … ON`, with the marked side moved to the
outer/right position: an early version emitted `INNER JOIN` with no `ON` at
all here too — a syntax error on PostgreSQL/MySQL/T-SQL and a silent
LEFT→INNER semantic change everywhere.

> **Note** faithful — live-verified identical rows on Oracle, PostgreSQL,
> MySQL and T-SQL (see above).

**See Also.** [`tests/unit/core/test_oracle_join_mark.py`](../../tests/unit/core/test_oracle_join_mark.py)
(note: this test lives in `tests/unit/core/`, not `tests/integration/`) ·
challenge `red2-ora-plus-outer-join-dup` (`tests/fixtures/challenge/challenge_oracle.sql`,
tagged `[fixed]`) is a **related but distinct**, already-fixed defect — a
table with *two* `(+)` predicates used to duplicate that table's join into an
extra `CROSS JOIN` — which this single-predicate mechanism never exhibited ·
[§7](../03-unsupported.md) "To Oracle" (the reverse-direction
parenthesized-join-tree gate).

### `ROWNUM <= n` (Oracle) → `LIMIT` / `TOP` / `FETCH FIRST`

**Problem.** Oracle's `ROWNUM` is a pseudo-column numbering rows as they are
produced; `WHERE ROWNUM <= n` is Oracle's idiom for capping a result to `n`
rows — with no ordering guarantee unless paired with an `ORDER BY` (the
`ROWNUM` filter applies before any sort).

**Solution.**

```sql
-- pinning test: tests/unit/core/test_rownum_dual.py::TestRownum
-- (no challenge-corpus case yet)
SELECT * FROM t WHERE ROWNUM <= 5
-- PostgreSQL / MySQL: SELECT * FROM t LIMIT 5
-- T-SQL:              SELECT TOP 5 * FROM t
```

`ROWNUM <= n` / `ROWNUM < n+1` folds to a plain `LIMIT n` (PostgreSQL/MySQL)
or `TOP n` (T-SQL); a `ROWNUM` predicate ANDed with another condition keeps
that condition in `WHERE` and only the row cap moves. Live-verified
(seed rows `1, 2, 3`): Oracle's `WHERE ROWNUM <= 2` and PostgreSQL's
`LIMIT 2` both return exactly 2 of the 3 rows.

**Discussion.** No other engine has a pseudo-column numbering rows before
`ORDER BY`; each target's own row-cap clause is the direct equivalent for the
common `ROWNUM <= n` idiom. `ROWNUM` used outside a simple upper-bound
predicate (e.g. projected in the select list, compared with `>`, or assigned
to a variable) has no such direct rewrite and is signalled rather than
silently passed through or dropped.

> **Note** faithful for the `ROWNUM <= n` / `< n+1` upper-bound form — same
> row *count* as Oracle's own (both are unordered without an explicit
> `ORDER BY`, mirroring this page's "`DELETE TOP (n)` row caps" entry's
> "faithful to `TOP`'s own unordered semantics" reasoning, applied here to a
> read instead of a delete). `[limit]` (warned) for any other `ROWNUM` shape.

**See Also.** [`tests/unit/core/test_rownum_dual.py::TestRownum`](../../tests/unit/core/test_rownum_dual.py)
(note: lives in `tests/unit/core/`, not `tests/integration/`).

### `FROM DUAL` synthesis and removal (bidirectional)

**Problem.** Oracle has no table-less `SELECT` — `SELECT 1` is
`ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's
answer is `DUAL`, a one-row system table. Every other engine allows (or, for
MySQL, merely tolerates) a bare `SELECT` with no `FROM` at all.

**Solution.**

```sql
-- pinning test: tests/unit/core/test_rownum_dual.py::TestFromDual
SELECT 1 FROM dual                    -- Oracle source
-- PostgreSQL / T-SQL: SELECT 1                 (DUAL dropped)
-- MySQL:              SELECT 1 FROM dual       (DUAL kept - MySQL accepts it)

SELECT 1                              -- T-SQL/MySQL source, Oracle target
-- Oracle: SELECT 1 FROM DUAL                    (DUAL synthesized)
```

Going **from** Oracle, `FROM dual` is dropped for PostgreSQL and T-SQL (a
bare `SELECT 1` is valid on both) but kept for MySQL, which also accepts
`FROM DUAL` natively — dropping it there would be gratuitous churn, not a
correctness fix. Going **to** Oracle from any table-less source `SELECT`
(T-SQL, MySQL, or an Oracle round-trip), `FROM DUAL` is synthesized so the
statement stays valid Oracle; a `SELECT` that already has a real `FROM`
clause is left untouched, and a leading comment on the statement survives the
rewrite.

**Discussion.** `DUAL` is a real, literal table name on every engine that
recognizes it (Oracle, MySQL) — not a keyword — so it cannot be mapped, only
added or removed depending on whether the target requires (Oracle), accepts
(MySQL) or has no use for (PostgreSQL/T-SQL) a `FROM`-less scalar `SELECT`.

> **Note** faithful — a one-row scalar `SELECT` returns the same single row
> whether or not `FROM (DUAL|dual)` is present/absent on a target that
> tolerates both forms.

**See Also.** [`tests/unit/core/test_rownum_dual.py::TestFromDual`](../../tests/unit/core/test_rownum_dual.py).

## Portable row-source rewrites (PostgreSQL)

### `FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)

**Problem.** PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source,
usable directly as a `FROM` item, as the operand of a quantified comparison
(`n > ALL (VALUES …)`), or with a column-aliased `v(x)`.

**Solution.**

```sql
-- corpus case pg-avg-null
SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)
-- T-SQL:
SELECT AVG((x) * 1.0)
FROM (SELECT 1 AS x UNION ALL SELECT 2 UNION ALL SELECT NULL UNION ALL SELECT 4) v
-- Oracle:
SELECT AVG(x)
FROM (SELECT 1 AS x FROM DUAL UNION ALL SELECT 2 FROM DUAL
      UNION ALL SELECT NULL FROM DUAL UNION ALL SELECT 4 FROM DUAL) v;
-- MySQL:
SELECT AVG(x)
FROM (SELECT 1 AS x UNION ALL SELECT 2 UNION ALL SELECT NULL UNION ALL SELECT 4) v;

-- corpus case pg-all-values (quantified form)
SELECT id FROM t WHERE n > ALL (VALUES (1),(2),(3))
-- Oracle:
SELECT id FROM t
WHERE n > ALL (SELECT 1 FROM DUAL UNION ALL SELECT 2 FROM DUAL UNION ALL SELECT 3 FROM DUAL);
```

Every `VALUES (…)` row list used as a *relation* (a `FROM` item or a
quantified-comparison subquery operand — not an `INSERT … VALUES` row list,
which every target keeps natively) is rewritten to a `SELECT <v1> UNION ALL
SELECT <v2> UNION ALL …` chain, even on T-SQL and MySQL, which both accept
`VALUES` as a table constructor natively. (T-SQL's `AVG` also gets its own,
separate integer-average promotion here; Oracle appends `FROM DUAL` to
every arm, per the "`FROM DUAL` synthesis" entry above.)

**Discussion.** The `UNION ALL` chain is not a per-engine compensation for
a missing feature — T-SQL and MySQL both support `VALUES (…)` as a `FROM`
row source. It is used because a **bare** `VALUES (…)` list is not a valid
subquery *expression* on MySQL, Oracle or T-SQL: only PostgreSQL treats
`VALUES` itself as a first-class query the way it treats `SELECT`, so `n >
ALL (VALUES (1),(2),(3))` — a `VALUES` list used directly as a quantified
comparison's operand — has no direct spelling on the other three at all.
The `SELECT … UNION ALL …` chain is a row source every target accepts in
every position a `VALUES` list can appear (including this one), so Unique
renders it uniformly rather than special-casing the one or two positions
(T-SQL/MySQL `FROM`) where a native `VALUES` would actually parse.

> **Note** faithful — corpus `pg-avg-null` is live-verified equal (same
> value, engine-specific decimal scale — precision-only diff, maintainer
> policy 2026-07-19); corpus `pg-all-values` is live-executed on
> T-SQL/Oracle/MySQL.

**See Also.** [`pg-avg-null`, `pg-all-values`](../../tests/fixtures/challenge/challenge_postgresql.sql)
· "`FROM DUAL` synthesis and removal" entry above.

### `FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)

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
`pg-gen-series-date`, `pg-generate-series`](../../tests/fixtures/challenge/challenge_postgresql.sql)
· [`test_challenge.py::TestGenerateSeriesFrom`](../../tests/integration/test_challenge.py).

## Parenthesized-structure unwrapping and shielding

### Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded

**Problem.** `(SELECT …) UNION ALL (SELECT …)` parenthesizes each arm of a
set operation — often just for readability, but sometimes because one arm
carries its own `ORDER BY`/`LIMIT` that must apply to *that arm alone*, not
to the combined result.

**Solution.**

```sql
-- pinning tests: test_pg_source_wave1.py::TestParenthesizedUnionArms
(select * from t1) union all (select * from t2);
-- PostgreSQL:
SELECT * FROM t1 UNION ALL SELECT * FROM t2;   -- (parens just dropped)

select a from t1 union all (select a from t2 order by a limit 1);
-- PostgreSQL:
SELECT a FROM t1
UNION ALL
SELECT * FROM (SELECT a FROM t2 ORDER BY a ASC NULLS FIRST LIMIT 1) uq_setarm;

(select a from t1 limit 2) union all (select a from t2) order by a;
-- PostgreSQL:
SELECT * FROM (SELECT a FROM t1 LIMIT 2) uq_setarm
UNION ALL
SELECT a FROM t2
ORDER BY a ASC NULLS FIRST;
```

Live-verified (`t1(3,1)`, `t2(9,2,5)`): the shielded-second-arm example
returns `(3),(1),(2)` — `t2`'s contribution is exactly its single smallest
row, proving the `ORDER BY … LIMIT 1` scoped to that arm alone rather than
to the whole union.

A parenthesized arm with **no** `ORDER BY`/`LIMIT` of its own just has its
parentheses dropped. An arm that does carry one gets wrapped in a
synthesized derived table (`uq_setarm`) instead, and the set operation's own
trailing `ORDER BY`/`LIMIT`, if any, still attaches to the combined result
as normal.

**Discussion.** A parenthesized arm arrives from sqlglot as a `Subquery`
wrapping a `Select`; the earlier converter read that wrapper as an empty
select, shipping `SELECT * UNION ALL SELECT *` with the arm's own `FROM`
and columns dropped entirely. The fix unwraps the arm's real `FROM`/columns
— but a plain unwrap is not always safe: an arm's own `ORDER BY`/`LIMIT`,
once unparenthesized, would bind to the **whole** set operation rather than
to the arm it belongs to (true on every target: a trailing `ORDER BY`/
`LIMIT` after the last arm of a `UNION`/`EXCEPT`/`INTERSECT` always scopes
to the combined result, never to one arm). So an arm carrying one of those
clauses is wrapped in a derived table instead of unwrapped bare, keeping
its original per-arm scope.

> **Note** faithful — live-verified above.

**See Also.** [`test_pg_source_wave1.py::TestParenthesizedUnionArms`](../../tests/integration/test_pg_source_wave1.py)
· "`ORDER BY` inside a joined derived table" entry above (a sibling
shielding mechanism, different trigger).

### Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table

**Problem.** Two different `FROM`-clause shapes both need restructuring,
for opposite reasons: a **parenthesized join group** — `FROM (t1 JOIN t2 ON
…), t3` — groups a join tree for readability with no semantic effect of its
own; a **column-aliased table reference** — PostgreSQL's `tbl AS
alias(col1, col2)` — renames the table's columns positionally, a real
semantic operation most targets cannot spell against a plain table
reference at all.

**Solution.**

```sql
-- pinning tests: test_pg_source_wave1.py::TestParenthesizedJoinRelations
select * from (t1 as x left join t2 as y using (a)), t3;
-- T-SQL:
SELECT * FROM t1 x LEFT JOIN t2 y ON x.a = y.a CROSS JOIN t3

select * from (t1 left join t2 on t1.a = t2.a);
-- PostgreSQL:
SELECT * FROM t1 LEFT JOIN t2 ON t1.a = t2.a;
```

```sql
-- pinning tests: test_pg_source_wave1.py::TestTableColumnAliases
select xx1 from x as xx(xx1, xx2);
-- T-SQL:
SELECT xx1 FROM (SELECT * FROM x) AS xx(xx1, xx2)

select * from y left join x as xx(xx1, xx2) on y1 = xx1;
-- T-SQL:
SELECT * FROM y LEFT JOIN (SELECT * FROM x) AS xx(xx1, xx2) ON y1 = xx1

-- MySQL/Oracle: whole-statement carrier + warning (UNIQUE-1003) —
-- see Discussion.
```

Live-verified (T-SQL, `x(c1=7, c2=8)`):
`SELECT xx1 FROM (SELECT * FROM x) AS xx(xx1, xx2)` returns `7` — the
renamed `xx1` really is `x`'s first column. Live-verified (T-SQL,
`t1(1),(2)`, `t2(1)`, `t3(100),(200)`): the unwrapped join-plus-cross-join
returns the expected 4-row result, `USING` correctly rewritten to `x.a =
y.a` and the trailing comma-join to `t3` rewritten to an explicit `CROSS
JOIN`.

**Discussion.** The parenthesized join group arrives from sqlglot as a
`Subquery` wrapping a `Table`, carrying its own `joins` list the converter
previously never read — the whole group, `USING` clause included, shipped
raw and unparsed. Since parentheses around a join tree are semantically
transparent (they only group; they never scope anything the way a derived
table's `ORDER BY` does — see the entries above), the fix unwraps the group
and hoists its table and joins straight into the outer `FROM` list,
preserving emission order so the surrounding comma-join grouping still
reads correctly.

The column-aliased table reference is the opposite case: it *is* a real
rewrite (positional column renaming). T-SQL accepts a derived table's own
column-alias list, so `tbl AS alias(c1, c2)` becomes `(SELECT * FROM tbl)
AS alias(c1, c2)` there. Oracle genuinely has no equivalent at all —
`SELECT xx1 FROM (SELECT * FROM x) xx(xx1, xx2)` is a live `ORA-03048`
syntax error (verified directly against Oracle) — so the Oracle degrade is
a real engine limit. **MySQL's degrade, however, does not appear to be
one**: MySQL 8 accepts the identical derived-table column-alias syntax
live (`SELECT xx1 FROM (SELECT * FROM x) AS xx(xx1, xx2)` runs and returns
the aliased column, verified directly against MySQL), yet the current gate
(`transformer.py::_gate_column_alias_ref`) degrades MySQL together with
Oracle and its docstring asserts neither engine "has the spelling." That
docstring claim is accurate for Oracle but not for MySQL as tested here —
flagged as a discrepancy for a maintainer to evaluate (a possible fix, not
an approved permanent limit); this entry documents the transpiler's
current, live behavior rather than asserting the MySQL degrade is required.

> **Note** faithful for the unwrap (live-verified above) and for the T-SQL
> column-alias rewrite (live-verified above). Oracle's whole-degrade is a
> genuine engine limit (live `ORA-03048`, verified). MySQL's whole-degrade
> is the current, live transpiler behavior — not independently verified as
> *required*; see Discussion.

**See Also.** [`test_pg_source_wave1.py::TestParenthesizedJoinRelations`](../../tests/integration/test_pg_source_wave1.py),
[`test_pg_source_wave1.py::TestTableColumnAliases`](../../tests/integration/test_pg_source_wave1.py).
