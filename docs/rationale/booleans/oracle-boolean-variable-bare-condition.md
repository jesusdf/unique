[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Predicate position: the reverse direction" direction="oracle → tsql" kind=article order=9 -->

# A bare Oracle PL/SQL `BOOLEAN` variable used as a condition → `= 1` on T-SQL

**Problem.** Oracle's PL/SQL `BOOLEAN` variables are used directly as
conditions — `IF NOT bexc THEN`, `WHILE bexc LOOP` — since PL/SQL has a
real boolean type. T-SQL has no boolean value type at all; a `BOOLEAN`
variable maps to `BIT`, a 0/1-valued numeric, and T-SQL's `IF`/`WHILE`
require a genuine predicate, not a bare numeric — `IF @bexc` alone is a
syntax error (live error 4145, "An expression of non-boolean type
specified in a context where a condition is expected").

**Solution.**

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestBooleanVarCondition
CREATE OR REPLACE PROCEDURE p_b(m_out OUT NUMBER) AS
  bexc BOOLEAN;
BEGIN
  bexc := TRUE;
  IF NOT bexc THEN
    m_out := 0;
  END IF;
  WHILE bexc LOOP
    m_out := 1;
  END LOOP;
END;
/
-- oracle -> tsql:
DECLARE @bexc BIT;
SET @bexc = 1;
IF NOT @bexc = 1
BEGIN
    SET @m_out = 0;
END
WHILE @bexc = 1
BEGIN
    SET @m_out = 1;
END
```

**Discussion.** A bare `BOOLEAN`-typed variable read directly in a
condition slot is a narrower case of the value/predicate duality this
project's booleans pages document generally: rather than wrapping the
comparison in a full tri-state `CASE`, a condition that is *only* a bare
`[NOT] variable` reference synthesizes the minimal `= 1` comparison needed
to make it a genuine T-SQL predicate — `NOT` itself binds to the
comparison (`NOT @bexc = 1`), matching Oracle's own `NOT bexc` reading of
"the stored value is not true." This is the mirror of [a numeric/bit value
where a genuine predicate is required](value-in-predicate-position.md),
specialized to Oracle's native `BOOLEAN` type as the source rather than a
numeric column.

> **Note** faithful — `@bexc = 1` is true exactly when `bexc` was `TRUE`,
> false when `FALSE`, and unresolved (neither branch) when `NULL`, matching
> PL/SQL's own three-valued `BOOLEAN` semantics in a condition. No warning.

**See Also.** [`test_oracle_source_m4_wave.py::TestBooleanVarCondition`](../../../tests/integration/test_oracle_source_m4_wave.py)
(`test_bare_boolean_conditions_compare_to_1`) · [A numeric/bit value where a
genuine predicate or boolean is required](value-in-predicate-position.md)
(the general mechanism this specializes).
