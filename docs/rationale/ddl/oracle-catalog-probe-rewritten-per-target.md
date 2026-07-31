[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="DDL guards" direction="oracle → tsql/postgresql" kind=article order=29 -->

# Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view

**Problem.** An Oracle PL/SQL script sometimes checks its own data
dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for
example resolving an index's owning table before a table-less `DROP INDEX`
(Oracle names only the index; T-SQL requires the table too, error 159), or
gating an `ALTER TABLE ... MODIFY` on whether a column already has the
target shape. `user_indexes`/`user_tab_cols` are Oracle-only views —
carrying them verbatim to another engine is not just unfaithful, it's
invalid SQL there.

**Solution.**

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestOracleCatalogOnTsql::test_table_less_drop_index_resolves_table
DECLARE v_exists NUMBER;
BEGIN
    SELECT count(*) INTO v_exists FROM user_indexes WHERE index_name = 'IX_H_F10';
    IF v_exists = 1 THEN
        execute immediate 'DROP INDEX IX_H_F10';
    END IF;
END;
/
-- oracle -> tsql (the table is resolved from sys.indexes at run time, since
-- T-SQL's DROP INDEX needs it and Oracle's script never named it):
DECLARE @exists DECIMAL;
SELECT @exists = COUNT(*) FROM sys.indexes WHERE name = 'IX_H_F10';
IF @exists = 1
BEGIN
    DECLARE @uq_ixtbl1 sysname = (SELECT TOP (1) OBJECT_NAME(object_id) FROM sys.indexes WHERE name = 'IX_H_F10');
    IF @uq_ixtbl1 IS NOT NULL EXEC(N'DROP INDEX [IX_H_F10] ON [' + @uq_ixtbl1 + ']');
END
```

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestWave11Classes::test_alter_modify_inside_guard
DECLARE v_e NUMBER;
BEGIN
    SELECT count(*) INTO v_e FROM user_tab_cols WHERE table_name = 'D_TB' AND column_name = 'R1';
    IF v_e = 1 THEN
        execute immediate 'ALTER TABLE D_TB MODIFY R1 NUMBER(9) NULL';
    END IF;
END;
/
-- oracle -> tsql:
DECLARE @e DECIMAL;
SELECT @e = COUNT(*) FROM sys.columns WHERE OBJECT_NAME(object_id) = 'D_TB' AND name = 'R1';
IF @e = 1
BEGIN
    ALTER TABLE D_TB ALTER COLUMN R1 NUMERIC(9) NULL;
END

-- oracle -> postgresql:
DO $$
DECLARE
    v_e NUMERIC;
BEGIN
    SELECT COUNT(*) INTO v_e FROM information_schema.columns WHERE table_name = lower('D_TB') AND column_name = lower('R1');
    IF v_e = 1 THEN
            ALTER TABLE D_TB ALTER COLUMN R1 TYPE NUMERIC(9), ALTER COLUMN R1 DROP NOT NULL;
    END IF;
END $$;
```

**Discussion.** This is the mirror of the T-SQL-sourced guard family: there
the catalog condition sometimes gets *dropped* in favor of a target's
native `IF [NOT] EXISTS` clause; here, Oracle's own dictionary lookup is
*rewritten* to the equivalent query against the target's own system view,
because a plain drop is not always available — T-SQL's `DROP INDEX`
syntactically requires the table name that the Oracle script never had to
supply, so the table itself has to be resolved from `sys.indexes` at run
time before the `DROP` can be built. The column-existence probe behind an
`ALTER ... MODIFY` follows the same idea: `user_tab_cols` becomes
`sys.columns` (T-SQL, matched via `OBJECT_NAME(object_id)`) or
`information_schema.columns` (PostgreSQL, matched with a `lower(...)`
compare, since Oracle identifiers default to upper case while
PostgreSQL's catalog stores them lower case) — the query keeps the same
row-existence semantics, just phrased against the target's own metadata
tables.

> **Note** faithful — the rewritten probe answers the identical
> existence question the Oracle script asked, so the guarded DDL runs
> exactly when the source script intended it to.

**See Also.** [`test_oracle_source_m4_wave.py`](../../../tests/integration/test_oracle_source_m4_wave.py)
(`TestOracleCatalogOnTsql::test_table_less_drop_index_resolves_table`,
`TestWave11Classes::test_alter_modify_inside_guard`) ·
[§6](../../03-unsupported.md), "Procedural Engine — Known Limitations"
("Oracle-source catalog probes rewritten per target") ·
[T-SQL system-catalog DDL guards](tsql-existence-guard-catalog-probes.md)
(the forward direction).
