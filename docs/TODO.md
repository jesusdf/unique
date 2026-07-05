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

- [x] **Phase 1 — registration + DML/DDL source.** Source-only `sqlite` dialect
      (parses via sqlglot; `emit()`/`target="sqlite"` raises); sqlglot mapping;
      `source_only` marker on the Dialect base; API `/dialects` exposes it and the
      web target combo filters it out. sqlglot + the shared converter already
      handle the DML/DDL quirks (type affinity, `INTEGER PRIMARY KEY
      [AUTOINCREMENT]` → identity/serial). DONE.
- [x] **Phase 2 — SQLite source functions.** `last_insert_rowid()` → the
      target's last-identity expr, `datetime('now')`/`date('now')` →
      CURRENT_TIMESTAMP/CURRENT_DATE, `random()` → RANDOM()/DBMS_RANDOM.VALUE;
      sqlglot already covers `ifnull`→COALESCE, `substr`, `instr`, `group_concat`.
      DONE.
- [x] **Phase 3 — row-level trigger translation from SQLite.** A `sqlite` entry
      in the procedural-batch classifier routes `CREATE TRIGGER … FOR EACH ROW
      BEGIN … END` to the procedural engine, which already produces the Oracle/
      MySQL/PostgreSQL trigger forms (BEFORE/AFTER, INSERT/UPDATE/DELETE, OLD/NEW,
      WHEN). DONE.
- [x] **Real-world fixtures.** MediaWiki schema variants vendored under
      `tests/fixtures/real_world/mediawiki/` with GPL attribution; validity test
      transpiles each (incl. sqlite → the four targets). DONE. *(A dedicated
      in-memory SQLite-source FE scenario remains a possible future addition.)*

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
  round-trip **restores the original** on a transpilation back to a supporting
  engine — verified for `%TYPE` via the procedural path and for physical index
  clauses via the DML path (`%TYPE` is PL/SQL-only, so it never appears in a
  DML/DDL statement).
