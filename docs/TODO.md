# Unique — Pending Work

This document tracks **outstanding** work only, ordered by priority. Completed
backlog sections move to [`docs/MILESTONES.md`](MILESTONES.md) (closing
summaries) with the detailed why/how of each fix archived in
[`docs/DONE.md`](DONE.md); `docs/STATUS.md` summarizes the project state at a
higher level.

Last reviewed: 2026-07-31.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## Discrete backlog

*The 2026-07-31 backlog liquidation closed Q1, D1 and A10's measurement +
harness (MILESTONES top entry; DONE §50–§51). What follows is the residue
that session filed: follow-up defect triage, maintainer decisions, and
small findings.*

### A10 follow-ups — functional-equivalence layer (P2)

*Audit: [`audit/2026-07-31-a10-fe-coverage.md`](../audit/2026-07-31-a10-fe-coverage.md).
The harness (A10-H) is live: 496 auto-enrolled cases, 43-case exclusions
ledger (`tests/helpers/challenge_fe_exclusions.py`), ratchet floor 43.*

- **A10-T4** — BLUE triage of the ledger's 25 `defect-pending-fix` cases
  (~27 unwarned wrong-value/runtime-fail pairs named in the report §T4:
  broken CAST emission on tsql/oracle, unnamed derived columns,
  string+INTERVAL arithmetic, INSERT()/LEFT()/REPEAT() float/OOB semantics,
  TO_CHAR mask fidelity, …) plus two D1-W8 additions (STUFF/OVERLAY→
  oracle/pg out-of-range-start guard missing — pg raises at runtime,
  unwarned; mysql `REPLACE` with a NON-literal NULL arg → oracle returns the
  original string where MySQL yields NULL). Each fix removes its ledger
  entry (the ratchet enforces the direction).
- ~~A10-T2~~ — DECIDED (maintainer, 2026-07-31: numeric tolerance) and DONE:
  two numeric cells match when equal after rounding to the COARSER operand's
  own precision, with a zero-adjacent absolute guard and a tight (1e-9)
  relative-epsilon fallback for full-precision transcendental noise (found
  via a live ts-trig regression). Purely-numeric fractional strings in
  scope; numbers inside longer text untouched. 11/12
  `precision-policy-pending` cases removed from the ledger
  (`my-num-to-str` retagged `documented-inherent`); floor 43→32. Policy
  documented in the `corpus_diff.py` module docstring.
- **A10-P** — procedures corpus live-COMPARE (4-dialect same-routine
  fixtures: call with fixed inputs, compare effects). Needs its own design;
  highest-value remaining FE gap.
- The 29 comparable-but-needs-tables cases enroll later via the `FuncCase`
  probe pattern (5 already curated by NF-1).

### Maintainer decisions pending

- **B47** (P2, live-probed) — Oracle bare `NUMBER` → `BIGINT` promotion is
  **unconditional** (`convert.py _convert_create_table` ~2428): a non-key
  fractional column (`discount_pct NUMBER`) silently becomes `BIGINT` —
  truncation risk, no warning. Faithful map would be PG `NUMERIC` or a
  role-aware promotion; either changes a long-pinned mapping
  (`TestOracleBareNumberToInteger`) and the shipped fixtures. Documented
  with a Warning callout in `docs/rationale/ddl.md` meanwhile.
- **A10-T2** above.

### Small findings (P3 unless noted)

- **B40** (found during B39) — the "no warning covers this carrier →
  synthesize a duplicate" reconciliation path emits a second
  `lossy_conversion` warning alongside a correctly-coded parse warning for
  the same carrier (cosmetic duplication) — a `_warning_covers`
  shingle-matching limitation, pre-existing.
- **B42** (verified pre-existing) — re-rendered `$$` splits into `$ $`
  inside *commented* degraded-routine carriers; cosmetic, but keeps the
  generated fixture perpetually dirty vs regeneration.
- **B43** (found during B37b) — mysql→tsql/oracle `ROW_COUNT()` inside an
  IF condition still degrades whole with warned UNIQUE-1151; warned/honest,
  coverage follow-up.
- **B44** (found during B38) — `_split_oracle`'s `plsql_start.search`
  matches "CREATE PROCEDURE" inside a *comment*, setting `in_plsql` early.
  Latent guardrail-3 wrinkle; harmless post-B38 (the peel undoes it) but
  the splitter should not read comment text.
- **B50** (P2, found during D1-recall-2, live-probed) — `INTERSECT ALL` /
  `EXCEPT ALL` → Oracle/T-SQL fall back to plain `INTERSECT`/`MINUS`-class
  forms with **zero warnings** — duplicate rows silently collapse. Oracle
  21c+ supports `INTERSECT ALL`/`MINUS ALL` natively → passthrough there
  (live-verify on 23c); T-SQL has no ALL form → rewrite (ROW_NUMBER pairing)
  or warned degrade, never a silent dedup.
- **B51** (P3, found during D1-recall-2, probed) — T-SQL
  `OPTION (MAXRECURSION n)` on a recursive CTE is dropped with only the
  generic unread-args tripwire warning (`UNIQUE-1228` "internal: unread
  sqlglot arg 'options'"). Promote to a real handler: drop with a proper
  documented warning (semantics genuinely diverge: T-SQL errors at the
  limit, PG recurses unbounded).
- **D1b2** (P3, docs) — the 18 new gap rows from the batch-5b full-recall
  pass (2 HIGH: binary-collation compensation family, recursive-CTE
  synthesis family) — table in `audit/2026-07-31-docs-gap-sweep.md`
  §Batch 5b; write as articles after the navigation restructure lands.
- **B49** (P2, found during D1b, live-probed) — `REPLACE t SET a=1 …` (MySQL)
  emits a `UNIQUE-1003` comment-only carrier on EVERY target — including
  `mysql → mysql` (the identity direction should round-trip valid MySQL
  syntax); AND its pinning test
  (`TestWave189BitwiseNotReplaceSet::test_replace_set_converts`) passes via a
  regex that matches the carrier's echoed-comment text — a test-quality
  false positive of the identity-mutant class. Fix both: convert
  `REPLACE … SET` (at least identity + the INSERT…SET-equivalent rewrite)
  and make the assertion real.
- **B48** (found during D1-W9, live-probed) — `_gate_column_alias_ref`
  degrades the derived-table column-alias list (`(SELECT …) AS xx(c1,c2)`)
  for MySQL claiming "no spelling" — live MySQL 8 accepts it; only Oracle's
  degrade is genuine (ORA-03048). Un-gate the mysql target.

### D1b/D1c — rationale residue (P3)

- **D1b** — the batch-6b recall pass's 9 MED + 3 LOW rows (4 HIGH done
  same-day). *In progress 2026-07-31 (docs worker).*
- **D1-recall-2** — `test_challenge.py` full-recall pass (batch 5 read only
  ~99/263 classes in full; the audit's honesty notes flag it as the
  weakest-recall batch after 6b closed). *In progress 2026-07-31.*
- **D1c** (maintainer-visible residue, not yet scheduled) — (a) the raw
  appendix rows of the docs-gap sweep NOT folded into the 18 clusters
  (single-mechanism MED/LOW items, each citing a pinning test); (b) test
  directories the sweep never covered: `tests/unit/dialects/`,
  `tests/unit/api/`, etc. (mostly rename-class parser/emitter tests —
  expected low yield, but unswept).

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
