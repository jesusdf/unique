[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Repeat, substring and splice" direction="tsql/postgresql/mysql → all" kind=article order=10 -->

# Positional string-splice: `OVERLAY`/`STUFF`/`INSERT` (PostgreSQL/T-SQL/MySQL) → all targets

**Problem.** Three engines each have a native "replace `len` characters of
`string` at 1-based position `start` with `new`" function: PostgreSQL's
`OVERLAY(string PLACING new FROM start [FOR len])`, T-SQL's `STUFF(string,
start, len, new)`, MySQL's `INSERT(string, start, len, new)`. None has a
native form on either of the other two, and Oracle has none of the three.

**Solution.**

```sql
-- pg-overlay, postgresql → tsql / mysql / oracle
SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 2) AS r;
-- => tsql
SELECT STUFF('abcdef', 2, 2, 'XY') AS r;
-- => mysql
SELECT INSERT('abcdef', 2, 2, 'XY') AS r;
-- => oracle
SELECT SUBSTR('abcdef', 1, (2) - 1) || 'XY' || SUBSTR('abcdef', (2) + (2)) AS r
FROM DUAL;

-- ts-stuff, tsql → oracle / postgresql / mysql
SELECT STUFF('abcdef', 2, 3, 'XY') AS r;
-- => oracle
SELECT (SUBSTR('abcdef', 1, 2 - 1) || 'XY' || SUBSTR('abcdef', 2 + 3)) AS r
FROM DUAL;
-- => postgresql
SELECT OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 3) AS r;
-- => mysql
SELECT INSERT('abcdef', 2, 3, 'XY') AS r;
```

Each of the three source forms rewrites to either of the other's native call
when the target has one, and to an Oracle `SUBSTR(…) || new || SUBSTR(…)`
splice (head up to `start`, the replacement, tail from `start + len`) when it
doesn't — the three functions share a single emission path keyed off the
target dialect.

**Discussion.** Oracle has no positional string-splice built-in at all, so
the `SUBSTR` concatenation is the only route there; PostgreSQL/T-SQL/MySQL
each natively have exactly one of the three spellings, so the other two
always translate to it (`emit_functions.py:2417-2441` for the `OVERLAY`
source path, `emit_functions.py:3458-3469` for the `STUFF` source path).

*An open, undocumented caveat found while writing this entry.* MySQL's
`INSERT()` returns the **original string unchanged** when `start` is `0` or
past the string's end (`my-insert-oob`, `my-insert-zeropos` — live-verified
`'abc'`/`'abcdef'`). The MySQL → T-SQL path guards this explicitly: T-SQL's
`STUFF` returns `NULL` for an out-of-range `start` (a different value class,
the same shape of problem as the REPEAT/REPLICATE clamp above), so the
emitted `CASE WHEN start < 1 OR start > LEN(s) THEN s ELSE STUFF(…) END`
(`emit_functions.py:3441-3457`) reproduces MySQL's behavior. The MySQL →
Oracle/PostgreSQL paths, and the plain `STUFF`/`OVERLAY` → Oracle/PostgreSQL
paths, carry **no such guard**: live-verified, `INSERT('abc', 10, 1, 'X')`
(MySQL, `'abc'`) becomes `'abcX'` via the Oracle `SUBSTR` splice, and
`INSERT('abcdef', 0, 2, 'XY')` (MySQL, `'abcdef'`) becomes `'XYbcdef'` on the
same splice — both wrong values, silently, no warning. On PostgreSQL the
`start = 0` case is worse: `OVERLAY('abcdef' PLACING 'XY' FROM 0 FOR 2)`
raises `negative substring length not allowed` at run time — an invalid
statement shipped with no warning at all. Neither gap is scored against any
corpus case (`my-insert-oob`/`my-insert-zeropos` only assert the T-SQL
guard) and would need a fix brief before a BLUE pass.

> **Warning** faithful for the in-bounds case on every target
> (live-verified `'aXYef'`/`'QuWhattic'` reproduced identically by all four
> engines). **Open, unwarned divergence** for an out-of-range `start` on
> Oracle and PostgreSQL targets (T-SQL alone is guarded) — not a documented
> limit, found live while writing this entry, not covered by any pinning
> test.

**See Also.** Corpus [`pg-overlay`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`my-insert2`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-insert-oob`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-insert-zeropos`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`ts-stuff`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestOverlay`](../../../tests/integration/test_challenge.py), [`TestMysqlInsertBounds`](../../../tests/integration/test_challenge.py) (pinned) ·
`test_mysql_to_tsql[my-insert-oob]`/`test_mysql_to_oracle[my-insert-oob]`/`test_mysql_to_postgresql[my-insert-oob]` (`test_challenge_assertions_mysql.py`) · `test_tsql_case` (`test_challenge_assertions_sqlserver.py`, `ts-stuff` row) ·
`emit_functions.py:2417-2441` (`OVERLAY`), `emit_functions.py:3441-3469` (`STUFF`/`INSERT`), docstrings.

---
