# Unique — Pending Work

This document tracks **outstanding** work, ordered by priority. Completed work
has been archived in [`docs/DONE.md`](DONE.md) (with the detailed why/how of
each fix); `docs/STATUS.md` summarizes the project state at a higher level.

Last reviewed: 2026-07-08. The functional-equivalence and 2026-07-02
audit-remediation backlogs are complete and archived in [`docs/DONE.md`](DONE.md)
(§18); source-syntax validation across core/API/web/CLI shipped (§34). The
**2026-07-08 follow-up audit** ([`audit/2026-07-08/`](../audit/2026-07-08/))
verified all 14 previous functional bugs fixed and opened the backlog below.

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche

---

## 1. Oracle procedural output — validity backlog (P1) — ✅ DONE (26 -> 0)

**Complete.** The T-SQL procedures fixture (32 objects) now transpiles to
**fully-valid Oracle** — `test_procedures_fixture_is_valid_live[oracle]` asserts it
(the `xfail` is gone). The Oracle live-validator queries `USER_ERRORS` after each
`CREATE` (Oracle compiles PL/SQL *lazily*, so `CREATE` succeeds even for an invalid
body) and recompiles to settle forward dependencies. Detailed why/how of each fix
is archived in [`docs/DONE.md`](DONE.md); the arc, in brief:

- **Expression/type:** string-`+` -> `||`; subquery / CAST assignments and RETURNs
  are SQL-only in PL/SQL, so via `SELECT … INTO v FROM DUAL` (or a nested block);
  `SELECT TOP (n)` -> `FETCH FIRST`; CLOB/`SQL_VARIANT` -> bounded `VARCHAR2`;
  `TRY_CAST`/`SHA256`/`EXTRACT(EPOCH …)`/`VARCHAR(MAX)`-cast/character-CAST length;
  `DATEDIFF` sub-day + canonical layout; `TIME_STR_TO_TIME` unwrap.
- **Structure (features):** bare result `SELECT` -> `SYS_REFCURSOR` OUT; `EXEC
  sp_executesql` -> `EXECUTE IMMEDIATE … USING`; **table variable -> hoisted GTT**;
  **trigger DECLARE section**; **reassigned IN parameters shadowed with locals**;
  **inline split TVF -> `SYS.ODCIVARCHAR2LIST` function** + `TABLE(fn(…))` callers.
- **Rules:** OUT/IN OUT params take no DEFAULT; procedure/trigger RETURN carries no
  value; no `AS` before a table alias.

## 2. Audit 2026-07-08 follow-ups

Findings from [`audit/2026-07-08/02-new-findings.md`](../audit/2026-07-08/02-new-findings.md)
(reproductions and mechanism analysis there).

### P1 — silent semantic changes (no-silent-loss violations)

- [ ] **N1: unbracketed real-data `IF [NOT] EXISTS` guard dropped silently.**
      `IF NOT EXISTS (SELECT 1 FROM cfg WHERE k='x') INSERT …` (no `BEGIN`)
      loses the condition on every target with zero warnings — re-runs insert
      duplicates. `batch_splitter._classify` (line ~278) only protects the
      `BEGIN … END` form; drop the `_TSQL_BEGIN_BLOCK_RE` conjunct so any
      non-catalog guard routes to the procedural engine. Add single-statement
      INSERT/UPDATE/DELETE guard probes + an FE scenario running a guarded
      INSERT twice.
- [ ] **N2: PG → T-SQL temp-table rename not script-wide.**
      `SELECT * INTO TEMPORARY tmp; SELECT a FROM tmp; DROP TABLE tmp` emits
      `INTO #tmp` but leaves `FROM tmp`/`DROP tmp` — output creates one table
      and reads another, silently. Propagate the rename across the script;
      round-trip test PG→T-SQL→PG.

### P2 — correctness of signals and validation

- [ ] **N3: `validate_source` false negatives → silent garbage.**
      `banana banana` (parses as `exp.Alias`) and `CREATE TALBE t (id INT)`
      (`Command` fallback) validate clean on every dialect; the first then
      transpiles to `banana AS banana;` with no warning. Extend the
      bare-statement check (validation.py:168) to alias/expression-only
      statements and unknown-verb Commands; warn when a batch parses to a bare
      expression.
- [ ] **N5: false-positive warning on a successful guard round-trip** — the
      Oracle FOR-loop guard that *is* converted back to a T-SQL `IF` still
      warns "FOR loop has no direct T-SQL equivalent"
      (procedural/transformer/tsql.py:258). Suppress when the rewrite succeeds.
- [ ] **N6: `/api/v1/validate` and `/api/v1/detect` lack `max_length`** on
      their `sql` fields (A2 DoS cap applies only to `/transpile`).
- [ ] **N8: near-duplicate `unsupported` entries** for one construct
      (CREATE SCHEMA→Oracle, sp_rename): deduplicate at carrier↔result
      reconciliation.
- [ ] **N4/N9: docs drift** — STATUS.md claims the guard round-trip is
      FE-exercised (coverage-matrix.md says the opposite); the
      project-overview skill still says Python 3.12 (project is 3.13) and
      shows `converter.py` as a file; README lacks the "`latest` publishes
      only on tags" note. Also consider mapping Unique's own emitted catalog
      guard back to the target catalog so A→B→A of a guarded migration stays
      executable (today it degrades to a carrier, warned).

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **Decide on the architecture proposals in
      [`audit/2026-07-08/04-architecture-analysis.md`](../audit/2026-07-08/04-architecture-analysis.md)**
      — adopted as proposed (P1 honesty gate, P2 comment trivia, P3 unified
      AST guard path, P4 embedded DML through the IR pipeline, P5
      validity-ratchet process, P6 per-direction tiering; sequencing M0–M4).
      Binding rules encoded in `skills/SKILL-development-workflow.md`
      ("Architecture guardrails", "Detect the wrong path"). The item-level
      bugs below are *instances* of those root causes — fix the classes
      (P2/P3/P4), not the instances one by one.
- [x] **M0 — productize the validity sweep** (`scripts/validity_sweep.py`) —
      done: transpiles a file to each target, executes per-statement on the
      live engines (PG savepoints, MySQL throwaway database, SQL Server
      `SET PARSEONLY ON`, Oracle throwaway schema), classifies
      syntax-vs-expected per engine error code, reports per-direction validity
      % + top error groups with samples. E1 fixed on the way: the statement
      splitters were consolidated into ONE shared string/comment-aware module
      (`tests/helpers/sql_split.py`, 13 unit tests) used by the FE engine
      runner, the live validators and the sweep — the old duplicated splitters
      (which split on `;` inside string literals) are gone. Tests:
      `tests/unit/helpers/test_sql_split.py`,
      `test_validity_sweep_classify.py`. Baselines (private corpus, empty
      DBs): pre-gate Oracle→T-SQL 71%, Oracle→PG 56%; **post-M1**:
      T-SQL→{PG 99.9%, MySQL 98.6%, Oracle 99.6%}, Oracle→{T-SQL 94.0%,
      MySQL 75.0%, PG 73.1%}.
- [x] **M1 — honesty gate** (`src/unique/core/output_gate.py`) — done:
      (a) plain DML/DDL output that doesn't parse under sqlglot in the target
      dialect degrades to a carrier (original source preserved) + a
      `validity_gate` warning + an `unsupported` entry; (b) ALL output is
      scanned outside comments/strings for source-dialect leftovers
      (ROWNUM/VARCHAR2/EXECUTE IMMEDIATE off Oracle, GETDATE/brackets off
      T-SQL, backticks off MySQL, stray GO / `/` terminators) and degrades
      whole on a hit — this catches invalid procedural units sqlglot can't
      judge; (c) duplicate warnings aggregate into one entry with an `(xN)`
      count. The splitter moved into the product
      (`unique/core/sql_split.py`) to support the gate. Tests:
      `tests/unit/core/test_output_gate.py` (17); full suite green with the
      gate active — zero false degradations on the curated corpus.
      *Still open (M1 residue):* honest re-labeling of the SET_OPTION
      fallback ("SET option commented out" on non-SET batches) — falls with
      the M2 guard unification; fragment-level desync (D9) is only caught
      when a leftover token appears in the fragment.
- [ ] **M2 — P2 comment trivia + P3 unified AST guard path** (clears the
      guard family: N1, N10, A1–A5).
- [ ] **M3 — P4 embedded DML through the IR converter**; delete the
      text-level rewriters (clears D3, D4, D8, A4 by construction).
- [ ] **M4 — Oracle-source bring-up** driven by the sweep frequency table
      (doc 03 §D backlog).

### P1 — private-fixture live sweep (audit doc 03; anonymized repros there)

Found by transpiling the three `fixtures-private/` scripts across the matrix
and executing the outputs on the real engines. Ordered by attack value; every
fix needs an **anonymized** regression fixture (never a private name).

- [ ] **A1/A2: guard batches with a leading comment, or `BEGIN…END`-wrapped
      `IF OBJECT_ID` guards, are commented out wholesale** on every target
      (mislabeled `set_option` warning). Fix the guard extractor to tolerate
      leading comments and unwrap `BEGIN…END`; likely clears N1 too.
- [ ] **A3: leading comment suppresses the `/` terminator** of the emitted
      Oracle guard block — every following statement is swallowed in SQL*Plus.
- [ ] **D3: `INSERT … SELECT … FROM DUAL WHERE NOT EXISTS(…)` keeps
      `FROM DUAL`** on PG/T-SQL (~6,000× in the real Oracle dump).
- [ ] **D1: Oracle `EXEC proc` → `EXEC AS proc`** on every target (T-SQL
      impersonation syntax; PG/MySQL need `CALL`).
- [ ] **D2: top-level `DECLARE…BEGIN…END` keeps its PL/SQL skeleton in
      T-SQL** instead of flattening to `DECLARE @x…; <statements>`.
- [ ] **D8: silent expression corruption in procedural embedded DML** —
      `MAX(NVL(x,0)) + 1` loses `, 0))` and `+ 1` on T-SQL, and numeric `+`
      becomes `||` on PG. Add these shapes to the operator round-trip suite.
- [ ] **C1: mid-body scalar `DECLARE @x t = expr` is not hoisted** to the
      declaration section (Oracle PLS-00103, MySQL invalid position and `=`
      instead of `DEFAULT`, PG `CURSOR` without `FOR`). Reuse the
      table-variable hoisting machinery.
- [ ] **B1: `PRIMARY KEY CLUSTERED (col ASC)` → `PRIMARY KEY, CLUSTERED
      (col ASC NULLS FIRST)`** — invalid on all four targets.
- [ ] **B2: `DROP INDEX` untranslated across the matrix** (PG 3-part name,
      MySQL missing `ON tbl`, table name dropped from the `ON` form).
- [ ] **C5: MySQL `CALL` emitted with named arguments** (`name => v`),
      unsupported by MySQL — emit positional.
- [ ] **D9: `create or replace⏎PROCEDURE` (split lines + `-- <codegen>`
      header comment) desyncs the procedural parser**, spilling declaration
      fragments (`v_x AS VARCHAR2`, `CURSOR AS cur1`) as top-level batches.
- [ ] **D4: `ROWNUM` untranslated inside procedural embedded DML** (the DML
      pipeline maps it; the procedural one doesn't — asymmetry).
- [ ] **A4: `NEWID()` inside a guard becomes `UUID()` on Oracle** (procedural
      map not per-target; `SYS_GUID()` expected).
- [ ] **A5: catalog CREATE-guard loses idempotency on PG/MySQL** (bare
      `CREATE TABLE`, no `IF NOT EXISTS`, no warning; Oracle keeps the guard).
- [ ] **C2/C3/C4: MySQL routine bodies** — raw `BEGIN TRY` leaks; `WHILE …
      LOOP` (PL/SQL form) instead of `WHILE … DO`; cursor options spill as
      `; LOCAL AS FAST_FORWARD;` fragments.
- [ ] **D5/D6/D7: Oracle→T-SQL passthroughs** — `ALTER TABLE … RENAME COLUMN`
      (needs `sp_rename`), trigger `IF UPDATING/INSERTING/DELETING` (needs
      `UPDATE()` / inserted-deleted tests), `TRUNC(date)` → nonexistent
      `DATE_TRUNC` (T-SQL 2022 `DATETRUNC(day,…)` or `CAST(… AS DATE)`).
- [ ] **B3: MySQL `ADD COLUMN … CONSTRAINT name DEFAULT 0`** — drop the
      named-DEFAULT constraint with a warning.
- [ ] **B4: bare `RETURN` eats the next line's comment** (false "discarded
      RETURN value" warning; comment lost on round-trip).
- [ ] **D10: `DBMS_SCHEDULER.CREATE_JOB` → raw `CALL` on PG** — should be a
      carrier + unsupported entry.
- [x] **E1 (harness): `_split_mysql_statements` splits on `;` inside string
      literals** — fixed via the shared `tests/helpers/sql_split.py` (see M0);
      all live splitting is now string/comment-aware, incl. MySQL backslash
      escapes and a BEGIN/END word-boundary fix.

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [ ] **CI: fail when fewer engines than expected were exercised** — a broken
      ODBC install or Oracle startup timeout currently shrinks live validation
      silently (waits are `continue-on-error`, tests skip on connect failure).
- [ ] **Raise the identity-mutation floor** toward the measured 0.38 as
      `test_cross_dialect.py` (291 survivors) / `test_comment_preservation.py`
      assertions harden.
- [ ] **Module growth**: `procedural/parser.py` 2886, `procedural/transformer/
      base.py` 2813, `transpiler.py` 1713 lines — resume the split along the
      seams named in audit 2026-07-02 doc 03.
- [ ] **Docker digest pin + constraints file**; report the decode encoding in
      a `/transpile/file` response header (A5 residue); sanitize the
      `Content-Disposition` filename stem (N7).

## 3. Packaging (P3)

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
