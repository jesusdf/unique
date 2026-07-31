[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Numeric division, cast rounding, and zero-divisor semantics" direction="cross-engine" kind=article order=12 direction-inferred=true -->

# Integer-truncating vs. decimal division (cross-engine)

**Problem.** `/` truncates two integer operands to an integer on
PostgreSQL and T-SQL (`5 / 2` is `2`), but MySQL and Oracle always return a
decimal (`5 / 2` is `2.5`) — crossing that line without compensation
silently changes the value. `AVG` is division in disguise for the same
purpose: T-SQL's `AVG` returns the argument's own type, so `AVG` over an
integer column truncates *before* dividing (`AVG(1,2)` = `1`, not `1.5`)
while MySQL/Oracle/PostgreSQL always average as decimal.

**Solution.**

```sql
-- literal operands
SELECT 5 / 2 AS r
-- postgresql -> mysql:  SELECT (5 DIV 2) AS r;
-- postgresql -> oracle: SELECT TRUNC(5 / 2) AS r FROM DUAL;
-- mysql -> postgresql:  SELECT (5 * 1.0 / NULLIF(2, 0)) AS r;
-- oracle -> tsql:       SELECT (5 * 1.0 / 2) AS r

-- declared integer variables (test_func_compensation.py::test_integer_division_declared_variables_procedural)
CREATE PROCEDURE p AS BEGIN DECLARE @a INT; DECLARE @b INT; DECLARE @r INT; SET @r = @a / @b; END
-- tsql -> oracle: V_R := TRUNC(V_A / V_B);
-- tsql -> mysql:  SET v_r = (v_a DIV v_b);

-- corpus case my-avg-int / pg-avg-int
SELECT AVG(x) FROM (SELECT 1 x UNION SELECT 2) t
-- mysql/postgresql -> tsql: SELECT AVG((x) * 1.0) FROM (...) t
```

Going from an integer-truncating source to a decimal-only engine
compensates by truncating the *target* too (`DIV` on MySQL, `TRUNC(...)` on
Oracle); going the other way forces the dividend decimal (`* 1.0`) so the
target's own truncation never fires. The same `* 1.0` promotion is applied
to an `AVG` argument whenever the source always averages as decimal and the
target is T-SQL. MySQL's `/` also never raises on a zero divisor (`x / 0` is
`NULL`, not an error); that NULL-safety is preserved on every other target
by wrapping the divisor in `NULLIF(divisor, 0)`, independent of whether the
division is an aggregate's own divisor or an ordinary expression — the two
compensations combine additively when both apply:

```sql
-- corpus case my-sum-div-count
SELECT SUM(x)/COUNT(x) FROM (SELECT 1 x UNION ALL SELECT 2) t
-- mysql -> postgresql/tsql: SUM(x) * 1.0 / NULLIF(COUNT(x), 0)

-- test_challenge.py::TestMysqlSafeDivision
SELECT a / b FROM t
-- mysql -> oracle: SELECT a / NULLIF(b, 0) FROM t;              -- Oracle already divides as decimal, only the guard is needed
-- mysql -> tsql:   SELECT (a * 1.0 / NULLIF(b, 0)) FROM t       -- T-SQL truncates too, so both compensations apply
```

**Discussion.** Three independent per-engine behaviors compose here:
whether `/` truncates or floats (PostgreSQL and T-SQL truncate; MySQL and
Oracle always float), whether `AVG` inherits its argument's type (T-SQL
only) or always averages as decimal (the other three), and whether division
by zero raises (PostgreSQL/T-SQL/Oracle) or returns `NULL` (MySQL only).
Each is read off the source dialect and compensated independently per
target; for a literal-operand division no schema is needed, and inside a
procedure body the same compensation applies to a declared integer
*variable* once its type is known from the `DECLARE`.

> **Note** faithful — `my-sum-div-count` live-verified `1.5`;
> `test_func_compensation.py`'s literal and declared-variable division tests
> pin the exact value on both sides of the truncating/decimal split;
> `TestMysqlSafeDivision` pins the NULL-safety preservation; `my-avg-int` /
> `pg-avg-int` / `my-avg-precision2` pin the `AVG` promotion.

**See Also.** [`my-sum-div-count`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-avg-int`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-avg-precision2`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`pg-avg-int`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`tests/integration/test_func_compensation.py` (`test_integer_division_literals_preserved`, `test_integer_division_declared_variables_procedural`) ·
`tests/integration/test_challenge.py` (`TestMysqlDecimalDivision`, `TestMysqlSafeDivision`, `TestTsqlAvgIntegerPromotion`).
