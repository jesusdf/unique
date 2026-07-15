# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tokenizer for procedural SQL.

Produces a stream of typed tokens from procedural SQL text, handling
string literals, comments, keywords, identifiers, and operators.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """Token types for the procedural lexer."""

    # Structural
    KEYWORD = auto()
    IDENTIFIER = auto()
    VARIABLE = auto()  # @var (T-SQL) or :var (bind)
    NUMBER = auto()
    STRING = auto()
    OPERATOR = auto()
    COMPARISON = auto()
    ASSIGN = auto()  # := (Oracle/PG)
    DOT = auto()
    COMMA = auto()
    SEMICOLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    PERCENT = auto()  # for %TYPE, %ROWTYPE
    COLON = auto()
    AT_SIGN = auto()  # @ prefix for T-SQL variables
    PIPE_PIPE = auto()  # || concatenation

    # Comments
    LINE_COMMENT = auto()
    BLOCK_COMMENT = auto()

    # Special
    NEWLINE = auto()
    WHITESPACE = auto()
    EOF = auto()
    UNKNOWN = auto()


# Keywords recognized by the procedural parser
KEYWORDS = frozenset(
    {
        "CREATE",
        "OR",
        "REPLACE",
        "ALTER",
        "DROP",
        "PROCEDURE",
        "FUNCTION",
        "TRIGGER",
        "PACKAGE",
        "BODY",
        "BEGIN",
        "END",
        "DECLARE",
        "AS",
        "IS",
        "IF",
        "THEN",
        "ELSE",
        "ELSIF",
        "ELSEIF",
        "CASE",
        "WHEN",
        "WHILE",
        "FOR",
        "LOOP",
        "IN",
        "REVERSE",
        "OPEN",
        "FETCH",
        "CLOSE",
        "DEALLOCATE",
        "CURSOR",
        "INTO",
        "NEXT",
        "FROM",
        "RETURN",
        "RETURNS",
        "RETURNING",
        "EXCEPTION",
        "RAISE",
        "RAISE_APPLICATION_ERROR",
        "RAISERROR",
        "THROW",
        "SET",
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "WITH",
        "NULL",
        "NOT",
        "AND",
        "DEFAULT",
        "OUT",
        "OUTPUT",
        "INOUT",
        "TYPE",
        "ROWTYPE",
        "EXEC",
        "EXECUTE",
        "IMMEDIATE",
        "USING",
        "PREPARE",
        "PRINT",
        "DBMS_OUTPUT",
        "TRY",
        "CATCH",
        "NOCOUNT",
        "ON",
        "OFF",
        "TABLE",
        "OF",
        "INDEX",
        "BY",
        "EXIT",
        "CONTINUE",
        "LEAVE",
        "BREAK",
        "LANGUAGE",
        "PLPGSQL",
        "SQL",
        "VOLATILE",
        "STABLE",
        "IMMUTABLE",
        "SECURITY",
        "DEFINER",
        "INVOKER",
        "BEFORE",
        "AFTER",
        "INSTEAD",
        "EACH",
        "ROW",
        "STATEMENT",
        "NEW",
        "OLD",
        "PRAGMA",
        "AUTONOMOUS_TRANSACTION",
        "EXCEPTION_INIT",
        # Transaction control and a few isolated T-SQL statement keywords.
        "TRAN",
        "TRANSACTION",
        "SAVE",
        "WORK",
        "WAITFOR",
        "DELAY",
        "IDENTITY_INSERT",
        "VARCHAR",
        "VARCHAR2",
        "NVARCHAR",
        "CHAR",
        "NCHAR",
        "INT",
        "INTEGER",
        "SMALLINT",
        "BIGINT",
        "TINYINT",
        "NUMBER",
        "NUMERIC",
        "DECIMAL",
        "FLOAT",
        "REAL",
        "DOUBLE",
        "DATE",
        "DATETIME",
        "DATETIME2",
        "TIMESTAMP",
        "TIME",
        "BOOLEAN",
        "BOOL",
        "BIT",
        "TEXT",
        "NTEXT",
        "CLOB",
        "NCLOB",
        "BLOB",
        "RAW",
        "BINARY",
        "VARBINARY",
        "IMAGE",
        "UNIQUEIDENTIFIER",
        "UUID",
        "GUID",
        "XML",
        "JSON",
        "JSONB",
        "MAX",
        "SCOPE_IDENTITY",
        "IDENTITY",
        "ROWCOUNT",
        "FOUND",
        "NOTFOUND",
        "LIKE",
        "BETWEEN",
        "EXISTS",
        "WHERE",
        "GROUP",
        "ORDER",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "JOIN",
        "INNER",
        "LEFT",
        "RIGHT",
        "FULL",
        "OUTER",
        "CROSS",
        "UNION",
        "ALL",
        "INTERSECT",
        "EXCEPT",
        "MINUS",
        "DISTINCT",
        "TOP",
        "FIRST",
        "ONLY",
        "VALUES",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "GRANT",
        "REVOKE",
        "TO",
        "CONSTRAINT",
        "PRIMARY",
        "KEY",
        "FOREIGN",
        "REFERENCES",
        "UNIQUE",
        "CHECK",
        "ASC",
        "DESC",
        "NULLS",
        "COALESCE",
        "ISNULL",
        "NVL",
        "IFNULL",
        "CAST",
        "CONVERT",
        "GETDATE",
        "SYSDATE",
        "NOW",
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "LOWER",
        "UPPER",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "SUBSTRING",
        "SUBSTR",
        "LEN",
        "LENGTH",
        "CHARINDEX",
        "INSTR",
        "TO_CHAR",
        "TO_DATE",
        "TO_NUMBER",
        "DATEDIFF",
        "DATEADD",
        "DATEPART",
        "OBJECT_ID",
        "GO",
        "PUT_LINE",
        "DUAL",
        "TRUNC",
        "ROUND",
        "ABS",
        "MOD",
        "POWER",
        "SQRT",
        "SYS_GUID",
        "NEWID",
    }
)


@dataclass(frozen=True)
class Token:
    """A single token from the lexer."""

    type: TokenType
    value: str
    line: int = 0
    column: int = 0

    @property
    def upper_value(self) -> str:
        """Return the uppercase value of the token."""
        return self.value.upper()

    def is_keyword(self, *keywords: str) -> bool:
        """Check if this token is one of the specified keywords."""
        if self.type != TokenType.KEYWORD:
            return False
        return self.upper_value in {k.upper() for k in keywords}

    def __repr__(self) -> str:
        val = self.value[:30] + "..." if len(self.value) > 30 else self.value
        return f"Token({self.type.name}, {val!r}, L{self.line})"


class Lexer:
    """Tokenizer for procedural SQL."""

    def __init__(self, sql: str, dialect: str = "tsql") -> None:
        self._sql = sql
        self._dialect = dialect
        self._pos = 0
        self._line = 1
        self._col = 1
        self._tokens: list[Token] = []
        self._tokenize()

    @property
    def tokens(self) -> list[Token]:
        """Return all tokens (excluding whitespace/newlines)."""
        return [
            t
            for t in self._tokens
            if t.type not in (TokenType.WHITESPACE, TokenType.NEWLINE)
        ]

    @property
    def all_tokens(self) -> list[Token]:
        """Return all tokens including whitespace."""
        return list(self._tokens)

    def _peek(self, offset: int = 0) -> str:
        pos = self._pos + offset
        if pos < len(self._sql):
            return self._sql[pos]
        return ""

    def _advance(self, count: int = 1) -> str:
        result = self._sql[self._pos : self._pos + count]
        for ch in result:
            if ch == "\n":
                self._line += 1
                self._col = 1
            else:
                self._col += 1
        self._pos += count
        return result

    def _at_end(self) -> bool:
        return self._pos >= len(self._sql)

    def _emit(self, token_type: TokenType, value: str, line: int, col: int) -> None:
        self._tokens.append(Token(type=token_type, value=value, line=line, column=col))

    def _tokenize(self) -> None:
        """Tokenize the entire input."""
        while not self._at_end():
            self._tokenize_one()
        self._emit(TokenType.EOF, "", self._line, self._col)

    def _tokenize_one(self) -> None:
        """Tokenize a single token from current position."""
        ch = self._peek()
        line, col = self._line, self._col

        # Whitespace (not newline)
        if ch in (" ", "\t"):
            start = self._pos
            while not self._at_end() and self._peek() in (" ", "\t"):
                self._advance()
            self._emit(TokenType.WHITESPACE, self._sql[start : self._pos], line, col)
            return

        # Newline
        if ch == "\n":
            self._advance()
            self._emit(TokenType.NEWLINE, "\n", line, col)
            return

        # Line comment
        if ch == "-" and self._peek(1) == "-":
            start = self._pos
            while not self._at_end() and self._peek() != "\n":
                self._advance()
            self._emit(TokenType.LINE_COMMENT, self._sql[start : self._pos], line, col)
            return

        # Block comment
        if ch == "/" and self._peek(1) == "*":
            start = self._pos
            self._advance(2)
            while not self._at_end():
                if self._peek() == "*" and self._peek(1) == "/":
                    self._advance(2)
                    break
                self._advance()
            self._emit(TokenType.BLOCK_COMMENT, self._sql[start : self._pos], line, col)
            return

        # String literal (single-quoted)
        if ch == "'":
            self._tokenize_string(line, col)
            return

        # N-prefixed string
        if ch in ("N", "n") and self._peek(1) == "'":
            self._advance()
            self._tokenize_string(line, col, prefix="N")
            return

        # Oracle q-quoted literal: q'[…]' / q'{…}' / q'(…)' / q'<…>' /
        # q'!…!' — the content is raw (no '' escaping) up to the closing
        # delimiter + quote. Emitted normalized to a standard single-quoted
        # string (content quotes doubled) so every consumer/target sees
        # plain quoting.
        if ch in ("Q", "q") and self._peek(1) == "'":
            open_delim = self._peek(2)
            if open_delim:
                close_delim = {"[": "]", "{": "}", "(": ")", "<": ">"}.get(
                    open_delim, open_delim
                )
                end = self._sql.find(close_delim + "'", self._pos + 3)
                if end != -1:
                    content = self._sql[self._pos + 3 : end]
                    # _advance keeps the line/column counters correct.
                    self._advance(end + 2 - self._pos)
                    normalized = "'" + content.replace("'", "''") + "'"
                    self._emit(TokenType.STRING, normalized, line, col)
                    return

        # Quoted identifier [brackets] (T-SQL)
        if ch == "[":
            start = self._pos
            self._advance()
            while not self._at_end() and self._peek() != "]":
                self._advance()
            if not self._at_end():
                self._advance()
            self._emit(TokenType.IDENTIFIER, self._sql[start : self._pos], line, col)
            return

        # Quoted identifier "double quotes"
        if ch == '"':
            start = self._pos
            self._advance()
            while not self._at_end() and self._peek() != '"':
                self._advance()
            if not self._at_end():
                self._advance()
            self._emit(TokenType.IDENTIFIER, self._sql[start : self._pos], line, col)
            return

        # Quoted identifier `backticks` (MySQL)
        if ch == "`":
            start = self._pos
            self._advance()
            while not self._at_end() and self._peek() != "`":
                self._advance()
            if not self._at_end():
                self._advance()
            self._emit(TokenType.IDENTIFIER, self._sql[start : self._pos], line, col)
            return

        # Numbers
        if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
            start = self._pos
            while not self._at_end() and (
                self._peek().isdigit() or self._peek() == "."
            ):
                self._advance()
            self._emit(TokenType.NUMBER, self._sql[start : self._pos], line, col)
            return

        # @@ system variable (T-SQL)
        if ch == "@" and self._peek(1) == "@":
            start = self._pos
            self._advance(2)
            while not self._at_end() and (
                self._peek().isalnum() or self._peek() == "_"
            ):
                self._advance()
            self._emit(TokenType.VARIABLE, self._sql[start : self._pos], line, col)
            return

        # @ variable (T-SQL)
        if ch == "@":
            start = self._pos
            self._advance()
            while not self._at_end() and (
                self._peek().isalnum() or self._peek() == "_"
            ):
                self._advance()
            self._emit(TokenType.VARIABLE, self._sql[start : self._pos], line, col)
            return

        # := assignment
        if ch == ":" and self._peek(1) == "=":
            self._advance(2)
            self._emit(TokenType.ASSIGN, ":=", line, col)
            return

        # : (bind variable prefix or label)
        if ch == ":":
            self._advance()
            self._emit(TokenType.COLON, ":", line, col)
            return

        # || concatenation
        if ch == "|" and self._peek(1) == "|":
            self._advance(2)
            self._emit(TokenType.PIPE_PIPE, "||", line, col)
            return

        # Comparison operators
        if ch == "<" and self._peek(1) == ">":
            self._advance(2)
            self._emit(TokenType.COMPARISON, "<>", line, col)
            return
        if ch == "!" and self._peek(1) == "=":
            self._advance(2)
            self._emit(TokenType.COMPARISON, "!=", line, col)
            return
        if ch == "<" and self._peek(1) == "=":
            self._advance(2)
            self._emit(TokenType.COMPARISON, "<=", line, col)
            return
        if ch == ">" and self._peek(1) == "=":
            self._advance(2)
            self._emit(TokenType.COMPARISON, ">=", line, col)
            return
        if ch in ("<", ">"):
            self._advance()
            self._emit(TokenType.COMPARISON, ch, line, col)
            return

        # => named-argument association (PL/SQL / PostgreSQL call syntax).
        # One token: splitting it into '=' + '>' re-joins as the invalid
        # ``name = > value`` in captured call-argument text.
        if ch == "=" and self._peek(1) == ">":
            self._advance(2)
            self._emit(TokenType.OPERATOR, "=>", line, col)
            return

        # = (assignment or comparison, context-dependent)
        if ch == "=":
            self._advance()
            self._emit(TokenType.OPERATOR, "=", line, col)
            return

        # Arithmetic operators
        if ch in ("+", "-", "*", "/"):
            self._advance()
            self._emit(TokenType.OPERATOR, ch, line, col)
            return

        # Punctuation
        if ch == "(":
            self._advance()
            self._emit(TokenType.LPAREN, "(", line, col)
            return
        if ch == ")":
            self._advance()
            self._emit(TokenType.RPAREN, ")", line, col)
            return
        if ch == ",":
            self._advance()
            self._emit(TokenType.COMMA, ",", line, col)
            return
        if ch == ";":
            self._advance()
            self._emit(TokenType.SEMICOLON, ";", line, col)
            return
        if ch == ".":
            self._advance()
            self._emit(TokenType.DOT, ".", line, col)
            return
        if ch == "%":
            self._advance()
            self._emit(TokenType.PERCENT, "%", line, col)
            return

        # Identifiers / keywords
        if ch.isalpha() or ch == "_" or ch == "#":
            start = self._pos
            # ``$`` continues an identifier (Oracle V$SESSION, T-SQL), but a
            # PostgreSQL source lexes dollar-quotes first: ``end$$`` must be
            # END followed by the ``$$`` close, never one identifier.
            cont = ("_", "#") if self._dialect == "postgresql" else ("_", "#", "$")
            while not self._at_end() and (
                self._peek().isalnum() or self._peek() in cont
            ):
                self._advance()
            word = self._sql[start : self._pos]
            if word.upper() in KEYWORDS:
                self._emit(TokenType.KEYWORD, word, line, col)
            else:
                self._emit(TokenType.IDENTIFIER, word, line, col)
            return

        # Unknown character
        self._advance()
        self._emit(TokenType.UNKNOWN, ch, line, col)

    def _tokenize_string(self, line: int, col: int, prefix: str = "") -> None:
        """Tokenize a single-quoted string literal, handling '' escapes."""
        start = self._pos
        self._advance()  # consume opening quote
        while not self._at_end():
            if self._peek() == "'":
                self._advance()
                if self._peek() == "'":
                    self._advance()  # escaped quote
                    continue
                break
            self._advance()
        value = self._sql[start : self._pos]
        if prefix:
            value = prefix + value
        self._emit(TokenType.STRING, value, line, col)
