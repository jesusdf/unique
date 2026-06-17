# Unique — Unsupported Features & Limitations

This document lists SQL features that are explicitly **out of scope** for
transpilation, along with the reasoning.

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

Format specifiers differ between engines (e.g., `'YYYY-MM-DD'` in Oracle vs
`'%Y-%m-%d'` in MySQL). The transpiler maps common format patterns but cannot
guarantee equivalence for all custom format strings.

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

MySQL lacks MERGE. The transpiler decomposes MERGE into:
- `INSERT ... ON DUPLICATE KEY UPDATE` (for simple cases)
- Separate `INSERT` and `UPDATE` wrapped in a transaction (for complex cases)

This may not be semantically identical for all edge cases.

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
  trailing semicolon, separated only by newlines. The current token-based
  parser does not treat newlines as statement terminators, so consecutive
  statements without semicolons inside a procedure body may be merged or
  truncated. **Workaround**: ensure statements are semicolon-terminated.
  Procedures that follow modern T-SQL style (semicolons after each
  statement) transpile fully.
- **`DECLARE @t TABLE (...)`** (table variables): captured as raw SQL;
  Oracle/PostgreSQL have no direct equivalent (use a collection type or
  temporary table).
- **`SELECT ... INTO @var`** combined with `OUTPUT ... INTO`: the `OUTPUT`
  clause is engine-specific and emitted as raw SQL.
- **Variable-assignment `SELECT`** (`SELECT @x = col`): handled for the
  `SELECT INTO` form; the assignment form may require manual review when
  embedded in complex queries.
- **`SET ROWCOUNT n`**: removed with a warning (deprecated; use `TOP`/
  `FETCH FIRST` instead).

These limitations are reported as **warnings** during transpilation so the
affected statements can be reviewed manually.
