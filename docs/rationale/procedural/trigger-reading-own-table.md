[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="postgresql/mysql ↔ oracle" kind=article order=22 -->

# Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`

**Problem.** A row-level trigger that aggregates a parent row from its
children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line
WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the
table it's attached to. Oracle raises `ORA-04091` ("table is mutating") for
exactly this shape in a plain row-level trigger; MySQL and PostgreSQL have no
such restriction.

**Solution.** MySQL/PostgreSQL → Oracle synthesizes a `COMPOUND TRIGGER`:
collect the affected key per row in `AFTER EACH ROW`, re-aggregate once in
`AFTER STATEMENT`:

```sql
-- tests/integration/test_triggers.py::TestRowLevelReReadToOracleCompound::test_synthesizes_compound_trigger
CREATE TRIGGER trg_agg AFTER INSERT ON invoice_line FOR EACH ROW
BEGIN
    UPDATE invoice SET total = (SELECT COALESCE(SUM(line_total), 0)
        FROM invoice_line WHERE invoice_id = NEW.invoice_id)
    WHERE id = NEW.invoice_id;
END
-- mysql -> oracle:
CREATE OR REPLACE TRIGGER trg_agg
FOR INSERT ON invoice_line
COMPOUND TRIGGER
    TYPE unique_kt_1 IS TABLE OF invoice_line.invoice_id%TYPE INDEX BY PLS_INTEGER;
    unique_key_1 unique_kt_1;
    g_n PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_n := g_n + 1;
        unique_key_1(g_n) := :NEW.invoice_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR unique_i IN 1 .. g_n LOOP
            UPDATE invoice SET total = (SELECT COALESCE(SUM(line_total), 0)
                FROM invoice_line WHERE invoice_id = unique_key_1(unique_i))
            WHERE id = unique_key_1(unique_i);
        END LOOP;
    END AFTER STATEMENT;
END;
/
```

The reverse conversion — an Oracle `COMPOUND TRIGGER` written this way, read
into a target where the mutating-table restriction doesn't exist — lowers
to a plain row-level trigger instead:

```sql
-- tests/integration/test_triggers.py::TestOracleCompoundTrigger::test_lowers_to_row_level_postgresql
-- oracle -> postgresql:
CREATE OR REPLACE FUNCTION trg_line_total_func()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE invoice SET total = 0 WHERE id = NEW.invoice_id;
    RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER trg_line_total
AFTER INSERT OR UPDATE ON invoice_line
FOR EACH ROW EXECUTE FUNCTION trg_line_total_func();
```

MySQL keeps neither shape: it degrades to a documented carrier
(`test_degrades_to_carrier_mysql`) — MySQL has no compound-trigger
equivalent to lower to, and a mechanical row-level rewrite would reintroduce
the very mutating-read pattern Oracle forbids, so Unique documents rather
than guesses.

A row-level trigger that does **not** re-read its own table is left alone on
Oracle — no needless compound rewrite
(`test_non_self_referencing_row_trigger_stays_row_level`).

**Discussion.** Oracle's `AFTER STATEMENT` phase runs the aggregation
**once per statement**, however many rows were collected; the PostgreSQL
lowering runs it **once per row** instead (a plain `FOR EACH ROW` trigger),
since PostgreSQL has no equivalent phase separation. For a pure aggregate
read like this one, the *final* value after all firings is identical either
way (`COALESCE(SUM(...))` is idempotent under repetition), but a multi-row
batch recomputes and rewrites the parent row N times on PostgreSQL where
Oracle's compound form would have done it once.

> **Warning** the collapse from statement-batched to per-row execution is a
> firing-count divergence, not a value divergence: correct final data, but
> `invoice` is written — and any of *its own* triggers fire — once per
> `invoice_line` row instead of once per statement. `[limit]` (documented,
> not rewritten) on MySQL — no compound-trigger equivalent exists to lower
> to.

**See Also.** [`TestRowLevelReReadToOracleCompound`](../../../tests/integration/test_triggers.py) ·
[`TestOracleCompoundTrigger`](../../../tests/integration/test_triggers.py) ·
[`UNIQUE-1156`](../../reference/warnings.md#unique-1156) ·
[`UNIQUE-1231`](../../reference/warnings.md#unique-1231).
