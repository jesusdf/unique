[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Value position: booleans wrapped for engines with no boolean value" direction="postgresql/mysql → tsql/oracle" kind=article order=2 -->

# `NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle

**Problem.** The same duality inside procedural bodies: `SET done = NOT
done` (MySQL) or `RETURN <predicate>` from a function declared to return a
boolean assigns/returns a value, not a predicate. A `NUMBER`/`INT`-typed
variable or a T-SQL function mapped to `RETURNS BIT` has no `NOT`-of-a-value
operator to reuse.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_not_value_wraps_tristate_on_oracle (mysql -> oracle)
DELIMITER //
create procedure p2() begin
  declare done int default 0;
  set done = not done;
end//
DELIMITER ;
-- transpiles to:
CREATE PROCEDURE p2
IS
    done NUMBER(10) := 0;
BEGIN
    done := CASE WHEN done = 0 THEN 1 WHEN done <> 0 THEN 0 END;
END;
/
```

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushZ4bBatch::test_predicate_return_wraps_for_bit (postgresql -> tsql)
create function dc(val int) returns boolean language plpgsql as
  $$ begin return val > 0; end $$;
-- transpiles to:
CREATE FUNCTION dc
(
    @val int
)
RETURNS BIT
AS
BEGIN
    RETURN CASE WHEN @val > 0 THEN 1 WHEN NOT (@val > 0) THEN 0 END;
END
```

**Discussion.** Same tri-state `CASE`, same reason (`done`/`val`'s
comparison could legitimately be `NULL`-valued for a different input), just
applied at an assignment or `RETURN` slot instead of a SELECT-list
projection. `NOT` itself is never emitted as a value-position operator on
these targets (`src/unique/core/procedural/transformer/base.py`: *"tri-state
CASE preserves NULL"*; `src/unique/core/converter/emit_expr.py`: *"NOT is
not a value expression on T-SQL — wrap tri-state"*).

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle`,
`::TestZeroPushZ4bBatch`.
