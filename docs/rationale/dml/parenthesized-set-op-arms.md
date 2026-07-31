[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Parenthesized-structure unwrapping and shielding" direction="cross-engine" kind=article order=21 direction-inferred=true -->

# Parenthesized set-operation arms unwrap; an arm's own `ORDER BY`/`LIMIT` is shielded

**Problem.** `(SELECT …) UNION ALL (SELECT …)` parenthesizes each arm of a
set operation — often just for readability, but sometimes because one arm
carries its own `ORDER BY`/`LIMIT` that must apply to *that arm alone*, not
to the combined result.

**Solution.**

```sql
-- pinning tests: test_pg_source_wave1.py::TestParenthesizedUnionArms
(select * from t1) union all (select * from t2);
-- PostgreSQL:
SELECT * FROM t1 UNION ALL SELECT * FROM t2;   -- (parens just dropped)

select a from t1 union all (select a from t2 order by a limit 1);
-- PostgreSQL:
SELECT a FROM t1
UNION ALL
SELECT * FROM (SELECT a FROM t2 ORDER BY a ASC NULLS FIRST LIMIT 1) uq_setarm;

(select a from t1 limit 2) union all (select a from t2) order by a;
-- PostgreSQL:
SELECT * FROM (SELECT a FROM t1 LIMIT 2) uq_setarm
UNION ALL
SELECT a FROM t2
ORDER BY a ASC NULLS FIRST;
```

Live-verified (`t1(3,1)`, `t2(9,2,5)`): the shielded-second-arm example
returns `(3),(1),(2)` — `t2`'s contribution is exactly its single smallest
row, proving the `ORDER BY … LIMIT 1` scoped to that arm alone rather than
to the whole union.

A parenthesized arm with **no** `ORDER BY`/`LIMIT` of its own just has its
parentheses dropped. An arm that does carry one gets wrapped in a
synthesized derived table (`uq_setarm`) instead, and the set operation's own
trailing `ORDER BY`/`LIMIT`, if any, still attaches to the combined result
as normal.

**Discussion.** A parenthesized arm arrives from sqlglot as a `Subquery`
wrapping a `Select`; the earlier converter read that wrapper as an empty
select, shipping `SELECT * UNION ALL SELECT *` with the arm's own `FROM`
and columns dropped entirely. The fix unwraps the arm's real `FROM`/columns
— but a plain unwrap is not always safe: an arm's own `ORDER BY`/`LIMIT`,
once unparenthesized, would bind to the **whole** set operation rather than
to the arm it belongs to (true on every target: a trailing `ORDER BY`/
`LIMIT` after the last arm of a `UNION`/`EXCEPT`/`INTERSECT` always scopes
to the combined result, never to one arm). So an arm carrying one of those
clauses is wrapped in a derived table instead of unwrapped bare, keeping
its original per-arm scope.

> **Note** faithful — live-verified above.

**See Also.** [`test_pg_source_wave1.py::TestParenthesizedUnionArms`](../../../tests/integration/test_pg_source_wave1.py)
· "`ORDER BY` inside a joined derived table" entry above (a sibling
shielding mechanism, different trigger).
