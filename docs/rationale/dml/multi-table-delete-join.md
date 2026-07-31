[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Multi-table `DELETE`" direction="mysql → tsql/oracle/postgresql" kind=article order=6 -->

# Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle

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

**See Also.** [`my-multitable-delete-join`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`reda-ts-delete-join`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
