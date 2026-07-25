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

from unique.core.ast_nodes import (
    Alias,
    ArrayLiteral,
    ASTNode,
    BinaryOp,
    BinaryOperator,
    CaseExpression,
    CastExpression,
    ColumnRef,
    DataType,
    ExcludedColumn,
    ExpressionList,
    FunctionCall,
    Literal,
    PassthroughSQL,
    RawSQL,
    SelectStatement,
    Star,
    SubqueryExpression,
    TableRef,
    UnaryOp,
    UnaryOperator,
    UnsupportedInline,
    WindowFunction,
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
    DML_FOUND_EXPR,
    ERROR_DIAGNOSTIC_EXPRS,
    ERROR_DIAGNOSTIC_SOURCES,
    ERROR_MESSAGE_EXPR,
    ERROR_MESSAGE_SOURCES,
)

# NOTE: moved verbatim from emit.py (audit doc 04 F4 split). Cross-seam
# and emit.py helpers are referenced by bare name and resolved at call time
# via the namespace injection emit.py performs after importing every seam.

__all__ = [
    "_emit_expression",
    "_ORACLE_BITWISE",
    "_BIN_PRECEDENCE",
    "_BITWISE_BIN_OPS",
    "_ARITH_BIN_OPS",
    "_NON_ASSOCIATIVE",
    "_emit_operand",
    "_is_integer_operand",
    "_nullable_string_operand",
    "_is_nonneg_literal",
    "_is_numeric_str_literal",
    "_is_date_only_literal",
    "_is_nonneg_int_literal",
    "_date_literal_sql",
    "_emit_binary",
    "_emit_unary",
    "_emit_case",
    "_emit_window",
]


def _emit_expression(node: ASTNode, dialect: str) -> str:
    """Emit an expression node as SQL text."""
    if isinstance(node, ExcludedColumn):
        return _emit_excluded_column(node, dialect)
    if isinstance(node, UnsupportedInline):
        # Valid on its own engine; a NULL placeholder + carrier + warning
        # elsewhere (the loss is documented, never silently mangled).
        if SOURCE_DIALECT.get() == dialect:
            return node.source_sql
        return (
            f"NULL /* UNIQUE: {node.detail} ({node.source_sql}) — "
            "see docs/03-unsupported.md */"
        )
    if isinstance(node, PassthroughSQL):
        # A passthrough that reached expression position (e.g. a subquery
        # argument to an unknown function). Re-transpile its inner SQL rather
        # than leak the node's Python repr — the invariant is that unhandled
        # fragments degrade to text, never to a mangled object dump.
        return _emit_passthrough(node, dialect)
    if isinstance(node, ColumnRef):
        # plpgsql's bare FOUND flag (statement state, not a column).
        if (
            not node.table
            and node.name.upper() == "FOUND"
            and SOURCE_DIALECT.get() == "postgresql"
        ):
            return DML_FOUND_EXPR.get(dialect, node.name)
        # Oracle's bare SESSIONTIMEZONE global (the session's UTC offset, e.g.
        # '+02:00') — session-dependent, so values cannot match across servers
        # (annotated; the ts-spid-version precedent).
        if (
            not node.table
            and node.name.upper() == "SESSIONTIMEZONE"
            and SOURCE_DIALECT.get() == "oracle"
            and dialect != "oracle"
        ):
            _stz = {
                "postgresql": "current_setting('TimeZone')",
                "mysql": "@@session.time_zone",
                "tsql": "DATENAME(TZOFFSET, SYSDATETIMEOFFSET())",
            }[dialect]
            return (
                f"{_stz} /* UNIQUE: Oracle SESSIONTIMEZONE is session-"
                "dependent; the mapped expression reports this session's "
                "zone/offset in the target's own format "
                "(docs/03-unsupported.md) */"
            )
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
            # PostgreSQL (16+) reads 0x1F as an INTEGER literal (31), not a
            # byte string — every other engine's hex literal is bytes, so a
            # PG-source hex literal must emit its decimal value.
            if SOURCE_DIALECT.get() == "postgresql":
                try:
                    return str(int(str(node.value), 16))
                except ValueError:
                    pass
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
        if node.dtype == "number" and node.raw is not None:
            # A high-precision decimal a float rounded away — emit the exact text.
            return node.raw
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
                # Off-Oracle, CAST(x AS DATE) STRIPS the time of day; Oracle
                # DATE keeps it. TRUNC a time-carrying literal cast to DATE.
                if (
                    node.target_type.name.upper() == "DATE"
                    and SOURCE_DIALECT.get() != "oracle"
                    and lit.upper().startswith("TIMESTAMP")
                ):
                    return f"TRUNC({lit})"
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
        # A hex literal cast to a CHARACTER type is a compile-time byte decode:
        # MySQL decodes per the cast's CHARACTER SET (utf8mb4 default; an
        # invalid sequence is NULL), T-SQL CONVERT(VARCHAR, 0x…) decodes the
        # default collation's cp1252. No engine-side reinterpret needed.
        if (
            isinstance(node.expression, Literal)
            and node.expression.dtype == "hex"
            and SOURCE_DIALECT.get() in ("mysql", "tsql")
            and node.target_type.name.split("(")[0].strip().upper() in _CHAR_CAST_BASES
        ):
            if SOURCE_DIALECT.get() == "tsql":
                _codec: str | None = "cp1252"
            else:
                _cs_m = re.search(r"(?i)CHARACTER\s+SET\s+(\w+)", node.target_type.name)
                _codec = _MYSQL_CHARSET_CODECS.get(
                    _cs_m.group(1).lower() if _cs_m else "utf8mb4"
                )
            if _codec is not None:
                try:
                    _decoded = bytes.fromhex(str(node.expression.value)).decode(_codec)
                except (ValueError, UnicodeDecodeError):
                    return "NULL"
                return "'" + _decoded.replace("'", "''") + "'"
        # The reverse: a string literal cast to VARBINARY is the literal's
        # encoded bytes — emit them as the target's hex literal. VARBINARY
        # only: a fixed BINARY(n) zero-PADS to n bytes, and a sized
        # VARBINARY(n) shorter than the value truncates, so those keep the
        # runtime CAST.
        if (
            isinstance(node.expression, Literal)
            and isinstance(node.expression.value, str)
            and node.expression.dtype in ("string", "national", "unknown")
            and node.target_type.name.split("(")[0].strip().upper() == "VARBINARY"
            and (
                not node.target_type.params
                or not str(node.target_type.params[0]).isdigit()
                or int(node.target_type.params[0])
                >= len(node.expression.value.encode("utf-8", errors="ignore"))
            )
        ):
            _enc = "cp1252" if SOURCE_DIALECT.get() == "tsql" else "utf-8"
            try:
                _bts = node.expression.value.encode(_enc)
            except UnicodeEncodeError:
                _bts = None
            if _bts is not None:
                return _emit_expression(
                    Literal(value=_bts.hex().upper(), dtype="hex"), dialect
                )
        # MySQL binary-ish literals cast to a number fold to their numeric
        # value: a hex literal is a big-endian integer (0xFFFF = 65535), a bit
        # literal b'1111' is base 2 (15), a boolean is 1/0 — the emitted forms
        # (bytea/bit-string/boolean) cannot be cast to a number elsewhere.
        if (
            SOURCE_DIALECT.get() == "mysql"
            and dialect != "mysql"
            and (
                node.target_type.name.split("(")[0].strip().upper()
                in _NUMERIC_CAST_TYPES
                or node.target_type.name.split("(")[0].strip().upper().startswith("U")
            )
        ):
            _mnum: int | None = None
            _mexp = node.expression
            if isinstance(_mexp, Literal) and _mexp.dtype == "hex":
                try:
                    _mnum = int(str(_mexp.value), 16)
                except ValueError:
                    _mnum = None
            elif isinstance(_mexp, Literal) and _mexp.dtype == "boolean":
                _mnum = 1 if _mexp.value else 0
            elif isinstance(_mexp, RawSQL):
                _mbit = re.fullmatch(r"(?i)\s*b'([01]+)'\s*", _mexp.sql)
                if _mbit:
                    _mnum = int(_mbit.group(1), 2)
            if _mnum is not None:
                return _emit_expression(
                    dataclasses.replace(
                        node,
                        expression=Literal(value=_mnum, dtype="integer"),
                    ),
                    dialect,
                )
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
        if (
            mapped
            and dialect == "oracle"
            and dtype.upper() == "CLOB"
            and IR_EMBEDDED.get()
        ):
            # Inside a PL/SQL body ``CAST(x AS CLOB)`` is valid but
            # ``CAST(x AS VARCHAR2(4000))`` is not (PLS-00103) — the exact reverse
            # of a top-level SQL statement (ORA-22849 on CLOB). The CLOB->VARCHAR2
            # remap is for the SQL engine; keep CLOB in a procedural body.
            mapped = None
        if mapped:
            dtype = mapped
            # A mapped character type keeps its length (Oracle rejects a
            # lengthless character CAST, ORA-00906); the others (SIGNED,
            # TIMESTAMP, BIT) take none.
            if node.target_type.params and mapped in ("VARCHAR2", "NVARCHAR2", "CHAR"):
                dtype += f"({', '.join(str(p) for p in node.target_type.params)})"
        elif node.target_type.params:
            dtype += f"({', '.join(str(p) for p in node.target_type.params)})"
        # A LENGTHLESS VARCHAR2 CAST is ORA-00906 in a SQL statement (but the
        # only valid form inside a PL/SQL expression — the CLOB lesson): give
        # the SQL-context cast the maximum length.
        if (
            dialect == "oracle"
            and not IR_EMBEDDED.get()
            and dtype.upper() in ("VARCHAR2", "NVARCHAR2", "VARCHAR", "NVARCHAR")
        ):
            dtype += "(4000)"
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
            # An INTEGER literal wider than the (38,10) default's 28 integer
            # digits would overflow it — size the type to the literal.
            _int_lit = node.expression
            if (
                isinstance(_int_lit, Literal)
                and isinstance(_int_lit.value, int)
                and not isinstance(_int_lit.value, bool)
                and len(str(abs(_int_lit.value))) > 28
            ):
                _digits = len(str(abs(int(_int_lit.value))))
                dtype += f"({min(_digits, 65 if dialect == 'mysql' else 38)}, 0)"
            else:
                dtype += "(10, 0)" if SOURCE_DIALECT.get() == "mysql" else "(38, 10)"
        # MySQL DATETIME/TIME default to 0 fractional digits, silently truncating
        # a literal's sub-second part ('…:30.123456' -> '…:30'); keep it with (6)
        # when the value carries a fraction.
        if (
            dialect == "mysql"
            and not node.target_type.params
            and dtype.upper() in ("DATETIME", "TIME")
            and isinstance(node.expression, Literal)
            and isinstance(node.expression.value, str)
            and re.search(r":\d{2}\.\d+", node.expression.value)
        ):
            dtype += "(6)"
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
        # T-SQL CAST(datetime AS INT) is the ROUNDED day count since the
        # 1900-01-01 epoch (no other engine has that implicit conversion).
        if (
            SOURCE_DIALECT.get() == "tsql"
            and dialect != "tsql"
            and _cast_to in ("INT", "INTEGER", "BIGINT", "SMALLINT")
            and isinstance(node.expression, FunctionCall)
            and node.expression.name.upper()
            in ("CURRENT_TIMESTAMP", "GETDATE", "SYSDATETIME", "GETUTCDATE", "NOW")
        ):
            if dialect == "oracle":
                return f"ROUND({inner} - DATE '1900-01-01')"
            if dialect == "postgresql":
                return (
                    f"ROUND(EXTRACT(EPOCH FROM ({inner} - "
                    "TIMESTAMP '1900-01-01')) / 86400)"
                )
            return (
                f"ROUND((TO_SECONDS({inner}) - TO_SECONDS('1900-01-01')) " "/ 86400, 0)"
            )
        # Off-Oracle semantics: CAST(ts AS DATE) strips the time of day
        # (a date-only value); Oracle DATE keeps it (10:30 survives the cast).
        # TRUNC the cast so the value matches — a no-op at midnight.
        if (
            dialect == "oracle"
            and _cast_to == "DATE"
            and SOURCE_DIALECT.get() not in (None, "oracle")
        ):
            return f"TRUNC(CAST({inner} AS DATE))"
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
        if node.on_error_default is not None:
            # Oracle ``CAST(x AS T DEFAULT d ON CONVERSION ERROR)`` returns d when
            # the conversion fails. Dropping the clause silently ships a cast that
            # raises on bad input, so translate the fallback (never lose it).
            default_sql = _emit_expression(node.on_error_default, dialect)
            _oerr_num = dtype.split("(")[0].strip().upper() in _NUMERIC_CAST_TYPES
            # A literal inner is resolvable now — and must be: PG constant-folds
            # the THEN branch of a runtime CASE and raises on a bad constant cast,
            # so no runtime guard can protect a literal. Fold it (as the safe-cast
            # path does): a numeric literal casts cleanly everywhere; a
            # non-numeric one yields the fallback.
            if _oerr_num and isinstance(node.expression, Literal):
                try:
                    float(str(node.expression.value).strip())
                except (TypeError, ValueError):
                    return default_sql
                if dialect == "oracle":
                    return (
                        f"CAST({inner} AS {dtype} DEFAULT {default_sql} "
                        "ON CONVERSION ERROR)"
                    )
                return f"CAST({inner} AS {dtype})"
            if dialect == "oracle":
                return (
                    f"CAST({inner} AS {dtype} DEFAULT {default_sql} "
                    "ON CONVERSION ERROR)"
                )
            if dialect == "tsql":
                # TRY_CAST yields NULL on a failed conversion; COALESCE supplies
                # the Oracle fallback.
                return f"COALESCE(TRY_CAST({inner} AS {dtype}), {default_sql})"
            if _oerr_num:
                # PG/MySQL have no error-safe cast; guard a numeric target with a
                # validation test so a non-numeric value yields the fallback
                # instead of raising. The pattern uses only POSIX classes (no
                # backslashes) so it survives MySQL's string-literal unescaping.
                num_re = "^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$"
                if dialect == "postgresql":
                    guard = f"{inner}::text ~ '{num_re}'"
                else:  # mysql
                    guard = f"CAST({inner} AS CHAR) REGEXP '{num_re}'"
                return (
                    f"CASE WHEN {guard} THEN CAST({inner} AS {dtype}) "
                    f"ELSE {default_sql} END"
                )
            # Non-numeric target with no error-safe cast: keep the valid cast but
            # flag that the fallback was dropped (documented divergence).
            return (
                f"CAST({inner} AS {dtype}) /* UNIQUE: Oracle DEFAULT ... ON "
                f"CONVERSION ERROR has no {dialect} error-safe cast for this "
                "type; fallback dropped -- see docs/03-unsupported.md */"
            )
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
    # NOT binds LOOSER than any comparison/IS operator, so ``(NOT x) IS NULL`` /
    # ``(NOT x) = y`` re-associate to ``NOT (x IS NULL)`` without parens (the
    # source Paren the IR unwrapped). Only AND/OR bind looser than NOT, so a NOT
    # operand of anything else needs its parens back.
    if (
        isinstance(child, UnaryOp)
        and child.operator == UnaryOperator.NOT
        and parent not in (BinaryOperator.AND, BinaryOperator.OR)
    ):
        return f"({text})"
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
    # MySQL arithmetic coerces a string operand by parsing its LEADING numeric
    # prefix ('0x10' + 0 = 0 — the parse stops at 'x'); PG would read '0x10' as
    # hex (16) and Oracle/T-SQL error. Fold a literal string operand of a
    # literal-only MySQL arithmetic expression to its MySQL numeric value.
    if (
        SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
        and node.operator
        in (BinaryOperator.ADD, BinaryOperator.SUB, BinaryOperator.MUL)
        and all(isinstance(side, Literal) for side in (node.left, node.right))
        and any(
            isinstance(side, Literal)
            and isinstance(side.value, str)
            and side.dtype in ("string", "national", "unknown")
            for side in (node.left, node.right)
        )
        # An ISO date/timestamp string keeps the documented DATE-arithmetic
        # normalization (the DATE - DATE branch below), not the numeric fold.
        and not any(
            isinstance(side, Literal)
            and isinstance(side.value, str)
            and _ISO_DT_LITERAL_RE.fullmatch(side.value.strip())
            for side in (node.left, node.right)
        )
    ):

        def _mysql_num(side: Literal) -> ASTNode:
            if not isinstance(side.value, str):
                return side
            m = re.match(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", side.value)
            text = m.group(1) if m else "0"
            # MySQL string-operand arithmetic always yields a DOUBLE.
            return Literal(value=float(text), dtype="number")

        return _emit_binary(
            dataclasses.replace(
                node,
                left=_mysql_num(cast(Literal, node.left)),
                right=_mysql_num(cast(Literal, node.right)),
            ),
            dialect,
        )
    # An INTERVAL literal in +/- arithmetic renders per target: T-SQL has no
    # interval at all (DATEADD), MySQL takes an unquoted count, Oracle quotes
    # the count alone (INTERVAL '1' DAY — '1 DAY' is ORA-30089), PG accepts
    # the combined form natively.
    if (
        node.operator in (BinaryOperator.ADD, BinaryOperator.SUB)
        and isinstance(node.right, RawSQL)
        and (
            _iv := re.fullmatch(
                r"(?is)\s*INTERVAL\s+'?(\d+)'?\s+'?([A-Z]+)'?\s*",
                node.right.sql,
            )
        )
        and dialect in ("tsql", "mysql", "oracle")
        # A MySQL-source string-literal date keeps its specialized handling
        # below (CAST-back-to-DATE wrap / non-datetime NULL fold).
        and not (SOURCE_DIALECT.get() == "mysql" and isinstance(node.left, Literal))
    ):
        _iv_n, _iv_unit = _iv.group(1), _iv.group(2).upper().rstrip("S")
        _iv_left = _emit_operand(node.left, node.operator, dialect)
        if dialect == "tsql":
            _sign = "-" if node.operator == BinaryOperator.SUB else ""
            return f"DATEADD({_iv_unit}, {_sign}{_iv_n}, {_iv_left})"
        _op = "-" if node.operator == BinaryOperator.SUB else "+"
        if dialect == "mysql":
            return f"{_iv_left} {_op} INTERVAL {_iv_n} {_iv_unit}"
        return f"{_iv_left} {_op} INTERVAL '{_iv_n}' {_iv_unit}"
    # Oracle/PG ``<now-function> + n`` adds n DAYS (a date value); MySQL would
    # do a numeric addition on the timestamp and PG rejects timestamp + int.
    if (
        SOURCE_DIALECT.get() in ("oracle", "postgresql")
        and dialect in ("mysql", "postgresql", "tsql")
        and node.operator in (BinaryOperator.ADD, BinaryOperator.SUB)
        and isinstance(node.left, FunctionCall)
        and node.left.name.upper()
        in ("CURRENT_TIMESTAMP", "CURRENT_DATE", "SYSDATE", "NOW", "GETDATE")
        and isinstance(node.right, Literal)
        and isinstance(node.right.value, int)
        and not isinstance(node.right.value, bool)
    ):
        _dl = _emit_expression(node.left, dialect)
        _dn = node.right.value
        _dsign = "-" if node.operator == BinaryOperator.SUB else ""
        if dialect == "mysql":
            _fn = "DATE_SUB" if node.operator == BinaryOperator.SUB else "DATE_ADD"
            return f"{_fn}({_dl}, INTERVAL {_dn} DAY)"
        if dialect == "tsql":
            return f"DATEADD(DAY, {_dsign}{_dn}, {_dl})"
        _dop = "-" if node.operator == BinaryOperator.SUB else "+"
        return f"{_dl} {_dop} INTERVAL '{_dn}' DAY"
    # MySQL date arithmetic on a NON-datetime string literal ('12:00:00' +
    # INTERVAL 90 MINUTE) yields NULL (the string is not a valid datetime);
    # PG/T-SQL would either error or invent a 1900-01-01 date. Fold to NULL
    # with the divergence documented inline (auto-warned).
    if (
        SOURCE_DIALECT.get() == "mysql"
        and dialect != "mysql"
        and node.operator in (BinaryOperator.ADD, BinaryOperator.SUB)
        and isinstance(node.left, Literal)
        and isinstance(node.left.value, str)
        and node.left.dtype in ("string", "national", "unknown")
        and not _ISO_DT_LITERAL_RE.fullmatch(node.left.value.strip())
        and isinstance(node.right, RawSQL)
        and node.right.sql.upper().lstrip().startswith("INTERVAL")
    ):
        return (
            "NULL /* UNIQUE: MySQL date arithmetic on a non-datetime string "
            "literal yields NULL (docs/03-unsupported.md) */"
        )
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

    # ``DATE('2020-01-01') = '2020-01-01 00:00:00'`` is a DATE comparison, true on
    # every engine (the date equals the midnight timestamp) — but the DATE() of a
    # literal was dropped to a bare string, making it a false TEXT comparison.
    # Only the narrow literal-vs-literal shape is handled (a general DATE(col) is
    # unchanged, to avoid disturbing the common ``DATE(col) = '…'`` pattern).
    if node.operator in (
        BinaryOperator.EQ,
        BinaryOperator.NEQ,
        BinaryOperator.LT,
        BinaryOperator.GT,
        BinaryOperator.LTE,
        BinaryOperator.GTE,
    ):

        def _date_of_literal(n: ASTNode) -> Literal | None:
            if (
                isinstance(n, FunctionCall)
                and n.name.upper() == "TS_OR_DS_TO_DATE"
                and len(n.args) == 1
                and isinstance(n.args[0], Literal)
            ):
                return n.args[0]
            return None

        _ld, _rd = _date_of_literal(node.left), _date_of_literal(node.right)
        if (_ld is not None and isinstance(node.right, Literal)) or (
            _rd is not None and isinstance(node.left, Literal)
        ):

            def _cmp_side(n: ASTNode, dlit: Literal | None, other_is_date: bool) -> str:
                if dlit is not None:
                    return _emit_expression(
                        CastExpression(
                            expression=dlit, target_type=DataType(name="DATE")
                        ),
                        dialect,
                    )
                # A date/datetime string opposite a DATE: Oracle can't implicitly
                # convert an ISO string (ORA-01861) — lift it to an ANSI literal.
                if (
                    other_is_date
                    and dialect == "oracle"
                    and isinstance(n, Literal)
                    and isinstance(n.value, str)
                ):
                    _s = n.value.strip().replace("T", " ")
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", _s):
                        return f"DATE '{_s}'"
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", _s):
                        return f"TIMESTAMP '{_s}'"
                return _emit_operand(n, node.operator, dialect)

            _op_sym = {
                BinaryOperator.EQ: "=",
                BinaryOperator.NEQ: "<>",
                BinaryOperator.LT: "<",
                BinaryOperator.GT: ">",
                BinaryOperator.LTE: "<=",
                BinaryOperator.GTE: ">=",
            }[node.operator]
            _cl = _cmp_side(node.left, _ld, _rd is not None)
            _cr = _cmp_side(node.right, _rd, _ld is not None)
            return f"{_cl} {_op_sym} {_cr}"

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
