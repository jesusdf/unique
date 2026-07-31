[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Oracle CAST length: PL/SQL body vs. top-level SQL" direction="tsql → oracle" kind=article order=37 -->

# A lengthless character `CAST` reaching Oracle: valid inside a PL/SQL body, invalid as a bare top-level statement

**Problem.** A T-SQL cast to a character type with **no length given at
all** (a bare `CAST(x AS VARCHAR)`, as opposed to `VARCHAR(n)`) needs
opposite treatment depending on where it lands on Oracle. The line Oracle
draws is between a **PL/SQL expression** and a **SQL statement**, *not*
between "inside a routine body" and "top level" — a compiled body holds
both. In a PL/SQL expression (a `PRINT`/`DBMS_OUTPUT` argument, an
`IF`/`WHILE` condition) Oracle rejects **any** length-constrained cast
(`PLS-00103`); the only accepted form is lengthless. In a SQL statement —
a bare top-level statement *or* an embedded one inside a body
(`SELECT … INTO`, a subquery) — Oracle requires the char length
(`ORA-00906`, "missing left parenthesis"); a lengthless `VARCHAR2` is
rejected outright. Crossing those two axes (context × whether the source
gave a length) makes four quadrants, each with its own emitted form.

**Solution.**

*PL/SQL expression, lengthless source* — kept lengthless:

```sql
-- tsql → oracle
CREATE PROCEDURE p AS BEGIN PRINT CAST(5 AS VARCHAR); END;
-- =>
CREATE OR REPLACE PROCEDURE p
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(CAST(5 AS VARCHAR2));
END;
/
```

*PL/SQL expression, explicit source length* — the length is **dropped**
(keeping it is `PLS-00103`), in a `PRINT` argument and equally in an
`IF`/`WHILE` condition:

```sql
-- tsql → oracle
CREATE PROCEDURE p AS BEGIN IF CAST(5 AS VARCHAR(10)) = '5' PRINT 'x'; END;
-- =>
CREATE OR REPLACE PROCEDURE p
AS
BEGIN
    IF CAST(5 AS VARCHAR2) = '5' THEN
        DBMS_OUTPUT.PUT_LINE('x');
    END IF;
END;
/
```

*SQL statement, lengthless source* — Oracle's maximum `VARCHAR2` length is
**synthesized** (`ORA-00906` without it), for a bare top-level statement:

```sql
-- ts-stragg-within2, tsql → oracle
SELECT STRING_AGG(CAST(n AS VARCHAR), ',') WITHIN GROUP (ORDER BY id) FROM t;
-- =>
SELECT LISTAGG(CAST(n AS VARCHAR2(4000)), ',') WITHIN GROUP (ORDER BY id)
FROM t;
```

…and identically for a statement **embedded** in a routine body (a
`SELECT … INTO`, or a subquery nested inside a PL/SQL condition — the
subquery re-enters SQL statement context):

```sql
-- tsql → oracle
CREATE PROCEDURE p AS BEGIN DECLARE @v VARCHAR(10);
    SELECT @v = CAST(n AS VARCHAR) FROM t; END;
-- =>
… SELECT CAST(n AS VARCHAR2(4000)) INTO v_v FROM t; …
```

*SQL statement, explicit source length* — the source length is **kept**:

```sql
-- tsql → oracle
… SELECT @v = CAST(n AS VARCHAR(10)) FROM t; …
-- =>
… SELECT CAST(n AS VARCHAR2(10)) INTO v_v FROM t; …
```

**Discussion.** Oracle draws the line between these contexts, not between
"expression" and "SQL statement" generically, and not between top-level and
in-a-body: what decides the rule is whether the cast sits in a compiled
PL/SQL *expression* position or reaches Oracle's SQL engine as part of a
statement. A plain top-level `SELECT` is a SQL statement, and so is a
`SELECT … INTO` or a subquery *inside* a procedure body — all of them
require every `VARCHAR2` `CAST` to carry an explicit length, so a source
cast that gave none gets the type's own maximum, `VARCHAR2(4000)`, which
preserves any string the source could have produced; an explicit length is
kept as given. In a PL/SQL expression the reverse holds: a length is not
just unnecessary but invalid, so a lengthless source stays lengthless and
an explicit one is stripped. The same numeric rule follows (a
`CAST(x AS NUMBER(10,2))` used as a PL/SQL expression is `PLS-00103` too, so
the precision is dropped there), and `CLOB` follows the same split — kept as
`CLOB` in a PL/SQL expression, remapped to `VARCHAR2(4000)` in a SQL
statement, where `CAST(x AS CLOB)` is `ORA-22849`.

> **Note** faithful (both directions) — all four quadrants live-compiled
> `VALID` on Oracle 23c; the synthesized top-level/embedded `VARCHAR2(4000)`
> form executes and returns the source value unchanged.

**See Also.** Corpus [`ts-cursor-attr`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`ts-stragg-within2`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestPlsqlExpressionCastContext`](../../../tests/integration/test_challenge.py),
[`TestWave4Rewrites::test_stragg_cast_sized`](../../../tests/integration/test_challenge.py).
