"""Oracle has no infix bitwise operators; they are expressed via BITAND()/POWER.

The identities (exact for non-negative integers) were validated live against
Oracle: 5|3=7, 5^3=6, 5&3=1, 8<<2=32, 20>>2=5.
"""

import sqlglot

from unique.core.transpiler import Transpiler

t = Transpiler()


def _oracle(expr: str) -> str:
    out = t.transpile(f"SELECT {expr} AS r", "tsql", "oracle").sql
    sqlglot.parse(out, read="oracle", error_level=sqlglot.ErrorLevel.RAISE)
    return out.upper()


class TestBitwiseOracle:
    def test_and_or_xor_use_bitand(self) -> None:
        assert "BITAND(5, 3)" in _oracle("5 & 3")
        # OR: a + b - (a & b)
        assert "5 + 3 - BITAND(5, 3)" in _oracle("5 | 3")
        # XOR: a + b - 2*(a & b)
        assert "5 + 3 - 2 * BITAND(5, 3)" in _oracle("5 ^ 3")

    def test_shifts_use_power(self) -> None:
        assert "8 * POWER(2, 2)" in _oracle("8 << 2")
        assert "FLOOR(20 / POWER(2, 2))" in _oracle("20 >> 2")

    def test_no_raw_bitwise_operator_leaks_to_oracle(self) -> None:
        for expr in ("5 | 3", "5 ^ 3", "5 & 3", "8 << 2", "20 >> 2"):
            out = _oracle(expr)
            # None of Oracle's rejected infix forms should survive.
            assert " | " not in out and " ^ " not in out
            assert " << " not in out and " >> " not in out

    def test_other_targets_keep_native_operator(self) -> None:
        # PostgreSQL: XOR is "#"; MySQL keeps "^". Sanity that we only rewrote Oracle.
        assert "#" in t.transpile("SELECT 5 ^ 3 AS r", "tsql", "postgresql").sql
        assert "^" in t.transpile("SELECT 5 ^ 3 AS r", "tsql", "mysql").sql
