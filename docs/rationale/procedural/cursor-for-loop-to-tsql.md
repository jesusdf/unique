[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="oracle → tsql" kind=article order=29 -->

# PL/SQL `FOR rec IN cur LOOP` (Oracle) → T-SQL explicit cursor scaffold

**Problem.** A PL/SQL cursor `FOR` loop declares nothing: it implicitly
opens the cursor, fetches one row per iteration into a record `rec`, and
closes it when the cursor is exhausted — `rec.col` reads that iteration's
column. T-SQL has no such implicit record-fetch loop at all.

**Solution.**

```sql
-- tests/integration/test_cursor_for_loop_tsql.py (_NAMED)
DECLARE
  v_total NUMBER := 0;
  CURSOR cur1 IS SELECT id, amount, name FROM src_t WHERE flag = 1;
BEGIN
  FOR rec IN cur1 LOOP
    IF rec.amount > 0 THEN
      INSERT INTO dst_t (id, label) VALUES (rec.id, rec.name || '!');
    END IF;
    v_total := v_total + rec.amount;
  END LOOP;
END;
/
-- oracle -> tsql:
DECLARE @total DECIMAL = 0;
DECLARE cur1 CURSOR LOCAL FAST_FORWARD FOR SELECT id, amount, name FROM src_t WHERE flag = 1;
-- UNIQUE-1187: cursor FOR-loop expanded; loop variables are NVARCHAR(4000) (exact column types need --db-url metadata).
DECLARE @rec_id NVARCHAR(4000), @rec_amount NVARCHAR(4000), @rec_name NVARCHAR(4000);
OPEN cur1;
FETCH NEXT FROM cur1 INTO @rec_id, @rec_amount, @rec_name;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF @rec_amount > 0
    BEGIN
            INSERT INTO dst_t (id, label) VALUES (@rec_id, @rec_name + '!');
    END
    SET @total = @total + @rec_amount;
FETCH NEXT FROM cur1 INTO @rec_id, @rec_amount, @rec_name;
END;
CLOSE cur1;
DEALLOCATE cur1;
```

The loop expands into a complete `DECLARE`/`OPEN`/positional
`FETCH ... INTO`/`WHILE @@FETCH_STATUS = 0`/`CLOSE`/`DEALLOCATE` scaffold,
one `@rec_<col>` variable per selected column, with every `rec.col`
reference in the body rewritten to the matching `@rec_col`, and the
re-fetch duplicated at the bottom of the loop body (T-SQL's `WHILE` tests
*before* each iteration, unlike PL/SQL's implicit post-fetch test). The same
expansion applies to an inline cursor query
(`test_inline_query_loop_expands_completely`: `FOR r IN (SELECT a, b FROM t
...) LOOP`).

**Discussion.** T-SQL cursors are opened, fetched, and tested for
`@@FETCH_STATUS` as three separate statements — there is no single
statement that both advances a cursor and binds a whole row to a
record-like variable the way PL/SQL's `FOR ... IN cursor LOOP` does, so the
implicit fetch-and-bind has to be made explicit, one scalar variable per
column. Without `--db-url` metadata, Unique does not know each selected
column's real type, so every `@rec_<col>` is declared as the permissive
`NVARCHAR(4000)` (`UNIQUE-1187`) rather than the column's actual type. When
the select list is *not* statically resolvable (e.g. `SELECT *` with no
visible schema), Unique cannot generate the per-column variable list at
all, and falls back to the previously-documented scaffold with a
placeholder `FETCH ... INTO /* col1, ... */` for the developer to complete
(`test_unresolvable_select_star_keeps_documented_scaffold`, `UNIQUE-1174`) —
warned, never guessed.

> **Warning** `[limit]` without `--db-url` — loop variables are
> `NVARCHAR(4000)`, not the column's real type; the loop's control flow,
> `rec.col` rewriting, and FETCH positions are otherwise complete and
> faithful. `[limit]` (documented scaffold, not expanded) when the column
> list cannot be resolved at all.

**See Also.** [`test_named_cursor_loop_expands_completely`, `test_inline_query_loop_expands_completely`, `test_unresolvable_select_star_keeps_documented_scaffold`](../../../tests/integration/test_cursor_for_loop_tsql.py) ·
[`UNIQUE-1187`](../../reference/warnings.md#unique-1187) ·
[`UNIQUE-1174`](../../reference/warnings.md#unique-1174) — no dedicated
challenge-corpus case exercises the named-cursor `FOR` loop, so the example
above is drawn from that dedicated integration test.
