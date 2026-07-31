[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Parenthesized-structure unwrapping and shielding" direction="cross-engine" kind=article order=22 direction-inferred=true -->

# Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table

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

**See Also.** [`test_pg_source_wave1.py::TestParenthesizedJoinRelations`](../../../tests/integration/test_pg_source_wave1.py),
[`test_pg_source_wave1.py::TestTableColumnAliases`](../../../tests/integration/test_pg_source_wave1.py).
