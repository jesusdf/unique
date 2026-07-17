-- Challenge fixtures — PostgreSQL / PL-pgSQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: pg-accent-eq — fails on mysql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'Ä' = 'A' AS r

-- CASE[open]: pg-age — fails on mysql, oracle, tsql. (195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a

-- CASE[open]: pg-alter-add — fails on mysql, oracle. ORA-30649: missing DIRECTORY keyword
CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'

-- CASE[open]: pg-alter-type — fails on oracle. ORA-01735: invalid ALTER TABLE option
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a TYPE BIGINT

-- CASE[open]: pg-any-array-subquery — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near 'ARRAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ
CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a WHERE id = ANY(ARRAY(SELECT id FROM b))

-- CASE[open]: pg-array-agg — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT ARRAY_AGG(x ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-array-any — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT 3 = ANY(ARRAY[1,2,3]) AS r

-- CASE[open]: pg-array-concat — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT ARRAY[1,2,3] || ARRAY[4,5] AS r

-- CASE[open]: pg-array-index2 — fails on mysql. FUNC-DIFF: source=(('2',),) target=()
SELECT (ARRAY[1,2,3])[2] AS r

-- CASE[open]: pg-array-jsonb — fails on mysql, oracle. ORA-03099: unexpected item [ in a column definition
CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)

-- CASE[open]: pg-array-subquery — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT ARRAY(SELECT generate_series(1,3)) AS r

-- CASE[open]: pg-array-to-string — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT array_to_string(ARRAY[1,2,3], ',')

-- CASE[open]: pg-ascii-empty — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('NULL',),)
SELECT ASCII('') AS r

-- CASE[open]: pg-at-time-zone — fails on mysql, oracle, tsql. (8116, b'Argument data type timestamp is invalid for argument 1 of AT TIME ZONE function.D
SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r

-- CASE[open]: pg-avg-int — fails on tsql. FUNC-DIFF: source=(('1.5',),) target=(('1',),)
SELECT AVG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-avg-null — fails on mysql, tsql. FUNC-DIFF: source=(('2.33333',),) target=(('2',),)
SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)

-- CASE[open]: pg-before-update-trg — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT PRIMARY KEY, n INT, updated TIMESTAMP);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN NEW.updated := now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg BEFORE UPDATE ON t FOR EACH ROW EXECUTE FUNCTION trg_fn();

-- CASE[open]: pg-bitnot — fails on mysql. FUNC-DIFF: source=(('-1',),) target=(('18446744073709551616',),)
SELECT ~0 AS r

-- CASE[open]: pg-bool-int-cast — fails on oracle. ORA-01722: unable to convert string value containing 't' to a number: 
SELECT 'true'::boolean::int AS r

-- CASE[open]: pg-bool-text2 — fails on mysql. FUNC-DIFF: source=(('true',),) target=(('1',),)
SELECT true::text AS r

-- CASE[open]: pg-bulk-insert — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
CREATE TABLE t (a INT); INSERT INTO t SELECT generate_series(1, 1000)

-- CASE[open]: pg-caret-power — fails on mysql. FUNC-DIFF: source=(('8',),) target=()
SELECT 2 ^ 3 AS r

-- CASE[open]: pg-case-statement — fails on tsql. (455, b'The last statement included within a function must be a return statement.DB-Lib er
CREATE FUNCTION f(n INT) RETURNS TEXT AS $$ BEGIN CASE n WHEN 1 THEN RETURN 'one'; ELSE RETURN 'other'; END CASE; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-cast-array — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT '{1,2,3}'::int[] AS r

-- CASE[open]: pg-cast-int — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT CAST(2.7 AS INT) AS r

-- CASE[open]: pg-cast-interval — fails on mysql, oracle. ORA-30089: missing or invalid <datetime field>
SELECT '1 day'::interval AS r

-- CASE[open]: pg-cast-point — fails on mysql, oracle, tsql. (243, b'Type POINT is not a defined system type.DB-Lib error message 20018, severity 16:\n
SELECT '(1,2)'::point AS r

-- CASE[open]: pg-cast-round-half — fails on tsql. FUNC-DIFF: source=(('8',),) target=(('7',),)
SELECT 7.5 :: int AS r

-- CASE[open]: pg-cast-tstz — fails on mysql, oracle, tsql. (243, b'Type TIMESTAMPTZ is not a defined system type.DB-Lib error message 20018, severity
SELECT '2020-01-01'::timestamptz AS r

-- CASE[open]: pg-chr-concat — fails on mysql. FUNC-DIFF: source=(('AB',),) target=(('4142',),)
SELECT chr(65) || chr(66)

-- CASE[open]: pg-chr-unicode — fails on mysql, tsql. FUNC-DIFF: source=(('μ',),) target=(('NULL',),)
SELECT CHR(956) AS r

-- CASE[open]: pg-collate — fails on mysql. (1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT 'a' < 'B' COLLATE "C" AS r

-- CASE[open]: pg-collate-cmp — fails on mysql. FUNC-DIFF: source=(('0',),) target=()
SELECT 'A' = 'a' COLLATE "C" AS r

-- CASE[open]: pg-collate2 — fails on mysql. (1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT 'abc' COLLATE "C" AS r

-- CASE[open]: pg-comment-on — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT); COMMENT ON COLUMN t.a IS 'the a column'

-- CASE[open]: pg-comment-table — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT); COMMENT ON TABLE t IS 'my table'

-- CASE[open]: pg-composite-in-table — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type money_amt.DB-Lib error m
CREATE TYPE money_amt AS (amount NUMERIC, currency TEXT); CREATE TABLE t (price money_amt)

-- CASE[open]: pg-composite-type — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TYPE addr AS (street TEXT, city TEXT)

-- CASE[open]: pg-computed-array — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (dims INT[], area INT GENERATED ALWAYS AS (dims[1] * dims[2]) STORED)

-- CASE[open]: pg-computed-func — fails on tsql. (8116, b'Argument data type text is invalid for argument 1 of lower function.DB-Lib error 
CREATE TABLE t (a TEXT, b TEXT GENERATED ALWAYS AS (lower(a)) STORED)

-- CASE[open]: pg-computed-jsonb — fails on mysql, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type JSONB.DB-Lib error messa
CREATE TABLE t (data JSONB, name TEXT GENERATED ALWAYS AS (data->>'name') STORED)

-- CASE[open]: pg-convert-to — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co
SELECT convert_to('abc', 'UTF8')

-- CASE[open]: pg-create-role — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE ROLE r LOGIN PASSWORD 'x'

-- CASE[open]: pg-cte-cycle — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n<3) CYCLE n SET is_cycle USING path SELECT * FROM r

-- CASE[open]: pg-cte-delete-insert — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); WITH moved AS (DELETE FROM t WHERE n < 0 RETURNING *) INSERT INTO t SELECT * FROM moved

-- CASE[open]: pg-cte-search — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n<3) SEARCH DEPTH FIRST BY n SET ord SELECT * FROM r

-- CASE[open]: pg-date-diff-days — fails on mysql. FUNC-DIFF: source=(('60',),) target=(('200',),)
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r

-- CASE[open]: pg-date-part — fails on oracle. ORA-00907: missing right parenthesis
SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15')

-- CASE[open]: pg-date-trunc — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d

-- CASE[open]: pg-div-fn2 — fails on mysql. FUNC-DIFF: source=(('3',),) target=()
SELECT div(10, 3) AS r

-- CASE[open]: pg-div-func — fails on mysql. FUNC-DIFF: source=(('3',),) target=()
SELECT DIV(7, 2) AS r

-- CASE[open]: pg-div-mod-int — fails on mysql. FUNC-DIFF: source=(('3', '2'),) target=()
SELECT DIV(17, 5), 17 % 5

-- CASE[open]: pg-div-precision — fails on mysql. FUNC-DIFF: source=(('0.333333',),) target=(('0.33333',),)
SELECT 1.0 / 3 AS r

-- CASE[open]: pg-domain — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE DOMAIN posint AS INT CHECK (VALUE > 0)

-- CASE[open]: pg-domain-in-table — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type email.DB-Lib error messa
CREATE DOMAIN email AS TEXT CHECK (VALUE ~ '@'); CREATE TABLE t (e email)

-- CASE[open]: pg-double-cast — fails on oracle, tsql. (529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message
SELECT 123::text::int AS r

-- CASE[open]: pg-drop-not-null — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP NOT NULL

-- CASE[open]: pg-emoji-len — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT LENGTH('😀') AS r

-- CASE[open]: pg-empty-is-null — fails on oracle. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT '' IS NULL AS r

-- CASE[open]: pg-encode-base64 — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ENCODE('abc'::bytea, 'base64') AS r

-- CASE[open]: pg-encode-decode — fails on mysql, oracle, tsql. (195, b"'DECODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ENCODE(DECODE('SGVsbG8=', 'base64'), 'hex')

-- CASE[open]: pg-estring — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT E'line1\nline2' AS r

-- CASE[open]: pg-estring-hex — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT E'\x41' AS r

-- CASE[open]: pg-except-all — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SELECT 1 EXCEPT ALL SELECT 2

-- CASE[open]: pg-exception-handler — fails on tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-execute-using — fails on mysql. (1336, 'Dynamic SQL is not allowed in stored function or trigger')
CREATE FUNCTION f() RETURNS VOID AS $$ BEGIN EXECUTE 'INSERT INTO t VALUES ($1)' USING 5; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-explain — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
EXPLAIN SELECT 1

-- CASE[open]: pg-expr-index — fails on mysql, oracle. ORA-02327: cannot create index on expression with data type LOB
CREATE TABLE t (a INT, b TEXT); CREATE INDEX ix ON t (lower(b))

-- CASE[open]: pg-extract-dow — fails on mysql, oracle, tsql. (155, b"'DOW' is not a recognized datepart option.DB-Lib error message 20018, severity 15:
SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d

-- CASE[open]: pg-extract-epoch — fails on mysql, oracle, tsql. (155, b"'EPOCH' is not a recognized datepart option.DB-Lib error message 20018, severity 1
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01') AS r

-- CASE[open]: pg-for-record-loop — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE FUNCTION f() RETURNS INT AS $$ DECLARE r RECORD; t INT := 0; BEGIN FOR r IN SELECT generate_series(1,3) AS n LOOP t := t + r.n; END LOOP; RETURN t; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-for-update — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id INT); SELECT * FROM t FOR UPDATE

-- CASE[open]: pg-format-func — fails on oracle, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT format('%s=%s', 'a', 1) AS r

-- CASE[open]: pg-full-outer-join — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a FULL OUTER JOIN b ON a.id = b.id

-- CASE[open]: pg-fulltext — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT to_tsvector('a cat') @@ to_tsquery('cat') AS r

-- CASE[open]: pg-fulltext2 — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id FROM t WHERE to_tsvector('english', s) @@ plainto_tsquery('english', 'term')

-- CASE[open]: pg-generate-series — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.GE
SELECT generate_series(1, 5) AS r

-- CASE[open]: pg-grant — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT); GRANT SELECT, INSERT ON t TO PUBLIC

-- CASE[open]: pg-grant-column — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT); GRANT SELECT (a) ON t TO PUBLIC

-- CASE[open]: pg-greatest-null — fails on mysql, oracle. FUNC-DIFF: source=(('3',),) target=(('NULL',),)
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[open]: pg-greatest-string — fails on mysql, tsql. FUNC-DIFF: source=(('a',),) target=(('B',),)
SELECT GREATEST('a', 'B') AS r

-- CASE[open]: pg-grouping-fn — fails on mysql, oracle, tsql. (8161, b'Argument 1 of the GROUPING function does not match any of the expressions in the 
SELECT x, GROUPING(x) FROM (VALUES (1)) v(x) GROUP BY CUBE (x)

-- CASE[open]: pg-grouping-sets — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())

-- CASE[open]: pg-hex-literal — fails on oracle. ORA-00932: expression is of data type BINARY, which is incompatible with expected data typ
SELECT x'FF'::int AS h, 1.5e3 AS s

-- CASE[open]: pg-ilike-any — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id, n FROM t WHERE s ILIKE '%abc%' AND n = ANY(ARRAY[1,2,3])

-- CASE[open]: pg-inheritance — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE parent (id INT); CREATE TABLE child () INHERITS (parent)

-- CASE[open]: pg-initcap — fails on mysql, oracle, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r

-- CASE[open]: pg-insert-returning — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT); INSERT INTO t (id, n) VALUES (1, 5) RETURNING id

-- CASE[open]: pg-insert-select-conflict — fails on mysql, oracle, tsql. (208, b"Invalid object name 'dbo.GENERATE_SERIES'.DB-Lib error message 20018, severity 16:
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); INSERT INTO t (id, n) SELECT g, g*2 FROM generate_series(1,5) g ON CONFLICT DO NOTHING

-- CASE[open]: pg-intdiv — fails on mysql, oracle. FUNC-DIFF: source=(('2',),) target=(('2.5',),)
SELECT 5 / 2 AS r

-- CASE[open]: pg-intersect-all — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SELECT 1 INTERSECT ALL SELECT 1

-- CASE[open]: pg-interval-arith — fails on mysql, oracle, tsql. (207, b"Invalid column name 'INTERVAL'.DB-Lib error message 20018, severity 16:\nGeneral S
SELECT NOW() - INTERVAL '1 day', DATE '2020-01-01' + 7

-- CASE[open]: pg-json-num — fails on mysql. FUNC-DIFF: source=(('1.5',),) target=()
SELECT ('{"a":1.5}'::jsonb->>'a')

-- CASE[open]: pg-jsonb-agg — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSONB_AGG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-jsonb-arrow — fails on mysql. (1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT '{"a":1}'::jsonb -> 'a'

-- CASE[open]: pg-jsonb-build — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.JS
SELECT JSONB_BUILD_OBJECT('a', 1, 'b', 2)

-- CASE[open]: pg-jsonb-path — fails on mysql. (1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT '{"a":[1,2]}'::jsonb #> '{a,0}'

-- CASE[open]: pg-jsonb-path-query — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.js
SELECT jsonb_path_query('{"a":[1,2]}', '$.a[*]') AS r

-- CASE[open]: pg-jsonb-recordset — fails on mysql, tsql. (317, b"Table-valued function 'jsonb_to_recordset' cannot have a column alias.DB-Lib error
SELECT * FROM jsonb_to_recordset('[{"a":1}]') AS x(a INT)

-- CASE[open]: pg-justify — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '1 mon 40 days'.DB-Lib error message 20018, severity 15:\nGe
SELECT JUSTIFY_INTERVAL(INTERVAL '1 mon 40 days') AS r

-- CASE[open]: pg-left-neg — fails on mysql. FUNC-DIFF: source=(('ab',),) target=(('',),)
SELECT LEFT('abc', -1) AS r

-- CASE[open]: pg-like-cs — fails on mysql, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[open]: pg-like-escape — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT 'a_b' LIKE 'a\_b' AS r

-- CASE[open]: pg-lock-table — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT); LOCK TABLE t IN SHARE MODE

-- CASE[open]: pg-log-2arg — fails on tsql. FUNC-DIFF: source=(('3',),) target=(('0.333333',),)
SELECT LOG(2, 8) AS r

-- CASE[open]: pg-log-base — fails on mysql, tsql. FUNC-DIFF: source=(('2',),) target=(('4.60517',),)
SELECT LOG(100) AS r

-- CASE[open]: pg-lpad-shrink — fails on tsql. FUNC-DIFF: source=(('hel',),) target=(('llo',),)
SELECT LPAD('hello', 3) AS r

-- CASE[open]: pg-make-date — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_DATE(2020, 6, 15), MAKE_TIME(10, 30, 0)

-- CASE[open]: pg-math-log — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT LOG(10, 100), LN(2.718), POWER(2, 8), SQRT(16)

-- CASE[open]: pg-matview-nodata — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE MATERIALIZED VIEW mv AS SELECT 1 AS x WITH NO DATA

-- CASE[open]: pg-md5 — fails on oracle, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc') AS r

-- CASE[open]: pg-mod-decimal — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('3',),) target=(('2',),)
SELECT MOD(10, 3.5::numeric) AS r

-- CASE[open]: pg-mode — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT MODE() WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(1),(2)) v(x)

-- CASE[open]: pg-multi-out — fails on oracle. FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared
CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-named-exception — fails on oracle, tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1/0; EXCEPTION WHEN division_by_zero THEN RETURN -1; WHEN OTHERS THEN RAISE; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-named-window2 — fails on oracle. ORA-30485: missing ORDER BY expression in the window specification
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id, LAG(n) OVER w, LEAD(n) OVER w FROM t WINDOW w AS (PARTITION BY s ORDER BY id)

-- CASE[open]: pg-nested-call — fails on oracle. PROCEDURE OUTER_P compiled INVALID (line 4): PLS-00201: identifier 'INNER_P' must be decla
CREATE PROCEDURE outer_p() AS $$ BEGIN CALL inner_p(); END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-network-types — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag
CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)

-- CASE[open]: pg-not-null-is-null — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT (NOT NULL) IS NULL AS r

-- CASE[open]: pg-num-nonnulls — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUM_NONNULLS(1, NULL, 2) AS r

-- CASE[open]: pg-order-nulls-default — fails on mysql, tsql. FUNC-DIFF: source=(('1',), ('3',), ('NULL',)) target=(('NULL',), ('1',), ('3',))
SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x

-- CASE[open]: pg-overlay — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV
SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o

-- CASE[open]: pg-partial-unique — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (a INT, b INT); CREATE UNIQUE INDEX ix ON t (a) WHERE b > 0

-- CASE[open]: pg-partition-of — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, dt DATE) PARTITION BY RANGE (dt); CREATE TABLE t_2020 PARTITION OF t FOR VALUES FROM ('2020-01-01') TO ('2021-01-01')

-- CASE[open]: pg-percentile — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2),(3)) v(x)

-- CASE[open]: pg-percentile-disc — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY x) FROM (VALUES (1),(2),(3)) v(x)

-- CASE[open]: pg-position-case — fails on mysql, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT POSITION('a' IN 'ABC') AS r

-- CASE[open]: pg-position-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT POSITION('' IN 'abc') AS r

-- CASE[open]: pg-power-neg — fails on mysql. FUNC-DIFF: source=(('0.5',),) target=()
SELECT POWER(2, -1) AS r

-- CASE[open]: pg-quote — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU
SELECT QUOTE_LITERAL('O''Brien'), QUOTE_IDENT('my col')

-- CASE[open]: pg-raise-using — fails on mysql, tsql. (443, b"Invalid use of a side-effecting operator 'RAISERROR' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RAISE EXCEPTION 'err %', 42 USING ERRCODE = 'P0001'; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-range-contains — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT INT4RANGE(1, 10) @> 5 AS r

-- CASE[open]: pg-range-types — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m
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

-- CASE[open]: pg-recursive-view — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT, b INT); CREATE RECURSIVE VIEW v(n) AS SELECT 1 UNION ALL SELECT n+1 FROM v WHERE n < 5

-- CASE[open]: pg-regex-case — fails on mysql. FUNC-DIFF: source=(('0',),) target=()
SELECT 'abc' ~ '^A' AS r

-- CASE[open]: pg-regexp-matches — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE
SELECT REGEXP_MATCHES('a1b2', '[0-9]', 'g') AS r

-- CASE[open]: pg-regexp-split-table — fails on mysql, oracle, tsql. (208, b"Invalid object name 'dbo.regexp_split_to_table'.DB-Lib error message 20018, severi
SELECT * FROM regexp_split_to_table('a,b,c', ',')

-- CASE[open]: pg-repeat-left-right — fails on oracle. ORA-00904: "RIGHT": invalid identifier
SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)

-- CASE[open]: pg-return-query — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE FUNCTION f() RETURNS SETOF INT AS $$ BEGIN RETURN QUERY SELECT 1 UNION SELECT 2; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-return-refcursor — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE FUNCTION f() RETURNS refcursor AS $$ DECLARE c refcursor; BEGIN OPEN c FOR SELECT 1; RETURN c; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-returning-expr — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT);
UPDATE t SET n = 1 WHERE id = 1 RETURNING id, n, n*2 AS doubled

-- CASE[open]: pg-returns-table — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE FUNCTION f() RETURNS TABLE(a INT, b TEXT) AS $$ BEGIN RETURN QUERY SELECT 1, 'x'; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-revoke — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT); REVOKE ALL ON t FROM PUBLIC

-- CASE[open]: pg-rollup — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)

-- CASE[open]: pg-round-2675 — fails on mysql, oracle, tsql. FUNC-DIFF: source=(('2.68',),) target=(('3',),)
SELECT ROUND(2.675::numeric, 2) AS r

-- CASE[open]: pg-rule — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT); CREATE RULE r AS ON DELETE TO t DO INSTEAD NOTHING

-- CASE[open]: pg-savepoint — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'AS'.DB-Lib error message 20018, severity 15:\nG
BEGIN; SAVEPOINT sp; ROLLBACK TO SAVEPOINT sp; COMMIT

-- CASE[open]: pg-sequence — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne
CREATE SEQUENCE seq; SELECT nextval('seq'), currval('seq')

-- CASE[open]: pg-sequence-options — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE SEQUENCE seq INCREMENT 2 MINVALUE 10 MAXVALUE 100 CACHE 5 CYCLE

-- CASE[open]: pg-serial-bit — fails on mysql, oracle, tsql. (2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit
CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))

-- CASE[open]: pg-set-default — fails on oracle, tsql. (156, b"Incorrect syntax near the keyword 'SET'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5

-- CASE[open]: pg-set-searchpath — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SET search_path TO myschema, public

-- CASE[open]: pg-setweight — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.se
SELECT setweight(to_tsvector('cat'), 'A') AS r

-- CASE[open]: pg-size-funcs — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.pg
SELECT pg_size_pretty(1024::bigint), pg_relation_size('pg_class')

-- CASE[open]: pg-split-part — fails on mysql, oracle, tsql. (195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018
SELECT SPLIT_PART('a,b,c', ',', 2) AS r

-- CASE[open]: pg-str-lt — fails on mysql, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'apple' < 'Banana' AS r

-- CASE[open]: pg-string-agg-order — fails on oracle, tsql. (529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message
SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-string-to-array — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT string_to_array('a,b,c', ',')

-- CASE[open]: pg-strpos-empty — fails on oracle, tsql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT STRPOS('', '') AS r

-- CASE[open]: pg-substr-zero — fails on mysql, oracle. FUNC-DIFF: source=(('ab',),) target=(('abc',),)
SELECT SUBSTRING('abcdef', 0, 3) AS r

-- CASE[open]: pg-substring-regex — fails on oracle, tsql. (8116, b'Argument data type varchar is invalid for argument 2 of substring function.DB-Lib
SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r

-- CASE[open]: pg-synonym-as-view — fails on oracle. ORA-00955: name is already used by an existing object
CREATE TABLE t (a INT); CREATE VIEW syn AS SELECT * FROM t

-- CASE[open]: pg-system-funcs — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT version(), current_database(), current_user, pg_backend_pid()

-- CASE[open]: pg-tablesample — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
CREATE TABLE t (id INT); SELECT * FROM t TABLESAMPLE BERNOULLI(50)

-- CASE[open]: pg-to-hex-typeof — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT to_hex(255), pg_typeof(1)

-- CASE[open]: pg-tochar-neg — fails on mysql, tsql. FUNC-DIFF: source=(('-1234.5',),) target=(('-9999123599',),)
SELECT to_char(-1234.5, '9999.99') AS r

-- CASE[open]: pg-trailing-eq — fails on oracle, tsql. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'a ' = 'a' AS r

-- CASE[open]: pg-transition-tables — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT);
CREATE FUNCTION trg() RETURNS TRIGGER AS $$ BEGIN RETURN NULL; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg AFTER UPDATE ON t REFERENCING OLD TABLE AS old_t NEW TABLE AS new_t FOR EACH STATEMENT EXECUTE FUNCTION trg();

-- CASE[open]: pg-translate — fails on mysql. (1305, 'FUNCTION unique_val_5e892bc4b99a.TRANSLATE does not exist')
SELECT TRANSLATE('abc', 'ab', 'xy') AS r

-- CASE[open]: pg-trigger-multi-event — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg AFTER INSERT OR UPDATE OR DELETE ON t FOR EACH ROW EXECUTE FUNCTION trg_fn();

-- CASE[open]: pg-trigger-on-view — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT);
CREATE VIEW v AS SELECT id FROM t;
CREATE FUNCTION f() RETURNS TRIGGER AS $$ BEGIN INSERT INTO t VALUES (NEW.id); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg INSTEAD OF INSERT ON v FOR EACH ROW EXECUTE FUNCTION f();

-- CASE[open]: pg-trigger-raise — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT PRIMARY KEY, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN IF OLD.n <> NEW.n THEN RAISE EXCEPTION 'no change allowed'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg BEFORE UPDATE ON t FOR EACH ROW EXECUTE PROCEDURE trg_fn();

-- CASE[open]: pg-trigger-statement-level — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN RETURN NULL; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg AFTER INSERT ON t FOR EACH STATEMENT EXECUTE FUNCTION trg_fn();

-- CASE[open]: pg-trim-both-chars — fails on oracle. ORA-30001: trim set should have only one character
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS t

-- CASE[open]: pg-trim-len — fails on oracle, tsql. FUNC-DIFF: source=(('2', '0'),) target=(('0', '0'),)
SELECT CHAR_LENGTH('  '), LENGTH(TRIM('  '))

-- CASE[open]: pg-truncate-restart — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near 'RESTART'.DB-Lib error message 20018, severity 15:\nGeneral 
CREATE TABLE t (id INT); TRUNCATE TABLE t RESTART IDENTITY CASCADE

-- CASE[open]: pg-tstzrange — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '1 DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ
SELECT tstzrange(now(), now() + INTERVAL '1 day') AS r

-- CASE[open]: pg-tz-interval — fails on mysql, oracle. ORA-30089: missing or invalid <datetime field>
CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)

-- CASE[open]: pg-unicode-escape — fails on mysql, oracle, tsql. (207, b"Invalid column name 'U'.DB-Lib error message 20018, severity 16:\nGeneral SQL Serv
SELECT U&'\0041' AS r

-- CASE[open]: pg-unnest — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT UNNEST(ARRAY[1,2,3]) AS r

-- CASE[open]: pg-update-from-window — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); UPDATE t SET n = s.rn FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY id) rn FROM t) s WHERE t.id = s.id

-- CASE[open]: pg-update-returning — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT, n INT); UPDATE t SET n = 1 RETURNING id, n

-- CASE[open]: pg-values-stmt — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
VALUES (1, 'a'), (2, 'b')

-- CASE[open]: pg-view-check — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (id INT); CREATE VIEW v AS SELECT id FROM t WITH LOCAL CHECK OPTION

-- CASE[open]: pg-week — fails on tsql. FUNC-DIFF: source=(('1',),) target=(('2',),)
SELECT EXTRACT(WEEK FROM DATE '2020-01-05') AS r

-- CASE[open]: pg-week-jan1 — fails on mysql. FUNC-DIFF: source=(('1',),) target=(('0',),)
SELECT EXTRACT(WEEK FROM DATE '2020-01-01') AS r

-- CASE[open]: pg-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT width_bucket(5, 0, 10, 5) AS r

-- CASE[open]: pg-xmlelement — fails on mysql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT XMLELEMENT(NAME foo, 'bar') AS r

-- CASE[open]: pg-xmlelement2 — fails on mysql, tsql. (195, b"'XMLELEMENT' is not a recognized built-in function name.DB-Lib error message 20018
SELECT xmlelement(name foo, 'bar')

-- CASE[open]: pg-xpath — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.xp
SELECT xpath('/a/text()', '<a>1</a>'::xml)

-- CASE[open]: postgresql-drop-CHECK — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)
CREATE TABLE t (age INT CHECK (age >= 0))

-- CASE[open]: postgresql-drop-DEFERRABLE — fails on oracle. SILENT CLAUSE DROP: 'DEFERRABLE' absent from valid oracle output, no warning (target suppo
CREATE TABLE t (id INT PRIMARY KEY DEFERRABLE INITIALLY DEFERRED)

-- CASE[open]: postgresql-drop-ON\s+DELETE\s+ — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'ON\s+DELETE\s+CASCADE' absent from valid tsql output, no warning (tar
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE CASCADE)

-- CASE[open]: postgresql-drop-ON\s+UPDATE\s+ — fails on mysql. SILENT CLAUSE DROP: 'ON\s+UPDATE\s+CASCADE' absent from valid mysql output, no warning (ta
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

-- CASE[open]: postgresql-drop5-REFERENCES — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'REFERENCES' absent from valid tsql output, no warning
CREATE TABLE t (a INT PRIMARY KEY, b INT REFERENCES t(a))

-- CASE[open]: postgresql-qdrop-FOR\s+UPDATE — fails on tsql. SILENT CLAUSE DROP: 'FOR\s+UPDATE' absent from valid tsql output, no warning
SELECT x FROM (VALUES (1),(2)) v(x) FOR UPDATE

-- CASE[open]: postgresql-qdrop-ROWS\s+BETWE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'ROWS\s+BETWEEN' absent from valid tsql output, no warning
SELECT x, SUM(x) OVER (ORDER BY x ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM (VALUES (1),(2)) v(x)

