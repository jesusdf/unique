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

-- CASE[open]: ora-bitand — fails on mysql, postgresql, tsql. (195, b"'BITAND' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT BITAND(5, 3) AS r FROM DUAL

-- CASE[open]: ora-cast-expr — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL

-- CASE[open]: ora-concat-null — fails on tsql. SEMANTIC: Oracle '||' treats NULL as empty string -> 'ab'; T-SQL/PG/MySQL return NULL. No 
SELECT 'a' || NULL || 'b' AS r FROM DUAL

-- CASE[open]: ora-concat-num — fails on tsql. (245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er
SELECT 'a' || 5 AS r FROM DUAL

-- CASE[open]: ora-connect-by — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LEVEL, 1 AS n FROM DUAL CONNECT BY LEVEL <= 5

-- CASE[open]: ora-cursor — fails on mysql. (1337, 'Variable or condition declaration after cursor or handler declaration')
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;

-- CASE[open]: ora-date-plus-int — fails on mysql, postgresql. SEMANTIC: Oracle 'date + 1' adds ONE DAY; MySQL 'CURRENT_TIMESTAMP + 1' does numeric arith
SELECT SYSDATE + 1 AS r FROM DUAL

-- CASE[open]: ora-dump — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DU
SELECT DUMP('abc') AS r FROM DUAL

-- CASE[open]: ora-empty-string-null — fails on postgresql. SEMANTIC: Oracle '' IS NULL so NVL returns 'was null'; COALESCE('', ...) on other engines 
SELECT NVL('', 'was null') AS r FROM DUAL

-- CASE[open]: ora-from-tz — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_TZ(CAST(SYSDATE AS TIMESTAMP), '00:00') AS r FROM DUAL

-- CASE[open]: ora-initcap — fails on mysql, postgresql, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r FROM DUAL

-- CASE[open]: ora-last-day — fails on postgresql, tsql. (195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT LAST_DAY(SYSDATE) AS r FROM DUAL

-- CASE[open]: ora-listagg — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)

-- CASE[open]: ora-months-between — fails on mysql, postgresql. operator does not exist: timestamp with time zone - integer
SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL

-- CASE[open]: ora-next-day — fails on mysql, postgresql, tsql. (195, b"'NEXT_DAY' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT NEXT_DAY(SYSDATE, 'MONDAY') AS r FROM DUAL

-- CASE[open]: ora-numeric-concat — fails on tsql. SEMANTIC: Oracle '||' concatenates -> '23'; emitted as T-SQL '2 + 3' = 5. Result changed s
SELECT 2 || 3 AS r FROM DUAL

-- CASE[open]: ora-numtodsinterval — fails on mysql, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS r FROM DUAL

-- CASE[open]: ora-sequence — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE SEQUENCE seq START WITH 1;
SELECT seq.NEXTVAL FROM DUAL

-- CASE[open]: ora-soundex — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('Smith') AS r FROM DUAL

-- CASE[open]: ora-tablespace — fails on mysql, postgresql, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a NUMBER) TABLESPACE users

-- CASE[open]: ora-translate — fails on mysql. (1305, 'FUNCTION unique_val_6c47c43e12f3.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r FROM DUAL

-- CASE[open]: ora-tz-interval — fails on mysql, tsql. (102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL 
CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)

