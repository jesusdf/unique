# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Recursive descent parser for procedural SQL.

Parses stored procedures, functions, and triggers into IR AST nodes.
Delegates embedded DML/DQL statements to sqlglot for transpilation.
"""

from __future__ import annotations

import dataclasses
import logging
import re

from unique.core.ast_nodes import (
    ASTNode,
    BeginEndBlock,
    ContinueStatement,
    CursorDeclaration,
    CursorOperation,
    DeclareStatement,
    ExecuteStatement,
    ExitStatement,
    IfStatement,
    SelectIntoStatement,
    StatementList,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.procedural.lexer import TokenType
from unique.core.procedural.parser._base import ParserBase

logger = logging.getLogger(__name__)


class TsqlStatementsMixin(ParserBase):
    """The T-SQL statement family (semicolon-less bodies, BEGIN/END blocks,
    TRY/CATCH, assignment-selects)."""

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
        # Preserve a comment that occupies its own statement position: emit it
        # as a CommentStatement (one per call; the body loop calls again for
        # the next token) instead of discarding it.
        if self._current().type in (
            TokenType.LINE_COMMENT,
            TokenType.BLOCK_COMMENT,
        ):
            tok = self._current()
            self._advance()
            return self._normalize_comment(tok.value, tok.type)

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
        elif tok.is_keyword("WAITFOR"):
            return self._parse_waitfor()
        elif (
            tok.is_keyword("COMMIT", "ROLLBACK", "SAVE")
            or tok.is_keyword("BEGIN")
            and self._peek_is_transaction()
        ):
            return self._parse_transaction()
        elif tok.is_keyword("BEGIN"):
            return self._parse_tsql_begin_block()
        elif tok.is_keyword("RETURN"):
            return self._parse_return()
        elif tok.is_keyword("EXEC", "EXECUTE"):
            return self._parse_tsql_exec()
        elif tok.is_keyword("PRINT"):
            return self._parse_print()
        elif tok.is_keyword("BREAK"):
            # Loop exit: Oracle/PG EXIT, MySQL LEAVE, T-SQL BREAK.
            self._advance()
            self._match_type(TokenType.SEMICOLON)
            return ExitStatement()
        elif tok.is_keyword("CONTINUE"):
            # Loop skip: Oracle/PG CONTINUE, MySQL ITERATE, T-SQL CONTINUE.
            self._advance()
            self._match_type(TokenType.SEMICOLON)
            return ContinueStatement()
        elif tok.is_keyword("RAISERROR", "THROW"):
            return self._parse_raiserror()
        elif tok.is_keyword("TRY"):
            return self._parse_tsql_try_catch()
        elif tok.is_keyword("OPEN") and self._peek(1).type in (
            TokenType.IDENTIFIER,
            TokenType.VARIABLE,
        ):
            # Cursor OPEN. Exclude OPEN SYMMETRIC/MASTER KEY (falls through to
            # embedded DML like any other opaque statement).
            if self._peek(1).upper_value not in ("SYMMETRIC", "MASTER"):
                return self._parse_plsql_open()
            return self._parse_embedded_dml()
        elif tok.is_keyword("FETCH"):
            return self._parse_tsql_fetch()
        elif tok.is_keyword("CLOSE") and self._peek(1).type in (
            TokenType.IDENTIFIER,
            TokenType.VARIABLE,
        ):
            return self._parse_plsql_close()
        elif tok.is_keyword("DEALLOCATE"):
            return self._parse_tsql_deallocate()
        elif tok.is_keyword("SELECT"):
            # A T-SQL assignment-select (SELECT @v = expr) must become a
            # SELECT ... INTO, not embedded DML (where sqlglot would turn the
            # '=' into a column alias and drop the assignment).
            assign_stmt = self._try_parse_tsql_assignment_select()
            if assign_stmt is not None:
                return assign_stmt
            return self._parse_embedded_dml()
        elif tok.is_keyword("WITH"):
            # A CTE feeding an assignment-select (WITH x AS (...) SELECT
            # @v = ...) must become SELECT ... INTO like the plain form —
            # sqlglot would turn the '=' into an alias and drop the
            # assignment.
            cte_stmt = self._try_parse_tsql_cte_assignment_select()
            if cte_stmt is not None:
                return cte_stmt
            return self._parse_embedded_dml()
        elif tok.is_keyword("INSERT", "UPDATE", "DELETE", "MERGE"):
            return self._parse_embedded_dml()
        elif tok.type == TokenType.SEMICOLON:
            self._advance()
            return None
        else:
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
                # T-SQL cursor options (LOCAL FAST_FORWARD ...) sit between
                # CURSOR and FOR; they are scope/perf hints with no portable
                # meaning — consume them so the FOR query is still captured.
                while (
                    self._current().type in (TokenType.IDENTIFIER, TokenType.KEYWORD)
                    and self._current().upper_value in self._TSQL_CURSOR_OPTIONS
                ):
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
            # Statement verbs that can never continue a boolean expression:
            # ``IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION`` used to swallow the
            # ROLLBACK (and everything after) into the condition.
            "COMMIT",
            "ROLLBACK",
            "SAVE",
            "DECLARE",
            "WAITFOR",
            "BREAK",
            "CONTINUE",
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
        # Do not skip comments when probing for ELSE: a standalone comment
        # after the THEN block (before END) must be preserved by the body loop,
        # not silently consumed while looking for an optional ELSE.
        if self._current().is_keyword("ELSE"):
            self._advance()
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
        """Parse T-SQL WHILE ... BEGIN...END (or a single-statement body).

        The condition stops at any statement-starting keyword, like IF's:
        an unbracketed body without ';' (``WHILE cond\\n  SET @i += 1``)
        otherwise swallows the following statements into the condition.
        """
        self._expect_keyword("WHILE")
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
            # Statement verbs that can never continue a boolean expression:
            # ``IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION`` used to swallow the
            # ROLLBACK (and everything after) into the condition.
            "COMMIT",
            "ROLLBACK",
            "SAVE",
            "DECLARE",
            "WAITFOR",
            "BREAK",
            "CONTINUE",
        )

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
        # Consume a trailing semicolon only if it is the next token; do not
        # skip comments here, which would discard a comment following the
        # block (e.g. before the enclosing END).
        if self._current().type == TokenType.SEMICOLON:
            self._advance()
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

    def _parse_tsql_fetch(self) -> ASTNode:
        """Parse T-SQL ``FETCH [NEXT|PRIOR|FIRST|LAST] FROM c [INTO @v, ...]``.

        The direction keyword is dropped (NEXT is both the T-SQL default and
        the only portable behaviour); ABSOLUTE/RELATIVE fetches have no
        counterpart in the targets and fall through as embedded DML.
        """
        if self._peek(1).upper_value in ("ABSOLUTE", "RELATIVE"):
            return self._parse_embedded_dml()
        self._expect_keyword("FETCH")
        self._match_keyword("NEXT", "PRIOR", "FIRST", "LAST")
        self._match_keyword("FROM")
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

    def _parse_tsql_deallocate(self) -> ASTNode:
        """Parse T-SQL ``DEALLOCATE [GLOBAL] c``."""
        self._expect_keyword("DEALLOCATE")
        self._match_keyword("GLOBAL")
        cursor_name = self._parse_identifier()
        self._match_type(TokenType.SEMICOLON)
        return CursorOperation(operation="DEALLOCATE", cursor_name=cursor_name)

    def _try_parse_tsql_cte_assignment_select(self) -> ASTNode | None:
        """Capture ``WITH <ctes> SELECT @v = ...`` as a SelectIntoStatement
        carrying the CTE prefix; None (position restored) when the main
        statement is not an assignment-select."""
        start = self._pos
        self._expect_keyword("WITH")
        parts: list[str] = ["WITH"]
        depth = 0
        while not self._at_end():
            tok = self._current()
            if depth == 0 and (
                tok.is_keyword("SELECT") or tok.type == TokenType.SEMICOLON
            ):
                break
            if tok.type == TokenType.LPAREN:
                depth += 1
            elif tok.type == TokenType.RPAREN:
                depth -= 1
            parts.append(self._flat_value(tok))
            self._advance()
        if self._at_end() or not self._current().is_keyword("SELECT"):
            self._pos = start
            return None
        assign = self._try_parse_tsql_assignment_select()
        if not isinstance(assign, SelectIntoStatement):
            self._pos = start
            return None
        return dataclasses.replace(assign, with_sql=" ".join(parts))

    def _try_parse_tsql_assignment_select(self) -> ASTNode | None:
        """If the upcoming SELECT is ``SELECT @v = expr [, ...] [FROM ...]``,
        parse it into a SelectIntoStatement and return it; otherwise restore the
        position and return None so the caller parses it as embedded DML."""
        start = self._pos
        self._expect_keyword("SELECT")
        select_parts: list[str] = []
        paren_depth = 0
        case_depth = 0
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and (
                tok.is_keyword("FROM") or tok.type == TokenType.SEMICOLON
            ):
                break
            if tok.is_keyword("CASE"):
                case_depth += 1
            if paren_depth == 0 and tok.is_keyword("END"):
                if case_depth == 0:
                    break
                case_depth -= 1
            # ELSE outside a CASE belongs to the enclosing IF, never to the
            # select list (semicolon-less T-SQL: IF ... SELECT @v=... ELSE).
            if paren_depth == 0 and case_depth == 0 and tok.is_keyword("ELSE"):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            select_parts.append(self._flat_value(tok))
            self._advance()

        assign = self._parse_tsql_assignment_select(select_parts)
        if assign is None:
            self._pos = start
            return None

        into_vars, exprs = assign
        # Capture the remainder (FROM onward) up to the statement end. Stop at a
        # statement boundary so the following statements (SET/INSERT/IF/...) and
        # any own-line comment are not absorbed into this one. T-SQL omits the
        # ';' terminator, so we rely on the same boundary detection used for
        # embedded DML.
        rest_parts: list[str] = []
        paren_depth = 0
        case_depth = 0
        prev_line: int | None = None
        first_rest = True
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
                self._advance()
                break
            if tok.is_keyword("CASE"):
                case_depth += 1
            if paren_depth == 0 and tok.is_keyword("END"):
                if case_depth == 0:
                    break
                case_depth -= 1
            if paren_depth == 0 and case_depth == 0 and tok.is_keyword("ELSE"):
                break
            # An own-line comment ends this statement (it belongs between
            # statements, like in the body loop).
            if (
                paren_depth == 0
                and not first_rest
                and tok.type in (TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT)
                and prev_line is not None
                and tok.line is not None
                and tok.line != prev_line
            ):
                break
            # A new statement keyword on a new line ends this one.
            if (
                paren_depth == 0
                and not first_rest
                and tok.type == TokenType.KEYWORD
                and tok.upper_value
                in (
                    "SET",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "MERGE",
                    "SELECT",
                    "IF",
                    "WHILE",
                    "RETURN",
                    "EXEC",
                    "EXECUTE",
                    "DECLARE",
                    "BEGIN",
                    "PRINT",
                    "RAISERROR",
                    "THROW",
                    "FETCH",
                    "OPEN",
                    "CLOSE",
                )
                and prev_line is not None
                and tok.line is not None
                and tok.line != prev_line
            ):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            rest_parts.append(self._flat_value(tok))
            prev_line = tok.line
            first_rest = False
            self._advance()

        from unique.core.ast_nodes import RawSQL as _RawSQL

        return SelectIntoStatement(
            columns=(_RawSQL(sql=", ".join(exprs), reason="select list"),),
            into_vars=tuple(into_vars),
            rest_sql=" ".join(rest_parts).strip(),
            tsql_assignment=True,
        )

    def _parse_tsql_assignment_select(
        self, select_parts: list[str]
    ) -> tuple[list[str], list[str]] | None:
        """Detect a T-SQL assignment-select list (``@v = expr, ...``).

        Returns ``(into_vars, exprs)`` when every comma-separated item has the
        shape ``@var = expression``; otherwise ``None`` (it's an ordinary
        select list). Splits on top-level commas so expressions containing
        commas (function calls) are handled.
        """
        text = " ".join(select_parts).strip()
        if "=" not in text or "@" not in text:
            return None
        # Split on top-level commas.
        items: list[str] = []
        depth = 0
        buf: list[str] = []
        for ch in text:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            if ch == "," and depth == 0:
                items.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        if buf:
            items.append("".join(buf))

        into_vars: list[str] = []
        exprs: list[str] = []
        for item in items:
            # Each item must be "@var = expr" with a single '=' assignment, not
            # a comparison (>=, <=, <>) or equality test.
            m = re.match(r"^\s*(@\w+)\s*=\s*(.+)$", item, re.DOTALL)
            if not m:
                return None
            expr = m.group(2).strip()
            if not expr or expr[0] in "=<>!":
                return None
            into_vars.append(m.group(1))
            exprs.append(expr)
        if not into_vars:
            return None
        return into_vars, exprs

    _TSQL_CURSOR_OPTIONS = frozenset(
        {
            "LOCAL",
            "GLOBAL",
            "FORWARD_ONLY",
            "SCROLL",
            "STATIC",
            "KEYSET",
            "DYNAMIC",
            "FAST_FORWARD",
            "READ_ONLY",
            "SCROLL_LOCKS",
            "OPTIMISTIC",
            "TYPE_WARNING",
        }
    )
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
            "WAITFOR",
            "COMMIT",
            "ROLLBACK",
            "SAVE",
        }
    )

    def _at_tsql_stmt_boundary(self) -> bool:
        """Whether the current token begins a new T-SQL statement.

        Used to delimit statements that omit the trailing semicolon. Only
        active for the T-SQL dialect; Oracle/PG/MySQL rely on semicolons.
        """
        if not self._is_tsql_source():
            return False
        tok = self._current()
        if tok.type != TokenType.KEYWORD:
            return False
        upper = tok.upper_value
        if upper in self._TSQL_STMT_BOUNDARY_KEYWORDS:
            return True
        # ``BEGIN TRY`` / ``BEGIN TRAN[SACTION]`` unambiguously start a new
        # statement: a semicolon-less ``SET @v = NULL`` used to absorb the
        # following TRY block into the value. (A bare ``BEGIN`` is left
        # alone — treating every BEGIN as a boundary broke DML conservation
        # in block bodies.)
        if upper == "BEGIN" and self._peek(1).is_keyword("TRY", "TRAN", "TRANSACTION"):
            return True
        # Cursor operations start statements (semicolon-less bodies used to
        # absorb ``OPEN c`` / ``FETCH NEXT FROM c`` into the previous DML or
        # EXEC argument list). OPEN/CLOSE SYMMETRIC|MASTER KEY are not cursor
        # ops, and FETCH is only a boundary in its cursor form — never the
        # ``OFFSET … FETCH NEXT n ROWS`` clause of a SELECT.
        if (
            upper in ("OPEN", "CLOSE")
            and self._peek(1).type in (TokenType.IDENTIFIER, TokenType.VARIABLE)
            and self._peek(1).upper_value not in ("SYMMETRIC", "MASTER")
        ):
            return True
        if upper == "DEALLOCATE":
            return True
        if upper == "FETCH" and (
            self._peek(1).is_keyword("FROM")
            or (
                self._peek(1).is_keyword("NEXT", "PRIOR", "FIRST", "LAST")
                and self._peek(2).is_keyword("FROM")
            )
        ):
            return True
        # A standalone SET statement — ``SET @var = …`` or a session option
        # (``SET NOEXEC ON``) — begins a statement; the SET clause of an
        # UPDATE/MERGE (target is a column identifier) does not.
        return upper == "SET" and self._set_starts_statement(self._peek(1))
