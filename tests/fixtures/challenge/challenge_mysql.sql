-- Challenge fixtures — MySQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: my-accent-eq — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'Ä' = 'A' AS r

-- CASE[open]: my-aes — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(AES_ENCRYPT('data', 'key')) AS r

-- CASE[open]: my-alter-modify — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S
CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT

-- CASE[open]: my-ascii-empty — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT ASCII('') AS r

-- CASE[open]: my-avg-int — fails on tsql. FUNC-DIFF: source=(('1.5',),) target=(('1',),)
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-base64 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO
SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')

-- CASE[open]: my-benchmark — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BE
SELECT BENCHMARK(1, 1+1) AS r

-- CASE[open]: my-bit-agg — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_XOR(x), BIT_OR(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-bit-count — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_COUNT(255) AS r

-- CASE[open]: my-bitnot — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('18446744073709551616',),) target=(('-1',),)
SELECT ~0 AS r

-- CASE[open]: my-bool-char — fails on postgresql. FUNC-DIFF: source=(('1',),) target=(('t',),)
SELECT CAST((1=1) AS CHAR) AS r

-- CASE[open]: my-cast-convert — fails on oracle, postgresql, tsql. (243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:
SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)

-- CASE[open]: my-cast-datetime — fails on oracle. ORA-01843: An invalid month was specified.
SELECT CAST('2020-01-01' AS DATETIME) AS r

-- CASE[open]: my-cast-hex-char — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(0xFF AS CHAR) AS r

-- CASE[open]: my-cast-int — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT CAST(2.7 AS SIGNED) AS r

-- CASE[open]: my-cast-num-char — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(1234.5 AS CHAR) AS r

-- CASE[open]: my-cast-time — fails on oracle. DPY-3006: Oracle data type 178 is not supported
SELECT CAST('10:00:00' AS TIME) AS r

-- CASE[open]: my-change-column — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'CHANGE'.DB-Lib error message 20018, severity 15:\nGeneral S
CREATE TABLE t (a INT, b INT); ALTER TABLE t CHANGE a x INT

-- CASE[open]: my-char-256 — fails on oracle, postgresql. FUNC-DIFF: source=(('0100',),) target=(('\x01\x00',),)
SELECT CHAR(256) AS r

-- CASE[open]: my-char-unicode — fails on postgresql. FUNC-DIFF: source=(('NULL',),) target=(('μ',),)
SELECT CHAR(956 USING utf8mb4) AS r

-- CASE[open]: my-coalesce-empty — fails on oracle. FUNC-DIFF: source=(('1',),) target=(('NULL',),)
SELECT COALESCE(NULL, 0) = '' AS r

-- CASE[open]: my-collation-fn — fails on oracle. FUNC-DIFF: source=(('utf8mb4_0900_ai_ci',),) target=(('USING_NLS_COMP',),)
SELECT COLLATION('abc') AS r

-- CASE[open]: my-compress — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT UNCOMPRESS(COMPRESS('data')) AS r

-- CASE[open]: my-concat-null — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('ab',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[open]: my-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r

-- CASE[open]: my-convert-signed — fails on oracle. ORA-00902: invalid datatype
SELECT CONVERT('123', SIGNED) AS r

-- CASE[open]: my-convert-tz — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CONVERT_TZ('2020-01-01 10:00', '+00:00', '+02:00') AS r

-- CASE[open]: my-crc32 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR
SELECT CRC32('abc') AS r

-- CASE[open]: my-create-role — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE ROLE 'r'

-- CASE[open]: my-date-add-interval — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT DATE_ADD('2020-01-01', INTERVAL 7 DAY) AS r

-- CASE[open]: my-date-add-month — fails on tsql. FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)
SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[open]: my-date-diff-minus — fails on oracle, postgresql. FUNC-DIFF: source=(('200',),) target=(('60',),)
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r

-- CASE[open]: my-date-eq-dt — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT DATE('2020-01-01') = '2020-01-01 00:00:00' AS r

-- CASE[open]: my-date-format — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r

-- CASE[open]: my-datetime-precision — fails on tsql. (2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat
CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)

-- CASE[open]: my-div — fails on postgresql, tsql. FUNC-DIFF: source=(('2.5',),) target=(('2',),)
SELECT 5 / 2 AS r

-- CASE[open]: my-div-precision — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('0.33333',),) target=(('0.333333',),)
SELECT 1.0 / 3 AS r

-- CASE[open]: my-elt — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EL
SELECT ELT(2, 'a', 'b', 'c') AS r

-- CASE[open]: my-emoji-len — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT CHAR_LENGTH('😀') AS r

-- CASE[open]: my-empty-eq-zero — fails on oracle. FUNC-DIFF: source=(('1',),) target=(('NULL',),)
SELECT '' = 0 AS r

-- CASE[open]: my-eq-mix — fails on oracle, tsql. FUNC-DIFF: source=(('1', '0', '1'),) target=(('1', '1', '1'),)
SELECT 1 = 1.0 AS r, 'a' = 'a ' AS b, 1 = TRUE AS c

-- CASE[open]: my-export-set — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXPORT_SET(5, 'Y', 'N', ',', 4) AS r

-- CASE[open]: my-extractvalue — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXTRACTVALUE('<a>1</a>', '/a') AS r

-- CASE[open]: my-field — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI
SELECT FIELD('b', 'a', 'b', 'c') AS r

-- CASE[open]: my-floor-precision — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('2',),) target=(('3',),)
SELECT FLOOR(2.9999999999999999) AS r

-- CASE[open]: my-gc-order — fails on oracle. FUNC-DIFF: source=(('3,1,2',),) target=(('1,2,3',),)
SELECT GROUP_CONCAT(x) FROM (SELECT 3 x UNION ALL SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[open]: my-get-lock — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_LOCK('l', 0), RELEASE_LOCK('l')

-- CASE[open]: my-greatest-null — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('3',),)
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[open]: my-greatest-null2 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1',),)
SELECT GREATEST(NULL, 1) AS r

-- CASE[open]: my-greatest-string — fails on oracle, postgresql. FUNC-DIFF: source=(('B',),) target=(('a',),)
SELECT GREATEST('a', 'B') AS r

-- CASE[open]: my-group-concat — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-hash — fails on oracle, postgresql, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc'), SHA1('abc'), SHA2('abc', 256)

-- CASE[open]: my-hex-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(255) AS r, BIN(5) AS b

-- CASE[open]: my-index-using — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT, b INT); CREATE INDEX ix ON t (a) USING BTREE

-- CASE[open]: my-inet — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET_ATON('127.0.0.1'), INET_NTOA(2130706433)

-- CASE[open]: my-insert-oob — fails on tsql. FUNC-DIFF: source=(('abc',),) target=(('NULL',),)
SELECT INSERT('abc', 10, 1, 'X') AS r

-- CASE[open]: my-int-or-empty — fails on oracle. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT 0 OR '' AS r

-- CASE[open]: my-is-true — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'IS'.DB-Lib error message 20018, severity 15:\nG
SELECT 1 IN (SELECT 1) IS TRUE AS r

-- CASE[open]: my-json-arrayagg — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-json-keys — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_KEYS('{"a":1,"b":2}') AS r

-- CASE[open]: my-json-merge — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_MERGE_PATCH('{"a":1}', '{"b":2}') AS r

-- CASE[open]: my-json-object — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_
SELECT JSON_OBJECT('a', 1, 'b', 2)

-- CASE[open]: my-json-type — fails on oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (data JSON)

-- CASE[open]: my-last-day-name — fails on oracle, postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY('2020-02-15'), DAYNAME('2020-06-15'), MONTHNAME('2020-06-15')

-- CASE[open]: my-least-null2 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1',),)
SELECT LEAST(1, 2, NULL, 3) AS r

-- CASE[open]: my-left-neg — fails on postgresql. FUNC-DIFF: source=(('',),) target=(('ab',),)
SELECT LEFT('abc', -1) AS r

-- CASE[open]: my-length-bytes — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('5',),) target=(('4',),)
SELECT LENGTH('café') AS r

-- CASE[open]: my-like-ci — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[open]: my-like-escape — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'a_b' LIKE 'a\_b' AS r

-- CASE[open]: my-like-single — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'x' LIKE 'X' AS r

-- CASE[open]: my-locate-case — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT LOCATE('a', 'ABC') AS r

-- CASE[open]: my-locate-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT LOCATE('', '') AS r

-- CASE[open]: my-lock-tables — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT); LOCK TABLES t WRITE

-- CASE[open]: my-log-2arg — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('0.333333',),)
SELECT LOG(2, 8) AS r

-- CASE[open]: my-log2-log10 — fails on tsql. FUNC-DIFF: source=(('3', '3'),) target=(('0.333333', '0.333333'),)
SELECT LOG2(8), LOG10(1000)

-- CASE[open]: my-lpad-trunc — fails on tsql. FUNC-DIFF: source=(('ab',),) target=(('bc',),)
SELECT LPAD('abc', 2, 'x') AS r

-- CASE[open]: my-make-set — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_SET(3, 'a', 'b', 'c') AS r

-- CASE[open]: my-makedate — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKEDATE(2020, 100), MAKETIME(10, 30, 0)

-- CASE[open]: my-month-overflow — fails on tsql. FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)
SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[open]: my-name-const — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NAME_CONST('col', 5) AS r

-- CASE[open]: my-nested-call — fails on oracle. PROCEDURE P compiled INVALID (line 4): PLS-00201: identifier 'OTHER_PROC' must be declared
CREATE PROCEDURE p() BEGIN CALL other_proc(); END

-- CASE[open]: my-numeric — fails on tsql. (2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se
CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)

-- CASE[open]: my-partition-hash — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT, dt DATE) PARTITION BY HASH(id) PARTITIONS 4

-- CASE[open]: my-period-diff — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE
SELECT PERIOD_DIFF(202006, 202001) AS r

-- CASE[open]: my-realworld-orders — fails on postgresql. relation "orders" already exists
CREATE TABLE orders (id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL, total DECIMAL(10,2) DEFAULT 0, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP, INDEX ix_cust (customer_id), CHECK (total >= 0)) ENGINE=InnoDB;
CREATE TRIGGER trg BEFORE INSERT ON orders FOR EACH ROW SET NEW.created = NOW();

-- CASE[open]: my-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n INT) RETURNS INT DETERMINISTIC BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END

-- CASE[open]: my-repeat-neg — fails on tsql. FUNC-DIFF: source=(('',),) target=(('NULL',),)
SELECT REPEAT('ab', -1) AS r

-- CASE[open]: my-replace-into — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT); REPLACE INTO t VALUES (1)

-- CASE[open]: my-scalar-subquery-assign — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE PROCEDURE p() BEGIN DECLARE v INT; SET v = (SELECT COUNT(*) FROM (SELECT 1) t); END

-- CASE[open]: my-select-into-out — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE PROCEDURE p(OUT c INT) BEGIN SELECT COUNT(*) INTO c FROM (SELECT 1) t; END

-- CASE[open]: my-soundex-format — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)

-- CASE[open]: my-spatial — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_AsText(ST_GeomFromText('POINT(1 1)')) AS r

-- CASE[open]: my-status-funcs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RO
SELECT LAST_INSERT_ID(), ROW_COUNT(), FOUND_ROWS()

-- CASE[open]: my-str-lt — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'apple' < 'Banana' AS r

-- CASE[open]: my-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('def',),) target=(('ab',),)
SELECT SUBSTRING('abcdef', -3) AS r

-- CASE[open]: my-substring-index — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r

-- CASE[open]: my-system-funcs — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'USER'.DB-Lib error message 20018, severity 15:\
SELECT CONNECTION_ID(), DATABASE(), USER(), VERSION()

-- CASE[open]: my-timestampadd — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT TIMESTAMPADD(MINUTE, 30, '2020-01-01 10:00') AS r

-- CASE[open]: my-timestampdiff — fails on oracle. ORA-01861: literal does not match format string
SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[open]: my-timestampdiff-mon — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10') AS r

-- CASE[open]: my-timestampdiff-year — fails on tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT TIMESTAMPDIFF(YEAR, '2019-12-31', '2020-01-01') AS r

-- CASE[open]: my-trailing-eq — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'a ' = 'a' AS r

-- CASE[open]: my-trim-both — fails on postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS r

-- CASE[open]: my-trim-leading — fails on postgresql, tsql. FUNC-DIFF: source=(('7',),) target=(('',),)
SELECT TRIM(LEADING '0' FROM '007') AS r

-- CASE[open]: my-ts-to-date — fails on postgresql. FUNC-DIFF: source=(('2020-01-01',),) target=(('2020-01-01 14:30:00+00:00',),)
SELECT DATE(TIMESTAMP '2020-01-01 14:30') AS r

-- CASE[open]: my-unix-timestamp — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)

-- CASE[open]: my-update-join — fails on oracle, postgresql, tsql. (4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se
CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n

-- CASE[open]: my-upper-sharps — fails on postgresql. FUNC-DIFF: source=(('ß',),) target=(('ẞ',),)
SELECT UPPER('ß') AS r

-- CASE[open]: my-upper-sharps-len — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('2',),) target=(('1',),)
SELECT LENGTH(UPPER('ß')) AS r

-- CASE[open]: my-uuid-funcs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU
SELECT UUID(), UUID_SHORT()

-- CASE[open]: my-view-cascade-check — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT, b INT); CREATE VIEW v AS SELECT a FROM t WHERE a > 0 WITH CASCADED CHECK OPTION

-- CASE[open]: my-week-quarter — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')

-- CASE[open]: my-weight-string — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEIGHT_STRING('abc') AS r

-- CASE[open]: mysql-drop-'note'|note — fails on oracle, postgresql. SILENT CLAUSE DROP: ''note'|note' absent from valid oracle output, no warning (target supp
CREATE TABLE t (a INT COMMENT 'note')

-- CASE[open]: mysql-drop-CHECK — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)
CREATE TABLE t (email VARCHAR(255) CHECK (email LIKE '%@%'))

-- CASE[open]: mysql-drop-GENERATED|AS\s — fails on tsql. SILENT CLAUSE DROP: 'GENERATED|AS\s*\(' absent from valid tsql output, no warning (target 
CREATE TABLE t (a INT, b INT AS (a+1) STORED)

-- CASE[open]: mysql-drop2-ON\s+UPDATE — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ON\s+UPDATE' absent from valid tsql output, no warning
CREATE TABLE t (a INT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)

-- CASE[open]: mysql-drop2-latin1|CHARA — fails on oracle, postgresql. SILENT CLAUSE DROP: 'latin1|CHARACTER\s+SET' absent from valid postgresql output, no warni
CREATE TABLE t (a VARCHAR(10) CHARACTER SET latin1)

-- CASE[open]: mysql-drop2-my table|COM — fails on oracle, postgresql. SILENT CLAUSE DROP: 'my table|COMMENT' absent from valid postgresql output, no warning
CREATE TABLE t (a INT) COMMENT='my table'

-- CASE[open]: mysql-drop4-50|IDENTITY| — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: '50|IDENTITY|START' absent from valid tsql output, no warning
CREATE TABLE t (a INT PRIMARY KEY) AUTO_INCREMENT = 50

-- CASE[open]: mysql-drop4-COLLATE|utf8 — fails on oracle, postgresql. SILENT CLAUSE DROP: 'COLLATE|utf8mb4' absent from valid postgresql output, no warning
CREATE TABLE t (a INT) COLLATE=utf8mb4_unicode_ci

-- CASE[open]: mysql-drop4-UNSIGNED|CHE — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'UNSIGNED|CHECK' absent from valid postgresql output, no warning
CREATE TABLE t (a INT UNSIGNED)

-- CASE[open]: mysql-drop4-ZEROFILL|LPA — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ZEROFILL|LPAD' absent from valid postgresql output, no warning
CREATE TABLE t (a INT ZEROFILL)

-- CASE[open]: mysql-drop5-utf8mb4|CHAR — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'utf8mb4|CHARSET' absent from valid tsql output, no warning
CREATE TABLE t (a INT AUTO_INCREMENT PRIMARY KEY, b VARCHAR(20)) DEFAULT CHARSET=utf8mb4

-- CASE[open]: mysql-qdrop-ROLLUP — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ROLLUP' absent from valid tsql output, no warning
SELECT x FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x WITH ROLLUP

-- CASE[open]: mysql-qdrop-SQL_CALC_FOU — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'SQL_CALC_FOUND_ROWS|FOUND' absent from valid tsql output, no warning
SELECT SQL_CALC_FOUND_ROWS x FROM (SELECT 1 x) t LIMIT 1

