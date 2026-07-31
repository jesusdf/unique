[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Oracle join syntax and row limits (source direction)" direction="cross-engine" kind=article order=17 direction-inferred=true -->

# `ROWNUM <= n` (Oracle) → `LIMIT` / `TOP` / `FETCH FIRST`

**Problem.** Oracle's `ROWNUM` is a pseudo-column numbering rows as they are
produced; `WHERE ROWNUM <= n` is Oracle's idiom for capping a result to `n`
rows — with no ordering guarantee unless paired with an `ORDER BY` (the
`ROWNUM` filter applies before any sort).

**Solution.**

```sql
-- pinning test: tests/unit/core/test_rownum_dual.py::TestRownum
-- (no challenge-corpus case yet)
SELECT * FROM t WHERE ROWNUM <= 5
-- PostgreSQL / MySQL: SELECT * FROM t LIMIT 5
-- T-SQL:              SELECT TOP 5 * FROM t
```

`ROWNUM <= n` / `ROWNUM < n+1` folds to a plain `LIMIT n` (PostgreSQL/MySQL)
or `TOP n` (T-SQL); a `ROWNUM` predicate ANDed with another condition keeps
that condition in `WHERE` and only the row cap moves. Live-verified
(seed rows `1, 2, 3`): Oracle's `WHERE ROWNUM <= 2` and PostgreSQL's
`LIMIT 2` both return exactly 2 of the 3 rows.

**Discussion.** No other engine has a pseudo-column numbering rows before
`ORDER BY`; each target's own row-cap clause is the direct equivalent for the
common `ROWNUM <= n` idiom. `ROWNUM` used outside a simple upper-bound
predicate (e.g. projected in the select list, compared with `>`, or assigned
to a variable) has no such direct rewrite and is signalled rather than
silently passed through or dropped.

> **Note** faithful for the `ROWNUM <= n` / `< n+1` upper-bound form — same
> row *count* as Oracle's own (both are unordered without an explicit
> `ORDER BY`, mirroring this page's "`DELETE TOP (n)` row caps" entry's
> "faithful to `TOP`'s own unordered semantics" reasoning, applied here to a
> read instead of a delete). `[limit]` (warned) for any other `ROWNUM` shape.

**See Also.** [`tests/unit/core/test_rownum_dual.py::TestRownum`](../../../tests/unit/core/test_rownum_dual.py)
(note: lives in `tests/unit/core/`, not `tests/integration/`).
