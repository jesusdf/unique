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
execute-only check masked (and the CI *does* run a live Oracle — the failures
were simply invisible with the execute-only check).
`test_procedures_fixture_is_valid_live[oracle]` `xfail`s until these are fixed.

**Done:** the T-SQL string-`+` concatenation in procedural bodies now becomes
Oracle `||` (`PLS-00306` cleared). A sweep of the T-SQL procedures fixture ->
Oracle leaves **24 INVALID** objects across these classes; each is a distinct,
non-trivial procedural transformation:

- [ ] **`PLS-00103` variable initialised from a subquery** — `v TYPE := (SELECT …)`
      in the declare section is invalid PL/SQL; restructure to a `SELECT … INTO v`
      in the body. (Biggest single class.)
- [ ] **`PLS-00103` `CREATE … TABLE` inside the block** — a T-SQL table variable
      (`DECLARE @t TABLE(...)`) becomes `CREATE TEMPORARY TABLE` *inside* `BEGIN`,
      which Oracle forbids (a GTT is schema-level DDL). Emit a documented carrier,
      or a schema-level GTT + `EXECUTE IMMEDIATE`.
- [ ] **`PLS-00428` bare `SELECT`** — a result-returning `SELECT` in a proc body
      needs `INTO`/a ref cursor; there is no direct PL/SQL equivalent → carrier.
- [ ] **`PLS-00204` `IF EXISTS(subquery)`** — invalid in PL/SQL; needs the creative
      rewrite (`FOR _ IN (SELECT 1 FROM (<subq>) WHERE ROWNUM = 1) LOOP … END
      LOOP;`, or `COUNT(*) INTO v` for the ELSE case). *(Earlier "works on Oracle
      23" was a false positive — the proc CREATE'd but was INVALID.)*
- [ ] **`ORA-00900`** on a set-based-trigger carrier — the `-- UNIQUE:` block is
      followed by an orphan `END IF`/`END` fragment (a statement-split bug).
- [ ] **`ORA-00942` / `PLS-00111` / `PLS-00122`** — remaining smaller cases (some
      may cascade from the above once the earlier ones are fixed).

These are a **phased effort** (not a single change): the procedural -> Oracle path
does not yet produce valid PL/SQL for complex real-world procedures. The
validator + `xfail` now track progress objectively.

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
