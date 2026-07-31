[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Top-level batch wrapped for PL/pgSQL-only constructs" direction="tsql/oracle → postgresql" kind=article order=48 -->

# A top-level T-SQL/Oracle batch needing a procedural construct → PostgreSQL `DO $$ ... $$`

**Problem.** A standalone (not-inside-a-`CREATE PROCEDURE`) T-SQL batch or
Oracle anonymous block can freely mix `PRINT`/`DBMS_OUTPUT`, variable
declarations, `IF`, cursor `FOR` loops, and dynamic `EXECUTE` — all
procedural constructs that only exist *inside* a routine body on
PostgreSQL. A bare top-level `PRINT`/anonymous block has nowhere on
PostgreSQL to run its procedural content unless it is wrapped in
PostgreSQL's own anonymous-block statement.

**Solution.**

```sql
-- tests/integration/test_procedural.py::TestTopLevelPrintAndSet
PRINT 'hi'
-- tsql -> oracle (Oracle's own anonymous block, no wrap needed for a
-- standalone statement):
BEGIN
    DBMS_OUTPUT.PUT_LINE('hi');
END;
/
-- tsql -> postgresql (needs the DO $$ ... $$ wrapper — RAISE NOTICE is
-- PL/pgSQL-only, illegal as a bare top-level statement):
DO $$
BEGIN
    RAISE NOTICE '%', 'hi';
END $$;
-- tsql -> mysql (no anonymous-block concept; falls back to a plain
-- top-level statement wherever one exists):
SELECT 'hi';
```

The same wrap covers a T-SQL batch that `DECLARE`s a variable and captures
a procedure's `OUTPUT` parameter (`EXEC p @out = @v OUTPUT`), and an Oracle
top-level anonymous block that itself needs full procedural machinery — a
cursor `FOR` loop driving dynamic `EXECUTE IMMEDIATE` calls, for instance —
which routes to PostgreSQL's `DO $$ ... $$` (which supports anonymous
blocks, cursor `FOR`-loops, and dynamic `EXECUTE` inside it) the same way.

**Discussion.** The decision of *whether* to wrap is per-construct, not
"every top-level batch always gets a `DO $$`" — a plain `SELECT`/`INSERT`
with nothing procedural about it stays a bare statement on PostgreSQL, same
as on every other target. The wrap only fires once the batch is routed to
the procedural engine at all, which happens whenever it contains something
with no non-procedural spelling (`PRINT`, a variable `DECLARE`+`SET`, an
`EXEC ... OUTPUT` capture, a full anonymous block). MySQL has no
top-level procedural construct whatsoever — it cannot run any code outside
a stored routine — so a construct that needs one degrades to a documented
carrier + warning there instead of being force-fit into anything.

> **Note** faithful — `DO $$ ... $$` runs once, immediately, exactly like
> the source's own top-level batch; it is PostgreSQL's structural
> requirement for procedural code outside a routine, not a change in when
> or how many times the body executes. No warning for the PostgreSQL/Oracle
> legs; MySQL's degrade is a documented, warned loss when no procedural
> top-level form exists there at all.

**See Also.** [`test_procedural.py`](../../../tests/integration/test_procedural.py)
(`TestTopLevelPrintAndSet`, `TestTopLevelTryCatch`, `TestExecOutputCapture`,
`TestOracleAnonymousBlock`) · [§3.5](../../03-unsupported.md), "Error
Handling" (the narrower, already-documented case of this same wrap for a
top-level `TRY`/`CATCH` specifically).
