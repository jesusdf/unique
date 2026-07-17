-- Challenge fixtures — PostgreSQL / PL-pgSQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: pg-age — fails on mysql, oracle, tsql. (195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a

-- CASE[open]: pg-alter-add — fails on mysql, oracle. ORA-30649: missing DIRECTORY keyword
CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'

-- CASE[open]: pg-array-agg — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT ARRAY_AGG(x ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-array-jsonb — fails on mysql, oracle. ORA-03099: unexpected item [ in a column definition
CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)

-- CASE[open]: pg-before-update-trg — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT PRIMARY KEY, n INT, updated TIMESTAMP);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN NEW.updated := now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg BEFORE UPDATE ON t FOR EACH ROW EXECUTE FUNCTION trg_fn();

-- CASE[open]: pg-comment-on — fails on mysql, oracle, tsql. UNRECOGNIZED CARRIER: ['UNIQUE: Unhandled']
CREATE TABLE t (a INT); COMMENT ON COLUMN t.a IS 'the a column'

-- CASE[open]: pg-date-trunc — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.TI
SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d

-- CASE[open]: pg-exception-handler — fails on tsql. (443, b"Invalid use of a side-effecting operator 'BEGIN TRY' within a function.DB-Lib erro
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-expr-index — fails on mysql, oracle. ORA-02327: cannot create index on expression with data type LOB
CREATE TABLE t (a INT, b TEXT); CREATE INDEX ix ON t (lower(b))

-- CASE[open]: pg-extract-dow — fails on mysql, oracle, tsql. (155, b"'DOW' is not a recognized datepart option.DB-Lib error message 20018, severity 15:
SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d

-- CASE[open]: pg-grouping-sets — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())

-- CASE[open]: pg-jsonb-arrow — fails on mysql. (1064, 'You have an error in your SQL syntax; check the manual that corresponds to your My
SELECT '{"a":1}'::jsonb -> 'a'

-- CASE[open]: pg-multi-out — fails on oracle. FUNCTION F compiled INVALID (line 7): PLS-00201: identifier 'VOID' must be declared
CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-network-types — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag
CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)

-- CASE[open]: pg-overlay — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.OV
SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o

-- CASE[open]: pg-range-types — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m
CREATE TABLE t (rng INT4RANGE, tsr TSRANGE)

-- CASE[open]: pg-repeat-left-right — fails on oracle. ORA-00904: "RIGHT": invalid identifier
SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)

-- CASE[open]: pg-return-query — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE FUNCTION f() RETURNS SETOF INT AS $$ BEGIN RETURN QUERY SELECT 1 UNION SELECT 2; END; $$ LANGUAGE plpgsql

-- CASE[open]: pg-rollup — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)

-- CASE[open]: pg-serial-bit — fails on mysql, oracle, tsql. (2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit
CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))

-- CASE[open]: pg-string-agg-order — fails on oracle, tsql. (529, b'Explicit conversion from data type int to text is not allowed.DB-Lib error message
SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[open]: pg-trigger-raise — fails on mysql. (1064, "You have an error in your SQL syntax; check the manual that corresponds to your My
CREATE TABLE t (id INT PRIMARY KEY, n INT);
CREATE FUNCTION trg_fn() RETURNS TRIGGER AS $$ BEGIN IF OLD.n <> NEW.n THEN RAISE EXCEPTION 'no change allowed'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg BEFORE UPDATE ON t FOR EACH ROW EXECUTE PROCEDURE trg_fn();

-- CASE[open]: pg-trim-both-chars — fails on oracle. ORA-30001: trim set should have only one character
SELECT TRIM(BOTH 'x' FROM 'xxabcxx') AS t

-- CASE[open]: pg-tz-interval — fails on mysql, oracle. ORA-30089: missing or invalid <datetime field>
CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)
