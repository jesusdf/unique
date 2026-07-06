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

## 1. Oracle procedural output — validity backlog (P1)

The Oracle live-validator now queries `USER_ERRORS` after a `CREATE`
(Oracle compiles PL/SQL **lazily** — `CREATE` succeeds even when the body is
invalid, leaving the object `INVALID`). This exposed real bugs the old
execute-only check masked. `test_procedures_fixture_is_valid_live[oracle]` fails
until these are fixed; a sweep of the T-SQL procedures fixture -> Oracle showed
several classes:

- [ ] **`PLS-00204` `EXISTS` in PL/SQL** — `IF EXISTS(subquery) THEN` is invalid
      Oracle (no subquery in a boolean expr). Needs the creative rewrite
      (`FOR _ IN (SELECT 1 FROM (<subq>) WHERE ROWNUM = 1) LOOP … END LOOP;`, or a
      `COUNT(*) INTO v` for the ELSE case). *(Earlier "works on Oracle 23" was a
      false positive — the proc CREATE'd but was INVALID.)*
- [ ] **`PLS-00103` statement boundaries** (`Encountered "CREATE"/"SELECT"`) — a
      PL/SQL body emits a run-together or misplaced statement.
- [ ] **`PLS-00103` variable use** (`Encountered "V_COL_…"`) — a declared/used
      local variable is mis-emitted.
- [ ] **`PLS-00306` call to `'+'`** — the untyped `col + col` concat reaches
      Oracle as arithmetic on strings.
- [ ] **`ORA-00910` length too long** — a type-length mapping.
- [ ] **`ORA-00900`** on a set-based-trigger carrier — the `-- UNIQUE:` block for
      an unsupported trigger is followed by an invalid fragment.

**CI gap:** the live jobs do not run a real Oracle (only PG/MySQL/MSSQL), so none
of the above is caught in CI. Consider an Oracle service in the live job, or run
the validity sweep as a scheduled job.

## 2. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

- **Test-assertion quality** is measured by the nightly mutation job
  (`mutation.yml` / `scripts/mutation_test.py`) rather than a static to-do list:
  surviving mutants in its run summary are the live map of weakest assertions.
  Strengthen them opportunistically (the biggest foci at last measure were
  `emit._emit_function`/`_emit_date_diff` and `transformer._replace_oracle_date_add`).
  Differential result testing (`test_corpus_results_live.py`) guards against
  semantic regressions on every syntax-live CI run.

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
