# Challenge findings ledger (RED)

Source constructs that transpile wrong on >=1 target, each **validated on a
live engine** (original accepted by its own engine; output rejected by the
target engine, or degraded to an unrecognized carrier). Tagged `[open]` in
the `challenge_<engine>.sql` scripts; BLUE fixes and flips to `[fixed]`.


> **Scope: SILENT defects only.** A construct that degrades WITH a warning is a documented, acceptable outcome — NOT an error — and is excluded (326 warned rows dropped: `Unhandled` carriers and warned-invalid preservations). What remains transpiles wrong with NO warning.

Kinds: **invalid** = live target rejected the output; **func** = runs clean but returns a DIFFERENT result (executed on both engines); **silent-drop** = a clause the target supports vanished, no warning; **carrier** = degraded to an `Unhandled` carrier (BLUE triages); **semantic** = documented divergence.


## Priority classes for BLUE (recurring mechanisms, most severe first)

**A. Silent WRONG RESULTS (func — valid output, different value/rows):**

1. **Integer division** — `5/2`, `1/3` differ (2/0 on T-SQL/PG vs 2.5/0.333 on MySQL/Oracle); propagates through expressions (`1/3*3` = 0 vs 1).

2. **NULL ordering** — bare `ORDER BY x` / DISTINCT / GROUP BY reorders: NULLs FIRST on T-SQL/MySQL vs LAST on PG/Oracle.

3. **String collation** — `ORDER BY <text>`, `=`, `LIKE`, DISTINCT differ by case/accent sensitivity (MySQL CI/AI vs binary elsewhere).

4. **Oracle empty-string-is-NULL** and `||` NULL-as-empty ('a'||NULL='a').

5. **Aggregate integer truncation** (AVG over INT), **CAST float->int** round-vs-truncate, **ROUND(x, n)** precision arg dropped, float length args round vs truncate (REPEAT/SUBSTRING/LEFT).

6. **GREATEST/LEAST/CONCAT NULL** — MySQL returns NULL, others skip.

7. **LENGTH bytes vs chars**, **T-SQL LEN** ignores trailing spaces.

8. **Date arithmetic** — Oracle `date+1` = +1 day; MySQL `date-date` = numeric; `+` string-concat vs numeric; `TOP n WITH TIES` dropped; LOG base; `~0` sign.


**B. Silent CLAUSE DROPS (silent-drop — data integrity):**

9. FK `ON DELETE/UPDATE` actions; CHECK constraints; COLLATE / CHARACTER SET; IDENTITY/sequence seed (START WITH); UNSIGNED; window `ROWS/RANGE BETWEEN` frame; `WITH ROLLUP`; EXCLUDE constraint; column COMMENT; MySQL BIT(64)->1-bit.


**C. Invalid output, no warning (invalid):** unmapped scalar functions emit verbatim (STUFF, CHOOSE, AGE, DATE_TRUNC, OVERLAY, ADD_MONTHS, …) or an invented name (FORMAT -> NUMBER_TO_STR); most cross-engine function/type gaps.


---


## my-accent-eq  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'Ä' = 'A' AS r`

## my-aes  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE`
- src: `SELECT HEX(AES_ENCRYPT('data', 'key')) AS r`

## my-alter-drop-default  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'DEFAULT'.DB-Lib error message 20018, severity 1`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP DEFAULT`

## my-alter-modify  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT`

## my-alter-set-default  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5`

## my-any-value  (mysql)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '>'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `SELECT ANY_VALUE(x), GROUP_CONCAT(x) FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x>0`

## my-ascii-empty  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('NULL',),)`
- src: `SELECT ASCII('') AS r`

## my-avg-int  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t`

## my-avg-precision2  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.6667',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 2) t`

## my-base64  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO`
- src: `SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')`

## my-benchmark  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BE`
- src: `SELECT BENCHMARK(1, 1+1) AS r`

## my-binary-substr  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN`
- src: `SELECT SUBSTRING(UNHEX('48656C6C6F'), 1, 2) AS r`

## my-bit-agg  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI`
- src: `SELECT BIT_XOR(x), BIT_OR(x) FROM (SELECT 1 x UNION SELECT 2) t`

## my-bit-count  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI`
- src: `SELECT BIT_COUNT(255) AS r`

## my-bit-fns  (mysql)
- targets: postgresql(invalid)
- live error: `function bitwise_count(bit) does not exist`
- src: `SELECT BIT_COUNT(b'1011'), BIT_LENGTH('a'), OCTET_LENGTH('ab')`

## my-bitnot  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('18446744073709551616',),) target=(('-1',),)`
- src: `SELECT ~0 AS r`

## my-blob-length  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO`
- src: `CREATE TABLE t (data BLOB); INSERT INTO t VALUES (LOAD_FILE('/x')); SELECT LENGTH(data) FROM t`

## my-bool-char  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('t',),)`
- src: `SELECT CAST((1=1) AS CHAR) AS r`

## my-cast-charset  (mysql)
- targets: oracle(invalid)
- live error: `ORA-25137: Data value out of range`
- src: `SELECT CAST(0xC3A9 AS CHAR CHARACTER SET utf8mb4) AS r`

## my-cast-convert  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:`
- src: `SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)`

## my-cast-datetime  (mysql)
- targets: oracle(invalid)
- live error: `ORA-01843: An invalid month was specified.`
- src: `SELECT CAST('2020-01-01' AS DATETIME) AS r`

## my-cast-hex-char  (mysql)
- targets: oracle(invalid)
- live error: `ORA-25137: Data value out of range`
- src: `SELECT CAST(0xFF AS CHAR) AS r`

## my-cast-int  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT CAST(2.7 AS SIGNED) AS r`

## my-cast-num-char  (mysql)
- targets: oracle(invalid)
- live error: `ORA-25137: Data value out of range`
- src: `SELECT CAST(1234.5 AS CHAR) AS r`

## my-cast-time  (mysql)
- targets: oracle(invalid)
- live error: `DPY-3006: Oracle data type 178 is not supported`
- src: `SELECT CAST('10:00:00' AS TIME) AS r`

## my-change-column  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'CHANGE'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t CHANGE a x INT`

## my-char-256  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('0100',),) target=(('\x01\x00',),)`
- src: `SELECT CHAR(256) AS r`

## my-char-unicode  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('μ',),)`
- src: `SELECT CHAR(956 USING utf8mb4) AS r`

## my-check-enforced  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'ENFORCED'.DB-Lib error message 20018, severity 15:\nGeneral`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) ENFORCED`

## my-coalesce-empty  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('NULL',),)`
- src: `SELECT COALESCE(NULL, 0) = '' AS r`

## my-collation-fn  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('utf8mb4_0900_ai_ci',),) target=(('USING_NLS_COMP',),)`
- src: `SELECT COLLATION('abc') AS r`

## my-compress  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN`
- src: `SELECT UNCOMPRESS(COMPRESS('data')) AS r`

## my-computed-json  (mysql)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(195, b"'JSON_UNQUOTE' is not a recognized built-in function name.DB-Lib error message 200`
- src: `CREATE TABLE t (data JSON, name VARCHAR(50) AS (JSON_UNQUOTE(JSON_EXTRACT(data, '$.name'))) VIRTUAL)`

## my-concat-bool  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('10',),) target=(('tf',),)`
- src: `SELECT CONCAT(TRUE, FALSE) AS r`

## my-concat-date  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('2020-01-01',),) target=(('01-JAN-20',),)`
- src: `SELECT CONCAT(DATE '2020-01-01', '') AS r`

## my-concat-null  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('ab',),)`
- src: `SELECT CONCAT('a', NULL, 'b') AS r`

## my-concat-ws  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00904: "CONCAT_WS": invalid identifier`
- src: `SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r`

## my-conv2  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO`
- src: `SELECT CONV('7F', 16, 2), CONV(255, 10, 16)`

## my-convert-signed  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CONVERT('123', SIGNED) AS r`

## my-convert-tz  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO`
- src: `SELECT CONVERT_TZ('2020-01-01 10:00', '+00:00', '+02:00') AS r`

## my-crc32  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR`
- src: `SELECT CRC32('abc') AS r`

## my-date-add-interval  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-30081: invalid data type for datetime/interval arithmetic`
- src: `SELECT DATE_ADD('2020-01-01', INTERVAL 7 DAY) AS r`

## my-date-add-month  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)`
- src: `SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r`

## my-date-diff-minus  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('200',),) target=(('60',),)`
- src: `SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r`

## my-date-eq-dt  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT DATE('2020-01-01') = '2020-01-01 00:00:00' AS r`

## my-date-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r`

## my-dateformat-iso  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT DATE_FORMAT('2020-06-15 14:30:45', '%Y-%m-%dT%H:%i:%s') AS r`

## my-dateformat-long  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT DATE_FORMAT('2020-06-15', '%W, %M %D, %Y') AS r`

## my-datetime-precision  (mysql)
- targets: tsql(invalid)
- live error: `(2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat`
- src: `CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)`

## my-distinct-case  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('a',), ('B',)) target=(('A',), ('B',))`
- src: `SELECT DISTINCT x FROM (SELECT 'a' x UNION ALL SELECT 'A' x UNION ALL SELECT 'a' x UNION ALL SELECT 'B' x) t ORDER BY x`

## my-div  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.5',),) target=(('2',),)`
- src: `SELECT 5 / 2 AS r`

## my-div-mult2  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 1/3*3 AS r`

## my-div-precision  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0.33333',),) target=(('0.333333',),)`
- src: `SELECT 1.0 / 3 AS r`

## my-elt  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EL`
- src: `SELECT ELT(2, 'a', 'b', 'c') AS r`

## my-emoji-len  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT CHAR_LENGTH('😀') AS r`

## my-empty-eq-zero  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('NULL',),)`
- src: `SELECT '' = 0 AS r`

## my-eq-mix  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1', '0', '1'),) target=(('1', '1', '1'),)`
- src: `SELECT 1 = 1.0 AS r, 'a' = 'a ' AS b, 1 = TRUE AS c`

## my-export-set  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX`
- src: `SELECT EXPORT_SET(5, 'Y', 'N', ',', 4) AS r`

## my-extractvalue  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX`
- src: `SELECT EXTRACTVALUE('<a>1</a>', '/a') AS r`

## my-field  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI`
- src: `SELECT FIELD('b', 'a', 'b', 'c') AS r`

## my-floor-precision  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('3',),)`
- src: `SELECT FLOOR(2.9999999999999999) AS r`

## my-full-select  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t GROUP BY id HAVING COUNT(*) > 1 ORDER`

## my-gc-order  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('3,1,2',),) target=(('1,2,3',),)`
- src: `SELECT GROUP_CONCAT(x) FROM (SELECT 3 x UNION ALL SELECT 1 x UNION ALL SELECT 2 x) t`

## my-get-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE`
- src: `SELECT GET_FORMAT(DATE, 'USA'), GET_FORMAT(DATETIME, 'ISO')`

## my-get-lock  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE`
- src: `SELECT GET_LOCK('l', 0), RELEASE_LOCK('l')`

## my-greatest-null  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('3',),)`
- src: `SELECT GREATEST(1, NULL, 3) AS r`

## my-greatest-null2  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('1',),)`
- src: `SELECT GREATEST(NULL, 1) AS r`

## my-greatest-string  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('B',),) target=(('a',),)`
- src: `SELECT GREATEST('a', 'B') AS r`

## my-group-case  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('a', '2'), ('b', '1')) target=(('A', '2'), ('b', '1'))`
- src: `SELECT x, COUNT(*) FROM (SELECT 'a' x UNION ALL SELECT 'A' x UNION ALL SELECT 'b' x) t GROUP BY x ORDER BY x`

## my-group-concat  (mysql)
- targets: postgresql(invalid)
- live error: `function string_agg(integer, unknown) does not exist`
- src: `SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t`

## my-hash  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT MD5('abc'), SHA1('abc'), SHA2('abc', 256)`

## my-hex-bin  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE`
- src: `SELECT HEX(255) AS r, BIN(5) AS b`

## my-inet  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN`
- src: `SELECT INET_ATON('127.0.0.1'), INET_NTOA(2130706433)`

## my-insert-oob  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('abc',),) target=(('NULL',),)`
- src: `SELECT INSERT('abc', 10, 1, 'X') AS r`

## my-instr-case  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT INSTR('aAaA', 'A') AS r`

## my-int-or-empty  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('NULL',),)`
- src: `SELECT 0 OR '' AS r`

## my-is-true  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'IS'.DB-Lib error message 20018, severity 15:\nG`
- src: `SELECT 1 IN (SELECT 1) IS TRUE AS r`

## my-json-aggs  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAYAGG(x), JSON_OBJECTAGG(x, x*2) FROM (SELECT 1 x UNION SELECT 2) t`

## my-json-array-ops  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAY_APPEND('[1,2]', '$', 3), JSON_ARRAY_INSERT('[1,2]', '$[0]', 0)`

## my-json-arrayagg  (mysql)
- targets: tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION SELECT 2) t`

## my-json-fns2  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_SEARCH('{"a":"x"}', 'one', 'x'), JSON_DEPTH('[1,[2]]'), JSON_LENGTH('[1,2,3]')`

## my-json-keys  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_KEYS('{"a":1,"b":2}') AS r`

## my-json-merge  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_MERGE_PATCH('{"a":1}', '{"b":2}') AS r`

## my-json-object  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_`
- src: `SELECT JSON_OBJECT('a', 1, 'b', 2)`

## my-json-type  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (data JSON)`

## my-last-day-name  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT LAST_DAY('2020-02-15'), DAYNAME('2020-06-15'), MONTHNAME('2020-06-15')`

## my-lastday-extract  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT LAST_DAY('2020-02-15'), EXTRACT(DAY FROM LAST_DAY('2020-02-15'))`

## my-least-null2  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('1',),)`
- src: `SELECT LEAST(1, 2, NULL, 3) AS r`

## my-left-float  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('hel',),) target=(('he',),)`
- src: `SELECT LEFT('hello', 2.9) AS r`

## my-left-neg  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('',),) target=(('ab',),)`
- src: `SELECT LEFT('abc', -1) AS r`

## my-length-bytes  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('5',),) target=(('4',),)`
- src: `SELECT LENGTH('café') AS r`

## my-length-div  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('6',),) target=(('1',),)`
- src: `SELECT LENGTH(1/3) AS r`

## my-like-ci  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'ABC' LIKE 'abc' AS r`

## my-like-escape  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'a_b' LIKE 'a\_b' AS r`

## my-like-single  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'x' LIKE 'X' AS r`

## my-locate-case  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT LOCATE('a', 'ABC') AS r`

## my-locate-empty  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT LOCATE('', '') AS r`

## my-log-2arg  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('0.333333',),)`
- src: `SELECT LOG(2, 8) AS r`

## my-log2-log10  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3', '3'),) target=(('0.333333', '0.333333'),)`
- src: `SELECT LOG2(8), LOG10(1000)`

## my-lpad-multichar  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('xyxab',),) target=(('yxyab',),)`
- src: `SELECT LPAD('ab', 5, 'xy') AS r`

## my-lpad-trunc  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('bc',),)`
- src: `SELECT LPAD('abc', 2, 'x') AS r`

## my-make-set  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT MAKE_SET(3, 'a', 'b', 'c') AS r`

## my-makedate  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT MAKEDATE(2020, 100), MAKETIME(10, 30, 0)`

## my-month-overflow  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)`
- src: `SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r`

## my-name-const  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA`
- src: `SELECT NAME_CONST('col', 5) AS r`

## my-nested-call  (mysql)
- targets: oracle(invalid)
- live error: `PROCEDURE P compiled INVALID (line 4): PLS-00201: identifier 'OTHER_PROC' must be declared`
- src: `CREATE PROCEDURE p() BEGIN CALL other_proc(); END`

## my-numeric  (mysql)
- targets: tsql(invalid)
- live error: `(2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)`

## my-optimizer-hints  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT /*+ QB_NAME(qb1) */ id FROM t WHERE n > (SELECT`

## my-order-strings  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('Apple',), ('banana',), ('Banana',), ('cherry',)) target=(('Apple',), `
- src: `SELECT x FROM (SELECT 'banana' x UNION ALL SELECT 'Apple' x UNION ALL SELECT 'cherry' x UNION ALL SELECT 'Banana' x) t ORDER BY x`

## my-period-diff  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE`
- src: `SELECT PERIOD_DIFF(202006, 202001) AS r`

## my-reads-sql  (mysql)
- targets: tsql(invalid)
- live error: `(8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve`
- src: `CREATE FUNCTION f(a INT) RETURNS INT READS SQL DATA BEGIN RETURN (SELECT COUNT(*) FROM (SELECT a) t); END`

## my-realworld-orders  (mysql)
- targets: postgresql(invalid)
- live error: `relation "orders" already exists`
- src: `CREATE TABLE orders (id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL, total DECIMAL(10,2) DEFAULT 0, created TIMESTAMP`

## my-recursive-cte2  (mysql)
- targets: oracle(invalid)
- live error: `ORA-32039: missing column alias list in recursive WITH clause element SEQ`
- src: `CREATE TABLE t (id INT, n INT, s VARCHAR(50)); WITH RECURSIVE seq AS (SELECT 1 n UNION ALL SELECT n+1 FROM seq WHERE n<10) SELECT`

## my-recursive-func  (mysql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS INT DETERMINISTIC BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END`

## my-repeat-float  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('ababab',),) target=(('abab',),)`
- src: `SELECT REPEAT('ab', 2.9) AS r`

## my-repeat-neg  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('',),) target=(('NULL',),)`
- src: `SELECT REPEAT('ab', -1) AS r`

## my-replace-case  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('AbCXBc',),) target=(('XbCXBc',),)`
- src: `SELECT REPLACE('AbCaBc', 'a', 'X') AS r`

## my-replace-null2  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT REPLACE('abc', NULL, 'x') IS NULL AS r`

## my-scalar-subquery-assign  (mysql)
- targets: tsql(invalid)
- live error: `(8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve`
- src: `CREATE PROCEDURE p() BEGIN DECLARE v INT; SET v = (SELECT COUNT(*) FROM (SELECT 1) t); END`

## my-select-into-out  (mysql)
- targets: tsql(invalid)
- live error: `(8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve`
- src: `CREATE PROCEDURE p(OUT c INT) BEGIN SELECT COUNT(*) INTO c FROM (SELECT 1) t; END`

## my-set-fns  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI`
- src: `SELECT FIND_IN_SET('b', 'a,b,c'), MAKE_SET(6, 'x','y','z')`

## my-soundex-eq  (mysql)
- targets: postgresql(invalid)
- live error: `function soundex(unknown) does not exist`
- src: `SELECT SOUNDEX('hello') = SOUNDEX('hallo') AS r`

## my-soundex-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)`

## my-spatial  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT ST_AsText(ST_GeomFromText('POINT(1 1)')) AS r`

## my-st-distance  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT ST_Distance(ST_GeomFromText('POINT(0 0)'), ST_GeomFromText('POINT(3 4)')) AS r`

## my-st-geojson  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT ST_AsGeoJSON(ST_GeomFromText('POINT(1 1)')) AS r`

## my-status-funcs  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RO`
- src: `SELECT LAST_INSERT_ID(), ROW_COUNT(), FOUND_ROWS()`

## my-str-lt  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'apple' < 'Banana' AS r`

## my-str-plus-interval  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2020-01-02',),) target=(('2020-01-02 00:00:00',),)`
- src: `SELECT '2020-01-01' + INTERVAL 1 DAY AS r`

## my-strnum-add  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('10',),) target=(('55',),)`
- src: `SELECT '5'+'5' AS r`

## my-substr-float  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('llo',),) target=(('el',),)`
- src: `SELECT SUBSTRING('hello', 2.9, 2.9) AS r`

## my-substr-neg  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('def',),) target=(('ab',),)`
- src: `SELECT SUBSTRING('abcdef', -3) AS r`

## my-substring-index  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU`
- src: `SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r`

## my-sum-div-count  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t`

## my-system-funcs  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'USER'.DB-Lib error message 20018, severity 15:\`
- src: `SELECT CONNECTION_ID(), DATABASE(), USER(), VERSION()`

## my-timestampadd  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-30081: invalid data type for datetime/interval arithmetic`
- src: `SELECT TIMESTAMPADD(MINUTE, 30, '2020-01-01 10:00') AS r`

## my-timestampdiff  (mysql)
- targets: oracle(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r`

## my-timestampdiff-mon  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10') AS r`

## my-timestampdiff-year  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT TIMESTAMPDIFF(YEAR, '2019-12-31', '2020-01-01') AS r`

## my-timestr-plus  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('1900-01-01 13:30:00',),)`
- src: `SELECT '12:00:00' + INTERVAL 90 MINUTE AS r`

## my-trailing-eq  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'a ' = 'a' AS r`

## my-trim-both  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('abc',),) target=(('',),)`
- src: `SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS r`

## my-trim-leading  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('7',),) target=(('',),)`
- src: `SELECT TRIM(LEADING '0' FROM '007') AS r`

## my-ts-to-date  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('2020-01-01',),) target=(('2020-01-01 14:30:00+00:00',),)`
- src: `SELECT DATE(TIMESTAMP '2020-01-01 14:30') AS r`

## my-unix-timestamp  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2`
- src: `SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)`

## my-update-join  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n`

## my-upper-sharps  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('ß',),) target=(('ẞ',),)`
- src: `SELECT UPPER('ß') AS r`

## my-upper-sharps-len  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('1',),)`
- src: `SELECT LENGTH(UPPER('ß')) AS r`

## my-upper-strasse  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('STRAßE',),) target=(('STRAẞE',),)`
- src: `SELECT UPPER('straße') AS r`

## my-uuid-funcs  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU`
- src: `SELECT UUID(), UUID_SHORT()`

## my-week-quarter  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE`
- src: `SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')`

## my-weight-string  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE`
- src: `SELECT WEIGHT_STRING('abc') AS r`

## my8-lag-nth  (mysql)
- targets: oracle(invalid)
- live error: `ORA-43853: JSON type cannot be used in non-automatic segment space management tablespace "`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, LAG(n, 1, 0) OVER (ORDER BY id), NTH_VALUE(n`

## my8-recursive  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); WITH RECURSIVE cte AS (SELECT 1 n UNION ALL SELECT n+1`

## my8-window  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, ROW_NUMBER() OVER w, SUM(n) OVER w FROM t WI`

## mysql-drop-'note'|note  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: ''note'|note' absent from valid oracle output, no warning (target supp`
- src: `CREATE TABLE t (a INT COMMENT 'note')`

## mysql-drop-CHECK  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)`
- src: `CREATE TABLE t (email VARCHAR(255) CHECK (email LIKE '%@%'))`

## mysql-drop-GENERATED|AS\s  (mysql)
- targets: tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'GENERATED|AS\s*\(' absent from valid tsql output, no warning (target `
- src: `CREATE TABLE t (a INT, b INT AS (a+1) STORED)`

## mysql-drop2-ON\s+UPDATE  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ON\s+UPDATE' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)`

## mysql-drop2-latin1|CHARA  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'latin1|CHARACTER\s+SET' absent from valid postgresql output, no warni`
- src: `CREATE TABLE t (a VARCHAR(10) CHARACTER SET latin1)`

## mysql-drop2-my table|COM  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'my table|COMMENT' absent from valid postgresql output, no warning`
- src: `CREATE TABLE t (a INT) COMMENT='my table'`

## mysql-drop4-50|IDENTITY|  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: '50|IDENTITY|START' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT PRIMARY KEY) AUTO_INCREMENT = 50`

## mysql-drop4-COLLATE|utf8  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'COLLATE|utf8mb4' absent from valid postgresql output, no warning`
- src: `CREATE TABLE t (a INT) COLLATE=utf8mb4_unicode_ci`

## mysql-drop4-UNSIGNED|CHE  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'UNSIGNED|CHECK' absent from valid postgresql output, no warning`
- src: `CREATE TABLE t (a INT UNSIGNED)`

## mysql-drop4-ZEROFILL|LPA  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ZEROFILL|LPAD' absent from valid postgresql output, no warning`
- src: `CREATE TABLE t (a INT ZEROFILL)`

## mysql-drop5-utf8mb4|CHAR  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'utf8mb4|CHARSET' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT AUTO_INCREMENT PRIMARY KEY, b VARCHAR(20)) DEFAULT CHARSET=utf8mb4`

## mysql-prec-64|BIGINT|  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT PRECISION CHANGE: '64|BIGINT|BINARY' not preserved in valid oracle output, no warni`
- src: `CREATE TABLE t (a BIT(64))`

## mysql-qdrop-ROLLUP  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ROLLUP' absent from valid tsql output, no warning`
- src: `SELECT x FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x WITH ROLLUP`

## mysql-qdrop-SQL_CALC_FOU  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'SQL_CALC_FOUND_ROWS|FOUND' absent from valid tsql output, no warning`
- src: `SELECT SQL_CALC_FOUND_ROWS x FROM (SELECT 1 x) t LIMIT 1`

## or-distinct-null  (oracle)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',), ('2',), ('NULL',)) target=(('NULL',), ('1',), ('2',))`
- src: `SELECT DISTINCT x FROM (SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NUL`

## or-order-strings  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), `
- src: `SELECT x FROM (SELECT 'banana' x FROM DUAL UNION ALL SELECT 'Apple' x FROM DUAL UNION ALL SELECT 'cherry' x FROM DUAL UNION ALL SE`

## ora-add-months  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL`

## ora-bit-fns  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT BITAND(12, 10), BIN_TO_NUM(1,1,0) FROM DUAL`

## ora-bitand  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT BITAND(5, 3) AS r FROM DUAL`

## ora-case-statement  (oracle)
- targets: tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'ELSE'.DB-Lib error message 20018, severity 15:\`
- src: `CREATE PROCEDURE p (n IN NUMBER) AS BEGIN CASE n WHEN 1 THEN NULL; ELSE NULL; END CASE; END;
/`

## ora-cast-expr  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL`

## ora-cast-onerror  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit`
- src: `SELECT CAST('abc' AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM DUAL`

## ora-clob-coalesce  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT COALESCE(TO_CLOB('a'), TO_CLOB('b')) AS r FROM DUAL`

## ora-collect  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO`
- src: `SELECT CAST(COLLECT(x) AS SYS.ODCINUMBERLIST) FROM (SELECT 1 x FROM DUAL)`

## ora-concat-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('NULL',),)`
- src: `SELECT 'a' || NULL || 'b' AS r FROM DUAL`

## ora-concat-num  (oracle)
- targets: tsql(invalid)
- live error: `(245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er`
- src: `SELECT 'a' || 5 AS r FROM DUAL`

## ora-cursor  (oracle)
- targets: mysql(invalid)
- live error: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;`

## ora-cursor-for-loop  (oracle)
- targets: tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/`

## ora-date-diff-days  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('60',),) target=(('0',),)`
- src: `SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r FROM DUAL`

## ora-date-plus-int  (oracle)
- targets: mysql(semantic), postgresql(invalid)
- live error: `SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith`
- src: `SELECT SYSDATE + 1 AS r FROM DUAL`

## ora-date-plus-int2  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2020-01-31 00:00:00',),) target=(('2050',),)`
- src: `SELECT DATE '2020-01-01' + 30 AS r FROM DUAL`

## ora-day-of-week  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('24',),)`
- src: `SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL`

## ora-decode-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('match',),) target=(('no',),)`
- src: `SELECT DECODE(NULL, NULL, 'match', 'no') AS r FROM DUAL`

## ora-div  (oracle)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.5',),) target=(('2',),)`
- src: `SELECT 5 / 2 AS r FROM DUAL`

## ora-div-mult2  (oracle)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 1/3*3 AS r FROM DUAL`

## ora-div-precision  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0.333333',),) target=(('0',),)`
- src: `SELECT 1 / 3 AS r FROM DUAL`

## ora-dump  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU`
- src: `SELECT DUMP('abc') AS r FROM DUAL`

## ora-dump2  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU`
- src: `SELECT DUMP('A', 1016) AS r FROM DUAL`

## ora-edit-distance  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "UTL_MATCH" or the user-defined function or aggregate "`
- src: `SELECT UTL_MATCH.EDIT_DISTANCE('hello', 'hallo') AS r FROM DUAL`

## ora-empty-is-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT CASE WHEN '' IS NULL THEN 1 ELSE 0 END AS r FROM DUAL`

## ora-empty-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('x',),) target=(('',),)`
- src: `SELECT NVL('', 'x') AS r FROM DUAL`

## ora-extractvalue  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX`
- src: `SELECT EXTRACTVALUE(XMLTYPE('<a>1</a>'), '/a') AS r FROM DUAL`

## ora-fmt-dayname  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('MONDAY',),) target=(('Monday',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-15', 'DAY') AS r FROM DUAL`

## ora-fmt-quarter  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('Q',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-15', 'Q') AS r FROM DUAL`

## ora-fmt-week  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('24',),) target=(('Monday',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-15', 'WW') AS r FROM DUAL`

## ora-for-update-nowait  (oracle)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT`

## ora-from-tz  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR`
- src: `SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL`

## ora-functional-index  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '*'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `CREATE TABLE t (a NUMBER); CREATE INDEX ix ON t (a * 2)`

## ora-hint-comment  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT /*+ FULL(t) */ 1 AS r FROM DUAL t`

## ora-initcap  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT INITCAP('hello world') AS r FROM DUAL`

## ora-insert-append  (oracle)
- targets: postgresql(invalid)
- live error: `validator-crash: sending query failed: another command is already in progress`
- src: `CREATE TABLE t (a NUMBER); INSERT /*+ APPEND */ INTO t SELECT 1 FROM DUAL`

## ora-instr-case  (oracle)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('1',),)`
- src: `SELECT INSTR('aAaA', 'A') AS r FROM DUAL`

## ora-interval-tochar  (oracle)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('+02 03:04:05.000000',),) target=(('2 days 03:04:05',),)`
- src: `SELECT TO_CHAR(INTERVAL '2 3:04:05.000' DAY TO SECOND) AS r FROM DUAL`

## ora-json-value  (oracle)
- targets: postgresql(invalid), tsql(silent-rt)
- live error: `SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'"] lost after oracle->tsql->oracle`
- src: `SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL`

## ora-last-day  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT LAST_DAY(SYSDATE) AS r FROM DUAL`

## ora-length-trailing  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('6',),) target=(('3',),)`
- src: `SELECT LENGTH('abc   ') AS r FROM DUAL`

## ora-listagg  (oracle)
- targets: postgresql(invalid)
- live error: `function string_agg(integer, unknown) does not exist`
- src: `SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)`

## ora-listagg-over  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4113, b"The function 'STRING_AGG' is not a valid windowing function, and cannot be used w`
- src: `SELECT deptno, LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) OVER (PARTITION BY deptno) FROM (SELECT 1 deptno, 2 x FROM DUAL)`

## ora-lnnvl  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '='.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `SELECT LNNVL(1 = 2) AS r FROM DUAL WHERE LNNVL(1 = 2)`

## ora-lob-length  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT DBMS_LOB.GETLENGTH(TO_CLOB('hello')) AS r FROM DUAL`

## ora-lpad-multichar  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('xyxab',),) target=(('yxyab',),)`
- src: `SELECT LPAD('ab', 5, 'xy') AS r FROM DUAL`

## ora-ltrim-set  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('abc',),) target=(('',),)`
- src: `SELECT LTRIM('xxabc', 'x') AS r FROM DUAL`

## ora-median-mode  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ME`
- src: `SELECT MEDIAN(x), STATS_MODE(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 1 FROM DUAL UNION ALL SELECT 2 FROM DUAL)`

## ora-month-name  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('June',),) target=(('Month',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-01', 'Month') AS r FROM DUAL`

## ora-months-between  (oracle)
- targets: mysql(invalid), postgresql(invalid)
- live error: `operator does not exist: timestamp with time zone - integer`
- src: `SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL`

## ora-months-between-val  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1.83871',),) target=(('2',),)`
- src: `SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL`

## ora-nanvl  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA`
- src: `SELECT NANVL(0/1, 0) AS r FROM DUAL`

## ora-nchr-unistr  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NC`
- src: `SELECT NCHR(233), UNISTR('\00e9') FROM DUAL`

## ora-next-day  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL`

## ora-nlssort  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NL`
- src: `SELECT NLSSORT('abc', 'NLS_SORT=BINARY_CI') AS r FROM DUAL`

## ora-num-concat  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('23',),) target=(('5',),)`
- src: `SELECT 2 || 3 AS r FROM DUAL`

## ora-numfmt-lead  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.5',),) target=(('0',),)`
- src: `SELECT TO_CHAR(0.5, '0.00') AS r FROM DUAL`

## ora-numfmt-sign  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('-42',),) target=(('NULL',),)`
- src: `SELECT TO_CHAR(-42, 'S999') AS r FROM DUAL`

## ora-numfmt-thousands  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1,234,567.89',),) target=(('NULL',),)`
- src: `SELECT TO_CHAR(1234567.891, '9,999,999.99') AS r FROM DUAL`

## ora-numtodsinterval  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL`

## ora-ora-hash  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'ORA_HASH' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT ORA_HASH('abc') AS r FROM DUAL`

## ora-order-nulls-default  (oracle)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))`
- src: `SELECT x FROM (SELECT 3 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL) ORDER BY x`

## ora-pk-using-index  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(1018, b"Incorrect syntax near 'INDEX'. If this is intended as a part of a table hint, A W`
- src: `CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)`

## ora-ratio-to-report  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA`
- src: `SELECT RATIO_TO_REPORT(x) OVER () FROM (SELECT 1 x FROM DUAL)`

## ora-ratio2  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA`
- src: `SELECT RATIO_TO_REPORT(1) OVER () FROM DUAL`

## ora-rawtohex  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'RAWTOHEX' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT RAWTOHEX('AB'), HEXTORAW('4142') FROM DUAL`

## ora-recursive-func  (oracle)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/`

## ora-regexp-count  (oracle)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')`
- src: `SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL`

## ora-regexp-group  (oracle)
- targets: mysql(invalid)
- live error: `(1582, "Incorrect parameter count in the call to native function 'REGEXP_SUBSTR'")`
- src: `SELECT REGEXP_SUBSTR('a1b2c3', '(\d)', 1, 1, NULL, 1) AS r FROM DUAL`

## ora-round-date-month  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2020-07-01 00:00:00',),) target=(('2020',),)`
- src: `SELECT ROUND(DATE '2020-06-16', 'MONTH') AS r FROM DUAL`

## ora-rtrim-chars  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('a',),) target=(('',),)`
- src: `SELECT RTRIM('axxx', 'x') AS r FROM DUAL`

## ora-sequence-options  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'NOCYCLE'.DB-Lib error message 20018, severity 15:\nGeneral `
- src: `CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE ORDER`

## ora-soundex  (oracle)
- targets: postgresql(invalid)
- live error: `function soundex(unknown) does not exist`
- src: `SELECT SOUNDEX('Smith') AS r FROM DUAL`

## ora-substr-neg  (oracle)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('de',),) target=(('',),)`
- src: `SELECT SUBSTR('abcdef', -3, 2) AS r FROM DUAL`

## ora-sys-extract-utc  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SY`
- src: `SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) AS r FROM DUAL`

## ora-table-collection  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:`
- src: `SELECT * FROM TABLE(SYS.ODCINUMBERLIST(1,2,3))`

## ora-table-varchar-list  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:`
- src: `SELECT COLUMN_VALUE FROM TABLE(SYS.ODCIVARCHAR2LIST('a','b','c'))`

## ora-to-char-day  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('SUNDAY',),) target=(('Sunday',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-14', 'DAY') AS r FROM DUAL`

## ora-to-number-sci  (oracle)
- targets: tsql(invalid)
- live error: `(8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit`
- src: `SELECT TO_NUMBER('1.234E2') AS r FROM DUAL`

## ora-to-timestamp  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT TO_TIMESTAMP('2020-01-01 10:00:00.123', 'YYYY-MM-DD HH24:MI:SS.FF') AS r FROM DUAL`

## ora-tochar-iso  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT TO_CHAR(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r FROM DUAL`

## ora-tochar-long  (oracle)
- targets: mysql(silent), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT TO_CHAR(DATE '2020-06-15', 'Day, Month DD, YYYY') AS r FROM DUAL`

## ora-tochar-neg  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('-1234.5',),) target=(('NULL',),)`
- src: `SELECT TO_CHAR(-1234.5, '9999.99') AS r FROM DUAL`

## ora-trailing-eq  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT CASE WHEN 'a ' = 'a' THEN 1 ELSE 0 END AS r FROM DUAL`

## ora-translate  (oracle)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_6c47c43e12f3.TRANSLATE does not exist')`
- src: `SELECT TRANSLATE('abc', 'ab', 'xy') AS r FROM DUAL`

## ora-tz-funcs  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO`
- src: `SELECT SYSTIMESTAMP, LOCALTIMESTAMP, SESSIONTIMEZONE FROM DUAL`

## ora-tz-interval  (oracle)
- targets: tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL `
- src: `CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)`

## ora-user-context  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'SYS_CONTEXT' is not a recognized built-in function name.DB-Lib error message 2001`
- src: `SELECT USER, SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL`

## ora-utl-raw  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "UTL_RAW" or the user-defined function or aggregate "UT`
- src: `SELECT UTL_RAW.CAST_TO_RAW('abc') AS r FROM DUAL`

## ora-vsize  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.VS`
- src: `SELECT VSIZE(123) AS r FROM DUAL`

## ora-width-bucket  (oracle)
- targets: mysql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI`
- src: `SELECT WIDTH_BUCKET(5, 0, 10, 5) AS r FROM DUAL`

## ora-xmlelement  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT XMLELEMENT("foo", 'bar') AS r FROM DUAL`

## ora-zero-divide  (oracle)
- targets: postgresql(invalid)
- live error: `unrecognized exception condition "zero_divide"`
- src: `CREATE PROCEDURE p AS v NUMBER; BEGIN v := 1/0; EXCEPTION WHEN ZERO_DIVIDE THEN v := 0; END;
/`

## ora23-json-object-star  (oracle)
- targets: postgresql(invalid)
- live error: `function j_s_o_n_object() does not exist`
- src: `CREATE TABLE t (id NUMBER, n NUMBER); CREATE TABLE s (id NUMBER, n NUMBER);
SELECT JSON_OBJECT(*) FROM t`

## oracle-drop2-100|START  (oracle)
- targets: postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (id NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100))`

## oracle-drop4-COLLATE  (oracle)
- targets: mysql(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a VARCHAR2(10) COLLATE BINARY_CI)`

## pg-accent-eq  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'Ä' = 'A' AS r`

## pg-age  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a`

## pg-all-values  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t WHERE n > ALL (VALUES (1),(2),(3))`

## pg-alter-add  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'`

## pg-alter-type  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01735: invalid ALTER TABLE option`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a TYPE BIGINT`

## pg-alter-using  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01735: invalid ALTER TABLE option`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DATA TYPE BIGINT USING a::bigint`

## pg-any-array-subquery  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'ARRAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ`
- src: `CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a WHERE id = ANY(ARRAY(SELECT id FROM b))`

## pg-array-jsonb  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-03099: unexpected item [ in a column definition`
- src: `CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)`

## pg-ascii-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('NULL',),)`
- src: `SELECT ASCII('') AS r`

## pg-at-time-zone  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D`
- src: `SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r`

## pg-avg-int  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (VALUES (1),(2)) v(x)`

## pg-avg-null  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.33333',),) target=(('2',),)`
- src: `SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)`

## pg-bit-fns  (postgresql)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_ff6c8e4945b4.GETBIT does not exist')`
- src: `SELECT get_bit(B'1011', 0), set_bit(B'0000', 1, 1)`

## pg-bitnot  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('-1',),) target=(('18446744073709551616',),)`
- src: `SELECT ~0 AS r`

## pg-blob-length  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'DECODE' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT LENGTH(decode('SGVsbG8=', 'base64')) AS r`

## pg-bool-int-cast  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01722: unable to convert string value containing 't' to a number: `
- src: `SELECT 'true'::boolean::int AS r`

## pg-bool-text2  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('true',),) target=(('1',),)`
- src: `SELECT true::text AS r`

## pg-bulk-insert  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE`
- src: `CREATE TABLE t (a INT); INSERT INTO t SELECT generate_series(1, 1000)`

## pg-case-statement  (postgresql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS TEXT AS $$ BEGIN CASE n WHEN 1 THEN RETURN 'one'; ELSE RETURN 'other'; END CASE; END; $$ LANGUAGE`

## pg-cast-int  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT CAST(2.7 AS INT) AS r`

## pg-cast-interval  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-30089: missing or invalid <datetime field>`
- src: `SELECT '1 day'::interval AS r`

## pg-cast-point  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(243, b'Type POINT is not a defined system type.DB-Lib error message 20018, severity 16:\n`
- src: `SELECT '(1,2)'::point AS r`

## pg-cast-round-half  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('8',),) target=(('7',),)`
- src: `SELECT 7.5 :: int AS r`

## pg-cast-tstz  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity`
- src: `SELECT '2020-01-01'::timestamptz AS r`

## pg-check-notvalid  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) NOT VALID`

## pg-chr-ascii-unicode  (postgresql)
- targets: oracle(invalid)
- live error: `'utf-8' codec can't decode byte 0xe9 in position 0: unexpected end of data`
- src: `SELECT chr(233), ascii('é')`

## pg-chr-concat  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('AB',),) target=(('4142',),)`
- src: `SELECT chr(65) || chr(66)`

## pg-chr-unicode  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('μ',),) target=(('NULL',),)`
- src: `SELECT CHR(956) AS r`

## pg-computed-func  (postgresql)
- targets: tsql(invalid)
- live error: `(8116, b'Argument data type text is invalid for argument 1 of lower function.DB-Lib error `
- src: `CREATE TABLE t (a TEXT, b TEXT GENERATED ALWAYS AS (lower(a)) STORED)`

## pg-computed-jsonb  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type JSONB.DB-Lib error messa`
- src: `CREATE TABLE t (data JSONB, name TEXT GENERATED ALWAYS AS (data->>'name') STORED)`

## pg-convert-to  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co`
- src: `SELECT convert_to('abc', 'UTF8')`

## pg-date-bin  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DA`
- src: `SELECT date_bin('15 minutes', TIMESTAMP '2020-01-01 00:07', TIMESTAMP '2020-01-01')`

## pg-date-diff-days  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('60',),) target=(('200',),)`
- src: `SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r`

## pg-date-part  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00907: missing right parenthesis`
- src: `SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15')`

## pg-date-plus-int  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('2020-01-31',),) target=(('2020-01-31 00:00:00',),)`
- src: `SELECT DATE '2020-01-01' + 30 AS r`

## pg-date-trunc  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI`
- src: `SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d`

## pg-div-precision  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.333333',),) target=(('0.33333',),)`
- src: `SELECT 1.0 / 3 AS r`

## pg-double-cast  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT 123::text::int AS r`

## pg-drop-default  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'DEFAULT'.DB-Lib error message 20018, severity 1`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP DEFAULT`

## pg-drop-not-null  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP NOT NULL`

## pg-emoji-len  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT LENGTH('😀') AS r`

## pg-empty-is-null  (postgresql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT '' IS NULL AS r`

## pg-encode-base64  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT ENCODE('abc'::bytea, 'base64') AS r`

## pg-encode-decode  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'DECODE' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT ENCODE(DECODE('SGVsbG8=', 'base64'), 'hex')`

## pg-except-all  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `SELECT 1 EXCEPT ALL SELECT 2`

## pg-exception-handler  (postgresql)
- targets: tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql`

## pg-execute-using  (postgresql)
- targets: mysql(invalid)
- live error: `(1336, 'Dynamic SQL is not allowed in stored function or trigger')`
- src: `CREATE FUNCTION f() RETURNS VOID AS $$ BEGIN EXECUTE 'INSERT INTO t VALUES ($1)' USING 5; END; $$ LANGUAGE plpgsql`

## pg-expr-index  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-02327: cannot create index on expression with data type LOB`
- src: `CREATE TABLE t (a INT, b TEXT); CREATE INDEX ix ON t (lower(b))`

## pg-extract-dow  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(155, b"'DOW' is not a recognized datepart option.DB-Lib error message 20018, severity 15:`
- src: `SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d`

## pg-extract-epoch  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(155, b"'EPOCH' is not a recognized datepart option.DB-Lib error message 20018, severity 1`
- src: `SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01') AS r`

## pg-fetch-ties2  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t ORDER BY id FETCH FIRST 5 ROWS WITH TI`

## pg-filter-subquery  (postgresql)
- targets: tsql(invalid)
- live error: `(130, b'Cannot perform an aggregate function on an expression containing an aggregate or a`
- src: `CREATE TABLE t (id INT, n INT); CREATE TABLE u (id INT, v INT); SELECT id, COUNT(*) FILTER (WHERE n > (SELECT AVG(v) FROM u)) FROM`

## pg-for-update  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT); SELECT * FROM t FOR UPDATE`

## pg-format-func  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT format('%s=%s', 'a', 1) AS r`

## pg-fulltext  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT to_tsvector('a cat') @@ to_tsquery('cat') AS r`

## pg-fulltext2  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id FROM t WHERE to_tsvector('english', s) @@ plainto_tsquery('english', 'ter`

## pg-func-attrs  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'sql'.DB-Lib error message 20018, severity 15:\nGeneral SQL `
- src: `CREATE FUNCTION f() RETURNS INT AS $$ SELECT 1 $$ LANGUAGE sql SECURITY DEFINER STABLE PARALLEL SAFE`

## pg-generate-series  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE`
- src: `SELECT generate_series(1, 5) AS r`

## pg-greatest-null  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('NULL',),)`
- src: `SELECT GREATEST(1, NULL, 3) AS r`

## pg-greatest-string  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('a',),) target=(('B',),)`
- src: `SELECT GREATEST('a', 'B') AS r`

## pg-grouping-fn  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8161, b'Argument 1 of the GROUPING function does not match any of the expressions in the `
- src: `SELECT x, GROUPING(x) FROM (VALUES (1)) v(x) GROUP BY CUBE (x)`

## pg-grouping-sets  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())`

## pg-grouping-sets2  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, n, GROUPING(id), GROUPING(n) FROM t GROUP BY`

## pg-groups2  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, n, count(*) OVER (ORDER BY id GROUPS BETWEEN`

## pg-hex-literal  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00932: expression is of data type BINARY, which is incompatible with expected data typ`
- src: `SELECT x'FF'::int AS h, 1.5e3 AS s`

## pg-initcap  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT INITCAP('hello world') AS r`

## pg-insert-select-conflict  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(208, b"Invalid object name 'dbo.GENERATE_SERIES'.DB-Lib error message 20018, severity 16:`
- src: `CREATE TABLE t (id INT, n INT, s VARCHAR(50)); INSERT INTO t (id, n) SELECT g, g*2 FROM generate_series(1,5) g ON CONFLICT DO NOTH`

## pg-intdiv  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('2.5',),)`
- src: `SELECT 5 / 2 AS r`

## pg-intersect-all  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `SELECT 1 INTERSECT ALL SELECT 1`

## pg-interval-arith  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(207, b"Invalid column name 'INTERVAL'.DB-Lib error message 20018, severity 16:\nGeneral S`
- src: `SELECT NOW() - INTERVAL '1 day', DATE '2020-01-01' + 7`

## pg-json-aggs  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_`
- src: `SELECT json_agg(x), json_object_agg(x::text, x*2) FROM (VALUES (1),(2)) v(x)`

## pg-jsonb-agg  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSONB_AGG(x) FROM (VALUES (1),(2)) v(x)`

## pg-jsonb-build  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSONB_BUILD_OBJECT('a', 1, 'b', 2)`

## pg-jsonb-path-query  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js`
- src: `SELECT jsonb_path_query('{"a":[1,2]}', '$.a[*]') AS r`

## pg-jsonb-recordset  (postgresql)
- targets: tsql(invalid)
- live error: `(317, b"Table-valued function 'jsonb_to_recordset' cannot have a column alias.DB-Lib error`
- src: `SELECT * FROM jsonb_to_recordset('[{"a":1}]') AS x(a INT)`

## pg-justify  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '1 mon 40 days'.DB-Lib error message 20018, severity 15:\nGe`
- src: `SELECT JUSTIFY_INTERVAL(INTERVAL '1 mon 40 days') AS r`

## pg-left-neg  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('',),)`
- src: `SELECT LEFT('abc', -1) AS r`

## pg-left-round  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('hel',),) target=(('he',),)`
- src: `SELECT LEFT('hello', 2.9::int) AS r`

## pg-like-cs  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'ABC' LIKE 'abc' AS r`

## pg-like-escape  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'a_b' LIKE 'a\_b' AS r`

## pg-log-2arg  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('0.333333',),)`
- src: `SELECT LOG(2, 8) AS r`

## pg-log-base  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('4.60517',),)`
- src: `SELECT LOG(100) AS r`

## pg-lpad-shrink  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('hel',),) target=(('llo',),)`
- src: `SELECT LPAD('hello', 3) AS r`

## pg-ltrim-set  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('abc',),) target=(('',),)`
- src: `SELECT ltrim('xxabc', 'x') AS r`

## pg-make-date  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT MAKE_DATE(2020, 6, 15), MAKE_TIME(10, 30, 0)`

## pg-md5  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT MD5('abc') AS r`

## pg-mod-decimal  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT MOD(10, 3.5::numeric) AS r`

## pg-multi-out  (postgresql)
- targets: oracle(invalid)
- live error: `FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared`
- src: `CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql`

## pg-named-exception  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1/0; EXCEPTION WHEN division_by_zero THEN RETURN -1; WHEN OTHERS THEN RAISE; EN`

## pg-named-window2  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-30485: missing ORDER BY expression in the window specification`
- src: `CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id, LAG(n) OVER w, LEAD(n) OVER w FROM t WINDOW w AS (PARTITION BY s ORDER B`

## pg-nested-call  (postgresql)
- targets: oracle(invalid)
- live error: `PROCEDURE OUTER_P compiled INVALID (line 4): PLS-00201: identifier 'INNER_P' must be decla`
- src: `CREATE PROCEDURE outer_p() AS $$ BEGIN CALL inner_p(); END; $$ LANGUAGE plpgsql`

## pg-network-types  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag`
- src: `CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)`

## pg-not-null-is-null  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT (NOT NULL) IS NULL AS r`

## pg-num-nonnulls  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT NUM_NONNULLS(1, NULL, 2) AS r`

## pg-numfmt-lead  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.5',),) target=(('0',),)`
- src: `SELECT to_char(0.5, '0.00') AS r`

## pg-numfmt-thousands  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1,234,567.89',),) target=(('9999999123456900',),)`
- src: `SELECT to_char(1234567.891, '9,999,999.99') AS r`

## pg-order-nulls-default  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))`
- src: `SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x`

## pg-overlay  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV`
- src: `SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o`

## pg-position-case  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT POSITION('a' IN 'ABC') AS r`

## pg-position-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT POSITION('' IN 'abc') AS r`

## pg-quote  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU`
- src: `SELECT QUOTE_LITERAL('O''Brien'), QUOTE_IDENT('my col')`

## pg-range-types  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m`
- src: `CREATE TABLE t (rng INT4RANGE, tsr TSRANGE)`

## pg-realworld-transfer  (postgresql)
- targets: mysql(silent-rt), oracle(invalid), tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE TABLE accounts (id SERIAL PRIMARY KEY, balance NUMERIC(12,2) DEFAULT 0 CHECK (balance >= 0));
CREATE TABLE ledger (id SERIA`

## pg-recursive-func  (postgresql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS INT AS $$ BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END; $$ LANGUAGE plpgsql`

## pg-regexp-backref  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-01722: unable to convert string value containing 'g' to a number: `
- src: `SELECT regexp_replace('a1b2', '(\d)', '[\1]', 'g') AS r`

## pg-regexp-matches  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE`
- src: `SELECT REGEXP_MATCHES('a1b2', '[0-9]', 'g') AS r`

## pg-regexp-split-table  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(208, b"Invalid object name 'dbo.regexp_split_to_table'.DB-Lib error message 20018, severi`
- src: `SELECT * FROM regexp_split_to_table('a,b,c', ',')`

## pg-repeat-left-right  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00904: "RIGHT": invalid identifier`
- src: `SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)`

## pg-rollup  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)`

## pg-round-1005  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.01',),) target=(('1',),)`
- src: `SELECT ROUND(1.005::numeric, 2) AS r`

## pg-round-2675  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.68',),) target=(('3',),)`
- src: `SELECT ROUND(2.675::numeric, 2) AS r`

## pg-savepoint  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'AS'.DB-Lib error message 20018, severity 15:\nG`
- src: `BEGIN; SAVEPOINT sp; ROLLBACK TO SAVEPOINT sp; COMMIT`

## pg-scale  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.sc`
- src: `SELECT scale(1.230), trim_scale(1.230)`

## pg-sequence  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne`
- src: `CREATE SEQUENCE seq; SELECT nextval('seq'), currval('seq')`

## pg-serial-bit  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit`
- src: `CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))`

## pg-set-default  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5`

## pg-setweight  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.se`
- src: `SELECT setweight(to_tsvector('cat'), 'A') AS r`

## pg-size-funcs  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.pg`
- src: `SELECT pg_size_pretty(1024::bigint), pg_relation_size('pg_class')`

## pg-split-part  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT SPLIT_PART('a,b,c', ',', 2) AS r`

## pg-str-lt  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'apple' < 'Banana' AS r`

## pg-string-agg-order  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-string-split-fns  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.st`
- src: `SELECT string_to_table('a,b,c', ','), regexp_split_to_array('a1b2', '\d')`

## pg-string-to-array  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message `
- src: `SELECT string_to_array('a,b,c', ',')`

## pg-strpos-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT STRPOS('', '') AS r`

## pg-substr-zero  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('abc',),)`
- src: `SELECT SUBSTRING('abcdef', 0, 3) AS r`

## pg-substring-regex  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib`
- src: `SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r`

## pg-synonym-as-view  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00955: name is already used by an existing object`
- src: `CREATE TABLE t (a INT); CREATE VIEW syn AS SELECT * FROM t`

## pg-tablesample  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT); SELECT * FROM t TABLESAMPLE BERNOULLI(50)`

## pg-tochar-iso  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type timestamp is invalid for argument 1 of format function.DB-Lib `
- src: `SELECT to_char(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r`

## pg-tochar-neg  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('-1234.5',),) target=(('-9999123599',),)`
- src: `SELECT to_char(-1234.5, '9999.99') AS r`

## pg-tohex2  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE`
- src: `SELECT to_hex(255), to_char(255, 'XX')`

## pg-totimestamp-long  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT to_timestamp('June 15 2020', 'Month DD YYYY') AS r`

## pg-trailing-eq  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'a ' = 'a' AS r`

## pg-translate  (postgresql)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_5e892bc4b99a.TRANSLATE does not exist')`
- src: `SELECT TRANSLATE('abc', 'ab', 'xy') AS r`

## pg-trim-both-chars  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-30001: trim set should have only one character`
- src: `SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS t`

## pg-trim-len  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2', '0'),) target=(('0', '0'),)`
- src: `SELECT CHAR_LENGTH('  '), LENGTH(TRIM('  '))`

## pg-truncate-restart  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'RESTART'.DB-Lib error message 20018, severity 15:\nGeneral `
- src: `CREATE TABLE t (id INT); TRUNCATE TABLE t RESTART IDENTITY CASCADE`

## pg-ts-headline  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ts`
- src: `SELECT ts_headline('the quick fox', to_tsquery('fox')) AS r`

## pg-ts-rank  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ts`
- src: `SELECT ts_rank(to_tsvector('the cat'), to_tsquery('cat')) AS r`

## pg-tstzrange  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '1 DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ`
- src: `SELECT tstzrange(now(), now() + INTERVAL '1 day') AS r`

## pg-tz-interval  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-30089: missing or invalid <datetime field>`
- src: `CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)`

## pg-unicode-escape  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(207, b"Invalid column name 'U'.DB-Lib error message 20018, severity 16:\nGeneral SQL Serv`
- src: `SELECT U&'\0041' AS r`

## pg-week  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT EXTRACT(WEEK FROM DATE '2020-01-05') AS r`

## pg-week-2016  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('53',),) target=(('1',),)`
- src: `SELECT EXTRACT(WEEK FROM DATE '2016-01-01') AS r`

## pg-week-jan1  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT EXTRACT(WEEK FROM DATE '2020-01-01') AS r`

## pg-width-bucket  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI`
- src: `SELECT width_bucket(5, 0, 10, 5) AS r`

## pg-xmlelement  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT XMLELEMENT(NAME foo, 'bar') AS r`

## pg-xmlelement2  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT xmlelement(name foo, 'bar')`

## pg-xpath  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.xp`
- src: `SELECT xpath('/a/text()', '<a>1</a>'::xml)`

## pg15-merge  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPD`

## po-distinct-case  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('A',), ('B',), ('a',)) target=(('A',), ('B',))`
- src: `SELECT DISTINCT x FROM (VALUES ('a'),('A'),('a'),('B')) v(x) ORDER BY x`

## po-distinct-null  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',), ('2',), ('NULL',)) target=(('NULL',), ('1',), ('2',))`
- src: `SELECT DISTINCT x FROM (VALUES (1),(NULL),(1),(NULL),(2)) v(x) ORDER BY x`

## po-group-case  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('A', '1'), ('a', '1'), ('b', '1')) target=(('A', '2'), ('b', '1'))`
- src: `SELECT x, COUNT(*) FROM (VALUES ('a'),('A'),('b')) v(x) GROUP BY x ORDER BY x`

## po-group-null  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1', '2'), ('NULL', '2')) target=(('NULL', '2'), ('1', '2'))`
- src: `SELECT x, COUNT(*) FROM (VALUES (1),(NULL),(1),(NULL)) v(x) GROUP BY x ORDER BY x`

## po-order-strings  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), `
- src: `SELECT x FROM (VALUES ('banana'),('Apple'),('cherry'),('Banana')) v(x) ORDER BY x`

## postgresql-drop-CHECK  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)`
- src: `CREATE TABLE t (age INT CHECK (age >= 0))`

## postgresql-drop-DEFERRABLE  (postgresql)
- targets: oracle(silent-drop)
- live error: `SILENT CLAUSE DROP: 'DEFERRABLE' absent from valid oracle output, no warning (target suppo`
- src: `CREATE TABLE t (id INT PRIMARY KEY DEFERRABLE INITIALLY DEFERRED)`

## postgresql-drop-ON\s+DELETE\s+  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ON\s+DELETE\s+CASCADE' absent from valid tsql output, no warning (tar`
- src: `CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE CASCADE)`

## postgresql-drop-ON\s+UPDATE\s+  (postgresql)
- targets: mysql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ON\s+UPDATE\s+CASCADE' absent from valid mysql output, no warning (ta`
- src: `CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON UPDATE CASCADE)`

## postgresql-drop2-100|START  (postgresql)
- targets: oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (id INT GENERATED BY DEFAULT AS IDENTITY (START WITH 100 INCREMENT BY 5))`

## postgresql-drop2-CONCURRENTLY  (postgresql)
- targets: mysql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'CONCURRENTLY' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT); CREATE INDEX CONCURRENTLY ix ON t (a)`

## postgresql-drop2-EXCLUDE  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'EXCLUDE' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT, EXCLUDE USING btree (a WITH =))`

## postgresql-drop2-NULLS\s+FIRS  (postgresql)
- targets: oracle(silent-drop)
- live error: `SILENT CLAUSE DROP: 'NULLS\s+FIRST' absent from valid oracle output, no warning`
- src: `CREATE TABLE t (a INT); CREATE INDEX ix ON t (a NULLS FIRST)`

## postgresql-drop4-BY\s+DEFAULT  (postgresql)
- targets: tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'BY\s+DEFAULT|GENERATED' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT GENERATED BY DEFAULT AS IDENTITY)`

## postgresql-drop4-COLLATE  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a TEXT COLLATE "en_US")`

## postgresql-drop4-MATCH\s+FULL  (postgresql)
- targets: oracle(silent-drop)
- live error: `SILENT CLAUSE DROP: 'MATCH\s+FULL' absent from valid oracle output, no warning`
- src: `CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) MATCH FULL)`

## postgresql-drop5-CHECK|IN\s*\  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'CHECK|IN\s*\(' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT CHECK (a IN (1,2,3)))`

## postgresql-drop5-REFERENCES  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'REFERENCES' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT PRIMARY KEY, b INT REFERENCES t(a))`

## postgresql-qdrop-FOR\s+UPDATE  (postgresql)
- targets: tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'FOR\s+UPDATE' absent from valid tsql output, no warning`
- src: `SELECT x FROM (VALUES (1),(2)) v(x) FOR UPDATE`

## postgresql-qdrop-ROWS\s+BETWE  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ROWS\s+BETWEEN' absent from valid tsql output, no warning`
- src: `SELECT x, SUM(x) OVER (ORDER BY x ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM (VALUES (1),(2)) v(x)`

## ts-after-delete-count  (tsql)
- targets: oracle(invalid)
- live error: `TRIGGER TRG compiled INVALID (line 4): PL/SQL: ORA-00942: table or view does not exist`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t AFTER DELETE AS BEGIN DECLARE @c INT = (SELECT COUNT(*) FRO`

## ts-alter-add  (tsql)
- targets: oracle(invalid)
- live error: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD b NVARCHAR(10) NOT NULL DEFAULT 'x'`

## ts-ascii-char  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NCHAR": invalid identifier`
- src: `SELECT ASCII('A'), CHAR(65), NCHAR(65)`

## ts-at-time-zone  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST('2020-01-01 10:00' AS DATETIME2) AT TIME ZONE 'UTC' AS r`

## ts-binary-length  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT DATALENGTH(CAST('hello' AS VARBINARY(MAX))) AS r`

## ts-bit-fns  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SET_BIT": invalid identifier`
- src: `SELECT GET_BIT(0x0A, 1), SET_BIT(0x0A, 0, 1)`

## ts-cast-bit  (tsql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT CAST(2 AS BIT) AS r`

## ts-cast-date-int  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00932: expression is of data type DATE, which is incompatible with expected data type `
- src: `SELECT CAST(GETDATE() AS INT) AS r`

## ts-cast-int-datetime  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00932: expression is of data type NUMBER, which is incompatible with expected data typ`
- src: `SELECT CAST(1 AS DATETIME) AS r`

## ts-cast-trycast  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01722: unable to convert string value containing 'x' to a number: `
- src: `SELECT CAST(123 AS VARCHAR(10)), TRY_CAST('x' AS INT), CONVERT(DATE, GETDATE())`

## ts-checksum-agg  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "CHECKSUM_AGG": invalid identifier`
- src: `SELECT CHECKSUM_AGG(x) FROM (VALUES (1),(2)) v(x)`

## ts-choose  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "CHOOSE": invalid identifier`
- src: `SELECT CHOOSE(2, 'a', 'b', 'c') AS r`

## ts-compress  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT COMPRESS('data') AS r`

## ts-concat-null  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('NULL',),)`
- src: `SELECT CONCAT('a', NULL, 'b') AS r`

## ts-concat-ws  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00904: "CONCAT_WS": invalid identifier`
- src: `SELECT CONCAT_WS('-', 'a', 'b', 'c') AS r`

## ts-concatws2  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00904: "CONCAT_WS": invalid identifier`
- src: `SELECT CONCAT_WS(',', 'a', NULL, 'b') AS r`

## ts-conditional  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "CHOOSE": invalid identifier`
- src: `SELECT IIF(1>0,'y','n'), CHOOSE(2,'a','b','c'), ISNULL(NULL,'x'), NULLIF(1,1)`

## ts-cursor  (tsql)
- targets: mysql(invalid)
- live error: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT x FROM (VALUES (1),(2)) v(x); DECLARE @x INT; OPEN c; FETCH NEXT FROM c IN`

## ts-date-bucket2  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT DATE_BUCKET(MINUTE, 15, CAST('2020-01-01 00:07' AS DATETIME2))`

## ts-dateadd  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-30081: invalid data type for datetime/interval arithmetic`
- src: `SELECT DATEADD(DAY, 7, '2020-01-01') AS r`

## ts-datediff  (tsql)
- targets: oracle(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT DATEDIFF(DAY, '2020-01-01', '2020-01-10') AS r`

## ts-datediff-big  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT DATEDIFF_BIG(SECOND, '2020-01-01', '2020-01-02') AS r`

## ts-datetimefromparts  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "TIMESTAMP_FROM_PARTS": invalid identifier`
- src: `SELECT DATETIMEFROMPARTS(2020, 6, 15, 10, 30, 0, 0) AS r`

## ts-datetimeoffset  (tsql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-03060: Data type TIME is invalid.`
- src: `CREATE TABLE t (a DATETIMEOFFSET, b DATETIME2(7), c TIME(3))`

## ts-default-nextval  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-04044: procedure, function, package, or type is not allowed here`
- src: `CREATE SEQUENCE s AS INT START WITH 1;
GO
CREATE TABLE t (id INT DEFAULT (NEXT VALUE FOR s), a INT)`

## ts-emoji-len  (tsql)
- targets: mysql(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('1',),)`
- src: `SELECT LEN(N'😀') AS r`

## ts-eomonth  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT EOMONTH('2020-02-15') AS r`

## ts-eomonth-nested  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT DATEADD(MONTH, -1, EOMONTH('2020-03-01')) AS r`

## ts-error-functions  (tsql)
- targets: oracle(invalid)
- live error: `PROCEDURE P compiled INVALID (line 12): PL/SQL: ORA-00904: "ERROR_LINE": invalid identifie`
- src: `CREATE PROCEDURE p AS BEGIN BEGIN TRY SELECT 1/0; END TRY BEGIN CATCH SELECT ERROR_MESSAGE(), ERROR_NUMBER(), ERROR_LINE(); END CA`

## ts-format-iso  (tsql)
- targets: mysql(silent), oracle(invalid), postgresql(silent)
- live error: `ORA-01821: date format not recognized`
- src: `SELECT FORMAT(CAST('2020-06-15 14:30:45' AS DATETIME2), 'yyyy-MM-ddTHH:mm:ss') AS r`

## ts-format-number  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NUMBER_TO_STR": invalid identifier`
- src: `SELECT FORMAT(1234.5, 'N2') AS r`

## ts-formatmessage  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "FORMATMESSAGE": invalid identifier`
- src: `SELECT FORMATMESSAGE('hi %s', 'x') AS r`

## ts-geography  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "GEOGRAPHY"."TOSTRING": invalid identifier`
- src: `SELECT GEOGRAPHY::Point(47.6, -122.3, 4326).ToString() AS r`

## ts-host-db  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "DB_NAME": invalid identifier`
- src: `SELECT HOST_NAME(), DB_NAME(), SUSER_SNAME()`

## ts-identity-funcs  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT SCOPE_IDENTITY(), @@IDENTITY, IDENT_CURRENT('t')`

## ts-inline-index2  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (id INT, name VARCHAR(50), INDEX ix_name NONCLUSTERED (name))`

## ts-insert-output  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00925: missing INTO keyword`
- src: `CREATE TABLE t (id INT, n INT);
GO
INSERT INTO t (id, n) OUTPUT INSERTED.id VALUES (1, 5)`

## ts-instead-of-insert  (tsql)
- targets: postgresql(invalid)
- live error: `"t" is a table`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id,`

## ts-len-trailing  (tsql)
- targets: mysql(func), oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('6',),)`
- src: `SELECT LEN('abc   ') AS r`

## ts-merge-full  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-02000: missing THEN keyword`
- src: `CREATE TABLE tgt (id INT PRIMARY KEY, n INT); CREATE TABLE src (id INT, n INT);
GO
MERGE tgt USING src ON tgt.id = src.id WHEN MAT`

## ts-metadata-funcs  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "OBJECT_ID": invalid identifier`
- src: `SELECT COL_LENGTH('t', 'c'), OBJECT_ID('t')`

## ts-money  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (price MONEY, small SMALLMONEY)`

## ts-money-arith  (tsql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('12.8',),) target=(('$12.80',),)`
- src: `SELECT CAST(10.5 AS MONEY) + CAST(2.3 AS MONEY) AS r`

## ts-month-overflow  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2020-02-29 00:00:00',),) target=(('2020-02-29',),)`
- src: `SELECT DATEADD(MONTH, 1, '2020-01-31') AS r`

## ts-nchar-hex  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NCHAR": invalid identifier`
- src: `SELECT NCHAR(0x1F600) AS r`

## ts-nolock-hint  (tsql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT);
GO
SELECT * FROM t WITH (NOLOCK)`

## ts-openjson  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "OPEN_J_S_O_N": invalid identifier`
- src: `SELECT * FROM OPENJSON('[1,2,3]')`

## ts-order-strings  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), `
- src: `SELECT x FROM (VALUES ('banana'),('Apple'),('cherry'),('Banana')) v(x) ORDER BY x`

## ts-patindex  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "PATINDEX": invalid identifier`
- src: `SELECT PATINDEX('%[0-9]%', 'abc123') AS r`

## ts-quotename  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SPLIT_PART": invalid identifier`
- src: `SELECT QUOTENAME('my table'), PARSENAME('a.b.c', 2)`

## ts-realworld-audit  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE LOG_IT compiled INVALID (line 11): PLS-00103: Encountered the symbol ")" when ex`
- src: `CREATE TABLE dbo.audit (id INT IDENTITY, msg NVARCHAR(MAX), ts DATETIME2);
GO
CREATE PROCEDURE dbo.log_it @msg NVARCHAR(MAX) AS BE`

## ts-recursive-cte  (tsql)
- targets: mysql(invalid), postgresql(invalid)
- live error: `relation "r" does not exist`
- src: `WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r`

## ts-replicate-space  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SPACE": invalid identifier`
- src: `SELECT REPLICATE('ab', 3), SPACE(5), REVERSE('abc')`

## ts-rowversion  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (row_ver ROWVERSION, flags BINARY(8))`

## ts-scroll-cursor  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 9): PLS-00103: Encountered the symbol ";" when expectin`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR LOCAL SCROLL FOR SELECT 1; OPEN c; FETCH LAST FROM c; CLOSE c; DEALLOCATE c; END`

## ts-select-into  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00905: missing keyword`
- src: `CREATE TABLE src (id INT);
GO
SELECT id INTO dst FROM src`

## ts-sequence-next  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NEXT_VALUE_FOR": invalid identifier`
- src: `CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1;
GO
SELECT NEXT VALUE FOR seq`

## ts-soundex-diff  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "DIFFERENCE": invalid identifier`
- src: `SELECT SOUNDEX('Smith'), DIFFERENCE('Smith', 'Smyth')`

## ts-spid-version  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT @@SPID, @@VERSION`

## ts-st-distance  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `DPY-4010: a bind variable replacement value for placeholder ":POINT" was not provided`
- src: `SELECT geometry::Point(0,0,0).STDistance(geometry::Point(3,4,0)) AS r`

## ts-str-func  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "STR": invalid identifier`
- src: `SELECT STR(3.14, 6, 2) AS r`

## ts-str-plus-num  (tsql)
- targets: mysql(func), oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('15',),) target=(('105',),)`
- src: `SELECT '10' + 5 AS r`

## ts-stragg-within2  (tsql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-00906: missing left parenthesis`
- src: `CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); CREATE TABLE data (data NVARCHAR(MAX));
GO
SELECT STRING_AGG(CAST(`

## ts-string-agg-within  (tsql)
- targets: postgresql(invalid)
- live error: `function string_agg(integer, unknown) does not exist`
- src: `SELECT STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## ts-string-split2  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "STRING_SPLIT": invalid identifier`
- src: `SELECT * FROM STRING_SPLIT('a,b,c', ',') WHERE value <> 'b'`

## ts-stuff  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "STUFF": invalid identifier`
- src: `SELECT STUFF('abcdef', 2, 3, 'XY') AS r`

## ts-sysdatetime  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "GETUTCDATE": invalid identifier`
- src: `SELECT SYSDATETIME(), SYSUTCDATETIME(), GETUTCDATE()`

## ts-tablesample  (tsql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT);
GO
SELECT * FROM t TABLESAMPLE (10 PERCENT)`

## ts-top-with-ties  (tsql)
- targets: postgresql(semantic)
- live error: `SILENT LOSS: TOP n WITH TIES -> plain LIMIT n on PG/MySQL (ties dropped); on Oracle the ro`
- src: `SELECT TOP 1 WITH TIES x FROM (VALUES (1),(1),(2)) v(x) ORDER BY x`

## ts-trailing-eq  (tsql)
- targets: mysql(func), oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT IIF('a ' = 'a', 1, 0) AS r`

## ts-translate  (tsql)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_d6bc06ffba67.TRANSLATE does not exist')`
- src: `SELECT TRANSLATE('abc', 'ab', 'xy') AS r`

## ts-trigger-on-view  (tsql)
- targets: postgresql(invalid)
- live error: `INSTEAD OF triggers must be FOR EACH ROW`
- src: `CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t;
GO
CREATE TRIGGER trg ON v INSTEAD OF INSERT AS BEGIN INSERT INTO t`

## ts-trim-chars  (tsql)
- targets: oracle(invalid)
- live error: `ORA-30001: trim set should have only one character`
- src: `SELECT TRIM('x' FROM 'xxabcxx') AS r`

## ts-try-convert  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01722: unable to convert string value containing 'a' to a number: `
- src: `SELECT TRY_CONVERT(INT, 'abc') AS r`

## ts-try-parse  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00907: missing right parenthesis`
- src: `SELECT TRY_PARSE('2020-01-01' AS DATE) AS r`

## ts-tzoffset  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "CURRENT_TIMESTAMP_L_T_Z": invalid identifier`
- src: `SELECT DATENAME(TZOFFSET, SYSDATETIMEOFFSET()) AS r`

## ts-while-break-continue  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 11): PLS-00201: identifier 'BREAK' must be declared`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE @i INT = 0; WHILE @i < 5 BEGIN SET @i = @i + 1; IF @i = 3 CONTINUE; IF @i = 5 BREAK; END; END`

## ts-while-loop  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 15): PLS-00103: Encountered the symbol "=" when expecti`
- src: `CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN SET @n -=`

## tsql-drop2-100|START|ID  (tsql)
- targets: postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: '100|START|IDENTITY' absent from valid postgresql output, no warning`
- src: `CREATE TABLE t (id INT IDENTITY(100, 5))`

## tsql-drop5-MEMORY_OPTIM  (tsql)
- targets: mysql(silent-drop), oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'MEMORY_OPTIMIZED' absent from valid postgresql output, no warning`
- src: `CREATE TABLE t (a INT) WITH (MEMORY_OPTIMIZED = ON)`
---

Totals: 516 distinct constructs; defect rows by kind: func 271, invalid 717, semantic 2, silent-drop 75.
