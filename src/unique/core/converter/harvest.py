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


_CT_HEAD_RE = re.compile(
    r"(?i)\bCREATE\s+(?:GLOBAL\s+|LOCAL\s+|TEMPORARY\s+|TEMP\s+|UNLOGGED\s+)*"
    r"TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\[\]\"`#]+)\s*\("
)
_CT_ELEMENT_HEADS = frozenset(
    {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT", "INDEX", "KEY", "EXCLUDE"}
)


def harvest_column_types(sql: str) -> dict[str, dict[str, str]]:
    """Column types per table from the script's own CREATE TABLEs
    (table -> {column -> declared type SQL}, lowercase keys). Balanced-paren
    body scan, so inline single-line CREATEs work too."""
    from unique.core.converter._base import _split_top_level_commas

    result: dict[str, dict[str, str]] = {}
    for m in _CT_HEAD_RE.finditer(sql):
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            ch = sql[i]
            if ch == "'":
                i += 1
                while i < len(sql):
                    if sql[i : i + 2] == "''":
                        i += 2
                        continue
                    if sql[i] == "'":
                        break
                    i += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = sql[m.end() : i - 1]
        table = m.group(1).replace("[", "").replace("]", "").replace('"', "")
        table = table.split(".")[-1].lstrip("#").lower()
        cols: dict[str, str] = {}
        for item in _split_top_level_commas(body):
            cm = re.match(
                r'\s*(\[[^\]]+\]|`[^`]+`|"[^"]+"|\w+)\s+'
                r"([A-Za-z]\w*(?:\s+PRECISION|\s+VARYING)?"
                r"(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)",
                item,
            )
            if not cm:
                continue
            name = cm.group(1).strip('[]"`')
            if name.upper() in _CT_ELEMENT_HEADS:
                continue
            cols[name.lower()] = cm.group(2).strip()
        if cols:
            result[table] = cols
    return result


def _scan_balanced(text: str, i: int) -> int:
    """Index just past the ``)`` that closes the ``(`` already consumed at *i*
    (single-quote aware, ``''`` escapes; depth starts at 1)."""
    depth = 1
    while i < len(text) and depth:
        ch = text[i]
        if ch == "'":
            i += 1
            while i < len(text):
                if text[i : i + 2] == "''":
                    i += 2
                    continue
                if text[i] == "'":
                    break
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return i


_ENUM_HEAD_RE = re.compile(r'(?is)^\s*(\[[^\]]+\]|`[^`]+`|"[^"]+"|\w+)\s+ENUM\s*\(')
_ENUM_VALUE_RE = re.compile(r"'((?:[^']|'')*)'")


def harvest_enum_columns(sql: str) -> dict[str, dict[str, tuple[str, ...]]]:
    """MySQL ENUM columns per table from the script's own CREATE TABLEs
    (table -> {column -> ordered value tuple}, lowercase keys). The ordered
    value list IS the column's sort order on MySQL; the transformer uses it to
    rewrite ordering-sensitive uses into an ordinal ``CASE`` (B29). SET is
    excluded — it is an unordered combination, so it carries no sort key."""
    from unique.core.converter._base import _split_top_level_commas

    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for m in _CT_HEAD_RE.finditer(sql):
        body = sql[m.end() : _scan_balanced(sql, m.end()) - 1]
        table = m.group(1).replace("[", "").replace("]", "").replace('"', "")
        table = table.split(".")[-1].lstrip("#").lower()
        cols: dict[str, tuple[str, ...]] = {}
        for item in _split_top_level_commas(body):
            em = _ENUM_HEAD_RE.match(item)
            if not em or em.group(1).strip('[]"`').upper() in _CT_ELEMENT_HEADS:
                continue
            inner = item[em.end() : _scan_balanced(item, em.end()) - 1]
            values = tuple(v.replace("''", "'") for v in _ENUM_VALUE_RE.findall(inner))
            if values:
                cols[em.group(1).strip('[]"`').lower()] = values
        if cols:
            result[table] = cols
    return result


def harvest_column_not_null(sql: str) -> dict[str, dict[str, bool]]:
    """Per-column NOT NULL knowledge from the script's own CREATE TABLEs
    (table -> {column -> True if declared NOT NULL else False}, lowercase
    keys). Companion to :func:`harvest_column_types` for the running
    ALTER-nullability scan; an absent column means the nullability is unknown.
    Column-level and table-level ``PRIMARY KEY`` imply NOT NULL."""
    from unique.core.converter._base import _split_top_level_commas

    result: dict[str, dict[str, bool]] = {}
    for m in _CT_HEAD_RE.finditer(sql):
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            ch = sql[i]
            if ch == "'":
                i += 1
                while i < len(sql):
                    if sql[i : i + 2] == "''":
                        i += 2
                        continue
                    if sql[i] == "'":
                        break
                    i += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = sql[m.end() : i - 1]
        table = m.group(1).replace("[", "").replace("]", "").replace('"', "")
        table = table.split(".")[-1].lstrip("#").lower()
        cols: dict[str, bool] = {}
        pk_cols: tuple[str, ...] = ()
        for item in _split_top_level_commas(body):
            s = item.strip()
            mk = re.match(r"(?is)^(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*\((.*?)\)", s)
            if mk:
                pk_cols = _key_column_list(mk.group(1))
                continue
            cm = re.match(r'\s*(\[[^\]]+\]|`[^`]+`|"[^"]+"|\w+)\s+', s)
            if not cm:
                continue
            name = cm.group(1).strip('[]"`')
            if name.upper() in _CT_ELEMENT_HEADS:
                continue
            not_null = bool(re.search(r"(?i)\bNOT\s+NULL\b", s)) or bool(
                re.search(r"(?i)\bPRIMARY\s+KEY\b", s)
            )
            cols[name.lower()] = not_null
        for c in pk_cols:
            if c in cols:
                cols[c] = True
        if cols:
            result[table] = cols
    return result


# One ALTER TABLE statement, split into the target table and the trailing
# action text (the running-scan fold parses the action per source dialect).
_ALTER_TABLE_HEAD_RE = re.compile(r"(?is)^\s*ALTER\s+TABLE\s+([\w.\[\]\"`#]+)\s+(.*)$")
_ALTER_TYPE_TAIL = r"([A-Za-z]\w*(?:\s*\([\d,\s]*\))?)"


def _norm_ident(text: str) -> str:
    """Bare lowercase identifier (last dotted segment, quotes/brackets/# off)."""
    return text.split(".")[-1].lstrip("#").strip('[]"`').lower()


def fold_alter_into_running_types(
    sql: str,
    source_dialect: str,
    col_types: dict[str, dict[str, str]] | None,
    col_not_null: dict[str, dict[str, bool]] | None,
) -> None:
    """Apply one ALTER TABLE statement's column-shape change to the running
    COLUMN_TYPES / COLUMN_NOT_NULL maps **in place**, in statement order:
    ``ALTER/MODIFY COLUMN … TYPE``, ``ADD COLUMN``, ``RENAME COLUMN`` and
    ``DROP/SET NOT NULL``. A no-op when neither map tracks the table (a table
    the script did not create in-script → the warned path).
    """
    if col_types is None and col_not_null is None:
        return
    m = _ALTER_TABLE_HEAD_RE.match(sql.strip())
    if not m:
        return
    table = _norm_ident(m.group(1))
    body = m.group(2).strip().rstrip(";").strip()
    ct = col_types.get(table) if col_types is not None else None
    nn = col_not_null.get(table) if col_not_null is not None else None
    if ct is None and nn is None:
        return  # table not created in-script

    # RENAME COLUMN old TO new — move both maps' keys.
    mr = re.match(
        r'(?is)^RENAME\s+(?:COLUMN\s+)?([\w\[\]"`]+)\s+TO\s+([\w\[\]"`]+)', body
    )
    if mr:
        old, new = _norm_ident(mr.group(1)), _norm_ident(mr.group(2))
        if ct is not None and old in ct:
            ct[new] = ct.pop(old)
        if nn is not None and old in nn:
            nn[new] = nn.pop(old)
        return

    # ADD [COLUMN] c <type> [NOT NULL …] — record the new column.
    ma = re.match(
        r'(?is)^ADD\s+(?:COLUMN\s+)?([\w\[\]"`]+)\s+' + _ALTER_TYPE_TAIL + r"(.*)$",
        body,
    )
    if ma and _norm_ident(ma.group(1)).upper() not in _CT_ELEMENT_HEADS:
        col = _norm_ident(ma.group(1))
        if ct is not None:
            ct[col] = ma.group(2).strip()
        if nn is not None:
            nn[col] = bool(re.search(r"(?i)\bNOT\s+NULL\b", ma.group(3)))
        return

    # DROP/SET NOT NULL — update nullability only.
    md = re.match(
        r'(?is)^ALTER\s+(?:COLUMN\s+)?([\w\[\]"`]+)\s+(DROP|SET)\s+NOT\s+NULL', body
    )
    if md:
        if nn is not None:
            nn[_norm_ident(md.group(1))] = md.group(2).upper() == "SET"
        return

    # Type change — spelling differs per source dialect.
    col_type = _alter_type_change(source_dialect, body)
    if col_type is not None:
        col, new_type, restated_null = col_type
        if ct is not None:
            ct[col] = new_type
        # MySQL MODIFY resets column attributes: a bare MODIFY drops NOT NULL
        # unless restated. PG/Oracle/T-SQL type changes preserve nullability.
        if nn is not None and source_dialect == "mysql":
            nn[col] = restated_null


def _alter_type_change(source_dialect: str, body: str) -> tuple[str, str, bool] | None:
    """Parse a type-change ALTER body for *source_dialect*; return
    (column, declared-type-SQL, restated-NOT-NULL) or None."""
    if source_dialect == "postgresql":
        mt = re.match(
            r'(?is)^ALTER\s+(?:COLUMN\s+)?([\w\[\]"`]+)\s+'
            r"(?:SET\s+DATA\s+)?TYPE\s+" + _ALTER_TYPE_TAIL,
            body,
        )
    elif source_dialect == "oracle":
        mt = re.match(
            r'(?is)^MODIFY\s*\(?\s*(?:COLUMN\s+)?([\w\[\]"`]+)\s+' + _ALTER_TYPE_TAIL,
            body,
        )
    elif source_dialect == "mysql":
        # MODIFY only; MySQL CHANGE (rename+retype) is split upstream and out of
        # this scan's scope. MODIFY resets attributes unless the tail restates.
        mt = re.match(
            r'(?is)^MODIFY\s+(?:COLUMN\s+)?([\w\[\]"`]+)\s+'
            + _ALTER_TYPE_TAIL
            + r"(.*)$",
            body,
        )
        if mt:
            return (
                _norm_ident(mt.group(1)),
                mt.group(2).strip(),
                bool(re.search(r"(?i)\bNOT\s+NULL\b", mt.group(3))),
            )
        return None
    elif source_dialect == "tsql":
        mt = re.match(
            r'(?is)^ALTER\s+COLUMN\s+([\w\[\]"`]+)\s+' + _ALTER_TYPE_TAIL, body
        )
    else:
        return None
    if not mt:
        return None
    return (_norm_ident(mt.group(1)), mt.group(2).strip(), False)


def _key_column_list(text: str) -> tuple[str, ...]:
    """Split a parenthesized key column list into bare lowercase names."""
    from unique.core.converter._base import _split_top_level_commas

    cols: list[str] = []
    for part in _split_top_level_commas(text):
        name = part.strip().strip('[]"`').split()[0] if part.strip() else ""
        name = name.strip('[]"`').lower()
        if name:
            cols.append(name)
    return tuple(cols)


def harvest_pk_unique_columns(sql: str) -> dict[str, list[tuple[str, ...]]]:
    """PRIMARY KEY / UNIQUE column tuples per table from the script's own
    CREATE TABLEs (table -> list of key column-tuples, PK first, lowercase
    keys). Balanced-paren body scan, so inline single-line CREATEs work too.

    Recognizes both table-level constraints (``PRIMARY KEY (a, b)``,
    ``CONSTRAINT x UNIQUE (a)``, MySQL ``UNIQUE KEY name (a)``) and column-level
    ``col type PRIMARY KEY`` / ``col type UNIQUE``.
    """
    from unique.core.converter._base import _split_top_level_commas

    result: dict[str, list[tuple[str, ...]]] = {}
    for m in _CT_HEAD_RE.finditer(sql):
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            ch = sql[i]
            if ch == "'":
                i += 1
                while i < len(sql):
                    if sql[i : i + 2] == "''":
                        i += 2
                        continue
                    if sql[i] == "'":
                        break
                    i += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = sql[m.end() : i - 1]
        table = m.group(1).replace("[", "").replace("]", "").replace('"', "")
        table = table.split(".")[-1].lstrip("#").lower()
        pk: tuple[str, ...] | None = None
        uniques: list[tuple[str, ...]] = []
        for item in _split_top_level_commas(body):
            s = item.strip()
            mk = re.match(r"(?is)^(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*\((.*?)\)", s)
            if mk:
                pk = _key_column_list(mk.group(1))
                continue
            mu = re.match(
                r"(?is)^(?:CONSTRAINT\s+\S+\s+)?UNIQUE(?:\s+KEY|\s+INDEX)?"
                r"(?:\s+[\w`\"\[\]]+)?\s*\((.*?)\)",
                s,
            )
            if mu:
                uniques.append(_key_column_list(mu.group(1)))
                continue
            cm = re.match(r'\s*(\[[^\]]+\]|`[^`]+`|"[^"]+"|\w+)\s+', s)
            if not cm:
                continue
            name = cm.group(1).strip('[]"`')
            if name.upper() in _CT_ELEMENT_HEADS:
                continue
            if re.search(r"(?i)\bPRIMARY\s+KEY\b", s):
                pk = (name.lower(),)
            elif re.search(r"(?i)\bUNIQUE\b", s):
                uniques.append((name.lower(),))
        keys: list[tuple[str, ...]] = []
        if pk:
            keys.append(pk)
        keys.extend(u for u in uniques if u)
        if keys:
            result[table] = keys
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
