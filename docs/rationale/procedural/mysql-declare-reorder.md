[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="mysql" kind=article order=33 direction-inferred=true -->

# Leading `DECLARE` block reordered (MySQL): variables before cursors

**Problem.** MySQL requires every `DECLARE <cursor>` to come *after* every
`DECLARE <variable>` in the same block (error 1337, "Variable or condition
declaration after cursor or handler declaration") — a rule no other target
engine imposes, so a source routine that declares its cursor before its
scalar variables (a legal order on Oracle/T-SQL/PostgreSQL) needs its
leading declaration block reordered for MySQL specifically.

**Solution.**

```sql
-- corpus case ora-cursor
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER;
BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p()
BEGIN
    DECLARE v DECIMAL;
    DECLARE c CURSOR FOR SELECT 1 AS x FROM DUAL;

    OPEN c;
    FETCH c INTO v;
    CLOSE c;
END$$
DELIMITER ;
```

The source declares the cursor `c` first, then the scalar `v`; the MySQL
output reorders them (`v` first, `c` second) while leaving every other
statement — `OPEN`/`FETCH`/`CLOSE` — untouched.

**Discussion.** MySQL's declaration-ordering rule exists because cursor and
handler declarations bind to the block's *remaining* variable declarations
at parse time; Oracle, T-SQL, and PostgreSQL have no such ordering
constraint at all, so a source author is free to declare a cursor before
the variables it will fetch into. Reordering only the leading declaration
block (not any executable statement) is enough to satisfy MySQL's rule
without changing behavior.

> **Note** faithful — live-verified: "Compiles + CALL ok on MySQL." Purely a
> declaration reorder; no executable statement moves or changes.

**See Also.** [`TestMysqlCursorDeclOrder`](../../../tests/integration/test_challenge.py) ·
[`ora-cursor`](../../../tests/fixtures/challenge/challenge_oracle.sql).
