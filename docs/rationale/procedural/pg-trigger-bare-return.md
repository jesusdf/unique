[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=25 direction-inferred=true -->

# Bare `RETURN;` inside a PostgreSQL trigger function's nested handler → `RETURN NEW;`

**Problem.** Oracle's bare `RETURN;` inside an exception handler simply
leaves the trigger (there is no return value to supply there). A PostgreSQL
trigger function must return a row of type `TRIGGER` from *every* code
path — a bare `RETURN;` there is `ERROR: 42601: missing expression`
(live-verified).

**Solution.**

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestBareReturnInPgTriggerFunction
CREATE OR REPLACE TRIGGER trg_r AFTER UPDATE ON t_e FOR EACH ROW
DECLARE v_x NUMBER;
BEGIN
  BEGIN
    SELECT a INTO v_x FROM t2 WHERE b = :NEW.id;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN;
  END;
  UPDATE t3 SET c = v_x WHERE id = :NEW.id;
END;
-- oracle -> postgresql (inside the trigger function):
EXCEPTION
    WHEN no_data_found THEN
        RETURN NEW;
```

**Discussion.** The rewrite fills the bare `RETURN;` in with whatever the
enclosing function's own trailing default return would be — `NEW` for a
row-level trigger (the row-level convention for "let the operation proceed
unchanged"), `NULL` for a set-based/statement-level one — rather than a
fixed guess, since the correct value depends on the trigger's own
granularity, not on the `RETURN` statement itself.

> **Note** faithful — the early exit still leaves the rest of the trigger
> body unexecuted, exactly as Oracle's bare `RETURN;` does; only the value
> handed back changes, to satisfy PostgreSQL's return-type contract.

**See Also.** [`TestBareReturnInPgTriggerFunction`](../../../tests/integration/test_oracle_source_m4_wave.py).
