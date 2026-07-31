# Transpilation rationale

**The wiki our users consult when they don't understand why something
translated the way it did.** A user typically works with one or two engines;
these pages are organized so that view comes first (the by-engine indexes).

The contract (maintainer, 2026-08-01):

- **Scope is the whole application**: every conversion Unique performs that
  is **not a direct equivalence** belongs here — a rewrite, hoist, guard
  synthesis, decomposition, compensation, or creative alternative — whether
  it ends faithful or divergent. The scope is NOT limited to any audit,
  sweep, or test set performed at some point in time; those are verification
  tools, the contract is total coverage.
- Each entry explains the source construct's semantics, the *engine-level*
  reason a direct mapping does not exist, what Unique emits instead, and
  exactly what (if anything) diverges — with the transpiler treated as a
  **black box** (no internals, no project history).
- **Coverage means a rationale article exists.** An entry in
  `docs/03-unsupported.md` counts as coverage only for a *genuine approved
  degradation* (a warned limit); a faithful creative conversion documented
  only there is misfiled — it gets an article here, and 03-unsupported
  cross-links it.

This is the narrative companion to two machine-checked sources of truth:

- [`docs/03-unsupported.md`](../03-unsupported.md) — the normative catalog of
  approved degradations. Every `[limit]` case in the challenge corpus must
  cite it (enforced by `tests/integration/test_challenge.py`).
- `tests/fixtures/challenge/challenge_*.sql` — the regression corpus. Every
  example in these pages is lifted from a corpus case (already live-verified
  on the four engines), never invented.

> **This index is generated — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages under each topic directory. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts or if any relative link in `docs/rationale/**.md` goes stale. The intro above and the appendix below come from the `_index_intro.md` / `_index_appendix.md` partials.

## Topics

| Topic | Covers | Articles |
|---|---|---|
| [Date/time arithmetic and formatting](datetime/README.md) | date/time arithmetic, truncation, unit maps, month-end semantics, epoch rebasing | 15 |
| [Strings, concatenation and collation](strings-collation/README.md) | concatenation & NULL, LIKE/ESCAPE, character classes, collation/order, Oracle `''` ≡ NULL, byte vs char lengths | 29 |
| [Aggregates and window functions](aggregates-windows/README.md) | window frames, ordered aggregates, string aggregation, DISTINCT ON, boolean aggregates | 16 |
| [Booleans: the value/predicate duality](booleans/README.md) | tri-state `CASE` wrap for value position, `<> 0` synthesis for predicate position, boolean-column `IS TRUE`/`IS FALSE` re-spelling | 10 |
| [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md) | PIVOT/UNPIVOT, MERGE/upsert lowering, multi-table DELETE, row caps, row-value comparisons | 28 |
| [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md) | identity/SERIAL, temp tables, FK actions, sequences, storage options | 26 |
| [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md) | cursors, error handling, dynamic SQL, system procedures, session directives | 57 |

## By engine

Each article grouped by the engine it converts **from** and **to** (derived from the `direction` metadata). Cross-engine articles — no single source/target — are listed once at the end.

| Engine | As source | As target |
|---|---|---|
| T-SQL | [as source](#t-sql-as-source) | [as target](#t-sql-as-target) |
| Oracle | [as source](#oracle-as-source) | [as target](#oracle-as-target) |
| PostgreSQL | [as source](#postgresql-as-source) | [as target](#postgresql-as-target) |
| MySQL | [as source](#mysql-as-source) | [as target](#mysql-as-target) |
| Cross-engine | [multi-directional](#cross-engine--multi-directional) |  |

### T-SQL as source

| [Date/time](#datetime-arithmetic-and-formatting) | [Strings](#strings-concatenation-and-collation) | [Aggregates & windows](#aggregates-and-window-functions) | [Booleans](#booleans-the-valuepredicate-duality) | [DML](#dml-pivotunpivot-merge-delete-row-values) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS](datetime/dateadd-month-to-oracle-add-months.md) | T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d, INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the day-of-month* and clamp down only when the target month is shorter: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`). |
| [An ISO date/timestamp string written into a harvested `DATE`/`DATETIME` column → wrapped in an Oracle ANSI literal](datetime/schema-harvested-date-literal-to-oracle.md) | `INSERT INTO evt (d, ts) VALUES ('2024-01-15', '2024-01-15 10:30:00')` relies on the target column's own declared type (`DATE`/`DATETIME`) to interpret a plain ISO string as a date or timestamp — T-SQL, PostgreSQL, and MySQL all accept this implicit string-to-date coercion. |
| [T-SQL `CONVERT(type, value, style)`'s numeric style code → a per-target format function, or ignored when the target type isn't a date](datetime/convert-style-code-per-target.md) | T-SQL's `CONVERT` takes an optional third argument, a numeric *style* code, whose meaning depends entirely on what the second argument is being converted to: against a date/time type, it selects a date format (`120` = ISO `yyyy-mm-dd hh:mi:ss`, `103` = British/French `dd/mm/yyyy`, ...); against a non-date type, the style code is only meaningful for a handful of special cases (binary-to-string encodings) and is otherwise ignored. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [3-argument `CHARINDEX(needle, s, start)` (T-SQL) → PostgreSQL zero-guarded `POSITION`](strings-collation/charindex-start-argument-zero-guard.md) | T-SQL's `CHARINDEX(needle, s, start)` searches only from `start` onward, and returns `0` (not `NULL`) when the needle isn't found anywhere from `start` on. |
| [Unary bitwise `~x`/NOT → Oracle `-(x) - 1`, MySQL `CAST(~x AS SIGNED)`](strings-collation/unary-bitwise-not-emulation.md) | PostgreSQL and T-SQL's unary bitwise NOT (`~x`) has no direct spelling on Oracle at all (PL/SQL has no bitwise NOT operator or built-in), and MySQL's `~x` operates on an *unsigned* 64-bit integer, so a plain `~5` there returns a huge unsigned complement rather than the signed `-6` the source engine intended. |
| [A T-SQL hex/binary literal used in arithmetic → folded to its integer value](strings-collation/hex-binary-literal-arithmetic-fold.md) | T-SQL's `0x0A` is a binary-string literal that also behaves as an integer in numeric contexts (`0x0A + 5` = `15`). |
| [Infix bitwise operators (`&`, `\|`, `^`, `<<`, `>>`) → Oracle `BITAND`/`POWER` identities](strings-collation/bitwise-operators-to-oracle-identities.md) | Oracle has no infix bitwise operators at all: `\|` is string concatenation there, and `^`/`&` are outright errors. |
| [T-SQL `NCHAR(n)` Unicode code point → PostgreSQL `CHR`, MySQL `CHAR(... USING utf32)`, Oracle `NCHR`/`UNISTR`](strings-collation/nchar-code-point-per-target.md) | T-SQL's `NCHAR(n)` returns the character for Unicode code point `n` — an integer argument (a `0x…` literal is still a *number* there, not a byte string) — with no matching built-in on any other engine under that name. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](aggregates-windows/tsql-cast-int-truncation-reverse.md) | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [T-SQL `CAST(x AS BIT)` → Oracle `SIGN(ABS(x))`, not a plain type change](booleans/tsql-cast-as-bit-normalizes.md) | T-SQL's `CAST(x AS BIT)` is not a value-preserving type change — it *normalizes* any numeric value to `0` or `1` (any non-zero number becomes `1`, zero stays `0`, `NULL` stays `NULL`). |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](dml/pivot.md) | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](dml/unpivot.md) | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](dml/merge-when-not-matched-by-source.md) | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |
| [Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold](dml/merge-matched-update-delete-fold.md) | A T-SQL `MERGE` may carry two conditional `WHEN MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`. |
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](dml/merge-with-leading-cte.md) | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](dml/delete-top-n-row-cap.md) | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](dml/multi-join-update-from.md) | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](dml/output-to-returning.md) | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |
| [`OUTPUT … INTO` redirect (T-SQL) → PostgreSQL](dml/output-into-redirect.md) | `OUTPUT INSERTED.a INTO log(a)` redirects the output rows into a second table instead of returning them to the caller. |
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](dml/set-op-trailing-order-by.md) | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](dml/recursive-cte-keyword-and-column-list.md) | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](dml/iif-to-case-or-native.md) | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](dml/money-literal-shorthand.md) | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |
| [Canonical `MERGE` (T-SQL/Oracle) → MySQL `INSERT … SELECT … ON DUPLICATE KEY UPDATE`](dml/merge-to-mysql-on-duplicate-key.md) | MySQL has no `MERGE` statement at all. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](ddl/tsql-identity-scope-reads.md) | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |
| [T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`](ddl/tsql-bit-to-postgresql-boolean.md) | T-SQL's `BIT` type behaves like a 1-bit integer: `0`/`1` literals are valid in a `DEFAULT` clause, an `INSERT ... VALUES` list, or an `UPDATE ... SET`, with no special casting. |
| [T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)](ddl/alter-column-nullability.md) | T-SQL's `ALTER COLUMN <c> <type>` bakes type *and* nullability into one clause — omitting a `NULL`/`NOT NULL` keyword does not mean "leave nullability alone," it means "make the column nullable," silently dropping an existing `NOT NULL` the statement never mentioned. |
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](ddl/session-temp-tables-to-oracle.md) | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](ddl/fk-on-update-action-to-oracle.md) | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](ddl/sequence-negative-option-spelling.md) | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](ddl/tsql-index-fillfactor.md) | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](ddl/create-type-alias-harvested.md) | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |
| [A plain `DROP TABLE t` → `DROP TABLE IF EXISTS t` on PostgreSQL](ddl/drop-table-idempotent-if-exists.md) | A migration script is meant to be re-runnable against a target that may already have run it once before — a bare `DROP TABLE t` errors on a second run if the table is already gone, stopping the whole script partway through. |
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](ddl/tsql-existence-guard-catalog-probes.md) | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [`EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/exec-sp-degrade-policy.md) | T-SQL system procedures (`sp_rename`, `sp_who`, …) call into SQL Server's own catalog/admin machinery. |
| [Statement-after-`EXEC` survival fix](procedural/statement-after-exec-survival.md) | A degraded system-proc `EXEC`, followed by another statement on the same line separated only by `;` (not a batch-separating `GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`. |
| [`SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/set-identity-insert-degrade.md) | T-SQL requires `IDENTITY_INSERT` to be explicitly turned `ON` before a script can supply its own value for an identity column, then turned back `OFF`. |
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](procedural/raiserror-expression-messages.md) | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → a ref-cursor parameter (Oracle `SYS_REFCURSOR` OUT, PostgreSQL `refcursor` INOUT), propagated to `CALL` sites](procedural/bare-result-select-to-refcursor.md) | A MySQL or T-SQL procedure can hand back a result set simply by running a `SELECT` with no `INTO` target partway through the body. |
| [Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL](procedural/scroll-cursor-fetch.md) | A T-SQL `SCROLL` cursor supports non-forward fetches: `FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc. |
| [T-SQL `INSTEAD OF` trigger → PostgreSQL (native on views, emulated on tables)](procedural/tsql-instead-of-trigger.md) | T-SQL allows `INSTEAD OF` on both views *and* base tables — the trigger body runs **instead of** the attempted INSERT/UPDATE/DELETE, which is never applied on its own. |
| [T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL](procedural/tsql-cursor-variable-binding.md) | T-SQL lets a cursor be bound to a *variable* in two steps: a bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... FOR <query>` to attach the query, then a bare `OPEN @cur;`. |
| [T-SQL loop control (`BREAK`/`CONTINUE`, compound assignment) → MySQL labeled `LEAVE`/`ITERATE`](procedural/tsql-loop-control-to-mysql-labels.md) | T-SQL's `BREAK`/`CONTINUE` act on the *nearest enclosing* loop with no name required. |
| [A row-by-row dynamic-SQL string build (T-SQL) → a single Oracle `LISTAGG` + `EXECUTE IMMEDIATE`](procedural/dynamic-sql-loop-to-listagg.md) | A common T-SQL pattern builds a dynamic-SQL string by looping over a result set implicitly, appending to the same variable on every row: `SELECT @sql = @sql + expr FROM t`. |
| [A lengthless character `CAST` reaching Oracle: valid inside a PL/SQL body, invalid as a bare top-level statement](procedural/oracle-cast-length-plsql-body-vs-sql-statement.md) | A T-SQL cast to a character type with **no length given at all** (a bare `CAST(x AS VARCHAR)`, as opposed to `VARCHAR(n)`) needs opposite treatment depending on where it lands on Oracle. |
| [T-SQL subquery-in-expression assignment → Oracle `SELECT ... INTO ... FROM DUAL`](procedural/tsql-subquery-assignment-to-oracle-select-into.md) | T-SQL lets a variable assignment's right-hand side embed a subquery directly, either as the whole expression or nested inside another call: `SET @x = (SELECT MAX(a) FROM t)`, or `DECLARE @x INT = (SELECT MAX(a) FROM t)` as an initializer. |
| [T-SQL `@@FETCH_STATUS` → Oracle / PostgreSQL / MySQL](procedural/tsql-fetch-status-to-oracle-postgresql-mysql.md) | T-SQL exposes cursor state through a single global variable, `@@FETCH_STATUS`, checked right after a `FETCH` (`0` = a row was returned, `-1` = no more rows, `-2` = the fetched row is missing). |
| [T-SQL's `CAST(N'' AS XML).value('xs:base64Binary(...)', ...)` base64-decode idiom → each target's native call](procedural/base64-xml-idiom-per-target.md) | T-SQL has no direct `BASE64_DECODE` function; the idiomatic way to decode a base64 string into binary is to route it through the XML type system — `CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@x"))', 'VARBINARY(MAX)')`. |
| [T-SQL `ERROR_MESSAGE()` (inside a `CATCH` block) → each target's own error-text accessor](procedural/error-message-function-per-target.md) | Inside a T-SQL `CATCH` block, `ERROR_MESSAGE()` reads the text of the error that was just caught. |
| [A `DECLARE` written mid-block (inside an `IF`/`CATCH`) → hoisted to the routine's top declaration section](procedural/mid-block-declare-hoist.md) | T-SQL allows `DECLARE @v type = init;` anywhere a statement is legal — inside an `IF` body, inside a `CATCH` block, nested arbitrarily deep. |
| [A top-level T-SQL/Oracle batch needing a procedural construct → PostgreSQL `DO $$ ... $$`](procedural/toplevel-batch-do-block-wrap.md) | A standalone (not-inside-a-`CREATE PROCEDURE`) T-SQL batch or Oracle anonymous block can freely mix `PRINT`/`DBMS_OUTPUT`, variable declarations, `IF`, cursor `FOR` loops, and dynamic `EXECUTE` — all procedural constructs that only exist *inside* a routine body on PostgreSQL. |
| [T-SQL `THROW`/`RAISERROR`'s numeric error code → each target's own error-code slot](procedural/throw-raiserror-numeric-code-per-target.md) | T-SQL's `THROW 50001, 'not found', 1` and `RAISERROR('not found', 16, 1)` (with a matching custom message id registered separately) both carry a *numeric error code* alongside the message text. |
| [A constrained numeric `CAST` inside a PL/SQL expression → hoisted through `SELECT ... INTO ... FROM DUAL`](procedural/constrained-cast-hoisted-select-into-dual.md) | Oracle's PL/SQL forbids a *constrained* type (one with a precision/scale, like `DECIMAL(12, 2)`, or a length) on a `CAST` used directly inside a procedural expression (`PLS-00103`) — only an unconstrained type is legal there. |
| [T-SQL sized parameter/return types (`DECIMAL(5,2)`, `NVARCHAR(50)`) → unconstrained on an Oracle routine header](procedural/oracle-formal-parameter-types-unconstrained.md) | Oracle's PL/SQL forbids length, precision, or scale on a *formal parameter* or *function return* type declaration — `PLS-00103` — even though the identical sized type is perfectly legal on a `CREATE TABLE` column. |
| [T-SQL `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)` → MySQL's native hash function directly](procedural/convert-hashbytes-wrapper-collapse.md) | T-SQL has no built-in "digest as a hex string" function — `HASHBYTES(...)` returns raw bytes, so the idiomatic way to get a readable hex digest is to wrap it in `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)`, where style `2` is `CONVERT`'s binary-to-hex-string style code. |
| [T-SQL `IF EXISTS (<real query>) BEGIN ... END [ELSE ...]` → Oracle cursor `FOR` loop over a `DUAL` probe](procedural/if-exists-control-flow-to-oracle-for-loop.md) | `IF EXISTS (SELECT ...) BEGIN ... END` is ordinary control flow over real table data (not a system-catalog idempotency guard) — a migration script checking "has this step already run?" before doing more work, for example. |
| [A purely set-based T-SQL trigger (`FROM inserted JOIN deleted`) → PostgreSQL statement-level trigger with named transition tables](procedural/tsql-set-based-trigger-to-pg-statement-level.md) | T-SQL triggers are always statement-level, exposing the whole batch of affected rows through two pseudo-tables, `inserted`/`deleted`, that a set-based trigger body joins against directly (`INSERT ... SELECT ... FROM inserted i JOIN deleted d ON d.id = i.id`). |
| [T-SQL `HASHBYTES('SHA2_256', x)` → PostgreSQL `sha256`, wrapped for a character argument](procedural/hashbytes-sha256-to-postgresql.md) | sqlglot canonicalizes T-SQL's `HASHBYTES('SHA2_256', x)` to a bare `SHA256(x)` call reaching PostgreSQL, but PostgreSQL's `sha256` takes a **bytea**, not text — `sha256(x)` over a character column is "function sha256(text) does not exist" at *runtime*, a defect a compile-only validity check does not catch (the call parses fine; it just never runs). |
| [Implicit row count in EXPRESSION position (Oracle `SQL%ROWCOUNT` / T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`) → PostgreSQL `GET DIAGNOSTICS` hoist](procedural/rowcount-expression-hoist-to-postgresql.md) | Oracle's `SQL%ROWCOUNT`, T-SQL's `@@ROWCOUNT`, and MySQL's `ROW_COUNT()` are all readable **inline**, as an expression, anywhere a value is expected (`IF SQL%ROWCOUNT <> 1`, `v := SQL%ROWCOUNT + 1`, a call argument, a `RETURN`). |

### T-SQL as target

| [Date/time](#datetime-arithmetic-and-formatting-1) | [Strings](#strings-concatenation-and-collation-1) | [Aggregates & windows](#aggregates-and-window-functions-1) | [Booleans](#booleans-the-valuepredicate-duality-1) | [DML](#dml-pivotunpivot-merge-delete-row-values-1) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-1) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-1) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)](datetime/oracle-add-months-to-dateadd.md) | Oracle's `ADD_MONTHS` sticks to the *target* month's last day whenever the operand is its own month's last day — `ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. |
| [PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week](datetime/date-trunc-to-oracle-trunc.md) | PostgreSQL `date_trunc('week', ts)` truncates to the start of the ISO week — **Monday** — and `date_trunc('quarter', ts)` to the first day of the quarter. |
| [MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target](datetime/mysql-timestampdiff-complete-month.md) | MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts **complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')` = `1`, not `2`, because the end's day-of-month (`10`) has not reached the start's (`15`) — the final partial month does not count. |
| [MySQL TO_DAYS year-0000 epoch rebase](datetime/mysql-to-days-epoch-rebase.md) | MySQL `TO_DAYS(d)` returns the count of days since a notional `0000-01-01`. |
| [Multi-field PostgreSQL INTERVAL decomposition](datetime/postgresql-interval-decomposition.md) | PostgreSQL accepts a verbose, multi-unit interval literal in one string: `INTERVAL '1 year 2 months 3 days'`. |
| [MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets](datetime/mysql-compound-extract-units.md) | MySQL's `EXTRACT` accepts several **compound** units — `YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack two or more calendar fields into a single decimal-weighted number in one call. |
| [Oracle `MONTHS_BETWEEN` fractional value → T-SQL exact `CASE` formula](datetime/months-between-fractional.md) | Oracle's `MONTHS_BETWEEN(date1, date2)` returns a **fractional** number of months: whole months plus `(day1 - day2) / 31` for the remainder, collapsing to a whole number only when both dates are the last day of their month or share the same day-of-month. |
| [An Oracle `DATE` literal inside a derived-table projection → its typing survives to the outer column reference](datetime/date-typing-propagated-through-derived-table.md) | `SELECT ShipDate - OrderDate FROM (SELECT DATE '2020-01-10' ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x` computes a day count on Oracle, since `DATE - DATE` is arithmetic there. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Oracle `'' ≡ NULL`](strings-collation/oracle-empty-string-is-null.md) | Every other engine stores and compares an empty string `''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('', 'x')` is `''`. |
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [Oracle `LTRIM(s, chars)`/`RTRIM(s, chars)` → `TRIM(LEADING/TRAILING chars FROM s)`](strings-collation/oracle-ltrim-rtrim-charset-reverse.md) | This is the reverse of Character-set `TRIM(chars FROM string)` → Oracle: Oracle's own `LTRIM`/`RTRIM` already accept a multi-character trim set as their second argument natively. |
| [Oracle `DECODE` with mixed-type result branches → `CASE` with a `CAST` inserted to unify types](strings-collation/decode-mixed-type-branch-cast.md) | Oracle's `DECODE(expr, search1, result1, ..., default)` tolerates result branches of different types — a string in one branch, a number in another — since Oracle resolves the whole expression's type loosely at runtime. |
| [MySQL `LOCATE('', s)` (always `1`) → T-SQL guarded `CASE`](strings-collation/locate-empty-needle-guard.md) | MySQL's `LOCATE(needle, haystack)` special-cases an empty needle: `LOCATE('', s)` is always `1`, regardless of `s`, treating the empty string as matching at the very start. |
| [PostgreSQL `ILIKE` (case-insensitive `LIKE`) → `UPPER(x) LIKE UPPER(pattern)`](strings-collation/ilike-upper-comparison.md) | PostgreSQL's `ILIKE` is a case-insensitive `LIKE` operator — no other target engine has a dedicated case-insensitive pattern-match operator (T-SQL and MySQL's default collations are already case-insensitive, but Oracle's is case-sensitive by default and has no `ILIKE` spelling at all). |
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](strings-collation/no-target-spelling-case-chain.md) | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
| [Oracle extended `INSTR` (occurrence / backward search) over **literal** arguments → the computed position](strings-collation/oracle-instr-literal-fold.md) | Oracle's 4-argument `INSTR(s, sub, start, occurrence)` finds the `occurrence`-th match at or after `start` — and, when `start` is negative, searches **backward** from the end of the string instead. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](aggregates-windows/groups-window-frame.md) | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-keep-dense-rank.md) | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](aggregates-windows/filter-clause.md) | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](aggregates-windows/bool-or-and-value-wrapping.md) | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](aggregates-windows/bool-or-filter-composition.md) | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](aggregates-windows/cast-folding-listagg-string-agg.md) | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](aggregates-windows/any-value-to-tsql.md) | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-listagg-over.md) | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](aggregates-windows/distinct-on.md) | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](aggregates-windows/cast-to-integer-rounding.md) | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](aggregates-windows/mod-by-zero-divisor.md) | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/predicate-in-value-position.md) | A comparison, boolean combinator, or null-test used as an ordinary value — `SELECT (a > b) AS c`, `SELECT (b1 AND a3) AS b3`, `SELECT (id IS NOT NULL) AS a3` — is legal on MySQL/PostgreSQL (comparisons and booleans are 1/0/NULL values there). |
| [`NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/not-of-truthy-value.md) | The same duality inside procedural bodies: `SET done = NOT done` (MySQL) or `RETURN <predicate>` from a function declared to return a boolean assigns/returns a value, not a predicate. |
| [A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/value-in-predicate-position.md) | MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN` return type demands an actual boolean expression, not a `NUMBER`. |
| [A value-wrapped predicate compared again in predicate position collapses back to the predicate (MySQL) → T-SQL](booleans/value-wrapped-predicate-collapse.md) | MySQL lets you compare a boolean value against `1`/`0`, or test it with `IS TRUE`, even when that value is itself already a predicate: `WHERE (c2 IS NOT NULL) = 1`. |
| [`flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle](booleans/boolean-column-is-true-false.md) | PostgreSQL's `IS TRUE`/`IS FALSE`/`IS NOT TRUE`/`IS NOT FALSE` predicate accepts `TRUE`/`FALSE`/`NULL`/`UNKNOWN` as its right-hand side — never an integer. |
| [`IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`](booleans/is-distinct-from.md) | PostgreSQL's `IS [NOT] DISTINCT FROM` is a null-safe equality: unlike `=`, it never itself evaluates to `UNKNOWN` — `NULL IS NOT DISTINCT FROM NULL` is `TRUE`, `1 IS DISTINCT FROM NULL` is `TRUE`. |
| [A bare Oracle PL/SQL `BOOLEAN` variable used as a condition → `= 1` on T-SQL](booleans/oracle-boolean-variable-bare-condition.md) | Oracle's PL/SQL `BOOLEAN` variables are used directly as conditions — `IF NOT bexc THEN`, `WHILE bexc LOOP` — since PL/SQL has a real boolean type. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`UNPIVOT` (T-SQL / Oracle) → all targets](dml/unpivot.md) | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](dml/multi-table-delete-join.md) | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](dml/row-value-inequality.md) | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [Row-value `IN` (Oracle) → T-SQL](dml/row-value-in.md) | `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN` list, valid on Oracle/PostgreSQL/MySQL. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](dml/from-values-to-union-all.md) | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](dml/from-generate-series.md) | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](dml/recursive-cte-keyword-and-column-list.md) | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |
| [`GROUP BY 1` (positional ordinal) → the actual `SELECT`-list column name](dml/group-by-ordinal-resolved.md) | PostgreSQL accepts a positional ordinal in `GROUP BY` — `GROUP BY 1` groups by whatever the first `SELECT`-list expression is. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [Self-referencing FK cascade (MySQL) → T-SQL](ddl/self-referencing-fk-cascade.md) | `FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL`, where the FK references its **own** table (an employee/manager hierarchy). |
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](ddl/sequence-negative-option-spelling.md) | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](ddl/mysql-enum-to-varchar-check.md) | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |
| [Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL](ddl/nameless-create-index-to-tsql.md) | PostgreSQL allows `CREATE INDEX ON t (col)` with no index name — the server picks one internally (`t_col_idx`-shaped, but never surfaced to the script). |
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](ddl/mysql-unsigned-check-synthesis.md) | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](ddl/truncate-restart-identity-cascade.md) | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](ddl/alter-column-drop-default.md) | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](ddl/oracle-alter-add-parenthesized-unwrap.md) | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](ddl/oracle-catalog-probe-rewritten-per-target.md) | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [Statement-after-`EXEC` survival fix](procedural/statement-after-exec-survival.md) | A degraded system-proc `EXEC`, followed by another statement on the same line separated only by `;` (not a batch-separating `GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`. |
| [`SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL](procedural/sqlplus-client-directives.md) | SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`, etc.) are **line-oriented client-tool commands**, not SQL statements — they carry no trailing `;` and configure the SQL*Plus session, not the database. |
| [Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL](procedural/oracle-type-rowtype-references.md) | `v_id employees.id%TYPE` declares a variable with **whatever type** the referenced column currently has — a live binding to the schema, not a fixed type name. |
| [Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL](procedural/oracle-cursor-attributes.md) | Oracle attaches state to each named cursor: `c%FOUND`/`c%NOTFOUND` (did the last `FETCH` return a row), `c%ISOPEN`, and `c%ROWCOUNT` (rows fetched so far on that cursor). |
| [PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`](procedural/implicit-found-flag.md) | PL/pgSQL keeps one implicit boolean, `FOUND`, updated by the *last* `SELECT INTO`, `UPDATE`, `DELETE`, `INSERT`, or `FETCH` in the routine — it answers "did that last statement affect/return a row?" for the routine as a whole, not for one named cursor. |
| [MySQL `DECLARE {EXIT\|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)](procedural/mysql-declare-handler.md) | MySQL declares an error handler *separately* from the code it protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in the block's declaration section, naming the condition(s) it reacts to and a single action statement. |
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](procedural/raiserror-expression-messages.md) | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [EXEC / routine-call expression argument (Oracle) → synthesized variable (T-SQL)](procedural/exec-expression-argument-hoist.md) | A T-SQL `EXEC` call accepts only a literal, a variable, or `DEFAULT`/`NULL` in its argument list — never an arbitrary expression. |
| [`RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)](procedural/returns-void-signature-synthesis.md) | A PostgreSQL function declared `RETURNS void` returns nothing — per the corpus's own count, the single most common plpgsql function shape (62 occurrences), typically a side-effecting helper invoked for its `INSERT`/`UPDATE`, never for a value. |
| [PL/SQL `FOR rec IN cur LOOP` (Oracle) → T-SQL explicit cursor scaffold](procedural/cursor-for-loop-to-tsql.md) | A PL/SQL cursor `FOR` loop declares nothing: it implicitly opens the cursor, fetches one row per iteration into a record `rec`, and closes it when the cursor is exhausted — `rec.col` reads that iteration's column. |
| [Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter](procedural/numeric-range-for-loop.md) | `FOR i IN 1..13 LOOP` (optionally `REVERSE`) is Oracle's counting loop — no cursor at all, just an integer range. |
| [T-SQL scalar function: synthesized trailing `RETURN NULL` after an all-branches-return `IF`/`ELSE`](procedural/scalar-function-trailing-return-null.md) | T-SQL requires a scalar function's **last statement** to literally *be* a `RETURN` (error 455 otherwise) — even when the function's body already returns a value on every possible branch, such as an `IF ... ELSE` where both arms end in `RETURN`. |
| [Oracle top-level anonymous block (`DECLARE … BEGIN … END;`) → a plain T-SQL batch](procedural/anonymous-block-flattens-to-tsql.md) | Oracle's top-level anonymous block — `DECLARE ... BEGIN ... END; /` — is a PL/SQL shell with its own `DECLARE` section and `BEGIN`/`END` delimiters. |
| [`EXECUTE IMMEDIATE '<sql>' INTO x` (Oracle) → a two-statement T-SQL capture](procedural/execute-immediate-into-capture.md) | Oracle's `EXECUTE IMMEDIATE '<sql>' INTO x` runs a dynamic query and captures its single-row result directly into a variable — PostgreSQL's `EXECUTE '<sql>' INTO x` is the same idiom natively. |
| [Oracle `DBMS_LOB`/`UTL_RAW`/`TO_NUMBER`/`TRUNC` helper calls → T-SQL/MySQL built-ins](procedural/oracle-lob-numeric-helpers-to-tsql.md) | Several of Oracle's package-qualified LOB helpers and its bare numeric/date built-ins have no shared name on other engines, and one (`DBMS_LOB.SUBSTR`) even reorders its arguments compared to the target's equivalent. |
| [PostgreSQL `SQLSTATE` / Oracle `SQLCODE` → `CAST(ERROR_STATE()/ERROR_NUMBER() AS NVARCHAR(n))`](procedural/sqlstate-sqlcode-to-tsql-error-functions.md) | PostgreSQL's `SQLSTATE` and Oracle's `SQLCODE` are bare identifiers, readable directly inside an exception handler as the caught error's state code or numeric code. |

### Oracle as source

| [Date/time](#datetime-arithmetic-and-formatting-2) | [Strings](#strings-concatenation-and-collation-2) | [Aggregates & windows](#aggregates-and-window-functions-2) | [Booleans](#booleans-the-valuepredicate-duality-2) | [DML](#dml-pivotunpivot-merge-delete-row-values-2) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-2) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-2) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)](datetime/oracle-add-months-to-dateadd.md) | Oracle's `ADD_MONTHS` sticks to the *target* month's last day whenever the operand is its own month's last day — `ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. |
| [Oracle `MONTHS_BETWEEN` fractional value → T-SQL exact `CASE` formula](datetime/months-between-fractional.md) | Oracle's `MONTHS_BETWEEN(date1, date2)` returns a **fractional** number of months: whole months plus `(day1 - day2) / 31` for the remainder, collapsing to a whole number only when both dates are the last day of their month or share the same day-of-month. |
| [Oracle `NUMTODSINTERVAL` / `NUMTOYMINTERVAL` → PostgreSQL `INTERVAL`](datetime/numtointerval-oracle-to-postgresql.md) | Oracle's `NUMTODSINTERVAL(n, 'unit')` and `NUMTOYMINTERVAL(n, 'unit')` build a standalone day-to-second or year-to-month `INTERVAL` value from a number and a unit name (`NUMTODSINTERVAL(-3, 'DAY')` is "an interval of minus three days"). |
| [An Oracle `DATE` literal inside a derived-table projection → its typing survives to the outer column reference](datetime/date-typing-propagated-through-derived-table.md) | `SELECT ShipDate - OrderDate FROM (SELECT DATE '2020-01-10' ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x` computes a day count on Oracle, since `DATE - DATE` is arithmetic there. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Oracle `'' ≡ NULL`](strings-collation/oracle-empty-string-is-null.md) | Every other engine stores and compares an empty string `''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('', 'x')` is `''`. |
| [Oracle `LTRIM(s, chars)`/`RTRIM(s, chars)` → `TRIM(LEADING/TRAILING chars FROM s)`](strings-collation/oracle-ltrim-rtrim-charset-reverse.md) | This is the reverse of Character-set `TRIM(chars FROM string)` → Oracle: Oracle's own `LTRIM`/`RTRIM` already accept a multi-character trim set as their second argument natively. |
| [Oracle `DECODE` with mixed-type result branches → `CASE` with a `CAST` inserted to unify types](strings-collation/decode-mixed-type-branch-cast.md) | Oracle's `DECODE(expr, search1, result1, ..., default)` tolerates result branches of different types — a string in one branch, a number in another — since Oracle resolves the whole expression's type loosely at runtime. |
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](strings-collation/no-target-spelling-case-chain.md) | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
| [Oracle extended `INSTR` (occurrence / backward search) over **literal** arguments → the computed position](strings-collation/oracle-instr-literal-fold.md) | Oracle's 4-argument `INSTR(s, sub, start, occurrence)` finds the `occurrence`-th match at or after `start` — and, when `start` is negative, searches **backward** from the end of the string instead. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](aggregates-windows/groups-window-frame.md) | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-keep-dense-rank.md) | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-listagg-over.md) | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [Oracle PL/SQL `BOOLEAN` variables and parameters keep native `NOT` (handled)](booleans/oracle-plsql-native-boolean.md) | Oracle's exception to its own "SQL has no boolean value" rule: a PL/SQL variable or parameter declared `BOOLEAN` **is** a first-class value inside procedural code — just not inside a SQL statement issued from that same block. |
| [A bare Oracle PL/SQL `BOOLEAN` variable used as a condition → `= 1` on T-SQL](booleans/oracle-boolean-variable-bare-condition.md) | Oracle's PL/SQL `BOOLEAN` variables are used directly as conditions — `IF NOT bexc THEN`, `WHILE bexc LOOP` — since PL/SQL has a real boolean type. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](dml/pivot.md) | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](dml/unpivot.md) | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](dml/row-value-inequality.md) | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [Row-value `IN` (Oracle) → T-SQL](dml/row-value-in.md) | `(a, b) IN ((1, 2), (3, 4))` is a row-constructor `IN` list, valid on Oracle/PostgreSQL/MySQL. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [Canonical `MERGE` (T-SQL/Oracle) → MySQL `INSERT … SELECT … ON DUPLICATE KEY UPDATE`](dml/merge-to-mysql-on-duplicate-key.md) | MySQL has no `MERGE` statement at all. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](ddl/sequence-negative-option-spelling.md) | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |
| [Oracle `RAW(16) DEFAULT SYS_GUID()` → PostgreSQL `BYTEA` with a matching `DECODE(...)` default](ddl/raw-guid-default-bytea.md) | `RAW(16) DEFAULT SYS_GUID()` is Oracle's idiom for a binary-GUID primary key: `SYS_GUID()` generates a 16-byte raw value used directly as the default. |
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](ddl/oracle-alter-add-parenthesized-unwrap.md) | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](ddl/oracle-catalog-probe-rewritten-per-target.md) | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [`SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL](procedural/sqlplus-client-directives.md) | SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`, etc.) are **line-oriented client-tool commands**, not SQL statements — they carry no trailing `;` and configure the SQL*Plus session, not the database. |
| [Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL](procedural/oracle-type-rowtype-references.md) | `v_id employees.id%TYPE` declares a variable with **whatever type** the referenced column currently has — a live binding to the schema, not a fixed type name. |
| [Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL](procedural/oracle-cursor-attributes.md) | Oracle attaches state to each named cursor: `c%FOUND`/`c%NOTFOUND` (did the last `FETCH` return a row), `c%ISOPEN`, and `c%ROWCOUNT` (rows fetched so far on that cursor). |
| [PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`](procedural/implicit-found-flag.md) | PL/pgSQL keeps one implicit boolean, `FOUND`, updated by the *last* `SELECT INTO`, `UPDATE`, `DELETE`, `INSERT`, or `FETCH` in the routine — it answers "did that last statement affect/return a row?" for the routine as a whole, not for one named cursor. |
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](procedural/raiserror-expression-messages.md) | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [EXEC / routine-call expression argument (Oracle) → synthesized variable (T-SQL)](procedural/exec-expression-argument-hoist.md) | A T-SQL `EXEC` call accepts only a literal, a variable, or `DEFAULT`/`NULL` in its argument list — never an arbitrary expression. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](procedural/trigger-reading-own-table.md) | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [PL/SQL `FOR rec IN cur LOOP` (Oracle) → T-SQL explicit cursor scaffold](procedural/cursor-for-loop-to-tsql.md) | A PL/SQL cursor `FOR` loop declares nothing: it implicitly opens the cursor, fetches one row per iteration into a record `rec`, and closes it when the cursor is exhausted — `rec.col` reads that iteration's column. |
| [PL/SQL cursor `FOR` loop (Oracle) → MySQL explicit cursor scaffold](procedural/cursor-for-loop-to-mysql.md) | The same implicit fetch-and-bind PL/SQL construct as above, but onto MySQL, whose procedural dialect additionally requires every `DECLARE` to sit at the very top of its enclosing `BEGIN` block (MySQL error 1337) and has no `WHILE @@FETCH_STATUS` equivalent — loop termination is driven by a `CONTINUE HANDLER FOR NOT FOUND`. |
| [Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter](procedural/numeric-range-for-loop.md) | `FOR i IN 1..13 LOOP` (optionally `REVERSE`) is Oracle's counting loop — no cursor at all, just an integer range. |
| [T-SQL scalar function: synthesized trailing `RETURN NULL` after an all-branches-return `IF`/`ELSE`](procedural/scalar-function-trailing-return-null.md) | T-SQL requires a scalar function's **last statement** to literally *be* a `RETURN` (error 455 otherwise) — even when the function's body already returns a value on every possible branch, such as an `IF ... ELSE` where both arms end in `RETURN`. |
| [Oracle top-level anonymous block (`DECLARE … BEGIN … END;`) → a plain T-SQL batch](procedural/anonymous-block-flattens-to-tsql.md) | Oracle's top-level anonymous block — `DECLARE ... BEGIN ... END; /` — is a PL/SQL shell with its own `DECLARE` section and `BEGIN`/`END` delimiters. |
| [`EXECUTE IMMEDIATE '<sql>' INTO x` (Oracle) → a two-statement T-SQL capture](procedural/execute-immediate-into-capture.md) | Oracle's `EXECUTE IMMEDIATE '<sql>' INTO x` runs a dynamic query and captures its single-row result directly into a variable — PostgreSQL's `EXECUTE '<sql>' INTO x` is the same idiom natively. |
| [`SELECT ... INTO :NEW.col1, :NEW.col2` (Oracle trigger) → PostgreSQL `NEW.col`, MySQL session variables](procedural/pseudo-row-into-mysql-session-vars.md) | An Oracle row-level trigger can `SELECT ... INTO :NEW.col1, :NEW.col2` directly — assigning query results straight into the pseudo-row's columns. |
| [A package-qualified ref-cursor type (`pkg.my_cursor`) → the target's own ref-cursor type](procedural/refcursor-package-type-and-inout-mode.md) | An Oracle procedure parameter can be typed with a package-defined `REF CURSOR` subtype (`v_cur OUT pkg_ret.my_cursor`) — `pkg_ret.my_cursor` is only meaningful *inside that package*, never on a target with no package concept at all. |
| [A top-level T-SQL/Oracle batch needing a procedural construct → PostgreSQL `DO $$ ... $$`](procedural/toplevel-batch-do-block-wrap.md) | A standalone (not-inside-a-`CREATE PROCEDURE`) T-SQL batch or Oracle anonymous block can freely mix `PRINT`/`DBMS_OUTPUT`, variable declarations, `IF`, cursor `FOR` loops, and dynamic `EXECUTE` — all procedural constructs that only exist *inside* a routine body on PostgreSQL. |
| [Oracle `DBMS_LOB`/`UTL_RAW`/`TO_NUMBER`/`TRUNC` helper calls → T-SQL/MySQL built-ins](procedural/oracle-lob-numeric-helpers-to-tsql.md) | Several of Oracle's package-qualified LOB helpers and its bare numeric/date built-ins have no shared name on other engines, and one (`DBMS_LOB.SUBSTR`) even reorders its arguments compared to the target's equivalent. |
| [PostgreSQL `SQLSTATE` / Oracle `SQLCODE` → `CAST(ERROR_STATE()/ERROR_NUMBER() AS NVARCHAR(n))`](procedural/sqlstate-sqlcode-to-tsql-error-functions.md) | PostgreSQL's `SQLSTATE` and Oracle's `SQLCODE` are bare identifiers, readable directly inside an exception handler as the caught error's state code or numeric code. |
| [`EXECUTE IMMEDIATE '...' USING v1, v2` (Oracle) → MySQL `EXECUTE ... USING @v1, @v2`, bound through session variables](procedural/mysql-execute-using-session-vars.md) | Oracle's `EXECUTE IMMEDIATE '<sql>' USING bind1, bind2` accepts routine locals and parameters directly as bind arguments. |
| [Implicit row count in EXPRESSION position (Oracle `SQL%ROWCOUNT` / T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`) → PostgreSQL `GET DIAGNOSTICS` hoist](procedural/rowcount-expression-hoist-to-postgresql.md) | Oracle's `SQL%ROWCOUNT`, T-SQL's `@@ROWCOUNT`, and MySQL's `ROW_COUNT()` are all readable **inline**, as an expression, anywhere a value is expected (`IF SQL%ROWCOUNT <> 1`, `v := SQL%ROWCOUNT + 1`, a call argument, a `RETURN`). |

### Oracle as target

| [Date/time](#datetime-arithmetic-and-formatting-3) | [Strings](#strings-concatenation-and-collation-3) | [Aggregates & windows](#aggregates-and-window-functions-3) | [Booleans](#booleans-the-valuepredicate-duality-3) | [DML](#dml-pivotunpivot-merge-delete-row-values-3) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-3) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-3) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS](datetime/dateadd-month-to-oracle-add-months.md) | T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d, INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the day-of-month* and clamp down only when the target month is shorter: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`). |
| [PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week](datetime/date-trunc-to-oracle-trunc.md) | PostgreSQL `date_trunc('week', ts)` truncates to the start of the ISO week — **Monday** — and `date_trunc('quarter', ts)` to the first day of the quarter. |
| [MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target](datetime/mysql-timestampdiff-complete-month.md) | MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts **complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')` = `1`, not `2`, because the end's day-of-month (`10`) has not reached the start's (`15`) — the final partial month does not count. |
| [MySQL TO_DAYS year-0000 epoch rebase](datetime/mysql-to-days-epoch-rebase.md) | MySQL `TO_DAYS(d)` returns the count of days since a notional `0000-01-01`. |
| [Multi-field PostgreSQL INTERVAL decomposition](datetime/postgresql-interval-decomposition.md) | PostgreSQL accepts a verbose, multi-unit interval literal in one string: `INTERVAL '1 year 2 months 3 days'`. |
| [MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets](datetime/mysql-compound-extract-units.md) | MySQL's `EXTRACT` accepts several **compound** units — `YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack two or more calendar fields into a single decimal-weighted number in one call. |
| [An ISO date/timestamp string written into a harvested `DATE`/`DATETIME` column → wrapped in an Oracle ANSI literal](datetime/schema-harvested-date-literal-to-oracle.md) | `INSERT INTO evt (d, ts) VALUES ('2024-01-15', '2024-01-15 10:30:00')` relies on the target column's own declared type (`DATE`/`DATETIME`) to interpret a plain ISO string as a date or timestamp — T-SQL, PostgreSQL, and MySQL all accept this implicit string-to-date coercion. |
| [T-SQL `CONVERT(type, value, style)`'s numeric style code → a per-target format function, or ignored when the target type isn't a date](datetime/convert-style-code-per-target.md) | T-SQL's `CONVERT` takes an optional third argument, a numeric *style* code, whose meaning depends entirely on what the second argument is being converted to: against a date/time type, it selects a date format (`120` = ISO `yyyy-mm-dd hh:mi:ss`, `103` = British/French `dd/mm/yyyy`, ...); against a non-date type, the style code is only meaningful for a handful of special cases (binary-to-string encodings) and is otherwise ignored. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Oracle `'' ≡ NULL`](strings-collation/oracle-empty-string-is-null.md) | Every other engine stores and compares an empty string `''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('', 'x')` is `''`. |
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [PostgreSQL `regexp_replace` flags → Oracle/MySQL positional occurrence + backreference respelling](strings-collation/regexp-replace-flags-and-backreferences.md) | PostgreSQL's `regexp_replace(source, pattern, replacement, flags)` fourth argument is a **flags string** (`'g'` for global, `'i'` for case-insensitive, …); Oracle's and MySQL's `REGEXP_REPLACE` instead take a **numeric** occurrence/position argument in that slot, and both already replace every match by default. |
| [Unary bitwise `~x`/NOT → Oracle `-(x) - 1`, MySQL `CAST(~x AS SIGNED)`](strings-collation/unary-bitwise-not-emulation.md) | PostgreSQL and T-SQL's unary bitwise NOT (`~x`) has no direct spelling on Oracle at all (PL/SQL has no bitwise NOT operator or built-in), and MySQL's `~x` operates on an *unsigned* 64-bit integer, so a plain `~5` there returns a huge unsigned complement rather than the signed `-6` the source engine intended. |
| [A T-SQL hex/binary literal used in arithmetic → folded to its integer value](strings-collation/hex-binary-literal-arithmetic-fold.md) | T-SQL's `0x0A` is a binary-string literal that also behaves as an integer in numeric contexts (`0x0A + 5` = `15`). |
| [PostgreSQL `ILIKE` (case-insensitive `LIKE`) → `UPPER(x) LIKE UPPER(pattern)`](strings-collation/ilike-upper-comparison.md) | PostgreSQL's `ILIKE` is a case-insensitive `LIKE` operator — no other target engine has a dedicated case-insensitive pattern-match operator (T-SQL and MySQL's default collations are already case-insensitive, but Oracle's is case-sensitive by default and has no `ILIKE` spelling at all). |
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](strings-collation/no-target-spelling-case-chain.md) | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
| [Infix bitwise operators (`&`, `\|`, `^`, `<<`, `>>`) → Oracle `BITAND`/`POWER` identities](strings-collation/bitwise-operators-to-oracle-identities.md) | Oracle has no infix bitwise operators at all: `\|` is string concatenation there, and `^`/`&` are outright errors. |
| [T-SQL `NCHAR(n)` Unicode code point → PostgreSQL `CHR`, MySQL `CHAR(... USING utf32)`, Oracle `NCHR`/`UNISTR`](strings-collation/nchar-code-point-per-target.md) | T-SQL's `NCHAR(n)` returns the character for Unicode code point `n` — an integer argument (a `0x…` literal is still a *number* there, not a byte string) — with no matching built-in on any other engine under that name. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](aggregates-windows/filter-clause.md) | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](aggregates-windows/bool-or-and-value-wrapping.md) | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](aggregates-windows/bool-or-filter-composition.md) | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](aggregates-windows/cast-folding-listagg-string-agg.md) | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](aggregates-windows/distinct-on.md) | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](aggregates-windows/mod-by-zero-divisor.md) | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](aggregates-windows/tsql-cast-int-truncation-reverse.md) | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |
| [An unordered MySQL `GROUP_CONCAT` → Oracle `LISTAGG` gains a synthesized `WITHIN GROUP (ORDER BY <arg>)`](aggregates-windows/group-concat-synthesized-within-group-oracle.md) | MySQL's `GROUP_CONCAT(expr SEPARATOR sep)` needs no ordering clause — an unordered call is valid MySQL, with whatever order the engine happens to produce. |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/predicate-in-value-position.md) | A comparison, boolean combinator, or null-test used as an ordinary value — `SELECT (a > b) AS c`, `SELECT (b1 AND a3) AS b3`, `SELECT (id IS NOT NULL) AS a3` — is legal on MySQL/PostgreSQL (comparisons and booleans are 1/0/NULL values there). |
| [`NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/not-of-truthy-value.md) | The same duality inside procedural bodies: `SET done = NOT done` (MySQL) or `RETURN <predicate>` from a function declared to return a boolean assigns/returns a value, not a predicate. |
| [A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/value-in-predicate-position.md) | MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN` return type demands an actual boolean expression, not a `NUMBER`. |
| [`flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle](booleans/boolean-column-is-true-false.md) | PostgreSQL's `IS TRUE`/`IS FALSE`/`IS NOT TRUE`/`IS NOT FALSE` predicate accepts `TRUE`/`FALSE`/`NULL`/`UNKNOWN` as its right-hand side — never an integer. |
| [`IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`](booleans/is-distinct-from.md) | PostgreSQL's `IS [NOT] DISTINCT FROM` is a null-safe equality: unlike `=`, it never itself evaluates to `UNKNOWN` — `NULL IS NOT DISTINCT FROM NULL` is `TRUE`, `1 IS DISTINCT FROM NULL` is `TRUE`. |
| [T-SQL `CAST(x AS BIT)` → Oracle `SIGN(ABS(x))`, not a plain type change](booleans/tsql-cast-as-bit-normalizes.md) | T-SQL's `CAST(x AS BIT)` is not a value-preserving type change — it *normalizes* any numeric value to `0` or `1` (any non-zero number becomes `1`, zero stays `0`, `NULL` stays `NULL`). |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`UNPIVOT` (T-SQL / Oracle) → all targets](dml/unpivot.md) | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](dml/merge-when-not-matched-by-source.md) | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |
| [Conditional `MATCHED` UPDATE+DELETE pair (T-SQL) → Oracle fold](dml/merge-matched-update-delete-fold.md) | A T-SQL `MERGE` may carry two conditional `WHEN MATCHED` clauses in sequence — first-match-wins — one `UPDATE`, one `DELETE`. |
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](dml/merge-with-leading-cte.md) | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](dml/multi-table-delete-join.md) | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](dml/delete-top-n-row-cap.md) | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](dml/multi-join-update-from.md) | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](dml/output-to-returning.md) | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](dml/set-op-trailing-order-by.md) | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](dml/from-values-to-union-all.md) | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](dml/from-generate-series.md) | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](dml/recursive-cte-keyword-and-column-list.md) | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](dml/iif-to-case-or-native.md) | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](dml/money-literal-shorthand.md) | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](ddl/tsql-identity-scope-reads.md) | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](ddl/session-temp-tables-to-oracle.md) | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](ddl/fk-on-update-action-to-oracle.md) | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](ddl/sequence-negative-option-spelling.md) | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](ddl/tsql-index-fillfactor.md) | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](ddl/mysql-enum-to-varchar-check.md) | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](ddl/mysql-unsigned-check-synthesis.md) | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](ddl/truncate-restart-identity-cascade.md) | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](ddl/create-type-alias-harvested.md) | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](ddl/alter-column-drop-default.md) | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](ddl/tsql-existence-guard-catalog-probes.md) | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [`EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/exec-sp-degrade-policy.md) | T-SQL system procedures (`sp_rename`, `sp_who`, …) call into SQL Server's own catalog/admin machinery. |
| [Statement-after-`EXEC` survival fix](procedural/statement-after-exec-survival.md) | A degraded system-proc `EXEC`, followed by another statement on the same line separated only by `;` (not a batch-separating `GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`. |
| [`SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/set-identity-insert-degrade.md) | T-SQL requires `IDENTITY_INSERT` to be explicitly turned `ON` before a script can supply its own value for an identity column, then turned back `OFF`. |
| [MySQL `DECLARE {EXIT\|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)](procedural/mysql-declare-handler.md) | MySQL declares an error handler *separately* from the code it protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in the block's declaration section, naming the condition(s) it reacts to and a single action statement. |
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](procedural/raiserror-expression-messages.md) | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [`RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)](procedural/returns-void-signature-synthesis.md) | A PostgreSQL function declared `RETURNS void` returns nothing — per the corpus's own count, the single most common plpgsql function shape (62 occurrences), typically a side-effecting helper invoked for its `INSERT`/`UPDATE`, never for a value. |
| [A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → a ref-cursor parameter (Oracle `SYS_REFCURSOR` OUT, PostgreSQL `refcursor` INOUT), propagated to `CALL` sites](procedural/bare-result-select-to-refcursor.md) | A MySQL or T-SQL procedure can hand back a result set simply by running a `SELECT` with no `INTO` target partway through the body. |
| [Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL](procedural/scroll-cursor-fetch.md) | A T-SQL `SCROLL` cursor supports non-forward fetches: `FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](procedural/trigger-reading-own-table.md) | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL](procedural/tsql-cursor-variable-binding.md) | T-SQL lets a cursor be bound to a *variable* in two steps: a bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... FOR <query>` to attach the query, then a bare `OPEN @cur;`. |
| [A row-by-row dynamic-SQL string build (T-SQL) → a single Oracle `LISTAGG` + `EXECUTE IMMEDIATE`](procedural/dynamic-sql-loop-to-listagg.md) | A common T-SQL pattern builds a dynamic-SQL string by looping over a result set implicitly, appending to the same variable on every row: `SELECT @sql = @sql + expr FROM t`. |
| [A lengthless character `CAST` reaching Oracle: valid inside a PL/SQL body, invalid as a bare top-level statement](procedural/oracle-cast-length-plsql-body-vs-sql-statement.md) | A T-SQL cast to a character type with **no length given at all** (a bare `CAST(x AS VARCHAR)`, as opposed to `VARCHAR(n)`) needs opposite treatment depending on where it lands on Oracle. |
| [T-SQL subquery-in-expression assignment → Oracle `SELECT ... INTO ... FROM DUAL`](procedural/tsql-subquery-assignment-to-oracle-select-into.md) | T-SQL lets a variable assignment's right-hand side embed a subquery directly, either as the whole expression or nested inside another call: `SET @x = (SELECT MAX(a) FROM t)`, or `DECLARE @x INT = (SELECT MAX(a) FROM t)` as an initializer. |
| [T-SQL `@@FETCH_STATUS` → Oracle / PostgreSQL / MySQL](procedural/tsql-fetch-status-to-oracle-postgresql-mysql.md) | T-SQL exposes cursor state through a single global variable, `@@FETCH_STATUS`, checked right after a `FETCH` (`0` = a row was returned, `-1` = no more rows, `-2` = the fetched row is missing). |
| [T-SQL's `CAST(N'' AS XML).value('xs:base64Binary(...)', ...)` base64-decode idiom → each target's native call](procedural/base64-xml-idiom-per-target.md) | T-SQL has no direct `BASE64_DECODE` function; the idiomatic way to decode a base64 string into binary is to route it through the XML type system — `CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@x"))', 'VARBINARY(MAX)')`. |
| [T-SQL `ERROR_MESSAGE()` (inside a `CATCH` block) → each target's own error-text accessor](procedural/error-message-function-per-target.md) | Inside a T-SQL `CATCH` block, `ERROR_MESSAGE()` reads the text of the error that was just caught. |
| [A `DECLARE` written mid-block (inside an `IF`/`CATCH`) → hoisted to the routine's top declaration section](procedural/mid-block-declare-hoist.md) | T-SQL allows `DECLARE @v type = init;` anywhere a statement is legal — inside an `IF` body, inside a `CATCH` block, nested arbitrarily deep. |
| [A package-qualified ref-cursor type (`pkg.my_cursor`) → the target's own ref-cursor type](procedural/refcursor-package-type-and-inout-mode.md) | An Oracle procedure parameter can be typed with a package-defined `REF CURSOR` subtype (`v_cur OUT pkg_ret.my_cursor`) — `pkg_ret.my_cursor` is only meaningful *inside that package*, never on a target with no package concept at all. |
| [A local variable named after an Oracle built-in (`count`) → renamed everywhere it's used](procedural/oracle-builtin-name-collision-rename.md) | `count` is a perfectly legal PL/pgSQL local variable name — PostgreSQL has no keyword collision. |
| [T-SQL `THROW`/`RAISERROR`'s numeric error code → each target's own error-code slot](procedural/throw-raiserror-numeric-code-per-target.md) | T-SQL's `THROW 50001, 'not found', 1` and `RAISERROR('not found', 16, 1)` (with a matching custom message id registered separately) both carry a *numeric error code* alongside the message text. |
| [A constrained numeric `CAST` inside a PL/SQL expression → hoisted through `SELECT ... INTO ... FROM DUAL`](procedural/constrained-cast-hoisted-select-into-dual.md) | Oracle's PL/SQL forbids a *constrained* type (one with a precision/scale, like `DECIMAL(12, 2)`, or a length) on a `CAST` used directly inside a procedural expression (`PLS-00103`) — only an unconstrained type is legal there. |
| [T-SQL sized parameter/return types (`DECIMAL(5,2)`, `NVARCHAR(50)`) → unconstrained on an Oracle routine header](procedural/oracle-formal-parameter-types-unconstrained.md) | Oracle's PL/SQL forbids length, precision, or scale on a *formal parameter* or *function return* type declaration — `PLS-00103` — even though the identical sized type is perfectly legal on a `CREATE TABLE` column. |
| [T-SQL `IF EXISTS (<real query>) BEGIN ... END [ELSE ...]` → Oracle cursor `FOR` loop over a `DUAL` probe](procedural/if-exists-control-flow-to-oracle-for-loop.md) | `IF EXISTS (SELECT ...) BEGIN ... END` is ordinary control flow over real table data (not a system-catalog idempotency guard) — a migration script checking "has this step already run?" before doing more work, for example. |

### PostgreSQL as source

| [Date/time](#datetime-arithmetic-and-formatting-4) | [Strings](#strings-concatenation-and-collation-4) | [Aggregates & windows](#aggregates-and-window-functions-4) | [Booleans](#booleans-the-valuepredicate-duality-4) | [DML](#dml-pivotunpivot-merge-delete-row-values-4) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-4) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-4) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS](datetime/dateadd-month-to-oracle-add-months.md) | T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d, INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the day-of-month* and clamp down only when the target month is shorter: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`). |
| [PostgreSQL date_trunc → Oracle TRUNC format codes and T-SQL ISO week](datetime/date-trunc-to-oracle-trunc.md) | PostgreSQL `date_trunc('week', ts)` truncates to the start of the ISO week — **Monday** — and `date_trunc('quarter', ts)` to the first day of the quarter. |
| [Multi-field PostgreSQL INTERVAL decomposition](datetime/postgresql-interval-decomposition.md) | PostgreSQL accepts a verbose, multi-unit interval literal in one string: `INTERVAL '1 year 2 months 3 days'`. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [PostgreSQL `regexp_replace` flags → Oracle/MySQL positional occurrence + backreference respelling](strings-collation/regexp-replace-flags-and-backreferences.md) | PostgreSQL's `regexp_replace(source, pattern, replacement, flags)` fourth argument is a **flags string** (`'g'` for global, `'i'` for case-insensitive, …); Oracle's and MySQL's `REGEXP_REPLACE` instead take a **numeric** occurrence/position argument in that slot, and both already replace every match by default. |
| [Unary bitwise `~x`/NOT → Oracle `-(x) - 1`, MySQL `CAST(~x AS SIGNED)`](strings-collation/unary-bitwise-not-emulation.md) | PostgreSQL and T-SQL's unary bitwise NOT (`~x`) has no direct spelling on Oracle at all (PL/SQL has no bitwise NOT operator or built-in), and MySQL's `~x` operates on an *unsigned* 64-bit integer, so a plain `~5` there returns a huge unsigned complement rather than the signed `-6` the source engine intended. |
| [PostgreSQL `ILIKE` (case-insensitive `LIKE`) → `UPPER(x) LIKE UPPER(pattern)`](strings-collation/ilike-upper-comparison.md) | PostgreSQL's `ILIKE` is a case-insensitive `LIKE` operator — no other target engine has a dedicated case-insensitive pattern-match operator (T-SQL and MySQL's default collations are already case-insensitive, but Oracle's is case-sensitive by default and has no `ILIKE` spelling at all). |
| [Infix bitwise operators (`&`, `\|`, `^`, `<<`, `>>`) → Oracle `BITAND`/`POWER` identities](strings-collation/bitwise-operators-to-oracle-identities.md) | Oracle has no infix bitwise operators at all: `\|` is string concatenation there, and `^`/`&` are outright errors. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](aggregates-windows/groups-window-frame.md) | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](aggregates-windows/filter-clause.md) | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [`bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle](aggregates-windows/bool-or-and-value-wrapping.md) | `(a > 1)::int` and `bool_or(pred)` both need a predicate's truth value used as an ordinary scalar (a `CAST` operand, or an aggregate argument). |
| [`bool_or(...) FILTER (WHERE …)` composition (PostgreSQL) → T-SQL / Oracle](aggregates-windows/bool-or-filter-composition.md) | `bool_or(a > 5) FILTER (WHERE b = 1)` combines the boolean-aggregate value wrapping above with `FILTER`'s `agg(CASE WHEN cond THEN arg END)` rewrite in a single expression. |
| [`CAST` folding for `LISTAGG`/`STRING_AGG` value arguments (PostgreSQL) → Oracle / T-SQL](aggregates-windows/cast-folding-listagg-string-agg.md) | `string_agg(x::text, ',' ORDER BY x)` casts the aggregate argument to `TEXT` before joining. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](aggregates-windows/any-value-to-tsql.md) | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](aggregates-windows/distinct-on.md) | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](aggregates-windows/cast-to-integer-rounding.md) | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/predicate-in-value-position.md) | A comparison, boolean combinator, or null-test used as an ordinary value — `SELECT (a > b) AS c`, `SELECT (b1 AND a3) AS b3`, `SELECT (id IS NOT NULL) AS a3` — is legal on MySQL/PostgreSQL (comparisons and booleans are 1/0/NULL values there). |
| [`NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/not-of-truthy-value.md) | The same duality inside procedural bodies: `SET done = NOT done` (MySQL) or `RETURN <predicate>` from a function declared to return a boolean assigns/returns a value, not a predicate. |
| [A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/value-in-predicate-position.md) | MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN` return type demands an actual boolean expression, not a `NUMBER`. |
| [`flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle](booleans/boolean-column-is-true-false.md) | PostgreSQL's `IS TRUE`/`IS FALSE`/`IS NOT TRUE`/`IS NOT FALSE` predicate accepts `TRUE`/`FALSE`/`NULL`/`UNKNOWN` as its right-hand side — never an integer. |
| [`IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`](booleans/is-distinct-from.md) | PostgreSQL's `IS [NOT] DISTINCT FROM` is a null-safe equality: unlike `=`, it never itself evaluates to `UNKNOWN` — `NULL IS NOT DISTINCT FROM NULL` is `TRUE`, `1 IS DISTINCT FROM NULL` is `TRUE`. |
| [Boolean-to-text/char rendering (PostgreSQL `::text` / MySQL `CAST(... AS CHAR)`)](booleans/boolean-to-text-rendering.md) | PostgreSQL renders a boolean cast to text as the words `'true'`/`'false'`; MySQL has no boolean text representation at all — its booleans are ordinary integers, so casting one to a character type gives `'1'`/`'0'` instead. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](dml/multi-join-update-from.md) | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](dml/row-value-inequality.md) | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](dml/from-values-to-union-all.md) | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](dml/from-generate-series.md) | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |
| [`GROUP BY 1` (positional ordinal) → the actual `SELECT`-list column name](dml/group-by-ordinal-resolved.md) | PostgreSQL accepts a positional ordinal in `GROUP BY` — `GROUP BY 1` groups by whatever the first `SELECT`-list expression is. |
| [`INSERT ... ON CONFLICT` / `ON DUPLICATE KEY UPDATE` upsert clause → per-target idiom](dml/upsert-clause-modeled-per-target.md) | PostgreSQL's `INSERT ... ON CONFLICT (key) DO UPDATE/DO NOTHING` and MySQL's `INSERT ... ON DUPLICATE KEY UPDATE` / `INSERT IGNORE` are each one engine's own upsert syntax. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](ddl/session-temp-tables-to-oracle.md) | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](ddl/fk-on-update-action-to-oracle.md) | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](ddl/sequence-negative-option-spelling.md) | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |
| [Nameless `CREATE INDEX ON t(col)` (PostgreSQL) → T-SQL](ddl/nameless-create-index-to-tsql.md) | PostgreSQL allows `CREATE INDEX ON t (col)` with no index name — the server picks one internally (`t_col_idx`-shaped, but never surfaced to the script). |
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](ddl/truncate-restart-identity-cascade.md) | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |
| [PostgreSQL `ALTER COLUMN a DROP DEFAULT` → Oracle `MODIFY ... DEFAULT NULL`, T-SQL dynamic-SQL script](ddl/alter-column-drop-default.md) | PostgreSQL's `ALTER TABLE t ALTER COLUMN a DROP DEFAULT` removes a column's default expression by name-free reference — no other engine has an equivalent "just remove whatever default is there" clause. |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`](procedural/implicit-found-flag.md) | PL/pgSQL keeps one implicit boolean, `FOUND`, updated by the *last* `SELECT INTO`, `UPDATE`, `DELETE`, `INSERT`, or `FETCH` in the routine — it answers "did that last statement affect/return a row?" for the routine as a whole, not for one named cursor. |
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](procedural/raiserror-expression-messages.md) | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [`RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)](procedural/returns-void-signature-synthesis.md) | A PostgreSQL function declared `RETURNS void` returns nothing — per the corpus's own count, the single most common plpgsql function shape (62 occurrences), typically a side-effecting helper invoked for its `INSERT`/`UPDATE`, never for a value. |
| [A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → a ref-cursor parameter (Oracle `SYS_REFCURSOR` OUT, PostgreSQL `refcursor` INOUT), propagated to `CALL` sites](procedural/bare-result-select-to-refcursor.md) | A MySQL or T-SQL procedure can hand back a result set simply by running a `SELECT` with no `INTO` target partway through the body. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](procedural/trigger-reading-own-table.md) | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [T-SQL scalar function: synthesized trailing `RETURN NULL` after an all-branches-return `IF`/`ELSE`](procedural/scalar-function-trailing-return-null.md) | T-SQL requires a scalar function's **last statement** to literally *be* a `RETURN` (error 455 otherwise) — even when the function's body already returns a value on every possible branch, such as an `IF ... ELSE` where both arms end in `RETURN`. |
| [A local variable named after an Oracle built-in (`count`) → renamed everywhere it's used](procedural/oracle-builtin-name-collision-rename.md) | `count` is a perfectly legal PL/pgSQL local variable name — PostgreSQL has no keyword collision. |
| [PostgreSQL `SQLSTATE` / Oracle `SQLCODE` → `CAST(ERROR_STATE()/ERROR_NUMBER() AS NVARCHAR(n))`](procedural/sqlstate-sqlcode-to-tsql-error-functions.md) | PostgreSQL's `SQLSTATE` and Oracle's `SQLCODE` are bare identifiers, readable directly inside an exception handler as the caught error's state code or numeric code. |

### PostgreSQL as target

| [Date/time](#datetime-arithmetic-and-formatting-5) | [Strings](#strings-concatenation-and-collation-5) | [Aggregates & windows](#aggregates-and-window-functions-5) | [Booleans](#booleans-the-valuepredicate-duality-5) | [DML](#dml-pivotunpivot-merge-delete-row-values-5) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-5) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-5) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)](datetime/oracle-add-months-to-dateadd.md) | Oracle's `ADD_MONTHS` sticks to the *target* month's last day whenever the operand is its own month's last day — `ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. |
| [MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target](datetime/mysql-timestampdiff-complete-month.md) | MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts **complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')` = `1`, not `2`, because the end's day-of-month (`10`) has not reached the start's (`15`) — the final partial month does not count. |
| [MySQL TO_DAYS year-0000 epoch rebase](datetime/mysql-to-days-epoch-rebase.md) | MySQL `TO_DAYS(d)` returns the count of days since a notional `0000-01-01`. |
| [Multi-field PostgreSQL INTERVAL decomposition](datetime/postgresql-interval-decomposition.md) | PostgreSQL accepts a verbose, multi-unit interval literal in one string: `INTERVAL '1 year 2 months 3 days'`. |
| [MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets](datetime/mysql-compound-extract-units.md) | MySQL's `EXTRACT` accepts several **compound** units — `YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack two or more calendar fields into a single decimal-weighted number in one call. |
| [Oracle `NUMTODSINTERVAL` / `NUMTOYMINTERVAL` → PostgreSQL `INTERVAL`](datetime/numtointerval-oracle-to-postgresql.md) | Oracle's `NUMTODSINTERVAL(n, 'unit')` and `NUMTOYMINTERVAL(n, 'unit')` build a standalone day-to-second or year-to-month `INTERVAL` value from a number and a unit name (`NUMTODSINTERVAL(-3, 'DAY')` is "an interval of minus three days"). |
| [An Oracle `DATE` literal inside a derived-table projection → its typing survives to the outer column reference](datetime/date-typing-propagated-through-derived-table.md) | `SELECT ShipDate - OrderDate FROM (SELECT DATE '2020-01-10' ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x` computes a day count on Oracle, since `DATE - DATE` is arithmetic there. |
| [T-SQL `CONVERT(type, value, style)`'s numeric style code → a per-target format function, or ignored when the target type isn't a date](datetime/convert-style-code-per-target.md) | T-SQL's `CONVERT` takes an optional third argument, a numeric *style* code, whose meaning depends entirely on what the second argument is being converted to: against a date/time type, it selects a date format (`120` = ISO `yyyy-mm-dd hh:mi:ss`, `103` = British/French `dd/mm/yyyy`, ...); against a non-date type, the style code is only meaningful for a handful of special cases (binary-to-string encodings) and is otherwise ignored. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Oracle `'' ≡ NULL`](strings-collation/oracle-empty-string-is-null.md) | Every other engine stores and compares an empty string `''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('', 'x')` is `''`. |
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [3-argument `CHARINDEX(needle, s, start)` (T-SQL) → PostgreSQL zero-guarded `POSITION`](strings-collation/charindex-start-argument-zero-guard.md) | T-SQL's `CHARINDEX(needle, s, start)` searches only from `start` onward, and returns `0` (not `NULL`) when the needle isn't found anywhere from `start` on. |
| [A T-SQL hex/binary literal used in arithmetic → folded to its integer value](strings-collation/hex-binary-literal-arithmetic-fold.md) | T-SQL's `0x0A` is a binary-string literal that also behaves as an integer in numeric contexts (`0x0A + 5` = `15`). |
| [Oracle `LTRIM(s, chars)`/`RTRIM(s, chars)` → `TRIM(LEADING/TRAILING chars FROM s)`](strings-collation/oracle-ltrim-rtrim-charset-reverse.md) | This is the reverse of Character-set `TRIM(chars FROM string)` → Oracle: Oracle's own `LTRIM`/`RTRIM` already accept a multi-character trim set as their second argument natively. |
| [Oracle `DECODE` with mixed-type result branches → `CASE` with a `CAST` inserted to unify types](strings-collation/decode-mixed-type-branch-cast.md) | Oracle's `DECODE(expr, search1, result1, ..., default)` tolerates result branches of different types — a string in one branch, a number in another — since Oracle resolves the whole expression's type loosely at runtime. |
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](strings-collation/no-target-spelling-case-chain.md) | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
| [T-SQL `NCHAR(n)` Unicode code point → PostgreSQL `CHR`, MySQL `CHAR(... USING utf32)`, Oracle `NCHR`/`UNISTR`](strings-collation/nchar-code-point-per-target.md) | T-SQL's `NCHAR(n)` returns the character for Unicode code point `n` — an integer argument (a `0x…` literal is still a *number* there, not a byte string) — with no matching built-in on any other engine under that name. |
| [Oracle extended `INSTR` (occurrence / backward search) over **literal** arguments → the computed position](strings-collation/oracle-instr-literal-fold.md) | Oracle's 4-argument `INSTR(s, sub, start, occurrence)` finds the `occurrence`-th match at or after `start` — and, when `start` is negative, searches **backward** from the end of the string instead. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-keep-dense-rank.md) | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |
| [`DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL](aggregates-windows/distinct-numeric-order-by.md) | `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-')` de-duplicates `x` and orders the *numeric* values before joining them. |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-listagg-over.md) | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](aggregates-windows/mod-by-zero-divisor.md) | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](aggregates-windows/tsql-cast-int-truncation-reverse.md) | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [Boolean-to-text/char rendering (PostgreSQL `::text` / MySQL `CAST(... AS CHAR)`)](booleans/boolean-to-text-rendering.md) | PostgreSQL renders a boolean cast to text as the words `'true'`/`'false'`; MySQL has no boolean text representation at all — its booleans are ordinary integers, so casting one to a character type gives `'1'`/`'0'` instead. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](dml/pivot.md) | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](dml/unpivot.md) | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |
| [`WHEN NOT MATCHED BY SOURCE` (T-SQL) → PostgreSQL / Oracle](dml/merge-when-not-matched-by-source.md) | T-SQL's `MERGE` can act on target rows that have **no** matching source row at all (`WHEN NOT MATCHED BY SOURCE THEN UPDATE/DELETE`) — an anti-join over the `ON` predicate. |
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](dml/multi-table-delete-join.md) | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](dml/delete-top-n-row-cap.md) | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](dml/multi-join-update-from.md) | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |
| [`INSERT`/`UPDATE … OUTPUT` (T-SQL) → PostgreSQL `RETURNING` / Oracle carrier](dml/output-to-returning.md) | T-SQL's `OUTPUT INSERTED.col, DELETED.col` returns a result set of the affected rows' before/after values alongside the DML. |
| [`OUTPUT … INTO` redirect (T-SQL) → PostgreSQL](dml/output-into-redirect.md) | `OUTPUT INSERTED.a INTO log(a)` redirects the output rows into a second table instead of returning them to the caller. |
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](dml/set-op-trailing-order-by.md) | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](dml/from-values-to-union-all.md) | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](dml/from-generate-series.md) | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](dml/recursive-cte-keyword-and-column-list.md) | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](dml/iif-to-case-or-native.md) | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](dml/money-literal-shorthand.md) | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](ddl/tsql-identity-scope-reads.md) | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |
| [T-SQL `BIT` `0`/`1` values (defaults, `INSERT`, `UPDATE`, incl. inside procedure bodies) → PostgreSQL `BOOLEAN`](ddl/tsql-bit-to-postgresql-boolean.md) | T-SQL's `BIT` type behaves like a 1-bit integer: `0`/`1` literals are valid in a `DEFAULT` clause, an `INSERT ... VALUES` list, or an `UPDATE ... SET`, with no special casting. |
| [T-SQL `ALTER COLUMN <c> <type>` re-states the column's last-known nullability → PostgreSQL (both directions)](ddl/alter-column-nullability.md) | T-SQL's `ALTER COLUMN <c> <type>` bakes type *and* nullability into one clause — omitting a `NULL`/`NOT NULL` keyword does not mean "leave nullability alone," it means "make the column nullable," silently dropping an existing `NOT NULL` the statement never mentioned. |
| [One-word vs two-word negative options (Oracle `NOMAXVALUE`/`NOCYCLE` vs T-SQL/PostgreSQL `NO MAXVALUE`/`NO CYCLE`)](ddl/sequence-negative-option-spelling.md) | `CREATE SEQUENCE … NO MAXVALUE NO CYCLE` (T-SQL, PostgreSQL) and `CREATE SEQUENCE … NOMAXVALUE NOCYCLE` (Oracle) both mean "no upper bound, do not wrap around" — the same option, spelled as two words on some engines and fused to one word on Oracle. |
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](ddl/mysql-enum-to-varchar-check.md) | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](ddl/mysql-unsigned-check-synthesis.md) | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](ddl/create-type-alias-harvested.md) | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |
| [Oracle `RAW(16) DEFAULT SYS_GUID()` → PostgreSQL `BYTEA` with a matching `DECODE(...)` default](ddl/raw-guid-default-bytea.md) | `RAW(16) DEFAULT SYS_GUID()` is Oracle's idiom for a binary-GUID primary key: `SYS_GUID()` generates a 16-byte raw value used directly as the default. |
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](ddl/oracle-alter-add-parenthesized-unwrap.md) | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |
| [A plain `DROP TABLE t` → `DROP TABLE IF EXISTS t` on PostgreSQL](ddl/drop-table-idempotent-if-exists.md) | A migration script is meant to be re-runnable against a target that may already have run it once before — a bare `DROP TABLE t` errors on a second run if the table is already gone, stopping the whole script partway through. |
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](ddl/tsql-existence-guard-catalog-probes.md) | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |
| [Oracle catalog probes inside dynamic DDL (`user_indexes`/`user_tab_cols`) → the target's own system view](ddl/oracle-catalog-probe-rewritten-per-target.md) | An Oracle PL/SQL script sometimes checks its own data dictionary before running dynamic DDL through `EXECUTE IMMEDIATE` — for example resolving an index's owning table before a table-less `DROP INDEX` (Oracle names only the index; T-SQL requires the table too, error 159), or gating an `ALTER TABLE ... MODIFY` on whether a column already has the target shape. |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [`EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/exec-sp-degrade-policy.md) | T-SQL system procedures (`sp_rename`, `sp_who`, …) call into SQL Server's own catalog/admin machinery. |
| [Statement-after-`EXEC` survival fix](procedural/statement-after-exec-survival.md) | A degraded system-proc `EXEC`, followed by another statement on the same line separated only by `;` (not a batch-separating `GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`. |
| [`SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/set-identity-insert-degrade.md) | T-SQL requires `IDENTITY_INSERT` to be explicitly turned `ON` before a script can supply its own value for an identity column, then turned back `OFF`. |
| [`SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL](procedural/sqlplus-client-directives.md) | SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`, etc.) are **line-oriented client-tool commands**, not SQL statements — they carry no trailing `;` and configure the SQL*Plus session, not the database. |
| [Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL](procedural/oracle-type-rowtype-references.md) | `v_id employees.id%TYPE` declares a variable with **whatever type** the referenced column currently has — a live binding to the schema, not a fixed type name. |
| [MySQL `DECLARE {EXIT\|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)](procedural/mysql-declare-handler.md) | MySQL declares an error handler *separately* from the code it protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in the block's declaration section, naming the condition(s) it reacts to and a single action statement. |
| [RAISERROR (T-SQL) ↔ Oracle `RAISE_APPLICATION_ERROR` / PostgreSQL `RAISE EXCEPTION`: expression messages and printf substitutions](procedural/raiserror-expression-messages.md) | T-SQL's `RAISERROR` accepts only a literal, a variable, or a message id as its first argument — never an expression. |
| [A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → a ref-cursor parameter (Oracle `SYS_REFCURSOR` OUT, PostgreSQL `refcursor` INOUT), propagated to `CALL` sites](procedural/bare-result-select-to-refcursor.md) | A MySQL or T-SQL procedure can hand back a result set simply by running a `SELECT` with no `INTO` target partway through the body. |
| [Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL](procedural/scroll-cursor-fetch.md) | A T-SQL `SCROLL` cursor supports non-forward fetches: `FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](procedural/trigger-reading-own-table.md) | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [T-SQL `INSTEAD OF` trigger → PostgreSQL (native on views, emulated on tables)](procedural/tsql-instead-of-trigger.md) | T-SQL allows `INSTEAD OF` on both views *and* base tables — the trigger body runs **instead of** the attempted INSERT/UPDATE/DELETE, which is never applied on its own. |
| [T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL](procedural/tsql-cursor-variable-binding.md) | T-SQL lets a cursor be bound to a *variable* in two steps: a bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... FOR <query>` to attach the query, then a bare `OPEN @cur;`. |
| [T-SQL `@@FETCH_STATUS` → Oracle / PostgreSQL / MySQL](procedural/tsql-fetch-status-to-oracle-postgresql-mysql.md) | T-SQL exposes cursor state through a single global variable, `@@FETCH_STATUS`, checked right after a `FETCH` (`0` = a row was returned, `-1` = no more rows, `-2` = the fetched row is missing). |
| [`EXECUTE IMMEDIATE '<sql>' INTO x` (Oracle) → a two-statement T-SQL capture](procedural/execute-immediate-into-capture.md) | Oracle's `EXECUTE IMMEDIATE '<sql>' INTO x` runs a dynamic query and captures its single-row result directly into a variable — PostgreSQL's `EXECUTE '<sql>' INTO x` is the same idiom natively. |
| [T-SQL's `CAST(N'' AS XML).value('xs:base64Binary(...)', ...)` base64-decode idiom → each target's native call](procedural/base64-xml-idiom-per-target.md) | T-SQL has no direct `BASE64_DECODE` function; the idiomatic way to decode a base64 string into binary is to route it through the XML type system — `CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@x"))', 'VARBINARY(MAX)')`. |
| [T-SQL `ERROR_MESSAGE()` (inside a `CATCH` block) → each target's own error-text accessor](procedural/error-message-function-per-target.md) | Inside a T-SQL `CATCH` block, `ERROR_MESSAGE()` reads the text of the error that was just caught. |
| [A `DECLARE` written mid-block (inside an `IF`/`CATCH`) → hoisted to the routine's top declaration section](procedural/mid-block-declare-hoist.md) | T-SQL allows `DECLARE @v type = init;` anywhere a statement is legal — inside an `IF` body, inside a `CATCH` block, nested arbitrarily deep. |
| [`SELECT ... INTO :NEW.col1, :NEW.col2` (Oracle trigger) → PostgreSQL `NEW.col`, MySQL session variables](procedural/pseudo-row-into-mysql-session-vars.md) | An Oracle row-level trigger can `SELECT ... INTO :NEW.col1, :NEW.col2` directly — assigning query results straight into the pseudo-row's columns. |
| [A package-qualified ref-cursor type (`pkg.my_cursor`) → the target's own ref-cursor type](procedural/refcursor-package-type-and-inout-mode.md) | An Oracle procedure parameter can be typed with a package-defined `REF CURSOR` subtype (`v_cur OUT pkg_ret.my_cursor`) — `pkg_ret.my_cursor` is only meaningful *inside that package*, never on a target with no package concept at all. |
| [A top-level T-SQL/Oracle batch needing a procedural construct → PostgreSQL `DO $$ ... $$`](procedural/toplevel-batch-do-block-wrap.md) | A standalone (not-inside-a-`CREATE PROCEDURE`) T-SQL batch or Oracle anonymous block can freely mix `PRINT`/`DBMS_OUTPUT`, variable declarations, `IF`, cursor `FOR` loops, and dynamic `EXECUTE` — all procedural constructs that only exist *inside* a routine body on PostgreSQL. |
| [T-SQL `THROW`/`RAISERROR`'s numeric error code → each target's own error-code slot](procedural/throw-raiserror-numeric-code-per-target.md) | T-SQL's `THROW 50001, 'not found', 1` and `RAISERROR('not found', 16, 1)` (with a matching custom message id registered separately) both carry a *numeric error code* alongside the message text. |
| [A purely set-based T-SQL trigger (`FROM inserted JOIN deleted`) → PostgreSQL statement-level trigger with named transition tables](procedural/tsql-set-based-trigger-to-pg-statement-level.md) | T-SQL triggers are always statement-level, exposing the whole batch of affected rows through two pseudo-tables, `inserted`/`deleted`, that a set-based trigger body joins against directly (`INSERT ... SELECT ... FROM inserted i JOIN deleted d ON d.id = i.id`). |
| [T-SQL `HASHBYTES('SHA2_256', x)` → PostgreSQL `sha256`, wrapped for a character argument](procedural/hashbytes-sha256-to-postgresql.md) | sqlglot canonicalizes T-SQL's `HASHBYTES('SHA2_256', x)` to a bare `SHA256(x)` call reaching PostgreSQL, but PostgreSQL's `sha256` takes a **bytea**, not text — `sha256(x)` over a character column is "function sha256(text) does not exist" at *runtime*, a defect a compile-only validity check does not catch (the call parses fine; it just never runs). |
| [Implicit row count in EXPRESSION position (Oracle `SQL%ROWCOUNT` / T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`) → PostgreSQL `GET DIAGNOSTICS` hoist](procedural/rowcount-expression-hoist-to-postgresql.md) | Oracle's `SQL%ROWCOUNT`, T-SQL's `@@ROWCOUNT`, and MySQL's `ROW_COUNT()` are all readable **inline**, as an expression, anywhere a value is expected (`IF SQL%ROWCOUNT <> 1`, `v := SQL%ROWCOUNT + 1`, a call argument, a `RETURN`). |

### MySQL as source

| [Date/time](#datetime-arithmetic-and-formatting-6) | [Strings](#strings-concatenation-and-collation-6) | [Aggregates & windows](#aggregates-and-window-functions-6) | [Booleans](#booleans-the-valuepredicate-duality-6) | [DML](#dml-pivotunpivot-merge-delete-row-values-6) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-6) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-6) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [DATEADD(MONTH) (T-SQL/MySQL/PostgreSQL) → Oracle ADD_MONTHS](datetime/dateadd-month-to-oracle-add-months.md) | T-SQL `DATEADD(MONTH, n, d)`, MySQL `DATE_ADD(d, INTERVAL n MONTH)` and PostgreSQL `d + n * INTERVAL '1 month'` all *keep the day-of-month* and clamp down only when the target month is shorter: `DATEADD(MONTH, 1, '2020-02-29')` = `2020-03-29` (not `2020-03-31`). |
| [MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target](datetime/mysql-timestampdiff-complete-month.md) | MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts **complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')` = `1`, not `2`, because the end's day-of-month (`10`) has not reached the start's (`15`) — the final partial month does not count. |
| [MySQL TO_DAYS year-0000 epoch rebase](datetime/mysql-to-days-epoch-rebase.md) | MySQL `TO_DAYS(d)` returns the count of days since a notional `0000-01-01`. |
| [MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets](datetime/mysql-compound-extract-units.md) | MySQL's `EXTRACT` accepts several **compound** units — `YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack two or more calendar fields into a single decimal-weighted number in one call. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [MySQL `LOCATE('', s)` (always `1`) → T-SQL guarded `CASE`](strings-collation/locate-empty-needle-guard.md) | MySQL's `LOCATE(needle, haystack)` special-cases an empty needle: `LOCATE('', s)` is always `1`, regardless of `s`, treating the empty string as matching at the very start. |
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](strings-collation/no-target-spelling-case-chain.md) | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
| [Infix bitwise operators (`&`, `\|`, `^`, `<<`, `>>`) → Oracle `BITAND`/`POWER` identities](strings-collation/bitwise-operators-to-oracle-identities.md) | Oracle has no infix bitwise operators at all: `\|` is string concatenation there, and `^`/`&` are outright errors. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [`DISTINCT` + numeric `ORDER BY` restructure (MySQL) → PostgreSQL](aggregates-windows/distinct-numeric-order-by.md) | `GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '-')` de-duplicates `x` and orders the *numeric* values before joining them. |
| [`ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL](aggregates-windows/any-value-to-tsql.md) | `ANY_VALUE(x)` returns an arbitrary (implementation picked) value from the group — used to satisfy a functional-dependency `GROUP BY` without an aggregate wrapper. |
| [`CAST(... AS <integer type>)` rounding vs. truncation trade (PostgreSQL / MySQL) → T-SQL](aggregates-windows/cast-to-integer-rounding.md) | Casting a fractional value to an integer type rounds half-away-from-zero on PostgreSQL (`CAST(2.7 AS INT)` = `3`, `7.5::int` = `8`) and on MySQL's `SIGNED` cast (`CAST(2.7 AS SIGNED)` = `3`); T-SQL's `CAST`/`CONVERT` to an integer type always **truncates** (a plain `CAST(2.7 AS INT)` would give `2`). |
| [`MOD`/`%` by a zero divisor (MySQL) → PostgreSQL / T-SQL / Oracle](aggregates-windows/mod-by-zero-divisor.md) | MySQL's `MOD`/`%` returns `NULL` when the divisor is `0` (`5 MOD 0` is `NULL`, not an error); PostgreSQL and T-SQL raise a division-by-zero error, and Oracle's `MOD` returns the **dividend** unchanged (`MOD(5, 0)` = `5`) — three different behaviors for the same input, all different from MySQL's. |
| [An unordered MySQL `GROUP_CONCAT` → Oracle `LISTAGG` gains a synthesized `WITHIN GROUP (ORDER BY <arg>)`](aggregates-windows/group-concat-synthesized-within-group-oracle.md) | MySQL's `GROUP_CONCAT(expr SEPARATOR sep)` needs no ordering clause — an unordered call is valid MySQL, with whatever order the engine happens to produce. |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/predicate-in-value-position.md) | A comparison, boolean combinator, or null-test used as an ordinary value — `SELECT (a > b) AS c`, `SELECT (b1 AND a3) AS b3`, `SELECT (id IS NOT NULL) AS a3` — is legal on MySQL/PostgreSQL (comparisons and booleans are 1/0/NULL values there). |
| [`NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/not-of-truthy-value.md) | The same duality inside procedural bodies: `SET done = NOT done` (MySQL) or `RETURN <predicate>` from a function declared to return a boolean assigns/returns a value, not a predicate. |
| [A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle](booleans/value-in-predicate-position.md) | MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN` return type demands an actual boolean expression, not a `NUMBER`. |
| [A value-wrapped predicate compared again in predicate position collapses back to the predicate (MySQL) → T-SQL](booleans/value-wrapped-predicate-collapse.md) | MySQL lets you compare a boolean value against `1`/`0`, or test it with `IS TRUE`, even when that value is itself already a predicate: `WHERE (c2 IS NOT NULL) = 1`. |
| [Boolean-to-text/char rendering (PostgreSQL `::text` / MySQL `CAST(... AS CHAR)`)](booleans/boolean-to-text-rendering.md) | PostgreSQL renders a boolean cast to text as the words `'true'`/`'false'`; MySQL has no boolean text representation at all — its booleans are ordinary integers, so casting one to a character type gives `'1'`/`'0'` instead. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [Multi-table `DELETE … JOIN` (MySQL) → PostgreSQL / T-SQL / Oracle](dml/multi-table-delete-join.md) | `DELETE t1 FROM t1 JOIN t2 ON … WHERE t2.flag = 1` deletes rows from `t1` filtered by a join against `t2`. |
| [Row-value inequality (PostgreSQL / Oracle / MySQL) → T-SQL](dml/row-value-inequality.md) | `(a, b) > (1, 5)` is a lexicographic row-value comparison — common for keyset pagination — true when `a > 1`, or `a = 1 AND b > 5`. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](dml/recursive-cte-keyword-and-column-list.md) | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |
| [T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`](dml/iif-to-case-or-native.md) | T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are both a three-argument ternary conditional expression — neither function exists on Oracle or PostgreSQL, so carrying either name across verbatim would be an unresolved-function error there. |
| [`INSERT ... ON CONFLICT` / `ON DUPLICATE KEY UPDATE` upsert clause → per-target idiom](dml/upsert-clause-modeled-per-target.md) | PostgreSQL's `INSERT ... ON CONFLICT (key) DO UPDATE/DO NOTHING` and MySQL's `INSERT ... ON DUPLICATE KEY UPDATE` / `INSERT IGNORE` are each one engine's own upsert syntax. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`](ddl/session-temp-tables-to-oracle.md) | A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp` table, and a MySQL `TEMPORARY` table are all **session-scoped**: their definition and rows live only for the current connection, and — critically — their rows **survive an intervening `COMMIT`**. |
| [`ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle](ddl/fk-on-update-action-to-oracle.md) | `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE` propagates both a delete and a primary-key update on the parent to the child. |
| [Self-referencing FK cascade (MySQL) → T-SQL](ddl/self-referencing-fk-cascade.md) | `FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL`, where the FK references its **own** table (an employee/manager hierarchy). |
| [`ENUM('lo','mid','hi')` (MySQL) → PostgreSQL / T-SQL / Oracle VARCHAR + CHECK](ddl/mysql-enum-to-varchar-check.md) | A MySQL `ENUM` column stores one of a fixed value list, and — the part that matters here — **orders by declaration index**, not alphabetically: `ENUM('lo','mid','hi')` sorts `lo < mid < hi` regardless of the values' lexical order. |
| [MySQL `UNSIGNED` → widened signed type + synthesized `CHECK (col >= 0)`](ddl/mysql-unsigned-check-synthesis.md) | A MySQL `UNSIGNED` integer column can never hold a negative value — that's enforced structurally by the column's own type, not by a constraint. |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [MySQL `DECLARE {EXIT\|CONTINUE} HANDLER FOR ...` → block-structured exception handling (PostgreSQL / Oracle / T-SQL)](procedural/mysql-declare-handler.md) | MySQL declares an error handler *separately* from the code it protects — `DECLARE EXIT HANDLER FOR SQLEXCEPTION <stmt>` sits anywhere in the block's declaration section, naming the condition(s) it reacts to and a single action statement. |
| [A bare result `SELECT` inside a procedure body (MySQL / PostgreSQL / T-SQL) → a ref-cursor parameter (Oracle `SYS_REFCURSOR` OUT, PostgreSQL `refcursor` INOUT), propagated to `CALL` sites](procedural/bare-result-select-to-refcursor.md) | A MySQL or T-SQL procedure can hand back a result set simply by running a `SELECT` with no `INTO` target partway through the body. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](procedural/trigger-reading-own-table.md) | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [Leading `DECLARE` block reordered (MySQL): variables before cursors](procedural/mysql-declare-reorder.md) | MySQL requires every `DECLARE <cursor>` to come *after* every `DECLARE <variable>` in the same block (error 1337, "Variable or condition declaration after cursor or handler declaration") — a rule no other target engine imposes, so a source routine that declares its cursor before its scalar variables (a legal order on Oracle/T-SQL/PostgreSQL) needs its leading declaration block reordered for MySQL specifically. |
| [Implicit row count in EXPRESSION position (Oracle `SQL%ROWCOUNT` / T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`) → PostgreSQL `GET DIAGNOSTICS` hoist](procedural/rowcount-expression-hoist-to-postgresql.md) | Oracle's `SQL%ROWCOUNT`, T-SQL's `@@ROWCOUNT`, and MySQL's `ROW_COUNT()` are all readable **inline**, as an expression, anywhere a value is expected (`IF SQL%ROWCOUNT <> 1`, `v := SQL%ROWCOUNT + 1`, a call argument, a `RETURN`). |

### MySQL as target

| [Date/time](#datetime-arithmetic-and-formatting-7) | [Strings](#strings-concatenation-and-collation-7) | [Aggregates & windows](#aggregates-and-window-functions-7) | [Booleans](#booleans-the-valuepredicate-duality-7) | [DML](#dml-pivotunpivot-merge-delete-row-values-7) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-7) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-7) |
|---|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [ADD_MONTHS (Oracle) → DATEADD/DATE_ADD/interval-add (T-SQL/MySQL/PostgreSQL)](datetime/oracle-add-months-to-dateadd.md) | Oracle's `ADD_MONTHS` sticks to the *target* month's last day whenever the operand is its own month's last day — `ADD_MONTHS('2020-02-29', 1)` = `2020-03-31`. |
| [MySQL TIMESTAMPDIFF complete-month adjustment, ported to every target](datetime/mysql-timestampdiff-complete-month.md) | MySQL `TIMESTAMPDIFF(MONTH, start, end)` counts **complete** month periods: `TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10')` = `1`, not `2`, because the end's day-of-month (`10`) has not reached the start's (`15`) — the final partial month does not count. |
| [MySQL TO_DAYS year-0000 epoch rebase](datetime/mysql-to-days-epoch-rebase.md) | MySQL `TO_DAYS(d)` returns the count of days since a notional `0000-01-01`. |
| [Multi-field PostgreSQL INTERVAL decomposition](datetime/postgresql-interval-decomposition.md) | PostgreSQL accepts a verbose, multi-unit interval literal in one string: `INTERVAL '1 year 2 months 3 days'`. |
| [MySQL compound `EXTRACT` units (`YEAR_MONTH`, `DAY_HOUR`, …) → all targets](datetime/mysql-compound-extract-units.md) | MySQL's `EXTRACT` accepts several **compound** units — `YEAR_MONTH`, `DAY_HOUR`, `DAY_MINUTE`, `DAY_SECOND`, and others — that pack two or more calendar fields into a single decimal-weighted number in one call. |
| [An Oracle `DATE` literal inside a derived-table projection → its typing survives to the outer column reference](datetime/date-typing-propagated-through-derived-table.md) | `SELECT ShipDate - OrderDate FROM (SELECT DATE '2020-01-10' ShipDate, DATE '2020-01-01' OrderDate FROM DUAL) x` computes a day count on Oracle, since `DATE - DATE` is arithmetic there. |
| [T-SQL `CONVERT(type, value, style)`'s numeric style code → a per-target format function, or ignored when the target type isn't a date](datetime/convert-style-code-per-target.md) | T-SQL's `CONVERT` takes an optional third argument, a numeric *style* code, whose meaning depends entirely on what the second argument is being converted to: against a date/time type, it selects a date format (`120` = ISO `yyyy-mm-dd hh:mi:ss`, `103` = British/French `dd/mm/yyyy`, ...); against a non-date type, the style code is only meaningful for a handful of special cases (binary-to-string encodings) and is otherwise ignored. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [Oracle `'' ≡ NULL`](strings-collation/oracle-empty-string-is-null.md) | Every other engine stores and compares an empty string `''` as a distinct, zero-length value: `'' IS NULL` is false, `COALESCE('', 'x')` is `''`. |
| [Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets](strings-collation/overlay-stuff-insert-splice.md) | Three engines each have a native "replace `len` characters of `string` at 1-based position `start` with `new`" function: PostgreSQL's `OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string, start, len, new)`, MySQL's `INSERT(string, start, len, new)`. |
| [PostgreSQL `regexp_replace` flags → Oracle/MySQL positional occurrence + backreference respelling](strings-collation/regexp-replace-flags-and-backreferences.md) | PostgreSQL's `regexp_replace(source, pattern, replacement, flags)` fourth argument is a **flags string** (`'g'` for global, `'i'` for case-insensitive, …); Oracle's and MySQL's `REGEXP_REPLACE` instead take a **numeric** occurrence/position argument in that slot, and both already replace every match by default. |
| [Unary bitwise `~x`/NOT → Oracle `-(x) - 1`, MySQL `CAST(~x AS SIGNED)`](strings-collation/unary-bitwise-not-emulation.md) | PostgreSQL and T-SQL's unary bitwise NOT (`~x`) has no direct spelling on Oracle at all (PL/SQL has no bitwise NOT operator or built-in), and MySQL's `~x` operates on an *unsigned* 64-bit integer, so a plain `~5` there returns a huge unsigned complement rather than the signed `-6` the source engine intended. |
| [A T-SQL hex/binary literal used in arithmetic → folded to its integer value](strings-collation/hex-binary-literal-arithmetic-fold.md) | T-SQL's `0x0A` is a binary-string literal that also behaves as an integer in numeric contexts (`0x0A + 5` = `15`). |
| [Oracle `LTRIM(s, chars)`/`RTRIM(s, chars)` → `TRIM(LEADING/TRAILING chars FROM s)`](strings-collation/oracle-ltrim-rtrim-charset-reverse.md) | This is the reverse of Character-set `TRIM(chars FROM string)` → Oracle: Oracle's own `LTRIM`/`RTRIM` already accept a multi-character trim set as their second argument natively. |
| [Oracle `DECODE` with mixed-type result branches → `CASE` with a `CAST` inserted to unify types](strings-collation/decode-mixed-type-branch-cast.md) | Oracle's `DECODE(expr, search1, result1, ..., default)` tolerates result branches of different types — a string in one branch, a number in another — since Oracle resolves the whole expression's type loosely at runtime. |
| [PostgreSQL `ILIKE` (case-insensitive `LIKE`) → `UPPER(x) LIKE UPPER(pattern)`](strings-collation/ilike-upper-comparison.md) | PostgreSQL's `ILIKE` is a case-insensitive `LIKE` operator — no other target engine has a dedicated case-insensitive pattern-match operator (T-SQL and MySQL's default collations are already case-insensitive, but Oracle's is case-sensitive by default and has no `ILIKE` spelling at all). |
| [Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`](strings-collation/no-target-spelling-case-chain.md) | MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and `FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if absent) have no equivalent built-in on any other engine. |
| [T-SQL `NCHAR(n)` Unicode code point → PostgreSQL `CHR`, MySQL `CHAR(... USING utf32)`, Oracle `NCHR`/`UNISTR`](strings-collation/nchar-code-point-per-target.md) | T-SQL's `NCHAR(n)` returns the character for Unicode code point `n` — an integer argument (a `0x…` literal is still a *number* there, not a byte string) — with no matching built-in on any other engine under that name. |
| [Oracle extended `INSTR` (occurrence / backward search) over **literal** arguments → the computed position](strings-collation/oracle-instr-literal-fold.md) | Oracle's 4-argument `INSTR(s, sub, start, occurrence)` finds the `occurrence`-th match at or after `start` — and, when `start` is negative, searches **backward** from the end of the string instead. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [`GROUPS` window frame (PostgreSQL / Oracle) → T-SQL / MySQL](aggregates-windows/groups-window-frame.md) | `OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)` frames the window by *peer groups* — every row sharing the same `ORDER BY` key is one frame unit — rather than by physical row count (`ROWS`) or by value distance (`RANGE`). |
| [Oracle `KEEP (DENSE_RANK FIRST/LAST …)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-keep-dense-rank.md) | `MAX(x) KEEP (DENSE_RANK LAST ORDER BY y)` is an **aggregate**, not a window function: it returns one row per group, taking `x` from the row(s) whose `y` is the dense-rank extreme. |
| [`agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle](aggregates-windows/filter-clause.md) | PostgreSQL's `FILTER (WHERE p)` restricts which rows an aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y > 5`) without a separate subquery or `CASE`; none of the other three engines parse the clause at all (T-SQL error 102, "incorrect syntax"). |
| [Oracle `LISTAGG(...) WITHIN GROUP (...) OVER (...)` → PostgreSQL / T-SQL / MySQL](aggregates-windows/oracle-listagg-over.md) | Oracle allows `LISTAGG` to be used as a **window** function (`OVER (PARTITION BY …)`), producing a running string aggregation — one output row per input row, not one per group. |
| [PostgreSQL `DISTINCT ON (a)` → T-SQL / MySQL / Oracle](aggregates-windows/distinct-on.md) | `SELECT DISTINCT ON (a) a, b FROM … ORDER BY a, b` returns exactly **one** row per distinct `a` — the first one under the `ORDER BY`. |
| [T-SQL `CAST(... AS <integer type>)` truncates; a fractional literal folds, and `AVG(int)` gets a `TRUNC` wrap going the other way](aggregates-windows/tsql-cast-int-truncation-reverse.md) | This is the reverse of `CAST(... AS <integer type>)` rounding vs. truncation trade: T-SQL's own cast to an integer type always truncates toward zero (`CAST(2.9 AS INT)` = `2`), while PostgreSQL, Oracle, and MySQL's `SIGNED` cast all round half-away-from-zero (`CAST(2.9 AS INT)` would be `3` on those). |

#### [Booleans: the value/predicate duality](booleans/README.md)

| Article | Description |
|---|---|
| [`IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`](booleans/is-distinct-from.md) | PostgreSQL's `IS [NOT] DISTINCT FROM` is a null-safe equality: unlike `=`, it never itself evaluates to `UNKNOWN` — `NULL IS NOT DISTINCT FROM NULL` is `TRUE`, `1 IS DISTINCT FROM NULL` is `TRUE`. |
| [Boolean-to-text/char rendering (PostgreSQL `::text` / MySQL `CAST(... AS CHAR)`)](booleans/boolean-to-text-rendering.md) | PostgreSQL renders a boolean cast to text as the words `'true'`/`'false'`; MySQL has no boolean text representation at all — its booleans are ordinary integers, so casting one to a character type gives `'1'`/`'0'` instead. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`PIVOT` (T-SQL / Oracle) → PostgreSQL / MySQL](dml/pivot.md) | `PIVOT (agg(arg) FOR col IN (v1, v2))` rotates rows into columns for a small, explicit set of pivot values, aggregating `arg` per value. |
| [`UNPIVOT` (T-SQL / Oracle) → all targets](dml/unpivot.md) | `UNPIVOT (val FOR col IN (a, b))` turns columns `a`, `b` into row pairs `(col, val)` — `col` carrying the *name* of the source column, `val` its value. |
| [A leading CTE feeding `MERGE` (T-SQL) → Oracle / MySQL](dml/merge-with-leading-cte.md) | `WITH src AS (…) MERGE INTO t USING src ON … WHEN MATCHED THEN UPDATE … WHEN NOT MATCHED THEN INSERT …` — the `MERGE`'s `USING` source is itself a named CTE. |
| [`DELETE TOP (n)` row caps (T-SQL) → MySQL / Oracle / PostgreSQL](dml/delete-top-n-row-cap.md) | `DELETE TOP (n) FROM t WHERE …` caps the delete to `n` **arbitrary** matching rows (T-SQL gives no ordering guarantee for `TOP` without an `ORDER BY`, which `DELETE` cannot carry). |
| [Multi-join `UPDATE … FROM … JOIN … JOIN …` (T-SQL / PostgreSQL) → Oracle / MySQL / PostgreSQL](dml/multi-join-update-from.md) | `UPDATE t SET t.total = d.amount + c.fee FROM t JOIN detail d ON … JOIN charges c ON … WHERE …` drives the assignment and the row filter off two or more joined tables the `UPDATE` itself never lists as its target — the sibling mechanism to this page's multi-table `DELETE` above, but for `UPDATE`. |
| [Trailing `ORDER BY` on `UNION`/`EXCEPT`/`INTERSECT` (T-SQL) → PostgreSQL / Oracle / MySQL](dml/set-op-trailing-order-by.md) | `SELECT … EXCEPT SELECT … ORDER BY a` orders the **combined** result of the whole set operation. |
| [`FROM DUAL` synthesis and removal (bidirectional)](dml/from-dual.md) | Oracle has no table-less `SELECT` — `SELECT 1` is `ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's answer is `DUAL`, a one-row system table. |
| [`FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)](dml/from-values-to-union-all.md) | PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source, usable directly as a `FROM` item, as the operand of a quantified comparison (`n > ALL (VALUES …)`), or with a column-aliased `v(x)`. |
| [`FROM generate_series(…)` (PostgreSQL) → a synthesized numbers source (every target)](dml/from-generate-series.md) | PostgreSQL's `generate_series(start, stop[, step])` is a set-returning function usable directly as a `FROM` item (or, via an implicit lateral unnest, in the `SELECT` list) — a compact way to manufacture one row per integer (or per date, with an `INTERVAL` step) in a range. |
| [Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint](dml/recursive-cte-keyword-and-column-list.md) | A recursive CTE — one whose body queries its own name — needs different declaration syntax on every engine. |
| [T-SQL bare money literal (`$12.50`) → the numeric literal it means](dml/money-literal-shorthand.md) | T-SQL accepts a bare currency-prefixed literal like `$12.50` or `$100` as a numeric constant, but the underlying parser mis-reads it as a `table.column` reference instead — `$12.50` becomes `Column(this=Literal(50), table=Identifier($12))`, a nonsense "column `50` of table `$12`" — because the digits after the dot look like a member access, not a decimal point. |
| [Canonical `MERGE` (T-SQL/Oracle) → MySQL `INSERT … SELECT … ON DUPLICATE KEY UPDATE`](dml/merge-to-mysql-on-duplicate-key.md) | MySQL has no `MERGE` statement at all. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL](ddl/tsql-identity-scope-reads.md) | T-SQL exposes the last-generated identity value through three functions with different scoping rules (current scope / current session / a named table). |
| [T-SQL index `WITH (FILLFACTOR = n)` → Oracle / MySQL](ddl/tsql-index-fillfactor.md) | `FILLFACTOR` reserves free space per index page for future inserts — a physical storage tuning knob with no logical effect on query results. |
| [PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL](ddl/truncate-restart-identity-cascade.md) | PostgreSQL's `TRUNCATE` defaults to *keeping* an identity column's next value where it was (`CONTINUE IDENTITY` is implicit), and only resets it when you say `RESTART IDENTITY` explicitly; the same statement's `CASCADE` also truncates every table with a foreign key pointing at the truncated one. |
| [T-SQL `CREATE TYPE x FROM base` alias type → resolved to its base type everywhere](ddl/create-type-alias-harvested.md) | T-SQL lets a script define a named alias type (`CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL`) and then use `[dbo].[Name]` as an ordinary column type elsewhere in the same script. |
| [Oracle `ALTER TABLE ... ADD ( ... )` (parenthesized element list) → an unwrapped `ADD` clause](ddl/oracle-alter-add-parenthesized-unwrap.md) | Oracle allows one or more table elements (columns, constraints) to be added in a single parenthesized list — `ALTER TABLE t ADD (CONSTRAINT fk FOREIGN KEY (col) REFERENCES p(id))`. |
| [T-SQL system-catalog DDL guards (`OBJECT_ID`/`sys.objects`/`sys.columns`) → native `IF [NOT] EXISTS` or a synthesized per-target probe](ddl/tsql-existence-guard-catalog-probes.md) | A T-SQL migration script often guards a `CREATE`/`DROP`/`ALTER` with a system-catalog existence check — `IF OBJECT_ID('t') IS NOT NULL DROP TABLE t` or `IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID('t')) BEGIN CREATE TABLE t (...) END` — so a second run of the same script doesn't fail on an object that's already there (or already gone). |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [`EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/exec-sp-degrade-policy.md) | T-SQL system procedures (`sp_rename`, `sp_who`, …) call into SQL Server's own catalog/admin machinery. |
| [Statement-after-`EXEC` survival fix](procedural/statement-after-exec-survival.md) | A degraded system-proc `EXEC`, followed by another statement on the same line separated only by `;` (not a batch-separating `GO`): `EXEC sp_rename 't.a','b','COLUMN'; UPDATE t SET b = 1;`. |
| [`SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL](procedural/set-identity-insert-degrade.md) | T-SQL requires `IDENTITY_INSERT` to be explicitly turned `ON` before a script can supply its own value for an identity column, then turned back `OFF`. |
| [`SET SERVEROUTPUT ON` and similar client directives (Oracle) → PostgreSQL / T-SQL / MySQL](procedural/sqlplus-client-directives.md) | SQL*Plus `SET` directives (`SET SERVEROUTPUT ON`, etc.) are **line-oriented client-tool commands**, not SQL statements — they carry no trailing `;` and configure the SQL*Plus session, not the database. |
| [Oracle `%TYPE`/`%ROWTYPE` column-type references → PostgreSQL / T-SQL / MySQL](procedural/oracle-type-rowtype-references.md) | `v_id employees.id%TYPE` declares a variable with **whatever type** the referenced column currently has — a live binding to the schema, not a fixed type name. |
| [Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL](procedural/oracle-cursor-attributes.md) | Oracle attaches state to each named cursor: `c%FOUND`/`c%NOTFOUND` (did the last `FETCH` return a row), `c%ISOPEN`, and `c%ROWCOUNT` (rows fetched so far on that cursor). |
| [PL/pgSQL implicit `FOUND` / Oracle implicit `SQL%FOUND` → T-SQL `@@ROWCOUNT` / MySQL `ROW_COUNT()`](procedural/implicit-found-flag.md) | PL/pgSQL keeps one implicit boolean, `FOUND`, updated by the *last* `SELECT INTO`, `UPDATE`, `DELETE`, `INSERT`, or `FETCH` in the routine — it answers "did that last statement affect/return a row?" for the routine as a whole, not for one named cursor. |
| [`RETURNS void` (PostgreSQL) → neutral scalar return type + synthesized `RETURN` (MySQL / T-SQL / Oracle)](procedural/returns-void-signature-synthesis.md) | A PostgreSQL function declared `RETURNS void` returns nothing — per the corpus's own count, the single most common plpgsql function shape (62 occurrences), typically a side-effecting helper invoked for its `INSERT`/`UPDATE`, never for a value. |
| [Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL](procedural/scroll-cursor-fetch.md) | A T-SQL `SCROLL` cursor supports non-forward fetches: `FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc. |
| [Row-level trigger re-reading its own table (MySQL/PostgreSQL) ↔ Oracle `COMPOUND TRIGGER`](procedural/trigger-reading-own-table.md) | A row-level trigger that aggregates a parent row from its children (`UPDATE invoice SET total = (SELECT SUM(...) FROM invoice_line WHERE invoice_id = NEW.invoice_id) WHERE id = NEW.invoice_id`) re-reads the table it's attached to. |
| [T-SQL cursor-variable binding (`SET @cur = CURSOR ... FOR q; OPEN @cur;`) → PostgreSQL / Oracle / MySQL](procedural/tsql-cursor-variable-binding.md) | T-SQL lets a cursor be bound to a *variable* in two steps: a bare `DECLARE @cur CURSOR;` (no query yet), then `SET @cur = CURSOR ... FOR <query>` to attach the query, then a bare `OPEN @cur;`. |
| [PL/SQL cursor `FOR` loop (Oracle) → MySQL explicit cursor scaffold](procedural/cursor-for-loop-to-mysql.md) | The same implicit fetch-and-bind PL/SQL construct as above, but onto MySQL, whose procedural dialect additionally requires every `DECLARE` to sit at the very top of its enclosing `BEGIN` block (MySQL error 1337) and has no `WHILE @@FETCH_STATUS` equivalent — loop termination is driven by a `CONTINUE HANDLER FOR NOT FOUND`. |
| [Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter](procedural/numeric-range-for-loop.md) | `FOR i IN 1..13 LOOP` (optionally `REVERSE`) is Oracle's counting loop — no cursor at all, just an integer range. |
| [T-SQL loop control (`BREAK`/`CONTINUE`, compound assignment) → MySQL labeled `LEAVE`/`ITERATE`](procedural/tsql-loop-control-to-mysql-labels.md) | T-SQL's `BREAK`/`CONTINUE` act on the *nearest enclosing* loop with no name required. |
| [T-SQL `@@FETCH_STATUS` → Oracle / PostgreSQL / MySQL](procedural/tsql-fetch-status-to-oracle-postgresql-mysql.md) | T-SQL exposes cursor state through a single global variable, `@@FETCH_STATUS`, checked right after a `FETCH` (`0` = a row was returned, `-1` = no more rows, `-2` = the fetched row is missing). |
| [T-SQL's `CAST(N'' AS XML).value('xs:base64Binary(...)', ...)` base64-decode idiom → each target's native call](procedural/base64-xml-idiom-per-target.md) | T-SQL has no direct `BASE64_DECODE` function; the idiomatic way to decode a base64 string into binary is to route it through the XML type system — `CAST(N'' AS XML).value('xs:base64Binary(sql:variable("@x"))', 'VARBINARY(MAX)')`. |
| [T-SQL `ERROR_MESSAGE()` (inside a `CATCH` block) → each target's own error-text accessor](procedural/error-message-function-per-target.md) | Inside a T-SQL `CATCH` block, `ERROR_MESSAGE()` reads the text of the error that was just caught. |
| [A `DECLARE` written mid-block (inside an `IF`/`CATCH`) → hoisted to the routine's top declaration section](procedural/mid-block-declare-hoist.md) | T-SQL allows `DECLARE @v type = init;` anywhere a statement is legal — inside an `IF` body, inside a `CATCH` block, nested arbitrarily deep. |
| [`SELECT ... INTO :NEW.col1, :NEW.col2` (Oracle trigger) → PostgreSQL `NEW.col`, MySQL session variables](procedural/pseudo-row-into-mysql-session-vars.md) | An Oracle row-level trigger can `SELECT ... INTO :NEW.col1, :NEW.col2` directly — assigning query results straight into the pseudo-row's columns. |
| [A package-qualified ref-cursor type (`pkg.my_cursor`) → the target's own ref-cursor type](procedural/refcursor-package-type-and-inout-mode.md) | An Oracle procedure parameter can be typed with a package-defined `REF CURSOR` subtype (`v_cur OUT pkg_ret.my_cursor`) — `pkg_ret.my_cursor` is only meaningful *inside that package*, never on a target with no package concept at all. |
| [T-SQL `THROW`/`RAISERROR`'s numeric error code → each target's own error-code slot](procedural/throw-raiserror-numeric-code-per-target.md) | T-SQL's `THROW 50001, 'not found', 1` and `RAISERROR('not found', 16, 1)` (with a matching custom message id registered separately) both carry a *numeric error code* alongside the message text. |
| [Oracle `DBMS_LOB`/`UTL_RAW`/`TO_NUMBER`/`TRUNC` helper calls → T-SQL/MySQL built-ins](procedural/oracle-lob-numeric-helpers-to-tsql.md) | Several of Oracle's package-qualified LOB helpers and its bare numeric/date built-ins have no shared name on other engines, and one (`DBMS_LOB.SUBSTR`) even reorders its arguments compared to the target's equivalent. |
| [T-SQL `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)` → MySQL's native hash function directly](procedural/convert-hashbytes-wrapper-collapse.md) | T-SQL has no built-in "digest as a hex string" function — `HASHBYTES(...)` returns raw bytes, so the idiomatic way to get a readable hex digest is to wrap it in `CONVERT(NVARCHAR(MAX), HASHBYTES(...), 2)`, where style `2` is `CONVERT`'s binary-to-hex-string style code. |
| [`EXECUTE IMMEDIATE '...' USING v1, v2` (Oracle) → MySQL `EXECUTE ... USING @v1, @v2`, bound through session variables](procedural/mysql-execute-using-session-vars.md) | Oracle's `EXECUTE IMMEDIATE '<sql>' USING bind1, bind2` accepts routine locals and parameters directly as bind arguments. |

### Cross-engine / multi-directional

| [Date/time](#datetime-arithmetic-and-formatting-8) | [Strings](#strings-concatenation-and-collation-8) | [Aggregates & windows](#aggregates-and-window-functions-8) | [DML](#dml-pivotunpivot-merge-delete-row-values-8) | [DDL](#ddl-identity-temp-tables-foreign-keys-sequences-storage-options-8) | [Procedural](#procedural-cursors-dynamic-sql-system-procedures-session-directives-8) |
|---|---|---|---|---|---|

#### [Date/time arithmetic and formatting](datetime/README.md)

| Article | Description |
|---|---|
| [Temporal +/− arithmetic: date ± int, MySQL numeric coercion, timestamp − timestamp](datetime/temporal-plus-minus-arithmetic.md) | PostgreSQL/Oracle `date_col + n` / `date_col - n` is day arithmetic; T-SQL `datetime_col + n` likewise adds days. |
| [DATEDIFF/DATEPART unit maps: the QUARTER crash and WEEKDAY per-target forms](datetime/datediff-datepart-unit-maps.md) | T-SQL `DATEDIFF(QUARTER, d1, d2)` and `DATEDIFF(WEEK, d1, d2)` are valid, translatable unit spellings; `DATEPART(WEEKDAY, d)` returns the day-of-week under the session's `@@DATEFIRST` setting (default: Sunday = 1). |
| [`EXTRACT(field FROM x)` ↔ T-SQL `DATEPART(field, x)` for the standard fields](datetime/extract-datepart-standard-fields.md) | Oracle, PostgreSQL and MySQL spell a date-field extraction as `EXTRACT(field FROM x)` (a special two-token syntax, not an ordinary function call); T-SQL has no `EXTRACT` at all and instead uses `DATEPART(field, x)` — an ordinary comma-separated function call. |

#### [Strings, concatenation and collation](strings-collation/README.md)

| Article | Description |
|---|---|
| [CONCAT / `\|\|` NULL-propagation per engine](strings-collation/concat-null-propagation.md) | MySQL's `CONCAT(a, b, …)` **propagates** `NULL`: any `NULL` argument makes the whole result `NULL`. |
| [`GREATEST`/`LEAST` NULL-propagation per engine](strings-collation/greatest-least-null-propagation.md) | MySQL and Oracle's `GREATEST`/`LEAST` return `NULL` if *any* argument is `NULL`. |
| [`REPLACE` and `NULL`: Oracle's 2-arg form vs MySQL's propagation](strings-collation/replace-and-null.md) | Two independent `REPLACE`/`NULL` divergences. |
| [LIKE … ESCAPE mapping](strings-collation/like-escape-mapping.md) | `LIKE pattern ESCAPE 'c'` is SQL-standard: `c` escapes a following `%`/`_` so it matches literally. |
| [T-SQL LIKE character classes (`'[A-C]%'`) → SIMILAR TO / REGEXP / REGEXP_LIKE](strings-collation/tsql-like-character-classes.md) | T-SQL's `LIKE` supports bracketed **character classes**: `'[A-C]%'` matches any string starting with `A`, `B` or `C`. |
| [Negative/zero REPEAT/REPLICATE clamps](strings-collation/repeat-replicate-clamps.md) | PostgreSQL `repeat(s, n)` and MySQL `REPEAT(s, n)` with `n <= 0` return an empty string `''`. |
| [SUBSTRING negative/zero start semantics per engine](strings-collation/substring-negative-start.md) | T-SQL and PostgreSQL `SUBSTRING(s, start, len)` treat a `start < 1` as counting *backwards from the length*: out-of-range leading positions still consume `len`, they just don't emit characters for them. |
| [Character-set `TRIM(chars FROM string)` → Oracle](strings-collation/trim-chars-from-string-to-oracle.md) | `TRIM([BOTH\|LEADING\|TRAILING] chars FROM string)` strips every occurrence of any character in `chars` from the string (both ends by default). |
| [DATALENGTH byte-vs-char lengths (UTF-16 caveat)](strings-collation/datalength-byte-vs-char.md) | T-SQL `DATALENGTH(x)` returns the storage **byte** length of `x`, not its character count. |
| [SOUNDEX as the canonical unmapped-builtin gate example](strings-collation/soundex-unmapped-builtin-gate.md) | Oracle and T-SQL's `SOUNDEX(s)` is a native phonetic built-in. |
| [Collation and ordering divergences — documented limits](strings-collation/collation-and-ordering-limits.md) | String equality, `ORDER BY`, `DISTINCT`, `GROUP BY` and `LIKE` all compare under the source engine's **default collation** — case sensitivity, accent sensitivity, and trailing-space handling are properties of that collation, not of the SQL text. |
| [Case-sensitivity compensation on string-literal operands (cross-engine)](strings-collation/literal-collation-compensation.md) | PostgreSQL and Oracle's default collations compare strings **case-sensitively**; MySQL's and T-SQL's default collations compare **case-insensitively**. |
| [String-function positional-argument edge cases: negative `LEFT`, T-SQL `LEN` trailing spaces, MySQL fractional rounding](strings-collation/string-function-argument-edge-cases.md) | `LEFT`/`SUBSTRING`/`REPEAT`'s position and length arguments, and T-SQL `LEN`, each have one engine-specific edge-case rule that a literal translation would silently drop: PostgreSQL's `LEFT(s, -n)` means something different from a plain clamp, T-SQL's `LEN` counts differently from every other engine's length function, and MySQL rounds a fractional numeric argument where the other engines truncate it. |
| [Numeric-operand `\|\|`/`CONCAT` casting (Oracle/MySQL → T-SQL, → PostgreSQL)](strings-collation/numeric-operand-concatenation-casting.md) | Oracle's `\|\|` and MySQL's `CONCAT` implicitly stringify a numeric operand: `2 \|\| 3` is the two-character string `'23'`. |
| [Bitwise/arithmetic operator-precedence parentheses (MySQL/Oracle ↔ PostgreSQL/T-SQL)](strings-collation/bitwise-arithmetic-precedence-parens.md) | `&`, `\|` and `<<`/`>>` bind **looser** than `+`/`*` on MySQL and Oracle, but **tighter** than `+`/`*` on PostgreSQL and T-SQL. |

#### [Aggregates and window functions](aggregates-windows/README.md)

| Article | Description |
|---|---|
| [Integer-truncating vs. decimal division (cross-engine)](aggregates-windows/integer-vs-decimal-division.md) | `/` truncates two integer operands to an integer on PostgreSQL and T-SQL (`5 / 2` is `2`), but MySQL and Oracle always return a decimal (`5 / 2` is `2.5`) — crossing that line without compensation silently changes the value. |
| [Math functions with no shared spelling: `LOG` argument order, `COT`, `PI()`, `TRUNC(x, n)`](aggregates-windows/math-function-per-engine-spelling.md) | Several ordinary scalar math functions differ across engines in ways a rename table alone can't bridge — an argument order flip, a missing function entirely, or a same-name function with different rounding behavior. |

#### [DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](dml/README.md)

| Article | Description |
|---|---|
| [`ORDER BY` inside a joined derived table (any source) → T-SQL: kept only with a row cap](dml/derived-table-order-by-to-tsql.md) | A derived table used as a join operand can carry its own `ORDER BY` — e.g. to pick or arrange the rows it contributes — separately from any `ORDER BY` on the outer query. |
| [Oracle `(+)` outer-join mark → explicit `LEFT JOIN … ON`; comma joins → `CROSS JOIN`](dml/oracle-outer-join-mark.md) | Oracle's legacy join syntax has no `JOIN` keyword at all: tables are comma-listed in `FROM`, and `col(+)` on one side of a `WHERE` predicate marks that table as the *optional* (outer) side of the join — the row is still produced, NULL-extended, when no match exists. |
| [`ROWNUM <= n` (Oracle) → `LIMIT` / `TOP` / `FETCH FIRST`](dml/oracle-rownum-row-cap.md) | Oracle's `ROWNUM` is a pseudo-column numbering rows as they are produced; `WHERE ROWNUM <= n` is Oracle's idiom for capping a result to `n` rows — with no ordering guarantee unless paired with an `ORDER BY` (the `ROWNUM` filter applies before any sort). |
| [Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded](dml/parenthesized-set-op-arms.md) | `(SELECT …) UNION ALL (SELECT …)` parenthesizes each arm of a set operation — often just for readability, but sometimes because one arm carries its own `ORDER BY`/`LIMIT` that must apply to *that arm alone*, not to the combined result. |
| [Parenthesized join-relation groups unwrap; a column-aliased table ref wraps into a derived table](dml/parenthesized-join-groups.md) | Two different `FROM`-clause shapes both need restructuring, for opposite reasons: a **parenthesized join group** — `FROM (t1 JOIN t2 ON …), t3` — groups a join tree for readability with no semantic effect of its own; a **column-aliased table reference** — PostgreSQL's `tbl AS alias(col1, col2)` — renames the table's columns positionally, a real semantic operation most targets cannot spell against a plain table reference at all. |
| [`INTERSECT ALL` / `EXCEPT ALL` → Oracle / T-SQL](dml/intersect-except-all.md) | `INTERSECT ALL` and `EXCEPT ALL` compare rows the same way as the plain `INTERSECT`/`EXCEPT`, but **keep duplicates**: `INTERSECT ALL` returns `min(count in left, count in right)` copies of each matching row, and `EXCEPT ALL` returns `max(count in left − count in right, 0)` copies. |

#### [DDL: identity, temp tables, foreign keys, sequences, storage options](ddl/README.md)

| Article | Description |
|---|---|
| [Auto-incrementing key columns (PostgreSQL `SERIAL` / T-SQL `IDENTITY` / Oracle `GENERATED … AS IDENTITY` / MySQL `AUTO_INCREMENT`)](ddl/auto-incrementing-keys.md) | Each engine spells "the database assigns this column's value from an internal counter" differently: PostgreSQL `SERIAL`/`BIGSERIAL` (sugar for an integer + an owned sequence + a default), T-SQL `IDENTITY(seed, step)`, Oracle `GENERATED ALWAYS\|BY DEFAULT AS IDENTITY [(START WITH s INCREMENT BY i …)]`, MySQL `AUTO_INCREMENT` (a single table-level counter, no per-column seed/step). |
| [Oracle bare `NUMBER` (no precision/scale) → role-aware numeric](ddl/oracle-bare-number-role-aware.md) | Oracle's unqualified `NUMBER` — no precision or scale — is overloaded. |
| [`CREATE TABLE AS SELECT` ↔ `SELECT ... INTO` for ordinary (non-temporary) tables](ddl/ctas-vs-select-into.md) | This extends the entry above from *temp* tables specifically to *any* table: T-SQL has no `CREATE TABLE ... AS SELECT` syntax at all — whether or not the table is session-scoped — so any CTAS from another source dialect must become a T-SQL `SELECT ... INTO`. |
| [Unnamed derived-table / `SELECT ... INTO` projections → synthesized `uq_col1` (T-SQL)](ddl/unnamed-projection-synthesized-name.md) | `SELECT (SELECT a) t` or `SELECT (SELECT 1) t` — a derived table whose single projected column is a bare parameter reference or a literal, with no alias — is legal on PostgreSQL/MySQL/Oracle (the column gets an engine-assigned display name that nothing else references). |
| [`GENERATED ALWAYS AS (expr)` computed columns (cross-engine)](ddl/computed-columns-generated-always.md) | A computed (generated) column derives its value from an expression over other columns in the same row, recalculated automatically on every read or write — a fundamentally different thing from an auto-incrementing identity column, even though MySQL spells the two very differently and PostgreSQL's `GENERATED ALWAYS AS (...)` clause is shared syntax for both. |
| [Inline DDL attributes decomposed into standalone statements: MySQL `COMMENT`, T-SQL inline `INDEX`](ddl/inline-attribute-to-standalone-statement.md) | MySQL lets a column or table carry a `COMMENT '...'` right inside its `CREATE TABLE`, and T-SQL lets a table element declare an `INDEX` inline alongside its columns. |
| [An inline column-level `REFERENCES`/`CHECK` constraint → a table-level constraint clause](ddl/inline-fk-check-relocated-table-level.md) | `c INT REFERENCES p(id) ON DELETE CASCADE` and `c INT CHECK (c > 0)` declare a foreign key or check constraint directly on the column, inline inside its own definition — every engine accepts this shorthand. |

#### [Procedural: cursors, dynamic SQL, system procedures, session directives](procedural/README.md)

| Article | Description |
|---|---|
| [A constant dynamic-SQL string (T-SQL `EXEC sp_executesql` / Oracle `EXECUTE IMMEDIATE` / PL/pgSQL `EXECUTE`) → any target](procedural/constant-dynamic-sql-string.md) | Dynamic SQL executes a string built at runtime. |
| [Row-level trigger body (`SET NEW.col = expr`) → T-SQL statement-level `UPDATE ... WHERE ... IN (SELECT ... FROM inserted)`](procedural/row-level-trigger-body-to-tsql.md) | A MySQL/PL-SQL row-level trigger (`FOR EACH ROW`) runs once per affected row, with `NEW`/`OLD` bound to that single row. |
| [Oracle event predicates (`INSERTING`/`DELETING`/`UPDATING('col')`) → per-engine rewrite](procedural/oracle-trigger-event-predicates.md) | An Oracle trigger body asks, inline, "did this statement INSERT/DELETE/UPDATE, and did this specific column change" via `INSERTING`/`DELETING`/`UPDATING('col')`. |
| [PL/pgSQL trigger context variables (`TG_NAME`/`TG_TABLE_NAME`/`TG_OP`/`TG_WHEN`/`TG_LEVEL`, `TG_ARGV`/`TG_NARGS`) → compile-time constants once the function inlines](procedural/plpgsql-trigger-context-variables.md) | Inside a plpgsql trigger function, `TG_NAME`/`TG_TABLE_NAME`/ `TG_OP`/`TG_WHEN`/`TG_LEVEL` are implicit variables PostgreSQL's trigger machinery populates at fire time, and `TG_ARGV[n]`/`TG_NARGS` read the argument list supplied by the specific `CREATE TRIGGER ... EXECUTE FUNCTION fn(arg1, arg2, ...)` that invoked it. |
| [PG named transition tables (`REFERENCING ... TABLE AS alias`) → T-SQL `inserted`/`deleted` alias rename](procedural/pg-named-transition-tables.md) | A PostgreSQL statement trigger can name its transition tables (`REFERENCING NEW TABLE AS newtab`), and the inlined function body reads rows through that chosen alias. |
| [Trigger body → PostgreSQL `CREATE FUNCTION ... RETURNS TRIGGER` + `CREATE TRIGGER`](procedural/trigger-body-to-pg-function.md) | PostgreSQL has no inline trigger body: `CREATE TRIGGER` only *names* a function, which must already exist and return `TRIGGER`. |
| [Bare `RETURN;` inside a PostgreSQL trigger function's nested handler → `RETURN NEW;`](procedural/pg-trigger-bare-return.md) | Oracle's bare `RETURN;` inside an exception handler simply leaves the trigger (there is no return value to supply there). |
| [Empty trigger body → synthesized `SET NOCOUNT ON;` no-op (T-SQL)](procedural/empty-trigger-body-noop.md) | T-SQL forbids an empty statement block: `BEGIN END` alone after a trigger header is a syntax error. |
| [Bare `RETURN` in a MySQL procedure → labeled `proc_exit:` block + `LEAVE`](procedural/mysql-bare-return-to-leave.md) | MySQL forbids `RETURN` anywhere inside a `PROCEDURE` body ("RETURN is only allowed in a FUNCTION") — but an early-exit bare `RETURN` (no value) is ordinary control flow in T-SQL/Oracle/PostgreSQL procedures. |
| [An unqualified scalar function call → `dbo.`-qualified on T-SQL](procedural/tsql-udf-auto-qualification.md) | T-SQL requires a user-defined scalar function call to be schema-qualified (`dbo.fn(...)`); an unqualified call is error 195, "not a recognized built-in function name," even when a function of that name exists in the target database. |
| [A T-SQL procedure body gains a synthesized `SET NOCOUNT ON;` by default](procedural/nocount-injected-default.md) | SQL Server's documented best practice for every stored procedure is `SET NOCOUNT ON` — it suppresses the "N row(s) affected" message that would otherwise ride along on every DML statement, cluttering client output and, over a network round trip, costing real time. |

## Entry format (keep it — the pages are grep-able by construct)

Each article is a cookbook recipe — problem, solution, discussion, see also:

```markdown
# <construct> (<source engine>) → <target(s)>

**Problem.** What the construct does, and what you expect from it when
migrating it, in one or two sentences (second person, direct).
**Solution.** A real input/output example copied from the corpus case,
*first*, then one sentence on the output shape Unique emits.
**Discussion.** The target-engine-level reason a direct mapping does not
exist (missing value type, different clamping rule, parser limitation…), not
"unsupported" — followed by the divergence as a blockquote callout:
`> **Warning** …` (the exact divergence and the warning text the user will
see), or `> **Note** faithful — …` (same result set, with the proof cited).
**See Also.** Corpus case id(s) · 03-unsupported § (if a limit) · a link to
[warnings.md](reference/warnings.md) when the entry names a diagnostic code.
```

Each article page opens with a breadcrumb nav line and a machine-readable
`<!-- rationale: topic=… type="…" direction="…" -->` metadata comment that the
index generator (`scripts/generate_rationale_index.py`) reads to build the
per-topic and by-engine tables above. Do not hand-edit the topic `README.md`
or this master index — they are generated; a CI freshness gate
(`python scripts/generate_rationale_index.py --check`) fails the build if they
drift, and its link checker fails if any relative link goes stale.

Rules for contributors (human or agent): every claim must be traceable to a
corpus case, an emitter docstring, or a `docs/03-unsupported.md` section —
cite it; examples are copied from corpus cases verbatim (they are
live-verified; an invented example is a liability); `faithful` may only be
claimed where a corpus assertion or the nightly live result-diff proves it.

**Write for the user — the transpiler is a black box (maintainer rule,
2026-07-31).** An article explains how a construct translates between
engines and why: a direct equivalence is stated and done; an inexact one
explains exactly what diverges and why; a construct with no direct
equivalent explains the creative alternative used and why it is needed.
What does NOT belong in the prose: project history (that a conversion was
once wrong, audits, campaign/finding ids, "before/after the fix"), internal
pipeline detail (IR, parser/emitter/converter internals, library names), or
the reason an entry exists — the entry must read the same as if the
behavior had always been correct. Traceability stays in **See Also** (test/
corpus citations), never as narrative.

## Reference (generated)

These hand-curated pages link out to `docs/reference/` instead of duplicating
its tables. That directory is machine-generated by
`scripts/generate_reference_docs.py` from `core/mappings.py` and the
challenge corpus — never edited by hand; a CI freshness gate
(`python scripts/generate_reference_docs.py --check`) fails the build if it
drifts from the code.

| Page | Covers |
|---|---|
| [mappings-tsql-oracle.md](../reference/mappings-tsql-oracle.md) · [oracle-tsql.md](../reference/mappings-oracle-tsql.md) | tsql ↔ oracle function/type renames, niladic expressions, gate lists |
| [mappings-tsql-postgresql.md](../reference/mappings-tsql-postgresql.md) · [postgresql-tsql.md](../reference/mappings-postgresql-tsql.md) | tsql ↔ postgresql, same shape |
| [mappings-tsql-mysql.md](../reference/mappings-tsql-mysql.md) · [mysql-tsql.md](../reference/mappings-mysql-tsql.md) | tsql ↔ mysql, same shape |
| [mappings-oracle-postgresql.md](../reference/mappings-oracle-postgresql.md) · [postgresql-oracle.md](../reference/mappings-postgresql-oracle.md) | oracle ↔ postgresql, same shape |
| [mappings-oracle-mysql.md](../reference/mappings-oracle-mysql.md) · [mysql-oracle.md](../reference/mappings-mysql-oracle.md) | oracle ↔ mysql, same shape |
| [mappings-postgresql-mysql.md](../reference/mappings-postgresql-mysql.md) · [mysql-postgresql.md](../reference/mappings-mysql-postgresql.md) | postgresql ↔ mysql, same shape |
| [limits.md](../reference/limits.md) | the `[limit]` degradation catalog — one row per corpus case (id, source engine, class, description, `03-unsupported.md` citation) |
| [coverage.md](../reference/coverage.md) | challenge-corpus case counts per source engine and finding class |
| [warnings.md](../reference/warnings.md) | the `UNIQUE-NNNN` diagnostic catalog — a Problem/Solution/Discussion/See Also recipe per code that has a structured rationale entry; codes without one yet stay in a compact table marked `(rationale pending)` |
