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

"""Intermediate Representation (IR) node definitions for the Unique transpiler.

All nodes are immutable dataclasses that form the engine-agnostic AST
used between parsing and emission stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# ---------------------------------------------------------------------------
# Source location metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceLocation:
    """Tracks the original position in source SQL for error reporting."""

    line: int | None = None
    column: int | None = None


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ASTNode:
    """Base class for all IR nodes."""

    location: SourceLocation = field(
        default_factory=SourceLocation, compare=False, kw_only=True
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JoinType(Enum):
    INNER = auto()
    LEFT = auto()
    RIGHT = auto()
    FULL = auto()
    CROSS = auto()
    NATURAL = auto()
    LATERAL = auto()


class OrderDirection(Enum):
    ASC = auto()
    DESC = auto()


class SetOperationType(Enum):
    UNION = auto()
    UNION_ALL = auto()
    INTERSECT = auto()
    EXCEPT = auto()


class UnaryOperator(Enum):
    NOT = auto()
    NEGATIVE = auto()
    EXISTS = auto()
    IS_NULL = auto()
    IS_NOT_NULL = auto()


class BinaryOperator(Enum):
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    AND = auto()
    OR = auto()
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()
    LIKE = auto()
    ILIKE = auto()
    IN = auto()
    NOT_IN = auto()
    BETWEEN = auto()
    CONCAT = auto()


class TransactionAction(Enum):
    BEGIN = auto()
    COMMIT = auto()
    ROLLBACK = auto()
    SAVEPOINT = auto()


# ---------------------------------------------------------------------------
# Expression nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Literal(ASTNode):
    """A literal value: string, number, boolean, or NULL."""

    value: Any
    dtype: str = "unknown"


@dataclass(frozen=True)
class ColumnRef(ASTNode):
    """Reference to a column, optionally qualified by table/schema."""

    name: str
    table: str | None = None
    schema: str | None = None


@dataclass(frozen=True)
class TableRef(ASTNode):
    """Reference to a table, optionally qualified by schema and aliased."""

    name: str
    schema: str | None = None
    alias: str | None = None
    database: str | None = None


@dataclass(frozen=True)
class Star(ASTNode):
    """Represents SELECT * or table.*."""

    table: str | None = None


@dataclass(frozen=True)
class Alias(ASTNode):
    """An expression with an alias."""

    expression: ASTNode
    name: str


@dataclass(frozen=True)
class ParameterRef(ASTNode):
    """Reference to a variable or parameter."""

    name: str


@dataclass(frozen=True)
class FunctionCall(ASTNode):
    """A function call with arguments."""

    name: str
    args: tuple[ASTNode, ...] = ()
    distinct: bool = False
    schema: str | None = None


@dataclass(frozen=True)
class BinaryOp(ASTNode):
    """Binary operation: left op right."""

    operator: BinaryOperator
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True)
class UnaryOp(ASTNode):
    """Unary operation: op operand."""

    operator: UnaryOperator
    operand: ASTNode


@dataclass(frozen=True)
class CaseExpression(ASTNode):
    """CASE WHEN ... THEN ... ELSE ... END."""

    operand: ASTNode | None = None
    whens: tuple[tuple[ASTNode, ASTNode], ...] = ()
    else_expr: ASTNode | None = None


@dataclass(frozen=True)
class CastExpression(ASTNode):
    """CAST(expression AS type)."""

    expression: ASTNode
    target_type: DataType


@dataclass(frozen=True)
class SubqueryExpression(ASTNode):
    """A subquery used as an expression."""

    query: SelectStatement


@dataclass(frozen=True)
class WindowSpec(ASTNode):
    """Window specification for window functions."""

    partition_by: tuple[ASTNode, ...] = ()
    order_by: tuple[OrderByItem, ...] = ()
    frame_start: str | None = None
    frame_end: str | None = None


@dataclass(frozen=True)
class WindowFunction(ASTNode):
    """A window function call."""

    function: FunctionCall
    window: WindowSpec


# ---------------------------------------------------------------------------
# Clause nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderByItem(ASTNode):
    """Single item in an ORDER BY clause."""

    expression: ASTNode
    direction: OrderDirection = OrderDirection.ASC
    nulls_first: bool | None = None


@dataclass(frozen=True)
class JoinClause(ASTNode):
    """A JOIN clause."""

    join_type: JoinType
    table: TableRef | SubqueryExpression
    alias: str | None = None
    condition: ASTNode | None = None


@dataclass(frozen=True)
class CTEDefinition(ASTNode):
    """A single CTE (WITH name AS (...))."""

    name: str
    query: SelectStatement
    columns: tuple[str, ...] = ()
    recursive: bool = False


@dataclass(frozen=True)
class LimitClause(ASTNode):
    """LIMIT/OFFSET or TOP or FETCH FIRST."""

    limit: ASTNode | None = None
    offset: ASTNode | None = None


# ---------------------------------------------------------------------------
# Type nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataType(ASTNode):
    """A SQL data type reference."""

    name: str
    params: tuple[int, ...] = ()
    unsigned: bool = False


@dataclass(frozen=True)
class ColumnDefinition(ASTNode):
    """Column definition within CREATE TABLE."""

    name: str
    data_type: DataType
    nullable: bool = True
    default: ASTNode | None = None
    identity: bool = False
    primary_key: bool = False
    unique: bool = False
    check: ASTNode | None = None


# ---------------------------------------------------------------------------
# Statement nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectStatement(ASTNode):
    """A SELECT query."""

    columns: tuple[ASTNode, ...] = ()
    from_clause: TableRef | SubqueryExpression | None = None
    joins: tuple[JoinClause, ...] = ()
    where: ASTNode | None = None
    group_by: tuple[ASTNode, ...] = ()
    having: ASTNode | None = None
    order_by: tuple[OrderByItem, ...] = ()
    limit: LimitClause | None = None
    distinct: bool = False
    ctes: tuple[CTEDefinition, ...] = ()
    set_op: SetOperationType | None = None
    set_query: SelectStatement | None = None


@dataclass(frozen=True)
class InsertStatement(ASTNode):
    """INSERT INTO ... VALUES / SELECT."""

    table: TableRef
    columns: tuple[str, ...] = ()
    values: tuple[tuple[ASTNode, ...], ...] = ()
    select: SelectStatement | None = None
    on_conflict: ASTNode | None = None
    returning: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class UpdateStatement(ASTNode):
    """UPDATE ... SET ... WHERE."""

    table: TableRef
    assignments: tuple[tuple[str, ASTNode], ...] = ()
    where: ASTNode | None = None
    from_clause: TableRef | None = None
    joins: tuple[JoinClause, ...] = ()
    returning: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class DeleteStatement(ASTNode):
    """DELETE FROM ... WHERE."""

    table: TableRef
    where: ASTNode | None = None
    using: tuple[TableRef, ...] = ()
    returning: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class MergeStatement(ASTNode):
    """MERGE INTO ... USING ... ON ... WHEN MATCHED/NOT MATCHED."""

    target: TableRef
    source: TableRef | SubqueryExpression
    on_condition: ASTNode
    when_matched: tuple[ASTNode, ...] = ()
    when_not_matched: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class CreateTableStatement(ASTNode):
    """CREATE TABLE ... (columns)."""

    table: TableRef
    columns: tuple[ColumnDefinition, ...] = ()
    if_not_exists: bool = False
    temporary: bool = False
    as_select: SelectStatement | None = None


@dataclass(frozen=True)
class DropStatement(ASTNode):
    """DROP TABLE/VIEW/INDEX/PROCEDURE/FUNCTION."""

    object_type: str
    name: TableRef
    if_exists: bool = False
    cascade: bool = False


@dataclass(frozen=True)
class AlterTableStatement(ASTNode):
    """ALTER TABLE ... ADD/DROP/MODIFY."""

    table: TableRef
    actions: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class CreateIndexStatement(ASTNode):
    """CREATE INDEX."""

    name: str
    table: TableRef
    columns: tuple[ASTNode, ...] = ()
    unique: bool = False
    if_not_exists: bool = False


@dataclass(frozen=True)
class CreateViewStatement(ASTNode):
    """CREATE VIEW."""

    name: TableRef
    query: SelectStatement
    or_replace: bool = False
    columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreateSequenceStatement(ASTNode):
    """CREATE SEQUENCE."""

    name: str
    start: int = 1
    increment: int = 1
    min_value: int | None = None
    max_value: int | None = None


# ---------------------------------------------------------------------------
# Procedural nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclareStatement(ASTNode):
    """Variable declaration."""

    name: str
    data_type: DataType
    default: ASTNode | None = None


@dataclass(frozen=True)
class SetVariableStatement(ASTNode):
    """Variable assignment."""

    name: str
    value: ASTNode


@dataclass(frozen=True)
class IfStatement(ASTNode):
    """IF ... THEN ... ELSE."""

    condition: ASTNode
    then_body: tuple[ASTNode, ...] = ()
    else_body: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class WhileStatement(ASTNode):
    """WHILE ... DO ... END."""

    condition: ASTNode
    body: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class BeginEndBlock(ASTNode):
    """BEGIN ... END block."""

    statements: tuple[ASTNode, ...] = ()
    label: str | None = None


@dataclass(frozen=True)
class TryCatchBlock(ASTNode):
    """TRY ... CATCH / EXCEPTION block."""

    try_body: tuple[ASTNode, ...] = ()
    catch_body: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class ReturnStatement(ASTNode):
    """RETURN [value]."""

    value: ASTNode | None = None


@dataclass(frozen=True)
class RaiseErrorStatement(ASTNode):
    """RAISERROR / RAISE / SIGNAL."""

    message: ASTNode | None = None
    severity: ASTNode | None = None
    state: ASTNode | None = None


@dataclass(frozen=True)
class CreateProcedureStatement(ASTNode):
    """CREATE PROCEDURE."""

    name: str
    parameters: tuple[ParameterDefinition, ...] = ()
    body: tuple[ASTNode, ...] = ()
    or_replace: bool = False
    schema: str | None = None


@dataclass(frozen=True)
class CreateFunctionStatement(ASTNode):
    """CREATE FUNCTION."""

    name: str
    parameters: tuple[ParameterDefinition, ...] = ()
    return_type: DataType | None = None
    body: tuple[ASTNode, ...] = ()
    or_replace: bool = False
    schema: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class ParameterDefinition(ASTNode):
    """Parameter in a procedure/function definition."""

    name: str
    data_type: DataType
    direction: str = "IN"
    default: ASTNode | None = None


@dataclass(frozen=True)
class ExecuteStatement(ASTNode):
    """Dynamic SQL execution."""

    sql_expression: ASTNode
    params: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class TransactionStatement(ASTNode):
    """Transaction control statement."""

    action: TransactionAction
    name: str | None = None


# ---------------------------------------------------------------------------
# Passthrough node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawSQL(ASTNode):
    """Passthrough for SQL that cannot be parsed into structured IR.

    Emitters output this as-is with a warning comment.
    """

    sql: str
    reason: str = "Could not parse this construct"


# ---------------------------------------------------------------------------
# Script node (top-level container)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Script(ASTNode):
    """A complete SQL script containing multiple statements."""

    statements: tuple[ASTNode, ...] = ()
