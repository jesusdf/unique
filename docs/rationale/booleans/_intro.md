
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
