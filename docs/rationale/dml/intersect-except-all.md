[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Set-operation `ALL` quantifier" direction="cross-engine" kind=article order=23 direction-inferred=true -->

# `INTERSECT ALL` / `EXCEPT ALL` → Oracle / T-SQL

**Problem.** `INTERSECT ALL` and `EXCEPT ALL` compare rows the same way as
the plain `INTERSECT`/`EXCEPT`, but **keep duplicates**: `INTERSECT ALL`
returns `min(count in left, count in right)` copies of each matching row,
and `EXCEPT ALL` returns `max(count in left − count in right, 0)` copies.
Falling back to the plain, duplicate-collapsing form changes the answer,
not just the spelling.

**Solution.**

```sql
-- source: duplicate-bearing arms, t1 = {1, 1, 2}, t2 = {1}
SELECT a FROM t1 INTERSECT ALL SELECT a FROM t2;
SELECT a FROM t1 EXCEPT ALL SELECT a FROM t2;

-- Oracle: native, same quantifier — EXCEPT ALL spells MINUS ALL
SELECT a FROM t1 INTERSECT ALL SELECT a FROM t2;
SELECT a FROM t1 MINUS ALL SELECT a FROM t2;

-- T-SQL: each side's rows are numbered per duplicate, paired, then
-- the row number is projected away
SELECT c0 AS a
FROM (
  SELECT a AS c0, ROW_NUMBER() OVER (PARTITION BY a ORDER BY (SELECT NULL)) AS rn
  FROM t1
  INTERSECT
  SELECT a AS c0, ROW_NUMBER() OVER (PARTITION BY a ORDER BY (SELECT NULL)) AS rn
  FROM t2
) uq;
```

Live-verified with `t1 = {1, 1, 2}`, `t2 = {1}`: `INTERSECT ALL` returns a
single `1` (the smaller of the two counts) and `EXCEPT ALL` returns `1, 2`
(the leftover copy of `1` plus the untouched `2`) — identically on
PostgreSQL, MySQL, Oracle and T-SQL.

**Discussion.** PostgreSQL and MySQL support `INTERSECT ALL`/`EXCEPT ALL`
directly, and so does Oracle from version 21c onward — only its
`EXCEPT ALL` is spelled `MINUS ALL`, matching its plain `EXCEPT`/`MINUS`
naming. T-SQL has neither `ALL` form on either operator (the server
rejects the keyword outright). To keep every duplicate there, each side's
rows are first numbered per distinct value with `ROW_NUMBER() OVER
(PARTITION BY <every output column> ORDER BY (SELECT NULL))` — the
`ORDER BY (SELECT NULL)` is T-SQL's standard "no particular order needed"
idiom, required syntactically by `ROW_NUMBER`. A plain (deduplicating)
`INTERSECT`/`EXCEPT` on the numbered rows then keeps a (row, copy-number)
pair only when it is present on both sides (`INTERSECT`) or only on the
left (`EXCEPT`) — reproducing the exact `min`/`max` counts of the `ALL`
form, one distinct value at a time. The outer query drops the row-number
column, leaving just the original columns under their original names.

The rewrite covers the common shape: one `ALL` operator, optionally
preceded by other `UNION`/`INTERSECT`/`EXCEPT` operators, with a known
column list on both sides. An `ALL` operator immediately followed by more
chained set operations, or acting on `SELECT *`, is reported as a
limitation instead of being rewritten with a guess at operator precedence
or an unknown column list.

> **Warning** T-SQL: an `ALL` operator immediately followed by more
> chained set operations, or acting on `SELECT *`, is reported as an
> unsupported construct rather than silently losing duplicate rows.

> **Note** faithful (all other shapes) — live-verified above: PostgreSQL,
> MySQL, Oracle and T-SQL all return the same duplicate-preserving row set.

**See Also.** [`test_setop_all.py`](../../../tests/integration/test_setop_all.py)
· [`UNIQUE-1003`](../../reference/warnings.md#unique-1003), the general
"statement preserved as a comment" carrier, for the unsupported-chain case.
