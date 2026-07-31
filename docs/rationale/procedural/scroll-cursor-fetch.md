[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Other `[limit]` procedural entries" direction="tsql → oracle/postgresql/mysql" kind=article order=15 -->

# Scroll cursor `FETCH PRIOR/FIRST/LAST/ABSOLUTE/RELATIVE` (T-SQL) → Oracle / PostgreSQL / MySQL

**Problem.** A T-SQL `SCROLL` cursor supports non-forward fetches:
`FETCH LAST`, `FETCH PRIOR`, `FETCH ABSOLUTE n`, etc.

**Solution.**

```sql
-- corpus case ts-scroll-cursor
CREATE PROCEDURE p AS BEGIN
  DECLARE c CURSOR LOCAL SCROLL FOR SELECT 1;
  OPEN c; FETCH LAST FROM c; CLOSE c; DEALLOCATE c;
END
```

The scroll fetch itself degrades to a carrier
comment; the surrounding `OPEN`/`CLOSE`/`DEALLOCATE` still compile normally.

**Discussion.** Oracle, PostgreSQL and MySQL cursors are
**forward-only** — only `FETCH NEXT` exists — so a non-forward fetch has no
equivalent operation to translate to.

> **Warning** `[limit]` — approved degrade.

**See Also.** [`ts-scroll-cursor`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) · [§2](../../03-unsupported.md) (scroll
cursor row).
