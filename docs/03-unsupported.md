# Unique — Unsupported Features & Limitations

This document lists SQL features that are explicitly **out of scope** for
transpilation, along with the reasoning.

**Diagnostic codes.** Every degrade/warning carries a stable code of the form
`UNIQUE-NNNN` (four digits, flat sequential — the same idea as `ORA-00942` or
`rustc E0308`). Carrier comments therefore read `-- UNIQUE-1234: …` /
`/* UNIQUE-1234: … */`, and the matching `warnings` entry exposes it as
`.code`. Codes are **append-only**: never renumbered, never reused. The
authoritative catalog is `src/unique/core/diagnostics.py`; the generated
reference is [`reference/warnings.md`](reference/warnings.md).

A **completeness gate** (`tests/unit/core/test_diagnostic_completeness.py`)
holds the warning channel to the contract *no warning ships uncoded*, as a
ratchet that only goes down. Carrier-backed warnings inherit their code from the
`-- UNIQUE-NNNN:` carrier (reconciliation backfill); non-carrier warnings pass
the code at the emission site. The current floor is the **procedural-layer
carrier residual** — the T-SQL/MySQL/Oracle procedural emitters still emit some
legacy uncoded `/* UNIQUE: … */` carriers (they map to existing codes; coding
them at the procedural emitters and regenerating `tests/fixtures/procedures/*`
is a follow-up). Users can suppress a code from the warning channel with the CLI
`--ignore UNIQUE-NNNN` / API `ignore` field; suppression never touches the SQL —
the carriers are the artifact.

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
| `FOR XML` / `FOR JSON` → PG/MySQL/Oracle | T-SQL | Serializes a row set into a single XML/JSON scalar; no other engine has an equivalent, so both a `(SELECT … FOR XML)` scalar subquery and a top-level `SELECT … FOR XML/JSON` degrade to a carrier + warning (the base rows are returned; the exact null-omission/formatting rules cannot be guaranteed equal) |
| `CAST(x AS JSON)` → PG/Oracle/T-SQL | MySQL | T-SQL has no JSON type (error 243) and MySQL's canonical JSON spacing (`'[1, 2]'`) differs from PG/Oracle, so the value can't be guaranteed equal — the cast keeps the source value as text + a carrier |
| `EXTRACT(EPOCH FROM interval)` → T-SQL/MySQL/Oracle | PG | The total-seconds-of-an-interval computation has no portable form (T-SQL/MySQL have no interval *value* type); degrades to a carrier + warning. `EXTRACT(EPOCH FROM timestamp)` is translated to a literal date-diff |
| `timestamp - timestamp` → T-SQL/MySQL | PG/Oracle | The difference of two timestamps is an INTERVAL on PG/Oracle (e.g. `'02:00:00'`); T-SQL/MySQL have no interval *value* type, so it degrades to a `DATEDIFF/TIMESTAMPDIFF(SECOND, …)` second-count with a carrier + warning (a scalar, not an interval). `date - date` (a plain day count) is translated exactly |
| `x AT TIME ZONE 'zone'` → cross-engine | PG/T-SQL | Oracle/MySQL have no such operator (ORA-00902), and the PG↔T-SQL timestamp/timestamptz semantics plus the session-tz-dependent display differ, so the value can't be guaranteed equal — degrades to a carrier + warning (kept verbatim on its own dialect) |
| `sha256/sha512(bytea)` → Oracle/T-SQL/MySQL | PG | PG returns a **bytea** digest; the others return a hex string (Oracle STANDARD_HASH, T-SQL HASHBYTES, MySQL SHA2) — the same digest in a different representation, so it degrades to a carrier + warning. `md5()` (a hex digest everywhere) is translated |
| `STANDARD_HASH(x, 'SHA1')` / `RAWTOHEX(STANDARD_HASH(x, 'SHA1'))` → PG | Oracle | SHA1 is `STANDARD_HASH`'s own default algorithm (no `ALG` argument); core PostgreSQL (11+) has `md5()`/`sha256()`/`sha384()`/`sha512()` but no `sha1()` without the `pgcrypto` extension, so it degrades to a carrier + warning (`UNIQUE-1235`). `RAWTOHEX(x)` and `STANDARD_HASH`/`RAWTOHEX(STANDARD_HASH(...))` for MD5/SHA256/SHA384/SHA512 are translated (byte-identical, live-verified) |
| Windowed string aggregation (`LISTAGG(…) OVER (…)`) → PG/MySQL/T-SQL | Oracle | A string aggregate used as a window function: T-SQL/MySQL never allow it and PG rejects an ORDER-BY'd one — degrades to a carrier + warning |
| Exception handler / `RAISE NOTICE` / PRINT in a scalar **function** → T-SQL | PG/Oracle/MySQL | A T-SQL scalar function forbids side-effecting operators (TRY/CATCH, PRINT, RAISERROR — error 443), so a PG/Oracle `EXCEPTION` handler or `RAISE NOTICE` has no function-level equivalent; the function is preserved as a carrier comment (it compiles on the other engines) |
| Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` → Oracle/PG/MySQL | T-SQL | Those engines' cursors are forward-only (only `FETCH NEXT`), so a non-forward fetch has no equivalent; the scroll fetch degrades to a carrier comment and the surrounding OPEN/CLOSE still compile |
| `EXTRACT(MICROSECONDS FROM TIME …)` → Oracle | PG | Oracle has no `TIME` type (nor a MICROSECONDS extract field), so a `TIME`-based sub-second extract degrades to a carrier; MySQL/T-SQL compute it as `SECOND*1e6 + MICROSECOND` |
| FK `ON UPDATE` action → Oracle | Oracle | Oracle has **no** `ON UPDATE` referential action (only `ON DELETE CASCADE`/`SET NULL`); the clause is stripped — with a carrier + warning (not silently) — and the FK + `ON DELETE` kept |
| FK `ON DELETE SET DEFAULT` → Oracle | Oracle | Oracle's referential actions are only `CASCADE`/`SET NULL`/`NO ACTION` (`SET DEFAULT` is ORA-03001); the action is dropped — with a carrier + warning — so the FK reverts to `NO ACTION`; emulate `SET DEFAULT` with an `AFTER DELETE` trigger if required |
| Window frame `EXCLUDE CURRENT ROW/GROUP/TIES` → T-SQL/MySQL | PG/Oracle | Only PostgreSQL and Oracle support a frame `EXCLUDE`; T-SQL/MySQL have only `ROWS`/`RANGE` and no faithful rewrite (EXCLUDE removes specific peers from each frame), so the framed aggregate degrades to a warned `NULL` carrier there — PG/Oracle targets keep `EXCLUDE` |
| `INVISIBLE` column → PG/T-SQL | MySQL/Oracle | MySQL and Oracle support columns excluded from `SELECT *` (`c INT INVISIBLE`); those targets keep it. PostgreSQL and T-SQL have no invisible-column attribute, so it is dropped — with a carrier + warning — and the column becomes visible to `SELECT *` |
| `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` in a routine → PostgreSQL | PG | PL/pgSQL has no explicit savepoints (`ROLLBACK TO SAVEPOINT` is a compile-time syntax error); inside a procedure/function body they degrade to a carrier + warning — a `BEGIN … EXCEPTION` block is PL/pgSQL's subtransaction (it rolls back to its start on error). T-SQL (`SAVE`/`ROLLBACK TRANSACTION`), Oracle and MySQL keep native savepoints |
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

> Subsections §3.13+ are ordered **newest first** (a new limitation is added
> right after §3.12), so numbering runs §3.12, §3.22 … §3.13. All numbers
> exist; cross-references resolve by number, not position.

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

**Partition-extended table references** (Oracle `FROM t PARTITION (p)` /
`SUBPARTITION (sp)`) restrict a query to one partition's rows. No other engine
has this syntax, and the partition's key/value boundaries are not visible at
transpile time, so the row filter cannot be reconstructed as a `WHERE`. The
statement is preserved as a `UNIQUE:` carrier comment with a warning rather than
emitted as a semantically different query returning all rows (challenge
`reda-ora-partition-extension`).

### 3.3b Ordered aggregates: `KEEP (DENSE_RANK FIRST/LAST …)`

Oracle's `agg(x) KEEP (DENSE_RANK FIRST|LAST ORDER BY y)` is an **aggregate**
that returns one value per group (taken from the rows with the extreme `y`), not
a window function. No portable equivalent exists across T-SQL/PostgreSQL/MySQL
(a windowed `agg(x) OVER (ORDER BY y)` would silently become a per-row running
aggregate with a different result and row count), so it is preserved whole as a
`UNIQUE:` carrier comment with a warning (challenge `reda-ora-keep-denserank`).

### 3.4 Materialized Views

Only Oracle and PostgreSQL support materialized views natively. Transpilation
to T-SQL or MySQL will emit the view definition as a regular view with a
warning that materialization must be handled externally.

### 3.4b Non-portable view modifiers

`WITH CHECK OPTION` is portable and survives on all four engines (T-SQL and
Oracle accept only the unscoped form, so a MySQL/PostgreSQL `LOCAL`/`CASCADED`
scope is narrowed to the plain spelling there). The single-engine view
modifiers — T-SQL `SCHEMABINDING`/`ENCRYPTION`/`VIEW_METADATA`, MySQL
`ALGORITHM=`/`DEFINER=`/`SQL SECURITY` — are kept when the target is the
engine that owns them and otherwise dropped with a `-- UNIQUE:` carrier plus a
warning (they configure engine-local binding/security behavior with no
cross-engine equivalent).

### 3.5 Error Handling

Error handling constructs are structurally different:
- T-SQL: `TRY...CATCH`
- Oracle/PostgreSQL: `EXCEPTION` blocks
- MySQL: `DECLARE HANDLER`

The transpiler handles common patterns (catch-all, specific error codes) but
complex exception handling with multiple handlers may lose precision.

**Batch-level `BEGIN TRY … END CATCH`** (a TRY/CATCH outside any routine, common
in migration scripts) is routed to the procedural engine and lowered with the
same machinery as an in-routine TRY/CATCH: PostgreSQL wraps it in
`DO $$ BEGIN … EXCEPTION WHEN OTHERS THEN … END $$;`, Oracle in an anonymous
`BEGIN … EXCEPTION WHEN OTHERS THEN … END;` block. **MySQL** has no procedural
code outside a stored routine, so a top-level TRY/CATCH degrades to a documented
`-- UNIQUE:` carrier comment plus a `result.warnings` entry (never invalid
executable SQL). Note the standing PL/pgSQL caveat: an `EXCEPTION` block runs its
body inside an implicit subtransaction, so work done *before* the error inside
the same block is rolled back — T-SQL `TRY/CATCH` leaves already-committed
statements in place. Behavior is equivalent for the swallow-and-continue case
(the handler runs, the script proceeds); it diverges only when the protected
block performs a partial mutation before failing.

### 3.6 MERGE Statement → MySQL

MySQL lacks MERGE. The canonical pattern (one unconditional WHEN MATCHED
UPDATE plus one unconditional WHEN NOT MATCHED INSERT) is rewritten as
`INSERT ... SELECT ... ON DUPLICATE KEY UPDATE`; the rewrite relies on a
UNIQUE or PRIMARY KEY covering the ON-clause columns, which is noted in a
carrier comment and mirrored in `result.warnings`.

More complex MERGEs (conditional WHEN clauses, WHEN MATCHED DELETE, multiple
branches) are preserved as a documented comment and registered in
`result.warnings` / `result.unsupported` — never dropped silently.

#### MERGE clause composition across engines (audit 2026-07-24)

Some cross-engine MERGE lowerings are only value-equivalent in restricted
shapes; outside them the whole MERGE degrades to a carrier + warning rather
than ship silently-wrong output:

- **Conditional DELETE that reads an UPDATE-assigned column → Oracle.** Oracle
  folds a conditional `WHEN MATCHED … DELETE` / `WHEN MATCHED … UPDATE` pair
  into one `UPDATE … DELETE WHERE`, but Oracle evaluates `DELETE WHERE` against
  the *post-update* row while T-SQL evaluates the original row. The fold is
  therefore performed **only** when the DELETE condition references no target
  column the UPDATE assigns (source-column conditions are safe); an unsafe
  shape degrades warned (`… would delete rows the source keeps`).
- **`OUTPUT` on a MERGE → PostgreSQL.** PostgreSQL has no `MERGE … RETURNING`
  (PG16; PG17 spells `$action` as `merge_action()`), so the OUTPUT result set
  degrades to the same "no standalone OUTPUT/RETURNING result set" carrier +
  warning that Oracle/MySQL already use — the MERGE effect is preserved, the
  returned rows are not; the tail is never re-attached to a follow-up
  statement or a comment. (Plain INSERT/UPDATE/DELETE `OUTPUT` → PG still maps
  to a valid `RETURNING`.)
- **`THEN DO NOTHING` → T-SQL / Oracle.** PostgreSQL's `DO NOTHING` merge
  action has no T-SQL/Oracle spelling; first-match-wins lets it be lowered as a
  clause carve-out (its negated condition is ANDed onto every later same-kind
  clause; an unconditional `DO NOTHING` drops all later same-kind clauses). A
  MERGE `Var` action that is neither `DELETE` nor `DO NOTHING` degrades warned.

### 3.7 OUTPUT / RETURNING Clause → MySQL

MySQL has no equivalent to the OUTPUT (T-SQL) or RETURNING (Oracle/PostgreSQL)
clause. The transpiler will strip it with a warning suggesting the use of
`LAST_INSERT_ID()` or a follow-up SELECT.

### 3.8 Recursive CTEs

While all four engines support recursive CTEs (MySQL 8.0+), there are subtle
differences in recursion depth limits and cycle detection. The transpiler
translates the syntax but does not add engine-specific cycle guards.

T-SQL's own recursion-depth guard, the trailing `OPTION (MAXRECURSION n)`
query hint, has no equivalent on any other engine — PostgreSQL/MySQL/Oracle
recursive queries have no depth limit — so it is dropped with a warning
(`UNIQUE-1238`) rather than emitted invalid or silently discarded. Every
other `OPTION (...)` query hint (`MAXDOP`, `RECOMPILE`, `FORCE ORDER`,
`KEEPFIXED PLAN`, …) is a pure optimizer directive with no effect on the
result set, and is dropped the same way with a lighter warning
(`UNIQUE-1239`).

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

### 3.25 `GROUPS` Window Frame → T-SQL / MySQL

PostgreSQL and Oracle support the SQL:2011 `GROUPS` frame mode
(`OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW)`), which frames
by *peer groups* of the `ORDER BY` value. T-SQL and MySQL support only `ROWS`
and `RANGE`. With ties in the `ORDER BY` key a `GROUPS` frame spans whole peer
groups, so there is **no faithful `ROWS`/`RANGE` rewrite**. Transpiling to
T-SQL/MySQL degrades the framed aggregate to a warned `NULL` carrier rather than
emit an invalid `GROUPS` clause (T-SQL error 102 / MySQL 1235). Oracle and
PostgreSQL keep the native `GROUPS` frame.

### 3.24 T-SQL Money Literal Shorthand (`$12.50`) — Handled (2026-07-25)

T-SQL's bare currency literal (`$12.50`, `$100`) is mis-parsed by sqlglot as a
`table.column` reference (`Column(this=Literal(50), table=Identifier($12))`
for the dotted form, `Column(this=Identifier($100))` for a whole-dollar
amount) rather than a number — a nonsense shape that used to ship unmodified
(a quoted `"$12"` identifier and a bare `$` on non-T-SQL targets, both
invalid SQL there, with zero warnings). The converter now recognizes both
shapes on T-SQL source and rebuilds the numeric literal (`12.50`, `100`),
value-preserving on every target — no warning is needed since nothing is
lost. A **quoted** `"$12".50` / `[$12].[50]` is left untouched (it is
already-invalid T-SQL, not the money shorthand — live-verified Msg 102), and
the same `table.column` shape on a dialect with no money-literal syntax
(Oracle/MySQL source) is now flagged by `validate_source` as invalid input
instead of validating clean (generalizing the §07-08 "garbage `table.column`"
detector one level below the top-level bare-statement check).

### 3.22 Annotated Inherent Divergences (2026-07-24 batch)

Approved-limit divergences that now warn + annotate instead of shipping
silently:

- **Case-variant literals under ORDER BY/GROUP BY** (MySQL/T-SQL CI source →
  any other target): equal keys under a case-insensitive collation group/sort
  differently elsewhere; annotated when a case-variant literal pair is present.
- **MySQL `ZEROFILL`**: display-only zero pad (dropped by the parser); the
  stored value is identical — annotated from the source text.
- **`TO_CHAR(INTERVAL …)`**: each engine's default interval rendering differs
  and there is no portable mask — annotated.
- **Self-referencing FK cascade on T-SQL** (error 1785): the action downgrades
  to `NO ACTION` with a warned note (emulate with an AFTER trigger).
- **`SQL%ROWCOUNT`/`GET DIAGNOSTICS … = ROW_COUNT` → MySQL `ROW_COUNT()`**
  (audit N11/B12): Oracle's implicit-cursor `SQL%ROWCOUNT` and PostgreSQL's
  `GET DIAGNOSTICS x = ROW_COUNT` both count rows the last statement
  **matched**; MySQL's `ROW_COUNT()` counts rows it **changed** — an
  `UPDATE` that re-asserts a row's existing value returns a different count
  on MySQL (live-verified: Oracle `SQL%ROWCOUNT` = 1, MySQL `ROW_COUNT()` =
  0 for the same no-op update). No connection-wide fix exists without the
  caller opting into `CLIENT_FOUND_ROWS`, so the mapping is kept (still the
  closest equivalent) and every emission carries a `UNIQUE:` note + warning.
  T-SQL's `@@ROWCOUNT` is matched-rows too (verified equivalent) and stays
  unannotated.
- **`SQL%ROWCOUNT` in EXPRESSION position → PostgreSQL** (B37): PostgreSQL reads
  the last statement's row count only through the `GET DIAGNOSTICS x = ROW_COUNT`
  *statement*, so an inline reference (`IF SQL%ROWCOUNT <> 1`, `v := SQL%ROWCOUNT
  + 1`, a call argument, a `RETURN`) can no longer be substituted in place — it
  used to degrade to a `UNIQUE-1033` carrier. It is now lowered by hoisting a
  `GET DIAGNOSTICS uq_rowcount = ROW_COUNT;` (a `bigint` local declared once per
  routine) immediately before the referencing statement and substituting the
  local. Oracle's `SQL%ROWCOUNT` names the last executed DML, which in
  straight-line code is the preceding statement, so a capture placed just before
  the use reads the same value (live-verified on PostgreSQL). A **re-evaluated
  loop/exit condition** (`WHILE SQL%ROWCOUNT > 0`) cannot be captured once and
  keeps the honest `UNIQUE-1033` carrier + warning. T-SQL (`@@ROWCOUNT`) and
  MySQL (`ROW_COUNT()`) already read the count inline and are unaffected.
- **PostgreSQL `SET TRANSACTION [ISOLATION LEVEL <lvl>] READ ONLY|READ
  WRITE`** (audit N7/B8): MySQL comma-joins the isolation level and access
  mode into one statement; Oracle prefers the access mode (its `READ ONLY`
  is already implicitly serializable) when both are given, and keeps its
  existing `READ COMMITTED`-is-the-default no-op note otherwise. T-SQL has no
  access-mode clause on `SET TRANSACTION` — the isolation level statement is
  kept and the access mode is dropped with a `UNIQUE:` note + warning; a
  bare access-mode-only statement (no isolation level) has nothing to keep
  and degrades to a documented carrier + `unsupported` entry.
- **PostgreSQL `U&'…'` Unicode-escape literals**: mis-parsed by the parser —
  the statement degrades to a documented carrier + warning off PG (rewrite as
  a plain literal or `CHR()`).
- **PostgreSQL array column types** (`TEXT[]`): no cross-engine model (§7) —
  the output gate degrades the statement off PG.
- **Upsert semantics across engines** (audit B1/N1): the upsert clause is
  modeled and lowered per target (native PG⟷MySQL, MERGE for T-SQL/Oracle), but
  two divergences are annotated + warned rather than shipped silently:
  - **MySQL `ON DUPLICATE KEY UPDATE` fires on *any* unique/primary key**, not a
    single named conflict target — so a PG `ON CONFLICT (k)` mapped to MySQL, or
    a MySQL-source upsert whose target key had to be assumed from the in-script
    PK, carries a `UNIQUE:` note naming the assumption.
  - **MySQL `INSERT IGNORE` also swallows non-duplicate errors** (bad values, FK
    violations), which PG `ON CONFLICT DO NOTHING` and the MERGE forms do not; a
    PG `DO NOTHING` → MySQL `INSERT IGNORE` mapping is annotated to that effect.
  A MySQL-source upsert (no explicit conflict target) whose table's PK/UNIQUE key
  is **not** declared in-script cannot be lowered faithfully (PG needs a target;
  the MERGE needs an `ON` condition) and degrades the WHOLE statement to a
  carrier + warning — never a bare INSERT that would raise a duplicate-key error.
- **MySQL `REPLACE [INTO] t ...` statement** (both the `SET col = expr, ...`
  shorthand and the `[(cols)] VALUES (...)` form): a delete-then-insert
  upsert — it cascades on FK deletes, resets `AUTO_INCREMENT` differently,
  and fires DELETE **and** INSERT triggers, which is not the same operation
  as an `ON CONFLICT`/MERGE upsert. On a MySQL target it round-trips as a real
  `REPLACE INTO` statement; every other target has no faithful equivalent and
  the whole statement degrades to a carrier + warning naming REPLACE — never a
  silently emitted plain INSERT (duplicate-key error) or an UPDATE-style
  upsert (wrong semantics).

### 3.23 Oracle cursor attributes (per-cursor emulation, audit B7/N5+N6)

Oracle's cursor attributes have no cross-engine global, so each named cursor
gets its **own** state variables (mirroring the `%ROWCOUNT` counter), maintained
right beside the cursor operation they depend on — a FETCH or OPEN/CLOSE on
another cursor can no longer corrupt them:

- **`%FOUND` / `%NOTFOUND`** — T-SQL captures `@@FETCH_STATUS` into `@uq_<c>_fs`
  immediately after each `FETCH <c>` (T-SQL has a single global
  `@@FETCH_STATUS`, so a non-adjacent check would otherwise read another
  cursor's status). MySQL transfers the shared `NOT FOUND` handler flag into a
  per-cursor `v_uq_<c>_done` right after each FETCH, then resets the shared flag.
- **`%ISOPEN`** — a per-cursor `@uq_<c>_open` / `v_uq_<c>_open` flag set to 1/0
  on `OPEN`/`CLOSE` (T-SQL's `CURSOR_STATUS()` three-state/scope guessing is less
  faithful than a deterministic flag).
- **`%ROWCOUNT`** — the existing per-cursor counter (the MySQL `ROW_COUNT()`
  divergence for the *implicit* `SQL%ROWCOUNT` is annotated separately, §3.22).
- Each emitted MySQL loop carries a **unique label** (`loop_lbl_<n>`), so nested
  loops never collide (MySQL error 1309 "Redefining label").
- **Unrecognized cursor attributes** (e.g. `%BULK_ROWCOUNT`, or an invalid one):
  degrade to a `-- UNIQUE:` carrier + warning — never emitted as `%` modulo
  arithmetic.

### 3.21 Oracle Extended `INSTR` (occurrence / backward search)

Oracle's 4-argument `INSTR(s, sub, start, occurrence)` and the negative-start
backward search have no equivalent on MySQL/PostgreSQL/T-SQL. Literal
arguments are folded to Oracle's computed value at transpile time; a
non-literal occurrence or negative start degrades to `NULL` with a `UNIQUE:`
note and a warning. Compile-time literal folds of the same kind cover the
LENGTH family (per-source code-unit semantics, including T-SQL LEN's UTF-16
count and right-trim), substring edge positions, MySQL byte-string decodes
(`CAST(0x… AS CHAR)`, `CHAR(n USING cs)`), string-operand arithmetic, and
T-SQL binary `CONVERT`s.

### 3.20 PostgreSQL `money` Formatting

`::money` values render with a locale currency symbol on PostgreSQL
(`'$12.99'`). No other engine has that display form — T-SQL `MONEY` and the
`NUMBER(19,4)`/`DECIMAL(19,4)` mappings store the same numeric value but render
it plain (`12.99`). The numeric value is preserved; the formatted text differs.
A `money` cast is annotated with a `UNIQUE:` note + warning.

### 3.19 Column Types With No Target Equivalent (closest-type + note)

A column type the target genuinely lacks maps to the closest type, with a
trailing `-- UNIQUE:` note and a warning (never silently):

- `TIME`/`TIMETZ` → Oracle `INTERVAL DAY TO SECOND` (time of day as an
  interval; `TIMETZ` additionally drops the zone offset).
- PostgreSQL bare `INTERVAL` → Oracle `INTERVAL DAY TO SECOND` (Oracle splits
  intervals into two families; year-month values need `INTERVAL YEAR TO MONTH`).
- Oracle/PG `INTERVAL …` → T-SQL/MySQL `VARCHAR(30)` (no interval column type).
- `TIMESTAMP WITH TIME ZONE` → PostgreSQL `TIMESTAMPTZ` (exactly equivalent,
  faithful), T-SQL `DATETIMEOFFSET`, MySQL `TIMESTAMP` (UTC-normalized). A
  fractional-seconds precision stays on the base field
  (`TIMESTAMP(6) WITH TIME ZONE` → `TIMESTAMPTZ(6)` / `DATETIMEOFFSET(6)`).
- `TIMESTAMP WITH LOCAL TIME ZONE` → PostgreSQL `TIMESTAMPTZ` (same session-tz
  display, same instant), T-SQL `DATETIMEOFFSET` / MySQL `TIMESTAMP` (the
  instant is kept but the session-time-zone display is not reproduced); Oracle
  keeps its native spelling.
- `INTERVAL YEAR TO MONTH` / `INTERVAL DAY TO SECOND` → PostgreSQL native
  (faithful); a per-field precision PostgreSQL cannot express
  (`INTERVAL DAY(2) TO SECOND(6)`) is stripped to the bare qualifier with the
  original carried in the `UNIQUE:` note.
- Multi-bit `BIT(n)` (n > 1) → PostgreSQL native `BIT(n)`; Oracle
  `NUMBER(20)` / T-SQL `NUMERIC(20)` hold the 64-bit numeric value (the
  boolean-style `BIT` map used to truncate it to 1 bit silently). Bit-string
  literals/functions on those targets remain in the unsigned-64 limit family.
- Fractional-seconds precision above 6 → clamped to `(6)` on MySQL.
- A non-id bare Oracle `NUMBER` (arbitrary precision, no `PRIMARY KEY`/`UNIQUE`/
  identity/`FOREIGN KEY` role) → PostgreSQL unbounded `NUMERIC` (faithful, no
  note), MySQL/T-SQL bounded `DECIMAL(38, 10)` (`UNIQUE-1236` — those engines
  have no unbounded numeric type; values beyond 38 total / 10 fractional digits
  are not representable). An id-role bare `NUMBER` maps to `BIGINT` instead (so
  identity/PK/FK columns stay valid); `NUMBER(p,s)` keeps its `DECIMAL` mapping.
- T-SQL `SMALLDATETIME` → Oracle `DATE` (superset, no note needed).

The datetime/interval closest-type mappings above also apply to PL/SQL variable
declarations (a `DECLARE v TIMESTAMP WITH LOCAL TIME ZONE` in a converted
routine), not only to `CREATE TABLE` column definitions; the original spelling
rides a `/* UNIQUE */` carrier so a reverse transpilation restores it exactly.

Additionally, `CAST(x AS DATE)` on an Oracle *target* from a non-Oracle source
is wrapped in `TRUNC(…)`: every other engine's DATE cast strips the time of
day, while Oracle DATE keeps it.

### 3.18 `NOT` of a Non-Predicate on T-SQL (no boolean value type)

PostgreSQL, MySQL and Oracle evaluate `NOT` on a value with three-valued logic —
`(NOT NULL) IS NULL` is `TRUE` (the negation of `NULL` is `NULL`, which *is* null).
T-SQL has no boolean *value* type: `NOT` requires a predicate, so `NOT NULL` (or
`NOT <column>`) as an operand of a comparison is error 4145. The correct value is
kept on the engines that can express it; on T-SQL the operand degrades to a
documented carrier. (Correct parenthesization of the `NOT` operand — `(NOT x) IS
NULL`, which binds tighter than `NOT` — is now preserved on every engine.) See
[rationale/booleans/README.md](rationale/booleans/README.md) for the general value/predicate
duality mechanism (the tri-state `CASE` wrap and its reverse `<> 0` synthesis)
this carrier is the residual, unresolved case of.

### 3.17 Sequence `CURRVAL` → T-SQL

Oracle/PostgreSQL expose a sequence's last-issued value (`seq.CURRVAL` /
`currval('seq')`) without advancing it. T-SQL has no such function — `NEXT VALUE
FOR seq` only *advances* and returns. `NEXTVAL` maps cleanly; `CURRVAL` degrades to
a documented carrier (the pattern is to capture `NEXT VALUE FOR` into a variable
and reuse it).

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

T-SQL `TRY_CAST`/`TRY_CONVERT` (which yield `NULL` on a bad value) use the same
mechanism: over a **column** — where nothing can be folded — a numeric target is
wrapped in the runtime guard with `ELSE NULL` (`INT`-family targets guard on an
integer-only pattern; `DECIMAL`/`FLOAT` on the general numeric one), so a
non-numeric row yields `NULL` instead of a MySQL `0` or a PostgreSQL runtime abort.
A string-type `TRY` cast never fails and stays a faithful plain `CAST`.

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

### 3.38 Structural similarity, **not** equivalence

`unique compare` (and `unique.core.similarity.compare`) reports a *structural
similarity* percentage between two scripts — how close their statement shapes,
predicates and control flow are after both are normalized through the transpiler
to a PostgreSQL pivot. It is deliberately **not** a claim of semantic
equivalence, and the number must never be read as a "probability of
equivalence":

- **Query equivalence is undecidable in general.** No terminating procedure can
  decide whether two arbitrary SQL queries always return the same result. The
  SMT-based provers that do exist (Cosette, SPES, SQLSolver) cover only
  restricted `SELECT`-only fragments and no procedural code, so they cannot
  score the stored-routine scripts this feature targets. Formal equivalence
  proving is therefore **out of scope permanently.**
- **A high score is corroboration, not proof.** Two scripts can be structurally
  identical yet behave differently (e.g. a collation or NULL-ordering
  difference), and two semantically equivalent scripts can score low if written
  with different structure. Use the score to *rank and triage* a migration
  audit ("which routines drifted most?"), then review the flagged ones — not as
  a green light.
- **The pivot's fidelity bounds the score.** Both inputs pass through the
  transpiler first; where a construct degrades to a carrier on the PostgreSQL
  pivot (e.g. today's Oracle→PG and MySQL→PG procedural gaps), the degraded
  statement is counted as *unmatched*, which lowers the similarity rather than
  silently inflating it. Improving those transpilation paths raises the scores
  for the affected dialect pairs.

The report is per-dimension (DML structure, predicates, control flow, tree
match) precisely so a single opaque number is never the whole story.

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
| View re-creation | Every converted view emits `CREATE OR REPLACE VIEW` (`CREATE OR ALTER VIEW` on T-SQL), even when the source said plain `CREATE VIEW`. Deliberate (maintainer decision 2026-07-29): migration scripts stay re-runnable — a plain `CREATE` errors on an existing view, `OR REPLACE` redefines it. If the source relied on `CREATE` *failing* when the view already exists, that error is gone. |

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
- **`SELECT ... INTO #tmp`** inside a procedure (a T-SQL temp table, not a
  variable): lowered to the target's temp-table idiom rather than the invalid
  variable-`INTO` form. **PostgreSQL/MySQL** emit `CREATE TEMPORARY TABLE tmp AS
  SELECT …` preceded by a `DROP … IF EXISTS` (so a second `CALL` in the same
  session recreates it — temp tables outlive a statement there). **Oracle**
  hoists a session **Global Temporary Table** before the routine (same machinery
  as `@table` variables) and the body clears + repopulates it
  (`DELETE`/`INSERT`) so each call is isolated. Outside a procedure (in a
  function or trigger, where the Oracle CREATE cannot be hoisted) it falls back
  to the documented warned degrade.
- **`SELECT ... INTO @var`** combined with `OUTPUT ... INTO`: the `OUTPUT`
  clause is engine-specific and emitted as raw SQL.
- **Variable-assignment `SELECT`** (`SELECT @x = col`): handled for the
  `SELECT INTO` form; the assignment form may require manual review when
  embedded in complex queries.
- **`SET ROWCOUNT n`**: removed with a warning (deprecated; use `TOP`/
  `FETCH FIRST` instead).
- **Dynamic SQL** (T-SQL `EXEC(...)`/`EXEC sp_executesql`, Oracle
  `EXECUTE IMMEDIATE`, plpgsql `EXECUTE`): a **constant** SQL string — a
  literal argument, or a variable whose single assignment is a constant string
  literal — is **translated through the regular transpilation pipeline** and
  the translated text is spliced back into the string (audit N10/B11,
  2026-07-25), so the target engine executes its own dialect at runtime. A
  string **built at runtime** (concatenation, parameter values, more than one
  assignment) cannot be translated statically: literal fragments still get the
  existing fragment-level rewrites, and the statement is flagged with a
  "review the dynamic SQL" warning. A constant string that does not parse as a
  single source-dialect statement, and dynamic **routine DDL** (a
  `CREATE PROCEDURE/FUNCTION/TRIGGER` kept inside a string), are likewise
  flagged. A **parameterized** run (bind values via `USING` / `sp_executesql`
  bindings) keeps the established placeholder-level handling and its
  documented binding limits — the placeholder spelling belongs to the target's
  execution form, so the content is not statically re-translated. Nested
  embedded translation is capped at depth 2 (warned beyond).
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
- **Column-existence DDL guards** (a narrower catalog probe than the
  object-existence guard above): `IF NOT EXISTS(SELECT 1 FROM sys.columns
  WHERE object_id = OBJECT_ID('t') AND name = 'c' AND …) ALTER TABLE t
  ADD/ALTER COLUMN c …` cannot fall back to "drop the condition, use the
  target's native `IF NOT EXISTS`" the way the object-existence guard does —
  no target has an `ADD COLUMN IF NOT EXISTS`/`ALTER COLUMN` guard clause, so
  dropping the probe would raise "column already exists" (or double-apply a
  default) on a re-run. Every target instead gets a full synthesized probe
  against its own catalog, keeping the guard's condition: **PostgreSQL** a
  `DO $$ IF NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE
  table_name = lower('t') AND column_name = lower('c') AND …) THEN ALTER
  TABLE … END IF; END $$;` block; **MySQL** (no anonymous blocks, no `IF`
  outside a routine) a three-statement `SET @unique_guard_sql = (SELECT
  IF(NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='t'
  AND column_name='c' AND …), '<ddl>', 'DO 0')); PREPARE unique_guard_stmt
  FROM @unique_guard_sql; EXECUTE unique_guard_stmt; DROP PREPARE
  unique_guard_stmt;`; **Oracle** the same compact `FOR unique_guard IN
  (SELECT 1 FROM DUAL WHERE NOT EXISTS(SELECT 1 FROM user_tab_columns WHERE
  table_name = UPPER('t') AND column_name = UPPER('c') AND …)) LOOP EXECUTE
  IMMEDIATE '<ddl>'; END LOOP;` idiom the object-existence guard uses. An
  `ELSE` branch is supported when its body is a diagnostic `PRINT` (rewritten
  to `RAISE NOTICE`/`DBMS_OUTPUT.PUT_LINE`/a MySQL `CONCAT`-built alternate
  statement); any other `ELSE` body, or a probe predicate outside the
  recognized set (plain existence, `default_object_id <> 0`, `is_identity`),
  falls back to the honest warned drop rather than being guessed at. The same
  catalog-probe treatment covers a guarded `DROP TRIGGER` targeting
  PostgreSQL, for a different reason: PostgreSQL's `DROP TRIGGER` syntax
  requires `ON <table>`, which a T-SQL `OBJECT_ID(name, 'TR')` guard never
  names, so the table is resolved from a `pg_trigger` probe inside the `DO $$`
  block instead of dropping the statement.
  (`tests/unit/core/test_guard_translation.py::TestFaithfulColumnProbeGuard`,
  `::TestGuardElseBranch`, `::TestTrailingCommentOnGuardLine` — note: these
  live in `tests/unit/core/`, not `tests/integration/`.)
- **Oracle-source catalog probes rewritten per target** (the mirror
  direction): an Oracle guard or dynamic-DDL idiom that queries
  `user_indexes` (to resolve an index's owning table before a table-less
  `DROP INDEX`, which T-SQL requires by name — error 159) or
  `user_tab_cols`/`user_tab_columns` (to gate an `ALTER TABLE … MODIFY`) gets
  its catalog probe rewritten to the target's own system view with matching
  semantics, not carried verbatim: T-SQL `sys.indexes`/`sys.columns` +
  `OBJECT_NAME(object_id)`, PostgreSQL `information_schema.columns` (with a
  `lower(...)` compare, since Oracle identifiers default to upper case).
  (`tests/integration/test_oracle_source_m4_wave.py::TestOracleCatalogOnTsql.
  test_table_less_drop_index_resolves_table`,
  `::TestWave11Classes.test_alter_modify_inside_guard`.)
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
- **`INTERSECT ALL` / `EXCEPT ALL` have no T-SQL form at all** (the server
  rejects the keyword outright) — a `ROW_NUMBER`-pairing rewrite keeps
  every duplicate row for the common shape (see
  [the rationale article](rationale/dml/intersect-except-all.md)); an
  `ALL` operator immediately followed by more chained set operations, or
  acting on `SELECT *`, degrades whole rather than guess at operator
  precedence or an unknown column list.

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
