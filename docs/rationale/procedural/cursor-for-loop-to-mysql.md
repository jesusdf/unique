[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="oracle → mysql" kind=article order=30 -->

# PL/SQL cursor `FOR` loop (Oracle) → MySQL explicit cursor scaffold

**Problem.** The same implicit fetch-and-bind PL/SQL construct as above, but
onto MySQL, whose procedural dialect additionally requires every `DECLARE`
to sit at the very top of its enclosing `BEGIN` block (MySQL error 1337)
and has no `WHILE @@FETCH_STATUS` equivalent — loop termination is driven by
a `CONTINUE HANDLER FOR NOT FOUND`.

**Solution.**

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestMySqlCursorForLoopExpansion (_NAMED)
create or replace PROCEDURE p_cur AS
  CURSOR curES IS SELECT accion, codigo AS codpostal FROM t_dir;
BEGIN
  FOR r IN curES LOOP
    INSERT INTO t_out (a, b) VALUES (r.accion, r.codpostal);
  END LOOP;
END;
/
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p_cur()
BEGIN
    DECLARE curES CURSOR FOR SELECT accion, codigo AS codpostal FROM t_dir;

    -- UNIQUE-1175: cursor FOR-loop expanded; loop variables are TEXT (exact column types need --db-url metadata).
    BEGIN
        DECLARE r_accion TEXT;
        DECLARE r_codpostal TEXT;
        DECLARE r_done INT DEFAULT FALSE;
        DECLARE CONTINUE HANDLER FOR NOT FOUND SET r_done = TRUE;
        OPEN curES;
        r_loop: LOOP
            FETCH curES INTO r_accion, r_codpostal;
            IF r_done THEN LEAVE r_loop; END IF;
            INSERT INTO t_out (a, b) VALUES (r_accion, r_codpostal);
        END LOOP;
        CLOSE curES;
    END;
END$$
DELIMITER ;
```

The expansion opens a **new nested block** so its per-column `DECLARE`s and
the `CONTINUE HANDLER` are legal at that block's own top (they cannot be
injected into the outer procedure's declaration section, since the loop
variables are scoped to the loop). Each generated loop carries its own
unique label (`r_loop`) so nested cursor loops never collide (MySQL error
1309, "redefining label"). An inline (unnamed) cursor query desugars the
same way, folding its `SELECT` directly into a synthesized
`DECLARE r_cur CURSOR FOR <query>`
(`test_inline_query_expands_completely`), and an unresolvable `SELECT *`
falls back to the documented placeholder scaffold exactly as in the T-SQL
case above (`test_unresolvable_list_keeps_documented_scaffold`,
`UNIQUE-1174`).

**Discussion.** MySQL cursor control flow is built entirely from
declarations, an explicit `LOOP`, and a `NOT FOUND` handler flag that must
be checked after each `FETCH` — there is no statement that fetches into a
whole record and tests exhaustion in one step, so the same rec-to-scalars
expansion as the T-SQL entry above is required, plus MySQL's own
declaration-ordering and block-scoping rules.

> **Warning** `[limit]` without `--db-url` — loop variables are `TEXT`, not
> the column's real type; the loop's control flow and FETCH positions are
> otherwise complete and faithful. `[limit]` (documented scaffold) when the
> column list cannot be resolved.

**See Also.** [`TestMySqlCursorForLoopExpansion`](../../../tests/integration/test_oracle_mysql_tail.py) ·
[`UNIQUE-1175`](../../reference/warnings.md#unique-1175) ·
[`UNIQUE-1174`](../../reference/warnings.md#unique-1174).
