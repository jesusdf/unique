[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Boolean-column predicates re-spelled for engines with no boolean type" direction="postgresql → tsql/oracle" kind=article order=6 -->

# `flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle

**Problem.** PostgreSQL's `IS TRUE`/`IS FALSE`/`IS NOT TRUE`/`IS NOT FALSE`
predicate accepts `TRUE`/`FALSE`/`NULL`/`UNKNOWN` as its right-hand side —
never an integer. A boolean *column* mapped to `BIT` (T-SQL) or `NUMBER(1)`
(Oracle) has to keep the predicate spelling valid: `flag IS 1` is T-SQL
error 156 / Oracle `ORA-00908`.

**Solution.**

```sql
-- tests/integration/test_challenge.py::TestBoolColumnIsPredicate::test_is_true_becomes_value_comparison
-- corpus case red2-pg-boolcol-is-true (challenge_postgresql.sql)
SELECT a FROM t WHERE flag IS TRUE
-- transpiles to (postgresql -> tsql):
SELECT a
FROM t
WHERE flag = 1
```

```sql
-- tests/integration/test_challenge.py::TestBoolColumnIsPredicate::test_is_false_and_negations (postgresql -> tsql)
SELECT a FROM t WHERE flag IS NOT TRUE
-- transpiles to:
SELECT a
FROM t
WHERE (flag <> 1 OR flag IS NULL)
```

MySQL keeps the native predicate unchanged
(`TestBoolColumnIsPredicate::test_mysql_keeps_native_boolean`: `WHERE flag
IS TRUE` stays `WHERE flag IS TRUE;` — MySQL has a real boolean type, so
nothing needs rewriting there).

**Discussion.** `flag = 1` (`IS TRUE`) and `flag = 0` (`IS FALSE`) are exact
substitutions — a boolean column is never anything but `TRUE`/`FALSE`/`NULL`
on the source, and equality against `1`/`0` reproduces the same three
outcomes (a `NULL` column fails both `= 1` and `= 0`, exactly like it fails
both `IS TRUE` and `IS FALSE`). The negated forms need the extra `OR flag IS
NULL` leg specifically *because* `IS NOT TRUE`/`IS NOT FALSE` are defined to
also catch the `NULL` case (`NULL IS NOT TRUE` is `TRUE`), which a plain
`<>` comparison would miss (`NULL <> 1` is `UNKNOWN`, not `TRUE`) — the same
"don't let `UNKNOWN` silently become the wrong answer" concern as the
tri-state `CASE`'s implicit `ELSE NULL`, just spelled as an explicit `OR ...
IS NULL` here because the whole thing must stay a `WHERE`-clause predicate.

> **Note** faithful — `assert_statements_parse` confirms the rewritten form
> parses on every target; the value-comparison spelling produces the same
> row set as the source `IS [NOT] TRUE/FALSE` predicate for every value of
> `flag` including `NULL`.

**See Also.** `tests/integration/test_challenge.py::TestBoolColumnIsPredicate` ·
corpus case `red2-pg-boolcol-is-true` (`tests/fixtures/challenge/challenge_postgresql.sql`).
