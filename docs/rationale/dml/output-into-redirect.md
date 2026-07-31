[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`OUTPUT` / `RETURNING`" direction="tsql → postgresql" kind=article order=12 -->

# `OUTPUT … INTO` redirect (T-SQL) → PostgreSQL

**Problem.** `OUTPUT INSERTED.a INTO log(a)` redirects the output
rows into a second table instead of returning them to the caller.

**Solution.**

```sql
-- corpus case reda-ts-output-into
INSERT INTO t (a) OUTPUT INSERTED.a INTO log(a) VALUES (1)
-- PostgreSQL: INSERT INTO t (a) VALUES (1) RETURNING a
-- (the INTO log(a) redirect is dropped with a warning, not silently)
```

The plain `OUTPUT INSERTED.a` (no `INTO`) form maps
cleanly to `RETURNING a` (the `INSERTED.` qualifier is stripped, as above).
The `INTO log(a)` redirect itself has no PostgreSQL equivalent and is
dropped with a warning, rather than leaking the invalid `RETURNING
INSERTED.a` (PostgreSQL rejects `INSERTED` as an unqualified relation).

**Discussion.** PostgreSQL's `RETURNING` only ever
returns a result set to the caller; it has no `INTO <table>` redirect form.

> **Warning** `[limit]` — the redirect into `log` is lost; the
> base `INSERT` and its plain-`RETURNING` value are faithful.

**See Also.** [`reda-ts-output-into`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`UNIQUE-1137`](../../reference/warnings.md#unique-1137) ·
[`UNIQUE-1139`](../../reference/warnings.md#unique-1139).
