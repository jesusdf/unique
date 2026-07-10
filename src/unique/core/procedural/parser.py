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
from dataclasses import dataclass, field, replace

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AnonymousBlock,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CallStatement,
    CommentStatement,
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
    TransactionAction,
    TransactionStatement,
    TryCatchBlock,
    WaitForStatement,
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

    # ------------------------------------------------------------------
    # Source-family helpers
    #
    # The parser dispatches on the *source* dialect, of which there are only
    # two syntactic families: T-SQL and PL/SQL (Oracle/PostgreSQL/MySQL). These
    # helpers name that distinction so the family checks read intentionally
    # rather than as scattered ``self._dialect == "tsql"`` tests.
    # ------------------------------------------------------------------

    def _is_tsql_source(self) -> bool:
        """Whether the source dialect uses T-SQL procedural syntax."""
        return self._dialect == "tsql"

    def _parse_routine_body(self, with_pg_header: bool = True) -> list[ASTNode]:
        """Consume a routine header and parse its body for the source family.

        T-SQL uses ``AS <body>``; the PL/SQL family uses ``IS``/``AS``. When
        ``with_pg_header`` is set, PostgreSQL/MySQL also carry an extra
        ``LANGUAGE``/``$$`` header consumed by ``_consume_pg_routine_header``
        (procedures and functions); triggers have no such header.
        """
        if self._is_tsql_source():
            self._match_keyword("AS")
            return list(self._parse_tsql_body())
        if with_pg_header and self._dialect in ("postgresql", "mysql"):
            self._consume_pg_routine_header()
            return list(self._parse_plsql_body())
        if self._match_keyword("AS") or self._match_keyword("IS"):
            pass
        return list(self._parse_plsql_body())

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

    # A forward pass that dropped a source-only construct leaves a note like
    # "/* UNIQUE: <orig> -- <dialect>-only, no <target> equivalent */". Capture
    # <orig> and <dialect> so a transpilation back to <dialect> can restore it.
    _RESTORABLE_NOTE_RE = re.compile(
        r"(?is)^/\*\s*UNIQUE:\s*(.+?)\s*--\s*([a-z0-9_]+)-only,.*?\*/$"
    )

    @classmethod
    def _normalize_comment(cls, text: str, token_type: TokenType) -> CommentStatement:
        """Build a CommentStatement, normalizing only a line comment's spacing.

        The only permitted change to a source comment is ensuring exactly one
        space after ``--`` (ANSI SQL). Block comments are preserved verbatim,
        except that a restorable ``/* UNIQUE: … -- <dialect>-only … */`` note is
        tagged with its restore payload (see ``CommentStatement``).
        """
        if token_type == TokenType.LINE_COMMENT:
            # Preserve everything after the leading dashes, but guarantee a
            # single space between '--' and the comment text.
            body = text[2:]
            stripped = body.lstrip(" \t")
            normalized = "-- " + stripped if stripped else "--"
            return CommentStatement(text=normalized.rstrip(), style="line")
        m = cls._RESTORABLE_NOTE_RE.match(text.strip())
        if m:
            return CommentStatement(
                text=text,
                style="block",
                restore_sql=m.group(1).strip(),
                restore_dialect=m.group(2).strip(),
            )
        return CommentStatement(text=text, style="block")

    def _take_comments(self) -> list[ASTNode]:
        """Consume pending comment tokens, returning them as AST nodes.

        Unlike ``_skip_comments`` (which discards them), this preserves the
        comments so the emitter can re-emit them in place. Used by body-parsing
        loops where a comment occupies its own statement position.
        """
        nodes: list[ASTNode] = []
        while self._current().type in (
            TokenType.LINE_COMMENT,
            TokenType.BLOCK_COMMENT,
        ):
            tok = self._current()
            nodes.append(self._normalize_comment(tok.value, tok.type))
            self._advance()
        return nodes

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
        elif tok.is_keyword("ALTER") and self._is_tsql_source():
            return self._parse_alter()
        elif tok.is_keyword("EXEC", "EXECUTE", "DECLARE", "PRINT", "SET"):
            # A standalone anonymous block: a bare EXEC of a procedure, a DECLARE
            # of batch-local variables, a diagnostic PRINT, or a ``SET @v = …``
            # variable assignment. Parse it as a statement sequence so PRINT
            # becomes the target's message form and the assignment/EXEC is
            # translated, instead of falling back to verbatim RawSQL. (The batch
            # classifier only routes a ``SET @var`` assignment here — a session
            # option like ``SET NOCOUNT ON`` stays on the SET_OPTION path.)
            return self._parse_anonymous_block()
        elif tok.is_keyword("BEGIN") and not self._is_tsql_source():
            # A top-level Oracle/PL-SQL anonymous ``BEGIN … END;`` block (the
            # re-runnable DROP guard a schema opens with). T-SQL is excluded:
            # a bare BEGIN there is a transaction/BEGIN-TRY, handled elsewhere.
            return self._parse_anonymous_block()
        elif tok.is_keyword("IF") and self._is_tsql_source():
            # A top-level T-SQL control-flow guard (``IF [NOT] EXISTS(…) BEGIN …
            # END``) the batch classifier routed here — i.e. a *non-catalog*
            # condition (a system-catalog guard is handled on the DDL path). Parse
            # it as an anonymous block so the IF is translated (on Oracle,
            # ``IF EXISTS`` becomes a cursor FOR-loop emulation) instead of a
            # verbatim RawSQL carrier.
            return self._parse_anonymous_block()
        elif tok.upper_value == "CALL":
            # A standalone stored-procedure call (MySQL/PostgreSQL/Oracle
            # ``CALL proc(args)``). Wrap it in an anonymous block so each target
            # gets its call form (Oracle needs a BEGIN … END; shell).
            return self._parse_anonymous_block()
        else:
            return self._parse_fallback()

    def _parse_anonymous_block(self) -> ASTNode:
        """Parse a top-level statement sequence (no CREATE wrapper).

        Returns an AnonymousBlock carrying the parsed statements; the emitter
        renders the target-appropriate wrapper (e.g. PostgreSQL DO $$ … $$).
        A leading ``BEGIN``/trailing ``END`` PL/SQL wrapper is unwrapped so the
        block holds only its inner statements. Non-T-SQL sources parse the body
        with the PL/SQL statement parser (FOR loops, EXECUTE IMMEDIATE, …).
        Falls back to RawSQL if nothing parses, so behavior never regresses.
        """
        parse_stmt = (
            self._parse_tsql_statement
            if self._is_tsql_source()
            else self._parse_plsql_statement
        )
        statements: list[ASTNode] = []
        if not self._is_tsql_source() and self._current().is_keyword("DECLARE"):
            # A PL/SQL ``DECLARE`` opens a *section*: every declaration up to
            # BEGIN belongs to it. Taking only one leaks the rest as raw text
            # and leaves their references unrenamed (audit D9, shape B).
            self._advance()
            guard = 0
            while not self._at_end() and not self._current().is_keyword("BEGIN"):
                guard += 1
                if guard > 100000:
                    break
                before = self._pos
                decl = self._parse_plsql_declaration()
                if decl:
                    statements.append(decl)
                if self._pos == before:
                    self._advance()
        wrapped = self._match_keyword("BEGIN")
        stop = ("END",) if wrapped else ()
        statements += self._run_body_loop(parse_stmt, stop)
        if wrapped:
            self._match_keyword("END")
            self._match_type(TokenType.SEMICOLON)
        if not statements:
            return RawSQL(sql="", reason="Empty or unparsable anonymous block")
        return AnonymousBlock(statements=tuple(statements))

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

        body = self._parse_routine_body()

        if is_alter and self._is_tsql_source():
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

        body = self._parse_routine_body()

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

        # Events: INSERT, UPDATE, DELETE. T-SQL separates them with a comma
        # (``AFTER INSERT, UPDATE``); Oracle/PostgreSQL with ``OR``
        # (``BEFORE INSERT OR UPDATE``). Accept either separator.
        events = []
        update_of: list[str] = []
        while True:
            tok = self._current()
            if tok.is_keyword("INSERT", "UPDATE", "DELETE"):
                event = self._advance().upper_value
                events.append(event)
                # Oracle/PG ``UPDATE OF c1, c2``: the trigger fires only for
                # those columns. Capture the list (dropping it silently would
                # widen the trigger to every UPDATE).
                if event == "UPDATE" and self._match_keyword("OF"):
                    while self._current().type in (
                        TokenType.IDENTIFIER,
                        TokenType.KEYWORD,
                    ) and not self._current().is_keyword("ON", "OR", "FOR"):
                        update_of.append(self._advance().value)
                        if not self._match_type(TokenType.COMMA):
                            break
                if self._match_type(TokenType.COMMA) or self._match_keyword("OR"):
                    continue
                break
            else:
                break

        # ON table (Oracle/PG ordering, if not already captured)
        if not table_name and self._match_keyword("ON"):
            table_name, _ = self._parse_qualified_name()

        # Oracle COMPOUND TRIGGER (declarations + AFTER EACH ROW / AFTER
        # STATEMENT sections over a PL/SQL collection). Consume the rest of the
        # definition (so the emitter documents it rather than shredding the body)
        # and, when it matches the common "collect the affected key per row,
        # re-aggregate once in AFTER STATEMENT" idiom, also capture a row-level
        # equivalent body a mutating-table-free target (PostgreSQL) can run.
        if self._current().upper_value == "COMPOUND":
            raw_parts: list[str] = []
            while not self._at_end():
                tok = self._advance()
                if tok.type not in (
                    TokenType.LINE_COMMENT,
                    TokenType.BLOCK_COMMENT,
                ):
                    raw_parts.append(tok.value)
            return CreateTriggerStatement(
                name=name,
                table=table_name,
                timing=timing,
                events=tuple(events),
                update_of=tuple(update_of),
                or_replace=or_replace,
                schema=schema,
                compound=True,
                compound_row_body=self._compound_row_body(" ".join(raw_parts)),
            )

        # REFERENCING NEW TABLE AS x [OLD TABLE AS y] (PostgreSQL transition
        # tables; lexed as an identifier, so match by value). Collect the raw
        # clause up to FOR so it can be re-emitted faithfully to PostgreSQL.
        referencing = ""
        if self._current().upper_value == "REFERENCING":
            self._advance()
            ref_parts: list[str] = []
            while not self._at_end() and not self._current().is_keyword("FOR"):
                ref_parts.append(self._advance().value)
            referencing = " ".join(ref_parts)

        # FOR EACH ROW (Oracle/PG)
        for_each = "STATEMENT"
        if self._match_keyword("FOR"):
            self._match_keyword("EACH")
            if self._match_keyword("ROW"):
                for_each = "ROW"
            else:
                self._match_keyword("STATEMENT")

        # Oracle/PG row-condition clause: ``FOR EACH ROW WHEN (cond)``. The
        # condition references NEW/OLD without the colon sigil. Model it as
        # an IF wrapping the body — every target's existing trigger
        # machinery (PG plain IF, MySQL IF ... THEN, the T-SQL set-based
        # fold) then applies.
        when_cond = ""
        if self._current().is_keyword("WHEN"):
            self._advance()
            if self._match_type(TokenType.LPAREN):
                parts: list[str] = []
                depth = 1
                while not self._at_end() and depth > 0:
                    tok = self._advance()
                    if tok.type == TokenType.LPAREN:
                        depth += 1
                    elif tok.type == TokenType.RPAREN:
                        depth -= 1
                        if depth == 0:
                            break
                    parts.append(tok.value)
                when_cond = " ".join(parts)

        # PostgreSQL delegates the body to a trigger function:
        # ``EXECUTE {FUNCTION|PROCEDURE} fn(args)``. Capture the function name;
        # the body lives in that separate CREATE FUNCTION. Other dialects inline
        # the body after FOR EACH, parsed below.
        execute_function: str | None = None
        body: list[ASTNode] = []
        if self._match_keyword("EXECUTE"):
            if not self._match_keyword("FUNCTION"):
                self._match_keyword("PROCEDURE")
            execute_function, _ = self._parse_qualified_name()
            if self._match_type(TokenType.LPAREN):
                while not self._at_end() and self._current().type != TokenType.RPAREN:
                    self._advance()
                self._match_type(TokenType.RPAREN)
            self._match_type(TokenType.SEMICOLON)
        else:
            body = self._parse_routine_body(with_pg_header=False)
        if when_cond and body:
            body = [
                IfStatement(
                    condition=RawSQL(sql=when_cond, reason="trigger WHEN clause"),
                    then_body=tuple(body),
                )
            ]

        return CreateTriggerStatement(
            name=name,
            table=table_name,
            timing=timing,
            events=tuple(events),
            update_of=tuple(update_of),
            for_each=for_each,
            body=tuple(body),
            or_replace=or_replace,
            schema=schema,
            execute_function=execute_function,
            referencing=referencing,
        )

    # The common Oracle COMPOUND TRIGGER aggregation idiom: a collection filled
    # from ``:NEW.<fk>`` (or ``:OLD.``) once per row in AFTER EACH ROW, then
    # re-read in an AFTER STATEMENT ``FOR <v> IN 1 .. <n> LOOP`` that
    # re-aggregates the parent. Matched over the space-joined body tokens, so the
    # patterns tolerate the whitespace the lexer leaves around ``.``/``:``/``:=``.
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
        if self._is_tsql_source() and self._current().type == TokenType.VARIABLE:
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

        if self._is_tsql_source():
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

    # A type-carrier marker left by a forward transpilation when a non-portable
    # type was lowered to a permissive carrier, e.g. "TEXT /* UNIQUE: SQL_VARIANT
    # */" or "SQL_VARIANT /* UNIQUE: H_X.Y%TYPE */". The captured group is the
    # original type text (no "-- ..." suffix, which marks a non-type UNIQUE note).
    _CARRIER_TYPE_RE = re.compile(r"(?is)^/\*\s*UNIQUE:\s*(?!.*--)(.+?)\s*\*/$")
    # The restored original must look like a type: a (possibly qualified or
    # %TYPE/%ROWTYPE) name with an optional parenthesized parameter list.
    _CARRIER_TYPEISH_RE = re.compile(
        r"(?i)^([\w.]+(?:%\w+)?)\s*(?:\(\s*([\w, ]+)\s*\))?$"
    )

    def _take_carrier_origin(self) -> str | None:
        """If the current token is a ``/* UNIQUE: <orig> */`` type-carrier marker,
        consume it and return ``<orig>`` (the original type text); else None.

        A forward transpilation lowers a non-portable type to a permissive
        carrier and records the original here. The original is attached to the
        parsed (carrier) type as ``origin_comment`` so the transformer can decide,
        per target, whether to restore the original (target supports it) or
        re-emit a carrier — making a reverse/onward transpilation faithful.
        Checked directly against the current token (not via ``_match_type``,
        which skips comments).
        """
        tok = self._current()
        if tok.type != TokenType.BLOCK_COMMENT:
            return None
        m = self._CARRIER_TYPE_RE.match(tok.value.strip())
        if not m:
            return None
        original = m.group(1).strip()
        if not self._CARRIER_TYPEISH_RE.match(original):
            return None
        self._advance()  # consume the carrier comment
        return original

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

        # A no-parameter carrier comment appears right here; capture it before
        # _match_type (which skips comments) can discard it.
        origin = self._take_carrier_origin()
        if origin is not None:
            return DataType(name=type_name, origin_comment=origin)

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
            origin = self._take_carrier_origin()

        return DataType(name=type_name, params=tuple(params), origin_comment=origin)

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

        origin = self._take_carrier_origin()
        if origin is not None:
            return DataType(name=type_name, origin_comment=origin)

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
            origin = self._take_carrier_origin()

        return DataType(name=type_name, params=tuple(params), origin_comment=origin)

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

    def _parse_set_statement(self) -> ASTNode | None:
        """Parse SET @var = expr or SET NOCOUNT ON."""
        self._expect_keyword("SET")
        tok = self._current()

        # SET NOCOUNT/NOEXEC/… ON/OFF — a session option with no portable
        # equivalent (documented as a comment). Match on the option name, not the
        # token type: some (e.g. NOEXEC) are not reserved words and lex as bare
        # identifiers. IDENTITY_INSERT is handled separately below.
        if tok.upper_value in {
            "NOCOUNT",
            "NOEXEC",
            "QUOTED_IDENTIFIER",
            "ANSI_NULLS",
            "XACT_ABORT",
            "ARITHABORT",
            "ROWCOUNT",
        }:
            kw = self._advance().value
            # These options take a short argument (ON/OFF or a value/var).
            # T-SQL statements often omit the trailing semicolon, so we must
            # NOT scan to the next ';' (that would swallow the whole body).
            # Consume at most one argument token (ON/OFF or a value).
            arg = ""
            if self._current().is_keyword("ON", "OFF") or self._current().type in (
                TokenType.NUMBER,
                TokenType.VARIABLE,
                TokenType.IDENTIFIER,
            ):
                arg = self._advance().value
            self._match_type(TokenType.SEMICOLON)
            original = f"SET {kw} {arg}".rstrip()
            self._warnings.append(f"{original} skipped (no equivalent)")
            # Keep the original text in the sql field so the transformer can
            # preserve it as a comment (documenting the dropped statement).
            return RawSQL(sql=original, reason="Dialect-specific SET option")

        # SET IDENTITY_INSERT <table> ON/OFF — no portable equivalent; capture
        # the original so the transformer can document it as a comment instead
        # of mis-parsing it as a DML statement. The table may be schema-qualified
        # (dbo.t), which the lexer splits into identifier '.' identifier tokens.
        if tok.is_keyword("IDENTITY_INSERT"):
            self._advance()
            target = ""
            while self._current().type in (
                TokenType.IDENTIFIER,
                TokenType.VARIABLE,
                TokenType.DOT,
            ):
                target += self._advance().value
            state = ""
            if self._current().is_keyword("ON", "OFF"):
                state = self._advance().value
            self._match_type(TokenType.SEMICOLON)
            original = f"SET IDENTITY_INSERT {target} {state}".rstrip()
            self._warnings.append(f"{original} skipped (no equivalent)")
            return RawSQL(sql=original, reason="Dialect-specific SET option")

        # SET @variable = expression
        if tok.type == TokenType.VARIABLE:
            var_name = self._advance().value
            self._match_type(TokenType.OPERATOR)  # =
            expr = self._parse_expression_until_semicolon()
            self._match_type(TokenType.SEMICOLON)
            return SetVariableStatement(name=var_name, value=expr)

        return self._parse_embedded_dml()

    def _peek_is_transaction(self) -> bool:
        """Whether a BEGIN starts a transaction (BEGIN TRAN/TRANSACTION) rather
        than a BEGIN...END block."""
        nxt = self._peek(1)
        return nxt.type == TokenType.KEYWORD and nxt.upper_value in (
            "TRAN",
            "TRANSACTION",
        )

    def _parse_transaction(self) -> ASTNode:
        """Parse a T-SQL transaction-control statement.

        Handles ``BEGIN TRAN[SACTION] [name]``, ``COMMIT [TRAN[SACTION]|WORK]``,
        ``ROLLBACK [TRAN[SACTION]|WORK] [name]`` and ``SAVE TRAN[SACTION] name``.
        An optional transaction/savepoint name is captured.
        """
        verb = self._advance().upper_value  # BEGIN | COMMIT | ROLLBACK | SAVE
        # Consume an optional TRAN/TRANSACTION/WORK keyword.
        self._match_keyword("TRAN", "TRANSACTION", "WORK")
        # Optional transaction or savepoint name (identifier or @variable).
        name: str | None = None
        if self._current().type in (TokenType.IDENTIFIER, TokenType.VARIABLE):
            name = self._advance().value
        self._match_type(TokenType.SEMICOLON)

        if verb == "BEGIN":
            action = TransactionAction.BEGIN
        elif verb == "COMMIT":
            action = TransactionAction.COMMIT
        elif verb == "SAVE":
            action = TransactionAction.SAVEPOINT
        else:
            action = TransactionAction.ROLLBACK
        return TransactionStatement(action=action, name=name)

    def _parse_waitfor(self) -> ASTNode:
        """Parse T-SQL ``WAITFOR DELAY '<hh:mm:ss>'`` / ``WAITFOR TIME '...'``."""
        self._expect_keyword("WAITFOR")
        kind = "DELAY"
        if self._match_keyword("TIME"):
            kind = "TIME"
        else:
            self._match_keyword("DELAY")
        value = ""
        if self._current().type == TokenType.STRING:
            value = self._advance().value
        self._match_type(TokenType.SEMICOLON)
        literal = value.strip().strip("'\"")
        seconds: float | None = None
        if kind == "DELAY":
            parts = literal.split(":")
            try:
                nums = [float(p) for p in parts]
                if len(nums) == 3:
                    seconds = nums[0] * 3600 + nums[1] * 60 + nums[2]
                elif len(nums) == 2:
                    seconds = nums[0] * 60 + nums[1]
                elif len(nums) == 1:
                    seconds = nums[0]
            except ValueError:
                seconds = None
        return WaitForStatement(kind=kind, value=literal, seconds=seconds)

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

    # ---------------------------------------------------------------
    # Body parsing — PL/SQL (Oracle) and PL/pgSQL
    # ---------------------------------------------------------------

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

    def _parse_call_statement(self) -> ASTNode:
        """Parse a stored-procedure call: ``CALL name(args)`` (MySQL/PG/Oracle).
        ``CALL`` lexes as an identifier, so the caller matches it by value."""
        self._advance()  # CALL
        name, schema = self._parse_qualified_name()
        args = self._capture_call_args()
        self._match_type(TokenType.SEMICOLON)
        return CallStatement(name=name, args=args, schema=schema)

    def _capture_call_args(self) -> str:
        """Capture the ``(…)`` argument text of a procedure call, if present.
        Assumes the current token is the opening ``(``; returns the normalized
        argument text (no outer parens)."""
        if not self._match_type(TokenType.LPAREN):
            return ""
        arg_tokens: list[str] = []
        depth = 1
        while not self._at_end() and depth > 0:
            cur = self._current()
            if cur.type == TokenType.LPAREN:
                depth += 1
            elif cur.type == TokenType.RPAREN:
                depth -= 1
                if depth == 0:
                    self._advance()
                    break
            arg_tokens.append(self._advance().value)
        joined = " ".join(arg_tokens)
        joined = re.sub(r"\s+([,)])", r"\1", joined)
        return re.sub(r"\(\s+", "(", joined).strip()

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
            parts.append(tok.value)
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
            select_parts.append(tok.value)
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
            rest_parts.append(tok.value)
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
                    rest_parts2.append(tok.value)
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

    def _starts_row_ref_assignment(self) -> bool:
        """Whether the cursor sits on the ``:`` of an Oracle row-level trigger
        assignment ``:NEW.col := …`` / ``:OLD.col := …``.

        Requires a ``:=`` before the statement terminator, so a ``:NEW.col`` used
        only as a value (never at statement start in valid PL/SQL) is left to the
        embedded-DML path rather than mis-parsed as an assignment target."""
        if self._current().type != TokenType.COLON:
            return False
        if self._peek(1).upper_value not in ("NEW", "OLD"):
            return False
        i = self._pos + 2
        n = len(self._tokens)
        while i < n:
            ttype = self._tokens[i].type
            if ttype in (TokenType.SEMICOLON, TokenType.EOF):
                return False
            if ttype == TokenType.ASSIGN:
                return True
            i += 1
        return False

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
        """Parse RETURN [expression].

        A bare ``RETURN`` (T-SQL early-exit from a procedure) takes no value.
        Only treat what follows as the return expression when it is on the same
        source line and does not start a new statement; otherwise the following
        statement (e.g. a `SELECT` on the next line) must not be absorbed.
        """
        self._expect_keyword("RETURN")
        cur = self._current()
        if cur.type == TokenType.SEMICOLON or self._at_end():
            self._match_type(TokenType.SEMICOLON)
            return ReturnStatement()
        # A statement keyword after RETURN means this RETURN has no value
        # (early exit). A scalar return value never begins with one of these
        # (a subquery value is parenthesized: RETURN (SELECT ...)), so this
        # holds even on the same source line.
        _stmt_starts = {
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
            "IF",
            "WHILE",
            "SET",
            "DECLARE",
            "BEGIN",
            "EXEC",
            "EXECUTE",
            "PRINT",
            "RAISERROR",
            "THROW",
            "RETURN",
            "FETCH",
            "OPEN",
            "CLOSE",
            "END",
        }
        if cur.type == TokenType.KEYWORD and cur.upper_value in _stmt_starts:
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
        """Capture a scalar assignment value as raw SQL until a boundary.

        Used for ``SET @var = <expr>``. Besides ';'/END and the usual
        control-flow boundaries, a DML verb (SELECT/INSERT/UPDATE/DELETE/MERGE)
        beginning a new line ends the value: a scalar assignment cannot contain
        a bare statement, so the following statement must not be absorbed (a
        common shape when T-SQL omits the ';' terminator).
        """
        parts: list[str] = []
        paren_depth = 0
        case_depth = 0
        first = True
        prev_line: int | None = None
        dml_starts = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"}
        while not self._at_end():
            tok = self._current()
            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
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
            # A DML verb on a new line ends the scalar value.
            if (
                not first
                and paren_depth == 0
                and case_depth == 0
                and tok.type == TokenType.KEYWORD
                and tok.upper_value in dml_starts
                and prev_line is not None
                and tok.line is not None
                and tok.line != prev_line
            ):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            # A line comment inside a captured expression would, once the
            # multi-line expression is flattened to a single line, comment out
            # everything after it (including the rest of the expression and the
            # statement terminator). Convert it to a block comment so the text
            # is preserved without swallowing the rest of the line.
            if tok.type == TokenType.LINE_COMMENT:
                parts.append(self._line_comment_to_block(tok.value))
            else:
                parts.append(tok.value)
            prev_line = tok.line
            first = False
            self._advance()
        raw = " ".join(parts).strip()
        if raw.upper() == "NULL":
            return Literal(value=None, dtype="null")
        return RawSQL(sql=raw, reason="captured expression")

    @staticmethod
    def _line_comment_to_block(text: str) -> str:
        """Turn a ``-- comment`` token into a ``/* comment */`` block comment."""
        body = text.lstrip()
        if body.startswith("--"):
            body = body[2:]
        body = body.strip()
        # Avoid nested block-comment terminators.
        body = body.replace("*/", "* /")
        return f"/* {body} */" if body else "/* */"

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
                and self._is_tsql_source()
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
    #: T-SQL DECLARE CURSOR options (between CURSOR and FOR) — scope and
    #: performance hints with no counterpart in the targets.
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
        values_seen = False
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
                and self._is_tsql_source()
                and self._starts_new_dml(tok, prev_tok, lead_verb, values_seen)
            ):
                break

            # A depth-0 SET that begins a *statement* (SET NOCOUNT/IDENTITY_INSERT
            # /other option, or SET @var = ...) ends the captured DML. This is
            # distinguishable from an UPDATE/MERGE's own "SET <column> = ..."
            # clause, whose SET is followed by a column identifier, by peeking at
            # the token after SET.
            if (
                not first
                and paren_depth == 0
                and begin_depth == 0
                and case_depth == 0
                and self._is_tsql_source()
                and tok.is_keyword("SET")
                and self._set_starts_statement(self._peek(1))
            ):
                break

            if tok.is_keyword("VALUES"):
                values_seen = True
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

            # A line/block comment that starts its own line AND is followed by
            # a statement boundary (END, or a new statement keyword) is a
            # between-statements comment, not part of this DML. Stop so the body
            # loop preserves it as a standalone CommentStatement. A comment that
            # continues the same statement (followed by FROM/WHERE/JOIN/...) is
            # left inside the DML text.
            if (
                not first
                and paren_depth == 0
                and begin_depth == 0
                and case_depth == 0
                and tok.type in (TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT)
                and prev_tok is not None
                and tok.line is not None
                and prev_tok.line is not None
                and tok.line != prev_tok.line
                and self._comment_precedes_boundary()
            ):
                break

            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1

            # The captured tokens are re-joined with spaces, losing newlines.
            # A line comment (-- ...) relies on a newline to terminate, so
            # without one it would swallow the rest of the statement. Convert
            # it to an equivalent block comment so the surrounding SQL stays
            # intact and the comment is still preserved in place.
            if tok.type == TokenType.LINE_COMMENT:
                body = tok.value[2:].strip()
                parts.append(f"/* {body} */" if body else "/* */")
                prev_tok = tok
                self._advance()
                first = False
                continue

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
            # A MERGE action clause: WHEN [NOT] MATCHED THEN UPDATE/INSERT/
            # DELETE stays inside the MERGE (T-SQL requires the terminating
            # ';' on MERGE, so a real next statement is never absorbed).
            "THEN",
            "ALL",
            "EXISTS",
            "IN",
        }
    )

    def _comment_precedes_boundary(self) -> bool:
        """Look past consecutive comments from the current position; return True
        if the next real token ends the current statement (END / EOF / a new
        statement keyword). Used to decide whether an own-line comment belongs
        between statements rather than inside the current DML."""
        i = self._pos
        n = len(self._tokens)
        while i < n and self._tokens[i].type in (
            TokenType.LINE_COMMENT,
            TokenType.BLOCK_COMMENT,
        ):
            i += 1
        if i >= n:
            return True
        nxt = self._tokens[i]
        if nxt.type == TokenType.EOF:
            return True
        if nxt.type == TokenType.SEMICOLON:
            return True
        return nxt.type == TokenType.KEYWORD and nxt.upper_value in {
            "END",
            "IF",
            "WHILE",
            "SET",
            "DECLARE",
            "BEGIN",
            "RETURN",
            "EXEC",
            "EXECUTE",
            "PRINT",
            "RAISERROR",
            "THROW",
            "FETCH",
            "OPEN",
            "CLOSE",
            "ELSE",
        }

    # Keywords that, following SET, mark a statement-level SET (not an
    # UPDATE/MERGE "SET <column> = ..." clause).
    _SET_OPTION_KEYWORDS = frozenset(
        {
            "NOCOUNT",
            "NOEXEC",
            "IDENTITY_INSERT",
            "QUOTED_IDENTIFIER",
            "ANSI_NULLS",
            "XACT_ABORT",
            "ARITHABORT",
            "ROWCOUNT",
        }
    )

    def _set_starts_statement(self, after_set: Token) -> bool:
        """Whether a SET token begins a new statement rather than continuing an
        UPDATE/MERGE SET clause, judged by the token right after SET."""
        if after_set.type == TokenType.VARIABLE:
            return True
        # A session option (SET NOEXEC/NOCOUNT/…). The option name may lex as a
        # keyword or a bare identifier (e.g. NOEXEC is not a reserved word), so
        # match on the name, not the token type.
        return after_set.upper_value in self._SET_OPTION_KEYWORDS

    def _starts_new_dml(
        self,
        tok: Token,
        prev_tok: Token | None,
        lead_verb: str = "",
        values_seen: bool = False,
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
        # An INSERT ... SELECT keeps its source SELECT attached — but only when
        # the INSERT has no VALUES clause yet. Once VALUES was seen, a SELECT on
        # a new line is a separate statement (e.g. INSERT INTO @t VALUES (...)
        # followed by SELECT ... FROM @t).
        if lead_verb == "INSERT" and tok.upper_value == "SELECT" and not values_seen:
            return False
        # After an INSERT ... VALUES (...), a SELECT is always a new statement
        # (an INSERT cannot have both VALUES and a source SELECT), even on the
        # same source line.
        if (
            lead_verb == "INSERT"
            and tok.upper_value == "SELECT"
            and values_seen
            and prev_tok.type == TokenType.RPAREN
        ):
            return True
        if tok.line == prev_tok.line:
            return False
        # A CTE's main statement: ``WITH x AS (...)`` is followed by its
        # SELECT/INSERT/UPDATE/DELETE after the closing paren — that verb
        # belongs to the WITH, not to a new statement.
        if lead_verb == "WITH" and prev_tok.type == TokenType.RPAREN:
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
        """When we can't parse, capture everything as RawSQL (a documented
        carrier) and register a warning so the loss is never silent. Keep a newline
        between tokens that came from different source lines, so a large construct
        is preserved as readable multi-line text instead of one enormous line that
        breaks editors and diffs."""
        parts: list[str] = []
        prev_line: int | None = None
        while not self._at_end():
            tok = self._current()
            if parts:
                parts.append(
                    " " if prev_line is None or tok.line == prev_line else "\n"
                )
            parts.append(tok.value)
            prev_line = tok.line
            self._advance()
        self._warnings.append(
            "Could not parse procedural construct; preserved as a documented "
            "carrier for manual review"
        )
        return RawSQL(
            sql="".join(parts).strip(),
            reason="Could not parse procedural construct",
        )
