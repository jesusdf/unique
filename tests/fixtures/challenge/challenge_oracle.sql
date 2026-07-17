-- Challenge fixtures — Oracle / PL-SQL source.
-- Anonymized tricky constructs; one per entry. See README.md.

-- CASE: self-qualified parameter reference (<routine>.<param>).
-- Oracle lets a body reference a formal parameter as ``<subprogram>.<param>``.
-- No target engine has that form, and sqlglot cannot parse it in a FETCH FIRST
-- count, so the qualifier must be stripped and the bare parameter renamed to
-- the target variable (T-SQL @row_limit / SELECT TOP, MySQL LIMIT).
CREATE OR REPLACE PROCEDURE get_top_rows
(
    row_limit       IN NUMBER DEFAULT 10,
    result_cursor   OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN result_cursor FOR
        SELECT *
        FROM t
        FETCH FIRST get_top_rows.row_limit ROWS ONLY;
END;
/

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: ora-add-months — fails on mysql, postgresql, tsql. (195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018
SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL

-- CASE[open]: ora-alter-session — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD'

-- CASE[open]: ora-bitand — fails on mysql, postgresql, tsql. (195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT BITAND(5, 3) AS r FROM DUAL

-- CASE[open]: ora-bulk-collect — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['could not translate']
CREATE PROCEDURE p AS TYPE t_tab IS TABLE OF NUMBER; v t_tab; BEGIN SELECT 1 BULK COLLECT INTO v FROM DUAL; END;
/

-- CASE[open]: ora-case-statement — fails on tsql. (156, b"Incorrect syntax near the keyword 'ELSE'.DB-Lib error message 20018, severity 15:\
CREATE PROCEDURE p (n IN NUMBER) AS BEGIN CASE n WHEN 1 THEN NULL; ELSE NULL; END CASE; END;
/

-- CASE[open]: ora-cast-expr — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL

-- CASE[open]: ora-comment-col — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id NUMBER); COMMENT ON COLUMN t.id IS 'the id'

-- CASE[open]: ora-concat-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT 'a' || NULL || 'b' AS r FROM DUAL

-- CASE[open]: ora-concat-num — fails on tsql. (245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er
SELECT 'a' || 5 AS r FROM DUAL

-- CASE[open]: ora-connect-by — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LEVEL, 1 AS n FROM DUAL CONNECT BY LEVEL <= 5

-- CASE[open]: ora-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;

-- CASE[open]: ora-cursor-for-loop — fails on tsql. (156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n
CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/

-- CASE[open]: ora-date-plus-int — fails on mysql, postgresql. SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith
SELECT SYSDATE + 1 AS r FROM DUAL

-- CASE[open]: ora-day-of-week — fails on mysql. FUNC-DIFF: source=(('1',),) target=(('24',),)
SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL

-- CASE[open]: ora-div — fails on postgresql, tsql. FUNC-DIFF: source=(('2.5',),) target=(('2',),)
SELECT 5 / 2 AS r FROM DUAL

-- CASE[open]: ora-dump — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('abc') AS r FROM DUAL

-- CASE[open]: ora-empty-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('x',),) target=(('',),)
SELECT NVL('', 'x') AS r FROM DUAL

-- CASE[open]: ora-exception-init — fails on mysql, postgresql, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type EXCEPTION.DB-Lib error m
CREATE PROCEDURE p AS e EXCEPTION; PRAGMA EXCEPTION_INIT(e, -20001); BEGIN RAISE e; END;
/

-- CASE[open]: ora-fk-novalidate — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE p (id NUMBER PRIMARY KEY); CREATE TABLE c (pid NUMBER, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES p(id) ON DELETE CASCADE ENABLE NOVALIDATE)

-- CASE[open]: ora-for-update-nowait — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT

-- CASE[open]: ora-from-tz — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL

-- CASE[open]: ora-grant — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id NUMBER); GRANT SELECT ON t TO PUBLIC

-- CASE[open]: ora-initcap — fails on mysql, postgresql, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r FROM DUAL

-- CASE[open]: ora-insert-all — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE a (id NUMBER); CREATE TABLE b (id NUMBER);
INSERT ALL INTO a (id) VALUES (x) INTO b (id) VALUES (x) SELECT 1 x FROM DUAL

-- CASE[open]: ora-json-object — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT JSON_OBJECT('a' VALUE 1) AS r FROM DUAL

-- CASE[open]: ora-json-value — fails on postgresql. SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'"] lost after oracle->tsql->oracle
SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL

-- CASE[open]: ora-last-day — fails on postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY(SYSDATE) AS r FROM DUAL

-- CASE[open]: ora-last-value-ignore — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LAST_VALUE(x IGNORE NULLS) OVER (ORDER BY x) FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-length-trailing — fails on tsql. FUNC-DIFF: source=(('6',),) target=(('3',),)
SELECT LENGTH('abc   ') AS r FROM DUAL

-- CASE[open]: ora-listagg — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)

-- CASE[open]: ora-months-between — fails on mysql, postgresql. operator does not exist: timestamp with time zone - integer
SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL

-- CASE[open]: ora-months-between-val — fails on tsql. FUNC-DIFF: source=(('1.83871',),) target=(('2',),)
SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL

-- CASE[open]: ora-nanvl — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NANVL(0/1, 0) AS r FROM DUAL

-- CASE[open]: ora-next-day — fails on mysql, postgresql, tsql. (195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL

-- CASE[open]: ora-num-concat — fails on tsql. FUNC-DIFF: source=(('23',),) target=(('5',),)
SELECT 2 || 3 AS r FROM DUAL

-- CASE[open]: ora-numtodsinterval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL

-- CASE[open]: ora-ora-hash — fails on mysql, postgresql, tsql. (195, b"'ORA_HASH' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT ORA_HASH('abc') AS r FROM DUAL

-- CASE[open]: ora-package-spec — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['could not translate']
CREATE PACKAGE pkg AS PROCEDURE p; FUNCTION f RETURN NUMBER; END pkg;
/

-- CASE[open]: ora-pk-using-index — fails on mysql, postgresql, tsql. (1018, b"Incorrect syntax near 'INDEX'. If this is intended as a part of a table hint, A W
CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)

-- CASE[open]: ora-ratio-to-report — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(x) OVER () FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/

-- CASE[open]: ora-regexp-count — fails on mysql. (1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')
SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL

-- CASE[open]: ora-rtrim-chars — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('a',),) target=(('',),)
SELECT RTRIM('axxx', 'x') AS r FROM DUAL

-- CASE[open]: ora-sequence — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE SEQUENCE seq START WITH 1;
SELECT seq.NEXTVAL FROM DUAL

-- CASE[open]: ora-sequence-options — fails on mysql, postgresql, tsql. (102, b"Incorrect syntax near 'NOCYCLE'.DB-Lib error message 20018, severity 15:\nGeneral 
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE ORDER

-- CASE[open]: ora-soundex — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') AS r FROM DUAL

-- CASE[open]: ora-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('de',),) target=(('',),)
SELECT SUBSTR('abcdef', -3, 2) AS r FROM DUAL

-- CASE[open]: ora-sys-connect-path — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT SYS_CONNECT_BY_PATH(id, '/') AS p FROM (SELECT 1 id, NULL par FROM DUAL) START WITH par IS NULL CONNECT BY PRIOR id = par

-- CASE[open]: ora-tablespace — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a NUMBER) TABLESPACE users

-- CASE[open]: ora-to-char-day — fails on mysql. FUNC-DIFF: source=(('SUNDAY',),) target=(('Sunday',),)
SELECT TO_CHAR(DATE '2020-06-14', 'DAY') AS r FROM DUAL

-- CASE[open]: ora-trailing-eq — fails on tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT CASE WHEN 'a ' = 'a' THEN 1 ELSE 0 END AS r FROM DUAL

-- CASE[open]: ora-translate — fails on mysql. (1305, 'FUNCTION unique_val_6c47c43e12f3.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r FROM DUAL

-- CASE[open]: ora-tz-funcs — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT SYSTIMESTAMP, LOCALTIMESTAMP, SESSIONTIMEZONE FROM DUAL

-- CASE[open]: ora-tz-interval — fails on mysql, tsql. (102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL 
CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)

-- CASE[open]: ora-user-context — fails on mysql, postgresql, tsql. (195, b"'SYS_CONTEXT' is not a recognized built-in function name.DB-Lib error message 2001
SELECT USER, SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL

-- CASE[open]: ora-vsize — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.VS
SELECT VSIZE(123) AS r FROM DUAL

-- CASE[open]: ora-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT WIDTH_BUCKET(5, 0, 10, 5) AS r FROM DUAL

