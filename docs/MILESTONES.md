# Unique — Milestones

Completed backlog sections, moved here from [`docs/TODO.md`](TODO.md) so the
backlog holds only pending work. Each entry keeps the closing summary as it
stood in the TODO; the detailed why/how of every fix lives in
[`docs/DONE.md`](DONE.md) (section numbers referenced below).
`docs/STATUS.md` summarizes the current project state at a higher level.

Newest first.

---

## Challenge campaign 2026-07-30, cycle 2 — seeded probe + docs armament

RED round 2 (one seeded 1-hour probe over cycle-1's leads): **27 findings /
75 points / 6 classes** — headline a real data-loss (MySQL `DELETE … ORDER BY
… LIMIT` dropped the cap and deleted every matching row). BLUE closed
**27/27** across two workers: the date-function unit/format-model space swept
as a class (unmapped units now warn by name, never silently wrong), the
asymmetric false-unmap family wired symmetrically (JSON_VALUE, DIV, nextval,
matview, LIKE char-classes + DAYOFWEEK/`~*` from the sweep), the ordered
DELETE cap per target, EXCLUDE window frames, SAVEPOINT-in-procedure, and the
comment/statement-swallow class extended to SET. Docs armament shipped in the
same cycle: hand-curated `docs/rationale/` (6 pages, 52 entries, every claim
corpus-traceable — the audit style paid off: it caught six dead assertions
misfiled in SUSPECT_CASES and two doc-vs-code discrepancies) plus T8's
generated `docs/reference/` (14 pages from `core/mappings.py` + the corpus,
CI freshness gate — which caught its first real drift the day it landed).
Backlog: B29–B32 briefs approved (ENUM order, date-type propagation,
rationale metadata, `UNIQUE-NNNN` warning codes). Ratchets tightened:
emit 3718→3696, dialect-compares 575→571. Corpus:
**783 `[fixed]` / 169 `[limit]` / 2 `[open]` (both briefed)** of 954.
Remaining known, uncased observations (UPDATE ORDER BY LIMIT, non-literal
TRY_CAST, SET TRANSACTION, GOTO) → cycle 3's narrow scope.

---

## Challenge campaign 2026-07-30, cycle 1 — PURPLE-directed red&blue (v0.35.0+)

First campaign run under the PURPLE role (architect/analyst directing worker
agents). RED: two 1-hour committed-time batches hunting one level up
(clause enumeration + composition grids on tsql/oracle; self-emitted
round-trips + script-wide consistency on pg/mysql) yielded **61 findings /
196 points / all 7 classes** — headline: silent PIVOT drop, GROUP BY
multi-element drop, DISTINCT ON as SELECT DISTINCT, a DATEDIFF KeyError
crash, and a systematic lying-warning family from the sqlglot 30.14 bump.
BLUE: five workers over two waves closed **57 of 61 (93%)** — new IR for
composite GROUP BY, PIVOT/UNPIVOT and LIKE-ESCAPE; the CONCAT-NULL class in
both directions; day-preserving ADD_MONTHS; the comment-prose corruption
class in the text rules; plus 1 maintainer-approved `[limit]`
(GROUPS frame) and 2 feature briefs (B29 ENUM order, B30 date-type
propagation) holding the last 2 `[open]`. Architect-side: `emit_relations.py`
seam carved to keep all four ratchets at floor (never raised); worker
branch discipline made a hard rule after a RED worker committed on `main`
and swept another session's changes. Corpus: 862 → 927 cases,
**756 `[fixed]` / 169 `[limit]` / 2 `[open]` (briefed)**. Full round log in
the session's FINDINGS.md history and `docs/TODO.md` B29/B30.

---

## Post-audit findings + B28 features (2026-07-25, v0.31.0–v0.32.0)

The flywheel's second turn: the findings the audit campaign itself surfaced
(`TIMESTAMPLTZ` invalid-type class + the T4 gate's sqlglot-leniency denylist,
numeric `||`→PG operand casts, PL/SQL multi-word datetime/interval declares)
and the two authored feature briefs (B28a `#temp`-in-procedures with live
two-call isolation on all targets; B28b top-level TRY/CATCH with a live
raise-and-recover matching the SQL Server reference) — all closed
brief-first by workers under architect review, ratchets kept flat by
refactor. Remaining from the audit stream: two maintainer decisions only.
Detail: [`docs/DONE.md`](DONE.md) §45.

---

## Audit 2026-07-24 backlog — fully executed in agentic team mode (2026-07-24 → 2026-07-25)

The third full audit ([`audit/2026-07-24/`](../audit/2026-07-24/)) verified
the 07-08 remediation, found 10 new live-verified S1s one level up
(clause-level + cross-feature composition), and produced a prevention plan
(doc 08) + pre-analyzed fix briefs (doc 09). The ENTIRE backlog (B1–B28,
tools T1–T7) was then executed across three /goal tandas by worker agents
under architect review — the "agentic team mode" now documented in the
dev-workflow skill. Highlights: upserts modeled end-to-end (live FE on 4
engines), MERGE semantic series, per-cursor attribute emulation, running
column-type harvest, constant dynamic-SQL translation, original-text
carriers, emitter debt paid (`emit.py` 10,485→3,718 max lines, F1/F2
de-regexed, ratchet gates + complexity ceilings in CI), the challenge corpus
armed (target-parse gate, nightly live result-diff job, 1,073 new
identity-killing dedicated assertions → kill rate 66%→**76%**, floor 0.70 —
the T7 stale backstop demanded the raise itself), confidentiality tooling
(leak checker that caught a real leak on day one), and a self-ratcheting
nightly mutation workflow. New findings surfaced by the campaign form the
next (small) pending backlog. Detail: [`docs/DONE.md`](DONE.md) §44.

---

## Challenge corpus — 862 RED findings fully resolved (2026-07-18 → 2026-07-24, v0.30.0)

Regression corpus at [`tests/fixtures/challenge/`](../tests/fixtures/challenge/)
— one anonymized script per source engine collecting tricky constructs as they
are found; guarded by `tests/integration/test_challenge.py`. Cases are tagged
`[fixed]` (strictly guarded), `[limit]` (approved divergence — must warn +
annotate + cite `docs/03-unsupported.md`) or `[open]` (RED backlog). See the
[challenge-corpus skill](../skills/SKILL-challenge-corpus.md) for the red/blue
workflow.

- [x] **CAMPAIGN COMPLETE 2026-07-24 — 0 `[open]` / 694 `[fixed]` /
      168 `[limit]` of 862 RED findings; released as v0.30.0.** Every case is
      either strictly guarded (`[fixed]`) or an approved, warned + annotated,
      documented limit (`[limit]`, docs/03-unsupported.md §3.19–3.22 + §7).
      The fix-vs-limit decision was delegated by the user to the 2026-07-24
      architect session. Full campaign log (waves, mechanisms, per-front
      composition, mandatory method) archived in [`docs/DONE.md`](DONE.md) §43.

## Test-suite memory blow-up (P2) — surfaced 2026-07-21, RESOLVED 2026-07-22

- [x] **Root cause found + fixed (commit `02f483b`).** The "memory growth" was
      **not** linear accumulation and **not** a coverage-only problem — it was a
      single pathological test whose guard had regressed. This cycle's `scrub()`
      lying-warning fix changed scrubbed non-empty literals from `''` to `'x'`,
      which broke the psql-`:'var'` parse guard in `convert.py` (its signature
      `(?<!:):\s*''` no longer matched). So `COPY t FROM :'filename'` fell through
      to sqlglot, whose `_parse_copy_parameters` **loops unboundedly allocating
      memory**. Serially the `MemoryError` is *caught* and the statement still
      degrades — but only after a multi-GB transient spike (the "~9 GB by 22% at
      `test_embedded_dml_ir`" and the misread "linear climb" were this one test).
      Under the parallel runner four such spikes coincide and the OS OOM-killer
      SIGKILLs a worker (EXIT=137) before Python can raise → **the CI Test job's
      4th shard went silent ~6 min then "the runner has received a shutdown
      signal".** Fix: match the new scrub output, `(?<!:):\s*'`. Diagnostic aid
      added: `faulthandler_timeout=120` in `pyproject.toml` (a future single-test
      hang now dumps its stack instead of surfacing only as a runner shutdown).
      Verified: the 4-worker parallel suite (the CI config) passes clean, no OOM;
      CI green on `02f483b`.
- [x] **Coverage re-added to CI (`COV=1`) — 2026-07-23.** With the real cause
      (above) fixed, measured `COV=1 PYTEST_WORKERS=4 scripts/test-parallel.sh`
      locally: **peak total RSS across all workers = 1.19 GB** (all shards green,
      91% coverage, `coverage.xml` produced) — far under a runner's ~16 GB. Memory
      is tied to the core count (nproc workers, ~0.3 GB/worker), so it stays
      bounded. Restored the `COV=1` Test-job step + the `Upload coverage` artifact
      in `.github/workflows/ci.yaml` (reverting `3a2029e`).
      **Process note:** `pytest … | tail` reports the *pipe's* exit, not pytest's
      — capture `> file; echo "EXIT=$?" >> file` for a trustworthy full-suite
      result; use `ulimit -v` so a runaway `MemoryError`s instead of OOM-killing
      the host.

## T-SQL keyword coverage — DONE (archived [`docs/DONE.md`](DONE.md) §42)

`PROC`≡`PROCEDURE`, `CREATE OR ALTER`, and `BEGIN TRAN[SACTION]` all route and
translate; covered by `tests/integration/test_tsql_keyword_alias.py` +
`test_challenge.py` + `test_procedural.py`.

## Audit 2026-07-08 follow-ups — all closed by 2026-07-17

Findings from [`audit/2026-07-08/02-new-findings.md`](../audit/2026-07-08/02-new-findings.md)
(reproductions and mechanism analysis there).

### P1 — silent semantic changes (no-silent-loss violations)

- [x] **Residual invalid output ships WITHOUT a warning (P1) — CLOSED at the architectural floor (2026-07-17, `469917a`).** Six-direction residue driven ~770→133; every statement transpiles validly or carries a warning; pg→pg discovery 287→0. Remainder needs schema-aware transpilation. Full log [`docs/DONE.md`](DONE.md) §36.

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **M3 final — DONE 2026-07-17 (`86f7c11`): IR-first is the expression engine.** The last architecture-plan milestone; scalar fragments route through the shared IR pipeline, text rewriters are the fallback (`UNIQUE_NO_IR_FIRST` kill-switch). Full log [`docs/DONE.md`](DONE.md) §39.
- [x] **Zero-reduction campaign (P2) — CLOSED at the floor, residue 133 → 16 (2026-07-17, `34d7338`).** Mechanism fixes (not waves) drove the six-direction live-syntax residue to 16, both Oracle directions 100.0% validity; remainder is the architectural floor (adversarial pg_regress, schema-dependent inference). Full log [`docs/DONE.md`](DONE.md) §40.
- [x] **Prune fallback-only text rewriters (P3) — CLOSED BY MEASUREMENT 2026-07-17.** 36/37 rewriters carry live fallback traffic; nothing safely prunable. Archived [`docs/DONE.md`](DONE.md) §42.

### P3 — hardening carry-overs (from 2026-07-02)

- [x] **Module growth — DONE 2026-07-17.** All three oversized modules split (procedural/parser package, transformer `_expr.py` seam, `core/transpiler/` package). Full detail [`docs/DONE.md`](DONE.md) §37.
- [x] **tsql→mysql procedural DATEADD nested INTERVAL — FIXED 2026-07-17.** The normalize walk hoists a tsql `DateAdd`'s interval into the unit slot (was `INTERVAL (INTERVAL '-1' MONTH) DAY`). Archived [`docs/DONE.md`](DONE.md) §42.

## Test-corpus expansion (P3) — wave campaign completed 2026-07-17

- Corpus wave campaign **COMPLETED and archived** (2026-07-15 →
  2026-07-17, waves 4–95; full per-wave log with measured commit
  hashes in `docs/DONE.md`, section "Wave campaign — corpus
  validity"; waves 96–102 are the M3-prereq/M3b record kept in the
  audit-follow-ups M3 item above). Final standings at `3fdfc88`:
  - pg-source (PostgreSQL regression corpus,
    `fixtures-corpus/pg_corpus_valid.sql`): →T-SQL **163** syntax
    failures (95.0% validity), →MySQL **131** (95.7%), →Oracle **89**
    (97.2%).
  - mysql-source (private local corpus, provenance undocumented by
    policy): →T-SQL **166** (97.2%), →PG **107** (98.2%), →Oracle
    **129** (97.8%).
  - Both residues are at the deep-singles floor (a full measure cycle
    buys ~−1); do not resume waves on these corpora without a new
    corpus or a fidelity target.

## Oracle procedural output — validity backlog (P1) — DONE (26 -> 0)

**Complete.** The T-SQL procedures fixture (32 objects) now transpiles to
**fully-valid Oracle** — `test_procedures_fixture_is_valid_live[oracle]` asserts it
(the `xfail` is gone). The Oracle live-validator queries `USER_ERRORS` after each
`CREATE` (Oracle compiles PL/SQL *lazily*, so `CREATE` succeeds even for an invalid
body) and recompiles to settle forward dependencies. Detailed why/how of each fix
is archived in [`docs/DONE.md`](DONE.md); the arc, in brief:

- **Expression/type:** string-`+` -> `||`; subquery / CAST assignments and RETURNs
  are SQL-only in PL/SQL, so via `SELECT … INTO v FROM DUAL` (or a nested block);
  `SELECT TOP (n)` -> `FETCH FIRST`; CLOB/`SQL_VARIANT` -> bounded `VARCHAR2`;
  `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)`/`VARCHAR(MAX)`-cast/character-CAST length;
  `DATEDIFF` sub-day + canonical layout; `TIME_STR_TO_TIME` unwrap.
- **Structure (features):** bare result `SELECT` -> `SYS_REFCURSOR` OUT; `EXEC
  sp_executesql` -> `EXECUTE IMMEDIATE … USING`; **table variable -> hoisted GTT**;
  **trigger DECLARE section**; **reassigned IN parameters shadowed with locals**;
  **inline split TVF -> `SYS.ODCIVARCHAR2LIST` function** + `TABLE(fn(…))` callers.
- **Rules:** OUT/IN OUT params take no DEFAULT; procedure/trigger RETURN carries no
  value; no `AS` before a table alias.
