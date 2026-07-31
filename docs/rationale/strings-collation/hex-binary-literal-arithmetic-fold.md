[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Hex/binary literal folding" direction="tsql → postgresql/oracle/mysql" kind=article order=21 direction-inferred=true -->

# A T-SQL hex/binary literal used in arithmetic → folded to its integer value

**Problem.** T-SQL's `0x0A` is a binary-string literal that also behaves
as an integer in numeric contexts (`0x0A + 5` = `15`). PostgreSQL, Oracle,
and MySQL each have their own, differently-typed binary-literal spelling
(`bytea`, `HEXTORAW(...)`, `x'0A'`) — none of which support arithmetic the
way T-SQL's does, so emitting a same-shaped binary literal into an
arithmetic expression on any of them is invalid, not merely different.

**Solution.**

```sql
-- corpus case reda-ts-hex-literal-arith
SELECT 0x0A + 5 AS r
-- tsql -> postgresql / oracle / mysql:
SELECT 10 + 5 AS r;
```

**Discussion.** Rather than translate the literal's *spelling* into each
target's own binary-literal syntax (which would produce a type error the
moment it's added to `5`), Unique folds the hex literal to its plain
integer value at translation time, since the value is always statically
known. The literal's *binary type* only matters when it's used as an
actual byte string (an `INSERT` into a `BINARY`/`BLOB` column, say); used
arithmetically, T-SQL is really treating it as a number, so the fold
reproduces that reading directly rather than emitting a target-native
binary literal no target's arithmetic operator would accept.

> **Note** faithful — `0x0A` = `10`, and `10 + 5 = 15` on every target,
> identical to T-SQL's own `0x0A + 5`. No warning.

**See Also.** Corpus [`reda-ts-hex-literal-arith`](../../../tests/fixtures/challenge/challenge_sqlserver.sql) ·
`test_challenge_assertions_sqlserver.py` (`reda-ts-hex-literal-arith`).
