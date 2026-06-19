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

- [x] **ALTER TABLE** (180) — `ADD CONSTRAINT` (FK/PK/default/check),
      `ADD/DROP/ALTER COLUMN`. Now round-tripped through sqlglot via
      `PassthroughSQL` (sqlglot transpiles ALTER faithfully across engines).
- [x] **CREATE INDEX** (69 incl. NONCLUSTERED/CLUSTERED) — round-tripped via
      `PassthroughSQL`. sqlglot drops the CLUSTERED/NONCLUSTERED keyword for
      engines that lack it.
- [x] **CREATE SEQUENCE** (9) — round-tripped via `PassthroughSQL`; MySQL has
      no sequences, so it emits a documented `AUTO_INCREMENT` comment instead.
- [x] **CREATE SCHEMA** (6) — round-tripped via `PassthroughSQL`.
- [x] **USE <db>** (6) — MySQL/T-SQL pass through; PostgreSQL and Oracle
      (no SQL USE) emit a documented comment to connect to the target DB.
- [ ] **Filtered / INCLUDE indexes** — verify T-SQL `INCLUDE (...)` and
      `WHERE` predicate handling in the passthrough output.

## 2. Column / type features in CREATE TABLE (P1)

- [x] **Table-level constraints** — `CONSTRAINT ... PRIMARY KEY (cols)`,
      `FOREIGN KEY ... REFERENCES`, `UNIQUE (cols)`, `CHECK (...)` declared
      outside a single column are now captured as PassthroughSQL fragments
      and re-transpiled per dialect (preserved instead of dropped).
- [x] **User-defined / domain types** — T-SQL `[dbo].[Name]` now keeps its
      type name instead of collapsing to the literal USER-DEFINED.
- [x] **MySQL `... BINARY` column attribute** — stripped before parsing
      (the BINARY(n) data type and BINARY(expr) function are preserved).
      `ON UPDATE CURRENT_TIMESTAMP` is handled by sqlglot directly.
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

- [x] **Substring-position functions** — `CHARINDEX`↔`INSTR`↔`LOCATE`↔`STRPOS`
      now translated with correct argument reordering (start position kept).
- [x] **`DECODE`→`CASE`** — Oracle DECODE translated to a searched CASE.
- [x] **String aggregation** — `STRING_AGG` ↔ `LISTAGG` ↔ `GROUP_CONCAT`
      (handles MySQL `SEPARATOR` syntax). Quote-aware argument splitting so
      commas inside string literals are not mis-split.
- [x] **`NVL2`→`CASE`** — `NVL2(e, a, b)` → `CASE WHEN e IS NOT NULL THEN a
      ELSE b END` (Oracle source).
- [x] **`TO_CHAR`/`TO_DATE` with date-format strings (Oracle→MySQL)** —
      mapped to `DATE_FORMAT`/`STR_TO_DATE` with format-pattern translation
      (`YYYY`→`%Y`, `HH24`→`%H`, etc.). Oracle→PostgreSQL keeps the same
      patterns. `CONVERT` style-code mapping for T-SQL remains.
- [ ] **`CONVERT` with style codes (T-SQL)** — map numeric style codes to
      explicit format strings where possible.
- [ ] **Date-format strings** — map Oracle `'YYYY-MM-DD'` ↔ MySQL `'%Y-%m-%d'`
      ↔ T-SQL style codes.

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
