# Challenge findings ledger (RED)

Source constructs that transpile wrong on >=1 target, each **validated on a
live engine** (original accepted by its own engine; output rejected by the
target engine, or degraded to an unrecognized carrier). Tagged `[open]` in
the `challenge_<engine>.sql` scripts; BLUE fixes and flips to `[fixed]`.

> **BLUE round 2026-07-18 — pruned.** 703 finding-rows are RESOLVED and were
> removed: the RC-1b gate now degrades every unmapped built-in to a documented
> carrier + warning (no longer SILENT), and 21 built-ins + FK/CHECK/IDENTITY/
> COMMENT translate faithfully. What remains below is the true residual — the
> architectural floor: **func-diffs** (collation, integer division, LENGTH
> bytes-vs-chars, NULL propagation — need per-column type/collation knowledge),
> the harder **silent-drops** (COLLATE, window frames), and **invalid** rows that
> are DDL/type/operator gaps or now translate but were not re-executed to
> confirm. See `docs/TODO.md §5` for the full resolution.


> **Scope: SILENT defects only.** A construct that degrades WITH a warning is a documented, acceptable outcome — NOT an error — and is excluded (548 warned rows dropped: `Unhandled` carriers and warned-invalid preservations). What remains transpiles wrong with NO warning.

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


## my-adddate  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2020-01-31',),) target=(('2020-01-31 00:00:00',),)`
- src: `SELECT ADDDATE('2020-01-01', 30) AS r`

## my-agg-bit  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI`
- src: `SELECT BIT_AND(x),BIT_OR(x),BIT_XOR(x) FROM (SELECT 3 x UNION ALL SELECT 5 x UNION ALL SELECT 6 x) t`

## my-agg-boolean  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('2', '3', '0.6667', '1'),) target=(('2', '3', '0.666667', '1'),)`
- src: `SELECT SUM(x>1), COUNT(x>1), AVG(x>1), MAX(x>1) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 3) t`

## my-agg-collect  (mysql)
- targets: postgresql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT GROUP_CONCAT(x),JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION ALL SELECT 2 x) t`

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
- targets: postgresql(invalid)
- live error: `(102, b"Incorrect syntax near '>'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `SELECT ANY_VALUE(x), GROUP_CONCAT(x) FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x>0`

## my-ascii-empty  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('NULL',),)`
- src: `SELECT ASCII('') AS r`

## my-avg-int  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t`

## my-avg-precision2  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.6667',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 2) t`

## my-bintypes  (mysql)
- targets: tsql(invalid)
- live error: `(2716, b'Column, parameter, or variable #7: Cannot specify a column width on data type bit`
- src: `CREATE TABLE t (a BINARY(16), b VARBINARY(255), c TINYBLOB, d BLOB, e MEDIUMBLOB, f LONGBLOB, g BIT(8), h BOOL)`

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

## my-bit-negative  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('18446744073709551616', '18446744073709551616', '3', '9223372036854775`
- src: `SELECT ~0, ~5, -5 & 3, -1 >> 1, 5 & -1`

## my-bit-prec2  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2', '14', '8'),) target=(('3', '14', '5'),)`
- src: `SELECT 10 & 6 + 1, 10 | 2 * 3, 1 << 2 + 1`

## my-bitand-prec  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('3',),)`
- src: `SELECT 10 & 6 + 1 AS r`

## my-bitnot  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('18446744073709551616',),) target=(('-1',),)`
- src: `SELECT ~0 AS r`

## my-bitnot-arith  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('18446744073709551616',),) target=(('-5',),)`
- src: `SELECT ~5 + 1 AS r`

## my-bitops  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1', '7', '6', '18446744073709551616', '10', '2'),) target=(('1', '7',`
- src: `SELECT 5 & 3, 5 | 2, 5 ^ 3, ~5, 5 << 1, 5 >> 1`

## my-bool-char  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('t',),)`
- src: `SELECT CAST((1=1) AS CHAR) AS r`

## my-cast-binary2  (mysql)
- targets: postgresql(invalid)
- live error: `type "binary" does not exist`
- src: `SELECT CONVERT('abc',BINARY), CONVERT('abc' USING latin1), CAST('abc' AS BINARY)`

## my-cast-convert  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:`
- src: `SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)`

## my-cast-datetime  (mysql)
- targets: oracle(invalid)
- live error: `ORA-01843: An invalid month was specified.`
- src: `SELECT CAST('2020-01-01' AS DATETIME) AS r`

## my-cast-datetime2  (mysql)
- targets: oracle(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT CAST('2020-01-01 10:00' AS DATE), CAST('2020-01-01 10:00' AS TIME), CAST('2020-01-01 10:00' AS DATETIME)`

## my-cast-decimal2  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit`
- src: `SELECT CAST('12.99' AS DECIMAL(4,1)), CAST('12.99' AS DECIMAL(3,0)), CAST('abc' AS DECIMAL)`

## my-cast-int  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT CAST(2.7 AS SIGNED) AS r`

## my-cast-json  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(243, b'Type json is not a defined system type.DB-Lib error message 20018, severity 16:\nG`
- src: `SELECT CAST(1 AS JSON), CAST('[1,2]' AS JSON), CAST(NULL AS JSON)`

## my-cast-matrix  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST(3.14 AS DECIMAL(10,2)), CAST(3.14 AS SIGNED), CAST(3.14 AS CHAR), CAST(3.14 AS DOUBLE)`

## my-cast-num-char  (mysql)
- targets: oracle(invalid)
- live error: `ORA-25137: Data value out of range`
- src: `SELECT CAST(1234.5 AS CHAR) AS r`

## my-cast-suite  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST('123' AS SIGNED),CAST('1.5' AS DECIMAL(4,2)),CONVERT('123',SIGNED),CAST('2020-01-01' AS DATE),CAST(65 AS CHAR)`

## my-cast-time  (mysql)
- targets: oracle(invalid)
- live error: `DPY-3006: Oracle data type 178 is not supported`
- src: `SELECT CAST('10:00:00' AS TIME) AS r`

## my-cast-year  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST('2020' AS YEAR), CAST(2020 AS YEAR), CAST('99' AS YEAR)`

## my-change-column  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'CHANGE'.DB-Lib error message 20018, severity 15:\nGeneral S`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t CHANGE a x INT`

## my-char-256  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('0100',),) target=(('\x01\x00',),)`
- src: `SELECT CHAR(256) AS r`

## my-check-enforced  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'ENFORCED'.DB-Lib error message 20018, severity 15:\nGeneral`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) ENFORCED`

## my-coalesce-empty  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('NULL',),)`
- src: `SELECT COALESCE(NULL, 0) = '' AS r`

## my-coalesce-single  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00938: not enough arguments for function`
- src: `SELECT COALESCE(x) FROM (SELECT NULL x) t`

## my-collation-fn  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('utf8mb4_0900_ai_ci',),) target=(('USING_NLS_COMP',),)`
- src: `SELECT COLLATION('abc') AS r`

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

## my-concat-null3  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL', 'a,b'),) target=(('a', 'a,b'),)`
- src: `SELECT CONCAT('a',NULL), CONCAT_WS(',','a',NULL,'b')`

## my-convert-signed  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CONVERT('123', SIGNED) AS r`

## my-convert-tz  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO`
- src: `SELECT CONVERT_TZ('2020-01-01 10:00', '+00:00', '+02:00') AS r`

## my-convert-using2  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('2020-06-15 14:30',),) target=(('2',),)`
- src: `SELECT CONVERT('2020-06-15 14:30' USING utf8mb4) AS r`

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

## my-dateadd-units  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 2 of dateadd function.DB-Lib e`
- src: `SELECT DATE_ADD(NOW(),INTERVAL 1 QUARTER), DATE_SUB(NOW(),INTERVAL 2 WEEK)`

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

## my-decimal-scale  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('3.33333', '3.3333', '3.33333', '2.25', '0.01'),) target=(('3.33333', `
- src: `SELECT 10.00/3, 10/3.0, CAST(10 AS DECIMAL(10,4))/3, 1.5*1.5, 0.1*0.1`

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

## my-empty-eq-zero  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('NULL',),)`
- src: `SELECT '' = 0 AS r`

## my-extract-compound  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(155, b"'YEAR_MONTH' is not a recognized datepart option.DB-Lib error message 20018, sever`
- src: `SELECT EXTRACT(YEAR_MONTH FROM NOW()), EXTRACT(DAY_HOUR FROM NOW())`

## my-extractvalue  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX`
- src: `SELECT EXTRACTVALUE('<a>1</a>', '/a') AS r`

## my-fconcatnum  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('x5', 'x5.5', 'x1', 'NULL'),) target=(('x5', 'x5.5', 'x1', 'x'),)`
- src: `SELECT CONCAT('x',5),CONCAT('x',5.5),CONCAT('x',TRUE),CONCAT('x',NULL)`

## my-field  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI`
- src: `SELECT FIELD('b', 'a', 'b', 'c') AS r`

## my-float-precision  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0.3', '0.3', '0.33333', '0.6667'),) target=(('0.3', '0.3', '0.333333'`
- src: `SELECT 0.1+0.2, CAST(0.1 AS DOUBLE)+CAST(0.2 AS DOUBLE), 1.0/3, 2/3`

## my-floor-precision  (mysql)
- targets: oracle(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('3',),)`
- src: `SELECT FLOOR(2.9999999999999999) AS r`

## my-fmt-spec  (mysql)
- targets: oracle(invalid), postgresql(silent), tsql(silent)
- live error: `SILENT: source literal(s) ["'%a %b %e %T %Y'", "'%p %l:%i'", "'%j %U %u %V'"] absent from `
- src: `SELECT DATE_FORMAT(NOW(),'%a %b %e %T %Y'),DATE_FORMAT(NOW(),'%p %l:%i'),DATE_FORMAT(NOW(),'%j %U %u %V')`

## my-fmt-spec2  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT DATE_FORMAT('2020-06-15','%D %W %M'),DATE_FORMAT('2020-06-15','%X %V')`

## my-fmt3  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT FORMAT(1234.5678,2),FORMAT(1234.5678,4,'de_DE'),TRUNCATE(1234.5678,2)`

## my-for-share  (mysql)
- targets: oracle(invalid)
- live error: `ORA-02000: missing COMPRESS or UPDATE keyword`
- src: `CREATE TABLE t (id INT, INDEX ix (id)); SELECT id FROM t WHERE id = 1 FOR SHARE`

## my-fulltext  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA`
- src: `CREATE TABLE t (txt TEXT, FULLTEXT(txt));
SELECT * FROM t WHERE MATCH(txt) AGAINST('hello' IN NATURAL LANGUAGE MODE)`

## my-gen-constr  (mysql)
- targets: tsql(invalid)
- live error: `(1764, b"Computed Column 'b' in table 't' is invalid for use in 'CHECK CONSTRAINT' because`
- src: `CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a+1) VIRTUAL, UNIQUE (b), CHECK (b>a))`

## my-gencol2  (mysql)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(1759, b"Computed column 'b' in table 't' is not allowed to be used in another computed-co`
- src: `CREATE TABLE t (a INT, b INT AS (a*2) STORED, c INT AS (a+b) VIRTUAL, KEY(b))`

## my-greatest-null  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('3',),)`
- src: `SELECT GREATEST(1, NULL, 3) AS r`

## my-greatest-null2  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('1',),)`
- src: `SELECT GREATEST(NULL, 1) AS r`

## my-groupconcat-distinct  (mysql)
- targets: oracle(silent-rt), postgresql(invalid)
- live error: `SILENT-ROUNDTRIP: literal(s) ["'|'"] lost after mysql->oracle->mysql`
- src: `SELECT GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '|') FROM (SELECT 1 x UNION ALL SELECT 1 UNION ALL SELECT 2) t`

## my-having-noagg  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8121, b"Column 't.x' is invalid in the HAVING clause because it is not contained in eithe`
- src: `SELECT x, RANK() OVER (ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2) t HAVING x>0`

## my-ifnull-empty  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('',),) target=(('NULL',),)`
- src: `SELECT IFNULL('', NULL) AS r`

## my-index-fns  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI`
- src: `SELECT INTERVAL(3, 1, 2, 4, 6), FIELD('b','a','b'), ELT(1,'x','y')`

## my-insert-oob  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('abc',),) target=(('NULL',),)`
- src: `SELECT INSERT('abc', 10, 1, 'X') AS r`

## my-insert-zeropos  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('abcdef',),) target=(('NULL',),)`
- src: `SELECT INSERT('abcdef', 0, 2, 'XY') AS r`

## my-insert2  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "STUFF": invalid identifier`
- src: `SELECT INSERT('Quadratic', 3, 4, 'What') AS r`

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

## my-json-agg  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAYAGG(x), JSON_OBJECTAGG(x,x*10) FROM (SELECT 1 x UNION ALL SELECT 2) t`

## my-json-aggs  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAYAGG(x), JSON_OBJECTAGG(x, x*2) FROM (SELECT 1 x UNION SELECT 2) t`

## my-json-build  (mysql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS`
- src: `SELECT JSON_ARRAY(1,'a',NULL,TRUE),JSON_OBJECT('k','v','n',1)`

## my-json-index  (mysql)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(2715, b'Column, parameter, or variable #2: Cannot find data type json.DB-Lib error messag`
- src: `CREATE TABLE t (a INT, b JSON, c INT AS (JSON_EXTRACT(b,'$.x')) STORED, INDEX((CAST(b->'$.x' AS UNSIGNED))))`

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

## my-least-greatest-null  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL', 'NULL'),) target=(('a', '1'),)`
- src: `SELECT LEAST(NULL, 'a') AS r, GREATEST(NULL, 1) AS b`

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

## my-length-div  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('6',),) target=(('1',),)`
- src: `SELECT LENGTH(1/3) AS r`

## my-locate-case  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT LOCATE('a', 'ABC') AS r`

## my-locate-empty  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT LOCATE('', '') AS r`

## my-locate-empty2  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1', '1'),) target=(('0', '0'),)`
- src: `SELECT LOCATE('', 'abc'), INSTR('abc', '')`

## my-log2-log10  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3', '3'),) target=(('0.333333', '0.333333'),)`
- src: `SELECT LOG2(8), LOG10(1000)`

## my-lpad-trunc  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('bc',),)`
- src: `SELECT LPAD('abc', 2, 'x') AS r`

## my-mod-edge  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('0', '1', '1'),) target=(('0', '0', '0'),)`
- src: `SELECT MOD(0,5), MOD(5,0) IS NULL, 5%0 IS NULL`

## my-mod-zero  (mysql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 5 MOD 0 IS NULL AS r`

## my-month-overflow  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)`
- src: `SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r`

## my-nested-call  (mysql)
- targets: oracle(invalid)
- live error: `PROCEDURE P compiled INVALID (line 4): PLS-00201: identifier 'OTHER_PROC' must be declared`
- src: `CREATE PROCEDURE p() BEGIN CALL other_proc(); END`

## my-numeric  (mysql)
- targets: tsql(invalid)
- live error: `(2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)`

## my-order-case-sens  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('Apple',), ('banana',), ('Cherry',)) target=(('Apple',), ('Cherry',), `
- src: `SELECT x FROM (SELECT 'Apple' x UNION SELECT 'banana' UNION SELECT 'Cherry') t ORDER BY x`

## my-pad-repeat  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SPACE": invalid identifier`
- src: `SELECT LPAD('7',3,'0'),RPAD('7',3,'x'),REPEAT('ab',3),REVERSE('abc'),SPACE(3),CONCAT('[',SPACE(2),']')`

## my-pi-fns  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU`
- src: `SELECT TRUNCATE(PI(), 4), ROUND(PI(), 4), FORMAT(PI(), 4)`

## my-pi-vals  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('180', '3.14159', '3.14159'),) target=(('180', '3', '3.14159'),)`
- src: `SELECT DEGREES(PI()), RADIANS(180), PI()`

## my-reads-sql  (mysql)
- targets: tsql(invalid)
- live error: `(8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve`
- src: `CREATE FUNCTION f(a INT) RETURNS INT READS SQL DATA BEGIN RETURN (SELECT COUNT(*) FROM (SELECT a) t); END`

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

## my-round-cast  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST(3.99 AS SIGNED),CAST(-3.99 AS SIGNED),CONVERT(3.99,SIGNED)`

## my-scalar-subquery-assign  (mysql)
- targets: tsql(invalid)
- live error: `(8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve`
- src: `CREATE PROCEDURE p() BEGIN DECLARE v INT; SET v = (SELECT COUNT(*) FROM (SELECT 1) t); END`

## my-seq-concat  (mysql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-32039: missing column alias list in recursive WITH clause element SEQ`
- src: `WITH RECURSIVE seq AS (SELECT 1 n UNION ALL SELECT n+1 FROM seq WHERE n<10) SELECT GROUP_CONCAT(n) FROM seq`

## my-str-null  (mysql)
- targets: oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('NULL', 'NULL', 'NULL', 'NULL', 'NULL', 'NULL'),) target=(('NULL', 'a'`
- src: `SELECT LENGTH(NULL), CONCAT('a',NULL), REPLACE(NULL,'a','b'), SUBSTRING(NULL,1,2), UPPER(NULL), TRIM(NULL)`

## my-str-plus-interval  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2020-01-02',),) target=(('2020-01-02 00:00:00',),)`
- src: `SELECT '2020-01-01' + INTERVAL 1 DAY AS r`

## my-strnum-add  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('10',),) target=(('55',),)`
- src: `SELECT '5'+'5' AS r`

## my-subdate  (mysql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2019-12-31',),) target=(('2019-12-31 00:00:00',),)`
- src: `SELECT SUBDATE('2020-01-31', INTERVAL 1 MONTH) AS r`

## my-substr-float  (mysql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('llo',),) target=(('el',),)`
- src: `SELECT SUBSTRING('hello', 2.9, 2.9) AS r`

## my-sum-div-count  (mysql)
- targets: postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t`

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

## my-trig  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(174, b'The atan function requires 1 argument(s).DB-Lib error message 20018, severity 15:\`
- src: `SELECT ATAN2(1,1), ATAN(1,1), DEGREES(PI()), RADIANS(180), COT(1)`

## my-trig-suite  (mysql)
- targets: oracle(invalid)
- live error: `ORA-00904: "RADIANS": invalid identifier`
- src: `SELECT ACOS(1),ASIN(0),ATAN(1),COS(0),SIN(0),TAN(0),COT(1),DEGREES(1),RADIANS(1)`

## my-ts-to-date  (mysql)
- targets: postgresql(func)
- live error: `FUNC-DIFF: source=(('2020-01-01',),) target=(('2020-01-01 14:30:00+00:00',),)`
- src: `SELECT DATE(TIMESTAMP '2020-01-01 14:30') AS r`

## my-tz-convert  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO`
- src: `SELECT CONVERT_TZ('2020-06-15 10:00:00','+00:00','+05:30'), CONVERT_TZ('2020-06-15 10:00:00','UTC','America/New_York')`

## my-upd-selfjoin  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4104, b'The multi-part identifier "t2.n" could not be bound.DB-Lib error message 20018, s`
- src: `CREATE TABLE t (id INT, n INT);UPDATE t t1 JOIN t t2 ON t1.id=t2.id+1 SET t1.n=t2.n`

## my-update-join  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4104, b'The multi-part identifier "s.n" could not be bound.DB-Lib error message 20018, se`
- src: `CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n`

## my-using-join  (mysql)
- targets: tsql(invalid)
- live error: `(209, b"Ambiguous column name 'x'.DB-Lib error message 20018, severity 16:\nGeneral SQL Se`
- src: `SELECT x FROM (SELECT 1 x) a JOIN (SELECT 1 x) b USING (x)`

## my-xml-fns  (mysql)
- targets: oracle(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.Ex`
- src: `SELECT ExtractValue('<r><a>1</a></r>','/r/a'), UpdateXML('<r><a>1</a></r>','/r/a','<a>2</a>')`

## mysql-drop-'note'|note  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop)
- live error: `SILENT CLAUSE DROP: ''note'|note' absent from valid oracle output, no warning (target supp`
- src: `CREATE TABLE t (a INT COMMENT 'note')`

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

## mysql-drop5-utf8mb4|CHAR  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'utf8mb4|CHARSET' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT AUTO_INCREMENT PRIMARY KEY, b VARCHAR(20)) DEFAULT CHARSET=utf8mb4`

## mysql-qdrop-ROLLUP  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'ROLLUP' absent from valid tsql output, no warning`
- src: `SELECT x FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x WITH ROLLUP`

## mysql-qdrop-SQL_CALC_FOU  (mysql)
- targets: oracle(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'SQL_CALC_FOUND_ROWS|FOUND' absent from valid tsql output, no warning`
- src: `SELECT SQL_CALC_FOUND_ROWS x FROM (SELECT 1 x) t LIMIT 1`

## ora-add-months  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'ADD_MONTHS' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT ADD_MONTHS(SYSDATE, 3) AS r FROM DUAL`

## ora-alter-suite  (oracle)
- targets: tsql(invalid)
- live error: `(5074, b"The object 'DF__t__name__6D63CF5D' is dependent on column 'nm'.DB-Lib error messa`
- src: `CREATE TABLE t (id NUMBER);
ALTER TABLE t ADD (name VARCHAR2(50) DEFAULT '' NOT NULL);
ALTER TABLE t MODIFY (id NUMBER(19));
ALTER`

## ora-arr-collect  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "SYS" or the user-defined function or aggregate "SYS.OD`
- src: `SELECT SYS.ODCINUMBERLIST(1,2,3) FROM DUAL`

## ora-bitand  (oracle)
- targets: postgresql(invalid)
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

## ora-cast-int-edge  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('4', '3', '4', '4'),) target=(('3', '3', '4', '4'),)`
- src: `SELECT CAST('3.9' AS INT), TRUNC(3.9), ROUND(3.9), CAST(3.9 AS NUMBER(1)) FROM DUAL`

## ora-cast-onerror  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(8114, b'Error converting data type varchar to numeric.DB-Lib error message 20018, severit`
- src: `SELECT CAST('abc' AS NUMBER DEFAULT -1 ON CONVERSION ERROR) AS r FROM DUAL`

## ora-collect  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO`
- src: `SELECT CAST(COLLECT(x) AS SYS.ODCINUMBERLIST) FROM (SELECT 1 x FROM DUAL)`

## ora-cursor  (oracle)
- targets: mysql(invalid)
- live error: `(1337, 'Variable or condition declaration after cursor or handler declaration')`
- src: `CREATE PROCEDURE p AS CURSOR c IS SELECT 1 AS x FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; CLOSE c; END;`

## ora-cursor-attr  (oracle)
- targets: mysql(invalid), tsql(invalid)
- live error: `(128, b'The name "c" is not permitted in this context. Valid expressions are constants, co`
- src: `CREATE PROCEDURE p AS CURSOR c IS SELECT 1 FROM DUAL; v NUMBER; BEGIN OPEN c; FETCH c INTO v; IF c%FOUND THEN DBMS_OUTPUT.PUT_LINE`

## ora-cursor-for-loop  (oracle)
- targets: tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'END'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE PROCEDURE p AS BEGIN FOR r IN (SELECT 1 AS x FROM DUAL) LOOP NULL; END LOOP; END;
/`

## ora-date-diff-days  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('60',),) target=(('0',),)`
- src: `SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r FROM DUAL`

## ora-date-plus-int2  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2020-01-31 00:00:00',),) target=(('2050',),)`
- src: `SELECT DATE '2020-01-01' + 30 AS r FROM DUAL`

## ora-day-of-week  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('24',),)`
- src: `SELECT TO_NUMBER(TO_CHAR(DATE '2020-06-14', 'D')) AS r FROM DUAL`

## ora-decimal-scale  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('3.33333', '3.33333', '3.33333', '2.25'),) target=(('3.33333', '3.3333`
- src: `SELECT 10.00/3, 10/3.0, CAST(10 AS NUMBER(10,4))/3, 1.5*1.5 FROM DUAL`

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

## ora-dyn-count  (oracle)
- targets: tsql(invalid)
- live error: `(102, b"Incorrect syntax near '+'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `CREATE PROCEDURE p (tbl VARCHAR2) AS n NUMBER; BEGIN EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || tbl INTO n; END;
/`

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

## ora-float-precision  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.3', '0.3', '0.333333'),) target=(('0.3', '0.3', '0.33333'),)`
- src: `SELECT 0.1+0.2, CAST(0.1 AS BINARY_DOUBLE)+CAST(0.2 AS BINARY_DOUBLE), 1.0/3 FROM DUAL`

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

## ora-fmt3  (oracle)
- targets: postgresql(silent-rt)
- live error: `(195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT TO_CHAR(1234.5678,'9G999D99'),TO_CHAR(-5,'S9') FROM DUAL`

## ora-for-update-nowait  (oracle)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id NUMBER); SELECT * FROM t FOR UPDATE NOWAIT`

## ora-format-currency  (oracle)
- targets: mysql(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('1,234,567.89', '$1,234,567.89'),) target=(('1,234,567.89', '1,234,567`
- src: `SELECT TO_CHAR(1234567.891,'FM999,999,990.00'), TO_CHAR(1234567.891,'FML999G999G990D00') FROM DUAL`

## ora-forupdate-wait  (oracle)
- targets: mysql(invalid), postgresql(invalid)
- live error: `syntax error at or near "WAIT"`
- src: `CREATE TABLE t (id NUMBER); CREATE INDEX ix ON t (id);
SELECT id FROM t WHERE id = 1 FOR UPDATE OF id WAIT 5`

## ora-functional-index  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near '*'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `CREATE TABLE t (a NUMBER); CREATE INDEX ix ON t (a * 2)`

## ora-gen-expr  (oracle)
- targets: mysql(invalid)
- live error: `(1075, 'Incorrect table definition; there can be only one auto column and it must be defin`
- src: `CREATE TABLE t (a NUMBER, b NUMBER, hyp NUMBER GENERATED ALWAYS AS (SQRT(a*a+b*b)))`

## ora-grouping-sets  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(8120, b"Column 'uq_dt.deptno' is invalid in the select list because it is not contained i`
- src: `SELECT deptno,job,SUM(sal) FROM (SELECT 10 deptno,'X' job,100 sal FROM DUAL) GROUP BY GROUPING SETS ((deptno),(job),())`

## ora-hint-comment  (oracle)
- targets: mysql(invalid)
- live error: `(1064, "You have an error in your SQL syntax; check the manual that corresponds to your My`
- src: `SELECT /*+ FULL(t) */ 1 AS r FROM DUAL t`

## ora-identity-opts  (oracle)
- targets: mysql(invalid)
- live error: `(1075, 'Incorrect table definition; there can be only one auto column and it must be defin`
- src: `CREATE TABLE t (a NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100 INCREMENT BY 10 MAXVALUE 9999 CYCLE))`

## ora-implicit-arith  (oracle)
- targets: mysql(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('2', '20', '2'),) target=(('11', '20', '2'),)`
- src: `SELECT '1'+1, '10'*2, TO_NUMBER('1')+1 FROM DUAL`

## ora-initcap  (oracle)
- targets: postgresql(invalid)
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

## ora-instr-empty  (oracle)
- targets: mysql(func), postgresql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('NULL',),) target=(('0',),)`
- src: `SELECT INSTR('abc', '') AS r FROM DUAL`

## ora-json-value  (oracle)
- targets: tsql(silent-rt)
- live error: `SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'"] lost after oracle->tsql->oracle`
- src: `SELECT JSON_VALUE('{"a":1}', '$.a') AS r FROM DUAL`

## ora-json-x  (oracle)
- targets: tsql(silent-rt)
- live error: `SILENT-ROUNDTRIP: literal(s) ['\'{"a":1}\'', "'$.a'", '\'{"a":[1]}\'', "'$.a'"] lost after`
- src: `SELECT JSON_VALUE('{"a":1}','$.a'),JSON_QUERY('{"a":[1]}','$.a') FROM DUAL`

## ora-json-xml-agg  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT JSON_ARRAYAGG(x), XMLAGG(XMLELEMENT("i",x)) FROM (SELECT 1 x FROM DUAL UNION ALL SELECT 2 FROM DUAL) t`

## ora-last-day  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(195, b"'LAST_DAY' is not a recognized built-in function name.DB-Lib error message 20018, `
- src: `SELECT LAST_DAY(SYSDATE) AS r FROM DUAL`

## ora-lastday-leap  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2020-02-29 00:00:00',),) target=(('2020-02-29',),)`
- src: `SELECT LAST_DAY(DATE '2020-02-01') AS r FROM DUAL`

## ora-length-trailing  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('6',),) target=(('3',),)`
- src: `SELECT LENGTH('abc   ') AS r FROM DUAL`

## ora-listagg-over  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4113, b"The function 'STRING_AGG' is not a valid windowing function, and cannot be used w`
- src: `SELECT deptno, LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) OVER (PARTITION BY deptno) FROM (SELECT 1 deptno, 2 x FROM DUAL)`

## ora-listagg-overflow  (oracle)
- targets: mysql(silent), postgresql(invalid), tsql(silent)
- live error: `SILENT: source literal(s) ["'...'"] absent from valid output, no warning`
- src: `SELECT LISTAGG(x,',' ON OVERFLOW TRUNCATE '...') WITHIN GROUP (ORDER BY x) FROM (SELECT 1 x FROM DUAL) t`

## ora-month-name  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('June',),) target=(('Month',),)`
- src: `SELECT TO_CHAR(DATE '2020-06-01', 'Month') AS r FROM DUAL`

## ora-months-between-val  (oracle)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('1.83871',),) target=(('2',),)`
- src: `SELECT MONTHS_BETWEEN(DATE '2020-03-10', DATE '2020-01-15') AS r FROM DUAL`

## ora-multiset-table  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:`
- src: `SELECT COLUMN_VALUE FROM TABLE(CAST(MULTISET(SELECT LEVEL FROM DUAL CONNECT BY LEVEL<=3) AS SYS.ODCINUMBERLIST))`

## ora-name-locale  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('Monday', 'June', 'MONDAY'),) target=(('25ay', 'Month', 'Monday'),)`
- src: `SELECT TO_CHAR(DATE '2020-06-15','Day'), TO_CHAR(DATE '2020-06-15','Month'), TRIM(TO_CHAR(DATE '2020-06-15','DAY')) FROM DUAL`

## ora-now-fns  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO`
- src: `SELECT SYSDATE, CURRENT_DATE, SYSTIMESTAMP, LOCALTIMESTAMP FROM DUAL`

## ora-now-variants  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO`
- src: `SELECT SYSDATE, SYSTIMESTAMP, CURRENT_TIMESTAMP, CURRENT_DATE, LOCALTIMESTAMP FROM DUAL`

## ora-numfmt-lead  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.5',),) target=(('0',),)`
- src: `SELECT TO_CHAR(0.5, '0.00') AS r FROM DUAL`

## ora-numfmt-sign  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('-42',),) target=(('NULL',),)`
- src: `SELECT TO_CHAR(-42, 'S999') AS r FROM DUAL`

## ora-numfmt-spec  (oracle)
- targets: mysql(silent), postgresql(silent-rt)
- live error: `(195, b"'TO_CHAR' is not a recognized built-in function name.DB-Lib error message 20018, s`
- src: `SELECT TO_CHAR(1234.5,'L9G999D99MI'),TO_CHAR(0.75,'999PR'),TO_CHAR(255,'0XX') FROM DUAL`

## ora-numfmt-thousands  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1,234,567.89',),) target=(('NULL',),)`
- src: `SELECT TO_CHAR(1234567.891, '9,999,999.99') AS r FROM DUAL`

## ora-order-nulls-default  (oracle)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))`
- src: `SELECT x FROM (SELECT 3 x FROM DUAL UNION ALL SELECT 1 x FROM DUAL UNION ALL SELECT NULL x FROM DUAL) ORDER BY x`

## ora-pk-using-index  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(1018, b"Incorrect syntax near 'INDEX'. If this is intended as a part of a table hint, A W`
- src: `CREATE TABLE t (id NUMBER, CONSTRAINT pk PRIMARY KEY (id) USING INDEX)`

## ora-rand  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "DBMS_RANDOM" or the user-defined function or aggregate`
- src: `SELECT DBMS_RANDOM.VALUE, DBMS_RANDOM.STRING('U', 5) FROM DUAL`

## ora-recursive-func  (oracle)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END;
/`

## ora-regexp-group  (oracle)
- targets: mysql(invalid)
- live error: `(1582, "Incorrect parameter count in the call to native function 'REGEXP_SUBSTR'")`
- src: `SELECT REGEXP_SUBSTR('a1b2c3', '(\d)', 1, 1, NULL, 1) AS r FROM DUAL`

## ora-round-date-month  (oracle)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('2020-07-01 00:00:00',),) target=(('2020',),)`
- src: `SELECT ROUND(DATE '2020-06-16', 'MONTH') AS r FROM DUAL`

## ora-seq-use  (oracle)
- targets: tsql(invalid)
- live error: `(4104, b'The multi-part identifier "s.CURRVAL" could not be bound.DB-Lib error message 200`
- src: `CREATE SEQUENCE s START WITH 1; SELECT s.NEXTVAL,s.CURRVAL FROM DUAL`

## ora-sequence-options  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'NOCYCLE'.DB-Lib error message 20018, severity 15:\nGeneral `
- src: `CREATE SEQUENCE seq START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE ORDER`

## ora-table-collection  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:`
- src: `SELECT * FROM TABLE(SYS.ODCINUMBERLIST(1,2,3))`

## ora-table-fn2  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'TABLE'.DB-Lib error message 20018, severity 15:`
- src: `SELECT t.COLUMN_VALUE FROM TABLE(SYS.ODCINUMBERLIST(1,2,3)) t`

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

## ora-todate2  (oracle)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_9fa2bcf8c36d.STR_TO_TIME does not exist')`
- src: `SELECT TO_DATE('15-JUN-20','DD-MON-YY'),TO_TIMESTAMP('2020-06-15 10:30:45.123','YYYY-MM-DD HH24:MI:SS.FF3') FROM DUAL`

## ora-translate3  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(174, b'The replace function requires 3 argument(s).DB-Lib error message 20018, severity 1`
- src: `SELECT TRANSLATE('12345', '123', 'abc'), REPLACE('aaa','a') FROM DUAL`

## ora-unpivot  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(207, b"Invalid column name 'col'.DB-Lib error message 20018, severity 16:\nGeneral SQL Se`
- src: `SELECT id,col,val FROM (SELECT 1 id,10 a,20 b FROM DUAL) UNPIVOT (val FOR col IN (a,b))`

## ora-upd-correlated  (oracle)
- targets: mysql(invalid)
- live error: `(1093, "You can't specify target table 't' for update in FROM clause")`
- src: `CREATE TABLE t (id NUMBER, n NUMBER);UPDATE t SET n=(SELECT MAX(n) FROM t x WHERE x.id<t.id)`

## ora-utl-raw  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "UTL_RAW" or the user-defined function or aggregate "UT`
- src: `SELECT UTL_RAW.CAST_TO_RAW('abc') AS r FROM DUAL`

## ora-xmlagg  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT XMLAGG(XMLELEMENT("e", dummy)) FROM DUAL`

## ora-xmlelement  (oracle)
- targets: mysql(invalid), postgresql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT XMLELEMENT("foo", 'bar') AS r FROM DUAL`

## ora-xmltable  (oracle)
- targets: postgresql(invalid), tsql(invalid)
- live error: `(208, b"Invalid object name 'dbo.X_M_L_TABLE'.DB-Lib error message 20018, severity 16:\nGe`
- src: `SELECT x.a,x.b FROM XMLTABLE('/r' PASSING XMLTYPE('<r><a>1</a><b>2</b></r>') COLUMNS a INT PATH 'a', b INT PATH 'b') x`

## ora-zero-divide  (oracle)
- targets: postgresql(invalid)
- live error: `unrecognized exception condition "zero_divide"`
- src: `CREATE PROCEDURE p AS v NUMBER; BEGIN v := 1/0; EXCEPTION WHEN ZERO_DIVIDE THEN v := 0; END;
/`

## oracle-drop2-100|START  (oracle)
- targets: postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (id NUMBER GENERATED ALWAYS AS IDENTITY (START WITH 100))`

## oracle-drop4-COLLATE  (oracle)
- targets: mysql(silent-drop), postgresql(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a VARCHAR2(10) COLLATE BINARY_CI)`

## pg-alter-add  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-30649: missing DIRECTORY keyword`
- src: `CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'`

## pg-alter-notvalid  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (id INT);
ALTER TABLE t RENAME TO tbl;
ALTER TABLE tbl ADD CONSTRAINT ck CHECK (id>0) NOT VALID;`

## pg-alter-suite  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (id INT);
ALTER TABLE t ADD COLUMN name VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE t ALTER COLUMN id TYPE BIGINT;`

## pg-alter-type  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01735: invalid ALTER TABLE option`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a TYPE BIGINT`

## pg-alter-using  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01735: invalid ALTER TABLE option`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DATA TYPE BIGINT USING a::bigint`

## pg-ascii-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('NULL',),)`
- src: `SELECT ASCII('') AS r`

## pg-at-time-zone  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D`
- src: `SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r`

## pg-avg-int  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1.5',),) target=(('1',),)`
- src: `SELECT AVG(x) FROM (VALUES (1),(2)) v(x)`

## pg-avg-null  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2.33333',),) target=(('2',),)`
- src: `SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)`

## pg-bit-negative  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('-1', '-6', '3', '5'),) target=(('18446744073709551616', '184467440737`
- src: `SELECT ~0, ~5, (-5) & 3, 5 & (-1)`

## pg-bit-prec2  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('2', '8'),) target=(('3', '5'),)`
- src: `SELECT 10 & 6 + 1, 1 << 2 + 1`

## pg-bitnot  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('-1',),) target=(('18446744073709551616',),)`
- src: `SELECT ~0 AS r`

## pg-bitops  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1', '7', '6', '-6', '10', '2'),) target=(('1', '7', '6', '18446744073`
- src: `SELECT 5 & 3, 5 | 2, 5 # 3, ~5, 5 << 1, 5 >> 1`

## pg-bool-int-cast  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01722: unable to convert string value containing 't' to a number: `
- src: `SELECT 'true'::boolean::int AS r`

## pg-bool-repr  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1', '1', 'true', '0', 'NULL'),) target=(('1', '1', '1', '0', 'NULL'),`
- src: `SELECT (1>0), (1>0)::int, (1>0)::text, NOT (1>0), true AND NULL`

## pg-bool-text2  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('true',),) target=(('1',),)`
- src: `SELECT true::text AS r`

## pg-bool-week  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(245, b"Conversion failed when converting the varchar value 't' to data type bit.DB-Lib er`
- src: `SELECT 'true'::boolean, 't'::boolean, 1::boolean, EXTRACT(WEEK FROM DATE '2020-01-01')`

## pg-case-statement  (postgresql)
- targets: tsql(invalid)
- live error: `(455, b'The last statement included within a function must be a return statement.DB-Lib er`
- src: `CREATE FUNCTION f(n INT) RETURNS TEXT AS $$ BEGIN CASE n WHEN 1 THEN RETURN 'one'; ELSE RETURN 'other'; END CASE; END; $$ LANGUAGE`

## pg-cast-bool2  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(245, b"Conversion failed when converting the varchar value 'yes' to data type bit.DB-Lib `
- src: `SELECT '1'::boolean, 'yes'::boolean, 'off'::boolean, 't'::boolean`

## pg-cast-datetime2  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT '2020-01-01 10:00'::date, '2020-01-01 10:00'::time, '10:00'::interval`

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

## pg-check-xor  (postgresql)
- targets: tsql(invalid)
- live error: `(102, b"Incorrect syntax near '<'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se`
- src: `CREATE TABLE t (a INT, b INT, c INT, CONSTRAINT ck CHECK ((a IS NULL) != (b IS NULL)))`

## pg-chr-ascii-unicode  (postgresql)
- targets: oracle(invalid)
- live error: `'utf-8' codec can't decode byte 0xe9 in position 0: unexpected end of data`
- src: `SELECT chr(233), ascii('é')`

## pg-chr-unicode  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('μ',),) target=(('NULL',),)`
- src: `SELECT CHR(956) AS r`

## pg-concat-null  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('NULL', 'ab', 'a-b'),) target=(('NULL', 'NULL', 'a-b'),)`
- src: `SELECT 'a'||NULL||'b', concat('a',NULL,'b'), concat_ws('-','a',NULL,'b')`

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

## pg-datetrunc-units  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI`
- src: `SELECT date_trunc('quarter', now()), date_trunc('decade', now())`

## pg-decimal-scale  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('3.33333', '3.33333', '3.33333', '2.25'),) target=(('3.33333', '3.3333`
- src: `SELECT 10.00/3, 10/3.0, 10::numeric(10,4)/3, 1.5*1.5`

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

## pg-empty-is-null  (postgresql)
- targets: oracle(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT '' IS NULL AS r`

## pg-epoch  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(155, b"'EPOCH' is not a recognized datepart option.DB-Lib error message 20018, severity 1`
- src: `SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01 00:00:00'), EXTRACT(EPOCH FROM INTERVAL '1 day')`

## pg-exception-handler  (postgresql)
- targets: tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql`

## pg-exception-when  (postgresql)
- targets: mysql(silent-rt), oracle(invalid), tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS void AS $$ BEGIN INSERT INTO t VALUES(1); EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'dup';`

## pg-execute-using  (postgresql)
- targets: mysql(invalid)
- live error: `(1336, 'Dynamic SQL is not allowed in stored function or trigger')`
- src: `CREATE FUNCTION f() RETURNS VOID AS $$ BEGIN EXECUTE 'INSERT INTO t VALUES ($1)' USING 5; END; $$ LANGUAGE plpgsql`

## pg-extract-dow  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(155, b"'DOW' is not a recognized datepart option.DB-Lib error message 20018, severity 15:`
- src: `SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d`

## pg-extract-epoch  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(155, b"'EPOCH' is not a recognized datepart option.DB-Lib error message 20018, severity 1`
- src: `SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01') AS r`

## pg-float-precision  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.3', '0.3', '0.333333', '0.333333', '0.666667'),) target=(('0.3', '0`
- src: `SELECT 0.1+0.2, 0.1::float+0.2::float, 1.0/3, (1.0/3)::float, 2::float/3`

## pg-fmt-spec  (postgresql)
- targets: mysql(silent), oracle(invalid), tsql(silent)
- live error: `SILENT: source literal(s) ["'Dy Mon DD HH24:MI:SS YYYY'", "'AM HH12:MI'", "'DDD WW IW'"] a`
- src: `SELECT to_char(now(),'Dy Mon DD HH24:MI:SS YYYY'),to_char(now(),'AM HH12:MI'),to_char(now(),'DDD WW IW')`

## pg-fmt3  (postgresql)
- targets: mysql(silent), oracle(invalid), tsql(silent)
- live error: `SILENT: source literal(s) ["'9G999D99'"] absent from valid output, no warning`
- src: `SELECT to_char(1234.5678,'9G999D99'),to_char(-5,'S9')`

## pg-for-update  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT); SELECT * FROM t FOR UPDATE`

## pg-format-currency  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1,234,567.89', '1,234,567.89'),) target=(('FM999999991234567.89', 'FM`
- src: `SELECT to_char(1234567.891,'FM999,999,990.00'), to_char(1234567.891,'FML999G999G990D00')`

## pg-format-func  (postgresql)
- targets: tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er`
- src: `SELECT format('%s=%s', 'a', 1) AS r`

## pg-frac-seconds  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(155, b"'MICROSECONDS' is not a recognized datepart option.DB-Lib error message 20018, sev`
- src: `SELECT TIMESTAMP '2020-01-01 10:20:30.123456', EXTRACT(MICROSECONDS FROM TIME '10:20:30.123456')`

## pg-fround  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1', '2', '3', '2.57'),) target=(('1', '2', '3', '3'),)`
- src: `SELECT round(0.5::numeric),round(1.5::numeric),round(2.5::numeric),round(2.567::numeric,2)`

## pg-gen-series-date  (postgresql)
- targets: tsql(invalid)
- live error: `(102, b"Incorrect syntax near '1 DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ`
- src: `SELECT generate_series('2020-01-01'::date, '2020-01-05'::date, '1 day') AS d`

## pg-gen-series-ord  (postgresql)
- targets: tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'ORDINALITY'.DB-Lib error message 20018, severity 15:\nGener`
- src: `SELECT * FROM generate_series(1, 10, 2) WITH ORDINALITY AS t(v, n)`

## pg-gencol2  (postgresql)
- targets: mysql(invalid)
- live error: `(1075, 'Incorrect table definition; there can be only one auto column and it must be defin`
- src: `CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a*2) STORED, c INT GENERATED ALWAYS AS IDENTITY)`

## pg-generate-series  (postgresql)
- targets: tsql(invalid)
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

## pg-hash-fns  (postgresql)
- targets: mysql(invalid)
- live error: `(195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever`
- src: `SELECT lpad('x', 3), md5('x'), sha256('x'::bytea)`

## pg-hex-literal  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00932: expression is of data type BINARY, which is incompatible with expected data typ`
- src: `SELECT x'FF'::int AS h, 1.5e3 AS s`

## pg-intdiv  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('2.5',),)`
- src: `SELECT 5 / 2 AS r`

## pg-json-aggs  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_`
- src: `SELECT json_agg(x), json_object_agg(x::text, x*2) FROM (VALUES (1),(2)) v(x)`

## pg-left-neg  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('',),)`
- src: `SELECT LEFT('abc', -1) AS r`

## pg-left-round  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('hel',),) target=(('he',),)`
- src: `SELECT LEFT('hello', 2.9::int) AS r`

## pg-log-2arg  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('0.333333',),)`
- src: `SELECT LOG(2, 8) AS r`

## pg-log-base  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('2',),) target=(('4.60517',),)`
- src: `SELECT LOG(100) AS r`

## pg-loop-notice  (postgresql)
- targets: tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'PRINT' within a function.DB-Lib error me`
- src: `CREATE FUNCTION f() RETURNS void AS $$ DECLARE i INT:=0; BEGIN LOOP i:=i+1; EXIT WHEN i>=3; END LOOP; RAISE NOTICE 'done'; END; $$`

## pg-lpad-shrink  (postgresql)
- targets: tsql(func)
- live error: `FUNC-DIFF: source=(('hel',),) target=(('llo',),)`
- src: `SELECT LPAD('hello', 3) AS r`

## pg-mod-decimal  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('3',),) target=(('2',),)`
- src: `SELECT MOD(10, 3.5::numeric) AS r`

## pg-multi-out  (postgresql)
- targets: oracle(invalid)
- live error: `FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared`
- src: `CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql`

## pg-name-locale  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('Monday', 'June', 'Monday'),) target=(('ua20', '6onA12', '6ua20'),)`
- src: `SELECT to_char(DATE '2020-06-15','Day'), to_char(DATE '2020-06-15','Month'), trim(to_char(DATE '2020-06-15','FMDay'))`

## pg-named-exception  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro`
- src: `CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1/0; EXCEPTION WHEN division_by_zero THEN RETURN -1; WHEN OTHERS THEN RAISE; EN`

## pg-named-window  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-30485: missing ORDER BY expression in the window specification`
- src: `SELECT x,sum(x) OVER w,rank() OVER w FROM (SELECT 1 x UNION ALL SELECT 2) t WINDOW w AS (ORDER BY x)`

## pg-nan-cmp  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT 'NaN'::numeric > 1 AS r`

## pg-nested-call  (postgresql)
- targets: oracle(invalid)
- live error: `PROCEDURE OUTER_P compiled INVALID (line 4): PLS-00201: identifier 'INNER_P' must be decla`
- src: `CREATE PROCEDURE outer_p() AS $$ BEGIN CALL inner_p(); END; $$ LANGUAGE plpgsql`

## pg-not-null-is-null  (postgresql)
- targets: mysql(func), oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT (NOT NULL) IS NULL AS r`

## pg-numfmt-lead  (postgresql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.5',),) target=(('0',),)`
- src: `SELECT to_char(0.5, '0.00') AS r`

## pg-numfmt-spec  (postgresql)
- targets: mysql(silent), oracle(invalid), tsql(silent)
- live error: `SILENT: source literal(s) ["'L9G999D99MI'"] absent from valid output, no warning`
- src: `SELECT to_char(1234.5,'L9G999D99MI'),to_char(-5,'999PR'),to_char(255,'FMRN')`

## pg-numfmt-thousands  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1,234,567.89',),) target=(('9999999123456900',),)`
- src: `SELECT to_char(1234567.891, '9,999,999.99') AS r`

## pg-numtypes  (postgresql)
- targets: mysql(invalid)
- live error: `(1075, 'Incorrect table definition; there can be only one auto column and it must be defin`
- src: `CREATE TABLE t (a SMALLINT, b INT, c BIGINT, d NUMERIC(10,2), e REAL, f DOUBLE PRECISION, g SERIAL, h MONEY)`

## pg-order-case-sens  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('Apple',), ('Cherry',), ('banana',)) target=(('Apple',), ('banana',), `
- src: `SELECT x FROM (SELECT 'Apple' x UNION SELECT 'banana' UNION SELECT 'Cherry') t ORDER BY x`

## pg-order-nulls-default  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))`
- src: `SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x`

## pg-overlay  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV`
- src: `SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o`

## pg-pad-repeat  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00904: "REPEAT": invalid identifier`
- src: `SELECT lpad('7',3,'0'),rpad('7',3,'x'),repeat('ab',3),reverse('abc'),repeat(' ',3)`

## pg-pi-fns  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00904: "PI": invalid identifier`
- src: `SELECT trunc(pi()::numeric, 4), round(pi()::numeric, 4)`

## pg-position-case  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('0',),) target=(('1',),)`
- src: `SELECT POSITION('a' IN 'ABC') AS r`

## pg-position-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT POSITION('' IN 'abc') AS r`

## pg-regexp-backref  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-01722: unable to convert string value containing 'g' to a number: `
- src: `SELECT regexp_replace('a1b2', '(\d)', '[\1]', 'g') AS r`

## pg-rollup  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8120, b"Column 'v.x' is invalid in the select list because it is not contained in either `
- src: `SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)`

## pg-rollup2  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(8120, b"Column 't.a' is invalid in the select list because it is not contained in either `
- src: `SELECT a,b,sum(c) FROM (SELECT 1 a,2 b,3 c) t GROUP BY ROLLUP(a,b)`

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

## pg-select-into-ctas  (postgresql)
- targets: oracle(invalid)
- live error: `ORA-00905: missing keyword`
- src: `CREATE TABLE t (id INT);
SELECT id INTO TEMP t2 FROM t;
CREATE TABLE t3 AS SELECT * FROM t;`

## pg-set-default  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n`
- src: `CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5`

## pg-srf-in-select  (postgresql)
- targets: tsql(invalid)
- live error: `(208, b"Invalid object name 'dbo.GENERATE_SERIES'.DB-Lib error message 20018, severity 16:`
- src: `SELECT g, g*g FROM generate_series(1,3) g`

## pg-stragg-order  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT string_agg(x::text,',' ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2) t`

## pg-string-agg-order  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message`
- src: `SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)`

## pg-strpos-empty  (postgresql)
- targets: oracle(func), tsql(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('0',),)`
- src: `SELECT STRPOS('', '') AS r`

## pg-substr-zero  (postgresql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('abc',),)`
- src: `SELECT SUBSTRING('abcdef', 0, 3) AS r`

## pg-substring-escape  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib`
- src: `SELECT substring('a1b2' from '([a-z])([0-9])' for '#') AS r`

## pg-substring-regex  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib`
- src: `SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r`

## pg-tablesample  (postgresql)
- targets: mysql(invalid)
- live error: `(1192, "Can't execute the given command because you have active locked tables or an active`
- src: `CREATE TABLE t (id INT); SELECT * FROM t TABLESAMPLE BERNOULLI(50)`

## pg-tochar-fmts  (postgresql)
- targets: mysql(silent), oracle(invalid), tsql(silent)
- live error: `SILENT: source literal(s) ["'Day'", "'FMDay'", "'TZ'"] absent from valid output, no warnin`
- src: `SELECT to_char(now(),'Day'), to_char(now(),'FMDay'), to_char(now(),'IW'), to_char(now(),'TZ')`

## pg-tochar-iso  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(8116, b'Argument data type timestamp is invalid for argument 1 of format function.DB-Lib `
- src: `SELECT to_char(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r`

## pg-tochar-neg  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('-1234.5',),) target=(('-9999123599',),)`
- src: `SELECT to_char(-1234.5, '9999.99') AS r`

## pg-todate2  (postgresql)
- targets: mysql(invalid)
- live error: `(1305, 'FUNCTION unique_val_2ac6422f99c6.STR_TO_TIME does not exist')`
- src: `SELECT to_date('06/15/2020','MM/DD/YYYY'),to_timestamp('2020-06-15 10:30','YYYY-MM-DD HH24:MI')`

## pg-tohex2  (postgresql)
- targets: oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE`
- src: `SELECT to_hex(255), to_char(255, 'XX')`

## pg-totimestamp-long  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST`
- src: `SELECT to_timestamp('June 15 2020', 'Month DD YYYY') AS r`

## pg-truncate-restart  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(102, b"Incorrect syntax near 'RESTART'.DB-Lib error message 20018, severity 15:\nGeneral `
- src: `CREATE TABLE t (id INT); TRUNCATE TABLE t RESTART IDENTITY CASCADE`

## pg-unique-nulls-notdistinct  (postgresql)
- targets: mysql(invalid), oracle(invalid)
- live error: `ORA-03050: invalid identifier: "UNIQUE" is a reserved word`
- src: `CREATE TABLE t (a INT, b INT, UNIQUE NULLS NOT DISTINCT (a, b))`

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

## pg-xmlelement  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT XMLELEMENT(NAME foo, 'bar') AS r`

## pg-xmlelement2  (postgresql)
- targets: mysql(invalid), tsql(invalid)
- live error: `(195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018`
- src: `SELECT xmlelement(name foo, 'bar')`

## po-agg-bit  (postgresql)
- targets: mysql(invalid), oracle(invalid), tsql(invalid)
- live error: `(4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI`
- src: `SELECT BIT_AND(x),BIT_OR(x),BIT_XOR(x) FROM (VALUES (3),(5),(6)) v(x)`

## po-distinct-case  (postgresql)
- targets: mysql(func), tsql(func)
- live error: `FUNC-DIFF: source=(('A',), ('B',), ('a',)) target=(('A',), ('B',))`
- src: `SELECT DISTINCT x FROM (VALUES ('a'),('A'),('a'),('B')) v(x) ORDER BY x`

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

## postgresql-drop5-CHECK|IN\s*\  (postgresql)
- targets: mysql(silent-drop), oracle(silent-drop), tsql(silent-drop)
- live error: `SILENT CLAUSE DROP: 'CHECK|IN\s*\(' absent from valid tsql output, no warning`
- src: `CREATE TABLE t (a INT CHECK (a IN (1,2,3)))`

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

## ts-at-time-zone  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST('2020-01-01 10:00' AS DATETIME2) AT TIME ZONE 'UTC' AS r`

## ts-binary-length  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT DATALENGTH(CAST('hello' AS VARBINARY(MAX))) AS r`

## ts-bit-cast  (tsql)
- targets: oracle(invalid)
- live error: `ORA-01722: unable to convert string value containing 't' to a number: `
- src: `SELECT CAST(1 AS BIT), CAST('true' AS BIT), CAST(0 AS BIT)`

## ts-bit-fns  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SET_BIT": invalid identifier`
- src: `SELECT GET_BIT(0x0A, 1), SET_BIT(0x0A, 0, 1)`

## ts-bitops  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('1', '7', '6', '-6'),) target=(('1', '7', '6', '18446744073709551616')`
- src: `SELECT 5 & 3, 5 | 2, 5 ^ 3, ~5`

## ts-cast-bit  (tsql)
- targets: mysql(func), oracle(func)
- live error: `FUNC-DIFF: source=(('1',),) target=(('2',),)`
- src: `SELECT CAST(2 AS BIT) AS r`

## ts-cast-bit2  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01722: unable to convert string value containing 't' to a number: `
- src: `SELECT CAST(1 AS BIT), CAST('true' AS BIT), CAST(0.5 AS BIT), TRY_CAST('x' AS BIT)`

## ts-cast-int-datetime  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00932: expression is of data type NUMBER, which is incompatible with expected data typ`
- src: `SELECT CAST(1 AS DATETIME) AS r`

## ts-cast-money  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00902: invalid datatype`
- src: `SELECT CAST(12.99 AS MONEY), CAST(12.99 AS SMALLMONEY), CONVERT(MONEY, '$12.99')`

## ts-concat-null  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('ab',),) target=(('NULL',),)`
- src: `SELECT CONCAT('a', NULL, 'b') AS r`

## ts-continue-break  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 6): PLS-00103: Encountered the symbol "=" when expectin`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE @i INT=1; WHILE @i<=3 BEGIN SET @i+=1; IF @i=2 CONTINUE; IF @i=5 BREAK; END; END`

## ts-cube  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00937: not a single-group group function`
- src: `SELECT a,b,SUM(c) FROM (SELECT 1 a,2 b,3 c) t GROUP BY CUBE(a,b)`

## ts-cursor-attr  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE P compiled INVALID (line 6): PLS-00103: Encountered the symbol ";" when expectin`
- src: `CREATE PROCEDURE p AS BEGIN DECLARE c CURSOR FOR SELECT 1; OPEN c; FETCH NEXT FROM c; IF @@FETCH_STATUS=0 PRINT CAST(@@CURSOR_ROWS`

## ts-dateadd  (tsql)
- targets: mysql(func), oracle(invalid), postgresql(invalid)
- live error: `FUNC-DIFF: source=(('2020-02-29 00:00:00', '2020-01-02 00:00:00', '2020-02-29'),) target=(`
- src: `SELECT DATEADD(MONTH,1,'2020-01-31'), DATEADD(DAY,1,'2020-01-01'), EOMONTH('2020-02-15')`

## ts-decimal-scale  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('3.33333', '3.33333', '3.33333', '2.25'),) target=(('3.33333', '3.3333`
- src: `SELECT 10.00/3, 10/3.0, CAST(10 AS DECIMAL(10,4))/3, 1.5*1.5`

## ts-eomonth  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT EOMONTH('2020-02-15') AS r`

## ts-eomonth-nested  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01861: literal does not match format string`
- src: `SELECT DATEADD(MONTH, -1, EOMONTH('2020-03-01')) AS r`

## ts-float-precision  (tsql)
- targets: mysql(func)
- live error: `FUNC-DIFF: source=(('0.3', '0.3', '0.333333', '0.333333'),) target=(('0.3', '0.3', '0.3333`
- src: `SELECT 0.1+0.2, CAST(0.1 AS FLOAT)+CAST(0.2 AS FLOAT), 1.0/3, CAST(1 AS FLOAT)/3`

## ts-fmt-spec  (tsql)
- targets: mysql(silent), oracle(invalid), postgresql(silent)
- live error: `ORA-01821: date format not recognized`
- src: `SELECT FORMAT(GETDATE(),'ddd MMM dd HH:mm:ss yyyy'),FORMAT(GETDATE(),'tt hh:mm'),FORMAT(GETDATE(),'D')`

## ts-for-xml  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00913: too many values`
- src: `SELECT (SELECT 1 a,2 b FOR XML PATH('row'),ROOT('rows')) AS xmlcol`

## ts-format-iso  (tsql)
- targets: mysql(silent), oracle(invalid), postgresql(silent)
- live error: `ORA-01821: date format not recognized`
- src: `SELECT FORMAT(CAST('2020-06-15 14:30:45' AS DATETIME2), 'yyyy-MM-ddTHH:mm:ss') AS r`

## ts-format-number  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "NUMBER_TO_STR": invalid identifier`
- src: `SELECT FORMAT(1234.5, 'N2') AS r`

## ts-frac-seconds  (tsql)
- targets: oracle(invalid)
- live error: `ORA-01843: An invalid month was specified.`
- src: `SELECT CAST('2020-01-01 10:20:30.1234567' AS DATETIME2), CAST('2020-01-01 10:20:30.123' AS DATETIME)`

## ts-gen-series-apply  (tsql)
- targets: postgresql(invalid)
- live error: `ORA-00904: "GENERATE_SERIES": invalid identifier`
- src: `SELECT value, ordinal FROM GENERATE_SERIES(1, 5) g CROSS APPLY (SELECT g.value AS ordinal) x`

## ts-generate-series  (tsql)
- targets: postgresql(invalid)
- live error: `ORA-00904: "GENERATE_SERIES": invalid identifier`
- src: `SELECT value FROM GENERATE_SERIES(1,5)`

## ts-geography  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "GEOGRAPHY"."TOSTRING": invalid identifier`
- src: `SELECT GEOGRAPHY::Point(47.6, -122.3, 4326).ToString() AS r`

## ts-hash-all  (tsql)
- targets: oracle(silent)
- live error: `SILENT: source literal(s) ["'SHA2_512'"] absent from valid output, no warning`
- src: `SELECT HASHBYTES('SHA2_512', 'abc'), CHECKSUM('abc')`

## ts-identity-funcs  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT SCOPE_IDENTITY(), @@IDENTITY, IDENT_CURRENT('t')`

## ts-insert-output  (tsql)
- targets: oracle(invalid)
- live error: `ORA-63809: returning clause is not allowed with INSERT and Table Value Constructor`
- src: `CREATE TABLE t (id INT IDENTITY, n INT);
GO
INSERT INTO t (n) OUTPUT INSERTED.id,INSERTED.n VALUES (10),(20)`

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

## ts-maxrecursion  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-32039: missing column alias list in recursive WITH clause element S`
- src: `WITH s AS (SELECT 1 n UNION ALL SELECT n+1 FROM s WHERE n<5) SELECT n FROM s OPTION (MAXRECURSION 10)`

## ts-merge-full  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-02000: missing THEN keyword`
- src: `CREATE TABLE tgt (id INT PRIMARY KEY, n INT); CREATE TABLE src (id INT, n INT);
GO
MERGE tgt USING src ON tgt.id = src.id WHEN MAT`

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

## ts-now-fns  (tsql)
- targets: mysql(invalid)
- live error: `ORA-00904: "CURRENT_TIMESTAMP_L_T_Z": invalid identifier`
- src: `SELECT GETDATE(), SYSDATETIME(), CURRENT_TIMESTAMP, GETUTCDATE(), SYSDATETIMEOFFSET()`

## ts-openjson  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "OPEN_J_S_O_N": invalid identifier`
- src: `SELECT * FROM OPENJSON('[1,2,3]')`

## ts-realworld-audit  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `PROCEDURE LOG_IT compiled INVALID (line 11): PLS-00103: Encountered the symbol ")" when ex`
- src: `CREATE TABLE dbo.audit (id INT IDENTITY, msg NVARCHAR(MAX), ts DATETIME2);
GO
CREATE PROCEDURE dbo.log_it @msg NVARCHAR(MAX) AS BE`

## ts-recursion-limit  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-32039: missing column alias list in recursive WITH clause element N`
- src: `WITH n AS (SELECT 1 v UNION ALL SELECT v+1 FROM n WHERE v<100) SELECT COUNT(*) FROM n OPTION (MAXRECURSION 1000)`

## ts-recursive-cte  (tsql)
- targets: mysql(invalid), postgresql(invalid)
- live error: `relation "r" does not exist`
- src: `WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r`

## ts-replicate-space  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "SPACE": invalid identifier`
- src: `SELECT REPLICATE('ab', 3), SPACE(5), REVERSE('abc')`

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

## ts-select-into-temp  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00905: missing keyword`
- src: `SELECT id INTO #t2 FROM (SELECT 1 id) s;
SELECT * FROM #t2;`

## ts-spatial  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `DPY-4010: a bind variable replacement value for placeholder ":POINT" was not provided`
- src: `SELECT geometry::Point(0,0,0).STDistance(geometry::Point(3,4,0)), geography::Point(47,-122,4326).ToString()`

## ts-spid-version  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00936: missing expression`
- src: `SELECT @@SPID, @@VERSION`

## ts-st-distance  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `DPY-4010: a bind variable replacement value for placeholder ":POINT" was not provided`
- src: `SELECT geometry::Point(0,0,0).STDistance(geometry::Point(3,4,0)) AS r`

## ts-str-plus-num  (tsql)
- targets: mysql(func), oracle(func), postgresql(func)
- live error: `FUNC-DIFF: source=(('15',),) target=(('105',),)`
- src: `SELECT '10' + 5 AS r`

## ts-stuff  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "STUFF": invalid identifier`
- src: `SELECT STUFF('abcdef', 2, 3, 'XY') AS r`

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

## ts-trg-instead-delete  (tsql)
- targets: postgresql(invalid)
- live error: `"t" is a table`
- src: `CREATE TABLE t (id INT);
GO
CREATE TRIGGER g ON t INSTEAD OF DELETE AS BEGIN DELETE FROM t WHERE id IN (SELECT id FROM deleted WHE`

## ts-trig  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00904: "COT": invalid identifier`
- src: `SELECT ATN2(1,1), DEGREES(PI()), RADIANS(180.0), COT(1)`

## ts-trigger-on-view  (tsql)
- targets: postgresql(invalid)
- live error: `INSTEAD OF triggers must be FOR EACH ROW`
- src: `CREATE TABLE t (id INT);
GO
CREATE VIEW v AS SELECT id FROM t;
GO
CREATE TRIGGER trg ON v INSTEAD OF INSERT AS BEGIN INSERT INTO t`

## ts-try-convert  (tsql)
- targets: oracle(invalid), postgresql(invalid)
- live error: `ORA-01722: unable to convert string value containing 'a' to a number: `
- src: `SELECT TRY_CONVERT(INT, 'abc') AS r`

## ts-tzoffset  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "CURRENT_TIMESTAMP_L_T_Z": invalid identifier`
- src: `SELECT DATENAME(TZOFFSET, SYSDATETIMEOFFSET()) AS r`

## ts-unpivot  (tsql)
- targets: mysql(invalid), oracle(invalid), postgresql(invalid)
- live error: `ORA-00904: "VAL": invalid identifier`
- src: `SELECT id,col,val FROM (SELECT 1 id,10 a,20 b) s UNPIVOT (val FOR col IN (a,b)) u`

## ts-update-output  (tsql)
- targets: oracle(invalid)
- live error: `ORA-00925: missing INTO keyword`
- src: `CREATE TABLE t (id INT);
GO
CREATE INDEX ix ON t (id);
GO
UPDATE t SET id = id + 1 OUTPUT DELETED.id, INSERTED.id`

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

Totals: 862 distinct constructs; defect rows by kind: func 401, invalid 1322, semantic 2, silent-drop 75.
