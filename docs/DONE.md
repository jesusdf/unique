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
published by CI). (The `IIF`→`CASE WHEN` and `DATEPART`→`EXTRACT(… FROM …)`
rewrites for standalone DML noted here as pending were later completed — see the
date-format/EXTRACT entry below.)

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

## 14. Aggregation-trigger translation — all 12 reachable FE pairs green (P1)

The last 3 red functional-equivalence pairs all reduced to one feature: an
*aggregation* trigger (re-aggregate a parent row when child rows change) crossing
the statement-level / compound / mutating-table boundary. The mutating-table
restriction is **Oracle-specific** — PostgreSQL and MySQL let a row-level trigger
re-read the table it fires on — which set the translation strategy. All TDD,
gate-clean; the local `docker-compose.test.yaml` matrix is now **12/12 reachable
pairs green** (the 4 T-SQL-*target* pairs still skip — no `pyodbc`).

**`oracle→postgresql` — lower the COMPOUND trigger to a PG row-level trigger.**
An Oracle COMPOUND TRIGGER exists only to dodge ORA-04091; PostgreSQL doesn't
need it. The parser recognizes the "collect `:NEW.<fk>` in AFTER EACH ROW,
re-aggregate in an AFTER STATEMENT `FOR v IN 1 .. n LOOP`" idiom and stores the
loop's statement(s) — with the collection re-read `coll(v)` rewritten to the
collected `:NEW.<fk>` — in `CreateTriggerStatement.compound_row_body`. For the
PostgreSQL target the transformer lowers it to a plain row-level AFTER trigger
(the existing PG emitter renders the trigger function + binding; the embedded-DML
pipeline maps `:NEW.`→`NEW.` and `NVL`→`COALESCE`). Oracle (shares the
restriction) and MySQL (documented) keep the `-- UNIQUE:` carrier; an unmatched
body falls back to the carrier.

**`mysql→oracle` — synthesize a COMPOUND trigger from a row-level re-read.** The
inverse: a MySQL row-level AFTER trigger whose body reads its own triggering
table hits ORA-04091 as a plain Oracle row-level trigger. The Oracle emitter
detects the hazard (a row-level AFTER trigger reading/writing its own table in a
FROM/JOIN/UPDATE/INTO position) and emits a COMPOUND TRIGGER: a PLS_INTEGER-
indexed collection per distinct `:NEW.`/`:OLD.` key (typed via
`<table>.<col>%TYPE`, so no catalog is needed), filled in AFTER EACH ROW, and the
body re-keyed to the collection in a `FOR` loop in AFTER STATEMENT.

**`oracle→mysql` — documented divergence (the agreed MySQL story).** MySQL can
express the aggregation as a row-level re-read, but per the design decision the
compound body stays a `-- UNIQUE:` carrier and its maintained values
(`invoice.total`, `is_paid`) are excluded from the assertion via the harness's
new explicit `_DOCUMENTED_TRIGGER_DIVERGENCE` set (replacing the ad-hoc
`source in (tsql, postgresql) and target in (mysql, oracle)` guard).

**Two bugs surfaced en route (both were latent — the pairs errored before these
code paths ran):**

- [x] **Oracle row-level `:NEW.col := expr` → MySQL `SET NEW.col = expr`.** The
      lexer emits `:` as a bare COLON, so the assignment fell to embedded DML and
      only `:NEW.`→`NEW.` was regex-normalized, leaving Oracle's `:=` — a syntax
      error on MySQL (PostgreSQL tolerated it). The PL/SQL dispatcher now parses a
      `:NEW.`/`:OLD.`-led `:=` statement as an AssignmentStatement, and a raw-SQL
      assignment value normalizes `:NEW.`/`:OLD.` like embedded DML does.
- [x] **Bare Oracle `DECIMAL`/`NUMERIC`/`DEC` → `NUMBER` in parameter/RETURN
      position.** Unconstraining a formal type (PLS-00103) stripped `DECIMAL(12,2)`
      to a bare `DECIMAL`, which is `NUMBER(38,0)` and silently rounds to an
      integer — so a transpiled `fn_tax` returned 6 instead of 5.55 and the
      aggregated total came back 61.50 instead of 61.05. `_unconstrained` now maps
      the bare numeric names to `NUMBER` (keeps the value's own scale).

## 15. Reaching SQL Server root-free (pymssql) + first T-SQL-target fixes (P1)

The 4 T-SQL-*target* functional-equivalence pairs had always skipped: the MS ODBC
driver needs root to install, and pyodbc is useless without it. **pymssql**
bundles FreeTDS in its wheel and connects with no system driver, so the harness
`connect()` now parses a `mssql://user:pass@host:port/db` URL and uses pymssql,
still preferring pyodbc for an ODBC connection string (CI). Added the
`mssql-freetds` optional-dependency. `tsql→tsql` is now live-green.

Running the T-SQL-target pairs for the first time surfaced long-latent emitter
bugs (all TDD, `test_converter.py::TestTSQLTypePortability`):

- [x] **Source `TIMESTAMP` → T-SQL `DATETIME2`.** T-SQL `TIMESTAMP` is
      `ROWVERSION` (an auto binary value), not a wall clock, and rejects a
      `DEFAULT` (error 1755).
- [x] **Integer display width dropped for T-SQL** (`TINYINT(1)`, error 2716) —
      the existing PostgreSQL width-strip now also covers T-SQL, plus `TINYINT`.
- [x] **No `SET NOCOUNT` inside a T-SQL function** (error 443, a side-effecting
      SET option) — the T-SQL emitter gains a function-specific body without the
      procedure preamble; procedures keep it.
- [x] **T-SQL parameters always carry `@`** — the emitter guarantees the sigil
      regardless of source.

Still **not green** (tracked in TODO §1): the 3 cross→tsql pairs need date
subtraction → `DATEDIFF`, MySQL-source `@` var sigils in routine bodies, and —
the substantial one — trigger translation *to* T-SQL (statement-level
`inserted`/`deleted` synthesized from PG trigger-function / Oracle COMPOUND /
MySQL row-level sources).

## 16. Full 4×4 matrix green — trigger translation *to* T-SQL (P1)

The last 4 pairs (T-SQL as target) went green, so **all 16 source×target
functional-equivalence pairs converge on the same `expected_state.yaml`,
live** (SQL Server 2022 via pymssql + PostgreSQL 16 + MySQL 8 + Oracle Free 23).
All TDD, gate-clean.

**T-SQL DDL/routine fixes (surfaced pair by pair):** date subtraction `d2 - d1`
→ `DATEDIFF(DAY, d1, d2)` (a `_date_vars` registry mirrors `_string_vars`);
MySQL-source routine bodies gain the `@` sigil on local/param references (not
just the declaration); `CREATE OR REPLACE VIEW` → `CREATE OR ALTER VIEW`;
`RETURNING … INTO @v` → `SET @v = SCOPE_IDENTITY()` (T-SQL `OUTPUT … INTO` needs
a *table* variable); an ANSI `DATE '…'` EXEC argument → the bare string; and a
bare `DECIMAL`/`NUMERIC` routine param/return (an unconstrained source `NUMBER`)
is `(18,0)` on T-SQL and rounds to an integer, so it gets a wide exact scale
(fn_tax 5.55 stays 5.55, total 61.05 not 61.50).

**Trigger translation to T-SQL** (T-SQL triggers are statement-level over
`inserted`/`deleted`, with no per-row NEW/OLD):

- **MySQL / Oracle row-level source** — a `SET NEW.col = expr` (incl. Oracle's
  `:NEW.col :=`) becomes `UPDATE <tbl> SET col = <expr> WHERE <pk> IN (SELECT
  <pk> FROM inserted)` (PK from the identity registry, now harvested for the
  T-SQL target); an embedded `UPDATE <tgt> <alias> SET … WHERE <alias>.<key> =
  NEW.<fk>` becomes a set-based update scoped to `inserted` (target alias
  dropped — T-SQL forbids it — the inner `NEW.<fk>` correlated to `<tgt>.<key>`,
  the outer equality → `<tgt>.<key> IN (SELECT <fk> FROM inserted)`). An Oracle
  COMPOUND trigger reuses its captured `compound_row_body`.
- **PostgreSQL source** — a trigger delegating to a `RETURNS TRIGGER` function is
  merged: the function text is harvested by name (`PG_TRIGGER_FN_BODIES`), its
  body inlined into `CREATE TRIGGER … AS BEGIN … END` with the
  `pg_trigger_depth()` guard (T-SQL: RECURSIVE_TRIGGERS OFF) and `RETURN`
  dropped; the standalone function is dropped as a one-line note.
- A scalar-UDF call in any of these is qualified `dbo.<fn>` (harvested
  `CREATE FUNCTION` names) — T-SQL rejects an unqualified scalar UDF.

**Harness:** SQL Server is reachable **root-free via pymssql** (its wheel bundles
FreeTDS); `connect()` uses it for a `mssql://…` URL and pyodbc for an ODBC
connection string. Remaining: wire a SQL Server driver into CI and drop the
`syntax-live` `continue-on-error` to make the 4×4 gating (TODO §1).

## 17. Large-script performance + T-SQL migration-idiom coverage (P1/P2)

Driven by running two real dumps through the tool (a 13k-line T-SQL migration
script and a 216k-line / 13 MB Oracle dump).

**Performance — two O(n²) hot paths removed (421 s → ~30 s on the 13 MB file,
now linear ~0.14 ms/line):**
- `Transpiler._join_parts` accumulated the whole multi-MB output with
  ``out += piece`` (O(output²)); rebuilt as a list + one `"".join()`.
- The carrier↔warning reconciliation re-scanned every accumulated warning for
  every carrier of every batch (O(carriers × warnings), shingle sets); dedupe
  carrier fragments globally so each unique fragment is reconciled once.
- COMMIT / ROLLBACK / TRUNCATE now pass through (PassthroughSQL) instead of a
  per-statement Command carrier — a dump has thousands.
- A mandatory rule was added to `SKILL-development-workflow.md`: never build a
  string with `+=` in an input-proportional loop.

**T-SQL migration idioms (SSMA output) — `-- UNIQUE:` carriers on the sample
script cut 969 → ~190 (~80%):**
- `IF [NOT] EXISTS (<catalog query>) [BEGIN] <stmt> [END] [ELSE PRINT …]` guards:
  the catalog condition has no cross-engine form, so keep the intent — transpile
  the guarded statement (idempotent `DROP … IF EXISTS` for a guarded DROP).
  Balanced-parens condition skipped, single `BEGIN…END` unwrapped, a leading
  diagnostic `PRINT`/`SET` and the whole `ELSE` branch dropped.
- `ALTER TABLE t ADD [CONSTRAINT n] DEFAULT v FOR c` → `ALTER COLUMN c SET
  DEFAULT v` (Oracle `MODIFY c DEFAULT v`); validate the output and fall back to
  a restorable note when the value has no clean target form (e.g. `NEWID()`).
- `ALTER TABLE t [WITH [NO]CHECK] {CHECK|NOCHECK} CONSTRAINT c` → Oracle
  ENABLE/DISABLE, PostgreSQL VALIDATE (CHECK); a restorable note otherwise.
  Handles `[bracketed]` schema/constraint names (SSMA embeds `$`).

**Restorable physical index clauses (completing the %TYPE precedent):**
CLUSTERED/NONCLUSTERED, `WITH (options)` and `ON <filegroup>` were dropped
*silently* from a CREATE INDEX; now preserved in a restorable
``/* UNIQUE: … -- tsql-only … (physical index clause) */`` note, and **restored**
when transpiling back to T-SQL (CLUSTERED re-inserted after `CREATE [UNIQUE]`,
WITH/ON re-appended). `CREATE CLUSTERED INDEX` survives tsql→pg→tsql intact.

**Web:** upload cap raised 2 MB → 64 MB (`UNIQUE_MAX_SQL_BYTES`).

## 18. Archived TODO checklists — FE harness + audit remediation (P1)

Moved from `docs/TODO.md` on 2026-07-05 once every item was complete; kept here as the granular task record behind the narrative sections above.

## 1. Functional-equivalence test database (P1)

**Goal:** move from *syntactic* validation (the `syntax-live` job confirms a
transpiled script *compiles* on the target engine) to *functional* equivalence
— confirm a migrated script **behaves identically**: same final table state
after running DDL + seed data + mutations (direct DML, updates on a
triggered table, inserts/updates from a stored procedure, …).

Design, schema, scenario and expected-state spec live in their own folder:
**[`tests/functional_equivalence/`](../tests/functional_equivalence/)** — see its
`README.md` for the full architecture and rationale. Build it *after* the items
below are closed.

High-level plan (details in that folder):

- [x] **Coverage matrix** — enumerate the behaviors to *guarantee* functionally
      (data types, object types, trigger/proc/function/view semantics), proving
      the schema is minimal yet complete. Done: `tests/functional_equivalence/
      coverage-matrix.md` locked for Phase 1 — every type/object mapped to a
      scenario step and to an `expected_state.yaml` assertion, with a minimality
      argument and a per-value determinism checklist. Resolved the draft gaps:
      `fn_tax` now exercised via a tax-on-invoice path, `is_paid` set by an
      explicit payment-path UPDATE, `created_at` is presence-asserted only.
- [x] **Minimal schema** — a small invoicing-style domain (customer, product,
      invoice, invoice_line, payment) that exercises every covered construct;
      canonical DDL + a UML/Mermaid diagram. Design locked in `schema.mmd`;
      canonical T-SQL DDL authored in `schema/tsql.sql` (Scenario A + B:
      5 tables with PK/FK/UNIQUE/CHECK/DEFAULT and pinned identity, a sequence,
      `fn_tax`/`fn_days_between`, `v_invoice_totals`/`v_overdue_invoices`, and
      the `trg_line_total`/`trg_invoice_touch`/`trg_payment_paid` triggers).
      Transpiles to all three targets with exit 0; output spot-checked.
      Discovered + fixed while validating: a FOREIGN KEY that `REFERENCES` a
      `dbo`-qualified table kept the `dbo.` on Oracle/MySQL/PostgreSQL (a real
      transpiler bug; the schema of the *created* table was already stripped but
      the reference target was not). Fixed in `converter.py` with a failing test
      first (`test_foreign_key_reference_strips_dbo_schema`).
- [x] **dbo. leak on views / sequences / object bodies** (discovered while
      validating the canonical schema; now fixed). The `dbo` default schema is
      meaningful only in T-SQL, so it is dropped for the three other engines.
      Centralized the strip in `_emit_table_ref` (a new optional `dialect`
      argument), which covers the view name, tables in a view/SELECT body, and
      INSERT/UPDATE/DELETE/JOIN targets; the prior ad-hoc strip in
      `_emit_create_table` now reuses it. A general `_strip_dbo_schema_qualifier`
      cleans sqlglot passthrough output (CREATE SEQUENCE / INDEX / ALTER) and the
      MySQL "no sequences" degradation comment. Failing tests first
      (`test_create_view_strips_dbo_schema`, `test_create_sequence_strips_dbo_schema`).
      Verified end-to-end: the canonical schema transpiles to all three engines
      with **0 executable `dbo.`** (remaining occurrences are inside harmless
      degraded-guard comments).
- [x] **Standalone `UPDATE … FROM … JOIN` fixed** (found while validating the
      canonical trigger bodies). The transpiler used to drop the source table
      and join predicate entirely, emitting a bare `UPDATE t SET c = s.c`
      (wrong: undefined alias, updates every row). `_convert_update` now lifts
      `FROM`/`JOIN` into the IR and `_emit_update` renders each engine's
      idiomatic cross-table form (PostgreSQL `FROM … WHERE`, MySQL `JOIN … SET`,
      Oracle correlated subquery + `EXISTS`, T-SQL native `FROM`/`JOIN`). Also
      fixed a long-standing bug where a join alias was emitted twice (`t2 b b`).
      Tests first (`test_update_from_join_*`, `test_select_join_with_alias_not_duplicated`).
- [x] **Set-based trigger bodies now functional on PostgreSQL.** The procedural
      engine (a separate parser/transformer/emitter from the standalone-DML
      path) used to delegate embedded DML straight to sqlglot, which mishandles
      `UPDATE … FROM … JOIN`, leaving the set-based trigger UPDATEs invalid or
      degraded. `_transform_embedded_dml` now routes a cross-table embedded
      UPDATE through the IR converter/emitter, so PostgreSQL emits a valid
      `UPDATE … FROM inserted WHERE …` inside the `FOR EACH STATEMENT` trigger
      function (with `REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted`).
      All three canonical triggers (`trg_line_total`, `trg_invoice_touch`,
      `trg_payment_paid`) now transpile to **functional** PostgreSQL: 0 degraded
      bodies, 0 executable `dbo.`, 0 empty `FROM`. Along the way, fixed three
      general bugs (TDD): a top-level `AND`/`OR` in a WHERE emitted as a function
      call `AND(a,b)` (`exp.And` is also `exp.Func`, so Binary is now checked
      before Func); a schema-qualified user-function call `dbo.fn_tax(...)`
      (parsed as an `exp.Dot`) kept `dbo.` and is now folded into a
      FunctionCall whose qualifier is stripped per engine; and an empty `FROM`
      when a join targeted a subquery (now falls back to the documented path).
      Canonical trigger bodies were also rewritten to use correlated subqueries
      (not JOIN-against-aggregate) — the faithfully-transpilable pattern.
      MySQL/Oracle still document the set-based form (no named transition
      tables); that is a real limitation, not a bug — see next item.
- [x] **MySQL/Oracle set-based triggers remain documented (by design).** Neither
      has T-SQL's named `inserted`/`deleted` transition tables, so a set-based
      trigger can't be mechanically rewritten to a single faithful trigger
      (Oracle would need a compound trigger accumulating rows into a PL/SQL
      collection; MySQL has no transition tables at all). Both emit a `-- UNIQUE:`
      note today. Revisit only if a faithful automatic rewrite proves feasible;
      otherwise this stays a documented divergence, and the functional-
      equivalence harness should assert trigger-maintained values on PostgreSQL
      (+ T-SQL) and treat MySQL/Oracle trigger effects as out of scope.
- [x] **Deterministic scenario authored** (`scenario/tsql.sql`) — the five
      locked steps in T-SQL: seed (2 customers, one with notes one NULL; 2
      products), direct INSERT invoice 1 + 2 lines, UPDATE a line on the
      triggered table (Widget qty 2→3), `create_invoice` proc call for invoice 2,
      and a payment that marks it paid. All literals fixed (dates, `CAST(… AS
      DECIMAL(p,s))`), 10% tax exact at scale 2. Also added the missing
      `create_invoice` stored procedure to `schema/tsql.sql`. Schema +
      scenario transpile to all three targets with exit 0; PostgreSQL output
      spot-checked (proc body, INSERTs, triggered UPDATE all valid).
- [x] **`EXEC proc` / batch `DECLARE` now route to the procedural engine.** The
      batch classifier only treated `CREATE/ALTER PROCEDURE/FUNCTION/TRIGGER` as
      procedural, so a standalone `EXEC dbo.create_invoice …` or `DECLARE @x …`
      fell to the sqlglot path and degraded to `-- UNIQUE: Unhandled … Declare/
      Execute`. Added T-SQL classifier patterns for `EXEC/EXECUTE <user proc>`
      (system `sp_*`, incl. schema-qualified `sys.sp_*`, still excluded so the
      DML pipeline documents them) and batch-level `DECLARE @…`. TDD:
      test_exec_proc_is_procedural / _execute_keyword_ / _batch_declare_ /
      _exec_system_proc_not_procedural. Full suite green (1149).
- [x] **Standalone `EXEC proc` now emits `CALL` per engine.** A top-level
      anonymous block parses to a new `AnonymousBlock` IR node (the top-level
      parser routes a bare `EXEC`/`DECLARE` batch through the statement parser
      instead of returning one verbatim `RawSQL`). `EXEC [dbo.]proc args` →
      `CALL proc(args)` on PostgreSQL/MySQL and `proc(args);` on Oracle, with the
      `dbo` schema stripped, the trailing `OUTPUT` keyword dropped, and the
      qualified-name regex fixed in all three EXEC emitters (previously
      `CALL dbo(. proc …)`). Oracle wraps the call in a `BEGIN … END;` PL/SQL
      block (a bare call isn't runnable standalone). Scenario step 4 rewritten to
      a positional call (the new id is invoice 2, used directly), and the unused
      `@new_id OUTPUT` removed from `create_invoice`. Result: the full
      schema+scenario transpile to PostgreSQL with **0 degraded steps / 0 UNIQUE
      comments**. TDD: `TestStandaloneExec` (3 engines).
- [x] **Batch `DECLARE @x … @x OUTPUT` capture.** A block that captures a
      procedure's OUT parameter into a batch-local variable now emits the
      target's OUT/INOUT call form: PostgreSQL `DO $$ DECLARE v_x …; BEGIN CALL
      p(… => v_x); … END $$`, Oracle `DECLARE v_x …; BEGIN p(… => v_x); … END;`
      (the batch variable carries through to later statements, `OUTPUT` dropped).
      MySQL degrades by design — it has no top-level anonymous block. Verified
      2026-07-05 (TODO reassessed): the anonymous-block + named-arg handling
      already covers it. TDD: `TestExecOutputCapture` (PostgreSQL, Oracle).
- [x] **Engine-agnostic expected-state spec** (`expected_state.yaml`) — per-table
      row counts and specific `pk → column` values, defined once. Done: locked
      for Phase 1, all values reconciled (invoice.total = net + 10% tax, every
      taxed value exact at scale 2) and cross-checked against the matrix.
- [x] **Harness built** — `state_check.py` (load `expected_state.yaml`, per-engine
      value normalization: bool/int/decimal-scale/str-trim/date/NULL, and table
      comparison) and `engine_runner.py` (statement splitter for GO / `;` /
      Oracle `/`, keeping `$$…$$` and `BEGIN…END` bodies intact; lazy DB-API
      connect per engine; run script + read tables). The live test
      `test_functional_equivalence_live.py` transpiles schema+scenario per target,
      runs them, and asserts the expected state; it **skips** unless the matching
      `UNIQUE_TEST_*_URL` env var is set (same pattern as `test_live_syntax.py`).
      The pure mechanics are CI-covered with no external DB: `test_state_check.py`
      (17 cases) and `test_engine_runner.py` (splitter + an end-to-end read+compare
      smoke test on SQLite). Added Oracle to `docker-compose.test.yaml` and a
      runbook (`HARNESS.md`).
- [x] **Live run + final adjustments** (2026-07-03, against real PostgreSQL 16
      and MariaDB 11). The first live run surfaced and fixed, test-first:
      PostgreSQL transition-table rules (single event per trigger, NEW/OLD
      TABLE availability per event → the pg emitter and native fixture now
      split multi-event set-based triggers, with a `pg_trigger_depth()` guard
      emulating T-SQL's RECURSIVE_TRIGGERS OFF — unguarded, the rollup
      trigger recursed to the stack limit); `BIT DEFAULT 1`/0-1 literals into
      BOOLEAN columns (harvested BIT-column registry + emit-time coercion,
      incl. embedded procedure DML); T-SQL `IF OBJECT_ID ... IS NOT NULL
      DROP` guards now map to `DROP ... IF EXISTS`/pg_trigger DO-block/Oracle
      tolerant block (transpiled schemas are re-runnable); MySQL one event
      per trigger (split, and multi-routine DELIMITER wrapping); MariaDB's
      no-IGNORE_SPACE rejection of `CAST (` (built-in call spacing collapsed);
      MySQL integer display widths dropped for PostgreSQL; missing DROP VIEW
      guards in the MySQL fixture. Trigger-maintained values
      (`trigger_maintained` in expected_state.yaml) are excluded on targets
      where the source's set-based triggers are documented divergences
      (tsql→mysql/oracle), per the design note below. **Live-green pairs:**
      tsql→postgresql, tsql→mysql, postgresql→postgresql, mysql→mysql.
      MSSQL/Oracle identity pairs need pyodbc / valid Oracle credentials.
- [x] **CI job for the live harness** — the `syntax-live` workflow job runs
      `test_functional_equivalence_live.py` against the same four engines it
      already starts (MSSQL/Oracle/MySQL/PostgreSQL), right after the live syntax
      validation, surfacing any divergence as a `::error::` annotation + step
      summary. Confirmed green against the real engines, so it is now **gating**
      (the `continue-on-error` guard was removed) for the tagged Docker publish.
- [x] **Phase 2: full 4×4 matrix — all 16 source×target pairs converge on the
      same `expected_state.yaml`, live-green** (local `docker-compose.test.yaml`:
      SQL Server 2022 via pymssql + PostgreSQL 16 + MySQL 8 + Oracle Free 23). See
      DONE §14–16.
  - [x] **Native fixtures written** — `schema/{postgresql,mysql,oracle}.sql` and
        `scenario/{postgresql,mysql,oracle}.sql`, each idiomatic to its engine
        (PostgreSQL `GENERATED … IDENTITY` + statement-level transition-table
        triggers; MySQL `AUTO_INCREMENT` + `TINYINT(1)` + row-level `FOR EACH ROW`
        triggers with `DELIMITER //` routine bodies; Oracle `GENERATED … IDENTITY`
        + `NUMBER(1)` booleans + **compound triggers** to dodge the mutating-table
        error). All parse cleanly as their own source dialect (exercising each
        parser) and share the canonical arithmetic (totals 61.05 / 39.05). The
        T-SQL native fixture is `*/tsql.sql`.
  - [x] **Harness splitter hardened for the native fixtures** — `split_statements`
        now ignores `--` and `/* */` comments (an apostrophe or BEGIN/END inside
        a comment no longer desyncs it) and honors MySQL `DELIMITER //` directives
        (routine bodies kept intact, directives dropped). TDD in
        `test_engine_runner.py`.
  - [x] **16-pair harness wired** — `test_functional_equivalence_live.py` now
        parametrizes all 16 (source, target) pairs. Only the four native fixtures
        are committed; for source != target the harness transpiles the source's
        native schema+scenario to the target **on the fly** (nothing transpiled
        is stored). Each pair skips unless the target's `UNIQUE_TEST_*_URL` is
        set. Collection verified (16 pairs, all skip cleanly without DB URLs; all
        16 on-the-fly transpilations produce non-empty SQL). The CI `syntax-live`
        job runs it; kept `continue-on-error` until the 12 cross-dialect pairs are
        confirmed green on real engines (the T-SQL->{PG,MySQL,Oracle} column was
        already green). Renamed `canonical.sql` -> `tsql.sql` so the four fixtures
        are symmetric.
  - [x] **All 12 reachable cross-dialect pairs are live-green** (local
        `docker-compose.test.yaml`: PostgreSQL 16 + MySQL 8 + Oracle Free 23,
        `system/oracle` @ `FREEPDB1`). The last 3 red pairs went green with the
        aggregation-trigger translation (**DONE §14**):
        - `oracle→postgresql` — the Oracle COMPOUND trigger is lowered to a plain
          PostgreSQL row-level AFTER trigger (PG has no mutating-table rule).
        - `mysql→oracle` — a MySQL row-level re-read is synthesized into an Oracle
          COMPOUND trigger (collection filled in AFTER EACH ROW, re-aggregated in
          AFTER STATEMENT), dodging ORA-04091.
        - `oracle→mysql` — the aggregation is a **documented divergence** (per the
          agreed MySQL story): the compound body degrades to a `-- UNIQUE:`
          carrier and its maintained values are excluded via
          `_DOCUMENTED_TRIGGER_DIVERGENCE`; the rest of the script runs and the
          state matches.
        Also fixed en route: an Oracle row-level `:NEW.col := expr` now lowers to
        `SET NEW.col = expr` on MySQL; a bare Oracle `DECIMAL`/`NUMERIC`/`DEC`
        parameter/RETURN type (NUMBER(38,0), rounds to integer) now becomes
        `NUMBER`.
  - [x] **The 4 T-SQL-*target* pairs are green** (DONE §15–16). The harness reaches
        SQL Server via **pymssql** (no MS ODBC driver / root needed); a wave of
        latent T-SQL emitter bugs was fixed (TIMESTAMP→DATETIME2, integer display
        width, no `SET NOCOUNT` in a function, `@` sigils, date-subtraction →
        DATEDIFF, `CREATE OR ALTER VIEW`, `RETURNING…INTO` → `SCOPE_IDENTITY`,
        `dbo.`-qualified UDF calls, ANSI `DATE '…'` EXEC args, bare-numeric scale);
        and **trigger translation *to* T-SQL** — a statement-level
        `inserted`/`deleted` trigger synthesized from a MySQL row-level, an Oracle
        row-level/COMPOUND, and a PostgreSQL trigger-function source.
  - [x] **CI 4×4 is gating** — the `syntax-live` job installs `pymssql` (so the
        FE harness reaches SQL Server without the flaky msodbcsql18 apt install)
        and the functional-equivalence step dropped its `continue-on-error`. The
        harness `connect()` is driver-flexible (pymssql↔pyodbc, pymysql↔mysql-
        connector), so it runs under either the local or the CI driver set;
        verified locally by running the full matrix with `pymysql` blocked.

Key design risks, captured for when we start:
- **Determinism** is the central challenge — see the folder README for the list
  of engine-defined behaviors to design around.
- **Cross-engine value normalization** for the assertions (BIT vs BOOLEAN,
  NUMBER vs INT, DECIMAL scale, CHAR padding, CLOB/NCLOB, NULL) is the bulk of
  harness work and where subtle false results hide.
- **Scope to the faithfully-transpilable subset**; lossy constructs stay covered
  by the existing syntactic + `-- UNIQUE:` comment tests.

## 2. Audit 2026-07-02 remediation (P1)

Findings, evidence and reproductions live in **[`audit/2026-07-02/`](../audit/2026-07-02/)**.
Work the items in this order; each fix requires a test that fails under the
identity mutant (see `skills/SKILL-development-workflow.md` → *Test assertion
quality*).

**P1 — silent loss / invalid SQL (audit doc 01):**

- [x] Enforce the no-silent-loss invariant: every unmapped construct populates
      `result.warnings`/`result.unsupported`; add the carrier↔warnings
      consistency test. (S1-3 mechanism, cross-cutting)
- [x] Translate identifier quoting between engines instead of stripping it
      (`` ` `` ↔ `"` ↔ `[]`). (S1-1)
- [x] Oracle `(+)` outer joins → proper `LEFT/RIGHT OUTER JOIN ... ON`, or
      registered unsupported — never INNER JOIN without ON. (S1-2)
- [x] MERGE → MySQL: implement the simple-case `INSERT ... ON DUPLICATE KEY
      UPDATE` rewrite the docs promise, or mark unsupported with warning. (S1-3)
- [x] `DATEADD` → MySQL `DATE_ADD(ts, INTERVAL n unit)`. (S1-4)
- [x] `ROWNUM` → `LIMIT`/`FETCH FIRST` for non-Oracle targets. (S1-5)
- [x] Drop `FROM dual` for PG/T-SQL targets. (S1-6)
- [x] `ILIKE` rewrite per target. (S1-7)
- [x] `GROUP_CONCAT` ↔ `STRING_AGG` both directions, with `SEPARATOR`
      semantics fixed for the MySQL target. (S1-8, S2-1)
- [x] Boolean literals `TRUE/FALSE` → `1/0` for T-SQL (expressions and
      DDL defaults). (S1-9)
- [x] PG DDL defaults: `CURRENT_TIMESTAMP` without parens. (S1-10)
- [x] Oracle emitter: unconstrained formal-parameter types (strip
      length/precision in parameter position). (S1-11)
- [x] Preserve `THROW`/`RAISERROR` message text on all targets. (S2-2)
- [x] T-SQL assignment-select → Oracle: handle `NO_DATA_FOUND` divergence
      (nested block + empty handler). (S2-3)
- [x] FE-harness scenario for S2-3: step 6 (`flag_payment_status`) reads
      `payment` with an assignment-select that matches no row for invoice 1
      and writes `customer.notes` ('no payment'/'paid'), asserted in
      `expected_state.yaml`; native counterparts use `MAX()` so only the
      T-SQL source exercises the transform. Verified live on PostgreSQL and
      MariaDB (Oracle blocked on server credentials; the wrapper itself is
      unit-covered in `test_no_data_found.py`). Building it also fixed the
      assignment-select `dbo.` strip for PG/MySQL targets.

**P1 — test hardening (audit doc 02):**

- [x] Rewrite `test_cross_dialect.py` / `test_function_translation.py`
      assertions to the "target idiom present, source idiom absent" pattern.
- [x] Harden `test_real_world.py` with procedural-aware validity gates
      (`TestOutputValidity`): every non-procedural transpiled statement of the
      four fixtures parses in the target dialect (FE-harness splitter +
      `classify_batch` to exempt routine bodies), no bracket/backtick/GO
      leaks into executable output, and each fixture's signature construct
      is asserted in the target idiom. Building it surfaced and fixed 10
      emitter bugs (see DONE.md: audit doc 02 hardening); integration
      kill rate 28% → 36%, gate floor raised to 33%.
- [x] Shared helper: parse every transpiled output with sqlglot in the target
      dialect (`ErrorLevel.RAISE`).
- [x] Add the identity-mutation check as a CI job with a kill-rate threshold.
- [x] Extend live-syntax CI coverage to standalone DML/DDL probes — added 10
      snippets exercising the audit S1/S2 constructs (CURRENT_TIMESTAMP / boolean
      / CHECK DDL defaults, Oracle `(+)` outer join, ROWNUM, ILIKE, GROUP_CONCAT
      ↔ STRING_AGG ↔ LISTAGG, DATEADD, reserved-word identifier quoting), each
      transpiled and executed on every configured engine. Fixed a validator
      cleanup gap surfaced by the reserved-word probe: `_objects_created` now
      keeps a quoted name so Oracle emits `DROP TABLE "order"` (auto-committed
      DDL was leaking, ORA-00955 on rerun).

**P2 — structure & ops (audit docs 03–04):**

- [x] Consolidate function/type/literal mappings into one module consumed by
      both pipelines (`core/mappings.py`): the DML emit-side type map, the
      procedural per-pair type/function maps, the canonical function renames,
      and the current-timestamp/UUID spellings all live there now, with
      `tests/unit/core/test_mappings.py` iterating them in both directions
      (rename round-trips, no chained entries, cross-pipeline agreement with
      an explicit documented-divergence list). The very first run of that
      test surfaced and fixed two real asymmetries: `mysql→tsql` lacked
      `UTC_TIMESTAMP→GETUTCDATE`, and the emit map sent `NTEXT→TEXT` on
      MySQL (64 KB cap; now LONGTEXT, matching the procedural map). The
      pipelines' current-timestamp spelling is unified to
      `CURRENT_TIMESTAMP` on PG/MySQL. Remaining (follow-up, same audit
      item): fold the regex-based per-construct rewrites (DATEADD/DATEDIFF,
      STRING_AGG, date formats) into declarative entries, and move dialect
      knowledge behind the per-engine plugin classes (doc 03 "plugin
      architecture" note).
- [x] API: sync (`def`) endpoints, input size limits (UNIQUE_MAX_SQL_BYTES),
      BOM-aware decoding, generic 500 messages.
- [x] `db_url` SSRF hardening (A3): databases are configured server-side as
      named DSNs (`UNIQUE_DSN_<NAME>`) and referenced by name (`db` field on
      both endpoints); `/api/v1/info` exposes the names (never URLs) and the
      UI renders them as a dropdown. A raw `db_url` now needs the extra
      `UNIQUE_ALLOW_RAW_DB_URL` opt-in on top of
      `UNIQUE_ALLOW_DB_CONNECTION`. Found and fixed along the way:
      `web/src/index.template.html` had drifted behind the committed
      generated `static/index.html` (a rebuild would have silently dropped
      the db-field feature); the template was regenerated from the committed
      output (round-trip verified) before applying the UI change.
- [x] Split the >2000-line modules. **Done 2026-07-05 for the one module where
      it helps; the other two are intentionally left whole (analysis below).**
  - **`converter.py` (3329) → `converter/` package** — `_base` (shared state +
    leaf helpers), `harvest`, `convert`, `emit`, each < 1600 lines, re-exported
    from `__init__`. Clean because these are free functions and parse/emit never
    call each other (only convert/emit import a few coercion helpers from
    harvest → no cycles).
  - **`procedural/parser.py` (2848) and `procedural/transformer/base.py` (2633)
    are single cohesive classes** (`ProceduralParser`, 89 methods;
    `ProceduralTransformer`, 121). Splitting a class means mixins, and a
    concern-grouping of the parser shows the methods are heavily interleaved (a
    recursive-descent parser: 53 statement methods calling each other, the
    token-cursor primitives, and the expression/DDL methods, with no contiguous
    sections). A mixin split would scatter tightly-coupled logic across files and
    fight mypy-strict (every cross-mixin `self._parse_x()` needs a base-class
    declaration) for no readability gain — it would make the code *worse*. Kept
    whole by design; revisit only if a genuinely independent sub-parser emerges.

**P2 — documentation drift (audit doc 05):**

- [x] Fix README/`docs/07-interfaces.md` CLI examples (`--from/--to`, no
      inline-SQL positional).
- [x] Correct compatibility-matrix rows (ROWNUM, MERGE→MySQL, Boolean) or
      implement them; add matrix probe tests.

## 19. SQLite import-only support (P2)

Moved from `docs/TODO.md` on 2026-07-05 (phases complete).

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


## 20. MediaWiki live-schema bug-hunt (P2)

Executing the transpiled MediaWiki 1.46 schema (64 tables) against **live**
engines (`test_mediawiki_live.py`) surfaced a class of real DDL bugs that the
sqlglot parse-check missed. Green live now: **`mysql → {postgresql, oracle,
tsql}`** and **`sqlite → postgresql`**. Fixed:

- **Binary/LOB types:** PostgreSQL `BYTEA`/`BLOB` take no length; MySQL
  TINY/MEDIUM/LONG `BLOB`→`BYTEA`/`BLOB`/`VARBINARY(MAX)` and `*TEXT`→`TEXT`/
  `CLOB`/`VARCHAR(MAX)`; Oracle has no `VARBINARY` (→`RAW`, keep length) or
  `DOUBLE` (→`BINARY_DOUBLE`); unsigned floats (`UDOUBLE`…) per target; a
  length-less binary (SQLite BLOB affinity) → `BLOB`.
- **Reserved-word identifiers** quoted for the target — in both the IR emit path
  (`_ident`) and sqlglot-passthrough statements (`_emit_passthrough` parses,
  marks reserved identifiers quoted, regenerates); added engine-specific reserved
  words (`collation`, `file`, `comment`, …).
- **`SERIAL`/`BIGSERIAL`/`SMALLSERIAL`** as a source → the target's identity
  (MySQL `AUTO_INCREMENT`, Oracle `GENERATED AS IDENTITY`, T-SQL `IDENTITY`) on
  the base integer type.
- **String default on a binary column** dropped for Oracle (ORA-01465) and
  SQL Server (error 257); **bare `NULLS FIRST/LAST`** stripped from index
  columns for non-PostgreSQL targets.
- **SQL Server live validator** now prefers **pymssql** (root-free), pyodbc
  fallback — so the `→tsql` targets run locally.

Remaining pairs (PostgreSQL/SQLite → MySQL/SQL Server/Oracle) all reduce to one
**intrinsic** impedance — indexing an unbounded `TEXT`/`BLOB` column, which those
engines cannot do — documented in `docs/03-unsupported.md` §0b and skipped in
the test's `_KNOWN_GAPS`.

## 21. Cross-engine %TYPE/%ROWTYPE resolution + SQLite metadata source (P2)

`--db-url` metadata resolution now works from **any of the five engines** and
covers both reference kinds:

- **SQLite as a metadata source** — `sqlite:///file.db` reads declared types via
  `PRAGMA table_info` (SQLite has no `INFORMATION_SCHEMA`), parsing the affinity
  string into name + length/precision/scale.
- **SQL Server via pymssql** — `_connect_tsql` prefers pymssql (root-free) and
  falls back to pyodbc; the `INFORMATION_SCHEMA` queries use a per-driver
  parameter marker so both work.
- **`%ROWTYPE` now consults the DB** — previously ignored, it is resolved via
  `resolve_table_columns` and the record's columns are documented in the warning
  (targets without a record type still emit a carrier).
- **Test** — `TestOracleTypeResolutionAcrossEngines` transpiles one Oracle
  `%TYPE`/`%ROWTYPE` source against a `--db-url` for each engine (seeding a
  self-contained probe table), asserting `%TYPE` resolves to a concrete type and
  `%ROWTYPE` is read from the schema. Wired into the `syntax-live` CI job (all
  four servers) plus SQLite, and unit-tested against an in-memory SQLite DB.

## 22. Corpus × live-execution sweep (bug-catching harness, approach 1)

Instead of finding bugs by running queries by hand, a corpus of self-contained
SQL (`tests/fixtures/corpus/<dialect>.sql`) is transpiled to every valid target
and the output is **executed against the real engine** (rolled back) via
`test_corpus_live.py` — wired into the `syntax-live` CI job, plus a
`scripts/corpus-sweep.py` for ad-hoc local sweeps (`--private` also sweeps the
gitignored real-world fixtures). Executing (not just parsing) is essential: a
permissive parser accepts output a real engine rejects.

The first run immediately caught three real converter bugs, now fixed + unit-
pinned (`test_subquery_limit.py`):

- **Derived-table alias dropped** — `FROM (SELECT …) t` lost `t`, so references
  to it (and the derived table itself on MySQL) were invalid.
- **Joined subquery dropped** — `… JOIN (SELECT …) b ON …` flattened the
  subquery to an empty `TableRef`, emitting `INNER JOIN  ON …`.
- **`LIMIT None` leak** — a T-SQL `OFFSET … FETCH NEXT n` parses to `exp.Fetch`
  whose count is in `args["count"]`, not `.expression`, so the count was lost.

Remaining engine-specific function/type gaps the sweep surfaced are annotated
inline with `-- @xfail: <targets>` in the corpus (a documented backlog; the test
flags them if they start passing). See docs/TODO.md.

## 23. Generative fuzzing + preservation invariants (approaches 4 & 3)

`tests/helpers/sql_gen.py` is a Hypothesis generator of portable, self-contained
SELECT statements (nested numeric expressions, derived tables, joined derived
tables, WHERE/ORDER BY, optional leading comment). `tests/property/
test_dml_properties.py` drives it and asserts, for every source→target pair,
invariants that must always hold — with Hypothesis shrinking any failure to a
minimal statement (the payoff over a fixed corpus):

- **no crash** and non-empty output;
- **no Python `None` leak** into the SQL;
- **output is valid target SQL** (sqlglot RAISE — catches a dropped derived-table
  alias or an empty `INNER JOIN  ON`, i.e. the structural bugs from §22);
- **leading comments preserved**;
- **derived-table aliases conserved** (no silent loss);
- **source→target→source round-trip stays valid**.

Runs in the plain (no-DB) suite (100 examples/property). Together with the live
corpus sweep (§22) this replaces ad-hoc manual query testing with generated
inputs + real-engine execution + always-true invariants.

## 24. Corpus-sweep function/type gaps closed (TODO §1 liquidated)

All 13 engine-specific function/type gaps the live corpus sweep (§22) surfaced —
annotated `-- @xfail` in the corpus — are fixed, and the sweep is fully green
(395/395 executed live). Each is a per-target handler in `_emit_function`
(sqlglot's own translation was the reference output to replicate):

- **Null/conditional**: Oracle `NVL2` and `DECODE` (parsed as `DecodeCase`) ->
  searched `CASE` for non-Oracle targets.
- **Date/time**: MySQL `NOW()` -> each engine's current-timestamp; `CURDATE()` /
  PostgreSQL `CURRENT_DATE` -> each engine's current-date (no stray parens);
  MySQL 2-arg `DATEDIFF(end, start)` -> per-target day count; Oracle `TO_CHAR`
  and `TO_DATE` format models translated between the Oracle / strftime / .NET
  models (`_convert_date_format`).
- **Numeric/cast**: numeric `TRUNC(x)` -> `TRUNCATE`/`ROUND(…,0,1)`; T-SQL
  `CONVERT(type, expr)` -> `CAST` (VARCHAR/INT -> CHAR/SIGNED on MySQL); `CAST
  AS BOOLEAN/INT` -> BIT / SIGNED per target.
- **String `+` chain**: `_rewrite_tsql_string_concat` now runs to a fixpoint, so
  every `+` in `'a' + 'b' + 'c'` becomes the concat operator (sqlglot's transform
  doesn't re-descend into a replaced node).

Pinned as fast unit tests in `test_function_mappings.py`. `docs/TODO.md` is now
packaging-only again.

## 25. Mutation testing + differential result testing (test-quality push)

Two measurement/improvement layers on top of the corpus harness:

- **Mutation testing** (`scripts/mutation_test.py`, nightly `mutation.yml`):
  mutates a module one node at a time and reports the score + surviving
  mutants — the objective test-assertion-quality metric the identity gate only
  approximates with one mutant. Baselines: convert.py 73%, emit.py 69%,
  transformer/base.py 62%; the weak functions are recorded in `docs/TODO.md` §1.
- **Differential result testing** (`tests/helpers/corpus_diff.py` +
  `test_corpus_results_live.py`, in the syntax-live CI job): executes each
  result-comparable corpus SELECT on its source engine and its transpiled output
  on each target, comparing normalized result sets. Catches *semantic* bugs that
  syntactic validity misses.

On its first clean run the differential test caught a real semantic bug:
**a UNION of 3+ arms dropped every middle arm** (`_convert_union` converted only
the outer two operands). Fixed by flattening the whole left-nested chain into a
linked `set_query`; regression-pinned in `test_subquery_limit.py`. It also
surfaced that EXCEPT/INTERSECT never reach `_convert_union` (tracked in TODO §2).

## 26. EXCEPT/INTERSECT converted + assertion hardening (TODO §1/§2 cleared)

- **EXCEPT / INTERSECT** now transpile (they were carriers): `exp.Except`/
  `exp.Intersect` are not `exp.Union` subclasses but share `exp.SetOperation`, so
  the dispatch and the multi-arm flatten loop now key on `SetOperation`. Oracle
  gets `MINUS`; a 3-arm `A EXCEPT B EXCEPT C` keeps every arm. Corpus + unit +
  result-diff coverage added.
- **Assertion hardening** for the convert.py mutation survivors (column-flag
  defaults `nullable`/`primary_key`/`unique`/`identity`, DISTINCT, idempotent
  DROP) in `test_ddl_flags.py` — asserting the default/negative case, not just
  the positive one. Re-measured: convert.py 73% -> 79% mutation score (survivors
  down despite the EXCEPT code adding 15 new mutants).

`docs/TODO.md` is packaging-only again; test-assertion quality is now a
continuously-tracked metric (the nightly mutation job), not a static backlog.

## 27. IR-node repr leaked into SQL (EXISTS subquery) + detection guard

Transpiling `INSERT … SELECT <literals> WHERE NOT EXISTS (SELECT … FROM t …)`
leaked a Python dataclass repr into the output —
`WHERE NOT EXISTS(SelectStatement(location=SourceLocation(...), …))` — because:

- `exp.Exists` is a Func, so it went through `_convert_function` and kept the raw
  `SelectStatement` as an argument; the emitter then hit its `str()` fallback.
  Fixed by converting `exp.Exists` to `UnaryOp(EXISTS, SubqueryExpression(...))`
  so the subquery emits as SQL (and `exp.Null` -> a NULL literal, not a carrier).
- The outer table-less SELECT stole the subquery's FROM: `_convert_select` used
  `expr.find(exp.From)` (recursive) instead of the direct `args["from_"]`, so the
  NOT EXISTS subquery's `FROM t` became the outer SELECT's FROM. Fixed.

Detection: `test_no_ir_leak.py` asserts the output never contains an IR-node repr
(`SourceLocation(` / `SelectStatement(` / `RawSQL(` / …) for EXISTS/IN/scalar
subqueries; the same invariant was added to the generative property test so any
future str()/repr() fallback is caught. Corpus + result-diff coverage added.

## 28. Bitwise operators -> Oracle (creative BITAND/POWER identities)

Reviewing the unsupported list for creative equivalents (each validated against
the *real* engine, since a permissive parser lies):

- **Bitwise -> Oracle**: Oracle has no infix bitwise operators (`|` is concat,
  `^`/`&` are errors), so they were emitted verbatim = invalid. Now translated
  via exact integer identities, live-validated (`5|3=7`, `5^3=6`, `5&3=1`,
  `8<<2=32`, `20>>2=5`): `a&b=BITAND(a,b)`, `a|b=a+b-BITAND(a,b)`,
  `a^b=a+b-2*BITAND(a,b)`, `a<<b=a*POWER(2,b)`, `a>>b=FLOOR(a/POWER(2,b))`. Corpus
  + differential-result coverage (results match the source engine's).
- **`IF EXISTS (subquery) THEN`** — investigated (the reported inspiration): it
  actually **compiles on Oracle 23 and MySQL 8** (both now allow a subquery in a
  boolean/IF condition), so no rewrite is needed on the supported engine
  versions. The validate-against-the-real-engine step is what caught this — the
  premise (that it was invalid) was wrong for current Oracle/MySQL.
- `IIF -> CASE` was already implemented; the stale doc note was corrected.

## 29. Date part/format + datetime casts (finish the "pending" date items)

The docs still listed `IIF`→`CASE` and `DATEPART`→`EXTRACT` as pending; a review
(each validated against the *real* engine) closed the genuine gaps:

- **`DATEPART(part, x)` -> `EXTRACT(part FROM x)`** (was the invalid comma form
  `EXTRACT(part, x)`, rejected by all three targets). `exp.Extract` is converted
  to a clean FunctionCall the emitter renders with `FROM`.
- **Date FORMAT model** — documented the four-convention token table (Oracle /
  MySQL DATE_FORMAT / T-SQL .NET / Python-strftime) in `03-unsupported.md` §3.1
  and fixed two real bugs: the **.NET model is case-sensitive** (`MM` month vs
  `mm` minute), and sqlglot's `TimeToStr`/`StrToTime` canonical is **Python**
  strftime (`%M` minute), not MySQL's (`%M` month name) — the conflation rendered
  `14:30` as `14:June`. All 7 cross-engine round-trips now return the same value.
- **`CAST(x AS DATETIME/DATETIME2/SMALLDATETIME)` -> `TIMESTAMP`** on Oracle/
  PostgreSQL (previously passed through and failed; `_CAST_TYPE_MAP` had no
  Oracle/PostgreSQL entries) and `DATETIME` on MySQL. Non-literal casts validated
  live; casting a string literal to a date on Oracle still depends on NLS format
  (pre-existing, orthogonal).
- **`IIF`→`CASE`** was already implemented; corrected the stale matrix row and
  `03-unsupported` §3.12. Tests: `test_date_format.py`, `test_no_ir_leak.py`.

## 30. Non-catalog IF EXISTS(...) BEGIN...END no longer silently dropped

`IF EXISTS (SELECT NULL) BEGIN SELECT 2 END` (tsql->oracle) transpiled to just
`SELECT 2 FROM DUAL` — valid SQL that runs with the **guard silently removed**
(the worst kind of loss: looks fine, wrong semantics). Root cause: the
migration-guard path (`_extract_exists_guard`) matched *any* `IF EXISTS(...)` and
dropped the condition, assuming — but never checking — that it queried a system
catalog.

Fix: the guard-drop now requires a **catalog reference** (`sys.*`, `OBJECT_ID`,
`INFORMATION_SCHEMA`, `sysobjects/…`). A non-catalog `IF EXISTS(...) BEGIN...END`
is classified as procedural control flow; the procedural parser preserves a block
it cannot fully model as a documented `-- UNIQUE:` carrier and now **registers a
warning** on the fallback (previously silent). A genuine catalog guard still
transpiles its guarded DDL. Pinned in `test_if_exists_control_flow.py`.

## 31. Oracle procedural string concat + nightly cron; validity backlog opened

- **String `+` -> `||` in Oracle procedural bodies.** The `+`-as-concat rewrite
  (already applied for PostgreSQL/MySQL) now also runs for Oracle in
  `_fix_oracle_dml` and the assignment/return path (`_fix_raw_sql_target`), so
  `V_WHERE := a + N' AND ' + b` becomes `a || ' AND ' || b` instead of failing
  with PLS-00306. Validated live.
- **Nightly mutation job** moved to **04:44 UTC** (`cron: "44 4 * * *"`).
- The Oracle validity sweep (see DONE #30 / TODO §1) is now precisely
  categorized: 24 INVALID objects remain across distinct, non-trivial procedural
  transformations (subquery-initialised variables, table-variable GTTs, bare
  result SELECTs, IF EXISTS, a statement-split trigger-carrier orphan). A phased
  effort, tracked objectively by the validator + `xfail`.

## 32. Result-set SELECT -> SYS_REFCURSOR OUT on Oracle (+ TOP, more)

Continuing the Oracle procedural validity backlog, worked class-by-class with
each fix validated against a live Oracle:

- **A bare result-set `SELECT` becomes a `SYS_REFCURSOR` OUT parameter** opened
  FOR that query (`OPEN result_cursor FOR SELECT …`). A T-SQL procedure returns
  rows with a bare SELECT; Oracle PL/SQL has no equivalent, and the *only* faithful
  form is a ref cursor. This preserves the query so the procedure body is correct
  — only the call sites adapt — vs a carrier, where the whole body would also need
  a manual rewrite (per user guidance). Applied for both CREATE and the T-SQL
  stub+`ALTER PROCEDURE` idiom; multiple result sets get distinct cursors; a
  `SELECT … INTO`/assignment is left alone.
- The equivalence **fingerprint** now recognizes `OPEN c FOR <query>`: its query's
  verbs/fields/conditions are counted (structure preserved) and it is not counted
  as a loop — so the mandatory DML-conservation invariant still holds.
- Also: `SELECT TOP (n)` in a scalar subquery -> `FETCH FIRST n ROWS ONLY` (via
  sqlglot); body/declare subquery assignments -> `SELECT … INTO … FROM DUAL`.

Sweep of the T-SQL procedures fixture -> Oracle: **26 -> 20 INVALID** (of 32); the
rest is a documented long tail (TODO §1). `test_oracle_refcursor.py`,
`test_oracle_subquery_assign.py`.

## 33. Oracle procedural validity backlog complete — 26 -> 0 INVALID

The whole T-SQL procedures fixture (32 objects) now transpiles to **fully-valid
Oracle**; `test_procedures_fixture_is_valid_live[oracle]` asserts it (the
special-case `xfail` is gone). Each fix was validated against a live Oracle,
class by class. The validator also **recompiles** invalid objects after loading to
settle forward dependencies (an object referencing one defined later in the script
compiles INVALID first — e.g. `FUNC4 -> FUNC2 -> PROC_6`), as a real deployment
does.

Structural features (each a real translation, not a carrier):

- **`EXEC sp_executesql @stmt, N'…', @a, @b` -> `EXECUTE IMMEDIATE @stmt USING @a,
  @b`** (the parameter-definition string is dropped).
- **Table variable -> hoisted Global Temporary Table.** A `DECLARE @t TABLE(…)`
  has no in-block Oracle form (a CREATE can't live in PL/SQL, and the block
  references it statically). Lift it to a schema-level GTT emitted *before* the
  procedure, with a per-procedure-unique name and renamed body references. An
  `INSERT … OUTPUT … INTO @t` (which Oracle RETURNING can't target a table with)
  is a documented carrier.
- **Trigger-local variables in a DECLARE section** (T-SQL declares them inline).
- **Reassigned IN parameters shadowed with locals** (`p -> p_IN` + `p := p_IN`);
  an Oracle IN parameter is read-only (PLS-00363), positional call sites unchanged.
- **Function RETURN of a SQL-only expression** (CAST, a SQL-only builtin like
  STANDARD_HASH, a scalar subquery) via `SELECT <expr> INTO v FROM DUAL; RETURN v`
  in a nested block.
- **Inline split table-valued function -> a `SYS.ODCIVARCHAR2LIST` function**
  (built-in collection; `REGEXP_SUBSTR` + `CONNECT BY`, no custom type/pipelining);
  callers rewritten `FROM fn(…)` -> `COLUMN_VALUE FROM TABLE(fn(…))`.

Expression / type / rule fixes: CLOB & `SQL_VARIANT` -> bounded `VARCHAR2` (a CLOB
can't be a comparison key, ANYDATA can't take a plain call argument);
`TRY_CAST` -> `CAST(… DEFAULT NULL ON CONVERSION ERROR)` (a *character* cast keeps
its length and takes no DEFAULT clause); `SHA256`/`HASHBYTES` -> `STANDARD_HASH`;
`EXTRACT(EPOCH …)` and `DATEDIFF` sub-day units via date arithmetic; the sqlglot
`TIME_STR_TO_TIME`/`DATE_STR_TO_DATE` wrapper unwrapped; `VARCHAR(MAX)` casts
bounded; CAST/subquery/RETURN treated as SQL-only in a PL/SQL expression; OUT/IN
OUT parameters take no DEFAULT (PLS-00230); a procedure/trigger RETURN carries no
value (PLS-00372); no `AS` before a table alias (ORA-00907, incl. the IR
cross-table UPDATE subquery, applied after the concat re-pass that re-adds it).

Test-harness: the functional-equivalence / real-world Oracle script splitter now
separates a `;`-DDL prefix from a trailing PL/SQL DROP guard and finds a PL/SQL
unit head *outside strings/comments* (so a `declare` inside a view's XML query
can't trip it) — mimicking SQL*Plus for a programmatic client. Version 0.18.0.

## 34. Source-syntax validation across core, API, web and CLI

A malformed script is now caught and **located** before transpiling rather than
silently mistranspiled. `unique.core.validation.validate_source(sql, dialect)`
splits the input by `GO` and parses each batch with sqlglot in `RAISE` mode,
returning `SyntaxIssue(line, column, message, snippet)` per problem. It flags
genuine errors (an unclosed parenthesis; a `CREATE PROCEDURE` with no preceding
`GO` — the batch it must start) while tolerating constructs sqlglot
*Command-fallbacks* (which the transpiler preprocesses — TEXTIMAGE_ON, WITH
NOCHECK, ALTER COLUMN, T-SQL procedures) and SQL\*Plus directives (`PROMPT`, …),
so valid T-SQL does not false-positive (0 on the procedures fixture).

Wired through every surface:

- **API** — `/api/v1/transpile` refuses a malformed source with `422`
  (`{error, message, issues}`) unless `ignore_syntax_errors: true`; a `source` of
  `auto` is detected before validating. `/api/v1/validate` returns the structured,
  line-located issues.
- **Web** — the page validates live (debounced) and disables the Translate button
  while the script is invalid, listing each error; the source-of-truth template
  (`web/src/index.template.html`) carries the JS, rebuilt via `web/build.py`.
- **CLI** — `unique transpile` refuses (exit 1, errors listed) unless
  `--ignore-syntax-errors`; `unique validate` reports the located issues.

Motivated by a real cumulative migration fixture with no `GO`s: the giant
first batch (mixing DML with procedures) collapsed into one carrier — now the
user is told exactly where the batch boundary is missing. (That fixture turned
out to be predominantly **Oracle** — `/`-terminated, `CREATE OR REPLACE`,
`PROMPT` — with historic non-Oracle patches, so it is transpiled as `oracle`,
not `tsql`; "add a `GO`" did not apply.)

## 35. M3 core (audit doc-04 P4): embedded DML through the shared IR pipeline

- [x] **Embedded DML in routine bodies runs the standalone IR pipeline**
      (`parse_sql → Transformer → emit_node`); raw `sqlglot.transpile` +
      target text-fixups remain only as an explicitly *warned* fallback
      (unmodeled constructs, TVFs in FROM, parse failures). One mapping
      engine, two callers: D3 (`FROM DUAL` INSERT-guards on PG/T-SQL) and D4
      (`ROWNUM` in procedural DML) became impossible by construction.
      Why it was the highest-value refactor: every "mapped in one pipeline,
      not the other" bug came from the procedural engine owning a second,
      regex-based copy of the dialect knowledge.
- [x] **Four IR-core bugs surfaced by the new traffic — all also corrupted
      standalone DML:** (1) transform-pass recursion stopped at top-level
      SELECTs (INSERT source queries/subqueries never saw a pass) — replaced
      with a generic dataclass-field walker; (2) `find(exp.Where/Having)`
      duplicated a derived table's WHERE onto the outer SELECT; (3) the
      emitter never re-parenthesized by precedence, silently re-associating
      `a AND (b OR c)`; (4) `OrderByItem.nulls_first` was never carried, so
      T-SQL `ORDER BY … DESC` changed row order on PostgreSQL. Also modeled:
      `exp.In` (was a RawSQL passes could not see) and unstyled `exp.Convert`
      (now a CastExpression sharing the CAST type maps: VARCHAR2 on Oracle,
      CHAR on MySQL).
- [x] **D8 expression corruption:** the T-SQL SELECT-INTO emitter split the
      select list with a naive `split(",")`, cutting inside function calls
      (`MAX(NVL(a,0)) + 1` lost `, 0))` and `+ 1`). Fixed with the shared
      paren/string-aware `split_top_level_commas` (`unique/core/sql_split.py`).
- [x] **Comment trivia hardening:** IR-harvested inline comments re-emit
      *before* the statement (a trailing one commented out the terminator);
      three head-anchored matchers (result-SELECT→refcursor, identity
      capture, trigger set-based rewrite) now match on
      `split_leading_trivia`'s code part.
- [x] **Measured (2026-07-09, live engines):** test.sql→PG **100.0%** /
      Oracle 99.6% / MySQL 97.7%; bigtest (Oracle source)→T-SQL **94.3%**,
      PG **76.6%** (73.1 pre-M3), MySQL 75.0%; live-syntax suite green;
      procedural fixtures regenerated. Tests:
      `tests/integration/test_embedded_dml_ir.py` (22 probes incl. an
      oracle→tsql→oracle round-trip). An IR-first route for *scalar
      expressions* was attempted and reverted (18 tests: downstream matchers
      consume expression text; the text path holds procedural context) —
      recorded as the M3-prereq item in `docs/TODO.md`.

---

## Wave campaign — corpus validity (2026-07-15 → 2026-07-17, waves 4–95)

Archived from `docs/TODO.md` §3 on 2026-07-17. Final standings at
`3fdfc88`: pg-source {tsql 163 (95.0%) / mysql 131 (95.7%) / oracle 89
(97.2%)}, mysql-source {tsql 166 (97.2%) / pg 107 (98.2%) / oracle 129
(97.8%)}. Waves 96–102 (M3-prereq increments, the M3b probe and the
family-migration survey) remain recorded in the open §2 M3 item of
`docs/TODO.md`.

- [x] **Import the upstream PostgreSQL regression fixtures as a PG-source
      test corpus — DONE** (fetcher shipped 2026-07-11; the corpus is the
      daily driver of the §3 wave loop, standing pg→{tsql 163, mysql 131,
      oracle 89}). Original (user request, 2026-07-10; evaluation done
      2026-07-10): Findings: **PG yes, MySQL no.**
      - *PostgreSQL* (`src/test/regress/sql/`, 247 files / ~4.9 MB): plain
        `.sql`, license is the permissive PostgreSQL License (BSD-like —
        committable with the COPYRIGHT notice reproduced). Probe: today's
        pipeline transpiles `insert.sql` PG→T-SQL in 0.2 s with honest
        warnings and no crash. Noise is tractable: sparse psql
        meta-commands (`\d+`, `\set`, …) and `COPY … FROM stdin` data blocks
        need a line-oriented strip (same class as the SQL*Plus directive
        peel); engine-internal suites (stats_import, rowsecurity,
        privileges, GUC tests) should simply not be selected. Start set:
        the portable core — insert/update/delete/join/select*/aggregates/
        window/case/union/subselect/with/triggers/plpgsql.
      - *MySQL* (`mysql-test/`): **rejected** — GPLv2 (incompatible with
        committing into this MIT repo) and written in the mysqltest DSL
        (`--source`, `if` blocks, per-connection commands) interleaved with
        the SQL, so it would need a real parser, not a curation pass.
      - *Fetcher shipped 2026-07-11:* `scripts/fetch_pg_corpus.py` downloads
        the 15-file portable core at a pinned tag (default `REL_17_5`),
        strips psql meta-commands + COPY-stdin blocks, prepends the license
        header, writes to the gitignored `fixtures-corpus/pg/`
        (download-on-demand). Tests: `test_fetch_pg_corpus.py` (8).
      - **HONEST baseline 2026-07-11 at `9176813`** (source-validated
        corpus: `filter_valid_source.py` keeps only the 5,196 statements
        live PostgreSQL itself accepts — the regression suite deliberately
        contains invalid SQL — and the shared splitter no longer counts
        transactional `BEGIN;` as block depth, which had glued 78% of the
        corpus into one pseudo-statement): **pg→Oracle 87.5% (454),
        pg→MySQL 83.9% (579), pg→T-SQL 71.3% (1090)**. Classes: tsql —
        149x near-',', 111x near-'=', 59x near-AS, 59x FIRST_VALUE needs
        OVER(ORDER BY), 58x near-')'; the dominant gate samples read
        "Expected table name but got CROSS/ON/GROUP_BY" (likely ONE emit
        mechanism dropping a FROM table). oracle — 133x ORA-00922, 61x
        ORA-00936, 54x ORA-00900, 68x PLS-00103. mysql — 576x generic
        1064 (needs the near-token dump classification M4 used). Work the
        classes from the sweep dumps, M4-style. **Waves 1–3b (2026-07-11,
        official re-measure at `ed9fa7e`): pg→Oracle 90.4% (351, was 454),
        pg→T-SQL 74.5% (973, was 1090), pg→MySQL 83.7% (589)** — session
        GUC SETs/RESETs degrade to carriers, VALUES relations lower to
        UNION ALL row-SELECTs on all four engines (they converted to
        NOTHING — empty FROM), ranking/offset window functions gain
        T-SQL's required ORDER BY (SELECT NULL), and joined derived
        tables keep their alias. **Remaining mysql residue classified:**
        dominated by plpgsql FUNCTION bodies spilling fragments
        (34x `AS LANGUAGE;`, 18x `RETURN AS NEW`, per-function CREATE
        heads) — the pg-source PROCEDURAL bring-up, an M4-scale
        workstream; first step is honesty (a desynced plpgsql unit must
        degrade WHOLE, doc-04 rule 4), then the function→routine
        conversion classes. *Wave 4 (2026-07-15):* the 34x `AS LANGUAGE;`
        class was the glued dollar-quote close (`end$$ language plpgsql`,
        no space): the lexer let `$` continue identifiers (Oracle
        `V$SESSION`), so `end$$` lexed as ONE identifier and the tail
        leaked into the body. For a postgresql source `$` now ends the
        identifier (dollar-quotes win, matching PG's own lexing) —
        `lexer.py`, tests in `test_pg_source_wave1.py::
        TestGluedDollarQuoteClose`. **Measured at `145551f` (2026-07-15):
        pg→Oracle 90.7% (341, was 351), pg→MySQL 84.9% (539, was 589),
        pg→T-SQL 74.7% (967, was 973).** Operational note: the pg-source
        sweep pushes Oracle to ~2.2 GiB — above its 2 g compose cap
        (cgroup OOM-killed it mid-sweep, `oom=true`); before an Oracle
        sweep run `docker update --memory 3g --memory-swap 3g
        unique-oracle-1` (runtime-only override; the committed 2 g cap
        keeps the full four-engine stack bootable on the 8 GB host).
        *Wave 5 (2026-07-15):* the PG signature grammar landed in the
        procedural parser — a dedicated postgresql branch of
        `_parse_parameter` (`[argmode] [argname] argtype [DEFAULT v]`,
        mode-first, name optional): type-only params `(int, int)`,
        argmode-first `(out x int)`, `int default 0` no longer desync
        (they had swallowed the whole function into the parameter list
        with ZERO warnings); unnamed params get synthesized `p1…pn`
        names and `$n` positional references rewrite to parameter names
        at token level (the lexer now emits `$1` as ONE token for a PG
        source); `BatchSplitter._split_postgresql` was rebuilt as a
        char-scanner (dollar-quotes, multi-line `'…'`/`E'…'` strings,
        `"…"` idents, comments) so old-style single-quoted plpgsql
        bodies stay whole, and `_consume_pg_routine_header` re-lexes a
        string body in place so `as '…' language plpgsql` converts like
        its `$$` twin. Tests: `test_pg_source_wave1.py` (TestTypeOnly…,
        TestPositionalParamReference, TestSingleQuotedBody,
        TestPgArgmodeFirstParameters). **Measured at `9a7263d`
        (2026-07-15): pg→Oracle 92.4% (269, was 341), pg→MySQL 86.3%
        (474, was 539), pg→T-SQL 75.8% (905, was 967)** — from the
        honest baseline that is Oracle 454→269, MySQL 579→474, T-SQL
        1090→905. The `RETURN AS NEW/OLD/x` fragment classes are gone
        from the residue. Next classes (fresh dumps, first-code-line
        shapes): mysql — plpgsql body *content* now that units hold
        together (19x stricttest = STRICT/INTO semantics, 12x
        raise_test = RAISE USING/level forms, 15x foreach_test =
        FOREACH…IN ARRAY, 10x compos = composite-type returns), 8x
        `float8 '…'` type-prefixed literals, 9x ARRAY_AGG; tsql — 60x
        `SELECT dbo.…` (qualified scalar-function calls in plain
        SELECTs, likely ONE emit shape), 30x `CREATE TABLE #…` temp
        tables, 18x trigger DDL, 17x partitioned CREATE TABLE.
        *Wave 6 (2026-07-15):* statistical/boolean aggregates + float8
        casts, in BOTH pipelines' shared paths. sqlglot canonicalizes
        `var_pop`→VARIANCE_POP (no engine accepts it; T-SQL dbo.-
        qualified it as a UDF → error 195) and mislabels MySQL's
        POPULATION-semantics VARIANCE/STDDEV with the sample-semantics
        canonical names. Landed: `_STAT_AGGREGATE_MAP` (canonical→per-
        target: VARP/VAR/STDEVP/STDEV on T-SQL, explicit `*_SAMP` on
        MySQL) + source-side `_SOURCE_STAT_NORMALIZATION` reading the
        new `SOURCE_DIALECT` ContextVar (mysql VARIANCE→VARIANCE_POP,
        tsql VARP/VAR/STDEVP canonicalized — covers aliased/nested
        args through the whole recursion); bool_or/bool_and/every →
        MAX/MIN (CAST(… AS INT) on T-SQL, CASE on Oracle); CAST DOUBLE
        → FLOAT (T-SQL) / BINARY_DOUBLE (Oracle) in `_CAST_TYPE_MAP`
        (55x `AS DOUBLE` in the tsql residue). Round-trip tests incl.
        the MySQL population-semantics preservation. Tests:
        `test_pg_source_wave1.py` (13 new). **Measured at `493565b`
        (2026-07-15): pg→T-SQL 77.0% (859, was 905), pg→MySQL 86.5%
        (468, was 474), pg→Oracle 92.4% (269 syntax unchanged — its
        aggregate wins show as ok 1698→1731, since ORA-00904 unknown
        function classifies as "other", not syntax).** Cumulative from
        the honest baseline: T-SQL 1090→859, MySQL 579→468, Oracle
        454→269.
        *Wave 7 (2026-07-15):* PG table-binding honesty. `INHERITS (…)`
        and `PARTITION OF … FOR VALUES …` were dropped SILENTLY by the
        IR conversion (a partition child shipped as a bare column-less
        `CREATE TABLE` — 30x `CREATE TABLE #…` in the tsql residue, 0
        warnings). Now modeled on `CreateTableStatement`
        (`inherits_clause`/`partition_of_clause`), the PG target renders
        them, and `SyntaxNormalizer._degrade_pg_table_binding` degrades
        the WHOLE statement to a carrier + warning + unsupported entry
        everywhere else. `DEFERRABLE`/`INITIALLY …` constraint
        attributes strip with a warning on T-SQL/MySQL via sqlglot-AST
        surgery on the constraint fragment (a column literally named
        "deferrable" is untouched); Oracle keeps them. Tests:
        `test_pg_source_wave1.py` (11 new). Left open: the partition
        PARENT (`PARTITION BY RANGE …`, 17x mcrparted) and column-LEVEL
        constraint attributes. **Measured at `3a54e36` (2026-07-15):
        pg→T-SQL 80.5% — syntax failures 859→696 (−163, the biggest
        single-wave drop); pg→MySQL 467 (−1); pg→Oracle 269 (flat).
        Denominators shrank (tsql 3732→3569 stmts) because the degraded
        INHERITS/PARTITION tables are now comment-only carriers — the
        honest ratchet is the absolute syntax count, not the %.**
        Cumulative from the honest baseline: T-SQL 1090→696, MySQL
        579→467, Oracle 454→269.
        *Wave 8 (2026-07-15):* PG routine-header attributes (STRICT,
        PARALLEL SAFE/UNSAFE/RESTRICTED, COST n, ROWS n, LEAKPROOF,
        WINDOW, SUPPORT fn, CALLED/RETURNS NULL ON NULL INPUT) were not
        consumed by `_consume_pg_routine_header` and spilled into the
        routine body as garbage declarations (`STRICT LANGUAGE;
        plpgsql AS; $ $;` inside the Oracle IS-section — 24x+
        PLS-00103 'AS', and the whole stricttest class on MySQL/T-SQL).
        Consumed now, both before AND after the `$$` body. Tests:
        `test_pg_source_wave1.py::TestPgRoutineHeaderAttributes`.
        **Measured at `e30a7e9` (2026-07-15): T-SQL 696→693, MySQL
        467→464, Oracle 269→266 (−3 each).** Honest read: the garbage
        declarations are gone (error-group composition changed) but the
        affected plpgsql functions still fail on their NEXT body
        blocker — RAISE forms, FOREACH, STRICT INTO — so the syntax
        counts barely move until those body features land. The
        remaining function classes are blocker CHAINS, not single
        shapes.
        *Wave 9 (2026-07-15):* `JOIN … USING (c)` → ON for T-SQL across
        the whole join CHAIN (27x+ errors 102/321): `_emit_join` now
        shares a per-SELECT `merged_cols` map tracking the chain's
        merged-column expression (LEFT/INNER keep the left carrier,
        RIGHT replaces it, FULL merges via COALESCE — PG's USING
        semantics), and derived-table left sides supply their alias.
        Left open: the parenthesized-join FROM item (`(j1 JOIN j2 USING
        (i)) AS x`, ~7x) flows outside the IR SELECT model and keeps
        USING; `SELECT *` projection still duplicates the join column
        (USING merges it in PG) — same caveat as the pre-existing
        single-join rewrite. Tests:
        `test_pg_source_wave1.py::TestJoinUsingOnTsql`. **Measured at
        `ca03ff9` (2026-07-15): T-SQL 693→687 (−6); MySQL 464 and
        Oracle 266 flat (USING is native there).** Less than the 27x
        class size: the paren-join FROM shape (~7x) stayed open and
        12x of the `SELECT *` group are bare-boolean WHERE clauses
        (error 4145, needs type knowledge). **Cumulative from the
        honest baseline: T-SQL 1090→687, MySQL 579→464, Oracle
        454→266.** The residue is now dominated by the plpgsql body
        bring-up chains (RAISE forms ~12x/direction, FOREACH 15x,
        STRICT INTO 19x, composite returns 10x) — the M4-scale
        workstream; single-shape DML waves are close to exhausted.
        *Wave 10 (2026-07-15):* plpgsql `RAISE level 'fmt %', args
        [USING …]` formatting — the first body-chain blocker. The raw
        argument tuple was pasted into single-argument carriers on
        every target (`PUT_LINE('x', a)` PLS-00306, `PRINT 'x', @a`
        error 102, bare `SELECT 'x', a` in MySQL functions), and the
        USING warning mislabeled plpgsql options as RAISERROR args.
        The parser now interleaves `%` placeholders (incl. `%%`) into
        ONE `||` concatenation in source spelling — the operator
        machinery maps it per target (CONCAT on MySQL, `+` on T-SQL,
        `||` on Oracle) — and folds USING options into the message
        with a truthful warning; MySQL SIGNAL hoists non-literal
        messages through `@uq_errmsg` (MESSAGE_TEXT accepts only
        literals/variables). Tests: TestPlpgsqlRaiseFormat (7). Left
        open: notices inside MySQL FUNCTIONs still emit a bare SELECT
        (invalid there — needs routine-kind context in the emitter);
        T-SQL `+` on non-string args is a runtime cast risk (M3
        string-typing). **Measured at `a1360c9` (2026-07-15): T-SQL
        687→677 (−10), Oracle 266→262 (−4), MySQL 464 flat — exactly
        the predicted chain effect: MySQL's RAISE functions stay
        blocked on the notice-in-FUNCTION SELECT. Cumulative: T-SQL
        1090→677, MySQL 579→464, Oracle 454→262.**
        *Wave 11 (2026-07-15):* that notice channel — a bare `SELECT
        <msg>` is invalid inside a MySQL FUNCTION (error 1415); the
        base `_emit_print` now diverts to `SET @uq_notice = …` with a
        documented carrier when `_in_mysql_function` (procedures keep
        the visible SELECT). Tests: TestMysqlFunctionNotice.
        **Measured at `6adf580` (2026-07-15): MySQL syntax 464 flat but
        ok 1741→1757 (+16) with expected-missing −16 — the fixed
        functions now create AND run, resolving their dependent calls.
        T-SQL 677 / Oracle 262 unchanged.**
        *Wave 12 (2026-07-15):* `RETURNS void` (62x in the corpus — the
        most common plpgsql test-function type) emitted verbatim and is
        invalid on every target. Mapped to the neutral scalar (INT on
        MySQL/T-SQL, NUMBER on Oracle) with a guaranteed trailing
        RETURN and bare `RETURN;` statements gaining the neutral value
        (nested included, via an `_in_void_function` flag). `DECLARE x
        record` (row shape unknown until runtime, no equivalent
        anywhere) now degrades the routine WHOLE to a carrier +
        warning; the procedural emitter's carrier contract generalized
        beyond the parse-fallback reason string. Tests:
        TestReturnsVoid, TestRecordDeclarationDegrades. **Measured at
        `640788e` (2026-07-15): MySQL 464→417 (−47), T-SQL 677→643
        (−34), Oracle 262→237 (−25) — the biggest chain-wave gain.
        Cumulative from the honest baseline: T-SQL 1090→643, MySQL
        579→417, Oracle 454→237.**
        *Wave 13 (2026-07-15):* `LANGUAGE sql` bodies (bare statement
        list, no BEGIN/DECLARE) were shredded by the declare-section
        parser into garbage declarations (`DECLARE select LONGTEXT;
        DECLARE $ $;`) — they now parse as statements and a non-void
        function's trailing SELECT/VALUES becomes its RETURN
        (`_parse_pg_sql_function_body`). PG pseudo-types (`record` in
        params/returns, the `anyelement`/`anyarray` polymorphic
        family) generalize the wave-12 record degrade: the routine
        degrades WHOLE with a warning naming the culprit. Tests:
        TestLanguageSqlBody, TestPolymorphicPseudoTypes. **Measured at
        `2792430` (2026-07-15): MySQL 417→389 (−28), T-SQL 643→615
        (−28), Oracle 237→215 (−22). Cumulative from the honest
        baseline: T-SQL 1090→615 (82.4%), MySQL 579→389 (88.0%),
        Oracle 454→215 (93.5%).**
        *Wave 14 (2026-07-15):* plpgsql's bare-``=`` assignment
        (synonym of ``:=``, unambiguous at statement start) parses as
        an assignment for a PG source — it shipped raw (PLS-00103,
        8x+ direct plus chain blockers); and ``RETURNS setof <t>``
        parses as ONE type unit (the inner name had leaked into the
        header as garbage) and degrades the routine WHOLE (RETURN
        NEXT protocol has no equivalent). Tests:
        TestPlpgsqlEqualsAssignment, TestSetofReturnsDegrade.
        **Measured at `7a1a1e2` (2026-07-15): MySQL 389→363 (−26),
        T-SQL 615→590 (−25), Oracle 215→202 (−13). Cumulative from the
        honest baseline: T-SQL 1090→590 (83.1%), MySQL 579→363
        (88.7%), Oracle 454→202 (93.9%).**
        *Wave 15 (2026-07-15):* PG `CREATE INDEX` → T-SQL rebuilt from
        the parsed tree (`_pg_index_to_tsql`): PG's nameless form gets
        a synthesized `<table>_<cols>_idx` name (T-SQL requires one),
        sqlglot's write-side CASE-WHEN NULLs emulation never reaches
        the column list, a filtered index's `NOT x IS NULL` spells
        `x IS NOT NULL` (the only form CREATE INDEX…WHERE accepts),
        unique indexes without a filter carry the NULLs-distinct
        semantics note, and the physical-clause round-trip carrier
        (CLUSTERED/WITH/ON fg) is re-injected — the cross-dialect
        round-trip suite caught the rebuild dropping it. Tests:
        TestPgIndexToTsql. **Measured at `8528178` (2026-07-15):
        T-SQL 590→582 (−8, ok +8); MySQL/Oracle flat (tsql-only wave).
        Cumulative from the honest baseline: T-SQL 1090→582 (83.3%),
        MySQL 579→363 (88.7%), Oracle 454→202 (93.9%).**
        *Wave 16 (2026-07-15):* boolean-literal conditions on T-SQL —
        PG's ``JOIN b ON true`` / ``WHERE false`` mapped via TRUE→1 to
        ``ON 1`` (error 4145, 12x): `_emit_condition` renders a bare
        boolean literal in WHERE/HAVING/ON position as a real
        predicate (`1 = 1` / `1 = 0`). Tests:
        TestBooleanLiteralConditionsTsql. **Measured at `7fa6c60`
        (2026-07-15): T-SQL 582→573 (−9); MySQL 363 / Oracle 202 flat.
        Session cumulative from the honest baseline: T-SQL 1090→573
        (83.5%), MySQL 579→363 (88.7%), Oracle 454→202 (93.9%).**
        Next classes (fresh dumps at `7fa6c60`): tsql — 23x `SELECT
        dbo.…` array-construct calls (`dbo.ARRAY`, `ARRAY_AGG`,
        `dbo.EXPLODE`: no arrays on T-SQL/MySQL → honest whole-
        statement carriers + unsupported entries), 18x triggers with
        transition tables (`EXECUTE FUNCTION` bindings), 13x remaining
        index shapes (expression indexes fall back to the generic
        path), 12x `CREATE OR ALTER VIEW` with aggregate ORDER BY
        args; mysql — 15x FOREACH…IN ARRAY (array emulation needed or
        honest degrade), 12x `f1()` polymorphic call sites, 8x
        `float8 'nan'` special values (`'nan'`/`'inf'` literals have
        no MySQL FLOAT spelling).
        *Wave 17 (2026-07-15):* array-construct honesty — statements
        using `ARRAY[…]`/`array_agg`/`unnest` shipped as fake calls
        (`dbo.ARRAY(1,2)`, unqualified `ARRAY_AGG(x)` — guaranteed
        engine errors) with ZERO warnings on T-SQL/MySQL. A statement-
        level gate in `Transformer.transform` degrades them WHOLE to a
        carrier + warning + unsupported entry (PG/Oracle keep their
        paths). Tests: TestArrayConstructsDegrade. **Measured at
        `0223762` (2026-07-15): MySQL 363→321 (−42), T-SQL 573→550
        (−23), Oracle 202 flat (kept its path). Session cumulative
        from the honest baseline: T-SQL 1090→550 (84.0%), MySQL
        579→321 (89.9%), Oracle 454→202 (93.9%).**
        *Wave 18 (2026-07-15):* dollar-quoted STRINGS in the PG lexer —
        the class fix behind the wave-4/5 patches (rule of three). A
        dollar-quoted literal NESTED in a body (`EXECUTE $q$…$q$`, the
        18x transition-table trigger class) shredded into `$ q $`
        token soup; the lexer now tokenizes `$$…$$`/`$tag$…$tag$` as
        ONE STRING normalized to single-quote form (the Oracle q'…'
        precedent), which routes outer bodies AND nested literals
        through the same wave-5 splice path. All prior dollar-quote
        tests keep passing. Tests: TestNestedDollarQuotedLiterals.
        **Measured at `4a09dc2` (2026-07-15): slightly NEGATIVE —
        T-SQL 550→551, MySQL 321→323, Oracle 202→204 (+5 total).
        Honest read: units that used to desync into whole carriers now
        parse and emit near-correct SQL that trips the NEXT chain
        blocker (e.g. `DECLARE CURSOR FOR EXECUTE` on T-SQL — dynamic
        FOR loops still need a target-side story). The class fix
        stands: one canonical dollar-quote path, all prior tests
        green, and the trigger/EXECUTE chains are now parseable for
        the next wave.**
        *Wave 19 (2026-07-15):* PG catalog internals — `CAST(x AS
        regclass)` (and the whole `reg*` OID-type family) plus system
        columns (`tableoid`, `ctid`, `xmin`…) shipped raw with zero
        warnings (22x ORA-00936). The wave-17 statement gate
        generalizes: `_gate_pg_internals` degrades such statements
        WHOLE on every non-PG target. Tests:
        TestPgCatalogInternalsDegrade. **Measured at `0e35ddd`
        (2026-07-15): Oracle 204→182 (94.4% — the whole regclass
        class), T-SQL 551→549, MySQL 323 flat. Cumulative: T-SQL
        1090→549, MySQL 579→323, Oracle 454→182.**
        *Wave 20 (2026-07-15):* ordered-set aggregates and ARRAY casts
        join the statement gate — `RANK(x) WITHIN GROUP (ORDER BY …)`
        reaches the IR as an unhandled-WithinGroup RawSQL and shipped
        verbatim (9x 1064 on MySQL, plus the T-SQL twin, 0 warnings);
        `CAST(x AS ARRAY)` (the aggregate-transition-function class,
        8x) was invisible to the wave-17 array finder. Both degrade
        WHOLE on T-SQL/MySQL; Oracle keeps WITHIN GROUP (native).
        Tests: TestOrderedSetAggregatesDegrade. **Measured at
        `4bcc1d9` (2026-07-15): MySQL 323→285 (−38, 90.9%), T-SQL
        549→519 (−30, 84.5%), Oracle 182 flat (native WITHIN GROUP).
        Cumulative: T-SQL 1090→519, MySQL 579→285, Oracle 454→182.**
        *Wave 21 (2026-07-15):* FULL OUTER JOIN on MySQL — no spelling
        exists there and it shipped raw (1064, the bulk of the
        remaining `SELECT *` class). Statement-level degrade with a
        warning naming the manual rewrite (LEFT JOIN UNION ALL right
        anti-join); T-SQL/Oracle/PG keep their native FULL JOIN.
        Classified for later: the raise_test residue is now SQLSTATE/
        SQLERRM pseudo-variables inside converted EXIT HANDLERs.
        Tests: TestMysqlFullOuterJoinDegrades. **Measured at `cdb86a0`
        (2026-07-15): MySQL 285→266 (−19, 91.5%); T-SQL 519 / Oracle
        182 flat. Cumulative: T-SQL 1090→519, MySQL 579→266, Oracle
        454→182.**
        *Wave 22 (2026-07-15):* custom-aggregate CALL syntax — `fn(*)`
        on a non-COUNT function and `fn(DISTINCT … ORDER BY …)` (an
        unhandled-Order RawSQL argument) have no T-SQL/MySQL spelling
        (UDFs cannot be aggregates); the statement gate degrades them
        WHOLE (errors 102/156, the remaining `SELECT dbo.…` class).
        Tests: TestUserAggregateCallsDegrade. **Measured at `7e7dee2`
        (2026-07-15): T-SQL 519→499 (−20, 85.0% — under 500), MySQL
        266→247 (−19, 92.0%), Oracle 182 flat. Cumulative: T-SQL
        1090→499, MySQL 579→247, Oracle 454→182.**
        *Wave 23 (2026-07-15):* Oracle leading-underscore identifiers
        quote (`_ident` + the derived-table/join alias sites that
        bypassed it — PG's suite aliases VALUES relations `_(x)`, 15x
        ORA-00911, and declares `_sqlstate` locals); plpgsql DECLARE
        defaults accept the bare `=` (wave 14 covered statements only
        — 6x PLS-00103 '='). Tests: TestOracleUnderscoreIdentifiers,
        TestPlpgsqlDeclareEqualsDefault. **Measured at `437a5c3`
        (2026-07-15): Oracle 182→170 (−12, 94.8%); MySQL 247 / T-SQL
        499 flat. Cumulative: T-SQL 1090→499, MySQL 579→247, Oracle
        454→170.**
        *Wave 24 (2026-07-15):* aggregate `FILTER (WHERE p)` — PG-only
        spelling with a FAITHFUL universal rewrite instead of a
        degrade: `agg(CASE WHEN p THEN x END)` (`COUNT(*)` counts 1),
        applied at IR conversion for every target (the `SELECT
        (SELECT` class, error 102). Tests: TestAggregateFilterRewrite.
        **Measured at `a71020f` (2026-07-15): MySQL 247→233 (92.5%),
        T-SQL 499→490 (85.3%), Oracle 170→168 — all three moved (a
        universal rewrite). Cumulative: T-SQL 1090→490, MySQL 579→233,
        Oracle 454→168.**
        *Wave 26 (2026-07-15):* `SET SESSION AUTHORIZATION` (kept as
        a "real SQL SET" in wave 1, but only PG has it — 6x MySQL + 6x
        Oracle) degrades with its own carrier in the SET-option path
        AND the passthrough; `DROP TYPE` on MySQL (no user-defined
        types in any form, 5x) mirrors the sequence carrier. Tests:
        TestSessionAuthorizationDegrades, TestMysqlUserTypesDegrade.
        **Measured at `9394e9c` (2026-07-15): Oracle 168→162 (95.0%),
        MySQL 233→222 (92.8%), T-SQL 477→471 (85.8%). Cumulative:
        T-SQL 1090→471, MySQL 579→222, Oracle 454→162.**
        *Wave 28 (2026-07-15):* the index rebuild generalizes to MySQL
        (`_pg_index_rebuild`): MySQL also requires an index name (4x
        nameless) and has NO filtered indexes at all — any WHERE drops
        with a broader-index note on plain indexes and degrades WHOLE
        on unique ones; opclass strip and name synthesis shared with
        the T-SQL path. Tests: TestPgIndexToMysql. **Measured at
        `4843e14` (2026-07-15): MySQL 219→210 (93.2%); T-SQL 467 /
        Oracle 162 flat. Cumulative: T-SQL 1090→467, MySQL 579→210,
        Oracle 454→162.**
        *Wave 29 (2026-07-15):* the raise_test residue — a bare
        re-``RAISE;`` inside a handler emitted ``SET MESSAGE_TEXT = ;``
        (empty: a syntax error AND a broken re-raise): the faithful
        spellings are MySQL ``RESIGNAL;`` and T-SQL ``THROW;`` (Oracle
        keeps ``RAISE;``). And the level-less ``RAISE 'msg' USING …``
        (defaults to EXCEPTION) now routes through the wave-10 format
        parser instead of shipping the USING tail raw with the old
        mislabeled warning. Tests: TestRaiseResidue. Sweep re-measure
        **Measured at `f156123` (2026-07-15): MySQL 210→206 (93.3%);
        T-SQL 467 / Oracle 162 flat. Cumulative: T-SQL 1090→467, MySQL
        579→206, Oracle 454→162.** Mutation validation #2: convert.py
        and procedural base.py both at/above floor; emit.py 57% (<60)
        — the remaining survivor work must run where nothing snapshots
        the tree (see the incident note below). **Incident 2026-07-15
        evening: `scripts/mutation_test.py` mutates sources IN PLACE;
        a background full-emit.py run was mid-mutant when wave 29's
        commit snapshotted the tree — 99e0ba4 pushed a mutated emit.py
        (CI caught it red); restored byte-for-byte in f156123, full
        gate + CI green. Rule: full mutation runs happen in CI, or
        locally only with gates/sweeps/commits quiesced.**
        *Wave 30 (2026-07-15):* the tsql raise_test twin —
        RAISERROR's is_direct heuristic was fooled by an expression
        payload STARTING with a quote (`'a' + 'b'` from the wave-10
        fold; error 102 near '+'): only a single literal/variable/
        msg-id goes inline now, expressions hoist through
        `@unique_errmsgN`. And the SQLERRM/SQLCODE→ERROR_* mapping
        widened to PG sources (plpgsql shares the names) plus
        SQLSTATE→CAST(ERROR_STATE() AS NVARCHAR(5)) with a
        domain-difference warning — all via `_map_outside_strings`
        (a literal 'SQLSTATE: ' label must never rewrite; the old
        plain re.sub was a latent string-corruption hazard on the
        Oracle path too). PERFORM mangling (`perform 1`→`perform;`)
        classified for the next wave. Also this block: the mysql-source
        private corpus filtered live — 10,352 statements kept, 39
        rejected (`filter_valid_source.py --dialect mysql`, throwaway
        database, DELIMITER-block aware). Tests:
        TestTsqlRaiserrorExpressionHoist. **Measured at `eed51dc`
        (2026-07-15): T-SQL 467→461 (86.1%); MySQL 206 / Oracle 162
        flat. Cumulative: T-SQL 1090→461, MySQL 579→206, Oracle
        454→162.**
        *Wave 31 (2026-07-15):* plpgsql ``PERFORM`` (evaluate and
        discard) reached sqlglot as raw text and mangled to
        ``perform;``. New `PerformStatement` IR node: MySQL emits
        ``DO expr;`` (exact semantics), T-SQL a throwaway inline
        ``DECLARE @uq_discardN SQL_VARIANT = (expr);``, Oracle a
        nested SELECT-INTO-discard block, PG keeps PERFORM; the
        FROM-tail form (multi-row discard) degrades with a warning in
        the transformer. Mutation floors: per user, measured by the
        NIGHTLY run only from now on (no local/dispatch runs). Tests:
        TestPerformDiscard. **Measured at `3b48991` (2026-07-15):
        MySQL 206→200 (93.5%), Oracle 162→159 (95.1%), T-SQL 461→455
        (86.3%) — all three moved. Cumulative: T-SQL 1090→455, MySQL
        579→200, Oracle 454→159.**
        **mysql-source baseline #1 (private local corpus, 2026-07-15,
        at `801ed0e`): mysql→PG 90.2% (648 syntax / 6,580 stmts),
        mysql→T-SQL 84.6% (988 / 6,422); mysql→Oracle failed mid-sweep
        on the long-TODO'd DPY-1001 session-kill — the sweep's Oracle
        runner now RECONNECTS and counts the killer statement as
        'other' (fixed in `scripts/validity_sweep.py`). **Complete
        baseline at `070c60f`: mysql→PG 90.2% (648/6,580), mysql→Oracle
        91.3% (555/6,412 — 1,604 'other' includes the session-killers,
        honestly counted), mysql→T-SQL 84.6% (988/6,422). The
        mysql-source direction now joins the wave cadence.**
        *Wave M1 (mysql-source, 2026-07-15):* the mirror of pg wave 1 —
        MySQL session knobs (`SET [@@]sql_mode`, `SET GLOBAL/SESSION/
        PERSIST`, bare `SET name =` system vars, and any SET whose
        value reads an `@@` variable — the save/restore pattern) plus
        admin commands (`FLUSH`, `LOCK/UNLOCK TABLES`, `ANALYZE/
        OPTIMIZE/REPAIR/CHECK/CHECKSUM TABLE` — sqlglot mis-parses
        FLUSH as an alias) degrade to documented carriers off MySQL,
        across all three routing paths (SET-option batch, passthrough,
        admin classified with the option statements — SQL*Plus
        precedent). Largest baseline classes: 68–124x per direction.
        Tests: TestMysqlSessionKnobsDegrade (13). **Measured at
        `351751c` (2026-07-15): mysql→T-SQL 988→756 (−232, 87.8%),
        mysql→PG 648→503 (−145, 92.1%), mysql→Oracle 555→323 (−232,
        94.8%).**
        *Wave M2 (mysql-source, 2026-07-15):* `CREATE TABLE t [AS]
        SELECT …` silently LOST its query on every source — the
        converter never read sqlglot's `expression` slot (0 warnings,
        worst class; MySQL's no-AS spelling was the 161x `CREATE
        TABLE` block in →PG). Also: MySQL `DOUBLE(11,0)` display
        widths drop for PG's parameterless `DOUBLE PRECISION`, and
        leading-`$` identifiers (legal in MySQL) quote on PG. Tests:
        TestMysqlCtasAndTypes. **Measured at `6f70e9c` (2026-07-15):
        mysql→PG 503→403 (−100, 93.7% — the CTAS class); mysql→Oracle
        323 syntax flat with ok +20 / expected-missing +63 (CTAS
        tables now exist, dependencies resolve); mysql→T-SQL 756→755.**
        *Wave M3 (mysql-source, 2026-07-15):* comment-only nested
        `BEGIN … END` blocks (MySQL scope idiom) are a syntax error on
        targets requiring at least one statement: the block emitter
        gains an `_empty_block_filler` hook — `SET NOCOUNT ON;` on
        T-SQL (the BEGIN TRY precedent), `NULL;` on Oracle/PG, none on
        MySQL where the empty block is legal. Tests:
        TestTsqlEmptyBeginBlock. **Measured at `dc8a027`
        (2026-07-15): mysql→T-SQL 755→754 (−1); PG/Oracle flat —
        honest small yield, the class was thinner than sampled and
        those routines carry further chain blockers. The mysql-source
        residue is now the long tail: PREPARE/EXECUTE dynamic SQL and
        the bug* procedural chains (→T-SQL 754, →PG 403, →Oracle
        323).**
        *Wave M4 (mysql-source, 2026-07-15):* T-SQL CTAS — no `CREATE
        TABLE AS` exists there; the faithful idiom `SELECT … INTO
        <#table> FROM …` now renders (an `into=` hook in
        `_emit_select`, 133x — the class wave M2's CTAS rescue made
        visible); and views over temporary tables (T-SQL 4508, 91x)
        degrade whole via a transformer gate driven by the TEMP_TABLES
        harvest. Left classified: `CREATE TABLE t LIKE t1` clones
        (26x) drop their LIKE — next wave. Tests:
        TestTsqlCtasBecomesSelectInto. **Measured at `051cc8d`
        (2026-07-15): mysql→T-SQL 754→572 (−182, 90.6% — the biggest
        mysql-source wave; ok +94). All three mysql-source directions
        now above 90%: →T-SQL 572 (90.6%), →PG 403 (93.7%), →Oracle
        323 (94.8%).**
        *Wave M5 (mysql-source, 2026-07-15):* `CREATE TABLE t2 LIKE
        t1` structure clones silently dropped their LIKE everywhere
        (bare CREATE, 0 warnings, 26x): now `like_source` on the IR —
        PG native `(LIKE t1 INCLUDING ALL)`, T-SQL `SELECT * INTO …
        WHERE 1 = 0`, Oracle empty CTAS, both with the
        indexes-not-cloned note; MySQL keeps its native form. Tests:
        TestCreateTableLikeClone. **Measured at `5eb75bf`
        (2026-07-15): mysql→T-SQL 572→566 (90.7%), mysql→PG 403→397
        (93.7%), mysql→Oracle 323 flat (LIKE tables now exist —
        expected-missing +6). mysql-source day-one cumulative: →T-SQL
        988→566 (−43%), →PG 648→397 (−39%), →Oracle 555→323 (−42%).
        Next tranche (heavy): the bug*/proc_* procedural chains
        (64-86x per direction — multi-blocker plpgsql-style bring-up
        for mysql routine bodies), and the dynamic PREPARE/EXECUTE
        trio's faithful mysql→PG conversion (native there; currently
        honest carriers).**
        *Wave M6 (mysql-source, 2026-07-15):* table-qualified INSERT
        column lists (`INSERT INTO t (t.a, t.b) …`, legal MySQL) —
        sqlglot cannot parse them and lenient paths truncated to
        `INSERT INTO t (t)` with the body GONE (the 2026-07-09 audit
        class, still alive in embedded routine bodies; the bug8849
        family). A retry-after-failure pre-parse normalization (the
        Oracle SYSDATE() pattern) drops the redundant qualifier inside
        the identifier-only list region. Tests:
        TestInsertQualifiedColumns. **Measured at `3e2f165`
        (2026-07-15): →PG 397→396, →T-SQL 566→565, →Oracle flat —
        honest small yield; the bug* routines carry further chain
        blockers. Day-one mysql-source close: →T-SQL 988→565 (90.7%),
        →PG 648→396 (93.8%), →Oracle 555→323 (94.8%). The residue on
        all six directions is now long-tail multi-blocker chains
        (M4-scale deep dives, diminishing per-wave yields).**
        *Wave 32 (2026-07-15, deep chains):* parameterized cursors —
        PG's name-first `c1 CURSOR (p1 int) FOR …` shredded the whole
        declare section and `OPEN c1(5)` dropped its argument as a
        stray statement. Parsed properly now (name-first path +
        `CursorOperation.args`); Oracle renders its native
        `CURSOR c1(p1 t) IS …`, PG keeps `c1 CURSOR (p1 int) FOR …`;
        T-SQL/MySQL (no parameterized cursors) degrade the routine
        whole. The analysis-before-change pass caught a LATENT silent
        loss on the way: `_transform_cursor_decl` rebuilt the node
        without its `parameters` field — fixed. Tests:
        TestParameterizedCursors. **Measured at `18aee57`
        (2026-07-15): T-SQL 455→418 (−37, 87.3% — the shredded-declare
        routines), Oracle 159→155 (95.2%), MySQL 200→198. Cumulative:
        T-SQL 1090→418, MySQL 579→198, Oracle 454→155.**
        *Wave 33 (2026-07-15, deep chains):* leading-underscore locals
        (`_sqlstate text` — the stacked_diagnostics family) are illegal
        unquoted in PL/SQL; they RENAME to `uq_*` through the existing
        `_var_map` rewrite (declare + assignments + raw-text references
        consistent, string literals untouched; quoting could not reach
        the raw references). The `_var_map` outside-strings application
        now also runs for the Oracle target. Remaining in that family:
        `GET STACKED DIAGNOSTICS` itself (mysql native; oracle→SQLERRM/
        FORMAT_ERROR_BACKTRACE; tsql→ERROR_*()) — classified for the
        next deep wave. Tests: TestOracleUnderscoreLocals. Sweep
        re-measure done: **flat at `22f63f4` — necessary but not
        sufficient (the family's next blocker is GET STACKED
        DIAGNOSTICS itself; wave-8 pattern, honestly recorded).**
        *Wave 34 (2026-07-15, deep chains):* `GET [STACKED] DIAGNOSTICS
        v = ITEM, …` (15x, mangled to `get AS stacked;`) — new IR node;
        Oracle/T-SQL convert to plain assignments through the EXISTING
        emitters (ROW_COUNT→SQL%ROWCOUNT/@@ROWCOUNT, MESSAGE_TEXT→
        SQLERRM/ERROR_MESSAGE(), PG_CONTEXT→FORMAT_ERROR_BACKTRACE/
        ERROR_PROCEDURE+LINE; RETURNED_SQLSTATE maps with a
        domain-difference warning); MySQL keeps ROW_COUNT() and the
        native CONDITION-1 form for condition items; PG verbatim.
        Unmappable items (pg_routine_oid) degrade per-item with a
        warning. Tests: TestGetDiagnostics (4). **Measured at
        `d50a058` (2026-07-15): Oracle 155→150 (95.4%), T-SQL 418→412
        (87.5%), MySQL 198→194 (93.7%) — all three moved; the
        stacked_diagnostics chain (waves 30→33→34) is unblocked
        end-to-end. Cumulative: T-SQL 1090→412, MySQL 579→194, Oracle
        454→150.**
        *Wave 35 (2026-07-15, deep chains):* `FOR v IN EXECUTE
        '<literal>'` — after wave 18 the dollar-quoted dynamic string
        is a plain literal, so the EXECUTE is unnecessary: the query
        INLINES (faithful on every target; the transition-table
        trigger family shipped `CURSOR FOR execute '…'`, invalid
        T-SQL). A NON-literal EXECUTE source (real dynamic SQL) joins
        the whole-routine degrade scan — no cursor-over-dynamic form
        off PG. Tests: TestForExecuteLiteralInlines. **Measured at
        `f5691aa`: −1/−1/−1 — the inlined loops now hit the NEXT link:
        the T-SQL cursor expansion's `FETCH INTO /* @col1… */`
        placeholder (column vars underivable in general; derivable
        when the loop var is scalar and the SELECT has exactly one
        output column — next link classified). Cumulative: T-SQL
        1090→411, MySQL 579→193, Oracle 454→149.**
        *Wave 36 (2026-07-15, deep chains):* transition-table aliases —
        PG statement triggers name them (`REFERENCING NEW TABLE AS
        newtab`); T-SQL's are the fixed `inserted`/`deleted`. The
        inlined trigger body's alias references now rename (outside
        string literals, via a generic raw-text-field walker); PG keeps
        REFERENCING verbatim. Tests: TestTransitionTableAliases. Sweep
        re-measure done: **flat at `bbbacd7` — the real blocker was one
        deeper: those triggers iterate DYNAMIC EXPLAIN output (engine
        introspection, `dbo.EXPLAIN (…)` as a cursor source). Wave 37
        refines the wave-35 inlining: only QUERY literals
        (SELECT/VALUES/WITH) inline; non-query literals join the
        whole-routine degrade. Tests:
        TestForExecuteNonQueryDegrades.**
        *Wave 38 (2026-07-16):* wave 37 ALSO measured flat — the
        two-strikes rule fired and the end-to-end trace found the real
        hole: the trigger-INLINE path (PG_TRIGGER_FN_BODIES) re-parses
        the harvested body and expands it BYPASSING the routine-level
        degrade scan. The inline now runs the same scan and degrades
        the TRIGGER whole when the body is unconvertible. Tests:
        TestTriggerInlineDegradeGate. **Measured at `da454df`: T-SQL
        411→408 (−3, the dynamic-EXPLAIN subset).**
        *Wave 39 (2026-07-16):* the rest of the trigger family blocks
        on plpgsql's `FOUND` flag (error 4145): per-target predicates
        now map it — `(@@ROWCOUNT > 0)` on T-SQL, `(ROW_COUNT() > 0)`
        on MySQL, native `SQL%FOUND` on Oracle (string-safe,
        pg-source only). Tests: TestPlpgsqlFoundFlag. **Measured at
        `62c078b` (2026-07-16): T-SQL 408→402 (−6, 87.8%); MySQL/Oracle
        syntax flat, ok +1 each. Cumulative: T-SQL 1090→402, MySQL
        579→193, Oracle 454→149.**
        *Wave 40 (2026-07-16):* plpgsql's TG_* context variables are
        compile-time CONSTANTS once the trigger function inlines into a
        named trigger — TG_NAME/TG_TABLE_NAME/TG_OP/TG_WHEN/TG_LEVEL
        substitute as literals from the trigger node (18x error 128).
        Next link classified: whole-row `inserted::text` stringification
        (no T-SQL form). Tests: TestTgContextConstants. **Measured at
        `54255e8` (2026-07-16): T-SQL 402→384 (−18, 88.3% — the whole
        child-trigger family in one stroke); MySQL/Oracle flat.
        Cumulative: T-SQL 1090→384, MySQL 579→193, Oracle 454→149.**
        *Wave 41 (2026-07-16):* null-safe comparison — PG's `IS [NOT]
        DISTINCT FROM` shipped raw as an unmapped operator (1064 on
        MySQL). Proper IR operators (NULLSAFE_EQ/NEQ) with per-dialect
        emission: MySQL `<=>` / `NOT (a <=> b)`, the version-safe
        EXISTS-INTERSECT form on T-SQL and Oracle (INTERSECT compares
        null-safely everywhere; Oracle arms take FROM DUAL), PG native.
        Tests: TestNullSafeComparison. **Measured at `3b41e16`:
        MySQL 193→183 (−10, 94.1%), Oracle ok +11 (INTERSECT forms
        run), T-SQL +1 — a select-list case exposed the
        value-vs-predicate gap.**
        *Wave 42 (2026-07-16):* that gap — a predicate is not a value
        on T-SQL/Oracle: the null-safe forms wrap in `CASE WHEN … THEN
        1 ELSE 0 END` in value position, and `_emit_condition`
        (WHERE/HAVING/ON) unwraps to the bare predicate. Tests
        strengthened (value + condition positions). **Measured at
        `f06d57d`: flat — the one select-list corpus case needs its own
        trace (single statement; parked).**
        *Wave 43 (2026-07-16):* select-list PREDICATES from MySQL
        sources — comparisons are VALUES there (1/0/NULL) but T-SQL/
        Oracle reject a predicate in value position (38x error 102 in
        mysql→tsql). `_emit_value_expression` wraps them tri-state
        exactly: `CASE WHEN p THEN 1 WHEN not-p THEN 0 END` (ELSE NULL
        implicit — MySQL's NULL semantics; the negation flips the
        operator when possible). Condition positions and PG boolean
        values untouched. Tests: TestSelectListComparisonsWrap. Sweep
        re-measure done: **at `53020a8` — mysql→T-SQL 565→536 (−29,
        91.2%), pg→T-SQL 385→380 (incl. the parked wave-42 case);
        mysql→Oracle +4 traced NOT to the wrap but to a distinct
        class:**
        *Wave 44 (2026-07-16):* MySQL routine bodies may be a SINGLE
        statement without BEGIN (`CREATE PROCEDURE g(..) CASE … END
        CASE;`); the declare-section parser shredded them into garbage
        declarations. A statement-keyword body now parses as one
        statement (the CASE statement legitimately converts to
        IF/ELSE). Tests: TestMysqlSingleStatementBody. **Measured at
        `c7dba03` (2026-07-16): −46 across the direction — mysql→Oracle
        327→308 (95.0%, the +4 reversed and beaten), mysql→T-SQL
        536→516 (91.5%), mysql→PG 396→389 (93.9%). Standing: pg-source
        {380/183/149}, mysql-source {516/389/308} — all six directions
        ≥88.5%.**
        *Wave 45 (2026-07-16):* two more dropped-definition shapes
        behind the 54x bare `CREATE TABLE` (mysql→pg): a table whose
        columns are ALL generated (passthrough fragments; `columns`
        empty → the emit skipped the whole parenthesized branch,
        constraints included — now triggers on constraints too), and
        CTAS whose query is a UNION (the M2 extraction accepted only
        exp.Select; now any SetOperation). Tests:
        TestBareCreateResidue. **Measured at `dc6eda1` (2026-07-16):
        −110 across the direction — mysql→PG 389→338 (94.7%),
        mysql→T-SQL 516→457 (92.5%), mysql→Oracle 308→307 with ok +13.
        Standing: pg-source {380/183/149}, mysql-source {457/338/307}.**
        *Wave 46 (2026-07-16):* three residue classes — the
        all-defaults `INSERT … VALUES ()` (every row empty) emitted a
        bare `VALUES ()` (invalid off MySQL); the existing DEFAULT
        VALUES fallback only fired when the values list was absent, so
        it now also routes the all-empty-rows shape (T-SQL/PG `DEFAULT
        VALUES`, Oracle degrades — no spelling without the column
        list). `IS` became a first-class BinaryOperator (was RawSQL
        'unmapped operator Is'), so `x IS NULL` in VALUE position gets
        wave 43's tri-state CASE wrap; IS/NULLSAFE joined
        _BIN_PRECEDENCE (the embedded-DML path KeyError'd). Sweep-side:
        tsql error 911 (USE of an absent database) reclassified as
        environmental, not syntax. Tests: TestEmptyValuesAndIsNullValue.
        **Measured at `faeef75` (2026-07-16): mysql→T-SQL 457→419
        (93.1%), mysql→PG 338→327 (94.8%), mysql→Oracle 307→296
        (95.2%). Standing: pg-source {380/183/149}, mysql-source
        {419/327/296}.**
        *Wave 47 (2026-07-16):* NATURAL join modifiers were silently
        DROPPED (sqlglot carries them in `method`, the converter read
        only side/kind): `NATURAL FULL JOIN` shipped as `FULL JOIN`
        with no ON at all (26x of the pg→tsql residue). JoinClause
        gained a `natural` flag: preserved on PG/MySQL/Oracle
        (`NATURAL JOIN` bare spelling for inner — MySQL rejects
        `NATURAL INNER JOIN`), whole-degrade on T-SQL (no NATURAL in
        any spelling, ON not synthesizable without column knowledge);
        mysql's FULL gate already catches NATURAL FULL there. Tests:
        TestNaturalJoins. **Measured at `6be4e8c` (2026-07-16):
        pg→T-SQL 380→374 (88.6%), pg→MySQL 183→180 (94.2%),
        pg→Oracle 149 flat. Standing: pg-source {374/180/149},
        mysql-source {419/327/296}.**
        *Wave 48 (2026-07-16):* parenthesized set-operation arms
        (`(SELECT …) UNION ALL (SELECT …)`) arrive as exp.Subquery;
        _convert_select read them as EMPTY selects — `SELECT * UNION
        ALL SELECT *`, every FROM and column dropped (62x of
        mysql→pg). Arms now unwrap; an arm with its own LIMIT is
        shielded as a derived table (trailing position would re-scope
        it to the whole union); arm-local ORDER BY without LIMIT drops
        (no observable effect in a set op); the union's OUTER
        order/limit (parsed onto the SetOperation node, previously
        ignored) attaches to the last arm. Tests:
        TestParenthesizedUnionArms. *Measurement pending next
        mysql-corpus cycle.*
        *Wave 49 (2026-07-16):* null-safe comparisons in VALUE
        position on T-SQL/Oracle shipped the predicate spelling
        `CASE … END = 1` (12x of pg→tsql — the trailing `= 1` is not
        a value there); the value position now keeps just the CASE
        (never NULL, so the two-armed form is exact). Tests:
        TestNullsafeValuePosition. **Waves 48+49 measured at `825d8cf`
        (2026-07-16, clean relaunch — the first cycle caught wave 49
        landing mid-measure): mysql→PG 327→256 (96.0%), mysql→T-SQL
        419→416 (93.2%), mysql→Oracle 296→301 (95.1%, honest +5 —
        un-carriered union arms now reach the next Oracle blocker).
        Standing: pg-source {374/180/149} at 6be4e8c, mysql-source
        {416/256/301}.**
        *Wave 50 (2026-07-16):* PG RETURNING lowered to T-SQL OUTPUT
        with BARE items — T-SQL requires the INSERTED./DELETED. prefix
        on every one (13x of pg→tsql: `OUTPUT *`, `OUTPUT a, b`).
        Items now qualify on the sqlglot AST (DELETE→DELETED, else
        INSERTED — PG returns the new row); DELETE's OUTPUT moves
        after the table (sqlglot renders it before FROM, which not
        even its reader accepts); the output gate drops the (valid)
        OUTPUT clause before its tsql reparse — a sqlglot reader gap,
        not an output defect. Tests: TestReturningOutputPrefix.
        **Waves 49+50 measured at `c1002d4` (2026-07-16): pg→T-SQL
        374→344 (89.5%), pg→Oracle 149 flat, pg→MySQL 180→186 (honest
        +6 — wave 48's un-carriered union arms reach the next MySQL
        blocker). Standing: pg-source {344/186/149}, mysql-source
        {416/256/301}.**
        *Wave 51 (2026-07-16):* TG_ARGV/TG_NARGS are compile-time
        constants once the trigger function is inlined — the CREATE
        TRIGGER's `EXECUTE FUNCTION fn('a','b')` argument list (which
        the parser used to SKIP; now captured as `execute_args`)
        supplies TG_ARGV[n]; an unresolvable index degrades the
        trigger whole (8x pg→tsql error 128). Tests:
        TestTgArgvSubstitution.
        *Wave 52 (2026-07-16):* a routine the procedural parser cannot
        parse falls back to RawSQL('Parse error…') — and shipped RAW
        cross-dialect: mysql handler-declaring procedure bodies leaked
        as top-level fragments on pg (~43x of mysql→pg: `declare
        continue/exit handler`, `end if/while`, quoted-alias SELECTs
        …). The procedural transformer now rewrites the parse fallback
        to the carrier contract (source==target still passes through
        untouched). Follow-up chain: parse DECLARE …HANDLER properly
        (EXIT→EXCEPTION is faithful; CONTINUE has no plpgsql map).
        Tests: TestParseFallbackDegradesCrossDialect. **Wave 52
        measured at `c92a5ab` (2026-07-16): −212 across the direction
        — mysql→PG 256→156 (97.5%), mysql→T-SQL 416→359 (94.0%),
        mysql→Oracle 301→246 (96.0%). Standing: pg-source
        {344/186/149}, mysql-source {359/156/246}; wave 51's pg-corpus
        measure pending.**
        *Wave 53 (2026-07-16):* PG's column-renaming table alias
        (`x AS xx(xx1, xx2)`) silently DROPPED its column list on
        every target (7x pg→tsql shipped it raw inside joins).
        TableRef gained `column_aliases`: T-SQL rewrites faithfully to
        `(SELECT * FROM x) AS xx(xx1, xx2)` (alias lists are legal on
        derived tables), PG keeps native, MySQL/Oracle whole-degrade
        (no spelling without column knowledge). Tests:
        TestTableColumnAliases.
        *Wave 54 (2026-07-16):* two invalid-shipping shapes on T-SQL —
        NTH_VALUE mapped to a fictitious `dbo.NTH_VALUE(...) OVER`
        (4x; now whole-degrades with the ROW_NUMBER emulation hint),
        and INSERT combining RETURNING with ON CONFLICT took the
        RETURNING passthrough leaving `ON CONFLICT` raw after OUTPUT
        (4x; now a MERGE-hint carrier off PG). Tests:
        TestTsqlInvalidShapesDegrade. **Waves 51+53+54 measured at
        `5997002` (2026-07-16): pg→T-SQL 344→266 (91.8%), pg→MySQL
        186→180 (94.1%), pg→Oracle 149→140 (95.6%). Standing:
        pg-source {266/180/140}, mysql-source {359/156/246} — all six
        ≥91.8%.**
        *Wave 55 (2026-07-16):* two mechanical mysql→tsql classes — a
        numeric literal operand of AND/OR in condition position (MySQL
        truthiness) becomes `lit <> 0` on T-SQL/Oracle (15x error
        4145: `HAVING f1 = 'a' OR 1`); and a scalar subquery's ORDER
        BY without LIMIT (illegal on T-SQL, no observable effect)
        strips (7x error 1033). Tests:
        TestTsqlBooleanLiteralsAndScalarOrder. **Measured at `e999409`
        (2026-07-16): mysql→T-SQL 359→347 (94.2%), →PG 156 and →Oracle
        246 flat. Standing: pg-source {266/180/140}, mysql-source
        {347/156/246}. Remaining mysql→tsql chains classified: 32x
        `SELECT … INTO @var` (sqlglot mangles the multi-var parse —
        degrade), 11x USING inside parenthesized join relations (the
        joins live on the inner Table's `joins` arg, never read), 12x
        mysql `@@sysvar` references, 6x RAND(seed).**
        *Wave 56 (2026-07-16):* MySQL's session-variable `SELECT …
        INTO @var[, @var2]` — sqlglot mangles the multi-var parse
        (extra vars absorb into the select list), and the CTAS path
        shipped `CREATE TABLE $a AS …` garbage (32x mysql→tsql). Now a
        `SELECT INTO VAR` passthrough: native on the source engine
        (identity keeps the ORIGINAL text, intercepted in parse_sql
        before the mangle), assignment-form-hint carrier elsewhere.
        Tests: TestSelectIntoUserVariable.
        *Wave 57 (2026-07-16):* single-level parenthesized join
        relations (`FROM (t1 LEFT JOIN t2 USING (a)), t3`) shipped raw
        through the PAREN JOIN passthrough — sqlglot keeps USING on
        tsql (11x). The group now unwraps: inner table + its `joins`
        arg hoist into the select (parens around joins are
        semantically transparent; comma-join order preserved); only
        deeper nesting stays passthrough. Tests:
        TestParenthesizedJoinRelations. **Measured at `6c15672`
        (2026-07-16): mysql→T-SQL 347→334 (94.5%), mysql→PG 156→153
        (97.5%), mysql→Oracle 246 flat. Standing: pg-source
        {266/180/140}, mysql-source {334/153/246}.**
        *Wave 58 (2026-07-16):* three mysql edge-value classes —
        CAST of an invalid calendar date ('0000-00-00', '2000-02-31',
        'YYYY-MM-DD'…) whole-degrades off MySQL (MySQL returns NULL +
        warning, everyone else errors; 24x), interval arithmetic
        `expr ± INTERVAL 'n' UNIT` lowers to `DATEADD(UNIT, ±n, expr)`
        on T-SQL (6x), and a MySQL `@@sysvar` T-SQL doesn't know
        (whitelist of T-SQL globals) whole-degrades (12x error 137).
        Tests: TestMysqlEdgeValueClasses. **Measured at `3a6f13e`
        (2026-07-16): mysql→T-SQL 334→303 (94.9%), mysql→Oracle
        246→242, mysql→PG 153 flat. Standing: pg-source
        {266/180/140}, mysql-source {303/153/242}.**
        *Wave 59 (2026-07-16):* three mysql-source classes — a
        top-level statement referencing a MySQL @user variable shipped
        raw off MySQL (session state lives client-side there; 23x
        ORA-00936 plus pg/tsql twins — whole-degrade, source==mysql
        gate); the EXISTS-INTERSECT null-safe form emitted ROW
        constructors as parenthesized tuples (`SELECT (f1, f2) FROM
        DUAL`, ORA-00907 15x — operands now unpack into select-list
        items, ExpressionList or paren-RawSQL); and MySQL's
        fixed-point `DOUBLE(p,s)`/`FLOAT(p,s)` mapped to
        `BINARY_DOUBLE(7, 2)` on Oracle which takes no parameters
        (13x ORA-00922 — now NUMBER(p,s)). Tests:
        TestUserVarsRowTuplesOracleDouble. **Measured at `60bf727`
        (2026-07-16): −59 across the direction — mysql→T-SQL 303→276
        (95.4%), mysql→Oracle 242→212 (96.5%), mysql→PG 153→148
        (97.6%). Standing: pg-source {266/180/140}, mysql-source
        {276/148/212}.**
        *Wave 60 (2026-07-16):* LATERAL joined subqueries VANISHED —
        exp.Lateral fell through _convert_table_or_subquery to an
        empty TableRef and the gate carriered the batch (7x pg→tsql).
        JoinClause gained `lateral`: T-SQL/Oracle spell it APPLY
        (LEFT + ON TRUE → OUTER APPLY, INNER/CROSS → CROSS APPLY),
        PG/MySQL keep native `LEFT JOIN LATERAL … ON …`; a non-TRUE
        lateral condition keeps the LATERAL spelling (gate carriers it
        on tsql — no APPLY equivalent). Tests: TestLateralJoins.
        **Measured at `2399670` (2026-07-16): un-carriered LATERAL
        batches un-glued +51 statements on pg→tsql (ok 2963→3010,
        syntax 266→270 — honest +4 reaching next blockers); pg→MySQL
        180→173 (94.4%), pg→Oracle 140→144 (honest +4). Standing:
        pg-source {270/173/144}, mysql-source {276/148/212}.**
        *Wave 61 (2026-07-16):* four mysql→tsql classes — row-tuple
        comparisons expand pairwise on T-SQL (no row constructors;
        `(a,b) = (x,y)` → `a = x AND b = y`, `<>` → OR; 17x error
        4145); boolean literals under AND/OR join wave 55's rewrite
        (`OR TRUE` shipped as bare `OR 1`; 13x); single-argument ROUND
        gains the mandatory scale (6x error 189); `SET NAMES`/
        `CHARACTER SET` join the session-knob carriers (3x error
        195). Tests: TestTuplesRoundSetNamesBoolLiterals. **Measured
        at `30aaf2d` (2026-07-16): −42 — mysql→T-SQL 276→252 (95.8%),
        mysql→PG 148→140 (97.7%), mysql→Oracle 212→202 (96.7%).
        Standing: pg-source {270/173/144}, mysql-source
        {252/140/202}.**
        *Wave 62 (2026-07-16):* STR_TO_DATE of an impossible date
        lowers to CAST at EMIT time — after wave 58's gate had run;
        the gate now inspects the function form too (6x mysql→tsql).
        And routines declaring/returning a PG composite type
        (`CREATE TYPE x AS (…)`, itself an Unhandled-CREATE carrier)
        shipped `DECLARE @v compostype` (6x pg→tsql): new
        PG_COMPOSITE_TYPES harvest + composite culprit in
        _degrade_record_function. Tests:
        TestStrToDateAndCompositeTypes. **pg-corpus measured at
        `2b943f6` (2026-07-16): pg→T-SQL 270→265 (91.9%), pg→MySQL
        173→163 (94.7%), pg→Oracle 144→142 (95.6%). Standing:
        pg-source {265/163/142}, mysql-source {252/140/202}.**
        *Wave 63 (2026-07-16):* four mysql→tsql classes — a row tuple
        compared to a SUBQUERY has no pairwise expansion
        (whole-degrade with the join/EXISTS hint; 16x); a bare scalar
        subquery in condition position is MySQL truthiness → `(sq) <>
        0` on T-SQL/Oracle (12x); a view's ORDER BY without TOP strips
        on T-SQL (illegal there, advisory on MySQL; 3x); zero-length
        CHAR/VARCHAR/BINARY become length 1 off MySQL (5x error
        1001). Tests: TestSubqueryConditionsViewOrderCharZero.
        **Measured at `62e7f1c` (2026-07-16): mysql→T-SQL 252→238
        (96.0%), mysql→PG 140 flat, mysql→Oracle 202 flat with ok
        +15. Standing: pg-source {265/163/142}, mysql-source
        {238/140/202} — all six directions ≥91.9%.**
        *Wave 64 (2026-07-16):* wave 59's @user-variable gate covered
        the DML pipeline only — routines travel the PROCEDURAL one,
        which shipped `@cnt := := @cnt + 1` garbage to Oracle (52x
        mysql→oracle: CALL blocks 26x, functions 16x, triggers 10x —
        the wave-38 alternate-route hole class again). The procedural
        transformer now whole-degrades any routine/call referencing a
        @user variable off MySQL. Tests: TestUserVarsInRoutines.
        **Measured at `00c2476` (2026-07-16): −70 — mysql→T-SQL
        238→213 (96.4%), mysql→PG 140→121 (98.0%), mysql→Oracle
        202→176 (97.1%). Standing: pg-source {265/163/142},
        mysql-source {213/121/176}.**
        *Wave 65 (2026-07-16):* MySQL's `INT UNSIGNED` in routine
        parameter/declare types broke the procedural parser — the
        whole body was swallowed as parameter garbage (15x mysql→pg);
        UNSIGNED/SIGNED/ZEROFILL now parse as type attributes (they
        tokenize as IDENTIFIERs, so the stop-word scan accepts those
        too), and `WHILE … DO … END WHILE` joined the loop grammar.
        PROCEDURAL_TYPE_MAPS gained the missing (mysql, oracle) and
        (mysql, postgresql) entries (`RETURN tinyint` shipped raw as
        PLS errors; DATETIME→TIMESTAMP to agree with the emit map).
        The scalar-subquery ORDER BY strip extends to Oracle (7x
        ORA-00907). Tests: TestUnsignedParamsOracleTypes. **Measured
        at `def5cb3` (2026-07-16): −23 — mysql→T-SQL 213→210 (96.5%),
        mysql→PG 121→113 (98.1%), mysql→Oracle 176→164 (97.3%).
        Standing: pg-source {265/163/142}, mysql-source
        {210/113/164}. pg-corpus re-verified at `76742d3`: identical
        {265/163/142} — the wave-65 parser changes (identifier stop
        words) cost nothing on pg source.**
        *Wave 66 (2026-07-16):* MySQL's `CHAR BINARY` collation
        attribute shredded the parameter parser like UNSIGNED did
        (12x mysql→pg; BINARY joins the attribute set), and a CALL to
        a routine whose CREATE degraded earlier in the same script
        shipped as `BEGIN a(3); END;` — PLS-00221 at compile (18x
        mysql→oracle). New DEGRADED_ROUTINES per-run registry:
        populated by every routine degrade (uservar, record/composite,
        parse fallback — name regexed from the original), checked in
        _transform_call. Tests: TestCharBinaryAndDegradedCallRegistry.
        First cycle at `4e87922` exposed two follow-ups (66b): the
        CALL carrier got WRAPPED in `BEGIN … END;` — a comment-only
        block, PLS-00103 (oracle 164→225 regression; an
        AnonymousBlock whose every statement degraded now returns the
        merged carrier bare); and `BEGIN a(3); END;` where the proc
        EXISTS but compiled invalid (its body references absent
        schemas) is an environmental cascade — PLS-00221 joins the
        sweep's expected bucket. **Measured at `5ab96bb`
        (2026-07-16): mysql→Oracle 164→158 (97.4%, the +61 regression
        fully reversed), mysql→PG 113→112 (98.1%), mysql→T-SQL 210
        flat (96.4%). Standing: pg-source {265/163/142}, mysql-source
        {210/112/158}.**
        *Wave 67 (2026-07-16):* MySQL's `REPEAT … UNTIL cond END
        REPEAT` shredded into garbage statements (`repeat AS set;` —
        REPEAT/UNTIL tokenize as identifiers, no grammar existed). It
        parses now as a post-test loop: LoopStatement with a trailing
        `EXIT WHEN cond`, native on every target. Tests:
        TestRepeatUntilLoop. **Measured at `50d734a` (2026-07-16):
        mysql→T-SQL 210→209, mysql→PG 112→111, mysql→Oracle 158→160
        (honest +2: un-carriered REPEAT routines reach their next
        blocker). Standing: pg-source {265/163/142}, mysql-source
        {209/111/160}. The mysql-source residue is now long-tail
        (top classes ≤5x); the next highest-yield front is the
        pg→tsql 265 (raise_test/EXCEPTION chains) and the
        DECLARE HANDLER fidelity work (carriers → EXIT→EXCEPTION
        conversions, no validity delta).**
        *Wave 68 (2026-07-16):* PG's `RAISE condition_name [USING k =
        v]` fell to the raw-expression path — T-SQL declared `@msg
        NVARCHAR(2048) = division_by_zero using detail = '…'` (6x
        pg→tsql raise_test). The condition name now folds into a
        literal message with USING items appended as text (the format
        path's existing convention). Tests: TestRaiseConditionName.
        **Measured at `7693a9f` (2026-07-16): pg→T-SQL 265→262
        (92.0%), pg→MySQL 163→160 (94.8%), pg→Oracle 142→140 (95.7%).
        Standing: pg-source {262/160/140}, mysql-source
        {209/111/160}.**
        *Wave 69 (2026-07-16):* a CTE body's ORDER BY without LIMIT
        is illegal on T-SQL (error 1033, ~7x pg→tsql) and cannot
        change the result — strips like the view/scalar-subquery
        cases (waves 55/63). Tests: TestCteOrderByStrip. **Measured at
        `c9d5a60` (2026-07-16): pg→T-SQL 262→261, others flat — the
        WITH chains carry further blockers (whole-row `SELECT q FROM
        q` refs). Standing: pg-source {261/160/140}, mysql-source
        {209/111/160}. Both directions are converged to deep
        multi-blocker chains: per-wave yield has been ≤3 for four
        waves. Remaining named fronts (fidelity, not validity):
        DECLARE HANDLER EXIT→EXCEPTION conversion, PG whole-row CTE
        references on tsql, EXPLAIN/psql-ism passthrough polish.**
        *Wave 70 (2026-07-16):* MySQL's `DECLARE {EXIT|CONTINUE|UNDO}
        HANDLER FOR conds stmt` now PARSES (new HandlerDeclaration
        node; wave 52 had been carrying whole routines). An EXIT
        handler for SQLEXCEPTION/SQLWARNING folds into the enclosing
        block's TryCatchBlock — EXCEPTION WHEN OTHERS on PG/Oracle,
        TRY/CATCH on T-SQL; identity keeps the native DECLARE …
        HANDLER spelling. CONTINUE handlers (resume semantics — no
        target equivalent), specific conditions (SQLSTATE/errno/named)
        and nested/multiple handlers keep the honest whole-routine
        degrade, now with the culprit spelled out. This is fidelity
        work: those routines were already carriers, so sweep validity
        should hold or improve slightly. Tests:
        TestMysqlDeclareHandler. **Measured at `95afaf8`
        (2026-07-16): the fidelity gain is visible — mysql→PG 111
        flat with ok +6 and warnings 289→263 (fewer carriers),
        mysql→T-SQL 209 flat with ok +11, mysql→Oracle 160→165
        (honest +5: converted handler bodies now reach PL/SQL's
        SELECT-without-INTO — the next front). Standing: pg-source
        {261/160/140}, mysql-source {209/111/165}.**
        *Wave 71 (2026-07-16):* the bare-SELECT → SYS_REFCURSOR
        rewrite (Oracle) did not recurse into TryCatchBlock bodies —
        a result SELECT inside wave 70's folded exception section
        shipped as PL/SQL SELECT-without-INTO (the +5). The recursion
        now covers try/catch bodies. Tests: TestRefcursorInTryCatch.
        **Measured at `f4cf7c9` (2026-07-16): mysql→Oracle 165→164;
        the rest of wave 70's +5 carries further blockers. Standing:
        pg-source {261/160/140}, mysql-source {209/111/164}.**
        *Wave 72 (2026-07-16):* two more MySQL-truthiness shapes — a
        bare function call or COLUMN as a condition gains `<> 0` on
        T-SQL/Oracle (`WHERE dbo.DAYNAME('…')`, `WHERE b`); and a row
        tuple in `IN (SELECT …)` joins wave 63's whole-degrade (the
        IN operator joins the tuple-vs-subquery gate). Tests:
        TestBareValueConditionsAndTupleIn. **Measured at `4511621`
        (2026-07-16): mysql→T-SQL 209→188 (−21, 96.8%) — the
        truthiness shapes were widespread; →PG/→Oracle flat.
        Standing: pg-source {261/160/140}, mysql-source
        {188/111/164}.**
        *Wave 73 (2026-07-16):* STR_TO_DATE inside an unconverted
        expression blob (a BETWEEN fallen to RawSQL) ships raw off
        MySQL — the emit-time STR_TO_DATE→CAST mapping only fires on
        FunctionCall nodes (6x error 195). The invalid-date gate now
        degrades statements whose RawSQL text calls STR_TO_DATE.
        Tests: TestRawStrToDateDegrades. **Measured at `173e7cf`
        (2026-07-16): mysql→T-SQL 188→180 (96.9%), →PG/→Oracle flat.
        Standing: pg-source {261/160/140}, mysql-source
        {180/111/164}.**
        *Wave 74 (2026-07-16):* the SYS_REFCURSOR rewrite changes the
        procedure's SIGNATURE, but same-script CALLs kept the old
        arity — PLS-00306 at compile (19x mysql→oracle). New
        REFCURSOR_PROCS per-run registry (populated when the rewrite
        adds params); later CALLs now wrap in a nested DECLARE block
        with local `uq_rcN SYS_REFCURSOR` variables appended to the
        argument list. Tests: TestRefcursorCallSites. **Measured at
        `f8ceb42` (2026-07-16): mysql→Oracle 164→144 (−20, 97.6%, ok
        +22); →PG/→T-SQL flat. Standing: pg-source {261/160/140},
        mysql-source {180/111/144}.**
        *Wave 75 (2026-07-16):* MySQL double-quoted STRING literals
        inside procedural raw text (`CONCAT(arg, "")`, `SET x =
        "it's"`) survived to targets where `"` delimits IDENTIFIERS —
        pg 42601 zero-length identifier (11x mysql→pg). A string-safe
        scanner now rewrites them to single-quoted literals (inner
        quotes doubled, backslash escapes honored) in
        _transform_raw_sql off MySQL. Tests:
        TestMysqlDoubleQuotedStrings. **Measured at `a4d7783`
        (2026-07-16): −9 across all three — mysql→T-SQL 180→177
        (97.0%), mysql→PG 111→108 (98.2%), mysql→Oracle 144→141
        (97.6%). Standing: pg-source {261/160/140}, mysql-source
        {177/108/141}.**
        *Wave 76 (2026-07-16):* MySQL labeled loops (`foo: loop … end
        loop foo`) and `LEAVE label` mangled into `foo AS %(loop)s;`
        garbage (4x mysql→pg). Labels parse now (loop/while/repeat
        heads; trailing END labels consumed; LEAVE→ExitStatement with
        label, ITERATE→CONTINUE); the label flows through
        _transform_loop and PG/Oracle emit `<<label>> LOOP … END LOOP
        label;` with `EXIT label;`. Tests: TestLabeledLoops.
        **Measured at `f083425` (2026-07-16): mysql→PG 108→107,
        others flat — the labeled routines carry further blockers.
        Standing: pg-source {261/160/140}, mysql-source
        {177/107/141}.**
        *Wave 77 (2026-07-16):* T-SQL forbids subqueries in PRINT
        arguments (error 1046 — 56x pg→tsql, inlined trigger bodies
        printing transition-table aggregates). The expression now
        hoists into a `DECLARE @uq_prtN NVARCHAR(MAX) = …` temp
        (initializers DO accept subqueries) and PRINT takes the
        variable. Tests: TestPrintSubqueryHoist. **Measured at
        `4c1c679` (2026-07-16): pg→T-SQL 261→257 (92.1%) — the 1046
        triggers carry further blockers (`dbo.FROM` mangles in UNION
        aggregates, OLD refs); →MySQL/→Oracle flat. Standing:
        pg-source {257/160/140}, mysql-source {177/107/141}.**
        *Wave 78 (2026-07-17):* `FROM (` before a derived table got
        dbo.-qualified (`dbo.FROM`) by the user-function pass —
        FROM/JOIN/LATERAL/APPLY were missing from TSQL_NEVER_QUALIFY
        (2x pg→tsql inside trigger CTEs, blocking the 1046 chain).
        Tests: TestFromNeverQualifies. **Measured at `6033f9a`
        (2026-07-17): pg→T-SQL 257→256 (92.2%). Standing: pg-source
        {256/160/140}, mysql-source {177/107/141}.**
        *Wave 79 (2026-07-17):* PG `expr::type` casts inside
        procedural raw text shipped as `x : : type` off PG (65x, the
        biggest remaining pg→tsql class) — simple operands
        (identifiers/@vars/numbers) rewrite to `CAST(x AS type)`
        string-safely; string-literal and parenthesized operands stay
        (rare). And `CAST(NOT b AS INT)` is invalid on T-SQL (NOT is
        not a value there; 12x) — the operand wraps tri-state
        `CASE WHEN b = 0 THEN 1 WHEN b <> 0 THEN 0 END`. Tests:
        TestPgCastsInRawTextAndNotInCast. **Measured at `d4bdacc`
        (2026-07-17): pg→Oracle 140→135 (95.8%), pg→T-SQL 256→254
        (92.2%) — the 65x routines also carry `RETURNS foodomain`
        (CREATE DOMAIN types; next front: harvest domains → base
        types, like PG_COMPOSITE_TYPES). Standing: pg-source
        {254/160/135}, mysql-source {177/107/141}.**
        *Wave 80 (2026-07-17):* PG DOMAIN types survived into
        signatures, declares and raw casts off PG (unknown type names
        — the rest of the 65x class). New PG_DOMAIN_TYPES harvest
        (name → base type); _transform_data_type resolves them and
        raw-text casts substitute string-safely. Tests:
        TestPgDomainTypes. **Measured at `f8c7cec` (2026-07-17):
        pg→MySQL 160→159, tsql/oracle flat — the domain routines
        stack `RETURN (SELECT … language sql)` body mangles on top
        (LANGUAGE sql single-expression functions whose body leaks
        into the RETURN). Standing: pg-source {254/159/135},
        mysql-source {177/107/141}.**
        *Wave 81 (2026-07-17):* the LANGUAGE-sql single-expression
        body capture ran past its closing $$ — `language sql` /
        IMMUTABLE / STRICT leaked into the RETURN expression (the
        rest of the 65x chain). Tail attributes now strip from the
        captured result. Tests: TestLanguageSqlTailStrip. **Measured
        at `e90c761` (2026-07-17): pg→T-SQL 254→252 (92.3%),
        pg→Oracle 135→133 (95.9%), →MySQL flat. Standing: pg-source
        {252/159/133}, mysql-source {177/107/141}.**
        *Wave 82 (2026-07-17):* PG's in-call aggregate ORDER BY —
        `STRING_AGG(x, ',' ORDER BY a)` — is `… ) WITHIN GROUP (ORDER
        BY a)` on T-SQL (51x, the blocker wave 77's hoist exposed). A
        paren-aware, string-safe scanner rewrites it in raw trigger
        text. Tests: TestStringAggOrderBy. **Measured at `abeaaa0`
        (2026-07-17): pg→T-SQL 252→198 (−54, 93.9%, ok +54) — the
        whole class cleared. Standing: pg-source {198/159/133},
        mysql-source {177/107/141}.**
        *Wave 83 (2026-07-17):* `BOOL_AND(NOT b2)` lowered to
        `MIN(CAST(NOT b2 AS INT))` on T-SQL — the boolean-aggregate
        mapping string-formats its arg, bypassing wave 79's IR wrap
        (12x); predicate/NOT args now wrap tri-state before the CAST.
        And `INSERT INTO t (cols) WITH cte AS (…) SELECT` puts the
        CTE after the INSERT clause — T-SQL requires WITH first (14x
        error 156); the CTE hoists before the INSERT. Tests:
        TestBoolAggregateNotArg, TestInsertCteHoist. **Measured at
        `3cc6a3d` (2026-07-17): pg→T-SQL 198→189 (94.2%), others
        flat. Standing: pg-source {189/159/133}, mysql-source
        {177/107/141}.**
        *Wave 84 (2026-07-17):* a searched CASE's WHEN emitted its
        condition as an EXPRESSION — a bare boolean column
        (`CASE WHEN b1 THEN …`) shipped raw to T-SQL (part of the
        4145 residue). Searched WHENs (no operand) now emit in
        condition position, picking up the truthiness wraps; simple
        CASE operands stay expressions. Tests:
        TestCaseWhenBareBoolean. **Measured at `e540dc3`
        (2026-07-17): pg→T-SQL 189→182 (94.4%), others flat. CI note:
        waves 83's `inner` name collision tripped CI mypy (version
        newer than local) at 3cc6a3d/6376336 — fixed in this wave's
        commit, CI green again at e540dc3. Standing: pg-source
        {182/159/133}, mysql-source {177/107/141}.**
        *Wave 85 (2026-07-17):* linking an outer set operation onto
        an arm that is ITSELF a chain (`(a UNION b ORDER BY 1)
        INTERSECT c`) clobbered the nested chain — the whole inner
        tail vanished silently, and a surviving tail ORDER BY landed
        mid-chain (error 156, 3x+). Chain arms now link at their
        TAIL, dropping a tail ORDER BY without LIMIT. Tests:
        TestNestedChainMidOrderStrip. **Measured at `56e1e9f`
        (2026-07-17): validity flat {182/159/133} — the clobbered
        arms had been emitting VALID SQL with silently missing data,
        so this is a pure correctness (no-silent-loss) repair.
        Standing: pg-source {182/159/133}, mysql-source
        {177/107/141}.**
        *Wave 86 (2026-07-17):* PG array types in RETURNS shredded
        the header — the RETURNS branch used the generic type parser,
        not the pg-aware one that consumes `[]` (48x pg→oracle:
        `[] LANGUAGE; plpgsql STRICT;` garbage declares). RETURNS now
        parses pg-aware, and array-typed params/returns/declares
        degrade the routine whole off PG (no target equivalent).
        Tests: TestPgArrayTypedRoutines. **Measured at `478ced0`
        (2026-07-17): −29 across the direction — pg→T-SQL 182→174
        (94.7%), pg→MySQL 159→147 (95.2%), pg→Oracle 133→124 (96.2%).
        Standing: pg-source {174/147/124}, mysql-source
        {177/107/141}.**
        *Wave 87 (2026-07-17):* PG ARRAY constructors inside routine
        BODIES (`x := array[$1,$2]`) shipped raw off PG — wave 86
        checked declared types only (part of the 39x pg→oracle
        residue). A body whose raw text builds arrays now degrades
        the routine whole. Tests: TestArrayConstructorInBody.
        **Measured at `d58d8e0` (2026-07-17): −4 — pg-source
        {172/146/123}; the 39x PLS class is heterogeneous (remaining
        shapes: dotted refs, assignment mangles — deep singles).
        Standing: pg-source {172/146/123}, mysql-source
        {177/107/141}.**
        *Wave 88 (2026-07-17):* top-level DML with RETURNING shipped
        the clause raw to Oracle (ORA-00936, 7x) — RETURNING…INTO
        exists only inside PL/SQL with target variables. Same
        contract as the MySQL branch: the DML keeps its effect
        (sqlglot-rendered for the target), the clause strips with a
        documented note. Tests: TestReturningOracle. **Measured at
        `a4623e5` (2026-07-17): pg→Oracle 123→98 (−25, 97.0%, ok +15
        — the class spanned INSERT/DELETE RETURNING forms too);
        tsql/mysql flat. Standing: pg-source {172/146/98},
        mysql-source {177/107/141}.**
        *Wave 89 (2026-07-17):* the RETURNING+ON CONFLICT carrier
        (wave 54) sat AFTER the MySQL RETURNING branch — MySQL
        stripped RETURNING and shipped ON CONFLICT raw (4x); the
        check now runs first, off PG. And PG E-strings in procedural
        raw text emitted as `E '...'` (3x): MySQL's backslash escapes
        are compatible, so the prefix drops there (other targets
        treat backslashes literally — left alone). Tests:
        TestOnConflictMysqlAndEStrings. **Measured at `73505e1`
        (2026-07-17): pg→MySQL 146→135 (95.6%), pg→Oracle 98→94
        (97.1%), tsql flat. Standing: pg-source {172/135/94},
        mysql-source {177/107/141}.**
        *Wave 90 (2026-07-17):* three mysql→tsql classes —
        `DELETE/UPDATE IGNORE` is unparseable by sqlglot (whole batch
        carriered and glued innocents, 4x): the modifier
        pre-normalizes away on the retry path (error-skipping
        semantics have no cross-engine form); MySQL's INVISIBLE
        column attribute strips off MySQL (3x); OFFSET…FETCH without
        ORDER BY gains `ORDER BY (SELECT NULL)` (6x). Tests:
        TestIgnoreInvisibleOffsetOrder. **Measured at `e673e81`
        (2026-07-17): mysql→T-SQL 177→165 (97.2%), mysql→PG 107→106
        (98.2%), oracle flat. Standing: pg-source {172/135/94},
        mysql-source {165/106/141}.**
        *Wave 91 (2026-07-17):* three mysql→oracle classes — charset
        introducers and COLLATE clauses (engine-local) strip from
        RawSQL fragments off MySQL (`_latin1 'test' COLLATE …`,
        ORA-00911, 3x); ROW-tuple comparisons expand pairwise on
        Oracle too (wave 61 was tsql-only, incl. the tri-state wrap's
        negated arm, 3x); and PLS-00049 (trigger :NEW field on a
        table whose CREATE degraded) joins the sweep's expected
        bucket (6x cascade). Tests:
        TestCharsetIntroducersAndRowOracle. **Measured at `b09c3ea`
        (2026-07-17): mysql→Oracle 141→129 (−12, 97.8%); tsql 166 /
        pg 107 (±1 statement-count noise). Standing: pg-source
        {172/135/94}, mysql-source {166/107/129}.**
        *Wave 92 (2026-07-17):* PG casts of PARENTHESIZED expressions
        (`row(a,b)::int8_tbl` — composite row types) survive the
        simple-operand ANSI rewrite and shipped as `) : : type` (6x
        pg→tsql). A body still carrying such a cast now degrades the
        routine whole. Tests: TestParenCastDegrades. **Measured at
        `092b41a` (2026-07-17): −14 — pg→T-SQL 172→165 (94.9%),
        pg→MySQL 135→132 (95.7%), pg→Oracle 94→90 (97.2%). Standing:
        pg-source {165/132/90}, mysql-source {166/107/129}.**
        *Wave 93 (2026-07-17):* PG's `RAISE sqlstate '1234F'` fell to
        the raw-expression path where the T-SQL SQLSTATE→ERROR_STATE
        substitution mangled it (3x); like wave 68's condition-name
        form, it folds into a literal message. Tests:
        TestRaiseSqlstateLiteral. **Measured at `8a63039`
        (2026-07-17): −3 — pg-source {164/131/89}; pg→T-SQL reaches
        95.0%. Standing: pg-source {164/131/89}, mysql-source
        {166/107/129} — all six directions ≥95.0%.**
        *Wave 94 (2026-07-17):* `(a, b) IN (VALUES (1,1), (20,0))`
        has no T-SQL/Oracle spelling (row constructors, 4145) —
        literal rows expand to the disjunction of conjunctions.
        Tests: TestTupleInValuesList. **Measured at `4cbc26b`
        (2026-07-17): pg→T-SQL 164→163, rest flat — the remaining
        statements stack multiple exotic constructs each (deep-singles
        floor: further waves cost a full cycle for −1). Standing:
        pg-source {163/131/89}, mysql-source {166/107/129}.**
        *Wave 95 (2026-07-17):* backlog housekeeping closed three
        completed items (nightly mutation floors GREEN at `17de248`,
        mysql-source corpus sweep, PG corpus import), and the
        live-check spotted there confirmed: MySQL requires
        parentheses around expression DEFAULTs — the column emitter
        shipped `DEFAULT UUID()` bare (1064). Function-call defaults
        now parenthesize (CURRENT_TIMESTAMP exempt). Tests:
        TestMysqlFunctionDefaultParens. **Measured at `d9ac96d`
        (2026-07-17): flat {163/131/89} — correctness fix (the pg
        corpus barely exercises uuid defaults). Standing: pg-source
        {163/131/89}, mysql-source {166/107/129}.**
        *Wave 27 (2026-07-15):* whole-row `COUNT(t2.*)` (PG counts
        non-NULL rows after an outer join; 9x 1064) — no spelling
        elsewhere and no rewrite without schema knowledge: a QUALIFIED
        star argument (IR: ColumnRef `*` with a table) degrades the
        statement whole on every non-PG target; plain `COUNT(*)`
        untouched. Tests: TestQualifiedStarCountDegrades. Sweep
        re-measure done: **measured at `14b1600` (2026-07-15): MySQL
        222→219 (92.9%), T-SQL 471→467 (85.9%), Oracle 162 flat
        (95.0%). Cumulative: T-SQL 1090→467, MySQL 579→219, Oracle
        454→162.**
        *Wave 25 (2026-07-15):* index-rebuild refinements — PG
        opclasses (`roomno bpchar_ops`, error 35336) strip to the bare
        column; a filtered-index predicate outside T-SQL's restricted
        grammar (arithmetic left sides, error 10735) drops the WHERE
        with a broader-index note on plain indexes and degrades WHOLE
        on UNIQUE ones (a broader unique index would reject rows the
        partial one allowed); the predicate renderer now accepts only
        column-vs-constant comparisons. Tests:
        TestIndexRebuildRefinements. **Measured at `6e74f3f`
        (2026-07-15): T-SQL 490→477 (−13, 85.6%); MySQL 233 / Oracle
        168 flat. Cumulative: T-SQL 1090→477, MySQL 579→233, Oracle
        454→168.**
        Known gaps left open (P2): **MySQL FUNCTION emitter drops
        OUT/INOUT modes silently** for every source (MySQL functions
        can't declare them — needs a warning per no-silent-loss);
        **VARIADIC** parameters still desync (no consume, no carrier);
        array subscripts (`p1[1]`) degrade honestly via the output gate. Getting here surfaced and
        fixed THREE product bugs: the sqlglot COPY DoS (`:'var'`,
        `3aa55b4`), the transactional-BEGIN splitter glue (also under the
        output gate), and the oracle first-boot healthcheck wait.

- [x] **MySQL-source validity sweep over the private local corpus — DONE
      2026-07-15/17** (M1–M6 plus waves through 91; standing in §3:
      mysql→{tsql 166, pg 107, oracle 129}, all ≥97.2%). Original (P2,
      2026-07-15): A privately-prepared mysql-source corpus now exists under
      the gitignored `fixtures-corpus/` (local-only material; per policy its
      provenance is not documented here — see the private prep script next to
      it). Pending: a mysql variant of `scripts/filter_valid_source.py` (the
      current one is PG-only) to get an honest denominator, then per-direction
      sweeps mysql→{pg,oracle,tsql} joining the wave cadence.


---

## Items archived from TODO on 2026-07-17 (completed checkboxes)

### From: P1 — silent semantic changes (no-silent-loss violations)

- [x] **N1 (fixed in M2): unbracketed real-data `IF [NOT] EXISTS` guard dropped silently.**
      `IF NOT EXISTS (SELECT 1 FROM cfg WHERE k='x') INSERT …` (no `BEGIN`)
      loses the condition on every target with zero warnings — re-runs insert
      duplicates. `batch_splitter._classify` (line ~278) only protects the
      `BEGIN … END` form; drop the `_TSQL_BEGIN_BLOCK_RE` conjunct so any
      non-catalog guard routes to the procedural engine. Add single-statement
      INSERT/UPDATE/DELETE guard probes + an FE scenario running a guarded
      INSERT twice.
- [x] **N2 (fixed 2026-07-10): PG → T-SQL temp-table rename not
      script-wide.** Temp-table names are harvested once per transpile
      (`harvest_temp_tables` → `TEMP_TABLES` ContextVar, same pattern as
      `IDENTITY_COLUMNS`) and `_emit_table_ref` prefixes `#` on every
      reference for the T-SQL target — FROM, INSERT, DROP included.
      Tests: `tests/integration/test_temp_table_rename.py` (incl. the
      PG→T-SQL→PG round-trip and a non-temp negative).


### From: P2 — correctness of signals and validation

- [x] **Guard audit findings (2026-07-09, per-batch sweep of the private
      corpora):** test.sql/test2.sql clean (531 guarded batches, 0 losses);
      bigtest exposed three classes, all fixed: (1) `parse_sql` trusted
      sqlglot WARN-mode partial trees — a table-qualified column in an INSERT
      list shipped as `INSERT … DEFAULT VALUES` with the guarded SELECT gone;
      now parses with RAISE and degrades to an honest carrier (also catches
      mangled source fragments — N3 evidence). (2) The Oracle batch splitter
      treated a lone `/` (and directives) as structural inside `/* */` block
      comments, desyncing into orphan `*/ …` batches. (3) `emit_node(RawSQL)`
      embedded multi-line sqlglot error text after `-- UNIQUE:`, leaking its
      tail (unbalanced quote incl.) as executable output. Probes in
      `test_embedded_dml_ir.py` + `test_batch_splitter.py`; re-audit: 0
      losses on all 9 fixture×target pairs; test.sql→PG back at 100.0%.
- [x] **N3 (fixed 2026-07-10): `validate_source` false negatives → silent
      garbage.** A bare top-level `exp.Alias` (`banana banana`) is now
      flagged like the other non-statements, and a `CREATE` that fell back
      to an opaque Command is checked against a known object-kind allowlist
      (`CREATE TALBE` → "unrecognized CREATE object kind"; real unmodeled
      kinds like SYNONYM stay clean). Transpile-side, the parse-RAISE change
      (2026-07-09) already degrades such fragments to carriers. Tests:
      `TestBareAndTypoStatements`.
- [x] **N5 (fixed 2026-07-09): false-positive warning on a successful guard
      round-trip** — the blanket T-SQL FOR-loop warning is gone; degraded
      paths carry `-- UNIQUE:` markers that the reconciliation surfaces
      exactly when they fire. Test: `TestNoFalseGuardWarning`.
- [x] **N6 (fixed 2026-07-09):** `/api/v1/validate` and `/api/v1/detect` now
      enforce `MAX_SQL_BYTES` like `/transpile`. Test:
      `TestValidateDetectSizeCap`.
- [x] **N8 (fixed 2026-07-09): near-duplicate `unsupported` entries** — the
      reconciliation now skips carrier fragments already covered by an
      existing entry (3-word-shingle test). Test:
      `TestUnsupportedDeduplication`.
- [x] **N4/N9: docs drift (closed 2026-07-09)** — STATUS.md's guard-round-trip
      claim was corrected (unit tests, not FE); the project-overview skill
      says Python 3.13 and shows `converter/` as a package; README gained the
      "`latest` publishes only on release tags" note in the docs pass. The
      "map Unique's own emitted catalog guard back to the target catalog"
      idea moved into the *Faithful conditional for unmappable catalog
      guards* P2 item above.


### From: P0 — architecture plan (audit doc 04 — ADOPTED 2026-07-08)

- [x] **Decide on the architecture proposals in
      [`audit/2026-07-08/04-architecture-analysis.md`](../audit/2026-07-08/04-architecture-analysis.md)**
      — adopted as proposed (P1 honesty gate, P2 comment trivia, P3 unified
      AST guard path, P4 embedded DML through the IR pipeline, P5
      validity-ratchet process, P6 per-direction tiering; sequencing M0–M4).
      Binding rules encoded in `skills/SKILL-development-workflow.md`
      ("Architecture guardrails", "Detect the wrong path"). The item-level
      bugs below are *instances* of those root causes — fix the classes
      (P2/P3/P4), not the instances one by one.
- [x] **M0 — productize the validity sweep** (`scripts/validity_sweep.py`) —
      done: transpiles a file to each target, executes per-statement on the
      live engines (PG savepoints, MySQL throwaway database, SQL Server
      `SET PARSEONLY ON`, Oracle throwaway schema), classifies
      syntax-vs-expected per engine error code, reports per-direction validity
      % + top error groups with samples. E1 fixed on the way: the statement
      splitters were consolidated into ONE shared string/comment-aware module
      (`tests/helpers/sql_split.py`, 13 unit tests) used by the FE engine
      runner, the live validators and the sweep — the old duplicated splitters
      (which split on `;` inside string literals) are gone. Tests:
      `tests/unit/helpers/test_sql_split.py`,
      `test_validity_sweep_classify.py`. Baselines (private corpus, empty
      DBs): pre-gate Oracle→T-SQL 71%, Oracle→PG 56%; **post-M1**:
      T-SQL→{PG 99.9%, MySQL 98.6%, Oracle 99.6%}, Oracle→{T-SQL 94.0%,
      MySQL 75.0%, PG 73.1%}.
- [x] **M1 — honesty gate** (`src/unique/core/output_gate.py`) — done:
      (a) plain DML/DDL output that doesn't parse under sqlglot in the target
      dialect degrades to a carrier (original source preserved) + a
      `validity_gate` warning + an `unsupported` entry; (b) ALL output is
      scanned outside comments/strings for source-dialect leftovers
      (ROWNUM/VARCHAR2/EXECUTE IMMEDIATE off Oracle, GETDATE/brackets off
      T-SQL, backticks off MySQL, stray GO / `/` terminators) and degrades
      whole on a hit — this catches invalid procedural units sqlglot can't
      judge; (c) duplicate warnings aggregate into one entry with an `(xN)`
      count. The splitter moved into the product
      (`unique/core/sql_split.py`) to support the gate. Tests:
      `tests/unit/core/test_output_gate.py` (17); full suite green with the
      gate active — zero false degradations on the curated corpus.
      *M1 residue resolved in M2:* the SET_OPTION fallback now labels
      non-SET batches honestly (feature=unhandled_batch + unsupported).
      Still open: fragment-level desync (D9) is only caught when a leftover
      token appears in the fragment.
- [x] **M2 — P2 comment trivia + P3 unified guard path** — done (clears the
      guard family: N1, N10, A1–A5). One shared `split_leading_trivia`
      (`unique/core/sql_split.py`) feeds the classifier, the guard matchers,
      `_oracle_needs_slash` and the fallback labels; the three per-spelling
      guard regexes collapsed into ONE `_extract_catalog_guard` (polarity +
      inner-trivia aware, BEGIN…END unwrap, OBJECT_ID arity-proof); non-catalog
      IF guards route to the procedural engine with or without BEGIN (N1);
      catalog CREATE-guards keep their idempotent intent per target
      (`_guard_idempotent`: Oracle probe, PG/MySQL native IF NOT EXISTS, MySQL
      index warned); NEWID/UUID maps per target inside procedural bodies via
      the shared `UUID_FUNCTION` table (A4). Tests:
      `tests/unit/core/test_guard_translation.py` (40, combinatorial neighbor
      matrix). Measured 2026-07-10 (post C1–C4 wave): **test.sql AND
      test2.sql at 100.0% on PG, MySQL and Oracle**.
- [x] **M4 — Oracle-source bring-up — ✅ COMPLETE 2026-07-11.** Official
      validity_sweep at `7c1cea7` on the 13 MB dump (35k+ statements per
      direction): **oracle→T-SQL 0 syntax failures, oracle→PostgreSQL 0,
      oracle→MySQL 0 — 100.0% on all three** (from 475/41/121 at the
      start of the bring-up). Driven by the sweep frequency table
      (doc 03 §D backlog). ***Official sweep 2026-07-11 at `8f6e4a0` (post
      waves 15a–15f): T-SQL 99.9% (48), PostgreSQL 100.0% (10), MySQL
      100.0% (0 — the whole 18-class residue cleared).*** Residue
      classification (2026-07-11, from the sweep dumps): **(P1, silent
      corruption, all targets)** the PL/SQL CASE-*statement*→IF-chain
      rewrite joins the condition onto one line WITH inline `--` comments
      that sat between the CASE selector and `WHEN`, so the comment
      swallows `= 'x' THEN` (`IF v --comment = 'U' THEN`) — same trivia
      class as commit 9474f55 but in the CASE→IF path; accounts for the
      2x tsql-4145 and at least 1 PG fail. **(P1)** 2x PG `INSERT …
      (cols) DEFAULT VALUES` — the partial-parse corruption signature
      shipped (guard leak). **tsql 48:** ~15x error 195 — unqualified
      scalar-UDF calls; T-SQL *requires* `dbo.fn()` (the old "resolves on
      the real DB" assumption was wrong — error 195 fires even when the
      function exists), so qualify unknown functions with `dbo.`; plus
      unmapped scalars in raw/procedural contexts (EXTRACT→DATEPART,
      2-arg TRUNC→ROUND(x,d,1), TO_NUMBER, RPAD, EMPTY_BLOB); 2x
      duplicate `@x` declarations (134), 2x `@new` / `@@…` variable edges,
      date-literal + @dosis1 + misc 102s. **PG 10:** 2x ADD COLUMNS (a,b)
      → per-column ADD, 2x RAW(16) DEFAULT SYS_GUID() → `BYTEA DEFAULT
      gen_random_uuid()` type mismatch, missing-THEN edge, `X record`
      placement edge. ***Official sweep 2026-07-11 at `857b515` (post
      waves 16–18b): PostgreSQL 100.0% (0 — ZERO), MySQL 100.0% (0),
      T-SQL 100.0% (13 — 0.04%)*** — from 475/41/121 when M4 started.
      Waves 17a–18b closed: formatted TO_DATE/TO_CHAR (style table +
      FORMAT via the shared token model), RAW(16) GUID defaults on PG,
      embedded ALTER through the IR passthrough (`ADD COLUMNS` fixed),
      nested-block loop-record hoisting (shared _split_declarations),
      SYSDATE() empty-parens retry, case-insensitive var rename,
      cursor %FOUND/%NOTFOUND on T-SQL, %ROWTYPE loop-var double-@,
      loop-DECLARE dedupe per batch, raw RPAD/LPAD, bare RETURN in PG
      trigger functions → NEW/NULL, and incomplete T-SQL trigger
      conversions (NEW./OLD. leftovers) now degrade honestly via the
      gate. **2026-07-11 waves 19–19b** (official sweep at `638231e`):
      aliased single-table UPDATEs (5x — T-SQL's `UPDATE alias … FROM t
      alias` form + the trigger rewriter renormalizes it), ROWNUM = 1 →
      TOP 1, ROWNUM added to the tsql gate deny-list, quoted dateparts
      (`DATEDIFF('Y',…)`), parameterless CREATE FUNCTION parens.
      ***Waves 20–21 (2026-07-11, official sweep at `b19e03a`): T-SQL
      100.0% (3), PostgreSQL 0, MySQL 0.*** Closed: boolean-var IF/WHILE
      conditions (`= 1`), param-shadowing locals dropped, DISTINCT hoist
      in assignment-selects, **Oracle q-quoted literals** (`q'[…]'` —
      lexer feature; exposed that constant-EXECUTE-IMMEDIATE routine DDL
      must STAY dynamic, now warned), 2-arg SUBSTR with sign-aware start
      (balanced-paren scanner), and the `p_x`/`v_p_x` prefix-strip rename
      collision (error 134 + a silent aliasing risk). **The final 3 are
      ONE class:** scalar calls inside sqlglot-emitted MERGE passthrough
      text (DATEVALUE→dbo., 1-arg TO_CHAR, REGEXP_LIKE) — the shared
      function decisions (mappings + qualifier) never see passthrough
      output; run the tsql scalar pass + string-aware qualifier over
      MERGE passthrough text for the tsql target (REGEXP_LIKE itself has
      no SQL Server 2022 form — document as a visible limitation).* *Wave 16 landed
      2026-07-11:*
      the trivia class fix (`_flat_value` — every flattening capture, CASE
      selector/WHEN included), the parenthesized/UNION INSERT-body drop
      (silent DEFAULT VALUES corruption), structural `dbo.` qualification
      of scalar-UDF calls (error 195 — the "resolves on the real DB"
      assumption was wrong), and the scalar wave (EXTRACT→DATEPART,
      TRUNC(n,d), LPAD/RPAD via exp.Pad, EMPTY_BLOB/CLOB, TO_NUMBER /
      1-arg TO_CHAR/TO_DATE argument-aware — the old name renames emitted
      CONVERT/CAST missing the type argument). *Earlier waves:* Waves 13–14: derived-table aliases synthesized
      for every non-Oracle target (a shared cause across all three) +
      T-SQL's no-TOP ORDER BY dropped inside them; seq.NEXTVAL/CURRVAL;
      the cursor FOR-loop expansion completes for aliased expressions
      (COUNT(*) TOTAL) with the inline form's parens stripped
      (live-validated idempotent); anonymous-block CURSOR declarations
      hoisted into the DO $$ DECLARE section; the CLOB→VARCHAR(MAX) map no
      longer crashes the batch; oversized (N)VARCHAR caps to (MAX). Waves 11–12 added: the shared ALTER ... MODIFY
      rewriter (neither Oracle form parses in sqlglot), user_tab_cols →
      sys.columns / information_schema probes (case-folded on PG — a
      semantic fix, the guards never fired), ALTER TRIGGER ENABLE via
      catalog lookups, named-association LHS protected from the variable
      rename (EXEC p @@id = @id), EXEC expression-arguments hoisted
      (GETDATE() is not a valid EXEC argument — whole seeding batches), and
      the ROWNUM→TOP derived table aliased (T-SQL requires it). Wave 10 added: the sqlglot index NULLS-ordering
      CASE emulation stripped (25x — a T-SQL index key cannot be an
      expression), multi-column `ALTER ... DROP (a, b)` normalized per
      target, MYSQL_ERRNO magnitudes (Oracle's -20xxx codes, 20x),
      PIPELINED table functions preserved as documented carriers, bare
      VARBINARY sized in passthrough DDL, standalone-DML scalars on T-SQL
      (CHR/TO_NUMBER/MONTHS_BETWEEN), PG reserved column names and the
      top-level no-op leak. The waves: exception-scope folding (T-SQL
      TRY / MySQL handler blocks, NOT FOUND for NO_DATA_FOUND), trigger
      `UPDATE OF`/`WHEN` headers, event predicates (TG_OP / per-variant
      constants / ELSEIF), pseudo-row `INTO :NEW.col` targets, the PL/SQL
      CASE *statement* → IF chain, constant `EXECUTE IMMEDIATE` unwrap,
      Oracle-style `DROP INDEX` via a sys.indexes lookup, `user_*` catalog
      probes → `sys.*`, `SQL%ROWCOUNT`/`MONTHS_BETWEEN`/CHR/TRUNC/base
      builtins on T-SQL, unsized VARCHAR sizing, ref-cursor OUT params →
      direct result sets on T-SQL/MySQL, PG row-loop record declarations
      (+ shadowed-name rename), CALL-arg renames/pseudo-records, and the
      partial-parse corruption guard (INSERT → DEFAULT VALUES signature).
      Probes: `tests/integration/test_oracle_source_m4_wave.py` (23).
      Note: the T-SQL count is *flat vs. the morning's 127 but far more
      honest* — unwrapping constant dynamic SQL surfaced ~30 failures that
      previously hid as runtime missing-object noise inside EXEC() strings.
      *Remaining (tsql 54):* dominated by ~12 client-DB-resident UDFs
      (SVF_* — genuinely unresolvable without --db-url metadata; on the
      real target DB they resolve), PL/SQL collections (ARRAYTIPOALTA),
      and 2x edges (4145 non-boolean IF, 128, @dosis1, date literal,
      TO_NUMBER-in-raw). PG 10 — RETURN edges, ADD COLUMNS(...),
      2x bytea/uuid defaults. **MySQL 18 classified 2026-07-10** (dump hook +
      per-statement re-run against MySQL 8.4 for exact near-tokens):
      (a) 3x `MANUAL` is a *new reserved word in MySQL 8.4* — plain INSERT
      column lists need backtick-quoting (same class as the wave-10 PG
      reserved-column fix, MySQL table was stale); (b) 2x space between a
      special-grammar function and `(` — `EXTRACT ( YEAR FROM x)` does not
      parse (empirically: `SUM ( x )` fine, `EXTRACT ( … )` 1064) — raw-token
      join must not pad the paren; (c) 2x named-cursor FOR loop expansion:
      `DECLARE rowX_cur CURSOR FOR curES` is invalid (a MySQL cursor cannot
      alias another cursor — drive the named cursor directly), the scaffold
      `FETCH INTO /* col1… */` stays unresolved though every select-list item
      is aliased, and the DECLAREs land mid-body (MySQL wants them at block
      head — wrap the expansion in a nested BEGIN…END); (d) 2x bare `RETURN;`
      inside procedure/trigger handlers (only functions may RETURN — needs a
      labeled block + LEAVE); (e) 4x parser token-soup on unmappable PL/SQL
      declarations (`TYPE t IS VARRAY(n) OF …`, `RETURN pkg.col%TYPE`, REF
      CURSOR-returning functions) emitted as `DECLARE . LONGTEXT;` fragments —
      violates "a desynced unit degrades whole"; (f) 1x `DECLARE PRAGMA
      AUTONOMOUS_TRANSACTION` leak + `GROUP_CONCAT(… SEPARATOR CHR(13)||…)
      WITHIN GROUP (…)` (LISTAGG lowering must fold a constant separator to a
      literal and move ORDER BY inside); (g) 1x `EXECUTE … USING V_LOCAL` —
      MySQL prepared statements only bind session `@vars` (hoist args), and
      the constant `'BEGIN p(:1…); END;'` should unwrap to a direct CALL;
      (h) 1x `DROP SEQUENCE IF EXISTS` shipped raw (no MySQL sequences);
      (i) 1x `CREATE FUNCTION NOW()` — collides with the built-in, unmappable
      without renaming call sites. Silent-corruption findings from the same
      dump (parse-valid, wrong semantics — no-silent-loss violations to fix
      with the wave): Oracle `||` reaching MySQL raw expressions parses as
      logical OR (loop bodies, RETURN concat, SET assignments); numeric
      `+ 1` emitted as `CONCAT(…, 1)` / `|| 1`; `TRUNC(date)` emitted as
      1-arg `TRUNCATE` (grammar error) instead of `DATE()`; 3-arg
      `DATEDIFF('S',…)` instead of `TIMESTAMPDIFF`.
      Note: the compose `stop_grace_period: 30s` for mssql applies on the
      next `up -d` (containers keep their creation-time config).

- [x] **Faithful conditional for unmappable catalog guards (P2)** (done
      2026-07-10 for the sys.columns/syscolumns column-probe family, both
      polarities, `default_object_id <> 0` included): PG gets a `DO $$ IF
      [NOT] EXISTS(information_schema.columns …)` block, Oracle a
      `user_tab_columns` COUNT probe (+ `default_length` for the default
      predicate — `data_default` is a LONG) with EXECUTE IMMEDIATE;
      live-validated idempotent on both engines. Unrecognized predicates and
      MySQL (no anonymous blocks) keep the explicit `guard_dropped` warning.
      Tests: `TestFaithfulColumnProbeGuard`. Original text:** A T-SQL
      guard whose body has no native conditional form (e.g. `IF NOT EXISTS
      (SELECT … FROM sys.columns … default_object_id <> 0) ALTER … ADD
      DEFAULT`) currently drops the condition — since 2026-07-09 with an
      explicit `guard_dropped` warning (user report; it was silent). The
      emitted `SET DEFAULT`/`MODIFY` is re-runnable (the guard's main
      purpose) but overwrites an existing different default that T-SQL would
      have preserved. The faithful fix is translating the *condition* to the
      target's catalog (`information_schema.columns.column_default` on
      PG/MySQL, `user_tab_columns.data_default` on Oracle) wrapped in the
      target's conditional block — needs careful identifier-case mapping,
      so it must land with live-validated tests. Related to the N4/N9 note
      about mapping Unique's own emitted guards back.


### From: P1 — private-fixture live sweep (audit doc 03; anonymized repros there)

- [x] **A1/A2: guard batches with a leading comment, or `BEGIN…END`-wrapped
      `IF OBJECT_ID` guards, are commented out wholesale** on every target
      (mislabeled `set_option` warning). Fix the guard extractor to tolerate
      leading comments and unwrap `BEGIN…END`; likely clears N1 too.
- [x] **A3 (fixed in M2): leading comment suppresses the `/` terminator** of the emitted
      Oracle guard block — every following statement is swallowed in SQL*Plus.
- [x] **D3 (fixed in M3a): `INSERT … SELECT … FROM DUAL WHERE NOT EXISTS(…)` keeps
      `FROM DUAL`** on PG/T-SQL (~6,000× in the real Oracle dump). Root cause
      was transform-pass recursion stopping at top-level SELECTs; the generic
      recursion + the embedded-DML IR route fixed both pipelines. Probes in
      `test_embedded_dml_ir.py` (standalone + procedural, + scalar-subquery
      and IN-subquery neighbors).
- [x] **D1 (fixed in M4 bring-up, 2026-07-09): Oracle `EXEC proc` → `EXEC AS proc`**
      on every target (T-SQL impersonation syntax; PG/MySQL need `CALL`).
      Mechanism: SQL*Plus `EXEC` has no sqlglot model — it parsed as an
      *alias* and shipped `EXEC AS proc` with the arguments dropped. The
      classifier now routes Oracle `EXEC`/`EXECUTE` batches to the procedural
      engine, whose parser models them as `CallStatement`
      (`_parse_sqlplus_exec_call`; `EXECUTE IMMEDIATE` unaffected) and each
      target emits its call form. Probes:
      `tests/integration/test_exec_call_translation.py` (9, incl.
      args-never-dropped on all targets).
- [x] **SQL*Plus `SET` directives shipped raw (fixed in M4 bring-up, 2026-07-09)** —
      `SET SERVEROUTPUT ON` etc. (~940 invalid statements per direction on the
      real dump) are line-oriented client commands with no `;`, so they also
      glued to the following block and corrupted it. The Oracle splitter now
      peels a known-option directive line into its own SET_OPTION batch (at a
      statement boundary only — an UPDATE's `SET` clause is untouched), the
      SET_OPTION path comments it with a warning for oracle→X, and real SQL
      `SET TRANSACTION`/`SET CONSTRAINTS` now flows as `exp.Set` passthrough
      (it used to be misclassified as a session option). Tests:
      `test_batch_splitter.py::TestSqlPlusSetDirectives`,
      `tests/integration/test_sqlplus_directives.py`.
- [x] **D2 (fixed in M4 bring-up, 2026-07-09): top-level `DECLARE…BEGIN…END` keeps
      its PL/SQL skeleton in T-SQL** instead of flattening to `DECLARE @x…;
      <statements>`. The T-SQL emitter inherited the base's Oracle-style
      anonymous-block shell; it now overrides `_emit_anonymous_block` and
      flattens (a T-SQL batch *is* the block; ~500 statements on the dump).
      Tests: `tests/integration/test_anonymous_block_tsql.py`.
- [x] **D8 (fixed in M3b): silent expression corruption in procedural embedded DML** —
      `MAX(NVL(x,0)) + 1` loses `, 0))` and `+ 1` on T-SQL, and numeric `+`
      becomes `||` on PG. Mechanism: the T-SQL SELECT-INTO emitter split the
      select list with a naive `split(",")`, cutting inside the function call.
      Fixed with the shared paren/string-aware `split_top_level_commas`
      (`unique/core/sql_split.py`); embedded-DML `+` now flows through the IR
      (M3a). Probes + oracle→tsql→oracle round-trip in
      `test_embedded_dml_ir.py`.
- [x] **C1 (verified closed 2026-07-10): mid-body scalar `DECLARE @x t =
      expr`** — hoisted recursively (nested blocks included) with the
      initializer left in place as an assignment; covered by
      `_split_declarations`' pull_nested pass.
- [x] **B1 (fixed 2026-07-09): `PRIMARY KEY CLUSTERED (col ASC)`** — the
      `ADD CONSTRAINT … PRIMARY KEY/UNIQUE CLUSTERED (…) WITH (…) ON [grp]`
      shape is rebuilt directly per target (`_tsql_add_key_constraint`);
      sqlglot mangled it into comma-joined actions that SHIPPED inside
      Oracle guards. Tests: B1 pair in `test_ddl_rename_dropindex.py`.
- [x] **B2 (fixed 2026-07-09): `DROP INDEX` untranslated across the matrix** (PG
      3-part name, MySQL missing `ON tbl`, table name dropped from the `ON`
      form). `DropStatement` now carries `on_table` (from T-SQL's `ON tbl` or
      the legacy `tbl.ix` qualifier); T-SQL/MySQL emit `… ON tbl` (MySQL
      without `IF EXISTS`, which it lacks), Oracle/PG emit the bare index
      name, and a required-but-unknown table degrades to a documented
      carrier. Tests: `tests/integration/test_ddl_rename_dropindex.py`.
- [x] **C5 (fixed in M4 bring-up, 2026-07-09): MySQL `CALL` emitted with named
      arguments** (`name => v`), unsupported by MySQL — now lowered to
      positional by the MySQL transformer with a warning (argument order must
      match the declaration). Same change wave: the lexer now emits `=>` as
      ONE token (it split into `= >`, breaking PG/Oracle output too), and the
      T-SQL emitter spells named association as `@name = value`. Tests:
      `test_exec_call_translation.py` (named-arg trio).
- [x] **D9 (fixed 2026-07-09): `create or replace⏎PROCEDURE` (split lines +
      `-- <codegen>` header comment) desyncs the procedural parser**,
      spilling declaration fragments as top-level batches. Two mechanisms:
      the splitter's PL/SQL-head regex was line-bound (now matches over a
      3-line window), and a top-level anonymous block's `DECLARE` was parsed
      as ONE declaration instead of a section up to `BEGIN` (now mirrors
      `_parse_plsql_body`). Measured: Oracle→PG syntax failures 268 → **39**
      (99.9% validity). Tests: `TestOracleSplitLineCreateHeader`,
      `test_declare_section_with_multiple_declarations`.
- [x] **P1 (fixed 2026-07-09): faithful T-SQL expansion of named-cursor FOR
      loops** — declarations emit the classic un-@ form and record their
      query; a loop over a named cursor drives it directly with one
      `@<var>_<col>` per resolvable select-list column, positional FETCH
      INTO, and `rec.col` → `@rec_col` body rewriting (documented scaffold
      only for unresolvable lists). Follow-ups landed the same day:
      `EXECUTE IMMEDIATE … INTO` captured per target (T-SQL `INSERT … EXEC`
      into a table variable) and `||` → `+` in T-SQL raw expressions.
      Final dump measurement: **T-SQL 99.6% / PG 99.9% / MySQL 99.6%**.
      Remaining T-SQL classes (127): TRY fragments in flattened blocks,
      subquery ORDER BY (error 1033), ~21 near-`)`.
- [x] **C2/C3/C4 (closed 2026-07-10, sweep-closing wave): MySQL routine
      bodies** — the whole class fell out of the semicolon-less boundary
      fixes plus per-target lowering: cursor options consumed on DECLARE
      CURSOR; OPEN/FETCH/CLOSE/DEALLOCATE parsed as cursor ops (were sqlglot
      `OPEN AS c` aliases); `@@FETCH_STATUS` loops per target (PG FOUND,
      Oracle `%FOUND`, MySQL done-flag + NOT FOUND handler); assignment-select
      stops at bare `ELSE`; IF conditions stop at statement verbs
      (ROLLBACK/COMMIT/DECLARE/…); MERGE actions chain after `THEN` and route
      through the IR (mysql upsert, Oracle `ON (…)`, non-canonical → warned
      carrier); CTE assignment-select → `WITH … SELECT INTO`; updatable-CTE
      DML → warned carrier (was silent CTE drop); parenthesized FROM join
      trees passthrough (were a silent whole-FROM loss); base64-XML idiom,
      ERROR_MESSAGE()/RAISERROR(@var), VARBINARY(MAX), table hints in raw
      conditions, DROP INDEX guard per target, nested table-variable GTT
      hoist, MySQL `NULL;`→`DO 0;`. **Measured 2026-07-10: test.sql AND
      test2.sql at 100.0% validity on all three targets.** Tests:
      `tests/integration/test_test2_residue_wave.py` (28) +
      `test_cursor_variable_binding.py` (6).
- [x] **D5/D6/D7 (fixed 2026-07-09): Oracle→T-SQL passthroughs** — D5:
      `RENAME COLUMN` → `EXEC sp_rename` (T-SQL only; PG/MySQL 8 native).
      D6: `INSERTING`/`DELETING`/`UPDATING['(col)']` → the T-SQL
      inserted/deleted EXISTS idiom / `UPDATE(col)`, and the row→statement
      trigger conversion recurses into `IF` bodies (a NEW/OLD condition
      folds into the inserted-rows subquery). D7: `TRUNC(date)` →
      `CAST(x AS DATE)` (T-SQL), `DATE_TRUNC('day',…)` (PG), `DATE(x)`
      (MySQL). Tests: `test_ddl_rename_dropindex.py`,
      `test_trigger_predicates_scheduler.py`.
- [x] **B3 (fixed 2026-07-09): named DEFAULT constraints** (T-SQL-only)
      dropped on every other target with a per-name note/warning.
- [x] **B4 (verified fixed 2026-07-09): bare `RETURN` eats the next line's
      comment** — no longer reproduces; pinned by
      `test_comment_after_bare_return_survives`.
- [x] **D10 (fixed 2026-07-09): `DBMS_SCHEDULER.CREATE_JOB` → raw `CALL` on
      PG** — Oracle built-in package calls (`DBMS_*`, `UTL_*`, …) now degrade
      to a documented carrier + warning + no-op off Oracle.
- [x] **E1 (harness): `_split_mysql_statements` splits on `;` inside string
      literals** — fixed via the shared `tests/helpers/sql_split.py` (see M0);
      all live splitting is now string/comment-aware, incl. MySQL backslash
      escapes and a BEGIN/END word-boundary fix.


### From: P3 — hardening carry-overs (from 2026-07-02, still open)

- [x] **CI: fail when fewer engines than expected were exercised** (done
      2026-07-10) — a gating "all four engines reachable" step in
      `syntax-live` fails the job before the live suites run; the waits stay
      `continue-on-error` for readable logs but can no longer shrink the
      validation silently.
- [x] **Identity-mutation floor raised 0.33 → 0.40 → 0.45** (2026-07-11;
      measured 0.49 after the M4-closing and M3-prereq waves). Next
      ratchet as `test_cross_dialect.py` survivors harden.
- [x] **Docker digest pin + constraints file** (done 2026-07-10): both
      Dockerfiles pin `python:3.13-slim` by sha256 digest and the runtime
      install applies `constraints.txt` (full dependency closure) — image
      build verified locally. A5 (`X-Unique-Decoded-As`) and N7 (filename
      stem sanitize) shipped the same day.


### From: Continuously tracked (not a discrete backlog)

- [x] **Nightly mutation floors under water since 2026-07-09 — RECOVERED
  2026-07-16** (nightly run at `17de248` green: all floors passing with
  the wave-file selections + survivor-targeted assertions). Original
  finding (P2; user flagged 2026-07-15): convert.py 60% < 65, emit.py 53% < 60,
  procedural base.py 51% < 52. Root cause: the M-era + wave code landed
  with its tests in `tests/integration/test_pg_source_wave1.py`, which
  the nightly's `--tests` selections did NOT include — every mutant in
  the new paths survived by construction. Fixed the selection (wave
  file added to BOTH mutation steps, 2026-07-15; local 60-mutant sample
  on emit.py: 53%→58%). Validation dispatch (2026-07-15 evening):
  convert.py recovered its floor; emit.py 56% and procedural base.py 51%
  still short → survivor-targeted assertions added
  (`test_emit_mutation_survivors.py`: CTE-DML gate branches, index-
  rebuild decisions, per-target DEFAULT rewrites;
  `test_transformer_survivors.py`: trigger timing/delegation/UPDATE-OF
  decisions). Local 80–100-mutant samples after: emit.py 65% (floor
  60), base.py 61% (floor 52). Second validation dispatch pending —
  possible live-check item spotted on the way: MySQL `DEFAULT UUID()`
  emits WITHOUT the parens MySQL requires for function defaults
  (verify against live MySQL; the `(UUID())` rewrite exists but a
  different path emits).
- **Test-assertion quality** is measured by the nightly mutation job
  (`mutation.yml` / `scripts/mutation_test.py`) rather than a static to-do list:
  surviving mutants in its run summary are the live map of weakest assertions.
  Strengthen them opportunistically (the biggest foci at last measure were
  `emit._emit_function`/`_emit_date_diff` and `transformer._replace_oracle_date_add`).
  Differential result testing (`test_corpus_results_live.py`) guards against
  semantic regressions on every syntax-live CI run.


