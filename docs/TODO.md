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

*The 2026-07-24 audit backlog, the findings it surfaced, and the B28 features
are ALL closed — see [`docs/MILESTONES.md`](MILESTONES.md) and
[`docs/DONE.md`](DONE.md) §44–§47. Both maintainer decisions are resolved:
`or_replace` on views kept and documented (2026-07-29, DONE §46); the sqlglot
CASCADED-hang closed by the 30.14.0 upgrade — fixed upstream (2026-07-30,
DONE §47).*

### B32 — warning/error code registry: `UNIQUE-NNNN` (P2, feature brief; approved 2026-07-30)

*Prerequisite for B31 (the rationale registry keys on these codes) and
consumed by T8 (the generated catalog is per-code). Same pattern as the
engines we transpile (ORA-00942, SQLSTATE) and modern compilers (rustc E0308).*

- **Deliverable:** every emitted warning/error/carrier carries a stable code
  (`UNIQUE-1234`). A single registry module (code → {category, message
  template}) with a CI collision check; `TranspileWarning.code` alongside
  `.message`; carriers become `-- UNIQUE-1234: …` / `/* UNIQUE-1234: … */`.
- **Numbering:** flat sequential (no thematic ranges — they rot); category is
  registry metadata.
- **Sentinel compatibility:** the harness/invariant regexes
  (`tests/helpers/invariants.py:44`, `_carrier_fragments@_core.py:432` and
  siblings) widen to `UNIQUE(-\d{4})?:` so pre-code outputs still match.
- **Three waves:** (1) registry + codes at all emission sites + sentinel
  regexes; (2) migrate test assertions from prose-matching to code-matching
  (kills the comment-prose trap; the `[limit]` contract asserts the *specific*
  code); (3) completeness gate — no warning ships uncoded (a ratcheting
  count of uncoded sites, unread-args style), plus CLI `--ignore UNIQUE-NNNN`.
- **Locks in:** docs anchors per code (`docs/reference/warnings.md#unique-1234`),
  stable grep for users, suppression/telemetry by code.

### B31 — structured rationale metadata on degrade sites (P3, feature brief; approved 2026-07-30; depends on B32)

*Docs "phase 2" (maintainer-approved): make the narrative layer generable.*

- **Symptom:** the *why* of each degrade/creative conversion (engine-level
  reason, example, exact divergence) lives in free-form docstrings and case
  headers; `docs/rationale/` must therefore be hand-written and can drift.
- **Mechanism to build:** a declarative rationale registry — each
  carrier/warning emission site registers `{construct, reason, example_case,
  divergence}` (compile-time data, no runtime cost), the same way the degrade
  registries already work. `generate_reference_docs.py` (T8) then emits the
  rationale sections mechanically, and a coverage check reports degrade sites
  with no registered rationale (ratcheting down, never up).
- **Design constraint:** the registry must not fatten the emitters — a
  side-table keyed by the **B32 `UNIQUE-NNNN` code** (its primary key), not
  per-site inline blobs; respects all four architecture ratchets.
- **Locks in:** every `docs/rationale/` claim about a degrade becomes
  traceable to a registry entry; new degrades cannot ship without a rationale.

### Q1 — Oracle-source / MySQL-source procedural degrade rate on the PG pivot (P2)

*Measured by F1's acceptance corpus (2026-07-30): `oracle→postgresql` and
`mysql→postgresql` degrade **~19–21 of ~32** `tests/fixtures/procedures/`
routines to carriers, while `sqlserver↔postgresql` keeps ~31–32. This is the
transpiler-quality reason those cross-dialect same-function pairs score
17–34% instead of ~99%. Front: triage the degraded routines by carrier code
(the B32 catalog makes this a `grep -c` per `UNIQUE-NNNN`), rank mechanisms
by frequency, and work them as briefs — same method as the campaign fronts.
Also aligns with the standing "Oracle-source Tier-1 promotion" goal in
`docs/STATUS.md`.*

### Q2 — small emitter/degrade coherence bugs (P3, observed 2026-07-30)

- The PG-pivot output can contain a stray `$$` inside a `--` commented body
  line (found by F1's splitter work) — desyncs naive statement scanners;
  find the emitter that leaks it and keep the comment self-contained.
- A parse-failed statement's sibling transaction closer survives the degrade:
  `begin \nSELECT 1;\nend` (invalid PG source) comments the failed opener but
  still emits a lone `COMMIT TRANSACTION` (T-SQL error 3902 at runtime).
  Warned (UNIQUE-1003), so within the honesty rules — but the coherent
  degrade is to carrier the whole transactional unit when its opener fails.

### F2 — web UI "Compare" button for F1 (P3; depends on F1 — LANDED 2026-07-30; approved 2026-07-30)

*Maintainer-specified UI (2026-07-30):*

- **Button:** a `Compare` button in the web UI, placed **to the right of
  `Transpile`**, styled with the **same color as the version-label badge's
  background** (reuse that CSS token/class — do not hardcode a new color).
- **Flow:** compares the two editor panes' scripts via the F1 API
  (`similarity` endpoint — add it to `src/unique/api/` mirroring the
  transpile endpoint, thin wrapper over `core/similarity.py`).
- **Result presentation (expectation management, REQUIRED):** the result
  panel must explain what the percentage REPRESENTS — *normalized structural
  similarity* of the two scripts after pivot-normalization (per-dimension
  breakdown shown), explicitly NOT semantic equivalence nor a probability of
  correctness — mirroring F1's presentation mandate and its
  `docs/03-unsupported.md` boundary note. Wording visible next to the score,
  not hidden in a tooltip.
- **Build:** `web/` source + `build.py`; probe test for the endpoint; UI
  smoke per existing web-test patterns.

### F1 — `unique compare`: structural similarity score between two scripts (P2)

Full brief below, in the `audit/2026-07-24/09-fix-briefs.md` format — the
implementing session starts **here** (plus the two standing skills), not from
scratch. File:line references are at HEAD of 2026-07-30 (`a5295d7`) —
re-confirm cited sites before patching.

**Goal / scope:** a new capability that takes two SQL scripts — same dialect or
**different dialects** — and reports a *normalized structural similarity*
percentage plus a per-dimension breakdown. Primary use case (maintainer
decision, 2026-07-30): **cross-dialect migration audit** — "how close is this
hand-migrated PL/SQL to the original T-SQL?". Explicitly **NOT** semantic
equivalence: query equivalence is undecidable in general, and SMT-based provers
(Cosette/SPES/SQLSolver) cover SELECT-only fragments with no procedural code.
The number must be presented as *structural similarity*, never "probability of
equivalence". Document that boundary in `docs/03-unsupported.md`.

**Assets already in the repo (verified 2026-07-30):**

- `tests/helpers/functional_equivalence.py` — `fingerprint(sql, dialect) ->
  ProcedureFingerprint` with `.differences(other)`: counts DML verbs, column
  multisets, predicates, control flow, using the hybrid path (procedural IR for
  the shell, sqlglot per DML fragment). This *is* the embryonic dimension
  layer; only `tests/integration/test_functional_equivalence.py` imports it.
- **sqlglot 30.14.0 ships a tree-diff**: `sqlglot.diff(a, b)` returns
  Change-Distiller-style edits (`Keep`/`Insert`/`Remove`/`Move`/`Update`).
  Verified live in the project venv. `2·|Keep| / (|nodes A| + |nodes B|)` is a
  ready-made per-statement score.
- The transpiler itself is the cross-dialect normalizer (see Approach step 1).
- `tests/fixtures/procedures/procedures_{sqlserver,oracle,postgresql,mysql}.sql`
  hold the *same routines in all four dialects* — a ready-made corpus of
  "different SQL, same function" pairs that must score HIGH.

**Approach — layered score, MVP = layers 0–2:**

1. **Layer 0, normalization via the existing pipeline.** To compare
   cross-dialect, transpile *both* inputs to one pivot dialect (postgresql)
   with the existing `transpile` entry point, then re-parse the outputs. This
   reuses the whole IR pipeline as the canonicalizer (dialect idioms like
   `ISNULL` vs `NVL` vs `COALESCE` collapse for free) and is the project's
   unique advantage — do NOT hand-write a second normalizer. On top of the
   pivot output, normalize comparison-only noise: alias alpha-renaming,
   commutative AND/OR operand order (sort by canonical key), literal quoting.
   Comments are trivia (already the project rule). Same-dialect comparisons go
   through the same pivot path — one code path, no special case.
2. **Layer 1, dimension fingerprints.** Promote the fingerprint logic from
   `tests/helpers/functional_equivalence.py` into a new
   `src/unique/core/similarity.py` (move the logic; leave the tests helper as a
   thin re-export so `test_functional_equivalence.py` keeps working). Dimensions
   for the report: DML structure, predicates, control flow — per-dimension
   scores are more honest than one opaque number (maintainer decision).
3. **Layer 2, tree matching.**
   - *Statement alignment first:* scripts hold N vs M statements; align with
     `difflib.SequenceMatcher` over statement-kind signatures, then greedy
     best-match within replace-blocks by per-pair score (Hungarian is
     overkill for MVP). Unmatched statements count fully against similarity.
   - *Per aligned DML pair:* `sqlglot.diff` on the pivot-dialect ASTs; score
     `2·|Keep|/(|A|+|B|)` with **node-type weights** — losing a WHERE/JOIN/ON
     predicate must cost far more than an alias or literal delta. Start with a
     small weight table (predicate/join/source nodes heavy; identifiers,
     literals, aliases light) and tune against the fixture corpus.
   - *Procedural shell:* recursive statement-list alignment over the project
     IR (`IfStatement`/`WhileStatement`/`ForLoopStatement`/… branches recurse;
     embedded DML delegates to the sqlglot layer above). Plain sequence
     alignment + kind matching is enough for MVP — full tree-edit-distance on
     the procedural IR is NOT required.
   - Overall % = weighted mean of dimensions; report all components.
4. **Layer 3 — deferred, NOT in this brief:** empirical live check (run both
   scripts on the four Docker engines over seeded data via
   `tests/helpers/live_validation.py` and compare results). It yields
   equivalent/not-on-this-data, not a % — if ever built, it's a separate
   brief; do not scope-creep it into the MVP.

**Surface (MVP):** `unique compare A.sql B.sql` as a new `@cli.command()` in
`src/unique/cli/main.py:24`-style (group at `main.py:18`), options
`--dialect-a/--dialect-b` (fall back to `core/detection.py` auto-detect, echo
what was detected), `--json` for machine-readable output. Python API:
`unique.core.similarity.compare(sql_a, sql_b, dialect_a=None, dialect_b=None)
-> SimilarityReport` (dataclass: overall, per-dimension, per-statement pairs,
unmatched statements, warnings). REST endpoint: follow-up, not MVP.

**Edge semantics to decide up front (defaults chosen; change consciously):**
empty vs empty → 100; empty vs non-empty → 0; a script that fails to parse →
hard error naming which input (never a silent 0); transpiler warnings during
pivot normalization → surface them in `SimilarityReport.warnings` (a degraded
statement compared as a carrier comment would inflate similarity — count
degraded statements as unmatched instead).

**Rejected paths (do not revisit):**

- Text/token-level diff as the main signal — dialect noise dominates and it
  violates the no-text-transform architecture rule; acceptable only as a
  debug extra, never in the score.
- Formal equivalence proving — undecidable; out of scope permanently
  (document in `03-unsupported.md`).
- ML/embedding similarity — unexplainable number, unjustifiable in an audit.
- Diffing the two *source*-dialect sqlglot ASTs directly without the pivot
  transpile — dialect idioms would read as structural differences, which
  undercounts exactly the pairs this project exists to normalize.

**Tests first (assertion quality bar applies — every test must fail under a
`return 100.0` stub AND under a `return 0.0` stub):**

- Identity: a script vs itself → 100 on every dimension.
- Cross-dialect same-function: each pair of the four
  `tests/fixtures/procedures/` variants scores above a high floor (calibrate
  the floor empirically, then ratchet it — same pattern as the validity
  floors); unrelated script pairs score below a low ceiling.
- Weight ordering: dropping a WHERE clause from B lowers the score strictly
  more than renaming an alias in B.
- Alignment: statement reordering is tolerated (Move ≠ Remove); an extra
  unmatched statement lowers the score.
- Degraded-statement rule: a pair where one side degrades to a carrier during
  pivot normalization does NOT score as matched.
- CLI: `--json` output schema, dialect auto-detect echo, parse-failure exit
  code distinct from "low similarity".

**Acceptance:** CLI + Python API working on the fixture corpus with the floors
above; gate green (black + isort + ruff + mypy + full parallel suite); ratchets
untouched (new module, no emitter growth); docs updated in the same change —
`07-interfaces.md` (command + API), `03-unsupported.md` (no formal
equivalence), README example runnable as written.

**Blast radius:** new `src/unique/core/similarity.py`; `src/unique/cli/main.py`
(one command); `tests/helpers/functional_equivalence.py` becomes a re-export;
new `tests/unit/test_similarity.py` + CLI test; three doc files. Core
transpiler untouched — if the pivot normalization surfaces transpiler bugs,
file them as separate findings (brief-first), do not fix inline.

**Estimated effort:** MVP (layers 0–2, CLI, tests, docs) — days, not weeks.
Procedural weight tuning is the open-ended part; time-box it and ship with the
calibrated floors.

---

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
