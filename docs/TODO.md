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

- [x] **M3 final — DONE 2026-07-17 (`86f7c11`): IR-first is the expression
      engine.** The LAST architecture-plan milestone (audit doc-04 P4)
      closed: scalar fragments route through the shared IR pipeline by
      default; the text rewriters serve only IR-declined fragments (parse
      failures, shell-machinery text) — the same primary+fallback shape
      M3a gave embedded DML. `UNIQUE_NO_IR_FIRST` is the kill-switch.
      Arc: probe 126 → 113 → 109 → … → 0-real via ~15 family commits
      (shared func/error/diagnostic tables consumed by BOTH pipelines,
      cursor+FOUND state context, styled CONVERT + TO_DATE/TO_CHAR format
      bridge, trigger-shell guards, comment line→block carrying, national
      literals, Trim positions, nested subqueries, LOB helpers, concat
      classification+flattening) + 23 assertions strengthened to exact IR
      forms at the flip. **Measured (definitive cycle): pg-corpus {tsql
      20, mysql 37, oracle 25}, mysql-corpus {tsql 17, pg 13, oracle 15}
      = TOTAL 127 vs the declared floor 133 (−6); validity 98.7–99.8%;
      discovery pg→pg 0; FE live 16/16.** Full log in
      [`docs/DONE.md`](DONE.md) §39.
- [x] **Prune fallback-only text rewriters (P3) — CLOSED BY MEASUREMENT
      2026-07-17:** a coverage run over ALL real material (both corpora,
      the procedures fixtures and the three private fixtures, every
      direction) shows **36 of 37 rewriters still receive fallback
      traffic** — the IR-declined fragments (parse failures, mid-transform
      hybrids) are real and the text fallback is their working surface.
      The single zero-traffic method (`_map_mysql_datefmt_to_oracle`, 8
      lines) is a helper of a live method and reachable by real
      mysql→oracle date formats outside the corpus — deleting it would
      break the fallback with no replacement. Conclusion: nothing is
      safely prunable; the fallback surface stays as-is. (Harness: the
      scratchpad coverage run with COVERAGE_CORE=sysmon; the timed-out
      first attempt without sysmon is the reminder to always use it.)

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
