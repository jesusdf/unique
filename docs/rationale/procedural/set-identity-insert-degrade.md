[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="`SET IDENTITY_INSERT` coherent degrade" direction="tsql → oracle/postgresql/mysql" kind=article order=3 -->

# `SET IDENTITY_INSERT t ON … INSERT … SET IDENTITY_INSERT t OFF` (T-SQL) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL requires `IDENTITY_INSERT` to be explicitly
turned `ON` before a script can supply its own value for an identity column,
then turned back `OFF`.

**Solution.**

```sql
-- corpus case reda-ts-identity-insert
CREATE TABLE t (id INT IDENTITY(1,1), v INT);
SET IDENTITY_INSERT t ON;
INSERT INTO t (id, v) VALUES (5, 10);
SET IDENTITY_INSERT t OFF
-- every target: both SET IDENTITY_INSERT statements become carriers (one
-- warning); INSERT INTO t (id, v) VALUES (5, 10) transpiles unchanged
```

Both `SET IDENTITY_INSERT … ON/OFF` statements
degrade to documented carriers (with one warning), and the `INSERT` itself
—value list intact— transpiles normally, since every target already accepts
an explicit identity value without special ceremony.

**Discussion.** None of the other three targets
distinguishes an "explicit identity value" mode — they simply accept an
explicit value in the `INSERT` column list (PostgreSQL 15+ additionally has
`OVERRIDING SYSTEM VALUE`, unused here).

> **Note** faithful for the `INSERT`'s data. `[limit]`
> (carrier) for the `ON`/`OFF` bracket itself. The earlier defect handled the
> two `SET` statements **incoherently**: `ON` degraded correctly, but `OFF`
> was mangled into `SET IDENTITY_INSERT = t AS OFF` and shipped as **live,
> invalid** SQL with no warning (PostgreSQL: `syntax error at or near "AS"`)
> — a real defect this fix closes.

**See Also.** [`reda-ts-identity-insert`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1002`](../../reference/warnings.md#unique-1002).
