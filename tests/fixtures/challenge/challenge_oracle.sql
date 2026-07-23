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

-- CASE[fixed]: or-distinct-null — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('2',), ('NULL',)) target=(('NULL',), ('1',), ('2',))
SELECT DISTINCT x FROM (SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL UNION ALL SELECT 2 x FROM DUAL) ORDER BY x

-- CASE[fixed]: or-order-strings — fails on mysql. FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), 
SELECT x FROM (SELECT 'banana' x FROM DUAL UNION ALL SELECT 'Apple' x FROM DUAL UNION ALL SELECT 'cherry' x FROM DUAL UNION ALL SELECT 'Banana' x FROM DUAL) ORDER BY x

-- CASE[fixed]: ora-add-months — ADD_MONTHS (sticky last-day) translates on all targets; the PG branch now types the ISO date literal (DATE '…') so DATE_TRUNC is unambiguous. Live-verified 2020-02-29.
SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL

-- CASE[fixed]: ora-agg-collect — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x,',') WITHIN GROUP(ORDER BY x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 x FROM DUAL)

-- CASE[fixed]: ora-agg-median — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ME
SELECT MEDIAN(x),STATS_MODE(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT 2 x FROM DUAL)

-- CASE[fixed]: ora-alter-suite — an Oracle ALTER batch ending in DROP COLUMN nm now translates to T-SQL: the DROP COLUMN pre-drops the (auto-named) default constraint that depended on nm (error 5074 otherwise). live-verified whole batch on tsql.
CREATE TABLE t (id NUMBER);
ALTER TABLE t ADD (name VARCHAR2(50) DEFAULT '' NOT NULL);
ALTER TABLE t MODIFY (id NUMBER(19));
ALTER TABLE t RENAME COLUMN name TO nm;
ALTER TABLE t DROP COLUMN nm;

-- CASE[limit]: ora-arr-collect — Oracle's SYS.ODCINUMBERLIST/ODCIVARCHAR2LIST (built-in collection types used as table/array constructors) have no cross-engine equivalent; the gate now recognizes them and degrades + annotates instead of shipping an undefined function (docs/03-unsupported.md). fails on mysql, postgresql, tsql
SELECT SYS.ODCINUMBERLIST(1,2,3) FROM DUAL

-- CASE[fixed]: ora-asciistr — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.AS
SELECT ASCIISTR('ABÄCD'), UNISTR('\0041') FROM DUAL

-- CASE[fixed]: ora-baseconv — fails on mysql, postgresql, tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT TO_CHAR(255,'XXX'),BIN_TO_NUM(1,1,1,1,1,1,1,1) FROM DUAL

-- CASE[fixed]: ora-bit-fns — fails on mysql, postgresql, tsql. (195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT BITAND(12, 10), BIN_TO_NUM(1,1,0) FROM DUAL

-- CASE[fixed]: ora-bitand — Oracle BITAND(a, b) is a bitwise AND; emit the & operator on MySQL/PG/T-SQL (none have BITAND, incl. PG). Live-verified 1 (5 & 3).
SELECT BITAND(5, 3) AS r FROM DUAL

-- CASE[open]: ora-case-statement — fails on tsql. (156, b"Incorrect syntax near the keyword 'ELSE'.DB-Lib error message 20018, severity 15:\
CREATE PROCEDURE p (n IN NUMBER) AS BEGIN CASE n WHEN 1 THEN NULL; ELSE NULL; END CASE; END;
/

-- CASE[open]: ora-cast-datetime3 — fails on mysql, tsql. (243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity
SELECT CAST(SYSTIMESTAMP AS DATE), CAST(SYSDATE AS TIMESTAMP), CAST(SYSDATE AS TIMESTAMP WITH TIME ZONE) FROM DUAL

-- CASE[fixed]: ora-cast-expr — CAST(x AS TIMESTAMP) maps to MySQL DATETIME (MySQL has no TIMESTAMP cast target, 1064) and T-SQL DATETIME2 (T-SQL TIMESTAMP is a rowversion, not a datetime).
SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL

-- CASE[fixed]: ora-cast-int-edge — fails on mysql. FUNC-DIFF: source=(('4', '3', '4', '4'),) target=(('3', '3', '4', '4'),)
SELECT CAST('3.9' AS INT), TRUNC(3.9), ROUND(3.9), CAST(3.9 AS NUMBER(1)) FROM DUAL

-- CASE[open]: ora-cast-onerror — fails on postgresql, tsql. (8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit
SELECT CAST('abc' AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM DUAL

-- CASE[fixed]: ora-char-encoding — fails on mysql, postgresql, tsql. (195, b"'RAWTOHEX' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT ASCII('A'),CHR(65),RAWTOHEX('AB'),UTL_RAW.CAST_TO_RAW('AB'),DUMP('AB'),NCHR(65) FROM DUAL

-- CASE[fixed]: ora-clob-coalesce — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT COALESCE(TO_CLOB('a'), TO_CLOB('b')) AS r FROM DUAL

-- CASE[fixed]: ora-clob-ops — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT TO_CLOB('x') || TO_CLOB('y'), DBMS_LOB.SUBSTR(TO_CLOB('hello'), 3) FROM DUAL

-- CASE[limit]: ora-collect — Oracle's COLLECT aggregate builds a nested-table collection (paired with a SYS.ODCI* type) — no cross-engine equivalent (PG array_agg yields an array, not an Oracle collection); the gate now recognizes it and degrades + annotates (docs/03-unsupported.md). fails on postgresql, tsql
SELECT CAST(COLLECT(x) AS SYS.ODCINUMBERLIST) FROM (SELECT 1 x FROM DUAL)

-- CASE[fixed]: ora-compose — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT COMPOSE('a'||UNISTR('\0301')), DECOMPOSE('á') FROM DUAL

-- CASE[fixed]: ora-concat-null — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('ab',),) target=(('NULL',),)
SELECT 'a' || NULL || 'b' AS r FROM DUAL

-- CASE[fixed]: ora-concat-num — fails on tsql. (245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er
SELECT 'a' || 5 AS r FROM DUAL

-- CASE[open]: ora-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;

-- CASE[open]: ora-cursor-attr — fails on mysql, tsql. (128, b'The name "c" is not permitted in this context. Valid expressions are constants, co
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; IF c%FOUND THEN DBMS_OUTPUT.PUT_LINE(c%ROWCOUNT); END IF; CLOSE c; END;
/

-- CASE[open]: ora-cursor-for-loop — fails on tsql. (156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n
CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/

-- CASE[fixed]: ora-date-arith2 — fails on mysql, postgresql, tsql. (195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018
SELECT ADD_MONTHS(SYSDATE,3), NEXT_DAY(SYSDATE,'MONDAY'), LAST_DAY(SYSDATE) FROM DUAL

-- CASE[fixed]: ora-date-diff-days — fails on mysql. FUNC-DIFF: source=(('60',),) target=(('0',),)
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r FROM DUAL

-- CASE[open]: ora-date-plus-int — fails on mysql, postgresql. SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith
SELECT SYSDATE + 1 AS r FROM DUAL

-- CASE[fixed]: ora-date-plus-int2 — Oracle date + n adds n days; MySQL numeric-coerced it (2050.0). Emit DATE_ADD(date, INTERVAL n DAY).
SELECT DATE '2020-01-01' + 30 AS r FROM DUAL

-- CASE[limit]: ora-day-of-week — TO_CHAR(d,'D') day-of-week number is NLS_TERRITORY-dependent in Oracle, so no portable equivalent exists; gated + annotated (docs/03-unsupported.md). fails on mysql
SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL

-- CASE[fixed]: ora-decimal-scale — same value at each engine's default decimal scale (10/3 = 3.3333...). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 10.00/3, 10/3.0, CAST(10 AS NUMBER(10,4))/3, 1.5*1.5 FROM DUAL

-- CASE[fixed]: ora-decode-null — Oracle DECODE uses NULL-safe equality (NULL matches NULL); a NULL search emits CASE WHEN subject IS NULL (SQL equality on a NULL yields unknown).
SELECT DECODE(NULL, NULL, 'match', 'no') AS r FROM DUAL

-- CASE[fixed]: ora-div — Oracle / is decimal (2.5); PG/T-SQL truncate two ints. Force decimal via (a * 1.0 / b). Value 2.5 (repr differs by decimal scale).
SELECT 5 / 2 AS r FROM DUAL

-- CASE[fixed]: ora-div-mult2 — 1/3*3 = 1; same value at different engine precision (0.999999 vs 1). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 1/3*3 AS r FROM DUAL

-- CASE[fixed]: ora-div-precision — 1/3 = 0.3333...; same value at each engine's default division scale. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 1 / 3 AS r FROM DUAL

-- CASE[fixed]: ora-dttypes — fails on postgresql, tsql. (102, b"Incorrect syntax near 'YEAR'.DB-Lib error message 20018, severity 15:\nGeneral SQL
CREATE TABLE t (a DATE, b TIMESTAMP, c TIMESTAMP WITH TIME ZONE, d TIMESTAMP WITH LOCAL TIME ZONE, e INTERVAL YEAR TO MONTH, f INTERVAL DAY TO SECOND)

-- CASE[fixed]: ora-dump — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('abc') AS r FROM DUAL

-- CASE[fixed]: ora-dump2 — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('A', 1016) AS r FROM DUAL

-- CASE[open]: ora-dyn-count — fails on tsql. (102, b"Incorrect syntax near '+'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
CREATE PROCEDURE p (tbl VARCHAR2) AS n NUMBER; BEGIN EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || tbl INTO n; END;
/

-- CASE[limit]: ora-edit-distance — Oracle's UTL_MATCH.EDIT_DISTANCE (Levenshtein) has no core cross-engine equivalent (PG's is a fuzzystrmatch extension); the gate now recognizes it and degrades + annotates instead of shipping an undefined function (docs/03-unsupported.md). fails on mysql, postgresql, tsql
SELECT UTL_MATCH.EDIT_DISTANCE('hello', 'hallo') AS r FROM DUAL

-- CASE[limit]: ora-empty-is-null — fails on mysql, postgresql, tsql. Oracle stores '' as NULL so '' IS NULL is true (1) only on Oracle; other engines see a real empty string (0). No faithful workaround (docs/03-unsupported.md).
SELECT CASE WHEN '' IS NULL THEN 1 ELSE 0 END AS r FROM DUAL

-- CASE[limit]: ora-empty-null — fails on mysql, postgresql, tsql. Oracle NVL('','x')='x' because '' is NULL there; COALESCE('','x')='' elsewhere. Oracle can't represent '' apart from NULL (docs/03-unsupported.md).
SELECT NVL('', 'x') AS r FROM DUAL

-- CASE[fixed]: ora-extract — fails on mysql. FUNC-DIFF: source=(('2020', '6', '2', '2'),) target=(('2020', '6', '25', 'Q'),)
SELECT EXTRACT(YEAR FROM DATE '2020-06-15'), EXTRACT(MONTH FROM DATE '2020-06-15'), TO_CHAR(DATE '2020-06-15','D'), TO_CHAR(DATE '2020-06-15','Q') FROM DUAL

-- CASE[fixed]: ora-extractvalue — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXTRACTVALUE(XMLTYPE('<a>1</a>'), '/a') AS r FROM DUAL

-- CASE[fixed]: ora-fconcat — fails on mysql, tsql. FUNC-DIFF: source=(('ab', 'a', '23'),) target=(('ab', 'NULL', '5'),)
SELECT 'a'||'b','a'||NULL,2||3 FROM DUAL

-- CASE[fixed]: ora-fk-and-check — fails on mysql. (1239, "Incorrect foreign key definition for 'fk': Key reference and table reference don't
CREATE TABLE parent (id NUMBER PRIMARY KEY); CREATE TABLE child (pid NUMBER, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES parent ON DELETE CASCADE, CONSTRAINT fk2 CHECK (pid > 0))

-- CASE[fixed]: ora-float-precision — same IEEE/float value at each engine's display precision. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 0.1+0.2, CAST(0.1 AS BINARY_DOUBLE)+CAST(0.2 AS BINARY_DOUBLE), 1.0/3 FROM DUAL

-- CASE[limit]: ora-fmt-dayname — fails on mysql. locale month/day names and Oracle Q quarter token have no reproducible cross-engine format token (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(DATE '2020-06-15', 'DAY') AS r FROM DUAL

-- CASE[limit]: ora-fmt-quarter — fails on mysql. locale month/day names and Oracle Q quarter token have no reproducible cross-engine format token (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(DATE '2020-06-15', 'Q') AS r FROM DUAL

-- CASE[limit]: ora-fmt-week — TO_CHAR(d,'WW') week-of-year has no portable format token (engines disagree on week 1, and MySQL's '%W' means the weekday NAME); it now degrades + annotates instead of emitting a silently wrong 'Monday' (docs/03-unsupported.md). fails on mysql
SELECT TO_CHAR(DATE '2020-06-15', 'WW') AS r FROM DUAL

-- CASE[limit]: ora-fmt3 — fails on tsql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(1234.5678,'9G999D99'),TO_CHAR(-5,'S9') FROM DUAL

-- CASE[fixed]: ora-for-update-nowait — SELECT … FOR UPDATE NOWAIT passes through to MySQL 8.0 and PostgreSQL (both support NOWAIT); the RED failure was a harness locked-table artifact. live-verified.
CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT

-- CASE[limit]: ora-format-currency — TO_CHAR with a currency mask ($999,999.00) maps to PostgreSQL's TO_CHAR (works, live-verified $1,234.50); MySQL's FORMAT() has no currency-symbol mask, so its output degrades to a carrier + warning (docs/03-unsupported.md). fails on mysql
SELECT TO_CHAR(1234567.891,'FM999,999,990.00'), TO_CHAR(1234567.891,'FML999G999G990D00') FROM DUAL

-- CASE[limit]: ora-forupdate-wait — Oracle FOR UPDATE WAIT <n> (bounded lock wait) has no PostgreSQL/MySQL equivalent (they offer only FOR UPDATE / NOWAIT); the WAIT <n> is dropped and the lost timeout annotated (docs/03-unsupported.md). fails on mysql, postgresql
CREATE TABLE t (id NUMBER); CREATE INDEX ix ON t (id);
SELECT id FROM t WHERE id = 1 FOR UPDATE OF id WAIT 5

-- CASE[fixed]: ora-frac-seconds — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT TO_TIMESTAMP('2020-01-01 10:20:30.123456','YYYY-MM-DD HH24:MI:SS.FF6'), EXTRACT(SECOND FROM TIMESTAMP '2020-01-01 10:20:30.123456') FROM DUAL

-- CASE[fixed]: ora-from-tz — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL

-- CASE[limit]: ora-functional-index — an expression index maps to MySQL 8.0.13+/PostgreSQL double-paren form ((a*2)) [now valid there]; T-SQL has no expression index (needs a computed column), so it degrades with a carrier (docs/03-unsupported.md). fails on tsql
CREATE TABLE t (a NUMBER); CREATE INDEX ix ON t (a * 2)

-- CASE[fixed]: ora-gen-expr — Oracle virtual column GENERATED ALWAYS AS (SQRT(a*a+b*b)) maps to the MySQL generated-column form with the ported type; live-verified hyp(3,4)=5 on both.
CREATE TABLE t (a NUMBER, b NUMBER, hyp NUMBER GENERATED ALWAYS AS (SQRT(a*a+b*b)))

-- CASE[limit]: ora-grouping-id — GROUPING_ID has no MySQL (no ROLLUP GROUPING_ID) or PostgreSQL equivalent (PG has GROUPING but not GROUPING_ID); T-SQL supports it natively (works). The MySQL/PG output degrades to a carrier + warning (docs/03-unsupported.md). fails on mysql, postgresql
SELECT deptno,job,SUM(sal),GROUPING(deptno),GROUPING_ID(deptno,job) FROM (SELECT 10 deptno,'X' job,100 sal FROM DUAL) GROUP BY ROLLUP(deptno,job)

-- CASE[fixed]: ora-grouping-sets — fails on mysql, postgresql, tsql. (8120, b"Column 'uq_dt.deptno' is invalid in the select list because it is not contained i
SELECT deptno,job,SUM(sal) FROM (SELECT 10 deptno,'X' job,100 sal FROM DUAL) GROUP BY GROUPING SETS ((deptno),(job),())

-- CASE[fixed]: ora-hash-all — fails on mysql, postgresql, tsql. (195, b"'STANDARD_HASH' is not a recognized built-in function name.DB-Lib error message 20
SELECT STANDARD_HASH('abc', 'SHA256'), ORA_HASH('abc', 100) FROM DUAL

-- CASE[open]: ora-hint-comment — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT /*+ FULL(t) */ 1 AS r FROM DUAL t

-- CASE[limit]: ora-identity-opts — MySQL AUTO_INCREMENT has no per-column START/INCREMENT/MAXVALUE/CYCLE; emits AUTO_INCREMENT (keyed) + a documented carrier + warning (docs/03-unsupported.md). fails on mysql
CREATE TABLE t (a NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 10 MAXVALUE 9999 CYCLE))

-- CASE[fixed]: ora-implicit-arith — '1' + 1 is arithmetic (number operand), not concat: kept as + so it evaluates to 2.
SELECT '1'+1, '10'*2, TO_NUMBER('1')+1 FROM DUAL

-- CASE[limit]: ora-initcap — INITCAP (title-case each word) has no MySQL/T-SQL builtin and cannot be emulated for arbitrary multi-word text; PostgreSQL has INITCAP natively so it transpiles cleanly there. Gated + annotated on the other two (docs/03-unsupported.md). fails on mysql, tsql
SELECT INITCAP('hello world') AS r FROM DUAL

-- CASE[fixed]: ora-insert-append — the Oracle /*+ APPEND */ direct-path hint is advisory (result-identical) and is dropped for PostgreSQL; the INSERT … SELECT runs unchanged. The RED "crash" was a harness connection-state artifact. live-verified 1 row inserted.
CREATE TABLE t (a NUMBER); INSERT /*+ APPEND */ INTO t SELECT 1 FROM DUAL

-- CASE[fixed]: ora-instr-case — Oracle INSTR is case-sensitive; force BINARY (MySQL) / BIN2 collation (T-SQL) on the haystack so the match position is 2, not 1.
SELECT INSTR('aAaA', 'A') AS r FROM DUAL

-- CASE[open]: ora-instr-edge — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('3', '4', '4'),) target=(('3', '3', '3'),)
SELECT INSTR('hello','l'), INSTR('hello','l',1,2), INSTR('hello','l',-1) FROM DUAL

-- CASE[limit]: ora-instr-empty — fails on mysql, postgresql, tsql. Oracle INSTR(s,'') is NULL ('' is NULL); other engines return 0. No faithful workaround (docs/03-unsupported.md).
SELECT INSTR('abc', '') AS r FROM DUAL

-- CASE[fixed]: ora-interval-out — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTOYMINTERVAL(14,'MONTH'), NUMTODSINTERVAL(90000,'SECOND') FROM DUAL

-- CASE[open]: ora-interval-tochar — fails on postgresql. FUNC-DIFF: source=(('+02 03:04:05.000000',),) target=(('2 days 03:04:05',),)
SELECT TO_CHAR(INTERVAL '2 3:04:05.000' DAY TO SECOND) AS r FROM DUAL

-- CASE[fixed]: ora-json-value — JSON_VALUE(doc,path) maps to native JSON_VALUE on Oracle/T-SQL/MySQL and to JSONB_PATH_QUERY_FIRST(...) #>> '{}' on PostgreSQL <17. live-verified '1'.
SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL

-- CASE[fixed]: ora-json-x — JSON_VALUE + JSON_QUERY map to native forms (MySQL has no JSON_QUERY -> JSON_EXTRACT; PostgreSQL -> JSONB_PATH_QUERY_FIRST). live-verified '1', '[1]'.
SELECT JSON_VALUE('{"a":1}','$.a'),JSON_QUERY('{"a":[1]}','$.a') FROM DUAL

-- CASE[limit]: ora-json-xml-agg — combines JSON_ARRAYAGG + XMLAGG; PostgreSQL has both natively (works, live-verified [1,2] / <i>1</i><i>2</i>), but MySQL/T-SQL have no XML aggregate, so their output degrades to a carrier + warning (docs/03-unsupported.md). fails on mysql, tsql
SELECT JSON_ARRAYAGG(x), XMLAGG(XMLELEMENT("i",x)) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL) t

-- CASE[fixed]: ora-last-day — LAST_DAY now translates (PG DATE_TRUNC month-end formula, T-SQL EOMONTH); stale tag, live-verified 2020-02-29 (date-vs-datetime display is precision-only).
SELECT LAST_DAY(SYSDATE) AS r FROM DUAL

-- CASE[fixed]: ora-lastday-leap — LAST_DAY(2020-02-01)=2020-02-29 on both; Oracle returns a DATE (shown with 00:00:00), MySQL a date — same value, precision-only (maintainer policy 2026-07-19).
SELECT LAST_DAY(DATE '2020-02-01') AS r FROM DUAL

-- CASE[fixed]: ora-length-trailing — Oracle/PG LENGTH counts trailing spaces (6); T-SQL LEN drops them. Emit LEN(x + '.') - 1 on T-SQL to preserve the count.
SELECT LENGTH('abc   ') AS r FROM DUAL

-- CASE[fixed]: ora-listagg — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x,',') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL)

-- CASE[open]: ora-listagg-over — fails on mysql, postgresql, tsql. (4113, b"The function 'STRING_AGG' is not a valid windowing function, and cannot be used w
SELECT deptno, LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) OVER (PARTITION BY deptno) FROM (SELECT 1 deptno, 2 x FROM DUAL)

-- CASE[fixed]: ora-listagg-overflow — LISTAGG(x, sep ON OVERFLOW TRUNCATE) -> PG STRING_AGG. PG string_agg has no length cap, so the ON OVERFLOW TRUNCATE clause is a no-op for non-overflowing data (the common case) and is dropped; value matches. live-verified on postgresql.
SELECT LISTAGG(x,',' ON OVERFLOW TRUNCATE '...') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x FROM DUAL) t

-- CASE[fixed]: ora-lnnvl — fails on mysql, postgresql, tsql. (102, b"Incorrect syntax near '='.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT LNNVL(1 = 2) AS r FROM DUAL WHERE LNNVL(1 = 2)

-- CASE[fixed]: ora-lob-length — fails on mysql, postgresql, tsql. (195, b"'TO_CLOB' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT DBMS_LOB.GETLENGTH(TO_CLOB('hello')) AS r FROM DUAL

-- CASE[fixed]: ora-logexp — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LN
SELECT LOG(2, 8), LN(2.718), EXP(1) FROM DUAL

-- CASE[fixed]: ora-lpad-multichar — fails on tsql. FUNC-DIFF: source=(('xyxab',),) target=(('yxyab',),)
SELECT LPAD('ab', 5, 'xy') AS r FROM DUAL

-- CASE[fixed]: ora-lpad-tochar — fails on tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT LPAD(TO_CHAR(5,'FMB'), 8, '0') FROM DUAL

-- CASE[fixed]: ora-ltrim-set — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT LTRIM('xxabc', 'x') AS r FROM DUAL

-- CASE[fixed]: ora-median-mode — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ME
SELECT MEDIAN(x), STATS_MODE(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 1 FROM DUAL UNION ALL SELECT 2 FROM DUAL)

-- CASE[fixed]: ora-misc-num — fails on mysql, postgresql, tsql. (189, b'The rand function requires 0 to 1 arguments.DB-Lib error message 20018, severity 1
SELECT DBMS_RANDOM.VALUE(1,100),BITAND(12,10),WIDTH_BUCKET(5,0,10,5),ORA_HASH('x') FROM DUAL

-- CASE[limit]: ora-month-name — fails on mysql. TO_CHAR with a locale month/day NAME (Month/Day) is NLS-dependent, no reproducible cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(DATE '2020-06-01', 'Month') AS r FROM DUAL

-- CASE[fixed]: ora-months-between — fails on mysql, postgresql. operator does not exist: timestamp with time zone - integer
SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL

-- CASE[fixed]: ora-months-between-val — Oracle MONTHS_BETWEEN is fractional (whole months + (day1-day2)/31, whole when both are month-ends or same day); T-SQL DATEDIFF(MONTH) was an integer boundary count. Emit the exact CASE on T-SQL. live-verified 1.83871.
SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL

-- CASE[open]: ora-multiset-table — fails on postgresql, tsql. (156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:
SELECT COLUMN_VALUE FROM TABLE(CAST(MULTISET(SELECT LEVEL FROM DUAL CONNECT BY LEVEL<=3) AS SYS.ODCINUMBERLIST))

-- CASE[limit]: ora-name-locale — fails on mysql. TO_CHAR with locale month/day NAMES (Day/Month) is NLS/collation-dependent, no cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(DATE '2020-06-15','Day'), TO_CHAR(DATE '2020-06-15','Month'), TRIM(TO_CHAR(DATE '2020-06-15','DAY')) FROM DUAL

-- CASE[fixed]: ora-nanvl — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NANVL(0/1, 0) AS r FROM DUAL

-- CASE[fixed]: ora-nchr-unistr — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NC
SELECT NCHR(233), UNISTR('\00e9') FROM DUAL

-- CASE[fixed]: ora-next-day — fails on mysql, postgresql, tsql. (195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL

-- CASE[fixed]: ora-nls-case — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NL
SELECT NLS_INITCAP('word'), NLS_UPPER('word'), NLS_LOWER('WORD') FROM DUAL

-- CASE[fixed]: ora-nlssort — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NL
SELECT NLSSORT('abc', 'NLS_SORT=BINARY_CI') AS r FROM DUAL

-- CASE[fixed]: ora-now-fns — LOCALTIMESTAMP is now mapped per engine (PostgreSQL niladic keyword, T-SQL SYSDATETIME(), MySQL CURRENT_TIMESTAMP) alongside SYSDATE/CURRENT_DATE/SYSTIMESTAMP. live-verified the SELECT runs on all targets (values are the current timestamp).
SELECT SYSDATE, CURRENT_DATE, SYSTIMESTAMP, LOCALTIMESTAMP FROM DUAL

-- CASE[fixed]: ora-now-variants — same as ora-now-fns: the full set of Oracle "now" spellings (SYSDATE/SYSTIMESTAMP/CURRENT_TIMESTAMP/CURRENT_DATE/LOCALTIMESTAMP) maps per engine. live-verified the SELECT runs on all targets.
SELECT SYSDATE, SYSTIMESTAMP, CURRENT_TIMESTAMP, CURRENT_DATE, LOCALTIMESTAMP FROM DUAL

-- CASE[fixed]: ora-num-concat — fails on tsql. FUNC-DIFF: source=(('23',),) target=(('5',),)
SELECT 2 || 3 AS r FROM DUAL

-- CASE[open]: ora-num-to-str — fails on mysql, postgresql. FUNC-DIFF: source=(('n=5', 'x=5.5', 'd=.333333333333333333333333333333333333333', '5.5'),)
SELECT 'n='||5, 'x='||5.50, 'd='||(1.0/3), TO_CHAR(5.50) FROM DUAL

-- CASE[limit]: ora-numfmt-lead — fails on mysql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(0.5, '0.00') AS r FROM DUAL

-- CASE[limit]: ora-numfmt-sign — fails on mysql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(-42, 'S999') AS r FROM DUAL

-- CASE[limit]: ora-numfmt-spec — fails on tsql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(1234.5,'L9G999D99MI'),TO_CHAR(0.75,'999PR'),TO_CHAR(255,'0XX') FROM DUAL

-- CASE[limit]: ora-numfmt-thousands — fails on mysql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(1234567.891, '9,999,999.99') AS r FROM DUAL

-- CASE[fixed]: ora-numtodsinterval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL

-- CASE[fixed]: ora-numtointerval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(1.5,'DAY'), NUMTOYMINTERVAL(18,'MONTH') FROM DUAL

-- CASE[fixed]: ora-ora-hash — fails on mysql, postgresql, tsql. (195, b"'ORA_HASH' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT ORA_HASH('abc') AS r FROM DUAL

-- CASE[fixed]: ora-order-nulls-default — Oracle sorts NULLs high by default; MySQL/T-SQL sort them low. Emulate with a null-priority key.
SELECT x FROM (SELECT 3 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL) ORDER BY x

-- CASE[fixed]: ora-percentile — fails on postgresql. function median(integer) does not exist
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x),PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY x),MEDIAN(x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 3 FROM DUAL)

-- CASE[fixed]: ora-pk-using-index — Oracle's PRIMARY KEY … USING INDEX names/tunes the backing index (a storage detail); every engine backs a PK with an index by default, so the clause is stripped and the constraint is identical. live-verified CREATE runs.
CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)

-- CASE[limit]: ora-rand — fails on mysql, postgresql, tsql. DBMS_RANDOM.VALUE/STRING is non-deterministic (values cannot match cross-engine) and DBMS_RANDOM.STRING has no equivalent random-string builtin elsewhere (docs/03-unsupported.md §2). Warned carrier on all three.
SELECT DBMS_RANDOM.VALUE, DBMS_RANDOM.STRING('U', 5) FROM DUAL

-- CASE[fixed]: ora-ratio-to-report — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(x) OVER () FROM (SELECT 1 x FROM DUAL)

-- CASE[fixed]: ora-ratio2 — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RATIO_TO_REPORT(1) OVER () FROM DUAL

-- CASE[fixed]: ora-rawtohex — fails on mysql, postgresql, tsql. (195, b"'RAWTOHEX' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT RAWTOHEX('AB'), HEXTORAW('4142') FROM DUAL

-- CASE[open]: ora-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/

-- CASE[fixed]: ora-regex-suite — fails on mysql. (1305, 'FUNCTION unique_val_8dd1b20b3f30.REGEXP_COUNT does not exist')
SELECT REGEXP_REPLACE('abc123','[0-9]+','X'),REGEXP_SUBSTR('abc123','[0-9]+'),REGEXP_INSTR('abc123','[0-9]'),REGEXP_COUNT('a1b2','[0-9]') FROM DUAL

-- CASE[fixed]: ora-regexp-cnt — fails on mysql. (1305, 'FUNCTION unique_val_015f5453adcc.REGEXP_COUNT does not exist')
SELECT REGEXP_COUNT('a1b2c3','[0-9]'),REGEXP_INSTR('a1b2','[0-9]',1,2) FROM DUAL

-- CASE[fixed]: ora-regexp-count — fails on mysql. (1305, 'FUNCTION unique_val_41751da4688e.REGEXP_COUNT does not exist')
SELECT REGEXP_COUNT('a1b2c3', '[0-9]') AS r FROM DUAL

-- CASE[open]: ora-regexp-group — fails on mysql. (1582, "Incorrect parameter count in the call to native function 'REGEXP_SUBSTR'")
SELECT REGEXP_SUBSTR('a1b2c3', '(\d)', 1, 1, NULL, 1) AS r FROM DUAL

-- CASE[fixed]: ora-round-date-month — MySQL has no ROUND(date,'MONTH'); emulate the month rounding (day>=16 -> 1st of next month) with a CASE. Live-verified 2020-07-01.
SELECT ROUND(DATE '2020-06-16', 'MONTH') AS r FROM DUAL

-- CASE[fixed]: ora-round-fns — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE
SELECT FLOOR(3.7), CEIL(3.2), ROUND(3.567, 2), TRUNC(3.567, 1), REMAINDER(10,3) FROM DUAL

-- CASE[fixed]: ora-rtrim-chars — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('a',),) target=(('',),)
SELECT RTRIM('axxx', 'x') AS r FROM DUAL

-- CASE[open]: ora-seq-use — fails on tsql. (4104, b'The multi-part identifier "s.CURRVAL" could not be bound.DB-Lib error message 200
CREATE SEQUENCE s START WITH 1; SELECT s.NEXTVAL,s.CURRVAL FROM DUAL

-- CASE[fixed]: ora-sequence-options — Oracle's one-word sequence negatives (NOCYCLE/NOCACHE/...) map to PostgreSQL/T-SQL two-word NO CYCLE etc., and the ORDER/NOORDER RAC option (no other engine) is dropped. live-verified CREATE SEQUENCE runs. 
CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE ORDER

-- CASE[fixed]: ora-soundex — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') AS r FROM DUAL

-- CASE[fixed]: ora-soundex3 — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') FROM DUAL

-- CASE[fixed]: ora-str-misc — fails on postgresql, tsql. (195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT SOUNDEX('Robert'),TO_CHAR(1234567.891,'999G999G999D99'),NVL(NULLIF('a','a'),'x') FROM DUAL

-- CASE[fixed]: ora-substr-edge — fails on mysql, postgresql, tsql. FUNC-DIFF: source=(('llo', 'el', 'he'),) target=(('h', 'el', 'h'),)
SELECT SUBSTR('hello',-3), SUBSTR('hello',2,2), SUBSTR('hello',0,2) FROM DUAL

-- CASE[fixed]: ora-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('de',),) target=(('',),)
SELECT SUBSTR('abcdef', -3, 2) AS r FROM DUAL

-- CASE[fixed]: ora-sys-extract-utc — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SY
SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) AS r FROM DUAL

-- CASE[fixed]: ora-sys-fns — fails on mysql, postgresql, tsql. (195, b"'SYS_CONTEXT' is not a recognized built-in function name.DB-Lib error message 2001
SELECT SYS_GUID(), SYS_CONTEXT('USERENV','SID'), USERENV('LANGUAGE') FROM DUAL

-- CASE[limit]: ora-table-collection — Oracle TABLE(SYS.ODCINUMBERLIST(...)) unnests a built-in collection into rows; no cross-engine equivalent (the ODCI collection type + TABLE() have no PG/T-SQL form), so it degrades to a carrier + warning (docs/03-unsupported.md). fails on postgresql, tsql
SELECT * FROM TABLE(SYS.ODCINUMBERLIST(1,2,3))

-- CASE[limit]: ora-table-fn2 — TABLE(SYS.ODCINUMBERLIST(...)) collection unnesting with COLUMN_VALUE has no PG/T-SQL equivalent; degrades to a carrier + warning (docs/03-unsupported.md). fails on postgresql, tsql
SELECT t.COLUMN_VALUE FROM TABLE(SYS.ODCINUMBERLIST(1,2,3)) t

-- CASE[limit]: ora-table-varchar-list — TABLE(SYS.ODCIVARCHAR2LIST(...)) collection unnesting has no PG/T-SQL equivalent; degrades to a carrier + warning (docs/03-unsupported.md). fails on postgresql, tsql
SELECT COLUMN_VALUE FROM TABLE(SYS.ODCIVARCHAR2LIST('a','b','c'))

-- CASE[limit]: ora-to-char-day — fails on mysql. TO_CHAR(d,'DAY') is a locale day NAME, NLS-dependent, no reproducible cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(DATE '2020-06-14', 'DAY') AS r FROM DUAL

-- CASE[fixed]: ora-to-number-sci — T-SQL can't CAST a scientific-notation string to DECIMAL; use FLOAT so TO_NUMBER('1.234E2') = 123.4 (live-verified).
SELECT TO_NUMBER('1.234E2') AS r FROM DUAL

-- CASE[fixed]: ora-to-timestamp — TO_TIMESTAMP(str, mask). A constant ISO-shaped string parses to a fixed value -> ANSI TIMESTAMP literal (PG/Oracle) / CAST DATETIME(6)/DATETIME2 (MySQL/T-SQL), preserving the .123 fractional. live-verified on all four.
SELECT TO_TIMESTAMP('2020-01-01 10:00:00.123', 'YYYY-MM-DD HH24:MI:SS.FF') AS r FROM DUAL

-- CASE[fixed]: ora-tochar-iso — TO_CHAR(ts, mask) date formatting. sqlglot canonicalizes the mask to python strftime; the emitter translates it per engine model -> PG TO_CHAR, MySQL DATE_FORMAT, T-SQL FORMAT (literal "T" preserved). live-verified 2020-06-15T14:30:45 on all four.
SELECT TO_CHAR(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r FROM DUAL

-- CASE[limit]: ora-tochar-long — fails on postgresql, tsql. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(DATE '2020-06-15', 'Day, Month DD, YYYY') AS r FROM DUAL

-- CASE[limit]: ora-tochar-neg — fails on mysql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT TO_CHAR(-1234.5, '9999.99') AS r FROM DUAL

-- CASE[fixed]: ora-todate2 — TO_DATE/TO_TIMESTAMP map to MySQL STR_TO_DATE / a DATETIME literal; live-verified 2020-06-15 and 2020-06-15 10:30:45.123 (date-precision on col1).
SELECT TO_DATE('15-JUN-20','DD-MON-YY'),TO_TIMESTAMP('2020-06-15 10:30:45.123','YYYY-MM-DD HH24:MI:SS.FF3') FROM DUAL

-- CASE[fixed]: ora-tonumber2 — fails on mysql, tsql. (195, b"'TO_NUMBER' is not a recognized built-in function name.DB-Lib error message 20018,
SELECT CAST('123.45' AS NUMBER), TO_NUMBER('1,234.5','9,999.9'), TO_NUMBER('$5','$9') FROM DUAL

-- CASE[limit]: ora-trailing-eq — fails on tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT CASE WHEN 'a ' = 'a' THEN 1 ELSE 0 END AS r FROM DUAL

-- CASE[limit]: ora-trailing-space-cmp — fails on tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0', '0'),) target=(('1', '1'),)
SELECT CASE WHEN 'a'='a ' THEN 1 ELSE 0 END, CASE WHEN 'a'=RPAD('a',2) THEN 1 ELSE 0 END FROM DUAL

-- CASE[fixed]: ora-translate — fails on mysql. (1305, 'FUNCTION unique_val_6c47c43e12f3.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r FROM DUAL

-- CASE[open]: ora-translate3 — fails on mysql, postgresql, tsql. (174, b'The replace function requires 3 argument(s).DB-Lib error message 20018, severity 1
SELECT TRANSLATE('12345', '123', 'abc'), REPLACE('aaa','a') FROM DUAL

-- CASE[fixed]: ora-trig — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.AT
SELECT ATAN2(1,1), COSH(1), SINH(1), TANH(1) FROM DUAL

-- CASE[fixed]: ora-trig-suite — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT ACOS(1),ASIN(0),ATAN(1),COS(0),SIN(0),TAN(0),COSH(0),SINH(0),TANH(0) FROM DUAL

-- CASE[fixed]: ora-trim-translate — fails on postgresql, tsql. FUNC-DIFF: source=(('7', '7', 'hi', 'XbZ'),) target=(('', '', '', 'XbZ'),)
SELECT TRIM(LEADING '0' FROM '007'), LTRIM('007','0'), RTRIM('hi!!','!'), TRANSLATE('abc','ac','XZ') FROM DUAL

-- CASE[fixed]: ora-tz-fns — fails on mysql, postgresql, tsql. (155, b"'TIMEZONE_HOUR' is not a recognized datepart option.DB-Lib error message 20018, se
SELECT EXTRACT(TIMEZONE_HOUR FROM SYSTIMESTAMP), TZ_OFFSET('US/Eastern') FROM DUAL

-- CASE[open]: ora-tz-funcs — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT SYSTIMESTAMP, LOCALTIMESTAMP, SESSIONTIMEZONE FROM DUAL

-- CASE[open]: ora-tz-interval — fails on tsql. (102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL 
CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)

-- CASE[open]: ora-unpivot — fails on mysql, postgresql, tsql. (207, b"Invalid column name 'col'.DB-Lib error message 20018, severity 16:\nGeneral SQL Se
SELECT id,col,val FROM (SELECT 1 id,10 a,20 b FROM DUAL) UNPIVOT (val FOR col IN (a,b))

-- CASE[fixed]: ora-upd-correlated — wrap the target's self-reference in a derived table (FROM (SELECT * FROM t) x) so MySQL allows the correlated subquery; live-verified (1,NULL),(2,10),(3,20).
CREATE TABLE t (id NUMBER, n NUMBER);UPDATE t SET n=(SELECT MAX(n) FROM t x WHERE x.id<t.id)

-- CASE[fixed]: ora-user-context — fails on mysql, postgresql, tsql. (195, b"'SYS_CONTEXT' is not a recognized built-in function name.DB-Lib error message 2001
SELECT USER, SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL

-- CASE[limit]: ora-utl-raw — Oracle's UTL_RAW.CAST_TO_RAW (RAW/byte packing) has no cross-engine equivalent; the gate now recognizes the UTL_RAW package functions and degrades + annotates instead of shipping an undefined function (docs/03-unsupported.md). fails on mysql, postgresql, tsql
SELECT UTL_RAW.CAST_TO_RAW('abc') AS r FROM DUAL

-- CASE[fixed]: ora-vsize — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.VS
SELECT VSIZE(123) AS r FROM DUAL

-- CASE[fixed]: ora-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT WIDTH_BUCKET(5, 0, 10, 5) AS r FROM DUAL

-- CASE[fixed]: ora-window-analytic — fails on postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT x,RATIO_TO_REPORT(x) OVER (),NTILE(2) OVER (ORDER BY x),CUME_DIST() OVER (ORDER BY x),PERCENT_RANK() OVER (ORDER BY x) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL)

-- CASE[limit]: ora-xmlagg — XMLAGG (XML fragment aggregation) has no MySQL or T-SQL equivalent; PostgreSQL has xmlagg/xmlelement natively (works, live-verified <e>x</e>). The MySQL/T-SQL output degrades to a carrier + warning (docs/03-unsupported.md). fails on mysql, tsql
SELECT XMLAGG(XMLELEMENT("e", dummy)) FROM DUAL

-- CASE[limit]: ora-xmlelement — fails on mysql, tsql. XMLELEMENT is an SQL/XML built-in on Oracle & PostgreSQL (transpiled faithfully, element-name case preserved); MySQL has no XML type and T-SQL has no XMLELEMENT (only FOR XML) — no cross-engine mapping (docs/03-unsupported.md §5, §2). Warned carrier on mysql/tsql.
SELECT XMLELEMENT("foo", 'bar') AS r FROM DUAL

-- CASE[limit]: ora-xmltable — XMLTABLE is a table-valued XML shredder; PostgreSQL's XMLTABLE has a different column-spec shape and T-SQL has no equivalent (it uses .nodes()/.value()), so the statement degrades to a carrier + warning rather than shipping the undefined function (docs/03-unsupported.md). fails on postgresql, tsql
SELECT x.a,x.b FROM XMLTABLE('/r' PASSING XMLTYPE('<r><a>1</a><b>2</b></r>') COLUMNS a INT PATH 'a', b INT PATH 'b') x

-- CASE[fixed]: ora-zero-divide — Oracle predefined exception ZERO_DIVIDE maps to the PL/pgSQL condition division_by_zero (was emitted verbatim, which PG rejects).
CREATE PROCEDURE p AS v NUMBER; BEGIN v := 1/0; EXCEPTION WHEN ZERO_DIVIDE THEN v := 0; END;
/

-- CASE[open]: ora23-json-object-star — fails on postgresql. function j_s_o_n_object() does not exist
CREATE TABLE t (id NUMBER, n NUMBER); CREATE TABLE s (id NUMBER, n NUMBER);
SELECT JSON_OBJECT(*) FROM t

-- CASE[fixed]: oracle-drop2-100|START — fails on postgresql, tsql. SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning
CREATE TABLE t (id NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100))

-- CASE[fixed]: oracle-drop4-COLLATE — fails on mysql, postgresql, tsql. SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning
CREATE TABLE t (a VARCHAR2(10) COLLATE BINARY_CI)

