# 01 — Functional bugs

All findings reproduced on commit `b6632c3` (v0.7.0) via
`from unique.core import transpile`. Severity legend:

- **S1** — output is invalid SQL on the target engine, or a statement is
  silently lost/semantically changed with no warning.
- **S2** — output is valid but semantically wrong, or meaning is degraded
  (lost message text, etc.).
- **S3** — output is valid and safe but suboptimal / cosmetic.

---

## S1-1. Quoted identifiers lose their quoting

```text
IN  (mysql):  SELECT `select`, `from` FROM `order`
OUT (postgresql): SELECT select, from FROM order        -- syntax error

IN  (tsql):   SELECT [select] FROM [order] WHERE [key] = 1
OUT (mysql):  SELECT select FROM order WHERE key = 1    -- syntax error
```

Identifier quoting must be *translated* (`` ` `` ↔ `"` ↔ `[]`), never
stripped. Any real schema using reserved words or mixed-case identifiers is
corrupted. Also affects case-sensitivity semantics on PostgreSQL/Oracle
(quoted vs. folded identifiers).

## S1-2. Oracle `(+)` outer join → INNER JOIN without ON

```text
IN  (oracle): SELECT * FROM a, b WHERE a.id = b.id(+)
OUT (postgresql):
    SELECT * FROM a INNER JOIN b WHERE a.id = b.id
```

Two failures at once:

1. `INNER JOIN b` with no `ON`/`USING` is a **syntax error** on PostgreSQL.
2. Even if it parsed, `(+)` on `b` means **LEFT OUTER JOIN** — rows of `a`
   without a match must be kept. Rewriting to inner-join semantics silently
   drops rows. No warning is emitted.

If `(+)` cannot be rewritten faithfully, it must at minimum land in
`result.unsupported` with the original preserved in a carrier comment.

## S1-3. `MERGE` → MySQL: statement silently dropped, docs contradicted

```text
IN  (tsql):
    MERGE INTO t USING s ON t.id=s.id
    WHEN MATCHED THEN UPDATE SET t.v=s.v
    WHEN NOT MATCHED THEN INSERT (id,v) VALUES (s.id,s.v);
OUT (mysql):
    -- UNIQUE: MySQL has no MERGE; rewrite as INSERT ... ON DUPLICATE KEY UPDATE. Original:
    -- MERGE INTO t USING s ON t.id = s.id ...
```

- The executable output contains **no statement at all** — in a migration the
  upsert simply stops happening.
- `result.warnings == []` and `result.unsupported == []`: the API/CLI caller
  has **no programmatic signal** that anything was dropped. This directly
  contradicts the README ("nothing is silently lost") — the carrier comment
  exists, but a machine consuming `TranspileResult` sees a clean result.
- `docs/03-unsupported.md §3.6` claims the transpiler "decomposes MERGE into
  `INSERT ... ON DUPLICATE KEY UPDATE` … or separate INSERT and UPDATE
  wrapped in a transaction". Neither happens.

Fix (in order of value): populate `unsupported`/`warnings` unconditionally;
then implement the simple-case rewrite the docs already promise.

## S1-4. `DATEADD` → MySQL: missing `INTERVAL`

```text
IN  (tsql):  SELECT DATEADD(day, 7, GETDATE())
OUT (mysql): SELECT DATE_ADD(CURRENT_TIMESTAMP, 7, DAY);   -- syntax error
```

MySQL requires `DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY)`. Note
`DATE_ADD` is also 2-argument only — the 3-argument form never parses.

## S1-5. `ROWNUM` passes through to PostgreSQL

```text
IN  (oracle): SELECT * FROM t WHERE ROWNUM <= 5
OUT (postgresql): SELECT * FROM t WHERE ROWNUM <= 5   -- unknown column
```

No translation, no warning. `docs/01-compatibility.md` line 51 claims
`ROWNUM … ✅ → LIMIT / ROW_NUMBER()`. The simple `WHERE ROWNUM <= n` pattern
should become `LIMIT n` (or `FETCH FIRST n ROWS ONLY`).

## S1-6. `FROM dual` passes through to PostgreSQL/MySQL targets

```text
IN  (oracle): SELECT 1 FROM dual
OUT (postgresql): SELECT 1 FROM dual   -- relation "dual" does not exist
```

`FROM dual` must be dropped for PostgreSQL/T-SQL (kept for MySQL, which
tolerates it).

## S1-7. `ILIKE` passes through to MySQL

```text
IN  (postgresql): SELECT * FROM t WHERE name ILIKE '%a%'
OUT (mysql):      ... WHERE name ILIKE '%a%'   -- syntax error
```

MySQL comparisons are case-insensitive under default collations, so plain
`LIKE` (with a warning about collation dependence) is the right rewrite; for
T-SQL, `LIKE` likewise; for Oracle, `UPPER(x) LIKE UPPER(y)` or `REGEXP_LIKE
(..., 'i')`.

## S1-8. `GROUP_CONCAT` passes through to PostgreSQL

```text
IN  (mysql): SELECT GROUP_CONCAT(name SEPARATOR ', ') FROM t
OUT (postgresql): SELECT GROUP_CONCAT(name, ', ') FROM t   -- unknown function
```

Should be `STRING_AGG(name, ', ')`. Ironically the *reverse* direction is
mapped (see S2-1), so the mapping table is asymmetric.

## S1-9. Boolean literals reach T-SQL

```text
IN  (postgresql): SELECT * FROM t WHERE active = TRUE
OUT (tsql):       ... WHERE active = TRUE          -- invalid: no boolean literals

IN  (postgresql): CREATE TABLE t (ok BOOLEAN DEFAULT TRUE)
OUT (tsql):       CREATE TABLE t (ok BIT DEFAULT TRUE)   -- invalid default
```

The *type* is mapped (`BOOLEAN` → `BIT`) but the *literals* are not
(`TRUE`/`FALSE` → `1`/`0`). Same class of issue likely for Oracle targets
(< 23c has no BOOLEAN in SQL contexts).

## S1-10. `DEFAULT CURRENT_TIMESTAMP()` emitted for PostgreSQL

```text
IN  (mysql): CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY,
                             ts DATETIME DEFAULT CURRENT_TIMESTAMP)
OUT (postgresql): ... ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP()   -- syntax error
```

PostgreSQL rejects the parenthesized form; emit `CURRENT_TIMESTAMP` (no
parens) or `now()`.

## S1-11. Oracle emitter produces constrained parameter types

```text
IN  (tsql):  CREATE PROCEDURE dbo.upd_price @id INT, @pct DECIMAL(5,2) AS ...
OUT (oracle):
    CREATE OR REPLACE PROCEDURE upd_price
    (
        V_ID IN NUMBER(10),        -- PLS-00103: size not allowed here
        V_PCT IN NUMBER(5, 2)      -- PLS-00103
    )
```

Oracle formal parameters must use unconstrained types (`NUMBER`, `VARCHAR2` —
no length/precision). The routine will not compile. The type mapper needs a
"parameter position" mode that strips constraints for Oracle (and PL/SQL
return types).

Note: the live-syntax CI job apparently doesn't catch this, which suggests the
Oracle fixtures don't include a T-SQL-sourced procedure with sized numeric
parameters — worth adding as a regression fixture.

## S2-1. `STRING_AGG` → MySQL: wrong separator semantics

```text
IN  (postgresql): SELECT STRING_AGG(name, ',') FROM t
OUT (mysql):      SELECT GROUP_CONCAT(name, ',') FROM t
```

Valid MySQL, but **wrong**: `GROUP_CONCAT(name, ',')` concatenates `','` to
*each* value and joins with the default separator (`a,,b,,c,`), not
`GROUP_CONCAT(name SEPARATOR ',')`. Silent data corruption in results.

## S2-2. `THROW` loses the error message on every target

```text
IN  (tsql):  THROW 50001, 'not found', 1;

OUT (postgresql): RAISE EXCEPTION '%', 50001;
    -- the number becomes the message; 'not found' is gone, no carrier comment

OUT (oracle):     RAISE_APPLICATION_ERROR(-20001, 50001);
    -- message argument is the number; 'not found' is gone

OUT (mysql):      SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = 50001;
    -- at least documents the drop in a trailing comment, but the original
    -- message could simply be used as MESSAGE_TEXT
```

The natural mapping preserves the text: PG `RAISE EXCEPTION 'not found'
USING ERRCODE …`, Oracle `RAISE_APPLICATION_ERROR(-20001, 'not found')`,
MySQL `SET MESSAGE_TEXT = 'not found'`. Losing operator-facing error messages
makes migrated systems materially harder to run.

## S2-3. T-SQL assignment-select vs Oracle `SELECT INTO`: no-row behavior diverges

```text
IN (tsql):
    SELECT @old = price FROM products WHERE id = @id;
    IF @old IS NULL ...            -- reachable: no row leaves @old NULL

OUT (oracle):
    SELECT price INTO V_OLD FROM products WHERE id = V_ID;
    IF V_OLD IS NULL THEN ...      -- unreachable: no row raises NO_DATA_FOUND
```

In Oracle a zero-row `SELECT INTO` raises `NO_DATA_FOUND`, so the transpiled
`IF ... IS NULL` guard never fires and the caller sees an unhandled exception
instead. Faithful translation needs either an
`EXCEPTION WHEN NO_DATA_FOUND THEN V_OLD := NULL;` wrapper or a
`MAX(price)`/cursor-based rewrite. This is exactly the "silent semantic
drift" category the functional-equivalence harness is meant to catch — worth
adding as a scenario there.

## S3-1. Minor observations

- `SET NOCOUNT ON` and other T-SQL-only settings are correctly documented in
  carrier comments — good pattern, keep it.
- `SELECT * INTO #tmp` → PG `SELECT * INTO TEMPORARY tmp` is valid, but the
  more portable modern form is `CREATE TEMPORARY TABLE tmp AS SELECT …`
  (PG docs deprecate `SELECT INTO` for new code).
- `detection.py` contains weight-0 rules (`TEXT`, `BOOLEAN` for postgresql)
  that can never contribute to a score — dead entries; delete or weight them.

---

## Cross-cutting fix: warnings must be load-bearing

S1-2, S1-3, S1-5, S1-6, S1-7, S1-8, S2-2 all share one trait: **nothing
appears in `result.warnings` or `result.unsupported`**. Recommendation: add an
internal invariant (and a test) that any construct the transformer cannot map
1:1 *must* register a warning or unsupported entry. A cheap enforcement: scan
the emitted output for `/* UNIQUE:` / `-- UNIQUE:` carriers and assert each
one has a corresponding entry in the result object.
