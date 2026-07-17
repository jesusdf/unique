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

-- CASE[open]: ora-cast-onerror — fails on postgresql, tsql. (8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit
SELECT CAST('abc' AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM DUAL

-- CASE[open]: ora-clob-coalesce — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT COALESCE(TO_CLOB('a'), TO_CLOB('b')) AS r FROM DUAL

-- CASE[open]: ora-collect — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CAST(COLLECT(x) AS SYS.ODCINUMBERLIST) FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-comment-col — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id NUMBER); COMMENT ON COLUMN t.id IS 'the id'

-- CASE[open]: ora-compound-trigger — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id NUMBER, n NUMBER);
CREATE TRIGGER trg FOR UPDATE ON t COMPOUND TRIGGER BEFORE EACH ROW IS BEGIN NULL; END BEFORE EACH ROW; END trg;
/

-- CASE[open]: ora-concat-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT 'a' || NULL || 'b' AS r FROM DUAL

-- CASE[open]: ora-concat-num — fails on tsql. (245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er
SELECT 'a' || 5 AS r FROM DUAL

-- CASE[open]: ora-connect-by — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LEVEL, 1 AS n FROM DUAL CONNECT BY LEVEL <= 5

-- CASE[open]: ora-connect-by-root — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT CONNECT_BY_ROOT id AS root FROM (SELECT 1 id, NULL par FROM DUAL) CONNECT BY PRIOR id = par

-- CASE[open]: ora-connect-by2 — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT id FROM (SELECT 1 id, NULL par FROM DUAL) START WITH par IS NULL CONNECT BY PRIOR id = par

-- CASE[open]: ora-create-role — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE ROLE r

-- CASE[open]: ora-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;

-- CASE[open]: ora-cursor-for-loop — fails on tsql. (156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n
CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/

-- CASE[open]: ora-date-diff-days — fails on mysql. FUNC-DIFF: source=(('60',),) target=(('0',),)
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r FROM DUAL

-- CASE[open]: ora-date-plus-int — fails on mysql, postgresql. SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith
SELECT SYSDATE + 1 AS r FROM DUAL

-- CASE[open]: ora-day-of-week — fails on mysql. FUNC-DIFF: source=(('1',),) target=(('24',),)
SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL

-- CASE[open]: ora-decode-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('match',),) target=(('no',),)
SELECT DECODE(NULL, NULL, 'match', 'no') AS r FROM DUAL

-- CASE[open]: ora-div — fails on postgresql, tsql. FUNC-DIFF: source=(('2.5',),) target=(('2',),)
SELECT 5 / 2 AS r FROM DUAL

-- CASE[open]: ora-div-precision — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('0.333333',),) target=(('0',),)
SELECT 1 / 3 AS r FROM DUAL

-- CASE[open]: ora-dump — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('abc') AS r FROM DUAL

-- CASE[open]: ora-dump2 — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('A', 1016) AS r FROM DUAL

-- CASE[open]: ora-empty-is-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT CASE WHEN '' IS NULL THEN 1 ELSE 0 END AS r FROM DUAL

-- CASE[open]: ora-empty-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('x',),) target=(('',),)
SELECT NVL('', 'x') AS r FROM DUAL

-- CASE[open]: ora-exception-init — fails on mysql, postgresql, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type EXCEPTION.DB-Lib error m
CREATE PROCEDURE p AS e EXCEPTION; PRAGMA EXCEPTION_INIT(e, -20001); BEGIN RAISE e; END;
/

-- CASE[open]: ora-extractvalue — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXTRACTVALUE(XMLTYPE('<a>1</a>'), '/a') AS r FROM DUAL

-- CASE[open]: ora-fk-novalidate — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE p (id NUMBER PRIMARY KEY); CREATE TABLE c (pid NUMBER, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES p(id) ON DELETE CASCADE ENABLE NOVALIDATE)

-- CASE[open]: ora-for-update-nowait — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT

-- CASE[open]: ora-from-tz — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL

-- CASE[open]: ora-goto — fails on mysql, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'AS'.DB-Lib error message 20018, severity 15:\nG
CREATE PROCEDURE p AS BEGIN GOTO done; <<done>> NULL; END;
/

-- CASE[open]: ora-grant — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id NUMBER); GRANT SELECT ON t TO PUBLIC

-- CASE[open]: ora-grant-system — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
GRANT CREATE SESSION, CREATE TABLE TO r

-- CASE[open]: ora-hint-comment — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT /*+ FULL(t) */ 1 AS r FROM DUAL t

-- CASE[open]: ora-initcap — fails on mysql, postgresql, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r FROM DUAL

-- CASE[open]: ora-insert-all — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE a (id NUMBER); CREATE TABLE b (id NUMBER);
INSERT ALL INTO a (id) VALUES (x) INTO b (id) VALUES (x) SELECT 1 x FROM DUAL

-- CASE[open]: ora-insert-all-cond — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a NUMBER);
INSERT ALL WHEN a > 0 THEN INTO t VALUES (a) SELECT 1 a FROM DUAL

-- CASE[open]: ora-insert-append — fails on postgresql. validator-crash: sending query failed: another command is already in progress
CREATE TABLE t (a NUMBER); INSERT /*+ APPEND */ INTO t SELECT 1 FROM DUAL

-- CASE[open]: ora-interval-partition — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id NUMBER, dt DATE) PARTITION BY RANGE (dt) INTERVAL (NUMTOYMINTERVAL(1,'MONTH')) (PARTITION p0 VALUES LESS THAN (DATE '2020-01-01'))

-- CASE[open]: ora-interval-tochar — fails on postgresql. FUNC-DIFF: source=(('+02 03:04:05.000000',),) target=(('2 days 03:04:05',),)
SELECT TO_CHAR(INTERVAL '2 3:04:05.000' DAY TO SECOND) AS r FROM DUAL

-- CASE[open]: ora-json-object — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT JSON_OBJECT('a' VALUE 1) AS r FROM DUAL

-- CASE[open]: ora-json-table — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT * FROM JSON_TABLE('[1,2]', '$[*]' COLUMNS (v NUMBER PATH '$'))

-- CASE[open]: ora-json-value — fails on postgresql. SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'"] lost after oracle->tsql->oracle
SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL

-- CASE[open]: ora-last-day — fails on postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY(SYSDATE) AS r FROM DUAL

-- CASE[open]: ora-last-value-ignore — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LAST_VALUE(x IGNORE NULLS) OVER (ORDER BY x) FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-length-trailing — fails on tsql. FUNC-DIFF: source=(('6',),) target=(('3',),)
SELECT LENGTH('abc   ') AS r FROM DUAL

-- CASE[open]: ora-level2 — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LEVEL FROM DUAL CONNECT BY LEVEL <= 3

-- CASE[open]: ora-listagg — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)

-- CASE[open]: ora-listagg-over — fails on mysql, postgresql, tsql. (4113, b"The function 'STRING_AGG' is not a valid windowing function, and cannot be used w
SELECT deptno, LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) OVER (PARTITION BY deptno) FROM (SELECT 1 deptno, 2 x FROM DUAL)

-- CASE[open]: ora-lnnvl — fails on mysql, postgresql, tsql. (102, b"Incorrect syntax near '='.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT LNNVL(1 = 2) AS r FROM DUAL WHERE LNNVL(1 = 2)

-- CASE[open]: ora-month-name — fails on mysql. FUNC-DIFF: source=(('June',),) target=(('Month',),)
SELECT TO_CHAR(DATE '2020-06-01', 'Month') AS r FROM DUAL

-- CASE[open]: ora-months-between — fails on mysql, postgresql. operator does not exist: timestamp with time zone - integer
SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL

-- CASE[open]: ora-months-between-val — fails on tsql. FUNC-DIFF: source=(('1.83871',),) target=(('2',),)
SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL

-- CASE[open]: ora-nanvl — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NANVL(0/1, 0) AS r FROM DUAL

-- CASE[open]: ora-nested-proc — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE PROCEDURE p AS PROCEDURE helper IS BEGIN NULL; END; BEGIN helper; END;
/

-- CASE[open]: ora-next-day — fails on mysql, postgresql, tsql. (195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL

-- CASE[open]: ora-nlssort — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NL
SELECT NLSSORT('abc', 'NLS_SORT=BINARY_CI') AS r FROM DUAL

-- CASE[open]: ora-num-concat — fails on tsql. FUNC-DIFF: source=(('23',),) target=(('5',),)
SELECT 2 || 3 AS r FROM DUAL

-- CASE[open]: ora-numtodsinterval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL

-- CASE[open]: ora-ora-hash — fails on mysql, postgresql, tsql. (195, b"'ORA_HASH' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT ORA_HASH('abc') AS r FROM DUAL

-- CASE[open]: ora-order-nulls-default — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))
SELECT x FROM (SELECT 3 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL) ORDER BY x

-- CASE[open]: ora-package-body — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['could not translate']
CREATE PACKAGE pkg AS FUNCTION f(x NUMBER) RETURN NUMBER; END pkg;
/
CREATE PACKAGE BODY pkg AS FUNCTION f(x NUMBER) RETURN NUMBER IS BEGIN RETURN x*2; END; END pkg;
/

-- CASE[open]: ora-package-spec — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['could not translate']
CREATE PACKAGE pkg AS PROCEDURE p; FUNCTION f RETURN NUMBER; END pkg;
/

-- CASE[open]: ora-pk-using-index — fails on mysql, postgresql, tsql. (1018, b"Incorrect syntax near 'INDEX'. If this is intended as a part of a table hint, A W
CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)

-- CASE[open]: ora-ratio-to-report — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(x) OVER () FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-ratio2 — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(1) OVER () FROM DUAL

-- CASE[open]: ora-realworld-emp — fails on tsql. (1003, b'Line 13: FOR UPDATE clause allowed only for DECLARE CURSOR.DB-Lib error message 2
CREATE TABLE emp (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name VARCHAR2(50), mgr_id NUMBER, salary NUMBER(10,2));
ALTER TABLE emp ADD CONSTRAINT fk_mgr FOREIGN KEY (mgr_id) REFERENCES emp(id);
CREATE OR REPLACE PROCEDURE give_raise(p_id NUMBER, p_pct NUMBER) AS
v_sal NUMBER;
BEGIN
SELECT salary INTO v_sal FROM emp WHERE id = p_id FOR UPDATE;
UPDATE emp SET salary = v_sal * (1 + p_pct/100) WHERE id = p_id;
COMMIT;
EXCEPTION WHEN NO_DATA_FOUND THEN RAISE_APPLICATION_ERROR(-20001, 'no such employee'); END;
/

-- CASE[open]: ora-realworld-orders — fails on mysql, postgresql. relation "orders" already exists
CREATE TABLE orders (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, customer_id NUMBER NOT NULL, total NUMBER(10,2) DEFAULT 0, created DATE DEFAULT SYSDATE);
CREATE INDEX ix_cust ON orders (customer_id);
CREATE OR REPLACE PROCEDURE add_order(p_cid IN NUMBER, p_total IN NUMBER) AS BEGIN INSERT INTO orders (customer_id, total) VALUES (p_cid, p_total); COMMIT; END;
/

-- CASE[open]: ora-record-type — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['could not translate']
CREATE PROCEDURE p AS TYPE rec IS RECORD (a NUMBER, b VARCHAR2(10)); r rec; BEGIN r.a := 1; END;
/

-- CASE[open]: ora-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/

-- CASE[open]: ora-regexp-count — fails on mysql. (1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')
SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL

-- CASE[open]: ora-regexp-like — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT REGEXP_LIKE('abc', '^a') AS matched FROM DUAL WHERE REGEXP_LIKE('abc', '^a')

-- CASE[open]: ora-reverse-index — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a NUMBER, b NUMBER);
CREATE INDEX ix ON t (a) REVERSE

-- CASE[open]: ora-round-date-month — fails on mysql. FUNC-DIFF: source=(('2020-07-01 00:00:00',),) target=(('2020',),)
SELECT ROUND(DATE '2020-06-16', 'MONTH') AS r FROM DUAL

-- CASE[open]: ora-rtrim-chars — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('a',),) target=(('',),)
SELECT RTRIM('axxx', 'x') AS r FROM DUAL

-- CASE[open]: ora-sequence — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE SEQUENCE seq START WITH 1;
SELECT seq.NEXTVAL FROM DUAL

-- CASE[open]: ora-sequence-options — fails on mysql, postgresql, tsql. (102, b"Incorrect syntax near 'NOCYCLE'.DB-Lib error message 20018, severity 15:\nGeneral 
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE ORDER

-- CASE[open]: ora-soundex — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') AS r FROM DUAL

-- CASE[open]: ora-sqlerrm — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE PROCEDURE p AS BEGIN NULL; EXCEPTION WHEN NO_DATA_FOUND THEN RAISE; WHEN OTHERS THEN RAISE_APPLICATION_ERROR(-20001, SQLERRM); END;
/

-- CASE[open]: ora-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('de',),) target=(('',),)
SELECT SUBSTR('abcdef', -3, 2) AS r FROM DUAL

-- CASE[open]: ora-sys-connect-path — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT SYS_CONNECT_BY_PATH(id, '/') AS p FROM (SELECT 1 id, NULL par FROM DUAL) START WITH par IS NULL CONNECT BY PRIOR id = par

-- CASE[open]: ora-sys-extract-utc — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SY
SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) AS r FROM DUAL

-- CASE[open]: ora-table-collection — fails on mysql, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:
SELECT * FROM TABLE(SYS.ODCINUMBERLIST(1,2,3))

-- CASE[open]: ora-tablespace — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a NUMBER) TABLESPACE users

-- CASE[open]: ora-to-char-day — fails on mysql. FUNC-DIFF: source=(('SUNDAY',),) target=(('Sunday',),)
SELECT TO_CHAR(DATE '2020-06-14', 'DAY') AS r FROM DUAL

-- CASE[open]: ora-to-number-sci — fails on tsql. (8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit
SELECT TO_NUMBER('1.234E2') AS r FROM DUAL

-- CASE[open]: ora-to-timestamp — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT TO_TIMESTAMP('2020-01-01 10:00:00.123', 'YYYY-MM-DD HH24:MI:SS.FF') AS r FROM DUAL

-- CASE[open]: ora-tochar-neg — fails on mysql. FUNC-DIFF: source=(('-1234.5',),) target=(('NULL',),)
SELECT TO_CHAR(-1234.5, '9999.99') AS r FROM DUAL

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

-- CASE[open]: ora-utl-raw — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "UTL_RAW" or the user-defined function or aggregate "UT
SELECT UTL_RAW.CAST_TO_RAW('abc') AS r FROM DUAL

-- CASE[open]: ora-vsize — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.VS
SELECT VSIZE(123) AS r FROM DUAL

-- CASE[open]: ora-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT WIDTH_BUCKET(5, 0, 10, 5) AS r FROM DUAL

-- CASE[open]: ora-xmlelement — fails on mysql, postgresql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT XMLELEMENT("foo", 'bar') AS r FROM DUAL

-- CASE[open]: ora-zero-divide — fails on postgresql. unrecognized exception condition "zero_divide"
CREATE PROCEDURE p AS v NUMBER; BEGIN v := 1/0; EXCEPTION WHEN ZERO_DIVIDE THEN v := 0; END;
/

-- CASE[open]: oracle-drop2-100|START — fails on postgresql, tsql. SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning
CREATE TABLE t (id NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100))

-- CASE[open]: oracle-drop4-COLLATE — fails on mysql, postgresql, tsql. SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning
CREATE TABLE t (a VARCHAR2(10) COLLATE BINARY_CI)

