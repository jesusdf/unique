-- T-SQL-source corpus (swept: tsql -> {oracle, postgresql, mysql}).
-- Table-less or self-contained; exercises T-SQL idioms that must be translated.
-- @@@
SELECT GETDATE() AS now
-- @@@
SELECT SYSDATETIME() AS now2
-- @@@
SELECT LEN('hello') AS l
-- @@@
SELECT ISNULL(NULL, 1) AS c
-- @@@
SELECT SUBSTRING('hello', 1, 3) AS s
-- @@@
SELECT CHARINDEX('l', 'hello') AS p
-- @@@
SELECT 'a' + 'b' + 'c' AS concatenated
-- @@@
SELECT IIF(1 = 1, 'y', 'n') AS iif
-- @@@
SELECT DATEADD(DAY, 7, CAST('2024-01-01' AS DATE)) AS d
-- @@@
SELECT DATEDIFF(DAY, CAST('2024-01-01' AS DATE), CAST('2024-01-08' AS DATE)) AS diff
-- @@@
SELECT CAST(GETDATE() AS DATE) AS today
-- @@@
SELECT CONVERT(VARCHAR(20), 12345) AS str
-- @@@
SELECT TOP 2 x FROM (SELECT 1 AS x UNION SELECT 2 UNION SELECT 3) t ORDER BY x
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t ORDER BY x OFFSET 1 ROWS FETCH NEXT 1 ROWS ONLY
-- @@@
SELECT ROW_NUMBER() OVER (ORDER BY x) AS rn, x FROM (SELECT 1 AS x UNION SELECT 2) t
-- @@@
CREATE TABLE corpus_tsql_types (
    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    name NVARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) DEFAULT 0,
    flag BIT DEFAULT 0,
    notes NVARCHAR(MAX) NULL,
    payload VARBINARY(MAX) NULL,
    created DATETIME2 DEFAULT SYSDATETIME()
)
-- @@@
CREATE TABLE corpus_tsql_dml (id INT PRIMARY KEY, n INT);
INSERT INTO corpus_tsql_dml (id, n) VALUES (1, 10), (2, 20);
UPDATE corpus_tsql_dml SET n = n + 1 WHERE id = 1;
DELETE FROM corpus_tsql_dml WHERE id = 2;
