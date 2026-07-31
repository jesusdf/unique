[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Oracle join syntax and row limits (source direction)" direction="oracle ↔ all" kind=article order=18 direction-inferred=true -->

# `FROM DUAL` synthesis and removal (bidirectional)

**Problem.** Oracle has no table-less `SELECT` — `SELECT 1` is
`ORA-00923` — so every scalar `SELECT` needs a `FROM` clause; Oracle's
answer is `DUAL`, a one-row system table. Every other engine allows (or, for
MySQL, merely tolerates) a bare `SELECT` with no `FROM` at all.

**Solution.**

```sql
-- pinning test: tests/unit/core/test_rownum_dual.py::TestFromDual
SELECT 1 FROM dual                    -- Oracle source
-- PostgreSQL / T-SQL: SELECT 1                 (DUAL dropped)
-- MySQL:              SELECT 1 FROM dual       (DUAL kept - MySQL accepts it)

SELECT 1                              -- T-SQL/MySQL source, Oracle target
-- Oracle: SELECT 1 FROM DUAL                    (DUAL synthesized)
```

Going **from** Oracle, `FROM dual` is dropped for PostgreSQL and T-SQL (a
bare `SELECT 1` is valid on both) but kept for MySQL, which also accepts
`FROM DUAL` natively — dropping it there would be gratuitous churn, not a
correctness fix. Going **to** Oracle from any table-less source `SELECT`
(T-SQL, MySQL, or an Oracle round-trip), `FROM DUAL` is synthesized so the
statement stays valid Oracle; a `SELECT` that already has a real `FROM`
clause is left untouched, and a leading comment on the statement survives the
rewrite.

**Discussion.** `DUAL` is a real, literal table name on every engine that
recognizes it (Oracle, MySQL) — not a keyword — so it cannot be mapped, only
added or removed depending on whether the target requires (Oracle), accepts
(MySQL) or has no use for (PostgreSQL/T-SQL) a `FROM`-less scalar `SELECT`.

> **Note** faithful — a one-row scalar `SELECT` returns the same single row
> whether or not `FROM (DUAL|dual)` is present/absent on a target that
> tolerates both forms.

**See Also.** [`tests/unit/core/test_rownum_dual.py::TestFromDual`](../../../tests/unit/core/test_rownum_dual.py).
