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

-- CASE[open]: ts-after-update-trg — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT PRIMARY KEY, n INT, updated DATETIME);
GO
CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN UPDATE t SET updated = GETDATE() FROM t JOIN inserted i ON t.id = i.id; END

-- CASE[open]: ts-alter-add — fails on oracle. ORA-30649: missing DIRECTORY keyword
CREATE TABLE t (a INT); ALTER TABLE t ADD b NVARCHAR(10) NOT NULL DEFAULT 'x'

-- CASE[open]: ts-ascii-char — fails on mysql, oracle, postgresql. ORA-00904: "NCHAR": invalid identifier
SELECT ASCII('A'), CHAR(65), NCHAR(65)

-- CASE[open]: ts-at-time-zone — fails on mysql, oracle, postgresql. ORA-00902: invalid datatype
SELECT CAST('2020-01-01 10:00' AS DATETIME2) AT TIME ZONE 'UTC' AS r

-- CASE[open]: ts-cast-bit — fails on mysql, oracle. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT CAST(2 AS BIT) AS r

-- CASE[open]: ts-cast-trycast — fails on oracle, postgresql. ORA-01722: unable to convert string value containing 'x' to a number: 
SELECT CAST(123 AS VARCHAR(10)), TRY_CAST('x' AS INT), CONVERT(DATE, GETDATE())

-- CASE[open]: ts-choose — fails on mysql, oracle, postgresql. ORA-00904: "CHOOSE": invalid identifier
SELECT CHOOSE(2, 'a', 'b', 'c') AS r

-- CASE[open]: ts-collate — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT 'a' COLLATE Latin1_General_CS_AS AS r

-- CASE[open]: ts-concat-null — fails on mysql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[open]: ts-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', 'c') AS r

-- CASE[open]: ts-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT x FROM (VALUES (1),(2)) v(x); DECLARE @x INT; OPEN c; FETCH NEXT FROM c INTO @x; WHILE @@FETCH_STATUS = 0 BEGIN FETCH NEXT FROM c INTO @x; END; CLOSE c; DEALLOCATE c; END

-- CASE[open]: ts-dateadd — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT DATEADD(DAY, 7, '2020-01-01') AS r

-- CASE[open]: ts-datediff — fails on oracle. ORA-01861: literal does not match format string
SELECT DATEDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[open]: ts-datediff-big — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATEDIFF_BIG(SECOND, '2020-01-01', '2020-01-02') AS r

-- CASE[open]: ts-datetimefromparts — fails on mysql, oracle, postgresql. ORA-00904: "TIMESTAMP_FROM_PARTS": invalid identifier
SELECT DATETIMEFROMPARTS(2020, 6, 15, 10, 30, 0, 0) AS r

-- CASE[open]: ts-datetimeoffset — fails on mysql, oracle. ORA-03060: Data type TIME is invalid.
CREATE TABLE t (a DATETIMEOFFSET, b DATETIME2(7), c TIME(3))

-- CASE[open]: ts-eomonth — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT EOMONTH('2020-02-15') AS r

-- CASE[open]: ts-eomonth-nested — fails on oracle, postgresql. ORA-01861: literal does not match format string
SELECT DATEADD(MONTH, -1, EOMONTH('2020-03-01')) AS r

-- CASE[open]: ts-filtered-index — fails on mysql, oracle. ORA-02158: invalid CREATE INDEX option
CREATE TABLE t (a INT, b INT); CREATE NONCLUSTERED INDEX ix ON t (a) INCLUDE (b) WHERE a > 0

-- CASE[open]: ts-format-number — fails on mysql, oracle, postgresql. ORA-00904: "NUMBER_TO_STR": invalid identifier
SELECT FORMAT(1234.5, 'N2') AS r

-- CASE[open]: ts-insert-output — fails on mysql, oracle. ORA-00925: missing INTO keyword
CREATE TABLE t (id INT, n INT);
GO
INSERT INTO t (id, n) OUTPUT INSERTED.id VALUES (1, 5)

-- CASE[open]: ts-instead-of-insert — fails on mysql, postgresql. "t" is a table
CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id, n FROM inserted; END

-- CASE[open]: ts-json-value — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT JSON_VALUE('{"a":1}', '$.a')

-- CASE[open]: ts-lead-ignore-nulls — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT x, LEAD(x, 1) IGNORE NULLS OVER (ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: ts-len-trailing — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('3',),) target=(('6',),)
SELECT LEN('abc   ') AS r

-- CASE[open]: ts-log — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LOG(2.718), LOG10(100), POWER(2, 8)

-- CASE[open]: ts-math — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT CEILING(4.2), FLOOR(4.8), ROUND(4.555, 2), SQUARE(4)

-- CASE[open]: ts-merge — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE tgt (id INT PRIMARY KEY, n INT); MERGE tgt USING (VALUES (1, 5)) AS s(id, n) ON tgt.id = s.id WHEN MATCHED THEN UPDATE SET n = s.n WHEN NOT MATCHED THEN INSERT (id, n) VALUES (s.id, s.n);

-- CASE[open]: ts-money — fails on mysql, oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (price MONEY, small SMALLMONEY)

-- CASE[open]: ts-openjson — fails on mysql, oracle, postgresql. ORA-00904: "OPEN_J_S_O_N": invalid identifier
SELECT * FROM OPENJSON('[1,2,3]')

-- CASE[open]: ts-quotename — fails on mysql, oracle, postgresql. ORA-00904: "SPLIT_PART": invalid identifier
SELECT QUOTENAME('my table'), PARSENAME('a.b.c', 2)

-- CASE[open]: ts-recursive-cte — fails on mysql, postgresql. relation "r" does not exist
WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r

-- CASE[open]: ts-replicate-space — fails on oracle, postgresql. ORA-00904: "SPACE": invalid identifier
SELECT REPLICATE('ab', 3), SPACE(5), REVERSE('abc')

-- CASE[open]: ts-rowversion — fails on mysql, oracle, postgresql. ORA-00902: invalid datatype
CREATE TABLE t (row_ver ROWVERSION, flags BINARY(8))

-- CASE[open]: ts-select-into — fails on oracle. ORA-00905: missing keyword
CREATE TABLE src (id INT);
GO
SELECT id INTO dst FROM src

-- CASE[open]: ts-sequence-next — fails on mysql, oracle, postgresql. ORA-00904: "NEXT_VALUE_FOR": invalid identifier
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1;
GO
SELECT NEXT VALUE FOR seq

-- CASE[open]: ts-soundex-diff — fails on mysql, oracle, postgresql. ORA-00904: "DIFFERENCE": invalid identifier
SELECT SOUNDEX('Smith'), DIFFERENCE('Smith', 'Smyth')

-- CASE[open]: ts-str-plus-num — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('15',),) target=(('105',),)
SELECT '10' + 5 AS r

-- CASE[open]: ts-string-agg-within — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: ts-stuff — fails on mysql, oracle, postgresql. ORA-00904: "STUFF": invalid identifier
SELECT STUFF('abcdef', 2, 3, 'XY') AS r

-- CASE[open]: ts-sysdatetime — fails on mysql, oracle, postgresql. ORA-00904: "GETUTCDATE": invalid identifier
SELECT SYSDATETIME(), SYSUTCDATETIME(), GETUTCDATE()

-- CASE[open]: ts-table-variable — fails on oracle. ORA-06550: line 2, column 5:
DECLARE @t TABLE (id INT); INSERT INTO @t VALUES (1); SELECT * FROM @t

-- CASE[open]: ts-top-with-ties — fails on postgresql. SILENT LOSS: TOP n WITH TIES -> plain LIMIT n on PG/MySQL (ties dropped); on Oracle the ro
SELECT TOP 1 WITH TIES x FROM (VALUES (1),(1),(2)) v(x) ORDER BY x

-- CASE[open]: ts-trailing-eq — fails on mysql, oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT IIF('a ' = 'a', 1, 0) AS r

-- CASE[open]: ts-try-convert — fails on oracle, postgresql. ORA-01722: unable to convert string value containing 'a' to a number: 
SELECT TRY_CONVERT(INT, 'abc') AS r

-- CASE[open]: ts-view-check — fails on mysql, oracle, postgresql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t WHERE id > 0 WITH CHECK OPTION

-- CASE[open]: ts-while-loop — fails on mysql, oracle, postgresql. PROCEDURE P compiled INVALID (line 15): PLS-00103: Encountered the symbol "=" when expecti
CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN SET @n -= 1; END; END

