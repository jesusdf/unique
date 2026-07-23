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
from typing import cast

import sqlglot
import sqlglot.expressions as exp

from unique.core.ast_nodes import (
    Alias,
    ArrayLiteral,
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CaseExpression,
    CastExpression,
    ColumnDefinition,
    ColumnRef,
    CommentStatement,
    CreateTableStatement,
    CreateViewStatement,
    CTEDefinition,
    DataType,
    DeleteStatement,
    DropStatement,
    ExpressionList,
    FunctionCall,
    InsertStatement,
    JoinClause,
    JoinType,
    LimitClause,
    Literal,
    OrderByItem,
    OrderDirection,
    PassthroughSQL,
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
    UnsupportedInline,
    UpdateStatement,
    WindowFunction,
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
from unique.core.mappings import (
    CURRENT_DATE_EXPR,
    CURRENT_TIMESTAMP_EXPR,
    DML_FOUND_EXPR,
    ERROR_DIAGNOSTIC_EXPRS,
    ERROR_DIAGNOSTIC_SOURCES,
    ERROR_MESSAGE_EXPR,
    ERROR_MESSAGE_SOURCES,
    LAST_IDENTITY_EXPR,
    LAST_IDENTITY_SOURCE_FUNCS,
    ORACLE_DATE_FORMAT_STYLES,
    TSQL_OBJECT_CONTEXT_WORDS,
    tsql_call_needs_schema,
)
from unique.core.sql_split import qualify_function_calls

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
        dst_name = dst.split("(")[0]
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
            "data-modifying CTEs (WITH x AS (INSERT/UPDATE/DELETE … "
            "RETURNING)) are PostgreSQL-only; run the DML separately and "
            "read its result from a table."
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
            "Oracle has no WITH clause on UPDATE/DELETE; inline the CTE as a "
            "subquery or rewrite as a MERGE."
        )
    return None


_ORACLE_MODIFY_RE = re.compile(
    r"(?is)^\s*ALTER\s+TABLE\s+(?P<table>[\w.\"]+)\s+MODIFY\s+"
    r"(?:\((?P<parenspec>.+)\)|(?P<spec>[^;]+?))\s*;?\s*$"
)
_MODIFY_COL_RE = re.compile(
    r"(?is)^(?P<col>[\w\"]+)\s*"
    r"(?P<type>(?!NOT\b|NULL\b)[A-Za-z]\w*(?:\s*\(\s*\d+"
    r"(?:\s*,\s*\d+)?\s*\))?)?\s*(?P<null>NOT\s+NULL|NULL)?$"
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


_SEQ_NEXTVAL_RE = re.compile(r"(?i)\b([A-Za-z_]\w*)\s*\.\s*NEXTVAL\b")
_SEQ_CURRVAL_RE = re.compile(r"(?i)\b([A-Za-z_]\w*)\s*\.\s*CURRVAL\b")


def map_sequence_refs(sql: str, dialect: str) -> str:
    """Map Oracle ``seq.NEXTVAL``/``seq.CURRVAL`` to the target's spelling.

    T-SQL: NEXT VALUE FOR seq (no CURRVAL equivalent — left for the
    honesty gate); PostgreSQL: nextval('seq')/currval('seq'). MySQL has no
    sequences at all — left untouched for the existing degradation paths.
    """
    if dialect == "tsql":
        sql = _SEQ_NEXTVAL_RE.sub(r"NEXT VALUE FOR \1", sql)
    elif dialect == "postgresql":
        sql = _SEQ_NEXTVAL_RE.sub(lambda m: f"nextval('{m.group(1).lower()}')", sql)
        sql = _SEQ_CURRVAL_RE.sub(lambda m: f"currval('{m.group(1).lower()}')", sql)
    return sql


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
        return f"-- UNIQUE: {reason}\n{_comment_block(node.sql)}"
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
    """Render a filtered-index predicate in T-SQL's restricted grammar.

    ``NOT x IS NULL`` (sqlglot's model of IS NOT NULL) must spell
    ``x IS NOT NULL`` — the only form CREATE INDEX ... WHERE accepts.
    Returns None for shapes outside that grammar (caller falls back)."""
    if (
        isinstance(pred, exp.Not)
        and isinstance(pred.this, exp.Is)
        and isinstance(pred.this.expression, exp.Null)
    ):
        return f"{pred.this.this.sql(dialect='tsql')} IS NOT NULL"
    if isinstance(pred, exp.Is) and isinstance(pred.expression, exp.Null):
        return f"{pred.this.sql(dialect='tsql')} IS NULL"
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
            f"-- UNIQUE: NULLS FIRST/LAST index ordering has no {dialect} "
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
        r"(?is)\s*/\*\s*UNIQUE:\s*(?P<clauses>.+?)\s*--\s*tsql-only,"
        r"[^*]*?physical index clause[^*]*?\*/",
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
                "T-SQL has no expression indexes (add a computed column "
                "and index it); statement preserved as a comment"
            )
            body = "\n".join(f"-- {line}" for line in sql.strip().splitlines())
            return f"-- UNIQUE: {reason}\n{body}"
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
                return f"-- UNIQUE: {reason}\n{body}"
            dropped_where = (
                "\n-- UNIQUE: partial-index predicate dropped (no "
                f"{dialect} filtered-index form); the index is broader "
                f"than the source's: {where.this.sql(dialect=write)}"
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
            f"{stmt};\n-- UNIQUE: PostgreSQL unique indexes treat NULLs as "
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
        "DECLARE @n SYSNAME; "
        "SELECT @n = dc.name FROM sys.default_constraints dc "
        "JOIN sys.columns c ON c.object_id = dc.parent_object_id "
        "AND c.column_id = dc.parent_column_id "
        f"WHERE dc.parent_object_id = OBJECT_ID('{tn}') AND c.name = '{cn}'; "
        f"IF @n IS NOT NULL EXEC('ALTER TABLE {table} DROP CONSTRAINT ' + @n)"
    )


def _emit_passthrough(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a passthrough statement to the target dialect.

    Uses sqlglot directly (it handles ALTER, CREATE INDEX, CREATE SEQUENCE,
    etc. well). On failure, fall back to a commented passthrough so nothing
    is silently lost.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)

    # T-SQL has no data-modifying CTE — an INSERT/UPDATE/DELETE inside a WITH
    # (PostgreSQL's ``WITH ins AS (INSERT … RETURNING) …``) is invalid there;
    # sqlglot re-transpiles it verbatim. Preserve it as a documented carrier.
    if dialect == "tsql":
        # sqlglot drops the WITH arg when a CTE body is DML (``RETURNING … *``
        # defeats its parse), so detect it on scrubbed text: a statement that
        # starts with WITH and has a CTE body opening with a DML verb.
        _scrubbed = re.sub(r"'(?:[^']|'')*'", "''", node.sql)
        if re.match(r"(?is)^\s*WITH\b", _scrubbed) and re.search(
            r"(?is)\bAS\s*\(\s*(?:INSERT|UPDATE|DELETE|MERGE)\b", _scrubbed
        ):
            _cte_reason = (
                "T-SQL has no data-modifying CTE (INSERT/UPDATE/DELETE "
                "inside WITH); statement preserved as a comment"
            )
            return f"-- UNIQUE: {_cte_reason}\n{_comment_block(node.sql)}"

    # MySQL's STRAIGHT_JOIN is INNER JOIN plus a join-order hint no other
    # engine spells — inside a parenthesized join tree it survived the
    # re-transpile verbatim (wave 179; ORA-00907 / error 102 live).
    if (
        node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.search(r"(?i)\bSTRAIGHT_JOIN\b", node.sql)
    ):
        node = dataclasses.replace(
            node,
            sql=re.sub(r"(?i)\bSTRAIGHT_JOIN\b", "INNER JOIN", node.sql),
        )

    # Oracle/PG have no ``ALTER VIEW … AS`` (ORA-00922; PG alters only
    # properties): redefining a view is CREATE OR REPLACE VIEW there
    # (wave 180). T-SQL/MySQL keep ALTER VIEW.
    if (
        node.kind == "ALTER"
        and dialect in ("oracle", "postgresql")
        and re.match(r"(?is)^\s*ALTER\s+VIEW\b.*\bAS\b", node.sql)
    ):
        node = dataclasses.replace(
            node,
            sql=re.sub(
                r"(?is)^\s*ALTER\s+VIEW\b",
                "CREATE OR REPLACE VIEW",
                node.sql,
                count=1,
            ),
        )

    # ``ALTER TABLE t MODIFY [COLUMN] c <type>`` changes a column's type; sqlglot
    # passes MODIFY COLUMN through unchanged (unsupported on every write dialect).
    # Each engine spells the type change differently:
    #   Oracle      ALTER TABLE t MODIFY c <type>
    #   PostgreSQL  ALTER TABLE t ALTER COLUMN c TYPE <type>
    #   T-SQL       ALTER TABLE t ALTER COLUMN c <type>
    # Only the simple type-only form is rewritten; a modify carrying an inline
    # constraint (NOT NULL / DEFAULT / …) leaves the tail unmatched and falls
    # through to the generic path.
    if node.kind == "ALTER" and dialect != node.source_dialect:
        m_mod = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+MODIFY\s+(?:COLUMN\s+)?"
            r"(\S+)\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)\s*;?\s*$",
            node.sql,
        )
        if m_mod:
            _mt, _mc, _mtype = m_mod.groups()
            _mtype = _portable_types_in_sql(_mtype, dialect)
            if dialect == "oracle":
                return f"ALTER TABLE {_mt} MODIFY {_mc} {_mtype}"
            if dialect == "postgresql":
                return f"ALTER TABLE {_mt} ALTER COLUMN {_mc} TYPE {_mtype}"
            if dialect == "tsql":
                return f"ALTER TABLE {_mt} ALTER COLUMN {_mc} {_mtype}"
            return f"ALTER TABLE {_mt} MODIFY COLUMN {_mc} {_mtype}"

    # ``ALTER TABLE t ALTER COLUMN c SET DEFAULT v``: the MySQL/PostgreSQL-native
    # spelling (T-SQL uses ADD DEFAULT … FOR, handled by the guard/default paths,
    # so this stays gated to those sources). Oracle uses MODIFY c DEFAULT v;
    # T-SQL has no ALTER COLUMN … DEFAULT — a default is a named constraint, so
    # ADD CONSTRAINT … DEFAULT v FOR c (name derived from table+column).
    if (
        node.kind == "ALTER"
        and node.source_dialect in ("mysql", "postgresql")
        and dialect != node.source_dialect
    ):
        m_sd = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
            r"SET\s+DEFAULT\s+(.+?)\s*;?\s*$",
            node.sql,
        )
        if m_sd:
            _t, _c, _v = m_sd.groups()
            if dialect == "oracle":
                return f"ALTER TABLE {_t} MODIFY {_c} DEFAULT {_v}"
            if dialect == "tsql":
                # SET DEFAULT replaces any existing default (MySQL/PG semantics);
                # T-SQL ADD CONSTRAINT would collide (error 1781), so drop the
                # current default constraint (dynamic — name unknown) first.
                _cn = re.sub(r"[^A-Za-z0-9_]", "", _t.split(".")[-1] + "_" + _c)
                return (
                    f"{_tsql_drop_col_default(_t, _c)}; "
                    f"ALTER TABLE {_t} ADD CONSTRAINT DF_{_cn} DEFAULT {_v} FOR {_c}"
                )
            return f"ALTER TABLE {_t} ALTER COLUMN {_c} SET DEFAULT {_v}"

        # PostgreSQL ``ALTER COLUMN c [SET DATA] TYPE t [USING …]`` -> Oracle
        # ``MODIFY c t`` (Oracle has neither the TYPE keyword nor a USING clause;
        # a redundant USING cast IS the target's implicit conversion). The other
        # targets keep the ALTER COLUMN … TYPE spelling (sqlglot handles them).
        if dialect == "oracle":
            m_ty = re.match(
                r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
                r"(?:SET\s+DATA\s+)?TYPE\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)"
                r"(?:\s+USING\b.*)?\s*;?\s*$",
                node.sql,
            )
            if m_ty:
                _t2, _c2, _ty2 = m_ty.groups()
                _ty2 = _portable_types_in_sql(_ty2, "oracle")
                return f"ALTER TABLE {_t2} MODIFY {_c2} {_ty2}"

        # ``ALTER COLUMN c DROP DEFAULT``: Oracle spells it MODIFY c DEFAULT NULL.
        # T-SQL has no column-level drop — a default is a named constraint whose
        # (auto-generated) name is unknown here, so look it up and drop it via
        # dynamic SQL (a no-op when the column has no default, matching MySQL/PG).
        m_dd = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+ALTER\s+COLUMN\s+(\S+)\s+"
            r"DROP\s+DEFAULT\s*;?\s*$",
            node.sql,
        )
        if m_dd:
            _td, _cd = m_dd.groups()
            if dialect == "oracle":
                return f"ALTER TABLE {_td} MODIFY {_cd} DEFAULT NULL"
            if dialect == "tsql":
                return _tsql_drop_col_default(_td, _cd)
            return f"ALTER TABLE {_td} ALTER COLUMN {_cd} DROP DEFAULT"

    # ``ALTER TABLE t CHANGE [COLUMN] old new <type>`` renames a column AND
    # changes its type in one MySQL-only statement. Split into a rename + a type
    # change (the column is ``new`` after the rename); only the simple type-only
    # form is handled, a trailing constraint falls through.
    if node.kind == "ALTER" and node.source_dialect == "mysql" and dialect != "mysql":
        m_ch = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+CHANGE\s+(?:COLUMN\s+)?"
            r"(\S+)\s+(\S+)\s+([A-Za-z0-9_]+(?:\s*\([\d,\s]*\))?)\s*;?\s*$",
            node.sql,
        )
        if m_ch:
            _t, _old, _new, _ty = m_ch.groups()
            _ty = _portable_types_in_sql(_ty, dialect)
            if dialect == "oracle":
                return (
                    f"ALTER TABLE {_t} RENAME COLUMN {_old} TO {_new};\n"
                    f"ALTER TABLE {_t} MODIFY {_new} {_ty}"
                )
            if dialect == "postgresql":
                return (
                    f"ALTER TABLE {_t} RENAME COLUMN {_old} TO {_new};\n"
                    f"ALTER TABLE {_t} ALTER COLUMN {_new} TYPE {_ty}"
                )
            if dialect == "tsql":
                _tn = _t.strip('[]"`')
                _on = _old.strip('[]"`')
                _nn = _new.strip('[]"`')
                return (
                    f"EXEC sp_rename '{_tn}.{_on}', '{_nn}', 'COLUMN';\n"
                    f"ALTER TABLE {_t} ALTER COLUMN {_new} {_ty}"
                )

    # Oracle requires DEFAULT before NOT NULL in a column definition (ORA-30649
    # otherwise); sqlglot keeps the source's ``NOT NULL DEFAULT`` order. Reorder
    # it for an ADD/MODIFY column on Oracle.
    if (
        node.kind == "ALTER"
        and dialect == "oracle"
        and re.search(r"(?is)\bNOT\s+NULL\s+DEFAULT\b", node.sql)
    ):
        try:
            rendered = sqlglot.transpile(node.sql, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else node.sql
        except Exception:  # noqa: BLE001 - keep the source spelling on failure
            base = node.sql
        return re.sub(
            r"(?is)\bNOT\s+NULL\s+DEFAULT\s+('(?:[^']|'')*'|\S+)",
            r"DEFAULT \1 NOT NULL",
            base,
        )

    # MySQL rejects a literal DEFAULT on a TEXT/BLOB/JSON/spatial column (error
    # 1101) — it must be an expression default ``DEFAULT (v)``. Wrap the literal
    # when such a type appears in an ADD/MODIFY column (parenthesizing a literal
    # default is valid for every type on MySQL 8.0.13+, so it is always safe).
    if (
        node.kind == "ALTER"
        and dialect == "mysql"
        and re.search(r"(?i)\bDEFAULT\s+(?!\()", node.sql)
        and re.search(
            r"(?i)\b(?:TINY|MEDIUM|LONG)?TEXT\b|\b(?:TINY|MEDIUM|LONG)?BLOB\b"
            r"|\bJSON\b|\bGEOMETRY\b",
            node.sql,
        )
    ):
        try:
            rendered = sqlglot.transpile(node.sql, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else node.sql
        except Exception:  # noqa: BLE001 - keep the source spelling on failure
            base = node.sql
        return re.sub(
            r"(?i)\bDEFAULT\s+('(?:[^']|'')*'|-?\d+(?:\.\d+)?|TRUE|FALSE)(?!\s*\()",
            r"DEFAULT (\1)",
            base,
        )

    # MySQL's ENFORCED / NOT ENFORCED on a CHECK constraint: ENFORCED is the
    # default (the constraint IS validated) — strip the keyword for every other
    # engine (identical semantics). NOT ENFORCED (defined but skipped) has no
    # equivalent — strip with a carrier so the semantic loss is documented.
    if (
        node.kind == "ALTER"
        and node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.search(r"(?i)\bENFORCED\b", node.sql)
    ):
        not_enforced = re.search(r"(?i)\bNOT\s+ENFORCED\b", node.sql)
        stripped = re.sub(r"(?i)\s*\b(?:NOT\s+)?ENFORCED\b", "", node.sql).rstrip()
        try:
            rendered = sqlglot.transpile(stripped, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else stripped
        except Exception:  # noqa: BLE001 - keep the stripped spelling on failure
            base = stripped
        if dialect == "tsql":
            base = base.rstrip().rstrip(";")
        if not_enforced:
            return (
                f"-- UNIQUE: MySQL NOT ENFORCED (a CHECK that is defined but not "
                f"validated) has no {dialect} equivalent; it is enforced here\n"
                f"{base}"
            )
        return base

    # T-SQL cannot DROP a COLUMN that still has a default constraint (error
    # 5074); other engines drop the default with the column. Drop any default
    # constraint on the column first (dynamic — the name is auto-generated),
    # then drop the column. Only the single-column form is rewritten.
    if node.kind == "ALTER" and dialect == "tsql" and node.source_dialect != "tsql":
        m_drop = re.match(
            r"(?is)^\s*ALTER\s+TABLE\s+(\S+)\s+DROP\s+COLUMN\s+(\S+)\s*;?\s*$",
            node.sql,
        )
        if m_drop:
            _tdc, _cdc = m_drop.groups()
            return (
                f"{_tsql_drop_col_default(_tdc, _cdc)}; "
                f"ALTER TABLE {_tdc} DROP COLUMN {_cdc}"
            )

    # MySQL/PostgreSQL FOR SHARE (a shared row lock) has no Oracle form — Oracle
    # SELECT locking is FOR UPDATE (exclusive) only. Drop it and document the
    # absent shared lock.
    if (
        dialect == "oracle"
        and node.source_dialect in ("mysql", "postgresql")
        and re.search(r"(?i)\bFOR\s+SHARE\b", node.sql)
    ):
        _fs = re.sub(r"(?i)\s*\bFOR\s+SHARE\b", "", node.sql)
        try:
            _fsr = sqlglot.transpile(_fs, read=read, write=write)
            _fsb = _fsr[0] if _fsr and _fsr[0].strip() else _fs
        except Exception:  # noqa: BLE001 - keep the stripped spelling on failure
            _fsb = _fs
        return (
            "-- UNIQUE: FOR SHARE (shared row lock) has no Oracle equivalent "
            "(Oracle SELECT locking is FOR UPDATE, exclusive); the shared lock "
            f"is dropped (docs/03-unsupported.md)\n{_fsb}"
        )

    # Oracle FOR UPDATE WAIT <n> (block up to n seconds for the row lock) has no
    # PostgreSQL/MySQL form — they offer only FOR UPDATE (block) and NOWAIT. Drop
    # the WAIT <n> and document the lost bounded-wait timeout.
    if (
        node.source_dialect == "oracle"
        and dialect in ("postgresql", "mysql")
        and re.search(r"(?i)\bFOR\s+UPDATE\b[\s\S]*\bWAIT\s+\d+", node.sql)
    ):
        _stripped = re.sub(r"(?i)\s*\bWAIT\s+\d+\b", "", node.sql)
        try:
            _rendered = sqlglot.transpile(_stripped, read=read, write=write)
            _base = _rendered[0] if _rendered and _rendered[0].strip() else _stripped
        except Exception:  # noqa: BLE001 - keep the stripped spelling on failure
            _base = _stripped
        return (
            f"-- UNIQUE: Oracle FOR UPDATE WAIT <n> (bounded lock wait) has no "
            f"{dialect} equivalent; it blocks with the default behavior "
            f"(docs/03-unsupported.md)\n{_base}"
        )

    # CREATE INDEX on an EXPRESSION (function-based index): Oracle keeps the
    # native single-parens form; MySQL 8.0.13+/PostgreSQL require the expression
    # in DOUBLE parens; T-SQL has no expression index (it needs a computed
    # column), so it degrades with a carrier. A plain column-list index is
    # unaffected (it has no operator/function, or a top-level comma).
    if node.kind == "CREATE INDEX" and dialect != node.source_dialect:
        m_idx = re.match(
            r"(?is)^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(\S+)\s+ON\s+(\S+)\s*"
            r"\((.*)\)\s*;?\s*$",
            node.sql,
        )
        if m_idx:
            _uni, _iname, _itbl, _itgt = m_idx.groups()
            _itgt = _itgt.strip()
            is_expr = bool(re.search(r"[*/%+]|\|\||\b\w+\s*\(", _itgt)) and (
                "," not in _itgt
            )
            if is_expr:
                _uni = _uni or ""
                if dialect in ("mysql", "postgresql"):
                    return f"CREATE {_uni}INDEX {_iname} ON {_itbl} (({_itgt}))"
                if dialect == "tsql":
                    return (
                        "-- UNIQUE: T-SQL has no expression/function index; add a "
                        "computed column and index it (docs/03-unsupported.md)\n"
                        f"{_comment_block(node.sql)}"
                    )

    # Oracle CREATE SEQUENCE spells its negatives as one word (NOCYCLE, NOCACHE,
    # NOMAXVALUE, NOMINVALUE) and has an ORDER/NOORDER RAC option no other engine
    # shares. PostgreSQL/T-SQL use two words (NO CYCLE, …) and have no ORDER
    # clause — normalize sqlglot's (verbatim) output for them.
    if (
        node.kind == "CREATE SEQUENCE"
        and dialect in ("postgresql", "tsql")
        and node.source_dialect == "oracle"
    ):
        try:
            rendered = sqlglot.transpile(node.sql, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else node.sql
        except Exception:  # noqa: BLE001 - keep the source spelling on failure
            base = node.sql
        base = re.sub(r"(?i)\bNO(CYCLE|CACHE|MAXVALUE|MINVALUE)\b", r"NO \1", base)
        base = re.sub(r"(?i)\s*\b(?:NOORDER|ORDER)\b", "", base)
        return base.rstrip().rstrip(";") if dialect == "tsql" else base

    # T-SQL / PostgreSQL ``SELECT … INTO [TEMP] newtable FROM …`` CREATES a table;
    # Oracle and MySQL have no SELECT-INTO-table form (INTO there targets
    # variables), so rewrite it to CREATE TABLE … AS SELECT (CTAS).
    if node.kind == "SELECT INTO" and dialect in ("oracle", "mysql"):
        m_si = re.match(
            r"(?is)^\s*SELECT\s+(.*?)\s+INTO\s+(TEMP(?:ORARY)?\s+)?"
            r"([\w.\"\[\]#]+)\s+FROM\s+(.*?)\s*;?\s*$",
            node.sql,
        )
        if m_si:
            _sel, _temp, _tbl, _rest = m_si.groups()
            # A T-SQL ``#name`` target is a (session) temp table too.
            _is_temp = bool(_temp) or _tbl.startswith("#")
            _tbl = _tbl.strip('#[]"')
            # Build the CTAS in the SOURCE dialect (TEMPORARY, its own spelling)
            # and let sqlglot map it to the target (Oracle GLOBAL TEMPORARY, …).
            _temp_kw = "TEMPORARY " if _is_temp else ""
            _ctas = f"CREATE {_temp_kw}TABLE {_tbl} AS SELECT {_sel} FROM {_rest}"
            try:
                rendered = sqlglot.transpile(_ctas, read=read, write=write)
                return rendered[0] if rendered and rendered[0].strip() else _ctas
            except Exception:  # noqa: BLE001 - keep the rewritten spelling
                return _ctas

    # PG's NOT VALID (add the constraint but skip validating existing rows) has
    # no equivalent on the other engines, which validate immediately. Strip it —
    # the constraint definition is identical — and document the difference so the
    # loss is never silent.
    if (
        node.kind == "ALTER"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.search(r"(?is)\bNOT\s+VALID\b\s*;?\s*$", node.sql)
    ):
        stripped = re.sub(r"(?is)\s*\bNOT\s+VALID\b\s*;?\s*$", "", node.sql).rstrip()
        try:
            rendered = sqlglot.transpile(stripped, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else stripped
        except Exception:  # noqa: BLE001 - keep the source spelling
            base = stripped
        base = _portable_types_in_sql(base, dialect)
        return (
            f"-- UNIQUE: {dialect} has no ALTER … NOT VALID; the constraint is "
            f"validated immediately (PostgreSQL defers it)\n{base}"
        )

    # PG's TRUNCATE … RESTART IDENTITY / CASCADE. RESTART IDENTITY is the
    # DEFAULT TRUNCATE behavior on MySQL/Oracle/T-SQL (they always reset the
    # identity), so strip it — faithful, no divergence. CASCADE (also truncate
    # FK-dependent tables) exists on Oracle but not MySQL/T-SQL; strip it there
    # with a carrier so the semantic loss is not silent.
    if (
        dialect != "postgresql"
        and re.search(r"(?is)^\s*TRUNCATE\b", node.sql)
        and re.search(r"(?i)\bRESTART\s+IDENTITY\b|\bCASCADE\b", node.sql)
    ):
        stripped = re.sub(r"(?i)\s+RESTART\s+IDENTITY\b", "", node.sql)
        carrier = ""
        if dialect in ("mysql", "tsql") and re.search(r"(?i)\bCASCADE\b", stripped):
            stripped = re.sub(r"(?i)\s+CASCADE\b", "", stripped)
            carrier = (
                f"-- UNIQUE: TRUNCATE … CASCADE (also truncates FK-dependent "
                f"tables) has no {dialect} equivalent; only this table is "
                "truncated — truncate any dependents explicitly\n"
            )
        try:
            rendered = sqlglot.transpile(stripped, read=read, write=write)
            base = rendered[0] if rendered and rendered[0].strip() else stripped
        except Exception:  # noqa: BLE001 - keep the stripped spelling
            base = stripped
        return (
            carrier + base.rstrip().rstrip(";") if dialect == "tsql" else carrier + base
        )

    # Oracle rejects parenthesized join trees in FROM (ORA-00907). For a
    # pure INNER/CROSS tree the flat CROSS-chain + ANDed WHERE is exactly
    # equivalent (wave 185); outer joins keep the paren carrier.
    if node.kind == "PAREN JOIN" and dialect == "oracle":
        flattened = _flatten_paren_joins(node.sql, node.source_dialect)
        if flattened is not None:
            node = dataclasses.replace(node, sql=flattened)

    # T-SQL/MySQL require an alias on every derived table — PG's bare
    # ``FROM ((SELECT 1 AS x))`` shipped alias-less (error 102 / 1248;
    # wave 198). Inject uq_dtN aliases structurally.
    if node.kind == "PAREN JOIN" and dialect in ("tsql", "mysql"):
        aliased = _alias_bare_derived_tables(node.sql, node.source_dialect)
        if aliased is not None:
            node = dataclasses.replace(node, sql=aliased)

    # PG's ALTER COLUMN … TYPE … USING <expr>: no other engine has the
    # conversion clause (wave 199). A redundant ``USING CAST(col AS
    # type)`` strips (the engine's implicit conversion IS that cast);
    # any other expression keeps a documented carrier.
    if (
        node.kind == "ALTER"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.search(r"(?i)\bALTER\s+COLUMN\b.*\bUSING\b", node.sql)
    ):
        m_red = re.search(
            r"(?is)\bALTER\s+COLUMN\s+(\w+)\s+(?:SET\s+DATA\s+)?(?:TYPE\s+)?"
            r"(\w+(?:\([\d,\s]*\))?)\s+USING\s+"
            r"CAST\s*\(\s*\1\s+AS\s+(\w+(?:\([\d,\s]*\))?)\s*\)\s*$",
            node.sql.rstrip().rstrip(";"),
        )
        if m_red and m_red.group(2).upper() == m_red.group(3).upper():
            node = dataclasses.replace(
                node,
                sql=re.sub(
                    r"(?is)\s+USING\s+CAST.*$", "", node.sql.rstrip().rstrip(";")
                ),
            )
        else:
            return (
                f"-- UNIQUE: {dialect} has no ALTER COLUMN … USING conversion "
                f"expression; convert the data manually. Statement preserved "
                f"as a comment\n{_comment_block(node.sql)}"
            )

    # T-SQL ADD CONSTRAINT ... PRIMARY KEY/UNIQUE with storage clauses:
    # rebuilt directly (sqlglot mangles it into comma-joined actions).
    if node.kind == "ALTER" and node.source_dialect == "tsql":
        rebuilt = _tsql_add_key_constraint(node.sql, dialect)
        if rebuilt is not None:
            return rebuilt

    # PostgreSQL CREATE INDEX -> T-SQL: sqlglot's write-side NULLs-distinct
    # emulation wraps unique-index columns in CASE WHEN expressions
    # (invalid in a T-SQL index column list) and keeps PG's nameless form
    # (T-SQL requires a name). Rebuild from the parsed tree.
    if (
        node.kind == "CREATE INDEX"
        and node.source_dialect == "postgresql"
        and dialect in ("tsql", "mysql")
    ):
        rebuilt = _pg_index_rebuild(node.sql, read, dialect)
        if rebuilt is not None:
            # PG's CONCURRENTLY builds the index without locking the table; no
            # other engine has the option (the index is identical). The rebuild
            # already omits it — surface the loss so it is never silent.
            if re.search(r"(?i)\bCONCURRENTLY\b", node.sql):
                rebuilt = (
                    "-- UNIQUE: CONCURRENTLY (PostgreSQL's non-locking index "
                    f"build) has no {dialect} equivalent; the index is created "
                    "with the target's default locking\n" + rebuilt
                )
            rebuilt = _carry_index_nulls_order(node.sql, rebuilt, dialect)
            return rebuilt

    if (
        node.kind in ("SET", "COMMAND")
        and node.source_dialect == "mysql"
        and dialect != "mysql"
        and (
            re.match(
                r"(?is)^\s*SET\s+(?:@@|(?:GLOBAL|SESSION|LOCAL|PERSIST)\b)",
                node.sql,
            )
            or (re.match(r"(?is)^\s*SET\b", node.sql) and "@@" in node.sql)
        )
    ):
        return (
            f"-- UNIQUE: MySQL session setting has no {dialect} equivalent; "
            f"configure the session natively.\n{_comment_block(node.sql)}"
        )

    # MySQL admin commands (FLUSH/ANALYZE/OPTIMIZE/REPAIR/LOCK TABLES…)
    # are engine-local; sqlglot mangles them (``FLUSH AS STATUS``).
    if (
        node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.match(
            r"(?is)^\s*(?:FLUSH|ANALYZE\s+TABLE|OPTIMIZE\s+TABLE|"
            r"REPAIR\s+TABLE|LOCK\s+TABLES|UNLOCK\s+TABLES|"
            r"CHECK\s+TABLE|CHECKSUM\s+TABLE)\b",
            node.sql,
        )
    ):
        return (
            f"-- UNIQUE: MySQL admin command has no {dialect} equivalent; "
            f"run the target's own maintenance.\n{_comment_block(node.sql)}"
        )

    # A TEMPORARY sequence exists only on PostgreSQL (T-SQL/Oracle
    # sequences are permanent objects; the temp-rename would ship an
    # invalid #name) — zero push.
    if (
        node.kind == "CREATE SEQUENCE"
        and dialect != "postgresql"
        and re.search(r"(?i)\bTEMP(?:ORARY)?\s+SEQUENCE\b", node.sql)
    ):
        return (
            f"-- UNIQUE: {dialect} has no TEMPORARY sequences; statement "
            "preserved as a comment\n" + _comment_block(node.sql)
        )

    # MySQL has no CREATE SEQUENCE; sqlglot would emit invalid SQL.
    if dialect == "mysql" and node.kind == "CREATE SEQUENCE":
        return (
            "-- UNIQUE: MySQL has no sequences; use an AUTO_INCREMENT column "
            "instead. Original:\n"
            + _comment_block(_strip_dbo_schema_qualifier(node.sql))
        )

    # PostgreSQL session GUCs (SET name = v / SET name TO v, optionally
    # LOCAL/SESSION) are engine-local knobs with no meaning elsewhere — the
    # largest class of the pg-source baseline (they error on every other
    # engine). Real SQL SET forms (TRANSACTION, CONSTRAINTS, ROLE, SESSION
    # AUTHORIZATION) keep their path.
    if (
        node.kind in ("SET", "COMMAND")
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.match(r"(?is)^\s*SET\s+SESSION\s+AUTHORIZATION\b", node.sql)
    ):
        return (
            f"-- UNIQUE: SET SESSION AUTHORIZATION has no {dialect} "
            f"equivalent; switch users natively.\n{_comment_block(node.sql)}"
        )

    if (
        node.kind == "SET"
        and node.source_dialect == "postgresql"
        and dialect != "postgresql"
        and re.match(
            r"(?is)^\s*SET\s+(?:LOCAL\s+|SESSION\s+(?!AUTHORIZATION\b))?"
            r"(?!TRANSACTION\b|CONSTRAINTS\b|ROLE\b|TIME\s+ZONE\b)"
            r"[A-Za-z_][\w.]*\s*(?:=|\bTO\b)",
            node.sql,
        )
    ):
        return (
            f"-- UNIQUE: PostgreSQL session setting has no {dialect} "
            f"equivalent; configure the session natively.\n"
            f"{_comment_block(node.sql)}"
        )

    # USE <db> switches the active database. Valid in MySQL and T-SQL only;
    # PostgreSQL (\\c is a psql meta-command) and Oracle have no SQL form.
    if node.kind == "USE" and dialect in ("postgresql", "oracle"):
        return (
            f"-- UNIQUE: {dialect} has no USE statement; "
            f"connect to the target database/schema instead.\n"
            f"{_comment_block(node.sql)}"
        )

    # PG's ALTER COLUMN SET STORAGE knob: engine-internal storage tuning.
    if node.kind == "PG STORAGE":
        if dialect == "postgresql":
            return node.sql
        return (
            f"-- UNIQUE: PostgreSQL column STORAGE tuning has no {dialect} "
            f"equivalent; statement preserved as a comment:\n"
            f"-- {node.sql}"
        )

    if node.kind == "PG SEARCH CTE":
        # PG 14 recursive-CTE SEARCH/CYCLE ordering — no spelling on any
        # other engine (wave 191).
        if dialect == "postgresql":
            return node.sql
        return (
            f"-- UNIQUE: PostgreSQL's recursive-CTE SEARCH/CYCLE clause has "
            f"no {dialect} equivalent; statement preserved as a comment\n"
            f"{_comment_block(node.sql)}"
        )

    # SAVEPOINT: same spelling everywhere but T-SQL (SAVE TRANSACTION).
    # Modeled as a passthrough because sqlglot mis-parses the statement
    # into an Alias (wave 123).
    if node.kind == "SAVEPOINT":
        name = node.sql.split()[-1]
        if dialect == "tsql":
            return f"SAVE TRANSACTION {name}"
        return f"SAVEPOINT {name}"

    # MySQL has no MERGE. The canonical one-UPDATE/one-INSERT pattern is
    # rewritten as INSERT ... SELECT ... ON DUPLICATE KEY UPDATE (which relies
    # on a UNIQUE/PRIMARY KEY covering the ON columns — noted in a carrier).
    # Anything more complex falls back to a documented comment.
    if node.kind == "MERGE" and dialect == "mysql":
        upsert = _merge_to_mysql_upsert(node.sql, read)
        if upsert is not None:
            return upsert
        commented = _comment_block(node.sql)
        return (
            "-- UNIQUE: MySQL has no MERGE; rewrite as "
            "INSERT ... ON DUPLICATE KEY UPDATE. Original:\n" + commented
        )

    # A CTE on UPDATE/DELETE: no engine besides T-SQL can update *through*
    # the CTE, and Oracle rejects the WITH clause on DML entirely — emit a
    # documented carrier instead of invalid (or silently re-targeted) SQL.
    if node.kind == "CTE DML":
        reason = _cte_dml_unsupported(node.sql, read, dialect)
        if reason is not None:
            return f"-- UNIQUE: {reason} Original:\n{_comment_block(node.sql)}"

    # BEGIN TRANSACTION: T-SQL/PG/MySQL have a statement form (rendered by the
    # sqlglot passthrough below); Oracle starts a transaction implicitly, so drop
    # it with a documented note instead of a bare — and invalid — ``BEGIN``.
    if node.kind == "BEGIN TRANSACTION" and dialect == "oracle":
        return (
            "-- UNIQUE: BEGIN TRANSACTION dropped -- Oracle starts a "
            "transaction implicitly"
        )

    # Oracle hierarchical query: keep as-is for Oracle; for others there is
    # no faithful automatic rewrite, so emit a documented comment.
    if node.kind == "CONNECT BY" and dialect != "oracle":
        commented = _comment_block(node.sql)
        return (
            "-- UNIQUE: Oracle CONNECT BY / START WITH hierarchical query has "
            "no automatic equivalent; rewrite as a WITH RECURSIVE CTE. "
            "Original:\n" + commented
        )

    # Session-variable SELECT INTO: native on the source engine, no
    # cross-dialect equivalent (T-SQL's form is SELECT @a = expr).
    if node.kind == "SELECT INTO VAR":
        if dialect == node.source_dialect:
            return node.sql
        return (
            "-- UNIQUE: session-variable SELECT INTO has no cross-dialect "
            "equivalent; rewrite as the target's assignment form. Original:\n"
            + _comment_block(node.sql)
        )

    # RETURNING + ON CONFLICT in one statement: any strip/rewrite of one
    # clause would ship the other raw — carrier before the per-target
    # RETURNING branches below get a chance to.
    if node.kind == "RETURNING" and dialect != "postgresql":
        try:
            _oc_parsed = sqlglot.parse(node.sql, read=read)
        except Exception:  # noqa: BLE001
            _oc_parsed = []
        if any(e is not None and e.find(exp.OnConflict) for e in _oc_parsed):
            return (
                "-- UNIQUE: INSERT combines RETURNING and ON CONFLICT; "
                f"rewrite as MERGE/upsert with result capture on {dialect}. "
                "Original:\n" + _comment_block(node.sql)
            )

    # Oracle's RETURNING…INTO exists only inside PL/SQL with target
    # variables; top-level SQL keeps the DML effect, the clause strips
    # with a documented note (same contract as the MySQL branch below).
    if node.kind == "RETURNING" and dialect == "oracle":
        m = re.search(r"(?i)\bRETURNING\b\s+(.*?)\s*;?\s*$", node.sql)
        cols = m.group(1).strip() if m else ""
        base = re.sub(r"(?i)\s*\bRETURNING\b.*$", "", node.sql).rstrip()
        try:
            rendered = sqlglot.transpile(base, read=read, write=write)
            if rendered and rendered[0].strip():
                base = rendered[0]
        except Exception:  # noqa: BLE001 - keep the source spelling
            pass
        # The stripped base may still carry PG-only shapes (wave 206):
        # Oracle takes WITH only inside the INSERT's subquery, and has
        # no UPDATE … FROM at all.
        base = re.sub(
            r"(?is)^\s*WITH\s+(.*?)\s+INSERT\s+INTO\s+(\S+)\s+SELECT\b",
            r"INSERT INTO \2 WITH \1 SELECT",
            base,
            count=1,
        )
        if re.search(r"(?is)\bUPDATE\b.*\bSET\b.*\sFROM\s", base):
            return (
                "-- UNIQUE: Oracle has no UPDATE … FROM (rewrite with a "
                "correlated subquery or MERGE) and no top-level RETURNING. "
                "Statement preserved as a comment\n" + _comment_block(node.sql)
            )
        return (
            f"{base};\n-- UNIQUE: Oracle has no top-level RETURNING; "
            f"the statement returned: {cols}"
        )

    # MySQL has no RETURNING/OUTPUT; comment it rather than emit invalid SQL.
    if node.kind == "RETURNING" and dialect == "mysql":
        m = re.search(r"(?i)\bRETURNING\b\s+(.*?)\s*;?\s*$", node.sql)
        cols = m.group(1).strip() if m else ""
        base = re.sub(r"(?i)\s*\bRETURNING\b.*$", "", node.sql).rstrip()
        # The stripped base may still carry PG-only DML shapes (wave
        # 203): UPDATE … FROM is MySQL's multi-table UPDATE, DELETE …
        # USING its multi-table DELETE — and MySQL takes WITH only
        # inside the INSERT's SELECT (wave 222).
        base = re.sub(
            r"(?is)^\s*WITH\s+(.*?)\s+INSERT\s+INTO\s+(\S+)\s+SELECT\b",
            r"INSERT INTO \2 WITH \1 SELECT",
            base,
            count=1,
        )
        # An aliased / self-join ``UPDATE t AS v1 SET … FROM t AS v2`` needs
        # the modeled multi-table rewrite (the bare-name regex below only
        # handles the simplest shape); re-parse and re-emit that base.
        remodeled = _remodel_update_from(base, dialect)
        if remodeled is not None:
            base = remodeled
        else:
            base = re.sub(
                r"(?is)\bUPDATE\s+([\w.`\"]+)\s+SET\s+(.*?)\s+FROM\s+([\w.`\",\s]+?)"
                r"(\s+WHERE\b)",
                r"UPDATE \1, \3 SET \2\4",
                base,
                count=1,
            )
        base = re.sub(
            r"(?is)\bDELETE\s+FROM\s+([\w.`\"]+)\s+USING\s+([\w.`\",\s]+?)"
            r"(\s+WHERE\b)",
            r"DELETE \1 FROM \1, \2\3",
            base,
            count=1,
        )
        return (
            f"{base};\n-- UNIQUE: MySQL has no RETURNING/OUTPUT; "
            f"the statement returned: {cols}"
        )

    try:
        # Parse → quote reserved-word identifiers → generate, so a passthrough
        # CREATE INDEX / ALTER on a reserved name (e.g. ``collation``) is valid.
        parsed = [e for e in sqlglot.parse(node.sql, read=read) if e is not None]
        if (
            node.kind == "RETURNING"
            and dialect != "postgresql"
            and any(e.find(exp.OnConflict) for e in parsed)
        ):
            # RETURNING + ON CONFLICT in one statement: the RETURNING
            # passthrough would ship ON CONFLICT raw after OUTPUT.
            return (
                "-- UNIQUE: INSERT combines RETURNING and ON CONFLICT; "
                f"rewrite as MERGE with OUTPUT on {dialect}. Original:\n"
                + _comment_block(node.sql)
            )
        if node.kind == "RETURNING" and dialect == "tsql":
            # T-SQL OUTPUT items must carry the INSERTED./DELETED. prefix;
            # sqlglot renders RETURNING's items bare.
            for e in parsed:
                _prefix_tsql_output_items(cast(exp.Expression, e))
        out = [
            _quote_reserved_identifiers(cast(exp.Expression, e), dialect).sql(
                dialect=write
            )
            for e in parsed
        ]
        if out and out[0].strip():
            result = out[0]
            if node.kind == "CTE DML" and dialect == "tsql":
                # PG's DELETE … USING inside a CTE statement — T-SQL
                # spells the multi-table delete (wave 199).
                result = re.sub(
                    r"(?is)\bDELETE\s+FROM\s+([\w.\[\]\"]+)\s+USING\s+"
                    r"(.+?)(\s+WHERE\b)",
                    r"DELETE \1 FROM \1, \2\3",
                    result,
                    count=1,
                )
            if node.kind == "RETURNING" and dialect == "tsql":
                # sqlglot renders DELETE's OUTPUT before FROM, which not
                # even its own tsql reader accepts; T-SQL wants it after
                # the table.
                result = re.sub(
                    r"(?is)^DELETE\s+(OUTPUT\s.*?)\s+FROM\s+(\S+)",
                    r"DELETE FROM \2 \1",
                    result,
                    count=1,
                )
                # And no AS alias on the UPDATE target (error 156) —
                # T-SQL names the alias and binds it in FROM (wave 197).
                m197 = re.match(
                    r"(?is)^UPDATE\s+([\w.\[\]\"]+)\s+AS\s+(\w+)\s+"
                    r"SET\s+(.*?)\s+FROM\s+(.*)$",
                    result,
                )
                if m197:
                    tbl, alias, sets, rest = m197.groups()
                    result = (
                        f"UPDATE {alias} SET {sets} " f"FROM {tbl} AS {alias}, {rest}"
                    )
            if node.kind == "CREATE INDEX":
                result = _portable_index(result, dialect)
                result = _carry_index_nulls_order(node.sql, result, dialect)
            else:
                result = _portable_types_in_sql(result, dialect)
            if node.kind == "CREATE SEQUENCE" and dialect == "oracle":
                result = _oracle_sequence_drop_type(result)
            if node.kind == "MERGE":
                # sqlglot keeps the USING subquery's FROM DUAL on engines
                # that have no dual relation, and T-SQL *requires* MERGE to
                # end with ';' (error 10713) — the one statement where the
                # no-';' T-SQL convention does not apply.
                if dialect in ("tsql", "postgresql"):
                    result = re.sub(r"(?i)\s+FROM\s+DUAL\b", "", result)
                if dialect == "oracle":
                    # Oracle requires MERGE ... ON (<condition>) — the parens
                    # are mandatory (ORA-00969 without them).
                    result = _oracle_merge_paren_on(result)
                if dialect == "tsql" and not result.rstrip().endswith(";"):
                    result = result.rstrip() + ";"
                if dialect == "tsql":
                    # Scalar-UDF calls inside the sqlglot-emitted MERGE text
                    # never met the shared dbo. decision (error 195 live).
                    def _decide(name: str, prev_word: str | None) -> str | None:
                        if prev_word and prev_word.upper() in TSQL_OBJECT_CONTEXT_WORDS:
                            return None
                        return "dbo." if tsql_call_needs_schema(name) else None

                    result = qualify_function_calls(result, _decide)
            if dialect == "tsql":
                result = _portable_rename_column(result)
                # T-SQL's multi-column drop is ONE DROP COLUMN with a comma
                # list (each engine's normalized form repeats the keyword).
                result = re.sub(r"(?i),\s*DROP\s+COLUMN\s+", ", ", result)
                # sqlglot's tsql writer emits FETCH FIRST/NEXT without the
                # OFFSET clause T-SQL requires (error 102 near 'first').
                result = re.sub(
                    r"(?i)(?<!ROWS )\bFETCH (FIRST|NEXT)\b",
                    r"OFFSET 0 ROWS FETCH \1",
                    result,
                )
            if dialect != "tsql" and node.kind == "ALTER":
                result = _drop_named_default(result)
            if dialect != "oracle":
                result = _portable_alter_add(result, dialect)
            if dialect in ("oracle", "mysql", "postgresql"):
                result = _strip_dbo_schema_qualifier(result)
            # T-SQL has no trailing row-lock clause (FOR UPDATE / FOR SHARE);
            # sqlglot drops it silently. Surface the loss as a documented
            # carrier so the no-silent-loss invariant mirrors it as a warning
            # (Oracle/MySQL keep the clause, so this only bites T-SQL).
            if (
                dialect == "tsql"
                and node.kind == "SELECT"
                and any(e.args.get("locks") for e in parsed)
                and not re.search(r"(?i)\bFOR\s+(?:UPDATE|SHARE)\b", result)
            ):
                result = (
                    "-- UNIQUE: T-SQL has no FOR UPDATE/FOR SHARE row-lock "
                    "clause; lock the rows with a WITH (UPDLOCK, ROWLOCK) "
                    "table hint\n" + result
                )
            return result
    except Exception as e:  # noqa: BLE001 - report and fall back
        logger.warning("passthrough transpile error (%s): %s", node.kind, e)
    return f"-- UNIQUE: Unhandled {node.kind}\n{_comment_block(node.sql)}"


_TSQL_ADD_KEY_RE = re.compile(
    r"(?isx)^\s*ALTER\s+TABLE\s+(?P<table>[\w.\[\]\"]+)\s+"
    r"ADD\s+CONSTRAINT\s+(?P<name>[\w\[\]\"]+)\s+"
    r"(?P<kind>PRIMARY\s+KEY|UNIQUE)\s*(?:CLUSTERED|NONCLUSTERED)?\s*"
    r"\(\s*(?P<cols>[^()]*?)\s*\)"
    r"(?P<tail>.*)$"
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
        f"ALTER TABLE {table_sql} ADD CONSTRAINT {name_sql} "
        f"{kind} ({', '.join(cols)})"
    )


_RENAME_COLUMN_RE = re.compile(
    r"(?is)^\s*ALTER\s+TABLE\s+(?P<table>[\w.\[\]\"`]+)\s+"
    r"RENAME\s+COLUMN\s+(?P<old>[\w\[\]\"`]+)\s+TO\s+(?P<new>[\w\[\]\"`]+)\s*;?\s*$"
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
        f"-- UNIQUE: named DEFAULT constraint {n} dropped "
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
            r"(?is)CASE\s+WHEN\s+.+?\s+IS\s+NULL\s+THEN\s+1\s+ELSE\s+0"
            r"\s+END(?:\s+(?:ASC|DESC))?\s*,\s*",
            "",
            sql,
        )
        # Round-trip: restore physical index clauses this tool stripped on a
        # forward pass, recorded in a ``/* UNIQUE: … -- tsql-only … (physical
        # index clause) */`` note — CLUSTERED is positional (after CREATE
        # [UNIQUE]); WITH (...) / ON <fg> are trailing.
        note = re.search(
            r"(?is)\s*/\*\s*UNIQUE:\s*(?P<clauses>.+?)\s*--\s*tsql-only,"
            r"[^*]*?physical index clause[^*]*?\*/",
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
            r"(?i)CASE\s+WHEN\s+(?P<col>[\w.\[\]\"`]+)\s+IS\s+NULL\s+THEN\s+"
            r"\d+\s+ELSE\s+\d+\s+END\s*,\s*(?P=col)",
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
                + f"\n-- UNIQUE: {dialect} does not support INCLUDE covering "
                f"columns; dropped: {m.group(0)}"
            )
        # Filtered index WHERE: not supported (MySQL/Oracle).
        m = re.search(r"(?i)\sWHERE\s+.+$", sql)
        if m:
            sql = (
                sql[: m.start()].rstrip()
                + f"\n-- UNIQUE: {dialect} does not support filtered indexes; "
                f"dropped predicate:{m.group(0)}"
            )
    if dropped_physical:
        # Preserve the stripped physical clauses in a restorable note so the
        # original can be recovered on a transpilation back to T-SQL.
        clauses = " ".join(dropped_physical)
        sql += (
            f"\n/* UNIQUE: {clauses} -- tsql-only, no {dialect} equivalent "
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
    src = node.source
    if isinstance(src, SubqueryExpression):
        inner = _emit_select(src.query, dialect)
        src_alias = src.alias or (None if dialect == "oracle" else "uq_src")
        src_sql = f"({inner})" + (
            f" {_ident(src_alias, False, dialect)}" if src_alias else ""
        )
    elif isinstance(src, TableRef):
        src_sql = _emit_table_ref(src, dialect)
    else:
        src_sql = emit_node(src, dialect)

    carried = _unpivot_carried_columns(src, node.columns)
    if carried is None:
        return (
            f"{src_sql} /* UNIQUE: UNPIVOT has no {dialect} equivalent and the "
            "source columns are not visible to rewrite it as UNION ALL — see "
            "docs/03-unsupported.md */"
        )
    val = _ident(node.value_col, False, dialect)
    name = _ident(node.name_col, False, dialect)
    # Oracle upper-cases unquoted identifiers, so its UNPIVOT name-column holds
    # the upper-cased column name; every other engine preserves it as written.
    upper = SOURCE_DIALECT.get() == "oracle"
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


def _emit_select(node: SelectStatement, dialect: str, into: str | None = None) -> str:
    """Emit a SELECT statement.

    ``into`` renders T-SQL's ``SELECT … INTO <table> FROM …`` (the
    faithful CTAS form there); placed right before the FROM clause.
    """
    node = _qualify_using_join_columns(node, dialect)
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
        _inner = dataclasses.replace(node, having=None)
        _hcond = _emit_condition(node.having, dialect)
        return f"SELECT * FROM ({_emit_select(_inner, dialect)}) uq_h\nWHERE {_hcond}"
    parts: list[str] = []

    # CTEs
    if node.ctes:
        cte_parts = []
        for cte in node.ctes:
            # PG and MySQL REQUIRE the RECURSIVE keyword; T-SQL and
            # Oracle have no such keyword (recursion is implicit).
            recursive = (
                "RECURSIVE "
                if cte.recursive and dialect in ("postgresql", "mysql")
                else ""
            )
            cols = f"({', '.join(cte.columns)})" if cte.columns else ""
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
    ):
        _dstr = _from_string_columns(node)
    if node.empty_select_list and not node.columns and dialect == "postgresql":
        # PG's zero-column select list (``SELECT;``) — a ``*`` here is
        # invalid without FROM and changes the shape with one (wave 124).
        parts.append(f"SELECT {distinct}".rstrip())
    else:
        _col_parts = []
        for c in node.columns:
            _cstr = _emit_value_expression(c, dialect)
            if (
                _dstr
                and isinstance(c, ColumnRef)
                and c.table is None
                and c.name.lower() in _dstr
            ):
                _cstr = f"{_cstr} COLLATE {_dcoll}"
            _col_parts.append(_cstr)
        cols = ", ".join(_col_parts) or "*"
        parts.append(f"SELECT {distinct}{top}{cols}")

    if into:
        parts.append(f"INTO {into}")

    # FROM
    if node.from_clause:
        if isinstance(node.from_clause, UnpivotRelation):
            parts.append(f"FROM {_emit_unpivot_relation(node.from_clause, dialect)}")
        elif isinstance(node.from_clause, SubqueryExpression):
            # A derived table needs its alias, or references to it (and, on
            # MySQL, the derived table itself) are invalid. Oracle is the
            # only engine where the alias is optional — synthesize one for
            # everyone else when the source (Oracle) omitted it.
            alias = node.from_clause.alias
            if not alias and dialect != "oracle":
                alias = "uq_dt"
            sub_alias = f" {_ident(alias, False, dialect)}" if alias else ""
            inner_sql = _emit_select(node.from_clause.query, dialect)
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
        if node.group_modifier == "GROUPING SETS" and dialect != "mysql":
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
            item_sql = _emit_order_item(o, dialect, collate=_oc, lower=_lower)
            rendered.append(f"{key}, {item_sql}" if key else item_sql)
        parts.append(f"ORDER BY {', '.join(rendered)}")
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
            f"-- UNIQUE: MySQL has no GROUP BY {node.group_modifier}; the base "
            "grouping is kept and the super-aggregate (subtotal) rows are "
            "omitted\n" + result
        )

    # Set operation
    if node.set_op and node.set_query:
        # INTERSECT ALL / EXCEPT ALL keep duplicates. MySQL (8.0.31+) and PG
        # support them; Oracle < 21c has only MINUS/INTERSECT (distinct) and
        # T-SQL has no ALL form, so those fall back to the distinct spelling
        # (the ALL cannot be honoured there — a documented version limit).
        _all_ok = dialect in ("mysql", "postgresql")
        op_map = {
            SetOperationType.UNION: "UNION",
            SetOperationType.UNION_ALL: "UNION ALL",
            SetOperationType.INTERSECT: "INTERSECT",
            SetOperationType.INTERSECT_ALL: (
                "INTERSECT ALL" if _all_ok else "INTERSECT"
            ),
            SetOperationType.EXCEPT: "EXCEPT" if dialect != "oracle" else "MINUS",
            SetOperationType.EXCEPT_ALL: (
                "EXCEPT ALL"
                if _all_ok
                else ("MINUS" if dialect == "oracle" else "EXCEPT")
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
            "-- UNIQUE: MySQL SQL_CALC_FOUND_ROWS has no equivalent here; the "
            "full row count for a following FOUND_ROWS() is not computed — run "
            "a separate COUNT(*) query\n" + result
        )

    return result


def _emit_insert(node: InsertStatement, dialect: str) -> str:
    """Emit an INSERT statement."""
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
        return f"INSERT INTO {table}{cols}\nVALUES {values}"

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
        return f"{with_prefix}INSERT INTO {table}{cols}\n{select}"

    if dialect == "mysql":
        # MySQL has no DEFAULT VALUES clause; the all-defaults row is
        # spelled with empty lists.
        return f"INSERT INTO {table} () VALUES ()"
    if dialect == "oracle" and (all_empty or not node.columns):
        # Oracle has no DEFAULT VALUES and the all-defaults row cannot
        # be spelled without the column list.
        return (
            "-- UNIQUE: all-defaults INSERT has no Oracle spelling "
            "without the column list; original preserved:\n"
            f"-- INSERT INTO {table} VALUES ()"
        )
    return f"INSERT INTO {table}{cols}\nDEFAULT VALUES"


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
            "-- UNIQUE: Oracle has no UPDATE ... FROM and this join shape "
            "(no ON condition) cannot become a correlated subquery; rewrite "
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
    if dialect == "tsql" and node.table.alias:
        # T-SQL spells an aliased delete ``DELETE alias FROM t alias``
        # (``DELETE FROM t alias`` is a syntax error — wave 140).
        result = f"DELETE {node.table.alias} FROM {table}"
    else:
        result = f"DELETE FROM {table}"

    if node.where:
        result += f"\nWHERE {_emit_condition(node.where, dialect)}"

    return result


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
        f"-- UNIQUE: MySQL SET type on {col_name} has no {dialect} "
        f"equivalent; stored as {varchar}({total_len}). "
        f"Allowed members: {quoted_values}"
    )
    return f"{varchar}({total_len})", "", note


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
                "-- UNIQUE: LIKE clone copies column structure only here; "
                "the source's indexes/keys are not cloned"
            )
        if dialect == "oracle":
            return (
                f"CREATE {temp}TABLE {exists}{table} AS\n"
                f"SELECT *\nFROM {node.like_source}\nWHERE 1 = 0\n"
                "-- UNIQUE: LIKE clone copies column structure only here; "
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
        col_defs = []
        set_type_notes: list[str] = []
        column_comments: list[tuple[str, str]] = []
        on_update_notes: list[str] = []
        collate_notes: list[str] = []
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
                if _tn == "JSON":
                    if dialect == "oracle":
                        dtype = "CLOB"
                    elif dialect == "tsql":
                        dtype = "NVARCHAR(MAX)"
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
                            f" /* UNIQUE: source IDENTITY (START {seed} INCREMENT "
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
                    persisted = " PERSISTED" if col.generated_stored else ""
                    generated = f" AS ({expr}){persisted}"
                elif dialect == "postgresql":
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
                    f"-- UNIQUE: MySQL's {col.on_update} on column {col_name} has "
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
                    f"-- UNIQUE: column {col_name} collation/charset "
                    f"({col.collate}) has no portable {dialect} equivalent; the "
                    "column uses the default collation (comparisons/ordering may "
                    "differ) — set it explicitly on the target or supply the "
                    "source DB connection"
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
                    f"{nullable}{pk}{unique}{check}{unsigned_check}"
                )
            else:
                nullable = "" if col.nullable else " NOT NULL"
                col_defs.append(
                    f"  {col_name} {dtype}{collate_inline}{identity}{nullable}"
                    f"{default}{pk}{unique}{check}{unsigned_check}"
                    f"{on_update_inline}{comment_inline}"
                )
        # Table-level constraints (PK/FK/UNIQUE/CHECK), re-transpiled.
        # A fragment may come back as a documented comment (e.g. a generated
        # column with no portable type); those can't live inside the
        # parenthesized column list, so collect them and append afterwards.
        trailing_comments: list[str] = list(set_type_notes)
        trailing_comments.extend(on_update_notes)
        trailing_comments.extend(collate_notes)
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
                    "-- UNIQUE: PostgreSQL UNIQUE … NULLS NOT DISTINCT (NULLs "
                    f"compare equal) has no {dialect} equivalent; a plain UNIQUE "
                    "treats NULLs as distinct (docs/03-unsupported.md)"
                )
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
                    f"-- UNIQUE: T-SQL In-Memory OLTP storage option(s) [{opts}] "
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
                    f"-- UNIQUE: MySQL table default collation/charset "
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


def _emit_passthrough_inline(node: PassthroughSQL, dialect: str) -> str:
    """Re-transpile a constraint fragment for inclusion inside CREATE TABLE.

    Wraps the fragment in a throwaway table so sqlglot will transpile the
    constraint, then extracts it back out. Falls back to the raw fragment.
    """
    read = sqlglot_dialect_name(node.source_dialect)
    write = sqlglot_dialect_name(dialect)
    fragment_sql = node.sql
    # Oracle ``… USING INDEX [<storage>]`` on a PK/UNIQUE names/tunes the backing
    # index — an Oracle storage detail. Every engine backs a PK/UNIQUE with an
    # index by default, so strip the clause (the constraint is identical).
    if node.source_dialect == "oracle" and dialect != "oracle":
        fragment_sql = re.sub(r"(?is)\s+USING\s+INDEX\b.*$", "", fragment_sql)
    # PostgreSQL EXCLUDE has no equivalent on any other engine; keep it on PG,
    # degrade it to a documented carrier elsewhere (never silently drop it).
    if node.kind == "EXCLUDE" and dialect != "postgresql":
        return (
            f"-- UNIQUE: PostgreSQL EXCLUDE constraint has no {dialect} "
            f"equivalent; enforce the exclusion with a trigger. Original: "
            f"{node.sql}"
        )
    if (
        node.source_dialect == "mysql"
        and dialect != "mysql"
        and re.match(r"(?i)\s*(PRIMARY\s+KEY|UNIQUE|KEY|INDEX)\b", fragment_sql)
    ):
        # MySQL prefix indexes (``KEY (a, b(132))``): only MySQL indexes
        # a column prefix — the length has no spelling elsewhere, and
        # indexing the whole column accepts every row the prefix key
        # accepted (wave 166).
        fragment_sql = re.sub(r"(?i)\b(\w+)\s*\(\s*\d+\s*\)", r"\1", fragment_sql)
    if node.source_dialect == "tsql" and dialect != "tsql":
        # T-SQL physical hints in a table constraint (the CLUSTERED keyword,
        # WITH (...) storage options, ON [filegroup]) have no meaning on the
        # other engines, and sqlglot's non-T-SQL writers render them as bogus
        # comma-separated column-list items ("PRIMARY KEY, CLUSTERED (...),
        # WITH (...), ON ..."). Strip them before re-transpiling.
        fragment_sql = re.sub(r"(?i)\b(NON)?CLUSTERED\s+", "", fragment_sql)
        fragment_sql = re.sub(r"(?i)\s*WITH\s*\([^)]*\)", "", fragment_sql)
        fragment_sql = re.sub(r"(?i)\s+ON\s+(?:\[[^\]]+\]|\w+)\s*$", "", fragment_sql)
        # ASC/DESC are index hints inside a PK/UNIQUE column list; sqlglot's
        # T-SQL reader itself rejects them once the CLUSTERED keyword is gone.
        if re.match(r"(?i)\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE)\b", fragment_sql):
            fragment_sql = re.sub(r"(?i)\s+(?:ASC|DESC)\b", "", fragment_sql)
    if dialect == "oracle":
        # Oracle has NO ``ON UPDATE`` referential action at all (only ON DELETE
        # CASCADE/SET NULL); keeping it ships invalid DDL. Strip it — a
        # documented engine limitation (docs/03-unsupported.md).
        fragment_sql = re.sub(
            r"(?i)\s+ON\s+UPDATE\s+(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|"
            r"RESTRICT|NO\s+ACTION)",
            "",
            fragment_sql,
        )
        # Nor a FK ``MATCH FULL|PARTIAL|SIMPLE`` clause (PG only, ORA-03075);
        # Oracle FKs are always simple-match. Strip it (documented limitation).
        fragment_sql = re.sub(
            r"(?i)\s+MATCH\s+(?:FULL|PARTIAL|SIMPLE)", "", fragment_sql
        )
    try:
        wrapped = f"CREATE TABLE __c__ (x INT, {fragment_sql})"
        out = sqlglot.transpile(wrapped, read=read, write=write)[0]
        inner = out[out.index("(") + 1 : out.rindex(")")]
        # Drop the placeholder "x INT," prefix.
        parts = inner.split(",", 1)
        if len(parts) == 2:
            fragment = parts[1].strip()
            # PostgreSQL and Oracle require an explicit type before a generated
            # column. T-SQL computed columns carry no declared type, so sqlglot
            # emits a typeless definition -- either "col GENERATED ALWAYS AS
            # (...) STORED" or "col AS (...) PERSISTED" -- that those engines
            # reject. Emit a documented comment instead of invalid SQL.
            # MySQL column visibility is engine-local; INVISIBLE has no
            # spelling elsewhere.
            if dialect != "mysql":
                fragment = re.sub(r"(?i)\s+\bINVISIBLE\b", "", fragment)
            is_generated = re.search(
                r"(?i)\bGENERATED\s+ALWAYS\s+AS\b|\bAS\s*\(", fragment
            )
            has_type = re.search(
                r"(?i)^\s*[\w\[\]\".]+\s+"
                r"(INT|INTEGER|BIGINT|SMALLINT|TINYINT|NUMERIC|DECIMAL|FLOAT|"
                r"REAL|DOUBLE|CHAR|VARCHAR|NVARCHAR|TEXT|DATE|TIMESTAMP|"
                r"BOOLEAN|NUMBER|RAW)",
                fragment,
            )
            if (
                dialect in ("postgresql", "oracle", "mysql")
                and is_generated
                and not has_type
            ):
                col_name = fragment.split()[0]
                return (
                    f"-- UNIQUE: {dialect} requires an explicit type for the "
                    f"generated column {col_name}; original computed column: "
                    f"{node.sql}"
                )
            # Oracle and PostgreSQL do not allow NULLS FIRST / NULLS LAST or
            # ASC / DESC inside PRIMARY KEY or UNIQUE constraint column lists
            # (only in ORDER BY / index specs). sqlglot adds the NULLS
            # ordering when emulating T-SQL ordering; ASC/DESC come straight
            # from the SSMS-generated source and are index hints, not
            # semantics, so dropping them is safe.
            if dialect in ("oracle", "postgresql"):
                fragment = re.sub(r"(?i)\s+NULLS\s+(?:FIRST|LAST)", "", fragment)
            if dialect != "tsql" and re.match(
                r"(?i)\s*(CONSTRAINT|PRIMARY\s+KEY|UNIQUE)\b", fragment
            ):
                fragment = re.sub(r"(?i)\s+(?:ASC|DESC)\b", "", fragment)
            # MySQL's named inline key "UNIQUE name (cols)" is only valid
            # MySQL; the portable spelling is CONSTRAINT name UNIQUE (cols).
            if dialect != "mysql":
                fragment = re.sub(
                    r"(?i)^UNIQUE\s+(?:KEY\s+|INDEX\s+)?([`\"\[\]\w]+)\s*\(",
                    r"CONSTRAINT \1 UNIQUE (",
                    fragment,
                )
            # A FOREIGN KEY may REFERENCE a dbo-qualified table. The "dbo" schema
            # is meaningless on the other engines (and would name a non-existent
            # schema/database), exactly as for the table being created, so strip
            # it from the reference target too.
            if dialect in ("oracle", "mysql", "postgresql"):
                fragment = _strip_dbo_from_references(fragment)
            return fragment
    except Exception as e:  # noqa: BLE001
        logger.warning("constraint transpile error: %s", e)
    return node.sql


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
    return f"CREATE {replace}VIEW {name} AS\n{query}"


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
            "-- UNIQUE: MySQL has no sequences (use an AUTO_INCREMENT "
            "column); original preserved:\n"
            f"-- DROP SEQUENCE {exists}{name}"
        )
    if node.object_type == "TYPE" and dialect == "mysql":
        # MySQL has no user-defined types in any form.
        return (
            "-- UNIQUE: MySQL has no user-defined types; original "
            f"preserved:\n-- DROP TYPE {exists}{name}"
        )
    if node.object_type == "INDEX":
        if dialect in ("tsql", "mysql"):
            if not node.on_table:
                return (
                    f"-- UNIQUE: {dialect} DROP INDEX requires the owning "
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
                    "-- UNIQUE: PostgreSQL DROP TRIGGER requires the "
                    "owning table (ON tbl), which the source statement "
                    "does not carry; original preserved:\n"
                    f"-- DROP TRIGGER {exists}{name}"
                )
            return f"DROP TRIGGER {exists}{name} ON {node.on_table}{cascade}"
        return f"DROP TRIGGER {exists}{name}{cascade}"
    return f"DROP {node.object_type} {exists}{name}{cascade}"


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
        return f"0 /* UNIQUE: @@ROWCOUNT has no top-level {dialect} equivalent */"
    if upper == "@@FETCH_STATUS" and dialect != "tsql":
        # Cursor-contextual by nature; the procedural path maps it with
        # surrounding state. Context-free there is only the neutral.
        return (
            f"0 /* UNIQUE: @@FETCH_STATUS has no top-level {dialect} "
            "equivalent; it is cursor state */"
        )
    if upper == "@@ERROR" and dialect != "tsql":
        return (
            f"0 /* UNIQUE: @@ERROR has no top-level {dialect} equivalent; "
            "use an exception handler */"
        )
    if upper == "@@VERSION" and dialect != "tsql":
        # PG/MySQL have a version function; the string it returns is engine
        # specific, so the value cannot match T-SQL's. Oracle's is in v$version
        # (needs a query + privileges) — a documented NULL is the honest neutral.
        fn = {"postgresql": "version()", "mysql": "VERSION()"}.get(dialect)
        if fn:
            return (
                f"{fn} /* UNIQUE: @@VERSION -> {fn}; "
                "version string differs per engine */"
            )
        return "NULL /* UNIQUE: @@VERSION has no Oracle equivalent outside v$version */"
    if upper == "@@SPID" and dialect != "tsql":
        # Session/connection id — every engine spells it differently and the
        # value is per-connection, so it can never equal T-SQL's @@SPID.
        fn = {
            "postgresql": "pg_backend_pid()",
            "mysql": "CONNECTION_ID()",
            "oracle": "SYS_CONTEXT('USERENV', 'SID')",
        }[dialect]
        return f"{fn} /* UNIQUE: @@SPID -> {fn}; session id differs per engine */"
    if re.fullmatch(r"(?i)SQL\s*%\s*ROWCOUNT", stripped) and dialect != "oracle":
        if dialect == "tsql":
            return "@@ROWCOUNT"
        if dialect == "mysql":
            return "ROW_COUNT()"
        return f"0 /* UNIQUE: SQL%ROWCOUNT has no top-level {dialect} equivalent */"
    return None


def _emit_expression(node: ASTNode, dialect: str) -> str:
    """Emit an expression node as SQL text."""
    if isinstance(node, UnsupportedInline):
        # Valid on its own engine; a NULL placeholder + carrier + warning
        # elsewhere (the loss is documented, never silently mangled).
        if SOURCE_DIALECT.get() == dialect:
            return node.source_sql
        return (
            f"NULL /* UNIQUE: {node.detail} ({node.source_sql}) — "
            "see docs/03-unsupported.md */"
        )
    if isinstance(node, ColumnRef):
        # plpgsql's bare FOUND flag (statement state, not a column).
        if (
            not node.table
            and node.name.upper() == "FOUND"
            and SOURCE_DIALECT.get() == "postgresql"
        ):
            return DML_FOUND_EXPR.get(dialect, node.name)
        # Bare SQLERRM (PL/SQL and plpgsql spell it without parens) is the
        # current-error-message global, not a column (exception context).
        if (
            not node.table
            and SOURCE_DIALECT.get()
            in ERROR_MESSAGE_SOURCES.get(node.name.upper(), frozenset())
            and dialect in ERROR_MESSAGE_EXPR
        ):
            return ERROR_MESSAGE_EXPR[dialect]
        # SQLSTATE/SQLCODE diagnostic globals (same exception context).
        if (
            not node.table
            and SOURCE_DIALECT.get()
            in ERROR_DIAGNOSTIC_SOURCES.get(node.name.upper(), frozenset())
            and dialect in ERROR_DIAGNOSTIC_EXPRS[node.name.upper()]
        ):
            return ERROR_DIAGNOSTIC_EXPRS[node.name.upper()][dialect]
        name = _ident(node.name, node.quoted, dialect)
        if node.table:
            qual = node.table
            # A temp-table QUALIFIER must rename too (``JOIN #t1 ON
            # t1.c0 = 5`` left t1 dangling on T-SQL — wave 231).
            if dialect == "tsql" and not qual.startswith("#"):
                temp_tables = TEMP_TABLES.get()
                defined = DEFINED_ALIASES.get() or frozenset()
                if (
                    temp_tables
                    and qual.lower() in temp_tables
                    and qual.lower() not in defined
                ):
                    qual = f"#{qual}"
            table = _ident(qual, node.table_quoted, dialect)
            return f"{table}.{name}"
        return name

    if isinstance(node, Star):
        if node.table:
            return f"{node.table}.*"
        return "*"

    if isinstance(node, Literal):
        if node.value is None:
            return "NULL"
        if node.dtype == "boolean":
            # T-SQL and Oracle (pre-23c) have no boolean literals in SQL
            # contexts (audit 2026-07-02, S1-9).
            if dialect in ("tsql", "oracle"):
                return "1" if node.value else "0"
            return "TRUE" if node.value else "FALSE"
        if node.dtype == "national":
            quoted_n = str(node.value).replace("'", "''")
            if dialect in ("tsql", "oracle"):
                return f"N'{quoted_n}'"
            return f"'{quoted_n}'"
        if node.dtype == "hex":
            # Binary/hex literal: MySQL x'8f', T-SQL 0x8f, PG bytea,
            # Oracle HEXTORAW (wave 174 — it shipped as a DECIMAL
            # rendering that overflowed past BIGINT digits).
            digits = str(node.value)
            if dialect == "tsql":
                return f"0x{digits}"
            if dialect == "postgresql":
                return f"'\\x{digits}'::bytea"
            if dialect == "oracle":
                return f"HEXTORAW('{digits}')"
            return f"x'{digits}'"
        if node.dtype == "string" or (
            node.dtype == "unknown" and isinstance(node.value, str)
        ):
            escaped = str(node.value).replace("'", "''")
            return f"'{escaped}'"
        return str(node.value)

    if isinstance(node, Alias):
        inner = _emit_expression(node.expression, dialect)
        return f"{inner} AS {_ident(node.name, node.quoted, dialect)}"

    if isinstance(node, FunctionCall):
        return _emit_function(node, dialect)

    if isinstance(node, ArrayLiteral):
        # ARRAY(SELECT …) keeps the subquery-constructor parens; value
        # elements keep the bracket spelling (targets without arrays are
        # gated whole before emission ever sees this node).
        if len(node.elements) == 1 and isinstance(node.elements[0], SelectStatement):
            return f"ARRAY({_emit_select(node.elements[0], dialect)})"
        parts = ", ".join(_emit_expression(e, dialect) for e in node.elements)
        return f"ARRAY[{parts}]"

    if isinstance(node, BinaryOp):
        return _emit_binary(node, dialect)

    if isinstance(node, UnaryOp):
        return _emit_unary(node, dialect)

    if isinstance(node, CaseExpression):
        return _emit_case(node, dialect)

    if isinstance(node, CastExpression):
        # Oracle can't CAST an ISO string to DATE/TIMESTAMP (it applies
        # NLS_DATE_FORMAT, ORA-01861). It does accept the ANSI literal
        # ``DATE '…'`` / ``TIMESTAMP '…'`` directly, so emit that instead.
        if (
            dialect == "oracle"
            and node.target_type.name.upper()
            in (
                "DATE",
                "TIMESTAMP",
                "DATETIME",
                "DATETIME2",
                "SMALLDATETIME",
                "TIMESTAMPTZ",
            )
            and isinstance(node.expression, Literal)
            and isinstance(node.expression.value, str)
        ):
            lit = _oracle_date_literal(node.expression.value.strip())
            if lit is not None:
                return lit
        # Oracle can't CAST a HEXTORAW to a number (ORA-00932). TO_NUMBER with an
        # 'X' hex mask parses the hex digits directly (x'FF'::int -> 255).
        if (
            dialect == "oracle"
            and isinstance(node.expression, Literal)
            and node.expression.dtype == "hex"
            and node.target_type.name.split("(")[0].strip().upper()
            in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "NUMBER", "NUMERIC")
        ):
            _hx = str(node.expression.value)
            return f"TO_NUMBER('{_hx}', '{'X' * len(_hx)}')"
        # MySQL casts a string to a number leniently — it parses the leading
        # numeric prefix and yields 0 for a non-numeric string (CAST('abc' AS
        # DECIMAL) = 0), where Oracle/PG/T-SQL raise a conversion error. Replace
        # the literal with its MySQL-parsed value so the target computes the same
        # result (a plain numeric literal — no CASE guard for PG to constant-fold).
        if (
            SOURCE_DIALECT.get() == "mysql"
            and dialect != "mysql"
            and isinstance(node.expression, Literal)
            and isinstance(node.expression.value, str)
            and node.target_type.name.split("(")[0].strip().upper()
            in _NUMERIC_CAST_TYPES
        ):
            _m = re.match(
                r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", node.expression.value
            )
            _lax = _m.group(1) if _m else "0"
            _num: ASTNode = (
                Literal(value=float(_lax), dtype="number")
                if any(c in _lax for c in ".eE")
                else Literal(value=int(_lax), dtype="integer")
            )
            return _emit_expression(dataclasses.replace(node, expression=_num), dialect)
        if (
            dialect == "tsql"
            and isinstance(node.expression, UnaryOp)
            and node.expression.operator == UnaryOperator.NOT
        ):
            # NOT is not a value expression on T-SQL — wrap tri-state.
            operand = _emit_expression(node.expression.operand, dialect)
            inner = f"CASE WHEN {operand} = 0 THEN 1 " f"WHEN {operand} <> 0 THEN 0 END"
        else:
            inner = _emit_expression(node.expression, dialect)
        # MySQL CAST of a boolean (a comparison) to a character type yields
        # '1'/'0' (MySQL booleans are integers); PostgreSQL renders the boolean
        # as 't'/'f'. Convert the boolean to an integer first so the value
        # matches.
        if (
            dialect == "postgresql"
            and SOURCE_DIALECT.get() == "mysql"
            and _is_predicate_node(node.expression)
            and node.target_type.name.split("(")[0].strip().upper()
            in ("CHAR", "VARCHAR", "TEXT", "NCHAR", "NVARCHAR")
        ):
            inner = f"CASE WHEN {inner} THEN 1 ELSE 0 END"
        # The reverse: PostgreSQL renders a boolean cast to text as 'true'/'false',
        # but MySQL has no boolean text and would give '1'/'0'. Emit the words so
        # the value matches (a boolean is a comparison predicate or a true/false
        # literal).
        if (
            dialect == "mysql"
            and SOURCE_DIALECT.get() == "postgresql"
            and (
                _is_predicate_node(node.expression)
                or (
                    isinstance(node.expression, Literal)
                    and node.expression.dtype == "boolean"
                )
            )
            and node.target_type.name.split("(")[0].strip().upper()
            in ("CHAR", "VARCHAR", "TEXT", "NCHAR", "NVARCHAR")
        ):
            return f"CASE WHEN {inner} THEN 'true' ELSE 'false' END"
        # Oracle CAST-to-integer ROUNDS the value (CAST('3.9' AS INT) = 4), but
        # MySQL's CAST(... AS SIGNED) truncates a string ('3.9' -> 3). Round
        # first so the value matches (a no-op for an already-integer value).
        if (
            dialect == "mysql"
            and SOURCE_DIALECT.get() == "oracle"
            and node.target_type.name.split("(")[0].strip().upper()
            in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT")
        ):
            inner = f"ROUND({inner})"
        # The reverse target: Oracle/PG/MySQL CAST-to-integer ROUNDS a numeric
        # literal half-away-from-zero (CAST(2.7 AS INT) = 3, 7.5 -> 8), but T-SQL
        # CAST truncates (2, 7). Round first so the value matches — T-SQL ROUND is
        # half-away-from-zero too. Gated to a fractional numeric literal: PG rounds
        # a float *column* half-to-even, which would not match, so leave those.
        # A fractional numeric literal, or its negation (``-3.99`` parses to a
        # UnaryOp over a Literal, so a plain isinstance(Literal) check missed it).
        _ci_lit_node = node.expression
        if (
            isinstance(_ci_lit_node, UnaryOp)
            and _ci_lit_node.operator == UnaryOperator.NEGATIVE
        ):
            _ci_lit_node = _ci_lit_node.operand
        _ci_frac_lit = (
            isinstance(_ci_lit_node, Literal)
            and isinstance(_ci_lit_node.value, (int, float))
            and not isinstance(_ci_lit_node.value, bool)
            and float(_ci_lit_node.value) != int(_ci_lit_node.value)
        )
        if (
            dialect == "tsql"
            and SOURCE_DIALECT.get() in ("oracle", "postgresql", "mysql")
            and _ci_frac_lit
            and node.target_type.name.split("(")[0].strip().upper()
            in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT")
        ):
            inner = f"ROUND({inner}, 0)"
        # MySQL CAST only accepts a fixed set of target types (SIGNED, not INT;
        # no BOOLEAN); T-SQL has no BOOLEAN (it is BIT).
        dtype = node.target_type.name
        if dialect != "mysql":
            # ``CHAR CHARACTER SET cs`` is MySQL-only; the charset has
            # no inline-cast spelling elsewhere (wave 163).
            dtype = re.sub(r"(?i)\s+CHARACTER\s+SET\s+\S+$", "", dtype)
        mapped = _CAST_TYPE_MAP.get(dialect, {}).get(dtype.upper())
        if mapped:
            dtype = mapped
            # A mapped character type keeps its length (Oracle rejects a
            # lengthless character CAST, ORA-00906); the others (SIGNED,
            # TIMESTAMP, BIT) take none.
            if node.target_type.params and mapped in ("VARCHAR2", "NVARCHAR2", "CHAR"):
                dtype += f"({', '.join(str(p) for p in node.target_type.params)})"
        elif node.target_type.params:
            dtype += f"({', '.join(str(p) for p in node.target_type.params)})"
        # PostgreSQL's unbounded ``numeric``/``decimal`` (no precision/scale) is
        # arbitrary-precision, but a bare DECIMAL defaults to scale 0 on
        # MySQL/Oracle/T-SQL — it silently truncates the fraction (2.675::numeric
        # would become 3 before a later ROUND). Give a PG-source cast a generous
        # scale so the fraction survives; a MySQL-source bare DECIMAL is really
        # DECIMAL(10,0) (scale 0), so keep that to match MySQL's own rounding.
        if (
            not node.target_type.params
            and dialect in ("mysql", "oracle", "tsql")
            and re.fullmatch(r"(?i)(DECIMAL|NUMERIC|NUMBER|DEC)", dtype.strip())
        ):
            dtype += "(10, 0)" if SOURCE_DIALECT.get() == "mysql" else "(38, 10)"
        if dialect == "tsql":
            # A size beyond T-SQL's 8000-byte page types only exists as
            # MAX (MySQL BINARY takes sizes up to 2^32-1 — wave 187).
            m = re.fullmatch(
                r"(?is)(N?VARCHAR|VARBINARY|BINARY|CHAR)\s*\(\s*(\d+)\s*\)", dtype
            )
            if m:
                base, size = m.group(1).upper(), int(m.group(2))
                limit = 4000 if base == "NVARCHAR" else 8000
                if size > limit:
                    dtype = (
                        "VARBINARY(MAX)"
                        if base in ("BINARY", "VARBINARY")
                        else f"{'N' if base == 'NVARCHAR' else ''}VARCHAR(MAX)"
                    )
        # Oracle has no TIME type (CAST(... AS TIME) shipped an invalid ORA-00902
        # datatype), and no *bare* INTERVAL type — it requires a qualifier
        # (INTERVAL DAY TO SECOND / YEAR TO MONTH) and can't cast a free-form
        # '1 day' string. No exact equivalent exists — keep the value as text with
        # a documented carrier.
        _cast_to = node.target_type.name.split("(")[0].strip().upper()
        if dialect == "oracle" and _cast_to in ("TIME", "INTERVAL"):
            _what = "TIME" if _cast_to == "TIME" else "bare INTERVAL"
            return (
                f"{inner} /* UNIQUE: Oracle has no {_what} type — value kept as "
                "text (docs/03-unsupported.md) */"
            )
        # MySQL's JSON type has no faithful cross-engine cast: T-SQL has no JSON
        # type at all (error 243), and MySQL's canonical JSON spacing ('[1, 2]')
        # differs from PG/Oracle, so the value can't be guaranteed equal. Keep the
        # source value as text with a documented carrier.
        if (
            dialect != "mysql"
            and SOURCE_DIALECT.get() == "mysql"
            and _cast_to == "JSON"
        ):
            return (
                f"{inner} /* UNIQUE: MySQL JSON type has no faithful cross-engine "
                "equivalent (T-SQL has no JSON type; canonical JSON spacing differs "
                "on PG/Oracle) — value kept as text — see docs/03-unsupported.md */"
            )
        # PostgreSQL geometric types (point/line/box/…) have no cross-engine
        # equivalent; keep the source's text value with a documented carrier.
        if (
            dialect != "postgresql"
            and SOURCE_DIALECT.get() == "postgresql"
            and _cast_to in _PG_GEOMETRIC_TYPES
        ):
            return (
                f"{inner} /* UNIQUE: PostgreSQL geometric type "
                f"{_cast_to.lower()} has no cross-engine equivalent — value kept "
                "as text (docs/03-unsupported.md) */"
            )
        # PostgreSQL numeric represents NaN / ±Infinity; MySQL/T-SQL/Oracle
        # DECIMAL do not (CAST('NaN' AS DECIMAL) collapses to 0), so a comparison
        # silently diverges. Emit the cast with a documented carrier.
        _nan = node.expression
        if (
            dialect in ("mysql", "tsql", "oracle")
            and SOURCE_DIALECT.get() == "postgresql"
            and isinstance(_nan, Literal)
            and isinstance(_nan.value, str)
            and _nan.value.strip().lstrip("+-").upper() in ("NAN", "INFINITY", "INF")
            and re.match(
                r"(?i)(DECIMAL|NUMERIC|NUMBER|DEC|FLOAT|DOUBLE|REAL|INT)", dtype.strip()
            )
        ):
            return (
                f"CAST({inner} AS {dtype}) /* UNIQUE: PostgreSQL NaN/Infinity has "
                f"no {dialect} numeric equivalent (docs/03-unsupported.md) */"
            )
        # MySQL's UNSIGNED integer cast (sqlglot: UBIGINT/UINT/…) has no signed-
        # engine equivalent — map to a wide numeric that holds the value and flag
        # that the unsigned wraparound semantics aren't preserved.
        if dialect in ("oracle", "postgresql", "tsql") and node.target_type.name.split(
            "("
        )[0].strip().upper() in (
            "UBIGINT",
            "UINT",
            "UINTEGER",
            "USMALLINT",
            "UTINYINT",
            "UMEDIUMINT",
        ):
            _signed = "NUMBER" if dialect == "oracle" else "NUMERIC"
            return (
                f"CAST({inner} AS {_signed}) /* UNIQUE: MySQL UNSIGNED has no "
                f"{dialect} equivalent; unsigned wraparound not preserved "
                "(docs/03-unsupported.md) */"
            )
        # A TRY_CAST/TRY_CONVERT yields NULL on a conversion error. T-SQL has
        # TRY_CAST natively; Oracle has DEFAULT NULL ON CONVERSION ERROR. PG/MySQL
        # have neither and constant-fold a CASE guard, so a literal is resolved at
        # transpile time (a non-numeric string cast to a number becomes NULL).
        if node.safe:
            if dialect == "tsql":
                return f"TRY_CAST({inner} AS {dtype})"
            if dialect == "oracle":
                return f"CAST({inner} AS {dtype} DEFAULT NULL ON CONVERSION ERROR)"
            _sup = dtype.split("(")[0].strip().upper()
            if isinstance(node.expression, Literal):
                _lv = str(node.expression.value).strip()
                if _sup in (
                    "INT",
                    "INTEGER",
                    "BIGINT",
                    "SMALLINT",
                    "TINYINT",
                    "DECIMAL",
                    "NUMERIC",
                    "NUMBER",
                    "DEC",
                    "FLOAT",
                    "DOUBLE",
                    "REAL",
                ):
                    try:
                        float(_lv)
                    except (TypeError, ValueError):
                        return "NULL"  # non-numeric literal -> safe cast is NULL
                elif _sup in ("BOOLEAN", "BOOL", "BIT") and _lv.lower() not in (
                    "true",
                    "false",
                    "t",
                    "f",
                    "yes",
                    "no",
                    "y",
                    "n",
                    "on",
                    "off",
                    "0",
                    "1",
                ):
                    return "NULL"  # non-boolean literal -> safe cast is NULL
        return f"CAST({inner} AS {dtype})"

    if isinstance(node, SubqueryExpression):
        query = node.query
        # A ``(SELECT … FOR XML/JSON)`` scalar subquery serializes its rows to a
        # single XML/JSON value — T-SQL-only. Elsewhere the clause is dropped and
        # the multi-column rows ship raw (ORA-00913 "too many values"), so degrade
        # the whole scalar to a carrier + warning.
        if getattr(query, "has_for_xml", False) and dialect != "tsql":
            return (
                "NULL /* UNIQUE: T-SQL FOR XML/JSON row serialization has no "
                "cross-engine equivalent — see docs/03-unsupported.md */"
            )
        if dialect in ("tsql", "oracle") and not node.quantifier:
            # Illegal in a T-SQL/Oracle scalar subquery without TOP/FETCH,
            # and with no LIMIT it cannot change the single-row result.
            # A set-op query hangs its ORDER BY on the LAST arm of the
            # set_query chain (wave 163), so strip along the chain.
            # (A quantified ALL/ANY subquery is multi-row — keep it.)
            query = _strip_unlimited_order_by(query)
        rendered = f"({_emit_select(query, dialect)})"
        if node.quantifier:
            # ``> ALL/ANY (subquery)`` (wave 234).
            return f"{node.quantifier} {rendered}"
        return rendered

    if isinstance(node, ExpressionList):
        inner = ", ".join(_emit_expression(item, dialect) for item in node.items)
        return f"({inner})"

    if isinstance(node, WindowFunction):
        return _emit_window(node, dialect)

    if isinstance(node, TableRef):
        return _emit_table_ref(node, dialect)

    if isinstance(node, RawSQL):
        mapped_global = _map_system_global(node.sql, dialect)
        if mapped_global is not None:
            return mapped_global
        # PostgreSQL's ``MODE() WITHIN GROUP (ORDER BY x)`` ordered-set
        # aggregate is spelled ``STATS_MODE(x)`` on Oracle (T-SQL/MySQL have
        # no equivalent and degraded the whole statement upstream).
        if dialect == "oracle":
            mode_m = re.match(
                r"(?is)^\s*MODE\s*\(\s*\)\s+WITHIN\s+GROUP\s*\(\s*ORDER\s+BY\s+"
                r"(.+?)\s*\)\s*$",
                node.sql,
            )
            if mode_m:
                arg = re.sub(
                    r"(?i)\s+(?:ASC|DESC)?\s*(?:NULLS\s+(?:FIRST|LAST))?\s*$",
                    "",
                    mode_m.group(1),
                ).strip()
                return f"STATS_MODE({arg})"
        # An unmapped construct left visible (a mapping gap) must not be
        # silent cross-dialect (P1 silent-output, 2026-07-17).
        if node.reason.startswith("unmapped operator") and SOURCE_DIALECT.get() not in (
            None,
            dialect,
        ):
            return (
                f"{node.sql} /* UNIQUE: {node.reason}; "
                f"no {dialect} mapping — review */"
            )
        # Inline expression context (e.g. a column DEFAULT): emit the raw
        # SQL directly without a wrapping comment, which would be invalid
        # inside a column definition.
        return node.sql

    return str(node)


def _emit_date_add(node: FunctionCall, dialect: str) -> str | None:
    """Emit DATE_ADD/DATE_SUB/DATEADD with the target's own idiom.

    The IR canonical form is ``(ts, n, unit)``. Emitting the 3-argument
    ``DATE_ADD(ts, 7, DAY)`` form is invalid on every engine (audit
    2026-07-02, S1-4); each target needs its native spelling.
    """
    if len(node.args) != 3:
        return None
    unit = _date_unit_name(node.args[2])
    if unit is None:
        return None
    ts = _emit_expression(_unwrap_sqlglot_wrappers(node.args[0]), dialect)
    amount = node.args[1]
    literal_n: str | None = None
    plain = _plain_int_value(amount)
    if plain is not None:
        # MySQL parses INTERVAL amounts as string literals; use the bare
        # number (a unary-minus literal counts — ``-1`` must stay INSIDE
        # the INTERVAL string on PG, not multiply a unit interval).
        literal_n = str(plain)
    n = literal_n if literal_n is not None else _emit_expression(amount, dialect)
    sub = node.name.upper() == "DATE_SUB"

    # A DATEADD whose base is a DATEDIFF result operates on a NUMBER, not
    # a date — plain arithmetic is the (live-validated) form; an interval
    # add would be invalid (Oracle) or wrongly typed (PG).
    base = _unwrap_sqlglot_wrappers(node.args[0])
    if (
        dialect in ("postgresql", "oracle")
        and isinstance(base, FunctionCall)
        and base.name.upper() == "DATEDIFF"
    ):
        op = "-" if sub else "+"
        return f"{ts} {op} {n}"

    # MySQL's DATE_ADD/TIMESTAMPADD reads a bare ``'2020-01-01[ 10:00]'`` string as
    # a date/timestamp, but on PG interval arithmetic reads it as an *interval*
    # ("invalid input syntax") and Oracle rejects the implicit string->date cast.
    # Qualify a date/datetime literal as its ANSI literal so the arithmetic runs.
    if isinstance(base, Literal) and isinstance(base.value, str):
        if dialect == "oracle":
            # Oracle's TIMESTAMP literal needs seconds (…10:00 -> ORA-01861);
            # _oracle_date_literal pads them (and picks DATE for a date-only).
            _ol = _oracle_date_literal(base.value.strip())
            if _ol is not None:
                ts = _ol
        elif dialect == "postgresql":
            _pl = _as_datetime_literal(base, dialect)
            if _pl is not None:
                ts = _pl

    if dialect == "mysql":
        fn = "DATE_SUB" if sub else "DATE_ADD"
        return f"{fn}({ts}, INTERVAL {n} {unit})"
    if dialect == "tsql":
        signed = (f"-{n}" if literal_n is not None else f"-({n})") if sub else n
        result = f"DATEADD({unit}, {signed}, {ts})"
        # MySQL date arithmetic on a DATE returns a DATE; T-SQL DATEADD returns a
        # DATETIME (…00:00:00). Cast back to DATE when the base is a date-only
        # literal so the value's type/repr matches (a datetime base keeps time).
        if SOURCE_DIALECT.get() == "mysql" and _is_date_only_literal(base):
            result = f"CAST({result} AS DATE)"
        return result
    if dialect == "postgresql":
        op = "-" if sub else "+"
        if literal_n is not None:
            return f"{ts} {op} INTERVAL '{n} {unit}'"
        return f"{ts} {op} ({n}) * INTERVAL '1 {unit}'"
    if dialect == "oracle":
        if unit in ("MONTH", "YEAR"):
            if unit == "MONTH":
                months = n
            elif literal_n is not None:
                months = str(int(literal_n) * 12)
            else:
                months = f"({n}) * 12"
            if sub:
                signed = f"-{months}" if literal_n is not None else f"-({months})"
            else:
                signed = months
            return f"ADD_MONTHS({ts}, {signed})"
        op = "-" if sub else "+"
        if unit == "WEEK":
            days = str(int(literal_n) * 7) if literal_n is not None else f"({n}) * 7"
            return f"{ts} {op} NUMTODSINTERVAL({days}, 'DAY')"
        return f"{ts} {op} NUMTODSINTERVAL({n}, '{unit}')"
    return None


def _emit_date_diff(node: FunctionCall, dialect: str) -> str | None:
    """Emit DATEDIFF with T-SQL boundary-count semantics per target.

    IR canonical argument order is ``(end, start, unit)``. T-SQL DATEDIFF
    counts unit-boundary crossings, so month/year use calendar arithmetic
    rather than elapsed-interval functions (audit 2026-07-02, S1-4).
    """
    if len(node.args) == 2:
        # MySQL DATEDIFF(end, start): whole days between two dates.
        end = _emit_expression(node.args[0], dialect)
        start = _emit_expression(node.args[1], dialect)
        if dialect == "mysql":
            return f"DATEDIFF({end}, {start})"
        if dialect == "tsql":
            return f"DATEDIFF(DAY, {start}, {end})"
        # PostgreSQL / Oracle: subtracting two dates yields the day count.
        # Oracle can't CAST an ISO string to DATE (NLS_DATE_FORMAT, ORA-01861);
        # the ANSI ``DATE '…'`` literal is valid on both engines.
        end, start = wrap_oracle_date_arg(end), wrap_oracle_date_arg(start)
        return f"(CAST({end} AS DATE) - CAST({start} AS DATE))"
    if len(node.args) != 3:
        return None
    args = node.args
    # A part-FIRST spelling (T-SQL-style DATEDIFF(part, start, end) kept
    # positional by an anonymous parse) reorders to the canonical
    # (end, start, unit).
    if _date_unit_name(args[2]) is None and _date_unit_name(args[0]) is not None:
        args = (args[2], args[1], args[0])
    unit = _date_unit_name(args[2])
    if unit is None:
        return None
    end = _emit_expression(_unwrap_sqlglot_wrappers(args[0]), dialect)
    start = _emit_expression(_unwrap_sqlglot_wrappers(args[1]), dialect)

    if dialect == "tsql":
        boundary = f"DATEDIFF({unit}, {start}, {end})"
        # MySQL TIMESTAMPDIFF counts COMPLETE periods; T-SQL DATEDIFF counts
        # unit-boundary crossings. For month/quarter/year they diverge when the
        # end's day/time has not yet reached the start's (2020-01-15 -> 2020-03-10
        # is 1 whole month, not 2): drop the incomplete final period. A
        # DATEDIFF-sourced batch keeps pure boundary counting.
        if node.name.upper() == "TIMESTAMPDIFF" and unit in (
            "YEAR",
            "QUARTER",
            "MONTH",
        ):
            return (
                f"({boundary} - CASE WHEN DATEADD({unit}, {boundary}, {start}) "
                f"> {end} THEN 1 ELSE 0 END)"
            )
        return boundary
    if dialect == "mysql":
        if unit == "DAY":
            return f"DATEDIFF({end}, {start})"
        if unit == "WEEK":
            return f"FLOOR(DATEDIFF({end}, {start}) / 7)"
        if unit == "MONTH":
            return (
                f"((YEAR({end}) * 12 + MONTH({end})) - "
                f"(YEAR({start}) * 12 + MONTH({start})))"
            )
        if unit == "YEAR":
            return f"(YEAR({end}) - YEAR({start}))"
        k = {"HOUR": 3600, "MINUTE": 60, "SECOND": 1}[unit]
        return (
            f"(FLOOR(UNIX_TIMESTAMP({end}) / {k}) - "
            f"FLOOR(UNIX_TIMESTAMP({start}) / {k}))"
        )
    if dialect == "postgresql":
        # ISO string literals need the ANSI ``DATE '…'`` form for date math.
        end, start = wrap_oracle_date_arg(end), wrap_oracle_date_arg(start)
        if unit == "DAY":
            return f"(CAST({end} AS DATE) - CAST({start} AS DATE))"
        if unit == "WEEK":
            return f"FLOOR((CAST({end} AS DATE) - CAST({start} AS DATE)) / 7)"
        if unit == "MONTH":
            return (
                f"((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))"
            )
        if unit == "YEAR":
            return f"(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))"
        k = {"HOUR": 3600, "MINUTE": 60, "SECOND": 1}[unit]
        return (
            f"(FLOOR(EXTRACT(EPOCH FROM {end}) / {k}) - "
            f"FLOOR(EXTRACT(EPOCH FROM {start}) / {k}))"
        )
    if dialect == "oracle":
        # Oracle rejects an implicit ISO-string→DATE conversion (ORA-01861);
        # emit the ANSI ``DATE '…'`` literal for a string operand.
        end, start = wrap_oracle_date_arg(end), wrap_oracle_date_arg(start)
        if unit == "DAY":
            return f"(TRUNC(CAST({end} AS DATE)) - TRUNC(CAST({start} AS DATE)))"
        if unit == "WEEK":
            return (
                f"FLOOR((TRUNC(CAST({end} AS DATE)) - "
                f"TRUNC(CAST({start} AS DATE))) / 7)"
            )
        if unit == "MONTH":
            return (
                f"((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))"
            )
        if unit == "YEAR":
            return f"(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))"
        trunc_fmt = {"HOUR": "HH24", "MINUTE": "MI"}.get(unit)
        mult = {"HOUR": 24, "MINUTE": 1440, "SECOND": 86400}[unit]
        if trunc_fmt:
            return (
                f"ROUND((TRUNC(CAST({end} AS DATE), '{trunc_fmt}') - "
                f"TRUNC(CAST({start} AS DATE), '{trunc_fmt}')) * {mult})"
            )
        return f"ROUND((CAST({end} AS DATE) - CAST({start} AS DATE)) * {mult})"
    return None


_TEXT_TYPE_NAMES = frozenset(
    {
        "TEXT",
        "VARCHAR",
        "VARCHAR2",
        "NVARCHAR",
        "CHAR",
        "NCHAR",
        "CHARACTER",
        "CHARACTER VARYING",
        "STRING",
        "CLOB",
        "NTEXT",
        "NVARCHAR2",
    }
)
_TEXT_RETURNING_FUNCS = frozenset(
    {
        "CONCAT",
        "SUBSTR",
        "SUBSTRING",
        "UPPER",
        "LOWER",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "LPAD",
        "RPAD",
        "REPLACE",
        "LEFT",
        "RIGHT",
        "TO_CHAR",
        "CHR",
        "INITCAP",
    }
)


def _is_text_valued(node: object) -> bool:
    """True when an expression is already text — no PG ``::text`` cast needed."""
    if isinstance(node, Literal):
        return node.dtype in ("string", "national")
    if isinstance(node, CastExpression):
        base = node.target_type.name.split("(")[0].strip().upper()
        return base in _TEXT_TYPE_NAMES
    if isinstance(node, FunctionCall):
        return node.name.upper() in _TEXT_RETURNING_FUNCS
    if isinstance(node, ColumnRef):
        strs = STRING_VARIABLES.get()
        return strs is not None and node.name.lstrip("@").lower() in strs
    return False


def _emit_group_concat(node: FunctionCall, dialect: str) -> str | None:
    """Emit the string-aggregation family in the target's own spelling.

    IR canonical form: ``GROUP_CONCAT(expr[, separator])``. An Oracle LISTAGG
    source may carry its WITHIN GROUP ordering folded into the first argument
    as RawSQL ("expr ORDER BY ...").
    """
    first = node.args[0]
    expr_sql: str
    order_sql: str | None = None
    if isinstance(first, RawSQL) and " ORDER BY " in first.sql:
        expr_sql, order_sql = first.sql.split(" ORDER BY ", 1)
        # The folded value/ORDER-BY text keeps the SOURCE's type names; portabilize
        # them, and map a string cast to the target's VARCHAR — LISTAGG rejects a
        # CLOB (ORA-00932) and T-SQL STRING_AGG a TEXT (error 529).
        expr_sql = _portable_types_in_sql(expr_sql.strip(), dialect)
        order_sql = re.sub(r"\s+NULLS\s+(FIRST|LAST)\s*$", "", order_sql.strip())
        order_sql = _portable_types_in_sql(order_sql, dialect)
        if dialect == "oracle":
            expr_sql = re.sub(r"(?i)\bCLOB\b", "VARCHAR2(4000)", expr_sql)
        elif dialect == "tsql":
            expr_sql = re.sub(r"(?i)\bTEXT\b", "VARCHAR(MAX)", expr_sql)
    else:
        expr_sql = _emit_expression(first, dialect)

    sep: str | None = None
    dyn_sep: str | None = None
    if len(node.args) > 1:
        sep_node = node.args[1]
        if isinstance(sep_node, Literal) and isinstance(sep_node.value, str):
            sep = sep_node.value
        elif isinstance(sep_node, Literal) and sep_node.value is None:
            # PG string_agg(x, NULL): concatenate without a separator —
            # the generic fallthrough shipped a nonexistent GROUP_CONCAT
            # on T-SQL (wave 140).
            sep = ""
        else:
            # Expression separator: keep it as the target's own argument
            # (T-SQL 2022+/PG/Oracle accept an expression; the old
            # fallthrough shipped GROUP_CONCAT raw).
            dyn_sep = _emit_expression(sep_node, dialect)
    distinct = "DISTINCT " if node.distinct else ""

    def quoted(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    def sep_sql(default: str) -> str:
        if dyn_sep is not None:
            return dyn_sep
        return quoted(sep if sep is not None else default)

    if dialect == "mysql":
        # The canonical first argument may be a generically rendered RawSQL
        # ("expr ORDER BY …"); MySQL's CAST target set differs (no TEXT).
        def _mysql_cast_targets(s: str) -> str:
            s = re.sub(r"(?i)\bAS\s+TEXT\s*\)", "AS CHAR)", s)
            return re.sub(r"(?i)\bAS\s+(?:INT|INTEGER|BIGINT)\s*\)", "AS SIGNED)", s)

        expr_sql = _mysql_cast_targets(expr_sql)
        if order_sql:
            order_sql = _mysql_cast_targets(order_sql)
        order = f" ORDER BY {order_sql}" if order_sql else ""
        if dyn_sep is not None:
            separator = f" SEPARATOR {dyn_sep}"
        else:
            separator = f" SEPARATOR {quoted(sep)}" if sep is not None else ""
        return f"GROUP_CONCAT({distinct}{expr_sql}{order}{separator})"
    if dialect == "postgresql":
        # PG string_agg(value, sep) demands a text value and will NOT implicitly
        # stringify — unlike T-SQL STRING_AGG / Oracle LISTAGG / MySQL
        # GROUP_CONCAT — so ``string_agg(int, …)`` errors "function does not
        # exist". Cast the value to text (text→text is a no-op) unless it is
        # already text. With DISTINCT, an ORDER BY must match the argument, so
        # order by the cast value too.
        value = expr_sql
        if not _is_text_valued(first):
            value = f"CAST({expr_sql} AS TEXT)"
            if node.distinct and order_sql == expr_sql:
                order_sql = value
        order = f" ORDER BY {order_sql}" if order_sql else ""
        return f"STRING_AGG({distinct}{value}, {sep_sql(',')}{order})"
    if dialect == "tsql":
        within = f" WITHIN GROUP (ORDER BY {order_sql})" if order_sql else ""
        return f"STRING_AGG({expr_sql}, {sep_sql(',')}){within}"
    if dialect == "oracle":
        # LISTAGG requires WITHIN GROUP; default to ordering by the
        # aggregated expression itself when the source specified none.
        order = order_sql or expr_sql
        return (
            f"LISTAGG({distinct}{expr_sql}, {sep_sql(',')}) "
            f"WITHIN GROUP (ORDER BY {order})"
        )
    return None


def _emit_function(node: FunctionCall, dialect: str) -> str:
    """Emit a function call."""
    fn_name = node.name.upper()
    # A parameterless aggregate call is invalid on every engine — PG's own
    # error says "count(*) must be used"; that IS the faithful spelling.
    if fn_name == "COUNT" and not node.args and not node.distinct:
        return "COUNT(*)"
    # sqlglot-internal cast wrappers must never reach the output.
    if fn_name in _SQLGLOT_WRAPPERS and len(node.args) == 1:
        inner = node.args[0]
        # MySQL/T-SQL ``DATE(x)`` genuinely extracts the date part (drops any
        # time); sqlglot models it as this wrapper. Unwrapping to the bare
        # expression silently keeps the time on the target, so a timestamp
        # argument comes back with its clock component. Preserve the truncation
        # with an explicit CAST for anything that is not a plain literal (those
        # are handled as ANSI date literals elsewhere).
        if fn_name == "TS_OR_DS_TO_DATE" and not isinstance(inner, Literal):
            return f"CAST({_emit_expression(inner, dialect)} AS DATE)"
        return _emit_expression(inner, dialect)

    # GREATEST/LEAST compare strings by collation: PostgreSQL/Oracle are
    # case-sensitive (GREATEST('a','B') = 'a', since 'a' > 'B' by code point),
    # but MySQL's and T-SQL's default collations are case-insensitive ('B'). Force
    # a binary collation on the first string-literal argument so the whole
    # comparison is case-sensitive.
    if (
        fn_name in ("GREATEST", "LEAST")
        and dialect in ("mysql", "tsql")
        and SOURCE_DIALECT.get() in ("postgresql", "oracle")
        and node.args
        and all(isinstance(a, Literal) and isinstance(a.value, str) for a in node.args)
    ):
        _coll = "utf8mb4_bin" if dialect == "mysql" else "Latin1_General_BIN2"
        _parts = [_emit_expression(a, dialect) for a in node.args]
        _parts[0] = f"{_parts[0]} COLLATE {_coll}"
        return f"{fn_name}({', '.join(_parts)})"

    # MySQL EXTRACTVALUE(xml_string, xpath) returns the text of the first matching
    # node. Oracle's own EXTRACTVALUE needs an XMLTYPE (a bare string is ORA-00932);
    # PG uses XPATH(...'/text()')[1], T-SQL an XML .value(). A literal xpath is
    # required for T-SQL's compile-time .value() path.
    if fn_name == "EXTRACTVALUE" and len(node.args) == 2 and dialect != "mysql":
        _xml = _emit_expression(node.args[0], dialect)
        _xp = node.args[1]
        if dialect == "oracle":
            return f"EXTRACTVALUE(XMLTYPE({_xml}), {_emit_expression(_xp, dialect)})"
        if isinstance(_xp, Literal) and isinstance(_xp.value, str):
            if dialect == "postgresql":
                return f"(XPATH('{_xp.value}/text()', {_xml}::XML))[1]::TEXT"
            if dialect == "tsql":
                return (
                    f"CAST({_xml} AS XML).value("
                    f"'({_xp.value}/text())[1]', 'NVARCHAR(MAX)')"
                )

    # MySQL UpdateXML(xml, xpath, new_fragment) replaces the matched node. PG has
    # no such function; T-SQL uses .modify() XML-DML and Oracle's UPDATEXML has a
    # different XMLTYPE signature/semantics — no faithful cross-engine form, so
    # degrade to a carrier (ExtractValue in the same statement still translates).
    if (
        fn_name == "UPDATEXML"
        and SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
    ):
        return (
            "NULL /* UNIQUE: MySQL UpdateXML has no cross-engine equivalent "
            "(PG lacks it; T-SQL .modify() and Oracle UPDATEXML differ) — "
            "see docs/03-unsupported.md */"
        )

    # COLLATION(x) returns the argument's collation NAME, which is engine-specific
    # (MySQL 'utf8mb4_0900_ai_ci' vs Oracle 'USING_NLS_COMP') — the function
    # exists on both but can never return the same value. Flag it.
    if (
        fn_name == "COLLATION"
        and SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
        and len(node.args) == 1
    ):
        _c = _emit_expression(node.args[0], dialect)
        return (
            f"COLLATION({_c}) /* UNIQUE: collation names are engine-specific and "
            "cannot match across engines (docs/03-unsupported.md) */"
        )

    # Oracle REGEXP_SUBSTR(str, pat, pos, occ, match, GROUP) extracts a capture
    # group; MySQL's REGEXP_SUBSTR has no group argument (and takes at most 5
    # args), so the 6-arg form shipped an invalid call. Emit the portable
    # ``(str, pat, pos, occ)`` subset plus a carrier — group extraction has no
    # MySQL equivalent (and the match value diverges without it).
    if fn_name == "REGEXP_SUBSTR" and dialect == "mysql" and len(node.args) >= 6:
        _base = ", ".join(_emit_expression(a, dialect) for a in node.args[:4])
        return (
            f"REGEXP_SUBSTR({_base}) /* UNIQUE: Oracle REGEXP_SUBSTR capture-group "
            "extraction (6th arg) has no MySQL equivalent (docs/03-unsupported.md) */"
        )

    # Oracle ROUND(date, 'MONTH') rounds to the nearest month start (day >= 16
    # rounds up to the 1st of next month) — MySQL's ROUND is numeric and would
    # ship an invalid ``ROUND('2020-06-16', 'MONTH')``. Emulate with month
    # arithmetic (live-verified against Oracle across the 15/16 boundary).
    if (
        fn_name == "ROUND"
        and dialect == "mysql"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and isinstance(node.args[1].value, str)
        and node.args[1].value.upper() in ("MONTH", "MM")
    ):
        _d = _emit_expression(_unwrap_sqlglot_wrappers(node.args[0]), dialect)
        _first = f"DATE_SUB({_d}, INTERVAL DAYOFMONTH({_d}) - 1 DAY)"
        return (
            f"CASE WHEN DAYOFMONTH({_d}) < 16 THEN {_first} "
            f"ELSE DATE_ADD({_first}, INTERVAL 1 MONTH) END"
        )

    # T-SQL AVG returns the *input* type, so AVG over an integer column truncates
    # (AVG of 1, 2 = 1), whereas MySQL/Oracle/PostgreSQL always average as a
    # decimal (1.5). Promote the argument so T-SQL averages as a decimal too.
    if (
        fn_name == "AVG"
        and dialect == "tsql"
        and SOURCE_DIALECT.get() in ("mysql", "oracle", "postgresql")
        and len(node.args) == 1
    ):
        _avg_distinct = "DISTINCT " if node.distinct else ""
        _avg_arg = _emit_expression(node.args[0], dialect)
        return f"AVG({_avg_distinct}({_avg_arg}) * 1.0)"

    # T-SQL LEN excludes trailing spaces (LEN('abc   ') = 3); MySQL CHAR_LENGTH
    # and Oracle/PG LENGTH count them (6). LEN normalizes to a LENGTH node, so on
    # a T-SQL source trim trailing spaces to preserve the count on other targets.
    if (
        fn_name == "LENGTH"
        and SOURCE_DIALECT.get() == "tsql"
        and dialect != "tsql"
        and len(node.args) == 1
    ):
        _len_arg = _emit_expression(node.args[0], dialect)
        _len_fn = "CHAR_LENGTH" if dialect == "mysql" else "LENGTH"
        return f"{_len_fn}(RTRIM({_len_arg}))"

    # The reverse: Oracle/PostgreSQL LENGTH counts trailing spaces, but T-SQL LEN
    # drops them (LEN('abc   ') = 3 vs LENGTH = 6). Preserve the count on a T-SQL
    # target with the standard LEN(x + '.') - 1 trick — the sentinel char anchors
    # the trailing run (NULL stays NULL: NULL + '.' = NULL).
    if (
        fn_name == "LENGTH"
        and SOURCE_DIALECT.get() in ("oracle", "postgresql")
        and dialect == "tsql"
        and len(node.args) == 1
    ):
        _lt_arg = _emit_expression(node.args[0], dialect)
        return f"LEN({_lt_arg} + '.') - 1"

    # MySQL's GREATEST/LEAST return NULL if ANY argument is NULL; PostgreSQL and
    # T-SQL ignore NULLs (GREATEST(1, NULL, 3) = 3 there). Preserve MySQL's
    # NULL-propagation with a guard (Oracle already propagates, so it is left).
    if (
        fn_name in ("GREATEST", "LEAST")
        and SOURCE_DIALECT.get() == "mysql"
        and dialect in ("postgresql", "tsql")
        and node.args
    ):
        _gl_args = [_emit_expression(a, dialect) for a in node.args]
        _gl_null = " OR ".join(f"{a} IS NULL" for a in _gl_args)
        _gl_call = f"{fn_name}({', '.join(_gl_args)})"
        return f"CASE WHEN {_gl_null} THEN NULL ELSE {_gl_call} END"

    # The reverse: PostgreSQL (and T-SQL) GREATEST/LEAST IGNORE NULL arguments
    # (GREATEST(1, NULL, 3) = 3), while MySQL/Oracle propagate NULL. Drop a
    # literal NULL argument so the max/min over the remaining values matches
    # (all-NULL collapses to NULL; a single survivor is that value — MySQL
    # rejects a 1-arg GREATEST/LEAST).
    if (
        fn_name in ("GREATEST", "LEAST")
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect in ("mysql", "oracle")
        and any(isinstance(a, Literal) and a.value is None for a in node.args)
    ):
        _gl_kept = [
            a for a in node.args if not (isinstance(a, Literal) and a.value is None)
        ]
        if not _gl_kept:
            return "NULL"
        if len(_gl_kept) == 1:
            return _emit_expression(_gl_kept[0], dialect)
        _gl_keep_sql = ", ".join(_emit_expression(a, dialect) for a in _gl_kept)
        return f"{fn_name}({_gl_keep_sql})"

    # Oracle BITAND(a, b) is a bitwise AND; the other engines spell it with the
    # & operator (Oracle keeps BITAND, which it has natively; PG has no BITAND).
    if fn_name == "BITAND" and len(node.args) == 2 and dialect != "oracle":
        _ba = _emit_expression(node.args[0], dialect)
        _bb = _emit_expression(node.args[1], dialect)
        return f"({_ba} & {_bb})"

    # MySQL ATAN(y, x) is the 2-argument arctangent (= ATAN2); Oracle/PG have
    # ATAN2 and T-SQL has ATN2. (1-arg ATAN and a MySQL target are unchanged.)
    if fn_name == "ATAN" and len(node.args) == 2 and dialect != "mysql":
        _at_args = ", ".join(_emit_expression(a, dialect) for a in node.args)
        return f"{'ATN2' if dialect == 'tsql' else 'ATAN2'}({_at_args})"

    # MySQL/PostgreSQL ASCII('') is 0; Oracle/T-SQL return NULL (Oracle stores ''
    # as NULL, T-SQL's ASCII('') is NULL). Recover the 0: T-SQL distinguishes ''
    # from NULL (a faithful CASE — ASCII(NULL) stays NULL); Oracle cannot, so
    # COALESCE picks the empty-string reading (the inherent Oracle '' = NULL edge
    # means a genuine NULL argument also reads as 0 there).
    if (
        fn_name == "ASCII"
        and SOURCE_DIALECT.get() in ("mysql", "postgresql")
        and len(node.args) == 1
        and dialect in ("oracle", "tsql")
    ):
        _asc_x = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"CASE WHEN {_asc_x} = '' THEN 0 ELSE ASCII({_asc_x}) END"
        return f"COALESCE(ASCII({_asc_x}), 0)"

    # MySQL CONCAT returns NULL if ANY argument is NULL (it propagates NULL);
    # PG/Oracle/T-SQL CONCAT ignore NULL. When a MySQL CONCAT has a literal NULL
    # argument, the whole result is NULL — fold it (MySQL target keeps native
    # CONCAT, which already propagates).
    if (
        fn_name == "CONCAT"
        and SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
        and any(isinstance(a, Literal) and a.value is None for a in node.args)
    ):
        return "NULL"

    # Oracle REPLACE(str, search) [2-arg] omits the replacement, removing every
    # occurrence of search; an all-removed empty result becomes NULL (Oracle's
    # empty string = NULL). PG/T-SQL/MySQL REPLACE require 3 args, so supply the
    # '' and reproduce Oracle's empty->NULL with NULLIF.
    if (
        fn_name == "REPLACE"
        and len(node.args) == 2
        and SOURCE_DIALECT.get() == "oracle"
        and dialect != "oracle"
    ):
        _r0 = _emit_expression(node.args[0], dialect)
        _r1 = _emit_expression(node.args[1], dialect)
        return f"NULLIF(REPLACE({_r0}, {_r1}, ''), '')"

    # TRANSLATE(str, from, to) is a per-character map. Oracle/PG have it natively
    # and T-SQL 2017+ does too, but MySQL has none — and a nested REPLACE is
    # order-dependent (not equivalent), so degrade to a documented carrier.
    if fn_name == "TRANSLATE" and dialect == "mysql" and len(node.args) == 3:
        return (
            "NULL /* UNIQUE: MySQL has no TRANSLATE and a nested-REPLACE "
            "emulation is order-dependent (not equivalent) — "
            "see docs/03-unsupported.md */"
        )

    # MySQL REPLACE propagates NULL — REPLACE(str, NULL, x) is NULL — while
    # Oracle's REPLACE ignores a NULL search/replace and returns the subject
    # unchanged. With a literal NULL argument the MySQL result is NULL; fold it
    # (PG already propagates; MySQL target keeps native REPLACE).
    if (
        fn_name == "REPLACE"
        and SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
        and any(isinstance(a, Literal) and a.value is None for a in node.args)
    ):
        return "NULL"

    # MySQL/Oracle/PostgreSQL REPLACE matches case-sensitively; T-SQL uses the
    # subject's collation (case-insensitive by default), so REPLACE('AbC','a','X')
    # would also replace the 'A'. Force a binary collation on a literal subject so
    # only the exact-case matches are replaced (a column keeps its own collation).
    if (
        fn_name == "REPLACE"
        and dialect == "tsql"
        and SOURCE_DIALECT.get() in ("mysql", "oracle", "postgresql")
        and len(node.args) >= 3
        and isinstance(node.args[0], Literal)
        and isinstance(node.args[0].value, str)
    ):
        subj = _emit_expression(node.args[0], dialect)
        rest = ", ".join(_emit_expression(a, dialect) for a in node.args[1:])
        return f"REPLACE({subj} COLLATE Latin1_General_BIN2, {rest})"

    # The reverse: T-SQL/PG/Oracle CONCAT() *ignore* a NULL argument, so a
    # literal NULL contributes nothing. Drop it (otherwise MySQL's NULL-
    # propagating CONCAT would turn the whole result NULL). The ``||`` operator
    # is a separate BinaryOp and is untouched.
    if (
        fn_name == "CONCAT"
        and SOURCE_DIALECT.get() in ("tsql", "postgresql", "oracle")
        and any(isinstance(a, Literal) and a.value is None for a in node.args)
    ):
        _kept = tuple(
            a for a in node.args if not (isinstance(a, Literal) and a.value is None)
        )
        if _kept:
            return _emit_function(dataclasses.replace(node, args=_kept), dialect)

    # MySQL booleans are integers, so CONCAT(TRUE, FALSE) is '10'; PostgreSQL
    # renders the boolean literals 't'/'f'. Emit them as 1/0 in this string
    # context (only PG needs it — T-SQL/Oracle already render boolean 1/0).
    if (
        fn_name == "CONCAT"
        and dialect == "postgresql"
        and SOURCE_DIALECT.get() == "mysql"
        and any(isinstance(a, Literal) and a.dtype == "boolean" for a in node.args)
    ):
        _cb_parts = [
            (
                ("1" if a.value else "0")
                if isinstance(a, Literal) and a.dtype == "boolean"
                else _emit_expression(a, dialect)
            )
            for a in node.args
        ]
        return f"CONCAT({', '.join(_cb_parts)})"

    # Oracle renders a DATE concatenated to a string through NLS_DATE_FORMAT
    # ('01-JAN-20'), unlike MySQL's ISO 'yyyy-mm-dd'. Wrap a DATE-valued CONCAT
    # argument in TO_CHAR(…, 'YYYY-MM-DD') to preserve the ISO text.
    if (
        fn_name == "CONCAT"
        and dialect == "oracle"
        and any(
            isinstance(a, CastExpression) and a.target_type.name.upper() == "DATE"
            for a in node.args
        )
    ):
        _dc_args = tuple(
            (
                FunctionCall(
                    name="TO_CHAR",
                    args=(a, Literal(value="YYYY-MM-DD", dtype="string")),
                )
                if isinstance(a, CastExpression)
                and a.target_type.name.upper() == "DATE"
                else a
            )
            for a in node.args
        )
        return _emit_function(dataclasses.replace(node, args=_dc_args), dialect)

    # PG's binary DECODE(text, 'hex') — not Oracle's conditional DECODE
    # (that one has 3+ args and became a CASE upstream). Faithful hex
    # mappings exist everywhere (wave 139); other formats stay put.
    if (
        fn_name == "DECODE"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and str(node.args[1].value).lower() == "hex"
    ):
        arg = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"CONVERT(VARBINARY(MAX), {arg}, 2)"
        if dialect == "oracle":
            return f"HEXTORAW({arg})"
        if dialect == "mysql":
            return f"UNHEX({arg})"

    # MySQL REPEAT is T-SQL REPLICATE (same signature; PG/Oracle keep
    # REPEAT). And a single-argument CONCAT — valid MySQL/PG — needs 2+
    # on T-SQL/Oracle: it IS its argument (wave 154).
    if fn_name == "REPEAT" and dialect == "tsql" and len(node.args) == 2:
        _rp_s = _emit_expression(node.args[0], dialect)
        _rp_n = _emit_expression(node.args[1], dialect)
        # MySQL rounds a float count and returns '' for a negative one; T-SQL
        # REPLICATE truncates the float and returns NULL for a negative. Round
        # (T-SQL ROUND needs an explicit scale — error 189) and clamp, for a
        # MySQL source, skipping a provably integer non-negative literal.
        if SOURCE_DIALECT.get() == "mysql" and not _is_nonneg_int_literal(node.args[1]):
            _rp_n = f"ROUND({_rp_n}, 0)"
            _rp_n = f"CASE WHEN {_rp_n} < 0 THEN 0 ELSE {_rp_n} END"
        return f"REPLICATE({_rp_s}, {_rp_n})"
    # MySQL rounds a float LEFT length (LEFT('hello', 2.9) = 'hel') and returns
    # '' for a negative one; T-SQL LEFT truncates the float and errors on a
    # negative. Round (with the scale T-SQL needs) and clamp.
    if (
        fn_name == "LEFT"
        and SOURCE_DIALECT.get() == "mysql"
        and dialect == "tsql"
        and len(node.args) == 2
        and not _is_nonneg_int_literal(node.args[1])
    ):
        _lf_s = _emit_expression(node.args[0], dialect)
        _lf_n = f"ROUND({_emit_expression(node.args[1], dialect)}, 0)"
        return f"LEFT({_lf_s}, CASE WHEN {_lf_n} < 0 THEN 0 ELSE {_lf_n} END)"
    # MySQL LEFT with a negative length returns '' ; PostgreSQL reads a negative
    # length as "all but the last |n|". Clamp to 0 to preserve the empty string.
    if (
        fn_name == "LEFT"
        and SOURCE_DIALECT.get() == "mysql"
        and dialect == "postgresql"
        and len(node.args) == 2
        and not _is_nonneg_literal(node.args[1])
    ):
        _lf_s = _emit_expression(node.args[0], dialect)
        _lf_n = _emit_expression(node.args[1], dialect)
        return f"LEFT({_lf_s}, CASE WHEN {_lf_n} < 0 THEN 0 ELSE {_lf_n} END)"
    # The reverse: PostgreSQL LEFT with a negative length returns "all but the
    # last |n|" (LEFT('abc', -1) = 'ab'); MySQL returns '' for a negative length.
    # Reproduce PostgreSQL's semantics: LEFT(s, GREATEST(CHAR_LENGTH(s) + n, 0)).
    if (
        fn_name == "LEFT"
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect == "mysql"
        and len(node.args) == 2
        and isinstance(node.args[1], UnaryOp)
        and node.args[1].operator == UnaryOperator.NEGATIVE
    ):
        _lf_s = _emit_expression(node.args[0], dialect)
        _lf_n = _emit_expression(node.args[1], dialect)
        return f"LEFT({_lf_s}, GREATEST(CHAR_LENGTH({_lf_s}) + {_lf_n}, 0))"
    if fn_name == "CONCAT" and len(node.args) == 1 and dialect in ("tsql", "oracle"):
        return _emit_expression(node.args[0], dialect)
    # A CONCAT chain emits ONE flat call on MySQL (nested CONCATs are valid
    # but the flat form is the canonical output both pipelines agree on).
    if fn_name == "CONCAT" and dialect == "mysql" and len(node.args) >= 2:
        flat: list[str] = []

        def _gather_concat_args(n: ASTNode) -> None:
            inner = _unwrap_sqlglot_wrappers(n)
            if isinstance(inner, FunctionCall) and inner.name.upper() == "CONCAT":
                for a in inner.args:
                    _gather_concat_args(a)
            else:
                flat.append(_emit_expression(n, dialect))

        for concat_arg in node.args:
            _gather_concat_args(concat_arg)
        return f"CONCAT({', '.join(flat)})"
    # Same for a single-argument COALESCE (T-SQL error 1088 / Oracle ORA-00938:
    # at least two arguments) — it IS its argument (wave 161).
    if fn_name == "COALESCE" and len(node.args) == 1 and dialect in ("tsql", "oracle"):
        return _emit_expression(node.args[0], dialect)
    # PG SUBSTRING(text FROM posix_pattern) — extract the first regex match — is
    # modelled as a 2-arg SUBSTRING whose 2nd arg is a STRING (a numeric 2nd arg
    # is an ordinary start position). Oracle/MySQL have REGEXP_SUBSTR; T-SQL has
    # no POSIX regex engine, so it degrades to NULL + a documented carrier. Must
    # run before the T-SQL 2-arg->3-arg LEN rewrite below (which would treat the
    # pattern as a start position).
    if (
        fn_name in ("SUBSTRING", "SUBSTR")
        and SOURCE_DIALECT.get() == "postgresql"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and node.args[1].dtype == "string"
    ):
        rs_x = _emit_expression(node.args[0], dialect)
        rs_pat_node = node.args[1]
        if dialect == "tsql":
            return (
                "NULL /* UNIQUE: SUBSTRING(x FROM POSIX pattern) has no T-SQL "
                "regex equivalent — see docs/03-unsupported.md */"
            )
        rs_pat = _emit_expression(rs_pat_node, dialect)
        if dialect == "mysql" and isinstance(rs_pat_node.value, str):
            pv = rs_pat_node.value.replace("\\", "\\\\")
            rs_pat = "'" + pv.replace("'", "''") + "'"
        return f"REGEXP_SUBSTR({rs_x}, {rs_pat})"

    # PG SUBSTRING(x FROM sql_regex FOR escape) — the SQL-standard SIMILAR TO form
    # (string pattern + string escape char) — has no cross-engine equivalent: its
    # metacharacters (%/_ wildcards) and #"…"# capture markers differ from POSIX,
    # so a REGEXP_SUBSTR mapping would be unfaithful. Degrade off PG.
    if (
        fn_name in ("SUBSTRING", "SUBSTR")
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect != "postgresql"
        and len(node.args) == 3
        and isinstance(node.args[1], Literal)
        and node.args[1].dtype == "string"
        and isinstance(node.args[2], Literal)
        and node.args[2].dtype == "string"
    ):
        return (
            "NULL /* UNIQUE: SUBSTRING(x FROM SIMILAR-TO pattern FOR escape) has "
            "no cross-engine equivalent (SQL-regex metachars differ from POSIX) — "
            "see docs/03-unsupported.md */"
        )

    # MySQL SUBSTRING rounds a fractional position/length (2.9 -> 3), but
    # Oracle/PG/T-SQL truncate it (2). Pre-round a fractional numeric-literal
    # argument on a MySQL source so the result matches.
    if (
        fn_name == "SUBSTRING"
        and dialect in ("oracle", "postgresql", "tsql")
        and SOURCE_DIALECT.get() == "mysql"
        and len(node.args) in (2, 3)
        and any(
            isinstance(a, Literal)
            and isinstance(a.value, float)
            and a.value != int(a.value)
            for a in node.args[1:]
        )
    ):
        _rounded: list[ASTNode] = [node.args[0]]
        for _arg in node.args[1:]:
            if (
                isinstance(_arg, Literal)
                and isinstance(_arg.value, float)
                and _arg.value != int(_arg.value)
            ):
                _rounded.append(Literal(value=int(_arg.value + 0.5), dtype="integer"))
            else:
                _rounded.append(_arg)
        return _emit_function(dataclasses.replace(node, args=tuple(_rounded)), dialect)

    # Oracle/MySQL SUBSTR(s, -n[, len]) counts the start position from the END;
    # PG/T-SQL SUBSTRING is 1-indexed from the start and reads -n literally (an
    # empty/left-of-string result). Convert a negative literal start:
    # start = LENGTH(s) + (-n) + 1. (The 0-start and |n|>len edges are left for
    # a dedicated pass.)
    if (
        fn_name == "SUBSTRING"
        and dialect in ("postgresql", "tsql")
        and len(node.args) in (2, 3)
        and SOURCE_DIALECT.get() in ("oracle", "mysql")
        and isinstance(node.args[1], UnaryOp)
        and node.args[1].operator == UnaryOperator.NEGATIVE
    ):
        s = _emit_expression(node.args[0], dialect)
        neg = _emit_expression(node.args[1], dialect)
        lenfn = "LEN" if dialect == "tsql" else "LENGTH"
        startpos = f"{lenfn}({s}) + ({neg}) + 1"
        if len(node.args) == 3:
            length = _emit_expression(node.args[2], dialect)
        elif dialect == "postgresql":
            return f"SUBSTRING({s}, {startpos})"  # PG 2-arg runs to the end
        else:
            length = f"{lenfn}({s})"  # T-SQL needs a length; to the end
        return f"SUBSTRING({s}, {startpos}, {length})"
    # Oracle SUBSTR treats a start position of 0 as 1; the other engines read 0
    # literally (PG/T-SQL a char short, MySQL an empty string). Oracle-source
    # only — MySQL's own SUBSTR(s, 0) is '' by design, so don't touch that.
    if (
        fn_name == "SUBSTRING"
        and dialect in ("postgresql", "tsql", "mysql")
        and len(node.args) in (2, 3)
        and SOURCE_DIALECT.get() == "oracle"
        and isinstance(node.args[1], Literal)
        and node.args[1].value == 0
    ):
        s = _emit_expression(node.args[0], dialect)
        if len(node.args) == 3:
            return f"SUBSTRING({s}, 1, {_emit_expression(node.args[2], dialect)})"
        if dialect == "tsql":
            return f"SUBSTRING({s}, 1, LEN({s}))"
        return f"SUBSTRING({s}, 1)"  # PG/MySQL 2-arg runs to the end
    # PostgreSQL (and T-SQL) SUBSTRING(s, start, len) with a start <= 0 count the
    # out-of-range leading positions toward the length: SUBSTRING('abcdef', 0, 3)
    # is 'ab' (positions 0,1,2 -> the two real chars). Oracle clamps 0 to 1
    # ('abc') and MySQL returns '' for start 0, so reproduce PG's length
    # reduction with a 1-based start and an adjusted length (start + len - 1).
    if (
        fn_name == "SUBSTRING"
        and dialect in ("oracle", "mysql")
        and len(node.args) == 3
        and SOURCE_DIALECT.get() == "postgresql"
        and isinstance(node.args[1], Literal)
        and isinstance(node.args[1].value, int)
        and not isinstance(node.args[1].value, bool)
        and node.args[1].value <= 0
    ):
        s = _emit_expression(node.args[0], dialect)
        _sub_start = node.args[1].value
        if isinstance(node.args[2], Literal) and isinstance(node.args[2].value, int):
            adj = str(node.args[2].value + _sub_start - 1)  # fold to a constant
        else:
            length = _emit_expression(node.args[2], dialect)
            adj = f"{length} + ({_sub_start - 1})"
        return f"SUBSTR({s}, 1, {adj})"
    # T-SQL's SUBSTRING requires the length argument (error 174); the
    # 2-argument form means "to the end" — LEN(x) always covers it.
    if fn_name == "SUBSTRING" and dialect == "tsql" and len(node.args) == 2:
        a0 = _emit_expression(node.args[0], dialect)
        a1 = _emit_expression(node.args[1], dialect)
        return f"SUBSTRING({a0}, {a1}, LEN({a0}))"
    # Character-set TRIM. Canonical IR: TRIM(remset, string[, position]) — the
    # set to strip first, the string second, an optional keyword literal
    # (BOTH/LEADING/TRAILING) last. Covers MySQL's comma form and the standard
    # ``TRIM([pos] set FROM s)`` (the comma form is error 174 / ORA-00907 off
    # MySQL — wave 188).
    if fn_name == "TRIM" and len(node.args) in (2, 3):
        rem = _emit_expression(node.args[0], dialect)
        s = _emit_expression(node.args[1], dialect)
        position = "BOTH"
        if len(node.args) == 3 and isinstance(node.args[2], Literal):
            position = str(node.args[2].value).upper()
        # Oracle's TRIM(BOTH c FROM s) accepts only a SINGLE trim character
        # (ORA-30001); LTRIM/RTRIM accept a multi-character set on every side,
        # matching the PG/MySQL "trim any char in the set" semantics.
        if dialect == "oracle":
            if position == "LEADING":
                return f"LTRIM({s}, {rem})"
            if position == "TRAILING":
                return f"RTRIM({s}, {rem})"
            return f"LTRIM(RTRIM({s}, {rem}), {rem})"
        if dialect == "tsql" and position == "BOTH":
            return f"TRIM({rem} FROM {s})"
        return f"TRIM({position} {rem} FROM {s})"

    # PG's function-style casts (``float8(x)``, ``int4(x)`` …): only PG
    # has them (wave 200) — everywhere else they are CAST, routed through
    # the normal cast machinery (per-dialect type maps included).
    if (
        fn_name in _PG_FUNCTION_CASTS
        and len(node.args) == 1
        and dialect != "postgresql"
        and SOURCE_DIALECT.get() == "postgresql"
    ):
        return _emit_expression(
            CastExpression(
                expression=node.args[0],
                target_type=DataType(name=_PG_FUNCTION_CASTS[fn_name]),
            ),
            dialect,
        )

    # MySQL's VALUES(col) is only meaningful inside INSERT … ON
    # DUPLICATE KEY UPDATE; anywhere else MySQL itself evaluates it to
    # NULL — the faithful mapping (wave 223).
    if fn_name == "VALUES" and len(node.args) == 1 and dialect != "mysql":
        return (
            "NULL /* UNIQUE: MySQL VALUES(col) outside INSERT … ON "
            "DUPLICATE KEY UPDATE is NULL */"
        )

    # MySQL's CONNECTION_ID(): every engine has a session id under a
    # different name (wave 171) — dbo.connection_id shipped as a fake
    # UDF on T-SQL.
    if fn_name == "CONNECTION_ID" and not node.args:
        if dialect == "tsql":
            return "@@SPID"
        if dialect == "postgresql":
            return "pg_backend_pid()"
        if dialect == "oracle":
            return "SYS_CONTEXT('USERENV', 'SID')"
        return "CONNECTION_ID()"

    # Oracle MONTHS_BETWEEN(d1, d2): fractional months = whole months +
    # (day1 - day2)/31, except when both are their month's last day (or the same
    # day-of-month), which yields a whole number. Only T-SQL lacks it (its
    # DATEDIFF(MONTH,…) is an integer boundary count); PG/MySQL are handled
    # elsewhere. Emit the exact CASE (live-verified against Oracle).
    if fn_name == "MONTHS_BETWEEN" and len(node.args) == 2 and dialect == "tsql":
        d1 = _emit_expression(node.args[0], dialect)
        d2 = _emit_expression(node.args[1], dialect)
        return (
            f"CASE WHEN DAY({d1}) = DAY({d2}) OR (DAY({d1}) = DAY(EOMONTH({d1})) "
            f"AND DAY({d2}) = DAY(EOMONTH({d2}))) THEN DATEDIFF(MONTH, {d2}, {d1}) "
            f"ELSE DATEDIFF(MONTH, {d2}, {d1}) + (DAY({d1}) - DAY({d2})) / 31.0 END"
        )

    # MySQL's INTERVAL(x, v1, v2, …) index function: position of the
    # last threshold ≤ x, −1 for NULL x. Only MySQL has it; the CASE
    # chain is the mechanical form everywhere else (wave 165).
    if fn_name == "INTERVAL" and len(node.args) >= 2:
        if dialect == "mysql":
            args = ", ".join(_emit_expression(a, dialect) for a in node.args)
            return f"INTERVAL({args})"
        x = _emit_expression(node.args[0], dialect)
        whens = [f"WHEN {x} IS NULL THEN -1"]
        for i, threshold in enumerate(node.args[1:]):
            t = _emit_expression(threshold, dialect)
            whens.append(f"WHEN {x} < {t} THEN {i}")
        return f"CASE {' '.join(whens)} ELSE {len(node.args) - 1} END"

    # Date arithmetic has a distinct spelling per engine.
    # MySQL's TIMESTAMPADD(unit, n, ts) — argument order differs from
    # the canonical DATE_ADD(ts, n, unit) (wave 232); reorder, then let
    # the date-add emitter spell each target.
    if fn_name == "TIMESTAMPADD" and len(node.args) == 3 and dialect != "mysql":
        reordered = dataclasses.replace(
            node,
            name="DATE_ADD",
            args=(node.args[2], node.args[1], node.args[0]),
        )
        emitted = _emit_date_add(reordered, dialect)
        if emitted is not None:
            return emitted
    if fn_name in ("DATE_ADD", "DATE_SUB", "DATEADD"):
        emitted = _emit_date_add(node, dialect)
        if emitted is not None:
            return emitted
        if len(node.args) == 3:
            # Unknown part: keep the SOURCE-visible T-SQL spelling for
            # manual review (the canonical 3-arg DATE_ADD form is invalid
            # on every engine — audit S1-4).
            unit_sql = _emit_expression(node.args[2], dialect).strip("'\"")
            n_sql = _emit_expression(node.args[1], dialect)
            ts_sql = _emit_expression(node.args[0], dialect)
            return f"DATEADD({unit_sql}, {n_sql}, {ts_sql})"
    if fn_name in ("DATEDIFF", "TIMESTAMPDIFF"):
        emitted = _emit_date_diff(node, dialect)
        if emitted is not None:
            return emitted
        if len(node.args) == 3:
            unit_sql = _emit_expression(node.args[0], dialect).strip("'\"")
            a_sql = _emit_expression(node.args[1], dialect)
            b_sql = _emit_expression(node.args[2], dialect)
            return f"DATEDIFF({unit_sql}, {a_sql}, {b_sql})"

    # String aggregation: IR canonical form is GROUP_CONCAT(expr[, sep]).
    # Each engine spells it differently, and MySQL's comma form
    # GROUP_CONCAT(x, ',') concatenates ',' onto every value instead of
    # separating them (audit 2026-07-02, S1-8/S2-1).
    if fn_name in ("GROUP_CONCAT", "STRING_AGG", "LISTAGG") and node.args:
        emitted = _emit_group_concat(node, dialect)
        if emitted is not None:
            return emitted

    # Statistical aggregates: sqlglot canonicalizes var_pop -> VARIANCE_POP
    # (accepted by NO engine) and keeps VARIANCE/STDDEV, whose PG semantics
    # are SAMPLE while MySQL's identically-named builtins are POPULATION —
    # passing the name through silently changes the math. T-SQL spells the
    # family VARP/VAR/STDEVP/STDEV (anything else gets dbo.-qualified as a
    # UDF and fails). Absent entries mean the canonical name is already the
    # engine's spelling.
    stat_map = _STAT_AGGREGATE_MAP.get(fn_name)
    if stat_map is not None and len(node.args) == 1:
        arg = _emit_expression(node.args[0], dialect)
        return f"{stat_map.get(dialect, fn_name)}({arg})"

    # Boolean aggregates: PG bool_or/bool_and/every canonicalize to
    # LOGICAL_OR/LOGICAL_AND (or stay verbatim) — no other engine has
    # them. MySQL booleans are 0/1, so MAX/MIN aggregate them directly;
    # T-SQL's bit is not a valid MAX operand and needs CAST(… AS INT);
    # Oracle SQL (23ai+) aggregates a CASE over the boolean.
    if fn_name in ("LOGICAL_OR", "BOOL_OR", "LOGICAL_AND", "BOOL_AND", "EVERY") and (
        len(node.args) == 1
    ):
        arg = _emit_expression(node.args[0], dialect)
        agg = "MAX" if fn_name in ("LOGICAL_OR", "BOOL_OR") else "MIN"
        if dialect == "tsql":
            inner = node.args[0]
            if isinstance(inner, BinaryOp) and inner.operator in _COMPARISON_OPS:
                # A predicate is not a value on T-SQL — wrap tri-state.
                arg = f"CASE WHEN {arg} THEN 1 WHEN NOT ({arg}) THEN 0 END"
            elif isinstance(inner, UnaryOp) and inner.operator == UnaryOperator.NOT:
                operand = _emit_expression(inner.operand, dialect)
                arg = (
                    f"CASE WHEN {operand} = 0 THEN 1 " f"WHEN {operand} <> 0 THEN 0 END"
                )
            return f"{agg}(CAST({arg} AS INT))"
        if dialect == "mysql":
            return f"{agg}({arg})"
        if dialect == "oracle":
            return f"{agg}(CASE WHEN {arg} THEN 1 ELSE 0 END)"
        return f"{'BOOL_OR' if agg == 'MAX' else 'BOOL_AND'}({arg})"

    # Conditional shorthand: MySQL IF() / T-SQL IIF(). Neither exists on
    # PostgreSQL/Oracle, whose spelling is a searched CASE.
    if fn_name in ("IF", "IIF") and len(node.args) == 3:
        # The first argument is condition position — MySQL truthiness
        # (a bare number/column) must become a comparison on T-SQL/Oracle.
        cond = _emit_condition(node.args[0], dialect)
        then_v, else_v = (_emit_expression(a, dialect) for a in node.args[1:])
        if dialect == "tsql":
            return f"IIF({cond}, {then_v}, {else_v})"
        if dialect == "mysql":
            return f"IF({cond}, {then_v}, {else_v})"
        return f"CASE WHEN {cond} THEN {then_v} ELSE {else_v} END"

    # EXTRACT(part FROM x): the standard spelling. sqlglot parses DATEPART/EXTRACT
    # to exp.Extract; the generic path would emit EXTRACT(part, x) (comma), which
    # Oracle/PostgreSQL/MySQL all reject. The FROM form is valid on all three;
    # T-SQL has no EXTRACT at all (error 195) — its spelling is DATEPART.
    if fn_name == "EXTRACT" and len(node.args) == 2:
        part = _emit_expression(node.args[0], dialect).strip("'\"").upper()
        value = _emit_expression(node.args[1], dialect)
        # Fields the target's native EXTRACT/DATEPART either rejects or computes
        # with different semantics, mapped to a value-preserving, NLS-/DATEFIRST-
        # /week-mode-independent equivalent. PostgreSQL semantics: DOW is
        # Sunday=0..Saturday=6, WEEK is the ISO 8601 week (1-53), QUARTER is 1-4.
        if part == "DOW":
            if dialect == "mysql":
                # DAYOFWEEK is 1(Sun)..7(Sat); shift to PG's 0..6.
                return f"(DAYOFWEEK({value}) - 1)"
            if dialect == "oracle":
                # 1970-01-04 was a Sunday; the outer MOD keeps it 0..6 for dates
                # before that reference too (Oracle MOD carries the sign).
                return f"MOD(MOD(TRUNC({value}) - DATE '1970-01-04', 7) + 7, 7)"
            if dialect == "tsql":
                # 1900-01-07 was a Sunday; DATEFIRST-independent (T-SQL % carries
                # the sign, so the +7/%7 wrap keeps pre-1900 dates 0..6).
                return f"(DATEDIFF(DAY, '19000107', {value}) % 7 + 7) % 7"
        if part == "WEEK":
            # PG's WEEK is ISO 8601. Oracle's EXTRACT rejects it; MySQL's native
            # EXTRACT(WEEK) follows default_week_format (mode 0, off by one) and
            # T-SQL's DATEPART(WEEK) is DATEFIRST-dependent — all wrong for ISO.
            if dialect == "oracle":
                return f"TO_NUMBER(TO_CHAR({value}, 'IW'))"
            if dialect == "mysql":
                return f"WEEK({value}, 3)"  # mode 3 = ISO 8601
            if dialect == "tsql":
                return f"DATEPART(ISO_WEEK, {value})"
        if part == "QUARTER" and dialect == "oracle":
            return f"TO_NUMBER(TO_CHAR({value}, 'Q'))"
        if part == "EPOCH":
            # Unix epoch seconds. PG's EPOCH for a timestamp WITHOUT time zone is
            # the literal difference from 1970-01-01 00:00:00 — no session-tz
            # conversion — so use a literal date-diff (not UNIX_TIMESTAMP, which
            # would shift by the session offset). EPOCH FROM an INTERVAL is a
            # different computation this does not model (it stays unhandled).
            if dialect == "oracle":
                return f"((CAST({value} AS DATE) - DATE '1970-01-01') * 86400)"
            if dialect == "tsql":
                return f"DATEDIFF_BIG(SECOND, '1970-01-01', {value})"
            if dialect == "mysql":
                return f"TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', {value})"
            return f"EXTRACT(EPOCH FROM {value})"
        if dialect == "tsql":
            return f"DATEPART({part}, {value})"
        return f"EXTRACT({part} FROM {value})"

    # OVERLAY(string PLACING sub FROM start [FOR len]): replace ``len`` chars of
    # ``string`` at 1-based ``start`` with ``sub`` (len defaults to sub's length).
    # sqlglot flattened it to a bare OVERLAY(...) call that only PG resolves (the
    # others errored — dbo.OVERLAY on T-SQL — with no warning). T-SQL STUFF and
    # MySQL INSERT() share the exact 1-based shape; Oracle rebuilds it with SUBSTR.
    if fn_name == "OVERLAY" and len(node.args) >= 3:
        ov_s = _emit_expression(node.args[0], dialect)
        ov_r = _emit_expression(node.args[1], dialect)
        ov_pos = _emit_expression(node.args[2], dialect)
        # ``FOR len`` is optional; when absent the replaced length defaults to the
        # length of ``r``. ``ov_len`` is "" (falsy) when absent, so ``ov_len or
        # <default>`` picks the engine's length-of-r expression.
        ov_len = _emit_expression(node.args[3], dialect) if len(node.args) >= 4 else ""
        if dialect == "postgresql":
            _for = f" FOR {ov_len}" if ov_len else ""
            return f"OVERLAY({ov_s} PLACING {ov_r} FROM {ov_pos}{_for})"
        if dialect == "tsql":
            return f"STUFF({ov_s}, {ov_pos}, {ov_len or f'LEN({ov_r})'}, {ov_r})"
        if dialect == "mysql":
            _l = ov_len or f"CHAR_LENGTH({ov_r})"
            return f"INSERT({ov_s}, {ov_pos}, {_l}, {ov_r})"
        return (
            f"SUBSTR({ov_s}, 1, ({ov_pos}) - 1) || {ov_r} || "
            f"SUBSTR({ov_s}, ({ov_pos}) + ({ov_len or f'LENGTH({ov_r})'}))"
        )

    # PG regexp_replace(src, pat, repl [, flags]): the 4th arg is a FLAGS string
    # (``g`` = global, ``i`` = case-insensitive); with no flags PG replaces only
    # the FIRST match. Oracle/MySQL take numeric position/occurrence instead and
    # are global by default, so PG's ``g`` was mis-passed as Oracle's position
    # (ORA-01722 on 'g'). Normalize: drop ``g``, map first-only to occurrence 1,
    # carry ``i`` as the match-param, and rewrite \N backrefs to $N for MySQL.
    if (
        fn_name == "REGEXP_REPLACE"
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect in ("oracle", "mysql")
        and len(node.args) >= 3
    ):
        rr_src = _emit_expression(node.args[0], dialect)
        rr_pat_node = node.args[1]
        rr_pat = _emit_expression(rr_pat_node, dialect)
        rr_repl_node = node.args[2]
        rr_flags = ""
        if (
            len(node.args) >= 4
            and isinstance(node.args[3], Literal)
            and isinstance(node.args[3].value, str)
        ):
            rr_flags = node.args[3].value
        rr_global = "g" in rr_flags
        rr_icase = "i" in rr_flags
        rr_repl = _emit_expression(rr_repl_node, dialect)
        if dialect == "mysql":
            # MySQL unescapes ``\`` inside a string literal before the regex
            # engine sees it (so ``'\d'`` becomes ``d``, matching a literal d) and
            # spells backrefs ``$N`` not ``\N``. Double the pattern's backslashes
            # and rewrite \N -> $N in the replacement.
            if isinstance(rr_pat_node, Literal) and isinstance(rr_pat_node.value, str):
                pv = rr_pat_node.value.replace("\\", "\\\\")
                rr_pat = "'" + pv.replace("'", "''") + "'"
            if isinstance(rr_repl_node, Literal) and isinstance(
                rr_repl_node.value, str
            ):
                conv = re.sub(r"\\(\d)", r"$\1", rr_repl_node.value)
                conv = conv.replace("\\", "\\\\")
                rr_repl = "'" + conv.replace("'", "''") + "'"
        if rr_icase:
            rr_tail = ", 1, 0, 'i'" if rr_global else ", 1, 1, 'i'"
        elif not rr_global:
            rr_tail = ", 1, 1"
        else:
            rr_tail = ""
        return f"REGEXP_REPLACE({rr_src}, {rr_pat}, {rr_repl}{rr_tail})"

    # PG format(template, args…) is printf-style (T-SQL/MySQL FORMAT is a totally
    # different value/number formatter; Oracle has none). A ``%s``-only template
    # (with ``%%`` for a literal percent) rewrites faithfully to concatenation —
    # the engines auto-stringify a numeric arg in ``||``/CONCAT. Any other spec
    # (%I, %L, width, positional %1$s) has no portable equivalent — degrade.
    if (
        fn_name == "FORMAT"
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect != "postgresql"
        and node.args
        and isinstance(node.args[0], Literal)
        and isinstance(node.args[0].value, str)
    ):
        tmpl = node.args[0].value
        specs = re.findall(r"%(.)", tmpl)
        if (
            not all(c in ("s", "%") for c in specs)
            or specs.count("s") != len(node.args) - 1
        ):
            return (
                "NULL /* UNIQUE: PG format() with %I/%L/width/positional "
                "specifiers has no cross-engine equivalent — "
                "see docs/03-unsupported.md */"
            )
        fmt_args = [_emit_expression(a, dialect) for a in node.args[1:]]
        pieces: list[str] = []
        for i, part in enumerate(re.split(r"%s", tmpl)):
            lit = part.replace("%%", "%")
            if lit:
                pieces.append("'" + lit.replace("'", "''") + "'")
            if i < len(fmt_args):
                pieces.append(fmt_args[i])
        if not pieces:
            return "''"
        if len(pieces) == 1:
            return pieces[0]
        if dialect == "oracle":
            return " || ".join(pieces)
        return f"CONCAT({', '.join(pieces)})"

    # XMLELEMENT(name, value...): SQL/XML built-in on Oracle and PostgreSQL.
    # Oracle spells the element name as a (usually quoted) identifier;
    # PostgreSQL requires the ``NAME`` keyword before it. MySQL and T-SQL have
    # no XMLELEMENT — the gate degrades those to a carrier (a documented limit).
    if fn_name == "XMLELEMENT" and node.args:
        # Quote the element name on both engines so neither re-folds its case
        # (Oracle upper-folds an unquoted identifier, PostgreSQL lower-folds it):
        # a PG ``NAME foo`` must stay ``<foo>`` on Oracle, not ``<FOO>``.
        bare = _emit_expression(node.args[0], dialect).strip('"')
        name = f'"{bare}"'
        vals = [_emit_expression(a, dialect) for a in node.args[1:]]
        if dialect == "postgresql":
            return f"XMLELEMENT({', '.join([f'NAME {name}', *vals])})"
        return f"XMLELEMENT({', '.join([name, *vals])})"

    # JSON_VALUE(doc, path) / JSON_QUERY(doc, path): SQL/JSON scalar and
    # object extraction. Oracle and T-SQL have both natively; MySQL has
    # JSON_VALUE (8.0.21+) but no JSON_QUERY (JSON_EXTRACT is the object form);
    # PostgreSQL <17 has neither, so route through the SQL/JSON path engine
    # (JSONB_PATH_QUERY_FIRST), extracting the scalar as text for JSON_VALUE.
    if fn_name in ("JSON_VALUE", "JSON_QUERY") and len(node.args) == 2:
        doc = _emit_expression(node.args[0], dialect)
        path = _emit_expression(node.args[1], dialect)
        if dialect == "postgresql":
            found = f"JSONB_PATH_QUERY_FIRST(CAST({doc} AS JSONB), {path})"
            return f"({found} #>> '{{}}')" if fn_name == "JSON_VALUE" else found
        if dialect == "mysql" and fn_name == "JSON_QUERY":
            return f"JSON_EXTRACT({doc}, {path})"
        return f"{fn_name}({doc}, {path})"

    # Oracle NVL2(a, b, c): b when a is not null, else c. Only Oracle has it.
    if fn_name == "NVL2" and len(node.args) == 3:
        a, b, c = (_emit_expression(x, dialect) for x in node.args)
        if dialect == "oracle":
            return f"NVL2({a}, {b}, {c})"
        return f"CASE WHEN {a} IS NOT NULL THEN {b} ELSE {c} END"

    # Oracle DECODE(expr, s1, r1[, s2, r2, ...][, default]): a searched CASE
    # everywhere else. sqlglot parses it as DecodeCase (IR name DECODE_CASE).
    if fn_name in ("DECODE", "DECODE_CASE") and len(node.args) >= 3:
        parts = [_emit_expression(x, dialect) for x in node.args]
        if dialect == "oracle":
            return f"DECODE({', '.join(parts)})"
        subject, whens, i = parts[0], [], 1
        while i + 1 < len(parts):
            # Oracle DECODE uses NULL-safe equality (NULL matches NULL), unlike
            # SQL '=' where NULL = NULL is unknown. A NULL search matches exactly
            # when the subject IS NULL.
            _dc_search = node.args[i]
            if isinstance(_dc_search, Literal) and _dc_search.value is None:
                cond = f"{subject} IS NULL"
            else:
                cond = f"{subject} = {parts[i]}"
            whens.append(f"WHEN {cond} THEN {parts[i + 1]}")
            i += 2
        default = f" ELSE {parts[i]}" if i < len(parts) else ""
        return f"CASE {' '.join(whens)}{default} END"

    # Niladic current-date spellings: PostgreSQL CURRENT_DATE, MySQL CURDATE().
    # Each engine names "today" differently (and CURRENT_DATE takes no parens).
    if fn_name in ("CURRENT_DATE", "CURDATE") and not node.args:
        return CURRENT_DATE_EXPR.get(dialect, "CURRENT_DATE")

    # Oracle's 1-arg TRUNC is type-dependent: over a declared DATE variable
    # it is midnight truncation (MySQL DATE()); otherwise numeric
    # truncation-toward-zero (MySQL TRUNCATE(x, 0)). The declaration
    # knowledge travels via DATE_VARIABLES (procedural context).
    if fn_name == "TRUNC" and len(node.args) == 1 and dialect == "mysql":
        arg_node = _unwrap_sqlglot_wrappers(node.args[0])
        arg_sql = _emit_expression(node.args[0], dialect)
        date_vars = DATE_VARIABLES.get() or frozenset()
        if (
            isinstance(arg_node, ColumnRef)
            and not arg_node.table
            and arg_node.name.lstrip("@").lower() in date_vars
        ):
            return f"DATE({arg_sql})"
        return f"TRUNCATE({arg_sql}, 0)"

    # Numeric TRUNC(x): only PostgreSQL/Oracle have TRUNC. A bare numeric literal
    # is truncation-toward-zero (a date TRUNC keeps its native form untouched).
    if (
        fn_name == "TRUNC"
        and len(node.args) == 1
        and isinstance(node.args[0], Literal)
        and str(node.args[0].dtype) in ("integer", "number")
    ):
        x = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"ROUND({x}, 0, 1)"  # 3rd arg truncates instead of rounding
        if dialect == "mysql":
            return f"TRUNCATE({x}, 0)"

    # Two-argument numeric TRUNC(x, d): the second argument being an integer
    # literal is decisive — Oracle's *date* TRUNC takes a format STRING there.
    if (
        fn_name == "TRUNC"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and str(node.args[1].dtype) in ("integer", "number")
    ):
        x = _emit_expression(node.args[0], dialect)
        d = _emit_expression(node.args[1], dialect)
        if dialect == "tsql":
            return f"ROUND({x}, {d}, 1)"
        if dialect == "mysql":
            return f"TRUNCATE({x}, {d})"
        # PostgreSQL TRUNC(numeric, int) has no double-precision overload, so a
        # double expression (PI(), a float column) errors; cast it to NUMERIC.
        # A numeric literal already resolves, so leave that clean.
        if dialect == "postgresql" and not (
            isinstance(node.args[0], Literal)
            and str(node.args[0].dtype) in ("integer", "number")
        ):
            return f"TRUNC(CAST({x} AS NUMERIC), {d})"
        return f"TRUNC({x}, {d})"

    # PostgreSQL ROUND(numeric, int) likewise has no double-precision overload:
    # ROUND(PI(), 4) / ROUND(<float column>, n) errors. Cast the value to NUMERIC
    # (a numeric literal already resolves, so leave that clean).
    if (
        fn_name == "ROUND"
        and len(node.args) == 2
        and dialect == "postgresql"
        and not (
            isinstance(node.args[0], Literal)
            and str(node.args[0].dtype) in ("integer", "number")
        )
    ):
        x = _emit_expression(node.args[0], dialect)
        d = _emit_expression(node.args[1], dialect)
        return f"ROUND(CAST({x} AS NUMERIC), {d})"

    # Oracle LOB initializers. T-SQL/PG/MySQL spell "empty" as an empty
    # binary/character literal.
    if fn_name in ("EMPTY_BLOB", "EMPTY_CLOB") and not node.args:
        if dialect == "oracle":
            return f"{fn_name}()"
        if fn_name == "EMPTY_BLOB":
            return {"tsql": "0x", "postgresql": "''::BYTEA", "mysql": "x''"}[dialect]
        return "''"

    # LPAD/RPAD: native on Oracle/PG/MySQL; T-SQL builds them from
    # REPLICATE (LEFT/RIGHT truncate to the target length, matching the
    # source semantics when the input is longer than the pad length).
    if fn_name in ("LPAD", "RPAD") and len(node.args) in (2, 3):
        s = _emit_expression(node.args[0], dialect)
        length = _emit_expression(node.args[1], dialect)
        pad = _emit_expression(node.args[2], dialect) if len(node.args) == 3 else "' '"
        if dialect == "tsql":
            if fn_name == "RPAD":
                return f"LEFT({s} + REPLICATE({pad}, {length}), {length})"
            # LPAD must take the pad's LEADING chars (a RIGHT() of the repeated
            # pad misaligns a multi-char pad, e.g. LPAD('ab',5,'xy')='xyxab' not
            # 'yxyab'); guard the truncation case (input longer than length).
            return (
                f"LEFT(REPLICATE({pad}, {length}), "
                f"CASE WHEN {length} > LEN({s}) THEN {length} - LEN({s}) "
                f"ELSE 0 END) + LEFT({s}, {length})"
            )
        return f"{fn_name}({s}, {length}, {pad})"

    # T-SQL CONVERT(type, value, style): the style is a date-format code
    # (sqlglot's tsql table) or the hash-stringify wrapper (style 1/2 around
    # a hash whose target functions already return hex) — M3 family F1.
    if (
        fn_name == "CONVERT"
        and len(node.args) == 3
        and isinstance(node.args[0], RawSQL)
        and isinstance(node.args[2], Literal)
    ):
        target_type = node.args[0].sql.strip()
        style = str(node.args[2].value).strip()
        value = _emit_expression(node.args[1], dialect)
        if dialect == "tsql":
            return f"CONVERT({target_type}, {value}, {style})"
        inner = _unwrap_sqlglot_wrappers(node.args[1])
        if (
            style in ("1", "2")
            and isinstance(inner, FunctionCall)
            and inner.name.upper() in ("SHA2", "SHA256", "SHA1", "SHA", "MD5")
        ):
            # SHA2/SHA256 return the hex string the wrapper asked for.
            return value
        from sqlglot.dialects.tsql import TSQL as _TSQL

        fmt = _TSQL.CONVERT_FORMAT_MAPPING.get(style)
        if fmt is not None:
            type_up = target_type.upper()
            to_string = bool(re.match(r"N?(?:VAR)?CHAR|N?TEXT", type_up))
            if dialect == "mysql":
                my = _convert_date_format(fmt, "python", "mysql")
                fn = "DATE_FORMAT" if to_string else "STR_TO_DATE"
                return f"{fn}({value}, '{my}')"
            ora = _convert_date_format(fmt, "python", "oracle")
            if to_string:
                return f"TO_CHAR({value}, '{ora}')"
            fn = (
                "TO_DATE"
                if type_up.startswith("DATE") and "TIME" not in type_up
                else "TO_TIMESTAMP"
            )
            return f"{fn}({value}, '{ora}')"
        # Unknown style off T-SQL: keep the call visible (a mapping gap).
        return f"CONVERT({target_type}, {value}, {style})"

    # T-SQL's SHA2(x, n) spells SHA256/SHA512 etc. on PostgreSQL and
    # RAWTOHEX(STANDARD_HASH(x, 'SHAn')) on Oracle (the text path's
    # live-validated forms; neither engine has a two-argument SHA2 —
    # PLS-00201 live in CI's Oracle validator).
    if (
        fn_name == "SHA2"
        and dialect in ("postgresql", "oracle")
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and str(node.args[1].value) in ("256", "384", "512")
    ):
        arg = _emit_expression(node.args[0], dialect)
        if dialect == "postgresql":
            return f"SHA{node.args[1].value}({arg})"
        return f"RAWTOHEX(STANDARD_HASH({arg}, 'SHA{node.args[1].value}'))"

    # T-SQL CONVERT(type, expr): sqlglot keeps the type as raw SQL in arg 0.
    # Everywhere else this is a plain CAST.
    if (
        fn_name == "CONVERT"
        and len(node.args) == 2
        and isinstance(node.args[0], RawSQL)
    ):
        target_type = node.args[0].sql.strip()
        value = _emit_expression(node.args[1], dialect)
        if dialect == "tsql":
            return f"CONVERT({target_type}, {value})"
        if dialect == "mysql":
            # MySQL CAST has no VARCHAR/INT spelling — use CHAR / SIGNED.
            target_type = re.sub(r"(?i)^VARCHAR\b", "CHAR", target_type)
            target_type = re.sub(
                r"(?i)^(?:INT|INTEGER|BIGINT)\b", "SIGNED", target_type
            )
        return f"CAST({value} AS {target_type})"

    # Date truncation (Oracle TRUNC(date[, fmt]) arrives canonicalized as
    # DATE_TRUNC): each engine spells it differently — audit D7: the Oracle
    # part 'DD' leaked into T-SQL's nonexistent DATE_TRUNC, and PostgreSQL
    # rejects 'DD' as a field too.
    if (
        fn_name == "DATE_TRUNC"
        and len(node.args) == 2
        and isinstance(node.args[0], (Literal, RawSQL))
    ):
        raw_part = (
            str(node.args[0].value)
            if isinstance(node.args[0], Literal)
            else node.args[0].sql.strip("'")
        )
        trunc_part = {
            "DD": "day",
            "DAY": "day",
            "DDD": "day",
            "MM": "month",
            "MON": "month",
            "MONTH": "month",
            "YYYY": "year",
            "YY": "year",
            "YEAR": "year",
            "HH": "hour",
            "HH24": "hour",
            "MI": "minute",
            "MINUTE": "minute",
            "Q": "quarter",
            "QUARTER": "quarter",
            "WW": "week",
            "WEEK": "week",
        }.get(raw_part.upper())
        if trunc_part is not None:
            value = _emit_expression(node.args[1], dialect)
            if dialect == "postgresql":
                return f"DATE_TRUNC('{trunc_part}', {value})"
            if dialect == "oracle":
                if trunc_part == "day":
                    return f"TRUNC({value})"
                return f"TRUNC({value}, '{raw_part}')"
            if dialect == "tsql":
                # CAST AS DATE works on every supported version; DATETRUNC
                # (2022+) covers the other parts.
                if trunc_part == "day":
                    return f"CAST({value} AS DATE)"
                return f"DATETRUNC({trunc_part}, {value})"
            if dialect == "mysql":
                if trunc_part == "day":
                    return f"DATE({value})"
                if trunc_part == "month":
                    return f"DATE_FORMAT({value}, '%Y-%m-01')"
                if trunc_part == "year":
                    return f"DATE_FORMAT({value}, '%Y-01-01')"

    # Date formatting/parsing. sqlglot canonicalizes TO_CHAR(date,fmt) to
    # TIME_TO_STR and TO_TIMESTAMP/TO_DATE(str,fmt) to STR_TO_TIME, with the
    # mask already in the python-strftime model. Translate the mask to each
    # engine's model and spell its date-format/parse function; a non-reproducible
    # mask (Oracle FF fractional, locale month/day names) falls through and
    # degrades via the gate. MySQL uses bare literal characters (strip the
    # ``"…"`` quotes the Oracle/.NET models use).
    if (
        fn_name == "TIME_TO_STR"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and isinstance(node.args[1].value, str)
        and _date_fmt_reproducible(node.args[1].value)
    ):
        # The value may be a bare ISO string (MySQL DATE_FORMAT('2020-05-17', …))
        # that a target's TO_CHAR/FORMAT rejects as a string — wrap it as a date.
        value = _as_datetime_literal(node.args[0], dialect) or _emit_expression(
            node.args[0], dialect
        )
        pyfmt = node.args[1].value
        if dialect in ("oracle", "postgresql"):
            # A lone full month/day NAME pads to 9 chars and uppercases on the
            # Oracle model ('JUNE     '); FM + init-capped name trims and
            # matches the source (MySQL MONTHNAME/DAYNAME give 'June'/'Monday').
            # Safe only for a single token — Oracle's FM *toggles* fill mode, so
            # a multi-field mask cannot use a per-field FM.
            lone_name = {"%B": "FMMonth", "%A": "FMDay"}.get(pyfmt.strip())
            if lone_name is not None:
                return f"TO_CHAR({value}, '{lone_name}')"
            return (
                f"TO_CHAR({value}, '{_convert_date_format(pyfmt, 'python', 'oracle')}')"
            )
        if dialect == "mysql":
            mf = _convert_date_format(pyfmt, "python", "mysql").replace('"', "")
            return f"DATE_FORMAT({value}, '{mf}')"
        if dialect == "tsql":
            return f"FORMAT({value}, '{_convert_date_format(pyfmt, 'python', 'tsql')}')"

    if fn_name == "STR_TO_TIME" and len(node.args) == 2:
        # A constant ISO-shaped string (also how sqlglot models a TIMESTAMP/DATE
        # literal argument) parses to a fixed value — emit the ANSI literal / cast
        # directly; the parse format is implied and its FF fractional is moot.
        as_lit = _as_datetime_literal(node, dialect)
        if as_lit is not None:
            return as_lit
        # Otherwise a real format-driven parse of a (possibly non-constant)
        # string — reproducible masks only; non-ISO/locale masks degrade.
        if (
            isinstance(node.args[1], Literal)
            and isinstance(node.args[1].value, str)
            and _date_fmt_reproducible(node.args[1].value)
        ):
            s = _emit_expression(node.args[0], dialect)
            pyfmt = node.args[1].value
            if dialect in ("oracle", "postgresql"):
                ofmt = _convert_date_format(pyfmt, "python", "oracle")
                return f"TO_TIMESTAMP({s}, '{ofmt}')"
            if dialect == "mysql":
                mf = _convert_date_format(pyfmt, "python", "mysql").replace('"', "")
                return f"STR_TO_DATE({s}, '{mf}')"

    # Oracle's one-argument TO_CHAR(x) — a plain to-string conversion — exists
    # nowhere else (PostgreSQL's TO_CHAR needs a format); spell it as a cast.
    if fn_name == "TO_CHAR" and len(node.args) == 1 and dialect != "oracle":
        value = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"CONVERT(VARCHAR(4000), {value})"
        if dialect == "mysql":
            return f"CAST({value} AS CHAR)"
        return f"CAST({value} AS TEXT)"

    # NUMBER_TO_STR: sqlglot's canonical for T-SQL/MySQL FORMAT(num, mask) of a
    # number. A reproducible grouping/decimal mask maps to each engine's numeric
    # formatter (Oracle/PG TO_CHAR with an FM mask — no leading pad space, so it
    # matches T-SQL/MySQL FORMAT). A non-reproducible mask (currency, hex, locale)
    # falls through and degrades.
    if (
        fn_name == "NUMBER_TO_STR"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
    ):
        spec = _number_mask_spec(node.args[1].value)
        if spec is not None:
            decimals, grouping = spec
            value = _emit_expression(node.args[0], dialect)
            if dialect in ("oracle", "postgresql"):
                return f"TO_CHAR({value}, '{_oracle_number_mask(decimals, grouping)}')"
            if dialect == "tsql":
                return f"FORMAT({value}, '{'N' if grouping else 'F'}{decimals}')"
            if dialect == "mysql" and grouping:
                # MySQL FORMAT always groups; a non-grouping mask has no builtin.
                return f"FORMAT({value}, {decimals})"

    # Date <-> string formatting. sqlglot keeps TO_CHAR's Oracle format model but
    # normalizes the DATE_FORMAT/STR_TO_DATE ones to strftime; translate per
    # target (PostgreSQL shares Oracle's model; T-SQL uses FORMAT/.NET).
    if (
        fn_name == "TO_CHAR"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
    ):
        value = _emit_expression(node.args[0], dialect)
        fmt = str(node.args[1].value)
        is_date_mask = bool(
            re.search(r"(?i)YY|MM|DD|HH|MI|SS|MON|DAY|DY|RM|IW|WW|\bQ\b", fmt)
        )
        if dialect in ("oracle", "postgresql"):
            # Oracle and PostgreSQL share the TO_CHAR number/date model — identity.
            return f"TO_CHAR({value}, '{fmt}')"
        if is_date_mask:
            if dialect == "mysql":
                mf = _convert_date_format(fmt, "oracle", "mysql")
                return f"DATE_FORMAT({value}, '{mf}')"
            return f"FORMAT({value}, '{_convert_date_format(fmt, 'oracle', 'tsql')}')"
        if dialect == "tsql" and re.fullmatch(r"\d+", fmt):
            # A bare number is T-SQL client code: TO_CHAR(x, 112) = CONVERT style.
            return f"CONVERT(VARCHAR(4000), {value}, {fmt})"
        # A numeric mask (grouping, currency, hex, sign): MySQL/T-SQL cannot
        # reproduce Oracle's number formatting (leading pad space, ``L``/``X``/
        # ``PR``) — fall through and degrade honestly rather than ship a wrong
        # value.

    # (TIME_TO_STR — sqlglot's date->string canonical — is handled above with a
    # value-wrap + reproducible-mask guard; a non-reproducible mask degrades.)

    # STR_TO_DATE: sqlglot's canonical for a string->date parse; its format is
    # likewise Python strftime.
    if (
        fn_name == "STR_TO_DATE"
        and len(node.args) == 2
        and isinstance(node.args[1], Literal)
        and isinstance(node.args[1].value, str)
    ):
        # A constant ISO-shaped string parses to a fixed value — the ANSI literal.
        as_lit = _as_datetime_literal(node, dialect)
        if as_lit is not None:
            return as_lit
        # Otherwise only a reproducible mask round-trips; a non-reproducible one
        # falls through (no return) to degrade honestly via the gate.
        if _date_fmt_reproducible(node.args[1].value):
            value = _emit_expression(node.args[0], dialect)
            fmt = str(node.args[1].value)  # python strftime
            if dialect == "mysql":
                my = _convert_date_format(fmt, "python", "mysql")
                return f"STR_TO_DATE({value}, '{my}')"
            if dialect in ("oracle", "postgresql"):
                ofmt = _convert_date_format(fmt, "python", "oracle")
                return f"TO_DATE({value}, '{ofmt}')"
            # T-SQL: the common unambiguous formats map to a fixed CONVERT
            # style (the shared table); anything else stays visible for review
            # — a blanket CAST dropped the format AND the time part.
            ora_fmt = _convert_date_format(fmt, "python", "oracle").upper()
            known_style = ORACLE_DATE_FORMAT_STYLES.get(
                re.sub(r"\s*HH24:MI:SS$", "", ora_fmt)
            )
            if known_style is not None:
                return f"CONVERT(DATETIME, {value}, {known_style})"
            return f"TO_DATE({value}, '{ora_fmt}')"

    # A user function may be schema-qualified (dbo.fn_tax). The "dbo" default
    # schema is meaningless on the other engines, so drop it there, as for any
    # other object reference. Built-in names never carry it.
    if dialect in ("oracle", "mysql", "postgresql") and "." in node.name:
        node = _strip_dbo_function_name(node)
    # Special handling for CURRENT_TIMESTAMP (no parens in some dialects)
    if node.name.upper() == "CURRENT_TIMESTAMP" and not node.args:
        return CURRENT_TIMESTAMP_EXPR.get(dialect, "CURRENT_TIMESTAMP")

    # Oracle niladic "now" spellings that sqlglot passes through as anonymous
    # calls. SYSTIMESTAMP has no cross-engine parens form (it would leak as an
    # invalid SYSTIMESTAMP() — invalid even on Oracle); SYSDATE is included for
    # the same passthrough case. Map to each dialect's current-timestamp form.
    if node.name.upper() in ("SYSTIMESTAMP", "SYSDATE", "NOW") and not node.args:
        return CURRENT_TIMESTAMP_EXPR.get(dialect, "CURRENT_TIMESTAMP")

    # LOCALTIMESTAMP (current local timestamp, no time zone): Oracle/PostgreSQL
    # spell it as a niladic KEYWORD — a parenthesized LOCALTIMESTAMP() is invalid
    # on PG; T-SQL has no such keyword and uses SYSDATETIME(); MySQL's is a NOW()
    # synonym.
    if node.name.upper() == "LOCALTIMESTAMP" and not node.args:
        return {
            "oracle": "LOCALTIMESTAMP",
            "postgresql": "LOCALTIMESTAMP",
            "tsql": "SYSDATETIME()",
            "mysql": "CURRENT_TIMESTAMP",
        }.get(dialect, "CURRENT_TIMESTAMP")

    # CURRENT_USER/SESSION_USER are niladic KEYWORDS on PG/T-SQL (the
    # parenthesized call is invalid there); Oracle spells it USER.
    if node.name.upper() in ("CURRENT_USER", "SESSION_USER") and not node.args:
        if dialect in ("postgresql", "tsql"):
            return node.name.upper()
        if dialect == "oracle":
            return "USER"
        return f"{node.name.upper()}()"

    # Substring position: canonical CHARINDEX(needle, haystack[, start]) maps to
    # each engine's function with its own argument order.
    if node.name.upper() == "CHARINDEX" and len(node.args) >= 2:
        needle = _emit_expression(node.args[0], dialect)
        haystack = _emit_expression(node.args[1], dialect)
        # MySQL's default collation is case-insensitive, so LOCATE/INSTR match
        # regardless of case (INSTR('aAaA', 'A') = 1); Oracle and PostgreSQL
        # compare case-sensitively. Fold both operands to lower case there to
        # preserve MySQL's result (T-SQL's default collation is already
        # case-insensitive, so it needs no change).
        if SOURCE_DIALECT.get() == "mysql" and dialect in ("oracle", "postgresql"):
            needle = f"LOWER({needle})"
            haystack = f"LOWER({haystack})"
        # The reverse: Oracle/PostgreSQL search case-sensitively, but MySQL's and
        # T-SQL's default collations are case-insensitive (INSTR('aAaA','A') = 1
        # not 2). When the haystack is a *string literal* — where the intended
        # comparison is unambiguous — force a binary / case-sensitive collation so
        # the match position matches the source. A column keeps its own collation
        # (forcing one there is the broader, unsupported collation question).
        elif (
            SOURCE_DIALECT.get() in ("oracle", "postgresql")
            and dialect in ("mysql", "tsql")
            and isinstance(node.args[1], Literal)
            and isinstance(node.args[1].value, str)
        ):
            haystack = (
                f"BINARY {haystack}"
                if dialect == "mysql"
                else f"{haystack} COLLATE Latin1_General_BIN2"
            )
        start = _emit_expression(node.args[2], dialect) if len(node.args) > 2 else None
        # MySQL LOCATE/INSTR and PostgreSQL POSITION/STRPOS with an empty needle
        # return 1; Oracle INSTR returns NULL (empty string -> NULL) and T-SQL
        # CHARINDEX returns 0. Recover the 1 when the needle could be empty (skip
        # a provably non-empty literal).
        _n0 = node.args[0]
        _needle_maybe_empty = (
            SOURCE_DIALECT.get() in ("mysql", "postgresql")
            and start is None
            and not (
                isinstance(_n0, Literal)
                and isinstance(_n0.value, str)
                and _n0.value != ""
            )
        )
        if dialect == "tsql":
            args_sql = f"{needle}, {haystack}" + (f", {start}" if start else "")
            base = f"CHARINDEX({args_sql})"
            if _needle_maybe_empty:
                return f"CASE WHEN {needle} = '' THEN 1 ELSE {base} END"
            return base
        if dialect == "mysql":
            # LOCATE(needle, haystack[, start])
            args_sql = f"{needle}, {haystack}" + (f", {start}" if start else "")
            return f"LOCATE({args_sql})"
        if dialect == "oracle":
            # INSTR(haystack, needle[, start])
            args_sql = f"{haystack}, {needle}" + (f", {start}" if start else "")
            base = f"INSTR({args_sql})"
            if _needle_maybe_empty:
                return f"COALESCE({base}, 1)"
            return base
        # postgresql: STRPOS has no start arg; use POSITION(needle IN haystack)
        # and add the offset when a start position is given — guarded so a
        # not-found still returns 0 (the bare +offset form returned
        # start - 1, a semantic drift from CHARINDEX).
        if start:
            pos = f"POSITION({needle} IN SUBSTRING({haystack} FROM {start}))"
            return f"CASE WHEN {pos} = 0 THEN 0 ELSE {pos} + {start} - 1 END"
        return f"POSITION({needle} IN {haystack})"

    # The source's last-identity function is a GLOBAL, not a UDF — it maps
    # to the target's whole expression (LAST_IDENTITY_EXPR); guarded on the
    # name belonging to the SOURCE dialect so a same-named user function on
    # another engine stays a visible call.
    if (
        not node.args
        and fn_name in LAST_IDENTITY_SOURCE_FUNCS
        and LAST_IDENTITY_SOURCE_FUNCS[fn_name] == SOURCE_DIALECT.get()
        and dialect in LAST_IDENTITY_EXPR
    ):
        return LAST_IDENTITY_EXPR[dialect]

    # The current-error-message global (exception context): T-SQL's
    # ERROR_MESSAGE() ↔ SQLERRM. MySQL has no expression form (absent from
    # the table) — the name stays a visible gap there.
    if (
        not node.args
        and SOURCE_DIALECT.get() in ERROR_MESSAGE_SOURCES.get(fn_name, frozenset())
        and dialect in ERROR_MESSAGE_EXPR
    ):
        return ERROR_MESSAGE_EXPR[dialect]

    # Oracle's bare TO_NUMBER(x) (no format) is a decimal cast off Oracle —
    # a name rename would emit CONVERT/CAST without a type (error 156); the
    # text path's live-validated form is CAST(x AS DECIMAL(38, 10)).
    if (
        fn_name == "TO_NUMBER"
        and len(node.args) == 1
        and dialect in ("tsql", "mysql", "postgresql")
    ):
        arg = _emit_expression(node.args[0], dialect)
        # T-SQL can't CAST a scientific-notation string ('1.234E2') to DECIMAL
        # (error 8114); FLOAT parses the exponent. Oracle TO_NUMBER accepts it,
        # so keep the value via FLOAT for such a literal.
        _a0 = node.args[0]
        if (
            dialect == "tsql"
            and isinstance(_a0, Literal)
            and isinstance(_a0.value, str)
            and re.fullmatch(r"\s*[-+]?\d*\.?\d+[eE][-+]?\d+\s*", _a0.value) is not None
        ):
            return f"CAST({arg} AS FLOAT)"
        target_num = "DECIMAL(38, 10)" if dialect != "postgresql" else "NUMERIC"
        return f"CAST({arg} AS {target_num})"

    # Oracle LOB helpers on T-SQL (the text path's live-validated forms):
    # DBMS_LOB.SUBSTR(x, len, start) is SUBSTRING(x, start, len);
    # UTL_RAW.CAST_TO_VARCHAR2 a VARCHAR(MAX) CONVERT; GETLENGTH DATALENGTH.
    if dialect == "tsql" and SOURCE_DIALECT.get() == "oracle":
        if fn_name in ("DBMS_LOB.SUBSTR", "DBMS_LOB.SUBSTRING") and len(node.args) in (
            2,
            3,
        ):
            lob = _emit_expression(node.args[0], dialect)
            length = _emit_expression(node.args[1], dialect)
            start = (
                _emit_expression(node.args[2], dialect) if len(node.args) == 3 else "1"
            )
            return f"SUBSTRING({lob}, {start}, {length})"
        if fn_name == "UTL_RAW.CAST_TO_VARCHAR2" and len(node.args) == 1:
            return f"CONVERT(VARCHAR(MAX), {_emit_expression(node.args[0], dialect)})"
        if fn_name == "DBMS_LOB.GETLENGTH" and len(node.args) == 1:
            return f"DATALENGTH({_emit_expression(node.args[0], dialect)})"

    # Functions with no name on the target but a faithful rewrite (RC-1a).
    up = node.name.upper()
    if dialect == "oracle" and up == "LEFT" and len(node.args) == 2:
        # Oracle has no LEFT; SUBSTR(s, 1, n) is exact (n>len returns the whole
        # string, n=0 returns '' which Oracle treats as NULL either way).
        s = _emit_expression(node.args[0], dialect)
        n = _emit_expression(node.args[1], dialect)
        return f"SUBSTR({s}, 1, {n})"
    if up == "INITCAP" and node.args and dialect in ("oracle", "postgresql"):
        # Oracle and PG INITCAP take a single argument; sqlglot appends a
        # default word-delimiter set (Snowflake's 2-arg form) that neither
        # accepts — emit just the string.
        return f"INITCAP({_emit_expression(node.args[0], dialect)})"
    if up == "TIMESTAMP_FROM_PARTS" and len(node.args) == 7 and dialect != "tsql":
        # T-SQL DATETIMEFROMPARTS(y, mo, d, h, mi, s, ms) → a constructed
        # timestamp. The ms rides as an arithmetic interval (no fractional-second
        # format string to zero-pad). sqlglot canonicalises the name.
        p = [_emit_expression(x, dialect) for x in node.args]
        if dialect == "postgresql":
            return (
                f"make_timestamp({p[0]}, {p[1]}, {p[2]}, {p[3]}, {p[4]}, "
                f"{p[5]} + {p[6]} / 1000.0)"
            )
        if dialect == "oracle":
            base = (
                f"{p[0]} || '-' || {p[1]} || '-' || {p[2]} || ' ' || "
                f"{p[3]} || ':' || {p[4]} || ':' || {p[5]}"
            )
            return (
                f"(TO_TIMESTAMP({base}, 'YYYY-MM-DD HH24:MI:SS') "
                f"+ NUMTODSINTERVAL({p[6]} / 1000, 'SECOND'))"
            )
        base = (
            f"CONCAT({p[0]}, '-', {p[1]}, '-', {p[2]}, ' ', "
            f"{p[3]}, ':', {p[4]}, ':', {p[5]})"
        )  # mysql
        return f"(TIMESTAMP({base}) + INTERVAL ({p[6]}) * 1000 MICROSECOND)"
    if (
        up == "NEXT_VALUE_FOR"
        and len(node.args) == 1
        and dialect
        in (
            "oracle",
            "postgresql",
        )
    ):
        # T-SQL ``NEXT VALUE FOR seq``: Oracle spells it ``seq.NEXTVAL``, PG
        # ``nextval('seq')`` (regclass string). MySQL has no sequences, so it
        # falls through to the gate's honest degrade.
        seq = _emit_expression(node.args[0], dialect)
        if dialect == "oracle":
            return f"{seq}.NEXTVAL"
        bare = node.args[0].name if isinstance(node.args[0], ColumnRef) else seq
        return f"nextval('{bare}')"
    if (
        up == "CHR"
        and len(node.args) == 1
        and SOURCE_DIALECT.get() == "mysql"
        and dialect in ("oracle", "postgresql")
        and isinstance(node.args[0], Literal)
        and isinstance(node.args[0].value, int)
        and node.args[0].value > 255
    ):
        # MySQL CHAR(n) is byte-based: n > 255 yields a multi-byte byte string
        # (CHAR(256) = 0x0100), not the single code point CHR gives elsewhere.
        _n = node.args[0].value
        return (
            f"CHR({_n}) /* UNIQUE: MySQL CHAR({_n}) is a multi-byte byte string, "
            "not a single code point (docs/03-unsupported.md) */"
        )
    if up == "CHR" and len(node.args) == 1 and dialect in ("mysql", "tsql"):
        # PG/Oracle CHR(n) is a Unicode code point; above ASCII (n > 127) MySQL's
        # byte CHAR(n USING latin1) gives the wrong bytes and T-SQL's CHAR(n)
        # returns NULL (0-255 only). Build the Unicode character instead — MySQL
        # in a Unicode set, T-SQL via NCHAR.
        _cn = node.args[0]
        if isinstance(_cn, Literal) and isinstance(_cn.value, int) and _cn.value > 127:
            return (
                f"CHAR({_cn.value} USING utf16)"
                if dialect == "mysql"
                else f"NCHAR({_cn.value})"
            )
    if up == "CHR" and len(node.args) == 1 and dialect == "mysql":
        # MySQL has no CHR (Oracle/PG spelling). Bare CHAR(n) returns a BINARY
        # string; a charset makes it a character string — latin1 matches T-SQL
        # CHAR's code-page byte semantics. (sqlglot canonicalises CHAR to Chr.)
        return f"CHAR({_emit_expression(node.args[0], dialect)} USING latin1)"
    if up == "NCHAR" and len(node.args) == 1 and dialect != "tsql":
        # T-SQL NCHAR(n) is the Unicode code point → character function (not the
        # NCHAR type here — that arrives as a DataType). Oracle spells it NCHR;
        # PG's CHR takes a code point; MySQL builds the char in a Unicode set.
        n = _emit_expression(node.args[0], dialect)
        if dialect == "oracle":
            return f"NCHR({n})"
        if dialect == "postgresql":
            return f"CHR({n})"
        return f"CHAR({n} USING utf16)"  # mysql
    if up == "SPACE" and len(node.args) == 1 and dialect in ("oracle", "postgresql"):
        # Neither engine has SPACE(n); n spaces is RPAD(' ', n) / REPEAT(' ', n).
        n = _emit_expression(node.args[0], dialect)
        return f"RPAD(' ', {n})" if dialect == "oracle" else f"REPEAT(' ', {n})"
    if dialect == "oracle" and up == "COT" and len(node.args) == 1:
        # Oracle has no COT; cot(x) = 1 / tan(x).
        return f"(1 / TAN({_emit_expression(node.args[0], dialect)}))"
    if dialect == "oracle" and up == "PI" and not node.args:
        return "ACOS(-1)"  # Oracle has no PI(); ACOS(-1) is exactly pi.
    if dialect == "tsql" and up == "LN" and len(node.args) == 1:
        # T-SQL has no LN; its 1-arg LOG(x) is the natural logarithm.
        return f"LOG({_emit_expression(node.args[0], dialect)})"
    if dialect == "tsql" and up == "ATAN2" and len(node.args) == 2:
        a = _emit_expression(node.args[0], dialect)
        b = _emit_expression(node.args[1], dialect)
        return f"ATN2({a}, {b})"  # T-SQL spells atan2 as ATN2, same arg order.
    # Date built-ins with no target name but a faithful rewrite (RC-1a).
    # ADD_MONTHS carries Oracle's sticky last-day rule (ADD_MONTHS('2020-02-29',1)
    # = '2020-03-31'): if d is its month's last day, the result is the result
    # month's last day; otherwise plain interval arithmetic (which already clamps
    # a too-large day down). Each target has a last-day primitive to express it.
    if up == "ADD_MONTHS" and len(node.args) == 2 and dialect != "oracle":
        d = _emit_expression(node.args[0], dialect)
        n = _emit_expression(node.args[1], dialect)
        if dialect == "mysql":
            add = f"DATE_ADD({d}, INTERVAL {n} MONTH)"
            return f"CASE WHEN {d} = LAST_DAY({d}) THEN LAST_DAY({add}) ELSE {add} END"
        if dialect == "tsql":
            add = f"DATEADD(MONTH, {n}, {d})"
            return f"CASE WHEN {d} = EOMONTH({d}) THEN EOMONTH({add}) ELSE {add} END"
        # PG DATE_TRUNC has no unique overload for an untyped string literal
        # ("date_trunc(unknown, unknown) is not unique") — type the ISO literal
        # as an ANSI DATE (a column/expression is left untouched).
        d = wrap_oracle_date_arg(d)
        add = f"({d} + {n} * INTERVAL '1 month')"  # postgresql
        eom = "+ INTERVAL '1 month' - INTERVAL '1 day' AS DATE)"
        ld_d = f"CAST(DATE_TRUNC('month', {d}) {eom}"
        ld_add = f"CAST(DATE_TRUNC('month', {add}) {eom}"
        return f"CASE WHEN {d} = {ld_d} THEN {ld_add} ELSE CAST({add} AS DATE) END"
    if up == "LAST_DAY" and len(node.args) == 1 and dialect != "mysql":
        d = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"EOMONTH({d})"
        # PG/Oracle can't implicitly convert an ISO string to a date here
        # (ORA-01861 / PG unknown type); the ANSI ``DATE '…'`` literal is valid
        # on both. Oracle has LAST_DAY natively; PG builds the month end.
        d = wrap_oracle_date_arg(d)
        if dialect == "oracle":
            return f"LAST_DAY({d})"
        return (
            f"CAST(DATE_TRUNC('month', {d}) + INTERVAL '1 month' "
            f"- INTERVAL '1 day' AS DATE)"
        )
    if up == "QUARTER" and len(node.args) == 1 and dialect != "mysql":
        d = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"DATEPART(QUARTER, {d})"
        if dialect == "oracle":
            return f"TO_NUMBER(TO_CHAR({d}, 'Q'))"
        return f"EXTRACT(QUARTER FROM {d})"  # postgresql
    if up == "DAYNAME" and len(node.args) == 1 and dialect != "mysql":
        d = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"DATENAME(WEEKDAY, {d})"
        # A bare ISO-string arg needs an ANSI ``DATE '…'`` literal or Oracle/PG
        # reject it (ORA-01722 / PG unknown type), exactly like LAST_DAY above.
        # Oracle/PG pad the day name to 9 chars; fm/FM trims it to match MySQL.
        d = wrap_oracle_date_arg(d)
        return (
            f"TO_CHAR({d}, 'fmDay')"
            if dialect == "oracle"
            else f"TO_CHAR({d}, 'FMDay')"
        )
    # T-SQL RADIANS/DEGREES return the argument's type: an integer argument
    # truncates the result (RADIANS(180) = 3, not 3.14159). Cast to FLOAT so the
    # value is preserved, matching MySQL/PostgreSQL/Oracle.
    if (
        dialect == "tsql"
        and up in ("RADIANS", "DEGREES")
        and len(node.args) == 1
        and _is_integer_operand(node.args[0])
    ):
        return f"{up}(CAST({_emit_expression(node.args[0], dialect)} AS FLOAT))"
    # Math built-ins Oracle lacks (RC-1a).
    if dialect == "oracle" and up == "DEGREES" and len(node.args) == 1:
        return f"({_emit_expression(node.args[0], dialect)} * 180 / ACOS(-1))"
    if dialect == "oracle" and up == "RADIANS" and len(node.args) == 1:
        return f"({_emit_expression(node.args[0], dialect)} * ACOS(-1) / 180)"
    if dialect == "oracle" and up == "RAND" and not node.args:
        return "DBMS_RANDOM.VALUE"  # both yield a uniform value in [0, 1).
    if dialect == "oracle" and up == "REPEAT" and len(node.args) == 2:
        s = _emit_expression(node.args[0], dialect)
        n = _emit_expression(node.args[1], dialect)
        return f"RPAD({s}, LENGTH({s}) * {n}, {s})"  # exact, incl. n=0 -> '' (NULL).
    # MySQL INSERT() returns the original string when the position is 0 or past
    # the string's end; T-SQL STUFF returns NULL there. Guard the bounds so the
    # MySQL value is preserved (the in-bounds case is identical).
    if (
        up == "STUFF"
        and len(node.args) == 4
        and dialect == "tsql"
        and SOURCE_DIALECT.get() == "mysql"
    ):
        _st_s, _st_pos, _st_len, _st_new = (
            _emit_expression(a, dialect) for a in node.args
        )
        _stuff = f"STUFF({_st_s}, {_st_pos}, {_st_len}, {_st_new})"
        return (
            f"CASE WHEN {_st_pos} < 1 OR {_st_pos} > LEN({_st_s}) "
            f"THEN {_st_s} ELSE {_stuff} END"
        )
    # STUFF(s, start, len, new): delete `len` chars at `start`, insert `new`.
    # PG has OVERLAY, MySQL has INSERT(); Oracle has neither, so SUBSTR-concat.
    # T-SQL keeps STUFF natively.
    if up == "STUFF" and len(node.args) == 4 and dialect != "tsql":
        s, start, length, new = (_emit_expression(a, dialect) for a in node.args)
        if dialect == "mysql":
            return f"INSERT({s}, {start}, {length}, {new})"
        if dialect == "postgresql":
            return f"OVERLAY({s} PLACING {new} FROM {start} FOR {length})"
        return (
            f"(SUBSTR({s}, 1, {start} - 1) || {new} || SUBSTR({s}, {start} + {length}))"
        )
    if dialect == "postgresql" and up == "MEDIAN" and len(node.args) == 1:
        x = _emit_expression(node.args[0], dialect)
        return f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {x})"
    # JSON aggregates map faithfully across PostgreSQL, MySQL and Oracle (same
    # JSON value); T-SQL has no JSON aggregate, so its emission degrades through
    # the gate (output_gate._CROSS_ENGINE_AGG).
    if up == "JSON_ARRAYAGG" and len(node.args) == 1:
        x = _emit_expression(node.args[0], dialect)
        if dialect == "postgresql":
            return f"JSON_AGG({x})"  # PG spells the array aggregate json_agg
        return f"JSON_ARRAYAGG({x})"  # MySQL/Oracle native; T-SQL degrades
    if up == "JSON_OBJECTAGG" and len(node.args) == 2:
        key_node, val_node = node.args
        v = _emit_expression(val_node, dialect)
        if dialect == "postgresql":
            return f"JSON_OBJECT_AGG({_emit_expression(key_node, dialect)}, {v})"
        if dialect == "oracle":
            # Oracle's KEY..VALUE syntax; the key must be VARCHAR2 (a NUMBER key
            # raises ORA-00932, and a text key mapped to CLOB — e.g. PG's
            # ``x::text`` — raises ORA-22849 even wrapped). Cast the *inner*
            # value straight to VARCHAR2, past any text→CLOB cast.
            inner = (
                key_node.expression
                if isinstance(key_node, CastExpression)
                else key_node
            )
            k = f"CAST({_emit_expression(inner, dialect)} AS VARCHAR2(4000))"
            return f"JSON_OBJECTAGG({k} VALUE {v})"
        return f"JSON_OBJECTAGG({_emit_expression(key_node, dialect)}, {v})"

    # JSON_OBJECT / JSON_ARRAY constructors — a built-in on all four engines but
    # spelled differently. A boolean stays a JSON boolean (PG/Oracle/MySQL keep
    # TRUE; T-SQL renders a BIT as JSON true/false), and NULL is preserved
    # (Oracle/T-SQL default to ABSENT ON NULL — force NULL ON NULL).
    def _json_arg(a: ASTNode) -> str:
        if isinstance(a, Literal) and a.dtype == "boolean":
            if dialect == "tsql":
                return f"CAST({1 if a.value else 0} AS BIT)"
            return "TRUE" if a.value else "FALSE"
        return _emit_expression(a, dialect)

    if up == "JSON_OBJECT" and len(node.args) >= 2 and len(node.args) % 2 == 0:
        vals = [_json_arg(a) for a in node.args]
        pairs = list(zip(vals[0::2], vals[1::2], strict=True))
        if dialect == "postgresql":
            return f"JSON_BUILD_OBJECT({', '.join(vals)})"
        if dialect == "oracle":
            body = ", ".join(f"{k} VALUE {v}" for k, v in pairs)
            return f"JSON_OBJECT({body} NULL ON NULL)"
        if dialect == "tsql":
            body = ", ".join(f"{k}:{v}" for k, v in pairs)
            return f"JSON_OBJECT({body} NULL ON NULL)"
        return f"JSON_OBJECT({', '.join(vals)})"  # MySQL native comma pairs

    if up == "JSON_ARRAY" and node.args:
        arr = ", ".join(_json_arg(a) for a in node.args)
        if dialect == "postgresql":
            return f"JSON_BUILD_ARRAY({arr})"
        if dialect in ("oracle", "tsql"):
            return f"JSON_ARRAY({arr} NULL ON NULL)"
        return f"JSON_ARRAY({arr})"  # MySQL native (keeps NULLs by default)

    # T-SQL DATALENGTH(x): the byte length. Oracle spells it LENGTHB, PG/MySQL
    # OCTET_LENGTH. A VARBINARY cast argument is a no-op for the byte count of a
    # string (its byte length is the same), so unwrap it — the other engines have
    # no direct VARBINARY(MAX) equivalent.
    if up == "DATALENGTH" and len(node.args) == 1 and dialect != "tsql":
        dl_arg = node.args[0]
        if isinstance(dl_arg, CastExpression) and dl_arg.target_type.name.upper() in (
            "VARBINARY",
            "BINARY",
            "BLOB",
            "BYTEA",
            "RAW",
        ):
            dl_arg = dl_arg.expression
        x = _emit_expression(dl_arg, dialect)
        return f"LENGTHB({x})" if dialect == "oracle" else f"OCTET_LENGTH({x})"

    # MySQL ELT(n, a, b, …)/FIELD(v, a, b, …) → portable CASE chains (RC-1a).
    if up == "ELT" and len(node.args) >= 2 and dialect != "mysql":
        n = _emit_expression(node.args[0], dialect)
        arms = " ".join(
            f"WHEN {i} THEN {_emit_expression(a, dialect)}"
            for i, a in enumerate(node.args[1:], start=1)
        )
        return f"CASE {n} {arms} END"
    if up == "FIELD" and len(node.args) >= 2 and dialect != "mysql":
        v = _emit_expression(node.args[0], dialect)
        arms = " ".join(
            f"WHEN {_emit_expression(a, dialect)} THEN {i}"
            for i, a in enumerate(node.args[1:], start=1)
        )
        return f"CASE {v} {arms} ELSE 0 END"

    # Map canonical function names to dialect-specific names
    name = _map_function_name(node.name, dialect)

    # T-SQL rejects an unqualified scalar-UDF call as an unknown built-in
    # (error 195) — even when the function exists in the database. A name
    # that is neither a T-SQL builtin nor a known foreign builtin (an
    # unmapped one must stay a visible gap) is a user function: qualify it.
    if dialect == "tsql" and tsql_call_needs_schema(name):
        name = f"dbo.{name}"

    distinct = "DISTINCT " if node.distinct else ""
    arg_nodes = node.args
    # A 1-arg LOG in the IR is always base-10: only PostgreSQL spells log-base-10
    # as LOG(x) — MySQL/T-SQL LOG(x) is the natural log and parses to LN, and
    # Oracle's LOG needs two args. Emitting a bare LOG(x) would silently be read
    # as the natural log on MySQL/T-SQL, so name the base-10 form explicitly.
    if name.upper() == "LOG" and len(arg_nodes) == 1:
        x = _emit_expression(arg_nodes[0], dialect)
        if dialect == "oracle":
            return f"LOG(10, {x})"
        if dialect in ("mysql", "tsql"):
            return f"LOG10({x})"
        return f"LOG({x})"  # PostgreSQL: native base-10
    # T-SQL computes LOG(x, 10) with a floating-point error (LOG(1000, 10) yields
    # 2.9999999999999996); its native LOG10 is exact, so prefer it for base 10.
    if (
        dialect == "tsql"
        and name.upper() == "LOG"
        and len(arg_nodes) == 2
        and isinstance(arg_nodes[0], Literal)
        and str(arg_nodes[0].value) in ("10", "10.0")
    ):
        return f"LOG10({_emit_expression(arg_nodes[1], dialect)})"
    # The IR is canonical ``LOG(base, x)`` (every source is normalised to it, T-SQL
    # included); T-SQL spells it ``LOG(x, base)``, so swap on the way out or it
    # silently computes a different logarithm (RC-2).
    if dialect == "tsql" and name.upper() == "LOG" and len(arg_nodes) == 2:
        arg_nodes = (arg_nodes[1], arg_nodes[0])
    args = ", ".join(_emit_expression(a, dialect) for a in arg_nodes)
    # T-SQL's ROUND requires the scale argument (error 189).
    if dialect == "tsql" and name.upper() == "ROUND" and len(node.args) == 1:
        args += ", 0"
    # NOTE (P1 silent-output): a FunctionCall-level gap note here broke
    # the downstream text handlers that consume this output (TRUNC→ROUND
    # on the M4 path) — the M3 lesson. The unmapped-operator note lives
    # on the RawSQL branch instead; FunctionCall-modeled foreigners are
    # handled by their dedicated downstream handlers.
    return f"{name}({distinct}{args})"


_ORACLE_BITWISE = frozenset(
    {
        BinaryOperator.BIT_AND,
        BinaryOperator.BIT_OR,
        BinaryOperator.BIT_XOR,
        BinaryOperator.BIT_LSHIFT,
        BinaryOperator.BIT_RSHIFT,
    }
)


#: Binding strength of each binary operator (higher binds tighter). Used to
#: re-parenthesize on emit: the converter drops explicit exp.Paren nodes, so
#: ``a AND (b OR c)`` must regain its parens or it silently becomes
#: ``(a AND b) OR c`` (audit 2026-07-08 D8 class: silent semantic corruption).
_BIN_PRECEDENCE = {
    BinaryOperator.OR: 1,
    BinaryOperator.AND: 2,
    BinaryOperator.EQ: 3,
    BinaryOperator.NEQ: 3,
    BinaryOperator.LT: 3,
    BinaryOperator.GT: 3,
    BinaryOperator.LTE: 3,
    BinaryOperator.GTE: 3,
    BinaryOperator.LIKE: 3,
    BinaryOperator.ILIKE: 3,
    BinaryOperator.IN: 3,
    BinaryOperator.NOT_IN: 3,
    BinaryOperator.BETWEEN: 3,
    BinaryOperator.IS: 3,
    BinaryOperator.NULLSAFE_EQ: 3,
    BinaryOperator.NULLSAFE_NEQ: 3,
    BinaryOperator.BIT_OR: 4,
    BinaryOperator.BIT_XOR: 4,
    BinaryOperator.BIT_AND: 4,
    BinaryOperator.BIT_LSHIFT: 4,
    BinaryOperator.BIT_RSHIFT: 4,
    BinaryOperator.ADD: 5,
    BinaryOperator.SUB: 5,
    BinaryOperator.CONCAT: 5,
    BinaryOperator.MUL: 6,
    BinaryOperator.DIV: 6,
    BinaryOperator.MOD: 6,
}

#: Bitwise vs arithmetic operators — their relative precedence differs by engine
#: (MySQL/Oracle: bitwise looser than +/*; PostgreSQL/T-SQL: tighter), so a mixed
#: expression must be explicitly parenthesized to keep the source's grouping.
_BITWISE_BIN_OPS = frozenset(
    {
        BinaryOperator.BIT_OR,
        BinaryOperator.BIT_XOR,
        BinaryOperator.BIT_AND,
        BinaryOperator.BIT_LSHIFT,
        BinaryOperator.BIT_RSHIFT,
    }
)
_ARITH_BIN_OPS = frozenset(
    {
        BinaryOperator.ADD,
        BinaryOperator.SUB,
        BinaryOperator.MUL,
        BinaryOperator.DIV,
        BinaryOperator.MOD,
    }
)

#: Operators where ``a op (b op c)`` differs from ``(a op b) op c`` — the
#: right operand keeps its parens even at equal precedence.
_NON_ASSOCIATIVE = frozenset(
    {
        BinaryOperator.SUB,
        BinaryOperator.DIV,
        BinaryOperator.MOD,
        BinaryOperator.BIT_LSHIFT,
        BinaryOperator.BIT_RSHIFT,
    }
)


def _emit_operand(
    child: ASTNode, parent: BinaryOperator, dialect: str, right: bool = False
) -> str:
    """Emit a binary operand, parenthesized when it binds weaker than *parent*."""
    text = _emit_expression(child, dialect)
    if isinstance(child, BinaryOp):
        child_prec = _BIN_PRECEDENCE[child.operator]
        parent_prec = _BIN_PRECEDENCE[parent]
        # Bitwise-vs-arithmetic precedence is NOT portable: MySQL/Oracle bind a
        # bitwise operator LOOSER than +/*, but PostgreSQL/T-SQL bind it tighter.
        # A source tree like ``10 & (6 + 1)`` would silently re-associate to
        # ``(10 & 6) + 1`` on the other family, so always parenthesize across the
        # boundary (explicit parens are semantics-preserving everywhere).
        _pair = {parent, child.operator}
        if _pair & _BITWISE_BIN_OPS and _pair & _ARITH_BIN_OPS:
            return f"({text})"
        if child_prec < parent_prec or (
            right and child_prec == parent_prec and parent in _NON_ASSOCIATIVE
        ):
            return f"({text})"
    return text


def _is_integer_operand(node: object) -> bool:
    """An integer literal, or a procedural variable declared as an integer type."""
    if isinstance(node, Literal):
        return node.dtype == "integer"
    if isinstance(node, ColumnRef):
        ints = INTEGER_VARIABLES.get()
        return ints is not None and node.name.lstrip("@").lower() in ints
    return False


def _nullable_string_operand(node: object) -> bool:
    """An operand a concat could see as NULL: a NULL literal, or a procedural
    string variable (always nullable — unassigned locals start NULL)."""
    if isinstance(node, Literal):
        return node.dtype == "null"
    if isinstance(node, ColumnRef):
        strs = STRING_VARIABLES.get()
        return strs is not None and node.name.lstrip("@").lower() in strs
    return False


def _is_nonneg_literal(node: ASTNode) -> bool:
    """True if node is a non-negative numeric literal (so a negative-value guard
    is provably unnecessary). A ``-1`` parses as a UnaryOp, not a Literal."""
    return (
        isinstance(node, Literal)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value >= 0
    )


def _is_numeric_str_literal(node: ASTNode) -> bool:
    """True if node is a string literal whose text is a plain number ('5',
    '5.5', '-3') — so MySQL's numeric '+' can be reproduced with a CAST without
    risking MySQL's lenient leading-prefix conversion ('10abc' -> 10)."""
    return (
        isinstance(node, Literal)
        and node.dtype == "string"
        and isinstance(node.value, str)
        and re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", node.value) is not None
    )


def _is_date_only_literal(node: ASTNode) -> bool:
    """True if node is a ``YYYY-MM-DD`` (date-only, no time) string literal."""
    return (
        isinstance(node, Literal)
        and isinstance(node.value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", node.value.strip()) is not None
    )


def _is_nonneg_int_literal(node: ASTNode) -> bool:
    """True if node is a non-negative, integer-valued numeric literal — so both a
    negative-value guard AND a round-the-float guard are provably unnecessary. A
    ``-1`` parses as a UnaryOp (not a Literal); ``2.9`` is a non-integer float."""
    return (
        isinstance(node, Literal)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value >= 0
        and node.value == int(node.value)
    )


def _date_literal_sql(node: ASTNode, dialect: str) -> str | None:
    """Emit a sqlglot ``DATE '…'`` literal (a DATE_STR_TO_DATE wrapper around a
    string) as the target's date literal, or None if node is not one."""
    if (
        isinstance(node, FunctionCall)
        and node.name.upper() == "DATE_STR_TO_DATE"
        and len(node.args) == 1
        and isinstance(node.args[0], Literal)
    ):
        s = node.args[0].value
        if dialect in ("oracle", "postgresql"):
            return f"DATE '{s}'"
        return f"CAST('{s}' AS DATE)"
    # PostgreSQL ``DATE '…'`` parses as CAST('…' AS DATE) rather than the
    # sqlglot wrapper, so recognize that shape too.
    if (
        isinstance(node, CastExpression)
        and node.target_type.name.split("(")[0].strip().upper() == "DATE"
        and isinstance(node.expression, Literal)
        and isinstance(node.expression.value, str)
    ):
        s = node.expression.value
        if dialect in ("oracle", "postgresql"):
            return f"DATE '{s}'"
        return f"CAST('{s}' AS DATE)"
    return None


def _emit_binary(node: BinaryOp, dialect: str) -> str:
    """Emit a binary operation."""
    # ``DATE 'a' - DATE 'b'`` is a day count on every engine, but spelled
    # differently: Oracle/PostgreSQL subtract dates natively (yielding days),
    # T-SQL/MySQL need DATEDIFF. sqlglot models each DATE literal as a
    # DATE_STR_TO_DATE wrapper whose default unwrap is a bare string, so a plain
    # ``str - str`` computes nothing — detect the two date literals and spell the
    # difference per dialect (Oracle source d1 - d2 = days from d2 to d1).
    if node.operator == BinaryOperator.SUB:
        ld = _date_literal_sql(node.left, dialect)
        rd = _date_literal_sql(node.right, dialect)
        if ld is not None and rd is not None:
            # MySQL's ``DATE - DATE`` is a numeric YYYYMMDD subtraction
            # (2020-03-01 - 2020-01-01 = 200, not 60 days); the meaningful day
            # count is emitted instead, so flag the deliberate normalization.
            _sub_carrier = (
                " /* UNIQUE: MySQL DATE - DATE is a numeric YYYYMMDD subtraction; "
                "normalized to a day count (docs/03-unsupported.md) */"
                if SOURCE_DIALECT.get() == "mysql" and dialect != "mysql"
                else ""
            )
            if dialect in ("oracle", "postgresql"):
                return f"({ld} - {rd}){_sub_carrier}"
            if dialect == "tsql":
                return f"DATEDIFF(DAY, {rd}, {ld}){_sub_carrier}"
            return f"DATEDIFF({ld}, {rd})"  # MySQL

    # ``date + n`` adds n days on PostgreSQL/Oracle (yielding a date), but MySQL
    # reads it as a NUMERIC addition (2020-01-01 + 30 = 20200131) and T-SQL
    # rejects it. From a PG/Oracle source, spell a date-literal-plus-integer as
    # DATE_ADD / DATEADD on those targets so the day arithmetic is preserved.
    if (
        node.operator == BinaryOperator.ADD
        and dialect in ("mysql", "tsql")
        and SOURCE_DIALECT.get() in ("postgresql", "oracle")
    ):
        for dside, nside in ((node.left, node.right), (node.right, node.left)):
            dlit = _date_literal_sql(dside, dialect)
            if dlit is not None and _is_nonneg_int_literal(nside):
                n = _emit_expression(nside, dialect)
                if dialect == "mysql":
                    return f"DATE_ADD({dlit}, INTERVAL {n} DAY)"
                return f"DATEADD(DAY, {n}, {dlit})"

    # MySQL '+' is always arithmetic; T-SQL '+' on strings concatenates
    # ('5' + '5' = '55', not 10). When a MySQL source adds numeric string
    # literals, cast them so T-SQL does the arithmetic (10.0, matching MySQL).
    if (
        node.operator == BinaryOperator.ADD
        and dialect == "tsql"
        and SOURCE_DIALECT.get() == "mysql"
        and _is_numeric_str_literal(node.left)
        and _is_numeric_str_literal(node.right)
    ):
        _sl = _emit_expression(node.left, dialect)
        _sr = _emit_expression(node.right, dialect)
        return f"CAST({_sl} AS FLOAT) + CAST({_sr} AS FLOAT)"

    left = _emit_operand(node.left, node.operator, dialect)
    right = _emit_operand(node.right, node.operator, dialect, right=True)

    # Integer division diverges: PG/T-SQL truncate two integer operands
    # (5 / 2 = 2), MySQL/Oracle return a decimal (2.5). Compensate when both
    # operands are known integers — a literal, or (in the procedural pipeline) a
    # variable declared with an integer type — to keep the source's result.
    if (
        node.operator == BinaryOperator.DIV
        and _is_integer_operand(node.left)
        and _is_integer_operand(node.right)
    ):
        src = SOURCE_DIALECT.get()
        int_div = ("postgresql", "tsql")
        if src and (src in int_div) != (dialect in int_div):
            if src in int_div:  # source truncated toward zero — match it
                return (
                    f"({left} DIV {right})"
                    if dialect == "mysql"
                    else f"TRUNC({left} / {right})"
                )
            return f"({left} * 1.0 / {right})"  # source decimal — force it
    # MySQL's / is *always* decimal division (SUM(x)/COUNT(x) = 1.5), but PG/T-SQL
    # truncate two integers to an integer (1). The literal case is handled above;
    # this covers non-literal integer results (aggregates like COUNT) that can't be
    # proven integer statically — mysql never truncates, so forcing decimal is safe.
    if (
        node.operator == BinaryOperator.DIV
        and dialect in ("postgresql", "tsql")
        and SOURCE_DIALECT.get() == "mysql"
    ):
        return f"({left} * 1.0 / {right})"

    # Interval arithmetic: T-SQL has no INTERVAL literal — lower
    # ``expr ± INTERVAL 'n' UNIT`` to DATEADD(UNIT, ±n, expr).
    if dialect == "tsql" and node.operator in (
        BinaryOperator.ADD,
        BinaryOperator.SUB,
    ):
        interval_side = None
        other_side = None
        # For SUB only ``expr - INTERVAL`` is date math (INTERVAL - expr
        # is not); ADD is commutative.
        candidates = [(node.right, node.left)]
        if node.operator == BinaryOperator.ADD:
            candidates.append((node.left, node.right))
        for cand, other in candidates:
            if isinstance(cand, RawSQL):
                m = re.fullmatch(
                    r"(?is)INTERVAL\s+'?(\d+)'?\s+"
                    r"(YEAR|QUARTER|MONTH|WEEK|DAY|HOUR|MINUTE|SECOND)S?",
                    cand.sql.strip(),
                )
                if m:
                    interval_side, other_side = m, other
                    break
        if interval_side is not None and other_side is not None:
            n = interval_side.group(1)
            unit = interval_side.group(2).upper()
            amount = n if node.operator == BinaryOperator.ADD else f"-{n}"
            other_sql = _emit_expression(other_side, dialect)
            result = f"DATEADD({unit}, {amount}, {other_sql})"
            # MySQL date + INTERVAL on a DATE returns a DATE; cast the T-SQL
            # DATEADD back to DATE when the base is a date-only literal.
            if SOURCE_DIALECT.get() == "mysql" and _is_date_only_literal(other_side):
                result = f"CAST({result} AS DATE)"
            return result

    # Null-safe comparison: PG spells IS [NOT] DISTINCT FROM, MySQL <=>;
    # T-SQL/Oracle use the version-safe EXISTS-INTERSECT form (INTERSECT
    # compares rows with null-safe semantics on every engine).
    if node.operator in (BinaryOperator.NULLSAFE_EQ, BinaryOperator.NULLSAFE_NEQ):
        equal = node.operator == BinaryOperator.NULLSAFE_EQ
        if dialect == "mysql":
            core = f"{left} <=> {right}"
            return core if equal else f"NOT ({core})"
        if dialect in ("tsql", "oracle"):
            dual = " FROM DUAL" if dialect == "oracle" else ""

            # A ROW constructor operand must unpack into select-list items:
            # ``SELECT (f1, f2)`` is an illegal parenthesized tuple there.
            # It arrives as an ExpressionList or as parenthesized RawSQL.
            def _unpack_row(side: ASTNode, emitted: str) -> str:
                if isinstance(side, ExpressionList):
                    return ", ".join(_emit_expression(i, dialect) for i in side.items)
                text = emitted.strip()
                if (
                    isinstance(side, RawSQL)
                    and text.startswith("(")
                    and text.endswith(")")
                ):
                    return text[1:-1].strip()
                return emitted

            left = _unpack_row(node.left, left)
            right = _unpack_row(node.right, right)
            core = f"EXISTS (SELECT {left}{dual} INTERSECT SELECT {right}{dual})"
            pred = core if equal else f"NOT {core}"
            # A predicate is not a value expression on these engines; the
            # generic (value) position wraps in CASE. _emit_condition
            # unwraps it for WHERE/HAVING/ON.
            return f"CASE WHEN {pred} THEN 1 ELSE 0 END = 1"
        keyword = "IS NOT DISTINCT FROM" if equal else "IS DISTINCT FROM"
        return f"{left} {keyword} {right}"

    # Row tuple IN a literal VALUES list: expand to the disjunction of
    # conjunctions — T-SQL/Oracle have no row constructors.
    if (
        dialect in ("tsql", "oracle")
        and node.operator == BinaryOperator.IN
        and isinstance(node.right, ExpressionList)
        and len(node.right.items) == 1
        and isinstance(node.right.items[0], RawSQL)
    ):
        lt = _tuple_items(node.left, left)
        values_text = node.right.items[0].sql.strip()
        vm = re.fullmatch(
            r"(?is)VALUES\s+(\(([^()]*)\)\s*(?:,\s*\(([^()]*)\)\s*)*)",
            values_text,
        )
        if lt is not None and vm is not None:
            rows = [r.strip() for r in re.findall(r"\(([^()]*)\)", values_text)]
            groups = []
            ok = True
            for row in rows:
                cells = [c.strip() for c in row.split(",")]
                if len(cells) != len(lt):
                    ok = False
                    break
                groups.append(
                    "("
                    + " AND ".join(f"{a} = {b}" for a, b in zip(lt, cells, strict=True))
                    + ")"
                )
            if ok and groups:
                return " OR ".join(groups)

    # Row-tuple comparison: T-SQL and Oracle have no row constructors
    # in comparisons — expand ``(a, b) = (x, y)`` pairwise (AND for =,
    # OR for <>).
    if dialect in ("tsql", "oracle") and node.operator in (
        BinaryOperator.EQ,
        BinaryOperator.NEQ,
    ):
        lt = _tuple_items(node.left, left)
        rt = _tuple_items(node.right, right)
        if lt is not None and rt is not None and len(lt) == len(rt) > 1:
            if node.operator == BinaryOperator.EQ:
                return " AND ".join(f"{a} = {b}" for a, b in zip(lt, rt, strict=True))
            return " OR ".join(f"{a} <> {b}" for a, b in zip(lt, rt, strict=True))

    # ``@@FETCH_STATUS = 0`` / ``<> 0`` / ``= -1`` is cursor state: when the
    # procedural transformer published the target's (success, failure) forms
    # (FETCH_STATUS_FORMS — M3 precondition (a)), map the comparison exactly
    # like the text path does; without context the RawSQL emit keeps the
    # documented neutral.
    fetch_forms = FETCH_STATUS_FORMS.get()
    if (
        fetch_forms is not None
        and isinstance(node.left, RawSQL)
        and node.left.sql.strip().upper() == "@@FETCH_STATUS"
        and node.operator in (BinaryOperator.EQ, BinaryOperator.NEQ)
    ):
        value = _plain_int_value(node.right)
        ok_form, fail_form = fetch_forms
        if node.operator == BinaryOperator.EQ and value == 0:
            return ok_form
        if node.operator == BinaryOperator.NEQ and value == 0:
            return fail_form
        if node.operator == BinaryOperator.EQ and value in (-1, -2):
            return fail_form

    # T-SQL has no date ``-`` operator (error 8117/257): ``d2 - d1`` over
    # two declared DATE variables spells DATEDIFF(DAY, d1, d2) — the days
    # from d1 to d2, matching the source's date-difference semantics.
    if node.operator == BinaryOperator.SUB and dialect == "tsql":

        def _bare_var_name(n: ASTNode) -> str | None:
            if isinstance(n, ColumnRef) and not n.table:
                return n.name
            # A mid-transform @name parses as a Parameter and lands in a
            # RawSQL (the embedded-hybrid rule).
            if isinstance(n, RawSQL) and re.fullmatch(r"@?\w+", n.sql.strip()):
                return n.sql.strip()
            return None

        left_name = _bare_var_name(node.left)
        right_name = _bare_var_name(node.right)
        date_vars = DATE_VARIABLES.get() or frozenset()
        if (
            left_name is not None
            and right_name is not None
            and left_name.lstrip("@").lower() in date_vars
            and right_name.lstrip("@").lower() in date_vars
        ):
            left_sql = _emit_expression(node.left, dialect)
            right_sql = _emit_expression(node.right, dialect)
            return f"DATEDIFF(DAY, {right_sql}, {left_sql})"

    # Oracle's SQL%ROWCOUNT parses as ``SQL % ROWCOUNT`` (modulo) — map
    # the global before emitting a bogus arithmetic expression. The other
    # cursor attributes (SQL%FOUND / <cursor>%[NOT]FOUND) parse the same
    # way and map like the text path: statement state to the row-count
    # predicate, named-cursor state to the fetch-status idiom.
    if (
        node.operator == BinaryOperator.MOD
        and isinstance(node.left, ColumnRef)
        and not node.left.table
        and isinstance(node.right, ColumnRef)
        and node.right.name.upper() in ("FOUND", "NOTFOUND")
        and SOURCE_DIALECT.get() == "oracle"
        and dialect != "oracle"
    ):
        negated = node.right.name.upper() == "NOTFOUND"
        if node.left.name.upper() == "SQL":
            if dialect == "tsql":
                return "@@ROWCOUNT = 0" if negated else "@@ROWCOUNT > 0"
            if dialect == "mysql":
                return "(ROW_COUNT() = 0)" if negated else "(ROW_COUNT() > 0)"
            return "NOT FOUND" if negated else "FOUND"
        if dialect == "tsql":
            return "@@FETCH_STATUS <> 0" if negated else "@@FETCH_STATUS = 0"
        if dialect == "postgresql":
            return "NOT FOUND" if negated else "FOUND"
        # MySQL named-cursor state needs the handler-flag machinery the
        # statement-level transformer owns; keep the attribute visible.
    if (
        node.operator == BinaryOperator.MOD
        and isinstance(node.left, ColumnRef)
        and node.left.name.upper() == "SQL"
        and isinstance(node.right, ColumnRef)
        and node.right.name.upper() == "ROWCOUNT"
    ):
        mapped = _map_system_global("SQL%ROWCOUNT", dialect)
        if mapped is not None:
            return mapped
        return "SQL%ROWCOUNT"

    op_map = {
        BinaryOperator.EQ: "=",
        BinaryOperator.NEQ: "<>",
        BinaryOperator.LT: "<",
        BinaryOperator.GT: ">",
        BinaryOperator.LTE: "<=",
        BinaryOperator.GTE: ">=",
        BinaryOperator.AND: "AND",
        BinaryOperator.OR: "OR",
        BinaryOperator.ADD: "+",
        BinaryOperator.SUB: "-",
        BinaryOperator.MUL: "*",
        BinaryOperator.DIV: "/",
        BinaryOperator.MOD: "%",
        BinaryOperator.IS: "IS",
        BinaryOperator.LIKE: "LIKE",
        BinaryOperator.ILIKE: "ILIKE",
        BinaryOperator.IN: "IN",
        BinaryOperator.NOT_IN: "NOT IN",
        BinaryOperator.BETWEEN: "BETWEEN",
        BinaryOperator.CONCAT: "||",
        BinaryOperator.BIT_AND: "&",
        BinaryOperator.BIT_OR: "|",
        BinaryOperator.BIT_XOR: "^",
        BinaryOperator.BIT_LSHIFT: "<<",
        BinaryOperator.BIT_RSHIFT: ">>",
    }

    op = op_map[node.operator]

    # PG/MySQL LIKE treat backslash as the default escape character; Oracle and
    # T-SQL have NO default escape, so a pattern like ``'a\%b'`` matches a
    # literal ``%`` on the source but a wildcard on the target. Preserve the
    # source semantics with an explicit ``ESCAPE '\'`` for a backslash pattern.
    if (
        node.operator == BinaryOperator.LIKE
        and dialect in ("oracle", "tsql")
        and SOURCE_DIALECT.get() in ("postgresql", "mysql")
        and isinstance(node.right, Literal)
        and isinstance(node.right.value, str)
        and "\\" in node.right.value
    ):
        return f"{left} LIKE {right} ESCAPE '\\'"

    # Dialect-specific overrides
    if node.operator == BinaryOperator.CONCAT:
        if dialect == "oracle":
            # Oracle's || treats NULL as '' (no propagation), unlike T-SQL '+',
            # PG '||' and MySQL CONCAT, which all yield NULL when any operand is
            # NULL. When the source propagates and a nullable string variable is
            # an operand, guard the concat so Oracle reproduces the source's
            # NULL result (RC-2 compensation).
            src = SOURCE_DIALECT.get()
            if src and src != "oracle":
                operands: list[ASTNode] = []

                def _gather_ops(n: ASTNode) -> None:
                    if isinstance(n, BinaryOp) and n.operator == BinaryOperator.CONCAT:
                        _gather_ops(n.left)
                        _gather_ops(n.right)
                    else:
                        operands.append(n)

                _gather_ops(node)
                nullable = [p for p in operands if _nullable_string_operand(p)]
                if nullable:
                    joined = " || ".join(_emit_expression(p, dialect) for p in operands)
                    guard = " OR ".join(
                        f"{_emit_expression(p, dialect)} IS NULL" for p in nullable
                    )
                    return f"CASE WHEN {guard} THEN NULL ELSE {joined} END"
        if dialect == "tsql":
            # T-SQL '+' does ARITHMETIC on numeric operands (2 + 3 = 5, not the
            # '23' that Oracle/PG || and MySQL CONCAT produce) and errors on
            # string + number. When any operand is numeric, use CONCAT(), which
            # converts every argument to a string — matching || semantics.
            tparts: list[ASTNode] = []

            def _gather_tsql(n: ASTNode) -> None:
                if isinstance(n, BinaryOp) and n.operator == BinaryOperator.CONCAT:
                    _gather_tsql(n.left)
                    _gather_tsql(n.right)
                else:
                    tparts.append(n)

            _gather_tsql(node)
            _arith = (
                BinaryOperator.ADD,
                BinaryOperator.SUB,
                BinaryOperator.MUL,
                BinaryOperator.DIV,
                BinaryOperator.MOD,
            )
            if any(
                (isinstance(p, Literal) and p.dtype in ("integer", "number", "float"))
                or _is_integer_operand(p)
                or (isinstance(p, BinaryOp) and p.operator in _arith)
                for p in tparts
            ):
                joined = ", ".join(_emit_expression(p, dialect) for p in tparts)
                return f"CONCAT({joined})"
            op = "+"
        elif dialect == "mysql":
            # MySQL has no concat operator at all — and a chain must emit
            # ONE flat CONCAT (the nested form is valid but the flat one is
            # the canonical output both pipelines agree on).
            parts: list[str] = []

            def _gather_concat(n: ASTNode) -> None:
                if isinstance(n, BinaryOp) and n.operator == BinaryOperator.CONCAT:
                    _gather_concat(n.left)
                    _gather_concat(n.right)
                else:
                    parts.append(_emit_expression(n, dialect))

            _gather_concat(node)
            return f"CONCAT({', '.join(parts)})"

    # MySQL's ``x MOD 0`` returns NULL; every other engine either errors (PG/
    # T-SQL divide-by-zero) or returns the dividend (Oracle). Preserve MySQL's
    # NULL-on-zero-divisor so the value matches on the other engines.
    if (
        node.operator == BinaryOperator.MOD
        and SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
    ):
        mod = f"MOD({left}, {right})" if dialect == "oracle" else f"{left} % {right}"
        return f"CASE WHEN {right} = 0 THEN NULL ELSE {mod} END"

    if node.operator == BinaryOperator.MOD and dialect == "oracle":
        return f"MOD({left}, {right})"

    # PostgreSQL spells bitwise XOR as "#" ("^" there is exponentiation).
    if node.operator == BinaryOperator.BIT_XOR and dialect == "postgresql":
        op = "#"

    # Oracle has no infix bitwise operators — only BITAND(). Express the others
    # via exact integer identities (for non-negative integers), validated live:
    #   a|b = a+b-(a&b),  a^b = a+b-2*(a&b),  a<<b = a*2^b,  a>>b = floor(a/2^b).
    if dialect == "oracle" and node.operator in _ORACLE_BITWISE:
        if node.operator == BinaryOperator.BIT_AND:
            return f"BITAND({left}, {right})"
        if node.operator == BinaryOperator.BIT_OR:
            return f"({left} + {right} - BITAND({left}, {right}))"
        if node.operator == BinaryOperator.BIT_XOR:
            return f"({left} + {right} - 2 * BITAND({left}, {right}))"
        if node.operator == BinaryOperator.BIT_LSHIFT:
            return f"({left} * POWER(2, {right}))"
        if node.operator == BinaryOperator.BIT_RSHIFT:
            return f"FLOOR({left} / POWER(2, {right}))"

    return f"{left} {op} {right}"


def _emit_unary(node: UnaryOp, dialect: str) -> str:
    """Emit a unary operation."""
    operand = _emit_expression(node.operand, dialect)
    # NOT/negation bind tighter than any binary operator the operand could
    # be — ``NOT a OR b`` would silently re-associate without the parens.
    if isinstance(node.operand, BinaryOp) and node.operator in (
        UnaryOperator.NOT,
        UnaryOperator.NEGATIVE,
    ):
        operand = f"({operand})"

    if node.operator == UnaryOperator.NOT:
        return f"NOT {operand}"
    if node.operator == UnaryOperator.NEGATIVE:
        return f"-{operand}"
    if node.operator == UnaryOperator.BITWISE_NOT:
        # Oracle has no ~ (ORA-00911); the two's-complement identity
        # ``-(x) - 1`` is exact for integers (wave 189).
        if dialect == "oracle":
            return f"-({operand}) - 1"
        # MySQL's ~ yields an UNSIGNED BIGINT (~5 = 18446744073709551610); a
        # signed-source ~ is a signed result (-6), so cast back to SIGNED.
        if dialect == "mysql" and SOURCE_DIALECT.get() not in (None, "mysql"):
            return f"CAST(~{operand} AS SIGNED)"
        return f"~{operand}"
    if node.operator == UnaryOperator.IS_NULL:
        return f"{operand} IS NULL"
    if node.operator == UnaryOperator.IS_NOT_NULL:
        return f"{operand} IS NOT NULL"
    if node.operator == UnaryOperator.EXISTS:
        # operand is a SubqueryExpression, already rendered with its own parens.
        return f"EXISTS {operand}"

    return operand


def _emit_case(node: CaseExpression, dialect: str) -> str:
    """Emit a CASE expression."""
    parts = ["CASE"]

    if node.operand:
        parts[0] += f" {_emit_expression(node.operand, dialect)}"

    for condition, result in node.whens:
        # A searched CASE's WHEN is condition position (a simple CASE
        # compares the operand — expression position).
        cond = (
            _emit_expression(condition, dialect)
            if node.operand
            else _emit_condition(condition, dialect)
        )
        res = _emit_expression(result, dialect)
        parts.append(f"  WHEN {cond} THEN {res}")

    if node.else_expr:
        parts.append(f"  ELSE {_emit_expression(node.else_expr, dialect)}")

    parts.append("END")
    return "\n".join(parts)


def _emit_window(node: WindowFunction, dialect: str) -> str:
    """Emit a window function."""
    func = _emit_function(node.function, dialect)
    # Windowed string aggregation (Oracle ``LISTAGG(…) WITHIN GROUP (…) OVER (…)``)
    # has no portable equivalent: T-SQL STRING_AGG (error 4113) and MySQL
    # GROUP_CONCAT (error 1235) are never window functions, and PostgreSQL rejects
    # an ORDER-BY'd aggregate used as a window function. Degrade with a carrier.
    if isinstance(node.function, FunctionCall) and node.function.name in (
        "GROUP_CONCAT",
        "STRING_AGG",
        "LISTAGG",
    ):
        ordered = bool(re.search(r"(?i)\bORDER\s+BY\b|\bWITHIN\s+GROUP\b", func))
        if dialect in ("tsql", "mysql") or (dialect == "postgresql" and ordered):
            return (
                "NULL /* UNIQUE: windowed string aggregation (string-agg OVER …) "
                f"has no {dialect} equivalent — see docs/03-unsupported.md */"
            )
    spec_parts: list[str] = []

    if node.window.partition_by:
        partition = ", ".join(
            _emit_expression(p, dialect) for p in node.window.partition_by
        )
        spec_parts.append(f"PARTITION BY {partition}")

    if node.window.order_by:
        order = ", ".join(_emit_order_item(o, dialect) for o in node.window.order_by)
        spec_parts.append(f"ORDER BY {order}")
    elif dialect == "tsql" and re.match(
        r"(?i)\s*(FIRST_VALUE|LAST_VALUE|LAG|LEAD|NTILE|ROW_NUMBER|RANK|"
        r"DENSE_RANK|PERCENT_RANK|CUME_DIST)\s*\(",
        func,
    ):
        # T-SQL requires ORDER BY in these functions' OVER clause (error
        # 4112); PostgreSQL allows an empty/partition-only spec. The
        # standard neutral idiom preserves "no meaningful order".
        spec_parts.append("ORDER BY (SELECT NULL)")

    if node.window.frame:
        spec_parts.append(node.window.frame)

    spec = " ".join(spec_parts)
    return f"{func} OVER ({spec})"


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
            f"(SELECT ({_gstart}) + LEVEL - 1 AS value FROM DUAL "
            f"CONNECT BY LEVEL <= ({_gstop}) - ({_gstart}) + 1) {_gal}"
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
            f" /* UNIQUE: TABLESAMPLE ({what}) has no MySQL equivalent — all rows "
            "returned (docs/03-unsupported.md) */"
        )
    if dialect == "tsql":
        return f" TABLESAMPLE ({pct} PERCENT)" if pct else f" TABLESAMPLE ({rows} ROWS)"
    if dialect == "oracle":
        if pct:
            return f" SAMPLE ({pct})"
        return (
            " /* UNIQUE: TABLESAMPLE by row count has no Oracle SAMPLE form "
            "(docs/03-unsupported.md) */"
        )
    # postgresql
    if pct:
        return f" TABLESAMPLE {node.sample_method or 'SYSTEM'} ({pct})"
    return (
        " /* UNIQUE: TABLESAMPLE by row count has no PostgreSQL equivalent "
        "(docs/03-unsupported.md) */"
    )


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
                f"FETCH FIRST {_emit_expression(limit.limit, dialect)}"
                f"{pct} ROWS {tail}"
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
                " /* UNIQUE: source had WITH TIES; MySQL has no equivalent — rows "
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
                f" /* UNIQUE: source was TOP n PERCENT; {dialect} has no LIMIT "
                "PERCENT — emitted as a row count, adjust to "
                "CEIL(n/100 * total_rows) if a true percentage is required */"
            )
        parts.append(limit_sql)
    if limit.offset:
        parts.append(f"OFFSET {_emit_expression(limit.offset, dialect)}")
    return "\n".join(parts)
