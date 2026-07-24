# Audit 2026-07-24 — 06: Documentation drift

Scope: docs/STATUS.md headline claims vs measured artifacts; the
docs/01-compatibility.md matrix probed live via the API; docs/03-unsupported.md
warn-claims probed; README/06-installation/07-interfaces CLI examples run as
written; skills/*.md vs the actual tree; TODO/MILESTONES/DONE cross-references;
02-architecture/05-procedural component paths; release artifacts vs git tags.
Repo state: v0.30.0, HEAD `69a71cd`. All probes ran with `.venv/bin/python`
(`unique.__version__ == 0.30.0`).

Severity: **S2** = a doc overclaims a guarantee (a ✅/claim that does not hold);
**S3** = drift/staleness that misleads but does not overclaim.

---

## Verified clean (no finding)

- **Challenge-corpus headline is exact.** Line-start `-- CASE[...]` markers in
  `tests/fixtures/challenge/challenge_*.sql`: **694 `[fixed]` + 168 `[limit]` +
  0 `[open]` = 862** — matches STATUS, MILESTONES, DONE §43 verbatim. (A naive
  grep counts 169 `[limit]`; the 169th is a mid-comment cross-reference, not a
  case marker.)
- **FE-harness claims hold.** `test_functional_equivalence_live.py` builds
  `_PAIRS` as the full 4×4 (16 ids `s->t`), and all four source scenarios exist
  (`scenario/{tsql,oracle,postgresql,mysql}.sql`). STATUS's guard-round-trip
  attribution ("covered by `test_dual_guard.py` — *not* by the FE harness")
  matches `coverage-matrix.md` §"Not exercised here (by design)" — the
  2026-07-08 drift on this point is fixed.
- **TODO/MILESTONES/DONE ledger discipline holds.** `docs/TODO.md` discrete
  backlog is empty (matches STATUS "currently empty"), "Last reviewed:
  2026-07-24" is current, and every DONE § referenced from STATUS/MILESTONES/
  skills exists: §36 (l.3365), §40 (l.4845), §41 (l.4938), §42 (l.5115),
  §43 (l.5175).
- **README `:latest` note carried over.** README l.57 says "image published on
  release tags", `docs/06-installation.md` documents the Docker Hub image and
  the SHA-pin alternative, and CI actually pushes `unique:latest`
  (`.github/workflows/ci.yaml:488`). The 2026-07-02 gap is closed.
- **Python version drift fixed.** SKILL-project-overview says 3.13;
  `pyproject.toml requires-python = ">=3.13"` and all CI jobs pin 3.13.
- **CLI/API examples run as written.** README quick-start, all
  `docs/07-interfaces.md` CLI forms, and the `docs/02-architecture.md` §3.3
  variants (`--output` long flag, stdin pipe, `validate --dialect`) all exit 0
  with the documented behavior; `unique dialects` lists sqlite as
  `[import-only]`; sqlite-as-target exits 1; `unique.api.app:app` imports;
  entry-point group `unique.dialects` exists in pyproject. (Cosmetic only: the
  README/interfaces inline output comments show one-line SQL without the
  trailing `;` — actual output is multi-line with `;`. And the sqlite-target
  error interpolates the reason where a dialect name belongs: `Cannot
  transpile 'sqlite is import-only (a source only, never a target)' from tsql
  to sqlite`.)
- **Release claims check out locally.** Annotated tag `v0.30.0` exists and
  points at HEAD `69a71cd`; the version is single-sourced
  (`src/unique/__init__.py`) exactly as `scripts/release.py` and STATUS
  describe. (Remote push state could not be verified from this environment —
  `git ls-remote` has no credentials here.)
- **STATUS-cited mechanisms all exist:** `unique/core/output_gate.py`,
  `unique/core/sql_split.py`, `scripts/validity_sweep.py`,
  `scripts/discover_silent_gaps.py`, `TranspileOptions.validate_live_url`
  (`core/live_validate.py`), `UNIQUE_NO_IR_FIRST` (`transpiler/_core.py`),
  `_carrier_fragments` in the gate path.
- **12 of 15 probed matrix ✅ rows hold, with tests:** TOP→LIMIT, Oracle
  `(+)`→ANSI JOIN, `&`→BITAND, CROSS APPLY→LATERAL, EXCEPT→MINUS, `#tmp`→GTT,
  NVL2→CASE, DECODE→CASE, `::`→CAST, RAISERROR→RAISE, `0x`→HEXTORAW,
  WITH RECURSIVE, SELECT INTO→CTAS (test files located for each, e.g.
  `tests/unit/core/test_bitwise_oracle.py`, `test_subquery_limit.py`,
  `test_function_mappings.py`).
- **4 of 4 probed 03-unsupported warn-claims hold:** SOUNDEX→postgresql,
  OUTPUT→mysql, AT TIME ZONE→oracle, GOTO→postgresql each degrade **with** a
  warning; the §1.5 CONSTANT relaxation is unwarned exactly as documented
  ("safe relaxation").

---

## D1 (S2) — Matrix ✅ "INSERT … ON CONFLICT / MERGE" does not hold: PG `ON CONFLICT` is silently dropped on every foreign target

**Claim** (`docs/01-compatibility.md` §2): `INSERT … ON CONFLICT / MERGE | ✓
(MERGE) | ✓ (MERGE) | ✓ (ON CONFLICT) | ✓ (ON DUPLICATE KEY) | ✅`.

**Measured** (API probe, source=postgresql):

```
INSERT INTO t (id, v) VALUES (1, 2) ON CONFLICT (id) DO UPDATE SET v = EXCLUDED.v
  -> mysql : INSERT INTO t (id, v) VALUES (1, 2);   warns=0
  -> oracle: INSERT INTO t (id, v) VALUES (1, 2);   warns=0
  -> tsql  : INSERT INTO t (id, v) VALUES (1, 2)    warns=0
ON CONFLICT (id) DO NOTHING -> same: clause gone, warns=0 on all three
```

The upsert clause vanishes with **no warning** — a plain INSERT that raises a
duplicate-key error (DO NOTHING case) or fails to update (DO UPDATE case)
instead of upserting. This is simultaneously a matrix overclaim and a
violation of the no-silent-loss invariant STATUS advertises ("every statement
now transpiles validly or carries an explicit warning/carrier"). Existing
tests only cover the *degrade* interaction shapes (`RETURNING`+`ON CONFLICT`
carrier, `tests/integration/test_pg_source_wave1.py` waves 54/89) and the
challenge case `pg-insert-select-conflict` (DO NOTHING on a fresh table, where
the drop is value-invisible); no test proves the ✅ for the plain upsert.
`tests/unit/core/test_merge_mysql.py` covers T-SQL MERGE→MySQL, not PG
`ON CONFLICT`.

**Fix:** either implement the mapping (mysql `ON DUPLICATE KEY UPDATE` /
`INSERT IGNORE`, MERGE on tsql/oracle) with probe tests, or degrade the
statement to a carrier + warning **and** downgrade the matrix cell to ⚠️ with
the caveat spelled out. Until then the row must not read ✅.

## D2 (S3) — STATUS's identity-mutation numbers are stale: "floor 33%, currently 38%" vs actual floor 45% (measured 49%)

**Claim** (`docs/STATUS.md` l.79-80): "Test-assertion quality is gated
(identity-mutation floor 33%, currently 38%)".

**Measured** (`scripts/identity_mutation_check.py` l.20-28):
`KILL_RATE_FLOOR = 0.45`, with the history in comments: 0.30→0.33 (measured
36%), 0.33→0.40 on 2026-07-10 (measured 0.44), 0.40→**0.45** on 2026-07-11
(measured **0.49**). `SKILL-challenge-corpus.md` l.261 already says
"kill-rate floor 45%" — STATUS is two raises behind and its "currently 38%"
figure corresponds to no current measurement (it would fail today's gate).

**Fix:** update STATUS to "floor 45%, last measured 49%" (or reference the
script as the single source instead of inlining numbers).

## D3 (S3) — Matrix "IF EXISTS ✅ (Oracle → exception block)" describes a transform that does not happen

**Claim** (`docs/01-compatibility.md` §3.1): `IF EXISTS / IF NOT EXISTS | ✓ |
N/A | ✓ | ✓ | ✅ (Oracle → exception block)`.

**Measured:** `DROP TABLE IF EXISTS t;` (tsql or pg source) → oracle emits
`DROP TABLE IF EXISTS t;` **verbatim**, warns=0; `CREATE TABLE IF NOT EXISTS`
→ oracle likewise verbatim. No exception block is generated and no test
asserts one (`tests/unit/core/test_ddl_flags.py` asserts the PG side only).
Verbatim `IF [NOT] EXISTS` is valid only on Oracle **23c+** — the live CI
engine (FREEPDB1) accepts it, but the matrix elsewhere baselines Oracle at
12c+ (`FETCH FIRST … ✓ (12c+)`), where this output is a syntax error. The
cell's mechanism note is fiction either way.

**Fix:** change the parenthetical to "kept verbatim — requires Oracle 23c+"
(and state the Oracle version floor), or actually emit the guarded block for
pre-23c targets. Add a probe test for whichever is chosen.

## D4 (S3) — Matrix Summary Statistics table is stale: claims 172 rows (116/52/4), the matrix has 190 (133/52/5)

**Claim** (`docs/01-compatibility.md` §Summary Statistics): "Total 172 —
116 ✅ (67%) / 52 ⚠️ (30%) / 4 ❌ (2%)".

**Measured** (script counting the status column of every table row): **133 ✅ /
52 ⚠️ / 5 ❌ = 190 rows**. Rows added by the 2026-07 campaigns (hex literals,
quantified subqueries, data-modifying CTEs, SQL*Plus rows, truthiness, etc.)
were never folded into the totals; several per-category counts (e.g. Triggers
"5" vs 7 rows) are also off.

**Fix:** recount (a 10-line script) or delete the summary table — a wrong
aggregate undermines the matrix's "kept in sync" note.

## D5 (S3) — DONE §40's heading contradicts its own body (and STATUS): "127 → 22 (batches W1–W6)" vs the actual close at 16 after W1–W10

**Claim** (`docs/DONE.md` l.4845): "## 40. Zero-reduction campaign —
six-direction residue 127 → 22 (batches W1–W6)".

**Measured:** the section's own cycle table runs z10–z13 through **W7–W10**
ending at **16** ("Both Oracle directions reached 100.0% validity at z13"),
and STATUS (l.14-24) + MILESTONES ("residue 133 → 16") say 16 / W1–W10. The
heading froze at an intermediate cycle when the section was extended.

**Fix:** retitle §40 to "…residue 127 → 16 (batches W1–W10)".

## D6 (S3) — STATUS's two validity ranges for the same campaign disagree (98.9% vs 98.8% lower bound)

**Claim** (`docs/STATUS.md`): l.8 says the six directions closed at "validity
**98.9–99.8%**"; the Tier table (l.88) says "PostgreSQL → T-SQL / MySQL /
Oracle | **98.8–99.2%** measured validity … (2026-07-17)".

**Measured reality:** both cite the same §36 close; one lower bound is wrong
(the union of the tier rows is 98.8–99.8). Trivial, but STATUS is the
headline document and quotes itself inconsistently.

**Fix:** align on one range (98.8–99.8% per the tier rows) in both places.

## D7 (S3) — FINDINGS.md still carries ~160 finding rows and RED-era totals although the corpus is closed at 0 open

**Claim** (skill contract, `skills/SKILL-challenge-corpus.md`): BLUE "flips
each finding … and **removes it from FINDINGS.md**"; the batch ends only when
"every row in `FINDINGS.md` cleared".

**Measured:** `tests/fixtures/challenge/FINDINGS.md` is 2,228 lines and still
lists resolved cases as findings (e.g. `## ts-while-loop`, `## tsql-drop5-…`
"SILENT CLAUSE DROP … no warning") and ends with "Totals: 862 distinct
constructs; defect rows by kind: func 401, invalid 1322, semantic 2,
silent-drop 75" — all of which are now `[fixed]`/`[limit]` in the scripts.
Anyone reading the ledger concludes there is an open backlog; STATUS/
MILESTONES say 0 open.

**Fix:** prune FINDINGS.md to a closed-campaign note (pointer to
MILESTONES/DONE §43) as the 2026-07-18 prune did for the earlier 703 rows, or
re-label it explicitly as a historical archive.

## D8 (S3) — SKILL-challenge-corpus does not document the `[limit]` status tag that 168 cases now carry

**Claim** (`skills/SKILL-challenge-corpus.md` §"Case status tags"): only
`[open]`, `[fixed]`, and untagged are defined; "RED adds `[open]`; BLUE flips
to `[fixed]`", and the batch-end rule requires user approval per limit.

**Measured:** 168 cases are tagged `-- CASE[limit]: …`, `test_challenge.py`
enforces a distinct contract for them (must warn + `UNIQUE:` annotation +
`docs/03-unsupported.md` citation), and STATUS/MILESTONES describe `[limit]`
as a first-class outcome. The skill — the authoritative workflow doc — never
mentions the tag, so a fresh RED/BLUE session following it cannot process or
emit `[limit]` correctly.

**Fix:** add `[limit]` to the status-tag list with its contract (warn +
annotate + document + approval provenance), and update the BLUE batch-end
wording to include "approved `[limit]`" as a terminal state.

## D9 (S3) — The multi-file dialect-plugin layout described in three documents does not exist

**Claim** (`docs/02-architecture.md` §3.2, `docs/04-development-guide.md`
§"Adding a New Dialect", `skills/SKILL-development-workflow.md` l.386-390):
each `dialects/<name>/` contains `parser.py`, `emitter.py`, `functions.py`,
`types.py`, `keywords.py`.

**Measured:** every dialect package is a **single `__init__.py`**
(`dialects/tsql/__init__.py` is 69 lines; oracle/postgresql/mysql/sqlite
identical shape). None of the five described files exists anywhere under
`src/unique/dialects/`. A contributor following the "Adding a New Dialect"
recipe would build a structure the registry never loads beyond `__init__`.

**Fix:** rewrite the three passages to the real shape (one `Dialect` subclass
per `__init__.py`, function/type knowledge centralized in
`core/mappings.py`, procedural per-target modules under
`core/procedural/{emitter,transformer}/`).

## D10 (S3) — 02-architecture cites `transpiler.py`, `procedural/parser.py`, and `api/{routes,models}.py`; all three moved or never existed

**Claims** (`docs/02-architecture.md`): §3.1 tree shows
`core/transpiler.py` and `core/procedural/parser.py` as single modules
(headings "#### transpiler.py — Orchestrator" l.210); §3.4 shows
`api/routes.py` and `api/models.py`. `docs/05-procedural-engine.md` l.118
likewise cites `core/procedural/parser.py`.

**Measured:** since the 2026-07-17 module split (DONE §37),
`core/transpiler/` is a package (`_core.py`, `_text_rules.py`) and
`core/procedural/parser/` is a package (`_base.py`, `_tsql.py`, `_plsql.py`).
`src/unique/api/` contains only `app.py` (+ `static/`) — no `routes.py`, no
`models.py`. The §3.1 sketch also omits load-bearing core modules the docs
elsewhere rely on (`output_gate.py`, `sql_split.py`, `mappings.py`,
`batch_splitter.py`, `builtins.py`, `dialect.py`, `live_validate.py`).

**Fix:** refresh the §3.1/§3.4 trees and the two module headings; one pass
against `ls src/unique/core` suffices.

## D11 (S3) — SKILL-project-overview repository sketch lags the tree (same package splits, missing files)

**Claim** (`skills/SKILL-project-overview.md` l.47-101): layout shows
`core/… transpiler.py`, `procedural/ … parser.py # recursive descent`, and a
docs list ending at `DONE.md`.

**Measured:** `transpiler/` and `procedural/parser/` are packages (see D10);
the docs list omits `MILESTONES.md`, which the TODO/STATUS/CLAUDE.md
bookkeeping now names as one of the three ledger files; the core sketch omits
`output_gate.py`/`sql_split.py`/`builtins.py`/`live_validate.py`/`dialect.py`.
(The skill's Python 3.13 claim and campaign-closure narrative are accurate;
its §36/§40 references resolve.)

**Fix:** update the sketch's two filenames, add `MILESTONES.md` to the docs
list, and add the four missing core modules.

## D12 (S3) — 03-unsupported §3 subsections are ordered 3.12 → 3.22 → 3.21 → … → 3.13 (descending)

**Measured** (`docs/03-unsupported.md`): after §3.12 (l.329) the file runs
§3.22 (l.338), §3.21 (l.358), §3.20 (l.370), §3.19 (l.378), §3.18, §3.17,
§3.16, §3.15, §3.14, §3.13 (l.449). Cross-references like "docs/03-unsupported.md
§3.19–3.22" (STATUS, challenge case headers, MILESTONES) resolve, but a
reader scanning forward from §3.12 finds §3.22 next and may conclude
§3.13–3.18 are missing.

**Fix:** reorder ascending (pure move, no text changes), or add a one-line
"newest first" note at the top of §3.

## D13 (S3) — coverage-matrix.md status line still says "LOCKED for Phase 1 (T-SQL canonical source → MySQL/PostgreSQL/Oracle)"

**Claim** (`tests/functional_equivalence/coverage-matrix.md` l.9): "Status:
**LOCKED for Phase 1** (T-SQL canonical source → MySQL / PostgreSQL /
Oracle)."

**Measured:** the harness runs the full 4×4 (16 pairs) with native scenario
fixtures for all four sources (`scenario/{tsql,oracle,postgresql,mysql}.sql`),
which STATUS advertises as the headline FE guarantee. The document's own
Step-6 addendum already discusses the native PG/MySQL/Oracle fixtures, so only
the status line is stale — but it is the line STATUS's strongest claim rests
on, and the 2026-07-08 audit (N4/N9) made exactly this doc the arbiter for FE
claims.

**Fix:** update the status line to name the current phase (4×4 matrix,
scenarios A–C) and when it was extended.

---

## Summary

- **13 drift findings: 1 × S2, 12 × S3.** No finding contradicts the
  challenge-corpus headline, the release bookkeeping, or the
  TODO/MILESTONES/DONE ledger mechanics — those all verify exactly.
- **The S2:** matrix ✅ for `INSERT … ON CONFLICT` — PG upserts silently lose
  their conflict clause on all three foreign targets with zero warnings (D1),
  which also breaches the no-silent-loss invariant STATUS advertises.
- **Worst-offender doc:** `docs/01-compatibility.md` (D1, D3, D4 — an
  overclaimed ✅, a fictional mechanism note, and a stale summary table),
  followed by `docs/02-architecture.md` + the dialect-layout fiction repeated
  across three documents (D9, D10).
- Prior-audit items re-verified fixed: FE/guard-round-trip attribution,
  Python 3.13, README `:latest` note.
