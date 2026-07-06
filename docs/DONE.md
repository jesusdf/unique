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
