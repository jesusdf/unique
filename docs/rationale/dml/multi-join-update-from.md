[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Multi-join `UPDATE`" direction="tsql/postgresql → oracle/postgresql/mysql" kind=article order=8 -->

# Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL

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

**See Also.** [`test_embedded_dml_ir.py`](../../../tests/integration/test_embedded_dml_ir.py),
[`test_cross_dialect.py::TestCrossDialectDML`](../../../tests/integration/test_cross_dialect.py),
[`test_ir_first_families.py::TestZeroPushW3Batch`](../../../tests/unit/core/test_ir_first_families.py),
[`test_oracle_source_m4_wave.py::TestAliasedSingleTableUpdateOnTsql`](../../../tests/integration/test_oracle_source_m4_wave.py)
· "Multi-table `DELETE … JOIN`" entry above (sibling mechanism).
