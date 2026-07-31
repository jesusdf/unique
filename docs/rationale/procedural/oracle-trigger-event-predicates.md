[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=19 direction-inferred=true -->

# Oracle event predicates (`INSERTING`/`DELETING`/`UPDATING('col')`) → per-engine rewrite

**Problem.** An Oracle trigger body asks, inline, "did this statement
INSERT/DELETE/UPDATE, and did this specific column change" via
`INSERTING`/`DELETING`/`UPDATING('col')`. No other engine spells the same
question the same way, and MySQL triggers cannot even ask it — a MySQL
trigger fires on exactly one event.

**Solution.**

```sql
-- tests/integration/test_trigger_predicates_scheduler.py::test_inserting_deleting_predicates_map_to_tsql
CREATE OR REPLACE TRIGGER trg1 AFTER INSERT OR DELETE ON t1 FOR EACH ROW
BEGIN
  IF INSERTING THEN INSERT INTO log_t (op) VALUES ('I'); END IF;
  IF DELETING THEN INSERT INTO log_t (op) VALUES ('D'); END IF;
END;
-- oracle -> tsql:
IF (EXISTS (SELECT 1 FROM inserted) AND NOT EXISTS (SELECT 1 FROM deleted))
BEGIN
    INSERT INTO log_t (op) VALUES ('I');
END
IF (EXISTS (SELECT 1 FROM deleted) AND NOT EXISTS (SELECT 1 FROM inserted))
BEGIN
    INSERT INTO log_t (op) VALUES ('D');
END
```

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestEventPredicates — IF UPDATING('estado') THEN ...
-- oracle -> postgresql:
IF (TG_OP = 'UPDATE' AND NEW.estado IS DISTINCT FROM OLD.estado) THEN ...
-- oracle -> mysql: the body is statically DUPLICATED once per event (trg_m ->
-- trg_m_ins + trg_m_upd), each copy's own-event predicate folded to a constant
-- instead of tested at runtime:
--   trg_m_ins: IF (1 = 1) THEN ...        -- INSERTING folds true here
--              IF (1 = 0) THEN ...        -- UPDATING('estado') folds false here
--   trg_m_upd: IF (1 = 0) THEN ...        -- INSERTING folds false here
--              IF (NOT (NEW.estado <=> OLD.estado)) THEN ...
```

The reverse direction — T-SQL's `UPDATE(col)` predicate read into every
engine — is the same mechanism read backwards:

```sql
-- tests/integration/test_triggers.py::TestTriggerUpdatePredicate
IF UPDATE(col_32) BEGIN INSERT INTO dbo.log (a) VALUES (1) END
-- tsql -> postgresql:  NEW.col_32 IS DISTINCT FROM OLD.col_32
-- tsql -> mysql:        NOT (NEW.col_32 <=> OLD.col_32)
-- tsql -> oracle:       UPDATING('col_32')
```

**Discussion.** `INSERTING`/`DELETING` describe which pseudo-table has rows
this firing, which T-SQL restates as an existence test against the
`inserted`/`deleted` tables the rest of the trigger already uses.
`UPDATING('col')` and T-SQL's `UPDATE(col)` both ask "did this column's
value actually change on this row" (not merely "was it in the `SET` list"),
which PostgreSQL/MySQL have no keyword for at all — Unique expands it to an
explicit `NEW.col IS DISTINCT FROM OLD.col` (PostgreSQL's NULL-safe
comparison) or `NOT (NEW.col <=> OLD.col)` (MySQL's NULL-safe equality
operator, negated). MySQL's one-event-per-trigger restriction additionally
forces the whole body to be **duplicated per event** — one physical trigger
per event, each copy's own-event predicate folded to a compile-time constant
rather than tested — a structural change (one trigger becomes two, or more),
not a semantic one, since each copy only ever fires for its own event.

> **Note** faithful — each rewrite restates the same boolean question in the
> target's own syntax; unlike the row-level-body family above, these
> predicates only ever gate a body that already runs at the right
> granularity for its engine, so there is no firing-count divergence here.

**See Also.** [`test_inserting_deleting_predicates_map_to_tsql`](../../../tests/integration/test_trigger_predicates_scheduler.py) ·
[`TestEventPredicates`](../../../tests/integration/test_oracle_source_m4_wave.py) ·
[`TestTriggerUpdatePredicate`](../../../tests/integration/test_triggers.py).
