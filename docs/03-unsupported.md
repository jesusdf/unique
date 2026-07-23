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

These features will **never** be transpiled. They are degraded to a documented
carrier comment (`/* UNIQUE: … */` or `-- UNIQUE: …`) **with a matching
`warnings`/`unsupported` entry** in the result — nothing is dropped silently
(the project's no-silent-loss invariant).

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

Statements using PG array constructs — `ARRAY[…]` / `ARRAY(SELECT …)`
constructors (including inside `= ANY(…)` or a `WITHIN GROUP` aggregate),
array-type casts, and subscript reads/slices like `arr[2]` — degrade **whole**
to the carrier comment with a warning on T-SQL, MySQL and Oracle targets.
On a PostgreSQL target they are preserved faithfully (bracket spelling and
1-based subscripts intact).

### 1.5 Constant variables (`CONSTANT` declarations)

**Engines:** Oracle (PL/SQL), PostgreSQL (plpgsql)

T-SQL and MySQL have no constant local variables. A `name CONSTANT type`
declaration is emitted as the plain mutable declaration on those targets —
a safe relaxation for valid programs (the initializer still applies; only
the compile-time reassignment guard is lost). Oracle↔PostgreSQL keep
`CONSTANT` intact. Cursor scrollability (`[NO] SCROLL`) is likewise kept on
PostgreSQL and T-SQL (`SCROLL`) and dropped on MySQL/Oracle, whose cursors
are forward-only.

### 1.6 Function/Procedure Overloading

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
| REGEXP_LIKE/REGEXP_REPLACE/… → T-SQL | Oracle/PG/MySQL | SQL Server gained REGEXP_* only in 2025; targeting 2012+, a statement using them degrades to a documented carrier + warning (rewrite with LIKE/PATINDEX manually) |
| `TRANSLATE(s, from, to)` → MySQL | Oracle/PG | MySQL has no TRANSLATE, and a nested `REPLACE` emulation is order-dependent (not equivalent), so it degrades to a carrier + warning (Oracle/PG/T-SQL 2017+ have it natively) |
| MySQL `UpdateXML(xml, xpath, new)` → PG/T-SQL/Oracle | MySQL | Node-replacement XML DML has no faithful cross-engine form (PG has no such function; T-SQL uses `.modify()`, Oracle `UPDATEXML` a different XMLTYPE signature) — degrades to a carrier + warning (`ExtractValue` in the same statement still translates) |
| `FOR XML` / `FOR JSON` → PG/MySQL/Oracle | T-SQL | Serializes a row set into a single XML/JSON scalar; no other engine has an equivalent, so a `(SELECT … FOR XML)` scalar subquery degrades to a carrier + warning |
| `CAST(x AS JSON)` → PG/Oracle/T-SQL | MySQL | T-SQL has no JSON type (error 243) and MySQL's canonical JSON spacing (`'[1, 2]'`) differs from PG/Oracle, so the value can't be guaranteed equal — the cast keeps the source value as text + a carrier |
| `EXTRACT(EPOCH FROM interval)` → T-SQL/MySQL/Oracle | PG | The total-seconds-of-an-interval computation has no portable form (T-SQL/MySQL have no interval *value* type); degrades to a carrier + warning. `EXTRACT(EPOCH FROM timestamp)` is translated to a literal date-diff |
| `x AT TIME ZONE 'zone'` → cross-engine | PG/T-SQL | Oracle/MySQL have no such operator (ORA-00902), and the PG↔T-SQL timestamp/timestamptz semantics plus the session-tz-dependent display differ, so the value can't be guaranteed equal — degrades to a carrier + warning (kept verbatim on its own dialect) |
| `sha256/sha512(bytea)` → Oracle/T-SQL/MySQL | PG | PG returns a **bytea** digest; the others return a hex string (Oracle STANDARD_HASH, T-SQL HASHBYTES, MySQL SHA2) — the same digest in a different representation, so it degrades to a carrier + warning. `md5()` (a hex digest everywhere) is translated |
| Windowed string aggregation (`LISTAGG(…) OVER (…)`) → PG/MySQL/T-SQL | Oracle | A string aggregate used as a window function: T-SQL/MySQL never allow it and PG rejects an ORDER-BY'd one — degrades to a carrier + warning |
| Exception handler / `RAISE NOTICE` / PRINT in a scalar **function** → T-SQL | PG/Oracle/MySQL | A T-SQL scalar function forbids side-effecting operators (TRY/CATCH, PRINT, RAISERROR — error 443), so a PG/Oracle `EXCEPTION` handler or `RAISE NOTICE` has no function-level equivalent; the function is preserved as a carrier comment (it compiles on the other engines) |
| Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` → Oracle/PG/MySQL | T-SQL | Those engines' cursors are forward-only (only `FETCH NEXT`), so a non-forward fetch has no equivalent; the scroll fetch degrades to a carrier comment and the surrounding OPEN/CLOSE still compile |
| `EXTRACT(MICROSECONDS FROM TIME …)` → Oracle | PG | Oracle has no `TIME` type (nor a MICROSECONDS extract field), so a `TIME`-based sub-second extract degrades to a carrier; MySQL/T-SQL compute it as `SECOND*1e6 + MICROSECOND` |
| FK `ON UPDATE` action → Oracle | Oracle | Oracle has **no** `ON UPDATE` referential action (only `ON DELETE CASCADE`/`SET NULL`); the clause is stripped, the FK + `ON DELETE` kept |
| FK `MATCH FULL/PARTIAL/SIMPLE` → Oracle | Oracle | Oracle FKs are always simple-match; the `MATCH` clause (PostgreSQL) is stripped, the FK kept (ORA-03075 otherwise) |
| `INT UNSIGNED` → PG/Oracle/T-SQL | MySQL | No unsigned integer type; widened to the next signed size (BIGINT) so the full range fits — the ≥0 constraint is not re-added |
| Column `COMMENT` → T-SQL | MySQL/PG/Oracle | Carried inline (MySQL) or as `COMMENT ON COLUMN` (PG/Oracle); T-SQL's only vehicle is `sp_addextendedproperty`, so it is noted rather than synthesised |
| PostgreSQL-only types: `INET`, `CIDR`, `MACADDR`, range types (`INT4RANGE`, `TSRANGE`, …), `TSVECTOR`/`TSQUERY` | PostgreSQL | No cross-engine equivalent — a statement declaring one degrades to a documented carrier + warning (no silent invalid type). `SMALLMONEY`/`MONEY` **do** map (→ `DECIMAL`) |
| T-SQL-only types: `ROWVERSION`, `SQL_VARIANT`, `HIERARCHYID` | T-SQL | No equivalent elsewhere (the `ROWVERSION` auto-update semantic especially) — carrier + warning |
| Oracle `XMLTYPE` → MySQL | Oracle | MySQL has no XML type — carrier + warning (PG/T-SQL keep it as `XML`) |
| String collation in `=`/`ORDER BY`/`DISTINCT`/`LIKE` | all | Case/accent sensitivity is a per-**column** collation property, absent from a statement like `SELECT 'Ä' = 'A'`; the result can differ and cannot be compensated at the statement level. **User-approved limit (2026-07-18).** |
| `LENGTH` bytes-vs-chars | MySQL vs others | MySQL `LENGTH` counts bytes, others count characters, and the byte count itself depends on each engine's default encoding (UTF-8 vs UTF-16) — not reconcilable without the column encoding. **User-approved limit (2026-07-18).** Use `CHAR_LENGTH`/`OCTET_LENGTH` explicitly for a defined semantic. |
| Empty string as a distinct value → Oracle | Oracle | Oracle stores `''` as `NULL`, so an empty-string *result* (e.g. `IFNULL('', NULL)` = `''` on MySQL) becomes `NULL` on Oracle — Oracle cannot represent an empty string distinct from NULL, so there is no faithful workaround. Function inputs are recovered where possible (`ASCII('')`→0, `LOCATE('',…)`→1 via `COALESCE`); a divergent *result* degrades to a documented warning. **User-approved limit (2026-07-19).** |

### 2.1 Unmapped built-in scalar functions

A scalar function that is a **built-in of the source engine** but has no form on
the target (and no mapping/handler) — `SOUNDEX`→PostgreSQL, `GENERATE_SERIES`→
Oracle, `LISTAGG`→MySQL when no aggregate rewrite applies, `INITCAP`→T-SQL/MySQL
(word-boundary capitalisation, no built-in), and the long tail of engine-specific
functions — degrades the whole statement to a documented carrier + `validity_gate`
warning + `unsupported` entry, rather than shipping the call verbatim (which the
target engine rejects). A second safety net covers **sqlglot internal-name
leaks**: when sqlglot cannot map a function to the target it renders an internal
canonical that no engine has (`DATETIMEFROMPARTS`→`TIMESTAMP_FROM_PARTS`,
`FORMAT`→`NUMBER_TO_STR`, …); such a name — a sqlglot function canonical that is a
built-in in no supported engine — is degraded the same way (it is never a source
built-in, so the source-side check alone would let it slip through). The gate distinguishes a source
built-in from a **user object**: a name that is *not* a source built-in (a UDF,
stored procedure, or user type) is passed through untouched, because the target
schema is expected to define it. The per-engine built-in catalogs are sourced
authoritatively (live `pg_proc` / `V$SQLFN_METADATA` / `mysql.help_topic` + a
curated T-SQL list) by `scripts/gen_builtins.py`; the runtime reads the static
snapshot (`unique.core.builtins`). The scan covers both standalone DML and
routine bodies (it skips `TYPE(n)` constructors, the `VALUES` keyword, and
table-position names like `INSERT INTO line (…)` that may collide with a
built-in name).

Adding a real mapping for such a function (so it transpiles instead of
degrading) is always preferable — the carrier is the honest floor, not the goal.

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

**Non-reproducible date/number masks (⚠️ degrade to a carrier + warning).** A
**reproducible** mask — standard date fields, or a plain grouping/decimal number
mask (`TO_CHAR(x,'9G999D99')` ↔ T-SQL `FORMAT(x,'N2')` ↔ MySQL `FORMAT(x,2)`) —
is translated across all four engines. A mask with **no faithful cross-engine
equivalent** is *not* guessed; it emits a `UNIQUE:` carrier + warning instead of
a wrong value:

- **Number masks**: currency (`L`, `$`, `C`), hex (`X`), Roman (`RN`), angle-
  bracket negatives (`PR`), scientific (`EEEE`), and Oracle's leading pad space
  (a mask without `FM`, e.g. `' 1,234.57'`) — which `FORMAT` cannot reproduce.
- **Date masks**: locale month/day **names** (`MONTH`/`DAY`/`%W`) and quarter/
  ISO-week tokens (`Q`/`IW`) whose value depends on `NLS`/collation; a bare-letter
  literal (MySQL's unquoted `%Y-%m-%dT…`) that Oracle/PostgreSQL need quoted; and
  any exotic `.NET`/`TO_CHAR` token outside the table above.

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

### 3.16 `NCHAR(n)` Unicode Code Point (handled)

T-SQL `NCHAR(n)` returns the character for Unicode code point `n` (an integer — a
`0x…` argument is a number, not a byte string). It maps to PostgreSQL `CHR(n)`,
MySQL `CHAR(n USING utf32)`, and Oracle `NCHR(n)`. Oracle's `NCHR` only covers the
Basic Multilingual Plane and truncates a supplementary code point (`> U+FFFF`) to
16 bits, so those are emitted as `UNISTR('\HHHH\LLLL')` with the UTF-16 surrogate
pair (e.g. `NCHAR(0x1F600)` 😀 → `UNISTR('\D83D\DE00')`). Verified live on all three.

### 3.15 Error-Tolerant Cast (`DEFAULT … ON CONVERSION ERROR`)

Oracle's `CAST(x AS T DEFAULT d ON CONVERSION ERROR)` returns `d` when the
conversion fails instead of raising. It is translated so the fallback is never
silently dropped: T-SQL uses `COALESCE(TRY_CAST(x AS T), d)`; PostgreSQL and MySQL
have no error-safe cast, so a **numeric** target is guarded with a validation
`CASE` (`x ~`/`REGEXP` a number pattern, else `d`). A **literal** operand is folded
at transpile time — a valid number casts, a non-numeric one becomes `d` — because
PostgreSQL constant-folds the `THEN` branch during planning and would raise on a
bad constant before the guard runs. A non-numeric target with a fallback keeps the
plain cast and flags the dropped default with a carrier.

### 3.14 Case-Insensitive Collation Under DISTINCT / ORDER BY

MySQL's default collation is case-insensitive, so `SELECT DISTINCT x … ORDER BY x`
merges `'a'` and `'A'` into one group. PostgreSQL and Oracle are case-sensitive by
default and keep them distinct — a different row count that no rewrite can bridge
(a case-insensitive `ORDER BY LOWER(x)` is both invalid under `DISTINCT`, since the
sort key is not in the select list, and cannot change how `DISTINCT` itself
deduplicates). The transpiler keeps the plain, valid ordering and flags the
divergence with a carrier. T-SQL is also case-insensitive, so it dedups the same
way MySQL does (it may echo a different but collation-equal representative byte).

### 3.13 Oracle Collection Unnesting (`TABLE(CAST(MULTISET(...)))`)

Oracle can materialize a subquery into a nested-table collection and unnest it in
the `FROM` clause — `SELECT COLUMN_VALUE FROM TABLE(CAST(MULTISET(SELECT ...) AS
SYS.ODCINUMBERLIST))`. The `MULTISET` constructor, the collection cast, and the
`TABLE()` unnest operator have no PostgreSQL or T-SQL equivalent (PG uses `unnest`
on real array types; T-SQL has no collection type at all). The whole batch is
preserved as a documented carrier comment rather than emitted as invalid SQL.

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
- **`IF [NOT] EXISTS(…)` DDL guards** (idempotent migration scripts): a
  *system-catalog* existence guard (`IF [NOT] EXISTS(SELECT … FROM sys.…)` /
  `OBJECT_ID`). The catalog query has no faithful cross-engine form, so on most
  targets the condition is dropped and the guarded DDL is emitted (PostgreSQL/MySQL
  use their own `CREATE … IF NOT EXISTS` where available). On **Oracle** the guard
  is kept idempotently and portably: a guarded `CREATE` becomes a `user_objects`
  existence probe + `EXECUTE IMMEDIATE` — `BEGIN FOR _ IN (SELECT 1 FROM DUAL WHERE
  NOT EXISTS(SELECT 1 FROM user_objects WHERE object_name='X' AND object_type='…'))
  LOOP EXECUTE IMMEDIATE q'[<ddl>]'; END LOOP; END; /`. This is the idiomatic Oracle
  form (DDL cannot be a conditional statement inline, so `EXECUTE IMMEDIATE` is
  required; `q'[…]'` avoids escaping) and works on every version — unlike `CREATE …
  IF NOT EXISTS` (23ai+). A re-run no longer fails with `ORA-00955`. (A guarded
  `DROP` maps to `DROP … IF EXISTS` / a tolerant block.)
- **Non-catalog `IF EXISTS(…) BEGIN … END` control flow**: a **real-data**
  condition (e.g. `IF EXISTS (SELECT NULL FROM t …)
  BEGIN … END`, common in migration scripts) is control flow — dropping its guard
  would silently change semantics. On **Oracle**, where `IF EXISTS(subquery)` is
  invalid PL/SQL (PLS-00204), it is **emulated with a cursor FOR loop** over a
  one-row probe — `FOR … IN (SELECT 1 FROM DUAL WHERE [NOT] EXISTS(<subquery>))
  LOOP <body> END LOOP` — so the body runs once iff the subquery returns a row; a
  top-level block is wrapped in an anonymous `BEGIN … END; /`. An **`ELSE`** is a
  second FOR over the *negated* probe (`EXISTS` ⟷ `NOT EXISTS`, mutually exclusive
  — exactly one body fires). A T-SQL session directive such as `SET NOEXEC ON`
  inside the block has no Oracle equivalent and is carried.
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

---

## 7. Per-target impossibility gates (2026-07 direction-residue campaign)

The corpus campaign (waves 103–239, `docs/DONE.md` §36) live-validated the
PostgreSQL- and MySQL-source directions against all four real engines and
added **whole-statement degrade gates** for constructs the target engine
simply cannot express. Each gate emits the documented carrier + warning —
never invalid SQL, never a silent drop.

### To T-SQL

- **CTEs are statement-top only** — a `WITH` inside a set-operation arm,
  derived table, or subquery has no spelling (an INSERT-source CTE is hoisted
  instead of degraded). Same on Oracle.
- **Functions cannot write** (error 443): a PG function with side-effecting
  DML that stays a function (non-void, no OUT params, non-trigger) degrades;
  void/OUT-param functions become procedures instead. Functions can't access
  temp tables (2772) — creating one OR referencing a session temp table the
  script declares, from any source — or return cursors either.
- **`APPLY` takes no `ON`** — only a `LATERAL … ON TRUE` join maps; a lateral
  join with a real condition degrades. Same on Oracle.
- **No expression indexes**; `STRING_AGG(DISTINCT …)` has no form; `EXEC`
  arguments take only variables/literals (expression arguments are hoisted
  into typed variables automatically).
- `SET ROLE` exists everywhere but T-SQL (carrier there only).

### To MySQL

- **No table functions** except `JSON_TABLE` — a set-returning function in
  FROM position degrades whole.
- **`LAG`/`LEAD`/`NTH_VALUE` need constant offsets; `NTILE` a positive
  integer**; `GROUP_CONCAT SEPARATOR` takes a literal only, and `DISTINCT`
  inside non-builtin aggregates is a hard error — all degrade.
- **A DISTINCT string-aggregate must ORDER BY its own argument** —
  `string_agg(DISTINCT x, sep ORDER BY <other expr>)` has no MySQL
  spelling and degrades whole (M3 flip).
- **Cursors bind at declaration** — ref-cursor variables (opened dynamically)
  have no form; routines declaring/returning them degrade (also on T-SQL).
- `WITH` is legal only inside an INSERT's SELECT (relocated automatically);
  index prefix lengths (`KEY (a(132))`) are stripped (whole-column keys are a
  safe superset).
- MySQL-only **admin statements** (`FLUSH`/`RESET`/`PURGE`/`KILL`/`SHOW`/
  `REPAIR`/`OPTIMIZE`/`LOCK`/`INTO OUTFILE`…) ship verbatim on MySQL and
  degrade to carriers on every other target.

### To Oracle

- **No parenthesized join trees in FROM** (ORA-00907): pure INNER/CROSS trees
  flatten to the equivalent CROSS chain + WHERE; outer-join trees degrade
  (NULL-extension semantics would change).
- No `@@` globals, no `CAST(… AS BINARY)`, no `ALTER VIEW … AS` (rewritten to
  `CREATE OR REPLACE VIEW`), and PL/SQL cannot run static DDL (wrapped in
  `EXECUTE IMMEDIATE`). Locals shadowing parameters (PLS-00410) are renamed.

### PostgreSQL-only shapes (carried on every other target)

- Composite **row values** (`ELSE (a, b, c)`, row tuples as columns,
  whole-row casts `CAST(alias.* AS type)`, bare whole-row `OLD`/`NEW` in
  trigger bodies).
- `SEARCH`/`CYCLE` recursive-CTE clauses, data-modifying CTEs,
  `GENERATE_SERIES(…) OVER ()`, `TRUNCATE` triggers (kept where the target
  has the event), **non-SQL-language functions** (`LANGUAGE C`/internal —
  verbatim pg→pg, carrier elsewhere), `INTERVAL`-type casts (no such data
  type on MySQL/T-SQL).

### Statement-level architecture floor (not closable by more mappings)

After the campaign, the six corpus directions hold **98.8–99.8% live
validity**; the residue (133 statements) is three classes that need
**schema-aware transpilation**, declared out of scope for the current
statement-level architecture:

1. **Schema-dependent ambiguity** — e.g. a column whose name equals a local
   variable (the right-hand side of `SET data = data` is undecidable without
   the table's columns), `SELECT *` expansion into variables.
2. **Adversarial error-path inputs** (pg_regress corpora): corrupt latin1
   identifiers, `PREPARE`/`EXECUTE` dynamic SQL, custom aggregates.
3. **`RETURN QUERY` table functions** — a real multi-file feature (parser +
   IR + three emitters), tracked separately; attempted and cleanly reverted
   once to avoid a pg→pg regression.
