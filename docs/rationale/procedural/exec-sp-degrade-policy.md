[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="System procedures" direction="tsql → oracle/postgresql/mysql" kind=article order=1 -->

# `EXEC sp_<name>` degrade policy (T-SQL) → PostgreSQL / Oracle / MySQL

**Problem.** T-SQL system procedures (`sp_rename`, `sp_who`, …) call
into SQL Server's own catalog/admin machinery.

**Solution.** An unmapped `sp_*` call degrades to a documented
`-- UNIQUE:` carrier comment plus a `result.warnings` entry — the call is
never shipped as executable SQL, since the target has nothing to route it
to.

**Discussion.** These are engine-internal administrative
routines; no other engine exposes the same operation through a callable
procedure with the same name or signature.

> **Warning** `[limit]` — approved degrade; the administrative
> action itself is lost and must be performed through the target's own
> tooling.

**See Also.** [`reda-ts-exec-swallow-next`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), `mysql-drop2` family (see below) ·
[`UNIQUE-1211`](../../reference/warnings.md#unique-1211).
