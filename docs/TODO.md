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
      share the boundary-counting forms).* Remaining increments: *(3) DONE 2026-07-17 (wave 96):
      LastIdentityCapture node landed — producer in both assignment
      transforms (oracle target, value is only the last-identity
      call), pairing pass consumes the node, marker constant deleted;
      the UNPAIRED fallback improves from the invalid `v := /* … */;`
      to a valid NULL assignment + note. Full gate green on first
      try; pg-corpus verification cycle at `b073133` identical
      {163/131/89} — no regression. Tests:
      TestLastIdentityCaptureNode.* Original analysis
      (2026-07-17): the marker is the TAIL of the Oracle comment
      `LAST_IDENTITY_EXPR["oracle"]` produced by
      `_transform_last_identity`'s text substitution;
      `_identity_assignment_var` then substring-matches it
      (`base.py:390`). Design: when the assignment transform detects a
      LAST_IDENTITY_SOURCE_FUNCS call with target oracle, return a
      dedicated `LastIdentityCapture(target_var)` node; the pairing
      pass (`base.py:345`) consumes the node; the emitter renders the
      documented comment for any UNPAIRED capture (fallback). Keep the
      non-assignment usages (`SELECT @@IDENTITY` in expressions) on
      the comment path. This is a fresh-session-sized refactor — the
      naive attempt broke 18 tests.*; (4) dual-guard→IF and
      DECLARE-init hoisting consume nodes — *4a landed 2026-07-17
      (wave 97): Oracle's assignment-via-SELECT-INTO decision now
      inspects the value NODE first (`_needs_sql_context`: subquery or
      CAST anywhere in the tree; RawSQL fragments keep the spelling
      regex). Tests: TestAssignmentViaSelectNodeAware; verification
      cycle at `129cc6b` identical {163/131/89}. Remaining 4b —
      *analysis 2026-07-17: the DECLARE-init half is DONE BY
      CONSTRUCTION after 4a (the hoisting already builds an
      AssignmentStatement from the initializer NODE, which then takes
      the node-aware SELECT-INTO path — verified live); the
      batch-level T-SQL guard recognizer (`_TSQL_GUARD_HEAD_RE`) is
      PRE-PARSE BY DESIGN (audited M2/P3 single-recognizer decision,
      runs on batch text before any parsing — unaffected by
      IR-emitting scalar expressions). The M3b probe RAN 2026-07-17
      (uncommitted IR-first in `_transform_raw_sql`, full suite):
      **126 failures** — the text path has GROWN as the expression
      engine since the original 18. Category map (top offenders):
      curated DATEADD/DATEDIFF/TRUNC/TO_DATE handlers (16+),
      function-name mapping & oracle-builtin renames (7+),
      FOUND/fetch-status cursor idioms (7), string-concat/plus
      classification (6+), error-global conditions & RAISERROR hoists
      (8+), comments inside expressions (IR drops them, 6+),
      SUBSTRING/position arg orders (4). Conclusion: wholesale
      IR-first is NOT the path — each consumer family must migrate
      individually (the increments-1..4a pattern), OR the IR
      expression pipeline must absorb those behaviors first. The
      probe patch is reproducible: guard `UNIQUE_IR_FIRST` in
      `_transform_raw_sql` wrapping `_ir_transpile_dml` for scalar
      fragments. Family migration step 1 (dates) landed 2026-07-17
      (wave 98): the differential found a live IR bug — DATEADD over
      a DATEDIFF base added an INTERVAL to a NUMBER (invalid Oracle /
      wrongly typed PG); the IR now matches the text path's numeric
      addition. Tests: TestIrNestedDateaddOverDatediff; verification cycle at
      `6be5038` identical {163/131/89}. Family step 2 (function
      renames) landed 2026-07-17 (wave 99): the differential found the
      procedural text path had NO (mysql, postgresql)/(mysql, oracle)
      function maps — IFNULL shipped raw to PG; both maps added
      (IFNULL/RAND/CURDATE/UUID + the symmetry round-trips the
      mapping-contract test enforces). Known cosmetic divergences left
      documented: NVL→ISNULL (text) vs COALESCE (IR) on tsql — both
      valid; sqlglot's LEN→LENGTH(CAST AS CLOB) vs text's plain
      LENGTH — both count trailing spaces that T-SQL LEN ignores
      (shared caveat, not a divergence). Tests:
      TestMysqlProceduralFuncMaps; mysql-corpus cycle at `e933b82`
      stable {166/107/129} (fidelity inside already-counted
      routines). Family step 3 (concat classification) landed
      2026-07-17 (wave 100): T-SQL `N'…'` literals parse as
      exp.National, which `_looks_like_string` did not recognize —
      `N'pre' + s` shipped raw `+` to Oracle (invalid on strings).
      The nested-CONCAT shape on mysql (`CONCAT(CONCAT(a,b),'c')` vs
      flat) is cosmetic, documented not chased. Tests:
      TestNationalStringConcat.*; then the text rewriters can
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

- [x] **Import the upstream PostgreSQL regression fixtures as a PG-source
      test corpus — DONE** (fetcher shipped 2026-07-11; the corpus is the
      daily driver of the §3 wave loop, standing pg→{tsql 163, mysql 131,
      oracle 89}). Original (user request, 2026-07-10; evaluation done
      2026-07-10): Findings: **PG yes, MySQL no.**
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
        TestBooleanLiteralConditionsTsql. **Measured at `7fa6c60`
        (2026-07-15): T-SQL 582→573 (−9); MySQL 363 / Oracle 202 flat.
        Session cumulative from the honest baseline: T-SQL 1090→573
        (83.5%), MySQL 579→363 (88.7%), Oracle 454→202 (93.9%).**
        Next classes (fresh dumps at `7fa6c60`): tsql — 23x `SELECT
        dbo.…` array-construct calls (`dbo.ARRAY`, `ARRAY_AGG`,
        `dbo.EXPLODE`: no arrays on T-SQL/MySQL → honest whole-
        statement carriers + unsupported entries), 18x triggers with
        transition tables (`EXECUTE FUNCTION` bindings), 13x remaining
        index shapes (expression indexes fall back to the generic
        path), 12x `CREATE OR ALTER VIEW` with aggregate ORDER BY
        args; mysql — 15x FOREACH…IN ARRAY (array emulation needed or
        honest degrade), 12x `f1()` polymorphic call sites, 8x
        `float8 'nan'` special values (`'nan'`/`'inf'` literals have
        no MySQL FLOAT spelling).
        *Wave 17 (2026-07-15):* array-construct honesty — statements
        using `ARRAY[…]`/`array_agg`/`unnest` shipped as fake calls
        (`dbo.ARRAY(1,2)`, unqualified `ARRAY_AGG(x)` — guaranteed
        engine errors) with ZERO warnings on T-SQL/MySQL. A statement-
        level gate in `Transformer.transform` degrades them WHOLE to a
        carrier + warning + unsupported entry (PG/Oracle keep their
        paths). Tests: TestArrayConstructsDegrade. **Measured at
        `0223762` (2026-07-15): MySQL 363→321 (−42), T-SQL 573→550
        (−23), Oracle 202 flat (kept its path). Session cumulative
        from the honest baseline: T-SQL 1090→550 (84.0%), MySQL
        579→321 (89.9%), Oracle 454→202 (93.9%).**
        *Wave 18 (2026-07-15):* dollar-quoted STRINGS in the PG lexer —
        the class fix behind the wave-4/5 patches (rule of three). A
        dollar-quoted literal NESTED in a body (`EXECUTE $q$…$q$`, the
        18x transition-table trigger class) shredded into `$ q $`
        token soup; the lexer now tokenizes `$$…$$`/`$tag$…$tag$` as
        ONE STRING normalized to single-quote form (the Oracle q'…'
        precedent), which routes outer bodies AND nested literals
        through the same wave-5 splice path. All prior dollar-quote
        tests keep passing. Tests: TestNestedDollarQuotedLiterals.
        **Measured at `4a09dc2` (2026-07-15): slightly NEGATIVE —
        T-SQL 550→551, MySQL 321→323, Oracle 202→204 (+5 total).
        Honest read: units that used to desync into whole carriers now
        parse and emit near-correct SQL that trips the NEXT chain
        blocker (e.g. `DECLARE CURSOR FOR EXECUTE` on T-SQL — dynamic
        FOR loops still need a target-side story). The class fix
        stands: one canonical dollar-quote path, all prior tests
        green, and the trigger/EXECUTE chains are now parseable for
        the next wave.**
        *Wave 19 (2026-07-15):* PG catalog internals — `CAST(x AS
        regclass)` (and the whole `reg*` OID-type family) plus system
        columns (`tableoid`, `ctid`, `xmin`…) shipped raw with zero
        warnings (22x ORA-00936). The wave-17 statement gate
        generalizes: `_gate_pg_internals` degrades such statements
        WHOLE on every non-PG target. Tests:
        TestPgCatalogInternalsDegrade. **Measured at `0e35ddd`
        (2026-07-15): Oracle 204→182 (94.4% — the whole regclass
        class), T-SQL 551→549, MySQL 323 flat. Cumulative: T-SQL
        1090→549, MySQL 579→323, Oracle 454→182.**
        *Wave 20 (2026-07-15):* ordered-set aggregates and ARRAY casts
        join the statement gate — `RANK(x) WITHIN GROUP (ORDER BY …)`
        reaches the IR as an unhandled-WithinGroup RawSQL and shipped
        verbatim (9x 1064 on MySQL, plus the T-SQL twin, 0 warnings);
        `CAST(x AS ARRAY)` (the aggregate-transition-function class,
        8x) was invisible to the wave-17 array finder. Both degrade
        WHOLE on T-SQL/MySQL; Oracle keeps WITHIN GROUP (native).
        Tests: TestOrderedSetAggregatesDegrade. **Measured at
        `4bcc1d9` (2026-07-15): MySQL 323→285 (−38, 90.9%), T-SQL
        549→519 (−30, 84.5%), Oracle 182 flat (native WITHIN GROUP).
        Cumulative: T-SQL 1090→519, MySQL 579→285, Oracle 454→182.**
        *Wave 21 (2026-07-15):* FULL OUTER JOIN on MySQL — no spelling
        exists there and it shipped raw (1064, the bulk of the
        remaining `SELECT *` class). Statement-level degrade with a
        warning naming the manual rewrite (LEFT JOIN UNION ALL right
        anti-join); T-SQL/Oracle/PG keep their native FULL JOIN.
        Classified for later: the raise_test residue is now SQLSTATE/
        SQLERRM pseudo-variables inside converted EXIT HANDLERs.
        Tests: TestMysqlFullOuterJoinDegrades. **Measured at `cdb86a0`
        (2026-07-15): MySQL 285→266 (−19, 91.5%); T-SQL 519 / Oracle
        182 flat. Cumulative: T-SQL 1090→519, MySQL 579→266, Oracle
        454→182.**
        *Wave 22 (2026-07-15):* custom-aggregate CALL syntax — `fn(*)`
        on a non-COUNT function and `fn(DISTINCT … ORDER BY …)` (an
        unhandled-Order RawSQL argument) have no T-SQL/MySQL spelling
        (UDFs cannot be aggregates); the statement gate degrades them
        WHOLE (errors 102/156, the remaining `SELECT dbo.…` class).
        Tests: TestUserAggregateCallsDegrade. **Measured at `7e7dee2`
        (2026-07-15): T-SQL 519→499 (−20, 85.0% — under 500), MySQL
        266→247 (−19, 92.0%), Oracle 182 flat. Cumulative: T-SQL
        1090→499, MySQL 579→247, Oracle 454→182.**
        *Wave 23 (2026-07-15):* Oracle leading-underscore identifiers
        quote (`_ident` + the derived-table/join alias sites that
        bypassed it — PG's suite aliases VALUES relations `_(x)`, 15x
        ORA-00911, and declares `_sqlstate` locals); plpgsql DECLARE
        defaults accept the bare `=` (wave 14 covered statements only
        — 6x PLS-00103 '='). Tests: TestOracleUnderscoreIdentifiers,
        TestPlpgsqlDeclareEqualsDefault. **Measured at `437a5c3`
        (2026-07-15): Oracle 182→170 (−12, 94.8%); MySQL 247 / T-SQL
        499 flat. Cumulative: T-SQL 1090→499, MySQL 579→247, Oracle
        454→170.**
        *Wave 24 (2026-07-15):* aggregate `FILTER (WHERE p)` — PG-only
        spelling with a FAITHFUL universal rewrite instead of a
        degrade: `agg(CASE WHEN p THEN x END)` (`COUNT(*)` counts 1),
        applied at IR conversion for every target (the `SELECT
        (SELECT` class, error 102). Tests: TestAggregateFilterRewrite.
        **Measured at `a71020f` (2026-07-15): MySQL 247→233 (92.5%),
        T-SQL 499→490 (85.3%), Oracle 170→168 — all three moved (a
        universal rewrite). Cumulative: T-SQL 1090→490, MySQL 579→233,
        Oracle 454→168.**
        *Wave 26 (2026-07-15):* `SET SESSION AUTHORIZATION` (kept as
        a "real SQL SET" in wave 1, but only PG has it — 6x MySQL + 6x
        Oracle) degrades with its own carrier in the SET-option path
        AND the passthrough; `DROP TYPE` on MySQL (no user-defined
        types in any form, 5x) mirrors the sequence carrier. Tests:
        TestSessionAuthorizationDegrades, TestMysqlUserTypesDegrade.
        **Measured at `9394e9c` (2026-07-15): Oracle 168→162 (95.0%),
        MySQL 233→222 (92.8%), T-SQL 477→471 (85.8%). Cumulative:
        T-SQL 1090→471, MySQL 579→222, Oracle 454→162.**
        *Wave 28 (2026-07-15):* the index rebuild generalizes to MySQL
        (`_pg_index_rebuild`): MySQL also requires an index name (4x
        nameless) and has NO filtered indexes at all — any WHERE drops
        with a broader-index note on plain indexes and degrades WHOLE
        on unique ones; opclass strip and name synthesis shared with
        the T-SQL path. Tests: TestPgIndexToMysql. **Measured at
        `4843e14` (2026-07-15): MySQL 219→210 (93.2%); T-SQL 467 /
        Oracle 162 flat. Cumulative: T-SQL 1090→467, MySQL 579→210,
        Oracle 454→162.**
        *Wave 29 (2026-07-15):* the raise_test residue — a bare
        re-``RAISE;`` inside a handler emitted ``SET MESSAGE_TEXT = ;``
        (empty: a syntax error AND a broken re-raise): the faithful
        spellings are MySQL ``RESIGNAL;`` and T-SQL ``THROW;`` (Oracle
        keeps ``RAISE;``). And the level-less ``RAISE 'msg' USING …``
        (defaults to EXCEPTION) now routes through the wave-10 format
        parser instead of shipping the USING tail raw with the old
        mislabeled warning. Tests: TestRaiseResidue. Sweep re-measure
        **Measured at `f156123` (2026-07-15): MySQL 210→206 (93.3%);
        T-SQL 467 / Oracle 162 flat. Cumulative: T-SQL 1090→467, MySQL
        579→206, Oracle 454→162.** Mutation validation #2: convert.py
        and procedural base.py both at/above floor; emit.py 57% (<60)
        — the remaining survivor work must run where nothing snapshots
        the tree (see the incident note below). **Incident 2026-07-15
        evening: `scripts/mutation_test.py` mutates sources IN PLACE;
        a background full-emit.py run was mid-mutant when wave 29's
        commit snapshotted the tree — 99e0ba4 pushed a mutated emit.py
        (CI caught it red); restored byte-for-byte in f156123, full
        gate + CI green. Rule: full mutation runs happen in CI, or
        locally only with gates/sweeps/commits quiesced.**
        *Wave 30 (2026-07-15):* the tsql raise_test twin —
        RAISERROR's is_direct heuristic was fooled by an expression
        payload STARTING with a quote (`'a' + 'b'` from the wave-10
        fold; error 102 near '+'): only a single literal/variable/
        msg-id goes inline now, expressions hoist through
        `@unique_errmsgN`. And the SQLERRM/SQLCODE→ERROR_* mapping
        widened to PG sources (plpgsql shares the names) plus
        SQLSTATE→CAST(ERROR_STATE() AS NVARCHAR(5)) with a
        domain-difference warning — all via `_map_outside_strings`
        (a literal 'SQLSTATE: ' label must never rewrite; the old
        plain re.sub was a latent string-corruption hazard on the
        Oracle path too). PERFORM mangling (`perform 1`→`perform;`)
        classified for the next wave. Also this block: the mysql-source
        private corpus filtered live — 10,352 statements kept, 39
        rejected (`filter_valid_source.py --dialect mysql`, throwaway
        database, DELIMITER-block aware). Tests:
        TestTsqlRaiserrorExpressionHoist. **Measured at `eed51dc`
        (2026-07-15): T-SQL 467→461 (86.1%); MySQL 206 / Oracle 162
        flat. Cumulative: T-SQL 1090→461, MySQL 579→206, Oracle
        454→162.**
        *Wave 31 (2026-07-15):* plpgsql ``PERFORM`` (evaluate and
        discard) reached sqlglot as raw text and mangled to
        ``perform;``. New `PerformStatement` IR node: MySQL emits
        ``DO expr;`` (exact semantics), T-SQL a throwaway inline
        ``DECLARE @uq_discardN SQL_VARIANT = (expr);``, Oracle a
        nested SELECT-INTO-discard block, PG keeps PERFORM; the
        FROM-tail form (multi-row discard) degrades with a warning in
        the transformer. Mutation floors: per user, measured by the
        NIGHTLY run only from now on (no local/dispatch runs). Tests:
        TestPerformDiscard. **Measured at `3b48991` (2026-07-15):
        MySQL 206→200 (93.5%), Oracle 162→159 (95.1%), T-SQL 461→455
        (86.3%) — all three moved. Cumulative: T-SQL 1090→455, MySQL
        579→200, Oracle 454→159.**
        **mysql-source baseline #1 (private local corpus, 2026-07-15,
        at `801ed0e`): mysql→PG 90.2% (648 syntax / 6,580 stmts),
        mysql→T-SQL 84.6% (988 / 6,422); mysql→Oracle failed mid-sweep
        on the long-TODO'd DPY-1001 session-kill — the sweep's Oracle
        runner now RECONNECTS and counts the killer statement as
        'other' (fixed in `scripts/validity_sweep.py`). **Complete
        baseline at `070c60f`: mysql→PG 90.2% (648/6,580), mysql→Oracle
        91.3% (555/6,412 — 1,604 'other' includes the session-killers,
        honestly counted), mysql→T-SQL 84.6% (988/6,422). The
        mysql-source direction now joins the wave cadence.**
        *Wave M1 (mysql-source, 2026-07-15):* the mirror of pg wave 1 —
        MySQL session knobs (`SET [@@]sql_mode`, `SET GLOBAL/SESSION/
        PERSIST`, bare `SET name =` system vars, and any SET whose
        value reads an `@@` variable — the save/restore pattern) plus
        admin commands (`FLUSH`, `LOCK/UNLOCK TABLES`, `ANALYZE/
        OPTIMIZE/REPAIR/CHECK/CHECKSUM TABLE` — sqlglot mis-parses
        FLUSH as an alias) degrade to documented carriers off MySQL,
        across all three routing paths (SET-option batch, passthrough,
        admin classified with the option statements — SQL*Plus
        precedent). Largest baseline classes: 68–124x per direction.
        Tests: TestMysqlSessionKnobsDegrade (13). **Measured at
        `351751c` (2026-07-15): mysql→T-SQL 988→756 (−232, 87.8%),
        mysql→PG 648→503 (−145, 92.1%), mysql→Oracle 555→323 (−232,
        94.8%).**
        *Wave M2 (mysql-source, 2026-07-15):* `CREATE TABLE t [AS]
        SELECT …` silently LOST its query on every source — the
        converter never read sqlglot's `expression` slot (0 warnings,
        worst class; MySQL's no-AS spelling was the 161x `CREATE
        TABLE` block in →PG). Also: MySQL `DOUBLE(11,0)` display
        widths drop for PG's parameterless `DOUBLE PRECISION`, and
        leading-`$` identifiers (legal in MySQL) quote on PG. Tests:
        TestMysqlCtasAndTypes. **Measured at `6f70e9c` (2026-07-15):
        mysql→PG 503→403 (−100, 93.7% — the CTAS class); mysql→Oracle
        323 syntax flat with ok +20 / expected-missing +63 (CTAS
        tables now exist, dependencies resolve); mysql→T-SQL 756→755.**
        *Wave M3 (mysql-source, 2026-07-15):* comment-only nested
        `BEGIN … END` blocks (MySQL scope idiom) are a syntax error on
        targets requiring at least one statement: the block emitter
        gains an `_empty_block_filler` hook — `SET NOCOUNT ON;` on
        T-SQL (the BEGIN TRY precedent), `NULL;` on Oracle/PG, none on
        MySQL where the empty block is legal. Tests:
        TestTsqlEmptyBeginBlock. **Measured at `dc8a027`
        (2026-07-15): mysql→T-SQL 755→754 (−1); PG/Oracle flat —
        honest small yield, the class was thinner than sampled and
        those routines carry further chain blockers. The mysql-source
        residue is now the long tail: PREPARE/EXECUTE dynamic SQL and
        the bug* procedural chains (→T-SQL 754, →PG 403, →Oracle
        323).**
        *Wave M4 (mysql-source, 2026-07-15):* T-SQL CTAS — no `CREATE
        TABLE AS` exists there; the faithful idiom `SELECT … INTO
        <#table> FROM …` now renders (an `into=` hook in
        `_emit_select`, 133x — the class wave M2's CTAS rescue made
        visible); and views over temporary tables (T-SQL 4508, 91x)
        degrade whole via a transformer gate driven by the TEMP_TABLES
        harvest. Left classified: `CREATE TABLE t LIKE t1` clones
        (26x) drop their LIKE — next wave. Tests:
        TestTsqlCtasBecomesSelectInto. **Measured at `051cc8d`
        (2026-07-15): mysql→T-SQL 754→572 (−182, 90.6% — the biggest
        mysql-source wave; ok +94). All three mysql-source directions
        now above 90%: →T-SQL 572 (90.6%), →PG 403 (93.7%), →Oracle
        323 (94.8%).**
        *Wave M5 (mysql-source, 2026-07-15):* `CREATE TABLE t2 LIKE
        t1` structure clones silently dropped their LIKE everywhere
        (bare CREATE, 0 warnings, 26x): now `like_source` on the IR —
        PG native `(LIKE t1 INCLUDING ALL)`, T-SQL `SELECT * INTO …
        WHERE 1 = 0`, Oracle empty CTAS, both with the
        indexes-not-cloned note; MySQL keeps its native form. Tests:
        TestCreateTableLikeClone. **Measured at `5eb75bf`
        (2026-07-15): mysql→T-SQL 572→566 (90.7%), mysql→PG 403→397
        (93.7%), mysql→Oracle 323 flat (LIKE tables now exist —
        expected-missing +6). mysql-source day-one cumulative: →T-SQL
        988→566 (−43%), →PG 648→397 (−39%), →Oracle 555→323 (−42%).
        Next tranche (heavy): the bug*/proc_* procedural chains
        (64-86x per direction — multi-blocker plpgsql-style bring-up
        for mysql routine bodies), and the dynamic PREPARE/EXECUTE
        trio's faithful mysql→PG conversion (native there; currently
        honest carriers).**
        *Wave M6 (mysql-source, 2026-07-15):* table-qualified INSERT
        column lists (`INSERT INTO t (t.a, t.b) …`, legal MySQL) —
        sqlglot cannot parse them and lenient paths truncated to
        `INSERT INTO t (t)` with the body GONE (the 2026-07-09 audit
        class, still alive in embedded routine bodies; the bug8849
        family). A retry-after-failure pre-parse normalization (the
        Oracle SYSDATE() pattern) drops the redundant qualifier inside
        the identifier-only list region. Tests:
        TestInsertQualifiedColumns. **Measured at `3e2f165`
        (2026-07-15): →PG 397→396, →T-SQL 566→565, →Oracle flat —
        honest small yield; the bug* routines carry further chain
        blockers. Day-one mysql-source close: →T-SQL 988→565 (90.7%),
        →PG 648→396 (93.8%), →Oracle 555→323 (94.8%). The residue on
        all six directions is now long-tail multi-blocker chains
        (M4-scale deep dives, diminishing per-wave yields).**
        *Wave 32 (2026-07-15, deep chains):* parameterized cursors —
        PG's name-first `c1 CURSOR (p1 int) FOR …` shredded the whole
        declare section and `OPEN c1(5)` dropped its argument as a
        stray statement. Parsed properly now (name-first path +
        `CursorOperation.args`); Oracle renders its native
        `CURSOR c1(p1 t) IS …`, PG keeps `c1 CURSOR (p1 int) FOR …`;
        T-SQL/MySQL (no parameterized cursors) degrade the routine
        whole. The analysis-before-change pass caught a LATENT silent
        loss on the way: `_transform_cursor_decl` rebuilt the node
        without its `parameters` field — fixed. Tests:
        TestParameterizedCursors. **Measured at `18aee57`
        (2026-07-15): T-SQL 455→418 (−37, 87.3% — the shredded-declare
        routines), Oracle 159→155 (95.2%), MySQL 200→198. Cumulative:
        T-SQL 1090→418, MySQL 579→198, Oracle 454→155.**
        *Wave 33 (2026-07-15, deep chains):* leading-underscore locals
        (`_sqlstate text` — the stacked_diagnostics family) are illegal
        unquoted in PL/SQL; they RENAME to `uq_*` through the existing
        `_var_map` rewrite (declare + assignments + raw-text references
        consistent, string literals untouched; quoting could not reach
        the raw references). The `_var_map` outside-strings application
        now also runs for the Oracle target. Remaining in that family:
        `GET STACKED DIAGNOSTICS` itself (mysql native; oracle→SQLERRM/
        FORMAT_ERROR_BACKTRACE; tsql→ERROR_*()) — classified for the
        next deep wave. Tests: TestOracleUnderscoreLocals. Sweep
        re-measure done: **flat at `22f63f4` — necessary but not
        sufficient (the family's next blocker is GET STACKED
        DIAGNOSTICS itself; wave-8 pattern, honestly recorded).**
        *Wave 34 (2026-07-15, deep chains):* `GET [STACKED] DIAGNOSTICS
        v = ITEM, …` (15x, mangled to `get AS stacked;`) — new IR node;
        Oracle/T-SQL convert to plain assignments through the EXISTING
        emitters (ROW_COUNT→SQL%ROWCOUNT/@@ROWCOUNT, MESSAGE_TEXT→
        SQLERRM/ERROR_MESSAGE(), PG_CONTEXT→FORMAT_ERROR_BACKTRACE/
        ERROR_PROCEDURE+LINE; RETURNED_SQLSTATE maps with a
        domain-difference warning); MySQL keeps ROW_COUNT() and the
        native CONDITION-1 form for condition items; PG verbatim.
        Unmappable items (pg_routine_oid) degrade per-item with a
        warning. Tests: TestGetDiagnostics (4). **Measured at
        `d50a058` (2026-07-15): Oracle 155→150 (95.4%), T-SQL 418→412
        (87.5%), MySQL 198→194 (93.7%) — all three moved; the
        stacked_diagnostics chain (waves 30→33→34) is unblocked
        end-to-end. Cumulative: T-SQL 1090→412, MySQL 579→194, Oracle
        454→150.**
        *Wave 35 (2026-07-15, deep chains):* `FOR v IN EXECUTE
        '<literal>'` — after wave 18 the dollar-quoted dynamic string
        is a plain literal, so the EXECUTE is unnecessary: the query
        INLINES (faithful on every target; the transition-table
        trigger family shipped `CURSOR FOR execute '…'`, invalid
        T-SQL). A NON-literal EXECUTE source (real dynamic SQL) joins
        the whole-routine degrade scan — no cursor-over-dynamic form
        off PG. Tests: TestForExecuteLiteralInlines. **Measured at
        `f5691aa`: −1/−1/−1 — the inlined loops now hit the NEXT link:
        the T-SQL cursor expansion's `FETCH INTO /* @col1… */`
        placeholder (column vars underivable in general; derivable
        when the loop var is scalar and the SELECT has exactly one
        output column — next link classified). Cumulative: T-SQL
        1090→411, MySQL 579→193, Oracle 454→149.**
        *Wave 36 (2026-07-15, deep chains):* transition-table aliases —
        PG statement triggers name them (`REFERENCING NEW TABLE AS
        newtab`); T-SQL's are the fixed `inserted`/`deleted`. The
        inlined trigger body's alias references now rename (outside
        string literals, via a generic raw-text-field walker); PG keeps
        REFERENCING verbatim. Tests: TestTransitionTableAliases. Sweep
        re-measure done: **flat at `bbbacd7` — the real blocker was one
        deeper: those triggers iterate DYNAMIC EXPLAIN output (engine
        introspection, `dbo.EXPLAIN (…)` as a cursor source). Wave 37
        refines the wave-35 inlining: only QUERY literals
        (SELECT/VALUES/WITH) inline; non-query literals join the
        whole-routine degrade. Tests:
        TestForExecuteNonQueryDegrades.**
        *Wave 38 (2026-07-16):* wave 37 ALSO measured flat — the
        two-strikes rule fired and the end-to-end trace found the real
        hole: the trigger-INLINE path (PG_TRIGGER_FN_BODIES) re-parses
        the harvested body and expands it BYPASSING the routine-level
        degrade scan. The inline now runs the same scan and degrades
        the TRIGGER whole when the body is unconvertible. Tests:
        TestTriggerInlineDegradeGate. **Measured at `da454df`: T-SQL
        411→408 (−3, the dynamic-EXPLAIN subset).**
        *Wave 39 (2026-07-16):* the rest of the trigger family blocks
        on plpgsql's `FOUND` flag (error 4145): per-target predicates
        now map it — `(@@ROWCOUNT > 0)` on T-SQL, `(ROW_COUNT() > 0)`
        on MySQL, native `SQL%FOUND` on Oracle (string-safe,
        pg-source only). Tests: TestPlpgsqlFoundFlag. **Measured at
        `62c078b` (2026-07-16): T-SQL 408→402 (−6, 87.8%); MySQL/Oracle
        syntax flat, ok +1 each. Cumulative: T-SQL 1090→402, MySQL
        579→193, Oracle 454→149.**
        *Wave 40 (2026-07-16):* plpgsql's TG_* context variables are
        compile-time CONSTANTS once the trigger function inlines into a
        named trigger — TG_NAME/TG_TABLE_NAME/TG_OP/TG_WHEN/TG_LEVEL
        substitute as literals from the trigger node (18x error 128).
        Next link classified: whole-row `inserted::text` stringification
        (no T-SQL form). Tests: TestTgContextConstants. **Measured at
        `54255e8` (2026-07-16): T-SQL 402→384 (−18, 88.3% — the whole
        child-trigger family in one stroke); MySQL/Oracle flat.
        Cumulative: T-SQL 1090→384, MySQL 579→193, Oracle 454→149.**
        *Wave 41 (2026-07-16):* null-safe comparison — PG's `IS [NOT]
        DISTINCT FROM` shipped raw as an unmapped operator (1064 on
        MySQL). Proper IR operators (NULLSAFE_EQ/NEQ) with per-dialect
        emission: MySQL `<=>` / `NOT (a <=> b)`, the version-safe
        EXISTS-INTERSECT form on T-SQL and Oracle (INTERSECT compares
        null-safely everywhere; Oracle arms take FROM DUAL), PG native.
        Tests: TestNullSafeComparison. **Measured at `3b41e16`:
        MySQL 193→183 (−10, 94.1%), Oracle ok +11 (INTERSECT forms
        run), T-SQL +1 — a select-list case exposed the
        value-vs-predicate gap.**
        *Wave 42 (2026-07-16):* that gap — a predicate is not a value
        on T-SQL/Oracle: the null-safe forms wrap in `CASE WHEN … THEN
        1 ELSE 0 END` in value position, and `_emit_condition`
        (WHERE/HAVING/ON) unwraps to the bare predicate. Tests
        strengthened (value + condition positions). **Measured at
        `f06d57d`: flat — the one select-list corpus case needs its own
        trace (single statement; parked).**
        *Wave 43 (2026-07-16):* select-list PREDICATES from MySQL
        sources — comparisons are VALUES there (1/0/NULL) but T-SQL/
        Oracle reject a predicate in value position (38x error 102 in
        mysql→tsql). `_emit_value_expression` wraps them tri-state
        exactly: `CASE WHEN p THEN 1 WHEN not-p THEN 0 END` (ELSE NULL
        implicit — MySQL's NULL semantics; the negation flips the
        operator when possible). Condition positions and PG boolean
        values untouched. Tests: TestSelectListComparisonsWrap. Sweep
        re-measure done: **at `53020a8` — mysql→T-SQL 565→536 (−29,
        91.2%), pg→T-SQL 385→380 (incl. the parked wave-42 case);
        mysql→Oracle +4 traced NOT to the wrap but to a distinct
        class:**
        *Wave 44 (2026-07-16):* MySQL routine bodies may be a SINGLE
        statement without BEGIN (`CREATE PROCEDURE g(..) CASE … END
        CASE;`); the declare-section parser shredded them into garbage
        declarations. A statement-keyword body now parses as one
        statement (the CASE statement legitimately converts to
        IF/ELSE). Tests: TestMysqlSingleStatementBody. **Measured at
        `c7dba03` (2026-07-16): −46 across the direction — mysql→Oracle
        327→308 (95.0%, the +4 reversed and beaten), mysql→T-SQL
        536→516 (91.5%), mysql→PG 396→389 (93.9%). Standing: pg-source
        {380/183/149}, mysql-source {516/389/308} — all six directions
        ≥88.5%.**
        *Wave 45 (2026-07-16):* two more dropped-definition shapes
        behind the 54x bare `CREATE TABLE` (mysql→pg): a table whose
        columns are ALL generated (passthrough fragments; `columns`
        empty → the emit skipped the whole parenthesized branch,
        constraints included — now triggers on constraints too), and
        CTAS whose query is a UNION (the M2 extraction accepted only
        exp.Select; now any SetOperation). Tests:
        TestBareCreateResidue. **Measured at `dc6eda1` (2026-07-16):
        −110 across the direction — mysql→PG 389→338 (94.7%),
        mysql→T-SQL 516→457 (92.5%), mysql→Oracle 308→307 with ok +13.
        Standing: pg-source {380/183/149}, mysql-source {457/338/307}.**
        *Wave 46 (2026-07-16):* three residue classes — the
        all-defaults `INSERT … VALUES ()` (every row empty) emitted a
        bare `VALUES ()` (invalid off MySQL); the existing DEFAULT
        VALUES fallback only fired when the values list was absent, so
        it now also routes the all-empty-rows shape (T-SQL/PG `DEFAULT
        VALUES`, Oracle degrades — no spelling without the column
        list). `IS` became a first-class BinaryOperator (was RawSQL
        'unmapped operator Is'), so `x IS NULL` in VALUE position gets
        wave 43's tri-state CASE wrap; IS/NULLSAFE joined
        _BIN_PRECEDENCE (the embedded-DML path KeyError'd). Sweep-side:
        tsql error 911 (USE of an absent database) reclassified as
        environmental, not syntax. Tests: TestEmptyValuesAndIsNullValue.
        **Measured at `faeef75` (2026-07-16): mysql→T-SQL 457→419
        (93.1%), mysql→PG 338→327 (94.8%), mysql→Oracle 307→296
        (95.2%). Standing: pg-source {380/183/149}, mysql-source
        {419/327/296}.**
        *Wave 47 (2026-07-16):* NATURAL join modifiers were silently
        DROPPED (sqlglot carries them in `method`, the converter read
        only side/kind): `NATURAL FULL JOIN` shipped as `FULL JOIN`
        with no ON at all (26x of the pg→tsql residue). JoinClause
        gained a `natural` flag: preserved on PG/MySQL/Oracle
        (`NATURAL JOIN` bare spelling for inner — MySQL rejects
        `NATURAL INNER JOIN`), whole-degrade on T-SQL (no NATURAL in
        any spelling, ON not synthesizable without column knowledge);
        mysql's FULL gate already catches NATURAL FULL there. Tests:
        TestNaturalJoins. **Measured at `6be4e8c` (2026-07-16):
        pg→T-SQL 380→374 (88.6%), pg→MySQL 183→180 (94.2%),
        pg→Oracle 149 flat. Standing: pg-source {374/180/149},
        mysql-source {419/327/296}.**
        *Wave 48 (2026-07-16):* parenthesized set-operation arms
        (`(SELECT …) UNION ALL (SELECT …)`) arrive as exp.Subquery;
        _convert_select read them as EMPTY selects — `SELECT * UNION
        ALL SELECT *`, every FROM and column dropped (62x of
        mysql→pg). Arms now unwrap; an arm with its own LIMIT is
        shielded as a derived table (trailing position would re-scope
        it to the whole union); arm-local ORDER BY without LIMIT drops
        (no observable effect in a set op); the union's OUTER
        order/limit (parsed onto the SetOperation node, previously
        ignored) attaches to the last arm. Tests:
        TestParenthesizedUnionArms. *Measurement pending next
        mysql-corpus cycle.*
        *Wave 49 (2026-07-16):* null-safe comparisons in VALUE
        position on T-SQL/Oracle shipped the predicate spelling
        `CASE … END = 1` (12x of pg→tsql — the trailing `= 1` is not
        a value there); the value position now keeps just the CASE
        (never NULL, so the two-armed form is exact). Tests:
        TestNullsafeValuePosition. **Waves 48+49 measured at `825d8cf`
        (2026-07-16, clean relaunch — the first cycle caught wave 49
        landing mid-measure): mysql→PG 327→256 (96.0%), mysql→T-SQL
        419→416 (93.2%), mysql→Oracle 296→301 (95.1%, honest +5 —
        un-carriered union arms now reach the next Oracle blocker).
        Standing: pg-source {374/180/149} at 6be4e8c, mysql-source
        {416/256/301}.**
        *Wave 50 (2026-07-16):* PG RETURNING lowered to T-SQL OUTPUT
        with BARE items — T-SQL requires the INSERTED./DELETED. prefix
        on every one (13x of pg→tsql: `OUTPUT *`, `OUTPUT a, b`).
        Items now qualify on the sqlglot AST (DELETE→DELETED, else
        INSERTED — PG returns the new row); DELETE's OUTPUT moves
        after the table (sqlglot renders it before FROM, which not
        even its reader accepts); the output gate drops the (valid)
        OUTPUT clause before its tsql reparse — a sqlglot reader gap,
        not an output defect. Tests: TestReturningOutputPrefix.
        **Waves 49+50 measured at `c1002d4` (2026-07-16): pg→T-SQL
        374→344 (89.5%), pg→Oracle 149 flat, pg→MySQL 180→186 (honest
        +6 — wave 48's un-carriered union arms reach the next MySQL
        blocker). Standing: pg-source {344/186/149}, mysql-source
        {416/256/301}.**
        *Wave 51 (2026-07-16):* TG_ARGV/TG_NARGS are compile-time
        constants once the trigger function is inlined — the CREATE
        TRIGGER's `EXECUTE FUNCTION fn('a','b')` argument list (which
        the parser used to SKIP; now captured as `execute_args`)
        supplies TG_ARGV[n]; an unresolvable index degrades the
        trigger whole (8x pg→tsql error 128). Tests:
        TestTgArgvSubstitution.
        *Wave 52 (2026-07-16):* a routine the procedural parser cannot
        parse falls back to RawSQL('Parse error…') — and shipped RAW
        cross-dialect: mysql handler-declaring procedure bodies leaked
        as top-level fragments on pg (~43x of mysql→pg: `declare
        continue/exit handler`, `end if/while`, quoted-alias SELECTs
        …). The procedural transformer now rewrites the parse fallback
        to the carrier contract (source==target still passes through
        untouched). Follow-up chain: parse DECLARE …HANDLER properly
        (EXIT→EXCEPTION is faithful; CONTINUE has no plpgsql map).
        Tests: TestParseFallbackDegradesCrossDialect. **Wave 52
        measured at `c92a5ab` (2026-07-16): −212 across the direction
        — mysql→PG 256→156 (97.5%), mysql→T-SQL 416→359 (94.0%),
        mysql→Oracle 301→246 (96.0%). Standing: pg-source
        {344/186/149}, mysql-source {359/156/246}; wave 51's pg-corpus
        measure pending.**
        *Wave 53 (2026-07-16):* PG's column-renaming table alias
        (`x AS xx(xx1, xx2)`) silently DROPPED its column list on
        every target (7x pg→tsql shipped it raw inside joins).
        TableRef gained `column_aliases`: T-SQL rewrites faithfully to
        `(SELECT * FROM x) AS xx(xx1, xx2)` (alias lists are legal on
        derived tables), PG keeps native, MySQL/Oracle whole-degrade
        (no spelling without column knowledge). Tests:
        TestTableColumnAliases.
        *Wave 54 (2026-07-16):* two invalid-shipping shapes on T-SQL —
        NTH_VALUE mapped to a fictitious `dbo.NTH_VALUE(...) OVER`
        (4x; now whole-degrades with the ROW_NUMBER emulation hint),
        and INSERT combining RETURNING with ON CONFLICT took the
        RETURNING passthrough leaving `ON CONFLICT` raw after OUTPUT
        (4x; now a MERGE-hint carrier off PG). Tests:
        TestTsqlInvalidShapesDegrade. **Waves 51+53+54 measured at
        `5997002` (2026-07-16): pg→T-SQL 344→266 (91.8%), pg→MySQL
        186→180 (94.1%), pg→Oracle 149→140 (95.6%). Standing:
        pg-source {266/180/140}, mysql-source {359/156/246} — all six
        ≥91.8%.**
        *Wave 55 (2026-07-16):* two mechanical mysql→tsql classes — a
        numeric literal operand of AND/OR in condition position (MySQL
        truthiness) becomes `lit <> 0` on T-SQL/Oracle (15x error
        4145: `HAVING f1 = 'a' OR 1`); and a scalar subquery's ORDER
        BY without LIMIT (illegal on T-SQL, no observable effect)
        strips (7x error 1033). Tests:
        TestTsqlBooleanLiteralsAndScalarOrder. **Measured at `e999409`
        (2026-07-16): mysql→T-SQL 359→347 (94.2%), →PG 156 and →Oracle
        246 flat. Standing: pg-source {266/180/140}, mysql-source
        {347/156/246}. Remaining mysql→tsql chains classified: 32x
        `SELECT … INTO @var` (sqlglot mangles the multi-var parse —
        degrade), 11x USING inside parenthesized join relations (the
        joins live on the inner Table's `joins` arg, never read), 12x
        mysql `@@sysvar` references, 6x RAND(seed).**
        *Wave 56 (2026-07-16):* MySQL's session-variable `SELECT …
        INTO @var[, @var2]` — sqlglot mangles the multi-var parse
        (extra vars absorb into the select list), and the CTAS path
        shipped `CREATE TABLE $a AS …` garbage (32x mysql→tsql). Now a
        `SELECT INTO VAR` passthrough: native on the source engine
        (identity keeps the ORIGINAL text, intercepted in parse_sql
        before the mangle), assignment-form-hint carrier elsewhere.
        Tests: TestSelectIntoUserVariable.
        *Wave 57 (2026-07-16):* single-level parenthesized join
        relations (`FROM (t1 LEFT JOIN t2 USING (a)), t3`) shipped raw
        through the PAREN JOIN passthrough — sqlglot keeps USING on
        tsql (11x). The group now unwraps: inner table + its `joins`
        arg hoist into the select (parens around joins are
        semantically transparent; comma-join order preserved); only
        deeper nesting stays passthrough. Tests:
        TestParenthesizedJoinRelations. **Measured at `6c15672`
        (2026-07-16): mysql→T-SQL 347→334 (94.5%), mysql→PG 156→153
        (97.5%), mysql→Oracle 246 flat. Standing: pg-source
        {266/180/140}, mysql-source {334/153/246}.**
        *Wave 58 (2026-07-16):* three mysql edge-value classes —
        CAST of an invalid calendar date ('0000-00-00', '2000-02-31',
        'YYYY-MM-DD'…) whole-degrades off MySQL (MySQL returns NULL +
        warning, everyone else errors; 24x), interval arithmetic
        `expr ± INTERVAL 'n' UNIT` lowers to `DATEADD(UNIT, ±n, expr)`
        on T-SQL (6x), and a MySQL `@@sysvar` T-SQL doesn't know
        (whitelist of T-SQL globals) whole-degrades (12x error 137).
        Tests: TestMysqlEdgeValueClasses. **Measured at `3a6f13e`
        (2026-07-16): mysql→T-SQL 334→303 (94.9%), mysql→Oracle
        246→242, mysql→PG 153 flat. Standing: pg-source
        {266/180/140}, mysql-source {303/153/242}.**
        *Wave 59 (2026-07-16):* three mysql-source classes — a
        top-level statement referencing a MySQL @user variable shipped
        raw off MySQL (session state lives client-side there; 23x
        ORA-00936 plus pg/tsql twins — whole-degrade, source==mysql
        gate); the EXISTS-INTERSECT null-safe form emitted ROW
        constructors as parenthesized tuples (`SELECT (f1, f2) FROM
        DUAL`, ORA-00907 15x — operands now unpack into select-list
        items, ExpressionList or paren-RawSQL); and MySQL's
        fixed-point `DOUBLE(p,s)`/`FLOAT(p,s)` mapped to
        `BINARY_DOUBLE(7, 2)` on Oracle which takes no parameters
        (13x ORA-00922 — now NUMBER(p,s)). Tests:
        TestUserVarsRowTuplesOracleDouble. **Measured at `60bf727`
        (2026-07-16): −59 across the direction — mysql→T-SQL 303→276
        (95.4%), mysql→Oracle 242→212 (96.5%), mysql→PG 153→148
        (97.6%). Standing: pg-source {266/180/140}, mysql-source
        {276/148/212}.**
        *Wave 60 (2026-07-16):* LATERAL joined subqueries VANISHED —
        exp.Lateral fell through _convert_table_or_subquery to an
        empty TableRef and the gate carriered the batch (7x pg→tsql).
        JoinClause gained `lateral`: T-SQL/Oracle spell it APPLY
        (LEFT + ON TRUE → OUTER APPLY, INNER/CROSS → CROSS APPLY),
        PG/MySQL keep native `LEFT JOIN LATERAL … ON …`; a non-TRUE
        lateral condition keeps the LATERAL spelling (gate carriers it
        on tsql — no APPLY equivalent). Tests: TestLateralJoins.
        **Measured at `2399670` (2026-07-16): un-carriered LATERAL
        batches un-glued +51 statements on pg→tsql (ok 2963→3010,
        syntax 266→270 — honest +4 reaching next blockers); pg→MySQL
        180→173 (94.4%), pg→Oracle 140→144 (honest +4). Standing:
        pg-source {270/173/144}, mysql-source {276/148/212}.**
        *Wave 61 (2026-07-16):* four mysql→tsql classes — row-tuple
        comparisons expand pairwise on T-SQL (no row constructors;
        `(a,b) = (x,y)` → `a = x AND b = y`, `<>` → OR; 17x error
        4145); boolean literals under AND/OR join wave 55's rewrite
        (`OR TRUE` shipped as bare `OR 1`; 13x); single-argument ROUND
        gains the mandatory scale (6x error 189); `SET NAMES`/
        `CHARACTER SET` join the session-knob carriers (3x error
        195). Tests: TestTuplesRoundSetNamesBoolLiterals. **Measured
        at `30aaf2d` (2026-07-16): −42 — mysql→T-SQL 276→252 (95.8%),
        mysql→PG 148→140 (97.7%), mysql→Oracle 212→202 (96.7%).
        Standing: pg-source {270/173/144}, mysql-source
        {252/140/202}.**
        *Wave 62 (2026-07-16):* STR_TO_DATE of an impossible date
        lowers to CAST at EMIT time — after wave 58's gate had run;
        the gate now inspects the function form too (6x mysql→tsql).
        And routines declaring/returning a PG composite type
        (`CREATE TYPE x AS (…)`, itself an Unhandled-CREATE carrier)
        shipped `DECLARE @v compostype` (6x pg→tsql): new
        PG_COMPOSITE_TYPES harvest + composite culprit in
        _degrade_record_function. Tests:
        TestStrToDateAndCompositeTypes. **pg-corpus measured at
        `2b943f6` (2026-07-16): pg→T-SQL 270→265 (91.9%), pg→MySQL
        173→163 (94.7%), pg→Oracle 144→142 (95.6%). Standing:
        pg-source {265/163/142}, mysql-source {252/140/202}.**
        *Wave 63 (2026-07-16):* four mysql→tsql classes — a row tuple
        compared to a SUBQUERY has no pairwise expansion
        (whole-degrade with the join/EXISTS hint; 16x); a bare scalar
        subquery in condition position is MySQL truthiness → `(sq) <>
        0` on T-SQL/Oracle (12x); a view's ORDER BY without TOP strips
        on T-SQL (illegal there, advisory on MySQL; 3x); zero-length
        CHAR/VARCHAR/BINARY become length 1 off MySQL (5x error
        1001). Tests: TestSubqueryConditionsViewOrderCharZero.
        **Measured at `62e7f1c` (2026-07-16): mysql→T-SQL 252→238
        (96.0%), mysql→PG 140 flat, mysql→Oracle 202 flat with ok
        +15. Standing: pg-source {265/163/142}, mysql-source
        {238/140/202} — all six directions ≥91.9%.**
        *Wave 64 (2026-07-16):* wave 59's @user-variable gate covered
        the DML pipeline only — routines travel the PROCEDURAL one,
        which shipped `@cnt := := @cnt + 1` garbage to Oracle (52x
        mysql→oracle: CALL blocks 26x, functions 16x, triggers 10x —
        the wave-38 alternate-route hole class again). The procedural
        transformer now whole-degrades any routine/call referencing a
        @user variable off MySQL. Tests: TestUserVarsInRoutines.
        **Measured at `00c2476` (2026-07-16): −70 — mysql→T-SQL
        238→213 (96.4%), mysql→PG 140→121 (98.0%), mysql→Oracle
        202→176 (97.1%). Standing: pg-source {265/163/142},
        mysql-source {213/121/176}.**
        *Wave 65 (2026-07-16):* MySQL's `INT UNSIGNED` in routine
        parameter/declare types broke the procedural parser — the
        whole body was swallowed as parameter garbage (15x mysql→pg);
        UNSIGNED/SIGNED/ZEROFILL now parse as type attributes (they
        tokenize as IDENTIFIERs, so the stop-word scan accepts those
        too), and `WHILE … DO … END WHILE` joined the loop grammar.
        PROCEDURAL_TYPE_MAPS gained the missing (mysql, oracle) and
        (mysql, postgresql) entries (`RETURN tinyint` shipped raw as
        PLS errors; DATETIME→TIMESTAMP to agree with the emit map).
        The scalar-subquery ORDER BY strip extends to Oracle (7x
        ORA-00907). Tests: TestUnsignedParamsOracleTypes. **Measured
        at `def5cb3` (2026-07-16): −23 — mysql→T-SQL 213→210 (96.5%),
        mysql→PG 121→113 (98.1%), mysql→Oracle 176→164 (97.3%).
        Standing: pg-source {265/163/142}, mysql-source
        {210/113/164}. pg-corpus re-verified at `76742d3`: identical
        {265/163/142} — the wave-65 parser changes (identifier stop
        words) cost nothing on pg source.**
        *Wave 66 (2026-07-16):* MySQL's `CHAR BINARY` collation
        attribute shredded the parameter parser like UNSIGNED did
        (12x mysql→pg; BINARY joins the attribute set), and a CALL to
        a routine whose CREATE degraded earlier in the same script
        shipped as `BEGIN a(3); END;` — PLS-00221 at compile (18x
        mysql→oracle). New DEGRADED_ROUTINES per-run registry:
        populated by every routine degrade (uservar, record/composite,
        parse fallback — name regexed from the original), checked in
        _transform_call. Tests: TestCharBinaryAndDegradedCallRegistry.
        First cycle at `4e87922` exposed two follow-ups (66b): the
        CALL carrier got WRAPPED in `BEGIN … END;` — a comment-only
        block, PLS-00103 (oracle 164→225 regression; an
        AnonymousBlock whose every statement degraded now returns the
        merged carrier bare); and `BEGIN a(3); END;` where the proc
        EXISTS but compiled invalid (its body references absent
        schemas) is an environmental cascade — PLS-00221 joins the
        sweep's expected bucket. **Measured at `5ab96bb`
        (2026-07-16): mysql→Oracle 164→158 (97.4%, the +61 regression
        fully reversed), mysql→PG 113→112 (98.1%), mysql→T-SQL 210
        flat (96.4%). Standing: pg-source {265/163/142}, mysql-source
        {210/112/158}.**
        *Wave 67 (2026-07-16):* MySQL's `REPEAT … UNTIL cond END
        REPEAT` shredded into garbage statements (`repeat AS set;` —
        REPEAT/UNTIL tokenize as identifiers, no grammar existed). It
        parses now as a post-test loop: LoopStatement with a trailing
        `EXIT WHEN cond`, native on every target. Tests:
        TestRepeatUntilLoop. **Measured at `50d734a` (2026-07-16):
        mysql→T-SQL 210→209, mysql→PG 112→111, mysql→Oracle 158→160
        (honest +2: un-carriered REPEAT routines reach their next
        blocker). Standing: pg-source {265/163/142}, mysql-source
        {209/111/160}. The mysql-source residue is now long-tail
        (top classes ≤5x); the next highest-yield front is the
        pg→tsql 265 (raise_test/EXCEPTION chains) and the
        DECLARE HANDLER fidelity work (carriers → EXIT→EXCEPTION
        conversions, no validity delta).**
        *Wave 68 (2026-07-16):* PG's `RAISE condition_name [USING k =
        v]` fell to the raw-expression path — T-SQL declared `@msg
        NVARCHAR(2048) = division_by_zero using detail = '…'` (6x
        pg→tsql raise_test). The condition name now folds into a
        literal message with USING items appended as text (the format
        path's existing convention). Tests: TestRaiseConditionName.
        **Measured at `7693a9f` (2026-07-16): pg→T-SQL 265→262
        (92.0%), pg→MySQL 163→160 (94.8%), pg→Oracle 142→140 (95.7%).
        Standing: pg-source {262/160/140}, mysql-source
        {209/111/160}.**
        *Wave 69 (2026-07-16):* a CTE body's ORDER BY without LIMIT
        is illegal on T-SQL (error 1033, ~7x pg→tsql) and cannot
        change the result — strips like the view/scalar-subquery
        cases (waves 55/63). Tests: TestCteOrderByStrip. **Measured at
        `c9d5a60` (2026-07-16): pg→T-SQL 262→261, others flat — the
        WITH chains carry further blockers (whole-row `SELECT q FROM
        q` refs). Standing: pg-source {261/160/140}, mysql-source
        {209/111/160}. Both directions are converged to deep
        multi-blocker chains: per-wave yield has been ≤3 for four
        waves. Remaining named fronts (fidelity, not validity):
        DECLARE HANDLER EXIT→EXCEPTION conversion, PG whole-row CTE
        references on tsql, EXPLAIN/psql-ism passthrough polish.**
        *Wave 70 (2026-07-16):* MySQL's `DECLARE {EXIT|CONTINUE|UNDO}
        HANDLER FOR conds stmt` now PARSES (new HandlerDeclaration
        node; wave 52 had been carrying whole routines). An EXIT
        handler for SQLEXCEPTION/SQLWARNING folds into the enclosing
        block's TryCatchBlock — EXCEPTION WHEN OTHERS on PG/Oracle,
        TRY/CATCH on T-SQL; identity keeps the native DECLARE …
        HANDLER spelling. CONTINUE handlers (resume semantics — no
        target equivalent), specific conditions (SQLSTATE/errno/named)
        and nested/multiple handlers keep the honest whole-routine
        degrade, now with the culprit spelled out. This is fidelity
        work: those routines were already carriers, so sweep validity
        should hold or improve slightly. Tests:
        TestMysqlDeclareHandler. **Measured at `95afaf8`
        (2026-07-16): the fidelity gain is visible — mysql→PG 111
        flat with ok +6 and warnings 289→263 (fewer carriers),
        mysql→T-SQL 209 flat with ok +11, mysql→Oracle 160→165
        (honest +5: converted handler bodies now reach PL/SQL's
        SELECT-without-INTO — the next front). Standing: pg-source
        {261/160/140}, mysql-source {209/111/165}.**
        *Wave 71 (2026-07-16):* the bare-SELECT → SYS_REFCURSOR
        rewrite (Oracle) did not recurse into TryCatchBlock bodies —
        a result SELECT inside wave 70's folded exception section
        shipped as PL/SQL SELECT-without-INTO (the +5). The recursion
        now covers try/catch bodies. Tests: TestRefcursorInTryCatch.
        **Measured at `f4cf7c9` (2026-07-16): mysql→Oracle 165→164;
        the rest of wave 70's +5 carries further blockers. Standing:
        pg-source {261/160/140}, mysql-source {209/111/164}.**
        *Wave 72 (2026-07-16):* two more MySQL-truthiness shapes — a
        bare function call or COLUMN as a condition gains `<> 0` on
        T-SQL/Oracle (`WHERE dbo.DAYNAME('…')`, `WHERE b`); and a row
        tuple in `IN (SELECT …)` joins wave 63's whole-degrade (the
        IN operator joins the tuple-vs-subquery gate). Tests:
        TestBareValueConditionsAndTupleIn. **Measured at `4511621`
        (2026-07-16): mysql→T-SQL 209→188 (−21, 96.8%) — the
        truthiness shapes were widespread; →PG/→Oracle flat.
        Standing: pg-source {261/160/140}, mysql-source
        {188/111/164}.**
        *Wave 73 (2026-07-16):* STR_TO_DATE inside an unconverted
        expression blob (a BETWEEN fallen to RawSQL) ships raw off
        MySQL — the emit-time STR_TO_DATE→CAST mapping only fires on
        FunctionCall nodes (6x error 195). The invalid-date gate now
        degrades statements whose RawSQL text calls STR_TO_DATE.
        Tests: TestRawStrToDateDegrades. **Measured at `173e7cf`
        (2026-07-16): mysql→T-SQL 188→180 (96.9%), →PG/→Oracle flat.
        Standing: pg-source {261/160/140}, mysql-source
        {180/111/164}.**
        *Wave 74 (2026-07-16):* the SYS_REFCURSOR rewrite changes the
        procedure's SIGNATURE, but same-script CALLs kept the old
        arity — PLS-00306 at compile (19x mysql→oracle). New
        REFCURSOR_PROCS per-run registry (populated when the rewrite
        adds params); later CALLs now wrap in a nested DECLARE block
        with local `uq_rcN SYS_REFCURSOR` variables appended to the
        argument list. Tests: TestRefcursorCallSites. **Measured at
        `f8ceb42` (2026-07-16): mysql→Oracle 164→144 (−20, 97.6%, ok
        +22); →PG/→T-SQL flat. Standing: pg-source {261/160/140},
        mysql-source {180/111/144}.**
        *Wave 75 (2026-07-16):* MySQL double-quoted STRING literals
        inside procedural raw text (`CONCAT(arg, "")`, `SET x =
        "it's"`) survived to targets where `"` delimits IDENTIFIERS —
        pg 42601 zero-length identifier (11x mysql→pg). A string-safe
        scanner now rewrites them to single-quoted literals (inner
        quotes doubled, backslash escapes honored) in
        _transform_raw_sql off MySQL. Tests:
        TestMysqlDoubleQuotedStrings. **Measured at `a4d7783`
        (2026-07-16): −9 across all three — mysql→T-SQL 180→177
        (97.0%), mysql→PG 111→108 (98.2%), mysql→Oracle 144→141
        (97.6%). Standing: pg-source {261/160/140}, mysql-source
        {177/108/141}.**
        *Wave 76 (2026-07-16):* MySQL labeled loops (`foo: loop … end
        loop foo`) and `LEAVE label` mangled into `foo AS %(loop)s;`
        garbage (4x mysql→pg). Labels parse now (loop/while/repeat
        heads; trailing END labels consumed; LEAVE→ExitStatement with
        label, ITERATE→CONTINUE); the label flows through
        _transform_loop and PG/Oracle emit `<<label>> LOOP … END LOOP
        label;` with `EXIT label;`. Tests: TestLabeledLoops.
        **Measured at `f083425` (2026-07-16): mysql→PG 108→107,
        others flat — the labeled routines carry further blockers.
        Standing: pg-source {261/160/140}, mysql-source
        {177/107/141}.**
        *Wave 77 (2026-07-16):* T-SQL forbids subqueries in PRINT
        arguments (error 1046 — 56x pg→tsql, inlined trigger bodies
        printing transition-table aggregates). The expression now
        hoists into a `DECLARE @uq_prtN NVARCHAR(MAX) = …` temp
        (initializers DO accept subqueries) and PRINT takes the
        variable. Tests: TestPrintSubqueryHoist. **Measured at
        `4c1c679` (2026-07-16): pg→T-SQL 261→257 (92.1%) — the 1046
        triggers carry further blockers (`dbo.FROM` mangles in UNION
        aggregates, OLD refs); →MySQL/→Oracle flat. Standing:
        pg-source {257/160/140}, mysql-source {177/107/141}.**
        *Wave 78 (2026-07-17):* `FROM (` before a derived table got
        dbo.-qualified (`dbo.FROM`) by the user-function pass —
        FROM/JOIN/LATERAL/APPLY were missing from TSQL_NEVER_QUALIFY
        (2x pg→tsql inside trigger CTEs, blocking the 1046 chain).
        Tests: TestFromNeverQualifies. **Measured at `6033f9a`
        (2026-07-17): pg→T-SQL 257→256 (92.2%). Standing: pg-source
        {256/160/140}, mysql-source {177/107/141}.**
        *Wave 79 (2026-07-17):* PG `expr::type` casts inside
        procedural raw text shipped as `x : : type` off PG (65x, the
        biggest remaining pg→tsql class) — simple operands
        (identifiers/@vars/numbers) rewrite to `CAST(x AS type)`
        string-safely; string-literal and parenthesized operands stay
        (rare). And `CAST(NOT b AS INT)` is invalid on T-SQL (NOT is
        not a value there; 12x) — the operand wraps tri-state
        `CASE WHEN b = 0 THEN 1 WHEN b <> 0 THEN 0 END`. Tests:
        TestPgCastsInRawTextAndNotInCast. **Measured at `d4bdacc`
        (2026-07-17): pg→Oracle 140→135 (95.8%), pg→T-SQL 256→254
        (92.2%) — the 65x routines also carry `RETURNS foodomain`
        (CREATE DOMAIN types; next front: harvest domains → base
        types, like PG_COMPOSITE_TYPES). Standing: pg-source
        {254/160/135}, mysql-source {177/107/141}.**
        *Wave 80 (2026-07-17):* PG DOMAIN types survived into
        signatures, declares and raw casts off PG (unknown type names
        — the rest of the 65x class). New PG_DOMAIN_TYPES harvest
        (name → base type); _transform_data_type resolves them and
        raw-text casts substitute string-safely. Tests:
        TestPgDomainTypes. **Measured at `f8c7cec` (2026-07-17):
        pg→MySQL 160→159, tsql/oracle flat — the domain routines
        stack `RETURN (SELECT … language sql)` body mangles on top
        (LANGUAGE sql single-expression functions whose body leaks
        into the RETURN). Standing: pg-source {254/159/135},
        mysql-source {177/107/141}.**
        *Wave 81 (2026-07-17):* the LANGUAGE-sql single-expression
        body capture ran past its closing $$ — `language sql` /
        IMMUTABLE / STRICT leaked into the RETURN expression (the
        rest of the 65x chain). Tail attributes now strip from the
        captured result. Tests: TestLanguageSqlTailStrip. **Measured
        at `e90c761` (2026-07-17): pg→T-SQL 254→252 (92.3%),
        pg→Oracle 135→133 (95.9%), →MySQL flat. Standing: pg-source
        {252/159/133}, mysql-source {177/107/141}.**
        *Wave 82 (2026-07-17):* PG's in-call aggregate ORDER BY —
        `STRING_AGG(x, ',' ORDER BY a)` — is `… ) WITHIN GROUP (ORDER
        BY a)` on T-SQL (51x, the blocker wave 77's hoist exposed). A
        paren-aware, string-safe scanner rewrites it in raw trigger
        text. Tests: TestStringAggOrderBy. **Measured at `abeaaa0`
        (2026-07-17): pg→T-SQL 252→198 (−54, 93.9%, ok +54) — the
        whole class cleared. Standing: pg-source {198/159/133},
        mysql-source {177/107/141}.**
        *Wave 83 (2026-07-17):* `BOOL_AND(NOT b2)` lowered to
        `MIN(CAST(NOT b2 AS INT))` on T-SQL — the boolean-aggregate
        mapping string-formats its arg, bypassing wave 79's IR wrap
        (12x); predicate/NOT args now wrap tri-state before the CAST.
        And `INSERT INTO t (cols) WITH cte AS (…) SELECT` puts the
        CTE after the INSERT clause — T-SQL requires WITH first (14x
        error 156); the CTE hoists before the INSERT. Tests:
        TestBoolAggregateNotArg, TestInsertCteHoist. **Measured at
        `3cc6a3d` (2026-07-17): pg→T-SQL 198→189 (94.2%), others
        flat. Standing: pg-source {189/159/133}, mysql-source
        {177/107/141}.**
        *Wave 84 (2026-07-17):* a searched CASE's WHEN emitted its
        condition as an EXPRESSION — a bare boolean column
        (`CASE WHEN b1 THEN …`) shipped raw to T-SQL (part of the
        4145 residue). Searched WHENs (no operand) now emit in
        condition position, picking up the truthiness wraps; simple
        CASE operands stay expressions. Tests:
        TestCaseWhenBareBoolean. **Measured at `e540dc3`
        (2026-07-17): pg→T-SQL 189→182 (94.4%), others flat. CI note:
        waves 83's `inner` name collision tripped CI mypy (version
        newer than local) at 3cc6a3d/6376336 — fixed in this wave's
        commit, CI green again at e540dc3. Standing: pg-source
        {182/159/133}, mysql-source {177/107/141}.**
        *Wave 85 (2026-07-17):* linking an outer set operation onto
        an arm that is ITSELF a chain (`(a UNION b ORDER BY 1)
        INTERSECT c`) clobbered the nested chain — the whole inner
        tail vanished silently, and a surviving tail ORDER BY landed
        mid-chain (error 156, 3x+). Chain arms now link at their
        TAIL, dropping a tail ORDER BY without LIMIT. Tests:
        TestNestedChainMidOrderStrip. **Measured at `56e1e9f`
        (2026-07-17): validity flat {182/159/133} — the clobbered
        arms had been emitting VALID SQL with silently missing data,
        so this is a pure correctness (no-silent-loss) repair.
        Standing: pg-source {182/159/133}, mysql-source
        {177/107/141}.**
        *Wave 86 (2026-07-17):* PG array types in RETURNS shredded
        the header — the RETURNS branch used the generic type parser,
        not the pg-aware one that consumes `[]` (48x pg→oracle:
        `[] LANGUAGE; plpgsql STRICT;` garbage declares). RETURNS now
        parses pg-aware, and array-typed params/returns/declares
        degrade the routine whole off PG (no target equivalent).
        Tests: TestPgArrayTypedRoutines. **Measured at `478ced0`
        (2026-07-17): −29 across the direction — pg→T-SQL 182→174
        (94.7%), pg→MySQL 159→147 (95.2%), pg→Oracle 133→124 (96.2%).
        Standing: pg-source {174/147/124}, mysql-source
        {177/107/141}.**
        *Wave 87 (2026-07-17):* PG ARRAY constructors inside routine
        BODIES (`x := array[$1,$2]`) shipped raw off PG — wave 86
        checked declared types only (part of the 39x pg→oracle
        residue). A body whose raw text builds arrays now degrades
        the routine whole. Tests: TestArrayConstructorInBody.
        **Measured at `d58d8e0` (2026-07-17): −4 — pg-source
        {172/146/123}; the 39x PLS class is heterogeneous (remaining
        shapes: dotted refs, assignment mangles — deep singles).
        Standing: pg-source {172/146/123}, mysql-source
        {177/107/141}.**
        *Wave 88 (2026-07-17):* top-level DML with RETURNING shipped
        the clause raw to Oracle (ORA-00936, 7x) — RETURNING…INTO
        exists only inside PL/SQL with target variables. Same
        contract as the MySQL branch: the DML keeps its effect
        (sqlglot-rendered for the target), the clause strips with a
        documented note. Tests: TestReturningOracle. **Measured at
        `a4623e5` (2026-07-17): pg→Oracle 123→98 (−25, 97.0%, ok +15
        — the class spanned INSERT/DELETE RETURNING forms too);
        tsql/mysql flat. Standing: pg-source {172/146/98},
        mysql-source {177/107/141}.**
        *Wave 89 (2026-07-17):* the RETURNING+ON CONFLICT carrier
        (wave 54) sat AFTER the MySQL RETURNING branch — MySQL
        stripped RETURNING and shipped ON CONFLICT raw (4x); the
        check now runs first, off PG. And PG E-strings in procedural
        raw text emitted as `E '...'` (3x): MySQL's backslash escapes
        are compatible, so the prefix drops there (other targets
        treat backslashes literally — left alone). Tests:
        TestOnConflictMysqlAndEStrings. **Measured at `73505e1`
        (2026-07-17): pg→MySQL 146→135 (95.6%), pg→Oracle 98→94
        (97.1%), tsql flat. Standing: pg-source {172/135/94},
        mysql-source {177/107/141}.**
        *Wave 90 (2026-07-17):* three mysql→tsql classes —
        `DELETE/UPDATE IGNORE` is unparseable by sqlglot (whole batch
        carriered and glued innocents, 4x): the modifier
        pre-normalizes away on the retry path (error-skipping
        semantics have no cross-engine form); MySQL's INVISIBLE
        column attribute strips off MySQL (3x); OFFSET…FETCH without
        ORDER BY gains `ORDER BY (SELECT NULL)` (6x). Tests:
        TestIgnoreInvisibleOffsetOrder. **Measured at `e673e81`
        (2026-07-17): mysql→T-SQL 177→165 (97.2%), mysql→PG 107→106
        (98.2%), oracle flat. Standing: pg-source {172/135/94},
        mysql-source {165/106/141}.**
        *Wave 91 (2026-07-17):* three mysql→oracle classes — charset
        introducers and COLLATE clauses (engine-local) strip from
        RawSQL fragments off MySQL (`_latin1 'test' COLLATE …`,
        ORA-00911, 3x); ROW-tuple comparisons expand pairwise on
        Oracle too (wave 61 was tsql-only, incl. the tri-state wrap's
        negated arm, 3x); and PLS-00049 (trigger :NEW field on a
        table whose CREATE degraded) joins the sweep's expected
        bucket (6x cascade). Tests:
        TestCharsetIntroducersAndRowOracle. **Measured at `b09c3ea`
        (2026-07-17): mysql→Oracle 141→129 (−12, 97.8%); tsql 166 /
        pg 107 (±1 statement-count noise). Standing: pg-source
        {172/135/94}, mysql-source {166/107/129}.**
        *Wave 92 (2026-07-17):* PG casts of PARENTHESIZED expressions
        (`row(a,b)::int8_tbl` — composite row types) survive the
        simple-operand ANSI rewrite and shipped as `) : : type` (6x
        pg→tsql). A body still carrying such a cast now degrades the
        routine whole. Tests: TestParenCastDegrades. **Measured at
        `092b41a` (2026-07-17): −14 — pg→T-SQL 172→165 (94.9%),
        pg→MySQL 135→132 (95.7%), pg→Oracle 94→90 (97.2%). Standing:
        pg-source {165/132/90}, mysql-source {166/107/129}.**
        *Wave 93 (2026-07-17):* PG's `RAISE sqlstate '1234F'` fell to
        the raw-expression path where the T-SQL SQLSTATE→ERROR_STATE
        substitution mangled it (3x); like wave 68's condition-name
        form, it folds into a literal message. Tests:
        TestRaiseSqlstateLiteral. **Measured at `8a63039`
        (2026-07-17): −3 — pg-source {164/131/89}; pg→T-SQL reaches
        95.0%. Standing: pg-source {164/131/89}, mysql-source
        {166/107/129} — all six directions ≥95.0%.**
        *Wave 94 (2026-07-17):* `(a, b) IN (VALUES (1,1), (20,0))`
        has no T-SQL/Oracle spelling (row constructors, 4145) —
        literal rows expand to the disjunction of conjunctions.
        Tests: TestTupleInValuesList. **Measured at `4cbc26b`
        (2026-07-17): pg→T-SQL 164→163, rest flat — the remaining
        statements stack multiple exotic constructs each (deep-singles
        floor: further waves cost a full cycle for −1). Standing:
        pg-source {163/131/89}, mysql-source {166/107/129}.**
        *Wave 95 (2026-07-17):* backlog housekeeping closed three
        completed items (nightly mutation floors GREEN at `17de248`,
        mysql-source corpus sweep, PG corpus import), and the
        live-check spotted there confirmed: MySQL requires
        parentheses around expression DEFAULTs — the column emitter
        shipped `DEFAULT UUID()` bare (1064). Function-call defaults
        now parenthesize (CURRENT_TIMESTAMP exempt). Tests:
        TestMysqlFunctionDefaultParens. **Measured at `d9ac96d`
        (2026-07-17): flat {163/131/89} — correctness fix (the pg
        corpus barely exercises uuid defaults). Standing: pg-source
        {163/131/89}, mysql-source {166/107/129}.**
        *Wave 27 (2026-07-15):* whole-row `COUNT(t2.*)` (PG counts
        non-NULL rows after an outer join; 9x 1064) — no spelling
        elsewhere and no rewrite without schema knowledge: a QUALIFIED
        star argument (IR: ColumnRef `*` with a table) degrades the
        statement whole on every non-PG target; plain `COUNT(*)`
        untouched. Tests: TestQualifiedStarCountDegrades. Sweep
        re-measure done: **measured at `14b1600` (2026-07-15): MySQL
        222→219 (92.9%), T-SQL 471→467 (85.9%), Oracle 162 flat
        (95.0%). Cumulative: T-SQL 1090→467, MySQL 579→219, Oracle
        454→162.**
        *Wave 25 (2026-07-15):* index-rebuild refinements — PG
        opclasses (`roomno bpchar_ops`, error 35336) strip to the bare
        column; a filtered-index predicate outside T-SQL's restricted
        grammar (arithmetic left sides, error 10735) drops the WHERE
        with a broader-index note on plain indexes and degrades WHOLE
        on UNIQUE ones (a broader unique index would reject rows the
        partial one allowed); the predicate renderer now accepts only
        column-vs-constant comparisons. Tests:
        TestIndexRebuildRefinements. **Measured at `6e74f3f`
        (2026-07-15): T-SQL 490→477 (−13, 85.6%); MySQL 233 / Oracle
        168 flat. Cumulative: T-SQL 1090→477, MySQL 579→233, Oracle
        454→168.**
        Known gaps left open (P2): **MySQL FUNCTION emitter drops
        OUT/INOUT modes silently** for every source (MySQL functions
        can't declare them — needs a warning per no-silent-loss);
        **VARIADIC** parameters still desync (no consume, no carrier);
        array subscripts (`p1[1]`) degrade honestly via the output gate. Getting here surfaced and
        fixed THREE product bugs: the sqlglot COPY DoS (`:'var'`,
        `3aa55b4`), the transactional-BEGIN splitter glue (also under the
        output gate), and the oracle first-boot healthcheck wait.

- [x] **MySQL-source validity sweep over the private local corpus — DONE
      2026-07-15/17** (M1–M6 plus waves through 91; standing in §3:
      mysql→{tsql 166, pg 107, oracle 129}, all ≥97.2%). Original (P2,
      2026-07-15): A privately-prepared mysql-source corpus now exists under
      the gitignored `fixtures-corpus/` (local-only material; per policy its
      provenance is not documented here — see the private prep script next to
      it). Pending: a mysql variant of `scripts/filter_valid_source.py` (the
      current one is PG-only) to get an honest denominator, then per-direction
      sweeps mysql→{pg,oracle,tsql} joining the wave cadence.

## 4. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

- [x] **Nightly mutation floors under water since 2026-07-09 — RECOVERED
  2026-07-16** (nightly run at `17de248` green: all floors passing with
  the wave-file selections + survivor-targeted assertions). Original
  finding (P2; user flagged 2026-07-15): convert.py 60% < 65, emit.py 53% < 60,
  procedural base.py 51% < 52. Root cause: the M-era + wave code landed
  with its tests in `tests/integration/test_pg_source_wave1.py`, which
  the nightly's `--tests` selections did NOT include — every mutant in
  the new paths survived by construction. Fixed the selection (wave
  file added to BOTH mutation steps, 2026-07-15; local 60-mutant sample
  on emit.py: 53%→58%). Validation dispatch (2026-07-15 evening):
  convert.py recovered its floor; emit.py 56% and procedural base.py 51%
  still short → survivor-targeted assertions added
  (`test_emit_mutation_survivors.py`: CTE-DML gate branches, index-
  rebuild decisions, per-target DEFAULT rewrites;
  `test_transformer_survivors.py`: trigger timing/delegation/UPDATE-OF
  decisions). Local 80–100-mutant samples after: emit.py 65% (floor
  60), base.py 61% (floor 52). Second validation dispatch pending —
  possible live-check item spotted on the way: MySQL `DEFAULT UUID()`
  emits WITHOUT the parens MySQL requires for function defaults
  (verify against live MySQL; the `(UUID())` rewrite exists but a
  different path emits).
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
