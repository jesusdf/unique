# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""MERGE comment trivia (audit 2026-07-24 N14 / brief B21).

Comments are trivia and must be preserved exactly once, correctly placed. In
the N14 probe a standalone comment before a ``WHEN`` clause disappeared on
every target (sqlglot drops mid-statement comments when it re-renders the
passthrough MERGE), while an inline ``/* */`` comment was emitted twice — once
inline and again as a trailing ``--`` line (the child-comment recovery
double-counted comments already present in the re-rendered SQL).
"""

from __future__ import annotations

import pytest

from unique.core.transpiler import Transpiler

_TARGETS = ["oracle", "postgresql", "mysql"]

# N14's exact shape: a standalone comment between ON and WHEN, plus an inline
# block comment inside the UPDATE SET.
_SRC = (
    "MERGE INTO dst AS d USING src AS s ON d.id = s.id\n"
    "-- keep totals in sync\n"
    "WHEN MATCHED THEN UPDATE SET d.qty = s.qty /* qty sync */\n"
    "WHEN NOT MATCHED THEN INSERT (id, qty) VALUES (s.id, s.qty);"
)


@pytest.fixture
def transpiler() -> Transpiler:
    return Transpiler()


class TestMergeCommentTrivia:
    @pytest.mark.parametrize("target", _TARGETS)
    def test_leading_comment_preserved_exactly_once(
        self, transpiler: Transpiler, target: str
    ) -> None:
        out = transpiler.transpile(_SRC, "tsql", target).sql
        assert out.count("keep totals in sync") == 1, out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_inline_comment_not_duplicated(
        self, transpiler: Transpiler, target: str
    ) -> None:
        out = transpiler.transpile(_SRC, "tsql", target).sql
        assert out.count("qty sync") == 1, out
