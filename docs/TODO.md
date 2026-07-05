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

## 1. MediaWiki live-schema gaps (P2)

`tests/integration/test_mediawiki_live.py` executes the transpiled MediaWiki
schema against real engines. **Green:** `mysql → {postgresql, oracle}` and
`sqlite → postgresql`. The remaining pairs are skipped as documented gaps (fix
them and remove from `_KNOWN_GAPS`):

- [x] **Reserved words in passthrough** (`CREATE INDEX ON collation`), **binary/
      LOB type mappings** (bare binary → BLOB; unsigned floats; DOUBLE →
      BINARY_DOUBLE; MySQL blob/text families), **`SERIAL`/`BIGSERIAL` → each
      target's identity**, and **Oracle RAW/BLOB with a string default** — all
      fixed (v0.10.1+).
- [ ] **BLOB/TEXT column in a MySQL key needs a prefix length** (MySQL 1170).
      A source `TEXT`/`BLOB` column (PostgreSQL/SQLite) used in a UNIQUE/index
      has no length; MySQL requires `col(191)`. Affects `postgresql→mysql`,
      `sqlite→mysql`.
- [ ] **A few PostgreSQL/SQLite-source → Oracle cases**: a functional/expression
      index (ORA-02327) and one remaining type (ORA-00907). Affects
      `postgresql→oracle`, `sqlite→oracle`.
- [ ] Wire a root-free SQL Server driver (pymssql) into the live validator so
      the `→tsql` pairs run (they currently skip: the validator needs pyodbc).

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
