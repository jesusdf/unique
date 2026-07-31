[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="tsql → postgresql" kind=article order=58 -->

# A purely set-based T-SQL trigger (`FROM inserted JOIN deleted`) → PostgreSQL statement-level trigger with named transition tables

**Problem.** T-SQL triggers are always statement-level, exposing the whole
batch of affected rows through two pseudo-tables, `inserted`/`deleted`, that
a set-based trigger body joins against directly (`INSERT ... SELECT ...
FROM inserted i JOIN deleted d ON d.id = i.id`). PostgreSQL trigger
functions are normally row-level (`NEW`/`OLD`, one invocation per row) —
carrying a `FROM inserted` reference into a row-level function would be
invalid, there being no such table.

**Solution.**

```sql
-- tests/integration/test_triggers.py::TestSetBasedTriggerRewrite::test_pure_set_based_to_postgresql_uses_transition_tables
CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN
    INSERT INTO audit (a, b)
    SELECT i.col1, d.col1 FROM inserted i JOIN deleted d ON d.id = i.id
END
-- tsql -> postgresql:
CREATE OR REPLACE FUNCTION trg_func()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;
    INSERT INTO audit (a, b) SELECT i.col1, d.col1 FROM inserted i INNER JOIN deleted d ON d.id = i.id;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE TRIGGER trg
AFTER UPDATE ON t
REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted
FOR EACH STATEMENT
EXECUTE FUNCTION trg_func();
```

**Discussion.** PostgreSQL 10+ supports the same statement-level shape
T-SQL always uses: a `FOR EACH STATEMENT` trigger whose function declares
`REFERENCING NEW TABLE AS ... OLD TABLE AS ...`, naming the two
transition tables that hold the whole affected batch — exactly what
`inserted`/`deleted` already are in the source. Recognizing a trigger as
**purely** set-based (its body reads `inserted`/`deleted` only through
`FROM`/`JOIN`, with no row-level qualifier like `inserted.col` in a
scalar position and no `UPDATE(col)` predicate, which only makes sense
per-row) is what licenses this rewrite: the T-SQL body's join against
`inserted`/`deleted` is preserved unchanged, since PostgreSQL's named
transition tables behave the same way in a query. The `pg_trigger_depth()
> 1` guard exists for a different reason — it stops the trigger's own
statement-level DML from re-entering itself one level deeper — and is
unrelated to the set/row-level question.

A **mixed** trigger (row-level and set-level references together, or an
`UPDATE(col)` predicate, which is inherently per-column-per-row) cannot be
expressed as one statement-level trigger and is not rewritten. Oracle has
no *named* transition tables at all — emulating one would mean
accumulating rows into a PL/SQL collection inside a compound trigger,
which is a hand-written data structure, not a mechanical syntax rewrite —
and MySQL has neither named nor unnamed transition tables; both keep
documenting the construct rather than risk invalid or silently-wrong SQL
(see [§6](../../03-unsupported.md), "Set-based trigger pseudo-tables", for
that residual).

> **Note** faithful on PostgreSQL — the rewritten trigger fires once per
> statement over the identical joined row set the T-SQL body operated on.

**See Also.** [`test_triggers.py::TestSetBasedTriggerRewrite`](../../../tests/integration/test_triggers.py)
· [§6](../../03-unsupported.md), "Procedural Engine — Known Limitations"
("Set-based trigger pseudo-tables" — the Oracle/MySQL residual and the
mixed-trigger case) · [PG named transition tables → T-SQL rename](pg-named-transition-tables.md)
(the reverse direction, PostgreSQL-authored named transition tables
collapsing to T-SQL's fixed `inserted`/`deleted`).
