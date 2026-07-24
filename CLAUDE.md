# CLAUDE.md

Guidance for Claude Code (and any AI agent) working in this repository.

## Follow the project skills — every session

This project ships **skills** under [`skills/`](skills/). Read and follow them
at the start of every session; they override generic defaults.

- [`skills/SKILL-project-overview.md`](skills/SKILL-project-overview.md) —
  architecture of the Unique SQL transpiler (the two pipelines, the dialects,
  the functional-equivalence harness). **Load this first when resuming work.**
- [`skills/SKILL-development-workflow.md`](skills/SKILL-development-workflow.md) —
  how to make changes here: analyze-before-changing (mandatory first step), the
  **architecture guardrails** (no regex shape-patches in the script layer, no
  text-level SQL transforms, comments are trivia, never ship invalid output
  silently), the **wrong-path circuit breakers** (rule of three, neighbor
  test, escalation protocol — detect when you are patching instances of a
  class or going in circles), the TDD cycle and test-assertion quality bar,
  the no-silent-loss invariant, the pre-commit verification gate, commit/push
  discipline, and performance rules (e.g. never build a string with `+=` in an
  input-proportional loop).
- [`skills/SKILL-challenge-corpus.md`](skills/SKILL-challenge-corpus.md) —
  the `tests/fixtures/challenge/` regression corpus and its **red/blue**
  workflow: a RED role that only finds mis-transpilations (valid, non-repeated,
  anonymized source SQL) and a BLUE role that only fixes and locks them in. Load
  this when hunting for or fixing transpilation defects.

If a Skill tool is available, invoke the matching skill rather than only reading
the file. When guidance here and a skill disagree, the skill is authoritative.

## General behavioral guidelines

Source: [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills),
reproduced verbatim below. Where a project skill conflicts, the skill wins.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Quick reference

- **Latest audit:** [`audit/2026-07-24/`](audit/2026-07-24/) — ground truth on
  current defects. Its `08-prevention-plan.md` (root causes + mechanical rules
  now in force) and `09-fix-briefs.md` (per-finding pre-analysis) define how
  audit findings get fixed: **read the brief before fixing — never start a fix
  from scratch when a brief exists.**
- **Backlog:** [`docs/TODO.md`](docs/TODO.md) is the single source of truth and
  holds **pending work only**; when a backlog section closes, its summary moves
  to [`docs/MILESTONES.md`](docs/MILESTONES.md) and the detailed why/how is
  archived in [`docs/DONE.md`](docs/DONE.md). Keep all three current.
- **Tests:** `pytest` (serial) or `scripts/test-parallel.sh` (across cores, needs
  GNU parallel). The gate is black + isort + ruff + mypy + the full suite green.
- **Never** commit or push unless asked; branch off `main` first when you do.
- **Confidential:** `fixtures-private/` is a real client's SQL and this repo is
  public — extrapolate functionality, but never copy a real object name (table,
  proc, column, revision…) into committed tests/comments/messages. Anonymize. See
  the [development-workflow skill](skills/SKILL-development-workflow.md).
