[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Recursive CTE synthesis" direction="tsql/mysql → all" kind=article order=24 -->

# Recursive CTE synthesis: `WITH RECURSIVE` keyword, Oracle's required column list, and the `MAXRECURSION` hint

**Problem.** A recursive CTE — one whose body queries its own name — needs
different declaration syntax on every engine. T-SQL and Oracle both infer
recursion from the CTE simply referencing itself and need no keyword at
all; PostgreSQL and MySQL require an explicit `WITH RECURSIVE` up front, a
parse error if it's missing. Oracle additionally *requires* an explicit
column-alias list on any recursive CTE, even when the anchor `SELECT`'s own
column names would otherwise be inferred automatically the way they are on
every other recursive-CTE-capable engine.

**Solution.**

A self-referencing T-SQL CTE reaches PostgreSQL/MySQL with `RECURSIVE`
added, and Oracle unchanged (no keyword — Oracle infers it):

```sql
-- ts-recursive-cte, tsql → postgresql / mysql / oracle
WITH r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 5) SELECT * FROM r;

-- => postgresql / mysql
WITH RECURSIVE r(n) AS (
  SELECT 1
  UNION ALL
  SELECT n + 1
  FROM r
  WHERE n < 5
)
SELECT * FROM r;

-- => oracle (no RECURSIVE keyword — a syntax error there)
WITH r(n) AS (
  SELECT 1 FROM DUAL
  UNION ALL
  SELECT n + 1
  FROM r
  WHERE n < 5
)
SELECT * FROM r;
```

When the source CTE omits its own column-alias list, Oracle still needs
one — it's derived from the anchor `SELECT`'s own output column names:

```sql
-- ts-maxrecursion, tsql → oracle (source has no explicit r(n) alias list)
WITH s AS (SELECT 1 n UNION ALL SELECT n+1 FROM s WHERE n<5) SELECT n FROM s;
-- =>
WITH s(n) AS (
  SELECT 1 AS n FROM DUAL
  UNION ALL
  SELECT n + 1
  FROM s
  WHERE n < 5
)
SELECT n FROM s;
```

T-SQL's own recursion-depth guard, the trailing `OPTION (MAXRECURSION n)`
hint, is dropped with a warning rather than silently discarded, since
PostgreSQL, MySQL and Oracle recursive queries have no equivalent depth
ceiling to translate it into:

```sql
-- ts-maxrecursion, tsql → oracle / postgresql / mysql
WITH s AS (SELECT 1 n UNION ALL SELECT n+1 FROM s WHERE n<5) SELECT n FROM s OPTION (MAXRECURSION 10);
-- => the CTE translates as above, plus:
-- UNIQUE-1238: T-SQL OPTION (MAXRECURSION 10) has no portable equivalent
-- and was dropped: T-SQL raises an error once a recursive CTE exceeds 10
-- recursions (the server default is 100 when no OPTION is given), while
-- PostgreSQL, MySQL and Oracle recursive queries have no such limit — a
-- source query that relied on the T-SQL error to bound recursion will
-- instead run to completion (or loop) elsewhere
```

**Discussion.** Three independent engine requirements collide on the same
construct. The `RECURSIVE` keyword is a pure syntax difference — T-SQL and
Oracle both recognize a CTE that references its own name without being
told to expect it, while PostgreSQL and MySQL parse `WITH` non-recursively
by default and need the keyword to switch modes; detecting the
self-reference and adding the keyword only where it's required (never on
T-SQL/Oracle, where it would itself be a syntax error) reproduces both
sides correctly. Oracle's column-list requirement (`ORA-32039` without one)
is unrelated to the keyword question — it's Oracle's own recursive-CTE
grammar rule, satisfied here by deriving the names from the anchor
`SELECT`'s own output rather than inventing placeholder names or
requiring the source to have spelled them out already.

`MAXRECURSION` is different in kind from the first two: it isn't a syntax
gap but a **semantic guard** with no portable equivalent — T-SQL raises an
error once a recursive CTE exceeds the given bound (or the implicit
default of 100 recursions with no `OPTION` at all), while the other three
engines' recursion has no depth limit of its own. Translating the clause
away can't preserve that guard, so it's surfaced as a warning
(`UNIQUE-1238`) rather than either emitted as invalid syntax on a target
that has no such option, or dropped without telling the reader their
recursion-depth safety net is gone. Every other T-SQL query hint
(`MAXDOP`, `RECOMPILE`, `FORCE ORDER`, `KEEPFIXED PLAN`, …) is a pure
optimizer directive with no effect on the result set, and is dropped the
same way with a lighter warning (`UNIQUE-1239`).

> **Note** faithful (`RECURSIVE` keyword placement; Oracle column-list
> derivation) — live-verified `1..5` on PostgreSQL/MySQL and Oracle. >
> **Warning** (`MAXRECURSION` drop) — the target's recursion has no depth
> ceiling; a query that relied on T-SQL's guard to terminate runaway
> recursion will instead run to completion or loop.

**See Also.** Corpus [`ts-recursive-cte`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`ts-maxrecursion`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`ts-recursion-limit`](../../../tests/fixtures/challenge/challenge_sqlserver.sql),
[`my-seq-concat`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestRecursiveCteKeyword`](../../../tests/integration/test_challenge.py),
[`TestRecursiveCteOracleColumnList`](../../../tests/integration/test_challenge.py) ·
[§3.8](../../03-unsupported.md), "Recursive CTEs" ·
[`UNIQUE-1238`](../../reference/warnings.md#unique-1238),
[`UNIQUE-1239`](../../reference/warnings.md#unique-1239).
