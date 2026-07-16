# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Transformation engine that normalizes IR nodes between source and target dialects.

Transformations are organized as composable passes that visit and rewrite
the AST. Each pass handles one category of normalization.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace

from unique.core.ast_nodes import (
    Alias,
    ArrayLiteral,
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
    Star,
    SubqueryExpression,
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

    #: PG catalog internals: object-identifier cast types and system
    #: columns. Engine-internal on EVERY other target.
    _PG_CATALOG_TYPES = frozenset(
        {
            "REGCLASS",
            "REGTYPE",
            "REGPROC",
            "REGPROCEDURE",
            "REGOPER",
            "REGOPERATOR",
            "REGNAMESPACE",
            "REGROLE",
            "REGCONFIG",
            "REGDICTIONARY",
            "REGCOLLATION",
        }
    )
    _PG_SYSTEM_COLUMNS = frozenset({"TABLEOID", "CTID", "XMIN", "XMAX", "CMIN", "CMAX"})

    def transform(self, nodes: list[ASTNode]) -> list[ASTNode]:
        """Apply all transformation passes to a list of IR nodes.

        Args:
            nodes: The IR nodes to transform.

        Returns:
            The transformed IR nodes.
        """
        result = nodes
        if self.context.target != "postgresql":
            result = [self._gate_pg_internals(node) for node in result]
        if self.context.target == "postgresql":
            result = [self._gate_pg_setop_order_aggregate(node) for node in result]
        if self.context.target in ("tsql", "mysql", "oracle"):
            result = [self._gate_array_constructs(node) for node in result]
            result = [self._gate_empty_select_list(node) for node in result]
            result = [self._gate_zero_column_table(node) for node in result]
            result = [self._gate_composite_row_value(node) for node in result]
        if self.context.target == "mysql":
            result = [self._gate_mysql_full_join(node) for node in result]
            result = [self._gate_mysql_function_relation(node) for node in result]
            result = [self._gate_mysql_agg_forms(node) for node in result]
            result = [self._gate_mysql_nonconst_lag(node) for node in result]
        if self.context.target in ("mysql", "oracle"):
            result = [self._gate_column_alias_ref(node) for node in result]
        if self.context.target != "mysql":
            result = [self._gate_invalid_date_literal(node) for node in result]
        if self.context.target == "tsql":
            result = [self._gate_tsql_unknown_sysvar(node) for node in result]
        elif self.context.source == "mysql" and self.context.target in (
            "oracle",
            "postgresql",
        ):
            # Oracle/PG have no @@ globals at all — a MySQL @@sysvar in
            # a top-level statement is unmappable there too (wave 178).
            result = [self._gate_tsql_unknown_sysvar(node) for node in result]
        if self.context.source == "mysql" and self.context.target != "mysql":
            result = [self._gate_mysql_user_var(node) for node in result]
            result = [self._strip_mysql_charset_marks(node) for node in result]
            result = [
                n2
                for n in result
                if isinstance((n2 := self._inline_having_alias(n)), ASTNode)
            ]
        if self.context.target in ("tsql", "oracle"):
            result = [self._gate_nested_cte_arm(node) for node in result]
            result = [self._gate_conditioned_lateral(node) for node in result]
        if self.context.target == "tsql":
            result = [self._gate_tsql_temp_view(node) for node in result]
            result = [self._gate_tsql_all_computed_table(node) for node in result]
            result = [self._gate_tsql_agg_distinct(node) for node in result]
            result = [self._gate_tsql_natural_join(node) for node in result]
            result = [self._gate_tsql_nth_value(node) for node in result]
            result = [self._gate_tsql_tuple_subquery(node) for node in result]
        for pass_ in self._passes:
            result = [self._apply_pass(pass_, node) for node in result]
        return result

    def _gate_pg_internals(self, node: ASTNode) -> ASTNode:
        """Degrade a statement touching PG catalog internals — WHOLE.

        ``CAST(x AS regclass)`` / system columns like ``ctid`` are
        engine internals; they shipped raw (ORA-00936 & friends, 22x)
        with zero warnings."""
        found = self._find_pg_internal(node)
        if found is None:
            return node
        reason = (
            f"PostgreSQL catalog internal {found} has no "
            f"{self.context.target} equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "pg_catalog_internal")
        self.context.mark_unsupported(f"{found} (PG catalog internal)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_pg_internal(self, value: object) -> str | None:
        """First PG catalog-internal construct reachable from *value*."""
        if (
            isinstance(value, CastExpression)
            and value.target_type.name.upper() in self._PG_CATALOG_TYPES
        ):
            return f"cast to {value.target_type.name}"
        if isinstance(value, DataType) and value.name.upper() in self._PG_CATALOG_TYPES:
            return f"type {value.name}"
        if (
            isinstance(value, ColumnRef)
            and value.name.upper() in self._PG_SYSTEM_COLUMNS
        ):
            return f"system column {value.name}"
        if isinstance(value, FunctionCall):
            for a in value.args:
                qualified_star = (
                    isinstance(a, ColumnRef) and a.name == "*" and a.table
                ) or (isinstance(a, Star) and getattr(a, "table", None))
                if qualified_star:
                    # Whole-row COUNT(t.*): counts non-NULL rows after an
                    # outer join; no spelling elsewhere, no rewrite
                    # without the schema.
                    table = a.table if hasattr(a, "table") else ""
                    return f"whole-row {value.name}({table}.*)"
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_pg_internal(getattr(value, f.name))
                if found is not None:
                    return found
            return None
        if isinstance(value, tuple):
            for item in value:
                found = self._find_pg_internal(item)
                if found is not None:
                    return found
        return None

    def _gate_mysql_full_join(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using FULL OUTER JOIN — WHOLE, on MySQL.

        MySQL has no FULL join in any spelling; it shipped raw (1064).
        The faithful manual rewrite is LEFT JOIN UNION ALL the right
        anti-join, which changes the statement's shape too much to do
        mechanically without column knowledge."""
        if not self._contains_full_join(node):
            return node
        reason = (
            "MySQL has no FULL OUTER JOIN; rewrite as LEFT JOIN UNION ALL "
            "right anti-join. Statement preserved as a comment"
        )
        self.context.warn(reason, "full_outer_join")
        self.context.mark_unsupported("FULL OUTER JOIN (MySQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _gate_composite_row_value(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using a PG composite/row VALUE — WHOLE.

        A row constructor in value position (``(a, b, c)`` as a CASE
        result or function argument — an unhandled-Tuple RawSQL) and the
        parenthesized whole-row form (``(n.*)`` — ColumnRef('*')) have
        no spelling off PostgreSQL (wave 137)."""
        found = self._find_composite_row_value(node)
        if found is None:
            return node
        reason = (
            f"PostgreSQL composite row value {found} has no "
            f"{self.context.target} equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "composite_row_value")
        self.context.mark_unsupported(f"{found} (composite row value)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_composite_row_value(self, value: object) -> str | None:
        # ONLY a Tuple in a CASE result or function-argument position:
        # tuple COMPARISONS ((a,b) = (c,d), IN lists, set-op tuples) are
        # expanded by later passes and must not gate (their tests fired
        # on the first draft).
        from unique.core.ast_nodes import CaseExpression

        def is_tuple_raw(v: object) -> bool:
            return isinstance(v, RawSQL) and (
                "Unhandled expression type: Tuple" in v.reason
            )

        if isinstance(value, CaseExpression):
            arms = [w[1] for w in value.whens] + [value.else_expr]
            if any(is_tuple_raw(a) for a in arms):
                return "row constructor"
        if (
            isinstance(value, BinaryOp)
            and value.operator in (BinaryOperator.EQ, BinaryOperator.NEQ)
            and is_tuple_raw(value.left)
            and isinstance(value.right, RawSQL)
            and re.search(
                r"(?is)Unhandled expression type: (Any|All)", value.right.reason
            )
        ):
            # A row tuple compared with ANY/ALL over a subquery — both
            # sides arrive as source-spelled RawSQL fragments (function
            # maps can't see inside); no verified spelling off PG
            # (wave 153).
            return "row comparison with ANY/ALL"
        if isinstance(value, SelectStatement) and any(
            is_tuple_raw(c) or (isinstance(c, Alias) and is_tuple_raw(c.expression))
            for c in value.columns
        ):
            # A row tuple AS a select column (``SELECT (a, b, c)`` in a
            # lateral) — same composite class (wave 144).
            return "row constructor"
        if isinstance(value, FunctionCall) and any(is_tuple_raw(a) for a in value.args):
            return "row constructor"
        if isinstance(value, FunctionCall) and any(
            isinstance(a, RawSQL)
            and "Unhandled expression type: Distinct" in a.reason
            and re.search(r"(?is)\b(?:then|else)\s*\((?:[^()]+,)+[^()]+\)", a.sql)
            for a in value.args
        ):
            # DISTINCT wraps the whole argument in one RawSQL; a CASE
            # branch returning a row constructor hides in its text.
            return "row constructor"
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_composite_row_value(getattr(value, f.name))
                if found is not None:
                    return found
            return None
        if isinstance(value, tuple):
            for item in value:
                found = self._find_composite_row_value(item)
                if found is not None:
                    return found
        return None

    def _gate_zero_column_table(self, node: ASTNode) -> ASTNode:
        """Degrade PG's zero-column CREATE TABLE — WHOLE, off PG.

        ``CREATE TABLE onerow()`` exists only on PostgreSQL; without the
        gate the bare (paren-less) form shipped invalid."""
        if not isinstance(node, CreateTableStatement):
            return node
        if (
            node.columns
            or node.table_constraints
            or node.as_select
            or node.like_source
            or node.partition_of_clause
            or node.inherits_clause
        ):
            return node
        reason = (
            f"PostgreSQL's zero-column CREATE TABLE has no "
            f"{self.context.target} equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "zero_column_table")
        self.context.mark_unsupported("zero-column CREATE TABLE")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _gate_nested_cte_arm(self, node: ASTNode) -> ASTNode:
        """Degrade a statement whose set arm carries its own WITH — WHOLE.

        Valid PG/MySQL-8; T-SQL and Oracle only allow CTEs at the
        statement top (the parenthesized arm shipped invalid, wave 134)."""
        if not self._has_nested_cte_arm(node):
            return node
        reason = (
            f"a WITH inside a set-operation arm has no {self.context.target} "
            "spelling (CTEs are statement-top only); statement preserved "
            "as a comment"
        )
        self.context.warn(reason, "nested_cte_arm")
        self.context.mark_unsupported("WITH inside a set-operation arm")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _has_nested_cte_arm(self, value: object, is_top: bool = True) -> bool:
        # ANY non-top CTE: a set arm's WITH, a derived table's WITH, a
        # lateral/APPLY subquery's WITH, a CTE whose own body has a WITH —
        # T-SQL/Oracle only allow the clause at the statement top
        # (waves 134/136).
        from unique.core.ast_nodes import InsertStatement

        if isinstance(value, SelectStatement) and not is_top and value.ctes:
            return True
        if isinstance(value, InsertStatement):
            # An INSERT's source-select CTE is hoistable to the statement
            # top (the emitter already does) — it stays "top".
            return any(
                self._has_nested_cte_arm(
                    getattr(value, f.name), is_top=(f.name == "select")
                )
                for f in fields(value)
            )
        if isinstance(value, ASTNode):
            return any(
                self._has_nested_cte_arm(getattr(value, f.name), False)
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._has_nested_cte_arm(item, False) for item in value)
        return False

    def _gate_conditioned_lateral(self, node: ASTNode) -> ASTNode:
        """Degrade a LATERAL join with a REAL ON condition — WHOLE, on
        T-SQL/Oracle. Their APPLY operators take no ON clause; only the
        unconditioned (ON TRUE) form maps (wave 136)."""
        if not self._has_conditioned_lateral(node):
            return node
        reason = (
            f"a LATERAL join with an ON condition has no {self.context.target} "
            "APPLY equivalent (APPLY takes no ON); statement preserved "
            "as a comment"
        )
        self.context.warn(reason, "conditioned_lateral")
        self.context.mark_unsupported("LATERAL JOIN … ON <condition>")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _has_conditioned_lateral(self, value: object) -> bool:
        from unique.core.ast_nodes import JoinClause

        if isinstance(value, JoinClause) and value.lateral:
            cond = value.condition
            real = cond is not None and not (
                isinstance(cond, Literal) and cond.dtype == "boolean" and cond.value
            )
            if real:
                return True
        if isinstance(value, ASTNode):
            return any(
                self._has_conditioned_lateral(getattr(value, f.name))
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._has_conditioned_lateral(item) for item in value)
        return False

    def _gate_empty_select_list(self, node: ASTNode) -> ASTNode:
        """Degrade a statement with PG's zero-column select list — WHOLE.

        ``SELECT;`` (empty list, one row) exists only on PostgreSQL;
        the old ``*`` substitute silently changed the shape."""
        if not self._has_empty_select_list(node):
            return node
        reason = (
            f"PostgreSQL's empty select list (zero columns) has no "
            f"{self.context.target} equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "empty_select_list")
        self.context.mark_unsupported("empty select list")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _has_empty_select_list(self, value: object) -> bool:
        if (
            isinstance(value, SelectStatement)
            and value.empty_select_list
            and not value.columns
        ):
            return True
        if isinstance(value, ASTNode):
            return any(
                self._has_empty_select_list(getattr(value, f.name))
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._has_empty_select_list(item) for item in value)
        return False

    _MYSQL_DISTINCT_BUILTINS = frozenset(
        {
            "COUNT",
            "SUM",
            "AVG",
            "MIN",
            "MAX",
            "GROUP_CONCAT",
            "STRING_AGG",
            "BIT_AND",
            "BIT_OR",
            "BIT_XOR",
            "JSON_ARRAYAGG",
            "STD",
            "STDDEV",
            "VARIANCE",
            "VAR_POP",
            "VAR_SAMP",
            "STDDEV_POP",
            "STDDEV_SAMP",
        }
    )

    def _gate_mysql_agg_forms(self, node: ASTNode) -> ASTNode:
        """Degrade MySQL-impossible aggregate forms — WHOLE (wave 145).

        A string-agg with an EXPRESSION separator: MySQL's SEPARATOR takes
        a literal only, and the comma form CONCATENATES the separator onto
        every value (audit S1-8 — the silent-corruption classic). And
        DISTINCT inside a non-builtin aggregate call is a hard 1064."""
        found = self._find_mysql_agg_form(node)
        if found is None:
            return node
        reason = f"{found}; statement preserved as a comment"
        self.context.warn(reason, "mysql_agg_form")
        self.context.mark_unsupported(found)
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_mysql_agg_form(self, value: object) -> str | None:
        if isinstance(value, FunctionCall):
            name = value.name.upper()
            if (
                name in ("GROUP_CONCAT", "STRING_AGG", "LISTAGG")
                and len(value.args) > 1
                and not (
                    isinstance(value.args[1], Literal)
                    and (
                        value.args[1].value is None
                        or isinstance(value.args[1].value, str)
                    )
                )
            ):
                return (
                    "MySQL's GROUP_CONCAT SEPARATOR takes a literal only "
                    "(an expression separator has no MySQL spelling)"
                )
            has_distinct = value.distinct or any(
                isinstance(a, RawSQL)
                and "Unhandled expression type: Distinct" in a.reason
                for a in value.args
            )
            if has_distinct and name not in self._MYSQL_DISTINCT_BUILTINS:
                return (
                    f"DISTINCT inside a non-builtin aggregate call "
                    f"({value.name}) is invalid MySQL"
                )
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_mysql_agg_form(getattr(value, f.name))
                if found is not None:
                    return found
            return None
        if isinstance(value, tuple):
            for item in value:
                found = self._find_mysql_agg_form(item)
                if found is not None:
                    return found
        return None

    def _gate_mysql_nonconst_lag(self, node: ASTNode) -> ASTNode:
        """LAG/LEAD with a NON-CONSTANT offset — MySQL requires a constant
        (a column offset raises 1327 'Undeclared variable') — wave 147."""
        found = self._find_nonconst_lag(node)
        if not found:
            return node
        reason = (
            "MySQL requires a constant LAG/LEAD offset (a column offset "
            "has no MySQL spelling); statement preserved as a comment"
        )
        self.context.warn(reason, "nonconst_lag_offset")
        self.context.mark_unsupported("non-constant LAG/LEAD offset (MySQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_nonconst_lag(self, value: object) -> bool:
        if (
            isinstance(value, FunctionCall)
            and value.name.upper() in ("LAG", "LEAD")
            and len(value.args) >= 2
            and not isinstance(value.args[1], Literal)
        ):
            return True
        if isinstance(value, ASTNode):
            return any(
                self._find_nonconst_lag(getattr(value, f.name)) for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._find_nonconst_lag(item) for item in value)
        return False

    def _gate_mysql_function_relation(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using a function as a relation — WHOLE, on MySQL.

        MySQL has no table functions except JSON_TABLE: ``FROM fn(…) a``
        is a hard 1064 in every spelling (243x on the pg corpus once
        wave 110 stopped dropping the function silently)."""
        found = self._find_function_relation(node)
        if found is None:
            return node
        reason = (
            f"MySQL has no table functions (only JSON_TABLE); FROM "
            f"{found}(…) has no MySQL spelling. Statement preserved as a comment"
        )
        self.context.warn(reason, "function_relation")
        self.context.mark_unsupported(f"{found} as a relation (MySQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_function_relation(self, value: object) -> str | None:
        """First non-JSON_TABLE function-relation name reachable from *value*."""
        if isinstance(value, TableRef) and value.function is not None:
            name = (
                value.function.name
                if isinstance(value.function, FunctionCall)
                else "function"
            )
            if name.upper() != "JSON_TABLE":
                return name
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_function_relation(getattr(value, f.name))
                if found is not None:
                    return found
            return None
        if isinstance(value, tuple):
            for item in value:
                found = self._find_function_relation(item)
                if found is not None:
                    return found
        return None

    def _gate_invalid_date_literal(self, node: ASTNode) -> ASTNode:
        """Degrade a statement CASTing an invalid calendar date — WHOLE.

        MySQL returns NULL (with a warning) for CAST('0000-00-00' AS
        DATE) and impossible dates; every other engine errors. There is
        no faithful spelling — NULL substitution would hide the
        warning."""
        found = self._find_invalid_date_cast(node)
        if found is None:
            return node
        reason = (
            f"CAST of invalid calendar date {found} returns NULL on MySQL "
            f"and errors on {self.context.target}; statement preserved as "
            "a comment"
        )
        self.context.warn(reason, "invalid_date_literal")
        self.context.mark_unsupported("invalid calendar date CAST")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_invalid_date_cast(self, value: object) -> str | None:
        import datetime

        from unique.core.ast_nodes import CastExpression, FunctionCall, Literal

        candidate: Literal | None = None
        if isinstance(value, CastExpression) and value.target_type.name.upper() in (
            "DATE",
            "DATETIME",
            "TIMESTAMP",
        ):
            inner = value.expression
            if isinstance(inner, Literal) and inner.dtype == "string":
                candidate = inner
        # STR_TO_DATE lowers to the same CAST at emit time, after this
        # gate has run — inspect the function form here too.
        if (
            isinstance(value, FunctionCall)
            and value.name.upper() == "STR_TO_DATE"
            and value.args
            and isinstance(value.args[0], Literal)
            and value.args[0].dtype == "string"
        ):
            candidate = value.args[0]
        if isinstance(value, RawSQL) and re.search(
            r"(?i)\bSTR_TO_DATE\s*\(", value.sql
        ):
            # Inside an unconverted expression blob the emit-time
            # STR_TO_DATE→CAST mapping never fires; it would ship raw.
            return "STR_TO_DATE(...)"
        if candidate is not None:
            text = str(candidate.value).strip()
            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
            if m is None:
                return f"'{text}'"
            try:
                datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return f"'{text}'"
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_invalid_date_cast(getattr(value, f.name))
                if found is not None:
                    return found
        if isinstance(value, tuple):
            for item in value:
                found = self._find_invalid_date_cast(item)
                if found is not None:
                    return found
        return None

    #: T-SQL's own global variables — anything else in @@ form is a MySQL
    #: system variable with no T-SQL meaning.
    _TSQL_GLOBALS = frozenset(
        {
            "@@VERSION",
            "@@IDENTITY",
            "@@ROWCOUNT",
            "@@ERROR",
            "@@TRANCOUNT",
            "@@SPID",
            "@@SERVERNAME",
            "@@FETCH_STATUS",
            "@@NESTLEVEL",
            "@@DATEFIRST",
            "@@LANGUAGE",
        }
    )

    _CHARSET_INTRO_RE = re.compile(r"_\w+\s*(?=')")
    _COLLATE_RE = re.compile(r"(?i)\s+COLLATE\s+\w+")

    def _strip_mysql_charset_marks(self, node: ASTNode) -> ASTNode:
        """Charset introducers (``_latin1'x'``) and COLLATE clauses are
        engine-local; embedded in RawSQL fragments they ship raw off
        MySQL (ORA-00911 & friends)."""

        def rewrite(value: object) -> object:
            if isinstance(value, RawSQL):
                sql = self._CHARSET_INTRO_RE.sub("", value.sql)
                sql = self._COLLATE_RE.sub("", sql)
                if sql != value.sql:
                    # The construct is handled now — the stale 'unmapped'
                    # reason must not trigger the gap note downstream.
                    return replace(value, sql=sql, reason="charset marks stripped")
                return value
            if isinstance(value, ASTNode):
                changes = {}
                for f in fields(value):
                    v = getattr(value, f.name)
                    nv = rewrite(v)
                    if nv is not v:
                        changes[f.name] = nv
                if changes:
                    return replace(value, **changes)  # type: ignore[arg-type]
                return value
            if isinstance(value, tuple):
                items = tuple(rewrite(i) for i in value)
                if any(a is not b for a, b in zip(items, value, strict=True)):
                    return items
                return value
            return value

        out = rewrite(node)
        assert isinstance(out, ASTNode)
        return out

    _USER_VAR_RE = re.compile(r"(?<!@)@(\w+)")

    def _gate_mysql_user_var(self, node: ASTNode) -> ASTNode:
        """Degrade a top-level statement referencing a MySQL @user
        variable — WHOLE, off MySQL (no equivalent: session state
        lives in the client there)."""
        found = self._find_user_var(node)
        if found is None:
            return node
        reason = (
            f"MySQL user variable @{found} has no "
            f"{self.context.target} equivalent outside a routine; "
            "statement preserved as a comment"
        )
        self.context.warn(reason, "mysql_user_var")
        self.context.mark_unsupported(f"@{found} (MySQL user variable)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_user_var(self, value: object) -> str | None:
        if isinstance(value, (RawSQL, PassthroughSQL)):
            # Scrub string literals so an email-like '@' inside text
            # doesn't trip the scan. The assignment itself arrives as a
            # PassthroughSQL SET (``SET @v0 = '2'`` shipped raw — wave
            # 168), the references as RawSQL.
            scrubbed = re.sub(r"'(?:[^']|'')*'", "''", value.sql)
            m = self._USER_VAR_RE.search(scrubbed)
            return m.group(1) if m else None
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_user_var(getattr(value, f.name))
                if found is not None:
                    return found
        if isinstance(value, tuple):
            for item in value:
                found = self._find_user_var(item)
                if found is not None:
                    return found
        return None

    def _gate_tsql_unknown_sysvar(self, node: ASTNode) -> ASTNode:
        """Degrade a statement referencing a MySQL @@system variable the
        target does not know — WHOLE (T-SQL error 137 live; Oracle/PG
        have no @@ globals at all — wave 178)."""
        found = self._find_unknown_sysvar(node)
        if found is None:
            return node
        reason = (
            f"MySQL system variable {found} has no {self.context.target} "
            "equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "mysql_sysvar")
        self.context.mark_unsupported(f"{found} (MySQL system variable)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    _SYSVAR_RE = re.compile(r"@@\w+(?:\.\w+)?")

    def _find_unknown_sysvar(self, value: object) -> str | None:
        if isinstance(value, RawSQL):
            # Only T-SQL has @@ globals; on Oracle/PG every @@name is
            # foreign (the gate runs for mysql source only there).
            known = self._TSQL_GLOBALS if self.context.target == "tsql" else ()
            for m in self._SYSVAR_RE.finditer(value.sql):
                name = m.group(0)
                if name.upper() not in known:
                    return name
            return None
        if isinstance(value, ASTNode):
            for f in fields(value):
                found = self._find_unknown_sysvar(getattr(value, f.name))
                if found is not None:
                    return found
        if isinstance(value, tuple):
            for item in value:
                found = self._find_unknown_sysvar(item)
                if found is not None:
                    return found
        return None

    def _gate_tsql_tuple_subquery(self, node: ASTNode) -> ASTNode:
        """Degrade a statement comparing a row tuple to a SUBQUERY —
        WHOLE, on T-SQL (no row constructors, and the pairwise
        expansion cannot reference a subquery twice)."""
        if not self._contains_tuple_subquery_cmp(node):
            return node
        reason = (
            "T-SQL has no row-tuple comparison against a subquery; rewrite "
            "with a join or EXISTS. Statement preserved as a comment"
        )
        self.context.warn(reason, "tuple_subquery")
        self.context.mark_unsupported("row tuple = (subquery) (T-SQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _contains_tuple_subquery_cmp(self, value: object) -> bool:
        from unique.core.ast_nodes import (
            BinaryOp,
            BinaryOperator,
            ExpressionList,
            SubqueryExpression,
        )

        def is_tuple(side: object) -> bool:
            if isinstance(side, ExpressionList) and len(side.items) > 1:
                return True
            return (
                isinstance(side, RawSQL)
                and side.sql.strip().startswith("(")
                and "," in side.sql
                and "SELECT" not in side.sql.upper()
            )

        if (
            isinstance(value, BinaryOp)
            and value.operator
            in (BinaryOperator.EQ, BinaryOperator.NEQ, BinaryOperator.IN)
            and (
                (is_tuple(value.left) and isinstance(value.right, SubqueryExpression))
                or (
                    is_tuple(value.right) and isinstance(value.left, SubqueryExpression)
                )
            )
        ):
            # Only multi-column subqueries make this a ROW comparison.
            sq = (
                value.right
                if isinstance(value.right, SubqueryExpression)
                else value.left
            )
            if isinstance(sq, SubqueryExpression) and len(sq.query.columns) > 1:
                return True
        if isinstance(value, ASTNode):
            return any(
                self._contains_tuple_subquery_cmp(getattr(value, f.name))
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_tuple_subquery_cmp(item) for item in value)
        return False

    def _gate_tsql_nth_value(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using NTH_VALUE — WHOLE, on T-SQL.

        T-SQL has no NTH_VALUE; the generic UDF qualification shipped a
        fictitious ``dbo.NTH_VALUE(...) OVER`` (a scalar UDF cannot take
        OVER — error near ORDER)."""
        if not self._contains_nth_value(node):
            return node
        reason = (
            "T-SQL has no NTH_VALUE window function; emulate with "
            "ROW_NUMBER over the window. Statement preserved as a comment"
        )
        self.context.warn(reason, "nth_value")
        self.context.mark_unsupported("NTH_VALUE (T-SQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _contains_nth_value(self, value: object) -> bool:
        from unique.core.ast_nodes import WindowFunction

        if (
            isinstance(value, WindowFunction)
            and value.function.name.upper() == "NTH_VALUE"
        ):
            return True
        if isinstance(value, ASTNode):
            return any(
                self._contains_nth_value(getattr(value, f.name)) for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_nth_value(item) for item in value)
        return False

    def _gate_column_alias_ref(self, node: ASTNode) -> ASTNode:
        """Degrade a statement whose base-table ref renames columns via
        an alias list (``x AS xx(c1, c2)``) — WHOLE, on MySQL/Oracle.

        Neither engine has the spelling, and the derived-table rewrite
        T-SQL gets needs no column knowledge only because T-SQL accepts
        the alias list on the derived table; MySQL/Oracle do not."""
        if not self._contains_column_alias_ref(node):
            return node
        reason = (
            f"{self.context.target} has no column-renaming table alias "
            "(x AS xx(c1, c2)); rewrite with explicit column aliases in a "
            "derived table. Statement preserved as a comment"
        )
        self.context.warn(reason, "column_alias_ref")
        self.context.mark_unsupported("column-renaming table alias")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _contains_column_alias_ref(self, value: object) -> bool:
        from unique.core.ast_nodes import TableRef

        if isinstance(value, TableRef) and value.column_aliases:
            return True
        if isinstance(value, ASTNode):
            return any(
                self._contains_column_alias_ref(getattr(value, f.name))
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_column_alias_ref(item) for item in value)
        return False

    def _inline_having_alias(self, value: object) -> object:
        """MySQL lets HAVING reference a select alias; every other engine
        needs the aliased expression inlined (wave 157). Bottom-up so
        subquery HAVINGs get the same treatment."""
        node = self._map_children(value, self._inline_having_alias)
        if not (isinstance(node, SelectStatement) and node.having is not None):
            return node
        aliases = {
            col.name.upper(): col.expression
            for col in node.columns
            if isinstance(col, Alias) and not isinstance(col.expression, ColumnRef)
        }
        if not aliases:
            return node

        def substitute(v: object) -> object:
            if (
                isinstance(v, ColumnRef)
                and v.table is None
                and v.name.upper() in aliases
            ):
                return aliases[v.name.upper()]
            return self._map_children(v, substitute)

        having = substitute(node.having)
        if having is node.having:
            return node
        assert isinstance(having, ASTNode)
        return replace(node, having=having)

    def _map_children(self, value: object, fn: Callable[[object], object]) -> object:
        """Rebuild ``value`` with ``fn`` mapped over its child nodes
        (identity when nothing changes — callers can ``is``-check)."""
        if isinstance(value, tuple):
            new_items = tuple(fn(v) for v in value)
            return (
                value
                if all(a is b for a, b in zip(new_items, value, strict=True))
                else new_items
            )
        if not isinstance(value, ASTNode):
            return value
        changes: dict[str, object] = {}
        for f in fields(value):
            old = getattr(value, f.name)
            new = fn(old)
            if new is not old:
                changes[f.name] = new
        return replace(value, **changes) if changes else value  # type: ignore[arg-type]

    _GENERATED_COLUMN_RE = re.compile(r"(?i)\bGENERATED\s+ALWAYS\s+AS\b|\bAS\s*\(")

    def _gate_tsql_all_computed_table(self, node: ASTNode) -> ASTNode:
        """Degrade a CREATE TABLE whose columns are ALL computed — WHOLE,
        on T-SQL (wave 175): the engine requires at least one
        non-computed column (error 102 at the closing paren, verified
        live)."""
        if not (
            isinstance(node, CreateTableStatement)
            and not node.columns
            and node.table_constraints
        ):
            return node
        col_frags = [
            c
            for c in node.table_constraints
            if isinstance(c, PassthroughSQL) and c.kind == "COLUMN"
        ]
        if not col_frags or len(col_frags) != len(node.table_constraints):
            return node
        if not all(self._GENERATED_COLUMN_RE.search(c.sql) for c in col_frags):
            return node
        reason = (
            "T-SQL requires at least one non-computed column in a table; "
            "every column here is generated. Statement preserved as a comment"
        )
        self.context.warn(reason, "tsql_all_computed_table")
        self.context.mark_unsupported("all-computed table (T-SQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    _SETOP_ORDER_AGG_RE = re.compile(r"(?i)\b(MAX|MIN|SUM|COUNT|AVG)\s*\(")

    def _gate_pg_setop_order_aggregate(self, node: ASTNode) -> ASTNode:
        """Degrade a set-op query ordering by an aggregate or subquery —
        WHOLE, on PostgreSQL (error 0A000, wave 186): a UNION's ORDER BY
        may only name result columns there; MySQL tolerates the form."""
        if not (isinstance(node, SelectStatement) and node.set_op is not None):
            return node
        cur: SelectStatement | None = node
        offending = False
        while cur is not None:
            for item in cur.order_by:
                expr = item.expression
                if isinstance(expr, SubqueryExpression):
                    offending = True
                if isinstance(expr, FunctionCall) and self._SETOP_ORDER_AGG_RE.match(
                    f"{expr.name}("
                ):
                    offending = True
                if isinstance(expr, RawSQL) and self._SETOP_ORDER_AGG_RE.search(
                    expr.sql
                ):
                    offending = True
            cur = cur.set_query
        if not offending:
            return node
        reason = (
            "PostgreSQL's set-operation ORDER BY may only name result "
            "columns (no aggregates/subqueries). Statement preserved as "
            "a comment"
        )
        self.context.warn(reason, "pg_setop_order_aggregate")
        self.context.mark_unsupported("set-op ORDER BY aggregate (PG)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _gate_tsql_agg_distinct(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using STRING_AGG(DISTINCT …) — WHOLE, on
        T-SQL (wave 157). MySQL/PG accept DISTINCT inside their
        string-aggregate; T-SQL's STRING_AGG has no DISTINCT in any
        spelling and the rewrite needs a derived-table restructure."""
        if not self._contains_agg_distinct(node):
            return node
        reason = (
            "T-SQL's STRING_AGG takes no DISTINCT; deduplicate in a "
            "derived table first. Statement preserved as a comment"
        )
        self.context.warn(reason, "tsql_agg_distinct")
        self.context.mark_unsupported("STRING_AGG(DISTINCT) (T-SQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _contains_agg_distinct(self, value: object) -> bool:
        if isinstance(value, FunctionCall):
            name = value.name.upper()
            if name in ("STRING_AGG", "GROUP_CONCAT", "LISTAGG") and (
                value.distinct
                or any(
                    isinstance(a, RawSQL)
                    and "Unhandled expression type: Distinct" in a.reason
                    for a in value.args
                )
            ):
                return True
        if isinstance(value, ASTNode):
            return any(
                self._contains_agg_distinct(getattr(value, f.name))
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_agg_distinct(item) for item in value)
        return False

    def _gate_tsql_natural_join(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using a NATURAL join — WHOLE, on T-SQL.

        T-SQL has no NATURAL in any spelling, and synthesizing the ON
        needs column knowledge we don't have; dropping the modifier
        shipped JOINs with no condition at all."""
        if not self._contains_natural_join(node):
            return node
        reason = (
            "T-SQL has no NATURAL join; rewrite with an explicit ON over "
            "the common columns. Statement preserved as a comment"
        )
        self.context.warn(reason, "natural_join")
        self.context.mark_unsupported("NATURAL join (T-SQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _contains_natural_join(self, value: object) -> bool:
        from unique.core.ast_nodes import JoinClause, JoinType

        if isinstance(value, JoinClause) and (
            value.natural or value.join_type == JoinType.NATURAL
        ):
            return True
        if isinstance(value, ASTNode):
            return any(
                self._contains_natural_join(getattr(value, f.name))
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_natural_join(item) for item in value)
        return False

    def _contains_full_join(self, value: object) -> bool:
        from unique.core.ast_nodes import JoinClause, JoinType

        if isinstance(value, JoinClause) and value.join_type == JoinType.FULL:
            return True
        if isinstance(value, ASTNode):
            return any(
                self._contains_full_join(getattr(value, f.name)) for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_full_join(item) for item in value)
        return False

    def _gate_tsql_temp_view(self, node: ASTNode) -> ASTNode:
        """T-SQL forbids views over temporary tables (error 4508);
        degrade the CREATE VIEW whole with a warning."""
        from unique.core.ast_nodes import CreateViewStatement
        from unique.core.converter import TEMP_TABLES

        if not isinstance(node, CreateViewStatement):
            return node
        temps = TEMP_TABLES.get() or frozenset()
        if not temps:
            return node
        if not self._references_table(node.query, temps):
            return node
        reason = (
            "T-SQL does not allow views over temporary tables (4508); "
            "statement preserved as a comment"
        )
        self.context.warn(reason, "temp_view")
        self.context.mark_unsupported("VIEW over temporary table (T-SQL)")
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _references_table(self, value: object, names: frozenset[str]) -> bool:
        if isinstance(value, TableRef) and value.name.lower().lstrip("#") in names:
            return True
        if isinstance(value, ASTNode):
            return any(
                self._references_table(getattr(value, f.name), names)
                for f in fields(value)
            )
        if isinstance(value, tuple):
            return any(self._references_table(item, names) for item in value)
        return False

    def _gate_array_constructs(self, node: ASTNode) -> ASTNode:
        """Degrade a statement using PG array constructs — WHOLE.

        They shipped as fake calls (``dbo.ARRAY(1,2)``, unqualified
        ``ARRAY_AGG(x)``) with zero warnings; there is no spelling of
        arrays on these targets."""
        found = self._find_array_construct(node)
        if found is None:
            return node
        # Oracle DOES have WITHIN GROUP ordered-set aggregates and
        # aggregate-star calls; only the genuine array constructs
        # (ARRAY[…], ARRAY_AGG, UNNEST, array casts) lack a spelling.
        if self.context.target == "oracle" and found in (
            "WITHIN GROUP (ordered-set aggregate)",
        ):
            return node
        reason = (
            f"PostgreSQL construct {found} has no "
            f"{self.context.target} equivalent; statement preserved as a comment"
        )
        self.context.warn(reason, "array_construct")
        self.context.mark_unsupported(found)
        from unique.core.converter.emit import emit_node

        return RawSQL(sql=emit_node(node, self.context.source), reason=reason)

    def _find_array_construct(self, value: object) -> str | None:
        """First array-construct function name reachable from *value*."""
        if isinstance(value, ArrayLiteral):
            return "ARRAY[…] constructor"
        if (
            isinstance(value, FunctionCall)
            and value.name.upper() in self._ARRAY_CONSTRUCTS
        ):
            return value.name.upper()
        if isinstance(value, CastExpression) and (
            value.target_type.name.upper() == "ARRAY"
            or value.target_type.name.rstrip().endswith("[]")
        ):
            return "CAST(… AS ARRAY)"
        if isinstance(value, RawSQL):
            if "WithinGroup" in value.reason and "ARRAY[" not in value.sql:
                return "WITHIN GROUP (ordered-set aggregate)"
            if "ARRAY[" in value.sql:
                # An unmodeled fragment (unmapped operator, WITHIN GROUP,
                # complex subquery…) carrying an array constructor — the
                # ARRAY inside has no spelling on these targets either.
                return "ARRAY[…] constructor"
            if "Unhandled expression type: Bracket" in value.reason:
                return "array subscript"
        if isinstance(value, FunctionCall):
            # Custom-aggregate call syntax: fn(*) on a non-COUNT function,
            # or an inner ORDER BY captured as an unhandled-Order arg.
            if value.name.upper() not in ("COUNT", "COUNT_BIG") and any(
                isinstance(a, Star) for a in value.args
            ):
                return f"aggregate star call {value.name}(*)"
            if any(
                isinstance(a, RawSQL) and "Unhandled expression type: Order" in a.reason
                for a in value.args
            ):
                return f"aggregate ORDER BY inside {value.name}(…)"
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
