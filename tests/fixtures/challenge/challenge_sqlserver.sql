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

-- CASE[open]: ts-after-delete-count — fails on oracle. TRIGGER TRG compiled INVALID (line 4): PL/SQL: ORA-00942: table or view does not exist
CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t AFTER DELETE AS BEGIN DECLARE @c INT = (SELECT COUNT(*) FROM deleted); END

-- CASE[open]: ts-alter-add — fails on oracle. ORA-30649: missing DIRECTORY keyword
CREATE TABLE t (a INT); ALTER TABLE t ADD b NVARCHAR(10) NOT NULL DEFAULT 'x'

-- CASE[open]: ts-ascii-char — fails on mysql, oracle, postgresql. ORA-00904: "NCHAR": invalid identifier
SELECT ASCII('A'), CHAR(65), NCHAR(65)

-- CASE[open]: ts-at-time-zone — fails on oracle, postgresql. ORA-00902: invalid datatype
SELECT CAST('2020-01-01 10:00' AS DATETIME2) AT TIME ZONE 'UTC' AS r

-- CASE[open]: ts-binary-length — fails on mysql, oracle, postgresql. ORA-00902: invalid datatype
SELECT DATALENGTH(CAST('hello' AS VARBINARY(MAX))) AS r

-- CASE[open]: ts-bit-fns — fails on mysql, oracle, postgresql. ORA-00904: "SET_BIT": invalid identifier
SELECT GET_BIT(0x0A, 1), SET_BIT(0x0A, 0, 1)

-- CASE[open]: ts-bitops — fails on mysql. FUNC-DIFF: source=(('1', '7', '6', '-6'),) target=(('1', '7', '6', '18446744073709551616')
SELECT 5 & 3, 5 | 2, 5 ^ 3, ~5

-- CASE[open]: ts-cast-bit — fails on mysql, oracle. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT CAST(2 AS BIT) AS r

-- CASE[open]: ts-cast-bit2 — fails on oracle, postgresql. ORA-01722: unable to convert string value containing 't' to a number: 
SELECT CAST(1 AS BIT), CAST('true' AS BIT), CAST(0.5 AS BIT), TRY_CAST('x' AS BIT)

-- CASE[open]: ts-cast-date-int — fails on oracle, postgresql. ORA-00932: expression is of data type DATE, which is incompatible with expected data type 
SELECT CAST(GETDATE() AS INT) AS r

-- CASE[open]: ts-cast-int-datetime — fails on oracle, postgresql. ORA-00932: expression is of data type NUMBER, which is incompatible with expected data typ
SELECT CAST(1 AS DATETIME) AS r

-- CASE[open]: ts-cast-money — fails on oracle, postgresql. ORA-00902: invalid datatype
SELECT CAST(12.99 AS MONEY), CAST(12.99 AS SMALLMONEY), CONVERT(MONEY, '$12.99')

-- CASE[open]: ts-cast-suite — fails on mysql, oracle, postgresql. ORA-00906: missing left parenthesis
SELECT CAST('123' AS INT),CONVERT(INT,'123'),CONVERT(VARCHAR,123),TRY_CAST('x' AS INT),TRY_CONVERT(INT,'x'),PARSE('123' AS INT)

-- CASE[open]: ts-cast-trycast — fails on oracle, postgresql. ORA-01722: unable to convert string value containing 'x' to a number: 
SELECT CAST(123 AS VARCHAR(10)), TRY_CAST('x' AS INT), CONVERT(DATE, GETDATE())

-- CASE[open]: ts-checksum-agg — fails on mysql, oracle, postgresql. ORA-00904: "CHECKSUM_AGG": invalid identifier
SELECT CHECKSUM_AGG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: ts-checksum-fns — fails on mysql, oracle, postgresql. ORA-00909: invalid number of arguments
SELECT CHECKSUM('a','b'), BINARY_CHECKSUM('x'), HASHBYTES('MD5','x')

-- CASE[open]: ts-choose — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT CHOOSE(2, 'a', 'b', 'c') AS r

-- CASE[open]: ts-compress — fails on oracle, postgresql. ORA-00936: missing expression
SELECT COMPRESS('data') AS r

-- CASE[open]: ts-compress2 — fails on mysql, oracle, postgresql. ORA-00936: missing expression
SELECT COMPRESS('x'), DECOMPRESS(COMPRESS('x'))

-- CASE[open]: ts-concat-null — fails on mysql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[open]: ts-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', 'c') AS r

-- CASE[open]: ts-concatws2 — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS(',', 'a', NULL, 'b') AS r

-- CASE[open]: ts-cond-all — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT ISNULL(NULL,3),NULLIF(1,1),COALESCE(NULL,3),IIF(1=1,'y','n'),CHOOSE(1,'a','b'),CASE WHEN 1=1 THEN 1 END

-- CASE[open]: ts-conditional — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT IIF(1>0,'y','n'), CHOOSE(2,'a','b','c'), ISNULL(NULL,'x'), NULLIF(1,1)

-- CASE[open]: ts-continue-break — fails on mysql, oracle, postgresql. PROCEDURE P compiled INVALID (line 6): PLS-00103: Encountered the symbol "=" when expectin
CREATE PROCEDURE p AS BEGIN DECLARE @i INT=1; WHILE @i<=3 BEGIN SET @i+=1; IF @i=2 CONTINUE; IF @i=5 BREAK; END; END

-- CASE[open]: ts-convert-style — fails on oracle. ORA-01821: date format not recognized
SELECT CONVERT(VARCHAR,GETDATE(),101),CONVERT(VARCHAR,GETDATE(),112),CONVERT(VARCHAR,GETDATE(),120),CONVERT(VARCHAR,GETDATE(),126)

-- CASE[open]: ts-cube — fails on mysql, oracle, postgresql. ORA-00937: not a single-group group function
SELECT a,b,SUM(c) FROM (SELECT 1 a,2 b,3 c) t GROUP BY CUBE(a,b)

-- CASE[open]: ts-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT x FROM (VALUES (1),(2)) v(x); DECLARE @x INT; OPEN c; FETCH NEXT FROM c INTO @x; WHILE @@FETCH_STATUS = 0 BEGIN FETCH NEXT FROM c INTO @x; END; CLOSE c; DEALLOCATE c; END

-- CASE[open]: ts-date-bucket2 — fails on mysql, oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATE_BUCKET(MINUTE, 15, CAST('2020-01-01 00:07' AS DATETIME2))

-- CASE[open]: ts-dateadd — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('2020-02-29 00:00:00', '2020-01-02 00:00:00', '2020-02-29'),) target=(
SELECT DATEADD(MONTH,1,'2020-01-31'), DATEADD(DAY,1,'2020-01-01'), EOMONTH('2020-02-15')

-- CASE[open]: ts-datediff — fails on oracle. ORA-01861: literal does not match format string
SELECT DATEDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[open]: ts-datediff-big — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATEDIFF_BIG(SECOND, '2020-01-01', '2020-01-02') AS r

-- CASE[open]: ts-datetimefromparts — fails on mysql, oracle, postgresql. ORA-00904: "TIMESTAMP_FROM_PARTS": invalid identifier
SELECT DATETIMEFROMPARTS(2020, 6, 15, 10, 30, 0, 0) AS r

-- CASE[open]: ts-datetimeoffset — fails on mysql, oracle. ORA-03060: Data type TIME is invalid.
CREATE TABLE t (a DATETIMEOFFSET, b DATETIME2(7), c TIME(3))

-- CASE[open]: ts-default-nextval — fails on oracle, postgresql. ORA-04044: procedure, function, package, or type is not allowed here
CREATE SEQUENCE s AS INT START WITH 1;
GO
CREATE TABLE t (id INT DEFAULT (NEXT VALUE FOR s), a INT)

-- CASE[open]: ts-dttypes — fails on oracle. ORA-03060: Data type TIME is invalid.
CREATE TABLE t (a DATE, b TIME, c DATETIME, d DATETIME2, e SMALLDATETIME, f DATETIMEOFFSET, g TIME(3))

-- CASE[open]: ts-dyn-concat-loop — fails on oracle. PROCEDURE P compiled INVALID (line 6): PL/SQL: ORA-00942: table or view does not exist
CREATE PROCEDURE p AS BEGIN DECLARE @sql NVARCHAR(MAX) = N''; SELECT @sql = @sql + 'DROP TABLE ' + name + ';' FROM sys.tables; EXEC(@sql); END

-- CASE[open]: ts-dyn-count — fails on oracle. PROCEDURE P compiled INVALID (line 6): PLS-00201: identifier 'QUOTENAME' must be declared
CREATE PROCEDURE p @tbl NVARCHAR(128) AS BEGIN DECLARE @sql NVARCHAR(MAX) = N'SELECT COUNT(*) FROM ' + QUOTENAME(@tbl); EXEC(@sql); END

-- CASE[open]: ts-emoji-len — fails on mysql, postgresql. FUNC-DIFF: source=(('2',),) target=(('1',),)
SELECT LEN(N'😀') AS r

-- CASE[open]: ts-eomonth — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT EOMONTH('2020-02-15') AS r

-- CASE[open]: ts-eomonth-nested — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATEADD(MONTH, -1, EOMONTH('2020-03-01')) AS r

-- CASE[open]: ts-error-functions — fails on oracle. PROCEDURE P compiled INVALID (line 12): PL/SQL: ORA-00904: "ERROR_LINE": invalid identifie
CREATE PROCEDURE p AS BEGIN BEGIN TRY SELECT 1/0; END TRY BEGIN CATCH SELECT ERROR_MESSAGE(), ERROR_NUMBER(), ERROR_LINE(); END CATCH END

-- CASE[open]: ts-fmt-spec — fails on oracle. ORA-01821: date format not recognized
SELECT FORMAT(GETDATE(),'ddd MMM dd HH:mm:ss yyyy'),FORMAT(GETDATE(),'tt hh:mm'),FORMAT(GETDATE(),'D')

-- CASE[open]: ts-format-iso — fails on oracle. ORA-01821: date format not recognized
SELECT FORMAT(CAST('2020-06-15 14:30:45' AS DATETIME2), 'yyyy-MM-ddTHH:mm:ss') AS r

-- CASE[open]: ts-format-number — fails on mysql, oracle, postgresql. ORA-00904: "NUMBER_TO_STR": invalid identifier
SELECT FORMAT(1234.5, 'N2') AS r

-- CASE[open]: ts-formatmessage — fails on mysql, oracle, postgresql. ORA-00904: "FORMATMESSAGE": invalid identifier
SELECT FORMATMESSAGE('hi %s', 'x') AS r

-- CASE[open]: ts-gen-series-apply — fails on oracle, postgresql. ORA-00904: "GENERATE_SERIES": invalid identifier
SELECT value, ordinal FROM GENERATE_SERIES(1, 5) g CROSS APPLY (SELECT g.value AS ordinal) x

-- CASE[open]: ts-geography — fails on mysql, oracle, postgresql. ORA-00904: "GEOGRAPHY"."TOSTRING": invalid identifier
SELECT GEOGRAPHY::Point(47.6, -122.3, 4326).ToString() AS r

-- CASE[open]: ts-hash-all — fails on mysql, postgresql. SILENT: source literal(s) ["'SHA2_512'"] absent from valid output, no warning
SELECT HASHBYTES('SHA2_512', 'abc'), CHECKSUM('abc')

-- CASE[open]: ts-hexcast — fails on oracle, postgresql. ORA-00906: missing left parenthesis
SELECT CONVERT(VARCHAR,0x48656C6C6F),CONVERT(VARBINARY,'Hello',0)

-- CASE[open]: ts-host-db — fails on mysql, oracle, postgresql. ORA-00904: "DB_NAME": invalid identifier
SELECT HOST_NAME(), DB_NAME(), SUSER_SNAME()

-- CASE[open]: ts-identity-funcs — fails on mysql, oracle, postgresql. ORA-00936: missing expression
SELECT SCOPE_IDENTITY(), @@IDENTITY, IDENT_CURRENT('t')

-- CASE[open]: ts-inline-index2 — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (id INT, name VARCHAR(50), INDEX ix_name NONCLUSTERED (name))

-- CASE[open]: ts-insert-output — fails on oracle. ORA-00925: missing INTO keyword
CREATE TABLE t (id INT, n INT);
GO
INSERT INTO t (id, n) OUTPUT INSERTED.id VALUES (1, 5)

-- CASE[open]: ts-instead-of-insert — fails on postgresql. "t" is a table
CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id, n FROM inserted; END

-- CASE[open]: ts-is-fns — fails on mysql, oracle, postgresql. ORA-00904: "ISJSON": invalid identifier
SELECT ISNUMERIC('12.3'), ISDATE('2020-01-01'), ISJSON('{}')

-- CASE[open]: ts-len-trailing — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('3',),) target=(('6',),)
SELECT LEN('abc   ') AS r

-- CASE[open]: ts-merge-full — fails on oracle, postgresql. ORA-02000: missing THEN keyword
CREATE TABLE tgt (id INT PRIMARY KEY, n INT); CREATE TABLE src (id INT, n INT);
GO
MERGE tgt USING src ON tgt.id = src.id WHEN MATCHED AND src.n > 0 THEN UPDATE SET n = src.n WHEN MATCHED THEN DELETE WHEN NOT MATCHED BY TARGET THEN INSERT (id, n) VALUES (src.id, src.n) WHEN NOT MATCHED BY SOURCE THEN DELETE;

-- CASE[open]: ts-metadata-funcs — fails on mysql, oracle, postgresql. ORA-00904: "OBJECT_ID": invalid identifier
SELECT COL_LENGTH('t', 'c'), OBJECT_ID('t')

-- CASE[open]: ts-money — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (price MONEY, small SMALLMONEY)

-- CASE[open]: ts-money-arith — fails on postgresql. FUNC-DIFF: source=(('12.8',),) target=(('$12.80',),)
SELECT CAST(10.5 AS MONEY) + CAST(2.3 AS MONEY) AS r

-- CASE[open]: ts-month-overflow — fails on mysql. FUNC-DIFF: source=(('2020-02-29 00:00:00',),) target=(('2020-02-29',),)
SELECT DATEADD(MONTH, 1, '2020-01-31') AS r

-- CASE[open]: ts-nchar-hex — fails on mysql, oracle, postgresql. ORA-00904: "NCHAR": invalid identifier
SELECT NCHAR(0x1F600) AS r

-- CASE[open]: ts-nolock-hint — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id INT);
GO
SELECT * FROM t WITH (NOLOCK)

-- CASE[open]: ts-now-fns — fails on mysql, oracle, postgresql. ORA-00904: "CURRENT_TIMESTAMP_L_T_Z": invalid identifier
SELECT GETDATE(), SYSDATETIME(), CURRENT_TIMESTAMP, GETUTCDATE(), SYSDATETIMEOFFSET()

-- CASE[open]: ts-openjson — fails on oracle, postgresql. ORA-00904: "OPEN_J_S_O_N": invalid identifier
SELECT * FROM OPENJSON('[1,2,3]')

-- CASE[open]: ts-order-strings — fails on mysql. FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), 
SELECT x FROM (VALUES ('banana'),('Apple'),('cherry'),('Banana')) v(x) ORDER BY x

-- CASE[open]: ts-patindex — fails on mysql, oracle, postgresql. ORA-00904: "PATINDEX": invalid identifier
SELECT PATINDEX('%[0-9]%', 'abc123') AS r

-- CASE[open]: ts-quotename — fails on mysql, oracle, postgresql. ORA-00904: "SPLIT_PART": invalid identifier
SELECT QUOTENAME('my table'), PARSENAME('a.b.c', 2)

-- CASE[open]: ts-realworld-audit — fails on mysql, oracle, postgresql. PROCEDURE LOG_IT compiled INVALID (line 11): PLS-00103: Encountered the symbol ")" when ex
CREATE TABLE dbo.audit (id INT IDENTITY, msg NVARCHAR(MAX), ts DATETIME2);
GO
CREATE PROCEDURE dbo.log_it @msg NVARCHAR(MAX) AS BEGIN BEGIN TRY INSERT INTO dbo.audit (msg, ts) VALUES (@msg, SYSDATETIME()); END TRY BEGIN CATCH THROW; END CATCH END

-- CASE[open]: ts-recursion-limit — fails on mysql, oracle, postgresql. ORA-32039: missing column alias list in recursive WITH clause element N
WITH n AS (SELECT 1 v UNION ALL SELECT v+1 FROM n WHERE v<100) SELECT COUNT(*) FROM n OPTION (MAXRECURSION 1000)

-- CASE[open]: ts-recursive-cte — fails on mysql, postgresql. relation "r" does not exist
WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r

-- CASE[open]: ts-replicate-space — fails on oracle, postgresql. ORA-00904: "SPACE": invalid identifier
SELECT REPLICATE('ab', 3), SPACE(5), REVERSE('abc')

-- CASE[open]: ts-rowversion — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (row_ver ROWVERSION, flags BINARY(8))

-- CASE[open]: ts-scroll-cursor — fails on mysql, oracle, postgresql. PROCEDURE P compiled INVALID (line 9): PLS-00103: Encountered the symbol ";" when expectin
CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR LOCAL SCROLL FOR SELECT 1; OPEN c; FETCH LAST FROM c; CLOSE c; DEALLOCATE c; END

-- CASE[open]: ts-select-into — fails on oracle. ORA-00905: missing keyword
CREATE TABLE src (id INT);
GO
SELECT id INTO dst FROM src

-- CASE[open]: ts-select-into-temp — fails on oracle. ORA-00905: missing keyword
SELECT id INTO #t2 FROM (SELECT 1 id) s;
SELECT * FROM #t2;

-- CASE[open]: ts-seq-use — fails on oracle, postgresql. ORA-00904: "NEXT_VALUE_FOR": invalid identifier
CREATE SEQUENCE s START WITH 1; SELECT NEXT VALUE FOR s

-- CASE[open]: ts-sequence-next — fails on oracle, postgresql. ORA-00904: "NEXT_VALUE_FOR": invalid identifier
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1;
GO
SELECT NEXT VALUE FOR seq

-- CASE[open]: ts-session-ctx — fails on mysql, oracle, postgresql. ORA-00904: "CURRENT_TRANSACTION_ID": invalid identifier
SELECT SESSION_CONTEXT(N'k'), CURRENT_TRANSACTION_ID()

-- CASE[open]: ts-soundex-diff — fails on mysql, oracle, postgresql. ORA-00904: "DIFFERENCE": invalid identifier
SELECT SOUNDEX('Smith'), DIFFERENCE('Smith', 'Smyth')

-- CASE[open]: ts-soundex3 — fails on mysql, oracle, postgresql. ORA-00904: "DIFFERENCE": invalid identifier
SELECT SOUNDEX('Smith'),DIFFERENCE('Smith','Smyth')

-- CASE[open]: ts-spectypes — fails on oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (a BINARY(16), b VARBINARY(MAX), c IMAGE, d BIT, e UNIQUEIDENTIFIER, f XML, g SQL_VARIANT, h ROWVERSION, i HIERARCHYID, j GEOGRAPHY)

-- CASE[open]: ts-spid-version — fails on mysql, oracle, postgresql. ORA-00936: missing expression
SELECT @@SPID, @@VERSION

-- CASE[open]: ts-split-agg — fails on oracle, postgresql. ORA-00904: "STRING_SPLIT": invalid identifier
SELECT STRING_AGG(value,',') FROM STRING_SPLIT('a,b,c',',')

-- CASE[open]: ts-st-distance — fails on oracle, postgresql. DPY-4010: a bind variable replacement value for placeholder ":POINT" was not provided
SELECT geometry::Point(0,0,0).STDistance(geometry::Point(3,4,0)) AS r

-- CASE[open]: ts-str-func — fails on mysql, oracle, postgresql. ORA-00904: "STR": invalid identifier
SELECT STR(3.14, 6, 2) AS r

-- CASE[open]: ts-str-plus-num — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('15',),) target=(('105',),)
SELECT '10' + 5 AS r

-- CASE[open]: ts-stragg-within — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT STRING_AGG(x,',') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[open]: ts-stragg-within2 — fails on mysql, oracle. ORA-00906: missing left parenthesis
CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); CREATE TABLE data (data NVARCHAR(MAX));
GO
SELECT STRING_AGG(CAST(n AS VARCHAR), ',') WITHIN GROUP (ORDER BY id) FROM t

-- CASE[open]: ts-string-agg-within — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: ts-string-fns2 — fails on mysql, oracle, postgresql. ORA-00904: "STUFF": invalid identifier
SELECT STRING_ESCAPE('a"b', 'json'), STUFF('abcdef',2,3,'XYZ')

-- CASE[open]: ts-string-fns3 — fails on mysql, oracle, postgresql. ORA-00904: "QUOTENAME": invalid identifier
SELECT TRANSLATE('abc','ab','xy'), REPLICATE('ab',3), QUOTENAME('a]b')

-- CASE[open]: ts-string-split2 — fails on oracle, postgresql. ORA-00904: "STRING_SPLIT": invalid identifier
SELECT * FROM STRING_SPLIT('a,b,c', ',') WHERE value <> 'b'

-- CASE[open]: ts-stuff — fails on mysql, oracle, postgresql. ORA-00904: "STUFF": invalid identifier
SELECT STUFF('abcdef', 2, 3, 'XY') AS r

-- CASE[open]: ts-sysdatetime — fails on mysql, oracle, postgresql. ORA-00904: "GETUTCDATE": invalid identifier
SELECT SYSDATETIME(), SYSUTCDATETIME(), GETUTCDATE()

-- CASE[open]: ts-tablesample — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id INT);
GO
SELECT * FROM t TABLESAMPLE (10 PERCENT)

-- CASE[open]: ts-top-with-ties — fails on postgresql. SILENT LOSS: TOP n WITH TIES -> plain LIMIT n on PG/MySQL (ties dropped); on Oracle the ro
SELECT TOP 1 WITH TIES x FROM (VALUES (1),(1),(2)) v(x) ORDER BY x

-- CASE[open]: ts-trailing-eq — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT IIF('a ' = 'a', 1, 0) AS r

-- CASE[open]: ts-translate — fails on mysql. (1305, 'FUNCTION unique_val_d6bc06ffba67.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r

-- CASE[open]: ts-trg-instead-delete — fails on postgresql. "t" is a table
CREATE TABLE t (id INT);
GO
CREATE TRIGGER g ON t INSTEAD OF DELETE AS BEGIN DELETE FROM t WHERE id IN (SELECT id FROM deleted WHERE id>0); END

-- CASE[open]: ts-trig — fails on oracle. ORA-00904: "COT": invalid identifier
SELECT ATN2(1,1), DEGREES(PI()), RADIANS(180.0), COT(1)

-- CASE[open]: ts-trigger-on-view — fails on postgresql. INSTEAD OF triggers must be FOR EACH ROW
CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t;
GO
CREATE TRIGGER trg ON v INSTEAD OF INSERT AS BEGIN INSERT INTO t SELECT id FROM inserted; END

-- CASE[open]: ts-trim-chars — fails on oracle. ORA-30001: trim set should have only one character
SELECT TRIM('x' FROM 'xxabcxx') AS r

-- CASE[open]: ts-try-convert — fails on oracle, postgresql. ORA-01722: unable to convert string value containing 'a' to a number: 
SELECT TRY_CONVERT(INT, 'abc') AS r

-- CASE[open]: ts-try-parse — fails on mysql, oracle, postgresql. ORA-00907: missing right parenthesis
SELECT TRY_PARSE('2020-01-01' AS DATE) AS r

-- CASE[open]: ts-tz-fns — fails on mysql, oracle, postgresql. ORA-00904: "TODATETIMEOFFSET": invalid identifier
SELECT SWITCHOFFSET(SYSDATETIMEOFFSET(),'+00:00'), TODATETIMEOFFSET(GETDATE(),'+05:00')

-- CASE[open]: ts-tzoffset — fails on mysql, oracle, postgresql. ORA-00904: "CURRENT_TIMESTAMP_L_T_Z": invalid identifier
SELECT DATENAME(TZOFFSET, SYSDATETIMEOFFSET()) AS r

-- CASE[open]: ts-unpivot — fails on mysql, oracle, postgresql. ORA-00904: "VAL": invalid identifier
SELECT id,col,val FROM (SELECT 1 id,10 a,20 b) s UNPIVOT (val FOR col IN (a,b)) u

-- CASE[open]: ts-update-output — fails on oracle. ORA-00925: missing INTO keyword
CREATE TABLE t (id INT);
GO
CREATE INDEX ix ON t (id);
GO
UPDATE t SET id = id + 1 OUTPUT DELETED.id, INSERTED.id

-- CASE[open]: ts-waitfor-exec — fails on oracle. PROCEDURE P compiled INVALID (line 4): PLS-00201: identifier 'DBMS_LOCK' must be declared
CREATE PROCEDURE p AS BEGIN WAITFOR DELAY '00:00:01'; EXEC sp_who; END

-- CASE[open]: ts-while-break-continue — fails on mysql, oracle, postgresql. PROCEDURE P compiled INVALID (line 11): PLS-00201: identifier 'BREAK' must be declared
CREATE PROCEDURE p AS BEGIN DECLARE @i INT = 0; WHILE @i < 5 BEGIN SET @i = @i + 1; IF @i = 3 CONTINUE; IF @i = 5 BREAK; END; END

-- CASE[open]: ts-while-loop — fails on mysql, oracle, postgresql. PROCEDURE P compiled INVALID (line 15): PLS-00103: Encountered the symbol "=" when expecti
CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN SET @n -= 1; END; END

-- CASE[open]: tsql-drop2-100|START|ID — fails on postgresql. SILENT CLAUSE DROP: '100|START|IDENTITY' absent from valid postgresql output, no warning
CREATE TABLE t (id INT IDENTITY(100, 5))

-- CASE[open]: tsql-drop5-MEMORY_OPTIM — fails on mysql, oracle, postgresql. SILENT CLAUSE DROP: 'MEMORY_OPTIMIZED' absent from valid postgresql output, no warning
CREATE TABLE t (a INT) WITH (MEMORY_OPTIMIZED = ON)

