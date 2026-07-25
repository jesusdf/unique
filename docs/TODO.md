# Unique — Pending Work

This document tracks **outstanding** work only, ordered by priority. Completed
backlog sections move to [`docs/MILESTONES.md`](MILESTONES.md) (closing
summaries) with the detailed why/how of each fix archived in
[`docs/DONE.md`](DONE.md); `docs/STATUS.md` summarizes the project state at a
higher level.

Last reviewed: 2026-07-24.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## Discrete backlog — 2026-07-24 audit (`audit/2026-07-24/`)

Every item below has a **pre-analyzed fix brief** in
[`audit/2026-07-24/09-fix-briefs.md`](../audit/2026-07-24/09-fix-briefs.md)
(verified root cause, chosen approach, tests-first, acceptance criteria) —
**start from the brief, not from scratch.** Process rules for this backlog:
[`audit/2026-07-24/08-prevention-plan.md`](../audit/2026-07-24/08-prevention-plan.md).
Findings detail: audit docs 02/04/05/07.

### P1

- [x] **B3** Confidentiality remediation at HEAD — done 2026-07-24: renamed all
  private vocabulary to verified-synthetic names in the 7 flagged files (plus 2
  residues the fix sweep itself caught), reworded the 2 `docs/DONE.md`
  passages, and moved the fixture anonymization guard's fragment list to an
  untracked `fixtures-private/leak_fragments.txt` (guard skips when absent).
  Diff swept against the full 24,923-token private inventory: 0 hits.
  Maintainer decided: **no history rewrite** — the 2 commit-message hits are
  accepted residual risk.
- [x] **B2** Unread-args tripwire (T1), warn-mode first — the mechanical guard
  for the N1/N3/N4 class. Done: read-tracking wrapper at the converter dispatch
  (`converter/_unread_args.py` + `convert.py`), env `UNIQUE_UNREAD_ARGS=
  off|warn|gate` (default warn), empirical 3-entry allowlist (Concat.safe,
  Create.properties, Introducer.this), `scripts/unread_args_sweep.py --sweep`,
  and `tests/unit/core/test_unread_args.py` (the fixture-corpus-clean test is
  the CI ratchet). N1's `Insert.conflict` now warns pre-B1.
- [x] **B1** Model the upsert clause (`ON CONFLICT`/`ON DUPLICATE KEY UPDATE`)
  — audit N1, the headline S1: upserts silently become plain INSERTs in every
  direction. **Done:** `OnConflictClause`/`ExcludedColumn` IR on
  `InsertStatement`; converted from `exp.OnConflict`/`Insert.ignore`; emitted
  native PG⟷MySQL and lowered to a MERGE for T-SQL/Oracle; MySQL-source keys
  taken from a new PK/UNIQUE harvest, else the whole statement degrades warned;
  any-key + `INSERT IGNORE` divergences annotated. Also extended: `INSERT
  IGNORE` (DO NOTHING class). Covered by `tests/unit/core/test_upsert.py` +
  `TestInsertSelectConflict` in `test_challenge.py`; live FE value test on all
  four engines (DO UPDATE and DO NOTHING). Corpus case `pg-insert-select-conflict`
  made scenario-adequate (PK + pre-seeded conflict).
- [x] **B4/B5/B6** MERGE semantic series (one series, `converter/emit.py`
  `_merge_extended_clauses` + `_merge_carve_do_nothing`, and the OUTPUT path in
  `transpiler/_core.py`) — done 2026-07-24: **B4** Oracle conditional-DELETE
  fold now carries a safety predicate (`_merge_delete_reads_updated`): folds
  only when the DELETE condition reads no UPDATE-assigned target column, else
  degrades warned (live: SQL Server `{(2,7)}` == Oracle for the safe shape; the
  N2 unsafe shape now carries instead of returning `{}`). **B5** `OUTPUT` on a
  MERGE → PostgreSQL degrades to the existing "no standalone OUTPUT/RETURNING"
  carrier + warning (never re-attaches the tail to a follow-up statement or a
  comment); plain INSERT/UPDATE/DELETE OUTPUT → PG still returns. **B6** PG
  `THEN DO NOTHING` → T-SQL/Oracle lowered by clause carve-out (negated
  condition ANDed onto later same-kind clauses; unknown `Var` action degrades
  warned) — live three-engine equality `{(1,5),(2,7),(3,9)}`. Tests:
  `test_challenge.py::TestMerge{ConditionalDeleteFoldSafety,OutputToPostgres,
  DoNothingCarveOut}`; `ts-merge-full` corpus case stays green;
  `docs/03-unsupported.md` §3.6 documents the three degrades.

### P2

- [x] **B10** Running COLUMN_TYPES harvest + T-SQL `ALTER COLUMN` nullability
  (N9 — silent type revert / dropped NOT NULL) — done 2026-07-25: the
  COLUMN_TYPES map (plus a new COLUMN_NOT_NULL companion seeded by
  `harvest_column_not_null`) is now a running scan folded in statement order
  (`fold_alter_into_running_types` in `converter/harvest.py`: ALTER/MODIFY …
  TYPE, ADD COLUMN, RENAME COLUMN, DROP/SET NOT NULL; MySQL MODIFY resets
  nullability unless restated), and the T-SQL `ALTER COLUMN <c> <type>`
  emission re-states the column's known nullability (NOT NULL/NULL), warning
  when the script never defined the column — the USING-redundant-cast strip
  routes through the same helper. Live-verified: SQL Server end state
  (bigint, is_nullable) matches PG's for the N9 script and the ADD COLUMN
  fold. Tests: `test_harvest_running_columns.py`,
  `test_pg_source_wave1.py::TestB10RunningColumnTypeAlterNullability`.
- [x] **B7** Per-cursor status emulation class fix (N5+N6: duplicate MySQL
  labels, stale NOT-FOUND flag, global `@@FETCH_STATUS`, `%ISOPEN` as modulo) —
  done: per-cursor `@uq_<c>_fs`/`v_uq_<c>_done` fetch-status flags captured
  beside each FETCH, per-cursor `%ISOPEN` open flags, unique `loop_lbl_<n>`
  labels (emitter-base counter + label stack), unmapped `%<attr>` hits the
  warned carrier gate. `_emulate_cursor_state` generalizes the `%ROWCOUNT`
  pass; live-verified nested (MySQL, all parents processed) + interleaved
  (T-SQL == Oracle row count) in `tests/integration/test_cursor_state_b7.py`;
  docs 03 §3.23 + compat matrix updated.
- [x] **B8** PG `SET TRANSACTION … READ ONLY` access-mode mapping (N7) — done
  2026-07-25; `batch_splitter.classify_batch` routes the statement to the DML
  pipeline (like Oracle's equivalent already did) instead of the SET-option
  comment-out fallback, `convert.py` models it as a `PassthroughSQL` carrying
  the original text (`kind="SET TRANSACTION MODE"`), and `emit.py` extends
  the BEGIN-TRANSACTION access-mode table: MySQL comma-joins the
  characteristics, T-SQL keeps the isolation-level statement and drops the
  access mode with a `UNIQUE:` warning, Oracle prefers the access mode (or
  keeps the existing READ-COMMITTED no-op note). Live-verified on
  SQL Server + MySQL (`pymssql`/`pymysql`); Oracle spot-checked via
  `DBMS_SQL.PARSE`. Tests: `test_pg_source_wave1.py::TestPgSetTransactionAccessMode`.
- [x] **B9** T-SQL money literal `$12.50` mangle intercept + garbage-shape
  guard (N8) — done 2026-07-25; `convert.py` rebuilds sqlglot's
  `Column(this=Literal, table=Identifier($…))` (and the whole-dollar
  `Column(this=Identifier($…))` no-dot form) into the numeric literal on
  T-SQL source, gated to unquoted `$`-shaped identifiers only (a quoted
  `"$12".50` is already-invalid T-SQL, not the shorthand, and is left
  untouched); `validation.py` flags the identical shape as invalid input on
  Oracle/MySQL source, which have no money-literal syntax. Live-verified
  12.50/0.5/100 on pg/oracle/mysql. Tests:
  `test_challenge.py::TestMoneyLiteralMangle`,
  `test_validation.py::TestBareAndTypoStatements::test_dollar_money_*`.
- [x] **B11** Dynamic-SQL constant strings routed through the transpiler, warn
  otherwise (N10) — done 2026-07-25; a constant string reaching an
  `EXEC`/`sp_executesql`/`EXEC(...)`/`EXECUTE [IMMEDIATE]` sink (literal
  argument, or a variable whose single assignment is a constant literal that
  parses as one source-dialect statement) is translated through the real
  embedded-DML pipeline and spliced back (`procedural/transformer/base.py`:
  `_collect_dynamic_sql_vars` pre-scan at every routine entry +
  `_maybe_translate_dynamic_sink` at `_transform_execute` +
  `_dyn_sql_value_replacement` at declare/SET/assignment sites); non-constant
  variables, non-SQL strings, and multi-statement strings get the
  "review the dynamic SQL" warning (never silent); recursion capped at depth 2
  via the `_EMBEDDED_DYN_SQL_DEPTH` ContextVar. Parameterized sinks
  (`USING`/sp_executesql binds) keep the established placeholder handling —
  translating them statically would mangle the target's placeholder spelling
  (`$1`→`?` etc.); statically translating the non-placeholder content of a
  parameterized constant string is a possible follow-up. Live-verified: the
  N10 pair (literal + variable) creates, compiles VALID, and executes on
  PG and Oracle. Tests: `test_dynamic_sql_constant.py` (translation both
  targets, warning paths, round-trip, depth cap, parameterized regression).
- [x] **B12** `SQL%ROWCOUNT`→MySQL annotated divergence (N11, §3.22 class) —
  done 2026-07-25; kept the mapping (no faithful emulation exists) and added
  a `UNIQUE:` note + deduplicated warning at both emission sites
  (`procedural/transformer/mysql.py::_map_cursor_attributes` for Oracle's
  implicit-cursor `SQL%ROWCOUNT`, `transformer/base.py::_transform_get_
  diagnostics`'s `_DIAG_ITEMS["mysql"]["ROW_COUNT"]` entry for PostgreSQL's
  `GET DIAGNOSTICS x = ROW_COUNT`); T-SQL `@@ROWCOUNT` stays unannotated
  (matched-rows, verified equivalent). Live-verified on MySQL: an UPDATE
  re-asserting an unchanged value returns `ROW_COUNT()=0` where the source's
  matched-rows semantics return 1. Tests:
  `test_challenge.py::TestRowcountDivergenceAnnotation`.
- [x] **B13** Carriers preserve the ORIGINAL statement text, never a hybrid
  re-render (N12) + carrier-body-parses-as-source assertion — done
  2026-07-25. The parser attaches the original text to each statement node
  (`ASTNode.source_text`; DML: `parse_sql` slices per-statement at tokenizer
  `;` boundaries; procedural: `_transpile_procedural` attaches the batch
  text) and the degrade gates quote it via `_preserved_sql` (both
  pipelines), re-rendering only when no original is attached. The sweep
  caught the procedural sibling (a degraded MySQL routine's carrier said
  `DETERMINISTIC` where the source said `READS SQL DATA`) — same class,
  fixed by the same mechanism. Shared assertion
  `assert_carrier_bodies_parse_as_source` in `tests/helpers/invariants.py`
  (sqlglot parse, procedural-parser fallback for routine bodies), wired
  into `test_real_world.py::TestGenericInvariants` over all 12 directions.
  Tests: `tests/unit/core/test_carrier_original_text.py`.
- [x] **B14** API filename sanitizer `re.ASCII` one-liner (05 A1) — done
  2026-07-24; non-latin-1 filenames return 200 with an ASCII header
  (`test_file_non_ascii_filename_does_not_break_header`).
- [ ] **B15** Re-arm ratchets: identity floor 0.45→0.60 (done — measured
  0.66, margin 6) and stale-floor detector (T7, done —
  `scripts/identity_mutation_check.py` fails with a distinct exit code and
  "floor is stale — raise it" when measured − floor > 0.15). Remaining:
  nightly floors: bump to measured−10 after the first clean nightly at this
  HEAD (owner: next session).
- [ ] **B16** Challenge corpus: target-parse gate (T4) + upgrade the ~362
  loop-only `[fixed]` cases to dedicated assertions (batched campaign).
  Progress 2026-07-25: the 110 PostgreSQL-source `[fixed]` cases that lacked a
  dedicated assertion are now covered in
  `tests/integration/test_challenge_assertions_postgresql.py` (declarative
  `CASES` table + one parametrized runner per foreign target; present-AND-absent
  on comment-stripped output, warn+`UNIQUE:` for degrade-expected targets). 310
  new parametrized rows, all failing under the identity transpiler; identity
  kill rate 66% -> 70%. One `SUSPECT_CASES` entry (`postgresql-drop4-match`
  oracle silently drops MATCH FULL — no-op for a single-column FK, left
  unasserted).   - MySQL-source batch done 2026-07-25: new module
    `tests/integration/test_challenge_assertions_mysql.py` gives every
    uncovered `[fixed]` MySQL case a dedicated per-target present+absent (or
    warned-degrade) assertion — 141 cases / 390 parametrized items, all fail
    under the identity transpiler. Overall identity kill rate 66% -> 71%.
    `SUSPECT_CASES` empty (no silent-loss/invalid found). Remaining: the
    sqlserver/oracle source batches (in progress).
- [ ] **B17** Emitter debt: arm ratchet gates (T3) + complexity lint (T6),
  de-regex the two guardrail violations (F1/F2), split `emit.py` along the
  doc-04 seams.

### P3

- [x] **B18** `scripts/private_leak_check.py` (T2) — done 2026-07-25;
  pre-push confidentiality sweep, local-only. Derives its token inventory at
  runtime from `fixtures-private/` (case-fold, length >= 6, drop SQL
  keywords/this repo's own builtin catalogs/curated English+Spanish
  dictionary words) plus the untracked `leak_fragments.txt` for short/compound
  fragments; checks `origin/main..HEAD` + staged/working-tree diff lines and
  `origin/main..HEAD` commit messages; no-ops when `fixtures-private/` is
  absent. Contains no private data itself. Tests:
  `tests/unit/test_private_leak_check.py` (fake private dir + a real temp git
  repo, 24 cases).
- [x] **B19** `scripts/challenge_stats.py` (T5) — done 2026-07-25; parses
  `-- CASE[status][class=x]:` headers across
  `tests/fixtures/challenge/challenge_*.sql`, reports per-status/per-class/
  per-source counts, and `--batch-since <ref>` scores `[open]` cases added
  since a ref against the challenge skill's A9 rules (points table,
  concentration cap, >= 3 distinct classes; unclassified legacy cases
  excluded from scoring). Pure stdlib. Tests:
  `tests/unit/test_challenge_stats.py` (25 cases, incl. a real temp git repo
  for `--batch-since`).
- [x] **B20–B27** small items — ALL DONE. *(2026-07-24: B22 traceback
  logging via `exc_info`, B26 `.dockerignore`. 2026-07-25: B20 PG `TABLE t`
  validation whitelist (`_is_pg_table_shorthand`); B21 MERGE comment trivia —
  leading standalone comment preserved once, inline comment no longer
  duplicated (`test_merge_comment_trivia.py`); B23 removed the 5
  zero-reference IR node classes and `builtins_for`, hoisted the duplicated
  `_transform_exception_block` to the transformer base; B24
  `scripts/mutation_test.py` mutates a temp copy of `src/` (live-verified
  the real tree stays untouched mid-run); B25 perf budgets measure CPU time
  (+12s northwind margin) — load flake dead; B27 all 5 CI `pip install`
  steps pin to `constraints.txt`.)*
- [ ] **Architect follow-up from B27** (2026-07-25): `constraints.txt` is
  hand-regenerated (`pip install . && pip freeze --exclude-editable`) and
  nothing forces it to stay current now that CI enforces it as an install
  constraint — add a release-checklist line to
  `skills/SKILL-development-workflow.md` ("Releasing" section) to
  regenerate `constraints.txt` (or verify it still resolves cleanly) as
  part of cutting a release, or wire a periodic CI job that does so.
- [ ] **B28** feature briefs when scheduled: `#temp`-in-procedure wiring,
  top-level `BEGIN TRY/CATCH` routing (currently honest warned degrades).
- [x] **RED seeds from the B2 sweep** (2026-07-24): (a) `Create.properties`
  is allowlisted as cosmetic but bundles view modifiers (`WITH CHECK OPTION`,
  `SCHEMABINDING`) the VIEW converter currently drops — probe, and split the
  allowlist if semantic; (b) `INSERT IGNORE` (`Insert.ignore`) — folded into
  B1's scope as the DO NOTHING-class upsert (done). *(Done 2026-07-25: (a)
  `WITH [CASCADED|LOCAL] CHECK OPTION` is modelled pre-parse (sqlglot cannot
  parse it) and re-emitted on every target (unscoped on T-SQL/Oracle);
  non-portable modifiers (SCHEMABINDING, ALGORITHM=, …) are kept on the
  owning engine and warned-dropped elsewhere; the `Create.properties`
  allowlist entry is removed — an unread `properties` warns again.
  `tests/integration/test_create_view_modifiers.py`, live CHECK OPTION
  enforcement verified on MySQL.)*
- [x] **RED seed from B13** (2026-07-25): standalone `JSON_QUERY(x, path)`
  T-SQL→Oracle converts to `JSON_EXTRACT(...)` as *executable* output —
  Oracle has no `JSON_EXTRACT`; probe and route through the per-target JSON
  accessor mapping or degrade warned. *(Done 2026-07-25: tsql/oracle-source
  object extraction emits native `JSON_QUERY` on tsql/oracle and
  `JSONB_PATH_QUERY_FIRST` on PG; MySQL keeps `JSON_EXTRACT`. Live value
  verified on Oracle. `tests/integration/test_json_query_accessor.py`.)*
- [ ] **Maintainer decision — `or_replace` on converted views** (found
  2026-07-25, predates the view-modifier work): `_convert_create_view` sets
  `or_replace = expr.args.get("replace") is not None`, but sqlglot stores
  `replace=False` for a plain CREATE — so EVERY converted view emits
  `CREATE OR REPLACE` (`OR ALTER` on tsql). Migration-friendly but a silent
  semantic change (a plain CREATE errors on an existing view; OR REPLACE
  overwrites it). Decide: keep as a documented idempotency feature (add the
  03-unsupported note + annotation) or fix to `bool(...)` and re-bless the
  affected corpus/tests.
- [ ] **sqlglot hang note** (2026-07-25): sqlglot 30.x's parse-error
  highlighter hangs (infinite) on `WITH CASCADED CHECK OPTION` under the
  `oracle` reader at `ErrorLevel.RAISE`. Our pre-parse hook now strips the
  clause first, but if raw user input can ever reach a RAISE-parse on the
  oracle reader, guard it (timeout or pre-strip) — and consider reporting
  upstream.
- [ ] **RED seed from B17b** (2026-07-25): `SELECT 2||3` Oracle→PostgreSQL
  emits bare `2 || 3` — PG rejects `integer || integer` (Oracle implicitly
  casts to varchar and returns '23'). Needs an operand cast
  (`2::text || 3::text`) or CONCAT() on PG when both operands are numeric.
  Excluded from the nightly FUNC_CASES until fixed (`ora-num-concat`).
- [ ] **B17 follow-ups** (2026-07-25): (c-remaining) the ~362 loop-only
  challenge `[fixed]` cases upgrade campaign (B16 step 2) — mysql+postgresql
  modules in progress 2026-07-25.
  - [x] **(a)** seam namespace injection → explicit tail imports, mypy strict
    restored on the 4 seam modules (no overrides), emit floor 3721→3718 —
    done 2026-07-25.
  - [x] **(b)** B16's 4-entry `XFAIL_TARGET_PARSE` triage — resolved on
    principle 2026-07-25: each case transpiled and its output EXECUTED on the
    live target engine (Oracle 23ai / SQL Server 2022 / PostgreSQL 16). All
    four ran clean, so all four are sqlglot-parser gaps on VALID SQL, not
    product defects. Moved to a `VALID_BUT_SQLGLOT_UNPARSEABLE` allowlist in
    `tests/integration/test_challenge.py`, each carrying its live-verification
    evidence; the empty `XFAIL_TARGET_PARSE` dict was deleted.
  - [x] **(c-nightly)** nightly live-execution job for challenge func-class
    cases — done 2026-07-25: `.github/workflows/challenge-live.yml` (nightly
    cron + workflow_dispatch, all four engines via ci.yaml's service-container
    pattern) runs `tests/integration/test_challenge_live.py`, which executes
    each curated FUNC_CASES entry (11 semantic cases: int/decimal division,
    numeric-string arithmetic, concat-vs-NULL, safe CAST, ON CONFLICT upsert,
    full MERGE fold) plus any `[class=func]`-tagged `[fixed]` case on its source
    engine vs the transpiled output on each target and diffs result sets
    (reusing `corpus_diff.normalize_rows`). Skips per case when the
    `UNIQUE_TEST_*_URL` env vars are absent. Live-verified 33 pass / 33 skip
    offline.

---

## Continuously tracked (not a discrete backlog)

- Challenge corpus (`tests/fixtures/challenge/`) remains the live intake for
  new RED findings — new batches follow the class/points rules in
  [`skills/SKILL-challenge-corpus.md`](../skills/SKILL-challenge-corpus.md).

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
