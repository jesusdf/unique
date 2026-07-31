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

- **A10-T4** — *round 1 DONE 2026-07-31 (T4-A): 8 structural cases / 5
  mechanisms fixed faithfully (boolean-to-char casts, Oracle string→int
  rounding, unnamed synthesized derived columns, string-date+INTERVAL
  promotion, unlockable-view FOR UPDATE drop under new `UNIQUE-1237`);
  ledger 32→24; two lying assertions corrected.* Remaining: the
  function-semantics family (~16 cases: INSERT()/LEFT()/REPEAT() float/OOB,
  STUFF/OVERLAY guards on oracle/pg, TO_CHAR masks, base conversion,
  multibyte CHR/ASCII, COMPRESS container, cast-int-datetime, ts-to-date,
  frac-seconds, cast-binary padding, REPLACE non-literal NULL). *Round 2
  (T4-B) DONE 2026-07-31: every remaining `defect-pending-fix` entry
  cleared — 11 mechanisms fixed faithfully, COMPRESS container = honest
  warned degrade (`UNIQUE-1240`), 4 retagged `documented-inherent` with
  live evidence, 1 cleared by the tolerance comparator. Ledger 24→11
  (9 inherent + 2 session-dependent), floor 11.* **A10-T4 COMPLETE.**
- ~~A10-T2~~ — DECIDED (maintainer, 2026-07-31: numeric tolerance) and DONE:
  two numeric cells match when equal after rounding to the COARSER operand's
  own precision, with a zero-adjacent absolute guard and a tight (1e-9)
  relative-epsilon fallback for full-precision transcendental noise (found
  via a live ts-trig regression). Purely-numeric fractional strings in
  scope; numbers inside longer text untouched. 11/12
  `precision-policy-pending` cases removed from the ledger
  (`my-num-to-str` retagged `documented-inherent`); floor 43→32. Policy
  documented in the `corpus_diff.py` module docstring.
- ~~A10-P~~ — DONE (P1+P2 2026-07-31/08-01; P3 stopped at a stable point by
  maintainer decision 2026-08-01): the procedures-FE harness compares **18 of
  33 routines nightly** (scalar/OUT/table-state + result sets via per-driver
  refcursor capture + the func1-freeze lever; proc_26 on oracle/pg only —
  B60), ledger 15 with re-verified reasons (4 clock-inherent, 4 dynamic-sql,
  3 degrade-output-clause, generated-key, encoding-inherent, TVF, trigger),
  `ENROLLED_FLOOR = 18` monotonic-up + the `18+15==33` no-silent-loss
  invariant. Deferred P3 remainder: none actionable — every non-enrolled
  routine's blocker is re-verified independent of the harness.
- ~~B60~~ — DONE 2026-08-01: the existing SET-only self-ref wrap generalized
  to a recursive tree-walker (WHERE/IN/EXISTS, DELETE, JOINs, unaliased →
  synthesized `uq_sr`); live 1093 repros → all execute; proc_26 re-enrolled
  on all 3 targets (harness 43/0); rationale article shipped same-commit
  (`dml/mysql-update-delete-self-reference.md`) + new corpus case.
- ~~B56~~ — DONE 2026-07-31: PG result-set procs get the shared refcursor rewrite (`INOUT refcursor`, argmode-first for sqlglot; Oracle byte-identical); 12 fixture procs now runnable, live-fetched.
- ~~B57~~ — DONE 2026-07-31: SHA-n over character args wraps CONVERT_TO in the IR path too; runtime error gone; NVARCHAR/UTF-16 divergence documented inherent.
- The 29 comparable-but-needs-tables cases enroll later via the `FuncCase`
  probe pattern (5 already curated by NF-1).

### Maintainer decisions pending

- ~~B47~~ — DECIDED (maintainer, 2026-07-31: role-aware + warning) and DONE:
  bare `NUMBER` → `BIGINT` only on STRUCTURAL id signals (inline/table-level
  PK/UNIQUE/identity/FK incl. the cross-statement `PK_UNIQUE_COLUMNS`
  harvest; FKs promote for join compatibility); otherwise PG unbounded
  `NUMERIC` (faithful, no warning) and MySQL/T-SQL `DECIMAL(38,10)` + new
  `UNIQUE-1236` warning. Live: `0.1250000001` preserved (was truncated to 0
  under BIGINT). Docs: ddl.md callout rewritten, 03-unsupported §3.19,
  reference regenerated. `TestOracleBareNumberToInteger` strengthened.
(Both maintainer decisions resolved 2026-07-31.)

### Small findings (P3 unless noted)

- **B61** (P2, found during RECLASS-2, probed) — PL/SQL `CONSTANT` variable
  declarations are dropped on EVERY cross-engine direction including
  Oracle↔PostgreSQL (both support them); only a same-dialect round-trip
  keeps them. The old docs claimed Oracle↔PG kept them — corrected; the fix
  is to thread `CONSTANT` through for targets that support it.
- **B62** (P2, found during RECLASS-2, probed) — T-SQL cursor `SCROLL` is
  discarded unconditionally at parse time (`_tsql.py::_parse_tsql_declare`
  lumps it with LOCAL/FAST_FORWARD hints) — silent, even on a tsql→tsql
  round-trip and toward PostgreSQL (both support SCROLL; scroll-FETCH forms
  are a documented [limit] elsewhere, but the DECLARE property itself should
  survive where the target supports it). PG-source SCROLL threads fine.

- ~~B59~~ — DONE 2026-07-31: pg identity respells canonical HEX back to `TO_HEX`; all 4 directions live-verified lowercase-unpadded.

- ~~B58~~ — DONE 2026-07-31: T-SQL OUTPUT → INOUT at the single parser source point (unconditional faithful; all emitters already spelled it; OUTPUT→INOUT→OUTPUT round-trips). proc_14 enrolled (13), live 'base flt' on all 3 targets.
- ~~B55~~ — DONE 2026-07-31: the real axis is PL/SQL-expression vs SQL-statement (`IR_PLSQL_EXPR` ContextVar from `_expr_position`, extended to IF/WHILE, subquery resets); all 4 quadrants live-VALID on Oracle 23c; also fixes CLOB-in-SELECT-INTO.
- ~~B54~~ — DONE 2026-07-31: `to_hex` mapped faithfully to tsql (VARBINARY+style-2+pad-strip) and oracle (TO_CHAR XXXX), live-verified 0/255/2^32/max-bigint.
- ~~B53~~ — DONE 2026-07-31: ratchet re-baselined counting `==`/`!=`/dialect-tuple membership; new floor 924.

- ~~B40~~ — DONE 2026-07-31: reconciliation no longer duplicates an identically-coded warning.
- ~~B42~~ — DONE 2026-07-31: dollar-quote close-tag scanner desync bug found+fixed first, then the `$$`→`$ $` mangling removed as dead; fixture regen shows exactly the 4 fixes.
- ~~B43~~ — DONE 2026-07-31: inline `ROW_COUNT()`→`@@ROWCOUNT`/`SQL%ROWCOUNT` pre-IR shell step for tsql/oracle (general, not IF-only), live-compiled.
- ~~B44~~ — DONE 2026-07-31: `_split_oracle` head-window scan comment-blind via the shared strip.
- ~~B50~~ — DONE 2026-07-31: Oracle native passthrough (`INTERSECT ALL` /
  `MINUS ALL`, live-probed on 23c); T-SQL gets the bounded ROW_NUMBER-pairing
  rewrite (top-down traversal so chain shapes read the original structure),
  warned whole-degrade outside the bound — never a silent dedup. 28 tests
  incl. live multiset value checks on 4 engines; new rationale article +
  compatibility row. `test_setop_all.py`.
- ~~B52~~ — DONE 2026-07-31: `_convert_union` reads the set-op node's
  `with` and routes it through the shared `_convert_cte` machinery onto the
  head arm; remaining SetOperation args enumerated per guardrail 7 (all
  either handled or never populated by real grammars, tripwire backstops).
  Composes with B50's ALL rewrite for free. 95 tests incl. 12 live-value;
  `test_setop_cte.py`.
- ~~B51~~ — DONE 2026-07-31: `options` consumed into
  `SelectStatement.query_hints`; MAXRECURSION drops under `UNIQUE-1238`
  (divergence stated), other hints under `UNIQUE-1239`; tsql→tsql keeps the
  clause (live-proven load-bearing: 500-level recursion). 1228 gone for
  this shape.
- **D1b2** (P3, docs) — the 18 new gap rows from the batch-5b full-recall
  pass (2 HIGH: binary-collation compensation family, recursive-CTE
  synthesis family) — table in `audit/2026-07-31-docs-gap-sweep.md`
  §Batch 5b; write as articles after the navigation restructure lands.
- ~~B49~~ — DONE 2026-07-31: both REPLACE forms parse through the INSERT
  IR (`is_replace` flag; pre-parse keyword shim per the compound-assignment
  precedent, original kept in `source_text`); mysql identity emits real
  `REPLACE INTO` (live delete-then-insert verified incl. PK-collation
  collision); other targets degrade honestly; the lying assertion now fails
  under the identity mutant.
- ~~B48~~ — DONE 2026-07-31: mysql un-gated (routed through the same
  derived-table rewrite tsql gets; live-executed on MySQL 8); Oracle's
  ORA-03048 degrade re-verified genuine and kept.

### D1b/D1c — rationale residue (P3)

- ~~D1b~~ — DONE 2026-07-31: all 12 batch-6b rows written as 14 entries.
- ~~D1-recall-2~~ — DONE 2026-07-31: 215/263 classes read in full (batch
  5b appendix); recall debt closed; 18 new gap rows → D1b2.
- ~~D1c~~ — DONE 2026-07-31: (a) all 115 raw appendix rows reconciled — 49
  covered, 53 → 41 new articles, 13 LOW deferred with reasons; (b) the
  remaining test dirs swept in full (batch 8: 40 files, 3 gaps → articles,
  everything else 0-gap) — **the entire test tree is now swept**. Rationale
  corpus ≈ 181 articles; generator hardened (delink, span-aware sentence
  cut, multi-line-span link checker).

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
