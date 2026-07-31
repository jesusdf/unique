[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Routine-scoped temporary storage" direction="tsql → oracle/postgresql/mysql" kind=article order=61 -->

# T-SQL table variable (`DECLARE @t TABLE`) / in-routine `SELECT ... INTO #tmp` → per-target temp table

**Problem.** A T-SQL table variable (`DECLARE @t TABLE (...)`) and an
in-procedure `SELECT ... INTO #tmp` (a temp table, not a variable) both need
somewhere to live once the routine converts to PL/SQL — but Oracle's `CREATE
TABLE` cannot appear inside a PL/SQL block at all (a `CREATE` is DDL; PL/SQL
executes only DML/control-flow statically), so the table has to exist
*before* the routine, not inside it.

**Solution.**

```sql
-- tsql -> oracle: DECLARE @t TABLE
CREATE PROCEDURE p AS
BEGIN
    DECLARE @t TABLE (id INT, v INT);
    INSERT INTO @t (id, v) SELECT 1, 2;
    SELECT * FROM @t;
END;
-- =>
CREATE GLOBAL TEMPORARY TABLE p_V_T (
  id NUMBER(10),
  v NUMBER(10)
) ON COMMIT DELETE ROWS;

CREATE OR REPLACE PROCEDURE p (RESULT_CURSOR OUT SYS_REFCURSOR) AS
BEGIN
    INSERT INTO p_V_T (id, v) SELECT 1, 2 FROM DUAL;
    OPEN RESULT_CURSOR FOR SELECT * FROM p_V_T;
END;
/
```

```sql
-- tests/integration/test_temp_table_in_procedure.py, tsql -> oracle: SELECT ... INTO #tmp
CREATE PROCEDURE dbo.rollup_report AS
BEGIN
    SELECT cust_id, amount INTO #w FROM orders WHERE amount > 0;
    ...
END
-- =>
CREATE GLOBAL TEMPORARY TABLE rollup_report_w ON COMMIT PRESERVE ROWS AS
  SELECT * FROM (SELECT cust_id, amount FROM orders WHERE amount > 0) WHERE 1 = 0;

CREATE OR REPLACE PROCEDURE rollup_report (...) AS
BEGIN
    DELETE FROM rollup_report_w;
    INSERT INTO rollup_report_w
    SELECT cust_id, amount FROM orders WHERE amount > 0;
    ...
END;
/
```

Both forms hoist a `CREATE GLOBAL TEMPORARY TABLE` **before** the routine,
named from the routine + the variable/temp-table name so multiple routines
in the same script never collide, with every in-body reference renamed to
match. A table variable's rows must not survive past the call (`ON COMMIT
DELETE ROWS`, matching a variable's own scope); a `SELECT INTO #tmp`
temp table's rows must survive the current transaction (`ON COMMIT
PRESERVE ROWS`, matching T-SQL's `#temp` semantics) but still be **re-usable
across separate calls** in the same session, so the body clears it first
(`DELETE`) and repopulates it (`INSERT`) rather than relying on the `CREATE`
that only ran once, ahead of time.

**Discussion.** Oracle's `GLOBAL TEMPORARY TABLE` has a persistent, shared
*definition* (visible to every session) with per-session private rows — the
opposite of T-SQL's table variable/temp table, which is defined *and*
scoped to the batch/connection that declares it. Splitting the `CREATE`
(hoisted once, outside the routine) from the per-call population (`DELETE`/
`INSERT` inside it) reproduces "fresh rows every call" without a `CREATE`
that PL/SQL cannot execute inline.

> **Note** faithful — live-compiled and run on Oracle: the hoisted GTT
> populates and reads back correctly through the converted procedure
> (`OPEN … FOR SELECT * FROM p_V_T` returns the inserted row). An
> accompanying `INSERT … OUTPUT … INTO @t` (a T-SQL `OUTPUT` clause writing
> into a table variable) is a documented carrier instead — Oracle's
> `RETURNING` cannot target a whole table, only `INTO` variables, so the GTT
> would need to be populated by hand.

PostgreSQL and MySQL need no hoist at all: both can run `CREATE TEMPORARY
TABLE` as a plain statement inside the routine body, so a table variable
becomes a real temp table declared right where the source `DECLARE`
was — live-verified on both engines — with a documentary `UNIQUE-1196`
carrier noting the substitution (not a divergence: the carrier is purely
informational, since a temp table gives the same session-scoped,
statement-usable storage a table variable would). `SELECT ... INTO #tmp`
gets the `CREATE TEMPORARY TABLE ... AS SELECT` shown above the same way,
preceded by a `DROP ... IF EXISTS` so a second `CALL` in the same session
recreates it (a temp table there, unlike Oracle's GTT, does not need a
separate clear-and-repopulate step). Outside a procedure (in a function or
trigger, where Oracle's `CREATE` cannot be hoisted the same way), the
`SELECT ... INTO #tmp` form falls back to the documented warned degrade on
Oracle. See [§6](../../03-unsupported.md).

**See Also.** [`test_temp_table_in_procedure.py`](../../../tests/integration/test_temp_table_in_procedure.py) (B28a), [`TestTableVariableToMySQL`](../../../tests/integration/test_procedural.py), [`test_procedural_leading_ddl.py`](../../../tests/integration/test_procedural_leading_ddl.py) (`UNIQUE-1196`) ·
[§6](../../03-unsupported.md) (the outside-a-procedure `SELECT ... INTO #tmp` fallback on Oracle) ·
[Session-scoped temp tables (top-level `CREATE TEMP`/`#temp`) → Oracle `GLOBAL TEMPORARY`](../ddl/session-temp-tables-to-oracle.md)
(the sibling mechanism for a **standalone** statement, not one hoisted out
of a routine body — same `ON COMMIT PRESERVE ROWS` reasoning).

---
