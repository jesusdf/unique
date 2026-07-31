[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Dynamic SQL bind arguments copied into session variables" direction="oracle → mysql" kind=article order=56 -->

# `EXECUTE IMMEDIATE '...' USING v1, v2` (Oracle) → MySQL `EXECUTE ... USING @v1, @v2`, bound through session variables

**Problem.** Oracle's `EXECUTE IMMEDIATE '<sql>' USING bind1, bind2`
accepts routine locals and parameters directly as bind arguments. MySQL's
prepared-statement `EXECUTE stmt USING @v1, @v2` accepts only `@session`
variables as its bind list — a routine's own local variables or IN
parameters cannot be passed directly, since MySQL's `PREPARE`/`EXECUTE`
machinery only ever reads from session scope.

**Solution.**

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestMySqlExecuteUsingSessionVars
create or replace PROCEDURE p_dyn(v_a IN NUMBER, v_b IN VARCHAR2)
AS BEGIN
  EXECUTE IMMEDIATE 'BEGIN other_p(:1, :2); END;' USING v_a, v_b;
END;
/
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p_dyn
(
    IN v_a DECIMAL,
    IN v_b TEXT
)
BEGIN
    SET @_stmt = 'BEGIN other_p(:1, :2); END;';
    PREPARE _dyn FROM @_stmt;
    SET @_b1 = v_a;
    SET @_b2 = v_b;
    EXECUTE _dyn USING @_b1, @_b2;
    DEALLOCATE PREPARE _dyn;
END$$
DELIMITER ;
```

**Discussion.** Each bind argument gets its own synthesized session
variable (`@_b1`, `@_b2`, ...), assigned from the routine local
immediately before the `EXECUTE`, so the `USING` clause can reference only
`@`-prefixed names as MySQL's grammar requires — the dynamic SQL text
itself is copied into `@_stmt` first for the same structural reason
(`PREPARE` reads its source from a session variable or literal, never a
routine local). This mirrors the pattern MySQL's own dynamic-SQL machinery
always needs, independent of where the values being bound originally came
from.

> **Note** faithful — each bind position receives the identical value the
> routine local held; the session-variable hop is purely a scoping
> requirement MySQL's `PREPARE`/`EXECUTE` imposes, not a change to any
> bound value. No warning.

**See Also.** [`test_oracle_mysql_tail.py::TestMySqlExecuteUsingSessionVars`](../../../tests/integration/test_oracle_mysql_tail.py)
(`test_using_binds_are_session_variables`).
