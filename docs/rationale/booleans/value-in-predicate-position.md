[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Predicate position: the reverse direction" direction="postgresql/mysql → tsql/oracle" kind=article order=4 -->

# A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle

**Problem.** MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a
condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN`
return type demands an actual boolean expression, not a `NUMBER`. Shipped
raw, the target either silently accepts a nonsensical condition or rejects
the type mismatch outright.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW1Batch::test_bare_numeric_where_gets_comparison (mysql -> tsql)
UPDATE v1 SET b = 0 WHERE 0;
-- transpiles to:
UPDATE v1
SET b = 0
WHERE 0 <> 0
```

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW7Batch::test_numeric_return_wrapped_for_bool_type_oracle (postgresql -> oracle)
create function bk() returns bool as
  $$ begin return 1; end $$ language plpgsql;
-- transpiles to:
CREATE OR REPLACE FUNCTION bk
RETURN bool
AS
BEGIN
    RETURN (1 <> 0);
END;
/
```

**Discussion.** `<> 0` is the mirror image of the value-position wrap: a
bare numeric literal is only ever `TRUE` (non-zero) or `FALSE` (zero) — it
is never `UNKNOWN` unless it is itself `NULL` — so a plain comparison
(rather than a `CASE`) is enough to synthesize a genuine predicate/boolean
from it. `RETURN bool` (the lowercase spelling carried over from the
PostgreSQL source, rather than `RETURN BOOLEAN`) live-compiles on Oracle
unchanged — no rewrite to the `BOOLEAN` type name is needed for the
declaration itself.

> **Note** faithful — `0`/non-`0` truthiness and `<> 0`/`= 0` comparisons
> agree on every value including `NULL` (both stay `NULL`/`UNKNOWN`).

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushW1Batch::test_bare_numeric_where_gets_comparison`,
`::TestZeroPushW7Batch::test_numeric_return_wrapped_for_bool_type_oracle`.
