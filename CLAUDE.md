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
  TDD cycle and test-assertion quality bar, the no-silent-loss invariant, the
  pre-commit verification gate, commit/push discipline, and performance rules
  (e.g. never build a string with `+=` in an input-proportional loop).

If a Skill tool is available, invoke the matching skill rather than only reading
the file. When guidance here and a skill disagree, the skill is authoritative.

## Quick reference

- **Backlog:** [`docs/TODO.md`](docs/TODO.md) is the single source of truth;
  completed work is archived in [`docs/DONE.md`](docs/DONE.md). Keep both current.
- **Tests:** `pytest` (serial) or `scripts/test-parallel.sh` (across cores, needs
  GNU parallel). The gate is black + isort + ruff + mypy + the full suite green.
- **Never** commit or push unless asked; branch off `main` first when you do.
