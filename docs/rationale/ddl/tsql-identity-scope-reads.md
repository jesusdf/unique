[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="The SERIAL / IDENTITY / AUTO_INCREMENT triangle" direction="tsql → oracle/postgresql/mysql" kind=article order=2 -->

# T-SQL identity-scope reads (`SCOPE_IDENTITY()`/`@@IDENTITY`/`IDENT_CURRENT()`) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL exposes the last-generated identity value through
three functions with different scoping rules (current scope / current
session / a named table).

**Solution.** The statement degrades to a documented carrier +
warning rather than picking one imprecise mapping.

**Discussion.** Each target exposes the equivalent
through a structurally different mechanism: Oracle `sequence.CURRVAL`,
PostgreSQL `lastval()`, MySQL `LAST_INSERT_ID()` — none of them share T-SQL's
three-way scope/session/table distinction.

> **Warning** `[limit]` — approved degrade.

**See Also.** [`ts-identity-funcs`](../../../tests/fixtures/challenge/challenge_sqlserver.sql).
