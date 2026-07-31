[← All rationale topics](../README.md)

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

See [`03-unsupported.md` §3.18](../../03-unsupported.md#318-not-of-a-non-predicate-on-t-sql-no-boolean-value-type)
for the one case this mechanism does **not** resolve — `NOT` applied directly
to a bare literal nested inside another boolean operation, which still
degrades to a documented carrier.

> **Generated file — do not edit by hand.** Produced by `python scripts/generate_rationale_index.py` from the article pages in this directory; the intro above comes from `_intro.md`. The CI freshness gate (`python scripts/generate_rationale_index.py --check`) fails the build if it drifts.

## Value position: booleans wrapped for engines with no boolean value

| Article | Direction | Description |
|---|---|---|
| [Comparisons, `AND`/`OR`, `IS [NOT] NULL`, `EXISTS` in a SELECT-list value position (MySQL, PostgreSQL) → T-SQL, Oracle](predicate-in-value-position.md) | postgresql/mysql → tsql/oracle | A comparison, boolean combinator, or null-test used as an ordinary value — `SELECT (a > b) AS c`, `SELECT (b1 AND a3) AS b3`, `SELECT (id IS NOT NULL) AS a3` — is legal on MySQL/PostgreSQL (comparisons and booleans are 1/0/NULL values there). |
| [`NOT` of a truthy variable, assignment, or function `RETURN` (MySQL, PostgreSQL) → T-SQL, Oracle](not-of-truthy-value.md) | postgresql/mysql → tsql/oracle | The same duality inside procedural bodies: `SET done = NOT done` (MySQL) or `RETURN <predicate>` from a function declared to return a boolean assigns/returns a value, not a predicate. |
| [Oracle PL/SQL `BOOLEAN` variables and parameters keep native `NOT` (handled)](oracle-plsql-native-boolean.md) | oracle | Oracle's exception to its own "SQL has no boolean value" rule: a PL/SQL variable or parameter declared `BOOLEAN` **is** a first-class value inside procedural code — just not inside a SQL statement issued from that same block. |
| [Boolean-to-text/char rendering (PostgreSQL `::text` / MySQL `CAST(... AS CHAR)`)](boolean-to-text-rendering.md) | postgresql/mysql → mysql/postgresql | PostgreSQL renders a boolean cast to text as the words `'true'`/`'false'`; MySQL has no boolean text representation at all — its booleans are ordinary integers, so casting one to a character type gives `'1'`/`'0'` instead. |

## Predicate position: the reverse direction

| Article | Direction | Description |
|---|---|---|
| [A numeric/bit value where a genuine predicate or boolean is required (MySQL, PostgreSQL) → T-SQL, Oracle](value-in-predicate-position.md) | postgresql/mysql → tsql/oracle | MySQL/PostgreSQL treat `0`/non-`0` as false/true anywhere a condition is expected (`WHERE 0` never matches); Oracle PL/SQL's `BOOLEAN` return type demands an actual boolean expression, not a `NUMBER`. |
| [A value-wrapped predicate compared again in predicate position collapses back to the predicate (MySQL) → T-SQL](value-wrapped-predicate-collapse.md) | mysql → tsql | MySQL lets you compare a boolean value against `1`/`0`, or test it with `IS TRUE`, even when that value is itself already a predicate: `WHERE (c2 IS NOT NULL) = 1`. |

## Boolean-column predicates re-spelled for engines with no boolean type

| Article | Direction | Description |
|---|---|---|
| [`flag IS [NOT] TRUE/FALSE` on a boolean column (PostgreSQL) → T-SQL, Oracle](boolean-column-is-true-false.md) | postgresql → tsql/oracle | PostgreSQL's `IS TRUE`/`IS FALSE`/`IS NOT TRUE`/`IS NOT FALSE` predicate accepts `TRUE`/`FALSE`/`NULL`/`UNKNOWN` as its right-hand side — never an integer. |

## Null-safe equality: `IS [NOT] DISTINCT FROM` has no target operator

| Article | Direction | Description |
|---|---|---|
| [`IS [NOT] DISTINCT FROM` (PostgreSQL null-safe comparison) → MySQL `<=>` / T-SQL, Oracle `EXISTS`/`INTERSECT`](is-distinct-from.md) | postgresql → tsql/oracle/mysql | PostgreSQL's `IS [NOT] DISTINCT FROM` is a null-safe equality: unlike `=`, it never itself evaluates to `UNKNOWN` — `NULL IS NOT DISTINCT FROM NULL` is `TRUE`, `1 IS DISTINCT FROM NULL` is `TRUE`. |
