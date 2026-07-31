[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Multi-table `DELETE`" direction="tsql → oracle/postgresql/mysql" kind=article order=7 -->

# `DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL

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

**See Also.** [`reda-ts-delete-top`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
