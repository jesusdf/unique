[← Procedural: cursors, dynamic SQL, system procedures, session directives](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=procedural type="Cursor attribute mapping" direction="oracle → tsql/mysql" kind=article order=6 -->

# Oracle `%FOUND`/`%NOTFOUND`/`%ISOPEN`/`%ROWCOUNT` → T-SQL / MySQL

**Problem.** Oracle attaches state to each named cursor:
`c%FOUND`/`c%NOTFOUND` (did the last `FETCH` return a row), `c%ISOPEN`, and
`c%ROWCOUNT` (rows fetched so far on that cursor).

**Solution.**

```sql
-- corpus case ora-cursor-attr
CREATE PROCEDURE p AS CURSOR c IS SELECT 1 FROM DUAL; v NUMBER;
BEGIN OPEN c; FETCH c INTO v; IF c%FOUND THEN DBMS_OUTPUT.PUT_LINE(c%ROWCOUNT); END IF; CLOSE c; END;
-- live-compiled VALID on tsql + mysql
```

Cursor attributes are mapped **before** the general
expression IR sees them (`c%FOUND` would otherwise parse as `c` modulo
`FOUND`). Each named cursor gets its **own** per-cursor state, captured right
beside the cursor operation it depends on: T-SQL captures `@@FETCH_STATUS`
into a per-cursor `@uq_<c>_fs` variable immediately after each `FETCH <c>`;
MySQL transfers the shared handler flag into a per-cursor `v_uq_<c>_done`
right after each `FETCH`, then resets the shared flag. `%ISOPEN` becomes a
per-cursor flag set on `OPEN`/`CLOSE`. `%ROWCOUNT` becomes a per-cursor
counter incremented after each successful `FETCH`. An unrecognized attribute
(e.g. `%BULK_ROWCOUNT`) degrades to a `-- UNIQUE:` carrier + warning — never
emitted as `%` modulo arithmetic.

**Discussion.** T-SQL exposes only a single **global**
`@@FETCH_STATUS`/cursor state, shared across every open cursor in the
routine — reading it for cursor `c` after an intervening `FETCH` on a
*different* cursor `d` would silently report `d`'s status. MySQL similarly
has one shared `NOT FOUND` handler flag per routine, not one per cursor.
Naively mapping Oracle's per-cursor attributes onto either shared mechanism
is only correct if no other cursor is touched in between — not something
Unique can assume about arbitrary procedure bodies.

> **Note** faithful — live-compiled valid on T-SQL and MySQL.

**See Also.** [`ora-cursor-attr`](../../../tests/fixtures/challenge/challenge_oracle.sql) · [§3.23](../../03-unsupported.md) (audit
B7/N5+N6) — the same section also covers the related but distinct
`SQL%ROWCOUNT`/`ROW_COUNT()` "matched vs. changed rows" divergence onto
MySQL (§3.22).
