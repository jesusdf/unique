# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Transformation engine that normalizes IR nodes between source and target dialects.

Transformations are organized as composable passes that visit and rewrite
the AST. Each pass handles one category of normalization.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from unique.core.ast_nodes import (
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CastExpression,
    DataType,
    FunctionCall,
    SelectStatement,
)

logger = logging.getLogger(__name__)


@dataclass
class TransformWarning:
    """A non-fatal issue detected during transformation."""

    message: str
    feature: str
    source_dialect: str
    target_dialect: str


@dataclass
class TransformContext:
    """Mutable context shared across transformation passes."""

    source: str
    target: str
    warnings: list[TransformWarning] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    def warn(self, message: str, feature: str) -> None:
        """Record a transformation warning."""
        self.warnings.append(
            TransformWarning(
                message=message,
                feature=feature,
                source_dialect=self.source,
                target_dialect=self.target,
            )
        )

    def mark_unsupported(self, feature: str) -> None:
        """Record an unsupported feature."""
        self.unsupported.append(feature)


class TransformPass(ABC):
    """Base class for AST transformation passes."""

    @abstractmethod
    def visit(self, node: ASTNode, ctx: TransformContext) -> ASTNode:
        """Visit and optionally transform a node.

        Args:
            node: The node to transform.
            ctx: Shared transformation context.

        Returns:
            The transformed node (or the original if unchanged).
        """


class FunctionNormalizer(TransformPass):
    """Maps dialect-specific functions to canonical equivalents.

    For example: ISNULL → COALESCE, NVL → COALESCE, GETDATE → NOW,
    LEN → LENGTH, CHARINDEX → inversion to match target function names.
    """

    # Canonical function mappings: source_name → (canonical_name, arg_transform)
    CANONICAL_MAP: dict[str, str] = {
        # Null handling
        "ISNULL": "COALESCE",
        "NVL": "COALESCE",
        "IFNULL": "COALESCE",
        # Date/time
        "GETDATE": "CURRENT_TIMESTAMP",
        "SYSDATETIME": "CURRENT_TIMESTAMP",
        "SYSDATE": "CURRENT_TIMESTAMP",
        # String
        "LEN": "LENGTH",
        "SUBSTR": "SUBSTRING",
        # Conditional
        "IIF": "_IIF_TO_CASE",
        "DECODE": "_DECODE_TO_CASE",
    }

    def visit(self, node: ASTNode, ctx: TransformContext) -> ASTNode:
        """Transform function calls to canonical forms."""
        if not isinstance(node, FunctionCall):
            return node

        upper_name = node.name.upper()
        canonical = self.CANONICAL_MAP.get(upper_name)

        if canonical is None:
            return node

        if canonical == "_IIF_TO_CASE":
            return self._iif_to_case(node)

        if canonical == "_DECODE_TO_CASE":
            return self._decode_to_case(node, ctx)

        return FunctionCall(
            name=canonical,
            args=node.args,
            distinct=node.distinct,
            location=node.location,
        )

    def _iif_to_case(self, node: FunctionCall) -> ASTNode:
        """Convert IIF(cond, true_val, false_val) to CASE WHEN."""
        if len(node.args) != 3:
            return node
        from unique.core.ast_nodes import CaseExpression

        return CaseExpression(
            whens=((node.args[0], node.args[1]),),
            else_expr=node.args[2],
            location=node.location,
        )

    def _decode_to_case(self, node: FunctionCall, ctx: TransformContext) -> ASTNode:
        """Convert DECODE(expr, val1, res1, ..., default) to CASE WHEN."""
        from unique.core.ast_nodes import CaseExpression

        args = list(node.args)
        if len(args) < 3:
            return node

        expr = args[0]
        whens: list[tuple[ASTNode, ASTNode]] = []
        i = 1
        while i + 1 < len(args):
            condition = BinaryOp(
                operator=BinaryOperator.EQ,
                left=expr,
                right=args[i],
                location=node.location,
            )
            whens.append((condition, args[i + 1]))
            i += 2

        else_expr = args[i] if i < len(args) else None

        return CaseExpression(
            whens=tuple(whens),
            else_expr=else_expr,
            location=node.location,
        )


class TypeMapper(TransformPass):
    """Maps data types between dialects."""

    # Mapping from (source_type, target_dialect) → target_type
    TYPE_MAP: dict[tuple[str, str], str] = {
        # Oracle → other
        ("VARCHAR2", "tsql"): "VARCHAR",
        ("VARCHAR2", "postgresql"): "VARCHAR",
        ("VARCHAR2", "mysql"): "VARCHAR",
        ("NVARCHAR2", "tsql"): "NVARCHAR",
        ("NVARCHAR2", "postgresql"): "VARCHAR",
        ("NVARCHAR2", "mysql"): "VARCHAR",
        ("NUMBER", "tsql"): "NUMERIC",
        ("NUMBER", "postgresql"): "NUMERIC",
        ("NUMBER", "mysql"): "NUMERIC",
        ("CLOB", "tsql"): "VARCHAR(MAX)",
        ("CLOB", "postgresql"): "TEXT",
        ("CLOB", "mysql"): "LONGTEXT",
        # T-SQL → other
        ("NVARCHAR", "oracle"): "NVARCHAR2",
        ("NVARCHAR", "postgresql"): "VARCHAR",
        ("NVARCHAR", "mysql"): "VARCHAR",
        ("DATETIME2", "oracle"): "TIMESTAMP",
        ("DATETIME2", "postgresql"): "TIMESTAMP",
        ("DATETIME2", "mysql"): "DATETIME",
        ("BIT", "oracle"): "NUMBER(1)",
        ("BIT", "postgresql"): "BOOLEAN",
        ("BIT", "mysql"): "BOOLEAN",
        ("UNIQUEIDENTIFIER", "oracle"): "RAW(16)",
        ("UNIQUEIDENTIFIER", "postgresql"): "UUID",
        ("UNIQUEIDENTIFIER", "mysql"): "CHAR(36)",
        # PostgreSQL → other
        ("SERIAL", "tsql"): "INT IDENTITY",
        ("SERIAL", "oracle"): "NUMBER",
        ("SERIAL", "mysql"): "INT AUTO_INCREMENT",
        ("BOOLEAN", "oracle"): "NUMBER(1)",
        ("BYTEA", "tsql"): "VARBINARY(MAX)",
        ("BYTEA", "oracle"): "BLOB",
        ("BYTEA", "mysql"): "LONGBLOB",
        ("TEXT", "oracle"): "CLOB",
    }

    def visit(self, node: ASTNode, ctx: TransformContext) -> ASTNode:
        """Transform data type references to target dialect equivalents."""
        if not isinstance(node, (DataType, CastExpression)):
            return node

        if isinstance(node, CastExpression):
            mapped_type = self._map_type(node.target_type, ctx.target)
            if mapped_type != node.target_type:
                return CastExpression(
                    expression=node.expression,
                    target_type=mapped_type,
                    location=node.location,
                )
            return node

        return self._map_type(node, ctx.target)

    def _map_type(self, dtype: DataType, target: str) -> DataType:
        """Look up the type mapping and return the target DataType."""
        key = (dtype.name.upper(), target)
        mapped_name = self.TYPE_MAP.get(key)
        if mapped_name is None:
            return dtype
        return DataType(name=mapped_name, params=dtype.params, location=dtype.location)


class SyntaxNormalizer(TransformPass):
    """Normalizes dialect-specific syntax to target equivalents.

    Handles TOP → LIMIT, string concatenation operator differences, etc.
    """

    def visit(self, node: ASTNode, ctx: TransformContext) -> ASTNode:
        """Normalize syntax constructs."""
        if isinstance(node, BinaryOp):
            return self._normalize_concat(node, ctx)
        return node

    def _normalize_concat(self, node: BinaryOp, ctx: TransformContext) -> ASTNode:
        """Normalize string concatenation between dialects."""
        if node.operator != BinaryOperator.CONCAT:
            return node
        # If target is MySQL, wrap in CONCAT function
        if ctx.target == "mysql":
            return FunctionCall(
                name="CONCAT",
                args=(node.left, node.right),
                location=node.location,
            )
        return node


class Transformer:
    """Orchestrates transformation passes over a list of IR nodes."""

    def __init__(self, source: str, target: str) -> None:
        self.context = TransformContext(source=source, target=target)
        self._passes: list[TransformPass] = [
            FunctionNormalizer(),
            TypeMapper(),
            SyntaxNormalizer(),
        ]

    @property
    def warnings(self) -> list[TransformWarning]:
        """Warnings collected during transformation."""
        return self.context.warnings

    @property
    def unsupported(self) -> list[str]:
        """Unsupported features encountered during transformation."""
        return self.context.unsupported

    def transform(self, nodes: list[ASTNode]) -> list[ASTNode]:
        """Apply all transformation passes to a list of IR nodes.

        Args:
            nodes: The IR nodes to transform.

        Returns:
            The transformed IR nodes.
        """
        result = nodes
        for pass_ in self._passes:
            result = [self._apply_pass(pass_, node) for node in result]
        return result

    def _apply_pass(self, pass_: TransformPass, node: ASTNode) -> ASTNode:
        """Apply a single pass to a node, recursing into children."""
        # First transform this node
        transformed = pass_.visit(node, self.context)
        # Then recurse into children (for composite nodes)
        return self._recurse(pass_, transformed)

    def _recurse(self, pass_: TransformPass, node: ASTNode) -> ASTNode:
        """Recurse into composite node children.

        This handles the common case of nodes that contain other nodes
        as fields. For simplicity, we handle the most important
        composite types explicitly.
        """
        if isinstance(node, SelectStatement):
            return self._recurse_select(pass_, node)
        return node

    def _recurse_select(
        self, pass_: TransformPass, node: SelectStatement
    ) -> SelectStatement:
        """Recurse into SelectStatement children."""
        new_columns = tuple(self._apply_pass(pass_, col) for col in node.columns)
        new_where = self._apply_pass(pass_, node.where) if node.where else None
        return SelectStatement(
            columns=new_columns,
            from_clause=node.from_clause,
            joins=node.joins,
            where=new_where,
            group_by=node.group_by,
            having=node.having,
            order_by=node.order_by,
            limit=node.limit,
            distinct=node.distinct,
            ctes=node.ctes,
            set_op=node.set_op,
            set_query=node.set_query,
            location=node.location,
        )
