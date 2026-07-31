[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Local variable renamed to avoid an Oracle built-in collision" direction="postgresql → oracle" kind=article order=49 -->

# A local variable named after an Oracle built-in (`count`) → renamed everywhere it's used

**Problem.** `count` is a perfectly legal PL/pgSQL local variable name —
PostgreSQL has no keyword collision. On Oracle, `COUNT` is a built-in
aggregate function name, and PL/SQL rejects a local variable declared with
that name (or resolves it ambiguously against the built-in, silently
breaking any call to the real `COUNT(*)` inside the same routine).

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW4Batch::test_oracle_unsafe_local_count_renamed
create function cl(p1 numeric) returns numeric as $$
  declare count numeric(10);
  begin
    select count(*) into count from t1;
    return count;
  end$$ language plpgsql;
-- postgresql -> oracle:
CREATE OR REPLACE FUNCTION cl
(
    p1 IN NUMBER
)
RETURN NUMBER
IS
    uq_count numeric(10);
BEGIN
    SELECT COUNT(*) INTO uq_count from t1;
    RETURN uq_count;
END;
/
```

**Discussion.** Unique checks every declared local variable name against
Oracle's reserved built-in names before emitting Oracle output; a collision
renames the *variable* (not the built-in call) to a synthesized
`uq_<name>`, and rewrites every reference to the variable — the
declaration, every assignment, every read — consistently through the
routine body. The genuine `COUNT(*)` call inside the same statement is left
untouched, since it is a call to the aggregate, not a reference to the
now-renamed variable; recognizing which occurrence is which (a bare
`count` token that is a variable reference vs. one that is a function call
followed by `(`) is what keeps the rewrite from either renaming the
built-in call by mistake or leaving the variable's own name colliding.

> **Note** faithful — the variable holds the same value under its new
> name; only the identifier text changes, and only on Oracle, where the
> collision would otherwise be a compile error or a semantic corruption.
> No warning: the rename is silent because it produces valid Oracle code
> with no shift in meaning, unlike a warned rename that would signal an
> unavoidable loss.

**See Also.** [`test_ir_first_families.py::TestZeroPushW4Batch`](../../../tests/unit/core/test_ir_first_families.py)
(`test_oracle_unsafe_local_count_renamed`).
