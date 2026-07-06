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

Also fixed since: CLOB-comparison keys (`VARCHAR(MAX)` -> bounded `VARCHAR2`, both
DDL and procedural), `SQL_VARIANT` -> `VARCHAR2` (ANYDATA can't take a plain value
in a call), and Oracle-less functions `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)` and
`VARCHAR(MAX)` casts. Sweep: **26 -> 12 INVALID** (of 32).

The remaining **12 need structural features, not one-line fixes** — mostly
T-SQL-specific patterns with no clean Oracle equivalent:

- [ ] **Table variable** (`DECLARE @t TABLE …`, 4 procs) — needs a schema-level
      Global Temporary Table *hoisted before the procedure* (a CREATE cannot live
      inside a PL/SQL block, and the block references it statically) **plus**
      `INSERT … OUTPUT … INTO @t` -> `RETURNING … BULK COLLECT INTO`. A real feature.
- [ ] **Table-valued function in `FROM`** (`FUNC5`, 1 proc) — a T-SQL TVF becomes
      an Oracle pipelined function over a collection type; it is currently a
      carrier, so callers hit `ORA-00904`.
- [ ] **Deeply-nested date arithmetic** (`FUNC2`, ~14 stacked errors) — layered
      `CAST(CAST(… AS TIMESTAMP) …)` / EPOCH math; needs a focused rewrite.
- [ ] **Trigger-local declarations** — declarations emitted inside `BEGIN` need a
      trigger `DECLARE` section.
- [ ] **Assorted single-statement fixes** — `AS` before a table alias in an IR
      cross-table `UPDATE` subquery (`ORA-00907`), a couple of length/paren cases.

These are a genuine multi-session effort; reaching **exactly 0** requires the
table-variable and TVF features above (or carrier-ing whole procedures, which
would break the mandatory DML-verb-conservation invariant). Tracked by the
validator + `xfail`.

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
