[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`MERGE` / upsert lowering" direction="tsql → oracle/postgresql" kind=article order=3 -->

# `WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle

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

**See Also.** [`ts-merge-full`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
