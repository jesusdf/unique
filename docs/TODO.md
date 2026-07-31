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
- **A10-P** — *design DONE 2026-07-31:
  [`audit/2026-07-31-a10p-procedures-fe-design.md`](../audit/2026-07-31-a10p-procedures-fe-design.md)
  (33-routine inventory, live-probed effect capture per engine incl. the
  oracledb refcursor-binding hang gotcha, benign-warning allowlist {1193,
  1196}, enrolled-floor-up ratchet + no-silent-loss invariant, nightly +3-6
  min).* Architect decisions taken: PG result-set-proc invalidity = defect
  (B56, fix not degrade); allowlist approved as designed; func1-freeze
  approved for P3. Implementation briefs: **A10-P1** (scalar/OUT/table-state
  start set) → **A10-P2** (result sets after B56) → **A10-P3**
  (func1-freeze, trigger, TVF).
- **B56** (P2, found by the A10-P prototype, live-verified) — tsql
  result-set PROCEDURES → PG emit a bare `SELECT` (no INTO/RETURN) inside a
  PROCEDURE — runtime SQLSTATE 42601 "no destination for result data";
  passes the compile gate. Faithful conversion needs the refcursor-OUT
  pattern PG-side (the same signature rewrite Oracle gets) or an honest
  degrade — never runtime-invalid.
- **B57** (P2, same source) — `func4`→PG emits `sha256(text)` (no such
  function; PG's sha256 takes bytea). B36b's mapping covered the
  CONVERT_TO(bytea) path in DML shapes; this fixture shape misses the
  conversion — close the gap and add the missing-leg test.
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

- **B55** (P2, found during D1b2, live-verified on Oracle) — two invalid
  Oracle CAST-context combinations outside the pinned shapes: an
  explicit-length CAST inside an expression ARGUMENT emits PLS-00103-invalid
  output, and a lengthless CAST inside an embedded SQL statement (e.g.
  `SELECT … INTO`) emits ORA-00906-invalid output (the `IR_EMBEDDED`
  length-stripping decision keys on in-body vs not, missing these two
  quadrants). The rationale article
  `procedural/oracle-cast-length-plsql-body-vs-sql-statement.md` documents
  only the two verified-safe combinations.
- **B54** (P3, found during T4-B, probed) — a standalone `to_hex(x)` →
  T-SQL/Oracle emits an unwarned phantom `dbo.HEX` / `HEX` call that errors
  at runtime (not in the FE ledger — different shape than pg-baseconv's
  fixed leg). Map faithfully (tsql `CONVERT(VARCHAR, x, 2)`-family / oracle
  `TO_CHAR(x,'FMXX...')` or LOWER(RAWTOHEX)-family — live-verify) or degrade
  warned.
- **B53** (P3, architect finding 2026-07-31) — the `shared_dialect_compares`
  architecture ratchet counts only `== "<dialect>"` spellings; two same-day
  fixes (B49, B51) legitimately added dialect dispatch written as
  `dialect != "mysql"` / `dialect in ("tsql",)` — counter stays flat while
  the real dispatch debt grows. Re-baseline the metric to count `==`, `!=`,
  and tuple-membership forms, set the new floor at the re-measured value,
  and keep it monotonic from there.

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
