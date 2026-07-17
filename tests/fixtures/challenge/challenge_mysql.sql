-- Challenge fixtures — MySQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: my-alter-modify — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S
CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT

-- CASE[open]: my-avg-int — fails on tsql. FUNC-DIFF: source=(('1.5',),) target=(('1',),)
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-base64 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO
SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')

-- CASE[open]: my-bit-count — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_COUNT(255) AS r

-- CASE[open]: my-cast-convert — fails on oracle, postgresql, tsql. (243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:
SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)

-- CASE[open]: my-cast-int — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT CAST(2.7 AS SIGNED) AS r

-- CASE[open]: my-concat-null — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('ab',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[open]: my-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r

-- CASE[open]: my-convert-tz — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CONVERT_TZ('2020-01-01 10:00', '+00:00', '+02:00') AS r

-- CASE[open]: my-crc32 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR
SELECT CRC32('abc') AS r

-- CASE[open]: my-date-add-interval — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT DATE_ADD('2020-01-01', INTERVAL 7 DAY) AS r

-- CASE[open]: my-date-add-month — fails on tsql. FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)
SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[open]: my-date-format — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r

-- CASE[open]: my-datetime-precision — fails on tsql. (2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat
CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)

-- CASE[open]: my-div — fails on postgresql, tsql. FUNC-DIFF: source=(('2.5',),) target=(('2',),)
SELECT 5 / 2 AS r

-- CASE[open]: my-elt — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EL
SELECT ELT(2, 'a', 'b', 'c') AS r

-- CASE[open]: my-field — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI
SELECT FIELD('b', 'a', 'b', 'c') AS r

-- CASE[open]: my-greatest-null — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('3',),)
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[open]: my-group-concat — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-hash — fails on oracle, postgresql, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc'), SHA1('abc'), SHA2('abc', 256)

-- CASE[open]: my-hex-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(255) AS r, BIN(5) AS b

-- CASE[open]: my-inet — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET_ATON('127.0.0.1'), INET_NTOA(2130706433)

-- CASE[open]: my-json-arrayagg — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-json-object — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_
SELECT JSON_OBJECT('a', 1, 'b', 2)

-- CASE[open]: my-json-type — fails on oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (data JSON)

-- CASE[open]: my-last-day-name — fails on oracle, postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY('2020-02-15'), DAYNAME('2020-06-15'), MONTHNAME('2020-06-15')

-- CASE[open]: my-length-bytes — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('5',),) target=(('4',),)
SELECT LENGTH('café') AS r

-- CASE[open]: my-like-ci — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[open]: my-makedate — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKEDATE(2020, 100), MAKETIME(10, 30, 0)

-- CASE[open]: my-numeric — fails on tsql. (2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se
CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)

-- CASE[open]: my-partition-hash — fails on oracle, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT, dt DATE) PARTITION BY HASH(id) PARTITIONS 4

-- CASE[open]: my-period-diff — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE
SELECT PERIOD_DIFF(202006, 202001) AS r

-- CASE[open]: my-soundex-format — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)

-- CASE[open]: my-substring-index — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r

-- CASE[open]: my-timestampadd — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT TIMESTAMPADD(MINUTE, 30, '2020-01-01 10:00') AS r

-- CASE[open]: my-timestampdiff — fails on oracle. ORA-01861: literal does not match format string
SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[open]: my-trim-both — fails on postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS r

-- CASE[open]: my-unix-timestamp — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)

-- CASE[open]: my-update-join — fails on oracle, postgresql, tsql. (4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se
CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n

-- CASE[open]: my-week-quarter — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')

