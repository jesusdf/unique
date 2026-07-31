[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="NULL and empty-string semantics" direction="cross-engine" kind=article order=2 direction-inferred=true -->

# `GREATEST`/`LEAST` NULL-propagation per engine

**Problem.** MySQL and Oracle's `GREATEST`/`LEAST` return `NULL` if *any*
argument is `NULL`. PostgreSQL and T-SQL's `GREATEST`/`LEAST` **ignore**
`NULL` arguments and pick the max/min of the survivors:
`GREATEST(1, NULL, 3)` is `3` on PostgreSQL/T-SQL, `NULL` on MySQL/Oracle —
the same propagate-vs-ignore split as `CONCAT`/`||` above, on a different
function pair.

**Solution.**

```sql
-- my-greatest-null, mysql → postgresql / tsql
SELECT GREATEST(1, NULL, 3) AS r;
-- =>
SELECT CASE WHEN 1 IS NULL OR NULL IS NULL OR 3 IS NULL THEN NULL ELSE GREATEST(1, NULL, 3) END AS r;

-- reda-ora-greatest-null, oracle → postgresql / tsql
SELECT GREATEST(1, NULL, 3) AS r FROM DUAL;
-- => same CASE-guard shape as above, on both targets

-- pg-greatest-null, postgresql → mysql / oracle
SELECT GREATEST(1, NULL, 3) AS r;
-- =>
SELECT GREATEST(1, 3) AS r;
```

Going **MySQL/Oracle → PostgreSQL/T-SQL**, the call is wrapped in `CASE WHEN
<arg> IS NULL OR … THEN NULL ELSE GREATEST(…) END` so the propagating
source's `NULL` survives on a target that would otherwise ignore it. Going
**PostgreSQL → MySQL/Oracle**, a literal `NULL` argument is instead dropped
from the call, so MySQL/Oracle's own propagating `GREATEST`/`LEAST` computes
the max/min of the remaining arguments — the value PostgreSQL's
NULL-ignoring semantics already produced (a single survivor collapses to
that value directly, since MySQL rejects a 1-arg `GREATEST`/`LEAST`). A
target that already shares the source's propagation direction needs no
rewrite and passes the call through unchanged.

**Discussion.** A straight copy of the call reverses the result on whichever
side disagrees with the source, exactly as with `CONCAT`/`||`. This was
filed as a `lying-warning`: the only signal on the Oracle-source →
PostgreSQL leg was the internal "unread sqlglot arg `ignore_nulls` on
`Greatest` — may be dropped" tripwire, which does not name the NULL-semantics
divergence and had no docs entry (`reda-ora-greatest-null`).

> **Note** faithful — live-verified: MySQL/Oracle `GREATEST(1, NULL, 3)` =
> `NULL`, reproduced as `NULL` by the guarded `CASE` on PostgreSQL/T-SQL (was
> `3` before the fix); PostgreSQL's own `GREATEST(1, NULL, 3)` = `3`,
> reproduced as `3` by `GREATEST(1, 3)` after the literal-`NULL` drop on
> MySQL/Oracle. No warning in either direction.

**See Also.** Corpus [`my-greatest-null`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-greatest-null2`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-least-greatest-null`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-least-null2`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`reda-ora-greatest-null`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`pg-greatest-null`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestGreatestLeastNullPropagation`](../../../tests/integration/test_challenge.py), [`TestGreatestLeastDropsNullFromPg`](../../../tests/integration/test_challenge.py) (pinned) · `test_mysql_to_tsql[my-greatest-null]`/`test_mysql_to_postgresql[my-greatest-null]` (`test_challenge_assertions_mysql.py`) · `test_ora_case` (`test_challenge_assertions_oracle.py`, `reda-ora-greatest-null` row) ·
`emit_functions.py:1644-1678` (docstring).

---
