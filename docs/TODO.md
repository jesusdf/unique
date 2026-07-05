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

## 1. SQLite support — import-only (P2)

SQLite as a **source only** (SQLite → the four server engines), not a target:
it has no procedural language (no stored procedures/functions/anonymous blocks),
so it can never be a faithful procedural target. Import-only sidesteps that
entirely — the procedural transformer/emitter are keyed by *target*, so a SQLite
source needs no new procedural plugin. Common real use case: migrating *off* an
embedded/prototype SQLite DB onto a server. Live FE testing is free (`sqlite3`
is stdlib, in-memory).

- [ ] **Phase 1 — registration + DML/DDL source.** Register a source-only
      `sqlite` dialect (parses via sqlglot; `emit()`/`target="sqlite"` raises a
      clear "SQLite is import-only" error). Add the sqlglot mapping
      (`"sqlite": "sqlite"`), the UI (source-only, disabled as target), and
      SQLite-source IR quirks in the converter: type affinity
      (INTEGER/TEXT/REAL/BLOB/NUMERIC → the target's real types),
      `INTEGER PRIMARY KEY [AUTOINCREMENT]` (rowid alias) → identity/serial,
      no schema qualifiers, booleans as 0/1. The design wrinkle: the
      `DialectRegistry` is symmetric — introduce a source-only marker and update
      the `available_dialects` == 4 test / matrix / UI accordingly.
- [ ] **Phase 2 — SQLite source functions.** `last_insert_rowid()`,
      `strftime`/`datetime('now')` → each target's date functions,
      `ifnull` → COALESCE, `substr`, `typeof`, `hex(randomblob(...))`.
- [ ] **Phase 3 — row-level trigger translation from SQLite.** A SQLite
      `CREATE TRIGGER … FOR EACH ROW BEGIN <stmts> END` (NEW/OLD, simple SQL
      body, no variables/control-flow) → the target's row-level trigger,
      reusing the existing trigger machinery.
- [ ] **Real-world fixtures + FE.** Vendor the MediaWiki schema variants
      (mysql/postgres/sqlite) under `tests/` with attribution; add real-world
      validity tests (incl. sqlite → the four targets) and, once Phase 1 lands,
      a small SQLite-source FE scenario run in-memory via `sqlite3`.

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
  restorable-note round-trip is already wired for physical index clauses
  (DONE §17); extending it to `%TYPE` on the DML path is the remaining piece.
