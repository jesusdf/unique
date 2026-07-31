# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import contextlib
import dataclasses
import decimal
import re
from collections.abc import Iterator
from typing import Any, cast

import sqlglot
import sqlglot.expressions as exp
from sqlglot import TokenType, transforms

from unique.core.ast_nodes import (
    Alias,
    ArrayLiteral,
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CaseExpression,
    CastExpression,
    ColumnDefinition,
    ColumnRef,
    CommentStatement,
    CreateTableStatement,
    CreateViewStatement,
    CTEDefinition,
    DataType,
    DeleteStatement,
    DropStatement,
    ExcludedColumn,
    ExpressionList,
    FunctionCall,
    GroupingElement,
    InsertStatement,
    JoinClause,
    JoinType,
    LimitClause,
    Literal,
    OnConflictClause,
    OrderByItem,
    OrderDirection,
    PassthroughSQL,
    PivotRelation,
    RawSQL,
    SelectStatement,
    SetOperationType,
    Star,
    SubqueryExpression,
    TableRef,
    UnaryOp,
    UnaryOperator,
    UnpivotRelation,
    UnsupportedInline,
    UpdateStatement,
    WindowFunction,
    WindowSpec,
)

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter._unread_args import dispatch_tracked
from unique.core.converter.harvest import _resolve_tsql_alias_type  # noqa: F401
from unique.core.converter.type_env import infer_column_types, tag_temporal_columns
from unique.core.sql_split import is_executable, split_leading_trivia

_INSERT_COLS_RE = re.compile(
    r"(?is)\b(INSERT\s+(?:IGNORE\s+)?INTO\s+`?(\w+)`?\s*\()([^)]*)(\))"
)


def _inline_named_windows(root: exp.Expression) -> None:
    """Substitute each ``OVER <name>`` reference with the spec from the SELECT's
    ``WINDOW <name> AS (…)`` clause, then drop the clause. The IR models no named
    window, so a reference would otherwise emit an empty ``OVER ()``."""
    for sel in root.find_all(exp.Select):
        windows = sel.args.get("windows")
        if not windows:
            continue
        defs = {w.this.name: w for w in windows if isinstance(w.this, exp.Identifier)}
        for ref in sel.find_all(exp.Window):
            # A definition node (its ``this`` is the name) is not a reference.
            if isinstance(ref.this, exp.Identifier):
                continue
            alias = ref.args.get("alias")
            if not isinstance(alias, exp.Identifier):
                continue
            spec = defs.get(alias.name)
            if spec is None:
                continue
            for key in ("partition_by", "order", "spec", "first"):
                if ref.args.get(key) is None and spec.args.get(key) is not None:
                    ref.set(key, spec.args[key].copy())
            ref.set("alias", None)
        sel.set("windows", None)


def _strip_insert_column_qualifiers(sql: str) -> str:
    """Drop redundant ``tbl.`` prefixes inside an INSERT's column list.

    The list region is an identifier list (no string literals can
    legally appear there), so the scoped substitution is safe."""

    def _fix(m: re.Match[str]) -> str:
        table = m.group(2)
        cols = re.sub(rf"(?i)\b{re.escape(table)}\s*\.\s*", "", m.group(3))
        return f"{m.group(1)}{cols}{m.group(4)}"

    return _INSERT_COLS_RE.sub(_fix, sql)


def _iter_sql_comments(text: str) -> Iterator[tuple[str, bool]]:
    """Yield ``(comment_body, is_own_line)`` for each comment in *text*.

    ``comment_body`` is the stripped comment content (no ``--`` or ``/* */``
    markers); ``is_own_line`` is True when only whitespace precedes the comment
    on its physical line. String literals are skipped so a ``--`` inside a
    string is not read as a comment. Used to recover standalone comments that
    sqlglot drops when it re-renders a passthrough statement (audit N14/B21):
    the ones already carried in the re-rendered SQL are filtered by the caller.
    """
    i, n = 0, len(text)
    line_has_code = False
    while i < n:
        ch = text[i]
        if ch == "\n":
            line_has_code = False
            i += 1
        elif ch in "'\"`":
            i += 1
            while i < n:
                if text[i] == ch:
                    if ch == "'" and i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            line_has_code = True
        elif ch == "-" and i + 1 < n and text[i + 1] == "-":
            j = text.find("\n", i)
            j = n if j == -1 else j
            yield text[i + 2 : j].strip(), not line_has_code
            i = j
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            body_end = n if end == -1 else end
            yield text[i + 2 : body_end].strip(), not line_has_code
            i = body_end if end == -1 else end + 2
            line_has_code = True
        else:
            if not ch.isspace():
                line_has_code = True
            i += 1


def parse_sql(sql: str, dialect: str) -> list[ASTNode]:
    """Parse SQL text using sqlglot and convert to IR nodes.

    Args:
        sql: Raw SQL text.
        dialect: Our dialect name ('tsql', 'oracle', 'postgresql', 'mysql').

    Returns:
        A list of IR ASTNode instances.
    """
    sg_dialect = sqlglot_dialect_name(dialect)
    # Comments are trivia (guardrail 3): the regex pre-recognitions below
    # must see the CODE, not a leading comment — a commented ALTER … SET
    # (storage) dodged the PG STORAGE branch. Split once and recurse on the
    # code; the trivia re-attaches as leading comment nodes.
    leading_trivia, code = split_leading_trivia(sql)
    if leading_trivia.strip() and code.strip():
        trivia_nodes: list[ASTNode] = [
            CommentStatement(
                text=line,
                style="line" if line.lstrip().startswith("--") else "block",
            )
            for line in leading_trivia.rstrip().splitlines()
            if line.strip()
        ]
        return [*trivia_nodes, *parse_sql(code, dialect)]

    # ``DROP TABLE a, b, c`` — sqlglot cannot parse the multi-object
    # form (it shredded the statement at the first comma; waves 236,
    # 239 extend it to FUNCTION/PROCEDURE/VIEW/SEQUENCE/etc.). Split
    # into one DROP per object: valid on every engine (Oracle has no
    # comma form at all), semantically identical.
    multi_drop = re.match(
        r"(?is)^\s*DROP\s+"
        r"(TABLE|VIEW|SEQUENCE|INDEX|FUNCTION|PROCEDURE|TYPE|DOMAIN)\s+"
        r"(IF\s+EXISTS\s+)?"
        r'([\w"`.\[\]]+(?:\s*,\s*[\w"`.\[\]]+)+)\s*(CASCADE|RESTRICT)?\s*;?\s*$',
        sql,
    )
    if multi_drop:
        obj = multi_drop.group(1).upper()
        if_exists = bool(multi_drop.group(2))
        tail = f" {multi_drop.group(4)}" if multi_drop.group(4) else ""
        out: list[ASTNode] = []
        for tbl in multi_drop.group(3).split(","):
            name = tbl.strip()
            ie = "IF EXISTS " if if_exists else ""
            out.extend(parse_sql(f"DROP {obj} {ie}{name}{tail};", dialect))
        return out
    # ``SAVEPOINT name`` mis-parses in sqlglot as an Alias expression
    # (``SAVEPOINT AS name`` shipped — invalid everywhere; wave 123).
    # Same spelling on PG/MySQL/Oracle; T-SQL re-emits SAVE TRANSACTION.
    sp = re.match(r'(?is)^\s*SAVEPOINT\s+([\w"`\[\]]+)\s*;?\s*$', sql)
    if sp and dialect in ("postgresql", "mysql", "oracle"):
        return [
            PassthroughSQL(
                sql=f"SAVEPOINT {sp.group(1)}",
                source_dialect=dialect,
                kind="SAVEPOINT",
            )
        ]
    # PG's ALTER COLUMN … SET STORAGE knob: sqlglot's own round-trip
    # INVENTS a ``DROP DEFAULT,`` before it (wave 132). Keep the original
    # text: verbatim on PG, carrier elsewhere (a storage internal).
    storage = re.match(
        r'(?is)^\s*(ALTER\s+TABLE\s+[\w".]+\s+(?:ALTER\s+COLUMN\s+[\w"]+'
        r"\s+SET\s+STORAGE\s+\w+|SET\s*\(.+?\)))\s*;?\s*$",
        sql,
    )
    if storage and dialect == "postgresql":
        return [
            PassthroughSQL(
                sql=storage.group(1),
                source_dialect=dialect,
                kind="PG STORAGE",
            )
        ]
    # ``CREATE VIEW … WITH [CASCADED|LOCAL] CHECK OPTION``: sqlglot cannot
    # parse the trailing clause on any dialect (it degrades the whole CREATE to
    # a Command carrier, or drops it silently on Oracle). It is portable — all
    # four engines spell it ``WITH CHECK OPTION`` (MySQL/PG also accept the
    # CASCADED/LOCAL scope) — so strip it, re-parse the view, and model the
    # option on the IR for the emitter to re-attach per target.
    if "CHECK" in sql.upper():
        check_opt = re.match(
            r"(?is)^\s*(CREATE\b.+?\bVIEW\b.+?)\s+WITH\s+"
            r"(?:(CASCADED|LOCAL)\s+)?CHECK\s+OPTION\s*;?\s*$",
            sql,
        )
        if check_opt:
            scope = check_opt.group(2)
            opt = f"{scope.upper()} CHECK OPTION" if scope else "CHECK OPTION"
            return [
                (
                    dataclasses.replace(n, check_option=opt)
                    if isinstance(n, CreateViewStatement)
                    else n
                )
                for n in parse_sql(check_opt.group(1).strip() + ";", dialect)
            ]
    if dialect == "mysql":
        # MySQL's ``INSERT INTO t SET a = 1, b = 2`` form: sqlglot cannot
        # parse it at all, and the embedded-routine fallback DROPPED the
        # SET clause (``INSERT INTO t3;`` — silent loss, wave 168). Same
        # story for ``REPLACE t SET a = 1`` (delete-then-insert upsert).
        # Rewrite to the universal column-list VALUES form.
        original_sql = sql
        ins = re.match(
            r"(?is)^\s*(INSERT\s+(?:IGNORE\s+)?INTO|REPLACE\s+(?:INTO\s+)?)"
            r'\s*([\w."`]+)\s+SET\s+(.+?)\s*;?\s*$',
            sql,
        )
        if ins:
            from unique.core.sql_split import split_top_level_commas

            cols: list[str] = []
            vals: list[str] = []
            ok = True
            for pair in split_top_level_commas(ins.group(3)):
                m2 = re.match(r"(?s)^\s*([\w`\"]+)\s*:?=\s*(.+?)\s*$", pair)
                if not m2:
                    ok = False
                    break
                cols.append(m2.group(1).strip('`"'))
                vals.append(m2.group(2))
            if ok and cols:
                rewritten = (
                    f"INSERT INTO {ins.group(2)} ({', '.join(cols)}) "
                    f"VALUES ({', '.join(vals)})"
                )
                if ins.group(1).upper().startswith("REPLACE"):
                    # sqlglot's MySQL reader has no REPLACE-statement parser
                    # at all — it swallows any ``REPLACE ...`` into an opaque
                    # Command node (a non-fatal fallback, so keeping the verb
                    # as ``REPLACE`` here would still fail below). Parse the
                    # equivalent INSERT text structurally and tag the result
                    # as a REPLACE so each target's emitter decides: MySQL
                    # spells it back as REPLACE INTO, every other target has
                    # no equivalent (guardrail 7 — never let it fall through
                    # as a silent plain INSERT).
                    return [
                        (
                            dataclasses.replace(
                                n,
                                is_replace=True,
                                source_text=original_sql.strip().rstrip(";"),
                            )
                            if isinstance(n, InsertStatement)
                            else n
                        )
                        for n in parse_sql(rewritten + ";", dialect)
                    ]
                sql = rewritten
        else:
            replace_rest = re.match(
                r"(?is)^\s*REPLACE\s+"
                r"(?:(?:LOW_PRIORITY|DELAYED)\s+)?"
                r"(?:INTO\s+)?(.+)$",
                sql,
            )
            if replace_rest:
                # ``REPLACE [INTO] t [(cols)] VALUES (...)`` / ``... SELECT
                # ...`` — syntactically identical to INSERT past the table
                # name, but hits the same unparseable-verb wall as the SET
                # form above. Swap the verb and parse the equivalent INSERT
                # text structurally, then tag the result as a REPLACE.
                rewritten = f"INSERT INTO {replace_rest.group(1)}"
                return [
                    (
                        dataclasses.replace(
                            n,
                            is_replace=True,
                            source_text=original_sql.strip().rstrip(";"),
                        )
                        if isinstance(n, InsertStatement)
                        else n
                    )
                    for n in parse_sql(rewritten, dialect)
                ]
    if dialect == "postgresql":
        # PG's ``SET TRANSACTION [ISOLATION LEVEL <lvl>] [READ ONLY|READ
        # WRITE]``: sqlglot parses the bare access-mode form as ``exp.Set``
        # and the combined form (with ISOLATION LEVEL) as an opaque
        # ``exp.Command`` — neither shape carries a usable per-target
        # spelling, and the batch classifier now routes this statement class
        # here instead of the SET-option comment-out fallback (N7/B8). Model
        # it as a passthrough carrying the ORIGINAL text so the emitter can
        # apply the per-target access-mode mapping without re-parsing a
        # mangled tree.
        txn_mode = re.match(
            r"(?is)^\s*SET\s+TRANSACTION\s+"
            r"(?=.*\b(?:ISOLATION\s+LEVEL|READ\s+(?:ONLY|WRITE))\b)",
            sql,
        )
        if txn_mode:
            return [
                PassthroughSQL(
                    sql=sql.strip().rstrip(";"),
                    source_dialect=dialect,
                    kind="SET TRANSACTION MODE",
                )
            ]
        # PG 14's recursive-CTE ordering clauses (``) SEARCH DEPTH|BREADTH
        # FIRST BY … SET col`` / ``) CYCLE … SET col``): sqlglot cannot
        # parse them and the fallback SHREDDED the statement into
        # fragments (46x in the pg→mysql residue — wave 191). Verbatim on
        # PG; a documented carrier elsewhere.
        if re.search(
            r"(?is)\)\s*(SEARCH\s+(?:DEPTH|BREADTH)\s+FIRST\s+BY|CYCLE\s+)",
            sql,
        ) and re.search(r"(?is)\bWITH\s+RECURSIVE\b", sql):
            return [
                PassthroughSQL(
                    sql=sql.rstrip().rstrip(";"),
                    source_dialect=dialect,
                    kind="PG SEARCH CTE",
                )
            ]
        # PG's ``TABLE name`` shorthand IS ``SELECT * FROM name``; sqlglot
        # mis-parses it into an aliased identifier (silent mangle). Leading
        # line comments are trivia and must not defeat the match (wave 131).
        sql = re.sub(
            r'(?is)^((?:\s*--[^\n]*\n)*\s*)TABLE\s+([\w."]+)(\s*;?\s*)$',
            r"\1SELECT * FROM \2\3",
            sql,
        )
    if dialect == "postgresql" and re.search(r":'\w+'|:\"\w+\"", sql):
        from unique.core.output_gate import scrub

        # scrub() replaces string contents with a placeholder, so on
        # scrubbed text the signature is a colon directly before a string
        # start (a real ``:'var'`` survives as ``:'…'`` while a ``:'`` that
        # sat *inside* a string is collapsed away; a PG cast is ``::type`` —
        # excluded by the lookbehind).
        if re.search(r"(?<!:):\s*'", scrub(sql)):
            # psql client-side variable substitution (:'var') is never
            # server SQL — and sqlglot's COPY-parameter parser loops
            # unboundedly on it until MemoryError (30 bytes of input
            # exhausted the host running the PG regression corpus).
            return [
                RawSQL(
                    sql=sql,
                    reason="psql client-side variable substitution (:'var')",
                )
            ]
    try:
        # RAISE, not WARN: a partial tree from a lenient parse silently drops
        # tokens — a real-corpus INSERT with a table-qualified column in its
        # column list shipped as ``INSERT … DEFAULT VALUES`` (columns
        # truncated, the guarded SELECT gone). A statement sqlglot cannot
        # fully parse becomes an honest RawSQL carrier instead.
        parsed = sqlglot.parse(
            sql, read=sg_dialect, error_level=sqlglot.ErrorLevel.RAISE
        )
    except Exception as e:
        # Real Oracle dumps carry ``SYSDATE()`` — empty parens, invalid even
        # on Oracle (a client code generator emitted it) — which breaks the
        # parse (and the WARN fallback would mangle it into ``… AS ()``).
        # Retry once with the niladic spelling normalized; doing this only
        # AFTER a failure means statements whose string literals mention
        # SYSDATE() are never touched (they parse fine the first time).
        if dialect == "oracle":
            normalized = re.sub(r"(?i)\b(SYSDATE|SYSTIMESTAMP)\s*\(\s*\)", r"\1", sql)
            if normalized != sql:
                with contextlib.suppress(Exception):
                    return parse_sql(normalized, dialect)
        if dialect == "mysql":
            # MySQL allows table-qualified INSERT column lists
            # (INSERT INTO t (t.a, t.b) …) which sqlglot cannot parse;
            # the qualifier is redundant by definition (the columns
            # belong to the INSERT's table). Same retry-after-failure
            # pattern as the Oracle SYSDATE() normalization.
            normalized = _strip_insert_column_qualifiers(sql)
            if normalized != sql:
                with contextlib.suppress(Exception):
                    return parse_sql(normalized, dialect)
            # DELETE/UPDATE IGNORE: sqlglot cannot parse the modifier and
            # the whole batch would carrier (gluing innocents). The
            # error-skipping semantics have no cross-engine form anyway.
            normalized = re.sub(r"(?i)\b(DELETE|UPDATE)\s+IGNORE\b", r"\1", sql)
            if normalized != sql:
                with contextlib.suppress(Exception):
                    return parse_sql(normalized, dialect)
        if IR_EMBEDDED.get():
            # Mid-transform probe from the procedural engine's IR path
            # (variables/args already target-spelled, e.g. an EXEC lowered to
            # ``proc a => 1`` before its parens): a failure here is expected
            # and handled — the caller falls back to its own emitters. At
            # WARNING this spammed one false alarm per EXEC call in a real
            # migration dump (user report 2026-07-29), burying real warnings.
            logger.debug("sqlglot parse error (IR probe): %s", e)
        else:
            logger.warning("sqlglot parse error: %s", e)
        return [RawSQL(sql=sql, reason=str(e))]

    nodes: list[ASTNode] = []
    # Original batch text for degrade carriers: slice the batch into
    # per-statement ORIGINAL texts (via the tokenizer — a ``;`` inside a
    # string/comment must not cut) and attach each to its converted node,
    # so a "statement preserved as a comment" carrier can quote the
    # ORIGINAL, never a re-render of the mid-transform tree (audit
    # 2026-07-24 N12). When the slices cannot be aligned one-to-one with
    # the parsed statements, nodes keep the re-render fallback.
    statement_count = sum(
        1 for e in parsed if e is not None and not isinstance(e, exp.Semicolon)
    )
    source_texts = (
        _statement_source_texts(sql, sg_dialect, statement_count)
        if statement_count
        else None
    )
    stmt_idx = 0
    for expression in parsed:
        # An empty statement — a stray/leading ``;`` (e.g. the mandatory one in
        # T-SQL's ``;WITH``). sqlglot yields None for it, or an exp.Semicolon when a
        # comment precedes it; both are no-ops, not an "unhandled" construct.
        if expression is None or isinstance(expression, exp.Semicolon):
            continue
        original_stmt = source_texts[stmt_idx] if source_texts else None
        stmt_idx += 1
        # Preserve the statement's leading comments (sqlglot attaches them to the
        # expression); our IR conversion would otherwise drop them. Re-emit them
        # as CommentStatements just before the statement, and clear them so a
        # PassthroughSQL ``.sql()`` doesn't also render them.
        emitted_comments: set[str] = set()
        leading = getattr(expression, "comments", None)
        if leading:
            for raw in leading:
                text = (raw or "").strip()
                emitted_comments.add(text)
                if "\n" in text:
                    nodes.append(CommentStatement(text=f"/* {text} */", style="block"))
                else:
                    nodes.append(
                        CommentStatement(
                            text=f"-- {text}" if text else "--", style="line"
                        )
                    )
            expression.comments = None
        # Oracle (+) join marks: rewrite into explicit LEFT/RIGHT OUTER JOINs
        # with ON conditions before converting. sqlglot drops the mark on
        # emit (turning an outer join into an inner one, silently), so the
        # rewrite must happen at the tree level (audit 2026-07-02, S1-2).
        if dialect == "oracle" and any(
            c.args.get("join_mark") for c in expression.find_all(exp.Column)
        ):
            expression = transforms.eliminate_join_marks(expression)
            # sqlglot 30.14's eliminate_join_marks re-adds an ALIASED preserved
            # table as a spurious bare CROSS JOIN: its "preserve other joins"
            # loop compares each join's alias-or-name against the new FROM's
            # table NAME (not its alias), so ``tb b`` (alias b, name tb) is kept
            # AND duplicated -> "table name b specified more than once". Drop any
            # bare join whose alias-or-name repeats one already in scope (a
            # duplicate alias is always invalid SQL, so this is safe).
            _dedup_duplicate_cross_joins(expression)  # type: ignore[arg-type]
        # T-SQL "+" on strings is concatenation; rewrite it to "||" so it maps
        # to the target's concat operator (sqlglot keeps it as arithmetic "+").
        # Oracle/PostgreSQL sources get the same charity: their "+" over a
        # recognizable string is malformed source whose intent is concat (the
        # text path's stance). MySQL is excluded — its "+" is numeric by
        # definition, string operands included.
        if dialect in ("tsql", "oracle", "postgresql"):
            expression = _rewrite_tsql_string_concat(
                expression  # type: ignore[arg-type]
            )
        # Inline a named WINDOW clause (``… OVER w … WINDOW w AS (…)``): the IR
        # has no named-window concept, so an un-inlined ``OVER w`` reference loses
        # its spec and emits ``OVER ()`` (silent loss / invalid on engines with a
        # mandatory ORDER BY).
        _inline_named_windows(expression)  # type: ignore[arg-type]
        if (
            isinstance(expression, exp.Select)
            and isinstance(expression.args.get("into"), exp.Into)
            and expression.args["into"].find(exp.Parameter) is not None
            and len(parsed) == 1
        ):
            # Keep the ORIGINAL text — re-rendering the mangled parse
            # would preserve garbage in the carrier.
            nodes.append(
                PassthroughSQL(
                    sql=sql.strip().rstrip(";"),
                    source_dialect=dialect,
                    kind="SELECT INTO VAR",
                )
            )
            continue
        node = convert_expression(expression, dialect)  # type: ignore[arg-type]
        if original_stmt is not None:
            node = dataclasses.replace(node, source_text=original_stmt)
        # A source-rendering node (PassthroughSQL/RawSQL/…) re-emits the
        # original expression verbatim, comments included; an IR-modelled node
        # renders no SQL string here (``rendered`` empty). sqlglot drops
        # standalone mid-statement comments when it re-renders — recover those
        # the render lost, placed above the statement, so nothing is dropped
        # and nothing already carried inline is duplicated (audit N14/B21).
        rendered = getattr(node, "sql", "") or getattr(node, "source_sql", "") or ""
        if rendered and original_stmt:
            for body, own_line in _iter_sql_comments(original_stmt):
                if (
                    own_line
                    and body
                    and body not in rendered
                    and body not in emitted_comments
                ):
                    emitted_comments.add(body)
                    nodes.append(CommentStatement(text=f"-- {body}", style="line"))
        nodes.append(node)
        # Trailing / inline comments attach to child nodes, not the statement;
        # collect them so they aren't lost (re-emitted after the statement —
        # position may shift slightly, but nothing is dropped). A comment the
        # source-rendering ``rendered`` already carries is skipped so it is not
        # emitted twice (audit N14/B21).
        for sub in expression.walk():
            if sub is expression or not sub.comments:
                continue
            for raw in sub.comments:
                text = (raw or "").strip()
                if text and text not in rendered:
                    nodes.append(CommentStatement(text=f"-- {text}", style="line"))

    return nodes


def _styled_convert_is_modeled(c: exp.Convert) -> bool:
    """Whether a styled CONVERT converts structurally (known date style, or
    the hash-stringify wrapper whose target functions already return hex)."""
    # A BINARY/VARBINARY target is a byte reinterpretation, never a date
    # conversion — style 0 there is the default binary style, not the date
    # format mapping (it used to misparse to TO_TIMESTAMP).
    _type = c.this if isinstance(c.this, exp.DataType) else c.expression
    if isinstance(_type, exp.DataType) and _type.this in (
        exp.DataType.Type.VARBINARY,
        exp.DataType.Type.BINARY,
    ):
        return False
    style = str(c.args["style"].name).strip("'")
    if style in ("1", "2"):
        inner = c.args.get("expression")
        if inner is not None and (isinstance(inner, exp.SHA2) or inner.find(exp.SHA2)):
            return True
    from sqlglot.dialects.tsql import TSQL

    return style in TSQL.CONVERT_FORMAT_MAPPING


def _convert_styled_convert(expr: exp.Convert) -> FunctionCall | None:
    """Model CONVERT(type, value, style) when the style is known."""
    if not _styled_convert_is_modeled(expr):
        return None
    type_expr, value_expr = expr.this, expr.expression
    if not isinstance(type_expr, exp.DataType) and isinstance(value_expr, exp.DataType):
        type_expr, value_expr = value_expr, type_expr
    if not isinstance(type_expr, exp.DataType) or value_expr is None:
        return None
    style = str(expr.args["style"].name).strip("'")
    return FunctionCall(
        name="CONVERT",
        args=(
            RawSQL(sql=type_expr.sql(dialect="tsql"), reason="CONVERT type"),
            convert_expression(value_expr),
            Literal(value=int(style), dtype="integer"),
        ),
    )


def convert_expression(expr: exp.Expression, source_dialect: str = "tsql") -> ASTNode:
    """Convert a single sqlglot expression to an IR node.

    Dispatches based on the sqlglot expression type. ``source_dialect`` is
    used to re-transpile passthrough statements (ALTER, CREATE INDEX, ...)
    that sqlglot handles directly but we do not model structurally.
    """
    # Statements sqlglot transpiles well but we don't model in IR: keep them
    # as PassthroughSQL so the emitter can re-transpile to the target.
    if isinstance(expr, (exp.Alter, exp.Create)) and _is_passthrough_create(expr):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind=_passthrough_kind(expr),
        )
    if isinstance(expr, exp.Alter):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="ALTER",
        )
    if isinstance(expr, exp.Use):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="USE",
        )
    # A server-side SET statement (Oracle/PG SET TRANSACTION, PG SET
    # search_path, …): sqlglot transpiles it directly. Client directives
    # (SQL*Plus SET, T-SQL session options) never reach here — the batch
    # classifier routes them to the SET_OPTION path.
    # T-SQL ``SET IDENTITY_INSERT <table> ON|OFF`` is a session directive that
    # permits an explicit value in an identity column. It has no cross-engine
    # equivalent (the targets accept an explicit value into a SERIAL / BY
    # DEFAULT identity / AUTO_INCREMENT column directly), and sqlglot parses the
    # two forms incoherently — ON as an opaque Command ("Unhandled"), OFF as an
    # invalid ``SET IDENTITY_INSERT = t AS OFF``. Drop the whole bracket with a
    # documented carrier (auto-warned) rather than emit the mangled/Unhandled
    # statement.
    if (
        source_dialect == "tsql"
        and isinstance(expr, (exp.Command, exp.Set))
        and re.search(r"(?i)\bIDENTITY_INSERT\b", expr.sql(dialect="tsql"))
    ):
        _ii = re.search(
            r"(?i)IDENTITY_INSERT\s+(?:=\s*)?(?P<tbl>[\[\]\w.\"]+).*?\b(?P<st>ON|OFF)\b",
            expr.sql(dialect="tsql"),
        )
        _ii_tbl = _ii.group("tbl") if _ii else ""
        _ii_st = _ii.group("st").upper() if _ii else ""
        return CommentStatement(
            text=(
                f"-- UNIQUE-1002: SET IDENTITY_INSERT {_ii_tbl} {_ii_st} is a T-SQL "
                "session directive with no cross-engine equivalent; dropped (the "
                "target accepts an explicit value into an identity/serial/"
                "auto_increment column) (docs/03-unsupported.md)"
            ),
            style="line",
        )
    if isinstance(expr, exp.Set):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="SET",
        )
    if isinstance(expr, exp.Merge):
        # A leading CTE feeding the MERGE (``WITH src AS (…) MERGE … USING src``)
        # has no portable placement: Oracle forbids WITH before MERGE
        # (ORA-00928) and the MySQL upsert rewrite drops the CTE (undefined
        # ``src``). Inline each single-referenced CTE into the USING subquery so
        # the source travels with the statement on every target.
        _merge = _inline_merge_cte(expr)
        return PassthroughSQL(
            sql=_merge.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="MERGE",
        )
    # A T-SQL CLR static call — ``geometry::Point(…).STDistance(…)``, a
    # hierarchyid or a UDT method — parses as a ScopeResolution (the ``::``
    # static-method operator). No other engine has it, and sqlglot silently
    # flattens it (dropping the ``::type`` half), so surface it as a documented
    # degrade rather than a mangled, invalid column. Matched only at the column
    # expression's own shape so it never swallows a surrounding statement.
    if isinstance(expr, exp.ScopeResolution) or (
        isinstance(expr, exp.Dot) and isinstance(expr.this, exp.ScopeResolution)
    ):
        return UnsupportedInline(
            source_sql=" ".join(
                expr.sql(dialect=sqlglot_dialect_name(source_dialect)).split()
            ),
            detail=(
                "T-SQL spatial/CLR type method (::) has no cross-engine equivalent"
            ),
        )
    # ``x AT TIME ZONE 'zone'`` is not portable: Oracle/MySQL have no such
    # operator (ORA-00902), and the PG<->T-SQL semantics plus the session-tz
    # dependent display differ, so the value can't be guaranteed equal. Keep it
    # verbatim on its own dialect and degrade (carrier + warning) elsewhere.
    if isinstance(expr, exp.AtTimeZone):
        return UnsupportedInline(
            source_sql=" ".join(
                expr.sql(dialect=sqlglot_dialect_name(source_dialect)).split()
            ),
            detail=(
                "AT TIME ZONE is not portable (Oracle/MySQL have no such operator; "
                "session-tz-dependent display differs on PG/T-SQL)"
            ),
        )
    # INSERT/UPDATE/DELETE with a RETURNING clause: our DML IR drops it, so
    # pass through to sqlglot (which maps RETURNING <-> OUTPUT) to preserve
    # the returned columns.
    if isinstance(expr, (exp.Insert, exp.Update, exp.Delete)) and expr.args.get(
        "returning"
    ):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="RETURNING",
        )
    # UPDATE/DELETE with a leading CTE: the IR models neither's ``with`` arg
    # (the clause silently vanished), so pass through to sqlglot whole.
    if isinstance(expr, (exp.Update, exp.Delete)) and (
        expr.args.get("with") or expr.args.get("with_")
    ):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="CTE DML",
        )
    # A data-modifying CTE under a SELECT — ``WITH ins AS (INSERT …
    # RETURNING) SELECT …`` (PG-only): the CTE converter would shred the
    # DML body into a bare SELECT skeleton (wave 114). Pass through whole;
    # the emitter keeps it on PG and carriers it elsewhere.
    if isinstance(expr, exp.Select):
        with_arg = expr.args.get("with") or expr.args.get("with_")
        if with_arg is not None and any(
            isinstance(cte.this, (exp.Insert, exp.Update, exp.Delete))
            for cte in with_arg.expressions
        ):
            return PassthroughSQL(
                sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
                source_dialect=source_dialect,
                kind="CTE DML",
            )
    # A parenthesized join tree in FROM (the Access-style
    # ``FROM ((a JOIN b ON ...) JOIN c ON ...)``) parses as nested Subquery
    # nodes that are not derived tables; the IR would silently lose the whole
    # FROM clause, so hand the statement to sqlglot whole.
    if isinstance(expr, exp.Select):
        _from = expr.args.get("from_") or expr.args.get("from")
        if (
            _from is not None
            and isinstance(_from.this, exp.Subquery)
            and not isinstance(_from.this.this, (exp.Select, exp.SetOperation))
        ):
            # The single-level group — Subquery wrapping a Table whose
            # joins have plain operands — converts via the hoist in
            # _convert_select; only deeper nesting stays passthrough.
            _inner = _from.this.this
            _single_level = isinstance(_inner, exp.Table) and all(
                not (
                    isinstance(j.this, exp.Subquery)
                    and not isinstance(j.this.this, (exp.Select, exp.SetOperation))
                )
                for j in (_inner.args.get("joins") or [])
            )
            if not _single_level:
                return PassthroughSQL(
                    sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
                    source_dialect=source_dialect,
                    kind="PAREN JOIN",
                )
    # Oracle hierarchical queries (START WITH / CONNECT BY) have no faithful
    # automatic rewrite; emit a documented comment instead of silently
    # dropping the clause (which would change results).
    if isinstance(expr, exp.Select) and expr.args.get("connect") is not None:
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="CONNECT BY",
        )
    # T-SQL "SELECT ... INTO <table>" creates a new table. sqlglot maps it
    # correctly per dialect (CREATE TABLE AS for MySQL, SELECT INTO for
    # PG/Oracle); our SELECT converter would drop the INTO, so pass through.
    if isinstance(expr, exp.Select) and isinstance(expr.args.get("into"), exp.Into):
        if expr.args["into"].find(exp.Parameter) is not None:
            # MySQL ``SELECT … INTO @var[, @var2]`` captures into session
            # variables; sqlglot mangles the multi-var parse (extra vars
            # absorb into the select list), so no faithful rebuild exists.
            # parse_sql intercepts the single-statement case with the
            # ORIGINAL text; this fallback covers embedded occurrences.
            return PassthroughSQL(
                sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
                source_dialect=source_dialect,
                kind="SELECT INTO VAR",
            )
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="SELECT INTO",
        )
    # SELECT clauses our IR does not model (row locks like FOR UPDATE,
    # QUALIFY) would otherwise be dropped silently; pass them through so
    # sqlglot can translate them and the semantics are preserved.
    if isinstance(expr, exp.Select) and (
        expr.args.get("locks") or expr.args.get("qualify") is not None
    ):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="SELECT",
        )
    # T-SQL CONVERT(type, value, style): known date-style codes and the
    # hash-stringify wrapper are modeled (FunctionCall CONVERT with the style
    # argument — see _convert_styled_convert); a style outside the known
    # table still passes the whole statement through.
    # A BINARY/VARBINARY conversion with style 0 IS the default byte
    # reinterpretation — drop the redundant style so it models as a plain
    # cast instead of dragging the whole statement into the passthrough.
    if isinstance(expr, exp.Select):
        for _c in expr.find_all(exp.Convert):
            if _c.args.get("style") is None:
                continue
            _ct = _c.this if isinstance(_c.this, exp.DataType) else _c.expression
            if not isinstance(_ct, exp.DataType):
                continue
            _style_val = str(_c.args["style"].name).strip("'")
            # A BINARY/VARBINARY conversion with style 0 is the default byte
            # reinterpretation, and a NUMERIC target ignores the style entirely
            # (the T-SQL style code only shapes date/time and the numeric->string
            # direction — CONVERT(INT, '26', 0) is just a cast). Drop the
            # redundant style so it models as a plain CAST instead of being
            # mis-read as a date parse (TO_TIMESTAMP) or dragged into passthrough.
            _is_binary = _ct.this in (
                exp.DataType.Type.VARBINARY,
                exp.DataType.Type.BINARY,
            )
            if (
                _is_binary and _style_val == "0"
            ) or _ct.this in exp.DataType.NUMERIC_TYPES:
                _c.set("style", None)
    if isinstance(expr, exp.Select) and any(
        not _styled_convert_is_modeled(c)
        for c in expr.find_all(exp.Convert)
        if c.args.get("style") is not None
    ):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="SELECT",
        )
    # CREATE TABLE is modeled in IR but its table-level constraints are kept
    # as passthrough fragments, which need the source dialect.
    if (
        isinstance(expr, exp.Create)
        and (expr.args.get("kind") or "").upper() in ("TABLE", "")
        and isinstance(expr.this, exp.Schema)
    ):
        return _convert_create_table(expr, source_dialect)
    # BEGIN TRANSACTION: valid on T-SQL/PG/MySQL (sqlglot renders the target's
    # form); Oracle has no explicit statement (transactions are implicit), so the
    # emitter degrades it to a documented carrier rather than shipping a bare —
    # and invalid — ``BEGIN``.
    if isinstance(expr, exp.Transaction):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="BEGIN TRANSACTION",
        )
    # ``SAVEPOINT name`` inside a batch is parsed by sqlglot as an Alias
    # (``SAVEPOINT AS name``), which every engine rejects, and a re-transpile
    # re-introduces it — model it as a SAVEPOINT passthrough (the emit spells
    # T-SQL's SAVE TRANSACTION). The standalone-parse path handles this too.
    if (
        isinstance(expr, exp.Alias)
        and isinstance(expr.this, exp.Column)
        and expr.this.name.upper() == "SAVEPOINT"
        and expr.this.table == ""
    ):
        return PassthroughSQL(
            sql=f"SAVEPOINT {expr.alias}",
            source_dialect=source_dialect,
            kind="SAVEPOINT",
        )
    # ``ROLLBACK TO SAVEPOINT name``: sqlglot drops the savepoint name when it
    # re-transpiles to T-SQL (a bare ROLLBACK TRANSACTION undoes the whole
    # transaction, not just to the savepoint). Model it so the name survives.
    if isinstance(expr, exp.Rollback) and expr.args.get("savepoint") is not None:
        _sp = expr.args["savepoint"]
        _sp_name = _sp.name if hasattr(_sp, "name") else str(_sp)
        return PassthroughSQL(
            sql=f"ROLLBACK TO SAVEPOINT {_sp_name}",
            source_dialect=source_dialect,
            kind="ROLLBACK_SAVEPOINT",
        )
    # Transaction/DDL control (COMMIT / ROLLBACK / TRUNCATE) is valid on every
    # target — a data-migration dump is full of these — so re-transpile it via
    # the passthrough path instead of degrading each to an "Unhandled" carrier.
    if isinstance(expr, (exp.Commit, exp.Rollback, exp.TruncateTable)):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="statement",
        )
    # Structural conversion — the only path where a construct can be silently
    # dropped by an unread sqlglot arg. Track args reads and report residue
    # (guardrail 7 / brief B2); the passthrough branches above re-render the
    # whole node, so nothing can fall on the floor there.
    return dispatch_tracked(expr, _convert_expression_impl)


def _is_passthrough_create(expr: exp.Expression) -> bool:
    """Whether a CREATE should be passed through to sqlglot unchanged.

    Tables and views are modeled in IR; indexes (including T-SQL
    CLUSTERED/NONCLUSTERED), sequences, and schemas are not, so they
    round-trip through sqlglot.
    """
    if not isinstance(expr, exp.Create):
        return False
    kind = (expr.args.get("kind") or "").upper()
    return "INDEX" in kind or kind in ("SEQUENCE", "SCHEMA")


def _passthrough_kind(expr: exp.Expression) -> str:
    if isinstance(expr, exp.Create):
        kind = (expr.args.get("kind") or "").upper()
        # Normalize CLUSTERED/NONCLUSTERED index variants to a common kind.
        if "INDEX" in kind:
            return "CREATE INDEX"
        return "CREATE " + kind
    return type(expr).__name__.upper()


def _statement_source_texts(sql: str, sg_dialect: str, count: int) -> list[str] | None:
    """Per-statement slices of the ORIGINAL batch text.

    Aligned one-to-one with the batch's *count* parsed statements. Boundaries
    come from the tokenizer's top-level ``;`` tokens (never a text split — a
    ``;`` inside a string or comment must not cut). Returns None when the
    slices cannot be aligned unambiguously; callers then keep their re-render
    fallback.
    """
    if count == 1 and ";" not in sql:
        return [sql.strip()]
    try:
        tokens = sqlglot.tokenize(sql, read=sg_dialect)
    except Exception:
        return None
    pieces: list[str] = []
    start = 0
    for tok in tokens:
        if tok.token_type == TokenType.SEMICOLON:
            pieces.append(sql[start : tok.start])
            start = tok.end + 1
    pieces.append(sql[start:])
    statements = [p.strip() for p in pieces if is_executable(p)]
    return statements if len(statements) == count else None


def _source_sql(expr: exp.Expr) -> str:
    """Render a sqlglot expression in the transpile's SOURCE dialect.

    RawSQL fallbacks must preserve the source spelling: the generic
    renderer re-bases PG array subscripts (``arr[2]`` -> ``arr[1]``) and
    loses other dialect-specific forms.
    """
    source = SOURCE_DIALECT.get()
    try:
        if source and not IR_EMBEDDED.get():
            return expr.sql(dialect=sqlglot_dialect_name(source))
        return expr.sql()
    except Exception:
        return str(expr)


def _convert_expression_impl(expr: exp.Expression) -> ASTNode:
    """Convert a single sqlglot expression to an IR node.

    Dispatches based on the sqlglot expression type.
    """
    if isinstance(expr, exp.Select):
        return _convert_select(expr)
    if isinstance(expr, exp.Insert):
        return _convert_insert(expr)
    if isinstance(expr, exp.Update):
        return _convert_update(expr)
    if isinstance(expr, exp.Delete):
        return _convert_delete(expr)
    if isinstance(expr, exp.Create):
        return _convert_create(expr)
    if isinstance(expr, exp.Drop):
        return _convert_drop(expr)
    if isinstance(expr, exp.SetOperation):
        return _convert_union(expr)
    if isinstance(expr, exp.Column):
        seq_ref = _convert_sequence_ref(expr)
        if seq_ref is not None:
            return seq_ref
        user_fn = _convert_oracle_user_pseudo(expr)
        if user_fn is not None:
            return user_fn
        money = _tsql_money_literal_from_column(expr)
        if money is not None:
            return money
        return _convert_column(expr)
    if isinstance(expr, exp.Table):
        return _convert_table(expr)
    if isinstance(expr, exp.Literal):
        return _convert_literal(expr)
    if isinstance(expr, exp.Boolean):
        # TRUE/FALSE literals; T-SQL and Oracle need 1/0 at emit time
        # (audit 2026-07-02, S1-9).
        return Literal(value=bool(expr.this), dtype="boolean")
    if isinstance(expr, exp.Star):
        return Star()
    if isinstance(expr, exp.Alias):
        return _convert_alias(expr)
    # ``> ALL (VALUES (1),(2))`` parses as an Anonymous ALL/ANY call over a
    # Values node (not exp.All): rewrite the single-column VALUES to a
    # portable UNION ALL subquery (bare VALUES is not a subquery on
    # MySQL/Oracle/T-SQL).
    if (
        isinstance(expr, exp.Anonymous)
        and str(expr.this).upper() in ("ALL", "ANY", "SOME")
        and len(expr.expressions) == 1
        and isinstance(expr.expressions[0], exp.Values)
    ):
        _tuples = expr.expressions[0].expressions
        if _tuples and all(
            isinstance(tp, exp.Tuple) and len(tp.expressions) == 1 for tp in _tuples
        ):
            _sel: exp.Select | exp.Union = exp.Select(
                expressions=[_tuples[0].expressions[0].copy()]
            )
            for _tp in _tuples[1:]:
                _sel = exp.Union(
                    this=_sel,
                    expression=exp.Select(expressions=[_tp.expressions[0].copy()]),
                    distinct=False,
                )
            _kw = "ALL" if str(expr.this).upper() == "ALL" else "ANY"
            return SubqueryExpression(query=_convert_select(_sel), quantifier=_kw)
    if isinstance(expr, exp.Anonymous):
        return _convert_function(expr)
    if isinstance(expr, exp.Filter) and isinstance(expr.this, exp.WithinGroup):
        # FILTER over an ordered-set aggregate: the generic path shredded
        # it into a fake WITHINGROUP(CASE …) call (wave 133). Preserve the
        # source spelling; the array/within-group gate handles targets.
        return RawSQL(
            sql=_source_sql(expr),
            reason="Unhandled expression type: WithinGroup(Filter)",
        )
    if isinstance(expr, exp.Array):
        # ARRAY[…] / ARRAY(SELECT …): a real node, never a FunctionCall —
        # the parenthesized call spelling is invalid even on PostgreSQL.
        return ArrayLiteral(
            elements=tuple(convert_expression(e) for e in expr.expressions)
        )
    if isinstance(expr, exp.Case):
        return _convert_case(expr)
    if isinstance(expr, exp.Cast):
        return _convert_cast(expr)
    # sqlglot canonicalizes LTRIM/RTRIM to Trim(position=LEADING/TRAILING);
    # dropping the position silently trims BOTH sides. Recover the concrete
    # one-sided name (a position-less Trim is the plain TRIM).
    # An in-call ordered aggregate (PG ``string_agg(x, sep ORDER BY a)`` /
    # MySQL GROUP_CONCAT ... ORDER BY): sqlglot nests the Order inside
    # ``this``. Fold it into the canonical first-argument RawSQL the
    # group-concat emitter understands ("expr ORDER BY ...").
    if isinstance(expr, exp.GroupConcat) and isinstance(expr.this, exp.Order):
        ordered = expr.this
        inner_agg = ordered.this
        is_distinct = isinstance(inner_agg, exp.Distinct)
        if is_distinct and len(inner_agg.expressions) == 1:
            # Carry DISTINCT on the node so the T-SQL whole-statement gate
            # (wave 157) and the per-target emitters see it.
            inner_agg = inner_agg.expressions[0]
        expr_txt = inner_agg.sql()
        order_txt = ", ".join(o.sql() for o in ordered.expressions)
        gc_args: list[ASTNode] = [
            RawSQL(sql=f"{expr_txt} ORDER BY {order_txt}", reason="ordered aggregate")
        ]
        sep_arg = expr.args.get("separator")
        if sep_arg is not None:
            gc_args.append(convert_expression(sep_arg))
        return FunctionCall(
            name="GROUP_CONCAT", args=tuple(gc_args), distinct=is_distinct
        )
    if isinstance(expr, exp.Trim) and expr.args.get("position") and not expr.expression:
        side = str(expr.args["position"]).upper()
        name = {"LEADING": "LTRIM", "TRAILING": "RTRIM"}.get(side)
        if name is not None:
            return FunctionCall(name=name, args=(convert_expression(expr.this),))
    # TRIM([BOTH|LEADING|TRAILING] chars FROM string): sqlglot puts the string
    # in ``this`` and the trim SET in ``expression`` (LTRIM/RTRIM with a set
    # canonicalize here too). Emit the set FIRST so the downstream
    # ``TRIM(set FROM string)`` keeps operands in order — a swap silently trims
    # the wrong argument (wrong result on every target). The position rides as a
    # keyword literal the TRIM emitter reads and never prints as a value.
    if isinstance(expr, exp.Trim) and expr.expression is not None:
        position = str(expr.args.get("position") or "BOTH").upper()
        return FunctionCall(
            name="TRIM",
            args=(
                convert_expression(expr.expression),
                convert_expression(expr.this),
                Literal(value=position, dtype="keyword"),
            ),
        )
    # T-SQL CONVERT(type, value, style) with a modeled style keeps its
    # structure: FunctionCall("CONVERT", (type RawSQL, value, style Literal))
    # — the emitter spells each target's date-format/hash form (M3 F1).
    if isinstance(expr, exp.Convert) and expr.args.get("style") is not None:
        styled = _convert_styled_convert(expr)
        if styled is not None:
            return styled
    # T-SQL CONVERT(type, expr) without a style code is a plain CAST; modeling
    # it as one applies the shared type mappings (VARCHAR2, CHAR for MySQL
    # CAST, …). A styled CONVERT is caught earlier and passed through.
    if isinstance(expr, exp.Convert) and not expr.args.get("style"):
        type_expr, value_expr = expr.this, expr.expression
        if not isinstance(type_expr, exp.DataType) and isinstance(
            value_expr, exp.DataType
        ):
            type_expr, value_expr = value_expr, type_expr
        if isinstance(type_expr, exp.DataType) and value_expr is not None:
            return CastExpression(
                expression=convert_expression(value_expr),
                target_type=_convert_data_type(type_expr),
                safe=bool(expr.args.get("safe")),
            )
    # A schema-qualified function call (e.g. dbo.fn_tax(net)) parses as a Dot
    # (schema . func(...)). Fold it into a FunctionCall whose name keeps the
    # qualifier ("dbo.fn_tax"); the emitter strips dbo for non-T-SQL targets.
    if isinstance(expr, exp.Dot):
        dot_func = _convert_qualified_function(expr)
        if dot_func is not None:
            return dot_func
    # exp.And / exp.Or (and other connectors) are *also* exp.Func in sqlglot's
    # class hierarchy, so the Binary check must come before the Func check or a
    # top-level "a AND b" would be emitted as the function call "AND(a, b)".
    if isinstance(expr, exp.Add):
        rebased = _rebase_to_days(expr)
        if rebased is not None:
            return rebased
    if isinstance(expr, exp.Binary):
        return _convert_binary(expr)
    # IN with a subquery or a value list. Modeling it (rather than the RawSQL
    # fallback) lets the transform passes reach the nested query — e.g.
    # ``WHERE id IN (SELECT … WHERE ROWNUM <= 10)`` must get its ROWNUM
    # rewritten like any other SELECT (audit 2026-07-08, D3/D4 class).
    if isinstance(expr, exp.In):
        converted_in = _convert_in(expr)
        if converted_in is not None:
            return converted_in
    # EXISTS is a Func in sqlglot; convert its subquery to a SubqueryExpression
    # so it emits as SQL. Otherwise _convert_function keeps the raw SelectStatement
    # as an argument and the emitter leaks its Python repr into the output.
    if isinstance(expr, exp.Exists):
        inner = expr.this
        if isinstance(inner, (exp.Select, exp.SetOperation)):
            return UnaryOp(
                operator=UnaryOperator.EXISTS,
                operand=SubqueryExpression(query=_convert_select(inner)),
            )
        return RawSQL(sql=_source_sql(expr), reason="Complex EXISTS")
    # ALL/ANY/SOME quantified subquery (``> ALL (SELECT …)``): sqlglot
    # models the subquery, but unconverted it kept a RawSQL whose inner
    # WHERE never saw the mapping pipeline (wave 234). Convert the
    # subquery; the emitter re-attaches the quantifier keyword.
    if isinstance(expr, (exp.All, exp.Any)):
        inner = expr.this
        # sqlglot wraps the operand in a Subquery/Paren — unwrap to the
        # SELECT so it becomes a modeled SubqueryExpression (else it fell
        # through to a RawSQL carrier that never saw the emit pipeline,
        # e.g. a no-op OFFSET 0 the target rejects). A MULTI-column subquery
        # implies a row-value ``(a, b) = ANY (…)`` comparison with no
        # faithful spelling off PG — leave it a RawSQL for the composite
        # gate to degrade whole (wave 153).
        while isinstance(inner, (exp.Subquery, exp.Paren)):
            inner = inner.this
        # PG ``ANY(ARRAY(SELECT …))`` is equivalent to ``ANY(SELECT …)`` —
        # unwrap the ARRAY() constructor around a single subquery (no other
        # engine has the array spelling).
        if (
            isinstance(inner, exp.Array)
            and len(inner.expressions) == 1
            and isinstance(inner.expressions[0], (exp.Select, exp.Subquery))
        ):
            inner = inner.expressions[0]
            while isinstance(inner, (exp.Subquery, exp.Paren)):
                inner = inner.this
        scalar = not (isinstance(inner, exp.Select) and len(inner.expressions) > 1)
        if isinstance(inner, (exp.Select, exp.SetOperation)) and scalar:
            kw = "ALL" if isinstance(expr, exp.All) else "ANY"
            return SubqueryExpression(query=_convert_select(inner), quantifier=kw)
    if isinstance(expr, exp.Null):
        return Literal(value=None, dtype="null")
    # EXTRACT/DATEPART -> a FunctionCall the emitter renders as EXTRACT(part FROM x).
    # Keep the part as a clean keyword rather than an "unhandled Var" carrier.
    if isinstance(expr, exp.Extract):
        part = expr.this.name if isinstance(expr.this, exp.Var) else str(expr.this)
        return FunctionCall(
            name="EXTRACT",
            args=(
                RawSQL(sql=part.upper(), reason="date part"),
                convert_expression(expr.expression),
            ),
        )
    # Aggregate FILTER (WHERE p): PG-only spelling with a faithful
    # universal rewrite — agg(CASE WHEN p THEN x END); COUNT(*) counts 1.
    if isinstance(expr, exp.Filter):
        agg = _convert_function(expr.this)
        cond = convert_expression(expr.expression.this)
        from unique.core.ast_nodes import CaseExpression

        if agg.args and isinstance(agg.args[0], Star):
            wrapped: ASTNode = CaseExpression(
                whens=((cond, Literal(value=1, dtype="integer")),), else_expr=None
            )
        elif agg.args:
            wrapped = CaseExpression(whens=((cond, agg.args[0]),), else_expr=None)
        else:
            wrapped = CaseExpression(
                whens=((cond, Literal(value=1, dtype="integer")),), else_expr=None
            )
        return FunctionCall(
            name=agg.name,
            args=(wrapped, *agg.args[1:]),
            distinct=agg.distinct,
        )

    if isinstance(expr, exp.Coalesce) and expr.args.get("is_null"):
        # T-SQL ``ISNULL(x, y)`` returns a value of the FIRST argument's declared
        # type, so a longer replacement is TRUNCATED (``ISNULL(CAST(NULL AS
        # VARCHAR(2)), 'abcdef')`` = ``'ab'``). Plain COALESCE keeps the full
        # value (its result type is the highest-precedence operand). When the
        # first argument is a CAST to a length-bearing type, wrap the COALESCE in
        # that CAST to reproduce ISNULL's truncation. (Consuming ``is_null`` also
        # clears the unread-arg tripwire.)
        call = _convert_function(expr)
        first = call.args[0] if call.args else None
        if isinstance(first, CastExpression) and first.target_type.params:
            return CastExpression(expression=call, target_type=first.target_type)
        return call
    if isinstance(expr, exp.Func):
        return _convert_function(expr)
    if isinstance(expr, exp.Not):
        return UnaryOp(
            operator=UnaryOperator.NOT, operand=convert_expression(expr.this)
        )
    if isinstance(expr, exp.Neg):
        return UnaryOp(
            operator=UnaryOperator.NEGATIVE,
            operand=convert_expression(expr.this),
        )
    if isinstance(expr, exp.Is):
        return _convert_is(expr)
    if isinstance(expr, exp.Subquery):
        inner = expr.this
        # A double-parenthesized scalar subquery nests Subquery/Paren:
        # unwrap — the "Complex subquery" fallback rendered it in sqlglot's
        # GENERIC dialect inside routine bodies.
        while isinstance(inner, (exp.Subquery, exp.Paren)):
            inner = inner.this
        # A scalar ``(VALUES (v[, …]))`` (one row) is PG-only spelling —
        # ``(SELECT v[, …])`` is the universal equivalent.
        if isinstance(inner, exp.Values) and len(inner.expressions) == 1:
            row = inner.expressions[0]
            cols = tuple(convert_expression(c) for c in row.expressions)
            return SubqueryExpression(
                query=SelectStatement(columns=cols), alias=expr.alias or None
            )
        if isinstance(inner, (exp.Select, exp.SetOperation)):
            return SubqueryExpression(
                query=_convert_select(inner), alias=expr.alias or None
            )
        return RawSQL(sql=_source_sql(expr), reason="Complex subquery")
    if isinstance(expr, exp.Window):
        if str(expr.args.get("over") or "").upper() == "KEEP":
            # Oracle ``agg(x) KEEP (DENSE_RANK FIRST/LAST ORDER BY y)`` is an
            # ordered AGGREGATE (one value per group, taken from the rows with
            # the extreme y) — NOT a window function. Rendering it as ``agg(x)
            # OVER (ORDER BY y)`` silently changed it to a per-row running
            # aggregate. There is no portable form, so preserve it whole and
            # degrade honestly (carrier + warning via _gate_unmapped_operator).
            return RawSQL(
                sql=_source_sql(expr),
                reason="unmapped operator KEEP (DENSE_RANK) ordered aggregate",
            )
        return _convert_window(expr)
    if isinstance(expr, exp.Paren):
        return convert_expression(expr.this)
    # A bare Select in expression position (a double-parenthesized scalar
    # subquery unwraps to one): model it — the unhandled fallback rendered
    # it in sqlglot's GENERIC dialect inside routine bodies.
    if isinstance(expr, (exp.Select, exp.SetOperation)):
        return SubqueryExpression(query=_convert_select(expr), alias=None)
    if isinstance(expr, exp.Ordered):
        return _convert_ordered(expr)
    # MySQL charset introducer (_utf8'x'): the charset tag is MySQL-only
    # syntax (and legacy even there); keep just the string literal.
    if isinstance(expr, exp.Introducer):
        return convert_expression(expr.expression)

    # Hex/binary literal (MySQL x'8f'): the raw fallback rendered it as
    # a DECIMAL number, overflowing past BIGINT digits (wave 174). Model
    # it; each emitter has its own spelling.
    if isinstance(expr, exp.HexString):
        return Literal(value=str(expr.this), dtype="hex")

    # MySQL/PG bit-string literal ``b'101'`` (== ``0b101``) evaluates to its
    # integer value in a numeric context (MySQL ``b'101' + 0`` = 5). Emitting
    # the bare bit literal shipped an invalid ``bit + integer`` to PG; fold it
    # to the integer like the hex path so it is portable everywhere.
    if isinstance(expr, exp.BitString):
        return Literal(value=int(str(expr.this), 2), dtype="integer")

    # T-SQL N'...' national literals: modeled so each target spells them —
    # PostgreSQL has NO such literal (the RawSQL fallback shipped it raw)
    # and MySQL's canonical output drops the prefix.
    if isinstance(expr, exp.National):
        return Literal(value=str(expr.name), dtype="national")

    # Bitwise NOT (``~x``): Oracle has no ~ operator (ORA-00911) — the
    # emitter spells the two's-complement identity there (wave 189).
    if isinstance(expr, exp.BitwiseNot):
        return UnaryOp(
            operator=UnaryOperator.BITWISE_NOT,
            operand=convert_expression(expr.this),
        )

    # MySQL's INTERVAL(x, v1, v2, …) INDEX function (position of the
    # last threshold ≤ x) parses as an Interval literal wrapping a
    # Tuple — it shipped ``INTERVAL ((x, v1, …))``, invalid everywhere
    # (wave 165). Only the unit-less Tuple form is the function.
    if (
        isinstance(expr, exp.Interval)
        and isinstance(expr.this, exp.Tuple)
        and expr.args.get("unit") is None
    ):
        return FunctionCall(
            name="INTERVAL",
            args=tuple(convert_expression(a) for a in expr.this.expressions),
        )

    # Fallback: emit as raw SQL, rendered in the SOURCE dialect. The
    # default (generic) renderer silently changes spellings — sqlglot
    # stores PG subscripts 0-based, so ``arr[2]`` shipped as ``arr[1]``
    # (silent data corruption, wave 108).
    return RawSQL(
        sql=_source_sql(expr),
        reason=f"Unhandled expression type: {type(expr).__name__}",
    )


def _dedup_duplicate_cross_joins(expression: exp.Expression) -> None:
    """Remove bare joins whose alias-or-name repeats a table already in scope.

    Works around a sqlglot ``eliminate_join_marks`` bug (see the call site): an
    aliased preserved table is re-emitted as a spurious CROSS JOIN. A duplicate
    table alias in a FROM/JOIN list is always a syntax error, so dropping the
    repeat (only when it carries no ON/USING) is a safe normalization.
    """
    for select in expression.find_all(exp.Select):
        joins = select.args.get("joins") or []
        if not joins:
            continue
        frm = select.args.get("from") or select.args.get("from_")
        seen: set[str] = set()
        if frm is not None and frm.this is not None:
            seen.add(frm.this.alias_or_name)
        kept: list[exp.Join] = []
        for j in joins:
            name = j.this.alias_or_name
            is_bare = not j.args.get("on") and not j.args.get("using")
            if name in seen and is_bare:
                continue
            seen.add(name)
            kept.append(j)
        if len(kept) != len(joins):
            select.set("joins", kept)


def _requalify_distinct_order(
    items: tuple[OrderByItem, ...], projected: set[str], has_star: bool
) -> tuple[OrderByItem, ...] | None:
    """Re-point a DISTINCT ON outer ORDER BY's table-qualified keys to the
    wrapper's bare projected columns (see ``_rewrite_distinct_on``). Returns
    ``None`` when a key is not projected and cannot be referenced at the
    wrapper level."""
    out: list[OrderByItem] = []
    for it in items:
        e = it.expression
        if isinstance(e, ColumnRef) and e.table is not None:
            if not (has_star or e.name.lower() in projected):
                return None
            out.append(
                dataclasses.replace(
                    it, expression=ColumnRef(name=e.name, quoted=e.quoted)
                )
            )
        else:
            out.append(it)
    return tuple(out)


def _rewrite_distinct_on(
    *,
    distinct_on: tuple[ASTNode, ...],
    columns: tuple[ASTNode, ...],
    from_clause: object,
    joins: tuple[JoinClause, ...],
    where: ASTNode | None,
    order_by: tuple[OrderByItem, ...],
    limit: object,
    ctes: tuple[CTEDefinition, ...],
) -> SelectStatement | None:
    """Rewrite PostgreSQL ``SELECT DISTINCT ON (keys) … ORDER BY …`` into the
    portable ``ROW_NUMBER() OVER (PARTITION BY keys ORDER BY …) = 1`` form so
    the one-row-per-group semantics survive on engines with no DISTINCT ON
    (T-SQL/MySQL/Oracle). ``SELECT DISTINCT`` alone would keep every distinct
    tuple. Returns None when a projected column cannot be referenced from the
    wrapping query (so the caller keeps the current behaviour)."""

    def _outer_ref(col: ASTNode) -> ASTNode | None:
        if isinstance(col, Star):
            return Star()
        if isinstance(col, Alias):
            return ColumnRef(name=col.name, quoted=col.quoted)
        if isinstance(col, ColumnRef):
            return ColumnRef(name=col.name, quoted=col.quoted)
        return None

    outer_columns = tuple(_outer_ref(c) for c in columns)
    if any(c is None for c in outer_columns):
        return None

    # The outer ORDER BY runs against the WRAPPER (alias ``uq_distinct_on``),
    # not the source relation ``x`` — a table-qualified order key (``x.a``,
    # ``x.b``) is out of scope there (T-SQL 4104 / MySQL 1054 / ORA-00904).
    # Re-point each qualified order key to the wrapper's projected column
    # (its bare name); bail out (keep current behaviour) if an order key is
    # not among the projected columns and cannot be referenced.
    _has_star = any(isinstance(c, Star) for c in columns)
    _projected = {c.name.lower() for c in columns if isinstance(c, (Alias, ColumnRef))}
    outer_order_by = _requalify_distinct_order(order_by, _projected, _has_star)
    if outer_order_by is None:
        return None
    # ROW_NUMBER needs a deterministic order; the DISTINCT ON's own ORDER BY
    # picks the surviving row (fall back to the keys when none was given).
    window_order = order_by or tuple(OrderByItem(expression=k) for k in distinct_on)
    rn = Alias(
        expression=WindowFunction(
            function=FunctionCall(name="ROW_NUMBER"),
            window=WindowSpec(partition_by=distinct_on, order_by=window_order),
        ),
        name="uq_rn",
    )
    inner = SelectStatement(
        columns=(*columns, rn),
        from_clause=from_clause,  # type: ignore[arg-type]
        joins=joins,
        where=where,
    )
    return SelectStatement(
        columns=cast("tuple[ASTNode, ...]", outer_columns),
        from_clause=SubqueryExpression(query=inner, alias="uq_distinct_on"),
        where=BinaryOp(
            operator=BinaryOperator.EQ,
            left=ColumnRef(name="uq_rn"),
            right=Literal(value=1, dtype="integer"),
        ),
        order_by=outer_order_by,
        limit=limit,  # type: ignore[arg-type]
        ctes=ctes,
    )


def _convert_select(expr: exp.Expression) -> SelectStatement:
    """Convert a sqlglot Select expression to a SelectStatement IR node."""
    # Handle Union by extracting the left Select
    if isinstance(expr, exp.SetOperation):
        return _convert_union(expr)

    columns = tuple(convert_expression(col) for col in (expr.expressions or []))

    # FROM — use the direct arg, not find(), which recurses into a subquery in
    # the WHERE (e.g. NOT EXISTS (SELECT … FROM t)) and would pull that table
    # into this SELECT's FROM. sqlglot keys it "from_" (older versions "from").
    from_clause: (
        TableRef | SubqueryExpression | UnpivotRelation | PivotRelation | None
    ) = None
    hoisted_joins: tuple[JoinClause, ...] = ()
    from_expr = expr.args.get("from_") or expr.args.get("from")
    if from_expr and from_expr.this:
        from_item = from_expr.this
        # A parenthesized join relation — ``FROM (a JOIN b ON …), c`` — is a
        # Subquery wrapping a Table that carries the group's joins; parens
        # around joins are semantically transparent, so unwrap and hoist
        # (emission order keeps the comma-join grouping).
        if (
            isinstance(from_item, exp.Subquery)
            and isinstance(from_item.this, exp.Table)
            and from_item.this.args.get("joins")
        ):
            inner_table = from_item.this
            hoisted_joins = tuple(_convert_join(j) for j in inner_table.args["joins"])
            from_clause = _convert_table_ref(inner_table)
        else:
            from_clause = _convert_table_or_subquery(from_item)
        from_clause = _maybe_wrap_unpivot(from_item, from_clause)

    # JOINs
    joins = hoisted_joins + tuple(
        _convert_join(j) for j in (expr.args.get("joins") or [])
    )

    # WHERE — the direct arg, like FROM: find() would descend into a derived
    # table in FROM and duplicate ITS where onto this (outer) SELECT.
    where = None
    where_expr = expr.args.get("where")
    if where_expr:
        where = convert_expression(where_expr.this)

    # GROUP BY, plus its ROLLUP super-aggregate modifier. sqlglot keeps ROLLUP
    # in a separate ``rollup`` arg — either wrapping the columns (the standard
    # ``ROLLUP(x)`` spelling) or empty with the columns in ``expressions`` (the
    # MySQL ``x WITH ROLLUP`` spelling). Both were dropped, silently discarding
    # the subtotal rows (or, for ``ROLLUP(x)``, the entire GROUP BY).
    group_by_expr = expr.args.get("group")
    group_modifier: str | None = None
    grouping_sets_sql: str | None = None
    group_by_composite: tuple[GroupingElement, ...] = ()
    group_source: list[exp.Expression] = []
    if group_by_expr is not None:
        rollup = group_by_expr.args.get("rollup") or []
        cube = group_by_expr.args.get("cube") or []
        gsets = group_by_expr.args.get("grouping_sets") or []
        plain = list(group_by_expr.expressions)
        # A CUBE/ROLLUP wrapper is only its own grouping element when it CARRIES
        # columns; an EMPTY ``ROLLUP()`` wrapper with the columns in
        # ``expressions`` is MySQL's ``cols WITH ROLLUP`` single-modifier form.
        ne_cube = [c for c in cube if c.expressions]
        ne_rollup = [r for r in rollup if r.expressions]
        # A composite GROUP BY — more than one grouping element (``CUBE(a, b),
        # ROLLUP(c)``, ``a, ROLLUP(b)``, …). sqlglot splits the elements across
        # the ``expressions``/``cube``/``rollup``/``grouping_sets`` args; keeping
        # only one (the previous behaviour) silently dropped the rest. Preserve
        # every element in ``group_by_composite`` (the result set is
        # order-independent across grouping elements).
        _pieces = (1 if plain else 0) + len(ne_cube) + len(ne_rollup) + len(gsets)
        if _pieces > 1:
            elements: list[GroupingElement] = []
            if plain:
                elements.append(
                    GroupingElement(
                        kind="",
                        columns=tuple(convert_expression(g) for g in plain),
                    )
                )
            for c in ne_cube:
                elements.append(
                    GroupingElement(
                        kind="CUBE",
                        columns=tuple(convert_expression(x) for x in c.expressions),
                    )
                )
            for r in ne_rollup:
                elements.append(
                    GroupingElement(
                        kind="ROLLUP",
                        columns=tuple(convert_expression(x) for x in r.expressions),
                    )
                )
            for gs in gsets:
                elements.append(
                    GroupingElement(kind="GROUPING SETS", sets_sql=gs.sql())
                )
            group_by_composite = tuple(elements)
            # Distinct base columns for the MySQL degrade / clause-presence checks.
            seen_c: dict[str, exp.Expression] = {}
            _flat = (
                list(plain)
                + [x for c in ne_cube for x in c.expressions]
                + [x for r in ne_rollup for x in r.expressions]
            )
            for node_g in _flat:
                cols = (
                    [node_g]
                    if isinstance(node_g, exp.Column)
                    else node_g.find_all(exp.Column)
                )
                for col in cols:
                    seen_c.setdefault(col.sql(), col)
            for gs in gsets:
                for col in gs.find_all(exp.Column):
                    seen_c.setdefault(col.sql(), col)
            group_source = list(seen_c.values())
        elif rollup or cube:
            mod_nodes = rollup or cube
            group_modifier = "ROLLUP" if rollup else "CUBE"
            inner = [c for r in mod_nodes for c in r.expressions]
            group_source = inner or list(group_by_expr.expressions)
        elif gsets:
            # GROUPING SETS is standard SQL on T-SQL/Oracle/PG — render it once
            # and emit verbatim; MySQL has no equivalent, so keep the distinct
            # columns as a base GROUP BY (a carrier documents the omission).
            group_modifier = "GROUPING SETS"
            grouping_sets_sql = " ".join(g.sql() for g in gsets)
            seen: dict[str, exp.Expression] = {}
            for g in gsets:
                for col in g.find_all(exp.Column):
                    seen.setdefault(col.sql(), col)
            group_source = list(seen.values())
        else:
            group_source = list(group_by_expr.expressions)
    group_by = tuple(convert_expression(g) for g in group_source)

    # HAVING — direct arg, for the same reason as WHERE.
    having = None
    having_expr = expr.args.get("having")
    if having_expr:
        having = convert_expression(having_expr.this)

    # ORDER BY
    order_by_expr = expr.args.get("order")
    order_by: tuple[OrderByItem, ...] = ()
    if order_by_expr:
        order_by = tuple(_convert_ordered(o) for o in order_by_expr.expressions)

    # LIMIT / OFFSET
    limit = None
    limit_expr = expr.args.get("limit")
    offset_expr = expr.args.get("offset")
    if limit_expr or offset_expr:
        # T-SQL TOP n PERCENT carries a percent flag in sqlglot's limit options.
        # ``OFFSET … FETCH NEXT n ROWS`` parses to an exp.Fetch whose count is in
        # args["count"], not .expression — so read either (else LIMIT leaks None).
        percent = False
        with_ties = False
        limit_count = None
        if limit_expr is not None:
            opts = limit_expr.args.get("limit_options")
            percent = bool(opts and opts.args.get("percent"))
            with_ties = bool(opts and opts.args.get("with_ties"))
            count_node = limit_expr.args.get("count") or limit_expr.expression
            limit_count = convert_expression(count_node) if count_node else None
        limit = LimitClause(
            limit=limit_count,
            offset=convert_expression(offset_expr.expression) if offset_expr else None,
            percent=percent,
            with_ties=with_ties,
        )

    # DISTINCT / DISTINCT ON
    distinct_node = expr.args.get("distinct")
    distinct = distinct_node is not None
    distinct_on: tuple[ASTNode, ...] = ()
    if distinct_node is not None and distinct_node.args.get("on") is not None:
        _on = distinct_node.args["on"]
        _on_exprs = _on.expressions if isinstance(_on, exp.Tuple) else [_on]
        distinct_on = tuple(convert_expression(e) for e in _on_exprs)
        distinct = False  # DISTINCT ON is not a plain SELECT DISTINCT

    # CTEs
    ctes: tuple[CTEDefinition, ...] = ()
    with_clause = expr.args.get("with") or expr.args.get("with_")
    if with_clause:
        rec = bool(with_clause.args.get("recursive"))
        ctes = tuple(_convert_cte(c, recursive=rec) for c in with_clause.expressions)

    # A set-returning function in the SELECT list with no FROM — PG's
    # ``SELECT generate_series(1, 5)`` returns one row per element. Move the SRF
    # into the FROM clause (a function relation) and project its value column, so
    # the FROM-position rewrite (CONNECT BY / numbers source) can render it.
    if from_clause is None and not joins and len(columns) == 1:
        _only = columns[0]
        _srf = _only.expression if isinstance(_only, Alias) else _only
        if isinstance(_srf, FunctionCall) and _srf.name.upper() == "GENERATE_SERIES":
            _srf_alias = _only.name if isinstance(_only, Alias) else "generate_series"
            from_clause = TableRef(name=_srf_alias, function=_srf, alias=_srf_alias)
            columns = (ColumnRef(name=_srf_alias),)

    if (
        distinct_on
        and not group_by
        and not group_by_composite
        and not grouping_sets_sql
    ):
        rewritten = _rewrite_distinct_on(
            distinct_on=distinct_on,
            columns=columns,
            from_clause=from_clause,
            joins=joins,
            where=where,
            order_by=order_by,
            limit=limit,
            ctes=ctes,
        )
        if rewritten is not None:
            return tag_temporal_columns(rewritten)

    return tag_temporal_columns(
        SelectStatement(
            columns=columns,
            from_clause=from_clause,
            joins=joins,
            where=where,
            group_by=group_by,
            group_modifier=group_modifier,
            grouping_sets_sql=grouping_sets_sql,
            group_by_composite=group_by_composite,
            having=having,
            order_by=order_by,
            limit=limit,
            distinct=distinct,
            ctes=ctes,
            # A genuinely-empty source select list (PG ``SELECT;``) must not
            # gain a ``*`` (wave 124) — flagged so the emitter distinguishes
            # it from fallback-built empty tuples where ``*`` is load-bearing.
            empty_select_list=not (expr.expressions or []),
            calc_found_rows=any(
                isinstance(m, exp.Var) and m.name.upper() == "SQL_CALC_FOUND_ROWS"
                for m in (expr.args.get("operation_modifiers") or [])
            ),
            # T-SQL FOR XML/FOR JSON (sqlglot only partially models the clause,
            # so capture its presence — the emitter degrades on non-T-SQL).
            has_for_xml=expr.args.get("for_") is not None,
        )
    )


def _set_op_type(node: exp.SetOperation) -> SetOperationType:
    # ``distinct is False`` means the ALL variant (INTERSECT ALL / EXCEPT ALL /
    # UNION ALL) — keeping duplicates. Dropping it silently changes the row
    # multiset (a defect); the emitter renders ALL where the target supports it.
    is_all = node.args.get("distinct") is False
    if isinstance(node, exp.Intersect):
        return SetOperationType.INTERSECT_ALL if is_all else SetOperationType.INTERSECT
    if isinstance(node, exp.Except):
        return SetOperationType.EXCEPT_ALL if is_all else SetOperationType.EXCEPT
    return SetOperationType.UNION_ALL if is_all else SetOperationType.UNION


def _convert_union(expr: exp.SetOperation) -> SelectStatement:
    """Convert a UNION/INTERSECT/EXCEPT chain to a linked SelectStatement.

    sqlglot parses ``A UNION B UNION C`` left-nested as ``Union(Union(A, B), C)``.
    Flatten the whole chain (converting only the outer two operands silently
    dropped every middle arm) into a base statement whose ``set_query`` links
    each subsequent arm in left-to-right order.
    """

    def _convert_arm(e: exp.Expression) -> SelectStatement:
        # A parenthesized arm ``(SELECT …)`` is a Subquery; reading it as
        # a Select shipped an empty ``SELECT *`` with FROM and columns
        # dropped.
        if isinstance(e, exp.Subquery):
            inner = cast(exp.Expression, e.unnest())
            if isinstance(inner, exp.Values):
                # A VALUES arm — ``(VALUES ('a'), ('b')) UNION ALL …`` —
                # mangled into a one-row SELECT; reuse the relation
                # converter's UNION-chain lowering (wave 131).
                lowered = _convert_table_or_subquery(inner)
                if isinstance(lowered, SubqueryExpression):
                    return lowered.query
            if isinstance(inner, exp.SetOperation):
                # A parenthesized arm that is ITSELF a chain — ``A UNION
                # (B UNION ALL C)`` — must keep its association (UNION
                # dedups; flattening changes the row set) and its outer
                # trailing ORDER must stay outside. Shield it as a
                # derived table, valid on every target (wave 130).
                return SelectStatement(
                    columns=(Star(),),
                    from_clause=SubqueryExpression(
                        query=_convert_union(inner), alias="uq_setarm"
                    ),
                )
            e = inner
        sel = _convert_select(e)
        if sel.set_query is not None:
            return sel  # nested chain — handled by its own conversion
        if sel.limit is not None:
            # An arm-local ORDER BY/LIMIT loses its scope once the parens
            # go (trailing position re-reads it as the whole union's);
            # shield it as a derived table, valid on every target.
            return SelectStatement(
                columns=(Star(),),
                from_clause=SubqueryExpression(query=sel, alias="uq_setarm"),
            )
        if sel.order_by:
            # ORDER BY without LIMIT in a set-op arm has no observable
            # effect (arm order is never guaranteed); drop it.
            sel = dataclasses.replace(sel, order_by=())
        return sel

    ops: list[tuple[SetOperationType, SelectStatement]] = []
    node: exp.Expression = expr
    while isinstance(node, exp.SetOperation):
        ops.append((_set_op_type(node), _convert_arm(node.expression)))
        node = node.this
    ops.reverse()  # first..last set operation, left to right

    selects = [_convert_arm(node), *(s for _, s in ops)]

    # The union's OUTER ORDER BY/LIMIT parse onto the SetOperation node;
    # trailing position on the last arm is read as whole-union by every
    # engine.
    order_expr = expr.args.get("order")
    if (
        order_expr is None
        and isinstance(expr.expression, exp.Select)
        and expr.expression.args.get("order") is not None
        and expr.expression.args.get("limit") is None
    ):
        # sqlglot's T-SQL/MySQL readers attach a whole-set-op trailing ORDER BY
        # to the LAST arm's SELECT node (only PG puts it on the SetOperation).
        # Those engines forbid a per-arm ORDER BY without TOP/LIMIT, so a bare
        # trailing sort on the last arm IS the whole-union order — promote it
        # here (``_convert_arm`` would otherwise drop it as ineffective).
        order_expr = expr.expression.args.get("order")
    if order_expr:
        selects[-1] = dataclasses.replace(
            selects[-1],
            order_by=tuple(_convert_ordered(o) for o in order_expr.expressions),
        )
    limit_expr = expr.args.get("limit")
    offset_expr = expr.args.get("offset")
    if limit_expr is not None or offset_expr is not None:
        count_node = None
        if limit_expr is not None:
            count_node = limit_expr.args.get("count") or limit_expr.expression
        selects[-1] = dataclasses.replace(
            selects[-1],
            limit=LimitClause(
                limit=convert_expression(count_node) if count_node else None,
                offset=(
                    convert_expression(offset_expr.expression) if offset_expr else None
                ),
            ),
        )
    set_ops = [op for op, _ in ops]

    def _link(
        arm: SelectStatement, op: SetOperationType, rest: SelectStatement
    ) -> SelectStatement:
        # An arm that is itself a chain links at its TAIL — replacing
        # set_op/set_query on the head clobbered the nested chain, and a
        # tail ORDER BY without LIMIT would land mid-chain (drop it).
        if arm.set_query is not None:
            return dataclasses.replace(arm, set_query=_link(arm.set_query, op, rest))
        if arm.order_by and arm.limit is None:
            arm = dataclasses.replace(arm, order_by=())
        return dataclasses.replace(arm, set_op=op, set_query=rest)

    result = selects[-1]
    for i in range(len(set_ops) - 1, -1, -1):
        result = _link(selects[i], set_ops[i], result)
    return result


def _convert_insert(expr: exp.Insert) -> InsertStatement | RawSQL:
    """Convert a sqlglot Insert to InsertStatement."""
    table = _convert_table_ref(expr.this)

    columns: tuple[str, ...] = ()
    # In sqlglot v30+, columns may be embedded in a Schema node
    schema_node = expr.this
    if isinstance(schema_node, exp.Schema) and schema_node.expressions:
        columns = tuple(
            c.name if hasattr(c, "name") else str(c) for c in schema_node.expressions
        )
    else:
        col_expr = expr.args.get("columns")
        if col_expr:
            columns = tuple(c.name if hasattr(c, "name") else str(c) for c in col_expr)

    # The body may be wrapped in parens — Oracle/PG allow ``INSERT INTO t
    # (cols) (SELECT …)`` — which sqlglot models as a Subquery; unwrap it
    # (the unparenthesized form is valid on every target).
    val_expr = expr.args.get("expression")
    body = val_expr.unnest() if isinstance(val_expr, exp.Subquery) else val_expr

    # VALUES
    values: tuple[tuple[ASTNode, ...], ...] = ()
    if isinstance(body, exp.Values):
        values = tuple(
            tuple(convert_expression(v) for v in row.expressions)
            for row in body.expressions
        )

    # SELECT (or a set operation: SELECT … UNION SELECT …)
    select = None
    if isinstance(body, (exp.Select, exp.SetOperation)):
        # A CTE that precedes the INSERT (``WITH cte AS (…) INSERT … SELECT …
        # FROM cte``) is parsed onto the Insert, not the inner SELECT — move it
        # onto the SELECT or the emitter drops it, leaving ``FROM cte`` dangling.
        cte = expr.args.get("with") or expr.args.get("with_")
        if cte is not None and not (body.args.get("with") or body.args.get("with_")):
            body.set("with", cte)
        select = _convert_select(body)

    if val_expr is not None and not values and select is None:
        # The source has a body we could not model. Emitting the bare INSERT
        # would ship ``DEFAULT VALUES`` — parse-valid on the target, so the
        # honesty gate cannot catch it: silent data loss (live 2x on PG,
        # 2026-07-11). Degrade to a passthrough instead; the target-dialect
        # parse check downstream decides whether it must become a carrier.
        return RawSQL(
            sql=_source_sql(expr),
            reason=f"Unmodeled INSERT body: {type(val_expr).__name__}",
        )

    # Upsert clause (guardrail 7 — do not let ``conflict``/``ignore`` fall on
    # the floor). sqlglot normalizes PG ``ON CONFLICT`` and MySQL ``ON
    # DUPLICATE KEY UPDATE`` into ``exp.OnConflict``; ``INSERT IGNORE`` sets the
    # ``ignore`` flag. A shape we cannot model degrades the WHOLE statement to a
    # carrier (never a plain INSERT that would raise/duplicate at runtime).
    conflict = expr.args.get("conflict")
    on_conflict: ASTNode | None = None
    if isinstance(conflict, exp.OnConflict):
        on_conflict = _convert_on_conflict(conflict)
        if on_conflict is None:
            return RawSQL(
                sql=_source_sql(expr),
                reason=(
                    "INSERT upsert clause has no portable model; "
                    "statement preserved as a comment"
                ),
            )
    elif expr.args.get("ignore"):
        on_conflict = OnConflictClause(action="nothing", from_ignore=True)

    # ``INSERT … DEFAULT VALUES`` (all-defaults row): read the ``default`` arg so
    # guardrail 7's tripwire does not false-fire (challenge
    # pg-insert-default-values-falsewarn). The emitter spells it per target
    # (MySQL ``() VALUES ()``, Oracle carrier + warning, PG/T-SQL ``DEFAULT
    # VALUES``); it is honestly translated on MySQL, so no warning is due there.
    default_values = bool(expr.args.get("default"))

    return InsertStatement(
        table=table,
        columns=columns,
        values=values,
        select=select,
        on_conflict=on_conflict,
        default_values=default_values,
    )


def _map_excluded_refs(node: ASTNode) -> ASTNode:
    """Replace incoming-row references anywhere in a converted conflict-action
    value — PG ``EXCLUDED.col`` (a table-qualified ColumnRef) and MySQL
    ``VALUES(col)`` (a one-arg function) — with the :class:`ExcludedColumn`
    marker, recursing through the whole expression tree."""
    if isinstance(node, ColumnRef) and node.table and node.table.upper() == "EXCLUDED":
        return ExcludedColumn(column=node.name)
    if (
        isinstance(node, FunctionCall)
        and node.name.upper() == "VALUES"
        and len(node.args) == 1
    ):
        arg = node.args[0]
        if isinstance(arg, ColumnRef) and not arg.table:
            return ExcludedColumn(column=arg.name)
        # A bare column identifier converts to a RawSQL passthrough, not a
        # ColumnRef; accept the simple-name form (``VALUES(v)``).
        if isinstance(arg, RawSQL) and re.fullmatch(r"\w+", arg.sql.strip()):
            return ExcludedColumn(column=arg.sql.strip())
    if not dataclasses.is_dataclass(node):
        return node
    changes: dict[str, Any] = {}
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if isinstance(value, ASTNode):
            mapped = _map_excluded_refs(value)
            if mapped is not value:
                changes[f.name] = mapped
        elif isinstance(value, tuple):
            new_items = tuple(_map_tuple_item(item) for item in value)
            if new_items != value:
                changes[f.name] = new_items
    return dataclasses.replace(node, **changes) if changes else node


def _map_tuple_item(item: object) -> object:
    """Recurse ``_map_excluded_refs`` through a tuple field's items (an ASTNode,
    or a nested tuple such as a CASE branch pair)."""
    if isinstance(item, ASTNode):
        return _map_excluded_refs(item)
    if isinstance(item, tuple):
        return tuple(_map_tuple_item(sub) for sub in item)
    return item


def _convert_on_conflict(oc: exp.OnConflict) -> OnConflictClause | None:
    """Convert ``exp.OnConflict`` (PG/MySQL) to the IR clause, or ``None`` when
    the shape has no portable model (named constraint, partial-index predicate,
    non-EQ assignment)."""
    # ON CONSTRAINT <name> / partial-index WHERE on the target: PG-only shapes
    # with no key list to lower a MERGE with — degrade whole.
    if (
        oc.args.get("constraint") is not None
        or oc.args.get("index_predicate") is not None
    ):
        return None
    keys = tuple(k.name for k in oc.args.get("conflict_keys") or [])
    where_expr = oc.args.get("where")
    where = None
    if isinstance(where_expr, exp.Where):
        where = convert_expression(where_expr.this)
    elif where_expr is not None:
        where = convert_expression(where_expr)

    action_var = oc.args.get("action")
    action_text = (action_var.name if action_var is not None else "").upper()
    if action_text == "DO NOTHING":
        return OnConflictClause(action="nothing", key_columns=keys, where=where)

    # DO UPDATE (PG) / ON DUPLICATE KEY UPDATE (MySQL, ``duplicate=True``).
    assignments: list[tuple[str, ASTNode]] = []
    for eq in oc.args.get("expressions") or []:
        if not isinstance(eq, exp.EQ):
            return None
        col = eq.this.name if hasattr(eq.this, "name") else str(eq.this)
        assignments.append((col, _map_excluded_refs(convert_expression(eq.expression))))
    if not assignments:
        return None
    return OnConflictClause(
        action="update",
        key_columns=keys,
        assignments=tuple(assignments),
        where=where,
    )


def _convert_update(expr: exp.Update) -> ASTNode:
    """Convert a sqlglot Update to UpdateStatement.

    A cross-table ``UPDATE ... SET ... FROM t JOIN s ON ...`` keeps its source
    table and joins: sqlglot nests them inside the ``from_`` clause's table
    (``from_.this`` is the first source table, whose ``joins`` arg holds the
    rest). They are lifted into ``from_clause``/``joins`` so the emitter can
    render each engine's idiomatic cross-table update instead of dropping them.
    """
    table = _convert_table_ref(expr.this)

    assignments: list[tuple[str, ASTNode]] = []
    for eq in expr.args.get("expressions", []):
        if isinstance(eq, exp.EQ):
            col_name = eq.this.name if hasattr(eq.this, "name") else str(eq.this)
            val = convert_expression(eq.expression)
            assignments.append((col_name, val))

    from_clause: TableRef | None = None
    joins: list[JoinClause] = []
    from_expr = expr.args.get("from_") or expr.args.get("from")
    if from_expr is not None:
        source_table = from_expr.this
        if isinstance(source_table, exp.Table):
            from_clause = _convert_table_ref(source_table)
            for join_expr in source_table.args.get("joins") or []:
                joins.append(_convert_join(join_expr))
        else:
            # A derived-table source (``FROM (VALUES …) s(x)``) has no
            # modeled form — it was silently DROPPED, leaving dangling
            # alias references (wave 193). Same-dialect ships verbatim,
            # cross-dialect gets the unhandled-expression carrier.
            return RawSQL(
                sql=_source_sql(expr),
                reason="Unhandled expression type: UPDATE FROM derived table",
            )

    # MySQL's ``UPDATE t JOIN s ON … SET …`` hangs the join off the target table
    # (``expr.this``), not a FROM clause, so the join was silently dropped —
    # leaving an ``UPDATE t SET n = s.n`` with a dangling ``s``. Lift it into the
    # same from_clause/joins shape the FROM-JOIN form uses so the per-engine
    # cross-table emitter renders it.
    if (
        from_clause is None
        and isinstance(expr.this, exp.Table)
        and expr.this.args.get("joins")
    ):
        from_clause = _convert_table_ref(expr.this)
        for join_expr in expr.this.args["joins"]:
            joins.append(_convert_join(join_expr))

    where = None
    # Direct arg, not find(): find() would descend into a subquery in SET/FROM
    # and lift ITS where onto this UPDATE (same class as the SELECT bug).
    where_expr = expr.args.get("where")
    if where_expr:
        where = convert_expression(where_expr.this)

    # MySQL ``UPDATE … [ORDER BY …] LIMIT n`` caps the update to n rows; both
    # args were unread, so the LIMIT (and its ORDER BY) fell on the floor and
    # the UPDATE hit EVERY matching row (data loss, twin of the DELETE cap).
    order_items, limit = _read_order_and_limit(expr)

    return UpdateStatement(
        table=table,
        assignments=tuple(assignments),
        where=where,
        from_clause=from_clause,
        joins=tuple(joins),
        limit=limit,
        order_by=order_items,
    )


def _delete_top_count(tb: exp.Expression) -> int | None:
    """Return n if *tb* is the pseudo-table sqlglot builds for ``DELETE TOP(n)``.

    sqlglot's T-SQL reader mis-parses ``DELETE TOP (n) FROM t`` by dropping the
    cap into ``tables`` as a fake table ``TOP`` whose alias column holds ``n``.
    (``TOP (n) PERCENT`` does not parse in sqlglot, so only the plain row cap
    reaches here.)
    """
    if (
        isinstance(tb, exp.Table)
        and isinstance(tb.this, exp.Identifier)
        and tb.this.name.upper() == "TOP"
    ):
        alias = tb.args.get("alias")
        cols = alias.args.get("columns") if alias else None
        if cols:
            try:
                return int(cols[0].name)
            except (ValueError, AttributeError):
                return None
    return None


def _convert_delete_join(
    expr: exp.Delete,
    target: exp.Expression,
    real_tables: list[exp.Expression],
    joins: list[exp.Expression],
    where: ASTNode | None,
    top_limit: LimitClause | None,
) -> ASTNode:
    """Model a multi-table DELETE join (T-SQL/MySQL ``DELETE t FROM t JOIN s``).

    sqlglot keeps the FROM table + its joins in ``this`` and the delete-target
    alias in ``tables``. Unread, the JOIN vanished, leaving the WHERE referencing
    an undefined table (invalid on every target). Model the joined tables via
    ``using`` with the ON conditions folded into WHERE — the ``using`` emitter
    then renders the correct DELETE…FROM…JOIN / USING / EXISTS form per target.
    """
    base_alias = (target.alias or target.name).lower()
    if real_tables:
        _t0 = real_tables[0]
        if (_t0.alias or _t0.name).lower() != base_alias:
            # The delete target is a JOINED table, not the FROM head — rarer and
            # not safely expressible via this rewrite. Degrade whole.
            return RawSQL(
                sql=_source_sql(expr),
                reason="DELETE join whose target is a joined table "
                "preserved as a comment",
            )
    join_tables: list[TableRef] = []
    for j in joins:
        jt = j.this
        if not isinstance(jt, exp.Table):
            return RawSQL(
                sql=_source_sql(expr),
                reason="Unhandled expression type: DELETE join non-table",
            )
        join_tables.append(_convert_table_ref(jt))
        on_expr = j.args.get("on")
        if on_expr is not None:
            on_cond = convert_expression(on_expr)
            where = (
                BinaryOp(operator=BinaryOperator.AND, left=on_cond, right=where)
                if where is not None
                else on_cond
            )
    return DeleteStatement(
        table=_convert_table_ref(target),
        where=where,
        using=tuple(join_tables),
        limit=top_limit,
    )


def _split_delete_top(
    tables_arg: list[exp.Expression],
) -> tuple[LimitClause | None, list[exp.Expression]]:
    """Separate a ``DELETE TOP (n)`` row cap (mis-parsed by sqlglot into
    ``tables``) from the real delete-target-alias list."""
    top_limit: LimitClause | None = None
    real_tables: list[exp.Expression] = []
    for tb in tables_arg:
        n = _delete_top_count(tb)
        if n is not None:
            top_limit = LimitClause(limit=Literal(value=n, dtype="integer"))
        else:
            real_tables.append(tb)
    return top_limit, real_tables


def _read_order_and_limit(
    expr: exp.Update | exp.Delete,
) -> tuple[tuple[OrderByItem, ...], LimitClause | None]:
    """Read a statement's MySQL ``[ORDER BY …] LIMIT n`` cap args (guardrail 7).

    Shared by UPDATE and DELETE: both leave ``order``/``limit`` unread by
    default, and dropping them makes the statement hit EVERY matching row
    instead of the capped first n (data loss). The ORDER BY is only observable
    together with the LIMIT (a full statement's order is unobservable)."""
    order_items: tuple[OrderByItem, ...] = ()
    order_arg = expr.args.get("order")
    if isinstance(order_arg, exp.Order):
        order_items = tuple(
            (
                _convert_ordered(o)
                if isinstance(o, exp.Ordered)
                else OrderByItem(expression=convert_expression(o))
            )
            for o in order_arg.expressions
        )
    limit: LimitClause | None = None
    limit_arg = expr.args.get("limit")
    if isinstance(limit_arg, exp.Limit) and limit_arg.expression is not None:
        limit = LimitClause(limit=convert_expression(limit_arg.expression))
    return order_items, limit


def _delete_order_and_limit(
    expr: exp.Delete, top_limit: LimitClause | None
) -> tuple[tuple[OrderByItem, ...], LimitClause | None]:
    """Read a DELETE's ``ORDER BY`` and ``LIMIT`` args (MySQL ordered cap),
    falling back to any T-SQL ``TOP`` cap already split out."""
    order_items, limit = _read_order_and_limit(expr)
    return order_items, (limit if limit is not None else top_limit)


def _convert_delete(expr: exp.Delete) -> ASTNode:
    """Convert a sqlglot Delete to DeleteStatement."""
    # ``DELETE TOP (n)``: sqlglot lands the row cap in ``tables``; the rest is
    # the multi-table delete's target-alias list.
    top_limit, real_tables = _split_delete_top(list(expr.args.get("tables") or []))

    # Oracle's FROM-less ``DELETE t WHERE …`` parses with the table in
    # ``tables`` and ``this=False`` — reading ``this`` blindly emitted the
    # literal ``DELETE FROM False`` (silent corruption; audit sweep).
    target = expr.this
    if not isinstance(target, exp.Expression):
        if not real_tables:
            raise ValueError("DELETE without a target table")
        target = real_tables[0]

    where = None
    where_expr = expr.args.get("where")
    if where_expr:
        where = convert_expression(where_expr.this)

    # MySQL ``DELETE … [ORDER BY …] LIMIT n``: the cap deletes only n rows (the
    # first n by ORDER BY). Both args were unread — the ORDER BY + LIMIT fell on
    # the floor and the DELETE hit EVERY matching row (data loss). Read them
    # (guardrail 7) and carry the cap; the ORDER BY is only observable with a cap.
    order_items, tail_limit = _delete_order_and_limit(expr, top_limit)

    # Multi-table DELETE with a JOIN (T-SQL/MySQL ``DELETE t FROM t JOIN s ON …``).
    joins = target.args.get("joins") if isinstance(target, exp.Expression) else None
    if joins:
        return _convert_delete_join(expr, target, real_tables, joins, where, top_limit)

    table = _convert_table_ref(target)

    # PG's DELETE … USING sources: sqlglot nests the comma list as the
    # first table's joins. Unread, the whole clause was silently
    # DROPPED, leaving dangling references (wave 196).
    using: list[TableRef] = []
    using_expr = expr.args.get("using")
    # sqlglot stores False (not None) here for plain deletes.
    if using_expr:
        sources = using_expr if isinstance(using_expr, list) else [using_expr]
        for src in sources:
            if not isinstance(src, exp.Table):
                return RawSQL(
                    sql=_source_sql(expr),
                    reason="Unhandled expression type: DELETE USING derived table",
                )
            using.append(_convert_table_ref(src))
            for j in src.args.get("joins") or []:
                jt = j.this
                if not isinstance(jt, exp.Table):
                    return RawSQL(
                        sql=_source_sql(expr),
                        reason="Unhandled expression type: DELETE USING derived table",
                    )
                using.append(_convert_table_ref(jt))

    return DeleteStatement(
        table=table,
        where=where,
        using=tuple(using),
        limit=tail_limit,
        order_by=order_items,
    )


def _normalize_ddl_kind(kind: str) -> str:
    """Canonicalize a DDL object-type keyword.

    T-SQL accepts ``PROC`` as an abbreviation of ``PROCEDURE`` (sqlglot keeps
    the abbreviated spelling verbatim); no other engine does, so the canonical
    form must be emitted regardless of target.
    """
    return "PROCEDURE" if kind == "PROC" else kind


def _convert_create(expr: exp.Create) -> ASTNode:
    """Convert a sqlglot Create to the appropriate IR node."""
    kind = _normalize_ddl_kind((expr.args.get("kind") or "").upper())

    if kind == "TABLE":
        return _convert_create_table(expr)
    if kind == "VIEW":
        return _convert_create_view(expr)

    return RawSQL(sql=_source_sql(expr), reason=f"Unhandled CREATE {kind}")


def _convert_create_table(
    expr: exp.Create, source_dialect: str = "tsql"
) -> CreateTableStatement:
    """Convert CREATE TABLE."""
    table = _convert_table_ref(expr.this)

    columns: list[ColumnDefinition] = []
    constraints: list[PassthroughSQL] = []
    schema_expr = expr.this
    if isinstance(schema_expr, exp.Schema):
        table = _convert_table_ref(schema_expr.this)
        # Structural id-role signals for the bare-Oracle-``NUMBER`` promotion
        # (B47): a column that is (part of) the PRIMARY KEY, is UNIQUE-
        # constrained, or is a FOREIGN KEY / REFERENCES is id-like -> BIGINT;
        # anything else keeps Oracle's arbitrary precision. Table-level keys/FKs
        # are collected here so the per-column decision (taken after that
        # column's own constraints are read) can consult them. PK/UNIQUE reuse
        # the cross-statement harvest; table-level FK local columns come straight
        # off this statement's AST.
        _table_key_cols: set[str] = set()
        for _keytuple in (PK_UNIQUE_COLUMNS.get() or {}).get(table.name.lower(), []):
            _table_key_cols.update(_keytuple)
        _fk_cols: set[str] = set()
        for _fk in expr.find_all(exp.ForeignKey):
            for _c in _fk.expressions:
                _fk_cols.add(str(getattr(_c, "name", _c)).lower())
        for col_def in schema_expr.expressions:
            if (
                isinstance(col_def, exp.ColumnDef)
                and str(getattr(col_def.this, "name", "")).upper() == "INDEX"
                and isinstance(col_def.kind, exp.DataType)
                and col_def.kind.this == exp.DataType.Type.USERDEFINED
            ):
                # T-SQL inline ``INDEX ix (cols)``: sqlglot MISPARSES it as a
                # column named INDEX whose "type" is the index name, with the
                # column list inside a (NON)CLUSTERED constraint. Reconstruct.
                _ix_name = str(col_def.kind.args.get("kind") or "").strip()
                _ix_cols = [
                    c.name
                    for c in col_def.find_all(exp.Column)
                    if isinstance(c.this, exp.Identifier)
                ]
                if _ix_name and _ix_cols:
                    constraints.append(
                        PassthroughSQL(
                            sql=f"{_ix_name}|{', '.join(_ix_cols)}",
                            source_dialect=source_dialect,
                            kind="INLINE_INDEX_COLS",
                        )
                    )
                else:  # unreconstructible — keep the raw fragment as a carrier
                    constraints.append(
                        PassthroughSQL(
                            sql=col_def.sql(
                                dialect=sqlglot_dialect_name(source_dialect)
                            ),
                            source_dialect=source_dialect,
                            kind="INLINE_INDEX",
                        )
                    )
                continue
            if isinstance(col_def, exp.ColumnDef):
                # Computed/generated columns (AS (expr) [PERSISTED/STORED]).
                # A TYPED shorthand (MySQL ``c INT AS (…) STORED``) models as a
                # generated ColumnDefinition, gaining the whole modeled-path
                # machinery (chained-reference inlining, PERSISTED-when-
                # referenced, PG JSON casts). The typeless T-SQL form keeps the
                # passthrough fragment (the target derives the type).
                _comp = next(
                    (
                        c.kind
                        for c in col_def.args.get("constraints", [])
                        if isinstance(
                            getattr(c, "kind", None), exp.ComputedColumnConstraint
                        )
                    ),
                    None,
                )
                if _comp is not None:
                    if col_def.args.get("kind") is not None:
                        _cexpr = _comp.this
                        while isinstance(_cexpr, exp.Paren):
                            _cexpr = _cexpr.this
                        _gen = convert_expression(_cexpr)

                        def _has_unmapped(v: object) -> bool:
                            if isinstance(v, RawSQL):
                                return v.reason.startswith("unmapped operator")
                            if isinstance(v, ASTNode):
                                return any(
                                    _has_unmapped(getattr(v, f.name))
                                    for f in dataclasses.fields(v)
                                )
                            if isinstance(v, tuple):
                                return any(_has_unmapped(x) for x in v)
                            return False

                        if not _has_unmapped(_gen):
                            columns.append(
                                ColumnDefinition(
                                    name=(
                                        col_def.this.name
                                        if hasattr(col_def.this, "name")
                                        else str(col_def.this)
                                    ),
                                    data_type=_resolve_tsql_alias_type(
                                        _convert_data_type(col_def.args["kind"])
                                    ),
                                    nullable=True,
                                    generated_expr=_gen,
                                    generated_stored=bool(_comp.args.get("persisted")),
                                    quoted=_identifier_quoted(col_def.this),
                                )
                            )
                            continue
                        # An unmapped operator in the expression (e.g. ->>)
                        # keeps the passthrough fragment (sqlglot re-renders
                        # it per target) instead of tripping the whole-degrade
                        # gate.
                    constraints.append(
                        PassthroughSQL(
                            sql=col_def.sql(
                                dialect=sqlglot_dialect_name(source_dialect)
                            ),
                            source_dialect=source_dialect,
                            kind="COLUMN",
                        )
                    )
                    continue

                dtype = DataType(name="VARCHAR")
                # Oracle's unqualified NUMBER (no precision/scale) parses to a
                # bare DECIMAL; the id-vs-value decision is deferred until this
                # column's structural role is known (see below). NUMBER(p,s)
                # has params and is never a bare NUMBER.
                is_bare_number = False
                if col_def.args.get("kind"):
                    dtype = _resolve_tsql_alias_type(
                        _convert_data_type(col_def.args["kind"])
                    )
                    is_bare_number = (
                        source_dialect == "oracle"
                        and dtype.name.upper() in ("DECIMAL", "NUMERIC")
                        and not dtype.params
                    )

                nullable = True
                is_fk = False
                identity = False
                identity_seed: int | None = None
                identity_step: int | None = None
                identity_always = False
                generated_expr: ASTNode | None = None
                generated_stored = False
                on_update: str | None = None
                collate: str | None = None
                invisible = False
                primary_key = False
                unique = False
                col_comment: str | None = None
                deferrable: str | None = None
                default: ASTNode | None = None
                for constraint in col_def.args.get("constraints", []):
                    kind = getattr(constraint, "kind", None)
                    if isinstance(kind, exp.NotNullColumnConstraint):
                        # sqlglot uses this for both "NOT NULL" and an
                        # explicit "NULL" (allow_null=True).
                        nullable = bool(getattr(kind, "args", {}).get("allow_null"))
                    elif isinstance(kind, exp.GeneratedAsIdentityColumnConstraint):
                        gen_expr = kind.args.get("expression")
                        if gen_expr is not None:
                            # GENERATED ALWAYS AS (expr) is a COMPUTED column, not
                            # an identity — sqlglot models both with this node.
                            generated_expr = convert_expression(gen_expr)
                            generated_stored = bool(
                                re.search(r"(?i)\bSTORED\b", kind.sql())
                            )
                            continue
                        identity = True
                        identity_always = bool(kind.args.get("this"))
                        # Preserve the seed/step (T-SQL IDENTITY(100, 5), PG
                        # GENERATED … START WITH …) so the sequence doesn't
                        # silently restart at 1 on the target (RC-3).
                        for arg, setter in (("start", "seed"), ("increment", "step")):
                            lit = kind.args.get(arg)
                            if lit is not None:
                                try:
                                    val = int(lit.name)
                                except (ValueError, AttributeError):
                                    continue
                                if setter == "seed":
                                    identity_seed = val
                                else:
                                    identity_step = val
                    elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
                        primary_key = True
                        dm = re.search(
                            r"(?i)\b((?:NOT\s+)?DEFERRABLE"
                            r"(?:\s+INITIALLY\s+(?:DEFERRED|IMMEDIATE))?)",
                            kind.sql(),
                        )
                        if dm:
                            deferrable = dm.group(1)
                    elif isinstance(kind, exp.UniqueColumnConstraint):
                        unique = True
                    elif isinstance(kind, exp.DefaultColumnConstraint):
                        # Convert properly so boolean/function defaults are
                        # re-emitted in the target's own spelling (audit
                        # 2026-07-02, S1-9/S1-10).
                        default = (
                            convert_expression(kind.this, source_dialect)
                            if kind.this
                            else None
                        )
                    elif isinstance(kind, exp.AutoIncrementColumnConstraint):
                        identity = True
                    elif isinstance(kind, exp.CommentColumnConstraint):
                        # Preserve the column comment (RC-3 — was dropped).
                        if kind.this is not None:
                            col_comment = kind.this.sql(
                                dialect=sqlglot_dialect_name(source_dialect)
                            )
                    elif isinstance(kind, exp.OnUpdateColumnConstraint):
                        # MySQL's ON UPDATE CURRENT_TIMESTAMP auto-update — kept
                        # inline on MySQL, carried as a documented note elsewhere.
                        on_update = kind.sql(
                            dialect=sqlglot_dialect_name(source_dialect)
                        )
                    elif isinstance(
                        kind,
                        (
                            exp.CollateColumnConstraint,
                            exp.CharacterSetColumnConstraint,
                        ),
                    ):
                        # A column COLLATE / CHARACTER SET clause — engine-specific
                        # name, kept on the source engine and carried as a warning
                        # elsewhere (no portable mapping).
                        collate = kind.sql(dialect=sqlglot_dialect_name(source_dialect))
                    elif isinstance(kind, exp.InvisibleColumnConstraint):
                        # MySQL/Oracle INVISIBLE column (excluded from SELECT *) —
                        # kept inline on those engines, carried as a documented
                        # note on PG/T-SQL (which have no equivalent).
                        invisible = True
                    elif isinstance(kind, exp.Reference):
                        # Inline column FK (``c INT REFERENCES p(id) ON DELETE …``)
                        # is equivalent to a table-level FOREIGN KEY; route it
                        # there so it emits per-target instead of being silently
                        # dropped (RC-3 — referential integrity). It also marks
                        # the column id-like for the bare-NUMBER promotion (B47).
                        is_fk = True
                        sg = sqlglot_dialect_name(source_dialect)
                        col_ref = col_def.this.sql(dialect=sg)
                        constraints.append(
                            PassthroughSQL(
                                sql=f"FOREIGN KEY ({col_ref}) {kind.sql(dialect=sg)}",
                                source_dialect=source_dialect,
                                kind="CONSTRAINT",
                            )
                        )
                    elif isinstance(kind, exp.CheckColumnConstraint):
                        # Inline column CHECK — keep it as a table-level CHECK
                        # rather than drop the data-integrity rule.
                        constraints.append(
                            PassthroughSQL(
                                sql=kind.sql(
                                    dialect=sqlglot_dialect_name(source_dialect)
                                ),
                                source_dialect=source_dialect,
                                kind="CONSTRAINT",
                            )
                        )

                if is_bare_number:
                    # B47: a bare Oracle NUMBER is promoted to BIGINT only when a
                    # STRUCTURAL signal makes it id-like — it is (part of) the
                    # PRIMARY KEY, is UNIQUE-constrained, is an identity, or is a
                    # FOREIGN KEY / REFERENCES (join compatibility with the
                    # promoted id it points at). Every other bare NUMBER keeps
                    # Oracle's arbitrary precision as unbounded NUMERIC — the
                    # emitter bounds+warns it on MySQL/T-SQL (UNIQUE-1236),
                    # PostgreSQL keeps it unbounded. This avoids silently
                    # truncating a fractional value (``discount_pct NUMBER``) to
                    # an integer. A name like ``x_id`` is NOT a signal.
                    _col_name = (
                        col_def.this.name
                        if hasattr(col_def.this, "name")
                        else str(col_def.this)
                    ).lower()
                    _id_like = (
                        identity
                        or primary_key
                        or unique
                        or is_fk
                        or _col_name in _table_key_cols
                        or _col_name in _fk_cols
                    )
                    dtype = DataType(name="BIGINT" if _id_like else "NUMERIC")

                columns.append(
                    ColumnDefinition(
                        name=(
                            col_def.this.name
                            if hasattr(col_def.this, "name")
                            else str(col_def.this)
                        ),
                        data_type=dtype,
                        nullable=nullable,
                        default=default,
                        identity=identity,
                        identity_seed=identity_seed,
                        identity_step=identity_step,
                        identity_always=identity_always,
                        generated_expr=generated_expr,
                        generated_stored=generated_stored,
                        primary_key=primary_key,
                        unique=unique,
                        comment=col_comment,
                        deferrable=deferrable,
                        on_update=on_update,
                        collate=collate,
                        invisible=invisible,
                        quoted=_identifier_quoted(col_def.this),
                    )
                )
            elif isinstance(col_def, exp.IndexColumnConstraint):
                # An inline INDEX table element (MySQL functional/plain index):
                # keep the fragment so the emitter re-emits it on MySQL and
                # degrades it to a carrier elsewhere (it was dropped SILENTLY).
                constraints.append(
                    PassthroughSQL(
                        sql=col_def.sql(dialect=sqlglot_dialect_name(source_dialect)),
                        source_dialect=source_dialect,
                        kind="INLINE_INDEX",
                    )
                )
            elif isinstance(col_def, exp.ExcludeColumnConstraint):
                # PostgreSQL EXCLUDE is a pg-only exclusion constraint with no
                # equivalent elsewhere; keep it as a fragment (kind tags it so the
                # emitter degrades it to a carrier off PG rather than dropping it).
                constraints.append(
                    PassthroughSQL(
                        sql=col_def.sql(dialect=sqlglot_dialect_name(source_dialect)),
                        source_dialect=source_dialect,
                        kind="EXCLUDE",
                    )
                )
            elif isinstance(
                col_def,
                (
                    exp.Constraint,
                    exp.PrimaryKey,
                    exp.ForeignKey,
                    exp.UniqueColumnConstraint,
                    exp.CheckColumnConstraint,
                ),
            ):
                # Table-level constraint: keep as a passthrough fragment so
                # the emitter can re-transpile it per dialect via sqlglot.
                constraints.append(
                    PassthroughSQL(
                        sql=col_def.sql(dialect=sqlglot_dialect_name(source_dialect)),
                        source_dialect=source_dialect,
                        kind="CONSTRAINT",
                    )
                )

    # sqlglot stores exists=False when IF NOT EXISTS is absent (not None),
    # so "is not None" would wrongly set if_not_exists=True for every table.
    if_not_exists = bool(expr.args.get("exists"))

    # PostgreSQL table-binding clauses (INHERITS / PARTITION OF … FOR
    # VALUES …): keep them verbatim on the node — dropping them loses the
    # table's defining structure (a partition child shipped as a bare
    # column-less CREATE TABLE). The transformer decides per target.
    inherits_clause: str | None = None
    partition_of_clause: str | None = None
    like_source: str | None = None
    unsupported_options: list[str] = []
    table_collate: str | None = None
    table_comment: str | None = None
    sg = sqlglot_dialect_name(source_dialect)
    props = expr.args.get("properties")
    if props is not None:
        for prop in props.expressions:
            if isinstance(prop, exp.InheritsProperty):
                inherits_clause = prop.sql(dialect=sg)
            elif isinstance(prop, exp.PartitionedOfProperty):
                partition_of_clause = prop.sql(dialect=sg)
            elif isinstance(prop, exp.LikeProperty):
                like_source = prop.this.sql(dialect=sg)
            elif isinstance(prop, (exp.CollateProperty, exp.CharacterSetProperty)):
                # MySQL table-level default collation / charset — engine-specific.
                table_collate = prop.sql(dialect=sg)
            elif isinstance(prop, exp.SchemaCommentProperty):
                # MySQL table COMMENT='…' — materialized as COMMENT ON TABLE on
                # PG/Oracle rather than dropped silently.
                table_comment = prop.this.sql(dialect=sg)
            elif re.search(r"(?i)MEMORY_OPTIMIZED|DURABILITY", prop.sql(dialect=sg)):
                # T-SQL In-Memory OLTP storage options — physical only (no
                # logical/value impact) and T-SQL-specific; kept for T-SQL,
                # carried as a note elsewhere (RC-2 — was dropped silently).
                unsupported_options.append(prop.sql(dialect=sg))
    # PG's ``CREATE TABLE x (LIKE y)`` parks the LikeProperty INSIDE the
    # column schema, not in properties; missing it dropped the whole
    # clause and emitted an empty ``CREATE TABLE x`` (silent data loss).
    if like_source is None and isinstance(expr.this, exp.Schema):
        for e in expr.this.expressions:
            if isinstance(e, exp.LikeProperty):
                like_source = e.this.sql(dialect=sg)
                break

    # CREATE TABLE … [AS] SELECT: sqlglot parks the query in
    # ``expression``; never reading it silently dropped the whole CTAS
    # body (MySQL's no-AS spelling included).
    as_select = None
    select_expr = expr.args.get("expression")
    if isinstance(select_expr, (exp.Select, exp.SetOperation)):
        as_select = _convert_select(select_expr)

    # CREATE TEMP[ORARY] TABLE: the property was never read, silently
    # turning a session-scoped table into a permanent one (wave 128).
    temporary = any(
        isinstance(p, exp.TemporaryProperty)
        for p in (expr.args.get("properties") or [])
    )

    return CreateTableStatement(
        table=table,
        columns=tuple(columns),
        if_not_exists=if_not_exists,
        temporary=temporary,
        table_constraints=tuple(constraints),
        inherits_clause=inherits_clause,
        partition_of_clause=partition_of_clause,
        like_source=like_source,
        unsupported_options=tuple(unsupported_options),
        table_collate=table_collate,
        table_comment=table_comment,
        as_select=as_select,
    )


def _convert_create_view(expr: exp.Create) -> CreateViewStatement:
    """Convert CREATE VIEW.

    Reads ``Create.properties`` (guardrail 7): a view carries only non-portable
    single-engine modifiers there (SCHEMABINDING, ALGORITHM=, DEFINER=, SQL
    SECURITY, …). They are collected as ``dropped_modifiers`` so the emitter
    degrades each with a warning instead of dropping it silently. ``WITH CHECK
    OPTION`` is portable and is modelled separately by the pre-parse hook.
    """
    name_expr = expr.this
    table = _convert_table_ref(name_expr)

    query_expr = expr.args.get("expression")
    query = _convert_select(query_expr) if query_expr else SelectStatement()

    props = expr.args.get("properties")
    modifiers: list[str] = []
    if props is not None:
        for prop in props.expressions:
            text = re.sub(r"(?is)^\s*WITH\s+", "", prop.sql()).strip()
            if text:
                modifiers.append(text)

    return CreateViewStatement(
        name=table,
        query=query,
        # DELIBERATE (maintainer decision 2026-07-29): sqlglot stores
        # ``replace=False`` for a plain CREATE VIEW, so this ``is not None``
        # makes EVERY converted view emit CREATE OR REPLACE (OR ALTER on
        # tsql). That is an idempotency feature for migration scripts, not a
        # bug — do not "fix" it to ``bool(...)`` (docs/03-unsupported.md §4,
        # tests/integration/test_create_view_modifiers.py).
        or_replace=expr.args.get("replace") is not None,
        dropped_modifiers=tuple(modifiers),
    )


def _convert_drop(expr: exp.Drop) -> DropStatement:
    """Convert DROP statement."""
    kind = _normalize_ddl_kind((expr.args.get("kind") or "TABLE").upper())
    table = _convert_table_ref(expr.this) if expr.this else TableRef(name="unknown")
    if_exists = expr.args.get("exists") is not None

    # DROP INDEX / DROP TRIGGER: keep the owning table. T-SQL indexes and PG
    # triggers spell it ``ON tbl`` (sqlglot parks it in ``cluster`` as an
    # OnProperty) or, legacy, as the qualifier of a two-part index name
    # (``DROP INDEX tbl.ix``). MySQL DROP INDEX and PG DROP TRIGGER require
    # it; dropping it silently made the statement invalid there (audit B2;
    # wave 109 for triggers).
    on_table: str | None = None
    if kind in ("INDEX", "TRIGGER"):
        cluster = expr.args.get("cluster")
        if cluster is not None and getattr(cluster, "this", None) is not None:
            on_table = str(cluster.this.name or cluster.this)
        elif kind == "INDEX" and table.schema:
            # Two-part legacy form: the "schema" slot is really the table.
            on_table = table.schema
            table = TableRef(name=table.name, quoted=table.quoted)

    return DropStatement(
        object_type=kind,
        name=table,
        if_exists=if_exists,
        on_table=on_table,
    )


_MONEY_MANGLE_RE = re.compile(r"^\$[\d.,]+$")


def _tsql_money_literal_from_column(expr: exp.Column) -> Literal | None:
    """Rebuild a T-SQL money literal (``$12.50``) sqlglot mis-parses as a
    ``table.column`` reference (N8/B9).

    ``$12.50`` parses as ``Column(this=Literal(50), table=Identifier($12))``
    — a bogus column ``50`` of a table ``$12`` — and a bare whole-dollar
    amount (``$100``) as ``Column(this=Identifier($100))`` with no table at
    all. Neither is a real identifier: an unquoted T-SQL identifier cannot
    start with ``$``, and a *quoted* ``"$12"."50"``/``[$12].[50]`` reference
    to real columns parses with quoted ``Identifier`` nodes, never a
    ``Literal``, on the ``this`` side — so gating on ``this`` being an
    unquoted numeric ``Literal`` (dotted form) or an unquoted ``$``-prefixed
    ``Identifier`` (whole-dollar form) never mistakes a genuine identifier
    (e.g. Oracle's ``A$B``, or a bracket-quoted ``[$12abc]``) for a literal.
    Scoped to T-SQL source only, where the money shorthand exists.
    """
    if SOURCE_DIALECT.get() != "tsql":
        return None
    table = expr.args.get("table")
    if (
        table is not None
        and isinstance(expr.this, exp.Literal)
        and not expr.this.is_string
        and not (isinstance(table, exp.Identifier) and table.args.get("quoted"))
        and _MONEY_MANGLE_RE.match(str(table.this))
    ):
        whole = str(table.this)[1:].replace(",", "")
        frac = str(expr.this.this)
        return _convert_literal(exp.Literal(this=f"{whole}.{frac}", is_string=False))
    if (
        table is None
        and isinstance(expr.this, exp.Identifier)
        and not expr.this.args.get("quoted")
        and _MONEY_MANGLE_RE.fullmatch(str(expr.this.this))
    ):
        whole = str(expr.this.this)[1:].replace(",", "")
        return _convert_literal(exp.Literal(this=whole, is_string=False))
    return None


def _convert_sequence_ref(expr: exp.Column) -> FunctionCall | None:
    """Model Oracle ``seq.NEXTVAL`` / ``seq.CURRVAL`` as a sequence FunctionCall.

    sqlglot parses these pseudo-columns as a table-qualified ``Column``
    (``Column(this=NEXTVAL, table=seq)``) — they are not real columns. The
    NEXTVAL form becomes the same ``NEXT_VALUE_FOR`` call the T-SQL ``NEXT VALUE
    FOR seq`` source produces, so the emitter's per-target rendering is shared;
    CURRVAL becomes ``CURRENT_VALUE_FOR``. Oracle-source only (elsewhere
    ``x.nextval`` is an ordinary column), and only the bare ``seq.PSEUDO`` shape
    (no schema/catalog qualifier), matching the former ``map_sequence_refs``
    regex. Modeling this on the AST replaces that post-emit text rewrite, so a
    ``NEXTVAL`` inside a string literal or a column genuinely named ``nextval``
    is no longer mis-rewritten (audit doc 04 F2, guardrail 2).
    """
    if SOURCE_DIALECT.get() != "oracle":
        return None
    if (
        expr.args.get("table") is None
        or expr.args.get("db")
        or expr.args.get("catalog")
    ):
        return None
    fn = {"NEXTVAL": "NEXT_VALUE_FOR", "CURRVAL": "CURRENT_VALUE_FOR"}.get(
        expr.name.upper()
    )
    if fn is None:
        return None
    seq = ColumnRef(name=expr.table, quoted=_identifier_quoted(expr.args.get("table")))
    return FunctionCall(name=fn, args=(seq,))


def _inline_merge_cte(expr: exp.Merge) -> exp.Merge:
    """Inline a leading CTE that feeds a MERGE's USING into a USING subquery.

    ``WITH src AS (<q>) MERGE INTO t USING src ON …`` becomes
    ``MERGE INTO t USING (<q>) src ON …`` and the ``WITH`` is dropped, so the
    source travels with the MERGE (Oracle forbids WITH before MERGE; the MySQL
    upsert rewrite otherwise references an undefined CTE). Only the simple
    ``USING <cte-name>`` shape is inlined; anything else is left untouched.
    """
    merged = expr.copy()
    with_node = merged.args.get("with_") or merged.args.get("with")
    using = merged.args.get("using")
    if with_node is None or not isinstance(using, exp.Table):
        return expr
    ctes = {c.alias: c.this for c in with_node.expressions if isinstance(c, exp.CTE)}
    if using.name not in ctes:
        return expr
    merged.set(
        "using",
        exp.Subquery(
            this=ctes[using.name].copy(),
            alias=exp.TableAlias(this=exp.to_identifier(using.name)),
        ),
    )
    merged.set("with_", None)
    merged.set("with", None)
    return merged


def _convert_oracle_user_pseudo(expr: exp.Column) -> FunctionCall | None:
    """Model Oracle's niladic ``USER`` pseudo-function.

    Oracle ``USER`` returns the current schema/session user; sqlglot parses the
    bare keyword as an ordinary ``Column(Identifier(USER))``, so it leaked as a
    quoted identifier (``"USER"`` / ``[USER]`` / `` `USER` ``) — a column
    reference that does not exist (PG/T-SQL error). ``USER`` is reserved in
    Oracle (a real column of that name must be quoted), so an **unquoted**,
    table-less ``USER`` is always the function. Model it as the same
    ``CURRENT_USER`` FunctionCall Oracle ``CURRENT_USER`` produces, so the
    per-target rendering (PG ``CURRENT_USER`` / MySQL ``CURRENT_USER()`` /
    T-SQL ``CURRENT_USER``) is shared. Oracle-source only.
    """
    if SOURCE_DIALECT.get() != "oracle":
        return None
    if expr.args.get("table") or expr.args.get("db") or expr.args.get("catalog"):
        return None
    if _identifier_quoted(expr.this) or expr.name.upper() != "USER":
        return None
    return FunctionCall(name="CURRENT_USER", args=())


def _convert_column(expr: exp.Column) -> ColumnRef:
    """Convert a column reference."""
    table = None
    if expr.table:
        table = expr.table

    return ColumnRef(
        name=expr.name,
        table=table,
        quoted=_identifier_quoted(expr.this),
        table_quoted=_identifier_quoted(expr.args.get("table")),
    )


def _convert_table(expr: exp.Table) -> TableRef:
    """Convert a table expression."""
    return _convert_table_ref(expr)


def _convert_table_ref(expr: exp.Expression) -> TableRef:
    """Convert any expression to a TableRef."""
    if isinstance(expr, exp.Table):
        alias = None
        alias_expr = expr.args.get("alias")
        if alias_expr:
            alias = (
                alias_expr.this
                if isinstance(alias_expr.this, str)
                else str(alias_expr.this)
            )
        # A set-returning function in relation position — ``FROM fn(args)
        # alias`` parses as Table(this=<func>). Reading only ``.name``
        # dropped the function and promoted the alias to a fake table name
        # (silent data loss, wave 110).
        # (exp.Func is a mixin outside exp.Expression; concrete function
        # nodes inherit both, so the double check also narrows for mypy.)
        if isinstance(expr.this, exp.Func) and isinstance(expr.this, exp.Expression):
            fn_cols: tuple[str, ...] = ()
            if alias_expr is not None:
                fn_cols = tuple(c.name for c in (alias_expr.args.get("columns") or []))
            return TableRef(
                name=alias or expr.name or "",
                alias=alias,
                function=convert_expression(expr.this),
                ordinality=bool(expr.args.get("ordinality")),
                column_aliases=fn_cols,
            )
        # DROP SCHEMA x / USE x parse as a Table with only the db part set;
        # promoting db to name avoids emitting a dangling "x." qualifier.
        if not expr.name and expr.db:
            return TableRef(
                name=expr.db,
                alias=alias,
                quoted=_identifier_quoted(expr.args.get("db")),
            )
        column_aliases: tuple[str, ...] = ()
        if alias_expr is not None:
            column_aliases = tuple(
                c.name for c in (alias_expr.args.get("columns") or [])
            )
        s_method: str | None = None
        s_percent: str | None = None
        s_rows: str | None = None
        sample = expr.args.get("sample")
        if isinstance(sample, exp.TableSample):
            method = sample.args.get("method")
            s_method = method.name.upper() if method is not None else None
            pct = sample.args.get("percent")
            rows = sample.args.get("rows") or sample.args.get("size")
            if pct is not None:
                s_percent = pct.name
            elif rows is not None:
                s_rows = rows.name
        return TableRef(
            name=expr.name,
            schema=expr.db if expr.db else None,
            alias=alias,
            database=(
                expr.catalog if hasattr(expr, "catalog") and expr.catalog else None
            ),
            quoted=_identifier_quoted(expr.this),
            schema_quoted=_identifier_quoted(expr.args.get("db")),
            column_aliases=column_aliases,
            sample_method=s_method,
            sample_percent=s_percent,
            sample_rows=s_rows,
        )
    if isinstance(expr, exp.Schema):
        return _convert_table_ref(expr.this)
    if isinstance(expr, exp.Unnest):
        # ``FROM unnest(arr) AS u(x)`` parses as a bare Unnest relation.
        un_alias_expr = expr.args.get("alias")
        un_alias = un_alias_expr.this.name if un_alias_expr is not None else None
        un_cols: tuple[str, ...] = ()
        if un_alias_expr is not None:
            un_cols = tuple(c.name for c in (un_alias_expr.args.get("columns") or []))
        return TableRef(
            name=un_alias or "unnest",
            alias=un_alias,
            function=FunctionCall(
                name="UNNEST",
                args=tuple(convert_expression(e) for e in expr.expressions),
            ),
            column_aliases=un_cols,
        )
    if hasattr(expr, "name"):
        return TableRef(name=expr.name)
    return TableRef(name=str(expr))


def _maybe_wrap_unpivot(
    src_expr: exp.Expression,
    converted: TableRef | SubqueryExpression,
) -> TableRef | SubqueryExpression | UnpivotRelation | PivotRelation:
    """Wrap the converted FROM source in an ``UnpivotRelation``/``PivotRelation``
    when the source carries an ``UNPIVOT``/``PIVOT`` clause, so the emitter can
    re-spell it natively (T-SQL/Oracle) or rewrite it (MySQL/PG)."""
    pivots = src_expr.args.get("pivots")
    if not pivots:
        return converted
    piv = pivots[0]
    if not piv.args.get("unpivot"):
        # A PIVOT (not UNPIVOT). Model the common single-aggregate / IN-list form
        # so it is never silently dropped (T-SQL/Oracle native, PG/MySQL
        # conditional-aggregation rewrite or a warned degrade).
        aggs = piv.args.get("expressions") or []
        fields = piv.args.get("fields") or []
        if len(aggs) == 1 and fields and isinstance(fields[0], exp.In):
            agg = aggs[0]
            in_expr = fields[0]
            pivot_col = in_expr.this.name if in_expr.this else ""
            values = [c.name for c in in_expr.expressions if c.name]
            agg_arg_expr = agg.this if isinstance(agg, exp.Expression) else None
            if pivot_col and values and agg_arg_expr is not None:
                alias_arg = piv.args.get("alias")
                return PivotRelation(
                    source=converted,
                    agg_func=type(agg).__name__.upper(),
                    agg_arg=convert_expression(agg_arg_expr),
                    pivot_col=pivot_col,
                    values=tuple(values),
                    alias=(alias_arg.name if alias_arg is not None else None) or None,
                )
        return converted
    value_exprs = piv.args.get("expressions") or []
    value_col = value_exprs[0].name if value_exprs else ""
    name_col = ""
    columns: list[str] = []
    fields = piv.args.get("fields") or []
    if fields and isinstance(fields[0], exp.In):
        in_expr = fields[0]
        name_col = in_expr.this.name if in_expr.this else ""
        columns = [c.name for c in in_expr.expressions if c.name]
    alias_arg = piv.args.get("alias")
    alias = alias_arg.name if alias_arg is not None else None
    if not value_col or not name_col or not columns:
        return converted
    return UnpivotRelation(
        source=converted,
        value_col=value_col,
        name_col=name_col,
        columns=tuple(columns),
        alias=alias or None,
        include_nulls=bool(piv.args.get("include_nulls")),
    )


def _convert_table_or_subquery(expr: exp.Expression) -> TableRef | SubqueryExpression:
    """Convert to either TableRef or SubqueryExpression."""
    if isinstance(expr, exp.Subquery):
        inner = expr.this
        if isinstance(inner, (exp.Select, exp.SetOperation)):
            # A derived table's alias (``(SELECT …) t``) must be carried through,
            # or references to it — and the derived table itself on MySQL — break.
            inner_query = _convert_select(inner)
            # Infer the temporal type of each projected column (feature B30) so
            # the outer query can spell ``derived_col ± n`` / ``d2 - d1`` per
            # target. Computed bottom-up: a nested derived table is already
            # converted, so its own ``column_types`` resolve pass-through refs.
            return SubqueryExpression(
                query=inner_query,
                alias=expr.alias or None,
                column_types=tuple(infer_column_types(inner_query).items()),
            )
    if isinstance(expr, exp.Values):
        # A VALUES relation — ``FROM (VALUES (1,'x'),(2,'y')) v(a,b)`` —
        # previously converted to NOTHING (the FROM emitted empty; the
        # gate degraded the batch). Lower it to the UNION ALL chain of
        # row-SELECTs, valid on all four engines (Oracle gets FROM DUAL
        # from the emitter; the alias list names the first arm's columns).
        cols = expr.alias_column_names or []
        selects: list[SelectStatement] = []
        for ri, row in enumerate(expr.expressions):
            cells = getattr(row, "expressions", None) or [row]
            items: list[ASTNode] = []
            for ci, cell in enumerate(cells):
                item = convert_expression(cell)
                if ri == 0 and ci < len(cols):
                    item = Alias(expression=item, name=cols[ci])
                items.append(item)
            selects.append(SelectStatement(columns=tuple(items)))
        query = selects[-1]
        for i in range(len(selects) - 2, -1, -1):
            query = dataclasses.replace(
                selects[i], set_op=SetOperationType.UNION_ALL, set_query=query
            )
        return SubqueryExpression(query=query, alias=expr.alias or None)
    return _convert_table_ref(expr)


def _convert_literal(expr: exp.Literal) -> Literal:
    """Convert a literal value."""
    if expr.is_int:
        return Literal(value=int(expr.this), dtype="integer")
    if expr.is_number:
        text = str(expr.this)
        fval = float(text)
        # A double cannot hold every decimal (``2.9999999999999999`` -> 3.0), so
        # keep the exact source text when the value the float would EMIT
        # (``str(fval)``) differs from the source decimal. Comparing the emitted
        # form (not the float's exact bits) leaves ordinary decimals like ``0.10``
        # untouched — only a genuinely rounded value is preserved.
        raw: str | None = None
        with contextlib.suppress(decimal.InvalidOperation):
            if decimal.Decimal(str(fval)) != decimal.Decimal(text):
                raw = text
        # A trailing-zero scale ('5.50') is numerically equal but display- and
        # (on PG/MySQL) type-significant: 5.50 keeps scale 2 in DECIMAL
        # arithmetic and in ||/CONCAT stringification. Keep the source text.
        if raw is None and re.fullmatch(r"-?\d+\.\d*0", text):
            raw = text
        return Literal(value=fval, dtype="number", raw=raw)
    if expr.is_string:
        return Literal(value=str(expr.this), dtype="string")
    return Literal(value=expr.this, dtype="unknown")


def _convert_alias(expr: exp.Alias) -> Alias:
    """Convert an alias expression."""
    return Alias(
        expression=convert_expression(expr.this),
        name=str(expr.alias),
        quoted=_identifier_quoted(expr.args.get("alias")),
    )


def _convert_qualified_function(expr: exp.Dot) -> FunctionCall | None:
    """Convert a ``schema.func(args)`` Dot into a qualified FunctionCall.

    Returns ``None`` when the Dot is not a function call (e.g. a plain
    ``a.b.c`` column path), so the caller can fall back to the generic handling.
    """
    inner = expr.expression
    if not isinstance(inner, exp.Func):
        return None
    qualifier = expr.this
    qualifier_name = qualifier.name if hasattr(qualifier, "name") else str(qualifier)
    func = _convert_function(cast(exp.Expression, inner))
    return dataclasses.replace(func, name=f"{qualifier_name}.{func.name}")


#: Source-side statistical-aggregate normalization. MySQL's VARIANCE/
#: STDDEV/STD are POPULATION aggregates, but sqlglot canonicalizes the
#: first two to the names the IR treats as SAMPLE semantics — mapping by
#: name alone would silently change the math. T-SQL's VARP/VAR/STDEVP
#: stay Anonymous in sqlglot; canonicalize them so the emitter's
#: per-target map applies uniformly (its STDEV parses to Stddev = sample,
#: which is already correct).
_SOURCE_STAT_NORMALIZATION: dict[str, dict[str, str]] = {
    "mysql": {
        "VARIANCE": "VARIANCE_POP",
        "STDDEV": "STDDEV_POP",
        "STD": "STDDEV_POP",
    },
    "tsql": {
        "VARP": "VARIANCE_POP",
        "VAR": "VARIANCE",
        "STDEVP": "STDDEV_POP",
    },
}


def _normalize_stat_aggregate(name: str) -> str:
    """Return the semantics-true canonical name for the run's source dialect."""
    source = SOURCE_DIALECT.get()
    if source is None:
        return name
    return _SOURCE_STAT_NORMALIZATION.get(source, {}).get(name.upper(), name)


def _convert_function(expr: exp.Expression) -> FunctionCall:
    """Convert a function call."""
    # An aggregate's DISTINCT lives in a wrapper node (Count(this=
    # Distinct(...))); unconverted it became a verbatim RawSQL argument,
    # so the inner expressions bypassed every function mapping
    # (COUNT(DISTINCT REPEAT(65, 3)) shipped REPEAT on T-SQL — wave 161).
    if isinstance(expr.this, exp.Distinct) and not expr.expressions:
        inner = expr.this.expressions
        name = (
            expr.sql_name() if hasattr(expr, "sql_name") else type(expr).__name__
        ).upper()
        return FunctionCall(
            name=_normalize_stat_aggregate(name),
            args=tuple(convert_expression(a) for a in inner),
            distinct=True,
        )
    # StrPosition (T-SQL CHARINDEX, MySQL LOCATE, ...) keeps its arguments in
    # named slots (this=haystack, substr=needle, position=start) rather than in
    # `expressions`, so the generic collection below would drop all but the
    # haystack. Canonicalize to CHARINDEX(needle, haystack[, start]); the emitter
    # renders the right per-dialect function and argument order.
    if isinstance(expr, exp.StrPosition):
        needle = expr.args.get("substr")
        haystack = expr.this
        start = expr.args.get("position")
        occurrence = expr.args.get("occurrence")
        sp_args: list[ASTNode] = []
        if needle is not None:
            sp_args.append(convert_expression(needle))
        if haystack is not None:
            sp_args.append(convert_expression(haystack))
        if start is not None:
            sp_args.append(convert_expression(start))
        if occurrence is not None:
            # Oracle INSTR's 4th argument (the n-th occurrence) — dropping it
            # silently returned the FIRST match. The emitter folds/degrades it.
            if start is None:
                sp_args.append(Literal(value=1, dtype="integer"))
            sp_args.append(convert_expression(occurrence))
        return FunctionCall(name="CHARINDEX", args=tuple(sp_args))

    # sqlglot canonicalizes LPAD/RPAD to one Pad node whose direction lives in
    # the ``is_left`` arg — the generic path would emit a nonexistent PAD().
    # Recover the concrete name; the emitter spells T-SQL's expansion.
    if isinstance(expr, exp.Pad):
        pad_args = [convert_expression(expr.this)]
        if expr.expression is not None:
            pad_args.append(convert_expression(expr.expression))
        fill = expr.args.get("fill_pattern")
        if fill is not None:
            pad_args.append(convert_expression(fill))
        return FunctionCall(
            name="LPAD" if expr.args.get("is_left") else "RPAD",
            args=tuple(pad_args),
        )

    # sqlglot canonicalizes the BIT_AND/BIT_OR/BIT_XOR *aggregates* to
    # BitwiseAndAgg/BitwiseOrAgg/BitwiseXorAgg, whose sql_name() is the internal
    # "BITWISE_AND_AGG" (not a real function). The generic path would emit that
    # and the gate would degrade it even on PostgreSQL/MySQL, which both have
    # these aggregates. Recover the real name; Oracle and T-SQL have no bit
    # aggregate, so the gate degrades those to a documented carrier.
    if isinstance(expr, (exp.BitwiseAndAgg, exp.BitwiseOrAgg, exp.BitwiseXorAgg)):
        bit_name = (
            "BIT_AND"
            if isinstance(expr, exp.BitwiseAndAgg)
            else "BIT_OR" if isinstance(expr, exp.BitwiseOrAgg) else "BIT_XOR"
        )
        return FunctionCall(name=bit_name, args=(convert_expression(expr.this),))

    # JSON aggregates: sqlglot canonicalizes json_agg/JSON_ARRAYAGG to
    # JSONArrayAgg and json_object_agg/JSON_OBJECTAGG to JSONObjectAgg, whose
    # sql_name() is a fake internal "J_S_O_N_ARRAY_AGG"; recover a canonical
    # name (the emitter spells the per-engine form; T-SQL has no JSON aggregate,
    # so the gate degrades that emission — see output_gate._CROSS_ENGINE_AGG).
    if isinstance(expr, exp.JSONArrayAgg):
        return FunctionCall(name="JSON_ARRAYAGG", args=(convert_expression(expr.this),))
    if isinstance(expr, exp.JSONObjectAgg):
        # MySQL wraps the pair in one JSONKeyValue; PostgreSQL keeps two args.
        exprs = expr.expressions
        if len(exprs) == 1 and isinstance(exprs[0], exp.JSONKeyValue):
            key, val = exprs[0].this, exprs[0].expression
        elif len(exprs) >= 2:
            key, val = exprs[0], exprs[1]
        else:
            key = val = None
        if key is not None and val is not None:
            return FunctionCall(
                name="JSON_OBJECTAGG",
                args=(convert_expression(key), convert_expression(val)),
            )

    # JSON_OBJECT(k, v, ...) — a built-in on all four engines but spelled
    # differently (MySQL comma, PG json_build_object, Oracle KEY..VALUE, T-SQL
    # colon). sqlglot parses it to JSONObject with a fake sql_name; flatten the
    # JSONKeyValue pairs to (k, v, k, v, …) and let the emitter render per engine.
    if isinstance(expr, exp.JSONObject):
        jo_args: list[ASTNode] = []
        for kv in expr.expressions:
            if isinstance(kv, exp.JSONKeyValue):
                jo_args.append(convert_expression(kv.this))
                jo_args.append(convert_expression(kv.expression))
            else:
                jo_args.append(convert_expression(kv))
        return FunctionCall(name="JSON_OBJECT", args=tuple(jo_args))

    # PostgreSQL date_trunc('unit', ts) parses to TimestampTrunc/DateTrunc whose
    # sql_name() is the internal "TIMESTAMP_TRUNC" (no engine has it).
    # Canonicalize to the DATE_TRUNC FunctionCall the emitter already maps per
    # engine (Oracle TRUNC, T-SQL DATETRUNC, MySQL DATE_FORMAT); an unmapped unit
    # (e.g. 'decade') falls through there and degrades via the gate.
    if isinstance(expr, (exp.TimestampTrunc, exp.DateTrunc)):
        unit = expr.args.get("unit")
        if unit is not None:
            return FunctionCall(
                name="DATE_TRUNC",
                args=(
                    RawSQL(sql=unit.name.upper(), reason="date_trunc unit"),
                    convert_expression(expr.this),
                ),
            )

    # exp.Anonymous is an unrecognized function: its real name is in `this`
    # (a string), not in sql_name() which returns "ANONYMOUS". Its arguments
    # live in `expressions`.
    if isinstance(expr, exp.Anonymous):
        # MySQL's ADDDATE/SUBDATE are DATE_ADD/DATE_SUB aliases sqlglot
        # leaves anonymous — they shipped dbo.-qualified as fake UDFs
        # with a raw INTERVAL argument (wave 162). Canonicalize to the
        # 3-argument (ts, n, unit) form the date-add emitter renders.
        anon_name = str(expr.name).upper()
        if (
            SOURCE_DIALECT.get() in ("postgresql",)
            and anon_name in ("NEXTVAL", "CURRVAL")
            and len(expr.expressions) == 1
            and isinstance(expr.expressions[0], exp.Literal)
            and expr.expressions[0].is_string
        ):
            # PG ``nextval('seq')`` / ``currval('seq')`` — model as the shared
            # sequence call the T-SQL (``NEXT VALUE FOR seq``) and Oracle
            # (``seq.NEXTVAL``) sources already produce, symmetric with the
            # reverse directions (the emitter renders each per target; MySQL,
            # which has no sequences, degrades honestly). The regclass argument
            # is a bare sequence name.
            seq_name = str(expr.expressions[0].this)
            fn = "NEXT_VALUE_FOR" if anon_name == "NEXTVAL" else "CURRENT_VALUE_FOR"
            return FunctionCall(name=fn, args=(ColumnRef(name=seq_name),))
        if anon_name in ("ADDDATE", "SUBDATE") and len(expr.expressions) == 2:
            canonical = "DATE_ADD" if anon_name == "ADDDATE" else "DATE_SUB"
            ts, amount = expr.expressions
            if isinstance(amount, exp.Interval):
                n = convert_expression(amount.this)
                unit = convert_expression(amount.args["unit"])
            else:
                # Bare-number second argument counts days.
                n = convert_expression(amount)
                unit = RawSQL(sql="DAY", reason="implicit ADDDATE unit")
            return FunctionCall(name=canonical, args=(convert_expression(ts), n, unit))
        return FunctionCall(
            name=_normalize_stat_aggregate(str(expr.name)),
            args=tuple(convert_expression(a) for a in expr.expressions),
        )

    name = expr.sql_name() if hasattr(expr, "sql_name") else type(expr).__name__.upper()
    name = _normalize_stat_aggregate(name)
    # sqlglot's postgres reader models FROM-position generate_series as an
    # internal "exploding" node whose sql_name is not a real function.
    if isinstance(expr, (exp.GenerateSeries, exp.ExplodingGenerateSeries)):
        name = "GENERATE_SERIES"

    # Generic argument collection. sqlglot models most specialized functions
    # with their arguments in *named slots* (Substring -> this/start/length,
    # Replace -> this/expression/replacement, Round -> this/decimals,
    # DateAdd -> this/expression/unit, ...), not in `expressions`. The previous
    # heuristic only read `this` + `expressions`, so every named slot was
    # dropped (SUBSTRING(a,1,3) became SUBSTR(a)). Collect the scalar arguments
    # in declaration order from `arg_types`, which preserves them all.
    if expr.expressions:
        # Variadic functions (COALESCE, CONCAT, ...) keep their args in
        # `expressions`, with an optional leading `this`.
        args = []
        if expr.this is not None and not isinstance(expr.this, (bool, str)):
            args.append(convert_expression(expr.this))
        for arg in expr.expressions:
            args.append(convert_expression(arg))
        return FunctionCall(name=name, args=tuple(args))

    ordered: list[ASTNode] = []
    for slot in expr.arg_types:
        value = expr.args.get(slot)
        # Skip boolean flags (e.g. Round.truncate, Substring.zero_start) and
        # non-expression metadata; keep only actual argument expressions.
        if isinstance(value, exp.Expression) and not isinstance(
            expr, (exp.Column, exp.Table)
        ):
            ordered.append(convert_expression(value))
    if ordered:
        return FunctionCall(name=name, args=tuple(ordered))

    # No-argument function (e.g. GETUTCDATE(), NEWID()): single `this` if any,
    # otherwise an empty argument list.
    args = []
    if (
        expr.this is not None
        and not isinstance(expr, (exp.Column, exp.Table, exp.Anonymous))
        and isinstance(expr.this, exp.Expression)
    ):
        args.append(convert_expression(expr.this))
    return FunctionCall(name=name, args=tuple(args))


def _convert_in(expr: exp.In) -> ASTNode | None:
    """Convert ``x IN (subquery)`` / ``x IN (a, b, …)`` to a BinaryOp.

    Returns None for the exotic forms (UNNEST, field access) so the caller
    falls through to the RawSQL fallback.
    """
    left = convert_expression(expr.this)
    query = expr.args.get("query")
    if isinstance(query, exp.Subquery) and isinstance(
        query.this, (exp.Select, exp.SetOperation)
    ):
        return BinaryOp(
            operator=BinaryOperator.IN,
            left=left,
            right=SubqueryExpression(query=_convert_select(query.this)),
        )
    if expr.expressions:
        return BinaryOp(
            operator=BinaryOperator.IN,
            left=left,
            right=ExpressionList(
                items=tuple(convert_expression(e) for e in expr.expressions)
            ),
        )
    return None


def _rebase_to_days(expr: exp.Add) -> ASTNode | None:
    """Rebase sqlglot's ``TO_DAYS(x)`` expansion off the invalid year-0000 epoch.

    MySQL ``TO_DAYS(x)`` lowers to ``DATEDIFF(x, DATE '0000-01-01', DAY) + 1``,
    but year 0000 is rejected by every other engine (and pre-1582 dates put
    Oracle on the Julian calendar, off by 2 days). Re-express it against a
    post-Gregorian-reform epoch that all engines compute identically:
    ``DATEDIFF(x, DATE '1970-01-01', DAY) + 719528`` (``TO_DAYS('1970-01-01')``
    = 719528). Returns None when ``expr`` is not the TO_DAYS shape."""
    if not isinstance(expr.this, exp.DateDiff):
        return None
    base = expr.this.expression
    base_lit = base.this if isinstance(base, exp.TsOrDsToDate) else base
    off = expr.expression
    if not (
        isinstance(base_lit, exp.Literal)
        and str(base_lit.this) == "0000-01-01"
        and isinstance(off, exp.Literal)
        and str(off.this) == "1"
    ):
        return None
    rebased = expr.copy()
    new_base = rebased.this.expression
    new_base_lit = new_base.this if isinstance(new_base, exp.TsOrDsToDate) else new_base
    new_base_lit.set("this", "1970-01-01")
    rebased.expression.set("this", "719528")
    # The copy no longer matches the 0000 shape, so this does not recurse.
    return convert_expression(rebased)


#: sqlglot binary-operator nodes every engine expresses as a portable call —
#: modeled as a ``FunctionCall`` so the emitter renders the per-target form
#: rather than degrading the whole statement as an "unmapped operator". The IR
#: function name is the value; a 3rd tuple element is an extra literal argument.
_BINARY_AS_CALL: dict[type, tuple[str, str | None]] = {
    exp.Pow: ("POWER", None),
    exp.RegexpLike: ("REGEXP_LIKE", None),
    exp.RegexpILike: ("REGEXP_LIKE", "i"),  # PG ``~*`` case-insensitive
    exp.JSONExtractScalar: ("JSON_EXTRACT_SCALAR", None),
    exp.JSONExtract: ("JSON_EXTRACT", None),
    exp.IntDiv: ("INT_DIV", None),
}


def _convert_binary_as_call(expr: exp.Binary) -> FunctionCall | None:
    """Model a portable binary operator as a ``FunctionCall``, or None.

    POWER, POSIX regex (case-sensitive and ``~*`` case-insensitive), scalar and
    object JSON extract, and integer division all have a per-target form the
    emitter renders (the reverse directions already map them) — so they are
    modeled as calls instead of degrading as an unmapped operator.
    ``exp.JSONExtractScalar`` must be checked before ``exp.JSONExtract`` (its
    superclass); ``dict`` lookup on the exact type avoids that ordering hazard.
    """
    spec = _BINARY_AS_CALL.get(type(expr))
    if spec is None:
        return None
    name, extra = spec
    args: list[ASTNode] = [
        convert_expression(expr.this),
        convert_expression(expr.expression),
    ]
    if extra is not None:
        args.append(Literal(value=extra, dtype="string"))
    return FunctionCall(name=name, args=tuple(args))


def _convert_binary(expr: exp.Binary) -> ASTNode:
    """Convert a binary operation.

    A binary operator that is not in the map is *not* silently coerced to ``=``
    (a dangerous default that would change semantics — e.g. bitwise ``&`` became
    ``=``). Instead the original expression is preserved as ``RawSQL`` so the
    emitter re-renders it via sqlglot, which knows the per-dialect spelling.
    """
    call = _convert_binary_as_call(expr)
    if call is not None:
        return call
    if isinstance(expr, exp.Escape):
        # ``LIKE p ESCAPE c`` — SQL-standard, supported identically on every
        # engine. Carry the escape char on the inner LIKE/ILIKE BinaryOp instead
        # of degrading the whole statement as an unmapped operator.
        inner = convert_expression(expr.this)
        if isinstance(inner, BinaryOp) and inner.operator in (
            BinaryOperator.LIKE,
            BinaryOperator.ILIKE,
        ):
            return dataclasses.replace(
                inner, escape=convert_expression(expr.expression)
            )
        return RawSQL(
            sql=_source_sql(expr), reason=f"unmapped operator {type(expr).__name__}"
        )
    if isinstance(expr, exp.Is) and expr.args.get("negate"):
        # sqlglot 30.12+ folds ``IS NOT NULL`` into ``Is(negate=True)``
        # (≤30.11 wraps in Not, which the unary path converts). Reproduce
        # that shape — NOT over the plain IS — so the polarity survives;
        # dropping the arg inverted the predicate (upgrade prep 2026-07-30).
        return UnaryOp(
            operator=UnaryOperator.NOT,
            operand=BinaryOp(
                operator=BinaryOperator.IS,
                left=convert_expression(expr.this),
                right=convert_expression(expr.expression),
            ),
        )
    op_map: dict[type, BinaryOperator] = {
        exp.EQ: BinaryOperator.EQ,
        exp.NEQ: BinaryOperator.NEQ,
        exp.LT: BinaryOperator.LT,
        exp.GT: BinaryOperator.GT,
        exp.LTE: BinaryOperator.LTE,
        exp.GTE: BinaryOperator.GTE,
        exp.And: BinaryOperator.AND,
        exp.Or: BinaryOperator.OR,
        exp.Add: BinaryOperator.ADD,
        exp.Sub: BinaryOperator.SUB,
        exp.Mul: BinaryOperator.MUL,
        exp.Div: BinaryOperator.DIV,
        exp.Mod: BinaryOperator.MOD,
        exp.Like: BinaryOperator.LIKE,
        exp.ILike: BinaryOperator.ILIKE,
        exp.DPipe: BinaryOperator.CONCAT,
        exp.BitwiseAnd: BinaryOperator.BIT_AND,
        exp.BitwiseOr: BinaryOperator.BIT_OR,
        exp.BitwiseXor: BinaryOperator.BIT_XOR,
        exp.BitwiseLeftShift: BinaryOperator.BIT_LSHIFT,
        exp.BitwiseRightShift: BinaryOperator.BIT_RSHIFT,
        exp.NullSafeEQ: BinaryOperator.NULLSAFE_EQ,
        exp.NullSafeNEQ: BinaryOperator.NULLSAFE_NEQ,
        exp.Is: BinaryOperator.IS,
    }

    operator = op_map.get(type(expr))
    if operator is None:
        # Unknown operator: preserve verbatim rather than corrupt it to "=".
        return RawSQL(
            sql=_source_sql(expr), reason=f"unmapped operator {type(expr).__name__}"
        )

    # MySQL ``/`` is NULL-safe division (``1/0`` → NULL, not an error);
    # sqlglot flags it ``Div.safe``. Read it (guardrail 7 — else the tripwire
    # false-fires, challenge audit) and carry it so the emitter preserves the
    # semantics into non-safe targets (PG/T-SQL/Oracle) via NULLIF.
    safe = bool(expr.args.get("safe")) if isinstance(expr, exp.Div) else False

    return BinaryOp(
        operator=operator,
        left=convert_expression(expr.this),
        right=convert_expression(expr.expression),
        safe=safe,
    )


def _convert_is(expr: exp.Is) -> UnaryOp:
    """Convert IS NULL / IS NOT NULL.

    sqlglot ≤30.11 models ``IS NOT NULL`` as ``Not(Is(…))``; 30.12+ folds the
    negation into ``Is(…, negate=True)``. The arg must be read (guardrail:
    never assume the wrapper) — dropping it silently INVERTS the predicate
    (a pg-source ``DELETE … WHERE a IS NOT NULL`` shipped as ``IS NULL``;
    upgrade prep 2026-07-30)."""
    negated = bool(expr.args.get("negate"))
    if isinstance(expr.expression, exp.Null):
        return UnaryOp(
            operator=(UnaryOperator.IS_NOT_NULL if negated else UnaryOperator.IS_NULL),
            operand=convert_expression(expr.this),
        )
    return UnaryOp(
        operator=UnaryOperator.IS_NOT_NULL,
        operand=convert_expression(expr.this),
    )


def _convert_case(expr: exp.Case) -> CaseExpression:
    """Convert a CASE expression."""
    operand = None
    if expr.this:
        operand = convert_expression(expr.this)

    whens: list[tuple[ASTNode, ASTNode]] = []
    for ifs in expr.args.get("ifs", []):
        condition = convert_expression(ifs.this)
        result = convert_expression(ifs.args.get("true"))
        whens.append((condition, result))

    else_expr = None
    default = expr.args.get("default")
    if default:
        else_expr = convert_expression(default)

    return CaseExpression(
        operand=operand,
        whens=tuple(whens),
        else_expr=else_expr,
    )


def _convert_cast(expr: exp.Cast) -> CastExpression:
    """Convert a CAST expression."""
    inner = convert_expression(expr.this)
    target_type = _convert_data_type(expr.to)
    # Oracle ``CAST(x AS T DEFAULT d ON CONVERSION ERROR)`` — sqlglot keeps the
    # fallback on the ``default`` arg (a non-NULL default; ``DEFAULT NULL`` maps
    # to ``safe``). Capture it so the fallback isn't silently dropped.
    default = expr.args.get("default")
    return CastExpression(
        expression=inner,
        target_type=target_type,
        safe=bool(expr.args.get("safe")),
        on_error_default=convert_expression(default) if default is not None else None,
    )


def _convert_data_type(expr: exp.Expression) -> DataType:
    """Convert a sqlglot data type expression to our DataType."""
    if isinstance(expr, exp.DataType):
        name = expr.this.value if hasattr(expr.this, "value") else str(expr.this)
        # User-defined / domain types (e.g. T-SQL [dbo].[Name]) carry their
        # real name in the 'kind' arg; sqlglot's 'this' is just USER-DEFINED.
        if name == "USER-DEFINED" and expr.args.get("kind") is not None:
            kind = expr.args["kind"]
            name = kind.sql() if hasattr(kind, "sql") else str(kind)
        # ENUM/SET carry string values, not numeric length params; keep them
        # so the emitter can render the type faithfully (MySQL) or as
        # VARCHAR + CHECK (everything else).
        if name.upper() in ("ENUM", "SET"):
            values = tuple(
                str(p.this)
                for p in expr.expressions
                if isinstance(p, exp.Literal) and p.is_string
            )
            return DataType(name=name.upper(), values=values)
        # MySQL ``CAST(x AS CHAR CHARACTER SET cs)``: sqlglot collapses
        # the whole type to CHARACTER_SET (the CHAR base is implied —
        # only CHAR/NCHAR take a charset). It emitted a nonexistent
        # ``CAST(… AS CHARACTER_SET)`` everywhere (wave 163). Keep the
        # full MySQL spelling; non-MySQL targets strip the suffix.
        if name.upper() == "CHARACTER_SET":
            kind = expr.args.get("kind")
            cs = str(kind) if kind is not None else ""
            return DataType(name=f"CHAR CHARACTER SET {cs}".strip() if cs else "CHAR")
        # A PG array type (``float8[]``): sqlglot models it as an ARRAY
        # DataType nesting the element type. Collapsing to a bare "ARRAY"
        # loses the element type and emits invalid ``CAST(… AS ARRAY)``
        # even on PG. Keep the source spelling; non-PG targets degrade
        # the whole statement (the array gate).
        if name.upper() == "ARRAY":
            return DataType(name=expr.sql(dialect="postgres"))
        params: list[int] = []
        for p in expr.expressions:
            if isinstance(p, exp.DataTypeParam):
                if p.this and hasattr(p.this, "this"):
                    with contextlib.suppress(ValueError, TypeError):
                        params.append(int(p.this.this))
            elif isinstance(p, exp.Literal) and p.is_int:
                params.append(int(p.this))
        return DataType(name=name, params=tuple(params))
    return DataType(name=str(expr))


def _convert_join(expr: exp.Join) -> JoinClause:
    """Convert a JOIN expression."""
    # Determine join type
    join_kind = expr.side or ""
    join_type_str = f"{join_kind} JOIN".strip().upper()
    if expr.args.get("kind"):
        join_type_str = f"{join_kind} {expr.args['kind']} JOIN".strip().upper()

    join_type = _JOIN_TYPE_MAP.get(join_type_str, JoinType.INNER)

    table_expr = expr.this
    # A LATERAL subquery would fall through to an EMPTY TableRef, dropping
    # the joined relation entirely; unwrap it and mark the JoinClause.
    lateral = isinstance(table_expr, exp.Lateral)
    if lateral:
        lat_alias = table_expr.alias or None
        lat_inner = table_expr.this
        if isinstance(lat_inner, exp.Subquery):
            lat_alias = lat_alias or lat_inner.alias or None
            lat_inner = lat_inner.unnest()
        return JoinClause(
            join_type=_JOIN_TYPE_MAP.get(join_type_str, JoinType.INNER),
            table=SubqueryExpression(query=_convert_select(lat_inner), alias=lat_alias),
            alias=lat_alias,
            condition=(
                convert_expression(expr.args["on"]) if expr.args.get("on") else None
            ),
            lateral=True,
        )
    # A joined derived table (``… JOIN (SELECT …) b ON …``) is a Subquery, not a
    # Table; _convert_table_ref would flatten it to an empty TableRef, dropping
    # the whole joined relation.
    table = _convert_table_or_subquery(table_expr)

    alias = None
    if isinstance(table_expr, exp.Table):
        alias_expr = table_expr.args.get("alias")
        if alias_expr:
            alias = str(alias_expr.this)
    elif isinstance(table_expr, exp.Subquery):
        alias = table_expr.alias or None

    condition = None
    on_expr = expr.args.get("on")
    if on_expr:
        condition = convert_expression(on_expr)

    using = tuple(ident.name for ident in (expr.args.get("using") or []))

    return JoinClause(
        join_type=join_type,
        table=table,
        alias=alias,
        condition=condition,
        using=using,
        natural=(expr.args.get("method") or "").upper() == "NATURAL",
    )


def _convert_window(expr: exp.Window) -> WindowFunction:
    """Convert a window function expression."""
    func_expr = expr.this
    function = convert_expression(func_expr)
    if not isinstance(function, FunctionCall):
        function = FunctionCall(name=str(func_expr), args=())

    partition_by: tuple[ASTNode, ...] = ()
    order_by: tuple[OrderByItem, ...] = ()

    partition = expr.args.get("partition_by")
    if partition:
        partition_by = tuple(convert_expression(p) for p in partition)

    order = expr.args.get("order")
    if order:
        order_by = tuple(
            (
                _convert_ordered(o)
                if isinstance(o, exp.Ordered)
                else OrderByItem(expression=convert_expression(o))
            )
            for o in (order.expressions if hasattr(order, "expressions") else [order])
        )

    # The frame (ROWS/RANGE BETWEEN …) is standard SQL on every target; capture
    # it verbatim rather than dropping it (which silently turns a running total
    # into a grand total).
    spec = expr.args.get("spec")
    # ``spec.sql()`` (generic dialect) omits the frame's EXCLUDE clause, so
    # capture it separately — only PG/Oracle can re-emit it (the emitter
    # degrades T-SQL/MySQL, which have no equivalent).
    frame = spec.sql() if isinstance(spec, exp.WindowSpec) else None
    exclude = None
    if isinstance(spec, exp.WindowSpec) and spec.args.get("exclude") is not None:
        exclude = f"EXCLUDE {spec.args['exclude'].this}"

    window_spec = WindowSpec(
        partition_by=partition_by, order_by=order_by, frame=frame, exclude=exclude
    )
    return WindowFunction(function=function, window=window_spec)


def _convert_ordered(expr: exp.Ordered) -> OrderByItem:
    """Convert an ORDER BY item.

    sqlglot records the *source* NULL-ordering semantics in ``nulls_first``
    (T-SQL/MySQL sort NULLs low, PostgreSQL/Oracle high), so carrying it lets
    the emitter preserve the source's row order on targets whose default
    differs.
    """
    inner = convert_expression(expr.this)
    desc = expr.args.get("desc")
    direction = OrderDirection.DESC if desc else OrderDirection.ASC
    nulls_first = expr.args.get("nulls_first")
    return OrderByItem(
        expression=inner,
        direction=direction,
        nulls_first=nulls_first if isinstance(nulls_first, bool) else None,
    )


def _convert_cte(expr: exp.CTE, recursive: bool = False) -> CTEDefinition:
    """Convert a CTE definition.

    RECURSIVE and the column list (``x(a)``) were silently dropped, and a
    VALUES body mangled into a one-row SELECT (wave 127)."""
    name = expr.alias if isinstance(expr.alias, str) else str(expr.alias)
    alias_expr = expr.args.get("alias")
    columns: tuple[str, ...] = ()
    if alias_expr is not None:
        columns = tuple(c.name for c in (alias_expr.args.get("columns") or []))

    query_expr = expr.this
    body = query_expr
    if isinstance(body, exp.Paren):
        body = body.this
    if isinstance(body, exp.Values):
        converted = _convert_table_or_subquery(body)
        query = (
            converted.query
            if isinstance(converted, SubqueryExpression)
            else SelectStatement()
        )
    elif query_expr is not None:
        query = _convert_select(query_expr)
    else:
        query = SelectStatement()

    # A CTE whose body references its own name is recursive even when the source
    # omits the RECURSIVE keyword (T-SQL and Oracle infer it); PostgreSQL and
    # MySQL REQUIRE it, so detect the self-reference rather than lose it.
    if not recursive and query_expr is not None:
        recursive = any(
            (t.name or "").lower() == name.lower()
            for t in query_expr.find_all(exp.Table)
        )

    return CTEDefinition(name=name, query=query, columns=columns, recursive=recursive)
