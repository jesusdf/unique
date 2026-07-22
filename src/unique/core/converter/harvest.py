# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import re

from unique.core.ast_nodes import ASTNode, DataType, Literal, RawSQL, TableRef

# Split out of the former single-file converter; see the package __init__.
from unique.core.converter._base import *  # noqa: F401,F403

_PG_COMPOSITE_TYPE_RE = re.compile(r"(?is)\bCREATE\s+TYPE\s+(?:\w+\.)?(\w+)\s+AS\s*\(")


_PG_TABLE_NAME_RE = re.compile(
    r"(?is)\bCREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:\w+\.)?(\w+)"
)


def harvest_pg_composite_types(sql: str) -> frozenset[str]:
    """Collect PG composite-type names from a whole script.

    Every table name is ALSO a rowtype in PG (``function f(t onek)``) —
    a routine typed with one is as untranslatable off PG as an explicit
    CREATE TYPE composite (wave 151)."""
    named = frozenset(m.group(1).lower() for m in _PG_COMPOSITE_TYPE_RE.finditer(sql))
    tables = frozenset(m.group(1).lower() for m in _PG_TABLE_NAME_RE.finditer(sql))
    return named | tables


_PG_DOMAIN_RE = re.compile(
    r"(?is)\bCREATE\s+DOMAIN\s+(?:\w+\.)?(\w+)\s+AS\s+"
    r"(\w+(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)"
)


def harvest_pg_domains(sql: str) -> dict[str, str]:
    """Collect PG domain-type names and their base types."""
    return {m.group(1).lower(): m.group(2) for m in _PG_DOMAIN_RE.finditer(sql)}


def harvest_tsql_alias_types(sql: str) -> dict[str, DataType]:
    """Collect T-SQL alias-type definitions from a whole script."""
    aliases: dict[str, DataType] = {}
    for m in _CREATE_ALIAS_TYPE_RE.finditer(sql):
        name, base, p1, p2 = m.groups()
        params = tuple(int(p) for p in (p1, p2) if p is not None)
        aliases[name.lower()] = DataType(name=base.upper(), params=params)
    return aliases


def _resolve_tsql_alias_type(dt: DataType) -> DataType:
    """Resolve a column type that names a harvested T-SQL alias type."""
    aliases = TSQL_ALIAS_TYPES.get()
    if not aliases:
        return dt
    key = re.sub(r'(?i)^(?:\[dbo\]|"dbo"|dbo)\s*\.\s*', "", dt.name)
    key = key.strip('[]"').lower()
    return aliases.get(key, dt)


def harvest_tsql_bit_columns(sql: str) -> dict[str, frozenset[str]]:
    """Collect BIT column names per table from a whole T-SQL script."""
    result: dict[str, set[str]] = {}
    current: str | None = None
    for line in sql.splitlines():
        m = _CREATE_TABLE_NAME_RE.search(line)
        if m:
            name = m.group(1).replace("[", "").replace("]", "").replace('"', "")
            current = name.split(".")[-1].lower()
            continue
        if current is None:
            continue
        cm = _BIT_COLUMN_RE.match(line)
        if cm:
            col = cm.group(1).strip('[]"').lower()
            result.setdefault(current, set()).add(col)
    return {t: frozenset(c) for t, c in result.items()}


def _coerce_bit_literal(
    table: TableRef, column: str, value: ASTNode, dialect: str
) -> ASTNode:
    """Turn an integer 0/1 written to a known BIT column into a boolean."""
    if dialect != "postgresql":
        return value
    registry = TSQL_BIT_COLUMNS.get()
    if not registry:
        return value
    cols = registry.get(table.name.lower())
    if not cols:
        return value
    if column.split(".")[-1].strip('[]"').lower() not in cols:
        return value
    if (
        isinstance(value, Literal)
        and value.dtype != "string"
        and str(value.value) in ("0", "1")
    ):
        return Literal(value=str(value.value) == "1", dtype="boolean")
    return value


def harvest_identity_columns(sql: str) -> dict[str, str]:
    """Collect each table's identity/auto-increment column from a script.

    Works across source dialects (IDENTITY, AUTO_INCREMENT, SERIAL, GENERATED
    … AS IDENTITY). Only the first such column per table is recorded (a table
    has at most one). Used only when the target is Oracle.
    """
    result: dict[str, str] = {}
    current: str | None = None
    for line in sql.splitlines():
        m = _CREATE_TABLE_NAME_RE.search(line)
        if m:
            name = m.group(1).replace("[", "").replace("]", "").replace('"', "")
            current = name.split(".")[-1].lower()
            continue
        if current is None or current in result:
            continue
        cm = _COLUMN_NAME_RE.match(line)
        if cm and _IDENTITY_MARKER_RE.search(line):
            result[current] = cm.group(1).strip('[]"`').lower()
    return result


def harvest_user_functions(sql: str) -> frozenset[str]:
    """Collect the bare names of user-defined functions created in *sql*."""
    names: set[str] = set()
    for m in _CREATE_FUNCTION_NAME_RE.finditer(sql):
        names.add(m.group(1).strip('[]"`').split(".")[-1].lower())
    return frozenset(names)


def harvest_pg_trigger_functions(sql: str) -> dict[str, str]:
    """Map each ``RETURNS TRIGGER`` function's bare name to its full CREATE text
    (dollar-quoted body included), for inlining into a T-SQL trigger."""
    result: dict[str, str] = {}
    for m in _PG_TRIGGER_FN_RE.finditer(sql):
        result[m.group(1).lower()] = m.group(0)
    return result


def harvest_proc_date_params(sql: str) -> dict[str, frozenset[int]]:
    """Collect the positional indexes of each procedure's date parameters.

    Works across source dialects (T-SQL ``@p DATE`` and the parenthesized
    ``(p IN DATE)`` forms). Used only when the target is Oracle.
    """
    result: dict[str, frozenset[int]] = {}
    for m in _PROC_HEADER_RE.finditer(sql):
        name = m.group(1).replace("[", "").replace("]", "").replace('"', "")
        name = name.split(".")[-1].lower()
        section = m.group(2).strip()
        if section.startswith("(") and section.endswith(")"):
            section = section[1:-1]
        if not section.strip():
            continue
        positions: set[int] = set()
        for i, part in enumerate(_split_top_level_commas(section)):
            tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", part)
            # Skip the parameter name (and IN/OUT direction) — only the type
            # tokens decide, so a parameter *named* "date" is not a false match.
            if any(t.upper() in _DATE_TYPE_TOKENS for t in tokens[1:]):
                positions.add(i)
        if positions:
            result[name] = frozenset(positions)
    return result


def harvest_date_columns(sql: str) -> dict[str, frozenset[str]]:
    """Collect date/time column names per table from a whole script.

    Works across source dialects (the type keyword is enough); only used when
    the target is Oracle.
    """
    result: dict[str, set[str]] = {}
    current: str | None = None
    for line in sql.splitlines():
        m = _CREATE_TABLE_NAME_RE.search(line)
        if m:
            name = m.group(1).replace("[", "").replace("]", "").replace('"', "")
            current = name.split(".")[-1].lower()
            continue
        if current is None:
            continue
        cm = _DATE_COLUMN_RE.match(line)
        if cm:
            col = cm.group(1).strip('[]"`').lower()
            result.setdefault(current, set()).add(col)
    return {t: frozenset(c) for t, c in result.items()}


def _coerce_date_literal(
    table: TableRef, column: str, value: ASTNode, dialect: str
) -> ASTNode:
    """Wrap an ISO date/datetime string written to a known date column in an
    ANSI ``DATE``/``TIMESTAMP`` literal so Oracle accepts it (ORA-01861)."""
    if dialect != "oracle":
        return value
    registry = DATE_COLUMNS.get()
    if not registry:
        return value
    cols = registry.get(table.name.lower())
    if not cols:
        return value
    if column.split(".")[-1].strip('[]"`').lower() not in cols:
        return value
    if not (isinstance(value, Literal) and isinstance(value.value, str)):
        return value
    text = value.value.strip()
    wrapped = _oracle_date_literal(text)
    return RawSQL(sql=wrapped) if wrapped is not None else value


def _oracle_date_literal(text: str) -> str | None:
    """Return the ANSI ``DATE``/``TIMESTAMP`` literal for an ISO date/datetime
    string, or ``None`` when *text* is not one."""
    if _ISO_DATE_RE.match(text):
        return f"DATE '{text}'"
    dt = _ISO_DATETIME_RE.match(text)
    if dt:
        time_part = dt.group(2)
        # Oracle's TIMESTAMP literal needs a full HH24:MI:SS; a seconds-less
        # time (PostgreSQL accepts ``TIMESTAMP '… 10:00'``) is ORA-01861.
        if re.fullmatch(r"\d{2}:\d{2}", time_part):
            time_part += ":00"
        return f"TIMESTAMP '{dt.group(1)} {time_part}'"
    return None


def wrap_oracle_date_arg(arg: str) -> str:
    """Wrap a quoted ISO date/datetime CALL argument in an ANSI literal.

    ``'2024-02-01'`` -> ``DATE '2024-02-01'``. Non-date or unquoted arguments
    are returned unchanged. Used for Oracle stored-procedure call arguments at
    known date-parameter positions (Oracle won't implicitly convert the string,
    ORA-01861).
    """
    s = arg.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        wrapped = _oracle_date_literal(s[1:-1])
        if wrapped is not None:
            return wrapped
    return arg
