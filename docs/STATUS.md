# Unique — Project Status

## Current state: v0.22.3 + audit-04 plan (M0/M1 shipped)

The project is executing the architecture plan adopted from the 2026-07-08
audit ([`audit/2026-07-08/04-architecture-analysis.md`](../audit/2026-07-08/04-architecture-analysis.md)):
close the paths that bypass the AST core, make every failure loud and honest,
and replace "the fixture is green" with a **measured per-direction validity
percentage** as the definition of done. Milestones **M0** (validity sweep) and
**M1** (output honesty gate) are done; **M2** (comment trivia + unified AST
guard path) and **M3** (embedded DML through the IR converter) are next
(`docs/TODO.md`).

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
  - **T-SQL → PostgreSQL ≈ 99.9%**, **→ MySQL ≈ 98.6%**, **→ Oracle ≈ 99.6%**
    on a 13k-line migration dump (remaining failures are single known classes,
    e.g. `PRIMARY KEY CLUSTERED` inside a guard).
  - A procedures-heavy file exposes the open **declaration-hoisting family**
    (mid-body `DECLARE`) on all three targets — tracked P1.
  - **Oracle → T-SQL/PostgreSQL/MySQL is Tier-2 (experimental)**: ~29–44% of a
    real 13 MB dump fails on the target (`EXEC` handling, top-level `DECLARE`
    blocks, `FROM DUAL` INSERT-guards, expression corruption — the M4 bring-up
    backlog in `docs/TODO.md`).
- **Test-assertion quality** is gated (identity-mutation floor 33%, currently
  38%) and tracked nightly (mutation job with per-module floors).

### Direction tiers (doc-04 P6)

| Tier | Directions | Meaning |
|---|---|---|
| 1 — supported | T-SQL → PostgreSQL / MySQL / Oracle | ≥98% measured validity on real dumps; failures are enumerated classes with backlog entries |
| 1 — supported | the 4 native identities + curated FE matrix | FE harness green |
| 2 — experimental | Oracle → T-SQL / PostgreSQL / MySQL | large known defect classes; use behind the validity sweep |
| 2 — experimental | PostgreSQL/MySQL sources beyond the FE scenario | not yet corpus-measured |

### Recent milestones

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

Five complementary layers:

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

The version is single-sourced from `unique.__version__` and released via
`scripts/release.py`. History: `docs/DONE.md`. Backlog: `docs/TODO.md`
(M2–M4 + the audit-03 P1 class list + packaging).
