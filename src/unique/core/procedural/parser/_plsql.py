# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Recursive descent parser for procedural SQL.

Parses stored procedures, functions, and triggers into IR AST nodes.
Delegates embedded DML/DQL statements to sqlglot for transpilation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from unique.core.ast_nodes import (
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CallStatement,
    CommentStatement,
    CursorDeclaration,
    CursorOperation,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
    ExceptionHandler,
    ExecuteStatement,
    ForLoopStatement,
    GetDiagnosticsStatement,
    IfStatement,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    PerformStatement,
    PragmaDeclaration,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    SelectIntoStatement,
    WhileStatement,
)
from unique.core.procedural.lexer import TokenType
from unique.core.procedural.parser._base import ParserBase

logger = logging.getLogger(__name__)


class PlsqlStatementsMixin(ParserBase):
    """The PL/SQL / PL-pgSQL statement family (BEGIN ... EXCEPTION blocks,
    SQL*Plus directives, CASE statements, compound triggers)."""

    _COMPOUND_COLLECT_RE = re.compile(
        r"(?is)AFTER\s+EACH\s+ROW\b.*?"
        r"(\w+)\s*\(\s*\w+\s*\)\s*:=\s*(:\s*(?:NEW|OLD)\s*\.\s*\w+)\s*;"
    )
    _COMPOUND_STMT_LOOP_RE = re.compile(
        r"(?is)AFTER\s+STATEMENT\b.*?\bBEGIN\b.*?"
        r"\bFOR\s+(\w+)\s+IN\b.*?\bLOOP\b(.*?)\bEND\s+LOOP\b"
    )

    def _compound_row_body(self, raw: str) -> tuple[ASTNode, ...]:
        """Extract a row-level equivalent of a COMPOUND TRIGGER's AFTER STATEMENT
        aggregation, or ``()`` when the body does not match the recognized idiom.

        The collection re-read (``<coll>(<loop_var>)``) is rewritten to the
        collected per-row key (``:NEW.<fk>``), so the aggregating statement is
        keyed on the current row — exactly what a plain row-level AFTER trigger
        needs on an engine (PostgreSQL) that lets a trigger re-read its table."""
        collect = self._COMPOUND_COLLECT_RE.search(raw)
        loop = self._COMPOUND_STMT_LOOP_RE.search(raw)
        if not collect or not loop:
            return ()
        coll_name, key_ref = collect.group(1), collect.group(2)
        loop_var, loop_body = loop.group(1), loop.group(2)
        # ": NEW . invoice_id" -> ":NEW.invoice_id"
        key_ref = re.sub(r"\s+", "", key_ref)
        rewritten = re.sub(
            rf"(?is)\b{re.escape(coll_name)}\s*\(\s*{re.escape(loop_var)}\s*\)",
            key_ref,
            loop_body,
        )
        stmts = [s.strip() for s in rewritten.split(";") if s.strip()]
        return tuple(EmbeddedDML(sql=s, dialect=self._dialect) for s in stmts)

    def _parse_plsql_body(self) -> list[ASTNode]:
        """Parse a PL/SQL procedure/function body (DECLARE...BEGIN...END)."""
        stmts: list[ASTNode] = []

        # A run of comments right after IS/AS (before any declaration) is the
        # routine's header comment. Oracle/PostgreSQL/MySQL keep such comments in
        # the stored module; preserve them (flagged ``header``) so the emitter can
        # place them idiomatically per target — inside the routine here, or back
        # out before the CREATE for T-SQL, which keeps them in the module text.
        for comment in self._take_comments():
            if isinstance(comment, CommentStatement):
                stmts.append(replace(comment, header=True))

        # A MySQL routine body may be a SINGLE statement with no BEGIN
        # (``CREATE PROCEDURE g(..) CASE … END CASE``); the declare loop
        # below would shred it into garbage declarations.
        if (
            self._dialect == "mysql"
            and not self._current().is_keyword("BEGIN", "DECLARE")
            and (
                self._current().is_keyword(
                    "CASE",
                    "IF",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "SELECT",
                    "SET",
                    "WHILE",
                    "CALL",
                    "RETURN",
                )
            )
        ):
            stmt = self._parse_plsql_statement()
            if stmt is not None:
                stmts.append(stmt)
            return stmts

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

        # PRAGMA <directive>[(args)]; — a compiler directive, not a variable
        # (parsing it as one shipped ``DECLARE PRAGMA AUTONOMOUS_TRANSACTION;``).
        if tok.upper_value == "PRAGMA":
            self._advance()
            parts: list[str] = []
            while not self._at_end() and self._current().type != TokenType.SEMICOLON:
                parts.append(self._flat_value(self._current()))
                self._advance()
            self._match_type(TokenType.SEMICOLON)
            return PragmaDeclaration(name=" ".join(parts))

        # Variable: name type [:= value];
        name = self._parse_identifier()

        # PG's name-first cursor: ``c1 CURSOR [(params)] FOR <select>``
        # (the keyword-first Oracle form is handled above); unparsed it
        # shredded the whole declare section.
        if self._dialect == "postgresql" and self._current().is_keyword("CURSOR"):
            self._advance()
            cparams: list[ParameterDefinition] = []
            if self._current().type == TokenType.LPAREN:
                cparams = self._parse_parameter_list()
            cquery: ASTNode | None = None
            if self._match_keyword("FOR") or self._match_keyword("IS"):
                cquery = self._parse_embedded_dml()
            self._match_type(TokenType.SEMICOLON)
            return CursorDeclaration(name=name, query=cquery, parameters=tuple(cparams))

        # Check for type_reference (%TYPE, %ROWTYPE)
        data_type = self._parse_data_type_or_reference()

        default: ASTNode | None = None
        if (
            self._match_type(TokenType.ASSIGN)
            or self._match_keyword("DEFAULT")
            or (
                self._dialect == "postgresql"
                and self._current().type == TokenType.OPERATOR
                and self._current().value == "="
                and self._advance() is not None
            )
        ):
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
        # Preserve a comment that occupies its own statement position (emit it
        # as a CommentStatement, one per call) instead of discarding it, so a
        # restorable "/* UNIQUE: … */" note survives onward transpilation — the
        # same way the T-SQL body does.
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

        if tok.upper_value == "CALL" and tok.type != TokenType.KEYWORD:
            return self._parse_call_statement()
        if tok.is_keyword("DECLARE"):
            # MySQL places variable declarations inside BEGIN ... END.
            self._advance()
            return self._parse_plsql_declaration()
        if tok.is_keyword("SET"):
            # MySQL assignment: SET var = expr;
            return self._parse_mysql_set()
        if tok.is_keyword("IF"):
            return self._parse_plsql_if()
        elif tok.is_keyword("CASE") and self._plsql_case_is_statement():
            return self._parse_plsql_case_statement()
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
        elif self._dialect == "postgresql" and tok.upper_value == "PERFORM":
            return self._parse_plsql_perform()
        elif tok.upper_value == "GET" and self._peek(1).upper_value in (
            "DIAGNOSTICS",
            "STACKED",
            "CURRENT",
        ):
            return self._parse_get_diagnostics()
        elif tok.is_keyword("EXECUTE") and self._peek(1).is_keyword("IMMEDIATE"):
            return self._parse_plsql_execute_immediate()
        elif tok.is_keyword("EXEC", "EXECUTE"):
            # SQL*Plus ``EXEC[UTE] proc[(args)]`` — shorthand for
            # ``BEGIN proc(args); END;``. Model it as a CallStatement so each
            # target emits its own call syntax; letting it fall to embedded
            # DML ships T-SQL impersonation syntax (``EXEC AS proc``) with the
            # arguments dropped (audit 2026-07-08, D1).
            return self._parse_sqlplus_exec_call()
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
        elif tok.type == TokenType.COLON and self._starts_row_ref_assignment():
            # Oracle row-level trigger assignment ``:NEW.col := expr``. The lexer
            # emits ``:`` as a bare COLON, so drop it here and parse the rest as a
            # ``NEW.col := expr`` assignment (the leading ``:`` is re-applied per
            # target). Without this the statement would fall to embedded DML and
            # the Oracle ``:=`` operator would leak to MySQL, which rejects it.
            self._advance()  # consume the ':' of :NEW./:OLD.
            return self._parse_plsql_assignment_or_call()
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

    def _plsql_case_is_statement(self) -> bool:
        """Whether a leading CASE is the PL/SQL CASE *statement* (branches
        hold statements, terminated by END CASE) rather than a CASE
        expression starting an assignment/scalar context. At statement
        position a CASE expression cannot stand alone, so a bare CASE here
        is always the statement form."""
        return True

    def _parse_plsql_case_statement(self) -> ASTNode:
        """Parse ``CASE [selector] WHEN v THEN stmts ... [ELSE stmts] END
        CASE;`` into an IF/ELSIF chain — the portable model (T-SQL has no
        CASE statement; PG/MySQL emit their native chained IF forms)."""
        self._expect_keyword("CASE")
        # Selector (empty for the searched form: CASE WHEN cond THEN ...).
        selector_parts: list[str] = []
        while not self._at_end() and not self._current().is_keyword("WHEN"):
            selector_parts.append(self._flat_value(self._advance()))
        selector = " ".join(selector_parts).strip()

        def parse_branch_body() -> tuple[ASTNode, ...]:
            stmts: list[ASTNode] = []
            guard = 0
            while not self._at_end() and not self._current().is_keyword(
                "WHEN", "ELSE", "END"
            ):
                guard += 1
                if guard > 100000:
                    break
                before = self._pos
                stmt = self._parse_plsql_statement()
                if stmt:
                    stmts.append(stmt)
                if self._pos == before:
                    self._advance()
            return tuple(stmts)

        branches: list[tuple[str, tuple[ASTNode, ...]]] = []
        else_body: tuple[ASTNode, ...] = ()
        while self._match_keyword("WHEN"):
            cond_parts: list[str] = []
            while not self._at_end() and not self._current().is_keyword("THEN"):
                cond_parts.append(self._flat_value(self._advance()))
            self._match_keyword("THEN")
            when_value = " ".join(cond_parts).strip()
            condition = f"{selector} = {when_value}" if selector else when_value
            branches.append((condition, parse_branch_body()))
        if self._match_keyword("ELSE"):
            else_body = parse_branch_body()
        self._match_keyword("END")
        self._match_keyword("CASE")
        self._match_type(TokenType.SEMICOLON)

        if not branches:
            return NullStatement()
        node: ASTNode | None = None
        for condition, body in reversed(branches):
            wrapped: tuple[ASTNode, ...] = else_body if node is None else (node,)
            node = IfStatement(
                condition=RawSQL(sql=condition, reason="CASE statement branch"),
                then_body=body or (NullStatement(),),
                else_body=wrapped,
            )
        assert node is not None
        return node

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

    #: ``[REVERSE] <start> .. <end>`` — a counting loop, not a cursor loop.
    _NUMERIC_RANGE_RE = re.compile(r"(?is)^\s*(REVERSE\s+)?(.+?)\s*\.\.\s*(.+?)\s*$")

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

        # ``FOR i IN [REVERSE] 1..13`` counts; feeding the range into the
        # cursor slot shipped ``DECLARE i_cur CURSOR FOR 1..13`` on MySQL.
        range_m = (
            self._NUMERIC_RANGE_RE.match(cursor.sql)
            if isinstance(cursor, RawSQL)
            else None
        )
        if range_m and isinstance(cursor, RawSQL) and "(" not in cursor.sql:
            return ForLoopStatement(
                variable=var_name,
                range_start=RawSQL(sql=range_m.group(2)),
                range_end=RawSQL(sql=range_m.group(3)),
                body=tuple(body),
                reverse=bool(range_m.group(1)),
            )
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
        args = ""
        if self._current().type == TokenType.LPAREN:
            args = self._capture_call_args().strip()
            if args.startswith("(") and args.endswith(")"):
                args = args[1:-1].strip()
        query: ASTNode | None = None
        if self._match_keyword("FOR"):
            query = self._parse_embedded_dml()
        else:
            self._match_type(TokenType.SEMICOLON)
        return CursorOperation(
            operation="OPEN", cursor_name=cursor_name, query=query, args=args
        )

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
        """Parse a MySQL SET assignment: SET var = expr;

        The target may be dotted — a BEFORE trigger assigns the pseudo-row
        column ``SET NEW.col = expr`` — so collect the whole ``a.b`` name
        before the ``=`` instead of stopping at the first identifier.
        """
        self._expect_keyword("SET")
        name_parts = [self._parse_identifier()]
        while self._current().type == TokenType.DOT:
            self._advance()
            name_parts.append(self._parse_identifier())
        target = ".".join(name_parts)
        self._match_type(TokenType.OPERATOR)  # =
        value = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return AssignmentStatement(target=target, value=value)

    def _parse_get_diagnostics(self) -> ASTNode:
        """GET [STACKED|CURRENT] DIAGNOSTICS v = ITEM[, …];"""
        self._advance()  # GET
        stacked = False
        if self._current().upper_value == "STACKED":
            stacked = True
            self._advance()
        elif self._current().upper_value == "CURRENT":
            self._advance()
        self._advance()  # DIAGNOSTICS
        items: list[tuple[str, str]] = []
        guard = 0
        while not self._at_end() and self._current().type != TokenType.SEMICOLON:
            guard += 1
            if guard > 50:
                break
            var = self._parse_identifier()
            if self._current().type == TokenType.OPERATOR or (
                self._current().type == TokenType.ASSIGN
            ):
                self._advance()  # = or :=
            item = self._parse_identifier()
            items.append((var, item.upper()))
            if not self._match_type(TokenType.COMMA):
                break
        self._match_type(TokenType.SEMICOLON)
        return GetDiagnosticsStatement(items=tuple(items), stacked=stacked)

    def _parse_plsql_perform(self) -> ASTNode:
        """plpgsql PERFORM: evaluate and discard (PG-only spelling)."""
        self._advance()  # PERFORM
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return PerformStatement(expression=expr)

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
            informational = level.upper_value in ("NOTICE", "INFO", "LOG", "DEBUG")
            if self._current().type == TokenType.STRING:
                formatted = self._parse_pg_raise_format()
                if formatted is not None:
                    if informational:
                        return PrintStatement(expression=formatted)
                    return RaiseErrorStatement(message=formatted)
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            if informational:
                return PrintStatement(expression=expr)
            return RaiseErrorStatement(message=expr)

        # Level-less ``RAISE 'msg' [, args] [USING …]`` defaults to
        # EXCEPTION in plpgsql — same format path as the leveled form.
        if self._dialect == "postgresql" and self._current().type == TokenType.STRING:
            formatted = self._parse_pg_raise_format()
            if formatted is not None:
                return RaiseErrorStatement(message=formatted)
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return RaiseErrorStatement(message=expr)

    def _parse_pg_raise_format(self) -> ASTNode | None:
        """Parse PG's ``'fmt %', args [USING opt = v, …]`` RAISE tail.

        Each ``%`` placeholder consumes one argument (``%%`` is a literal
        percent); the result is ONE ``||`` concatenation in the source
        spelling, which the existing operator machinery maps per target —
        the raw tuple pasted into single-argument carriers was invalid
        everywhere (``PUT_LINE('x', a)``, ``PRINT 'x', @a``). USING
        options have no separate channel off PostgreSQL and fold into the
        message text, with a warning saying exactly that. Returns None
        (position restored) when the shape doesn't match, so the caller
        keeps the raw capture — never a corrupted message.
        """
        start_pos = self._pos
        fmt = self._advance().value  # STRING token, quotes included

        args: list[str] = []
        while self._match_type(TokenType.COMMA):
            arg_parts: list[str] = []
            depth = 0
            while not self._at_end():
                tok = self._current()
                if depth == 0 and (
                    tok.type in (TokenType.COMMA, TokenType.SEMICOLON)
                    or tok.is_keyword("USING")
                ):
                    break
                if tok.type == TokenType.LPAREN:
                    depth += 1
                elif tok.type == TokenType.RPAREN:
                    if depth == 0:
                        break
                    depth -= 1
                arg_parts.append(self._flat_value(tok))
                self._advance()
            if not arg_parts:
                self._pos = start_pos
                return None
            args.append(" ".join(arg_parts))

        using_text: str | None = None
        if self._current().is_keyword("USING"):
            self._advance()
            using_parts: list[str] = []
            while not self._at_end() and self._current().type != TokenType.SEMICOLON:
                using_parts.append(self._flat_value(self._advance()))
            using_text = " ".join(using_parts)

        pieces = self._interleave_raise_format(fmt, args)
        if pieces is None:
            self._pos = start_pos
            return None
        self._match_type(TokenType.SEMICOLON)

        if using_text:
            folded = using_text.replace("'", "''")
            pieces.append(f"' [USING {folded}]'")
            self._warnings.append(
                "RAISE USING options folded into the message text "
                f"(no separate channel on the target): {using_text[:80]}"
            )
        return RawSQL(sql=" || ".join(pieces), reason="expression")

    @staticmethod
    def _interleave_raise_format(fmt: str, args: list[str]) -> list[str] | None:
        """Interleave a plpgsql format string with its arguments.

        Returns the ``||`` operand list, or None when the placeholder and
        argument counts disagree (the caller falls back to raw capture).
        """
        content = fmt[1:-1]
        pieces: list[str] = []
        lit: list[str] = []
        arg_index = 0
        i = 0
        while i < len(content):
            ch = content[i]
            if ch == "%":
                if content[i + 1 : i + 2] == "%":
                    lit.append("%")
                    i += 2
                    continue
                if arg_index >= len(args):
                    return None
                if lit:
                    pieces.append("'" + "".join(lit) + "'")
                    lit = []
                arg = args[arg_index]
                pieces.append(arg if len(arg.split()) == 1 else f"({arg})")
                arg_index += 1
                i += 1
                continue
            lit.append(ch)
            i += 1
        if lit:
            pieces.append("'" + "".join(lit) + "'")
        if arg_index != len(args):
            return None
        return pieces or ["''"]

    def _parse_sqlplus_exec_call(self) -> ASTNode:
        """Parse the SQL*Plus ``EXEC[UTE] proc[(args)]`` shorthand call."""
        self._advance()  # EXEC/EXECUTE
        name, schema = self._parse_qualified_name()
        args = ""
        if self._current().type == TokenType.LPAREN:
            args = self._capture_call_args()
        self._match_type(TokenType.SEMICOLON)
        return CallStatement(name=name, args=args, schema=schema)

    def _parse_plsql_execute_immediate(self) -> ASTNode:
        """Parse EXECUTE IMMEDIATE expr [USING bind1, bind2, ...].

        The optional USING clause supplies bind variables for the dynamic
        statement (Oracle). They are captured separately so each target can
        emit the appropriate form (PG keeps USING; T-SQL uses sp_executesql).
        """
        self._expect_keyword("EXECUTE")
        self._expect_keyword("IMMEDIATE")
        expr = self._parse_expression_until_keyword("USING", "INTO")

        into_vars: list[str] = []
        if self._match_keyword("INTO"):
            while not self._at_end():
                into_vars.append(self._parse_identifier())
                if not self._match_type(TokenType.COMMA):
                    break

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
        return ExecuteStatement(
            sql_expression=expr,
            params=tuple(params),
            immediate=True,
            into_vars=tuple(into_vars),
        )

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
        # Consume a trailing semicolon only if it is the next token; do not
        # skip comments here, which would discard a comment following the
        # block (e.g. before the enclosing END).
        if self._current().type == TokenType.SEMICOLON:
            self._advance()
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
            select_parts.append(self._flat_value(tok))
            self._advance()

        if not has_into:
            # T-SQL assignment-select: SELECT @v1 = expr1, @v2 = expr2 [FROM ...]
            # assigns expressions to variables. sqlglot would mistranslate the
            # '=' as a column alias, silently dropping the assignment, so detect
            # it here and turn it into a SELECT ... INTO so the emitter produces
            # the correct target form.
            assign = self._parse_tsql_assignment_select(select_parts)
            if assign is not None:
                into_vars_a, exprs_a = assign
                rest_parts2: list[str] = []
                paren_depth2 = 0
                while not self._at_end():
                    tok = self._current()
                    if paren_depth2 == 0 and tok.type == TokenType.SEMICOLON:
                        self._advance()
                        break
                    if paren_depth2 == 0 and tok.is_keyword("END"):
                        break
                    if tok.type == TokenType.LPAREN:
                        paren_depth2 += 1
                    elif tok.type == TokenType.RPAREN:
                        paren_depth2 -= 1
                    rest_parts2.append(self._flat_value(tok))
                    self._advance()
                rest_sql2 = " ".join(rest_parts2).strip()
                from unique.core.ast_nodes import RawSQL as _RawSQL2

                return SelectIntoStatement(
                    columns=(_RawSQL2(sql=", ".join(exprs_a), reason="select list"),),
                    into_vars=tuple(into_vars_a),
                    rest_sql=rest_sql2,
                    tsql_assignment=True,
                )
            # Not a SELECT INTO and not an assignment — reparse as embedded DML
            self._pos = start
            return self._parse_embedded_dml()

        # Consume INTO and capture target variables. A target may be a
        # trigger pseudo-row field (``:NEW.col`` — lexed as ':' 'NEW' '.'
        # 'col') or any dotted name; collect the whole reference, or the tail
        # leaks into the FROM remainder.
        self._expect_keyword("INTO")
        into_vars: list[str] = []
        while not self._at_end():
            tok = self._current()
            if tok.is_keyword("FROM") or tok.type == TokenType.SEMICOLON:
                break
            if tok.value == ":":
                self._advance()
                tok = self._current()
            if tok.type in (
                TokenType.IDENTIFIER,
                TokenType.KEYWORD,
                TokenType.VARIABLE,
            ):
                name = self._advance().value
                while self._current().type == TokenType.DOT:
                    self._advance()
                    name += "." + self._advance().value
                into_vars.append(name)
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
            rest_parts.append(self._flat_value(tok))
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

        # Assignment: name := expr; — plpgsql also accepts a bare ``=``
        # as the assignment operator (a statement cannot start with a
        # comparison, so the form is unambiguous here).
        if self._current().type == TokenType.ASSIGN or (
            self._dialect == "postgresql"
            and self._current().type == TokenType.OPERATOR
            and self._current().value == "="
        ):
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

        # A bare ``name(args);`` statement in PL/SQL is a procedure call (a
        # function call only appears inside an expression). Capture it as a
        # CallStatement so the target emits its own call syntax (PG/MySQL
        # ``CALL name(args)``), rather than letting it fall through to
        # EmbeddedDML where sqlglot mangles it into a bare ``NAME(args)``.
        if self._current().type == TokenType.LPAREN:
            args = self._capture_call_args()
            self._match_type(TokenType.SEMICOLON)
            schema = ".".join(name_parts[:-1]) or None
            return CallStatement(name=name_parts[-1], args=args, schema=schema)

        # Procedure call or other statement
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return EmbeddedDML(
            sql=f"{full_name} {expr.sql if isinstance(expr, RawSQL) else ''}"
        )
