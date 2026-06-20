# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Recursive descent parser for procedural SQL.

Parses stored procedures, functions, and triggers into IR AST nodes.
Delegates embedded DML/DQL statements to sqlglot for transpilation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    ContinueStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    CursorDeclaration,
    CursorOperation,
    DataType,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
    ExceptionHandler,
    ExecuteStatement,
    ExitStatement,
    ForLoopStatement,
    IfStatement,
    Literal,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SelectIntoStatement,
    SetVariableStatement,
    StatementList,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.procedural.lexer import Lexer, Token, TokenType

logger = logging.getLogger(__name__)


@dataclass
class ParseError:
    """A parse error with context."""

    message: str
    line: int = 0
    column: int = 0


@dataclass
class ParseResult:
    """Result of parsing a procedural SQL batch."""

    node: ASTNode | None = None
    errors: list[ParseError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ProceduralParser:
    """Recursive descent parser for procedural SQL constructs.

    Handles T-SQL, Oracle PL/SQL, PostgreSQL PL/pgSQL, and MySQL
    procedural syntax.
    """

    def __init__(self, dialect: str) -> None:
        self._dialect = dialect
        self._tokens: list[Token] = []
        self._pos = 0
        self._errors: list[ParseError] = []
        self._warnings: list[str] = []

    def parse(self, sql: str) -> ParseResult:
        """Parse a procedural SQL batch into an IR AST node.

        Args:
            sql: The procedural SQL text.

        Returns:
            A ParseResult containing the AST node and any errors/warnings.
        """
        self._errors = []
        self._warnings = []

        lexer = Lexer(sql, self._dialect)
        self._tokens = lexer.tokens
        self._pos = 0

        try:
            node = self._parse_top_level()
            return ParseResult(node=node, errors=self._errors, warnings=self._warnings)
        except Exception as e:
            logger.debug("Parse failed: %s", e)
            self._errors.append(ParseError(message=str(e)))
            return ParseResult(
                node=RawSQL(sql=sql, reason=f"Parse error: {e}"),
                errors=self._errors,
                warnings=self._warnings,
            )

    # ---------------------------------------------------------------
    # Token navigation
    # ---------------------------------------------------------------

    def _current(self) -> Token:
        """Return current token."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(type=TokenType.EOF, value="", line=0, column=0)

    def _peek(self, offset: int = 0) -> Token:
        """Look ahead by offset tokens."""
        pos = self._pos + offset
        if pos < len(self._tokens):
            return self._tokens[pos]
        return Token(type=TokenType.EOF, value="", line=0, column=0)

    def _advance(self) -> Token:
        """Consume and return current token."""
        token = self._current()
        self._pos += 1
        return token

    def _skip_comments(self) -> None:
        """Skip over comment tokens."""
        while self._current().type in (
            TokenType.LINE_COMMENT,
            TokenType.BLOCK_COMMENT,
        ):
            self._advance()

    def _expect_keyword(self, *keywords: str) -> Token:
        """Consume a keyword token, raising if it doesn't match."""
        self._skip_comments()
        tok = self._current()
        if not tok.is_keyword(*keywords):
            expected = " or ".join(keywords)
            raise ValueError(
                f"Expected {expected} at line {tok.line}, "
                f"got {tok.value!r} ({tok.type.name})"
            )
        return self._advance()

    def _match_keyword(self, *keywords: str) -> Token | None:
        """Consume a keyword token if it matches, otherwise return None."""
        self._skip_comments()
        if self._current().is_keyword(*keywords):
            return self._advance()
        return None

    def _at_end(self) -> bool:
        """Check if we've consumed all tokens."""
        return self._pos >= len(self._tokens) or self._current().type == TokenType.EOF

    def _match_type(self, token_type: TokenType) -> Token | None:
        """Consume a token of the given type if it matches."""
        self._skip_comments()
        if self._current().type == token_type:
            return self._advance()
        return None

    def _expect_type(self, token_type: TokenType) -> Token:
        """Consume a token of the given type, raising if wrong."""
        self._skip_comments()
        tok = self._current()
        if tok.type != token_type:
            raise ValueError(
                f"Expected {token_type.name} at line {tok.line}, "
                f"got {tok.value!r} ({tok.type.name})"
            )
        return self._advance()

    # ---------------------------------------------------------------
    # Top-level dispatch
    # ---------------------------------------------------------------

    def _parse_top_level(self) -> ASTNode:
        """Parse the top-level construct."""
        self._skip_comments()
        tok = self._current()

        if tok.is_keyword("CREATE"):
            return self._parse_create()
        elif tok.is_keyword("ALTER") and self._dialect == "tsql":
            return self._parse_alter()
        else:
            return self._parse_fallback()

    def _parse_create(self) -> ASTNode:
        """Parse CREATE [OR REPLACE] PROCEDURE|FUNCTION|TRIGGER."""
        self._expect_keyword("CREATE")
        or_replace = False
        if self._match_keyword("OR"):
            self._expect_keyword("REPLACE")
            or_replace = True

        tok = self._current()
        if tok.is_keyword("PROCEDURE"):
            return self._parse_procedure(or_replace=or_replace, is_alter=False)
        elif tok.is_keyword("FUNCTION"):
            return self._parse_function(or_replace=or_replace)
        elif tok.is_keyword("TRIGGER"):
            return self._parse_trigger(or_replace=or_replace)
        else:
            return self._parse_fallback()

    def _parse_alter(self) -> ASTNode:
        """Parse ALTER PROCEDURE|FUNCTION (T-SQL)."""
        self._expect_keyword("ALTER")
        tok = self._current()
        if tok.is_keyword("PROCEDURE"):
            return self._parse_procedure(or_replace=True, is_alter=True)
        elif tok.is_keyword("FUNCTION"):
            return self._parse_function(or_replace=True, is_alter=True)
        else:
            return self._parse_fallback()

    # ---------------------------------------------------------------
    # Procedure parsing
    # ---------------------------------------------------------------

    def _consume_pg_routine_header(self) -> None:
        """Consume PostgreSQL routine header clauses before the body.

        Handles: LANGUAGE <lang>, [NOT] {VOLATILE|STABLE|IMMUTABLE},
        SECURITY {DEFINER|INVOKER}, AS, and the $$ / $tag$ body delimiters.
        These appear between the signature and the DECLARE/BEGIN body.
        """
        guard = 0
        while not self._at_end():
            guard += 1
            if guard > 200:
                break
            tok = self._current()

            # $$ or $tag$ dollar-quote delimiters: tokenized as '$' tokens
            if tok.type == TokenType.UNKNOWN and tok.value == "$":
                self._advance()
                # consume an optional tag and the closing '$'
                while not self._at_end() and not (
                    self._current().type == TokenType.UNKNOWN
                    and self._current().value == "$"
                ):
                    self._advance()
                if not self._at_end():
                    self._advance()  # closing '$'
                continue

            if tok.is_keyword("LANGUAGE"):
                self._advance()
                if not self._at_end():
                    self._advance()  # language name
                continue

            if tok.is_keyword("SECURITY"):
                self._advance()
                if not self._at_end():
                    self._advance()  # DEFINER/INVOKER
                continue

            if tok.is_keyword("VOLATILE", "STABLE", "IMMUTABLE"):
                self._advance()
                continue

            if tok.is_keyword("NOT"):
                self._advance()
                continue

            # MySQL routine characteristics between the signature and body:
            # DETERMINISTIC, READS/MODIFIES/NO/CONTAINS SQL [DATA],
            # LANGUAGE SQL, COMMENT '...'. Match by token value so they are
            # consumed even when tokenized as identifiers.
            upper = tok.value.upper()
            if upper == "DETERMINISTIC":
                self._advance()
                continue
            if upper in ("READS", "MODIFIES", "CONTAINS", "NO"):
                self._advance()
                # consume the following SQL [DATA] words
                while not self._at_end() and self._current().value.upper() in (
                    "SQL",
                    "DATA",
                ):
                    self._advance()
                continue
            if upper == "COMMENT":
                self._advance()
                if not self._at_end():
                    self._advance()  # the comment string literal
                continue

            if tok.is_keyword("AS"):
                self._advance()
                continue

            # Reached DECLARE/BEGIN (or anything else): header is done.
            break

    def _parse_procedure(
        self, or_replace: bool = False, is_alter: bool = False
    ) -> ASTNode:
        """Parse a stored procedure definition."""
        self._expect_keyword("PROCEDURE")
        name, schema = self._parse_qualified_name()
        params = self._parse_parameter_list()

        if self._dialect == "tsql":
            self._match_keyword("AS")
            body = self._parse_tsql_body()
        elif self._dialect in ("postgresql", "mysql"):
            self._consume_pg_routine_header()
            body = self._parse_plsql_body()
        else:
            if self._match_keyword("AS") or self._match_keyword("IS"):
                pass
            body = self._parse_plsql_body()

        if is_alter and self._dialect == "tsql":
            return AlterProcedureStatement(
                name=name,
                parameters=tuple(params),
                body=tuple(body),
                schema=schema,
            )
        return CreateProcedureStatement(
            name=name,
            parameters=tuple(params),
            body=tuple(body),
            or_replace=or_replace,
            schema=schema,
        )

    def _parse_function(
        self, or_replace: bool = False, is_alter: bool = False
    ) -> ASTNode:
        """Parse a function definition."""
        self._expect_keyword("FUNCTION")
        name, schema = self._parse_qualified_name()
        params = self._parse_parameter_list()

        return_type: DataType | None = None
        if self._match_keyword("RETURN") or self._match_keyword("RETURNS"):
            return_type = self._parse_data_type()

        if self._dialect == "tsql":
            self._match_keyword("AS")
            body = self._parse_tsql_body()
        elif self._dialect in ("postgresql", "mysql"):
            self._consume_pg_routine_header()
            body = self._parse_plsql_body()
        else:
            if self._match_keyword("AS") or self._match_keyword("IS"):
                pass
            body = self._parse_plsql_body()

        return CreateFunctionStatement(
            name=name,
            parameters=tuple(params),
            return_type=return_type,
            body=tuple(body),
            or_replace=or_replace,
            schema=schema,
        )

    def _parse_trigger(self, or_replace: bool = False) -> ASTNode:
        """Parse a trigger definition."""
        self._expect_keyword("TRIGGER")
        name, schema = self._parse_qualified_name()

        # Timing: BEFORE | AFTER | INSTEAD OF | FOR (T-SQL)
        # T-SQL puts "ON table" before the timing/events; Oracle/PG put it
        # after. Accept an optional leading ON clause first.
        table_name = ""
        if self._match_keyword("ON"):
            table_name, _ = self._parse_qualified_name()

        # Timing: BEFORE | AFTER | INSTEAD OF | FOR (T-SQL)
        timing = "AFTER"
        if self._match_keyword("BEFORE"):
            timing = "BEFORE"
        elif self._match_keyword("AFTER"):
            timing = "AFTER"
        elif self._match_keyword("INSTEAD"):
            self._match_keyword("OF")
            timing = "INSTEAD OF"
        elif self._match_keyword("FOR"):
            timing = "FOR"

        # Events: INSERT, UPDATE, DELETE
        events = []
        while True:
            tok = self._current()
            if tok.is_keyword("INSERT", "UPDATE", "DELETE"):
                events.append(self._advance().upper_value)
                if not self._match_type(TokenType.COMMA):
                    break
            else:
                break

        # ON table (Oracle/PG ordering, if not already captured)
        if not table_name and self._match_keyword("ON"):
            table_name, _ = self._parse_qualified_name()

        # FOR EACH ROW (Oracle/PG)
        for_each = "STATEMENT"
        if self._match_keyword("FOR"):
            self._match_keyword("EACH")
            if self._match_keyword("ROW"):
                for_each = "ROW"
            else:
                self._match_keyword("STATEMENT")

        # Body
        if self._dialect == "tsql":
            self._match_keyword("AS")
            body = self._parse_tsql_body()
        else:
            if self._match_keyword("AS") or self._match_keyword("IS"):
                pass
            body = self._parse_plsql_body()

        return CreateTriggerStatement(
            name=name,
            table=table_name,
            timing=timing,
            events=tuple(events),
            for_each=for_each,
            body=tuple(body),
            or_replace=or_replace,
            schema=schema,
        )

    # ---------------------------------------------------------------
    # Identifiers and names
    # ---------------------------------------------------------------

    def _parse_qualified_name(self) -> tuple[str, str | None]:
        """Parse a potentially qualified name (schema.name)."""
        self._skip_comments()
        parts: list[str] = [self._advance().value]

        while self._current().type == TokenType.DOT:
            self._advance()
            parts.append(self._advance().value)

        if len(parts) >= 2:
            return parts[-1], ".".join(parts[:-1])
        return parts[0], None

    def _parse_identifier(self) -> str:
        """Parse a single identifier or keyword used as name."""
        self._skip_comments()
        tok = self._current()
        if tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD, TokenType.VARIABLE):
            return self._advance().value
        return self._advance().value

    # ---------------------------------------------------------------
    # Parameters
    # ---------------------------------------------------------------

    def _parse_parameter_list(self) -> list[ParameterDefinition]:
        """Parse procedure/function parameter list.

        Handles both parenthesized lists (Oracle/PG/MySQL and optional
        T-SQL) and paren-less T-SQL lists terminated by AS/IS.
        """
        params: list[ParameterDefinition] = []

        has_parens = bool(self._match_type(TokenType.LPAREN))

        if has_parens:
            guard = 0
            while not self._at_end() and self._current().type != TokenType.RPAREN:
                guard += 1
                if guard > 1000:
                    break
                self._skip_comments()
                if self._current().type == TokenType.RPAREN:
                    break

                before = self._pos
                param = self._parse_parameter()
                if param:
                    params.append(param)
                self._match_type(TokenType.COMMA)
                if self._pos == before:
                    self._advance()  # prevent stall

            self._match_type(TokenType.RPAREN)
            return params

        # Paren-less T-SQL: @p1 type, @p2 type AS ...
        if self._dialect == "tsql" and self._current().type == TokenType.VARIABLE:
            guard = 0
            while not self._at_end():
                guard += 1
                if guard > 1000:
                    break
                self._skip_comments()
                if self._current().is_keyword("AS"):
                    break
                if self._current().type != TokenType.VARIABLE:
                    break

                before = self._pos
                param = self._parse_parameter()
                if param:
                    params.append(param)
                if not self._match_type(TokenType.COMMA):
                    break
                if self._pos == before:
                    self._advance()

        return params

    def _parse_parameter(self) -> ParameterDefinition | None:
        """Parse a single parameter definition."""
        self._skip_comments()

        direction = "IN"
        name = ""
        data_type: DataType | None = None
        default: ASTNode | None = None

        tok = self._current()

        if self._dialect == "tsql":
            # T-SQL: @name type [= default] [OUTPUT]
            if tok.type == TokenType.VARIABLE:
                name = self._advance().value
            else:
                name = self._parse_identifier()

            data_type = self._parse_data_type()

            if self._match_type(TokenType.OPERATOR):  # = sign for default
                default = self._parse_expression_simple(
                    stop_keywords=self._EXPR_SIMPLE_STOP_KEYWORDS
                )

            if self._match_keyword("OUTPUT", "OUT"):
                direction = "OUT"
        elif self._dialect == "mysql":
            # MySQL: [IN|OUT|INOUT] name type
            if self._match_keyword("INOUT"):
                direction = "INOUT"
            elif self._match_keyword("IN"):
                direction = "IN"
            elif self._match_keyword("OUT"):
                direction = "OUT"

            name = self._parse_identifier()
            data_type = self._parse_data_type_or_reference()

            if self._match_keyword("DEFAULT") or self._match_type(TokenType.ASSIGN):
                default = self._parse_expression_simple()
        else:
            # Oracle/PG: name [IN|OUT|INOUT] type [DEFAULT value]
            name = self._parse_identifier()

            if self._match_keyword("IN"):
                direction = "INOUT" if self._match_keyword("OUT") else "IN"
            elif self._match_keyword("OUT"):
                direction = "OUT"
            elif self._match_keyword("INOUT"):
                direction = "INOUT"

            data_type = self._parse_data_type_or_reference()

            if self._match_keyword("DEFAULT") or self._match_type(TokenType.ASSIGN):
                default = self._parse_expression_simple()

        if data_type is None:
            data_type = DataType(name="UNKNOWN")

        return ParameterDefinition(
            name=name, data_type=data_type, direction=direction, default=default
        )

    # ---------------------------------------------------------------
    # Data types
    # ---------------------------------------------------------------

    def _parse_data_type(self) -> DataType:
        """Parse a SQL data type."""
        self._skip_comments()
        type_name = self._parse_identifier()
        params: list[int] = []

        # Table variables: DECLARE @t TABLE (col type, ...). The column
        # definition list has no portable equivalent; capture it verbatim so
        # the body is preserved and a warning can be raised downstream.
        if type_name.upper() == "TABLE" and self._current().type == TokenType.LPAREN:
            depth = 0
            cols: list[str] = []
            while not self._at_end():
                tok = self._current()
                if tok.type == TokenType.LPAREN:
                    depth += 1
                elif tok.type == TokenType.RPAREN:
                    depth -= 1
                    if depth == 0:
                        cols.append(tok.value)
                        self._advance()
                        break
                cols.append(tok.value)
                self._advance()
            return DataType(name="TABLE " + " ".join(cols))

        if self._match_type(TokenType.LPAREN):
            guard = 0
            while not self._at_end() and self._current().type != TokenType.RPAREN:
                guard += 1
                if guard > 1000:
                    break
                if self._current().type == TokenType.NUMBER:
                    params.append(int(self._advance().value))
                elif self._current().is_keyword("MAX"):
                    params.append(-1)
                    self._advance()
                elif not self._match_type(TokenType.COMMA):
                    # Unrecognized token inside type params; consume it so the
                    # loop always makes progress (avoids infinite loops).
                    self._advance()
            self._match_type(TokenType.RPAREN)

        return DataType(name=type_name, params=tuple(params))

    def _parse_data_type_or_reference(self) -> DataType:
        """Parse a data type that might be a %TYPE or %ROWTYPE reference."""
        self._skip_comments()
        name_parts: list[str] = []
        name_parts.append(self._parse_identifier())

        while self._current().type == TokenType.DOT:
            self._advance()
            name_parts.append(self._parse_identifier())

        # Check for %TYPE or %ROWTYPE
        if self._current().type == TokenType.PERCENT:
            self._advance()
            type_suffix = self._parse_identifier().upper()
            if type_suffix == "TYPE":
                if len(name_parts) >= 2:
                    return DataType(name=f"{'.'.join(name_parts)}%TYPE")
                return DataType(name=f"{name_parts[0]}%TYPE")
            elif type_suffix == "ROWTYPE":
                return DataType(name=f"{'.'.join(name_parts)}%ROWTYPE")

        # Regular type with optional params
        type_name = ".".join(name_parts)
        params: list[int] = []
        if self._match_type(TokenType.LPAREN):
            guard = 0
            while not self._at_end() and self._current().type != TokenType.RPAREN:
                guard += 1
                if guard > 1000:
                    break
                if self._current().type == TokenType.NUMBER:
                    params.append(int(self._advance().value))
                elif self._current().is_keyword("MAX"):
                    params.append(-1)
                    self._advance()
                elif not self._match_type(TokenType.COMMA):
                    self._advance()
            self._match_type(TokenType.RPAREN)

        return DataType(name=type_name, params=tuple(params))

    # ---------------------------------------------------------------
    # Body parsing — T-SQL
    # ---------------------------------------------------------------

    def _run_body_loop(
        self,
        parse_stmt: object,
        stop_keywords: tuple[str, ...],
    ) -> list[ASTNode]:
        """Run a statement-parsing loop with stall protection.

        Args:
            parse_stmt: A zero-arg callable returning an ASTNode or None.
            stop_keywords: Keywords that terminate the loop.

        Returns:
            The list of parsed statements.
        """
        stmts: list[ASTNode] = []
        guard = 0
        while not self._at_end():
            guard += 1
            if guard > 100000:
                break
            if stop_keywords and self._current().is_keyword(*stop_keywords):
                break
            before = self._pos
            stmt = parse_stmt()  # type: ignore[operator]
            if stmt:
                stmts.append(stmt)
            if self._pos == before:
                # No progress — force advance to avoid infinite loop
                self._advance()
        return stmts

    def _parse_tsql_body(self) -> list[ASTNode]:
        """Parse a T-SQL procedure/function body."""
        if self._match_keyword("BEGIN"):
            stmts = self._run_body_loop(self._parse_tsql_statement, ("END",))
            self._match_keyword("END")
            return stmts
        return self._run_body_loop(self._parse_tsql_statement, ())

    def _parse_tsql_statement(self) -> ASTNode | None:
        """Parse a single T-SQL statement, guaranteeing token progress."""
        before = self._pos
        node = self._parse_tsql_statement_inner()
        if self._pos == before and not self._at_end():
            # Dispatch consumed nothing; force progress to avoid stalls.
            self._advance()
        return node

    def _parse_tsql_statement_inner(self) -> ASTNode | None:
        """Parse a single T-SQL statement inside a body."""
        self._skip_comments()
        if self._at_end():
            return None

        tok = self._current()

        if tok.is_keyword("SET"):
            return self._parse_set_statement()
        elif tok.is_keyword("DECLARE"):
            return self._parse_tsql_declare()
        elif tok.is_keyword("IF"):
            return self._parse_tsql_if()
        elif tok.is_keyword("WHILE"):
            return self._parse_tsql_while()
        elif tok.is_keyword("BEGIN"):
            return self._parse_tsql_begin_block()
        elif tok.is_keyword("RETURN"):
            return self._parse_return()
        elif tok.is_keyword("EXEC", "EXECUTE"):
            return self._parse_tsql_exec()
        elif tok.is_keyword("PRINT"):
            return self._parse_print()
        elif tok.is_keyword("RAISERROR", "THROW"):
            return self._parse_raiserror()
        elif tok.is_keyword("TRY"):
            return self._parse_tsql_try_catch()
        elif tok.is_keyword("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "WITH"):
            return self._parse_embedded_dml()
        elif tok.type == TokenType.SEMICOLON:
            self._advance()
            return None
        else:
            return self._parse_embedded_dml()

    def _parse_set_statement(self) -> ASTNode | None:
        """Parse SET @var = expr or SET NOCOUNT ON."""
        self._expect_keyword("SET")
        tok = self._current()

        # SET NOCOUNT ON/OFF — skip these
        if tok.is_keyword(
            "NOCOUNT",
            "QUOTED_IDENTIFIER",
            "ANSI_NULLS",
            "XACT_ABORT",
            "ARITHABORT",
            "ROWCOUNT",
        ):
            kw = self._advance().value
            # These options take a short argument (ON/OFF or a value/var).
            # T-SQL statements often omit the trailing semicolon, so we must
            # NOT scan to the next ';' (that would swallow the whole body).
            # Consume at most one argument token (ON/OFF or a value).
            if self._current().is_keyword("ON", "OFF") or self._current().type in (
                TokenType.NUMBER,
                TokenType.VARIABLE,
                TokenType.IDENTIFIER,
            ):
                self._advance()
            self._match_type(TokenType.SEMICOLON)
            self._warnings.append(f"SET {kw} skipped (no equivalent)")
            return RawSQL(sql=f"SET {kw}", reason="Dialect-specific SET option")

        # SET @variable = expression
        if tok.type == TokenType.VARIABLE:
            var_name = self._advance().value
            self._match_type(TokenType.OPERATOR)  # =
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            return SetVariableStatement(name=var_name, value=expr)

        return self._parse_embedded_dml()

    def _parse_tsql_declare(self) -> ASTNode:
        """Parse DECLARE @var type [= value] [, @var2 type [= value] ...].

        T-SQL allows several comma-separated variable declarations in a
        single DECLARE; they expand to one DeclareStatement each.
        """
        self._expect_keyword("DECLARE")

        declarations: list[ASTNode] = []
        while True:
            tok = self._current()
            if tok.type == TokenType.VARIABLE:
                var_name = self._advance().value
            else:
                var_name = self._parse_identifier()

            # CURSOR declaration (always single).
            if self._current().is_keyword("CURSOR"):
                self._advance()
                query: ASTNode | None = None
                if self._match_keyword("FOR"):
                    query = self._parse_embedded_dml()
                return CursorDeclaration(name=var_name, query=query)

            data_type = self._parse_data_type()
            default: ASTNode | None = None
            if self._match_type(TokenType.OPERATOR):  # =
                default = self._parse_declare_default()

            declarations.append(
                DeclareStatement(name=var_name, data_type=data_type, default=default)
            )

            # Another variable in the same DECLARE?
            if not self._match_type(TokenType.COMMA):
                break

        self._match_type(TokenType.SEMICOLON)
        if len(declarations) == 1:
            return declarations[0]
        return StatementList(statements=tuple(declarations))

    def _parse_tsql_if(self) -> ASTNode:
        """Parse T-SQL IF ... BEGIN...END [ELSE BEGIN...END]."""
        self._expect_keyword("IF")
        condition = self._parse_expression_until_keyword(
            "BEGIN",
            "SET",
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "EXEC",
            "EXECUTE",
            "RETURN",
            "PRINT",
            "RAISERROR",
            "THROW",
        )

        then_body: list[ASTNode] = []
        if self._current().is_keyword("BEGIN"):
            node = self._parse_tsql_begin_block()
            if isinstance(node, BeginEndBlock):
                then_body = list(node.statements)
            else:
                then_body = [node]
        else:
            stmt = self._parse_tsql_statement()
            if stmt:
                then_body = [stmt]

        else_body: list[ASTNode] = []
        if self._match_keyword("ELSE"):
            if self._current().is_keyword("BEGIN"):
                node = self._parse_tsql_begin_block()
                if isinstance(node, BeginEndBlock):
                    else_body = list(node.statements)
                else:
                    else_body = [node]
            elif self._current().is_keyword("IF"):
                nested_if = self._parse_tsql_if()
                else_body = [nested_if]
            else:
                stmt = self._parse_tsql_statement()
                if stmt:
                    else_body = [stmt]

        return IfStatement(
            condition=condition,
            then_body=tuple(then_body),
            else_body=tuple(else_body),
        )

    def _parse_tsql_while(self) -> ASTNode:
        """Parse T-SQL WHILE ... BEGIN...END."""
        self._expect_keyword("WHILE")
        condition = self._parse_expression_until_keyword("BEGIN")

        body: list[ASTNode] = []
        if self._current().is_keyword("BEGIN"):
            node = self._parse_tsql_begin_block()
            if isinstance(node, BeginEndBlock):
                body = list(node.statements)
        else:
            stmt = self._parse_tsql_statement()
            if stmt:
                body = [stmt]

        return WhileStatement(condition=condition, body=tuple(body))

    def _parse_tsql_begin_block(self) -> ASTNode:
        """Parse BEGIN...END block."""
        self._expect_keyword("BEGIN")

        # Check for BEGIN TRY
        if self._current().is_keyword("TRY"):
            self._advance()
            return self._parse_tsql_try_catch_inner()

        stmts: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            stmt = self._parse_tsql_statement()
            if stmt:
                stmts.append(stmt)

        self._match_keyword("END")
        self._match_type(TokenType.SEMICOLON)
        return BeginEndBlock(statements=tuple(stmts))

    def _parse_tsql_try_catch(self) -> ASTNode:
        """Parse BEGIN TRY...END TRY BEGIN CATCH...END CATCH."""
        self._expect_keyword("BEGIN")
        self._expect_keyword("TRY")
        return self._parse_tsql_try_catch_inner()

    def _parse_tsql_try_catch_inner(self) -> ASTNode:
        """Parse the internals of TRY...CATCH after BEGIN TRY consumed."""
        try_body: list[ASTNode] = []
        while not self._at_end():
            if self._current().is_keyword("END"):
                self._advance()
                if self._match_keyword("TRY"):
                    break
            stmt = self._parse_tsql_statement()
            if stmt:
                try_body.append(stmt)

        catch_body: list[ASTNode] = []
        if self._match_keyword("BEGIN"):
            self._expect_keyword("CATCH")
            while not self._at_end():
                if self._current().is_keyword("END"):
                    self._advance()
                    if self._match_keyword("CATCH"):
                        break
                stmt = self._parse_tsql_statement()
                if stmt:
                    catch_body.append(stmt)

        return TryCatchBlock(try_body=tuple(try_body), catch_body=tuple(catch_body))

    def _parse_tsql_exec(self) -> ASTNode:
        """Parse EXEC/EXECUTE statement."""
        self._advance()  # EXEC/EXECUTE
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return ExecuteStatement(sql_expression=expr)

    # ---------------------------------------------------------------
    # Body parsing — PL/SQL (Oracle) and PL/pgSQL
    # ---------------------------------------------------------------

    def _parse_plsql_body(self) -> list[ASTNode]:
        """Parse a PL/SQL procedure/function body (DECLARE...BEGIN...END)."""
        stmts: list[ASTNode] = []

        # Optional DECLARE section (before BEGIN)
        guard = 0
        while not self._at_end() and not self._current().is_keyword("BEGIN"):
            guard += 1
            if guard > 100000:
                break
            if self._current().is_keyword("DECLARE"):
                self._advance()
                continue
            before = self._pos
            decl = self._parse_plsql_declaration()
            if decl:
                stmts.append(decl)
            if self._pos == before:
                self._advance()

        # BEGIN ... END block
        if self._match_keyword("BEGIN"):
            guard = 0
            while not self._at_end() and not self._current().is_keyword("END"):
                guard += 1
                if guard > 100000:
                    break
                if self._current().is_keyword("EXCEPTION"):
                    stmts.append(self._parse_plsql_exception())
                    continue
                before = self._pos
                stmt = self._parse_plsql_statement()
                if stmt:
                    stmts.append(stmt)
                if self._pos == before:
                    self._advance()

            self._match_keyword("END")
            # Optional procedure/function name after END
            if self._current().type in (
                TokenType.IDENTIFIER,
                TokenType.KEYWORD,
            ) and not self._current().is_keyword("IF", "LOOP", "CASE"):
                self._advance()
            self._match_type(TokenType.SEMICOLON)

        return stmts

    def _parse_plsql_declaration(self) -> ASTNode | None:
        """Parse a PL/SQL declaration (variable, cursor, etc.)."""
        self._skip_comments()
        if self._at_end() or self._current().is_keyword("BEGIN"):
            return None

        tok = self._current()

        # CURSOR name IS SELECT ...
        if tok.is_keyword("CURSOR"):
            self._advance()
            cursor_name = self._parse_identifier()
            query: ASTNode | None = None
            if self._match_keyword("IS") or self._match_keyword("FOR"):
                query = self._parse_embedded_dml()
            self._match_type(TokenType.SEMICOLON)
            return CursorDeclaration(name=cursor_name, query=query)

        # Variable: name type [:= value];
        name = self._parse_identifier()

        # Check for type_reference (%TYPE, %ROWTYPE)
        data_type = self._parse_data_type_or_reference()

        default: ASTNode | None = None
        if self._match_type(TokenType.ASSIGN) or self._match_keyword("DEFAULT"):
            default = self._parse_expression_until_semicolon()

        self._match_type(TokenType.SEMICOLON)
        return DeclareStatement(name=name, data_type=data_type, default=default)

    def _parse_plsql_statement(self) -> ASTNode | None:
        """Parse a single PL/SQL statement, guaranteeing token progress."""
        before = self._pos
        node = self._parse_plsql_statement_inner()
        if self._pos == before and not self._at_end():
            self._advance()
        return node

    def _parse_plsql_statement_inner(self) -> ASTNode | None:
        """Parse a single PL/SQL statement."""
        self._skip_comments()
        if self._at_end():
            return None

        tok = self._current()

        if tok.is_keyword("DECLARE"):
            # MySQL places variable declarations inside BEGIN ... END.
            self._advance()
            return self._parse_plsql_declaration()
        if tok.is_keyword("SET"):
            # MySQL assignment: SET var = expr;
            return self._parse_mysql_set()
        if tok.is_keyword("IF"):
            return self._parse_plsql_if()
        elif tok.is_keyword("WHILE"):
            return self._parse_plsql_while()
        elif tok.is_keyword("FOR"):
            return self._parse_plsql_for()
        elif tok.is_keyword("LOOP"):
            return self._parse_plsql_loop()
        elif tok.is_keyword("OPEN"):
            return self._parse_plsql_open()
        elif tok.is_keyword("FETCH"):
            return self._parse_plsql_fetch()
        elif tok.is_keyword("CLOSE"):
            return self._parse_plsql_close()
        elif tok.is_keyword("RETURN"):
            return self._parse_return()
        elif tok.is_keyword("RAISE") or tok.is_keyword("RAISE_APPLICATION_ERROR"):
            return self._parse_plsql_raise()
        elif tok.is_keyword("EXECUTE"):
            return self._parse_plsql_execute_immediate()
        elif tok.is_keyword("EXIT"):
            return self._parse_exit()
        elif tok.is_keyword("CONTINUE"):
            return self._parse_continue()
        elif tok.is_keyword("NULL"):
            self._advance()
            self._match_type(TokenType.SEMICOLON)
            return NullStatement()
        elif tok.is_keyword("BEGIN"):
            return self._parse_plsql_nested_begin()
        elif tok.is_keyword("SELECT"):
            return self._parse_plsql_select_or_dml()
        elif tok.is_keyword("INSERT", "UPDATE", "DELETE", "MERGE"):
            return self._parse_embedded_dml()
        elif tok.is_keyword("DBMS_OUTPUT"):
            return self._parse_dbms_output()
        elif tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            # Could be assignment: name := expr; or procedure call
            return self._parse_plsql_assignment_or_call()
        elif tok.type == TokenType.SEMICOLON:
            self._advance()
            return None
        else:
            return self._parse_embedded_dml()

    def _parse_plsql_if(self) -> ASTNode:
        """Parse PL/SQL IF ... THEN ... [ELSIF ... THEN ...] [ELSE ...] END IF."""
        self._expect_keyword("IF")
        condition = self._parse_expression_until_keyword("THEN")
        self._expect_keyword("THEN")

        then_body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword(
            "ELSIF", "ELSEIF", "ELSE", "END"
        ):
            stmt = self._parse_plsql_statement()
            if stmt:
                then_body.append(stmt)

        # Handle ELSIF chains
        else_body: list[ASTNode] = []
        if self._current().is_keyword("ELSIF", "ELSEIF"):
            nested_if = self._parse_plsql_if_no_end()
            else_body = [nested_if]
        elif self._match_keyword("ELSE"):
            while not self._at_end() and not self._current().is_keyword("END"):
                stmt = self._parse_plsql_statement()
                if stmt:
                    else_body.append(stmt)

        if self._match_keyword("END"):
            self._match_keyword("IF")
            self._match_type(TokenType.SEMICOLON)

        return IfStatement(
            condition=condition,
            then_body=tuple(then_body),
            else_body=tuple(else_body),
        )

    def _parse_plsql_if_no_end(self) -> ASTNode:
        """Parse ELSIF/ELSEIF ... THEN without consuming final END IF."""
        self._advance()  # ELSIF/ELSEIF
        condition = self._parse_expression_until_keyword("THEN")
        self._expect_keyword("THEN")

        then_body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword(
            "ELSIF", "ELSEIF", "ELSE", "END"
        ):
            stmt = self._parse_plsql_statement()
            if stmt:
                then_body.append(stmt)

        else_body: list[ASTNode] = []
        if self._current().is_keyword("ELSIF", "ELSEIF"):
            nested_if = self._parse_plsql_if_no_end()
            else_body = [nested_if]
        elif self._match_keyword("ELSE"):
            while not self._at_end() and not self._current().is_keyword("END"):
                stmt = self._parse_plsql_statement()
                if stmt:
                    else_body.append(stmt)

        return IfStatement(
            condition=condition,
            then_body=tuple(then_body),
            else_body=tuple(else_body),
        )

    def _parse_plsql_while(self) -> ASTNode:
        """Parse PL/SQL WHILE ... LOOP ... END LOOP."""
        self._expect_keyword("WHILE")
        condition = self._parse_expression_until_keyword("LOOP")
        self._expect_keyword("LOOP")

        body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            stmt = self._parse_plsql_statement()
            if stmt:
                body.append(stmt)

        self._match_keyword("END")
        self._match_keyword("LOOP")
        self._match_type(TokenType.SEMICOLON)

        return WhileStatement(condition=condition, body=tuple(body))

    def _parse_plsql_for(self) -> ASTNode:
        """Parse PL/SQL FOR ... IN ... LOOP ... END LOOP."""
        self._expect_keyword("FOR")
        var_name = self._parse_identifier()
        self._expect_keyword("IN")

        cursor = self._parse_expression_until_keyword("LOOP")
        self._expect_keyword("LOOP")

        body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            stmt = self._parse_plsql_statement()
            if stmt:
                body.append(stmt)

        self._match_keyword("END")
        self._match_keyword("LOOP")
        self._match_type(TokenType.SEMICOLON)

        return ForLoopStatement(variable=var_name, cursor=cursor, body=tuple(body))

    def _parse_plsql_loop(self) -> ASTNode:
        """Parse PL/SQL LOOP ... END LOOP."""
        self._expect_keyword("LOOP")
        body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            stmt = self._parse_plsql_statement()
            if stmt:
                body.append(stmt)
        self._match_keyword("END")
        self._match_keyword("LOOP")
        self._match_type(TokenType.SEMICOLON)
        return LoopStatement(body=tuple(body))

    def _parse_plsql_open(self) -> ASTNode:
        """Parse OPEN cursor [FOR select]."""
        self._expect_keyword("OPEN")
        cursor_name = self._parse_identifier()
        query: ASTNode | None = None
        if self._match_keyword("FOR"):
            query = self._parse_embedded_dml()
        else:
            self._match_type(TokenType.SEMICOLON)
        return CursorOperation(operation="OPEN", cursor_name=cursor_name, query=query)

    def _parse_plsql_fetch(self) -> ASTNode:
        """Parse FETCH cursor INTO vars."""
        self._expect_keyword("FETCH")
        cursor_name = self._parse_identifier()
        into_vars: list[str] = []
        if self._match_keyword("INTO"):
            while not self._at_end() and self._current().type != TokenType.SEMICOLON:
                into_vars.append(self._parse_identifier())
                if not self._match_type(TokenType.COMMA):
                    break
        self._match_type(TokenType.SEMICOLON)
        return CursorOperation(
            operation="FETCH",
            cursor_name=cursor_name,
            into_vars=tuple(into_vars),
        )

    def _parse_plsql_close(self) -> ASTNode:
        """Parse CLOSE cursor."""
        self._expect_keyword("CLOSE")
        cursor_name = self._parse_identifier()
        self._match_type(TokenType.SEMICOLON)
        return CursorOperation(operation="CLOSE", cursor_name=cursor_name)

    def _parse_mysql_set(self) -> ASTNode:
        """Parse a MySQL SET assignment: SET var = expr;"""
        self._expect_keyword("SET")
        target = self._parse_identifier()
        self._match_type(TokenType.OPERATOR)  # =
        value = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return AssignmentStatement(target=target, value=value)

    def _parse_plsql_raise(self) -> ASTNode:
        """Parse RAISE / RAISE_APPLICATION_ERROR / PostgreSQL RAISE level.

        PostgreSQL: RAISE NOTICE|INFO|LOG|DEBUG 'msg' -> informational
        (mapped to a PrintStatement); RAISE EXCEPTION|WARNING 'msg' or a
        bare RAISE -> RaiseErrorStatement.
        """
        tok = self._advance()
        if tok.upper_value == "RAISE_APPLICATION_ERROR":
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            return RaiseErrorStatement(message=expr)

        # PostgreSQL RAISE with a level keyword
        level = self._current()
        if level.type in (TokenType.KEYWORD, TokenType.IDENTIFIER) and (
            level.upper_value
            in ("NOTICE", "INFO", "LOG", "DEBUG", "WARNING", "EXCEPTION")
        ):
            self._advance()
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            if level.upper_value in ("NOTICE", "INFO", "LOG", "DEBUG"):
                return PrintStatement(expression=expr)
            return RaiseErrorStatement(message=expr)

        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return RaiseErrorStatement(message=expr)

    def _parse_plsql_execute_immediate(self) -> ASTNode:
        """Parse EXECUTE IMMEDIATE expr [USING bind1, bind2, ...].

        The optional USING clause supplies bind variables for the dynamic
        statement (Oracle). They are captured separately so each target can
        emit the appropriate form (PG keeps USING; T-SQL uses sp_executesql).
        """
        self._expect_keyword("EXECUTE")
        self._expect_keyword("IMMEDIATE")
        expr = self._parse_expression_until_keyword("USING")

        params: list[ASTNode] = []
        if self._match_keyword("USING"):
            while not self._at_end():
                # Oracle allows IN/OUT markers on bind args; skip them.
                self._match_keyword("IN")
                self._match_keyword("OUT")
                param = self._parse_expression_until_comma_or_semicolon()
                if isinstance(param, RawSQL) and param.sql:
                    params.append(param)
                if not self._match_type(TokenType.COMMA):
                    break

        self._match_type(TokenType.SEMICOLON)
        return ExecuteStatement(sql_expression=expr, params=tuple(params))

    def _parse_plsql_exception(self) -> ASTNode:
        """Parse EXCEPTION block."""
        self._expect_keyword("EXCEPTION")
        handlers: list[ExceptionHandler] = []

        while not self._at_end() and self._current().is_keyword("WHEN"):
            self._advance()
            exception_name = self._parse_identifier()
            self._expect_keyword("THEN")
            body: list[ASTNode] = []
            while not self._at_end() and not self._current().is_keyword("WHEN", "END"):
                stmt = self._parse_plsql_statement()
                if stmt:
                    body.append(stmt)
            handlers.append(
                ExceptionHandler(exception_name=exception_name, body=tuple(body))
            )

        return ExceptionBlock(handlers=tuple(handlers))

    def _parse_plsql_nested_begin(self) -> ASTNode:
        """Parse nested BEGIN...END block within PL/SQL."""
        self._expect_keyword("BEGIN")
        stmts: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            if self._current().is_keyword("EXCEPTION"):
                stmts.append(self._parse_plsql_exception())
                continue
            stmt = self._parse_plsql_statement()
            if stmt:
                stmts.append(stmt)
        self._match_keyword("END")
        self._match_type(TokenType.SEMICOLON)
        return BeginEndBlock(statements=tuple(stmts))

    def _parse_plsql_select_or_dml(self) -> ASTNode:
        """Parse SELECT that might have INTO (PL/SQL SELECT INTO).

        PL/SQL: SELECT col1, col2 INTO var1, var2 FROM ...
        We capture the select-list, the INTO targets, and the remainder
        (FROM onward) so the emitter can produce the right target syntax.
        """
        start = self._pos
        self._expect_keyword("SELECT")

        # Capture select list up to INTO or FROM
        select_parts: list[str] = []
        paren_depth = 0
        has_into = False
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.is_keyword("INTO"):
                has_into = True
                break
            if paren_depth == 0 and tok.is_keyword("FROM"):
                break
            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            select_parts.append(tok.value)
            self._advance()

        if not has_into:
            # Not a SELECT INTO — reparse as embedded DML
            self._pos = start
            return self._parse_embedded_dml()

        # Consume INTO and capture target variables
        self._expect_keyword("INTO")
        into_vars: list[str] = []
        while not self._at_end():
            tok = self._current()
            if tok.is_keyword("FROM") or tok.type == TokenType.SEMICOLON:
                break
            if tok.type in (
                TokenType.IDENTIFIER,
                TokenType.KEYWORD,
                TokenType.VARIABLE,
            ):
                into_vars.append(tok.value)
                self._advance()
                if not self._match_type(TokenType.COMMA):
                    break
            else:
                self._advance()

        # Capture remainder (FROM onward) as raw SQL
        rest_parts: list[str] = []
        paren_depth = 0
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
                self._advance()
                break
            if paren_depth == 0 and tok.is_keyword("END"):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            rest_parts.append(tok.value)
            self._advance()

        from unique.core.ast_nodes import RawSQL as _RawSQL

        select_list = " ".join(select_parts).strip()
        rest_sql = " ".join(rest_parts).strip()
        return SelectIntoStatement(
            columns=(_RawSQL(sql=select_list, reason="select list"),),
            into_vars=tuple(into_vars),
            rest_sql=rest_sql,
        )

    def _parse_plsql_assignment_or_call(self) -> ASTNode:
        """Parse name := expr; or procedure_call(args);"""
        self._skip_comments()
        name_parts: list[str] = [self._parse_identifier()]

        while self._current().type == TokenType.DOT:
            self._advance()
            name_parts.append(self._parse_identifier())

        full_name = ".".join(name_parts)

        # Assignment: name := expr;
        if self._current().type == TokenType.ASSIGN:
            self._advance()
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            return AssignmentStatement(target=full_name, value=expr)

        # DBMS_OUTPUT.PUT_LINE(...)
        if full_name.upper() == "DBMS_OUTPUT" and self._current().type == TokenType.DOT:
            self._advance()
            method = self._parse_identifier()
            if method.upper() == "PUT_LINE":
                expr = self._parse_expression_until_semicolon()
                self._match_type(TokenType.SEMICOLON)
                return PrintStatement(expression=expr)

        # Procedure call or other statement
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return EmbeddedDML(
            sql=f"{full_name} {expr.sql if isinstance(expr, RawSQL) else ''}"
        )

    def _parse_dbms_output(self) -> ASTNode:
        """Parse DBMS_OUTPUT.PUT_LINE(expr)."""
        self._advance()  # DBMS_OUTPUT
        self._match_type(TokenType.DOT)
        self._match_keyword("PUT_LINE")
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return PrintStatement(expression=expr)

    # ---------------------------------------------------------------
    # Shared statement parsers
    # ---------------------------------------------------------------

    def _parse_return(self) -> ASTNode:
        """Parse RETURN [expression]."""
        self._expect_keyword("RETURN")
        if self._current().type == TokenType.SEMICOLON or self._at_end():
            self._match_type(TokenType.SEMICOLON)
            return ReturnStatement()
        value = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return ReturnStatement(value=value)

    def _parse_print(self) -> ASTNode:
        """Parse PRINT expression."""
        self._expect_keyword("PRINT")
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return PrintStatement(expression=expr)

    def _parse_raiserror(self) -> ASTNode:
        """Parse RAISERROR or THROW."""
        self._advance()
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return RaiseErrorStatement(message=expr)

    def _parse_exit(self) -> ASTNode:
        """Parse EXIT [WHEN condition]."""
        self._expect_keyword("EXIT")
        condition: ASTNode | None = None
        if self._match_keyword("WHEN"):
            condition = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return ExitStatement(condition=condition)

    def _parse_continue(self) -> ASTNode:
        """Parse CONTINUE [WHEN condition]."""
        self._advance()
        condition: ASTNode | None = None
        if self._match_keyword("WHEN"):
            condition = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return ContinueStatement(condition=condition)

    # ---------------------------------------------------------------
    # Expression parsing (simplified — captures raw SQL)
    # ---------------------------------------------------------------

    def _parse_expression_until_semicolon(self) -> ASTNode:
        """Capture tokens as raw SQL until we hit a semicolon or END."""
        return self._capture_raw_until(TokenType.SEMICOLON)

    def _parse_expression_until_keyword(self, *keywords: str) -> ASTNode:
        """Capture tokens as raw SQL until a keyword, semicolon, or END.

        A stop keyword immediately followed by '(' is treated as a function
        call (e.g. the trigger predicate ``UPDATE(col)``, or ``EXISTS(...)``)
        rather than a statement boundary, so it is captured into the
        expression.
        """
        parts: list[str] = []
        paren_depth = 0
        first = True
        while not self._at_end():
            tok = self._current()
            is_call = (
                tok.type == TokenType.KEYWORD and self._peek(1).type == TokenType.LPAREN
            )
            if (
                paren_depth == 0
                and not (first and is_call)
                and tok.is_keyword(*keywords)
                and not is_call
            ):
                break
            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
                break
            if paren_depth == 0 and tok.is_keyword("END"):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            parts.append(tok.value)
            self._advance()
            first = False
        return RawSQL(sql=" ".join(parts).strip(), reason="expression")

    def _parse_expression_until_comma_or_semicolon(self) -> ASTNode:
        """Capture a single comma-separated argument (e.g. a bind variable)."""
        parts: list[str] = []
        paren_depth = 0
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type in (
                TokenType.COMMA,
                TokenType.SEMICOLON,
            ):
                break
            if paren_depth == 0 and tok.is_keyword("END"):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            parts.append(tok.value)
            self._advance()
        return RawSQL(sql=" ".join(parts).strip(), reason="bind argument")

    # DML verbs that can start a standalone statement after a DECLARE default
    # (no semicolon separator). These are NOT in _TSQL_STMT_BOUNDARY_KEYWORDS
    # (which excludes DML) but must terminate a DECLARE = <expr> context.
    _DECLARE_DML_BOUNDARY = frozenset(
        {"SELECT", "UPDATE", "DELETE", "INSERT", "MERGE", "WITH"}
    )

    def _parse_declare_default(self) -> ASTNode:
        """Capture a DECLARE default value.

        Stops at a comma (next variable in the same DECLARE), a semicolon,
        END, or a T-SQL statement boundary (so a semicolon-less DECLARE does
        not absorb the statement that follows it).
        """
        parts: list[str] = []
        paren_depth = 0
        case_depth = 0
        first = True
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type in (
                TokenType.COMMA,
                TokenType.SEMICOLON,
            ):
                break
            # A trailing inline comment after the expression value (at depth 0)
            # signals end-of-statement; stop here so the emitter places the
            # terminator BEFORE the comment and not inside it.
            if paren_depth == 0 and tok.type == TokenType.LINE_COMMENT and not first:
                break
            if paren_depth == 0 and tok.is_keyword("END"):
                if case_depth > 0:
                    case_depth -= 1
                else:
                    break
            elif paren_depth == 0 and tok.is_keyword("CASE"):
                case_depth += 1
            if (
                not first
                and paren_depth == 0
                and case_depth == 0
                and self._at_tsql_stmt_boundary()
            ):
                break
            # DML verbs on their own (outside any expression) terminate the
            # DECLARE value even without a semicolon (T-SQL semicolons optional).
            if (
                not first
                and paren_depth == 0
                and case_depth == 0
                and self._dialect == "tsql"
                and tok.type == TokenType.KEYWORD
                and tok.upper_value in self._DECLARE_DML_BOUNDARY
            ):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            parts.append(tok.value)
            self._advance()
            first = False
        return RawSQL(sql=" ".join(parts).strip(), reason="default value")

    # Keywords that cannot appear in a parameter default value expression
    # (only at paren_depth == 0 — AS inside CAST(x AS INT) is fine).
    _EXPR_SIMPLE_STOP_KEYWORDS = frozenset(
        {"AS", "IS", "OUTPUT", "OUT", "READONLY", "VARYING"}
    )

    def _parse_expression_simple(
        self,
        stop_keywords: frozenset[str] | None = None,
    ) -> ASTNode:
        """Parse a simple expression (for default values, etc.)."""
        effective_stop = stop_keywords or frozenset()
        parts: list[str] = []
        paren_depth = 0
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type in (
                TokenType.COMMA,
                TokenType.RPAREN,
                TokenType.SEMICOLON,
            ):
                break
            if (
                paren_depth == 0
                and tok.type == TokenType.KEYWORD
                and tok.upper_value in effective_stop
            ):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                if paren_depth == 0:
                    break
                paren_depth -= 1
            parts.append(tok.value)
            self._advance()
        raw = " ".join(parts).strip()
        if raw.upper() == "NULL":
            return Literal(value=None, dtype="null")
        return RawSQL(sql=raw, reason="expression")

    def _capture_raw_until(self, *stop_types: TokenType) -> ASTNode:
        """Capture tokens as raw SQL until a stop token type or END.

        For T-SQL (where the trailing semicolon is often omitted), also
        stops at the next statement boundary so a single expression does
        not absorb the statements that follow it. The first token is always
        consumed to guarantee progress.
        """
        parts: list[str] = []
        paren_depth = 0
        case_depth = 0
        first = True
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type in stop_types:
                break
            if paren_depth == 0 and tok.is_keyword("END"):
                if case_depth > 0:
                    case_depth -= 1
                else:
                    break
            elif paren_depth == 0 and tok.is_keyword("CASE"):
                case_depth += 1
            if (
                not first
                and paren_depth == 0
                and case_depth == 0
                and self._at_tsql_stmt_boundary()
            ):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            parts.append(tok.value)
            self._advance()
            first = False
        return RawSQL(sql=" ".join(parts).strip(), reason="captured expression")

    # Control-flow keywords that unambiguously begin a new T-SQL statement
    # at depth 0. DML keywords (SELECT/INSERT/UPDATE/DELETE/MERGE) are
    # excluded because they chain (e.g. INSERT ... SELECT). SET is handled
    # separately: "SET @var" is an assignment, "SET col" is an UPDATE clause.
    _TSQL_STMT_BOUNDARY_KEYWORDS = frozenset(
        {
            "IF",
            "WHILE",
            "DECLARE",
            "PRINT",
            "RETURN",
            "RAISERROR",
            "THROW",
            "ELSE",
            "EXEC",
            "EXECUTE",
        }
    )

    def _at_tsql_stmt_boundary(self) -> bool:
        """Whether the current token begins a new T-SQL statement.

        Used to delimit statements that omit the trailing semicolon. Only
        active for the T-SQL dialect; Oracle/PG/MySQL rely on semicolons.
        """
        if self._dialect != "tsql":
            return False
        tok = self._current()
        if tok.type != TokenType.KEYWORD:
            return False
        upper = tok.upper_value
        if upper in self._TSQL_STMT_BOUNDARY_KEYWORDS:
            return True
        # Standalone "SET @var = ..." assignment (distinct from the SET
        # clause of an UPDATE, where the target is a column identifier).
        return upper == "SET" and self._peek(1).type == TokenType.VARIABLE

    # ---------------------------------------------------------------
    # Embedded DML (delegated to sqlglot later)
    # ---------------------------------------------------------------

    def _parse_embedded_dml(self) -> ASTNode:
        """Capture a DML statement for later sqlglot transpilation.

        Stops at a semicolon or an unmatched END. For T-SQL, also stops at
        the next statement boundary (control-flow keyword or standalone SET
        assignment) so semicolon-less statements are bounded. The leading
        keyword is always consumed first to guarantee progress and to keep
        chained DML such as INSERT ... SELECT together.
        """
        parts: list[str] = []
        paren_depth = 0
        begin_depth = 0
        case_depth = 0
        first = True
        prev_tok: Token | None = None
        lead_verb = (
            self._current().upper_value
            if self._current().type == TokenType.KEYWORD
            else ""
        )

        while not self._at_end():
            tok = self._current()

            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
                self._advance()
                break

            if (
                not first
                and paren_depth == 0
                and begin_depth == 0
                and case_depth == 0
                and self._at_tsql_stmt_boundary()
            ):
                break

            # Boundary between two semicolon-less DML statements: a new DML
            # verb on a new line whose preceding token does not chain it
            # (so INSERT ... SELECT, UNION, subqueries, etc. stay together).
            if (
                not first
                and paren_depth == 0
                and begin_depth == 0
                and case_depth == 0
                and self._dialect == "tsql"
                and self._starts_new_dml(tok, prev_tok, lead_verb)
            ):
                break

            if tok.is_keyword("CASE"):
                case_depth += 1
            elif tok.is_keyword("BEGIN"):
                begin_depth += 1
            elif tok.is_keyword("END"):
                if case_depth > 0:
                    case_depth -= 1
                elif begin_depth > 0:
                    begin_depth -= 1
                else:
                    break

            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1

            parts.append(tok.value)
            prev_tok = tok
            self._advance()
            first = False

        sql = " ".join(parts).strip()
        return EmbeddedDML(sql=sql, dialect=self._dialect)

    # DML verbs that can start a standalone statement.
    _DML_START_KEYWORDS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"})
    # Tokens after which a DML verb is a continuation, not a new statement.
    _DML_CHAINING_KEYWORDS = frozenset(
        {
            "UNION",
            "EXCEPT",
            "INTERSECT",
            "AS",
            "OUTPUT",
            "INTO",
            "VALUES",
            "FROM",
            "RETURNING",
            "WITH",
            "ALL",
            "EXISTS",
            "IN",
        }
    )

    def _starts_new_dml(
        self, tok: Token, prev_tok: Token | None, lead_verb: str = ""
    ) -> bool:
        """Whether ``tok`` begins a new DML statement after a previous one.

        True only when ``tok`` is a DML verb on a different source line than
        the previous token, and the previous token does not syntactically
        chain into it (which would indicate INSERT ... SELECT, a UNION, a
        subquery, etc.).
        """
        if prev_tok is None:
            return False
        if tok.type != TokenType.KEYWORD or tok.upper_value not in (
            self._DML_START_KEYWORDS
        ):
            return False
        # An INSERT statement is commonly followed by its source SELECT; never
        # split an INSERT before a SELECT/VALUES.
        if lead_verb == "INSERT" and tok.upper_value == "SELECT":
            return False
        if tok.line == prev_tok.line:
            return False
        # Previous token chains into this verb → not a boundary.
        if prev_tok.type in (
            TokenType.COMMA,
            TokenType.LPAREN,
            TokenType.OPERATOR,
        ):
            return False
        # A chaining keyword (UNION, FROM, INTO, ...) means continuation.
        return not (
            prev_tok.type == TokenType.KEYWORD
            and prev_tok.upper_value in self._DML_CHAINING_KEYWORDS
        )

    # ---------------------------------------------------------------
    # Fallback
    # ---------------------------------------------------------------

    def _parse_fallback(self) -> ASTNode:
        """When we can't parse, capture everything as RawSQL."""
        parts: list[str] = []
        while not self._at_end():
            parts.append(self._current().value)
            self._advance()
        return RawSQL(
            sql=" ".join(parts).strip(),
            reason="Could not parse procedural construct",
        )
