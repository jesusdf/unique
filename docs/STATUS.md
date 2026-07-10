# Unique — Project Status

## Current state: v0.24.0 (M0–M2 shipped; M3 core + M4 bring-up landed)

The project is executing the architecture plan adopted from the 2026-07-08
audit ([`audit/2026-07-08/04-architecture-analysis.md`](../audit/2026-07-08/04-architecture-analysis.md)):
close the paths that bypass the AST core, make every failure loud and honest,
and replace "the fixture is green" with a **measured per-direction validity
percentage** as the definition of done. Milestones **M0** (validity sweep),
**M1** (output honesty gate) and **M2** (comment trivia + unified AST guard
path) are done. **M3**'s core landed (2026-07-09): embedded DML in routine
bodies now runs the same `parse → transform → emit` IR pipeline standalone
DML uses (raw sqlglot only as a warned fallback) — one mapping engine, two
callers. Routing that traffic exposed and fixed four IR-core bugs that also
corrupted standalone DML (pass recursion stopped at top-level SELECTs; a
derived table's WHERE duplicated onto the outer SELECT; parens/precedence
dropped on emit; NULL-ordering not carried on ORDER BY). M3's final step
(deleting the expression-level text rewriters) is blocked on moving the
procedural text-matchers onto structure — tracked in `docs/TODO.md`.

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
    real 13 MB dump (official sweep 2026-07-10, after TEN M4 closing
    waves): **PostgreSQL 100.0% (12 fails), MySQL 99.9% (18), T-SQL 99.7%
    (97)** — post-M1 baseline was 73.1 / 75.0 / 94.0. The waves closed
    the exception-scope, trigger-header (UPDATE OF / WHEN / event
    predicates), CASE-statement, pseudo-row, dynamic-SQL and Oracle-builtin
    families (see `docs/TODO.md` M4 for the full list and the remaining
    classes). The T-SQL count is flat vs. the morning but *more honest*:
    unwrapping constant EXECUTE IMMEDIATE strings surfaced failures that
    previously hid as runtime noise inside opaque EXEC() calls.
    Tier-1 promotion still wants a second corpus.
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
