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

- [x] **Residual invalid output ships WITHOUT a warning (P1) — CLOSED at the
      architectural floor (2026-07-17, user declaration at `469917a`).** The
      direction-residue campaign (waves 103–239) took the six-direction residue
      from ~770 invalid-silent statements to **133 pending** (mysql-corpus
      {tsql 20, pg 15, oracle 13}, pg-corpus {tsql 29, mysql 32, oracle 24}),
      validity **98.9–99.8%**, and the pg→pg silent-gap discovery channel from
      **287 to 0** (`scripts/discover_silent_gaps.py`). Every statement now
      transpiles validly or carries a warning/carrier; the remainder is three
      non-wave classes (adversarial pg_regress error-path inputs,
      schema-dependent ambiguity, RETURN QUERY table functions) that need
      schema-aware transpilation — declared out of scope for statement-level
      transpilation. Full per-wave log (mechanisms, measured commit hashes,
      tests) archived in [`docs/DONE.md`](DONE.md) §36; the floor declaration
      and scope decisions are reproduced there verbatim. Standing decisions:
      live validation stays a development-only tool (never CLI/API), and no
      new waves on these corpora without a new corpus or a fidelity target.

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [ ] **M3 final — IR-first scalar expressions; retire the text-level
      expression rewriters (`transformer/_expr.py`).** The LAST open
      architecture-plan step, a declared MULTI-SESSION milestone — never a
      wave. *Done so far:* M3a/M3b (embedded DML through the shared IR
      pipeline, measured 2026-07-09) and the whole M3-prereq arc
      (increments 1–4 + family steps 1–4, archived in
      [`docs/DONE.md`](DONE.md) §38). *Remaining, in dependency order:*
      1. *Precondition (a) — procedural context into the IR expression
         pipeline:* cursor state (last-fetch cursor, per-target
         fetch-status forms), published like STRING_VARIABLES, so the
         FOUND/@@FETCH_STATUS idioms can migrate.
      2. *Precondition (b) — comment-carrying expression nodes:* the IR
         drops in-expression comments today; the converter/emitters need
         trivia-bearing expression nodes.
      3. *Family-by-family migration* (the increments-1..4a pattern,
         differential text-vs-IR audits per family, live sweeps as the
         net), then flip `_transform_raw_sql` to IR-first and delete the
         rewriters.
      **Probe re-measured 2026-07-17 (HEAD `5b26d5b`):** IR-first for
      scalar fragments = **113 test failures** (was 126 at the original
      probe; waves 98–102 absorbed the difference). Module map:
      pg_source_wave1 25, procedural/test_transformer 21,
      oracle_source_m4_wave 15, test_procedural 13, oracle_mysql_tail 9,
      test2_residue_wave 7, embedded_dml_ir 5, triggers 4+4, singles 10.
      Probe recipe (reproducible): guard `UNIQUE_IR_FIRST` in
      `_transform_raw_sql`, calling `self._ir_transpile_dml(node.sql)`
      right after the early-return carriers and returning the replaced
      node when it succeeds; run the full suite with `UNIQUE_IR_FIRST=1`.

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [x] **Module growth — DONE 2026-07-17.** All three oversized modules are
      split: `procedural/parser` package (2026-07-10), the transformer's
      `ExpressionRewriter` seam (`transformer/_expr.py`, `997f0e8` —
      base.py 5053 → 3735 lines), and `transpiler.py` → the
      `core/transpiler/` package (`_text_rules.py` + `_core.py` +
      re-exporting `__init__`, `0e6ead0`). Full detail archived in
      [`docs/DONE.md`](DONE.md) §37; the rewriter object is what M3's
      IR-first expressions will eventually replace.
- [x] **tsql→mysql procedural DATEADD nested INTERVAL — FIXED 2026-07-17**
      (same day it was filed): `_mysql_normalize_funcs`'s sqlglot
      round-trip re-emitted a tsql-read `DateAdd` carrying its whole
      `Interval` in the *expression* slot through the mysql generator,
      which invents an implicit DAY unit (`INTERVAL (INTERVAL '-1'
      MONTH) DAY` — invalid MySQL and a silent unit change). The
      normalize walk hoists the interval into the expression/unit
      slots. Test: TestDateAddUnderConvertMySql.

## 3. Test-corpus expansion (P3)

- Corpus wave campaign **COMPLETED and archived** (2026-07-15 →
  2026-07-17, waves 4–95; full per-wave log with measured commit
  hashes in `docs/DONE.md`, section "Wave campaign — corpus
  validity"; waves 96–102 are the M3-prereq/M3b record kept in the
  §2 M3 item). Final standings at `3fdfc88`:
  - pg-source (PostgreSQL regression corpus,
    `fixtures-corpus/pg_corpus_valid.sql`): →T-SQL **163** syntax
    failures (95.0% validity), →MySQL **131** (95.7%), →Oracle **89**
    (97.2%).
  - mysql-source (private local corpus, provenance undocumented by
    policy): →T-SQL **166** (97.2%), →PG **107** (98.2%), →Oracle
    **129** (97.8%).
  - Both residues are at the deep-singles floor (a full measure cycle
    buys ~−1); do not resume waves on these corpora without a new
    corpus or a fidelity target.

## 4. Packaging (P3)

- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

---

## Continuously tracked (not a discrete backlog)

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
