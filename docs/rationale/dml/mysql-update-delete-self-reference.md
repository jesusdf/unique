[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Self-referencing `UPDATE`/`DELETE` subquery (MySQL)" direction="all → mysql" kind=article order=26 -->

# A subquery reading its own `UPDATE`/`DELETE` target → MySQL derived-table wrap

**Problem.** MySQL rejects a subquery — anywhere in an `UPDATE`'s `SET` or
`WHERE` clause, or a `DELETE`'s `WHERE` clause — that reads from the very
table being written, with error 1093 ("You can't specify target table 't'
for update in FROM clause"). This fires whether the self-reference sits in a
scalar comparison, an `IN` list, or an `EXISTS` check, whether it carries its
own alias or not, and even when it is one of two joined tables inside that
subquery rather than the subquery's only source.

**Solution.**

```sql
-- pinning test: test_challenge.py::TestMysqlUpdateSelfRef::test_self_ref_wrapped_for_mysql
CREATE TABLE t (id NUMBER, n NUMBER);
UPDATE t SET n=(SELECT MAX(n) FROM t x WHERE x.id<t.id)
-- MySQL:
UPDATE t
SET n = (SELECT MAX(n)
FROM (SELECT *
FROM t) x
WHERE x.id < t.id);

-- Live-verified (seed t(1,NULL) (2,10) (3,20)): MySQL lands the same rows as
-- running the original statement directly on Oracle/PostgreSQL, which allow
-- the self-reference natively — (1,NULL) (2,10) (3,20).
```

The same wrap applies when the self-reference is in the `WHERE` clause
instead of `SET` — including when the inner subquery joins the self-reference
to another table:

```sql
-- pinning test: test_challenge.py::TestMysqlUpdateSelfRef::test_self_ref_in_where_in_subquery_wrapped
CREATE TABLE t (id NUMBER, k NUMBER, flag NUMBER);
CREATE TABLE s (k NUMBER);
UPDATE t SET flag=0
WHERE flag=1 AND id IN (SELECT x.id FROM t x INNER JOIN s ON s.k=x.k WHERE x.flag=1)
-- MySQL:
UPDATE t
SET flag = 0
WHERE flag = 1 AND id IN (SELECT x.id
FROM (SELECT *
FROM t) x
INNER JOIN s ON s.k = x.k
WHERE x.flag = 1);
```

A `DELETE` gets the identical wrap on its `WHERE` clause, an `EXISTS`
predicate is handled the same way as `IN`, more than one self-reference in
the same statement is wrapped independently, and a self-reference with no
alias of its own gets a synthesized one (`uq_sr`, then `uq_sr2`, … for a
second occurrence) since nothing else in the statement can be pointing at it
by name. A subquery that reads a *different* table is left exactly as
written.

**Discussion.** MySQL's optimizer refuses to modify a table while a nested
subquery of the same statement is still reading it directly — the standard
workaround is to force that subquery to materialize into a temporary result
first, which breaks the direct read the restriction is checking for. Unique
reuses the source's own alias for the materialized copy, so every existing
qualified reference inside the subquery (`x.id`, `x.flag`, …) keeps resolving
unchanged; only the alias-less case needs a synthesized name. Every other
engine allows the self-reference outright, so the wrap is MySQL-only — going
the other way, or between any two non-MySQL engines, the subquery is left
untouched.

> **Note** faithful — live-verified on all four shapes above (`SET` scalar,
> `WHERE IN`, `WHERE EXISTS`, `DELETE`): the wrapped MySQL statement lands the
> identical final row set as the same statement run directly on an engine
> that allows the self-reference, for every seed used in the pinning tests.

**See Also.** [`TestMysqlUpdateSelfRef`](../../../tests/integration/test_challenge.py)
· corpus cases `ora-upd-correlated`, `ora-upd-selfref-where`
([`challenge_oracle.sql`](../../../tests/fixtures/challenge/challenge_oracle.sql))
· [`test_procedures_fe_live.py`](../../../tests/integration/test_procedures_fe_live.py)
(`proc_26`, the same wrap inside a routine body).
