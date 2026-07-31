[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Positional GROUP BY resolved to a column name" direction="postgresql → tsql" kind=article order=25 direction-inferred=true -->

# `GROUP BY 1` (positional ordinal) → the actual `SELECT`-list column name

**Problem.** PostgreSQL accepts a positional ordinal in `GROUP BY` —
`GROUP BY 1` groups by whatever the first `SELECT`-list expression is.
T-SQL's `GROUP BY` grammar has no positional form at all: a bare integer
there is read as an (invalid) grouping *expression*, not a reference back
into the `SELECT` list.

**Solution.**

```sql
-- corpus case pg-group-by-ordinal
SELECT dept, COUNT(*) FROM t GROUP BY 1
-- postgresql -> tsql:
SELECT dept, COUNT(*)
FROM t
GROUP BY dept
```

**Discussion.** Unique resolves the ordinal against the query's own
`SELECT` list at translation time — position `1` is the first projected
expression, here `dept` — and substitutes the actual expression text in
`GROUP BY`'s place, exactly as if the source had written it out by name to
begin with. This only fires on a target with no positional `GROUP BY` of
its own; PostgreSQL, MySQL, and Oracle's identity/cross-transpile paths
keep the ordinal untouched where it's still legal.

> **Note** faithful — grouping by the resolved column name produces
> identical groups to grouping by the ordinal position, since both refer to
> the same underlying expression. No warning.

**See Also.** Corpus [`pg-group-by-ordinal`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`test_challenge_assertions_postgresql.py` (`pg-group-by-ordinal`).
