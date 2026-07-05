# Unique — Pending Work

This document tracks **outstanding** work, ordered by priority. Completed work
has been archived in [`docs/DONE.md`](DONE.md) (with the detailed why/how of
each fix); `docs/STATUS.md` summarizes the project state at a higher level.

Last reviewed: 2026-07-05. The functional-equivalence and audit-remediation
backlogs are complete and archived in [`docs/DONE.md`](DONE.md) (§18); only
packaging remains.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## 1. Test-assertion hardening (P2) — from the mutation run

`scripts/mutation_test.py` (nightly `mutation.yml`) measured how many injected
mutations the tests kill. Survivors = lines executed but **not verified**. Review
the tests for the weakest functions and add assertions (target idiom present AND
source idiom absent AND, ideally, result compared). Scores below are a *lower
bound* (the fast runner does not cover every path — e.g. `_base.py`/`harvest.py`
procedural code is killed by suites not in the runner).

Baseline scores (killed/total): convert.py 73%, emit.py 69%, `_base.py` 46%,
harvest.py 59%, transformer/base.py 62%.

- [ ] **emit.py** (130 survivors) — the biggest focus: `_emit_function` (28),
      `_emit_date_diff` (20), `_emit_create_table` (12 — column-flag defaults),
      `_emit_update_oracle_subquery` (9), `_convert_date_format` (8),
      `_emit_date_add` (8). Many per-dialect emit branches are un-asserted.
- [ ] **transformer/base.py** (201 survivors) — `_replace_oracle_date_add` (35 —
      single biggest weak spot), `_transform_trigger` (13), `_transform_data_type`
      (11), `_transform_function` (8), `_transform_cross_table_update` (8).
- [ ] **_base.py / harvest.py** — `_split_top_level_commas`, `_looks_like_string`,
      `wrap_oracle_date_arg`, `harvest_proc_date_params` (partly runner-coverage
      bias; re-measure with the procedural runner).
- [ ] **convert.py** (23 survivors) — column-flag defaults (`nullable`,
      `primary_key`, `unique`, `identity`), DISTINCT detection, DROP-without-IF-EXISTS.

## 2. EXCEPT / INTERSECT not converted (P2) — found by differential result test

`exp.Except`/`exp.Intersect` are not `exp.Union` subclasses in the pinned
sqlglot, so `convert_expression` never dispatches them to `_convert_union`
(which already handles them via `_set_op_type`) — a standalone
`A EXCEPT B` / `A INTERSECT B` degrades to a `-- UNIQUE:` carrier instead of
transpiling. Dispatch them to `_convert_union` and add corpus + result-diff
coverage.

## 3. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally emitted as
comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, …).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as a carrier type with the
  original preserved in a `/* UNIQUE: … */` comment, plus a warning). The
  round-trip **restores the original** on a transpilation back to a supporting
  engine — verified for `%TYPE` via the procedural path and for physical index
  clauses via the DML path (`%TYPE` is PL/SQL-only, so it never appears in a
  DML/DDL statement).
