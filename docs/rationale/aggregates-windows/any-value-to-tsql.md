[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family" direction="postgresql/mysql → tsql" kind=article order=8 -->

# `ANY_VALUE` (MySQL / PostgreSQL 16+) → T-SQL

**Problem.** `ANY_VALUE(x)` returns an arbitrary (implementation
picked) value from the group — used to satisfy a functional-dependency
`GROUP BY` without an aggregate wrapper.

**Solution.** PostgreSQL 16+ keeps the native `ANY_VALUE` (the
sibling `GROUP_CONCAT`→`STRING_AGG` in the same statement works too, live
`(1,'1,2')`); T-SQL degrades the call to a documented carrier + warning.

**Discussion.** T-SQL has no `ANY_VALUE` function and no
equivalent "pick one, unspecified which" aggregate.

> **Warning** `[limit]` on T-SQL — approved degrade, no faithful
> substitute exists.

**See Also.** [`my-any-value`](../../../tests/fixtures/challenge/challenge_mysql.sql) · [§2.1](../../03-unsupported.md) (unmapped
built-in scalar functions).
