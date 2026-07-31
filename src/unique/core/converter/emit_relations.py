"""Relation-shaped FROM items and DELETE emission (B17 step-4 seam of emit.py).

PIVOT/UNPIVOT relations and the DELETE statement family were carved out of
``emit.py`` when the 2026-07-30 challenge fixes (PIVOT modeling, DELETE caps,
multi-table DELETE) pushed it past its size ratchet. Same contract as every
seam: this module defines its own names first, then imports the ``emit.py``
helpers it needs at its tail (see the emit.py docstring for why the mutual
recursion is safe), and ``emit.py`` re-exports it via ``import *``.

``_emit_table_ref``/``_emit_tablesample`` (table-reference and TABLESAMPLE
emission — also relation-shaped FROM items) moved here for the same reason
(B36b follow-up, 2026-07-31): ``emit.py``/``emit_ddl.py``'s tails import
``_emit_table_ref`` back lazily (inside the functions that call it, not at
module load), since this module's own tail needs ``_emit_expression`` from
``emit_expr.py`` — a genuine two-way dependency that a load-time import
cannot resolve, only a call-time one.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from unique.core.ast_nodes import (
    Alias,
    ASTNode,
    CastExpression,
    ColumnRef,
    DeleteStatement,
    FunctionCall,
    Literal,
    PivotRelation,
    RawSQL,
    SubqueryExpression,
    TableRef,
    UnpivotRelation,
    UpdateStatement,
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
    "_UPDATE_CAP",
    "_emit_update",
    "_emit_capped_update",
    "_is_numeric_series",
    "_emit_table_ref",
    "_emit_tablesample",
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
            f"{src_sql} /* UNIQUE-1149: UNPIVOT has no {dialect} equivalent and the "
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
            f"{src_sql} /* UNIQUE-1150: PIVOT has no {dialect} equivalent and the "
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


#: Row-capped DELETE rendering per target — dict dispatch (preferred over
#: ``if dialect ==``). ``t`` = target SQL, ``w`` = WHERE text (or None), ``n`` =
#: cap, ``o`` = ORDER BY column text (or None for an UNORDERED cap).
#:
#: - **Unordered** (``o is None``, e.g. T-SQL ``DELETE TOP (n)``): cap to n
#:   ARBITRARY matching rows. T-SQL keeps TOP; MySQL trails LIMIT; Oracle folds
#:   ROWNUM into the predicate; PG selects n candidate rows by ctid.
#: - **Ordered** (``o`` given, MySQL ``… ORDER BY … LIMIT n``): the first n
#:   rows BY THAT ORDER — deterministic. Most engines can't ORDER a DELETE, so
#:   each uses a keyed subquery: MySQL keeps native ORDER BY+LIMIT; T-SQL deletes
#:   through a ``TOP (n) … ORDER BY`` CTE; PG orders the ctid subquery; Oracle
#:   caps a rowid subquery with ROWNUM applied AFTER the ordering.
_DELETE_CAP: dict[str, Callable[[str, str | None, int, str | None], str]] = {
    "tsql": lambda t, w, n, o: (
        f"WITH uq_del AS (\nSELECT TOP ({n}) * FROM {t}"
        + (f" WHERE {w}" if w else "")
        + f" ORDER BY {o}\n)\nDELETE FROM uq_del"
        if o
        else f"DELETE TOP ({n}) FROM {t}" + (f"\nWHERE {w}" if w else "")
    ),
    "mysql": lambda t, w, n, o: f"DELETE FROM {t}"
    + (f"\nWHERE {w}" if w else "")
    + (f"\nORDER BY {o}" if o else "")
    + f"\nLIMIT {n}",
    "oracle": lambda t, w, n, o: (
        f"DELETE FROM {t}\nWHERE rowid IN (SELECT rid FROM "
        f"(SELECT rowid AS rid FROM {t}"
        + (f" WHERE {w}" if w else "")
        + f" ORDER BY {o}) WHERE ROWNUM <= {n})"
        if o
        else f"DELETE FROM {t}\nWHERE "
        + (f"{w} AND ROWNUM <= {n}" if w else f"ROWNUM <= {n}")
    ),
    "postgresql": lambda t, w, n, o: f"DELETE FROM {t}\nWHERE ctid IN "
    + f"(SELECT ctid FROM {t}"
    + (f" WHERE {w}" if w else "")
    + (f" ORDER BY {o}" if o else "")
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
    # Row-capped DELETE (``TOP (n)`` / ``ORDER BY … LIMIT n``) — rendered per
    # target by ``_DELETE_CAP``. An ORDER BY only picks WHICH rows when a cap is
    # present, so it is emitted only alongside the limit.
    cap = (
        _plain_int_value(node.limit.limit) if node.limit and node.limit.limit else None
    )
    if cap is not None:
        where_sql = _emit_condition(node.where, dialect) if node.where else None
        order_sql = (
            ", ".join(_emit_order_item(o, dialect) for o in node.order_by)
            if node.order_by
            else None
        )
        return _DELETE_CAP[dialect](table, where_sql, cap, order_sql)

    if dialect == "tsql" and node.table.alias:
        # T-SQL spells an aliased delete ``DELETE alias FROM t alias``
        # (``DELETE FROM t alias`` is a syntax error — wave 140).
        result = f"DELETE {node.table.alias} FROM {table}"
    else:
        result = f"DELETE FROM {table}"

    if node.where:
        result += f"\nWHERE {_emit_condition(node.where, dialect)}"

    return result


#: Row-capped UPDATE rendering per target — dict dispatch (twin of
#: ``_DELETE_CAP``). ``t`` = target SQL, ``s`` = SET-assignment text, ``w`` =
#: WHERE text (or None), ``n`` = cap, ``o`` = ORDER BY text (or None for an
#: unordered cap). Only MySQL can order+limit an UPDATE directly; the others cap
#: through a keyed subquery: T-SQL updates an updatable ``SELECT TOP (n) …`` CTE
#: (sqlglot cannot parse the bare ``UPDATE TOP (n)`` spelling, so the CTE form is
#: used for the unordered cap too); PG updates rows chosen by a ctid subquery;
#: Oracle by a rowid subquery with ROWNUM applied AFTER the ordering.
_UPDATE_CAP: dict[str, Callable[[str, str, str | None, int, str | None], str]] = {
    "tsql": lambda t, s, w, n, o: (
        f"WITH uq_upd AS (\nSELECT TOP ({n}) * FROM {t}"
        + (f" WHERE {w}" if w else "")
        + (f" ORDER BY {o}" if o else "")
        + f"\n)\nUPDATE uq_upd\nSET {s}"
    ),
    "mysql": lambda t, s, w, n, o: f"UPDATE {t}\nSET {s}"
    + (f"\nWHERE {w}" if w else "")
    + (f"\nORDER BY {o}" if o else "")
    + f"\nLIMIT {n}",
    "oracle": lambda t, s, w, n, o: (
        f"UPDATE {t}\nSET {s}\nWHERE rowid IN (SELECT rid FROM "
        f"(SELECT rowid AS rid FROM {t}"
        + (f" WHERE {w}" if w else "")
        + f" ORDER BY {o}) WHERE ROWNUM <= {n})"
        if o
        else f"UPDATE {t}\nSET {s}\nWHERE "
        + (f"{w} AND ROWNUM <= {n}" if w else f"ROWNUM <= {n}")
    ),
    "postgresql": lambda t, s, w, n, o: f"UPDATE {t}\nSET {s}\nWHERE ctid IN "
    + f"(SELECT ctid FROM {t}"
    + (f" WHERE {w}" if w else "")
    + (f" ORDER BY {o}" if o else "")
    + f" LIMIT {n})",
}


def _emit_capped_update(
    node: UpdateStatement, dialect: str, table: str, sets: str, cap: int
) -> str:
    """Render a MySQL ``UPDATE … [ORDER BY …] LIMIT n`` row cap per target."""
    where_sql = _emit_condition(node.where, dialect) if node.where else None
    order_sql = (
        ", ".join(_emit_order_item(o, dialect) for o in node.order_by)
        if node.order_by
        else None
    )
    return _UPDATE_CAP[dialect](table, sets, where_sql, cap, order_sql)


def _emit_update(node: UpdateStatement, dialect: str) -> str:
    """Emit an UPDATE statement.

    A cross-table update (``from_clause``/``joins`` present) is rendered in each
    engine's idiomatic form. T-SQL keeps ``UPDATE t SET ... FROM ... JOIN``;
    PostgreSQL uses ``UPDATE t SET ... FROM ... WHERE <join preds>``; MySQL puts
    the joins before SET (``UPDATE t JOIN s ON ... SET ...``); Oracle, which has
    no ``UPDATE ... FROM``, uses correlated subqueries. A plain single-table
    update is unchanged.
    """
    if node.from_clause is not None or node.joins:
        return _emit_cross_table_update(node, dialect)

    table = _emit_table_ref(node.table, dialect)
    set_parts = []
    for col, val in node.assignments:
        if dialect == "mysql":
            val = _wrap_mysql_update_self_ref(val, node.table.name)
        val = _coerce_bit_literal(node.table, col, val, dialect)
        val = _coerce_date_literal(node.table, col, val, dialect)
        set_parts.append(
            f"{_ident_if_plain(col, dialect)} = {_emit_expression(val, dialect)}"
        )
    sets = ", ".join(set_parts)

    # MySQL ``UPDATE … [ORDER BY …] LIMIT n`` row cap — rendered per target via a
    # keyed subquery (twin of the DELETE cap). Dropping the cap updated ALL
    # matching rows; the ORDER BY only picks WHICH rows when a cap is present.
    cap = (
        _plain_int_value(node.limit.limit) if node.limit and node.limit.limit else None
    )
    if cap is not None:
        return _emit_capped_update(node, dialect, table, sets, cap)

    # T-SQL rejects an alias after the UPDATE target (``UPDATE t ep SET``,
    # error 102); its aliased spelling is ``UPDATE ep SET … FROM t ep``
    # (correlated subqueries keep resolving against the alias).
    alias = getattr(node.table, "alias", None)
    if dialect == "tsql" and alias:
        result = f"UPDATE {alias}\nSET {sets}\nFROM {table}"
        if node.where:
            result += f"\nWHERE {_emit_condition(node.where, dialect)}"
        return result

    result = f"UPDATE {table}\nSET {sets}"

    if node.where:
        result += f"\nWHERE {_emit_condition(node.where, dialect)}"

    return result


def _is_numeric_series(args: tuple[ASTNode, ...]) -> bool:
    """True when a generate_series' bounds are plain integers (not a date/
    timestamp range, whose arithmetic and step interval need a different
    rewrite). Only literal integer bounds are treated as the numeric form."""
    return all(
        isinstance(a, Literal)
        and isinstance(a.value, int)
        and not isinstance(a.value, bool)
        for a in args[:2]
    )


def _emit_table_ref(node: TableRef, dialect: str | None = None) -> str:
    """Emit a table reference.

    When ``dialect`` is one of the non-T-SQL engines, the T-SQL default schema
    ``dbo`` is dropped: it names no real schema on Oracle/PostgreSQL and would
    name a non-existent database on MySQL. Passing ``dialect=None`` keeps the
    reference verbatim (used where the schema must be preserved, e.g. a T-SQL
    OBJECT_ID guard).
    """
    if (
        isinstance(node.function, FunctionCall)
        and node.function.name.upper() == "GENERATE_SERIES"
        and len(node.function.args) in (2, 3)
        and dialect in ("oracle", "tsql")
        and SOURCE_DIALECT.get() == "postgresql"
        and _is_numeric_series(node.function.args)
    ):
        # PG ``FROM generate_series(start, stop[, step])`` as a relation. The
        # single value column is named after the correlation alias (PG lets the
        # table alias double as the column name); an explicit ``AS t(v[, n])``
        # renames it, and ``WITH ORDINALITY`` adds a 1-based row number.
        _gs = node.function.args
        _gstart = _emit_expression(_gs[0], dialect)
        _gstop = _emit_expression(_gs[1], dialect)
        _gstep = _emit_expression(_gs[2], dialect) if len(_gs) == 3 else "1"
        _talias = node.alias or "uq_gs"
        _vcol = node.column_aliases[0] if node.column_aliases else _talias
        _ord = (
            node.column_aliases[1]
            if node.ordinality and len(node.column_aliases) > 1
            else "ordinality"
        )
        # count = floor((stop-start)/step) + 1
        _cnt = (
            f"({_gstop}) - ({_gstart}) + 1"
            if _gstep == "1"
            else f"FLOOR((({_gstop}) - ({_gstart})) / ({_gstep})) + 1"
        )
        _mul = "" if _gstep == "1" else f" * ({_gstep})"
        if dialect == "oracle":
            _ord_sel = f", LEVEL AS {_ord}" if node.ordinality else ""
            _inner = (
                f"SELECT ({_gstart}) + (LEVEL - 1){_mul} AS {_vcol}{_ord_sel} FROM "
                f"DUAL CONNECT BY LEVEL <= {_cnt}"
            )
            return f"({_inner}) {_talias}"
        # T-SQL: a numbers source (sys.all_objects has plenty of rows for the
        # small ranges these series cover); ROW_NUMBER gives the 1-based index.
        _rn = "ROW_NUMBER() OVER (ORDER BY (SELECT NULL))"
        _ord_sel = f", {_rn} AS {_ord}" if node.ordinality else ""
        _inner = (
            f"SELECT TOP ({_cnt}) ({_gstart}) + ({_rn} - 1){_mul} AS {_vcol}{_ord_sel} "
            f"FROM sys.all_objects"
        )
        return f"({_inner}) {_talias}"
    if (
        isinstance(node.function, FunctionCall)
        and node.function.name.upper() == "GENERATE_SERIES"
        and len(node.function.args) == 3
        and dialect in ("oracle", "tsql")
        and SOURCE_DIALECT.get() == "postgresql"
        and isinstance(node.function.args[0], CastExpression)
        and node.function.args[0].target_type.name.upper() == "DATE"
        and isinstance(node.function.args[2], RawSQL)
    ):
        # PG date-range generate_series(date, date, INTERVAL 'n' DAY). Only a day
        # step is modelled (month/year intervals fall through to the degrade):
        # Oracle adds days to a DATE directly, T-SQL via DATEADD over a numbers
        # source. count = floor((stop - start) / step) + 1.
        # Accept both interval spellings sqlglot may emit: ``INTERVAL '1' DAY``
        # and ``INTERVAL '1 day'``; only a plain day step (no month/year) matches.
        _istep = node.function.args[2].sql
        _dm = re.search(r"(?i)INTERVAL\s+'?(\d+)", _istep)
        if (
            _dm
            and re.search(r"(?i)\bDAYS?\b", _istep)
            and not re.search(r"(?i)\b(MONTH|YEAR|HOUR|MINUTE|SECOND|WEEK)", _istep)
        ):
            _step = _dm.group(1)
            _dstart = _emit_expression(node.function.args[0], dialect)
            _dstop = _emit_expression(node.function.args[1], dialect)
            _dtal = node.alias or "uq_gs"
            _dvcol = node.column_aliases[0] if node.column_aliases else _dtal
            if dialect == "oracle":
                _dmul = "" if _step == "1" else f" * {_step}"
                _dcnt = (
                    f"({_dstop}) - ({_dstart}) + 1"
                    if _step == "1"
                    else f"FLOOR((({_dstop}) - ({_dstart})) / {_step}) + 1"
                )
                _dinner = (
                    f"SELECT ({_dstart}) + (LEVEL - 1){_dmul} AS {_dvcol} FROM DUAL "
                    f"CONNECT BY LEVEL <= {_dcnt}"
                )
                return f"({_dinner}) {_dtal}"
            _drn = "ROW_NUMBER() OVER (ORDER BY (SELECT NULL))"
            _dcnt = f"DATEDIFF(DAY, {_dstart}, {_dstop}) / {_step} + 1"
            _dinner = (
                f"SELECT TOP ({_dcnt}) DATEADD(DAY, ({_drn} - 1) * {_step}, {_dstart}) "
                f"AS {_dvcol} FROM sys.all_objects"
            )
            return f"({_dinner}) {_dtal}"
    if (
        isinstance(node.function, FunctionCall)
        and node.function.name.upper() == "GENERATE_SERIES"
        and len(node.function.args) == 2
        and dialect in ("oracle", "postgresql")
        and SOURCE_DIALECT.get() == "tsql"
        and not node.column_aliases
    ):
        # T-SQL's GENERATE_SERIES(start, stop) table function yields a column
        # named ``value``. PostgreSQL's generate_series names it after the
        # function, and Oracle has none — spell each so ``value`` resolves.
        _gs = node.function.args
        _gstart = _emit_expression(_gs[0], dialect)
        _gstop = _emit_expression(_gs[1], dialect)
        _gal = node.alias or "uq_gs"
        if dialect == "postgresql":
            return f"generate_series({_gstart}, {_gstop}) AS {_gal}(value)"
        return (
            f"(SELECT ({_gstart}) + LEVEL - 1 AS value FROM DUAL CONNECT BY LEVEL <= "
            f"({_gstop}) - ({_gstart}) + 1) {_gal}"
        )
    if node.function is not None:
        # A function IS the relation (``FROM fn(args) alias``); targets
        # without the construct degrade in the transformer, so this only
        # ever renders where it is (or is claimed to be) valid.
        result = _emit_expression(node.function, dialect or "")
        if dialect == "oracle":
            # Oracle spells a function relation ``TABLE(fn(args)) alias``.
            result = f"TABLE({result})"
        if node.ordinality:
            result += " WITH ORDINALITY"
        if node.column_aliases and node.alias:
            cols = ", ".join(node.column_aliases)
            return f"{result} AS {node.alias}({cols})"
        if node.alias:
            result += f" {node.alias}"
        return result

    parts = []
    if node.database:
        parts.append(node.database)
    schema = node.schema
    if dialect in ("oracle", "mysql", "postgresql") and schema == "dbo":
        schema = None
    # PostgreSQL's default schema plays the same role: off PG it is a
    # RESERVED word on T-SQL (error 156 near 'public') and a nonexistent
    # database/schema elsewhere.
    if (
        dialect in ("oracle", "mysql", "tsql")
        and schema == "public"
        and SOURCE_DIALECT.get() == "postgresql"
    ):
        schema = None
    if schema:
        parts.append(_ident(schema, node.schema_quoted, dialect))
    name = node.name
    # A temp table declared anywhere in the script is ``#name`` on T-SQL —
    # for EVERY reference, not only the creating statement (audit N2).
    if dialect == "tsql" and not name.startswith("#"):
        temp_tables = TEMP_TABLES.get()
        if temp_tables and name.lower() in temp_tables:
            name = f"#{name}"
    parts.append(_ident(name, node.quoted, dialect))
    result = ".".join(parts)

    if node.column_aliases and node.alias:
        # PG's column-renaming alias has no direct T-SQL spelling on a base
        # table; the derived-table rewrite is faithful. (PG keeps native;
        # MySQL/Oracle statements degrade whole in the transformer.)
        cols = ", ".join(node.column_aliases)
        if dialect == "tsql":
            return f"(SELECT * FROM {result}) AS {node.alias}({cols})"
        return f"{result} AS {node.alias}({cols})"

    # MySQL rejects an alias on the DUAL pseudo-table (error 1064); the alias is
    # only ever load-bearing for an Oracle hint, which is dropped anyway.
    if node.alias and not (dialect == "mysql" and node.name.upper() == "DUAL"):
        result += f" {node.alias}"

    if node.sample_method or node.sample_percent or node.sample_rows:
        result += _emit_tablesample(node, dialect)

    return result


def _emit_tablesample(node: TableRef, dialect: str | None) -> str:
    """Emit a TABLESAMPLE clause in the target's idiom.

    PostgreSQL/T-SQL keep a native TABLESAMPLE, Oracle uses SAMPLE(pct). MySQL
    has no row sampling, so it degrades to a documented carrier (a silent drop
    would return every row). Row-count sampling has no PG/Oracle spelling and is
    likewise carried.
    """
    pct, rows = node.sample_percent, node.sample_rows
    if dialect == "mysql":
        what = f"{pct} PERCENT" if pct else f"{rows} ROWS"
        return (
            f" /* UNIQUE-1034: TABLESAMPLE ({what}) has no MySQL equivalent — all rows "
            "returned (docs/03-unsupported.md) */"
        )
    if dialect == "tsql":
        return f" TABLESAMPLE ({pct} PERCENT)" if pct else f" TABLESAMPLE ({rows} ROWS)"
    if dialect == "oracle":
        if pct:
            return f" SAMPLE ({pct})"
        return (
            " /* UNIQUE-1035: TABLESAMPLE by row count has no Oracle SAMPLE form "
            "(docs/03-unsupported.md) */"
        )
    # postgresql
    if pct:
        return f" TABLESAMPLE {node.sample_method or 'SYSTEM'} ({pct})"
    return (
        " /* UNIQUE-1036: TABLESAMPLE by row count has no PostgreSQL equivalent "
        "(docs/03-unsupported.md) */"
    )


from unique.core.converter.emit import (  # noqa: E402
    _emit_condition,
    _emit_cross_table_update,
    _emit_expression,
    _emit_order_item,
    _emit_select,
    _ident,
    _ident_if_plain,
    _plain_int_value,
    _wrap_mysql_update_self_ref,
    emit_node,
)
from unique.core.converter.harvest import (  # noqa: E402
    _coerce_bit_literal,
    _coerce_date_literal,
)
