[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom" direction="cross-engine" kind=article order=8 direction-inferred=true -->

# `CREATE TABLE AS SELECT` ↔ `SELECT ... INTO` for ordinary (non-temporary) tables

**Problem.** This extends the entry above from *temp* tables specifically
to *any* table: T-SQL has no `CREATE TABLE ... AS SELECT` syntax at all —
whether or not the table is session-scoped — so any CTAS from another
source dialect must become a T-SQL `SELECT ... INTO`. The same idiom runs
in reverse: a plain (non-temp) `SELECT ... INTO newtable` from PostgreSQL or
T-SQL has no equivalent on MySQL or Oracle, so it becomes their own
`CREATE TABLE ... AS SELECT`.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestTsqlCtasBecomesSelectInto
create temporary table tmp as select a, b from t3;
-- mysql -> tsql:
SELECT a, b
INTO #tmp
FROM t3
```

```sql
-- corpus case ts-select-into
CREATE TABLE src (id INT);
GO
SELECT id INTO dst FROM src
-- tsql -> oracle:
CREATE TABLE dst AS SELECT id FROM src;
```

```sql
-- tests/integration/test_cross_dialect.py::TestDDLPassthrough::test_select_into_table_to_mysql
SELECT a, b INTO new_table FROM src WHERE id > 0
-- tsql -> mysql:
CREATE TABLE new_table AS SELECT a, b FROM src WHERE id > 0;
```

A CTAS onto a target that already supports the syntax natively is kept as
CTAS, not routed through the T-SQL `SELECT INTO` shape at all
(`test_ctas_kept_on_oracle`: `create table tmp2 as select 1 as x;` from
MySQL stays `CREATE TABLE tmp2 AS SELECT 1 AS x FROM DUAL` on Oracle), and
the reverse direction is likewise left alone whenever the target already
has `SELECT ... INTO` natively
(`test_select_into_table_preserved`: PostgreSQL and Oracle both keep the
literal `SELECT ... INTO newtable` form from a T-SQL source).

**Discussion.** Unlike the temp-table entry above — which is about a
*semantic* mismatch (commit-surviving rows vs. Oracle's transaction-scoped
default) — this is a pure *syntax-availability* gap: T-SQL simply has no
`CREATE TABLE ... AS SELECT` grammar production, temp or not, and MySQL/
Oracle have no `SELECT ... INTO` grammar production. Recognizing "this is a
table-creating query" and re-spelling it in whichever of the two idioms the
target actually supports is the same rewrite as the temp-table case above,
just without the `ON COMMIT` semantics layered on top — hence extending
this entry rather than filing an unrelated one.

> **Note** faithful — same resulting table and rows on every target; only
> the surface syntax changes to match whichever of the two idioms
> (`SELECT ... INTO` / `CREATE TABLE ... AS SELECT`) the target actually
> supports.

**See Also.** [`ts-select-into`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestTsqlCtasBecomesSelectInto`](../../../tests/integration/test_pg_source_wave1.py) ·
[`TestDDLPassthrough`](../../../tests/integration/test_cross_dialect.py).
