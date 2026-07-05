# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Hypothesis strategies that generate portable SELECT statements.

The statements are self-contained (they read from an inline derived table) and
use only numeric, cross-dialect constructs, so they parse in every source
dialect and their transpiled output should execute anywhere. Hypothesis shrinks
any failing statement to a minimal reproducer — the payoff over a fixed corpus.
"""

from __future__ import annotations

from hypothesis import strategies as st

# Integer columns provided by the inline derived table below.
_COLUMNS = ("a", "b")
_DERIVED = "(SELECT 1 AS a, 2 AS b) t"

_ident = st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)
_int_lit = st.integers(min_value=-50, max_value=50).map(str)


def numeric_expr() -> st.SearchStrategy[str]:
    """A numeric scalar expression over the derived-table columns/int literals."""
    base = st.one_of(st.sampled_from(_COLUMNS), _int_lit)
    return st.recursive(
        base,
        lambda kids: st.one_of(
            st.builds(
                lambda left, op, right: f"({left} {op} {right})",
                kids,
                st.sampled_from(("+", "-", "*")),
                kids,
            ),
            st.builds(lambda x, y: f"COALESCE({x}, {y})", kids, kids),
            st.builds(lambda x: f"ABS({x})", kids),
            st.builds(
                lambda c, x, y: f"CASE WHEN {c} > 0 THEN {x} ELSE {y} END",
                kids,
                kids,
                kids,
            ),
        ),
        max_leaves=5,
    )


@st.composite
def select_query(draw: st.DrawFn, *, with_comment: bool = False) -> str:
    """A portable SELECT: projected expressions over a derived table, optionally
    joined to a second derived table, with WHERE / ORDER BY and a leading
    comment. Valid in every source dialect."""
    n = draw(st.integers(min_value=1, max_value=3))
    cols = ", ".join(f"{draw(numeric_expr())} AS c{i}" for i in range(n))
    sql = f"SELECT {cols} FROM {_DERIVED}"

    if draw(st.booleans()):
        # Exercise the joined-derived-table path (a past bug source).
        sql += " INNER JOIN (SELECT 1 AS a2, 2 AS b2) u ON t.a = u.a2"

    if draw(st.booleans()):
        col = draw(st.sampled_from(_COLUMNS))
        sql += f" WHERE t.{col} > {draw(_int_lit)}"

    if draw(st.booleans()):
        sql += " ORDER BY c0"

    if with_comment:
        sql = f"-- note {draw(_ident)}\n{sql}"

    return sql
