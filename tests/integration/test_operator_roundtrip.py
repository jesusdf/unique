# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Operator round-trip tests: A -> B -> A'.

For an operator whose spelling differs between engines (most notably string
concatenation, which is ``+`` in T-SQL and ``||`` / ``CONCAT`` elsewhere),
transpiling A -> B should adopt B's spelling, and A -> B -> A should recover A's.
A one-way test can miss a no-op conversion (T-SQL ``+`` left as ``+`` on Oracle
looks plausible), so the round-trip is what makes such a regression visible.

Note on a fundamental limit: ``col1 + col2`` between two *columns* is ambiguous
without type information -- it could be numeric addition or string
concatenation, and T-SQL decides by the columns' declared types. With no
metadata (the standalone-DML path has none), the converter only rewrites ``+``
to concatenation when an operand is *recognizably* a string (a literal, a
varchar cast, a string function). These tests therefore use a string literal to
make the intent unambiguous, which is also the shape of the real-world report
that motivated them.
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler

#: Concatenation of a column with a string literal, as each engine spells it.
_CONCAT = {
    "tsql": "name + '!'",
    "oracle": "name || '!'",
    "postgresql": "name || '!'",
    "mysql": "CONCAT(name, '!')",
}


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().rstrip(";").strip()


def _concat_form_present(sql: str, engine: str) -> bool:
    """Whether the output uses *engine*'s concatenation spelling."""
    s = _norm(sql).upper()
    if engine == "mysql":
        return "CONCAT(" in s
    return "||" in s  # oracle / postgresql


def _is_concat_for(sql: str, engine: str) -> bool:
    """Whether the output is a *concatenation* valid on *engine* (not arithmetic
    "+"). T-SQL concatenates with "+"; Oracle/PostgreSQL use "||" (and also
    accept CONCAT); MySQL uses CONCAT. The select list must contain a concat,
    not a bare arithmetic plus."""
    head = _norm(sql).split("FROM")[0].upper()
    if engine == "tsql":
        return "+" in head or "CONCAT(" in head
    if engine == "mysql":
        return "CONCAT(" in head
    return "||" in head or "CONCAT(" in head  # oracle / postgresql


class TestStringConcatRoundTrip:
    @pytest.mark.parametrize("a", ["tsql", "oracle", "postgresql", "mysql"])
    @pytest.mark.parametrize("b", ["tsql", "oracle", "postgresql", "mysql"])
    def test_concat_roundtrip_recovers_original(self, a: str, b: str) -> None:
        if a == b:
            pytest.skip("same engine")
        sql = f"SELECT {_CONCAT[a]} AS x FROM t"
        intermediate = _t(sql, a, b)
        back = _t(intermediate, b, a)
        # The intermediate must use B's concat form (no foreign spelling left),
        # and the round-trip back to A must still be a concatenation valid on A
        # -- not arithmetic "+" and not another engine's spelling.
        assert _is_concat_for(intermediate, b), (
            f"{a}->{b} did not adopt {b}'s concat form: "
            f"{_norm(sql)!r} -> {_norm(intermediate)!r}"
        )
        assert _is_concat_for(back, a), (
            f"{a}->{b}->{a} lost the concatenation: "
            f"{_norm(sql)!r} -> {_norm(intermediate)!r} -> {_norm(back)!r}"
        )

    @pytest.mark.parametrize("b", ["oracle", "postgresql", "mysql"])
    def test_tsql_plus_adopts_target_spelling(self, b: str) -> None:
        out = _t("SELECT 'a' + 'b' AS x FROM t", "tsql", b)
        assert _concat_form_present(out, b)
        # T-SQL's "+" must not survive into the non-T-SQL target.
        assert "+" not in _norm(out).split("FROM")[0]

    def test_numeric_addition_is_not_concatenation(self) -> None:
        for target in ("oracle", "postgresql", "mysql"):
            out = _t("SELECT 1 + 2 AS n FROM t", "tsql", target)
            assert "||" not in out
            assert "CONCAT" not in out.upper()
            assert "+" in out

    def test_mixed_column_and_string_literal(self) -> None:
        out = _t("SELECT name + ' suffix' AS x FROM t", "tsql", "postgresql")
        assert "||" in out
        assert "+" not in _norm(out).split("FROM")[0]
