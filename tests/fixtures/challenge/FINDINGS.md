# Challenge findings ledger (RED)

Auto-collected from live-engine validation. Each entry is a source
construct that transpiles wrong on >=1 target. `[open]` in the
`challenge_<engine>.sql` scripts; BLUE fixes and flips to `[fixed]`.

Kinds: **invalid** = target output rejected by the live engine;
**carrier** = degraded to an `Unhandled`/unrecognized carrier;
**silent** = valid output but a source literal/clause vanished (verify).


## my-alter-modify  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- sample: `(102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT`

## my-cast-convert  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- sample: `(243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:`
- src: `SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)`

## my-concat-ws  (mysql)
- targets: oracle(invalid)
- sample: `ORA-00904: "CONCAT_WS": invalid identifier`
- src: `SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r`

## my-date-add-interval  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- sample: `ORA-30081: invalid data type for datetime/interval arithmetic`
- src: `SELECT DATE_ADD('2020-01-01', INTERVAL 7 DAY) AS r`

## my-date-format  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- sample: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r`

## my-datetime-precision  (mysql)
- targets: tsql(invalid)
- sample: `(2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat`
- src: `CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)`

## my-group-concat  (mysql)
- targets: postgresql(invalid)
- sample: `function string_agg(integer, unknown) does not exist`
- src: `SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t`

## my-hex-bin  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- sample: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE`
- src: `SELECT HEX(255) AS r, BIN(5) AS b`

## my-json-object  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- sample: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_`
- src: `SELECT JSON_OBJECT('a', 1, 'b', 2)`

## my-json-type  (mysql)
- targets: oracle(invalid), tsql(invalid)
- sample: `(2715, b'Column, parameter, or variable #1: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (data JSON)`

## my-numeric  (mysql)
- targets: tsql(invalid)
- sample: `(2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)`

## my-timestampdiff  (mysql)
- targets: oracle(invalid)
- sample: `ORA-01861: literal does not match format string`
- src: `SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r`

## ora-add-months  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- sample: `(195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL`

## ora-cast-expr  (oracle)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT CAST('123' AS NUMBER), CAST(SYSDATE AS TIMESTAMP) FROM DUAL`

## ora-concat-num  (oracle)
- targets: tsql(invalid)
- sample: `(245, b"Conversion failed when converting the varchar value 'a' to data type int.DB-Lib er`
- src: `SELECT 'a' || 5 AS r FROM DUAL`

## ora-cursor  (oracle)
- targets: mysql(invalid)
- sample: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;`

## ora-last-day  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- sample: `(195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT LAST_DAY(SYSDATE) AS r FROM DUAL`

## ora-listagg  (oracle)
- targets: postgresql(invalid)
- sample: `function string_agg(integer, unknown) does not exist`
- src: `SELECT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) AS r FROM (SELECT 1 x FROM DUAL UNION SELECT 2 FROM DUAL)`

## ora-months-between  (oracle)
- targets: mysql(invalid), postgresql(invalid)
- sample: `operator does not exist: timestamp with time zone - integer`
- src: `SELECT MONTHS_BETWEEN(SYSDATE, SYSDATE - 40) AS r FROM DUAL`

## ora-tablespace  (oracle)
- targets: mysql(carrier), postgresql(carrier), tsql(carrier)
- sample: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a NUMBER) TABLESPACE users`

## ora-tz-interval  (oracle)
- targets: mysql(invalid), tsql(invalid)
- sample: `(102, b"Incorrect syntax near 'DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQL `
- src: `CREATE TABLE t (a TIMESTAMP WITH TIME ZONE, b INTERVAL DAY TO SECOND, c INTERVAL YEAR TO MONTH)`

## pg-age  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a`

## pg-alter-add  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- sample: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'`

## pg-array-agg  (postgresql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT ARRAY_AGG(x ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-array-jsonb  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- sample: `ORA-03099: unexpected item [ in a column definition`
- src: `CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)`

## pg-before-update-trg  (postgresql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT, updated TIMESTAMP);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN NEW.`

## pg-comment-on  (postgresql)
- targets: mysql(carrier), oracle(carrier), tsql(carrier)
- sample: `UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']`
- src: `CREATE TABLE t (a INT); COMMENT ON COLUMN t.a IS 'the a column'`

## pg-date-trunc  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI`
- src: `SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d`

## pg-exception-handler  (postgresql)
- targets: tsql(invalid)
- sample: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql`

## pg-expr-index  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- sample: `ORA-02327: cannot create index on expression with data type LOB`
- src: `CREATE TABLE t (a INT, b TEXT); CREATE INDEX ix ON t (lower(b))`

## pg-extract-dow  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(155, b"'DOW' is not a recognized datepart option.DB-Lib error message 20018, severity 15:`
- src: `SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d`

## pg-grouping-sets  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())`

## pg-jsonb-arrow  (postgresql)
- targets: mysql(invalid)
- sample: `(1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT '{"a":1}'::jsonb -> 'a'`

## pg-multi-out  (postgresql)
- targets: oracle(invalid)
- sample: `FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared`
- src: `CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql`

## pg-network-types  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag`
- src: `CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)`

## pg-overlay  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV`
- src: `SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o`

## pg-range-types  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m`
- src: `CREATE TABLE t (rng INT4RANGE, tsr TSRANGE)`

## pg-repeat-left-right  (postgresql)
- targets: oracle(invalid)
- sample: `ORA-00904: "RIGHT": invalid identifier`
- src: `SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)`

## pg-return-query  (postgresql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE FUNCTION f() RETURNS SETOF INT AS $$ BEGIN RETURN QUERY SELECT 1 UNION SELECT 2; END; $$ LANGUAGE plpgsql`

## pg-rollup  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)`

## pg-serial-bit  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- sample: `(2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit`
- src: `CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))`

## pg-string-agg-order  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- sample: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-trigger-raise  (postgresql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN IF OLD.n <> NEW.n THEN`

## pg-trim-both-chars  (postgresql)
- targets: oracle(invalid)
- sample: `ORA-30001: trim set should have only one character`
- src: `SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS t`

## pg-tz-interval  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- sample: `ORA-30089: missing or invalid <datetime field>`
- src: `CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)`

## ts-after-delete-count  (tsql)
- targets: oracle(invalid)
- sample: `TRIGGER TRG compiled INVALID (line 4): PL/SQL: ORA-00942: table or view does not exist`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t AFTER DELETE AS BEGIN DECLARE @c INT = (SELECT CO`

## ts-after-update-trg  (tsql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT, updated DATETIME);
GO
CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN UPDATE t`

## ts-alter-add  (tsql)
- targets: oracle(invalid)
- sample: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD b NVARCHAR(10) NOT NULL DEFAULT 'x'`

## ts-cast-trycast  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- sample: `ORA-01722: unable to convert string value containing 'x' to a number: `
- src: `SELECT CAST(123 AS VARCHAR(10)), TRY_CAST('x' AS INT), CONVERT(DATE, GETDATE())`

## ts-choose  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- sample: `ORA-00904: "CHOOSE": invalid identifier`
- src: `SELECT CHOOSE(2, 'a', 'b', 'c') AS r`

## ts-concat-ws  (tsql)
- targets: oracle(invalid)
- sample: `ORA-00904: "CONCAT_WS": invalid identifier`
- src: `SELECT CONCAT_WS('-', 'a', 'b', 'c') AS r`

## ts-cursor  (tsql)
- targets: mysql(invalid)
- sample: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT x FROM (VALUES (1),(2)) v(x); DECLARE @x INT; OPEN c; FETCH NEXT`

## ts-dateadd  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- sample: `ORA-30081: invalid data type for datetime/interval arithmetic`
- src: `SELECT DATEADD(DAY, 7, '2020-01-01') AS r`

## ts-datediff  (tsql)
- targets: oracle(invalid)
- sample: `ORA-01861: literal does not match format string`
- src: `SELECT DATEDIFF(DAY, '2020-01-01', '2020-01-10') AS r`

## ts-datetimeoffset  (tsql)
- targets: mysql(invalid), oracle(invalid)
- sample: `ORA-03060: Data type TIME is invalid.`
- src: `CREATE TABLE t (a DATETIMEOFFSET, b DATETIME2(7), c TIME(3))`

## ts-filtered-index  (tsql)
- targets: mysql(invalid), oracle(invalid)
- sample: `ORA-02158: invalid CREATE INDEX option`
- src: `CREATE TABLE t (a INT, b INT); CREATE NONCLUSTERED INDEX ix ON t (a) INCLUDE (b) WHERE a > 0`

## ts-format-number  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- sample: `ORA-00904: "NUMBER_TO_STR": invalid identifier`
- src: `SELECT FORMAT(1234.5, 'N2') AS r`

## ts-instead-of-insert  (tsql)
- targets: mysql(invalid), postgresql(invalid)
- sample: `"t" is a table`
- src: `CREATE TABLE t (id INT PRIMARY KEY, n INT);
GO
CREATE TRIGGER trg ON t INSTEAD OF INSERT AS BEGIN INSERT INTO t (id, n)`

## ts-json-value  (tsql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT JSON_VALUE('{"a":1}', '$.a')`

## ts-merge  (tsql)
- targets: mysql(invalid)
- sample: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `CREATE TABLE tgt (id INT PRIMARY KEY, n INT); MERGE tgt USING (VALUES (1, 5)) AS s(id, n) ON tgt.id = s.id WHEN MATCHED`

## ts-money  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- sample: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (price MONEY, small SMALLMONEY)`

## ts-recursive-cte  (tsql)
- targets: mysql(invalid), postgresql(invalid)
- sample: `relation "r" does not exist`
- src: `WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r`

## ts-rowversion  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- sample: `ORA-00902: invalid datatype`
- src: `CREATE TABLE t (row_ver ROWVERSION, flags BINARY(8))`

## ts-stuff  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- sample: `ORA-00904: "STUFF": invalid identifier`
- src: `SELECT STUFF('abcdef', 2, 3, 'XY') AS r`

## ts-while-loop  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- sample: `PROCEDURE P compiled INVALID (line 15): PLS-00103: Encountered the symbol "=" when expecti`
- src: `CREATE PROCEDURE p @id INT AS BEGIN DECLARE @n INT; SELECT @n = COUNT(*) FROM (VALUES (1),(2)) v(x); WHILE @n > 0 BEGIN`
