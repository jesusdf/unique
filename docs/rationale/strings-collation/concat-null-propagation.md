[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Concatenation" direction="cross-engine" kind=article order=1 direction-inferred=true -->

# CONCAT / `||` NULL-propagation per engine

**Problem.** MySQL's `CONCAT(a, b, …)` **propagates** `NULL`: any
`NULL` argument makes the whole result `NULL`. PostgreSQL `||`, T-SQL `+`
(string context) and MySQL/PostgreSQL/T-SQL's own `CONCAT()` function all
propagate the same way. Oracle's `||` operator is the odd one out: it treats
`NULL` as an **empty string**, so `'a' || NULL || 'b'` = `'ab'`, not `NULL`.

**Solution.**

```sql
-- reda-ora-concat-null-cast, oracle → postgresql
SELECT 'a' || CAST(NULL AS VARCHAR2(10)) || 'b' AS r FROM DUAL;
-- =>
SELECT 'a' || 'b' AS r;   -- Oracle's own '' collapses the operand; folds to 'ab'

-- my-concat-null-col, mysql → postgresql / tsql / oracle
SELECT CONCAT(a, b) AS c FROM (SELECT 1 AS a, CAST(NULL AS CHAR) AS b) t;
-- =>
SELECT CASE
  WHEN a IS NULL OR b IS NULL THEN NULL
  ELSE CONCAT(a, b)
END AS c
FROM (SELECT 1 AS a, CAST(NULL AS TEXT) AS b) t;
```

A literal `NULL` operand of an Oracle-source `||` is
constant-folded away at transpile time. A **non-literal** possibly-`NULL`
operand (a `CAST(NULL AS …)`, or a column recognised as nullable) is guarded
with a `CASE WHEN <op> IS NULL … THEN NULL ELSE <concat> END` so the
propagation direction matches the source engine, whichever way it runs.

The reverse (Oracle as target of a propagating source) needs no CASE guard
when the operand is a bare literal `NULL`: `ora-concat-null` folds `'a' + 'b'`
(T-SQL) / `CONCAT('a', 'b')` (MySQL) / `'a' || 'b'` (PostgreSQL) — dropping
the literal reproduces Oracle's own empty-string treatment without needing a
runtime guard, since a compile-time-known `NULL` is gone either way.

**Discussion.** A straight operator/function copy
reverses the result on whichever side treats `NULL` differently. Going
**Oracle → other engines**, a bare `NULL` operand must be dropped so the
other engines' propagating `||`/`CONCAT` produces Oracle's `'ab'`, not the
propagating engines' own `NULL`. Going **MySQL → other engines**, a `NULL`
operand must instead be preserved (or synthesised) so the target's
non-propagating engines (Oracle) or operators still yield `NULL`. Two
sub-cases compound this: a **non-literal** `NULL` (`CAST(NULL AS
VARCHAR2(10))`, or a `NULL`-valued **column** known only at runtime) is not
visible to a compile-time literal check, so an early fix that only stripped
*literal* `NULL` left both holes open (`reda-ora-concat-null-cast`,
`my-concat-null-col` — both filed as class `func`/`lying-warning`: the only
signal was an unrelated internal "unread sqlglot arg" tripwire, not a message
describing the semantic loss).

> **Note** faithful in both directions — live-verified: T-SQL
> `'a' + 'b'` / PostgreSQL `'a' || 'b'` / MySQL `CONCAT('a', 'b')` all give
> `'ab'` matching Oracle's own `'ab'`; the guarded CASE gives MySQL's `NULL` on
> every target. No warning (the value is reproduced exactly, not merely
> approximated).

**See Also.** Corpus [`ora-concat-null`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`reda-ora-concat-null-cast`](../../../tests/fixtures/challenge/challenge_oracle.sql),
[`my-concat-null`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`my-concat-null-col`](../../../tests/fixtures/challenge/challenge_mysql.sql), [`ts-concat-null`](../../../tests/fixtures/challenge/challenge_sqlserver.sql), [`pg-concat-null`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
`emit_expr.py:1869-1897` (`_emit_binary`, CONCAT dialect overrides, docstring).

---
