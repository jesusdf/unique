# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import logging
import re
from typing import cast

import sqlglot
import sqlglot.expressions as exp
from sqlglot import transforms

from unique.core.ast_nodes import (
    Alias,
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CaseExpression,
    CastExpression,
    ColumnDefinition,
    ColumnRef,
    CreateTableStatement,
    CreateViewStatement,
    CTEDefinition,
    DataType,
    DeleteStatement,
    DropStatement,
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
    Script,
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
from unique.core.mappings import (
    BARE_CHAR_BIGTEXT,
    CURRENT_TIMESTAMP_EXPR,
    EMIT_TYPE_MAP,
    UUID_FUNCTION,
)

logger = logging.getLogger(__name__)

# T-SQL alias types (CREATE TYPE x FROM base) harvested from the script being
# transpiled, keyed by lowercase unqualified name. The transpiler sets this
# around a run (contextvar: safe under the API's threadpool) so column types
# referencing an alias resolve to the base type on engines without aliases.
TSQL_ALIAS_TYPES: contextvars.ContextVar[dict[str, DataType] | None] = (
    contextvars.ContextVar("tsql_alias_types", default=None)
)

_CREATE_ALIAS_TYPE_RE = re.compile(
    r"(?im)^\s*CREATE\s+TYPE\s+(?:\[?dbo\]?\s*\.\s*)?\[?(\w+)\]?\s+"
    r"FROM\s+\[?(\w+)\]?\s*(?:\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\))?"
)


def harvest_tsql_alias_types(sql: str) -> dict[str, DataType]:
    """Collect T-SQL alias-type definitions from a whole script."""
    aliases: dict[str, DataType] = {}
    for m in _CREATE_ALIAS_TYPE_RE.finditer(sql):
        name, base, p1, p2 = m.groups()
        params = tuple(int(p) for p in (p1, p2) if p is not None)
        aliases[name.lower()] = DataType(name=base.upper(), params=params)
    return aliases


def _resolve_tsql_alias_type(dt: DataType) -> DataType:
    """Resolve a column type that names a harvested T-SQL alias type."""
    aliases = TSQL_ALIAS_TYPES.get()
    if not aliases:
        return dt
    key = re.sub(r'(?i)^(?:\[dbo\]|"dbo"|dbo)\s*\.\s*', "", dt.name)
    key = key.strip('[]"').lower()
    return aliases.get(key, dt)


# BIT columns harvested from the script's CREATE TABLE statements (table ->
# column names, lowercase). BIT maps to a real BOOLEAN on PostgreSQL, which
# rejects the integer 0/1 literals a T-SQL script writes into those columns,
# so INSERT/UPDATE literals are coerced at emit time.
TSQL_BIT_COLUMNS: contextvars.ContextVar[dict[str, frozenset[str]] | None] = (
    contextvars.ContextVar("tsql_bit_columns", default=None)
)

_CREATE_TABLE_NAME_RE = re.compile(
    r"(?i)\bCREATE\s+TABLE\s+([\w\[\]\".]+)",
)
_BIT_COLUMN_RE = re.compile(
    r"(?i)^\s*(\[[^\]]+\]|\w+)\s+(?:\[bit\]|bit)\b",
)


def harvest_tsql_bit_columns(sql: str) -> dict[str, frozenset[str]]:
    """Collect BIT column names per table from a whole T-SQL script."""
    result: dict[str, set[str]] = {}
    current: str | None = None
    for line in sql.splitlines():
        m = _CREATE_TABLE_NAME_RE.search(line)
        if m:
            name = m.group(1).replace("[", "").replace("]", "").replace('"', "")
            current = name.split(".")[-1].lower()
            continue
        if current is None:
            continue
        cm = _BIT_COLUMN_RE.match(line)
        if cm:
            col = cm.group(1).strip('[]"').lower()
            result.setdefault(current, set()).add(col)
    return {t: frozenset(c) for t, c in result.items()}


def coerce_bit_literals_in_sql(sql: str, dialect: str) -> str:
    """Rewrite 0/1 literals written to harvested BIT columns in raw SQL.

    Used by the procedural pipeline for embedded DML, which is transpiled
    through sqlglot rather than the IR emitter. Only INSERT ... (cols)
    VALUES and UPDATE ... SET assignments are touched, and only on
    PostgreSQL (where BIT maps to a real BOOLEAN).
    """
    if dialect != "postgresql":
        return sql
    registry = TSQL_BIT_COLUMNS.get()
    if not registry:
        return sql
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001 - leave unparseable SQL untouched
        return sql

    def as_bool(cell: exp.Expression) -> exp.Boolean | None:
        if (
            isinstance(cell, exp.Literal)
            and not cell.is_string
            and cell.this in ("0", "1")
        ):
            return exp.Boolean(this=cell.this == "1")
        return None

    changed = False
    if isinstance(tree, exp.Insert) and isinstance(tree.this, exp.Schema):
        schema_expr = tree.this
        if isinstance(schema_expr.this, exp.Table):
            cols = registry.get(schema_expr.this.name.lower(), frozenset())
            names = [c.name.lower() for c in schema_expr.expressions]
            values = tree.expression
            if cols and isinstance(values, exp.Values):
                for row in values.expressions:
                    for i, cell in enumerate(row.expressions):
                        if i < len(names) and names[i] in cols:
                            replacement = as_bool(cell)
                            if replacement is not None:
                                cell.replace(replacement)
                                changed = True
    elif isinstance(tree, exp.Update) and isinstance(tree.this, exp.Table):
        cols = registry.get(tree.this.name.lower(), frozenset())
        if cols:
            for assignment in tree.expressions:
                if (
                    isinstance(assignment, exp.EQ)
                    and isinstance(assignment.this, exp.Column)
                    and assignment.this.name.lower() in cols
                ):
                    replacement = as_bool(assignment.expression)
                    if replacement is not None:
                        assignment.expression.replace(replacement)
                        changed = True
    return tree.sql(dialect="postgres") if changed else sql


def _coerce_bit_literal(
    table: TableRef, column: str, value: ASTNode, dialect: str
) -> ASTNode:
    """Turn an integer 0/1 written to a known BIT column into a boolean."""
    if dialect != "postgresql":
        return value
    registry = TSQL_BIT_COLUMNS.get()
    if not registry:
        return value
    cols = registry.get(table.name.lower())
    if not cols:
        return value
    if column.split(".")[-1].strip('[]"').lower() not in cols:
        return value
    if (
        isinstance(value, Literal)
        and value.dtype != "string"
        and str(value.value) in ("0", "1")
    ):
        return Literal(value=str(value.value) == "1", dtype="boolean")
    return value


# DATE/DATETIME/TIMESTAMP columns harvested per table (table -> column names,
# lowercase). Oracle has no default that reads an ISO string as a date, so a
# bare '2024-01-15' written to such a column raises ORA-01861; the literal is
# wrapped in an ANSI DATE/TIMESTAMP literal at emit time (Oracle target only).
DATE_COLUMNS: contextvars.ContextVar[dict[str, frozenset[str]] | None] = (
    contextvars.ContextVar("date_columns", default=None)
)

_DATE_COLUMN_RE = re.compile(
    r"(?i)^\s*(\[[^\]]+\]|`[^`]+`|\"[^\"]+\"|\w+)\s+"
    r"(DATE|DATETIME2?|SMALLDATETIME|DATETIMEOFFSET|TIMESTAMP(?:TZ)?)\b"
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)$"
)


def harvest_date_columns(sql: str) -> dict[str, frozenset[str]]:
    """Collect date/time column names per table from a whole script.

    Works across source dialects (the type keyword is enough); only used when
    the target is Oracle.
    """
    result: dict[str, set[str]] = {}
    current: str | None = None
    for line in sql.splitlines():
        m = _CREATE_TABLE_NAME_RE.search(line)
        if m:
            name = m.group(1).replace("[", "").replace("]", "").replace('"', "")
            current = name.split(".")[-1].lower()
            continue
        if current is None:
            continue
        cm = _DATE_COLUMN_RE.match(line)
        if cm:
            col = cm.group(1).strip('[]"`').lower()
            result.setdefault(current, set()).add(col)
    return {t: frozenset(c) for t, c in result.items()}


def _coerce_date_literal(
    table: TableRef, column: str, value: ASTNode, dialect: str
) -> ASTNode:
    """Wrap an ISO date/datetime string written to a known date column in an
    ANSI ``DATE``/``TIMESTAMP`` literal so Oracle accepts it (ORA-01861)."""
    if dialect != "oracle":
        return value
    registry = DATE_COLUMNS.get()
    if not registry:
        return value
    cols = registry.get(table.name.lower())
    if not cols:
        return value
    if column.split(".")[-1].strip('[]"`').lower() not in cols:
        return value
    if not (isinstance(value, Literal) and isinstance(value.value, str)):
        return value
    text = value.value.strip()
    if _ISO_DATE_RE.match(text):
        return RawSQL(sql=f"DATE '{text}'")
    dt = _ISO_DATETIME_RE.match(text)
    if dt:
        return RawSQL(sql=f"TIMESTAMP '{dt.group(1)} {dt.group(2)}'")
    return value


# Mapping from sqlglot join types to our JoinType enum
_JOIN_TYPE_MAP = {
    "JOIN": JoinType.INNER,
    "INNER JOIN": JoinType.INNER,
    "LEFT JOIN": JoinType.LEFT,
    "LEFT OUTER JOIN": JoinType.LEFT,
    "RIGHT JOIN": JoinType.RIGHT,
    "RIGHT OUTER JOIN": JoinType.RIGHT,
    "FULL JOIN": JoinType.FULL,
    "FULL OUTER JOIN": JoinType.FULL,
    "CROSS JOIN": JoinType.CROSS,
}


def sqlglot_dialect_name(dialect: str) -> str:
    """Map our dialect names to sqlglot dialect names."""
    mapping = {
        "tsql": "tsql",
        "oracle": "oracle",
        "postgresql": "postgres",
        "mysql": "mysql",
    }
    return mapping.get(dialect, dialect)


def _looks_like_string(node: exp.Expression) -> bool:
    """Whether a sqlglot node is recognizably a string value.

    Used to decide if a T-SQL ``+`` is string concatenation rather than
    arithmetic addition: a string literal, a CHAR/VARCHAR/TEXT cast, an existing
    concatenation, or a known string function.
    """
    if isinstance(node, exp.Literal):
        return bool(node.args.get("is_string"))
    if isinstance(node, (exp.DPipe, exp.Concat)):
        return True
    if isinstance(node, exp.Cast):
        to = node.args.get("to")
        if isinstance(to, exp.DataType):
            return to.this in {
                exp.DataType.Type.CHAR,
                exp.DataType.Type.VARCHAR,
                exp.DataType.Type.NCHAR,
                exp.DataType.Type.NVARCHAR,
                exp.DataType.Type.TEXT,
            }
    if isinstance(node, (exp.Substring, exp.Trim, exp.Upper, exp.Lower)):
        return True
    if isinstance(node, exp.Anonymous):
        name = (node.name or "").upper()
        return name in {
            "LEFT",
            "RIGHT",
            "SUBSTRING",
            "LTRIM",
            "RTRIM",
            "TRIM",
            "UPPER",
            "LOWER",
            "REPLACE",
            "FORMAT",
            "STR",
            "CONCAT",
            "STUFF",
        }
    return False


def _rewrite_tsql_string_concat(expr: exp.Expression) -> exp.Expression:
    """Rewrite a T-SQL ``+`` that is string concatenation into ``||`` (DPipe).

    In T-SQL ``+`` means concatenation when an operand is a string, but sqlglot
    parses it as arithmetic ``Add`` regardless of operand type and does not
    re-map it per dialect, so ``'a' + 'b'`` would wrongly stay ``+`` on Oracle/
    PostgreSQL/MySQL. Convert an ``Add`` to ``DPipe`` when either side is
    recognizably a string (directly, or transitively through a nested string
    ``+`` already rewritten to ``DPipe``); purely numeric additions are left
    untouched. sqlglot then emits ``||`` for Oracle/PostgreSQL and ``CONCAT``
    for MySQL.
    """

    def transform(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Add):
            left, right = node.left, node.right
            if left is None or right is None:
                return node
            if (
                _looks_like_string(left)  # type: ignore[arg-type]
                or _looks_like_string(right)  # type: ignore[arg-type]
                or isinstance(left, exp.DPipe)
                or isinstance(right, exp.DPipe)
            ):
                return exp.DPipe(this=left, expression=right)
        return node

    # Bottom-up so a nested "+" is rewritten to DPipe before its parent is
    # examined, letting string-ness propagate up a chain (a + b + 'c').
    result = expr.transform(transform)
    assert isinstance(result, exp.Expression)
    return result


def parse_sql(sql: str, dialect: str) -> list[ASTNode]:
    """Parse SQL text using sqlglot and convert to IR nodes.

    Args:
        sql: Raw SQL text.
        dialect: Our dialect name ('tsql', 'oracle', 'postgresql', 'mysql').

    Returns:
        A list of IR ASTNode instances.
    """
    sg_dialect = sqlglot_dialect_name(dialect)
    try:
        parsed = sqlglot.parse(
            sql, read=sg_dialect, error_level=sqlglot.ErrorLevel.WARN
        )
    except Exception as e:
        logger.warning("sqlglot parse error: %s", e)
        return [RawSQL(sql=sql, reason=str(e))]

    nodes: list[ASTNode] = []
    for expression in parsed:
        if expression is None:
            continue
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
        if dialect == "tsql":
            expression = _rewrite_tsql_string_concat(
                expression  # type: ignore[arg-type]
            )
        node = convert_expression(expression, dialect)  # type: ignore[arg-type]
        nodes.append(node)

    return nodes


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
    # T-SQL CONVERT(type, value, style) uses numeric style codes for date
    # formatting that sqlglot maps to TO_CHAR/DATE_FORMAT patterns. Our
    # expression converter would drop the value and style, so pass the whole
    # statement through when a styled CONVERT is present.
    if isinstance(expr, exp.Select) and any(
        c.args.get("style") is not None for c in expr.find_all(exp.Convert)
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
    if isinstance(expr, exp.Union):
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
    if isinstance(expr, exp.Case):
        return _convert_case(expr)
    if isinstance(expr, exp.Cast):
        return _convert_cast(expr)
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
        if isinstance(inner, (exp.Select, exp.Union)):
            return SubqueryExpression(query=_convert_select(inner))
        return RawSQL(sql=expr.sql(), reason="Complex subquery")
    if isinstance(expr, exp.Window):
        return _convert_window(expr)
    if isinstance(expr, exp.Paren):
        return convert_expression(expr.this)
    if isinstance(expr, exp.Ordered):
        return _convert_ordered(expr)
    # MySQL charset introducer (_utf8'x'): the charset tag is MySQL-only
    # syntax (and legacy even there); keep just the string literal.
    if isinstance(expr, exp.Introducer):
        return convert_expression(expr.expression)

    # Fallback: emit as raw SQL
    try:
        raw = expr.sql()
    except Exception:
        raw = str(expr)
    return RawSQL(sql=raw, reason=f"Unhandled expression type: {type(expr).__name__}")


def _convert_select(expr: exp.Expression) -> SelectStatement:
    """Convert a sqlglot Select expression to a SelectStatement IR node."""
    # Handle Union by extracting the left Select
    if isinstance(expr, exp.Union):
        return _convert_union(expr)

    columns = tuple(convert_expression(col) for col in (expr.expressions or []))

    # FROM
    from_clause = None
    from_expr = expr.find(exp.From)
    if from_expr and from_expr.this:
        from_clause = _convert_table_or_subquery(from_expr.this)

    # JOINs
    joins = tuple(_convert_join(j) for j in (expr.args.get("joins") or []))

    # WHERE
    where = None
    where_expr = expr.find(exp.Where)
    if where_expr:
        where = convert_expression(where_expr.this)

    # GROUP BY
    group_by_expr = expr.args.get("group")
    group_by = tuple(
        convert_expression(g)
        for g in (group_by_expr.expressions if group_by_expr else [])
    )

    # HAVING
    having = None
    having_expr = expr.find(exp.Having)
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
        percent = False
        if limit_expr is not None:
            opts = limit_expr.args.get("limit_options")
            percent = bool(opts and opts.args.get("percent"))
        limit = LimitClause(
            limit=convert_expression(limit_expr.expression) if limit_expr else None,
            offset=convert_expression(offset_expr.expression) if offset_expr else None,
            percent=percent,
        )

    # DISTINCT
    distinct = expr.args.get("distinct") is not None

    # CTEs
    ctes: tuple[CTEDefinition, ...] = ()
    with_clause = expr.args.get("with") or expr.args.get("with_")
    if with_clause:
        ctes = tuple(_convert_cte(c) for c in with_clause.expressions)

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
    )


def _convert_union(expr: exp.Union) -> SelectStatement:
    """Convert a UNION/INTERSECT/EXCEPT to a SelectStatement with set operation."""
    left = _convert_select(expr.this)
    right = _convert_select(expr.expression)

    # Determine set operation type
    if isinstance(expr, exp.Intersect):
        set_op = SetOperationType.INTERSECT
    elif isinstance(expr, exp.Except):
        set_op = SetOperationType.EXCEPT
    elif expr.args.get("distinct") is False:
        set_op = SetOperationType.UNION_ALL
    else:
        set_op = SetOperationType.UNION

    return SelectStatement(
        columns=left.columns,
        from_clause=left.from_clause,
        joins=left.joins,
        where=left.where,
        group_by=left.group_by,
        having=left.having,
        order_by=left.order_by,
        limit=left.limit,
        distinct=left.distinct,
        ctes=left.ctes,
        set_op=set_op,
        set_query=right,
    )


def _convert_insert(expr: exp.Insert) -> InsertStatement:
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

    # VALUES
    values: tuple[tuple[ASTNode, ...], ...] = ()
    val_expr = expr.args.get("expression")
    if isinstance(val_expr, exp.Values):
        values = tuple(
            tuple(convert_expression(v) for v in row.expressions)
            for row in val_expr.expressions
        )

    # SELECT
    select = None
    if isinstance(val_expr, exp.Select):
        select = _convert_select(val_expr)

    return InsertStatement(
        table=table,
        columns=columns,
        values=values,
        select=select,
    )


def _convert_update(expr: exp.Update) -> UpdateStatement:
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

    where = None
    where_expr = expr.find(exp.Where)
    if where_expr:
        where = convert_expression(where_expr.this)

    return UpdateStatement(
        table=table,
        assignments=tuple(assignments),
        where=where,
        from_clause=from_clause,
        joins=tuple(joins),
    )


def _convert_delete(expr: exp.Delete) -> DeleteStatement:
    """Convert a sqlglot Delete to DeleteStatement."""
    table = _convert_table_ref(expr.this)

    where = None
    where_expr = expr.find(exp.Where)
    if where_expr:
        where = convert_expression(where_expr.this)

    return DeleteStatement(table=table, where=where)


def _convert_create(expr: exp.Create) -> ASTNode:
    """Convert a sqlglot Create to the appropriate IR node."""
    kind = (expr.args.get("kind") or "").upper()

    if kind == "TABLE":
        return _convert_create_table(expr)
    if kind == "VIEW":
        return _convert_create_view(expr)

    return RawSQL(sql=expr.sql(), reason=f"Unhandled CREATE {kind}")


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

    return CreateTableStatement(
        table=table,
        columns=tuple(columns),
        if_not_exists=if_not_exists,
        table_constraints=tuple(constraints),
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
    kind = (expr.args.get("kind") or "TABLE").upper()
    table = _convert_table_ref(expr.this) if expr.this else TableRef(name="unknown")
    if_exists = expr.args.get("exists") is not None

    return DropStatement(
        object_type=kind,
        name=table,
        if_exists=if_exists,
    )


def _identifier_quoted(node: exp.Expression | None) -> bool:
    """True if *node* is a sqlglot Identifier that was quoted in the source."""
    return isinstance(node, exp.Identifier) and bool(node.args.get("quoted"))


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
        # DROP SCHEMA x / USE x parse as a Table with only the db part set;
        # promoting db to name avoids emitting a dangling "x." qualifier.
        if not expr.name and expr.db:
            return TableRef(
                name=expr.db,
                alias=alias,
                quoted=_identifier_quoted(expr.args.get("db")),
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
        )
    if isinstance(expr, exp.Schema):
        return _convert_table_ref(expr.this)
    if hasattr(expr, "name"):
        return TableRef(name=expr.name)
    return TableRef(name=str(expr))


def _convert_table_or_subquery(expr: exp.Expression) -> TableRef | SubqueryExpression:
    """Convert to either TableRef or SubqueryExpression."""
    if isinstance(expr, exp.Subquery):
        inner = expr.this
        if isinstance(inner, (exp.Select, exp.Union)):
            return SubqueryExpression(query=_convert_select(inner))
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


def _convert_function(expr: exp.Expression) -> FunctionCall:
    """Convert a function call."""
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

    # exp.Anonymous is an unrecognized function: its real name is in `this`
    # (a string), not in sql_name() which returns "ANONYMOUS". Its arguments
    # live in `expressions`.
    if isinstance(expr, exp.Anonymous):
        return FunctionCall(
            name=str(expr.name),
            args=tuple(convert_expression(a) for a in expr.expressions),
        )

    name = expr.sql_name() if hasattr(expr, "sql_name") else type(expr).__name__.upper()

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
    }

    operator = op_map.get(type(expr))
    if operator is None:
        # Unknown operator: preserve verbatim rather than corrupt it to "=".
        return RawSQL(sql=expr.sql(), reason=f"unmapped operator {type(expr).__name__}")

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


# Type tables live in the shared declarative mapping layer (audit doc 03);
# _TYPE_NAME_MAP / _BARE_CHAR_BIGTEXT are kept as local aliases for the many
# call sites in this module.
_TYPE_NAME_MAP = EMIT_TYPE_MAP
_BARE_CHAR_BIGTEXT = BARE_CHAR_BIGTEXT


def _portable_type_name(name: str, dialect: str) -> str:
    """Map a data-type name to the target dialect's equivalent.

    Falls back to the original name when no mapping is needed. Some mappings
    (e.g. UNIQUEIDENTIFIER -> CHAR(36)) carry their own length, in which case
    the caller's parameter list should be empty; these are types that don't
    take a user-supplied length here.
    """
    return _TYPE_NAME_MAP.get(dialect, {}).get(name.upper(), name)


def _portable_types_in_sql(sql: str, dialect: str) -> str:
    """Replace non-portable type names in raw emitted SQL for ``dialect``.

    Used for passthrough DDL (e.g. CREATE TABLE handled by sqlglot) where
    column types aren't routed through our own emitter. Word-boundary,
    case-insensitive replacement; types that carry their own length in the
    map (e.g. CHAR(36)) only substitute the bare name, so an existing
    ``(n)`` after it would be left — acceptable since those source types
    (UNIQUEIDENTIFIER/UUID) don't take a user length.
    """
    mapping = _TYPE_NAME_MAP.get(dialect, {})
    if not mapping:
        return sql
    for src, dst in mapping.items():
        # Replace the bare type name not already followed by '2' (avoid
        # turning VARCHAR into VARCHAR2 twice) — handled by word boundary.
        dst_name = dst.split("(")[0]
        sql = re.sub(rf"(?i)\b{re.escape(src)}\b", dst_name, sql)
    return sql


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
    table = _convert_table_ref(table_expr)

    alias = None
    if isinstance(table_expr, exp.Table):
        alias_expr = table_expr.args.get("alias")
        if alias_expr:
            alias = str(alias_expr.this)

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
    """Convert an ORDER BY item."""
    inner = convert_expression(expr.this)
    desc = expr.args.get("desc")
    direction = OrderDirection.DESC if desc else OrderDirection.ASC
    return OrderByItem(expression=inner, direction=direction)


def _convert_cte(expr: exp.CTE) -> CTEDefinition:
    """Convert a CTE definition."""
    name = expr.alias if isinstance(expr.alias, str) else str(expr.alias)
    query_expr = expr.this
    query = _convert_select(query_expr) if query_expr else SelectStatement()

    return CTEDefinition(name=name, query=query)


def emit_sql(nodes: list[ASTNode], dialect: str) -> str:
    """Emit IR nodes as SQL text for the given dialect.

    This is the shared emitter that handles common patterns. Dialect-specific
    emitters may override individual node handling.

    Args:
        nodes: IR nodes to emit.
        dialect: Target dialect name.

    Returns:
        Formatted SQL text.
    """
    parts: list[str] = []
    for node in nodes:
        sql = emit_node(node, dialect)
        if sql:
            parts.append(sql)
    # T-SQL separates batches with GO and does not terminate statements with
    # ';'. Other dialects use ';' as the statement terminator.
    if dialect == "tsql":
        return "\nGO\n\n".join(parts)
    return ";\n\n".join(parts)


def _comment_block(sql: str) -> str:
    """Comment out every line of *sql* (``-- `` prefix).

    Degraded passthroughs must comment the whole statement: prefixing only
    the first line leaves the remaining lines as raw source SQL, executable
    and invalid on the target.
    """
    return "\n".join(f"-- {ln}" if ln.strip() else "--" for ln in sql.splitlines())


def emit_node(node: ASTNode, dialect: str) -> str:
    """Emit a single IR node as SQL text."""
    if isinstance(node, SelectStatement):
        return _emit_select(node, dialect)
    if isinstance(node, InsertStatement):
        return _emit_insert(node, dialect)
    if isinstance(node, UpdateStatement):
        return _emit_update(node, dialect)
    if isinstance(node, DeleteStatement):
        return _emit_delete(node, dialect)
    if isinstance(node, CreateTableStatement):
        return _emit_create_table(node, dialect)
    if isinstance(node, CreateViewStatement):
        return _emit_create_view(node, dialect)
    if isinstance(node, DropStatement):
        return _emit_drop(node, dialect)
    if isinstance(node, RawSQL):
        return f"-- UNIQUE: {node.reason}\n{_comment_block(node.sql)}"
    if isinstance(node, PassthroughSQL):
        return _emit_passthrough(node, dialect)
    if isinstance(node, Script):
        sep = "\nGO\n\n" if dialect == "tsql" else ";\n\n"
        return sep.join(emit_node(s, dialect) for s in node.statements)

    # Expression-level emission
    return _emit_expression(node, dialect)


def _merge_to_mysql_upsert(sql: str, read: str) -> str | None:
    """Rewrite a canonical MERGE as MySQL INSERT ... ON DUPLICATE KEY UPDATE.

    Handles exactly one unconditional WHEN MATCHED THEN UPDATE plus one
    unconditional WHEN NOT MATCHED THEN INSERT, with a table or subquery
    source. Each UPDATE assignment must be either a literal or a source
    column that also appears in the INSERT values (rewritten as
    ``col = VALUES(col)``). Returns None when the MERGE is more complex, so
    the caller falls back to the documented carrier comment.
    """
    try:
        merge = sqlglot.parse_one(sql, read=read)
    except Exception:  # noqa: BLE001 - unparseable, let caller fall back
        return None
    if not isinstance(merge, exp.Merge) or merge.args.get("returning"):
        return None

    whens = merge.args.get("whens")
    when_list = list(whens.expressions) if whens else []
    if len(when_list) != 2:
        return None
    update = insert = None
    for when in when_list:
        if when.args.get("condition") is not None:
            return None
        then = when.args.get("then")
        if when.args.get("matched") and isinstance(then, exp.Update):
            update = then
        elif not when.args.get("matched") and isinstance(then, exp.Insert):
            insert = then
        else:
            return None
    if update is None or insert is None:
        return None
    if not isinstance(insert.this, exp.Tuple) or not isinstance(
        insert.expression, exp.Tuple
    ):
        return None

    insert_cols = [c.name for c in insert.this.expressions]
    insert_vals = insert.expression.expressions
    if len(insert_cols) != len(insert_vals):
        return None
    # Map each inserted value's SQL back to its column, so UPDATE assignments
    # whose RHS is one of the inserted source columns become VALUES(col).
    value_to_col = {
        val.sql(dialect="mysql"): col
        for col, val in zip(insert_cols, insert_vals, strict=True)
    }

    assignments: list[str] = []
    for eq in update.expressions:
        if not isinstance(eq, exp.EQ):
            return None
        target_col = eq.this.name  # strip any target-alias qualifier
        rhs = eq.expression
        rhs_sql = rhs.sql(dialect="mysql")
        if rhs_sql in value_to_col:
            assignments.append(f"{target_col} = VALUES({value_to_col[rhs_sql]})")
        elif isinstance(rhs, (exp.Literal, exp.Null)):
            assignments.append(f"{target_col} = {rhs_sql}")
        else:
            return None

    target_sql = merge.this.sql(dialect="mysql")
    source_sql = merge.args["using"].sql(dialect="mysql")
    cols_sql = ", ".join(insert_cols)
    vals_sql = ", ".join(v.sql(dialect="mysql") for v in insert_vals)
    on_cols = ", ".join(sorted({c.name for c in merge.args["on"].find_all(exp.Column)}))
    return (
        f"INSERT INTO {target_sql} ({cols_sql})\n"
        f"SELECT {vals_sql} FROM {source_sql}\n"
        f"ON DUPLICATE KEY UPDATE {', '.join(assignments)};\n"
        f"-- UNIQUE: MERGE rewritten as INSERT ... ON DUPLICATE KEY UPDATE; "
        f"requires a UNIQUE or PRIMARY KEY on ({on_cols})"
    )


def _emit_passthrough(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a passthrough statement to the target dialect.

    Uses sqlglot directly (it handles ALTER, CREATE INDEX, CREATE SEQUENCE,
    etc. well). On failure, fall back to a commented passthrough so nothing
    is silently lost.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)

    # MySQL has no CREATE SEQUENCE; sqlglot would emit invalid SQL.
    if dialect == "mysql" and node.kind == "CREATE SEQUENCE":
        return (
            "-- UNIQUE: MySQL has no sequences; use an AUTO_INCREMENT column "
            "instead. Original:\n"
            + _comment_block(_strip_dbo_schema_qualifier(node.sql))
        )

    # USE <db> switches the active database. Valid in MySQL and T-SQL only;
    # PostgreSQL (\\c is a psql meta-command) and Oracle have no SQL form.
    if node.kind == "USE" and dialect in ("postgresql", "oracle"):
        return (
            f"-- UNIQUE: {dialect} has no USE statement; "
            f"connect to the target database/schema instead.\n"
            f"{_comment_block(node.sql)}"
        )

    # MySQL has no MERGE. The canonical one-UPDATE/one-INSERT pattern is
    # rewritten as INSERT ... SELECT ... ON DUPLICATE KEY UPDATE (which relies
    # on a UNIQUE/PRIMARY KEY covering the ON columns — noted in a carrier).
    # Anything more complex falls back to a documented comment.
    if node.kind == "MERGE" and dialect == "mysql":
        upsert = _merge_to_mysql_upsert(node.sql, read)
        if upsert is not None:
            return upsert
        commented = _comment_block(node.sql)
        return (
            "-- UNIQUE: MySQL has no MERGE; rewrite as "
            "INSERT ... ON DUPLICATE KEY UPDATE. Original:\n" + commented
        )

    # Oracle hierarchical query: keep as-is for Oracle; for others there is
    # no faithful automatic rewrite, so emit a documented comment.
    if node.kind == "CONNECT BY" and dialect != "oracle":
        commented = _comment_block(node.sql)
        return (
            "-- UNIQUE: Oracle CONNECT BY / START WITH hierarchical query has "
            "no automatic equivalent; rewrite as a WITH RECURSIVE CTE. "
            "Original:\n" + commented
        )

    # MySQL has no RETURNING/OUTPUT; comment it rather than emit invalid SQL.
    if node.kind == "RETURNING" and dialect == "mysql":
        m = re.search(r"(?i)\bRETURNING\b\s+(.*?)\s*;?\s*$", node.sql)
        cols = m.group(1).strip() if m else ""
        base = re.sub(r"(?i)\s*\bRETURNING\b.*$", "", node.sql).rstrip()
        return (
            f"{base};\n-- UNIQUE: MySQL has no RETURNING/OUTPUT; "
            f"the statement returned: {cols}"
        )

    try:
        out = sqlglot.transpile(node.sql, read=read, write=write)
        if out and out[0].strip():
            result = out[0]
            if node.kind == "CREATE INDEX":
                result = _portable_index(result, dialect)
            else:
                result = _portable_types_in_sql(result, dialect)
            if node.kind == "CREATE SEQUENCE" and dialect == "oracle":
                result = _oracle_sequence_drop_type(result)
            if dialect != "oracle":
                result = _portable_alter_add(result, dialect)
            if dialect in ("oracle", "mysql", "postgresql"):
                result = _strip_dbo_schema_qualifier(result)
            return result
    except Exception as e:  # noqa: BLE001 - report and fall back
        logger.warning("passthrough transpile error (%s): %s", node.kind, e)
    return f"-- UNIQUE: Unhandled {node.kind}\n{_comment_block(node.sql)}"


def _split_top_level_commas(text: str) -> list[str]:
    """Split *text* on commas not nested inside parentheses or strings."""
    parts: list[str] = []
    depth = 0
    in_string = False
    start = 0
    for i, ch in enumerate(text):
        if in_string:
            if ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _oracle_sequence_drop_type(sql: str) -> str:
    """Drop the ``AS <type>`` clause from a CREATE SEQUENCE for Oracle.

    T-SQL/PostgreSQL allow ``CREATE SEQUENCE s AS INT ...`` to bound the
    sequence's data type; Oracle has no such clause and rejects it
    (ORA-03048). sqlglot maps the type but keeps the clause, so remove the
    ``AS <type>`` that follows the sequence name.
    """
    return re.sub(
        r"(?is)(\bCREATE\s+SEQUENCE\s+\S+)\s+AS\s+\w+(?:\s*\([^)]*\))?",
        r"\1",
        sql,
        count=1,
    )


def _portable_alter_add(sql: str, dialect: str) -> str:
    """Unwrap Oracle's parenthesized ALTER TABLE ADD ( ... ) form.

    sqlglot's non-Oracle writers render it as "ADD COLUMNS (item, ...)",
    which no other engine parses. T-SQL takes a plain comma list after one
    ADD; PostgreSQL/MySQL need one ADD per item.
    """
    m = re.search(r"(?is)\bADD\s+COLUMNS\s*\((.*)\)\s*$", sql)
    if not m:
        return sql
    items = [i.strip() for i in _split_top_level_commas(m.group(1))]
    head = sql[: m.start()].rstrip()
    if dialect == "tsql":
        return f"{head} ADD {', '.join(items)}"
    return f"{head} ADD " + ", ADD ".join(items)


def _portable_index(sql: str, dialect: str) -> str:
    """Make a transpiled CREATE INDEX portable for the target dialect.

    - CLUSTERED/NONCLUSTERED are T-SQL-only physical hints; drop them for
      other engines (the keyword has no meaning and breaks parsing).
    - INCLUDE (covering columns) is supported by PostgreSQL and T-SQL but not
      MySQL or Oracle; comment it out there with a note.
    - A filtered-index WHERE clause is supported by PostgreSQL (partial
      index) but not MySQL/Oracle; flag it for those.
    """
    if dialect != "tsql":
        sql = re.sub(r"(?i)\b(NON)?CLUSTERED\s+", "", sql)
        # T-SQL physical index storage options (WITH (PAD_INDEX = ..., ...))
        # and ON [filegroup] have no portable equivalent; drop them.
        sql = re.sub(r"(?i)\s+WITH\s*\([^)]*\)", "", sql)
        sql = re.sub(r"(?i)\s+ON\s+\[[^\]]+\]\s*$", "", sql)

    # sqlglot emulates PostgreSQL's NULLS-ordering by prefixing an index key
    # with "CASE WHEN col IS NULL THEN 1 ELSE 0 END, col". That expression is
    # invalid inside an index column list in T-SQL, MySQL and Oracle, so
    # collapse it back to just the column for every target except PostgreSQL.
    if dialect != "postgresql":
        sql = re.sub(
            r"(?i)CASE\s+WHEN\s+(?P<col>[\w.\[\]\"`]+)\s+IS\s+NULL\s+THEN\s+"
            r"\d+\s+ELSE\s+\d+\s+END\s*,\s*(?P=col)",
            lambda m: m.group("col"),
            sql,
        )

    if dialect in ("mysql", "oracle"):
        # INCLUDE (...) covering columns: not supported.
        m = re.search(r"(?i)\bINCLUDE\s*\([^)]*\)", sql)
        if m:
            sql = (
                sql[: m.start()].rstrip()
                + sql[m.end() :]
                + f"\n-- UNIQUE: {dialect} does not support INCLUDE covering "
                f"columns; dropped: {m.group(0)}"
            )
        # Filtered index WHERE: not supported (MySQL/Oracle).
        m = re.search(r"(?i)\sWHERE\s+.+$", sql)
        if m:
            sql = (
                sql[: m.start()].rstrip()
                + f"\n-- UNIQUE: {dialect} does not support filtered indexes; "
                f"dropped predicate:{m.group(0)}"
            )
    return sql


def _emit_select(node: SelectStatement, dialect: str) -> str:
    """Emit a SELECT statement."""
    parts: list[str] = []

    # CTEs
    if node.ctes:
        cte_parts = []
        for cte in node.ctes:
            recursive = "RECURSIVE " if cte.recursive else ""
            cols = f"({', '.join(cte.columns)})" if cte.columns else ""
            inner = _emit_select(cte.query, dialect)
            cte_parts.append(f"{cte.name}{cols} AS (\n{inner}\n)")
        parts.append(f"WITH {recursive}{', '.join(cte_parts)}")

    # SELECT — T-SQL spells a plain row limit as TOP inside the SELECT
    # clause (OFFSET/FETCH needs an ORDER BY and an offset). v0.7.0 reduced
    # it to a comment, silently returning all rows (audit 2026-07-02).
    top = ""
    if (
        dialect == "tsql"
        and node.limit is not None
        and node.limit.limit is not None
        and node.limit.offset is None
    ):
        pct = " PERCENT" if node.limit.percent else ""
        top = f"TOP {_emit_expression(node.limit.limit, dialect)}{pct} "
    distinct = "DISTINCT " if node.distinct else ""
    cols = ", ".join(_emit_expression(c, dialect) for c in node.columns) or "*"
    parts.append(f"SELECT {distinct}{top}{cols}")

    # FROM
    if node.from_clause:
        if isinstance(node.from_clause, SubqueryExpression):
            parts.append(f"FROM ({_emit_select(node.from_clause.query, dialect)})")
        else:
            parts.append(f"FROM {_emit_table_ref(node.from_clause, dialect)}")

    # JOINs
    left_name = None
    if isinstance(node.from_clause, TableRef) and len(node.joins) == 1:
        left_name = node.from_clause.alias or node.from_clause.name
    for join in node.joins:
        parts.append(_emit_join(join, dialect, left_name=left_name))

    # WHERE
    if node.where:
        parts.append(f"WHERE {_emit_expression(node.where, dialect)}")

    # GROUP BY
    if node.group_by:
        group_cols = ", ".join(_emit_expression(g, dialect) for g in node.group_by)
        parts.append(f"GROUP BY {group_cols}")

    # HAVING
    if node.having:
        parts.append(f"HAVING {_emit_expression(node.having, dialect)}")

    # ORDER BY
    if node.order_by:
        order_items = ", ".join(_emit_order_item(o, dialect) for o in node.order_by)
        parts.append(f"ORDER BY {order_items}")

    # LIMIT / OFFSET
    if node.limit:
        limit_sql = _emit_limit(node.limit, dialect)
        if limit_sql:
            parts.append(limit_sql)

    result = "\n".join(parts)

    # Set operation
    if node.set_op and node.set_query:
        op_map = {
            SetOperationType.UNION: "UNION",
            SetOperationType.UNION_ALL: "UNION ALL",
            SetOperationType.INTERSECT: "INTERSECT",
            SetOperationType.EXCEPT: "EXCEPT" if dialect != "oracle" else "MINUS",
        }
        op = op_map.get(node.set_op, "UNION")
        right = _emit_select(node.set_query, dialect)
        result = f"{result}\n{op}\n{right}"

    return result


def _emit_insert(node: InsertStatement, dialect: str) -> str:
    """Emit an INSERT statement."""
    table = _emit_table_ref(node.table, dialect)
    cols = f" ({', '.join(node.columns)})" if node.columns else ""

    if node.values:
        rows = []
        for row in node.values:
            cells = []
            for i, v in enumerate(row):
                if node.columns and i < len(node.columns):
                    v = _coerce_bit_literal(node.table, node.columns[i], v, dialect)
                    v = _coerce_date_literal(node.table, node.columns[i], v, dialect)
                cells.append(_emit_expression(v, dialect))
            rows.append(f"({', '.join(cells)})")
        values = ", ".join(rows)
        return f"INSERT INTO {table}{cols}\nVALUES {values}"

    if node.select:
        select = _emit_select(node.select, dialect)
        return f"INSERT INTO {table}{cols}\n{select}"

    return f"INSERT INTO {table}{cols}\nDEFAULT VALUES"


def _emit_update(node: UpdateStatement, dialect: str) -> str:
    """Emit an UPDATE statement.

    A cross-table update (``from_clause``/``joins`` present) is rendered in each
    engine's idiomatic form. T-SQL keeps ``UPDATE t SET ... FROM ... JOIN``;
    PostgreSQL uses ``UPDATE t SET ... FROM ... WHERE <join preds>``; MySQL puts
    the joins before SET (``UPDATE t JOIN s ON ... SET ...``); Oracle, which has
    no ``UPDATE ... FROM``, uses correlated subqueries. A plain single-table
    update is unchanged.
    """
    if node.from_clause is not None or node.joins:
        return _emit_cross_table_update(node, dialect)

    table = _emit_table_ref(node.table, dialect)
    set_parts = []
    for col, val in node.assignments:
        val = _coerce_bit_literal(node.table, col, val, dialect)
        val = _coerce_date_literal(node.table, col, val, dialect)
        set_parts.append(f"{col} = {_emit_expression(val, dialect)}")
    sets = ", ".join(set_parts)
    result = f"UPDATE {table}\nSET {sets}"

    if node.where:
        result += f"\nWHERE {_emit_expression(node.where, dialect)}"

    return result


def _emit_join_table_ref(table: TableRef | SubqueryExpression, dialect: str) -> str:
    """Emit a join's source table, whether a plain table or a subquery."""
    if isinstance(table, SubqueryExpression):
        return f"({_emit_select(table.query, dialect)})"
    return _emit_table_ref(table, dialect)


def _emit_cross_table_update(node: UpdateStatement, dialect: str) -> str:
    """Render a cross-table UPDATE (``UPDATE ... SET ... FROM/JOIN``) per engine.

    The T-SQL target alias usually names the same table as the FROM's first
    source (``UPDATE il SET il.c = p.c FROM invoice_line il JOIN product p``).
    We treat that first source as the table being updated and the remaining
    joins as the source side.
    """
    target = _cross_update_target(node)
    assignments = [
        (
            col,
            _emit_expression(
                _coerce_date_literal(
                    target, col, _coerce_bit_literal(target, col, val, dialect), dialect
                ),
                dialect,
            ),
        )
        for col, val in node.assignments
    ]

    if dialect == "oracle":
        return _emit_update_oracle_subquery(node, target, assignments)
    if dialect == "mysql":
        return _emit_update_mysql_join(node, target, assignments, dialect)
    if dialect == "postgresql":
        return _emit_update_postgres_from(node, target, assignments, dialect)
    # T-SQL (and any other) keeps the native UPDATE ... FROM ... JOIN form.
    return _emit_update_tsql_from(node, assignments, dialect)


def _cross_update_target(node: UpdateStatement) -> TableRef:
    """The real table being updated in a cross-table UPDATE.

    The T-SQL ``node.table`` is typically the alias (e.g. ``il``); the FROM's
    first source carries the actual table name and that alias. Prefer the FROM
    source when its alias matches the target, so we emit the real table name.
    """
    tgt_name = node.table.name
    if node.from_clause is not None:
        fc = node.from_clause
        if fc.alias == tgt_name or fc.name == tgt_name:
            return fc
    return node.table


def _join_predicates(node: UpdateStatement, dialect: str) -> list[str]:
    """Collect every join ON condition as a list of boolean SQL fragments."""
    preds: list[str] = []
    for join in node.joins:
        if join.condition is not None:
            preds.append(_emit_expression(join.condition, dialect))
    return preds


def _emit_update_postgres_from(
    node: UpdateStatement,
    target: TableRef,
    assignments: list[tuple[str, str]],
    dialect: str,
) -> str:
    """PostgreSQL: UPDATE t SET c = s.c FROM s [, ...] WHERE <join preds>."""
    target_sql = _emit_table_ref(target, dialect)
    sets = ", ".join(f"{col} = {val}" for col, val in assignments)
    sources = [_emit_join_table_ref(j.table, dialect) for j in node.joins]
    result = f"UPDATE {target_sql}\nSET {sets}"
    if sources:
        result += f"\nFROM {', '.join(sources)}"
    conditions = _join_predicates(node, dialect)
    if node.where is not None:
        conditions.append(_emit_expression(node.where, dialect))
    if conditions:
        result += f"\nWHERE {' AND '.join(conditions)}"
    return result


def _emit_update_mysql_join(
    node: UpdateStatement,
    target: TableRef,
    assignments: list[tuple[str, str]],
    dialect: str,
) -> str:
    """MySQL: UPDATE t JOIN s ON ... SET t.c = s.c [WHERE ...]."""
    target_sql = _emit_table_ref(target, dialect)
    joins_sql = "".join(f"\n{_emit_join(j, dialect)}" for j in node.joins)
    sets = ", ".join(f"{col} = {val}" for col, val in assignments)
    result = f"UPDATE {target_sql}{joins_sql}\nSET {sets}"
    if node.where is not None:
        result += f"\nWHERE {_emit_expression(node.where, dialect)}"
    return result


def _emit_update_tsql_from(
    node: UpdateStatement,
    assignments: list[tuple[str, str]],
    dialect: str,
) -> str:
    """T-SQL: UPDATE t SET t.c = s.c FROM t JOIN s ON ... [WHERE ...]."""
    table = _emit_table_ref(node.table, dialect)
    sets = ", ".join(f"{col} = {val}" for col, val in assignments)
    result = f"UPDATE {table}\nSET {sets}"
    if node.from_clause is not None:
        from_sql = _emit_table_ref(node.from_clause, dialect)
        joins_sql = "".join(f"\n{_emit_join(j, dialect)}" for j in node.joins)
        result += f"\nFROM {from_sql}{joins_sql}"
    if node.where is not None:
        result += f"\nWHERE {_emit_expression(node.where, dialect)}"
    return result


def _emit_update_oracle_subquery(
    node: UpdateStatement,
    target: TableRef,
    assignments: list[tuple[str, str]],
) -> str:
    """Oracle has no UPDATE ... FROM; use a correlated-subquery UPDATE.

    For a single source join with predicate, each assigned value is rewritten
    as ``(SELECT <expr> FROM <source> WHERE <join pred>)`` and an EXISTS guard
    limits the update to rows that have a match. Falls back to a documented
    comment when the shape is too complex to rewrite safely (multiple joins).
    """
    dialect = "oracle"
    target_sql = _emit_table_ref(target, dialect)

    if len(node.joins) != 1 or node.joins[0].condition is None:
        original = _emit_update_tsql_from(node, assignments, dialect)
        commented = _comment_block(original)
        return (
            "-- UNIQUE: Oracle has no UPDATE ... FROM with multiple joins; "
            "rewrite as a MERGE or correlated subqueries. Original:\n" + commented
        )

    join = node.joins[0]
    source_sql = _emit_join_table_ref(join.table, dialect)
    assert join.condition is not None  # guarded by the check above
    pred = _emit_expression(join.condition, dialect)

    set_items = ", ".join(
        f"{col} = (SELECT {val} FROM {source_sql} WHERE {pred})"
        for col, val in assignments
    )
    result = f"UPDATE {target_sql}\nSET {set_items}"
    conditions = [f"EXISTS (SELECT 1 FROM {source_sql} WHERE {pred})"]
    if node.where is not None:
        conditions.append(_emit_expression(node.where, dialect))
    result += f"\nWHERE {' AND '.join(conditions)}"
    return result


def _emit_delete(node: DeleteStatement, dialect: str) -> str:
    """Emit a DELETE statement."""
    table = _emit_table_ref(node.table, dialect)
    result = f"DELETE FROM {table}"

    if node.where:
        result += f"\nWHERE {_emit_expression(node.where, dialect)}"

    return result


def _emit_enum_type(col: ColumnDefinition, dialect: str) -> tuple[str, str, str]:
    """Render a MySQL ENUM/SET column type for *dialect*.

    Returns ``(type_sql, inline_check_sql, trailing_note)``. MySQL keeps the
    native type. Elsewhere ENUM becomes VARCHAR sized to the longest value
    plus an inline CHECK carrying the value-list semantics; SET (an unordered
    combination of values) has no CHECK equivalent, so it becomes a VARCHAR
    wide enough for all values with a documented carrier note.
    """
    values = col.data_type.values
    quoted_values = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    kind = col.data_type.name.upper()
    if dialect == "mysql":
        return f"{kind}({quoted_values})", "", ""
    varchar = _portable_type_name("VARCHAR", dialect)
    col_name = _ident(col.name, col.quoted, dialect)
    if kind == "ENUM":
        max_len = max(len(v) for v in values)
        return (
            f"{varchar}({max_len})",
            f" CHECK ({col_name} IN ({quoted_values}))",
            "",
        )
    total_len = sum(len(v) for v in values) + max(len(values) - 1, 0)
    note = (
        f"-- UNIQUE: MySQL SET type on {col_name} has no {dialect} "
        f"equivalent; stored as {varchar}({total_len}). "
        f"Allowed members: {quoted_values}"
    )
    return f"{varchar}({total_len})", "", note


def _emit_create_table(node: CreateTableStatement, dialect: str) -> str:
    """Emit a CREATE TABLE statement."""
    # The T-SQL default schema "dbo" has no meaning in Oracle, MySQL or
    # PostgreSQL; _emit_table_ref drops it for those dialects so the table lands
    # in the current user's schema (Oracle), the connected database (MySQL), or
    # the default "public" schema (PostgreSQL).
    table = _emit_table_ref(node.table, dialect)
    temp = "TEMPORARY " if node.temporary else ""
    # T-SQL has no "CREATE TABLE IF NOT EXISTS"; the idiomatic equivalent is an
    # existence guard against the catalog. Other engines support the clause
    # inline. Oracle (< 23c) also lacks it, but sqlglot/most targets accept it;
    # we keep the inline form there and special-case only T-SQL.
    inline_exists = ""
    tsql_guard = ""
    if node.if_not_exists:
        if dialect == "tsql":
            tsql_guard = (
                f"IF OBJECT_ID(N'{_object_id_name(node.table)}', N'U') " "IS NULL\n"
            )
        else:
            inline_exists = "IF NOT EXISTS "
    exists = inline_exists

    if node.as_select:
        select = _emit_select(node.as_select, dialect)
        return f"{tsql_guard}CREATE {temp}TABLE {exists}{table} AS\n{select}"

    if node.columns:
        col_defs = []
        set_type_notes: list[str] = []
        for col in node.columns:
            check = ""
            if col.data_type.name.upper() in ("ENUM", "SET") and col.data_type.values:
                # MySQL keeps the native type; everyone else gets VARCHAR
                # sized to the values, plus a CHECK for ENUM semantics.
                dtype, check, note = _emit_enum_type(col, dialect)
                if note:
                    set_type_notes.append(note)
            else:
                dtype = _portable_type_name(col.data_type.name, dialect)
                # If the mapped name already carries a length (e.g. CHAR(36)),
                # don't append the caller's params on top of it. PostgreSQL
                # integer types take no parameters at all — a MySQL display
                # width (TINYINT(1), INT(11)) would be a syntax error.
                skip_params = dialect == "postgresql" and dtype.upper() in (
                    "SMALLINT",
                    "INT",
                    "INTEGER",
                    "BIGINT",
                )
                if col.data_type.params and "(" not in dtype and not skip_params:
                    dtype += f"({', '.join(str(p) for p in col.data_type.params)})"
                # A character type with no length is invalid DDL in most engines
                # (MySQL/Oracle reject it; PostgreSQL treats bare VARCHAR as
                # unlimited but that is not what was meant). It originates from a
                # T-SQL VARCHAR(MAX)/NVARCHAR(MAX) whose MAX marker is dropped
                # during IR conversion (the non-numeric param is not preserved).
                # Map the bare character type to the dialect's large-text type.
                if not col.data_type.params:
                    _base = dtype.upper().split("(")[0]
                    _bigtext = _BARE_CHAR_BIGTEXT.get(dialect, {}).get(_base)
                    if _bigtext:
                        dtype = _bigtext
            pk = " PRIMARY KEY" if col.primary_key else ""
            unique = " UNIQUE" if col.unique else ""
            default = ""
            if col.default is not None:
                default_sql = _emit_expression(col.default, dialect)
                if dialect == "oracle":
                    default_sql = re.sub(
                        r"(?i)\bNEWSEQUENTIALID\s*\(\s*\)", "SYS_GUID()", default_sql
                    )
                    default_sql = re.sub(
                        r"(?i)\bNEWID\s*\(\s*\)", "SYS_GUID()", default_sql
                    )
                elif dialect == "mysql":
                    # MySQL has no sequential-GUID generator; UUID() is the
                    # closest equivalent. A function default requires the
                    # parenthesized "(expr)" form (MySQL 8.0.13+).
                    default_sql = re.sub(
                        r"(?i)\b(?:NEWSEQUENTIALID|NEWID)\s*\(\s*\)",
                        "(UUID())",
                        default_sql,
                    )
                elif dialect == "postgresql":
                    # PostgreSQL: gen_random_uuid() (pgcrypto / built-in 13+).
                    default_sql = re.sub(
                        r"(?i)\b(?:NEWSEQUENTIALID|NEWID)\s*\(\s*\)",
                        "gen_random_uuid()",
                        default_sql,
                    )
                if dialect in ("postgresql", "oracle"):
                    # Both reject the parenthesized CURRENT_TIMESTAMP() form
                    # in DDL defaults (audit 2026-07-02, S1-10).
                    default_sql = re.sub(
                        r"(?i)\bCURRENT_TIMESTAMP\s*\(\s*\)",
                        "CURRENT_TIMESTAMP",
                        default_sql,
                    )
                if dialect == "postgresql" and dtype.upper() == "BOOLEAN":
                    # A source BIT column arrives with a 0/1 default;
                    # PostgreSQL rejects an integer default on BOOLEAN.
                    m_bool = re.fullmatch(r"\(*\s*([01])\s*\)*", default_sql)
                    if m_bool:
                        default_sql = "TRUE" if m_bool.group(1) == "1" else "FALSE"
                default = f" DEFAULT {default_sql}"
            identity = ""
            if col.identity:
                if dialect == "mysql":
                    identity = " AUTO_INCREMENT"
                elif dialect == "postgresql":
                    # BIGSERIAL when the column is a 64-bit integer so a FK from
                    # another BIGINT column matches (SERIAL is only int4).
                    dtype = "BIGSERIAL" if dtype.upper() == "BIGINT" else "SERIAL"
                    identity = ""
                elif dialect == "tsql":
                    identity = " IDENTITY(1,1)"
                else:
                    identity = " GENERATED BY DEFAULT AS IDENTITY"
            # Oracle column attribute order: type [identity] [DEFAULT val] [NOT NULL].
            # Other dialects: type [identity] [NOT NULL] [DEFAULT val].
            if dialect == "oracle":
                # Identity columns are implicitly NOT NULL in Oracle; adding NOT NULL
                # explicitly after AS IDENTITY can cause parser errors in some versions.
                nullable = "" if (col.nullable or col.identity) else " NOT NULL"
                col_name = _ident(col.name, col.quoted, dialect)
                col_defs.append(
                    f"  {col_name} {dtype}{identity}{default}{nullable}{pk}"
                    f"{unique}{check}"
                )
            else:
                nullable = "" if col.nullable else " NOT NULL"
                col_name = _ident(col.name, col.quoted, dialect)
                col_defs.append(
                    f"  {col_name} {dtype}{identity}{nullable}{default}{pk}"
                    f"{unique}{check}"
                )
        # Table-level constraints (PK/FK/UNIQUE/CHECK), re-transpiled.
        # A fragment may come back as a documented comment (e.g. a generated
        # column with no portable type); those can't live inside the
        # parenthesized column list, so collect them and append afterwards.
        trailing_comments: list[str] = list(set_type_notes)
        for constraint in node.table_constraints:
            emitted = _emit_passthrough_inline(constraint, dialect)
            if emitted.lstrip().startswith("--"):
                trailing_comments.append(emitted.strip())
            else:
                col_defs.append(f"  {emitted}")
        cols = ",\n".join(col_defs)
        result = f"{tsql_guard}CREATE {temp}TABLE {exists}{table} (\n{cols}\n)"
        if trailing_comments:
            result += "\n" + "\n".join(trailing_comments)
        return result

    return f"{tsql_guard}CREATE {temp}TABLE {exists}{table}"


def _strip_dbo_function_name(node: FunctionCall) -> FunctionCall:
    """Return a copy of ``node`` with a leading ``dbo.`` removed from its name.

    A user function call like ``dbo.fn_tax`` keeps just ``fn_tax`` for the
    non-T-SQL engines, where the ``dbo`` default schema does not exist. The
    qualifier may be bare, bracketed (``[dbo].``) or quoted (``"dbo".``).
    """
    new_name = re.sub(r'(?i)^\s*(?:\[dbo\]|"dbo"|dbo)\s*\.\s*', "", node.name)
    if new_name == node.name:
        return node
    return dataclasses.replace(node, name=new_name)


def _strip_dbo_schema_qualifier(sql: str) -> str:
    """Remove the T-SQL ``dbo.`` schema qualifier from object names in ``sql``.

    ``dbo`` is the T-SQL default schema; it names no real schema on Oracle/
    PostgreSQL and a non-existent database on MySQL, so a qualified reference
    like ``dbo.invoice`` (in a CREATE SEQUENCE/INDEX, a view body, an FK
    reference, etc.) must drop the prefix for those engines. The qualifier may
    be bare (``dbo.``), bracketed (``[dbo].``) or quoted (``"dbo".``). Only a
    ``dbo`` immediately followed by ``.`` and an identifier is touched, so a
    column or value literally containing the text is left alone.
    """
    return re.sub(
        r'(?i)(?:\[dbo\]|"dbo"|\bdbo)\s*\.\s*(?=[\w\[\"])',
        "",
        sql,
    )


def _strip_dbo_from_references(fragment: str) -> str:
    """Remove a leading ``dbo.`` qualifier from a FOREIGN KEY reference target.

    A T-SQL ``REFERENCES dbo.customer (id)`` must become ``REFERENCES customer
    (id)`` on Oracle/MySQL/PostgreSQL, where ``dbo`` names no real schema. Only
    the table named right after ``REFERENCES`` is touched; the qualifier may be
    bare (``dbo.``), bracketed (``[dbo].``) or quoted (``"dbo".``).
    """
    return re.sub(
        r'(?i)(\bREFERENCES\s+)(?:\[dbo\]|"dbo"|dbo)\s*\.\s*',
        r"\1",
        fragment,
    )


def _emit_passthrough_inline(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a constraint fragment for inclusion inside CREATE TABLE.

    Wraps the fragment in a throwaway table so sqlglot will transpile the
    constraint, then extracts it back out. Falls back to the raw fragment.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)
    fragment_sql = node.sql
    if node.source_dialect == "tsql" and dialect != "tsql":
        # T-SQL physical hints in a table constraint (the CLUSTERED keyword,
        # WITH (...) storage options, ON [filegroup]) have no meaning on the
        # other engines, and sqlglot's non-T-SQL writers render them as bogus
        # comma-separated column-list items ("PRIMARY KEY, CLUSTERED (...),
        # WITH (...), ON ..."). Strip them before re-transpiling.
        fragment_sql = re.sub(r"(?i)\b(NON)?CLUSTERED\s+", "", fragment_sql)
        fragment_sql = re.sub(r"(?i)\s*WITH\s*\([^)]*\)", "", fragment_sql)
        fragment_sql = re.sub(r"(?i)\s+ON\s+(?:\[[^\]]+\]|\w+)\s*$", "", fragment_sql)
        # ASC/DESC are index hints inside a PK/UNIQUE column list; sqlglot's
        # T-SQL reader itself rejects them once the CLUSTERED keyword is gone.
        if re.match(r"(?i)\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE)\b", fragment_sql):
            fragment_sql = re.sub(r"(?i)\s+(?:ASC|DESC)\b", "", fragment_sql)
    try:
        wrapped = f"CREATE TABLE __c__ (x INT, {fragment_sql})"
        out = sqlglot.transpile(wrapped, read=read, write=write)[0]
        inner = out[out.index("(") + 1 : out.rindex(")")]
        # Drop the placeholder "x INT," prefix.
        parts = inner.split(",", 1)
        if len(parts) == 2:
            fragment = parts[1].strip()
            # PostgreSQL and Oracle require an explicit type before a generated
            # column. T-SQL computed columns carry no declared type, so sqlglot
            # emits a typeless definition -- either "col GENERATED ALWAYS AS
            # (...) STORED" or "col AS (...) PERSISTED" -- that those engines
            # reject. Emit a documented comment instead of invalid SQL.
            is_generated = re.search(
                r"(?i)\bGENERATED\s+ALWAYS\s+AS\b|\bAS\s*\(", fragment
            )
            has_type = re.search(
                r"(?i)^\s*[\w\[\]\".]+\s+"
                r"(INT|INTEGER|BIGINT|SMALLINT|TINYINT|NUMERIC|DECIMAL|FLOAT|"
                r"REAL|DOUBLE|CHAR|VARCHAR|NVARCHAR|TEXT|DATE|TIMESTAMP|"
                r"BOOLEAN|NUMBER|RAW)",
                fragment,
            )
            if (
                dialect in ("postgresql", "oracle", "mysql")
                and is_generated
                and not has_type
            ):
                col_name = fragment.split()[0]
                return (
                    f"-- UNIQUE: {dialect} requires an explicit type for the "
                    f"generated column {col_name}; original computed column: "
                    f"{node.sql}"
                )
            # Oracle and PostgreSQL do not allow NULLS FIRST / NULLS LAST or
            # ASC / DESC inside PRIMARY KEY or UNIQUE constraint column lists
            # (only in ORDER BY / index specs). sqlglot adds the NULLS
            # ordering when emulating T-SQL ordering; ASC/DESC come straight
            # from the SSMS-generated source and are index hints, not
            # semantics, so dropping them is safe.
            if dialect in ("oracle", "postgresql"):
                fragment = re.sub(r"(?i)\s+NULLS\s+(?:FIRST|LAST)", "", fragment)
            if dialect != "tsql" and re.match(
                r"(?i)\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE)\b", fragment
            ):
                fragment = re.sub(r"(?i)\s+(?:ASC|DESC)\b", "", fragment)
            # MySQL's named inline key "UNIQUE name (cols)" is only valid
            # MySQL; the portable spelling is CONSTRAINT name UNIQUE (cols).
            if dialect != "mysql":
                fragment = re.sub(
                    r"(?i)^UNIQUE\s+(?:KEY\s+|INDEX\s+)?([`\"\[\]\w]+)\s*\(",
                    r"CONSTRAINT \1 UNIQUE (",
                    fragment,
                )
            # A FOREIGN KEY may REFERENCE a dbo-qualified table. The "dbo" schema
            # is meaningless on the other engines (and would name a non-existent
            # schema/database), exactly as for the table being created, so strip
            # it from the reference target too.
            if dialect in ("oracle", "mysql", "postgresql"):
                fragment = _strip_dbo_from_references(fragment)
            return fragment
    except Exception as e:  # noqa: BLE001
        logger.warning("constraint transpile error: %s", e)
    return node.sql


def _emit_create_view(node: CreateViewStatement, dialect: str) -> str:
    """Emit a CREATE VIEW statement."""
    name = _emit_table_ref(node.name, dialect)
    replace = "OR REPLACE " if node.or_replace else ""
    query = _emit_select(node.query, dialect)
    return f"CREATE {replace}VIEW {name} AS\n{query}"


def _emit_drop(node: DropStatement, dialect: str) -> str:
    """Emit a DROP statement."""
    name = _emit_table_ref(node.name)
    exists = "IF EXISTS " if node.if_exists else ""
    cascade = " CASCADE" if node.cascade else ""
    return f"DROP {node.object_type} {exists}{name}{cascade}"


_IDENT_QUOTES = {
    "tsql": ("[", "]"),
    "mysql": ("`", "`"),
    "postgresql": ('"', '"'),
    "oracle": ('"', '"'),
}


def _quote_ident(name: str, dialect: str | None) -> str:
    """Wrap *name* in the target dialect's identifier quote characters.

    Quoting is translated between engines, never stripped (audit 2026-07-02,
    S1-1): a quoted identifier may be a reserved word or case/space-sensitive,
    so dropping the quotes changes meaning or breaks the syntax outright.
    """
    left, right = _IDENT_QUOTES.get(dialect or "tsql", ('"', '"'))
    escaped = name.replace(right, right * 2)
    return f"{left}{escaped}{right}"


def _ident(name: str, quoted: bool, dialect: str | None) -> str:
    """Emit an identifier, re-quoting it when it was quoted in the source."""
    return _quote_ident(name, dialect) if quoted else name


def _emit_expression(node: ASTNode, dialect: str) -> str:
    """Emit an expression node as SQL text."""
    if isinstance(node, ColumnRef):
        name = _ident(node.name, node.quoted, dialect)
        if node.table:
            table = _ident(node.table, node.table_quoted, dialect)
            return f"{table}.{name}"
        return name

    if isinstance(node, Star):
        if node.table:
            return f"{node.table}.*"
        return "*"

    if isinstance(node, Literal):
        if node.value is None:
            return "NULL"
        if node.dtype == "boolean":
            # T-SQL and Oracle (pre-23c) have no boolean literals in SQL
            # contexts (audit 2026-07-02, S1-9).
            if dialect in ("tsql", "oracle"):
                return "1" if node.value else "0"
            return "TRUE" if node.value else "FALSE"
        if node.dtype == "string" or (
            node.dtype == "unknown" and isinstance(node.value, str)
        ):
            escaped = str(node.value).replace("'", "''")
            return f"'{escaped}'"
        return str(node.value)

    if isinstance(node, Alias):
        inner = _emit_expression(node.expression, dialect)
        return f"{inner} AS {_ident(node.name, node.quoted, dialect)}"

    if isinstance(node, FunctionCall):
        return _emit_function(node, dialect)

    if isinstance(node, BinaryOp):
        return _emit_binary(node, dialect)

    if isinstance(node, UnaryOp):
        return _emit_unary(node, dialect)

    if isinstance(node, CaseExpression):
        return _emit_case(node, dialect)

    if isinstance(node, CastExpression):
        inner = _emit_expression(node.expression, dialect)
        dtype = node.target_type.name
        if node.target_type.params:
            dtype += f"({', '.join(str(p) for p in node.target_type.params)})"
        return f"CAST({inner} AS {dtype})"

    if isinstance(node, SubqueryExpression):
        return f"({_emit_select(node.query, dialect)})"

    if isinstance(node, WindowFunction):
        return _emit_window(node, dialect)

    if isinstance(node, TableRef):
        return _emit_table_ref(node, dialect)

    if isinstance(node, RawSQL):
        # Inline expression context (e.g. a column DEFAULT): emit the raw
        # SQL directly without a wrapping comment, which would be invalid
        # inside a column definition.
        return node.sql

    return str(node)


_DATE_UNIT_ALIASES = {
    "DD": "DAY",
    "D": "DAY",
    "DAYOFYEAR": "DAY",
    "MM": "MONTH",
    "M": "MONTH",
    "YY": "YEAR",
    "YYYY": "YEAR",
    "HH": "HOUR",
    "MI": "MINUTE",
    "N": "MINUTE",
    "SS": "SECOND",
    "S": "SECOND",
    "WK": "WEEK",
    "WW": "WEEK",
    "W": "WEEK",
}
_DATE_UNITS = {"DAY", "WEEK", "MONTH", "YEAR", "HOUR", "MINUTE", "SECOND"}

# sqlglot canonicalization wrappers that must never reach emitted SQL.
_SQLGLOT_WRAPPERS = {"TIME_STR_TO_TIME", "TS_OR_DS_TO_DATE", "TS_OR_DS_TO_TIMESTAMP"}


def _unwrap_sqlglot_wrappers(node: ASTNode) -> ASTNode:
    """Strip sqlglot-internal cast pseudo-functions from an argument."""
    while (
        isinstance(node, FunctionCall)
        and node.name.upper() in _SQLGLOT_WRAPPERS
        and len(node.args) == 1
    ):
        node = node.args[0]
    return node


def _date_unit_name(node: ASTNode) -> str | None:
    """Extract a normalized date-part unit (DAY, MONTH, ...) from an IR arg."""
    raw: str | None = None
    if isinstance(node, RawSQL):
        raw = node.sql
    elif isinstance(node, Literal) and isinstance(node.value, str):
        raw = node.value
    elif isinstance(node, ColumnRef) and not node.table:
        raw = node.name
    if raw is None:
        return None
    unit = _DATE_UNIT_ALIASES.get(raw.strip().upper(), raw.strip().upper())
    return unit if unit in _DATE_UNITS else None


def _emit_date_add(node: FunctionCall, dialect: str) -> str | None:
    """Emit DATE_ADD/DATE_SUB/DATEADD with the target's own idiom.

    The IR canonical form is ``(ts, n, unit)``. Emitting the 3-argument
    ``DATE_ADD(ts, 7, DAY)`` form is invalid on every engine (audit
    2026-07-02, S1-4); each target needs its native spelling.
    """
    if len(node.args) != 3:
        return None
    unit = _date_unit_name(node.args[2])
    if unit is None:
        return None
    ts = _emit_expression(_unwrap_sqlglot_wrappers(node.args[0]), dialect)
    amount = node.args[1]
    literal_n: str | None = None
    if isinstance(amount, Literal) and re.fullmatch(r"-?\d+", str(amount.value)):
        # MySQL parses INTERVAL amounts as string literals; use the bare number.
        literal_n = str(amount.value)
    n = literal_n if literal_n is not None else _emit_expression(amount, dialect)
    sub = node.name.upper() == "DATE_SUB"

    if dialect == "mysql":
        fn = "DATE_SUB" if sub else "DATE_ADD"
        return f"{fn}({ts}, INTERVAL {n} {unit})"
    if dialect == "tsql":
        signed = (f"-{n}" if literal_n is not None else f"-({n})") if sub else n
        return f"DATEADD({unit}, {signed}, {ts})"
    if dialect == "postgresql":
        op = "-" if sub else "+"
        if literal_n is not None:
            return f"{ts} {op} INTERVAL '{n} {unit}'"
        return f"{ts} {op} ({n}) * INTERVAL '1 {unit}'"
    if dialect == "oracle":
        if unit in ("MONTH", "YEAR"):
            if unit == "MONTH":
                months = n
            elif literal_n is not None:
                months = str(int(literal_n) * 12)
            else:
                months = f"({n}) * 12"
            if sub:
                signed = f"-{months}" if literal_n is not None else f"-({months})"
            else:
                signed = months
            return f"ADD_MONTHS({ts}, {signed})"
        op = "-" if sub else "+"
        if unit == "WEEK":
            days = str(int(literal_n) * 7) if literal_n is not None else f"({n}) * 7"
            return f"{ts} {op} NUMTODSINTERVAL({days}, 'DAY')"
        return f"{ts} {op} NUMTODSINTERVAL({n}, '{unit}')"
    return None


def _emit_date_diff(node: FunctionCall, dialect: str) -> str | None:
    """Emit DATEDIFF with T-SQL boundary-count semantics per target.

    IR canonical argument order is ``(end, start, unit)``. T-SQL DATEDIFF
    counts unit-boundary crossings, so month/year use calendar arithmetic
    rather than elapsed-interval functions (audit 2026-07-02, S1-4).
    """
    if len(node.args) != 3:
        return None
    unit = _date_unit_name(node.args[2])
    if unit is None:
        return None
    end = _emit_expression(_unwrap_sqlglot_wrappers(node.args[0]), dialect)
    start = _emit_expression(_unwrap_sqlglot_wrappers(node.args[1]), dialect)

    if dialect == "tsql":
        return f"DATEDIFF({unit}, {start}, {end})"
    if dialect == "mysql":
        if unit == "DAY":
            return f"DATEDIFF({end}, {start})"
        if unit == "WEEK":
            return f"FLOOR(DATEDIFF({end}, {start}) / 7)"
        if unit == "MONTH":
            return (
                f"((YEAR({end}) * 12 + MONTH({end})) - "
                f"(YEAR({start}) * 12 + MONTH({start})))"
            )
        if unit == "YEAR":
            return f"(YEAR({end}) - YEAR({start}))"
        k = {"HOUR": 3600, "MINUTE": 60, "SECOND": 1}[unit]
        return (
            f"(FLOOR(UNIX_TIMESTAMP({end}) / {k}) - "
            f"FLOOR(UNIX_TIMESTAMP({start}) / {k}))"
        )
    if dialect == "postgresql":
        if unit == "DAY":
            return f"(CAST({end} AS DATE) - CAST({start} AS DATE))"
        if unit == "WEEK":
            return f"FLOOR((CAST({end} AS DATE) - CAST({start} AS DATE)) / 7)"
        if unit == "MONTH":
            return (
                f"((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))"
            )
        if unit == "YEAR":
            return f"(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))"
        k = {"HOUR": 3600, "MINUTE": 60, "SECOND": 1}[unit]
        return (
            f"(FLOOR(EXTRACT(EPOCH FROM {end}) / {k}) - "
            f"FLOOR(EXTRACT(EPOCH FROM {start}) / {k}))"
        )
    if dialect == "oracle":
        if unit == "DAY":
            return f"(TRUNC(CAST({end} AS DATE)) - TRUNC(CAST({start} AS DATE)))"
        if unit == "WEEK":
            return (
                f"FLOOR((TRUNC(CAST({end} AS DATE)) - "
                f"TRUNC(CAST({start} AS DATE))) / 7)"
            )
        if unit == "MONTH":
            return (
                f"((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))"
            )
        if unit == "YEAR":
            return f"(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))"
        trunc_fmt = {"HOUR": "HH24", "MINUTE": "MI"}.get(unit)
        mult = {"HOUR": 24, "MINUTE": 1440, "SECOND": 86400}[unit]
        if trunc_fmt:
            return (
                f"ROUND((TRUNC(CAST({end} AS DATE), '{trunc_fmt}') - "
                f"TRUNC(CAST({start} AS DATE), '{trunc_fmt}')) * {mult})"
            )
        return f"ROUND((CAST({end} AS DATE) - CAST({start} AS DATE)) * {mult})"
    return None


def _emit_group_concat(node: FunctionCall, dialect: str) -> str | None:
    """Emit the string-aggregation family in the target's own spelling.

    IR canonical form: ``GROUP_CONCAT(expr[, separator])``. An Oracle LISTAGG
    source may carry its WITHIN GROUP ordering folded into the first argument
    as RawSQL ("expr ORDER BY ...").
    """
    first = node.args[0]
    expr_sql: str
    order_sql: str | None = None
    if isinstance(first, RawSQL) and " ORDER BY " in first.sql:
        expr_sql, order_sql = first.sql.split(" ORDER BY ", 1)
        expr_sql = expr_sql.strip()
        order_sql = re.sub(r"\s+NULLS\s+(FIRST|LAST)\s*$", "", order_sql.strip())
    else:
        expr_sql = _emit_expression(first, dialect)

    sep: str | None = None
    if len(node.args) > 1:
        sep_node = node.args[1]
        if isinstance(sep_node, Literal) and isinstance(sep_node.value, str):
            sep = sep_node.value
        else:
            return None  # dynamic separator: fall through to generic emission
    distinct = "DISTINCT " if node.distinct else ""

    def quoted(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    if dialect == "mysql":
        order = f" ORDER BY {order_sql}" if order_sql else ""
        separator = f" SEPARATOR {quoted(sep)}" if sep is not None else ""
        return f"GROUP_CONCAT({distinct}{expr_sql}{order}{separator})"
    if dialect == "postgresql":
        order = f" ORDER BY {order_sql}" if order_sql else ""
        return f"STRING_AGG({distinct}{expr_sql}, {quoted(sep or ',')}{order})"
    if dialect == "tsql":
        within = f" WITHIN GROUP (ORDER BY {order_sql})" if order_sql else ""
        return f"STRING_AGG({expr_sql}, {quoted(sep or ',')}){within}"
    if dialect == "oracle":
        # LISTAGG requires WITHIN GROUP; default to ordering by the
        # aggregated expression itself when the source specified none.
        order = order_sql or expr_sql
        return (
            f"LISTAGG({distinct}{expr_sql}, {quoted(sep or ',')}) "
            f"WITHIN GROUP (ORDER BY {order})"
        )
    return None


def _emit_function(node: FunctionCall, dialect: str) -> str:
    """Emit a function call."""
    fn_name = node.name.upper()
    # sqlglot-internal cast wrappers must never reach the output.
    if fn_name in _SQLGLOT_WRAPPERS and len(node.args) == 1:
        return _emit_expression(node.args[0], dialect)

    # Date arithmetic has a distinct spelling per engine.
    if fn_name in ("DATE_ADD", "DATE_SUB", "DATEADD"):
        emitted = _emit_date_add(node, dialect)
        if emitted is not None:
            return emitted
    if fn_name in ("DATEDIFF", "TIMESTAMPDIFF"):
        emitted = _emit_date_diff(node, dialect)
        if emitted is not None:
            return emitted

    # String aggregation: IR canonical form is GROUP_CONCAT(expr[, sep]).
    # Each engine spells it differently, and MySQL's comma form
    # GROUP_CONCAT(x, ',') concatenates ',' onto every value instead of
    # separating them (audit 2026-07-02, S1-8/S2-1).
    if fn_name in ("GROUP_CONCAT", "STRING_AGG", "LISTAGG") and node.args:
        emitted = _emit_group_concat(node, dialect)
        if emitted is not None:
            return emitted

    # Conditional shorthand: MySQL IF() / T-SQL IIF(). Neither exists on
    # PostgreSQL/Oracle, whose spelling is a searched CASE.
    if fn_name in ("IF", "IIF") and len(node.args) == 3:
        cond, then_v, else_v = (_emit_expression(a, dialect) for a in node.args)
        if dialect == "tsql":
            return f"IIF({cond}, {then_v}, {else_v})"
        if dialect == "mysql":
            return f"IF({cond}, {then_v}, {else_v})"
        return f"CASE WHEN {cond} THEN {then_v} ELSE {else_v} END"

    # A user function may be schema-qualified (dbo.fn_tax). The "dbo" default
    # schema is meaningless on the other engines, so drop it there, as for any
    # other object reference. Built-in names never carry it.
    if dialect in ("oracle", "mysql", "postgresql") and "." in node.name:
        node = _strip_dbo_function_name(node)
    # Special handling for CURRENT_TIMESTAMP (no parens in some dialects)
    if node.name.upper() == "CURRENT_TIMESTAMP" and not node.args:
        return CURRENT_TIMESTAMP_EXPR.get(dialect, "CURRENT_TIMESTAMP")

    # Oracle niladic "now" spellings that sqlglot passes through as anonymous
    # calls. SYSTIMESTAMP has no cross-engine parens form (it would leak as an
    # invalid SYSTIMESTAMP() — invalid even on Oracle); SYSDATE is included for
    # the same passthrough case. Map to each dialect's current-timestamp form.
    if node.name.upper() in ("SYSTIMESTAMP", "SYSDATE") and not node.args:
        return CURRENT_TIMESTAMP_EXPR.get(dialect, "CURRENT_TIMESTAMP")

    # Substring position: canonical CHARINDEX(needle, haystack[, start]) maps to
    # each engine's function with its own argument order.
    if node.name.upper() == "CHARINDEX" and len(node.args) >= 2:
        needle = _emit_expression(node.args[0], dialect)
        haystack = _emit_expression(node.args[1], dialect)
        start = _emit_expression(node.args[2], dialect) if len(node.args) > 2 else None
        if dialect == "tsql":
            inner = f"{needle}, {haystack}" + (f", {start}" if start else "")
            return f"CHARINDEX({inner})"
        if dialect == "mysql":
            # LOCATE(needle, haystack[, start])
            inner = f"{needle}, {haystack}" + (f", {start}" if start else "")
            return f"LOCATE({inner})"
        if dialect == "oracle":
            # INSTR(haystack, needle[, start])
            inner = f"{haystack}, {needle}" + (f", {start}" if start else "")
            return f"INSTR({inner})"
        # postgresql: STRPOS has no start arg; use POSITION(needle IN haystack)
        # and add the offset when a start position is given.
        if start:
            return (
                f"(POSITION({needle} IN SUBSTRING({haystack} FROM {start})) "
                f"+ {start} - 1)"
            )
        return f"POSITION({needle} IN {haystack})"

    # Map canonical function names to dialect-specific names
    name = _map_function_name(node.name, dialect)

    distinct = "DISTINCT " if node.distinct else ""
    args = ", ".join(_emit_expression(a, dialect) for a in node.args)
    return f"{name}({distinct}{args})"


def _map_function_name(name: str, dialect: str) -> str:
    """Map a canonical function name to the dialect-specific equivalent."""
    upper = name.upper()

    # COALESCE stays COALESCE everywhere (it's standard SQL)
    if upper == "COALESCE":
        return "COALESCE"

    # LENGTH
    if upper == "LENGTH":
        if dialect == "tsql":
            return "LEN"
        return "LENGTH"

    # SUBSTRING
    if upper == "SUBSTRING":
        if dialect == "oracle":
            return "SUBSTR"
        return "SUBSTRING"

    # UUID generation: sqlglot canonicalizes NEWID/UUID/GEN_RANDOM_UUID to
    # UUID, which only exists on MySQL. Each engine has its own function
    # (found by a hardened test during audit 2026-07-02 remediation).
    if upper in ("UUID", "NEWID", "GEN_RANDOM_UUID", "SYS_GUID"):
        return UUID_FUNCTION.get(dialect, name)

    return name


def _emit_binary(node: BinaryOp, dialect: str) -> str:
    """Emit a binary operation."""
    left = _emit_expression(node.left, dialect)
    right = _emit_expression(node.right, dialect)

    op_map = {
        BinaryOperator.EQ: "=",
        BinaryOperator.NEQ: "<>",
        BinaryOperator.LT: "<",
        BinaryOperator.GT: ">",
        BinaryOperator.LTE: "<=",
        BinaryOperator.GTE: ">=",
        BinaryOperator.AND: "AND",
        BinaryOperator.OR: "OR",
        BinaryOperator.ADD: "+",
        BinaryOperator.SUB: "-",
        BinaryOperator.MUL: "*",
        BinaryOperator.DIV: "/",
        BinaryOperator.MOD: "%",
        BinaryOperator.LIKE: "LIKE",
        BinaryOperator.ILIKE: "ILIKE",
        BinaryOperator.IN: "IN",
        BinaryOperator.NOT_IN: "NOT IN",
        BinaryOperator.BETWEEN: "BETWEEN",
        BinaryOperator.CONCAT: "||",
        BinaryOperator.BIT_AND: "&",
        BinaryOperator.BIT_OR: "|",
        BinaryOperator.BIT_XOR: "^",
        BinaryOperator.BIT_LSHIFT: "<<",
        BinaryOperator.BIT_RSHIFT: ">>",
    }

    op = op_map[node.operator]

    # Dialect-specific overrides
    if node.operator == BinaryOperator.CONCAT:
        if dialect == "tsql":
            op = "+"
        elif dialect == "mysql":
            return f"CONCAT({left}, {right})"

    if node.operator == BinaryOperator.MOD and dialect == "oracle":
        return f"MOD({left}, {right})"

    # PostgreSQL spells bitwise XOR as "#" (and has no "^" bitwise operator;
    # "^" there is exponentiation). Oracle has no infix bitwise operators at
    # all — only BITAND(); the other forms have no faithful translation, so
    # they are left as-is and flagged as a known limitation in the docs.
    if node.operator == BinaryOperator.BIT_XOR and dialect == "postgresql":
        op = "#"

    return f"{left} {op} {right}"


def _emit_unary(node: UnaryOp, dialect: str) -> str:
    """Emit a unary operation."""
    operand = _emit_expression(node.operand, dialect)

    if node.operator == UnaryOperator.NOT:
        return f"NOT {operand}"
    if node.operator == UnaryOperator.NEGATIVE:
        return f"-{operand}"
    if node.operator == UnaryOperator.IS_NULL:
        return f"{operand} IS NULL"
    if node.operator == UnaryOperator.IS_NOT_NULL:
        return f"{operand} IS NOT NULL"
    if node.operator == UnaryOperator.EXISTS:
        return f"EXISTS ({operand})"

    return operand


def _emit_case(node: CaseExpression, dialect: str) -> str:
    """Emit a CASE expression."""
    parts = ["CASE"]

    if node.operand:
        parts[0] += f" {_emit_expression(node.operand, dialect)}"

    for condition, result in node.whens:
        cond = _emit_expression(condition, dialect)
        res = _emit_expression(result, dialect)
        parts.append(f"  WHEN {cond} THEN {res}")

    if node.else_expr:
        parts.append(f"  ELSE {_emit_expression(node.else_expr, dialect)}")

    parts.append("END")
    return "\n".join(parts)


def _emit_window(node: WindowFunction, dialect: str) -> str:
    """Emit a window function."""
    func = _emit_function(node.function, dialect)
    spec_parts: list[str] = []

    if node.window.partition_by:
        partition = ", ".join(
            _emit_expression(p, dialect) for p in node.window.partition_by
        )
        spec_parts.append(f"PARTITION BY {partition}")

    if node.window.order_by:
        order = ", ".join(_emit_order_item(o, dialect) for o in node.window.order_by)
        spec_parts.append(f"ORDER BY {order}")

    spec = " ".join(spec_parts)
    return f"{func} OVER ({spec})"


def _emit_table_ref(node: TableRef, dialect: str | None = None) -> str:
    """Emit a table reference.

    When ``dialect`` is one of the non-T-SQL engines, the T-SQL default schema
    ``dbo`` is dropped: it names no real schema on Oracle/PostgreSQL and would
    name a non-existent database on MySQL. Passing ``dialect=None`` keeps the
    reference verbatim (used where the schema must be preserved, e.g. a T-SQL
    OBJECT_ID guard).
    """
    parts = []
    if node.database:
        parts.append(node.database)
    schema = node.schema
    if dialect in ("oracle", "mysql", "postgresql") and schema == "dbo":
        schema = None
    if schema:
        parts.append(_ident(schema, node.schema_quoted, dialect))
    parts.append(_ident(node.name, node.quoted, dialect))
    result = ".".join(parts)

    if node.alias:
        result += f" {node.alias}"

    return result


def _object_id_name(node: TableRef) -> str:
    """Build a schema-qualified name for a T-SQL OBJECT_ID() guard.

    Excludes any alias and the database part (OBJECT_ID resolves within the
    current database), keeping just ``[schema.]table``.
    """
    parts = []
    if node.schema:
        parts.append(node.schema)
    parts.append(node.name)
    return ".".join(parts)


def _emit_join(join: JoinClause, dialect: str, left_name: str | None = None) -> str:
    """Emit a JOIN clause.

    ``left_name`` is the FROM relation's name/alias, supplied only for
    single-join SELECTs; it lets a ``USING (...)`` join be rewritten as an
    explicit ``ON`` for T-SQL, which has no USING syntax.
    """
    type_map = {
        JoinType.INNER: "INNER JOIN",
        JoinType.LEFT: "LEFT JOIN",
        JoinType.RIGHT: "RIGHT JOIN",
        JoinType.FULL: "FULL OUTER JOIN",
        JoinType.CROSS: "CROSS JOIN",
        JoinType.NATURAL: "NATURAL JOIN",
        JoinType.LATERAL: "LATERAL JOIN",
    }
    join_type = type_map.get(join.join_type, "JOIN")

    if isinstance(join.table, SubqueryExpression):
        table = f"({_emit_select(join.table.query, dialect)})"
        # A subquery has no TableRef to carry the alias, so add it here.
        if join.alias:
            table += f" {join.alias}"
    else:
        # _emit_table_ref already renders the table's own alias; adding
        # join.alias again would duplicate it ("t2 b b").
        table = _emit_table_ref(join.table, dialect)
        if join.alias and not join.table.alias:
            table += f" {join.alias}"

    # A comma join parses as a bare Join with neither kind nor condition.
    # "INNER JOIN b" without ON is a syntax error on PostgreSQL/Oracle; the
    # faithful spelling of a comma join is CROSS JOIN (the WHERE clause
    # still applies the predicates). (audit 2026-07-02, S1-2)
    if join.condition is None and not join.using and join.join_type == JoinType.INNER:
        join_type = "CROSS JOIN"

    result = f"{join_type} {table}"

    if join.condition:
        result += f" ON {_emit_expression(join.condition, dialect)}"
    elif join.using:
        right = join.alias or (
            join.table.alias or join.table.name
            if isinstance(join.table, TableRef)
            else None
        )
        if dialect == "tsql" and left_name and right:
            # T-SQL has no USING; expand to the equivalent ON predicate.
            on = " AND ".join(f"{left_name}.{c} = {right}.{c}" for c in join.using)
            result += f" ON {on}"
        else:
            result += f" USING ({', '.join(join.using)})"

    return result


def _emit_order_item(item: OrderByItem, dialect: str) -> str:
    """Emit an ORDER BY item."""
    expr = _emit_expression(item.expression, dialect)
    direction = "DESC" if item.direction == OrderDirection.DESC else "ASC"
    return f"{expr} {direction}"


def _emit_limit(limit: LimitClause, dialect: str) -> str:
    """Emit LIMIT/OFFSET clause in dialect-appropriate syntax."""
    if dialect == "oracle":
        parts = []
        if limit.offset:
            parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)} ROWS")
        if limit.limit:
            # Oracle natively supports FETCH FIRST n PERCENT ROWS ONLY.
            pct = " PERCENT" if limit.percent else ""
            parts.append(
                f"FETCH FIRST {_emit_expression(limit.limit, dialect)}"
                f"{pct} ROWS ONLY"
            )
        return "\n".join(parts)

    if dialect == "tsql":
        # T-SQL uses TOP or OFFSET...FETCH
        if limit.offset:
            parts = [f"OFFSET {_emit_expression(limit.offset, dialect)} ROWS"]
            if limit.limit:
                parts.append(
                    f"FETCH NEXT {_emit_expression(limit.limit, dialect)} ROWS ONLY"
                )
            return "\n".join(parts)
        # A plain limit was already emitted as TOP in the SELECT clause.
        if limit.limit:
            return ""

    # PostgreSQL, MySQL: LIMIT ... OFFSET ...
    parts = []
    if limit.limit:
        limit_sql = f"LIMIT {_emit_expression(limit.limit, dialect)}"
        if limit.percent:
            # Neither MySQL nor PostgreSQL supports LIMIT n PERCENT. A faithful
            # rewrite needs the total row count (LIMIT CEIL(n/100 * COUNT(*))),
            # which can't be derived from a flat SELECT here; keep a valid row
            # LIMIT and document the change rather than emit invalid SQL or
            # silently drop the PERCENT semantics.
            limit_sql += (
                f" /* UNIQUE: source was TOP n PERCENT; {dialect} has no LIMIT "
                "PERCENT — emitted as a row count, adjust to "
                "CEIL(n/100 * total_rows) if a true percentage is required */"
            )
        parts.append(limit_sql)
    if limit.offset:
        parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)}")
    return "\n".join(parts)
