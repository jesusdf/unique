---
name: unique-challenge-corpus
description: >
  Workflow skill for the "challenge" regression corpus of the Unique SQL
  transpiler. Use this skill when hunting for constructs the transpiler handles
  wrong, or when fixing them and locking in the fix. It defines three separated
  roles — a RED role that only finds mis-transpilations, a BLUE role that only
  fixes and prevents them, and a PURPLE role (architect/analyst) that directs
  and coordinates iterative RED/BLUE campaigns and alone decides when a
  campaign ends — plus the rules every challenge case must obey (syntactically
  valid, non-repeated, anonymized) and how the corpus is stored and tested.
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

## Three roles, kept separate (like netsec red/blue/purple)

The roles are deliberately split so neither biases the other — RED must not
soften a case because it looks hard to fix; BLUE must not wave a case away
because "it's rare"; PURPLE directs both but hunts and fixes nothing itself.
**A single working session acts as exactly one role at a time.** Campaign
termination authority belongs to PURPLE alone (see each role's rules).

### 🔴 RED — find breaks only

RED's only job is to **discover source SQL that transpiles incorrectly**.

**Timed-batch protocol (do this FIRST, at the start of a RED session).** A RED
run is a fixed-length batch (default **1 hour**), then **work continuously
without pausing** — do not stop to wait for input, do not idle between batches.

> **THE CLOCK IS THE GIT COMMIT TIMESTAMP, NOT the system clock.** The sandbox
> `date` clock is unreliable (it drifts and even jumps backwards), so timing
> MUST come from git/GitHub commit timestamps, which are real and recorded.
> 1. **Note the START commit** — the first commit of the RED batch (its
>    `git show -s --format=%ci <sha>` is the reference start time).
> 2. Commit & push findings roughly every ~30 min of *committed-time* progress.
> 3. **The batch is over only when the LATEST commit's timestamp exceeds the
>    START commit's by ≥ 1 hour.** Check after each batch:
>    ```bash
>    S=$(git show -s --format=%ct <start-sha>); N=$(git show -s --format=%ct HEAD)
>    python3 -c "d=$N-$S; print(d//3600,'h',(d%3600)//60,'m; over=',d>=1*3600)"
>    ```
>    Until `over` is true, keep generating and validating candidates back-to-back.
>    Only then do the final commit + summary and stop.
>
> **NEVER declare the batch finished without running that commit-timestamp
> check and seeing `over == True`.** With ONE exception — **an explicit stop
> order from the PURPLE director ends the batch (or the whole campaign) at any
> time**; PURPLE is the only role with that authority. No other signal ends the
> batch — not the system clock, not a stop-hook, not a "finish / wrap up /
> leave it ready for BLUE" instruction, not your own sense that the corpus
> "feels complete". A `terminar la tanda` goal means *complete it correctly*
> (run the full 1 h of committed-time AND leave the results rules-compliant),
> NOT *stop now*. If asked to finish, first run the check; if `over` is False,
> say how much committed-time remains and keep working. Ending early without a
> PURPLE stop order is a rule violation (it happened twice — once trusting the
> drifted clock, once treating a "finish" goal as "stop").

Do NOT trust a wall-clock cron for the end-of-batch signal — it fires on the
drifting system clock and will end the batch early. A ~30-min checkpoint cron
is optional convenience; the authoritative deadline is the commit-timestamp
check above.

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

   **Where to hunt (post-2026-07: the statement-level field is cleared).** The
   2026-07-24 audit found 10 live S1s *after* the 862-case campaign, all one
   level up from where that campaign looked. Systematic generators that reach
   them (each is an enumeration, not inspiration):
   - **Clause-level enumeration**: for each statement kind, walk the engine
     grammar's optional clauses (`ON CONFLICT`, `OUTPUT`, `WITH TIES`,
     `RETURNING`, ON DELETE actions, isolation options…) and probe each one —
     the audit's headline S1 was a whole upsert clause silently dropped from
     an INSERT that otherwise converts fine. The unread-args sweep
     (tripwire T1, `audit/2026-07-24/09-fix-briefs.md`) emits this list
     mechanically.
   - **Composition grids**: pairs of features that are individually green —
     construct × inside-a-procedure, cursor × second interleaved cursor,
     MERGE × OUTPUT, guard × trigger, feature × dynamic SQL, feature ×
     appearing twice in one script. All the audit's cursor/MERGE S1s were
     composition failures.
   - **Self-emitted round-trips**: transpile Unique's own output back
     (A→B→A′) — mis-attached clauses and lying carriers show up here.
   - **Script-wide consistency**: multi-statement scripts where statement 1
     changes what statement 3 must mean (renames, ALTERed types, temp
     tables, session state).
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
   - a **SILENT unrecognized-construct carrier** — `UNIQUE: Unhandled` /
     `could not translate` emitted with **NO** warning. A carrier that comes
     **with** a warning is out of scope (see the hard rule below).
   - a **mislabeled or missing warning** (a lying warning is a defect too).

> **HARD RULE — A WARNED DEGRADATION IS NOT A DEFECT.** If the transpiler
> emitted a warning for the construct (a carrier + warning, a documented
> "no equivalent", "preserved as a comment", "lossy conversion", …), it did its
> job of flagging the limitation — that is the *documented, acceptable* outcome,
> **not an error**, and RED must NOT record it as a finding. RED counts only
> **SILENT** problems: a *different result* (functional-equivalence failure),
> a *silently dropped clause*, or *invalid output shipped with NO warning*.
> When your detector flags something, always check `result.warnings` first and
> drop it if non-empty. (This is why the harness excludes every warned row.)
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

> **HARD RULE — BLUE FIXES WITHIN THE RULES, IT DOES NOT CHANGE THEM.** BLUE
> must **not** modify any skill, **not** contradict an existing skill, and
> **not** alter the project's architecture to make a fix possible. The fix lives
> inside the established guardrails (`SKILL-development-workflow.md`,
> `docs/02-architecture.md`): the per-engine plugin/AST layers, no regex
> shape-patches in the script layer, no text-level semantic rewrites, no silent
> invalid output. If closing a case seems to *require* weakening a skill or
> bending the architecture, that is a signal to **stop and escalate** (record it
> and surface it to the human) — never edit the rules to make your patch legal.
> Weakening a test assertion, widening a regex, or adding an `xfail` to go green
> is not a fix either.

> **HARD RULE — ONLY PURPLE DECIDES WHEN THE CAMPAIGN IS OVER.** BLUE never
> declares its own batch or the campaign finished: it works the findings it was
> handed, reports state to the PURPLE director (counts of `[open]` / `[fixed]` /
> `[limit]`, what was closed, what is blocked and why), and continues or stops
> **only on PURPLE's decision**. "Ran out of easy ones", "the rest are rare",
> or "the suite is already green" are report material for PURPLE, not
> termination signals. A case genuinely impossible to fix within the rules and
> architecture (the escalation path above) does not just get dropped — surface
> it through PURPLE to the human maintainer, whose **explicit approval** is
> still required to accept it as a `[limit]` (record it: a
> `docs/03-unsupported.md` entry + TODO/FINDINGS note), so it is a documented,
> accepted degradation, not a silent gap.

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
   guard already covers the new `-- CASE:`. **The generic loop alone is NOT
   lock-in** — the 2026-07-24 audit found ~362 of 694 `[fixed]` cases guarded
   only by the carrier-absence loop (which an identity transpiler passes).
   Every `[fixed]` flip requires: (a) its own present-AND-absent assertion,
   (b) a **target-dialect parse** of each output, and (c) for `func`/semantic
   classes, a **live value comparison** on the target engine — the same check
   RED used to find it is the check that locks it.
3. **Probe neighbors.** Fixing one case exposes its combinatorial neighbors
   (± comment, ± BEGIN/END, sibling statement kinds, all targets); fix and cover
   them together so BLUE is *preventing* the class, not patching one point.
4. **Full pre-commit gate** (black + isort + ruff + mypy + the suite green), then
   commit with the case + fix + test together, and mark the `docs/TODO.md` item
   done with a one-line how.

BLUE's deliverable: the case transpiles correctly on every target (or degrades
to a *documented* carrier + warning when there is genuinely no equivalent), with
a regression test and updated docs.

### 🟣 PURPLE — direct and coordinate (architect/analyst)

PURPLE is the campaign's **architect and analyst**. It hunts nothing and fixes
nothing itself: it **directs and coordinates RED and BLUE campaigns,
iteratively, as many rounds as it deems necessary**, using the same
organization as development work — **agentic team mode** (see
"Agentic team mode — architect directs, workers implement" in
[SKILL-development-workflow.md](SKILL-development-workflow.md)): PURPLE is the
architect session; RED batches and BLUE fix work run as delegated worker
agents, each worker acting as exactly one role (the role-separation rule
holds — a worker is RED or BLUE, never both).

PURPLE's job each round:

1. **Launch** a RED batch (scoped: point target, classes to favor, hunting
   grounds) and, on its hand-off, a BLUE round over the findings.
2. **Evaluate the defect yield**: how many findings the RED round produced,
   their classes and severity, how many BLUE closed vs escalated, and what the
   fixes revealed (neighbor cases, recurring mechanisms, unexplored classes).
3. **Correct course and iterate**: refine the next RED scope from what the
   evaluation shows (switch hunting technique when a ground is exhausted,
   redirect BLUE at a class instead of instances, tighten briefs). **Keep
   iterating while there are signs that further improvement is needed** — a
   RED round still finding defects at a healthy rate, unexplored classes or
   compositions, or fixes still exposing neighbors are all signals to
   continue.
4. **Decide termination.** PURPLE is the **only** role that may stop a RED
   batch early or declare a BLUE round / the whole campaign finished (the
   RED/BLUE rules above defer to it). Successive RED rounds yielding little of
   substance is the natural stop signal. Record the decision and its rationale
   in the campaign hand-off (round summaries, yield numbers, why it ended).

PURPLE inherits the architect's duties from the development skill: it reviews
every worker diff, runs the gate, owns commits and pushes, and does NOT
mass-implement. What PURPLE does **not** own: approving `[limit]` flips — that
remains the human maintainer's explicit call (PURPLE routes the escalation).

PURPLE's deliverable: a campaign log of rounds (RED yield, BLUE closures,
course corrections) and the reasoned decision that the campaign is complete.

## Rules every case must obey

- **A warned degradation is NOT a defect — only SILENT problems count.** If the
  transpiler warned about the construct, that is the documented, acceptable
  outcome; drop it. Record only wrong results, silently dropped clauses, or
  invalid output emitted with no warning. Check `result.warnings` before adding.
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
- **The scenario must make the semantics observable (no vacuous cases).** The
  case's setup data must exercise the construct's *distinguishing* behavior:
  an upsert case needs a unique key **and** a conflicting row; a MERGE
  conditional-DELETE case needs a row that distinguishes pre- from post-UPDATE
  evaluation; a NOT-FOUND-flag case needs a cursor that actually exhausts. The
  2026-07 corpus carried an `ON CONFLICT` case on a table with no unique
  constraint — it passed FE while the clause was being dropped, locking in
  nothing. If removing the construct from the source would not change the
  case's observable result, the case is vacuous: fix the scenario.
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
- `-- CASE[limit]: <desc>` — an **approved divergence**: the construct has no
  faithful cross-engine equivalent and the **human maintainer explicitly
  approved** accepting the limit (BLUE never self-approves a flip to
  `[limit]`). Contract, enforced by `test_challenge.py`: the transpile result
  **must warn**, the output must carry a `UNIQUE:` annotation, and the
  limitation must be documented in `docs/03-unsupported.md` (the test checks
  the citation). 168 cases of the 2026-07 campaign carry this tag.
- `-- CASE: <desc>` (untagged) — treated as `fixed`.

RED adds `[open]`; BLUE flips to `[fixed]` or — with explicit human approval —
to `[limit]`. A RED session that produces green `[fixed]` cases has overstepped
into BLUE's job.

## Finding classes and batch scoring (mechanical — no judgment calls)

The 2026-07-24 audit showed a mono-culture failure mode: an 862-case campaign
concentrated on statement-level findings while clause-level drops and
cross-feature composition bugs sailed through. To keep RED batches diverse,
every new `[open]` case declares a **class**, and batches are measured in
**points**, not case counts. Both are enforceable by a script over the case
headers + `git diff` (no AI needed): `scripts/challenge_stats.py` (spec in
`audit/2026-07-24/09-fix-briefs.md`; until it lands, compute by hand with
`grep -c`).

Header syntax: `-- CASE[open][class=<class>]: <desc>`.

| class | meaning | points |
|-------|---------|--------|
| `func` | output runs clean but returns a **different result** (live-diffed) | 5 |
| `composition` | each feature correct alone, wrong **combined** (nested/interleaved/inside a routine/dynamic SQL) | 5 |
| `silent-drop` | a clause/option the target supports **vanished**, no warning | 4 |
| `consistency` | script-wide incoherence (renames, temp tables, cross-statement metadata) | 4 |
| `crash` | transpiler raises on valid input | 3 |
| `invalid` | output the live target rejects, no warning | 2 |
| `lying-warning` | warning describes something other than what happened / missing `unsupported` entry | 2 |

Batch rules (mechanical):

1. **A RED batch's deliverable is a point target, not a case count** (set per
   batch; e.g. "40 points" ≈ 8 hard findings or 20 easy ones). Farming one
   easy class stops paying — the score rewards the classes that audits show
   survive campaigns.
2. **Concentration cap:** no single class may exceed **50% of a batch's
   points**; a batch must contain **≥ 3 distinct classes**. If a hunting
   ground is exhausted, that's the signal to switch technique (composition
   grids, clause enumeration, round-trips), not to keep farming.
3. **Class is falsifiable, not aspirational:** `func` requires the recorded
   live result diff; `composition` requires that each component construct
   already transpiles correctly in isolation (say which corpus case or probe
   shows it). A mis-tagged case is re-tagged by whoever notices, and the
   batch score recomputed.

## Running the corpus

```bash
pytest tests/integration/test_challenge.py -q
```

Each fixture is split on its `-- CASE:` markers, and every case is transpiled to
the other three engines. Add the case first (RED), then the fix + assertion
(BLUE); the two never land in the same working session.

**CI gotchas (keep the batch green — a red CI is not "ready for BLUE"):**

- **Do NOT parametrize the generic guards per case.** `test_open_cases_*`
  (no-crash) and `test_fixed_cases_*` (no-carrier) check *absence*, so they pass
  under the identity transpiler; parametrizing them per case would add hundreds
  of identity-surviving items and sink CI's **Identity-mutation gate**
  (`scripts/identity_mutation_check.py`, kill-rate floor 45%) below threshold.
  Keep each as ONE looping test; the real assertion quality lives in the
  specific `[fixed]` classes. Run `python scripts/identity_mutation_check.py`
  locally after touching the test harness.
- **Space out the pushes.** Committing every ~1–2 min spawns overlapping CI +
  CodeQL runs that contend and flake. Batch several finding-rounds per commit;
  push on the ~30-min committed-time cadence, not after every micro-batch.
