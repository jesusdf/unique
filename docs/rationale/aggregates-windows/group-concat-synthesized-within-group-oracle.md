[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="`GROUP_CONCAT` / `STRING_AGG` / `LISTAGG` family" direction="mysql → oracle" kind=article order=18 -->

# An unordered MySQL `GROUP_CONCAT` → Oracle `LISTAGG` gains a synthesized `WITHIN GROUP (ORDER BY <arg>)`

**Problem.** MySQL's `GROUP_CONCAT(expr SEPARATOR sep)` needs no ordering
clause — an unordered call is valid MySQL, with whatever order the engine
happens to produce. Oracle's `LISTAGG` requires a `WITHIN GROUP (ORDER BY
...)` clause syntactically; `LISTAGG(expr, sep)` with no `WITHIN GROUP` at
all is a parse error (`ORA-30482`).

**Solution.**

```sql
-- tests/unit/core/test_ilike_groupconcat.py::TestStringAggregation::test_group_concat_to_oracle_listagg
SELECT GROUP_CONCAT(name SEPARATOR '; ') FROM t
-- mysql -> oracle:
SELECT LISTAGG(name, '; ') WITHIN GROUP (ORDER BY name) FROM t
```

**Discussion.** Rather than invent an arbitrary ordering, Unique reuses the
aggregate's own argument expression (`name`) as the `ORDER BY` key —
producing a *deterministic* result (unlike MySQL's own engine-dependent
order) while changing nothing about which values end up concatenated,
since the argument itself was already going to be part of the output
either way. This is the minimum synthesis Oracle's grammar requires, not
an attempt to reproduce MySQL's particular (and unspecified) internal
ordering.

> **Note** faithful in the sense that the same set of values is
> concatenated with the same separator; the exact *order* becomes
> deterministic (sorted by the concatenated value itself) rather than
> reproducing MySQL's own unspecified order, since MySQL's `GROUP_CONCAT`
> makes no ordering guarantee to preserve in the first place. No warning.

**See Also.** [`test_ilike_groupconcat.py::TestStringAggregation`](../../../tests/unit/core/test_ilike_groupconcat.py)
(`test_group_concat_to_oracle_listagg`) · [`DISTINCT` + numeric `ORDER BY`
restructure (MySQL) → PostgreSQL](distinct-numeric-order-by.md) (a sibling
`GROUP_CONCAT` ordering entry, for a different target and a different
source ordering shape).
