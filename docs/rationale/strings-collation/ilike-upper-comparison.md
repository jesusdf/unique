[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Case-insensitive pattern matching" direction="postgresql → oracle/tsql/mysql" kind=article order=25 direction-inferred=true -->

# PostgreSQL `ILIKE` (case-insensitive `LIKE`) → `UPPER(x) LIKE UPPER(pattern)`

**Problem.** PostgreSQL's `ILIKE` is a case-insensitive `LIKE` operator —
no other target engine has a dedicated case-insensitive pattern-match
operator (T-SQL and MySQL's default collations are already
case-insensitive, but Oracle's is case-sensitive by default and has no
`ILIKE` spelling at all).

**Solution.**

```sql
-- tests/unit/core/test_ilike_groupconcat.py::TestIlike
SELECT * FROM t WHERE name ILIKE 'a%'
-- postgresql -> oracle:
SELECT * FROM t WHERE UPPER(name) LIKE UPPER('a%');
```

Both sides of the comparison are upper-cased identically, so the match
proceeds without regard to case on any target regardless of its own
default collation.

**Discussion.** Wrapping both the column and the pattern in `UPPER(...)`
before comparing is a case-insensitivity technique that works identically
on every SQL engine's `LIKE`, independent of collation settings — it
doesn't rely on Oracle having, or PostgreSQL lacking, any particular
collation, so the rewrite is stable regardless of the database's own
default configuration. T-SQL and MySQL, whose `LIKE` is already
case-insensitive under their common default collations, could in principle
keep a bare `LIKE`, but Unique applies the same `UPPER`/`UPPER` wrap there
too rather than making the rewrite depend on the target's collation
configuration, which the transpiler has no reliable way to know ahead of
time.

> **Note** faithful — `UPPER(name) LIKE UPPER('a%')` matches exactly the
> same rows `name ILIKE 'a%'` would on PostgreSQL, independent of the
> target's own collation. No warning.

**See Also.** [`test_ilike_groupconcat.py::TestIlike`](../../../tests/unit/core/test_ilike_groupconcat.py)
(`test_ilike_to_oracle_uses_upper`).
