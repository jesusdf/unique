# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for the procedural SQL lexer."""

from __future__ import annotations

from unique.core.procedural.lexer import Lexer, TokenType


def _types(sql: str, dialect: str = "tsql") -> list[TokenType]:
    return [t.type for t in Lexer(sql, dialect).tokens]


def _values(sql: str, dialect: str = "tsql") -> list[str]:
    return [t.value for t in Lexer(sql, dialect).tokens]


class TestKeywordsAndIdentifiers:
    def test_keywords_recognized(self) -> None:
        tokens = Lexer("CREATE PROCEDURE", "tsql").tokens
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].upper_value == "CREATE"
        assert tokens[1].type == TokenType.KEYWORD

    def test_identifier_recognized(self) -> None:
        tokens = Lexer("my_table", "tsql").tokens
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "my_table"

    def test_bracketed_identifier(self) -> None:
        tokens = Lexer("[my table]", "tsql").tokens
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "[my table]"

    def test_double_quoted_identifier(self) -> None:
        tokens = Lexer('"my col"', "oracle").tokens
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == '"my col"'

    def test_keyword_is_case_insensitive(self) -> None:
        tokens = Lexer("create Procedure", "tsql").tokens
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[1].type == TokenType.KEYWORD


class TestVariables:
    def test_tsql_variable(self) -> None:
        tokens = Lexer("@userId", "tsql").tokens
        assert tokens[0].type == TokenType.VARIABLE
        assert tokens[0].value == "@userId"

    def test_tsql_system_variable(self) -> None:
        tokens = Lexer("@@ROWCOUNT", "tsql").tokens
        assert tokens[0].type == TokenType.VARIABLE
        assert tokens[0].value == "@@ROWCOUNT"


class TestLiterals:
    def test_string_literal(self) -> None:
        tokens = Lexer("'hello'", "tsql").tokens
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "'hello'"

    def test_string_with_escaped_quote(self) -> None:
        tokens = Lexer("'it''s'", "tsql").tokens
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "'it''s'"

    def test_n_prefixed_string(self) -> None:
        tokens = Lexer("N'unicode'", "tsql").tokens
        assert tokens[0].type == TokenType.STRING
        assert "unicode" in tokens[0].value

    def test_number(self) -> None:
        tokens = Lexer("42", "tsql").tokens
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "42"

    def test_decimal_number(self) -> None:
        tokens = Lexer("3.14", "tsql").tokens
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "3.14"


class TestOperators:
    def test_assign_operator(self) -> None:
        assert TokenType.ASSIGN in _types("x := 1", "oracle")

    def test_comparison_operators(self) -> None:
        for op in ["<>", "!=", "<=", ">=", "<", ">"]:
            tokens = Lexer(f"a {op} b", "tsql").tokens
            assert tokens[1].type == TokenType.COMPARISON
            assert tokens[1].value == op

    def test_concatenation_operator(self) -> None:
        assert TokenType.PIPE_PIPE in _types("a || b", "oracle")

    def test_arithmetic_operators(self) -> None:
        for op in ["+", "-", "*", "/"]:
            tokens = Lexer(f"a {op} b", "tsql").tokens
            assert tokens[1].type == TokenType.OPERATOR

    def test_percent_for_type_reference(self) -> None:
        assert TokenType.PERCENT in _types("emp.sal%TYPE", "oracle")


class TestComments:
    def test_line_comment_preserved_as_token(self) -> None:
        # Comments are preserved as tokens (not whitespace) so they can be
        # retained in output.
        types = _types("SELECT -- comment\n1", "tsql")
        assert TokenType.LINE_COMMENT in types

    def test_block_comment_preserved(self) -> None:
        types = _types("SELECT /* x */ 1", "tsql")
        assert TokenType.BLOCK_COMMENT in types

    def test_keyword_inside_string_not_tokenized(self) -> None:
        # .tokens includes a trailing EOF token, so a lone string yields two.
        tokens = Lexer("'BEGIN END'", "tsql").tokens
        non_eof = [t for t in tokens if t.type != TokenType.EOF]
        assert len(non_eof) == 1
        assert non_eof[0].type == TokenType.STRING


class TestPunctuation:
    def test_parentheses(self) -> None:
        types = _types("(a)", "tsql")
        assert types[0] == TokenType.LPAREN
        assert types[2] == TokenType.RPAREN

    def test_dot_comma_semicolon(self) -> None:
        assert TokenType.DOT in _types("a.b", "tsql")
        assert TokenType.COMMA in _types("a, b", "tsql")
        assert TokenType.SEMICOLON in _types("a;", "tsql")


class TestLineTracking:
    def test_line_numbers_tracked(self) -> None:
        tokens = Lexer("CREATE\nPROCEDURE", "tsql").tokens
        assert tokens[0].line == 1
        assert tokens[1].line == 2

    def test_eof_appended(self) -> None:
        all_tokens = Lexer("x", "tsql").all_tokens
        assert all_tokens[-1].type == TokenType.EOF
