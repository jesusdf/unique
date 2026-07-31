[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Boolean aggregates and `FILTER`" direction="postgresql → tsql/oracle/mysql" kind=article order=3 -->

# `agg(x) FILTER (WHERE p)` clause (PostgreSQL) → T-SQL / MySQL / Oracle

**Problem.** PostgreSQL's `FILTER (WHERE p)` restricts which rows an
aggregate sees (`SUM(x) FILTER (WHERE y > 5)` sums only the rows where `y >
5`) without a separate subquery or `CASE`; none of the other three engines
parse the clause at all (T-SQL error 102, "incorrect syntax").

**Solution.**

```sql
-- test_pg_source_wave1.py::TestAggregateFilterRewrite
select count(*) filter (where c <> 0) from t;
-- -> tsql: SELECT COUNT(CASE WHEN c <> 0 THEN 1 END) FROM t

select sum(x) filter (where y > 5) from t;
-- -> mysql / oracle: SELECT SUM(CASE WHEN y > 5 THEN x END) FROM t
```

Every `agg(x) FILTER (WHERE p)` rewrites to `agg(CASE WHEN p THEN x
END)` — the `CASE`'s implicit `ELSE NULL` reproduces "this row is excluded
from the aggregate" for any aggregate that already ignores `NULL` (`SUM`,
`COUNT`, `AVG`, `MIN`, `MAX`, …). `COUNT(*) FILTER (WHERE p)` has no column
to guard, so the `CASE`'s `THEN` branch counts a literal `1` instead.

**Discussion.** T-SQL, MySQL, and Oracle all reject `FILTER` as a syntax
error at parse time — there is no native spelling to fall back to on any of
them. The `CASE`-wrap rewrite works because every standard aggregate already
treats a `NULL` input as "not counted," so feeding it `NULL` on the
filtered-out rows is exactly equivalent to never seeing those rows at all.

> **Note** faithful — same aggregate value; corpus case
> `pg-filter-subquery` (`COUNT(*) FILTER` against a correlated-subquery
> threshold) is the standalone FILTER-alone case this rewrite is built from,
> and the `bool_or(...) FILTER (...)` entry below composes it with a second,
> independent rewrite.

**See Also.** [`pg-filter-subquery`](../../../tests/fixtures/challenge/challenge_postgresql.sql) · `tests/integration/test_pg_source_wave1.py` (`TestAggregateFilterRewrite`).
