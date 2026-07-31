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
always translate to it.

*Out-of-range `start` behaves differently per target.* MySQL's `INSERT()`
returns the **original string unchanged** when `start` is `0` or past the
string's end (live-verified `'abc'`/`'abcdef'`). The MySQL → T-SQL path
reproduces this explicitly: T-SQL's `STUFF` returns `NULL` for an
out-of-range `start` (a different value class, the same shape of problem as
the REPEAT/REPLICATE clamp above), so the emitted
`CASE WHEN start < 1 OR start > LEN(s) THEN s ELSE STUFF(…) END` reproduces
MySQL's unchanged-string result.

The MySQL → Oracle/PostgreSQL paths, and the plain `STUFF`/`OVERLAY` →
Oracle/PostgreSQL paths, do not reproduce this out-of-range handling:
`INSERT('abc', 10, 1, 'X')` (MySQL, `'abc'`) becomes `'abcX'` via the Oracle
`SUBSTR` splice, and `INSERT('abcdef', 0, 2, 'XY')` (MySQL, `'abcdef'`)
becomes `'XYbcdef'` on the same splice — both diverge from MySQL's
unchanged-string result, with no warning emitted. On PostgreSQL the
`start = 0` case instead raises `negative substring length not allowed` at
run time.

> **Warning** faithful for the in-bounds case on every target
> (live-verified `'aXYef'`/`'QuWhattic'` reproduced identically by all four
> engines). Out-of-range `start` values diverge on Oracle and PostgreSQL
> targets, with no warning — only the T-SQL target reproduces MySQL's
> unchanged-string behavior.

**See Also.** Corpus [`pg-overlay`](../../../tests/fixtures/challenge/challenge_postgresql.sql), [`my-insert2`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-insert-oob`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-insert-zeropos`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`ts-stuff`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
[`TestOverlay`](../../../tests/integration/test_challenge.py), [`TestMysqlInsertBounds`](../../../tests/integration/test_challenge.py) (pinned) ·
`test_mysql_to_tsql[my-insert-oob]`/`test_mysql_to_oracle[my-insert-oob]`/`test_mysql_to_postgresql[my-insert-oob]` (`test_challenge_assertions_mysql.py`) · `test_tsql_case` (`test_challenge_assertions_sqlserver.py`, `ts-stuff` row) ·
`emit_functions.py:2417-2441` (`OVERLAY`), `emit_functions.py:3441-3469` (`STUFF`/`INSERT`), docstrings.

---
