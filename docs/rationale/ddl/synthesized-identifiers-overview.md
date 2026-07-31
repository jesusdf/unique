[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Synthesized identifiers for anonymous constructs" direction="—" kind=overview order=14 -->

# Synthesized identifiers for anonymous constructs

T-SQL requires a name in two places where PostgreSQL/MySQL/Oracle happily
accept an anonymous construct: every derived-table column must have one
(error 8155), and — outside DDL proper but pinned by the same "T-SQL
requires a name" family — every index does too. Unique synthesizes a
deterministic name in both cases rather than erroring or dropping the
construct.
