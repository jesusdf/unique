[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="`%TYPE` / `%ROWTYPE` carrier without `--db-url`" direction="oracle → tsql/postgresql/mysql" kind=article order=5 -->

# Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL

**Problem.** `v_id employees.id%TYPE` declares a variable with
**whatever type** the referenced column currently has — a live binding to
the schema, not a fixed type name.

**Solution.**

```python
# tests/integration/test_procedural.py::test_type_reference_documented_then_restored
src = "CREATE PROCEDURE p (v_id employees.id%TYPE) AS BEGIN NULL; END;"
# oracle -> postgresql: carrier type + "UNIQUE: ... employees.id%TYPE ..." comment
# postgresql -> oracle (round trip): "employees.id%TYPE" restored, no carrier
```

Without `--db-url`: a permissive carrier type per
non-Oracle target (`SQL_VARIANT` on T-SQL, `TEXT` on PostgreSQL, `LONGTEXT` on
MySQL — Oracle keeps the `%TYPE` reference as-is, since it supports it
natively) with a `/* UNIQUE: employees.id%TYPE */` comment preserving the
original reference, plus a warning. With
`--db-url`: the reference resolves to the concrete column type from the live
catalog and no carrier is needed. On a **reverse** transpilation back to an
engine that supports `%TYPE` natively (i.e. back to Oracle), the original
`%TYPE` reference is restored from the comment rather than left as a carrier
— a faithful round trip.

**Discussion.** Only Oracle supports `%TYPE`/`%ROWTYPE`
natively. Resolving the *actual* column type requires a live catalog lookup
(`ALL_TAB_COLUMNS`); without a database connection, Unique has no way to
know what `employees.id`'s type is.

> **Warning** `[limit]` without `--db-url` (the carrier type may
> not match the real column type's behaviour exactly). Faithful with
> `--db-url`, and faithful on the Oracle-to-Oracle round trip either way.

**See Also.** [§6](../../03-unsupported.md) ("Oracle → T-SQL specifics") ·
[`TestUniqueCommentRestore::test_type_reference_documented_then_restored`](../../../tests/integration/test_procedural.py) —
no dedicated challenge-corpus case exercises `%TYPE` directly, so the
example above is drawn from that integration test ·
[`UNIQUE-1152`](../../reference/warnings.md#unique-1152).
