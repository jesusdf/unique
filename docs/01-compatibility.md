# Unique — SQL Compatibility Matrix

This document maps every major SQL feature category across the four supported
engines and indicates the transpilation support status for each.

> **SQLite (import-only).** SQLite is supported as a transpilation **source
> only** — SQLite → SQL Server / Oracle / PostgreSQL / MySQL. It has no
> procedural language (no stored procedures, functions or anonymous blocks), so
> it can never be a faithful procedural *target*; the tool rejects `sqlite` as a
> target with a clear error, and the web UI offers it as a source but not a
> target.
>
> **Supported from a SQLite source:**
> - **DDL** — `CREATE TABLE` (type affinity → the target's real types:
>   INTEGER/TEXT/REAL/BLOB/NUMERIC; a length-less binary → BLOB),
>   `INTEGER PRIMARY KEY [AUTOINCREMENT]` → the target's identity/serial,
>   `CREATE INDEX` / `CREATE VIEW`, `ALTER TABLE`, `DROP`.
> - **DML/DQL** — `SELECT`/`INSERT`/`UPDATE`/`DELETE`, CTEs (incl. recursive),
>   window functions.
> - **Functions** — most map via sqlglot (`ifnull`→COALESCE, `substr`, `instr`,
>   `group_concat`, …); SQLite-specific ones are rewritten per target
>   (`last_insert_rowid()` → the target's last-identity expression,
>   `datetime('now')`/`date('now')` → CURRENT_TIMESTAMP/CURRENT_DATE,
>   `random()` → RANDOM()/DBMS_RANDOM.VALUE).
> - **Triggers** — a row-level `CREATE TRIGGER … FOR EACH ROW BEGIN … END`
>   (NEW/OLD, WHEN, BEFORE/AFTER, INSERT/UPDATE/DELETE) → the target's trigger.
>
> **Not supported:** SQLite as a *target*; `typeof`/`hex(randomblob(…))` and
> other SQLite-only functions with no target equivalent (documented carriers);
> indexing an unbounded `TEXT`/`BLOB` column on MySQL/SQL Server/Oracle (see
> §0b in [`03-unsupported.md`](03-unsupported.md)).
>
> The matrix below describes the four full engines.

> **See also:** [`uml/catalog.mmd`](uml/catalog.mmd) — a UML class diagram that
> visualizes the full transpilable object catalog (tables, views, sequences,
> scalar/table functions, procedures, and triggers) with their dependencies.
> Includes the procedural surface (stored procedures and triggers) and the
> date-handling / record-update paths an ER diagram would omit.

> **Note:** the rows below are kept in sync with reality, but a matrix always
> lags the code. What keeps it honest is the **bug-detection infrastructure**
> (corpus × live execution, generative fuzzing, differential result testing,
> nightly mutation testing) and the **per-direction validity sweep** — see
> `docs/STATUS.md` for the measured percentages per direction. Recent
> additions folded into the rows: set operations of any arity incl.
> `EXCEPT`/`INTERSECT`→Oracle `MINUS` (§1.7), bitwise operators → Oracle via
> `BITAND`/`POWER` identities (§1.2a), cross-table `UPDATE … FROM … JOIN` per
> engine incl. multi-join sources → Oracle correlated subqueries (§2),
> string-`+`/compound assignment/named-slot function arguments, reversible
> type carriers, and — 2026-07-09 — embedded DML in routine bodies running
> the same IR pipeline as standalone DML, SQL*Plus script support from an
> Oracle source (`EXEC proc(args)` → each target's call form with `name =>
> value` association mapped per target; `SET SERVEROUTPUT`-style client
> directives documented, never shipped raw), Oracle FROM-less `DELETE`, and
> top-level anonymous blocks flattening to a plain batch on T-SQL. All
> four procedural fixtures validate **live** with 0 errors, so several
> "⚠️ Partial" procedural rows are effectively full today. See `docs/DONE.md`
> for the detailed history.
>
> **2026-07-17 — direction-residue campaign (waves 103–239, `docs/DONE.md`
> §36):** the PostgreSQL- and MySQL-source directions were corpus-measured to
> **98.8–99.8% live validity** and promoted to Tier 1 (see `docs/STATUS.md`).
> Folded into the rows below: an IR array model (PG arrays preserved pg→pg,
> whole-statement carriers elsewhere), set-returning functions in FROM
> (Oracle `TABLE(fn())`; MySQL carrier), boolean truthiness / predicates in
> value position comparisonized for strict engines, quantified `ALL`/`ANY`
> subqueries modeled, PG `DELETE … USING` → multi-table/correlated forms,
> data-modifying CTEs, hex literals per engine, dozens of procedural
> lexer/parser shapes (plpgsql `ALIAS FOR`, `FOREACH`, block labels, `::`
> and `..` tokens, MySQL labeled bodies, `INSERT … SET`, admin statements),
> and per-target impossibility gates that degrade honestly instead of
> shipping invalid SQL (see `docs/03-unsupported.md` §7).

**Legend**

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully supported — transpilation between all engines that have this feature |
| ⚠️ | Partially supported — works for common patterns, edge cases may fail |
| ❌ | Not supported — documented as out of scope |
| N/A | Feature does not exist in this engine |

---

## 1. Data Query Language (DQL)

### 1.1 SELECT Fundamentals

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| Basic SELECT | ✓ | ✓ | ✓ | ✓ | ✅ |
| Column aliases (AS) | ✓ | ✓ | ✓ | ✓ | ✅ |
| DISTINCT | ✓ | ✓ | ✓ | ✓ | ✅ |
| SELECT TOP n | ✓ | N/A | N/A | N/A | ✅ → LIMIT / FETCH FIRST |
| LIMIT / OFFSET | N/A | N/A | ✓ | ✓ | ✅ |
| FETCH FIRST n ROWS | ✓ (2012+) | ✓ (12c+) | ✓ | N/A | ✅ |
| ROWNUM | N/A | ✓ | N/A | N/A | ✅ → LIMIT / ROW_NUMBER() |
| SELECT INTO (new table) | ✓ | N/A | ✓ | ✓ | ✅ (CREATE TABLE AS SELECT) |

### 1.2 WHERE Clause

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| Comparison operators | ✓ | ✓ | ✓ | ✓ | ✅ |
| BETWEEN | ✓ | ✓ | ✓ | ✓ | ✅ |
| IN / NOT IN | ✓ | ✓ | ✓ | ✓ | ✅ |
| LIKE | ✓ | ✓ | ✓ | ✓ | ✅ |
| ILIKE | N/A | N/A | ✓ | N/A | ⚠️ → LOWER()+LIKE |
| IS NULL / IS NOT NULL | ✓ | ✓ | ✓ | ✓ | ✅ |
| EXISTS / NOT EXISTS | ✓ | ✓ | ✓ | ✓ | ✅ |
| ANY / ALL / SOME | ✓ | ✓ | ✓ | ✓ | ✅ |

### 1.2a Arithmetic, String & Bitwise Operators

| Operator | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|----------|-------|--------|------------|-------|------------------|
| Arithmetic `+ - * / %` | ✓ | ✓ (`%`→`MOD`) | ✓ | ✓ | ✅ |
| String concatenation | `+` | `\|\|` | `\|\|` | `CONCAT()` | ✅ when an operand is a recognizable string; `col + col` with no type info stays `+` (see [03-unsupported](03-unsupported.md)) |
| Compound assignment `+= -= *= /= %=` | ✓ | N/A | N/A | N/A | ✅ → `col = col <op> expr` |
| Bitwise `&` `\|` | ✓ | `BITAND` + identity | ✓ | ✓ | ✅ Oracle via `BITAND`/`a+b-BITAND` (live-validated) |
| Bitwise XOR `^`, shifts `<< >>` | ✓ | `BITAND`/`POWER` | ✓ (`#` XOR) | ✓ | ✅ Oracle via `a+b-2*BITAND` / `POWER(2,n)`; `#` on PostgreSQL |

### 1.3 JOINs

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| INNER JOIN | ✓ | ✓ | ✓ | ✓ | ✅ |
| LEFT/RIGHT OUTER JOIN | ✓ | ✓ | ✓ | ✓ | ✅ |
| FULL OUTER JOIN | ✓ | ✓ | ✓ | N/A | ⚠️ MySQL emulation via UNION |
| CROSS JOIN | ✓ | ✓ | ✓ | ✓ | ✅ |
| NATURAL JOIN | N/A | ✓ | ✓ | ✓ | ✅ |
| Oracle old-style (+) joins | N/A | ✓ | N/A | N/A | ✅ → ANSI JOIN syntax |
| LATERAL JOIN | ✓ (CROSS/OUTER APPLY) | ✓ (12c+) | ✓ | ✓ (8.0+) | ✅ |
| CROSS APPLY / OUTER APPLY | ✓ | N/A | N/A | N/A | ✅ → LATERAL JOIN |

### 1.4 Aggregation & Grouping

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| GROUP BY | ✓ | ✓ | ✓ | ✓ | ✅ |
| HAVING | ✓ | ✓ | ✓ | ✓ | ✅ |
| ROLLUP | ✓ | ✓ | ✓ | ✓ | ✅ |
| CUBE | ✓ | ✓ | ✓ | N/A | ⚠️ |
| GROUPING SETS | ✓ | ✓ | ✓ | N/A | ⚠️ |
| Aggregate functions (COUNT, SUM, AVG, MIN, MAX) | ✓ | ✓ | ✓ | ✓ | ✅ |
| STRING_AGG / LISTAGG / GROUP_CONCAT | ✓(2017+) | ✓ | ✓ | ✓ | ✅ NULL/expression separators handled per target; the impossible forms (T-SQL `STRING_AGG(DISTINCT …)`, MySQL expression separator / DISTINCT in non-builtin aggregates) degrade with a documented carrier |

### 1.5 Window Functions

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| ROW_NUMBER() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| RANK() / DENSE_RANK() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| NTILE() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| LAG() / LEAD() / NTH_VALUE() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ MySQL requires a constant offset — a non-constant offset (and `NTILE(NULL)`) degrades there with a documented carrier |
| FIRST_VALUE / LAST_VALUE | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Frame specs (ROWS/RANGE BETWEEN) | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Named window (WINDOW clause) | N/A | N/A | ✓ | ✓ (8.0+) | ⚠️ Inline expansion |

### 1.6 Subqueries & CTEs

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| Scalar subqueries | ✓ | ✓ | ✓ | ✓ | ✅ |
| Correlated subqueries | ✓ | ✓ | ✓ | ✓ | ✅ |
| CTE (WITH clause) | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Recursive CTE | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ `RECURSIVE` keyword per dialect (required on PG/MySQL, absent on T-SQL/Oracle); CTE column lists and VALUES bodies carried |
| Materialized CTE hints | N/A | ✓ | ✓ | N/A | ⚠️ Hint removed if unsupported |
| Non-top-level WITH (in a set-op arm / derived table / subquery) | N/A | N/A | ✓ | ✓ (8.0+) | ⚠️ preserved on PG/MySQL; T-SQL/Oracle allow CTEs only statement-top — documented carrier (INSERT-source CTEs are hoisted instead) |
| Data-modifying CTE (`WITH x AS (INSERT/UPDATE/DELETE … RETURNING) …`) | N/A | N/A | ✓ | N/A | ⚠️ preserved on PG, documented carrier elsewhere |
| SEARCH / CYCLE clauses (recursive-CTE ordering, PG 14+) | N/A | N/A | ✓ | N/A | ⚠️ verbatim on PG, documented carrier elsewhere |
| Set-returning function in FROM (`FROM generate_series(…) [WITH ORDINALITY]`) | ✓ | ✓ | ✓ | N/A | ⚠️ PG native, Oracle `TABLE(fn(args))`; MySQL has no table functions (JSON_TABLE aside) — documented carrier |
| Quantified subqueries (`> ALL / ANY / SOME (SELECT …)`) | ✓ | ✓ | ✓ | ✓ | ✅ modeled in the IR — the inner query maps fully |

### 1.7 Set Operations

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| UNION / UNION ALL | ✓ | ✓ | ✓ | ✓ | ✅ |
| INTERSECT | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| EXCEPT / MINUS | ✓ (EXCEPT) | ✓ (MINUS) | ✓ (EXCEPT) | ✓ (8.0+ EXCEPT) | ✅ |

---

## 2. Data Manipulation Language (DML)

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| INSERT INTO | ✓ | ✓ | ✓ | ✓ | ✅ |
| INSERT multi-row VALUES | ✓ | ✓ (12c+) | ✓ | ✓ | ✅ |
| INSERT ALL (multi-table) | N/A | ✓ | N/A | N/A | ⚠️ → multiple INSERTs |
| INSERT … ON CONFLICT / MERGE | ✓ (MERGE) | ✓ (MERGE) | ✓ (ON CONFLICT) | ✓ (ON DUPLICATE KEY) | ✅ |
| UPDATE | ✓ | ✓ | ✓ | ✓ | ✅ |
| UPDATE with JOIN | ✓ | ✓ | ✓ | ✓ | ✅ (syntax adaptation) |
| DELETE | ✓ | ✓ | ✓ | ✓ | ✅ |
| DELETE with JOIN / USING | ✓ | N/A | ✓ (USING) | ✓ | ✅ PG `USING` → T-SQL/MySQL multi-table DELETE, Oracle correlated `EXISTS`; derived-table sources degrade with a documented carrier |
| MERGE statement | ✓ | ✓ | ✓ (15+) | N/A | ⚠️ MySQL → INSERT ON DUP + UPDATE |
| TRUNCATE | ✓ | ✓ | ✓ | ✓ | ✅ |
| OUTPUT / RETURNING clause | ✓ (OUTPUT) | ✓ (RETURNING) | ✓ (RETURNING) | N/A | ⚠️ No MySQL equivalent |

---

## 3. Data Definition Language (DDL)

### 3.1 Tables

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CREATE TABLE | ✓ | ✓ | ✓ | ✓ | ✅ |
| ALTER TABLE ADD/DROP/MODIFY | ✓ | ✓ | ✓ | ✓ | ✅ (syntax normalization) |
| DROP TABLE | ✓ | ✓ | ✓ | ✓ | ✅ |
| IF EXISTS / IF NOT EXISTS | ✓ | N/A | ✓ | ✓ | ✅ (Oracle → exception block) |
| Temporary tables | ✓ (#table) | ✓ (GTT) | ✓ (TEMP) | ✓ (TEMPORARY) | ✅ |
| IDENTITY / SERIAL / AUTO_INCREMENT | ✓ | ✓ (12c+) | ✓ | ✓ | ✅ |
| Computed/generated columns | ✓ | ✓ | ✓ | ✓ | ✅ |
| DEFAULT values | ✓ | ✓ | ✓ | ✓ | ✅ |
| CHECK constraints | ✓ | ✓ | ✓ | ✓ (8.0.16+) | ✅ |
| Table partitioning | ✓ | ✓ | ✓ | ✓ | ⚠️ Syntax varies greatly |

### 3.2 Indexes

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CREATE INDEX | ✓ | ✓ | ✓ | ✓ | ✅ |
| UNIQUE INDEX | ✓ | ✓ | ✓ | ✓ | ✅ |
| Filtered/partial index | ✓ | N/A | ✓ | N/A | ⚠️ |
| Include columns | ✓ | N/A | ✓ (11+) | N/A | ⚠️ Stripped if unsupported |
| Index hints | ✓ | ✓ | N/A | ✓ | ❌ Engine-specific |

### 3.3 Views

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CREATE VIEW | ✓ | ✓ | ✓ | ✓ | ✅ |
| CREATE OR REPLACE VIEW | ✓ | ✓ | ✓ | ✓ | ✅ |
| Materialized views | N/A | ✓ | ✓ | N/A | ⚠️ |

### 3.4 Sequences

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CREATE SEQUENCE | ✓ (2012+) | ✓ | ✓ | N/A | ⚠️ MySQL → AUTO_INCREMENT |
| NEXT VALUE FOR / NEXTVAL | ✓ | ✓ | ✓ | N/A | ⚠️ |

---

## 4. Data Types

| Source Type | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|-------------|-------|--------|------------|-------|------------------|
| Integer types | INT, BIGINT, SMALLINT, TINYINT | NUMBER(n) | INTEGER, BIGINT, SMALLINT | INT, BIGINT, SMALLINT, TINYINT | ✅ |
| Decimal/Numeric | DECIMAL, NUMERIC | NUMBER(p,s) | DECIMAL, NUMERIC | DECIMAL, NUMERIC | ✅ |
| Float | FLOAT, REAL | BINARY_FLOAT, BINARY_DOUBLE | REAL, DOUBLE PRECISION | FLOAT, DOUBLE | ✅ |
| Boolean | BIT | NUMBER(1) | BOOLEAN | BOOLEAN/TINYINT(1) | ✅ |
| Char/Varchar | CHAR, VARCHAR, NVARCHAR | CHAR, VARCHAR2, NVARCHAR2 | CHAR, VARCHAR | CHAR, VARCHAR | ✅ |
| Text/CLOB | TEXT, NTEXT | CLOB, NCLOB | TEXT | TEXT, LONGTEXT | ✅ |
| Binary/BLOB | VARBINARY, IMAGE | BLOB, RAW | BYTEA | BLOB, LONGBLOB | ✅ |
| Date | DATE | DATE | DATE | DATE | ✅ |
| Time | TIME | N/A | TIME | TIME | ⚠️ |
| Datetime | DATETIME, DATETIME2 | TIMESTAMP | TIMESTAMP | DATETIME, TIMESTAMP | ✅ |
| Interval | N/A | INTERVAL | INTERVAL | N/A | ⚠️ |
| UUID/GUID | UNIQUEIDENTIFIER | RAW(16) | UUID | CHAR(36)/BINARY(16) | ⚠️ |
| JSON | NVARCHAR(MAX) | JSON (21c+) | JSON, JSONB | JSON | ⚠️ |
| XML | XML | XMLTYPE | XML | N/A | ⚠️ |
| Array | N/A | VARRAY | ARRAY | N/A | ⚠️ modeled in the IR: PG constructors/subscripts/casts preserved faithfully pg→pg; whole-statement documented carrier on other targets (see [03-unsupported §1.4](03-unsupported.md)) |
| Hex literals (`0x…` / `x'…'`) | ✓ (0x…) | ✓ (HEXTORAW) | ✓ (bytea) | ✓ (x'…') | ✅ per-engine spellings |
| User-defined types | ✓ | ✓ | ✓ | N/A | ❌ (incl. composite/rowtype-typed routine parameters — documented carrier off PG) |

---

## 5. Built-in Functions

### 5.1 String Functions

| Function Category | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|-------------------|-------|--------|------------|-------|------------------|
| Concatenation | + | \|\| | \|\| | CONCAT() | ✅ |
| Length | LEN() | LENGTH() | LENGTH() | LENGTH() / CHAR_LENGTH() | ✅ |
| Substring | SUBSTRING() | SUBSTR() | SUBSTRING() | SUBSTRING() | ✅ |
| Upper/Lower | UPPER/LOWER | UPPER/LOWER | UPPER/LOWER | UPPER/LOWER | ✅ |
| Trim | TRIM/LTRIM/RTRIM | TRIM/LTRIM/RTRIM | TRIM/LTRIM/RTRIM | TRIM/LTRIM/RTRIM | ✅ |
| Replace | REPLACE() | REPLACE() | REPLACE() | REPLACE() | ✅ |
| Position/Index | CHARINDEX() | INSTR() | POSITION() / STRPOS() | LOCATE() / INSTR() | ✅ |
| Padding | LEFT()/RIGHT() | LPAD()/RPAD() | LPAD()/RPAD() | LPAD()/RPAD() | ✅ |
| String split | STRING_SPLIT() | REGEXP_SUBSTR | STRING_TO_ARRAY() / REGEXP_SPLIT_TO_TABLE() | N/A | ⚠️ |
| Reverse | REVERSE() | REVERSE() | REVERSE() | REVERSE() | ✅ |
| Format | FORMAT() | TO_CHAR() | TO_CHAR() | FORMAT() | ✅ format-model table bridges Oracle/MySQL/.NET/strftime (§3.1 of [03-unsupported](03-unsupported.md)) |

### 5.2 Numeric Functions

| Function | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|----------|-------|--------|------------|-------|------------------|
| ABS, CEIL/CEILING, FLOOR | ✓ | ✓ | ✓ | ✓ | ✅ |
| ROUND | ✓ | ✓ | ✓ | ✓ | ✅ |
| MOD / % operator | % | MOD() | MOD() / % | MOD() / % | ✅ |
| POWER / SQRT / LOG | ✓ | ✓ | ✓ | ✓ | ✅ |
| SIGN | ✓ | ✓ | ✓ | ✓ | ✅ |
| RANDOM / RAND | RAND() | DBMS_RANDOM.VALUE | RANDOM() | RAND() | ✅ |

### 5.3 Date/Time Functions

| Function Category | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|-------------------|-------|--------|------------|-------|------------------|
| Current date/time | GETDATE(), SYSDATETIME() | SYSDATE, SYSTIMESTAMP | NOW(), CURRENT_TIMESTAMP | NOW(), CURRENT_TIMESTAMP | ✅ |
| Date add | DATEADD() | + INTERVAL | + INTERVAL | DATE_ADD() | ✅ |
| Date diff | DATEDIFF() | date1 - date2 | DATE_PART('epoch', age()) | DATEDIFF() / TIMESTAMPDIFF() | ✅ |
| Date part extract | DATEPART() / YEAR() etc. | EXTRACT() / TO_CHAR() | EXTRACT() / DATE_PART() | EXTRACT() / YEAR() etc. | ✅ `DATEPART`/`YEAR`/`MONTH`/`DAY` → `EXTRACT(part FROM x)` (live-validated) |
| Date format | FORMAT() / CONVERT() | TO_CHAR() | TO_CHAR() | DATE_FORMAT() | ✅ four-way format-model table (§3.1 of [03-unsupported](03-unsupported.md)); exotic tokens pass through |
| Date truncate | N/A | TRUNC() | DATE_TRUNC() | DATE() / DATE_FORMAT() | ⚠️ |

### 5.4 Null Handling Functions

| Function | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|----------|-------|--------|------------|-------|------------------|
| COALESCE | ✓ | ✓ | ✓ | ✓ | ✅ |
| ISNULL / NVL / IFNULL | ISNULL() | NVL() | COALESCE() | IFNULL() | ✅ → COALESCE |
| NULLIF | ✓ | ✓ | ✓ | ✓ | ✅ |
| NVL2 | N/A | ✓ | N/A | N/A | ✅ → CASE expression |

### 5.5 Conditional Expressions

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CASE WHEN | ✓ | ✓ | ✓ | ✓ | ✅ |
| IIF() | ✓ (IIF) | CASE WHEN | CASE WHEN | IF() | ✅ Oracle/PostgreSQL → `CASE WHEN`; MySQL `IF()`; T-SQL `IIF()` (live-validated) |
| DECODE() | N/A | ✓ | N/A | N/A | ✅ → CASE WHEN (PG's binary 2-arg `DECODE(x,'hex')` maps to CONVERT/HEXTORAW/UNHEX instead) |
| GREATEST / LEAST | N/A (2022+) | ✓ | ✓ | ✓ | ✅ |
| Numeric truthiness / predicates as values | N/A | N/A | partial | ✓ | ✅ MySQL/PG bare-value conditions are comparisonized (`<> 0`) for strict engines, and predicates in value position (`(x IS NULL) = y`, `SELECT a IN (…)`) become the exact tri-state CASE |

### 5.6 Type Conversion

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CAST | ✓ | ✓ | ✓ | ✓ | ✅ (with type mapping) |
| CONVERT | ✓ | N/A | N/A | ✓ | ✅ → CAST |
| TO_NUMBER / TO_DATE / TO_CHAR | N/A | ✓ | ✓ | N/A | ✅ → CAST / FORMAT |
| :: operator | N/A | N/A | ✓ | N/A | ✅ → CAST |
| TRY_CAST / TRY_CONVERT | ✓ | N/A | N/A | N/A | ⚠️ → Oracle `CAST(… DEFAULT NULL ON CONVERSION ERROR)`; else CASE + validation |

---

## 6. Procedural / Scripting SQL

### 6.1 Variables & Assignment

| Feature | T-SQL | Oracle (PL/SQL) | PostgreSQL (PL/pgSQL) | MySQL | Transpile Status |
|---------|-------|------------------|----------------------|-------|------------------|
| Variable declaration | DECLARE @var TYPE | var TYPE; | var TYPE; | DECLARE var TYPE; / SET @var | ✅ |
| Variable assignment | SET @var = val | var := val; | var := val; | SET @var = val; | ✅ |
| Compound assignment (UPDATE) | SET col += expr | N/A | N/A | N/A | ✅ → SET col = col + expr |
| SELECT INTO variable | SELECT @var = col | SELECT col INTO var | SELECT col INTO var | SELECT col INTO var | ✅ |

### 6.2 Control Flow

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| IF / ELSE | ✓ | ✓ | ✓ | ✓ | ✅ |
| CASE (procedural) | ✓ | ✓ | ✓ | ✓ | ✅ |
| WHILE loop | ✓ | LOOP / WHILE | LOOP / WHILE | WHILE / LOOP | ✅ |
| FOR loop | N/A | ✓ | ✓ | N/A | ⚠️ → WHILE equivalence |
| CURSOR FOR loop | N/A | ✓ | ✓ | ✓ | ⚠️ |
| BEGIN…END blocks | ✓ | BEGIN…END; | BEGIN…END; | BEGIN…END; | ✅ |
| GOTO | ✓ | ✓ | N/A | N/A | ❌ |
| WAITFOR / DBMS_LOCK.SLEEP | ✓ | ✓ | ✓ (pg_sleep) | ✓ (SLEEP) | ✅ |

### 6.3 Stored Procedures & Functions

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CREATE / ALTER / DROP PROCEDURE (incl. T-SQL `PROC` abbreviation) | ✓ | ✓ | ✓ | ✓ | ✅ T-SQL `PROC` is normalized to `PROCEDURE` (never leaked to other engines) |
| CREATE FUNCTION (scalar) | ✓ | ✓ | ✓ | ✓ | ✅ |
| CREATE FUNCTION (table-valued) | ✓ | ✓ (pipelined) | ✓ (RETURNS TABLE) | N/A | ⚠️ → a T-SQL string-split TVF becomes an Oracle `SYS.ODCIVARCHAR2LIST` function (`TABLE(fn(…))` callers); other shapes carrier |
| IN / OUT / INOUT params | ✓ | ✓ | ✓ | ✓ | ✅ |
| Default parameter values | ✓ | ✓ | ✓ | N/A | ⚠️ |
| Procedure call (`CALL` / T-SQL `EXEC` / SQL*Plus `EXEC proc(args)`) | ✓ | ✓ | ✓ | ✓ | ✅ each target's call form; `name => value` association → T-SQL `@name = value`, MySQL positional (warned) |
| Top-level anonymous block (`DECLARE…BEGIN…END`) | flattened batch | ✓ | ✓ (DO $$) | N/A | ✅ to T-SQL/Oracle/PG (T-SQL: flattened `DECLARE @x…; <stmts>`); MySQL documented carrier (no top-level procedural code) |
| SQL*Plus client directives (`SET SERVEROUTPUT`, `PROMPT`, `REM`) | N/A | ✓ (client) | N/A | N/A | ⚠️ documented as comments + warning (client-side, no server equivalent) |
| Overloading | N/A | ✓ | ✓ | N/A | ❌ |
| Packages | N/A | ✓ | N/A | N/A | ⚠️ → separate procs/funcs |

### 6.4 Error Handling

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| TRY…CATCH | ✓ | N/A | N/A | N/A | ⚠️ → BEGIN…EXCEPTION / HANDLER |
| EXCEPTION block | N/A | ✓ | ✓ | N/A | ⚠️ → TRY…CATCH / HANDLER |
| DECLARE HANDLER | N/A | N/A | N/A | ✓ | ⚠️ |
| RAISERROR / RAISE | ✓ | RAISE_APPLICATION_ERROR | RAISE | SIGNAL | ✅ |
| Error variables (@@ERROR, SQLCODE) | ✓ | ✓ | ✓ | ✓ | ⚠️ |

### 6.5 Cursors

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| DECLARE CURSOR | ✓ | ✓ | ✓ | ✓ | ✅ |
| OPEN / FETCH / CLOSE | ✓ | ✓ | ✓ | ✓ | ✅ |
| Cursor attributes | @@FETCH_STATUS | %FOUND, %NOTFOUND | FOUND | ✓ | ⚠️ |
| Ref cursors | N/A | ✓ (SYS_REFCURSOR) | ✓ (REFCURSOR) | N/A | ⚠️ Oracle↔PG type-mapped; a routine declaring or returning a ref cursor degrades whole on T-SQL/MySQL with a documented carrier |
| FETCH directions (NEXT/LAST/ABSOLUTE/RELATIVE) | ✓ | N/A | ✓ | N/A | ⚠️ native on PG/T-SQL (incl. SCROLL); Oracle/MySQL cursors are forward-only — documented carrier |

### 6.6 Dynamic SQL

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| EXEC / EXECUTE IMMEDIATE | ✓ | ✓ | ✓ | PREPARE + EXECUTE | ✅ |
| sp_executesql | ✓ | N/A | N/A | N/A | ⚠️ → EXECUTE … USING |
| Parameterized dynamic SQL | ✓ | ✓ (USING) | ✓ (USING) | ✓ | ⚠️ |

---

## 7. Transaction Control

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| BEGIN TRANSACTION | ✓ | implicit | ✓ | ✓ (START TRANSACTION) | ✅ |
| COMMIT / ROLLBACK | ✓ | ✓ | ✓ | ✓ | ✅ |
| SAVEPOINT | ✓ | ✓ | ✓ | ✓ | ✅ |
| SET TRANSACTION ISOLATION | ✓ | ✓ | ✓ | ✓ | ⚠️ Levels differ |

---

## 8. Access Control (DCL)

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| GRANT / REVOKE | ✓ | ✓ | ✓ | ✓ | ⚠️ Syntax normalization |
| CREATE USER / ROLE | ✓ | ✓ | ✓ | ✓ | ⚠️ |

---

## 9. Triggers

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| BEFORE / AFTER triggers | ✓ (AFTER/INSTEAD OF) | ✓ | ✓ | ✓ | ⚠️ |
| INSTEAD OF triggers | ✓ | ✓ | ✓ (via rules) | N/A | ⚠️ |
| Row-level triggers | N/A | ✓ | ✓ | ✓ | ⚠️ |
| Statement-level triggers | ✓ | ✓ | ✓ | N/A | ⚠️ |
| Trigger referencing (NEW/OLD) | INSERTED/DELETED | :NEW/:OLD | NEW/OLD | NEW/OLD | ✅ |
| Set-based trigger (FROM inserted/deleted) | ✓ | N/A | ✓ (transition tables) | N/A | ⚠️ PostgreSQL: rewritten to a statement-level trigger with `REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted`; Oracle/MySQL: documented |
| Mixed row-/set-level trigger | ✓ | — | — | — | ⚠️ documented on every target (cannot be a single trigger) |

---

## Summary Statistics

| Category | Total Features | ✅ Full | ⚠️ Partial | ❌ Out of Scope |
|----------|---------------|---------|------------|-----------------|
| DQL (SELECT, JOINs, etc.) | 53 | 39 | 13 | 1 |
| DML (INSERT, UPDATE, etc.) | 11 | 8 | 3 | 0 |
| DDL (Tables, Indexes, etc.) | 20 | 14 | 5 | 1 |
| Data Types | 17 | 11 | 6 | 0 |
| Built-in Functions | 33 | 25 | 8 | 0 |
| Procedural SQL | 27 | 14 | 11 | 2 |
| Transaction & DCL | 6 | 4 | 2 | 0 |
| Triggers | 5 | 1 | 4 | 0 |
| **Total** | **172** | **116 (67%)** | **52 (30%)** | **4 (2%)** |
