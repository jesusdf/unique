# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Structural similarity between two SQL scripts (possibly cross-dialect).

This module answers *"how structurally close are these two scripts?"* — the
migration-audit question "how faithful is this hand-migrated PL/SQL to the
original T-SQL?". It reports a **structural similarity** percentage with a
per-dimension breakdown; it is explicitly **not** a semantic-equivalence or
"probability of equivalence" claim (query equivalence is undecidable in
general — see ``docs/03-unsupported.md``).

Layers (see ``docs/TODO.md`` F1):

* **Layer 0 — normalization via the transpiler.** Both inputs are transpiled
  to one pivot dialect (PostgreSQL) with the project's own pipeline, which
  collapses dialect idioms (``ISNULL``/``NVL``/``COALESCE`` → one form) for
  free. On top of the pivot ASTs a light canonicalization removes
  comparison-only noise (alias names, commutative ``AND``/``OR`` order).
* **Layer 1 — dimension fingerprints.** A structural fingerprint (DML verbs,
  query shape, control flow) of each pivoted script, compared per dimension.
* **Layer 2 — tree matching.** Statements are aligned
  (:class:`difflib.SequenceMatcher` over statement-kind signatures + greedy
  best-match), each aligned DML pair scored with ``sqlglot.diff`` weighted by
  node type (predicates/joins heavy; identifiers/literals/aliases light), and
  procedural routine bodies aligned recursively over the project IR.

The fingerprint layer (:class:`ProcedureFingerprint`, :func:`fingerprint`,
:func:`assert_functionally_equivalent`) was promoted here from the test
helper; ``tests/helpers/functional_equivalence.py`` re-exports it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.diff import Keep, Move, Update, diff

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
from unique.core.detection import detect_dialect
from unique.core.procedural.parser import ProceduralParser

# sqlglot read dialect per project dialect name.
_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}

# The pivot dialect every input is transpiled to before comparison.
_PIVOT = "postgresql"

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


def _count_dml_verb(stmt: exp.Expression, result: _DmlCounts) -> None:
    """Tally the top-level verb of ``stmt`` and its field count."""
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
    if isinstance(stmt, exp.Select):
        result.selects += 1
        result.select_fields.append(_count_select_fields(stmt))


def _count_query_shape(stmt: exp.Expression, result: _DmlCounts) -> None:
    """Tally query-shape constructs anywhere in ``stmt`` (result-set shape)."""
    result.conditions += _count_conditions(stmt)
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


def _parse_dml(text: str, read: str) -> list[Any]:
    """Parse a (possibly multi-statement) DML fragment; [] if unparseable."""
    try:
        return list(sqlglot.parse(text, read=read))
    except Exception:
        try:
            return [sqlglot.parse_one(f"SELECT {text}", read=read)]
        except Exception:
            return []


def _analyze_dml_text(text: str, dialect: str) -> _DmlCounts:
    """Parse a DML fragment and count verbs, fields, conditions and query
    shape. Resilient: unparseable fragments contribute zero."""
    read = _SQLGLOT_DIALECT.get(dialect, dialect)
    result = _DmlCounts()
    for stmt in _parse_dml(text, read):
        if stmt is None:
            continue
        _count_dml_verb(stmt, result)
        _count_query_shape(stmt, result)
    return result


# Control-flow node class -> the fingerprint counter it increments by one.
_FP_COUNTERS: dict[type, str] = {
    IfStatement: "if_branches",
    ReturnStatement: "returns",
    RaiseErrorStatement: "raises",
    ExecuteStatement: "exec_calls",
    TryCatchBlock: "try_catch_blocks",
    TransactionStatement: "transactions",
}
_FP_LOOP_TYPES = (WhileStatement, ForLoopStatement, LoopStatement)
_FP_LOOPCTL_TYPES = (ExitStatement, ContinueStatement)


def _walk_control_flow(root: Any, fp: ProcedureFingerprint) -> list[str]:
    """Count control-flow nodes into ``fp``; return embedded DML fragments."""
    dml_fragments: list[str] = []
    for node in _iter_nodes(root):
        _count_control_node(node, fp, dml_fragments)
    return dml_fragments


def _count_control_node(
    node: Any, fp: ProcedureFingerprint, dml_fragments: list[str]
) -> None:
    """Increment the fingerprint for one procedural node, or collect its DML."""
    if isinstance(node, CursorOperation):
        _handle_cursor(node, fp, dml_fragments)
    elif isinstance(node, _FP_LOOP_TYPES):
        fp.loops += 1
    elif isinstance(node, _FP_LOOPCTL_TYPES):
        fp.loop_controls += 1
    else:
        for cls, attr in _FP_COUNTERS.items():
            if isinstance(node, cls):
                setattr(fp, attr, getattr(fp, attr) + 1)
                return
        _collect_dml_text(node, dml_fragments)


def _handle_cursor(
    node: Any, fp: ProcedureFingerprint, dml_fragments: list[str]
) -> None:
    """An ``OPEN c`` is a loop driver; ``OPEN c FOR <query>`` is a returned
    result set — count the query's DML, not a loop."""
    op = (getattr(node, "operation", "") or "").upper()
    query = getattr(node, "query", None)
    if op == "OPEN" and query is None:
        fp.loops += 1
    elif op == "OPEN" and query is not None:
        qtext = getattr(query, "sql", None)
        if isinstance(qtext, str):
            dml_fragments.append(qtext)


def _collect_dml_text(node: Any, dml_fragments: list[str]) -> None:
    """Append the raw SQL of a DML-bearing procedural node, if any."""
    if isinstance(
        node,
        (
            MergeStatement,
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
        return
    text = _dml_text(node)
    if text is not None:
        dml_fragments.append(text)


def _strip_mysql_delimiters(sql: str) -> str:
    """MySQL routines ship wrapped in ``DELIMITER $$ ... $$ DELIMITER ;``;
    strip the wrappers so the procedural parser sees the routine."""
    lines = [
        ln
        for ln in sql.splitlines()
        if ln.strip() not in ("DELIMITER $$", "DELIMITER ;")
    ]
    return "\n".join(lines).replace("END$$", "END")


def _add_dml_counts(fp: ProcedureFingerprint, counts: _DmlCounts) -> None:
    fp.selects += counts.selects
    fp.inserts += counts.inserts
    fp.updates += counts.updates
    fp.deletes += counts.deletes
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


def fingerprint(sql: str, dialect: str) -> ProcedureFingerprint:
    """Compute a structural fingerprint of a procedure's body.

    Control flow is counted from the procedural AST; DML verbs, fields and
    conditions from sqlglot per DML fragment. If the procedural parse fails,
    falls back to analysing the whole text as DML (control-flow counts stay 0).
    """
    fp = ProcedureFingerprint()
    parse_sql = _strip_mysql_delimiters(sql) if dialect == "mysql" else sql

    try:
        root = ProceduralParser(dialect).parse(parse_sql).node
    except Exception:
        root = None

    dml_fragments = _walk_control_flow(root, fp) if root is not None else [sql]
    for text in dml_fragments:
        _add_dml_counts(fp, _analyze_dml_text(text, dialect))
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


# ---------------------------------------------------------------------------
# Layer 0 — pivot normalization + statement splitting
# ---------------------------------------------------------------------------


def _pivot(sql: str, dialect: str, side: str) -> tuple[str, list[str]]:
    """Transpile ``sql`` to the pivot dialect; return (pivot_sql, warnings).

    Raises ``ValueError`` naming the input if it cannot be transpiled at all —
    a parse/transpile failure is a hard error, never a silent zero.
    """
    from unique.core.transpiler import transpile

    try:
        result = transpile(sql, dialect, _PIVOT)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(
            f"input {side}: could not transpile from '{dialect}': {exc}"
        ) from exc
    warnings = [f"input {side}: {w.message}" for w in result.warnings]
    return result.sql, warnings


def _split_top_level(sql: str) -> list[str]:
    """Split ``sql`` into top-level statements on ``;``.

    String literals, ``--`` and ``/* */`` comments and ``$tag$`` dollar-quoted
    bodies (PostgreSQL routine bodies) are treated as opaque so a ``;`` inside
    one never splits a statement. This is lexing, not a construct rewrite.
    """
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            j = _skip_quoted(sql, i)
            buf.append(sql[i:j])
            i = j
        elif ch == "-" and sql[i : i + 2] == "--":
            j = sql.find("\n", i)
            j = n if j < 0 else j
            buf.append(sql[i:j])
            i = j
        elif ch == "/" and sql[i : i + 2] == "/*":
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            buf.append(sql[i:j])
            i = j
        elif ch == "$":
            i = _consume_dollar(sql, i, buf)
        elif ch == ";":
            stmts.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    tail = "".join(buf)
    if tail.strip():
        stmts.append(tail)
    return stmts


def _consume_dollar(sql: str, i: int, buf: list[str]) -> int:
    """Consume a ``$tag$ ... $tag$`` body (or a lone ``$``) into ``buf``.

    The closing tag is located skipping ``--`` comments and string literals, so
    a stray ``$$`` the transpiler may leave inside a commented body line does
    not close the body early and desync the split.
    """
    tag = _dollar_tag(sql, i)
    if tag is None:
        buf.append(sql[i])
        return i + 1
    j = _find_close_tag(sql, i + len(tag), tag)
    buf.append(sql[i:j])
    return j


def _find_close_tag(sql: str, start: int, tag: str) -> int:
    """Index just past the next ``tag`` at ``start`` or later, skipping ``--``
    comments and ``'...'`` strings; end of string if none."""
    i, n = start, len(sql)
    while i < n:
        if sql[i : i + 2] == "--":
            nl = sql.find("\n", i)
            i = n if nl < 0 else nl + 1
        elif sql[i] == "'":
            i = _skip_quoted(sql, i)
        elif sql.startswith(tag, i):
            return i + len(tag)
        else:
            i += 1
    return n


def _skip_quoted(sql: str, i: int) -> int:
    """Return the index just past the single-quoted literal starting at ``i``."""
    n = len(sql)
    j = i + 1
    while j < n:
        if sql[j] == "'":
            if j + 1 < n and sql[j + 1] == "'":
                j += 2
                continue
            return j + 1
        j += 1
    return n


def _dollar_tag(sql: str, i: int) -> str | None:
    """If a ``$tag$`` dollar-quote opener starts at ``i``, return it, else None."""
    n = len(sql)
    j = i + 1
    while j < n and (sql[j].isalnum() or sql[j] == "_"):
        j += 1
    if j < n and sql[j] == "$":
        return sql[i : j + 1]
    return None


# ---------------------------------------------------------------------------
# Layer 2 — statement units, node weights, tree diff, alignment
# ---------------------------------------------------------------------------

# Node-type weights: losing a predicate/join/source must cost far more than an
# identifier, literal or alias. Everything unlisted gets the light default.
_HEAVY = 4.0
_MEDIUM = 2.0
_LIGHT = 1.0
_NODE_WEIGHTS: dict[type, float] = {
    exp.Where: _HEAVY,
    exp.Join: _HEAVY,
    exp.From: _HEAVY,
    exp.Group: _HEAVY,
    exp.Having: _HEAVY,
    exp.Union: _HEAVY,
    exp.Intersect: _HEAVY,
    exp.Except: _HEAVY,
    exp.Merge: _HEAVY,
    exp.When: _HEAVY,
    exp.EQ: _HEAVY,
    exp.NEQ: _HEAVY,
    exp.GT: _HEAVY,
    exp.GTE: _HEAVY,
    exp.LT: _HEAVY,
    exp.LTE: _HEAVY,
    exp.Like: _HEAVY,
    exp.ILike: _HEAVY,
    exp.In: _HEAVY,
    exp.Between: _HEAVY,
    exp.Is: _HEAVY,
    exp.Select: _MEDIUM,
    exp.Insert: _MEDIUM,
    exp.Update: _MEDIUM,
    exp.Delete: _MEDIUM,
    exp.Column: _MEDIUM,
    exp.Case: _MEDIUM,
    exp.Subquery: _MEDIUM,
    exp.Order: _MEDIUM,
    exp.Func: _MEDIUM,
    exp.Table: _MEDIUM,
}
# Leaf unit base weights (procedural leaves carry no sqlglot AST).
_CARRIER_WEIGHT = 8.0
_CONTROL_WEIGHT = 3.0
# Above this node count a ``sqlglot.diff`` is skipped for a size ratio (the
# diff is roughly quadratic; huge statements would dominate the runtime).
_MAX_DIFF_NODES = 400


def _node_weight(node: Any) -> float:
    for cls, weight in _NODE_WEIGHTS.items():
        if isinstance(node, cls):
            return weight
    return _LIGHT


def _ast_weight(ast: Any) -> float:
    return sum(_node_weight(node) for node in ast.walk())


@dataclass
class _Unit:
    """One comparable statement: a leaf DML/DDL (``ast``), a procedural
    routine/control node (``children``), or a degraded carrier."""

    kind: str
    ast: exp.Expression | None = None
    children: list[_Unit] = field(default_factory=list)
    degraded: bool = False
    # Normalized source text of a degraded carrier, so two identical carriers
    # (e.g. a script vs itself) match while a degrade only on one side does not.
    text: str = ""


def _safe_parse_one(text: str, read: str) -> Any:
    try:
        return sqlglot.parse_one(text, read=read)
    except Exception:
        return None


def _canon(ast: Any) -> Any:
    """Remove comparison-only noise: alias names → a sentinel, commutative
    AND/OR operands sorted by canonical key. Defensive: any glitch returns the
    original tree unchanged."""
    try:
        for node in ast.walk():
            if isinstance(node, exp.Alias) and node.args.get("alias"):
                node.set("alias", exp.to_identifier("a"))
            elif isinstance(node, exp.Connector):
                _sort_connector(node)
    except Exception:  # pragma: no cover - defensive
        return ast
    return ast


def _sort_connector(node: exp.Connector) -> None:
    left, right = node.left, node.right
    if left is not None and right is not None and left.sql() > right.sql():
        node.set("this", right)
        node.set("expression", left)


def _ast_kind(ast: exp.Expression) -> str:
    return type(ast).__name__.lower()


_ROUTINE_BODY_ATTRS = ("body", "statements")
_CONTAINER_BODIES: dict[type, tuple[str, ...]] = {
    IfStatement: ("then_body", "else_body"),
    WhileStatement: ("body",),
    ForLoopStatement: ("body",),
    LoopStatement: ("body",),
    TryCatchBlock: ("try_body", "catch_body"),
}
_DML_CLASSES = (
    SelectStatement,
    SelectIntoStatement,
    InsertStatement,
    UpdateStatement,
    DeleteStatement,
    MergeStatement,
    EmbeddedDML,
    RawSQL,
)
_LEAF_KINDS: list[tuple[type, str]] = [
    (ReturnStatement, "return"),
    (RaiseErrorStatement, "raise"),
    (ExecuteStatement, "exec"),
    (TransactionStatement, "tx"),
    (ExitStatement, "loopctl"),
    (ContinueStatement, "loopctl"),
]


def _container_kind(cls: type) -> str:
    if cls is IfStatement:
        return "if"
    if cls is TryCatchBlock:
        return "try"
    return "loop"


def _node_to_unit(node: Any) -> _Unit:
    """Turn one procedural IR node into a comparable :class:`_Unit`."""
    cls = type(node)
    bodies = _CONTAINER_BODIES.get(cls)
    if bodies is not None:
        children: list[_Unit] = []
        for attr in bodies:
            children += _body_units(getattr(node, attr, ()) or ())
        return _Unit(_container_kind(cls), children=children)
    if isinstance(node, _DML_CLASSES):
        return _dml_unit(getattr(node, "sql", None))
    if isinstance(node, CursorOperation):
        return _cursor_unit(node)
    for leaf_cls, kind in _LEAF_KINDS:
        if isinstance(node, leaf_cls):
            return _Unit(kind)
    return _Unit("other")


def _dml_unit(text: Any) -> _Unit:
    if not isinstance(text, str):
        return _Unit("dml")
    ast = _safe_parse_one(text, "postgres")
    return _Unit(_ast_kind(ast), ast=ast) if ast is not None else _Unit("dml")


def _cursor_unit(node: Any) -> _Unit:
    query = getattr(node, "query", None)
    qtext = getattr(query, "sql", None) if query is not None else None
    if isinstance(qtext, str):
        return _dml_unit(qtext)
    return _Unit("cursor")


def _body_units(body: Any) -> list[_Unit]:
    return [_node_to_unit(node) for node in body]


def _routine_body(node: Any) -> tuple[Any, ...] | None:
    for attr in _ROUTINE_BODY_ATTRS:
        body = getattr(node, attr, None)
        if body:
            return tuple(body)
    return None


def _is_comment_only(stmt: str) -> bool:
    """Whether ``stmt`` is only comments/whitespace — a degraded carrier or a
    ``-- UNIQUE:`` note left when a construct could not be transpiled."""
    without_block = _strip_block_comments(stmt)
    for line in without_block.splitlines():
        text = line.strip()
        if text and not text.startswith("--"):
            return False
    return True


def _strip_block_comments(stmt: str) -> str:
    out: list[str] = []
    i, n = 0, len(stmt)
    while i < n:
        if stmt[i : i + 2] == "/*":
            end = stmt.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(stmt[i])
            i += 1
    return "".join(out)


def _code_head(stmt: str) -> str:
    """The statement with leading comment/blank lines removed, lowercased.

    A statement may carry ``-- OBJECT: …`` header comments before the code; the
    routine test must look past them.
    """
    for line in stmt.splitlines():
        text = line.strip()
        if text and not text.startswith("--"):
            return stmt[stmt.index(line) :].lower()
    return ""


def _is_routine(stmt: str) -> bool:
    """Whether ``stmt`` is a stored routine or an anonymous ``DO`` block."""
    head = _code_head(stmt)
    if head.startswith("do") and "$" in head[:40]:
        return True
    return head.startswith(("create", "alter")) and (
        "function" in head[:60] or "procedure" in head[:60]
    )


def _routine_unit(stmt: str) -> _Unit:
    """Parse a routine with the procedural parser and build its body units.
    A routine that will not parse degrades to a carrier (counts as unmatched).
    """
    try:
        body = _routine_body(ProceduralParser(_PIVOT).parse(stmt).node)
    except Exception:
        body = None
    if body is None:
        return _Unit("carrier", degraded=True, text=_norm_text(stmt))
    return _Unit("routine", children=_body_units(body))


def _norm_text(stmt: str) -> str:
    """Whitespace-collapsed text of a carrier, for identical-carrier matching."""
    return " ".join(stmt.split())


def _script_units(pivot_sql: str) -> list[_Unit]:
    """Split a pivoted script into comparable statement units."""
    units: list[_Unit] = []
    for stmt in _split_top_level(pivot_sql):
        text = stmt.strip()
        if not text:
            continue
        if _is_comment_only(text):
            units.append(_Unit("carrier", degraded=True, text=_norm_text(text)))
        elif _is_routine(text):
            units.append(_routine_unit(text))
        else:
            ast = _safe_parse_one(text, "postgres")
            units.append(
                _Unit(_ast_kind(ast), ast=ast)
                if ast is not None
                else _Unit("carrier", degraded=True, text=_norm_text(text))
            )
    return units


def _tree_diff_score(a: Any, b: Any) -> float:
    """Weighted ``sqlglot.diff`` similarity of two ASTs in [0, 1]."""
    a, b = _canon(a.copy()), _canon(b.copy())
    if a == b:
        # Structurally identical after canonicalization. sqlglot.diff uses a
        # Change-Distiller heuristic that does not return all-Keep even for
        # equal trees, so short-circuit to a perfect score.
        return 1.0
    wa, wb = _ast_weight(a), _ast_weight(b)
    if wa + wb == 0:
        return 1.0
    if len(list(a.walk())) > _MAX_DIFF_NODES or len(list(b.walk())) > _MAX_DIFF_NODES:
        return min(wa, wb) / max(wa, wb)
    kept = 0.0
    for edit in diff(a, b):
        if isinstance(edit, (Keep, Move)):
            kept += _node_weight(edit.source)
        elif isinstance(edit, Update):
            kept += 0.5 * _node_weight(edit.source)
    return min(1.0, 2.0 * kept / (wa + wb))


def _unit_weight(unit: _Unit) -> float:
    if unit.degraded:
        return _CARRIER_WEIGHT
    if unit.children:
        return sum(_unit_weight(child) for child in unit.children) + _LIGHT
    if unit.ast is not None:
        return _ast_weight(unit.ast)
    return _CONTROL_WEIGHT


def _unit_similarity(a: _Unit, b: _Unit) -> float:
    """Similarity in [0, 1] of two aligned units (kind already comparable)."""
    if a.degraded and b.degraded:
        # Both sides degraded the same construct — a match only if the carrier
        # text is identical (a script vs itself); an asymmetric degrade is 0.
        return 1.0 if a.text and a.text == b.text else 0.0
    if a.degraded or b.degraded:
        return 0.0
    if a.children or b.children:
        num, den, _ = _align(a.children, b.children)
        return num / den if den else 1.0
    if a.kind != b.kind:
        return 0.0
    if a.ast is not None and b.ast is not None:
        return _tree_diff_score(a.ast, b.ast)
    return 1.0


def _score_pair(a: _Unit, b: _Unit) -> tuple[float, float, float]:
    """Return (weighted_matched, weight_sum, similarity) for an aligned pair."""
    den = _unit_weight(a) + _unit_weight(b)
    score = _unit_similarity(a, b)
    return score * den, den, score


def _greedy(la: list[_Unit], lb: list[_Unit]) -> tuple[float, float, list[Any]]:
    """Greedy best-match within a replace block; unmatched count fully against."""
    num = den = 0.0
    matches: list[Any] = []
    remaining = list(range(len(lb)))
    for ua in la:
        best_j, best_s = None, 0.0
        for j in remaining:
            _, _, s = _score_pair(ua, lb[j])
            if s > best_s:
                best_j, best_s = j, s
        if best_j is None:
            den += _unit_weight(ua)
            continue
        n, d, s = _score_pair(ua, lb[best_j])
        num += n
        den += d
        matches.append((ua, lb[best_j], s))
        remaining.remove(best_j)
    for j in remaining:
        den += _unit_weight(lb[j])
    return num, den, matches


def _align(
    units_a: list[_Unit], units_b: list[_Unit]
) -> tuple[float, float, list[Any]]:
    """Align two statement lists; return (matched_weight, total_weight, pairs).

    ``SequenceMatcher`` over statement-kind signatures aligns the common
    subsequence positionally (cheap, exact for identical/aligned scripts). Every
    remainder — replaced, deleted or inserted — is pooled and greedily
    best-matched, so a statement that merely *moved* (which SequenceMatcher
    reports as a delete on one side and an insert on the other) is rematched
    rather than counted as two losses.
    """
    matcher = SequenceMatcher(
        a=[u.kind for u in units_a], b=[u.kind for u in units_b], autojunk=False
    )
    num = den = 0.0
    matches: list[Any] = []
    left_a: list[_Unit] = []
    left_b: list[_Unit] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2), strict=False):
                n, d, s = _score_pair(units_a[i], units_b[j])
                num += n
                den += d
                matches.append((units_a[i], units_b[j], s))
        else:
            left_a.extend(units_a[i1:i2])
            left_b.extend(units_b[j1:j2])
    n, d, m = _greedy(left_a, left_b)
    return num + n, den + d, matches + m


# ---------------------------------------------------------------------------
# Layer 1 — dimension scores, and the public compare() API
# ---------------------------------------------------------------------------

# Fingerprint fields grouped into reported dimensions.
_DIM_FIELDS: dict[str, tuple[str, ...]] = {
    "dml_structure": (
        "selects",
        "inserts",
        "updates",
        "deletes",
        "merges",
    ),
    "predicates": (
        "conditions",
        "joins",
        "set_operations",
        "group_bys",
        "havings",
        "subqueries",
        "case_expressions",
        "distincts",
        "order_bys",
        "aggregates",
        "merge_when_clauses",
    ),
    "control_flow": (
        "if_branches",
        "loops",
        "returns",
        "raises",
        "exec_calls",
        "try_catch_blocks",
        "transactions",
        "loop_controls",
    ),
}
# Weights of each dimension in the overall score. Tree-match is the finest,
# most trustworthy signal; the fingerprint dimensions corroborate it.
_DIM_WEIGHTS: dict[str, float] = {
    "tree_match": 0.40,
    "dml_structure": 0.25,
    "predicates": 0.20,
    "control_flow": 0.15,
}


def _aggregate_fingerprint(pivot_sql: str) -> ProcedureFingerprint:
    """Sum per-statement fingerprints across a whole pivoted script."""
    agg = ProcedureFingerprint()
    for stmt in _split_top_level(pivot_sql):
        if not stmt.strip() or _is_comment_only(stmt.strip()):
            continue
        _merge_fingerprint(agg, fingerprint(stmt, _PIVOT))
    return agg


def _merge_fingerprint(agg: ProcedureFingerprint, fp: ProcedureFingerprint) -> None:
    for name in agg.__dataclass_fields__:
        a_val = getattr(agg, name)
        b_val = getattr(fp, name)
        if isinstance(a_val, int):
            setattr(agg, name, a_val + b_val)
        elif isinstance(a_val, list):
            a_val.extend(b_val)


def _dimension_score(
    a: ProcedureFingerprint, b: ProcedureFingerprint, fields: tuple[str, ...]
) -> tuple[float, bool]:
    """Bray-Curtis similarity over a group of count fields, and whether the
    dimension is *applicable* (present on at least one side).

    ``1 - Σ|a-b| / Σ(a+b)``: identical counts → 1. A dimension empty on both
    sides scores 1 vacuously but is flagged not-applicable so it does not
    inflate the overall when neither script exercises it (e.g. two scripts with
    no control flow must not read as "control-flow identical").
    """
    total = diff_sum = 0
    for name in fields:
        av, bv = getattr(a, name), getattr(b, name)
        total += av + bv
        diff_sum += abs(av - bv)
    if total == 0:
        return 1.0, False
    return 1.0 - diff_sum / total, True


@dataclass
class StatementPair:
    """One aligned statement pair (or a matched routine) in the report."""

    kind_a: str
    kind_b: str
    score: float


@dataclass
class SimilarityReport:
    """Result of :func:`compare` — structural similarity, never equivalence."""

    overall: float
    dimensions: dict[str, float]
    dialect_a: str
    dialect_b: str
    detected_a: bool
    detected_b: bool
    statement_pairs: list[StatementPair]
    unmatched_a: int
    unmatched_b: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "dimensions": self.dimensions,
            "dialect_a": self.dialect_a,
            "dialect_b": self.dialect_b,
            "detected_a": self.detected_a,
            "detected_b": self.detected_b,
            "statement_pairs": [
                {"kind_a": p.kind_a, "kind_b": p.kind_b, "score": p.score}
                for p in self.statement_pairs
            ],
            "unmatched_a": self.unmatched_a,
            "unmatched_b": self.unmatched_b,
            "warnings": self.warnings,
        }


def _resolve_dialect(sql: str, given: str | None, side: str) -> tuple[str, bool]:
    """Return (dialect, was_detected); raise if detection finds no signal."""
    if given is not None:
        return given, False
    detected = detect_dialect(sql).dialect
    if detected is None:
        raise ValueError(
            f"input {side}: could not auto-detect the SQL dialect; "
            f"pass --dialect-{side.lower()} explicitly"
        )
    return detected, True


def _pct(value: float) -> float:
    return round(100.0 * max(0.0, min(1.0, value)), 1)


def _weighted_overall(dims: dict[str, float], applicable: set[str]) -> float:
    """Weighted mean of the applicable dimensions, weights renormalized so a
    vacuous (both-empty) dimension neither counts for nor against the score."""
    total_weight = sum(_DIM_WEIGHTS[name] for name in applicable)
    if total_weight == 0:
        return 0.0
    return sum(dims[name] * _DIM_WEIGHTS[name] for name in applicable) / total_weight


def _degenerate_report(
    overall: float, da: str, db: str, det_a: bool, det_b: bool
) -> SimilarityReport:
    """Report for the empty-input edge cases (both empty → 100; one empty → 0)."""
    score = overall / 100.0
    dims = {k: _pct(score) for k in ("tree_match", *_DIM_FIELDS)}
    return SimilarityReport(
        overall=overall,
        dimensions=dims,
        dialect_a=da,
        dialect_b=db,
        detected_a=det_a,
        detected_b=det_b,
        statement_pairs=[],
        unmatched_a=0,
        unmatched_b=0,
        warnings=[],
    )


def compare(
    sql_a: str,
    sql_b: str,
    dialect_a: str | None = None,
    dialect_b: str | None = None,
) -> SimilarityReport:
    """Compare two SQL scripts and report their **structural similarity**.

    Both inputs are transpiled to the PostgreSQL pivot, then compared by
    structural fingerprint (DML/predicate/control-flow dimensions) and by
    weighted tree alignment. The result is a similarity percentage with a
    per-dimension breakdown — never a probability of semantic equivalence.

    ``dialect_a``/``dialect_b`` default to auto-detection (the report records
    whether each was detected). Raises ``ValueError`` if a dialect cannot be
    detected or an input cannot be transpiled.
    """
    empty_a, empty_b = not sql_a.strip(), not sql_b.strip()
    da, det_a = (
        _resolve_dialect(sql_a, dialect_a, "A")
        if not empty_a
        else (dialect_a or "", False)
    )
    db, det_b = (
        _resolve_dialect(sql_b, dialect_b, "B")
        if not empty_b
        else (dialect_b or "", False)
    )
    if empty_a and empty_b:
        return _degenerate_report(100.0, da, db, det_a, det_b)
    if empty_a or empty_b:
        return _degenerate_report(0.0, da, db, det_a, det_b)

    pivot_a, warn_a = _pivot(sql_a, da, "A")
    pivot_b, warn_b = _pivot(sql_b, db, "B")

    fp_a = _aggregate_fingerprint(pivot_a)
    fp_b = _aggregate_fingerprint(pivot_b)
    scored = {
        name: _dimension_score(fp_a, fp_b, fields)
        for name, fields in _DIM_FIELDS.items()
    }
    dims = {name: score for name, (score, _) in scored.items()}
    applicable = {name for name, (_, ok) in scored.items() if ok}

    units_a, units_b = _script_units(pivot_a), _script_units(pivot_b)
    num, den, pairs = _align(units_a, units_b)
    dims["tree_match"] = num / den if den else 1.0
    applicable.add("tree_match")

    overall = _weighted_overall(dims, applicable)
    return SimilarityReport(
        overall=_pct(overall),
        dimensions={name: _pct(score) for name, score in dims.items()},
        dialect_a=da,
        dialect_b=db,
        detected_a=det_a,
        detected_b=det_b,
        statement_pairs=[StatementPair(a.kind, b.kind, _pct(s)) for a, b, s in pairs],
        unmatched_a=len(units_a) - len(pairs),
        unmatched_b=len(units_b) - len(pairs),
        warnings=_dedupe(warn_a + warn_b),
    )


def _dedupe(messages: list[str]) -> list[str]:
    """Collapse repeated transpiler warnings to unique messages (order kept)."""
    seen: set[str] = set()
    out: list[str] = []
    for msg in messages:
        if msg not in seen:
            seen.add(msg)
            out.append(msg)
    return out


__all__ = [
    "ProcedureFingerprint",
    "SimilarityReport",
    "StatementPair",
    "assert_functionally_equivalent",
    "compare",
    "fingerprint",
]
