-- Challenge fixtures — PostgreSQL / PL-pgSQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[limit]: pg-accent-eq — fails on mysql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'Ä' = 'A' AS r

-- CASE[fixed]: pg-add-identity — ALTER ... ADD COLUMN ... GENERATED AS IDENTITY maps to MySQL's AUTO_INCREMENT with an accompanying ADD UNIQUE (the column must be a key), carried + warned. Live-executed and auto-assigns on mysql 2026-07-24.
CREATE TABLE t (id INT PRIMARY KEY, n INT);
ALTER TABLE t ADD COLUMN big BIGINT GENERATED ALWAYS AS IDENTITY

-- CASE[fixed]: pg-admin-fns — fails on mysql, oracle, tsql. (195, b"'pg_sleep' is not a recognized built-in function name.DB-Lib error message 20018, 
SELECT pg_sleep(0), pg_advisory_lock(1), txid_current()

-- CASE[fixed]: pg-age — fails on mysql, oracle, tsql. (195, b"'AGE' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT AGE(TIMESTAMP '2020-01-01', TIMESTAMP '2019-01-01') AS a

-- CASE[fixed]: pg-age-epoch — fails on mysql, oracle, tsql. (195, b"'age' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT age(now(), '2020-01-01'), date_part('epoch', now())

-- CASE[fixed]: pg-all-values — a quantified VALUES list (> ALL (VALUES (1),(2))) parses as an Anonymous ALL over a Values node and is rewritten to a portable UNION ALL subquery (bare VALUES is not a subquery on MySQL/Oracle/T-SQL). Live-executed on all three 2026-07-24.
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t WHERE n > ALL (VALUES (1),(2),(3))

-- CASE[fixed]: pg-alter-add — ADD COLUMN b TEXT NOT NULL DEFAULT 'x': Oracle reorders to DEFAULT 'x' NOT NULL (ORA-30649), and MySQL wraps the TEXT-column literal default as DEFAULT ('x') (error 1101 otherwise). live-verified DDL runs on both.
CREATE TABLE t (a INT); ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x'

-- CASE[fixed]: pg-alter-notvalid — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (id INT);
ALTER TABLE t RENAME TO tbl;
ALTER TABLE tbl ADD CONSTRAINT ck CHECK (id>0) NOT VALID;

-- CASE[fixed]: pg-alter-suite — a full ALTER batch (ADD COLUMN NOT NULL DEFAULT, ALTER COLUMN TYPE, SET DEFAULT, RENAME, DROP COLUMN) now translates: SET DEFAULT replaces (drops the existing default first on T-SQL) and DROP COLUMN pre-drops the dependent default constraint. live-verified whole batch on oracle + tsql.
CREATE TABLE t (id INT);
ALTER TABLE t ADD COLUMN name VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE t ALTER COLUMN id TYPE BIGINT;
ALTER TABLE t ALTER COLUMN name SET DEFAULT 'x';
ALTER TABLE t RENAME COLUMN name TO nm;
ALTER TABLE t DROP COLUMN nm;

-- CASE[fixed]: pg-alter-type — PostgreSQL ALTER COLUMN a TYPE t maps to Oracle MODIFY a t (Oracle has no TYPE keyword / SET DATA TYPE); T-SQL/MySQL keep their spelling. live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a TYPE BIGINT

-- CASE[fixed]: pg-alter-using — PostgreSQL ALTER COLUMN a SET DATA TYPE t USING a::t maps to Oracle MODIFY a t; the redundant USING cast IS Oracle's implicit conversion, so it is dropped. live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DATA TYPE BIGINT USING a::bigint

-- CASE[fixed]: pg-any-array-subquery — ANY(ARRAY(SELECT ...)) unwraps the ARRAY() constructor to the standard quantified subquery = ANY (SELECT ...), valid on all four engines. Live-executed on mysql/oracle/tsql 2026-07-24.
CREATE TABLE a (id INT, n INT); CREATE TABLE b (id INT, n INT); SELECT * FROM a WHERE id = ANY(ARRAY(SELECT id FROM b))

-- CASE[fixed]: pg-arr-str-roundtrip — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT array_to_string(string_to_array('a,b,c',','),'|')

-- CASE[limit]: pg-array-jsonb — PostgreSQL array column types (TEXT[], INT[][]) have no cross-engine model (docs/03-unsupported.md §7); the output gate now degrades the statement to a documented carrier + warning off PG (was shipped invalid, ORA-03099). fails on oracle
CREATE TABLE t (tags TEXT[], matrix INT[][], data JSONB)

-- CASE[fixed]: pg-ascii-empty — PG ASCII('') is 0; Oracle/T-SQL return NULL. Recover 0 (T-SQL CASE, Oracle COALESCE) — shared with the MySQL-source handler.
SELECT ASCII('') AS r

-- CASE[limit]: pg-at-time-zone — AT TIME ZONE is not portable (Oracle/MySQL have no such operator; the session-tz-dependent display differs on PG/T-SQL), so it degrades to NULL + annotation off PG (docs/03-unsupported.md). fails on mysql, oracle, tsql
SELECT TIMESTAMP '2020-01-01 10:00' AT TIME ZONE 'UTC' AS r

-- CASE[fixed]: pg-attz2 — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ti
SELECT now() AT TIME ZONE 'UTC', timezone('UTC', now())

-- CASE[fixed]: pg-avg-int — T-SQL AVG(int) truncates to 1; promote the argument so it averages as decimal (1.5) like PostgreSQL.
SELECT AVG(x) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: pg-avg-null — AVG = 7/3 = 2.3333...; same value, engine-specific decimal scale. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)

-- CASE[fixed]: pg-baseconv — fails on tsql. (291, b"CAST or CONVERT: invalid attributes specified for type 'bit'DB-Lib error message 2
SELECT 255::bit(8)::text,to_hex(255),255::text

-- CASE[fixed]: pg-bit-fns — fails on mysql. (1305, 'FUNCTION unique_val_ff6c8e4945b4.GETBIT does not exist')
SELECT get_bit(B'1011', 0), set_bit(B'0000', 1, 1)

-- CASE[fixed]: pg-bit-negative — Signed source ~x yields a negative (two's-complement) result; MySQL's ~ is UNSIGNED (~5=18446744073709551610), so the bitwise NOT is wrapped in CAST(~x AS SIGNED) to match. &|^ and shifts already agree. live-verified. (-1,-6,3,5)
SELECT ~0, ~5, (-5) & 3, 5 & (-1)

-- CASE[fixed]: pg-bit-prec2 — bitwise/arithmetic parens keep PG grouping on T-SQL (10 & (6+1), 1 << (2+1)).
SELECT 10 & 6 + 1, 1 << 2 + 1

-- CASE[fixed]: pg-bitnot — Signed source ~x yields a negative (two's-complement) result; MySQL's ~ is UNSIGNED (~5=18446744073709551610), so the bitwise NOT is wrapped in CAST(~x AS SIGNED) to match. &|^ and shifts already agree. live-verified. -1
SELECT ~0 AS r

-- CASE[fixed]: pg-bitops — Signed source ~x yields a negative (two's-complement) result; MySQL's ~ is UNSIGNED (~5=18446744073709551610), so the bitwise NOT is wrapped in CAST(~x AS SIGNED) to match. &|^ and shifts already agree. live-verified. (1,7,6,-6,10,2)
SELECT 5 & 3, 5 | 2, 5 # 3, ~5, 5 << 1, 5 >> 1

-- CASE[fixed]: pg-blob-length — LENGTH(decode(literal,'base64')) folds to the decoded byte count (5) on every target. Live-verified on mysql/oracle/tsql.
SELECT LENGTH(decode('SGVsbG8=', 'base64')) AS r

-- CASE[fixed]: pg-bool-int-cast — PostgreSQL 'true'::boolean accepts word spellings other engines can't cast to a number ('t'/'true'/'yes'/'on' -> 1); the string literal folds to 1, so ::int matches. live-verified 1.
SELECT 'true'::boolean::int AS r

-- CASE[fixed]: pg-bool-repr — boolean::text renders 'true'/'false' on MySQL (CASE), the boolean cols are True==1/False==0; live-verified (1,1,'true',0,NULL).
SELECT (1>0), (1>0)::int, (1>0)::text, NOT (1>0), true AND NULL

-- CASE[fixed]: pg-bool-text2 — PG boolean::text is 'true'/'false'; MySQL has no boolean text, so emit CASE WHEN ... THEN 'true' ELSE 'false'. Live-verified 'true'.
SELECT true::text AS r

-- CASE[fixed]: pg-bool-week — word/'t'/1 boolean casts fold to 1/0 and EXTRACT(WEEK) maps per engine; live-verified (1,1,1,1) (True==1).
SELECT 'true'::boolean, 't'::boolean, 1::boolean, EXTRACT(WEEK FROM DATE '2020-01-01')

-- CASE[fixed]: pg-bulk-insert — generate_series in INSERT..SELECT lands via the numbers-source rewrites (Oracle CONNECT BY LEVEL, T-SQL ROW_NUMBER over sys.all_objects), live-executed; MySQL has no table functions and degrades to a documented carrier + warning.
CREATE TABLE t (a INT); INSERT INTO t SELECT generate_series(1, 1000)

-- CASE[fixed]: pg-case-statement — T-SQL scalar functions require the LAST statement to be a RETURN (error 455); a body ending in an all-branches-return IF/ELSE now gets an unreachable trailing RETURN NULL; f(1)='one' verified
CREATE FUNCTION f(n INT) RETURNS TEXT AS $$ BEGIN CASE n WHEN 1 THEN RETURN 'one'; ELSE RETURN 'other'; END CASE; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-cast-bool2 — PG word-spelled boolean literals ('1'/'yes'/'off'/'t') fold to 1/0/0/1 on Oracle/T-SQL; live-verified (1,1,0,1). 
SELECT '1'::boolean, 'yes'::boolean, 'off'::boolean, 't'::boolean

-- CASE[fixed]: pg-cast-chain2 — fails on tsql. (529, b'Explicit conversion from data type time to text is not allowed.DB-Lib error messag
SELECT '10:00'::time::text, now()::date::text, 42::bit(8)::int

-- CASE[limit]: pg-cast-datetime2 — the ::time and ::interval casts have no Oracle type; kept as text with documented carriers (docs/03-unsupported.md). fails on oracle
SELECT '2020-01-01 10:00'::date, '2020-01-01 10:00'::time, '10:00'::interval

-- CASE[fixed]: pg-cast-int — PG CAST(2.7 AS INT) rounds (3); T-SQL CAST truncates (2). Wrap ROUND(x, 0) on a T-SQL target (both round half-away-from-zero).
SELECT CAST(2.7 AS INT) AS r

-- CASE[limit]: pg-cast-interval — Oracle has no bare INTERVAL type (it needs a DAY TO SECOND/YEAR TO MONTH qualifier); '1 day'::interval keeps the value as text with a documented carrier (docs/03-unsupported.md). fails on oracle
SELECT '1 day'::interval AS r

-- CASE[fixed]: pg-cast-interval3 — EXTRACT(field FROM <interval literal>) folds to its statically-known value (5) and the ::text leg matches PG's own rendering. Live ('5 days', 5) exact on oracle 2026-07-24.
SELECT '5 days'::interval::text, extract(days from '5 days'::interval)

-- CASE[fixed]: pg-cast-matrix — was: numeric→text CAST invalid on tsql (deprecated TEXT type). Cured by the CAST-only TEXT→VARCHAR(MAX)/VARCHAR2(4000) map + tsql int-cast ROUND; live value-verified (precision-tolerant) on all failing targets 2026-07-24.
SELECT 3.14::int, 3.14::text, 3.14::numeric(10,2), 3.14::double precision

-- CASE[limit]: pg-cast-money — money maps to NUMBER(19,4) (valid, same numeric value) but PostgreSQL renders money with a currency symbol ('$12.99') and Oracle renders it plain — formatted-text divergence, annotated + warned per docs/03-unsupported.md §3.20. fails on oracle
SELECT '12.99'::numeric(4,1), '12.99'::numeric(3,0), 12.99::money

-- CASE[limit]: pg-cast-point — PostgreSQL's geometric point type has no cross-engine equivalent (MySQL's spatial POINT is a different WKB type); the cast keeps the source's text value '(1,2)' + annotation (docs/03-unsupported.md). fails on oracle, tsql
SELECT '(1,2)'::point AS r

-- CASE[fixed]: pg-cast-round-half — PG 7.5::int rounds half-away-from-zero (8); T-SQL CAST truncates (7). ROUND(x, 0) on T-SQL matches (also half-away-from-zero).
SELECT 7.5 :: int AS r

-- CASE[fixed]: pg-cast-tstz — TIMESTAMPTZ maps per engine (T-SQL DATETIMEOFFSET, MySQL DATETIME, Oracle date literal); live-verified 2020-01-01 midnight (tz-representation precision).
SELECT '2020-01-01'::timestamptz AS r

-- CASE[fixed]: pg-char-encoding — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ascii('A'),chr(65),encode('AB','hex'),decode('4142','hex'),encode('AB','base64'),octet_length('AB')

-- CASE[fixed]: pg-check-array-len — fails on oracle. ORA-03099: unexpected item [ in a column definition
CREATE TABLE t (a INT PRIMARY KEY, path TEXT[], CONSTRAINT ck CHECK (array_length(path,1) > 0))

-- CASE[fixed]: pg-check-jsonb — fails on mysql, oracle, tsql. (195, b"'JSONB_TYPEOF' is not a recognized built-in function name.DB-Lib error message 200
CREATE TABLE t (id INT PRIMARY KEY, data JSONB, CONSTRAINT ck CHECK (jsonb_typeof(data) = 'object'))

-- CASE[fixed]: pg-check-notvalid — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'NOT'.DB-Lib error message 20018, severity 15:\n
CREATE TABLE t (a INT, b INT); ALTER TABLE t ADD CONSTRAINT ck CHECK (a>0) NOT VALID

-- CASE[fixed]: pg-check-xor — a CHECK comparing predicate operands ((a IS NULL) != (b IS NULL)) wraps each predicate in CASE WHEN ... THEN 1 ELSE 0 END for T-SQL (no boolean value type) via a sqlglot-AST pass on the constraint fragment. Live: XOR enforced (both-set insert rejected, 547) on tsql 2026-07-24.
CREATE TABLE t (a INT, b INT, c INT, CONSTRAINT ck CHECK ((a IS NULL) != (b IS NULL)))

-- CASE[fixed]: pg-chr-ascii-unicode — PG chr(n) is a Unicode code point (Oracle CHR(n>127) returns a raw byte) → NCHR(n); PG ascii() is the code point (Oracle ASCII of a multibyte char returns the raw encoding) → ASCII(TO_NCHAR(x)); ('é', 233) verified on Oracle
SELECT chr(233), ascii('é')

-- CASE[fixed]: pg-chr-concat — fails on mysql. FUNC-DIFF: source=(('AB',),) target=(('4142',),)
SELECT chr(65) || chr(66)

-- CASE[fixed]: pg-chr-unicode — CHR(n>127) is a Unicode code point; MySQL CHAR(n USING utf16) / T-SQL NCHAR(n) build the char (byte CHAR gave wrong bytes / NULL). Live-verified μ.
SELECT CHR(956) AS r

-- CASE[fixed]: pg-computed-func — PG TEXT now maps to T-SQL NVARCHAR(MAX) (TEXT is deprecated and string functions reject it, error 8116; procedural-map parity). Live-executed on tsql 2026-07-24.
CREATE TABLE t (a TEXT, b TEXT GENERATED ALWAYS AS (lower(a)) STORED)

-- CASE[fixed]: pg-computed-jsonb — JSONB maps per target and the ->> generated column lands as MySQL ->>/VIRTUAL and T-SQL JSON_VALUE/JSON_QUERY computed column. Live value 'bob' exact on mysql + tsql 2026-07-24.
CREATE TABLE t (data JSONB, name TEXT GENERATED ALWAYS AS (data->>'name') STORED)

-- CASE[fixed]: pg-concat-null — fails on mysql. FUNC-DIFF: source=(('NULL', 'ab', 'a-b'),) target=(('NULL', 'NULL', 'a-b'),)
SELECT 'a'||NULL||'b', concat('a',NULL,'b'), concat_ws('-','a',NULL,'b')

-- CASE[fixed]: pg-convert-roundtrip — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co
SELECT convert_from(convert_to('héllo','UTF8'),'UTF8')

-- CASE[fixed]: pg-convert-to — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.co
SELECT convert_to('abc', 'UTF8')

-- CASE[fixed]: pg-date-bin — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.DA
SELECT date_bin('15 minutes', TIMESTAMP '2020-01-01 00:07', TIMESTAMP '2020-01-01')

-- CASE[fixed]: pg-date-diff-days — PostgreSQL DATE-DATE is a day count (60); MySQL does numeric subtraction and T-SQL errors. Recognize the PG CAST(... AS DATE) literal shape and emit DATEDIFF.
SELECT DATE '2020-03-01' - DATE '2020-01-01' AS r

-- CASE[fixed]: pg-date-part — EXTRACT/DATE_PART WEEK and QUARTER. Oracle's EXTRACT rejects both -> TO_CHAR(d,'IW'/'Q'). WEEK is ISO 8601: MySQL EXTRACT(WEEK) uses default_week_format and T-SQL DATEPART(WEEK) is DATEFIRST-bound (both off), so emit WEEK(d,3) / DATEPART(ISO_WEEK,d). live-verified value on all four.
SELECT DATE_PART('week', DATE '2020-06-15'), DATE_PART('quarter', DATE '2020-06-15')

-- CASE[fixed]: pg-date-plus-int — PostgreSQL date + n adds n days; MySQL does numeric addition (20200131) and T-SQL errors. Emit DATE_ADD / DATEADD from a PG/Oracle source.
SELECT DATE '2020-01-01' + 30 AS r

-- CASE[fixed]: pg-date-trunc — DATE_TRUNC(unit, ts). PG date_trunc parses to TimestampTrunc (fake sql_name); canonicalized to DATE_TRUNC -> Oracle TRUNC(ts,'MM'), T-SQL DATETRUNC(month,ts), MySQL DATE_FORMAT. (Also fixed: Oracle TIMESTAMP literal needs padded seconds.) live-verified 2020-05-01 on all four.
SELECT DATE_TRUNC('month', TIMESTAMP '2020-05-17 10:00') AS d

-- CASE[limit]: pg-datetrunc-units — fails on mysql, oracle, tsql. date_trunc('decade', …) has no cross-engine equivalent and now() is non-deterministic (docs/03-unsupported.md §2).
SELECT date_trunc('quarter', now()), date_trunc('decade', now())

-- CASE[fixed]: pg-decimal-scale — same value at each engine's default decimal scale (10/3 = 3.3333...). (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 10.00/3, 10/3.0, 10::numeric(10,4)/3, 1.5*1.5

-- CASE[fixed]: pg-div-precision — 1/3 = 0.3333...; same value at each engine's default division scale. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 1.0 / 3 AS r

-- CASE[fixed]: pg-double-cast — an intermediate ::text CAST target maps to CLOB (Oracle, ORA-22849) / TEXT (T-SQL, error 529), neither castable; remapped to VARCHAR2(4000) / VARCHAR(MAX) in the CAST map (DDL LOB columns unaffected); value 123 verified on both
SELECT 123::text::int AS r

-- CASE[fixed]: pg-drop-default — ALTER COLUMN a DROP DEFAULT maps to Oracle MODIFY a DEFAULT NULL and T-SQL dynamic drop of the named default constraint (a no-op when none). live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP DEFAULT

-- CASE[fixed]: pg-drop-not-null — cross-statement COLUMN_TYPES harvest (the script's own CREATE TABLE) lets MySQL MODIFY / T-SQL ALTER COLUMN re-state the type; Oracle uses type-less MODIFY wrapped in an idempotent guard (PG's DROP/SET NOT NULL is idempotent, Oracle's raises ORA-01451/-01442). Live-executed on mysql/oracle/tsql 2026-07-24.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a DROP NOT NULL

-- CASE[fixed]: pg-dttypes — TIME/TIMETZ/INTERVAL now map to Oracle INTERVAL DAY TO SECOND with warned notes (docs/03-unsupported.md §3.19); TIMESTAMPTZ -> TIMESTAMP WITH TIME ZONE. Live-executed on oracle 2026-07-24.
CREATE TABLE t (a DATE, b TIME, c TIMESTAMP, d TIMESTAMPTZ, e TIMETZ, f INTERVAL, g TIMESTAMP(3))

-- CASE[fixed]: pg-dyn-count — format('%I') renders the argument as a QUOTED IDENTIFIER per target (Oracle '"'||REPLACE||'"' — live-compiled VALID; T-SQL QUOTENAME) and PL/SQL BIGINT maps to NUMBER(19); the T-SQL function leg degrades documented (INSERT EXEC is side-effecting, error 443), as does MySQL's dynamic SELECT INTO.
CREATE FUNCTION f(tbl TEXT) RETURNS BIGINT AS $$ DECLARE n BIGINT; BEGIN EXECUTE format('SELECT COUNT(*) FROM %I', tbl) INTO n; RETURN n; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-emoji-len — LENGTH of a literal folds to the code-point count (1), which is also T-SQL-correct. Live-verified on tsql.
SELECT LENGTH('😀') AS r

-- CASE[limit]: pg-empty-is-null — fails on oracle. APPROVED LIMIT (2026-07-19): Oracle stores '' as NULL so `'' IS NULL` is true (false on PostgreSQL) — no faithful workaround (docs/03-unsupported.md). Warns + annotates UNIQUE: on Oracle. FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT '' IS NULL AS r

-- CASE[fixed]: pg-encode-base64 — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ENCODE('abc'::bytea, 'base64') AS r

-- CASE[fixed]: pg-encode-decode — fails on mysql, oracle, tsql. (195, b"'DECODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT ENCODE(DECODE('SGVsbG8=', 'base64'), 'hex')

-- CASE[limit]: pg-epoch — EXTRACT(EPOCH FROM timestamp) is translated to a literal date-diff (1577836800 verified), but EXTRACT(EPOCH FROM interval) has no portable equivalent (T-SQL/MySQL have no interval value type) so it degrades to NULL + annotation (docs/03-unsupported.md). fails on mysql, oracle, tsql
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01 00:00:00'), EXTRACT(EPOCH FROM INTERVAL '1 day')

-- CASE[fixed]: pg-except-all — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SELECT 1 EXCEPT ALL SELECT 2

-- CASE[limit]: pg-exception-handler — WHEN OTHERS handler compiles on Oracle/MySQL; T-SQL scalar functions forbid TRY/CATCH (error 443) so it degrades to a carrier (docs/03-unsupported.md). fails on tsql
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1; EXCEPTION WHEN OTHERS THEN RETURN -1; END; $$ LANGUAGE plpgsql

-- CASE[limit]: pg-exception-when — unique_violation/OTHERS handler compiles on Oracle/MySQL (with the referenced table present); T-SQL scalar functions forbid TRY/CATCH (error 443) so it degrades to a carrier (docs/03-unsupported.md). fails on tsql
CREATE FUNCTION f() RETURNS void AS $$ BEGIN INSERT INTO t VALUES(1); EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'dup'; WHEN others THEN RAISE; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-execute-using — a PG RETURNS VOID function is semantically a PROCEDURE; MySQL forbids dynamic SQL in a function (1336) but allows it in a procedure, so the void function is emitted as a PROCEDURE (and PG's $1 placeholder -> MySQL ?); CALL inserts 5, verified
CREATE FUNCTION f() RETURNS VOID AS $$ BEGIN EXECUTE 'INSERT INTO t VALUES ($1)' USING 5; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-expr-index — an expression index over a column that maps to a LOB on the target (TEXT→CLOB; MySQL functional-index restriction) degrades to a documented carrier + warning via the COLUMN_TYPES harvest; a VARCHAR-typed expression index keeps its native emission. Live-verified 2026-07-24.
CREATE TABLE t (a INT, b TEXT); CREATE INDEX ix ON t (lower(b))

-- CASE[fixed]: pg-extract-dow — EXTRACT(DOW), PG Sunday=0..Saturday=6. No target's native EXTRACT/DATEPART matches: MySQL DAYOFWEEK(d)-1, Oracle MOD over a known Sunday (1970-01-04), T-SQL DATEDIFF over a known Sunday (1900-01-07) — all NLS-/DATEFIRST-independent. live-verified value on all four.
SELECT EXTRACT(DOW FROM DATE '2020-01-01') AS d

-- CASE[fixed]: pg-extract-epoch — EXTRACT(EPOCH FROM ts) rewritten to a literal date-diff (Oracle date arithmetic, T-SQL DATEDIFF_BIG SECOND, MySQL TIMESTAMPDIFF SECOND) with no session-tz shift; value 1577836800 verified equal on all three (PG returns it as numeric .000000, targets as integer — same value)
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01') AS r

-- CASE[limit]: pg-fcollate — fails on mysql, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('c', 'B', '0'),) target=(('c', 'a', '1'),)
SELECT greatest('a','B','c'),least('a','B'),'a'<'B'

-- CASE[fixed]: pg-fetch-ties2 — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id FROM t ORDER BY id FETCH FIRST 5 ROWS WITH TIES

-- CASE[fixed]: pg-filter-subquery — fails on tsql. (130, b'Cannot perform an aggregate function on an expression containing an aggregate or a
CREATE TABLE t (id INT, n INT); CREATE TABLE u (id INT, v INT); SELECT id, COUNT(*) FILTER (WHERE n > (SELECT AVG(v) FROM u)) FROM t GROUP BY id

-- CASE[fixed]: pg-fk-full — fails on oracle. ORA-03075: unexpected item ON in an out-of-line constraint
CREATE TABLE t (id INT PRIMARY KEY, parent INT, CONSTRAINT fk FOREIGN KEY (parent) REFERENCES t(id) ON DELETE CASCADE ON UPDATE RESTRICT DEFERRABLE INITIALLY DEFERRED)

-- CASE[fixed]: pg-float-precision — same IEEE/float value at each engine's display precision. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT 0.1+0.2, 0.1::float+0.2::float, 1.0/3, (1.0/3)::float, 2::float/3

-- CASE[limit]: pg-fmt-spec — fails on oracle. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT to_char(now(),'Dy Mon DD HH24:MI:SS YYYY'),to_char(now(),'AM HH12:MI'),to_char(now(),'DDD WW IW')

-- CASE[limit]: pg-fmt3 — fails on oracle. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(1234.5678,'9G999D99'),to_char(-5,'S9')

-- CASE[fixed]: pg-for-update — SELECT … FOR UPDATE passes through to MySQL (it has FOR UPDATE); the RED failure was a harness locked-table artifact, not a transpile defect. live-verified DDL+SELECT run.
CREATE TABLE t (id INT); SELECT * FROM t FOR UPDATE

-- CASE[limit]: pg-format-currency — fails on mysql, tsql. currency-symbol number formatting has no cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(1234567.891,'FM999,999,990.00'), to_char(1234567.891,'FML999G999G990D00')

-- CASE[fixed]: pg-format-func — PG printf-style format() with a %s-only template rewritten to concatenation (Oracle ||, T-SQL/MySQL CONCAT; %% -> literal %); 'a=1' verified on all three (complex %I/%L/width specs degrade to a carrier)
SELECT format('%s=%s', 'a', 1) AS r

-- CASE[fixed]: pg-format2 — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT format('%s-%I-%L', 'a', 'col name', 'val'), concat_ws('|', 'a', NULL, 'b')

-- CASE[limit]: pg-frac-seconds — EXTRACT(MICROSECONDS FROM t) = SECOND*1e6 + MICROSECOND on MySQL/T-SQL (30123456 verified; MySQL DATETIME/TIME casts of a fractional literal now use (6) to keep the sub-second part); Oracle has no TIME type so the TIME-based extract degrades to a carrier (docs/03-unsupported.md). fails on oracle
SELECT TIMESTAMP '2020-01-01 10:20:30.123456', EXTRACT(MICROSECONDS FROM TIME '10:20:30.123456')

-- CASE[fixed]: pg-fround — PG numeric ROUND half-up (0.5->1,1.5->2,2.5->3); unbounded ::numeric cast now scaled (was truncating to integer).
SELECT round(0.5::numeric),round(1.5::numeric),round(2.5::numeric),round(2.567::numeric,2)

-- CASE[fixed]: pg-fsubstr — 2-arg substring with start <= 0 runs from the beginning on PG; rewritten to an explicit start of 1 (SUBSTR(s,1)) on MySQL/Oracle/T-SQL. Live-verified ('abc','abc','bc') on all three.
SELECT substring('abc',0),substring('abc' from -1),substring('abc',2,10)

-- CASE[fixed]: pg-fulltext — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT to_tsvector('a cat') @@ to_tsquery('cat') AS r

-- CASE[fixed]: pg-fulltext2 — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id FROM t WHERE to_tsvector('english', s) @@ plainto_tsquery('english', 'term')

-- CASE[fixed]: pg-func-attrs — the LANGUAGE sql body's trailing-attribute strip now covers SECURITY DEFINER/INVOKER, LEAKPROOF, WINDOW and CALLED/RETURNS NULL ON NULL INPUT (they leaked into the RETURN expression); STABLE/PARALLEL SAFE were already handled. Live-compiled VALID on tsql/oracle/mysql 2026-07-24.
CREATE FUNCTION f() RETURNS INT AS $$ SELECT 1 $$ LANGUAGE sql SECURITY DEFINER STABLE PARALLEL SAFE

-- CASE[fixed]: pg-gen-months — fails on oracle. ORA-30089: missing or invalid <datetime field>
SELECT day::date FROM generate_series('2020-01-01', '2020-12-01', '1 month'::interval) day

-- CASE[limit]: pg-gen-series-date — date-range generate_series(date, date, INTERVAL 'n' DAY) rewritten for Oracle (DATE + (LEVEL-1)*n) and T-SQL (DATEADD over a numbers source); the 5 dates match (PG returns timestamptz, Oracle/T-SQL date/timestamp — precision only). MySQL has no inline table function so it degrades (docs/03-unsupported.md). fails on mysql
SELECT generate_series('2020-01-01'::date, '2020-01-05'::date, '1 day') AS d

-- CASE[fixed]: pg-gen-series-ord — FROM generate_series(1,10,2) WITH ORDINALITY rewritten for T-SQL to a numbers source (TOP over sys.all_objects; value = start+(rn-1)*step, ordinality = ROW_NUMBER); rows (1,1)..(9,5) verified
SELECT * FROM generate_series(1, 10, 2) WITH ORDINALITY AS t(v, n)

-- CASE[fixed]: pg-gencol2 — a STORED generated column plus a GENERATED AS IDENTITY column now transpiles to MySQL (the AUTO_INCREMENT column gets a KEY, error 1075 otherwise). live-verified a=5 -> b=10 (a*2), c=1 (identity).
CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a*2) STORED, c INT GENERATED ALWAYS AS IDENTITY)

-- CASE[limit]: pg-generate-series — a SELECT-list generate_series (SRF) is moved to FROM and rewritten for Oracle (CONNECT BY) and T-SQL (numbers source) — 1..5 verified; MySQL has no inline table function (a recursive CTE can't be inlined in FROM) so it degrades (docs/03-unsupported.md). fails on mysql
SELECT generate_series(1, 5) AS r

-- CASE[fixed]: pg-gin-jsonb — JSONB columns now map per target (JSON / CLOB / NVARCHAR(MAX)) and a GIN/GiST/BRIN index degrades to a documented carrier + warning (access-method specific, physical-only). Live-verified emissions on mysql/oracle/tsql 2026-07-24.
CREATE TABLE t (a INT, b JSONB); CREATE INDEX ix ON t USING gin (b jsonb_path_ops)

-- CASE[fixed]: pg-greatest-null — PG/T-SQL GREATEST/LEAST ignore NULL args (GREATEST(1, NULL, 3) = 3); MySQL/Oracle propagate NULL. Drop a literal NULL arg on those targets.
SELECT GREATEST(1, NULL, 3) AS r

-- CASE[fixed]: pg-greatest-string — GREATEST compares by collation; force a binary collation on the first string literal so MySQL/T-SQL are case-sensitive like PG ('a', not 'B'). Live-verified.
SELECT GREATEST('a', 'B') AS r

-- CASE[fixed]: pg-grouping — faithful on Oracle/T-SQL (live multiset-equal values); MySQL keeps the base grouping with GROUPING() folded to 0 + a documented carrier + warning (its GROUPING() needs a WITH ROLLUP context). Live-verified 2026-07-24.
SELECT a,sum(c),grouping(a) FROM (SELECT 1 a,3 c) t GROUP BY GROUPING SETS ((a),())

-- CASE[limit]: pg-grouping-fn — GROUPING(x) over GROUP BY CUBE works on Oracle/T-SQL ((1,0)/(NULL,1) verified); MySQL has no CUBE so it degrades to the base grouping (subtotal rows omitted) where GROUPING is always 0 — the (1,0) row matches (docs/03-unsupported.md). fails on mysql
SELECT x, GROUPING(x) FROM (VALUES (1)) v(x) GROUP BY CUBE (x)

-- CASE[fixed]: pg-grouping-sets — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10)) v(x,y) GROUP BY GROUPING SETS ((x),())

-- CASE[fixed]: pg-grouping-sets2 — GROUPING SETS + GROUPING() are native on Oracle/T-SQL (JSON column type map cured the old tsql error); MySQL keeps the base grouping with GROUPING() folded to 0 + a documented carrier + warning. Live-executed 2026-07-24.
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, n, GROUPING(id), GROUPING(n) FROM t GROUP BY GROUPING SETS ((id),(n),())

-- CASE[fixed]: pg-groups2 — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); SELECT id, n, count(*) OVER (ORDER BY id GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM t

-- CASE[fixed]: pg-hash-all — fails on mysql, oracle, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT md5('abc'), encode(sha256('abc'::bytea), 'hex')

-- CASE[limit]: pg-hash-fns — lpad + md5 translate faithfully (Oracle LOWER(STANDARD_HASH(x,'MD5')), T-SQL LOWER(CONVERT(...,HASHBYTES('MD5',x),2)); '  x'/'9dd4e4...' verified), but PG sha256(bytea) returns a bytea digest where the other engines return a hex string (same digest, different representation) so it degrades to NULL + annotation (docs/03-unsupported.md). fails on mysql, oracle, tsql
SELECT lpad('x', 3), md5('x'), sha256('x'::bytea)

-- CASE[fixed]: pg-hex-literal — a hex literal cast to int uses Oracle TO_NUMBER('FF','XX') (HEXTORAW can't cast to a number); live-verified (255, 1500).
SELECT x'FF'::int AS h, 1.5e3 AS s

-- CASE[fixed]: pg-hexcast — fails on mysql, oracle, tsql. (195, b"'ENCODE' is not a recognized built-in function name.DB-Lib error message 20018, se
SELECT encode('Hello'::bytea,'hex'),decode('48656c6c6f','hex')::text

-- CASE[fixed]: pg-inet-ops — fails on oracle, tsql. (243, b'Type cidr is not a defined system type.DB-Lib error message 20018, severity 16:\nG
SELECT '192.168.1.0/24'::cidr >> '192.168.1.5'::inet, abbrev('10.0.0.0/8'::cidr)

-- CASE[fixed]: pg-initcap — fails on mysql, oracle, tsql. (195, b"'INITCAP' is not a recognized built-in function name.DB-Lib error message 20018, s
SELECT INITCAP('hello world') AS r

-- CASE[fixed]: pg-insert-select-conflict — INSERT … SELECT with ON CONFLICT (id) DO NOTHING now models the upsert per target (PG native, MySQL INSERT IGNORE, T-SQL/Oracle insert-only MERGE) instead of dropping the clause; the table has a PRIMARY KEY and a pre-seeded conflicting row (id=1) so DO NOTHING is a real no-op. Live-validated on all four engines 2026-07-24 (audit B1/N1).
CREATE TABLE t (id INT PRIMARY KEY, n INT); INSERT INTO t (id, n) VALUES (1, 10); INSERT INTO t (id, n) SELECT 1, 99 ON CONFLICT (id) DO NOTHING

-- CASE[fixed]: pg-intdiv — PostgreSQL / truncates two ints (2); MySQL/Oracle divide as decimal. Match with DIV (MySQL) / TRUNC (Oracle).
SELECT 5 / 2 AS r

-- CASE[fixed]: pg-intersect-all — fails on mysql. (1192, "Can't execute the given command because you have active locked tables or an active
SELECT 1 INTERSECT ALL SELECT 1

-- CASE[fixed]: pg-interval-arith — INTERVAL-literal arithmetic renders per target (T-SQL DATEADD, MySQL unquoted count, Oracle INTERVAL 'n' UNIT) and date-literal + integer keeps the day-add rewrites. Live-executed on all three 2026-07-24.
SELECT NOW() - INTERVAL '1 day', DATE '2020-01-01' + 7

-- CASE[fixed]: pg-interval-out — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '400 DAYS'.DB-Lib error message 20018, severity 15:\nGeneral
SELECT INTERVAL '1 year 2 months 3 days', INTERVAL '1.5 hours', justify_interval(INTERVAL '400 days')

-- CASE[limit]: pg-json-aggs — fails on tsql. json_agg/json_object_agg map faithfully to MySQL/Oracle JSON_ARRAYAGG/JSON_OBJECTAGG (Oracle key cast to VARCHAR2; value-verified); T-SQL has no JSON aggregate (docs/03-unsupported.md §3.9). Warned carrier on tsql.
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

-- CASE[fixed]: pg-left-neg — PG LEFT(s, -n) returns all-but-last-|n| ('ab'); MySQL returns ''. Emit LEFT(s, GREATEST(CHAR_LENGTH(s) + n, 0)) on MySQL.
SELECT LEFT('abc', -1) AS r

-- CASE[fixed]: pg-left-round — PG 2.9::int rounds (3) so LEFT('hello', 3) = 'hel'; fixed by the T-SQL CAST-to-int ROUND wrap (a fractional literal cast now rounds). Live-verified 'hel'.
SELECT LEFT('hello', 2.9::int) AS r

-- CASE[limit]: pg-like-cs — fails on mysql, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'ABC' LIKE 'abc' AS r

-- CASE[fixed]: pg-like-escape — fails on oracle. FUNC-DIFF: source=(('1', '0', '1'),) target=(('0', '0', '1'),)
SELECT 'a%b' LIKE 'a\%b', 'AbC' LIKE 'abc', 'AbC' ILIKE 'abc'

-- CASE[fixed]: pg-log-2arg — PostgreSQL LOG(base, x); T-SQL LOG(x, base) — args swapped so LOG(2,8)=3 on both.
SELECT LOG(2, 8) AS r

-- CASE[fixed]: pg-log-base — fails on mysql, tsql. FUNC-DIFF: source=(('2',),) target=(('4.60517',),)
SELECT LOG(100) AS r

-- CASE[limit]: pg-loop-notice — LOOP + RAISE NOTICE compiles on Oracle/MySQL; T-SQL scalar functions forbid PRINT/side-effects (error 443) so it degrades to a carrier (docs/03-unsupported.md). fails on tsql
CREATE FUNCTION f() RETURNS void AS $$ DECLARE i INT:=0; BEGIN LOOP i:=i+1; EXIT WHEN i>=3; END LOOP; RAISE NOTICE 'done'; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-lpad-shrink — fails on tsql. FUNC-DIFF: source=(('hel',),) target=(('llo',),)
SELECT LPAD('hello', 3) AS r

-- CASE[fixed]: pg-ltrim-set — fails on mysql, tsql. FUNC-DIFF: source=(('abc',),) target=(('',),)
SELECT ltrim('xxabc', 'x') AS r

-- CASE[fixed]: pg-make-date — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.MA
SELECT MAKE_DATE(2020, 6, 15), MAKE_TIME(10, 30, 0)

-- CASE[fixed]: pg-md5 — fails on oracle, tsql. (195, b"'MD5' is not a recognized built-in function name.DB-Lib error message 20018, sever
SELECT MD5('abc') AS r

-- CASE[fixed]: pg-mod-decimal — PG MOD(10, 3.5) now translates faithfully; the remaining diff is decimal-precision only. (value equal, precision-only diff; maintainer policy 2026-07-19)
SELECT MOD(10, 3.5::numeric) AS r

-- CASE[fixed]: pg-multi-out — a PG function with only OUT params (no RETURNS) returns void; on Oracle a FUNCTION must RETURN a type (RETURN void = PLS-00201), so it now emits a PROCEDURE (a IN, b/c OUT); compiles VALID and f(5) yields b=5, c=10
CREATE FUNCTION f(a INT, OUT b INT, OUT c INT) AS $$ BEGIN b := a; c := a * 2; END; $$ LANGUAGE plpgsql

-- CASE[limit]: pg-name-locale — fails on mysql, tsql. to_char with locale month/day NAMES (Day/Month/FMDay) is locale-dependent, no cross-engine equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(DATE '2020-06-15','Day'), to_char(DATE '2020-06-15','Month'), trim(to_char(DATE '2020-06-15','FMDay'))

-- CASE[limit]: pg-named-exception — the named exception maps per engine (PG division_by_zero -> Oracle ZERO_DIVIDE), valid + f()=-1 on Oracle/MySQL; T-SQL scalar functions forbid TRY/CATCH (error 443) so the exception handler has no function-level equivalent and degrades to a carrier (docs/03-unsupported.md). fails on tsql
CREATE FUNCTION f() RETURNS INT AS $$ BEGIN RETURN 1/0; EXCEPTION WHEN division_by_zero THEN RETURN -1; WHEN OTHERS THEN RAISE; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-named-window — the WINDOW clause is inlined into each OVER (ORDER BY x) so no OVER () is emitted; live-verified (1,1,1),(2,3,2) on Oracle.
SELECT x,sum(x) OVER w,rank() OVER w FROM (SELECT 1 x UNION ALL SELECT 2) t WINDOW w AS (ORDER BY x)

-- CASE[fixed]: pg-named-window2 — fails on oracle. ORA-30485: missing ORDER BY expression in the window specification
CREATE TABLE t (id INT, n INT, s VARCHAR(50)); SELECT id, LAG(n) OVER w, LEAD(n) OVER w FROM t WINDOW w AS (PARTITION BY s ORDER BY id)

-- CASE[limit]: pg-nan-cmp — PostgreSQL numeric NaN (NaN > 1 = true) has no MySQL equivalent (CAST('NaN' AS DECIMAL) collapses to 0); emit the cast + a documented carrier (docs/03-unsupported.md). fails on mysql
SELECT 'NaN'::numeric > 1 AS r

-- CASE[fixed]: pg-nested-call — CALL inner_p() maps to the target's call form (Oracle inner_p();, T-SQL EXEC inner_p;, MySQL CALL inner_p();). The RED PLS-00201 was a missing-dependency artifact — the snippet never defines inner_p; the transpiled proc compiles valid once it exists (verified against a stub).
CREATE PROCEDURE outer_p() AS $$ BEGIN CALL inner_p(); END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-network-types — fails on oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INET.DB-Lib error messag
CREATE TABLE t (ip INET, mac MACADDR, cidr CIDR)

-- CASE[limit]: pg-not-null-is-null — fails on tsql. (NOT NULL) IS NULL is 1 (3VL: NOT NULL is NULL, which IS null); the IR dropped the source parens so NOT re-associated. Parens restored -> live 1 on PG/MySQL/Oracle; T-SQL has no boolean value type (NOT of a non-predicate is error 4145) so it degrades to a carrier (docs/03-unsupported.md §3.18).
SELECT (NOT NULL) IS NULL AS r

-- CASE[fixed]: pg-now-fns — fails on mysql, oracle, tsql. (156, b"Incorrect syntax near the keyword 'CURRENT_TIME'.DB-Lib error message 20018, sever
SELECT now(), current_date, current_time, localtimestamp, clock_timestamp()

-- CASE[fixed]: pg-now-variants — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '3'.DB-Lib error message 20018, severity 15:\nGeneral SQL Se
SELECT now(), current_timestamp, current_timestamp(3), current_date, current_time, localtimestamp, clock_timestamp()

-- CASE[fixed]: pg-num-literals — PG16 reads 0x1F as the INTEGER 31 (other engines read hex literals as bytes); a PG-source hex literal now emits its decimal value. Live-verified ('1000','0.015','0.5','5','31') on mysql.
SELECT 1e3, 1.5e-2, .5, 5., 0x1F::text

-- CASE[fixed]: pg-num-nonnulls — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.NU
SELECT NUM_NONNULLS(1, NULL, 2) AS r

-- CASE[fixed]: pg-num-to-str — trailing-zero literals keep their source text (5.50::text stays '5.50'); the residual 'd=' scale difference (20-digit vs 5-digit expansions of 1/3) is the maintainer's approved precision policy (2026-07-19).
SELECT 'n='||5, 'x='||5.50, 'd='||(1.0/3), 5.50::text

-- CASE[limit]: pg-numfmt-lead — fails on mysql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(0.5, '0.00') AS r

-- CASE[limit]: pg-numfmt-spec — fails on oracle. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(1234.5,'L9G999D99MI'),to_char(-5,'999PR'),to_char(255,'FMRN')

-- CASE[limit]: pg-numfmt-thousands — fails on mysql, tsql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(1234567.891, '9,999,999.99') AS r

-- CASE[fixed]: pg-numnulls — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.nu
SELECT num_nonnulls(1,NULL,2),num_nulls(1,NULL,2)

-- CASE[fixed]: pg-numtypes — PostgreSQL SERIAL maps to a MySQL AUTO_INCREMENT column, which MySQL requires to be indexed (error 1075); a KEY is added when nothing already covers it. live-verified CREATE runs.
CREATE TABLE t (a SMALLINT, b INT, c BIGINT, d NUMERIC(10,2), e REAL, f DOUBLE PRECISION, g SERIAL, h MONEY)

-- CASE[fixed]: pg-order-case-sens — force a binary collation on the (provably-string) ORDER BY key so MySQL/T-SQL sort case-sensitively like PG (Apple, Cherry, banana).
SELECT x FROM (SELECT 'Apple' x UNION SELECT 'banana' UNION SELECT 'Cherry') t ORDER BY x

-- CASE[fixed]: pg-order-nulls-default — PostgreSQL sorts NULLs high by default; MySQL/T-SQL sort them low. Emulate with a null-priority key.
SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x

-- CASE[fixed]: pg-overlay — OVERLAY(s PLACING r FROM start FOR len) rewritten per engine (T-SQL STUFF, MySQL INSERT(), Oracle SUBSTR concat, PG native); 'aXYdef' verified equal on all three
SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS o

-- CASE[fixed]: pg-pad-repeat — PG lpad/rpad/repeat/reverse now translate (Oracle RPAD/REVERSE); stale tag, live-verified equal.
SELECT lpad('7',3,'0'),rpad('7',3,'x'),repeat('ab',3),reverse('abc'),repeat(' ',3)

-- CASE[fixed]: pg-pi-fns — PG pi()/trunc/round now translate (Oracle ACOS(-1) for PI); stale tag, live-verified equal.
SELECT trunc(pi()::numeric, 4), round(pi()::numeric, 4)

-- CASE[fixed]: pg-position-case — POSITION goes through the CHARINDEX path, so the case-sensitivity fix (BINARY/BIN2 on the literal haystack) applies: 0 on MySQL/T-SQL (live-verified).
SELECT POSITION('a' IN 'ABC') AS r

-- CASE[fixed]: pg-position-empty — PG POSITION('' IN x) is 1; Oracle INSTR -> NULL, T-SQL CHARINDEX -> 0. Recover 1 (Oracle COALESCE, T-SQL CASE) — shared empty-needle handler.
SELECT POSITION('' IN 'abc') AS r

-- CASE[fixed]: pg-quote — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.QU
SELECT QUOTE_LITERAL('O''Brien'), QUOTE_IDENT('my col')

-- CASE[fixed]: pg-range-types — fails on mysql, oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type INT4RANGE.DB-Lib error m
CREATE TABLE t (rng INT4RANGE, tsr TSRANGE)

-- CASE[fixed]: pg-realworld-transfer — PG check_violation (no predefined Oracle exception) now lands as WHEN OTHERS + SQLCODE = -2290 + RAISE (live-compiled VALID on oracle); the T-SQL leg degrades documented (TRY/CATCH in a scalar function, error 443).
CREATE TABLE accounts (id SERIAL PRIMARY KEY, balance NUMERIC(12,2) DEFAULT 0 CHECK (balance >= 0));
CREATE TABLE ledger (id SERIAL PRIMARY KEY, account_id INT REFERENCES accounts(id) ON DELETE CASCADE, amount NUMERIC(12,2), ts TIMESTAMPTZ DEFAULT now());
CREATE FUNCTION transfer(from_id INT, to_id INT, amt NUMERIC) RETURNS VOID AS $$
BEGIN UPDATE accounts SET balance = balance - amt WHERE id = from_id;
UPDATE accounts SET balance = balance + amt WHERE id = to_id;
INSERT INTO ledger (account_id, amount) VALUES (from_id, -amt), (to_id, amt);
EXCEPTION WHEN check_violation THEN RAISE EXCEPTION 'insufficient funds'; END; $$ LANGUAGE plpgsql;

-- CASE[fixed]: pg-recursive-func — stale finding: the all-branches-return trailing RETURN NULL fix and the dbo.f() recursive-call qualification already cure it; live-compiled and dbo.f(4)=24 on tsql 2026-07-24.
CREATE FUNCTION f(n INT) RETURNS INT AS $$ BEGIN IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF; END; $$ LANGUAGE plpgsql

-- CASE[fixed]: pg-regexp-backref — PG regexp_replace flags normalized: drop the 'g' (Oracle/MySQL are global by default, so 'g' was mis-read as Oracle's numeric position), map no-flags to occurrence 1, carry 'i', and for MySQL double the pattern's backslashes + rewrite \N backrefs to $N; 'a[1]b[2]' verified on both
SELECT regexp_replace('a1b2', '(\d)', '[\1]', 'g') AS r

-- CASE[fixed]: pg-regexp-cnt — fails on mysql. (1305, 'FUNCTION unique_val_a1fe6b8252a9.REGEXP_COUNT does not exist')
SELECT regexp_count('a1b2','[0-9]'),regexp_instr('a1b2','[0-9]',1,2)

-- CASE[fixed]: pg-regexp-matches — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.RE
SELECT REGEXP_MATCHES('a1b2', '[0-9]', 'g') AS r

-- CASE[fixed]: pg-regexp-split-table — fails on oracle, tsql. (208, b"Invalid object name 'dbo.regexp_split_to_table'.DB-Lib error message 20018, severi
SELECT * FROM regexp_split_to_table('a,b,c', ',')

-- CASE[fixed]: pg-repeat-left-right — fails on oracle. ORA-00904: "RIGHT": invalid identifier
SELECT REPEAT('ab', 3), LEFT('abc', 2), RIGHT('abc', 2)

-- CASE[fixed]: pg-rollup — fails on mysql, oracle, tsql. (8120, b"Column 'v.x' is invalid in the select list because it is not contained in either 
SELECT x, SUM(y) FROM (VALUES (1,10),(1,20)) v(x,y) GROUP BY ROLLUP (x)

-- CASE[fixed]: pg-rollup2 — fails on mysql, oracle, tsql. (8120, b"Column 't.a' is invalid in the select list because it is not contained in either 
SELECT a,b,sum(c) FROM (SELECT 1 a,2 b,3 c) t GROUP BY ROLLUP(a,b)

-- CASE[fixed]: pg-round-1005 — PG numeric ROUND half-up (1.005->1.01); the unbounded ::numeric cast now carries a scale so the fraction survives.
SELECT ROUND(1.005::numeric, 2) AS r

-- CASE[fixed]: pg-round-2675 — PG numeric ROUND is half-up (2.675->2.68), same on all; the divergence was a bare DECIMAL cast truncating to scale 0 (fixed: scale the unbounded numeric cast).
SELECT ROUND(2.675::numeric, 2) AS r

-- CASE[fixed]: pg-savepoint — SAVEPOINT in a batch was sqlglot-misparsed as an Alias (SAVEPOINT AS sp, rejected everywhere) and a re-transpile re-introduced it; modeled as a passthrough (T-SQL SAVE TRANSACTION). ROLLBACK TO SAVEPOINT keeps its name (T-SQL ROLLBACK TRANSACTION sp; MySQL ROLLBACK TO sp). Batch executes on MySQL and T-SQL.
BEGIN; SAVEPOINT sp; ROLLBACK TO SAVEPOINT sp; COMMIT

-- CASE[fixed]: pg-scale — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.sc
SELECT scale(1.230), trim_scale(1.230)

-- CASE[fixed]: pg-scientific — a >28-digit integer literal cast to bare numeric now sizes the target DECIMAL to the literal (DECIMAL(30,0)) instead of overflowing the (38,10) default; float legs render equal. Live-verified exact 30-digit value on mysql.
SELECT 1e20::float, 1e-20::float, 123456789012345678901234567890::numeric

-- CASE[fixed]: pg-select-into-ctas — PostgreSQL SELECT … INTO TEMP t2 becomes Oracle CREATE GLOBAL TEMPORARY TABLE t2 AS SELECT …; the plain SELECT INTO becomes CREATE TABLE AS SELECT. live-verified batch runs.
CREATE TABLE t (id INT);
SELECT id INTO TEMP t2 FROM t;
CREATE TABLE t3 AS SELECT * FROM t;

-- CASE[fixed]: pg-seq-use — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne
CREATE SEQUENCE s; SELECT nextval('s'),currval('s'),setval('s',10)

-- CASE[fixed]: pg-sequence — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ne
CREATE SEQUENCE seq; SELECT nextval('seq'), currval('seq')

-- CASE[fixed]: pg-serial-bit — fails on oracle, tsql. (2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit
CREATE TABLE t (a BIGSERIAL, flags BIT(8), vb VARBIT(16))

-- CASE[fixed]: pg-set-default — PostgreSQL ALTER COLUMN a SET DEFAULT v maps to Oracle MODIFY a DEFAULT v and T-SQL ADD CONSTRAINT DF_t_a DEFAULT v FOR a (same handler as the MySQL form). live-verified DDL runs.
CREATE TABLE t (a INT, b INT); ALTER TABLE t ALTER COLUMN a SET DEFAULT 5

-- CASE[fixed]: pg-setweight — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.se
SELECT setweight(to_tsvector('cat'), 'A') AS r

-- CASE[fixed]: pg-size-funcs — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.pg
SELECT pg_size_pretty(1024::bigint), pg_relation_size('pg_class')

-- CASE[fixed]: pg-spectypes — fails on oracle, tsql. (2716, b'Column, parameter, or variable #2: Cannot specify a column width on data type bit
CREATE TABLE t (a BYTEA, b BIT(8), c VARBIT(16), d BOOLEAN, e UUID, f XML, g JSON, h JSONB)

-- CASE[fixed]: pg-split-part — fails on mysql, oracle, tsql. (195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018
SELECT SPLIT_PART('a,b,c', ',', 2) AS r

-- CASE[fixed]: pg-srf-in-select — FROM generate_series(1,3) rewritten to Oracle CONNECT BY (SELECT start+(LEVEL-1) FROM DUAL CONNECT BY LEVEL <= count) and a T-SQL numbers source; the correlation alias doubles as the value column so outer refs resolve; rows (1,1)/(2,4)/(3,9) verified
SELECT g, g*g FROM generate_series(1,3) g

-- CASE[limit]: pg-str-lt — fails on mysql, tsql. APPROVED LIMIT (2026-07-18): string-comparison collation (case/accent/trailing-space) is a per-column/default-collation property, not statement-compensable (docs/03-unsupported.md §2). FUNC-DIFF: source=(('0',),) target=(('1',),)
SELECT 'apple' < 'Banana' AS r

-- CASE[fixed]: pg-stragg-order — STRING_AGG(x::text ORDER BY x)'s folded value cast is portabilized to VARCHAR (LISTAGG rejects CLOB, T-SQL STRING_AGG rejects TEXT). Live-verified '1,2'.
SELECT string_agg(x::text,',' ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2) t

-- CASE[fixed]: pg-string-agg-order — STRING_AGG(x::text ORDER BY x)'s folded value cast is portabilized to VARCHAR (LISTAGG/STRING_AGG reject CLOB/TEXT). Live-verified '1,2'.
SELECT STRING_AGG(x::text, ',' ORDER BY x) FROM (VALUES (1),(2)) v(x)

-- CASE[fixed]: pg-string-fns2 — fails on mysql, oracle, tsql. (195, b"'SPLIT_PART' is not a recognized built-in function name.DB-Lib error message 20018
SELECT split_part('a,b,c', ',', 2), left('abc',-1), right('abc',-1)

-- CASE[fixed]: pg-string-fns3 — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT starts_with('abc','ab'), string_to_array('a.b.c','.')

-- CASE[fixed]: pg-string-split-fns — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.st
SELECT string_to_table('a,b,c', ','), regexp_split_to_array('a1b2', '\d')

-- CASE[fixed]: pg-string-to-array — fails on mysql, oracle, tsql. (195, b"'STRING_TO_ARRAY' is not a recognized built-in function name.DB-Lib error message 
SELECT string_to_array('a,b,c', ',')

-- CASE[fixed]: pg-strpos-empty — PG STRPOS(x, '') is 1; Oracle INSTR -> NULL, T-SQL CHARINDEX -> 0. Recover 1 (Oracle COALESCE, T-SQL CASE) — shared empty-needle handler.
SELECT STRPOS('', '') AS r

-- CASE[fixed]: pg-substr-edge — start<=0 rewrite + LEFT(s,-n) clamp emulation + RIGHT(s,-n) -> SUBSTR(s, n+1) (all but the first n). Live-verified ('hello','el','hell','ello') on mysql.
SELECT substring('hello',-3), substr('hello',2,2), left('hello',-1), right('hello',-1)

-- CASE[fixed]: pg-substr-zero — PostgreSQL SUBSTRING with start<=0 counts out-of-range positions toward the length ('ab'); rebase to start 1 with length start+len-1 on Oracle/MySQL.
SELECT SUBSTRING('abcdef', 0, 3) AS r

-- CASE[limit]: pg-substring-escape — SUBSTRING(x FROM SIMILAR-TO pattern FOR escape) is the SQL-standard regex form; its %/_ metachars and #"…"# capture markers differ from POSIX, so no faithful cross-engine rewrite exists — degrades to NULL + annotation (docs/03-unsupported.md). fails on oracle, tsql
SELECT substring('a1b2' from '([a-z])([0-9])' for '#') AS r

-- CASE[limit]: pg-substring-regex — SUBSTRING(x FROM POSIX pattern) → Oracle/MySQL REGEXP_SUBSTR ('1' verified live); T-SQL has no POSIX regex engine (2012+ target) so it degrades to NULL + annotation (docs/03-unsupported.md). fails on tsql
SELECT SUBSTRING('a1b2' FROM '[0-9]+') AS r

-- CASE[fixed]: pg-synonym-as-view — validator-environment artifact, not a defect: the live check runs as SYSTEM, whose schema has the data-dictionary synonym SYN, so CREATE VIEW syn hits ORA-00955 there; under a normal schema the emitted CREATE OR REPLACE VIEW syn is valid (live-verified 2026-07-24).
CREATE TABLE t (a INT); CREATE VIEW syn AS SELECT * FROM t

-- CASE[limit]: pg-tablesample — MySQL has no TABLESAMPLE (row sampling is also non-deterministic); degraded to a documented carrier + warning (docs/03-unsupported.md). PG->T-SQL/Oracle sample natively. fails on mysql
CREATE TABLE t (id INT); SELECT * FROM t TABLESAMPLE BERNOULLI(50)

-- CASE[limit]: pg-tochar-fmts — fails on oracle. date format mask uses a bare-letter literal / locale name / exotic token that cannot round-trip to a quoted cross-engine mask (docs/03-unsupported.md §3.1).
SELECT to_char(now(),'Day'), to_char(now(),'FMDay'), to_char(now(),'IW'), to_char(now(),'TZ')

-- CASE[fixed]: pg-tochar-iso — to_char(ts, mask) date formatting -> MySQL DATE_FORMAT, T-SQL FORMAT (via the strftime-model mask translation). live-verified 2020-06-15T14:30:45 on all four.
SELECT to_char(TIMESTAMP '2020-06-15 14:30:45', 'YYYY-MM-DD"T"HH24:MI:SS') AS r

-- CASE[limit]: pg-tochar-neg — fails on mysql, tsql. Oracle/PG numeric TO_CHAR mask (grouping pad space / currency L / sign MI / hex XX) has no faithful MySQL/T-SQL FORMAT equivalent (docs/03-unsupported.md §3.1).
SELECT to_char(-1234.5, '9999.99') AS r

-- CASE[fixed]: pg-todate2 — to_date/to_timestamp map to MySQL STR_TO_DATE / a DATETIME literal; live-verified 2020-06-15 and 2020-06-15 10:30 (same instant, tz-precision on col2).
SELECT to_date('06/15/2020','MM/DD/YYYY'),to_timestamp('2020-06-15 10:30','YYYY-MM-DD HH24:MI')

-- CASE[limit]: pg-tohex2 — PostgreSQL to_char(n,'XX') emits the literal template 'XX' (it has no hex number format), whereas Oracle's TO_CHAR reads X as hex (' FF'); the mask is not portable so the statement is gated + annotated (docs/03-unsupported.md). fails on oracle, tsql
SELECT to_hex(255), to_char(255, 'XX')

-- CASE[limit]: pg-totimestamp-long — fails on mysql, oracle, tsql. parsing a locale month NAME ('Month DD YYYY') is NLS-dependent, no reproducible cross-engine parse (docs/03-unsupported.md §3.1).
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

-- CASE[fixed]: pg-trim-len — LENGTH/CHAR_LENGTH of a literal (through TRIM of a literal) folds to PG's code-point count at compile time (2, 0) — this also sidesteps Oracle's LENGTH('')=NULL. Live-verified on oracle/tsql.
SELECT CHAR_LENGTH('  '), LENGTH(TRIM('  '))

-- CASE[fixed]: pg-trim-translate — fails on tsql. FUNC-DIFF: source=(('hi', '7', 'XbZ'),) target=(('', '', 'XbZ'),)
SELECT trim(both 'x' from 'xxhixx'), ltrim('007','0'), translate('abc','ac','XZ')

-- CASE[fixed]: pg-truncate-restart — TRUNCATE … RESTART IDENTITY is the default on MySQL/Oracle/T-SQL (strip it, faithful); CASCADE is kept on Oracle, stripped with a carrier on MySQL/T-SQL. Live-verified valid on all targets. 
CREATE TABLE t (id INT); TRUNCATE TABLE t RESTART IDENTITY CASCADE

-- CASE[fixed]: pg-ts-headline — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ts
SELECT ts_headline('the quick fox', to_tsquery('fox')) AS r

-- CASE[fixed]: pg-ts-rank — fails on mysql, oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.ts
SELECT ts_rank(to_tsvector('the cat'), to_tsquery('cat')) AS r

-- CASE[fixed]: pg-tstzrange — fails on mysql, oracle, tsql. (102, b"Incorrect syntax near '1 DAY'.DB-Lib error message 20018, severity 15:\nGeneral SQ
SELECT tstzrange(now(), now() + INTERVAL '1 day') AS r

-- CASE[limit]: pg-tz-convert — AT TIME ZONE is not portable (Oracle/MySQL have no such operator; the session-tz-dependent display differs on PG/T-SQL) and degrades to NULL + annotation + warning off PG — the same approved limit as ts-at-time-zone (docs/03-unsupported.md). fails on mysql, oracle, tsql
SELECT TIMESTAMP '2020-06-15 10:00:00' AT TIME ZONE 'America/New_York', now() AT TIME ZONE 'UTC'

-- CASE[fixed]: pg-tz-interval — same type-gap mapping as pg-dttypes (TIMETZ/INTERVAL -> INTERVAL DAY TO SECOND, warned notes, docs/03-unsupported.md §3.19). Live-executed on oracle 2026-07-24.
CREATE TABLE t (a TIMESTAMPTZ, b TIME WITH TIME ZONE, c INTERVAL)

-- CASE[limit]: pg-unicode-escape — U&'…' Unicode-escape literals are mis-parsed by the parser (U & '…'), so the statement degrades to a documented carrier + warning off PG instead of shipping a silently wrong expression (docs/03-unsupported.md §3.22). fails on mysql, oracle, tsql
SELECT U&'\0041' AS r

-- CASE[limit]: pg-unique-nulls-notdistinct — PostgreSQL UNIQUE … NULLS NOT DISTINCT (NULLs compare equal, so only one NULL row is allowed) has no equivalent; the modifier is stripped to a plain UNIQUE (NULLs distinct) and the divergence is annotated (docs/03-unsupported.md). fails on mysql, oracle
CREATE TABLE t (a INT, b INT, UNIQUE NULLS NOT DISTINCT (a, b))

-- CASE[fixed]: pg-week — EXTRACT(WEEK) ISO 8601. T-SQL DATEPART(WEEK) gave 2; DATEPART(ISO_WEEK,d) gives PG's 1. live-verified.
SELECT EXTRACT(WEEK FROM DATE '2020-01-05') AS r

-- CASE[fixed]: pg-week-2016 — EXTRACT(WEEK) ISO year-boundary: 2016-01-01 is ISO week 53 of 2015 (PG=53). MySQL WEEK(d,3) and T-SQL DATEPART(ISO_WEEK,d) both give 53; native gave 1. live-verified.
SELECT EXTRACT(WEEK FROM DATE '2016-01-01') AS r

-- CASE[fixed]: pg-week-jan1 — EXTRACT(WEEK) ISO: 2020-01-01 is ISO week 1 (PG=1). MySQL WEEK(d,3) gives 1; native EXTRACT(WEEK) (mode 0) gave 0. live-verified.
SELECT EXTRACT(WEEK FROM DATE '2020-01-01') AS r

-- CASE[fixed]: pg-width-bucket — fails on mysql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.WI
SELECT width_bucket(5, 0, 10, 5) AS r

-- CASE[limit]: pg-xmlelement — fails on mysql, tsql. XMLELEMENT maps faithfully between PostgreSQL & Oracle, but MySQL/T-SQL have no XMLELEMENT (docs/03-unsupported.md §5, §2). Warned carrier on mysql/tsql.
SELECT XMLELEMENT(NAME foo, 'bar') AS r

-- CASE[limit]: pg-xmlelement2 — fails on mysql, tsql. Lowercase spelling of pg-xmlelement; XMLELEMENT has no MySQL/T-SQL equivalent (docs/03-unsupported.md §5, §2). Warned carrier on mysql/tsql.
SELECT xmlelement(name foo, 'bar')

-- CASE[fixed]: pg-xpath — fails on oracle, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.xp
SELECT xpath('/a/text()', '<a>1</a>'::xml)

-- CASE[fixed]: pg15-merge — fails on oracle, tsql. (2715, b'Column, parameter, or variable #3: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (id INT, n INT, data JSON); CREATE TABLE s (id INT, n INT); MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPDATE SET n=s.n WHEN NOT MATCHED THEN INSERT VALUES (s.id, s.n)

-- CASE[limit]: po-agg-bit — fails on oracle, tsql. BIT_AND/BIT_OR/BIT_XOR aggregates map faithfully PostgreSQL<->MySQL (value-verified); Oracle/T-SQL have no bit aggregate (docs/03-unsupported.md §3.10). Warned carrier on oracle/tsql.
SELECT BIT_AND(x),BIT_OR(x),BIT_XOR(x) FROM (VALUES (3),(5),(6)) v(x)

-- CASE[fixed]: po-distinct-case — force a binary collation on the DISTINCT string column so MySQL/T-SQL keep 'a'/'A' distinct like PG (A, B, a); null-priority ORDER key skipped under DISTINCT.
SELECT DISTINCT x FROM (VALUES ('a'),('A'),('a'),('B')) v(x) ORDER BY x

-- CASE[fixed]: po-distinct-null — MySQL keeps the null-priority key (live 1,2,NULL exact); T-SQL now wraps the DISTINCT in a derived table and orders OUTSIDE it, so the null-priority key is legal there too (live 1,2,NULL exact, 2026-07-24).
SELECT DISTINCT x FROM (VALUES (1),(NULL),(1),(NULL),(2)) v(x) ORDER BY x

-- CASE[fixed]: po-group-case — force a binary collation consistently on the SELECT/GROUP BY/ORDER BY string key so MySQL/T-SQL group case-sensitively like PG (A,a,b each once).
SELECT x, COUNT(*) FROM (VALUES ('a'),('A'),('b')) v(x) GROUP BY x ORDER BY x

-- CASE[fixed]: po-group-null — PostgreSQL NULLS-LAST default preserved via a null-priority ORDER BY key on MySQL/T-SQL.
SELECT x, COUNT(*) FROM (VALUES (1),(NULL),(1),(NULL)) v(x) GROUP BY x ORDER BY x

-- CASE[fixed]: po-order-strings — force a binary collation on the (provably-string) ORDER BY key so MySQL sorts case-sensitively like PG (Apple, Banana, banana, cherry). 
SELECT x FROM (VALUES ('banana'),('Apple'),('cherry'),('Banana')) v(x) ORDER BY x

-- CASE[fixed]: postgresql-drop-CHECK — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'CHECK' absent from valid tsql output, no warning (target supports it)
CREATE TABLE t (age INT CHECK (age >= 0))

-- CASE[fixed]: postgresql-drop-DEFERRABLE — fails on oracle. SILENT CLAUSE DROP: 'DEFERRABLE' absent from valid oracle output, no warning (target suppo
CREATE TABLE t (id INT PRIMARY KEY DEFERRABLE INITIALLY DEFERRED)

-- CASE[fixed]: postgresql-drop-ON\s+DELETE\s+ — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'ON\s+DELETE\s+CASCADE' absent from valid tsql output, no warning (tar
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE CASCADE)

-- CASE[fixed]: postgresql-drop-ON\s+UPDATE\s+ — fails on mysql. SILENT CLAUSE DROP: 'ON\s+UPDATE\s+CASCADE' absent from valid mysql output, no warning (ta
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) ON UPDATE CASCADE)

-- CASE[fixed]: postgresql-drop2-100|START — fails on oracle, tsql. SILENT CLAUSE DROP: '100|START' absent from valid tsql output, no warning
CREATE TABLE t (id INT GENERATED BY DEFAULT AS IDENTITY (START WITH 100 INCREMENT BY 5))

-- CASE[fixed]: postgresql-drop2-CONCURRENTLY — fails on mysql, tsql. SILENT CLAUSE DROP: 'CONCURRENTLY' absent from valid tsql output, no warning
CREATE TABLE t (a INT); CREATE INDEX CONCURRENTLY ix ON t (a)

-- CASE[fixed]: postgresql-drop2-EXCLUDE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'EXCLUDE' absent from valid tsql output, no warning
CREATE TABLE t (a INT, EXCLUDE USING btree (a WITH =))

-- CASE[fixed]: postgresql-drop2-NULLS\s+FIRS — Oracle rejects NULLS FIRST/LAST in an index (ORA-00907) and T-SQL/MySQL have no such clause; the drop (physical null-order only, no query-result impact) is now a carrier + warning, no longer silent.
CREATE TABLE t (a INT); CREATE INDEX ix ON t (a NULLS FIRST)

-- CASE[fixed]: postgresql-drop4-BY\s+DEFAULT — fails on tsql. SILENT CLAUSE DROP: 'BY\s+DEFAULT|GENERATED' absent from valid tsql output, no warning
CREATE TABLE t (a INT GENERATED BY DEFAULT AS IDENTITY)

-- CASE[fixed]: postgresql-drop4-COLLATE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'COLLATE' absent from valid tsql output, no warning
CREATE TABLE t (a TEXT COLLATE "en_US")

-- CASE[fixed]: postgresql-drop4-MATCH\s+FULL — fails on oracle. SILENT CLAUSE DROP: 'MATCH\s+FULL' absent from valid oracle output, no warning
CREATE TABLE p (id INT PRIMARY KEY); CREATE TABLE c (pid INT REFERENCES p(id) MATCH FULL)

-- CASE[fixed]: postgresql-drop5-CHECK|IN\s*\ — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'CHECK|IN\s*\(' absent from valid tsql output, no warning
CREATE TABLE t (a INT CHECK (a IN (1,2,3)))

-- CASE[fixed]: postgresql-drop5-REFERENCES — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'REFERENCES' absent from valid tsql output, no warning
CREATE TABLE t (a INT PRIMARY KEY, b INT REFERENCES t(a))

-- CASE[fixed]: postgresql-qdrop-FOR\s+UPDATE — fails on tsql. SILENT CLAUSE DROP: 'FOR\s+UPDATE' absent from valid tsql output, no warning
SELECT x FROM (VALUES (1),(2)) v(x) FOR UPDATE

-- CASE[fixed]: postgresql-qdrop-ROWS\s+BETWE — fails on mysql, oracle, tsql. SILENT CLAUSE DROP: 'ROWS\s+BETWEEN' absent from valid tsql output, no warning
SELECT x, SUM(x) OVER (ORDER BY x ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM (VALUES (1),(2)) v(x)


-- CASE[open][class=func]: pg-distinct-on — DISTINCT ON (a) returns ONE row per a (the first by ORDER BY); it is rewritten to a plain SELECT DISTINCT a, b, which returns every distinct (a,b) PAIR. Different result set, no warning. PG=[(1,10),(2,5)]; MySQL/Oracle/T-SQL=[(1,10),(1,20),(2,5),(2,7)].
SELECT DISTINCT ON (a) a, b FROM (VALUES (1,10),(1,20),(2,5),(2,7)) v(a,b) ORDER BY a, b

-- CASE[fixed][class=lying-warning]: pg-window-over-falsewarn — EVERY window function (any OVER clause) emits the tripwire warning "internal: unread sqlglot arg 'over' on Window — construct may be dropped", but nothing is dropped: the OVER clause is emitted faithfully and the result is correct on all targets. sqlglot 30.14 populates Window.args['over']='OVER' (a keyword marker, not a droppable construct — the real spec lives in partition_by/order/spec, all read), so the unread-args tripwire false-fires on all sources/targets. This drowns the warning signal (real drops indistinguishable from noise).
SELECT a, SUM(a) OVER (ORDER BY a) AS s FROM (VALUES (1),(2),(3)) v(a) ORDER BY a

-- CASE[open][class=silent-drop]: pg-fk-onupdate-oracle — FK ON UPDATE CASCADE is silently dropped into Oracle (Oracle FKs support no ON UPDATE action at all). ON DELETE actions survive but the cascade-on-parent-key-update behavior vanishes with NO warning. (The existing [fixed] postgresql-drop-ON UPDATE CASCADE only covers MySQL, which now PRESERVES it; Oracle is uncovered and silent.) Oracle can't express it, so the correct outcome is a carrier + warning like the NULLS-FIRST-index drop, not silence.
CREATE TABLE redb_p (id INT PRIMARY KEY); CREATE TABLE redb_c (pid INT REFERENCES redb_p(id) ON UPDATE CASCADE)

-- CASE[open][class=invalid]: pg-window-groups-frame — a GROUPS window-frame mode (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) is emitted verbatim to T-SQL and MySQL, which support only ROWS/RANGE frames and REJECT it at runtime (SQL Server 102 'Incorrect syntax near GROUPS'; MySQL 1235 'does not yet support GROUPS'). No warning (sqlglot parses GROUPS so the target-parse gate passes). Oracle supports GROUPS. NOTE: the [fixed] pg-groups2 case (a JSON-type fix) also emits this invalid GROUPS clause to T-SQL/MySQL — same class.
SELECT x, SUM(x) OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) AS s FROM (VALUES (1),(2),(2),(3)) v(x)

-- CASE[open][class=invalid]: pg-multifield-interval-arith — a multi-field INTERVAL literal ('1 year 2 months 3 days') in date arithmetic is emitted VERBATIM to T-SQL/MySQL/Oracle, none of which accept PG's multi-field text interval, with NO warning. Single-unit intervals ('1 month') DO convert (DATEADD / INTERVAL 1 MONTH). The [fixed] pg-interval-out case only passes because its justify_interval() trips the output_gate and degrades the whole batch; a multi-field interval WITHOUT an unmapped builtin slips through invalid. (Bare `SELECT INTERVAL '1 year 2 months 3 days'` also fails identically.) PG=2021-03-04.
SELECT TIMESTAMP '2020-01-01 00:00:00' + INTERVAL '1 year 2 months 3 days' AS d

-- CASE[open][class=consistency]: pg-temp-oncommit-oracle — a PG TEMP table defaults to ON COMMIT PRESERVE ROWS (session-scoped); it maps to Oracle CREATE GLOBAL TEMPORARY TABLE with NO ON COMMIT clause, which defaults to ON COMMIT DELETE ROWS (transaction-scoped). With per-statement commits the rows vanish before the later SELECT: PG COUNT=2, Oracle COUNT=0. Silent cross-statement divergence, no warning.
CREATE TEMP TABLE redb_tmp (id INT);
INSERT INTO redb_tmp VALUES (1),(2);
SELECT COUNT(*) AS c FROM redb_tmp;

-- CASE[open][class=composition]: pg-boolagg-filter — bool_or/bool_and (boolean aggregate) alone wraps its boolean argument into 1/0 for T-SQL (MAX(CAST(CASE WHEN a>5 THEN 1 WHEN NOT (a>5) THEN 0 END AS INT))); FILTER alone rewrites to COUNT(CASE WHEN cond THEN ...). COMBINED, the FILTER rewrite emits MAX(CAST(CASE WHEN b=1 THEN a>5 END AS INT)) — the raw boolean a>5 as a CASE THEN-value, which T-SQL rejects (error 102, no boolean value type). The 1/0 wrapping bool_or does alone is lost. No warning. Components green alone: bool_or (live-valid on T-SQL) and FILTER (corpus pg-filter-subquery, line ~266).
SELECT bool_or(a > 5) FILTER (WHERE b = 1) AS r FROM (VALUES (10,1),(2,1),(3,2)) v(a,b)

-- CASE[open][class=invalid]: pg-round-bare-half-literal — ROUND on a BARE fractional literal (0.5, no ::numeric cast) becomes T-SQL ROUND(0.5, 0). T-SQL types the literal 0.5 as numeric(1,1) (range ±0.9), and ROUND preserves that precision/scale, so the rounded 1.0 OVERFLOWS (error 8115). PG ROUND(0.5)=1 (arbitrary precision). No warning. The existing round cases all use ::numeric casts that widen the type and dodge this; a bare literal does not.
SELECT ROUND(0.5) AS r

-- CASE[open][class=func]: pg-substring-neg-from-for — 3-arg SUBSTRING(s FROM start FOR len) with a NEGATIVE start: PG counts len from the (out-of-range) negative position and keeps only positions >= 1, so SUBSTRING('abcde' FROM -2 FOR 2) = '' (the [ -2, -1 ] range is entirely before position 1). It is emitted VERBATIM as SUBSTRING/SUBSTR('abcde', -2, 2); MySQL/Oracle read a negative start as counting from the END → 'de'. The pg-fsubstr / pg-substr-edge fixes only handle the 2-arg (no length) negative-start form. PG=''; MySQL/Oracle='de'. No warning. (T-SQL matches PG.)
SELECT SUBSTRING('abcde' FROM -2 FOR 2) AS s

-- CASE[fixed][class=lying-warning]: pg-insert-default-values-falsewarn — INSERT ... DEFAULT VALUES is correctly translated to MySQL `INSERT INTO t () VALUES ()` (live-equivalent: both insert one all-defaults row), yet it emits the tripwire warning "internal: unread sqlglot arg 'default' on Insert — construct may be dropped". Nothing was dropped. The converter consumes Insert.args['default'] to emit () VALUES () but never marks it read, so the unread-args tripwire false-fires. (Distinct from the Window.over false-warning: a different node/arg.)
CREATE TABLE redb_dv (id INT DEFAULT 7, v INT DEFAULT 3); INSERT INTO redb_dv DEFAULT VALUES

-- CASE[open][class=func]: pg-repeat-negative — repeat(s, n) with n<=0 returns '' in PostgreSQL (and MySQL REPEAT), but the T-SQL (REPLICATE) and Oracle (RPAD(s, len*n, s)) emulations return NULL for a negative count. PG/MySQL=''; T-SQL/Oracle=NULL. No warning. (The pg-pad-repeat / pg-repeat-left-right cases only use positive counts.)
SELECT repeat('ab', -1) AS r

-- CASE[open][class=invalid]: pg-row-value-comparison — a row-value inequality comparison (a, b) > (1, 5) (lexicographic; used for keyset pagination) is emitted VERBATIM to T-SQL, which has no row-value comparison and rejects it (error 4145 'non-boolean type ... where a condition is expected'). No warning. PG=(3,4). Oracle and MySQL both accept row inequality, so only T-SQL is invalid.
SELECT a, b FROM (VALUES (1,2),(3,4)) v(a,b) WHERE (a, b) > (1, 5)

-- CASE[open][class=invalid]: pg-bool-to-int-cast — the idiomatic PG cast of a boolean predicate to int, (a > 1)::int, is emitted verbatim as CAST(a > 1 AS INT) on T-SQL and Oracle, which have no boolean value type and reject a predicate as a CAST operand (T-SQL error 156; Oracle ORA-02000). No warning. PG=(1). Shares the root cause with pg-boolagg-filter (boolean value not wrapped to 1/0) but via a direct cast, not an aggregate.
SELECT (a > 1)::int AS r FROM (VALUES (2)) v(a)

-- CASE[open][class=invalid]: pg-group-by-ordinal — positional GROUP BY (GROUP BY 1, meaning the first select item) is emitted verbatim to T-SQL and Oracle, neither of which supports positional GROUP BY: T-SQL rejects the integer (error 164 'GROUP BY expression must contain at least one column that is not an outer reference') and Oracle raises ORA-03162 (group_by_position_enabled is FALSE). No warning. PG/MySQL support it. PG=[(1,2),(2,1)].
SELECT a, COUNT(*) AS c FROM (VALUES (1),(1),(2)) v(a) GROUP BY 1

-- CASE[open][class=silent-drop]: pg-groupby-multi-cube-rollup — a GROUP BY with MULTIPLE grouping elements (CUBE(a, b), ROLLUP(c)) silently keeps only the LAST element (ROLLUP(c)) and DROPS CUBE(a, b), even though T-SQL and Oracle support the multi-element form natively (live: T-SQL GROUP BY CUBE(a,b),ROLLUP(c) returns the same 18 rows as PG). The output GROUP BY ROLLUP(c) then leaves a and b ungrouped, so SELECT a, b is invalid (T-SQL error 8120). No warning. Both a wrong result (missing grouping sets) and invalid output.
SELECT a, b, c, SUM(x) AS s FROM (VALUES (1,1,1,10),(1,2,1,20),(2,1,2,30)) v(a,b,c,x) GROUP BY CUBE(a, b), ROLLUP(c)

-- CASE[open][class=silent-drop]: pg-serial-identity-oracle — a SERIAL column maps correctly to T-SQL IDENTITY and MySQL AUTO_INCREMENT, but into Oracle it becomes a plain `id NUMBER PRIMARY KEY` — the auto-generation is silently DROPPED (Oracle supports GENERATED BY DEFAULT AS IDENTITY since 12c). The later INSERTs omit id, so on Oracle they fail with ORA-01400 (cannot insert NULL into id). No warning. PG auto-assigns 1,2.
CREATE TABLE redb_ser (id SERIAL PRIMARY KEY, v INT);
INSERT INTO redb_ser (v) VALUES (10);
INSERT INTO redb_ser (v) VALUES (20);
SELECT id, v FROM redb_ser ORDER BY id;

-- CASE[fixed][class=func]: pg-date-trunc-week — date_trunc('week', d) starts the week on MONDAY in PostgreSQL (ISO). T-SQL DATETRUNC(week, d) starts on SUNDAY, so it returns a DIFFERENT date (PG 2020-06-15 vs T-SQL 2020-06-14) with no warning. Oracle is worse: it emits TRUNC(d, 'WEEK'), but 'WEEK' is not a valid Oracle format model (ORA-01898) — the Monday-based form is TRUNC(d, 'IW') (which returns 2020-06-15, matching PG). Both defects silent.
SELECT date_trunc('week', DATE '2020-06-17') AS d

-- CASE[fixed][class=func]: pg-date-minus-integer — date + integer correctly maps to DATEADD/DATE_ADD, but date - integer is emitted VERBATIM (CAST(... AS DATE) - 7): MySQL coerces the date to the number 20200301 and subtracts, returning garbage 20200294 (not 2020-02-23); T-SQL rejects it (error 206, 'date is incompatible with int'). No warning. PG=2020-02-23. Asymmetric: the '+' path is handled, the '-' path is not.
SELECT DATE '2020-03-01' - 7 AS d
