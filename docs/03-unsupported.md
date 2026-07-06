# Unique — Unsupported Features & Limitations

This document lists SQL features that are explicitly **out of scope** for
transpilation, along with the reasoning.

---

## 0. SQLite is import-only

**SQLite cannot be a transpilation target.** It has no procedural language (no
stored procedures, functions or anonymous PL/SQL-style blocks), so a faithful
target mapping is impossible; the tool raises a clear `UnsupportedFeatureError`
when `sqlite` is requested as a target, and the web UI hides it from the target
list. SQLite **is** supported as a **source** (SQLite → the four server
engines): its DML/DDL — type affinity, `AUTOINCREMENT`, `INTEGER PRIMARY KEY`
rowid aliases — is read via sqlglot and converted like any other source.

---

## 0b. Indexing an unbounded TEXT/BLOB column (intrinsic)

PostgreSQL and SQLite let you put a `TEXT`/`BLOB` (unbounded) column in an index
or UNIQUE constraint. **MySQL, SQL Server and Oracle cannot index an unbounded
binary/text column** — MySQL/SQL Server require a bounded type or a prefix
length, Oracle cannot index a LOB. This is a source-schema ↔ target-engine
mismatch, not a transpiler bug: the column type carries no length, so no correct
bounded form can be inferred. (MediaWiki itself sidesteps this by declaring these
columns `VARBINARY(255)` in its MySQL schema and `TEXT`/`BLOB` in its PostgreSQL/
SQLite schemas.) Transpile such a schema to MySQL/SQL Server/Oracle and the
engine rejects the index; bound the column type in the source, or add a
prefix/hash index by hand.

---

## 1. Fully Unsupported (❌)

These features will **never** be transpiled. They are silently dropped or
emitted as comments in the output.

### 1.1 GOTO Statements

**Engines:** T-SQL, Oracle (PL/SQL)

**Reason:** GOTO has no equivalent in PostgreSQL or MySQL. Restructuring
arbitrary GOTO logic into structured control flow is an undecidable problem
in the general case. The transpiler will emit the original code as a comment
with a warning.

### 1.2 Index Hints

**Engines:** T-SQL (`WITH (INDEX(...))`), Oracle (`/*+ INDEX(...) */`), MySQL (`USE INDEX`)

**Reason:** Query optimizer hints are deeply engine-specific and meaningless
when moved to a different engine. The target optimizer has different cost models,
statistics, and index implementations. Hints will be stripped with a warning.

### 1.3 User-Defined Types (UDTs)

**Engines:** T-SQL, Oracle, PostgreSQL

**Reason:** UDT semantics differ fundamentally between engines (CLR types in
SQL Server, object types in Oracle, composite types in PostgreSQL). There is no
meaningful mapping. Scripts that declare or use UDTs will have those sections
emitted as comments.

### 1.4 Array Types

**Engines:** PostgreSQL (`INTEGER[]`), Oracle (`VARRAY`)

**Reason:** MySQL and T-SQL have no native array type. While workarounds exist
(JSON arrays, temporary tables), automatic conversion would change the data
model semantics in unpredictable ways.

### 1.5 Function/Procedure Overloading

**Engines:** Oracle, PostgreSQL

**Reason:** T-SQL and MySQL do not support overloading. Automatic disambiguation
(e.g., renaming overloaded variants) would break calling code and is not safe
to do automatically.

---

## 2. Engine-Specific Features with No Equivalent

These are features that exist in only one engine and have no reasonable
transpilation target:

| Feature | Engine | Why Unsupported |
|---------|--------|-----------------|
| Oracle Packages | Oracle | No equivalent grouping construct in other engines |
| SQL Server CLR Integration | T-SQL | .NET runtime dependency |
| PostgreSQL Extensions (PostGIS, etc.) | PostgreSQL | Engine-specific extensions |
| MySQL-specific storage engines | MySQL | InnoDB/MyISAM are implementation details |
| Oracle Autonomous Transactions | Oracle | No equivalent in other engines |
| SQL Server Service Broker | T-SQL | Messaging subsystem, not SQL |
| Oracle Advanced Queuing | Oracle | Messaging subsystem, not SQL |
| PostgreSQL LISTEN/NOTIFY | PostgreSQL | Pub/sub, not standard SQL |
| T-SQL OPENROWSET / OPENQUERY | T-SQL | Linked server queries |
| Oracle CONNECT BY | Oracle | ⚠️ Partially supported → Recursive CTE |
| T-SQL PIVOT/UNPIVOT | T-SQL | ⚠️ Partially supported → CASE/UNION |

---

## 3. Partially Supported (⚠️) — Known Limitations

### 3.1 Date Format Strings

Format models differ between engines. The transpiler bridges four conventions —
Oracle/PostgreSQL `TO_CHAR`/`TO_DATE`, MySQL `DATE_FORMAT`/`STR_TO_DATE`, T-SQL
`FORMAT` (.NET custom format), and Python-strftime (sqlglot's canonical for a
parsed `FORMAT`/`DATE_FORMAT`) — via this token table (validated live):

| Meaning | Oracle / PostgreSQL | MySQL `DATE_FORMAT` | T-SQL `FORMAT` (.NET) | Python-strftime |
|---------|--------------------|--------------------|-----------------------|-----------------|
| 4-digit year | `YYYY` | `%Y` | `yyyy` | `%Y` |
| 2-digit year | `YY` | `%y` | `yy` | `%y` |
| Month (number) | `MM` | `%m` | `MM` | `%m` |
| Month (name) | `MONTH` | `%M` | `MMMM` | `%B` |
| Month (abbrev) | `MON` | `%b` | `MMM` | `%b` |
| Day of month | `DD` | `%d` | `dd` | `%d` |
| Day (name) | `DAY` | `%W` | `dddd` | `%A` |
| Day (abbrev) | `DY` | `%a` | `ddd` | `%a` |
| Hour (24) | `HH24` | `%H` | `HH` | `%H` |
| Hour (12) | `HH12` / `HH` | `%h` | `hh` | `%I` |
| Minute | `MI` | `%i` | `mm` | `%M` |
| Second | `SS` | `%s` | `ss` | `%S` |
| AM/PM | `AM` / `PM` | `%p` | `tt` | `%p` |

The two subtle traps this handles correctly: the **.NET model is case-sensitive**
(`MM` = month, `mm` = minute; `HH` = 24-hour, `hh` = 12-hour), and **MySQL's `%M`
is a month name while Python/sqlglot's `%M` is the minute** — conflating them
turned `14:30` into `14:June`. Tokens outside this table pass through literally,
so an exotic custom format may still need manual review.

#### Supported function translations

Within procedural bodies, the engine translates these built-in functions
across dialects (name mapping for same-arity equivalents, plus dedicated
handling for the forms below):

- **Current timestamp**: `GETDATE()` ↔ `SYSDATE` ↔ `NOW()`, with the correct
  parenthesization per engine.
- **`DATEADD(part, n, date)`**: → Oracle (`date + n` for days, `ADD_MONTHS`,
  `NUMTODSINTERVAL`), PostgreSQL (`date + INTERVAL 'n unit'`), MySQL
  (`DATE_ADD(date, INTERVAL n unit)`).
- **`DATEDIFF(part, start, end)`**: → Oracle (`end - start`,
  `MONTHS_BETWEEN`), PostgreSQL (`end::date - start::date`), MySQL
  (`DATEDIFF` for days, `TIMESTAMPDIFF` otherwise).
- **String/null functions**: `LEN`/`LENGTH`/`CHAR_LENGTH`,
  `SUBSTRING`/`SUBSTR`, `ISNULL`/`NVL`/`COALESCE`/`IFNULL`, `UPPER`,
  `LOWER`, `REPLACE`, `CEILING`/`CEIL`, and others.

Functions that require argument reordering (e.g. `CHARINDEX`↔`INSTR`↔
`LOCATE`, `DECODE`→`CASE`) are emitted with an inline review comment rather
than a guessed conversion. Unknown date parts or non-standard call shapes are
left intact for manual handling.

### 3.2 Collation & Character Sets

Collation names and behaviors are engine-specific. The transpiler strips
collation specifications with a warning.

### 3.3 Table Partitioning

Partitioning syntax varies dramatically. The transpiler handles basic RANGE
and LIST partitioning but will not attempt HASH partitioning or complex
partition management operations.

### 3.4 Materialized Views

Only Oracle and PostgreSQL support materialized views natively. Transpilation
to T-SQL or MySQL will emit the view definition as a regular view with a
warning that materialization must be handled externally.

### 3.5 Error Handling

Error handling constructs are structurally different:
- T-SQL: `TRY...CATCH`
- Oracle/PostgreSQL: `EXCEPTION` blocks
- MySQL: `DECLARE HANDLER`

The transpiler handles common patterns (catch-all, specific error codes) but
complex exception handling with multiple handlers may lose precision.

### 3.6 MERGE Statement → MySQL

MySQL lacks MERGE. The canonical pattern (one unconditional WHEN MATCHED
UPDATE plus one unconditional WHEN NOT MATCHED INSERT) is rewritten as
`INSERT ... SELECT ... ON DUPLICATE KEY UPDATE`; the rewrite relies on a
UNIQUE or PRIMARY KEY covering the ON-clause columns, which is noted in a
carrier comment and mirrored in `result.warnings`.

More complex MERGEs (conditional WHEN clauses, WHEN MATCHED DELETE, multiple
branches) are preserved as a documented comment and registered in
`result.warnings` / `result.unsupported` — never dropped silently.

### 3.7 OUTPUT / RETURNING Clause → MySQL

MySQL has no equivalent to the OUTPUT (T-SQL) or RETURNING (Oracle/PostgreSQL)
clause. The transpiler will strip it with a warning suggesting the use of
`LAST_INSERT_ID()` or a follow-up SELECT.

### 3.8 Recursive CTEs

While all four engines support recursive CTEs (MySQL 8.0+), there are subtle
differences in recursion depth limits and cycle detection. The transpiler
translates the syntax but does not add engine-specific cycle guards.

### 3.9 JSON Operations

JSON function names and path syntax differ between engines. The transpiler
handles basic `JSON_VALUE` and `JSON_QUERY` equivalents but does not cover
advanced JSON manipulation or PostgreSQL-specific JSONB operators.

### 3.10 Bitwise Operators → Oracle

Oracle has no infix bitwise operators (`|` is string concat, `^`/`&` are
errors). They are now translated via exact integer identities (validated live
against Oracle; correct for non-negative integers):

| T-SQL | Oracle |
|-------|--------|
| `a & b` | `BITAND(a, b)` |
| `a \| b` | `a + b - BITAND(a, b)` |
| `a ^ b` | `a + b - 2 * BITAND(a, b)` |
| `a << b` | `a * POWER(2, b)` |
| `a >> b` | `FLOOR(a / POWER(2, b))` |

On PostgreSQL `^` becomes `#` (its XOR); MySQL keeps the native operators.
(A former converter default silently corrupted these to `=`; long fixed.)

### 3.11 String Concatenation Between Untyped Columns

In T-SQL `+` means concatenation when an operand is a string and addition when
both are numeric. The transpiler rewrites `+` to the target's concatenation
operator (`||`, or `CONCAT()` on MySQL) when an operand is *recognizably* a
string — a literal, a varchar cast, or a string function. But `col1 + col2`
between two columns is **ambiguous without type information**: T-SQL resolves it
by the columns' declared types, which the standalone-DML path does not have (no
`--db-url`). Such an expression is left as `+`. Add a cast
(`CAST(col1 AS VARCHAR) + col2`) or run it through a routine with metadata.

### 3.12 IIF and DATEPART (handled)

`IIF(cond, a, b)` is translated to a searched `CASE WHEN cond THEN a ELSE b END`
for Oracle/PostgreSQL (kept as `IIF`/`IF` where native), and `DATEPART(part, x)`
emits the standard `EXTRACT(part FROM x)` (not the comma form every engine
rejects). Both are validated live. Only date parts outside the common
year/month/day/hour/minute/second set (e.g. `WEEKDAY`, `QUARTER` on Oracle) may
still need review.

---

## 4. Behavioral Differences (Not Bugs)

Some transpiled SQL may produce different results due to inherent engine
differences that cannot be resolved by syntax changes:

| Difference | Details |
|------------|---------|
| NULL sorting | Oracle: NULLs sort last by default. Others: NULLs sort first. |
| String comparison | Some engines are case-sensitive by default, others are not. |
| Division by zero | T-SQL returns NULL. PostgreSQL raises an error. |
| Empty string vs NULL | Oracle treats empty string as NULL. Others do not. |
| Integer division | Some engines truncate, others return decimal. |
| Transaction auto-commit | Default behavior varies. |
| Identifier quoting | `[]` vs `""` vs `` ` ` `` — handled, but original identifiers may conflict with reserved words in the target engine. |

These differences are **documented in warnings** when relevant constructs
are detected.

---

## 5. Future Consideration

Features currently out of scope may become supportable in future versions:

- **CONNECT BY** → Recursive CTE conversion (high demand)
- **PIVOT/UNPIVOT** → CASE/UNION equivalence (moderate complexity)
- **Materialized Views** → Engine-specific DDL (moderate demand)
- **XML operations** → Cross-engine XML function mapping
- **Spatial types** → PostGIS ↔ SQL Server spatial type mapping

---

## 6. Procedural Engine — Known Limitations

The procedural engine parses stored procedures, functions, and triggers
into an IR and re-emits them in the target dialect. Some constructs are
only partially supported:

- **Semicolon-less T-SQL statements**: T-SQL allows statements without a
  trailing semicolon, separated only by newlines. The parser detects
  statement boundaries (control-flow keywords and standalone `SET @var`
  assignments) so these bodies parse correctly. Chained DML such as
  `INSERT ... SELECT` and `UPDATE ... SET` is kept intact. Rare edge cases
  with unusual formatting may still need review.
- **`DECLARE @t TABLE (...)`** (table variables): on **Oracle**, hoisted to a
  schema-level **Global Temporary Table** emitted before the routine (a CREATE
  cannot live in a PL/SQL block, and the block references it statically), with a
  per-routine-unique name and renamed references; an accompanying `INSERT … OUTPUT
  … INTO @t` is a documented carrier (Oracle `RETURNING` cannot target a table, so
  the GTT is populated manually). **PostgreSQL/MySQL** have no direct equivalent —
  the column list is captured verbatim (use a collection type or temporary table).
- **`SELECT ... INTO @var`** combined with `OUTPUT ... INTO`: the `OUTPUT`
  clause is engine-specific and emitted as raw SQL.
- **Variable-assignment `SELECT`** (`SELECT @x = col`): handled for the
  `SELECT INTO` form; the assignment form may require manual review when
  embedded in complex queries.
- **`SET ROWCOUNT n`**: removed with a warning (deprecated; use `TOP`/
  `FETCH FIRST` instead).
- **Non-catalog `IF EXISTS(…) BEGIN … END` control flow**: only a *system-catalog*
  existence guard (`IF [NOT] EXISTS(SELECT … FROM sys.…)` / `OBJECT_ID`) is
  treated as an idempotent-DDL guard whose condition is dropped and whose body is
  transpiled. A **real-data** condition (e.g. `IF EXISTS (SELECT NULL FROM t …)
  BEGIN … END`, common in migration scripts) is control flow — dropping its guard
  would silently change semantics. On **Oracle**, where `IF EXISTS(subquery)` is
  invalid PL/SQL (PLS-00204), a THEN-only guard is **emulated with a cursor FOR
  loop** over a one-row probe — `FOR … IN (SELECT 1 FROM DUAL WHERE [NOT]
  EXISTS(<subquery>)) LOOP <body> END LOOP` — so the body runs once iff the
  subquery returns a row; the top-level block is wrapped in an anonymous `BEGIN …
  END; /`. (A guard with an `ELSE`, or a body the engine can't model, is still a
  documented `-- UNIQUE:` carrier with a warning.) A T-SQL session directive such
  as `SET NOEXEC ON` inside the block has no Oracle equivalent and is carried.
- **Set-based trigger pseudo-tables** (`FROM inserted JOIN deleted`): T-SQL
  triggers are statement-level with `inserted`/`deleted` row sets. Column
  qualifiers (`inserted.col`) map to the row-level `NEW`/`OLD` (`:NEW`/`:OLD`).
  A **purely set-based** trigger (using `inserted`/`deleted` only via
  `FROM`/`JOIN`, with no row-level qualifier or `UPDATE(col)` predicate) is now
  **rewritten to a PostgreSQL statement-level trigger** with `REFERENCING NEW
  TABLE AS inserted OLD TABLE AS deleted` + `FOR EACH STATEMENT`. Oracle and
  MySQL keep documenting it with a `-- UNIQUE:` note: Oracle has no *named*
  transition tables (a compound trigger would need a manual PL/SQL collection,
  and `FROM inserted` would be invalid), and MySQL has neither. A **mixed**
  trigger (row-level and set-level together) cannot be a single trigger and
  stays documented on every target.

### Oracle → T-SQL specifics

Validated against a 1,900-line real-world PL/SQL file (25 procedures):

- **`%TYPE` / `%ROWTYPE` without `--db-url`**: emitted as a permissive carrier
  type with a `/* UNIQUE: <original> */` comment and a warning, since the real
  column type is unknown without a database connection. Provide `--db-url` to
  resolve these to the actual types from `ALL_TAB_COLUMNS`. The original is
  **restored on a reverse/onward transpilation** to an engine that supports it
  (e.g. back to Oracle, the `%TYPE` reference returns).
- **`EXECUTE IMMEDIATE ... USING bind1, bind2`**: Oracle bind-variable
  passing has no direct T-SQL equivalent; the `USING` clause is preserved
  in the dynamic SQL but flagged for manual conversion to `sp_executesql`
  parameters.
- **Ref cursor OUT parameters** (`SYS_REFCURSOR`, package cursor types):
  emitted as-is; T-SQL uses `CURSOR VARYING OUTPUT` or result sets, which
  require manual adaptation.
- **`DECODE` and complex `CASE` inside embedded DML**: usually transpiled
  by sqlglot, but deeply nested forms may need review.

These limitations are reported as **warnings** during transpilation so the
affected statements can be reviewed manually.
