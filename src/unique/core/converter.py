# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import contextlib
import logging
import re

import sqlglot
import sqlglot.expressions as exp

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

logger = logging.getLogger(__name__)

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
    if isinstance(expr, exp.Func):
        return _convert_function(expr)
    if isinstance(expr, exp.Binary):
        return _convert_binary(expr)
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
    """Convert a sqlglot Update to UpdateStatement."""
    table = _convert_table_ref(expr.this)

    assignments: list[tuple[str, ASTNode]] = []
    for eq in expr.args.get("expressions", []):
        if isinstance(eq, exp.EQ):
            col_name = eq.this.name if hasattr(eq.this, "name") else str(eq.this)
            val = convert_expression(eq.expression)
            assignments.append((col_name, val))

    where = None
    where_expr = expr.find(exp.Where)
    if where_expr:
        where = convert_expression(where_expr.this)

    return UpdateStatement(
        table=table,
        assignments=tuple(assignments),
        where=where,
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
                    dtype = _convert_data_type(col_def.args["kind"])

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
                        default = RawSQL(
                            sql=kind.this.sql() if kind.this else "",
                            reason="column default",
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


def _convert_column(expr: exp.Column) -> ColumnRef:
    """Convert a column reference."""
    table = None
    if expr.table:
        table = expr.table

    return ColumnRef(name=expr.name, table=table)


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
        return TableRef(
            name=expr.name,
            schema=expr.db if expr.db else None,
            alias=alias,
            database=(
                expr.catalog if hasattr(expr, "catalog") and expr.catalog else None
            ),
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
    )


def _convert_function(expr: exp.Expression) -> FunctionCall:
    """Convert a function call."""
    name = expr.sql_name() if hasattr(expr, "sql_name") else type(expr).__name__.upper()

    args: list[ASTNode] = []
    # Some functions (e.g. Coalesce) store the first arg in `this` and the rest
    # in `expressions`. Collect `this` first when expressions also exist.
    has_expressions = bool(expr.expressions)
    if (
        expr.this is not None
        and has_expressions
        and not isinstance(expr.this, (bool, str))
    ):
        args.append(convert_expression(expr.this))
    for arg in expr.expressions or []:
        args.append(convert_expression(arg))
    # Single-argument functions: only `this`, no `expressions`
    if (
        not args
        and expr.this is not None
        and not isinstance(expr, (exp.Column, exp.Table))
    ):
        args.append(convert_expression(expr.this))

    return FunctionCall(name=name, args=tuple(args))


def _convert_binary(expr: exp.Binary) -> BinaryOp:
    """Convert a binary operation."""
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
        exp.DPipe: BinaryOperator.CONCAT,
    }

    operator = op_map.get(type(expr), BinaryOperator.EQ)

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


# Non-portable type names mapped to a portable equivalent per target dialect.
# T-SQL national/unicode types collapse to the regular char types elsewhere
# (PostgreSQL/Oracle/MySQL store text as unicode by default).
_TYPE_NAME_MAP: dict[str, dict[str, str]] = {
    "postgresql": {
        "NVARCHAR": "VARCHAR",
        "NCHAR": "CHAR",
        "NTEXT": "TEXT",
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "SMALLDATETIME": "TIMESTAMP",
        "TINYINT": "SMALLINT",
        "MONEY": "NUMERIC(19,4)",
        "BIT": "BOOLEAN",
        "UNIQUEIDENTIFIER": "UUID",
        "VARBINARY": "BYTEA",
        "IMAGE": "BYTEA",
    },
    "mysql": {
        "NVARCHAR": "VARCHAR",
        "NCHAR": "CHAR",
        "NTEXT": "TEXT",
        "DATETIME2": "DATETIME",
        "SMALLDATETIME": "DATETIME",
        "UNIQUEIDENTIFIER": "CHAR(36)",
        "UUID": "CHAR(36)",
        "MONEY": "DECIMAL(19,4)",
        "IMAGE": "LONGBLOB",
    },
    "oracle": {
        "NVARCHAR": "NVARCHAR2",
        "VARCHAR": "VARCHAR2",
        "NTEXT": "NCLOB",
        "TEXT": "CLOB",
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "TINYINT": "NUMBER(3)",
        "INT": "NUMBER(10)",
        "BIGINT": "NUMBER(19)",
        "BIT": "NUMBER(1)",
        "UNIQUEIDENTIFIER": "RAW(16)",
        "UUID": "RAW(16)",
        "MONEY": "NUMBER(19,4)",
        "IMAGE": "BLOB",
    },
    "tsql": {
        "VARCHAR2": "VARCHAR",
        "NVARCHAR2": "NVARCHAR",
        "NUMBER": "NUMERIC",
        "CLOB": "VARCHAR(MAX)",
        "NCLOB": "NVARCHAR(MAX)",
        "BLOB": "VARBINARY(MAX)",
        "BOOLEAN": "BIT",
        "BYTEA": "VARBINARY(MAX)",
        "UUID": "UNIQUEIDENTIFIER",
        "SERIAL": "INT",
    },
}


# A bare character type (no length) reaching the emitter came from a T-SQL
# VARCHAR(MAX)/NVARCHAR(MAX) whose MAX marker is lost during IR conversion.
# Map it to each engine's large-text type. Keyed by the type name AFTER
# _portable_type_name has mapped it to the target dialect.
_BARE_CHAR_BIGTEXT: dict[str, dict[str, str]] = {
    "oracle": {"VARCHAR2": "CLOB", "NVARCHAR2": "NCLOB"},
    "mysql": {"VARCHAR": "LONGTEXT", "NVARCHAR": "LONGTEXT"},
    "postgresql": {"VARCHAR": "TEXT", "NVARCHAR": "TEXT"},
    "tsql": {"VARCHAR": "VARCHAR(MAX)", "NVARCHAR": "NVARCHAR(MAX)"},
}


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

    return JoinClause(
        join_type=join_type,
        table=table,
        alias=alias,
        condition=condition,
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
        return f"-- UNIQUE: {node.reason}\n-- {node.sql}"
    if isinstance(node, PassthroughSQL):
        return _emit_passthrough(node, dialect)
    if isinstance(node, Script):
        sep = "\nGO\n\n" if dialect == "tsql" else ";\n\n"
        return sep.join(emit_node(s, dialect) for s in node.statements)

    # Expression-level emission
    return _emit_expression(node, dialect)


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
            "instead. Original:\n-- " + node.sql
        )

    # USE <db> switches the active database. Valid in MySQL and T-SQL only;
    # PostgreSQL (\\c is a psql meta-command) and Oracle have no SQL form.
    if node.kind == "USE" and dialect in ("postgresql", "oracle"):
        return (
            f"-- UNIQUE: {dialect} has no USE statement; "
            f"connect to the target database/schema instead.\n-- {node.sql}"
        )

    # MySQL has no MERGE; the idiomatic equivalent is INSERT ... ON
    # DUPLICATE KEY UPDATE, which needs key knowledge we can't infer safely.
    if node.kind == "MERGE" and dialect == "mysql":
        commented = "\n".join(f"-- {ln}" for ln in node.sql.splitlines())
        return (
            "-- UNIQUE: MySQL has no MERGE; rewrite as "
            "INSERT ... ON DUPLICATE KEY UPDATE. Original:\n" + commented
        )

    # Oracle hierarchical query: keep as-is for Oracle; for others there is
    # no faithful automatic rewrite, so emit a documented comment.
    if node.kind == "CONNECT BY" and dialect != "oracle":
        commented = "\n".join(f"-- {ln}" for ln in node.sql.splitlines())
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
            return result
    except Exception as e:  # noqa: BLE001 - report and fall back
        logger.warning("passthrough transpile error (%s): %s", node.kind, e)
    return f"-- UNIQUE: Unhandled {node.kind}\n-- {node.sql}"


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

    # SELECT
    distinct = "DISTINCT " if node.distinct else ""
    cols = ", ".join(_emit_expression(c, dialect) for c in node.columns) or "*"
    parts.append(f"SELECT {distinct}{cols}")

    # FROM
    if node.from_clause:
        if isinstance(node.from_clause, SubqueryExpression):
            parts.append(f"FROM ({_emit_select(node.from_clause.query, dialect)})")
        else:
            parts.append(f"FROM {_emit_table_ref(node.from_clause)}")

    # JOINs
    for join in node.joins:
        parts.append(_emit_join(join, dialect))

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
        parts.append(_emit_limit(node.limit, dialect))

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
    table = _emit_table_ref(node.table)
    cols = f" ({', '.join(node.columns)})" if node.columns else ""

    if node.values:
        rows = []
        for row in node.values:
            vals = ", ".join(_emit_expression(v, dialect) for v in row)
            rows.append(f"({vals})")
        values = ", ".join(rows)
        return f"INSERT INTO {table}{cols}\nVALUES {values}"

    if node.select:
        select = _emit_select(node.select, dialect)
        return f"INSERT INTO {table}{cols}\n{select}"

    return f"INSERT INTO {table}{cols}\nDEFAULT VALUES"


def _emit_update(node: UpdateStatement, dialect: str) -> str:
    """Emit an UPDATE statement."""
    table = _emit_table_ref(node.table)
    sets = ", ".join(
        f"{col} = {_emit_expression(val, dialect)}" for col, val in node.assignments
    )
    result = f"UPDATE {table}\nSET {sets}"

    if node.where:
        result += f"\nWHERE {_emit_expression(node.where, dialect)}"

    return result


def _emit_delete(node: DeleteStatement, dialect: str) -> str:
    """Emit a DELETE statement."""
    table = _emit_table_ref(node.table)
    result = f"DELETE FROM {table}"

    if node.where:
        result += f"\nWHERE {_emit_expression(node.where, dialect)}"

    return result


def _emit_create_table(node: CreateTableStatement, dialect: str) -> str:
    """Emit a CREATE TABLE statement."""
    table_node = node.table
    # The T-SQL default schema "dbo" has no meaning in Oracle, MySQL or
    # PostgreSQL — strip it so tables land in the current user's schema
    # (Oracle), the connected database (MySQL, where "dbo" would name a
    # non-existent database), or the default "public" schema (PostgreSQL,
    # where "dbo" would name a schema that doesn't exist).
    if dialect in ("oracle", "mysql", "postgresql") and getattr(
        table_node, "schema", None
    ) == ("dbo"):
        table_node = TableRef(name=table_node.name, alias=table_node.alias)
    table = _emit_table_ref(table_node)
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
        for col in node.columns:
            dtype = _portable_type_name(col.data_type.name, dialect)
            # If the mapped name already carries a length (e.g. CHAR(36)),
            # don't append the caller's params on top of it.
            if col.data_type.params and "(" not in dtype:
                dtype += f"({', '.join(str(p) for p in col.data_type.params)})"
            # A character type with no length is invalid DDL in most engines
            # (MySQL/Oracle reject it; PostgreSQL treats bare VARCHAR as
            # unlimited but that is not what was meant). It originates from a
            # T-SQL VARCHAR(MAX)/NVARCHAR(MAX) whose MAX marker is dropped during
            # IR conversion (the non-numeric param is not preserved). Map the
            # bare character type to the dialect's large-text type.
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
                default = f" DEFAULT {default_sql}"
            identity = ""
            if col.identity:
                if dialect == "mysql":
                    identity = " AUTO_INCREMENT"
                elif dialect == "postgresql":
                    dtype = "SERIAL"
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
                col_defs.append(
                    f"  {col.name} {dtype}{identity}{default}{nullable}{pk}{unique}"
                )
            else:
                nullable = "" if col.nullable else " NOT NULL"
                col_defs.append(
                    f"  {col.name} {dtype}{identity}{nullable}{default}{pk}{unique}"
                )
        # Table-level constraints (PK/FK/UNIQUE/CHECK), re-transpiled.
        # A fragment may come back as a documented comment (e.g. a generated
        # column with no portable type); those can't live inside the
        # parenthesized column list, so collect them and append afterwards.
        trailing_comments: list[str] = []
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


def _emit_passthrough_inline(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a constraint fragment for inclusion inside CREATE TABLE.

    Wraps the fragment in a throwaway table so sqlglot will transpile the
    constraint, then extracts it back out. Falls back to the raw fragment.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)
    try:
        wrapped = f"CREATE TABLE __c__ (x INT, {node.sql})"
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
            # Oracle and PostgreSQL do not allow NULLS FIRST / NULLS LAST inside
            # PRIMARY KEY or UNIQUE constraint column lists (only in ORDER BY /
            # index specs). sqlglot adds them when emulating ordering.
            if dialect in ("oracle", "postgresql"):
                fragment = re.sub(r"(?i)\s+NULLS\s+(?:FIRST|LAST)", "", fragment)
            return fragment
    except Exception as e:  # noqa: BLE001
        logger.warning("constraint transpile error: %s", e)
    return node.sql


def _emit_create_view(node: CreateViewStatement, dialect: str) -> str:
    """Emit a CREATE VIEW statement."""
    name = _emit_table_ref(node.name)
    replace = "OR REPLACE " if node.or_replace else ""
    query = _emit_select(node.query, dialect)
    return f"CREATE {replace}VIEW {name} AS\n{query}"


def _emit_drop(node: DropStatement, dialect: str) -> str:
    """Emit a DROP statement."""
    name = _emit_table_ref(node.name)
    exists = "IF EXISTS " if node.if_exists else ""
    cascade = " CASCADE" if node.cascade else ""
    return f"DROP {node.object_type} {exists}{name}{cascade}"


def _emit_expression(node: ASTNode, dialect: str) -> str:
    """Emit an expression node as SQL text."""
    if isinstance(node, ColumnRef):
        if node.table:
            return f"{node.table}.{node.name}"
        return node.name

    if isinstance(node, Star):
        if node.table:
            return f"{node.table}.*"
        return "*"

    if isinstance(node, Literal):
        if node.value is None:
            return "NULL"
        if node.dtype == "string" or (
            node.dtype == "unknown" and isinstance(node.value, str)
        ):
            escaped = str(node.value).replace("'", "''")
            return f"'{escaped}'"
        return str(node.value)

    if isinstance(node, Alias):
        inner = _emit_expression(node.expression, dialect)
        return f"{inner} AS {node.name}"

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
        return _emit_table_ref(node)

    if isinstance(node, RawSQL):
        # Inline expression context (e.g. a column DEFAULT): emit the raw
        # SQL directly without a wrapping comment, which would be invalid
        # inside a column definition.
        return node.sql

    return str(node)


def _emit_function(node: FunctionCall, dialect: str) -> str:
    """Emit a function call."""
    # Special handling for CURRENT_TIMESTAMP (no parens in some dialects)
    if node.name.upper() == "CURRENT_TIMESTAMP" and not node.args:
        if dialect == "tsql":
            return "GETDATE()"
        if dialect == "oracle":
            return "SYSDATE"
        return "CURRENT_TIMESTAMP"

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
    }

    op = op_map.get(node.operator, "=")

    # Dialect-specific overrides
    if node.operator == BinaryOperator.CONCAT:
        if dialect == "tsql":
            op = "+"
        elif dialect == "mysql":
            return f"CONCAT({left}, {right})"

    if node.operator == BinaryOperator.MOD and dialect == "oracle":
        return f"MOD({left}, {right})"

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


def _emit_table_ref(node: TableRef) -> str:
    """Emit a table reference."""
    parts = []
    if node.database:
        parts.append(node.database)
    if node.schema:
        parts.append(node.schema)
    parts.append(node.name)
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


def _emit_join(join: JoinClause, dialect: str) -> str:
    """Emit a JOIN clause."""
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
    else:
        table = _emit_table_ref(join.table)

    if join.alias:
        table += f" {join.alias}"

    result = f"{join_type} {table}"

    if join.condition:
        result += f" ON {_emit_expression(join.condition, dialect)}"

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
        if limit.limit:
            top_val = _emit_expression(limit.limit, dialect)
            return f"/* TOP {top_val} — use OFFSET/FETCH for paging */"

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
