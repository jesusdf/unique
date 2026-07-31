[← Strings, concatenation and collation](README.md) · [All rationale topics](../README.md)

<!-- rationale: topic=strings-collation type="Operator precedence" direction="tsql/postgresql/mysql → oracle" kind=article order=27 -->

# Infix bitwise operators (`&`, `|`, `^`, `<<`, `>>`) → Oracle `BITAND`/`POWER` identities

**Problem.** Oracle has no infix bitwise operators at all: `|` is string
concatenation there, and `^`/`&` are outright errors. Oracle's only
bitwise primitive is the `BITAND(a, b)` function — `OR`, `XOR`, and the
shift operators have no built-in Oracle spelling of their own.

**Solution.**

```sql
-- tests/unit/core/test_bitwise_oracle.py::TestBitwiseOracle
SELECT 5 & 3, 5 | 3, 5 ^ 3, 8 << 2, 20 >> 2
-- tsql -> oracle:
SELECT BITAND(5, 3), (5 + 3 - BITAND(5, 3)), (5 + 3 - 2 * BITAND(5, 3)),
       (8 * POWER(2, 2)), FLOOR(20 / POWER(2, 2))
```

**Discussion.** Every operator is rebuilt from `BITAND` and ordinary
arithmetic using an exact integer identity, not an approximation:
`a & b` is `BITAND(a, b)` directly; `a | b` is `a + b - BITAND(a, b)`
(each bit set in `a` or `b` is counted once, so subtracting their shared
`AND` removes the double-count of bits set in both); `a ^ b` is
`a + b - 2 * BITAND(a, b)` (the same identity, but bits set in *both*
must be removed entirely, not just de-duplicated, since XOR excludes
them); a left shift `a << b` is multiplication by `POWER(2, b)`, and a
right shift `a >> b` is division by the same power, floored down to an
integer. These identities hold exactly for non-negative integers, which
covers the values these operators are normally applied to. On
PostgreSQL, only `^` needs a respelling (`#`, PostgreSQL's own XOR
symbol — `&`/`|`/`<<`/`>>` are already native there); MySQL keeps every
operator as-is.

> **Note** faithful — live-verified against Oracle: `5 | 3` = `7`,
> `5 ^ 3` = `6`, `5 & 3` = `1`, `8 << 2` = `32`, `20 >> 2` = `5`, matching
> the source values exactly. No warning.

**See Also.** [`test_bitwise_oracle.py`](../../../tests/unit/core/test_bitwise_oracle.py)
(`TestBitwiseOracle`) · [§3.10](../../03-unsupported.md), "Bitwise
Operators → Oracle" · [Unary bitwise `~x`/NOT → Oracle/MySQL](unary-bitwise-not-emulation.md)
(the sibling entry for the unary operator) ·
[Bitwise/arithmetic operator-precedence parentheses](bitwise-arithmetic-precedence-parens.md)
(the sibling entry for mixed bitwise/arithmetic grouping).
