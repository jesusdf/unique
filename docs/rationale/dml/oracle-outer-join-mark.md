[← DML: PIVOT/UNPIVOT, MERGE, DELETE, row values](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=dml type="Oracle join syntax and row limits (source direction)" direction="cross-engine" kind=article order=16 direction-inferred=true -->

# Oracle `(+)` outer-join mark → explicit `LEFT JOIN … ON`; comma joins → `CROSS JOIN`

**Problem.** Oracle's legacy join syntax has no `JOIN` keyword at all: tables
are comma-listed in `FROM`, and `col(+)` on one side of a `WHERE` predicate
marks that table as the *optional* (outer) side of the join — the row is
still produced, NULL-extended, when no match exists.

**Solution.**

```sql
-- pinning test: tests/unit/core/test_oracle_join_mark.py::TestOracleJoinMark
-- (no challenge-corpus case yet)
SELECT a.x, b.y FROM ta a, tb b WHERE a.id = b.id(+)
-- PostgreSQL / MySQL / T-SQL:
SELECT a.x, b.y FROM ta a LEFT JOIN tb b ON a.id = b.id

-- a comma join with no (+) mark at all:
SELECT a.x FROM a, b WHERE a.id = b.id
-- -> FROM a CROSS JOIN b WHERE a.id = b.id   (not INNER JOIN: there is no ON)
```

Live-verified (Oracle, PostgreSQL, MySQL, T-SQL; seed rows `ta(1,'a1')
(2,'a2') (3,'a3')`, `tb(1,'b1') (2,'b2')`): all four return `('a1','b1')
('a2','b2') ('a3', NULL)` for the query above — the unmatched `ta` row keeps
its NULL-extended `b.y`.

**Discussion.** `(+)` and the bare comma join are Oracle-only syntax with no
target-engine equivalent, so the join must be reconstructed explicitly. A
comma join carries no `ON` clause to promote into `INNER JOIN`, so it becomes
`CROSS JOIN` (the faithful unfiltered Cartesian product) plus the original
predicate in `WHERE`, never a guessed `INNER JOIN` — emitting `INNER JOIN` with
no `ON` is invalid on every target, and inferring one from an unrelated
`WHERE` predicate would silently change which rows survive. `(+)` similarly
becomes an explicit `LEFT JOIN … ON`, with the marked side moved to the
outer/right position: an early version emitted `INNER JOIN` with no `ON` at
all here too — a syntax error on PostgreSQL/MySQL/T-SQL and a silent
LEFT→INNER semantic change everywhere.

> **Note** faithful — live-verified identical rows on Oracle, PostgreSQL,
> MySQL and T-SQL (see above).

**See Also.** [`tests/unit/core/test_oracle_join_mark.py`](../../../tests/unit/core/test_oracle_join_mark.py)
(note: this test lives in `tests/unit/core/`, not `tests/integration/`) ·
challenge `red2-ora-plus-outer-join-dup` (`tests/fixtures/challenge/challenge_oracle.sql`,
tagged `[fixed]`) is a **related but distinct**, already-fixed defect — a
table with *two* `(+)` predicates used to duplicate that table's join into an
extra `CROSS JOIN` — which this single-predicate mechanism never exhibited ·
[§7](../../03-unsupported.md) "To Oracle" (the reverse-direction
parenthesized-join-tree gate).
