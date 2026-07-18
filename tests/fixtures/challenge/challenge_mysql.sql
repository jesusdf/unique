-- Challenge fixtures — MySQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: my-accent-eq — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'Ä' = 'A' AS r

-- CASE[open]: my-adddate — fails on tsql. FUNC-DIFF: source=(('2020-01-31',),) target=(('2020-01-31 00:00:00',),)
SELECT ADDDATE('2020-01-01', 30) AS r

-- CASE[open]: my-aes — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(AES_ENCRYPT('data', 'key')) AS r

-- CASE[open]: my-agg-bit — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_AND(x),BIT_OR(x),BIT_XOR(x) FROM (SELECT 3 x UNION ALL SELECT 5 x UNION ALL SELECT 6 x) t

-- CASE[open]: my-agg-collect — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT GROUP_CONCAT(x),JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[open]: my-alter-drop-default — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'DEFAULT'.DB-Lib error message 20018, severity 1
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP DEFAULT

-- CASE[open]: my-alter-modify — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S
CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT

-- CASE[open]: my-alter-set-default — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5

-- CASE[open]: my-any-value — fails on postgresql, tsql. (102, b"Incorrect syntax near '>'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT ANY_VALUE(x), GROUP_CONCAT(x) FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x>0

-- CASE[open]: my-arr-json — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAY(1,2,3),JSON_ARRAY_APPEND('[1]','$',2),JSON_ARRAY_INSERT('[1,2]','$[0]',0)

-- CASE[open]: my-ascii-empty — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT ASCII('') AS r

-- CASE[open]: my-avg-int — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1.5',),) target=(('1',),)
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-avg-precision2 — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1.6667',),) target=(('1',),)
SELECT AVG(x) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 2) t

-- CASE[open]: my-base64 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO
SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')

-- CASE[open]: my-baseconv — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIN(255),OCT(255),HEX(255),CONV(255,10,36)

-- CASE[open]: my-benchmark — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BE
SELECT BENCHMARK(1, 1+1) AS r

-- CASE[open]: my-binary-substr — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT SUBSTRING(UNHEX('48656C6C6F'), 1, 2) AS r

-- CASE[open]: my-bintypes — fails on tsql. (2716, b'Column, parameter, or variable #7: Cannot specify a column width on data type bit
CREATE TABLE t (a BINARY(16), b VARBINARY(255), c TINYBLOB, d BLOB, e MEDIUMBLOB, f LONGBLOB, g BIT(8), h BOOL)

-- CASE[open]: my-bit-agg — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_XOR(x), BIT_OR(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-bit-char-len — fails on postgresql. FUNC-DIFF: source=(('24', '1', '3'),) target=(('24', '1', '1'),)
SELECT BIT_LENGTH('€'), CHAR_LENGTH('€'), LENGTH('€')

-- CASE[open]: my-bit-count — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_COUNT(255) AS r

-- CASE[open]: my-bit-fns — fails on postgresql. function bitwise_count(bit) does not exist
SELECT BIT_COUNT(b'1011'), BIT_LENGTH('a'), OCTET_LENGTH('ab')

-- CASE[open]: my-bit-prec2 — fails on tsql. FUNC-DIFF: source=(('2', '14', '8'),) target=(('3', '14', '5'),)
SELECT 10 & 6 + 1, 10 | 2 * 3, 1 << 2 + 1

-- CASE[open]: my-bitand-prec — fails on tsql. FUNC-DIFF: source=(('2',),) target=(('3',),)
SELECT 10 & 6 + 1 AS r

-- CASE[open]: my-bitnot — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('18446744073709551616',),) target=(('-1',),)
SELECT ~0 AS r

-- CASE[open]: my-bitnot-arith — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('18446744073709551616',),) target=(('-5',),)
SELECT ~5 + 1 AS r

-- CASE[open]: my-bitops — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1', '7', '6', '18446744073709551616', '10', '2'),) target=(('1', '7',
SELECT 5 & 3, 5 | 2, 5 ^ 3, ~5, 5 << 1, 5 >> 1

-- CASE[open]: my-blob-length — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
CREATE TABLE t (data BLOB); INSERT INTO t VALUES (LOAD_FILE('/x')); SELECT LENGTH(data) FROM t

-- CASE[open]: my-bool-char — fails on postgresql. FUNC-DIFF: source=(('1',),) target=(('t',),)
SELECT CAST((1=1) AS CHAR) AS r

-- CASE[open]: my-cast-binary2 — fails on postgresql. type "binary" does not exist
SELECT CONVERT('abc',BINARY), CONVERT('abc' USING latin1), CAST('abc' AS BINARY)

-- CASE[open]: my-cast-charset — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(0xC3A9 AS CHAR CHARACTER SET utf8mb4) AS r

-- CASE[open]: my-cast-convert — fails on oracle, postgresql, tsql. (243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:
SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)

-- CASE[open]: my-cast-datetime — fails on oracle. ORA-01843: An invalid month was specified.
SELECT CAST('2020-01-01' AS DATETIME) AS r

-- CASE[open]: my-cast-datetime2 — fails on oracle. ORA-01861: literal does not match format string
SELECT CAST('2020-01-01 10:00' AS DATE), CAST('2020-01-01 10:00' AS TIME), CAST('2020-01-01 10:00' AS DATETIME)

-- CASE[open]: my-cast-decimal2 — fails on oracle, postgresql, tsql. (8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit
SELECT CAST('12.99' AS DECIMAL(4,1)), CAST('12.99' AS DECIMAL(3,0)), CAST('abc' AS DECIMAL)

-- CASE[open]: my-cast-hex-char — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(0xFF AS CHAR) AS r

-- CASE[open]: my-cast-int — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT CAST(2.7 AS SIGNED) AS r

-- CASE[open]: my-cast-json — fails on oracle, postgresql, tsql. (243, b'Type json is not a defined system type.DB-Lib error message 20018, severity 16:\nG
SELECT CAST(1 AS JSON), CAST('[1,2]' AS JSON), CAST(NULL AS JSON)

-- CASE[open]: my-cast-matrix — fails on oracle, postgresql. ORA-00902: invalid datatype
SELECT CAST(3.14 AS DECIMAL(10,2)), CAST(3.14 AS SIGNED), CAST(3.14 AS CHAR), CAST(3.14 AS DOUBLE)

-- CASE[open]: my-cast-num-char — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(1234.5 AS CHAR) AS r

-- CASE[open]: my-cast-suite — fails on oracle. ORA-00902: invalid datatype
SELECT CAST('123' AS SIGNED),CAST('1.5' AS DECIMAL(4,2)),CONVERT('123',SIGNED),CAST('2020-01-01' AS DATE),CAST(65 AS CHAR)

-- CASE[open]: my-cast-time — fails on oracle. DPY-3006: Oracle data type 178 is not supported
SELECT CAST('10:00:00' AS TIME) AS r

-- CASE[open]: my-cast-truncate — fails on oracle, tsql. (243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity
SELECT CAST(TIMESTAMP '2020-01-01 10:30' AS DATE), CAST(TIME '10:30:45' AS CHAR)

-- CASE[open]: my-cast-uns2 — fails on postgresql. type "ubigint" does not exist
SELECT CAST(0xFFFF AS UNSIGNED), CAST(b'1111' AS UNSIGNED), CAST(TRUE AS UNSIGNED)

-- CASE[open]: my-cast-year — fails on oracle, postgresql. ORA-00902: invalid datatype
SELECT CAST('2020' AS YEAR), CAST(2020 AS YEAR), CAST('99' AS YEAR)

-- CASE[open]: my-change-column — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'CHANGE'.DB-Lib error message 20018, severity 15:\nGeneral S
CREATE TABLE t (a INT, b INT); ALTER TABLE t CHANGE a x INT

-- CASE[open]: my-char-256 — fails on oracle, postgresql. FUNC-DIFF: source=(('0100',),) target=(('\x01\x00',),)
SELECT CHAR(256) AS r

-- CASE[open]: my-char-encoding — fails on oracle, postgresql, tsql. (195, b"'CHR' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT ASCII('A'),CHAR(65),ORD('é'),HEX('AB'),UNHEX('4142'),TO_BASE64('AB'),FROM_BASE64('QUI='),BIT_LENGTH('AB')

-- CASE[open]: my-char-unicode — fails on postgresql. FUNC-DIFF: source=(('NULL',),) target=(('μ',),)
SELECT CHAR(956 USING utf8mb4) AS r

-- CASE[open]: my-char-unicode2 — fails on oracle, postgresql, tsql. (195, b"'CHR' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT CHAR(0x41,0x42 USING utf8mb4),ORD('中')

-- CASE[open]: my-check-enforced — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'ENFORCED'.DB-Lib error message 20018, severity 15:\nGeneral
CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) ENFORCED

-- CASE[open]: my-coalesce-empty — fails on oracle. FUNC-DIFF: source=(('1',),) target=(('NULL',),)
SELECT COALESCE(NULL, 0) = '' AS r

-- CASE[open]: my-coalesce-single — fails on oracle. ORA-00938: not enough arguments for function
SELECT COALESCE(x) FROM (SELECT NULL x) t

-- CASE[open]: my-collation-fn — fails on oracle. FUNC-DIFF: source=(('utf8mb4_0900_ai_ci',),) target=(('USING_NLS_COMP',),)
SELECT COLLATION('abc') AS r

-- CASE[open]: my-compress — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT UNCOMPRESS(COMPRESS('data')) AS r

-- CASE[open]: my-compress2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT COMPRESS('x'), UNCOMPRESSED_LENGTH(COMPRESS('x'))

-- CASE[open]: my-computed-json — fails on postgresql, tsql. (195, b"'JSON_UNQUOTE' is not a recognized built-in function name.DB-Lib error message 200
CREATE TABLE t (data JSON, name VARCHAR(50) AS (JSON_UNQUOTE(JSON_EXTRACT(data, '$.name'))) VIRTUAL)

-- CASE[open]: my-concat-bool — fails on postgresql. FUNC-DIFF: source=(('10',),) target=(('tf',),)
SELECT CONCAT(TRUE, FALSE) AS r

-- CASE[open]: my-concat-date — fails on oracle. FUNC-DIFF: source=(('2020-01-01',),) target=(('01-JAN-20',),)
SELECT CONCAT(DATE '2020-01-01', '') AS r

-- CASE[open]: my-concat-null — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('ab',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[open]: my-concat-null3 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL', 'a,b'),) target=(('a', 'a,b'),)
SELECT CONCAT('a',NULL), CONCAT_WS(',','a',NULL,'b')

-- CASE[open]: my-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r

-- CASE[open]: my-concatws3 — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', a, b) FROM (SELECT 'x' a, 'y' b) t

-- CASE[open]: my-conv2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CONV('7F', 16, 2), CONV(255, 10, 16)

-- CASE[open]: my-convert-signed — fails on oracle. ORA-00902: invalid datatype
SELECT CONVERT('123', SIGNED) AS r

-- CASE[open]: my-convert-tz — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CONVERT_TZ('2020-01-01 10:00', '+00:00', '+02:00') AS r

-- CASE[open]: my-convert-using2 — fails on oracle, postgresql. FUNC-DIFF: source=(('2020-06-15 14:30',),) target=(('2',),)
SELECT CONVERT('2020-06-15 14:30' USING utf8mb4) AS r

-- CASE[open]: my-crc32 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR
SELECT CRC32('abc') AS r

-- CASE[open]: my-crypto2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_BASE64(TO_BASE64('hello')),HEX(AES_DECRYPT(AES_ENCRYPT('d','k'),'k'))

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

-- CASE[open]: my-dateadd — fails on tsql. FUNC-DIFF: source=(('2020-02-29', '2020-01-02', '2020-02-29', '2020-01-01 01:00:00'),) tar
SELECT DATE_ADD('2020-01-31',INTERVAL 1 MONTH), DATE_ADD('2020-01-01',INTERVAL 1 DAY), DATE_SUB('2020-03-01',INTERVAL 1 DAY), '2020-01-01'+INTERVAL 1 HOUR

-- CASE[open]: my-dateadd-units — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 2 of dateadd function.DB-Lib e
SELECT DATE_ADD(NOW(),INTERVAL 1 QUARTER), DATE_SUB(NOW(),INTERVAL 2 WEEK)

-- CASE[open]: my-dateformat-iso — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT DATE_FORMAT('2020-06-15 14:30:45', '%Y-%m-%dT%H:%i:%s') AS r

-- CASE[open]: my-dateformat-long — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT DATE_FORMAT('2020-06-15', '%W, %M %D, %Y') AS r

-- CASE[open]: my-datetime-precision — fails on tsql. (2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat
CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)

-- CASE[open]: my-dayparts — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DA
SELECT DAYOFWEEK(NOW()), WEEKDAY(NOW()), DAYOFYEAR(NOW()), QUARTER(NOW())

-- CASE[open]: my-distinct-case — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('a',), ('B',)) target=(('A',), ('B',))
SELECT DISTINCT x FROM (SELECT 'a' x UNION ALL SELECT 'A' x UNION ALL SELECT 'a' x UNION ALL SELECT 'B' x) t ORDER BY x

-- CASE[open]: my-div — fails on postgresql, tsql. FUNC-DIFF: source=(('2.5',),) target=(('2',),)
SELECT 5 / 2 AS r

-- CASE[open]: my-div-mult2 — fails on postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 1/3*3 AS r

-- CASE[open]: my-div-precision — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('0.33333',),) target=(('0.333333',),)
SELECT 1.0 / 3 AS r

-- CASE[open]: my-dttypes — fails on oracle, tsql. (2716, b'Column, parameter, or variable #6: Cannot specify a column width on data type dat
CREATE TABLE t (a DATE, b TIME, c DATETIME, d TIMESTAMP, e YEAR, f DATETIME(6), g TIME(3))

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

-- CASE[open]: my-export-set2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXPORT_SET(5,'Y','N',',',4) AS r

-- CASE[open]: my-extract-compound — fails on oracle, postgresql, tsql. (155, b"'YEAR_MONTH' is not a recognized datepart option.DB-Lib error message 20018, sever
SELECT EXTRACT(YEAR_MONTH FROM NOW()), EXTRACT(DAY_HOUR FROM NOW())

-- CASE[open]: my-extractvalue — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXTRACTVALUE('<a>1</a>', '/a') AS r

-- CASE[open]: my-fcollate — fails on oracle, postgresql. FUNC-DIFF: source=(('c', 'a', '1'),) target=(('c', 'B', '0'),)
SELECT GREATEST('a','B','c'),LEAST('a','B'),'a'<'B'

-- CASE[open]: my-fconcatnum — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('x5', 'x5.5', 'x1', 'NULL'),) target=(('x5', 'x5.5', 'x1', 'x'),)
SELECT CONCAT('x',5),CONCAT('x',5.5),CONCAT('x',TRUE),CONCAT('x',NULL)

-- CASE[open]: my-field — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI
SELECT FIELD('b', 'a', 'b', 'c') AS r

-- CASE[open]: my-file-lock — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT LOAD_FILE('/etc/x'), IS_USED_LOCK('l')

-- CASE[open]: my-fk-full — fails on oracle. ORA-03075: unexpected item ON in an out-of-line constraint
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE t (pid INT, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES p(id) ON DELETE SET NULL ON UPDATE CASCADE)

-- CASE[open]: my-flen — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('5', '4', '6', '2'),) target=(('4', '4', '2', '2'),)
SELECT LENGTH('café'),CHAR_LENGTH('café'),LENGTH('日本'),CHAR_LENGTH('日本')

-- CASE[open]: my-floor-precision — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('2',),) target=(('3',),)
SELECT FLOOR(2.9999999999999999) AS r

-- CASE[open]: my-fmt-spec — fails on oracle. SILENT: source literal(s) ["'%a %b %e %T %Y'", "'%p %l:%i'", "'%j %U %u %V'"] absent from 
SELECT DATE_FORMAT(NOW(),'%a %b %e %T %Y'),DATE_FORMAT(NOW(),'%p %l:%i'),DATE_FORMAT(NOW(),'%j %U %u %V')

-- CASE[open]: my-fmt-spec2 — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT DATE_FORMAT('2020-06-15','%D %W %M'),DATE_FORMAT('2020-06-15','%X %V')

-- CASE[open]: my-fmt3 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT FORMAT(1234.5678,2),FORMAT(1234.5678,4,'de_DE'),TRUNCATE(1234.5678,2)

-- CASE[open]: my-for-share — fails on oracle. ORA-02000: missing COMPRESS or UPDATE keyword
CREATE TABLE t (id INT, INDEX ix (id)); SELECT id FROM t WHERE id = 1 FOR SHARE

-- CASE[open]: my-format-fns2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT DATE_FORMAT(NOW(),'%W %M %Y'), TIME_FORMAT(NOW(),'%r')

-- CASE[open]: my-fsubstr — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('', 'c', 'bc'),) target=(('ab', 'a', 'bc'),)
SELECT SUBSTRING('abc',0),SUBSTRING('abc',-1),SUBSTRING('abc',2,10)

-- CASE[open]: my-full-select — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t GROUP BY id HAVING COUNT(*) > 1 ORDER BY id LIMIT 10 OFFSET 5

-- CASE[open]: my-fulltext — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
CREATE TABLE t (txt TEXT, FULLTEXT(txt));
SELECT * FROM t WHERE MATCH(txt) AGAINST('hello' IN NATURAL LANGUAGE MODE)

-- CASE[open]: my-gc-order — fails on oracle. FUNC-DIFF: source=(('3,1,2',),) target=(('1,2,3',),)
SELECT GROUP_CONCAT(x) FROM (SELECT 3 x UNION ALL SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[open]: my-gen-constr — fails on tsql. (1764, b"Computed Column 'b' in table 't' is invalid for use in 'CHECK CONSTRAINT' because
CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a+1) VIRTUAL, UNIQUE (b), CHECK (b>a))

-- CASE[open]: my-gencol2 — fails on postgresql, tsql. (1759, b"Computed column 'b' in table 't' is not allowed to be used in another computed-co
CREATE TABLE t (a INT, b INT AS (a*2) STORED, c INT AS (a+b) VIRTUAL, KEY(b))

-- CASE[open]: my-get-format — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_FORMAT(DATE, 'USA'), GET_FORMAT(DATETIME, 'ISO')

-- CASE[open]: my-get-lock — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_LOCK('l', 0), RELEASE_LOCK('l')

-- CASE[open]: my-getformat2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_FORMAT(DATE,'EUR'), GET_FORMAT(TIME,'USA'), GET_FORMAT(DATETIME,'JIS')

-- CASE[open]: my-greatest-null — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('3',),)
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[open]: my-greatest-null2 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1',),)
SELECT GREATEST(NULL, 1) AS r

-- CASE[open]: my-greatest-string — fails on oracle, postgresql. FUNC-DIFF: source=(('B',),) target=(('a',),)
SELECT GREATEST('a', 'B') AS r

-- CASE[open]: my-group-case — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('a', '2'), ('b', '1')) target=(('A', '2'), ('b', '1'))
SELECT x, COUNT(*) FROM (SELECT 'a' x UNION ALL SELECT 'A' x UNION ALL SELECT 'b' x) t GROUP BY x ORDER BY x

-- CASE[open]: my-group-concat — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-groupconcat-order — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR ',') FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[open]: my-hash — fails on oracle, postgresql, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc'), SHA1('abc'), SHA2('abc', 256)

-- CASE[open]: my-hash-all — fails on oracle, postgresql, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT CRC32('abc'), MD5('abc'), SHA('abc'), SHA2('abc', 512)

-- CASE[open]: my-hex-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(255) AS r, BIN(5) AS b

-- CASE[open]: my-hex-str-add — fails on postgresql. FUNC-DIFF: source=(('0',),) target=(('16',),)
SELECT '0x10' + 0 AS r

-- CASE[open]: my-hexcast — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT CAST(x'48656C6C6F' AS CHAR),HEX('Hello'),UNHEX('48656C6C6F')

-- CASE[open]: my-ifnull-empty — fails on oracle. FUNC-DIFF: source=(('',),) target=(('NULL',),)
SELECT IFNULL('', NULL) AS r

-- CASE[open]: my-index-fns — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI
SELECT INTERVAL(3, 1, 2, 4, 6), FIELD('b','a','b'), ELT(1,'x','y')

-- CASE[open]: my-inet — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET_ATON('127.0.0.1'), INET_NTOA(2130706433)

-- CASE[open]: my-inet3 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET_ATON('10.0.0.1'),INET_NTOA(167772161),INET6_ATON('::1')

-- CASE[open]: my-inet6 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET6_ATON('::1'), INET6_NTOA(INET6_ATON('::1'))

-- CASE[open]: my-infoschema — fails on oracle. PROCEDURE P compiled INVALID (line 8): PL/SQL: ORA-00942: table or view does not exist
CREATE PROCEDURE p() BEGIN DECLARE c INT; SELECT COUNT(*) INTO c FROM information_schema.tables; SELECT c; END

-- CASE[open]: my-insert-oob — fails on tsql. FUNC-DIFF: source=(('abc',),) target=(('NULL',),)
SELECT INSERT('abc', 10, 1, 'X') AS r

-- CASE[open]: my-insert-zeropos — fails on tsql. FUNC-DIFF: source=(('abcdef',),) target=(('NULL',),)
SELECT INSERT('abcdef', 0, 2, 'XY') AS r

-- CASE[open]: my-insert2 — fails on oracle, postgresql. ORA-00904: "STUFF": invalid identifier
SELECT INSERT('Quadratic', 3, 4, 'What') AS r

-- CASE[open]: my-instr-case — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT INSTR('aAaA', 'A') AS r

-- CASE[open]: my-int-or-empty — fails on oracle. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT 0 OR '' AS r

-- CASE[open]: my-is-true — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'IS'.DB-Lib error message 20018, severity 15:\nG
SELECT 1 IN (SELECT 1) IS TRUE AS r

-- CASE[open]: my-json-aggs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAYAGG(x), JSON_OBJECTAGG(x, x*2) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-json-array-ops — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAY_APPEND('[1,2]', '$', 3), JSON_ARRAY_INSERT('[1,2]', '$[0]', 0)

-- CASE[open]: my-json-arrayagg — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-json-build — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAY(1,'a',NULL,TRUE),JSON_OBJECT('k','v','n',1)

-- CASE[open]: my-json-fns2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SEARCH('{"a":"x"}', 'one', 'x'), JSON_DEPTH('[1,[2]]'), JSON_LENGTH('[1,2,3]')

-- CASE[open]: my-json-index — fails on postgresql, tsql. (2715, b'Column, parameter, or variable #2: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (a INT, b JSON, c INT AS (JSON_EXTRACT(b,'$.x')) STORED, INDEX((CAST(b->'$.x' AS UNSIGNED))))

-- CASE[open]: my-json-keys — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_KEYS('{"a":1,"b":2}') AS r

-- CASE[open]: my-json-merge — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_MERGE_PATCH('{"a":1}', '{"b":2}') AS r

-- CASE[open]: my-json-meta — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_TYPE('[1]'),JSON_LENGTH('[1,2,3]'),JSON_DEPTH('[[1]]'),JSON_VALID('{a}')

-- CASE[open]: my-json-mod — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SET('{}','$.a',1),JSON_INSERT('{}','$.a',1),JSON_REPLACE('{"a":1}','$.a',2),JSON_REMOVE('{"a":1,"b":2}','$.a')

-- CASE[open]: my-json-modify — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SET('{}', '$.a', 1), JSON_REMOVE('{"a":1}', '$.a'), JSON_REPLACE('{"a":1}', '$.a', 2)

-- CASE[open]: my-json-object — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_
SELECT JSON_OBJECT('a', 1, 'b', 2)

-- CASE[open]: my-json-search — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_KEYS('{"a":1,"b":2}'),JSON_CONTAINS('[1,2]','1'),JSON_CONTAINS_PATH('{"a":1}','one','$.a')

-- CASE[open]: my-json-search2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SEARCH('{"a":"x","b":"x"}','all','x'),JSON_OVERLAPS('[1,2]','[2,3]')

-- CASE[open]: my-json-type — fails on oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (data JSON)

-- CASE[open]: my-last-day-name — fails on oracle, postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY('2020-02-15'), DAYNAME('2020-06-15'), MONTHNAME('2020-06-15')

-- CASE[open]: my-lastday-extract — fails on oracle, postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY('2020-02-15'), EXTRACT(DAY FROM LAST_DAY('2020-02-15'))

-- CASE[open]: my-least-greatest-null — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL', 'NULL'),) target=(('a', '1'),)
SELECT LEAST(NULL, 'a') AS r, GREATEST(NULL, 1) AS b

-- CASE[open]: my-least-null2 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1',),)
SELECT LEAST(1, 2, NULL, 3) AS r

-- CASE[open]: my-left-float — fails on tsql. FUNC-DIFF: source=(('hel',),) target=(('he',),)
SELECT LEFT('hello', 2.9) AS r

-- CASE[open]: my-left-neg — fails on postgresql. FUNC-DIFF: source=(('',),) target=(('ab',),)
SELECT LEFT('abc', -1) AS r

-- CASE[open]: my-len-trio — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT CHAR_LENGTH(s), LENGTH(s), BIT_LENGTH(s) FROM (SELECT 'héllo' s) t

-- CASE[open]: my-length-bytes — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('5',),) target=(('4',),)
SELECT LENGTH('café') AS r

-- CASE[open]: my-length-div — fails on oracle, tsql. FUNC-DIFF: source=(('6',),) target=(('1',),)
SELECT LENGTH(1/3) AS r

-- CASE[open]: my-length-unicode — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('5', '4', '5'),) target=(('4', '4', '3'),)
SELECT LENGTH('café'), CHAR_LENGTH('café'), LENGTH('  x  ')

-- CASE[open]: my-like-ci — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[open]: my-like-escape — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'a_b' LIKE 'a\_b' AS r

-- CASE[open]: my-like-single — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'x' LIKE 'X' AS r

-- CASE[open]: my-loadfile — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT LOAD_FILE('/nonexist') IS NULL AS r

-- CASE[open]: my-locate-case — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT LOCATE('a', 'ABC') AS r

-- CASE[open]: my-locate-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT LOCATE('', '') AS r

-- CASE[open]: my-locate-empty2 — fails on oracle, tsql. FUNC-DIFF: source=(('1', '1'),) target=(('0', '0'),)
SELECT LOCATE('', 'abc'), INSTR('abc', '')

-- CASE[open]: my-log-2arg — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('0.333333',),)
SELECT LOG(2, 8) AS r

-- CASE[open]: my-log2-log10 — fails on tsql. FUNC-DIFF: source=(('3', '3'),) target=(('0.333333', '0.333333'),)
SELECT LOG2(8), LOG10(1000)

-- CASE[open]: my-logexp — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LN
SELECT LOG2(8), LOG10(100), LN(2.718), EXP(1)

-- CASE[open]: my-lpad-conv — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT LPAD(CONV(5,10,2), 8, '0') AS r

-- CASE[open]: my-lpad-multichar — fails on tsql. FUNC-DIFF: source=(('xyxab',),) target=(('yxyab',),)
SELECT LPAD('ab', 5, 'xy') AS r

-- CASE[open]: my-lpad-trunc — fails on tsql. FUNC-DIFF: source=(('ab',),) target=(('bc',),)
SELECT LPAD('abc', 2, 'x') AS r

-- CASE[open]: my-make-set — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_SET(3, 'a', 'b', 'c') AS r

-- CASE[open]: my-make-set2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_SET(1|4,'hello','nice','world') AS r

-- CASE[open]: my-makedate — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKEDATE(2020, 100), MAKETIME(10, 30, 0)

-- CASE[open]: my-misc-num — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR
SELECT RAND(),FLOOR(RAND()*100),CRC32('x'),CONV(255,10,2),BIN(10),OCT(64),HEX(255)

-- CASE[open]: my-mod-edge — fails on oracle. FUNC-DIFF: source=(('0', '1', '1'),) target=(('0', '0', '0'),)
SELECT MOD(0,5), MOD(5,0) IS NULL, 5%0 IS NULL

-- CASE[open]: my-mod-zero — fails on oracle. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 5 MOD 0 IS NULL AS r

-- CASE[open]: my-month-overflow — fails on tsql. FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)
SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[open]: my-name-const — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NAME_CONST('col', 5) AS r

-- CASE[open]: my-nested-call — fails on oracle. PROCEDURE P compiled INVALID (line 4): PLS-00201: identifier 'OTHER_PROC' must be declared
CREATE PROCEDURE p() BEGIN CALL other_proc(); END

-- CASE[open]: my-now-fns — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'CURRENT_TIME'.DB-Lib error message 20018, sever
SELECT NOW(), CURDATE(), CURTIME(), UTC_DATE(), UTC_TIME(), SYSDATE()

-- CASE[open]: my-numeric — fails on tsql. (2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se
CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)

-- CASE[open]: my-numeric-conv — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_COUNT(255), CONV(255,10,16), OCT(64), HEX(255)

-- CASE[open]: my-optimizer-hints — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT /*+ QB_NAME(qb1) */ id FROM t WHERE n > (SELECT /*+ SEMIJOIN(@qb1) */ AVG(n) FROM t)

-- CASE[open]: my-order-strings — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('Apple',), ('banana',), ('Banana',), ('cherry',)) target=(('Apple',), 
SELECT x FROM (SELECT 'banana' x UNION ALL SELECT 'Apple' x UNION ALL SELECT 'cherry' x UNION ALL SELECT 'Banana' x) t ORDER BY x

-- CASE[open]: my-pad-repeat — fails on oracle, postgresql. ORA-00904: "SPACE": invalid identifier
SELECT LPAD('7',3,'0'),RPAD('7',3,'x'),REPEAT('ab',3),REVERSE('abc'),SPACE(3),CONCAT('[',SPACE(2),']')

-- CASE[open]: my-period-diff — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE
SELECT PERIOD_DIFF(202006, 202001) AS r

-- CASE[open]: my-period2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE
SELECT PERIOD_ADD(202001,14), PERIOD_DIFF(202101,202001)

-- CASE[open]: my-pi-fns — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT TRUNCATE(PI(), 4), ROUND(PI(), 4), FORMAT(PI(), 4)

-- CASE[open]: my-pi-vals — fails on tsql. FUNC-DIFF: source=(('180', '3.14159', '3.14159'),) target=(('180', '3', '3.14159'),)
SELECT DEGREES(PI()), RADIANS(180), PI()

-- CASE[open]: my-quote2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU
SELECT QUOTE('Don\'t!') AS r

-- CASE[open]: my-rand — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RAND(1), RANDOM_BYTES(4), UUID()

-- CASE[open]: my-reads-sql — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE FUNCTION f(a INT) RETURNS INT READS SQL DATA BEGIN RETURN (SELECT COUNT(*) FROM (SELECT a) t); END

-- CASE[open]: my-realworld-orders — fails on postgresql. relation "orders" already exists
CREATE TABLE orders (id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL, total DECIMAL(10,2) DEFAULT 0, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP, INDEX ix_cust (customer_id), CHECK (total >= 0)) ENGINE=InnoDB;
CREATE TRIGGER trg BEFORE INSERT ON orders FOR EACH ROW SET NEW.created = NOW();

-- CASE[open]: my-recursive-cte2 — fails on oracle. ORA-32039: missing column alias list in recursive WITH clause element SEQ
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); WITH RECURSIVE seq AS (SELECT 1 n UNION ALL SELECT n+1 FROM seq WHERE n<10) SELECT * FROM seq

-- CASE[open]: my-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n INT) RETURNS INT DETERMINISTIC BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END

-- CASE[open]: my-repeat-float — fails on tsql. FUNC-DIFF: source=(('ababab',),) target=(('abab',),)
SELECT REPEAT('ab', 2.9) AS r

-- CASE[open]: my-repeat-neg — fails on tsql. FUNC-DIFF: source=(('',),) target=(('NULL',),)
SELECT REPEAT('ab', -1) AS r

-- CASE[open]: my-replace-case — fails on tsql. FUNC-DIFF: source=(('AbCXBc',),) target=(('XbCXBc',),)
SELECT REPLACE('AbCaBc', 'a', 'X') AS r

-- CASE[open]: my-replace-null2 — fails on oracle. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT REPLACE('abc', NULL, 'x') IS NULL AS r

-- CASE[open]: my-round-cast — fails on oracle. ORA-00902: invalid datatype
SELECT CAST(3.99 AS SIGNED),CAST(-3.99 AS SIGNED),CONVERT(3.99,SIGNED)

-- CASE[open]: my-round-fns — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CE
SELECT FLOOR(3.7), CEILING(3.2), ROUND(3.567, 2), TRUNCATE(3.567, 1)

-- CASE[open]: my-scalar-subquery-assign — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE PROCEDURE p() BEGIN DECLARE v INT; SET v = (SELECT COUNT(*) FROM (SELECT 1) t); END

-- CASE[open]: my-select-into-out — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE PROCEDURE p(OUT c INT) BEGIN SELECT COUNT(*) INTO c FROM (SELECT 1) t; END

-- CASE[open]: my-self-fk — fails on tsql. (1785, b"Introducing FOREIGN KEY constraint 'FK__emp__mgr__790A8C33' on table 'emp' may ca
CREATE TABLE emp (id INT PRIMARY KEY, mgr INT, FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL)

-- CASE[open]: my-seq-concat — fails on oracle, postgresql. ORA-32039: missing column alias list in recursive WITH clause element SEQ
WITH RECURSIVE seq AS (SELECT 1 n UNION ALL SELECT n+1 FROM seq WHERE n<10) SELECT GROUP_CONCAT(n) FROM seq

-- CASE[open]: my-session-fns — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'USER'.DB-Lib error message 20018, severity 15:\
CREATE TABLE t (id INT); SELECT LAST_INSERT_ID(),ROW_COUNT(),CONNECTION_ID(),DATABASE(),VERSION(),USER(),CURRENT_USER()

-- CASE[open]: my-set-fns — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI
SELECT FIND_IN_SET('b', 'a,b,c'), MAKE_SET(6, 'x','y','z')

-- CASE[open]: my-set-transaction — fails on oracle. ORA-00900: invalid SQL statement
SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION READ ONLY; COMMIT;

-- CASE[open]: my-soundex-eq — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('hello') = SOUNDEX('hallo') AS r

-- CASE[open]: my-soundex-format — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)

-- CASE[open]: my-spatial — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_AsText(ST_GeomFromText('POINT(1 1)')) AS r

-- CASE[open]: my-st-distance — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_Distance(ST_GeomFromText('POINT(0 0)'), ST_GeomFromText('POINT(3 4)')) AS r

-- CASE[open]: my-st-geojson — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_AsGeoJSON(ST_GeomFromText('POINT(1 1)')) AS r

-- CASE[open]: my-status-funcs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RO
SELECT LAST_INSERT_ID(), ROW_COUNT(), FOUND_ROWS()

-- CASE[open]: my-stmt-digest — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT STATEMENT_DIGEST('SELECT 1'), STATEMENT_DIGEST_TEXT('SELECT 1')

-- CASE[open]: my-str-lt — fails on oracle, postgresql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'apple' < 'Banana' AS r

-- CASE[open]: my-str-misc — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT SOUNDEX('Robert'),FORMAT(1234567.891,2),INSERT('abcd',2,2,'XY'),QUOTE('a''b')

-- CASE[open]: my-str-plus-interval — fails on tsql. FUNC-DIFF: source=(('2020-01-02',),) target=(('2020-01-02 00:00:00',),)
SELECT '2020-01-01' + INTERVAL 1 DAY AS r

-- CASE[open]: my-strnum-add — fails on tsql. FUNC-DIFF: source=(('10',),) target=(('55',),)
SELECT '5'+'5' AS r

-- CASE[open]: my-subdate — fails on tsql. FUNC-DIFF: source=(('2019-12-31',),) target=(('2019-12-31 00:00:00',),)
SELECT SUBDATE('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[open]: my-substr-float — fails on oracle, tsql. FUNC-DIFF: source=(('llo',),) target=(('el',),)
SELECT SUBSTRING('hello', 2.9, 2.9) AS r

-- CASE[open]: my-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('def',),) target=(('ab',),)
SELECT SUBSTRING('abcdef', -3) AS r

-- CASE[open]: my-substr3 — fails on postgresql, tsql. FUNC-DIFF: source=(('bcdef', 'bcd', 'ef'),) target=(('bcdef', 'bcd', 'abc'),)
SELECT SUBSTR('abcdef',2), SUBSTR('abcdef',2,3), SUBSTR('abcdef',-2)

-- CASE[open]: my-substridx-agg — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX(GROUP_CONCAT(x),',',2) FROM (SELECT 1 x UNION SELECT 2 UNION SELECT 3) t

-- CASE[open]: my-substridx-nested — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX(SUBSTRING_INDEX('a,b,c,d', ',', 3), ',', -1) AS r

-- CASE[open]: my-substring-index — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r

-- CASE[open]: my-sum-div-count — fails on postgresql, tsql. FUNC-DIFF: source=(('1.5',),) target=(('1',),)
SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[open]: my-system-funcs — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'USER'.DB-Lib error message 20018, severity 15:\
SELECT CONNECTION_ID(), DATABASE(), USER(), VERSION()

-- CASE[open]: my-time-build — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT CAST('2020-01-01' AS DATETIME) + INTERVAL 90 MINUTE, MAKETIME(10,20,30), SEC_TO_TIME(3661)

-- CASE[open]: my-timestampadd — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT TIMESTAMPADD(MINUTE, 30, '2020-01-01 10:00') AS r

-- CASE[open]: my-timestampdiff — fails on oracle. ORA-01861: literal does not match format string
SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[open]: my-timestampdiff-mon — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10') AS r

-- CASE[open]: my-timestampdiff-year — fails on tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT TIMESTAMPDIFF(YEAR, '2019-12-31', '2020-01-01') AS r

-- CASE[open]: my-timestr-plus — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1900-01-01 13:30:00',),)
SELECT '12:00:00' + INTERVAL 90 MINUTE AS r

-- CASE[open]: my-trailing-eq — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'a ' = 'a' AS r

-- CASE[open]: my-trig — fails on oracle, postgresql, tsql. (174, b'The atan function requires 1 argument(s).DB-Lib error message 20018, severity 15:\
SELECT ATAN2(1,1), ATAN(1,1), DEGREES(PI()), RADIANS(180), COT(1)

-- CASE[open]: my-trig-suite — fails on oracle. ORA-00904: "RADIANS": invalid identifier
SELECT ACOS(1),ASIN(0),ATAN(1),COS(0),SIN(0),TAN(0),COT(1),DEGREES(1),RADIANS(1)

-- CASE[open]: my-trim-both — fails on postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS r

-- CASE[open]: my-trim-edge — fails on postgresql, tsql. FUNC-DIFF: source=(('hi', '7', 'hi'),) target=(('', '', ''),)
SELECT TRIM(BOTH 'x' FROM 'xxhixx'), TRIM(LEADING '0' FROM '007'), TRIM(TRAILING '!' FROM 'hi!!')

-- CASE[open]: my-trim-leading — fails on postgresql, tsql. FUNC-DIFF: source=(('7',),) target=(('',),)
SELECT TRIM(LEADING '0' FROM '007') AS r

-- CASE[open]: my-trim-len — fails on oracle. ORA-30001: trim set should have only one character
SELECT LENGTH(TRIM(BOTH ' ' FROM '  hi  ')),CHAR_LENGTH(RTRIM(' hi '))

-- CASE[open]: my-trim-trailing — fails on postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT TRIM(TRAILING '.' FROM 'abc...') AS r

-- CASE[open]: my-ts-to-date — fails on postgresql. FUNC-DIFF: source=(('2020-01-01',),) target=(('2020-01-01 14:30:00+00:00',),)
SELECT DATE(TIMESTAMP '2020-01-01 14:30') AS r

-- CASE[open]: my-tsadd-quarter — fails on oracle, postgresql. ORA-00904: "QUARTER": invalid identifier
SELECT TIMESTAMPADD(QUARTER,1,NOW()), TIMESTAMPDIFF(QUARTER,'2020-01-01',NOW())

-- CASE[open]: my-unix-timestamp — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)

-- CASE[open]: my-unixtime2 — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT FROM_UNIXTIME(1600000000,'%Y-%m-%d'), UNIX_TIMESTAMP('2020-09-13')

-- CASE[open]: my-upd-selfjoin — fails on oracle, postgresql, tsql. (4104, b'The multi-part identifier "t2.n" could not be bound.DB-Lib error message 20018, s
CREATE TABLE t (id INT, n INT);UPDATE t t1 JOIN t t2 ON t1.id=t2.id+1 SET t1.n=t2.n

-- CASE[open]: my-update-join — fails on oracle, postgresql, tsql. (4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se
CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n

-- CASE[open]: my-upper-sharps — fails on postgresql. FUNC-DIFF: source=(('ß',),) target=(('ẞ',),)
SELECT UPPER('ß') AS r

-- CASE[open]: my-upper-sharps-len — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('2',),) target=(('1',),)
SELECT LENGTH(UPPER('ß')) AS r

-- CASE[open]: my-upper-strasse — fails on postgresql. FUNC-DIFF: source=(('STRAßE',),) target=(('STRAẞE',),)
SELECT UPPER('straße') AS r

-- CASE[open]: my-using-join — fails on tsql. (209, b"Ambiguous column name 'x'.DB-Lib error message 20018, severity 16:\nGeneral SQL Se
SELECT x FROM (SELECT 1 x) a JOIN (SELECT 1 x) b USING (x)

-- CASE[open]: my-uuid-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU
SELECT UUID_TO_BIN(UUID()),BIN_TO_UUID(UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db'))

-- CASE[open]: my-uuid-funcs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU
SELECT UUID(), UUID_SHORT()

-- CASE[open]: my-week-mode — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK('2020-01-01',0), WEEK('2020-01-01',3), WEEKOFYEAR('2020-01-01'), YEARWEEK('2020-01-01')

-- CASE[open]: my-week-modes — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK(NOW(),0), WEEK(NOW(),3), WEEK(NOW(),5), YEARWEEK(NOW(),3)

-- CASE[open]: my-week-quarter — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')

-- CASE[open]: my-weight-string — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEIGHT_STRING('abc') AS r

-- CASE[open]: my-xml-fns — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.Ex
SELECT ExtractValue('<r><a>1</a></r>','/r/a'), UpdateXML('<r><a>1</a></r>','/r/a','<a>2</a>')

-- CASE[open]: my8-lag-nth — fails on oracle. ORA-43853: JSON type cannot be used in non-automatic segment space management tablespace "
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, LAG(n, 1, 0) OVER (ORDER BY id), NTH_VALUE(n, 2) OVER (ORDER BY id) FROM t

-- CASE[open]: my8-recursive — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); WITH RECURSIVE cte AS (SELECT 1 n UNION ALL SELECT n+1 FROM cte WHERE n<5) SELECT * FROM cte

-- CASE[open]: my8-window — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, ROW_NUMBER() OVER w, SUM(n) OVER w FROM t WINDOW w AS (ORDER BY id)

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

-- CASE[open]: mysql-prec-64|BIGINT| — fails on oracle, postgresql. SILENT PRECISION CHANGE: '64|BIGINT|BINARY' not preserved in valid oracle output, no warni
CREATE TABLE t (a BIT(64))

-- CASE[open]: mysql-qdrop-ROLLUP — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ROLLUP' absent from valid tsql output, no warning
SELECT x FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x WITH ROLLUP

-- CASE[open]: mysql-qdrop-SQL_CALC_FOU — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'SQL_CALC_FOUND_ROWS|FOUND' absent from valid tsql output, no warning
SELECT SQL_CALC_FOUND_ROWS x FROM (SELECT 1 x) t LIMIT 1

