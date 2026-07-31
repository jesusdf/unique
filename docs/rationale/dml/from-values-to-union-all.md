[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Portable row-source rewrites (PostgreSQL)" direction="postgresql → all" kind=article order=19 -->

# `FROM (VALUES …)` / a quantified bare-`VALUES` subquery (PostgreSQL) → `UNION ALL` chain (every target)

**Problem.** PostgreSQL's `VALUES (1),(2),(3)` is a first-class row source,
usable directly as a `FROM` item, as the operand of a quantified comparison
(`n > ALL (VALUES …)`), or with a column-aliased `v(x)`.

**Solution.**

```sql
-- corpus case pg-avg-null
SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)
-- T-SQL:
SELECT AVG((x) * 1.0)
FROM (SELECT 1 AS x UNION ALL SELECT 2 UNION ALL SELECT NULL UNION ALL SELECT 4) v
-- Oracle:
SELECT AVG(x)
FROM (SELECT 1 AS x FROM DUAL UNION ALL SELECT 2 FROM DUAL
      UNION ALL SELECT NULL FROM DUAL UNION ALL SELECT 4 FROM DUAL) v;
-- MySQL:
SELECT AVG(x)
FROM (SELECT 1 AS x UNION ALL SELECT 2 UNION ALL SELECT NULL UNION ALL SELECT 4) v;

-- corpus case pg-all-values (quantified form)
SELECT id FROM t WHERE n > ALL (VALUES (1),(2),(3))
-- Oracle:
SELECT id FROM t
WHERE n > ALL (SELECT 1 FROM DUAL UNION ALL SELECT 2 FROM DUAL UNION ALL SELECT 3 FROM DUAL);
```

Every `VALUES (…)` row list used as a *relation* (a `FROM` item or a
quantified-comparison subquery operand — not an `INSERT … VALUES` row list,
which every target keeps natively) is rewritten to a `SELECT <v1> UNION ALL
SELECT <v2> UNION ALL …` chain, even on T-SQL and MySQL, which both accept
`VALUES` as a table constructor natively. (T-SQL's `AVG` also gets its own,
separate integer-average promotion here; Oracle appends `FROM DUAL` to
every arm, per the "`FROM DUAL` synthesis" entry above.)

**Discussion.** The `UNION ALL` chain is not a per-engine compensation for
a missing feature — T-SQL and MySQL both support `VALUES (…)` as a `FROM`
row source. It is used because a **bare** `VALUES (…)` list is not a valid
subquery *expression* on MySQL, Oracle or T-SQL: only PostgreSQL treats
`VALUES` itself as a first-class query the way it treats `SELECT`, so `n >
ALL (VALUES (1),(2),(3))` — a `VALUES` list used directly as a quantified
comparison's operand — has no direct spelling on the other three at all.
The `SELECT … UNION ALL …` chain is a row source every target accepts in
every position a `VALUES` list can appear (including this one), so Unique
renders it uniformly rather than special-casing the one or two positions
(T-SQL/MySQL `FROM`) where a native `VALUES` would actually parse.

> **Note** faithful — corpus `pg-avg-null` is live-verified equal (same
> value; the decimal scale differs per engine's own `AVG` precision rules,
> not a translation loss); corpus `pg-all-values` is live-executed on
> T-SQL/Oracle/MySQL.

**See Also.** [`pg-avg-null`, `pg-all-values`](../../../tests/fixtures/challenge/challenge_postgresql.sql)
· "`FROM DUAL` synthesis and removal" entry above.
