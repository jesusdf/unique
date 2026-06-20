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
      passthrough fragment. MySQL keeps a typeless `GENERATED ALWAYS AS (expr)
      STORED`... but live validation showed PostgreSQL, Oracle **and MySQL**
      all reject a generated column without an explicit type (which T-SQL
      computed columns don't declare). So for every target we now emit a
      documented `-- UNIQUE:` comment **outside** the column list (keeping the
      CREATE TABLE valid) instead of invalid SQL. The expression is preserved
      in the comment; previously it was lost and the column became a bare
      VARCHAR.
- [x] **Invalid `CASE` in transpiled indexes** — sqlglot emulates
      PostgreSQL's NULLS ordering by prefixing an index key with
      `CASE WHEN col IS NULL THEN 1 ELSE 0 END, col`, which is invalid inside
      an index column list in T-SQL, MySQL and Oracle. Collapsed back to the
      bare column for every target except PostgreSQL. Found by live validation.

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
- [x] **Data-type name mapping in CREATE TABLE** — non-portable types
      (NVARCHAR/NCHAR/NTEXT, DATETIME2, MONEY, BIT, UNIQUEIDENTIFIER/UUID,
      VARBINARY/BYTEA, ...) map to the target dialect both in our own emitter
      and in passthrough DDL. Found by the live syntax-validation layer
      (PostgreSQL rejected `NVARCHAR`).
- [ ] **Data-type names inside procedural bodies (P2)** — variable/parameter
      declarations in stored routines (e.g. `v_size NVARCHAR(5)`) still carry
      the source type name. Extend the type mapping into the procedural engine
      without disturbing string literals or identifiers.

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

- [x] **Web UI** served at `/` by the API: two CodeMirror editors with SQL
      syntax highlighting (embedded, no CDN — works behind an offline reverse
      proxy), source/target selectors with swap, live dialect auto-detection,
      copy, Ctrl+Enter, and a file upload/download translate section.
      Built from `web/src/index.template.html` + `web/vendor/` via
      `python web/build.py`. New endpoints `POST /api/v1/detect` and
      `POST /api/v1/transpile/file`; detection in `core/detection.py`.
- [x] **Live syntax validation against real engines** — `tests/helpers/
      live_validation.py` + `tests/integration/test_live_syntax.py` validate
      transpiler output against SQL Server / PostgreSQL / MySQL (executed in a
      rolled-back transaction; MySQL in a throwaway database). CI job "Live
      Syntax Validation". This layer found and drove fixes for real bugs
      (NVARCHAR not mapped to PG, invalid `CASE` in indexes, typeless
      generated columns).
- [x] **Anonymized procedural fixtures** — `tests/fixtures/procedures/`
      (`procedures_sqlserver.sql`, `procedures_oracle.sql`) covering the
      stored-procedure surface, with `test_procedures_fixtures.py` (parse,
      split, anonymization guard, cross-dialect transpile-without-crash).
- [ ] **Make the procedural fixtures executable against real engines** —
      next steps (do where DB access is available):
      (1) generate the **DDL** for the tables/columns they reference (tables
      already identified; column types TBD: generic-by-use / all-VARCHAR /
      inferred); (2) optionally **simplify JOINs** (one of each kind per query,
      dropping orphaned columns) — prefer a sqlglot parse/re-emit approach over
      regex; (3) optional **dedup** of repeated blocks; (4) add a CI job that
      creates the schema and runs the scripts + their transpilations against
      real SQL Server and Oracle, then document it.
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
