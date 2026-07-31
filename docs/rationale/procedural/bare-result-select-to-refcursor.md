[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Return-type and signature synthesis" direction="tsql/postgresql/mysql → oracle" kind=article order=14 -->

# A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → Oracle `SYS_REFCURSOR` OUT parameter, propagated to `CALL` sites

**Problem.** A MySQL or T-SQL procedure can hand back a result set simply by
running a `SELECT` with no `INTO` target partway through the body. PL/SQL
forbids this outright — `SELECT` without `INTO` is a compile error
(PLS-00428/ORA-00905 depending on context) — a procedure that wants to
return rows needs an explicit `SYS_REFCURSOR` `OUT` parameter, `OPEN`ed
`FOR` the query.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestRefcursorCallSites::test_call_gains_cursor_arg (mysql -> oracle)
DELIMITER //
create procedure sel1()
begin
  select * from t1;
end//
DELIMITER ;
call sel1();
-- transpiles to:
CREATE PROCEDURE sel1
(
    RESULT_CURSOR OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN RESULT_CURSOR FOR SELECT * FROM t1;
END;
/

BEGIN
    DECLARE
        uq_rc1 SYS_REFCURSOR;
    BEGIN
        sel1(uq_rc1);
    END;
END;
/
```

A procedure that already takes parameters keeps them and appends the cursor
last (`TestRefcursorCallSites::test_call_with_args_appends_cursor`: `sel2(x
int)` running `select x + 1` becomes `sel2(x IN NUMBER, RESULT_CURSOR OUT
SYS_REFCURSOR)`, and the matching call site becomes `sel2(7, uq_rc1)`).

The rewrite recurses into every control-flow shape, including a
`TRY/CATCH`-folded exception section (the wave-70 MySQL `DECLARE ... HANDLER`
fold documented earlier on this page):

```sql
-- tests/integration/test_pg_source_wave1.py::TestRefcursorInTryCatch::test_select_in_catch_becomes_refcursor (mysql -> oracle)
DELIMITER //
create procedure hp2()
begin
  declare exit handler for sqlexception select 'bad' as e;
  insert into t1 values (1);
end//
DELIMITER ;
-- transpiles to:
CREATE PROCEDURE hp2
(
    RESULT_CURSOR OUT SYS_REFCURSOR
)
AS
BEGIN
    BEGIN
            INSERT INTO t1 VALUES (1);
    EXCEPTION
            WHEN OTHERS THEN
                OPEN RESULT_CURSOR FOR SELECT 'bad' AS e FROM DUAL;
    END;
END;
/
```

**Discussion.** The rewrite is two parts, both in
`src/unique/core/procedural/transformer/oracle.py`. `_result_selects_to_refcursors`
(line 330) walks the body — recursing into `IF`/loop/`BEGIN...END`/
`TRY...CATCH` blocks via `_rewrite_result_selects`, line 352 — replacing each
bare result `SELECT` with `OPEN <cursor> FOR <query>` and appending one
`SYS_REFCURSOR OUT` parameter per result `SELECT` found (`RESULT_CURSOR`,
`RESULT_CURSOR_2`, ... for a procedure with more than one). It also records
the procedure's name and the number of cursors it gained in a per-run
registry (`REFCURSOR_PROCS`, `src/unique/core/converter/_base.py:392`). The
`CALL`-site half, `_transform_call`
(`src/unique/core/procedural/transformer/base.py:3320-3345`), looks up the
callee in that registry and — only for an Oracle target — rewrites the call
into a small anonymous block that declares one local `uq_rcN SYS_REFCURSOR`
variable per cursor and appends them to the call's own argument list. The
docstring on `_transform_procedure` frames the motivating shape as a T-SQL
source (`oracle.py:61-64`), but the mechanism itself runs on the already-
parsed procedural IR with no source-dialect gate — the pinning tests above
exercise it from MySQL source, and it is a **different** mechanism from the
older, unrelated "Ref cursor OUT parameters" bullet in
[`03-unsupported.md`](../../03-unsupported.md#oracle--t-sql-specifics)
("Oracle → T-SQL specifics"), which is about an Oracle-authored
`SYS_REFCURSOR` parameter shipped as-is toward T-SQL — the reverse direction,
and already-existing PL/SQL syntax rather than a synthesized one.

> **Note** faithful for the body itself (the same rows, opened through the
> cursor instead of streamed as a bare result set) and for every same-script
> `CALL` site, which Unique itself rewrites to match.
> **Warning** the registry is scoped to a single transpile run — reset at
> the start of every `Transpiler().transpile()` call
> (`src/unique/core/transpiler/_core.py:501`, `:877`). A `CALL` of a
> procedure that was converted in a **separate** run (e.g. a
> previously-migrated procedure invoked from a brand-new script transpiled
> on its own) is not seen by this pass and its call site would need
> adapting by hand.

**See Also.** [`TestRefcursorInTryCatch`](../../../tests/integration/test_pg_source_wave1.py),
[`TestRefcursorCallSites`](../../../tests/integration/test_pg_source_wave1.py) ·
[`03-unsupported.md` § "Oracle → T-SQL specifics"](../../03-unsupported.md#oracle--t-sql-specifics)
(the older, unrelated Oracle-source direction).
