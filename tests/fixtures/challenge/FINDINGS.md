# Challenge findings ledger (RED)

Source constructs that transpile wrong on >=1 target, each **validated on a
live engine** (original accepted by its own engine; output rejected by the
target engine, or degraded to an unrecognized carrier). Tagged `[open]` in
the `challenge_<engine>.sql` scripts; BLUE fixes and flips to `[fixed]`.

Kinds: **invalid** = live target rejected the output; **carrier** = degraded
to an `Unhandled`/unrecognized carrier (may be an acceptable degrade — BLUE
triages); **silent/-rt** = valid output but a source literal vanished (verify manually — the literal detector is noisy).


## my-alter-modify  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT`

## my-base64  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO`
- src: `SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')`

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

## my-length-bytes  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('5',),) target=(('4',),)`
- src: `SELECT LENGTH('café') AS r`

## my-like-ci  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'ABC' LIKE 'abc' AS r`

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

## my-soundex-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)`

## my-substring-index  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU`
- src: `SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r`

## my-timestampadd  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-30081: invalid data type for datetime/interval arithmetic`
- src: `SELECT TIMESTAMPADD(MINUTE, 30, '2020-01-01 10:00') AS r`

## my-timestampdiff  (mysql)
- targets: oracle(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r`

## my-unix-timestamp  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2`
- src: `SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)`

## my-update-join  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n`

## my-week-quarter  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE`
- src: `SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')`

## ora-add-months  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL`

## ora-bitand  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT BITAND(5, 3) AS r FROM DUAL`

## ora-bulk-collect  (oracle)
- targets: mysql(invalid), postgresql(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['could not translate']`
- src: `CREATE PROCEDURE p AS TYPE t_tab IS TABLE OF NUMBER; v t_tab; BEGIN SELECT 1 BULK COLLECT INTO v FROM DUAL; END;
/`

## ora-cast-expr  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL`

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

## ora-cursor  (oracle)
- targets: mysql(invalid)
- live error: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;`

## ora-date-plus-int  (oracle)
- targets: mysql(semantic), postgresql(invalid)
- live error: `SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith`
- src: `SELECT SYSDATE + 1 AS r FROM DUAL`

## ora-div  (oracle)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.5',),) target=(('2',),)`
- src: `SELECT 5 / 2 AS r FROM DUAL`

## ora-dump  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU`
- src: `SELECT DUMP('abc') AS r FROM DUAL`

## ora-empty-null  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('x',),) target=(('',),)`
- src: `SELECT NVL('', 'x') AS r FROM DUAL`

## ora-exception-init  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #1: Cannot find data type EXCEPTION.DB-Lib error m`
- src: `CREATE PROCEDURE p AS e EXCEPTION; PRAGMA EXCEPTION_INIT(e, -20001); BEGIN RAISE e; END;
/`

## ora-fk-novalidate  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE p (id NUMBER PRIMARY KEY); CREATE TABLE c (pid NUMBER, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES p(id) ON DELETE CAS`

## ora-from-tz  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR`
- src: `SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL`

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

## ora-listagg  (oracle)
- targets: postgresql(invalid)
- live error: `function string_agg(integer, unknown) does not exist`
- src: `SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)`

## ora-months-between  (oracle)
- targets: mysql(invalid), postgresql(invalid)
- live error: `operator does not exist: timestamp with time zone - integer`
- src: `SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL`

## ora-next-day  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL`

## ora-num-concat  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('23',),) target=(('5',),)`
- src: `SELECT 2 || 3 AS r FROM DUAL`

## ora-numtodsinterval  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL`

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

## ora-regexp-count  (oracle)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')`
- src: `SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL`

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

## ora-translate  (oracle)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_6c47c43e12f3.TRANSLATE does not exist')`
- src: `SELECT TRANSLATE('abc', 'ab', 'xy') AS r FROM DUAL`

## ora-tz-interval  (oracle)
- targets: mysql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL `
- src: `CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)`

## pg-age  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a`

## pg-alter-add  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'`

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

## pg-at-time-zone  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D`
- src: `SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r`

## pg-before-update-trg  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT, updated TIMESTAMP);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN NEW.updated :=`

## pg-cast-int  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT CAST(2.7 AS INT) AS r`

## pg-collate  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 'a' < 'B' COLLATE "C" AS r`

## pg-comment-on  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a INT); COMMENT ON COLUMN t.a IS 'the a column'`

## pg-composite-type  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TYPE addr AS (street TEXT, city TEXT)`

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

## pg-domain  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE DOMAIN posint AS INT CHECK (VALUE > 0)`

## pg-encode-base64  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se`
- src: `SELECT ENCODE('abc'::bytea, 'base64') AS r`

## pg-estring  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT E'line1\nline2' AS r`

## pg-exception-handler  (postgresql)
- targets: tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql`

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

## pg-fulltext  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `SELECT to_tsvector('a cat') @@ to_tsquery('cat') AS r`

## pg-generate-series  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE`
- src: `SELECT generate_series(1, 5) AS r`

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

## pg-like-cs  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT 'ABC' LIKE 'abc' AS r`

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

## pg-percentile  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2),(3)) v(x)`

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

## pg-split-part  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT SPLIT_PART('a,b,c', ',', 2) AS r`

## pg-string-agg-order  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-substr-zero  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('abc',),)`
- src: `SELECT SUBSTRING('abcdef', 0, 3) AS r`

## pg-substring-regex  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib`
- src: `SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r`

## pg-translate  (postgresql)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_5e892bc4b99a.TRANSLATE does not exist')`
- src: `SELECT TRANSLATE('abc', 'ab', 'xy') AS r`

## pg-trigger-raise  (postgresql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN IF OLD.n <> NEW.n THEN RAISE EXCE`

## pg-trim-both-chars  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-30001: trim set should have only one character`
- src: `SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS t`

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

## pg-view-check  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t WITH LOCAL CHECK OPTION`

## pg-xmlelement  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT XMLELEMENT(NAME foo, 'bar') AS r`

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

## ts-cast-trycast  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01722: unable to convert string value containing 'x' to a number: `
- src: `SELECT CAST(123 AS VARCHAR(10)), TRY_CAST('x' AS INT), CONVERT(DATE, GETDATE())`

## ts-choose  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "CHOOSE": invalid identifier`
- src: `SELECT CHOOSE(2, 'a', 'b', 'c') AS r`

## ts-collate  (tsql)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT 'a' COLLATE Latin1_General_CS_AS AS r`

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

## ts-money  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (price MONEY, small SMALLMONEY)`

## ts-openjson  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "OPEN_J_S_O_N": invalid identifier`
- src: `SELECT * FROM OPENJSON('[1,2,3]')`

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

## ts-top-with-ties  (tsql)
- targets: postgresql(semantic)
- live error: `SILENT LOSS: TOP n WITH TIES -> plain LIMIT n on PG/MySQL (ties dropped); on Oracle the ro`
- src: `SELECT TOP 1 WITH TIES x FROM (VALUES (1),(1),(2)) v(x) ORDER BY x`

## ts-try-convert  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01722: unable to convert string value containing 'a' to a number: `
- src: `SELECT TRY_CONVERT(INT, 'abc') AS r`

## ts-view-check  (tsql)
- targets: mysql(carrier), oracle(carrier), postgresql(carrier)
- live error: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t WHERE id > 0 WITH CHECK OPTION`

## ts-while-loop  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 15): PLS-00103: Encountered the symbol "=" when expecti`
- src: `CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN SET @n -=`
---

Totals: 193 distinct constructs; 335 invalid-output rows, 71 carrier rows.
