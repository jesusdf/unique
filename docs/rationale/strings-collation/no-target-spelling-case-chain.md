[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Lookup functions with no target spelling" direction="mysql/oracle → all" kind=article order=26 -->

# Functions with no target spelling: MySQL `ELT`/`FIELD`, Oracle `NVL2` → a synthesized `CASE`

**Problem.** MySQL's `ELT(n, v1, v2, ...)` (pick the `n`th value) and
`FIELD(v, v1, v2, ...)` (find `v`'s 1-based position among the rest, `0` if
absent) have no equivalent built-in on any other engine. Oracle's
`NVL2(expr, value_if_not_null, value_if_null)` similarly has no built-in
match outside Oracle — PostgreSQL, T-SQL, and MySQL all have `NVL`-style
two-argument null coalescing, but none has this three-argument "branch on
nullness" form as a single function.

**Solution.** Each decomposes into a `CASE` that reproduces the same
lookup or branch:

```sql
-- tests/integration/test_rc1a_mappings.py::test_elt_and_field_to_case_chains
SELECT ELT(2, 'a', 'b', 'c') AS r
-- mysql -> postgresql / tsql / oracle:
SELECT CASE 2 WHEN 1 THEN 'a' WHEN 2 THEN 'b' WHEN 3 THEN 'c' END AS r;

SELECT FIELD('b', 'a', 'b') AS r
-- mysql -> postgresql / tsql / oracle:
SELECT CASE 'b' WHEN 'a' THEN 1 WHEN 'b' THEN 2 ELSE 0 END AS r;

-- tests/unit/core/test_function_mappings.py::TestNullFunctions::test_nvl2_to_case
SELECT NVL2(x, 1, 0) AS r FROM t
-- oracle -> postgresql / tsql / mysql:
SELECT CASE WHEN x IS NOT NULL THEN 1 ELSE 0 END AS r FROM t
```

**Discussion.** `ELT`'s `CASE <n> WHEN 1 THEN v1 WHEN 2 THEN v2 ...` chain
reproduces the positional lookup directly, with no `ELSE` — `ELT` with an
out-of-range index returns `NULL` on MySQL, which the chain reproduces
naturally by simply having no matching branch. `FIELD`'s chain is the
inverse lookup (searching by value instead of by index) and *does* need an
`ELSE 0`, matching `FIELD`'s own "not found" contract. `NVL2` collapses to
the plainest possible `CASE WHEN expr IS NOT NULL THEN ... ELSE ... END` —
there's no lookup involved, just a null test standing in for the function
call.

> **Note** faithful — every rewrite reproduces the source function's exact
> value for every input, including the edge cases (`ELT` out-of-range →
> `NULL`, `FIELD` not-found → `0`). No warning.

**See Also.** [`test_rc1a_mappings.py::test_elt_and_field_to_case_chains`](../../../tests/integration/test_rc1a_mappings.py) ·
`test_challenge_assertions_mysql.py` (`my-elt`, `my-field`, `my-index-fns`) ·
[`test_function_mappings.py::TestNullFunctions`](../../../tests/unit/core/test_function_mappings.py)
(`test_nvl2_to_case`).
