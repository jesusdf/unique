[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Cross-statement schema-state-driven coercion" direction="tsql → postgresql" kind=article order=5 -->

# T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)

**Problem.** T-SQL's `ALTER COLUMN <c> <type>` bakes type *and* nullability
into one clause — omitting a `NULL`/`NOT NULL` keyword does not mean
"leave nullability alone," it means "make the column nullable," silently
dropping an existing `NOT NULL` the statement never mentioned.
PostgreSQL's `ALTER COLUMN` instead separates the two into distinct
sub-clauses (`TYPE` vs. `SET`/`DROP NOT NULL`), so a PostgreSQL script can
have a type-only `ALTER COLUMN ... TYPE` statement that says nothing about
nullability at all. Read that literally into T-SQL and the column loses its
constraint; read a T-SQL statement literally into PostgreSQL's syntax and
the two clauses do not exist as one.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestB10RunningColumnTypeAlterNullability (_N9)
CREATE TABLE t (a INT NOT NULL, b TEXT);
ALTER TABLE t ALTER COLUMN a TYPE BIGINT;
ALTER TABLE t ALTER COLUMN a DROP NOT NULL;
-- postgresql -> tsql:
CREATE TABLE t (
  a INT NOT NULL,
  b NVARCHAR(MAX)
)
GO
ALTER TABLE t ALTER COLUMN a BIGINT NOT NULL
GO
ALTER TABLE t ALTER COLUMN a BIGINT NULL
```

The first `ALTER COLUMN` (a type-only change on the source) re-states the
column's known `NOT NULL`; the second (an explicit `DROP NOT NULL`) sees
the *new* type, `BIGINT`, not the original `INT` — both facts come from the
same running column-state map, which also survives an intervening `RENAME
COLUMN` (`test_rename_column_folds_into_running_map`: a column renamed
`a` → `a2` still carries its `NOT NULL` into a later `ALTER COLUMN a2 TYPE
BIGINT`). The reverse direction decomposes the other way:

```sql
-- tests/unit/core/test_transpiler.py::TestTranspiler::test_alter_column_postgres_type_then_nullability
ALTER TABLE dbo.t ALTER COLUMN c INT NOT NULL
-- tsql -> postgresql:
ALTER TABLE t ALTER COLUMN c TYPE INT;
ALTER TABLE t ALTER COLUMN c SET NOT NULL;
```

When the column's nullability genuinely cannot be known — the script never
`CREATE`s or otherwise declares the table being altered — Unique does not
guess silently; it emits a documented, warned degrade instead
(`test_unknown_column_warns`):

```sql
-- postgresql -> tsql, ALTER TABLE wtb10_ext ALTER COLUMN x TYPE BIGINT; (wtb10_ext never CREATEd in-script)
-- UNIQUE-1010: T-SQL ALTER COLUMN defaults the column to NULL; the script does
-- not define wtb10_ext.x's nullability, so it cannot be re-stated — verify
-- the column keeps its constraint
ALTER TABLE wtb10_ext ALTER COLUMN x BIGINT
```

**Discussion.** Neither engine's `ALTER COLUMN` grammar maps onto the
other's one-for-one: T-SQL always restates the full column definition in
one clause (type + nullability + identity), PostgreSQL always splits type
changes from constraint changes into separate sub-clauses. A literal,
context-free rewrite in either direction either drops a constraint the
statement never mentioned (PostgreSQL → T-SQL) or fails to parse (T-SQL's
combined clause has no single PostgreSQL equivalent). The fix requires
tracking column state across the *whole* script, not just the statement
being converted.

> **Warning** `[limit]`/warned on the PostgreSQL → T-SQL direction only
> when the column's nullability is genuinely unknown in-script
> (`UNIQUE-1010`, best-effort `NULL` emitted, verify by hand or supply
> `--db-url` to harvest live schema). Faithful whenever the column's
> `CREATE TABLE` (or a prior `ADD COLUMN`/`ALTER`) is present in the same
> script; faithful and unconditional on the T-SQL → PostgreSQL
> decomposition (nullability is always explicit in the T-SQL source
> clause).

**See Also.** [`TestB10RunningColumnTypeAlterNullability`](../../../tests/integration/test_pg_source_wave1.py), [`test_alter_column_postgres_type_then_nullability`](../../../tests/unit/core/test_transpiler.py) ·
[`UNIQUE-1010`](../../reference/warnings.md#unique-1010).
