# 03 — Test quality (2026-07-24, v0.30.0, HEAD 69a71cd)

Re-measurement of the test-assertion quality metrics from the 2026-07-08 audit
(`audit/2026-07-08/01-remediation-verification.md`, "Test quality" section),
plus an inspection of the challenge-corpus contract, the nightly mutation
ratchet, coverage, property tests and known flakiness. All numbers below were
measured locally on this machine (8 cores, `.venv` Python 3.13.5, clean tree at
`69a71cd`) on 2026-07-24.

## Headline numbers

| Metric | 2026-07-08 | 2026-07-24 | Delta |
|---|---:|---:|---:|
| Identity-mutation kill rate (CI gate) | 334/871 = **38%** | 1710/2585 = **66%** | +28 pts |
| CI kill-rate floor | 0.33 | 0.45 | floor last raised 2026-07-11 |
| Floor headroom | 5 pts | **21 pts** | ratchet stalled |
| Total suite size (collected) | 1774 | **3785** | +113% |
| Integration tests (collected / run under mutation) | 871 | 2709 / 2585 (124 env-skips) | +211% |
| Coverage (line, measured; not gated) | — | 90.89% (15280/16812) | — |
| Challenge corpus | (being built) | 862 cases: 694 `[fixed]` / 168 `[limit]` / 0 `[open]` | corpus closed |

## 1. Identity-mutation gate — 66% kill rate, floor 45%

Run exactly as CI does (`python scripts/identity_mutation_check.py`, which runs
`pytest tests/integration -p tests.mutation.identity_plugin`):

```
identity-mutation: 1710/2585 tests detect a no-op transpiler (kill rate 66%, floor 45%)
```

Per-file breakdown (killed / collected under the identity mutant; files whose
0% is entirely env-gated `pytest.skip` are marked *live*):

| File | Killed | Collected | Rate | 2026-07-08 |
|---|---:|---:|---:|---|
| test_pg_source_wave1.py | 600 | 806 | 74% | (new) |
| test_challenge.py | 485 | 557 | 87% | (new) |
| test_cross_dialect.py | 110 | 396 | **28%** | 105/396 = 27% |
| test_procedural.py | 123 | 144 | 85% | 121/141 = 86% |
| test_real_world.py | 28 | 134 | **21%** | 28/134 = 21% |
| test_oracle_source_m4_wave.py | 76 | 85 | 89% | (new) |
| test_live_syntax.py | 0 | 77 | *live* | — |
| test_oracle_mysql_tail.py | 38 | 51 | 75% | (new) |
| test_embedded_dml_ir.py | 34 | 45 | 76% | (new) |
| test_function_translation.py | 16 | 45 | 36% | 15/47 = 32% |
| test_triggers.py | 38 | 45 | 84% | 38/45 = 84% |
| test_procedures_fixtures.py | 0 | 36 | **0%** (1 skip) | — |
| test_functional_equivalence.py | 3 | 31 | 10% | — |
| test_operator_roundtrip.py | 17 | 31 | 55% | 55% |
| test_test2_residue_wave.py | 25 | 28 | 89% | — |
| test_ddl_rename_dropindex.py | 16 | 20 | 80% | (new) |
| test_trigger_predicates_scheduler.py | 19 | 19 | 100% | (new) |
| test_comment_preservation.py | 3 | 15 | **20%** | 3/15 = 20% |
| test_external_schemas.py | 3 | 15 | 20% | — |
| (remaining 19 smaller files) | 91 | 129 | 71% avg | — |

**Interpretation.** The 38% → 66% jump is real but comes almost entirely from
*new* test modules written to the assertion bar (the wave modules and
`test_challenge.py` contribute 1085 of the 1710 kills). The weak files the
2026-07-08 audit flagged are **unchanged**: `test_cross_dialect.py` gained 5
kills in 16 days (286 of its 396 tests still pass with the transpiler
disabled — the single largest survivor pool), `test_real_world.py` and
`test_comment_preservation.py` gained zero. Total survivor pool: 875 tests,
led by cross_dialect (286), pg_source_wave1 (205), real_world (106),
challenge (72 — see §3, mostly by-design), procedures_fixtures (~35),
function_translation (~28).

**Floor ratchet:** 0.33 (07-03, `030f43e`) → 0.40 (07-10, `447bf1b`) → 0.45
(07-11, `e5a0288`, measured 0.49). No raise in the 13 days since, while the
measured rate climbed 0.49 → 0.66. A regression that wiped out every wave-module
assertion would still pass today's floor.

## 2. Suite size — 3785 tests (+113%)

`pytest --collect-only -q`: **3785** collected — unit 1019, integration 2709,
functional_equivalence 46, property 11. Up from 1774 on 2026-07-08. The full
parallel suite at HEAD is green locally: `scripts/test-parallel.sh` → rc=0,
3785 tests, ~56 s wall on 8 workers.

## 3. Challenge-corpus contract (`tests/integration/test_challenge.py`)

862 cases across the four fixtures (694 `[fixed]`, 168 `[limit]`, 0 `[open]` —
matches the v0.30.0 release claim). 557 tests, all passing (25 s), 87%
identity-kill.

**Machinery, against the quality bar:**

- `[fixed]` generic loop (`test_fixed_cases_have_no_unrecognized_construct`):
  asserts only *absence* of `UNIQUE: Unhandled` / `could not translate` on
  every cross-engine pair. This passes under an identity transpiler —
  **deliberately** kept as one looping test so it does not dilute the gate
  (documented in its docstring). The real quality bar lives in the per-case
  classes.
- `[limit]` machinery (`test_limit_cases_warn_and_annotate_on_every_failing_target`):
  **meets the bar.** For every filed diverging target it enforces (1) a
  warning, (2) a `UNIQUE:` annotation in the output, (3) no unrecognized
  carrier, and (4) a `docs/03-unsupported` citation in the case header.
  Verified programmatically: all 168 `[limit]` heads carry a parseable
  `fails on <engines>` list (0 unparseable, 0 that resolve to no checked
  target — the failure mode where a malformed head would silently skip the
  case does not occur today, but nothing *guards* it; a head without
  `fails on` only fails on the citation check). The test fails under identity
  (no warnings from a no-op), so it kills the mutant.
- `[open]` smoke loop: no-crash only, correctly so; the corpus has 0 open.

**Per-case `[fixed]` assertions — spot check (~35 classes read across the
4882-line file):** consistently strong. The dominant pattern is target idiom
present AND source idiom absent (`161` `not in` + `9` `not re.search`
negative asserts across 439 test functions), with explicit comment-prose-trap
handling: 51 sites strip `--` lines and 8 split on `/*` before negative
asserts (e.g. `TestForXml`, `TestAtTimeZone`, `TestWindowedStringAgg` all
document that the carrier/header prose contains the banned phrase and check
only the executable text). The 72 challenge tests that survive identity are
overwhelmingly *by design*: same-dialect round-trips
(`test_tsql_roundtrip_preserves_or_alter`, `test_verbatim_on_own_dialect`),
"untouched/survives" invariants (`TestDdlConstraintClausesSurvive`), and
idioms spelled identically in source and target (`BIT_AND(x)`). A handful of
degrade tests assert presence of a phrase that also appears in carrier prose
(`TestTablesample`: `"TABLESAMPLE" in result.sql`), but each is paired with a
`result.warnings` assert, so none survive identity.

**Gaps found:**

1. **No target-dialect parse validation.** `tests/helpers/validity.py`
   (`assert_parses`, `assert_translated`) is used by 5 other integration
   modules but *not* by `test_challenge.py`. Challenge outputs are never
   parsed in the target dialect by CI.
2. **Not in any live sweep.** The challenge fixtures are absent from
   `tests/helpers/corpus.py` and every live test; the many "Live-verified …"
   claims in docstrings are manual BLUE-session evidence, not reproduced by
   CI. A regression that keeps the asserted substring but breaks the
   statement elsewhere would ship.
3. **Dedicated-assertion coverage ≈ 48%.** Only 332 distinct cases are
   referenced via `_case(...)` in per-case classes; the other ~362 `[fixed]`
   cases are guarded only by the identity-passing carrier-absence loop
   (plus, for some, assertions living in wave modules). The corpus README
   ("when you add a case … add an assertion in test_challenge.py") is not
   fully honored.

## 4. Nightly mutation workflow (`.github/workflows/mutation.yml`) — floors are not ratcheting

- Floors: `convert.py` 65, `emit.py` 60, `_base.py` 38, `harvest.py` 48,
  `transformer/base.py` 52 — set **2026-07-06** (`045db08`) and **never
  changed since**. The only later change (`b20f69a`, 07-15) added the wave
  modules to the `--tests` selections after the floors had been "under water
  since 07-09" — which *raises measured scores* without raising floors.
- Sampled local measurement (first 40 mutants of `convert.py`, same test
  selection as the nightly, `scripts/mutation_test.py --limit 40`):
  **33/40 killed (82%)** vs floor 65 — ≥17 points of slack on the flagship
  module (biased sample — first-N AST sites — but directionally clear).
- The nightly's actual scores could not be read from here (`gh` CLI not
  installed); they exist only in run summaries. Nothing in the workflow
  surfaces "measured is far above floor — raise it", so the ratchet only
  prevents regression below a 18-day-old baseline.
- **Hazard (verified the hard way during this audit):**
  `scripts/mutation_test.py` applies each mutant by **writing the mutated
  source to `src/` on disk** (`path.write_text(mutated)`, restored in a
  `finally`). Any *concurrent* test run against the same working tree reads
  mutated sources and fails with bizarre, hard-to-attribute errors (a
  concurrent full-suite run during this audit's sampled mutation produced 14
  spurious failures, e.g. `INSERT INTO t3 SET …` degrading to an
  `Unhandled expression type: Command` carrier; the tree was clean and green
  once the harness finished). Safe in CI's dedicated job; dangerous for the
  documented local workflow of running sweeps and suites in parallel.

## 5. Coverage — measured, not gated; not committed

- CI measures coverage on every push (`COV=1 scripts/test-parallel.sh` →
  per-worker data files → `coverage combine` → `coverage.xml` uploaded as an
  artifact + terminal report).
- There is **no gate**: no `fail_under` in `pyproject.toml` and no CI
  threshold check. Coverage can only be inspected, never enforced.
- The root `coverage.xml` (2026-07-23, local run) reports **90.89%** line
  coverage (15280/16812). It is listed in `.gitignore` (line 47) and **not
  tracked** — the "committed by mistake" concern does not hold.

## 6. Property tests — small, still meaningful; no xfail rot

- `tests/property/`: 11 tests, 2 files, last touched 2026-07-09. All
  high-value invariants that run in the default suite: lexer never
  crashes/always terminates on arbitrary text, token columns in bounds,
  parser always returns a node, generated T-SQL procedures round-trip to all
  targets, emitter preserves the PROCEDURE keyword, batch splitter never
  crashes, GO split count; DML side: **output parses in the target dialect**,
  leading comment preserved, derived-table aliases conserved, round-trip
  stays valid. No rot; but at 11 of 3785 tests the generative surface is
  small relative to the two pipelines.
- `-- @xfail:` rot in the live corpus (`test_corpus_live.py`): **zero**
  `@xfail` annotations remain in `tests/fixtures/corpus/*.sql`, so no stale
  xfails exist today. Note the stale-xfail detection in
  `test_corpus_live.py:48-52` only `print()`s a NOTE — if annotations return,
  one that starts passing will never fail CI, so rot would accumulate
  invisibly.

## 7. Flakiness — `test_transpile_within_budget[northwind_postgresql]`

- Still present and **unmitigated**: wall-clock assert, 10.0 s budget
  (unchanged since introduction, `7f98ed5`), no retry, no serial pinning, no
  CPU-time measurement; not tracked in `docs/TODO.md`.
- Measured today: passes serially (all 4 perf tests in ~11 s); the full
  8-worker parallel run at HEAD passed it (suite green, 56 s); under
  *additional* concurrent load (the mutation harness running alongside the
  parallel suite) it failed at **19.69 s vs 10.0 s**. Consistent with the
  known behavior (overshoots only under parallel load). It remains a latent
  intermittent in CI's 4-core parallel run.

## Findings, ordered by importance

1. **Both quality ratchets have stalled.** Identity floor 0.45 vs measured
   0.66 (21 pts); nightly mutation floors untouched since 2026-07-06 with
   ≥17 pts sampled slack on `convert.py`. The infrastructure is excellent;
   the policy of "raise as assertions harden" (stated in both scripts) has
   not been executed since 07-11 / 07-06.
2. **The 2026-07-08 weak files are exactly as weak.** cross_dialect 28%
   (286 survivors — largest pool), real_world 21%, comment_preservation 20%.
   All overall improvement came from new modules; none from hardening.
3. **Challenge `[fixed]` guard is two-tier.** ~332/694 cases have strong
   dedicated assertions (present-AND-absent, prose-trap-aware — they meet the
   bar); the remaining ~362 are covered only by an identity-passing
   carrier-absence loop. Challenge outputs are neither target-parsed nor
   live-executed in CI, so the extensive "live-verified" evidence is
   unreproducible.
4. **Coverage (90.9%) is measured but ungated** — a coverage regression
   cannot fail CI.
5. **Perf-budget flake latent and unhandled**; wall-clock under parallel
   load is the wrong measurement.
6. **Local-workflow hazards:** mutation harness mutates `src/` on disk
   (breaks any concurrent run); stale-`@xfail` detection is print-only.

## Recommendations

1. **Raise `KILL_RATE_FLOOR` 0.45 → 0.60** (measured 0.66; 6 pts margin
   absorbs suite-composition drift). Justified by today's measurement alone.
2. **Ratchet the nightly mutation floors from one full nightly run** — e.g.
   `convert.py` 65 → 75 if the full run confirms the sampled 82%. Add the
   measured-vs-floor table to the job summary and adopt a written policy:
   floor := measured − 5 whenever measured > floor + 10 for three consecutive
   nights. Consider committing the nightly scores to the repo (a small JSON)
   so audits and ratchets don't depend on run-summary archaeology.
3. **Spend one hardening wave on `test_cross_dialect.py`** using the existing
   `assert_translated` helper — 286 survivors is the single biggest lever;
   taking the file to ≥50% lifts the whole gate to ~69% and unlocks a 0.65
   floor.
4. **Close the challenge loop:** (a) add `assert_parses` (target-dialect
   sqlglot parse) to the generic `[fixed]` loop for DML-shaped cases;
   (b) feed the challenge fixtures into the live corpus sweep
   (`tests/helpers/corpus.py`) so the "live-verified" claims are CI-enforced;
   (c) burn down the ~362 fixed cases without dedicated assertions, or
   annotate each with where its assertion lives.
5. **Gate coverage:** `fail_under = 88` in `[tool.coverage.report]` (current
   90.89% leaves ~3 pts headroom), enforced in the CI coverage step.
6. **De-flake the perf test:** assert on `time.process_time()` (CPU time is
   load-independent) or run the perf parameters in a dedicated serial phase
   of `scripts/test-parallel.sh`; track the flake in `docs/TODO.md` until
   fixed.
7. **Make stale `@xfail` a failure** in `test_corpus_live.py` (it already
   computes the list; change the `print` to a `pytest.fail` — with 0
   annotations today this is free).
8. **Make the mutation harness safe locally:** mutate a copy of the tree (or
   an import hook) instead of writing into `src/`, or at minimum print a
   loud banner and document the do-not-run-concurrently constraint in the
   development-workflow skill.
