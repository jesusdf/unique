# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.

Seam layout (audit doc 04 F4 split — B17). The emitter families were moved into
four sibling modules — ``emit_functions``/``emit_expr``/``emit_ddl``/
``emit_passthrough`` — mutually recursive with each other and this module. They
resolve cross-references with *explicit* imports, not runtime namespace
injection. This module is always the entry point (nothing imports a seam
directly), so its helpers are all defined before its tail ``import *`` pulls the
seams in and re-exports them (the façade surface). Each seam in turn imports the
helpers and siblings it calls at *its own tail*, after its ``def``\\s — so every
module finishes defining its own names before importing any other, and the
cycle (notably ``emit_expr`` ⇄ ``emit_functions``) resolves: whichever is
entered second finds the first already complete. Every cross-seam name is thus
statically importable — mypy checks the seams at the project's normal strictness
with no per-module override, and there is no per-call import cost.
"""

from __future__ import annotations

import dataclasses
import re

import sqlglot
import sqlglot.expressions as exp

from unique.core.ast_nodes import (
    Alias,
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CaseExpression,
    CastExpression,
    ColumnRef,
    CommentStatement,
    CreateTableStatement,
    CreateViewStatement,
    CTEDefinition,
    DeleteStatement,
    DropStatement,
    ExcludedColumn,
    ExpressionList,
    FunctionCall,
    InsertStatement,
    JoinClause,
    JoinType,
    LimitClause,
    Literal,
    OnConflictClause,
    OrderByItem,
    OrderDirection,
    PassthroughSQL,
    PivotRelation,
    RawSQL,
    Script,
    SelectStatement,
    SetOperationType,
    Star,
    SubqueryExpression,
    TableRef,
    UnaryOp,
    UnaryOperator,
    UnpivotRelation,
    UpdateStatement,
)

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter._base import _RESERVED_IDENTIFIERS
from unique.core.converter.harvest import (  # noqa: F401
    _coerce_bit_literal,
    _coerce_date_literal,
    _oracle_date_literal,
    wrap_oracle_date_arg,
)

# Per-dialect CAST target-type overrides: MySQL CAST accepts only a fixed set
# (SIGNED/UNSIGNED/CHAR/DATE/…), not INT/BOOLEAN; T-SQL has no BOOLEAN (it is BIT).
# PostgreSQL's built-in geometric types have no equivalent on the other engines
# (MySQL's spatial POINT is a different, WKB-based type). A cast to one degrades
# to the source's text value plus a carrier.
_PG_GEOMETRIC_TYPES = frozenset(
    {"POINT", "LINE", "LSEG", "BOX", "PATH", "POLYGON", "CIRCLE"}
)

# Numeric CAST targets, for MySQL's lenient string->number cast compensation.
_NUMERIC_CAST_TYPES = frozenset(
    {
        "DECIMAL",
        "NUMERIC",
        "NUMBER",
        "DEC",
        "INT",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "MEDIUMINT",
        "FLOAT",
        "DOUBLE",
        "REAL",
    }
)

# MySQL UNSIGNED integer CAST targets (sqlglot spells them U*), for the same
# lenient string->number compensation as _NUMERIC_CAST_TYPES.
_UNSIGNED_CAST_TYPES = frozenset(
    {"UBIGINT", "UINT", "UINTEGER", "USMALLINT", "UTINYINT", "UMEDIUMINT"}
)

_CAST_TYPE_MAP: dict[str, dict[str, str]] = {
    "mysql": {
        "INT": "SIGNED",
        "INTEGER": "SIGNED",
        "BIGINT": "SIGNED",
        "SMALLINT": "SIGNED",
        "TINYINT": "SIGNED",
        "BOOLEAN": "SIGNED",
        "BOOL": "SIGNED",
        # T-SQL's precise datetime types -> MySQL's DATETIME. MySQL's CAST has
        # no TIMESTAMP target either (that spelling is 1064) — DATETIME holds the
        # same value.
        "DATETIME2": "DATETIME",
        "SMALLDATETIME": "DATETIME",
        "TIMESTAMP": "DATETIME",
        # MySQL has no timezone-aware type; DATETIME holds the same instant.
        "TIMESTAMPTZ": "DATETIME",
        # T-SQL money types are fixed-scale decimals (DECIMAL(19,4)/(10,4)).
        "MONEY": "DECIMAL(19,4)",
        "SMALLMONEY": "DECIMAL(10,4)",
        # MySQL CAST has no VARCHAR spelling — character casts use CHAR.
        "VARCHAR": "CHAR",
        "NVARCHAR": "CHAR",
        # …nor TEXT (PG's habitual cast target) — wave 148.
        "TEXT": "CHAR",
    },
    # PG float8 casts parse to DOUBLE — T-SQL's 64-bit float is FLOAT
    # (bare DOUBLE is a syntax error) and Oracle's is BINARY_DOUBLE
    # (ORA-00902).
    # T-SQL TIMESTAMP is a rowversion (binary), NOT a datetime — an Oracle/PG/
    # MySQL TIMESTAMP cast must become DATETIME2 to keep the value.
    "tsql": {
        "BOOLEAN": "BIT",
        "BOOL": "BIT",
        "DOUBLE": "FLOAT",
        "YEAR": "SMALLINT",
        "TIMESTAMP": "DATETIME2",
        # PG's timezone-aware timestamp -> T-SQL's DATETIMEOFFSET.
        "TIMESTAMPTZ": "DATETIMEOFFSET",
        # TEXT is a deprecated LOB — invalid as a CAST target (error 529); the
        # modern large-string type VARCHAR(MAX) holds the same value.
        "TEXT": "VARCHAR(MAX)",
    },
    # DATETIME/DATETIME2/SMALLDATETIME are T-SQL types; Oracle/PostgreSQL use
    # TIMESTAMP. Passing DATETIME through fails (ORA-00902 / invalid pg type).
    "oracle": {
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "SMALLDATETIME": "TIMESTAMP",
        "MONEY": "NUMBER(19,4)",
        "SMALLMONEY": "NUMBER(10,4)",
        "VARCHAR": "VARCHAR2",
        "NVARCHAR": "NVARCHAR2",
        # CLOB is not a valid CAST target (ORA-22849); VARCHAR2(4000) is the
        # portable large-string stand-in (matches the STRING_AGG/GROUP_CONCAT
        # CLOB->VARCHAR2 rewrite). DDL CLOB columns go through a separate map.
        "CLOB": "VARCHAR2(4000)",
        "DOUBLE": "BINARY_DOUBLE",
        # Oracle has INTEGER/SMALLINT (NUMBER aliases) but not BIGINT/TINYINT/
        # MEDIUMINT (ORA-00902); INTEGER rounds a fractional value like the
        # others (CAST(3.99 AS INTEGER) = 4).
        "BIGINT": "INTEGER",
        "TINYINT": "INTEGER",
        "MEDIUMINT": "INTEGER",
    },
    "postgresql": {
        "DATETIME": "TIMESTAMP",
        "DATETIME2": "TIMESTAMP",
        "SMALLDATETIME": "TIMESTAMP",
        "MONEY": "NUMERIC(19,4)",
        "SMALLMONEY": "NUMERIC(10,4)",
        # PG has no bare DOUBLE (a bare-name cast errors) — it is DOUBLE PRECISION.
        "DOUBLE": "DOUBLE PRECISION",
        # PG's binary type is BYTEA (there is no BINARY/VARBINARY).
        "BINARY": "BYTEA",
        "VARBINARY": "BYTEA",
    },
}

# Statistical-aggregate spellings per target. Keys are the canonical names
# the IR carries (sqlglot: var_pop -> VARIANCE_POP, variance -> VARIANCE);
# an absent target means the canonical name is already that engine's
# spelling. VARIANCE/STDDEV are SAMPLE variants in PG/Oracle/T-SQL(VAR/
# STDEV) but POPULATION in MySQL — hence the explicit *_SAMP mappings.
_STAT_AGGREGATE_MAP: dict[str, dict[str, str]] = {
    "VARIANCE_POP": {
        "tsql": "VARP",
        "mysql": "VAR_POP",
        "oracle": "VAR_POP",
        "postgresql": "VAR_POP",
    },
    "VAR_POP": {"tsql": "VARP"},
    "VARIANCE": {"tsql": "VAR", "mysql": "VAR_SAMP", "oracle": "VAR_SAMP"},
    "VAR_SAMP": {"tsql": "VAR"},
    "STDDEV_POP": {"tsql": "STDEVP"},
    "STDDEV_SAMP": {"tsql": "STDEV"},
    "STDDEV": {"tsql": "STDEV", "mysql": "STDDEV_SAMP", "oracle": "STDDEV_SAMP"},
}

# Date format-model tokens across the four conventions this tool bridges:
#   oracle  — Oracle/PostgreSQL TO_CHAR/TO_DATE model
#   mysql   — MySQL DATE_FORMAT/STR_TO_DATE (%i minute, %M month name, %s second)
#   tsql    — T-SQL FORMAT .NET custom format (MM month, mm minute, HH 24h)
#   python  — Python-strftime (%M minute, %m month, %S second) — sqlglot's
#             *canonical* format for TimeToStr/StrToTime, so it is the model we
#             receive when a T-SQL FORMAT / MySQL DATE_FORMAT is parsed.
# Longest-first so YYYY matches before YY and MONTH before MON/MM.
_DATE_FMT_TOKENS: list[tuple[str, str, str, str]] = [
    ("YYYY", "%Y", "yyyy", "%Y"),
    ("YY", "%y", "yy", "%y"),
    ("MONTH", "%M", "MMMM", "%B"),
    ("MON", "%b", "MMM", "%b"),
    ("HH24", "%H", "HH", "%H"),
    ("HH12", "%h", "hh", "%I"),
    ("MM", "%m", "MM", "%m"),
    ("DD", "%d", "dd", "%d"),
    ("HH", "%h", "hh", "%I"),
    ("MI", "%i", "mm", "%M"),
    ("SS", "%s", "ss", "%S"),
    ("DAY", "%W", "dddd", "%A"),
    ("DY", "%a", "ddd", "%a"),
    ("AM", "%p", "tt", "%p"),
    ("PM", "%p", "tt", "%p"),
]
_FMT_MODEL_IDX = {"oracle": 0, "mysql": 1, "tsql": 2, "python": 3}

# MySQL unsigned integer types. Their range is preserved by widening (UINT ->
# BIGINT, etc.); the non-negativity is preserved with a CHECK on other engines.
_UNSIGNED_INT_TYPES = {"UTINYINT", "USMALLINT", "UMEDIUMINT", "UINT", "UBIGINT"}


def _convert_date_format(fmt: str, src_model: str, dst_model: str) -> str:
    """Translate a date format string between the Oracle, strftime and .NET
    models (longest-token match; literal characters pass through)."""
    si, di = _FMT_MODEL_IDX[src_model], _FMT_MODEL_IDX[dst_model]
    toks = sorted(_DATE_FMT_TOKENS, key=lambda t: -len(t[si]))
    # strftime (%m vs %M) and .NET (MM month vs mm minute, HH 24h vs hh 12h) are
    # case-sensitive; only the Oracle model is case-insensitive.
    case_sensitive = si != _FMT_MODEL_IDX["oracle"]
    out: list[str] = []
    i = 0
    while i < len(fmt):
        for tok in toks:
            src_tok = tok[si]
            seg = fmt[i : i + len(src_tok)]
            if (seg == src_tok) if case_sensitive else (seg.upper() == src_tok):
                out.append(tok[di])
                i += len(src_tok)
                break
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


#: The python-strftime tokens sqlglot canonicalizes date formats to that
#: _convert_date_format can round-trip to every engine model (the %-column of
#: _DATE_FMT_TOKENS). A format built only of these + literal characters is
#: reproducible; anything else (Oracle ``FF`` fractional, a locale ``Month``/
#: ``Day`` name sqlglot left un-canonicalized) is not, and must degrade.
# NB: ``%W`` (python week-of-year, e.g. Oracle ``WW``) is deliberately absent —
# week numbering is not portable (engines disagree on the first week/day and
# MySQL's ``%W`` means the weekday NAME), so it must degrade rather than emit a
# silently wrong weekday. The weekday name travels as ``%A``.
_KNOWN_PY_FMT_TOKENS = frozenset(
    {"%Y", "%y", "%B", "%b", "%H", "%I", "%m", "%d", "%M", "%S", "%a", "%p"}
)
_PY_FMT_TOKEN_RE = re.compile(r"%.")


def _date_fmt_reproducible(pyfmt: str) -> bool:
    """Whether a python-model date format is composed only of tokens every
    engine can reproduce (no FF fractional, no un-canonicalized locale name)."""
    tokens = _PY_FMT_TOKEN_RE.findall(pyfmt)
    # No ``%`` field at all → not a date format (a number mask like ``9,999.99``
    # or a bare literal); it must not be routed through the date-format path.
    if not tokens or any(t not in _KNOWN_PY_FMT_TOKENS for t in tokens):
        return False
    # Remove the % tokens and any ``"…"`` quoted literal run (which round-trips:
    # kept quoted on Oracle/PG/.NET, stripped bare on MySQL). Any letter left is
    # a bare literal (MySQL's ``%Y-%m-%dT…``) that Oracle/PG would reject
    # unquoted, or a token sqlglot could not map (``Month``/``FF``) — not
    # reproducible, so degrade honestly instead of shipping a wrong value.
    stripped = re.sub(r'"[^"]*"', "", _PY_FMT_TOKEN_RE.sub("", pyfmt))
    return not re.search(r"[A-Za-z]", stripped)


_ISO_DT_LITERAL_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)?"
)


def _number_mask_spec(mask: object) -> tuple[int, bool] | None:
    """``(decimal_count, has_grouping)`` for a *reproducible* numeric format —
    plain digit grouping and a fixed number of decimals, which every engine can
    render. ``None`` for a mask with no cross-engine equivalent: currency (``L``
    / ``$``), hex (``X``), Roman (``RN``), angle-bracket negatives (``PR``),
    scientific (``EEEE``), or a locale culture name."""
    m = str(mask).strip().upper()
    dotnet = re.fullmatch(r"([NF])(\d+)", m)  # .NET N2 (grouped) / F2 (plain)
    if dotnet:
        return (int(dotnet.group(2)), dotnet.group(1) == "N")
    if re.fullmatch(r"\d+", m):  # MySQL FORMAT(x, n) — always grouped
        return (int(m), True)
    if re.search(r"[LXCU$%]|RN|PR|EEEE|\bV\b|FM.*FM", m):
        return None
    if not re.fullmatch(r"[90GD,.SMI ]+", m):  # only grouping/decimal/sign tokens
        return None
    grouping = "G" in m or "," in m
    dec = re.search(r"[D.]([90]*)", m)  # digits after the decimal point
    return (len(dec.group(1)) if dec else 0, grouping)


def _oracle_number_mask(decimals: int, grouping: bool) -> str:
    """Build an Oracle/PG ``TO_CHAR`` numeric mask for the given spec (``FM``
    trims the sign/pad space; ``990`` forces a leading zero for values < 1)."""
    intpart = "999G999G999G990" if grouping else "9999999990"
    return f"FM{intpart}" + (f"D{'0' * decimals}" if decimals else "")


def _as_datetime_literal(node: ASTNode, dialect: str) -> str | None:
    """The target's ANSI date/timestamp literal (or CAST) for a *constant*
    ISO date/datetime — a string ``Literal``, or the ``STR_TO_TIME`` wrapper
    sqlglot models a ``TIMESTAMP '…'`` / ``TO_TIMESTAMP('…', mask)`` as. ``None``
    when *node* is not such a constant (e.g. a column or expression)."""
    lit: str | None = None
    if isinstance(node, Literal) and isinstance(node.value, str):
        lit = node.value.strip()
    elif (
        isinstance(node, FunctionCall)
        # sqlglot's canonical wrappers for a string → date/timestamp value.
        and node.name.upper()
        in ("STR_TO_TIME", "TS_OR_DS_TO_TIMESTAMP", "TS_OR_DS_TO_DATE")
        and node.args
        and isinstance(node.args[0], Literal)
        and isinstance(node.args[0].value, str)
    ):
        lit = node.args[0].value.strip()
    if lit is None or not _ISO_DT_LITERAL_RE.fullmatch(lit):
        return None
    is_date = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", lit))
    if dialect in ("oracle", "postgresql"):
        return f"DATE '{lit}'" if is_date else f"TIMESTAMP '{lit}'"
    if dialect == "tsql":
        return f"CAST('{lit}' AS {'DATE' if is_date else 'DATETIME2'})"
    if is_date:
        return f"CAST('{lit}' AS DATE)"
    # MySQL DATETIME has no sub-second precision — DATETIME(6) keeps a fractional.
    return (
        f"CAST('{lit}' AS DATETIME(6))" if "." in lit else f"CAST('{lit}' AS DATETIME)"
    )


def _portable_type_name(name: str, dialect: str) -> str:
    """Map a data-type name to the target dialect's equivalent.

    Falls back to the original name when no mapping is needed. Some mappings
    (e.g. UNIQUEIDENTIFIER -> CHAR(36)) carry their own length, in which case
    the caller's parameter list should be empty; these are types that don't
    take a user-supplied length here.
    """
    return _TYPE_NAME_MAP.get(dialect, {}).get(name.upper(), name)


def _portable_types_in_sql(sql: str, dialect: str) -> str:
    """Replace non-portable type names in raw emitted SQL for ``dialect``.

    Used for passthrough DDL (e.g. CREATE TABLE handled by sqlglot) where
    column types aren't routed through our own emitter. Word-boundary,
    case-insensitive replacement; types that carry their own length in the
    map (e.g. CHAR(36)) only substitute the bare name, so an existing
    ``(n)`` after it would be left — acceptable since those source types
    (UNIQUEIDENTIFIER/UUID) don't take a user length.
    """
    # A bare VARBINARY (Oracle LONG RAW / unsized RAW through the name map)
    # needs a length on MySQL and silently defaults tiny elsewhere; the
    # unsized source form is unbounded, so the LOB type is faithful.
    if dialect == "mysql":
        sql = re.sub(r"(?i)\bVARBINARY\b(?!\s*\()", "LONGBLOB", sql)
    elif dialect == "tsql":
        sql = re.sub(r"(?i)\bVARBINARY\b(?!\s*\()", "VARBINARY(MAX)", sql)
    mapping = _TYPE_NAME_MAP.get(dialect, {})
    if not mapping:
        return sql
    for src, dst in mapping.items():
        # Replace the bare type name not already followed by '2' (avoid
        # turning VARCHAR into VARCHAR2 twice) — handled by word boundary.
        # A (MAX) marker is part of the type itself (VARCHAR alone means
        # VARCHAR(1) in DDL), unlike a numeric length the source may carry.
        dst_name = dst if dst.upper().endswith("(MAX)") else dst.split("(")[0]
        sql = re.sub(rf"(?i)\b{re.escape(src)}\b", dst_name, sql)
    return sql


def emit_sql(nodes: list[ASTNode], dialect: str) -> str:
    """Emit IR nodes as SQL text for the given dialect.

    This is the shared emitter that handles common patterns. Dialect-specific
    emitters may override individual node handling.

    Args:
        nodes: IR nodes to emit.
        dialect: Target dialect name.

    Returns:
        Formatted SQL text.
    """
    parts: list[tuple[str, bool]] = []
    for node in nodes:
        sql = emit_node(node, dialect)
        if sql:
            parts.append((sql, isinstance(node, CommentStatement)))
    if not parts:
        return ""
    # T-SQL separates batches with GO and does not terminate statements with
    # ';'. Other dialects use ';' as the statement terminator. A preserved
    # comment glues to the following statement with a newline (no ';'/GO after
    # it), so it reads as that statement's leading comment.
    separator = "\nGO\n\n" if dialect == "tsql" else ";\n\n"
    pieces = [parts[0][0]]
    for i in range(1, len(parts)):
        prev_is_comment = parts[i - 1][1]
        text = parts[i][0]
        pieces.append(("\n" if prev_is_comment else separator) + text)
    return "".join(pieces)


def _comment_block(sql: str) -> str:
    """Comment out every line of *sql* (``-- `` prefix).

    Degraded passthroughs must comment the whole statement: prefixing only
    the first line leaves the remaining lines as raw source SQL, executable
    and invalid on the target.
    """
    return "\n".join(f"-- {ln}" if ln.strip() else "--" for ln in sql.splitlines())


def _cte_dml_unsupported(sql: str, read: str, dialect: str) -> str | None:
    """Why a WITH-clause UPDATE/DELETE cannot run on *dialect* (None = it can).

    T-SQL lets a statement update through its CTE (``WITH x AS (SELECT ...)
    UPDATE x SET ...``); nothing else does. Oracle additionally has no WITH
    clause on UPDATE/DELETE at all.
    """
    try:
        expr = sqlglot.parse_one(sql, read=read)
    except Exception:  # noqa: BLE001 - let the generic path handle it
        return None
    with_clause = expr.args.get("with") or expr.args.get("with_")
    if with_clause is None:
        return None
    # A DML body INSIDE a CTE (``WITH ins AS (INSERT … RETURNING) SELECT``)
    # is PostgreSQL-only — checked before the T-SQL early-out below, which
    # covers the inverse shape (updating THROUGH a CTE).
    if any(
        isinstance(c.this, (exp.Insert, exp.Update, exp.Delete))
        for c in with_clause.expressions
    ):
        if dialect == "postgresql":
            return None
        return (
            "data-modifying CTEs (WITH x AS (INSERT/UPDATE/DELETE … RETURNING)) are "
            "PostgreSQL-only; run the DML separately and read its result from a table."
        )
    if dialect == "tsql":
        return None
    cte_names = {c.alias_or_name.lower() for c in with_clause.expressions}
    target = expr.this
    target_name = target.name.lower() if isinstance(target, exp.Table) else ""
    if target_name in cte_names:
        return (
            f"{dialect} cannot update through a CTE; rewrite as a MERGE or a "
            "correlated UPDATE joined on the table's key."
        )
    if dialect == "oracle":
        return (
            "Oracle has no WITH clause on UPDATE/DELETE; inline the CTE as a subquery "
            "or rewrite as a MERGE."
        )
    return None


_ORACLE_MODIFY_RE = re.compile(
    r"(?is)^\s*ALTER\s+TABLE\s+(?P<table>[\w.\"]+)\s+MODIFY\s+(?:\((?P<parenspec>.+)\)|(?P<spec>[^;]+?))\s*;?\s*$"
)
_MODIFY_COL_RE = re.compile(
    r"(?is)^(?P<col>[\w\"]+)\s*(?P<type>(?!NOT\b|NULL\b)[A-Za-z]\w*(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)?\s*(?P<null>NOT\s+NULL|NULL)?$"
)


def rewrite_oracle_modify(sql: str, dialect: str) -> str | None:
    """Rewrite Oracle's ``ALTER TABLE t MODIFY [(]col type [NULL]...[)]`` for
    *dialect* (sqlglot parses neither form — the statement leaked verbatim).

    Returns None when the statement is not that shape or a column spec is
    more complex than ``col [type] [NOT NULL|NULL]`` (defaults, constraints).
    """
    if dialect == "oracle":
        return None
    m = _ORACLE_MODIFY_RE.match(sql)
    if not m:
        return None
    table = m.group("table")
    spec_text = m.group("parenspec") or m.group("spec") or ""
    actions: list[str] = []
    for spec in _split_top_level_commas(spec_text):
        cm = _MODIFY_COL_RE.match(spec.strip())
        if not cm:
            return None
        col = cm.group("col")
        ctype = cm.group("type") or ""
        if ctype:
            ctype = _portable_types_in_sql(ctype, dialect)
        nullability = (cm.group("null") or "").upper()
        nullability = re.sub(r"\s+", " ", nullability)
        if not ctype and not nullability:
            return None
        if dialect == "tsql":
            if not ctype:
                # T-SQL's ALTER COLUMN requires the type for a nullability
                # change; without it there is no faithful single statement.
                return None
            suffix = f" {nullability}" if nullability else ""
            actions.append(f"ALTER COLUMN {col} {ctype}{suffix}")
        elif dialect == "postgresql":
            if ctype:
                actions.append(f"ALTER COLUMN {col} TYPE {ctype}")
            if nullability == "NOT NULL":
                actions.append(f"ALTER COLUMN {col} SET NOT NULL")
            elif nullability == "NULL":
                actions.append(f"ALTER COLUMN {col} DROP NOT NULL")
        else:  # mysql keeps MODIFY but needs the full definition
            if not ctype:
                return None
            suffix = f" {nullability}" if nullability else ""
            actions.append(f"MODIFY COLUMN {col} {ctype}{suffix}")
    if not actions:
        return None
    if dialect == "tsql":
        # One action per statement (T-SQL allows a single ALTER COLUMN).
        return ";\n".join(f"ALTER TABLE {table} {a}" for a in actions) + ";"
    return f"ALTER TABLE {table} " + ", ".join(actions) + ";"


def _oracle_merge_paren_on(sql: str) -> str:
    """Wrap a MERGE's ON condition in the parentheses Oracle requires.

    Scans at paren depth 0 (quote-aware) for the ``ON`` that follows USING and
    the ``WHEN`` that ends the condition, so an ON inside the USING subquery
    (a JOIN) is never touched.
    """
    depth = 0
    in_str = False
    on_at = when_at = None
    i = 0
    upper = sql.upper()
    while i < len(sql):
        ch = sql[i]
        if in_str:
            if ch == "'":
                in_str = False
        elif ch == "'":
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and upper.startswith(" ON ", i):
            if on_at is None:
                on_at = i
        elif depth == 0 and on_at is not None and upper.startswith(" WHEN ", i):
            when_at = i
            break
        i += 1
    if on_at is None or when_at is None:
        return sql
    cond = sql[on_at + 4 : when_at].strip()
    if cond.startswith("(") and cond.endswith(")"):
        return sql
    return f"{sql[:on_at]} ON ({cond}){sql[when_at:]}"


def _merge_delete_reads_updated(
    cond: exp.Expression, target_alias: str, assigned: set[str]
) -> bool:
    """True when the DELETE-relevant condition references a target column the
    UPDATE assigns. Oracle evaluates ``DELETE WHERE`` against *post-update*
    values, so such a fold would delete rows T-SQL keeps (audit N2)."""
    for col in cond.find_all(exp.Column):
        if col.name.lower() not in assigned:
            continue
        tbl = col.args.get("table")
        tbl_name = tbl.name.lower() if tbl is not None else None
        # A column qualified with the target alias, or an unqualified column
        # (which binds to the target in the DELETE), reads the updated row.
        if tbl_name in (target_alias, None):
            return True
    return False


def _merge_extended_clauses(
    tree: exp.Merge, dialect: str
) -> tuple[list[str], str | None, str | None]:
    """T-SQL's extended MERGE clause set on targets that lack it (in place).

    ``WHEN NOT MATCHED BY SOURCE`` exists nowhere else (PostgreSQL only from
    17): each such clause becomes a follow-up UPDATE/DELETE over the same join
    predicate as an anti-join — the rows it addresses cannot be touched by the
    remaining MERGE, so the two-statement split is value-equivalent.

    Oracle additionally allows a single unconditional WHEN MATCHED clause; its
    conditional forms are spelled ``UPDATE … WHERE`` / ``DELETE WHERE`` (no
    sqlglot grammar). A conditional UPDATE/DELETE pair folds into one
    unconditional UPDATE whose SET keeps the old value via CASE — Oracle's
    DELETE WHERE only examines *updated* rows, so the update must cover every
    matched row — plus a ``DELETE WHERE`` tail spliced after emission (second
    return value). First-match-wins order decides each action's condition.

    The third return value is a degrade reason (or ``None``): when the fold
    would be value-unsafe (the DELETE condition reads a column the UPDATE
    assigns — Oracle would evaluate it against post-update values), the whole
    MERGE degrades to a carrier + warning rather than ship silently wrong rows.
    """
    whens = tree.args.get("whens")
    using = tree.args.get("using")
    on = tree.args.get("on")
    if whens is None or using is None or on is None:
        return [], None, None
    wd = sqlglot_dialect_name(dialect)
    exprs = list(whens.expressions)
    followups: list[str] = []
    tgt_sql = tree.this.sql(dialect=wd)
    for w in [x for x in exprs if x.args.get("source")]:
        anti = (
            f"NOT EXISTS (SELECT 1 FROM {using.sql(dialect=wd)} WHERE "
            f"{on.sql(dialect=wd)})"
        )
        cond = w.args.get("condition")
        if cond is not None:
            anti += f" AND ({cond.sql(dialect=wd)})"
        then = w.args.get("then")
        if isinstance(then, exp.Update):
            sets = ", ".join(e.sql(dialect=wd) for e in then.expressions)
            followups.append(f"UPDATE {tgt_sql} SET {sets} WHERE {anti}")
        elif isinstance(then, exp.Var) and str(then.this).upper() == "DELETE":
            followups.append(f"DELETE FROM {tgt_sql} WHERE {anti}")
        else:
            return [], None, None
        exprs.remove(w)
    delete_where: str | None = None
    matched = [w for w in exprs if w.args.get("matched")]
    if dialect == "oracle" and (
        len(matched) > 1 or any(w.args.get("condition") for w in matched)
    ):
        updates = [w for w in matched if isinstance(w.args.get("then"), exp.Update)]
        deletes = [
            w
            for w in matched
            if isinstance(w.args.get("then"), exp.Var)
            and str(w.args["then"].this).upper() == "DELETE"
        ]
        if len(updates) == 1 and len(deletes) <= 1 and len(matched) <= 2:
            upd, dlt = updates[0], deletes[0] if deletes else None
            uc = upd.args.get("condition")
            dc = dlt.args.get("condition") if dlt is not None else None

            def _not_and(
                base: exp.Expression, extra: exp.Expression | None
            ) -> exp.Expression:
                inv = exp.Not(this=exp.Paren(this=base.copy()))
                if extra is None:
                    return inv
                return exp.And(this=inv, expression=exp.Paren(this=extra.copy()))

            if dlt is None:
                u_active, d_active = uc, None
            elif matched[0] is dlt:
                # DELETE(dc) wins first; UPDATE applies to the rest.
                u_active, d_active = _not_and(dc, uc) if dc is not None else None, dc
            else:
                u_active, d_active = uc, _not_and(uc, dc) if uc is not None else dc
            target_alias = (tree.this.alias or tree.this.name).lower()
            assigned = {
                eq.this.name.lower()
                for eq in upd.args["then"].expressions
                if isinstance(eq, exp.EQ) and isinstance(eq.this, exp.Column)
            }
            if d_active is not None and _merge_delete_reads_updated(
                d_active, target_alias, assigned
            ):
                # Unsafe fold: Oracle's DELETE WHERE would read post-update
                # values. Degrade the whole MERGE (carrier + warning).
                return (
                    [],
                    None,
                    (
                        "conditional DELETE in MERGE reads a column the UPDATE "
                        "assigns; Oracle evaluates DELETE WHERE against post-update "
                        "values, which would delete rows the source keeps — rewrite "
                        "the MERGE manually"
                    ),
                )
            if u_active is not None:
                alias = tree.this.alias or tree.this.name
                then_upd = upd.args["then"]
                for eq in then_upd.expressions:
                    keep = exp.column(eq.this.name, table=alias)
                    eq.set(
                        "expression",
                        exp.Case(
                            ifs=[
                                exp.If(this=u_active.copy(), true=eq.expression.copy())
                            ],
                            default=keep,
                        ),
                    )
            upd.set("condition", None)
            if d_active is not None:
                delete_where = d_active.sql(dialect=wd)
            if dlt is not None:
                exprs.remove(dlt)
    whens.set("expressions", exprs)
    return followups, delete_where, None


def _merge_carve_do_nothing(tree: exp.Merge) -> str | None:
    """Lower PG's ``THEN DO NOTHING`` merge action for targets that lack it
    (T-SQL / Oracle) by clause carve-out. First-match-wins makes
    ``WHEN <kind> AND c THEN DO NOTHING`` equivalent to adding ``AND NOT (c)``
    to every *later* clause of the same match kind; an unconditional
    ``DO NOTHING`` makes all later same-kind clauses unreachable (drop them).

    Modifies ``tree.args["whens"]`` in place. Returns a degrade reason for a
    ``Var`` action that is neither DELETE nor DO NOTHING (a future sqlglot
    merge action we do not model), or when the carve-out empties the clause
    list; otherwise ``None``.
    """
    whens = tree.args.get("whens")
    if whens is None:
        return None
    exprs = list(whens.expressions)

    def _then_var(w: exp.When) -> str | None:
        then = w.args.get("then")
        if isinstance(then, exp.Var):
            return str(then.this).strip().upper()
        return None

    for w in exprs:
        name = _then_var(w)
        if name is not None and name not in ("DELETE", "DO NOTHING"):
            return (
                f"MERGE action '{w.args['then'].this}' has no equivalent on "
                "this target; rewrite the MERGE manually"
            )

    def _kind(w: exp.When) -> tuple[bool, bool]:
        return bool(w.args.get("matched")), bool(w.args.get("source"))

    to_remove: set[int] = set()
    for idx, w in enumerate(exprs):
        if id(w) in to_remove or _then_var(w) != "DO NOTHING":
            continue
        to_remove.add(id(w))
        cond = w.args.get("condition")
        kind = _kind(w)
        for later in exprs[idx + 1 :]:
            if _kind(later) != kind:
                continue
            if cond is None:
                to_remove.add(id(later))
            else:
                neg = exp.Not(this=exp.Paren(this=cond.copy()))
                existing = later.args.get("condition")
                later.set(
                    "condition",
                    (
                        neg
                        if existing is None
                        else exp.And(this=exp.Paren(this=existing), expression=neg)
                    ),
                )
    kept = [w for w in exprs if id(w) not in to_remove]
    if not kept:
        return (
            "MERGE reduces to no action after DO NOTHING carve-out; rewrite the MERGE "
            "manually"
        )
    whens.set("expressions", kept)
    return None


def _collect_defined_aliases(value: object) -> set[str]:
    """Aliases the statement itself defines (table/derived-table aliases):
    the temp-table QUALIFIER rename must not fire on them — ``(SELECT …) y``
    is the statement's own name even when a temp table ``y`` exists."""
    found: set[str] = set()
    if isinstance(value, TableRef) and value.alias:
        found.add(value.alias.lower())
    if isinstance(value, SubqueryExpression) and value.alias:
        found.add(value.alias.lower())
    if isinstance(value, CTEDefinition) and value.name:
        # A CTE name shadows any same-named (temp) table inside the
        # statement — references bind to the CTE.
        found.add(value.name.lower())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            found |= _collect_defined_aliases(getattr(value, f.name))
    elif isinstance(value, tuple):
        for item in value:
            found |= _collect_defined_aliases(item)
    return found


def emit_node(node: ASTNode, dialect: str) -> str:
    """Emit a single IR node as SQL text."""
    token = DEFINED_ALIASES.set(frozenset(_collect_defined_aliases(node)))
    try:
        return _emit_node_inner(node, dialect)
    finally:
        DEFINED_ALIASES.reset(token)


def _emit_node_inner(node: ASTNode, dialect: str) -> str:
    if isinstance(node, CommentStatement):
        # A preserved source comment, re-emitted verbatim (text keeps its
        # ``--`` / ``/* */`` delimiters).
        return node.text
    if isinstance(node, SelectStatement):
        return _emit_select(node, dialect)
    if isinstance(node, InsertStatement):
        return _emit_insert(node, dialect)
    if isinstance(node, UpdateStatement):
        return _emit_update(node, dialect)
    if isinstance(node, DeleteStatement):
        return _emit_delete(node, dialect)
    if isinstance(node, CreateTableStatement):
        return _emit_create_table(node, dialect)
    if isinstance(node, CreateViewStatement):
        return _emit_create_view(node, dialect)
    if isinstance(node, DropStatement):
        return _emit_drop(node, dialect)
    if isinstance(node, RawSQL):
        if (
            node.reason.startswith("Unhandled expression type: UPDATE FROM")
            and SOURCE_DIALECT.get() == dialect
        ):
            # Valid, merely unmodeled source SQL is verbatim on its own
            # engine (wave 193) — the carrier is for cross-dialect only.
            return node.sql
        # The reason can be a multi-line sqlglot ParseError (source excerpt +
        # ANSI highlighting); embedded raw it would leak its lines 2+ as
        # executable text after the ``--`` prefix — flatten it to one clean
        # line so the carrier stays a comment.
        reason = re.sub(r"\x1b\[[0-9;]*m", "", node.reason)
        reason = " ".join(reason.split())
        return f"-- UNIQUE-1003: {reason}\n{_comment_block(node.sql)}"
    if isinstance(node, PassthroughSQL):
        return _emit_passthrough(node, dialect)
    if isinstance(node, Script):
        sep = "\nGO\n\n" if dialect == "tsql" else ";\n\n"
        return sep.join(emit_node(s, dialect) for s in node.statements)

    # Expression-level emission
    return _emit_expression(node, dialect)


def _ident_if_plain(name: str, dialect: str) -> str:
    """Quote a bare column name when it is a reserved word in *dialect*
    (``INSERT INTO t (a, manual)`` is a 1064 on MySQL 8.4). Dotted/quoted
    forms pass through untouched."""
    if re.fullmatch(r"\w+", name):
        return _ident(name, False, dialect)
    return name


def _quote_reserved_identifiers(expr: exp.Expression, dialect: str) -> exp.Expression:
    """Mark identifiers that are reserved words in *dialect* as quoted, so a
    passthrough CREATE INDEX / ALTER on a reserved name emits valid SQL."""
    reserved = _RESERVED_IDENTIFIERS.get(dialect, frozenset())
    if reserved:
        for ident in expr.find_all(exp.Identifier):
            if not ident.args.get("quoted") and str(ident.this).upper() in reserved:
                ident.set("quoted", True)
    return expr


def _tsql_index_predicate(pred: exp.Expression) -> str | None:
    """Render a filtered-index predicate in T-SQL's restricted grammar (None
    outside it; the caller falls back). IS NOT NULL arrives as ``Not(Is(…))``
    (sqlglot ≤30.11) or ``Is(…, negate=True)`` (30.12+ — unread, the negate
    inverts the predicate; 2026-07-30) and must spell ``x IS NOT NULL``."""
    if (
        isinstance(pred, exp.Not)
        and isinstance(pred.this, exp.Is)
        and isinstance(pred.this.expression, exp.Null)
    ):
        return f"{pred.this.this.sql(dialect='tsql')} IS NOT NULL"
    if isinstance(pred, exp.Is) and isinstance(pred.expression, exp.Null):
        negated = " NOT" if pred.args.get("negate") else ""
        return f"{pred.this.sql(dialect='tsql')} IS{negated} NULL"
    if isinstance(pred, exp.And):
        left = _tsql_index_predicate(pred.this)
        right = _tsql_index_predicate(pred.expression)
        if left and right:
            return f"{left} AND {right}"
        return None
    if isinstance(pred, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.NEQ)):
        # Only plain column-vs-constant comparisons are legal there —
        # arithmetic left sides are error 10735.
        if isinstance(pred.this, exp.Column) and isinstance(
            pred.expression, (exp.Literal, exp.Null, exp.Boolean)
        ):
            return str(pred.sql(dialect="tsql"))
        return None
    return None


def _balanced_outer(text: str) -> bool:
    """Whether the leading ``(`` of *text* closes at its final char."""
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(text) - 1
    return False


def _carry_index_nulls_order(source_sql: str, result: str, dialect: str) -> str:
    """Surface a dropped ``NULLS FIRST/LAST`` index-column ordering as a carrier.

    Oracle rejects it in an index (ORA-00907) and T-SQL/MySQL have no such
    clause, so sqlglot drops it. It affects only the index's physical null
    ordering, never query results, so a carrier (mirrored to a warning) is the
    faithful outcome rather than a silent drop.
    """
    nulls = re.compile(r"(?i)\bNULLS\s+(?:FIRST|LAST)\b")
    if nulls.search(source_sql) and not nulls.search(result):
        return (
            f"-- UNIQUE-1004: NULLS FIRST/LAST index ordering has no {dialect} "
            "equivalent; dropped (it affects only the index's physical null "
            "order, not query results)\n" + result
        )
    return result


def _pg_index_rebuild(sql: str, read: str, dialect: str) -> str | None:
    """Rebuild a PostgreSQL CREATE INDEX as valid T-SQL/MySQL, or None
    to let the generic sqlglot path try (expression indexes, exotic
    shapes). Both targets require an index NAME; MySQL has no filtered
    indexes at all, T-SQL only a restricted predicate grammar."""
    # A physical-clause note from a prior T-SQL->PG pass (CLUSTERED /
    # WITH (...) / ON <fg>) must survive the rebuild: extract it before
    # parsing and re-inject its pieces below (round-trip contract).
    physical_kw = ""
    trailing = ""
    note = re.search(
        r"(?is)\s*/\*\s*UNIQUE(?:-\d{4})?:\s*(?P<clauses>.+?)\s*--\s*tsql-only,[^*]*?"
        r"physical index clause[^*]*?\*/",
        sql,
    )
    if note:
        sql = (sql[: note.start()] + sql[note.end() :]).strip()
        clauses = note.group("clauses").strip()
        lead = re.match(r"(?i)(?P<kw>(?:NON)?CLUSTERED)\b\s*(?P<rest>.*)$", clauses)
        if lead:
            physical_kw = lead.group("kw") + " "
            trailing = lead.group("rest").strip()
        else:
            trailing = clauses
    try:
        tree = sqlglot.parse_one(sql, read=read)
    except Exception:
        return None
    if not isinstance(tree, exp.Create):
        return None
    index = tree.this
    if not isinstance(index, exp.Index):
        return None
    params = index.args.get("params")
    ordered = list(params.args.get("columns") or []) if params else []
    cols: list[str] = []
    for o in ordered:
        inner = o.this
        # A PG operator class (roomno bpchar_ops) is a PG-only concept:
        # keep the column, drop the opclass.
        if isinstance(inner, exp.Opclass):
            inner = inner.this
        if not isinstance(inner, exp.Column):
            if dialect == "mysql":
                # MySQL 8 functional index parts take DOUBLE parens
                # (wave 204: single-paren expressions were 1064).
                expr_sql = str(inner.sql(dialect="mysql")).strip()
                while (
                    expr_sql.startswith("(")
                    and expr_sql.endswith(")")
                    and _balanced_outer(expr_sql)
                ):
                    expr_sql = expr_sql[1:-1].strip()
                col = f"({expr_sql})"
                if o.args.get("desc"):
                    col += " DESC"
                cols.append(col)
                continue
            # T-SQL has no expression indexes (computed columns needed);
            # a whole carrier beats invalid output.
            reason = (
                "T-SQL has no expression indexes (add a computed column and index it); "
                "statement preserved as a comment"
            )
            body = "\n".join(f"-- {line}" for line in sql.strip().splitlines())
            return f"-- UNIQUE-1005: {reason}\n{body}"
        col = str(inner.sql(dialect="mysql" if dialect == "mysql" else "tsql"))
        if o.args.get("desc"):
            col += " DESC"
        cols.append(col)
    if not cols:
        return None
    table = index.args.get("table")
    if table is None:
        return None
    write = "mysql" if dialect == "mysql" else "tsql"
    table_sql = str(table.sql(dialect=write))
    name = str(index.this.sql(dialect=write)) if index.this else ""
    if not name:
        pieces = [re.sub(r"\W+", "", table_sql)] + [
            re.sub(r"\W+", "", c) for c in cols[:3]
        ]
        name = "_".join(p for p in pieces if p) + "_idx"
    unique = "UNIQUE " if tree.args.get("unique") else ""
    where = params.args.get("where") if params else None
    where_sql = ""
    dropped_where = ""
    if where is not None:
        rendered = _tsql_index_predicate(where.this) if dialect == "tsql" else None
        if rendered is None:
            # Outside T-SQL's filtered-index grammar (error 10735). A
            # broader UNIQUE index would reject rows the partial one
            # allowed — degrade whole; a plain index just gets bigger.
            if tree.args.get("unique"):
                reason = (
                    f"partial UNIQUE index predicate has no {dialect} "
                    "filtered-index form; statement preserved as a comment"
                )
                body = "\n".join(f"-- {line}" for line in sql.strip().splitlines())
                return f"-- UNIQUE-1006: {reason}\n{body}"
            dropped_where = (
                "\n-- UNIQUE-1007: partial-index predicate dropped (no "
                f"{dialect} filtered-index form); the index is broader than the "
                f"source's: {where.this.sql(dialect=write)}"
            )
        else:
            where_sql = f" WHERE {rendered}"
    stmt = (
        f"CREATE {unique}{physical_kw}INDEX {name} ON {table_sql} "
        f"({', '.join(cols)}){where_sql}"
    )
    if trailing:
        stmt += f" {trailing}"
    if dropped_where:
        stmt += dropped_where
    if unique and not where_sql and dialect == "tsql":
        return (
            f"{stmt};\n-- UNIQUE-1008: PostgreSQL unique indexes treat NULLs as "
            "distinct; T-SQL allows a single NULL per unique index"
        )
    return stmt


_COMPARISON_OPS = frozenset(
    {
        BinaryOperator.IS,
        BinaryOperator.EQ,
        BinaryOperator.NEQ,
        BinaryOperator.LT,
        BinaryOperator.GT,
        BinaryOperator.LTE,
        BinaryOperator.GTE,
        BinaryOperator.LIKE,
        BinaryOperator.AND,
        BinaryOperator.OR,
        # IN/NOT IN in value position are predicates too (wave 195:
        # ``SELECT x IN (SELECT …)`` was 4145 on T-SQL).
        BinaryOperator.IN,
        BinaryOperator.NOT_IN,
    }
)

_COMPARISON_NEGATION = {
    BinaryOperator.IS: "IS NOT",
    BinaryOperator.EQ: "<>",
    BinaryOperator.NEQ: "=",
    BinaryOperator.LT: ">=",
    BinaryOperator.GT: "<=",
    BinaryOperator.LTE: ">",
    BinaryOperator.GTE: "<",
}


def _emit_value_expression(node: ASTNode, dialect: str) -> str:
    """Emit a select-list item; predicates become tri-state values.

    MySQL comparisons ARE values (1/0/NULL); T-SQL/Oracle reject a
    predicate in value position. ``CASE WHEN p THEN 1 WHEN not-p THEN 0
    END`` reproduces the tri-state exactly (ELSE NULL implicit)."""
    inner = node.expression if isinstance(node, Alias) else node
    # ``<predicate> IS TRUE/FALSE`` / ``= 1/0`` in value position: normalize to the
    # predicate (or its negation) first, so the CASE wrap below emits a valid
    # condition instead of ``<pred> IS 1`` (T-SQL/Oracle have no boolean value).
    if dialect in ("tsql", "oracle"):
        _norm_pred = _predicate_int_comparison(inner)
        if _norm_pred is not None:
            inner = _norm_pred
    if (
        dialect in ("tsql", "oracle")
        and isinstance(inner, BinaryOp)
        and inner.operator in (BinaryOperator.NULLSAFE_EQ, BinaryOperator.NULLSAFE_NEQ)
    ):
        # _emit_binary returns the predicate spelling "CASE … END = 1";
        # the value position keeps just the CASE (never NULL, so the
        # two-armed form is already exact).
        wrapped = _emit_binary(inner, dialect)
        m = re.fullmatch(r"(CASE WHEN .+ THEN 1 ELSE 0 END) = 1", wrapped, re.S)
        value = m.group(1) if m else wrapped
        if isinstance(node, Alias):
            return f"{value} AS {_ident(node.name, node.quoted, dialect)}"
        return value
    if (
        dialect in ("tsql", "oracle")
        and isinstance(inner, UnaryOp)
        and inner.operator
        in (
            UnaryOperator.IS_NULL,
            UnaryOperator.IS_NOT_NULL,
            UnaryOperator.EXISTS,
            UnaryOperator.NOT,
        )
    ):
        # A unary predicate in value position (``(id IS NOT NULL) AS a3``)
        # — 4145 on T-SQL/Oracle. IS [NOT] NULL and EXISTS are two-valued
        # (ELSE 0 exact); NOT keeps the tri-state two-WHEN form (wave 141).
        cond = _emit_condition(inner, dialect)
        if inner.operator == UnaryOperator.NOT:
            wrapped = f"CASE WHEN {cond} THEN 1 WHEN NOT ({cond}) THEN 0 END"
        else:
            wrapped = f"CASE WHEN {cond} THEN 1 ELSE 0 END"
        if isinstance(node, Alias):
            return f"{wrapped} AS {_ident(node.name, node.quoted, dialect)}"
        return wrapped
    if (
        dialect in ("tsql", "oracle")
        and isinstance(inner, BinaryOp)
        and inner.operator in (BinaryOperator.AND, BinaryOperator.OR)
    ):
        # A boolean AND/OR in value position: the CASE wrap must go
        # through _emit_condition so bare truthy operands comparisonize
        # (``WHEN b1 AND a3`` was 4145 — wave 141).
        cond = _emit_condition(inner, dialect)
        wrapped = f"CASE WHEN {cond} THEN 1 WHEN NOT ({cond}) THEN 0 END"
        if isinstance(node, Alias):
            return f"{wrapped} AS {_ident(node.name, node.quoted, dialect)}"
        return wrapped
    if (
        dialect == "tsql"
        and isinstance(inner, BinaryOp)
        and inner.operator in _COMPARISON_OPS
        and any(
            isinstance(side, UnaryOp)
            and side.operator == UnaryOperator.NOT
            and not isinstance(side.operand, (BinaryOp, UnaryOp, SubqueryExpression))
            for side in (inner.left, inner.right)
        )
    ):
        # T-SQL has no boolean value type, so NOT applied to a non-predicate
        # (``NOT NULL``, ``NOT col``) — as an operand of a comparison/IS — has no
        # T-SQL form (error 4145). Degrade the value to a documented carrier.
        carrier = (
            "NULL /* UNIQUE-1009: T-SQL has no boolean value type; NOT of a "
            "non-predicate (e.g. NOT NULL) has no equivalent -- see "
            "docs/03-unsupported.md */"
        )
        if isinstance(node, Alias):
            return f"{carrier} AS {_ident(node.name, node.quoted, dialect)}"
        return carrier
    if (
        dialect in ("tsql", "oracle")
        and isinstance(inner, BinaryOp)
        and inner.operator in _COMPARISON_OPS
    ):
        pred = _emit_binary(inner, dialect)
        neg_op = _COMPARISON_NEGATION.get(inner.operator)
        left = _emit_expression(inner.left, dialect)
        right = _emit_expression(inner.right, dialect)
        if neg_op is not None and _tuple_items(inner.left, left) is None:
            not_pred = f"{left} {neg_op} {right}"
        else:
            # Row-tuple operands must go through the pairwise expansion.
            not_pred = f"NOT ({pred})"
        wrapped = f"CASE WHEN {pred} THEN 1 WHEN {not_pred} THEN 0 END"
        if isinstance(node, Alias):
            alias = _ident(node.name, node.quoted, dialect)
            return f"{wrapped} AS {alias}"
        return wrapped
    return _emit_expression(node, dialect)


def _tuple_items(side: ASTNode, emitted: str) -> list[str] | None:
    """The comma items of a row-constructor operand, or None."""
    if isinstance(side, ExpressionList):
        return [_emit_expression(i, "tsql") for i in side.items]
    text = emitted.strip()
    m = re.match(r"(?is)^ROW\s*\((.*)\)$", text)
    if isinstance(side, (RawSQL, FunctionCall)) and m:
        inner = m.group(1)
        if "(" not in inner and "," in inner:
            return [p.strip() for p in inner.split(",")]
    if isinstance(side, RawSQL) and text.startswith("(") and text.endswith(")"):
        inner = text[1:-1]
        if "(" not in inner and "," in inner:
            return [p.strip() for p in inner.split(",")]
    return None


def _comparisonize_literals(node: ASTNode) -> ASTNode:
    """MySQL/PG treat a numeric operand of AND/OR as a truth value;
    T-SQL/Oracle need a real comparison — rewrite the literal to
    ``lit <> 0`` throughout the boolean tree."""
    if not (
        isinstance(node, BinaryOp)
        and node.operator in (BinaryOperator.AND, BinaryOperator.OR)
    ):
        return node

    def fix(side: ASTNode) -> ASTNode:
        if isinstance(side, Literal) and side.dtype in ("integer", "number"):
            return BinaryOp(
                operator=BinaryOperator.NEQ,
                left=side,
                right=Literal(value=0, dtype="integer"),
            )
        if isinstance(side, Literal) and side.dtype == "null":
            # A bare NULL truth value (``… OR NULL``): UNKNOWN on both
            # engines — ``NULL <> 0`` is the comparison spelling (wave
            # 170).
            return BinaryOp(
                operator=BinaryOperator.NEQ,
                left=side,
                right=Literal(value=0, dtype="integer"),
            )
        if isinstance(side, Literal) and side.dtype == "boolean":
            one = Literal(value=1, dtype="integer")
            return BinaryOp(
                operator=(BinaryOperator.EQ if side.value else BinaryOperator.NEQ),
                left=one,
                right=one,
            )
        # A bare column/function/subquery under AND/OR is PG/MySQL
        # truthiness — T-SQL/Oracle need the comparison (wave 135; the
        # top-of-WHERE case was handled, the nested one shipped bare).
        if isinstance(side, (ColumnRef, FunctionCall, SubqueryExpression)):
            return BinaryOp(
                operator=BinaryOperator.NEQ,
                left=side,
                right=Literal(value=0, dtype="integer"),
            )
        if (
            isinstance(side, UnaryOp)
            and side.operator == UnaryOperator.NOT
            and isinstance(side.operand, (ColumnRef, FunctionCall))
        ):
            return BinaryOp(
                operator=BinaryOperator.EQ,
                left=side.operand,
                right=Literal(value=0, dtype="integer"),
            )
        if isinstance(side, CaseExpression):
            # A CASE as a truth operand (``a = 1 AND CASE 1 WHEN a …``)
            # is MySQL truthiness too (wave 187).
            return BinaryOp(
                operator=BinaryOperator.NEQ,
                left=side,
                right=Literal(value=0, dtype="integer"),
            )
        return _comparisonize_literals(side)

    return dataclasses.replace(node, left=fix(node.left), right=fix(node.right))


def _strip_unlimited_order_by(query: SelectStatement) -> SelectStatement:
    """Drop ORDER BY (no LIMIT — it cannot change the result) from a
    subquery's select node and every arm of its set_query chain."""
    if query.set_query is not None:
        stripped = _strip_unlimited_order_by(query.set_query)
        if stripped is not query.set_query:
            query = dataclasses.replace(query, set_query=stripped)
    if query.order_by and not query.limit:
        query = dataclasses.replace(query, order_by=())
    return query


#: PG's function-style cast names and their generic type spellings.
_PG_FUNCTION_CASTS = {
    "FLOAT8": "DOUBLE",
    "FLOAT4": "REAL",
    "INT2": "SMALLINT",
    "INT4": "INT",
    "INT8": "BIGINT",
    "BOOL": "BOOLEAN",
    "NUMERIC": "NUMERIC",
}


#: Operators whose BinaryOp is a predicate (truth-valued), not a scalar.
_PREDICATE_OPERATORS = frozenset(
    {
        BinaryOperator.EQ,
        BinaryOperator.NEQ,
        BinaryOperator.LT,
        BinaryOperator.GT,
        BinaryOperator.LTE,
        BinaryOperator.GTE,
        BinaryOperator.AND,
        BinaryOperator.OR,
        BinaryOperator.LIKE,
        BinaryOperator.ILIKE,
        BinaryOperator.IN,
        BinaryOperator.NOT_IN,
        BinaryOperator.BETWEEN,
        BinaryOperator.IS,
        BinaryOperator.NULLSAFE_EQ,
        BinaryOperator.NULLSAFE_NEQ,
    }
)


def _is_predicate_node(v: ASTNode) -> bool:
    if isinstance(v, BinaryOp) and v.operator in _PREDICATE_OPERATORS:
        return True
    # sqlglot spells IS NOT NULL as NOT(IS NULL) — still a predicate.
    return (
        isinstance(v, UnaryOp)
        and v.operator == UnaryOperator.NOT
        and _is_predicate_node(v.operand)
    )


def _predicate_int_comparison(node: ASTNode) -> ASTNode | None:
    """Rewrite ``<predicate> = 1`` / ``= 0`` / ``IS TRUE`` / ``IS FALSE``
    (MySQL's boolean-as-number) to the predicate itself or its negation;
    None when the shape does not match."""
    is_predicate = _is_predicate_node

    if not (
        isinstance(node, BinaryOp)
        and node.operator in (BinaryOperator.EQ, BinaryOperator.NEQ, BinaryOperator.IS)
        and isinstance(node.right, Literal)
        and is_predicate(node.left)
    ):
        return None
    if node.right.dtype == "integer" and node.right.value in (0, 1):
        right_true = node.right.value == 1
    elif node.right.dtype == "boolean":
        right_true = bool(node.right.value)
    else:
        return None
    truthy = right_true == (node.operator != BinaryOperator.NEQ)
    if truthy:
        return node.left
    return UnaryOp(operator=UnaryOperator.NOT, operand=node.left)


def _emit_condition(node: ASTNode, dialect: str) -> str:
    """Emit an expression in condition position.

    T-SQL has no boolean type in predicates: PG's bare boolean literal
    condition (``JOIN b ON true``, ``WHERE false``) mapped to ``ON 1``,
    which is error 4145 — it must be a real comparison. Null-safe
    comparisons emit their bare predicate here (the value position
    wraps them in CASE)."""
    if dialect == "tsql" and isinstance(node, Literal) and node.dtype == "boolean":
        return "1 = 1" if node.value else "1 = 0"
    if (
        dialect == "postgresql"
        and isinstance(node, Literal)
        and node.dtype in ("integer", "number")
    ):
        # PG's CASE/WHERE demand a boolean too — MySQL's numeric
        # truthiness (``CASE WHEN 1``) is error 42804 there (wave 176).
        return f"{_emit_expression(node, dialect)} <> 0"
    if dialect in ("tsql", "oracle"):
        if isinstance(node, Literal) and node.dtype in ("integer", "number", "null"):
            # MySQL truthiness again: a bare numeric literal condition
            # (``CASE WHEN 1``, ``IF(1, …)``) is error 4145 on T-SQL;
            # a bare NULL is UNKNOWN on both engines (wave 170).
            return f"{_emit_expression(node, dialect)} <> 0"
        if isinstance(node, SubqueryExpression):
            # MySQL truthiness: a bare scalar subquery as a condition is
            # nonzero-is-true; T-SQL/Oracle need the comparison.
            return f"({_emit_select(node.query, dialect)}) <> 0"
        if isinstance(node, (FunctionCall, ColumnRef)):
            # Same truthiness for a bare function call or column.
            return f"{_emit_expression(node, dialect)} <> 0"
        if (
            isinstance(node, UnaryOp)
            and node.operator == UnaryOperator.NOT
            and isinstance(node.operand, (ColumnRef, FunctionCall))
        ):
            # NOT boolcol — same truthiness, inverted (wave 135).
            return f"{_emit_expression(node.operand, dialect)} = 0"
        if (
            isinstance(node, UnaryOp)
            and node.operator == UnaryOperator.NOT
            and isinstance(node.operand, BinaryOp)
            and node.operand.operator == BinaryOperator.IS
            and isinstance(node.operand.left, ColumnRef)
            and isinstance(node.operand.right, Literal)
            and node.operand.right.dtype == "boolean"
        ):
            # ``flag IS NOT TRUE`` / ``IS NOT FALSE`` over a boolean column:
            # on these no-boolean engines ``x IS NOT TRUE`` is TRUE when x is
            # FALSE *or* NULL, so a bare ``NOT (x = 1)`` drops the NULL rows.
            # Keep the NULL leg explicitly.
            inner = _emit_expression(node.operand.left, dialect)
            val = "1" if node.operand.right.value else "0"
            return f"({inner} <> {val} OR {inner} IS NULL)"
        if (
            isinstance(node, UnaryOp)
            and node.operator == UnaryOperator.NOT
            and (
                isinstance(node.operand, BinaryOp)
                or (
                    isinstance(node.operand, UnaryOp)
                    and node.operand.operator == UnaryOperator.NOT
                )
            )
        ):
            # NOT (…) — the parenthesized operand is condition position
            # too: bare columns under the AND/OR inside shipped as
            # truthiness (wave 160). Narrow to BinaryOp/nested-NOT
            # operands so NOT EXISTS / IS NULL keep their idiomatic
            # spelling; the nested NOT comes from the ``NOT-pred = 0``
            # rewrite (wave 169).
            return f"NOT ({_emit_condition(node.operand, dialect)})"
        rewritten = _predicate_int_comparison(node)
        if rewritten is not None:
            # ``(c2 IS NULL) = 1`` — MySQL compares a predicate's truth
            # value to a number; T-SQL has no boolean value position.
            return _emit_condition(rewritten, dialect)
        node = _comparisonize_literals(node)
    if (
        dialect == "postgresql"
        and SOURCE_DIALECT.get() == "mysql"
        and isinstance(node, UnaryOp)
        and node.operator == UnaryOperator.NOT
        and isinstance(node.operand, BinaryOp)
    ):
        # PG needs the same NOT-recursion as T-SQL/Oracle for MySQL
        # truthiness shapes (wave 220).
        return f"NOT ({_emit_condition(node.operand, dialect)})"
    if (
        (
            dialect in ("tsql", "oracle")
            or (dialect == "postgresql" and SOURCE_DIALECT.get() == "mysql")
        )
        and isinstance(node, BinaryOp)
        and node.operator in (BinaryOperator.EQ, BinaryOperator.NEQ)
        and _is_predicate_node(node.left)
        and not _is_predicate_node(node.right)
    ):
        # The general chained comparison (``(x IS NULL) = y``, ``… =
        # 1000``): the predicate's MySQL truth VALUE is the exact
        # tri-state CASE (wave 220; the PG leg only for mysql source —
        # PG's own boolean columns compare legitimately).
        cond = _emit_condition(node.left, dialect)
        right = _emit_expression(node.right, dialect)
        op = "=" if node.operator == BinaryOperator.EQ else "<>"
        return f"CASE WHEN {cond} THEN 1 WHEN NOT ({cond}) THEN 0 END " f"{op} {right}"
    if (
        dialect in ("tsql", "oracle")
        and isinstance(node, BinaryOp)
        and node.operator in (BinaryOperator.NULLSAFE_EQ, BinaryOperator.NULLSAFE_NEQ)
    ):
        wrapped = _emit_binary(node, dialect)
        m = re.fullmatch(r"CASE WHEN (.+) THEN 1 ELSE 0 END = 1", wrapped, re.S)
        if m:
            return m.group(1)
        return wrapped
    return _emit_expression(node, dialect)


def _prefix_tsql_output_items(e: exp.Expression) -> None:
    """Qualify RETURNING/OUTPUT items with INSERTED./DELETED. in place.

    DELETE exposes only DELETED; INSERT/UPDATE return the new row, so
    INSERTED matches PG's RETURNING semantics."""
    returning = e.find(exp.Returning)
    if returning is None:
        return
    prefix = "DELETED" if isinstance(e, exp.Delete) else "INSERTED"
    for item in list(returning.expressions):
        target = item.this if isinstance(item, exp.Alias) else item
        if isinstance(target, exp.Star):
            # exp.column("*") would make a quotable identifier ([*]).
            target.replace(exp.Column(this=exp.Star(), table=exp.to_identifier(prefix)))
        elif isinstance(target, exp.Column) and not target.args.get("table"):
            target.set("table", exp.to_identifier(prefix))


def _alias_bare_derived_tables(sql: str, source_dialect: str) -> str | None:
    """Give every alias-less derived table in relation position a
    ``uq_dtN`` alias (T-SQL error 102 / MySQL 1248 without one; the
    double parens themselves are legal once aliased — wave 198)."""
    try:
        tree = sqlglot.parse_one(sql, read=sqlglot_dialect_name(source_dialect))
    except Exception:
        return None
    n = 0
    for sq in tree.find_all(exp.Subquery):
        # Only REAL derived tables (a SELECT body): a parenthesized join
        # GROUP also models as Subquery, and aliasing one both is
        # invalid and hides its tables' names (wave 209 regression fix).
        if (
            not sq.alias
            and isinstance(sq.parent, (exp.From, exp.Join))
            and isinstance(sq.unnest(), (exp.Select, exp.SetOperation))
        ):
            n += 1
            sq.set("alias", exp.TableAlias(this=exp.to_identifier(f"uq_dt{n}")))
    if n == 0:
        return None
    return tree.sql(dialect=sqlglot_dialect_name(source_dialect))


def _flatten_paren_joins(sql: str, source_dialect: str) -> str | None:
    """Flatten a parenthesized INNER/CROSS join tree into the equivalent
    flat CROSS chain with the ON conditions ANDed into WHERE. None when
    the statement carries any outer join (the rewrite would change
    NULL-extension semantics) or does not parse."""
    if re.search(r"(?i)\b(LEFT|RIGHT|FULL)\s+(OUTER\s+)?JOIN\b", sql):
        return None
    try:
        tree = sqlglot.parse_one(sql, read=sqlglot_dialect_name(source_dialect))
    except Exception:
        return None
    if not isinstance(tree, exp.Select):
        return None
    from_clause = tree.args.get("from") or tree.args.get("from_")
    if from_clause is None or tree.args.get("joins"):
        return None
    rel = from_clause.this

    tables: list[exp.Expression] = []
    conditions: list[exp.Expression] = []

    def walk(r: exp.Expression) -> bool:
        if isinstance(r, exp.Subquery) and isinstance(r.this, exp.Table):
            if r.alias:
                return False  # a real derived table, not a paren group
            return walk(r.this)
        if isinstance(r, exp.Table):
            joins = r.args.get("joins") or []
            bare = r.copy()
            bare.args.pop("joins", None)
            tables.append(bare)
            for j in joins:
                kind = (j.args.get("kind") or "").upper() if j.args.get("kind") else ""
                side = (j.args.get("side") or "").upper() if j.args.get("side") else ""
                if side or kind not in ("INNER", "CROSS", ""):
                    return False
                if not walk(j.this):
                    return False
                if j.args.get("on") is not None:
                    conditions.append(j.args["on"])
            return True
        return False

    if not walk(rel) or len(tables) < 2:
        return None

    first, rest = tables[0], tables[1:]
    new_select = tree.copy()
    from_key = "from" if "from" in new_select.arg_types else "from_"
    new_select.set(from_key, exp.From(this=first))
    new_select.set(
        "joins",
        [exp.Join(this=t, kind="CROSS") for t in rest],
    )
    where_parts = [c.this if isinstance(c, exp.Paren) else c for c in conditions]
    existing = new_select.args.get("where")
    if existing is not None:
        where_parts.append(existing.this)
    if where_parts:
        combined = where_parts[0]
        for part in where_parts[1:]:
            combined = exp.And(this=combined, expression=part)
        new_select.set("where", exp.Where(this=combined))
    return new_select.sql(dialect=sqlglot_dialect_name(source_dialect))


def _tsql_drop_col_default(table: str, column: str) -> str:
    """Dynamic T-SQL that drops the (auto-named) default constraint on a column
    — a no-op when the column has none. The constraint's generated name is not
    known at translation time, so it is looked up in sys.default_constraints.
    Used to give SET DEFAULT its replace semantics and to unblock DROP COLUMN /
    DROP DEFAULT (a column can carry only one default; error 1781 / 5074)."""
    tn = table.strip('[]"`')
    cn = column.strip('[]"`')
    return (
        "DECLARE @n SYSNAME; SELECT @n = dc.name FROM sys.default_constraints dc JOIN "
        "sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = "
        "dc.parent_column_id "
        f"WHERE dc.parent_object_id = OBJECT_ID('{tn}') AND c.name = '{cn}'; IF @n IS "
        f"NOT NULL EXEC('ALTER TABLE {table} DROP CONSTRAINT ' + @n)"
    )


def _tsql_alter_type_restating_nullability(table: str, col: str, dtype: str) -> str:
    """T-SQL ``ALTER COLUMN <col> <type>`` re-stating the column's known
    nullability. T-SQL defaults an unspecified nullability to NULL, silently
    dropping a NOT NULL constraint the source's type change preserves (audit
    2026-07-24 N9); the running COLUMN_NOT_NULL map says which to re-state.
    When the script never defined the column (a table it did not create
    in-script), the emission is a warned best-effort statement instead."""
    dtype = _portable_types_in_sql(dtype, "tsql")
    known = (
        (COLUMN_NOT_NULL.get() or {})
        .get(table.split(".")[-1].strip('[]"`').lower(), {})
        .get(col.split(".")[-1].strip('[]"`').lower())
    )
    if known is True:
        return f"ALTER TABLE {table} ALTER COLUMN {col} {dtype} NOT NULL"
    if known is False:
        return f"ALTER TABLE {table} ALTER COLUMN {col} {dtype} NULL"
    return (
        f"-- UNIQUE-1010: T-SQL ALTER COLUMN defaults the column to NULL; the script "
        f"does not define {table}.{col}'s nullability, so it cannot be re-stated — "
        f"verify the column keeps its constraint\nALTER TABLE {table} ALTER COLUMN "
        f"{col} {dtype}"
    )


_TSQL_ADD_KEY_RE = re.compile(
    r"(?isx)^\s*ALTER\s+TABLE\s+(?P<table>[\w.\[\]\"]+)\s+ADD\s+CONSTRAINT\s+(?P<name>[\w\[\]\"]+)\s+(?P<kind>PRIMARY\s+KEY|UNIQUE)\s*(?:CLUSTERED|NONCLUSTERED)?\s*\(\s*(?P<cols>[^()]*?)\s*\)(?P<tail>.*)$"
)
_TSQL_ADD_KEY_TAIL_RE = re.compile(
    r"(?is)^\s*(?:WITH\s*\([^()]*\))?\s*(?:ON\s+[\w\[\]\"]+)?\s*;?\s*$"
)


def _tsql_add_key_constraint(sql: str, dialect: str) -> str | None:
    """Normalize T-SQL ``ADD CONSTRAINT … PRIMARY KEY/UNIQUE CLUSTERED (col
    ASC) WITH (…) ON [grp]`` for the other engines (audit B1).

    sqlglot splits the storage clauses into comma-joined ALTER actions
    (invalid everywhere) and injects ``NULLS FIRST`` into the key column
    list, so this well-defined shape is rebuilt directly: the CLUSTERED
    keyword, per-column sort order, WITH options and filegroup are
    physical-storage details with no logical-schema impact.
    """
    from unique.core.sql_split import split_top_level_commas

    m = _TSQL_ADD_KEY_RE.match(sql)
    if not m or not _TSQL_ADD_KEY_TAIL_RE.match(m.group("tail")):
        return None
    cols: list[str] = []
    for item in split_top_level_commas(m.group("cols")):
        cm = re.fullmatch(r"(?is)\s*([\w\[\]\"]+)(?:\s+(?:ASC|DESC))?\s*", item)
        if not cm:
            return None
        cols.append(_ident(cm.group(1).strip('[]"'), True, dialect))
    if not cols:
        return None
    table_parts = [p.strip('[]"') for p in m.group("table").split(".")]
    if dialect != "tsql" and table_parts and table_parts[0].lower() == "dbo":
        table_parts = table_parts[1:]
    table_sql = ".".join(_ident(p, True, dialect) for p in table_parts)
    name_sql = _ident(m.group("name").strip('[]"'), True, dialect)
    kind = " ".join(m.group("kind").upper().split())
    return (
        f"ALTER TABLE {table_sql} ADD CONSTRAINT {name_sql} {kind} ({', '.join(cols)})"
    )


_RENAME_COLUMN_RE = re.compile(
    r"(?is)^\s*ALTER\s+TABLE\s+(?P<table>[\w.\[\]\"`]+)\s+RENAME\s+COLUMN\s+(?P<old>[\w\[\]\"`]+)\s+TO\s+(?P<new>[\w\[\]\"`]+)\s*;?\s*$"
)


def _portable_rename_column(sql: str) -> str:
    """T-SQL has no ``ALTER TABLE … RENAME COLUMN``; it renames via
    ``sp_rename 'tbl.old', 'new', 'COLUMN'`` (audit D5 — the clause used to
    pass through verbatim and fail on every run)."""
    m = _RENAME_COLUMN_RE.match(sql)
    if not m:
        return sql

    def bare(s: str) -> str:
        return s.strip('[]"`')

    table, old, new = bare(m.group("table")), bare(m.group("old")), bare(m.group("new"))
    return f"EXEC sp_rename '{table}.{old}', '{new}', 'COLUMN'"


_NAMED_DEFAULT_RE = re.compile(r"(?i)\bCONSTRAINT\s+([\w\[\]\"`]+)\s+(?=DEFAULT\b)")


def _drop_named_default(sql: str) -> str:
    """Drop a T-SQL named DEFAULT constraint's name (audit B3).

    Only T-SQL names its DEFAULT constraints; everywhere else ``CONSTRAINT
    <name> DEFAULT`` is a syntax error, and the default itself is anonymous.
    The dropped name is documented with a carrier note (the reconciliation
    layer turns it into a warning).
    """
    names = [m.group(1).strip('[]"`') for m in _NAMED_DEFAULT_RE.finditer(sql)]
    if not names:
        return sql
    cleaned = _NAMED_DEFAULT_RE.sub("", sql)
    notes = "\n".join(
        f"-- UNIQUE-1011: named DEFAULT constraint {n} dropped "
        "(defaults are anonymous on this engine)"
        for n in names
    )
    return f"{cleaned}\n{notes}"


def _portable_alter_add(sql: str, dialect: str) -> str:
    """Unwrap Oracle's parenthesized ALTER TABLE ADD ( ... ) form.

    sqlglot's non-Oracle writers render it as "ADD COLUMNS (item, ...)",
    which no other engine parses. T-SQL takes a plain comma list after one
    ADD; PostgreSQL/MySQL need one ADD per item.
    """
    m = re.search(r"(?is)\bADD\s+COLUMNS\s*\((.*)\)\s*$", sql)
    if not m:
        return sql
    items = [i.strip() for i in _split_top_level_commas(m.group(1))]
    head = sql[: m.start()].rstrip()
    if dialect == "tsql":
        return f"{head} ADD {', '.join(items)}"
    return f"{head} ADD " + ", ADD ".join(items)


def _portable_index(sql: str, dialect: str) -> str:
    """Make a transpiled CREATE INDEX portable for the target dialect.

    - CLUSTERED/NONCLUSTERED are T-SQL-only physical hints; drop them for
      other engines (the keyword has no meaning and breaks parsing).
    - INCLUDE (covering columns) is supported by PostgreSQL and T-SQL but not
      MySQL or Oracle; comment it out there with a note.
    - A filtered-index WHERE clause is supported by PostgreSQL (partial
      index) but not MySQL/Oracle; flag it for those.
    """
    if dialect == "tsql":
        # sqlglot emulates Oracle's default NULLS index ordering by pairing
        # every key with a ``CASE WHEN col IS NULL...`` expression — but a
        # T-SQL index key cannot be an expression (error 156 near CASE), and
        # T-SQL's NULLS-low default matches Oracle's b-tree behaviour for
        # the ASC case anyway. Strip the emulation pairs.
        sql = re.sub(
            r"(?is)CASE\s+WHEN\s+.+?\s+IS\s+NULL\s+THEN\s+1\s+ELSE\s+0\s+END(?:\s+(?:ASC|DESC))?\s*,\s*",
            "",
            sql,
        )
        # Round-trip: restore physical index clauses this tool stripped on a
        # forward pass, recorded in a ``/* UNIQUE: … -- tsql-only … (physical
        # index clause) */`` note — CLUSTERED is positional (after CREATE
        # [UNIQUE]); WITH (...) / ON <fg> are trailing.
        note = re.search(
            r"(?is)\s*/\*\s*UNIQUE(?:-\d{4})?:\s*(?P<clauses>.+?)\s*--\s*tsql-only,[^*]*?"
            r"physical index clause[^*]*?\*/",
            sql,
        )
        if note:
            sql = (
                (sql[: note.start()].rstrip() + sql[note.end() :]).rstrip().rstrip(";")
            )
            clauses = note.group("clauses").strip()
            lead = re.match(r"(?i)(?P<kw>(?:NON)?CLUSTERED)\b\s*(?P<rest>.*)$", clauses)
            if lead:
                sql = re.sub(
                    r"(?i)\bCREATE\s+(UNIQUE\s+)?INDEX\b",
                    lambda m: f"CREATE {m.group(1) or ''}{lead.group('kw')} INDEX",
                    sql,
                    count=1,
                )
                clauses = lead.group("rest").strip()
            if clauses:
                sql = f"{sql} {clauses}"

    dropped_physical: list[str] = []
    if dialect != "tsql":

        def _drop(match: re.Match[str]) -> str:
            dropped_physical.append(match.group(0).strip())
            return ""

        sql = re.sub(r"(?i)\s*\b(NON)?CLUSTERED\b", _drop, sql)
        # T-SQL physical index storage options (WITH (PAD_INDEX = ..., ...))
        # and ON <filegroup> have no portable equivalent; drop them — but keep
        # the original in a restorable note (never a silent loss). The filegroup
        # name may already be requoted ("PRIMARY") by the time we see it.
        sql = re.sub(r"(?i)\s+WITH\s*\([^)]*\)", _drop, sql)
        sql = re.sub(r'(?i)\s+ON\s+(?:\[[^\]]+\]|"[^"]+"|\w+)\s*$', _drop, sql)

    # sqlglot emulates PostgreSQL's NULLS-ordering by prefixing an index key
    # with "CASE WHEN col IS NULL THEN 1 ELSE 0 END, col". That expression is
    # invalid inside an index column list in T-SQL, MySQL and Oracle, so
    # collapse it back to just the column for every target except PostgreSQL.
    if dialect != "postgresql":
        sql = re.sub(
            r"(?i)CASE\s+WHEN\s+(?P<col>[\w.\[\]\"`]+)\s+IS\s+NULL\s+THEN\s+\d+\s+ELSE\s+\d+\s+END\s*,\s*(?P=col)",
            lambda m: m.group("col"),
            sql,
        )
        # A bare NULLS FIRST/LAST in an index column list is invalid on Oracle,
        # MySQL and T-SQL (allowed only in ORDER BY); sqlglot may add it.
        sql = re.sub(r"(?i)\s+NULLS\s+(?:FIRST|LAST)", "", sql)

    if dialect in ("mysql", "oracle"):
        # INCLUDE (...) covering columns: not supported.
        m = re.search(r"(?i)\bINCLUDE\s*\([^)]*\)", sql)
        if m:
            sql = (
                sql[: m.start()].rstrip()
                + sql[m.end() :]
                + f"\n-- UNIQUE-1012: {dialect} does not support INCLUDE covering "
                f"columns; dropped: {m.group(0)}"
            )
        # Filtered index WHERE: not supported (MySQL/Oracle).
        m = re.search(r"(?i)\sWHERE\s+.+$", sql)
        if m:
            sql = (
                sql[: m.start()].rstrip()
                + f"\n-- UNIQUE-1013: {dialect} does not support filtered indexes; "
                f"dropped predicate:{m.group(0)}"
            )
    if dropped_physical:
        # Preserve the stripped physical clauses in a restorable note so the
        # original can be recovered on a transpilation back to T-SQL.
        clauses = " ".join(dropped_physical)
        sql += (
            f"\n/* UNIQUE-1014: {clauses} -- tsql-only, no {dialect} equivalent "
            "(physical index clause) */"
        )
    return sql


def _walk_qualify_using(value: object, using_lc: set[str], left: str) -> object:
    """Qualify a bare ColumnRef whose name is a USING join column with the left
    table. Does not descend into a nested subquery/select (its own scope)."""
    if isinstance(value, ColumnRef):
        if value.table is None and value.name.lower() in using_lc:
            return dataclasses.replace(value, table=left)
        return value
    if isinstance(value, (SubqueryExpression, SelectStatement)):
        return value
    if isinstance(value, tuple):
        new = tuple(_walk_qualify_using(v, using_lc, left) for v in value)
        changed = any(a is not b for a, b in zip(new, value, strict=True))
        return new if changed else value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        changes = {
            f.name: nv
            for f in dataclasses.fields(value)
            if (nv := _walk_qualify_using(getattr(value, f.name), using_lc, left))
            is not getattr(value, f.name)
        }
        return dataclasses.replace(value, **changes) if changes else value
    return value


def _qualify_using_join_columns(node: SelectStatement, dialect: str) -> SelectStatement:
    """T-SQL has no USING; a ``USING (x)`` join becomes ``ON a.x = b.x``, so a
    bare ``x`` in the projection is then ambiguous. Qualify bare USING-column
    refs in the SELECT's own clauses with the left table (INNER/LEFT joins, whose
    merged column takes the left value)."""
    if dialect != "tsql" or not isinstance(
        node.from_clause, (TableRef, SubqueryExpression)
    ):
        return node
    left = node.from_clause.alias or getattr(node.from_clause, "name", None)
    using_lc = {
        c.lower()
        for j in node.joins
        if j.using and j.join_type in (JoinType.INNER, JoinType.LEFT)
        for c in j.using
    }
    if not left or not using_lc:
        return node
    return dataclasses.replace(
        node,
        columns=_walk_qualify_using(node.columns, using_lc, left),  # type: ignore[arg-type]
        where=_walk_qualify_using(node.where, using_lc, left),  # type: ignore[arg-type]
        group_by=_walk_qualify_using(node.group_by, using_lc, left),  # type: ignore[arg-type]
        having=_walk_qualify_using(node.having, using_lc, left),  # type: ignore[arg-type]
        order_by=_walk_qualify_using(node.order_by, using_lc, left),  # type: ignore[arg-type]
    )


_AGG_NAMES = frozenset(
    {
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "GROUP_CONCAT",
        "STRING_AGG",
        "LISTAGG",
        "STDDEV",
        "STDDEV_POP",
        "STDDEV_SAMP",
        "VARIANCE",
        "VAR_POP",
        "VAR_SAMP",
        "VAR",
        "STDEV",
        "STDEVP",
        "VARP",
        "ARRAY_AGG",
        "JSON_ARRAYAGG",
        "JSON_OBJECTAGG",
        "BIT_AND",
        "BIT_OR",
        "BIT_XOR",
        "BOOL_AND",
        "BOOL_OR",
    }
)


def _has_aggregate(node: object) -> bool:
    """True if an aggregate function call appears in *node* (not descending into a
    nested subquery/select, which has its own aggregation scope)."""
    if isinstance(node, FunctionCall) and node.name.upper() in _AGG_NAMES:
        return True
    if isinstance(node, (SelectStatement, SubqueryExpression)):
        return False
    if isinstance(node, tuple):
        return any(_has_aggregate(v) for v in node)
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        return any(
            _has_aggregate(getattr(node, f.name)) for f in dataclasses.fields(node)
        )
    return False


def _ir_is_string_expr(node: object) -> bool:
    """True if an IR expression is provably a string value (a string literal or a
    cast to a character type)."""
    if isinstance(node, Literal):
        return isinstance(node.value, str)
    if isinstance(node, CastExpression):
        return node.target_type.name.split("(")[0].strip().upper() in (
            "CHAR",
            "VARCHAR",
            "VARCHAR2",
            "NCHAR",
            "NVARCHAR",
            "TEXT",
            "CLOB",
        )
    return False


def _from_string_columns(node: SelectStatement) -> frozenset[str]:
    """Lower-cased names of the FROM subquery's columns that are provably string
    typed (all-string projection), so a bare ORDER BY/GROUP key on one can safely
    take a COLLATE without erroring on a non-string column."""
    fc = node.from_clause
    if not isinstance(fc, SubqueryExpression):
        return frozenset()
    out: set[str] = set()
    for c in fc.query.columns:
        if isinstance(c, Alias) and _ir_is_string_expr(c.expression):
            out.add(c.name.lower())
    return frozenset(out)


def _cte_anchor_column_names(query: SelectStatement) -> list[str]:
    """Output column names of a CTE's anchor SELECT — for Oracle's required
    recursive-CTE column alias list. Returns [] if any projection has no clean
    name (an unnameable list must not be guessed)."""
    names: list[str] = []
    for item in query.columns:
        if isinstance(item, Alias) or (isinstance(item, ColumnRef) and not item.table):
            names.append(item.name)
        else:
            return []
    return names


def _name_tsql_derived_columns(query: SelectStatement) -> SelectStatement:
    """Alias every unnamed projection of a T-SQL derived table (error 8155). A
    bare column reference already has a name; a literal, function call, expression
    or ``@parameter`` does not. A ``*`` projection is named by the source table."""
    new_cols: list[ASTNode] = []
    changed = False
    for i, col in enumerate(query.columns):
        if isinstance(col, Alias):
            new_cols.append(col)
            continue
        emitted = _emit_expression(col, "tsql").strip()
        # A column identifier must start with a letter/underscore — a numeric
        # literal (``1``) is \w+ but is NOT a named column and must be aliased.
        named = (
            emitted == "*"
            or emitted.endswith(".*")
            or re.fullmatch(
                r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|"[^"]+"|\[[^\]]+\]', emitted
            )
            is not None
        )
        if named:
            new_cols.append(col)
        else:
            new_cols.append(Alias(expression=col, name=f"uq_col{i + 1}"))
            changed = True
    return dataclasses.replace(query, columns=tuple(new_cols)) if changed else query


def _emit_select(node: SelectStatement, dialect: str, into: str | None = None) -> str:
    """Emit a SELECT statement.

    ``into`` renders T-SQL's ``SELECT … INTO <table> FROM …`` (the
    faithful CTAS form there); placed right before the FROM clause.
    """
    node = _qualify_using_join_columns(node, dialect)
    # T-SQL forbids a non-selected ORDER BY expression under DISTINCT, which
    # used to force dropping the null-priority key (silent NULL reordering).
    # Wrap the DISTINCT in a derived table and order OUTSIDE it instead —
    # sound when every ORDER BY expression is a bare selected column.
    if (
        dialect == "tsql"
        and node.distinct
        and node.order_by
        and into is None
        and not node.limit
        and all(
            isinstance(o.expression, ColumnRef) and o.expression.table is None
            for o in node.order_by
        )
        and any(_order_null_priority_key(o, dialect) for o in node.order_by)
    ):
        # Every derived-table column must be named (error 8155); a DISTINCT over
        # a computed/collated projection has none (the COLLATE below also strips
        # a bare column's name), so name them before wrapping.
        _dist_inner = _name_tsql_derived_columns(dataclasses.replace(node, order_by=()))
        inner = _emit_select(_dist_inner, dialect)
        rendered_items = []
        for o in node.order_by:
            key = _order_null_priority_key(o, dialect)
            item = _emit_order_item(o, dialect)
            rendered_items.append(f"{key}, {item}" if key else item)
        return (
            f"SELECT *\nFROM ({inner}) uq_d\n" f"ORDER BY {', '.join(rendered_items)}"
        )
    # MySQL allows HAVING without GROUP BY on a non-aggregate (a post-window row
    # filter); Oracle/PG/T-SQL require GROUP BY there. Wrap the query so the HAVING
    # becomes an outer WHERE, preserving the window-then-filter order.
    if (
        dialect != "mysql"
        and node.having is not None
        and not node.group_by
        and not _has_aggregate(node.having)
        and into is None
    ):
        # A computed projection (RANK()/expression) has no name — error 8155 in
        # the T-SQL uq_h derived table; name it before wrapping (a synthesized
        # alias on an unnamed column is valid on every target, so this is applied
        # unconditionally rather than behind a dialect check).
        _inner = _name_tsql_derived_columns(dataclasses.replace(node, having=None))
        _hcond = _emit_condition(node.having, dialect)
        return f"SELECT * FROM ({_emit_select(_inner, dialect)}) uq_h\nWHERE {_hcond}"
    parts: list[str] = []

    # CTEs
    if node.ctes:
        cte_parts = []
        # PG and MySQL REQUIRE the RECURSIVE keyword (once, after WITH, for the
        # whole clause) when ANY CTE is recursive; T-SQL and Oracle have no such
        # keyword (recursion is implicit).
        recursive = (
            "RECURSIVE "
            if dialect in ("postgresql", "mysql")
            and any(c.recursive for c in node.ctes)
            else ""
        )
        for cte in node.ctes:
            cols = f"({', '.join(cte.columns)})" if cte.columns else ""
            # Oracle REQUIRES an explicit column alias list on a recursive CTE
            # (ORA-32039); derive it from the anchor SELECT's output names when
            # the source omitted it (T-SQL/PG/MySQL infer them).
            if not cols and cte.recursive and dialect == "oracle":
                derived = _cte_anchor_column_names(cte.query)
                if derived:
                    cols = f"({', '.join(derived)})"
            cte_query = cte.query
            if dialect == "tsql" and cte_query.order_by and not cte_query.limit:
                # Illegal in a T-SQL CTE without TOP/OFFSET (error 1033),
                # and with no LIMIT it cannot change the result.
                cte_query = dataclasses.replace(cte_query, order_by=())
            inner = _emit_select(cte_query, dialect)
            cte_parts.append(f"{cte.name}{cols} AS (\n{inner}\n)")
        parts.append(f"WITH {recursive}{', '.join(cte_parts)}")

    # A literal ``OFFSET 0`` is a no-op (skip zero rows). On T-SQL it would
    # force an ORDER BY and on MySQL a LIMIT the source never had, so drop it
    # for those targets — the result set is identical either way.
    if (
        dialect in ("tsql", "mysql")
        and node.limit is not None
        and isinstance(node.limit.offset, Literal)
        and node.limit.offset.value == 0
    ):
        new_limit = (
            None
            if node.limit.limit is None
            else dataclasses.replace(node.limit, offset=None)
        )
        node = dataclasses.replace(node, limit=new_limit)

    # SELECT — T-SQL spells a plain row limit as TOP inside the SELECT
    # clause (OFFSET/FETCH needs an ORDER BY and an offset). v0.7.0 reduced
    # it to a comment, silently returning all rows (audit 2026-07-02).
    top = ""
    if (
        dialect == "tsql"
        and node.limit is not None
        and node.limit.limit is not None
        and node.limit.offset is None
    ):
        pct = " PERCENT" if node.limit.percent else ""
        limit_sql = _emit_expression(node.limit.limit, dialect)
        if not re.fullmatch(r"\d+", limit_sql.strip()):
            # T-SQL requires parentheses around a non-literal TOP argument.
            limit_sql = f"({limit_sql.strip()})"
        ties = " WITH TIES" if node.limit.with_ties else ""
        top = f"TOP {limit_sql}{pct}{ties} "
    distinct = "DISTINCT " if node.distinct else ""
    if (
        dialect in ("oracle", "mysql")
        and len(node.columns) > 1
        and any(isinstance(c, Star) and not c.table for c in node.columns)
        and isinstance(node.from_clause, TableRef)
    ):
        # Oracle AND MySQL reject a BARE ``*`` alongside other select
        # items (ORA-00923 / 1064); qualify it with the FROM relation
        # (waves 150, 213).
        qual = node.from_clause.alias or node.from_clause.name
        node = dataclasses.replace(
            node,
            columns=tuple(
                Star(table=qual) if isinstance(c, Star) and not c.table else c
                for c in node.columns
            ),
        )
    # MySQL CUBE/GROUPING SETS degrade to the base grouping (subtotal rows
    # omitted, warned carrier below): every surviving row is a base row, so a
    # GROUPING()/GROUPING_ID() there is the constant 0. Native WITH ROLLUP
    # keeps the real calls.
    if dialect == "mysql" and node.group_modifier in ("CUBE", "GROUPING SETS"):

        def _zero_grouping(e: ASTNode) -> ASTNode:
            if isinstance(e, FunctionCall) and e.name.upper() in (
                "GROUPING",
                "GROUPING_ID",
            ):
                return Literal(value=0, dtype="integer")
            if isinstance(e, Alias):
                return dataclasses.replace(e, expression=_zero_grouping(e.expression))
            return e

        node = dataclasses.replace(
            node, columns=tuple(_zero_grouping(c) for c in node.columns)
        )
    # SELECT DISTINCT / GROUP BY over a case-sensitive source's string column
    # dedups/groups in the target's case-insensitive collation on MySQL/T-SQL
    # (merging 'a'/'A'); a binary collation on the provably-string key — applied
    # consistently to the SELECT column, GROUP BY key and ORDER BY key — keeps
    # them distinct.
    _dstr: frozenset[str] = frozenset()
    _dcoll = "utf8mb4_bin" if dialect == "mysql" else "Latin1_General_BIN2"
    if (
        (node.distinct or node.group_by)
        and SOURCE_DIALECT.get() in ("postgresql", "oracle")
        and dialect in ("mysql", "tsql")
        # GROUPING()/GROUPING_ID() must reference the GROUP BY key VERBATIM
        # (MySQL error 3602 on a collated key) — skip the binary-collation
        # emulation when the select list uses them.
        and not any(
            isinstance(f, FunctionCall)
            and f.name.upper() in ("GROUPING", "GROUPING_ID")
            for c in node.columns
            for f in _walk_nodes(c)
        )
    ):
        _dstr = _from_string_columns(node)
    if node.empty_select_list and not node.columns and dialect == "postgresql":
        # PG's zero-column select list (``SELECT;``) — a ``*`` here is
        # invalid without FROM and changes the shape with one (wave 124).
        parts.append(f"SELECT {distinct}".rstrip())
    else:
        with _current_select_table(node):  # see _base.py (RAWTOHEX/etc.)
            _col_parts = []
            for c in node.columns:
                _cstr = _emit_value_expression(c, dialect)
                if (
                    _dstr
                    and isinstance(c, ColumnRef)
                    and c.table is None
                    and c.name.lower() in _dstr
                ):
                    # COLLATE strips the output column name; a T-SQL DISTINCT
                    # wrapped in the uq_d derived table then has an unnamed
                    # column (error 8155). Re-alias to the source name so the
                    # wrapper and its outer ORDER BY resolve (harmless on MySQL,
                    # which keeps the same output-column name either way).
                    _alias = _ident(c.name, c.quoted, dialect)
                    _cstr = f"{_cstr} COLLATE {_dcoll} AS {_alias}"
                _col_parts.append(_cstr)
            cols = ", ".join(_col_parts) or "*"
        parts.append(f"SELECT {distinct}{top}{cols}")

    if into:
        parts.append(f"INTO {into}")

    # FROM
    if node.from_clause:
        if isinstance(node.from_clause, UnpivotRelation):
            parts.append(f"FROM {_emit_unpivot_relation(node.from_clause, dialect)}")
        elif isinstance(node.from_clause, PivotRelation):
            parts.append(f"FROM {_emit_pivot_relation(node.from_clause, dialect)}")
        elif isinstance(node.from_clause, SubqueryExpression):
            # A derived table needs its alias, or references to it (and, on
            # MySQL, the derived table itself) are invalid. Oracle is the
            # only engine where the alias is optional — synthesize one for
            # everyone else when the source (Oracle) omitted it.
            alias = node.from_clause.alias
            if not alias and dialect != "oracle":
                alias = "uq_dt"
            sub_alias = f" {_ident(alias, False, dialect)}" if alias else ""
            dt_query = node.from_clause.query
            if dialect == "tsql":
                # T-SQL requires every derived-table column to be named (error
                # 8155) — a literal/function/@parameter projection has none.
                dt_query = _name_tsql_derived_columns(dt_query)
            inner_sql = _emit_select(dt_query, dialect)
            if dialect == "tsql":
                # A derived table may not carry ORDER BY without TOP
                # (error 1033); without a limit the ordering is meaningless.
                inner_sql = (
                    re.sub(r"(?is)\s+ORDER\s+BY\s+[^()]*$", "", inner_sql)
                    if not re.search(r"(?i)\bTOP\b", inner_sql)
                    else inner_sql
                )
            parts.append(f"FROM ({inner_sql}){sub_alias}")
        else:
            parts.append(f"FROM {_emit_table_ref(node.from_clause, dialect)}")
    elif dialect == "oracle":
        # Oracle requires a FROM clause: a table-less SELECT (e.g. ``SELECT 1``,
        # ``SELECT SYSDATE``) reads from the DUAL pseudo-table, else ORA-00923.
        parts.append("FROM DUAL")

    # JOINs. For the T-SQL USING->ON rewrite, track per USING column the
    # expression that denotes the chain's MERGED column so far: LEFT/INNER
    # joins keep the left carrier, a RIGHT join replaces it with its right
    # side, and a FULL join merges both (COALESCE) — PG's USING semantics.
    from_name = None
    if isinstance(node.from_clause, TableRef):
        from_name = node.from_clause.alias or node.from_clause.name
    elif isinstance(node.from_clause, UnpivotRelation):
        from_name = node.from_clause.alias or "uq_unpivot"
    elif isinstance(node.from_clause, PivotRelation):
        from_name = node.from_clause.alias or "uq_pivot"
    elif isinstance(node.from_clause, SubqueryExpression):
        from_name = node.from_clause.alias or ("uq_dt" if dialect != "oracle" else None)
    merged_cols: dict[str, str] = {}
    for join in node.joins:
        parts.append(
            _emit_join(join, dialect, left_name=from_name, merged_cols=merged_cols)
        )

    # WHERE
    if node.where:
        parts.append(f"WHERE {_emit_condition(node.where, dialect)}")

    # GROUP BY with its ROLLUP/CUBE super-aggregate modifier. MySQL trails ROLLUP
    # as ``WITH ROLLUP`` and has neither CUBE nor GROUPING SETS — so a CUBE keeps
    # the base grouping and a carrier (prepended below) documents the omitted
    # super-aggregate rows; every other engine wraps the columns natively.
    if node.group_by:

        def _group_key(g: ASTNode) -> str:
            # A positional GROUP BY ordinal (``GROUP BY 1``) has no equivalent on
            # T-SQL/Oracle — expand it to the referenced select-list expression
            # (PG/MySQL keep the ordinal; ORDER BY ordinals are fine everywhere).
            if dialect in ("tsql", "oracle"):
                _ord = _plain_int_value(g) if isinstance(g, Literal) else None
                if _ord is not None and 1 <= _ord <= len(node.columns):
                    _col = node.columns[_ord - 1]
                    if isinstance(_col, Alias):
                        _col = _col.expression
                    g = _col
            _gs = _emit_expression(g, dialect)
            if (
                _dstr
                and isinstance(g, ColumnRef)
                and g.table is None
                and g.name.lower() in _dstr
            ):
                return f"{_gs} COLLATE {_dcoll}"
            return _gs

        group_cols = ", ".join(_group_key(g) for g in node.group_by)
        if node.group_by_composite and dialect != "mysql":
            # A multi-element GROUP BY list — emit every element (T-SQL/Oracle/PG
            # take the standard comma-list syntax natively). MySQL falls through
            # to the base ``group_cols`` degrade (carrier prepended below).
            pieces: list[str] = []
            for el in node.group_by_composite:
                if el.kind == "GROUPING SETS":
                    pieces.append(el.sets_sql or "")
                elif el.kind:
                    cols = ", ".join(_group_key(c) for c in el.columns)
                    pieces.append(f"{el.kind}({cols})")
                else:
                    pieces.append(", ".join(_group_key(c) for c in el.columns))
            parts.append("GROUP BY " + ", ".join(pieces))
        elif node.group_modifier == "GROUPING SETS" and dialect != "mysql":
            parts.append(f"GROUP BY {node.grouping_sets_sql}")
        elif dialect == "mysql" and node.group_modifier == "ROLLUP":
            parts.append(f"GROUP BY {group_cols} WITH ROLLUP")
        elif dialect == "mysql" and node.group_modifier in ("CUBE", "GROUPING SETS"):
            parts.append(f"GROUP BY {group_cols}")
        elif node.group_modifier in ("ROLLUP", "CUBE"):
            parts.append(f"GROUP BY {node.group_modifier}({group_cols})")
        else:
            parts.append(f"GROUP BY {group_cols}")

    # HAVING
    if node.having:
        parts.append(f"HAVING {_emit_condition(node.having, dialect)}")

    # ORDER BY
    if node.order_by:
        # Preserve the source's implicit NULL ordering on MySQL/T-SQL with a
        # leading null-priority key. T-SQL forbids a non-selected ORDER BY
        # expression under DISTINCT; MySQL forbids one only when it references a
        # column that isn't in the (here collated) select list (error 3065). Skip
        # the emulation in those cases so the SQL stays valid.
        emulate_nulls = not (
            (dialect == "tsql" and node.distinct)
            or (
                dialect in ("mysql", "tsql")
                and (node.distinct or node.group_by)
                and _dstr
            )
        )
        # A case-sensitive source (PG/Oracle) ordering a string column comes back
        # in the target's default (case-insensitive) collation on MySQL/T-SQL; a
        # binary collation on a provably-string key preserves the source order.
        # The reverse — a case-INsensitive source (MySQL/T-SQL) ordering a string
        # column comes back case-sensitively on PG/Oracle; LOWER() on the key
        # approximates the source's case-insensitive order (maintainer policy).
        _cs_str_cols: frozenset[str] = frozenset()
        _ci_str_cols: frozenset[str] = frozenset()
        if SOURCE_DIALECT.get() in ("postgresql", "oracle") and dialect in (
            "mysql",
            "tsql",
        ):
            _cs_str_cols = _from_string_columns(node)
        elif SOURCE_DIALECT.get() in ("mysql", "tsql") and dialect in (
            "postgresql",
            "oracle",
        ):
            _ci_str_cols = _from_string_columns(node)
        _bin_coll = "utf8mb4_bin" if dialect == "mysql" else "Latin1_General_BIN2"
        _ci_distinct_limit = False
        rendered = []
        for o in node.order_by:
            key = _order_null_priority_key(o, dialect) if emulate_nulls else None
            _str_key = (
                o.expression.name.lower()
                if isinstance(o.expression, ColumnRef) and o.expression.table is None
                else None
            )
            _oc = _bin_coll if (_str_key in _cs_str_cols) else None
            _lower = _str_key is not None and _str_key in _ci_str_cols
            if _lower and node.distinct and dialect in ("postgresql", "oracle"):
                # PG/Oracle reject an ORDER BY expression (LOWER(x)) absent from a
                # DISTINCT select list — and LOWER-ordering cannot emulate MySQL's
                # case-insensitive DISTINCT dedup anyway (it collapses 'a'='A',
                # they don't). Keep the plain key (valid) and flag the collation
                # divergence as a documented carrier.
                _lower = False
                _ci_distinct_limit = True
            item_sql = _emit_order_item(o, dialect, collate=_oc, lower=_lower)
            rendered.append(f"{key}, {item_sql}" if key else item_sql)
        order_line = f"ORDER BY {', '.join(rendered)}"
        if _ci_distinct_limit:
            order_line += (
                " /* UNIQUE-1015: MySQL's default collation is case-insensitive, so "
                "DISTINCT/ordering on a string column merges 'a'='A'; PG/Oracle are "
                "case-sensitive and keep them distinct — no portable equivalent (see "
                "docs/03-unsupported.md) */"
            )
        parts.append(order_line)
    elif dialect == "tsql" and node.limit is not None and node.limit.offset is not None:
        # OFFSET…FETCH requires an ORDER BY on T-SQL; the source had
        # none, so the arbitrary-order marker is faithful.
        parts.append("ORDER BY (SELECT NULL)")

    # LIMIT / OFFSET
    if node.limit:
        limit_sql = _emit_limit(node.limit, dialect)
        if limit_sql:
            parts.append(limit_sql)

    result = "\n".join(parts)

    # MySQL has neither GROUP BY CUBE nor GROUPING SETS; the base grouping above
    # is valid but omits the super-aggregate rows, so surface the loss (the
    # no-silent-loss scan mirrors this carrier as a warning).
    if (
        dialect == "mysql"
        and node.group_modifier in ("CUBE", "GROUPING SETS")
        and node.group_by
    ):
        result = (
            f"-- UNIQUE-1016: MySQL has no GROUP BY {node.group_modifier}; the base "
            "grouping is kept and the super-aggregate (subtotal) rows are "
            "omitted\n" + result
        )
    elif dialect == "mysql" and node.group_by_composite and node.group_by:
        result = (
            "-- UNIQUE-1017: MySQL has no multi-element GROUP BY (CUBE/ROLLUP/GROUPING "
            "SETS combined); the base grouping is kept and the "
            "super-aggregate (subtotal) rows are omitted\n" + result
        )

    # A top-level ``SELECT … FOR XML/JSON`` serializes the whole result set into
    # ONE XML/JSON scalar — T-SQL-only. Elsewhere there is no faithful
    # cross-engine equivalent (the exact null-omission/formatting rules differ),
    # so degrade to a documented carrier + warning rather than silently dropping
    # the clause (which changes a one-row scalar into the raw multi-row set).
    if node.has_for_xml and dialect != "tsql":
        result = (
            "-- UNIQUE-1018: T-SQL FOR XML/JSON row serialization has no cross-engine "
            "equivalent; the clause is dropped and the base rows are returned "
            "instead (see docs/03-unsupported.md)\n" + result
        )

    # Set operation
    if node.set_op and node.set_query:
        # INTERSECT ALL / EXCEPT ALL keep duplicates. MySQL (8.0.31+), PG and
        # Oracle (21c+; live-verified on 23c) support them natively — Oracle
        # spells the EXCEPT-ALL form ``MINUS ALL``. T-SQL has no ALL form at
        # all (live-verified: "The 'ALL' version of the INTERSECT operator is
        # not supported") — ``Transformer`` rewrites or degrades those before
        # they ever reach this emitter (see ``_gate_tsql_setop_all``), so the
        # plain-spelling branches below are an unreachable defensive backstop
        # for T-SQL, never the live behaviour.
        _all_ok = dialect in ("mysql", "postgresql", "oracle")
        _is_oracle = dialect == "oracle"
        op_map = {
            SetOperationType.UNION: "UNION",
            SetOperationType.UNION_ALL: "UNION ALL",
            SetOperationType.INTERSECT: "INTERSECT",
            SetOperationType.INTERSECT_ALL: (
                "INTERSECT ALL" if _all_ok else "INTERSECT"
            ),
            SetOperationType.EXCEPT: "MINUS" if _is_oracle else "EXCEPT",
            SetOperationType.EXCEPT_ALL: (
                ("MINUS ALL" if _is_oracle else "EXCEPT ALL")
                if _all_ok
                else ("MINUS" if _is_oracle else "EXCEPT")
            ),
        }
        op = op_map.get(node.set_op, "UNION")
        right = _emit_select(node.set_query, dialect)
        if node.set_query.ctes:
            # A set arm carrying its own WITH was parenthesized in the
            # source (a flat chain cannot carry one) and needs the parens
            # back — ``UNION ALL WITH z …`` is invalid (wave 129).
            # Parenthesized CHAIN arms are shielded as derived tables at
            # conversion; a bare set_op arm here is a flat chain and must
            # stay flat (parens would re-associate the row set).
            right = f"({right})"
        result = f"{result}\n{op}\n{right}"

    # MySQL's SQL_CALC_FOUND_ROWS has no equivalent elsewhere; sqlglot drops it
    # silently. Surface the loss as a carrier (mirrored to a warning by the
    # no-silent-loss scan) so a following FOUND_ROWS() is not silently broken.
    if node.calc_found_rows and dialect != "mysql":
        result = (
            "-- UNIQUE-1019: MySQL SQL_CALC_FOUND_ROWS has no equivalent here; the "
            "full row count for a following FOUND_ROWS() is not computed — run "
            "a separate COUNT(*) query\n" + result
        )

    return result


def _emit_insert(node: InsertStatement, dialect: str) -> str:
    """Emit an INSERT statement, lowering any upsert clause per target."""
    if node.is_replace:
        # MySQL's REPLACE is a delete-then-insert upsert (cascades on FK
        # deletes, resets AUTO_INCREMENT differently, fires DELETE+INSERT
        # triggers) — not the same operation as an ON CONFLICT/MERGE
        # upsert, so it must never be silently lowered to a plain INSERT.
        # The Transformer already degrades non-MySQL targets whole
        # (``_gate_mysql_replace``) before this is reached; this branch is
        # the same honest degrade for any caller that emits directly.
        if dialect != "mysql":
            return _degrade_upsert(
                node,
                dialect,
                f"MySQL REPLACE (delete-then-insert upsert) has no "
                f"{dialect} equivalent",
            )
        return _emit_insert_core(node, dialect, insert_kw="REPLACE INTO")
    if isinstance(node.on_conflict, OnConflictClause):
        return _emit_upsert(node, node.on_conflict, dialect)
    return _emit_insert_core(node, dialect)


def _emit_insert_core(
    node: InsertStatement, dialect: str, insert_kw: str = "INSERT INTO"
) -> str:
    """Emit the bare INSERT (no upsert clause). ``insert_kw`` lets MySQL's
    ``INSERT IGNORE INTO`` reuse the same body."""
    table = _emit_table_ref(node.table, dialect)
    col_names = [_ident_if_plain(c, dialect) for c in node.columns]
    cols = f" ({', '.join(col_names)})" if node.columns else ""

    all_empty = bool(node.values) and all(len(row) == 0 for row in node.values)
    if node.values and not all_empty:
        rows = []
        for row in node.values:
            cells = []
            for i, v in enumerate(row):
                if node.columns and i < len(node.columns):
                    v = _coerce_bit_literal(node.table, node.columns[i], v, dialect)
                    v = _coerce_date_literal(node.table, node.columns[i], v, dialect)
                # VALUES cells are value position too: a predicate cell
                # (``(ld IS NULL)``) needs the tri-state CASE off MySQL
                # (wave 216).
                cells.append(_emit_value_expression(v, dialect))
            rows.append(f"({', '.join(cells)})")
        values = ", ".join(rows)
        return f"{insert_kw} {table}{cols}\nVALUES {values}"

    if node.select:
        sel_node = node.select
        with_prefix = ""
        if dialect == "tsql" and sel_node.ctes:
            # T-SQL requires the WITH clause BEFORE the INSERT.
            cte_parts = []
            for cte in sel_node.ctes:
                rec = "RECURSIVE " if cte.recursive else ""
                ccols = f"({', '.join(cte.columns)})" if cte.columns else ""
                cte_query = cte.query
                if cte_query.order_by and not cte_query.limit:
                    cte_query = dataclasses.replace(cte_query, order_by=())
                inner = _emit_select(cte_query, dialect)
                cte_parts.append(f"{rec}{cte.name}{ccols} AS (\n{inner}\n)")
            with_prefix = f"WITH {', '.join(cte_parts)}\n"
            sel_node = dataclasses.replace(sel_node, ctes=())
        select = _emit_select(sel_node, dialect)
        return f"{with_prefix}{insert_kw} {table}{cols}\n{select}"

    if dialect == "mysql":
        # MySQL has no DEFAULT VALUES clause; the all-defaults row is
        # spelled with empty lists.
        return f"{insert_kw} {table} () VALUES ()"
    if dialect == "oracle" and (all_empty or not node.columns):
        # Oracle has no DEFAULT VALUES and the all-defaults row cannot
        # be spelled without the column list.
        return (
            "-- UNIQUE-1020: all-defaults INSERT has no Oracle spelling without the "
            "column list; original preserved:\n"
            f"-- {insert_kw} {table} VALUES ()"
        )
    return f"{insert_kw} {table}{cols}\nDEFAULT VALUES"


#: The synthetic aliases used when an upsert is lowered to a MERGE statement.
#: The ``uq_`` prefix (the project's synthesized-name convention) keeps them from
#: colliding with a real target table named ``t``/``src`` (``MERGE INTO t AS t``
#: is ambiguous).
_UPSERT_TGT_ALIAS = "uq_t"
_UPSERT_SRC_ALIAS = "uq_s"


def _emit_excluded_column(node: ExcludedColumn, dialect: str) -> str:
    """Render an incoming-row reference in an upsert action per target:
    PG ``EXCLUDED.col``, MySQL ``VALUES(col)``, T-SQL/Oracle MERGE-source
    ``src.col``."""
    col = _ident_if_plain(node.column, dialect)
    if dialect == "postgresql":
        return f"EXCLUDED.{col}"
    if dialect == "mysql":
        return f"VALUES({col})"
    return f"{_UPSERT_SRC_ALIAS}.{col}"


def _resolve_conflict_key(
    node: InsertStatement, oc: OnConflictClause
) -> tuple[str, ...] | None:
    """The conflict-target columns to lower with: the explicit list when the
    source stated one (PG), else a single harvested PK/UNIQUE key (MySQL's
    any-key upsert), else ``None`` (the caller degrades whole)."""
    if oc.key_columns:
        return oc.key_columns
    registry = PK_UNIQUE_COLUMNS.get() or {}
    keys = registry.get(node.table.name.lower())
    if keys:
        # PK is stored first; it is the canonical, unambiguous target.
        return keys[0]
    return None


def _degrade_upsert(node: InsertStatement, dialect: str, reason: str) -> str:
    """Whole-statement carrier for an upsert the target cannot render (no key,
    or an unsupported action shape) — never a plain INSERT that would raise or
    duplicate at runtime."""
    original = _emit_insert_core(node, SOURCE_DIALECT.get() or dialect)
    return (
        f"-- UNIQUE-1021: {reason}; statement preserved as a comment\n"
        + _comment_block(original)
    )


def _emit_upsert(node: InsertStatement, oc: OnConflictClause, dialect: str) -> str:
    """Lower an INSERT ... upsert clause to the target's idiom."""
    if dialect == "postgresql":
        return _emit_upsert_pg(node, oc)
    if dialect == "mysql":
        return _emit_upsert_mysql(node, oc)
    return _emit_upsert_merge(node, oc, dialect)


def _emit_upsert_pg(node: InsertStatement, oc: OnConflictClause) -> str:
    core = _emit_insert_core(node, "postgresql")
    if oc.action == "nothing":
        # DO NOTHING needs no target (fires on any constraint); keep an
        # explicit one when the source named it.
        target = f" ({', '.join(oc.key_columns)})" if oc.key_columns else ""
        return f"{core}\nON CONFLICT{target} DO NOTHING"
    key = _resolve_conflict_key(node, oc)
    if not key:
        return _degrade_upsert(
            node,
            "postgresql",
            "PG ON CONFLICT DO UPDATE needs a conflict target and none was declared "
            "in-script",
        )
    set_items = [
        f"{_ident_if_plain(col, 'postgresql')} = {_emit_expression(val, 'postgresql')}"
        for col, val in oc.assignments
    ]
    where = f" WHERE {_emit_condition(oc.where, 'postgresql')}" if oc.where else ""
    clause = (
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {', '.join(set_items)}{where}"
    )
    note = ""
    if not oc.key_columns:
        # A faithful mapping with a caveat — inline /* … */ so it survives the
        # embedded-DML faithfulness check yet still reconciles to a warning.
        note = (
            " /* UNIQUE-1022: conflict target assumed to be "
            f"({', '.join(key)}) from the table's key; the MySQL source names "
            "no explicit target (fires on any unique key) */"
        )
    return f"{core}\n{clause}{note}"


def _emit_upsert_mysql(node: InsertStatement, oc: OnConflictClause) -> str:
    if oc.action == "nothing":
        core = _emit_insert_core(node, "mysql", insert_kw="INSERT IGNORE INTO")
        return (
            f"{core}\n/* UNIQUE-1023: INSERT IGNORE also swallows other errors "
            "(bad values, FK violations), not only duplicate keys — unlike PG ON "
            "CONFLICT DO NOTHING */"
        )
    if oc.where is not None:
        return _degrade_upsert(
            node,
            "mysql",
            "MySQL ON DUPLICATE KEY UPDATE has no conditional (WHERE) form",
        )
    core = _emit_insert_core(node, "mysql")
    set_items = [
        f"{_ident_if_plain(col, 'mysql')} = {_emit_expression(val, 'mysql')}"
        for col, val in oc.assignments
    ]
    clause = f"ON DUPLICATE KEY UPDATE {', '.join(set_items)}"
    note = (
        " /* UNIQUE-1024: MySQL ON DUPLICATE KEY UPDATE fires on ANY unique/primary "
        "key, not a single named conflict target */"
    )
    return f"{core}\n{clause}{note}"


def _upsert_merge_source(node: InsertStatement, dialect: str) -> str | None:
    """The ``USING <relation> <alias>`` fragment feeding the lowered MERGE, with
    the source columns exposed under the target column names. ``None`` when the
    source cannot be aliased (unknown column count)."""
    cols = list(node.columns)
    if not cols:
        return None
    alias = _UPSERT_SRC_ALIAS
    col_list = ", ".join(_ident_if_plain(c, dialect) for c in cols)
    all_empty = bool(node.values) and all(len(row) == 0 for row in node.values)
    if node.values and not all_empty:
        rendered_rows = []
        for row in node.values:
            if len(row) != len(cols):
                return None
            cells = []
            for i, v in enumerate(row):
                v = _coerce_bit_literal(node.table, cols[i], v, dialect)
                v = _coerce_date_literal(node.table, cols[i], v, dialect)
                cells.append(_emit_value_expression(v, dialect))
            rendered_rows.append(cells)
        if dialect == "oracle":
            # Oracle has no VALUES table constructor in USING; SELECT … FROM DUAL.
            selects = [
                "SELECT "
                + ", ".join(
                    f"{c} AS {_ident_if_plain(cols[i], dialect)}"
                    for i, c in enumerate(cell)
                )
                + " FROM DUAL"
                for cell in rendered_rows
            ]
            return f"USING ({' UNION ALL '.join(selects)}) {alias}"
        rows_sql = ", ".join(f"({', '.join(cell)})" for cell in rendered_rows)
        return f"USING (VALUES {rows_sql}) AS {alias} ({col_list})"
    if node.select is not None:
        if dialect == "oracle":
            # Oracle rejects a derived-table column-alias list; alias inside.
            aliased = _alias_select_columns(node.select, cols)
            if aliased is None:
                return None
            return f"USING ({_emit_select(aliased, dialect)}) {alias}"
        return f"USING ({_emit_select(node.select, dialect)}) AS {alias} ({col_list})"
    return None


def _alias_select_columns(
    select: SelectStatement, cols: list[str]
) -> SelectStatement | None:
    """Re-alias a SELECT's projection to *cols* (Oracle MERGE source, which
    can't take a derived-table column list). ``None`` when the arity differs or
    a star makes the columns unknown."""
    if len(select.columns) != len(cols):
        return None
    new_cols: list[ASTNode] = []
    for item, name in zip(select.columns, cols, strict=True):
        inner = item.expression if isinstance(item, Alias) else item
        if isinstance(inner, Star):
            return None
        new_cols.append(Alias(expression=inner, name=name))
    return dataclasses.replace(select, columns=tuple(new_cols))


def _emit_upsert_merge(
    node: InsertStatement, oc: OnConflictClause, dialect: str
) -> str:
    key = _resolve_conflict_key(node, oc)
    if not key:
        return _degrade_upsert(
            node,
            dialect,
            "upsert has no conflict key to build a MERGE ON condition and none was "
            "declared in-script",
        )
    using = _upsert_merge_source(node, dialect)
    if using is None:
        return _degrade_upsert(
            node, dialect, "upsert source cannot be modeled as a MERGE source"
        )
    tgt = _emit_table_ref(node.table, dialect)
    ta, sa = _UPSERT_TGT_ALIAS, _UPSERT_SRC_ALIAS
    on_terms = " AND ".join(
        f"{ta}.{_ident_if_plain(k, dialect)} = {sa}.{_ident_if_plain(k, dialect)}"
        for k in key
    )
    on_clause = f"({on_terms})" if dialect == "oracle" else on_terms
    tgt_ref = f"{tgt} {ta}" if dialect == "oracle" else f"{tgt} AS {ta}"
    whens: list[str] = []
    if oc.action == "update":
        set_items = [
            f"{ta}.{_ident_if_plain(col, dialect)} = {_emit_expression(val, dialect)}"
            for col, val in oc.assignments
        ]
        cond = f" AND ({_emit_condition(oc.where, dialect)})" if oc.where else ""
        whens.append(f"WHEN MATCHED{cond} THEN UPDATE SET {', '.join(set_items)}")
    insert_cols = ", ".join(_ident_if_plain(c, dialect) for c in node.columns)
    insert_vals = ", ".join(f"{sa}.{_ident_if_plain(c, dialect)}" for c in node.columns)
    whens.append(f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})")
    merge = f"MERGE INTO {tgt_ref}\n{using}\nON {on_clause}\n" + "\n".join(whens)
    if dialect == "tsql":
        merge += ";"  # T-SQL requires the MERGE statement to be ;-terminated.
    note = ""
    if not oc.key_columns:
        note = (
            " /* UNIQUE-1025: MERGE ON key assumed to be "
            f"({', '.join(key)}) from the table's key; the source names no "
            "explicit conflict target */"
        )
    return merge + note


def _wrap_mysql_update_self_ref(val: ASTNode, target: str) -> ASTNode:
    """MySQL error 1093: a subquery in SET can't select FROM the UPDATE target.
    Wrap an aliased target-table FROM reference in a derived table
    (``FROM t x`` -> ``FROM (SELECT * FROM t) x``) to force materialization so
    the correlated subquery is allowed; the outer correlation is unaffected."""
    if not isinstance(val, SubqueryExpression):
        return val
    sel = val.query
    fc = sel.from_clause
    if (
        isinstance(fc, TableRef)
        and fc.function is None
        and fc.name == target
        and fc.alias
        and fc.alias != target
    ):
        derived = SubqueryExpression(
            query=SelectStatement(
                columns=(Star(),),
                from_clause=dataclasses.replace(fc, alias=None),
            ),
            alias=fc.alias,
        )
        return dataclasses.replace(
            val, query=dataclasses.replace(sel, from_clause=derived)
        )
    return val


def _emit_join_table_ref(table: TableRef | SubqueryExpression, dialect: str) -> str:
    """Emit a join's source table, whether a plain table or a subquery."""
    if isinstance(table, SubqueryExpression):
        # The derived table's alias must survive (references break without
        # it, and MySQL requires every derived table to be aliased).
        alias = f" {table.alias}" if table.alias else ""
        inner_sql = _emit_select(table.query, dialect)
        if dialect == "tsql" and not re.search(r"(?i)\bTOP\b", inner_sql):
            # Same 1033 rule as the FROM-position derived table.
            inner_sql = re.sub(r"(?is)\s+ORDER\s+BY\s+[^()]*$", "", inner_sql)
        return f"({inner_sql}){alias}"
    return _emit_table_ref(table, dialect)


def _remodel_update_from(sql: str, dialect: str) -> str | None:
    """Re-parse a stripped ``UPDATE … SET … FROM …`` base through the modeled
    converter so an aliased/self-join source becomes the target's own
    multi-table UPDATE spelling. Returns None when the base is not an
    UPDATE-with-source or does not re-parse cleanly."""
    if not re.search(r"(?is)\bUPDATE\b.*\bSET\b.*\bFROM\b", sql):
        return None
    from unique.core.converter.convert import parse_sql

    src = SOURCE_DIALECT.get() or "postgresql"
    try:
        parsed = parse_sql(sql, src)
    except Exception:  # noqa: BLE001 - fall back to the regex rewrite
        return None
    node = parsed[0] if isinstance(parsed, list) else parsed
    if isinstance(node, UpdateStatement) and (
        node.from_clause is not None or node.joins
    ):
        return _emit_cross_table_update(node, dialect)
    return None


def _emit_cross_table_update(node: UpdateStatement, dialect: str) -> str:
    """Render a cross-table UPDATE (``UPDATE ... SET ... FROM/JOIN``) per engine.

    The T-SQL target alias usually names the same table as the FROM's first
    source (``UPDATE il SET il.c = p.c FROM invoice_line il JOIN product p``).
    We treat that first source as the table being updated and the remaining
    joins as the source side.
    """
    target = _cross_update_target(node)
    assignments = [
        (
            col,
            _emit_expression(
                _coerce_date_literal(
                    target, col, _coerce_bit_literal(target, col, val, dialect), dialect
                ),
                dialect,
            ),
        )
        for col, val in node.assignments
    ]

    if dialect == "oracle":
        return _emit_update_oracle_subquery(node, target, assignments)
    if dialect == "mysql":
        return _emit_update_mysql_join(node, target, assignments, dialect)
    if dialect == "postgresql":
        return _emit_update_postgres_from(node, target, assignments, dialect)
    # T-SQL (and any other) keeps the native UPDATE ... FROM ... JOIN form.
    return _emit_update_tsql_from(node, assignments, dialect)


def _join_predicates(node: UpdateStatement, dialect: str) -> list[str]:
    """Collect every join ON condition as a list of boolean SQL fragments."""
    preds: list[str] = []
    for join in node.joins:
        if join.condition is not None:
            preds.append(_emit_expression(join.condition, dialect))
    return preds


def _emit_update_postgres_from(
    node: UpdateStatement,
    target: TableRef,
    assignments: list[tuple[str, str]],
    dialect: str,
) -> str:
    """PostgreSQL: UPDATE t SET c = s.c FROM s [, ...] WHERE <join preds>."""
    target_sql = _emit_table_ref(target, dialect)
    sets = ", ".join(f"{col} = {val}" for col, val in assignments)
    sources = []
    # A FROM source distinct from the target (a self-join ``… FROM t AS v2``)
    # lives in from_clause, not joins — it must still be listed as a source.
    if node.from_clause is not None and node.from_clause is not target:
        sources.append(_emit_join_table_ref(node.from_clause, dialect))
    sources += [_emit_join_table_ref(j.table, dialect) for j in node.joins]
    result = f"UPDATE {target_sql}\nSET {sets}"
    if sources:
        result += f"\nFROM {', '.join(sources)}"
    conditions = _join_predicates(node, dialect)
    if node.where is not None:
        conditions.append(_emit_expression(node.where, dialect))
    if conditions:
        result += f"\nWHERE {' AND '.join(conditions)}"
    return result


def _emit_update_mysql_join(
    node: UpdateStatement,
    target: TableRef,
    assignments: list[tuple[str, str]],
    dialect: str,
) -> str:
    """MySQL multi-table UPDATE: ``UPDATE t [, s] [JOIN j ON …] SET … WHERE``.

    A source with an ON condition stays a JOIN (``UPDATE t JOIN s ON …``); a
    comma/cross source and a self-join FROM source join the comma table list
    (their correlation stays in WHERE). The SET target column is qualified
    with the target alias so it is not ambiguous across the listed tables.
    """
    comma_tables = [_emit_table_ref(target, dialect)]
    # A self-join FROM source (distinct from the target) is not in joins.
    if node.from_clause is not None and node.from_clause is not target:
        comma_tables.append(_emit_join_table_ref(node.from_clause, dialect))
    join_clauses: list[str] = []
    for j in node.joins:
        if (
            j.condition is None
            and not j.using
            and not j.natural
            and j.join_type in (JoinType.INNER, JoinType.CROSS)
        ):
            comma_tables.append(_emit_join_table_ref(j.table, dialect))
        else:
            join_clauses.append(_emit_join(j, dialect))
    multi = len(comma_tables) > 1 or bool(join_clauses)
    tgt_alias = target.alias or target.name

    def _qualify(col: str) -> str:
        return f"{tgt_alias}.{col}" if multi and "." not in col else col

    sets = ", ".join(f"{_qualify(col)} = {val}" for col, val in assignments)
    result = f"UPDATE {', '.join(comma_tables)}"
    for jc in join_clauses:
        result += f"\n{jc}"
    result += f"\nSET {sets}"
    if node.where is not None:
        result += f"\nWHERE {_emit_condition(node.where, dialect)}"
    return result


def _emit_update_tsql_from(
    node: UpdateStatement,
    assignments: list[tuple[str, str]],
    dialect: str,
) -> str:
    """T-SQL: UPDATE t SET t.c = s.c FROM t JOIN s ON ... [WHERE ...]."""
    table = _emit_table_ref(node.table, dialect)
    sets = ", ".join(f"{col} = {val}" for col, val in assignments)
    if node.table.alias and node.from_clause is not None:
        # T-SQL takes no AS alias on the UPDATE target (error 156) —
        # its aliased spelling names the alias and binds it in FROM
        # (wave 197: ``UPDATE v AS v1 SET … FROM v v2`` shipped raw).
        result = f"UPDATE {node.table.alias}\nSET {sets}"
        from_sql = _emit_table_ref(node.from_clause, dialect)
        joins_sql = "".join(f"\n{_emit_join(j, dialect)}" for j in node.joins)
        # When the FROM's first source IS the target (MySQL ``UPDATE t t1 JOIN …``
        # lifts the target's own join), it already binds the alias — re-listing
        # the target table would duplicate it (``FROM t t1, t t1 JOIN …``).
        if (
            node.from_clause.name == node.table.name
            and node.from_clause.alias == node.table.alias
        ):
            result += f"\nFROM {from_sql}{joins_sql}"
        else:
            result += f"\nFROM {table}, {from_sql}{joins_sql}"
        if node.where is not None:
            result += f"\nWHERE {_emit_condition(node.where, dialect)}"
        return result
    result = f"UPDATE {table}\nSET {sets}"
    if node.from_clause is not None:
        from_sql = _emit_table_ref(node.from_clause, dialect)
        joins_sql = "".join(f"\n{_emit_join(j, dialect)}" for j in node.joins)
        result += f"\nFROM {from_sql}{joins_sql}"
    if node.where is not None:
        result += f"\nWHERE {_emit_condition(node.where, dialect)}"
    return result


def _emit_update_oracle_subquery(
    node: UpdateStatement,
    target: TableRef,
    assignments: list[tuple[str, str]],
) -> str:
    """Oracle has no UPDATE ... FROM; use a correlated-subquery UPDATE.

    Each assigned value is rewritten as ``(SELECT <expr> FROM <sources>
    WHERE <first join pred>)`` and an EXISTS guard limits the update to rows
    that have a match. The first join's ON is the predicate correlating the
    sources to the update target; any further joins chain *between* sources,
    so they move inside the subquery's FROM. Falls back to a documented
    comment only for a join without an ON condition.
    """
    dialect = "oracle"
    target_sql = _emit_table_ref(target, dialect)

    if not node.joins or any(j.condition is None for j in node.joins):
        original = _emit_update_tsql_from(node, assignments, dialect)
        commented = _comment_block(original)
        return (
            "-- UNIQUE-1026: Oracle has no UPDATE ... FROM and this join shape (no ON "
            "condition) cannot become a correlated subquery; rewrite "
            "as a MERGE. Original:\n" + commented
        )

    first, rest = node.joins[0], node.joins[1:]
    source_sql = _emit_join_table_ref(first.table, dialect)
    for j in rest:
        source_sql += f" {_emit_join(j, dialect)}"
    assert first.condition is not None  # guarded by the check above
    pred = _emit_expression(first.condition, dialect)

    set_items = ", ".join(
        f"{col} = (SELECT {val} FROM {source_sql} WHERE {pred})"
        for col, val in assignments
    )
    result = f"UPDATE {target_sql}\nSET {set_items}"
    conditions = [f"EXISTS (SELECT 1 FROM {source_sql} WHERE {pred})"]
    if node.where is not None:
        conditions.append(_emit_expression(node.where, dialect))
    result += f"\nWHERE {' AND '.join(conditions)}"
    return result


def _plain_int_value(node: ASTNode) -> int | None:
    """The integer value of a literal (or unary-minus literal), else None."""
    if isinstance(node, UnaryOp) and node.operator == UnaryOperator.NEGATIVE:
        inner = _plain_int_value(node.operand)
        return None if inner is None else -inner
    if isinstance(node, Literal):
        try:
            return int(str(node.value))
        except (TypeError, ValueError):
            return None
    return None


def _map_system_global(sql: str, dialect: str) -> str | None:
    """Map a bare system global (@@ROWCOUNT/@@ERROR/SQL%ROWCOUNT) in a DML
    fragment — they lived only in the procedural maps and shipped raw off
    their engine. MySQL has a real SQL function; PG/Oracle only have
    PL-context forms, so a documented neutral is the honest top-level."""
    stripped = sql.strip()
    upper = stripped.upper()
    if upper == "@@ROWCOUNT" and dialect != "tsql":
        if dialect == "mysql":
            return "ROW_COUNT()"
        return f"0 /* UNIQUE-1027: @@ROWCOUNT has no top-level {dialect} equivalent */"
    if upper == "@@FETCH_STATUS" and dialect != "tsql":
        # Cursor-contextual by nature; the procedural path maps it with
        # surrounding state. Context-free there is only the neutral.
        return (
            f"0 /* UNIQUE-1028: @@FETCH_STATUS has no top-level {dialect} "
            "equivalent; it is cursor state */"
        )
    if upper == "@@ERROR" and dialect != "tsql":
        return (
            f"0 /* UNIQUE-1029: @@ERROR has no top-level {dialect} equivalent; "
            "use an exception handler */"
        )
    if upper == "@@IDENTITY" and dialect != "tsql":
        # The last identity inserted in the session — the same "last generated
        # id" the SCOPE_IDENTITY() function maps to (PG LASTVAL() / MySQL
        # LAST_INSERT_ID() / Oracle CURRVAL carrier). Shipped raw it was
        # ``@@IDENTITY`` -> PG 'column "identity" does not exist' / ORA-00936.
        from unique.core.mappings import LAST_IDENTITY_EXPR

        return LAST_IDENTITY_EXPR[dialect]
    if upper == "@@VERSION" and dialect != "tsql":
        # PG/MySQL have a version function; the string it returns is engine
        # specific, so the value cannot match T-SQL's. Oracle's is in v$version
        # (needs a query + privileges) — a documented NULL is the honest neutral.
        fn = {"postgresql": "version()", "mysql": "VERSION()"}.get(dialect)
        if fn:
            return (
                f"{fn} /* UNIQUE-1030: @@VERSION -> {fn}; "
                "version string differs per engine */"
            )
        return (
            "NULL /* UNIQUE-1031: @@VERSION has no Oracle equivalent outside v$version "
            "*/"
        )
    if upper == "@@SPID" and dialect != "tsql":
        # Session/connection id — every engine spells it differently and the
        # value is per-connection, so it can never equal T-SQL's @@SPID.
        fn = {
            "postgresql": "pg_backend_pid()",
            "mysql": "CONNECTION_ID()",
            "oracle": "SYS_CONTEXT('USERENV', 'SID')",
        }[dialect]
        return f"{fn} /* UNIQUE-1032: @@SPID -> {fn}; session id differs per engine */"
    if re.fullmatch(r"(?i)SQL\s*%\s*ROWCOUNT", stripped) and dialect != "oracle":
        if dialect == "tsql":
            return "@@ROWCOUNT"
        if dialect == "mysql":
            return "ROW_COUNT()"
        return (
            f"0 /* UNIQUE-1033: SQL%ROWCOUNT has no top-level {dialect} equivalent */"
        )
    return None


def _emit_join(
    join: JoinClause,
    dialect: str,
    left_name: str | None = None,
    merged_cols: dict[str, str] | None = None,
) -> str:
    """Emit a JOIN clause.

    ``left_name`` is the FROM relation's name/alias; with ``merged_cols``
    (shared across a SELECT's join chain, mapping USING column ->
    merged-column expression) it lets a ``USING (...)`` join be rewritten
    as an explicit ``ON`` for T-SQL, which has no USING syntax — chained
    joins included, where a later USING references the chain's MERGED
    column (COALESCE over the arms once a FULL join is involved).
    """
    if join.lateral and isinstance(join.table, SubqueryExpression):
        sub = f"({_emit_select(join.table.query, dialect)})"
        lat_alias = join.alias or join.table.alias or ""
        alias_sql = f" {_ident(lat_alias, False, dialect)}" if lat_alias else ""
        cond_is_true = join.condition is None or (
            isinstance(join.condition, Literal)
            and join.condition.dtype == "boolean"
            and bool(join.condition.value)
        )
        if dialect in ("tsql", "oracle") and cond_is_true:
            keyword = (
                "OUTER APPLY" if join.join_type == JoinType.LEFT else "CROSS APPLY"
            )
            return f"{keyword} {sub}{alias_sql}"
        side = {
            JoinType.LEFT: "LEFT JOIN",
            JoinType.CROSS: "CROSS JOIN",
        }.get(join.join_type, "JOIN")
        if side == "JOIN" and cond_is_true:
            # A comma-joined LATERAL arrives as an unconditioned inner
            # join; bare ``JOIN LATERAL`` without ON is invalid on the
            # engines that spell LATERAL (wave 111).
            side = "CROSS JOIN"
        result = f"{side} LATERAL {sub}{alias_sql}"
        if join.condition is not None and side != "CROSS JOIN":
            result += f" ON {_emit_condition(join.condition, dialect)}"
        return result

    type_map = {
        JoinType.INNER: "INNER JOIN",
        JoinType.LEFT: "LEFT JOIN",
        JoinType.RIGHT: "RIGHT JOIN",
        JoinType.FULL: "FULL OUTER JOIN",
        JoinType.CROSS: "CROSS JOIN",
        JoinType.NATURAL: "NATURAL JOIN",
        JoinType.LATERAL: "LATERAL JOIN",
    }
    join_type = type_map.get(join.join_type, "JOIN")
    if join.natural and join.join_type != JoinType.NATURAL:
        # MySQL rejects "NATURAL INNER JOIN"; the bare spelling is
        # valid on every engine that has NATURAL at all.
        join_type = (
            "NATURAL JOIN" if join_type == "INNER JOIN" else f"NATURAL {join_type}"
        )

    if isinstance(join.table, SubqueryExpression):
        sub_query = join.table.query
        if dialect in ("tsql", "oracle"):
            # A derived table may not carry ORDER BY without a row limit
            # (T-SQL error 1033 / Oracle ORA-00907 in this position); with
            # no LIMIT the ordering cannot change the join's result set.
            sub_query = _strip_unlimited_order_by(sub_query)
        table = f"({_emit_select(sub_query, dialect)})"
        # A subquery has no TableRef to carry the alias, so add it here
        # (the SubqueryExpression's own alias — e.g. a VALUES relation's —
        # when the JoinClause carries none).
        alias = join.alias or join.table.alias
        if not alias and dialect in ("tsql", "mysql"):
            # Both engines demand an alias on a derived table (error
            # 102 / 1248) — PG tolerates the bare form (wave 205).
            alias = "uq_j"
        if alias:
            table += f" {_ident(alias, False, dialect)}"
    else:
        # _emit_table_ref already renders the table's own alias; adding
        # join.alias again would duplicate it ("t2 b b").
        table = _emit_table_ref(join.table, dialect)
        if join.alias and not join.table.alias:
            table += f" {_ident(join.alias, False, dialect)}"

    # A comma join parses as a bare Join with neither kind nor condition.
    # "INNER JOIN b" without ON is a syntax error on PostgreSQL/Oracle; the
    # faithful spelling of a comma join is CROSS JOIN (the WHERE clause
    # still applies the predicates). (audit 2026-07-02, S1-2)
    if (
        join.condition is None
        and not join.using
        and not join.natural
        and join.join_type == JoinType.INNER
    ):
        join_type = "CROSS JOIN"

    result = f"{join_type} {table}"

    right = join.alias or (
        (join.table.alias or join.table.name)
        if isinstance(join.table, TableRef)
        else join.table.alias if isinstance(join.table, SubqueryExpression) else None
    )

    if join.condition:
        result += f" ON {_emit_condition(join.condition, dialect)}"
    elif join.using:
        if dialect == "tsql" and left_name and right:
            # T-SQL has no USING; expand to the equivalent ON predicate
            # against the chain's merged column so far.
            merged = merged_cols if merged_cols is not None else {}
            on_parts = []
            for c in join.using:
                left_expr = merged.get(c.lower(), f"{left_name}.{c}")
                on_parts.append(f"{left_expr} = {right}.{c}")
                if join.join_type == JoinType.FULL:
                    merged[c.lower()] = f"COALESCE({left_expr}, {right}.{c})"
                elif join.join_type == JoinType.RIGHT:
                    merged[c.lower()] = f"{right}.{c}"
                else:
                    merged[c.lower()] = left_expr
            result += f" ON {' AND '.join(on_parts)}"
        else:
            result += f" USING ({', '.join(join.using)})"

    return result


def _emit_order_item(
    item: OrderByItem,
    dialect: str,
    collate: str | None = None,
    lower: bool = False,
) -> str:
    """Emit an ORDER BY item.

    PostgreSQL/Oracle default to NULLS LAST ascending and NULLS FIRST
    descending; when the source's NULL ordering (carried in ``nulls_first``)
    differs, it must be spelled out or the row order silently changes.
    T-SQL/MySQL have no NULLS FIRST/LAST syntax, so it is omitted there
    (same as a raw sqlglot transpile). ``collate`` forces a collation on the key;
    ``lower`` wraps it in LOWER() (a case-insensitive source on a CS target).
    """
    expr = _emit_expression(item.expression, dialect)
    if lower:
        expr = f"LOWER({expr})"
    elif collate:
        expr = f"{expr} COLLATE {collate}"
    direction = "DESC" if item.direction == OrderDirection.DESC else "ASC"
    out = f"{expr} {direction}"
    if item.nulls_first is not None and dialect in ("postgresql", "oracle"):
        target_default_first = item.direction == OrderDirection.DESC
        if item.nulls_first != target_default_first:
            out += " NULLS FIRST" if item.nulls_first else " NULLS LAST"
    return out


def _order_null_priority_key(item: OrderByItem, dialect: str) -> str | None:
    """Emulate a source's implicit NULL ordering on MySQL/T-SQL.

    Oracle/PostgreSQL sort NULLs HIGH by default (LAST ascending, FIRST
    descending); MySQL/T-SQL sort them LOW and have no NULLS FIRST/LAST keyword.
    When the source placement (carried in ``nulls_first``) differs from the
    MySQL/T-SQL default, the row order silently flips. Return a leading
    null-priority ORDER BY key (``CASE WHEN expr IS NULL THEN …``) that restores
    it, or ``None`` when no emulation is needed. Positional ordinals carry no
    NULLs to reorder, so they are skipped.

    Only sound for a *statement-level* ORDER BY — never a window ORDER BY (it
    would change the frame's peer groups) and never under T-SQL ``DISTINCT`` (the
    added expression is not in the select list); callers gate those out.
    """
    if item.nulls_first is None or dialect not in ("mysql", "tsql"):
        return None
    if isinstance(item.expression, Literal) and _is_nonneg_int_literal(item.expression):
        return None
    target_default_first = item.direction != OrderDirection.DESC
    if item.nulls_first == target_default_first:
        return None
    expr = _emit_expression(item.expression, dialect)
    priority = "0 ELSE 1" if item.nulls_first else "1 ELSE 0"
    return f"CASE WHEN {expr} IS NULL THEN {priority} END"


def _emit_limit(limit: LimitClause, dialect: str) -> str:
    """Emit LIMIT/OFFSET clause in dialect-appropriate syntax."""
    if dialect == "oracle":
        parts = []
        if limit.offset:
            parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)} ROWS")
        if limit.limit:
            # Oracle natively supports FETCH FIRST n PERCENT ROWS ONLY / WITH TIES.
            pct = " PERCENT" if limit.percent else ""
            tail = "WITH TIES" if limit.with_ties else "ONLY"
            parts.append(
                f"FETCH FIRST {_emit_expression(limit.limit, dialect)}{pct} ROWS {tail}"
            )
        return "\n".join(parts)

    if dialect == "tsql":
        # T-SQL uses TOP or OFFSET...FETCH
        if limit.offset:
            parts = [f"OFFSET {_emit_expression(limit.offset, dialect)} ROWS"]
            if limit.limit:
                parts.append(
                    f"FETCH NEXT {_emit_expression(limit.limit, dialect)} ROWS ONLY"
                )
            return "\n".join(parts)
        # A plain limit was already emitted as TOP in the SELECT clause.
        if limit.limit:
            return ""

    # WITH TIES needs the SQL:2008 FETCH FIRST form. PostgreSQL (13+) supports it
    # natively; a plain LIMIT would silently drop the tied rows.
    if limit.with_ties and limit.limit is not None:
        if dialect == "postgresql":
            parts = []
            if limit.offset:
                parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)} ROWS")
            parts.append(
                f"FETCH FIRST {_emit_expression(limit.limit, dialect)} ROWS WITH TIES"
            )
            return "\n".join(parts)
        if dialect == "mysql":
            # MySQL has no WITH TIES; keep the row limit but flag the dropped ties
            # rather than silently returning fewer rows.
            limit_sql = f"LIMIT {_emit_expression(limit.limit, dialect)}"
            limit_sql += (
                " /* UNIQUE-1037: source had WITH TIES; MySQL has no equivalent — rows "
                "tying the last one are not returned (see docs/03-unsupported.md) */"
            )
            out = [limit_sql]
            if limit.offset:
                out.append(f"OFFSET {_emit_expression(limit.offset, dialect)}")
            return "\n".join(out)

    # PostgreSQL, MySQL: LIMIT ... OFFSET ...
    parts = []
    if dialect == "mysql" and limit.offset is not None and limit.limit is None:
        # MySQL has no bare OFFSET — the documented all-rows idiom is
        # LIMIT <2^64-1> OFFSET n (wave 192).
        parts.append("LIMIT 18446744073709551615")
    if limit.limit:
        limit_sql = f"LIMIT {_emit_expression(limit.limit, dialect)}"
        if limit.percent:
            # Neither MySQL nor PostgreSQL supports LIMIT n PERCENT. A faithful
            # rewrite needs the total row count (LIMIT CEIL(n/100 * COUNT(*))),
            # which can't be derived from a flat SELECT here; keep a valid row
            # LIMIT and document the change rather than emit invalid SQL or
            # silently drop the PERCENT semantics.
            limit_sql += (
                f" /* UNIQUE-1038: source was TOP n PERCENT; {dialect} has no LIMIT "
                "PERCENT — emitted as a row count, adjust to CEIL(n/100 * total_rows) "
                "if a true percentage is required */"
            )
        parts.append(limit_sql)
    if limit.offset:
        parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Emitter seam modules (audit doc 04 F4 split — 09-fix-briefs.md B17 step 4).
# The heavy families were moved verbatim out of this module for size and are
# re-exported here (``import *``) so the converter façade and this module's own
# dispatchers keep resolving them by bare name. Each seam imports the emit.py
# helpers and sibling emitters it needs explicitly at its own tail; the mutual
# recursion resolves because every module finishes defining its own names
# before importing any other — see this module's docstring.
# ---------------------------------------------------------------------------
from unique.core.converter.emit_ddl import *  # noqa: E402,F401,F403
from unique.core.converter.emit_expr import *  # noqa: E402,F401,F403
from unique.core.converter.emit_functions import *  # noqa: E402,F401,F403
from unique.core.converter.emit_passthrough import *  # noqa: E402,F401,F403
from unique.core.converter.emit_relations import *  # noqa: E402,F401,F403
