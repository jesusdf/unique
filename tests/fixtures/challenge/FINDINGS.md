# Challenge findings ledger (RED)

Source constructs that transpile wrong on >=1 target, each **validated on a
live engine** (original accepted by its own engine; output rejected by the
target engine, or degraded to an unrecognized carrier). Tagged `[open]` in
the `challenge_<engine>.sql` scripts; BLUE fixes and flips to `[fixed]`.

Kinds: **invalid** = live target rejected the output; **carrier** = degraded
to an `Unhandled`/unrecognized carrier (may be an acceptable degrade — BLUE
triages); **silent/-rt** = valid output but a source literal vanished (verify manually — the literal detector is noisy).


## my-aes  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE`
- src: `SELECT HEX(AES_ENCRYPT('data', 'key')) AS r`

## my-alter-modify  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT`

## my-avg-int  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t`

## my-base64  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO`
- src: `SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')`

## my-benchmark  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BE`
- src: `SELECT BENCHMARK(1, 1+1) AS r`

## my-bit-agg  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI`
- src: `SELECT BIT_XOR(x), BIT_OR(x) FROM (SELECT 1 x UNION SELECT 2) t`

## my-bit-count  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI`
- src: `SELECT BIT_COUNT(255) AS r`

## my-cast-convert  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:`
- src: `SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)`

## my-cast-int  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT CAST(2.7 AS SIGNED) AS r`

## my-change-column  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'CHANGE'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t CHANGE a x INT`

## my-coalesce-empty  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('NULL',),)`
- src: `SELECT COALESCE(NULL, 0) = '' AS r`

## my-concat-null  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('ab',),)`
- src: `SELECT CONCAT('a', NULL, 'b') AS r`

## my-concat-ws  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00904: "CONCAT_WS": invalid identifier`
- src: `SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r`

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

## my-date-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r`

## my-datetime-precision  (mysql)
- targets: tsql(invalid)
- live error: `(2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat`
- src: `CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)`

## my-div  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.5',),) target=(('2',),)`
- src: `SELECT 5 / 2 AS r`

## my-elt  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EL`
- src: `SELECT ELT(2, 'a', 'b', 'c') AS r`

## my-empty-eq-zero  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('NULL',),)`
- src: `SELECT '' = 0 AS r`

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

## my-greatest-null  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('3',),)`
- src: `SELECT GREATEST(1, NULL, 3) AS r`

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

## my-index-using  (mysql)
- targets: oracle(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a INT, b INT); CREATE INDEX ix ON t (a) USING BTREE`

## my-inet  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN`
- src: `SELECT INET_ATON('127.0.0.1'), INET_NTOA(2130706433)`

## my-json-arrayagg  (mysql)
- targets: tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION SELECT 2) t`

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

## my-left-neg  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('',),) target=(('ab',),)`
- src: `SELECT LEFT('abc', -1) AS r`

## my-length-bytes  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('5',),) target=(('4',),)`
- src: `SELECT LENGTH('café') AS r`

## my-like-ci  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'ABC' LIKE 'abc' AS r`

## my-lock-tables  (mysql)
- targets: oracle(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT); LOCK TABLES t WRITE`

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

## my-numeric  (mysql)
- targets: tsql(invalid)
- live error: `(2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)`

## my-partition-hash  (mysql)
- targets: oracle(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT, dt DATE) PARTITION BY HASH(id) PARTITIONS 4`

## my-period-diff  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE`
- src: `SELECT PERIOD_DIFF(202006, 202001) AS r`

## my-recursive-func  (mysql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS INT DETERMINISTIC BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END`

## my-soundex-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)`

## my-status-funcs  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RO`
- src: `SELECT LAST_INSERT_ID(), ROW_COUNT(), FOUND_ROWS()`

## my-substr-neg  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('def',),) target=(('ab',),)`
- src: `SELECT SUBSTRING('abcdef', -3) AS r`

## my-substring-index  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU`
- src: `SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r`

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

## my-trailing-eq  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'a ' = 'a' AS r`

## my-trim-both  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('abc',),) target=(('',),)`
- src: `SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS r`

## my-unix-timestamp  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2`
- src: `SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)`

## my-update-join  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n`

## my-uuid-funcs  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU`
- src: `SELECT UUID(), UUID_SHORT()`

## my-view-cascade-check  (mysql)
- targets: oracle(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a INT, b INT); CREATE VIEW v AS SELECT a FROM t WHERE a > 0 WITH CASCADED CHECK OPTION`

## my-week-quarter  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE`
- src: `SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')`

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

## ora-add-months  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL`

## ora-alter-session  (oracle)
- targets: mysql(invalid), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD'`

## ora-bitand  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT BITAND(5, 3) AS r FROM DUAL`

## ora-bulk-collect  (oracle)
- targets: mysql(invalid), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['could not translate']`
- src: `CREATE PROCEDURE p AS TYPE t_tab IS TABLE OF NUMBER; v t_tab; BEGIN SELECT 1 BULK COLLECT INTO v FROM DUAL; END;
/`

## ora-case-statement  (oracle)
- targets: tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'ELSE'.DB-Lib error message 20018, severity 15:\`
- src: `CREATE PROCEDURE p (n IN NUMBER) AS BEGIN CASE n WHEN 1 THEN NULL; ELSE NULL; END CASE; END;
/`

## ora-cast-expr  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL`

## ora-comment-col  (oracle)
- targets: mysql(invalid), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id NUMBER); COMMENT ON COLUMN t.id IS 'the id'`

## ora-concat-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('NULL',),)`
- src: `SELECT 'a' || NULL || 'b' AS r FROM DUAL`

## ora-concat-num  (oracle)
- targets: tsql(invalid)
- live error: `(245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er`
- src: `SELECT 'a' || 5 AS r FROM DUAL`

## ora-connect-by  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT LEVEL, 1 AS n FROM DUAL CONNECT BY LEVEL <= 5`

## ora-connect-by-root  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CONNECT_BY_ROOT id AS root FROM (SELECT 1 id, NULL par FROM DUAL) CONNECT BY PRIOR id = par`

## ora-connect-by2  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT id FROM (SELECT 1 id, NULL par FROM DUAL) START WITH par IS NULL CONNECT BY PRIOR id = par`

## ora-cursor  (oracle)
- targets: mysql(invalid)
- live error: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;`

## ora-cursor-for-loop  (oracle)
- targets: tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/`

## ora-date-plus-int  (oracle)
- targets: mysql(semantic), postgresql(invalid)
- live error: `SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith`
- src: `SELECT SYSDATE + 1 AS r FROM DUAL`

## ora-day-of-week  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('24',),)`
- src: `SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL`

## ora-div  (oracle)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.5',),) target=(('2',),)`
- src: `SELECT 5 / 2 AS r FROM DUAL`

## ora-dump  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU`
- src: `SELECT DUMP('abc') AS r FROM DUAL`

## ora-dump2  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU`
- src: `SELECT DUMP('A', 1016) AS r FROM DUAL`

## ora-empty-is-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT CASE WHEN '' IS NULL THEN 1 ELSE 0 END AS r FROM DUAL`

## ora-empty-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('x',),) target=(('',),)`
- src: `SELECT NVL('', 'x') AS r FROM DUAL`

## ora-exception-init  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type EXCEPTION.DB-Lib error m`
- src: `CREATE PROCEDURE p AS e EXCEPTION; PRAGMA EXCEPTION_INIT(e, -20001); BEGIN RAISE e; END;
/`

## ora-extractvalue  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX`
- src: `SELECT EXTRACTVALUE(XMLTYPE('<a>1</a>'), '/a') AS r FROM DUAL`

## ora-fk-novalidate  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE p (id NUMBER PRIMARY KEY); CREATE TABLE c (pid NUMBER, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES p(id) ON DELETE CAS`

## ora-for-update-nowait  (oracle)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT`

## ora-from-tz  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR`
- src: `SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL`

## ora-grant  (oracle)
- targets: mysql(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id NUMBER); GRANT SELECT ON t TO PUBLIC`

## ora-initcap  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT INITCAP('hello world') AS r FROM DUAL`

## ora-insert-all  (oracle)
- targets: mysql(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE a (id NUMBER); CREATE TABLE b (id NUMBER);
INSERT ALL INTO a (id) VALUES (x) INTO b (id) VALUES (x) SELECT 1 x FROM D`

## ora-json-object  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT JSON_OBJECT('a' VALUE 1) AS r FROM DUAL`

## ora-json-table  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT * FROM JSON_TABLE('[1,2]', '$[*]' COLUMNS (v NUMBER PATH '$'))`

## ora-json-value  (oracle)
- targets: postgresql(invalid), tsql(silent-rt)
- live error: `SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'"] lost after oracle->tsql->oracle`
- src: `SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL`

## ora-last-day  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT LAST_DAY(SYSDATE) AS r FROM DUAL`

## ora-last-value-ignore  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT LAST_VALUE(x IGNORE NULLS) OVER (ORDER BY x) FROM (SELECT 1 x FROM DUAL)`

## ora-length-trailing  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('6',),) target=(('3',),)`
- src: `SELECT LENGTH('abc   ') AS r FROM DUAL`

## ora-level2  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT LEVEL FROM DUAL CONNECT BY LEVEL <= 3`

## ora-listagg  (oracle)
- targets: postgresql(invalid)
- live error: `function string_agg(integer, unknown) does not exist`
- src: `SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)`

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

## ora-numtodsinterval  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL`

## ora-ora-hash  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'ORA_HASH' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT ORA_HASH('abc') AS r FROM DUAL`

## ora-package-spec  (oracle)
- targets: mysql(invalid), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['could not translate']`
- src: `CREATE PACKAGE pkg AS PROCEDURE p; FUNCTION f RETURN NUMBER; END pkg;
/`

## ora-pk-using-index  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(1018, b"Incorrect syntax near 'INDEX'. If this is intended as a part of a table hint, A W`
- src: `CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)`

## ora-ratio-to-report  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA`
- src: `SELECT RATIO_TO_REPORT(x) OVER () FROM (SELECT 1 x FROM DUAL)`

## ora-ratio2  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA`
- src: `SELECT RATIO_TO_REPORT(1) OVER () FROM DUAL`

## ora-recursive-func  (oracle)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/`

## ora-regexp-count  (oracle)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')`
- src: `SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL`

## ora-reverse-index  (oracle)
- targets: mysql(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a NUMBER, b NUMBER);
CREATE INDEX ix ON t (a) REVERSE`

## ora-rtrim-chars  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('a',),) target=(('',),)`
- src: `SELECT RTRIM('axxx', 'x') AS r FROM DUAL`

## ora-sequence  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE SEQUENCE seq START WITH 1;
SELECT seq.NEXTVAL FROM DUAL`

## ora-sequence-options  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
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

## ora-sys-connect-path  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT SYS_CONNECT_BY_PATH(id, '/') AS p FROM (SELECT 1 id, NULL par FROM DUAL) START WITH par IS NULL CONNECT BY PRIOR id = par`

## ora-tablespace  (oracle)
- targets: mysql(carrier), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a NUMBER) TABLESPACE users`

## ora-to-char-day  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('SUNDAY',),) target=(('Sunday',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-14', 'DAY') AS r FROM DUAL`

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
- targets: mysql(invalid), tsql(invalid)
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

## pg-age  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a`

## pg-alter-add  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'`

## pg-alter-type  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01735: invalid ALTER TABLE option`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a TYPE BIGINT`

## pg-any-array-subquery  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'ARRAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ`
- src: `CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a WHERE id = ANY(ARRAY(SELECT id FROM b))`

## pg-array-agg  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT ARRAY_AGG(x ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-array-any  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 3 = ANY(ARRAY[1,2,3]) AS r`

## pg-array-concat  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT ARRAY[1,2,3] || ARRAY[4,5] AS r`

## pg-array-jsonb  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-03099: unexpected item [ in a column definition`
- src: `CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)`

## pg-array-to-string  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT array_to_string(ARRAY[1,2,3], ',')`

## pg-at-time-zone  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D`
- src: `SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r`

## pg-avg-int  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (VALUES (1),(2)) v(x)`

## pg-before-update-trg  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT, updated TIMESTAMP);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN NEW.updated :=`

## pg-caret-power  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('8',),) target=()`
- src: `SELECT 2 ^ 3 AS r`

## pg-case-statement  (postgresql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS TEXT AS $$ BEGIN CASE n WHEN 1 THEN RETURN 'one'; ELSE RETURN 'other'; END CASE; END; $$ LANGUAGE`

## pg-cast-int  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT CAST(2.7 AS INT) AS r`

## pg-collate  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 'a' < 'B' COLLATE "C" AS r`

## pg-collate2  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 'abc' COLLATE "C" AS r`

## pg-comment-on  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a INT); COMMENT ON COLUMN t.a IS 'the a column'`

## pg-comment-table  (postgresql)
- targets: mysql(invalid), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT); COMMENT ON TABLE t IS 'my table'`

## pg-composite-type  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TYPE addr AS (street TEXT, city TEXT)`

## pg-convert-to  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co`
- src: `SELECT convert_to('abc', 'UTF8')`

## pg-cte-cycle  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n<3) CYCLE n SET is_cycle USING path SELECT * FROM r`

## pg-cte-search  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n<3) SEARCH DEPTH FIRST BY n SET ord SELECT * FROM r`

## pg-date-part  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00907: missing right parenthesis`
- src: `SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15')`

## pg-date-trunc  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI`
- src: `SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d`

## pg-div-func  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=()`
- src: `SELECT DIV(7, 2) AS r`

## pg-div-mod-int  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('3', '2'),) target=()`
- src: `SELECT DIV(17, 5), 17 % 5`

## pg-domain  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE DOMAIN posint AS INT CHECK (VALUE > 0)`

## pg-drop-not-null  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP NOT NULL`

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

## pg-estring  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT E'line1\nline2' AS r`

## pg-except-all  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `SELECT 1 EXCEPT ALL SELECT 2`

## pg-exception-handler  (postgresql)
- targets: tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql`

## pg-explain  (postgresql)
- targets: mysql(invalid), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `EXPLAIN SELECT 1`

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

## pg-for-record-loop  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ DECLARE r RECORD; t INT := 0; BEGIN FOR r IN SELECT generate_series(1,3) AS n LOOP t := t +`

## pg-for-update  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT); SELECT * FROM t FOR UPDATE`

## pg-format-func  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT format('%s=%s', 'a', 1) AS r`

## pg-full-outer-join  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a FULL OUTER JOIN b ON a.id = b.id`

## pg-fulltext  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT to_tsvector('a cat') @@ to_tsquery('cat') AS r`

## pg-generate-series  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE`
- src: `SELECT generate_series(1, 5) AS r`

## pg-grant  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT); GRANT SELECT, INSERT ON t TO PUBLIC`

## pg-greatest-null  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('NULL',),)`
- src: `SELECT GREATEST(1, NULL, 3) AS r`

## pg-grouping-fn  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8161, b'Argument 1 of the GROUPING function does not match any of the expressions in the `
- src: `SELECT x, GROUPING(x) FROM (VALUES (1)) v(x) GROUP BY CUBE (x)`

## pg-grouping-sets  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())`

## pg-hex-literal  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00932: expression is of data type BINARY, which is incompatible with expected data typ`
- src: `SELECT x'FF'::int AS h, 1.5e3 AS s`

## pg-initcap  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT INITCAP('hello world') AS r`

## pg-insert-returning  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT, n INT); INSERT INTO t (id, n) VALUES (1, 5) RETURNING id`

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

## pg-jsonb-agg  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSONB_AGG(x) FROM (VALUES (1),(2)) v(x)`

## pg-jsonb-arrow  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT '{"a":1}'::jsonb -> 'a'`

## pg-jsonb-build  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSONB_BUILD_OBJECT('a', 1, 'b', 2)`

## pg-jsonb-path  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT '{"a":[1,2]}'::jsonb #> '{a,0}'`

## pg-justify  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '1 mon 40 days'.DB-Lib error message 20018, severity 15:\nGe`
- src: `SELECT JUSTIFY_INTERVAL(INTERVAL '1 mon 40 days') AS r`

## pg-left-neg  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('',),)`
- src: `SELECT LEFT('abc', -1) AS r`

## pg-like-cs  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'ABC' LIKE 'abc' AS r`

## pg-lock-table  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT); LOCK TABLE t IN SHARE MODE`

## pg-log-base  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('4.60517',),)`
- src: `SELECT LOG(100) AS r`

## pg-make-date  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT MAKE_DATE(2020, 6, 15), MAKE_TIME(10, 30, 0)`

## pg-math-log  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT LOG(10, 100), LN(2.718), POWER(2, 8), SQRT(16)`

## pg-md5  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT MD5('abc') AS r`

## pg-mod-decimal  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT MOD(10, 3.5::numeric) AS r`

## pg-mode  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT MODE() WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(1),(2)) v(x)`

## pg-multi-out  (postgresql)
- targets: oracle(invalid)
- live error: `FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared`
- src: `CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql`

## pg-network-types  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag`
- src: `CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)`

## pg-overlay  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV`
- src: `SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o`

## pg-partial-unique  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (a INT, b INT); CREATE UNIQUE INDEX ix ON t (a) WHERE b > 0`

## pg-percentile  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2),(3)) v(x)`

## pg-position-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT POSITION('' IN 'abc') AS r`

## pg-power-neg  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.5',),) target=()`
- src: `SELECT POWER(2, -1) AS r`

## pg-quote  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU`
- src: `SELECT QUOTE_LITERAL('O''Brien'), QUOTE_IDENT('my col')`

## pg-range-types  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m`
- src: `CREATE TABLE t (rng INT4RANGE, tsr TSRANGE)`

## pg-recursive-func  (postgresql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS INT AS $$ BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END; $$ LANGUAGE plpgsql`

## pg-recursive-view  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a INT, b INT); CREATE RECURSIVE VIEW v(n) AS SELECT 1 UNION ALL SELECT n+1 FROM v WHERE n < 5`

## pg-regexp-matches  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE`
- src: `SELECT REGEXP_MATCHES('a1b2', '[0-9]', 'g') AS r`

## pg-repeat-left-right  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00904: "RIGHT": invalid identifier`
- src: `SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)`

## pg-return-query  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE FUNCTION f() RETURNS SETOF INT AS $$ BEGIN RETURN QUERY SELECT 1 UNION SELECT 2; END; $$ LANGUAGE plpgsql`

## pg-rollup  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)`

## pg-savepoint  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'AS'.DB-Lib error message 20018, severity 15:\nG`
- src: `BEGIN; SAVEPOINT sp; ROLLBACK TO SAVEPOINT sp; COMMIT`

## pg-sequence  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne`
- src: `CREATE SEQUENCE seq; SELECT nextval('seq'), currval('seq')`

## pg-sequence-options  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE SEQUENCE seq INCREMENT 2 MINVALUE 10 MAXVALUE 100 CACHE 5 CYCLE`

## pg-serial-bit  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit`
- src: `CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))`

## pg-set-default  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5`

## pg-set-searchpath  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `SET search_path TO myschema, public`

## pg-size-funcs  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.pg`
- src: `SELECT pg_size_pretty(1024::bigint), pg_relation_size('pg_class')`

## pg-split-part  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT SPLIT_PART('a,b,c', ',', 2) AS r`

## pg-string-agg-order  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-string-to-array  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message `
- src: `SELECT string_to_array('a,b,c', ',')`

## pg-substr-zero  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('abc',),)`
- src: `SELECT SUBSTRING('abcdef', 0, 3) AS r`

## pg-substring-regex  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib`
- src: `SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r`

## pg-system-funcs  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT version(), current_database(), current_user, pg_backend_pid()`

## pg-tablesample  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT); SELECT * FROM t TABLESAMPLE BERNOULLI(50)`

## pg-to-hex-typeof  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT to_hex(255), pg_typeof(1)`

## pg-trailing-eq  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'a ' = 'a' AS r`

## pg-translate  (postgresql)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_5e892bc4b99a.TRANSLATE does not exist')`
- src: `SELECT TRANSLATE('abc', 'ab', 'xy') AS r`

## pg-trigger-multi-event  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE`

## pg-trigger-raise  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN IF OLD.n <> NEW.n THEN RAISE EXCE`

## pg-trigger-statement-level  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN RETURN NULL; END; $$ LANGUAGE plpgsql;
CREATE TRIGGE`

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

## pg-tz-interval  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-30089: missing or invalid <datetime field>`
- src: `CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)`

## pg-unicode-escape  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(207, b"Invalid column name 'U'.DB-Lib error message 20018, severity 16:\nGeneral SQL Serv`
- src: `SELECT U&'\0041' AS r`

## pg-unnest  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT UNNEST(ARRAY[1,2,3]) AS r`

## pg-update-returning  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT, n INT); UPDATE t SET n = 1 RETURNING id, n`

## pg-values-stmt  (postgresql)
- targets: mysql(invalid), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `VALUES (1, 'a'), (2, 'b')`

## pg-view-check  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t WITH LOCAL CHECK OPTION`

## pg-week  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT EXTRACT(WEEK FROM DATE '2020-01-05') AS r`

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
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.xp`
- src: `SELECT xpath('/a/text()', '<a>1</a>'::xml)`

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

## ts-after-delete-count  (tsql)
- targets: oracle(invalid)
- live error: `TRIGGER TRG compiled INVALID (line 4): PL/SQL: ORA-00942: table or view does not exist`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t AFTER DELETE AS BEGIN DECLARE @c INT = (SELECT COUNT(*) FRO`

## ts-after-update-trg  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT, updated DATETIME);
GO
CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN UPDATE t SET update`

## ts-alter-add  (tsql)
- targets: oracle(invalid)
- live error: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD b NVARCHAR(10) NOT NULL DEFAULT 'x'`

## ts-ascii-char  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NCHAR": invalid identifier`
- src: `SELECT ASCII('A'), CHAR(65), NCHAR(65)`

## ts-at-time-zone  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST('2020-01-01 10:00' AS DATETIME2) AT TIME ZONE 'UTC' AS r`

## ts-cast-bit  (tsql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT CAST(2 AS BIT) AS r`

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

## ts-collate  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 'a' COLLATE Latin1_General_CS_AS AS r`

## ts-collate2  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 'abc' COLLATE Latin1_General_BIN AS r`

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

## ts-cursor  (tsql)
- targets: mysql(invalid)
- live error: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT x FROM (VALUES (1),(2)) v(x); DECLARE @x INT; OPEN c; FETCH NEXT FROM c IN`

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

## ts-eomonth  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT EOMONTH('2020-02-15') AS r`

## ts-eomonth-nested  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT DATEADD(MONTH, -1, EOMONTH('2020-03-01')) AS r`

## ts-filtered-index  (tsql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-02158: invalid CREATE INDEX option`
- src: `CREATE TABLE t (a INT, b INT); CREATE NONCLUSTERED INDEX ix ON t (a) INCLUDE (b) WHERE a > 0`

## ts-format-number  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NUMBER_TO_STR": invalid identifier`
- src: `SELECT FORMAT(1234.5, 'N2') AS r`

## ts-grant  (tsql)
- targets: mysql(carrier), oracle(carrier), postgresql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT);
GO
GRANT SELECT ON t TO PUBLIC`

## ts-host-db  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "DB_NAME": invalid identifier`
- src: `SELECT HOST_NAME(), DB_NAME(), SUSER_SNAME()`

## ts-identity-funcs  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT SCOPE_IDENTITY(), @@IDENTITY, IDENT_CURRENT('t')`

## ts-insert-output  (tsql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-00925: missing INTO keyword`
- src: `CREATE TABLE t (id INT, n INT);
GO
INSERT INTO t (id, n) OUTPUT INSERTED.id VALUES (1, 5)`

## ts-instead-of-insert  (tsql)
- targets: mysql(invalid), postgresql(invalid)
- live error: `"t" is a table`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n) SELECT id,`

## ts-json-value  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT JSON_VALUE('{"a":1}', '$.a')`

## ts-lead-ignore-nulls  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT x, LEAD(x, 1) IGNORE NULLS OVER (ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## ts-len-trailing  (tsql)
- targets: mysql(func), oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('6',),)`
- src: `SELECT LEN('abc   ') AS r`

## ts-log  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT LOG(2.718), LOG10(100), POWER(2, 8)`

## ts-math  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CEILING(4.2), FLOOR(4.8), ROUND(4.555, 2), SQUARE(4)`

## ts-merge  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE tgt (id INT PRIMARY KEY, n INT); MERGE tgt USING (VALUES (1, 5)) AS s(id, n) ON tgt.id = s.id WHEN MATCHED THEN UPDAT`

## ts-metadata-funcs  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "OBJECT_ID": invalid identifier`
- src: `SELECT COL_LENGTH('t', 'c'), OBJECT_ID('t')`

## ts-money  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (price MONEY, small SMALLMONEY)`

## ts-nolock-hint  (tsql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT);
GO
SELECT * FROM t WITH (NOLOCK)`

## ts-openjson  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "OPEN_J_S_O_N": invalid identifier`
- src: `SELECT * FROM OPENJSON('[1,2,3]')`

## ts-patindex  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "PATINDEX": invalid identifier`
- src: `SELECT PATINDEX('%[0-9]%', 'abc123') AS r`

## ts-quotename  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SPLIT_PART": invalid identifier`
- src: `SELECT QUOTENAME('my table'), PARSENAME('a.b.c', 2)`

## ts-recursive-cte  (tsql)
- targets: mysql(invalid), postgresql(invalid)
- live error: `relation "r" does not exist`
- src: `WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r`

## ts-replicate-space  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SPACE": invalid identifier`
- src: `SELECT REPLICATE('ab', 3), SPACE(5), REVERSE('abc')`

## ts-rowversion  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (row_ver ROWVERSION, flags BINARY(8))`

## ts-select-into  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00905: missing keyword`
- src: `CREATE TABLE src (id INT);
GO
SELECT id INTO dst FROM src`

## ts-sequence-next  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NEXT_VALUE_FOR": invalid identifier`
- src: `CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1;
GO
SELECT NEXT VALUE FOR seq`

## ts-soundex-diff  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "DIFFERENCE": invalid identifier`
- src: `SELECT SOUNDEX('Smith'), DIFFERENCE('Smith', 'Smyth')`

## ts-sp-rename  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (a INT, b INT);
GO
EXEC sp_rename 't.a', 'x', 'COLUMN'`

## ts-spid-version  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT @@SPID, @@VERSION`

## ts-str-plus-num  (tsql)
- targets: mysql(func), oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('15',),) target=(('105',),)`
- src: `SELECT '10' + 5 AS r`

## ts-string-agg-within  (tsql)
- targets: postgresql(invalid)
- live error: `function string_agg(integer, unknown) does not exist`
- src: `SELECT STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## ts-stuff  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "STUFF": invalid identifier`
- src: `SELECT STUFF('abcdef', 2, 3, 'XY') AS r`

## ts-sysdatetime  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "GETUTCDATE": invalid identifier`
- src: `SELECT SYSDATETIME(), SYSUTCDATETIME(), GETUTCDATE()`

## ts-table-variable  (tsql)
- targets: oracle(invalid)
- live error: `ORA-06550: line 2, column 5:`
- src: `DECLARE @t TABLE (id INT); INSERT INTO @t VALUES (1); SELECT * FROM @t`

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

## ts-view-check  (tsql)
- targets: mysql(carrier), oracle(carrier), postgresql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t WHERE id > 0 WITH CHECK OPTION`

## ts-while-break-continue  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 11): PLS-00201: identifier 'BREAK' must be declared`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE @i INT = 0; WHILE @i < 5 BEGIN SET @i = @i + 1; IF @i = 3 CONTINUE; IF @i = 5 BREAK; END; END`

## ts-while-loop  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 15): PLS-00103: Encountered the symbol "=" when expecti`
- src: `CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN SET @n -=`

## ts-xml-value  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CAST('<a>1</a>' AS XML).value('(/a)[1]', 'INT') AS r`
---

Totals: 319 distinct constructs; defect rows by kind: carrier 62, func 88, invalid 498, semantic 2, silent-drop 14.
