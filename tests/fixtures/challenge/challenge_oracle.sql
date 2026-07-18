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

-- CASE[open]: or-distinct-null — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('2',), ('NULL',)) target=(('NULL',), ('1',), ('2',))
SELECT DISTINCT x FROM (SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL UNION ALL SELECT 2 x FROM DUAL) ORDER BY x

-- CASE[open]: or-order-strings — fails on mysql. FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), 
SELECT x FROM (SELECT 'banana' x FROM DUAL UNION ALL SELECT 'Apple' x FROM DUAL UNION ALL SELECT 'cherry' x FROM DUAL UNION ALL SELECT 'Banana' x FROM DUAL) ORDER BY x

-- CASE[open]: ora-add-months — fails on mysql, postgresql, tsql. (195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018
SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL

-- CASE[open]: ora-agg-collect — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x,',') WITHIN GROUP(ORDER BY x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 x FROM DUAL)

-- CASE[open]: ora-agg-median — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ME
SELECT MEDIAN(x),STATS_MODE(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT 2 x FROM DUAL)

-- CASE[open]: ora-alter-suite — fails on tsql. (5074, b"The object 'DF__t__name__6D63CF5D' is dependent on column 'nm'.DB-Lib error messa
CREATE TABLE t (id NUMBER);
ALTER TABLE t ADD (name VARCHAR2(50) DEFAULT '' NOT NULL);
ALTER TABLE t MODIFY (id NUMBER(19));
ALTER TABLE t RENAME COLUMN name TO nm;
ALTER TABLE t DROP COLUMN nm;

-- CASE[open]: ora-arr-collect — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "SYS" or the user-defined function or aggregate "SYS.OD
SELECT SYS.ODCINUMBERLIST(1,2,3) FROM DUAL

-- CASE[open]: ora-asciistr — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.AS
SELECT ASCIISTR('ABÄCD'), UNISTR('\0041') FROM DUAL

-- CASE[open]: ora-baseconv — fails on mysql, postgresql, tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT TO_CHAR(255,'XXX'),BIN_TO_NUM(1,1,1,1,1,1,1,1) FROM DUAL

-- CASE[open]: ora-bit-fns — fails on mysql, postgresql, tsql. (195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT BITAND(12, 10), BIN_TO_NUM(1,1,0) FROM DUAL

-- CASE[open]: ora-bitand — fails on mysql, postgresql, tsql. (195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT BITAND(5, 3) AS r FROM DUAL

-- CASE[open]: ora-case-statement — fails on tsql. (156, b"Incorrect syntax near the keyword 'ELSE'.DB-Lib error message 20018, severity 15:\
CREATE PROCEDURE p (n IN NUMBER) AS BEGIN CASE n WHEN 1 THEN NULL; ELSE NULL; END CASE; END;
/

-- CASE[open]: ora-cast-datetime3 — fails on mysql, tsql. (243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity
SELECT CAST(SYSTIMESTAMP AS DATE), CAST(SYSDATE AS TIMESTAMP), CAST(SYSDATE AS TIMESTAMP WITH TIME ZONE) FROM DUAL

-- CASE[open]: ora-cast-expr — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL

-- CASE[open]: ora-cast-int-edge — fails on mysql. FUNC-DIFF: source=(('4', '3', '4', '4'),) target=(('3', '3', '4', '4'),)
SELECT CAST('3.9' AS INT), TRUNC(3.9), ROUND(3.9), CAST(3.9 AS NUMBER(1)) FROM DUAL

-- CASE[open]: ora-cast-onerror — fails on postgresql, tsql. (8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit
SELECT CAST('abc' AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM DUAL

-- CASE[open]: ora-char-encoding — fails on mysql, postgresql, tsql. (195, b"'RAWTOHEX' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT ASCII('A'),CHR(65),RAWTOHEX('AB'),UTL_RAW.CAST_TO_RAW('AB'),DUMP('AB'),NCHR(65) FROM DUAL

-- CASE[open]: ora-clob-coalesce — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT COALESCE(TO_CLOB('a'), TO_CLOB('b')) AS r FROM DUAL

-- CASE[open]: ora-clob-ops — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT TO_CLOB('x') || TO_CLOB('y'), DBMS_LOB.SUBSTR(TO_CLOB('hello'), 3) FROM DUAL

-- CASE[open]: ora-collect — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CAST(COLLECT(x) AS SYS.ODCINUMBERLIST) FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-compose — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT COMPOSE('a'||UNISTR('\0301')), DECOMPOSE('á') FROM DUAL

-- CASE[open]: ora-concat-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT 'a' || NULL || 'b' AS r FROM DUAL

-- CASE[open]: ora-concat-num — fails on tsql. (245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er
SELECT 'a' || 5 AS r FROM DUAL

-- CASE[open]: ora-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;

-- CASE[open]: ora-cursor-attr — fails on mysql, tsql. (128, b'The name "c" is not permitted in this context. Valid expressions are constants, co
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; IF c%FOUND THEN DBMS_OUTPUT.PUT_LINE(c%ROWCOUNT); END IF; CLOSE c; END;
/

-- CASE[open]: ora-cursor-for-loop — fails on tsql. (156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n
CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/

-- CASE[open]: ora-date-arith2 — fails on mysql, postgresql, tsql. (195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018
SELECT ADD_MONTHS(SYSDATE,3), NEXT_DAY(SYSDATE,'MONDAY'), LAST_DAY(SYSDATE) FROM DUAL

-- CASE[open]: ora-date-diff-days — fails on mysql. FUNC-DIFF: source=(('60',),) target=(('0',),)
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r FROM DUAL

-- CASE[open]: ora-date-plus-int — fails on mysql, postgresql. SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith
SELECT SYSDATE + 1 AS r FROM DUAL

-- CASE[open]: ora-date-plus-int2 — fails on mysql. FUNC-DIFF: source=(('2020-01-31 00:00:00',),) target=(('2050',),)
SELECT DATE '2020-01-01' + 30 AS r FROM DUAL

-- CASE[open]: ora-day-of-week — fails on mysql. FUNC-DIFF: source=(('1',),) target=(('24',),)
SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL

-- CASE[open]: ora-decode-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('match',),) target=(('no',),)
SELECT DECODE(NULL, NULL, 'match', 'no') AS r FROM DUAL

-- CASE[open]: ora-div — fails on postgresql, tsql. FUNC-DIFF: source=(('2.5',),) target=(('2',),)
SELECT 5 / 2 AS r FROM DUAL

-- CASE[open]: ora-div-mult2 — fails on postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 1/3*3 AS r FROM DUAL

-- CASE[open]: ora-div-precision — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('0.333333',),) target=(('0',),)
SELECT 1 / 3 AS r FROM DUAL

-- CASE[open]: ora-dttypes — fails on postgresql, tsql. (102, b"Incorrect syntax near 'YEAR'.DB-Lib error message 20018, severity 15:\nGeneral SQL
CREATE TABLE t (a DATE, b TIMESTAMP, c TIMESTAMP WITH TIME ZONE, d TIMESTAMP WITH LOCAL TIME ZONE, e INTERVAL YEAR TO MONTH, f INTERVAL DAY TO SECOND)

-- CASE[open]: ora-dump — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('abc') AS r FROM DUAL

-- CASE[open]: ora-dump2 — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('A', 1016) AS r FROM DUAL

-- CASE[open]: ora-dyn-count — fails on tsql. (102, b"Incorrect syntax near '+'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
CREATE PROCEDURE p (tbl VARCHAR2) AS n NUMBER; BEGIN EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || tbl INTO n; END;
/

-- CASE[open]: ora-edit-distance — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "UTL_MATCH" or the user-defined function or aggregate "
SELECT UTL_MATCH.EDIT_DISTANCE('hello', 'hallo') AS r FROM DUAL

-- CASE[open]: ora-empty-is-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT CASE WHEN '' IS NULL THEN 1 ELSE 0 END AS r FROM DUAL

-- CASE[open]: ora-empty-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('x',),) target=(('',),)
SELECT NVL('', 'x') AS r FROM DUAL

-- CASE[open]: ora-extract — fails on mysql. FUNC-DIFF: source=(('2020', '6', '2', '2'),) target=(('2020', '6', '25', 'Q'),)
SELECT EXTRACT(YEAR FROM DATE '2020-06-15'), EXTRACT(MONTH FROM DATE '2020-06-15'), TO_CHAR(DATE '2020-06-15','D'), TO_CHAR(DATE '2020-06-15','Q') FROM DUAL

-- CASE[open]: ora-extractvalue — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXTRACTVALUE(XMLTYPE('<a>1</a>'), '/a') AS r FROM DUAL

-- CASE[open]: ora-fconcat — fails on mysql, tsql. FUNC-DIFF: source=(('ab', 'a', '23'),) target=(('ab', 'NULL', '5'),)
SELECT 'a'||'b','a'||NULL,2||3 FROM DUAL

-- CASE[open]: ora-fk-and-check — fails on mysql. (1239, "Incorrect foreign key definition for 'fk': Key reference and table reference don't
CREATE TABLE parent (id NUMBER PRIMARY KEY); CREATE TABLE child (pid NUMBER, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES parent ON DELETE CASCADE, CONSTRAINT fk2 CHECK (pid > 0))

-- CASE[open]: ora-float-precision — fails on mysql. FUNC-DIFF: source=(('0.3', '0.3', '0.333333'),) target=(('0.3', '0.3', '0.33333'),)
SELECT 0.1+0.2, CAST(0.1 AS BINARY_DOUBLE)+CAST(0.2 AS BINARY_DOUBLE), 1.0/3 FROM DUAL

-- CASE[open]: ora-fmt-dayname — fails on mysql. FUNC-DIFF: source=(('MONDAY',),) target=(('Monday',),)
SELECT TO_CHAR(DATE '2020-06-15', 'DAY') AS r FROM DUAL

-- CASE[open]: ora-fmt-quarter — fails on mysql. FUNC-DIFF: source=(('2',),) target=(('Q',),)
SELECT TO_CHAR(DATE '2020-06-15', 'Q') AS r FROM DUAL

-- CASE[open]: ora-fmt-week — fails on mysql. FUNC-DIFF: source=(('24',),) target=(('Monday',),)
SELECT TO_CHAR(DATE '2020-06-15', 'WW') AS r FROM DUAL

-- CASE[open]: ora-fmt3 — fails on tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT TO_CHAR(1234.5678,'9G999D99'),TO_CHAR(-5,'S9') FROM DUAL

-- CASE[open]: ora-for-update-nowait — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT

-- CASE[open]: ora-forupdate-wait — fails on mysql, postgresql. syntax error at or near "WAIT"
CREATE TABLE t (id NUMBER); CREATE INDEX ix ON t (id);
SELECT id FROM t WHERE id = 1 FOR UPDATE OF id WAIT 5

-- CASE[open]: ora-frac-seconds — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT TO_TIMESTAMP('2020-01-01 10:20:30.123456','YYYY-MM-DD HH24:MI:SS.FF6'), EXTRACT(SECOND FROM TIMESTAMP '2020-01-01 10:20:30.123456') FROM DUAL

-- CASE[open]: ora-from-tz — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL

-- CASE[open]: ora-functional-index — fails on mysql, postgresql, tsql. (102, b"Incorrect syntax near '*'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
CREATE TABLE t (a NUMBER); CREATE INDEX ix ON t (a * 2)

-- CASE[open]: ora-gen-expr — fails on mysql. (1075, 'Incorrect table definition; there can be only one auto column and it must be defin
CREATE TABLE t (a NUMBER, b NUMBER, hyp NUMBER GENERATED ALWAYS AS (SQRT(a*a+b*b)))

-- CASE[open]: ora-grouping-id — fails on mysql, postgresql, tsql. (8120, b"Column 'uq_dt.deptno' is invalid in the select list because it is not contained i
SELECT deptno,job,SUM(sal),GROUPING(deptno),GROUPING_ID(deptno,job) FROM (SELECT 10 deptno,'X' job,100 sal FROM DUAL) GROUP BY ROLLUP(deptno,job)

-- CASE[open]: ora-grouping-sets — fails on mysql, postgresql, tsql. (8120, b"Column 'uq_dt.deptno' is invalid in the select list because it is not contained i
SELECT deptno,job,SUM(sal) FROM (SELECT 10 deptno,'X' job,100 sal FROM DUAL) GROUP BY GROUPING SETS ((deptno),(job),())

-- CASE[open]: ora-hash-all — fails on mysql, postgresql, tsql. (195, b"'STANDARD_HASH' is not a recognized built-in function name.DB-Lib error message 20
SELECT STANDARD_HASH('abc', 'SHA256'), ORA_HASH('abc', 100) FROM DUAL

-- CASE[open]: ora-hint-comment — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT /*+ FULL(t) */ 1 AS r FROM DUAL t

-- CASE[open]: ora-identity-opts — fails on mysql. (1075, 'Incorrect table definition; there can be only one auto column and it must be defin
CREATE TABLE t (a NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 10 MAXVALUE 9999 CYCLE))

-- CASE[open]: ora-implicit-arith — fails on mysql, postgresql. FUNC-DIFF: source=(('2', '20', '2'),) target=(('11', '20', '2'),)
SELECT '1'+1, '10'*2, TO_NUMBER('1')+1 FROM DUAL

-- CASE[open]: ora-initcap — fails on mysql, postgresql, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r FROM DUAL

-- CASE[open]: ora-insert-append — fails on postgresql. validator-crash: sending query failed: another command is already in progress
CREATE TABLE t (a NUMBER); INSERT /*+ APPEND */ INTO t SELECT 1 FROM DUAL

-- CASE[open]: ora-instr-case — fails on mysql, tsql. FUNC-DIFF: source=(('2',),) target=(('1',),)
SELECT INSTR('aAaA', 'A') AS r FROM DUAL

-- CASE[open]: ora-instr-edge — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('3', '4', '4'),) target=(('3', '3', '3'),)
SELECT INSTR('hello','l'), INSTR('hello','l',1,2), INSTR('hello','l',-1) FROM DUAL

-- CASE[open]: ora-instr-empty — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('0',),)
SELECT INSTR('abc', '') AS r FROM DUAL

-- CASE[open]: ora-interval-out — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTOYMINTERVAL(14,'MONTH'), NUMTODSINTERVAL(90000,'SECOND') FROM DUAL

-- CASE[open]: ora-interval-tochar — fails on postgresql. FUNC-DIFF: source=(('+02 03:04:05.000000',),) target=(('2 days 03:04:05',),)
SELECT TO_CHAR(INTERVAL '2 3:04:05.000' DAY TO SECOND) AS r FROM DUAL

-- CASE[open]: ora-json-value — fails on postgresql. SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'"] lost after oracle->tsql->oracle
SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL

-- CASE[open]: ora-json-x — fails on mysql, postgresql. SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'", '\'{"a":[1]}\'', "'$.a'"] lost after
SELECT JSON_VALUE('{"a":1}','$.a'),JSON_QUERY('{"a":[1]}','$.a') FROM DUAL

-- CASE[open]: ora-json-xml-agg — fails on mysql, postgresql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT JSON_ARRAYAGG(x), XMLAGG(XMLELEMENT("i",x)) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL) t

-- CASE[open]: ora-last-day — fails on postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY(SYSDATE) AS r FROM DUAL

-- CASE[open]: ora-lastday-leap — fails on mysql. FUNC-DIFF: source=(('2020-02-29 00:00:00',),) target=(('2020-02-29',),)
SELECT LAST_DAY(DATE '2020-02-01') AS r FROM DUAL

-- CASE[open]: ora-length-trailing — fails on tsql. FUNC-DIFF: source=(('6',),) target=(('3',),)
SELECT LENGTH('abc   ') AS r FROM DUAL

-- CASE[open]: ora-listagg — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x,',') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL)

-- CASE[open]: ora-listagg-over — fails on mysql, postgresql, tsql. (4113, b"The function 'STRING_AGG' is not a valid windowing function, and cannot be used w
SELECT deptno, LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) OVER (PARTITION BY deptno) FROM (SELECT 1 deptno, 2 x FROM DUAL)

-- CASE[open]: ora-listagg-overflow — fails on postgresql. SILENT: source literal(s) ["'...'"] absent from valid output, no warning
SELECT LISTAGG(x,',' ON OVERFLOW TRUNCATE '...') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x FROM DUAL) t

-- CASE[open]: ora-lnnvl — fails on mysql, postgresql, tsql. (102, b"Incorrect syntax near '='.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT LNNVL(1 = 2) AS r FROM DUAL WHERE LNNVL(1 = 2)

-- CASE[open]: ora-lob-length — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT DBMS_LOB.GETLENGTH(TO_CLOB('hello')) AS r FROM DUAL

-- CASE[open]: ora-logexp — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LN
SELECT LOG(2, 8), LN(2.718), EXP(1) FROM DUAL

-- CASE[open]: ora-lpad-multichar — fails on tsql. FUNC-DIFF: source=(('xyxab',),) target=(('yxyab',),)
SELECT LPAD('ab', 5, 'xy') AS r FROM DUAL

-- CASE[open]: ora-lpad-tochar — fails on tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT LPAD(TO_CHAR(5,'FMB'), 8, '0') FROM DUAL

-- CASE[open]: ora-ltrim-set — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT LTRIM('xxabc', 'x') AS r FROM DUAL

-- CASE[open]: ora-median-mode — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ME
SELECT MEDIAN(x), STATS_MODE(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 1 FROM DUAL UNION ALL SELECT 2 FROM DUAL)

-- CASE[open]: ora-misc-num — fails on mysql, postgresql, tsql. (189, b'The rand function requires 0 to 1 arguments.DB-Lib error message 20018, severity 1
SELECT DBMS_RANDOM.VALUE(1,100),BITAND(12,10),WIDTH_BUCKET(5,0,10,5),ORA_HASH('x') FROM DUAL

-- CASE[open]: ora-month-name — fails on mysql. FUNC-DIFF: source=(('June',),) target=(('Month',),)
SELECT TO_CHAR(DATE '2020-06-01', 'Month') AS r FROM DUAL

-- CASE[open]: ora-months-between — fails on mysql, postgresql. operator does not exist: timestamp with time zone - integer
SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL

-- CASE[open]: ora-months-between-val — fails on tsql. FUNC-DIFF: source=(('1.83871',),) target=(('2',),)
SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL

-- CASE[open]: ora-multiset-table — fails on postgresql, tsql. (156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:
SELECT COLUMN_VALUE FROM TABLE(CAST(MULTISET(SELECT LEVEL FROM DUAL CONNECT BY LEVEL<=3) AS SYS.ODCINUMBERLIST))

-- CASE[open]: ora-nanvl — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NANVL(0/1, 0) AS r FROM DUAL

-- CASE[open]: ora-nchr-unistr — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NC
SELECT NCHR(233), UNISTR('\00e9') FROM DUAL

-- CASE[open]: ora-next-day — fails on mysql, postgresql, tsql. (195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL

-- CASE[open]: ora-nls-case — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NL
SELECT NLS_INITCAP('word'), NLS_UPPER('word'), NLS_LOWER('WORD') FROM DUAL

-- CASE[open]: ora-nlssort — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NL
SELECT NLSSORT('abc', 'NLS_SORT=BINARY_CI') AS r FROM DUAL

-- CASE[open]: ora-now-fns — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT SYSDATE, CURRENT_DATE, SYSTIMESTAMP, LOCALTIMESTAMP FROM DUAL

-- CASE[open]: ora-now-variants — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT SYSDATE, SYSTIMESTAMP, CURRENT_TIMESTAMP, CURRENT_DATE, LOCALTIMESTAMP FROM DUAL

-- CASE[open]: ora-num-concat — fails on tsql. FUNC-DIFF: source=(('23',),) target=(('5',),)
SELECT 2 || 3 AS r FROM DUAL

-- CASE[open]: ora-num-to-str — fails on mysql, postgresql. FUNC-DIFF: source=(('n=5', 'x=5.5', 'd=.333333333333333333333333333333333333333', '5.5'),)
SELECT 'n='||5, 'x='||5.50, 'd='||(1.0/3), TO_CHAR(5.50) FROM DUAL

-- CASE[open]: ora-numfmt-lead — fails on mysql. FUNC-DIFF: source=(('0.5',),) target=(('0',),)
SELECT TO_CHAR(0.5, '0.00') AS r FROM DUAL

-- CASE[open]: ora-numfmt-sign — fails on mysql. FUNC-DIFF: source=(('-42',),) target=(('NULL',),)
SELECT TO_CHAR(-42, 'S999') AS r FROM DUAL

-- CASE[open]: ora-numfmt-spec — fails on tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT TO_CHAR(1234.5,'L9G999D99MI'),TO_CHAR(0.75,'999PR'),TO_CHAR(255,'0XX') FROM DUAL

-- CASE[open]: ora-numfmt-thousands — fails on mysql. FUNC-DIFF: source=(('1,234,567.89',),) target=(('NULL',),)
SELECT TO_CHAR(1234567.891, '9,999,999.99') AS r FROM DUAL

-- CASE[open]: ora-numtodsinterval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL

-- CASE[open]: ora-numtointerval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(1.5,'DAY'), NUMTOYMINTERVAL(18,'MONTH') FROM DUAL

-- CASE[open]: ora-ora-hash — fails on mysql, postgresql, tsql. (195, b"'ORA_HASH' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT ORA_HASH('abc') AS r FROM DUAL

-- CASE[open]: ora-order-nulls-default — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))
SELECT x FROM (SELECT 3 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL) ORDER BY x

-- CASE[open]: ora-percentile — fails on postgresql. function median(integer) does not exist
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x),PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY x),MEDIAN(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 3 FROM DUAL)

-- CASE[open]: ora-pk-using-index — fails on mysql, postgresql, tsql. (1018, b"Incorrect syntax near 'INDEX'. If this is intended as a part of a table hint, A W
CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)

-- CASE[open]: ora-rand — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "DBMS_RANDOM" or the user-defined function or aggregate
SELECT DBMS_RANDOM.VALUE, DBMS_RANDOM.STRING('U', 5) FROM DUAL

-- CASE[open]: ora-ratio-to-report — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(x) OVER () FROM (SELECT 1 x FROM DUAL)

-- CASE[open]: ora-ratio2 — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(1) OVER () FROM DUAL

-- CASE[open]: ora-rawtohex — fails on mysql, postgresql, tsql. (195, b"'RAWTOHEX' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT RAWTOHEX('AB'), HEXTORAW('4142') FROM DUAL

-- CASE[open]: ora-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/

-- CASE[open]: ora-regex-suite — fails on mysql. (1305, 'FUNCTION unique_val_8dd1b20b3f30.REGEXP_COUNT does not exist')
SELECT REGEXP_REPLACE('abc123','[0-9]+','X'),REGEXP_SUBSTR('abc123','[0-9]+'),REGEXP_INSTR('abc123','[0-9]'),REGEXP_COUNT('a1b2','[0-9]') FROM DUAL

-- CASE[open]: ora-regexp-cnt — fails on mysql. (1305, 'FUNCTION unique_val_015f5453adcc.REGEXP_COUNT does not exist')
SELECT REGEXP_COUNT('a1b2c3','[0-9]'),REGEXP_INSTR('a1b2','[0-9]',1,2) FROM DUAL

-- CASE[open]: ora-regexp-count — fails on mysql. (1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')
SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL

-- CASE[open]: ora-regexp-group — fails on mysql. (1582, "Incorrect parameter count in the call to native function 'REGEXP_SUBSTR'")
SELECT REGEXP_SUBSTR('a1b2c3', '(\d)', 1, 1, NULL, 1) AS r FROM DUAL

-- CASE[open]: ora-round-date-month — fails on mysql. FUNC-DIFF: source=(('2020-07-01 00:00:00',),) target=(('2020',),)
SELECT ROUND(DATE '2020-06-16', 'MONTH') AS r FROM DUAL

-- CASE[open]: ora-round-fns — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE
SELECT FLOOR(3.7), CEIL(3.2), ROUND(3.567, 2), TRUNC(3.567, 1), REMAINDER(10,3) FROM DUAL

-- CASE[open]: ora-rtrim-chars — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('a',),) target=(('',),)
SELECT RTRIM('axxx', 'x') AS r FROM DUAL

-- CASE[open]: ora-seq-use — fails on tsql. (4104, b'The multi-part identifier "s.CURRVAL" could not be bound.DB-Lib error message 200
CREATE SEQUENCE s START WITH 1; SELECT s.NEXTVAL,s.CURRVAL FROM DUAL

-- CASE[open]: ora-sequence-options — fails on postgresql, tsql. (102, b"Incorrect syntax near 'NOCYCLE'.DB-Lib error message 20018, severity 15:\nGeneral 
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE ORDER

-- CASE[open]: ora-soundex — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') AS r FROM DUAL

-- CASE[open]: ora-soundex3 — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') FROM DUAL

-- CASE[open]: ora-str-misc — fails on postgresql, tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT SOUNDEX('Robert'),TO_CHAR(1234567.891,'999G999G999D99'),NVL(NULLIF('a','a'),'x') FROM DUAL

-- CASE[open]: ora-substr-edge — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('llo', 'el', 'he'),) target=(('h', 'el', 'h'),)
SELECT SUBSTR('hello',-3), SUBSTR('hello',2,2), SUBSTR('hello',0,2) FROM DUAL

-- CASE[open]: ora-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('de',),) target=(('',),)
SELECT SUBSTR('abcdef', -3, 2) AS r FROM DUAL

-- CASE[open]: ora-sys-extract-utc — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SY
SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) AS r FROM DUAL

-- CASE[open]: ora-sys-fns — fails on mysql, postgresql, tsql. (195, b"'SYS_CONTEXT' is not a recognized built-in function name.DB-Lib error message 2001
SELECT SYS_GUID(), SYS_CONTEXT('USERENV','SID'), USERENV('LANGUAGE') FROM DUAL

-- CASE[open]: ora-table-collection — fails on postgresql, tsql. (156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:
SELECT * FROM TABLE(SYS.ODCINUMBERLIST(1,2,3))

-- CASE[open]: ora-table-fn2 — fails on postgresql, tsql. (156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:
SELECT t.COLUMN_VALUE FROM TABLE(SYS.ODCINUMBERLIST(1,2,3)) t

-- CASE[open]: ora-table-varchar-list — fails on postgresql, tsql. (156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:
SELECT COLUMN_VALUE FROM TABLE(SYS.ODCIVARCHAR2LIST('a','b','c'))

-- CASE[open]: ora-to-char-day — fails on mysql. FUNC-DIFF: source=(('SUNDAY',),) target=(('Sunday',),)
SELECT TO_CHAR(DATE '2020-06-14', 'DAY') AS r FROM DUAL

-- CASE[open]: ora-to-number-sci — fails on tsql. (8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit
SELECT TO_NUMBER('1.234E2') AS r FROM DUAL

-- CASE[open]: ora-to-timestamp — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT TO_TIMESTAMP('2020-01-01 10:00:00.123', 'YYYY-MM-DD HH24:MI:SS.FF') AS r FROM DUAL

-- CASE[open]: ora-tochar-iso — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT TO_CHAR(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r FROM DUAL

-- CASE[open]: ora-tochar-long — fails on postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT TO_CHAR(DATE '2020-06-15', 'Day, Month DD, YYYY') AS r FROM DUAL

-- CASE[open]: ora-tochar-neg — fails on mysql. FUNC-DIFF: source=(('-1234.5',),) target=(('NULL',),)
SELECT TO_CHAR(-1234.5, '9999.99') AS r FROM DUAL

-- CASE[open]: ora-todate2 — fails on mysql. (1305, 'FUNCTION unique_val_9fa2bcf8c36d.STR_TO_TIME does not exist')
SELECT TO_DATE('15-JUN-20','DD-MON-YY'),TO_TIMESTAMP('2020-06-15 10:30:45.123','YYYY-MM-DD HH24:MI:SS.FF3') FROM DUAL

-- CASE[open]: ora-tonumber2 — fails on mysql, tsql. (195, b"'TO_NUMBER' is not a recognized built-in function name.DB-Lib error message 20018,
SELECT CAST('123.45' AS NUMBER), TO_NUMBER('1,234.5','9,999.9'), TO_NUMBER('$5','$9') FROM DUAL

-- CASE[open]: ora-trailing-eq — fails on tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT CASE WHEN 'a ' = 'a' THEN 1 ELSE 0 END AS r FROM DUAL

-- CASE[open]: ora-trailing-space-cmp — fails on tsql. FUNC-DIFF: source=(('0', '0'),) target=(('1', '1'),)
SELECT CASE WHEN 'a'='a ' THEN 1 ELSE 0 END, CASE WHEN 'a'=RPAD('a',2) THEN 1 ELSE 0 END FROM DUAL

-- CASE[open]: ora-translate — fails on mysql. (1305, 'FUNCTION unique_val_6c47c43e12f3.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r FROM DUAL

-- CASE[open]: ora-translate3 — fails on mysql, postgresql, tsql. (174, b'The replace function requires 3 argument(s).DB-Lib error message 20018, severity 1
SELECT TRANSLATE('12345', '123', 'abc'), REPLACE('aaa','a') FROM DUAL

-- CASE[open]: ora-trig — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.AT
SELECT ATAN2(1,1), COSH(1), SINH(1), TANH(1) FROM DUAL

-- CASE[open]: ora-trig-suite — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT ACOS(1),ASIN(0),ATAN(1),COS(0),SIN(0),TAN(0),COSH(0),SINH(0),TANH(0) FROM DUAL

-- CASE[open]: ora-trim-translate — fails on postgresql, tsql. FUNC-DIFF: source=(('7', '7', 'hi', 'XbZ'),) target=(('', '', '', 'XbZ'),)
SELECT TRIM(LEADING '0' FROM '007'), LTRIM('007','0'), RTRIM('hi!!','!'), TRANSLATE('abc','ac','XZ') FROM DUAL

-- CASE[open]: ora-tz-fns — fails on mysql, postgresql, tsql. (155, b"'TIMEZONE_HOUR' is not a recognized datepart option.DB-Lib error message 20018, se
SELECT EXTRACT(TIMEZONE_HOUR FROM SYSTIMESTAMP), TZ_OFFSET('US/Eastern') FROM DUAL

-- CASE[open]: ora-tz-funcs — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT SYSTIMESTAMP, LOCALTIMESTAMP, SESSIONTIMEZONE FROM DUAL

-- CASE[open]: ora-tz-interval — fails on tsql. (102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL 
CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)

-- CASE[open]: ora-unpivot — fails on mysql, postgresql, tsql. (207, b"Invalid column name 'col'.DB-Lib error message 20018, severity 16:\nGeneral SQL Se
SELECT id,col,val FROM (SELECT 1 id,10 a,20 b FROM DUAL) UNPIVOT (val FOR col IN (a,b))

-- CASE[open]: ora-upd-correlated — fails on mysql. (1093, "You can't specify target table 't' for update in FROM clause")
CREATE TABLE t (id NUMBER, n NUMBER);UPDATE t SET n=(SELECT MAX(n) FROM t x WHERE x.id<t.id)

-- CASE[open]: ora-user-context — fails on mysql, postgresql, tsql. (195, b"'SYS_CONTEXT' is not a recognized built-in function name.DB-Lib error message 2001
SELECT USER, SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL

-- CASE[open]: ora-utl-raw — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "UTL_RAW" or the user-defined function or aggregate "UT
SELECT UTL_RAW.CAST_TO_RAW('abc') AS r FROM DUAL

-- CASE[open]: ora-vsize — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.VS
SELECT VSIZE(123) AS r FROM DUAL

-- CASE[open]: ora-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT WIDTH_BUCKET(5, 0, 10, 5) AS r FROM DUAL

-- CASE[open]: ora-window-analytic — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT x,RATIO_TO_REPORT(x) OVER (),NTILE(2) OVER (ORDER BY x),CUME_DIST() OVER (ORDER BY x),PERCENT_RANK() OVER (ORDER BY x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL)

-- CASE[open]: ora-xmlagg — fails on mysql, postgresql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT XMLAGG(XMLELEMENT("e", dummy)) FROM DUAL

-- CASE[open]: ora-xmlelement — fails on mysql, postgresql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT XMLELEMENT("foo", 'bar') AS r FROM DUAL

-- CASE[open]: ora-xmltable — fails on postgresql, tsql. (208, b"Invalid object name 'dbo.X_M_L_TABLE'.DB-Lib error message 20018, severity 16:\nGe
SELECT x.a,x.b FROM XMLTABLE('/r' PASSING XMLTYPE('<r><a>1</a><b>2</b></r>') COLUMNS a INT PATH 'a', b INT PATH 'b') x

-- CASE[open]: ora-zero-divide — fails on postgresql. unrecognized exception condition "zero_divide"
CREATE PROCEDURE p AS v NUMBER; BEGIN v := 1/0; EXCEPTION WHEN ZERO_DIVIDE THEN v := 0; END;
/

-- CASE[open]: ora23-json-object-star — fails on postgresql. function j_s_o_n_object() does not exist
CREATE TABLE t (id NUMBER, n NUMBER); CREATE TABLE s (id NUMBER, n NUMBER);
SELECT JSON_OBJECT(*) FROM t

-- CASE[open]: oracle-drop2-100|START — fails on postgresql, tsql. SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning
CREATE TABLE t (id NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100))

-- CASE[open]: oracle-drop4-COLLATE — fails on mysql, postgresql, tsql. SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning
CREATE TABLE t (a VARCHAR2(10) COLLATE BINARY_CI)

