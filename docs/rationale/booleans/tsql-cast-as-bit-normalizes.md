[← Booleans: the value/predicate duality](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=booleans type="Value position: booleans wrapped for engines with no boolean value" direction="tsql → oracle" kind=article order=10 -->

# T-SQL `CAST(x AS BIT)` → Oracle `SIGN(ABS(x))`, not a plain type change

**Problem.** T-SQL's `CAST(x AS BIT)` is not a value-preserving type
change — it *normalizes* any numeric value to `0` or `1` (any non-zero
number becomes `1`, zero stays `0`, `NULL` stays `NULL`). A plain type-cast
translation on a target with no `BIT` type would instead just carry the
number through unchanged, silently losing the 0/1 normalization the source
cast performed.

**Solution.**

```sql
-- tests/unit/core/test_transformer.py::TestTypeMapper::test_bit_cast_normalizes_to_sign_abs
SELECT CAST(x AS BIT) AS r FROM t
-- tsql -> oracle:
SELECT SIGN(ABS(x)) AS r FROM t
```

**Discussion.** `SIGN(ABS(x))` reproduces the same normalization with two
composed built-ins Oracle already has: `ABS(x)` collapses any negative
value to positive (so `-5` and `5` normalize the same way `CAST(... AS
BIT)` would), and `SIGN(...)` of a non-negative number is `0` for zero and
`1` for anything positive — exactly `BIT`'s own 0/1 range, with `NULL`
propagating through both functions unchanged. This is a narrower,
type-mapper-level case of the same "0/1 normalization" idea this project's
booleans pages document for value/predicate duality generally, triggered
specifically by a `CAST ... AS BIT` rather than a comparison or a
tri-state `CASE` source shape.

> **Note** faithful — live-verified `SIGN(ABS(-5)) = 1`, `SIGN(ABS(0)) =
> 0`, matching `CAST(-5 AS BIT) = 1`, `CAST(0 AS BIT) = 0` on T-SQL. No
> warning.

**See Also.** [`test_transformer.py::TestTypeMapper`](../../../tests/unit/core/test_transformer.py)
(`test_bit_cast_normalizes_to_sign_abs`).
