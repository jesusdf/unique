[← DDL: identity, temp tables, foreign keys, sequences, storage options](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=ddl type="TRUNCATE options" direction="postgresql → oracle/mysql/tsql" kind=article order=21 -->

# PostgreSQL `TRUNCATE ... RESTART IDENTITY / CASCADE` → Oracle/MySQL/T-SQL

**Problem.** PostgreSQL's `TRUNCATE` defaults to *keeping* an identity
column's next value where it was (`CONTINUE IDENTITY` is implicit), and
only resets it when you say `RESTART IDENTITY` explicitly; the same
statement's `CASCADE` also truncates every table with a foreign key
pointing at the truncated one. Oracle, MySQL and T-SQL have neither
default: their plain `TRUNCATE` always resets the identity/auto-increment
counter, and none of the three has a `CASCADE` keyword on `TRUNCATE` at
all.

**Solution.**

```sql
-- pg-truncate-restart, postgresql → oracle
TRUNCATE TABLE t RESTART IDENTITY CASCADE;
-- =>
TRUNCATE TABLE t CASCADE;
```

`RESTART IDENTITY` is dropped — not translated to anything — because
Oracle's plain `TRUNCATE` already resets identity columns unconditionally;
asking it to do what it always does needs no clause. Oracle happens to
support `CASCADE` on `TRUNCATE` natively (it truncates FK-dependent tables
the same way PostgreSQL's does), so that keyword is kept as-is.

MySQL and T-SQL have no `CASCADE` on `TRUNCATE` at all, so it degrades to a
documented carrier instead of being silently dropped:

```sql
-- pg-truncate-restart, postgresql → mysql / tsql
TRUNCATE TABLE t RESTART IDENTITY CASCADE;
-- =>
-- UNIQUE-1109: TRUNCATE … CASCADE (also truncates FK-dependent tables) has
-- no mysql/tsql equivalent; only this table is truncated — truncate any
-- dependents explicitly
TRUNCATE TABLE t;
```

**Discussion.** `RESTART IDENTITY` and `CASCADE` diverge in kind, not just
in availability. `RESTART IDENTITY` restates a behavior every non-PostgreSQL
target already has unconditionally — dropping the keyword changes nothing
about what actually happens, so no carrier is needed. `CASCADE` is the
opposite: it's a real, target-dependent capability (truncating other
tables transitively through their foreign keys) that MySQL and T-SQL
simply cannot express on a `TRUNCATE` statement, so silently dropping it
would leave FK-dependent tables un-truncated with no indication anything
changed — a genuine behavior loss, surfaced as `UNIQUE-1109` rather than
left for the reader to discover.

> **Note** faithful (`RESTART IDENTITY` drop, all three targets — their own
> `TRUNCATE` already resets identity/auto-increment by default) ·
> **Warning** (`CASCADE` drop on MySQL/T-SQL) — FK-dependent tables are not
> truncated automatically; truncate them explicitly.

**See Also.** Corpus [`pg-truncate-restart`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestTruncateRestartIdentity`](../../../tests/integration/test_challenge.py) ·
[`UNIQUE-1109`](../../reference/warnings.md#unique-1109).
