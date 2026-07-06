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

The remainder is a **long tail of distinct issues** (each its own fix; a proc
often stacks several, so the count drops slowly as layers are peeled):

- [ ] **CLOB comparison (`ORA-22848`)** — an unbounded `NVARCHAR`/`NCLOB` used in a
      WHERE/JOIN key; map to `VARCHAR2(4000)` (or dbms_lob compare).
- [ ] **`ORA-00910` length too long** — a `VARCHAR2(> 4000)` (or `NVARCHAR(MAX)`)
      exceeds Oracle's limit; clamp/`CLOB`.
- [ ] **table variable** (`CREATE TEMPORARY TABLE` in block) — carrier or a
      schema-level GTT + `EXECUTE IMMEDIATE`.
- [ ] **trigger-local declarations** — a trigger emits `V … := …` inside `BEGIN`
      instead of a `DECLARE` section (`PLS-00103` at the trigger's first line).
- [ ] **function gaps** — `TRY_CAST`, `SHA256`/`HASHBYTES`, `EXTRACT(EPOCH …)`,
      and a call to a carrier'd function (`FUNC5` -> `ORA-00904` cascade).
- [ ] **`IF EXISTS(subquery)`** (`PLS-00204`) — the creative `FOR _ IN (SELECT 1
      FROM (<subq>) WHERE ROWNUM = 1) LOOP … END LOOP;` rewrite.

A **phased effort**, tracked objectively by the validator + `xfail`; being worked
class-by-class.

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
