[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Foreign-key referential actions" direction="tsql/postgresql/mysql → oracle" kind=article order=9 -->

# `ON UPDATE <action>` (PostgreSQL / T-SQL / MySQL) → Oracle

**Problem.** `REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE`
propagates both a delete and a primary-key update on the parent to the
child.

**Solution.**

```sql
-- corpus case reda-ts-fk-on-update
CREATE TABLE c (id INT PRIMARY KEY, pid INT REFERENCES p(id) ON DELETE CASCADE ON UPDATE CASCADE)
-- MySQL/PostgreSQL: ... FOREIGN KEY (pid) REFERENCES p (id) ON DELETE CASCADE ON UPDATE CASCADE
-- Oracle: ON UPDATE CASCADE dropped, with a UNIQUE: carrier + warning
```

The `ON UPDATE` clause is stripped from the Oracle
`FOREIGN KEY`, with a `UNIQUE:` carrier + warning; the `ON DELETE` action and
the FK itself are kept. PostgreSQL and MySQL preserve `ON UPDATE` natively.

**Discussion.** Oracle foreign keys support **only** `ON
DELETE CASCADE`/`SET NULL` — there is no `ON UPDATE` referential action at
all (`ORA-00905` if attempted).

> **Warning** `[limit]` on Oracle — the cascade-on-parent-update
> behaviour is lost there and must be reproduced with a trigger if needed;
> faithful elsewhere. (An earlier version of this conversion dropped the
> clause on Oracle **silently**, with no warning — a real defect this closes.)

**See Also.** [`reda-ts-fk-on-update`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`pg-fk-onupdate-oracle`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[§2](../../03-unsupported.md) (FK `ON UPDATE` action → Oracle row) ·
[`UNIQUE-1148`](../../reference/warnings.md#unique-1148).
