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

- [ ] **Residual invalid output ships WITHOUT a warning (P1, analyzed
      2026-07-17).** The archived wave campaign left ~550 statements
      across the six directions that the live engines reject; behavior
      audit of pg→tsql's 163: **21 are VERBATIM passthroughs of the
      source SQL with ZERO warnings** (e.g. `SELECT CORR(b, a)` — CORR
      is a known-foreign builtin deliberately left visible, but
      silently; `ALTER TABLE … SET (parallel_workers = 4)` — a PG
      storage knob shipped raw), and 142 are transformed-but-invalid
      forms that pass the sqlglot-based output gate because sqlglot is
      more lenient than the real engines. Neither violates data, but
      both violate the no-silent-loss policy: invalid output must
      carry a warning or degrade to a carrier. **Treatment design
      (three mechanisms, ordered by cost):**
      1. *Unmapped-construct note (LANDED 2026-07-17, wave 103):*
         a RawSQL whose reason is `unmapped operator X` emitted
         cross-dialect now carries an inline `/* UNIQUE: … no
         <target> mapping — review */` note (covers CORR & friends —
         they arrive as unmapped-operator RawSQL, not FunctionCall).
         A FunctionCall-level note was tried and REVERTED: it broke
         the downstream text handlers that consume that output
         (TRUNC→ROUND on the M4 path) — the M3 lesson; rewrite passes
         that fix a construct must also CLEAR the stale reason
         (charset strip updated). Tests: TestForeignBuiltinNote. Verified at
         `fd2923f`: validity identical {163/131/89}, notes visible
         in output. Mechanisms 2–3 below remain open.
      2. *Verbatim-fallback warning — VERIFIED ALREADY COVERED
         (2026-07-17):* the DML parse-fallback path already carriers
         + warns (probe: `SELECT 1 INTO STRICT v` → carrier with
         warning). The probe instead exposed a silent-MANGLE class:
         PG's `TABLE name` shorthand shipped as `[TABLE] AS onek`
         (wave 104 fixed it — pre-normalized to `SELECT * FROM
         name`). The remaining silent classes are all
         sqlglot-leniency escapes → mechanism 3. (Wave 104 verified
         at `b400247`: validity flat, mangle gone.)
      3. *Live output validation, opt-in — LANDED 2026-07-17
         (wave 105):* `TranspileOptions.validate_live_url` +
         `core/live_validate.py`. Side-effect free per engine (T-SQL
         PARSEONLY, PG savepoints, MySQL throwaway DB; Oracle raises
         UnsupportedLiveValidationError — no side-effect-free channel
         without DBA rights). Applies the SWEEP'S classification:
         only syntax-class engine errors degrade (environmental
         missing-table errors on the validation DB must not carrier
         good SQL). Smoke-verified against live PG: syntax rejects
         carrier with the engine's error + a `live_validation`
         warning; environmental pass untouched. Oracle channel via
         `DBMS_SQL.PARSE` (syntax+semantics, no execute) added
         2026-07-17 — DML/SELECT only; DDL skipped (Oracle runs DDL
         at parse). **BLIND SPOT (user, 2026-07-17): live validation
         catches INVALID output, NOT silent data loss — a statement
         that dropped a clause/arm/row but stays syntactically valid
         PASSES (wave 85 class). It is NEVER the sole check; it
         complements the no-silent-loss gates, differential audits,
         and review of what each degrade drops.** Tests:
         TestLiveOutputValidation (env-gated). **Live-in-sweep gap
         discovery (user, 2026-07-17): a discovery script ran the
         corpus through the Transpiler + live PG validation, keeping
         only statements the ENGINE rejects that shipped with NO
         carrier/warning — 58 silent gaps. Top: `CAST(… AS ARRAY)`
         (11x — a PG array-type cast `'{…}'::float8[]` collapsed to
         a bare ARRAY, invalid even PG→PG; wave 106 preserves the
         array type and widens the array gate to Oracle, excluding
         WITHIN GROUP which Oracle supports). The discovery tool is committed
         (`scripts/discover_silent_gaps.py`) — MUST use the
         dollar-quote-aware splitter (a naive `;\n` split shreds
         plpgsql bodies into false-positive `return …` fragments —
         verified). Proper run over the whole corpus (5196 stmts):
         **287 silent gaps**. Wave 107 fixed the worst — a genuine
         SILENT DATA LOSS the live check exposed: `CREATE TABLE x
         (LIKE y)` (LIKE inside the column parens) dropped its LIKE
         entirely → empty `CREATE TABLE x` (the LikeProperty lands in
         the schema, not properties; now harvested from both).
         Remaining tail: `ARRAY(...)` constructor (9x, distinct from
         the cast), VARIADIC ARRAY, PERCENTILE_*(ARRAY …) — genuine
         array constructs with no non-PG spelling (degrade candidates
         for a future wave). Wave 108 (2026-07-16) closed that tail
         and found it was worse than a degrade gap — the IR had NO
         array model, one class, three defects: (a) sqlglot stores PG
         subscripts 0-BASED and the unhandled-expression RawSQL
         fallback rendered with NO dialect, so `arr[2]` shipped as
         `arr[1]` — silent data corruption, and on pg→tsql it even
         passed the validity gate (brackets parse as a quoted
         identifier) with ZERO warnings; (b) `ARRAY[…]` collapsed to a
         generic FunctionCall emitted `ARRAY(1, 2, 3)` — invalid even
         on PG; (c) the ARRAY(SELECT …) carrier leaked the IR repr
         instead of SQL. Fixes: `ArrayLiteral` IR node (PG emits
         `ARRAY[…]`/`ARRAY(SELECT …)` faithfully), ALL converter
         RawSQL fallbacks now render in the SOURCE dialect
         (`_source_sql`: unhandled expr, complex EXISTS/subquery,
         unmodeled INSERT body, unhandled CREATE, unmapped operator),
         and the array gate recognizes the node, subscripts
         (Bracket-RawSQL), and any RawSQL fragment carrying `ARRAY[`
         (neighbor probe caught `= ANY(ARRAY[…])` escaping via the
         unmapped-operator path; a WITHIN GROUP fragment with an
         ARRAY arg now degrades on oracle too, plain WITHIN GROUP
         stays). Tests: TestArrayModelFidelity (18). Measured
         (whole-corpus discovery, working tree over `f3c07d9`):
         **287 → 226 silent gaps (−61)**. Next-wave candidates from
         the new top classes (all silent-loss shapes): set-returning
         function dropped from FROM in LATERAL contexts (`FROM
         generate_series(…) s1` → `FROM  s1`), `DROP TRIGGER … ON
         table` losing the ON clause, CTAS over a parenthesized UNION
         subquery truncating (`syntax error at end of input`, 99x),
         and — verified distinct from this wave's DML class — the
         PROCEDURAL pipeline shreds plpgsql array-typed declares
         pg→pg (`a integer[] = '{…}'` → `a integer;` + garbage `[]
         =;` line; `RETURNS SETOF integer[]` silently narrows to
         `SETOF integer`) — the pg→pg preservation counterpart of
         wave 86's off-PG degrade (6x, the remaining `"["` gaps).
         Wave 108b: the live FE suite caught a wave-108 REGRESSION —
         source-dialect fallback rendering is wrong INSIDE procedural
         bodies, where embedded text is mid-transform (variables
         already `@`-rewritten): a postgres render turned
         `@p_customer_id` into the invalid `$p_customer_id` on
         T-SQL. `IR_EMBEDDED` ContextVar (set around
         `_ir_transpile_dml`) keeps the generic rendering there;
         top-level parses stay source-spelled. All 16 FE pairs
         re-verified live-green. Lesson for the structural list: a
         "render faithfully to the source" rule only holds where the
         text IS source — the procedural pipeline's embedded text is
         a hybrid. Tests: TestEmbeddedFallbackSpelling. Wave 109
         (2026-07-16): `DROP TRIGGER name ON tbl` lost its mandatory
         ON even pg→pg (sqlglot parks it in the unread `cluster` arg
         — the DROP INDEX lesson again); now harvested for TRIGGER
         too, PG emits it, and the inverse neighbor (tsql/mysql/
         oracle sources are schema-scoped, no table to carry)
         degrades to the documented carrier instead of shipping
         invalid PG silently. Known honest limit: `ON schema.tbl`
         doesn't parse in sqlglot (carrier + warning, not silent).
         Tests: TestDropTriggerOnTable (7). Measured: **226 → 156
         silent gaps (−70)** (working tree over `45edfa2`; the
         DROP TRIGGERs were most of the 99x end-of-input class).
         Remaining top classes: FROM-position set-returning function
         dropped (`FROM generate_series(…) g` → `FROM g`, the
         biggest remaining silent DATA LOSS — needs a
         function-relation model in the IR, fresh-session scale),
         psql client-side leftovers (25x near ":"), `WITH ins AS
         (INSERT … RETURNING)` mangled to `SELECT *` (14x), plpgsql
         array-typed declare shred (6x, above).**
         **Scope decision
         (user, 2026-07-17): live validation is a CODE-REFINEMENT
         tool only — used by the sweeps/tuning loops to find mapping
         gaps. It is deliberately NOT exposed in the CLI or the API
         (an end-user feature that needs a live engine to produce
         correct output would be a botch); `validate_live_url` stays
         a development-facing option.**

### P2 — correctness of signals and validation

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

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
      TestNationalStringConcat; verification cycle at `0a0ad03`
      identical {163/131/89}. Family step 4 (error-globals) landed
      2026-07-17 (wave 101): the system globals lived only in the
      procedural maps — a top-level `SELECT @@ROWCOUNT` shipped raw
      off T-SQL. New shared `_map_system_global` in the DML expression
      emit: MySQL gets the real ROW_COUNT(); PG/Oracle top-level get
      a documented neutral (their forms are PL-context only); Oracle's
      `SQL%ROWCOUNT` — which parses as a MODULO — maps at the
      BinaryOp. Tests: TestSystemGlobalsInDml; verification cycle at
      `63e0d31` identical {163/131/89}. Family survey CLOSED
      2026-07-17 (wave 102): @@FETCH_STATUS gets the top-level
      neutral (it is CURSOR-CONTEXTUAL by nature — the procedural
      path maps it with surrounding state: FOUND on pg, handler
      flags on mysql, cursor%FOUND on oracle; a context-free IR
      mapping is impossible today). DESIGN CONCLUSIONS for M3 final:
      (a) the IR expression pipeline must RECEIVE procedural context
      (cursor state, like STRING_VARIABLES) before fetch idioms can
      migrate; (b) in-expression COMMENTS need comment-carrying
      expression nodes in the IR (they are dropped today) — both are
      the remaining preconditions for deleting the text rewriters.
      Tests: TestFetchStatusTopLevel; verification at `2a2dc90`
      identical {163/131/89}.*; then the text rewriters can
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
### P1 — private-fixture live sweep (audit doc 03; anonymized repros there)

Found by transpiling the three `fixtures-private/` scripts across the matrix
and executing the outputs on the real engines. Ordered by attack value; every
fix needs an **anonymized** regression fixture (never a private name).

### P3 — hardening carry-overs (from 2026-07-02, still open)

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
## 3. Test-corpus expansion (P3)

- Corpus wave campaign **COMPLETED and archived** (2026-07-15 →
  2026-07-17, waves 4–95; full per-wave log with measured commit
  hashes in `docs/DONE.md`, section "Wave campaign — corpus
  validity"; waves 96–102 are the M3-prereq/M3b record kept in the
  §2 M3 item). Final standings at `3fdfc88`:
  - pg-source (PostgreSQL regression corpus,
    `fixtures-corpus/pg_corpus_valid.sql`): →T-SQL **163** syntax
    failures (95.0% validity), →MySQL **131** (95.7%), →Oracle **89**
    (97.2%).
  - mysql-source (private local corpus, provenance undocumented by
    policy): →T-SQL **166** (97.2%), →PG **107** (98.2%), →Oracle
    **129** (97.8%).
  - Both residues are at the deep-singles floor (a full measure cycle
    buys ~−1); do not resume waves on these corpora without a new
    corpus or a fidelity target.

## 4. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

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
