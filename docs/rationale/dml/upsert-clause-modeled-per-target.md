[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`MERGE` / upsert lowering" direction="postgresql/mysql → cross-engine" kind=article order=29 -->

# `INSERT ... ON CONFLICT` / `ON DUPLICATE KEY UPDATE` upsert clause → per-target idiom

**Problem.** PostgreSQL's `INSERT ... ON CONFLICT (key) DO UPDATE/DO NOTHING`
and MySQL's `INSERT ... ON DUPLICATE KEY UPDATE` / `INSERT IGNORE` are each
one engine's own upsert syntax. T-SQL and Oracle have no `ON CONFLICT`
clause at all — their only upsert vehicle is `MERGE`.

**Solution.**

```sql
-- corpus case pg-insert-select-conflict (DO UPDATE variant shown), postgresql -> *
INSERT INTO t (id, n) SELECT 1, 99 ON CONFLICT (id) DO UPDATE SET n = EXCLUDED.n;
-- => postgresql (native, unchanged)
INSERT INTO t (id, n) SELECT 1, 99 ON CONFLICT (id) DO UPDATE SET n = EXCLUDED.n;
-- => mysql
INSERT INTO t (id, n) SELECT 1, 99 ON DUPLICATE KEY UPDATE n = VALUES(n);
-- => tsql / oracle
MERGE INTO t AS uq_t
USING (SELECT 1, 99) AS uq_s (id, n)
ON uq_t.id = uq_s.id
WHEN MATCHED THEN UPDATE SET uq_t.n = uq_s.n
WHEN NOT MATCHED THEN INSERT (id, n) VALUES (uq_s.id, uq_s.n);
```

The upsert clause is read into one IR shape (its conflict-target key columns,
`DO UPDATE`/`DO NOTHING` action, assignments, and an optional `WHERE`) and
re-emitted per target: kept native on PostgreSQL, respelled as `ON DUPLICATE
KEY UPDATE`/`INSERT IGNORE` on MySQL, and — since T-SQL/Oracle have no upsert
clause at all — synthesized as an insert-only `MERGE`, with the `INSERT`'s
own row source wrapped into the `MERGE`'s `USING` (a `VALUES` table
constructor on T-SQL, a `SELECT … FROM DUAL` union on Oracle, which has none).
An `EXCLUDED.col` (PostgreSQL) or `VALUES(col)` (MySQL) reference in an
assignment — "the value this row would have inserted" — is recognized as the
same marker on both spellings and re-emitted as the `MERGE` source alias's
own column.

**Discussion.** Only PostgreSQL and MySQL have a single-statement upsert
clause, and they name the conflict differently: PostgreSQL takes an explicit
key-column list, MySQL infers it from whichever unique/primary key the new
row collides with. T-SQL and Oracle have no upsert clause whatsoever — `MERGE`
is their only construct that can conditionally insert-or-update a row, so
lowering to it (rather than degrading) needs the `INSERT`'s row source
turned into a joinable relation the `MERGE`'s `USING`/`ON` can match against.

> **Note** faithful — live-verified on all four engines: an existing key
> (id=1) is updated to the new value, an absent key would be inserted, on
> PostgreSQL, MySQL, T-SQL and Oracle alike.

Two engine-level divergences remain genuine, unannotated-away limits and stay
documented at [§3.22](../../03-unsupported.md): MySQL's `ON DUPLICATE KEY
UPDATE` fires on **any** unique/primary key rather than a single named
target, and MySQL's `INSERT IGNORE` swallows non-duplicate errors that
PostgreSQL's `DO NOTHING`/the `MERGE` forms do not. A MySQL-source upsert
whose conflict key cannot be resolved from an in-script `PRIMARY KEY`/`UNIQUE`
declaration has no target to lower with at all and degrades the **whole**
statement to a carrier + warning (`UNIQUE-1021`) — never a plain `INSERT`
that would raise or silently duplicate at runtime.

**See Also.** Corpus [`pg-insert-select-conflict`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[§3.22](../../03-unsupported.md) (the two named divergences and the no-key
whole-statement degrade) ·
[`UNIQUE-1021`](../../reference/warnings.md#unique-1021),
[`UNIQUE-1022`](../../reference/warnings.md#unique-1022),
[`UNIQUE-1023`](../../reference/warnings.md#unique-1023),
[`UNIQUE-1024`](../../reference/warnings.md#unique-1024) ·
[canonical `MERGE` → MySQL upsert](merge-to-mysql-on-duplicate-key.md) (the
mirror direction: an explicit `MERGE` source lowered the same way this
clause's insert-only `MERGE` target is built).

---
