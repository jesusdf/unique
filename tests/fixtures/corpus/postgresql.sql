-- PostgreSQL-source corpus (swept: postgresql -> {tsql, oracle, mysql}).
-- @@@
SELECT NOW() AS now
-- @@@
SELECT CURRENT_DATE AS today
-- @@@
SELECT 'a' || 'b' AS concatenated
-- @@@
SELECT LENGTH('hello') AS l
-- @@@
SELECT POSITION('l' IN 'hello') AS p
-- @@@
SELECT SUBSTRING('hello' FROM 1 FOR 3) AS s
-- @@@
SELECT CAST(1 AS BOOLEAN) AS b
-- @@@
SELECT 5 % 2 AS m
-- @@@
SELECT GREATEST(1, 2, 3) AS g, LEAST(1, 2, 3) AS le
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t ORDER BY x LIMIT 1
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t ORDER BY x LIMIT 1 OFFSET 1
-- @@@
SELECT RANK() OVER (ORDER BY x) AS r, x FROM (SELECT 1 AS x UNION SELECT 2) t
-- @@@
CREATE TABLE corpus_pg_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) DEFAULT 0,
    flag BOOLEAN DEFAULT FALSE,
    notes TEXT NULL,
    payload BYTEA NULL,
    created TIMESTAMP DEFAULT NOW()
)
-- @@@
CREATE TABLE corpus_pg_dml (id INT PRIMARY KEY, n INT);
INSERT INTO corpus_pg_dml (id, n) VALUES (1, 10), (2, 20);
UPDATE corpus_pg_dml SET n = n + 1 WHERE id = 1;
