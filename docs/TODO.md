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

- [ ] **B10** Running COLUMN_TYPES harvest + T-SQL `ALTER COLUMN` nullability
  (N9 — silent type revert / dropped NOT NULL); shares harvest work with B1.
- [x] **B7** Per-cursor status emulation class fix (N5+N6: duplicate MySQL
  labels, stale NOT-FOUND flag, global `@@FETCH_STATUS`, `%ISOPEN` as modulo) —
  done: per-cursor `@uq_<c>_fs`/`v_uq_<c>_done` fetch-status flags captured
  beside each FETCH, per-cursor `%ISOPEN` open flags, unique `loop_lbl_<n>`
  labels (emitter-base counter + label stack), unmapped `%<attr>` hits the
  warned carrier gate. `_emulate_cursor_state` generalizes the `%ROWCOUNT`
  pass; live-verified nested (MySQL, all parents processed) + interleaved
  (T-SQL == Oracle row count) in `tests/integration/test_cursor_state_b7.py`;
  docs 03 §3.23 + compat matrix updated.
- [ ] **B8** PG `SET TRANSACTION … READ ONLY` access-mode mapping (N7).
- [ ] **B9** T-SQL money literal `$12.50` mangle intercept + garbage-shape
  guard (N8).
- [ ] **B11** Dynamic-SQL constant strings routed through the transpiler, warn
  otherwise (N10).
- [ ] **B12** `SQL%ROWCOUNT`→MySQL annotated divergence (N11, §3.22 class).
- [ ] **B13** Carriers preserve the ORIGINAL statement text, never a hybrid
  re-render (N12) + carrier-body-parses-as-source assertion.
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
- [ ] **B17** Emitter debt: arm ratchet gates (T3) + complexity lint (T6),
  de-regex the two guardrail violations (F1/F2), split `emit.py` along the
  doc-04 seams.

### P3

- [ ] **B18** `scripts/private_leak_check.py` (T2) — pre-push confidentiality
  sweep, local-only.
- [ ] **B19** `scripts/challenge_stats.py` (T5) — class distribution + batch
  scoring for the challenge corpus.
- [ ] **B20–B27** small items: PG `TABLE t` validation false positive, MERGE
  comment trivia, dead IR nodes, mutation-script isolation, perf-budget flake
  (process_time), CI installs with `-c constraints.txt`. *(Done 2026-07-24:
  B22 traceback logging via `exc_info`, B26 `.dockerignore`.)*
- [ ] **B28** feature briefs when scheduled: `#temp`-in-procedure wiring,
  top-level `BEGIN TRY/CATCH` routing (currently honest warned degrades).
- [ ] **RED seeds from the B2 sweep** (2026-07-24): (a) `Create.properties`
  is allowlisted as cosmetic but bundles view modifiers (`WITH CHECK OPTION`,
  `SCHEMABINDING`) the VIEW converter currently drops — probe, and split the
  allowlist if semantic; (b) `INSERT IGNORE` (`Insert.ignore`) — folded into
  B1's scope as the DO NOTHING-class upsert.

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
