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
    CursorOperation,
    DeleteStatement,
    EmbeddedDML,
    ForLoopStatement,
    IfStatement,
    InsertStatement,
    LoopStatement,
    RawSQL,
    SelectIntoStatement,
    SelectStatement,
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

    selects: int = 0
    inserts: int = 0
    updates: int = 0
    deletes: int = 0
    # Sorted multiset of field counts, one entry per DML of that kind. Using a
    # multiset (not a sum) catches a column moving between two statements.
    select_field_counts: list[int] = field(default_factory=list)
    insert_field_counts: list[int] = field(default_factory=list)
    update_field_counts: list[int] = field(default_factory=list)
    conditions: int = 0
    if_branches: int = 0
    loops: int = 0

    def dml_verb_counts(self) -> dict[str, int]:
        return {
            "select": self.selects,
            "insert": self.inserts,
            "update": self.updates,
            "delete": self.deletes,
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
        cmp("if_branches", self.if_branches, other.if_branches)
        cmp("loops", self.loops, other.loops)
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


@dataclass
class _DmlCounts:
    selects: int = 0
    inserts: int = 0
    updates: int = 0
    deletes: int = 0
    select_fields: list[int] = field(default_factory=list)
    insert_fields: list[int] = field(default_factory=list)
    update_fields: list[int] = field(default_factory=list)
    conditions: int = 0


def _analyze_dml_text(text: str, dialect: str) -> _DmlCounts:
    """Parse a (possibly multi-statement) DML fragment and count verbs/fields/
    conditions. Resilient: unparseable fragments contribute zero."""
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
        # SELECT statements (including those nested as the source of INSERT ...
        # SELECT) are counted by scanning, but only top-level Selects that are
        # not the SELECT-part of an INSERT add a "select".
        if isinstance(stmt, exp.Select):
            result.selects += 1
            result.select_fields.append(_count_select_fields(stmt))
        result.conditions += _count_conditions(stmt)
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
        fp.select_field_counts.extend(counts.select_fields)
        fp.insert_field_counts.extend(counts.insert_fields)
        fp.update_field_counts.extend(counts.update_fields)
        fp.conditions += counts.conditions

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
    if check_fields:
        if sorted(src.select_field_counts) != sorted(out.select_field_counts):
            violations.append(
                f"SELECT field counts differ: "
                f"{sorted(src.select_field_counts)} != "
                f"{sorted(out.select_field_counts)}"
            )
        if sorted(src.insert_field_counts) != sorted(out.insert_field_counts):
            violations.append(
                f"INSERT field counts differ: "
                f"{sorted(src.insert_field_counts)} != "
                f"{sorted(out.insert_field_counts)}"
            )
        if sorted(src.update_field_counts) != sorted(out.update_field_counts):
            violations.append(
                f"UPDATE field counts differ: "
                f"{sorted(src.update_field_counts)} != "
                f"{sorted(out.update_field_counts)}"
            )
    if check_conditions and src.conditions != out.conditions:
        violations.append(
            f"condition counts differ: {src.conditions} != {out.conditions}"
        )
    if check_control_flow:
        if src.if_branches != out.if_branches:
            violations.append(
                f"IF branch counts differ: {src.if_branches} != " f"{out.if_branches}"
            )
        if src.loops != out.loops:
            violations.append(f"loop/cursor counts differ: {src.loops} != {out.loops}")
    return violations


__all__ = [
    "ProcedureFingerprint",
    "fingerprint",
    "assert_functionally_equivalent",
]
