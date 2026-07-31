[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`OUTPUT` / `RETURNING`" direction="tsql → oracle/postgresql" kind=article order=11 -->

# `INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier

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

**See Also.** [`ts-insert-output`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-update-output`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[§3.7](../../03-unsupported.md) (the MySQL side of the same gap) ·
[`UNIQUE-1212`](../../reference/warnings.md#unique-1212).
