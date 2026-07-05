-- Portable corpus: statements valid in T-SQL, PostgreSQL and MySQL as a source
-- (swept from each). Every entry is table-less or self-contained, so the
-- transpiled output executes on the target without any seeded schema.
--
-- Entries are separated by a line that is exactly "-- @@@". Add the minimal
-- statement that reproduces a bug here whenever one is found.
-- @@@
SELECT 1
-- @@@
SELECT 1 + 2 * 3 AS arith
-- @@@
SELECT 'hello world' AS greeting
-- @@@
SELECT NULL AS n
-- @@@
-- a leading line comment must survive transpilation
SELECT 42 AS answer
-- @@@
SELECT CASE WHEN 1 = 1 THEN 'yes' ELSE 'no' END AS verdict
-- @@@
SELECT COALESCE(NULL, NULL, 7) AS c
-- @@@
SELECT NULLIF(1, 1) AS n
-- @@@
SELECT CAST('123' AS INT) AS i
-- @@@
SELECT CAST(1 AS DECIMAL(10, 2)) AS d
-- @@@
SELECT ABS(-5) AS a
-- @@@
SELECT UPPER('abc') AS u, LOWER('ABC') AS l
-- @@@
SELECT 1 AS x UNION SELECT 2
-- @@@
SELECT 1 AS x UNION ALL SELECT 1
-- @@@
SELECT COUNT(*) AS c FROM (SELECT 1 AS x UNION SELECT 2) t
-- @@@
WITH cte AS (SELECT 1 AS x) SELECT x FROM cte
-- @@@
SELECT x, COUNT(*) AS c FROM (SELECT 1 AS x UNION ALL SELECT 1) t GROUP BY x
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t WHERE x > 1 ORDER BY x
-- @@@
SELECT MAX(x) AS mx, MIN(x) AS mn FROM (SELECT 1 AS x UNION SELECT 9) t
-- @@@
SELECT t.x FROM (SELECT 1 AS x) t INNER JOIN (SELECT 1 AS y) u ON t.x = u.y
-- @@@
SELECT 2 INTERSECT SELECT 2
-- @@@
SELECT 1 AS x UNION SELECT 2 EXCEPT SELECT 2
-- @@@
SELECT 3 EXCEPT SELECT 2 EXCEPT SELECT 1
