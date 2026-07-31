[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Set-operation `ORDER BY`" direction="cross-engine" kind=article order=14 direction-inferred=true -->

# `ORDER BY` inside a joined derived table (any source) → T-SQL: kept only with a row cap

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

**See Also.** [`test_ir_first_families.py::TestZeroPushW3Batch`](../../../tests/unit/core/test_ir_first_families.py).
