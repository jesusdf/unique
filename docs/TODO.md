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
- [x] **Filtered / INCLUDE indexes & CLUSTERED/NONCLUSTERED** — CLUSTERED/
      NONCLUSTERED keywords are dropped for non-T-SQL targets; INCLUDE and
      filtered `WHERE` are kept for PostgreSQL and flagged with a comment for
      MySQL/Oracle; T-SQL physical storage options (`WITH (PAD_INDEX = ...)`,
      `ON [filegroup]`) are stripped for portability.

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
- [x] **Computed/persisted columns** (`AS (expr) PERSISTED`) — captured as a
      passthrough fragment so sqlglot emits `GENERATED ALWAYS AS (expr)
      STORED`; previously the expression was lost and the column became a
      bare VARCHAR.

## 3. Procedural engine refinements (P2)

- [x] **Silently-dropped SELECT clauses** — row locks (`FOR UPDATE`),
      `QUALIFY`, `START WITH`/`CONNECT BY`, and `SELECT INTO <table>` are now
      routed through sqlglot instead of being discarded, preserving
      semantics (or emitting a documented comment where no equivalent
      exists).
- [x] **Cursor `FOR` loop → explicit cursor** — Oracle implicit cursor
      FOR-loops now expand to a structurally complete explicit cursor for
      T-SQL (DECLARE/OPEN/FETCH/WHILE @@FETCH_STATUS/CLOSE/DEALLOCATE) and
      MySQL (DECLARE cursor + NOT FOUND handler + LOOP/FETCH/LEAVE/CLOSE).
      The developer only fills the per-column FETCH INTO variables.
- [x] **`CONNECT BY` (Oracle hierarchical)** — kept as-is for Oracle; for
      other targets emit a documented comment pointing to a WITH RECURSIVE
      CTE rewrite, instead of silently dropping the clause (an automatic
      rewrite cannot be done faithfully for arbitrary queries). A full
      auto-conversion remains possible future work.
- [x] **`MERGE`** — Oracle and PostgreSQL emit native MERGE (via
      PassthroughSQL); MySQL (no MERGE) gets a documented comment pointing to
      `INSERT ... ON DUPLICATE KEY UPDATE`.
- [x] **`OUTPUT` / `RETURNING` clause** — T-SQL OUTPUT is extracted safely
      (preserving the WHERE clause, whose loss on DELETE/UPDATE would be a
      data-loss bug) and mapped to RETURNING for PostgreSQL/Oracle; PG/Oracle
      RETURNING maps back to T-SQL OUTPUT. MySQL (no OUTPUT/RETURNING) keeps
      the base statement plus a documented comment.
- [x] **`@@IDENTITY` / `SCOPE_IDENTITY()`** → `LASTVAL()` (PG) /
      `LAST_INSERT_ID()` (MySQL) / documented `<sequence>.CURRVAL` (Oracle).

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
- [x] **`CONVERT` with style codes (T-SQL)** — `CONVERT(type, value, style)`
      now routes through sqlglot, which maps the numeric style codes to the
      right TO_CHAR/DATE_FORMAT patterns (style 120 → ISO datetime, 103 →
      dd/mm/yyyy, etc.). Previously the value and style were truncated.
- [x] **Date-format strings** — bidirectional Oracle/PostgreSQL `TO_CHAR`/
      `TO_DATE` ↔ MySQL `DATE_FORMAT`/`STR_TO_DATE` with format-pattern
      mapping (`YYYY`↔`%Y`, `%T`→`HH24:MI:SS`, etc.).

## 5. Tooling / infrastructure (P3)

- [ ] **End-to-end real-world tests using the private `procedures.sql`**
      (SQL Server + Oracle) once a delivery mechanism is agreed. The file is
      out-of-band and never committed; tests must skip when absent.
- [x] **Round-trip fidelity tests** (A→B→A) on the public fixtures — added;
      these caught a missing statement-terminator bug (emitted statements
      lacked ';', so the output was not re-parseable). Output statements are
      now properly terminated.
- [x] **Generic transpilation invariants** (`tests/helpers/invariants.py`) —
      two reusable, dialect-agnostic validations applied across all 12 pairs:
      (1) *element conservation* — structural keywords (CREATE TABLE, PRIMARY
      KEY, FOREIGN KEY, ...) are not dropped unless documented with a
      `-- UNIQUE:` comment, catching silent loss generically; (2) *round-trip
      content similarity* — A→B→A' compared by normalized token-set Jaccard
      with per-source floors. Confirmed 0 silent DDL losses; low Oracle/T-SQL
      round-trip scores trace to legitimately commented proprietary DDL
      (sp_addextendedproperty, XML schemas), not bugs.
- [x] **Performance** — analyzed (not a bottleneck of our own code).
      Realistic best-of-3 timings: Northwind (~3,400 statements, mostly data
      INSERTs) 0.84s; AdventureWorks 0.11s; Sakila 0.06s; HR 0.03s. Profiling
      shows ~91% of the time is sqlglot parsing, proportional to the number
      of statements and inherent to the parser — there is no redundant work
      on our side (each statement is parsed once). No micro-optimization is
      warranted; if bulk data-INSERT throughput ever matters, batching or
      skipping pure-data INSERTs would be the lever, not parser tuning.
- [ ] **PyPI publication** — deferred until the tool has been used in real
      projects for a few months and proven stable. Not before then.

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
