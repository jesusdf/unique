---
name: unique-challenge-corpus
description: >
  Workflow skill for the "challenge" regression corpus of the Unique SQL
  transpiler. Use this skill when hunting for constructs the transpiler handles
  wrong, or when fixing them and locking in the fix. It defines two separated
  roles — a RED role that only finds mis-transpilations and a BLUE role that
  only fixes and prevents them — plus the rules every challenge case must obey
  (syntactically valid, non-repeated, anonymized) and how the corpus is stored
  and tested.
---

# Unique — Challenge Corpus (red/blue)

## What this is

`tests/fixtures/challenge/` is a **growing regression corpus of tricky source
constructs** — one script per source engine
(`challenge_sqlserver.sql`, `challenge_oracle.sql`,
`challenge_postgresql.sql`, `challenge_mysql.sql`). Each `-- CASE:` entry is a
construct that once transpiled wrong. `tests/integration/test_challenge.py`
guards the whole corpus: every case must transpile to every other engine
without an *unrecognized-construct* carrier, and each fixed case has a specific
assertion proving the correct output.

The goal is a **flywheel**: keep finding real mis-transpilations, keep fixing
them, and keep the fixes from regressing.

## Two roles, kept separate (like netsec red/blue)

The roles are deliberately split so neither biases the other — RED must not
soften a case because it looks hard to fix; BLUE must not wave a case away
because "it's rare". **A single working session acts as exactly one role at a
time.**

### 🔴 RED — find breaks only

RED's only job is to **discover source SQL that transpiles incorrectly**.

> **HARD RULE — RED NEVER FIXES.** RED must not modify `src/` (the transpiler)
> in any way: no function/type/operator mappings, no parser/emitter/transformer
> edits, no "quick fix while I'm here". If you spot the fix, **write it as a
> note in the finding for BLUE — do not apply it.** RED's only writes are:
> the `tests/fixtures/challenge/*.sql` scripts (new `[open]` cases),
> `tests/fixtures/challenge/FINDINGS.md` (the ledger), and — if the workflow
> itself needs it — this skill / the test harness that *records* findings.
> A commit that touches `src/` is by definition not a RED commit. Finding and
> fixing never happen in the same session.

1. **Generate candidate source SQL** for one source engine — small, focused,
   and exercising a real dialect feature (a scripting construct, a function, a
   type, an operator, a DDL form, a transaction/cursor/trigger shape). Draw
   ideas from each engine's reference docs and from real migration patterns.
2. **Prove the original is valid on a LIVE database** before using it — this is
   mandatory, not optional (a mis-transpile of invalid input is not a finding;
   see the earlier `IF NOT EXISTS` report). `sqlglot.parse` is too lenient to
   trust on its own. Bring up the engines and validate the source against the
   **real engine it is written for**:
   ```bash
   docker compose -f docker-compose.test.yaml up -d    # pg, mysql, mssql, oracle
   ```
   Use `tests/helpers/live_validation.py` — `make_validator(dialect, url).validate(sql)`
   parses/compiles without committing (T-SQL rolled-back txn, PG rolled-back txn,
   MySQL throwaway DB, Oracle create-drop + `USER_ERRORS`). Connection URLs:
   `postgresql://unique:unique@localhost:5433/unique`,
   `mysql://root:root@localhost:3307/unique`,
   `mssql://sa:Unique_Strong!Pass1@127.0.0.1:1433/master`,
   `oracle://system:oracle@localhost:1521/FREEPDB1`
   (`docker update --memory 3g unique-oracle-1` before an Oracle run). Discard
   anything the source engine rejects. Standalone statements, procedures,
   triggers, functions, views, and any other object all count as source.
3. **Transpile it to the other three engines** and look for a defect:
   - invalid **target** SQL (fails `sqlglot.parse` in the target / the live
     engine);
   - **a different result — this is a defect even when nothing errors.** For a
     standalone query, transpiled output that runs cleanly but returns a
     *different result set* (different rows, values, order when ordered, or
     types) than the original is a **functional-equivalence defect**, full stop.
     The strongest RED check is therefore to **execute both and compare**: run
     the original on its engine, run the transpiled output on the target
     engine, and diff the result sets. Example: `SELECT 1` must return one row
     with value `1` on every target; `SELECT 1 || 2` (PostgreSQL) must return
     `'12'`, so emitting `1 + 2` (= `3`) on T-SQL is a defect even though it
     runs. Live *syntax* validation passes these — only executing and comparing
     catches them.
   - **silent loss or semantic drift** (a construct/clause dropped — a FK
     `ON DELETE` action, a `CHECK`, an ENUM's values, a `WITH TIES`, a
     collation; an operator or type that changed meaning; an outer join
     inner-joined) — round-trip A→B→A to surface it, then confirm by executing.
   - an **unrecognized-construct carrier** (`UNIQUE: Unhandled`,
     `could not translate`) where a real translation is possible;
   - a **mislabeled or missing warning** (a lying warning is a defect too).
4. **De-duplicate.** If the corpus already covers that *mechanism* (not just
   that spelling), it is not a new case — the corpus holds **non-repeated**
   constructs. Skip near-duplicates; one construct per entry.
5. **Record the case, not the fix.** Append the *smallest* reproduction to the
   right `challenge_<engine>.sql` under a `-- CASE: <short description>` header,
   **anonymized** (never a real object name from a private fixture — see the
   development-workflow skill). Note the wrong output and the expected output in
   your hand-off (a `docs/TODO.md` item and/or a failing test). Hand off to BLUE.

RED's deliverable: new `-- CASE:` entries that are valid source, currently
transpile wrong, and are not already covered.

### 🔵 BLUE — fix and prevent only

BLUE takes RED's cases and makes them transpile correctly, **durably**. BLUE
does **not** invent new cases. BLUE is the **only** role that edits `src/`;
it flips each finding it closes from `-- CASE[open]:` to `-- CASE[fixed]:` and
removes it from `FINDINGS.md`.

1. **Fix at the right layer**, obeying the architecture guardrails in the
   [development-workflow skill](SKILL-development-workflow.md): route through the
   AST paths (lexer / parser / transformer / IR converter / emitter), never a
   regex shape-patch in the script layer, never a text-level semantic rewrite,
   never ship invalid output silently. Run the **circuit breakers** (rule of
   three, neighbor test, green-but-unmoved) — a challenge case is usually one
   instance of a *class*; fix the class.
2. **Lock it in.** Add a specific assertion in `test_challenge.py` (target idiom
   present, source idiom absent, identity-mutation-proof — see the
   development-workflow assertion bar), plus the generic no-unrecognized-carrier
   guard already covers the new `-- CASE:`.
3. **Probe neighbors.** Fixing one case exposes its combinatorial neighbors
   (± comment, ± BEGIN/END, sibling statement kinds, all targets); fix and cover
   them together so BLUE is *preventing* the class, not patching one point.
4. **Full pre-commit gate** (black + isort + ruff + mypy + the suite green), then
   commit with the case + fix + test together, and mark the `docs/TODO.md` item
   done with a one-line how.

BLUE's deliverable: the case transpiles correctly on every target (or degrades
to a *documented* carrier + warning when there is genuinely no equivalent), with
a regression test and updated docs.

## Rules every case must obey

- **"Runs without error" is NOT the bar — same result is.** For a standalone
  query, correctness means the transpiled output returns the *same result set*
  as the original on the target engine. Output that compiles and runs but yields
  a different value/row set/order is a **defect** (a functional-equivalence
  failure), not a pass. Confirm by executing both and comparing, not by eyeing
  the SQL. (`SELECT 1` → one row, value `1`, everywhere.)
- **Syntactically correct source.** Validate before adding; invalid input is not
  a finding.
- **Non-repeated.** One construct per `-- CASE:`; skip anything whose mechanism
  is already covered.
- **Smallest reproduction.** The least SQL that still reproduces the defect.
- **Anonymized.** Generic names only (`t`, `c`, `get_top_rows`, `row_limit`);
  never a real table/proc/column/schema/revision from `fixtures-private/` or a
  license-restricted corpus.
- **A documented degrade is a valid outcome**, not a defect — when a construct
  has no faithful cross-engine equivalent, the correct result is a carrier +
  warning + `docs/03-unsupported.md` entry, not an error.

## Case status tags

Each `-- CASE:` header carries a status so the committed test can stay green
while RED accumulates a backlog:

- `-- CASE[open]: <desc>` — RED-found, **not yet fixed**. `test_challenge.py`
  only smoke-checks it (must not crash); its output is known-wrong on some
  target. Detail lives in `FINDINGS.md`.
- `-- CASE[fixed]: <desc>` — BLUE closed it. Strictly guarded: must transpile to
  every target with no unrecognized carrier, plus a specific assertion.
- `-- CASE: <desc>` (untagged) — treated as `fixed`.

RED adds `[open]`; BLUE flips to `[fixed]`. A RED session that produces green
`[fixed]` cases has overstepped into BLUE's job.

## Running the corpus

```bash
pytest tests/integration/test_challenge.py -q
```

Each fixture is split on its `-- CASE:` markers, and every case is transpiled to
the other three engines. Add the case first (RED), then the fix + assertion
(BLUE); the two never land in the same working session.
