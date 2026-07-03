# Unique — Completed Work

This document archives finished work, moved out of `docs/TODO.md` to keep the
backlog focused on what is genuinely pending. Items are grouped by the area
they originally belonged to. `docs/STATUS.md` summarizes the project state at a
higher level; this file keeps the detailed history (the *why* and *how* of each
fix), which is useful when revisiting a feature or debugging a regression.

Legend: **P1** high impact · **P2** medium · **P3** niche. Parenthesized counts
were occurrences across the four real-world fixtures (all 12 directional pairs).

---

## 1. DDL statements wired through the IR (P1)

- [x] **ALTER TABLE** (180) — `ADD CONSTRAINT` (FK/PK/default/check),
      `ADD/DROP/ALTER COLUMN`. Round-tripped through sqlglot via
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
      outside a single column are captured as PassthroughSQL fragments and
      re-transpiled per dialect (preserved instead of dropped).
- [x] **User-defined / domain types** — T-SQL `[dbo].[Name]` keeps its type
      name instead of collapsing to the literal USER-DEFINED.
- [x] **MySQL `... BINARY` column attribute** — stripped before parsing
      (the BINARY(n) data type and BINARY(expr) function are preserved).
      `ON UPDATE CURRENT_TIMESTAMP` is handled by sqlglot directly.
- [x] **Computed/persisted columns** (`AS (expr) PERSISTED`) — captured as a
      passthrough fragment. Live validation showed PostgreSQL, Oracle **and
      MySQL** all reject a generated column without an explicit type (which
      T-SQL computed columns don't declare), so for every target we emit a
      documented `-- UNIQUE:` comment **outside** the column list (keeping the
      CREATE TABLE valid). The expression is preserved in the comment;
      previously it was lost and the column became a bare VARCHAR.
- [x] **Invalid `CASE` in transpiled indexes** — sqlglot emulates PostgreSQL's
      NULLS ordering by prefixing an index key with
      `CASE WHEN col IS NULL THEN 1 ELSE 0 END, col`, invalid inside an index
      column list in T-SQL/MySQL/Oracle. Collapsed back to the bare column for
      every target except PostgreSQL. Found by live validation.
- [x] **`VARCHAR(MAX)` / `NVARCHAR(MAX)` column type not mapped (P1)** — a
      T-SQL `VARCHAR(MAX)`/`NVARCHAR(MAX)` column was emitted as a bare
      `VARCHAR` (no length), which MySQL/Oracle reject; the `CREATE TABLE`
      failed and every later statement referencing that table errored
      (`1146 … doesn't exist`). The MAX marker is dropped during IR conversion
      (non-numeric param), so the emitter maps a bare character type to the
      dialect's large-text type via `_BARE_CHAR_BIGTEXT`: MySQL `LONGTEXT`,
      PostgreSQL `TEXT`, Oracle `CLOB`/`NCLOB`, T-SQL `VARCHAR(MAX)`. Found by
      the live MySQL/PostgreSQL procedures-fixture checks.

## 3. Procedural engine refinements (P2)

- [x] **Silently-dropped SELECT clauses** — row locks (`FOR UPDATE`),
      `QUALIFY`, `START WITH`/`CONNECT BY`, and `SELECT INTO <table>` are routed
      through sqlglot instead of discarded, preserving semantics (or a
      documented comment where no equivalent exists).
- [x] **Cursor `FOR` loop → explicit cursor** — Oracle implicit cursor
      FOR-loops expand to a structurally complete explicit cursor for T-SQL
      (DECLARE/OPEN/FETCH/WHILE @@FETCH_STATUS/CLOSE/DEALLOCATE) and MySQL
      (DECLARE cursor + NOT FOUND handler + LOOP/FETCH/LEAVE/CLOSE). The
      developer only fills the per-column FETCH INTO variables.
- [x] **`CONNECT BY` (Oracle hierarchical)** — kept as-is for Oracle; other
      targets get a documented comment pointing to a WITH RECURSIVE CTE rewrite
      instead of silently dropping the clause.
- [x] **`MERGE`** — Oracle and PostgreSQL emit native MERGE (via
      PassthroughSQL); MySQL (no MERGE) gets a documented comment pointing to
      `INSERT ... ON DUPLICATE KEY UPDATE`.
- [x] **`OUTPUT` / `RETURNING` clause** — T-SQL OUTPUT is extracted safely
      (preserving the WHERE clause, whose loss on DELETE/UPDATE would be a
      data-loss bug) and mapped to RETURNING for PostgreSQL/Oracle; PG/Oracle
      RETURNING maps back to T-SQL OUTPUT. MySQL keeps the base statement plus a
      documented comment.
- [x] **`@@IDENTITY` / `SCOPE_IDENTITY()`** → `LASTVAL()` (PG) /
      `LAST_INSERT_ID()` (MySQL) / documented `<sequence>.CURRVAL` (Oracle).
- [x] **Data-type name mapping in CREATE TABLE** — non-portable types
      (NVARCHAR/NCHAR/NTEXT, DATETIME2, MONEY, BIT, UNIQUEIDENTIFIER/UUID,
      VARBINARY/BYTEA, ...) map to the target dialect both in our emitter and in
      passthrough DDL. Found by the live syntax-validation layer.
- [x] **Data-type names inside procedural bodies (P2)** — variable/parameter
      declarations in stored routines (e.g. `v_size NVARCHAR(5)`) map to the
      target dialect's type without disturbing string literals or identifiers.
      Source types with no faithful equivalent (SQL_VARIANT, etc.) keep the
      original in a `/* UNIQUE: … */` comment, including unresolved
      `%TYPE`/`%ROWTYPE` references.
- [x] **Reverse transpilation: restore original *types* from `/* UNIQUE: … */`
      carrier comments (P2)** — a type lowered to a carrier with the original
      preserved (`SQL_VARIANT` → `TEXT /* UNIQUE: SQL_VARIANT */`, `emp.sal%TYPE`
      → `LONGTEXT /* UNIQUE: emp.sal%TYPE */`) now round-trips faithfully. The
      procedural parser captures the carrier comment (`_take_carrier_origin`,
      read directly off the current token since `_match_type` skips comments) and
      attaches the original to the parsed type as `origin_comment`. The
      transformer then re-maps the *original* for the target: it returns the
      original where the target supports it natively (so T-SQL recovers
      `SQL_VARIANT` with **no** redundant comment; Oracle recovers `%TYPE`), and
      re-applies a carrier where it doesn't (PG `TEXT`, MySQL `LONGTEXT`, Oracle
      `ANYDATA`, each with the `/* UNIQUE: … */` note). Two supporting fixes: a
      lossy type whose target carrier equals the original is emitted plainly
      (no redundant comment), and a `%TYPE`/`%ROWTYPE` reference is kept as-is for
      an Oracle target (Oracle supports it natively). Validated live on
      MySQL/PostgreSQL/Oracle; fixtures byte-for-byte unchanged. Tested
      (TestCarrierTypeRestoration). (Generalizing the restorer to non-type
      constructs remains open — see TODO.)

## 4. Function mapping gaps (P2)

- [x] **Substring-position functions** — `CHARINDEX`↔`INSTR`↔`LOCATE`↔`STRPOS`
      translated with correct argument reordering (start position kept).
- [x] **`DECODE`→`CASE`** — Oracle DECODE translated to a searched CASE.
- [x] **String aggregation** — `STRING_AGG` ↔ `LISTAGG` ↔ `GROUP_CONCAT`
      (handles MySQL `SEPARATOR`). Quote-aware argument splitting.
- [x] **`NVL2`→`CASE`** — `NVL2(e, a, b)` → `CASE WHEN e IS NOT NULL THEN a
      ELSE b END` (Oracle source).
- [x] **`TO_CHAR`/`TO_DATE` with date-format strings (Oracle→MySQL)** — mapped
      to `DATE_FORMAT`/`STR_TO_DATE` with format-pattern translation.
- [x] **`CONVERT` with style codes (T-SQL)** — routes through sqlglot, which
      maps the numeric style codes to the right TO_CHAR/DATE_FORMAT patterns.
- [x] **Date-format strings** — bidirectional Oracle/PostgreSQL `TO_CHAR`/
      `TO_DATE` ↔ MySQL `DATE_FORMAT`/`STR_TO_DATE`.
- [x] **`CHARINDEX` in standalone DML → invalid `STR_POSITION` (P2)** — in a
      non-procedural DML batch, sqlglot parses `CHARINDEX(needle, haystack)`
      into a structured `exp.StrPosition` (args in named slots, not
      `expressions`), so the native converter's generic `_convert_function`
      read only the haystack and emitted `STR_POSITION(haystack)`.
      `_convert_function` now canonicalizes `StrPosition` to
      `CHARINDEX(needle, haystack[, start])`, and `_emit_function` renders the
      right per-dialect function/arg order: MySQL `LOCATE`, Oracle `INSTR`
      (haystack first), PostgreSQL `POSITION(needle IN haystack)` (with a
      `SUBSTRING`+offset rewrite for a start position), T-SQL `CHARINDEX`.
      Validated live. Tested (TestCharIndexStandalone).

## 5. Tooling / infrastructure (P3)

- [x] **Web UI** served at `/` by the API: two CodeMirror editors with SQL
      syntax highlighting (embedded, no CDN), source/target selectors with swap,
      live dialect auto-detection, copy, Ctrl+Enter, file upload/download.
      Built from `web/src/index.template.html` + `web/vendor/` via
      `python web/build.py`. Endpoints `POST /api/v1/detect`,
      `POST /api/v1/transpile/file`; detection in `core/detection.py`.
- [x] **Live syntax validation against real engines** —
      `tests/helpers/live_validation.py` + `tests/integration/test_live_syntax.py`
      validate transpiler output against SQL Server / PostgreSQL / MySQL
      (rolled-back transaction; MySQL in a throwaway database). CI job
      "Live Syntax Validation". Drove fixes for real bugs.
- [x] **Anonymized procedural fixtures** — `tests/fixtures/procedures/`
      (`procedures_sqlserver.sql`, `procedures_oracle.sql`,
      `procedures_mysql.sql`, `procedures_postgresql.sql`) with
      `test_procedures_fixtures.py`. The MySQL/PostgreSQL/Oracle fixtures are
      generated by transpiling the T-SQL fixture and validated live.
- [x] **Make the procedural fixtures executable against real engines** — the
      whole script (DDL + routines) is loaded into a real engine in CI
      (`test_procedures_fixture_is_valid_live`), all four engines in
      `_LIVE_TARGETS` with a service each in the `syntax-live` job.
- [x] **Round-trip fidelity tests** (A→B→A) on the public fixtures — caught a
      missing statement-terminator bug; output statements are now terminated.
- [x] **Generic transpilation invariants** (`tests/helpers/invariants.py`) —
      (1) element conservation (structural keywords not dropped unless
      documented with a `-- UNIQUE:` comment); (2) round-trip content similarity
      (A→B→A' normalized token-set Jaccard with per-source floors).
- [x] **Performance** — analyzed; ~91% of time is sqlglot parsing, proportional
      to statement count and inherent to the parser. No redundant work on our
      side; no micro-optimization warranted.
- [x] **Document the `--db-url`/`db_url` connection parameter (P3)** — added a
      "Database connection" section to `docs/07-interfaces.md`.

## 6. MySQL stored-procedure live-testing findings (P1/P2)

Surfaced while enabling live validation of `procedures_mysql.sql`. The
`syntax-live` job was driven error-by-error to green; the MySQL and PostgreSQL
procedures fixtures validate with 0 errors against real engines.

- [x] **Parameterless routine missing `()` on MySQL/PostgreSQL (P1)** — the
      emitter always emits `()` for those engines when there are no parameters
      (Oracle allows omitting them). Tested (TestParameterlessRoutineParens).
- [x] **Inline table-valued function (`RETURNS TABLE`) (P1)** — documented with
      a per-engine `-- UNIQUE:` note and the non-portable translation commented
      out, so the script stays valid. Tested (TestInlineTableValuedFunction).
- [x] **Trigger `UPDATE(col)` predicate (P1)** — rewritten per engine: MySQL
      `NOT (NEW.col <=> OLD.col)`, PostgreSQL `(NEW.col IS DISTINCT FROM
      OLD.col)`, Oracle `UPDATING('col')`. Only the function-style
      `UPDATE(<column>)` predicate is matched. Tested (TestTriggerUpdatePredicate).
- [x] **Table-valued function in a `FROM` clause on MySQL (P1)** — the MySQL DML
      cleaner detects a function in FROM/JOIN position (via sqlglot) and comments
      the statement out with a `-- UNIQUE:` note; `JSON_TABLE` and the
      `STRING_SPLIT`→`JSON_TABLE` rewrite are kept. Tested
      (TestTableValuedFunctionInFrom).
- [x] **Line comments inside a captured expression break the statement (P1)** —
      the expression capture converts line comments to `/* … */` block comments
      (`_line_comment_to_block`). Tested (TestInlineCommentInCapturedExpression).
- [x] **`RETURN` in a MySQL procedure — bare or with a value (P1)** — in a
      procedure the body is wrapped in a `proc_exit:` labeled block and any
      `RETURN` becomes `LEAVE proc_exit;` (discarded value documented); in a
      function `RETURN <value>` is kept. A valueless `RETURN` followed by a
      statement keyword no longer swallows the following statement. Tested
      (TestBareReturnInProcedure, TestReturnValueInProcedure).
- [x] **Empty block from a dropped SET option** — `SET NOCOUNT ON` and the other
      SET options are preserved as a `/* UNIQUE: <original> -- no <target>
      equivalent */` comment, and any IF/WHILE/LOOP/FOR/BEGIN-END left without an
      executable statement gets a dialect no-op (`DO 0;` MySQL, `NULL;` Oracle/PG).
- [x] **T-SQL assignment-select dropped** — `SELECT @v = expr [, ...]` is
      detected and emitted as `SELECT ... INTO` (sqlglot otherwise turned `=`
      into a column alias). Ordinary selects unaffected.
- [x] **Parser: assignment-SELECT / SET absorbing following statements** — both
      now stop at a statement boundary (own-line comment, new statement keyword,
      or a DML verb on a new line). Was a silent semantic-loss bug.
- [x] **`OUTPUT ... INTO @var` → invalid `RETURNING` on MySQL (P1)** — the MySQL
      DML cleaner strips a RETURNING clause, emits the base statement, and
      documents the dropped clause (Oracle/PostgreSQL keep native RETURNING).
      Tested (TestOutputClauseToMySQL).
- [x] **Table variables `DECLARE @t TABLE (...)` on MySQL (P1)** — rewritten to a
      `CREATE TEMPORARY TABLE` in the executable body (column types mapped via
      sqlglot); the embedded-DML splitter ends an `INSERT ... VALUES (...)`
      before a following SELECT. Tested (TestTableVariableToMySQL,
      TestInsertValuesSelectBoundary).
- [x] **TRY/CATCH → invalid EXCEPTION block on MySQL (P1)** — MySQL gets a
      `DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN <catch> END;` before the
      protected statements; Oracle/PostgreSQL keep the EXCEPTION block. Tested
      (TestTryCatchToMySQL).
- [x] **`THROW`/`RAISERROR` argument shape (P2)** — a string becomes
      `MESSAGE_TEXT = '<msg>'`; a numeric message id becomes
      `MESSAGE_TEXT = 'Application error', MYSQL_ERRNO = <id>`; dropped
      severity/state documented. Oracle/PostgreSQL use the message argument only.
      Tested (TestRaiserrorToMySQLSignal).
- [x] **`BEGIN TRAN`/`BEGIN TRANSACTION` not bounded (P2)** — transaction
      keywords recognized as their own statements (parser dispatch + lexer
      keywords TRAN/TRANSACTION/SAVE/WORK) and emitted via `TransactionStatement`
      per dialect: `BEGIN TRANSACTION` → MySQL `START TRANSACTION`,
      documented-comment for Oracle/PostgreSQL; `COMMIT`/`ROLLBACK` pass through;
      `SAVE TRAN name`/`ROLLBACK TRAN name` → `SAVEPOINT`/`ROLLBACK TO SAVEPOINT`.
      Tested (TestTransactionControl).
- [x] **`SET IDENTITY_INSERT t ON/OFF` (P3)** — recognized in the SET parser and
      emitted as a documented `/* UNIQUE: … */` comment. A related parser fix
      stops an embedded INSERT/DELETE/SELECT before a following statement-level
      `SET` (peeking past `SET` to tell a new statement from an UPDATE/MERGE
      `SET <col>` clause). Tested (TestSetIdentityInsert).
- [x] **`@@ERROR` in a condition → broken IF (P2)** — `@@ERROR`/`@@TRANCOUNT`
      map to a neutral `0` carrying an inline block comment so the routine stays
      valid; Oracle keeps the valid `SQLCODE` function. Block comments only.
      Validated live. Tested (TestErrorGlobalInCondition).
- [x] **`WAITFOR DELAY '…'` (P3)** — parsed into a `WaitForStatement` (literal
      converted to seconds) and emitted per dialect: MySQL `DO SLEEP(n)`,
      PostgreSQL `PERFORM pg_sleep(n)`, Oracle `DBMS_LOCK.SLEEP(n)`, T-SQL kept;
      `WAITFOR TIME` documented. Tested (TestWaitFor).
- [x] **`TOP n PERCENT` (P2)** — the PERCENT flag is carried on
      `LimitClause.percent`. Oracle emits native `FETCH FIRST n PERCENT ROWS
      ONLY`; MySQL/PostgreSQL emit a valid row `LIMIT n` plus a documenting
      comment. Validated live. Tested (test_top_percent_*).
- [x] **Double-quoted string literal under `QUOTED_IDENTIFIER OFF` (P2)** — the
      transpiler tracks the `SET QUOTED_IDENTIFIER ON/OFF` session setting across
      batches; while OFF, `"..."` tokens are rewritten to `'...'` string literals
      before parsing (`_double_quoted_to_strings`, comment- and string-aware).
      Tested (TestQuotedIdentifierOff).

### PostgreSQL stored-procedure live-testing findings (P1/P2)

Surfaced while validating `procedures_postgresql.sql` against a real engine.

- [x] **PostgreSQL fixture — `dbo` schema everywhere** — stripped in CREATE
      TABLE (converter), routine names (`_qualified_name`), DML (`_pg_clean_dml`)
      and scalar expressions (`_transform_raw_sql`).
- [x] **PostgreSQL `OUTPUT`/`SQL_VARIANT`/table-vars/`NEWSEQUENTIALID`** —
      `OUTPUT inserted.col` → `RETURNING col`; `SQL_VARIANT` →
      `TEXT /* UNIQUE: SQL_VARIANT */`; table variables → `CREATE TEMPORARY
      TABLE`; `NEWSEQUENTIALID()`/`NEWID()` → `gen_random_uuid()`.
- [x] **PostgreSQL `CONVERT`/`HASHBYTES` in a scalar `RETURN`** — scalar
      expressions route through sqlglot; the spurious `TO_CHAR(SHA256(...), …)`
      cast sqlglot emits is unwrapped to the bare hash call.
- [x] **T-SQL string `+` concatenation on PostgreSQL (P2)** — the shared
      `_rewrite_string_concat`: MySQL emits `CONCAT(...)`, PostgreSQL chains
      operands with `||`. Numeric `+` untouched. Tested (TestPostgreSQLStringConcat).
- [x] **`NULLS FIRST`/`NULLS LAST` in a PRIMARY KEY/UNIQUE constraint (P1)** —
      stripped for Oracle and PostgreSQL in `_emit_passthrough_inline`.
- [x] **OUT parameter with a DEFAULT / OUT after a defaulted param (P1)** — the
      emitter drops the default from every OUT/INOUT param and from any IN param
      before the last OUT/INOUT param, keeping the routine creatable.
- [x] **Inline (multi-variable) DECLARE not hoisted (P1)** — `_split_declarations`
      flattens a `StatementList` of declarations so every one is hoisted into the
      DECLARE/IS section (also applied to the PostgreSQL trigger function body).
- [x] **`EXEC proc @x OUTPUT` → invalid `EXECUTE … OUTPUT` (P1)** —
      `_emit_pg_execute` distinguishes the three EXEC shapes: a named call →
      `CALL name(args)` (dropping `OUTPUT`); dynamic SQL → plpgsql
      `EXECUTE <text> [USING …]`.
- [x] **`RETURN <value>` in a PostgreSQL procedure (P1)** — emitted as a bare
      `RETURN;` with the discarded value in a `-- UNIQUE:` comment; functions
      keep `RETURN <value>`. Tracked via an `_in_pg_procedure` flag.
- [x] **`VARCHAR(MAX)` in a procedure-body CAST/expression (P1)** —
      `_pg_clean_dml` rewrites `(N)VARCHAR(MAX)` → `TEXT`.
- [x] **`DATEDIFF(<non-day part>, …)` and `CHAR(n)` in a scalar expression
      (P1)** — scalar expressions containing `DATEDIFF`/`CHAR` route through
      sqlglot, rendering `EXTRACT(EPOCH …)` and `CHR(n)`. DATEADD is left to its
      dedicated handler.

## 7. Triggers (P2)

- [x] **Trigger transpilation test coverage** — `test_triggers.py` covers firing
      modes (BEFORE/AFTER/INSTEAD OF) and granularity (row vs statement) across
      engines, plus the Oracle mutating-table hazard. Fixed two real bugs: the
      PostgreSQL emitter produced a broken `EXECUTE FUNCTION {name}_func()` and
      dropped the body — it now emits a proper `CREATE FUNCTION ... RETURNS
      TRIGGER` plus the `CREATE TRIGGER` that calls it; and MySQL emitted an
      invalid `INSTEAD OF` clause — it now documents the substitution and falls
      back to BEFORE. (The `inserted`/`deleted` pseudo-table mapping remains open
      — see TODO.)

- [x] **Trigger pseudo-tables `inserted`/`deleted` (P2)** — a T-SQL trigger
      body's pseudo-tables are now handled per use (`_in_trigger` flag +
      `_rewrite_trigger_pseudotables`). **Column qualifiers** (`inserted.col`/
      `deleted.col`) map to the row-level `NEW.col`/`OLD.col` (`:NEW`/`:OLD` for
      Oracle) — previously `_pg_clean_dml` stripped them to a bare column,
      corrupting the semantics (`WHERE id = inserted.id` → `WHERE id = id`). A
      **set-based use** (`FROM inserted`/`JOIN deleted`), which has no row-level
      equivalent, is commented out with a `-- UNIQUE:` note pointing to the
      manual rewrite (PostgreSQL transition tables / Oracle compound trigger /
      no MySQL equivalent), with a dialect no-op so an enclosing IF isn't left
      empty — instead of emitting SQL that fails at runtime. The strip is kept
      for the non-trigger `OUTPUT`→`RETURNING` case (guarded by `_in_trigger`).
      Fixtures regenerated; validated live on MySQL/PostgreSQL/Oracle (0 errors).
      Tested (TestTriggerPseudoTables). The full set-based *preservation* (auto
      transition tables / compound triggers) remains a possible future
      enhancement.

## 8. Web UI, docs and packaging (P2/P3)

- [x] **Editor boxes overflow on long lines (P2)** — fixed in
      `web/src/index.template.html` (grid `min-width: 0`, editor `max-width:
      100%`, `.CodeMirror-scroll { overflow-x: auto }`, `setSize("100%", …)`);
      rebuilt `static/index.html`.
- [x] **README slimming + docs split (P3)** — README focused on the
      sqlglot-based value proposition; installation/deployment moved to
      `docs/06-installation.md`, interfaces to `docs/07-interfaces.md`.
- [x] **docker-compose example for end users (P3)** — the default `unique`
      service pulls `jesusdf/unique:${UNIQUE_TAG:-latest}`; build-from-source
      kept under the `dev` profile. Documented in `06-installation.md`.
- [x] **Pin sqlglot to an exact version (P2)** — pinned to `sqlglot==30.11.0`.
      Vendoring/forking analysis in `docs/sqlglot-dependency.md`; recommendation
      is pin-only for now.
- [x] **Relicense to MIT (P2)** — replaced the `LICENSE` file, swapped the AGPL
      header for a short SPDX MIT header in all Python files, updated
      `pyproject.toml` and the README.
- [x] **CI: build the Docker image only on tags, gated on live checks (P2)** —
      the `docker` job runs only on a `v*` tag push and `needs` the full gate
      including `metadata-live` and `syntax-live`. `latest` tracks the latest tag.

## 9. Per-engine procedural plugin refactor + web polish (P1/P2)

The procedural engine (the value-add over sqlglot) did not follow the plugin
architecture the project promises ("each dialect a self-contained plugin; adding
an engine doesn't touch the core"): it carried ~126 target-dialect conditionals
(0 lexer, 11 parser, 58 transformer, 68 emitter). Refactored to a per-engine
plugin shape, then the web UI was polished.

- [x] **Emitter → per-target plugin package** — `ProceduralEmitter` is now a
      base class (shared structure + overridable hooks) with one subclass per
      target (`TSqlEmitter`/`OracleEmitter`/`PostgresEmitter`/`MySqlEmitter`),
      selected by a factory via `__new__`. Every per-engine `if/elif` became an
      overridable method/hook; the base has **0 dialect dispatch conditionals**
      (down from 68). Fixed a dead `return` in `_translate_cursor_attrs` and an
      Oracle RETURN/IN regression caught mid-refactor (guarded by
      `TestPerEngineRoutineSurface`); extracted a shared `_emit_indented_stmts`.
- [x] **Transformer → per-target plugin package, pair-aware** — same base +
      per-target subclass + factory. A transform is a *source→target* operation,
      so only target-only decisions moved into subclasses (via hooks like
      `_system_var_map`, `_varchar_max_type`, `_uses_set_statement`,
      `_transform_try_catch`, `_update_predicate`, `_fix_target_dml`, …); the
      pair-dependent logic (variable naming `@x`→`V_X`/`v_x`/`@x`; scalar-function
      mappings CHARINDEX/INSTR/LOCATE/STRPOS, DATEADD, DATEDIFF) and source-only
      logic stay in the base parameterized by `self._source`, by design.
- [x] **Parser — source-family consolidation** — the repeated body-parsing
      branches became a single `_parse_routine_body` helper and an intentional
      `_is_tsql_source()` predicate, rather than a 4-way subclass split (over-
      structure for an almost-entirely-shared parser). Only the MySQL
      parameter-syntax branch remains (a real source-family variation point).
- [x] **Physical plugin layout** — `emitter.py`/`transformer.py` became
      `emitter/` and `transformer/` packages mirroring `dialects/{engine}/`:
      `{base,tsql,oracle,postgresql,mysql}.py`, each engine module
      self-registering on import, `__init__.py` re-exporting the factory so the
      public import path is unchanged. Adding an engine = one module + one
      import line, touching no core logic.
- [x] **Docs/skills updated** — `02-architecture.md`, `05-procedural-engine.md`
      and `SKILL-project-overview.md` describe the per-engine plugin layout. The
      `SKILL-development-workflow.md` gained a mandatory "Analyze before changing"
      step and a "prioritize project goals over development convenience" rule.
- [x] **Web UI: version label, file-section swap, opt-in db-url, logo (P2)** —
      added `GET /api/v1/info` reporting the version label (derived from
      `__version__` via `_display_version`, e.g. `0.2.0`→`v0.02`, so a release
      needs no HTML edit) and a `db_connection_enabled` flag. The db-url option
      is gated by the `UNIQUE_ALLOW_DB_CONNECTION` env var (wired in
      Dockerfile/compose, documented in `06-installation.md`): both transpile
      endpoints reject `db_url` with 403 when disabled; when enabled the UI shows
      an optional "Database connection" field in both sections. Added a swap
      button to the file section, a red sans-serif "U" logo (`static/logo.svg`)
      used as the wordmark's capital, and tidied the file-row control alignment.
      Released as tag **v0.02** (image published by CI).

## 10. Reverse transpilation of non-type UNIQUE notes + set-based trigger rewrite (P2/P3)

Two follow-ups to the type-carrier round-trip and the trigger pseudo-table work.

- [x] **Restore documented source-only constructs on reverse transpilation.**
      Generalized the type-carrier round-trip to *non-type* constructs. A forward
      pass that drops a construct with no target equivalent (e.g.
      `SET IDENTITY_INSERT`, `SET ROWCOUNT`) now documents it as
      `/* UNIQUE: <orig> -- <source>-only, no <target> equivalent */`, recording
      the source engine. The parser captures `<orig>` + `<source>` onto
      `CommentStatement` (`restore_sql`/`restore_dialect`), and the transformer
      re-injects the original when the target is that source engine, else keeps
      the note so it survives onward transpilation to a third engine. Also:
      preserve body-level block comments in the PL/SQL parser (so the note
      reaches the AST), document the SET option from its *original* text before
      target fixups (dbo-stripping) corrupt it, and fix `SET IDENTITY_INSERT`
      capture to keep the schema-qualified table name (`dbo.t`, not `dbo`).
      Tests: `TestUniqueCommentRestore`.

- [x] **Rewrite a pure set-based trigger with PostgreSQL transition tables.**
      A *purely* set-based T-SQL trigger (body uses `inserted`/`deleted` only via
      `FROM`/`JOIN`, no row-level qualifier or `UPDATE(col)` predicate) is now
      rewritten to a PostgreSQL statement-level trigger: the function returns
      `NULL` and the trigger declares `REFERENCING NEW TABLE AS inserted OLD TABLE
      AS deleted` + `FOR EACH STATEMENT`, so the set-based body runs as-is. A
      *mixed* trigger (row-level and set-level together, like the fixture's
      `IF UPDATE(col) … FROM inserted`) cannot be a single trigger and stays
      documented. **Oracle and MySQL keep documenting** the set-based use:
      Oracle has no *named* transition tables (a compound trigger would need a
      manual PL/SQL collection — not a mechanical rewrite, and emitting
      `FROM inserted` would be invalid), and MySQL has none at all. Faithfulness
      won over a lossy rewrite. Adds `CreateTriggerStatement.set_based_transition`,
      the `_supports_transition_tables` hook (PostgreSQL only), and pure-vs-mixed
      detection over the whole trigger body (including the `IF` condition).
      Tests: `TestSetBasedTriggerRewrite`.

A design note on Oracle row-level → T-SQL set-based was also discussed: a
faithful general conversion would wrap the row-level body in a cursor over
`inserted` (RBAR, plus a PK-join problem for UPDATE), so a true set-based
rewrite is only safe for a detectable subset; the rest should stay documented.
Captured here for future reference rather than implemented.

## 11. Standalone-DML operator & function audit + packaging fix (P1/P2)

A real-world report (`'1234' + '5678'` staying `+` on Oracle) triggered a
systematic cross-engine audit of operators and functions in the standalone-DML
path (the procedural engine already handled these inside routine bodies; the gap
was DML-only). The round-trip technique (A→B→A') made no-op conversions visible.

- [x] **String concatenation.** T-SQL `+` is concatenation when an operand is a
      string, but sqlglot parses it as arithmetic `Add` and never re-maps it.
      Rewrite an `Add` to `DPipe` when an operand is recognizably a string
      (literal, varchar cast, string function — directly or transitively), so
      sqlglot emits `||` (Oracle/PostgreSQL) or `CONCAT` (MySQL). Purely numeric
      additions are untouched; ambiguous `col + col` without type info is left as
      `+` (documented). Tests: `test_operator_roundtrip.py`.
- [x] **Bitwise operators.** `& | ^ << >>` were silently coerced to `=` (a
      converter default mapped unknown operators to `EQ`, so `a & b` became
      `a = b`). Map them explicitly (PostgreSQL XOR is `#`) and **remove the
      dangerous default** — an unmapped operator is preserved verbatim, never
      turned into equality. Oracle has no infix bitwise operators, documented as
      a known limitation.
- [x] **Compound assignment.** `SET a += 1` was dropped by sqlglot to `SET = 1`
      (data loss, no warning). Expand `col <op>= expr` to `col = col <op> expr`
      before sqlglot, scoped to the UPDATE SET list so comparisons elsewhere are
      untouched. Composes with the concat and bitwise fixes.
- [x] **Function arguments.** sqlglot models specialized functions with their
      arguments in *named slots* (`Substring`→start/length, `Replace`→expression/
      replacement, `Round`→decimals, `Stuff`, `Replicate`, `DateAdd`→unit,
      `Power`/`Nullif`→expression, …), not in `expressions`. `_convert_function`
      read only `this` + `expressions`, dropping every named slot (`SUBSTRING(a,
      1,3)`→`SUBSTR(a)`). Collect scalar arguments in declaration order from
      `arg_types` (skipping boolean flags), keep variadics (COALESCE/CONCAT), and
      read an `Anonymous` function's real name from `.name` instead of emitting
      `ANONYMOUS`. Tests: `test_function_translation.py` (39 cases).
- [x] **Packaging: static SVG/PNG/ICO in the wheel.** The logo 404'd in the
      Docker image because the container installs from the wheel and
      `package-data` only declared `static/*.{html,css,js}`; add `*.svg`/`*.png`/
      `*.ico`, plus a test asserting the patterns are declared.

Documentation (`01-compatibility.md`, `03-unsupported.md`, `STATUS.md`,
`sqlglot-dependency.md`) updated to match. Released as **v0.05** (Docker image
published by CI). The remaining `IIF`→`CASE WHEN` and `DATEPART`→`EXTRACT(…
FROM …)` rewrites for standalone DML are noted as pending in `03-unsupported.md`.

## 12. Real-world output-validity hardening — audit doc 02, test_real_world.py (P1)

`test_real_world.py` had a 2% identity-mutation kill rate (audit doc 02): its
invariants (non-empty, CREATE TABLE counts, jaccard) were all maximized by a
no-op transpiler. The hardening added `TestOutputValidity` — per-statement
target-dialect parsing (procedural-aware: the FE-harness splitter +
`classify_batch` exempt routine bodies sqlglot cannot parse), a
foreign-quoting/separator gate (`[x]` / backticks / `GO` must not survive in
executable output), and per-fixture signature-idiom assertions. Building the
gates surfaced 10 emitter bugs producing invalid SQL on the four fixtures —
all fixed test-first:

- [x] **Degraded passthroughs commented only the first line** — the other ~30
      lines of a multi-line statement leaked as raw executable source SQL.
      `_comment_block()` now comments every line at all fallback sites.
      Similarity floors recalibrated (oracle 0.35 → 0.25): the leaked raw
      lines had inflated the old values.
- [x] **T-SQL `PRIMARY KEY/UNIQUE CLUSTERED (col ASC) WITH (...) ON [PRIMARY]`**
      re-emitted as bogus comma-separated items; physical hints now stripped
      before re-transpiling the constraint fragment.
- [x] **Procedural headers kept bracket quoting** (`CREATE FUNCTION
      [dbo].[fn](@p [tinyint]) RETURNS [nvarchar](15)`) — quoting now
      translated on routine name/schema/trigger table; bracketed type names
      unquoted before type-map lookup. Backtick tokenization added to the
      procedural lexer (sakila's `` CREATE TRIGGER `ins_film` `` shredded).
- [x] **Oracle `ORGANIZATION INDEX/HEAP`** degraded the whole CREATE TABLE;
      the physical clause is stripped pre-parse with carrier + warning.
- [x] **Oracle `ALTER TABLE ADD ( ... )`** re-emitted as `ADD COLUMNS (...)`
      (invalid everywhere); unwrapped to T-SQL's ADD comma-list / one ADD per
      item (PG/MySQL).
- [x] **MySQL unsigned/YEAR/TIMESTAMP types** leaked sqlglot internals
      (USMALLINT/UTINYINT/UMEDIUMINT) or invalid types; mapped per target.
- [x] **ENUM lost its value list silently**; values now ride the IR
      (`DataType.values`) — MySQL emits the native type, everyone else
      VARCHAR(max-len) + inline CHECK (SET: sized VARCHAR + carrier note).
- [x] **`UNIQUE idx (col)` / `DROP SCHEMA sakila.` / `_utf8' '`** — named
      inline keys become `CONSTRAINT idx UNIQUE (col)`; a Table with only the
      db part set no longer emits a dangling qualifier; charset introducers
      reduce to the plain literal.
- [x] **T-SQL alias types resolved** — `CREATE TYPE x FROM base` definitions
      are harvested from the script (contextvar around the run) and columns
      typed with the alias emit the base type (dbo.Name broke MySQL parsing).
- [x] **MySQL `IF()` / T-SQL `IIF()`** translate per target (IIF / IF /
      searched CASE); they used to leak verbatim (this also closes the
      pending `IIF`→`CASE WHEN` note from §11).

Result: 0 parse failures across all 12 fixture×target pairs (was 11/46 tsql,
29/57 oracle→tsql, 8/26 mysql→tsql); integration kill rate 28% → 36%
(`identity_mutation_check.py` floor raised to 33%).

## 13. Live Oracle functional equivalence via local Docker (P1)

The remote test stack's Oracle credentials were rejected, so every
Oracle-target and Oracle-source functional-equivalence pair had been skipped.
Running the local `docker-compose.test.yaml` stack instead (PostgreSQL 16 +
**real MySQL 8** + **Oracle Free 23**, `system/oracle` @ `FREEPDB1`) made them
live and moved the 4×4 matrix from **6 → 9 of 12 reachable pairs green** (all
Oracle-target pairs plus `tsql/postgresql → oracle`; the 4 T-SQL-target pairs
still skip — no local `pyodbc`). Real MySQL 8 (stricter than the old remote
MariaDB) also surfaced harness bugs. Everything below was TDD, gate-clean.

**Harness (`tests/helpers/live_validation.py`, `docker-compose.test.yaml`,
`tests/functional_equivalence/engine_runner.py`):**

- [x] **MySQL statement splitter glued the leading batch.** Everything before
      the first `DELIMITER` was flushed as one `execute()` (1064). Split the
      default-delimiter buffer on `;` at the DELIMITER switch, not just the tail.
- [x] **Oracle validator shredded PL/SQL bodies.** It split on `;`, breaking
      routine bodies and leaving stray `/` terminators (ORA-00900). Added a
      SQL\*Plus `/`-aware splitter that keeps a PL/SQL block whole (recognized
      past leading guard comments) and strips a trailing `;` only from plain SQL.
- [x] **MySQL non-isolated cleanup dropped only tables**, so a leftover
      procedure failed reruns (1304). Track and drop every created object
      (tables, routines, triggers, views) with FK checks off.
- [x] **MySQL 8 binary logging** blocks a non-SUPER user from creating
      routines/triggers (1419); the compose file now sets
      `--log-bin-trust-function-creators=1` for the throwaway test stack.
- [x] **FE engine-runner Oracle splitter** dropped the terminating `;` of the
      script's *last* PL/SQL block (no trailing `/`), so an anonymous
      `BEGIN … END;` reached the engine as `BEGIN … END` (PLS-00103). Keep a
      trailing PL/SQL block whole.

**Oracle emitter / converter (`converter.py`, `transpiler.py`, procedural
emitter/transformer):**

- [x] **`CREATE SEQUENCE … AS <type>`** dropped for Oracle (ORA-03048);
      PostgreSQL keeps its valid form.
- [x] **Multi-event triggers** joined with `OR` not comma for Oracle
      (`AFTER INSERT OR UPDATE`, ORA-00969) via an engine-specific hook; MySQL
      still splits into one trigger per event.
- [x] **ISO date/datetime handling for Oracle** (ORA-01861), keyed off
      harvested date columns / proc date-parameter positions: a bare string
      written to a date column, a string passed to a date proc-arg, and a
      source `CAST(str AS DATE)` / `DATE '…'` literal all emit the ANSI
      `DATE '…'` / `TIMESTAMP '…'` literal; other targets keep the ISO string.
- [x] **Constrained types in a PL/SQL `CAST` unconstrained** — `CAST(x AS
      NUMBER(12,2))` / `VARCHAR2(10)` drop the length and `DECIMAL`/`NUMERIC`
      become `NUMBER` (PLS-00103, PL/SQL only).
- [x] **Identity capture** — T-SQL `INSERT …; SET @id = SCOPE_IDENTITY()`
      peephole-merges into `INSERT … RETURNING <idcol> INTO <var>` (harvested
      identity columns; single-row VALUES inserts into a known table only).
      Also: sqlglot silently drops the `INTO <var>` of a `RETURNING … INTO`, so
      it is peeled before transpiling and re-appended natively for Oracle/PG
      (was ORA-00925).

**Trigger-body row references (both directions):**

- [x] **Oracle/PG event list `OR`** now parses (was leaving `OR UPDATE ON …`
      to leak into the body as garbage).
- [x] **Oracle-source `:NEW.`/`:OLD.`** normalized to the target row qualifier
      before sqlglot (was rendered as PG's `%(NEW)s` bind placeholder).
- [x] **MySQL/PG-source `NEW.`/`OLD.` → Oracle `:NEW.`/`:OLD.`** in the
      assignment target, its value, and an embedded `UPDATE` (PLS-00201); a
      negative lookbehind leaves an already `:`-prefixed reference untouched.

**Making the oracle-source pairs run end-to-end (still red on trigger values):**

- [x] **MySQL 2-arg `DATEDIFF(end, start)` in a routine body** → `(end - start)`
      (Oracle), `(end::date - start::date)` (PG), `DATEDIFF(DAY, start, end)`
      (T-SQL). The 3-arg T-SQL form was already handled; the MySQL form leaked
      verbatim (PLS-00201 / unknown function) in a function body.
- [x] **Oracle COMPOUND TRIGGER degrades to a documented carrier** instead of
      being shredded into garbage DECLAREs (`TYPE id_tab;`, `PLS_INTEGER ;;`)
      that crashed PostgreSQL (`variable "compound" has pseudo-type trigger`).
      The parser detects `COMPOUND`, consumes the definition, and the emitter
      writes a `-- UNIQUE:` note + warning.
- [x] **sqlglot `DATE_STR_TO_DATE` wrapper unwrapped** — an Oracle `DATE '…'`
      literal transpiled to PG as the internal `DATE_STR_TO_DATE('…')`
      (UndefinedFunction); added to the wrapper-unwrap set.
- [x] **Oracle bare `name(args);` proc call parsed as a CallStatement** (was
      EmbeddedDML → sqlglot mangled it to a bare `NAME(args)`, a syntax error on
      PG/MySQL). A statement-position call is unambiguously a procedure call.

Result: the transpiled Oracle schema+scenario now runs end-to-end on
PostgreSQL/MySQL. Row-level trigger translation is correct both directions; the
3 still-red pairs (`oracle→pg`, `oracle→mysql`, `mysql→oracle`) reduce to one
feature — the aggregating trigger across the statement-level / compound /
mutating-table boundary. `oracle→postgresql` now diverges *only* on the values
those compound triggers would maintain (`invoice.total`, `is_paid`), confirming
everything else is correct (see TODO §1).
