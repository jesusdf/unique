[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Operator precedence" direction="cross-engine" kind=article order=17 -->

# Bitwise/arithmetic operator-precedence parentheses (MySQL/Oracle ↔ PostgreSQL/T-SQL)

**Problem.** `&`, `|` and `<<`/`>>` bind **looser** than `+`/`*` on MySQL
and Oracle, but **tighter** than `+`/`*` on PostgreSQL and T-SQL. The same
unparenthesized expression — `10 & 6 + 1` — groups as `10 & (6 + 1)` on one
pair of engines and as `(10 & 6) + 1` on the other, changing the result
(`2` vs. `11`) even though every symbol transposes one-to-one.

**Solution.**

```sql
-- my-bit-prec2, mysql → postgresql / tsql
SELECT 10 & 6 + 1, 10 | 2 * 3, 1 << 2 + 1;
-- =>
SELECT 10 & (6 + 1), 10 | (2 * 3), 1 << (2 + 1);
```

Each mixed bitwise/arithmetic expression is parenthesized explicitly around
the arithmetic sub-expression, reproducing MySQL's own grouping
(`10 & (6 + 1)` = `2`) regardless of which way the target's own precedence
table runs. The same rewrite applies from a PostgreSQL source reaching a
target with the *opposite* ordering:

```sql
-- pg-bit-prec2, postgresql → tsql
SELECT 10 & 6 + 1, 1 << 2 + 1;
-- =>
SELECT 10 & (6 + 1), 1 << (2 + 1);
```

**Discussion.** Operator precedence between arithmetic and bitwise
operators is not part of the SQL standard — each engine picked its own
table, and MySQL/Oracle's choice (bitwise looser than arithmetic) is the
exact inverse of PostgreSQL/T-SQL's (bitwise tighter). A transpiled
expression that keeps the source's bare, unparenthesized form would
silently re-associate under the target's own rules whenever the two
disagree — the tokens are identical, but the value changes. Parenthesizing
the arithmetic sub-expression is unconditional and unambiguous: it fixes
the grouping to match the source's evaluation order on every target,
whether or not that target's own table happened to already agree.

> **Note** faithful — live-verified: `10 & 6 + 1` evaluates to `2` on
> MySQL/Oracle (bitwise loosest) and, after parenthesizing, to the same `2`
> on PostgreSQL/T-SQL, where an unparenthesized `10 & 6 + 1` would instead
> give `11`.

**See Also.** Corpus [`my-bit-prec2`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`my-bitand-prec`](../../../tests/fixtures/challenge/challenge_mysql.sql),
[`pg-bit-prec2`](../../../tests/fixtures/challenge/challenge_postgresql.sql) ·
[`TestBitwiseArithmeticPrecedence`](../../../tests/integration/test_challenge.py).
