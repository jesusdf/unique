[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Foreign-key referential actions" direction="mysql → tsql" kind=article order=10 -->

# Self-referencing FK cascade (MySQL) → T-SQL

**Problem.** `FOREIGN KEY (mgr) REFERENCES emp(id) ON DELETE SET
NULL`, where the FK references its **own** table (an employee/manager
hierarchy).

**Solution.** The action is downgraded to `ON DELETE NO ACTION`
plus a warned note that the cascade must be emulated with an `AFTER`
trigger if the behaviour is required.

**Discussion.** T-SQL forbids a cascading action on a
self-referencing foreign key outright (error 1785 at `CREATE TABLE` time) —
this is a T-SQL engine restriction, not a missing-feature gap.

> **Warning** `[limit]` — approved degrade (the cascade
> behaviour is lost on T-SQL).

**See Also.** [`my-self-fk`](../../../tests/fixtures/challenge/challenge_mysql.sql) · [§3.22](../../03-unsupported.md) (annotated
inherent divergences) · [`UNIQUE-1054`](../../reference/warnings.md#unique-1054).
