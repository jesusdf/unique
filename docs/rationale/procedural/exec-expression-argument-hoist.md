[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Expression arguments hoisted through a synthesized variable" direction="oracle → tsql" kind=article order=10 -->

# EXEC / routine-call expression argument (Oracle) → synthesized variable (T-SQL)

**Problem.** A T-SQL `EXEC` call accepts only a literal, a variable, or
`DEFAULT`/`NULL` in its argument list — never an arbitrary expression. An
Oracle call passing `SYSDATE`, or any other expression, as a named-association
argument (`PRC(V_ID=>1, V_modstamp=>SYSDATE)`) has no legal T-SQL spelling
inline.

**Solution.** The expression is hoisted into a synthesized variable declared
immediately before the `EXEC`, and the call itself passes only that
variable. A `GETDATE()`/`SYSDATETIME()`/`SYSUTCDATETIME()` value (the
Oracle-source `SYSDATE` case) gets its own dedicated `@uq_nowN DATETIME`
variable:

```sql
-- tests/integration/test_oracle_source_m4_wave.py::TestWave12And13Classes::test_exec_expression_argument_hoisted
BEGIN
    PRC_MED_INS(V_ID=>1, V_modstamp=>SYSDATE);
END;
-- oracle -> tsql:
DECLARE @uq_now1 DATETIME = GETDATE();
EXEC PRC_MED_INS @V_ID = 1, @V_modstamp = @uq_now1;
```

A general (non-`now()`) expression argument hoists the same way, into a
variable typed from the callee's own declared parameter type where it can be
resolved, rather than being restricted to the date-function case.

**Discussion.** T-SQL's `EXEC`/`EXECUTE` call syntax is simply stricter than
Oracle's named-association call, which accepts any expression directly. As
with the `RAISERROR` message hoist above, an expression argument has to be
evaluated into a variable *before* the call, in a separate statement, since
there is no argument-position syntax in T-SQL that would accept it inline.

> **Note** faithful — the hoisted variable holds exactly the value the
> inline expression would have evaluated to at the same point in the routine
> (same evaluation order, immediately before the call). No warning.

**See Also.** [`TestWave12And13Classes`](../../../tests/integration/test_oracle_source_m4_wave.py) —
no dedicated challenge-corpus case exercises the expression-argument hoist,
so the example above is drawn from that dedicated integration test.
