[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="Temporary tables and the `CREATE TABLE AS SELECT` ↔ `SELECT INTO` idiom" direction="tsql/postgresql/mysql → oracle" kind=article order=7 -->

# Session-scoped temp tables (PostgreSQL `TEMP` / T-SQL `#temp` / MySQL `TEMPORARY`) → Oracle `GLOBAL TEMPORARY`

**Problem.** A PostgreSQL `TEMP`/`TEMPORARY` table, a T-SQL `#temp`
table, and a MySQL `TEMPORARY` table are all **session-scoped**: their
definition and rows live only for the current connection, and — critically —
their rows **survive an intervening `COMMIT`**.

**Solution.**

```sql
-- corpus case pg-temp-oncommit-oracle (schematic: CREATE TEMP TABLE t (...), then INSERT, COMMIT, SELECT COUNT(*))
-- Oracle: CREATE GLOBAL TEMPORARY TABLE redb_tmp (...) ON COMMIT PRESERVE ROWS
-- (without ON COMMIT PRESERVE ROWS, Oracle defaults to ON COMMIT DELETE ROWS:
-- PostgreSQL COUNT = 2, Oracle COUNT = 0 across the same COMMIT boundary)
```

`CREATE GLOBAL TEMPORARY TABLE … ON COMMIT PRESERVE
ROWS` — the `ON COMMIT PRESERVE ROWS` clause is added whenever the source is
not already Oracle, specifically to match the source's commit-surviving
semantics. `SELECT … INTO #t2`/`SELECT … INTO TEMP t2` (the "create via
`SELECT INTO`" idiom) becomes `CREATE GLOBAL TEMPORARY TABLE t2 AS SELECT …`
on Oracle, or the target's own `CREATE TEMPORARY TABLE … AS SELECT …` /
`INTO TEMPORARY` idiom elsewhere.

**Discussion.** Oracle's closest construct, `CREATE
GLOBAL TEMPORARY TABLE`, has a **persistent, shared definition** (visible to
every session) with **per-session private rows** — a different model. Worse,
its default row-retention is `ON COMMIT DELETE ROWS` (transaction-scoped),
the opposite of the source engines' session-scoped, commit-surviving rows.

> **Note** faithful **once** `ON COMMIT PRESERVE ROWS` is
> added — verified: without it, a later statement in the same script sees 0
> rows on Oracle against 2 on PostgreSQL across the same commit boundary.

**See Also.** [`ts-select-into-temp`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`pg-select-into-ctas`](../../../tests/fixtures/challenge/challenge_postgresql.sql),
[`pg-temp-oncommit-oracle`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[T-SQL table variable / in-routine `SELECT ... INTO #tmp` → Oracle hoisted GTT](../procedural/routine-scoped-temp-tables-to-oracle-gtt.md)
(the sibling mechanism for storage declared *inside* a routine body, which
needs the `CREATE` hoisted out and a per-call `DELETE`/`INSERT` instead).
