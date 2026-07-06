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

**Fixed:** (1) string-`+` -> `||` (`PLS-00306`); (2) the validator's Oracle
splitter no longer shreds a PL/SQL block after plain SQL (spurious `ORA-00900`);
(3) a body assignment `x := (SELECT …)` -> `SELECT … INTO x FROM DUAL`; (4) a
subquery-initialised declaration `v TYPE := (SELECT …)` hoisted to the body as a
`SELECT … INTO`; (5) `SELECT TOP (n)` in a scalar subquery -> `FETCH FIRST`;
(6) a bare result `SELECT` -> a `SYS_REFCURSOR` OUT parameter opened FOR the
query (`PLS-00428`); (7) `EXEC sp_executesql @stmt, N'…', @a, @b` -> Oracle
`EXECUTE IMMEDIATE @stmt USING @a, @b` (paramdef dropped). Sweep: 26 -> **20
INVALID** of 32 (several procs stack multiple errors, so clearing a class often
exposes the next rather than dropping the object count).

**Fixed since (each a real feature/fix, all live-validated):** CLOB/`SQL_VARIANT`
-> bounded `VARCHAR2`; Oracle-less functions `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)`,
`VARCHAR(MAX)` casts, character-CAST length, `DATEDIFF` sub-day + canonical layout,
`TIME_STR_TO_TIME` unwrap; **table variable -> hoisted GTT** (+ `OUTPUT INTO`
carrier); OUT/IN OUT params take no DEFAULT; `AS`-before-table-alias; **trigger
DECLARE section**; CAST/RETURN are SQL-only in PL/SQL (evaluated via `SELECT …
INTO … FROM DUAL` / a nested block); procedure/trigger RETURN carries no value;
**reassigned IN parameters shadowed with locals**. The validator now recompiles
invalid objects to settle forward dependencies (FUNC4 -> FUNC2 -> PROC_6).

**Sweep: 26 -> 1 INVALID** (of 32). The one remaining:

- [ ] **PROC_25 via FUNC5 — inline table-valued function** (`RETURNS TABLE`). The
      last feature: emit the T-SQL TVF as an Oracle **pipelined function** over a
      collection type (hoisted like the GTT), translate its `STRING_SPLIT` body to
      `CONNECT BY`/`REGEXP_SUBSTR`, and rewrite the caller's `FROM func5(…)` to
      `FROM TABLE(func5(…))` (preserving the `item` column). Until then FUNC5 is a
      documented carrier and PROC_25 hits `ORA-00904`.

Once PROC_25 validates, drop the `xfail` on `test_procedures_fixture_is_valid_live[oracle]`
(task #42) and bump the version.

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
