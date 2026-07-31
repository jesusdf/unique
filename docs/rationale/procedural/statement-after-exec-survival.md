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

**Discussion.** *Why there is no direct mapping.* N/A — this is not a
cross-engine gap but a real defect: the `;`-split path that isolates the
degraded `EXEC` into its own carrier used to fold the **following** statement
into that same carrier, so `sp_rename`'s degrade silently swallowed the valid
`UPDATE` too (the warning named only `sp_rename`). With `GO`-separated
batches the `UPDATE` correctly survived — only the `;`-separated case was
affected.

> **Note** faithful for the `UPDATE` — no-silent-loss
> restored. `[limit]` for the `sp_rename` call itself, as above.

**See Also.** [`reda-ts-exec-swallow-next`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1211`](../../reference/warnings.md#unique-1211).
