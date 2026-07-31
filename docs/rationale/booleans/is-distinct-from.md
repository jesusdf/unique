[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Null-safe equality: `IS [NOT] DISTINCT FROM` has no target operator" direction="postgresql → tsql/oracle/mysql" kind=article order=7 -->

# `IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`

**Problem.** PostgreSQL's `IS [NOT] DISTINCT FROM` is a null-safe equality:
unlike `=`, it never itself evaluates to `UNKNOWN` — `NULL IS NOT DISTINCT
FROM NULL` is `TRUE`, `1 IS DISTINCT FROM NULL` is `TRUE`. No other target
spells an operator with that name; MySQL alone has a native null-safe
equality operator under a different spelling, and T-SQL/Oracle have none at
all.

**Solution.**

```sql
-- tests/integration/test_pg_source_wave1.py::TestNullSafeComparison::test_mysql_spaceship (postgresql -> mysql)
select 2 is not distinct from null as x;
-- transpiles to:
SELECT 2 <=> NULL AS x;

select 2 is distinct from 3 as x;
-- transpiles to:
SELECT NOT (2 <=> 3) AS x;
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestNullSafeComparison::test_tsql_condition_position_bare (postgresql -> tsql)
select 1 from t where a is distinct from b;
-- transpiles to:
SELECT 1
FROM t
WHERE NOT EXISTS (SELECT a INTERSECT SELECT b)
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestNullSafeComparison::test_tsql_intersect_form_value_position (postgresql -> tsql)
-- a predicate is not a value on T-SQL, so a SELECT-list use wraps:
select a is distinct from b from t;
-- transpiles to:
SELECT CASE WHEN NOT EXISTS (SELECT a INTERSECT SELECT b) THEN 1 ELSE 0 END
FROM t
```

```sql
-- tests/integration/test_pg_source_wave1.py::TestNullSafeComparison::test_oracle_intersect_form (postgresql -> oracle)
select a is not distinct from b from t;
-- transpiles to:
SELECT CASE WHEN EXISTS (SELECT a FROM DUAL INTERSECT SELECT b FROM DUAL) THEN 1 ELSE 0 END
FROM t;
```

A row-constructor operand (a parenthesized tuple, MySQL's own extension)
unpacks into the `SELECT` list's own items instead of shipping an illegal
parenthesized tuple:

```sql
-- tests/integration/test_pg_source_wave1.py::TestUserVarsRowTuplesOracleDouble::test_row_tuple_intersect_unpacks (mysql -> oracle)
select (1, 2) is distinct from (2, null) as x;
-- transpiles to:
SELECT CASE WHEN NOT EXISTS (SELECT 1, 2 FROM DUAL INTERSECT SELECT 2, NULL FROM DUAL) THEN 1 ELSE 0 END AS x
FROM DUAL;
```

PostgreSQL itself keeps the native operator unchanged
(`TestNullSafeComparison::test_pg_native`: `a IS DISTINCT FROM b` stays `a
IS DISTINCT FROM b`).

**Discussion.** MySQL's `<=>` ("spaceship", null-safe equal-to) is a direct
operator match — `IS DISTINCT FROM` just negates it. T-SQL and Oracle have
no null-safe comparison operator in any spelling, so Unique asks the same
question through `INTERSECT`, which every one of these engines already
defines with null-safe row-comparison semantics (`INTERSECT` matches `NULL`
to `NULL`): `EXISTS (SELECT a INTERSECT SELECT b)` is true exactly when `a`
and `b` are not-distinct, including the both-`NULL` case a plain `=` would
miss (`src/unique/core/converter/emit_expr.py`, the `NULLSAFE_EQ`/
`NULLSAFE_NEQ` branch of `_emit_binary`: *"T-SQL/Oracle use the version-safe
EXISTS-INTERSECT form (INTERSECT compares rows with null-safe semantics on
every engine)"*).

Unlike the tri-state `CASE` used for an ordinary comparison earlier on this
page, the value-position wrap here closes with an explicit `ELSE 0`, not an
implicit `ELSE NULL` — deliberately, since `IS [NOT] DISTINCT FROM` is
defined to *never* itself be `UNKNOWN` (that is the entire point of
"null-safe"), so the two-armed form is exact rather than merely
conservative. Internally the emitter builds one value-shaped form
(`CASE WHEN <pred> THEN 1 ELSE 0 END = 1`) and two separate call sites peel
it back down for their own position — the select-list emitter keeps the
bare `CASE` (`src/unique/core/converter/emit.py`, `_emit_value_expression`,
around line 1133), the condition emitter keeps the bare `EXISTS`/`NOT
EXISTS` predicate (`emit.py`, `_emit_condition`, around line 1497) — so the
intermediate value-shaped spelling never actually reaches SQL output; both
forms probed above are exactly what a caller sees.

This is a **different mechanism** from the `IS DISTINCT FROM` spelling
already documented in [procedural.md](../procedural/README.md)'s Triggers section,
under "Oracle event predicates (`INSERTING`/`DELETING`/`UPDATING('col')`) →
per-engine rewrite": that one is a predicate Unique itself synthesizes to
restate Oracle's `UPDATING('col')` trigger predicate. This entry is the
general-purpose operator, written directly in source SQL and read on its
own.

> **Note** faithful — `EXISTS (SELECT a INTERSECT SELECT b)` and MySQL's
> `<=>` both agree with PostgreSQL's `IS NOT DISTINCT FROM` for every
> combination of values including `NULL`; the negated forms
> (`IS DISTINCT FROM`, `NOT (... <=> ...)`, `NOT EXISTS (...)`) are the
> exact logical complement.

**See Also.** `tests/integration/test_pg_source_wave1.py::TestNullSafeComparison`,
`::TestNullsafeValuePosition`,
`::TestUserVarsRowTuplesOracleDouble::test_row_tuple_intersect_unpacks`.
