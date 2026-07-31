[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Return-type and signature synthesis" direction="postgresql/oracle → tsql" kind=article order=38 -->

# T-SQL scalar function: synthesized trailing `RETURN NULL` after an all-branches-return `IF`/`ELSE`

**Problem.** T-SQL requires a scalar function's **last statement** to
literally *be* a `RETURN` (error 455 otherwise) — even when the function's
body already returns a value on every possible branch, such as an `IF ...
ELSE` where both arms end in `RETURN`. A source function written in
PostgreSQL or Oracle, where the compiler can see that every branch returns
and doesn't require anything after the `IF`/`ELSE`, has nothing at its
syntactic end that satisfies T-SQL's purely textual rule.

**Solution.**

```sql
-- ora-recursive-func, oracle → tsql
CREATE FUNCTION f(n NUMBER) RETURN NUMBER AS
BEGIN
  IF n <= 1 THEN RETURN 1; ELSE RETURN n * f(n-1); END IF;
END;

-- =>
CREATE FUNCTION f (@n DECIMAL(38, 10))
RETURNS DECIMAL(38, 10)
AS
BEGIN
    IF @n <= 1
    BEGIN
            RETURN 1;
    END
    ELSE
    BEGIN
            RETURN @n * dbo.f(@n - 1);
    END
    RETURN NULL;
END
```

An unreachable `RETURN NULL;` is appended right after the `IF`/`ELSE`
block, satisfying T-SQL's syntactic requirement without ever actually
running (every real call path returns from inside the `IF` or the `ELSE`
first). The same synthesis applies to a PostgreSQL `CASE` statement whose
every branch `RETURN`s. Live-verified: `f(1)` = `'one'` for the `CASE`
example, and the recursive factorial `f(5)` = `120` for the example above —
the synthesized `RETURN NULL` never executes in either case.

**Discussion.** PostgreSQL and Oracle both perform (or simply don't
require) branch-completeness analysis on a function body — PL/pgSQL and
PL/SQL are happy to end a function at the close of an `IF`/`ELSE` whose
every arm already returns. T-SQL's rule is purely structural: whatever
statement is textually last must be a `RETURN`, regardless of whether the
control flow could ever reach it. Rather than restructure the function
(which would risk changing its logic) or reject it as unsupported, an
unreachable trailing `RETURN NULL` satisfies the syntax exactly where
T-SQL checks it, without altering what the function actually computes on
any input.

> **Note** faithful — live-verified: the recursive `f(5)` still evaluates
> to `120` (5!) and the `CASE`-based `f(1)` still evaluates to `'one'` on
> T-SQL; the synthesized trailing `RETURN NULL` is provably unreachable in
> both cases.

**See Also.** Corpus [`pg-case-statement`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`ora-recursive-func`](../../../tests/fixtures/challenge/challenge_oracle.sql) ·
[`TestTsqlScalarFunctionTrailingReturn`](../../../tests/integration/test_challenge.py) ·
[Return-type and signature synthesis](return-type-synthesis-overview.md), the
topic overview for this family.
