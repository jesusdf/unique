# Unique — Pending Work

This document tracks all outstanding work, ordered by priority. It is the
authoritative backlog; `docs/STATUS.md` summarizes what is already done.

Last reviewed: 2026-06-21 (MySQL procedures: live-testing-driven fixes).

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
- [x] **Data-type names inside procedural bodies (P2)** — variable/parameter
      declarations in stored routines (e.g. `v_size NVARCHAR(5)`) now map to the
      target dialect's type via the procedural transformer's type map, without
      disturbing string literals or identifiers. Source types with no faithful
      equivalent (SQL_VARIANT, etc.) keep the original in a `/* UNIQUE: … */`
      comment, including unresolved `%TYPE`/`%ROWTYPE` references.
- [ ] **Restore the original from a `/* UNIQUE: … */` comment on reverse
      transpilation (P2)** — when a non-portable type was lowered to a carrier
      with the original preserved (e.g. `SQL_VARIANT` →
      `TEXT /* UNIQUE: SQL_VARIANT */`, or an unresolved
      `H_X.Y%TYPE` → `SQL_VARIANT /* UNIQUE: H_X.Y%TYPE */`), transpiling back
      should emit the original type from the comment instead of keeping the
      carrier, so a round-trip is faithful. Implementation sketch: in the
      data-type parse path, if a type token is immediately followed by a
      `/* UNIQUE: <original> */` comment, parse `<original>` and use it as the
      `DataType.name` (dropping the carrier), so the existing emit path renders
      it. Add round-trip tests (A→B→A) asserting the original type returns.
      Evaluate generalizing this to **other constructs preserved in `UNIQUE`
      comments**, not just types: e.g. a dropped `SET NOCOUNT ON` kept as
      `/* UNIQUE: SET NOCOUNT ON -- no <target> equivalent */`, an
      `OUTPUT`/`RETURNING` clause documented as a trailing `-- UNIQUE:` comment,
      `MERGE`→`INSERT ... ON DUPLICATE KEY UPDATE` notes, etc. A single
      "UNIQUE-comment restorer" pass that, when the target is the construct's
      original engine, swaps the documented original back in for the carrier/
      comment would make many lossy conversions reversible. Care needed: only
      restore when the target actually supports the original construct, and
      keep the line/`-- ` vs `/* */` comment-style rules intact.

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
      (`procedures_sqlserver.sql`, `procedures_oracle.sql`,
      `procedures_mysql.sql`, `procedures_postgresql.sql`) covering the
      stored-procedure surface, with `test_procedures_fixtures.py` (parse,
      split, anonymization guard, cross-dialect transpile-without-crash, and
      per-engine non-portable-construct guards). The MySQL and PostgreSQL
      fixtures are generated by transpiling the T-SQL fixture and are validated
      live (see below).
- [x] **Make the procedural fixtures executable against real engines** — the
      MySQL and PostgreSQL fixtures are now validated live: the whole script
      (DDL + routines) is loaded into a real engine in CI
      (`test_procedures_fixture_is_valid_live`), with all four engines in
      `_LIVE_TARGETS` and a service each in the `syntax-live` job. This drove
      the long list of real fixes in section 6.
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

## 6. MySQL stored-procedure live testing — findings (P1/P2)

Surfaced while enabling live validation of `procedures_mysql.sql` and
`procedures_postgresql.sql`. Items marked [x] are fixed and tested; [ ] are
open.

- [x] **PostgreSQL fixture — `dbo` schema everywhere** — `dbo.` survived in
      CREATE TABLE, routine names, embedded DML and scalar expressions
      (assignments, RETURN, COALESCE), naming a schema that doesn't exist in
      PostgreSQL. Now stripped in all four places (CREATE TABLE in the
      converter, names via `_qualified_name`, DML via `_pg_clean_dml`,
      expressions in `_transform_raw_sql`).
- [x] **PostgreSQL `OUTPUT`/`SQL_VARIANT`/table-vars/`NEWSEQUENTIALID`** —
      `OUTPUT inserted.col` → `RETURNING col` (qualifier stripped);
      `SQL_VARIANT` → `TEXT /* UNIQUE: SQL_VARIANT */` (lossy types absent from
      the type map now fall back to the carrier); table variables →
      `CREATE TEMPORARY TABLE` with column types mapped via the project
      converter; `NEWSEQUENTIALID()`/`NEWID()` → `gen_random_uuid()`.
- [x] **PostgreSQL `CONVERT`/`HASHBYTES` in a scalar `RETURN`** — was left
      untranslated (`CONVERT(nvarchar(max), HASHBYTES('SHA2_256', x), 2)`).
      Scalar expressions containing these now route through sqlglot, and the
      spurious `TO_CHAR(SHA256(...), '…')`/`(MAX)` cast that sqlglot emits
      (misreading the style code as a date format) is unwrapped to the bare
      hash call.
- [x] **Parser: assignment-SELECT / SET absorbing following statements** — a
      multi-line `SELECT @v = … FROM …` followed by a comment and
      `SET`/`INSERT` concatenated everything into one fragment; and `SET @v =
      <expr>` swallowed a following DML statement. Both now stop at a statement
      boundary (own-line comment, new statement keyword, or a DML verb on a new
      line). This was a silent semantic-loss bug.
- [x] **T-SQL string `+` concatenation on PostgreSQL (P2)** — was rewritten to
      `CONCAT` for MySQL but left as `+` for PostgreSQL, where string
      concatenation is `||` (and `+` on text errors). The concat rewrite is now
      shared (`_rewrite_string_concat`): MySQL emits `CONCAT(...)`, PostgreSQL
      chains operands with the `||` (DPipe) operator. Numeric `+` is left
      untouched; detection uses string literals and known string variables.
      Tested (TestPostgreSQLStringConcat).

- [x] **Empty block from a dropped SET option** — `SET NOCOUNT ON` (and the
      other dialect-specific SET options) were silently removed, which could
      leave `IF ... THEN END IF` (rejected by MySQL) and erased information.
      Now preserved as a `/* UNIQUE: <original> -- no <target> equivalent */`
      comment, and any IF/WHILE/LOOP/FOR/BEGIN-END left without an executable
      statement gets a dialect no-op (`DO 0;` MySQL, `NULL;` Oracle/PG).
- [x] **T-SQL assignment-select dropped** — `SELECT @v = expr [, ...]` was
      routed to embedded DML, where sqlglot turned `=` into a column alias
      (`SELECT col AS v_x`) and lost the assignment. The T-SQL dispatcher now
      detects this and emits `SELECT ... INTO`. Ordinary selects unaffected.
- [x] **`OUTPUT ... INTO @var` → invalid `RETURNING` on MySQL (P1)** — an
      `INSERT ... OUTPUT inserted.col INTO @var` became
      `INSERT ... RETURNING inserted.col` for MySQL, which is invalid (MySQL
      has no RETURNING) and dropped the `INTO @var` target. The procedural
      MySQL DML cleaner now strips a RETURNING clause, emits the base
      statement, and documents the dropped clause with a `-- UNIQUE:` comment
      (Oracle/PostgreSQL keep native RETURNING). Fixed and tested
      (TestOutputClauseToMySQL); the 4 fixture occurrences are now valid.
- [x] **Table variables `DECLARE @t TABLE (...)` on MySQL (P1)** — were emitted
      verbatim as `DECLARE v_t TABLE (...)`, which MySQL rejects, and a table
      variable immediately followed by `INSERT INTO @t ... ; SELECT ... FROM @t`
      mis-parsed and dropped the following statement. Fixed: the transformer
      rewrites a table-variable DECLARE to a `CREATE TEMPORARY TABLE` in the
      executable body (column types mapped through sqlglot, so UNIQUEIDENTIFIER
      etc. are translated) with a documenting comment; and the embedded-DML
      splitter now ends an `INSERT ... VALUES (...)` before a following SELECT
      (a genuine INSERT ... SELECT still stays together). The 4 fixture
      occurrences are now valid and their UNIQUEIDENTIFIER columns mapped.
      Tested (TestTableVariableToMySQL, TestInsertValuesSelectBoundary).
      Oracle/PostgreSQL get the same CREATE TEMPORARY TABLE rewrite, but their
      column-type mapping and the in-PL/SQL DDL restriction still need
      refinement (MySQL — the live-tested target — is correct).
- [x] **TRY/CATCH → invalid EXCEPTION block on MySQL (P1)** — a T-SQL
      TRY/CATCH was emitted with Oracle/PostgreSQL `EXCEPTION WHEN OTHERS THEN`
      syntax for every non-T-SQL target, which MySQL rejects. MySQL now gets a
      `DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN <catch> END;` declared before
      the protected statements; Oracle/PostgreSQL keep the EXCEPTION block.
      Tested (TestTryCatchToMySQL). Not in the current fixture, but common in
      real error-handling code.
- [ ] **`BEGIN TRAN`/`BEGIN TRANSACTION` not bounded (P2)** — a transaction
      statement followed by DML on the same/next line mis-parses
      (`TRAN AS \`UPDATE\``), and `@@ERROR` in the following `IF` is commented
      out, breaking the condition. Needs the transaction keywords recognized as
      their own statements. Not in the current fixture.
- [ ] **`SET IDENTITY_INSERT t ON/OFF` (P3)** — mistranslated to
      `IDENTITY_INSERT AS t`. No portable equivalent; emit a documented comment
      (MySQL/Oracle/PG manage identity insertion differently). Not in fixture.
- [ ] **`THROW`/`RAISERROR` argument shape (P2)** — mapped to MySQL `SIGNAL
      SQLSTATE '45000' SET MESSAGE_TEXT = ...` but the message/number/severity
      arguments are passed through raw (e.g. `MESSAGE_TEXT = 50000, 'msg', 1`),
      which is not valid. Needs proper extraction of the message text (and a
      format-substitution strategy for RAISERROR's printf-style args).
- [ ] **`@@ERROR` in a condition → broken IF (P2)** — `IF @@ERROR <> 0` becomes
      `IF /* @@ERROR */ <> 0 THEN` (commented-out operand leaves an invalid
      condition). Map `@@ERROR`/`@@ROWCOUNT`-style globals used in expressions,
      or rewrite the construct; at minimum avoid emitting a syntactically
      broken condition. (`@@ROWCOUNT` alone already maps to `ROW_COUNT()`.)
- [ ] **`WAITFOR DELAY '…'` on MySQL (P3)** — mistranslated to `WAITFOR AS
      DELAY`. MySQL equivalent is `DO SLEEP(seconds)`. Not in the fixture.
- [ ] **`TOP n PERCENT` → invalid `LIMIT n PERCENT` on MySQL (P2)** — MySQL
      LIMIT takes no PERCENT. Needs a rewrite (e.g. `LIMIT CEIL(n/100 * (SELECT
      COUNT(*) ...))`) or a documented comment. Not in the current fixture.
- [ ] **Double-quoted string literal → backtick identifier (P2)** — with
      T-SQL `QUOTED_IDENTIFIER OFF`, `CHARINDEX(",", s)` uses `"` for a string,
      but sqlglot (QUOTED_IDENTIFIER ON by default) treats it as an identifier
      and emits `LOCATE(\`,\`, s)` for MySQL — a column reference, not the
      comma character. Single-quoted literals are fine. Not in the current
      fixture (which uses single quotes). Consider honoring a detected
      `SET QUOTED_IDENTIFIER OFF`.

## 7. Triggers — coverage to review (P2)

- [x] **Trigger transpilation test coverage** — added `test_triggers.py`
      covering firing modes (BEFORE/AFTER/INSTEAD OF) and granularity
      (row-level FOR EACH ROW vs statement-level) across engines, plus the
      Oracle mutating-table hazard (body preserved, not auto-rewritten). Fixed
      two real bugs found while writing them: the PostgreSQL emitter produced a
      broken `EXECUTE FUNCTION {name}_func()` (literal placeholder) and dropped
      the body — it now emits a proper `CREATE FUNCTION ... RETURNS TRIGGER`
      plus the `CREATE TRIGGER` that calls it; and MySQL emitted an invalid
      `INSTEAD OF` clause — it now documents the substitution with a
      `-- UNIQUE:` comment and falls back to BEFORE. Still open: translating the
      `inserted`/`deleted` pseudo-tables (T-SQL) to `NEW`/`OLD` (`:NEW`/`:OLD`)
      and the statement- vs row-level semantic gap (see new item below).
- [ ] **Trigger pseudo-table / granularity semantics (P2)** — T-SQL triggers
      are statement-level with `inserted`/`deleted` pseudo-tables; Oracle/MySQL/
      PostgreSQL row-level triggers use `:NEW`/`:OLD` / `NEW`/`OLD`. The
      transpiler currently keeps `inserted`/`deleted` verbatim (invalid on the
      other engines) and forces FOR EACH ROW. Map the pseudo-tables and either
      preserve statement-level semantics (e.g. PostgreSQL transition tables
      `REFERENCING NEW TABLE`) or document the change. This is a real semantic
      gap, not just syntax.



## 8. Web UI, docs and packaging (P2/P3)

- [x] **Editor boxes overflow on long lines (P2)** — the SQL input/output
      editors widened past the viewport when pasting very long lines. Fixed in
      `web/src/index.template.html`: grid items get `min-width: 0`, the editors
      get `max-width: 100%`, CodeMirror keeps its horizontal scrollbar inside
      its box (`.CodeMirror-scroll { overflow-x: auto }`), and the editors are
      sized with `setSize("100%", …)`. Rebuilt `static/index.html` via
      `web/build.py`.
- [x] **README slimming + docs split (P3)** — README rewritten to focus on the
      sqlglot-based value proposition (a dedicated "Built on sqlglot — and what
      Unique adds" section: procedural engine, shape-changing rewrites,
      documented/reversible lossy conversions, comment preservation,
      functional-equivalence guards, whole-script orchestration). Cut from 189
      to ~96 lines. Installation/deployment moved to
      [docs/06-installation.md](06-installation.md) and the CLI/Python/REST/web
      interfaces to [docs/07-interfaces.md](07-interfaces.md), both linked from
      the README's Documentation section. The duplicated Architecture / Project
      Structure / Development prose was removed (it already lives in
      `02-architecture.md` and `04-development-guide.md`).
- [x] **docker-compose example for end users (P3)** — the default `unique`
      service now pulls `jesusdf/unique:${UNIQUE_TAG:-latest}` from Docker Hub
      (no build needed); the build-from-source path is kept under the `dev`
      profile for contributors. Documented in `06-installation.md`.
- [x] **Pin sqlglot to an exact version (P2)** — was `sqlglot>=25.0.0` (open
      lower bound, pulled whatever was newest at install time); now pinned to
      `sqlglot==30.11.0` so upstream changes can't silently break
      transpilation. Upgrades are deliberate (bump, run suite + live job,
      regenerate fixtures, review). Vendoring/forking analysis (GRUB-style
      pinned sources + patch queue) recorded in `docs/sqlglot-dependency.md`;
      recommendation is pin-only for now, fork only if issues accumulate that
      can't be solved transformer-side.
- [x] **Relicense to MIT (P2)** — switched from AGPL-3.0 to the MIT License:
      replaced the `LICENSE` file, swapped the AGPL header in all Python files
      for a short SPDX MIT header, and updated `pyproject.toml` and the README.
      Source-file copyright lines aligned to the `LICENSE` holder.
- [x] **CI: build the Docker image only on tags, gated on live checks (P2)** —
      the `docker` job now runs only on a `v*` tag push (not on every push to
      `main`) and `needs` the full gate including `metadata-live` and
      `syntax-live`, so a published image is always verified end-to-end against
      the real engines. `latest` now tracks the latest tagged release.

## 9. Known limitations to keep documented (not bugs)

These have no faithful cross-engine equivalent and are intentionally
emitted as comments/warnings (see `docs/03-unsupported.md`):

- SQL Server system procedures (`sp_addextendedproperty`, `sp_rename`, ...).
- SQL*Plus session directives (`SET FEEDBACK`, etc.) and `rem`/`prompt`
  (now preserved as comments).
- `%TYPE`/`%ROWTYPE` without `--db-url` (emitted as a carrier type with the
  original preserved in a `/* UNIQUE: … */` comment, plus a warning).
- `EXECUTE IMMEDIATE ... USING` bind variables (T-SQL `sp_executesql`).
- Engine-specific physical features (partitioning, tablespaces, filegroups,
  index storage clauses).
