[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Oracle formal parameter/return types stripped of precision and scale" direction="tsql → oracle" kind=article order=53 -->

# T-SQL sized parameter/return types (`DECIMAL(5,2)`, `NVARCHAR(50)`) → unconstrained on an Oracle routine header

**Problem.** Oracle's PL/SQL forbids length, precision, or scale on a
*formal parameter* or *function return* type declaration — `PLS-00103` —
even though the identical sized type is perfectly legal on a `CREATE
TABLE` column. A T-SQL procedure's sized parameters (`@pct DECIMAL(5,2)`,
`@name NVARCHAR(50)`) translated verbatim into an Oracle header are a
compile error.

**Solution.**

```sql
-- tests/unit/core/test_boolean_timestamp.py::TestOracleParameterTypes
CREATE PROCEDURE dbo.upd @id INT, @pct DECIMAL(5,2), @name NVARCHAR(50) AS BEGIN
  UPDATE p SET v = @pct WHERE id = @id;
END
-- tsql -> oracle:
CREATE OR REPLACE PROCEDURE upd
(
    V_ID IN NUMBER,
    V_PCT IN NUMBER,
    V_NAME IN NVARCHAR2
)
AS
BEGIN
    UPDATE p SET v = V_PCT WHERE id = V_ID;
END;
/
```

A *table* column keeps its precision/scale/length unchanged (`name
NVARCHAR(50)` stays `NVARCHAR2(50)`) — only parameters and function return
types are stripped.

**Discussion.** The rule is scoped precisely to routine headers: Unique
strips a type's length/precision/scale only while emitting an Oracle
parameter or `RETURN` clause, and leaves the identical type declaration
alone everywhere else (table columns, local variable `DECLARE`s inside the
body — Oracle allows constraints there too). This mirrors, at the
signature level, the same PL/SQL-context-sensitivity this page's `CAST`
entries document at the expression level: what's legal depends on exactly
which Oracle grammar production the type lands in, not on the type itself.

> **Note** faithful — the underlying value range is unaffected for any
> value that actually fits T-SQL's declared bound; Oracle's unconstrained
> `NUMBER`/`NVARCHAR2` simply accepts a wider range than the source's
> explicit constraint did, which is never observable as a data loss (only
> as a validation the source engine would have performed but Oracle's
> parameter grammar cannot). No warning.

**See Also.** [`test_boolean_timestamp.py::TestOracleParameterTypes`](../../../tests/unit/core/test_boolean_timestamp.py)
(`test_sized_parameter_types_are_unconstrained`,
`test_function_return_type_unconstrained`,
`test_table_column_types_keep_size`).
