-- MySQL-source corpus (swept: mysql -> {tsql, oracle, postgresql}).
-- @@@
-- @xfail: oracle tsql  # MySQL NOW() not mapped to SYSTIMESTAMP / GETDATE()
SELECT NOW() AS now
-- @@@
-- @xfail: oracle postgresql tsql  # MySQL CURDATE() not mapped
SELECT CURDATE() AS today
-- @@@
SELECT CONCAT('a', 'b', 'c') AS concatenated
-- @@@
SELECT IFNULL(NULL, 1) AS c
-- @@@
SELECT LENGTH('hello') AS l
-- @@@
SELECT LOCATE('l', 'hello') AS p
-- @@@
SELECT SUBSTRING('hello', 1, 3) AS s
-- @@@
SELECT DATE_ADD(CAST('2024-01-01' AS DATE), INTERVAL 7 DAY) AS d
-- @@@
-- @xfail: oracle postgresql tsql  # MySQL 2-arg DATEDIFF(a,b) not translated
SELECT DATEDIFF(CAST('2024-01-08' AS DATE), CAST('2024-01-01' AS DATE)) AS diff
-- @@@
SELECT 10 MOD 3 AS m
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t ORDER BY x LIMIT 1
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t ORDER BY x LIMIT 1, 1
-- @@@
CREATE TABLE corpus_my_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) DEFAULT 0,
    flag TINYINT(1) DEFAULT 0,
    notes TEXT NULL,
    payload BLOB NULL,
    created DATETIME DEFAULT CURRENT_TIMESTAMP
)
-- @@@
CREATE TABLE corpus_my_dml (id INT PRIMARY KEY, n INT);
INSERT INTO corpus_my_dml (id, n) VALUES (1, 10), (2, 20);
UPDATE corpus_my_dml SET n = n + 1 WHERE id = 1;
