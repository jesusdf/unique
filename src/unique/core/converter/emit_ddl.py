# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterator
from typing import Any

from unique.core.ast_nodes import (
    ASTNode,
    ColumnDefinition,
    ColumnRef,
    CreateTableStatement,
    CreateViewStatement,
    DropStatement,
)

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter.harvest import (  # noqa: F401
    _coerce_bit_literal,
    _coerce_date_literal,
    _oracle_date_literal,
    wrap_oracle_date_arg,
)

# NOTE: moved verbatim from emit.py (audit doc 04 F4 split). The emit.py
# helpers and sibling emitters this module calls are imported explicitly at
# the module tail (after the defs) — see emit.py's module docstring for why the
# cross-family imports live at the tail rather than the top.

__all__ = [
    "_type_gap_map",
    "_emit_enum_type",
    "_walk_nodes",
    "_substitute_column_refs",
    "_emit_create_table",
    "_emit_create_view",
    "_emit_drop",
]


#: Faithful/closest column type for Oracle TIMESTAMP WITH LOCAL TIME ZONE
#: (sqlglot's TIMESTAMPLTZ) per target. No engine spells the type
#: ``TIMESTAMPLTZ``; sqlglot's lenient readers accept the raw token but every
#: real engine rejects it, so shipping it is a silent-invalid defect.
# Engines with no ``ON DELETE SET DEFAULT`` FK action (ORA-03001 on Oracle);
# the action is dropped + warned there. PG/MySQL/T-SQL all support it.
_NO_SET_DEFAULT_FK = frozenset({"oracle"})
_FK_SET_DEFAULT_RE = re.compile(r"(?i)\s*\bON\s+DELETE\s+SET\s+DEFAULT\b")

_LOCAL_TZ_TYPE: dict[str, str] = {
    "postgresql": "TIMESTAMPTZ",
    "tsql": "DATETIMEOFFSET",
    "mysql": "TIMESTAMP",
    # Oracle keeps its own native spelling — faithful, no loss, no note.
    "oracle": "TIMESTAMP WITH LOCAL TIME ZONE",
}

#: Trailing ``-- UNIQUE:`` carrier (auto-warned by the no-silent-loss scan) for
#: the WITH LOCAL TIME ZONE mapping. PostgreSQL timestamptz has the identical
#: session-tz display behaviour as Oracle LTZ (verified live: a value shows
#: 12:00 in a UTC session and 07:00 in a New York session, same instant), so
#: its note documents that dependence rather than a loss. T-SQL DATETIMEOFFSET
#: keeps a fixed stored offset and MySQL TIMESTAMP normalizes to UTC — the
#: instant is kept but the session-tz display is not reproduced. Oracle has no
#: entry: its native spelling loses nothing. ``{name}`` = the column name.
_LOCAL_TZ_NOTE: dict[str, str] = {
    "postgresql": (
        "-- UNIQUE-1039: Oracle WITH LOCAL TIME ZONE and PostgreSQL timestamptz "
        "both display column {name} in the session time zone (same instant, "
        "session-dependent wall clock) (docs/03-unsupported.md)"
    ),
    "tsql": (
        "-- UNIQUE-1040: tsql has no session-local timestamp type — column {name} "
        "WITH LOCAL TIME ZONE maps to DATETIMEOFFSET; the value's instant is "
        "kept but the session-time-zone display is not reproduced "
        "(docs/03-unsupported.md)"
    ),
    "mysql": (
        "-- UNIQUE-1041: mysql has no session-local timestamp type — column {name} "
        "WITH LOCAL TIME ZONE maps to TIMESTAMP; the value's instant is kept "
        "but the session-time-zone display is not reproduced "
        "(docs/03-unsupported.md)"
    ),
}


def _local_tz_gap(
    col: ColumnDefinition, dtype: str, dialect: str
) -> tuple[str, tuple[int, ...] | None, str]:
    """Closest-type mapping for Oracle TIMESTAMP WITH LOCAL TIME ZONE."""
    mapped = _LOCAL_TZ_TYPE.get(dialect)
    if mapped is None:
        return dtype, None, ""  # unknown target — leave the name alone
    note = _LOCAL_TZ_NOTE.get(dialect)
    return mapped, None, note.format(name=col.name) if note else ""


def _type_gap_map(
    col: ColumnDefinition, dtype: str, dialect: str
) -> tuple[str, tuple[int, ...] | None, str]:
    """Closest-type mapping for column types the target genuinely lacks.

    Returns ``(dtype, params_override, trailing_note)``. ``params_override``
    replaces the column's type parameters when the mapped spelling consumed or
    clamped them (``None`` = leave them alone). A non-empty note is a
    ``-- UNIQUE:`` trailing carrier — auto-warned by the no-silent-loss scan —
    so the loss is documented, never silent (docs/03-unsupported.md §3.19).
    """
    tn = col.data_type.name.upper()
    params = col.data_type.params
    if tn == "TIMESTAMPLTZ":
        return _local_tz_gap(col, dtype, dialect)
    if dialect == "oracle":
        # Bare INTERVAL DAY TO SECOND on purpose: the validity gate's sqlglot
        # parse rejects the (perfectly valid) precision forms DAY(0)/SECOND(3);
        # Oracle's defaults (DAY(2), SECOND(6)) cover both uses.
        if tn in ("TIME", "TIMETZ"):
            tz = "; the time-zone offset is dropped" if tn == "TIMETZ" else ""
            return (
                "INTERVAL DAY TO SECOND",
                (),
                f"-- UNIQUE-1042: Oracle has no TIME type — column {col.name} "
                f"stores the time of day as INTERVAL DAY TO SECOND{tz} "
                "(docs/03-unsupported.md)",
            )
        if tn == "INTERVAL" and not params:
            return (
                "INTERVAL DAY TO SECOND",
                (),
                f"-- UNIQUE-1043: PostgreSQL INTERVAL mixes year-month and "
                f"day-second fields; column {col.name} is mapped to INTERVAL "
                "DAY TO SECOND — year-month values need a separate "
                "INTERVAL YEAR TO MONTH column (docs/03-unsupported.md)",
            )
    if dialect in ("tsql", "mysql") and tn.startswith("INTERVAL"):
        # T-SQL has no interval type at all; MySQL's INTERVAL is only an
        # arithmetic qualifier, not a column type. Keep the value as text.
        return (
            "VARCHAR",
            (30,),
            f"-- UNIQUE-1044: {dialect} has no INTERVAL column type — column "
            f"{col.name} keeps the interval as text (docs/03-unsupported.md)",
        )
    if (
        dialect == "mysql"
        and tn in ("DATETIME", "DATETIME2", "TIMESTAMP", "TIME")
        and params
        and int(params[0]) > 6
    ):
        return (
            dtype,
            (6,),
            f"-- UNIQUE-1045: MySQL fractional-seconds precision caps at 6 — "
            f"column {col.name} precision {params[0]} clamped to 6 "
            "(docs/03-unsupported.md)",
        )
    # A multi-bit MySQL BIT(n) is a 64-bit value, not a boolean. The IR may
    # carry the name pre-mapped (BOOLEAN on PG, NUMBER(1) on Oracle), so match
    # those spellings too — only a BIT(n) source produces them with a width.
    if tn in ("BIT", "BOOLEAN", "NUMBER(1)") and params and int(params[0]) > 1:
        if dialect == "postgresql":
            return ("BIT", None, "")  # native bit string, width kept
        if dialect in ("oracle", "tsql"):
            mapped = "NUMBER(20)" if dialect == "oracle" else "NUMERIC(20)"
            return (
                mapped,
                (),
                f"-- UNIQUE-1046: {dialect} has no bit-string type — column "
                f"{col.name} BIT({params[0]}) stores its numeric value as "
                f"{mapped} (docs/03-unsupported.md)",
            )
    return dtype, None, ""


def _emit_enum_type(col: ColumnDefinition, dialect: str) -> tuple[str, str, str]:
    """Render a MySQL ENUM/SET column type for *dialect*.

    Returns ``(type_sql, inline_check_sql, trailing_note)``. MySQL keeps the
    native type. Elsewhere ENUM becomes VARCHAR sized to the longest value
    plus an inline CHECK carrying the value-list semantics; SET (an unordered
    combination of values) has no CHECK equivalent, so it becomes a VARCHAR
    wide enough for all values with a documented carrier note.
    """
    values = col.data_type.values
    quoted_values = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    kind = col.data_type.name.upper()
    if dialect == "mysql":
        return f"{kind}({quoted_values})", "", ""
    varchar = _portable_type_name("VARCHAR", dialect)
    col_name = _ident(col.name, col.quoted, dialect)
    if kind == "ENUM":
        max_len = max(len(v) for v in values)
        return (
            f"{varchar}({max_len})",
            f" CHECK ({col_name} IN ({quoted_values}))",
            "",
        )
    total_len = sum(len(v) for v in values) + max(len(values) - 1, 0)
    note = (
        f"-- UNIQUE-1047: MySQL SET type on {col_name} has no {dialect} "
        f"equivalent; stored as {varchar}({total_len}). "
        f"Allowed members: {quoted_values}"
    )
    return f"{varchar}({total_len})", "", note


def _walk_nodes(node: ASTNode) -> Iterator[ASTNode]:
    """Yield *node* and every ASTNode reachable through its dataclass fields."""
    yield node
    if not dataclasses.is_dataclass(node):
        return
    for f in dataclasses.fields(node):
        v = getattr(node, f.name)
        if isinstance(v, ASTNode):
            yield from _walk_nodes(v)
        elif isinstance(v, tuple):
            for x in v:
                if isinstance(x, ASTNode):
                    yield from _walk_nodes(x)


def _substitute_column_refs(expr: ASTNode, mapping: dict[str, ASTNode]) -> ASTNode:
    """Replace ColumnRef nodes named in *mapping* with their expressions
    (used to inline chained generated-column references)."""
    if isinstance(expr, ColumnRef) and expr.name.lower() in mapping:
        return mapping[expr.name.lower()]
    if not dataclasses.is_dataclass(expr):
        return expr
    changes: dict[str, Any] = {}
    for f in dataclasses.fields(expr):
        v = getattr(expr, f.name)
        if isinstance(v, ASTNode):
            nv = _substitute_column_refs(v, mapping)
            if nv is not v:
                changes[f.name] = nv
        elif isinstance(v, tuple) and any(isinstance(x, ASTNode) for x in v):
            nt = tuple(
                _substitute_column_refs(x, mapping) if isinstance(x, ASTNode) else x
                for x in v
            )
            if nt != v:
                changes[f.name] = nt
    return dataclasses.replace(expr, **changes) if changes else expr


def _emit_create_table(node: CreateTableStatement, dialect: str) -> str:
    """Emit a CREATE TABLE statement."""
    # The T-SQL default schema "dbo" has no meaning in Oracle, MySQL or
    # PostgreSQL; _emit_table_ref drops it for those dialects so the table lands
    # in the current user's schema (Oracle), the connected database (MySQL), or
    # the default "public" schema (PostgreSQL).
    table = _emit_table_ref(node.table, dialect)
    temp = ""
    if node.temporary:
        # PG/MySQL: TEMPORARY. Oracle's closest is a GLOBAL TEMPORARY
        # table (persistent definition, per-session rows — the table-
        # variable arc's precedent). T-SQL spells temp-ness as a #name;
        # the transformer warns about the dropped scope there.
        temp = {"oracle": "GLOBAL TEMPORARY ", "tsql": ""}.get(dialect, "TEMPORARY ")
    # T-SQL has no "CREATE TABLE IF NOT EXISTS"; the idiomatic equivalent is an
    # existence guard against the catalog. Other engines support the clause
    # inline. Oracle (< 23c) also lacks it, but sqlglot/most targets accept it;
    # we keep the inline form there and special-case only T-SQL.
    inline_exists = ""
    tsql_guard = ""
    if node.if_not_exists:
        if dialect == "tsql":
            tsql_guard = (
                f"IF OBJECT_ID(N'{_object_id_name(node.table)}', N'U') " "IS NULL\n"
            )
        else:
            inline_exists = "IF NOT EXISTS "
    exists = inline_exists

    if node.like_source:
        # Structure clone. PG spells it natively; T-SQL/Oracle use an
        # empty CTAS (column structure only — indexes/keys don't clone).
        if dialect == "postgresql":
            return (
                f"{tsql_guard}CREATE {temp}TABLE {exists}{table} "
                f"(LIKE {node.like_source} INCLUDING ALL)"
            )
        if dialect == "tsql":
            return (
                f"SELECT *\nINTO {table}\nFROM {node.like_source}\n"
                "WHERE 1 = 0\n"
                "-- UNIQUE-1048: LIKE clone copies column structure only here; "
                "the source's indexes/keys are not cloned"
            )
        if dialect == "oracle":
            return (
                f"CREATE {temp}TABLE {exists}{table} AS\n"
                f"SELECT *\nFROM {node.like_source}\nWHERE 1 = 0\n"
                "-- UNIQUE-1048: LIKE clone copies column structure only here; "
                "the source's indexes/keys are not cloned"
            )
        return f"CREATE {temp}TABLE {exists}{table} LIKE {node.like_source}"

    if node.as_select:
        if dialect == "tsql":
            # T-SQL has no CREATE TABLE AS; the faithful idiom is
            # SELECT … INTO <table> FROM … (a temp name keeps its #).
            return _emit_select(node.as_select, dialect, into=table)
        select = _emit_select(node.as_select, dialect)
        return f"{tsql_guard}CREATE {temp}TABLE {exists}{table} AS\n{select}"

    if node.columns or node.table_constraints:
        # A generated column referencing ANOTHER generated column is rejected
        # by PG and T-SQL (error 1759): inline the referenced expression
        # (transitively, in declaration order).
        if dialect in ("postgresql", "tsql"):
            _gen_map: dict[str, ASTNode] = {}
            _new_cols = []
            for _gc in node.columns:
                if _gc.generated_expr is not None:
                    _inlined = _substitute_column_refs(_gc.generated_expr, _gen_map)
                    _gen_map[_gc.name.lower()] = _inlined
                    _gc = dataclasses.replace(_gc, generated_expr=_inlined)
                _new_cols.append(_gc)
            node = dataclasses.replace(node, columns=tuple(_new_cols))
        # T-SQL: a computed column used by a CHECK constraint (error 1764) or
        # carrying UNIQUE/PK must be PERSISTED — collect the referenced names.
        _persist_names: set[str] = set()
        if dialect == "tsql":
            for _tc in node.table_constraints:
                for _gc in node.columns:
                    if _gc.generated_expr is not None and re.search(
                        rf"(?i)\b{re.escape(_gc.name)}\b", _tc.sql
                    ):
                        _persist_names.add(_gc.name.lower())
        col_defs = []
        set_type_notes: list[str] = []
        column_comments: list[tuple[str, str]] = []
        on_update_notes: list[str] = []
        collate_notes: list[str] = []
        invisible_notes: list[str] = []
        for col in node.columns:
            check = ""
            if col.data_type.name.upper() in ("ENUM", "SET") and col.data_type.values:
                # MySQL keeps the native type; everyone else gets VARCHAR
                # sized to the values, plus a CHECK for ENUM semantics.
                dtype, check, note = _emit_enum_type(col, dialect)
                if note:
                    set_type_notes.append(note)
            else:
                dtype = _portable_type_name(col.data_type.name, dialect)
                # Oracle's BINARY_DOUBLE takes no precision, and FLOAT no
                # scale; MySQL's parameterized DOUBLE(p,s)/FLOAT(p,s) is
                # fixed-point semantics — NUMBER(p,s) is the faithful
                # spelling.
                _tn = col.data_type.name.upper()
                if (
                    dialect == "oracle"
                    and col.data_type.params
                    and (
                        _tn in ("DOUBLE", "UDOUBLE")
                        or (
                            _tn in ("FLOAT", "UFLOAT")
                            and len(col.data_type.params) == 2
                        )
                    )
                ):
                    dtype = "NUMBER"
                # PostgreSQL/T-SQL FLOAT takes at most ONE argument (a precision
                # in bits, not a scale); MySQL's FLOAT(M,D) display form maps to
                # the same 4-byte REAL on both.
                if (
                    dialect in ("postgresql", "tsql")
                    and _tn in ("FLOAT", "UFLOAT")
                    and len(col.data_type.params) == 2
                ):
                    dtype = "REAL"
                # T-SQL DATETIME takes no fractional-seconds precision (error
                # 2716: "Cannot specify a column width on data type datetime");
                # a MySQL DATETIME(n) needs DATETIME2(n) to keep the precision.
                if dialect == "tsql" and _tn == "DATETIME" and col.data_type.params:
                    dtype = "DATETIME2"
                # A MySQL JSON column: PostgreSQL has native JSON, but Oracle's
                # JSON type has usage restrictions (ORA-43853) so JSON text lives
                # in a CLOB, and T-SQL has no JSON type (pre-2025) so it uses
                # NVARCHAR(MAX) — the canonical JSON storage on each.
                if _tn in ("JSON", "JSONB"):
                    if dialect == "oracle":
                        dtype = "CLOB"
                    elif dialect == "tsql":
                        dtype = "NVARCHAR(MAX)"
                    elif dialect == "mysql":
                        dtype = "JSON"
                    elif _tn == "JSONB":
                        dtype = "JSONB"
                # Types the target genuinely lacks (TIME/INTERVAL on Oracle,
                # INTERVAL on T-SQL/MySQL, multi-bit BIT(n), >6-digit
                # fractional seconds on MySQL): closest type + warned note.
                dtype, _gap_params, _gap_note = _type_gap_map(col, dtype, dialect)
                if _gap_note:
                    set_type_notes.append(_gap_note)
                if _gap_params is not None:
                    col = dataclasses.replace(
                        col,
                        data_type=dataclasses.replace(
                            col.data_type, params=_gap_params
                        ),
                    )
                # If the mapped name already carries a length (e.g. CHAR(36)),
                # don't append the caller's params on top of it. PostgreSQL and
                # T-SQL integer types take no parameters at all — a MySQL display
                # width (TINYINT(1), INT(11)) would be a syntax error.
                skip_params = (
                    (
                        dialect in ("postgresql", "tsql")
                        and dtype.upper()
                        in ("SMALLINT", "INT", "INTEGER", "BIGINT", "TINYINT")
                    )
                    or (
                        # PostgreSQL BYTEA / BLOB take no length (a MySQL
                        # VARBINARY(64) maps to BYTEA, not BYTEA(64)); and
                        # DOUBLE PRECISION takes no display width (MySQL's
                        # DOUBLE(11,0) is a display hint, not a precision).
                        dialect == "postgresql"
                        and dtype.upper()
                        in ("BYTEA", "BLOB", "DOUBLE PRECISION", "REAL")
                    )
                    or (
                        # Oracle LOB types take no length (BLOB/CLOB, not BLOB(255)).
                        dialect == "oracle"
                        and dtype.upper() in ("BLOB", "CLOB", "NCLOB")
                    )
                    or (
                        # T-SQL REAL takes no width (a MySQL FLOAT(M,D) mapped to
                        # REAL must not keep its display scale — error 2724). BIT
                        # is a single bit (error 2716 on a width): a MySQL BIT(M)
                        # maps to BIT, as it does to Oracle NUMBER(1) / PG BOOLEAN.
                        dialect == "tsql"
                        and dtype.upper() in ("REAL", "BIT")
                    )
                )
                params = col.data_type.params
                if (
                    dialect != "mysql"
                    and params == (0,)
                    and _tn in ("CHAR", "VARCHAR", "BINARY", "VARBINARY", "NCHAR")
                ):
                    # Zero-length character columns are MySQL-only.
                    params = (1,)
                if dtype.upper() in ("BOOLEAN", "BOOL"):
                    # BOOLEAN never takes parameters (a mapped BIT(n)
                    # carried its width along — wave 131).
                    params = ()
                if params and "(" not in dtype and not skip_params:
                    _params_sql = ", ".join(str(p) for p in params)
                    # Oracle's TIMESTAMP [WITH [LOCAL] TIME ZONE]: the precision
                    # belongs on TIMESTAMP, not after the whole multi-word type
                    # (``TIMESTAMP WITH TIME ZONE(3)`` does not parse).
                    _wtz = re.match(r"(?i)^(TIMESTAMP)\s+(WITH\b.*)$", dtype)
                    if _wtz:
                        dtype = f"{_wtz.group(1)}({_params_sql}) {_wtz.group(2)}"
                    else:
                        dtype += f"({_params_sql})"
                # A character type with no length is invalid DDL in most engines
                # (MySQL/Oracle reject it; PostgreSQL treats bare VARCHAR as
                # unlimited but that is not what was meant). It originates from a
                # T-SQL VARCHAR(MAX)/NVARCHAR(MAX) whose MAX marker is dropped
                # during IR conversion (the non-numeric param is not preserved).
                # Map the bare character type to the dialect's large-text type.
                if not col.data_type.params:
                    _base = dtype.upper().split("(")[0]
                    _bigtext = _BARE_CHAR_BIGTEXT.get(dialect, {}).get(_base)
                    if _bigtext:
                        dtype = _bigtext
                    # A binary type with no length (a SQLite BLOB affinity) is
                    # invalid where the target needs one (MySQL VARBINARY, Oracle
                    # RAW): a length-less binary is a BLOB. ``"(" not in dtype``
                    # guards types whose mapped name already has a length
                    # (UNIQUEIDENTIFIER -> RAW(16)).
                    elif (
                        _base in ("VARBINARY", "BINARY", "RAW")
                        and "(" not in dtype
                        and dialect in ("mysql", "oracle")
                    ):
                        dtype = "BLOB"
            pk = " PRIMARY KEY" if col.primary_key else ""
            # DEFERRABLE INITIALLY DEFERRED is valid on PG and Oracle only;
            # T-SQL/MySQL constraints are never deferrable, so drop it there.
            if (
                col.primary_key
                and col.deferrable
                and dialect in ("postgresql", "oracle")
            ):
                pk += f" {col.deferrable}"
            unique = " UNIQUE" if col.unique else ""
            default = ""
            if col.default is not None:
                default_sql = _emit_expression(col.default, dialect)
                if dialect == "oracle":
                    default_sql = re.sub(
                        r"(?i)\bNEWSEQUENTIALID\s*\(\s*\)", "SYS_GUID()", default_sql
                    )
                    default_sql = re.sub(
                        r"(?i)\bNEWID\s*\(\s*\)", "SYS_GUID()", default_sql
                    )
                elif dialect == "mysql":
                    # MySQL has no sequential-GUID generator; UUID() is the
                    # closest equivalent. A function default requires the
                    # parenthesized "(expr)" form (MySQL 8.0.13+).
                    default_sql = re.sub(
                        r"(?i)\b(?:NEWSEQUENTIALID|NEWID)\s*\(\s*\)",
                        "(UUID())",
                        default_sql,
                    )
                elif dialect == "postgresql":
                    # PostgreSQL: gen_random_uuid() (pgcrypto / built-in 13+).
                    default_sql = re.sub(
                        r"(?i)\b(?:NEWSEQUENTIALID|NEWID)\s*\(\s*\)",
                        "gen_random_uuid()",
                        default_sql,
                    )
                if dialect in ("postgresql", "oracle"):
                    # Both reject the parenthesized CURRENT_TIMESTAMP() form
                    # in DDL defaults (audit 2026-07-02, S1-10).
                    default_sql = re.sub(
                        r"(?i)\bCURRENT_TIMESTAMP\s*\(\s*\)",
                        "CURRENT_TIMESTAMP",
                        default_sql,
                    )
                if (
                    dialect == "postgresql"
                    and dtype.upper().split("(")[0] == "BYTEA"
                    and re.search(r"(?i)\bgen_random_uuid\s*\(\s*\)", default_sql)
                ):
                    # Oracle RAW(16) DEFAULT SYS_GUID(): the column mapped to
                    # BYTEA but gen_random_uuid() is a uuid (42804). Render
                    # the same 16 random bytes as bytea.
                    default_sql = re.sub(
                        r"(?i)\bgen_random_uuid\s*\(\s*\)",
                        "DECODE(REPLACE(gen_random_uuid()::TEXT, '-', ''), 'hex')",
                        default_sql,
                    )
                if dialect == "postgresql" and dtype.upper() == "BOOLEAN":
                    # A source BIT column arrives with a 0/1 default;
                    # PostgreSQL rejects an integer default on BOOLEAN.
                    m_bool = re.fullmatch(r"\(*\s*([01])\s*\)*", default_sql)
                    if m_bool:
                        default_sql = "TRUE" if m_bool.group(1) == "1" else "FALSE"
                # A string default on a binary column is invalid on Oracle
                # (ORA-01465: must be hex) and SQL Server (implicit varchar ->
                # varbinary conversion, error 257). A MySQL ``VARBINARY DEFAULT
                # '…'`` stores text in a binary column; drop the non-portable
                # default rather than emit invalid hex guesswork.
                if (
                    dialect in ("oracle", "tsql")
                    and dtype.upper().split("(")[0]
                    in ("RAW", "BLOB", "VARBINARY", "BINARY")
                    and re.fullmatch(r"'[^']*'", default_sql.strip())
                ):
                    default_sql = ""
                if (
                    dialect == "mysql"
                    and default_sql
                    and not default_sql.startswith("(")
                    and re.search(r"\w\s*\(", default_sql)
                    and not re.match(r"(?i)^\s*CURRENT_TIMESTAMP\b", default_sql)
                ):
                    # MySQL requires parentheses around expression
                    # defaults (8.0.13+); bare function calls are 1064.
                    default_sql = f"({default_sql})"
                default = f" DEFAULT {default_sql}" if default_sql else ""
            # A PostgreSQL SERIAL/BIGSERIAL/SMALLSERIAL column is an
            # auto-increment integer + sequence. On another engine it must become
            # the base integer type plus that engine's identity clause (leaving
            # ``BIGSERIAL`` verbatim is invalid MySQL/Oracle/T-SQL).
            _serial_base = {
                "SMALLSERIAL": "SMALLINT",
                "SERIAL2": "SMALLINT",
                "SERIAL": "INTEGER",
                "SERIAL4": "INTEGER",
                "BIGSERIAL": "BIGINT",
                "SERIAL8": "BIGINT",
            }
            is_serial = col.data_type.name.upper() in _serial_base
            if is_serial and dialect != "postgresql":
                dtype = _portable_type_name(
                    _serial_base[col.data_type.name.upper()], dialect
                )
            identity = ""
            if col.identity or (is_serial and dialect != "postgresql"):
                # Preserve the IDENTITY(seed, step) so the sequence keeps its
                # starting value/increment on the target (RC-3). None -> 1.
                seed = col.identity_seed if col.identity_seed is not None else 1
                step = col.identity_step if col.identity_step is not None else 1
                custom = seed != 1 or step != 1  # (1, 1) is every engine's default
                # GENERATED ALWAYS (immutable) vs BY DEFAULT — preserve it on the
                # engines that distinguish the two (PG/Oracle).
                kind = "ALWAYS" if col.identity_always else "BY DEFAULT"
                span = f" (START WITH {seed} INCREMENT BY {step})" if custom else ""
                if dialect == "mysql":
                    # MySQL has no per-column step, and the seed is a table option
                    # (AUTO_INCREMENT=n), not a column clause — left as the default.
                    identity = " AUTO_INCREMENT"
                    if custom:
                        # A non-default START WITH/INCREMENT BY (and any MAXVALUE/
                        # CYCLE) can't be a MySQL column clause; flag rather than
                        # silently reset the sequence to start 1 / step 1.
                        identity += (
                            f" /* UNIQUE-1049: source IDENTITY (START {seed} INCREMENT "
                            f"{step}) has no MySQL column form — AUTO_INCREMENT "
                            "starts at 1, steps by 1 (docs/03-unsupported.md) */"
                        )
                elif dialect == "postgresql":
                    if custom or col.identity_always:
                        identity = f" GENERATED {kind} AS IDENTITY{span}"
                    else:
                        # BIGSERIAL when the column is a 64-bit integer so a FK from
                        # another BIGINT column matches (SERIAL is only int4).
                        dtype = "BIGSERIAL" if dtype.upper() == "BIGINT" else "SERIAL"
                        identity = ""
                elif dialect == "tsql":
                    identity = f" IDENTITY({seed},{step})"
                else:
                    identity = f" GENERATED {kind} AS IDENTITY{span}"
            # A computed/generated column (``GENERATED ALWAYS AS (expr)``): T-SQL
            # spells it ``col AS (expr)`` (no type, PERSISTED = STORED); PG only
            # has STORED; Oracle/MySQL default VIRTUAL and keep STORED if present.
            generated = ""
            if col.generated_expr is not None:
                expr = _emit_expression(col.generated_expr, dialect)
                if dialect == "tsql":
                    persisted = (
                        " PERSISTED"
                        if col.generated_stored
                        or col.unique
                        or col.primary_key
                        or col.name.lower() in _persist_names
                        else ""
                    )
                    # A T-SQL computed column DERIVES its type from the
                    # expression; a JSON accessor yields nvarchar, so a
                    # declared numeric/date type needs an explicit CAST to
                    # keep the source column's typing.
                    if "JSON_" in expr.upper() and not re.match(
                        r"(?i)N?VARCHAR|N?CHAR|TEXT", dtype
                    ):
                        expr = f"CAST({expr} AS {dtype})"
                    generated = f" AS ({expr}){persisted}"
                elif dialect == "postgresql":
                    # A JSON extraction returns json; a non-text generated
                    # column needs the ->>-style TEXT accessor plus a cast
                    # ("column is of type integer but expression is of type
                    # json" otherwise).
                    if re.search(
                        r"(?i)\bJSON_EXTRACT(?:_PATH)?\s*\(", expr
                    ) and not re.match(r"(?i)TEXT|JSON", dtype):
                        expr = re.sub(
                            r"(?i)\bJSON_EXTRACT_PATH\s*\(",
                            "JSON_EXTRACT_PATH_TEXT(",
                            expr,
                        )
                        expr = re.sub(
                            r"(?i)\bJSON_EXTRACT\s*\(\s*(\w+)\s*,\s*'\$\.(\w+)'\s*\)",
                            r"(\1 ->> '\2')",
                            expr,
                        )
                        expr = f"CAST({expr} AS {dtype})"
                    generated = f" GENERATED ALWAYS AS ({expr}) STORED"
                else:
                    store = " STORED" if col.generated_stored else ""
                    generated = f" GENERATED ALWAYS AS ({expr}){store}"
            # Column comment (RC-3): inline on MySQL, a trailing COMMENT ON
            # statement on PG/Oracle, dropped-with-a-note on T-SQL.
            col_name = _ident(col.name, col.quoted, dialect)
            # A MySQL UNSIGNED integer widens to a type that holds its range
            # (UINT -> BIGINT, etc.), but the other engines can't enforce
            # non-negativity in the type — preserve it with CHECK (col >= 0).
            unsigned_check = (
                f" CHECK ({col_name} >= 0)"
                if col.data_type.name.upper() in _UNSIGNED_INT_TYPES
                and dialect != "mysql"
                else ""
            )
            comment_inline = (
                f" COMMENT {col.comment}" if dialect == "mysql" and col.comment else ""
            )
            if col.comment and dialect in ("postgresql", "oracle", "tsql"):
                column_comments.append((col_name, col.comment))
            # MySQL's ON UPDATE CURRENT_TIMESTAMP auto-update: keep it inline on
            # MySQL; the other engines need a trigger, so carry a documented note.
            on_update_inline = (
                f" {col.on_update}" if dialect == "mysql" and col.on_update else ""
            )
            if col.on_update and dialect != "mysql":
                on_update_notes.append(
                    f"-- UNIQUE-1050: MySQL's {col.on_update} on column {col_name} has "
                    f"no {dialect} column-level equivalent; add an ON UPDATE "
                    "trigger to refresh it"
                )
            # A column COLLATE clause is engine-specific: keep it on the source
            # engine, carry a warning elsewhere (its name has no portable
            # mapping — a live DB connection could resolve the actual collation).
            collate_inline = (
                f" {col.collate}"
                if col.collate and dialect == SOURCE_DIALECT.get()
                else ""
            )
            if col.collate and dialect != SOURCE_DIALECT.get():
                collate_notes.append(
                    f"-- UNIQUE-1051: column {col_name} collation/charset "
                    f"({col.collate}) has no portable {dialect} equivalent; the "
                    "column uses the default collation (comparisons/ordering may "
                    "differ) — set it explicitly on the target or supply the "
                    "source DB connection"
                )
            # A MySQL/Oracle INVISIBLE column is excluded from SELECT *; both
            # engines keep it inline (after the type). PG/T-SQL have no such
            # attribute, so carry a documented note — dropping it silently
            # changed SELECT *'s result set.
            invisible_inline = (
                " INVISIBLE" if col.invisible and dialect in ("mysql", "oracle") else ""
            )
            if col.invisible and dialect in ("postgresql", "tsql"):
                invisible_notes.append(
                    f"-- UNIQUE-1052: column {col_name} was INVISIBLE (excluded from "
                    f"SELECT *) on the source; {dialect} has no invisible-column "
                    "attribute, so the column is now visible to SELECT * "
                    "(docs/03-unsupported.md)"
                )
            # A computed column carries no identity/default; T-SQL derives the
            # type from the expression, so it omits the declared type entirely.
            if col.generated_expr is not None:
                nullable = "" if col.nullable else " NOT NULL"
                body = generated if dialect == "tsql" else f" {dtype}{generated}"
                col_defs.append(f"  {col_name}{body}{nullable}{pk}{unique}{check}")
                continue
            # Oracle column attribute order: type [identity] [DEFAULT val] [NOT NULL].
            # Other dialects: type [identity] [NOT NULL] [DEFAULT val].
            if dialect == "oracle":
                # Identity columns are implicitly NOT NULL in Oracle; adding NOT NULL
                # explicitly after AS IDENTITY can cause parser errors in some versions.
                nullable = "" if (col.nullable or col.identity) else " NOT NULL"
                col_defs.append(
                    f"  {col_name} {dtype}{collate_inline}{identity}{default}"
                    f"{nullable}{pk}{unique}{check}{unsigned_check}{invisible_inline}"
                )
            else:
                nullable = "" if col.nullable else " NOT NULL"
                col_defs.append(
                    f"  {col_name} {dtype}{collate_inline}{identity}{nullable}"
                    f"{default}{pk}{unique}{check}{unsigned_check}"
                    f"{on_update_inline}{comment_inline}{invisible_inline}"
                )
        # Table-level constraints (PK/FK/UNIQUE/CHECK), re-transpiled.
        # A fragment may come back as a documented comment (e.g. a generated
        # column with no portable type); those can't live inside the
        # parenthesized column list, so collect them and append afterwards.
        trailing_comments: list[str] = list(set_type_notes)
        trailing_comments.extend(on_update_notes)
        trailing_comments.extend(collate_notes)
        trailing_comments.extend(invisible_notes)
        post_statements: list[str] = []
        for constraint in node.table_constraints:
            # PostgreSQL ``UNIQUE … NULLS NOT DISTINCT`` (NULLs compare equal, so
            # only one NULL row is allowed) has no equivalent elsewhere, where a
            # UNIQUE key treats NULLs as distinct. Strip the modifier to a plain
            # UNIQUE and document the divergence (never silently change it).
            if (
                dialect != "postgresql"
                and constraint.source_dialect == "postgresql"
                and re.search(r"(?i)\bNULLS\s+NOT\s+DISTINCT\b", constraint.sql)
            ):
                constraint = dataclasses.replace(
                    constraint,
                    sql=re.sub(
                        r"(?i)\s*\bNULLS\s+NOT\s+DISTINCT\b", "", constraint.sql
                    ),
                )
                trailing_comments.append(
                    "-- UNIQUE-1053: PostgreSQL UNIQUE … NULLS NOT DISTINCT (NULLs "
                    f"compare equal) has no {dialect} equivalent; a plain UNIQUE "
                    "treats NULLs as distinct (docs/03-unsupported.md)"
                )
            # A SELF-referencing FK with a cascading referential action is
            # T-SQL error 1785 ("may cause cycles or multiple cascade paths"):
            # downgrade the action to NO ACTION and document the loss.
            _tbl_name = getattr(node.table, "name", "")
            if (
                dialect == "tsql"
                and _tbl_name
                and re.search(
                    rf"(?i)\bREFERENCES\s+\[?{re.escape(_tbl_name)}\]?\s*\(",
                    constraint.sql,
                )
                and re.search(
                    r"(?i)\bON\s+(?:DELETE|UPDATE)\s+(?:SET\s+NULL|SET\s+DEFAULT|CASCADE)\b",
                    constraint.sql,
                )
            ):
                constraint = dataclasses.replace(
                    constraint,
                    sql=re.sub(
                        r"(?i)\b(ON\s+(?:DELETE|UPDATE))\s+"
                        r"(?:SET\s+NULL|SET\s+DEFAULT|CASCADE)\b",
                        r"\1 NO ACTION",
                        constraint.sql,
                    ),
                )
                trailing_comments.append(
                    "-- UNIQUE-1054: T-SQL forbids a cascading action on a "
                    "self-referencing FK (error 1785); downgraded to NO ACTION "
                    "— emulate with an AFTER trigger if the automatic action "
                    "is required (docs/03-unsupported.md)"
                )
            # Oracle has no ``SET DEFAULT`` referential action (only CASCADE /
            # SET NULL / NO ACTION); shipped verbatim it is ORA-03001
            # "unimplemented feature". Drop the action (the FK reverts to the
            # NO ACTION default) and document the loss — an ON DELETE SET
            # DEFAULT must be emulated with a trigger if it is required.
            if dialect in _NO_SET_DEFAULT_FK and _FK_SET_DEFAULT_RE.search(
                constraint.sql
            ):
                constraint = dataclasses.replace(
                    constraint,
                    sql=_FK_SET_DEFAULT_RE.sub("", constraint.sql),
                )
                trailing_comments.append(
                    "-- UNIQUE-1055: Oracle has no ON DELETE SET DEFAULT referential "
                    "action; dropped (FK reverts to NO ACTION) — emulate with an "
                    "AFTER DELETE trigger if required (docs/03-unsupported.md)"
                )
            # A reconstructed T-SQL inline INDEX ("name|cols"): T-SQL and MySQL
            # keep the inline element; PG/Oracle get a separate CREATE INDEX
            # appended after the table (their CREATE TABLE has no inline form).
            if constraint.kind == "INLINE_INDEX_COLS":
                _ixn, _ixc = constraint.sql.split("|", 1)
                if dialect in ("tsql", "mysql"):
                    col_defs.append(f"  INDEX {_ixn} ({_ixc})")
                else:
                    post_statements.append(f"CREATE INDEX {_ixn} ON {table} ({_ixc})")
                continue
            emitted = _emit_passthrough_inline(constraint, dialect)
            if emitted.lstrip().startswith("--"):
                trailing_comments.append(emitted.strip())
            else:
                col_defs.append(f"  {emitted}")
        if dialect == "mysql":
            # MySQL requires an AUTO_INCREMENT column to be indexed (error 1075).
            # A PostgreSQL SERIAL carries no key, so add one when nothing already
            # covers the column (its own PRIMARY KEY/UNIQUE, or a table key).
            _auto_col = _auto_line_keyed = None
            for _cd in col_defs:
                if re.search(r"(?i)\bAUTO_INCREMENT\b", _cd):
                    _m = re.match(r'\s*[`"]?(\w+)', _cd)
                    _auto_col = _m.group(1) if _m else None
                    # Ignore a carrier comment — its "UNIQUE:" is not a key.
                    _cd_nc = re.sub(r"/\*.*?\*/", "", _cd)
                    _auto_line_keyed = bool(
                        re.search(r"(?i)\b(?:PRIMARY\s+KEY|UNIQUE)\b", _cd_nc)
                    )
                    break
            if _auto_col is not None and not _auto_line_keyed:
                _joined = re.sub(r"/\*.*?\*/", "", "\n".join(col_defs))
                _keyed = re.search(
                    r'(?i)\b(?:PRIMARY\s+KEY|UNIQUE|KEY)\b[^,\n]*[`"(]\s*'
                    + re.escape(_auto_col)
                    + r"\b",
                    _joined,
                )
                if not _keyed:
                    col_defs.append(f"  KEY (`{_auto_col}`)")
        cols = ",\n".join(col_defs)
        result = f"{tsql_guard}CREATE {temp}TABLE {exists}{table} (\n{cols}\n)"
        # An Oracle GLOBAL TEMPORARY TABLE defaults to ON COMMIT DELETE ROWS
        # (transaction-scoped). PG/T-SQL/MySQL temp tables are session-scoped —
        # their rows survive an inter-statement commit — so the faithful Oracle
        # form is ON COMMIT PRESERVE ROWS. Without it, rows vanish before a later
        # statement in the same script sees them (PG COUNT=2 vs Oracle COUNT=0).
        if node.temporary and dialect == "oracle" and SOURCE_DIALECT.get() != "oracle":
            result += " ON COMMIT PRESERVE ROWS"
        # Emitted unconditionally: the transformer degrades the whole
        # statement on targets without the concept, so only PostgreSQL
        # normally reaches here — and if anything slips through, emitting
        # the clause beats losing the table's defining structure.
        if node.inherits_clause:
            result += f"\n{node.inherits_clause}"
        # T-SQL In-Memory OLTP storage options (MEMORY_OPTIMIZED / DURABILITY):
        # re-emit on T-SQL, carry a documented note elsewhere — the table becomes
        # a regular disk table with no logical/value difference (RC-2).
        if node.unsupported_options:
            if dialect == "tsql":
                result += " WITH (" + ", ".join(node.unsupported_options) + ")"
            else:
                opts = ", ".join(node.unsupported_options)
                trailing_comments.append(
                    f"-- UNIQUE-1056: T-SQL In-Memory OLTP storage option(s) [{opts}] "
                    f"have no {dialect} equivalent; the table is created as a "
                    "regular disk-based table (no logical/value difference)"
                )
        # MySQL's table-level default COLLATE: keep it on MySQL, carry a warning
        # elsewhere (engine-specific name, no portable mapping — a live DB
        # connection could resolve the actual collation).
        if node.table_collate:
            if dialect == "mysql":
                result += f" {node.table_collate}"
            else:
                trailing_comments.append(
                    f"-- UNIQUE-1057: MySQL table default collation/charset "
                    f"({node.table_collate}) has no portable {dialect} "
                    "equivalent; string columns use the default collation "
                    "(comparisons/ordering may differ) — set it explicitly on "
                    "the target or supply the source DB connection"
                )
        # Column comments: PG/Oracle take a trailing COMMENT ON COLUMN statement;
        # T-SQL has only sp_addextendedproperty, so note the drop rather than
        # lose it silently.
        if column_comments and dialect in ("postgresql", "oracle"):
            result += ";\n" + ";\n".join(
                f"COMMENT ON COLUMN {table}.{cn} IS {cmt}"
                for cn, cmt in column_comments
            )
        elif column_comments and dialect == "tsql":
            # A column comment is metadata, not an executable statement; T-SQL
            # carries it via sp_addextendedproperty. Leave a plain (non-carrier)
            # note rather than emit that verbose call or lose it silently.
            trailing_comments.extend(
                f"-- column {cn} comment (T-SQL: sp_addextendedproperty): {cmt}"
                for cn, cmt in column_comments
            )
        # Table comment (MySQL COMMENT='…'): inline on MySQL, a trailing
        # COMMENT ON TABLE on PG/Oracle, a plain note on T-SQL (no executable
        # form) — rather than dropped silently.
        if node.table_comment:
            if dialect == "mysql":
                result += f" COMMENT={node.table_comment}"
            elif dialect in ("postgresql", "oracle"):
                result += f";\nCOMMENT ON TABLE {table} IS {node.table_comment}"
            else:  # tsql
                trailing_comments.append(
                    "-- table comment (T-SQL: sp_addextendedproperty): "
                    f"{node.table_comment}"
                )
        for _ps in post_statements:
            result += f";\n{_ps}"
        if trailing_comments:
            result += "\n" + "\n".join(trailing_comments)
        return result

    bare = f"{tsql_guard}CREATE {temp}TABLE {exists}{table}"
    if node.partition_of_clause:
        return f"{bare} {node.partition_of_clause}"
    if node.inherits_clause:
        # PG requires the empty column list when INHERITS supplies them all.
        return f"{bare} () {node.inherits_clause}"
    if dialect == "postgresql":
        # A zero-column table (``CREATE TABLE onerow()``) keeps its parens
        # — bare CREATE TABLE is invalid PG (wave 128). Only PG has the
        # form; other targets gate it in the transformer.
        return f"{bare} ()"
    return bare


#: Single-engine view modifiers each target re-attaches natively: slot ``with``
#: renders a ``WITH attr, …`` list after the view name (T-SQL); slot ``pre``
#: renders the modifiers between CREATE and VIEW (MySQL). A modifier no entry
#: claims is warn-dropped by ``_emit_create_view``.
_NATIVE_VIEW_MODIFIERS: dict[str, tuple[str, Callable[[str], bool]]] = {
    "tsql": (
        "with",
        lambda u: u in ("SCHEMABINDING", "ENCRYPTION", "VIEW_METADATA"),
    ),
    "mysql": (
        "pre",
        lambda u: u.startswith(("ALGORITHM", "DEFINER", "SQL SECURITY")),
    ),
}


def _emit_create_view(node: CreateViewStatement, dialect: str) -> str:
    """Emit a CREATE VIEW statement."""
    name = _emit_table_ref(node.name, dialect)
    if node.or_replace:
        # T-SQL has no CREATE OR REPLACE VIEW; CREATE OR ALTER VIEW (2016+) is
        # the equivalent that re-creates an existing view in place.
        replace = "OR ALTER " if dialect == "tsql" else "OR REPLACE "
    else:
        replace = ""
    view_query = node.query
    if dialect == "tsql" and view_query.order_by and not view_query.limit:
        # Illegal in a T-SQL view without TOP/OFFSET, and advisory on the
        # engines that accept it — a view has no guaranteed order anyway.
        view_query = dataclasses.replace(view_query, order_by=())
    query = _emit_select(view_query, dialect)
    # MATERIALIZED is a native modifier on Oracle and PostgreSQL (a distinct
    # object with its own storage/refresh), so it changes the CREATE keyword
    # rather than degrading — the reverse directions already round-trip it.
    # Neither engine accepts OR REPLACE on a materialized view. T-SQL/MySQL have
    # no equivalent, so it stays a warned drop there.
    materialized = any(m.upper() == "MATERIALIZED" for m in node.dropped_modifiers)
    view_kw = "VIEW"
    if materialized and dialect in ("oracle", "postgresql"):
        view_kw = "MATERIALIZED VIEW"
        replace = ""
    # Non-portable view modifiers (SCHEMABINDING, ALGORITHM=, DEFINER=, …):
    # re-attach natively where the target owns the modifier (per-engine table
    # below); degrade the rest with a warned carrier (auto-warned by the
    # no-silent-loss scan) — never a silent drop (audit 2026-07-24 B2 seed).
    with_list: list[str] = []
    pre_list: list[str] = []
    dropped: list[str] = []
    native = _NATIVE_VIEW_MODIFIERS.get(dialect)
    for mod in node.dropped_modifiers:
        upper = mod.upper()
        if upper == "MATERIALIZED" and view_kw == "MATERIALIZED VIEW":
            continue  # rendered natively in the CREATE keyword above
        if native and native[1](upper):
            (with_list if native[0] == "with" else pre_list).append(
                upper if native[0] == "with" else mod
            )
        else:
            dropped.append(mod)
    with_attrs = f"\nWITH {', '.join(with_list)}" if with_list else ""
    pre_mods = f"{' '.join(pre_list)} " if pre_list else ""
    result = f"CREATE {replace}{pre_mods}{view_kw} {name}{with_attrs} AS\n{query}"
    if node.check_option:
        # T-SQL and Oracle accept only the unscoped ``WITH CHECK OPTION``;
        # MySQL and PostgreSQL also take the LOCAL/CASCADED scope.
        opt = node.check_option
        if dialect in ("tsql", "oracle"):
            opt = "CHECK OPTION"
        result = f"{result}\nWITH {opt}"
    if dropped:
        carriers = "\n".join(
            f"-- UNIQUE-1058: view modifier {mod} is not portable on {dialect}; dropped"
            for mod in dropped
        )
        result = f"{carriers}\n{result}"
    return result


def _emit_drop(node: DropStatement, dialect: str) -> str:
    """Emit a DROP statement.

    DROP INDEX differs per engine (audit B2): T-SQL and MySQL require the
    owning table (``ON tbl``); Oracle/PostgreSQL take only the index name.
    When the target requires a table the source did not carry, the statement
    degrades to a documented carrier — never invalid SQL.
    """
    name = _emit_table_ref(node.name, dialect)
    exists = "IF EXISTS " if node.if_exists else ""
    cascade = " CASCADE" if node.cascade else ""
    if node.object_type == "SEQUENCE" and dialect == "mysql":
        # Mirrors the CREATE SEQUENCE carrier: MySQL has no sequences.
        return (
            "-- UNIQUE-1059: MySQL has no sequences (use an AUTO_INCREMENT "
            "column); original preserved:\n"
            f"-- DROP SEQUENCE {exists}{name}"
        )
    if node.object_type == "TYPE" and dialect == "mysql":
        # MySQL has no user-defined types in any form.
        return (
            "-- UNIQUE-1060: MySQL has no user-defined types; original "
            f"preserved:\n-- DROP TYPE {exists}{name}"
        )
    if node.object_type == "INDEX":
        if dialect in ("tsql", "mysql"):
            if not node.on_table:
                return (
                    f"-- UNIQUE-1061: {dialect} DROP INDEX requires the owning "
                    "table, which the source statement does not carry; "
                    "original preserved:\n"
                    f"-- DROP INDEX {exists}{name}"
                )
            if dialect == "mysql":
                # MySQL has no DROP INDEX IF EXISTS; emit the plain form
                # (a re-run on a missing index errors — same as the source
                # would without its guard machinery).
                return f"DROP INDEX {name} ON {node.on_table}"
            return f"DROP INDEX {exists}{name} ON {node.on_table}"
        # Oracle/PostgreSQL: index names are schema-scoped; the T-SQL ON
        # table (or legacy tbl. qualifier) is dropped.
        return f"DROP INDEX {exists}{name}"
    if node.object_type == "TRIGGER":
        # PG triggers are per-table: ``ON tbl`` is mandatory there and
        # invalid everywhere else (trigger names are schema-scoped on
        # T-SQL/MySQL/Oracle, which is also why a non-PG source has no
        # table to carry over — that degrades, like DROP INDEX).
        if dialect == "postgresql":
            if not node.on_table:
                return (
                    "-- UNIQUE-1062: PostgreSQL DROP TRIGGER requires the "
                    "owning table (ON tbl), which the source statement "
                    "does not carry; original preserved:\n"
                    f"-- DROP TRIGGER {exists}{name}"
                )
            return f"DROP TRIGGER {exists}{name} ON {node.on_table}{cascade}"
        return f"DROP TRIGGER {exists}{name}{cascade}"
    return f"DROP {node.object_type} {exists}{name}{cascade}"


# Cross-family imports at the tail (after the defs above) so the mutually
# recursive emit-family modules resolve without namespace injection — see
# emit.py's module docstring.
from unique.core.converter.emit import (  # noqa: E402
    _UNSIGNED_INT_TYPES,
    _emit_select,
    _emit_table_ref,
    _portable_type_name,
)
from unique.core.converter.emit_expr import _emit_expression  # noqa: E402
from unique.core.converter.emit_passthrough import (  # noqa: E402
    _emit_passthrough_inline,
)
