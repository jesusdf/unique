# Unique — Pending Work

This document tracks **outstanding** work only, ordered by priority. Completed
backlog sections move to [`docs/MILESTONES.md`](MILESTONES.md) (closing
summaries) with the detailed why/how of each fix archived in
[`docs/DONE.md`](DONE.md); `docs/STATUS.md` summarizes the project state at a
higher level.

Last reviewed: 2026-07-30.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## Discrete backlog

*Everything approved on 2026-07-30 is executed — campaign (MILESTONES), B29–B33, T8, F1/F2, Q2 (DONE §48–49 + milestones). The 2026-07-24 audit backlog, the findings it surfaced, and the B28 features
are ALL closed — see [`docs/MILESTONES.md`](MILESTONES.md) and
[`docs/DONE.md`](DONE.md) §44–§47. Both maintainer decisions are resolved:
`or_replace` on views kept and documented (2026-07-29, DONE §46); the sqlglot
CASCADED-hang closed by the 30.14.0 upgrade — fixed upstream (2026-07-30,
DONE §47).*

### Q1 — oracle/mysql-source procedural degrades — TRIAGED, briefs ready (P2)

*Triage report: [`audit/2026-07-30-q1-triage.md`](../audit/2026-07-30-q1-triage.md)
(fresh measurement: actionable gap = 28/32 oracle→pg, 21/31 mysql→pg; two of
the top mechanisms are transpiler BUGS, not degrades). Brief order by
routines-unblocked and severity:*

- **B34** — UNIQUE-1171 false positive: `_find_user_var` scans `@name` in raw
  text without scrubbing comments (transformer.py:1897) → ~11 mysql routines.
- **B35** — UNIQUE-1219 SET-var misclassification CORRUPTS output (closes the
  `$$` body early, leaks statements as top-level SQL) — severity-first.
- ~~B36~~ — DONE 2026-07-31 (3 of 4 causes): oracle→pg 1151 count 16 → 2.
  SYS_REFCURSOR type map, FROM-DUAL tail strip in SELECT INTO,
  NUMTODSINTERVAL/NUMTOYMINTERVAL → PG interval (both pipelines; 3 challenge
  cases lifted to faithful). Cause 3 became B37b below.
- **B37b** — extend B37's GET DIAGNOSTICS hoist to be spelling-general:
  consume MySQL `ROW_COUNT()` (`_ROWCOUNT_FN_PATTERN`, `_expr.py:149`) →
  clears the 8 remaining mysql→pg 1151 routines; ALSO fixes the latent
  tsql→pg `@@ROWCOUNT`→bare-`ROW_COUNT` silent-invalid substitution
  (`procedural/transformer/postgresql.py:38`).
- **B36b** — two more unmapped-builtin gaps surfaced out-of-brief: mysql
  `UNIX_TIMESTAMP()` (func2) and oracle `RAWTOHEX`/`STANDARD_HASH` (func4).
- ~~B37~~ — DONE 2026-07-31: expression-position hoist with honest re-evaluated-condition degrade; corpus 1033 count 8 → 0.
- **B38** — UNIQUE-1170 temp-table parse giveup: isolate before briefing. ALSO: `_split_generic` (batch_splitter.py ~663) shares the CASE-uncounted depth asymmetry B35 fixed in `_split_mysql` — a DELIMITER-less PL/SQL body with a CASE expression could tear the same way (flagged 2026-07-31, not yet reproduced).
- **B39** — 1230/1231 placeholder-code fidelity (quality, not coverage).

---

### A10 — functional-equivalence coverage audit (P2; after the docs-gap wave)

*Maintainer suspicion (2026-07-31, shared by the architect): the FE
execution-comparison layer is far greener than the corpus. Today the nightly
result-diff covers the curated FUNC_CASES (~12) plus the `[class=func]`
challenge cases; the other ~900 corpus cases and the procedures corpus have
parse/structural assertions only — "runs and returns the same result set" is
unproven for most of what the transpiler claims to convert.*

- **Audit shape:** measure the executable-comparable fraction per direction
  (a case is FE-comparable if deterministic, self-contained or probe-able —
  the `is_comparable` predicate exists in `tests/helpers/corpus_diff.py`);
  enumerate what's excluded and WHY (nondeterministic, session-dependent,
  DDL-only, needs setup data); then drive the comparable-but-uncompared set
  toward the nightly harness (auto-enroll like `[class=func]` does, probes
  for state-mutating cases per `test_challenge_live.FuncCase`).
- **Ratchet:** a counted floor of comparable-but-unenrolled cases that only
  goes down; nightly wall-time budget respected (batch/sample if needed —
  but say so, no silent caps).
- **Procedures corpus:** the 4-dialect same-routine fixtures are
  execution-comparable by construction (call each, compare effects) — today
  only live-VALIDATED (compiles), not live-COMPARED. Highest-value gap.

## Continuously tracked (not a discrete backlog)

- Challenge corpus (`tests/fixtures/challenge/`) remains the live intake for
  new RED findings — new batches follow the class/points rules in
  [`skills/SKILL-challenge-corpus.md`](../skills/SKILL-challenge-corpus.md)
  and are scored by `scripts/challenge_stats.py`.
- The first nightly runs at this HEAD will demand mutation-floor raises
  (`mutation.yml` self-ratcheting stale check) — apply them with the real
  full-run numbers.
- Oracle-source Tier-1 promotion still wants a second real corpus
  (`docs/STATUS.md` direction tiers).

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
