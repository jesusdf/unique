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
