# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared converter from sqlglot AST to Unique IR nodes.

All dialect parsers delegate to this module for the heavy lifting of
converting sqlglot's expression tree into our engine-agnostic IR.
"""

from __future__ import annotations

import contextvars
import dataclasses
import logging
import re

import sqlglot
import sqlglot.expressions as exp

from unique.core.ast_nodes import (
    ASTNode,
    ColumnRef,
    DataType,
    FunctionCall,
    JoinType,
    Literal,
    RawSQL,
    TableRef,
    UpdateStatement,
)
from unique.core.mappings import BARE_CHAR_BIGTEXT, EMIT_TYPE_MAP, UUID_FUNCTION

# Split out of the former single-file converter; see the package __init__.

logger = logging.getLogger(__name__)


# T-SQL alias types (CREATE TYPE x FROM base) harvested from the script being
# transpiled, keyed by lowercase unqualified name. The transpiler sets this
# around a run (contextvar: safe under the API's threadpool) so column types
# referencing an alias resolve to the base type on engines without aliases.
TSQL_ALIAS_TYPES: contextvars.ContextVar[dict[str, DataType] | None] = (
    contextvars.ContextVar("tsql_alias_types", default=None)
)


_CREATE_ALIAS_TYPE_RE = re.compile(
    r"(?im)^\s*CREATE\s+TYPE\s+(?:\[?dbo\]?\s*\.\s*)?\[?(\w+)\]?\s+"
    r"FROM\s+\[?(\w+)\]?\s*(?:\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\))?"
)


# BIT columns harvested from the script's CREATE TABLE statements (table ->
# column names, lowercase). BIT maps to a real BOOLEAN on PostgreSQL, which
# rejects the integer 0/1 literals a T-SQL script writes into those columns,
# so INSERT/UPDATE literals are coerced at emit time.
TSQL_BIT_COLUMNS: contextvars.ContextVar[dict[str, frozenset[str]] | None] = (
    contextvars.ContextVar("tsql_bit_columns", default=None)
)


_CREATE_TABLE_NAME_RE = re.compile(
    r"(?i)\bCREATE\s+TABLE\s+([\w\[\]\".]+)",
)


_BIT_COLUMN_RE = re.compile(
    r"(?i)^\s*(\[[^\]]+\]|\w+)\s+(?:\[bit\]|bit)\b",
)


def coerce_bit_literals_in_sql(sql: str, dialect: str) -> str:
    """Rewrite 0/1 literals written to harvested BIT columns in raw SQL.

    Used by the procedural pipeline for embedded DML, which is transpiled
    through sqlglot rather than the IR emitter. Only INSERT ... (cols)
    VALUES and UPDATE ... SET assignments are touched, and only on
    PostgreSQL (where BIT maps to a real BOOLEAN).
    """
    if dialect != "postgresql":
        return sql
    registry = TSQL_BIT_COLUMNS.get()
    if not registry:
        return sql
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001 - leave unparseable SQL untouched
        return sql

    def as_bool(cell: exp.Expression) -> exp.Boolean | None:
        if (
            isinstance(cell, exp.Literal)
            and not cell.is_string
            and cell.this in ("0", "1")
        ):
            return exp.Boolean(this=cell.this == "1")
        return None

    changed = False
    if isinstance(tree, exp.Insert) and isinstance(tree.this, exp.Schema):
        schema_expr = tree.this
        if isinstance(schema_expr.this, exp.Table):
            cols = registry.get(schema_expr.this.name.lower(), frozenset())
            names = [c.name.lower() for c in schema_expr.expressions]
            values = tree.expression
            if cols and isinstance(values, exp.Values):
                for row in values.expressions:
                    for i, cell in enumerate(row.expressions):
                        if i < len(names) and names[i] in cols:
                            replacement = as_bool(cell)
                            if replacement is not None:
                                cell.replace(replacement)
                                changed = True
    elif isinstance(tree, exp.Update) and isinstance(tree.this, exp.Table):
        cols = registry.get(tree.this.name.lower(), frozenset())
        if cols:
            for assignment in tree.expressions:
                if (
                    isinstance(assignment, exp.EQ)
                    and isinstance(assignment.this, exp.Column)
                    and assignment.this.name.lower() in cols
                ):
                    replacement = as_bool(assignment.expression)
                    if replacement is not None:
                        assignment.expression.replace(replacement)
                        changed = True
    return tree.sql(dialect="postgres") if changed else sql


# DATE/DATETIME/TIMESTAMP columns harvested per table (table -> column names,
# lowercase). Oracle has no default that reads an ISO string as a date, so a
# bare '2024-01-15' written to such a column raises ORA-01861; the literal is
# wrapped in an ANSI DATE/TIMESTAMP literal at emit time (Oracle target only).
DATE_COLUMNS: contextvars.ContextVar[dict[str, frozenset[str]] | None] = (
    contextvars.ContextVar("date_columns", default=None)
)


_DATE_COLUMN_RE = re.compile(
    r"(?i)^\s*(\[[^\]]+\]|`[^`]+`|\"[^\"]+\"|\w+)\s+"
    r"(DATE|DATETIME2?|SMALLDATETIME|DATETIMEOFFSET|TIMESTAMP(?:TZ)?)\b"
)


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


_ISO_DATETIME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)$"
)


# Identity/auto-increment column per table (table -> column name, lowercase).
# T-SQL SCOPE_IDENTITY()/@@IDENTITY has no Oracle session equivalent; the
# generated id is captured with ``INSERT … RETURNING <idcol> INTO <var>``, so
# the procedural pipeline needs to know each table's identity column.
IDENTITY_COLUMNS: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("identity_columns", default=None)
)


_COLUMN_NAME_RE = re.compile(r"^\s*(\[[^\]]+\]|`[^`]+`|\"[^\"]+\"|\w+)\b")


_IDENTITY_MARKER_RE = re.compile(
    r"(?i)\b(?:IDENTITY|AUTO_INCREMENT|(?:BIG|SMALL)?SERIAL)\b"
    r"|GENERATED\s+(?:ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY"
)


# Names (lowercased) of user-defined functions declared in the script. A T-SQL
# scalar UDF call must be schema-qualified (``dbo.fn_tax(…)``) or it errors as an
# unknown built-in; used to qualify calls when targeting T-SQL.
USER_FUNCTIONS: contextvars.ContextVar[frozenset[str] | None] = contextvars.ContextVar(
    "user_functions", default=None
)


_CREATE_FUNCTION_NAME_RE = re.compile(
    r"(?im)^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?FUNCTION\s+" r"([\w\[\]\"`.]+)"
)


# A PostgreSQL trigger delegates its body to a ``RETURNS TRIGGER`` function
# (``… EXECUTE FUNCTION fn()``). T-SQL inlines the body in the trigger, so the
# function's full text is harvested by name to merge into its trigger.
PG_TRIGGER_FN_BODIES: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("pg_trigger_fn_bodies", default=None)
)


_PG_TRIGGER_FN_RE = re.compile(
    r"(?is)\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)\s*\(\s*\)\s+"
    r"RETURNS\s+TRIGGER\b.*?\$\$.*?\$\$"
)


# Positional indexes of a stored procedure's date/time parameters (proc name
# -> set of 0-based positions). Used to wrap an ISO date-string argument in an
# Oracle CALL (create_invoice(2, '2024-02-01', …)) as an ANSI DATE literal,
# since Oracle won't implicitly convert it (ORA-01861).
PROC_DATE_PARAMS: contextvars.ContextVar[dict[str, frozenset[int]] | None] = (
    contextvars.ContextVar("proc_date_params", default=None)
)


_DATE_TYPE_TOKENS = {
    "DATE",
    "DATETIME",
    "DATETIME2",
    "SMALLDATETIME",
    "DATETIMEOFFSET",
    "TIMESTAMP",
    "TIMESTAMPTZ",
}


_PROC_HEADER_RE = re.compile(
    r"(?is)\bCREATE\s+(?:OR\s+(?:ALTER|REPLACE)\s+)?PROC(?:EDURE)?\s+"
    r"([\w\[\]\".]+)\s*(.*?)\s*\b(?:AS|IS|BEGIN|LANGUAGE)\b"
)


# Mapping from sqlglot join types to our JoinType enum
_JOIN_TYPE_MAP = {
    "JOIN": JoinType.INNER,
    "INNER JOIN": JoinType.INNER,
    "LEFT JOIN": JoinType.LEFT,
    "LEFT OUTER JOIN": JoinType.LEFT,
    "RIGHT JOIN": JoinType.RIGHT,
    "RIGHT OUTER JOIN": JoinType.RIGHT,
    "FULL JOIN": JoinType.FULL,
    "FULL OUTER JOIN": JoinType.FULL,
    "CROSS JOIN": JoinType.CROSS,
}


def sqlglot_dialect_name(dialect: str) -> str:
    """Map our dialect names to sqlglot dialect names."""
    mapping = {
        "tsql": "tsql",
        "oracle": "oracle",
        "postgresql": "postgres",
        "mysql": "mysql",
        "sqlite": "sqlite",
    }
    return mapping.get(dialect, dialect)


def _looks_like_string(node: exp.Expression) -> bool:
    """Whether a sqlglot node is recognizably a string value.

    Used to decide if a T-SQL ``+`` is string concatenation rather than
    arithmetic addition: a string literal, a CHAR/VARCHAR/TEXT cast, an existing
    concatenation, or a known string function.
    """
    if isinstance(node, exp.Literal):
        return bool(node.args.get("is_string"))
    if isinstance(node, (exp.DPipe, exp.Concat)):
        return True
    if isinstance(node, exp.Cast):
        to = node.args.get("to")
        if isinstance(to, exp.DataType):
            return to.this in {
                exp.DataType.Type.CHAR,
                exp.DataType.Type.VARCHAR,
                exp.DataType.Type.NCHAR,
                exp.DataType.Type.NVARCHAR,
                exp.DataType.Type.TEXT,
            }
    if isinstance(node, (exp.Substring, exp.Trim, exp.Upper, exp.Lower)):
        return True
    if isinstance(node, exp.Anonymous):
        name = (node.name or "").upper()
        return name in {
            "LEFT",
            "RIGHT",
            "SUBSTRING",
            "LTRIM",
            "RTRIM",
            "TRIM",
            "UPPER",
            "LOWER",
            "REPLACE",
            "FORMAT",
            "STR",
            "CONCAT",
            "STUFF",
        }
    return False


def _rewrite_tsql_string_concat(expr: exp.Expression) -> exp.Expression:
    """Rewrite a T-SQL ``+`` that is string concatenation into ``||`` (DPipe).

    In T-SQL ``+`` means concatenation when an operand is a string, but sqlglot
    parses it as arithmetic ``Add`` regardless of operand type and does not
    re-map it per dialect, so ``'a' + 'b'`` would wrongly stay ``+`` on Oracle/
    PostgreSQL/MySQL. Convert an ``Add`` to ``DPipe`` when either side is
    recognizably a string (directly, or transitively through a nested string
    ``+`` already rewritten to ``DPipe``); purely numeric additions are left
    untouched. sqlglot then emits ``||`` for Oracle/PostgreSQL and ``CONCAT``
    for MySQL.
    """

    def transform(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Add):
            left, right = node.left, node.right
            if left is None or right is None:
                return node
            if (
                _looks_like_string(left)  # type: ignore[arg-type]
                or _looks_like_string(right)  # type: ignore[arg-type]
                or isinstance(left, exp.DPipe)
                or isinstance(right, exp.DPipe)
            ):
                return exp.DPipe(this=left, expression=right)
        return node

    # Bottom-up so a nested "+" is rewritten to DPipe before its parent is
    # examined, letting string-ness propagate up a chain (a + b + 'c').
    result = expr.transform(transform)
    assert isinstance(result, exp.Expression)
    return result


def _identifier_quoted(node: exp.Expression | None) -> bool:
    """True if *node* is a sqlglot Identifier that was quoted in the source."""
    return isinstance(node, exp.Identifier) and bool(node.args.get("quoted"))


# Type tables live in the shared declarative mapping layer (audit doc 03);
# _TYPE_NAME_MAP / _BARE_CHAR_BIGTEXT are kept as local aliases for the many
# call sites in this module.
_TYPE_NAME_MAP = EMIT_TYPE_MAP


_BARE_CHAR_BIGTEXT = BARE_CHAR_BIGTEXT


def _merge_to_mysql_upsert(sql: str, read: str) -> str | None:
    """Rewrite a canonical MERGE as MySQL INSERT ... ON DUPLICATE KEY UPDATE.

    Handles exactly one unconditional WHEN MATCHED THEN UPDATE plus one
    unconditional WHEN NOT MATCHED THEN INSERT, with a table or subquery
    source. Each UPDATE assignment must be either a literal or a source
    column that also appears in the INSERT values (rewritten as
    ``col = VALUES(col)``). Returns None when the MERGE is more complex, so
    the caller falls back to the documented carrier comment.
    """
    try:
        merge = sqlglot.parse_one(sql, read=read)
    except Exception:  # noqa: BLE001 - unparseable, let caller fall back
        return None
    if not isinstance(merge, exp.Merge) or merge.args.get("returning"):
        return None

    whens = merge.args.get("whens")
    when_list = list(whens.expressions) if whens else []
    if len(when_list) != 2:
        return None
    update = insert = None
    for when in when_list:
        if when.args.get("condition") is not None:
            return None
        then = when.args.get("then")
        if when.args.get("matched") and isinstance(then, exp.Update):
            update = then
        elif not when.args.get("matched") and isinstance(then, exp.Insert):
            insert = then
        else:
            return None
    if update is None or insert is None:
        return None
    if not isinstance(insert.this, exp.Tuple) or not isinstance(
        insert.expression, exp.Tuple
    ):
        return None

    insert_cols = [c.name for c in insert.this.expressions]
    insert_vals = insert.expression.expressions
    if len(insert_cols) != len(insert_vals):
        return None
    # Map each inserted value's SQL back to its column, so UPDATE assignments
    # whose RHS is one of the inserted source columns become VALUES(col).
    value_to_col = {
        val.sql(dialect="mysql"): col
        for col, val in zip(insert_cols, insert_vals, strict=True)
    }

    assignments: list[str] = []
    for eq in update.expressions:
        if not isinstance(eq, exp.EQ):
            return None
        target_col = eq.this.name  # strip any target-alias qualifier
        rhs = eq.expression
        rhs_sql = rhs.sql(dialect="mysql")
        if rhs_sql in value_to_col:
            assignments.append(f"{target_col} = VALUES({value_to_col[rhs_sql]})")
        elif isinstance(rhs, (exp.Literal, exp.Null)):
            assignments.append(f"{target_col} = {rhs_sql}")
        else:
            return None

    target_sql = merge.this.sql(dialect="mysql")
    source_sql = merge.args["using"].sql(dialect="mysql")
    cols_sql = ", ".join(insert_cols)
    vals_sql = ", ".join(v.sql(dialect="mysql") for v in insert_vals)
    on_cols = ", ".join(sorted({c.name for c in merge.args["on"].find_all(exp.Column)}))
    return (
        f"INSERT INTO {target_sql} ({cols_sql})\n"
        f"SELECT {vals_sql} FROM {source_sql}\n"
        f"ON DUPLICATE KEY UPDATE {', '.join(assignments)};\n"
        f"-- UNIQUE: MERGE rewritten as INSERT ... ON DUPLICATE KEY UPDATE; "
        f"requires a UNIQUE or PRIMARY KEY on ({on_cols})"
    )


def _split_top_level_commas(text: str) -> list[str]:
    """Split *text* on commas not nested inside parentheses or strings."""
    parts: list[str] = []
    depth = 0
    in_string = False
    start = 0
    for i, ch in enumerate(text):
        if in_string:
            if ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _oracle_sequence_drop_type(sql: str) -> str:
    """Drop the ``AS <type>`` clause from a CREATE SEQUENCE for Oracle.

    T-SQL/PostgreSQL allow ``CREATE SEQUENCE s AS INT ...`` to bound the
    sequence's data type; Oracle has no such clause and rejects it
    (ORA-03048). sqlglot maps the type but keeps the clause, so remove the
    ``AS <type>`` that follows the sequence name.
    """
    return re.sub(
        r"(?is)(\bCREATE\s+SEQUENCE\s+\S+)\s+AS\s+\w+(?:\s*\([^)]*\))?",
        r"\1",
        sql,
        count=1,
    )


def _cross_update_target(node: UpdateStatement) -> TableRef:
    """The real table being updated in a cross-table UPDATE.

    The T-SQL ``node.table`` is typically the alias (e.g. ``il``); the FROM's
    first source carries the actual table name and that alias. Prefer the FROM
    source when its alias matches the target, so we emit the real table name.
    """
    tgt_name = node.table.name
    if node.from_clause is not None:
        fc = node.from_clause
        if fc.alias == tgt_name or fc.name == tgt_name:
            return fc
    return node.table


def _strip_dbo_function_name(node: FunctionCall) -> FunctionCall:
    """Return a copy of ``node`` with a leading ``dbo.`` removed from its name.

    A user function call like ``dbo.fn_tax`` keeps just ``fn_tax`` for the
    non-T-SQL engines, where the ``dbo`` default schema does not exist. The
    qualifier may be bare, bracketed (``[dbo].``) or quoted (``"dbo".``).
    """
    new_name = re.sub(r'(?i)^\s*(?:\[dbo\]|"dbo"|dbo)\s*\.\s*', "", node.name)
    if new_name == node.name:
        return node
    return dataclasses.replace(node, name=new_name)


def _strip_dbo_schema_qualifier(sql: str) -> str:
    """Remove the T-SQL ``dbo.`` schema qualifier from object names in ``sql``.

    ``dbo`` is the T-SQL default schema; it names no real schema on Oracle/
    PostgreSQL and a non-existent database on MySQL, so a qualified reference
    like ``dbo.invoice`` (in a CREATE SEQUENCE/INDEX, a view body, an FK
    reference, etc.) must drop the prefix for those engines. The qualifier may
    be bare (``dbo.``), bracketed (``[dbo].``) or quoted (``"dbo".``). Only a
    ``dbo`` immediately followed by ``.`` and an identifier is touched, so a
    column or value literally containing the text is left alone.
    """
    return re.sub(
        r'(?i)(?:\[dbo\]|"dbo"|\bdbo)\s*\.\s*(?=[\w\[\"])',
        "",
        sql,
    )


def _strip_dbo_from_references(fragment: str) -> str:
    """Remove a leading ``dbo.`` qualifier from a FOREIGN KEY reference target.

    A T-SQL ``REFERENCES dbo.customer (id)`` must become ``REFERENCES customer
    (id)`` on Oracle/MySQL/PostgreSQL, where ``dbo`` names no real schema. Only
    the table named right after ``REFERENCES`` is touched; the qualifier may be
    bare (``dbo.``), bracketed (``[dbo].``) or quoted (``"dbo".``).
    """
    return re.sub(
        r'(?i)(\bREFERENCES\s+)(?:\[dbo\]|"dbo"|dbo)\s*\.\s*',
        r"\1",
        fragment,
    )


_IDENT_QUOTES = {
    "tsql": ("[", "]"),
    "mysql": ("`", "`"),
    "postgresql": ('"', '"'),
    "oracle": ('"', '"'),
}


def _quote_ident(name: str, dialect: str | None) -> str:
    """Wrap *name* in the target dialect's identifier quote characters.

    Quoting is translated between engines, never stripped (audit 2026-07-02,
    S1-1): a quoted identifier may be a reserved word or case/space-sensitive,
    so dropping the quotes changes meaning or breaks the syntax outright.
    """
    left, right = _IDENT_QUOTES.get(dialect or "tsql", ('"', '"'))
    escaped = name.replace(right, right * 2)
    return f"{left}{escaped}{right}"


# Reserved words that commonly appear as table/column names in real schemas and
# must be quoted for the target engine (a bare ``CREATE TABLE collation`` is a
# syntax error on PostgreSQL and Oracle). Curated per dialect — over-quoting a
# non-reserved word is harmless, so a shared common core is included in each.
_RESERVED_COMMON = frozenset(
    {
        "USER",
        "ORDER",
        "GROUP",
        "TABLE",
        "COLUMN",
        "SELECT",
        "WHERE",
        "FROM",
        "CHECK",
        "DEFAULT",
        "PRIMARY",
        "REFERENCES",
        "UNIQUE",
        "CONSTRAINT",
        "INDEX",
        "COMMENT",
        "DESC",
        "ASC",
        "KEY",
        "LEVEL",
        "SESSION",
        "ALL",
        "AND",
        "OR",
        "NOT",
        "NULL",
        "IN",
        "IS",
        "LIKE",
        "BETWEEN",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AS",
        "ON",
        "BY",
        "TO",
        "VALUES",
    }
)
_RESERVED_IDENTIFIERS: dict[str, frozenset[str]] = {
    "postgresql": _RESERVED_COMMON
    | frozenset({"COLLATION", "LIMIT", "OFFSET", "USING", "DO", "ARRAY", "ANY"}),
    "oracle": _RESERVED_COMMON
    | frozenset(
        {
            "COLLATION",
            "DATE",
            "NUMBER",
            "SIZE",
            "ROWID",
            "ROWNUM",
            "ACCESS",
            "AUDIT",
            "CLUSTER",
            "RESOURCE",
            "MODE",
            "ROW",
            "RAW",
            "LONG",
            "FILE",
            "COMMENT",
            "SHARE",
            "START",
            "SYNONYM",
            "UID",
            "VALIDATE",
        }
    ),
    "mysql": _RESERVED_COMMON | frozenset({"COLLATION", "LIMIT", "USAGE", "READ"}),
    "tsql": _RESERVED_COMMON
    | frozenset({"USER", "PERCENT", "IDENTITY", "FILE", "PLAN", "KEY", "READTEXT"}),
}


def _ident(name: str, quoted: bool, dialect: str | None) -> str:
    """Emit an identifier, quoting it when the source quoted it *or* when it is a
    reserved word in the target dialect (else it is invalid unquoted DDL)."""
    if quoted or (
        dialect is not None
        and name.upper() in _RESERVED_IDENTIFIERS.get(dialect, frozenset())
    ):
        return _quote_ident(name, dialect)
    return name


_DATE_UNIT_ALIASES = {
    "DD": "DAY",
    "D": "DAY",
    "DAYOFYEAR": "DAY",
    "MM": "MONTH",
    "M": "MONTH",
    "YY": "YEAR",
    "YYYY": "YEAR",
    "HH": "HOUR",
    "MI": "MINUTE",
    "N": "MINUTE",
    "SS": "SECOND",
    "S": "SECOND",
    "WK": "WEEK",
    "WW": "WEEK",
    "W": "WEEK",
}


_DATE_UNITS = {"DAY", "WEEK", "MONTH", "YEAR", "HOUR", "MINUTE", "SECOND"}


# sqlglot canonicalization wrappers that must never reach emitted SQL.
_SQLGLOT_WRAPPERS = {
    "TIME_STR_TO_TIME",
    "TS_OR_DS_TO_DATE",
    "TS_OR_DS_TO_TIMESTAMP",
    # sqlglot renders an Oracle ``DATE '…'`` literal as this internal wrapper
    # when writing to some dialects; unwrap to the ISO string, which the target
    # implicitly converts for a date column.
    "DATE_STR_TO_DATE",
}


def _unwrap_sqlglot_wrappers(node: ASTNode) -> ASTNode:
    """Strip sqlglot-internal cast pseudo-functions from an argument."""
    while (
        isinstance(node, FunctionCall)
        and node.name.upper() in _SQLGLOT_WRAPPERS
        and len(node.args) == 1
    ):
        node = node.args[0]
    return node


def _date_unit_name(node: ASTNode) -> str | None:
    """Extract a normalized date-part unit (DAY, MONTH, ...) from an IR arg."""
    raw: str | None = None
    if isinstance(node, RawSQL):
        raw = node.sql
    elif isinstance(node, Literal) and isinstance(node.value, str):
        raw = node.value
    elif isinstance(node, ColumnRef) and not node.table:
        raw = node.name
    if raw is None:
        return None
    unit = _DATE_UNIT_ALIASES.get(raw.strip().upper(), raw.strip().upper())
    return unit if unit in _DATE_UNITS else None


def _map_function_name(name: str, dialect: str) -> str:
    """Map a canonical function name to the dialect-specific equivalent."""
    upper = name.upper()

    # COALESCE stays COALESCE everywhere (it's standard SQL)
    if upper == "COALESCE":
        return "COALESCE"

    # LENGTH
    if upper == "LENGTH":
        if dialect == "tsql":
            return "LEN"
        return "LENGTH"

    # SUBSTRING
    if upper == "SUBSTRING":
        if dialect == "oracle":
            return "SUBSTR"
        return "SUBSTRING"

    # UUID generation: sqlglot canonicalizes NEWID/UUID/GEN_RANDOM_UUID to
    # UUID, which only exists on MySQL. Each engine has its own function
    # (found by a hardened test during audit 2026-07-02 remediation).
    if upper in ("UUID", "NEWID", "GEN_RANDOM_UUID", "SYS_GUID"):
        return UUID_FUNCTION.get(dialect, name)

    return name


def _object_id_name(node: TableRef) -> str:
    """Build a schema-qualified name for a T-SQL OBJECT_ID() guard.

    Excludes any alias and the database part (OBJECT_ID resolves within the
    current database), keeping just ``[schema.]table``.
    """
    parts = []
    if node.schema:
        parts.append(node.schema)
    parts.append(node.name)
    return ".".join(parts)


__all__ = [
    "DATE_COLUMNS",
    "IDENTITY_COLUMNS",
    "PG_TRIGGER_FN_BODIES",
    "PROC_DATE_PARAMS",
    "TSQL_ALIAS_TYPES",
    "TSQL_BIT_COLUMNS",
    "USER_FUNCTIONS",
    "_BARE_CHAR_BIGTEXT",
    "_BIT_COLUMN_RE",
    "_COLUMN_NAME_RE",
    "_CREATE_ALIAS_TYPE_RE",
    "_CREATE_FUNCTION_NAME_RE",
    "_CREATE_TABLE_NAME_RE",
    "_DATE_COLUMN_RE",
    "_DATE_TYPE_TOKENS",
    "_DATE_UNITS",
    "_DATE_UNIT_ALIASES",
    "_IDENTITY_MARKER_RE",
    "_IDENT_QUOTES",
    "_ISO_DATETIME_RE",
    "_ISO_DATE_RE",
    "_JOIN_TYPE_MAP",
    "_PG_TRIGGER_FN_RE",
    "_PROC_HEADER_RE",
    "_SQLGLOT_WRAPPERS",
    "_TYPE_NAME_MAP",
    "_cross_update_target",
    "_date_unit_name",
    "_ident",
    "_identifier_quoted",
    "_looks_like_string",
    "_map_function_name",
    "_merge_to_mysql_upsert",
    "_object_id_name",
    "_oracle_sequence_drop_type",
    "_quote_ident",
    "_rewrite_tsql_string_concat",
    "_split_top_level_commas",
    "_strip_dbo_from_references",
    "_strip_dbo_function_name",
    "_strip_dbo_schema_qualifier",
    "_unwrap_sqlglot_wrappers",
    "coerce_bit_literals_in_sql",
    "logger",
    "sqlglot_dialect_name",
]
