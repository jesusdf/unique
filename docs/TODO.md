# Unique — Pending Work

This document tracks **outstanding** work, ordered by priority. Completed work
has been archived in [`docs/DONE.md`](DONE.md) (with the detailed why/how of
each fix); `docs/STATUS.md` summarizes the project state at a higher level.

Last reviewed: 2026-07-08. The functional-equivalence and 2026-07-02
audit-remediation backlogs are complete and archived in [`docs/DONE.md`](DONE.md)
(§18); source-syntax validation across core/API/web/CLI shipped (§34). The
**2026-07-08 follow-up audit** ([`audit/2026-07-08/`](../audit/2026-07-08/))
verified all 14 previous functional bugs fixed and opened the backlog below.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## 1. Oracle procedural output — validity backlog (P1) — ✅ DONE (26 -> 0)

**Complete.** The T-SQL procedures fixture (32 objects) now transpiles to
**fully-valid Oracle** — `test_procedures_fixture_is_valid_live[oracle]` asserts it
(the `xfail` is gone). The Oracle live-validator queries `USER_ERRORS` after each
`CREATE` (Oracle compiles PL/SQL *lazily*, so `CREATE` succeeds even for an invalid
body) and recompiles to settle forward dependencies. Detailed why/how of each fix
is archived in [`docs/DONE.md`](DONE.md); the arc, in brief:

- **Expression/type:** string-`+` -> `||`; subquery / CAST assignments and RETURNs
  are SQL-only in PL/SQL, so via `SELECT … INTO v FROM DUAL` (or a nested block);
  `SELECT TOP (n)` -> `FETCH FIRST`; CLOB/`SQL_VARIANT` -> bounded `VARCHAR2`;
  `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)`/`VARCHAR(MAX)`-cast/character-CAST length;
  `DATEDIFF` sub-day + canonical layout; `TIME_STR_TO_TIME` unwrap.
- **Structure (features):** bare result `SELECT` -> `SYS_REFCURSOR` OUT; `EXEC
  sp_executesql` -> `EXECUTE IMMEDIATE … USING`; **table variable -> hoisted GTT**;
  **trigger DECLARE section**; **reassigned IN parameters shadowed with locals**;
  **inline split TVF -> `SYS.ODCIVARCHAR2LIST` function** + `TABLE(fn(…))` callers.
- **Rules:** OUT/IN OUT params take no DEFAULT; procedure/trigger RETURN carries no
  value; no `AS` before a table alias.

## 2. Audit 2026-07-08 follow-ups

Findings from [`audit/2026-07-08/02-new-findings.md`](../audit/2026-07-08/02-new-findings.md)
(reproductions and mechanism analysis there).

### P1 — silent semantic changes (no-silent-loss violations)

- [x] **N1 (fixed in M2): unbracketed real-data `IF [NOT] EXISTS` guard dropped silently.**
      `IF NOT EXISTS (SELECT 1 FROM cfg WHERE k='x') INSERT …` (no `BEGIN`)
      loses the condition on every target with zero warnings — re-runs insert
      duplicates. `batch_splitter._classify` (line ~278) only protects the
      `BEGIN … END` form; drop the `_TSQL_BEGIN_BLOCK_RE` conjunct so any
      non-catalog guard routes to the procedural engine. Add single-statement
      INSERT/UPDATE/DELETE guard probes + an FE scenario running a guarded
      INSERT twice.
- [x] **N2 (fixed 2026-07-10): PG → T-SQL temp-table rename not
      script-wide.** Temp-table names are harvested once per transpile
      (`harvest_temp_tables` → `TEMP_TABLES` ContextVar, same pattern as
      `IDENTITY_COLUMNS`) and `_emit_table_ref` prefixes `#` on every
      reference for the T-SQL target — FROM, INSERT, DROP included.
      Tests: `tests/integration/test_temp_table_rename.py` (incl. the
      PG→T-SQL→PG round-trip and a non-temp negative).

### P2 — correctness of signals and validation

- [x] **Guard audit findings (2026-07-09, per-batch sweep of the private
      corpora):** test.sql/test2.sql clean (531 guarded batches, 0 losses);
      bigtest exposed three classes, all fixed: (1) `parse_sql` trusted
      sqlglot WARN-mode partial trees — a table-qualified column in an INSERT
      list shipped as `INSERT … DEFAULT VALUES` with the guarded SELECT gone;
      now parses with RAISE and degrades to an honest carrier (also catches
      mangled source fragments — N3 evidence). (2) The Oracle batch splitter
      treated a lone `/` (and directives) as structural inside `/* */` block
      comments, desyncing into orphan `*/ …` batches. (3) `emit_node(RawSQL)`
      embedded multi-line sqlglot error text after `-- UNIQUE:`, leaking its
      tail (unbalanced quote incl.) as executable output. Probes in
      `test_embedded_dml_ir.py` + `test_batch_splitter.py`; re-audit: 0
      losses on all 9 fixture×target pairs; test.sql→PG back at 100.0%.
- [x] **N3 (fixed 2026-07-10): `validate_source` false negatives → silent
      garbage.** A bare top-level `exp.Alias` (`banana banana`) is now
      flagged like the other non-statements, and a `CREATE` that fell back
      to an opaque Command is checked against a known object-kind allowlist
      (`CREATE TALBE` → "unrecognized CREATE object kind"; real unmodeled
      kinds like SYNONYM stay clean). Transpile-side, the parse-RAISE change
      (2026-07-09) already degrades such fragments to carriers. Tests:
      `TestBareAndTypoStatements`.
- [x] **N5 (fixed 2026-07-09): false-positive warning on a successful guard
      round-trip** — the blanket T-SQL FOR-loop warning is gone; degraded
      paths carry `-- UNIQUE:` markers that the reconciliation surfaces
      exactly when they fire. Test: `TestNoFalseGuardWarning`.
- [x] **N6 (fixed 2026-07-09):** `/api/v1/validate` and `/api/v1/detect` now
      enforce `MAX_SQL_BYTES` like `/transpile`. Test:
      `TestValidateDetectSizeCap`.
- [x] **N8 (fixed 2026-07-09): near-duplicate `unsupported` entries** — the
      reconciliation now skips carrier fragments already covered by an
      existing entry (3-word-shingle test). Test:
      `TestUnsupportedDeduplication`.
- [x] **N4/N9: docs drift (closed 2026-07-09)** — STATUS.md's guard-round-trip
      claim was corrected (unit tests, not FE); the project-overview skill
      says Python 3.13 and shows `converter/` as a package; README gained the
      "`latest` publishes only on release tags" note in the docs pass. The
      "map Unique's own emitted catalog guard back to the target catalog"
      idea moved into the *Faithful conditional for unmappable catalog
      guards* P2 item above.

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **Decide on the architecture proposals in
      [`audit/2026-07-08/04-architecture-analysis.md`](../audit/2026-07-08/04-architecture-analysis.md)**
      — adopted as proposed (P1 honesty gate, P2 comment trivia, P3 unified
      AST guard path, P4 embedded DML through the IR pipeline, P5
      validity-ratchet process, P6 per-direction tiering; sequencing M0–M4).
      Binding rules encoded in `skills/SKILL-development-workflow.md`
      ("Architecture guardrails", "Detect the wrong path"). The item-level
      bugs below are *instances* of those root causes — fix the classes
      (P2/P3/P4), not the instances one by one.
- [x] **M0 — productize the validity sweep** (`scripts/validity_sweep.py`) —
      done: transpiles a file to each target, executes per-statement on the
      live engines (PG savepoints, MySQL throwaway database, SQL Server
      `SET PARSEONLY ON`, Oracle throwaway schema), classifies
      syntax-vs-expected per engine error code, reports per-direction validity
      % + top error groups with samples. E1 fixed on the way: the statement
      splitters were consolidated into ONE shared string/comment-aware module
      (`tests/helpers/sql_split.py`, 13 unit tests) used by the FE engine
      runner, the live validators and the sweep — the old duplicated splitters
      (which split on `;` inside string literals) are gone. Tests:
      `tests/unit/helpers/test_sql_split.py`,
      `test_validity_sweep_classify.py`. Baselines (private corpus, empty
      DBs): pre-gate Oracle→T-SQL 71%, Oracle→PG 56%; **post-M1**:
      T-SQL→{PG 99.9%, MySQL 98.6%, Oracle 99.6%}, Oracle→{T-SQL 94.0%,
      MySQL 75.0%, PG 73.1%}.
- [x] **M1 — honesty gate** (`src/unique/core/output_gate.py`) — done:
      (a) plain DML/DDL output that doesn't parse under sqlglot in the target
      dialect degrades to a carrier (original source preserved) + a
      `validity_gate` warning + an `unsupported` entry; (b) ALL output is
      scanned outside comments/strings for source-dialect leftovers
      (ROWNUM/VARCHAR2/EXECUTE IMMEDIATE off Oracle, GETDATE/brackets off
      T-SQL, backticks off MySQL, stray GO / `/` terminators) and degrades
      whole on a hit — this catches invalid procedural units sqlglot can't
      judge; (c) duplicate warnings aggregate into one entry with an `(xN)`
      count. The splitter moved into the product
      (`unique/core/sql_split.py`) to support the gate. Tests:
      `tests/unit/core/test_output_gate.py` (17); full suite green with the
      gate active — zero false degradations on the curated corpus.
      *M1 residue resolved in M2:* the SET_OPTION fallback now labels
      non-SET batches honestly (feature=unhandled_batch + unsupported).
      Still open: fragment-level desync (D9) is only caught when a leftover
      token appears in the fragment.
- [x] **M2 — P2 comment trivia + P3 unified guard path** — done (clears the
      guard family: N1, N10, A1–A5). One shared `split_leading_trivia`
      (`unique/core/sql_split.py`) feeds the classifier, the guard matchers,
      `_oracle_needs_slash` and the fallback labels; the three per-spelling
      guard regexes collapsed into ONE `_extract_catalog_guard` (polarity +
      inner-trivia aware, BEGIN…END unwrap, OBJECT_ID arity-proof); non-catalog
      IF guards route to the procedural engine with or without BEGIN (N1);
      catalog CREATE-guards keep their idempotent intent per target
      (`_guard_idempotent`: Oracle probe, PG/MySQL native IF NOT EXISTS, MySQL
      index warned); NEWID/UUID maps per target inside procedural bodies via
      the shared `UUID_FUNCTION` table (A4). Tests:
      `tests/unit/core/test_guard_translation.py` (40, combinatorial neighbor
      matrix). Measured 2026-07-10 (post C1–C4 wave): **test.sql AND
      test2.sql at 100.0% on PG, MySQL and Oracle**.
- [ ] **M3 — P4 embedded DML through the IR converter**; delete the
      text-level rewriters (clears D3, D4, D8, A4 by construction).
      *M3a landed:* `_transform_embedded_dml` now routes through the shared
      `parse_sql → Transformer → emit_node` IR pipeline (raw sqlglot only as a
      warned fallback), which cleared D3 and D4 and surfaced+fixed four IR
      core bugs that also hit standalone DML: pass recursion stopped at
      top-level SELECTs (generic dataclass-field walker now), `find(exp.Where/
      Having)` duplicated a derived table's WHERE onto the outer SELECT,
      dropped parens/precedence on emit (silent `AND`/`OR` re-association),
      and `nulls_first` never carried (T-SQL DESC row order changed on PG).
      `exp.In`/unstyled `exp.Convert` are now modeled (IN was a RawSQL
      passthrough passes couldn't see; CONVERT now shares the CAST type maps).
      Three head-anchored matchers made trivia-aware via the shared
      `split_leading_trivia` (result-SELECT→refcursor, identity capture,
      trigger set-based rewrite). *M3b:* D8's remaining corruption was the
      T-SQL SELECT-INTO emitter's naive `split(",")` — fixed with the shared
      `split_top_level_commas`. Tests: `tests/integration/
      test_embedded_dml_ir.py` (22). **Measured (2026-07-09, live sweep):**
      test.sql→PG **100.0%** / Oracle 99.6% / MySQL 97.7% (unchanged classes);
      bigtest (Oracle source)→T-SQL **94.3%** / PG **76.6%** (was 73.1 — D3
      cleared) / MySQL 75.0%; live-syntax suite 53 passed. Transpile of the
      13 MB dump ~55 s (+22% vs pre-M3, linear). Still open: deleting the
      expression-level text rewriters — blocked on the M3-prereq below.
- [ ] **M3-prereq: move the procedural text-matchers onto structure before
      routing scalar expressions through the IR.** *Increment 1 landed
      2026-07-11 (`e8196ee`): the IR gains procedural variable types — a
      STRING_VARIABLES ContextVar published around every IR call lets the
      shared `_looks_like_string` classify `@a + @b` over declared string
      variables (fixed a live runtime bug: embedded UPDATE shipped
      `v_a + v_b` on PG). *Increment 2 landed 2026-07-11
      (`35c2155`, `33034ab`): the differential text-vs-IR audit found and
      fixed THREE live semantic bugs in the curated text handlers —
      DATEADD's '+' turned into '||' by the concat classifier (intervals
      now neutralize their literals), a token-joined '- 1' losing its
      sign inside the INTERVAL string (DATEADD(MONTH,-1) silently ADDED a
      month; literal counts compact, expression counts multiply a unit
      interval), and DATEDIFF DAY/MONTH/YEAR emitting Oracle-fractional /
      PG-AGE forms instead of T-SQL's boundary counts (both pipelines now
      share the boundary-counting forms).* Remaining increments: (3) the last-identity
      capture consumes a node, not a marker string; (4) dual-guard→IF and
      DECLARE-init hoisting consume nodes; then the text rewriters can
      shrink. Original blocker analysis:** A first attempt at IR-first
      for `_transform_raw_sql` expressions (M3b) broke 18 tests and was
      reverted: downstream machinery pattern-matches on the *transformed
      expression text* — the Oracle last-identity capture looks for a marker
      string, the dual-guard→IF and DECLARE-init hoisting match query
      spellings, `_rewrite_string_concat` uses declared-variable types the
      standalone IR doesn't have, and the curated DATEADD/DATEDIFF handlers
      produce live-validated forms the IR emitter doesn't. Those consumers
      must consume nodes (or the IR must gain procedural context: var types,
      PROCEDURAL_FUNC_MAPS) before the text rewriters can be deleted (P4's
      final step). Until then the text path stays the expression engine.
- [x] **M4 — Oracle-source bring-up — ✅ COMPLETE 2026-07-11.** Official
      validity_sweep at `7c1cea7` on the 13 MB dump (35k+ statements per
      direction): **oracle→T-SQL 0 syntax failures, oracle→PostgreSQL 0,
      oracle→MySQL 0 — 100.0% on all three** (from 475/41/121 at the
      start of the bring-up). Driven by the sweep frequency table
      (doc 03 §D backlog). ***Official sweep 2026-07-11 at `8f6e4a0` (post
      waves 15a–15f): T-SQL 99.9% (48), PostgreSQL 100.0% (10), MySQL
      100.0% (0 — the whole 18-class residue cleared).*** Residue
      classification (2026-07-11, from the sweep dumps): **(P1, silent
      corruption, all targets)** the PL/SQL CASE-*statement*→IF-chain
      rewrite joins the condition onto one line WITH inline `--` comments
      that sat between the CASE selector and `WHEN`, so the comment
      swallows `= 'x' THEN` (`IF v --comment = 'U' THEN`) — same trivia
      class as commit 9474f55 but in the CASE→IF path; accounts for the
      2x tsql-4145 and at least 1 PG fail. **(P1)** 2x PG `INSERT …
      (cols) DEFAULT VALUES` — the partial-parse corruption signature
      shipped (guard leak). **tsql 48:** ~15x error 195 — unqualified
      scalar-UDF calls; T-SQL *requires* `dbo.fn()` (the old "resolves on
      the real DB" assumption was wrong — error 195 fires even when the
      function exists), so qualify unknown functions with `dbo.`; plus
      unmapped scalars in raw/procedural contexts (EXTRACT→DATEPART,
      2-arg TRUNC→ROUND(x,d,1), TO_NUMBER, RPAD, EMPTY_BLOB); 2x
      duplicate `@x` declarations (134), 2x `@new` / `@@…` variable edges,
      date-literal + @dosis1 + misc 102s. **PG 10:** 2x ADD COLUMNS (a,b)
      → per-column ADD, 2x RAW(16) DEFAULT SYS_GUID() → `BYTEA DEFAULT
      gen_random_uuid()` type mismatch, missing-THEN edge, `X record`
      placement edge. ***Official sweep 2026-07-11 at `857b515` (post
      waves 16–18b): PostgreSQL 100.0% (0 — ZERO), MySQL 100.0% (0),
      T-SQL 100.0% (13 — 0.04%)*** — from 475/41/121 when M4 started.
      Waves 17a–18b closed: formatted TO_DATE/TO_CHAR (style table +
      FORMAT via the shared token model), RAW(16) GUID defaults on PG,
      embedded ALTER through the IR passthrough (`ADD COLUMNS` fixed),
      nested-block loop-record hoisting (shared _split_declarations),
      SYSDATE() empty-parens retry, case-insensitive var rename,
      cursor %FOUND/%NOTFOUND on T-SQL, %ROWTYPE loop-var double-@,
      loop-DECLARE dedupe per batch, raw RPAD/LPAD, bare RETURN in PG
      trigger functions → NEW/NULL, and incomplete T-SQL trigger
      conversions (NEW./OLD. leftovers) now degrade honestly via the
      gate. **2026-07-11 waves 19–19b** (official sweep at `638231e`):
      aliased single-table UPDATEs (5x — T-SQL's `UPDATE alias … FROM t
      alias` form + the trigger rewriter renormalizes it), ROWNUM = 1 →
      TOP 1, ROWNUM added to the tsql gate deny-list, quoted dateparts
      (`DATEDIFF('Y',…)`), parameterless CREATE FUNCTION parens.
      ***Waves 20–21 (2026-07-11, official sweep at `b19e03a`): T-SQL
      100.0% (3), PostgreSQL 0, MySQL 0.*** Closed: boolean-var IF/WHILE
      conditions (`= 1`), param-shadowing locals dropped, DISTINCT hoist
      in assignment-selects, **Oracle q-quoted literals** (`q'[…]'` —
      lexer feature; exposed that constant-EXECUTE-IMMEDIATE routine DDL
      must STAY dynamic, now warned), 2-arg SUBSTR with sign-aware start
      (balanced-paren scanner), and the `p_x`/`v_p_x` prefix-strip rename
      collision (error 134 + a silent aliasing risk). **The final 3 are
      ONE class:** scalar calls inside sqlglot-emitted MERGE passthrough
      text (DATEVALUE→dbo., 1-arg TO_CHAR, REGEXP_LIKE) — the shared
      function decisions (mappings + qualifier) never see passthrough
      output; run the tsql scalar pass + string-aware qualifier over
      MERGE passthrough text for the tsql target (REGEXP_LIKE itself has
      no SQL Server 2022 form — document as a visible limitation).* *Wave 16 landed
      2026-07-11:*
      the trivia class fix (`_flat_value` — every flattening capture, CASE
      selector/WHEN included), the parenthesized/UNION INSERT-body drop
      (silent DEFAULT VALUES corruption), structural `dbo.` qualification
      of scalar-UDF calls (error 195 — the "resolves on the real DB"
      assumption was wrong), and the scalar wave (EXTRACT→DATEPART,
      TRUNC(n,d), LPAD/RPAD via exp.Pad, EMPTY_BLOB/CLOB, TO_NUMBER /
      1-arg TO_CHAR/TO_DATE argument-aware — the old name renames emitted
      CONVERT/CAST missing the type argument). *Earlier waves:* Waves 13–14: derived-table aliases synthesized
      for every non-Oracle target (a shared cause across all three) +
      T-SQL's no-TOP ORDER BY dropped inside them; seq.NEXTVAL/CURRVAL;
      the cursor FOR-loop expansion completes for aliased expressions
      (COUNT(*) TOTAL) with the inline form's parens stripped
      (live-validated idempotent); anonymous-block CURSOR declarations
      hoisted into the DO $$ DECLARE section; the CLOB→VARCHAR(MAX) map no
      longer crashes the batch; oversized (N)VARCHAR caps to (MAX). Waves 11–12 added: the shared ALTER ... MODIFY
      rewriter (neither Oracle form parses in sqlglot), user_tab_cols →
      sys.columns / information_schema probes (case-folded on PG — a
      semantic fix, the guards never fired), ALTER TRIGGER ENABLE via
      catalog lookups, named-association LHS protected from the variable
      rename (EXEC p @@id = @id), EXEC expression-arguments hoisted
      (GETDATE() is not a valid EXEC argument — whole seeding batches), and
      the ROWNUM→TOP derived table aliased (T-SQL requires it). Wave 10 added: the sqlglot index NULLS-ordering
      CASE emulation stripped (25x — a T-SQL index key cannot be an
      expression), multi-column `ALTER ... DROP (a, b)` normalized per
      target, MYSQL_ERRNO magnitudes (Oracle's -20xxx codes, 20x),
      PIPELINED table functions preserved as documented carriers, bare
      VARBINARY sized in passthrough DDL, standalone-DML scalars on T-SQL
      (CHR/TO_NUMBER/MONTHS_BETWEEN), PG reserved column names and the
      top-level no-op leak. The waves: exception-scope folding (T-SQL
      TRY / MySQL handler blocks, NOT FOUND for NO_DATA_FOUND), trigger
      `UPDATE OF`/`WHEN` headers, event predicates (TG_OP / per-variant
      constants / ELSEIF), pseudo-row `INTO :NEW.col` targets, the PL/SQL
      CASE *statement* → IF chain, constant `EXECUTE IMMEDIATE` unwrap,
      Oracle-style `DROP INDEX` via a sys.indexes lookup, `user_*` catalog
      probes → `sys.*`, `SQL%ROWCOUNT`/`MONTHS_BETWEEN`/CHR/TRUNC/base
      builtins on T-SQL, unsized VARCHAR sizing, ref-cursor OUT params →
      direct result sets on T-SQL/MySQL, PG row-loop record declarations
      (+ shadowed-name rename), CALL-arg renames/pseudo-records, and the
      partial-parse corruption guard (INSERT → DEFAULT VALUES signature).
      Probes: `tests/integration/test_oracle_source_m4_wave.py` (23).
      Note: the T-SQL count is *flat vs. the morning's 127 but far more
      honest* — unwrapping constant dynamic SQL surfaced ~30 failures that
      previously hid as runtime missing-object noise inside EXEC() strings.
      *Remaining (tsql 54):* dominated by ~12 client-DB-resident UDFs
      (SVF_* — genuinely unresolvable without --db-url metadata; on the
      real target DB they resolve), PL/SQL collections (ARRAYTIPOALTA),
      and 2x edges (4145 non-boolean IF, 128, @dosis1, date literal,
      TO_NUMBER-in-raw). PG 10 — RETURN edges, ADD COLUMNS(...),
      2x bytea/uuid defaults. **MySQL 18 classified 2026-07-10** (dump hook +
      per-statement re-run against MySQL 8.4 for exact near-tokens):
      (a) 3x `MANUAL` is a *new reserved word in MySQL 8.4* — plain INSERT
      column lists need backtick-quoting (same class as the wave-10 PG
      reserved-column fix, MySQL table was stale); (b) 2x space between a
      special-grammar function and `(` — `EXTRACT ( YEAR FROM x)` does not
      parse (empirically: `SUM ( x )` fine, `EXTRACT ( … )` 1064) — raw-token
      join must not pad the paren; (c) 2x named-cursor FOR loop expansion:
      `DECLARE rowX_cur CURSOR FOR curES` is invalid (a MySQL cursor cannot
      alias another cursor — drive the named cursor directly), the scaffold
      `FETCH INTO /* col1… */` stays unresolved though every select-list item
      is aliased, and the DECLAREs land mid-body (MySQL wants them at block
      head — wrap the expansion in a nested BEGIN…END); (d) 2x bare `RETURN;`
      inside procedure/trigger handlers (only functions may RETURN — needs a
      labeled block + LEAVE); (e) 4x parser token-soup on unmappable PL/SQL
      declarations (`TYPE t IS VARRAY(n) OF …`, `RETURN pkg.col%TYPE`, REF
      CURSOR-returning functions) emitted as `DECLARE . LONGTEXT;` fragments —
      violates "a desynced unit degrades whole"; (f) 1x `DECLARE PRAGMA
      AUTONOMOUS_TRANSACTION` leak + `GROUP_CONCAT(… SEPARATOR CHR(13)||…)
      WITHIN GROUP (…)` (LISTAGG lowering must fold a constant separator to a
      literal and move ORDER BY inside); (g) 1x `EXECUTE … USING V_LOCAL` —
      MySQL prepared statements only bind session `@vars` (hoist args), and
      the constant `'BEGIN p(:1…); END;'` should unwrap to a direct CALL;
      (h) 1x `DROP SEQUENCE IF EXISTS` shipped raw (no MySQL sequences);
      (i) 1x `CREATE FUNCTION NOW()` — collides with the built-in, unmappable
      without renaming call sites. Silent-corruption findings from the same
      dump (parse-valid, wrong semantics — no-silent-loss violations to fix
      with the wave): Oracle `||` reaching MySQL raw expressions parses as
      logical OR (loop bodies, RETURN concat, SET assignments); numeric
      `+ 1` emitted as `CONCAT(…, 1)` / `|| 1`; `TRUNC(date)` emitted as
      1-arg `TRUNCATE` (grammar error) instead of `DATE()`; 3-arg
      `DATEDIFF('S',…)` instead of `TIMESTAMPDIFF`.
      Note: the compose `stop_grace_period: 30s` for mssql applies on the
      next `up -d` (containers keep their creation-time config).

- [x] **Faithful conditional for unmappable catalog guards (P2)** (done
      2026-07-10 for the sys.columns/syscolumns column-probe family, both
      polarities, `default_object_id <> 0` included): PG gets a `DO $$ IF
      [NOT] EXISTS(information_schema.columns …)` block, Oracle a
      `user_tab_columns` COUNT probe (+ `default_length` for the default
      predicate — `data_default` is a LONG) with EXECUTE IMMEDIATE;
      live-validated idempotent on both engines. Unrecognized predicates and
      MySQL (no anonymous blocks) keep the explicit `guard_dropped` warning.
      Tests: `TestFaithfulColumnProbeGuard`. Original text:** A T-SQL
      guard whose body has no native conditional form (e.g. `IF NOT EXISTS
      (SELECT … FROM sys.columns … default_object_id <> 0) ALTER … ADD
      DEFAULT`) currently drops the condition — since 2026-07-09 with an
      explicit `guard_dropped` warning (user report; it was silent). The
      emitted `SET DEFAULT`/`MODIFY` is re-runnable (the guard's main
      purpose) but overwrites an existing different default that T-SQL would
      have preserved. The faithful fix is translating the *condition* to the
      target's catalog (`information_schema.columns.column_default` on
      PG/MySQL, `user_tab_columns.data_default` on Oracle) wrapped in the
      target's conditional block — needs careful identifier-case mapping,
      so it must land with live-validated tests. Related to the N4/N9 note
      about mapping Unique's own emitted guards back.

### P1 — private-fixture live sweep (audit doc 03; anonymized repros there)

Found by transpiling the three `fixtures-private/` scripts across the matrix
and executing the outputs on the real engines. Ordered by attack value; every
fix needs an **anonymized** regression fixture (never a private name).

- [x] **A1/A2: guard batches with a leading comment, or `BEGIN…END`-wrapped
      `IF OBJECT_ID` guards, are commented out wholesale** on every target
      (mislabeled `set_option` warning). Fix the guard extractor to tolerate
      leading comments and unwrap `BEGIN…END`; likely clears N1 too.
- [x] **A3 (fixed in M2): leading comment suppresses the `/` terminator** of the emitted
      Oracle guard block — every following statement is swallowed in SQL*Plus.
- [x] **D3 (fixed in M3a): `INSERT … SELECT … FROM DUAL WHERE NOT EXISTS(…)` keeps
      `FROM DUAL`** on PG/T-SQL (~6,000× in the real Oracle dump). Root cause
      was transform-pass recursion stopping at top-level SELECTs; the generic
      recursion + the embedded-DML IR route fixed both pipelines. Probes in
      `test_embedded_dml_ir.py` (standalone + procedural, + scalar-subquery
      and IN-subquery neighbors).
- [x] **D1 (fixed in M4 bring-up, 2026-07-09): Oracle `EXEC proc` → `EXEC AS proc`**
      on every target (T-SQL impersonation syntax; PG/MySQL need `CALL`).
      Mechanism: SQL*Plus `EXEC` has no sqlglot model — it parsed as an
      *alias* and shipped `EXEC AS proc` with the arguments dropped. The
      classifier now routes Oracle `EXEC`/`EXECUTE` batches to the procedural
      engine, whose parser models them as `CallStatement`
      (`_parse_sqlplus_exec_call`; `EXECUTE IMMEDIATE` unaffected) and each
      target emits its call form. Probes:
      `tests/integration/test_exec_call_translation.py` (9, incl.
      args-never-dropped on all targets).
- [x] **SQL*Plus `SET` directives shipped raw (fixed in M4 bring-up, 2026-07-09)** —
      `SET SERVEROUTPUT ON` etc. (~940 invalid statements per direction on the
      real dump) are line-oriented client commands with no `;`, so they also
      glued to the following block and corrupted it. The Oracle splitter now
      peels a known-option directive line into its own SET_OPTION batch (at a
      statement boundary only — an UPDATE's `SET` clause is untouched), the
      SET_OPTION path comments it with a warning for oracle→X, and real SQL
      `SET TRANSACTION`/`SET CONSTRAINTS` now flows as `exp.Set` passthrough
      (it used to be misclassified as a session option). Tests:
      `test_batch_splitter.py::TestSqlPlusSetDirectives`,
      `tests/integration/test_sqlplus_directives.py`.
- [x] **D2 (fixed in M4 bring-up, 2026-07-09): top-level `DECLARE…BEGIN…END` keeps
      its PL/SQL skeleton in T-SQL** instead of flattening to `DECLARE @x…;
      <statements>`. The T-SQL emitter inherited the base's Oracle-style
      anonymous-block shell; it now overrides `_emit_anonymous_block` and
      flattens (a T-SQL batch *is* the block; ~500 statements on the dump).
      Tests: `tests/integration/test_anonymous_block_tsql.py`.
- [x] **D8 (fixed in M3b): silent expression corruption in procedural embedded DML** —
      `MAX(NVL(x,0)) + 1` loses `, 0))` and `+ 1` on T-SQL, and numeric `+`
      becomes `||` on PG. Mechanism: the T-SQL SELECT-INTO emitter split the
      select list with a naive `split(",")`, cutting inside the function call.
      Fixed with the shared paren/string-aware `split_top_level_commas`
      (`unique/core/sql_split.py`); embedded-DML `+` now flows through the IR
      (M3a). Probes + oracle→tsql→oracle round-trip in
      `test_embedded_dml_ir.py`.
- [x] **C1 (verified closed 2026-07-10): mid-body scalar `DECLARE @x t =
      expr`** — hoisted recursively (nested blocks included) with the
      initializer left in place as an assignment; covered by
      `_split_declarations`' pull_nested pass.
- [x] **B1 (fixed 2026-07-09): `PRIMARY KEY CLUSTERED (col ASC)`** — the
      `ADD CONSTRAINT … PRIMARY KEY/UNIQUE CLUSTERED (…) WITH (…) ON [grp]`
      shape is rebuilt directly per target (`_tsql_add_key_constraint`);
      sqlglot mangled it into comma-joined actions that SHIPPED inside
      Oracle guards. Tests: B1 pair in `test_ddl_rename_dropindex.py`.
- [x] **B2 (fixed 2026-07-09): `DROP INDEX` untranslated across the matrix** (PG
      3-part name, MySQL missing `ON tbl`, table name dropped from the `ON`
      form). `DropStatement` now carries `on_table` (from T-SQL's `ON tbl` or
      the legacy `tbl.ix` qualifier); T-SQL/MySQL emit `… ON tbl` (MySQL
      without `IF EXISTS`, which it lacks), Oracle/PG emit the bare index
      name, and a required-but-unknown table degrades to a documented
      carrier. Tests: `tests/integration/test_ddl_rename_dropindex.py`.
- [x] **C5 (fixed in M4 bring-up, 2026-07-09): MySQL `CALL` emitted with named
      arguments** (`name => v`), unsupported by MySQL — now lowered to
      positional by the MySQL transformer with a warning (argument order must
      match the declaration). Same change wave: the lexer now emits `=>` as
      ONE token (it split into `= >`, breaking PG/Oracle output too), and the
      T-SQL emitter spells named association as `@name = value`. Tests:
      `test_exec_call_translation.py` (named-arg trio).
- [x] **D9 (fixed 2026-07-09): `create or replace⏎PROCEDURE` (split lines +
      `-- <codegen>` header comment) desyncs the procedural parser**,
      spilling declaration fragments as top-level batches. Two mechanisms:
      the splitter's PL/SQL-head regex was line-bound (now matches over a
      3-line window), and a top-level anonymous block's `DECLARE` was parsed
      as ONE declaration instead of a section up to `BEGIN` (now mirrors
      `_parse_plsql_body`). Measured: Oracle→PG syntax failures 268 → **39**
      (99.9% validity). Tests: `TestOracleSplitLineCreateHeader`,
      `test_declare_section_with_multiple_declarations`.
- [x] **P1 (fixed 2026-07-09): faithful T-SQL expansion of named-cursor FOR
      loops** — declarations emit the classic un-@ form and record their
      query; a loop over a named cursor drives it directly with one
      `@<var>_<col>` per resolvable select-list column, positional FETCH
      INTO, and `rec.col` → `@rec_col` body rewriting (documented scaffold
      only for unresolvable lists). Follow-ups landed the same day:
      `EXECUTE IMMEDIATE … INTO` captured per target (T-SQL `INSERT … EXEC`
      into a table variable) and `||` → `+` in T-SQL raw expressions.
      Final dump measurement: **T-SQL 99.6% / PG 99.9% / MySQL 99.6%**.
      Remaining T-SQL classes (127): TRY fragments in flattened blocks,
      subquery ORDER BY (error 1033), ~21 near-`)`.
- [x] **C2/C3/C4 (closed 2026-07-10, sweep-closing wave): MySQL routine
      bodies** — the whole class fell out of the semicolon-less boundary
      fixes plus per-target lowering: cursor options consumed on DECLARE
      CURSOR; OPEN/FETCH/CLOSE/DEALLOCATE parsed as cursor ops (were sqlglot
      `OPEN AS c` aliases); `@@FETCH_STATUS` loops per target (PG FOUND,
      Oracle `%FOUND`, MySQL done-flag + NOT FOUND handler); assignment-select
      stops at bare `ELSE`; IF conditions stop at statement verbs
      (ROLLBACK/COMMIT/DECLARE/…); MERGE actions chain after `THEN` and route
      through the IR (mysql upsert, Oracle `ON (…)`, non-canonical → warned
      carrier); CTE assignment-select → `WITH … SELECT INTO`; updatable-CTE
      DML → warned carrier (was silent CTE drop); parenthesized FROM join
      trees passthrough (were a silent whole-FROM loss); base64-XML idiom,
      ERROR_MESSAGE()/RAISERROR(@var), VARBINARY(MAX), table hints in raw
      conditions, DROP INDEX guard per target, nested table-variable GTT
      hoist, MySQL `NULL;`→`DO 0;`. **Measured 2026-07-10: test.sql AND
      test2.sql at 100.0% validity on all three targets.** Tests:
      `tests/integration/test_test2_residue_wave.py` (28) +
      `test_cursor_variable_binding.py` (6).
- [x] **D5/D6/D7 (fixed 2026-07-09): Oracle→T-SQL passthroughs** — D5:
      `RENAME COLUMN` → `EXEC sp_rename` (T-SQL only; PG/MySQL 8 native).
      D6: `INSERTING`/`DELETING`/`UPDATING['(col)']` → the T-SQL
      inserted/deleted EXISTS idiom / `UPDATE(col)`, and the row→statement
      trigger conversion recurses into `IF` bodies (a NEW/OLD condition
      folds into the inserted-rows subquery). D7: `TRUNC(date)` →
      `CAST(x AS DATE)` (T-SQL), `DATE_TRUNC('day',…)` (PG), `DATE(x)`
      (MySQL). Tests: `test_ddl_rename_dropindex.py`,
      `test_trigger_predicates_scheduler.py`.
- [x] **B3 (fixed 2026-07-09): named DEFAULT constraints** (T-SQL-only)
      dropped on every other target with a per-name note/warning.
- [x] **B4 (verified fixed 2026-07-09): bare `RETURN` eats the next line's
      comment** — no longer reproduces; pinned by
      `test_comment_after_bare_return_survives`.
- [x] **D10 (fixed 2026-07-09): `DBMS_SCHEDULER.CREATE_JOB` → raw `CALL` on
      PG** — Oracle built-in package calls (`DBMS_*`, `UTL_*`, …) now degrade
      to a documented carrier + warning + no-op off Oracle.
- [x] **E1 (harness): `_split_mysql_statements` splits on `;` inside string
      literals** — fixed via the shared `tests/helpers/sql_split.py` (see M0);
      all live splitting is now string/comment-aware, incl. MySQL backslash
      escapes and a BEGIN/END word-boundary fix.

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [x] **CI: fail when fewer engines than expected were exercised** (done
      2026-07-10) — a gating "all four engines reachable" step in
      `syntax-live` fails the job before the live suites run; the waits stay
      `continue-on-error` for readable logs but can no longer shrink the
      validation silently.
- [x] **Identity-mutation floor raised 0.33 → 0.40 → 0.45** (2026-07-11;
      measured 0.49 after the M4-closing and M3-prereq waves). Next
      ratchet as `test_cross_dialect.py` survivors harden.
- [ ] **Module growth** — *parser done 2026-07-10:* `procedural/parser` is
      now a package (_base 1.7k + _tsql 0.7k + _plsql 0.8k, explicit
      cross-family contract). Still to split: `procedural/transformer/
      base.py` (~3.5k) and `transpiler.py` (~2.2k). *Finding (2026-07-10):*
      the parser's name-based mixin cut does NOT transfer to the
      transformer — its shared/node-transform/expression-rewrite families
      cross-call heavily (an attempted split needed a dozen-plus stub
      contract and was reverted). **Seam DESIGNED 2026-07-11 (measured):**
      the expression-rewrite family is 24 methods / ~751 lines with 33
      node→expr call edges; its instance state is small (class-constant
      regex/maps + `_source`, `_in_trigger`, `_string_vars`,
      `_get_func_map`). Design: a composed **`ExpressionRewriter`**
      object (`transformer/_expr.py`), constructed per transform with a
      narrow `RewriteContext` protocol (`source`, `target`, `in_trigger`,
      `string_vars`, `date_vars`, `warn()`, `func_map()`, and ONE
      `target_fixups(sql)` hook through which the per-target transformer
      classes keep their overrides — `_fix_raw_sql_target`,
      `_map_oracle_builtins`, …). The 33 call edges rewire mechanically
      to `self._expr.X(...)`. Implement as one mechanical commit with the
      full suite as the net; per-target subclassing of the rewriter can
      come later. This also unblocks M3-prereq's final step (the rewriter
      object is what IR-first expressions will eventually replace).
- [x] **Docker digest pin + constraints file** (done 2026-07-10): both
      Dockerfiles pin `python:3.13-slim` by sha256 digest and the runtime
      install applies `constraints.txt` (full dependency closure) — image
      build verified locally. A5 (`X-Unique-Decoded-As`) and N7 (filename
      stem sanitize) shipped the same day.

## 3. Test-corpus expansion (P3)

- [ ] **Import the upstream PostgreSQL regression fixtures as a PG-source
      test corpus** (user request, 2026-07-10; **evaluation done 2026-07-10**,
      import pending). Findings: **PG yes, MySQL no.**
      - *PostgreSQL* (`src/test/regress/sql/`, 247 files / ~4.9 MB): plain
        `.sql`, license is the permissive PostgreSQL License (BSD-like —
        committable with the COPYRIGHT notice reproduced). Probe: today's
        pipeline transpiles `insert.sql` PG→T-SQL in 0.2 s with honest
        warnings and no crash. Noise is tractable: sparse psql
        meta-commands (`\d+`, `\set`, …) and `COPY … FROM stdin` data blocks
        need a line-oriented strip (same class as the SQL*Plus directive
        peel); engine-internal suites (stats_import, rowsecurity,
        privileges, GUC tests) should simply not be selected. Start set:
        the portable core — insert/update/delete/join/select*/aggregates/
        window/case/union/subselect/with/triggers/plpgsql.
      - *MySQL* (`mysql-test/`): **rejected** — GPLv2 (incompatible with
        committing into this MIT repo) and written in the mysqltest DSL
        (`--source`, `if` blocks, per-connection commands) interleaved with
        the SQL, so it would need a real parser, not a curation pass.
      - *Fetcher shipped 2026-07-11:* `scripts/fetch_pg_corpus.py` downloads
        the 15-file portable core at a pinned tag (default `REL_17_5`),
        strips psql meta-commands + COPY-stdin blocks, prepends the license
        header, writes to the gitignored `fixtures-corpus/pg/`
        (download-on-demand). Tests: `test_fetch_pg_corpus.py` (8).
      - **HONEST baseline 2026-07-11 at `9176813`** (source-validated
        corpus: `filter_valid_source.py` keeps only the 5,196 statements
        live PostgreSQL itself accepts — the regression suite deliberately
        contains invalid SQL — and the shared splitter no longer counts
        transactional `BEGIN;` as block depth, which had glued 78% of the
        corpus into one pseudo-statement): **pg→Oracle 87.5% (454),
        pg→MySQL 83.9% (579), pg→T-SQL 71.3% (1090)**. Classes: tsql —
        149x near-',', 111x near-'=', 59x near-AS, 59x FIRST_VALUE needs
        OVER(ORDER BY), 58x near-')'; the dominant gate samples read
        "Expected table name but got CROSS/ON/GROUP_BY" (likely ONE emit
        mechanism dropping a FROM table). oracle — 133x ORA-00922, 61x
        ORA-00936, 54x ORA-00900, 68x PLS-00103. mysql — 576x generic
        1064 (needs the near-token dump classification M4 used). Work the
        classes from the sweep dumps, M4-style. **Waves 1–3b (2026-07-11,
        official re-measure at `ed9fa7e`): pg→Oracle 90.4% (351, was 454),
        pg→T-SQL 74.5% (973, was 1090), pg→MySQL 83.7% (589)** — session
        GUC SETs/RESETs degrade to carriers, VALUES relations lower to
        UNION ALL row-SELECTs on all four engines (they converted to
        NOTHING — empty FROM), ranking/offset window functions gain
        T-SQL's required ORDER BY (SELECT NULL), and joined derived
        tables keep their alias. **Remaining mysql residue classified:**
        dominated by plpgsql FUNCTION bodies spilling fragments
        (34x `AS LANGUAGE;`, 18x `RETURN AS NEW`, per-function CREATE
        heads) — the pg-source PROCEDURAL bring-up, an M4-scale
        workstream; first step is honesty (a desynced plpgsql unit must
        degrade WHOLE, doc-04 rule 4), then the function→routine
        conversion classes. *Wave 4 (2026-07-15):* the 34x `AS LANGUAGE;`
        class was the glued dollar-quote close (`end$$ language plpgsql`,
        no space): the lexer let `$` continue identifiers (Oracle
        `V$SESSION`), so `end$$` lexed as ONE identifier and the tail
        leaked into the body. For a postgresql source `$` now ends the
        identifier (dollar-quotes win, matching PG's own lexing) —
        `lexer.py`, tests in `test_pg_source_wave1.py::
        TestGluedDollarQuoteClose`. **Measured at `145551f` (2026-07-15):
        pg→Oracle 90.7% (341, was 351), pg→MySQL 84.9% (539, was 589),
        pg→T-SQL 74.7% (967, was 973).** Operational note: the pg-source
        sweep pushes Oracle to ~2.2 GiB — above its 2 g compose cap
        (cgroup OOM-killed it mid-sweep, `oom=true`); before an Oracle
        sweep run `docker update --memory 3g --memory-swap 3g
        unique-oracle-1` (runtime-only override; the committed 2 g cap
        keeps the full four-engine stack bootable on the 8 GB host).
        *Wave 5 (2026-07-15):* the PG signature grammar landed in the
        procedural parser — a dedicated postgresql branch of
        `_parse_parameter` (`[argmode] [argname] argtype [DEFAULT v]`,
        mode-first, name optional): type-only params `(int, int)`,
        argmode-first `(out x int)`, `int default 0` no longer desync
        (they had swallowed the whole function into the parameter list
        with ZERO warnings); unnamed params get synthesized `p1…pn`
        names and `$n` positional references rewrite to parameter names
        at token level (the lexer now emits `$1` as ONE token for a PG
        source); `BatchSplitter._split_postgresql` was rebuilt as a
        char-scanner (dollar-quotes, multi-line `'…'`/`E'…'` strings,
        `"…"` idents, comments) so old-style single-quoted plpgsql
        bodies stay whole, and `_consume_pg_routine_header` re-lexes a
        string body in place so `as '…' language plpgsql` converts like
        its `$$` twin. Tests: `test_pg_source_wave1.py` (TestTypeOnly…,
        TestPositionalParamReference, TestSingleQuotedBody,
        TestPgArgmodeFirstParameters). **Measured at `9a7263d`
        (2026-07-15): pg→Oracle 92.4% (269, was 341), pg→MySQL 86.3%
        (474, was 539), pg→T-SQL 75.8% (905, was 967)** — from the
        honest baseline that is Oracle 454→269, MySQL 579→474, T-SQL
        1090→905. The `RETURN AS NEW/OLD/x` fragment classes are gone
        from the residue. Next classes (fresh dumps, first-code-line
        shapes): mysql — plpgsql body *content* now that units hold
        together (19x stricttest = STRICT/INTO semantics, 12x
        raise_test = RAISE USING/level forms, 15x foreach_test =
        FOREACH…IN ARRAY, 10x compos = composite-type returns), 8x
        `float8 '…'` type-prefixed literals, 9x ARRAY_AGG; tsql — 60x
        `SELECT dbo.…` (qualified scalar-function calls in plain
        SELECTs, likely ONE emit shape), 30x `CREATE TABLE #…` temp
        tables, 18x trigger DDL, 17x partitioned CREATE TABLE.
        *Wave 6 (2026-07-15):* statistical/boolean aggregates + float8
        casts, in BOTH pipelines' shared paths. sqlglot canonicalizes
        `var_pop`→VARIANCE_POP (no engine accepts it; T-SQL dbo.-
        qualified it as a UDF → error 195) and mislabels MySQL's
        POPULATION-semantics VARIANCE/STDDEV with the sample-semantics
        canonical names. Landed: `_STAT_AGGREGATE_MAP` (canonical→per-
        target: VARP/VAR/STDEVP/STDEV on T-SQL, explicit `*_SAMP` on
        MySQL) + source-side `_SOURCE_STAT_NORMALIZATION` reading the
        new `SOURCE_DIALECT` ContextVar (mysql VARIANCE→VARIANCE_POP,
        tsql VARP/VAR/STDEVP canonicalized — covers aliased/nested
        args through the whole recursion); bool_or/bool_and/every →
        MAX/MIN (CAST(… AS INT) on T-SQL, CASE on Oracle); CAST DOUBLE
        → FLOAT (T-SQL) / BINARY_DOUBLE (Oracle) in `_CAST_TYPE_MAP`
        (55x `AS DOUBLE` in the tsql residue). Round-trip tests incl.
        the MySQL population-semantics preservation. Tests:
        `test_pg_source_wave1.py` (13 new). **Measured at `493565b`
        (2026-07-15): pg→T-SQL 77.0% (859, was 905), pg→MySQL 86.5%
        (468, was 474), pg→Oracle 92.4% (269 syntax unchanged — its
        aggregate wins show as ok 1698→1731, since ORA-00904 unknown
        function classifies as "other", not syntax).** Cumulative from
        the honest baseline: T-SQL 1090→859, MySQL 579→468, Oracle
        454→269.
        *Wave 7 (2026-07-15):* PG table-binding honesty. `INHERITS (…)`
        and `PARTITION OF … FOR VALUES …` were dropped SILENTLY by the
        IR conversion (a partition child shipped as a bare column-less
        `CREATE TABLE` — 30x `CREATE TABLE #…` in the tsql residue, 0
        warnings). Now modeled on `CreateTableStatement`
        (`inherits_clause`/`partition_of_clause`), the PG target renders
        them, and `SyntaxNormalizer._degrade_pg_table_binding` degrades
        the WHOLE statement to a carrier + warning + unsupported entry
        everywhere else. `DEFERRABLE`/`INITIALLY …` constraint
        attributes strip with a warning on T-SQL/MySQL via sqlglot-AST
        surgery on the constraint fragment (a column literally named
        "deferrable" is untouched); Oracle keeps them. Tests:
        `test_pg_source_wave1.py` (11 new). Left open: the partition
        PARENT (`PARTITION BY RANGE …`, 17x mcrparted) and column-LEVEL
        constraint attributes. **Measured at `3a54e36` (2026-07-15):
        pg→T-SQL 80.5% — syntax failures 859→696 (−163, the biggest
        single-wave drop); pg→MySQL 467 (−1); pg→Oracle 269 (flat).
        Denominators shrank (tsql 3732→3569 stmts) because the degraded
        INHERITS/PARTITION tables are now comment-only carriers — the
        honest ratchet is the absolute syntax count, not the %.**
        Cumulative from the honest baseline: T-SQL 1090→696, MySQL
        579→467, Oracle 454→269.
        *Wave 8 (2026-07-15):* PG routine-header attributes (STRICT,
        PARALLEL SAFE/UNSAFE/RESTRICTED, COST n, ROWS n, LEAKPROOF,
        WINDOW, SUPPORT fn, CALLED/RETURNS NULL ON NULL INPUT) were not
        consumed by `_consume_pg_routine_header` and spilled into the
        routine body as garbage declarations (`STRICT LANGUAGE;
        plpgsql AS; $ $;` inside the Oracle IS-section — 24x+
        PLS-00103 'AS', and the whole stricttest class on MySQL/T-SQL).
        Consumed now, both before AND after the `$$` body. Tests:
        `test_pg_source_wave1.py::TestPgRoutineHeaderAttributes`.
        **Measured at `e30a7e9` (2026-07-15): T-SQL 696→693, MySQL
        467→464, Oracle 269→266 (−3 each).** Honest read: the garbage
        declarations are gone (error-group composition changed) but the
        affected plpgsql functions still fail on their NEXT body
        blocker — RAISE forms, FOREACH, STRICT INTO — so the syntax
        counts barely move until those body features land. The
        remaining function classes are blocker CHAINS, not single
        shapes.
        *Wave 9 (2026-07-15):* `JOIN … USING (c)` → ON for T-SQL across
        the whole join CHAIN (27x+ errors 102/321): `_emit_join` now
        shares a per-SELECT `merged_cols` map tracking the chain's
        merged-column expression (LEFT/INNER keep the left carrier,
        RIGHT replaces it, FULL merges via COALESCE — PG's USING
        semantics), and derived-table left sides supply their alias.
        Left open: the parenthesized-join FROM item (`(j1 JOIN j2 USING
        (i)) AS x`, ~7x) flows outside the IR SELECT model and keeps
        USING; `SELECT *` projection still duplicates the join column
        (USING merges it in PG) — same caveat as the pre-existing
        single-join rewrite. Tests:
        `test_pg_source_wave1.py::TestJoinUsingOnTsql`. **Measured at
        `ca03ff9` (2026-07-15): T-SQL 693→687 (−6); MySQL 464 and
        Oracle 266 flat (USING is native there).** Less than the 27x
        class size: the paren-join FROM shape (~7x) stayed open and
        12x of the `SELECT *` group are bare-boolean WHERE clauses
        (error 4145, needs type knowledge). **Cumulative from the
        honest baseline: T-SQL 1090→687, MySQL 579→464, Oracle
        454→266.** The residue is now dominated by the plpgsql body
        bring-up chains (RAISE forms ~12x/direction, FOREACH 15x,
        STRICT INTO 19x, composite returns 10x) — the M4-scale
        workstream; single-shape DML waves are close to exhausted.
        *Wave 10 (2026-07-15):* plpgsql `RAISE level 'fmt %', args
        [USING …]` formatting — the first body-chain blocker. The raw
        argument tuple was pasted into single-argument carriers on
        every target (`PUT_LINE('x', a)` PLS-00306, `PRINT 'x', @a`
        error 102, bare `SELECT 'x', a` in MySQL functions), and the
        USING warning mislabeled plpgsql options as RAISERROR args.
        The parser now interleaves `%` placeholders (incl. `%%`) into
        ONE `||` concatenation in source spelling — the operator
        machinery maps it per target (CONCAT on MySQL, `+` on T-SQL,
        `||` on Oracle) — and folds USING options into the message
        with a truthful warning; MySQL SIGNAL hoists non-literal
        messages through `@uq_errmsg` (MESSAGE_TEXT accepts only
        literals/variables). Tests: TestPlpgsqlRaiseFormat (7). Left
        open: notices inside MySQL FUNCTIONs still emit a bare SELECT
        (invalid there — needs routine-kind context in the emitter);
        T-SQL `+` on non-string args is a runtime cast risk (M3
        string-typing). **Measured at `a1360c9` (2026-07-15): T-SQL
        687→677 (−10), Oracle 266→262 (−4), MySQL 464 flat — exactly
        the predicted chain effect: MySQL's RAISE functions stay
        blocked on the notice-in-FUNCTION SELECT. Cumulative: T-SQL
        1090→677, MySQL 579→464, Oracle 454→262.**
        *Wave 11 (2026-07-15):* that notice channel — a bare `SELECT
        <msg>` is invalid inside a MySQL FUNCTION (error 1415); the
        base `_emit_print` now diverts to `SET @uq_notice = …` with a
        documented carrier when `_in_mysql_function` (procedures keep
        the visible SELECT). Tests: TestMysqlFunctionNotice.
        **Measured at `6adf580` (2026-07-15): MySQL syntax 464 flat but
        ok 1741→1757 (+16) with expected-missing −16 — the fixed
        functions now create AND run, resolving their dependent calls.
        T-SQL 677 / Oracle 262 unchanged.**
        *Wave 12 (2026-07-15):* `RETURNS void` (62x in the corpus — the
        most common plpgsql test-function type) emitted verbatim and is
        invalid on every target. Mapped to the neutral scalar (INT on
        MySQL/T-SQL, NUMBER on Oracle) with a guaranteed trailing
        RETURN and bare `RETURN;` statements gaining the neutral value
        (nested included, via an `_in_void_function` flag). `DECLARE x
        record` (row shape unknown until runtime, no equivalent
        anywhere) now degrades the routine WHOLE to a carrier +
        warning; the procedural emitter's carrier contract generalized
        beyond the parse-fallback reason string. Tests:
        TestReturnsVoid, TestRecordDeclarationDegrades. **Measured at
        `640788e` (2026-07-15): MySQL 464→417 (−47), T-SQL 677→643
        (−34), Oracle 262→237 (−25) — the biggest chain-wave gain.
        Cumulative from the honest baseline: T-SQL 1090→643, MySQL
        579→417, Oracle 454→237.**
        *Wave 13 (2026-07-15):* `LANGUAGE sql` bodies (bare statement
        list, no BEGIN/DECLARE) were shredded by the declare-section
        parser into garbage declarations (`DECLARE select LONGTEXT;
        DECLARE $ $;`) — they now parse as statements and a non-void
        function's trailing SELECT/VALUES becomes its RETURN
        (`_parse_pg_sql_function_body`). PG pseudo-types (`record` in
        params/returns, the `anyelement`/`anyarray` polymorphic
        family) generalize the wave-12 record degrade: the routine
        degrades WHOLE with a warning naming the culprit. Tests:
        TestLanguageSqlBody, TestPolymorphicPseudoTypes. **Measured at
        `2792430` (2026-07-15): MySQL 417→389 (−28), T-SQL 643→615
        (−28), Oracle 237→215 (−22). Cumulative from the honest
        baseline: T-SQL 1090→615 (82.4%), MySQL 579→389 (88.0%),
        Oracle 454→215 (93.5%).**
        *Wave 14 (2026-07-15):* plpgsql's bare-``=`` assignment
        (synonym of ``:=``, unambiguous at statement start) parses as
        an assignment for a PG source — it shipped raw (PLS-00103,
        8x+ direct plus chain blockers); and ``RETURNS setof <t>``
        parses as ONE type unit (the inner name had leaked into the
        header as garbage) and degrades the routine WHOLE (RETURN
        NEXT protocol has no equivalent). Tests:
        TestPlpgsqlEqualsAssignment, TestSetofReturnsDegrade.
        **Measured at `7a1a1e2` (2026-07-15): MySQL 389→363 (−26),
        T-SQL 615→590 (−25), Oracle 215→202 (−13). Cumulative from the
        honest baseline: T-SQL 1090→590 (83.1%), MySQL 579→363
        (88.7%), Oracle 454→202 (93.9%).**
        *Wave 15 (2026-07-15):* PG `CREATE INDEX` → T-SQL rebuilt from
        the parsed tree (`_pg_index_to_tsql`): PG's nameless form gets
        a synthesized `<table>_<cols>_idx` name (T-SQL requires one),
        sqlglot's write-side CASE-WHEN NULLs emulation never reaches
        the column list, a filtered index's `NOT x IS NULL` spells
        `x IS NOT NULL` (the only form CREATE INDEX…WHERE accepts),
        unique indexes without a filter carry the NULLs-distinct
        semantics note, and the physical-clause round-trip carrier
        (CLUSTERED/WITH/ON fg) is re-injected — the cross-dialect
        round-trip suite caught the rebuild dropping it. Tests:
        TestPgIndexToTsql. **Measured at `8528178` (2026-07-15):
        T-SQL 590→582 (−8, ok +8); MySQL/Oracle flat (tsql-only wave).
        Cumulative from the honest baseline: T-SQL 1090→582 (83.3%),
        MySQL 579→363 (88.7%), Oracle 454→202 (93.9%).**
        *Wave 16 (2026-07-15):* boolean-literal conditions on T-SQL —
        PG's ``JOIN b ON true`` / ``WHERE false`` mapped via TRUE→1 to
        ``ON 1`` (error 4145, 12x): `_emit_condition` renders a bare
        boolean literal in WHERE/HAVING/ON position as a real
        predicate (`1 = 1` / `1 = 0`). Tests:
        TestBooleanLiteralConditionsTsql. Sweep re-measure pending.
        Known gaps left open (P2): **MySQL FUNCTION emitter drops
        OUT/INOUT modes silently** for every source (MySQL functions
        can't declare them — needs a warning per no-silent-loss);
        **VARIADIC** parameters still desync (no consume, no carrier);
        array subscripts (`p1[1]`) degrade honestly via the output gate. Getting here surfaced and
        fixed THREE product bugs: the sqlglot COPY DoS (`:'var'`,
        `3aa55b4`), the transactional-BEGIN splitter glue (also under the
        output gate), and the oracle first-boot healthcheck wait.

## 4. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

- **Test-assertion quality** is measured by the nightly mutation job
  (`mutation.yml` / `scripts/mutation_test.py`) rather than a static to-do list:
  surviving mutants in its run summary are the live map of weakest assertions.
  Strengthen them opportunistically (the biggest foci at last measure were
  `emit._emit_function`/`_emit_date_diff` and `transformer._replace_oracle_date_add`).
  Differential result testing (`test_corpus_results_live.py`) guards against
  semantic regressions on every syntax-live CI run.

---

## Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally emitted as
comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, …).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as a carrier type with the
  original preserved in a `/* UNIQUE: … */` comment, plus a warning). The
  round-trip **restores the original** on a transpilation back to a supporting
  engine — verified for `%TYPE` via the procedural path and for physical index
  clauses via the DML path (`%TYPE` is PL/SQL-only, so it never appears in a
  DML/DDL statement).
