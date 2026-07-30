"""Relation-shaped FROM items and DELETE emission (B17 step-4 seam of emit.py).

PIVOT/UNPIVOT relations and the DELETE statement family were carved out of
``emit.py`` when the 2026-07-30 challenge fixes (PIVOT modeling, DELETE caps,
multi-table DELETE) pushed it past its size ratchet. Same contract as every
seam: this module defines its own names first, then imports the ``emit.py``
helpers it needs at its tail (see the emit.py docstring for why the mutual
recursion is safe), and ``emit.py`` re-exports it via ``import *``.
"""

from __future__ import annotations

from collections.abc import Callable

from unique.core.ast_nodes import (
    Alias,
    ASTNode,
    ColumnRef,
    DeleteStatement,
    PivotRelation,
    SubqueryExpression,
    TableRef,
    UnpivotRelation,
)
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter._base import SOURCE_DIALECT

__all__ = [
    "_unpivot_carried_columns",
    "_emit_unpivot_relation",
    "_pivot_group_columns",
    "_emit_pivot_relation",
    "_DELETE_CAP",
    "_emit_delete",
]

#: Engines whose unquoted identifiers fold to UPPER case — their UNPIVOT
#: name-column values arrive upper-cased and the rewrite must match.
_FOLDS_IDENT_UPPER = frozenset({"oracle"})

#: Default alias for a derived-table source inside a PIVOT/UNPIVOT rewrite.
#: Oracle forbids an alias on the pivoted subquery itself (ORA-00933) → None.
_SRC_DEFAULT_ALIAS: dict[str, str | None] = {"oracle": None}


def _relation_source_sql(src: ASTNode, dialect: str) -> str:
    """The FROM-item SQL of a PIVOT/UNPIVOT source (shared prelude)."""
    if isinstance(src, SubqueryExpression):
        inner = _emit_select(src.query, dialect)
        alias = src.alias or _SRC_DEFAULT_ALIAS.get(dialect, "uq_src")
        return f"({inner})" + (f" {_ident(alias, False, dialect)}" if alias else "")
    if isinstance(src, TableRef):
        return _emit_table_ref(src, dialect)
    return emit_node(src, dialect)


def _unpivot_carried_columns(
    src: ASTNode, unpivoted: tuple[str, ...]
) -> list[str] | None:
    """The source's output columns that survive the UNPIVOT (everything not in
    the IN-list), needed to build the UNION ALL rewrite. ``None`` when the source
    has no visible projection to name (a bare table, a ``*``, or an unaliased
    expression) — the caller then degrades to a carrier rather than emit dangling
    references."""
    if not isinstance(src, SubqueryExpression):
        return None
    names: list[str] = []
    for col in src.query.columns:
        if isinstance(col, (Alias, ColumnRef)):
            names.append(col.name)
        else:
            return None
    lowered = {u.lower() for u in unpivoted}
    return [n for n in names if n.lower() not in lowered]


def _emit_unpivot_relation(node: UnpivotRelation, dialect: str) -> str:
    """Emit the FROM-item SQL for ``<source> UNPIVOT (val FOR col IN (…))``.

    Rendered as a ``UNION ALL`` (one arm per unpivoted column, excluding NULLs to
    match UNPIVOT's default) on every target — not the native UNPIVOT operator.
    The reason is the name-column *value*: native UNPIVOT re-derives it from the
    IN-list identifier, and Oracle folds an unquoted identifier to upper case
    (its UNPIVOT yields ``'A'`` where T-SQL yields ``'a'``). The rewrite instead
    emits an explicit string literal cased exactly as the *source* engine would
    produce it, so the values match across engines."""
    src_sql = _relation_source_sql(node.source, dialect)

    carried = _unpivot_carried_columns(node.source, node.columns)
    if carried is None:
        return (
            f"{src_sql} /* UNIQUE: UNPIVOT has no {dialect} equivalent and the "
            "source columns are not visible to rewrite it as UNION ALL — see "
            "docs/03-unsupported.md */"
        )
    val = _ident(node.value_col, False, dialect)
    name = _ident(node.name_col, False, dialect)
    upper = SOURCE_DIALECT.get() in _FOLDS_IDENT_UPPER
    arms: list[str] = []
    for c in node.columns:
        proj = [_ident(cc, False, dialect) for cc in carried]
        display = c.upper() if upper else c
        proj.append(f"'{display.replace(chr(39), chr(39) * 2)}' AS {name}")
        proj.append(f"{_ident(c, False, dialect)} AS {val}")
        arm = f"SELECT {', '.join(proj)} FROM {src_sql}"
        if not node.include_nulls:
            arm += f" WHERE {_ident(c, False, dialect)} IS NOT NULL"
        arms.append(arm)
    alias = _ident(node.alias or "uq_unpivot", False, dialect)
    return f"({' UNION ALL '.join(arms)}) {alias}"


def _pivot_group_columns(src: ASTNode, node: PivotRelation) -> list[str] | None:
    """The source columns that survive a PIVOT (become GROUP BY keys) — every
    projected column except the pivot column and the aggregate's argument.

    Returns None when the source projection is not visible (a bare table or a
    ``SELECT *``), so the conditional-aggregation rewrite must degrade instead.
    """
    if not isinstance(src, SubqueryExpression):
        return None
    names: list[str] = []
    for item in src.query.columns:
        if isinstance(item, Alias) or (isinstance(item, ColumnRef) and not item.table):
            names.append(item.name)
        else:
            return None
    arg_name = node.agg_arg.name if isinstance(node.agg_arg, ColumnRef) else None
    excl = {node.pivot_col.lower(), (arg_name or "").lower()}
    return [n for n in names if n.lower() not in excl]


def _emit_pivot_relation(node: PivotRelation, dialect: str) -> str:
    """Emit the FROM-item SQL for ``<source> PIVOT (agg(arg) FOR col IN (…))``.

    T-SQL/Oracle re-spell it natively (Oracle needs ``'v' AS v`` IN values so the
    output columns are named like T-SQL's ``[v]``). PG/MySQL have no PIVOT, so it
    becomes a conditional-aggregation derived table — a warned carrier when the
    source's grouping columns are not determinable. The ``native_vals`` dict
    dispatches the native IN-value spelling.
    """
    src = node.source
    src_sql = _relation_source_sql(src, dialect)

    agg = node.agg_func.upper()
    arg = _emit_expression(node.agg_arg, dialect)
    pcol = _ident(node.pivot_col, False, dialect)

    native_vals = {
        "tsql": ", ".join(f"[{v}]" for v in node.values),
        "oracle": ", ".join(
            f"'{v}' AS {_ident(v, False, 'oracle')}" for v in node.values
        ),
    }
    if dialect in native_vals:
        tail = f" {_ident(node.alias, False, dialect)}" if node.alias else ""
        return (
            f"{src_sql} PIVOT ({agg}({arg}) FOR {pcol} "
            f"IN ({native_vals[dialect]})){tail}"
        )

    # PG / MySQL — conditional-aggregation rewrite in a derived table.
    group_cols = _pivot_group_columns(src, node)
    if group_cols is None:
        return (
            f"{src_sql} /* UNIQUE: PIVOT has no {dialect} equivalent and the "
            "source columns are not visible to rewrite it as conditional "
            "aggregation — see docs/03-unsupported.md */"
        )
    projs = [_ident(gc, False, dialect) for gc in group_cols]
    for v in node.values:
        vlit = v.replace("'", "''")
        projs.append(
            f"{agg}(CASE WHEN {pcol} = '{vlit}' THEN {arg} END) "
            f"AS {_ident(v, False, dialect)}"
        )
    query = f"SELECT {', '.join(projs)} FROM {src_sql}"
    if group_cols:
        query += " GROUP BY " + ", ".join(
            _ident(gc, False, dialect) for gc in group_cols
        )
    return f"({query}) {_ident(node.alias or 'uq_pivot', False, dialect)}"


#: ``DELETE TOP (n)`` row-cap rendering per target — dict dispatch (preferred
#: over ``if dialect ==``). T-SQL keeps TOP; MySQL trails LIMIT; Oracle folds
#: ROWNUM into the predicate; PG selects n candidate rows by ctid. All cap the
#: delete to n arbitrary matching rows — faithful to TOP's unordered semantics.
#: ``t`` = target SQL, ``w`` = WHERE text (or None), ``n`` = cap.
_DELETE_CAP: dict[str, Callable[[str, str | None, int], str]] = {
    "tsql": lambda t, w, n: f"DELETE TOP ({n}) FROM {t}"
    + (f"\nWHERE {w}" if w else ""),
    "mysql": lambda t, w, n: f"DELETE FROM {t}"
    + (f"\nWHERE {w}" if w else "")
    + f"\nLIMIT {n}",
    "oracle": lambda t, w, n: f"DELETE FROM {t}\nWHERE "
    + (f"{w} AND ROWNUM <= {n}" if w else f"ROWNUM <= {n}"),
    "postgresql": lambda t, w, n: f"DELETE FROM {t}\nWHERE ctid IN "
    + f"(SELECT ctid FROM {t}"
    + (f" WHERE {w}" if w else "")
    + f" LIMIT {n})",
}


def _emit_delete(node: DeleteStatement, dialect: str) -> str:
    """Emit a DELETE statement."""
    table = _emit_table_ref(node.table, dialect)
    if node.using:
        # PG's DELETE … USING (wave 196). PG keeps it; T-SQL/MySQL spell
        # the multi-table delete; Oracle (no multi-table form) gets the
        # correlated-EXISTS rewrite, exact when WHERE is the join
        # condition (the target's columns stay visible inside).
        sources = ", ".join(_emit_table_ref(u, dialect) for u in node.using)
        where = _emit_expression(node.where, dialect) if node.where else "1 = 1"
        if dialect == "postgresql":
            return f"DELETE FROM {table}\nUSING {sources}\nWHERE {where}"
        if dialect in ("tsql", "mysql"):
            target = node.table.alias or node.table.name
            return f"DELETE {target} FROM {table}, {sources}\nWHERE {where}"
        return (
            f"DELETE FROM {table}\nWHERE EXISTS (SELECT 1 FROM {sources} "
            f"WHERE {where})"
        )
    # ``DELETE TOP (n)`` row cap — rendered per target by ``_DELETE_CAP``.
    cap = (
        _plain_int_value(node.limit.limit) if node.limit and node.limit.limit else None
    )
    if cap is not None:
        where_sql = _emit_condition(node.where, dialect) if node.where else None
        return _DELETE_CAP[dialect](table, where_sql, cap)

    if dialect == "tsql" and node.table.alias:
        # T-SQL spells an aliased delete ``DELETE alias FROM t alias``
        # (``DELETE FROM t alias`` is a syntax error — wave 140).
        result = f"DELETE {node.table.alias} FROM {table}"
    else:
        result = f"DELETE FROM {table}"

    if node.where:
        result += f"\nWHERE {_emit_condition(node.where, dialect)}"

    return result


from unique.core.converter.emit import (  # noqa: E402
    _emit_condition,
    _emit_expression,
    _emit_select,
    _emit_table_ref,
    _ident,
    _plain_int_value,
    emit_node,
)
