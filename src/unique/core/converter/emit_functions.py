# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import re
from typing import cast

from unique.core.ast_nodes import (
    ASTNode,
    BinaryOp,
    CaseExpression,
    CastExpression,
    ColumnRef,
    DataType,
    FunctionCall,
    Literal,
    RawSQL,
    UnaryOp,
    UnaryOperator,
)

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403
from unique.core.converter.harvest import (  # noqa: F401
    _coerce_bit_literal,
    _coerce_date_literal,
    _oracle_date_literal,
    wrap_oracle_date_arg,
)
from unique.core.mappings import (
    CURRENT_DATE_EXPR,
    CURRENT_TIMESTAMP_EXPR,
    ERROR_MESSAGE_EXPR,
    ERROR_MESSAGE_SOURCES,
    LAST_IDENTITY_EXPR,
    LAST_IDENTITY_SOURCE_FUNCS,
    ORACLE_DATE_FORMAT_STYLES,
    tsql_call_needs_schema,
)

# NOTE: moved verbatim from emit.py (audit doc 04 F4 split). The emit.py
# helpers and sibling emitters this module calls are imported explicitly at
# the module tail (after the defs) — see emit.py's module docstring for why the
# cross-family imports live at the tail rather than the top.

__all__ = [
    "_emit_date_add",
    "_emit_date_diff",
    "_TEXT_TYPE_NAMES",
    "_TEXT_RETURNING_FUNCS",
    "_is_text_valued",
    "_emit_group_concat",
    "_literal_str_resolve",
    "_CHAR_CAST_BASES",
    "_MYSQL_CHARSET_CODECS",
    "_fold_length_literal",
    "_fold_oracle_instr",
    "_emit_sequence_call",
    "_emit_function",
]


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
        # PG has no ``quarter`` interval unit — a quarter is three months.
        if unit == "QUARTER":
            if literal_n is not None:
                return f"{ts} {op} INTERVAL '{int(literal_n) * 3} months'"
            return f"{ts} {op} ({n}) * INTERVAL '3 months'"
        if literal_n is not None:
            return f"{ts} {op} INTERVAL '{n} {unit}'"
        return f"{ts} {op} ({n}) * INTERVAL '1 {unit}'"
    if dialect == "oracle":
        if unit in ("MONTH", "YEAR", "QUARTER"):
            if unit == "MONTH":
                months = n
            elif unit == "QUARTER":
                months = (
                    str(int(literal_n) * 3) if literal_n is not None else f"({n}) * 3"
                )
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


def _complete_period_adjust(
    boundary: str, start: str, end: str, unit: str, dialect: str
) -> str:
    """Drop the incomplete final period from a boundary count (PG/Oracle).

    MySQL TIMESTAMPDIFF counts COMPLETE year/quarter/month periods, but the
    year*12+month boundary difference overcounts when the end's day-of-month has
    not reached the start's (2020-01-31 -> 2020-03-30 is 1 complete month, not
    2). Subtract 1 when adding ``boundary`` periods to start overshoots end —
    mirroring the T-SQL DATEADD adjustment (challenge my-timestampdiff-mon-pgora).
    """
    if dialect == "postgresql":
        iv = {"MONTH": "1 month", "QUARTER": "3 months", "YEAR": "1 year"}[unit]
        added = f"{start} + ({boundary}) * INTERVAL '{iv}'"
    else:  # oracle
        months = {"MONTH": 1, "QUARTER": 3, "YEAR": 12}[unit]
        added = f"ADD_MONTHS({start}, ({boundary}) * {months})"
    return f"({boundary} - CASE WHEN {added} > {end} THEN 1 ELSE 0 END)"


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
        if unit == "QUARTER":
            return (
                f"((YEAR({end}) * 4 + QUARTER({end})) - "
                f"(YEAR({start}) * 4 + QUARTER({start})))"
            )
        if unit == "YEAR":
            return f"(YEAR({end}) - YEAR({start}))"
        k = {"HOUR": 3600, "MINUTE": 60, "SECOND": 1}.get(unit)
        if k is None:
            return None  # exotic unit: degrade to a carrier + warning, never raise
        return (
            f"(FLOOR(UNIX_TIMESTAMP({end}) / {k}) - "
            f"FLOOR(UNIX_TIMESTAMP({start}) / {k}))"
        )
    is_tsdiff = node.name.upper() == "TIMESTAMPDIFF"
    if dialect == "postgresql":
        # ISO string literals need the ANSI ``DATE '…'`` form for date math.
        end, start = wrap_oracle_date_arg(end), wrap_oracle_date_arg(start)
        if unit == "DAY":
            return f"(CAST({end} AS DATE) - CAST({start} AS DATE))"
        if unit == "WEEK":
            return f"FLOOR((CAST({end} AS DATE) - CAST({start} AS DATE)) / 7)"
        if unit == "MONTH":
            boundary = (
                f"((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))"
            )
        elif unit == "QUARTER":
            boundary = (
                f"((EXTRACT(YEAR FROM {end}) * 4 + EXTRACT(QUARTER FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 4 + EXTRACT(QUARTER FROM {start})))"
            )
        elif unit == "YEAR":
            boundary = f"(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))"
        else:
            k = {"HOUR": 3600, "MINUTE": 60, "SECOND": 1}.get(unit)
            if k is None:
                return None  # exotic unit: degrade to a carrier + warning
            return (
                f"(FLOOR(EXTRACT(EPOCH FROM {end}) / {k}) - "
                f"FLOOR(EXTRACT(EPOCH FROM {start}) / {k}))"
            )
        if is_tsdiff:
            return _complete_period_adjust(boundary, start, end, unit, dialect)
        return boundary
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
            boundary = (
                f"((EXTRACT(YEAR FROM {end}) * 12 + EXTRACT(MONTH FROM {end})) - "
                f"(EXTRACT(YEAR FROM {start}) * 12 + EXTRACT(MONTH FROM {start})))"
            )
            if is_tsdiff:
                return _complete_period_adjust(boundary, start, end, unit, dialect)
            return boundary
        if unit == "QUARTER":
            # Oracle has no EXTRACT(QUARTER); derive it from TO_CHAR(d, 'Q').
            boundary = (
                f"((EXTRACT(YEAR FROM {end}) * 4 + TO_NUMBER(TO_CHAR({end}, 'Q'))) - "
                f"(EXTRACT(YEAR FROM {start}) * 4 + TO_NUMBER(TO_CHAR({start}, 'Q'))))"
            )
            if is_tsdiff:
                return _complete_period_adjust(boundary, start, end, unit, dialect)
            return boundary
        if unit == "YEAR":
            boundary = f"(EXTRACT(YEAR FROM {end}) - EXTRACT(YEAR FROM {start}))"
            if is_tsdiff:
                return _complete_period_adjust(boundary, start, end, unit, dialect)
            return boundary
        trunc_fmt = {"HOUR": "HH24", "MINUTE": "MI"}.get(unit)
        mult = {"HOUR": 24, "MINUTE": 1440, "SECOND": 86400}.get(unit)
        if mult is None:
            return None  # exotic unit: degrade to a carrier + warning, never raise
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
            # A lengthless character CAST inside the canonical fragment is
            # ORA-00906 in SQL context.
            expr_sql = re.sub(
                r"(?i)\bN?VARCHAR2?\b(?!\s*\()", "VARCHAR2(4000)", expr_sql
            )
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
            s = re.sub(r"(?i)\bAS\s+N?VARCHAR\s*\)", "AS CHAR)", s)
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
            if node.distinct and order_sql:
                # PG: with DISTINCT the ORDER BY key must be the aggregated
                # argument itself. When the value is cast, the sort key (minus
                # its trailing ASC/DESC direction) must carry the same cast to
                # still match — else "ORDER BY expressions must appear in the
                # argument list" (my-groupconcat-distinct).
                mdir = re.search(r"(?i)\s+(ASC|DESC)\s*$", order_sql)
                key = order_sql[: mdir.start()] if mdir else order_sql
                if key.strip() == expr_sql:
                    order_sql = value + (mdir.group(0) if mdir else "")
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


def _literal_str_resolve(node: ASTNode) -> str | bytes | None:
    """Resolve *node* to its compile-time string/bytes value, unwrapping only
    the wrappers the pipeline itself materializes around a literal: a CAST to a
    character type, a plain-space TRIM family call, and a base64 DECODE /
    FROM_BASE64. Returns None for anything not statically known."""
    if isinstance(node, Literal) and isinstance(node.value, str):
        if node.dtype in ("string", "national", "unknown"):
            return node.value
        return None
    if isinstance(node, CastExpression):
        base = node.target_type.name.split("(")[0].strip().upper()
        if base in _CHAR_CAST_BASES:
            return _literal_str_resolve(node.expression)
        return None
    if isinstance(node, FunctionCall):
        fn = node.name.upper()
        if fn in ("TRIM", "LTRIM", "RTRIM") and len(node.args) == 1:
            inner = _literal_str_resolve(node.args[0])
            if not isinstance(inner, str):
                return None
            strip = {"TRIM": inner.strip, "LTRIM": inner.lstrip, "RTRIM": inner.rstrip}
            return strip[fn](" ")
        if (
            fn in ("DECODE", "FROM_BASE64")
            and len(node.args) in (1, 2)
            and isinstance(node.args[0], Literal)
            and isinstance(node.args[0].value, str)
            and (
                len(node.args) == 1
                or (
                    isinstance(node.args[1], Literal)
                    and str(node.args[1].value).lower() == "base64"
                )
            )
        ):
            try:
                return base64.b64decode(node.args[0].value)
            except (ValueError, binascii.Error):
                return None
    return None


_CHAR_CAST_BASES = frozenset(
    {
        "CHAR",
        "NCHAR",
        "VARCHAR",
        "NVARCHAR",
        "VARCHAR2",
        "NVARCHAR2",
        "TEXT",
        "CLOB",
        "NCLOB",
    }
)

#: MySQL character-set names -> Python codecs (for compile-time byte decodes).
_MYSQL_CHARSET_CODECS: dict[str, str] = {
    "utf8mb4": "utf-8",
    "utf8mb3": "utf-8",
    "utf8": "utf-8",
    "latin1": "cp1252",
    "ascii": "ascii",
    "binary": "latin-1",
    "ucs2": "utf-16-be",
    "utf16": "utf-16-be",
    "utf16le": "utf-16-le",
    "utf32": "utf-32-be",
}


def _fold_length_literal(node: FunctionCall) -> str | None:
    """Fold LENGTH(<literal>) to the SOURCE dialect's value.

    Per-source semantics: T-SQL LEN counts UTF-16 code units of the
    right-trimmed text; MySQL's LENGTH counts utf8mb4 BYTES but shares this IR
    name with CHAR_LENGTH, so only an ASCII literal (where both agree) folds;
    PG/Oracle count code points. A bytes value (base64 DECODE) is a byte count
    everywhere."""
    if len(node.args) != 1 or node.distinct:
        return None
    value = _literal_str_resolve(node.args[0])
    if isinstance(value, bytes):
        return str(len(value))
    if not isinstance(value, str):
        return None
    source = SOURCE_DIALECT.get()
    if source == "tsql":
        trimmed = value.rstrip(" ")
        return str(sum(2 if ord(c) > 0xFFFF else 1 for c in trimmed))
    if source == "mysql":
        return str(len(value)) if value.isascii() else None
    return str(len(value))


def _fold_oracle_instr(node: FunctionCall) -> str | None:
    """Fold Oracle's extended INSTR (negative start / 4-arg occurrence) over
    literal arguments. IR argument order is CHARINDEX-style (needle, haystack,
    start, occurrence). Oracle semantics: a positive start finds the occ-th
    occurrence at-or-after it; a negative start searches BACKWARD from
    position LENGTH(s)+start+1. Returns 0 when absent."""
    if not (2 <= len(node.args) <= 4):
        return None
    vals = []
    for arg in node.args:
        if isinstance(arg, Literal):
            vals.append(arg.value)
        elif (
            isinstance(arg, UnaryOp)
            and arg.operator == UnaryOperator.NEGATIVE
            and isinstance(arg.operand, Literal)
        ):
            vals.append(-arg.operand.value)
        else:
            return None
    sub, s = vals[0], vals[1]
    if not isinstance(s, str) or not isinstance(sub, str) or not sub:
        return None
    try:
        start = int(vals[2]) if len(vals) > 2 else 1
        occ = int(vals[3]) if len(vals) > 3 else 1
    except (TypeError, ValueError):
        return None
    if start == 0 or occ < 1:
        return "0"
    starts = [i for i in range(len(s) - len(sub) + 1) if s.startswith(sub, i)]
    if start > 0:
        hits = [i for i in starts if i >= start - 1]
    else:
        limit = len(s) + start
        hits = [i for i in reversed(starts) if i <= limit]
    return str(hits[occ - 1] + 1) if occ <= len(hits) else "0"


def _emit_sequence_call(node: FunctionCall, dialect: str) -> str | None:
    """Emit an Oracle-sequence pseudo-call per target, or ``None`` if *node* is
    not one for this dialect.

    Both the T-SQL ``NEXT VALUE FOR seq`` source and Oracle ``seq.NEXTVAL``
    (see ``convert._convert_sequence_ref``) model as ``NEXT_VALUE_FOR``, and
    Oracle ``seq.CURRVAL`` as ``CURRENT_VALUE_FOR``; this renders each per
    target from the shared model. MySQL has no sequences, so it returns
    ``None`` and the statement degrades honestly at the output gate. T-SQL has
    no CURRVAL, so that one degrades to a documented carrier (auto-warned).
    """
    up = node.name.upper()
    if up not in ("NEXT_VALUE_FOR", "CURRENT_VALUE_FOR") or len(node.args) != 1:
        return None
    if dialect == "mysql":
        return None
    seq = _emit_expression(node.args[0], dialect)
    bare = node.args[0].name if isinstance(node.args[0], ColumnRef) else seq
    if up == "NEXT_VALUE_FOR":
        return {
            "oracle": f"{seq}.NEXTVAL",
            "tsql": f"NEXT VALUE FOR {seq}",
        }.get(dialect, f"nextval('{bare}')")
    return {
        "oracle": f"{seq}.CURRVAL",
        "tsql": (
            "NULL /* UNIQUE: T-SQL has no sequence CURRVAL; capture "
            f"NEXT VALUE FOR {seq} in a variable — see docs/03-unsupported.md */"
        ),
    }.get(dialect, f"currval('{bare}')")


def _emit_json_object_extract(node: FunctionCall, dialect: str) -> str | None:
    """Emit a JSON object-extract (``JSON_EXTRACT``/``JSON_QUERY``/``->``).

    sqlglot models MySQL ``JSON_EXTRACT``/``->``, PG ``->`` and T-SQL/Oracle
    ``JSON_QUERY`` all as ``exp.JSONExtract`` (IR name ``JSON_EXTRACT``). Each
    non-MySQL target needs its own object accessor; the caller has already
    checked ``dialect != "mysql"`` (MySQL keeps native ``JSON_EXTRACT``).
    Returns ``None`` when the source dialect has no object-extract mapping so
    the generic path handles it.
    """
    jx = _emit_expression(node.args[0], dialect)
    jp = _emit_expression(node.args[1], dialect)
    src = SOURCE_DIALECT.get()
    if src == "mysql":
        # MySQL JSON_EXTRACT returns objects/arrays or scalars — T-SQL:
        # JSON_QUERY covers objects, JSON_VALUE scalars, ISNULL of both either.
        if dialect == "tsql":
            return f"ISNULL(JSON_QUERY({jx}, {jp}), JSON_VALUE({jx}, {jp}))"
        if dialect == "oracle":
            return f"JSON_VALUE({jx}, {jp})"
        jm = re.fullmatch(r"'\$\.(\w+)'", jp.strip())
        if jm:
            return f"JSON_EXTRACT_PATH({jx}, '{jm.group(1)}')"
        return f"JSON_EXTRACT_PATH({jx}, {jp})"
    if src in ("tsql", "oracle"):
        # T-SQL/Oracle JSON_QUERY is object extraction. Oracle and T-SQL have
        # JSON_QUERY natively; PostgreSQL has no such function — route through
        # the SQL/JSON path engine (the same lowering the JSON_QUERY builtin
        # uses). Emitting a bare JSON_EXTRACT shipped an executable call to
        # engines that lack it (N12/B13 follow-up).
        if dialect in ("tsql", "oracle"):
            return f"JSON_QUERY({jx}, {jp})"
        return f"JSONB_PATH_QUERY_FIRST(CAST({jx} AS JSONB), {jp})"
    return None


def _emit_bool_agg(node: FunctionCall, fn_name: str, dialect: str) -> str | None:
    """Boolean aggregate (bool_or/bool_and/every) per target, or None.

    PG bool_or/bool_and/every canonicalize to LOGICAL_OR/LOGICAL_AND — no other
    engine has them. MySQL booleans are 0/1, so MAX/MIN aggregate them directly;
    T-SQL's bit is not a valid MAX operand and needs CAST(… AS INT); Oracle
    aggregates a 1/0 CASE over the boolean.
    """
    if fn_name not in ("LOGICAL_OR", "BOOL_OR", "LOGICAL_AND", "BOOL_AND", "EVERY") or (
        len(node.args) != 1
    ):
        return None
    arg = _emit_expression(node.args[0], dialect)
    agg = "MAX" if fn_name in ("LOGICAL_OR", "BOOL_OR") else "MIN"
    filtered = _bool_agg_filter_arg(node.args[0], agg, dialect)
    if filtered is not None:
        return filtered
    if dialect == "tsql":
        inner = node.args[0]
        if isinstance(inner, BinaryOp) and inner.operator in _COMPARISON_OPS:
            # A predicate is not a value on T-SQL — wrap tri-state.
            arg = f"CASE WHEN {arg} THEN 1 WHEN NOT ({arg}) THEN 0 END"
        elif isinstance(inner, UnaryOp) and inner.operator == UnaryOperator.NOT:
            operand = _emit_expression(inner.operand, dialect)
            arg = f"CASE WHEN {operand} = 0 THEN 1 " f"WHEN {operand} <> 0 THEN 0 END"
        return f"{agg}(CAST({arg} AS INT))"
    if dialect == "mysql":
        return f"{agg}({arg})"
    if dialect == "oracle":
        return f"{agg}(CASE WHEN {arg} THEN 1 ELSE 0 END)"
    return f"{'BOOL_OR' if agg == 'MAX' else 'BOOL_AND'}({arg})"


#: Oracle cannot store an empty string apart from NULL — the documented
#: empty-string limit (docs/03-unsupported.md).
_ORACLE_EMPTY = (
    "'' /* UNIQUE: Oracle stores an empty string as NULL (docs/03-unsupported.md) */"
)


def _empty_string_result(dialect: str) -> str:
    """The empty-string value per target: '' everywhere, a warned carrier on
    Oracle (which folds '' to NULL)."""
    return {"oracle": _ORACLE_EMPTY}.get(dialect, "''")


def _bool_agg_filter_arg(arg_node: ASTNode, agg: str, dialect: str) -> str | None:
    """Boolean aggregate over a FILTER-lowered CASE, for T-SQL/Oracle.

    ``bool_or(x) FILTER (WHERE c)`` lowers to ``bool_or(CASE WHEN c THEN x END)``.
    On T-SQL/Oracle the boolean THEN-value ``x`` is not a value type, so wrap each
    predicate THEN in the 1/0 form — the CASE then yields an int the MAX/MIN
    aggregate takes directly (challenge pg-boolagg-filter). Returns None (MySQL/PG
    take the boolean as-is, and non-FILTER args fall through to the caller).
    """
    if (
        dialect not in ("tsql", "oracle")
        or not isinstance(arg_node, CaseExpression)
        or not any(_is_predicate_node(v) for _, v in arg_node.whens)
    ):
        return None
    one = Literal(value=1, dtype="integer")
    zero = Literal(value=0, dtype="integer")
    wrapped = tuple(
        (
            (c, CaseExpression(whens=((v, one),), else_expr=zero))
            if _is_predicate_node(v)
            else (c, v)
        )
        for c, v in arg_node.whens
    )
    rebuilt = dataclasses.replace(arg_node, whens=wrapped)
    return f"{agg}({_emit_expression(rebuilt, dialect)})"


def _widen_round_operand(operand: ASTNode, emitted: str) -> str:
    """Widen a bare fractional-literal ROUND operand for T-SQL.

    T-SQL types ``0.5`` as numeric(1,1) and ROUND preserves that precision/scale,
    so rounding to an integer OVERFLOWS (error 8115). Casting a fractional-literal
    operand to a wide DECIMAL leaves room for the rounded integer digit (challenge
    pg-round-bare-half-literal). A non-literal operand keeps its declared type.
    """
    if (
        isinstance(operand, Literal)
        and isinstance(operand.value, float)
        and operand.value != int(operand.value)
    ):
        return f"CAST({emitted} AS DECIMAL(38, 6))"
    return emitted


def _emit_substr_neg_start(
    node: FunctionCall, fn_name: str, dialect: str
) -> str | None:
    """SUBSTRING(s, start, len) with a start < 1 into Oracle/MySQL.

    PostgreSQL and T-SQL count out-of-range leading positions toward the length
    (``SUBSTRING('hello', 0, 3)`` = 'he'; ``SUBSTRING('abcde' FROM -2 FOR 2)`` =
    ''); Oracle clamps 0 to 1 / reads a negative start from the END, MySQL
    returns '' for start 0 / counts a negative start from the END. Reproduce the
    source semantics with a 1-based start and an adjusted length (start+len-1).
    The start may be a non-positive Literal (0, -2) or a negated Literal (``-2``
    parses as UnaryOp NEGATIVE). Covers pg-substring-neg-from-for and
    reda-ts-substring-zero-start; returns None when it does not apply.
    """
    if (
        fn_name != "SUBSTRING"
        or len(node.args) != 3
        or dialect not in ("oracle", "mysql")
        or SOURCE_DIALECT.get() not in ("postgresql", "tsql")
    ):
        return None
    s1 = node.args[1]
    if (
        isinstance(s1, Literal)
        and isinstance(s1.value, int)
        and not isinstance(s1.value, bool)
        and s1.value <= 0
    ):
        neg_start = s1.value
    elif (
        isinstance(s1, UnaryOp)
        and s1.operator == UnaryOperator.NEGATIVE
        and isinstance(s1.operand, Literal)
        and isinstance(s1.operand.value, int)
        and not isinstance(s1.operand.value, bool)
    ):
        neg_start = -s1.operand.value
    else:
        return None
    s = _emit_expression(node.args[0], dialect)
    if isinstance(node.args[2], Literal) and isinstance(node.args[2].value, int):
        adj_val = node.args[2].value + neg_start - 1  # fold to a constant
        if adj_val > 0:
            return f"SUBSTR({s}, 1, {adj_val})"
        # The run lies entirely before position 1 -> empty result (Oracle
        # cannot store '' apart from NULL -> documented empty-string limit).
        return _empty_string_result(dialect)
    length = _emit_expression(node.args[2], dialect)
    return f"SUBSTR({s}, 1, GREATEST({length} + ({neg_start - 1}), 0))"


def _emit_function(node: FunctionCall, dialect: str) -> str:
    """Emit a function call."""
    fn_name = node.name.upper()
    # Compile-time folds over literal arguments: the value each SOURCE engine
    # computes is emitted directly, sidestepping per-target semantic gaps
    # (LEN/LENGTH counting units, Oracle INSTR occurrence/backward search).
    if fn_name == "LENGTH":
        folded = _fold_length_literal(node)
        if folded is not None:
            return folded
        # MySQL LENGTH/CHAR_LENGTH share this IR name, so a non-ASCII MySQL
        # literal cannot fold (bytes vs chars is ambiguous). T-SQL LEN counts a
        # surrogate pair as TWO; a supplementary-character (_SC) collation makes
        # it count code points — the CHAR_LENGTH semantics every other engine
        # has. (A genuine byte-count LENGTH is already [limit]-annotated.)
        if (
            dialect == "tsql"
            and len(node.args) == 1
            and isinstance(node.args[0], Literal)
            and isinstance(node.args[0].value, str)
            and any(ord(c) > 0xFFFF for c in node.args[0].value)
        ):
            _sc = node.args[0].value.replace("'", "''")
            return f"LEN(N'{_sc}' COLLATE Latin1_General_100_CI_AS_SC)"
    if (
        fn_name == "CHARINDEX"
        and SOURCE_DIALECT.get() == "oracle"
        and (
            len(node.args) == 4
            or (
                len(node.args) == 3
                and isinstance(node.args[2], UnaryOp)
                and node.args[2].operator == UnaryOperator.NEGATIVE
            )
        )
    ):
        folded = _fold_oracle_instr(node)
        if folded is not None:
            return folded
        if dialect == "oracle":
            # Native re-spell: INSTR(haystack, needle, start[, occurrence]).
            _in = [_emit_expression(a, dialect) for a in node.args]
            return f"INSTR({_in[1]}, {_in[0]}, {', '.join(_in[2:])})"
        return (
            "NULL /* UNIQUE: Oracle INSTR with an occurrence count or "
            "backward (negative-start) search has no portable equivalent "
            "for non-literal arguments — see docs/03-unsupported.md */"
        )
    # A parameterless aggregate call is invalid on every engine — PG's own
    # error says "count(*) must be used"; that IS the faithful spelling.
    if fn_name == "COUNT" and not node.args and not node.distinct:
        return "COUNT(*)"
    # An ANSI ``DATE '…'`` literal (sqlglot's DATE_STR_TO_DATE wrapper) must keep
    # its date typing — unwrapping it to the bare string (below) drops the type,
    # so a value flowing into date arithmetic downstream (e.g. as a derived-table
    # projection feeding ``d1 - d2``) becomes text-minus-text (PG error). Emit the
    # target's date literal instead.
    if fn_name == "DATE_STR_TO_DATE":
        _dl = _date_literal_sql(node, dialect)
        if _dl is not None:
            return _dl
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
    # The reverse: a MySQL-source GREATEST/LEAST over ASCII string literals
    # compares case-insensitively (GREATEST('a','B') = 'B'); PG/Oracle compare
    # by code point ('a'). All-literal arguments fold to MySQL's answer —
    # skipped on a case-insensitive tie, where MySQL's pick is unspecified.
    if (
        fn_name in ("GREATEST", "LEAST")
        and SOURCE_DIALECT.get() == "mysql"
        and dialect in ("postgresql", "oracle")
        and len(node.args) > 1
        and all(
            isinstance(a, Literal) and isinstance(a.value, str) and a.value.isascii()
            for a in node.args
        )
    ):
        _vals = [cast(Literal, a).value for a in node.args]
        _keys = [str(v).lower() for v in _vals]
        if len(set(_keys)) == len(_keys):
            _pick = (max if fn_name == "GREATEST" else min)(
                _vals, key=lambda v: str(v).lower()
            )
            return "'" + str(_pick).replace("'", "''") + "'"

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
        # PG's ascii() returns the Unicode code point; Oracle ASCII of a multibyte
        # character returns its raw encoding (ASCII('é') = 50089, not 233), so read
        # the code point through the national charset (ASCII(TO_NCHAR(x)) = 233).
        if SOURCE_DIALECT.get() == "postgresql":
            return f"COALESCE(ASCII(TO_NCHAR({_asc_x})), 0)"
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
        # MySQL/PG REPEAT return '' for a negative count; T-SQL REPLICATE
        # truncates a float and returns NULL for a negative one. Round (T-SQL
        # ROUND needs an explicit scale — error 189) and clamp to 0, skipping a
        # provably integer non-negative literal (challenge pg-repeat-negative).
        if SOURCE_DIALECT.get() in (
            "mysql",
            "postgresql",
        ) and not _is_nonneg_int_literal(node.args[1]):
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
    # last |n|" (LEFT('abc', -1) = 'ab'); MySQL returns '' for a negative
    # length, and T-SQL/Oracle error/NULL on it. Reproduce PostgreSQL's
    # semantics with a clamped length: LEFT(s, max(len(s) + n, 0)).
    if (
        fn_name == "LEFT"
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect != "postgresql"
        and len(node.args) == 2
        and isinstance(node.args[1], UnaryOp)
        and node.args[1].operator == UnaryOperator.NEGATIVE
    ):
        _lf_s = _emit_expression(node.args[0], dialect)
        _lf_n = _emit_expression(node.args[1], dialect)
        if dialect == "tsql":
            _lf_len = f"LEN({_lf_s}) + {_lf_n}"
            return f"LEFT({_lf_s}, CASE WHEN {_lf_len} > 0 THEN {_lf_len} ELSE 0 END)"
        if dialect == "oracle":
            return f"SUBSTR({_lf_s}, 1, GREATEST(LENGTH({_lf_s}) + {_lf_n}, 0))"
        return f"LEFT({_lf_s}, GREATEST(CHAR_LENGTH({_lf_s}) + {_lf_n}, 0))"
    # PostgreSQL RIGHT with a negative length is "all but the FIRST |n|"
    # (RIGHT('hello', -1) = 'ello'); MySQL returns '' and T-SQL errors on a
    # negative length. That is a substring from position |n|+1 (naturally ''
    # when |n| >= length).
    if (
        fn_name == "RIGHT"
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect != "postgresql"
        and len(node.args) == 2
        and isinstance(node.args[1], UnaryOp)
        and node.args[1].operator == UnaryOperator.NEGATIVE
        and isinstance(node.args[1].operand, Literal)
    ):
        _rt_s = _emit_expression(node.args[0], dialect)
        _rt_from = int(node.args[1].operand.value) + 1
        if dialect == "tsql":
            return f"SUBSTRING({_rt_s}, {_rt_from}, LEN({_rt_s}))"
        return f"SUBSTR({_rt_s}, {_rt_from})"
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
    # MySQL SUBSTRING with a start of 0 is '' by design; PG would return the
    # whole string and Oracle would clamp 0 to 1. Preserve the empty string.
    if (
        fn_name == "SUBSTRING"
        and dialect != "mysql"
        and SOURCE_DIALECT.get() == "mysql"
        and len(node.args) in (2, 3)
        and isinstance(node.args[1], Literal)
        and node.args[1].value == 0
        and not isinstance(node.args[1].value, bool)
    ):
        if dialect == "oracle":
            # Oracle cannot represent '' apart from NULL — the approved limit.
            return (
                "'' /* UNIQUE: Oracle stores an empty string as NULL "
                "(docs/03-unsupported.md) */"
            )
        return "''"
    # PostgreSQL 2-arg SUBSTRING with a start <= 0 runs from the beginning
    # (virtual positions only shorten a 3-arg length, handled below); MySQL
    # would return ''/count from the end and Oracle counts a negative start
    # from the end. Rewrite to an explicit start of 1.
    if (
        fn_name == "SUBSTRING"
        and dialect != "postgresql"
        and SOURCE_DIALECT.get() == "postgresql"
        and len(node.args) == 2
        and (
            (
                isinstance(node.args[1], Literal)
                and isinstance(node.args[1].value, int)
                and not isinstance(node.args[1].value, bool)
                and node.args[1].value <= 0
            )
            or (
                isinstance(node.args[1], UnaryOp)
                and node.args[1].operator == UnaryOperator.NEGATIVE
                and isinstance(node.args[1].operand, Literal)
            )
        )
    ):
        _z_s = _emit_expression(node.args[0], dialect)
        if dialect == "tsql":
            return f"SUBSTRING({_z_s}, 1, LEN({_z_s}))"
        return f"SUBSTR({_z_s}, 1)"
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
    _neg_substr = _emit_substr_neg_start(node, fn_name, dialect)
    if _neg_substr is not None:
        return _neg_substr
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

    bool_agg = _emit_bool_agg(node, fn_name, dialect)
    if bool_agg is not None:
        return bool_agg

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
        # EXTRACT(field FROM <interval literal>) folds at compile time: the
        # interval-literal cast degrades to a text carrier off PG, which no
        # engine can EXTRACT from — but the value is statically known.
        _iv_arg = node.args[1]
        if (
            isinstance(_iv_arg, CastExpression)
            and _iv_arg.target_type.name.split("(")[0].strip().upper() == "INTERVAL"
            and isinstance(_iv_arg.expression, Literal)
            and isinstance(_iv_arg.expression.value, str)
        ):
            _iv_fields = {
                m.group(2).rstrip("s").upper(): int(m.group(1))
                for m in re.finditer(
                    r"(-?\d+)\s*(year|mon|month|week|day|hour|min|minute|sec|second)s?",
                    _iv_arg.expression.value,
                    re.I,
                )
            }
            _iv_want = (
                {"DAYS": "DAY", "HOURS": "HOUR", "YEARS": "YEAR"}
                .get(part, part)
                .rstrip("S")
            )
            if _iv_fields and _iv_want in (
                "YEAR",
                "MONTH",
                "DAY",
                "HOUR",
                "MINUTE",
                "SECOND",
            ):
                return str(_iv_fields.get(_iv_want, 0))
        value = _emit_expression(node.args[1], dialect)
        # MySQL's compound EXTRACT units (YEAR_MONTH -> YYYYMM, DAY_SECOND ->
        # DDHHMMSS, …) concatenate the component fields into one number; no other
        # engine has them (error 155 / ORA / PG). Rebuild the value from the
        # component fields with the same positional weights.
        _compound = {
            "YEAR_MONTH": [("YEAR", 100), ("MONTH", 1)],
            "DAY_HOUR": [("DAY", 100), ("HOUR", 1)],
            "DAY_MINUTE": [("DAY", 10000), ("HOUR", 100), ("MINUTE", 1)],
            "DAY_SECOND": [
                ("DAY", 1000000),
                ("HOUR", 10000),
                ("MINUTE", 100),
                ("SECOND", 1),
            ],
            "HOUR_MINUTE": [("HOUR", 100), ("MINUTE", 1)],
            "HOUR_SECOND": [("HOUR", 10000), ("MINUTE", 100), ("SECOND", 1)],
            "MINUTE_SECOND": [("MINUTE", 100), ("SECOND", 1)],
        }
        if part in _compound and dialect != "mysql":

            def _field(fld: str) -> str:
                if dialect == "tsql":
                    return f"DATEPART({fld}, {value})"
                return f"EXTRACT({fld} FROM {value})"

            terms = [
                f"{_field(f)} * {m}" if m != 1 else _field(f)
                for f, m in _compound[part]
            ]
            return "(" + " + ".join(terms) + ")"
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
            # EXTRACT(EPOCH FROM interval) is the interval's total seconds — a
            # different computation, and T-SQL/MySQL have no interval value type
            # to carry it — so degrade an interval argument to a carrier.
            if value.strip().upper().startswith("INTERVAL"):
                return (
                    "NULL /* UNIQUE: EXTRACT(EPOCH FROM interval) has no portable "
                    "equivalent (T-SQL/MySQL have no interval value type) — "
                    "see docs/03-unsupported.md */"
                )
            # Unix epoch seconds. PG's EPOCH for a timestamp WITHOUT time zone is
            # the literal difference from 1970-01-01 00:00:00 — no session-tz
            # conversion — so use a literal date-diff (not UNIX_TIMESTAMP, which
            # would shift by the session offset).
            if dialect == "oracle":
                return f"((CAST({value} AS DATE) - DATE '1970-01-01') * 86400)"
            if dialect == "tsql":
                return f"DATEDIFF_BIG(SECOND, '1970-01-01', {value})"
            if dialect == "mysql":
                return f"TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', {value})"
            return f"EXTRACT(EPOCH FROM {value})"
        if part == "MICROSECONDS":
            # PG's MICROSECONDS is the whole seconds field including its fraction,
            # times 1e6 (so 30.123456s -> 30123456). MySQL/T-SQL only expose the
            # sub-second MICROSECOND, so add SECOND*1e6. Oracle has no TIME type
            # (nor a MICROSECONDS extract), so it degrades to a carrier.
            if dialect == "tsql":
                return (
                    f"(DATEPART(SECOND, {value}) * 1000000 + "
                    f"DATEPART(MICROSECOND, {value}))"
                )
            if dialect == "mysql":
                return f"(SECOND({value}) * 1000000 + MICROSECOND({value}))"
            return (
                "NULL /* UNIQUE: EXTRACT(MICROSECONDS FROM TIME) has no Oracle "
                "equivalent (no TIME type) — see docs/03-unsupported.md */"
            )
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
            not all(c in ("s", "I", "%") for c in specs)
            or sum(1 for c in specs if c in ("s", "I")) != len(node.args) - 1
        ):
            return (
                "NULL /* UNIQUE: PG format() with %L/width/positional "
                "specifiers has no cross-engine equivalent — "
                "see docs/03-unsupported.md */"
            )

        def _quoted_ident(arg_sql: str) -> str:
            # %I: the argument as a QUOTED IDENTIFIER in the target's dialect.
            if dialect == "tsql":
                return f"QUOTENAME({arg_sql})"
            if dialect == "mysql":
                return f"CONCAT('`', REPLACE({arg_sql}, '`', '``'), '`')"
            return f"'\"' || REPLACE({arg_sql}, '\"', '\"\"') || '\"'"

        fmt_args = [_emit_expression(a, dialect) for a in node.args[1:]]
        fmt_parts = re.split(r"%([sI])", tmpl)
        pieces: list[str] = []
        _ai = 0
        for i, part in enumerate(fmt_parts):
            if i % 2 == 1:  # a captured spec letter
                arg_sql = fmt_args[_ai]
                pieces.append(_quoted_ident(arg_sql) if part == "I" else arg_sql)
                _ai += 1
                continue
            lit = part.replace("%%", "%")
            if lit:
                pieces.append("'" + lit.replace("'", "''") + "'")
        if not pieces:
            return "''"
        if len(pieces) == 1:
            return pieces[0]
        if dialect == "oracle":
            return " || ".join(pieces)
        return f"CONCAT({', '.join(pieces)})"

    # md5(x) -> a 32-char lowercase hex digest. PG and MySQL have it natively;
    # Oracle spells it STANDARD_HASH(x, 'MD5') and T-SQL HASHBYTES('MD5', x), both
    # returning binary that a hex CONVERT/UPPER renders to the same digest.
    if fn_name == "MD5" and len(node.args) == 1 and dialect in ("oracle", "tsql"):
        _md = _emit_expression(node.args[0], dialect)
        if dialect == "oracle":
            return f"LOWER(STANDARD_HASH({_md}, 'MD5'))"
        return f"LOWER(CONVERT(VARCHAR(32), HASHBYTES('MD5', {_md}), 2))"

    # PG sha224/256/384/512(bytea) — sqlglot canonicalises to SHA2(x, n) — return
    # a bytea digest; the other engines yield a hex string (Oracle STANDARD_HASH,
    # T-SQL HASHBYTES, MySQL SHA2), so the value is the same digest in a different
    # representation (binary vs hex). Degrade rather than claim equality.
    if (
        fn_name == "SHA2"
        and SOURCE_DIALECT.get() == "postgresql"
        and dialect != "postgresql"
    ):
        return (
            "NULL /* UNIQUE: PG sha256/sha512 returns a bytea digest; other engines "
            "return a hex string (same digest, different representation) — "
            "see docs/03-unsupported.md */"
        )

    # GROUPING(x) under a degraded MySQL CUBE/GROUPING SETS folds to 0 at the
    # SELECT level (_emit_select), where the grouping modifier is known —
    # native WITH ROLLUP keeps the real call here.

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
        # Oracle DECODE coerces every result (and the default) to the FIRST
        # result's datatype. PostgreSQL instead resolves the CASE to a single
        # common type and rejects a text branch mixed with a numeric ELSE
        # (DECODE(1,1,'a',...,99) -> 'invalid input syntax for type integer').
        # When the first result is a string literal, cast numeric-literal
        # result/default branches to text to mirror Oracle's coercion.
        _first_result = node.args[2] if len(node.args) >= 3 else None
        _coerce_text = (
            dialect == "postgresql"
            and isinstance(_first_result, Literal)
            and str(getattr(_first_result, "dtype", "")) == "string"
        )

        def _result(idx: int) -> str:
            _n = node.args[idx]
            if (
                _coerce_text
                and isinstance(_n, Literal)
                and str(_n.dtype) in ("integer", "number", "float", "double")
            ):
                return f"CAST({parts[idx]} AS TEXT)"
            return parts[idx]

        while i + 1 < len(parts):
            # Oracle DECODE uses NULL-safe equality (NULL matches NULL), unlike
            # SQL '=' where NULL = NULL is unknown. A NULL search matches exactly
            # when the subject IS NULL.
            _dc_search = node.args[i]
            if isinstance(_dc_search, Literal) and _dc_search.value is None:
                cond = f"{subject} IS NULL"
            else:
                cond = f"{subject} = {parts[i]}"
            whens.append(f"WHEN {cond} THEN {_result(i + 1)}")
            i += 2
        default = f" ELSE {_result(i)}" if i < len(parts) else ""
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
            # Style 126 (ISO8601): the literal 'T' separator must be quoted in
            # an Oracle mask, and the python %f fraction is FF3 — which needs a
            # TIMESTAMP value (FF on a DATE is ORA-01821).
            ora = re.sub(r"(?<=D)T(?=H)", '"T"', ora)
            if "%f" in ora:
                ora = ora.replace(".%f", ".FF3").replace("%f", "FF3")
            if to_string:
                if "FF" in ora:
                    value = f"CAST({value} AS TIMESTAMP)"
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
                # Oracle TRUNC format codes are NOT the source spelling: 'WEEK'
                # (ORA-01898), 'QUARTER'/'MINUTE' (ORA-01821) are all rejected.
                # Map each unit to Oracle's valid code — 'IW' is the ISO
                # (Monday-based) week, matching PG's date_trunc('week').
                ora_fmt = {
                    "month": "MM",
                    "year": "YYYY",
                    "quarter": "Q",
                    "week": "IW",
                    "hour": "HH24",
                    "minute": "MI",
                }[trunc_part]
                return f"TRUNC({value}, '{ora_fmt}')"
            if dialect == "tsql":
                # CAST AS DATE works on every supported version; DATETRUNC
                # (2022+) covers the other parts. PG's week is ISO (Monday);
                # T-SQL DATETRUNC(week) is Sunday-based, so use ISO_WEEK to
                # return the same Monday start.
                if trunc_part == "day":
                    return f"CAST({value} AS DATE)"
                ts_part = "ISO_WEEK" if trunc_part == "week" else trunc_part
                return f"DATETRUNC({ts_part}, {value})"
            if dialect == "mysql":
                if trunc_part == "day":
                    return f"DATE({value})"
                if trunc_part == "month":
                    return f"DATE_FORMAT({value}, '%Y-%m-01')"
                if trunc_part == "year":
                    return f"DATE_FORMAT({value}, '%Y-01-01')"
                if trunc_part == "week":
                    # ISO/Monday week start (WEEKDAY: Monday=0), matching PG.
                    return (
                        f"DATE_SUB(DATE({value}), INTERVAL WEEKDAY(DATE({value})) DAY)"
                    )
                if trunc_part == "quarter":
                    return (
                        f"MAKEDATE(YEAR({value}), 1) + "
                        f"INTERVAL (QUARTER({value}) - 1) QUARTER"
                    )
                # hour/minute have no faithful MySQL date-truncation spelling —
                # fall through to the warned validity-gate degrade.

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

    if fn_name == "JSON_EXTRACT" and len(node.args) == 2 and dialect != "mysql":
        _je = _emit_json_object_extract(node, dialect)
        if _je is not None:
            return _je

    # GROUPING_ID(a, b) is Oracle/T-SQL spelling; PG and MySQL expose the SAME
    # bitmask as multi-argument GROUPING(a, b) (live-verified 0/1/3 on both).
    if fn_name == "GROUPING_ID" and dialect in ("postgresql", "mysql") and node.args:
        _gid = ", ".join(_emit_expression(a, dialect) for a in node.args)
        return f"GROUPING({_gid})"

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
    seq_call = _emit_sequence_call(node, dialect)
    if seq_call is not None:
        return seq_call
    if (
        up == "CHR"
        and len(node.args) == 1
        and SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
        and isinstance(node.args[0], Literal)
        and isinstance(node.args[0].value, int)
        and node.args[0].value > 255
    ):
        # MySQL CHAR(n) is byte-based: n > 255 yields a multi-byte BYTE STRING
        # (CHAR(256) = bytes 0x01 0x00), not the single code point CHR gives
        # elsewhere. The value is computable now: decode the bytes as utf8mb4 —
        # an invalid sequence is NULL (what MySQL itself returns).
        _n = node.args[0].value
        _bts = _n.to_bytes(max((_n.bit_length() + 7) // 8, 1), "big")
        try:
            _chr_val: str | None = _bts.decode("utf-8")
        except UnicodeDecodeError:
            _chr_val = None
        if _chr_val is None:
            return "NULL"  # what MySQL itself returns for an invalid sequence
        if not any(ord(c) < 0x20 for c in _chr_val):
            return "'" + _chr_val.replace("'", "''") + "'"
        # Control/NUL bytes (CHAR(256) = 0x01 0x00) cannot live in a string
        # literal on PG/Oracle — keep the documented carrier.
        return (
            f"CHR({_n}) /* UNIQUE: MySQL CHAR({_n}) is a multi-byte byte string, "
            "not a single code point (docs/03-unsupported.md) */"
        )
    if (
        up == "CHR"
        and len(node.args) == 1
        and dialect == "oracle"
        and SOURCE_DIALECT.get() == "postgresql"
        and isinstance(node.args[0], Literal)
        and isinstance(node.args[0].value, int)
        and node.args[0].value > 127
    ):
        # PG CHR(n) is a Unicode code point; Oracle CHR(n) for n > 127 returns a
        # raw byte (invalid in an AL32UTF8 DB), so use NCHR (national code point).
        return f"NCHR({node.args[0].value})"
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
        # A ``0x…`` literal argument is an INTEGER code point, not a byte string —
        # resolve it so the emitted call receives the number, not hex bytes.
        nchar_arg = node.args[0]
        cp: int | None = None
        if isinstance(nchar_arg, Literal):
            if nchar_arg.dtype == "hex" and isinstance(nchar_arg.value, str):
                cp = int(nchar_arg.value, 16)
            elif isinstance(nchar_arg.value, int):
                cp = nchar_arg.value
        if cp is not None:
            if dialect == "postgresql":
                return f"CHR({cp})"
            if dialect == "mysql":
                # utf32 reads the number as a code point (BMP and supplementary).
                return f"CHAR({cp} USING utf32)"
            if cp > 0xFFFF:
                # Oracle NCHR only covers the BMP (it truncates a supplementary
                # code point to 16 bits); build the UTF-16 surrogate pair and let
                # UNISTR assemble the character.
                hi = 0xD800 + ((cp - 0x10000) >> 10)
                lo = 0xDC00 + ((cp - 0x10000) & 0x3FF)
                return f"UNISTR('\\{hi:04X}\\{lo:04X}')"
            return f"NCHR({cp})"
        n = _emit_expression(nchar_arg, dialect)
        if dialect == "oracle":
            return f"NCHR({n})"
        if dialect == "postgresql":
            return f"CHR({n})"
        return f"CHAR({n} USING utf32)"  # mysql
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
        # A provably-negative count is '' on PG/MySQL; Oracle cannot store an
        # empty string apart from NULL — emit the documented empty-string limit
        # (challenge pg-repeat-negative). RPAD with a clamped length keeps a
        # non-literal count safe (negative -> 0 -> NULL, Oracle's '').
        _n_arg = node.args[1]
        if (
            isinstance(_n_arg, UnaryOp)
            and _n_arg.operator == UnaryOperator.NEGATIVE
            and isinstance(_n_arg.operand, Literal)
        ):
            return _ORACLE_EMPTY
        n = _emit_expression(_n_arg, dialect)
        if _is_nonneg_int_literal(_n_arg):
            return (
                f"RPAD({s}, LENGTH({s}) * {n}, {s})"  # exact, incl. n=0 -> '' (NULL).
            )
        # A non-literal count may be negative at runtime; clamp so it yields ''.
        return f"RPAD({s}, GREATEST(LENGTH({s}) * {n}, 0), {s})"
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
        args = _widen_round_operand(node.args[0], args) + ", 0"
    # NOTE (P1 silent-output): a FunctionCall-level gap note here broke
    # the downstream text handlers that consume this output (TRUNC→ROUND
    # on the M4 path) — the M3 lesson. The unmapped-operator note lives
    # on the RawSQL branch instead; FunctionCall-modeled foreigners are
    # handled by their dedicated downstream handlers.
    return f"{name}({distinct}{args})"


# Cross-family imports at the tail (after the defs above) so the mutually
# recursive emit-family modules resolve without namespace injection — see
# emit.py's module docstring.
from unique.core.converter.emit import (  # noqa: E402
    _COMPARISON_OPS,
    _PG_FUNCTION_CASTS,
    _STAT_AGGREGATE_MAP,
    _as_datetime_literal,
    _convert_date_format,
    _date_fmt_reproducible,
    _emit_condition,
    _is_predicate_node,
    _number_mask_spec,
    _oracle_number_mask,
    _plain_int_value,
    _portable_types_in_sql,
)
from unique.core.converter.emit_expr import (  # noqa: E402
    _date_literal_sql,
    _emit_expression,
    _is_date_only_literal,
    _is_integer_operand,
    _is_nonneg_int_literal,
    _is_nonneg_literal,
)
