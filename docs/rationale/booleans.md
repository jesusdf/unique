# Booleans: the value/predicate duality

MySQL and PostgreSQL treat a comparison, an `AND`/`OR`, an `IS [NOT] NULL`, or
any other truthy expression as an ordinary **value**: it can sit in a SELECT
list, be assigned to a variable, or be returned from a function, and it
carries three possible outcomes — `TRUE` (1), `FALSE` (0), or `UNKNOWN`
(`NULL`). T-SQL has no boolean value type at all: a predicate may only appear
in `WHERE`/`ON`/`HAVING`/`CASE WHEN`. Oracle's *SQL* engine is the same —
except Oracle's *procedural* (PL/SQL) engine, which uniquely has a native
`BOOLEAN` type for variables and parameters, just not for anything that
crosses back into a SQL statement.

When a value crosses from an engine that has boolean-as-value into one that
doesn't, Unique reproduces the exact three-state semantics with a **tri-state
CASE**:

```sql
CASE WHEN <predicate> THEN 1 WHEN <negated predicate> THEN 0 END
```

There is no `ELSE` — that's deliberate. If the predicate itself is `UNKNOWN`
(a comparison against `NULL`), neither `WHEN` arm matches and the `CASE`
falls through to the implicit `ELSE NULL`, exactly reproducing the source's
third state. Spelling it `ELSE 0` instead would silently turn an `UNKNOWN`
into a `FALSE` — the classic three-valued-logic bug.

The reverse also happens: a numeric/bit value used where the target grammar
demands a genuine predicate or boolean expression (an Oracle PL/SQL
`BOOLEAN` context, a `WHERE`/`IF` condition inherited unchanged from a source
engine that treats `0`/non-`0` as false/true) gets a `<> 0` comparison
synthesized, since "truthy" and "non-zero" are the same idea numerically but
the target's grammar wants an actual boolean-shaped expression there.

See [`03-unsupported.md` §3.18](../03-unsupported.md#318-not-of-a-non-predicate-on-t-sql-no-boolean-value-type)
for the one case this mechanism does **not** resolve — `NOT` applied directly
to a bare literal nested inside another boolean operation, which still
degrades to a documented carrier.

## Value position: booleans wrapped for engines with no boolean value

### Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle

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

**Discussion.** `EXISTS` gets the simpler `ELSE 0` spelling
(`_emit_value_expression` in `src/unique/core/converter/emit.py`, which
documents the whole mechanism inline: *"predicates become tri-state
values… `CASE WHEN p THEN 1 WHEN not-p THEN 0 END` reproduces the tri-state
exactly (ELSE NULL implicit)"*) because `EXISTS` never evaluates to
`UNKNOWN` — there is no third state to preserve. `IS NULL`/`IS NOT NULL` are
logically two-valued for the same reason, but as probed above they are
actually spelled with the two-`WHEN` form rather than `ELSE 0` — harmless,
since the `WHEN`/negated-`WHEN` pair is already exhaustive for these
operators, but worth knowing the emitted shape doesn't always match the
"two-valued → `ELSE 0`" rule the source comment states for that family; see
the discrepancy note at the end of this page.

> **Note** faithful — the `CASE` reproduces the exact set of values the
> source engine would have produced (including `NULL` for an `UNKNOWN`
> comparison); no warning is raised because nothing is lost.

**See Also.** `tests/integration/test_pg_source_wave1.py::TestSelectListComparisonsWrap`,
`::TestBooleanOpInSelectList`, `::TestUnaryPredicateInSelectList` ·
[03-unsupported.md §3.18](../03-unsupported.md#318-not-of-a-non-predicate-on-t-sql-no-boolean-value-type).

### `NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle

**Problem.** The same duality inside procedural bodies: `SET done = NOT
done` (MySQL) or `RETURN <predicate>` from a function declared to return a
boolean assigns/returns a value, not a predicate. A `NUMBER`/`INT`-typed
variable or a T-SQL function mapped to `RETURNS BIT` has no `NOT`-of-a-value
operator to reuse.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_not_value_wraps_tristate_on_oracle (mysql -> oracle)
DELIMITER //
create procedure p2() begin
  declare done int default 0;
  set done = not done;
end//
DELIMITER ;
-- transpiles to:
CREATE PROCEDURE p2
IS
    done NUMBER(10) := 0;
BEGIN
    done := CASE WHEN done = 0 THEN 1 WHEN done <> 0 THEN 0 END;
END;
/
```

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushZ4bBatch::test_predicate_return_wraps_for_bit (postgresql -> tsql)
create function dc(val int) returns boolean language plpgsql as
  $$ begin return val > 0; end $$;
-- transpiles to:
CREATE FUNCTION dc
(
    @val int
)
RETURNS BIT
AS
BEGIN
    RETURN CASE WHEN @val > 0 THEN 1 WHEN NOT (@val > 0) THEN 0 END;
END
```

**Discussion.** Same tri-state `CASE`, same reason (`done`/`val`'s
comparison could legitimately be `NULL`-valued for a different input), just
applied at an assignment or `RETURN` slot instead of a SELECT-list
projection. `NOT` itself is never emitted as a value-position operator on
these targets (`src/unique/core/procedural/transformer/base.py`: *"tri-state
CASE preserves NULL"*; `src/unique/core/converter/emit_expr.py`: *"NOT is
not a value expression on T-SQL — wrap tri-state"*).

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle`,
`::TestZeroPushZ4bBatch`.

### Oracle PL/SQL `BOOLEAN` variables and parameters keep native `NOT` (handled)

**Problem.** Oracle's exception to its own "SQL has no boolean value" rule:
a PL/SQL variable or parameter declared `BOOLEAN` **is** a first-class value
inside procedural code — just not inside a SQL statement issued from that
same block. A `NOT` of a `BOOLEAN`-typed operand should not get the
tri-state wrap the previous entry uses for `NUMBER`/`INT` operands; that
would be a needless (and needlessly verbose) rewrite of something Oracle
already accepts natively.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_pg_boolean_not_stays_on_oracle (postgresql -> oracle)
create function f() returns boolean language plpgsql as $$
declare b boolean := true;
begin
  b := not b;
  return b;
end $$;
-- transpiles to:
CREATE OR REPLACE FUNCTION f
RETURN boolean
IS
    b boolean := 1;
BEGIN
    b := NOT b;
    RETURN b;
END;
/
```

**Discussion.** `b := NOT b;` stays exactly as written — no `CASE`, because
`b`'s declared type is `BOOLEAN`, and the whole mechanism is keyed off the
*operand's type*, not off "which engine": it is not "`NOT` is banned on
Oracle", it is "`NOT` of a `NUMBER`-typed value is not a value expression in
Oracle SQL", and a PL/SQL `BOOLEAN` variable sidesteps that because the
PL/SQL grammar (unlike the SQL grammar) allows it.

> **Discrepancy noticed while probing (not part of this mechanism):** the
> same output's `b boolean := 1;` initializer — the source's `TRUE` literal
> folded to the integer `1` even though the declared type is `BOOLEAN` — is
> **invalid live Oracle** (`PLS-00382: expression is of wrong type`,
> confirmed against `oracle://system:***@localhost:1521/FREEPDB1`). This is
> a distinct literal-typing bug in the `TRUE`/`FALSE` constant-folding path,
> unrelated to the value/predicate duality this page documents — reported
> here rather than silently presented as working, not fixed (docs-only
> brief).

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushMysqlOracle::test_pg_boolean_not_stays_on_oracle`.

## Predicate position: the reverse direction

### A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle

**Problem.** MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a
condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN`
return type demands an actual boolean expression, not a `NUMBER`. Shipped
raw, the target either silently accepts a nonsensical condition or rejects
the type mismatch outright.

**Solution.**

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW1Batch::test_bare_numeric_where_gets_comparison (mysql -> tsql)
UPDATE v1 SET b = 0 WHERE 0;
-- transpiles to:
UPDATE v1
SET b = 0
WHERE 0 <> 0
```

```sql
-- tests/unit/core/test_ir_first_families.py::TestZeroPushW7Batch::test_numeric_return_wrapped_for_bool_type_oracle (postgresql -> oracle)
create function bk() returns bool as
  $$ begin return 1; end $$ language plpgsql;
-- transpiles to:
CREATE OR REPLACE FUNCTION bk
RETURN bool
AS
BEGIN
    RETURN (1 <> 0);
END;
/
```

**Discussion.** `<> 0` is the mirror image of the value-position wrap: a
bare numeric literal is only ever `TRUE` (non-zero) or `FALSE` (zero) — it
is never `UNKNOWN` unless it is itself `NULL` — so a plain comparison
(rather than a `CASE`) is enough to synthesize a genuine predicate/boolean
from it. `RETURN bool` (not `RETURN BOOLEAN`) live-compiles on Oracle in
this example — verified against the same live instance above — so the
type-name spelling itself is not a defect worth flagging.

> **Note** faithful — `0`/non-`0` truthiness and `<> 0`/`= 0` comparisons
> agree on every value including `NULL` (both stay `NULL`/`UNKNOWN`).

**See Also.** `tests/unit/core/test_ir_first_families.py::TestZeroPushW1Batch::test_bare_numeric_where_gets_comparison`,
`::TestZeroPushW7Batch::test_numeric_return_wrapped_for_bool_type_oracle`.

### A value-wrapped predicate compared again in predicate position collapses back to the predicate (MySQL) → T-SQL

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

## Boolean-column predicates re-spelled for engines with no boolean type

### `flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle

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

## Null-safe equality: `IS [NOT] DISTINCT FROM` has no target operator

### `IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`

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
bare `CASE` (`src/unique/core/converter/emit.py`, `_emit_select_list_item`,
around line 1133), the condition emitter keeps the bare `EXISTS`/`NOT
EXISTS` predicate (`emit.py`, `_emit_condition`, around line 1497) — so the
intermediate value-shaped spelling never actually reaches SQL output; both
forms probed above are exactly what a caller sees.

This is a **different mechanism** from the `IS DISTINCT FROM` spelling
already documented in
[procedural.md's Triggers section](procedural.md#oracle-event-predicates-insertingdeletingupdatingcol--per-engine-rewrite):
that one is a predicate Unique itself synthesizes to restate Oracle's
`UPDATING('col')` trigger predicate. This entry is the general-purpose
operator, written directly in source SQL and read on its own.

> **Note** faithful — `EXISTS (SELECT a INTERSECT SELECT b)` and MySQL's
> `<=>` both agree with PostgreSQL's `IS NOT DISTINCT FROM` for every
> combination of values including `NULL`; the negated forms
> (`IS DISTINCT FROM`, `NOT (... <=> ...)`, `NOT EXISTS (...)`) are the
> exact logical complement.

**See Also.** `tests/integration/test_pg_source_wave1.py::TestNullSafeComparison`,
`::TestNullsafeValuePosition`,
`::TestUserVarsRowTuplesOracleDouble::test_row_tuple_intersect_unpacks`.
