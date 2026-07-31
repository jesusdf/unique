[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=18 direction-inferred=true -->

# Row-level trigger body (`SET NEW.col = expr`) → T-SQL statement-level `UPDATE ... WHERE ... IN (SELECT ... FROM inserted)`

**Problem.** A MySQL/PL-SQL row-level trigger (`FOR EACH ROW`) runs once per
affected row, with `NEW`/`OLD` bound to that single row. T-SQL has no
row-level trigger at all — every trigger is statement-level, and the only
per-row surface it exposes is the `inserted`/`deleted` pseudo-tables holding
the *whole* affected batch.

**Solution.**

```sql
-- tests/integration/test_triggers.py::TestRowLevelTriggerToTSql::test_new_assignment_becomes_setbased_update
CREATE TRIGGER t BEFORE INSERT ON invoice_line FOR EACH ROW
BEGIN
    SET NEW.line_total = NEW.qty * NEW.unit_price;
END
-- mysql -> tsql:
CREATE TRIGGER t ON invoice_line
AFTER INSERT
AS
BEGIN
    UPDATE invoice_line SET line_total = qty * unit_price WHERE id IN (SELECT id FROM inserted);
END
```

A per-row assignment against the trigger's own table becomes a single
`UPDATE` keyed on the primary key of every row in `inserted`. When the body
updates a *different* table via a foreign key
(`test_embedded_update_keyed_on_new_fk_scoped_to_inserted`), the same
scoping happens through the correlated subquery instead:

```sql
-- mysql -> tsql
UPDATE invoice SET total = (SELECT COALESCE(SUM(il.line_total), 0)
    FROM invoice_line il WHERE il.invoice_id = invoice.id)
WHERE invoice.id IN (SELECT invoice_id FROM inserted);
```

(the T-SQL `UPDATE ... FROM` form takes no alias on the *target* table, so
the correlation is re-qualified against the bare table name.)

**Discussion.** MySQL's `BEFORE INSERT` fires once per row and mutates only
that row's `NEW`; T-SQL's `AFTER INSERT` fires once per **statement** and
only ever sees the `inserted` set as a whole, so the row-level assignment
has to become a set operation scoped to that set before it can run at all.

> **Note** faithful when the per-row expression reads only that row's own
> `NEW`/`OLD` values (no cross-row dependency): the set-based `UPDATE`
> recomputes every affected row independently in one pass, which is what N
> per-row firings would have produced anyway.
> **Warning** if the same target table carries its **own** downstream
> trigger, firing counts diverge: MySQL's row-level trigger fires that
> downstream trigger once per originating row (N times for a batch of N rows
> sharing one FK target), while the collapsed T-SQL statement fires it once
> per **distinct** key touched by the single `UPDATE` — a batch of 5
> `invoice_line` inserts for the same invoice fires a downstream `invoice`
> trigger 5 times on MySQL but once on T-SQL.

**See Also.** [`TestRowLevelTriggerToTSql`](../../../tests/integration/test_triggers.py) ·
[`test_new_assignment_inside_if_converts_to_setbased`](../../../tests/integration/test_trigger_predicates_scheduler.py)
(the same rewrite recursing into an `IF` body).
