[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Mid-block DECLARE hoisted to the routine's top declaration section" direction="tsql → postgresql/mysql/oracle" kind=article order=45 -->

# A `DECLARE` written mid-block (inside an `IF`/`CATCH`) → hoisted to the routine's top declaration section

**Problem.** T-SQL allows `DECLARE @v type = init;` anywhere a statement is
legal — inside an `IF` body, inside a `CATCH` block, nested arbitrarily
deep. PostgreSQL, MySQL, and PL/SQL all require every local variable to be
declared once, at the top of its enclosing block, before any executable
statement — a mid-block `DECLARE` is a parse error on all three.

**Solution.** The declaration hoists bare to the routine's top; the
initializer stays behind as a conditional assignment exactly where the
`DECLARE` used to be:

```sql
-- tests/integration/test_trigger_predicates_scheduler.py::test_nested_declare_hoists_with_conditional_assignment
CREATE FUNCTION dbo.f2(@s NVARCHAR(100)) RETURNS INT AS BEGIN
  IF @s = N'x'
  BEGIN
    DECLARE @e INT = LEN(@s)
    RETURN @e
  END
  RETURN 0
END
-- tsql -> postgresql:
DECLARE
    v_e INT;
BEGIN
    IF v_s = 'x' THEN
        v_e := LENGTH(v_s);
        RETURN v_e;
    END IF;
    RETURN 0;
END;

-- tsql -> mysql:
DECLARE v_e INT;
IF v_s = 'x' THEN
    SET v_e = LENGTH(v_s);
    RETURN v_e;
END IF;
RETURN 0;
```

The same hoist applies to a `CATCH`-block-local `DECLARE` on the way to
Oracle — the declaration lands in the `DECLARE` section that opens the
routine, ahead of `BEGIN`, never inline inside the exception handler
(invalid PL/SQL there):

```sql
-- tests/integration/test_procedural.py::TestTopLevelTryCatch::test_catch_local_declare_is_hoisted_on_oracle
-- oracle output shape:
DECLARE
    v_msg NVARCHAR2(4000);
BEGIN
    ...
EXCEPTION WHEN OTHERS THEN
    v_msg := ...;
END;
```

**Discussion.** T-SQL's block-scoping is a documented but easy-to-miss
looseness in its `DECLARE` grammar — the statement is legal wherever any
other statement is, and its scope is effectively "from here to the end of
the batch," not "from here to the end of this `BEGIN`/`END`." Reproducing
the same visibility on an engine that enforces top-of-block declarations
means splitting the `DECLARE` into two independent pieces: the *name and
type* move to the block's top (unconditionally declared, since the target
grammar requires it), while the *initializer expression* stays exactly
where the original `DECLARE` was written, now spelled as a plain
assignment — so a variable that would never have been initialized on a
path that skips the `IF`/`CATCH` body still isn't initialized on the
target either.

> **Note** faithful — the variable's value at every point in the body is
> identical to the source; only its declaration's *textual position*
> changes, which has no observable effect since none of these three target
> engines allow the name to be referenced before the hoisted point anyway.
> No warning.

**See Also.** [`test_trigger_predicates_scheduler.py`](../../../tests/integration/test_trigger_predicates_scheduler.py)
(`test_nested_declare_hoists_with_conditional_assignment`) ·
[`test_procedural.py::TestTopLevelTryCatch`](../../../tests/integration/test_procedural.py)
(`test_catch_local_declare_is_hoisted_on_oracle`).
