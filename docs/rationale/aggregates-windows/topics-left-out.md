[← Aggregates and window functions](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=aggregates-windows type="Topics left out for lack of source support" direction="—" kind=overview order=15 -->

# Topics left out for lack of source support

- **CI-DISTINCT collation carrier inside the `GROUP_CONCAT`/`STRING_AGG`
  family specifically** — the corpus has a general case-insensitive-collation
  carrier for `DISTINCT`/`ORDER BY` (`my-distinct-case`,
  `docs/03-unsupported.md` §3.14), but no case combining it with a string
  aggregate's own `DISTINCT`/`ORDER BY` clause, so no dedicated entry is made
  here to avoid inventing an example.
