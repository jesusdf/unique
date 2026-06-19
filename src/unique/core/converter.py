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

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import contextlib
import logging

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
    # Oracle hierarchical queries (START WITH / CONNECT BY) have no faithful
    # automatic rewrite; emit a documented comment instead of silently
    # dropping the clause (which would change results).
    if isinstance(expr, exp.Select) and expr.args.get("connect") is not None:
        return PassthroughSQL(
            sql=expr.sql(dialect=sqlglot_dialect_name(source_dialect)),
            source_dialect=source_dialect,
            kind="CONNECT BY",
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

    Tables and views are modeled in IR; indexes, sequences, and schemas are
    not, so they round-trip through sqlglot.
    """
    if not isinstance(expr, exp.Create):
        return False
    kind = (expr.args.get("kind") or "").upper()
    return kind in ("INDEX", "SEQUENCE", "SCHEMA")


def _passthrough_kind(expr: exp.Expression) -> str:
    if isinstance(expr, exp.Create):
        return "CREATE " + (expr.args.get("kind") or "").upper()
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
        limit = LimitClause(
            limit=convert_expression(limit_expr.expression) if limit_expr else None,
            offset=convert_expression(offset_expr.expression) if offset_expr else None,
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

    if_not_exists = expr.args.get("exists") is not None

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
        return ";\n\n".join(emit_node(s, dialect) for s in node.statements)

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

    try:
        out = sqlglot.transpile(node.sql, read=read, write=write)
        if out and out[0].strip():
            return out[0]
    except Exception as e:  # noqa: BLE001 - report and fall back
        logger.warning("passthrough transpile error (%s): %s", node.kind, e)
    return f"-- UNIQUE: Unhandled {node.kind}\n-- {node.sql}"


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
    table = _emit_table_ref(node.table)
    exists = "IF NOT EXISTS " if node.if_not_exists else ""
    temp = "TEMPORARY " if node.temporary else ""

    if node.as_select:
        select = _emit_select(node.as_select, dialect)
        return f"CREATE {temp}TABLE {exists}{table} AS\n{select}"

    if node.columns:
        col_defs = []
        for col in node.columns:
            dtype = col.data_type.name
            if col.data_type.params:
                dtype += f"({', '.join(str(p) for p in col.data_type.params)})"
            nullable = "" if col.nullable else " NOT NULL"
            pk = " PRIMARY KEY" if col.primary_key else ""
            unique = " UNIQUE" if col.unique else ""
            default = ""
            if col.default is not None:
                default = f" DEFAULT {_emit_expression(col.default, dialect)}"
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
            col_defs.append(
                f"  {col.name} {dtype}{identity}{nullable}{default}{pk}{unique}"
            )
        # Table-level constraints (PK/FK/UNIQUE/CHECK), re-transpiled.
        for constraint in node.table_constraints:
            col_defs.append(f"  {_emit_passthrough_inline(constraint, dialect)}")
        cols = ",\n".join(col_defs)
        return f"CREATE {temp}TABLE {exists}{table} (\n{cols}\n)"

    return f"CREATE {temp}TABLE {exists}{table}"


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
            return parts[1].strip()
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
            parts.append(
                f"FETCH FIRST {_emit_expression(limit.limit, dialect)} ROWS ONLY"
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
        parts.append(f"LIMIT {_emit_expression(limit.limit, dialect)}")
    if limit.offset:
        parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)}")
    return "\n".join(parts)
