# Unique — Project Status

## Current state: v0.32.0 (**M0–M4 complete; the 2026-07-24 audit backlog, its follow-on findings and the B28 features all executed 2026-07-25** — every audit S1 fixed live-verified, emitter debt paid under CI ratchet gates, challenge corpus armed with 1,073 dedicated assertions; pending: two maintainer decisions)

**Direction-residue campaign closed 2026-07-17** (waves 103–239, user-declared
architectural floor at `469917a`): the six corpus directions (pg-source and
mysql-source × the three foreign targets) went from ~770 live-invalid
statements to **133**, validity **98.8–99.8%**, and the pg→pg silent-gap
discovery channel (`scripts/discover_silent_gaps.py`) from **287 to 0** — every
statement now transpiles validly or carries an explicit warning/carrier. Full
log: `docs/DONE.md` §36.

**Zero-reduction campaign — CLOSED far below the declared floor
(2026-07-17, batches W1–W10, `34d7338`).** The direction-residue campaign was
closed at a **user-declared floor of 133**; the M3-final flip then measured
127, and this campaign drove it to **16** — a further **−88% below the declared
floor** — with mechanism fixes (not waves), each commit gated + live-verified
(FE 16/16, discovery pg→pg 0). Current: pg-source {tsql 1, mysql 5, oracle
**1**}, mysql-source {tsql 4, pg 3, oracle **2**} — **both Oracle directions at
100.0% validity**, overall **99.8–100.0%**. The remaining 16 are the true
architectural floor (adversarial pg_regress/sqlancer inputs sqlglot cannot
parse, a correlated outer-aggregate subquery, composite-field access,
schema-dependent type inference, LATERAL column-alias lists). Full log:
`docs/DONE.md` §40.

**M4 milestone reached 2026-07-11:** the Oracle-source bring-up closed at
**0 syntax failures on all three directions** over the real 13 MB migration
dump (35k+ statements per direction, live engines): oracle→T-SQL 100.0%,
oracle→PostgreSQL 100.0%, oracle→MySQL 100.0% — from 475/41/121 failures at
the start of the bring-up (official `validity_sweep` at `7c1cea7`).

The architecture plan adopted from the 2026-07-08 audit
([`audit/2026-07-08/04-architecture-analysis.md`](../audit/2026-07-08/04-architecture-analysis.md))
— close the paths that bypass the AST core, make every failure loud and
honest, measure validity per direction as the definition of done — is
**fully executed**: **M0** (validity sweep), **M1** (output honesty gate),
**M2** (comment trivia + unified AST guard path), **M3** (embedded DML
*and* scalar expressions through the shared IR pipeline — IR-first with
the text rewriters as the warned fallback; `UNIQUE_NO_IR_FIRST` is the
emergency kill-switch) and **M4** (Oracle-source bring-up) are all done.
The **2026-07-24 audit** (`audit/2026-07-24/` — remediation verification,
10 new live-verified S1s, prevention plan, pre-analyzed fix briefs) and its
**entire B1–B28 backlog were executed 2026-07-24→25** in agentic team mode
(`docs/MILESTONES.md`, `docs/DONE.md` §44). The pending backlog in
`docs/TODO.md` now holds only the new findings that campaign surfaced, two
maintainer decisions, and the two authored feature briefs (B28a/B28b).

### What holds today (measured, not asserted)

- **Functional equivalence** holds across the full 4×4 matrix — all 16
  source×target pairs converge on the same final database state on real
  engines (curated scenario; CI-gating).
- **Honesty invariant (M1)**: the transpiler never ships output it can detect
  as invalid on the target. Plain DML/DDL is re-parsed in the target dialect
  and all output is scanned for source-dialect leftovers; a failing batch
  degrades to a carrier (original preserved) + `validity_gate` warning +
  `unsupported` entry. Duplicate warnings aggregate with an `(xN)` count.
- **Validity, per direction** (`scripts/validity_sweep.py`, M0 — transpile a
  real script, execute every statement on the live engine, classify
  transpiler defects vs empty-database noise). On the confidential real-world
  corpora (see `audit/2026-07-08/03-private-fixture-sweep.md`):
  - **T-SQL → PostgreSQL / Oracle / MySQL: 100.0%** on both confidential
    corpora (the 13k-line migration dump *and* the procedures-heavy file),
    measured 2026-07-10 after the sweep-closing wave: the C1–C4
    declaration/boundary family is closed (cursor variables and options,
    `@@FETCH_STATUS` loops per target, semicolon-less ELSE/statement-verb/
    MERGE/CTE boundaries, updatable-CTE and paren-join silent losses,
    base64-XML idiom, CATCH-block content, per-target DROP INDEX guards).
  - **Oracle → T-SQL/PostgreSQL/MySQL at Tier-1-grade validity**. On the
    real 13 MB dump (official sweep 2026-07-10, after FOURTEEN M4 closing
    waves): **PostgreSQL 100.0% (10 fails), MySQL 99.9% (18), T-SQL 99.8%
    (54)** — post-M1 baseline was 73.1 / 75.0 / 94.0; the T-SQL residue is
    dominated by client-DB-resident UDF calls that only resolve against
    the real target database (--db-url). The waves closed
    the exception-scope, trigger-header (UPDATE OF / WHEN / event
    predicates), CASE-statement, pseudo-row, dynamic-SQL and Oracle-builtin
    families (see `docs/TODO.md` M4 for the full list and the remaining
    classes). The T-SQL count is flat vs. the morning but *more honest*:
    unwrapping constant EXECUTE IMMEDIATE strings surfaced failures that
    previously hid as runtime noise inside opaque EXEC() calls.
    Tier-1 promotion still wants a second corpus.
- **Test-assertion quality** is gated (identity-mutation floor **70%**, last
  measured **76%** on 2026-07-25 after the challenge assertion campaign —
  the stale-floor backstop itself demanded the raise) and tracked nightly
  (mutation job with per-module floors, now self-ratcheting: it fails when a
  floor sits >15 points under the measurement). Architecture debt is gated
  too (`scripts/architecture_ratchets.py` in CI: emitter module size,
  post-emit regex surface, dialect string-dispatch, complexity offenders —
  monotonic downward).

### Direction tiers (doc-04 P6)

| Tier | Directions | Meaning |
|---|---|---|
| 1 — supported | T-SQL → PostgreSQL / MySQL / Oracle | ≥98% measured validity on real dumps; failures are enumerated classes with backlog entries |
| 1 — supported | the 4 native identities + curated FE matrix | FE harness green |
| 1 — supported | PostgreSQL → T-SQL / MySQL / Oracle | 98.8–99.2% measured validity on the PostgreSQL regression corpus (2026-07-17); residue enumerated in `docs/DONE.md` §36 |
| 1 — supported | MySQL → T-SQL / PostgreSQL / Oracle | 99.6–99.8% measured validity on the private MySQL corpus (2026-07-17); residue enumerated in `docs/DONE.md` §36 |
| 2 — experimental | Oracle → T-SQL / PostgreSQL / MySQL | large known defect classes; use behind the validity sweep |

### Recent milestones

The full milestone history (every closed backlog section, newest first) lives
in [`docs/MILESTONES.md`](MILESTONES.md); the highlights:

- **Challenge-corpus campaign COMPLETE** (2026-07-18 → 2026-07-24, v0.30.0):
  a RED batch live-validated 862 mis-transpilations (only *silent* problems
  count — a warned degrade is an accepted outcome); the BLUE/architect
  sessions then resolved every one: **694 `[fixed]`** (strictly guarded in
  `tests/integration/test_challenge.py`, live value-verified on the four
  engines) and **168 `[limit]`** (approved divergences — each warns, annotates
  the output with a `UNIQUE:` note and is documented in
  `docs/03-unsupported.md`). Highlights: full T-SQL MERGE (NOT MATCHED BY
  SOURCE → anti-join follow-up; Oracle single-clause fold + DELETE WHERE),
  Oracle cursor-attribute emulation, PL/SQL-vs-SQL CAST-context handling,
  cross-statement column-type metadata, JSONB/index carriers, constant folds
  by source semantics, INSTEAD OF trigger lowering. Full log: `docs/DONE.md`
  §41/§43.
- **M3 final — IR-first expressions** (2026-07-17, `86f7c11`): scalar
  fragments in routine bodies route through the shared IR pipeline by
  default; the text rewriters serve only IR-declined fragments (the
  primary+warned-fallback shape M3a gave embedded DML). Burn-down: the
  126-failure wholesale-probe rejection became ~15 family migrations with
  one shared table per family (both pipelines), closing with a measured
  live cycle BETTER than the declared floor: 127 total syntax failures
  across the six corpus directions (was 133), discovery pg→pg 0, FE 16/16.

- **Direction-residue campaign (waves 103–239)** (2026-07-15 → 2026-07-17):
  the no-silent-loss push over both validated corpora — silent-gap discovery
  pg→pg 287 → 0, six-direction live-invalid residue ~770 → 133 (98.8–99.8%
  validity), with an IR array model, function relations in FROM, a live
  output-validation option (`TranspileOptions.validate_live_url`,
  development-only by scope decision), and dozens of mechanism-level fixes in
  both pipelines. Closed at the user-declared architectural floor
  (`docs/DONE.md` §36).
- **M3 core (P4) — embedded DML through the shared IR pipeline** (2026-07-09):
  `_transform_embedded_dml` routes through `parse_sql → Transformer →
  emit_node`; raw sqlglot is a warned fallback. Cleared D3/D4/D8 and fixed
  four IR-core bugs affecting standalone DML (recursion, derived-table WHERE
  duplication, precedence parens, NULL ordering); `IN` and unstyled `CONVERT`
  now modeled. Probes: `tests/integration/test_embedded_dml_ir.py`.
- **M2 — comment trivia + unified AST guard path**: one shared
  `split_leading_trivia`; the per-spelling guard regexes collapsed into one
  polarity/trivia-aware extractor; per-target idempotent guard forms.
- **M1 — output honesty gate** (`unique/core/output_gate.py`): never ship
  known-invalid output; degrade to carrier + warning instead.
- **M0 — validity sweep** (`scripts/validity_sweep.py`) + one shared
  string/comment-aware statement splitter (`unique/core/sql_split.py`) used by
  the gate, the FE runner, the live validators and the sweep (fixes E1).
- **2026-07-08 audit**: all 14 findings of the 2026-07-02 audit verified
  fixed; ~25 new defect classes found by live-validating the private corpora;
  architecture plan (5 root causes, P1–P6) adopted — see `audit/2026-07-08/`.
- Earlier: T-SQL → Oracle procedures fixture fully valid (`USER_ERRORS`-aware
  validator); source-syntax validation across core/API/web/CLI; web UI
  redesign; guard round-trips covered by unit tests
  (`test_dual_guard.py` — *not* by the FE harness; see its coverage-matrix).

### Bug-detection infrastructure (what replaced ad-hoc manual testing)

Six complementary layers:

- **Validity sweep** (`scripts/validity_sweep.py`): per-direction validity %
  on real scripts against live engines — the definition of done.
- **Corpus × live-execution sweep** (`test_corpus_live.py`): the curated
  corpus transpiled to every target and executed for real; gaps are `@xfail`.
- **Generative fuzzer + invariants** (`tests/property/`): Hypothesis-generated
  SELECTs, invariants on every transpile, shrinking reproducers.
- **Differential result testing** (`test_corpus_results_live.py`): source vs
  transpiled result sets — catches wrong-answer bugs.
- **Mutation testing** (nightly + identity-mutation CI gate): assertion
  quality as a ratcheted number.
- **Challenge corpus, RED/BLUE roles** (`tests/fixtures/challenge/`, workflow
  in `skills/SKILL-challenge-corpus.md`): an adversarial RED role hunts
  *silent* mis-transpilations (valid, anonymized source; live-validated on
  the four engines; a warned degrade is not a finding) and records them as
  `[open]` cases; a BLUE role fixes each one and locks it in as `[fixed]`
  (strict assertion) or an approved `[limit]` (warning + `UNIQUE:` annotation
  + `docs/03-unsupported.md` entry, contract-enforced by
  `test_challenge.py`). The 2026-07 campaign resolved all 862 RED findings
  (`docs/MILESTONES.md`); the corpus stays as the live intake for new ones.

The version is single-sourced from `unique.__version__` and released via
`scripts/release.py`. History: `docs/MILESTONES.md` (closed backlog sections)
and `docs/DONE.md` (detailed archive). Backlog: `docs/TODO.md` (currently
empty — all discrete items closed and archived).
