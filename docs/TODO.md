# Unique — Pending Work

This document tracks all outstanding work, ordered by priority. It is the
authoritative backlog; `docs/STATUS.md` summarizes what is already done.

Last reviewed: 2026-06-18 (after column-constraint preservation work).

## Legend

- **P1** — high impact, appears frequently in real schemas
- **P2** — medium impact, common but not blocking
- **P3** — lower impact / niche
- Counts in parentheses are occurrences across the four real-world fixtures
  (all 12 directional pairs), as a rough impact signal.

---

## 1. DDL statements not yet wired through the IR (P1)

IR nodes exist for these but no converter/emitter connects them, so
sqlglot marks them "Unhandled" and they fall back to commented passthrough.

- [ ] **ALTER TABLE** (180) — `ADD CONSTRAINT` (foreign keys, primary keys,
      defaults, checks), `ADD/DROP COLUMN`, `ALTER COLUMN`. `AlterTableStatement`
      node exists; needs `_convert_alter_table` + `_emit_alter_table`.
- [ ] **CREATE INDEX** (69 incl. NONCLUSTERED/CLUSTERED) — map T-SQL
      CLUSTERED/NONCLUSTERED (drop the keyword for other engines),
      `INCLUDE (...)` columns, filtered indexes. `CreateIndexStatement` exists.
- [ ] **CREATE SEQUENCE** (9) — `CreateSequenceStatement` exists; wire
      converter/emitter; MySQL has no sequences (emit a documented comment).
- [ ] **CREATE SCHEMA** (6) — pass through / map `AUTHORIZATION`.
- [ ] **USE <db>** (6) — comment out or map to `\\c` (PG) / schema switch.

## 2. Column / type features in CREATE TABLE (P1)

- [ ] **Table-level constraints** — `CONSTRAINT ... PRIMARY KEY (cols)`,
      `FOREIGN KEY ... REFERENCES`, `UNIQUE (cols)`, `CHECK (...)` declared
      outside a single column are currently dropped (only per-column
      constraints are captured).
- [ ] **User-defined / domain types** — T-SQL `[dbo].[Name]` and Oracle/PG
      domains make sqlglot fail the whole CREATE TABLE. Strip schema-qualified
      UDTs to their base type or emit a documented warning.
- [ ] **MySQL `... BINARY` column attribute** and `ON UPDATE CURRENT_TIMESTAMP`
      — sqlglot fails the column; needs preprocessing similar to ROWGUIDCOL.
- [ ] **Computed/persisted columns** (`AS (expr) PERSISTED`).

## 3. Procedural engine refinements (P2)

- [ ] **`SELECT ... INTO <var>` (MySQL/PG/Oracle)** — `SELECT COUNT(*) INTO x`
      currently confuses sqlglot in embedded DML; route through the procedural
      SELECT-INTO path consistently for all source dialects.
- [ ] **Cursor `FOR` loop → explicit cursor** for T-SQL/MySQL (currently
      flagged for manual conversion).
- [ ] **`CONNECT BY` (Oracle hierarchical) → recursive CTE.**
- [ ] **`MERGE` → MySQL** (`INSERT ... ON DUPLICATE KEY UPDATE`).
- [ ] **`OUTPUT` / `RETURNING` clause** full mapping (partial today).
- [ ] **`@@IDENTITY` / `SCOPE_IDENTITY()`** → `lastval()` / `LAST_INSERT_ID()`
      / sequence `CURRVAL`.

## 4. Function mapping gaps (P2)

- [ ] **Argument-reordering functions** currently emitted as review comments:
      `CHARINDEX`↔`INSTR`↔`LOCATE`, `DECODE`→`CASE`, `NVL2`→`CASE`,
      `TO_CHAR`/`TO_DATE`/`CONVERT` with format strings.
- [ ] **Date-format strings** — map Oracle `'YYYY-MM-DD'` ↔ MySQL `'%Y-%m-%d'`
      ↔ T-SQL style codes.
- [ ] **String aggregation** — `STRING_AGG` ↔ `LISTAGG` ↔ `GROUP_CONCAT`.

## 5. Tooling / infrastructure (P3)

- [ ] **End-to-end real-world tests using the private `procedures.sql`**
      (SQL Server + Oracle) once a delivery mechanism is agreed. The file is
      out-of-band and never committed; tests must skip when absent.
- [ ] **Round-trip fidelity tests** (A→B→A) on the public fixtures.
- [ ] **Performance**: Northwind (~3,900 lines, 3,300 INSERTs) takes ~0.8s;
      profile the DML path if larger inputs are expected.
- [ ] **PyPI publication** — explicitly deferred (do not publish yet).

## 6. Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally
emitted as comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, ...).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (now preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as `SQL_VARIANT` + warning).
- `EXECUTE IMMEDIATE ... USING` bind variables (T-SQL `sp_executesql`).
- Engine-specific physical features (partitioning, tablespaces, filegroups,
  index storage clauses).
