[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="ALTER COLUMN DROP DEFAULT" direction="postgresql → oracle/tsql" kind=article order=25 -->

# PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script

**Problem.** PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT`
removes a column's default expression by name-free reference — no other
engine has an equivalent "just remove whatever default is there" clause.
Oracle has no `DROP DEFAULT` syntax at all, and T-SQL's default is a
separately *named* constraint object (`DF_...`), which the source
statement never names — it can only be dropped by first looking its
generated name up.

**Solution.**

```sql
-- corpus case pg-drop-default
ALTER TABLE t ALTER COLUMN a DROP DEFAULT;
-- postgresql -> oracle (a default-less MODIFY reproduces "no default"):
ALTER TABLE t MODIFY a DEFAULT NULL;
-- postgresql -> tsql (the constraint name isn't in the source; resolved
-- from the catalog at run time):
DECLARE @n SYSNAME;
SELECT @n = dc.name FROM sys.default_constraints dc
  JOIN sys.columns c ON c.object_id = dc.parent_object_id
                     AND c.column_id = dc.parent_column_id
  WHERE dc.parent_object_id = OBJECT_ID('t') AND c.name = 'a';
IF @n IS NOT NULL EXEC('ALTER TABLE t DROP CONSTRAINT ' + @n);
```

**Discussion.** Oracle's `MODIFY <col> DEFAULT NULL` is the closest native
equivalent to "this column now has no default" — Oracle has no bare "drop
the default" clause, but re-declaring the default as `NULL` produces the
same observable effect (an `INSERT` omitting the column gets `NULL`, not a
computed value). T-SQL is the harder case: a column default there is
always an independently named object, and the source statement (like
PostgreSQL's own grammar) never names it — it can only be found by
querying `sys.default_constraints` joined back to the column at *run
time*, since the name isn't known until the script actually executes
against a real database. The generated script is therefore a small
self-contained catalog probe, in the same family as this project's other
DDL-guard catalog-probe syntheses, ending in a dynamic `ALTER TABLE ... DROP
CONSTRAINT` once the name is resolved.

> **Note** faithful — both targets end with the column carrying no default,
> matching PostgreSQL's own post-`DROP DEFAULT` state; the T-SQL script is
> a no-op (skips the `EXEC`) if the column already has no default
> constraint to drop. No warning.

**See Also.** Corpus [`pg-drop-default`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`test_challenge_assertions_postgresql.py` (`pg-drop-default`).
