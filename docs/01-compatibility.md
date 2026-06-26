# Unique — SQL Compatibility Matrix

This document maps every major SQL feature category across the four supported
engines and indicates the transpilation support status for each.

> **See also:** [`uml/catalog.mmd`](uml/catalog.mmd) — a UML class diagram that
> visualizes the full transpilable object catalog (tables, views, sequences,
> scalar/table functions, procedures, and triggers) with their dependencies.
> Includes the procedural surface (stored procedures and triggers) and the
> date-handling / record-update paths an ER diagram would omit.

> **Note:** the matrix below is a point-in-time analysis. The procedural surface
> has since been hardened substantially (transaction control, WAITFOR,
> IDENTITY_INSERT, `@@ERROR`, `TOP n PERCENT`, QUOTED_IDENTIFIER, trigger
> pseudo-tables, reversible type carriers, …) and all four procedural fixtures
> now validate **live** against real engines with 0 errors, so several
> "⚠️ Partial" rows below are effectively full today. A later standalone-DML
> operator/function audit also fixed string-`+` concatenation, bitwise
> operators, compound assignment, and named-slot function arguments (rows 1.2a,
> 5.x). A cross-table-`UPDATE` audit then fixed `UPDATE … FROM … JOIN` (row 2):
> the source table and join predicate used to be dropped (a bare
> `UPDATE t SET c = s.c` was emitted), and are now rendered per engine —
> PostgreSQL `UPDATE t SET … FROM s WHERE …`, MySQL `UPDATE t JOIN s ON … SET …`,
> Oracle a correlated-subquery `UPDATE`, T-SQL its native `FROM`/`JOIN`; the same
> audit fixed a join alias emitted twice (`t2 b b`). See `docs/STATUS.md` for the
> current state and `docs/DONE.md` for the detailed history.

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
| Bitwise `&` `\|` | ✓ | N/A (`BITAND` only) | ✓ | ✓ | ⚠️ preserved as-is; valid on PostgreSQL/MySQL, not on Oracle |
| Bitwise XOR `^` | ✓ | N/A | ✓ (`#`) | ✓ | ⚠️ `#` on PostgreSQL; not valid on Oracle |

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
| STRING_AGG / LISTAGG / GROUP_CONCAT | ✓(2017+) | ✓ | ✓ | ✓ | ✅ |

### 1.5 Window Functions

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| ROW_NUMBER() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| RANK() / DENSE_RANK() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| NTILE() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| LAG() / LEAD() | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| FIRST_VALUE / LAST_VALUE | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Frame specs (ROWS/RANGE BETWEEN) | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Named window (WINDOW clause) | N/A | N/A | ✓ | ✓ (8.0+) | ⚠️ Inline expansion |

### 1.6 Subqueries & CTEs

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| Scalar subqueries | ✓ | ✓ | ✓ | ✓ | ✅ |
| Correlated subqueries | ✓ | ✓ | ✓ | ✓ | ✅ |
| CTE (WITH clause) | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Recursive CTE | ✓ | ✓ | ✓ | ✓ (8.0+) | ✅ |
| Materialized CTE hints | N/A | ✓ | ✓ | N/A | ⚠️ Hint removed if unsupported |

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
| DELETE with JOIN | ✓ | N/A | ✓ (USING) | ✓ | ⚠️ |
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
| Array | N/A | VARRAY | ARRAY | N/A | ❌ |
| User-defined types | ✓ | ✓ | ✓ | N/A | ❌ |

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
| Format | FORMAT() | TO_CHAR() | TO_CHAR() | FORMAT() | ⚠️ Format strings differ |

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
| Date part extract | DATEPART() / YEAR() etc. | EXTRACT() / TO_CHAR() | EXTRACT() / DATE_PART() | EXTRACT() / YEAR() etc. | ⚠️ `YEAR()/MONTH()/DAY()` ✅; standalone `DATEPART()` may emit non-standard `EXTRACT(part, x)` — prefer `YEAR(x)` etc. |
| Date format | FORMAT() / CONVERT() | TO_CHAR() | TO_CHAR() | DATE_FORMAT() | ⚠️ Format specifiers differ |
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
| IIF() | ✓ | N/A | N/A | IF() | ⚠️ emitted as `IF()` (valid on MySQL; `CASE WHEN` rewrite for Oracle/PostgreSQL pending — see [03-unsupported](03-unsupported.md)) |
| DECODE() | N/A | ✓ | N/A | N/A | ✅ → CASE WHEN |
| GREATEST / LEAST | N/A (2022+) | ✓ | ✓ | ✓ | ✅ |

### 5.6 Type Conversion

| Feature | T-SQL | Oracle | PostgreSQL | MySQL | Transpile Status |
|---------|-------|--------|------------|-------|------------------|
| CAST | ✓ | ✓ | ✓ | ✓ | ✅ (with type mapping) |
| CONVERT | ✓ | N/A | N/A | ✓ | ✅ → CAST |
| TO_NUMBER / TO_DATE / TO_CHAR | N/A | ✓ | ✓ | N/A | ✅ → CAST / FORMAT |
| :: operator | N/A | N/A | ✓ | N/A | ✅ → CAST |
| TRY_CAST / TRY_CONVERT | ✓ | N/A | N/A | N/A | ⚠️ → CASE + validation |

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
| CREATE PROCEDURE | ✓ | ✓ | ✓ | ✓ | ✅ |
| CREATE FUNCTION (scalar) | ✓ | ✓ | ✓ | ✓ | ✅ |
| CREATE FUNCTION (table-valued) | ✓ | ✓ (pipelined) | ✓ (RETURNS TABLE) | N/A | ⚠️ |
| IN / OUT / INOUT params | ✓ | ✓ | ✓ | ✓ | ✅ |
| Default parameter values | ✓ | ✓ | ✓ | N/A | ⚠️ |
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
| Ref cursors | N/A | ✓ (SYS_REFCURSOR) | ✓ (REFCURSOR) | N/A | ⚠️ |

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
| DQL (SELECT, JOINs, etc.) | 48 | 38 | 9 | 1 |
| DML (INSERT, UPDATE, etc.) | 11 | 7 | 4 | 0 |
| DDL (Tables, Indexes, etc.) | 20 | 14 | 5 | 1 |
| Data Types | 16 | 10 | 5 | 1 |
| Built-in Functions | 32 | 24 | 8 | 0 |
| Procedural SQL | 26 | 14 | 10 | 2 |
| Transaction & DCL | 6 | 4 | 2 | 0 |
| Triggers | 5 | 1 | 4 | 0 |
| **Total** | **164** | **112 (68%)** | **47 (29%)** | **5 (3%)** |
