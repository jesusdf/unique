# Unique — Project Status

## Current state: v0.42.1 (**M0–M4 complete**; v0.42.1 fixes MySQL 1093 self-referencing UPDATE/DELETE subqueries (generalized derived-table wrap) and lands the rationale contract + the 03-unsupported reclassification wave 1 (the BEGIN FOR guard family and 9 more misfiled faithful conversions now have articles); v0.42.0 completes the procedures functional-equivalence harness — **18 of 33 fixture routines result-compared nightly** (scalars, OUT/INOUT params, table state, multi-result sets via per-driver refcursor capture, and a func1 clock-freeze lever), 15-routine ledger with re-verified independent blockers, monotonic floors; v0.41.0 closes the defect backlog — OUTPUT params are INOUT (input values preserved), all four Oracle CAST-context quadrants live-valid, set-op CTEs and ALL forms faithful, REPLACE modeled, to_hex on every direction — and finishes the docs sweep: the ENTIRE test tree audited, ≈181 rationale articles, hardened generated indexes; v0.40.0 adds the rationale editorial pass — every article reads as user-facing translation documentation (black-box contract, encoded in the contributor rules) — the by-engine/per-topic jump navigation, and an editable web-UI destination editor so Compare works over arbitrary SQL pairs; v0.39.0 adds the two executed maintainer decisions — role-aware bare-`NUMBER` mapping with `UNIQUE-1236` on bounded targets, and the numeric-tolerance FE policy [ledger 43→32] — plus the book/MSDN rationale navigation: 105 one-article pages, generated per-topic and per-engine indexes with a CI freshness gate; the 2026-07-31 backlog liquidation closed Q1 [briefs B34–B39 + same-day findings B41/B45/B46], D1 [the 18-cluster rationale docs wave, incl. the new `booleans.md` page and full-recall pass], and A10's FE measurement + harness — **496 challenge cases now auto-enrolled** in the nightly result-diff behind a 43-case ratcheted ledger; corpus unchanged at **791 `[fixed]` / 169 `[limit]` / 0 `[open]`** of 960; pending residue in `docs/TODO.md`: A10-T4 defect triage, two maintainer decisions [B47, A10-T2], small findings B40/B42–B44/B48, D1b)

**Backlog liquidation 2026-07-31 (PURPLE-directed, agentic team mode)**: the
whole pending backlog executed in one session — see the top entry of
`docs/MILESTONES.md`, `docs/DONE.md` §50–§51, and
`audit/2026-07-31-a10-fe-coverage.md`. Highlights: the implicit-rowcount
hoist is spelling-general across sources; mysql SIGNAL/RESIGNAL reaches the
raise IR (was invalid output with the message lost); the leading-companion-DDL
batch shape parses (proc_2/7/8/9 execute on real PostgreSQL); warning
`.code`s match their carriers; Oracle native-BOOLEAN keeps `TRUE`/`FALSE`
(was live PLS-00382); the functional-equivalence nightly went from 21 to 496
compared cases and the previously-red `Challenge live` job is green.

**Challenge campaign 2026-07-30 (three cycles, PURPLE-directed red&blue)
CLOSED**: cycle 1 (61 findings), cycle 2 (27 findings, seeded), cycle 3 (6
findings, closed-list re-validation) — **94 findings total, 92 resolved
`[fixed]`**, 1 maintainer-approved `[limit]`, 2 held by approved feature
briefs (B29/B30), now also closed. The corpus stands at **791 `[fixed]` /
169 `[limit]` / 0 `[open]`** of 960 cases (`scripts/challenge_stats.py`,
run 2026-07-30). Full log: `docs/MILESTONES.md` ("Post-campaign backlog
executed" and the two campaign-cycle entries), `docs/DONE.md` §48–§49.

**Post-campaign backlog executed the same day**: **B29** (MySQL ENUM
declaration-order, sort-context only per a live-verified brief correction)
and **B30** (bounded date-type propagation for derived-table columns) closed
the corpus's last two `[open]` cases. **B32** landed a `UNIQUE-NNNN`
diagnostic-code registry across every carrier/warning emission site — see
"Diagnostic codes" below. **B31** added a rationale side-table keyed on
those codes, feeding the generated `docs/reference/warnings.md`. **B33**
drove the completeness gate's residual floor 14 → 0 by regenerating the
`tests/fixtures/procedures/*` fixtures through their sanctioned path
(`docs/DONE.md` §48). **F1** shipped `unique compare` (structural
similarity between two scripts) and **F2** its web UI Compare button — see
"Structural similarity" below. **Q2** (two emitter/degrade coherence bugs —
a stray `$$` inside a commented carrier body, and an orphan transaction
closer surviving a degraded opener) is closed per `git log` (`62d5493`,
`75dd020`, pinned by `0cba085`). **Q1** (the Oracle-source/MySQL-source
procedural degrade rate on the PostgreSQL pivot) was triaged
(`audit/2026-07-30-q1-triage.md`) and **fully executed 2026-07-31**
(`docs/DONE.md` §50): the actionable gap fell from 28/32 oracle→postgresql
and 21/31 mysql→postgresql routines to the two standing fronts only
(embedded-DML-as-text, dynamic SQL). Two of the top mechanisms had turned
out to be **transpiler bugs, not approved degrades** — a `UNIQUE-1171` false
positive from unscrubbed-comment `@name` scanning, and a `UNIQUE-1219`
SET-variable
misclassification that corrupts output by closing the routine body's `$$`
quoting early — both fixed among the six briefs.

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
`docs/TODO.md` now holds only the 2026-07-31 liquidation's residue (A10
follow-ups, two maintainer decisions, small findings, D1b) plus the
continuously-tracked rationale-coverage ratchet (see "Diagnostic codes"
below) and the challenge-corpus intake.

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
  - **Procedural pipeline, DML/DDL validity vs. carrier-degrade rate are
    different measurements** (Q1 triage, `audit/2026-07-30-q1-triage.md`,
    2026-07-30): the syntax-validity numbers above are for DML/DDL scripts.
    On the `tests/fixtures/procedures/` corpus specifically, oracle→postgresql
    and mysql→postgresql degrade a materially higher share of routines to
    carriers than sqlserver↔postgresql — 28/32 and 21/31 respectively — a
    distinct, currently open quality gap (briefs B34–B39, `docs/TODO.md`).
- **Test-assertion quality** is gated (identity-mutation floor **70%**, last
  measured **76%** on 2026-07-25 after the challenge assertion campaign —
  the stale-floor backstop itself demanded the raise) and tracked nightly
  (mutation job with per-module floors, now self-ratcheting: it fails when a
  floor sits >15 points under the measurement). Architecture debt is gated
  too (`scripts/architecture_ratchets.py` in CI: emitter module size,
  post-emit regex surface, dialect string-dispatch, complexity offenders —
  monotonic downward; measured 2026-07-30: emitter module **3645** lines,
  post-emit regex calls **182**, dialect string-compares **570**,
  cyclomatic-complexity offenders **114** — all at their current floor, zero
  slack).
- **Diagnostic codes (B32, 2026-07-30)**: every warning/error/carrier the
  transpiler emits carries a stable `UNIQUE-NNNN` code from a single
  registry (`src/unique/core/diagnostics.py`; **233 codes registered**,
  `UNIQUE-1001`–`UNIQUE-1233`, verified via
  `unique.core.diagnostics.DIAGNOSTICS`). A completeness gate
  (`tests/unit/core/test_diagnostic_completeness.py`) rejects any warning
  shipped without a code — the ratchet floor is **0** uncoded signatures,
  reached by B33 (2026-07-30) after regenerating the stale pre-B32
  procedural fixtures. `unique transpile --ignore UNIQUE-NNNN` (and the
  API's `ignore` field) suppress individual codes on the warning channel
  only — carriers always stay in the emitted SQL. A rationale side-table
  (B31, `src/unique/core/rationales.py`) keys the *why* of each code to a
  `docs/rationale/` page or `docs/03-unsupported.md` section, itself under a
  coverage ratchet — currently 33 of 233 codes have a registered rationale
  (floor: at most 200 uncovered, `tests/unit/core/test_diagnostics.py`).
  Lowering that floor is ongoing, unfinished work, not a closed item.

### Structural similarity — `unique compare` (F1/F2, 2026-07-30)

A new capability, distinct from functional-equivalence testing: `unique
compare A.sql B.sql` (and `unique.core.similarity.compare`,
`POST /api/v1/similarity`, and a web UI **Compare** button next to
**Transpile**, styled with the version-badge's colour tokens) reports a
*normalized structural similarity* percentage between two SQL scripts — same
or different source dialects — with a per-dimension breakdown (DML
structure, predicates, control flow, tree match). Both inputs are
normalized through the existing transpiler to a PostgreSQL pivot, then
compared by statement alignment plus weighted `sqlglot.diff` tree matching;
a statement that degrades to a carrier during normalization counts as
unmatched rather than inflating the score. It is explicitly presented as
**not** a claim of semantic equivalence — query equivalence is undecidable
in general — documented at `docs/03-unsupported.md` §3.38 and echoed in
both the CLI output and the web result panel. Source:
`src/unique/core/similarity.py`, `src/unique/cli/main.py` (`compare`
command), `src/unique/api/app.py` (`/api/v1/similarity`),
`web/src/index.template.html` (`compareBtn`).

### Documentation layers (T8, 2026-07-30)

Three complementary layers, indexed from [`docs/README.md`](README.md)
(landed 2026-07-30):

- **Curated rationale** (`docs/rationale/`): hand-written *why* pages —
  datetime, strings & collation, aggregates & windows, DML, DDL, procedural
  (6 pages plus a `README.md` index) — every claim traceable to a corpus
  case.
- **Generated reference** (`docs/reference/`, produced by
  `scripts/generate_reference_docs.py`, kept fresh by a CI `--check` gate
  that "caught real drift on its first day, twice" per `docs/DONE.md` §49):
  `warnings.md` (the per-`UNIQUE-NNNN`-code catalog, re-keyed on the B31/B32
  registries), `limits.md` (the approved-degradation `[limit]` catalog),
  `coverage.md` (challenge-corpus counts, machine-parsed from
  `scripts/challenge_stats.py`), and 12 `mappings-<source>-<target>.md`
  function/type matrices — 15 generated pages in total.
- **`docs/README.md`**: the documentation index itself, pointing readers to
  architecture, rationale, reference and the interfaces docs.

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

- **Challenge campaign, 2026-07-30, three cycles under the PURPLE role**
  (architect/analyst directing RED/BLUE worker agents; `docs/MILESTONES.md`):
  cycle 1 (61 findings: clause-enumeration/composition grids on
  tsql/oracle, self-emitted round-trips on pg/mysql), cycle 2 (27 findings,
  seeded probe — headline: MySQL `DELETE … ORDER BY … LIMIT` dropping the
  cap and deleting every matching row), cycle 3 (6 findings, closed-list
  re-validation: the UPDATE twin of the DELETE bug, non-literal
  TRY_CAST/TRY_CONVERT, SET TRANSACTION and GOTO in routine bodies). BLUE
  closed all but 2 (held by the B29/B30 feature briefs, since also closed).
  **94 findings, 92 `[fixed]`** — corpus 791/169/0 of 960. The same cycle
  shipped `docs/rationale/` (curated) and T8's generated `docs/reference/`.
  Full log: `docs/DONE.md` §48–§49.
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
- **Challenge corpus, RED/BLUE/PURPLE roles** (`tests/fixtures/challenge/`,
  workflow in `skills/SKILL-challenge-corpus.md`): an adversarial RED role
  hunts *silent* mis-transpilations (valid, anonymized source; live-validated
  on the four engines; a warned degrade is not a finding) and records them as
  `[open]` cases; a BLUE role fixes each one and locks it in as `[fixed]`
  (strict assertion) or an approved `[limit]` (warning + `UNIQUE:` annotation
  + `docs/03-unsupported.md` entry, contract-enforced by
  `test_challenge.py`); a PURPLE role — introduced 2026-07-30 — directs and
  coordinates iterative RED/BLUE rounds via delegated workers, evaluates
  yield, and is the sole role that decides when a campaign ends and commits/
  pushes to `main`. The 2026-07-18→24 campaign resolved all 862 RED findings
  and the three 2026-07-30 cycles resolved 92 of 94 more (`docs/MILESTONES.md`);
  the corpus (960 cases, 0 `[open]`) stays as the live intake for new ones.

The version is single-sourced from `unique.__version__` and released via
`scripts/release.py`. History: `docs/MILESTONES.md` (closed backlog sections)
and `docs/DONE.md` (detailed archive). Backlog: `docs/TODO.md` (currently
holds the 2026-07-31 liquidation residue — A10 defect triage and design
follow-ups, the B47/A10-T2 maintainer decisions, small findings — plus the
continuously-tracked rationale-coverage ratchet and challenge-corpus intake;
every other discrete item closed and archived).

---
*Last reviewed: 2026-07-30.*
