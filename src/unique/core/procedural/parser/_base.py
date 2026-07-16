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
from dataclasses import dataclass, field, replace

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AnonymousBlock,
    ASTNode,
    CallStatement,
    CommentStatement,
    ContinueStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    DataType,
    EmbeddedDML,
    ExitStatement,
    IfStatement,
    Literal,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SetVariableStatement,
    TransactionAction,
    TransactionStatement,
    WaitForStatement,
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


class ParserBase:
    """Recursive descent parser for procedural SQL constructs.

    Handles T-SQL, Oracle PL/SQL, PostgreSQL PL/pgSQL, and MySQL
    procedural syntax.
    """

    # ------------------------------------------------------------------
    # Cross-family contract: the statement-family mixins (_tsql/_plsql)
    # provide these; the base dispatch and shared capture loops call them.
    # ------------------------------------------------------------------

    def _is_tsql_source(self) -> bool:
        """Whether the source dialect uses T-SQL procedural syntax."""
        return self._dialect == "tsql"

    def _at_tsql_stmt_boundary(self) -> bool:
        raise NotImplementedError  # TsqlStatementsMixin

    def _parse_tsql_body(self) -> list[ASTNode]:
        raise NotImplementedError  # TsqlStatementsMixin

    def _parse_tsql_statement(self) -> ASTNode | None:
        raise NotImplementedError  # TsqlStatementsMixin

    def _parse_tsql_assignment_select(
        self, select_parts: list[str]
    ) -> tuple[list[str], list[str]] | None:
        raise NotImplementedError  # TsqlStatementsMixin

    def _parse_plsql_body(self) -> list[ASTNode]:
        raise NotImplementedError  # PlsqlStatementsMixin

    def _parse_plsql_statement(self) -> ASTNode | None:
        raise NotImplementedError  # PlsqlStatementsMixin

    def _parse_plsql_declaration(self) -> ASTNode | None:
        raise NotImplementedError  # PlsqlStatementsMixin

    def _parse_plsql_open(self) -> ASTNode:
        raise NotImplementedError  # PlsqlStatementsMixin

    def _parse_plsql_close(self) -> ASTNode:
        raise NotImplementedError  # PlsqlStatementsMixin

    def _compound_row_body(self, raw: str) -> tuple[ASTNode, ...]:
        raise NotImplementedError  # PlsqlStatementsMixin

    def __init__(self, dialect: str) -> None:
        self._dialect = dialect
        self._tokens: list[Token] = []
        self._pos = 0
        self._errors: list[ParseError] = []
        self._warnings: list[str] = []
        #: position ("1") → parameter name, set per PG routine so bodies
        #: spliced in later (old-style quoted bodies) get the same $n
        #: rewrite as tokens present at signature-parse time.
        self._pg_positional_names: dict[str, str] = {}
        #: uppercased RETURNS type of the PG routine being parsed — a
        #: LANGUAGE sql body needs it to decide whether its trailing
        #: SELECT is the function result (becomes the RETURN).
        self._pg_fn_return_type = ""

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
            if self._dialect == "postgresql" and self._current().is_keyword(
                "SELECT", "VALUES", "WITH", "INSERT", "UPDATE", "DELETE"
            ):
                return self._parse_pg_sql_function_body()
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
        self._pg_positional_names = {}

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

            # Remaining PG routine attributes; unconsumed they spill into
            # the body as garbage declarations (``STRICT LANGUAGE;``).
            if upper in ("STRICT", "LEAKPROOF", "WINDOW"):
                self._advance()
                continue
            if upper == "PARALLEL":
                self._advance()
                if not self._at_end():
                    self._advance()  # SAFE / UNSAFE / RESTRICTED
                continue
            if upper in ("COST", "SUPPORT") or (
                upper == "ROWS" and self._peek(1).type == TokenType.NUMBER
            ):
                self._advance()
                if not self._at_end():
                    self._advance()  # the number / support function
                continue
            if upper == "CALLED":
                self._advance()  # CALLED ON NULL INPUT
                while not self._at_end() and self._current().upper_value in (
                    "ON",
                    "NULL",
                    "INPUT",
                ):
                    self._advance()
                continue
            if upper == "RETURNS" and self._peek(1).is_keyword("NULL"):
                self._advance()  # RETURNS NULL ON NULL INPUT
                while not self._at_end() and self._current().upper_value in (
                    "NULL",
                    "ON",
                    "INPUT",
                ):
                    self._advance()
                continue

            if tok.is_keyword("AS"):
                self._advance()
                continue

            # Old-style plpgsql body: ``AS '…begin … end;…'`` — the whole
            # body is ONE string literal. Unquote and re-lex it in place
            # so the routine parses exactly like its dollar-quoted twin.
            if tok.type == TokenType.STRING and self._dialect == "postgresql":
                inner = tok.value[1:-1].replace("''", "'")
                body_tokens = [
                    self._alias_positional_token(t)
                    for t in Lexer(inner, self._dialect).tokens
                    if t.type != TokenType.EOF
                ]
                self._tokens[self._pos : self._pos + 1] = body_tokens
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
        if self._dialect == "postgresql":
            params = self._alias_pg_positional_params(params)

        if self._plsql_collection_type_ahead():
            return self._parse_fallback()
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
        if self._dialect == "postgresql":
            params = self._alias_pg_positional_params(params)

        return_type: DataType | None = None
        if self._match_keyword("RETURN"):
            # Oracle's RETURN type may be dotted and/or a %TYPE reference
            # (``RETURN tbl.col%TYPE``, ``RETURN pkg.type``); the plain type
            # parser left ``.col%TYPE`` unconsumed and shattered the
            # declaration section that follows.
            return_type = self._parse_data_type_or_reference()
        elif self._match_keyword("RETURNS"):
            return_type = (
                self._parse_pg_data_type()
                if self._dialect == "postgresql"
                else self._parse_data_type()
            )
            # PG's two-word SETOF <type>: parse as ONE unit or the inner
            # type name leaks into the header/body as garbage.
            if self._dialect == "postgresql" and return_type.name.upper() == "SETOF":
                # PG-aware inner parse, or ``SETOF integer[]`` silently
                # narrows to ``SETOF integer`` (wave 115).
                inner = self._parse_pg_data_type()
                return_type = DataType(name=f"SETOF {inner.name}")

        # An Oracle PIPELINED table function streams rows of a package
        # collection type via PIPE ROW — no mechanical form on any other
        # engine; preserve the whole definition as a documented carrier
        # instead of shredding its body. The keyword sits between the (often
        # dotted package) return type and AS/IS, so scan a short window.
        for offset in range(6):
            peeked = self._peek(offset)
            if peeked.is_keyword("AS", "IS") or peeked.type == TokenType.EOF:
                break
            if peeked.upper_value == "PIPELINED":
                return self._parse_fallback()

        self._pg_fn_return_type = return_type.name.upper() if return_type else ""

        if self._plsql_collection_type_ahead():
            return self._parse_fallback()
        lang = self._pg_non_sql_language_ahead()
        if lang is not None:
            # A C/internal/PL-other function has no SQL body to transpile;
            # the body parse emitted an EMPTY plpgsql function (silent loss
            # of the implementation reference — wave 122). Same-dialect
            # ships verbatim; the transformer carriers it cross-dialect.
            return self._whole_unit_raw(f"non-SQL language function (LANGUAGE {lang})")
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
                    parts.append(self._flat_value(tok))
                when_cond = " ".join(parts)

        # PostgreSQL delegates the body to a trigger function:
        # ``EXECUTE {FUNCTION|PROCEDURE} fn(args)``. Capture the function name;
        # the body lives in that separate CREATE FUNCTION. Other dialects inline
        # the body after FOR EACH, parsed below.
        execute_function: str | None = None
        execute_args: list[str] = []
        body: list[ASTNode] = []
        if self._match_keyword("EXECUTE"):
            if not self._match_keyword("FUNCTION"):
                self._match_keyword("PROCEDURE")
            execute_function, _ = self._parse_qualified_name()
            if self._match_type(TokenType.LPAREN):
                depth = 1
                current: list[str] = []
                while not self._at_end() and depth > 0:
                    tok = self._current()
                    if tok.type == TokenType.LPAREN:
                        depth += 1
                    elif tok.type == TokenType.RPAREN:
                        depth -= 1
                        if depth == 0:
                            self._advance()
                            break
                    if tok.type == TokenType.COMMA and depth == 1:
                        execute_args.append(" ".join(current))
                        current = []
                    else:
                        current.append(str(tok.value))
                    self._advance()
                if current:
                    execute_args.append(" ".join(current))
            self._match_type(TokenType.SEMICOLON)
        else:
            if self._plsql_collection_type_ahead():
                return self._parse_fallback()
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
            execute_args=tuple(execute_args),
            referencing=referencing,
        )

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

    #: Words that can only start a TYPE in a PG parameter position — they
    #: decide type-only parameters like ``varchar(10)`` where the token
    #: after the first word (a paren) doesn't end the parameter.
    _PG_TYPE_KEYWORDS = frozenset(
        {
            "VARCHAR",
            "NVARCHAR",
            "CHAR",
            "NCHAR",
            "INT",
            "INTEGER",
            "SMALLINT",
            "BIGINT",
            "NUMERIC",
            "DECIMAL",
            "FLOAT",
            "REAL",
            "DOUBLE",
            "DATE",
            "TIMESTAMP",
            "TIME",
            "BOOLEAN",
            "BOOL",
            "BIT",
            "TEXT",
            "UUID",
            "XML",
            "JSON",
            "JSONB",
            "INTERVAL",
        }
    )

    _ARRAY_SUFFIX_RE = re.compile(r"\[\s*\]\Z")

    def _parse_pg_data_type(self) -> DataType:
        """Parse a PG parameter type: the shared dotted/parenned parse
        plus PG spellings — ``DOUBLE PRECISION``, ``TIMESTAMP/TIME
        [WITH|WITHOUT] TIME ZONE`` and ``int[]`` array suffixes (the
        lexer folds ``[]`` into one bracket token)."""
        dtype = self._parse_data_type_or_reference()
        upper = dtype.name.upper()
        cur = self._current()
        if upper == "DOUBLE" and cur.value.upper() == "PRECISION":
            dtype = replace(dtype, name=f"{dtype.name} {self._advance().value}")
        elif upper in ("TIMESTAMP", "TIME") and cur.value.upper() in (
            "WITH",
            "WITHOUT",
        ):
            words = [self._advance().value]
            while words and self._current().value.upper() in ("TIME", "ZONE"):
                words.append(self._advance().value)
            dtype = replace(dtype, name=" ".join([dtype.name, *words]))
        while (
            self._current().type == TokenType.IDENTIFIER
            and self._ARRAY_SUFFIX_RE.fullmatch(self._current().value) is not None
        ):
            self._advance()
            dtype = replace(dtype, name=dtype.name + "[]")
        return dtype

    def _alias_pg_positional_params(
        self, params: list[ParameterDefinition]
    ) -> list[ParameterDefinition]:
        """Name PG positional parameters and re-point ``$n`` references.

        plpgsql addresses parameters positionally (``$1``) whether or not
        they are named; no target engine can. Unnamed (type-only)
        parameters get synthesized names (``p1``…), and every remaining
        ``$n`` VARIABLE token in the unit's body is rewritten to the
        n-th parameter's name — the token-level equivalent of plpgsql's
        own ``ALIAS FOR $n``, applied before the body parses so every
        downstream consumer sees a real identifier. String literals are
        untouched (they are single STRING tokens)."""
        taken = {p.name.lower() for p in params if p.name}
        named: list[ParameterDefinition] = []
        for i, param in enumerate(params, start=1):
            if param.name:
                named.append(param)
                continue
            candidate = f"p{i}"
            while candidate.lower() in taken:
                candidate += "_"
            taken.add(candidate.lower())
            named.append(replace(param, name=candidate))

        by_position = {str(i): p.name for i, p in enumerate(named, start=1)}
        self._pg_positional_names = by_position
        self._tokens[self._pos :] = [
            self._alias_positional_token(t) for t in self._tokens[self._pos :]
        ]
        return named

    def _alias_positional_token(self, tok: Token) -> Token:
        """Map a ``$n`` VARIABLE token to its parameter-name IDENTIFIER."""
        if tok.type != TokenType.VARIABLE or not tok.value.startswith("$"):
            return tok
        name = self._pg_positional_names.get(tok.value[1:])
        if not name:
            return tok
        return Token(
            type=TokenType.IDENTIFIER, value=name, line=tok.line, column=tok.column
        )

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
        elif self._dialect == "postgresql":
            # PG: [argmode] [argname] argtype [{DEFAULT | =} value] — the
            # argmode comes FIRST (the reverse of Oracle's name-first
            # order) and the name is optional: ``(int, int)`` declares two
            # positional parameters the body references as $1/$2.
            if self._match_keyword("INOUT"):
                direction = "INOUT"
            elif self._match_keyword("OUT"):
                direction = "OUT"
            elif self._match_keyword("IN"):
                direction = "IN"

            tok = self._current()
            nxt = self._peek(1)
            type_only = tok.upper_value in self._PG_TYPE_KEYWORDS or (
                nxt.type in (TokenType.COMMA, TokenType.RPAREN)
                or nxt.is_keyword("DEFAULT")
                or nxt.type == TokenType.ASSIGN
                or (nxt.type == TokenType.OPERATOR and nxt.value == "=")
            )
            if not type_only:
                name = self._parse_identifier()
            data_type = self._parse_pg_data_type()

            if (
                self._match_keyword("DEFAULT")
                or self._match_type(TokenType.ASSIGN)
                or (
                    self._current().type == TokenType.OPERATOR
                    and self._current().value == "="
                    and self._advance()
                )
            ):
                default = self._parse_expression_simple()
        else:
            # Oracle: name [IN|OUT|INOUT] type [DEFAULT value]
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

    _CARRIER_TYPE_RE = re.compile(r"(?is)^/\*\s*UNIQUE:\s*(?!.*--)(.+?)\s*\*/$")
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

    def _consume_type_attributes(self) -> bool:
        """Consume MySQL numeric-type attributes (UNSIGNED/SIGNED/
        ZEROFILL) so parameter/declare grammars don't shred the rest of
        the routine; True when UNSIGNED was present."""
        unsigned = False
        while self._current().type in (
            TokenType.KEYWORD,
            TokenType.IDENTIFIER,
        ) and self._current().upper_value in (
            "UNSIGNED",
            "SIGNED",
            "ZEROFILL",
            "BINARY",
        ):
            if self._current().upper_value == "UNSIGNED":
                unsigned = True
            self._advance()
        return unsigned

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
                        cols.append(self._flat_value(tok))
                        self._advance()
                        break
                cols.append(self._flat_value(tok))
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

        unsigned = self._consume_type_attributes()
        return DataType(
            name=type_name,
            params=tuple(params),
            unsigned=unsigned,
            origin_comment=origin,
        )

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

        unsigned = self._consume_type_attributes()
        return DataType(
            name=type_name,
            params=tuple(params),
            unsigned=unsigned,
            origin_comment=origin,
        )

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
            arg_tokens.append(self._flat_value(self._advance()))
        joined = " ".join(arg_tokens)
        joined = re.sub(r"\s+([,)])", r"\1", joined)
        return re.sub(r"\(\s+", "(", joined).strip()

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

    def _parse_dbms_output(self) -> ASTNode:
        """Parse DBMS_OUTPUT.PUT_LINE(expr)."""
        self._advance()  # DBMS_OUTPUT
        self._match_type(TokenType.DOT)
        self._match_keyword("PUT_LINE")
        expr = self._parse_expression_until_semicolon()
        self._match_type(TokenType.SEMICOLON)
        return PrintStatement(expression=expr)

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
            parts.append(self._flat_value(tok))
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

    def _flat_value(self, tok: Token) -> str:
        """Token text safe for a capture that is later flattened to one line.

        A line comment relies on its newline to terminate; once the capture
        is ``" ".join``-ed the comment would swallow everything after it —
        including the rest of the expression (``IF v --note`` lost
        ``= 'U' THEN``). Comments are trivia: convert to an inline block
        comment so the text is preserved without eating the line. Every
        capture loop that flattens MUST append via this helper."""
        if tok.type == TokenType.LINE_COMMENT:
            return self._line_comment_to_block(tok.value)
        return tok.value

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
        stops = {k.upper() for k in keywords}
        while not self._at_end():
            tok = self._current()
            is_call = (
                tok.type == TokenType.KEYWORD and self._peek(1).type == TokenType.LPAREN
            )
            # Some stop words (MySQL's DO) tokenize as identifiers.
            is_stop = tok.is_keyword(*keywords) or (
                tok.type == TokenType.IDENTIFIER and tok.upper_value in stops
            )
            if paren_depth == 0 and not (first and is_call) and is_stop and not is_call:
                break
            if paren_depth == 0 and tok.type == TokenType.SEMICOLON:
                break
            if paren_depth == 0 and tok.is_keyword("END"):
                break
            if tok.type == TokenType.LPAREN:
                paren_depth += 1
            elif tok.type == TokenType.RPAREN:
                paren_depth -= 1
            parts.append(self._flat_value(tok))
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
            parts.append(self._flat_value(tok))
            self._advance()
        return RawSQL(sql=" ".join(parts).strip(), reason="bind argument")

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
            parts.append(self._flat_value(tok))
            self._advance()
            first = False
        return RawSQL(sql=" ".join(parts).strip(), reason="default value")

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
            parts.append(self._flat_value(tok))
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
            parts.append(self._flat_value(tok))
            self._advance()
            first = False
        return RawSQL(sql=" ".join(parts).strip(), reason="captured expression")

    def _parse_pg_sql_function_body(self) -> list[ASTNode]:
        """Parse a ``LANGUAGE sql`` body: a bare statement list, no
        BEGIN/DECLARE (the declare-section parser used to shred it into
        garbage declarations). The trailing SELECT/VALUES of a non-void
        function is the function result and becomes its RETURN."""
        stmts: list[ASTNode] = []
        guard = 0
        while not self._at_end():
            guard += 1
            if guard > 500:
                break
            tok = self._current()
            if tok.type == TokenType.UNKNOWN and tok.value == "$":
                break
            if not tok.is_keyword(
                "SELECT", "VALUES", "WITH", "INSERT", "UPDATE", "DELETE"
            ):
                break
            stmts.append(self._parse_embedded_dml())
        returns_result = self._pg_fn_return_type not in ("", "VOID", "TRIGGER")
        if returns_result and stmts:
            last = stmts[-1]
            if isinstance(last, EmbeddedDML) and last.sql.lstrip().upper().startswith(
                ("SELECT", "VALUES", "WITH")
            ):
                # The capture may run past the closing $$ and swallow the
                # header's tail attributes — strip them from the result.
                body_sql = re.sub(
                    r"(?is)(?:\s+(?:language\s+\w+|immutable|stable|volatile"
                    r"|strict|parallel\s+\w+|cost\s+\d+(?:\.\d+)?"
                    r"|rows\s+\d+))+\s*$",
                    "",
                    last.sql.strip(),
                )
                stmts[-1] = ReturnStatement(
                    value=RawSQL(sql=f"({body_sql})", reason="expression")
                )
        return stmts

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

            parts.append(self._flat_value(tok))
            prev_tok = tok
            self._advance()
            first = False

        sql = " ".join(parts).strip()
        return EmbeddedDML(sql=sql, dialect=self._dialect)

    _DML_START_KEYWORDS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"})
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

    def _plsql_collection_type_ahead(self) -> bool:
        """Whether the declaration section ahead defines a PL/SQL collection or
        record type (``TYPE name IS VARRAY/TABLE/RECORD/REF CURSOR``). Such a
        unit has no mechanical off-Oracle equivalent; parsing it shredded the
        declaration into garbage (``DECLARE IS VARRAY(13);``). Scans only up to
        the first top-level BEGIN (the executable body may mention TYPE in
        other roles)."""
        if self._is_tsql_source():
            return False
        offset = 0
        while True:
            tok = self._peek(offset)
            if tok.type == TokenType.EOF or tok.is_keyword("BEGIN"):
                return False
            if (
                tok.upper_value == "TYPE"
                and self._peek(offset + 1).type == TokenType.IDENTIFIER
                and self._peek(offset + 2).is_keyword("IS")
            ):
                return True
            offset += 1

    _TRANSPILABLE_PG_LANGUAGES = frozenset({"SQL", "PLPGSQL"})

    def _pg_non_sql_language_ahead(self) -> str | None:
        """The unit's ``LANGUAGE <name>`` when it is NOT transpilable
        (C, internal, plperl, …); None for sql/plpgsql or no clause."""
        if self._dialect != "postgresql":
            return None
        for i, tok in enumerate(self._tokens):
            if tok.is_keyword("LANGUAGE") and i + 1 < len(self._tokens):
                nxt = self._tokens[i + 1]
                name = nxt.value.strip("'").upper()
                if name and name not in self._TRANSPILABLE_PG_LANGUAGES:
                    return name
        return None

    def _whole_unit_raw(self, reason: str) -> ASTNode:
        """Capture the WHOLE unit verbatim as a RawSQL with *reason* (no
        warning here — the transformer decides same-dialect passthrough
        vs cross-dialect carrier)."""
        self._pos = 0
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
        return RawSQL(sql="".join(parts).strip(), reason=reason)

    def _parse_fallback(self) -> ASTNode:
        """When we can't parse, capture everything as RawSQL (a documented
        carrier) and register a warning so the loss is never silent. Keep a newline
        between tokens that came from different source lines, so a large construct
        is preserved as readable multi-line text instead of one enormous line that
        breaks editors and diffs.

        The capture always restarts at the unit's first token — a parse() call
        holds exactly one batch, and starting at the *current* position silently
        lost everything already consumed (the PIPELINED carrier dropped its
        whole CREATE FUNCTION header)."""
        self._pos = 0
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
