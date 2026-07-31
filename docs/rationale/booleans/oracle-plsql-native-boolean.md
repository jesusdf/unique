[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Value position: booleans wrapped for engines with no boolean value" direction="oracle" kind=article order=3 direction-inferred=true -->

# Oracle PL/SQL `BOOLEAN` variables and parameters keep native `NOT` (handled)

**Problem.** Oracle's exception to its own "SQL has no boolean value" rule:
a PL/SQL variable or parameter declared `BOOLEAN` **is** a first-class value
inside procedural code — just not inside a SQL statement issued from that
same block. A `NOT` of a `BOOLEAN`-typed operand should not get the
tri-state wrap the previous entry uses for `NUMBER`/`INT` operands; that
would be a needless (and needlessly verbose) rewrite of something Oracle
already accepts natively.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_pg_boolean_not_stays_on_oracle (postgresql -> oracle)
create function f() returns boolean language plpgsql as $$
declare b boolean := true;
begin
  b := not b;
  return b;
end $$;
-- transpiles to:
CREATE OR REPLACE FUNCTION f
RETURN boolean
IS
    b boolean := TRUE;
BEGIN
    b := NOT b;
    RETURN b;
END;
/
```

**Discussion.** `b := NOT b;` stays exactly as written — no `CASE`, because
`b`'s declared type is `BOOLEAN`, and the whole mechanism is keyed off the
*operand's type*, not off "which engine": it is not "`NOT` is banned on
Oracle", it is "`NOT` of a `NUMBER`-typed value is not a value expression in
Oracle SQL", and a PL/SQL `BOOLEAN` variable sidesteps that because the
PL/SQL grammar (unlike the SQL grammar) allows it. The same rule applies to
the initializer: a `TRUE`/`FALSE` literal assigned to a declared `BOOLEAN`
variable is kept as the native `TRUE`/`FALSE` keyword, not folded to an
integer, since Oracle's PL/SQL `BOOLEAN` type only accepts its own literal
there.

> **Note** faithful — live-verified: the transpiled function compiles and
> runs on Oracle with no error.

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_pg_boolean_not_stays_on_oracle`.
