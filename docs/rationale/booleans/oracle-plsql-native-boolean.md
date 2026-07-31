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
    b boolean := 1;
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
PL/SQL grammar (unlike the SQL grammar) allows it.

> **Discrepancy noticed while probing (not part of this mechanism):** the
> same output's `b boolean := 1;` initializer — the source's `TRUE` literal
> folded to the integer `1` even though the declared type is `BOOLEAN` — is
> **invalid live Oracle** (`PLS-00382: expression is of wrong type`,
> confirmed against `oracle://system:***@localhost:1521/FREEPDB1`). This is
> a distinct literal-typing bug in the `TRUE`/`FALSE` constant-folding path,
> unrelated to the value/predicate duality this page documents — reported
> here rather than silently presented as working, not fixed (docs-only
> brief).

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_pg_boolean_not_stays_on_oracle`.
