[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="tsql → oracle/postgresql/mysql" kind=article order=28 -->

# T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL lets a cursor be bound to a *variable* in two steps: a
bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... FOR
<query>` to attach the query, then a bare `OPEN @cur;`. Read literally
across engines, this looks like an assignment statement plus a separate
open — but PostgreSQL/Oracle refcursors and MySQL's own cursor syntax only
ever open a cursor *with* its query in one step.

**Solution.**

```sql
-- tests/integration/test_cursor_variable_binding.py (_CURSOR_VAR_SRC)
CREATE PROCEDURE dbo.p9 AS
BEGIN
  DECLARE @cur CURSOR;
  DECLARE @id INT;
  SET @cur = CURSOR LOCAL FAST_FORWARD FOR SELECT id FROM t1;
  OPEN @cur;
  FETCH NEXT FROM @cur INTO @id;
  CLOSE @cur;
  DEALLOCATE @cur;
END
```

```sql
-- tsql -> postgresql
CREATE OR REPLACE PROCEDURE p9()
LANGUAGE plpgsql
AS $$
DECLARE
    v_cur REFCURSOR;
    v_id INTEGER;
BEGIN
    OPEN v_cur FOR
    SELECT id FROM t1;
    NULL;
    FETCH v_cur INTO v_id;
    CLOSE v_cur;
    -- DEALLOCATE not needed in postgresql
END;
$$;
```

```sql
-- tsql -> mysql (MySQL has no cursor variables: the query moves onto the
-- declaration itself, and the bare OPEN is where it actually runs)
DELIMITER $$
CREATE PROCEDURE p9()
BEGIN
    DECLARE v_id INT;
    DECLARE v_cur CURSOR FOR SELECT id FROM t1;

    OPEN v_cur;
    FETCH v_cur INTO v_id;
    CLOSE v_cur;
    -- DEALLOCATE not needed in mysql
END$$
DELIMITER ;
```

`SET @cur = CURSOR ... FOR <query>` is folded into the `REFCURSOR`/
`SYS_REFCURSOR` declaration's `OPEN ... FOR <query>` (PostgreSQL/Oracle) or
into the `DECLARE ... CURSOR FOR <query>` itself (MySQL); the subsequent
bare `OPEN` — which, on the source, is what actually runs the query — has
nothing left to do on PostgreSQL/Oracle (the `OPEN ... FOR` already ran it),
so it is emitted as a `NULL;` no-op statement rather than re-opening the
cursor a second time, while on MySQL it stays as the real `OPEN`, since that
is where MySQL's own cursor first executes its query.

**Discussion.** PostgreSQL and Oracle refcursors, and MySQL's own cursor
declarations, only support "declare-with-query" or "open-with-query" as a
single step — there is no analogue to T-SQL's separate variable-then-`SET`
binding. Preserving the two-step shape literally (a separate assignment,
then a second, independent `OPEN`) would either not parse (a cursor
variable cannot be assigned like a scalar) or double-open the cursor.

> **Note** faithful — one cursor, opened exactly once, on every target; the
> `tsql -> tsql` identity keeps the original two-statement form verbatim
> (`test_cursor_variable_tsql_identity_keeps_variable_form`), confirming the
> merge is target-specific rather than a lossy parse of the source.

**See Also.** [`test_cursor_variable_to_postgresql_opens_for_query`, `test_cursor_variable_to_oracle_opens_for_query`, `test_cursor_variable_to_mysql_merges_query_into_declaration`](../../../tests/integration/test_cursor_variable_binding.py) —
no dedicated challenge-corpus case exercises cursor variables, so the
example above is drawn from that dedicated integration test.
