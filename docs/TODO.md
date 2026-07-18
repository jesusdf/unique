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

- [x] **Residual invalid output ships WITHOUT a warning (P1) — CLOSED at the architectural floor (2026-07-17, `469917a`).** Six-direction residue driven ~770→133; every statement transpiles validly or carries a warning; pg→pg discovery 287→0. Remainder needs schema-aware transpilation. Full log [`docs/DONE.md`](DONE.md) §36.

### P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **M3 final — DONE 2026-07-17 (`86f7c11`): IR-first is the expression engine.** The last architecture-plan milestone; scalar fragments route through the shared IR pipeline, text rewriters are the fallback (`UNIQUE_NO_IR_FIRST` kill-switch). Full log [`docs/DONE.md`](DONE.md) §39.
- [x] **Zero-reduction campaign (P2) — CLOSED at the floor, residue 133 → 16 (2026-07-17, `34d7338`).** Mechanism fixes (not waves) drove the six-direction live-syntax residue to 16, both Oracle directions 100.0% validity; remainder is the architectural floor (adversarial pg_regress, schema-dependent inference). Full log [`docs/DONE.md`](DONE.md) §40.
- [x] **Prune fallback-only text rewriters (P3) — CLOSED BY MEASUREMENT 2026-07-17.** 36/37 rewriters carry live fallback traffic; nothing safely prunable. Archived [`docs/DONE.md`](DONE.md) §42.

### P3 — hardening carry-overs (from 2026-07-02, still open)

- [x] **Module growth — DONE 2026-07-17.** All three oversized modules split (procedural/parser package, transformer `_expr.py` seam, `core/transpiler/` package). Full detail [`docs/DONE.md`](DONE.md) §37.
- [x] **tsql→mysql procedural DATEADD nested INTERVAL — FIXED 2026-07-17.** The normalize walk hoists a tsql `DateAdd`'s interval into the unit slot (was `INTERVAL (INTERVAL '-1' MONTH) DAY`). Archived [`docs/DONE.md`](DONE.md) §42.

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

## 4. T-SQL keyword coverage — ✅ DONE (archived [`docs/DONE.md`](DONE.md) §42)

`PROC`≡`PROCEDURE`, `CREATE OR ALTER`, and `BEGIN TRAN[SACTION]` all route and translate; covered by `tests/integration/test_tsql_keyword_alias.py` + `test_challenge.py` + `test_procedural.py`.
## 5. Procedural round-trip fidelity (challenge corpus)

New regression corpus at [`tests/fixtures/challenge/`](../../tests/fixtures/challenge/)
— one anonymized script per source engine collecting tricky constructs as they
are found; guarded by `tests/integration/test_challenge.py`. Cases are tagged
`[fixed]` (strictly guarded) or `[open]` (RED backlog). See the
[challenge-corpus skill](../skills/SKILL-challenge-corpus.md) for the red/blue
workflow.

- [ ] **BLUE batch IN PROGRESS — NOT over (per `SKILL-challenge-corpus.md`, the
      batch ends only when every `[open]` case is `[fixed]` or user-approved as a
      documented limit).** Landed so far (recorded in [`docs/DONE.md`](DONE.md)
      §41): RC-1b gate (DML+procedural), 21 built-in mappings, RC-3
      FK/CHECK/IDENTITY/COMMENT + Oracle ON UPDATE, RC-2 LOG; 703 finding-rows
      resolved, `FINDINGS.md` pruned, 259 cases flipped `[open]→[fixed]`.
      **Correction:** I wrongly self-declared the ~600 residual `[open]` cases an
      "architectural floor" and archived the item as done — that violated the
      skill (only the USER may approve a limit) and mislabelled tractable work
      (MONEY→DECIMAL, INET→VARCHAR, GENERATED ALWAYS, ALTER COLUMN DEFAULT, …) as
      floor. **Resuming**: fix the tractable residual (flip each as fixed), then
      surface only the genuinely-impossible cases to the user for explicit
      approval. Residual: 1127 finding-rows (func 396, invalid 625, silent-drop
      75, silent 21, silent-rt 8, semantic 2) across ~600 `[open]` cases.

## 6. Packaging (P3)

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
