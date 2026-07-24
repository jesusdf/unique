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

- [ ] **B3** Confidentiality remediation at HEAD — rename private vocabulary in
  7 files + reword 2 `docs/DONE.md` lines (audit doc 07; hit list in the
  maintainer's local scratchpad). Maintainer decided 2026-07-24: **no history
  rewrite** — the 2 commit-message hits are accepted residual risk.
- [ ] **B2** Unread-args tripwire (T1), warn-mode first — the mechanical guard
  for the N1/N3/N4 class.
- [ ] **B1** Model the upsert clause (`ON CONFLICT`/`ON DUPLICATE KEY UPDATE`)
  — audit N1, the headline S1: upserts silently become plain INSERTs in every
  direction.
- [ ] **B4/B5/B6** MERGE semantic series (one PR series, same function):
  Oracle `DELETE WHERE` post-update evaluation (N2), `OUTPUT`→PG invalid or
  mis-attached RETURNING (N3), PG `THEN DO NOTHING` passthrough (N4).

### P2

- [ ] **B10** Running COLUMN_TYPES harvest + T-SQL `ALTER COLUMN` nullability
  (N9 — silent type revert / dropped NOT NULL); shares harvest work with B1.
- [ ] **B7** Per-cursor status emulation class fix (N5+N6: duplicate MySQL
  labels, stale NOT-FOUND flag, global `@@FETCH_STATUS`, `%ISOPEN` as modulo).
- [ ] **B8** PG `SET TRANSACTION … READ ONLY` access-mode mapping (N7).
- [ ] **B9** T-SQL money literal `$12.50` mangle intercept + garbage-shape
  guard (N8).
- [ ] **B11** Dynamic-SQL constant strings routed through the transpiler, warn
  otherwise (N10).
- [ ] **B12** `SQL%ROWCOUNT`→MySQL annotated divergence (N11, §3.22 class).
- [ ] **B13** Carriers preserve the ORIGINAL statement text, never a hybrid
  re-render (N12) + carrier-body-parses-as-source assertion.
- [ ] **B14** API filename sanitizer `re.ASCII` one-liner (05 A1).
- [ ] **B15** Re-arm ratchets: identity floor 0.45→0.60, nightly mutation
  floors, stale-floor detector (T7).
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
  comment trivia, `KeyError('into')` traceback logging, dead IR nodes,
  mutation-script isolation, perf-budget flake (process_time), `.dockerignore`,
  CI installs with `-c constraints.txt`.
- [ ] **B28** feature briefs when scheduled: `#temp`-in-procedure wiring,
  top-level `BEGIN TRY/CATCH` routing (currently honest warned degrades).

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
