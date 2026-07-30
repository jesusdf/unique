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
from dataclasses import replace

from unique.core.ast_nodes import (
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CallStatement,
    CommentStatement,
    ContinueStatement,
    CursorDeclaration,
    CursorOperation,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
    ExceptionHandler,
    ExecuteStatement,
    ExitStatement,
    ForeachStatement,
    ForLoopStatement,
    GetDiagnosticsStatement,
    HandlerDeclaration,
    IfStatement,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    PerformStatement,
    PragmaDeclaration,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SelectIntoStatement,
    StatementList,
    WhileStatement,
)
from unique.core.procedural.lexer import Token, TokenType
from unique.core.procedural.parser._base import ParserBase

logger = logging.getLogger(__name__)


class PlsqlStatementsMixin(ParserBase):
    """The PL/SQL / PL-pgSQL statement family (BEGIN ... EXCEPTION blocks,
    SQL*Plus directives, CASE statements, compound triggers)."""

    #: Label on the routine body's own block (``foo: begin … end foo``);
    #: LEAVE of this label is RETURN, not BREAK.
    _plsql_body_label: str | None = None

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
                # REPEAT/LOOP/CALL lex as identifiers; a ``label:``
                # prefix hides the loop keyword two tokens further on.
                or self._current().upper_value in ("REPEAT", "LOOP", "CALL")
                or (
                    self._current().type == TokenType.IDENTIFIER
                    and self._peek(1).type == TokenType.COLON
                    and self._peek(2).upper_value
                    in ("LOOP", "WHILE", "REPEAT", "BEGIN")
                )
            )
        ):
            # A label on the body's own block: LEAVE <label> is RETURN.
            if self._peek(1).type == TokenType.COLON:
                self._plsql_body_label = self._current().value
            try:
                stmt = self._parse_plsql_statement()
            finally:
                self._plsql_body_label = None
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
            # PG 14's SQL-standard function body (``BEGIN ATOMIC …``):
            # unconsumed, ATOMIC shredded the first statement into an
            # ``atomic;`` leftover and DROPPED it (wave 215).
            if (
                self._dialect == "postgresql"
                and self._current().upper_value == "ATOMIC"
            ):
                self._advance()
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

        # Variable: name [CONSTANT] type [:= value];
        name = self._parse_identifier()

        # MySQL declares several variables with ONE type (``DECLARE
        # z1, z2 int;``) — the unconsumed comma shredded the section
        # into ``DECLARE @z1 ,;`` garbage (wave 159).
        extra_names: list[str] = []
        if self._dialect == "mysql":
            while self._current().type == TokenType.COMMA:
                self._advance()
                extra_names.append(self._parse_identifier())

        # ``name ALIAS FOR <ident>;`` — plpgsql's parameter alias (wave
        # 117). Renaming the alias to its target in the remaining tokens
        # is the token-level equivalent (same mechanism as $n positional
        # aliasing), valid on every target; no declaration is emitted.
        if (
            self._dialect == "postgresql"
            and self._current().upper_value == "ALIAS"
            and self._peek(1).upper_value == "FOR"
        ):
            self._advance()
            self._advance()
            alias_target = self._parse_identifier()
            self._match_type(TokenType.SEMICOLON)
            low = name.lower()
            self._tokens[self._pos :] = [
                (
                    Token(
                        type=t.type,
                        value=alias_target,
                        line=t.line,
                        column=t.column,
                    )
                    if t.type == TokenType.IDENTIFIER and t.value.lower() == low
                    else t
                )
                for t in self._tokens[self._pos :]
            ]
            return None

        # CONSTANT modifier (Oracle PL/SQL and plpgsql). Unconsumed it
        # split the declaration in two (``rc constant;`` + ``refcursor ;;``).
        constant = False
        if self._current().upper_value == "CONSTANT":
            self._advance()
            constant = True

        # PG cursor scrollability: ``c [NO] SCROLL CURSOR … FOR <select>``.
        scroll: str | None = None
        if self._dialect == "postgresql":
            if self._current().upper_value == "SCROLL" and self._peek(1).is_keyword(
                "CURSOR"
            ):
                self._advance()
                scroll = "SCROLL"
            elif (
                self._current().upper_value == "NO"
                and self._peek(1).upper_value == "SCROLL"
                and self._peek(2).is_keyword("CURSOR")
            ):
                self._advance()
                self._advance()
                scroll = "NO SCROLL"

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
            return CursorDeclaration(
                name=name, query=cquery, parameters=tuple(cparams), scroll=scroll
            )

        # Check for type_reference (%TYPE, %ROWTYPE); the PG variant also
        # consumes DOUBLE PRECISION / TIME ZONE spellings and ``[]``
        # array suffixes (unconsumed, ``a integer[] = …`` shredded into
        # ``a integer;`` + ``[] =;``).
        data_type = (
            self._parse_pg_data_type()
            if self._dialect == "postgresql"
            else self._parse_data_type_or_reference()
        )

        # A type that is not identifier-shaped means the LEXER split a
        # non-representable identifier (mojibake latin1 bytes: ``lÃ¤`` split
        # into ``lÃ`` + ``¤``) and this "declaration" is shredded garbage —
        # fail the WHOLE unit into the parse carrier (guardrail 4), never
        # fragments.
        if data_type is not None and not re.match(
            r"[A-Za-z_\"`\[]", getattr(data_type, "name", "") or ""
        ):
            raise ValueError(
                f"declaration type {getattr(data_type, 'name', '')!r} is not "
                "an identifier (unrepresentable identifier bytes?)"
            )

        # NOT NULL modifier (PG/Oracle). Unconsumed it split the
        # declaration (``i integer;`` + ``NOT NULL := 0;`` — wave 131).
        not_null = False
        if self._current().is_keyword("NOT") and self._peek(1).upper_value == "NULL":
            self._advance()
            self._advance()
            not_null = True

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
        first = DeclareStatement(
            name=name,
            data_type=data_type,
            default=default,
            constant=constant,
            not_null=not_null,
        )
        if not extra_names:
            return first
        return StatementList(
            statements=(first,)
            + tuple(dataclasses.replace(first, name=n) for n in extra_names)
        )

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
            cur = self._current()
            if (
                self._dialect == "mysql"
                and cur.upper_value in ("EXIT", "CONTINUE", "UNDO")
                and self._peek(1).upper_value == "HANDLER"
            ):
                return self._parse_mysql_handler()
            return self._parse_plsql_declaration()
        if tok.is_keyword("SET"):
            # MySQL assignment: SET var = expr;
            return self._parse_mysql_set()
        if tok.upper_value == "COMMENT" and self._peek(1).upper_value == "ON":
            # ``COMMENT ON <obj> IS '…'`` inside a body: PG/Oracle SQL,
            # nothing on MySQL/T-SQL (wave 225). Capture whole.
            parts_c: list[str] = []
            while not self._at_end() and self._current().type != TokenType.SEMICOLON:
                parts_c.append(self._advance().value)
            self._match_type(TokenType.SEMICOLON)
            return RawSQL(
                sql=" ".join(parts_c) + ";",
                reason="COMMENT ON statement",
            )
        if self._dialect == "mysql" and (
            tok.upper_value
            in (
                "FLUSH",
                "RESET",
                "PURGE",
                "KILL",
                "SHOW",
                "REPAIR",
                "OPTIMIZE",
                "ANALYZE",
                "CHECKSUM",
                "LOCK",
                "UNLOCK",
            )
            # ALTER DATABASE/SERVER/INSTANCE in a routine body is server
            # administration (zero push) — a body ALTER TABLE stays DML.
            or (
                tok.upper_value == "ALTER"
                and self._peek(1).upper_value
                in ("DATABASE", "SCHEMA", "SERVER", "INSTANCE")
            )
            # MySQL server-side prepared statements (PREPARE name FROM …,
            # EXECUTE name [USING …], DEALLOCATE PREPARE name) have no
            # cross-engine session mechanism — the raw PREPARE shipped.
            or tok.upper_value in ("PREPARE", "DEALLOCATE")
            or (
                tok.upper_value == "EXECUTE"
                and self._peek(1).type == TokenType.IDENTIFIER
            )
        ):
            # MySQL admin statements — the embedded-DML fallback
            # shredded ``FLUSH QUERY CACHE`` into ``flush AS query``
            # (wave 166) and ``KILL QUERY id`` DROPPED its id (wave
            # 171). Capture whole; the transformer carriers them
            # cross-dialect, MySQL keeps them verbatim.
            kw = tok.upper_value
            parts: list[str] = []
            while not self._at_end() and self._current().type != TokenType.SEMICOLON:
                parts.append(self._advance().value)
            self._match_type(TokenType.SEMICOLON)
            return RawSQL(
                sql=" ".join(parts),
                reason=f"MySQL admin statement ({kw})",
            )
        if (
            self._dialect == "mysql"
            and tok.type == TokenType.IDENTIFIER
            and tok.upper_value == "REPEAT"
        ):
            return self._parse_mysql_repeat()
        if (
            self._dialect == "mysql"
            and tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD)
            and tok.upper_value in ("LEAVE", "ITERATE")
            and self._peek(1).type == TokenType.IDENTIFIER
        ):
            kw = self._advance().upper_value
            label = self._advance().value
            self._match_type(TokenType.SEMICOLON)
            if kw == "LEAVE":
                # LEAVE of the routine body's own block label exits the
                # routine — RETURN everywhere; ExitStatement emitted a
                # bare BREAK, invalid outside a loop on T-SQL.
                if label.upper() == (self._plsql_body_label or "").upper():
                    return ReturnStatement()
                return ExitStatement(label=label)
            # ITERATE label — modeled, or T-SQL shipped a literal
            # ``CONTINUE hmm`` (labels don't exist there).
            return ContinueStatement(label=label)
        if (
            self._dialect == "mysql"
            and tok.type == TokenType.IDENTIFIER
            and self._peek(1).type == TokenType.COLON
            and self._peek(2).upper_value in ("LOOP", "WHILE", "REPEAT", "BEGIN")
        ):
            label = self._advance().value
            self._advance()  # ':'
            inner = self._parse_plsql_statement()
            if isinstance(inner, (LoopStatement, WhileStatement, BeginEndBlock)):
                inner = dataclasses.replace(inner, label=label)
            # MySQL closes a labeled block/loop with ``END … label``.
            if self._current().value.upper() == label.upper():
                self._advance()
                self._match_type(TokenType.SEMICOLON)
            return inner
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
        elif tok.upper_value == "FOREACH" and self._dialect == "postgresql":
            return self._parse_plsql_foreach()
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
        elif tok.is_keyword("EXECUTE") and self._dialect == "postgresql":
            # plpgsql's EXECUTE is ALWAYS dynamic SQL (procedure calls are
            # spelled CALL there); the SQL*Plus exec-call fallthrough
            # mangled ``EXECUTE 'select …' INTO STRICT x`` into
            # ``CALL 'select …'();`` (wave 121).
            return self._parse_pg_dynamic_execute()
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
        elif tok.is_keyword("SAVEPOINT", "COMMIT") or (
            tok.is_keyword("ROLLBACK")
            # A bare ROLLBACK / ROLLBACK TO savepoint is transaction control;
            # ``ROLLBACK`` is never a PL/SQL assignment target. Routed to the
            # transaction parser so ``SAVEPOINT sp1`` / ``ROLLBACK TO sp1`` model
            # as TransactionStatements instead of falling to embedded DML, where
            # raw sqlglot mis-rendered ``SAVEPOINT sp1`` as ``SAVEPOINT AS sp1``.
            and self._peek(1).type != TokenType.LPAREN
        ):
            return self._parse_transaction()
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

    def _parse_mysql_handler(self) -> ASTNode:
        """MySQL ``DECLARE {EXIT|CONTINUE|UNDO} HANDLER FOR cond[, …]
        stmt`` (DECLARE already consumed)."""
        kind = self._advance().upper_value  # EXIT/CONTINUE/UNDO
        self._advance()  # HANDLER
        self._expect_keyword("FOR")

        conditions: list[str] = []
        current: list[str] = []
        while not self._at_end():
            tok = self._current()
            if tok.type == TokenType.COMMA:
                conditions.append(" ".join(current).upper())
                current = []
                self._advance()
                continue
            up = tok.upper_value
            if up in ("SQLEXCEPTION", "SQLWARNING"):
                current.append(up)
                self._advance()
            elif up == "NOT" and self._peek(1).upper_value == "FOUND":
                current.append("NOT FOUND")
                self._advance()
                self._advance()
            elif up == "SQLSTATE":
                self._advance()
                if self._current().upper_value == "VALUE":
                    self._advance()
                current.append(f"SQLSTATE {self._advance().value}")
            elif tok.type == TokenType.NUMBER or (
                tok.type == TokenType.IDENTIFIER
                and self._peek(1).type == TokenType.COMMA
            ):
                current.append(str(self._advance().value))
            else:
                break
        if current:
            conditions.append(" ".join(current).upper())

        action = self._parse_plsql_statement()
        return HandlerDeclaration(
            kind=kind,
            conditions=tuple(conditions),
            body=(action,) if action else (),
        )

    def _parse_mysql_repeat(self) -> ASTNode:
        """MySQL ``REPEAT … UNTIL cond END REPEAT`` — a post-test loop:
        LoopStatement with a trailing conditional EXIT."""
        self._advance()  # REPEAT (tokenizes as an identifier)

        body: list[ASTNode] = []
        while not self._at_end() and not (
            self._current().type in (TokenType.KEYWORD, TokenType.IDENTIFIER)
            and self._current().upper_value == "UNTIL"
        ):
            stmt = self._parse_plsql_statement()
            if stmt:
                body.append(stmt)
        self._advance()  # UNTIL
        condition = self._parse_expression_until_keyword("END")
        self._match_keyword("END")
        if self._current().upper_value == "REPEAT":
            self._advance()
        self._match_type(TokenType.SEMICOLON)

        return LoopStatement(body=tuple(body) + (ExitStatement(condition=condition),))

    def _parse_plsql_while(self) -> ASTNode:
        """Parse PL/SQL WHILE … LOOP … END LOOP (MySQL spells it
        WHILE … DO … END WHILE)."""
        self._expect_keyword("WHILE")
        condition = self._parse_expression_until_keyword("LOOP", "DO")
        if not self._match_keyword("LOOP"):
            if self._current().type == TokenType.IDENTIFIER and (
                self._current().upper_value == "DO"
            ):
                self._advance()
            else:
                self._expect_keyword("DO")

        body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            stmt = self._parse_plsql_statement()
            if stmt:
                body.append(stmt)

        self._match_keyword("END")
        if not self._match_keyword("LOOP"):
            self._match_keyword("WHILE")
        if self._current().type == TokenType.IDENTIFIER:
            self._advance()  # MySQL trailing label
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
        # MySQL closes a labeled loop as ``END LOOP label``.
        if self._current().type == TokenType.IDENTIFIER:
            self._advance()
        self._match_type(TokenType.SEMICOLON)
        return LoopStatement(body=tuple(body))

    def _parse_plsql_foreach(self) -> ASTNode:
        """Parse plpgsql FOREACH var [SLICE n] IN ARRAY expr LOOP … END LOOP.

        Unmodeled, the loop structure shredded (header flattened, END
        LOOP lost — wave 120)."""
        self._advance()  # FOREACH
        variable = self._parse_identifier()
        # Comma-separated target list (faithful pass-through; PG itself
        # validates the row-ness of multi-targets — wave 133).
        while self._current().type == TokenType.COMMA:
            self._advance()
            variable += f", {self._parse_identifier()}"
        slice_depth: int | None = None
        if self._current().upper_value == "SLICE":
            self._advance()
            if self._current().type == TokenType.NUMBER:
                slice_depth = int(self._advance().value)
        self._match_keyword("IN")
        # ARRAY keyword, then the array expression up to LOOP.
        if self._current().upper_value == "ARRAY":
            self._advance()
        expr_parts: list[str] = []
        while not self._at_end() and not self._current().is_keyword("LOOP"):
            expr_parts.append(self._flat_value(self._current()))
            self._advance()
        self._expect_keyword("LOOP")
        body: list[ASTNode] = []
        while not self._at_end() and not self._current().is_keyword("END"):
            stmt = self._parse_plsql_statement()
            if stmt:
                body.append(stmt)
        self._match_keyword("END")
        self._match_keyword("LOOP")
        self._match_type(TokenType.SEMICOLON)
        return ForeachStatement(
            variable=variable,
            array_expr=" ".join(expr_parts).strip(),
            body=tuple(body),
            slice_depth=slice_depth,
        )

    def _parse_plsql_open(self) -> ASTNode:
        """Parse OPEN cursor [FOR select]."""
        self._expect_keyword("OPEN")
        cursor_name = self._parse_identifier()
        args = ""
        if self._current().type == TokenType.LPAREN:
            args = self._capture_call_args().strip()
            if args.startswith("(") and args.endswith(")"):
                args = args[1:-1].strip()
        # PG scrollability on the OPEN itself: ``OPEN c [NO] SCROLL FOR …``
        # (unconsumed, ``scroll for execute '…';`` shipped as an orphan
        # statement — wave 116).
        scroll: str | None = None
        if self._dialect == "postgresql":
            if self._current().upper_value == "SCROLL":
                self._advance()
                scroll = "SCROLL"
            elif (
                self._current().upper_value == "NO"
                and self._peek(1).upper_value == "SCROLL"
            ):
                self._advance()
                self._advance()
                scroll = "NO SCROLL"
        query: ASTNode | None = None
        if self._match_keyword("FOR"):
            if self._current().is_keyword("EXECUTE"):
                # Dynamic open: FOR EXECUTE <string expr> [USING …] — not a
                # parseable DML; preserve the dynamic form verbatim.
                parts: list[str] = []
                while (
                    not self._at_end() and self._current().type != TokenType.SEMICOLON
                ):
                    parts.append(self._flat_value(self._current()))
                    self._advance()
                self._match_type(TokenType.SEMICOLON)
                query = RawSQL(sql=" ".join(parts), reason="dynamic OPEN FOR EXECUTE")
            else:
                query = self._parse_embedded_dml()
        else:
            self._match_type(TokenType.SEMICOLON)
        return CursorOperation(
            operation="OPEN",
            cursor_name=cursor_name,
            query=query,
            args=args,
            scroll=scroll,
        )

    _FETCH_DIRECTIONS = frozenset(
        {"NEXT", "PRIOR", "FIRST", "LAST", "FORWARD", "BACKWARD"}
    )

    def _parse_plsql_fetch(self) -> ASTNode:
        """Parse FETCH [direction FROM|IN] cursor INTO vars.

        The direction word used to be taken as the CURSOR NAME, emitting
        ``FETCH next INTO ;`` plus an orphan ``from c into x;`` (wave 118).
        A word only counts as a direction when FROM/IN follows (PG requires
        it then), so a cursor actually named ``last`` keeps working."""
        self._expect_keyword("FETCH")
        direction: str | None = None
        cur = self._current().upper_value
        if cur in self._FETCH_DIRECTIONS and self._peek(1).is_keyword("FROM", "IN"):
            direction = cur
            self._advance()
        elif (
            cur in ("ABSOLUTE", "RELATIVE", "FORWARD", "BACKWARD")
            and self._peek(1).type == TokenType.NUMBER
            and self._peek(2).is_keyword("FROM", "IN")
        ):
            self._advance()
            count = self._advance().value
            direction = f"{cur} {count}"
        elif (
            cur in ("ABSOLUTE", "RELATIVE", "FORWARD", "BACKWARD")
            and self._peek(1).value == "-"
            and self._peek(2).type == TokenType.NUMBER
            and self._peek(3).is_keyword("FROM", "IN")
        ):
            # Negative counts: FETCH RELATIVE -2 FROM c (wave 133).
            self._advance()
            self._advance()
            count = self._advance().value
            direction = f"{cur} -{count}"
        if self._current().is_keyword("FROM", "IN"):
            self._advance()
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
            direction=direction,
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
        assignments: list[ASTNode] = []
        while True:
            name_parts = [self._parse_identifier()]
            while self._current().type == TokenType.DOT:
                self._advance()
                name_parts.append(self._parse_identifier())
            target = ".".join(name_parts)
            # ``SET x = 1`` or the walrus ``SET x := 1`` — unmatched,
            # the := leaked into the value (``SET @x = := 1``).
            if not self._match_type(TokenType.OPERATOR):
                self._match_type(TokenType.ASSIGN)
            # MySQL assigns several variables in ONE SET (``SET a = 1,
            # b = 2;``) — split; the comma form is invalid T-SQL and
            # the second target shipped without its @ sigil (wave 159).
            value = (
                self._parse_expression_until_comma_or_semicolon()
                if self._peek_multi_assign_ahead()
                else self._parse_expression_until_semicolon()
            )
            assignments.append(AssignmentStatement(target=target, value=value))
            if self._current().type == TokenType.COMMA:
                self._advance()
                continue
            break
        self._match_type(TokenType.SEMICOLON)
        if len(assignments) == 1:
            return assignments[0]
        return StatementList(statements=tuple(assignments))

    def _peek_multi_assign_ahead(self) -> bool:
        """Whether a depth-0 ``, ident =`` follows before the statement
        ends — the multi-assignment SET form. The single-assignment
        capture must stay comma-transparent (``SET a = GREATEST(b,
        c)`` at depth 0 has no comma, but ``SET s = 'x,y'`` strings and
        row constructors do appear as values)."""
        depth = 0
        i = 0
        while True:
            tok = self._peek(i)
            if tok.type == TokenType.EOF or tok.type == TokenType.SEMICOLON:
                return False
            if tok.type == TokenType.LPAREN:
                depth += 1
            elif tok.type == TokenType.RPAREN:
                depth -= 1
            elif depth == 0 and tok.is_keyword("END"):
                return False
            elif (
                depth == 0
                and tok.type == TokenType.COMMA
                and self._peek(i + 1).type == TokenType.IDENTIFIER
                and self._peek(i + 2).type == TokenType.OPERATOR
                and self._peek(i + 2).value == "="
            ):
                return True
            i += 1
            if i > 4000:
                return False

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

        # Bare re-``RAISE;`` (re-throw the active exception): the generic
        # expression fallback emitted the invalid ``RAISE EXCEPTION '%', ;``
        # (wave 119). Every target has a native re-raise.
        if self._current().type == TokenType.SEMICOLON:
            self._advance()
            return RaiseErrorStatement(reraise=True)

        # ``RAISE USING key = expr, …`` — the ``message`` option IS the
        # message; other options fold into the text (no separate channel
        # off PostgreSQL).
        if self._dialect == "postgresql" and self._current().is_keyword("USING"):
            return self._parse_pg_raise_using(informational=False)

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
            if self._dialect == "postgresql" and self._current().is_keyword("USING"):
                # RAISE EXCEPTION USING key = expr, … (no message text) —
                # fell into the expression fallback and shipped
                # ``'%', using …`` (wave 133).
                return self._parse_pg_raise_using(informational)
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            if informational:
                return PrintStatement(expression=expr)
            return RaiseErrorStatement(message=expr)

        # ``RAISE SQLSTATE 'xxxxx' [USING …]`` — folds into a literal
        # message like the condition-name form below (the raw path would
        # let the SQLSTATE→ERROR_STATE substitution mangle it).
        if (
            self._dialect == "postgresql"
            and self._current().upper_value == "SQLSTATE"
            and self._peek(1).type == TokenType.STRING
        ):
            self._advance()
            state = self._advance().value.strip("'")
            state_using: list[str] = []
            if self._current().is_keyword("USING"):
                self._advance()
                while (
                    not self._at_end() and self._current().type != TokenType.SEMICOLON
                ):
                    state_using.append(self._flat_value(self._current()))
                    self._advance()
            self._match_type(TokenType.SEMICOLON)
            content = f"SQLSTATE {state}" + (
                " (" + " ".join(state_using) + ")" if state_using else ""
            )
            literal = "'" + content.replace("'", "''") + "'"
            return RaiseErrorStatement(
                message=RawSQL(sql=literal, reason="pg sqlstate RAISE")
            )

        # ``RAISE condition_name [USING k = v, …]`` — the name folds into
        # a literal message (USING items appended as text, like the
        # format path); the raw-expression fallback shipped it verbatim.
        if (
            self._dialect == "postgresql"
            and self._current().type == TokenType.IDENTIFIER
            and (
                self._peek(1).type == TokenType.SEMICOLON
                or self._peek(1).is_keyword("USING")
            )
        ):
            cond = self._advance().value
            using_parts: list[str] = []
            if self._current().is_keyword("USING"):
                self._advance()
                while (
                    not self._at_end() and self._current().type != TokenType.SEMICOLON
                ):
                    using_parts.append(self._flat_value(self._current()))
                    self._advance()
            self._match_type(TokenType.SEMICOLON)
            content = cond + (" (" + " ".join(using_parts) + ")" if using_parts else "")
            literal = "'" + content.replace("'", "''") + "'"
            return RaiseErrorStatement(
                message=RawSQL(sql=literal, reason="pg condition-name RAISE")
            )

        # Level-less ``RAISE 'msg' [, args] [USING …]`` defaults to
        # EXCEPTION in plpgsql — same format path as the leveled form.
        if self._dialect == "postgresql" and self._current().type == TokenType.STRING:
            formatted = self._parse_pg_raise_format()
            if formatted is not None:
                return RaiseErrorStatement(message=formatted)
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return RaiseErrorStatement(message=expr)

    def _parse_pg_raise_using(self, informational: bool) -> ASTNode:
        """Parse the ``USING key = expr, …`` tail of a plpgsql RAISE.

        The ``message`` option IS the message; other options fold into
        the text (no separate channel off PostgreSQL) — waves 119/133.
        """
        self._advance()  # USING
        pairs: list[tuple[str, str]] = []
        while not self._at_end() and self._current().type != TokenType.SEMICOLON:
            key = self._parse_identifier().lower()
            if self._current().value == "=":
                self._advance()
            val_parts: list[str] = []
            while not self._at_end() and self._current().type not in (
                TokenType.COMMA,
                TokenType.SEMICOLON,
            ):
                val_parts.append(self._flat_value(self._current()))
                self._advance()
            pairs.append((key, " ".join(val_parts)))
            if not self._match_type(TokenType.COMMA):
                break
        self._match_type(TokenType.SEMICOLON)
        msg = next((v for k, v in pairs if k == "message"), None)
        rest = [f"{k} = {v}" for k, v in pairs if k != "message"]
        if msg is None:
            content = "; ".join(f"{k} = {v}" for k, v in pairs)
            literal = "'" + content.replace("'", "''") + "'"
            node: ASTNode = RawSQL(sql=literal, reason="pg RAISE USING")
        elif rest:
            tail = "; ".join(rest).replace("'", "''")
            node = RawSQL(sql=f"{msg} || ' ({tail})'", reason="pg RAISE USING")
        else:
            node = RawSQL(sql=msg, reason="pg RAISE USING")
        if informational:
            return PrintStatement(expression=node)
        return RaiseErrorStatement(message=node)

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

    def _parse_pg_dynamic_execute(self) -> ASTNode:
        """Parse plpgsql ``EXECUTE expr [INTO [STRICT] vars] [USING …]``."""
        self._expect_keyword("EXECUTE")
        expr = self._parse_expression_until_keyword("USING", "INTO")

        strict = False
        into_vars: list[str] = []
        if self._match_keyword("INTO"):
            if self._current().upper_value == "STRICT":
                self._advance()
                strict = True
            while not self._at_end():
                into_vars.append(self._parse_identifier())
                if not self._match_type(TokenType.COMMA):
                    break

        params: list[ASTNode] = []
        if self._match_keyword("USING"):
            while not self._at_end():
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
            strict=strict,
        )

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
        # MySQL's SELECT … INTO OUTFILE/DUMPFILE is a file export — the
        # variable-INTO parse mangled OUTFILE into a fake variable
        # (wave 223). Capture whole; admin-statement routing applies.
        if self._dialect == "mysql":
            j = 0
            depth = 0
            while True:
                tok_a = self._peek(j)
                if tok_a.type in (TokenType.SEMICOLON, TokenType.EOF):
                    break
                if tok_a.type == TokenType.LPAREN:
                    depth += 1
                elif tok_a.type == TokenType.RPAREN:
                    depth -= 1
                elif (
                    depth == 0
                    and tok_a.upper_value == "INTO"
                    and self._peek(j + 1).upper_value in ("OUTFILE", "DUMPFILE")
                ):
                    parts_of: list[str] = []
                    while (
                        not self._at_end()
                        and self._current().type != TokenType.SEMICOLON
                    ):
                        parts_of.append(self._advance().value)
                    self._match_type(TokenType.SEMICOLON)
                    return RawSQL(
                        sql=" ".join(parts_of),
                        reason="MySQL admin statement (SELECT INTO OUTFILE)",
                    )
                j += 1
                if j > 4000:
                    break
        self._expect_keyword("SELECT")

        # plpgsql's INTO may come FIRST (``SELECT INTO x id FROM …``) —
        # the list-first capture shredded it (wave 226). Normalize by
        # consuming the INTO vars here; the shared tail handles the rest.
        into_first_vars: list[str] = []
        if self._dialect == "postgresql" and self._current().is_keyword("INTO"):
            self._advance()
            while not self._at_end():
                into_first_vars.append(self._parse_identifier())
                if self._current().type == TokenType.COMMA:
                    self._advance()
                    continue
                break

        # Capture select list up to INTO or FROM
        select_parts: list[str] = []
        paren_depth = 0
        has_into = bool(into_first_vars)
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
        into_vars: list[str] = []
        if into_first_vars:
            into_vars = list(into_first_vars)
        else:
            self._expect_keyword("INTO")
        while not into_first_vars and not self._at_end():
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
