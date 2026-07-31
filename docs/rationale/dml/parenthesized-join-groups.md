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
-- T-SQL / MySQL:
SELECT xx1 FROM (SELECT * FROM x) AS xx(xx1, xx2)

select * from y left join x as xx(xx1, xx2) on y1 = xx1;
-- T-SQL / MySQL:
SELECT * FROM y LEFT JOIN (SELECT * FROM x) AS xx(xx1, xx2) ON y1 = xx1

-- Oracle: whole-statement carrier + warning (UNIQUE-1003) — see Discussion.
```

Live-verified (T-SQL and MySQL 8, `x(c1=7, c2=8)`):
`SELECT xx1 FROM (SELECT * FROM x) AS xx(xx1, xx2)` returns `7` on both
engines — the renamed `xx1` really is `x`'s first column. Live-verified
(T-SQL, `t1(1),(2)`, `t2(1)`, `t3(100),(200)`): the unwrapped
join-plus-cross-join returns the expected 4-row result, `USING` correctly
rewritten to `x.a = y.a` and the trailing comma-join to `t3` rewritten to
an explicit `CROSS JOIN`.

**Discussion.** Parentheses around a join tree are semantically
transparent — they only group; they never scope anything the way a derived
table's `ORDER BY` does (see the entries above) — so the group unwraps and
its table and joins hoist straight into the outer `FROM` list, preserving
emission order so the surrounding comma-join grouping still reads
correctly.

The column-aliased table reference is the opposite case: it *is* a real
rewrite (positional column renaming). Neither T-SQL nor MySQL accepts a
column-alias list on a plain base-table reference — only on a derived
table — so `tbl AS alias(c1, c2)` becomes `(SELECT * FROM tbl) AS
alias(c1, c2)` on both. Oracle has no equivalent at all —
`SELECT xx1 FROM (SELECT * FROM x) xx(xx1, xx2)` is a live `ORA-03048`
syntax error (verified directly against Oracle) — so the whole statement
degrades to a documented carrier there.

> **Note** faithful for the unwrap and for the T-SQL/MySQL derived-table
> rewrite (both live-verified above).
> **Warning** Oracle has no spelling for a column-aliased table reference;
> the whole statement degrades to a carrier there (live `ORA-03048`).

**See Also.** [`test_pg_source_wave1.py::TestParenthesizedJoinRelations`](../../../tests/integration/test_pg_source_wave1.py),
[`test_pg_source_wave1.py::TestTableColumnAliases`](../../../tests/integration/test_pg_source_wave1.py).
