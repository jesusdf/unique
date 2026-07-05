-- SQLite-source corpus (import-only; swept: sqlite -> {tsql, oracle, postgresql, mysql}).
-- @@@
SELECT 1 AS x
-- @@@
SELECT IFNULL(NULL, 1) AS c
-- @@@
SELECT SUBSTR('hello', 1, 3) AS s
-- @@@
SELECT 'a' || 'b' AS concatenated
-- @@@
SELECT LENGTH('hello') AS l
-- @@@
SELECT DATE('now') AS today
-- @@@
SELECT x FROM (SELECT 1 AS x UNION SELECT 2) t ORDER BY x LIMIT 1
-- @@@
CREATE TABLE corpus_lite_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) DEFAULT 0,
    notes TEXT NULL,
    payload BLOB NULL,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
