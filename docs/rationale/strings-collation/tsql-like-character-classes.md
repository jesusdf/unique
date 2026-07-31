[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="LIKE and pattern matching" direction="cross-engine" kind=article order=6 direction-inferred=true -->

# T-SQL LIKE character classes (`'[A-C]%'`) → SIMILAR TO / REGEXP / REGEXP_LIKE

**Problem.** T-SQL's `LIKE` supports bracketed **character
classes**: `'[A-C]%'` matches any string starting with `A`, `B` or `C`.
PostgreSQL, MySQL and Oracle treat `[` and `]` as **literal characters** in a
`LIKE` pattern, so a verbatim passthrough silently flips the result
(`'Bob' LIKE '[A-C]%'` would be false — the string would have to start with
the literal `[`).

**Solution.**

```sql
-- corpus case red2-ts-like-charclass (tsql → postgresql)
SELECT c FROM t WHERE c LIKE '[A-C]%'
-- =>
SELECT c FROM t WHERE c SIMILAR TO '[A-C]%';
```

PostgreSQL keeps the bracket class via `SIMILAR TO` (whose pattern grammar
includes character classes); MySQL rewrites to `REGEXP '^[A-C].*$'` and
Oracle to `REGEXP_LIKE(expr, '^[A-C].*$')` — the `%`/`_` wildcards are
converted to their regex equivalents and the pattern is anchored.

**Discussion.** Standard `LIKE` has no character-class syntax, so each
target needs the closest predicate that does. Literal-vs-literal comparisons
still carry the generic collation-divergence note (`UNIQUE-1207`) that any
cross-engine string comparison gets — that warning is about case/accent
sensitivity and trailing spaces, a separate mechanism from the class
translation itself.

> **Note** faithful — live-verified 2026-07-30 on all four engines
> (`'Bob'` matches, value `1`); pinned by
> [`TestTsqlLikeCharClassTranslated`](../../../tests/integration/test_challenge.py).

**See Also.** corpus case `red2-ts-like-charclass`
(`tests/fixtures/challenge/challenge_sqlserver.sql`) ·
[`UNIQUE-1207`](../../reference/warnings.md#unique-1207).

---
