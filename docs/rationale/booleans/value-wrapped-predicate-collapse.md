[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Predicate position: the reverse direction" direction="mysql → tsql" kind=article order=5 -->

# A value-wrapped predicate compared again in predicate position collapses back to the predicate (MySQL) → T-SQL

**Problem.** MySQL lets you compare a boolean value against `1`/`0`, or test
it with `IS TRUE`, even when that value is itself already a predicate:
`WHERE (c2 IS NOT NULL) = 1`. sqlglot spells `IS NOT NULL` as `NOT (IS
NULL)`, so the naive round trip would wrap the inner predicate into a value
(tri-state `CASE`) and then re-wrap *that* into `<> 0`/`= 1` for the outer
comparison — technically correct, but needlessly indirect for something
that is already a bare predicate underneath.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestWave169NotNullParenCompare::test_isnotnull_eq_one (mysql -> tsql)
SELECT * FROM t1 LEFT JOIN t2 ON c1=c2 WHERE (c2 IS NOT NULL) = 1;
-- transpiles to:
SELECT *
FROM t1
LEFT JOIN t2 ON c1 = c2
WHERE NOT (c2 IS NULL)
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestWave169NotNullParenCompare::test_isnotnull_eq_zero (mysql -> tsql)
SELECT * FROM t1 LEFT JOIN t2 ON c1=c2 WHERE (c2 IS NOT NULL) = 0;
-- transpiles to:
SELECT *
FROM t1
LEFT JOIN t2 ON c1 = c2
WHERE NOT (NOT (c2 IS NULL))
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestWave169NotNullParenCompare::test_isnotnull_is_true (mysql -> tsql)
SELECT * FROM t1 LEFT JOIN t2 ON c1=c2 WHERE (c2 IS NOT NULL) IS TRUE;
-- transpiles to:
SELECT *
FROM t1
LEFT JOIN t2 ON c1 = c2
WHERE NOT (c2 IS NULL)
```

**Discussion.** Since the whole expression is still inside a `WHERE`
(predicate position) both before and after the `= 1`/`= 0`/`IS TRUE` test,
Unique's `BinaryOp`-left guard recognizes the "value-of-a-predicate compared
back to a constant" shape and unwraps it directly to the predicate itself
(negating it for the `= 0` case) instead of round-tripping it through a
`CASE`. This is the same recognition step the boolean-column entry below
reuses for `IS TRUE`/`IS FALSE`.

> **Note** faithful — `(p) = 1` and `p` agree for every value of `p`
> (including `NULL`, where `(p) = 1` is itself `NULL`/`UNKNOWN`, same as a
> bare `p`); `(p) = 0` and `NOT p` agree the same way.

**See Also.** `tests/integration/test_pg_source_wave1.py::TestWave169NotNullParenCompare`.
