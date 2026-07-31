[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=24 direction-inferred=true -->

# Trigger body → PostgreSQL `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER`

**Problem.** PostgreSQL has no inline trigger body: `CREATE TRIGGER` only
*names* a function, which must already exist and return `TRIGGER`. Every
other engine (T-SQL, Oracle, MySQL, SQLite) writes the body directly inside
`CREATE TRIGGER`.

**Solution.**

```sql
-- tests/integration/test_triggers.py::TestTriggerTiming::test_after_insert_postgresql_emits_function_and_trigger
CREATE TRIGGER trg ON dbo.t
AFTER INSERT
AS BEGIN UPDATE dbo.t SET n = 1 WHERE id = 1 END
-- tsql -> postgresql:
CREATE OR REPLACE FUNCTION trg_func()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE t SET n = 1 WHERE id = 1;
    RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER trg
AFTER INSERT ON t
EXECUTE FUNCTION trg_func();
```

The same decomposition applies from any source dialect, including SQLite
(whose own trigger body sits inline, like MySQL's/Oracle's):

```python
# tests/unit/core/test_transpiler.py::test_sqlite_trigger_to_targets
trg = "CREATE TRIGGER trg AFTER INSERT ON orders FOR EACH ROW BEGIN " \
      "UPDATE stats SET total = total + NEW.amount WHERE id = NEW.cat_id; END"
# sqlite -> postgresql: CREATE FUNCTION trg_func() RETURNS TRIGGER ...; CREATE TRIGGER trg ... EXECUTE FUNCTION trg_func();
# sqlite -> oracle:     CREATE OR REPLACE TRIGGER trg ... BEGIN ... :NEW.amount ... END; / (body stays inline)
# sqlite -> mysql:      DELIMITER-wrapped CREATE TRIGGER trg ... NEW.amount ... (body stays inline)
```

**Discussion.** PostgreSQL's function/trigger split is a structural, not a
semantic, requirement — the function's body is exactly the trigger's body,
with a mandatory `RETURN NEW`/`RETURN OLD`/`RETURN NULL` added since a
plpgsql function must return a value of its declared type (`TRIGGER`),
which no other engine's inline body has an equivalent obligation for.

> **Note** faithful — same statements, split across two `CREATE` objects
> instead of one, with the return value synthesized to satisfy PostgreSQL's
> function-return contract.

**See Also.** [`TestTriggerTiming`](../../../tests/integration/test_triggers.py) ·
[`test_sqlite_trigger_to_targets`](../../../tests/unit/core/test_transpiler.py).
