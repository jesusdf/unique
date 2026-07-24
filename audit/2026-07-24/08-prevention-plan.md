# 08 — Prevention plan: why the defect classes recurred, and what changes

Companion to this audit's findings docs. The question it answers is not "what
is broken" (docs 01–07) but "**why did the process let it happen again**, and
which adjustments to the instructions (skills), tooling and cadence stop each
class from growing back". The companion
[09-fix-briefs.md](09-fix-briefs.md) pre-analyzes every open finding so the
fixing session lands the right fix first time.

Context: the project *did* execute the 2026-07-08 architecture plan (M0–M4
complete, both prior S1s fixed, validity 99.8–100%, an 862-case RED/BLUE
campaign fully resolved) — and this audit still found 10 new live-verified
S1s, two guardrail violations, a 9,992-line emitter, stalled ratchets and 10
confidentiality leaks. Each of those has a *process* root cause, listed below.

## Root causes of the recurrence

- **RC1 — RED's finding shape was statement-level and isolated.** The campaign
  probed single statements on live engines, so it systematically missed
  (a) **clause-level drops** (`ON CONFLICT` vanishing from an INSERT that
  otherwise works), (b) **cross-feature composition** (nested cursor loops,
  MERGE + OUTPUT — each feature green alone), and (c) **vacuous scenarios**:
  the corpus's own `ON CONFLICT` case passed FE because its table had no
  unique constraint, so the dropped clause was a no-op in the test but not in
  real life.
- **RC2 — the sqlglot unread-args leniency had no mechanical guard.** It was
  already a *documented lesson* (workflow skill), but prose lessons don't fire
  on the 1,349th line of a converter. N1/N3/N4 are all "sqlglot parsed it,
  the converter never read the arg, nothing warned".
- **RC3 — the guardrail moratorium was scoped to the layer that had the
  problem in July, not to the pattern.** The script-layer regex ban held;
  under BLUE's throughput pressure the same cascade **relocated** into
  `converter/emit.py` (82 `re.sub`s, 57 "wave NNN" instance-patch comments,
  two post-emit text-mapping violations). Debt migrates to whichever layer the
  rules don't watch.
- **RC4 — ratchets don't raise themselves.** The identity floor (0.45 vs
  measured 0.66) and the nightly mutation floors (untouched since 07-06)
  have no owner and no cadence, so the gap becomes head-room that absorbs
  regressions instead of preventing them.
- **RC5 — docs claims are hand-written numbers with no re-measure trigger.**
  The compatibility matrix carried a ✅ for a construct that is silently
  dropped; STATUS carried two-raises-stale floor numbers. The "no ✅ without a
  probe test" rule existed but nothing enforces it at edit time.
- **RC6 — the confidentiality policy had no tool.** Leaks entered exactly
  where a human writes fast: tests derived from a private repro, and commit
  messages summarizing them. Nothing scanned either against the private
  corpus until this audit built the sweep.
- **RC7 — "case closed" was allowed to mean less than "class locked".**
  ~362 of 694 `[fixed]` challenge cases are guarded only by the generic
  carrier-absence loop; challenge outputs are never target-parsed or
  live-executed in CI. A campaign metric counted in cases rewards closing the
  case, not the class — three of the new S1s are in the MERGE feature the
  campaign itself added and marked green.

## Measures

### A. Normative — skills/instructions (applied with this audit)

| # | Change | Where | Kills |
|---|--------|-------|-------|
| A1 | Guardrail 2 extended from "script layer" to **every layer including post-emit**, with an explicit whitelist of sanctioned regex uses (lexing, trivia, carrier reconciliation, warned pre-parse strips). A function/type/operator/construct mapping via regex on SQL text is a violation anywhere. | dev-workflow skill, guardrail 2 | RC3 |
| A2 | **New guardrail: consume every semantic sqlglot arg.** Converting a node means accounting for every `node.args` key — convert it or degrade with a warning. Manual checklist until the tripwire (T1) lands. | dev-workflow skill, guardrail 7 | RC2 |
| A3 | **Neighbor test gains a composition dimension**: ± inside a routine body, ± a second interleaved instance (cursors!), ± OUTPUT/RETURNING, ± dynamic SQL, ± twice in one script. | dev-workflow skill, circuit breaker 2 | RC1b |
| A4 | **Scenario-adequacy rule**: a challenge/FE case must construct data that makes the distinguishing semantics observable (an upsert case needs a unique key + a conflicting row); a case that passes vacuously locks in nothing. | challenge skill, case rules | RC1c |
| A5 | **RED 2.0 hunting map**: clause-level enumeration (probe every clause of a statement kind, not the statement once), composition grids, self-emitted-output round-trips, script-wide consistency — the statement-level field is cleared; this is where the residue lives. | challenge skill, RED section | RC1 |
| A6 | **[fixed] bar raised**: the generic no-carrier loop is explicitly NOT lock-in; every flip needs a dedicated present-AND-absent assertion plus target-dialect parse; semantic cases need a live value check. `[limit]` tag documented (it was load-bearing but undocumented). | challenge skill, BLUE + tags | RC7 |
| A7 | **Ratchet cadence**: the release checklist re-measures identity kill rate, nightly mutation scores and the architecture ratchets (T3) and bumps floors to measured-minus-margin; a floor >10 points below measured is itself a finding. | dev-workflow skill, releasing | RC4 |
| A8 | **Commit-message vocabulary rule** (never quote identifiers from a private repro in a message — use the case ID) + pre-push leak check once T2 lands. | dev-workflow skill, confidential fixtures | RC6 |
| A9 | **Finding classes + batch scoring** (maintainer proposal, 2026-07-24): every `[open]` case declares a class (`func` 5 / `composition` 5 / `silent-drop` 4 / `consistency` 4 / `crash` 3 / `invalid` 2 / `lying-warning` 2 points); RED batches target **points, not case counts**, with a concentration cap (no class >50% of a batch's points, ≥3 distinct classes). Rewards the classes that survive campaigns; mechanically checkable from case headers + `git diff` (T5) — no AI in the loop. | challenge skill, "Finding classes and batch scoring" | RC1, RC8-adjacent |

### B. Mechanical — tooling and CI (specs in [09-fix-briefs.md](09-fix-briefs.md))

| # | Tool | Kills |
|---|------|-------|
| T1 | **Unread-args tripwire** in the converter: warn whenever a known-semantic sqlglot arg on a converted node was never read (allowlist for the genuinely ignorable); one-off sweep mode to enumerate today's unread args as RED findings in bulk. Rollout warn-only → gate. | RC2 |
| T2 | **`scripts/private_leak_check.py`**: productize this audit's token-intersection sweep; derives tokens from `fixtures-private/` at runtime (the script contains none), checks the diff-to-push and new commit messages, skips silently where the private corpus is absent (public CI unaffected). | RC6 |
| T3 | **Architecture ratchet gates**: a script + CI step asserting monotonic non-growth on measured debt — `emit.py` line count, `re.sub` count in emitter modules, dialect string-compares in shared modules, C901 offender count. Same spirit as the identity floor: numbers make circling visible; prose doesn't. | RC3, the anti-circling backstop |
| T4 | **Challenge outputs target-parsed (and periodically live-executed) in CI**, so a `[fixed]` case cannot silently emit unparseable target SQL. | RC7 |
| T5 | **`scripts/challenge_stats.py`**: parses `-- CASE[...][class=...]` headers, reports the corpus class/status distribution, and scores a batch (cases added since a given git ref) against the A9 point/concentration rules. Pure text processing — deterministic, CI-runnable, needs no AI. | RC1, RC7 |
| T6 | **Complexity/compliance lint, ratcheted**: enable `ruff` `C901` (cyclomatic complexity) plus `PLR0912`/`PLR0915` (branch/statement counts) with ceilings set to today's worst offenders and ratcheted down via T3 (107 current C901 offenders; `_emit_function` CC 355 — the rule isn't even on today). New code meets the real ceiling; legacy burns down by number. | RC3 |
| T7 | **Stale-floor detector**: the identity-mutation CI gate additionally fails when the floor sits >15 points below the measured rate — a stale ratchet becomes a red build, not an audit finding three weeks later. (The release checklist bumps at >10; CI hard-fails at >15 so it cannot be forgotten indefinitely.) | RC4 |

### C. Docs — drift repair + claim discipline

The 13 findings of [06-docs-drift.md](06-docs-drift.md) are applied with this
audit (matrix un-✅'d where reality disagrees, floors/date-stamped numbers
refreshed, layout sketches match the real tree). Standing rule reasserted:
a measured number in STATUS/docs carries the command that produced it and a
date; a ✅ in the matrix carries a probe test. Point-in-time docs are re-checked
at every release (the existing documentation-discipline section now has the
ratchet checklist to hang on).

### D. Process — cadence and the analysis-first rule

1. **Analysis-first fixing (the anti-circling core).** No audit finding is
   fixed without a brief: verified root cause, ONE chosen approach, rejected
   alternatives, tests-first list, acceptance criteria, blast radius
   ([09-fix-briefs.md](09-fix-briefs.md) covers every current finding; a new
   finding gets a brief before it gets a fix). A session that starts patching
   without a brief is the wrong-path pattern the circuit breakers exist for.
2. **Campaign design includes a debt checkpoint.** Any future wave/BLUE-style
   campaign runs the architecture ratchets (T3) *during* the campaign (every
   ~50 closed cases), not after — the emit.py cascade grew in exactly one
   16-day campaign window.
3. **Audit cadence.** A full audit per minor release or ~2 weeks of campaign
   work, whichever first; its remediation-verification doc is the ground truth
   the next audit starts from (this file's RCs are the checklist).
4. **Leading indicators for the next audit** (how we know this plan worked,
   beyond "fewer S1s"): floors within 10 points of measured; emitter ratchet
   numbers moving down, zero new `re.sub` in emitters; unread-args tripwire
   silent on the corpus; leak check green over the window; challenge `[fixed]`
   single-tier. If those hold and S1s still appear, the plan itself gets
   re-audited.
