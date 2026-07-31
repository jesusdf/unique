[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Error handling" direction="mysql → tsql/oracle/postgresql" kind=article order=8 -->

# MySQL `DECLARE {EXIT|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)

**Problem.** MySQL declares an error handler *separately* from the code it
protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in
the block's declaration section, naming the condition(s) it reacts to and a
single action statement. PostgreSQL/Oracle's `EXCEPTION WHEN OTHERS` and
T-SQL's `BEGIN TRY...END TRY BEGIN CATCH...END CATCH` are both
**block-structured** instead: the protected code and its handler are two
halves of one syntactic unit, not a declaration plus free-floating code.

**Solution.** An `EXIT` handler for `SQLEXCEPTION`/`SQLWARNING` is exactly
the enclosing block's exception section, so it folds directly into the
target's own block-structured form — the rest of the block becomes the
protected body, and the handler's action becomes the handler body:

```sql
-- tests/integration/test_pg_source_wave1.py::TestMysqlDeclareHandler (_EXIT_SRC)
create procedure hp()
begin
  declare exit handler for sqlexception select 'bad' as e;
  insert into t1 values (1);
  select 'ok' as r;
end
-- mysql -> postgresql:
CREATE PROCEDURE hp()
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
            INSERT INTO t1 VALUES (1);
            SELECT 'ok' AS r;
    EXCEPTION
    WHEN OTHERS THEN
            SELECT 'bad' AS e;
    END;
END;
$$;
-- mysql -> tsql:
CREATE PROCEDURE hp
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
            INSERT INTO t1 VALUES (1);
            SELECT 'ok' AS r;
    END TRY
    BEGIN CATCH
            SELECT 'bad' AS e;
    END CATCH
END
```

A `CONTINUE` handler, a handler for any condition other than
`SQLEXCEPTION`/`SQLWARNING` (a specific `SQLSTATE`, a named condition, `NOT
FOUND` used outside a cursor loop), more than one handler in the same block,
or a handler declared in a *nested* block all keep the honest,
already-documented whole-routine degrade instead — each with its own
interpolated reason:

```sql
-- tests/integration/test_pg_source_wave1.py::TestMysqlDeclareHandler::test_continue_handler_degrades
create procedure hc()
begin
  declare continue handler for sqlstate '23000' select 'dup';
  insert into t1 values (1);
end
-- mysql -> postgresql:
-- UNIQUE-1171: MySQL CONTINUE handler for SQLSTATE '23000' has no postgresql equivalent; routine preserved as a comment
-- create procedure hc()
-- begin
--   declare continue handler for sqlstate '23000' select 'dup';
--   insert into t1 values (1);
-- end
```

**Discussion.** `EXIT`'s control-flow contract — abandon the block and run
the handler's action — is precisely what `EXCEPTION WHEN OTHERS`/`CATCH`
already do, so a single condition set of `SQLEXCEPTION`/`SQLWARNING` maps
without any semantic gap. `CONTINUE` cannot: it resumes execution at the
statement *after* the one that raised, a resumption model neither
`EXCEPTION`/`CATCH` block nor any other target construct offers. A specific
`SQLSTATE` value or a named condition has no standard cross-engine spelling
Unique can trust without a lookup table it does not have, and a handler
nested inside an inner block, or more than one handler sharing a block,
would need per-condition dispatch logic no target's block-exception form
expresses directly — so each of those keeps the pre-existing whole-routine
carrier rather than guessing a mapping.

> **Note** faithful for the `EXIT`/`SQLEXCEPTION`/`SQLWARNING` fold — same
> protected body, same handler action, restated in each target's own
> block-exception syntax.
> **Warning** `[limit]` (the pre-existing whole-routine degrade,
> unaffected by this fold) for `CONTINUE` handlers, unmapped condition
> classes, multiple handlers, and nested-block handlers.

**See Also.** [`TestMysqlDeclareHandler`](../../../tests/integration/test_pg_source_wave1.py) ·
[`UNIQUE-1171`](../../reference/warnings.md#unique-1171) — no dedicated
challenge-corpus case exercises `DECLARE HANDLER`, so the examples above are
drawn from that dedicated integration test.
