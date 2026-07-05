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
schema against real engines. `mysql -> postgresql` is fully green; the remaining
source→target pairs are skipped as documented gaps this real schema surfaced
(fix them and remove from `_KNOWN_GAPS`):

- [ ] **Reserved words in sqlglot-passthrough statements** (e.g. `CREATE UNIQUE
      INDEX … ON collation (…)`): `_ident` quotes reserved identifiers in the
      IR emit path (CREATE TABLE) but CREATE INDEX / ALTER go through sqlglot,
      which does not quote them. Affects `sqlite→postgresql`, `mysql→oracle`.
- [ ] **PostgreSQL `SERIAL`/`BIGSERIAL` → MySQL**: emit `INT/BIGINT
      AUTO_INCREMENT` (currently leaks `BIGSERIAL`, a MySQL syntax error).
      Affects `postgresql→mysql`, `sqlite→mysql`.
- [ ] **More PostgreSQL-source → Oracle type rows** (ORA-00902/00906) and
      **Oracle `RAW`/`BLOB` columns with a `''` string default** (ORA-01465 — a
      MySQL `VARBINARY DEFAULT ''` should drop the default or use EMPTY_BLOB()).
      Affects `*→oracle`.
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
