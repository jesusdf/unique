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

## 1. Corpus-sweep function/type gaps (P2)

Surfaced by `test_corpus_live.py` and annotated `-- @xfail` in the corpus. Fix,
then remove the annotation (the sweep flags it once it starts passing):

- [ ] MySQL `NOW()`/`CURDATE()` -> Oracle/SQL Server (SYSTIMESTAMP/GETDATE, etc.).
- [ ] Oracle `NVL2`, `DECODE` -> CASE for the other targets.
- [ ] Oracle `TO_CHAR`/`TO_DATE` format models; MySQL 2-arg `DATEDIFF(a,b)`.
- [ ] `TRUNC(number)`, T-SQL `CONVERT(type, expr)`, `CAST(... AS BOOLEAN/INT)`
      per target; `CURRENT_DATE` emitted with parens; T-SQL string `+` chain.

## 2. Packaging (P3)

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
