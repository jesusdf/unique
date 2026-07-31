[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="SQLSTATE/SQLCODE read into T-SQL error functions" direction="postgresql/oracle → tsql" kind=article order=54 -->

# PostgreSQL `SQLSTATE` / Oracle `SQLCODE` → `CAST(ERROR_STATE()/ERROR_NUMBER() AS NVARCHAR(n))`

**Problem.** PostgreSQL's `SQLSTATE` and Oracle's `SQLCODE` are bare
identifiers, readable directly inside an exception handler as the caught
error's state code or numeric code. T-SQL has no matching bare identifier
— the same information is only reachable through the niladic functions
`ERROR_STATE()` and `ERROR_NUMBER()`, and both return an integer/tinyint,
not the string type `SQLSTATE`/`SQLCODE` behave as when concatenated into a
message.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestFlipRegressions::test_sqlstate_maps_on_tsql
SELECT 'S: ' || SQLSTATE
-- postgresql -> tsql:
SELECT 'S: ' + CAST(ERROR_STATE() AS NVARCHAR(5))

-- tests/unit/core/test_ir_first_families.py::TestFlipRegressions::test_sqlcode_maps_on_tsql
SELECT SQLCODE FROM DUAL
-- oracle -> tsql:
SELECT CAST(ERROR_NUMBER() AS NVARCHAR(20))
```

**Discussion.** Both bare identifiers translate to a T-SQL function call
wrapped in an explicit `CAST` to a right-sized `NVARCHAR` — `NVARCHAR(5)`
for `SQLSTATE` (a fixed 5-character SQLSTATE code) and `NVARCHAR(20)` for
`SQLCODE` (Oracle error numbers are signed integers, needing room for a
sign and up to several digits). The cast exists because `ERROR_STATE()`/
`ERROR_NUMBER()` are typed numeric/tinyint on T-SQL, while `SQLSTATE`/
`SQLCODE` behave as text on their source engines (concatenable with `||`
directly) — without it, a source expression like `'S: ' || SQLSTATE`
would fail to concatenate against T-SQL's `+` operator, which requires
matching (or implicitly convertible) operand types.

> **Note** faithful — the cast string reproduces the same code text/value
> the source identifier held inside its own exception handler. No warning.

**See Also.** [`test_ir_first_families.py::TestFlipRegressions`](../../../tests/unit/core/test_ir_first_families.py)
(`test_sqlstate_maps_on_tsql`, `test_sqlcode_maps_on_tsql`).
