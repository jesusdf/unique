[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Topics left out for lack of source support" direction="—" kind=overview order=17 -->

# Topics left out for lack of source support

- **PostgreSQL `SET`-type MySQL columns** (unordered multi-value combination)
  degrade the same way `ENUM` does (to a `VARCHAR` wide enough for all
  values plus a documented note), but no challenge-corpus case exercises
  `SET` specifically, so no dedicated entry is made to avoid inventing an
  example.
