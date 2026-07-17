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

## Quick reference

- **Backlog:** [`docs/TODO.md`](docs/TODO.md) is the single source of truth;
  completed work is archived in [`docs/DONE.md`](docs/DONE.md). Keep both current.
- **Tests:** `pytest` (serial) or `scripts/test-parallel.sh` (across cores, needs
  GNU parallel). The gate is black + isort + ruff + mypy + the full suite green.
- **Never** commit or push unless asked; branch off `main` first when you do.
- **Confidential:** `fixtures-private/` is a real client's SQL and this repo is
  public — extrapolate functionality, but never copy a real object name (table,
  proc, column, revision…) into committed tests/comments/messages. Anonymize. See
  the [development-workflow skill](skills/SKILL-development-workflow.md).
