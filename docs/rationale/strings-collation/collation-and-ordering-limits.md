[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Collation and ordering" direction="cross-engine" kind=article order=13 direction-inferred=true -->

# Collation and ordering divergences — documented limits

**Problem.** String equality, `ORDER BY`, `DISTINCT`, `GROUP BY` and
`LIKE` all compare under the source engine's **default collation** — case
sensitivity, accent sensitivity, and trailing-space handling are properties
of that collation, not of the SQL text.

**Solution.**

```sql
-- pg-order-nulls-default, postgresql → mysql
SELECT x FROM (VALUES (3),(1),(NULL)) v(x) ORDER BY x;
-- =>
SELECT x
FROM (SELECT 3 AS x UNION ALL SELECT 1 UNION ALL SELECT NULL) v
ORDER BY CASE WHEN x IS NULL THEN 1 ELSE 0 END, x ASC;
```

A related but **fixable** case is `NULL`-ordering default: PostgreSQL and
Oracle sort `NULL` **high** (last, ascending) by default; MySQL and T-SQL
sort it **low** and have no `NULLS FIRST/LAST` keyword to ask for the other
order explicitly. This *is* statement-compensable — the source order can be
reconstructed with a leading priority key — so it is not a limit but a
`faithful` rewrite.

**Discussion.** Collation is a **per-column** (or
connection-default) property that a statement like `SELECT 'a ' = 'a'` does
not carry any trace of — there is nothing in the transpiled text to compile
against. T-SQL's default collation is case-insensitive and (per SQL Server's
padding rules) ignores trailing spaces in comparison, so `'a '='a'` is true
there; PostgreSQL/Oracle/MySQL's typical defaults are case- and
space-sensitive, so the same comparison is false. No statement-level rewrite
can bridge this without knowing the actual target column collation, which
Unique does not have visibility into — a documented limit, not a bug
(`docs/03-unsupported.md` §2, "String collation in `=`/`ORDER BY`/`DISTINCT`/
`LIKE`"):

```sql
-- ts-trailing-eq, tsql → mysql / oracle / postgresql
SELECT IIF('a ' = 'a', 1, 0) AS r;
-- T-SQL: 1 (true, CI + space-insensitive default).  Others: 0 (false).
```

MySQL's/T-SQL's default **case-insensitive** collation additionally changes
what `DISTINCT`/`GROUP BY`/`ORDER BY` themselves consider equal — `'a'` and
`'A'` collapse into one row under `DISTINCT` on MySQL/T-SQL but stay two rows
on the case-sensitive PostgreSQL/Oracle defaults. This is a **row-count**
divergence, not just a display/order difference, and cannot be bridged by an
`ORDER BY LOWER(x)` rewrite (invalid under `DISTINCT`, since the sort key
would not be in the select list, and it does not change what `DISTINCT`
itself deduplicates) — documented separately as its own limit
(`docs/03-unsupported.md` §3.14).

> **Warning** `NULL`-ordering: `faithful` (live-verified
> reconstruction). Case/accent/trailing-space **comparison** results and
> case-insensitive **deduplication** row counts: **documented limits, warned**
> — no workaround exists without column-level collation visibility Unique does
> not have.

**See Also.** Corpus [`ts-trailing-eq`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`ts-trailing-space-cmp`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`pg-order-nulls-default`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`my-distinct-case`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-group-case`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[§2](../../03-unsupported.md), "String collation in `=`/`ORDER BY`/`DISTINCT`/
`LIKE`" · §3.14, "Case-Insensitive Collation Under DISTINCT / ORDER BY" ·
[`TestNullOrderingEmulation`](../../../tests/integration/test_challenge.py) (pinned) ·
[`UNIQUE-1015`](../../reference/warnings.md#unique-1015).
