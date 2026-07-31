[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`MERGE` / upsert lowering" direction="tsql → oracle/mysql" kind=article order=5 -->

# A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL

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

**See Also.** [`reda-ts-cte-merge`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
