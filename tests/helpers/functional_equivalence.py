"""Functional-equivalence checks for transpiled stored procedures.

Syntactic validity (the routine parses / the live engine accepts it) is not
enough: a transpilation can parse cleanly yet quietly change behaviour by
dropping a WHERE clause, a selected column, or a branch. These helpers extract
a *structural fingerprint* of a procedure and compare the fingerprint before
and after transpilation. A mismatch flags a likely silent semantic change.

The fingerprint counts, over the whole routine body:

1. DML verbs -- how many SELECT / INSERT / UPDATE / DELETE statements.
2. Field counts per DML -- columns selected, columns inserted, assignments in
   an UPDATE SET. Compared as sorted multisets so order doesn't matter.
3. Predicate counts -- boolean conditions (comparisons / IN / LIKE / BETWEEN /
   IS [NOT] NULL) across all WHERE/HAVING/ON/JOIN clauses.
4. Control-flow counts -- IF branches, and loops/cursors (WHILE / FOR / LOOP /
   cursor OPEN/FETCH).

Items 1-3 are computed by parsing each DML fragment with sqlglot (robust to
dialect quirks). Item 4 comes from the project's own procedural AST, which
already distinguishes IfStatement / WhileStatement / ForLoopStatement /
LoopStatement / CursorOperation. DML fragments inside the body are captured as
EmbeddedDML / RawSQL text and re-parsed per fragment.

The goal is a reusable safety net, not a rigid equality: callers compare two
fingerprints and assert the dimensions that must be conserved for the dialect
pair under test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from unique.core.ast_nodes import (
    ContinueStatement,
    CursorOperation,
    DeleteStatement,
    EmbeddedDML,
    ExecuteStatement,
    ExitStatement,
    ForLoopStatement,
    IfStatement,
    InsertStatement,
    LoopStatement,
    MergeStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SelectIntoStatement,
    SelectStatement,
    TransactionStatement,
    TryCatchBlock,
    UpdateStatement,
    WhileStatement,
)
from unique.core.procedural.parser import ProceduralParser

# sqlglot read dialect per project dialect name.
_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}

# Predicate node types that count as one "condition" each.
_PREDICATE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.Like,
    exp.ILike,
    exp.In,
    exp.Between,
    exp.Is,
)


@dataclass
class ProcedureFingerprint:
    """Structural counts that should be conserved across transpilation."""

    # --- DML verbs ---
    selects: int = 0
    inserts: int = 0
    updates: int = 0
    deletes: int = 0
    merges: int = 0
    # Sorted multiset of field counts, one entry per DML of that kind. Using a
    # multiset (not a sum) catches a column moving between two statements.
    select_field_counts: list[int] = field(default_factory=list)
    insert_field_counts: list[int] = field(default_factory=list)
    update_field_counts: list[int] = field(default_factory=list)
    conditions: int = 0
    # --- query shape (silent loss here changes the result set) ---
    joins: int = 0
    set_operations: int = 0  # UNION / INTERSECT / EXCEPT
    group_bys: int = 0
    havings: int = 0
    subqueries: int = 0
    case_expressions: int = 0
    distincts: int = 0
    order_bys: int = 0
    aggregates: int = 0  # COUNT/SUM/AVG/MIN/MAX calls
    merge_when_clauses: int = 0
    # --- control flow ---
    if_branches: int = 0
    loops: int = 0
    returns: int = 0
    raises: int = 0  # RAISERROR / THROW / SIGNAL
    exec_calls: int = 0  # EXEC / CALL / dynamic SQL
    try_catch_blocks: int = 0
    transactions: int = 0  # BEGIN TRAN / COMMIT / ROLLBACK
    loop_controls: int = 0  # BREAK/LEAVE / CONTINUE/ITERATE

    def dml_verb_counts(self) -> dict[str, int]:
        return {
            "select": self.selects,
            "insert": self.inserts,
            "update": self.updates,
            "delete": self.deletes,
            "merge": self.merges,
        }

    def differences(self, other: ProcedureFingerprint) -> list[str]:
        """Human-readable list of dimensions that differ from ``other``."""
        diffs: list[str] = []

        def cmp(name: str, a: Any, b: Any) -> None:
            if a != b:
                diffs.append(f"{name}: {a} != {b}")

        cmp("selects", self.selects, other.selects)
        cmp("inserts", self.inserts, other.inserts)
        cmp("updates", self.updates, other.updates)
        cmp("deletes", self.deletes, other.deletes)
        cmp("merges", self.merges, other.merges)
        cmp(
            "select_field_counts",
            sorted(self.select_field_counts),
            sorted(other.select_field_counts),
        )
        cmp(
            "insert_field_counts",
            sorted(self.insert_field_counts),
            sorted(other.insert_field_counts),
        )
        cmp(
            "update_field_counts",
            sorted(self.update_field_counts),
            sorted(other.update_field_counts),
        )
        cmp("conditions", self.conditions, other.conditions)
        cmp("joins", self.joins, other.joins)
        cmp("set_operations", self.set_operations, other.set_operations)
        cmp("group_bys", self.group_bys, other.group_bys)
        cmp("havings", self.havings, other.havings)
        cmp("subqueries", self.subqueries, other.subqueries)
        cmp("case_expressions", self.case_expressions, other.case_expressions)
        cmp("distincts", self.distincts, other.distincts)
        cmp("order_bys", self.order_bys, other.order_bys)
        cmp("aggregates", self.aggregates, other.aggregates)
        cmp("merge_when_clauses", self.merge_when_clauses, other.merge_when_clauses)
        cmp("if_branches", self.if_branches, other.if_branches)
        cmp("loops", self.loops, other.loops)
        cmp("returns", self.returns, other.returns)
        cmp("raises", self.raises, other.raises)
        cmp("exec_calls", self.exec_calls, other.exec_calls)
        cmp("try_catch_blocks", self.try_catch_blocks, other.try_catch_blocks)
        cmp("transactions", self.transactions, other.transactions)
        cmp("loop_controls", self.loop_controls, other.loop_controls)
        return diffs


def _iter_nodes(node: Any) -> Any:
    """Yield every AST node in a procedural tree (depth-first)."""
    yield node
    for attr in (
        "body",
        "then_body",
        "else_body",
        "statements",
        "elseif_clauses",
    ):
        children = getattr(node, attr, None)
        if not children:
            continue
        # elseif clauses are (condition, body) tuples in some shapes; handle
        # both bare nodes and iterables of nodes.
        for child in children:
            if hasattr(child, "__class__") and not isinstance(
                child, (str, bytes, tuple)
            ):
                yield from _iter_nodes(child)
            elif isinstance(child, tuple):
                for sub in child:
                    if hasattr(sub, "__class__") and not isinstance(sub, (str, bytes)):
                        yield from _iter_nodes(sub)


def _dml_text(node: Any) -> str | None:
    """Return the raw SQL text of a DML-bearing node, if any."""
    if isinstance(node, (EmbeddedDML, RawSQL)):
        return str(node.sql)
    return None


def _count_select_fields(select: exp.Select) -> int:
    exprs = select.expressions
    # SELECT * counts as one "field" group; otherwise count projections.
    return len(exprs) if exprs else 0


def _count_conditions(tree: exp.Expression) -> int:
    return sum(1 for _ in tree.find_all(*_PREDICATE_TYPES))


# Aggregate function node types (one per aggregate call).
_AGGREGATE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Count,
    exp.Sum,
    exp.Avg,
    exp.Min,
    exp.Max,
)


@dataclass
class _DmlCounts:
    selects: int = 0
    inserts: int = 0
    updates: int = 0
    deletes: int = 0
    merges: int = 0
    select_fields: list[int] = field(default_factory=list)
    insert_fields: list[int] = field(default_factory=list)
    update_fields: list[int] = field(default_factory=list)
    conditions: int = 0
    joins: int = 0
    set_operations: int = 0
    group_bys: int = 0
    havings: int = 0
    subqueries: int = 0
    case_expressions: int = 0
    distincts: int = 0
    order_bys: int = 0
    aggregates: int = 0
    merge_when_clauses: int = 0


def _analyze_dml_text(text: str, dialect: str) -> _DmlCounts:
    """Parse a (possibly multi-statement) DML fragment and count verbs, fields,
    conditions and query-shape constructs. Resilient: unparseable fragments
    contribute zero."""
    read = _SQLGLOT_DIALECT.get(dialect, dialect)
    result = _DmlCounts()
    statements: list[Any]
    try:
        statements = list(sqlglot.parse(text, read=read))
    except Exception:
        try:
            statements = [sqlglot.parse_one(f"SELECT {text}", read=read)]
        except Exception:
            return result
    for stmt in statements:
        if stmt is None:
            continue
        # Count the top-level verb of this statement.
        if isinstance(stmt, exp.Insert):
            result.inserts += 1
            this = stmt.this
            cols = this.expressions if isinstance(this, exp.Expression) else []
            result.insert_fields.append(len(cols))
        elif isinstance(stmt, exp.Update):
            result.updates += 1
            result.update_fields.append(len(stmt.expressions))
        elif isinstance(stmt, exp.Delete):
            result.deletes += 1
        elif isinstance(stmt, exp.Merge):
            result.merges += 1
        # SELECT statements (including those nested as the source of INSERT ...
        # SELECT) are counted by scanning, but only top-level Selects that are
        # not the SELECT-part of an INSERT add a "select".
        if isinstance(stmt, exp.Select):
            result.selects += 1
            result.select_fields.append(_count_select_fields(stmt))
        result.conditions += _count_conditions(stmt)
        # Query-shape constructs anywhere in the statement tree. Losing any of
        # these silently changes the result set, so they are conserved too.
        result.joins += len(list(stmt.find_all(exp.Join)))
        result.set_operations += len(
            list(stmt.find_all(exp.Union, exp.Intersect, exp.Except))
        )
        result.group_bys += len(list(stmt.find_all(exp.Group)))
        result.havings += len(list(stmt.find_all(exp.Having)))
        result.subqueries += len(list(stmt.find_all(exp.Subquery)))
        result.case_expressions += len(list(stmt.find_all(exp.Case)))
        result.distincts += len(list(stmt.find_all(exp.Distinct)))
        result.order_bys += len(list(stmt.find_all(exp.Order)))
        result.aggregates += len(list(stmt.find_all(*_AGGREGATE_TYPES)))
        result.merge_when_clauses += len(list(stmt.find_all(exp.When)))
    return result


def fingerprint(sql: str, dialect: str) -> ProcedureFingerprint:
    """Compute a structural fingerprint of a procedure's body.

    Control-flow is counted from the procedural AST; DML verbs, fields and
    conditions from sqlglot per DML fragment. If the procedural parse fails,
    falls back to analysing the whole text as DML (control-flow counts stay 0).
    """
    fp = ProcedureFingerprint()

    # MySQL routines are wrapped in DELIMITER $$ ... $$ DELIMITER ; for client
    # execution; strip the wrappers so the procedural parser sees the routine.
    parse_sql = sql
    if dialect == "mysql":
        lines = [
            ln
            for ln in sql.splitlines()
            if ln.strip() not in ("DELIMITER $$", "DELIMITER ;")
        ]
        parse_sql = "\n".join(lines)
        # The routine body now ends with END$$ -> restore a plain END.
        parse_sql = parse_sql.replace("END$$", "END")

    try:
        parsed = ProceduralParser(dialect).parse(parse_sql)
        root = parsed.node
    except Exception:
        root = None

    dml_fragments: list[str] = []

    if root is not None:
        for node in _iter_nodes(root):
            if isinstance(node, IfStatement):
                fp.if_branches += 1
            elif isinstance(node, (WhileStatement, ForLoopStatement, LoopStatement)):
                fp.loops += 1
            elif isinstance(node, CursorOperation):
                # Count an OPEN as a loop-equivalent driver; FETCH/CLOSE are
                # part of the same construct and not double-counted.
                op = (getattr(node, "operation", "") or "").upper()
                if op == "OPEN":
                    fp.loops += 1
            elif isinstance(node, ReturnStatement):
                fp.returns += 1
            elif isinstance(node, RaiseErrorStatement):
                fp.raises += 1
            elif isinstance(node, ExecuteStatement):
                fp.exec_calls += 1
            elif isinstance(node, TryCatchBlock):
                fp.try_catch_blocks += 1
            elif isinstance(node, TransactionStatement):
                fp.transactions += 1
            elif isinstance(node, (ExitStatement, ContinueStatement)):
                fp.loop_controls += 1
            elif isinstance(node, MergeStatement):
                # Counted via sqlglot below (so its WHEN clauses, joins and
                # conditions are captured too); just feed the text through.
                text = getattr(node, "sql", None)
                if isinstance(text, str):
                    dml_fragments.append(text)
            elif isinstance(
                node,
                (
                    SelectStatement,
                    SelectIntoStatement,
                    InsertStatement,
                    UpdateStatement,
                    DeleteStatement,
                ),
            ):
                text = getattr(node, "sql", None)
                if isinstance(text, str):
                    dml_fragments.append(text)
            else:
                text = _dml_text(node)
                if text is not None:
                    dml_fragments.append(text)
    else:
        dml_fragments.append(sql)

    for text in dml_fragments:
        counts = _analyze_dml_text(text, dialect)
        fp.selects += counts.selects
        fp.inserts += counts.inserts
        fp.updates += counts.updates
        fp.deletes += counts.deletes
        # MERGE may be counted from the AST node above; only add sqlglot's
        # count when the AST didn't already classify a MergeStatement (i.e.
        # the merge arrived as embedded text). Avoid double counting by only
        # taking sqlglot merges that exceed what the AST recorded for this
        # fragment is impractical here, so merges are summed solely from the
        # AST node and from sqlglot when the fragment parsed as a bare Merge.
        fp.merges += counts.merges
        fp.select_field_counts.extend(counts.select_fields)
        fp.insert_field_counts.extend(counts.insert_fields)
        fp.update_field_counts.extend(counts.update_fields)
        fp.conditions += counts.conditions
        fp.joins += counts.joins
        fp.set_operations += counts.set_operations
        fp.group_bys += counts.group_bys
        fp.havings += counts.havings
        fp.subqueries += counts.subqueries
        fp.case_expressions += counts.case_expressions
        fp.distincts += counts.distincts
        fp.order_bys += counts.order_bys
        fp.aggregates += counts.aggregates
        fp.merge_when_clauses += counts.merge_when_clauses

    return fp


def assert_functionally_equivalent(
    source_sql: str,
    source_dialect: str,
    output_sql: str,
    output_dialect: str,
    *,
    check_fields: bool = True,
    check_conditions: bool = True,
    check_control_flow: bool = True,
    check_query_shape: bool = True,
) -> list[str]:
    """Compare fingerprints; return a list of violations (empty == equivalent).

    Callers can relax individual dimensions for dialect pairs where a
    transformation legitimately changes the count (e.g. a FOR cursor loop being
    expanded into an explicit OPEN/FETCH/CLOSE), but the DML verb counts should
    always be conserved.
    """
    src = fingerprint(source_sql, source_dialect)
    out = fingerprint(output_sql, output_dialect)
    violations: list[str] = []

    if src.dml_verb_counts() != out.dml_verb_counts():
        violations.append(
            f"DML verbs differ: {src.dml_verb_counts()} != " f"{out.dml_verb_counts()}"
        )

    def scalar(name: str, a: int, b: int) -> None:
        if a != b:
            violations.append(f"{name} differ: {a} != {b}")

    def multiset(name: str, a: list[int], b: list[int]) -> None:
        if sorted(a) != sorted(b):
            violations.append(f"{name} differ: {sorted(a)} != {sorted(b)}")

    if check_fields:
        multiset(
            "SELECT field counts", src.select_field_counts, out.select_field_counts
        )
        multiset(
            "INSERT field counts", src.insert_field_counts, out.insert_field_counts
        )
        multiset(
            "UPDATE field counts", src.update_field_counts, out.update_field_counts
        )
    if check_conditions:
        scalar("condition counts", src.conditions, out.conditions)
    if check_query_shape:
        scalar("join counts", src.joins, out.joins)
        scalar("set-operation counts", src.set_operations, out.set_operations)
        scalar("GROUP BY counts", src.group_bys, out.group_bys)
        scalar("HAVING counts", src.havings, out.havings)
        scalar("subquery counts", src.subqueries, out.subqueries)
        scalar("CASE counts", src.case_expressions, out.case_expressions)
        scalar("DISTINCT counts", src.distincts, out.distincts)
        scalar("ORDER BY counts", src.order_bys, out.order_bys)
        scalar("aggregate counts", src.aggregates, out.aggregates)
        scalar(
            "MERGE WHEN-clause counts",
            src.merge_when_clauses,
            out.merge_when_clauses,
        )
    if check_control_flow:
        scalar("IF branch counts", src.if_branches, out.if_branches)
        scalar("loop/cursor counts", src.loops, out.loops)
        scalar("RETURN counts", src.returns, out.returns)
        scalar("RAISE/THROW counts", src.raises, out.raises)
        scalar("EXEC/CALL counts", src.exec_calls, out.exec_calls)
        scalar("TRY/CATCH counts", src.try_catch_blocks, out.try_catch_blocks)
        scalar("transaction counts", src.transactions, out.transactions)
        scalar("loop-control counts", src.loop_controls, out.loop_controls)
    return violations


__all__ = [
    "ProcedureFingerprint",
    "fingerprint",
    "assert_functionally_equivalent",
]
