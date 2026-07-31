[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Cursor attribute mapping" direction="tsql → oracle/postgresql/mysql" kind=article order=40 -->

# T-SQL `@@FETCH_STATUS` → Oracle / PostgreSQL / MySQL

**Problem.** T-SQL exposes cursor state through a single global variable,
`@@FETCH_STATUS`, checked right after a `FETCH` (`0` = a row was returned,
`-1` = no more rows, `-2` = the fetched row is missing). Oracle, PostgreSQL,
and MySQL each expose cursor state a different way, and none of them spell
it `@@FETCH_STATUS`.

**Solution.**

```sql
-- tsql source
CREATE PROCEDURE p AS
BEGIN
  DECLARE @c CURSOR
  DECLARE @v INT
  SET @c = CURSOR FOR SELECT a FROM rt
  OPEN @c
  FETCH NEXT FROM @c INTO @v
  WHILE @@FETCH_STATUS = 0
  BEGIN
    PRINT @v
    FETCH NEXT FROM @c INTO @v
  END
  CLOSE @c
  DEALLOCATE @c
END
```

```sql
-- tsql -> oracle:
...
    OPEN V_C FOR SELECT a FROM rt;
    FETCH V_C INTO V_V;
    WHILE V_C%FOUND LOOP
        DBMS_OUTPUT.PUT_LINE(V_V);
        FETCH V_C INTO V_V;
    END LOOP;
    CLOSE V_C;
...

-- tsql -> postgresql:
...
    OPEN v_c FOR SELECT a FROM rt;
    FETCH v_c INTO v_v;
    WHILE FOUND LOOP
        RAISE NOTICE '%', v_v;
        FETCH v_c INTO v_v;
    END LOOP;
    CLOSE v_c;
...

-- tsql -> mysql:
...
    DECLARE v_fetch_done INT DEFAULT FALSE;
    DECLARE v_c CURSOR FOR SELECT a FROM rt;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done = TRUE;
    OPEN v_c;
    FETCH v_c INTO v_v;
    WHILE NOT v_fetch_done DO
        SELECT v_v;
        FETCH v_c INTO v_v;
    END WHILE;
    CLOSE v_c;
...
```

`@@FETCH_STATUS = 0` (a row was returned) and `@@FETCH_STATUS <> 0`/`= -1`
(no more rows) are recognized as a pair and mapped per target: Oracle gets
the cursor's own `%FOUND`/`%NOTFOUND` (Oracle tracks fetch state per
cursor, so no synthesized variable is needed); PostgreSQL gets its implicit
`FOUND`/`NOT FOUND` boolean, set by the immediately preceding `FETCH`;
MySQL, which has no queryable fetch-state expression at all, gets a
synthesized `DECLARE ... DEFAULT FALSE` flag plus a
`DECLARE CONTINUE HANDLER FOR NOT FOUND SET <flag> = TRUE` that the engine
invokes automatically whenever a `FETCH` on that cursor exhausts the
result set, and the loop condition becomes `WHILE NOT <flag>`.

**Discussion.** T-SQL's `@@FETCH_STATUS` is global state, correct only if
you read it immediately after the `FETCH` it describes and no other cursor
is touched in between; Oracle's `%FOUND`/`%NOTFOUND` sidesteps that
entirely by living on the cursor itself. PostgreSQL's `FOUND` is scoped to
the routine, not the cursor, so it is reliable here for the same reason
`@@FETCH_STATUS` normally is: no other cursor operation runs between the
`FETCH` and the check. MySQL has no fetch-state expression to read at all —
the only way to observe "no more rows" is the `NOT FOUND` condition class,
which must be wired to a handler *before* the loop runs, so the flag it
sets is the only substitute reachable inside the loop condition. This is
the reverse direction of ["Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT`
→ T-SQL / MySQL"](oracle-cursor-attributes.md): that entry starts from
Oracle's per-cursor attributes and maps them onto T-SQL's/MySQL's shared
state; this one starts from T-SQL's shared `@@FETCH_STATUS` and maps it
onto each target's own idiom, including Oracle's richer per-cursor form.

> **Note** faithful — live-verified: the Oracle, PostgreSQL, and MySQL
> forms above all execute cleanly against a two-row cursor and stop the
> loop at the same point `@@FETCH_STATUS <> 0` would on T-SQL.

**See Also.** [`TestIrFetchStatusContext`](../../../tests/unit/core/procedural/test_transformer.py) ·
[Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL](oracle-cursor-attributes.md),
the reverse-direction sibling.
