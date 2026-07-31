[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="DDL guards" direction="tsql → oracle/postgresql/mysql" kind=article order=28 -->

# T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe

**Problem.** A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER`
with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP
TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id =
OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the
same script doesn't fail on an object that's already there (or already
gone). `sys.objects`/`OBJECT_ID`/`sys.columns` are T-SQL-only catalog
views: no other engine can evaluate that condition, but simply dropping it
would break the idempotent intent the script relied on.

**Solution.** An object-existence `CREATE` guard:

```sql
-- tests/unit/core/test_guard_translation.py::TestGuardIdempotencyOnNativeTargets
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('s1.t1'))
BEGIN
    CREATE TABLE [s1].[t1] ([id] [int] NOT NULL)
END
-- tsql -> postgresql / mysql (the condition is dropped; the target's own
-- native guard carries the idempotency):
CREATE TABLE IF NOT EXISTS s1.t1 (id INT NOT NULL);

-- tsql -> oracle (no native guarded CREATE; synthesized):
BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_objects WHERE object_name = 'T1' AND object_type = 'TABLE')) LOOP
    EXECUTE IMMEDIATE q'[CREATE TABLE s1.t1 (id NUMBER(10) NOT NULL)]';
  END LOOP; END;
/
```

A narrower **column**-existence guard (no target has an "ADD COLUMN IF NOT
EXISTS" to fall back on, so every target gets a full synthesized probe):

```sql
-- tests/unit/core/test_guard_translation.py::TestFaithfulColumnProbeGuard
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE [object_id] =
    OBJECT_ID('s1.t1') AND [name] = 'c1' AND default_object_id <> 0)
BEGIN
    ALTER TABLE [s1].[t1] ADD DEFAULT ((0)) FOR [c1]
END
-- tsql -> postgresql:
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = lower('t1') AND column_name = lower('c1')
          AND column_default IS NOT NULL
    ) THEN
        ALTER TABLE s1.t1 ALTER COLUMN c1 SET DEFAULT ((0));
    END IF;
END $$;

-- tsql -> mysql:
SET @unique_guard_sql = (SELECT IF(NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 't1' AND column_name = 'c1'
      AND column_default IS NOT NULL
), 'ALTER TABLE s1.t1 ALTER COLUMN c1 SET DEFAULT ((0))', 'DO 0'));
PREPARE unique_guard_stmt FROM @unique_guard_sql;
EXECUTE unique_guard_stmt;
DROP PREPARE unique_guard_stmt;

-- tsql -> oracle:
BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (
      SELECT 1 FROM user_tab_columns
      WHERE table_name = UPPER('t1') AND column_name = UPPER('c1')
        AND default_length IS NOT NULL)) LOOP
    EXECUTE IMMEDIATE 'ALTER TABLE s1.t1 MODIFY c1 DEFAULT ((0))';
  END LOOP; END;
/
```

**Discussion.** Two different tactics apply depending on what the guard
protects, because the targets' own native tools differ:

- **Object existence** (a whole `CREATE`/`DROP`). PostgreSQL and MySQL
  already have their own native "`IF [NOT] EXISTS`" clause on `CREATE
  TABLE`/`FUNCTION` and `DROP ...`, so the T-SQL catalog condition is
  simply dropped and the target's own clause carries the same
  re-run-safe intent forward — same effect, different mechanism. Oracle
  has no such native clause (pre-23ai) and DDL can never be a conditional
  *statement* inside PL/SQL — it can only run through `EXECUTE IMMEDIATE`
  — so the condition needs a real substitute: a one-row cursor `FOR` loop
  probing `user_objects` from `DUAL` lets the whole guard be a single
  compact statement (a plain PL/SQL `IF` would need a surrounding
  `DECLARE`/`BEGIN` block instead). A guarded `DROP` — usually
  unconditional in intent, since the source's `IF ... IS NOT NULL` just
  means "if it's there" — instead becomes a tolerant
  `EXECUTE IMMEDIATE` wrapped in `EXCEPTION WHEN OTHERS THEN NULL`, lighter
  than the `FOR` loop since there's nothing to branch on afterward.
- **Column existence** (`ALTER TABLE ... ADD`/`ALTER COLUMN`). None of
  PostgreSQL, MySQL or Oracle has an "ADD COLUMN IF NOT EXISTS" or "ALTER
  COLUMN IF EXISTS" clause, so dropping the condition here is unsafe on
  *any* target — a second run would raise "column already exists" (or
  silently re-apply a default/type change). Every target instead gets its
  own full synthesized catalog probe, keeping the original condition:
  PostgreSQL wraps the guarded `ALTER` in an anonymous `DO $$ ... IF NOT
  EXISTS (SELECT ... FROM information_schema.columns ...) THEN ... END
  IF; END $$;` block; MySQL — which has neither anonymous blocks nor an
  `IF` outside a stored routine — builds the `ALTER` as a string, gates
  it with `IF(...)` inside a `SET`, and runs it through
  `PREPARE`/`EXECUTE`/`DROP PREPARE`; Oracle reuses the same compact
  `FOR`-loop idiom as the object-existence case, this time probing
  `user_tab_columns`.
- An **`ELSE`** branch survives when its body is a diagnostic `PRINT`
  (rewritten to the target's own notice mechanism — `RAISE NOTICE`,
  `DBMS_OUTPUT.PUT_LINE`, or a MySQL `CONCAT`-built alternate statement
  run through the same `PREPARE`/`EXECUTE`); any other `ELSE` body, or a
  probe predicate outside the recognized set (plain existence,
  `default_object_id <> 0`, `is_identity`), is not guessed at — it falls
  back to the honest warned drop instead.

> **Note** faithful — a re-run against a target where the guarded
> object/column already exists (or is already absent) takes the exact
> no-op path the T-SQL script intended; live-validated idempotent on
> PostgreSQL and Oracle. No warning on the recognized shapes.

**See Also.** [`test_guard_translation.py`](../../../tests/unit/core/test_guard_translation.py)
(`TestDropGuardWithLeadingTrivia`, `TestBeginWrappedCatalogGuards`,
`TestGuardIdempotencyOnNativeTargets`, `TestFaithfulColumnProbeGuard`,
`TestGuardElseBranch`, `TestTrailingCommentOnGuardLine`) ·
[§6](../../03-unsupported.md), "Procedural Engine — Known Limitations"
(the two DDL-guard bullets this article replaces) · [Oracle catalog probes
inside dynamic DDL rewritten per target](oracle-catalog-probe-rewritten-per-target.md)
(the mirror direction) · [Non-catalog `IF EXISTS` real-data control flow →
Oracle cursor `FOR` loop](../procedural/if-exists-control-flow-to-oracle-for-loop.md)
(a different, control-flow mechanism using the same `FOR`-loop idiom).
