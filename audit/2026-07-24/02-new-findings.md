# 02 — New findings (v0.30.0, HEAD 69a71cd)

RED-style audit at the close of the 862-case challenge campaign (0 open).
Severity legend as in previous audits: **S1** invalid/lost/semantically changed
output with no warning; **S2** degraded meaning or a guarantee that doesn't
hold; **S3** valid but suboptimal / cosmetic / drift.

Every S1 below satisfies the RED bar: the source was validated on its live
engine, the output was confirmed invalid or semantically different on the live
target (containers `unique-postgres-1` / `unique-mssql-1` / `unique-oracle-1` /
`unique-mysql-1`), and `result.warnings` / `result.unsupported` were empty for
the construct.

---

## N1 (S1). `INSERT … ON DUPLICATE KEY UPDATE` / `ON CONFLICT` silently dropped — every direction

```text
IN  (mysql):
    INSERT INTO kv (k, v) VALUES ('a', 1) ON DUPLICATE KEY UPDATE v = VALUES(v) + 1;

OUT (tsql, postgresql, oracle — all):
    INSERT INTO kv (k, v) VALUES ('a', 1)

IN  (postgresql):
    INSERT INTO kv (k, v) VALUES ('a', 1) ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1;
    INSERT INTO kv (k, v) VALUES ('b', 2) ON CONFLICT DO NOTHING;

OUT (tsql, mysql):
    INSERT INTO kv (k, v) VALUES ('a', 1)
    INSERT INTO kv (k, v) VALUES ('b', 2)

warnings: []   unsupported: []   (all directions)
```

The whole upsert clause vanishes: an idempotent upsert becomes a plain INSERT
that either raises a duplicate-key error at runtime or (under `IGNORE`-style
retry logic) corrupts data. This is a *class* drop, not one spelling — MySQL
`ON DUPLICATE KEY UPDATE`, PG `ON CONFLICT (…) DO UPDATE`, and PG
`ON CONFLICT DO NOTHING` all disappear on every target, including
PG→MySQL where a direct equivalent (`ON DUPLICATE KEY UPDATE`) exists.
Both sources were executed successfully on their live engines.

Notably, the *green* corpus case `pg-insert-select-conflict`
(`tests/fixtures/challenge/challenge_postgresql.sql:367`) still exhibits the
drop — it was closed for the `generate_series` half, and its FE run passed only
because that table has no unique constraint (the `DO NOTHING` is a no-op
there).

**Mechanism:** sqlglot models the clause as `exp.Insert.args["conflict"]`
(`exp.OnConflict`); `_convert_insert`
(`src/unique/core/converter/convert.py:1348`) reads `columns` / `expression` /
`with` but never `conflict`, so the clause dies at IR construction — the exact
"sqlglot unread-args" leniency class the workflow skill warns about. The only
converter site that mentions `conflict` (`emit.py:2391`) handles a RETURNING
interaction, reachable only when the clause survives, which it never does.

**Fix:** model the conflict clause on `InsertStatement` (target action +
key + assignments), emit natively where an equivalent exists (MySQL ⟷ PG,
tsql → MERGE via the existing canonical-MERGE writer in
`converter/_base.py:508`, Oracle → MERGE) and degrade with a carrier + warning
elsewhere. Until modeled, an unread `conflict` arg must at minimum raise a
warning (add a converter-side unread-args guard for `Insert`).

## N2 (S1). T-SQL MERGE conditional DELETE → Oracle: `DELETE WHERE` evaluates post-UPDATE values

```text
IN  (tsql):
    MERGE INTO dst AS d USING src AS s ON d.id = s.id
    WHEN MATCHED AND d.qty = 0 THEN DELETE
    WHEN MATCHED THEN UPDATE SET d.qty = s.qty;

OUT (oracle):
    MERGE INTO dst d USING src s ON (d.id = s.id)
    WHEN MATCHED THEN UPDATE SET d.qty = CASE WHEN NOT (d.qty = 0) THEN s.qty ELSE d.qty END
    DELETE WHERE d.qty = 0;

warnings: []
```

Live comparison with `dst = {(1,5), (2,0)}`, `src = {(1,0), (2,7)}`:

- SQL Server (original): row 2 deleted, row 1 updated 5→0 → final `{(1,0)}`.
- Oracle (transpiled): **0 rows remain.** Oracle's `DELETE WHERE` examines the
  row *after* the update, so row 1 (updated to 0) also matches `d.qty = 0` and
  is deleted.

The T-SQL first-match-wins semantics evaluate the DELETE condition on the
*original* row. The fold is only value-equivalent when the delete condition
references no target column assigned by the UPDATE (source-column conditions
like `s.qty = 0` are safe — that variant checks out fine).

**Mechanism:** `_merge_extended_clauses`
(`src/unique/core/converter/emit.py:634-731`). The docstring covers the
"DELETE WHERE only examines *updated* rows" pitfall (hence the CASE-keep
update) but not the second Oracle rule: the `DELETE WHERE` condition is
evaluated against post-update column values. Both clause orders are affected
(UPDATE-first folds `NOT(uc) AND dc` into the tail, where `uc`/`dc` on target
columns also read post-update state). The corpus case `ts-merge-full`
(`challenge_sqlserver.sql:243`) only exercises source-column conditions, so it
stays green.

**Fix:** fold only when the DELETE-relevant conditions reference no column that
appears on the left side of the UPDATE SET (walk `d_active`/`u_active` for
columns of the target alias against the SET list); otherwise degrade with a
carrier + warning (or lower via a pre-computed key set, e.g. a follow-up
`DELETE … WHERE EXISTS(join AND dc)` executed *before* the MERGE when no
INSERT clause exists).

## N3 (S1). T-SQL MERGE `OUTPUT` → PostgreSQL: invalid `RETURNING $action`, or silently re-attached / swallowed

```text
IN  (tsql, valid — returns 2 rows UPDATE/DELETE on live SQL Server):
    MERGE INTO dst AS d USING src AS s ON d.id = s.id
    WHEN MATCHED THEN UPDATE SET d.qty = s.qty
    OUTPUT $action, inserted.id;

OUT (postgresql):
    MERGE INTO dst AS d USING src AS s ON d.id = s.id
    WHEN MATCHED THEN UPDATE SET qty = s.qty RETURNING $action, id;

warnings: []
```

Live PG: `ERROR: syntax error at or near "RETURNING"` (PG 16 has no MERGE
RETURNING; on PG 17 `$action` would still be invalid — the spelling is
`merge_action()`). Three sibling manifestations, all warning-free:

1. Plain MERGE (above): invalid output.
2. With a `WHEN NOT MATCHED BY SOURCE` clause, the split moves the tail onto
   the follow-up statement: `DELETE FROM dst AS d WHERE NOT EXISTS (…)
   RETURNING $action, id;` — even if it parsed, it would return rows for the
   anti-join DELETE only, not for the whole MERGE.
3. With an interleaved comment, the tail lands *inside a trailing `--`
   comment* (`-- qty sync RETURNING $action, id`) — the result set silently
   disappears.

Oracle and MySQL targets produce the documented
"no standalone OUTPUT/RETURNING result set" carrier + warning for the same
input (`docs/03-unsupported.md`; corpus `ts-insert-output`/`ts-update-output`
are approved limits for INSERT/UPDATE OUTPUT → Oracle). The PG MERGE path has
no such gate.

**Mechanism:** the OUTPUT→RETURNING rename is applied for PG
(`src/unique/core/converter/emit.py:1419` qualifies OUTPUT items;
the per-target "no standalone OUTPUT/RETURNING" gate that fires for
Oracle/MySQL doesn't fire for postgresql because PG *does* have RETURNING —
but not on MERGE), and `_merge_extended_clauses` + the follow-up splice
(`emit.py:2574`) never account for a pending OUTPUT tail.

**Fix:** treat OUTPUT-on-MERGE → PG as its own case: translate `$action` to
`merge_action()`/gate on PG-version knowledge, keep the RETURNING on the MERGE
statement (never the follow-up), and degrade with the existing
carrier + warning when the BY-SOURCE split or the version gate makes it
untranslatable.

## N4 (S1). PostgreSQL MERGE `WHEN MATCHED … THEN DO NOTHING` passed through to T-SQL/Oracle

```text
IN  (postgresql):
    MERGE INTO dst AS d USING src AS s ON d.id = s.id
    WHEN MATCHED AND s.qty IS NULL THEN DO NOTHING
    WHEN MATCHED THEN UPDATE SET qty = s.qty
    WHEN NOT MATCHED THEN INSERT (id, qty) VALUES (s.id, s.qty);

OUT (tsql):    … WHEN MATCHED AND s.qty IS NULL THEN DO NOTHING …   → Msg 102: Incorrect syntax near 'DO'
OUT (oracle):  … WHEN MATCHED AND s.qty IS NULL THEN DO NOTHING …   → ORA-02000: missing THEN keyword

warnings: []   (both)
```

`DO NOTHING` is a PG-only merge action (sqlglot models it as
`Var(this=DO NOTHING)` in the `whens`). `_merge_extended_clauses`
(`emit.py:634`) special-cases only `Var("DELETE")`; anything else falls through
to sqlglot's generator, which emits the PG spelling verbatim in every dialect.
The output gate does not catch it (sqlglot parses it back leniently).

**Fix:** in the merge lowering, translate a `DO NOTHING` action by *dropping
the clause and folding its condition* (negated) into the conditions of the
remaining MATCHED clauses (first-match-wins makes `DO NOTHING` a condition
carve-out; for Oracle it composes with the existing CASE fold), else degrade
warned.

## N5 (S1). Oracle nested cursor loops: duplicate MySQL labels, stale NOT-FOUND flag, wrong `@@FETCH_STATUS` cursor

Source (compiles VALID on live Oracle): two cursors `c1`/`c2`, inner loop over
`c2` inside the `c1` loop, standard `FETCH … EXIT WHEN cN%NOTFOUND`.

**(a) MySQL — invalid output.** Both loops are labeled `loop_lbl`:

```text
loop_lbl: LOOP
        FETCH c1 INTO v_p; …
        loop_lbl: LOOP …
        END LOOP loop_lbl; …
END LOOP loop_lbl;
```

Live MySQL: `ERROR 1309 (42000): Redefining label loop_lbl`. No warning.
Mechanism: the emitter hardcodes the label (`procedural/emitter/mysql.py:142`,
also 438-496) instead of generating a per-loop-depth unique one.

**(b) MySQL — stale handler flag.** A single `v_fetch_done` flag serves both
cursors (`DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done = TRUE`) and
is never reset: once the inner cursor exhausts, the flag stays TRUE and the
*outer* loop's `IF v_fetch_done THEN LEAVE` exits after one parent — silent
row loss even once (a) is fixed. The standard pattern is a per-loop flag reset
(`SET v_fetch_done = FALSE`) after each inner loop / before each outer test.

**(c) T-SQL — wrong cursor's status.** `EXIT WHEN c1%NOTFOUND` maps to
`IF @@FETCH_STATUS <> 0 BREAK` (`procedural/transformer/tsql.py:283`, same at
616-619). The code comment itself says this is "correct right after that
cursor's FETCH" — but nothing enforces adjacency. With any other FETCH between
`FETCH c1` and the test (probe: open/fetch/close of `c2` in between), T-SQL's
single global `@@FETCH_STATUS` reflects the *other* cursor: with `children`
empty, the transpiled loop exits on the first iteration while Oracle processes
every parent. Silent, 0 warnings.

**Fix:** (a) unique label per emitted loop; (b) reset the flag after each
inner loop (or one flag per cursor via per-cursor handlers on distinct
`DECLARE … HANDLER` blocks/nested BEGIN scopes); (c) emulate per-cursor status
like the existing `%ROWCOUNT` counter (`@uq_<name>_rc`,
`transformer/tsql.py:633`): capture `@@FETCH_STATUS` into `@uq_<name>_fs`
immediately after each `FETCH <name>` and rewrite `<name>%NOTFOUND` to read the
captured variable; warn when adjacency cannot be proven.

## N6 (S1). `c%ISOPEN` emitted as the arithmetic expression `c % ISOPEN`

```text
IN  (oracle, procedure compiles VALID live):
    IF c%ISOPEN THEN CLOSE c; END IF;

OUT (tsql):   IF c % ISOPEN BEGIN CLOSE c; END      -- '%' is modulo; c, ISOPEN unknown identifiers
OUT (mysql):  IF c % ISOPEN THEN CLOSE c; END IF;   -- same

warnings: []   (both)
```

The cursor-attribute emulation (commit 1c7c5f5) maps `%FOUND` / `%NOTFOUND` /
`%ROWCOUNT` (`procedural/transformer/tsql.py:281-284`, `mysql.py:209-211`) but
not `%ISOPEN`; the lexer's generic `%` token then survives to emission as a
modulo operator between two undeclared identifiers — invalid on both targets,
no warning.

**Fix:** T-SQL has a faithful mapping —
`CURSOR_STATUS('local','c') >= -1` (or a `@uq_c_open` flag set on OPEN/CLOSE,
which also works for MySQL); at minimum, an unmapped `%<attribute>` must hit
the unrecognized-construct gate instead of leaking through as arithmetic.

## N7 (S1). PG transaction access modes passed through to T-SQL / MySQL

```text
IN  (postgresql, valid live):
    BEGIN;
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY;
    …
    COMMIT;

OUT (tsql):   SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY;   → Msg 102: Incorrect syntax near 'SERIALIZABLE'
OUT (mysql):  SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY;   → ERROR 1064 (MySQL needs "…SERIALIZABLE, READ ONLY")

warnings: []   (both)
```

The plain form `SET TRANSACTION READ ONLY;` → T-SQL likewise passes through
verbatim (live: Msg 156, `Incorrect syntax near the keyword 'READ'`) with no
warning. The mysql-source direction was fixed in the campaign
(`my-set-transaction`, `challenge_mysql.sql:679` — `START TRANSACTION READ
ONLY` maps per target and T-SQL gets a documented "no access modes" note), but
the pg-source `SET TRANSACTION …` spellings never reach that mapping:
`batch_splitter.py:313` routes them to the DML pipeline, where they fall back
to a `Command` passthrough rendered verbatim; the access-mode handling in
`emit.py:2331-2366` only matches the mysql-source spellings.

**Fix:** extend the emit-side access-mode/isolation mapping to the PG
`SET TRANSACTION [ISOLATION LEVEL …] READ ONLY|READ WRITE` statement class:
comma-join characteristics for MySQL, strip the access mode with the existing
documented note for T-SQL, and keep Oracle's first-statement rule handling.

## N8 (S1). T-SQL money literal `$12.50` → garbage column reference / invalid `$`

```text
IN  (tsql, valid live — returns 12.5000):
    SELECT $12.50 AS price;

OUT (postgresql):  SELECT "$12".50 AS price;    → ERROR: syntax error at or near ".50"
OUT (oracle):      SELECT $12.50 AS price FROM DUAL;   → ORA-00911: $: invalid character

warnings: []   (both)
```

sqlglot misparses the currency literal as
`Column(this=Literal(50), table=Identifier($12))` — a column `50` of table
`$12` — and the converter accepts that shape silently, so PG gets a quoted
identifier `"$12"` and Oracle the raw `$`. (`ts-cast-money`/`ts-money` in the
corpus cover the MONEY *type* and `CONVERT(MONEY, '$12.99')`, not the bare
literal.)

**Fix:** intercept at conversion time — a `Column` whose table identifier
matches `^\$[\d.,]+$` (sqlglot's known money-literal mangle) is a currency
literal; rebuild it as the numeric literal (T-SQL money semantics: `12.50`)
with the same strip-`$`-and-commas logic `ts-cast-money` added for CONVERT.
This also belongs in the garbage-shape detector class from the 07-08 audit
(N3 there): a parse that yields `table.column` where the "table" is not a
valid identifier should never pass silently.

## N9 (S1). Cross-statement column-type metadata is stale after `ALTER … TYPE`, and the T-SQL `ALTER COLUMN <type>` emission drops NOT NULL

```text
IN  (postgresql, valid live — ends with a BIGINT, still NOT NULL until dropped):
    CREATE TABLE t (a INT NOT NULL, b TEXT);
    ALTER TABLE t ALTER COLUMN a TYPE BIGINT;
    ALTER TABLE t ALTER COLUMN a DROP NOT NULL;

OUT (tsql):
    CREATE TABLE t (a INT NOT NULL, b NVARCHAR(MAX))
    GO
    ALTER TABLE t ALTER COLUMN a BIGINT          -- (i) silently becomes NULLable
    GO
    ALTER TABLE t ALTER COLUMN a INT NULL        -- (ii) silently reverts the type to INT

warnings: []
```

Live-verified on SQL Server: after (i) the column is `bigint, is_nullable=1`
(T-SQL defaults ALTER COLUMN to NULL when nullability is unspecified, while
PG's `ALTER … TYPE` preserves NOT NULL — a silently dropped constraint); after
(ii) the column is `int` again — a silent type change with
truncation/overflow risk for values beyond INT range.

**Mechanism:** two halves of the new COLUMN_TYPES feature (commit 79a9e2d):

- `harvest_column_types` (`src/unique/core/converter/harvest.py:189`) reads
  only `CREATE TABLE` bodies — later `ALTER … TYPE` (and `ADD COLUMN`, which
  at least degrades warned) never update the map, so the nullability rewrite
  (`emit.py:2056-2075`) re-states the *original* type.
- The ALTER-TYPE emission for T-SQL (`emit.py:1607-1626`) emits
  `ALTER COLUMN c <type>` without re-stating nullability even though the
  harvest knows the column is NOT NULL.

**Fix:** make the harvest a running scan in statement order — apply
`ALTER … TYPE` / `ADD COLUMN` / `RENAME COLUMN` to the map as the script
progresses (the transpiler already visits statements in order); and when
emitting T-SQL `ALTER COLUMN` for a type change, append the column's known
nullability (`NOT NULL` when the map says so), warning when unknown.

## N10 (S1). Dynamic-SQL string literals are executed untranslated, with no warning

```text
IN  (tsql):
    CREATE PROCEDURE run_dyn AS
    BEGIN
      DECLARE @sql NVARCHAR(MAX) = N'SELECT TOP 5 name, GETDATE() FROM users ORDER BY name';
      EXEC sp_executesql @sql;
    END

OUT (postgresql):   v_sql TEXT := 'SELECT TOP 5 name, GETDATE() FROM users ORDER BY name';
                    EXECUTE v_sql;
OUT (oracle, EXEC(@sql) variant):  V_SQL NVARCHAR2(2000) := N'SELECT TOP 5 name FROM users ORDER BY name';
                    EXECUTE IMMEDIATE V_SQL;

warnings: []   unsupported: []   (both; same for the top-level DECLARE+EXEC form)
```

The surrounding shell converts perfectly (`EXECUTE` / `EXECUTE IMMEDIATE`),
which makes the output *compile* — and then fail at runtime, executing T-SQL
text on PG/Oracle. Fragment-level rewrites do exist (the corpus'
`ts-dyn-concat-loop` translates `sys.tables` inside a concatenated string), but
a whole SQL statement in a single string literal is left byte-identical with no
warning. `docs/03-unsupported.md` §6 closes with "These limitations are
reported as warnings during transpilation" — not here, so this is an
undocumented silent gap, not an approved limit (the approved sp_executesql
limits cover parameter *binding*, which does warn).

**Fix:** when a string variable (or literal argument) reaches an
`EXEC`/`sp_executesql`/`EXECUTE IMMEDIATE` sink, route its content through the
transpiler (the STRING_VARIABLES/IR_EMBEDDED machinery already tracks these)
and splice the translated text; when the content doesn't parse as SQL, emit the
existing "review dynamic SQL" warning. Never ship an untranslated executable
string silently — this is the no-silent-loss invariant applied one quote-level
down.

---

## N11 (S2). `SQL%ROWCOUNT` → MySQL `ROW_COUNT()`: matched-rows vs changed-rows

```text
IN  (oracle):  UPDATE dst SET qty = :v WHERE id = :i;  IF SQL%ROWCOUNT = 0 THEN INSERT …
OUT (mysql):   UPDATE dst SET qty = … ;                IF ROW_COUNT() = 0 THEN INSERT …
warnings: []
```

Live: after `UPDATE rc_t SET v = 7 WHERE id = 1` on a row already holding 7,
Oracle `SQL%ROWCOUNT` = **1**, MySQL `ROW_COUNT()` = **0**. The
update-then-insert-if-zero idiom (exactly the shape the cursor-attribute
feature was tested with) inserts a duplicate on MySQL whenever the update was a
no-op value-wise. Mapping: `procedural/transformer/mysql.py:209` (also
`base.py:2904`), warning-free. T-SQL's `@@ROWCOUNT` counts matched rows and is
fine. Fix direction: this is exactly the class §3.22 "annotated inherent
divergences" exists for — emit the annotation carrier + warning on
`SQL%ROWCOUNT`→`ROW_COUNT()` (MySQL's `CLIENT_FOUND_ROWS` flag makes it
connection-dependent, so a note is honest), or emulate with
`ROW_COUNT()`… no faithful emulation exists — warn.

## N12 (S2). "Statement preserved as a comment" preserves a mid-transform hybrid, not the statement

```text
IN  (tsql):
    SELECT JSON_VALUE(doc, '$.name') AS n, JSON_QUERY(doc, '$.items') AS items FROM docs;

OUT (oracle/postgresql/mysql):
    -- UNIQUE: unmapped operator JSONExtractScalar; no oracle mapping. Statement preserved as a comment
    -- SELECT ISNULL(JSON_QUERY(doc, '$.name'), JSON_VALUE(doc, '$.name')) AS n, dbo.JSON_EXTRACT(doc, '$.items') AS items
    -- FROM docs
```

The carrier claims to preserve the statement, but the comment holds a
half-transformed tree re-rendered in the source dialect: `dbo.JSON_EXTRACT`
exists in no dialect, and `ISNULL(JSON_QUERY…, JSON_VALUE…)` is the *converted*
accessor pair, not the input. A user uncommenting this for manual rewrite gets
garbage on every engine — the same repr-leak class as the 07-23
PassthroughSQL-in-expr invariant, one level up. Warned, but the warning lies
(RED rules: a mislabeled warning is a defect). Fix: preserve the original
batch text (the converter has it) in unmapped-operator carriers, not the
re-rendered tree; assert in the carrier test that the comment body round-trips
through the *source* parser.

---

## N13 (S3). `validate_source` false positive: PG's `TABLE t`

`validate_source("TABLE t", "postgresql")` returns
`not a valid SQL statement`, but `TABLE t;` is valid PostgreSQL
(shorthand for `SELECT * FROM t`). Since the API/CLI refuse invalid input on
this signal, a legal PG script is rejected. (The 07-08 N3 false negatives —
`banana banana`, `CREATE TALBE` — are all fixed.) Mechanism: the bare-statement
check in `src/unique/core/validation.py` treats the parse as a bare
identifier. Fix: whitelist `exp.Table`-statement parses for dialects that
support the `TABLE` command.

## N14 (S3). MERGE comment handling: leading comment dropped, inline comment duplicated

In the N3 probe, the standalone comment `-- keep totals in sync` before
`WHEN MATCHED` disappears on every target (comments are trivia and must be
preserved), while `/* qty sync */` is emitted twice — inline in the UPDATE and
again as a trailing `-- qty sync` line merged with the dropped OUTPUT tail.
Cosmetic, but it is the mechanism that produced N3's worst variant (the
RETURNING tail swallowed into a comment).

## N15 (S3, process). `FINDINGS.md` still carries 429 rows while the corpus has 0 `[open]` cases

`tests/fixtures/challenge/FINDINGS.md` (2,228 lines, 429 `##` entries) still
lists per-case rows (e.g. `my-adddate`, `my-avg-int`) whose corpus cases are
`[fixed]`/`[limit]`. The challenge-corpus skill says BLUE "removes it from
FINDINGS.md" on closing and the batch ends with "every row in FINDINGS.md
cleared" — the ledger is stale and will mislead the next RED session's
de-duplication. Prune it (or mark the residual header as historical).

## N16 (S3, reliability). One-off non-reproducible `DML transpilation failed: 'into'`

Observed once: `BEGIN; SET TRANSACTION READ ONLY; SELECT * FROM t; COMMIT;`
(pg → tsql and → mysql, same process) produced
`/* TRANSPILATION ERROR: 'into' */` on the SELECT plus a
`DML transpilation failed: 'into'` warning — a `KeyError('into')` escaping some
transform. 15 immediate re-runs of the identical input and a
PYTHONHASHSEED 0-9 sweep were all clean; the only guarded `args["into"]` sites
are `convert.py:360/582`. Recording the exact strings so it can be recognized
if it recurs; a `logger.exception`-with-traceback at
`transpiler/_core.py:1104` (currently logs only `str(e)`) would make the next
occurrence diagnosable.

---

## Improvement opportunities (ordered by leverage)

1. **Unread-args tripwire for the DML converter.** N1 (conflict), N3 (OUTPUT
   tail through the merge splitter) and N4 (non-DELETE Var actions) are all
   "sqlglot modeled it, the converter didn't read it" bugs. A debug-mode
   assertion that diffs the set of sqlglot args consumed during conversion
   against the args present, warning on any unread key, would have caught all
   three — and future sqlglot upgrades that add args.
2. **Adjacency-safe cursor-status emulation as a class.** N5(c) fixes
   `%NOTFOUND`; the same captured-variable pattern (`@uq_<name>_fs`) closes
   `%FOUND`, nested-loop `@@FETCH_STATUS`, and MySQL's handler-flag reset in
   one design. Worth doing once rather than per-attribute.
3. **Warn when a `#temp` table is used inside a converted procedure.** The
   `proc + SELECT INTO #w + cursor over #w` composition emits
   `SELECT id, qty INTO TEMPORARY w` inside plpgsql (invalid there),
   `IF ROW_COUNT = 0` (not a plpgsql variable), an Oracle
   `SELECT … INTO <table>` (PLS error) and Oracle `DROP TABLE IF EXISTS`
   (23ai-only) — all under one generic "review the statement" warning. The
   pieces (PG temp tables, Oracle GTT hoisting for `@table` variables) already
   exist; wiring `#temp` through them would fix a common proc shape.
4. **Top-level `BEGIN TRY/CATCH` routing.** A batch-level TRY/CATCH (very
   common in migration scripts) degrades to `Unhandled expression type:
   Command` (warned). The procedural engine already converts TRY/CATCH inside
   procedures; classify the top-level form as procedural like the IF-guard
   fix did.
5. **Round-trip Unique's own Oracle MERGE output.** The spliced
   `… DELETE WHERE …` tail (N2's carrier shape) cannot be re-parsed by sqlglot
   (`output_gate.py:452` knows this), so A→B→A of a conditional MERGE degrades.
   Teach the Oracle *parser* side the `UPDATE … DELETE WHERE` merge form
   (pre-splitting it before sqlglot, as other pre-parse hooks do).
6. **PG 17 feature gating.** `MERGE … RETURNING` + `merge_action()` and native
   `WHEN NOT MATCHED BY SOURCE` would close N3 and simplify the split path
   when the target is PG ≥ 17; a target-version option would let the emitter
   choose between native and lowered forms.
7. **mysql → oracle generated columns.** `c DECIMAL(12,2) AS (…) STORED`
   degrades (warned validity-gate carrier) though Oracle supports
   `GENERATED ALWAYS AS (…) VIRTUAL` — the emission just doesn't parse back;
   a small emit fix away from parity with the PG/T-SQL targets.
8. **Harvest `ADD COLUMN` into COLUMN_TYPES** (the warned half of N9): the
   type is in the statement; tracking it turns a carrier into a correct
   emission.
