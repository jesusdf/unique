[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="System procedures" direction="tsql → all" kind=article order=2 direction-inferred=true -->

# Statement-after-`EXEC` survival fix

**Problem.** A degraded system-proc `EXEC`, followed by another
statement on the same line separated only by `;` (not a batch-separating
`GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`.

**Solution.**

```sql
-- corpus case reda-ts-exec-swallow-next
EXEC sp_rename 't.a', 'b', 'COLUMN'; UPDATE t SET b = 1
-- every target: sp_rename becomes a UNIQUE: carrier + warning;
-- UPDATE t SET b = 1 still transpiles (present on postgresql/oracle/mysql)
```

Statements are split on `;` **before** degrading, so
only the `sp_rename` call becomes a carrier and the `UPDATE` still
transpiles normally on every target.

**Discussion.** Not a cross-engine gap — `sp_rename` and the following
`UPDATE` are two independent statements that happen to share one line,
separated by `;` rather than a batch-separating `GO`. Splitting on `;`
before degrading keeps the two statements independent, so the unmapped
`sp_rename` call's carrier never absorbs the `UPDATE` that follows it.

> **Note** faithful for the `UPDATE` — it survives untouched. `[limit]` for
> the `sp_rename` call itself, as above.

**See Also.** [`reda-ts-exec-swallow-next`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1211`](../../reference/warnings.md#unique-1211).
