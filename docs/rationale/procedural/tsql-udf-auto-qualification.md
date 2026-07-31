[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="T-SQL scalar UDF auto-qualification" direction="cross-engine" kind=article order=40 direction-inferred=true -->

# An unqualified scalar function call → `dbo.`-qualified on T-SQL

**Problem.** T-SQL requires a user-defined scalar function call to be
schema-qualified (`dbo.fn(...)`); an unqualified call is error 195, "not a
recognized built-in function name," even when a function of that name
exists in the target database. A source call to a function the script
never defines itself (because it lives in the client's own schema, not the
migrated script) has no way to be told apart from a genuine typo except by
checking it against every built-in Unique already knows how to map.

**Solution.**

```sql
-- tests/integration/test_tsql_udf_qualification.py::TestStandaloneDml::test_update_assignment_value_is_qualified
UPDATE h SET c = my_fn_guid();
-- oracle -> tsql:
UPDATE h
SET c = dbo.my_fn_guid()
```

The same rewrite applies inside a procedure body's raw expressions (an
assignment, an `IF` condition), and to every call site of the name in a
script, not just the first:

```sql
-- tests/integration/test_tsql_udf_qualification.py::TestProceduralRawExpressions
CREATE OR REPLACE PROCEDURE p_q(m_out OUT VARCHAR2) AS
BEGIN
  m_out := my_conf_fn('k', 'd');
END;
-- oracle -> tsql, inside the procedure body:
SET @m_out = dbo.my_conf_fn('k', 'd');
```

A call already qualified with a schema (`other_schema.fn(a)`) is left
untouched, and a call recognized as a T-SQL builtin or a *known* mapping
from another dialect (`SYSDATE` → `GETDATE()`) is never qualified — only
targets are qualified, and only on T-SQL.

**Discussion.** The decision is structural, not a guess: a call is
qualified with `dbo.` only when its name is neither a T-SQL builtin nor a
builtin Unique already maps from the source dialect. An *unmapped* foreign
builtin (Oracle's `REGEXP_SUBSTR`, say) is deliberately left unqualified —
qualifying it as `dbo.REGEXP_SUBSTR` would mask a genuine mapping gap as a
phantom user function, turning a visible failure into a silent wrong
answer. The qualification itself happens in two different code paths for
the same reason: the IR emitter handles standalone/embedded DML, and a
string-aware rewriter handles procedural raw expressions (assignments,
conditions) that never reach the IR.

> **Note** faithful — the call's name, arguments, and semantics are
> unchanged; only the `dbo.` schema prefix T-SQL requires for a
> user-defined function is added. No warning: this is a syntactic
> requirement, not a value-changing rewrite.

**See Also.** [`test_tsql_udf_qualification.py`](../../../tests/integration/test_tsql_udf_qualification.py)
(`TestStandaloneDml`, `TestProceduralRawExpressions`).
