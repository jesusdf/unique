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

---

## 36. Direction-residue campaign — no-silent-loss closed at the architectural floor

Archived from `docs/TODO.md` §2 P1 on 2026-07-17 (closed at the user-declared
floor, HEAD `469917a`). The full per-wave log follows verbatim, then the floor
declaration.

- [x] **Residual invalid output ships WITHOUT a warning (P1, analyzed
      2026-07-17).** The archived wave campaign left ~550 statements
      across the six directions that the live engines reject; behavior
      audit of pg→tsql's 163: **21 are VERBATIM passthroughs of the
      source SQL with ZERO warnings** (e.g. `SELECT CORR(b, a)` — CORR
      is a known-foreign builtin deliberately left visible, but
      silently; `ALTER TABLE … SET (parallel_workers = 4)` — a PG
      storage knob shipped raw), and 142 are transformed-but-invalid
      forms that pass the sqlglot-based output gate because sqlglot is
      more lenient than the real engines. Neither violates data, but
      both violate the no-silent-loss policy: invalid output must
      carry a warning or degrade to a carrier. **Treatment design
      (three mechanisms, ordered by cost):**
      1. *Unmapped-construct note (LANDED 2026-07-17, wave 103):*
         a RawSQL whose reason is `unmapped operator X` emitted
         cross-dialect now carries an inline `/* UNIQUE: … no
         <target> mapping — review */` note (covers CORR & friends —
         they arrive as unmapped-operator RawSQL, not FunctionCall).
         A FunctionCall-level note was tried and REVERTED: it broke
         the downstream text handlers that consume that output
         (TRUNC→ROUND on the M4 path) — the M3 lesson; rewrite passes
         that fix a construct must also CLEAR the stale reason
         (charset strip updated). Tests: TestForeignBuiltinNote. Verified at
         `fd2923f`: validity identical {163/131/89}, notes visible
         in output. Mechanisms 2–3 below remain open.
      2. *Verbatim-fallback warning — VERIFIED ALREADY COVERED
         (2026-07-17):* the DML parse-fallback path already carriers
         + warns (probe: `SELECT 1 INTO STRICT v` → carrier with
         warning). The probe instead exposed a silent-MANGLE class:
         PG's `TABLE name` shorthand shipped as `[TABLE] AS onek`
         (wave 104 fixed it — pre-normalized to `SELECT * FROM
         name`). The remaining silent classes are all
         sqlglot-leniency escapes → mechanism 3. (Wave 104 verified
         at `b400247`: validity flat, mangle gone.)
      3. *Live output validation, opt-in — LANDED 2026-07-17
         (wave 105):* `TranspileOptions.validate_live_url` +
         `core/live_validate.py`. Side-effect free per engine (T-SQL
         PARSEONLY, PG savepoints, MySQL throwaway DB; Oracle raises
         UnsupportedLiveValidationError — no side-effect-free channel
         without DBA rights). Applies the SWEEP'S classification:
         only syntax-class engine errors degrade (environmental
         missing-table errors on the validation DB must not carrier
         good SQL). Smoke-verified against live PG: syntax rejects
         carrier with the engine's error + a `live_validation`
         warning; environmental pass untouched. Oracle channel via
         `DBMS_SQL.PARSE` (syntax+semantics, no execute) added
         2026-07-17 — DML/SELECT only; DDL skipped (Oracle runs DDL
         at parse). **BLIND SPOT (user, 2026-07-17): live validation
         catches INVALID output, NOT silent data loss — a statement
         that dropped a clause/arm/row but stays syntactically valid
         PASSES (wave 85 class). It is NEVER the sole check; it
         complements the no-silent-loss gates, differential audits,
         and review of what each degrade drops.** Tests:
         TestLiveOutputValidation (env-gated). **Live-in-sweep gap
         discovery (user, 2026-07-17): a discovery script ran the
         corpus through the Transpiler + live PG validation, keeping
         only statements the ENGINE rejects that shipped with NO
         carrier/warning — 58 silent gaps. Top: `CAST(… AS ARRAY)`
         (11x — a PG array-type cast `'{…}'::float8[]` collapsed to
         a bare ARRAY, invalid even PG→PG; wave 106 preserves the
         array type and widens the array gate to Oracle, excluding
         WITHIN GROUP which Oracle supports). The discovery tool is committed
         (`scripts/discover_silent_gaps.py`) — MUST use the
         dollar-quote-aware splitter (a naive `;\n` split shreds
         plpgsql bodies into false-positive `return …` fragments —
         verified). Proper run over the whole corpus (5196 stmts):
         **287 silent gaps**. Wave 107 fixed the worst — a genuine
         SILENT DATA LOSS the live check exposed: `CREATE TABLE x
         (LIKE y)` (LIKE inside the column parens) dropped its LIKE
         entirely → empty `CREATE TABLE x` (the LikeProperty lands in
         the schema, not properties; now harvested from both).
         Remaining tail: `ARRAY(...)` constructor (9x, distinct from
         the cast), VARIADIC ARRAY, PERCENTILE_*(ARRAY …) — genuine
         array constructs with no non-PG spelling (degrade candidates
         for a future wave). Wave 108 (2026-07-16) closed that tail
         and found it was worse than a degrade gap — the IR had NO
         array model, one class, three defects: (a) sqlglot stores PG
         subscripts 0-BASED and the unhandled-expression RawSQL
         fallback rendered with NO dialect, so `arr[2]` shipped as
         `arr[1]` — silent data corruption, and on pg→tsql it even
         passed the validity gate (brackets parse as a quoted
         identifier) with ZERO warnings; (b) `ARRAY[…]` collapsed to a
         generic FunctionCall emitted `ARRAY(1, 2, 3)` — invalid even
         on PG; (c) the ARRAY(SELECT …) carrier leaked the IR repr
         instead of SQL. Fixes: `ArrayLiteral` IR node (PG emits
         `ARRAY[…]`/`ARRAY(SELECT …)` faithfully), ALL converter
         RawSQL fallbacks now render in the SOURCE dialect
         (`_source_sql`: unhandled expr, complex EXISTS/subquery,
         unmodeled INSERT body, unhandled CREATE, unmapped operator),
         and the array gate recognizes the node, subscripts
         (Bracket-RawSQL), and any RawSQL fragment carrying `ARRAY[`
         (neighbor probe caught `= ANY(ARRAY[…])` escaping via the
         unmapped-operator path; a WITHIN GROUP fragment with an
         ARRAY arg now degrades on oracle too, plain WITHIN GROUP
         stays). Tests: TestArrayModelFidelity (18). Measured
         (whole-corpus discovery, working tree over `f3c07d9`):
         **287 → 226 silent gaps (−61)**. Next-wave candidates from
         the new top classes (all silent-loss shapes): set-returning
         function dropped from FROM in LATERAL contexts (`FROM
         generate_series(…) s1` → `FROM  s1`), `DROP TRIGGER … ON
         table` losing the ON clause, CTAS over a parenthesized UNION
         subquery truncating (`syntax error at end of input`, 99x),
         and — verified distinct from this wave's DML class — the
         PROCEDURAL pipeline shreds plpgsql array-typed declares
         pg→pg (`a integer[] = '{…}'` → `a integer;` + garbage `[]
         =;` line; `RETURNS SETOF integer[]` silently narrows to
         `SETOF integer`) — the pg→pg preservation counterpart of
         wave 86's off-PG degrade (6x, the remaining `"["` gaps).
         Wave 108b: the live FE suite caught a wave-108 REGRESSION —
         source-dialect fallback rendering is wrong INSIDE procedural
         bodies, where embedded text is mid-transform (variables
         already `@`-rewritten): a postgres render turned
         `@p_customer_id` into the invalid `$p_customer_id` on
         T-SQL. `IR_EMBEDDED` ContextVar (set around
         `_ir_transpile_dml`) keeps the generic rendering there;
         top-level parses stay source-spelled. All 16 FE pairs
         re-verified live-green. Lesson for the structural list: a
         "render faithfully to the source" rule only holds where the
         text IS source — the procedural pipeline's embedded text is
         a hybrid. Tests: TestEmbeddedFallbackSpelling. Wave 109
         (2026-07-16): `DROP TRIGGER name ON tbl` lost its mandatory
         ON even pg→pg (sqlglot parks it in the unread `cluster` arg
         — the DROP INDEX lesson again); now harvested for TRIGGER
         too, PG emits it, and the inverse neighbor (tsql/mysql/
         oracle sources are schema-scoped, no table to carry)
         degrades to the documented carrier instead of shipping
         invalid PG silently. Known honest limit: `ON schema.tbl`
         doesn't parse in sqlglot (carrier + warning, not silent).
         Tests: TestDropTriggerOnTable (7). Measured: **226 → 156
         silent gaps (−70)** (working tree over `45edfa2`; the
         DROP TRIGGERs were most of the 99x end-of-input class).
         Remaining top classes: FROM-position set-returning function
         dropped (`FROM generate_series(…) g` → `FROM g`, the
         biggest remaining silent DATA LOSS — needs a
         function-relation model in the IR, fresh-session scale),
         psql client-side leftovers (25x near ":"), `WITH ins AS
         (INSERT … RETURNING)` mangled to `SELECT *` (14x), plpgsql
         array-typed declare shred (6x, above). Waves 110–111
         (2026-07-16): the function-relation model landed —
         `TableRef.function` (+`ordinality`) carries the SRF,
         harvested from `Table(this=<func>)` in FROM/JOIN position
         and from bare `Unnest` relations; PG re-emits `fn(args)
         [WITH ORDINALITY] [AS a(c…)]` faithfully; unnest relations
         still degrade off-PG via the array gate (it sees the
         FunctionCall by field recursion); sqlglot's internal
         `ExplodingGenerateSeries` canonicalizes to GENERATE_SERIES.
         Wave 110 alone measured FLAT (157) — green-but-unmoved
         fired: those statements were blocker CHAINS, and preserving
         the SRF exposed the next link — comma-joined LATERAL
         emitted `JOIN LATERAL (…) ss` with NO ON (invalid PG that
         sqlglot's lenient gate passes). Wave 111 spells an
         unconditioned inner lateral `CROSS JOIN LATERAL`. Together:
         **156 → 122 silent gaps (−34)** (working tree over
         `6bbf102`; end-of-input 29→4, near-WHERE class gone).
         Tests: TestFunctionRelations (7), TestCommaLateralJoin.
         Wave 112 (2026-07-16): the procedural lexer tokenized `::`
         as two COLON tokens and the joiner spaced them —
         `relname::text` shipped as the invalid `relname : : text`
         inside converted routine bodies (the 25x near-":" discovery
         class, plus 4x live on the pg→tsql sweep). `::` is now ONE
         OPERATOR token (PG accepts spaced `x :: text`); Oracle
         `:new`/`:old` single-colon refs unaffected. Tests:
         TestDoubleColonCastInBodies. Gate green; **discovery/sweep
         re-measurement PENDING** (host RAM upgrade in progress —
         resume by re-running `scripts/discover_silent_gaps.py`
         [expect ≈122−~25] and the full validity sweeps of BOTH
         corpora, which were last measured at `3fdfc88` wave ~102;
         a pg→tsql sweep at `5aed9ee` ran but its summary was lost
         to a `tail` pipe — DON'T pipe sweep output). MEASURED
         post-upgrade (2026-07-16, 31GiB host, all four engines
         parallel): discovery pg→pg **122 → 98** (−24, the ":"
         class gone as predicted). Full sweeps at `314f7c6`:
         pg-source {tsql **153** (95.4%), mysql 246→see 113, oracle
         **79** (97.5%)}; mysql-source {tsql **171** (97.1%), pg
         **105** (98.3%), oracle **129** (97.8%)} — pg-source beats
         the wave-102 record {163/131/89} across the board;
         mysql→tsql +5 vs record (166), unclassified, likely the
         SRF-honesty class. Wave 113 (2026-07-16): wave 110's
         preserved SRF relations surfaced the target truth — MySQL
         has NO table functions except JSON_TABLE (`FROM
         generate_series(…) g` = hard 1064, 243x, previously hidden
         as an expected-missing bare alias): new
         `_gate_mysql_function_relation` degrades WHOLE with
         carrier+warning (JSON_TABLE keeps its path); Oracle now
         spells a function relation `TABLE(fn(args)) alias`.
         Verified: pg→mysql **121** (96.0%, beats the 131 record);
         pg→oracle flat 79. Tests: TestFunctionRelationTargets.
         Wave 114 (2026-07-16): a data-modifying CTE (`WITH ins AS
         (INSERT … RETURNING) SELECT …`, PG-only) had its DML body
         SHREDDED into a `SELECT *` skeleton by `_convert_cte`
         (silent loss of the INSERT/DELETE itself). Now routed
         through the existing CTE-DML passthrough: preserved pg→pg,
         degraded whole with the documented carrier elsewhere (the
         DML-inside-CTE check runs BEFORE the helper's T-SQL
         early-out, which covers the inverse update-through-CTE
         shape). Measured: discovery **98 → 86** (−12; 'SELECT *
         with no tables' 15→3). Tests: TestDataModifyingCte.
         Wave 115 (2026-07-16): the plpgsql DECLARE parser stopped
         at the first unknown token and SHREDDED the declaration —
         one mechanism, four sub-shapes now consumed: `CONSTANT`
         (kept on PG/Oracle, safe mutable relaxation on T-SQL/MySQL,
         documented in 03-unsupported §1.5), `[NO] SCROLL CURSOR`
         (kept on PG; T-SQL SCROLL native, replaces FAST_FORWARD),
         `[]` array suffixes in DECLARE (via `_parse_pg_data_type`,
         closing the 6x `[` class), and `RETURNS SETOF type[]` no
         longer narrowing (pg-aware inner parse). Measured:
         discovery **86 → 81** (−5: `[` −6 and `data type` −3
         cleared, but the 14x `;` class has ANOTHER sub-mechanism —
         re-sampling — and un-shredded routines exposed new chain
         links: INTO 2→4, 'RETURN cannot have a parameter' 2x).
         Tests: TestPlpgsqlDeclareModifiers (6).
         Wave 116 (2026-07-16): `OPEN c [NO] SCROLL FOR [EXECUTE …]`
         — the OPEN parse stopped at the cursor name, shipping
         `scroll for execute '…';` as an ORPHAN statement.
         CursorOperation gains `scroll`; the dynamic `FOR EXECUTE`
         form is preserved verbatim; PG re-emits both (T-SQL keeps
         scrollability on its DECLARE; Oracle/MySQL forward-only).
         Measured: discovery **81 flat** — the wave's own classes
         cleared ('FOR' 3→0, orphans gone) but chains absorbed the
         delta (INTO 4→7). The 14x ';' class STILL unmoved after two
         waves → two-strikes fired: next step is an end-to-end trace
         of one real tg_* corpus function, not another sub-shape
         guess. Tests: TestOpenCursorScrollExecute (3).
         Wave 117 (2026-07-16): the trace found it first try — the
         tg_* corpus functions declare `myname ALIAS FOR $1;`, which
         shredded into `myname alias;` + orphan `for p1;`. Faithful
         translation on EVERY target: token-level rename of the
         alias to its target (the $n positional-aliasing mechanism);
         the declaration vanishes. Measured: discovery **81 → 78**
         (`;` 14→11 — the rest of that class are further sub-shapes,
         next trace needed). Tests: TestAliasForDeclaration (2).
         Wave 118 (2026-07-16): FETCH directions — `FETCH NEXT|LAST|
         ABSOLUTE n … FROM c INTO x` took the DIRECTION as the cursor
         name (`FETCH next INTO ;` + orphan). A word is a direction
         only when FROM/IN follows, so cursors named `last` still
         work; native re-emit on PG and T-SQL, documented carrier on
         Oracle/MySQL (forward-only). Found+fixed en route: the
         shared `_transform_cursor_op`/`_transform_cursor_decl`
         REBUILT their nodes field-by-field, silently dropping any
         field they didn't know (scroll, direction) — now
         dataclasses.replace; that trap ate wave 116's scroll on
         every transformed route. Measured: discovery **78 → 72**
         (INTO class gone). Sweeps at `63de504`: pg→tsql **145**
         (95.6%), pg→mysql **118** (96.1%), pg→oracle **77** (97.6%).
         Tests: TestFetchDirections (4).
         Wave 119 (2026-07-16): plpgsql's bare re-`RAISE;` emitted the
         invalid `RAISE EXCEPTION '%', ;` and `RAISE USING key = expr`
         mangled — both fell into the generic expression fallback. New
         `reraise` flag (native everywhere: PG/Oracle `RAISE;`, T-SQL
         `THROW;`, MySQL `RESIGNAL;`); USING's `message` option IS the
         message, other options fold into the text. The rebuild trap
         hit AGAIN en route (`_transform_raise_error` dropped the new
         flag) — fixed with dataclasses.replace like wave 118's.
         Measured: discovery **72 → 68** ('missing expression' class
         gone). Tests: TestBareRaiseAndUsing (5).
         Wave 120 (2026-07-16): plpgsql `FOREACH var [SLICE n] IN
         ARRAY expr LOOP … END LOOP` modeled (ForeachStatement):
         preserved pg→pg with a transformed body, documented carrier
         elsewhere (the array-body routine degrade usually fires
         first off-PG). Measured: discovery **68 flat** but the
         composition moved — `;` 11→5 (the FOREACH shreds cleared)
         and `[` REAPPEARED at 5x: un-shredding the loops exposed
         their bodies (array subscripts in plpgsql assignment
         contexts, being re-sampled). Chains, as ever. Tests:
         TestForeachArrayLoop (5). Wave 120b: the '[' 5x was my own
         wave-120 emit (a Python list repr interpolated into the loop
         body — the wave tests only checked header/END LOOP;
         strengthened). 68 → 63. Waves 121–122 (2026-07-16):
         plpgsql's EXECUTE is ALWAYS dynamic (CALL is spelled CALL) —
         the SQL*Plus exec-call fallthrough mangled `EXECUTE 'q' INTO
         STRICT x` into `CALL 'q'();` (8x): new `_parse_pg_dynamic_
         execute` with INTO [STRICT] + USING, PG re-emits natively
         (ExecuteStatement.strict). And a `LANGUAGE C` function
         (`AS '$libdir/…'`) emitted an EMPTY plpgsql function —
         silent loss of the implementation reference: non-SQL-language
         units (C/internal/plperl…) now capture whole
         (`_pg_non_sql_language_ahead` + `_whole_unit_raw`), ship
         VERBATIM same-dialect and carrier+warning cross-dialect (the
         transformer decides — it knows both ends). Measured:
         discovery **63 → 48** (−15). Tests: TestPgDynamicExecute
         (3), TestNonSqlLanguageFunction (4). Wave 123
         (2026-07-16): `SAVEPOINT a` mis-parses in SQLGLOT ITSELF as
         an Alias (`SAVEPOINT AS a` even in its own round-trip) —
         pre-recognized in parse_sql (the `TABLE name` precedent) as
         a PassthroughSQL kind: same spelling on PG/MySQL/Oracle,
         `SAVE TRANSACTION` on T-SQL (+ output-gate reparse exemption
         — sqlglot's tsql reader can't read that valid spelling
         either, the DELETE…OUTPUT lesson). Measured: **48 → 45**.
         Tests: TestSavepointStatement (4). Wave 124 (2026-07-16):
         PG's empty select list (`SELECT;`, zero columns one row)
         silently gained a `*` — invalid without FROM, shape-changing
         with one. `SelectStatement.empty_select_list` flag set only
         for genuinely-empty SOURCE lists (converter-fallback empty
         tuples keep their load-bearing `*` default); PG re-emits the
         bare SELECT, other targets gate to the carrier. Measured:
         **45 → 42**. Tests: TestEmptySelectList (6). Wave 125
         (2026-07-16): PG's TRUNCATE trigger event was unrecognized —
         the whole trigger shredded into garbage declarations.
         Recognized on PG (event list + upper_value, TRUNCATE isn't a
         lexer keyword); degraded whole via `_transform_trigger` on
         targets without the event (the `_degrade_mysql_uservar`
         recipe: re-emit in source + carrier + registry). Measured:
         **42 → 36** (FUNCTION and ON classes cleared). Tests:
         TestTruncateTrigger (4).* Wave 126 (2026-07-16): plpgsql
         `<<label>>` block labels (and their label-qualified variable
         refs) are unmodeled — the declare loop shredded them into
         `< <; label >; >` garbage. Detected BEFORE the body splice
         (the body is still one STRING token there — post-splice the
         label is token soup); verbatim on PG via the wave-122
         whole-unit path, carrier elsewhere. Measured: **36 → 34**
         (`<` class gone). Tests: TestPlpgsqlBlockLabel (4).
         Waves 127–128 (+127b, 2026-07-16): CTE fidelity — RECURSIVE
         and the column list `x(a)` were never harvested (fields
         existed, unset) and a VALUES body mangled to a one-row
         SELECT (now the FROM-relation UNION-chain converter);
         `CREATE TEMP TABLE` lost TEMPORARY even pg→pg (now
         harvested: TEMPORARY on pg/mysql, GLOBAL TEMPORARY on
         oracle, dropped-with-#-semantics note on tsql) and
         zero-column `CREATE TABLE x()` keeps its parens on PG /
         gates elsewhere. 127b: the sweep VERIFICATION caught my own
         regression (145→178 on tsql) — RECURSIVE is REQUIRED on
         pg/mysql and DOESN'T EXIST on tsql/oracle; now per-dialect.
         ALSO fixed the 32GiB OOM (user-reported): the PG validator
         (savepoint+execute) began EXECUTING the perf-test SRFs the
         moment the transpiler stopped breaking them — millions of
         rows buffered client-side; `statement_timeout=3000` in the
         validation session (a canceled statement is not
         syntax-class → no gap). MEASUREMENT POLICY: sequential, max
         2 python processes (the OOM was 4 parallel measurements).
         Measured: discovery **34 → 31** (end-of-input cleared);
         sweeps pg→tsql **132** (96.0%), pg→mysql **109** (96.3%),
         pg→oracle **65** (97.9%). Tests: TestCteFidelity,
         TestTempAndZeroColumnTables, TestRecursiveCtePerDialect.
         Waves 129–130 (2026-07-16): a set arm carrying its own WITH
         lost its parens (`UNION ALL WITH z …` invalid); a
         parenthesized CHAIN arm — `A UNION (B UNION ALL C)` — is now
         SHIELDED as a derived table (flattening RE-ASSOCIATED the
         row set: INTERSECT binds tighter than UNION — an old wave-85
         test had the wrong flat form CONSECRATED and was
         strengthened, not weakened); `..` FOR-ranges are ONE lexer
         token (the `::` twin — shipped `0 . . n`); plpgsql
         `#option` compiler lines go whole-unit (valid PG, shredded
         before). Measured: discovery **31 → 20** (WITH/#/0/UNION
         classes cleared). Tests: TestSetArmWithCte, TestWave130Batch,
         strengthened TestNestedChainMidOrderStrip.
         Wave 131 (2026-07-16), five shapes: VARIADIC is an ARGMODE
         (parsed as the param NAME, every `$1` body alias became
         `variadic`); `NOT NULL` declare modifier (the wave-115
         family, PG/Oracle native + tsql/mysql relaxation);
         a VALUES set-op arm (`(VALUES …) UNION ALL …`) now lowers
         via the relation converter; `TABLE name` with a LEADING
         COMMENT escaped the wave-104 pre-normalization (comments are
         trivia — regex now tolerates them); mapped BIT(n) shipped
         `BOOLEAN(4)` (BOOLEAN never takes params). Measured:
         **20 → 13**. Tests: TestWave131Batch (5). Wave 132
         (2026-07-16): SETOF sql-bodies wrap as `RETURN QUERY …`
         (the scalar `RETURN (…)` is invalid there); PG's `ALTER
         COLUMN SET STORAGE` knob — SQLGLOT'S OWN ROUND-TRIP INVENTS
         a `DROP DEFAULT,` before it — pre-recognized with the
         ORIGINAL text (PassthroughSQL kind "PG STORAGE": verbatim
         PG, carrier elsewhere); a dotted unnamed `%TYPE` parameter
         (`f(tbl.col%type)`) took the table as the param NAME
         (dotted first token ⇒ type-only). Measured: **13 → 9**.
         Tests: TestWave132Batch (6). Remaining 9: nested-DECLARE
         shadowing (2, needs block-local declares), dynamic-OPEN
         FETCH chain (2), WITHIN-GROUP-in-CASE view (1), RAISE USING
         variant (1), `return` as a variable name (1), FOREACH
         multi-target (1), transition tables (1). Wave 133
         (2026-07-16) closed ALL NINE: FILTER over an ordered-set
         aggregate (was a fake `WITHINGROUP(CASE…)` call — now the
         source-rendered RawSQL the gates see); `FETCH RELATIVE -n`
         signs; leveled `RAISE EXCEPTION USING key = v` (helper
         shared with wave 119's level-less form); FOREACH
         comma-targets; and three deep singles via the whole-unit
         path with NARROW body-shape regexes (nested DECLARE block,
         a variable literally named `return` with initializer, CTE
         feeding SELECT INTO — first regex draft broke 44 tests by
         matching plain `return x;`, calibrated). **DISCOVERY
         pg→pg = 0 SILENT GAPS (from 287)** — the fixtures-corpus
         no-silent-loss goal for the discovery channel is COMPLETE:
         every statement transpiles validly or carries a
         warning/carrier. Tests: TestWave133Batch (6). Direction-residue
         campaign opened (wave 134, 2026-07-16): a WITH inside a
         set-operation arm (valid PG/MySQL-8 after wave 129) has no
         T-SQL/Oracle spelling (CTEs are statement-top only) —
         `_gate_nested_cte_arm` degrades whole there. Measured:
         pg→tsql **122 → 118** (96.4%), discovery HOLDS at 0.
         Remaining tsql classes (sweep at `de81b44`): non-boolean
         WHERE 8x, near-SELECT 8x, `,` 7x, `(n.*)` star 5x, OLD
         pseudo-rows 5x, boolean-agg NOT 3x, DECODE 3x, set role 3x,
         AS 3x, OUTPUT-in-function 3x, E-strings 3x.
         Tests: TestNestedCteArmGate (3). Wave 135
         (2026-07-16): PG boolean truthiness under the condition
         TREE — a bare column/function/subquery under AND/OR (and
         `NOT col`) shipped bare to T-SQL/Oracle (4145); only the
         top-of-WHERE case was comparisonized. Extended
         `_comparisonize_literals` + `_emit_condition`. Measured:
         pg→tsql **118 → 116** (96.4%), pg→oracle **65 → 61**
         (98.1%), discovery HOLDS 0. Tests:
         TestBareBooleanConditions (4).* Wave 136 (2026-07-16): the
         nested-CTE gate generalizes to ANY non-top WITH (set arms,
         derived tables, APPLY/lateral subqueries, CTE bodies) —
         with the INSERT-source exemption (that CTE is hoistable and
         the emitter already hoists it; the neighbor probe caught the
         over-fire); and a LATERAL join with a REAL ON condition
         degrades on T-SQL/Oracle (APPLY takes no ON — only the
         ON TRUE form maps). Measured: pg→tsql **116 → 100** (96.9%,
         the deep-CTE gate caught double the sampled class),
         pg→oracle **61 → 59** (98.1%), discovery HOLDS 0. Tests:
         TestWave136LateralAndDeepCte (5).* Wave 137 (2026-07-16): PG row
         constructors in VALUE position (`ELSE (a, b, c)` as a CASE
         result / function arg) degrade off PG — detection is
         deliberately NARROW (Tuple-RawSQL under CASE arms or fn
         args, plus the DISTINCT-wrapped text form where the whole
         arg is one RawSQL): the first draft ate the row-tuple
         COMPARISONS that later passes expand (5 tests fired), and
         `ColumnRef('*')` proved ambiguous (legit `n.*` uses it on
         some paths) — the `(n.*)` composite single stays PENDING
         (needs a Paren(Star) marker at conversion). Measured:
         pg→tsql **100 → 97** (97.0%), discovery HOLDS 0. Tests:
         TestCompositeRowValues (5).* Wave 138 (2026-07-16): a BARE
         whole-row OLD/NEW in a trigger body (`'x' || OLD`) has no
         off-PG equivalent (rows are addressed per column there) —
         the inlined T-SQL trigger shipped `+ OLD` raw. The gate
         scans SCRUBBED text (string contents can't false-positive)
         of the trigger shell PLUS the harvested delegated-function
         body (PG triggers delegate; the shell has no body), with
         exclusions for qualified refs, RETURN NEW/OLD and
         REFERENCING new|old TABLE (4 existing tests fired on the
         draft). Measured: pg→tsql **97 → 92** (97.1%), discovery
         HOLDS 0. Tests: TestBareWholeRowTriggerRef (2).* Wave 139 (2026-07-16): PG's
         BINARY `DECODE(text, 'hex')` (2 args — not Oracle's
         conditional DECODE, which becomes CASE at 3+) maps
         faithfully everywhere: `CONVERT(VARBINARY(MAX), x, 2)`
         tsql, `HEXTORAW` oracle, `UNHEX` mysql; and `SET ROLE`
         (real SQL on PG/MySQL/Oracle) carriers on T-SQL only — in
         the SET_OPTION path (the transformer gate drafted first was
         DEAD CODE for that route; the batch classifier short-
         circuits it). Measured: pg→tsql **92 → 87** (97.3%),
         pg→oracle **59 → 56** (98.2%), pg→mysql **109 → 97**
         (96.7%), discovery HOLDS 0. Tests:
         TestWave139DecodeAndSetRole (5).* Wave 140 (2026-07-16):
         `string_agg(x, NULL)` shipped a nonexistent GROUP_CONCAT on
         T-SQL — a NULL separator concatenates bare (`''`) and an
         EXPRESSION separator now stays the target's own argument
         (both fell through the literal-only branch to generic
         emission); and T-SQL's aliased delete is `DELETE dt FROM t
         dt` (`DELETE FROM t dt` is a syntax error). Measured:
         pg→tsql **87 → 83** (97.4%), discovery HOLDS 0. Tests:
         TestWave140GroupConcatAndDeleteAlias (4).* Wave 141 (2026-07-16): boolean
         AND/OR **and unary predicates** (NOT / IS [NOT] NULL /
         EXISTS) in VALUE position — the CASE wrap existed for
         comparisons only; AND/OR wrapped with BARE truthy operands
         (`WHEN b1 AND a3`, 4145) and `(id IS NOT NULL) AS a3`
         shipped bare. Both now route through `_emit_condition`
         (which comparisonizes); two-valued predicates get the exact
         ELSE 0 form. Measured: pg→tsql **83 → 77** (97.6%),
         oracle flat 56, discovery HOLDS 0. Tests:
         TestBooleanOpInSelectList (3),
         TestUnaryPredicateInSelectList (2).* Wave 142 (2026-07-16): a PG
         function with OUT/INOUT params and void-or-INFERRED return
         (`function f1(in i int, out j int)` — PG infers the return
         from OUTs) cannot be a T-SQL FUNCTION (error 181) — it IS a
         procedure there. Measured: pg→tsql **77 → 74** (97.7%),
         discovery HOLDS 0. Tests: TestVoidOutFunctionBecomesProc.* Wave 143 (2026-07-16): PG
         E-strings inside procedural bodies token-split into a bare
         identifier `E` + the literal (`PRINT E 'foo\bar'`, 3x);
         the lexer now DECODES the C-style escapes (\\, \n, octal,
         \x, \u) into a plain single-quoted literal every target
         understands. (Also: a ruff failure hidden by a `| tail`
         pipe — the masked-rc lesson again.) Measured: pg→tsql
         **74 → 71** (97.8%), discovery HOLDS 0. Tests:
         TestEStringsInBodies.* Wave 144 (2026-07-16): a row
         tuple AS a select COLUMN (lateral `SELECT (a, b)`) joins
         the composite gate; and a T-SQL FUNCTION cannot access temp
         tables (2772) — a body creating one degrades whole (the
         wave-138 scan recipe). Measured: pg→tsql **71 → 68**
         (97.9%), discovery HOLDS 0. Tests:
         TestWave144TupleColumnAndTempFn (4).* Wave 145 (2026-07-16):
         MySQL-impossible aggregate forms — an EXPRESSION separator
         (SEPARATOR takes a literal only; the comma form
         CONCATENATES it onto every value — audit S1-8, and my own
         wave-140 dyn-sep emitted the invalid SEPARATOR expr there)
         and DISTINCT inside a non-builtin aggregate (hard 1064;
         arrives both as the flag AND as an Unhandled-Distinct
         RawSQL arg). Both degrade whole on mysql. Measured:
         pg→mysql **97 → 94**, oracle already at **51** (98.4%,
         waves 141-144 side effects), discovery HOLDS 0. Tests:
         TestWave145MysqlAggForms (4).* Wave 146 (2026-07-16): MySQL's
         CAST target set — the DML pipeline maps foreign spellings
         (`_CAST_TYPE_MAP`) but PROCEDURAL expression text shipped
         them raw (`RETURN CAST(p1 AS text)` = hard 1064; the
         dual-pipeline asymmetry classic): `_mysql_cast_types`
         mirror in the mysql fixup family (both sites), outside
         strings. NOTE: per-statement samplers give MISLEADING
         shapes for registry-dependent classes (composite types) —
         the real sweep transpiles the WHOLE file; classify from the
         sweep's own e.g. lines. Measured: pg→mysql **94 → 87**
         (97.0%), discovery HOLDS 0. Tests:
         TestMysqlProceduralCastTypes (2).* Wave 147 (2026-07-16): MySQL
         requires a CONSTANT LAG/LEAD offset — a column offset
         (`LAG(ten, four)`) raises 1327 and has no MySQL spelling;
         degrades whole there. Measured: pg→mysql **87 → 83**
         (97.2%), discovery HOLDS 0. Tests: TestMysqlNonConstLag
         (3).* Wave 148 (2026-07-16): the DML
         cast map covered VARCHAR/NVARCHAR→CHAR but not TEXT — PG's
         habitual cast target shipped `CAST(x AS TEXT)` raw on MySQL
         (the wave-146 procedural mirror had it; the DML side lagged
         — dual-pipeline symmetry cuts BOTH ways). Measured:
         pg→mysql **83 → 78** (97.4%), discovery HOLDS 0. Tests:
         TestMysqlDmlCastText.* Wave 149 (2026-07-16): the
         PG-source PROCEDURAL_TYPE_MAPS **never existed** — internal
         aliases (int2/4/8, float4/8) and PG-only types (TEXT, BYTEA,
         UUID, TIMESTAMPTZ, JSON/B, SERIAL) shipped raw into every
         target's routine signatures. All three maps added, ALIGNED
         with EMIT_TYPE_MAP via the cross-pipeline agreement contract
         (which fired on the first draft: FLOAT4/INT8/TIMESTAMPTZ
         disagreements — Oracle has NO BIGINT, mysql REAL is a
         DOUBLE alias); two tests STRENGTHENED (TEXT now maps to the
         modern large-string type instead of the deprecated raw
         passthrough). Measured: syntax counts flat {68/78/51} BUT
         oracle ok +27 (1749→1776 — correct types moved statements
         from environmental-fail to EXECUTING), discovery HOLDS 0.
         Tests: TestPgSourceProceduralTypeMaps (3).* Wave 150 (2026-07-16): Oracle
         rejects a BARE `*` alongside other select items (ORA-00923,
         13x) — qualified with the FROM relation (`t.*`) at emit.
         Measured: pg→oracle **51 → 38** (98.8%), discovery HOLDS 0.
         Tests: TestOracleBareStarWithSiblings (2).* Wave 151 (2026-07-16): every PG
         table name is also a ROWTYPE — a routine parameter typed
         with one (`function f(t onek)`) is as untranslatable off PG
         as an explicit composite; table names now join the
         composite-type harvest. Measured: pg→mysql **78 → 75**,
         pg→tsql **68 → 67**, discovery HOLDS 0. Tests:
         TestTableRowtypeParams (4).* Wave 152 (2026-07-16): a routine
         parameter typed with a name that resolves NOWHERE (not a
         known scalar/domain/composite/%TYPE) is a rowtype or custom
         type defined OUTSIDE the script (pg_regress setup tables
         like `onek`) — it cannot exist on the target either;
         degrades with a whitelist of known scalar spellings.
         Measured: pg→mysql **75 → 74**, pg→oracle **38 → 35**
         (98.9%), tsql flat 67, discovery HOLDS 0. Tests:
         TestUnknownParamType (4).* Wave 153 (2026-07-16): a row
         tuple compared with ANY/ALL over a subquery arrives as TWO
         source-spelled RawSQL fragments (`BinaryOp(EQ, Tuple-RawSQL,
         Any-RawSQL)` — function maps can't see inside; RANDOM()
         shipped unmapped); STRUCTURAL detection (two regex drafts
         failed: nested parens, then the two-fragment split) joins
         the composite gate. Measured: pg→mysql **74 → 72**,
         pg→tsql **67 → 65** (98.0%), discovery HOLDS 0. Tests:
         TestRowCompareAny (4).* Wave 154 (2026-07-16, mysql-corpus
         front opened): MySQL's REPEAT is T-SQL REPLICATE (it shipped
         dbo.-qualified as a fake UDF) and a 1-arg CONCAT (valid
         MySQL/PG) IS its argument on T-SQL/Oracle. Measured:
         mysql→tsql **167 → 164** — BELOW the 166 campaign record:
         the ⚠+5 anomaly is resolved and beaten (today's shared
         waves −4, this wave −3). Discovery HOLDS 0. Tests:
         TestWave154RepeatConcat (4).* Wave 155 (2026-07-16): MySQL
         truthiness in condition position — a bare numeric literal in
         ``IF(1, …)``/searched ``CASE WHEN 1`` is error 4145 on
         T-SQL/Oracle; ``_emit_condition`` now comparisonizes the
         literal and IIF routes its first argument through condition
         position. Also: pyodbc import-not-found (env driver drift)
         gets the live_validate override treatment. Measured:
         mysql→tsql **164 → 155** (−9). Discovery HOLDS 0. Tests:
         TestWave155ConditionLiterals (5).* Wave 156 (2026-07-16): a MySQL
         routine body that is a single LABELED loop (``proc c(x int)
         hmm: while … end while hmm``) or a bare REPEAT/LOOP has no
         BEGIN — the declare loop shredded it into ``DECLARE @hmm :;``
         garbage. The single-statement no-BEGIN branch now recognizes
         the ``label:`` prefix and identifier-lexed REPEAT/LOOP;
         ITERATE is a modeled ContinueStatement (T-SQL CONTINUE, MySQL
         ITERATE label — it shipped literal ``CONTINUE hmm``).
         Measured: mysql→tsql **155 → 151** (−4). Discovery HOLDS 0.
         Tests: TestWave156LabeledBodyNoBegin (4).* Wave 157 (2026-07-16): MySQL
         lets HAVING reference a select alias — every other engine
         needs the aliased expression inlined (new bottom-up
         ``_inline_having_alias`` + generic ``_map_children`` helper).
         And STRING_AGG(DISTINCT …) has no T-SQL spelling in any form:
         honest whole-statement carrier (``_gate_tsql_agg_distinct``).
         Measured: mysql→tsql **151 → 150** (−1 — the class was
         chain-glued; re-classify next). Discovery HOLDS 0. Tests:
         TestWave157HavingAliasStringAggDistinct (6).* Wave 158 (2026-07-16): MySQL
         labels BEGIN blocks too (``proc i(x int) foo: begin … leave
         foo; … end foo``) — the label shredded into ``DECLARE @foo
         :;`` and LEAVE became a bare BREAK (invalid outside a loop on
         T-SQL). The labeled-statement branch now takes BEGIN, closes
         ``END … label``, and a LEAVE of the body's own label is
         RETURN (MySQL roundtrip re-labels via proc_exit). Measured:
         mysql→tsql **150 → 146** (−4). Discovery HOLDS 0. Tests:
         TestWave158LabeledBeginBlock (3).* Wave 159 (2026-07-16): MySQL
         declares several variables with one type (``DECLARE z1, z2
         int;`` → per-name DeclareStatements in a StatementList) and
         assigns several in one SET (``SET a = 1, b = 2;`` → split;
         the comma form was invalid T-SQL and the second target lost
         its @ sigil). Depth-0 lookahead keeps single-assignment
         values comma-transparent. Measured: mysql→tsql **146 → 143**
         (−3). Discovery HOLDS 0. Tests:
         TestWave159MultiDeclareMultiSet (3).* Wave 160 (2026-07-16): MySQL
         truthiness under NOT — bare columns inside ``NOT (a AND b)``
         and a parenthesized predicate compared to 0/1 (``NOT (c2 IS
         NULL) = 1``) were error 4145 on T-SQL. ``_emit_condition``
         recurses into BinaryOp operands of NOT (narrowed so NOT
         EXISTS keeps its idiomatic spelling — the wide first cut
         broke 3 dual-guard tests) and a new
         ``_predicate_int_comparison`` rewrites ``<pred> = 1/0`` to
         the predicate or its negation. Measured: mysql→tsql
         **143 → 142** (−1; the 8x class holds INTERVAL() and
         outer-ref members). Discovery HOLDS 0. Tests:
         TestWave160NotParenTruthiness (5).* Wave 161 (2026-07-16): a
         single-argument COALESCE is T-SQL error 1088 — it IS its
         argument (CONCAT's wave-154 rule extended). And an
         aggregate's DISTINCT wrapper (``Count(this=Distinct(…))``)
         converted to a verbatim RawSQL argument, so the inner
         expressions bypassed EVERY function mapping
         (``COUNT(DISTINCT REPEAT(65, 3))`` shipped REPEAT on T-SQL) —
         now a real FunctionCall with ``distinct=True``. Measured:
         mysql→tsql **142 → 137** (−5). Discovery HOLDS 0. Tests:
         TestWave161CoalesceOneArgDistinctWrapper (4).* Wave 162 (2026-07-16):
         ADDDATE/SUBDATE are DATE_ADD/DATE_SUB aliases sqlglot leaves
         anonymous — they shipped dbo.-qualified as fake UDFs with a
         raw INTERVAL argument; canonicalized to the (ts, n, unit)
         form (bare-number second argument counts days). And ``SET
         sql_mode = …`` inside a routine is a session option, not a
         variable — it shipped a fake ``SET @sql_mode`` local;
         a known-options list degrades it to the established
         source-only comment carrier with a warning. Measured:
         mysql→tsql **137 → 131** (−6). Discovery HOLDS 0. Tests:
         TestWave162AdddateSqlMode (5).* Wave 163 (2026-07-16): sqlglot
         collapses ``CAST(x AS CHAR CHARACTER SET cs)`` to a
         CHARACTER_SET type — it emitted a nonexistent ``CAST(… AS
         CHARACTER_SET)`` everywhere, silently dropping the CHAR base
         (the corruption class). Converted to ``CHAR CHARACTER SET
         cs`` (MySQL keeps it; other targets strip the suffix). And a
         set-op subquery hangs its ORDER BY on the LAST arm of the
         set_query chain, dodging the existing unlimited-ORDER strip —
         now stripped along the chain. Measured: mysql→tsql
         **131 → 129** (−2). Discovery HOLDS 0. Tests:
         TestWave163CharsetCastSubqueryOrder (4).* Wave 164 (2026-07-16): MySQL's
         walrus assignment (``SET x := 1``) left the ``:=`` in the
         value (``SET @x = := 1`` — the OPERATOR match missed the
         ASSIGN token), and a SELECT INTO's trailing ``LIMIT n``
         survived verbatim in the T-SQL SELECT-assign, where the
         spelling is ``SELECT TOP n @v = …``. Measured: mysql→tsql
         **129 → 119** (−10, the day's biggest drop — both classes
         chained). Validity crossed **98.0%**. Discovery HOLDS 0.
         Tests: TestWave164AssignOpSelectLimit (4).* Wave 165 (2026-07-16): MySQL's
         INTERVAL(x, v1, v2, …) INDEX function (position of the last
         threshold ≤ x, −1 for NULL) parsed as an Interval literal
         wrapping a Tuple and shipped ``INTERVAL ((x, v1, …))`` —
         invalid everywhere. The unit-less Tuple form converts to a
         FunctionCall; MySQL keeps the native call, every other target
         gets the mechanical CASE chain. Measured: mysql→tsql
         **119 → 116** (−3). Discovery HOLDS 0. Tests:
         TestWave165IntervalIndexFunction (3).* Wave 166 (2026-07-16): MySQL
         prefix indexes (``PRIMARY KEY (a, b(132))``) have no
         cross-engine spelling — the passthrough-constraint path
         strips the length (whole-column keys accept every row the
         prefix key accepted; same precedent as the CLUSTERED/WITH
         strips). And FLUSH/RESET/PURGE admin statements shredded into
         ``flush AS query`` via the embedded-DML fallback — captured
         whole, verbatim on MySQL, in-body comment carriers elsewhere.
         Measured: mysql→tsql **116 → 114** (−2, validity 98.1%).
         Discovery HOLDS 0. Tests: TestWave166PrefixIndexFlush (4).* Wave 167 (2026-07-16): MySQL
         @@system variables (``@@server_id``, ``@@GLOBAL.x``) shipped
         raw — T-SQL rejects an unknown @@name (error 137). The
         user-variable whole-routine degrade now also scans @@sysvars
         (one detector, all five call sites inherit it); verbatim on
         MySQL. Measured: mysql→tsql **114 → 109** (−5). Discovery
         HOLDS 0. Tests: TestWave167MysqlSystemVars (3).* Wave 168 (2026-07-17): three
         fixes — (1) MySQL's ``INSERT … SET a=1`` form (sqlglot cannot
         parse it; the routine fallback DROPPED the SET clause —
         silent loss) pre-recognized into the universal column-list
         VALUES form; (2) a top-level ``SET @var = …`` arrived as a
         PassthroughSQL the user-var gate never scanned (the SET-option
         classifier excludes @ — first cut went on that dead path,
         removed per the wave-139 lesson) — the gate now scans
         PassthroughSQL too; (3) ``(pred) IS TRUE/FALSE`` emitted
         ``IS 1``. Measured: mysql→tsql **109 → 67** (−42 — the
         campaign's biggest drop; the @value chains collapsed).
         Validity **98.8%**. Discovery HOLDS 0. Tests:
         TestWave168InsertSetUservarIsTrue (6).* Wave 169 (2026-07-17):
         ``(c2 IS NOT NULL) = 1`` — sqlglot spells IS NOT NULL as
         NOT(IS NULL), so the predicate-to-int rewrite's BinaryOp-left
         guard missed it (error 102/156 live). ``is_predicate`` now
         accepts the NOT-wrapped form, and the ``NOT (…)`` condition
         branch takes nested-NOT operands (narrowed so NOT EXISTS/IS
         NULL keep their idiomatic spelling — the wide cut broke the
         dual-guard trio AGAIN; second offense, same lesson). Measured:
         mysql→tsql **67 → 63** (−4, validity 98.9%). Discovery HOLDS
         0. Tests: TestWave169NotNullParenCompare (3).* Wave 170 (2026-07-17): a bare
         NULL as a truth value (``… OR NULL``) was error 4145 on T-SQL
         — ``NULL <> 0`` is the UNKNOWN-preserving comparison; and
         MySQL's boolean-flip idiom ``SET done = NOT done`` has no NOT
         in T-SQL value position — the tri-state CASE preserves NULL
         (EXISTS excluded: it stays a predicate). Measured: mysql→tsql
         **63 → 60** — validity crossed **99.0%**. Discovery HOLDS 0.
         Tests: TestWave170NullTruthinessNotValue (3).* Wave 171 (2026-07-17): ``KILL
         QUERY id`` DROPPED its id via the embedded fallback (silent
         loss) — KILL joins the admin-statement family (whole capture,
         carrier off-MySQL). And CONNECTION_ID() shipped as a fake
         dbo. UDF — new niladic session-id map (@@SPID /
         pg_backend_pid() / SYS_CONTEXT('USERENV','SID')), chained
         with the UUID map. Measured: mysql→tsql **60 → 59** (−1).
         Discovery HOLDS 0. Tests: TestWave171KillConnectionId (4).* Wave 172 (2026-07-17):
         PROCEDURAL_TYPE_MAPS had NO (mysql, tsql) entry at all —
         ``DECLARE @lf double`` shipped a type T-SQL does not
         recognize. Added the full map aligned with EMIT_TYPE_MAP
         (DOUBLE→FLOAT, TEXT family→VARCHAR(MAX), BLOB
         family→VARBINARY(MAX), BOOLEAN→BIT, YEAR→SMALLINT,
         MEDIUMINT→INT); the cross-pipeline agreement contract stays
         green. Measured: mysql→tsql **59 → 57** (−2). Discovery HOLDS
         0. Tests: TestWave172MysqlTsqlDeclareTypes (3).* Wave 173 (2026-07-17): T-SQL
         EXEC arguments take only variables/literals — ``EXEC cbv2
         @y + 1, @y`` was error 102. The T-SQL emitter now tracks
         declared variable/parameter types while emitting the unit and
         hoists an expression argument into a variable of the
         referenced variable's declared type (generalizing the
         GETDATE() hoist); atomic and named-association arguments pass
         through. Measured: mysql→tsql **57 → 51** (−6, validity
         99.1%). Discovery HOLDS 0. Tests:
         TestWave173ExecExpressionArgs (3).* Wave 174 (2026-07-17): x'…'
         hex literals rendered as DECIMAL numbers (overflowing past
         BIGINT digits) — modeled as Literal dtype "hex" with per-
         engine spellings (0x…, x'…', bytea, HEXTORAW). ROW_COUNT()
         is a global on T-SQL/Oracle (@@ROWCOUNT / SQL%ROWCOUNT; PG
         keeps the source spelling — GET DIAGNOSTICS is a statement)
         and not a legal EXEC argument — @@globals hoist as INT. And
         T-SQL's SUBSTRING requires its length argument (error 174):
         the 2-argument form gets LEN(x). Measured: mysql→tsql
         **51 → 43** (−8, validity 99.3%). Discovery HOLDS 0. Tests:
         TestWave174HexRowcountSubstring (4).* Wave 175 (2026-07-17): T-SQL
         requires at least one non-computed column in a table
         (verified LIVE: error 102 at the closing paren; a mixed table
         passes) — a MySQL table whose columns are ALL generated
         degrades WHOLE with the carrier. Measured: mysql→tsql
         **43 → 42** (−1). Discovery HOLDS 0. Tests:
         TestWave175AllComputedTable (3).* Wave 176 (2026-07-17, mysql→pg
         front opened): the shared waves had already collapsed it
         105 → 36 unmeasured; PG's CASE/WHERE demand a boolean too —
         MySQL's numeric truthiness (``CASE WHEN 1``) was error 42804
         there, now comparisonized like T-SQL/Oracle (boolean literals
         untouched). Measured: mysql→pg **36 → 33** (validity 99.4%),
         mysql→tsql stable 42. Discovery HOLDS 0. Tests:
         TestWave176PgConditionLiterals (2).* Wave 177 (2026-07-17,
         mysql→oracle front opened — the shared waves had collapsed it
         129 → 66 unmeasured): Oracle spells the bidirectional
         parameter mode ``IN OUT`` (a verbatim INOUT was PLS-00103,
         9x), and PL/SQL requires at least one statement in a block —
         an empty MySQL body (``BEGIN END``) gets ``NULL;`` (5x).
         Measured: mysql→oracle **66 → 53** (−13, validity 99.1%).
         Discovery HOLDS 0. Tests: TestWave177OracleInoutEmptyBody
         (3).* Wave 178 (2026-07-17): Oracle/PG
         have no @@ globals at all — the unknown-sysvar gate now also
         runs for mysql-source oracle/postgresql targets (whitelist
         only applies on T-SQL). And PL/SQL cannot run DDL statically —
         embedded CREATE/DROP/ALTER/TRUNCATE wraps in EXECUTE
         IMMEDIATE. Measured: mysql→oracle **53 → 47** (−6, validity
         99.2%); mysql→pg stable 33. Discovery HOLDS 0. Tests:
         TestWave178SysvarGateExecImmediate (3).* Wave 179 (2026-07-17):
         STRAIGHT_JOIN is INNER JOIN plus a join-order hint no other
         engine spells — inside a parenthesized join tree (the PAREN
         JOIN passthrough) it survived the re-transpile verbatim
         (ORA-00907 / error 102 live). Normalized pre-transpile for
         non-MySQL targets. Measured: oracle **47 → 46**, tsql
         **42 → 41**, pg **33 → 32** (−3; those trees carry other
         issues too). Discovery HOLDS 0. Tests: TestWave179StraightJoin
         (3).* Wave 180 (2026-07-17):
         Oracle/PG have no ``ALTER VIEW … AS`` (ORA-00922) —
         redefinition rewrites to CREATE OR REPLACE VIEW (T-SQL/MySQL
         keep ALTER VIEW). And a raw embedded ``LIMIT [a,] b`` spells
         OFFSET/FETCH on Oracle (no ORDER BY needed there, unlike
         T-SQL). Measured: mysql→oracle **46 → 41** (−5, validity
         99.3%). Discovery HOLDS 0. Tests:
         TestWave180AlterViewLimitOracle (4).* Wave 181 (2026-07-17):
         Oracle forbids a local variable shadowing a parameter
         (PLS-00410); MySQL allows it. The colliding local renames to
         ``uq_<name>`` via the var-map (its default still sees the
         parameter — transformed before the rename registers — and
         body references follow the local, matching MySQL's shadowing
         semantics). Measured: mysql→oracle **41 → 39** (−2).
         Discovery HOLDS 0. Tests: TestWave181OracleShadowedParam
         (3).* Wave 182 (2026-07-17): SHOW /
         REPAIR / OPTIMIZE / ANALYZE / CHECKSUM / LOCK / UNLOCK inside
         a routine emitted a bare ``;`` (SHOW — SILENT LOSS with only
         a stderr note) or shredded (``REPAIR AS TABLE``); they join
         the wave-166 admin-statement family (whole capture, verbatim
         on MySQL, in-body carriers elsewhere). Measured: mysql→oracle
         **39 → 35** (−4, 99.4%), mysql→pg **32 → 22** (−10, 99.6%).
         Discovery HOLDS 0. Tests: TestWave182ShowRepairInBody (3).* Wave 183 (2026-07-17): a PL/SQL
         body whose only statement degraded to a comment carrier
         (``BEGIN -- UNIQUE: … END;``) was still PLS-00103 — the
         NULL;-injection now checks for EXECUTABLE text (not just
         non-empty), and bare ``;`` empty statements drop from the
         body. Measured: mysql→oracle **35 → 32** (−3, validity
         99.5%). Discovery HOLDS 0. Tests: TestWave183CommentOnlyBody
         (2).* Wave 184 (2026-07-17): MySQL's
         ``WHILE x DO`` loops while x ≠ 0 — Oracle/PG demand a boolean
         (PLS-00382/42804) and T-SQL's BIT fixup spelled it ``= 1``,
         SILENTLY changing a countdown loop's semantics (loops once
         instead of x times). The transformer wraps a bare-variable
         condition as ``<> 0`` for mysql source off-MySQL. Measured:
         mysql→oracle **32 → 31** (99.5%); tsql stable 40 (the fix
         there was semantics, not syntax). Discovery HOLDS 0. Tests:
         TestWave184BareWhileCondition (4).* Wave 185 (2026-07-17): Oracle
         rejects parenthesized join trees in FROM (ORA-00907). A pure
         INNER/CROSS tree (post STRAIGHT_JOIN normalization) flattens
         to the exactly-equivalent CROSS chain with the ON conditions
         ANDed into WHERE — sqlglot-parsed, structural; outer joins
         keep the carrier (NULL-extension semantics would change).
         Measured: mysql→oracle **31 → 30** (−1; the class members
         carry other issues too). Discovery HOLDS 0. Tests:
         TestWave185ParenJoinFlatten (3).* Wave 186 (2026-07-17): plpgsql
         bodies mirror the wave-183 Oracle fixes (bare ``;`` dropped,
         comment-only body gets NULL;), and a set-op ORDER BY over an
         aggregate/subquery is PG error 0A000 — whole-statement
         carrier (result-column ORDER BYs pass). First cut missed the
         SubqueryExpression import — the DML-failed warning caught it
         in the wave test. Measured: mysql→pg **22 → 18** (−4,
         validity 99.7%). Discovery HOLDS 0. Tests:
         TestWave186PgBodySemisSetopOrder (3).* Wave 187 (2026-07-17): MySQL
         BINARY casts take sizes up to 2^32−1 — beyond T-SQL's 8000
         bytes the type only exists as MAX (cast-position cap,
         mirroring the declare-position one); and a CASE as a truth
         operand under AND (``a = 1 AND CASE 1 WHEN a …``) is MySQL
         truthiness — comparisonized ``<> 0``. Measured: mysql→tsql
         **40 → 36** (−4, validity 99.4%). Discovery HOLDS 0. Tests:
         TestWave187BinaryCapCaseTruthiness (3).* Wave 188 (2026-07-17): ``IF
         level THEN`` takes MySQL numeric truthiness (PLS-00382) —
         the wave-184 bare-condition wrap is now shared by IF and
         WHILE (``_wrap_bare_truth_condition``); and the comma 2-arg
         TRIM spells ``TRIM([BOTH] x FROM y)`` off MySQL (error 174 /
         ORA-00907). Measured: mysql→oracle **30 → 28**, tsql
         **36 → 35**. Discovery HOLDS 0. Tests:
         TestWave188IfBareCondTrimTwoArg (4).* Wave 189 (2026-07-17): ``~x``
         has no Oracle spelling (ORA-00911) — new
         UnaryOperator.BITWISE_NOT with the exact two's-complement
         identity ``-(x) - 1`` there (native ``~`` elsewhere); and
         ``REPLACE t SET a=1`` joins the wave-168 INSERT-SET
         pre-recognition (it shredded inside bodies). Measured:
         mysql→oracle **28 → 27** (−1). Discovery HOLDS 0. Tests:
         TestWave189BitwiseNotReplaceSet (3).* Wave 190 measurement
         (2026-07-17, `a0819d9`): pg-corpus remeasured after 40 waves
         of shared fixes — pg→tsql **65 → 64**, pg→mysql **72**
         (unchanged), pg→oracle **35 → 32**: the pg-corpus classes are
         DISJOINT from the mysql-corpus ones. Total pending across
         both corpora: mysql-corpus 80 (35/18/27) + pg-corpus 168
         (64/72/32) = **248**, all deep singles / ≤3x classes.* Wave 191 (2026-07-17): PG 14's
         recursive-CTE ordering clauses (``) SEARCH DEPTH|BREADTH
         FIRST BY … SET col`` / ``CYCLE``) — sqlglot cannot parse
         them; the fallback SHREDDED the statement into fragments (46
         dump samples in the pg→mysql residue). Pre-recognized:
         verbatim on PG (output-gate exemption — sqlglot can't reparse
         valid PG here), documented carrier elsewhere. Measured:
         pg→mysql headline stays **72** (the fragments were not all
         counted as syntax) but output stmts 2939 → 2934 and the
         fragment class is GONE from the dump — no regressions (strict
         subset by diff). Discovery HOLDS 0. Tests:
         TestWave191PgSearchCte (3).* Wave 192 (2026-07-17): MySQL
         has no bare OFFSET — the documented all-rows idiom is
         ``LIMIT 18446744073709551615 OFFSET n``. Measured: pg→mysql
         **72 → 68** (−4 — wave 191's fragments also settled here).
         Discovery HOLDS 0. Tests: TestWave192MysqlBareOffset (3).* Wave 193 (2026-07-17): an
         UPDATE whose FROM source is a derived table (``FROM (VALUES
         …) s(x)``) was silently DROPPED at conversion, leaving
         dangling alias references. Now: verbatim on the source
         engine (SOURCE_DIALECT check in the top-level RawSQL emit),
         honest unhandled-expression carrier cross-dialect; the
         procedural cross-table-UPDATE helper takes the documented
         fallback when the conversion degrades. Measured: pg→mysql
         **68 → 67** (−1). Discovery HOLDS 0. Tests:
         TestWave193UpdateFromDerived (3).* Wave 194 (2026-07-17):
         ``NOT ((f1, f2) IN (SELECT * FROM i))`` — the tuple-subquery
         gate required >1 subquery columns and a lone ``*`` counted as
         one, so the row comparison shipped raw (4145 live). A star
         column now counts as multi when the tuple side is. Measured:
         pg→tsql **64 → 61** (−3). Discovery HOLDS 0. Tests:
         TestWave194NotTupleInStar (2).* Wave 195 (2026-07-17): IN/NOT
         IN in value position (``SELECT x IN (SELECT …)``) is a
         predicate — 4145 on T-SQL/Oracle. They join _COMPARISON_OPS,
         wrapping in the tri-state CASE (the NOT(pred) negation path —
         no pairwise negation operator exists for IN). Measured:
         pg→tsql **61 → 58** (−3). Discovery HOLDS 0. Tests:
         TestWave195InSubqueryValue (2).* Wave 196 (2026-07-17): PG's
         ``DELETE … USING`` sources were silently DROPPED at
         conversion (the DeleteStatement.using field existed but was
         never populated nor emitted) — dangling references shipped on
         EVERY target, pg→pg included. Now: PG keeps USING, T-SQL/
         MySQL spell the multi-table delete, Oracle gets the
         correlated-EXISTS rewrite; derived-table sources degrade
         honestly. Gotcha: sqlglot stores False (not None) in
         args['using'] for plain deletes — the first cut broke 5
         tests. Measured: pg→tsql stable **58** (corpus cases are
         WITH-prefixed → passthrough); the fix is silent-loss class.
         Discovery HOLDS 0. Tests: TestWave196DeleteUsing (5).* Wave 197 (2026-07-17): T-SQL
         takes no AS alias on an UPDATE target (error 156) — the
         RETURNING passthrough now names the alias and binds it in
         FROM (``UPDATE v1 SET … FROM cv AS v1, …``), placed AFTER the
         OUTPUT-prefixer so INSERTED. qualification survives (the
         early-return first cut lost it). Measured: pg→tsql
         **58 → 55** (−3). Discovery HOLDS 0. Tests:
         TestWave197AliasedUpdateReturning (2).* Wave 198 (2026-07-17):
         T-SQL/MySQL require an alias on every derived table — PG's
         bare ``FROM ((SELECT 1 AS x))`` shipped alias-less (error 102
         / MySQL 1248; the double parens are legal once aliased,
         verified live). ``uq_dtN`` aliases inject structurally in the
         PAREN JOIN passthrough. Measured: pg→tsql **55 → 54** (−1).
         Discovery HOLDS 0. Tests: TestWave198BareDerivedTables (3).* Wave 199 (2026-07-17): DELETE
         … USING inside a WITH statement spells the multi-table delete
         on T-SQL (the CTE-DML passthrough post-processes the render);
         and PG's ALTER COLUMN … USING conversion clause strips when
         it is the redundant self-cast (T-SQL's implicit conversion IS
         that cast — sqlglot normalizes to SET DATA TYPE, the pattern
         covers both spellings) and carriers otherwise. Measured:
         pg→tsql **54 → 52** (−2). Discovery HOLDS 0. Tests:
         TestWave199CteDeleteUsingAlterUsing (4).* Wave 200 (2026-07-17,
         milestone): PG's function-style casts (``float8(x)``,
         ``int4(x)`` …) exist only there — a name map routes them
         through the normal CAST machinery (per-dialect type maps
         included: DOUBLE on mysql, FLOAT on tsql); and ROW/ROWS are
         reserved in MySQL 8 (``AS row`` was 1064 — now quoted).
         Measured: pg→mysql **67 → 66** (−1). Discovery HOLDS 0.
         Tests: TestWave200FunctionCastsReservedAlias (4).* Wave 201 (2026-07-17): MySQL
         functions take only IN parameters — a PG void/inferred-return
         function WITH OUT params IS a procedure there (the wave-142
         T-SQL rule extended to mysql; the emitter already spells its
         RETURN as LEAVE proc_exit). Measured: pg→mysql **66 → 63**
         (−3). Discovery HOLDS 0. Tests:
         TestWave201MysqlOutParamFunction (2).* Wave 202 (2026-07-17): neither
         MySQL nor T-SQL has cursor-valued functions — a ``RETURNS
         refcursor`` routine degrades WHOLE with the carrier (new
         culprit in the record-function degrade chain; Oracle keeps
         its SYS_REFCURSOR mapping, PG verbatim). Measured: pg→mysql
         **63 → 58** (−5, validity 98.0%). Discovery HOLDS 0. Tests:
         TestWave202RefcursorReturn (3).* Wave 203 (2026-07-17): the
         RETURNING-mysql strip left PG-only DML shapes behind —
         ``UPDATE … FROM`` rewrites to MySQL's multi-table UPDATE and
         ``DELETE … USING`` to its multi-table DELETE (WITH prefixes
         stay legal on MySQL 8). Measured: pg→mysql **58 → 57** (−1).
         Discovery HOLDS 0. Tests: TestWave203ReturningMultiTable
         (2).* Wave 204 (2026-07-17): MySQL 8
         functional index parts take per-part parens — the mixed
         expression/column rebuild shipped a bare CASE part (1064);
         parts now wrap once (validated LIVE; the doubled first cut
         unbalanced parens via strip('()') — replaced with a balanced
         unwrapper) plus a gate exemption (sqlglot cannot reparse the
         valid form). T-SQL has no expression indexes at all — honest
         carrier. Measured: pg→mysql **57 → 54**, pg→tsql **52 → 49**
         (−6). Discovery HOLDS 0. Tests: TestWave204ExpressionIndexes
         (3).* Wave 205 (2026-07-17): a PG
         RETURNS TABLE function whose body is one RETURN (SELECT …)
         is T-SQL's INLINE table-valued function — the BEGIN…END form
         was error 102; and a derived table joined without alias gets
         ``uq_j`` on T-SQL/MySQL. Measured: pg→tsql **49 → 47** (−2).
         Discovery HOLDS 0. Tests: TestWave205InlineTvfJoinAlias
         (3).* Wave 206 (2026-07-17): the
         RETURNING-oracle strip left PG-only shapes behind — Oracle
         takes WITH only inside the INSERT's subquery (rewritten) and
         has no UPDATE … FROM at all (carrier). Measured: pg→oracle
         **32 → 30** (−2). Discovery HOLDS 0. Tests:
         TestWave206OracleReturningShapes (2).* Wave 207 (2026-07-17): SYSTEM
         is reserved since MySQL 8.0.16 (a bare ``CREATE TABLE
         system`` was 1064, probed live) — joins the quoting set; and
         MySQL's NTILE requires a positive integer — NTILE(NULL)
         degrades whole (PG returns NULL rows for it). Measured:
         pg→mysql **54 → 51** (−3). Discovery HOLDS 0. Tests:
         TestWave207SystemReservedNtileNull (3).* Wave 208 (2026-07-17): neither
         MySQL nor T-SQL has an INTERVAL data type — CAST(… AS
         INTERVAL) degrades whole; and GENERATE_SERIES(…) OVER ()
         (an SRF with a window clause) exists only on PG — carrier off
         it. Measured: pg→mysql **51 → 45** (−6), pg→tsql **47 → 46**
         (−1). Discovery HOLDS 0. Tests:
         TestWave208IntervalCastSrfWindow (4).* Wave 209 (2026-07-17): the
         inline unmapped-operator note still shipped invalid SQL (CORR
         on T-SQL is error 195 regardless of the comment) —
         cross-dialect statements carrying an unmapped-operator
         fragment now degrade WHOLE with the carrier; same-dialect
         ships verbatim. The wave-141 inline-note contract test
         updated to the new behavior. Measured: pg→tsql **46 → 39**
         (−7, validity 98.8%). Discovery HOLDS 0. Tests:
         TestWave209UnmappedOperatorGate (2).* Wave 210 (2026-07-17,
         regression fix): the wave-198 alias injection aliased
         parenthesized join GROUPS as if they were derived tables
         (invalid on T-SQL and it hid their table names — mysql→tsql
         had crept 35 → 38, caught by the four-direction remeasure).
         Only SELECT/set-op-bodied subqueries take the uq_dtN alias
         now (via unnest() — double parens nest Subquery). Measured:
         mysql→tsql **38 → 34** (better than the pre-regression 35),
         pg→tsql stable 39. Discovery HOLDS 0. Tests:
         TestWave210ParenGroupNotAliased (2).* Wave 211 (2026-07-17): Oracle
         has no CAST(… AS BINARY) form — whole carrier (7x); and
         MySQL's TRUE/FALSE are the numbers 1/0 while Oracle PL/SQL
         types them BOOLEAN (PLS-00382 assigning to NUMBER) — mapped
         in the raw-text chain for mysql→oracle only (MySQL declares
         no PL/SQL BOOLEANs, so the rewrite is safe). Measured:
         mysql→oracle **27 → 19** (−8, validity 99.7%). Discovery
         HOLDS 0. Tests: TestWave211OracleBinaryCastBoolLiterals
         (3).*** Wave 212 (2026-07-17): a two-arg ``LIMIT o, n`` in
         embedded T-SQL text spells OFFSET/FETCH with the ``ORDER BY
         (SELECT NULL)`` no-order idiom (the single-arg trailing form
         stays the SELECT-assign TOP of wave 164). Measured:
         mysql→tsql **34 → 33** (−1). Discovery HOLDS 0. Tests:
         TestWave212TsqlTwoArgLimit (2).* Wave 213 (2026-07-17): MySQL
         also rejects a bare ``*`` alongside other select items (1064)
         — the wave-150 Oracle FROM-relation qualification extends to
         it. Measured: pg→mysql **43 → 40** (−3). Discovery HOLDS 0.
         Tests: TestWave213MysqlBareStarSiblings (2).* Wave 214 (2026-07-17): PG's
         whole-row cast (``CAST(alias.* AS type)``) has no form
         elsewhere — whole carrier off PG. Measured: pg→mysql
         **40 → 39**, pg→tsql **39 → 38**. Discovery HOLDS 0. Tests:
         TestWave214WholeRowCast (3).* Wave 215 (2026-07-17): PG 14's
         SQL-standard body (``BEGIN ATOMIC …``) — unconsumed, ATOMIC
         shredded the first statement into an ``atomic;`` leftover and
         DROPPED it (silent loss; ATOMIC lexes as IDENTIFIER, so the
         keyword match missed). Measured: pg→tsql stable **38** (the
         corpus instances fail at the sqlglot source parse for other
         reasons); the fix is silent-loss class. Discovery HOLDS 0.
         Tests: TestWave215BeginAtomic (2).* Wave 216 (2026-07-17): INSERT
         VALUES cells are value position too — a predicate cell
         (``(ld IS NULL)``) now takes the tri-state CASE off MySQL
         (error 4145). Measured: mysql→tsql stable **33** (the corpus
         instance chains further members); the fix stands on its own
         tests. Discovery HOLDS 0. Tests:
         TestWave216InsertValuesPredicates (2).* Wave 217 (2026-07-17,
         structural): embedded routine text is mid-transform — its
         @names are RENAMED LOCALS, not session variables; the DML
         user-var gate ate in-body INSERT/UPDATEs and pushed them to
         the raw fallback, skipping every IR emitter fixup (the
         alternate-routes lesson, IR_EMBEDDED-guarded now). Measured:
         mysql→tsql **33 → 31** (validity 99.5%) and warnings 335 →
         305 (bodies stop over-degrading); top-level @vars still gate.
         Discovery HOLDS 0. Tests: TestWave217EmbeddedUservarGate
         (2).*** Wave 218 (2026-07-17): CALL lexes as an IDENTIFIER —
         a MySQL routine whose no-BEGIN body is a single ``call p()``
         shredded into a fake declaration and the body emptied to NULL
         (silent loss); CALL joins the identifier-lexed no-BEGIN
         branch (REPEAT/LOOP family). Measured: mysql→oracle
         **19 → 16** (−3, validity 99.7%). Discovery HOLDS 0. Tests:
         TestWave218NoBeginCallBody (2).* Wave 219 (2026-07-17): the
         raw-text variable rename hit FUNCTION CALLS — ``count(*)``
         became ``@count(*)`` when a local named count existed
         (semantic mangle); names followed by ``(`` or preceded by
         ``.``/``@`` stay untouched now. Measured: mysql→tsql
         **28 → 26** (99.6%; the wave-218 CALL fix had also rippled
         31 → 28 in the interim remeasure), pg→tsql stable 38.
         Discovery HOLDS 0. Tests: TestWave219VarRenameFunctionCalls
         (2).*** Wave 220 (2026-07-17): MySQL's chained comparison
         (``(x IS NULL) = y = 1000``) compares a predicate's truth
         VALUE — now the exact recursive tri-state CASE on
         T-SQL/Oracle and (mysql-source only) PG, including the PG
         NOT-recursion the shape needs. Measured: mysql→tsql/pg stable
         **26/18** (the corpus instances carry out-of-scope refs);
         fix stands on its tests. Discovery HOLDS 0. Tests:
         TestWave220ChainedComparison (3).* Wave 221 (2026-07-17): MySQL
         cursors bind to a fixed query at declaration — a refcursor
         VARIABLE (opened later, dynamically) has no form there; the
         routine degrades whole (sibling of the wave-202 return-type
         culprit). Measured: pg→mysql **39 → 38** (−1). Discovery
         HOLDS 0. Tests: TestWave221MysqlRefcursorVariable (2).* Wave 222 (2026-07-17): MySQL
         takes WITH only inside the INSERT's SELECT — the
         RETURNING-stripped WITH-first form was 1064 (the wave-206
         Oracle relocation, mirrored). Measured: pg→mysql **38 → 37**
         (−1). Discovery HOLDS 0. Tests:
         TestWave222MysqlReturningWithInsert (1).* Wave 223 (2026-07-17):
         VALUES(col) outside INSERT … ON DUPLICATE KEY UPDATE is NULL
         on MySQL itself — the faithful inline-noted mapping off it
         (the embedded leak rule refined: only ``-- UNIQUE:`` line
         carriers reject; ``/* UNIQUE: */`` notes are faithful
         mappings); and SELECT … INTO OUTFILE/DUMPFILE is a file
         export the variable-INTO parse mangled into a fake variable —
         whole admin carrier now. Measured: mysql→oracle **16 → 13**
         (99.8%), mysql→tsql **26 → 23**. Discovery HOLDS 0. Tests:
         TestWave223ValuesFnOutfile (3).* Wave 224 (2026-07-17): a bare
         RETURNS TABLE needs T-SQL's inline ``AS RETURN (select)``
         form — a body without a RETURN has no faithful spelling and
         degrades whole (new culprit). Measured: pg→tsql **38 → 34**
         (−4, validity 98.9%). Discovery HOLDS 0. Tests:
         TestWave224ReturnsTableNoBody (2).* Wave 225 (2026-07-17):
         ``COMMENT ON`` inside a routine body is PG/Oracle SQL —
         verbatim there (semicolon carried FROM THE PARSER: the
         transformer-side fix missed pg→pg, which briefly broke
         discovery to 1 before the in-wave verification caught it),
         carrier on MySQL/T-SQL. Measured: pg→mysql **37 → 36** (−1).
         Discovery HOLDS 0 (recovered in-wave). Tests:
         TestWave225CommentOnInBody (2).* Wave 226 (2026-07-17):
         plpgsql's INTO may come FIRST (``SELECT INTO x id FROM …``) —
         the list-first capture shredded it into an empty select list
         with mangled order; the INTO-first vars now normalize through
         the shared tail. Measured: pg→mysql **36 → 34**, pg→tsql
         **34 → 33** (−3). Discovery HOLDS 0. Tests:
         TestWave226IntoFirstSelect (3).* Wave 227 (2026-07-17): PG
         coerces a numeric RETURN into a boolean function — Oracle's
         BOOLEAN takes no numbers (PLS-00382): ``RETURN (n <> 0)`` IS
         the boolean; and refcursor declares spell SYS_REFCURSOR there
         (missing (postgresql, oracle) type-map entry). Measured:
         pg→oracle **28 → 25** (−3). Discovery HOLDS 0. Tests:
         TestWave227OracleBoolReturnRefcursor (3)(3).* **CHECKPOINT wave 228
         (2026-07-17, `4e6d908`, full 6-direction matrix)**:
         mysql-corpus {tsql **23** (99.6%), pg **15** (99.7%), oracle
         **13** (99.8%)}; pg-corpus {tsql **33** (99.0%), mysql **34**
         (98.8%), oracle **25** (99.2%)} — **TOTAL 143** from ~770 at
         campaign open (121 waves, 108–227). Discovery pg→pg **0**
         throughout. Remaining: adversarial deep singles (pg_regress
         shadow/label/custom-aggregate cases) across six fronts.* Wave 229 (2026-07-17): a
         single-arg ``LIMIT n`` INSIDE a subquery (``RETURN (select …
         limit 1)``) spells OFFSET/FETCH with the no-order idiom on
         T-SQL (the trailing statement-level form stays the wave-212
         SELECT-assign TOP); the raw-text LIMIT map now covers pg
         source too. Measured: pg→tsql **33 → 31** (−2). Discovery
         HOLDS 0. Tests: TestWave229SubqueryLimitTsql (2).* Wave 230 (2026-07-17): PG
         functions may WRITE; T-SQL functions take no side-effecting
         DML (error 443 — the previous outputs were live-invalid): a
         writing function that STAYS a function (non-void, no OUT
         params, non-trigger — those become procedures/trigger bodies)
         degrades honestly. Three legacy test fixtures converted to
         procedures (their asserted outputs were 443-invalid).
         Measured: pg→tsql **31 → 29** (validity 99.1%). Discovery
         HOLDS 0. Tests: TestWave230WritingFunctions (2).* Wave 231 (2026-07-17): a
         temp-table QUALIFIER (``JOIN #t1 ON t1.c0 = 5``) left the
         alias dangling on T-SQL — the ColumnRef emitter renamed
         temp-table NAMES but not qualifiers; fixed. Measured:
         mysql→tsql stable **23** (the one corpus instance uses an
         un-#'d ``t1.`` on a chained comparison the temp-rename can't
         reach without schema); the fix closes a real qualifier gap on
         its tests. Discovery HOLDS 0. Tests:
         TestWave231TempQualifierRename (2).* Wave 232 (2026-07-17): MySQL's
         TIMESTAMPADD(unit, n, ts) reorders to the canonical
         DATE_ADD(ts, n, unit) form (its arg order differs) — DATEADD
         on T-SQL, interval on Oracle; and CAST(… AS YEAR) is SMALLINT
         off MySQL. Measured: mysql→tsql **23 → 22** (−1). Discovery
         HOLDS 0. Tests: TestWave232TimestampaddYearCast (2).* Wave 233 (2026-07-17):
         ``SELECT * INTO x, y`` shipped ``@x = *, @y = *`` (error 102,
         no schema to expand the star) — the T-SQL select-into emitter
         degrades it honestly. Measured: mysql→tsql **22 → 21** (−1).
         Discovery HOLDS 0. Tests: TestWave233StarIntoMultipleVars
         (2).* Wave 234 (2026-07-17): ``> ALL
         / ANY / SOME (SELECT …)`` — sqlglot models the quantified
         subquery, but unconverted it stayed a RawSQL whose inner
         WHERE never saw the mapping pipeline (a truthy ``WHERE b`` was
         4145 on T-SQL). Now a real SubqueryExpression with a
         quantifier field; the emitter re-attaches the keyword and the
         inner query maps fully. Measured: mysql→tsql **21 → 20**
         (validity 99.7%). Discovery HOLDS 0. Tests:
         TestWave234QuantifiedSubquery (3).* **CHECKPOINT wave 235
         (2026-07-17, `17a3c32`, final matrix)**: mysql-corpus {tsql
         **20**, pg **15**, oracle **13**}; pg-corpus {tsql **29**,
         mysql **34**, oracle **24**} = **135 total**, validity
         98.8–99.8%. Discovery pg→pg **0**. **ADVERSARIAL FLOOR
         reached**: the residue is pg_regress error-path tests
         (corrupt latin1 identifiers, PREPARE/EXECUTE dynamic SQL,
         custom aggregates), constructs already carried (composite row
         values, whole-row casts), and cases needing SCHEMA knowledge
         (a column whose name collides with a local variable — cannot
         disambiguate without the table's columns). Each further wave
         moves ≈1 statement. Campaign: **128 waves (108–234), ~770 →
         135**, discovery 287 → 0.* Wave 235 (2026-07-17): PG's
         ``bpchar`` (blank-padded CHAR) and ``name`` types had no
         procedural type-map entry — added to all three pg-source maps
         (CHAR/VARCHAR2/VARCHAR); the (postgresql, tsql) entry lives in
         PROCEDURAL_TYPE_MAPS not the same-keyed FUNC map. Measured:
         pg→mysql **34 → 33**, pg→oracle 24 (one reclassified). Floor
         now **134**. Discovery HOLDS 0. Tests:
         TestWave235BpcharNameTypes (2).* Wave 236 (2026-07-17,
         FIDELITY): sqlglot cannot parse ``DROP TABLE a, b`` — it
         shipped the whole statement as a NO-OP COMMENT (the tables
         were never dropped — a silent behavior loss). A parse_sql
         pre-recognition splits it into one real DROP per table (valid
         everywhere; Oracle has no comma form). Statement counts jumped
         (mysql→tsql 5817 → 6299 — the split expands multi-drops) with
         syntax stable **20** / pg→mysql **33** — the fix is
         correctness, not a validity-count mover. Discovery HOLDS 0.
         Tests: TestWave236MultiTableDrop (3).* Wave 237 (2026-07-17,
         CORRECTNESS): the token rejoin spells a qualified column
         ``t1.data`` as ``t1 . data`` (spaces), and the fixed-width
         lookbehind protecting dotted names from the variable rename
         was blind across the space — a column whose name matched a
         local variable got mangled to ``t1. = @data`` (silent
         corruption). The rename now captures the optional
         ``<qual> .`` prefix and preserves it. Measured: mysql→tsql
         stable **20** (the corpus's setcontext also has a genuinely
         schema-ambiguous ``REPLACE … SET data = data`` where the RHS
         column-vs-variable is undecidable); the fix prevents the
         mangle class elsewhere. Discovery HOLDS 0. Tests:
         TestWave237DottedNameRenameSpaces (2).* Wave 238 (2026-07-17):
         MySQL's NTH_VALUE requires a positive integer LITERAL — an
         expression (``NTH_VALUE(x, four + 1)``) is 1064 (verified
         live); it joins the non-constant window-argument gate
         alongside LAG/LEAD. Measured: pg→mysql **33 → 32** (−1).
         Discovery HOLDS 0. Tests: TestWave238MysqlNonconstNthValue
         (2).* Wave 239 (2026-07-17,
         FIDELITY): the wave-236 multi-table DROP split extends to
         FUNCTION/VIEW/SEQUENCE/INDEX/PROCEDURE/TYPE/DOMAIN — ``DROP
         FUNCTION a, b`` also shipped as a no-op comment (objects
         never dropped). Now real per-object DROPs. Measured: pg→tsql
         stable **29** / oracle **24** (fidelity, not a count mover —
         the multi-drops were carried comments). Discovery HOLDS 0.
         Tests: TestWave239MultiObjectDrop (2).**
         **Scope decision
         (user, 2026-07-17): live validation is a CODE-REFINEMENT
         tool only — used by the sweeps/tuning loops to find mapping
         gaps. It is deliberately NOT exposed in the CLI or the API
         (an end-user feature that needs a live engine to produce
         correct output would be a botch); `validate_live_url` stays
         a development-facing option.**

## FLOOR DECLARED (2026-07-17, user, HEAD 469917a)

The direction-residue campaign (waves 108–239) is **complete at its
architectural floor**: **133 pending** across six directions
(mysql-corpus {tsql 20, pg 15, oracle 13}, pg-corpus {tsql 29, mysql
34→32, oracle 24}), validity **98.9–99.8%**, discovery pg→pg **0** from
287. The remaining residue is THREE non-wave classes: (1) adversarial
pg_regress error-path inputs (corrupt latin1 idents, PREPARE/EXECUTE,
custom aggregates); (2) schema-dependent (a column whose name equals a
local variable — RHS undecidable at statement level); (3) `RETURN
QUERY` table functions (a multi-file feature — attempted as a wave,
reverted cleanly to avoid a pg→pg regression). Two broad-net safety
nets were tried and reverted (RETURN QUERY, opaque-Command carrier);
both proved the floor is architectural, not a patch. Closing further
requires schema-aware transpilation or the dev-only live validator on
the emit path — out of scope for statement-level transpilation.

---

## 37. Module-growth hardening — parser, transformer and transpiler splits

Archived from `docs/TODO.md` §2 P3 on 2026-07-17. The three modules that had
outgrown review size are packages/composed objects now:

- **`procedural/parser`** (2026-07-10): package split `_base` 1.7k +
  `_tsql` 0.7k + `_plsql` 0.8k with an explicit cross-family contract.
  (The same name-based mixin cut did NOT transfer to the transformer — its
  families cross-call heavily; a first attempt needed a dozen-plus stub
  contract and was reverted, leading to the composed-object design below.)
- **`procedural/transformer/_expr.py`** (`997f0e8`, 2026-07-17): the
  expression-rewrite family — 36 text-level rewriters (curated
  DATEADD/DATEDIFF/STRING_AGG/DECODE handlers, string-concat
  classification, function renames, niladic/date-format maps,
  last-identity capture) plus their 13 class constants — moved to a
  composed `ExpressionRewriter` constructed per transform as
  `self._expr`, reading its narrow context (source/target, string/date
  vars, warning sink, pair func map) through the owning transformer.
  13 base + 11 per-target call edges rewired mechanically; no override
  point moved (`_fix_raw_sql_target` & friends stay per-target).
  `base.py` 5053 → 3735 lines. Verified: full gate green and the
  cross-target expression-path output byte-identical before/after.
  This object is the text path M3's IR-first expressions will replace.
- **`core/transpiler/`** (`0e6ead0`, 2026-07-17): the 2.4k-line module
  became a package — `_text_rules.py` (module-level batch recognizers and
  pre/post text helpers: the M2/P3 single guard recognizer, Oracle
  idempotent creates, carrier/warning reconciliation, SQLite source
  rewrites) and `_core.py` (the `Transpiler` orchestrator + options/result
  types), with `__init__.py` re-exporting the public surface unchanged
  (`Transpiler`, `TranspileOptions`, `TranspileResult`, `transpile`).
  Mechanical, no behavior change; public surface and CLI probed.

En route finding (filed as its own TODO item): the tsql→mysql procedural
DATEADD handler emits a nested `INTERVAL (INTERVAL '-1' MONTH) DAY` when the
DATEADD sits under a CONVERT chain — pre-existing (byte-identical before the
refactor), P2.

---

## 38. M3-prereq — procedural text-matchers moved onto structure

Archived from `docs/TODO.md` §2 P0 on 2026-07-17: every increment landed and
the family survey closed; what remains of M3 lives in the consolidated M3
item (the two IR preconditions + family migration). Original item verbatim:

- [x] **M3-prereq: move the procedural text-matchers onto structure before
      routing scalar expressions through the IR.** *Increment 1 landed
      2026-07-11 (`e8196ee`): the IR gains procedural variable types — a
      STRING_VARIABLES ContextVar published around every IR call lets the
      shared `_looks_like_string` classify `@a + @b` over declared string
      variables (fixed a live runtime bug: embedded UPDATE shipped
      `v_a + v_b` on PG). *Increment 2 landed 2026-07-11
      (`35c2155`, `33034ab`): the differential text-vs-IR audit found and
      fixed THREE live semantic bugs in the curated text handlers —
      DATEADD's '+' turned into '||' by the concat classifier (intervals
      now neutralize their literals), a token-joined '- 1' losing its
      sign inside the INTERVAL string (DATEADD(MONTH,-1) silently ADDED a
      month; literal counts compact, expression counts multiply a unit
      interval), and DATEDIFF DAY/MONTH/YEAR emitting Oracle-fractional /
      PG-AGE forms instead of T-SQL's boundary counts (both pipelines now
      share the boundary-counting forms).* Remaining increments: *(3) DONE 2026-07-17 (wave 96):
      LastIdentityCapture node landed — producer in both assignment
      transforms (oracle target, value is only the last-identity
      call), pairing pass consumes the node, marker constant deleted;
      the UNPAIRED fallback improves from the invalid `v := /* … */;`
      to a valid NULL assignment + note. Full gate green on first
      try; pg-corpus verification cycle at `b073133` identical
      {163/131/89} — no regression. Tests:
      TestLastIdentityCaptureNode.* Original analysis
      (2026-07-17): the marker is the TAIL of the Oracle comment
      `LAST_IDENTITY_EXPR["oracle"]` produced by
      `_transform_last_identity`'s text substitution;
      `_identity_assignment_var` then substring-matches it
      (`base.py:390`). Design: when the assignment transform detects a
      LAST_IDENTITY_SOURCE_FUNCS call with target oracle, return a
      dedicated `LastIdentityCapture(target_var)` node; the pairing
      pass (`base.py:345`) consumes the node; the emitter renders the
      documented comment for any UNPAIRED capture (fallback). Keep the
      non-assignment usages (`SELECT @@IDENTITY` in expressions) on
      the comment path. This is a fresh-session-sized refactor — the
      naive attempt broke 18 tests.*; (4) dual-guard→IF and
      DECLARE-init hoisting consume nodes — *4a landed 2026-07-17
      (wave 97): Oracle's assignment-via-SELECT-INTO decision now
      inspects the value NODE first (`_needs_sql_context`: subquery or
      CAST anywhere in the tree; RawSQL fragments keep the spelling
      regex). Tests: TestAssignmentViaSelectNodeAware; verification
      cycle at `129cc6b` identical {163/131/89}. Remaining 4b —
      *analysis 2026-07-17: the DECLARE-init half is DONE BY
      CONSTRUCTION after 4a (the hoisting already builds an
      AssignmentStatement from the initializer NODE, which then takes
      the node-aware SELECT-INTO path — verified live); the
      batch-level T-SQL guard recognizer (`_TSQL_GUARD_HEAD_RE`) is
      PRE-PARSE BY DESIGN (audited M2/P3 single-recognizer decision,
      runs on batch text before any parsing — unaffected by
      IR-emitting scalar expressions). The M3b probe RAN 2026-07-17
      (uncommitted IR-first in `_transform_raw_sql`, full suite):
      **126 failures** — the text path has GROWN as the expression
      engine since the original 18. Category map (top offenders):
      curated DATEADD/DATEDIFF/TRUNC/TO_DATE handlers (16+),
      function-name mapping & oracle-builtin renames (7+),
      FOUND/fetch-status cursor idioms (7), string-concat/plus
      classification (6+), error-global conditions & RAISERROR hoists
      (8+), comments inside expressions (IR drops them, 6+),
      SUBSTRING/position arg orders (4). Conclusion: wholesale
      IR-first is NOT the path — each consumer family must migrate
      individually (the increments-1..4a pattern), OR the IR
      expression pipeline must absorb those behaviors first. The
      probe patch is reproducible: guard `UNIQUE_IR_FIRST` in
      `_transform_raw_sql` wrapping `_ir_transpile_dml` for scalar
      fragments. Family migration step 1 (dates) landed 2026-07-17
      (wave 98): the differential found a live IR bug — DATEADD over
      a DATEDIFF base added an INTERVAL to a NUMBER (invalid Oracle /
      wrongly typed PG); the IR now matches the text path's numeric
      addition. Tests: TestIrNestedDateaddOverDatediff; verification cycle at
      `6be5038` identical {163/131/89}. Family step 2 (function
      renames) landed 2026-07-17 (wave 99): the differential found the
      procedural text path had NO (mysql, postgresql)/(mysql, oracle)
      function maps — IFNULL shipped raw to PG; both maps added
      (IFNULL/RAND/CURDATE/UUID + the symmetry round-trips the
      mapping-contract test enforces). Known cosmetic divergences left
      documented: NVL→ISNULL (text) vs COALESCE (IR) on tsql — both
      valid; sqlglot's LEN→LENGTH(CAST AS CLOB) vs text's plain
      LENGTH — both count trailing spaces that T-SQL LEN ignores
      (shared caveat, not a divergence). Tests:
      TestMysqlProceduralFuncMaps; mysql-corpus cycle at `e933b82`
      stable {166/107/129} (fidelity inside already-counted
      routines). Family step 3 (concat classification) landed
      2026-07-17 (wave 100): T-SQL `N'…'` literals parse as
      exp.National, which `_looks_like_string` did not recognize —
      `N'pre' + s` shipped raw `+` to Oracle (invalid on strings).
      The nested-CONCAT shape on mysql (`CONCAT(CONCAT(a,b),'c')` vs
      flat) is cosmetic, documented not chased. Tests:
      TestNationalStringConcat; verification cycle at `0a0ad03`
      identical {163/131/89}. Family step 4 (error-globals) landed
      2026-07-17 (wave 101): the system globals lived only in the
      procedural maps — a top-level `SELECT @@ROWCOUNT` shipped raw
      off T-SQL. New shared `_map_system_global` in the DML expression
      emit: MySQL gets the real ROW_COUNT(); PG/Oracle top-level get
      a documented neutral (their forms are PL-context only); Oracle's
      `SQL%ROWCOUNT` — which parses as a MODULO — maps at the
      BinaryOp. Tests: TestSystemGlobalsInDml; verification cycle at
      `63e0d31` identical {163/131/89}. Family survey CLOSED
      2026-07-17 (wave 102): @@FETCH_STATUS gets the top-level
      neutral (it is CURSOR-CONTEXTUAL by nature — the procedural
      path maps it with surrounding state: FOUND on pg, handler
      flags on mysql, cursor%FOUND on oracle; a context-free IR
      mapping is impossible today). DESIGN CONCLUSIONS for M3 final:
      (a) the IR expression pipeline must RECEIVE procedural context
      (cursor state, like STRING_VARIABLES) before fetch idioms can
      migrate; (b) in-expression COMMENTS need comment-carrying
      expression nodes in the IR (they are dropped today) — both are
      the remaining preconditions for deleting the text rewriters.
      Tests: TestFetchStatusTopLevel; verification at `2a2dc90`
      identical {163/131/89}.*; then the text rewriters can
      shrink. Original blocker analysis:** A first attempt at IR-first
      for `_transform_raw_sql` expressions (M3b) broke 18 tests and was
      reverted: downstream machinery pattern-matches on the *transformed
      expression text* — the Oracle last-identity capture looks for a marker
      string, the dual-guard→IF and DECLARE-init hoisting match query
      spellings, `_rewrite_string_concat` uses declared-variable types the
      standalone IR doesn't have, and the curated DATEADD/DATEDIFF handlers
      produce live-validated forms the IR emitter doesn't. Those consumers
      must consume nodes (or the IR must gain procedural context: var types,
      PROCEDURAL_FUNC_MAPS) before the text rewriters can be deleted (P4's
      final step). Until then the text path stays the expression engine.

The superseded M3 history (M3a/M3b detail), kept for reference:

- [x] *(superseded by the consolidated M3-final item in TODO)* **M3 — P4 embedded DML through the IR converter**; delete the
      text-level rewriters (clears D3, D4, D8, A4 by construction).
      *M3a landed:* `_transform_embedded_dml` now routes through the shared
      `parse_sql → Transformer → emit_node` IR pipeline (raw sqlglot only as a
      warned fallback), which cleared D3 and D4 and surfaced+fixed four IR
      core bugs that also hit standalone DML: pass recursion stopped at
      top-level SELECTs (generic dataclass-field walker now), `find(exp.Where/
      Having)` duplicated a derived table's WHERE onto the outer SELECT,
      dropped parens/precedence on emit (silent `AND`/`OR` re-association),
      and `nulls_first` never carried (T-SQL DESC row order changed on PG).
      `exp.In`/unstyled `exp.Convert` are now modeled (IN was a RawSQL
      passthrough passes couldn't see; CONVERT now shares the CAST type maps).
      Three head-anchored matchers made trivia-aware via the shared
      `split_leading_trivia` (result-SELECT→refcursor, identity capture,
      trigger set-based rewrite). *M3b:* D8's remaining corruption was the
      T-SQL SELECT-INTO emitter's naive `split(",")` — fixed with the shared
      `split_top_level_commas`. Tests: `tests/integration/
      test_embedded_dml_ir.py` (22). **Measured (2026-07-09, live sweep):**
      test.sql→PG **100.0%** / Oracle 99.6% / MySQL 97.7% (unchanged classes);
      bigtest (Oracle source)→T-SQL **94.3%** / PG **76.6%** (was 73.1 — D3
      cleared) / MySQL 75.0%; live-syntax suite 53 passed. Transpile of the
      13 MB dump ~55 s (+22% vs pre-M3, linear). Still open: deleting the
      expression-level text rewriters — blocked on the M3-prereq below.

---

## 39. M3 final — IR-first expressions (the last architecture-plan milestone)

Archived from `docs/TODO.md` §2 P0 on 2026-07-17 (landed at `86f7c11`).
Original consolidated item with the burn-down record:

- [ ] **M3 final — IR-first scalar expressions; retire the text-level
      expression rewriters (`transformer/_expr.py`).** The LAST open
      architecture-plan step, a declared MULTI-SESSION milestone — never a
      wave. *Done so far:* M3a/M3b (embedded DML through the shared IR
      pipeline, measured 2026-07-09) and the whole M3-prereq arc
      (increments 1–4 + family steps 1–4, archived in
      [`docs/DONE.md`](DONE.md) §38). *Remaining, in dependency order:*
      1. *Precondition (a) — DONE 2026-07-17 (`e44ce92`):* cursor state
         reaches the IR expression pipeline. `FETCH_STATUS_FORMS`
         ContextVar published around `_ir_transpile_dml` (guarded on the
         idiom so MySQL's handler-injection flag has no false side
         effect); the IR BinaryOp emit maps `@@FETCH_STATUS = 0 / <> 0 /
         = -1|-2` to the per-target forms exactly like the text path.
         Probe 113 → 109; live FE 16/16 green. Tests:
         TestIrFetchStatusContext (6).
      2. *Precondition (b) — comment-carrying expression nodes:* the IR
         drops in-expression comments today; the converter/emitters need
         trivia-bearing expression nodes. Fresh-session-scale.
      3. *Family-by-family migration* (the increments-1..4a pattern,
         differential text-vs-IR audits per family, live sweeps as the
         net), then flip `_transform_raw_sql` to IR-first and delete the
         rewriters.
      **Probe measurements 2026-07-17:** IR-first for scalar fragments =
      **113 failures at `5b26d5b`** (was 126 at the original probe;
      waves 98–102 absorbed the difference), **109 after precondition
      (a)**. Module map at 113: pg_source_wave1 25,
      procedural/test_transformer 21, oracle_source_m4_wave 15,
      test_procedural 13, oracle_mysql_tail 9, test2_residue_wave 7,
      embedded_dml_ir 5, triggers 4+4, singles 10.
      Probe recipe (reproducible): guard `UNIQUE_IR_FIRST` in
      `_transform_raw_sql`, calling `self._ir_transpile_dml(node.sql)`
      right after the early-return carriers and returning the replaced
      node when it succeeds; run the full suite with `UNIQUE_IR_FIRST=1`.

Closing summary: the UNIQUE_IR_FIRST development switch became the default
(kill-switch `UNIQUE_NO_IR_FIRST`); the family burn-down ran probe
126 → 113 (waves 98–102) → 109 (precondition (a)) → 74 (switch placed at
the expression-mapping layer, below the shell's variable renames) → 0 real
divergences across ~15 family commits (d7e0ea4..75bfc9d), each with its
always-on unit family in `tests/unit/core/test_ir_first_families.py`,
full-gate + FE-live verification, and one new shared table per family
(PROCEDURAL_FUNC_MAPS consumed by the IR, ERROR_MESSAGE/DIAGNOSTIC
tables, DML_FOUND_EXPR, ORACLE_DATE_FORMAT_STYLES, FETCH_STATUS_FORMS,
DATE_VARIABLES) — the audit's "one table, both pipelines" direction.
Definitive live cycle at the flip: TOTAL 127 syntax failures across the
six corpus directions vs the pre-M3 declared floor of 133, discovery
pg→pg 0, FE 16/16, suite green. Real bugs found en route by the
differentials: MySQL byte-vs-char LENGTH, LTRIM/RTRIM position loss,
CHARINDEX not-found offset drift, N'…' invalid on PG, silent GROUPS-frame
material, the '+'-as-concat mysql-source semantics, COUNT boundary
semantics of DATEDIFF(HOUR).

## 40. Zero-reduction campaign — six-direction residue 127 → 22 (batches W1–W6)

Archived from `docs/TODO.md` on 2026-07-17 (landed across `80c9545`..`34d7338`).
**The direction-residue campaign was CLOSED at a user-declared floor of 133
(§36). This follow-up campaign then blew straight through that floor: 133
(declared) → 127 (M3-final flip) → 16 — a further −88% below the floor, and
both Oracle directions reached 100.0% validity.** After the M3-final flip the
residue was driven down with **mechanism fixes, not corpus waves** — each batch
a commit with always-on tests in `tests/unit/core/test_ir_first_families.py`,
the full gate (black/isort/ruff/mypy + `scripts/test-parallel.sh`), and
live-syntax + FE 16/16 against the four engines. Discovery pg→pg held **0**
throughout; validity 99.8–100.0%. Concluded by the user 2026-07-17 ("la
reducción a cero la damos por concluida") — the remaining 16 is the true
architectural floor.

Cycle-by-cycle (`scripts/validity_sweep.py`, per direction on live engines):

| Cycle | Batch | pg→{tsql,mysql,oracle} | my→{tsql,pg,oracle} | Total |
|---|---|---|---|---|
| flip | M3-final | 20 / 37 / 25 | 17 / 13 / 15 | 127 |
| z3 | (prior) | 11 / 9 / 11 | 10 / 8 / 9 | 58 |
| z4 | W1 | 9 / 8 / 9 | 8 / 5 / 9 | 48 |
| z5 | W2 | 7 / 7 / 8 | 6 / 4 / 9 | 40 |
| z6 | W3 | 3 / 7 / 8 | 6 / 4 / 9 | 36 |
| z7 | W3-remodel+W4 | 3 / 7 / 6 | 6 / 4 / 5 | 29 |
| z8 | W5 | 3 / 5 / 4 | 4 / 4 / 5 | 25 |
| z9 | W6 | 3 / 5 / 4 | 4 / 4 / 2 | 22 |
| z10 | W7 | 2 / 5 / 4 | 4 / 3 / 2 | 20 |
| z11 | W8 | 1 / 5 / 4 | 4 / 3 / 2 | 19 |
| z12 | W9 | 1 / 5 / 2 | 4 / 3 / 2 | 17 |
| z13 | W10 | 1 / 5 / **1** | 4 / 3 / **2** | **16** |

Both Oracle directions reached **100.0% validity** at z13; discovery pg→pg 0.

Mechanisms (all live-verified where Oracle):

- **W1** — MySQL param `CHARSET`/`CHARACTER SET`/`COLLATE` attributes consumed;
  `REAL` joins the pg skip-params set; `CURRENT_USER`/`SESSION_USER` niladic;
  scalar `(VALUES (row))` → single-row subquery; bare `WHERE <expr>` routed
  through `_emit_condition`; `CAST(… AS information_schema.*)` gated;
  PREPARE/EXECUTE/DEALLOCATE join the MySQL admin-carrier family; CTE names in
  `DEFINED_ALIASES`.
- **W2** — MySQL BEFORE-row trigger IF-predicate transpiled through the IR
  (`ISNULL(x)` → `x IS NULL`) with a balanced wrapping-paren strip; MySQL
  `REPLACE` *statement* → routine carrier (distinct from `REPLACE()` the
  function); literal `OFFSET 0` dropped on T-SQL/MySQL; `ANY/ALL` subquery
  unwrapped to a scalar `SubqueryExpression` (multi-column stays RawSQL for the
  composite gate); `MODE() WITHIN GROUP` → Oracle `STATS_MODE`; nameless
  embedded `CREATE INDEX` gets a synthesized name.
- **W3** — join-position derived-table `ORDER BY` strip on T-SQL/Oracle;
  `RETURN QUERY`/`RETURN NEXT` bodies → routine carrier; self-join / comma-source
  `UPDATE … FROM` emits correctly (`_cross_update_target` picks the target by
  alias; PG + MySQL list the FROM source — MySQL as a comma multi-table UPDATE).
- **W3-remodel** — aliased `UPDATE … FROM … RETURNING` re-parsed through the
  modeled converter in the RETURNING passthrough (`_remodel_update_from`).
- **W4** — self-referential declaration init drop (guarded so a shadowed-param
  init is kept); Oracle-unsafe local names (count/min/max/sum/avg) renamed with
  the `SELECT … INTO` target following; named cursor args `:=` → `=>`; BLOB
  literal RETURN → `TO_BLOB(UTL_RAW.CAST_TO_RAW(…))`.
- **W5** — Oracle SYS_REFCURSOR parameter the body OPENs → `IN OUT`; refcursor
  declaration init dropped; a comment-only T-SQL trigger body (untranslatable
  CALLs) gets a `SET NOCOUNT ON` no-op filler.
- **W6** — `NULLS FIRST/LAST` stripped from an embedded Oracle `CREATE INDEX`
  (sqlglot injects it; ORA-00907) — proc_bug19733 compiles clean.

- **W7** — a data-modifying CTE (`WITH x AS (INSERT/UPDATE/DELETE …) …`)
  degrades to a carrier on T-SQL (detected on scrubbed text, since sqlglot
  drops the WITH arg when a CTE body is DML); the pg set-op `ORDER BY`
  aggregate gate now scans the ordering expression recursively (an aggregate
  wrapped in arithmetic was missed).
- **W8** — a whole-row `OLD.*`/`NEW.*` reference in a trigger function degrades
  the trigger to a carrier (no T-SQL whole-row variable); the inline path had
  warned but still shipped invalid SQL.
- **W9** — a `COMMENT ON <object>` statement inside a routine body carriers on
  every foreign target (DDL a PL/SQL block cannot run statically — the
  wave-225 Oracle "verbatim" decision was live-checked and corrected here); a
  plpgsql dynamic `OPEN … FOR EXECUTE` cursor carriers on Oracle.
- **W10** — Oracle accepts `bool` as BOOLEAN, so a numeric `RETURN 1` in a
  `RETURN bool` function wraps to `RETURN (1 <> 0)` (the wrap previously fired
  only for a return type spelled BOOLEAN).

**Remaining 16 are the architectural floor**: adversarial pg_regress/sqlancer
inputs sqlglot cannot parse (nested-paren join trees `(a CROSS JOIN (b JOIN c
ON …) ON …)` reach 2, chained `a = b = c` comparisons reach 2), a correlated
outer-aggregate subquery, composite-field access on a function result
(`(f(x)).field`), schema-dependent type inference (`COALESCE` bigint/char),
LATERAL derived-table column-alias lists, and a handful of mysql-source
structural singletons (backslash-escaped literals, EXEC expression-arg hoist,
handler placement). Measurement note: the pg→oracle sweep hangs at *runtime*
on bare `SELECT <dml-fn>()` pg_regress driver calls (DML in a SQL-called
function / lock wait) — these are not syntax defects (the `CREATE FUNCTION` is
compiled and counted); the sweep skips them.

## 41. BLUE round — challenge corpus RESOLVED to the architectural floor (2026-07-18)

Archived from `docs/TODO.md §5`. The RC-1..4 root-cause plan for the 862 RED findings, carried to closure: RC-1b built-in gate (DML + procedural), RC-3 clause-drops (FK/CHECK, IDENTITY seed/step, column COMMENT, Oracle ON UPDATE), RC-2 LOG, 21 live-verified RC-1a built-in mappings; FINDINGS.md pruned (703 rows resolved) and 259 cases flipped `[open]→[fixed]`. The 603 residual `[open]` cases are the declared floor (schema/type/collation-dependent). Detail below.

- [x] **BLUE backlog: 862 RED findings — RESOLVED to the architectural floor
      (2026-07-18).** The tractable, architecture-respecting work is complete; the
      residual is the declared floor (schema/type/collation-dependent, like the
      prior campaigns' floors). **703 finding-rows resolved** (RC-1b gate makes
      every unmapped built-in a documented carrier + warning; 21 built-ins +
      FK/CHECK/IDENTITY/COMMENT translate faithfully; RC-2 LOG; Oracle ON UPDATE).
      `FINDINGS.md` pruned to the residual; **259 cases flipped `[open]→[fixed]`**
      (603 remain `[open]` = func-diff collation/integer-division/LENGTH/NULL
      floor + still-invalid DDL/type/operator + harder silent-drops). Original RED
      batch context (kept for provenance):
      a RED batch (2026-07-17/18; start commit `dac260f`) generated valid
      per-engine source, validated each original on a live DB, transpiled to the
      other three engines, and validated/**executed** the output. **Only silent
      problems are recorded — a construct that degrades WITH a warning is a
      documented, acceptable outcome and was excluded** (~335 warned rows
      dropped; the `carrier` kind is intentionally gone). Ledger in
      [`tests/fixtures/challenge/FINDINGS.md`](../../tests/fixtures/challenge/FINDINGS.md),
      which opens with a **prioritized class list**. **1800 silent-defect rows**:
      **1322 invalid-output** (unmapped function/type → the target engine rejects
      it, no warning), **401 functional-equivalence** (runs clean but returns a
      *different result* — executed on both engines: integer division, NULL/
      collation ordering, `LOG` base, `CAST(x AS INT)` round-vs-truncate,
      `ROUND(x,n)` precision + half-even, `LENGTH` bytes-vs-chars, `LEN` trailing
      -space, `GREATEST/LEAST/CONCAT` NULL, Oracle `||`-null / `''`-is-NULL, `TOP
      … WITH TIES`, MySQL `date-date` numeric, `'5'+'5'`, bitwise sign/precedence,
      float precision, decimal scale, CHAR-pad WHERE filtering, int=varchar JOIN
      coercion, UNION/CASE type resolution, TO_CHAR format masks), **75 silent
      clause-drops**
      (FK `ON DELETE/UPDATE`, CHECK, COLLATE, IDENTITY/sequence seed, UNSIGNED,
      window frame, ROLLUP, EXCLUDE, column COMMENT, BIT-width), **2 semantic**.
      Each is a `-- CASE[open]:` in the per-engine scripts. **BLUE** works these
      down within the existing rules/architecture: fix at the AST layer, flip the
      case to `[fixed]` with an assertion, remove it from the ledger. Highest
      value first: the **functional-equivalence** rows (silent wrong results) and
      the **clause-drops** (data integrity).

  - **RESOLUTION (2026-07-18 BLUE round).** The tractable, architecture-respecting
    work is COMPLETE across all four root causes; what remains is the documented
    architectural floor (needs schema/type/collation awareness) plus a few
    structural DDL features. Landed: **RC-1b** invalid-class gate (DML +
    procedural) — no unmapped built-in ships silently invalid; **RC-3**
    clause-drops FK/CHECK + IDENTITY seed/step; **RC-2** LOG arg order; **RC-1a**
    21 built-ins faithfully mapped, every one live-verified (LEFT, SPACE, POWER/
    SQUARE/COT/PI, LN, ATAN2, LAST_DAY, QUARTER, DAYNAME, DEGREES, RADIANS, RAND,
    REPEAT, STUFF, MEDIAN, JSON_ARRAYAGG, ELT, FIELD, ADD_MONTHS-with-sticky-last
    -day). **Floor (not liquidatable at statement level):** RC-2 collation /
    integer-division / LENGTH-bytes / NULL-propagation (need per-column type or
    collation); RC-3 COLLATE (collation-name map), column COMMENT (separate
    `COMMENT ON` statements), UNSIGNED (→ CHECK ≥0 is a structural choice), window
    frame / ROLLUP / EXCLUDE, Oracle no-`ON UPDATE`; RC-1a tail without a faithful
    form (TRANSLATE, INITCAP, SOUNDEX, base conversions, WEEKDAY, MONTHS_BETWEEN,
    CBRT, UNIX_TIMESTAMP timezone, MONTHNAME case/pad) — all now degrade honestly.
    Corpus `[open]→[fixed]` flip / `FINDINGS.md` prune is outstanding bookkeeping
    (the now-warned rows are no longer SILENT, so out of the ledger's scope).

  - **RC-1b foundation landed (BLUE, Block 1).** Root-cause of the **invalid**
    class (1322 rows): an unmapped scalar function/type shipped verbatim with no
    warning — the target-parse gate missed it because sqlglot parses unknown
    functions leniently across dialects. Fix = an authoritative per-engine
    **built-in catalog** (`unique.core.builtins`, generated by
    `scripts/gen_builtins.py` from live `pg_proc`/`V$SQLFN_METADATA`/
    `mysql.help_topic` + curated T-SQL, ∪ a grammar-level SQL-standard set) plus
    a source-built-in leak scan in `core/output_gate.py`: a call whose emitted
    name is a source built-in but not a target built-in degrades WHOLE to the
    documented carrier + warning; a non-built-in name is a **user object**
    (UDF/proc) and passes through. **56% of the invalid DML rows (728/1280) now
    degrade honestly** with zero suite regressions (`test_unmapped_builtin_gate.py`).
    Remaining scope: (Block 2) the same scan for **procedural** bodies; (RC-1a)
    add real mappings so built-ins with a target form *translate* instead of
    degrading; then RC-2 (func compensations, annotated) and RC-3 (clause-drops).

  - **Block 2 landed (`d24c27c`)** — the scan now covers routine bodies too;
    MySQL catalog completeness fixed (help_topic miscategorises REPLACE/IF/…),
    table-position names (`INSERT INTO line`) excluded.
  - **RC-3 FK/CHECK landed (Block 3).** Inline column-level constraints
    (`c INT REFERENCES p(id) ON DELETE …`, `c INT CHECK (…)`) were dropped by the
    CREATE TABLE converter (it read only NOT NULL/IDENTITY/PK/UNIQUE/DEFAULT) —
    silent loss of referential integrity / validation. Now routed to the
    table-level constraint path and emitted per-target
    (`tests/integration/test_clause_drops.py`).
  - **RC-3 IDENTITY seed/step landed.** `IDENTITY(100, 5)` dropped its seed/step
    (→ `SERIAL`/`AUTO_INCREMENT`/bare `GENERATED`, all restarting at 1) — silent
    data loss. `ColumnDefinition` gained `identity_seed`/`identity_step`, the
    converter reads sqlglot's `start`/`increment`, and the emitter preserves them
    on tsql `IDENTITY(s,t)`, oracle/pg `GENERATED … (START WITH s INCREMENT BY t)`
    (live: pg yields 100, 105); the (1,1) default keeps idiomatic SERIAL. MySQL
    keeps `AUTO_INCREMENT` — it has no per-column step and the seed is a table
    option (documented limit).
  - **RC-3 column COMMENT landed.** A column comment was dropped; now inline on
    MySQL, a trailing `COMMENT ON COLUMN t.c IS '…'` on PG/Oracle, and a plain
    note on T-SQL (sp_addextendedproperty is too verbose to synthesise safely).
    `ColumnDefinition.comment`, converter reads `CommentColumnConstraint`.
  - **RC-3 Oracle `ON UPDATE` fixed + `UNSIGNED` documented.** Oracle has no
    `ON UPDATE` referential action; the emitter now strips it (keeps FK +
    `ON DELETE`) instead of shipping invalid DDL — documented in
    `docs/03-unsupported.md`. `UNSIGNED` widens to BIGINT (range preserved); the
    ≥0 constraint is a documented partial (auto-`CHECK` would over-reach).
    **Still dropped silently (RC-3 backlog, delicate):** column `COLLATE`
    (collation names differ per engine → needs a name map or honest degrade),
    window `ROWS/RANGE` frame, `WITH ROLLUP`, `EXCLUDE` — each needs modelling
    beyond a one-liner.
  - **RC-2 (func-diffs) — LOG arg order fixed; rest is the delicate floor.**
    The IR is canonical `LOG(base, x)`; T-SQL spells it `LOG(x, base)`, so the
    emitter swaps only when the target is T-SQL (a lossless correctness fix — the
    naive source-keyed transform double-swapped because the parser already
    canonicalises T-SQL's order; sqlglot handles LOG end-to-end, the IR emit path
    did not). `tests/integration/test_log_arg_order.py`. **The remaining func-diff
    classes are the delicate/architectural floor** and need per-column type or
    collation knowledge that is undecidable at statement level: string collation
    (`'Ä'='A'`, case/accent — 94 rows, the largest cluster), integer division
    (`5/2` — needs operand types), `LENGTH` bytes-vs-chars (a semantic judgement —
    forcing `OCTET_LENGTH`/`DATALENGTH` everywhere over-reaches; warn instead),
    NULL-propagation in `GREATEST`/`LEAST`/`CONCAT`, Oracle `''`-is-NULL and
    `||`-null, `CAST` float→int round-vs-truncate. These want a schema-aware /
    warn-on-divergence pass, not a per-spelling rewrite — the user's own caution
    ("RC-2 es delicado"); handling one wrong ships silent bad data.

  - **RC-1a mapping opportunities — systematic 2026-07-18 sweep, all
        LIVE-VERIFIED (value, not just parse). LANDED:**
    - [x] `LAST_DAY(d)` → tsql `EOMONTH(d)`, pg
        `CAST(DATE_TRUNC('month',d) + INTERVAL '1 month' - INTERVAL '1 day' AS DATE)`
        (live: 2020-05-31, leap 2020-02-29).
    - [x] `QUARTER(d)` (mysql) → tsql `DATEPART(QUARTER,d)`, pg `EXTRACT(QUARTER FROM d)`,
        oracle `TO_NUMBER(TO_CHAR(d,'Q'))` (live: 2).
    - [x] `DAYNAME(d)` (mysql) → tsql `DATENAME(WEEKDAY,d)`, oracle `TO_CHAR(d,'fmDay')`,
        pg `TO_CHAR(d,'FMDay')` (live: 'Friday'; locale = session NLS, like collation).
    - [x] `DEGREES`/`RADIANS` → oracle `(x*180/ACOS(-1))` / `(x*ACOS(-1)/180)` (live exact).
    - [x] `RAND()` → oracle `DBMS_RANDOM.VALUE`; `REPEAT(s,n)` → oracle `RPAD(s,LENGTH(s)*n,s)`.
    - [x] `STUFF(s,start,len,new)` (tsql) → pg `OVERLAY(...)`, mysql `INSERT(...)`,
        oracle `SUBSTR(s,1,start-1)||new||SUBSTR(s,start+len)` (Oracle has no OVERLAY —
        caught live; live: 'aXYZef').
    - [x] `MEDIAN(x)` (oracle) → pg `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)`
        (live: 2.5); `JSON_ARRAYAGG(x)` (mysql) → pg `JSON_AGG(x)` (live: [1,2]).
    - [x] `ELT(n,…)`/`FIELD(v,…)` (mysql) → portable CASE chains (live: ELT
        out-of-range→NULL, FIELD not-found→0).
    - [x] `ADD_MONTHS(d,n)` (oracle) — the sticky-last-day CASE lands after all:
        `CASE WHEN d = lastday(d) THEN lastday(d+n·mo) ELSE d+n·mo END`, using each
        target's last-day primitive (mysql `LAST_DAY`, tsql `EOMONTH`, pg
        DATE_TRUNC). Live-verified vs Oracle on all three targets across the sticky
        Feb-29→Mar-31 edge, clamps, negative n, leap years — all exact.
    - **Still open (mappable but needs more than a one-liner):** `MONTHNAME`
      (sqlglot decomposes it to TIME_TO_STR — handle upstream), `NEXT_DAY`,
      `UNIX_TIMESTAMP`/`FROM_UNIXTIME` (epoch), `WEEK` (mode),
      `MEDIAN`→tsql (window-only form).
    - **Floor after LIVE checks proved a value divergence:** `CBRT`
      (`POWER(ABS,1/3)` is `2.9999…` not `3` — float precision).
    - **Confirmed floor (no faithful equivalent — keep degrading honestly):**
      `TRANSLATE`→mysql/tsql (char map+delete), `INITCAP`→mysql/tsql, `SOUNDEX`→pg
      (needs fuzzystrmatch), `QUOTENAME`→others, `FORMAT` (locale), `SUBSTRING_INDEX`,
      `HEX`/`BIN`/`OCT`/`CONV`/`CRC32` (base conv), `WEEKDAY` (DATEFIRST-dependent),
      `MONTHS_BETWEEN`→mysql/pg (fractional).

- [x] **Duplicate `SET NOCOUNT ON` on `oracle`/`pg`/`mysql` → T-SQL (P2)** — the
      T-SQL procedure emitter injects `SET NOCOUNT ON` as a best-practice
      default, but did so even when the body already opened with one (an
      explicit author directive, or the restored `/* UNIQUE: SET NOCOUNT ON … */`
      round-trip carrier) — emitting it twice, and forcing `ON` in front of an
      explicit `SET NOCOUNT OFF`. Fixed: `emitter.base._emit_procedure_body`
      suppresses the injection when the first executable statement is already a
      `SET NOCOUNT` directive (`_body_manages_nocount`). Removed a dead,
      identically-buggy `_emit_tsql_procedure_body` duplicate. Covered by
      `tests/integration/test_tsql_nocount.py`.
- [x] **Oracle self-qualified parameter `<routine>.<param>` mangled → T-SQL/MySQL
      (P2)** — Oracle lets a body reference a formal parameter as
      `usp_get.topfilas`; the parameter rename treated any qualified name as a
      column, so it was left un-renamed (`WHERE n = usp_get.topfilas`) and, in a
      `FETCH FIRST` count, sqlglot could not parse it and dropped `.topfilas`
      (`FETCH FIRST usp_get`). Fixed: `transformer.base._strip_self_qualified_params`
      drops the `<routine>.` qualifier before the rename when the qualifier is
      the routine's own name and the suffix is a known parameter (a real
      table/alias of the same name is untouched). Covered by
      `tests/integration/test_challenge.py`.

## 42. Items archived from TODO on 2026-07-18 (completed checkboxes)

### From: §2 Audit follow-ups (P3)

- [x] **Prune fallback-only text rewriters (P3) — CLOSED BY MEASUREMENT
      2026-07-17:** a coverage run over ALL real material (both corpora,
      the procedures fixtures and the three private fixtures, every
      direction) shows **36 of 37 rewriters still receive fallback
      traffic** — the IR-declined fragments (parse failures, mid-transform
      hybrids) are real and the text fallback is their working surface.
      The single zero-traffic method (`_map_mysql_datefmt_to_oracle`, 8
      lines) is a helper of a live method and reachable by real
      mysql→oracle date formats outside the corpus — deleting it would
      break the fallback with no replacement. Conclusion: nothing is
      safely prunable; the fallback surface stays as-is. (Harness: the
      scratchpad coverage run with COVERAGE_CORE=sysmon; the timed-out
      first attempt without sysmon is the reminder to always use it.)

- [x] **tsql→mysql procedural DATEADD nested INTERVAL — FIXED 2026-07-17**
      (same day it was filed): `_mysql_normalize_funcs`'s sqlglot
      round-trip re-emitted a tsql-read `DateAdd` carrying its whole
      `Interval` in the *expression* slot through the mysql generator,
      which invents an implicit DAY unit (`INTERVAL (INTERVAL '-1'
      MONTH) DAY` — invalid MySQL and a silent unit change). The
      normalize walk hoists the interval into the expression/unit
      slots. Test: TestDateAddUnderConvertMySql.

### From: §4 T-SQL keyword coverage (all complete)

- [x] **`PROC` abbreviation of `PROCEDURE` (P2)** — T-SQL accepts `PROC` in
      `CREATE`/`ALTER`/`DROP`; the abbreviated spelling was mishandled while the
      full one worked (`CREATE PROC`/`ALTER PROC` degraded to an "Unhandled
      CREATE" carrier; `DROP PROC` leaked the T-SQL-only `PROC` keyword into
      PG/Oracle/MySQL output — invalid there). Fixed at three layers: the
      procedural-routing regex (`batch_splitter._PROCEDURAL_PATTERNS["tsql"]`)
      matches `PROC(?:EDURE)?`; the procedural lexer normalizes `PROC` →
      `PROCEDURE` only in the `CREATE`/`ALTER` keyword position (a column/object
      named `proc` stays an identifier); and `converter._normalize_ddl_kind`
      canonicalizes the DROP/CREATE `kind`. Covered by
      `tests/integration/test_tsql_keyword_alias.py`. The other two documented
      T-SQL statement abbreviations already work: `EXEC`≡`EXECUTE` and
      `TRAN`≡`TRANSACTION` on `COMMIT`/`ROLLBACK`/`SAVE`.
- [x] **`CREATE OR ALTER {PROCEDURE|PROC}` (P2)** — the T-SQL 2016+
      `CREATE OR ALTER` form (distinct from `CREATE OR REPLACE`) fell to the DML
      path and degraded to an "Unhandled CREATE PROCEDURE" carrier. Fixed: the
      routing regex accepts `CREATE\s+OR\s+ALTER`, `parser._parse_create`
      consumes the `OR ALTER` prefix like `OR REPLACE` (both set `or_replace`),
      and the T-SQL emitter now honors `or_replace` — so `CREATE OR ALTER`
      round-trips and Oracle/PG `CREATE OR REPLACE` ↔ T-SQL `CREATE OR ALTER`.
      Covered by `tests/integration/test_challenge.py` + `test_procedural.py`.
- [x] **`BEGIN TRAN[SACTION]` (P2)** — a standalone begin-transaction degraded to
      "Unhandled expression type: Transaction". Fixed: the converter passes
      `exp.Transaction` through (kind `BEGIN TRANSACTION`) so sqlglot renders
      T-SQL `BEGIN TRANSACTION` / PG+MySQL `BEGIN`; Oracle (implicit
      transactions) drops it to a documented carrier + warning in
      `emit._emit_passthrough` rather than a bare invalid `BEGIN`.
      `COMMIT`/`ROLLBACK`/`SAVE` already mapped. Covered by
      `tests/integration/test_challenge.py`. (A multi-statement `BEGIN TRAN … `
      `COMMIT` in ONE semicolon-less batch is a separate splitter limitation.)
