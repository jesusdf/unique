[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`PIVOT` / `UNPIVOT`" direction="tsql/oracle → all" kind=article order=2 -->

# `UNPIVOT` (T-SQL / Oracle) → all targets

**Problem.** `UNPIVOT (val FOR col IN (a, b))` turns columns `a`,
`b` into row pairs `(col, val)` — `col` carrying the *name* of the source
column, `val` its value.

**Solution.**

```sql
-- corpus case ora-unpivot (Oracle folds unquoted 'a'/'b' to 'A'/'B')
SELECT id,col,val FROM (SELECT 1 id,10 a,20 b FROM DUAL) UNPIVOT (val FOR col IN (a,b))
-- rewritten everywhere as:
--   SELECT id, 'A' AS col, a AS val FROM (...) WHERE a IS NOT NULL
--   UNION ALL
--   SELECT id, 'B' AS col, b AS val FROM (...) WHERE b IS NOT NULL
-- (name-column literal cased 'A'/'B' — matching Oracle's own upper-case fold —
-- not the lower-case 'a'/'b' a T-SQL source would produce for the same shape)
```

`SELECT <carried cols>, '<name>' AS col, <col> AS val
FROM <source> WHERE <col> IS NOT NULL` unioned per unpivoted column. When the
source's carried columns are not visible (no projection to name), it
degrades to a warned carrier instead.

**Discussion.** Unique renders `UNPIVOT` as a `UNION
ALL` (one arm per unpivoted column, `NULL`s excluded to match `UNPIVOT`'s
default) on **every** target, never the native `UNPIVOT` operator — even on
Oracle and T-SQL, which have one. The reason is the *name-column value*:
native `UNPIVOT` re-derives it from the `IN`-list identifier, and Oracle
folds an unquoted identifier to upper case, so Oracle's native `UNPIVOT`
yields `'A'` where T-SQL's yields `'a'` for the same source. The `UNION ALL`
rewrite instead emits an explicit string literal cased exactly as the
*source* engine would produce it, so the value matches across engines
(`emit_relations.py::_emit_unpivot_relation` docstring).

> **Note** faithful — values verified equal on
> Oracle/PostgreSQL/MySQL. `[limit]` (warned carrier) when the source
> projection is invisible.

**See Also.** [`ts-unpivot`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ora-unpivot`](../../../tests/fixtures/challenge/challenge_oracle.sql).
