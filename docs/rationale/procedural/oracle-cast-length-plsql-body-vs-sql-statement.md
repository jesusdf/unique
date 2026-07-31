[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Oracle CAST length: PL/SQL body vs. top-level SQL" direction="tsql → oracle" kind=article order=37 -->

# A lengthless character `CAST` reaching Oracle: valid inside a PL/SQL body, invalid as a bare top-level statement

**Problem.** A T-SQL cast to a character type with **no length given at
all** (a bare `CAST(x AS VARCHAR)`, as opposed to `VARCHAR(n)`) needs
opposite treatment depending on where it lands on Oracle. Left lengthless
as a plain top-level SQL statement, Oracle rejects it outright
(`ORA-00906`, "missing left parenthesis" — Oracle's `VARCHAR2` always needs
an explicit length there). Given one anyway inside certain PL/SQL
procedural expression positions, Oracle rejects *that* just as firmly
(`PLS-00103`) — the only form accepted there is the lengthless one.

**Solution.**

Inside a PL/SQL procedure body, a lengthless cast used as a plain
expression argument stays lengthless — shown here with a literal for
clarity (the pinning test exercises the same shape on T-SQL's
`@@CURSOR_ROWS` global):

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

As a standalone top-level SQL statement, the same kind of lengthless cast
instead gets Oracle's maximum `VARCHAR2` length:

```sql
-- ts-stragg-within2, tsql → oracle
SELECT STRING_AGG(CAST(n AS VARCHAR), ',') WITHIN GROUP (ORDER BY id) FROM t;
-- =>
SELECT LISTAGG(CAST(n AS VARCHAR2(4000)), ',') WITHIN GROUP (ORDER BY id)
FROM t;
```

**Discussion.** Oracle draws the line between these two contexts, not
between "expression" and "SQL statement" generically — what changes is
whether the cast sits inside a compiled PL/SQL procedure/function body at
all. A plain top-level `SELECT` has no such body: Oracle's SQL engine
requires every `VARCHAR2` `CAST` there to carry an explicit length, so a
source cast that gave none gets the type's own maximum, `VARCHAR2(4000)`,
which preserves any string the source could have produced. Inside a PL/SQL
body, the reverse rule applies in the position exercised here: adding a
length where the source gave none is not just unnecessary but invalid, so
the cast is left exactly as lengthless as the source specified it.

> **Note** faithful (both directions) — live-compiled `VALID` on Oracle for
> the lengthless-in-a-procedure-body form; the top-level `VARCHAR2(4000)`
> form executes and returns the source value unchanged.

**See Also.** Corpus [`ts-cursor-attr`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`ts-stragg-within2`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestPlsqlExpressionCastContext::test_print_cast_is_lengthless`](../../../tests/integration/test_challenge.py),
[`TestWave4Rewrites::test_stragg_cast_sized`](../../../tests/integration/test_challenge.py).
