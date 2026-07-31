[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="LIKE and pattern matching" direction="cross-engine" kind=article order=5 direction-inferred=true -->

# LIKE … ESCAPE mapping

**Problem.** `LIKE pattern ESCAPE 'c'` is SQL-standard: `c` escapes
a following `%`/`_` so it matches literally.

**Solution.**

```sql
-- reda-ts-like-escape, tsql → postgresql / oracle / mysql
SELECT a FROM t WHERE b LIKE '%x!%y%' ESCAPE '!';
-- => identical on all three targets
SELECT a FROM t WHERE b LIKE '%x!%y%' ESCAPE '!';
```

`LIKE … ESCAPE '…'` now passes through unchanged on
every target.

Separately, PostgreSQL and MySQL treat a bare backslash as their **default**
`LIKE` escape character (with no `ESCAPE` clause at all); Oracle and T-SQL
have **no** default escape. A pattern like `'a\%b'` therefore matches a
literal `%` on a PostgreSQL/MySQL source but a wildcard on an Oracle/T-SQL
target unless compensated — Unique adds an explicit `ESCAPE '\'` when a
backslash-containing `LIKE` pattern crosses from a PostgreSQL/MySQL source to
Oracle/T-SQL, to preserve the source's implicit escaping
(`emit_expr.py:1858-1864`).

**Discussion.** *Why there is no direct mapping — there isn't one, and the
old behaviour lied about it.* `ESCAPE` is supported **identically** by
PostgreSQL, Oracle and MySQL — a pure syntax passthrough. The transpiler used
to treat the `ESCAPE` clause as an "unmapped operator; no `<engine>` mapping"
and comment out the **entire** statement with a warning that misdescribed
reality (a mapping exists; nothing needed translating) — losing a valid,
portable construct entirely (`reda-ts-like-escape`, class `lying-warning`).

> **Note** faithful — live-verified true on all four
> engines. No warning (previously the whole statement was dropped; now
> nothing is).

**See Also.** Corpus [`reda-ts-like-escape`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`emit_expr.py:1858-1864` (backslash default-escape compensation, docstring).

---
