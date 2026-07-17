-- Challenge fixtures — MySQL source.
-- Anonymized tricky constructs; one per entry. See README.md.
-- (No entries yet — add the smallest self-contained reproduction of each
--  problematic construct as it is found.)

-- ===== RED-found open findings (validated live; see FINDINGS.md) =====

-- CASE[open]: my-alter-modify — fails on oracle, postgresql, tsql. (102, b"Incorrect syntax near 'MODIFY'.DB-Lib error message 20018, severity 15:\nGeneral S
CREATE TABLE t (a INT, b INT); ALTER TABLE t MODIFY COLUMN b BIGINT

-- CASE[open]: my-cast-convert — fails on oracle, postgresql, tsql. (243, b'Type UBIGINT is not a defined system type.DB-Lib error message 20018, severity 16:
SELECT CAST(123 AS CHAR), CONVERT('2020-01-01', DATE), CAST(1 AS UNSIGNED)

-- CASE[open]: my-concat-ws — fails on oracle. ORA-00904: "CONCAT_WS": invalid identifier
SELECT CONCAT_WS('-', 'a', 'b', NULL, 'c') AS r

-- CASE[open]: my-date-add-interval — fails on oracle, postgresql. ORA-30081: invalid data type for datetime/interval arithmetic
SELECT DATE_ADD('2020-01-01', INTERVAL 7 DAY) AS r

-- CASE[open]: my-date-format — fails on oracle, postgresql, tsql. (8116, b'Argument data type varchar is invalid for argument 1 of format function.DB-Lib er
SELECT DATE_FORMAT('2020-05-17', '%Y/%m/%d') AS r

-- CASE[open]: my-datetime-precision — fails on tsql. (2716, b'Column, parameter, or variable #1: Cannot specify a column width on data type dat
CREATE TABLE t (a DATETIME(6), b TIMESTAMP(3), c YEAR)

-- CASE[open]: my-group-concat — fails on postgresql. function string_agg(integer, unknown) does not exist
SELECT GROUP_CONCAT(x ORDER BY x SEPARATOR '|') AS r FROM (SELECT 1 x UNION SELECT 2) t

-- CASE[open]: my-hex-bin — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.HE
SELECT HEX(255) AS r, BIN(5) AS b

-- CASE[open]: my-json-object — fails on oracle, postgresql, tsql. (4121, b'Cannot find either column "dbo" or the user-defined function or aggregate "dbo.J_
SELECT JSON_OBJECT('a', 1, 'b', 2)

-- CASE[open]: my-json-type — fails on oracle, tsql. (2715, b'Column, parameter, or variable #1: Cannot find data type json.DB-Lib error messag
CREATE TABLE t (data JSON)

-- CASE[open]: my-numeric — fails on tsql. (2724, b"Parameter or variable 'b' has an invalid data type.DB-Lib error message 20018, se
CREATE TABLE t (a DECIMAL(20,4), b FLOAT(10,2), c DOUBLE)

-- CASE[open]: my-timestampdiff — fails on oracle. ORA-01861: literal does not match format string
SELECT TIMESTAMPDIFF(DAY, '2020-01-01', '2020-01-10') AS r
