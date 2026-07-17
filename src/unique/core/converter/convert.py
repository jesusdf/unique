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
import re
from typing import cast

import sqlglot
import sqlglot.expressions as exp
from sqlglot import transforms

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
    ExpressionList,
    FunctionCall,
    InsertStatement,
    JoinClause,
    JoinType,
    LimitClause,
    Literal,
    OrderByItem,
    OrderDirection,
    PassthroughSQL,
    RawSQL,
    SelectStatement,
    SetOperationType,
    Star,
    SubqueryExpression,
    TableRef,
    UnaryOp,
    UnaryOperator,
    UpdateStatement,
    WindowFunction,
    WindowSpec,
)

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter.harvest import _resolve_tsql_alias_type  # noqa: F401
from unique.core.sql_split import split_leading_trivia

_INSERT_COLS_RE = re.compile(
    r"(?is)\b(INSERT\s+(?:IGNORE\s+)?INTO\s+`?(\w+)`?\s*\()([^)]*)(\))"
)


def _strip_insert_column_qualifiers(sql: str) -> str:
    """Drop redundant ``tbl.`` prefixes inside an INSERT's column list.

    The list region is an identifier list (no string literals can
    legally appear there), so the scoped substitution is safe."""

    def _fix(m: re.Match[str]) -> str:
        table = m.group(2)
        cols = re.sub(rf"(?i)\b{re.escape(table)}\s*\.\s*", "", m.group(3))
        return f"{m.group(1)}{cols}{m.group(4)}"

    return _INSERT_COLS_RE.sub(_fix, sql)


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
    if dialect == "mysql":
        # MySQL's ``INSERT INTO t SET a = 1, b = 2`` form: sqlglot cannot
        # parse it at all, and the embedded-routine fallback DROPPED the
        # SET clause (``INSERT INTO t3;`` — silent loss, wave 168).
        # Rewrite to the universal column-list VALUES form.
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
                verb = (
                    "REPLACE INTO"
                    if ins.group(1).upper().startswith("REPLACE")
                    else "INSERT INTO"
                )
                sql = (
                    f"{verb} {ins.group(2)} ({', '.join(cols)}) "
                    f"VALUES ({', '.join(vals)})"
                )
    if dialect == "postgresql":
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

        # scrub() empties string contents, so on scrubbed text the
        # signature is a colon directly before a string start (a PG cast
        # is ``::type`` — excluded by the lookbehind).
        if re.search(r"(?<!:):\s*''", scrub(sql)):
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
        logger.warning("sqlglot parse error: %s", e)
        return [RawSQL(sql=sql, reason=str(e))]

    nodes: list[ASTNode] = []
    for expression in parsed:
        # An empty statement — a stray/leading ``;`` (e.g. the mandatory one in
        # T-SQL's ``;WITH``). sqlglot yields None for it, or an exp.Semicolon when a
        # comment precedes it; both are no-ops, not an "unhandled" construct.
        if expression is None or isinstance(expression, exp.Semicolon):
            continue
        # Preserve the statement's leading comments (sqlglot attaches them to the
        # expression); our IR conversion would otherwise drop them. Re-emit them
        # as CommentStatements just before the statement, and clear them so a
        # PassthroughSQL ``.sql()`` doesn't also render them.
        leading = getattr(expression, "comments", None)
        if leading:
            for raw in leading:
                text = (raw or "").strip()
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
        nodes.append(node)
        # Trailing / inline comments attach to child nodes, not the statement;
        # collect them so they aren't lost (re-emitted after the statement —
        # position may shift slightly, but nothing is dropped).
        for sub in expression.walk():
            if sub is expression or not sub.comments:
                continue
            for raw in sub.comments:
                text = (raw or "").strip()
                if text:
                    nodes.append(CommentStatement(text=f"-- {text}", style="line"))

    return nodes


def _styled_convert_is_modeled(c: exp.Convert) -> bool:
    """Whether a styled CONVERT converts structurally (known date style, or
    the hash-stringify wrapper whose target functions already return hex)."""
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
    if isinstance(expr, exp.Set):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="SET",
        )
    if isinstance(expr, exp.Merge):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="MERGE",
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
    # Transaction/DDL control (COMMIT / ROLLBACK / TRUNCATE) is valid on every
    # target — a data-migration dump is full of these — so re-transpile it via
    # the passthrough path instead of degrading each to an "Unhandled" carrier.
    if isinstance(expr, (exp.Commit, exp.Rollback, exp.TruncateTable)):
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="statement",
        )
    return _convert_expression_impl(expr)


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


def _convert_select(expr: exp.Expression) -> SelectStatement:
    """Convert a sqlglot Select expression to a SelectStatement IR node."""
    # Handle Union by extracting the left Select
    if isinstance(expr, exp.SetOperation):
        return _convert_union(expr)

    columns = tuple(convert_expression(col) for col in (expr.expressions or []))

    # FROM — use the direct arg, not find(), which recurses into a subquery in
    # the WHERE (e.g. NOT EXISTS (SELECT … FROM t)) and would pull that table
    # into this SELECT's FROM. sqlglot keys it "from_" (older versions "from").
    from_clause: TableRef | SubqueryExpression | None = None
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

    # GROUP BY
    group_by_expr = expr.args.get("group")
    group_by = tuple(
        convert_expression(g)
        for g in (group_by_expr.expressions if group_by_expr else [])
    )

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
        limit_count = None
        if limit_expr is not None:
            opts = limit_expr.args.get("limit_options")
            percent = bool(opts and opts.args.get("percent"))
            count_node = limit_expr.args.get("count") or limit_expr.expression
            limit_count = convert_expression(count_node) if count_node else None
        limit = LimitClause(
            limit=limit_count,
            offset=convert_expression(offset_expr.expression) if offset_expr else None,
            percent=percent,
        )

    # DISTINCT
    distinct = expr.args.get("distinct") is not None

    # CTEs
    ctes: tuple[CTEDefinition, ...] = ()
    with_clause = expr.args.get("with") or expr.args.get("with_")
    if with_clause:
        rec = bool(with_clause.args.get("recursive"))
        ctes = tuple(_convert_cte(c, recursive=rec) for c in with_clause.expressions)

    return SelectStatement(
        columns=columns,
        from_clause=from_clause,
        joins=joins,
        where=where,
        group_by=group_by,
        having=having,
        order_by=order_by,
        limit=limit,
        distinct=distinct,
        ctes=ctes,
        # A genuinely-empty source select list (PG ``SELECT;``) must not
        # gain a ``*`` (wave 124) — flagged so the emitter distinguishes
        # it from fallback-built empty tuples where ``*`` is load-bearing.
        empty_select_list=not (expr.expressions or []),
    )


def _set_op_type(node: exp.SetOperation) -> SetOperationType:
    if isinstance(node, exp.Intersect):
        return SetOperationType.INTERSECT
    if isinstance(node, exp.Except):
        return SetOperationType.EXCEPT
    if node.args.get("distinct") is False:
        return SetOperationType.UNION_ALL
    return SetOperationType.UNION


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

    return InsertStatement(
        table=table,
        columns=columns,
        values=values,
        select=select,
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

    where = None
    # Direct arg, not find(): find() would descend into a subquery in SET/FROM
    # and lift ITS where onto this UPDATE (same class as the SELECT bug).
    where_expr = expr.args.get("where")
    if where_expr:
        where = convert_expression(where_expr.this)

    return UpdateStatement(
        table=table,
        assignments=tuple(assignments),
        where=where,
        from_clause=from_clause,
        joins=tuple(joins),
    )


def _convert_delete(expr: exp.Delete) -> ASTNode:
    """Convert a sqlglot Delete to DeleteStatement."""
    # Oracle's FROM-less ``DELETE t WHERE …`` parses with the table in
    # ``tables`` and ``this=False`` — reading ``this`` blindly emitted the
    # literal ``DELETE FROM False`` (silent corruption; audit sweep).
    target = expr.this
    if not isinstance(target, exp.Expression):
        tables = expr.args.get("tables") or []
        if not tables:
            raise ValueError("DELETE without a target table")
        target = tables[0]
    table = _convert_table_ref(target)

    where = None
    where_expr = expr.args.get("where")
    if where_expr:
        where = convert_expression(where_expr.this)

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

    return DeleteStatement(table=table, where=where, using=tuple(using))


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
        for col_def in schema_expr.expressions:
            if isinstance(col_def, exp.ColumnDef):
                # Computed/generated columns (AS (expr) [PERSISTED]) have no
                # plain type; sqlglot translates them to GENERATED ALWAYS AS
                # (...) STORED. Keep the column as a passthrough fragment so
                # the expression and type are preserved.
                if any(
                    isinstance(getattr(c, "kind", None), exp.ComputedColumnConstraint)
                    for c in col_def.args.get("constraints", [])
                ):
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
                if col_def.args.get("kind"):
                    dtype = _resolve_tsql_alias_type(
                        _convert_data_type(col_def.args["kind"])
                    )
                    # Oracle's unqualified NUMBER (no precision/scale) parses to
                    # a bare DECIMAL but denotes an integer id/count: map it to
                    # BIGINT so identity/PK/FK columns are valid (a DECIMAL can't
                    # be AUTO_INCREMENT on MySQL, nor match an integer PK for a
                    # foreign key). Only for an Oracle source — a bare DECIMAL
                    # from other engines keeps its meaning. NUMBER(p,s) has
                    # params and is untouched.
                    if (
                        source_dialect == "oracle"
                        and dtype.name.upper() in ("DECIMAL", "NUMERIC")
                        and not dtype.params
                    ):
                        dtype = DataType(name="BIGINT")

                nullable = True
                identity = False
                primary_key = False
                unique = False
                default: ASTNode | None = None
                for constraint in col_def.args.get("constraints", []):
                    kind = getattr(constraint, "kind", None)
                    if isinstance(kind, exp.NotNullColumnConstraint):
                        # sqlglot uses this for both "NOT NULL" and an
                        # explicit "NULL" (allow_null=True).
                        nullable = bool(getattr(kind, "args", {}).get("allow_null"))
                    elif isinstance(kind, exp.GeneratedAsIdentityColumnConstraint):
                        identity = True
                    elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
                        primary_key = True
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
                        primary_key=primary_key,
                        unique=unique,
                        quoted=_identifier_quoted(col_def.this),
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
        as_select=as_select,
    )


def _convert_create_view(expr: exp.Create) -> CreateViewStatement:
    """Convert CREATE VIEW."""
    name_expr = expr.this
    table = _convert_table_ref(name_expr)

    query_expr = expr.args.get("expression")
    query = _convert_select(query_expr) if query_expr else SelectStatement()

    return CreateViewStatement(
        name=table,
        query=query,
        or_replace=expr.args.get("replace") is not None,
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


def _convert_table_or_subquery(expr: exp.Expression) -> TableRef | SubqueryExpression:
    """Convert to either TableRef or SubqueryExpression."""
    if isinstance(expr, exp.Subquery):
        inner = expr.this
        if isinstance(inner, (exp.Select, exp.SetOperation)):
            # A derived table's alias (``(SELECT …) t``) must be carried through,
            # or references to it — and the derived table itself on MySQL — break.
            return SubqueryExpression(
                query=_convert_select(inner), alias=expr.alias or None
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
        return Literal(value=float(expr.this), dtype="number")
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
        sp_args: list[ASTNode] = []
        if needle is not None:
            sp_args.append(convert_expression(needle))
        if haystack is not None:
            sp_args.append(convert_expression(haystack))
        if start is not None:
            sp_args.append(convert_expression(start))
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

    # exp.Anonymous is an unrecognized function: its real name is in `this`
    # (a string), not in sql_name() which returns "ANONYMOUS". Its arguments
    # live in `expressions`.
    if isinstance(expr, exp.Anonymous):
        # MySQL's ADDDATE/SUBDATE are DATE_ADD/DATE_SUB aliases sqlglot
        # leaves anonymous — they shipped dbo.-qualified as fake UDFs
        # with a raw INTERVAL argument (wave 162). Canonicalize to the
        # 3-argument (ts, n, unit) form the date-add emitter renders.
        anon_name = str(expr.name).upper()
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


def _convert_binary(expr: exp.Binary) -> ASTNode:
    """Convert a binary operation.

    A binary operator that is not in the map is *not* silently coerced to ``=``
    (a dangerous default that would change semantics — e.g. bitwise ``&`` became
    ``=``). Instead the original expression is preserved as ``RawSQL`` so the
    emitter re-renders it via sqlglot, which knows the per-dialect spelling.
    """
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

    return BinaryOp(
        operator=operator,
        left=convert_expression(expr.this),
        right=convert_expression(expr.expression),
    )


def _convert_is(expr: exp.Is) -> UnaryOp:
    """Convert IS NULL / IS NOT NULL."""
    if isinstance(expr.expression, exp.Null):
        return UnaryOp(
            operator=UnaryOperator.IS_NULL,
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
    return CastExpression(expression=inner, target_type=target_type)


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

    window_spec = WindowSpec(partition_by=partition_by, order_by=order_by)
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

    return CTEDefinition(name=name, query=query, columns=columns, recursive=recursive)
