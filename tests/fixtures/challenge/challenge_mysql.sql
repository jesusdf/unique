-- Challenge fixtures — MySQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[limit]: my-accent-eq — fails on oracle, postgresql, tsql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'Ä' = 'A' AS r

-- CASE[fixed]: my-adddate — fails on tsql. FUNC-DIFF: source=(('2020-01-31',),) target=(('2020-01-31 00:00:00',),)
SELECT ADDDATE('2020-01-01', 30) AS r

-- CASE[fixed]: my-aes — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(AES_ENCRYPT('data', 'key')) AS r

-- CASE[limit]: my-agg-bit — fails on oracle, tsql. BIT_AND/BIT_OR/BIT_XOR are aggregates on MySQL & PostgreSQL (transpiled faithfully, value-verified) but Oracle and T-SQL have no bit-aggregate function (docs/03-unsupported.md §3.10). Warned carrier on oracle/tsql.
SELECT BIT_AND(x),BIT_OR(x),BIT_XOR(x) FROM (SELECT 3 x UNION ALL SELECT 5 x UNION ALL SELECT 6 x) t

-- CASE[fixed]: my-agg-boolean — AVG of a boolean predicate is value-equal across engines; MySQL prints 4 decimals (0.6667), Oracle 6 (0.666667) — precision-only (maintainer policy). SUM/COUNT/MAX match; output valid, no gate.
SELECT SUM(x>1), COUNT(x>1), AVG(x>1), MAX(x>1) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 3) t

-- CASE[limit]: my-agg-collect — JSON_ARRAYAGG maps to PostgreSQL json_agg (works, live-verified [1,2]); T-SQL has no JSON aggregate, so its output degrades to a carrier + warning (docs/03-unsupported.md). fails on tsql
SELECT GROUP_CONCAT(x),JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[fixed]: my-alter-drop-default — ALTER COLUMN a DROP DEFAULT maps to Oracle MODIFY a DEFAULT NULL and T-SQL dynamic drop of the (named) default constraint via sys.default_constraints (a no-op when none). live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP DEFAULT

-- CASE[fixed]: my-alter-modify — MySQL ALTER TABLE … MODIFY COLUMN c <type> maps to Oracle MODIFY c, PostgreSQL ALTER COLUMN c TYPE, T-SQL ALTER COLUMN c (with the type ported). live-verified DDL runs on all three.
CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT

-- CASE[fixed]: my-alter-set-default — MySQL ALTER COLUMN a SET DEFAULT v maps to Oracle MODIFY a DEFAULT v and T-SQL ADD CONSTRAINT DF_t_a DEFAULT v FOR a (named default constraint). live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5

-- CASE[limit]: my-any-value — ANY_VALUE + GROUP_CONCAT map to PostgreSQL (ANY_VALUE is native in PG16+, GROUP_CONCAT->STRING_AGG; works, live-verified (1,'1,2')); T-SQL has no ANY_VALUE, so its output degrades to a carrier + warning (docs/03-unsupported.md). fails on tsql
SELECT ANY_VALUE(x), GROUP_CONCAT(x) FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x>0

-- CASE[fixed]: my-arr-json — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAY(1,2,3),JSON_ARRAY_APPEND('[1]','$',2),JSON_ARRAY_INSERT('[1,2]','$[0]',0)

-- CASE[fixed]: my-ascii-empty — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT ASCII('') AS r

-- CASE[fixed]: my-avg-int — T-SQL AVG returns the input type (integer -> truncates to 1); MySQL/Oracle/PG average as decimal. Promote arg (AVG((x)*1.0)) -> 1.5.
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[fixed]: my-avg-precision2 — AVG = 5/3 = 1.6667; T-SQL AVG(int) truncation fixed by arg promotion, remainder is engine decimal precision (value equal; maintainer policy 2026-07-19).
SELECT AVG(x) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 2) t

-- CASE[fixed]: my-base64 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TO
SELECT TO_BASE64('abc'), FROM_BASE64('YWJj')

-- CASE[fixed]: my-baseconv — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIN(255),OCT(255),HEX(255),CONV(255,10,36)

-- CASE[fixed]: my-benchmark — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BE
SELECT BENCHMARK(1, 1+1) AS r

-- CASE[fixed]: my-binary-substr — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT SUBSTRING(UNHEX('48656C6C6F'), 1, 2) AS r

-- CASE[fixed]: my-bintypes — MySQL BIT(M) maps to T-SQL BIT with no width (error 2716 otherwise), consistent with Oracle NUMBER(1) / PG BOOLEAN treating BIT as a boolean; the BLOB family maps to VARBINARY(MAX). live-verified CREATE runs.
CREATE TABLE t (a BINARY(16), b VARBINARY(255), c TINYBLOB, d BLOB, e MEDIUMBLOB, f LONGBLOB, g BIT(8), h BOOL)

-- CASE[limit]: my-bit-agg — fails on oracle, tsql. BIT_XOR/BIT_OR aggregates map faithfully MySQL<->PostgreSQL; Oracle/T-SQL have no bit aggregate (docs/03-unsupported.md §3.10). Warned carrier on oracle/tsql.
SELECT BIT_XOR(x), BIT_OR(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[limit]: my-bit-char-len — fails on postgresql. APPROVED LIMIT (2026-07-18): LENGTH/BIT_LENGTH byte-vs-char, encoding-dependent (docs/03-unsupported.md §2). FUNC-DIFF: source=(('24', '1', '3'),) target=(('24', '1', '1'),)
SELECT BIT_LENGTH('€'), CHAR_LENGTH('€'), LENGTH('€')

-- CASE[limit]: my-bit-count — BIT_COUNT (population count) has no cross-engine builtin; gated + annotated (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT BIT_COUNT(255) AS r

-- CASE[limit]: my-bit-fns — BIT_COUNT (population count) has no cross-engine builtin; gated + annotated (docs/03-unsupported.md). fails on postgresql
SELECT BIT_COUNT(b'1011'), BIT_LENGTH('a'), OCTET_LENGTH('ab')

-- CASE[limit]: my-bit-negative — fails on oracle, postgresql, tsql. MySQL treats bitwise operands as unsigned 64-bit, so ~ and negative-operand bit ops diverge from signed engines. No faithful mapping (docs/03-unsupported.md).
SELECT ~0, ~5, -5 & 3, -1 >> 1, 5 & -1

-- CASE[fixed]: my-bit-prec2 — MySQL/Oracle bind a bitwise operator LOOSER than +/*, but PostgreSQL/T-SQL bind it tighter, so the source grouping (10 & (6+1)) is now parenthesized explicitly on emit. live-verified (2,14,8).
SELECT 10 & 6 + 1, 10 | 2 * 3, 1 << 2 + 1

-- CASE[fixed]: my-bitand-prec — MySQL/Oracle bind a bitwise operator LOOSER than +/*, but PostgreSQL/T-SQL bind it tighter, so the source grouping (10 & (6+1)) is now parenthesized explicitly on emit. live-verified 2.
SELECT 10 & 6 + 1 AS r

-- CASE[limit]: my-bitnot — fails on oracle, postgresql, tsql. MySQL bitwise NOT is unsigned 64-bit (~0=18446744073709551615); other engines are signed (-1). No faithful unsigned-64 type (docs/03-unsupported.md).
SELECT ~0 AS r

-- CASE[limit]: my-bitnot-arith — fails on oracle, postgresql, tsql. MySQL bitwise ops are unsigned 64-bit, so ~5+1 overflows into a big unsigned value vs a signed -5 elsewhere. No faithful unsigned-64 mapping (docs/03-unsupported.md).
SELECT ~5 + 1 AS r

-- CASE[limit]: my-bitops — fails on oracle, postgresql, tsql. MySQL bitwise NOT/shift are unsigned 64-bit (~5=18446744073709551610); other engines signed. The high-bit results diverge (docs/03-unsupported.md).
SELECT 5 & 3, 5 | 2, 5 ^ 3, ~5, 5 << 1, 5 >> 1

-- CASE[fixed]: my-blob-length — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
CREATE TABLE t (data BLOB); INSERT INTO t VALUES (LOAD_FILE('/x')); SELECT LENGTH(data) FROM t

-- CASE[fixed]: my-bool-char — fails on postgresql. FUNC-DIFF: source=(('1',),) target=(('t',),)
SELECT CAST((1=1) AS CHAR) AS r

-- CASE[fixed]: my-cast-binary2 — CAST AS BINARY/VARBINARY maps to PG BYTEA (PG has no BINARY type). Live-verified (b'abc', 'abc', b'abc').
SELECT CONVERT('abc',BINARY), CONVERT('abc' USING latin1), CAST('abc' AS BINARY)

-- CASE[open]: my-cast-charset — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(0xC3A9 AS CHAR CHARACTER SET utf8mb4) AS r

-- CASE[limit]: my-cast-convert — CAST AS UNSIGNED has no signed-engine type; mapped to NUMERIC/NUMBER (value 1 exact) with a carrier flagging the lost unsigned wraparound (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)

-- CASE[fixed]: my-cast-datetime — CAST('2020-01-01' AS DATETIME) -> Oracle can't cast an ISO string to TIMESTAMP (ORA-01843); emit the ANSI DATE/TIMESTAMP literal (the Oracle-literal path now covers the DATETIME* type names too). live-verified 2020-01-01.
SELECT CAST('2020-01-01' AS DATETIME) AS r

-- CASE[limit]: my-cast-datetime2 — the CAST(... AS TIME) part has no Oracle type; kept as text with a documented carrier (docs/03-unsupported.md). fails on oracle
SELECT CAST('2020-01-01 10:00' AS DATE), CAST('2020-01-01 10:00' AS TIME), CAST('2020-01-01 10:00' AS DATETIME)

-- CASE[fixed]: my-cast-decimal2 — MySQL's lenient string->number cast (CAST('abc' AS DECIMAL)=0, leading-numeric-prefix parse) reproduced by folding the literal to its MySQL-parsed value; bare DECIMAL kept as DECIMAL(10,0) (MySQL's default scale 0); values 13/13/0 verified equal (Oracle drops a trailing .0 — precision only)
SELECT CAST('12.99' AS DECIMAL(4,1)), CAST('12.99' AS DECIMAL(3,0)), CAST('abc' AS DECIMAL)

-- CASE[open]: my-cast-hex-char — fails on oracle. ORA-25137: Data value out of range
SELECT CAST(0xFF AS CHAR) AS r

-- CASE[fixed]: my-cast-int — MySQL CAST(2.7 AS SIGNED) rounds (3); T-SQL CAST truncates (2). Wrap ROUND(x, 0) on a T-SQL target (both round half-away-from-zero).
SELECT CAST(2.7 AS SIGNED) AS r

-- CASE[limit]: my-cast-json — MySQL's JSON type has no faithful cross-engine cast (T-SQL has no JSON type at all; MySQL's canonical JSON spacing '[1, 2]' differs from PG/Oracle), so a CAST to JSON keeps the value as text + annotation (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT CAST(1 AS JSON), CAST('[1,2]' AS JSON), CAST(NULL AS JSON)

-- CASE[fixed]: my-cast-matrix — CAST AS DOUBLE maps to PG DOUBLE PRECISION / Oracle BINARY_DOUBLE (bare DOUBLE is an invalid type name). Live-verified (3.14, 3, '3.14', 3.14).
SELECT CAST(3.14 AS DECIMAL(10,2)), CAST(3.14 AS SIGNED), CAST(3.14 AS CHAR), CAST(3.14 AS DOUBLE)

-- CASE[fixed]: my-cast-num-char — MySQL CAST(x AS CHAR) (no length) is a to-string conversion; a bare CHAR is length-required elsewhere (Oracle ORA-25137). Map to VARCHAR2(4000)/TEXT/VARCHAR(MAX). live-verified 1234.5.
SELECT CAST(1234.5 AS CHAR) AS r

-- CASE[fixed]: my-cast-suite — MySQL SIGNED/CONVERT(,SIGNED) map to CAST(AS INTEGER); DECIMAL/DATE/CHAR map to NUMBER/DATE/VARCHAR2 on Oracle (DECIMAL prints 1.5 vs 1.50, precision-only). live-verified 123, 1.5, 123, 2020-01-01, 65.
SELECT CAST('123' AS SIGNED),CAST('1.5' AS DECIMAL(4,2)),CONVERT('123',SIGNED),CAST('2020-01-01' AS DATE),CAST(65 AS CHAR)

-- CASE[limit]: my-cast-time — Oracle has no TIME type; CAST(... AS TIME) keeps the value as text with a documented carrier (docs/03-unsupported.md). fails on oracle
SELECT CAST('10:00:00' AS TIME) AS r

-- CASE[open]: my-cast-truncate — fails on oracle, tsql. (243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity
SELECT CAST(TIMESTAMP '2020-01-01 10:30' AS DATE), CAST(TIME '10:30:45' AS CHAR)

-- CASE[open]: my-cast-uns2 — fails on postgresql. type "ubigint" does not exist
SELECT CAST(0xFFFF AS UNSIGNED), CAST(b'1111' AS UNSIGNED), CAST(TRUE AS UNSIGNED)

-- CASE[fixed]: my-cast-year — MySQL YEAR type has no cross-engine equivalent; fold a literal to its integer year with MySQL's 2-digit century rule (00-69->2000s, 70-99->1900s). live-verified 2020,2020,1999.
SELECT CAST('2020' AS YEAR), CAST(2020 AS YEAR), CAST('99' AS YEAR)

-- CASE[fixed]: my-change-column — MySQL ALTER TABLE t CHANGE a x <type> (rename + retype) splits into a RENAME COLUMN + a type change per engine (T-SQL uses EXEC sp_rename). live-verified DDL runs on all three.
CREATE TABLE t (a INT, b INT); ALTER TABLE t CHANGE a x INT

-- CASE[limit]: my-char-256 — MySQL CHAR(n) is byte-based (CHAR(256) = the 2-byte string 0x0100), not a single code point like CHR; carrier + warning (docs/03-unsupported.md). fails on oracle, postgresql
SELECT CHAR(256) AS r

-- CASE[fixed]: my-char-encoding — fails on oracle, postgresql, tsql. (195, b"'CHR' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT ASCII('A'),CHAR(65),ORD('é'),HEX('AB'),UNHEX('4142'),TO_BASE64('AB'),FROM_BASE64('QUI='),BIT_LENGTH('AB')

-- CASE[open]: my-char-unicode — fails on postgresql. FUNC-DIFF: source=(('NULL',),) target=(('μ',),)
SELECT CHAR(956 USING utf8mb4) AS r

-- CASE[fixed]: my-char-unicode2 — fails on oracle, postgresql, tsql. (195, b"'CHR' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT CHAR(0x41,0x42 USING utf8mb4),ORD('中')

-- CASE[fixed]: my-check-enforced — MySQL's ENFORCED is the default (the CHECK is validated), so the keyword is stripped for every other engine (identical semantics); NOT ENFORCED would keep a carrier. live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) ENFORCED

-- CASE[limit]: my-coalesce-empty — fails on oracle. Oracle stores '' as NULL (docs/03-unsupported.md). FUNC-DIFF: source=(('1',),) target=(('NULL',),)
SELECT COALESCE(NULL, 0) = '' AS r

-- CASE[fixed]: my-coalesce-single — a single-argument COALESCE(x) is its argument; Oracle (ORA-00938) and T-SQL reject a 1-arg COALESCE, so reduce it to the argument.
SELECT COALESCE(x) FROM (SELECT NULL x) t

-- CASE[limit]: my-collation-fn — COLLATION(x) returns engine-specific collation names (MySQL utf8mb4_0900_ai_ci vs Oracle USING_NLS_COMP); the function exists on both but can't match — carrier + warning (docs/03-unsupported.md). fails on oracle
SELECT COLLATION('abc') AS r

-- CASE[fixed]: my-compress — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT UNCOMPRESS(COMPRESS('data')) AS r

-- CASE[fixed]: my-compress2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UN
SELECT COMPRESS('x'), UNCOMPRESSED_LENGTH(COMPRESS('x'))

-- CASE[fixed]: my-computed-json — fails on postgresql, tsql. (195, b"'JSON_UNQUOTE' is not a recognized built-in function name.DB-Lib error message 200
CREATE TABLE t (data JSON, name VARCHAR(50) AS (JSON_UNQUOTE(JSON_EXTRACT(data, '$.name'))) VIRTUAL)

-- CASE[fixed]: my-concat-bool — fails on postgresql. FUNC-DIFF: source=(('10',),) target=(('tf',),)
SELECT CONCAT(TRUE, FALSE) AS r

-- CASE[fixed]: my-concat-date — Oracle renders a DATE in CONCAT via NLS_DATE_FORMAT ('01-JAN-20'); a DATE-valued CONCAT arg is now wrapped in TO_CHAR(d,'YYYY-MM-DD') to match MySQL's ISO. live-verified 2020-01-01.
SELECT CONCAT(DATE '2020-01-01', '') AS r

-- CASE[fixed]: my-concat-null — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('ab',),)
SELECT CONCAT('a', NULL, 'b') AS r

-- CASE[fixed]: my-concat-null3 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL', 'a,b'),) target=(('a', 'a,b'),)
SELECT CONCAT('a',NULL), CONCAT_WS(',','a',NULL,'b')

-- CASE[fixed]: my-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r

-- CASE[fixed]: my-concatws3 — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', a, b) FROM (SELECT 'x' a, 'y' b) t

-- CASE[fixed]: my-conv2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT CONV('7F', 16, 2), CONV(255, 10, 16)

-- CASE[fixed]: my-convert-signed — MySQL CONVERT(x, SIGNED) maps to CAST(x AS INTEGER) on Oracle. live-verified 123.
SELECT CONVERT('123', SIGNED) AS r

-- CASE[limit]: my-convert-tz — CONVERT_TZ has no uniform cross-engine form (Oracle needs format-aware parsing + FROM_TZ, T-SQL AT TIME ZONE takes named Windows zones not offsets, and the result type/format differ); it gates + annotates on every target (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT CONVERT_TZ('2020-01-01 10:00', '+00:00', '+02:00') AS r

-- CASE[fixed]: my-convert-using2 — MySQL CONVERT(x USING charset) is a charset conversion that leaves the value unchanged; mapped to an unbounded string cast (VARCHAR2(4000)/TEXT/VARCHAR(8000)), since a bare CAST AS CHAR wrongly truncated to CHAR(1) -> '2'. live-verified 2020-06-15 14:30.
SELECT CONVERT('2020-06-15 14:30' USING utf8mb4) AS r

-- CASE[fixed]: my-crc32 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR
SELECT CRC32('abc') AS r

-- CASE[fixed]: my-crypto2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FR
SELECT FROM_BASE64(TO_BASE64('hello')),HEX(AES_DECRYPT(AES_ENCRYPT('d','k'),'k'))

-- CASE[fixed]: my-date-add-interval — qualify the bare date string as DATE so PG/Oracle interval arithmetic runs (2020-01-08; midnight on the datetime-typed targets).
SELECT DATE_ADD('2020-01-01', INTERVAL 7 DAY) AS r

-- CASE[fixed]: my-date-add-month — fails on tsql. FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)
SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[limit]: my-date-diff-minus — MySQL DATE - DATE is a numeric YYYYMMDD subtraction (200), not a day count; the meaningful day count (60) is emitted with a documented carrier (docs/03-unsupported.md). fails on oracle, postgresql
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r

-- CASE[open]: my-date-eq-dt — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT DATE('2020-01-01') = '2020-01-01 00:00:00' AS r

-- CASE[fixed]: my-date-format — DATE_FORMAT(str, mask) with a reproducible mask. The bare ISO string value is wrapped as a DATE (Oracle/PG TO_CHAR / T-SQL FORMAT reject a string); mask translated python->engine model. live-verified 2020/05/17 on all four. (bare-letter/locale masks like %W degrade honestly.)
SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r

-- CASE[fixed]: my-dateadd — fails on tsql. FUNC-DIFF: source=(('2020-02-29', '2020-01-02', '2020-02-29', '2020-01-01 01:00:00'),) tar
SELECT DATE_ADD('2020-01-31',INTERVAL 1 MONTH), DATE_ADD('2020-01-01',INTERVAL 1 DAY), DATE_SUB('2020-03-01',INTERVAL 1 DAY), '2020-01-01'+INTERVAL 1 HOUR

-- CASE[fixed]: my-dateadd-units — QUARTER was unrecognized (dropped to an invalid DATEADD with a quoted count); added to the date-unit set and handled as 3 months on Oracle (ADD_MONTHS *3) and PG (INTERVAL '3 months'), native on T-SQL/MySQL; +1 quarter = 2020-04-15 and -2 weeks = 2020-01-01 verified on all
SELECT DATE_ADD(NOW(),INTERVAL 1 QUARTER), DATE_SUB(NOW(),INTERVAL 2 WEEK)

-- CASE[limit]: my-dateformat-iso — fails on oracle, postgresql, tsql. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT DATE_FORMAT('2020-06-15 14:30:45', '%Y-%m-%dT%H:%i:%s') AS r

-- CASE[limit]: my-dateformat-long — fails on oracle, postgresql, tsql. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT DATE_FORMAT('2020-06-15', '%W, %M %D, %Y') AS r

-- CASE[fixed]: my-datetime-precision — MySQL DATETIME(n)/TIMESTAMP(n) with fractional precision: T-SQL DATETIME takes no width (error 2716) so DATETIME(n)->DATETIME2(n); Oracle TIMESTAMP(n) WITH TIME ZONE keeps the precision inside the type name. Live-verified valid on all targets.
CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)

-- CASE[fixed]: my-dayparts — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DA
SELECT DAYOFWEEK(NOW()), WEEKDAY(NOW()), DAYOFYEAR(NOW()), QUARTER(NOW())

-- CASE[fixed]: my-decimal-scale — same value at each engine's default decimal scale (10/3 = 3.3333...; 1.5*1.5 = 2.25; 0.1*0.1 = 0.01). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 10.00/3, 10/3.0, CAST(10 AS DECIMAL(10,4))/3, 1.5*1.5, 0.1*0.1

-- CASE[open]: my-distinct-case — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('a',), ('B',)) target=(('A',), ('B',))
SELECT DISTINCT x FROM (SELECT 'a' x UNION ALL SELECT 'A' x UNION ALL SELECT 'a' x UNION ALL SELECT 'B' x) t ORDER BY x

-- CASE[fixed]: my-div — MySQL / is decimal (2.5); PG/T-SQL truncate two ints. Force decimal via (a * 1.0 / b). Value 2.5 (repr differs by decimal scale).
SELECT 5 / 2 AS r

-- CASE[fixed]: my-div-mult2 — 1/3*3 = 1; each engine carries a different decimal precision (MySQL 1, PG/T-SQL 0.999999). Same value. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 1/3*3 AS r

-- CASE[fixed]: my-div-precision — 1.0/3 = 0.3333...; same value at each engine's default division scale. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 1.0 / 3 AS r

-- CASE[open]: my-dttypes — fails on oracle, tsql. (2716, b'Column, parameter, or variable #6: Cannot specify a column width on data type dat
CREATE TABLE t (a DATE, b TIME, c DATETIME, d TIMESTAMP, e YEAR, f DATETIME(6), g TIME(3))

-- CASE[fixed]: my-elt — MySQL ELT(n, ...) now translates (element by 1-based index); stale tag, live-verified equal.
SELECT ELT(2, 'a', 'b', 'c') AS r

-- CASE[open]: my-emoji-len — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT CHAR_LENGTH('😀') AS r

-- CASE[limit]: my-empty-eq-zero — fails on oracle. Oracle stores '' as NULL (docs/03-unsupported.md). FUNC-DIFF: source=(('1',),) target=(('NULL',),)
SELECT '' = 0 AS r

-- CASE[fixed]: my-epoch — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT UNIX_TIMESTAMP('2020-01-01 00:00:00'), FROM_UNIXTIME(1577836800), TIME_TO_SEC('01:00:00')

-- CASE[limit]: my-eq-mix — fails on oracle, tsql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('1', '0', '1'),) target=(('1', '1', '1'),)
SELECT 1 = 1.0 AS r, 'a' = 'a ' AS b, 1 = TRUE AS c

-- CASE[fixed]: my-export-set — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXPORT_SET(5, 'Y', 'N', ',', 4) AS r

-- CASE[fixed]: my-export-set2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.EX
SELECT EXPORT_SET(5,'Y','N',',',4) AS r

-- CASE[open]: my-extract-compound — fails on oracle, postgresql, tsql. (155, b"'YEAR_MONTH' is not a recognized datepart option.DB-Lib error message 20018, sever
SELECT EXTRACT(YEAR_MONTH FROM NOW()), EXTRACT(DAY_HOUR FROM NOW())

-- CASE[fixed]: my-extractvalue — EXTRACTVALUE(xml,xpath) maps to Oracle EXTRACTVALUE(XMLTYPE(..)), PG XPATH(..'/text()')[1], T-SQL XML .value(). Live-verified '1'.
SELECT EXTRACTVALUE('<a>1</a>', '/a') AS r

-- CASE[limit]: my-fcollate — fails on oracle, postgresql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('c', 'a', '1'),) target=(('c', 'B', '0'),)
SELECT GREATEST('a','B','c'),LEAST('a','B'),'a'<'B'

-- CASE[fixed]: my-fconcatnum — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('x5', 'x5.5', 'x1', 'NULL'),) target=(('x5', 'x5.5', 'x1', 'x'),)
SELECT CONCAT('x',5),CONCAT('x',5.5),CONCAT('x',TRUE),CONCAT('x',NULL)

-- CASE[fixed]: my-field — MySQL FIELD(x, ...) now translates (1-based index of x, else 0); stale tag, live-verified equal.
SELECT FIELD('b', 'a', 'b', 'c') AS r

-- CASE[fixed]: my-file-lock — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT LOAD_FILE('/etc/x'), IS_USED_LOCK('l')

-- CASE[fixed]: my-fk-full — fails on oracle. ORA-03075: unexpected item ON in an out-of-line constraint
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE t (pid INT, CONSTRAINT fk FOREIGN KEY (pid) REFERENCES p(id) ON DELETE SET NULL ON UPDATE CASCADE)

-- CASE[limit]: my-flen — fails on oracle, postgresql, tsql. APPROVED LIMIT (2026-07-18): LENGTH/BIT_LENGTH byte-vs-char, encoding-dependent (docs/03-unsupported.md §2). FUNC-DIFF: source=(('5', '4', '6', '2'),) target=(('4', '4', '2', '2'),)
SELECT LENGTH('café'),CHAR_LENGTH('café'),LENGTH('日本'),CHAR_LENGTH('日本')

-- CASE[fixed]: my-float-precision — same IEEE/float value at each engine's display precision (DOUBLE vs FLOAT). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 0.1+0.2, CAST(0.1 AS DOUBLE)+CAST(0.2 AS DOUBLE), 1.0/3, 2/3

-- CASE[open]: my-floor-precision — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('2',),) target=(('3',),)
SELECT FLOOR(2.9999999999999999) AS r

-- CASE[limit]: my-fmt-spec — fails on oracle. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT DATE_FORMAT(NOW(),'%a %b %e %T %Y'),DATE_FORMAT(NOW(),'%p %l:%i'),DATE_FORMAT(NOW(),'%j %U %u %V')

-- CASE[limit]: my-fmt-spec2 — fails on oracle, postgresql, tsql. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT DATE_FORMAT('2020-06-15','%D %W %M'),DATE_FORMAT('2020-06-15','%X %V')

-- CASE[limit]: my-fmt3 — fails on oracle, postgresql, tsql. FORMAT with a locale (de_DE) has no cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT FORMAT(1234.5678,2),FORMAT(1234.5678,4,'de_DE'),TRUNCATE(1234.5678,2)

-- CASE[limit]: my-for-share — FOR SHARE (a shared row lock) has no Oracle equivalent (Oracle SELECT locking is FOR UPDATE, exclusive); the shared lock is dropped and the divergence annotated (docs/03-unsupported.md). fails on oracle
CREATE TABLE t (id INT, INDEX ix (id)); SELECT id FROM t WHERE id = 1 FOR SHARE

-- CASE[fixed]: my-format-fns2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT DATE_FORMAT(NOW(),'%W %M %Y'), TIME_FORMAT(NOW(),'%r')

-- CASE[open]: my-fsubstr — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('', 'c', 'bc'),) target=(('ab', 'a', 'bc'),)
SELECT SUBSTRING('abc',0),SUBSTRING('abc',-1),SUBSTRING('abc',2,10)

-- CASE[fixed]: my-full-select — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t GROUP BY id HAVING COUNT(*) > 1 ORDER BY id LIMIT 10 OFFSET 5

-- CASE[limit]: my-fulltext — fails on oracle, postgresql, tsql. MySQL FULLTEXT index + MATCH()..AGAINST() has no faithful cross-engine equivalent (Oracle Text, PG tsvector/GIN, T-SQL full-text catalog are all different engines with different syntax) (docs/03-unsupported.md §2). Warned carrier on all three.
CREATE TABLE t (txt TEXT, FULLTEXT(txt));
SELECT * FROM t WHERE MATCH(txt) AGAINST('hello' IN NATURAL LANGUAGE MODE)

-- CASE[open]: my-gc-order — fails on oracle. FUNC-DIFF: source=(('3,1,2',),) target=(('1,2,3',),)
SELECT GROUP_CONCAT(x) FROM (SELECT 3 x UNION ALL SELECT 1 x UNION ALL SELECT 2 x) t

-- CASE[open]: my-gen-constr — fails on tsql. (1764, b"Computed Column 'b' in table 't' is invalid for use in 'CHECK CONSTRAINT' because
CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a+1) VIRTUAL, UNIQUE (b), CHECK (b>a))

-- CASE[open]: my-gencol2 — fails on postgresql, tsql. (1759, b"Computed column 'b' in table 't' is not allowed to be used in another computed-co
CREATE TABLE t (a INT, b INT AS (a*2) STORED, c INT AS (a+b) VIRTUAL, KEY(b))

-- CASE[fixed]: my-get-format — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_FORMAT(DATE, 'USA'), GET_FORMAT(DATETIME, 'ISO')

-- CASE[fixed]: my-get-lock — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_LOCK('l', 0), RELEASE_LOCK('l')

-- CASE[fixed]: my-getformat2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT GET_FORMAT(DATE,'EUR'), GET_FORMAT(TIME,'USA'), GET_FORMAT(DATETIME,'JIS')

-- CASE[fixed]: my-greatest-null — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('3',),)
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[fixed]: my-greatest-null2 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1',),)
SELECT GREATEST(NULL, 1) AS r

-- CASE[open]: my-greatest-string — fails on oracle, postgresql. FUNC-DIFF: source=(('B',),) target=(('a',),)
SELECT GREATEST('a', 'B') AS r

-- CASE[open]: my-group-case — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('a', '2'), ('b', '1')) target=(('A', '2'), ('b', '1'))
SELECT x, COUNT(*) FROM (SELECT 'a' x UNION ALL SELECT 'A' x UNION ALL SELECT 'b' x) t GROUP BY x ORDER BY x

-- CASE[fixed]: my-group-concat — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-groupconcat-distinct — fails on postgresql. SILENT-ROUNDTRIP: literal(s) ["'|'"] lost after mysql->oracle->mysql
SELECT GROUP_CONCAT(DISTINCT x ORDER BY x DESC SEPARATOR '|') FROM (SELECT 1 x UNION ALL SELECT 1 UNION ALL SELECT 2) t

-- CASE[fixed]: my-groupconcat-order — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR ',') FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[fixed]: my-hash — fails on oracle, postgresql, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc'), SHA1('abc'), SHA2('abc', 256)

-- CASE[fixed]: my-hash-all — fails on oracle, postgresql, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT CRC32('abc'), MD5('abc'), SHA('abc'), SHA2('abc', 512)

-- CASE[fixed]: my-having-noagg — MySQL allows HAVING without GROUP BY on a non-aggregate; wrap the query so HAVING becomes an outer WHERE (window-then-filter). Live-verified (1,1),(2,2).
SELECT x, RANK() OVER (ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2) t HAVING x>0

-- CASE[fixed]: my-hex-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(255) AS r, BIN(5) AS b

-- CASE[open]: my-hex-str-add — fails on postgresql. FUNC-DIFF: source=(('0',),) target=(('16',),)
SELECT '0x10' + 0 AS r

-- CASE[fixed]: my-hexcast — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT CAST(x'48656C6C6F' AS CHAR),HEX('Hello'),UNHEX('48656C6C6F')

-- CASE[limit]: my-ifnull-empty — fails on oracle. Oracle stores '' as NULL, so an empty-string result cannot survive (docs/03-unsupported.md). FUNC-DIFF: source=(('',),) target=(('NULL',),)
SELECT IFNULL('', NULL) AS r

-- CASE[fixed]: my-index-fns — MySQL INTERVAL/FIELD/ELT now translate; stale tag, live-verified equal on all targets.
SELECT INTERVAL(3, 1, 2, 4, 6), FIELD('b','a','b'), ELT(1,'x','y')

-- CASE[fixed]: my-inet — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET_ATON('127.0.0.1'), INET_NTOA(2130706433)

-- CASE[fixed]: my-inet3 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET_ATON('10.0.0.1'),INET_NTOA(167772161),INET6_ATON('::1')

-- CASE[fixed]: my-inet6 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.IN
SELECT INET6_ATON('::1'), INET6_NTOA(INET6_ATON('::1'))

-- CASE[open]: my-infoschema — fails on oracle. PROCEDURE P compiled INVALID (line 8): PL/SQL: ORA-00942: table or view does not exist
CREATE PROCEDURE p() BEGIN DECLARE c INT; SELECT COUNT(*) INTO c FROM information_schema.tables; SELECT c; END

-- CASE[fixed]: my-insert-oob — fails on tsql. FUNC-DIFF: source=(('abc',),) target=(('NULL',),)
SELECT INSERT('abc', 10, 1, 'X') AS r

-- CASE[fixed]: my-insert-zeropos — fails on tsql. FUNC-DIFF: source=(('abcdef',),) target=(('NULL',),)
SELECT INSERT('abcdef', 0, 2, 'XY') AS r

-- CASE[fixed]: my-insert2 — MySQL INSERT(s, p, len, sub) now translates (Oracle SUBSTR concat, PG OVERLAY); stale tag, live-verified 'QuWhattic'.
SELECT INSERT('Quadratic', 3, 4, 'What') AS r

-- CASE[fixed]: my-instr-case — MySQL's default collation is case-insensitive (INSTR('aAaA','A')=1); Oracle/PG compare case-sensitively. LOWER both operands there.
SELECT INSTR('aAaA', 'A') AS r

-- CASE[limit]: my-int-or-empty — fails on oracle. Oracle stores '' as NULL (docs/03-unsupported.md). FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT 0 OR '' AS r

-- CASE[fixed]: my-is-true — <predicate> IS TRUE in value position normalizes to the predicate before the CASE wrap (was an invalid IS 1). Live-verified 1.
SELECT 1 IN (SELECT 1) IS TRUE AS r

-- CASE[limit]: my-json-agg — fails on tsql. JSON_ARRAYAGG/JSON_OBJECTAGG map faithfully across MySQL, PostgreSQL (json_agg/json_object_agg) and Oracle (value-verified); T-SQL has no JSON aggregate (docs/03-unsupported.md §3.9). Warned carrier on tsql.
SELECT JSON_ARRAYAGG(x), JSON_OBJECTAGG(x,x*10) FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[limit]: my-json-aggs — fails on tsql. Same as my-json-agg (JSON_ARRAYAGG/JSON_OBJECTAGG faithful MySQL<->PG<->Oracle); T-SQL has no JSON aggregate (docs/03-unsupported.md §3.9). Warned carrier on tsql.
SELECT JSON_ARRAYAGG(x), JSON_OBJECTAGG(x, x*2) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[fixed]: my-json-array-ops — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAY_APPEND('[1,2]', '$', 3), JSON_ARRAY_INSERT('[1,2]', '$[0]', 0)

-- CASE[fixed]: my-json-arrayagg — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_ARRAYAGG(x) FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[fixed]: my-json-build — JSON_ARRAY/JSON_OBJECT constructors. A boolean stays a JSON boolean (PG/Oracle TRUE, T-SQL CAST(x AS BIT)); NULL kept via NULL ON NULL (Oracle/T-SQL). PG spells json_build_array/object. live-verified [1,"a",null,true] on all four.
SELECT JSON_ARRAY(1,'a',NULL,TRUE),JSON_OBJECT('k','v','n',1)

-- CASE[fixed]: my-json-fns2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SEARCH('{"a":"x"}', 'one', 'x'), JSON_DEPTH('[1,[2]]'), JSON_LENGTH('[1,2,3]')

-- CASE[open]: my-json-index — fails on postgresql, tsql. (2715, b'Column, parameter, or variable #2: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (a INT, b JSON, c INT AS (JSON_EXTRACT(b,'$.x')) STORED, INDEX((CAST(b->'$.x' AS UNSIGNED))))

-- CASE[fixed]: my-json-keys — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_KEYS('{"a":1,"b":2}') AS r

-- CASE[limit]: my-json-merge — MySQL JSON_MERGE_PATCH (RFC 7396 deep merge) has no portable form (Oracle spells it JSON_MERGEPATCH, PG has only shallow ||); catalog-gated + annotated (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT JSON_MERGE_PATCH('{"a":1}', '{"b":2}') AS r

-- CASE[fixed]: my-json-meta — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_TYPE('[1]'),JSON_LENGTH('[1,2,3]'),JSON_DEPTH('[[1]]'),JSON_VALID('{a}')

-- CASE[fixed]: my-json-mod — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SET('{}','$.a',1),JSON_INSERT('{}','$.a',1),JSON_REPLACE('{"a":1}','$.a',2),JSON_REMOVE('{"a":1,"b":2}','$.a')

-- CASE[fixed]: my-json-modify — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SET('{}', '$.a', 1), JSON_REMOVE('{"a":1}', '$.a'), JSON_REPLACE('{"a":1}', '$.a', 2)

-- CASE[fixed]: my-json-object — JSON_OBJECT maps per engine: PG json_build_object, Oracle KEY..VALUE, T-SQL colon, MySQL comma (NULL ON NULL keeps null values). live-verified {"a":1,"b":2} on all four.
SELECT JSON_OBJECT('a', 1, 'b', 2)

-- CASE[fixed]: my-json-search — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_KEYS('{"a":1,"b":2}'),JSON_CONTAINS('[1,2]','1'),JSON_CONTAINS_PATH('{"a":1}','one','$.a')

-- CASE[fixed]: my-json-search2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSON_SEARCH('{"a":"x","b":"x"}','all','x'),JSON_OVERLAPS('[1,2]','[2,3]')

-- CASE[fixed]: my-json-type — a MySQL JSON column maps to Oracle CLOB (the native JSON type has usage limits, ORA-43853) and T-SQL NVARCHAR(MAX) (no JSON type pre-2025); PostgreSQL keeps native JSON. live-verified CREATE runs.
CREATE TABLE t (data JSON)

-- CASE[fixed]: my-last-day-name — LAST_DAY -> EOMONTH (tsql) / native (oracle) / DATE_TRUNC month-end (pg); DAYNAME/MONTHNAME wrap the ISO arg as an ANSI DATE and use FM-trimmed, init-capped names (Oracle 'MONTH' otherwise pads/uppercases to 'JUNE     '). live-verified 2020-02-29, Monday, June.
SELECT LAST_DAY('2020-02-15'), DAYNAME('2020-06-15'), MONTHNAME('2020-06-15')

-- CASE[fixed]: my-lastday-extract — LAST_DAY + EXTRACT(DAY). Oracle LAST_DAY / PG month-end via DATE_TRUNC / T-SQL EOMONTH; the extracted day = 29 on all. Oracle's DATE renders a 00:00:00 time (same value, precision-only; policy 2026-07-19). live-verified.
SELECT LAST_DAY('2020-02-15'), EXTRACT(DAY FROM LAST_DAY('2020-02-15'))

-- CASE[fixed]: my-least-greatest-null — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL', 'NULL'),) target=(('a', '1'),)
SELECT LEAST(NULL, 'a') AS r, GREATEST(NULL, 1) AS b

-- CASE[fixed]: my-least-null2 — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1',),)
SELECT LEAST(1, 2, NULL, 3) AS r

-- CASE[fixed]: my-left-float — fails on tsql. FUNC-DIFF: source=(('hel',),) target=(('he',),)
SELECT LEFT('hello', 2.9) AS r

-- CASE[fixed]: my-left-neg — fails on postgresql. FUNC-DIFF: source=(('',),) target=(('ab',),)
SELECT LEFT('abc', -1) AS r

-- CASE[fixed]: my-len-trio — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT CHAR_LENGTH(s), LENGTH(s), BIT_LENGTH(s) FROM (SELECT 'héllo' s) t

-- CASE[limit]: my-length-bytes — fails on oracle, postgresql, tsql. APPROVED LIMIT (2026-07-18): LENGTH bytes-vs-chars, encoding-dependent, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('5',),) target=(('4',),)
SELECT LENGTH('café') AS r

-- CASE[limit]: my-length-div — MySQL LENGTH() counts bytes and the division result's representation differs across engines; annotated bytes-vs-chars divergence (docs/03-unsupported.md). fails on oracle, tsql
SELECT LENGTH(1/3) AS r

-- CASE[limit]: my-length-unicode — fails on oracle, postgresql, tsql. APPROVED LIMIT (2026-07-18): LENGTH bytes-vs-chars, encoding-dependent, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('5', '4', '5'),) target=(('4', '4', '3'),)
SELECT LENGTH('café'), CHAR_LENGTH('café'), LENGTH('  x  ')

-- CASE[limit]: my-like-ci — fails on oracle, postgresql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[fixed]: my-like-escape — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'a_b' LIKE 'a\_b' AS r

-- CASE[limit]: my-like-single — fails on oracle, postgresql. APPROVED LIMIT (2026-07-18): LIKE case-sensitivity is a default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'x' LIKE 'X' AS r

-- CASE[fixed]: my-loadfile — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LO
SELECT LOAD_FILE('/nonexist') IS NULL AS r

-- CASE[fixed]: my-locate-case — MySQL LOCATE is case-insensitive by default (LOCATE('a','ABC')=1); LOWER both operands on Oracle/PG.
SELECT LOCATE('a', 'ABC') AS r

-- CASE[fixed]: my-locate-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT LOCATE('', '') AS r

-- CASE[fixed]: my-locate-empty2 — fails on oracle, tsql. FUNC-DIFF: source=(('1', '1'),) target=(('0', '0'),)
SELECT LOCATE('', 'abc'), INSTR('abc', '')

-- CASE[fixed]: my-log-2arg — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('0.333333',),)
SELECT LOG(2, 8) AS r

-- CASE[fixed]: my-log2-log10 — fails on tsql. FUNC-DIFF: source=(('3', '3'),) target=(('0.333333', '0.333333'),)
SELECT LOG2(8), LOG10(1000)

-- CASE[fixed]: my-logexp — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.LN
SELECT LOG2(8), LOG10(100), LN(2.718), EXP(1)

-- CASE[fixed]: my-lpad-conv — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CO
SELECT LPAD(CONV(5,10,2), 8, '0') AS r

-- CASE[fixed]: my-lpad-multichar — fails on tsql. FUNC-DIFF: source=(('xyxab',),) target=(('yxyab',),)
SELECT LPAD('ab', 5, 'xy') AS r

-- CASE[fixed]: my-lpad-trunc — fails on tsql. FUNC-DIFF: source=(('ab',),) target=(('bc',),)
SELECT LPAD('abc', 2, 'x') AS r

-- CASE[fixed]: my-make-set — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_SET(3, 'a', 'b', 'c') AS r

-- CASE[fixed]: my-make-set2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_SET(1|4,'hello','nice','world') AS r

-- CASE[fixed]: my-makedate — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKEDATE(2020, 100), MAKETIME(10, 30, 0)

-- CASE[fixed]: my-misc-num — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CR
SELECT RAND(),FLOOR(RAND()*100),CRC32('x'),CONV(255,10,2),BIN(10),OCT(64),HEX(255)

-- CASE[fixed]: my-mod-edge — fails on oracle. FUNC-DIFF: source=(('0', '1', '1'),) target=(('0', '0', '0'),)
SELECT MOD(0,5), MOD(5,0) IS NULL, 5%0 IS NULL

-- CASE[fixed]: my-mod-zero — fails on oracle. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 5 MOD 0 IS NULL AS r

-- CASE[fixed]: my-month-overflow — fails on tsql. FUNC-DIFF: source=(('2020-02-29',),) target=(('2020-02-29 00:00:00',),)
SELECT DATE_ADD('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[fixed]: my-name-const — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NA
SELECT NAME_CONST('col', 5) AS r

-- CASE[open]: my-nested-call — fails on oracle. PROCEDURE P compiled INVALID (line 4): PLS-00201: identifier 'OTHER_PROC' must be declared
CREATE PROCEDURE p() BEGIN CALL other_proc(); END

-- CASE[fixed]: my-now-fns — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'CURRENT_TIME'.DB-Lib error message 20018, sever
SELECT NOW(), CURDATE(), CURTIME(), UTC_DATE(), UTC_TIME(), SYSDATE()

-- CASE[fixed]: my-now-variants — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near '3'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT NOW(), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP(3), CURDATE(), CURTIME(), SYSDATE(), UNIX_TIMESTAMP()

-- CASE[open]: my-num-to-str — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('n=5', 'x=5.50', 'd=0.33333', 'b=1', '5.5'),) target=(('n=5', 'x=5.5',
SELECT CONCAT('n=',5), CONCAT('x=',5.50), CONCAT('d=',1.0/3), CONCAT('b=',TRUE), 5.50+0

-- CASE[fixed]: my-numeric — MySQL FLOAT(M,D) is a 4-byte float with a display scale; T-SQL FLOAT takes at most a bit-precision, so FLOAT(10,2) maps to REAL (no width), matching PostgreSQL. live-verified CREATE runs.
CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)

-- CASE[fixed]: my-numeric-conv — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_COUNT(255), CONV(255,10,16), OCT(64), HEX(255)

-- CASE[fixed]: my-optimizer-hints — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT /*+ QB_NAME(qb1) */ id FROM t WHERE n > (SELECT /*+ SEMIJOIN(@qb1) */ AVG(n) FROM t)

-- CASE[fixed]: my-order-case-sens — MySQL orders case-insensitively; LOWER() on the (provably-string) ORDER BY key reproduces that order on Oracle/PG (Apple, banana, Cherry). 
SELECT x FROM (SELECT 'Apple' x UNION SELECT 'banana' UNION SELECT 'Cherry') t ORDER BY x

-- CASE[open]: my-order-strings — fails on oracle, postgresql, tsql. FUNC-DIFF: source=(('Apple',), ('banana',), ('Banana',), ('cherry',)) target=(('Apple',), 
SELECT x FROM (SELECT 'banana' x UNION ALL SELECT 'Apple' x UNION ALL SELECT 'cherry' x UNION ALL SELECT 'Banana' x) t ORDER BY x

-- CASE[fixed]: my-pad-repeat — MySQL LPAD/RPAD/REPEAT/REVERSE/SPACE now translate (Oracle RPAD, PG REPEAT); stale tag, live-verified equal.
SELECT LPAD('7',3,'0'),RPAD('7',3,'x'),REPEAT('ab',3),REVERSE('abc'),SPACE(3),CONCAT('[',SPACE(2),']')

-- CASE[fixed]: my-period-diff — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE
SELECT PERIOD_DIFF(202006, 202001) AS r

-- CASE[fixed]: my-period2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.PE
SELECT PERIOD_ADD(202001,14), PERIOD_DIFF(202101,202001)

-- CASE[fixed]: my-pi-fns — TRUNCATE/ROUND/FORMAT of PI() across engines. PostgreSQL TRUNC/ROUND have no (double, int) overload, so PI() is cast to NUMERIC; Oracle PI()=ACOS(-1); FORMAT -> TO_CHAR/FORMAT number mask. live-verified 3.1415, 3.1416, 3.1416.
SELECT TRUNCATE(PI(), 4), ROUND(PI(), 4), FORMAT(PI(), 4)

-- CASE[fixed]: my-pi-vals — T-SQL RADIANS/DEGREES return the argument's type, so RADIANS(180) truncates an integer arg to 3; casting the integer arg to FLOAT preserves 3.14159. live-verified 180, 3.14159, 3.14159.
SELECT DEGREES(PI()), RADIANS(180), PI()

-- CASE[fixed]: my-quote2 — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU
SELECT QUOTE('Don\'t!') AS r

-- CASE[fixed]: my-rand — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RA
SELECT RAND(1), RANDOM_BYTES(4), UUID()

-- CASE[open]: my-reads-sql — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE FUNCTION f(a INT) RETURNS INT READS SQL DATA BEGIN RETURN (SELECT COUNT(*) FROM (SELECT a) t); END

-- CASE[fixed]: my-realworld-orders — fails on postgresql. relation "orders" already exists
CREATE TABLE orders (id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL, total DECIMAL(10,2) DEFAULT 0, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP, INDEX ix_cust (customer_id), CHECK (total >= 0)) ENGINE=InnoDB;
CREATE TRIGGER trg BEFORE INSERT ON orders FOR EACH ROW SET NEW.created = NOW();

-- CASE[fixed]: my-recursive-cte2 — fails on oracle. ORA-32039: missing column alias list in recursive WITH clause element SEQ
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); WITH RECURSIVE seq AS (SELECT 1 n UNION ALL SELECT n+1 FROM seq WHERE n<10) SELECT * FROM seq

-- CASE[fixed]: my-recursive-func — T-SQL requires a scalar function's LAST statement to be RETURN (error 455); an all-branches-return IF/ELSE body now gets a trailing RETURN NULL; recursive f(5)=120 verified
CREATE FUNCTION f(n INT) RETURNS INT DETERMINISTIC BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END

-- CASE[fixed]: my-repeat-float — fails on tsql. FUNC-DIFF: source=(('ababab',),) target=(('abab',),)
SELECT REPEAT('ab', 2.9) AS r

-- CASE[fixed]: my-repeat-neg — fails on tsql. FUNC-DIFF: source=(('',),) target=(('NULL',),)
SELECT REPEAT('ab', -1) AS r

-- CASE[fixed]: my-replace-case — MySQL REPLACE is case-sensitive; force a BIN2 collation on the T-SQL subject so only lowercase 'a' is replaced (AbCXBc, not XbCXBc).
SELECT REPLACE('AbCaBc', 'a', 'X') AS r

-- CASE[fixed]: my-replace-null2 — MySQL REPLACE propagates NULL (literal-NULL arg -> NULL); Oracle ignores it. Fold to NULL.
SELECT REPLACE('abc', NULL, 'x') IS NULL AS r

-- CASE[fixed]: my-round-cast — MySQL CAST(x AS SIGNED) rounds to int. Oracle CAST AS INTEGER rounds (BIGINT/TINYINT→INTEGER, no BIGINT type); PG BIGINT rounds; T-SQL truncates so wrap ROUND(x,0) — now also for a negated literal (-3.99 is a UnaryOp). live-verified 4,-4,4.
SELECT CAST(3.99 AS SIGNED),CAST(-3.99 AS SIGNED),CONVERT(3.99,SIGNED)

-- CASE[fixed]: my-round-fns — fails on tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.CE
SELECT FLOOR(3.7), CEILING(3.2), ROUND(3.567, 2), TRUNCATE(3.567, 1)

-- CASE[open]: my-scalar-subquery-assign — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE PROCEDURE p() BEGIN DECLARE v INT; SET v = (SELECT COUNT(*) FROM (SELECT 1) t); END

-- CASE[open]: my-select-into-out — fails on tsql. (8155, b"No column name was specified for column 1 of 't'.DB-Lib error message 20018, seve
CREATE PROCEDURE p(OUT c INT) BEGIN SELECT COUNT(*) INTO c FROM (SELECT 1) t; END

-- CASE[open]: my-self-fk — fails on tsql. (1785, b"Introducing FOREIGN KEY constraint 'FK__emp__mgr__790A8C33' on table 'emp' may ca
CREATE TABLE emp (id INT PRIMARY KEY, mgr INT, FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET NULL)

-- CASE[open]: my-seq-concat — fails on oracle, postgresql. ORA-32039: missing column alias list in recursive WITH clause element SEQ
WITH RECURSIVE seq AS (SELECT 1 n UNION ALL SELECT n+1 FROM seq WHERE n<10) SELECT GROUP_CONCAT(n) FROM seq

-- CASE[fixed]: my-session-fns — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'USER'.DB-Lib error message 20018, severity 15:\
CREATE TABLE t (id INT); SELECT LAST_INSERT_ID(),ROW_COUNT(),CONNECTION_ID(),DATABASE(),VERSION(),USER(),CURRENT_USER()

-- CASE[fixed]: my-set-fns — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.FI
SELECT FIND_IN_SET('b', 'a,b,c'), MAKE_SET(6, 'x','y','z')

-- CASE[open]: my-set-transaction — fails on oracle. ORA-00900: invalid SQL statement
SET TRANSACTION ISOLATION LEVEL READ COMMITTED; START TRANSACTION READ ONLY; COMMIT;

-- CASE[fixed]: my-soundex-eq — fails on postgresql. function soundex(unknown) does not exist
SELECT SOUNDEX('hello') = SOUNDEX('hallo') AS r

-- CASE[open]: my-soundex-format — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT SOUNDEX('Smith'), FORMAT(1234.5, 2)

-- CASE[fixed]: my-spatial — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_AsText(ST_GeomFromText('POINT(1 1)')) AS r

-- CASE[fixed]: my-st-distance — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_Distance(ST_GeomFromText('POINT(0 0)'), ST_GeomFromText('POINT(3 4)')) AS r

-- CASE[fixed]: my-st-geojson — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT ST_AsGeoJSON(ST_GeomFromText('POINT(1 1)')) AS r

-- CASE[fixed]: my-status-funcs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RO
SELECT LAST_INSERT_ID(), ROW_COUNT(), FOUND_ROWS()

-- CASE[fixed]: my-stmt-digest — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT STATEMENT_DIGEST('SELECT 1'), STATEMENT_DIGEST_TEXT('SELECT 1')

-- CASE[limit]: my-str-lt — fails on oracle, postgresql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'apple' < 'Banana' AS r

-- CASE[fixed]: my-str-misc — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT SOUNDEX('Robert'),FORMAT(1234567.891,2),INSERT('abcd',2,2,'XY'),QUOTE('a''b')

-- CASE[fixed]: my-str-null — fails on oracle, postgresql. FUNC-DIFF: source=(('NULL', 'NULL', 'NULL', 'NULL', 'NULL', 'NULL'),) target=(('NULL', 'a'
SELECT LENGTH(NULL), CONCAT('a',NULL), REPLACE(NULL,'a','b'), SUBSTRING(NULL,1,2), UPPER(NULL), TRIM(NULL)

-- CASE[fixed]: my-str-plus-interval — fails on tsql. FUNC-DIFF: source=(('2020-01-02',),) target=(('2020-01-02 00:00:00',),)
SELECT '2020-01-01' + INTERVAL 1 DAY AS r

-- CASE[fixed]: my-strnum-add — fails on tsql. FUNC-DIFF: source=(('10',),) target=(('55',),)
SELECT '5'+'5' AS r

-- CASE[fixed]: my-subdate — fails on tsql. FUNC-DIFF: source=(('2019-12-31',),) target=(('2019-12-31 00:00:00',),)
SELECT SUBDATE('2020-01-31', INTERVAL 1 MONTH) AS r

-- CASE[fixed]: my-substr-float — MySQL rounds a fractional SUBSTRING position/length (2.9->3); Oracle/T-SQL truncate, so pre-round the literal args. Live-verified 'llo'.
SELECT SUBSTRING('hello', 2.9, 2.9) AS r

-- CASE[fixed]: my-substr-neg — fails on postgresql, tsql. FUNC-DIFF: source=(('def',),) target=(('ab',),)
SELECT SUBSTRING('abcdef', -3) AS r

-- CASE[fixed]: my-substr3 — fails on postgresql, tsql. FUNC-DIFF: source=(('bcdef', 'bcd', 'ef'),) target=(('bcdef', 'bcd', 'abc'),)
SELECT SUBSTR('abcdef',2), SUBSTR('abcdef',2,3), SUBSTR('abcdef',-2)

-- CASE[fixed]: my-substridx-agg — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX(GROUP_CONCAT(x),',',2) FROM (SELECT 1 x UNION SELECT 2 UNION SELECT 3) t

-- CASE[fixed]: my-substridx-nested — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX(SUBSTRING_INDEX('a,b,c,d', ',', 3), ',', -1) AS r

-- CASE[fixed]: my-substring-index — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.SU
SELECT SUBSTRING_INDEX('a,b,c', ',', 2) AS r

-- CASE[fixed]: my-sum-div-count — MySQL / is always decimal division; PG/T-SQL truncate two integers, so force decimal (* 1.0) on a MySQL source. Live-verified 1.5.
SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[fixed]: my-system-funcs — fails on oracle, postgresql, tsql. (156, b"Incorrect syntax near the keyword 'USER'.DB-Lib error message 20018, severity 15:\
SELECT CONNECTION_ID(), DATABASE(), USER(), VERSION()

-- CASE[fixed]: my-time-build — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT CAST('2020-01-01' AS DATETIME) + INTERVAL 90 MINUTE, MAKETIME(10,20,30), SEC_TO_TIME(3661)

-- CASE[fixed]: my-timestampadd — qualify the bare datetime string as a TIMESTAMP literal (seconds padded for Oracle) so PG/Oracle interval arithmetic runs. Live-verified 2020-01-01 10:30.
SELECT TIMESTAMPADD(MINUTE, 30, '2020-01-01 10:00') AS r

-- CASE[fixed]: my-timestampdiff — MySQL TIMESTAMPDIFF(DAY, ...) now translates (day count); stale tag, live-verified 9.
SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r

-- CASE[fixed]: my-timestampdiff-mon — MySQL TIMESTAMPDIFF counts COMPLETE months; T-SQL DATEDIFF counts month boundaries (2020-01-15..2020-03-10 = 1, not 2). Drop the incomplete final period via DATEADD > end. live-verified 1.
SELECT TIMESTAMPDIFF(MONTH, '2020-01-15', '2020-03-10') AS r

-- CASE[fixed]: my-timestampdiff-year — same complete-vs-boundary divergence for YEAR (2019-12-31..2020-01-01 = 0 complete years, not 1). live-verified 0.
SELECT TIMESTAMPDIFF(YEAR, '2019-12-31', '2020-01-01') AS r

-- CASE[open]: my-timestr-plus — fails on postgresql, tsql. FUNC-DIFF: source=(('NULL',),) target=(('1900-01-01 13:30:00',),)
SELECT '12:00:00' + INTERVAL 90 MINUTE AS r

-- CASE[limit]: my-trailing-eq — fails on oracle, tsql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'a ' = 'a' AS r

-- CASE[limit]: my-trailing-space-cmp — fails on oracle, postgresql, tsql. APPROVED LIMIT (2026-07-18): collation case/accent/trailing-space sensitivity is a per-column property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0', '1', '1'),) target=(('1', '0', '1'),)
SELECT 'a'='a ', 'a'<'a ', 'abc'='ABC'

-- CASE[fixed]: my-trig — MySQL ATAN(y, x) is the 2-arg arctangent (= ATAN2); emit ATAN2 on Oracle/PG and ATN2 on T-SQL. Live-verified 0.7853981633974483.
SELECT ATAN2(1,1), ATAN(1,1), DEGREES(PI()), RADIANS(180), COT(1)

-- CASE[fixed]: my-trig-suite — MySQL ACOS/ASIN/ATAN/COS/SIN/TAN/COT/DEGREES/RADIANS now translate; the Oracle diff is decimal-precision only. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT ACOS(1),ASIN(0),ATAN(1),COS(0),SIN(0),TAN(0),COT(1),DEGREES(1),RADIANS(1)

-- CASE[fixed]: my-trim-both — fails on postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS r

-- CASE[fixed]: my-trim-edge — fails on postgresql, tsql. FUNC-DIFF: source=(('hi', '7', 'hi'),) target=(('', '', ''),)
SELECT TRIM(BOTH 'x' FROM 'xxhixx'), TRIM(LEADING '0' FROM '007'), TRIM(TRAILING '!' FROM 'hi!!')

-- CASE[fixed]: my-trim-leading — fails on postgresql, tsql. FUNC-DIFF: source=(('7',),) target=(('',),)
SELECT TRIM(LEADING '0' FROM '007') AS r

-- CASE[fixed]: my-trim-len — fails on oracle. ORA-30001: trim set should have only one character
SELECT LENGTH(TRIM(BOTH ' ' FROM '  hi  ')),CHAR_LENGTH(RTRIM(' hi '))

-- CASE[fixed]: my-trim-trailing — fails on postgresql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT TRIM(TRAILING '.' FROM 'abc...') AS r

-- CASE[fixed]: my-ts-to-date — DATE(x) extracts the date part; CAST AS DATE preserves the time-drop.
SELECT DATE(TIMESTAMP '2020-01-01 14:30') AS r

-- CASE[fixed]: my-tsadd-quarter — fails on oracle, postgresql. ORA-00904: "QUARTER": invalid identifier
SELECT TIMESTAMPADD(QUARTER,1,NOW()), TIMESTAMPDIFF(QUARTER,'2020-01-01',NOW())

-- CASE[limit]: my-tz-convert — CONVERT_TZ with a named IANA zone (America/New_York) has no faithful cross-engine equivalent (T-SQL uses Windows zone names, and DST rules differ), so the whole statement is gated + annotated (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT CONVERT_TZ('2020-06-15 10:00:00','+00:00','+05:30'), CONVERT_TZ('2020-06-15 10:00:00','UTC','America/New_York')

-- CASE[fixed]: my-unix-timestamp — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT UNIX_TIMESTAMP('2020-01-01'), FROM_UNIXTIME(1577836800)

-- CASE[fixed]: my-unixtime2 — fails on oracle, postgresql, tsql. (195, b"'UNIX_TIMESTAMP' is not a recognized built-in function name.DB-Lib error message 2
SELECT FROM_UNIXTIME(1600000000,'%Y-%m-%d'), UNIX_TIMESTAMP('2020-09-13')

-- CASE[fixed]: my-upd-selfjoin — the target's JOIN is lifted into the cross-table UPDATE emitter (PG FROM/WHERE, T-SQL FROM JOIN, Oracle correlated subquery); live-verified (1,10),(2,10).
CREATE TABLE t (id INT, n INT);UPDATE t t1 JOIN t t2 ON t1.id=t2.id+1 SET t1.n=t2.n

-- CASE[fixed]: my-update-join — UPDATE t JOIN s ON … SET … lifts the join into the per-engine cross-table UPDATE (join no longer dropped); live-verified (1,99),(2,88).
CREATE TABLE t (id INT, n INT); CREATE TABLE s (id INT, n INT); UPDATE t JOIN s ON t.id = s.id SET t.n = s.n

-- CASE[limit]: my-upper-sharps — fails on postgresql. APPROVED LIMIT (2026-07-18): non-ASCII case-folding (ß, accents) is locale/collation-dependent, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('ß',),) target=(('ẞ',),)
SELECT UPPER('ß') AS r

-- CASE[limit]: my-upper-sharps-len — fails on oracle, postgresql, tsql. APPROVED LIMIT (2026-07-18): non-ASCII case-folding (ß, accents) is locale/collation-dependent, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('2',),) target=(('1',),)
SELECT LENGTH(UPPER('ß')) AS r

-- CASE[limit]: my-upper-strasse — fails on postgresql. APPROVED LIMIT (2026-07-18): non-ASCII case-folding (ß, accents) is locale/collation-dependent, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('STRAßE',),) target=(('STRAẞE',),)
SELECT UPPER('straße') AS r

-- CASE[fixed]: my-using-join — USING(x)->ON a.x=b.x on T-SQL leaves a bare x ambiguous; qualify the projection's USING column with the left table (a.x). Live-verified 1.
SELECT x FROM (SELECT 1 x) a JOIN (SELECT 1 x) b USING (x)

-- CASE[fixed]: my-uuid-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU
SELECT UUID_TO_BIN(UUID()),BIN_TO_UUID(UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db'))

-- CASE[fixed]: my-uuid-funcs — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.UU
SELECT UUID(), UUID_SHORT()

-- CASE[fixed]: my-week-mode — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK('2020-01-01',0), WEEK('2020-01-01',3), WEEKOFYEAR('2020-01-01'), YEARWEEK('2020-01-01')

-- CASE[fixed]: my-week-modes — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK(NOW(),0), WEEK(NOW(),3), WEEK(NOW(),5), YEARWEEK(NOW(),3)

-- CASE[fixed]: my-week-quarter — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEEK('2020-06-15'), QUARTER('2020-06-15'), DAYOFWEEK('2020-06-15')

-- CASE[fixed]: my-weight-string — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WE
SELECT WEIGHT_STRING('abc') AS r

-- CASE[limit]: my-xml-fns — ExtractValue translates per engine (Oracle EXTRACTVALUE(XMLTYPE)/PG XPATH/T-SQL .value()), but MySQL UpdateXML has no cross-engine equivalent (PG lacks it; T-SQL .modify() XML-DML and Oracle UPDATEXML differ) so it degrades to NULL + annotation (docs/03-unsupported.md). fails on oracle, postgresql, tsql
SELECT ExtractValue('<r><a>1</a></r>','/r/a'), UpdateXML('<r><a>1</a></r>','/r/a','<a>2</a>')

-- CASE[fixed]: my8-lag-nth — fails on oracle. ORA-43853: JSON type cannot be used in non-automatic segment space management tablespace "
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, LAG(n, 1, 0) OVER (ORDER BY id), NTH_VALUE(n, 2) OVER (ORDER BY id) FROM t

-- CASE[fixed]: my8-recursive — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); WITH RECURSIVE cte AS (SELECT 1 n UNION ALL SELECT n+1 FROM cte WHERE n<5) SELECT * FROM cte

-- CASE[open]: my8-window — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, ROW_NUMBER() OVER w, SUM(n) OVER w FROM t WINDOW w AS (ORDER BY id)

-- CASE[fixed]: mysql-drop-'note'|note — MySQL column COMMENT now materializes as COMMENT ON COLUMN on PG/Oracle (RC-3); stale tag, live-verified the COMMENT executes.
CREATE TABLE t (a INT COMMENT 'note')

-- CASE[fixed]: mysql-drop-CHECK — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)
CREATE TABLE t (email VARCHAR(255) CHECK (email LIKE '%@%'))

-- CASE[fixed]: mysql-drop-GENERATED|AS\s — fails on tsql. SILENT CLAUSE DROP: 'GENERATED|AS\s*\(' absent from valid tsql output, no warning (target 
CREATE TABLE t (a INT, b INT AS (a+1) STORED)

-- CASE[fixed]: mysql-drop2-ON\s+UPDATE — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ON\s+UPDATE' absent from valid tsql output, no warning
CREATE TABLE t (a INT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)

-- CASE[fixed]: mysql-drop2-latin1|CHARA — fails on oracle, postgresql. SILENT CLAUSE DROP: 'latin1|CHARACTER\s+SET' absent from valid postgresql output, no warni
CREATE TABLE t (a VARCHAR(10) CHARACTER SET latin1)

-- CASE[fixed]: mysql-drop2-my table|COM — MySQL table COMMENT='…' now materializes as COMMENT ON TABLE on PG/Oracle (a note on T-SQL); live-verified the COMMENT executes.
CREATE TABLE t (a INT) COMMENT='my table'

-- CASE[fixed]: mysql-drop4-50|IDENTITY| — the table option AUTO_INCREMENT = 50 sets the next auto value, but the column `a` is not AUTO_INCREMENT, so the option is inert; dropping it on other engines is faithful. live-verified CREATE runs.
CREATE TABLE t (a INT PRIMARY KEY) AUTO_INCREMENT = 50

-- CASE[fixed]: mysql-drop4-COLLATE|utf8 — fails on oracle, postgresql. SILENT CLAUSE DROP: 'COLLATE|utf8mb4' absent from valid postgresql output, no warning
CREATE TABLE t (a INT) COLLATE=utf8mb4_unicode_ci

-- CASE[fixed]: mysql-drop4-UNSIGNED|CHE — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'UNSIGNED|CHECK' absent from valid postgresql output, no warning
CREATE TABLE t (a INT UNSIGNED)

-- CASE[open]: mysql-drop4-ZEROFILL|LPA — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ZEROFILL|LPAD' absent from valid postgresql output, no warning
CREATE TABLE t (a INT ZEROFILL)

-- CASE[fixed]: mysql-drop5-utf8mb4|CHAR — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'utf8mb4|CHARSET' absent from valid tsql output, no warning
CREATE TABLE t (a INT AUTO_INCREMENT PRIMARY KEY, b VARCHAR(20)) DEFAULT CHARSET=utf8mb4

-- CASE[open]: mysql-prec-64|BIGINT| — fails on oracle, postgresql. SILENT PRECISION CHANGE: '64|BIGINT|BINARY' not preserved in valid oracle output, no warni
CREATE TABLE t (a BIT(64))

-- CASE[fixed]: mysql-qdrop-ROLLUP — fails on oracle, postgresql, tsql. SILENT CLAUSE DROP: 'ROLLUP' absent from valid tsql output, no warning
SELECT x FROM (SELECT 1 x UNION SELECT 2) t GROUP BY x WITH ROLLUP

-- CASE[fixed]: mysql-qdrop-SQL_CALC_FOU — SQL_CALC_FOUND_ROWS has no equivalent on other engines; the drop is now surfaced as a carrier + warning (mirrored by the no-silent-loss scan), no longer silent.
SELECT SQL_CALC_FOUND_ROWS x FROM (SELECT 1 x) t LIMIT 1

