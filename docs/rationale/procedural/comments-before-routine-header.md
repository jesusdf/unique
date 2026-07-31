[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Comments written before a routine header" direction="—" kind=overview order=16 -->

# Comments written before a routine header

**Problem.** You annotate a routine from the outside — `-- author note`
lines immediately before `CREATE PROCEDURE` — and expect them to survive
the migration. On Oracle, trivia sitting *outside* the `CREATE OR REPLACE`
unit is at the mercy of script tooling: SQL*Plus splits units on `/`, and
comments stranded between units are silently discarded by several
execution paths.

**Solution.** Unique relocates leading comments *into* the routine's
declaration section, where every target's body protects them:

```sql
-- Calculates monthly totals for reporting.
CREATE PROCEDURE get_totals AS BEGIN SELECT 1; END
-- => (Oracle)
CREATE OR REPLACE PROCEDURE get_totals (...) IS
    -- Calculates monthly totals for reporting.
BEGIN ...
```

**Discussion.** Comments carry no SQL meaning, but they are the *author's*
content — dropping them silently would lose the one piece of documentation
a human reads after the migration. Placing them at the top of the
declaration section is the only position that is safe on every target's
execution model (Oracle unit splitting, PostgreSQL `$$` bodies, MySQL
`DELIMITER` blocks).

> **Note** faithful — content preserved verbatim; only the position moves
> (from before the header to the top of the declaration section).

**See Also.** [`TestLeadingCommentRelocation`](../../../tests/integration/test_procedural.py).
