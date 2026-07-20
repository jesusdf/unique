# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

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
    INTERSECT_ALL = auto()
    EXCEPT = auto()
    EXCEPT_ALL = auto()


class UnaryOperator(Enum):
    NOT = auto()
    NEGATIVE = auto()
    BITWISE_NOT = auto()
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
    BIT_AND = auto()
    BIT_OR = auto()
    BIT_XOR = auto()
    BIT_LSHIFT = auto()
    BIT_RSHIFT = auto()
    #: null-safe comparisons (PG IS [NOT] DISTINCT FROM, MySQL <=>)
    NULLSAFE_EQ = auto()
    NULLSAFE_NEQ = auto()
    #: IS (NULL/TRUE/FALSE tests)
    IS = auto()


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
    """Reference to a column, optionally qualified by table/schema.

    ``quoted``/``table_quoted`` record whether the identifier was quoted in
    the source, so emitters can re-quote it with the target dialect's quote
    characters instead of stripping it (audit 2026-07-02, S1-1).
    """

    name: str
    table: str | None = None
    schema: str | None = None
    quoted: bool = False
    table_quoted: bool = False


@dataclass(frozen=True)
class TableRef(ASTNode):
    """Reference to a table, optionally qualified by schema and aliased.

    ``quoted``/``schema_quoted`` record source quoting for faithful
    re-quoting in the target dialect (audit 2026-07-02, S1-1).
    """

    name: str
    schema: str | None = None
    alias: str | None = None
    database: str | None = None
    quoted: bool = False
    schema_quoted: bool = False
    #: PG ``x AS xx(c1, c2)`` column renames; T-SQL rewrites to a derived
    #: table, MySQL/Oracle degrade (no spelling without column knowledge).
    column_aliases: tuple[str, ...] = ()
    #: Set-returning function in relation position (``FROM fn(args) alias``):
    #: the FunctionCall (or fallback) that IS the relation. ``name`` then
    #: holds the alias so outer references still resolve (wave 110 — the
    #: function used to vanish, leaving the alias as a fake table name).
    function: ASTNode | None = None
    #: PG ``fn(…) WITH ORDINALITY [AS a(c…)]``.
    ordinality: bool = False


@dataclass(frozen=True)
class Star(ASTNode):
    """Represents SELECT * or table.*."""

    table: str | None = None


@dataclass(frozen=True)
class Alias(ASTNode):
    """An expression with an alias."""

    expression: ASTNode
    name: str
    quoted: bool = False


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
class ArrayLiteral(ASTNode):
    """A PostgreSQL array constructor.

    ``ARRAY[e1, e2, …]`` for value elements, or ``ARRAY(SELECT …)`` when
    the single element is a query. Modeled as its own node (not a
    FunctionCall) because the parenthesized function spelling is invalid
    even on PostgreSQL, and targets without arrays gate on the node.
    """

    elements: tuple[ASTNode, ...] = ()


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
    # Derived-table alias when the subquery is a FROM/JOIN relation
    # (``(SELECT …) t``); None for a scalar subquery.
    alias: str | None = None
    # Quantifier keyword for a ``> ALL/ANY/SOME (subquery)`` comparison
    # operand; None for a plain scalar/derived subquery.
    quantifier: str | None = None


@dataclass(frozen=True)
class ExpressionList(ASTNode):
    """A parenthesized expression list, e.g. the right side of ``x IN (a, b)``."""

    items: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class WindowSpec(ASTNode):
    """Window specification for window functions."""

    partition_by: tuple[ASTNode, ...] = ()
    order_by: tuple[OrderByItem, ...] = ()
    # The full frame clause (``ROWS BETWEEN 1 PRECEDING AND CURRENT ROW``,
    # ``RANGE UNBOUNDED PRECEDING``); standard SQL, spelled identically on every
    # engine we target, so it is captured once and emitted verbatim. Dropping it
    # silently changes results (a running total becomes a grand total).
    frame: str | None = None


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
    """A JOIN clause.

    ``using`` holds the column names of a ``USING (...)`` join; it is
    mutually exclusive with ``condition`` (audit 2026-07-02, S1-2 follow-up:
    v0.7.0 dropped USING entirely).
    """

    join_type: JoinType
    table: TableRef | SubqueryExpression
    alias: str | None = None
    condition: ASTNode | None = None
    using: tuple[str, ...] = ()
    #: NATURAL join modifier (PG/MySQL/Oracle); T-SQL must degrade.
    natural: bool = False
    #: LATERAL joined subquery: APPLY on T-SQL/Oracle, native elsewhere.
    lateral: bool = False


@dataclass(frozen=True)
class CTEDefinition(ASTNode):
    """A single CTE (WITH name AS (...))."""

    name: str
    query: SelectStatement
    columns: tuple[str, ...] = ()
    recursive: bool = False


@dataclass(frozen=True)
class LimitClause(ASTNode):
    """LIMIT/OFFSET or TOP or FETCH FIRST.

    ``percent`` marks a T-SQL ``TOP n PERCENT`` (limit by a fraction of rows
    rather than a row count).
    """

    limit: ASTNode | None = None
    offset: ASTNode | None = None
    percent: bool = False


# ---------------------------------------------------------------------------
# Type nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataType(ASTNode):
    """A SQL data type reference."""

    name: str
    params: tuple[int, ...] = ()
    unsigned: bool = False
    # ENUM/SET value lists (MySQL): the allowed strings are the type's
    # semantics, carried so non-MySQL emitters can render VARCHAR + CHECK.
    values: tuple[str, ...] = ()
    # When a source type cannot be translated faithfully (an unresolved
    # %TYPE/%ROWTYPE reference, or a type with no direct target equivalent),
    # the original source type text is preserved here so the emitter can append
    # a "/* UNIQUE: <original> */" marker. This documents the substitution for
    # the user and lets a reverse transpilation restore the original type.
    origin_comment: str | None = None


@dataclass(frozen=True)
class ColumnDefinition(ASTNode):
    """Column definition within CREATE TABLE."""

    name: str
    data_type: DataType
    nullable: bool = True
    default: ASTNode | None = None
    identity: bool = False
    #: Identity/auto-increment seed and step (e.g. T-SQL ``IDENTITY(100, 5)``).
    #: ``None`` means the engine default (1, 1); preserved so the sequence does
    #: not silently restart at 1 on the target.
    identity_seed: int | None = None
    identity_step: int | None = None
    #: ``GENERATED ALWAYS`` (immutable — forbids explicit inserts) vs the default
    #: ``BY DEFAULT``. Only PG/Oracle distinguish the two.
    identity_always: bool = False
    #: A computed/generated column expression (``GENERATED ALWAYS AS (expr)``).
    #: Distinct from ``identity`` — sqlglot models both with one node, but a
    #: generated column *computes* a value rather than auto-incrementing; treating
    #: it as IDENTITY corrupts the column. ``generated_stored`` records STORED
    #: (materialized) vs the default VIRTUAL.
    generated_expr: ASTNode | None = None
    generated_stored: bool = False
    primary_key: bool = False
    unique: bool = False
    check: ASTNode | None = None
    quoted: bool = False
    #: Column comment (MySQL inline ``COMMENT '…'``). Emitted inline on MySQL,
    #: as a trailing ``COMMENT ON COLUMN`` statement on PG/Oracle. Quoted literal.
    comment: str | None = None
    #: A constraint deferrability clause (``DEFERRABLE INITIALLY DEFERRED``, …)
    #: on an inline PRIMARY KEY/UNIQUE. PG and Oracle support it; T-SQL/MySQL do
    #: not, so it is dropped there. Stored as the raw clause text.
    deferrable: str | None = None
    #: MySQL's ``ON UPDATE CURRENT_TIMESTAMP`` auto-update column attribute. Only
    #: MySQL has it inline; the other engines need a trigger, so it degrades to a
    #: documented carrier rather than vanishing. Stored as the raw clause text.
    on_update: str | None = None
    #: A column ``COLLATE <name>`` clause. Collation names are engine-specific
    #: (Oracle BINARY_CI, PG "en_US", MySQL utf8mb4_…) with no portable mapping;
    #: kept on the source engine, and carried as a documented warning elsewhere
    #: (a live DB connection could resolve the actual collation). Raw clause text.
    collate: str | None = None


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
    #: A GROUP BY super-aggregate modifier over ``group_by``: ``"ROLLUP"``,
    #: ``"CUBE"`` or ``"GROUPING SETS"``. MySQL spells ROLLUP ``cols WITH ROLLUP``
    #: and has no CUBE/GROUPING SETS; every other engine wraps the columns.
    #: Dropping it discards the subtotal rows (or the whole GROUP BY).
    group_modifier: str | None = None
    #: The rendered ``GROUPING SETS (…)`` clause, kept verbatim (standard SQL on
    #: T-SQL/Oracle/PG); ``group_by`` holds its distinct columns for MySQL's base
    #: grouping fallback.
    grouping_sets_sql: str | None = None
    having: ASTNode | None = None
    order_by: tuple[OrderByItem, ...] = ()
    limit: LimitClause | None = None
    distinct: bool = False
    ctes: tuple[CTEDefinition, ...] = ()
    set_op: SetOperationType | None = None
    set_query: SelectStatement | None = None
    #: PG's empty select list (``SELECT;`` — zero columns, one row). Distinct
    #: from an empty ``columns`` tuple built by converter fallbacks, where a
    #: ``*`` default is load-bearing; only genuinely-empty source lists set
    #: this. PG re-emits the bare SELECT; no other engine has the form.
    empty_select_list: bool = False
    #: MySQL's ``SQL_CALC_FOUND_ROWS`` modifier — it makes the server count the
    #: full result set (ignoring LIMIT) for a following ``FOUND_ROWS()`` call. No
    #: other engine has it; dropping it silently breaks that pattern, so a
    #: non-MySQL target surfaces the loss as a carrier + warning.
    calc_found_rows: bool = False


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
    # Table-level constraints (PRIMARY KEY/FOREIGN KEY/UNIQUE/CHECK declared
    # outside a single column), kept as raw SQL fragments and re-transpiled
    # per dialect via sqlglot.
    table_constraints: tuple[PassthroughSQL, ...] = ()
    # PostgreSQL table-binding clauses with no mechanical equivalent
    # elsewhere: ``INHERITS (parent, …)`` and ``PARTITION OF parent FOR
    # VALUES …``. Kept verbatim; the transformer degrades the whole
    # statement to a carrier on targets without the concept (dropping
    # them silently loses the table's defining structure).
    inherits_clause: str | None = None
    partition_of_clause: str | None = None
    # MySQL's CREATE TABLE t2 LIKE t1 / PG's (LIKE t1): the source table
    # whose structure is cloned.
    like_source: str | None = None
    # Physical-storage table options with no logical/value impact and no
    # cross-engine equivalent (T-SQL ``WITH (MEMORY_OPTIMIZED = ON)`` /
    # ``DURABILITY``): re-emitted on their home engine, carried as a documented
    # note elsewhere rather than dropped silently.
    unsupported_options: tuple[str, ...] = ()
    # MySQL's table-level default ``COLLATE=<name>``: engine-specific, no portable
    # mapping; kept on MySQL, carried as a warning elsewhere. Raw ``COLLATE=…``.
    table_collate: str | None = None
    #: A table-level comment (MySQL ``COMMENT='…'``). Kept inline on MySQL; PG and
    #: Oracle take a trailing ``COMMENT ON TABLE`` statement. Quoted literal.
    table_comment: str | None = None


@dataclass(frozen=True)
class DropStatement(ASTNode):
    """DROP TABLE/VIEW/INDEX/PROCEDURE/FUNCTION."""

    object_type: str
    name: TableRef
    if_exists: bool = False
    cascade: bool = False
    # DROP INDEX / DROP TRIGGER: the owning table (T-SQL ``ON tbl`` /
    # legacy ``tbl.ix`` for indexes; PG ``ON tbl`` for triggers — mandatory
    # there, absent on the schema-scoped engines).
    on_table: str | None = None


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
    #: PL/SQL & plpgsql ``name CONSTANT type``. Native on Oracle/PG; targets
    #: without constants emit the plain (mutable) declaration — a safe
    #: relaxation for valid programs (documented in 03-unsupported).
    constant: bool = False
    #: ``name type NOT NULL [:= x]`` (PG/Oracle). Same relaxation contract
    #: as ``constant`` on targets without the modifier.
    not_null: bool = False


@dataclass(frozen=True)
class PragmaDeclaration(ASTNode):
    """A PL/SQL compiler directive in a declaration section (e.g. ``PRAGMA
    AUTONOMOUS_TRANSACTION``). Oracle re-emits it verbatim; other targets
    have no equivalent and degrade it to a documented comment + warning."""

    name: str


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
    label: str | None = None


@dataclass(frozen=True)
class BeginEndBlock(ASTNode):
    """BEGIN ... END block."""

    statements: tuple[ASTNode, ...] = ()
    label: str | None = None


@dataclass(frozen=True)
class StatementList(ASTNode):
    """A transparent sequence of statements (no BEGIN/END wrapper).

    Used when one syntactic construct expands to several statements, e.g.
    a T-SQL ``DECLARE @a INT, @b INT`` that becomes two declarations. The
    emitter renders the members in order with no surrounding tokens.
    """

    statements: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class AnonymousBlock(ASTNode):
    """A top-level anonymous procedural block (no CREATE wrapper).

    A bare ``EXEC proc …`` or a batch-level ``DECLARE @x …; …`` outside any
    routine. The emitter renders the engine's anonymous-block form: PostgreSQL
    ``DO $$ [DECLARE …] BEGIN … END $$;`` (or a plain ``CALL`` when there are no
    declarations), Oracle ``BEGIN … END;`` / ``DECLARE … BEGIN … END;``, MySQL
    has no anonymous block so a single call degrades to ``CALL`` and a
    declaring block is documented.

    ``degraded`` marks a block a target cannot run at the top level (e.g. a
    MySQL block containing control flow / a cursor loop): the emitter renders it
    as a ``-- UNIQUE:`` carrier comment, and the transformer registers the loss
    in ``result.warnings`` so nothing is silently dropped.
    """

    statements: tuple[ASTNode, ...] = ()
    degraded: bool = False


@dataclass(frozen=True)
class TryCatchBlock(ASTNode):
    """TRY ... CATCH / EXCEPTION block.

    ``catch_kind`` records the folded PL/SQL handler class when it is more
    specific than "any error": MySQL declares ``NOT FOUND`` instead of
    ``SQLEXCEPTION`` for a NO_DATA_FOUND-only handler.
    """

    try_body: tuple[ASTNode, ...] = ()
    catch_body: tuple[ASTNode, ...] = ()
    catch_kind: str = ""


@dataclass(frozen=True)
class GetDiagnosticsStatement(ASTNode):
    """``GET [STACKED] DIAGNOSTICS v = ITEM, …`` (plpgsql/MySQL).

    ``items`` holds (variable, ITEM) pairs. PG/MySQL keep native forms;
    Oracle/T-SQL convert to plain assignments in the transformer.
    """

    items: tuple[tuple[str, str], ...] = ()
    stacked: bool = False


@dataclass(frozen=True)
class PerformStatement(ASTNode):
    """plpgsql ``PERFORM <expr|select-tail>`` — evaluate and discard.

    ``expression`` holds the raw tail. Targets render their discard
    idiom (MySQL ``DO``, T-SQL a discard-variable DECLARE, Oracle a
    nested SELECT INTO block); a tail with a FROM clause degrades in
    the transformer (multi-row discard has no mechanical equivalent).
    """

    expression: ASTNode | None = None


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
    #: A bare re-raise inside a handler (``RAISE;``): every engine has a
    #: native spelling (PG/Oracle RAISE;, T-SQL THROW;, MySQL RESIGNAL;).
    reraise: bool = False


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
    #: PG ``VARIADIC name type[]`` (parsed as the NAME before wave 131).
    #: Only the PG emitter renders it; off-PG the array type degrades.
    variadic: bool = False


@dataclass(frozen=True)
class ExecuteStatement(ASTNode):
    """Dynamic SQL execution.

    ``immediate`` marks an Oracle ``EXECUTE IMMEDIATE`` (always a dynamic-SQL
    string/expression), as opposed to a T-SQL ``EXEC <proc>`` whose argument may
    be a named stored procedure. The distinction lets each target emitter route
    a genuine dynamic-SQL run to its ``EXECUTE``/``PREPARE`` form instead of the
    named-procedure ``CALL`` heuristic.
    """

    sql_expression: ASTNode
    params: tuple[ASTNode, ...] = ()
    immediate: bool = False
    #: plpgsql ``EXECUTE … INTO STRICT vars`` (exactly-one-row check).
    #: PG re-emits it; Oracle's SELECT INTO is inherently strict; T-SQL and
    #: MySQL have no equivalent and drop it.
    strict: bool = False
    # Oracle ``EXECUTE IMMEDIATE <expr> INTO v1, v2``: the dynamic SELECT's
    # scalar capture targets (each engine spells the capture differently).
    into_vars: tuple[str, ...] = ()


@dataclass(frozen=True)
class CallStatement(ASTNode):
    """A stored-procedure invocation (MySQL/PostgreSQL ``CALL name(args)``,
    Oracle ``name(args)``, T-SQL ``EXEC name args``).

    ``args`` is the raw argument text *inside* the parentheses, so each target
    emitter re-wraps it in its own call syntax. Distinct from ExecuteStatement,
    which models T-SQL ``EXEC``/Oracle ``EXECUTE IMMEDIATE`` dynamic SQL.
    """

    name: str
    args: str = ""
    schema: str | None = None


@dataclass(frozen=True)
class TransactionStatement(ASTNode):
    """Transaction control statement."""

    action: TransactionAction
    name: str | None = None


@dataclass(frozen=True)
class WaitForStatement(ASTNode):
    """T-SQL WAITFOR DELAY/TIME '<hh:mm:ss>'.

    ``kind`` is "DELAY" (relative) or "TIME" (absolute); ``value`` is the raw
    time literal. ``seconds`` is the parsed delay in seconds for a DELAY when it
    can be derived (used by engines whose sleep takes a numeric argument).
    """

    kind: str
    value: str
    seconds: float | None = None


@dataclass(frozen=True)
class TypeReference(ASTNode):
    """Oracle %TYPE or %ROWTYPE reference."""

    table: str
    column: str | None = None
    is_rowtype: bool = False


@dataclass(frozen=True)
class ForeachStatement(ASTNode):
    """plpgsql ``FOREACH var [SLICE n] IN ARRAY expr LOOP … END LOOP``.

    PG-only (arrays); other targets degrade whole with a carrier.
    """

    variable: str
    array_expr: str
    body: tuple[ASTNode, ...] = ()
    slice_depth: int | None = None


@dataclass(frozen=True)
class CursorDeclaration(ASTNode):
    """DECLARE CURSOR ... FOR SELECT."""

    name: str
    query: ASTNode | None = None
    parameters: tuple[ParameterDefinition, ...] = ()
    #: PG/T-SQL scrollability modifier: "SCROLL" or "NO SCROLL" (None =
    #: unspecified). Engines without scrollable cursors emit it away.
    scroll: str | None = None


@dataclass(frozen=True)
class CursorOperation(ASTNode):
    """OPEN, FETCH, CLOSE, DEALLOCATE cursor."""

    operation: str
    cursor_name: str
    into_vars: tuple[str, ...] = ()
    query: ASTNode | None = None
    #: OPEN c(args) — a parameterized cursor's actual arguments (raw text).
    args: str = ""
    #: PG ``OPEN c [NO] SCROLL FOR …``: "SCROLL" or "NO SCROLL" (None =
    #: unspecified). Only PostgreSQL re-emits it.
    scroll: str | None = None
    #: FETCH direction (``NEXT``, ``LAST``, ``ABSOLUTE 3``, …). Native on
    #: PG and T-SQL; Oracle/MySQL cursors are forward-only, so a non-NEXT
    #: direction degrades to the documented carrier there.
    direction: str | None = None


@dataclass(frozen=True)
class ForLoopStatement(ASTNode):
    """FOR ... IN ... LOOP ... END LOOP (Oracle) or FOR ... DO (MySQL)."""

    variable: str
    range_start: ASTNode | None = None
    range_end: ASTNode | None = None
    cursor: ASTNode | None = None
    body: tuple[ASTNode, ...] = ()
    reverse: bool = False


@dataclass(frozen=True)
class LoopStatement(ASTNode):
    """LOOP ... END LOOP (Oracle) or generic loop."""

    body: tuple[ASTNode, ...] = ()
    label: str | None = None


@dataclass(frozen=True)
class ExitStatement(ASTNode):
    """EXIT [WHEN condition] (Oracle) or LEAVE/BREAK."""

    condition: ASTNode | None = None
    label: str | None = None


@dataclass(frozen=True)
class ContinueStatement(ASTNode):
    """CONTINUE [WHEN condition]."""

    condition: ASTNode | None = None
    label: str | None = None


@dataclass(frozen=True)
class AssignmentStatement(ASTNode):
    """Variable assignment: var := expr (Oracle/PG) or SET @var = expr."""

    target: str
    value: ASTNode


@dataclass(frozen=True)
class NullStatement(ASTNode):
    """NULL; (Oracle PL/SQL no-op)."""


@dataclass(frozen=True)
class CommentStatement(ASTNode):
    """A source comment preserved verbatim across transpilation.

    ``text`` is the full comment including its delimiters. ``style`` is "line"
    for ``--`` comments or "block" for ``/* */`` comments. The transpiler
    re-emits the comment unchanged, except that a line comment is normalized to
    have exactly one space after ``--`` per ANSI SQL.

    When the comment is a ``/* UNIQUE: <orig> -- <dialect>-only … */`` note left
    by a forward pass that dropped a construct with no equivalent on the (then)
    target, ``restore_sql`` carries ``<orig>`` and ``restore_dialect`` carries
    ``<dialect>``. A later transpilation whose target equals ``restore_dialect``
    restores ``<orig>`` instead of re-emitting the note (a faithful round-trip);
    any other target keeps the note. Both are ``None`` for ordinary comments.

    ``header`` marks a comment re-homed from before a ``CREATE`` routine (SQL
    Server keeps such comments in the stored module; Oracle/PostgreSQL/MySQL
    store a routine from ``CREATE`` on): the emitter hoists it to the head of the
    declaration section so it sits right after the CREATE, inside the routine.
    """

    text: str
    style: str = "line"  # "line" | "block"
    restore_sql: str | None = None
    restore_dialect: str | None = None
    header: bool = False


@dataclass(frozen=True)
class PrintStatement(ASTNode):
    """PRINT (T-SQL) / DBMS_OUTPUT.PUT_LINE (Oracle) / RAISE NOTICE (PG)."""

    expression: ASTNode


@dataclass(frozen=True)
class LastIdentityCapture(ASTNode):
    """Assign the session's last generated identity to ``target``.

    Produced for the Oracle target (which has no session-scoped form);
    the pairing pass folds it into the preceding INSERT's
    ``RETURNING <idcol> INTO``. Unpaired, the emitter renders a valid
    NULL assignment with the documented CURRVAL note."""

    target: str


@dataclass(frozen=True)
class HandlerDeclaration(ASTNode):
    """MySQL ``DECLARE {EXIT|CONTINUE|UNDO} HANDLER FOR conds stmt``.

    An EXIT handler for SQLEXCEPTION folds into the enclosing block's
    TryCatchBlock off MySQL; other kinds/conditions degrade the routine.
    """

    kind: str = "EXIT"
    conditions: tuple[str, ...] = ()
    body: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class ExceptionHandler(ASTNode):
    """Single WHEN ... THEN handler in an EXCEPTION block."""

    exception_name: str
    body: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class ExceptionBlock(ASTNode):
    """Oracle EXCEPTION block or PG EXCEPTION WHEN."""

    handlers: tuple[ExceptionHandler, ...] = ()


@dataclass(frozen=True)
class CreateTriggerStatement(ASTNode):
    """CREATE TRIGGER statement.

    ``set_based_transition`` is set by the transformer when a *purely* set-based
    T-SQL trigger (using only ``FROM``/``JOIN inserted``/``deleted``) is being
    rewritten to a target with named transition tables: a PostgreSQL
    statement-level trigger whose function declares ``REFERENCING NEW TABLE AS
    inserted OLD TABLE AS deleted``. It stays ``False`` for row-level, mixed, or
    documented-only triggers (and for targets without a faithful equivalent,
    such as Oracle and MySQL).

    ``execute_function`` holds the referenced trigger function when the trigger
    delegates its body to one (PostgreSQL's ``… EXECUTE FUNCTION fn()`` form),
    in which case ``body`` is empty and ``referencing`` carries the raw
    ``REFERENCING … TABLE AS …`` transition-table clause for faithful
    re-emission. Targets without this split (MySQL/Oracle/T-SQL) document it.
    """

    name: str
    table: str
    timing: str = "BEFORE"
    events: tuple[str, ...] = ()
    for_each: str = "STATEMENT"
    body: tuple[ASTNode, ...] = ()
    or_replace: bool = False
    schema: str | None = None
    condition: ASTNode | None = None
    set_based_transition: bool = False
    execute_function: str | None = None
    #: Literal argument tokens of ``EXECUTE FUNCTION fn(args)`` — they become
    #: TG_ARGV[n] constants when the function body is inlined.
    execute_args: tuple[str, ...] = ()
    referencing: str = ""
    #: Column list of an ``UPDATE OF c1, c2`` event (Oracle/PG): the trigger
    #: fires only when one of these columns is updated.
    update_of: tuple[str, ...] = ()
    #: An Oracle COMPOUND TRIGGER (AFTER EACH ROW + AFTER STATEMENT sections
    #: over a PL/SQL collection). On a target with a mutating-table restriction
    #: (Oracle) or no equivalent (MySQL) it is emitted as a documented
    #: ``-- UNIQUE:`` carrier rather than mangled.
    compound: bool = False
    #: For the recognized "collect the affected key in AFTER EACH ROW, re-aggregate
    #: in AFTER STATEMENT" idiom, the AFTER STATEMENT body with the collection
    #: reference rewritten to the collected ``:NEW.<fk>``. A target without a
    #: mutating-table restriction (PostgreSQL) lowers this to a plain row-level
    #: AFTER trigger; empty when the idiom is not recognized (carrier fallback).
    compound_row_body: tuple[ASTNode, ...] = ()


@dataclass(frozen=True)
class AlterProcedureStatement(ASTNode):
    """ALTER PROCEDURE (T-SQL pattern for CREATE OR REPLACE)."""

    name: str
    parameters: tuple[ParameterDefinition, ...] = ()
    body: tuple[ASTNode, ...] = ()
    schema: str | None = None


@dataclass(frozen=True)
class SelectIntoStatement(ASTNode):
    """SELECT ... INTO variable (PL/SQL, PG).

    ``tsql_assignment`` marks a statement converted from a T-SQL
    ``SELECT @v = col ...``: zero matching rows leave the variable
    unchanged there, so the Oracle emitter must add a NO_DATA_FOUND
    handler to preserve those semantics (audit 2026-07-02, S2-3).
    """

    columns: tuple[ASTNode, ...] = ()
    into_vars: tuple[str, ...] = ()
    from_clause: ASTNode | None = None
    where: ASTNode | None = None
    rest_sql: str = ""
    tsql_assignment: bool = False
    #: A leading CTE clause (``WITH x AS (...)``) the SELECT draws from.
    with_sql: str = ""


@dataclass(frozen=True)
class EmbeddedDML(ASTNode):
    """Embedded DML statement to be transpiled by sqlglot."""

    sql: str
    dialect: str = ""


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


@dataclass(frozen=True)
class PassthroughSQL(ASTNode):
    """SQL that sqlglot can transpile directly but we don't model in IR.

    Carries the original statement plus its source dialect so the emitter
    can re-transpile it to the target dialect with sqlglot (e.g. ALTER
    TABLE, CREATE INDEX, CREATE SEQUENCE). If re-transpilation fails, the
    emitter falls back to a commented passthrough.
    """

    sql: str
    source_dialect: str
    kind: str = "statement"


# ---------------------------------------------------------------------------
# Script node (top-level container)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Script(ASTNode):
    """A complete SQL script containing multiple statements."""

    statements: tuple[ASTNode, ...] = ()


# ---------------------------------------------------------------------------
# Shared classifiers
# ---------------------------------------------------------------------------

#: Node types that make an anonymous block genuine procedural code — control
#: flow, declarations, cursors — and so require a procedural wrapper to run
#: (a PL/pgSQL ``DO $$ … $$`` on PostgreSQL, ``BEGIN … END;`` on Oracle). A
#: block of only simple statements (a bare CALL / DML) runs without one. Both
#: the transformer (to decide degradation on a target with no top-level block)
#: and the emitter (to decide wrapping) key off this single list.
PROCEDURAL_WRAPPER_NODES: tuple[type[ASTNode], ...] = (
    IfStatement,
    WhileStatement,
    ForLoopStatement,
    LoopStatement,
    BeginEndBlock,
    DeclareStatement,
    ExceptionBlock,
    TryCatchBlock,
    CursorDeclaration,
    CursorOperation,
)


def needs_procedural_wrapper(statements: tuple[ASTNode, ...]) -> bool:
    """Whether any statement requires a procedural wrapper to run.

    Recurses into StatementList containers (a transform may bundle a
    declaration with its loop) — the list itself is transparent."""
    for s in statements:
        if isinstance(s, PROCEDURAL_WRAPPER_NODES):
            return True
        if isinstance(s, StatementList) and needs_procedural_wrapper(s.statements):
            return True
    return False
