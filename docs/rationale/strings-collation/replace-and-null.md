[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="NULL and empty-string semantics" direction="cross-engine" kind=article order=3 direction-inferred=true -->

# `REPLACE` and `NULL`: Oracle's 2-arg form vs MySQL's propagation

**Problem.** Two independent `REPLACE`/`NULL` divergences, found in the same
sweep as the `GREATEST`/`LEAST` case above. Oracle's **2-argument**
`REPLACE(s, search)` (no replacement string) removes every occurrence of
`search` and, since Oracle collapses an empty result to `NULL` (see
`Oracle '' ≡ NULL` below), returns `NULL` when `search` accounts for the
whole string. Separately, MySQL's `REPLACE` **propagates** `NULL`: any
`NULL` argument makes the whole call `NULL` — Oracle's `REPLACE`, by
contrast, ignores a `NULL` search/replace argument and returns the subject
unchanged.

**Solution.**

```sql
-- ora-translate3 (REPLACE part), oracle → postgresql / tsql
SELECT REPLACE('aaa', 'a') AS r FROM DUAL;
-- =>
SELECT NULLIF(REPLACE('aaa', 'a', ''), '') AS r;

-- my-replace-null2, mysql → oracle / postgresql / tsql
SELECT REPLACE('abc', NULL, 'x') IS NULL AS r;
-- => oracle
SELECT CASE WHEN NULL IS NULL THEN 1 WHEN NULL IS NOT NULL THEN 0 END AS r
FROM DUAL;
-- => postgresql / tsql (the REPLACE call folds away entirely)
SELECT NULL IS NULL AS r;
```

Oracle's 2-arg form is rewritten to the 3-arg form everywhere else with an
explicit `''` replacement, and the whole call wrapped in `NULLIF(…, '')` so
an all-removed result reproduces Oracle's `NULL` instead of the target's own
`''`. Going the other way, a MySQL `REPLACE` call carrying a **literal**
`NULL` argument is folded to a bare `NULL` at transpile time: on
PostgreSQL/T-SQL, which already propagate `NULL` through a normal `REPLACE`,
this is a pure constant-fold (no `REPLACE` call survives to translate, as in
the second example above); on Oracle, whose `REPLACE` ignores a `NULL`
search/replace and would otherwise return the subject unchanged, the fold is
load-bearing.

**Discussion.** Oracle has no on-disk distinction driving the 2-arg case —
it is the same `'' ≡ NULL` collapse documented below, reached through a
function call instead of a literal. The literal-`NULL` fold for MySQL's
`REPLACE` mirrors the `CONCAT` literal-`NULL` fold above, but — unlike
`CONCAT`, which also guards a *non-literal* possibly-`NULL` operand with a
runtime `CASE` — `REPLACE` only checks for a literal `NULL` argument
(`emit_functions.py:1750-1760`). Probing a non-literal case live surfaces the
same hole the `CONCAT` fix closed, still open here: `REPLACE('abc',
CAST(NULL AS CHAR), 'x')` from MySQL is emitted unchanged on Oracle as
`REPLACE('abc', CAST(NULL AS VARCHAR2(4000)), 'x')`, which live-evaluates to
`'abc'` (Oracle ignores the `NULL` search) where the MySQL source is `NULL`.
PostgreSQL/T-SQL stay correct here only because their own native `REPLACE`
already propagates `NULL` regardless of what Unique emits — Oracle is the
one target where this specific gap is live.

> **Note** faithful for the 2-arg Oracle rewrite (`NULLIF` reproduces
> Oracle's own `NULL`/`'abc45'`, live-verified) and for the MySQL
> literal-`NULL` fold (`NULL IS NULL` → `1`/true on all three targets,
> live-verified). **Open, unwarned divergence** — not part of any pinning
> test, found live while writing this entry: a *non-literal* `NULL` argument
> to a MySQL-source `REPLACE` reaching an **Oracle** target is not folded and
> silently returns the wrong (unchanged-subject) value; PostgreSQL/T-SQL are
> unaffected by accident, not by design.

**See Also.** Corpus [`ora-translate3`](../../../tests/fixtures/challenge/challenge_oracle.sql), [`my-replace-null2`](../../../tests/fixtures/challenge/challenge_mysql.sql) ·
[`TestOracleTwoArgReplaceTranslate`](../../../tests/integration/test_challenge.py), [`TestMysqlReplaceNullPropagates`](../../../tests/integration/test_challenge.py) (pinned) ·
`emit_functions.py:1726-1738` (2-arg Oracle `REPLACE`), `emit_functions.py:1750-1760` (MySQL literal-`NULL` fold), docstrings.

---
