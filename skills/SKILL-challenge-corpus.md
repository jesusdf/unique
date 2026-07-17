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

RED's only job is to **discover source SQL that transpiles incorrectly**. RED
does **not** touch `src/`.

1. **Generate candidate source SQL** for one source engine — small, focused,
   and exercising a real dialect feature (a scripting construct, a function, a
   type, an operator, a DDL form, a transaction/cursor/trigger shape). Draw
   ideas from each engine's reference docs and from real migration patterns.
2. **Prove it is syntactically valid source** before using it (a mis-transpile
   of invalid input is not a finding — see the earlier `IF NOT EXISTS`
   report). Validate with `sqlglot.parse(sql, read=<dialect>)` and/or the live
   engine (`docker compose -f docker-compose.test.yaml`, the live-syntax
   harness). Discard anything the source engine itself would reject.
3. **Transpile it to the other three engines** and look for a defect:
   - invalid **target** SQL (fails `sqlglot.parse` in the target / the live
     engine);
   - **silent loss or semantic drift** (a construct dropped, an operator or
     type changed meaning, an outer join inner-joined) — round-trip A→B→A to
     surface it;
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
does **not** invent new cases.

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

## Running the corpus

```bash
pytest tests/integration/test_challenge.py -q
```

Each fixture is split on its `-- CASE:` markers, and every case is transpiled to
the other three engines. Add the case first (RED), then the fix + assertion
(BLUE); the two never land in the same working session.
