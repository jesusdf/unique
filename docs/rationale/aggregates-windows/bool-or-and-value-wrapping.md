[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Boolean aggregates and `FILTER`" direction="postgresql → tsql/oracle" kind=article order=4 -->

# `bool_or`/`bool_and` value wrapping (PostgreSQL) → T-SQL / Oracle

**Problem.** `(a > 1)::int` and `bool_or(pred)` both need a
predicate's truth value used as an ordinary scalar (a `CAST` operand, or an
aggregate argument).

**Solution.** The predicate is wrapped in a `CASE WHEN … THEN 1 ELSE
0 END` — `CAST(a > 1 AS INT)` becomes `CASE WHEN a > 1 THEN 1 ELSE 0 END`.

**Discussion.** T-SQL and Oracle have no boolean value
type: a predicate cannot appear as a `CAST` operand (T-SQL error 156, Oracle
`ORA-02000`) or as a bare aggregate argument.

> **Note** faithful (same integer value).

**See Also.** [`pg-bool-to-int-cast`](../../../tests/fixtures/challenge/challenge_postgresql.sql).
