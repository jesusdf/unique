[← DML: SELECT/INSERT/UPDATE/DELETE, joins, set operations, MERGE](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Conditional expression translation" direction="tsql/mysql → oracle/postgresql" kind=article order=26 -->

# T-SQL `IIF(cond, a, b)` / MySQL `IF(cond, a, b)` → Oracle/PostgreSQL searched `CASE`

**Problem.** T-SQL's `IIF(cond, a, b)` and MySQL's `IF(cond, a, b)` are
both a three-argument ternary conditional expression — neither function
exists on Oracle or PostgreSQL, so carrying either name across verbatim
would be an unresolved-function error there.

**Solution.**

```sql
-- tests/integration/test_function_translation.py::TestConditionalFunction
SELECT IIF(a > 0, 'y', 'n') FROM t
-- tsql -> oracle / postgresql:
SELECT CASE WHEN a > 0 THEN 'y' ELSE 'n' END FROM t;

-- mysql -> postgresql (same rewrite for MySQL's IF()):
SELECT IF(a > 0, 'y', 'n') FROM t
-- =>
SELECT CASE WHEN a > 0 THEN 'y' ELSE 'n' END FROM t;
```

T-SQL keeps its own `IIF(...)` unchanged when the target *is* T-SQL, and
MySQL keeps its own `IF(...)` unchanged when the target *is* MySQL — the
rewrite only fires for the two engines with no ternary-conditional
function of their own.

**Discussion.** `IIF(cond, a, b)` and `IF(cond, a, b)` are both exactly
equivalent to a single-branch searched `CASE WHEN cond THEN a ELSE b END`
— evaluate the condition once, return `a` if true and `b` otherwise — so
the rewrite is a direct, unconditional syntactic expansion with nothing
target-specific to decide. This closed a real leak found on production
view definitions: `IF(cu.active, ...)` inside a MySQL view shipped
verbatim into T-SQL/PostgreSQL/Oracle output, where no such function
exists and the statement would fail outright.

> **Note** faithful — the searched `CASE` evaluates the same condition and
> returns the same one of the two values on every target. No warning.

**See Also.** [`test_function_translation.py::TestConditionalFunction`](../../../tests/integration/test_function_translation.py)
· [§3.12](../../03-unsupported.md), "IIF and DATEPART" ·
[`EXTRACT(field FROM x)` ↔ T-SQL `DATEPART(field, x)`](../datetime/extract-datepart-standard-fields.md)
(the sibling entry bundled under the same heading in 03-unsupported.md,
for the other half of that section).
