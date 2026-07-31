[← All rationale topics](../README.md)

# Procedural: cursors, dynamic SQL, system procedures, session directives

Stored-procedure/function/trigger bodies parsed into an IR and re-emitted in
the target dialect — cursors, error handling, dynamic SQL, system procedures,
and client-tool directives. See [README.md](../README.md) for the entry format
and sourcing rules.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## System procedures

| Article | Direction | Description |
|---|---|---|
| [`EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL](exec-sp-degrade-policy.md) | tsql → oracle/postgresql/mysql | T-SQL system procedures (`sp_rename`, `sp_who`, …) call into SQL Server's own catalog/admin machinery. |
| [Statement-after-`EXEC` survival fix](statement-after-exec-survival.md) | tsql → all | A degraded system-proc `EXEC`, followed by another statement on the same line separated only by `;` (not a batch-separating `GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`. |

## `SET IDENTITY_INSERT` coherent degrade

| Article | Direction | Description |
|---|---|---|
| [`SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL](set-identity-insert-degrade.md) | tsql → oracle/postgresql/mysql | T-SQL requires `IDENTITY_INSERT` to be explicitly turned `ON` before a script can supply its own value for an identity column, then turned back `OFF`. |

## SQL*Plus directives preserved as comments

| Article | Direction | Description |
|---|---|---|
| [`SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL](sqlplus-client-directives.md) | oracle → tsql/postgresql/mysql | SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`, etc.) are **line-oriented client-tool commands**, not SQL statements — they carry no trailing `;` and configure the SQL*Plus session, not the database. |

## `%TYPE` / `%ROWTYPE` carrier without `--db-url`

| Article | Direction | Description |
|---|---|---|
| [Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL](oracle-type-rowtype-references.md) | oracle → tsql/postgresql/mysql | `v_id employees.id%TYPE` declares a variable with **whatever type** the referenced column currently has — a live binding to the schema, not a fixed type name. |

## Cursor attribute mapping

| Article | Direction | Description |
|---|---|---|
| [Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL](oracle-cursor-attributes.md) | oracle → tsql/mysql | Oracle attaches state to each named cursor: `c%FOUND`/`c%NOTFOUND` (did the last `FETCH` return a row), `c%ISOPEN`, and `c%ROWCOUNT` (rows fetched so far on that cursor). |
| [PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`](implicit-found-flag.md) | oracle/postgresql → tsql/mysql | PL/pgSQL keeps one implicit boolean, `FOUND`, updated by the *last* `SELECT INTO`, `UPDATE`, `DELETE`, `INSERT`, or `FETCH` in the routine — it answers "did that last statement affect/return a row?" for the routine as a whole, not for one named cursor. |
| [T-SQL `@@FETCH_STATUS` → Oracle / PostgreSQL / MySQL](tsql-fetch-status-to-oracle-postgresql-mysql.md) | tsql → oracle/postgresql/mysql | T-SQL exposes cursor state through a single global variable, `@@FETCH_STATUS`, checked right after a `FETCH` (`0` = a row was returned, `-1` = no more rows, `-2` = the fetched row is missing). |

## Error handling

| Article | Direction | Description |
|---|---|---|
| [MySQL `DECLARE {EXIT\|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)](mysql-declare-handler.md) | mysql → tsql/oracle/postgresql | MySQL declares an error handler *separately* from the code it protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in the block's declaration section, naming the condition(s) it reacts to and a single action statement. |

## Expression arguments hoisted through a synthesized variable

| Article | Direction | Description |
|---|---|---|
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](raiserror-expression-messages.md) | tsql ↔ oracle/postgresql | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [EXEC / routine-call expression argument (Oracle) → synthesized variable (T-SQL)](exec-expression-argument-hoist.md) | oracle → tsql | A T-SQL `EXEC` call accepts only a literal, a variable, or `DEFAULT`/`NULL` in its argument list — never an arbitrary expression. |

## Dynamic SQL constant translation

| Article | Direction | Description |
|---|---|---|
| [A constant dynamic-SQL string (T-SQL `EXEC sp_executesql` / Oracle `EXECUTE IMMEDIATE` / PL/pgSQL `EXECUTE`) → any target](constant-dynamic-sql-string.md) | cross-engine | Dynamic SQL executes a string built at runtime. |

## Return-type and signature synthesis

| Article | Direction | Description |
|---|---|---|
| [Return-type and signature synthesis](return-type-synthesis-overview.md) | overview | Two shapes where a routine's own declared **signature** has to change shape to satisfy the target grammar, not just its body: a PostgreSQL function that declares no return value at all, and a procedure whose body streams a result set that PL/SQL cannot express without an extra parameter. |
| [`RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)](returns-void-signature-synthesis.md) | postgresql → tsql/oracle/mysql | A PostgreSQL function declared `RETURNS void` returns nothing — per the corpus's own count, the single most common plpgsql function shape (62 occurrences), typically a side-effecting helper invoked for its `INSERT`/`UPDATE`, never for a value. |
| [A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → a ref-cursor parameter (Oracle `SYS_REFCURSOR` OUT, PostgreSQL `refcursor` INOUT), propagated to `CALL` sites](bare-result-select-to-refcursor.md) | tsql/mysql/postgresql → oracle/postgresql | A MySQL or T-SQL procedure can hand back a result set simply by running a `SELECT` with no `INTO` target partway through the body. |
| [T-SQL scalar function: synthesized trailing `RETURN NULL` after an all-branches-return `IF`/`ELSE`](scalar-function-trailing-return-null.md) | postgresql/oracle → tsql | T-SQL requires a scalar function's **last statement** to literally *be* a `RETURN` (error 455 otherwise) — even when the function's body already returns a value on every possible branch, such as an `IF ... |

## Other `[limit]` procedural entries

| Article | Direction | Description |
|---|---|---|
| [Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL](scroll-cursor-fetch.md) | tsql → oracle/postgresql/mysql | A T-SQL `SCROLL` cursor supports non-forward fetches: `FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc. |

## Comments written before a routine header

| Article | Direction | Description |
|---|---|---|
| [Comments written before a routine header](comments-before-routine-header.md) | overview | You annotate a routine from the outside — `-- author note` lines immediately before `CREATE PROCEDURE` — and expect them to survive the migration. |

## Triggers

| Article | Direction | Description |
|---|---|---|
| [Triggers](triggers-overview.md) | overview | The firing-mode surface that differs between engines: row-level (`FOR EACH ROW`, `NEW`/`OLD`) vs. statement-level (T-SQL's `inserted`/`deleted`), timing (`INSTEAD OF`), and each engine's own trigger-declaration shape. |
| [Row-level trigger body (`SET NEW.col = expr`) → T-SQL statement-level `UPDATE ... WHERE ... IN (SELECT ... FROM inserted)`](row-level-trigger-body-to-tsql.md) | cross-engine | A MySQL/PL-SQL row-level trigger (`FOR EACH ROW`) runs once per affected row, with `NEW`/`OLD` bound to that single row. |
| [Oracle event predicates (`INSERTING`/`DELETING`/`UPDATING('col')`) → per-engine rewrite](oracle-trigger-event-predicates.md) | cross-engine | An Oracle trigger body asks, inline, "did this statement INSERT/DELETE/UPDATE, and did this specific column change" via `INSERTING`/`DELETING`/`UPDATING('col')`. |
| [PL/pgSQL trigger context variables (`TG_NAME`/`TG_TABLE_NAME`/`TG_OP`/`TG_WHEN`/`TG_LEVEL`, `TG_ARGV`/`TG_NARGS`) → compile-time constants once the function inlines](plpgsql-trigger-context-variables.md) | cross-engine | Inside a plpgsql trigger function, `TG_NAME`/`TG_TABLE_NAME`/ `TG_OP`/`TG_WHEN`/`TG_LEVEL` are implicit variables PostgreSQL's trigger machinery populates at fire time, and `TG_ARGV[n]`/`TG_NARGS` read the argument list supplied by the specific `CREATE TRIGGER ... |
| [PG named transition tables (`REFERENCING ... TABLE AS alias`) → T-SQL `inserted`/`deleted` alias rename](pg-named-transition-tables.md) | cross-engine | A PostgreSQL statement trigger can name its transition tables (`REFERENCING NEW TABLE AS newtab`), and the inlined function body reads rows through that chosen alias. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](trigger-reading-own-table.md) | postgresql/mysql ↔ oracle | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [T-SQL `INSTEAD OF` trigger → PostgreSQL (native on views, emulated on tables)](tsql-instead-of-trigger.md) | tsql → postgresql | T-SQL allows `INSTEAD OF` on both views *and* base tables — the trigger body runs **instead of** the attempted INSERT/UPDATE/DELETE, which is never applied on its own. |
| [Trigger body → PostgreSQL `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER`](trigger-body-to-pg-function.md) | cross-engine | PostgreSQL has no inline trigger body: `CREATE TRIGGER` only *names* a function, which must already exist and return `TRIGGER`. |
| [Bare `RETURN;` inside a PostgreSQL trigger function's nested handler → `RETURN NEW;`](pg-trigger-bare-return.md) | cross-engine | Oracle's bare `RETURN;` inside an exception handler simply leaves the trigger (there is no return value to supply there). |
| [Empty trigger body → synthesized `SET NOCOUNT ON;` no-op (T-SQL)](empty-trigger-body-noop.md) | cross-engine | T-SQL forbids an empty statement block: `BEGIN END` alone after a trigger header is a syntax error. |

## Loop and cursor desugaring

| Article | Direction | Description |
|---|---|---|
| [Loop and cursor desugaring](loop-cursor-desugaring-overview.md) | overview | T-SQL cursor *variables*, PL/SQL/Oracle cursor `FOR` loops, and numeric range `FOR` loops all bind their query/bounds and their iteration into a single declarative statement. |
| [T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL](tsql-cursor-variable-binding.md) | tsql → oracle/postgresql/mysql | T-SQL lets a cursor be bound to a *variable* in two steps: a bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... |
| [PL/SQL `FOR rec IN cur LOOP` (Oracle) → T-SQL explicit cursor scaffold](cursor-for-loop-to-tsql.md) | oracle → tsql | A PL/SQL cursor `FOR` loop declares nothing: it implicitly opens the cursor, fetches one row per iteration into a record `rec`, and closes it when the cursor is exhausted — `rec.col` reads that iteration's column. |
| [PL/SQL cursor `FOR` loop (Oracle) → MySQL explicit cursor scaffold](cursor-for-loop-to-mysql.md) | oracle → mysql | The same implicit fetch-and-bind PL/SQL construct as above, but onto MySQL, whose procedural dialect additionally requires every `DECLARE` to sit at the very top of its enclosing `BEGIN` block (MySQL error 1337) and has no `WHILE @@FETCH_STATUS` equivalent — loop termination is driven by a `CONTINUE HANDLER FOR NOT FOUND`. |
| [Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter](numeric-range-for-loop.md) | oracle → tsql/mysql | `FOR i IN 1..13 LOOP` (optionally `REVERSE`) is Oracle's counting loop — no cursor at all, just an integer range. |
| [Bare `RETURN` in a MySQL procedure → labeled `proc_exit:` block + `LEAVE`](mysql-bare-return-to-leave.md) | cross-engine | MySQL forbids `RETURN` anywhere inside a `PROCEDURE` body ("RETURN is only allowed in a FUNCTION") — but an early-exit bare `RETURN` (no value) is ordinary control flow in T-SQL/Oracle/PostgreSQL procedures. |
| [Leading `DECLARE` block reordered (MySQL): variables before cursors](mysql-declare-reorder.md) | mysql | MySQL requires every `DECLARE <cursor>` to come *after* every `DECLARE <variable>` in the same block (error 1337, "Variable or condition declaration after cursor or handler declaration") — a rule no other target engine imposes, so a source routine that declares its cursor before its scalar variables (a legal order on Oracle/T-SQL/PostgreSQL) needs its leading declaration block reordered for MySQL specifically. |
| [T-SQL loop control (`BREAK`/`CONTINUE`, compound assignment) → MySQL labeled `LEAVE`/`ITERATE`](tsql-loop-control-to-mysql-labels.md) | tsql → mysql | T-SQL's `BREAK`/`CONTINUE` act on the *nearest enclosing* loop with no name required. |

## Topics left out for lack of source support

| Article | Direction | Description |
|---|---|---|
| [Topics left out for lack of source support](topics-left-out.md) | overview | - **Ref cursor `OUT` parameters** (`SYS_REFCURSOR`) and **`EXECUTE IMMEDIATE … USING bind1, bind2`** Oracle→T-SQL specifics are documented in `docs/03-unsupported.md` §6, but no challenge-corpus case exercises either construct, so no dedicated entry is made here to avoid inventing an example. |

## Dynamic-SQL loop-to-aggregate rewrite

| Article | Direction | Description |
|---|---|---|
| [A row-by-row dynamic-SQL string build (T-SQL) → a single Oracle `LISTAGG` + `EXECUTE IMMEDIATE`](dynamic-sql-loop-to-listagg.md) | tsql → oracle | A common T-SQL pattern builds a dynamic-SQL string by looping over a result set implicitly, appending to the same variable on every row: `SELECT @sql = @sql + expr FROM t`. |

## Oracle CAST length: PL/SQL body vs. top-level SQL

| Article | Direction | Description |
|---|---|---|
| [A lengthless character `CAST` reaching Oracle: valid inside a PL/SQL body, invalid as a bare top-level statement](oracle-cast-length-plsql-body-vs-sql-statement.md) | tsql → oracle | A T-SQL cast to a character type with **no length given at all** (a bare `CAST(x AS VARCHAR)`, as opposed to `VARCHAR(n)`) needs opposite treatment depending on where it lands on Oracle. |

## Anonymous block flattening

| Article | Direction | Description |
|---|---|---|
| [Oracle top-level anonymous block (`DECLARE … BEGIN … END;`) → a plain T-SQL batch](anonymous-block-flattens-to-tsql.md) | oracle → tsql | Oracle's top-level anonymous block — `DECLARE ... |

## Subquery-in-expression assignment restructuring

| Article | Direction | Description |
|---|---|---|
| [T-SQL subquery-in-expression assignment → Oracle `SELECT ... INTO ... FROM DUAL`](tsql-subquery-assignment-to-oracle-select-into.md) | tsql → oracle | T-SQL lets a variable assignment's right-hand side embed a subquery directly, either as the whole expression or nested inside another call: `SET @x = (SELECT MAX(a) FROM t)`, or `DECLARE @x INT = (SELECT MAX(a) FROM t)` as an initializer. |

## T-SQL scalar UDF auto-qualification

| Article | Direction | Description |
|---|---|---|
| [An unqualified scalar function call → `dbo.`-qualified on T-SQL](tsql-udf-auto-qualification.md) | cross-engine | T-SQL requires a user-defined scalar function call to be schema-qualified (`dbo.fn(...)`); an unqualified call is error 195, "not a recognized built-in function name," even when a function of that name exists in the target database. |

## SET NOCOUNT ON best-practice default

| Article | Direction | Description |
|---|---|---|
| [A T-SQL procedure body gains a synthesized `SET NOCOUNT ON;` by default](nocount-injected-default.md) | cross-engine | SQL Server's documented best practice for every stored procedure is `SET NOCOUNT ON` — it suppresses the "N row(s) affected" message that would otherwise ride along on every DML statement, cluttering client output and, over a network round trip, costing real time. |

## Dynamic SQL INTO capture

| Article | Direction | Description |
|---|---|---|
| [`EXECUTE IMMEDIATE '<sql>' INTO x` (Oracle) → a two-statement T-SQL capture](execute-immediate-into-capture.md) | oracle → tsql/postgresql | Oracle's `EXECUTE IMMEDIATE '<sql>' INTO x` runs a dynamic query and captures its single-row result directly into a variable — PostgreSQL's `EXECUTE '<sql>' INTO x` is the same idiom natively. |

## Base64 decode idiom

| Article | Direction | Description |
|---|---|---|
| [T-SQL's `CAST(N'' AS XML).value('xs:base64Binary(...)', ...)` base64-decode idiom → each target's native call](base64-xml-idiom-per-target.md) | tsql → oracle/postgresql/mysql | T-SQL has no direct `BASE64_DECODE` function; the idiomatic way to decode a base64 string into binary is to route it through the XML type system — `CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@x"))', 'VARBINARY(MAX)')`. |

## ERROR_MESSAGE() function mapping

| Article | Direction | Description |
|---|---|---|
| [T-SQL `ERROR_MESSAGE()` (inside a `CATCH` block) → each target's own error-text accessor](error-message-function-per-target.md) | tsql → oracle/postgresql/mysql | Inside a T-SQL `CATCH` block, `ERROR_MESSAGE()` reads the text of the error that was just caught. |

## Mid-block DECLARE hoisted to the routine's top declaration section

| Article | Direction | Description |
|---|---|---|
| [A `DECLARE` written mid-block (inside an `IF`/`CATCH`) → hoisted to the routine's top declaration section](mid-block-declare-hoist.md) | tsql → postgresql/mysql/oracle | T-SQL allows `DECLARE @v type = init;` anywhere a statement is legal — inside an `IF` body, inside a `CATCH` block, nested arbitrarily deep. |

## SELECT ... INTO :NEW.col pseudo-row targets

| Article | Direction | Description |
|---|---|---|
| [`SELECT ... INTO :NEW.col1, :NEW.col2` (Oracle trigger) → PostgreSQL `NEW.col`, MySQL session variables](pseudo-row-into-mysql-session-vars.md) | oracle → postgresql/mysql | An Oracle row-level trigger can `SELECT ... |

## Package ref-cursor type resolution and usage-inferred mode

| Article | Direction | Description |
|---|---|---|
| [A package-qualified ref-cursor type (`pkg.my_cursor`) → the target's own ref-cursor type](refcursor-package-type-and-inout-mode.md) | oracle → postgresql/oracle/mysql | An Oracle procedure parameter can be typed with a package-defined `REF CURSOR` subtype (`v_cur OUT pkg_ret.my_cursor`) — `pkg_ret.my_cursor` is only meaningful *inside that package*, never on a target with no package concept at all. |

## Top-level batch wrapped for PL/pgSQL-only constructs

| Article | Direction | Description |
|---|---|---|
| [A top-level T-SQL/Oracle batch needing a procedural construct → PostgreSQL `DO $$ ... $$`](toplevel-batch-do-block-wrap.md) | tsql/oracle → postgresql | A standalone (not-inside-a-`CREATE PROCEDURE`) T-SQL batch or Oracle anonymous block can freely mix `PRINT`/`DBMS_OUTPUT`, variable declarations, `IF`, cursor `FOR` loops, and dynamic `EXECUTE` — all procedural constructs that only exist *inside* a routine body on PostgreSQL. |

## Local variable renamed to avoid an Oracle built-in collision

| Article | Direction | Description |
|---|---|---|
| [A local variable named after an Oracle built-in (`count`) → renamed everywhere it's used](oracle-builtin-name-collision-rename.md) | postgresql → oracle | `count` is a perfectly legal PL/pgSQL local variable name — PostgreSQL has no keyword collision. |

## THROW/RAISERROR numeric error code

| Article | Direction | Description |
|---|---|---|
| [T-SQL `THROW`/`RAISERROR`'s numeric error code → each target's own error-code slot](throw-raiserror-numeric-code-per-target.md) | tsql → oracle/postgresql/mysql | T-SQL's `THROW 50001, 'not found', 1` and `RAISERROR('not found', 16, 1)` (with a matching custom message id registered separately) both carry a *numeric error code* alongside the message text. |

## Constrained CAST hoisted through SELECT ... INTO ... FROM DUAL

| Article | Direction | Description |
|---|---|---|
| [A constrained numeric `CAST` inside a PL/SQL expression → hoisted through `SELECT ... INTO ... FROM DUAL`](constrained-cast-hoisted-select-into-dual.md) | tsql → oracle | Oracle's PL/SQL forbids a *constrained* type (one with a precision/scale, like `DECIMAL(12, 2)`, or a length) on a `CAST` used directly inside a procedural expression (`PLS-00103`) — only an unconstrained type is legal there. |

## Oracle LOB and numeric-cast helper functions

| Article | Direction | Description |
|---|---|---|
| [Oracle `DBMS_LOB`/`UTL_RAW`/`TO_NUMBER`/`TRUNC` helper calls → T-SQL/MySQL built-ins](oracle-lob-numeric-helpers-to-tsql.md) | oracle → tsql/mysql | Several of Oracle's package-qualified LOB helpers and its bare numeric/date built-ins have no shared name on other engines, and one (`DBMS_LOB.SUBSTR`) even reorders its arguments compared to the target's equivalent. |

## Oracle formal parameter/return types stripped of precision and scale

| Article | Direction | Description |
|---|---|---|
| [T-SQL sized parameter/return types (`DECIMAL(5,2)`, `NVARCHAR(50)`) → unconstrained on an Oracle routine header](oracle-formal-parameter-types-unconstrained.md) | tsql → oracle | Oracle's PL/SQL forbids length, precision, or scale on a *formal parameter* or *function return* type declaration — `PLS-00103` — even though the identical sized type is perfectly legal on a `CREATE TABLE` column. |

## SQLSTATE/SQLCODE read into T-SQL error functions

| Article | Direction | Description |
|---|---|---|
| [PostgreSQL `SQLSTATE` / Oracle `SQLCODE` → `CAST(ERROR_STATE()/ERROR_NUMBER() AS NVARCHAR(n))`](sqlstate-sqlcode-to-tsql-error-functions.md) | postgresql/oracle → tsql | PostgreSQL's `SQLSTATE` and Oracle's `SQLCODE` are bare identifiers, readable directly inside an exception handler as the caught error's state code or numeric code. |

## CONVERT(...,HASHBYTES(...),2) style-2 hex wrapper collapse

| Article | Direction | Description |
|---|---|---|
| [T-SQL `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)` → MySQL's native hash function directly](convert-hashbytes-wrapper-collapse.md) | tsql → mysql | T-SQL has no built-in "digest as a hex string" function — `HASHBYTES(...)` returns raw bytes, so the idiomatic way to get a readable hex digest is to wrap it in `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)`, where style `2` is `CONVERT`'s binary-to-hex-string style code. |

## Dynamic SQL bind arguments copied into session variables

| Article | Direction | Description |
|---|---|---|
| [`EXECUTE IMMEDIATE '...' USING v1, v2` (Oracle) → MySQL `EXECUTE ... USING @v1, @v2`, bound through session variables](mysql-execute-using-session-vars.md) | oracle → mysql | Oracle's `EXECUTE IMMEDIATE '<sql>' USING bind1, bind2` accepts routine locals and parameters directly as bind arguments. |
