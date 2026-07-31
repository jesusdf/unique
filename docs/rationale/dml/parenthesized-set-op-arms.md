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

**Discussion.** The parentheses around a set-operation arm are themselves
insignificant — dropping them changes nothing, since a plain arm has no
scope of its own to lose. An arm's own `ORDER BY`/`LIMIT` is different: on
every target, a trailing `ORDER BY`/`LIMIT` after the last arm of a
`UNION`/`EXCEPT`/`INTERSECT` always scopes to the *combined* result, never
to one arm alone, so simply dropping that arm's parentheses would move its
`ORDER BY`/`LIMIT` from applying to that one arm to applying to the whole
set operation instead. Wrapping such an arm in a derived table keeps its
`ORDER BY`/`LIMIT` scoped to that arm, exactly as the parentheses did in
the source.

> **Note** faithful — live-verified above.

**See Also.** [`test_pg_source_wave1.py::TestParenthesizedUnionArms`](../../../tests/integration/test_pg_source_wave1.py)
· "`ORDER BY` inside a joined derived table" entry above (a sibling
shielding mechanism, different trigger).
