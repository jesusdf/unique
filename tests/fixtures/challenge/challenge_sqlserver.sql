-- Challenge fixtures — T-SQL source.
-- Anonymized tricky constructs; one per entry. See README.md.

-- CASE: CREATE PROC abbreviation (PROC == PROCEDURE) must route like the full
-- spelling and never leak the T-SQL-only PROC keyword to another engine.
CREATE PROC get_row
    @id INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM t WHERE id = @id;
END
GO

-- CASE: CREATE OR ALTER (T-SQL 2016+ idempotent form) must route to the
-- procedural engine (not degrade to an "Unhandled CREATE" carrier) and map to
-- the other engines' CREATE OR REPLACE.
CREATE OR ALTER PROCEDURE upd_row
    @id INT
AS
BEGIN
    UPDATE t SET touched = 1 WHERE id = @id;
END
GO

-- CASE: BEGIN TRANSACTION (and its BEGIN TRAN abbreviation) must translate to
-- each engine's transaction-open form; Oracle has none (implicit), so it drops
-- with a documented carrier rather than a bare invalid BEGIN.
BEGIN TRANSACTION
GO

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[fixed]: ts-after-delete-count — a set-based inserted/deleted read that slips past the pseudo-table rewrite (hoisted declaration initializer) now degrades the WHOLE trigger to a documented carrier + warning on Oracle (no transition tables; compound-trigger rewrite by hand). Live-compiled VALID 2026-07-24.
CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t AFTER DELETE AS BEGIN DECLARE @c INT = (SELECT COUNT(*) FROM deleted); END

-- CASE[fixed]: ts-alter-add — Oracle requires DEFAULT before NOT NULL in a column def (ORA-30649 otherwise); the ADD column's 'NOT NULL DEFAULT v' is reordered to 'DEFAULT v NOT NULL'. live-verified DDL runs.
CREATE TABLE t (a INT); ALTER TABLE t ADD b NVARCHAR(10) NOT NULL DEFAULT 'x'

-- CASE[fixed]: ts-ascii-char — fails on mysql, oracle, postgresql. ORA-00904: "NCHAR": invalid identifier
SELECT ASCII('A'), CHAR(65), NCHAR(65)

-- CASE[limit]: ts-at-time-zone — AT TIME ZONE is not portable (Oracle/MySQL have no such operator; the session-tz-dependent display differs on PG/T-SQL), so it degrades to NULL + annotation off T-SQL (docs/03-unsupported.md). fails on oracle, postgresql
SELECT CAST('2020-01-01 10:00' AS DATETIME2) AT TIME ZONE 'UTC' AS r

-- CASE[fixed]: ts-binary-length — DATALENGTH(x) is the byte length -> Oracle LENGTHB, PG/MySQL OCTET_LENGTH; the VARBINARY(MAX) cast is unwrapped (byte length of a string is the same). live-verified 5.
SELECT DATALENGTH(CAST('hello' AS VARBINARY(MAX))) AS r

-- CASE[fixed]: ts-bit-cast — T-SQL CAST('true' AS BIT) parses the boolean word; fold to 1/0 (other engines can't convert 'true' to a number). Live-verified (1,1,0). 
SELECT CAST(1 AS BIT), CAST('true' AS BIT), CAST(0 AS BIT)

-- CASE[limit]: ts-bit-fns — GET_BIT/SET_BIT have no cross-engine builtin; gated + annotated (docs/03-unsupported.md). fails on mysql, oracle, postgresql
SELECT GET_BIT(0x0A, 1), SET_BIT(0x0A, 0, 1)

-- CASE[fixed]: ts-bitops — Signed source ~x yields a negative (two's-complement) result; MySQL's ~ is UNSIGNED (~5=18446744073709551610), so the bitwise NOT is wrapped in CAST(~x AS SIGNED) to match. &|^ and shifts already agree. live-verified. (1,7,6,-6)
SELECT 5 & 3, 5 | 2, 5 ^ 3, ~5

-- CASE[fixed]: ts-cast-bit — T-SQL CAST(x AS BIT) normalizes non-zero to 1; other engines keep the value. Emit SIGN(ABS(x)) (0->0, non-zero->1, NULL->NULL) in the TypeMapper pass.
SELECT CAST(2 AS BIT) AS r

-- CASE[fixed]: ts-cast-bit2 — TRY_CAST is carried (safe flag): Oracle DEFAULT NULL ON CONVERSION ERROR, PG resolves the non-boolean literal to NULL at transpile time. Live-verified (1,1,1,NULL).
SELECT CAST(1 AS BIT), CAST('true' AS BIT), CAST(0.5 AS BIT), TRY_CAST('x' AS BIT)

-- CASE[fixed]: ts-cast-date-int — CAST(<now> AS INT) is T-SQL's ROUNDED day count since 1900-01-01; emitted as ROUND(SYSDATE - DATE '1900-01-01') / epoch-seconds forms. Live value-verified equal (46225) on oracle/postgresql 2026-07-24.
SELECT CAST(GETDATE() AS INT) AS r

-- CASE[fixed]: ts-cast-int-datetime — T-SQL CAST(n AS DATETIME) reads n as days since the 1900-01-01 epoch (no other engine has that implicit conversion); reproduce as DATE 1900-01-01 + n (Oracle/PG add days to a DATE). live-verified 1900-01-02.
SELECT CAST(1 AS DATETIME) AS r

-- CASE[fixed]: ts-cast-money — MONEY/SMALLMONEY -> NUMBER/NUMERIC(19,4)/(10,4) (same value, precision-only). CONVERT(MONEY, currency-string) strips $ and commas before the numeric cast (Oracle/PG cannot parse "$12.99"). live-verified 12.99.
SELECT CAST(12.99 AS MONEY), CAST(12.99 AS SMALLMONEY), CONVERT(MONEY, '$12.99')

-- CASE[fixed]: ts-cast-suite — fails on mysql, oracle, postgresql. ORA-00906: missing left parenthesis
SELECT CAST('123' AS INT),CONVERT(INT,'123'),CONVERT(VARCHAR,123),TRY_CAST('x' AS INT),TRY_CONVERT(INT,'x'),PARSE('123' AS INT)

-- CASE[fixed]: ts-cast-trycast — stale finding: TRY_CAST now carries its safe flag (Oracle DEFAULT NULL ON CONVERSION ERROR; PG folds the bad literal to NULL) and CONVERT(DATE, GETDATE()) gains the Oracle TRUNC date-cast. Live-verified (123, NULL, today) on oracle/postgresql 2026-07-24.
SELECT CAST(123 AS VARCHAR(10)), TRY_CAST('x' AS INT), CONVERT(DATE, GETDATE())

-- CASE[fixed]: ts-char-encoding — fails on mysql, oracle, postgresql. ORA-00906: missing left parenthesis
SELECT ASCII('A'),CHAR(65),UNICODE(N'é'),NCHAR(233),CONVERT(VARBINARY,'AB'),CONVERT(VARCHAR,0x4142)

-- CASE[fixed]: ts-checksum-agg — fails on mysql, oracle, postgresql. ORA-00904: "CHECKSUM_AGG": invalid identifier
SELECT CHECKSUM_AGG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: ts-checksum-fns — fails on mysql, oracle, postgresql. ORA-00909: invalid number of arguments
SELECT CHECKSUM('a','b'), BINARY_CHECKSUM('x'), HASHBYTES('MD5','x')

-- CASE[fixed]: ts-choose — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT CHOOSE(2, 'a', 'b', 'c') AS r

-- CASE[fixed]: ts-compress — fails on oracle, postgresql. ORA-00936: missing expression
SELECT COMPRESS('data') AS r

-- CASE[fixed]: ts-compress2 — fails on mysql, oracle, postgresql. ORA-00936: missing expression
SELECT COMPRESS('x'), DECOMPRESS(COMPRESS('x'))

-- CASE[fixed]: ts-concat-null — fails on mysql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[fixed]: ts-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', 'c') AS r

-- CASE[fixed]: ts-concatws2 — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS(',', 'a', NULL, 'b') AS r

-- CASE[fixed]: ts-cond-all — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT ISNULL(NULL,3),NULLIF(1,1),COALESCE(NULL,3),IIF(1=1,'y','n'),CHOOSE(1,'a','b'),CASE WHEN 1=1 THEN 1 END

-- CASE[fixed]: ts-conditional — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT IIF(1>0,'y','n'), CHOOSE(2,'a','b','c'), ISNULL(NULL,'x'), NULLIF(1,1)

-- CASE[fixed]: ts-continue-break — compound assignment (@i+=1) expanded to @i=@i+1; BREAK->EXIT/LEAVE, CONTINUE->CONTINUE/ITERATE; MySQL loop labeled. Compiles on oracle/pg/mysql.
CREATE PROCEDURE p AS BEGIN DECLARE @i INT=1; WHILE @i<=3 BEGIN SET @i+=1; IF @i=2 CONTINUE; IF @i=5 BREAK; END; END

-- CASE[fixed]: ts-convert-style — CONVERT date styles map to TO_CHAR masks; style 126 now quotes the ISO 'T' separator, maps %f -> FF3 and casts the value to TIMESTAMP (FF on DATE is ORA-01821). Live-executed on oracle 2026-07-24.
SELECT CONVERT(VARCHAR,GETDATE(),101),CONVERT(VARCHAR,GETDATE(),112),CONVERT(VARCHAR,GETDATE(),120),CONVERT(VARCHAR,GETDATE(),126)

-- CASE[fixed]: ts-cube — fails on mysql, oracle, postgresql. ORA-00937: not a single-group group function
SELECT a,b,SUM(c) FROM (SELECT 1 a,2 b,3 c) t GROUP BY CUBE(a,b)

-- CASE[fixed]: ts-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT x FROM (VALUES (1),(2)) v(x); DECLARE @x INT; OPEN c; FETCH NEXT FROM c INTO @x; WHILE @@FETCH_STATUS = 0 BEGIN FETCH NEXT FROM c INTO @x; END; CLOSE c; DEALLOCATE c; END

-- CASE[limit]: ts-cursor-attr — fails on mysql, oracle, postgresql. @@CURSOR_ROWS has no equivalent (neutral-0 carrier; docs/03-unsupported.md §7) and FETCH without INTO is preserved as a comment. The Oracle PLS-00103/ORA-00906 CAST-context inversion is handled: the PRINT argument is a marked expression position, so its char CAST stays lengthless. All three targets compile (live 2026-07-24).
CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT 1; OPEN c; FETCH NEXT FROM c; IF @@FETCH_STATUS=0 PRINT CAST(@@CURSOR_ROWS AS VARCHAR); CLOSE c; DEALLOCATE c; END

-- CASE[fixed]: ts-date-bucket2 — fails on mysql, oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATE_BUCKET(MINUTE, 15, CAST('2020-01-01 00:07' AS DATETIME2))

-- CASE[fixed]: ts-dateadd — DATEADD/EOMONTH map to ADD_MONTHS/LAST_DAY/DATE_ADD with the date literal qualified; live-verified 2020-02-29, 2020-01-02, 2020-02-29 on all targets.
SELECT DATEADD(MONTH,1,'2020-01-31'), DATEADD(DAY,1,'2020-01-01'), EOMONTH('2020-02-15')

-- CASE[fixed]: ts-datediff — fails on oracle. ORA-01861: literal does not match format string
SELECT DATEDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[fixed]: ts-datediff-big — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATEDIFF_BIG(SECOND, '2020-01-01', '2020-01-02') AS r

-- CASE[fixed]: ts-datetimefromparts — fails on mysql, oracle, postgresql. ORA-00904: "TIMESTAMP_FROM_PARTS": invalid identifier
SELECT DATETIMEFROMPARTS(2020, 6, 15, 10, 30, 0, 0) AS r

-- CASE[fixed]: ts-datetimeoffset — mysql: DATETIME2(7) precision clamps to DATETIME(6) with a warned note; oracle: TIME(3) -> INTERVAL DAY TO SECOND with a warned note (docs/03-unsupported.md §3.19); DATETIMEOFFSET -> TIMESTAMP WITH TIME ZONE natively. Live-executed on mysql + oracle 2026-07-24.
CREATE TABLE t (a DATETIMEOFFSET, b DATETIME2(7), c TIME(3))

-- CASE[fixed]: ts-decimal-scale — same value at each engine's default decimal scale (10/3 = 3.3333...). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 10.00/3, 10/3.0, CAST(10 AS DECIMAL(10,4))/3, 1.5*1.5

-- CASE[fixed]: ts-default-nextval — fails on oracle, postgresql. ORA-04044: procedure, function, package, or type is not allowed here
CREATE SEQUENCE s AS INT START WITH 1;
GO
CREATE TABLE t (id INT DEFAULT (NEXT VALUE FOR s), a INT)

-- CASE[fixed]: ts-dttypes — oracle: TIME -> INTERVAL DAY TO SECOND (warned note, docs/03-unsupported.md §3.19), SMALLDATETIME -> DATE (superset). Live-executed on oracle 2026-07-24.
CREATE TABLE t (a DATE, b TIME, c DATETIME, d DATETIME2, e SMALLDATETIME, f DATETIMEOFFSET, g TIME(3))

-- CASE[fixed]: ts-dyn-concat-loop — the T-SQL aggregation assignment (SELECT @v = @v + expr FROM ...) rewrites to LISTAGG(expr, '') WITHIN GROUP (ORDER BY ROWNUM) preserving the variable prefix and NULL propagation; sys.tables maps to user_tables (name -> table_name) and EXEC(@sql) of an upper-cased local now reaches EXECUTE IMMEDIATE (the v_ prefix check was case-sensitive, PLS-00221). Live-compiled VALID on oracle 2026-07-24.
CREATE PROCEDURE p AS BEGIN DECLARE @sql NVARCHAR(MAX) = N''; SELECT @sql = @sql + 'DROP TABLE ' + name + ';' FROM sys.tables; EXEC(@sql); END

-- CASE[fixed]: ts-dyn-count — fails on oracle. PROCEDURE P compiled INVALID (line 6): PLS-00201: identifier 'QUOTENAME' must be declared
CREATE PROCEDURE p @tbl NVARCHAR(128) AS BEGIN DECLARE @sql NVARCHAR(MAX) = N'SELECT COUNT(*) FROM ' + QUOTENAME(@tbl); EXEC(@sql); END

-- CASE[fixed]: ts-emoji-len — LEN of a literal folds to T-SQL's UTF-16 code-unit count of the right-trimmed text (2 for an emoji). Live-verified on mysql/postgresql.
SELECT LEN(N'😀') AS r

-- CASE[fixed]: ts-eomonth — EOMONTH -> Oracle LAST_DAY(DATE '..'), PG month-end via DATE_TRUNC, MySQL LAST_DAY. All = 2020-02-29; Oracle's DATE renders a 00:00:00 time (same value, precision-only; maintainer policy 2026-07-19). live-verified.
SELECT EOMONTH('2020-02-15') AS r

-- CASE[fixed]: ts-eomonth-nested — DATEADD(MONTH,-1,EOMONTH(..)) -> Oracle ADD_MONTHS(LAST_DAY,-1), PG/MySQL month-end +/- 1 month. All = 2020-02-29; DATE / timestamp-midnight rendering differs (same value, precision-only; policy 2026-07-19). live-verified.
SELECT DATEADD(MONTH, -1, EOMONTH('2020-03-01')) AS r

-- CASE[fixed]: ts-error-functions — fails on oracle. PROCEDURE P compiled INVALID (line 12): PL/SQL: ORA-00904: "ERROR_LINE": invalid identifie
CREATE PROCEDURE p AS BEGIN BEGIN TRY SELECT 1/0; END TRY BEGIN CATCH SELECT ERROR_MESSAGE(), ERROR_NUMBER(), ERROR_LINE(); END CATCH END

-- CASE[fixed]: ts-float-precision — same IEEE/float value at each engine's display precision (FLOAT vs DOUBLE). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 0.1+0.2, CAST(0.1 AS FLOAT)+CAST(0.2 AS FLOAT), 1.0/3, CAST(1 AS FLOAT)/3

-- CASE[limit]: ts-fmt-spec — fails on oracle. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT FORMAT(GETDATE(),'ddd MMM dd HH:mm:ss yyyy'),FORMAT(GETDATE(),'tt hh:mm'),FORMAT(GETDATE(),'D')

-- CASE[limit]: ts-for-xml — T-SQL FOR XML/JSON serializes a row set into a single XML/JSON scalar; no other engine has an equivalent (dropping it ships the multi-column rows raw → ORA-00913), so the scalar subquery degrades to NULL + annotation (docs/03-unsupported.md). fails on mysql, oracle, postgresql
SELECT (SELECT 1 a,2 b FOR XML PATH('row'),ROOT('rows')) AS xmlcol

-- CASE[limit]: ts-format-iso — fails on oracle. T-SQL FORMAT numeric/date .NET mask with no reproducible cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT FORMAT(CAST('2020-06-15 14:30:45' AS DATETIME2), 'yyyy-MM-ddTHH:mm:ss') AS r

-- CASE[fixed]: ts-format-number — FORMAT(num, .NET-mask) numeric. A reproducible grouping/decimal mask (N2) maps to each engine: Oracle/PG TO_CHAR with an FM mask (no leading pad, matches FORMAT), MySQL FORMAT(n,decimals). Currency/hex/locale masks degrade. live-verified 1,234.50 on all four.
SELECT FORMAT(1234.5, 'N2') AS r

-- CASE[fixed]: ts-formatmessage — fails on mysql, oracle, postgresql. ORA-00904: "FORMATMESSAGE": invalid identifier
SELECT FORMATMESSAGE('hi %s', 'x') AS r

-- CASE[fixed]: ts-frac-seconds — CAST AS DATETIME2/DATETIME maps to an Oracle TIMESTAMP literal; live-verified 10:20:30.123456 / .123000.
SELECT CAST('2020-01-01 10:20:30.1234567' AS DATETIME2), CAST('2020-01-01 10:20:30.123' AS DATETIME)

-- CASE[fixed]: ts-gen-series-apply — GENERATE_SERIES maps to PG/Oracle (CROSS APPLY→LATERAL/APPLY already handled); live-verified (1,1)..(5,5).
SELECT value, ordinal FROM GENERATE_SERIES(1, 5) g CROSS APPLY (SELECT g.value AS ordinal) x

-- CASE[fixed]: ts-generate-series — GENERATE_SERIES(start,stop) maps to PG generate_series (column aliased 'value') / Oracle CONNECT BY LEVEL. Live-verified 1..5.
SELECT value FROM GENERATE_SERIES(1,5)

-- CASE[limit]: ts-geography — T-SQL geography/geometry CLR type methods (the ``type::method()`` ScopeResolution) have no cross-engine equivalent; sqlglot silently flattened them, so the construct now degrades to NULL + annotation instead of shipping mangled invalid SQL (docs/03-unsupported.md). fails on mysql, oracle, postgresql
SELECT GEOGRAPHY::Point(47.6, -122.3, 4326).ToString() AS r

-- CASE[fixed]: ts-grouping-id — GROUPING_ID(a,b) maps to multi-argument GROUPING(a,b) on PG and MySQL (the SAME bitmask, live-verified 0/1/3 on both); ROLLUP is native everywhere. All three targets live value-equal 2026-07-24.
SELECT a,b,SUM(c),GROUPING(a),GROUPING_ID(a,b) FROM (SELECT 1 a,2 b,3 c) t GROUP BY ROLLUP(a,b)

-- CASE[limit]: ts-hash-all — CHECKSUM is a proprietary T-SQL row hash with no cross-engine equivalent; gated + annotated (docs/03-unsupported.md). fails on mysql, postgresql
SELECT HASHBYTES('SHA2_512', 'abc'), CHECKSUM('abc')

-- CASE[fixed]: ts-hexcast — CONVERT(VARCHAR, 0xhex) folds to the cp1252-decoded literal ('Hello'); CONVERT(VARBINARY, str[, 0]) folds to the encoded bytes as each target's binary literal (HEXTORAW / bytea / x''), with binary style 0 no longer misparsed as a date style. Live-verified on oracle/postgresql.
SELECT CONVERT(VARCHAR,0x48656C6C6F),CONVERT(VARBINARY,'Hello',0)

-- CASE[fixed]: ts-host-db — fails on mysql, oracle, postgresql. ORA-00904: "DB_NAME": invalid identifier
SELECT HOST_NAME(), DB_NAME(), SUSER_SNAME()

-- CASE[limit]: ts-identity-funcs — T-SQL identity-scope reads (SCOPE_IDENTITY/@@IDENTITY/IDENT_CURRENT) have no cross-engine equivalent (each engine exposes the last identity differently: Oracle sequence.CURRVAL, PG lastval(), MySQL LAST_INSERT_ID()); the statement degrades to a carrier + warning (docs/03-unsupported.md). fails on mysql, oracle, postgresql
SELECT SCOPE_IDENTITY(), @@IDENTITY, IDENT_CURRENT('t')

-- CASE[fixed]: ts-inline-index2 — the inline INDEX table element (which sqlglot misparses as a column named INDEX) is reconstructed: kept inline on T-SQL/MySQL and emitted as a separate CREATE INDEX after the table on PG/Oracle. Live-executed on postgresql/oracle/mysql 2026-07-24.
CREATE TABLE t (id INT, name VARCHAR(50), INDEX ix_name NONCLUSTERED (name))

-- CASE[limit]: ts-insert-output — the T-SQL OUTPUT clause returns a result set; PostgreSQL maps it to RETURNING, but Oracle's RETURNING needs INTO variables (PL/SQL only, ORA-63809), so the INSERT runs and the OUTPUT is documented in a carrier (docs/03-unsupported.md). fails on oracle
CREATE TABLE t (id INT IDENTITY, n INT);
GO
INSERT INTO t (n) OUTPUT INSERTED.id,INSERTED.n VALUES (10),(20)

-- CASE[fixed]: ts-instead-of-insert — PG allows INSTEAD OF only on views: on a table the equivalent is a BEFORE row trigger returning NULL (suppresses the original operation) with a pg_trigger_depth guard that lets the body's own DML through. Live: INSERT lands exactly once (2026-07-24).
CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id, n FROM inserted; END

-- CASE[fixed]: ts-is-fns — fails on mysql, oracle, postgresql. ORA-00904: "ISJSON": invalid identifier
SELECT ISNUMERIC('12.3'), ISDATE('2020-01-01'), ISJSON('{}')

-- CASE[fixed]: ts-len-trailing — T-SQL LEN excludes trailing spaces (LEN('abc   ')=3); other engines count them. Trim the argument (RTRIM) on non-T-SQL targets.
SELECT LEN('abc   ') AS r

-- CASE[fixed]: ts-maxrecursion — recursive CTE: PG/MySQL get WITH RECURSIVE, Oracle gets the required column list (derived from the anchor SELECT). OPTION (MAXRECURSION n) is a T-SQL-only hint with no equivalent (recursion completes within the target defaults), dropped. Live 1..5 on all three.
WITH s AS (SELECT 1 n UNION ALL SELECT n+1 FROM s WHERE n<5) SELECT n FROM s OPTION (MAXRECURSION 10)

-- CASE[fixed]: ts-merge-full — WHEN NOT MATCHED BY SOURCE splits into a follow-up anti-join DELETE/UPDATE (PG17-only / no Oracle form); Oracle folds the conditional MATCHED pair into one UPDATE with CASE-kept values plus DELETE WHERE. Live: identical final rows on tsql/oracle/pg 2026-07-24.
CREATE TABLE tgt (id INT PRIMARY KEY, n INT); CREATE TABLE src (id INT, n INT);
GO
MERGE tgt USING src ON tgt.id = src.id WHEN MATCHED AND src.n > 0 THEN UPDATE SET n = src.n WHEN MATCHED THEN DELETE WHEN NOT MATCHED BY TARGET THEN INSERT (id, n) VALUES (src.id, src.n) WHEN NOT MATCHED BY SOURCE THEN DELETE;

-- CASE[fixed]: ts-metadata-funcs — fails on mysql, oracle, postgresql. ORA-00904: "OBJECT_ID": invalid identifier
SELECT COL_LENGTH('t', 'c'), OBJECT_ID('t')

-- CASE[fixed]: ts-money — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (price MONEY, small SMALLMONEY)

-- CASE[fixed]: ts-money-arith — fails on postgresql. FUNC-DIFF: source=(('12.8',),) target=(('$12.80',),)
SELECT CAST(10.5 AS MONEY) + CAST(2.3 AS MONEY) AS r

-- CASE[fixed]: ts-month-overflow — DATEADD(MONTH,1,'2020-01-31')=2020-02-29 on both; T-SQL returns a datetime (00:00:00), MySQL a date — same value, precision-only (maintainer policy 2026-07-19).
SELECT DATEADD(MONTH, 1, '2020-01-31') AS r

-- CASE[fixed]: ts-nchar-hex — NCHAR(0x1F600) takes a Unicode code point (integer), not hex bytes: PG CHR(n), MySQL CHAR(n USING utf32), Oracle NCHR(n) for BMP / UNISTR('\D83D\DE00') surrogate pair for supplementary (Oracle NCHR truncates > U+FFFF). Live U+1F600 on all three.
SELECT NCHAR(0x1F600) AS r

-- CASE[fixed]: ts-nolock-hint — the WITH (NOLOCK) table hint (a read-uncommitted advisory) is dropped for MySQL; it does not change the committed result set. The RED failure was a harness locked-table artifact. live-verified.
CREATE TABLE t (id INT);
GO
SELECT * FROM t WITH (NOLOCK)

-- CASE[limit]: ts-now-fns — fails on mysql, oracle, postgresql. current-time functions are non-deterministic (no cross-engine value parity) and SYSDATETIMEOFFSET has no equivalent (docs/03-unsupported.md §2).
SELECT GETDATE(), SYSDATETIME(), CURRENT_TIMESTAMP, GETUTCDATE(), SYSDATETIMEOFFSET()

-- CASE[fixed]: ts-now-variants — fails on mysql, oracle, postgresql. ORA-00904: "SYSUTCDATETIME": invalid identifier
SELECT GETDATE(), GETUTCDATE(), SYSDATETIME(), SYSUTCDATETIME(), CURRENT_TIMESTAMP

-- CASE[limit]: ts-openjson — OPENJSON is a T-SQL table-valued JSON shredder with no simple cross-engine form (Oracle JSON_TABLE, PostgreSQL json_array_elements have different shapes); the statement degrades to a carrier + warning rather than shipping the undefined function (docs/03-unsupported.md). fails on oracle, postgresql
SELECT * FROM OPENJSON('[1,2,3]')

-- CASE[fixed]: ts-order-strings — not a defect: 'Banana' and 'banana' are EQUAL sort keys under both the source (T-SQL CI) and target (MySQL ai_ci) collations, so their relative order is an unspecified tie-break on both engines, not a collation divergence. CS targets already get the LOWER(x) ordering emulation.
SELECT x FROM (VALUES ('banana'),('Apple'),('cherry'),('Banana')) v(x) ORDER BY x

-- CASE[fixed]: ts-pad-repeat — fails on mysql, oracle, postgresql. ORA-00904: "STR": invalid identifier
SELECT REPLICATE('ab',3),REVERSE('abc'),SPACE(3),RIGHT('000'+'7',3),STR(7,3)

-- CASE[fixed]: ts-patindex — fails on mysql, oracle, postgresql. ORA-00904: "PATINDEX": invalid identifier
SELECT PATINDEX('%[0-9]%', 'abc123') AS r

-- CASE[fixed]: ts-quotename — fails on mysql, oracle, postgresql. ORA-00904: "SPLIT_PART": invalid identifier
SELECT QUOTENAME('my table'), PARSENAME('a.b.c', 2)

-- CASE[fixed]: ts-realworld-audit — a bare THROW; (re-raise in a CATCH) was parsed with an empty message and shipped RAISE_APPLICATION_ERROR(-20001, ) (PLS-00103); now flagged as reraise -> Oracle RAISE;, PG/MySQL native re-raise. Compiles valid on oracle/pg/mysql
CREATE TABLE dbo.audit (id INT IDENTITY, msg NVARCHAR(MAX), ts DATETIME2);
GO
CREATE PROCEDURE dbo.log_it @msg NVARCHAR(MAX) AS BEGIN BEGIN TRY INSERT INTO dbo.audit (msg, ts) VALUES (@msg, SYSDATETIME()); END TRY BEGIN CATCH THROW; END CATCH END

-- CASE[fixed]: ts-recursion-limit — recursive CTE: PG/MySQL WITH RECURSIVE, Oracle derived column list; the OPTION (MAXRECURSION 1000) hint is dropped (no equivalent; 100 iterations completes within target defaults). Live COUNT=100 on all three.
WITH n AS (SELECT 1 v UNION ALL SELECT v+1 FROM n WHERE v<100) SELECT COUNT(*) FROM n OPTION (MAXRECURSION 1000)

-- CASE[fixed]: ts-recursive-cte — a T-SQL CTE that references its own name is recursive, but T-SQL omits the RECURSIVE keyword; PG/MySQL REQUIRE it. Detect the self-reference and emit WITH RECURSIVE (Oracle infers it, no keyword). Live 1..5 on PG and MySQL.
WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r

-- CASE[fixed]: ts-replicate-space — REPLICATE/SPACE/REVERSE now translate faithfully (Oracle RPAD, PG REPEAT, native REVERSE); stale tag, live-verified equal on all targets.
SELECT REPLICATE('ab', 3), SPACE(5), REVERSE('abc')

-- CASE[fixed]: ts-rowversion — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (row_ver ROWVERSION, flags BINARY(8))

-- CASE[limit]: ts-scroll-cursor — a scroll cursor FETCH (PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE) has no cross-engine equivalent (Oracle/PG/MySQL cursors are forward-only, only FETCH NEXT); the scroll fetch degrades to a carrier comment and the surrounding OPEN/CLOSE compile (docs/03-unsupported.md). fails on mysql, oracle, postgresql
CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR LOCAL SCROLL FOR SELECT 1; OPEN c; FETCH LAST FROM c; CLOSE c; DEALLOCATE c; END

-- CASE[fixed]: ts-select-into — T-SQL SELECT … INTO newtable creates a table; Oracle has no such form, so it is rewritten to CREATE TABLE newtable AS SELECT …. live-verified DDL runs.
CREATE TABLE src (id INT);
GO
SELECT id INTO dst FROM src

-- CASE[fixed]: ts-select-into-temp — SELECT … INTO #t2 (a T-SQL session temp table) becomes Oracle CREATE GLOBAL TEMPORARY TABLE t2 AS SELECT …. live-verified DDL runs.
SELECT id INTO #t2 FROM (SELECT 1 id) s;
SELECT * FROM #t2;

-- CASE[fixed]: ts-seq-use — fails on oracle, postgresql. ORA-00904: "NEXT_VALUE_FOR": invalid identifier
CREATE SEQUENCE s START WITH 1; SELECT NEXT VALUE FOR s

-- CASE[fixed]: ts-sequence-next — fails on oracle, postgresql. ORA-00904: "NEXT_VALUE_FOR": invalid identifier
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1;
GO
SELECT NEXT VALUE FOR seq

-- CASE[fixed]: ts-session-ctx — fails on mysql, oracle, postgresql. ORA-00904: "CURRENT_TRANSACTION_ID": invalid identifier
SELECT SESSION_CONTEXT(N'k'), CURRENT_TRANSACTION_ID()

-- CASE[fixed]: ts-soundex-diff — fails on mysql, oracle, postgresql. ORA-00904: "DIFFERENCE": invalid identifier
SELECT SOUNDEX('Smith'), DIFFERENCE('Smith', 'Smyth')

-- CASE[fixed]: ts-soundex3 — fails on mysql, oracle, postgresql. ORA-00904: "DIFFERENCE": invalid identifier
SELECT SOUNDEX('Smith'),DIFFERENCE('Smith','Smyth')

-- CASE[fixed]: ts-sp-executesql — named sp_executesql parameters now bind POSITIONALLY in EXECUTE IMMEDIATE ... USING (the named form was PLS-00103), with a warned UNIQUE note that the dynamic string's placeholders must be spelled :1, :2, ... Live-compiled VALID on oracle 2026-07-24.
CREATE PROCEDURE p AS BEGIN DECLARE @sql NVARCHAR(200)=N'SELECT * FROM t WHERE id=@i'; EXEC sp_executesql @sql,N'@i INT',@i=5; END

-- CASE[limit]: ts-spatial — T-SQL geometry/geography CLR type methods (``type::Point(…).STDistance(…)`` ScopeResolution) have no cross-engine equivalent; degraded to NULL + annotation instead of the mangled invalid flatten (docs/03-unsupported.md). fails on oracle, postgresql
SELECT geometry::Point(0,0,0).STDistance(geometry::Point(3,4,0)), geography::Point(47,-122,4326).ToString()

-- CASE[fixed]: ts-spectypes — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (a BINARY(16), b VARBINARY(MAX), c IMAGE, d BIT, e UNIQUEIDENTIFIER, f XML, g SQL_VARIANT, h ROWVERSION, i HIERARCHYID, j GEOGRAPHY)

-- CASE[limit]: ts-spid-version — @@SPID/@@VERSION map to each engine's own session-id/version function, but the values are server- and connection-specific and can never equal T-SQL's; mapped + annotated (docs/03-unsupported.md). fails on mysql, oracle, postgresql
SELECT @@SPID, @@VERSION

-- CASE[fixed]: ts-split-agg — fails on oracle, postgresql. ORA-00904: "STRING_SPLIT": invalid identifier
SELECT STRING_AGG(value,',') FROM STRING_SPLIT('a,b,c',',')

-- CASE[limit]: ts-st-distance — T-SQL geometry ``::Point(…).STDistance(…)`` (a CLR ScopeResolution method) has no cross-engine equivalent; degraded to NULL + annotation (docs/03-unsupported.md). fails on oracle, postgresql
SELECT geometry::Point(0,0,0).STDistance(geometry::Point(3,4,0)) AS r

-- CASE[fixed]: ts-str-func — fails on mysql, oracle, postgresql. ORA-00904: "STR": invalid identifier
SELECT STR(3.14, 6, 2) AS r

-- CASE[fixed]: ts-str-misc — fails on mysql, oracle, postgresql. ORA-00904: "QUOTENAME": invalid identifier
SELECT SOUNDEX('Robert'),DIFFERENCE('Robert','Rupert'),FORMAT(1234567.891,'N2'),QUOTENAME('a]b')

-- CASE[fixed]: ts-str-plus-num — '10' + 5 is arithmetic (number operand), not concat: kept as + so it evaluates to 15.
SELECT '10' + 5 AS r

-- CASE[fixed]: ts-stragg-order — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT STRING_AGG(x,',') WITHIN GROUP (ORDER BY x DESC) FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[fixed]: ts-stragg-within — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT STRING_AGG(x,',') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[fixed]: ts-stragg-within2 — a lengthless character CAST inside STRING_AGG's canonical fragment is sized (VARCHAR2(4000)) for Oracle SQL context and mapped to CHAR for MySQL's CAST target set. Live-executed on mysql/oracle 2026-07-24.
CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); CREATE TABLE data (data NVARCHAR(MAX));
GO
SELECT STRING_AGG(CAST(n AS VARCHAR), ',') WITHIN GROUP (ORDER BY id) FROM t

-- CASE[fixed]: ts-string-agg-within — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: ts-string-fns2 — fails on mysql, oracle, postgresql. ORA-00904: "STUFF": invalid identifier
SELECT STRING_ESCAPE('a"b', 'json'), STUFF('abcdef',2,3,'XYZ')

-- CASE[fixed]: ts-string-fns3 — fails on mysql, oracle, postgresql. ORA-00904: "QUOTENAME": invalid identifier
SELECT TRANSLATE('abc','ab','xy'), REPLICATE('ab',3), QUOTENAME('a]b')

-- CASE[fixed]: ts-string-split2 — fails on oracle, postgresql. ORA-00904: "STRING_SPLIT": invalid identifier
SELECT * FROM STRING_SPLIT('a,b,c', ',') WHERE value <> 'b'

-- CASE[fixed]: ts-stuff — STUFF now translates faithfully (MySQL INSERT, PG OVERLAY, Oracle SUBSTR concat); stale tag, live-verified 'aXYef' on all targets.
SELECT STUFF('abcdef', 2, 3, 'XY') AS r

-- CASE[fixed]: ts-sysdatetime — fails on mysql, oracle, postgresql. ORA-00904: "GETUTCDATE": invalid identifier
SELECT SYSDATETIME(), SYSUTCDATETIME(), GETUTCDATE()

-- CASE[limit]: ts-tablesample — MySQL has no TABLESAMPLE (row sampling is also non-deterministic); degraded to a documented carrier + warning (docs/03-unsupported.md). fails on mysql
CREATE TABLE t (id INT);
GO
SELECT * FROM t TABLESAMPLE (10 PERCENT)

-- CASE[fixed]: ts-top-with-ties — carry WITH TIES to PG/Oracle FETCH FIRST n ROWS WITH TIES (both tied rows returned); MySQL keeps LIMIT + a documented carrier.
SELECT TOP 1 WITH TIES x FROM (VALUES (1),(1),(2)) v(x) ORDER BY x

-- CASE[limit]: ts-trailing-eq — fails on mysql, oracle, postgresql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT IIF('a ' = 'a', 1, 0) AS r

-- CASE[limit]: ts-trailing-space-cmp — fails on mysql, oracle, postgresql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('eq', 'eq'),) target=(('ne', 'ne'),)
SELECT CASE WHEN 'a'='a ' THEN 'eq' ELSE 'ne' END, CASE WHEN 'a '='a' THEN 'eq' ELSE 'ne' END

-- CASE[fixed]: ts-translate — fails on mysql. (1305, 'FUNCTION unique_val_d6bc06ffba67.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r

-- CASE[fixed]: ts-trg-instead-delete — same BEFORE-row emulation; the depth guard returns OLD on DELETE (NEW is NULL there and would suppress the nested delete). Live: only id>0 rows deleted, exact T-SQL semantics (2026-07-24).
CREATE TABLE t (id INT);
GO
CREATE TRIGGER g ON t INSTEAD OF DELETE AS BEGIN DELETE FROM t WHERE id IN (SELECT id FROM deleted WHERE id>0); END

-- CASE[fixed]: ts-trig — ATN2/DEGREES/RADIANS/COT translate (Oracle ATAN2/ACOS-formula/(1/TAN)); the Oracle diff is decimal-precision only (180.0 vs 180; COT last digit). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT ATN2(1,1), DEGREES(PI()), RADIANS(180.0), COT(1)

-- CASE[fixed]: ts-trigger-on-view — PG INSTEAD OF triggers are row-level only: emitted FOR EACH ROW without REFERENCING, with the transition-table reads rowified to NEW/OLD references. Live: INSERT INTO v landed in t (2026-07-24).
CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t;
GO
CREATE TRIGGER trg ON v INSTEAD OF INSERT AS BEGIN INSERT INTO t SELECT id FROM inserted; END

-- CASE[fixed]: ts-trim-chars — fails on oracle. ORA-30001: trim set should have only one character
SELECT TRIM('x' FROM 'xxabcxx') AS r

-- CASE[fixed]: ts-try-catch-raiserror — fails on mysql, oracle, postgresql. PROCEDURE P compiled INVALID (line 8): PLS-00103: Encountered the symbol "RAISERROR" when 
CREATE PROCEDURE p AS BEGIN BEGIN TRY INSERT INTO t VALUES(1); END TRY BEGIN CATCH IF ERROR_NUMBER()=2627 RAISERROR('dup',16,1); END CATCH END

-- CASE[fixed]: ts-try-convert — TRY_CONVERT carried via the CastExpression safe flag: Oracle DEFAULT NULL ON CONVERSION ERROR, PG resolves the non-numeric literal to NULL. Live-verified NULL.
SELECT TRY_CONVERT(INT, 'abc') AS r

-- CASE[fixed]: ts-try-parse — fails on mysql, oracle, postgresql. ORA-00907: missing right parenthesis
SELECT TRY_PARSE('2020-01-01' AS DATE) AS r

-- CASE[fixed]: ts-tz-fns — fails on mysql, oracle, postgresql. ORA-00904: "TODATETIMEOFFSET": invalid identifier
SELECT SWITCHOFFSET(SYSDATETIMEOFFSET(),'+00:00'), TODATETIMEOFFSET(GETDATE(),'+05:00')

-- CASE[fixed]: ts-tz-offset — fails on mysql, oracle, postgresql. ORA-00904: "TODATETIMEOFFSET": invalid identifier
SELECT CONVERT(VARCHAR,SYSDATETIMEOFFSET(),121), SWITCHOFFSET(SYSDATETIMEOFFSET(),'+05:30'), TODATETIMEOFFSET(GETDATE(),'-08:00')

-- CASE[limit]: ts-tzoffset — fails on mysql, oracle, postgresql. DATENAME(TZOFFSET, SYSDATETIMEOFFSET()) is non-deterministic and tz-offset extraction is engine-specific (docs/03-unsupported.md §2).
SELECT DATENAME(TZOFFSET, SYSDATETIMEOFFSET()) AS r

-- CASE[fixed]: ts-unpivot — UNPIVOT rewritten to a UNION ALL (one arm per column, NULLs excluded); values verified equal on oracle/pg/mysql
SELECT id,col,val FROM (SELECT 1 id,10 a,20 b) s UNPIVOT (val FOR col IN (a,b)) u

-- CASE[limit]: ts-update-output — same as ts-insert-output: OUTPUT has no standalone Oracle equivalent (RETURNING needs INTO variables); the UPDATE runs and the OUTPUT is documented in a carrier (docs/03-unsupported.md). fails on oracle
CREATE TABLE t (id INT);
GO
CREATE INDEX ix ON t (id);
GO
UPDATE t SET id = id + 1 OUTPUT DELETED.id, INSERTED.id

-- CASE[fixed]: ts-waitfor-exec — WAITFOR DELAY now emits DBMS_SESSION.SLEEP (18c+, PUBLIC-granted; DBMS_LOCK.SLEEP needs a grant → PLS-00201), and EXEC of a Microsoft system procedure (sp_who) degrades to a documented carrier + warning off T-SQL. Live-compiled VALID on oracle/postgresql/mysql 2026-07-24.
CREATE PROCEDURE p AS BEGIN WAITFOR DELAY '00:00:01'; EXEC sp_who; END

-- CASE[fixed]: ts-while-break-continue — WHILE with BREAK/CONTINUE maps to MySQL LEAVE/ITERATE (labeled loop), Oracle EXIT/CONTINUE, PG equivalents; verified compile-valid on oracle/pg/mysql
CREATE PROCEDURE p AS BEGIN DECLARE @i INT = 0; WHILE @i < 5 BEGIN SET @i = @i + 1; IF @i = 3 CONTINUE; IF @i = 5 BREAK; END; END

-- CASE[fixed]: ts-while-loop — WHILE loop + SELECT COUNT INTO now compiles on all three: MySQL's table value constructor needs ROW() per row (VALUES ROW(1),ROW(2)); Oracle/PG were already valid. Verified compile-valid on oracle/pg/mysql
CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN SET @n -= 1; END; END

-- CASE[fixed]: tsql-drop2-100|START|ID — fails on postgresql. SILENT CLAUSE DROP: '100|START|IDENTITY' absent from valid postgresql output, no warning
CREATE TABLE t (id INT IDENTITY(100, 5))

-- CASE[fixed]: tsql-drop5-MEMORY_OPTIM — fails on mysql, oracle, postgresql. SILENT CLAUSE DROP: 'MEMORY_OPTIMIZED' absent from valid postgresql output, no warning
CREATE TABLE t (a INT) WITH (MEMORY_OPTIMIZED = ON)


-- CASE[fixed][class=func]: reda-ts-cast-int-trunc — fails on postgresql, mysql, oracle. T-SQL CAST(decimal AS INT) TRUNCATES toward zero (=2); PG/MySQL/Oracle CAST rounds (=3). Emitted as a plain CAST with no compensation and NO warning → different result. Live: tsql=2, pg=3, mysql=3, oracle=3.
SELECT CAST(2.9 AS INT) AS n

-- CASE[fixed][class=func]: reda-ts-addmonths-lastday — DATEADD(MONTH,1,<last-day-of-month>) does NOT stick to month-end in T-SQL/MySQL/PG (2020-02-29 -> 2020-03-29, keep the day and clamp only when shorter) but Oracle ADD_MONTHS forces the target month's last day (-> 2020-03-31). The Oracle month/quarter/year map now subtracts the extra stuck-past days (LEAST(day, target-month-length)) so the result matches the source, preserving time-of-day. Live-verified 2020-03-29 on all four engines (also mid-month, day31->30-day-month, leap-year, quarter, sub). Both pipelines.
SELECT DATEADD(MONTH, 1, CAST('2020-02-29' AS DATE)) AS d

-- CASE[fixed][class=lying-warning]: reda-ts-fk-on-update — fails on oracle. FK REFERENCES ... ON DELETE CASCADE ON UPDATE CASCADE: Oracle has no ON UPDATE referential action, so the ON UPDATE CASCADE clause is silently dropped from the emitted constraint with NO warning and no docs/03-unsupported note — a genuine semantic degrade shipped silently. (PG/MySQL preserve it.) BLUE: emit a lossy_conversion warning + UNIQUE carrier for the dropped ON UPDATE action into Oracle.
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (id INT PRIMARY KEY, pid INT REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE)

-- CASE[fixed][class=invalid]: reda-ts-output-into — fails on postgresql. The OUTPUT ... INTO <table> redirect form breaks the INSERTED-qualifier stripping that plain OUTPUT gets right (corpus ts-insert-output is green): PG emits 'RETURNING INSERTED.a', invalid ('missing FROM-clause entry for table "inserted"'), with NO warning. The INTO log(a) redirect (rows meant to be inserted into log) is also silently dropped. Live: plain OUTPUT INSERTED.a -> RETURNING a (valid); OUTPUT INSERTED.a INTO log -> RETURNING INSERTED.a (PG rejects). BLUE: strip the INSERTED/DELETED qualifier on the INTO path too, and warn on the dropped INTO redirect.
CREATE TABLE t (a INT); CREATE TABLE log (a INT); INSERT INTO t (a) OUTPUT INSERTED.a INTO log(a) VALUES (1)

-- CASE[fixed][class=invalid]: reda-ts-delete-join — the multi-table DELETE-join conversion is correct (PG USING / MySQL comma-list / Oracle WHERE EXISTS); this case ALSO exposed a comment-adjacent corruption: the ``-- CASE`` header prose contains the word "output" inside a quoted-SQL fragment, and the pre-parse OUTPUT text rule scanned it (guardrail 3 violation), interleaving comment text with the batch. Fixed by matching OUTPUT on the trivia-free code only (_extract_tsql_output).
CREATE TABLE t (id INT, v INT); CREATE TABLE s (id INT, flag INT); DELETE t FROM t INNER JOIN s ON t.id = s.id WHERE s.flag = 1

-- CASE[fixed][class=silent-drop]: reda-ts-pivot — fails on oracle, postgresql, mysql. The whole PIVOT operator is silently dropped: 'SELECT * FROM (SELECT dept,v FROM t) src PIVOT (SUM(v) FOR dept IN ([A],[B])) pv' becomes just 'SELECT * FROM (SELECT dept, v FROM t) src' with NO warning. Result set and shape change completely. Live (rows A/1,A/2,B/5): T-SQL PIVOT = one row (A=3,B=5); dropped = 3 raw rows (A,1),(A,2),(B,5). Oracle supports PIVOT natively (needs IN value xlate [A]->'A' AS A). BLUE: translate to Oracle PIVOT, and CASE-sum rewrite or a warned degrade on PG/MySQL — never drop it silently.
CREATE TABLE t (dept VARCHAR(1), v INT); SELECT * FROM (SELECT dept, v FROM t) src PIVOT (SUM(v) FOR dept IN ([A],[B])) pv

-- CASE[fixed][class=silent-drop]: reda-ts-for-json — fails on postgresql, oracle, mysql. FOR JSON PATH serializes the whole result set into ONE json scalar; the clause is silently dropped (SELECT a,b FROM t FOR JSON PATH -> SELECT a,b FROM t) with NO warning, unlike its sibling FOR XML (corpus ts-for-xml warns+carriers). Result set and shape change: live (rows (1,2),(3,4)) FOR JSON PATH = one row/one col '[{"a":1,"b":2},{"a":3,"b":4}]'; dropped = 2 rows x 2 cols. BLUE: give FOR JSON the same warned-degrade/rewrite (json_agg / JSON_ARRAYAGG) treatment as FOR XML.
CREATE TABLE t (a INT, b INT); SELECT a, b FROM t FOR JSON PATH

-- CASE[fixed][class=func]: reda-ts-substring-zero-start — fails on mysql, oracle. SUBSTRING(s, start, len) with start<1: T-SQL (and PG) count positions below 1 against the length -> SUBSTRING('hello',0,3)='he'. The call is passed through unchanged, but MySQL SUBSTRING(s,0,n) returns '' (position 0 = empty) and Oracle SUBSTR(s,0,n) treats 0 as 1 -> 'hel'. No warning. Live: tsql='he', pg='he', mysql='', oracle='hel'. BLUE: normalize start<1 to T-SQL semantics (clamp start to 1 and reduce len by 1-start) for MySQL/Oracle.
SELECT SUBSTRING('hello', 0, 3) AS r

-- CASE[fixed][class=func]: reda-ts-avg-int-trunc — fails on postgresql, mysql, oracle. T-SQL AVG over an INTEGER column returns an INTEGER (the average is truncated): AVG of (1,2) = 1. The call is passed through unchanged with no warning; PG/MySQL/Oracle AVG of integers returns a fractional value = 1.5. Live: tsql=1, pg=1.5, mysql=1.5. BLUE: to preserve T-SQL semantics, floor the AVG (or cast operands) when the argument is an integer type.
SELECT AVG(x) AS r FROM (VALUES (1), (2)) v(x)

-- CASE[fixed][class=composition]: reda-ts-cte-merge — fails on mysql, oracle. A leading CTE feeding a MERGE ('WITH src AS (...) MERGE INTO t USING src ...'). Each part is green alone: MERGE->MySQL upsert emits a valid INSERT...ON DUPLICATE KEY UPDATE, and a plain 'WITH src AS(...) SELECT' keeps the CTE. Combined, the MySQL upsert rewrite DROPS the WITH src CTE -> output 'INSERT ... SELECT ... FROM src' with src undefined (live: MySQL 1146 "Table 'src' doesn't exist"). Oracle keeps 'WITH src AS(...) MERGE' but Oracle forbids a leading WITH before MERGE (live: ORA-00928 SELECT keyword missing) with NO warning. BLUE: carry the CTE into the MySQL upsert's SELECT and push it into the Oracle MERGE USING subquery.
CREATE TABLE t (id INT PRIMARY KEY, v INT); CREATE TABLE s (id INT, v INT); WITH src AS (SELECT id, v FROM s) MERGE INTO t USING src ON t.id = src.id WHEN MATCHED THEN UPDATE SET t.v = src.v WHEN NOT MATCHED THEN INSERT (id, v) VALUES (src.id, src.v)

-- CASE[fixed][class=invalid]: reda-ts-alter-column-oracle — fails on oracle. T-SQL 'ALTER TABLE t ALTER COLUMN a BIGINT' (column type change) is emitted for Oracle as 'ALTER TABLE t ALTER COLUMN a SET DATA TYPE NUMBER', which Oracle rejects (ORA-01735 invalid ALTER TABLE option); Oracle needs 'MODIFY a NUMBER'. No warning. The MySQL-source MODIFY path is handled (corpus my-alter-modify) but the T-SQL ALTER COLUMN -> Oracle path is not. BLUE: route T-SQL ALTER COLUMN <type> to Oracle MODIFY like the MySQL path.
CREATE TABLE t (a INT); ALTER TABLE t ALTER COLUMN a BIGINT

-- CASE[fixed][class=consistency]: reda-ts-identity-insert — fails on postgresql, oracle, mysql. The SET IDENTITY_INSERT t ON ... INSERT ... SET IDENTITY_INSERT t OFF bracket (explicit-identity-value insert) is handled incoherently within one script: the ON degrades to a comment+warning, but the OFF is mangled to 'SET IDENTITY_INSERT = t AS OFF' and emitted as LIVE SQL with no warning — invalid on every target (PG 'syntax error at or near "AS"'). The identity-override on the INSERT is also not compensated. BLUE: recognize the whole IDENTITY_INSERT bracket, drop both SET statements (with one warning) or map to the target's explicit-identity mechanism (PG OVERRIDING SYSTEM VALUE); never emit the mangled SET.
CREATE TABLE t (id INT IDENTITY(1,1), v INT); SET IDENTITY_INSERT t ON; INSERT INTO t (id, v) VALUES (5, 10); SET IDENTITY_INSERT t OFF

-- CASE[fixed][class=func]: reda-ts-date-plus-int — fails on mysql, postgresql. T-SQL datetime + <int> ADDS DAYS: CAST('2020-01-01' AS DATETIME) + 1 = 2020-01-02. Emitted with no compensation, no warning. MySQL CAST(... AS DATETIME) + 1 does NUMERIC coercion -> 20200101000001 (live) — a wrong value, not a date. PG CAST(... AS TIMESTAMP) + 1 -> live ERROR 'operator does not exist: timestamp + integer' (invalid output). Oracle DATE + 1 is correct. Live: tsql=2020-01-02, mysql=20200101000001, pg=error, oracle=2020-01-02. BLUE: map datetime+int to DATE_ADD(.., INTERVAL n DAY) (MySQL) and .. + n * INTERVAL '1 day' (PG).
SELECT CAST('2020-01-01' AS DATETIME) + 1 AS d

-- CASE[fixed][class=silent-drop]: reda-ts-delete-top — fails on mysql, oracle, postgresql. DELETE TOP (2) FROM t WHERE a>0 limits the delete to 2 rows; the TOP (2) is silently dropped -> DELETE FROM t WHERE a>0 deletes ALL matching rows. Only the internal 'unread sqlglot arg tables on Delete' tripwire fires (about the alias, not TOP). MySQL supports DELETE ... LIMIT 2 natively (so this is a dropped supported clause); Oracle needs AND ROWNUM<=2, PG a ctid-subquery. BLUE: preserve the row cap per target.
CREATE TABLE t (a INT); DELETE TOP (2) FROM t WHERE a > 0

-- CASE[fixed][class=lying-warning]: reda-ts-like-escape — fails on postgresql, oracle, mysql. LIKE '...' ESCAPE '!' is SQL-standard and supported IDENTICALLY by PostgreSQL, Oracle and MySQL (all live-verified true), but the transpiler treats ESCAPE as an 'unmapped operator; no <engine> mapping' and comments out the ENTIRE statement with a (false) warning — losing a construct that is a pure identity passthrough. The warning misdescribes reality (a mapping exists) and the whole SELECT becomes a comment. BLUE: pass LIKE ... ESCAPE through unchanged on all three targets.
SELECT a FROM t WHERE b LIKE '%x!%y%' ESCAPE '!'

-- CASE[fixed][class=invalid]: reda-ts-datepart-weekday — fails on postgresql, oracle, mysql. T-SQL DATEPART(WEEKDAY, d) is mapped to EXTRACT(DAYOFWEEK FROM d), but NO engine has a DAYOFWEEK extract unit: live PG 'unit "dayofweek" not recognized', MySQL 1064 syntax error, Oracle ORA-00907. Invalid output on all three, no warning. BLUE: map to EXTRACT(DOW ...)+1 / DAYOFWEEK()/ the DOW rewrite already used for pg-extract-dow (and note DATEPART(WEEKDAY) is DATEFIRST-dependent, default Sunday=1).
SELECT DATEPART(WEEKDAY, CAST('2020-06-15' AS DATE)) AS r

-- CASE[fixed][class=invalid]: reda-ts-sequence-no-cycle — fails on oracle. T-SQL CREATE SEQUENCE ... NO MAXVALUE NO CYCLE (two-word forms, valid T-SQL and PG) is emitted verbatim into Oracle, but Oracle spells these NOMAXVALUE / NOCYCLE (one word): live ORA-03049 "SQL keyword 'NO' is not syntactically valid". No warning. BLUE: collapse NO MAXVALUE->NOMAXVALUE, NO MINVALUE->NOMINVALUE, NO CYCLE->NOCYCLE, NO CACHE->NOCACHE for the Oracle sequence emitter.
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 NO MAXVALUE NO CYCLE

-- CASE[fixed][class=invalid]: reda-ts-index-fillfactor-mysql — fails on mysql. T-SQL 'CREATE INDEX ix ON t (a) WITH (FILLFACTOR = 80)' into MySQL is mangled to 'CREATE INDEX ix ON t ((a) WITH (FILLFACTOR=80))' — the WITH option is folded INTO the index key-part parens — and emitted with NO warning: live MySQL 1064 syntax error near 'WITH (FILLFACTOR=80))'. The Oracle path correctly drops FILLFACTOR with a warning; the MySQL path does not. BLUE: MySQL has no FILLFACTOR — drop it with a lossy warning like the Oracle emitter, never fold it into the key list.
CREATE TABLE t (a INT); CREATE INDEX ix ON t (a) WITH (FILLFACTOR = 80)

-- CASE[fixed][class=lying-warning]: reda-ts-isnull-trunc — fails on postgresql, oracle, mysql. T-SQL ISNULL(x, y) returns a value of the FIRST argument's declared type: ISNULL(CAST(NULL AS VARCHAR(2)), 'abcdef') = 'ab' (truncated to VARCHAR(2)). It maps to COALESCE, which returns the full second value = 'abcdef' (COALESCE result type = highest precedence). The only warning is the internal 'unread sqlglot arg is_null on Coalesce' tripwire, which says nothing about the truncation; no docs entry. Live: tsql='ab', pg='abcdef'. Borderline func (clean live diff). BLUE: wrap the COALESCE in a CAST to the first arg's type to preserve ISNULL truncation.
SELECT ISNULL(CAST(NULL AS VARCHAR(2)), 'abcdef') AS r

-- CASE[fixed][class=crash]: reda-ts-datediff-quarter — fails on mysql, oracle, postgresql. DATEDIFF(QUARTER, d1, d2) (valid T-SQL, translatable) makes the emitter RAISE KeyError: 'QUARTER' inside _emit_date_diff (emit_functions.py ~235/254, the epoch dict {HOUR,MINUTE,SECOND}[unit]); DATEDIFF(WEEK,...) hits the same gap. The raise is swallowed by the transpile catch-all and surfaced as a '/* TRANSPILATION ERROR: QUARTER */' carrier that ships the untranslated T-SQL DATEDIFF (invalid on MySQL/Oracle). Note DATEADD(QUARTER)/DATEADD(WEEK) translate fine — only DATEDIFF's unit map is incomplete. BLUE: extend the DATEDIFF unit handling to QUARTER (3-month) and WEEK across all targets.
SELECT DATEDIFF(QUARTER, CAST('2020-01-01' AS DATE), CAST('2020-12-31' AS DATE)) AS r

-- CASE[fixed][class=func]: reda-ts-datalength-nchar — fails on postgresql, mysql. HOLE in [fixed] ts-binary-length: DATALENGTH->OCTET_LENGTH is right for VARBINARY/ASCII (byte length matches) but for an NVARCHAR (N'...') argument it silently diverges. T-SQL stores NVARCHAR as UTF-16 (2 bytes/char) so DATALENGTH(N'abc')=6; the N prefix is dropped and OCTET_LENGTH('abc')=3 (UTF-8). No warning. Live: tsql=6, pg=3. This is an encoding-dependent divergence (cf. the LENGTH bytes/chars limit) but shipped SILENTLY — it should warn (a documented [limit]) rather than emit a wrong value with no signal. BLUE: for DATALENGTH of an N-typed string, either double the char count for UTF-16 semantics or warn as a limit.
SELECT DATALENGTH(N'abc') AS r

-- CASE[fixed][class=invalid]: reda-ts-convert-numeric-style — fails on postgresql, mysql, oracle. CONVERT(INT, '26', 0) is a string->INT conversion (T-SQL third arg is a style code, ignored for INT) = 26. The transpiler assumes any 3-arg CONVERT is a DATE conversion and IGNORES the numeric target type, mapping it to TO_TIMESTAMP('26','MON DD YYYY…') (PG/Oracle) / STR_TO_DATE (MySQL). No warning. Live: tsql=26; PG ERROR 'invalid value "26" for "MON"'; MySQL=NULL. Same for CONVERT(DECIMAL(10,2),'26.5',2). BLUE: only treat the style as a date style when the target type is a date/time type; for numeric/char targets emit CAST and drop the style.
SELECT CONVERT(INT, '26', 0) AS r

-- CASE[fixed][class=consistency]: reda-ts-exec-swallow-next — fails on postgresql, oracle, mysql. When a degraded EXEC (a system proc like sp_rename with no target equivalent) is followed by another statement separated by ';' (not GO), the degrade carrier SWALLOWS the following statement: 'EXEC sp_rename ''t.a'',''b'',''COLUMN''; UPDATE t SET b = 1;' emits only a comment for BOTH, silently dropping the valid UPDATE (the warning names only sp_rename). With GO separation the UPDATE correctly survives. Root cause: the '; '-split path folds trailing statements into the degraded EXEC's carrier. BLUE: split ';'-separated statements before degrading, so only the sp_rename becomes a carrier and the UPDATE still transpiles.
EXEC sp_rename 't.a', 'b', 'COLUMN'; UPDATE t SET b = 1

-- CASE[fixed][class=invalid]: reda-ts-hex-literal-arith — fails on postgresql, oracle. A T-SQL binary/hex literal in arithmetic, 0x0A + 5, treats 0x0A as the integer 10 -> 15. It is emitted as a BINARY value into PG ('\x0A'::bytea + 5) and Oracle (HEXTORAW('0A') + 5), neither of which allows arithmetic on a binary type: live PG 'operator does not exist: bytea + integer', Oracle ORA-00932. No warning. (MySQL x'0A' + 5 = 15 is fine.) BLUE: when a 0x.. literal is used in a numeric context, fold it to its integer value.
SELECT 0x0A + 5 AS r

-- CASE[fixed][class=silent-drop]: reda-ts-setop-orderby — fails on postgresql, oracle, mysql. A trailing ORDER BY on a set operation (SELECT ... EXCEPT/UNION SELECT ... ORDER BY a) is silently DROPPED: PG/MySQL/Oracle all emit the bare set op with NO ORDER BY and NO warning, though every target supports ORDER BY on a UNION/EXCEPT/INTERSECT result. The ordered result set becomes unordered. BLUE: preserve the ORDER BY that applies to the whole set operation.
SELECT a FROM t EXCEPT SELECT a FROM s ORDER BY a

-- CASE[fixed][class=invalid]: reda-ts-select-into-identity — fails on postgresql, mysql, oracle. T-SQL's IDENTITY(type, seed, incr) function inside SELECT ... INTO adds an identity column to the new table. It is passed through unchanged; no other engine has an IDENTITY() function, so PG parses it as IDENTITY(<column int>, 1, 1) -> live 'column "int" does not exist'. No warning. BLUE: for SELECT..INTO with IDENTITY(), create the target with a real identity/serial/auto_increment column per target instead of leaking the function.
SELECT IDENTITY(INT, 1, 1) AS id INTO t2 FROM t

-- CASE[open][class=invalid]: red2-ts-datediff-weekday-unit — fails on mysql, oracle. T-SQL DATEDIFF with a unit that has no cross-engine mapping (WEEKDAY, ISO_WEEK) is passed through as a 3-arg DATEDIFF while the date args are rendered unquoted (2020-03-01), so the output slips the validity gate (parses as arithmetic) and ships invalid with NO warning: MySQL DATEDIFF(2020-03-01,'2020-01-01',WEEKDAY) -> 1582 "Incorrect parameter count in the call to native function DATEDIFF"; Oracle -> ORA-00904 "WEEKDAY": invalid identifier. (The datetime-literal variant DATEDIFF(MILLISECOND,'..00:00:00','..') is correctly gated+warned; only the bare-DATE-arg form escapes.) Source valid on tsql. BLUE: reject/degrade-with-warning unmapped DATEDIFF units instead of emitting a 3-arg passthrough; also quote the date args.
SELECT DATEDIFF(WEEKDAY, '2020-01-01', '2020-03-01') AS d

-- CASE[open][class=lying-warning]: red2-ts-json-value-false-unmap — fails on mysql, oracle, postgresql. T-SQL JSON_VALUE(doc, path) (sqlglot JSONExtractScalar) is degraded to a comment with the warning "unmapped operator JSONExtractScalar; no <engine> mapping. Statement preserved as a comment" — but MySQL and Oracle BOTH support JSON_VALUE(doc, path) natively (live: MySQL='1', Oracle='1' with the identical spelling) and PG has jsonb_path_query_first / ->>. The "no mapping" claim is false and the Oracle-SOURCE direction already maps JSON_VALUE correctly, so this is a T-SQL-source-only false-unmap that loses the whole statement behind a lying warning. BLUE: map JSONExtractScalar T-SQL->target (identity for MySQL/Oracle, jsonb path for PG) instead of degrading.
SELECT JSON_VALUE('{"a":1}', '$.a') AS v

-- CASE[open][class=lying-warning]: red2-ts-like-charclass — fails on postgresql, mysql, oracle. T-SQL LIKE supports a [A-C] character-class range that PG/MySQL/Oracle treat as literal characters. 'Bob' LIKE '[A-C]%' is TRUE on T-SQL ('B' in A..C) but the pattern is passed through unchanged; live result flips: tsql=1, pg=0, mysql=0, oracle=0 — a different result. The only warning emitted is the generic collation notice ("case/accent sensitivity and trailing-space handling ... the boolean result may differ") which mis-describes the loss: the divergence is the character-class pattern syntax, NOT collation. Lying/mis-attributed warning. BLUE: translate the T-SQL [..] LIKE character class (to POSIX/regex per target) or warn specifically about pattern-syntax loss.
SELECT CASE WHEN 'Bob' LIKE '[A-C]%' THEN 1 ELSE 0 END AS r

-- CASE[open][class=func]: red2-ts-datepart-week-iso — fails on postgresql, mysql, oracle. T-SQL DATEPART(WEEK, d) is the NON-ISO week (week 1 contains Jan 1; DATEFIRST-based), but it is mapped to the ISO-week functions on every target: PG EXTRACT(WEEK), MySQL WEEK(x, 3), Oracle TO_CHAR(x,'IW') are all ISO. Live for 2021-01-01: tsql=1, pg=53, mysql=53, oracle=53 (ISO week 53 of 2020). Different result, no warning. Note EXTRACT(WEEK) PG->targets is correctly ISO->ISO; the bug is only the T-SQL non-ISO source direction. BLUE: map DATEPART(WEEK) to each engine's non-ISO week (MySQL WEEK(x,0/2), Oracle TO_CHAR('WW')) — reserve the ISO functions for DATEPART(ISO_WEEK).
SELECT DATEPART(WEEK, '2021-01-01') AS w

-- CASE[open][class=invalid]: red2-ts-exec-named-param-mysql — fails on mysql. T-SQL EXEC proc @p = v (named parameter binding) is translated to MySQL as CALL proc(v_p = v), but MySQL CALL has no named-parameter syntax: v_p = v is parsed as a boolean expression over a column v_p -> live error 1054 "Unknown column 'v_id' in 'field list'". No warning. Positional EXEC proc 1, 0 correctly becomes CALL proc(1, 0); PG (name => v) and Oracle (name => v) named-arg forms are valid. Only the MySQL leg ships invalid. BLUE: MySQL CALL is positional-only — reorder the named args to the routine's parameter order (or degrade+warn) instead of emitting name = value.
EXEC dbo.get_rows @id = 1, @flag = 0

-- CASE[open][class=silent-drop]: red2-ts-raiserror-format-arg-drop — fails on postgresql, oracle. A RAISERROR with a printf-style format message and substitution arguments (RAISERROR('value is %d today', 16, 1, 42) => T-SQL raises "value is 42 today") loses the substitution: the message is emitted with the literal %d and the argument 42 is silently DROPPED, with NO warning. PG: RAISE EXCEPTION '%', 'value is %d today' (PG RAISE fully supports 'value is % today', 42); Oracle: RAISE_APPLICATION_ERROR(-20001, 'value is %d today'). The MySQL leg DOES warn ("original RAISERROR/THROW severity/state args dropped: 1, 42") — PG/Oracle are silently inconsistent. Source proc compiles on T-SQL. BLUE: translate the %d/%s substitution into PG RAISE format args / Oracle string concatenation instead of dropping them; at minimum warn like the MySQL leg.
CREATE PROCEDURE p AS
BEGIN
  RAISERROR('value is %d today', 16, 1, 42);
END

-- CASE[open][class=consistency]: red2-ts-set-swallow-next — fails on postgresql, mysql, oracle. A degraded SET option (SET NOCOUNT ON, SET DATEFORMAT dmy, ...) followed by a ';'-separated statement SWALLOWS that statement into its comment: "SET NOCOUNT ON; SELECT 1 AS a;" emits two commented-out lines and the valid SELECT 1 is DROPPED on every target, with only a "SET option commented out" warning that does not say a real statement was lost. SELECT 1 transpiles fine alone, and GO-separation (SET NOCOUNT ON / GO / SELECT 1) correctly keeps the SELECT. This is the direct neighbor of the fixed reda-ts-exec-swallow-next (EXEC-degrade swallowing the next statement) for the SET-degrade path — and SET NOCOUNT ON heads a huge fraction of real T-SQL scripts. BLUE: split ';'-separated statements before degrading the SET so only the SET becomes a carrier and the following statement still transpiles.
SET NOCOUNT ON; SELECT 1 AS a

-- CASE[fixed][class=invalid]: red2-ts-at-identity-passthrough — fails on postgresql, oracle. The T-SQL global @@IDENTITY (last identity inserted in the session) is passed through verbatim, unlike SCOPE_IDENTITY() which IS mapped (PG LASTVAL(), MySQL LAST_INSERT_ID()). SELECT @@IDENTITY -> live PG 'column "identity" does not exist' (parsed as @@ + IDENTITY), Oracle ORA-00936. No warning. (MySQL tolerates @@IDENTITY.) BLUE: map @@IDENTITY like SCOPE_IDENTITY (LASTVAL()/LAST_INSERT_ID()/sequence CURRVAL) or degrade+warn — the two identity globals should be handled symmetrically.
SELECT @@IDENTITY AS id

-- CASE[open][class=func]: red2-ts-trycast-mysql-zero — fails on mysql. T-SQL TRY_CAST/TRY_CONVERT returns NULL when the conversion fails (TRY_CAST('abc' AS INT) = NULL), but it is emitted to MySQL as a plain CAST('abc' AS SIGNED), which returns 0 (non-strict) rather than NULL — the TRY (null-on-failure) semantics are lost. Live: tsql=NULL, mysql=0. No warning. (PG constant-folds to NULL and Oracle uses CAST(.. DEFAULT NULL ON CONVERSION ERROR) — both correct; only the MySQL leg drops the TRY semantics.) Source valid on T-SQL. BLUE: wrap the MySQL cast so an unparseable value yields NULL (e.g. CASE WHEN value REGEXP '^-?[0-9]+$' THEN CAST(... ) ELSE NULL END, or NULLIF on the 0-default).
SELECT TRY_CAST('abc' AS INT) AS r
