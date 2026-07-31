[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Loop and cursor desugaring" direction="oracle → tsql/mysql" kind=article order=31 -->

# Numeric range `FOR i IN a..b LOOP` (Oracle) → MySQL / T-SQL explicit `WHILE` + counter

**Problem.** `FOR i IN 1..13 LOOP` (optionally `REVERSE`) is Oracle's
counting loop — no cursor at all, just an integer range. `1..13` is not a
query, so it cannot be spelled as a cursor declaration on any target.
MySQL/T-SQL have no native counting-`FOR` construct, so it has to become an
explicit `WHILE` loop with its own counter.

**Solution.**

```sql
-- tests/integration/test_oracle_mysql_tail.py::TestNumericRangeForLoop
create or replace PROCEDURE p_rng AS BEGIN
  FOR i IN 1..13 LOOP
    INSERT INTO t (a) VALUES (i);
  END LOOP;
END;
/
-- oracle -> mysql:
DELIMITER $$
CREATE PROCEDURE p_rng()
BEGIN
    BEGIN
        DECLARE i INT DEFAULT 1;
        WHILE i <= 13 DO
            INSERT INTO t (a) VALUES (i);
            SET i = i + 1;
        END WHILE;
    END;
END$$
DELIMITER ;
-- oracle -> tsql:
DECLARE @i INT = 1;
WHILE @i <= 13
BEGIN
        INSERT INTO t (a) VALUES (@i);
    SET @i = @i + 1;
END;
```

`FOR i IN REVERSE 1..13 LOOP` counts down instead: MySQL/T-SQL get
`DECLARE i INT DEFAULT 13;` / `WHILE i >= 1` / `SET i = i - 1`
(`test_reverse_range_mysql_counts_down`). PostgreSQL and Oracle itself keep
the native `FOR i IN 1..13 LOOP` form unchanged
(`test_postgresql_keeps_native_range_loop`,
`test_oracle_identity_keeps_range_loop`), since both support the construct
directly.

**Discussion.** PostgreSQL and Oracle both have a native integer-range `FOR`
loop; MySQL and T-SQL do not, so counting has to be made explicit — a
`DECLARE`d counter, a `WHILE` bound test, and an explicit increment/decrement
after the body, mirroring exactly what the implicit range loop does
internally.

> **Note** faithful — same iteration count and bound values on every
> target; no warning, since a `WHILE` + counter reproduces the range loop
> exactly (no per-column typing uncertainty is involved here, unlike the
> cursor loops above).

**See Also.** [`TestNumericRangeForLoop`](../../../tests/integration/test_oracle_mysql_tail.py) —
no dedicated challenge-corpus case exercises the numeric range loop, so the
example above is drawn from that dedicated integration test.
