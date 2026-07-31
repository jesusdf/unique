[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="tsql → postgresql" kind=article order=23 -->

# T-SQL `INSTEAD OF` trigger → PostgreSQL (native on views, emulated on tables)

**Problem.** T-SQL allows `INSTEAD OF` on both views *and* base tables — the
trigger body runs **instead of** the attempted INSERT/UPDATE/DELETE, which is
never applied on its own. PostgreSQL's `INSTEAD OF` exists too, but **only**
on views (a table raises "... instead of triggers are only for views").

**Solution.** On a view, the mapping is direct:

```sql
-- corpus case ts-trigger-on-view
CREATE VIEW v AS SELECT id FROM t;
CREATE TRIGGER trg ON v INSTEAD OF INSERT AS BEGIN INSERT INTO t SELECT id FROM inserted; END
-- tsql -> postgresql:
CREATE OR REPLACE TRIGGER trg
INSTEAD OF INSERT ON v
FOR EACH ROW EXECUTE FUNCTION trg_func();
-- (trg_func() body: INSERT INTO t SELECT NEW.id; RETURN NEW;)
```

On a base table, PostgreSQL has nothing to map to at all, so Unique emulates
the "runs instead, never both" contract with a `BEFORE` row trigger plus a
`pg_trigger_depth()` guard: the body's own DML re-enters the same trigger one
level deeper, where the guard lets it through; the *original* attempted row
is always suppressed (`RETURN NULL`) at depth 1:

```sql
-- corpus case ts-instead-of-insert
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id, n FROM inserted; END
-- tsql -> postgresql:
CREATE OR REPLACE FUNCTION trg_func()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;
    INSERT INTO t (id, n) SELECT NEW.id, NEW.n;
    RETURN NULL;
END;
$$;
CREATE OR REPLACE TRIGGER trg
BEFORE INSERT ON t
FOR EACH ROW EXECUTE FUNCTION trg_func();
```

A `DELETE` guard returns `OLD` (not `NEW`, which is `NULL` on `DELETE`) at
depth > 1, so the recursive delete is allowed through instead of silently
no-opping:

```sql
-- corpus case ts-trg-instead-delete
CREATE TRIGGER g ON t INSTEAD OF DELETE AS BEGIN DELETE FROM t WHERE id IN (SELECT id FROM deleted WHERE id>0); END
-- tsql -> postgresql:
IF pg_trigger_depth() > 1 THEN
    RETURN OLD;
END IF;
DELETE FROM t WHERE id IN (SELECT OLD.id WHERE OLD.id > 0);
RETURN NULL;
```

**Discussion.** PostgreSQL's row-level restriction (`FOR EACH ROW` only —
`INSTEAD OF` has no statement-level form in PostgreSQL) means the emulation
fires once per originating row, recursing once per row to perform its own
single-row insert/delete, where the source body's `SELECT ... FROM
inserted`/`deleted` was itself already a set read over the whole batch. The
final table contents match (every row in the batch is individually inserted
or deleted, under the same conditions), but the number of statement
executions against `t` differs from a literal reading of the T-SQL body: one
`INSERT ... SELECT ... FROM inserted` (one statement, whole batch) on T-SQL
becomes N recursive single-row inserts on PostgreSQL, one per row in the
batch.

> **Note** faithful in final result — live-verified exactly-once insertion
> per row and exact `id > 0` filtering on delete (2026-07-24) — but not
> execution-count faithful for a multi-row batch, per above.

**See Also.** [`ts-trigger-on-view`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-instead-of-insert`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-trg-instead-delete`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestInsteadOfTriggers`](../../../tests/integration/test_challenge.py) ·
[`UNIQUE-1182`](../../reference/warnings.md#unique-1182).
