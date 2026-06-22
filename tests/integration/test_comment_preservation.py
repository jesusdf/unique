# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Comment preservation across transpilation.

Original comments must survive transpilation. A standalone comment (on its own
line, between statements or inside a block) is preserved verbatim as a line
(``--``) or block (``/* */``) comment, with the only permitted change being a
single space after ``--`` per ANSI SQL. A comment that sits inside a DML
statement is preserved in place; because the DML round-trips through sqlglot
(which renders comments as ``/* */``), an inline ``--`` becomes a block comment
there, but its text and position are kept.
"""

from __future__ import annotations

import pytest

from unique.core.ast_nodes import CommentStatement
from unique.core.procedural.parser import ProceduralParser
from unique.core.transpiler import Transpiler

_TARGETS = ["oracle", "postgresql", "mysql"]


@pytest.fixture
def transpiler() -> Transpiler:
    return Transpiler()


class TestStandaloneCommentsPreserved:
    SRC = (
        "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
        "    --no space here\n"
        "    -- already spaced\n"
        "    /* a block comment */\n"
        "    DECLARE @x INT\n"
        "    IF @x > 0\n    BEGIN\n"
        "        -- inside the if block\n"
        "        SELECT 1\n"
        "    END\n"
        "    -- right before end\n"
        "END"
    )

    @pytest.mark.parametrize("target", _TARGETS)
    def test_line_comments_survive(self, transpiler: Transpiler, target: str) -> None:
        out = transpiler.transpile(self.SRC, "tsql", target).sql
        assert "-- already spaced" in out
        assert "-- inside the if block" in out
        assert "-- right before end" in out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_block_comment_survives(self, transpiler: Transpiler, target: str) -> None:
        out = transpiler.transpile(self.SRC, "tsql", target).sql
        assert "/* a block comment */" in out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_dash_space_normalized(self, transpiler: Transpiler, target: str) -> None:
        out = transpiler.transpile(self.SRC, "tsql", target).sql
        # "--no space here" must become "-- no space here".
        assert "-- no space here" in out
        assert "--no space here" not in out


class TestCommentParsing:
    def test_comment_becomes_comment_statement(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    -- a note\n"
            "    SELECT 1\n"
            "END"
        )
        res = ProceduralParser("tsql").parse(src)

        def find_comments(node: object) -> list[CommentStatement]:
            found: list[CommentStatement] = []
            if isinstance(node, CommentStatement):
                found.append(node)
            for attr in ("body", "then_body", "else_body", "statements"):
                for child in getattr(node, attr, ()) or ():
                    found.extend(find_comments(child))
            return found

        comments = find_comments(res.node)
        assert any(c.text == "-- a note" for c in comments)

    def test_line_comment_normalization(self) -> None:
        from unique.core.procedural.lexer import TokenType

        c = ProceduralParser._normalize_comment("--tight", TokenType.LINE_COMMENT)
        assert c.text == "-- tight"
        assert c.style == "line"

    def test_block_comment_kept_verbatim(self) -> None:
        from unique.core.procedural.lexer import TokenType

        c = ProceduralParser._normalize_comment(
            "/*  spaced  block  */", TokenType.BLOCK_COMMENT
        )
        assert c.text == "/*  spaced  block  */"
        assert c.style == "block"


class TestDmlInternalCommentNotCorrupting:
    """A comment inside a DML must not swallow the rest of the statement."""

    @pytest.mark.parametrize("target", _TARGETS)
    def test_mid_statement_comment_keeps_sql_intact(
        self, transpiler: Transpiler, target: str
    ) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    SELECT a, b\n"
            "    -- a mid-statement note\n"
            "    FROM t WHERE x = 1\n"
            "END"
        )
        out = transpiler.transpile(src, "tsql", target).sql
        # The FROM/WHERE must survive (the line comment must not eat them).
        assert "FROM t" in out
        assert "x = 1" in out
        # The comment text is preserved (as a block comment inside the DML).
        assert "a mid-statement note" in out
