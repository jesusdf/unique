[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Triggers" direction="cross-engine" kind=article order=26 direction-inferred=true -->

# Empty trigger body → synthesized `SET NOCOUNT ON;` no-op (T-SQL)

**Problem.** T-SQL forbids an empty statement block: `BEGIN END` alone after
a trigger header is a syntax error. Other engines allow an intentional no-op
body (`BEGIN END`, or one that only ever held comments before trivia is
stripped).

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushZ4bBatch::test_empty_trigger_body_gets_executable_noop
CREATE TRIGGER t1_bu AFTER UPDATE ON t1 FOR EACH ROW BEGIN END
-- mysql -> tsql:
CREATE TRIGGER t1_bu ON t1
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
END
```

**Discussion.** `SET NOCOUNT ON` is already Unique's standard filler for a
T-SQL routine body that would otherwise be empty (it suppresses the
row-count message and has no observable effect on data) — reused here
rather than inventing a trigger-specific placeholder.

> **Note** faithful — the trigger still fires and does nothing, matching the
> source's empty body; the only difference is the now-syntactically-required
> statement, which has no data effect.

**See Also.** [`TestZeroPushZ4bBatch`](../../../tests/unit/core/test_ir_first_families.py) —
a related, weaker guard
(`TestZeroPushW5Batch::test_comment_only_trigger_body_gets_noop`) checks the
same invariant conditionally (*if* the emitted trigger body is comment-only,
it must also carry the no-op filler) rather than pinning a genuinely
comment-only source body — that test's own fixture body is not actually
comment-only (`CALL p1();`), so it is cited here for context, not as an
independent proof of the comment-only case.
