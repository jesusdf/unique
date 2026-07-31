[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="`MERGE` / upsert lowering" direction="tsql/oracle → mysql" kind=article order=28 -->

# Canonical `MERGE` (T-SQL/Oracle) → MySQL `INSERT … SELECT … ON DUPLICATE KEY UPDATE`

**Problem.** MySQL has no `MERGE` statement at all. The common upsert
shape — one unconditional `WHEN MATCHED THEN UPDATE` plus one unconditional
`WHEN NOT MATCHED THEN INSERT` — still needs a MySQL-side equivalent rather
than degrading whole.

**Solution.**

```sql
-- tests/unit/core/test_merge_mysql.py::CANONICAL, tsql -> mysql
MERGE INTO t USING s ON t.id = s.id
  WHEN MATCHED THEN UPDATE SET t.v = s.v, t.w = s.w
  WHEN NOT MATCHED THEN INSERT (id, v, w) VALUES (s.id, s.v, s.w);
-- =>
INSERT INTO t (id, v, w)
SELECT s.id, s.v, s.w FROM s
ON DUPLICATE KEY UPDATE v = VALUES(v), w = VALUES(w);
-- UNIQUE-1001: MERGE rewritten as INSERT ... ON DUPLICATE KEY UPDATE;
-- requires a UNIQUE or PRIMARY KEY on (id)
```

The `USING` source becomes the `INSERT … SELECT`'s `FROM`, the `INSERT`
column list and values carry over unchanged, and each `UPDATE` assignment
whose right-hand side is one of the inserted source columns is rewritten as
`col = VALUES(col)` — MySQL's own idiom for "the value this row would have
inserted." An assignment to a plain literal or `NULL` is copied verbatim
instead.

**Discussion.** `ON DUPLICATE KEY UPDATE` fires the `UPDATE` clause when the
new row's key collides with an existing row under **any** `UNIQUE`/`PRIMARY
KEY` constraint — there is no `ON`-clause equivalent to name a specific
conflict target the way `MERGE`'s join condition does. The rewrite is
therefore only value-equivalent to the source `MERGE` when the `ON`
columns are themselves covered by a `UNIQUE`/`PRIMARY KEY` on the target
table (so a "matched" row under the `MERGE` join is also the row MySQL's key
collision detects); a carrier note names that assumption rather than
asserting it silently. `VALUES(col)` reads the row MySQL is about to
insert, which is exactly the source row `MERGE`'s `WHEN MATCHED` branch
would have compared against — so an `UPDATE` assignment copied from a
source column stays correct even though the rewritten statement's `UPDATE`
runs after the `INSERT` values are already computed, not against a live join.

> **Note** faithful, conditioned on the noted PK/UNIQUE assumption —
> live-verified on MySQL: an existing row's key is updated to the source
> value, a new key is inserted, matching `MERGE`'s per-row semantics.

A `MERGE` outside this shape (a conditional `WHEN` clause, `WHEN MATCHED
THEN DELETE`, more than the one matched/not-matched pair) has no equivalent
rewrite and degrades whole to a documented carrier + warning instead — see
[§3.6](../../03-unsupported.md).

**See Also.** [`test_merge_mysql.py`](../../../tests/unit/core/test_merge_mysql.py) (`TestMergeToMySQL`) ·
[§3.6](../../03-unsupported.md) (the complex-`MERGE` fallback this rewrite is the faithful counterpart to) ·
[`UNIQUE-1001`](../../reference/warnings.md#unique-1001) ·
[a leading CTE feeding `MERGE`](merge-with-leading-cte.md) (the same rewrite, CTE-sourced).

---
