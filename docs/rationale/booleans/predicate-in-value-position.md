[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Value position: booleans wrapped for engines with no boolean value" direction="postgresql/mysql → tsql/oracle" kind=article order=1 -->

# Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle

**Problem.** A comparison, boolean combinator, or null-test used as an
ordinary value — `SELECT (a > b) AS c`, `SELECT (b1 AND a3) AS b3`,
`SELECT (id IS NOT NULL) AS a3` — is legal on MySQL/PostgreSQL (comparisons
and booleans are 1/0/NULL values there). Shipped unchanged to T-SQL or
Oracle it is a predicate in a place that requires an expression (T-SQL
errors 102/4145 depending on the shape, the analogous Oracle parse error).

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestSelectListComparisonsWrap::test_comparison_wraps_tsql (mysql -> tsql)
select cast('2007-10-09' as date) > '2007-10-01' as c;
-- transpiles to:
SELECT CASE WHEN CAST('2007-10-09' AS DATE) > '2007-10-01' THEN 1 WHEN CAST('2007-10-09' AS DATE) <= '2007-10-01' THEN 0 END AS c
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestBooleanOpInSelectList::test_and_in_select_list_tsql (postgresql -> tsql)
select (b1 and a3) as b3 from t;
-- transpiles to:
SELECT CASE WHEN b1 <> 0 AND a3 <> 0 THEN 1 WHEN NOT (b1 <> 0 AND a3 <> 0) THEN 0 END AS b3
FROM t
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestUnaryPredicateInSelectList::test_is_not_null_value_tsql (postgresql -> tsql)
select (id is not null) as a3 from t;
-- transpiles to:
SELECT CASE WHEN NOT (id IS NULL) THEN 1 WHEN NOT (NOT (id IS NULL)) THEN 0 END AS a3
FROM t
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestUnaryPredicateInSelectList::test_exists_value_oracle (postgresql -> oracle)
select exists(select 1 from u) as e from t;
-- transpiles to:
SELECT CASE WHEN EXISTS (SELECT 1 FROM u) THEN 1 ELSE 0 END AS e
FROM t;
```

The position matters, not just the expression: the same comparison in a
`WHERE` clause (`select 1 from t where a > b;`, `TestSelectListComparisonsWrap
::test_condition_position_untouched`) transpiles untouched — no `CASE`
appears because it is already a predicate there. And on a target that *does*
have boolean-as-value, nothing wraps at all
(`TestSelectListComparisonsWrap::test_pg_target_keeps_boolean_value`:
`select a > b as c from t;` mysql → postgresql stays `SELECT a > b AS c`).

**Discussion.** `EXISTS` gets the simpler `ELSE 0` spelling because it never
evaluates to `UNKNOWN` — there is no third state to preserve. `IS
NULL`/`IS NOT NULL` are also logically two-valued for the same reason, but
are spelled with the two-`WHEN` form instead: the `WHEN`/negated-`WHEN` pair
is already exhaustive for these operators, so the result is identical
either way.

> **Note** faithful — the `CASE` reproduces the exact set of values the
> source engine would have produced (including `NULL` for an `UNKNOWN`
> comparison); no warning is raised because nothing is lost.

**See Also.** `tests/integration/test_pg_source_wave1.py::TestSelectListComparisonsWrap`,
`::TestBooleanOpInSelectList`, `::TestUnaryPredicateInSelectList` ·
[03-unsupported.md §3.18](../../03-unsupported.md#318-not-of-a-non-predicate-on-t-sql-no-boolean-value-type).
