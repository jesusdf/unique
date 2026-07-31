[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="tsql → mysql" kind=article order=35 -->

# T-SQL loop control (`BREAK`/`CONTINUE`, compound assignment) → MySQL labeled `LEAVE`/`ITERATE`

**Problem.** T-SQL's `BREAK`/`CONTINUE` act on the *nearest enclosing*
loop with no name required. MySQL has no such unlabeled form — its
`LEAVE`/`ITERATE` always target a specific loop **label**, so every
translated loop needs one, and two independently generated labels in the
same routine would collide (MySQL error 1309, a duplicate label).

**Solution.**

```sql
-- ts-continue-break, tsql → mysql
CREATE PROCEDURE p AS BEGIN
  DECLARE @i INT=1;
  WHILE @i<=3 BEGIN
    SET @i+=1;
    IF @i=2 CONTINUE;
    IF @i=5 BREAK;
  END;
END;

-- =>
CREATE PROCEDURE p()
BEGIN
    DECLARE v_i INT DEFAULT 1;

    loop_lbl_1: WHILE v_i <= 3 DO
            SET v_i = v_i + 1;
            IF v_i = 2 THEN
                        ITERATE loop_lbl_1;
            END IF;
            IF v_i = 5 THEN
                        LEAVE loop_lbl_1;
            END IF;
    END WHILE loop_lbl_1;
END
```

Each emitted `WHILE` loop is given its own unique, per-instance label
(`loop_lbl_1`, `loop_lbl_2`, …), and every `BREAK`/`CONTINUE` inside that
loop compiles to `LEAVE`/`ITERATE` targeting the same label — so nested
loops in the same routine never collide, whatever their nesting depth. The
compound assignment `@i += 1` is also expanded to `v_i = v_i + 1`, since
MySQL's procedural dialect has no `+=` operator. On Oracle and PostgreSQL,
which both support unlabeled `EXIT`/`CONTINUE` the way T-SQL's `BREAK`/
`CONTINUE` do, no label or rewrite is needed at all.

**Discussion.** MySQL's `LEAVE`/`ITERATE` are a structurally different
control-flow primitive from T-SQL's `BREAK`/`CONTINUE` — always
label-targeted rather than nearest-enclosing-loop-relative — so a literal
keyword rename isn't enough; every loop needs a label synthesized for it.
Generating that label uniquely *per emitted loop instance*, rather than
once per routine or reusing a fixed name, is what keeps nested loops safe:
a routine with two sibling or nested `WHILE` loops gets two distinct
labels, so `LEAVE`/`ITERATE` inside either one can only ever target its own
loop.

> **Note** faithful — live-verified: the compound assignment expands with
> no leftover `:= =` artifact, `BREAK`/`CONTINUE` map to `LEAVE`/`ITERATE`
> against the loop's own generated label on MySQL and to unlabeled
> `EXIT`/`CONTINUE` on Oracle/PostgreSQL, and no stray T-SQL `BREAK`
> keyword survives on any target.

**See Also.** Corpus [`ts-continue-break`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestTsqlLoopControl`](../../../tests/integration/test_challenge.py) ·
[Loop and cursor desugaring](loop-cursor-desugaring-overview.md), the topic
overview for this family.
