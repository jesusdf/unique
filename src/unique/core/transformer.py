# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Transformation engine that normalizes IR nodes between source and target dialects.

Transformations are organized as composable passes that visit and rewrite
the AST. Each pass handles one category of normalization.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields, replace

from unique.core.ast_nodes import (
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CastExpression,
    ColumnRef,
    CreateTableStatement,
    DataType,
    FunctionCall,
    LimitClause,
    Literal,
    PassthroughSQL,
    RawSQL,
    SelectStatement,
    TableRef,
)
from unique.core.mappings import CANONICAL_FUNCTION_NAMES

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

    # Plain renames come from the shared mapping layer (audit doc 03);
    # IIF/DECODE become CASE expressions, handled structurally below.
    CANONICAL_MAP: dict[str, str] = {
        **CANONICAL_FUNCTION_NAMES,
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

    Handles TOP → LIMIT, string concatenation operator differences,
    Oracle ROWNUM row limits and FROM dual (audit 2026-07-02, S1-5/S1-6).
    """

    def visit(self, node: ASTNode, ctx: TransformContext) -> ASTNode:
        """Normalize syntax constructs."""
        if isinstance(node, BinaryOp):
            node = self._normalize_ilike(node, ctx)
            if isinstance(node, BinaryOp):
                node = self._normalize_concat(node, ctx)
            return node
        if isinstance(node, SelectStatement):
            node = self._drop_dual(node, ctx)
            node = self._rownum_to_limit(node, ctx)
        if isinstance(node, CreateTableStatement):
            degraded = self._degrade_pg_table_binding(node, ctx)
            if not isinstance(degraded, CreateTableStatement):
                return degraded
            node = self._strip_constraint_attributes(degraded, ctx)
        return node

    @staticmethod
    def _degrade_pg_table_binding(
        node: CreateTableStatement, ctx: TransformContext
    ) -> ASTNode:
        """Degrade INHERITS / PARTITION OF tables whole off PostgreSQL.

        Neither clause has a mechanical equivalent elsewhere, and dropping
        it silently loses the table's defining structure (a partition
        child shipped as a bare column-less CREATE TABLE)."""
        if ctx.target == "postgresql":
            return node
        if not (node.inherits_clause or node.partition_of_clause):
            return node
        kind = "PARTITION OF" if node.partition_of_clause else "INHERITS"
        from unique.core.converter.emit import emit_node

        original = emit_node(node, "postgresql")
        reason = (
            f"PostgreSQL {kind} table binding has no {ctx.target} equivalent; "
            "the CREATE TABLE is preserved as a comment"
        )
        ctx.warn(reason, "table_inheritance")
        ctx.mark_unsupported(f"{kind} (PostgreSQL table binding)")
        return RawSQL(sql=original, reason=reason)

    #: cheap containment gate only — the actual removal is sqlglot-AST
    #: surgery, so a column literally named "deferrable" is never touched.
    _CONSTRAINT_ATTR_HINTS = ("DEFERRABLE", "INITIALLY")

    @classmethod
    def _strip_constraint_attributes(
        cls, node: CreateTableStatement, ctx: TransformContext
    ) -> CreateTableStatement:
        """Drop PG constraint attributes (DEFERRABLE / INITIALLY …) for
        targets whose constraints are always immediate (T-SQL, MySQL)."""
        if ctx.target not in ("tsql", "mysql"):
            return node
        changed: list[PassthroughSQL] = []
        dirty = False
        for frag in node.table_constraints:
            upper = frag.sql.upper()
            if not any(h in upper for h in cls._CONSTRAINT_ATTR_HINTS):
                changed.append(frag)
                continue
            stripped = cls._strip_options_via_sqlglot(frag)
            if stripped is None or stripped == frag.sql:
                changed.append(frag)
                continue
            ctx.warn(
                "constraint attribute (DEFERRABLE / INITIALLY …) dropped: "
                f"{ctx.target} constraints are always immediate",
                "constraint_attribute",
            )
            changed.append(replace(frag, sql=stripped))
            dirty = True
        if not dirty:
            return node
        return replace(node, table_constraints=tuple(changed))

    @staticmethod
    def _strip_options_via_sqlglot(frag: PassthroughSQL) -> str | None:
        """Remove DEFERRABLE-family options from a constraint fragment at
        the sqlglot-AST level (wrapped in a scratch CREATE so the bare
        fragment parses). Returns None when the surgery isn't possible —
        the caller keeps the fragment untouched (honest passthrough)."""
        import sqlglot

        from unique.core.converter import sqlglot_dialect_name

        read = sqlglot_dialect_name(frag.source_dialect)
        try:
            wrapped = sqlglot.parse_one(f"CREATE TABLE _x ({frag.sql})", read=read)
            dirty = False
            for n in wrapped.walk():
                opts = n.args.get("options")
                if not opts:
                    continue
                kept = [
                    o
                    for o in opts
                    if not (
                        isinstance(o, str)
                        and ("DEFERRABLE" in o.upper() or "INITIALLY" in o.upper())
                    )
                ]
                if len(kept) != len(opts):
                    n.set("options", kept)
                    dirty = True
            if not dirty:
                return frag.sql
            exprs = wrapped.this.expressions
            if len(exprs) != 1:
                return None
            return str(exprs[0].sql(dialect=read))
        except Exception:
            return None

    @staticmethod
    def _normalize_ilike(node: BinaryOp, ctx: TransformContext) -> ASTNode:
        """Rewrite ILIKE for engines that lack it (audit 2026-07-02, S1-7).

        MySQL/T-SQL: plain LIKE — usually case-insensitive under their
        default collations, but collation-dependent, so a warning is raised.
        Oracle: UPPER(x) LIKE UPPER(y).
        """
        if node.operator != BinaryOperator.ILIKE or ctx.target == "postgresql":
            return node
        if ctx.target in ("mysql", "tsql"):
            ctx.warn(
                "ILIKE rewritten as LIKE; case-insensitivity depends on the "
                "column collation",
                "ilike",
            )
            return replace(node, operator=BinaryOperator.LIKE)
        if ctx.target == "oracle":
            return BinaryOp(
                operator=BinaryOperator.LIKE,
                left=FunctionCall(name="UPPER", args=(node.left,)),
                right=FunctionCall(name="UPPER", args=(node.right,)),
                location=node.location,
            )
        return node

    @staticmethod
    def _drop_dual(node: SelectStatement, ctx: TransformContext) -> SelectStatement:
        """Drop ``FROM dual`` for engines where dual does not exist.

        Oracle/MySQL accept it; PostgreSQL and T-SQL have no dual relation
        and both allow a FROM-less SELECT.
        """
        if (
            ctx.target in ("postgresql", "tsql")
            and isinstance(node.from_clause, TableRef)
            and node.from_clause.name.lower() == "dual"
            and node.from_clause.schema is None
            and not node.joins
        ):
            return replace(node, from_clause=None)
        return node

    def _rownum_to_limit(
        self, node: SelectStatement, ctx: TransformContext
    ) -> SelectStatement:
        """Rewrite ``WHERE ROWNUM <= n`` as the target's row-limit clause.

        Handles a top-level ROWNUM comparison, alone or AND-ed with other
        predicates. Any other ROWNUM use (select list, OR branches, nested
        expressions) has no simple LIMIT equivalent and is signalled instead
        of being passed through as an unknown column.
        """
        if ctx.source != "oracle" or ctx.target == "oracle":
            return node

        limit_count: int | None = None
        if node.where is not None and node.limit is None:
            comparison, remainder = self._split_rownum_predicate(node.where)
            if comparison is not None:
                limit_count = self._rownum_limit_value(comparison)
                if limit_count is not None:
                    node = replace(
                        node,
                        where=remainder,
                        limit=LimitClause(
                            limit=Literal(value=limit_count, dtype="integer")
                        ),
                    )

        if self._contains_rownum(node):
            ctx.warn(
                "ROWNUM has no direct equivalent here; rewrite as "
                "LIMIT/FETCH or ROW_NUMBER() manually",
                "rownum",
            )
            ctx.mark_unsupported("ROWNUM (non-limit usage)")
        return node

    @staticmethod
    def _is_rownum(node: ASTNode) -> bool:
        return (
            isinstance(node, ColumnRef)
            and node.table is None
            and node.name.upper() == "ROWNUM"
        )

    def _split_rownum_predicate(
        self, where: ASTNode
    ) -> tuple[BinaryOp | None, ASTNode | None]:
        """Extract a top-level ROWNUM comparison from a WHERE tree.

        Returns (comparison, remaining_predicate). Only AND conjunctions are
        traversed: under OR, removing the ROWNUM term would change semantics.
        """
        if isinstance(where, BinaryOp) and where.operator in (
            BinaryOperator.LTE,
            BinaryOperator.LT,
            # ROWNUM = 1 is the common "first row" idiom (equivalent to
            # <= 1; ROWNUM = n for n > 1 never matches and stays warned).
            BinaryOperator.EQ,
        ):
            if self._is_rownum(where.left):
                return where, None
            return None, where
        if isinstance(where, BinaryOp) and where.operator == BinaryOperator.AND:
            left_cmp, left_rest = self._split_rownum_predicate(where.left)
            if left_cmp is not None:
                if left_rest is None:
                    return left_cmp, where.right
                return left_cmp, replace(where, left=left_rest)
            right_cmp, right_rest = self._split_rownum_predicate(where.right)
            if right_cmp is not None:
                if right_rest is None:
                    return right_cmp, where.left
                return right_cmp, replace(where, right=right_rest)
        return None, where

    @staticmethod
    def _rownum_limit_value(comparison: BinaryOp) -> int | None:
        """ROWNUM <= n -> n; ROWNUM < n -> n - 1; ROWNUM = 1 -> 1."""
        right = comparison.right
        if not isinstance(right, Literal):
            return None
        try:
            n = int(str(right.value))
        except (TypeError, ValueError):
            return None
        if comparison.operator == BinaryOperator.EQ:
            return 1 if n == 1 else None
        return n if comparison.operator == BinaryOperator.LTE else n - 1

    def _contains_rownum(self, node: ASTNode | None) -> bool:
        """Deep scan for any remaining ROWNUM reference."""
        if node is None:
            return False
        if self._is_rownum(node):
            return True
        for node_field in fields(node):
            value = getattr(node, node_field.name)
            if isinstance(value, ASTNode):
                if self._contains_rownum(value):
                    return True
            elif isinstance(value, tuple):
                for item in value:
                    if isinstance(item, ASTNode) and self._contains_rownum(item):
                        return True
        return False

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

    #: Array-construct function names (IR canonical): PostgreSQL arrays
    #: have no T-SQL/MySQL equivalent; a statement using them cannot run
    #: there in any spelling.
    _ARRAY_CONSTRUCTS = frozenset({"ARRAY", "ARRAY_AGG", "UNNEST", "EXPLODE"})

    def transform(self, nodes: list[ASTNode]) -> list[ASTNode]:
        """Apply all transformation passes to a list of IR nodes.

        Args:
            nodes: The IR nodes to transform.

        Returns:
            The transformed IR nodes.
        """
        result = nodes
        if self.context.target in ("tsql", "mysql"):
            result = [self._gate_array_constructs(node) for node in result]
        for pass_ in self._passes:
            result = [self._apply_pass(pass_, node) for node in result]
        return result

    def _gate_array_constructs(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using PG array constructs — WHOLE.

        They shipped as fake calls (``dbo.ARRAY(1,2)``, unqualified
        ``ARRAY_AGG(x)``) with zero warnings; there is no spelling of
        arrays on these targets."""
        found = self._find_array_construct(node)
        if found is None:
            return node
        reason = (
            f"PostgreSQL array construct {found}(…) has no "
            f"{self.context.target} equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "array_construct")
        self.context.mark_unsupported(f"{found} (array construct)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_array_construct(self, value: object) -> str | None:
        """First array-construct function name reachable from *value*."""
        if (
            isinstance(value, FunctionCall)
            and value.name.upper() in self._ARRAY_CONSTRUCTS
        ):
            return value.name.upper()
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_array_construct(getattr(value, f.name))
                if found is not None:
                    return found
            return None
        if isinstance(value, tuple):
            for item in value:
                found = self._find_array_construct(item)
                if found is not None:
                    return found
        return None

    def _apply_pass(self, pass_: TransformPass, node: ASTNode) -> ASTNode:
        """Apply a single pass to a node, recursing into children."""
        # First transform this node
        transformed = pass_.visit(node, self.context)
        # Then recurse into children (for composite nodes)
        return self._recurse(pass_, transformed)

    def _recurse(self, pass_: TransformPass, node: ASTNode) -> ASTNode:
        """Recurse into every ASTNode-valued field of a composite node.

        A pass must see a query (or expression) wherever it sits — an
        INSERT's source SELECT, a scalar subquery in an UPDATE assignment,
        an IN-subquery — not only at the top level. Recursion used to stop
        at top-level SelectStatements, which is how ``FROM DUAL`` survived
        inside an INSERT source query (audit 2026-07-08, D3).
        """
        changes: dict[str, object] = {}
        for f in fields(node):
            old = getattr(node, f.name)
            new = self._recurse_value(pass_, old)
            if new is not old:
                changes[f.name] = new
        return replace(node, **changes) if changes else node  # type: ignore[arg-type]

    def _recurse_value(self, pass_: TransformPass, value: object) -> object:
        """Apply *pass_* to a field value: a node, or a (nested) tuple of them."""
        if isinstance(value, ASTNode):
            return self._apply_pass(pass_, value)
        if isinstance(value, tuple):
            items = tuple(self._recurse_value(pass_, v) for v in value)
            if any(a is not b for a, b in zip(items, value, strict=True)):
                return items
            return value
        return value
