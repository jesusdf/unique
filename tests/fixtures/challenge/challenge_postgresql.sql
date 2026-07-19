-- Challenge fixtures — PostgreSQL / PL-pgSQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[limit]: pg-accent-eq — fails on mysql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'Ä' = 'A' AS r

-- CASE[open]: pg-add-identity — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT PRIMARY KEY, n INT);
ALTER TABLE t ADD COLUMN big BIGINT GENERATED ALWAYS AS IDENTITY

-- CASE[fixed]: pg-admin-fns — fails on mysql, oracle, tsql. (195, b"'pg_sleep' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT pg_sleep(0), pg_advisory_lock(1), txid_current()

-- CASE[fixed]: pg-age — fails on mysql, oracle, tsql. (195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a

-- CASE[fixed]: pg-age-epoch — fails on mysql, oracle, tsql. (195, b"'age' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT age(now(), '2020-01-01'), date_part('epoch', now())

-- CASE[open]: pg-all-values — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t WHERE n > ALL (VALUES (1),(2),(3))

-- CASE[open]: pg-alter-add — fails on mysql, oracle. ORA-30649: missing DIRECTORY keyword
CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'

-- CASE[open]: pg-alter-notvalid — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (id INT);
ALTER TABLE t RENAME TO tbl;
ALTER TABLE tbl ADD CONSTRAINT ck CHECK (id>0) NOT VALID;

-- CASE[open]: pg-alter-suite — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (id INT);
ALTER TABLE t ADD COLUMN name VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE t ALTER COLUMN id TYPE BIGINT;
ALTER TABLE t ALTER COLUMN name SET DEFAULT 'x';
ALTER TABLE t RENAME COLUMN name TO nm;
ALTER TABLE t DROP COLUMN nm;

-- CASE[open]: pg-alter-type — fails on oracle. ORA-01735: invalid ALTER TABLE option
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a TYPE BIGINT

-- CASE[open]: pg-alter-using — fails on oracle. ORA-01735: invalid ALTER TABLE option
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DATA TYPE BIGINT USING a::bigint

-- CASE[open]: pg-any-array-subquery — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near 'ARRAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ
CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a WHERE id = ANY(ARRAY(SELECT id FROM b))

-- CASE[fixed]: pg-arr-str-roundtrip — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT array_to_string(string_to_array('a,b,c',','),'|')

-- CASE[open]: pg-array-jsonb — fails on oracle. ORA-03099: unexpected item [ in a column definition
CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)

-- CASE[open]: pg-ascii-empty — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT ASCII('') AS r

-- CASE[open]: pg-at-time-zone — fails on mysql, oracle, tsql. (8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D
SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r

-- CASE[fixed]: pg-attz2 — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ti
SELECT now() AT TIME ZONE 'UTC', timezone('UTC', now())

-- CASE[open]: pg-avg-int — fails on mysql, tsql. FUNC-DIFF: source=(('1.5',),) target=(('1',),)
SELECT AVG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-avg-null — fails on mysql, tsql. FUNC-DIFF: source=(('2.33333',),) target=(('2',),)
SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)

-- CASE[fixed]: pg-baseconv — fails on tsql. (291, b"CAST or CONVERT: invalid attributes specified for type 'bit'DB-Lib error message 2
SELECT 255::bit(8)::text,to_hex(255),255::text

-- CASE[fixed]: pg-bit-fns — fails on mysql. (1305, 'FUNCTION unique_val_ff6c8e4945b4.GETBIT does not exist')
SELECT get_bit(B'1011', 0), set_bit(B'0000', 1, 1)

-- CASE[open]: pg-bit-negative — fails on mysql. FUNC-DIFF: source=(('-1', '-6', '3', '5'),) target=(('18446744073709551616', '184467440737
SELECT ~0, ~5, (-5) & 3, 5 & (-1)

-- CASE[open]: pg-bit-prec2 — fails on tsql. FUNC-DIFF: source=(('2', '8'),) target=(('3', '5'),)
SELECT 10 & 6 + 1, 1 << 2 + 1

-- CASE[open]: pg-bitnot — fails on mysql. FUNC-DIFF: source=(('-1',),) target=(('18446744073709551616',),)
SELECT ~0 AS r

-- CASE[open]: pg-bitops — fails on mysql. FUNC-DIFF: source=(('1', '7', '6', '-6', '10', '2'),) target=(('1', '7', '6', '18446744073
SELECT 5 & 3, 5 | 2, 5 # 3, ~5, 5 << 1, 5 >> 1

-- CASE[open]: pg-blob-length — fails on mysql, oracle, tsql. (195, b"'DECODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT LENGTH(decode('SGVsbG8=', 'base64')) AS r

-- CASE[open]: pg-bool-int-cast — fails on oracle. ORA-01722: unable to convert string value containing 't' to a number: 
SELECT 'true'::boolean::int AS r

-- CASE[open]: pg-bool-repr — fails on mysql. FUNC-DIFF: source=(('1', '1', 'true', '0', 'NULL'),) target=(('1', '1', '1', '0', 'NULL'),
SELECT (1>0), (1>0)::int, (1>0)::text, NOT (1>0), true AND NULL

-- CASE[open]: pg-bool-text2 — fails on mysql. FUNC-DIFF: source=(('true',),) target=(('1',),)
SELECT true::text AS r

-- CASE[open]: pg-bool-week — fails on oracle, tsql. (245, b"Conversion failed when converting the varchar value 't' to data type bit.DB-Lib er
SELECT 'true'::boolean, 't'::boolean, 1::boolean, EXTRACT(WEEK FROM DATE '2020-01-01')

-- CASE[open]: pg-bulk-insert — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
CREATE TABLE t (a INT); INSERT INTO t SELECT generate_series(1, 1000)

-- CASE[open]: pg-case-statement — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n INT) RETURNS TEXT AS $$ BEGIN CASE n WHEN 1 THEN RETURN 'one'; ELSE RETURN 'other'; END CASE; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-cast-bool2 — fails on oracle, tsql. (245, b"Conversion failed when converting the varchar value 'yes' to data type bit.DB-Lib 
SELECT '1'::boolean, 'yes'::boolean, 'off'::boolean, 't'::boolean

-- CASE[fixed]: pg-cast-chain2 — fails on tsql. (529, b'Explicit conversion from data type time to text is not allowed.DB-Lib error messag
SELECT '10:00'::time::text, now()::date::text, 42::bit(8)::int

-- CASE[open]: pg-cast-datetime2 — fails on oracle. ORA-01861: literal does not match format string
SELECT '2020-01-01 10:00'::date, '2020-01-01 10:00'::time, '10:00'::interval

-- CASE[open]: pg-cast-int — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT CAST(2.7 AS INT) AS r

-- CASE[open]: pg-cast-interval — fails on oracle. ORA-30089: missing or invalid <datetime field>
SELECT '1 day'::interval AS r

-- CASE[open]: pg-cast-interval3 — fails on oracle. ORA-30089: missing or invalid <datetime field>
SELECT '5 days'::interval::text, extract(days from '5 days'::interval)

-- CASE[open]: pg-cast-matrix — fails on oracle, tsql. (529, b'Explicit conversion from data type numeric to text is not allowed.DB-Lib error mes
SELECT 3.14::int, 3.14::text, 3.14::numeric(10,2), 3.14::double precision

-- CASE[open]: pg-cast-money — fails on oracle. ORA-00902: invalid datatype
SELECT '12.99'::numeric(4,1), '12.99'::numeric(3,0), 12.99::money

-- CASE[open]: pg-cast-point — fails on oracle, tsql. (243, b'Type POINT is not a defined system type.DB-Lib error message 20018, severity 16:\n
SELECT '(1,2)'::point AS r

-- CASE[open]: pg-cast-round-half — fails on tsql. FUNC-DIFF: source=(('8',),) target=(('7',),)
SELECT 7.5 :: int AS r

-- CASE[open]: pg-cast-tstz — fails on mysql, oracle, tsql. (243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity
SELECT '2020-01-01'::timestamptz AS r

-- CASE[fixed]: pg-char-encoding — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ascii('A'),chr(65),encode('AB','hex'),decode('4142','hex'),encode('AB','base64'),octet_length('AB')

-- CASE[fixed]: pg-check-array-len — fails on oracle. ORA-03099: unexpected item [ in a column definition
CREATE TABLE t (a INT PRIMARY KEY, path TEXT[], CONSTRAINT ck CHECK (array_length(path,1) > 0))

-- CASE[fixed]: pg-check-jsonb — fails on mysql, oracle, tsql. (195, b"'JSONB_TYPEOF' is not a recognized built-in function name.DB-Lib error message 200
CREATE TABLE t (id INT PRIMARY KEY, data JSONB, CONSTRAINT ck CHECK (jsonb_typeof(data) = 'object'))

-- CASE[open]: pg-check-notvalid — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) NOT VALID

-- CASE[open]: pg-check-xor — fails on tsql. (102, b"Incorrect syntax near '<'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
CREATE TABLE t (a INT, b INT, c INT, CONSTRAINT ck CHECK ((a IS NULL) != (b IS NULL)))

-- CASE[open]: pg-chr-ascii-unicode — fails on oracle. 'utf-8' codec can't decode byte 0xe9 in position 0: unexpected end of data
SELECT chr(233), ascii('é')

-- CASE[fixed]: pg-chr-concat — fails on mysql. FUNC-DIFF: source=(('AB',),) target=(('4142',),)
SELECT chr(65) || chr(66)

-- CASE[open]: pg-chr-unicode — fails on mysql, tsql. FUNC-DIFF: source=(('μ',),) target=(('NULL',),)
SELECT CHR(956) AS r

-- CASE[open]: pg-computed-func — fails on tsql. (8116, b'Argument data type text is invalid for argument 1 of lower function.DB-Lib error 
CREATE TABLE t (a TEXT, b TEXT GENERATED ALWAYS AS (lower(a)) STORED)

-- CASE[open]: pg-computed-jsonb — fails on mysql, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type JSONB.DB-Lib error messa
CREATE TABLE t (data JSONB, name TEXT GENERATED ALWAYS AS (data->>'name') STORED)

-- CASE[open]: pg-concat-null — fails on mysql. FUNC-DIFF: source=(('NULL', 'ab', 'a-b'),) target=(('NULL', 'NULL', 'a-b'),)
SELECT 'a'||NULL||'b', concat('a',NULL,'b'), concat_ws('-','a',NULL,'b')

-- CASE[fixed]: pg-convert-roundtrip — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co
SELECT convert_from(convert_to('héllo','UTF8'),'UTF8')

-- CASE[fixed]: pg-convert-to — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co
SELECT convert_to('abc', 'UTF8')

-- CASE[fixed]: pg-date-bin — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DA
SELECT date_bin('15 minutes', TIMESTAMP '2020-01-01 00:07', TIMESTAMP '2020-01-01')

-- CASE[open]: pg-date-diff-days — fails on mysql. FUNC-DIFF: source=(('60',),) target=(('200',),)
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r

-- CASE[open]: pg-date-part — fails on oracle. ORA-00907: missing right parenthesis
SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15')

-- CASE[open]: pg-date-plus-int — fails on mysql, oracle. FUNC-DIFF: source=(('2020-01-31',),) target=(('2020-01-31 00:00:00',),)
SELECT DATE '2020-01-01' + 30 AS r

-- CASE[open]: pg-date-trunc — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d

-- CASE[open]: pg-datetrunc-units — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT date_trunc('quarter', now()), date_trunc('decade', now())

-- CASE[open]: pg-decimal-scale — fails on mysql. FUNC-DIFF: source=(('3.33333', '3.33333', '3.33333', '2.25'),) target=(('3.33333', '3.3333
SELECT 10.00/3, 10/3.0, 10::numeric(10,4)/3, 1.5*1.5

-- CASE[open]: pg-div-precision — fails on mysql. FUNC-DIFF: source=(('0.333333',),) target=(('0.33333',),)
SELECT 1.0 / 3 AS r

-- CASE[open]: pg-double-cast — fails on oracle, tsql. (529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message
SELECT 123::text::int AS r

-- CASE[open]: pg-drop-default — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'DEFAULT'.DB-Lib error message 20018, severity 1
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP DEFAULT

-- CASE[open]: pg-drop-not-null — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP NOT NULL

-- CASE[open]: pg-dttypes — fails on oracle. ORA-30089: missing or invalid <datetime field>
CREATE TABLE t (a DATE, b TIME, c TIMESTAMP, d TIMESTAMPTZ, e TIMETZ, f INTERVAL, g TIMESTAMP(3))

-- CASE[open]: pg-dyn-count — fails on oracle, tsql. (102, b"Incorrect syntax near 'SELECT COUNT(*) FROM %I'.DB-Lib error message 20018, severi
CREATE FUNCTION f(tbl TEXT) RETURNS BIGINT AS $$ DECLARE n BIGINT; BEGIN EXECUTE format('SELECT COUNT(*) FROM %I', tbl) INTO n; RETURN n; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-emoji-len — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT LENGTH('😀') AS r

-- CASE[open]: pg-empty-is-null — fails on oracle. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT '' IS NULL AS r

-- CASE[fixed]: pg-encode-base64 — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ENCODE('abc'::bytea, 'base64') AS r

-- CASE[fixed]: pg-encode-decode — fails on mysql, oracle, tsql. (195, b"'DECODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ENCODE(DECODE('SGVsbG8=', 'base64'), 'hex')

-- CASE[open]: pg-epoch — fails on mysql, oracle, tsql. (155, b"'EPOCH' is not a recognized datepart option.DB-Lib error message 20018, severity 1
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01 00:00:00'), EXTRACT(EPOCH FROM INTERVAL '1 day')

-- CASE[fixed]: pg-except-all — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SELECT 1 EXCEPT ALL SELECT 2

-- CASE[open]: pg-exception-handler — fails on tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-exception-when — fails on oracle, tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS void AS $$ BEGIN INSERT INTO t VALUES(1); EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'dup'; WHEN others THEN RAISE; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-execute-using — fails on mysql. (1336, 'Dynamic SQL is not allowed in stored function or trigger')
CREATE FUNCTION f() RETURNS VOID AS $$ BEGIN EXECUTE 'INSERT INTO t VALUES ($1)' USING 5; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-expr-index — fails on mysql, oracle. ORA-02327: cannot create index on expression with data type LOB
CREATE TABLE t (a INT, b TEXT); CREATE INDEX ix ON t (lower(b))

-- CASE[open]: pg-extract-dow — fails on mysql, oracle, tsql. (155, b"'DOW' is not a recognized datepart option.DB-Lib error message 20018, severity 15:
SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d

-- CASE[open]: pg-extract-epoch — fails on mysql, oracle, tsql. (155, b"'EPOCH' is not a recognized datepart option.DB-Lib error message 20018, severity 1
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01') AS r

-- CASE[limit]: pg-fcollate — fails on mysql, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('c', 'B', '0'),) target=(('c', 'a', '1'),)
SELECT greatest('a','B','c'),least('a','B'),'a'<'B'

-- CASE[fixed]: pg-fetch-ties2 — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t ORDER BY id FETCH FIRST 5 ROWS WITH TIES

-- CASE[fixed]: pg-filter-subquery — fails on tsql. (130, b'Cannot perform an aggregate function on an expression containing an aggregate or a
CREATE TABLE t (id INT, n INT); CREATE TABLE u (id INT, v INT); SELECT id, COUNT(*) FILTER (WHERE n > (SELECT AVG(v) FROM u)) FROM t GROUP BY id

-- CASE[fixed]: pg-fk-full — fails on oracle. ORA-03075: unexpected item ON in an out-of-line constraint
CREATE TABLE t (id INT PRIMARY KEY, parent INT, CONSTRAINT fk FOREIGN KEY (parent) REFERENCES t(id) ON DELETE CASCADE ON UPDATE RESTRICT DEFERRABLE INITIALLY DEFERRED)

-- CASE[open]: pg-float-precision — fails on mysql. FUNC-DIFF: source=(('0.3', '0.3', '0.333333', '0.333333', '0.666667'),) target=(('0.3', '0
SELECT 0.1+0.2, 0.1::float+0.2::float, 1.0/3, (1.0/3)::float, 2::float/3

-- CASE[open]: pg-fmt-spec — fails on oracle. SILENT: source literal(s) ["'Dy Mon DD HH24:MI:SS YYYY'", "'AM HH12:MI'", "'DDD WW IW'"] a
SELECT to_char(now(),'Dy Mon DD HH24:MI:SS YYYY'),to_char(now(),'AM HH12:MI'),to_char(now(),'DDD WW IW')

-- CASE[open]: pg-fmt3 — fails on oracle. SILENT: source literal(s) ["'9G999D99'"] absent from valid output, no warning
SELECT to_char(1234.5678,'9G999D99'),to_char(-5,'S9')

-- CASE[open]: pg-for-update — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id INT); SELECT * FROM t FOR UPDATE

-- CASE[open]: pg-format-currency — fails on mysql, tsql. FUNC-DIFF: source=(('1,234,567.89', '1,234,567.89'),) target=(('FM999999991234567.89', 'FM
SELECT to_char(1234567.891,'FM999,999,990.00'), to_char(1234567.891,'FML999G999G990D00')

-- CASE[open]: pg-format-func — fails on oracle, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT format('%s=%s', 'a', 1) AS r

-- CASE[fixed]: pg-format2 — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT format('%s-%I-%L', 'a', 'col name', 'val'), concat_ws('|', 'a', NULL, 'b')

-- CASE[open]: pg-frac-seconds — fails on mysql, oracle, tsql. (155, b"'MICROSECONDS' is not a recognized datepart option.DB-Lib error message 20018, sev
SELECT TIMESTAMP '2020-01-01 10:20:30.123456', EXTRACT(MICROSECONDS FROM TIME '10:20:30.123456')

-- CASE[open]: pg-fround — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('1', '2', '3', '2.57'),) target=(('1', '2', '3', '3'),)
SELECT round(0.5::numeric),round(1.5::numeric),round(2.5::numeric),round(2.567::numeric,2)

-- CASE[open]: pg-fsubstr — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('abc', 'abc', 'bc'),) target=(('ab', 'a', 'bc'),)
SELECT substring('abc',0),substring('abc' from -1),substring('abc',2,10)

-- CASE[fixed]: pg-fulltext — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT to_tsvector('a cat') @@ to_tsquery('cat') AS r

-- CASE[fixed]: pg-fulltext2 — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id FROM t WHERE to_tsvector('english', s) @@ plainto_tsquery('english', 'term')

-- CASE[open]: pg-func-attrs — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near 'sql'.DB-Lib error message 20018, severity 15:\nGeneral SQL 
CREATE FUNCTION f() RETURNS INT AS $$ SELECT 1 $$ LANGUAGE sql SECURITY DEFINER STABLE PARALLEL SAFE

-- CASE[fixed]: pg-gen-months — fails on oracle. ORA-30089: missing or invalid <datetime field>
SELECT day::date FROM generate_series('2020-01-01', '2020-12-01', '1 month'::interval) day

-- CASE[open]: pg-gen-series-date — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '1 DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ
SELECT generate_series('2020-01-01'::date, '2020-01-05'::date, '1 day') AS d

-- CASE[open]: pg-gen-series-ord — fails on tsql. (102, b"Incorrect syntax near 'ORDINALITY'.DB-Lib error message 20018, severity 15:\nGener
SELECT * FROM generate_series(1, 10, 2) WITH ORDINALITY AS t(v, n)

-- CASE[open]: pg-gencol2 — fails on mysql. (1075, 'Incorrect table definition; there can be only one auto column and it must be defin
CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a*2) STORED, c INT GENERATED ALWAYS AS IDENTITY)

-- CASE[open]: pg-generate-series — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT generate_series(1, 5) AS r

-- CASE[open]: pg-gin-jsonb — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #2: Cannot find data type JSONB.DB-Lib error messa
CREATE TABLE t (a INT, b JSONB); CREATE INDEX ix ON t USING gin (b jsonb_path_ops)

-- CASE[open]: pg-greatest-null — fails on mysql, oracle. FUNC-DIFF: source=(('3',),) target=(('NULL',),)
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[open]: pg-greatest-string — fails on mysql, tsql. FUNC-DIFF: source=(('a',),) target=(('B',),)
SELECT GREATEST('a', 'B') AS r

-- CASE[open]: pg-grouping — fails on mysql, oracle, tsql. (8120, b"Column 't.a' is invalid in the select list because it is not contained in either 
SELECT a,sum(c),grouping(a) FROM (SELECT 1 a,3 c) t GROUP BY GROUPING SETS ((a),())

-- CASE[open]: pg-grouping-fn — fails on mysql, oracle, tsql. (8161, b'Argument 1 of the GROUPING function does not match any of the expressions in the 
SELECT x, GROUPING(x) FROM (VALUES (1)) v(x) GROUP BY CUBE (x)

-- CASE[open]: pg-grouping-sets — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())

-- CASE[open]: pg-grouping-sets2 — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, n, GROUPING(id), GROUPING(n) FROM t GROUP BY GROUPING SETS ((id),(n),())

-- CASE[fixed]: pg-groups2 — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, n, count(*) OVER (ORDER BY id GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM t

-- CASE[fixed]: pg-hash-all — fails on mysql, oracle, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT md5('abc'), encode(sha256('abc'::bytea), 'hex')

-- CASE[open]: pg-hash-fns — fails on mysql, oracle, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT lpad('x', 3), md5('x'), sha256('x'::bytea)

-- CASE[open]: pg-hex-literal — fails on oracle. ORA-00932: expression is of data type BINARY, which is incompatible with expected data typ
SELECT x'FF'::int AS h, 1.5e3 AS s

-- CASE[fixed]: pg-hexcast — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT encode('Hello'::bytea,'hex'),decode('48656c6c6f','hex')::text

-- CASE[fixed]: pg-inet-ops — fails on oracle, tsql. (243, b'Type cidr is not a defined system type.DB-Lib error message 20018, severity 16:\nG
SELECT '192.168.1.0/24'::cidr >> '192.168.1.5'::inet, abbrev('10.0.0.0/8'::cidr)

-- CASE[fixed]: pg-initcap — fails on mysql, oracle, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r

-- CASE[fixed]: pg-insert-select-conflict — fails on oracle, tsql. (208, b"Invalid object name 'dbo.GENERATE_SERIES'.DB-Lib error message 20018, severity 16:
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); INSERT INTO t (id, n) SELECT g, g*2 FROM generate_series(1,5) g ON CONFLICT DO NOTHING

-- CASE[open]: pg-intdiv — fails on mysql, oracle. FUNC-DIFF: source=(('2',),) target=(('2.5',),)
SELECT 5 / 2 AS r

-- CASE[fixed]: pg-intersect-all — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SELECT 1 INTERSECT ALL SELECT 1

-- CASE[open]: pg-interval-arith — fails on mysql, oracle, tsql. (207, b"Invalid column name 'INTERVAL'.DB-Lib error message 20018, severity 16:\nGeneral S
SELECT NOW() - INTERVAL '1 day', DATE '2020-01-01' + 7

-- CASE[fixed]: pg-interval-out — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '400 DAYS'.DB-Lib error message 20018, severity 15:\nGeneral
SELECT INTERVAL '1 year 2 months 3 days', INTERVAL '1.5 hours', justify_interval(INTERVAL '400 days')

-- CASE[open]: pg-json-aggs — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_
SELECT json_agg(x), json_object_agg(x::text, x*2) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: pg-json-build — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_build_array(1,'a',NULL,true),jsonb_build_object('k','v')

-- CASE[fixed]: pg-json-meta — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_typeof('[1]'),jsonb_array_length('[1,2,3]'),jsonb_pretty('{"a":1}')

-- CASE[fixed]: pg-json-mod — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_set('{}','{a}','1'),jsonb_insert('{}','{a}','1'),'{"a":1}'::jsonb-'a','{"a":1}'::jsonb||'{"b":2}'

-- CASE[fixed]: pg-json-path — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_path_query('{"a":[1,2]}','$.a[*]'),jsonb_path_exists('{"a":1}','$.a')

-- CASE[fixed]: pg-jsonb-agg — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSONB_AGG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: pg-jsonb-build — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSONB_BUILD_OBJECT('a', 1, 'b', 2)

-- CASE[fixed]: pg-jsonb-each — fails on oracle, tsql. (208, b"Invalid object name 'dbo.jsonb_each'.DB-Lib error message 20018, severity 16:\nGen
SELECT key, value FROM jsonb_each('{"a":1,"b":2}'::jsonb)

-- CASE[fixed]: pg-jsonb-elements-ord — fails on oracle, tsql. (102, b"Incorrect syntax near 'ORDINALITY'.DB-Lib error message 20018, severity 15:\nGener
SELECT * FROM jsonb_array_elements('[1,2,3]'::jsonb) WITH ORDINALITY

-- CASE[fixed]: pg-jsonb-fns2 — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_pretty('{"a":1}'::jsonb), jsonb_strip_nulls('{"a":null}'::jsonb)

-- CASE[fixed]: pg-jsonb-modify — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_set('{}', '{a}', '1'), '{"a":1}'::jsonb - 'a'

-- CASE[fixed]: pg-jsonb-path-query — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_path_query('{"a":[1,2]}', '$.a[*]') AS r

-- CASE[fixed]: pg-jsonb-recordset — fails on tsql. (317, b"Table-valued function 'jsonb_to_recordset' cannot have a column alias.DB-Lib error
SELECT * FROM jsonb_to_recordset('[{"a":1}]') AS x(a INT)

-- CASE[fixed]: pg-justify — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '1 mon 40 days'.DB-Lib error message 20018, severity 15:\nGe
SELECT JUSTIFY_INTERVAL(INTERVAL '1 mon 40 days') AS r

-- CASE[open]: pg-left-neg — fails on mysql. FUNC-DIFF: source=(('ab',),) target=(('',),)
SELECT LEFT('abc', -1) AS r

-- CASE[open]: pg-left-round — fails on tsql. FUNC-DIFF: source=(('hel',),) target=(('he',),)
SELECT LEFT('hello', 2.9::int) AS r

-- CASE[limit]: pg-like-cs — fails on mysql, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[open]: pg-like-escape — fails on oracle. FUNC-DIFF: source=(('1', '0', '1'),) target=(('0', '0', '1'),)
SELECT 'a%b' LIKE 'a\%b', 'AbC' LIKE 'abc', 'AbC' ILIKE 'abc'

-- CASE[open]: pg-log-2arg — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('0.333333',),)
SELECT LOG(2, 8) AS r

-- CASE[open]: pg-log-base — fails on mysql, tsql. FUNC-DIFF: source=(('2',),) target=(('4.60517',),)
SELECT LOG(100) AS r

-- CASE[open]: pg-loop-notice — fails on tsql. (443, b"Invalid use of a side-effecting operator 'PRINT' within a function.DB-Lib error me
CREATE FUNCTION f() RETURNS void AS $$ DECLARE i INT:=0; BEGIN LOOP i:=i+1; EXIT WHEN i>=3; END LOOP; RAISE NOTICE 'done'; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-lpad-shrink — fails on tsql. FUNC-DIFF: source=(('hel',),) target=(('llo',),)
SELECT LPAD('hello', 3) AS r

-- CASE[fixed]: pg-ltrim-set — fails on mysql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT ltrim('xxabc', 'x') AS r

-- CASE[fixed]: pg-make-date — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_DATE(2020, 6, 15), MAKE_TIME(10, 30, 0)

-- CASE[fixed]: pg-md5 — fails on oracle, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc') AS r

-- CASE[open]: pg-mod-decimal — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT MOD(10, 3.5::numeric) AS r

-- CASE[open]: pg-multi-out — fails on oracle. FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared
CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-name-locale — fails on mysql, tsql. FUNC-DIFF: source=(('Monday', 'June', 'Monday'),) target=(('ua20', '6onA12', '6ua20'),)
SELECT to_char(DATE '2020-06-15','Day'), to_char(DATE '2020-06-15','Month'), trim(to_char(DATE '2020-06-15','FMDay'))

-- CASE[open]: pg-named-exception — fails on oracle, tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1/0; EXCEPTION WHEN division_by_zero THEN RETURN -1; WHEN OTHERS THEN RAISE; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-named-window — fails on oracle. ORA-30485: missing ORDER BY expression in the window specification
SELECT x,sum(x) OVER w,rank() OVER w FROM (SELECT 1 x UNION ALL SELECT 2) t WINDOW w AS (ORDER BY x)

-- CASE[fixed]: pg-named-window2 — fails on oracle. ORA-30485: missing ORDER BY expression in the window specification
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id, LAG(n) OVER w, LEAD(n) OVER w FROM t WINDOW w AS (PARTITION BY s ORDER BY id)

-- CASE[open]: pg-nan-cmp — fails on mysql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'NaN'::numeric > 1 AS r

-- CASE[open]: pg-nested-call — fails on oracle. PROCEDURE OUTER_P compiled INVALID (line 4): PLS-00201: identifier 'INNER_P' must be decla
CREATE PROCEDURE outer_p() AS $$ BEGIN CALL inner_p(); END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-network-types — fails on oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag
CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)

-- CASE[open]: pg-not-null-is-null — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT (NOT NULL) IS NULL AS r

-- CASE[fixed]: pg-now-fns — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'CURRENT_TIME'.DB-Lib error message 20018, sever
SELECT now(), current_date, current_time, localtimestamp, clock_timestamp()

-- CASE[fixed]: pg-now-variants — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '3'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT now(), current_timestamp, current_timestamp(3), current_date, current_time, localtimestamp, clock_timestamp()

-- CASE[open]: pg-num-literals — fails on mysql. FUNC-DIFF: source=(('1000', '0.015', '0.5', '5', '31'),) target=(('1000', '0.015', '0.5', 
SELECT 1e3, 1.5e-2, .5, 5., 0x1F::text

-- CASE[fixed]: pg-num-nonnulls — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUM_NONNULLS(1, NULL, 2) AS r

-- CASE[open]: pg-num-to-str — fails on mysql. FUNC-DIFF: source=(('n=5', 'x=5.50', 'd=0.33333333333333333333', '5.5'),) target=(('n=5', 
SELECT 'n='||5, 'x='||5.50, 'd='||(1.0/3), 5.50::text

-- CASE[open]: pg-numfmt-lead — fails on mysql. FUNC-DIFF: source=(('0.5',),) target=(('0',),)
SELECT to_char(0.5, '0.00') AS r

-- CASE[open]: pg-numfmt-spec — fails on oracle. SILENT: source literal(s) ["'L9G999D99MI'"] absent from valid output, no warning
SELECT to_char(1234.5,'L9G999D99MI'),to_char(-5,'999PR'),to_char(255,'FMRN')

-- CASE[open]: pg-numfmt-thousands — fails on mysql, tsql. FUNC-DIFF: source=(('1,234,567.89',),) target=(('9999999123456900',),)
SELECT to_char(1234567.891, '9,999,999.99') AS r

-- CASE[fixed]: pg-numnulls — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.nu
SELECT num_nonnulls(1,NULL,2),num_nulls(1,NULL,2)

-- CASE[open]: pg-numtypes — fails on mysql. (1075, 'Incorrect table definition; there can be only one auto column and it must be defin
CREATE TABLE t (a SMALLINT, b INT, c BIGINT, d NUMERIC(10,2), e REAL, f DOUBLE PRECISION, g SERIAL, h MONEY)

-- CASE[open]: pg-order-case-sens — fails on mysql, tsql. FUNC-DIFF: source=(('Apple',), ('Cherry',), ('banana',)) target=(('Apple',), ('banana',), 
SELECT x FROM (SELECT 'Apple' x UNION SELECT 'banana' UNION SELECT 'Cherry') t ORDER BY x

-- CASE[open]: pg-order-nulls-default — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))
SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x

-- CASE[open]: pg-overlay — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV
SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o

-- CASE[open]: pg-pad-repeat — fails on oracle. ORA-00904: "REPEAT": invalid identifier
SELECT lpad('7',3,'0'),rpad('7',3,'x'),repeat('ab',3),reverse('abc'),repeat(' ',3)

-- CASE[open]: pg-pi-fns — fails on oracle. ORA-00904: "PI": invalid identifier
SELECT trunc(pi()::numeric, 4), round(pi()::numeric, 4)

-- CASE[open]: pg-position-case — fails on mysql, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT POSITION('a' IN 'ABC') AS r

-- CASE[open]: pg-position-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT POSITION('' IN 'abc') AS r

-- CASE[fixed]: pg-quote — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU
SELECT QUOTE_LITERAL('O''Brien'), QUOTE_IDENT('my col')

-- CASE[fixed]: pg-range-types — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m
CREATE TABLE t (rng INT4RANGE, tsr TSRANGE)

-- CASE[open]: pg-realworld-transfer — fails on oracle, tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE TABLE accounts (id SERIAL PRIMARY KEY, balance NUMERIC(12,2) DEFAULT 0 CHECK (balance >= 0));
CREATE TABLE ledger (id SERIAL PRIMARY KEY, account_id INT REFERENCES accounts(id) ON DELETE CASCADE, amount NUMERIC(12,2), ts TIMESTAMPTZ DEFAULT now());
CREATE FUNCTION transfer(from_id INT, to_id INT, amt NUMERIC) RETURNS VOID AS $$
BEGIN UPDATE accounts SET balance = balance - amt WHERE id = from_id;
UPDATE accounts SET balance = balance + amt WHERE id = to_id;
INSERT INTO ledger (account_id, amount) VALUES (from_id, -amt), (to_id, amt);
EXCEPTION WHEN check_violation THEN RAISE EXCEPTION 'insufficient funds'; END; $$ LANGUAGE plpgsql;

-- CASE[open]: pg-recursive-func — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n INT) RETURNS INT AS $$ BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-regexp-backref — fails on mysql, oracle. ORA-01722: unable to convert string value containing 'g' to a number: 
SELECT regexp_replace('a1b2', '(\d)', '[\1]', 'g') AS r

-- CASE[fixed]: pg-regexp-cnt — fails on mysql. (1305, 'FUNCTION unique_val_a1fe6b8252a9.REGEXP_COUNT does not exist')
SELECT regexp_count('a1b2','[0-9]'),regexp_instr('a1b2','[0-9]',1,2)

-- CASE[fixed]: pg-regexp-matches — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE
SELECT REGEXP_MATCHES('a1b2', '[0-9]', 'g') AS r

-- CASE[fixed]: pg-regexp-split-table — fails on oracle, tsql. (208, b"Invalid object name 'dbo.regexp_split_to_table'.DB-Lib error message 20018, severi
SELECT * FROM regexp_split_to_table('a,b,c', ',')

-- CASE[fixed]: pg-repeat-left-right — fails on oracle. ORA-00904: "RIGHT": invalid identifier
SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)

-- CASE[open]: pg-rollup — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)

-- CASE[open]: pg-rollup2 — fails on mysql, oracle, tsql. (8120, b"Column 't.a' is invalid in the select list because it is not contained in either 
SELECT a,b,sum(c) FROM (SELECT 1 a,2 b,3 c) t GROUP BY ROLLUP(a,b)

-- CASE[open]: pg-round-1005 — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('1.01',),) target=(('1',),)
SELECT ROUND(1.005::numeric, 2) AS r

-- CASE[open]: pg-round-2675 — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('2.68',),) target=(('3',),)
SELECT ROUND(2.675::numeric, 2) AS r

-- CASE[open]: pg-savepoint — fails on mysql, tsql. (156, b"Incorrect syntax near the keyword 'AS'.DB-Lib error message 20018, severity 15:\nG
BEGIN; SAVEPOINT sp; ROLLBACK TO SAVEPOINT sp; COMMIT

-- CASE[fixed]: pg-scale — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.sc
SELECT scale(1.230), trim_scale(1.230)

-- CASE[open]: pg-scientific — fails on mysql. FUNC-DIFF: source=(('100000000000000000000', '1e-20', '123456789012345677877719597056'),) 
SELECT 1e20::float, 1e-20::float, 123456789012345678901234567890::numeric

-- CASE[open]: pg-select-into-ctas — fails on oracle. ORA-00905: missing keyword
CREATE TABLE t (id INT);
SELECT id INTO TEMP t2 FROM t;
CREATE TABLE t3 AS SELECT * FROM t;

-- CASE[fixed]: pg-seq-use — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne
CREATE SEQUENCE s; SELECT nextval('s'),currval('s'),setval('s',10)

-- CASE[fixed]: pg-sequence — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne
CREATE SEQUENCE seq; SELECT nextval('seq'), currval('seq')

-- CASE[fixed]: pg-serial-bit — fails on oracle, tsql. (2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit
CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))

-- CASE[open]: pg-set-default — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5

-- CASE[fixed]: pg-setweight — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.se
SELECT setweight(to_tsvector('cat'), 'A') AS r

-- CASE[fixed]: pg-size-funcs — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.pg
SELECT pg_size_pretty(1024::bigint), pg_relation_size('pg_class')

-- CASE[fixed]: pg-spectypes — fails on oracle, tsql. (2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit
CREATE TABLE t (a BYTEA, b BIT(8), c VARBIT(16), d BOOLEAN, e UUID, f XML, g JSON, h JSONB)

-- CASE[fixed]: pg-split-part — fails on mysql, oracle, tsql. (195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018
SELECT SPLIT_PART('a,b,c', ',', 2) AS r

-- CASE[open]: pg-srf-in-select — fails on oracle, tsql. (208, b"Invalid object name 'dbo.GENERATE_SERIES'.DB-Lib error message 20018, severity 16:
SELECT g, g*g FROM generate_series(1,3) g

-- CASE[limit]: pg-str-lt — fails on mysql, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'apple' < 'Banana' AS r

-- CASE[open]: pg-stragg-order — fails on oracle, tsql. (529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message
SELECT string_agg(x::text,',' ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[open]: pg-string-agg-order — fails on oracle, tsql. (529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message
SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: pg-string-fns2 — fails on mysql, oracle, tsql. (195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018
SELECT split_part('a,b,c', ',', 2), left('abc',-1), right('abc',-1)

-- CASE[fixed]: pg-string-fns3 — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT starts_with('abc','ab'), string_to_array('a.b.c','.')

-- CASE[fixed]: pg-string-split-fns — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.st
SELECT string_to_table('a,b,c', ','), regexp_split_to_array('a1b2', '\d')

-- CASE[fixed]: pg-string-to-array — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT string_to_array('a,b,c', ',')

-- CASE[open]: pg-strpos-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT STRPOS('', '') AS r

-- CASE[open]: pg-substr-edge — fails on mysql. FUNC-DIFF: source=(('hello', 'el', 'hell', 'ello'),) target=(('llo', 'el', '', ''),)
SELECT substring('hello',-3), substr('hello',2,2), left('hello',-1), right('hello',-1)

-- CASE[open]: pg-substr-zero — fails on mysql, oracle. FUNC-DIFF: source=(('ab',),) target=(('abc',),)
SELECT SUBSTRING('abcdef', 0, 3) AS r

-- CASE[open]: pg-substring-escape — fails on oracle, tsql. (8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib
SELECT substring('a1b2' from '([a-z])([0-9])' for '#') AS r

-- CASE[open]: pg-substring-regex — fails on oracle, tsql. (8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib
SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r

-- CASE[open]: pg-synonym-as-view — fails on oracle. ORA-00955: name is already used by an existing object
CREATE TABLE t (a INT); CREATE VIEW syn AS SELECT * FROM t

-- CASE[open]: pg-tablesample — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id INT); SELECT * FROM t TABLESAMPLE BERNOULLI(50)

-- CASE[open]: pg-tochar-fmts — fails on oracle. SILENT: source literal(s) ["'Day'", "'FMDay'", "'TZ'"] absent from valid output, no warnin
SELECT to_char(now(),'Day'), to_char(now(),'FMDay'), to_char(now(),'IW'), to_char(now(),'TZ')

-- CASE[open]: pg-tochar-iso — fails on mysql, tsql. (8116, b'Argument data type timestamp is invalid for argument 1 of format function.DB-Lib 
SELECT to_char(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r

-- CASE[open]: pg-tochar-neg — fails on mysql, tsql. FUNC-DIFF: source=(('-1234.5',),) target=(('-9999123599',),)
SELECT to_char(-1234.5, '9999.99') AS r

-- CASE[open]: pg-todate2 — fails on mysql. (1305, 'FUNCTION unique_val_2ac6422f99c6.STR_TO_TIME does not exist')
SELECT to_date('06/15/2020','MM/DD/YYYY'),to_timestamp('2020-06-15 10:30','YYYY-MM-DD HH24:MI')

-- CASE[open]: pg-tohex2 — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT to_hex(255), to_char(255, 'XX')

-- CASE[open]: pg-totimestamp-long — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ST
SELECT to_timestamp('June 15 2020', 'Month DD YYYY') AS r

-- CASE[limit]: pg-trailing-eq — fails on oracle, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'a ' = 'a' AS r

-- CASE[limit]: pg-trailing-space-cmp — fails on mysql, oracle, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0', '1', '0'),) target=(('1', '1', '1'),)
SELECT 'a'='a ', 'a'::char(2)='a'::char(2), 'abc'='ABC'

-- CASE[fixed]: pg-translate — fails on mysql. (1305, 'FUNCTION unique_val_5e892bc4b99a.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r

-- CASE[fixed]: pg-trig — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.AT
SELECT atan2(1,1), degrees(pi()), radians(180), cot(1), sind(30)

-- CASE[fixed]: pg-trim-both-chars — fails on oracle. ORA-30001: trim set should have only one character
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS t

-- CASE[open]: pg-trim-len — fails on oracle, tsql. FUNC-DIFF: source=(('2', '0'),) target=(('0', '0'),)
SELECT CHAR_LENGTH('  '), LENGTH(TRIM('  '))

-- CASE[fixed]: pg-trim-translate — fails on tsql. FUNC-DIFF: source=(('hi', '7', 'XbZ'),) target=(('', '', 'XbZ'),)
SELECT trim(both 'x' from 'xxhixx'), ltrim('007','0'), translate('abc','ac','XZ')

-- CASE[open]: pg-truncate-restart — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near 'RESTART'.DB-Lib error message 20018, severity 15:\nGeneral 
CREATE TABLE t (id INT); TRUNCATE TABLE t RESTART IDENTITY CASCADE

-- CASE[fixed]: pg-ts-headline — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ts
SELECT ts_headline('the quick fox', to_tsquery('fox')) AS r

-- CASE[fixed]: pg-ts-rank — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ts
SELECT ts_rank(to_tsvector('the cat'), to_tsquery('cat')) AS r

-- CASE[fixed]: pg-tstzrange — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '1 DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ
SELECT tstzrange(now(), now() + INTERVAL '1 day') AS r

-- CASE[open]: pg-tz-convert — fails on mysql, oracle, tsql. (8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D
SELECT TIMESTAMP '2020-06-15 10:00:00' AT TIME ZONE 'America/New_York', now() AT TIME ZONE 'UTC'

-- CASE[open]: pg-tz-interval — fails on oracle. ORA-30089: missing or invalid <datetime field>
CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)

-- CASE[open]: pg-unicode-escape — fails on mysql, oracle, tsql. (207, b"Invalid column name 'U'.DB-Lib error message 20018, severity 16:\nGeneral SQL Serv
SELECT U&'\0041' AS r

-- CASE[open]: pg-unique-nulls-notdistinct — fails on mysql, oracle. ORA-03050: invalid identifier: "UNIQUE" is a reserved word
CREATE TABLE t (a INT, b INT, UNIQUE NULLS NOT DISTINCT (a, b))

-- CASE[open]: pg-week — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT EXTRACT(WEEK FROM DATE '2020-01-05') AS r

-- CASE[open]: pg-week-2016 — fails on mysql, tsql. FUNC-DIFF: source=(('53',),) target=(('1',),)
SELECT EXTRACT(WEEK FROM DATE '2016-01-01') AS r

-- CASE[open]: pg-week-jan1 — fails on mysql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT EXTRACT(WEEK FROM DATE '2020-01-01') AS r

-- CASE[fixed]: pg-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT width_bucket(5, 0, 10, 5) AS r

-- CASE[open]: pg-xmlelement — fails on mysql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT XMLELEMENT(NAME foo, 'bar') AS r

-- CASE[open]: pg-xmlelement2 — fails on mysql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT xmlelement(name foo, 'bar')

-- CASE[fixed]: pg-xpath — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.xp
SELECT xpath('/a/text()', '<a>1</a>'::xml)

-- CASE[fixed]: pg15-merge — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPDATE SET n=s.n WHEN NOT MATCHED THEN INSERT VALUES (s.id, s.n)

-- CASE[open]: po-agg-bit — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.BI
SELECT BIT_AND(x),BIT_OR(x),BIT_XOR(x) FROM (VALUES (3),(5),(6)) v(x)

-- CASE[open]: po-distinct-case — fails on mysql, tsql. FUNC-DIFF: source=(('A',), ('B',), ('a',)) target=(('A',), ('B',))
SELECT DISTINCT x FROM (VALUES ('a'),('A'),('a'),('B')) v(x) ORDER BY x

-- CASE[open]: po-distinct-null — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('2',), ('NULL',)) target=(('NULL',), ('1',), ('2',))
SELECT DISTINCT x FROM (VALUES (1),(NULL),(1),(NULL),(2)) v(x) ORDER BY x

-- CASE[open]: po-group-case — fails on mysql, tsql. FUNC-DIFF: source=(('A', '1'), ('a', '1'), ('b', '1')) target=(('A', '2'), ('b', '1'))
SELECT x, COUNT(*) FROM (VALUES ('a'),('A'),('b')) v(x) GROUP BY x ORDER BY x

-- CASE[open]: po-group-null — fails on mysql, tsql. FUNC-DIFF: source=(('1', '2'), ('NULL', '2')) target=(('NULL', '2'), ('1', '2'))
SELECT x, COUNT(*) FROM (VALUES (1),(NULL),(1),(NULL)) v(x) GROUP BY x ORDER BY x

-- CASE[open]: po-order-strings — fails on mysql. FUNC-DIFF: source=(('Apple',), ('Banana',), ('banana',), ('cherry',)) target=(('Apple',), 
SELECT x FROM (VALUES ('banana'),('Apple'),('cherry'),('Banana')) v(x) ORDER BY x

-- CASE[fixed]: postgresql-drop-CHECK — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)
CREATE TABLE t (age INT CHECK (age >= 0))

-- CASE[open]: postgresql-drop-DEFERRABLE — fails on oracle. SILENT CLAUSE DROP: 'DEFERRABLE' absent from valid oracle output, no warning (target suppo
CREATE TABLE t (id INT PRIMARY KEY DEFERRABLE INITIALLY DEFERRED)

-- CASE[fixed]: postgresql-drop-ON\s+DELETE\s+ — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'ON\s+DELETE\s+CASCADE' absent from valid tsql output, no warning (tar
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE CASCADE)

-- CASE[fixed]: postgresql-drop-ON\s+UPDATE\s+ — fails on mysql. SILENT CLAUSE DROP: 'ON\s+UPDATE\s+CASCADE' absent from valid mysql output, no warning (ta
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON UPDATE CASCADE)

-- CASE[open]: postgresql-drop2-100|START — fails on oracle, tsql. SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning
CREATE TABLE t (id INT GENERATED BY DEFAULT AS IDENTITY (START WITH 100 INCREMENT BY 5))

-- CASE[open]: postgresql-drop2-CONCURRENTLY — fails on mysql, tsql. SILENT CLAUSE DROP: 'CONCURRENTLY' absent from valid tsql output, no warning
CREATE TABLE t (a INT); CREATE INDEX CONCURRENTLY ix ON t (a)

-- CASE[open]: postgresql-drop2-EXCLUDE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'EXCLUDE' absent from valid tsql output, no warning
CREATE TABLE t (a INT, EXCLUDE USING btree (a WITH =))

-- CASE[open]: postgresql-drop2-NULLS\s+FIRS — fails on oracle. SILENT CLAUSE DROP: 'NULLS\s+FIRST' absent from valid oracle output, no warning
CREATE TABLE t (a INT); CREATE INDEX ix ON t (a NULLS FIRST)

-- CASE[open]: postgresql-drop4-BY\s+DEFAULT — fails on tsql. SILENT CLAUSE DROP: 'BY\s+DEFAULT|GENERATED' absent from valid tsql output, no warning
CREATE TABLE t (a INT GENERATED BY DEFAULT AS IDENTITY)

-- CASE[open]: postgresql-drop4-COLLATE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning
CREATE TABLE t (a TEXT COLLATE "en_US")

-- CASE[open]: postgresql-drop4-MATCH\s+FULL — fails on oracle. SILENT CLAUSE DROP: 'MATCH\s+FULL' absent from valid oracle output, no warning
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) MATCH FULL)

-- CASE[open]: postgresql-drop5-CHECK|IN\s*\ — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'CHECK|IN\s*\(' absent from valid tsql output, no warning
CREATE TABLE t (a INT CHECK (a IN (1,2,3)))

-- CASE[fixed]: postgresql-drop5-REFERENCES — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'REFERENCES' absent from valid tsql output, no warning
CREATE TABLE t (a INT PRIMARY KEY, b INT REFERENCES t(a))

-- CASE[open]: postgresql-qdrop-FOR\s+UPDATE — fails on tsql. SILENT CLAUSE DROP: 'FOR\s+UPDATE' absent from valid tsql output, no warning
SELECT x FROM (VALUES (1),(2)) v(x) FOR UPDATE

-- CASE[open]: postgresql-qdrop-ROWS\s+BETWE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'ROWS\s+BETWEEN' absent from valid tsql output, no warning
SELECT x, SUM(x) OVER (ORDER BY x ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM (VALUES (1),(2)) v(x)

