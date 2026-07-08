# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Main transpiler orchestrator: parse → transform → emit.

Supports two pipelines:
  1. DML/DDL pipeline: sqlglot-based parsing and emission.
  2. Procedural pipeline: custom lexer/parser for stored procedures,
     functions, triggers, and anonymous blocks.

The transpiler automatically routes each batch to the appropriate
pipeline based on content classification.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace

from unique.core.ast_nodes import (
    CommentStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
)
from unique.core.batch_splitter import _TSQL_SYSTEM_PROCS, BatchSplitter, BatchType
from unique.core.converter import (
    DATE_COLUMNS,
    IDENTITY_COLUMNS,
    PG_TRIGGER_FN_BODIES,
    PROC_DATE_PARAMS,
    TSQL_ALIAS_TYPES,
    TSQL_BIT_COLUMNS,
    USER_FUNCTIONS,
    harvest_date_columns,
    harvest_identity_columns,
    harvest_pg_trigger_functions,
    harvest_proc_date_params,
    harvest_tsql_alias_types,
    harvest_tsql_bit_columns,
    harvest_user_functions,
)
from unique.core.dialect import Dialect
from unique.core.errors import UnsupportedFeatureError
from unique.core.output_gate import degrade_to_carrier, gate_reason
from unique.core.procedural.emitter import ProceduralEmitter
from unique.core.procedural.parser import ProceduralParser
from unique.core.procedural.transformer import ProceduralTransformer
from unique.core.registry import DialectRegistry
from unique.core.sql_split import split_leading_trivia
from unique.core.transformer import Transformer, TransformWarning

logger = logging.getLogger(__name__)

# ONE recognizer for every T-SQL catalog migration-guard head (audit
# 2026-07-08, M2/P3 — three per-spelling regexes each had their own holes):
# ``IF [NOT] EXISTS (<catalog query>)`` and ``IF OBJECT_ID(…) IS [NOT] NULL``,
# followed by a single statement or a ``BEGIN … END`` block. The condition
# queries T-SQL system catalogs with no faithful cross-engine form, so the
# *intent* is kept: guarded DROPs become the target's conditional drop and
# guarded CREATEs the target's idempotent form (see ``_guard_idempotent``).
_TSQL_GUARD_HEAD_RE = re.compile(
    r"(?is)^\s*IF\s+(?:(?P<neg>NOT\s+)?EXISTS|(?P<objid>OBJECT_ID))\s*\("
)
_DROP_STMT_RE = re.compile(
    r"(?is)^\s*DROP\s+"
    r"(?P<kind>TABLE|VIEW|SEQUENCE|PROCEDURE|FUNCTION|TRIGGER|INDEX)\s+"
    r"(?P<name>[\w\[\]\".]+)"
)


# T-SQL "CREATE SCHEMA <name> [AUTHORIZATION <owner>]", possibly wrapped in
# dynamic SQL: "EXEC('CREATE SCHEMA …')". sqlglot leaves the EXEC(...) as an opaque
# Execute (its string argument is never transpiled), so this is handled directly.
_TSQL_CREATE_SCHEMA_RE = re.compile(
    r"(?is)^\s*(?:EXEC(?:UTE)?\s*\(\s*N?'\s*)?"
    r"CREATE\s+SCHEMA\s+(?P<name>\[?\w+\]?|\"[^\"]+\")"
    r"(?:\s+AUTHORIZATION\s+(?P<owner>\[?\w+\]?|\"[^\"]+\"))?"
    r"\s*(?:'\s*\))?\s*;?\s*$"
)

# T-SQL "ALTER TABLE t ALTER COLUMN c <type> [NULL|NOT NULL]". sqlglot cannot
# parse the trailing nullability (falls back to a Command) and emits a non-Oracle
# "ALTER COLUMN … SET DATA TYPE" for the type change, so this is handled directly.
_TSQL_ALTER_COLUMN_RE = re.compile(
    # A guarded ALTER arrives with its section-header comments re-attached, so
    # skip (and preserve) leading comment/blank lines before ALTER.
    r"(?is)^(?P<lead>(?:[^\S\n]*(?:--[^\n]*)?\n)*)[^\S\n]*"
    r"ALTER\s+TABLE\s+(?P<table>\[?\w+\]?(?:\s*\.\s*\[?\w+\]?)*)\s+"
    r"ALTER\s+COLUMN\s+(?P<col>\[?\w+\]?)\s+"
    r"(?P<type>[A-Za-z]\w*(?:\s*\(\s*[\w, ]+\s*\))?)"
    r"(?:\s+(?P<null>NOT\s+NULL|NULL))?\s*;?\s*$"
)

_ORACLE_CREATE_OBJ_RE = re.compile(
    r"(?is)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+|BITMAP\s+)*"
    r"(?P<kind>TABLE|INDEX|VIEW|SEQUENCE|SYNONYM|TYPE)\s+"
    r'(?:"?\w+"?\s*\.\s*)?"?(?P<name>\w+)"?'
)

# ``ALTER TABLE t ADD <col> …`` — a guarded column add whose T-SQL guard checked
# ``syscolumns``. Idempotent on Oracle via a ``user_tab_columns`` probe. Excludes
# ADD CONSTRAINT/PRIMARY/… (those add no column, so the column probe is wrong).
_ORACLE_ALTER_ADD_RE = re.compile(
    r'(?is)^\s*ALTER\s+TABLE\s+(?:"?\w+"?\s*\.\s*)?"?(?P<table>\w+)"?\s+'
    r"ADD\s+\(?\s*"
    r"(?!CONSTRAINT\b|PRIMARY\b|FOREIGN\b|UNIQUE\b|CHECK\b)"
    r'"?(?P<col>\w+)"?\b'
)

# ``ALTER TABLE t ADD CONSTRAINT c …`` — a guarded constraint add (FK/PK/UNIQUE);
# idempotent on Oracle via a ``user_constraints`` probe on the constraint name.
_ORACLE_ALTER_ADD_CONSTRAINT_RE = re.compile(
    r'(?is)^\s*ALTER\s+TABLE\s+(?:"?\w+"?\s*\.\s*)?"?\w+"?\s+'
    r'ADD\s+CONSTRAINT\s+"?(?P<name>\w+)"?\b'
)

# Leading blank / ``--`` comment lines (a section header often precedes the guarded
# DDL); kept and re-attached so the idempotent wrapper does not swallow them.
_ORACLE_LEADING_NOISE_RE = re.compile(r"(?s)^((?:[ \t]*(?:--[^\n]*)?\n)*)")


def _oracle_q_quote(s: str) -> str:
    """Wrap *s* in an Oracle ``q'…'`` literal, picking a delimiter whose closing
    sequence is absent so an embedded ``'`` never needs doubling."""
    for open_c, close_c in (("[", "]"), ("{", "}"), ("<", ">"), ("!", "!"), ("#", "#")):
        if close_c + "'" not in s:
            return f"q'{open_c}{s}{close_c}'"
    return "'" + s.replace("'", "''") + "'"  # pragma: no cover — degenerate DDL


def _oracle_idempotent_create(ddl: str) -> str | None:
    """Make a guarded ``CREATE`` or ``ALTER TABLE … ADD`` idempotent on Oracle.
    Oracle DDL cannot be a conditional (static) statement inside PL/SQL, so run it
    via ``EXECUTE IMMEDIATE`` only when the target is absent — a catalog probe over
    ``user_objects`` for a CREATE (covers every object type) or ``user_tab_columns``
    for an added column. Portable to every Oracle version (unlike ``… IF NOT
    EXISTS``, 23ai+). A leading section-header comment is preserved. Returns
    ``None`` when neither shape is recognized (caller keeps the bare DDL)."""
    lead = _ORACLE_LEADING_NOISE_RE.match(ddl)
    prefix, stmt = (ddl[: lead.end()], ddl[lead.end() :]) if lead else ("", ddl)

    create = _ORACLE_CREATE_OBJ_RE.match(stmt)
    constraint = _ORACLE_ALTER_ADD_CONSTRAINT_RE.match(stmt)
    if create:
        name, kind = create.group("name").upper(), create.group("kind").upper()
        probe = (
            f"SELECT 1 FROM user_objects WHERE object_name = '{name}' "
            f"AND object_type = '{kind}'"
        )
    elif constraint:
        cname = constraint.group("name").upper()
        probe = f"SELECT 1 FROM user_constraints WHERE constraint_name = '{cname}'"
    else:
        add = _ORACLE_ALTER_ADD_RE.match(stmt)
        if not add:
            return None
        table, col = add.group("table").upper(), add.group("col").upper()
        probe = (
            f"SELECT 1 FROM user_tab_columns WHERE table_name = '{table}' "
            f"AND column_name = '{col}'"
        )
    body = stmt.strip().rstrip(";").rstrip()
    return prefix + (
        "BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT EXISTS (\n"
        f"      {probe})) LOOP\n"
        f"    EXECUTE IMMEDIATE {_oracle_q_quote(body)};\n"
        "  END LOOP; END;"
    )


def _extract_catalog_guard(code: str) -> tuple[str, str, str] | None:
    """Parse a T-SQL catalog migration guard into ``(polarity, trivia, body)``.

    ``polarity`` is ``"absent"`` (run the body when the object does NOT exist:
    ``IF NOT EXISTS(…)`` / ``IF OBJECT_ID(…) IS NULL``) or ``"present"``
    (``IF EXISTS(…)`` / ``IS NOT NULL``). ``body`` is the guarded statement —
    a single ``BEGIN … END`` wrapper is unwrapped, a diagnostic ``ELSE``
    branch is cut, and leading ``PRINT``/``SET`` noise is dropped. ``trivia``
    is any comment found between the condition and the body (e.g. a trailing
    ``-- old name`` on the guard line) — preserved by the caller, never left
    in the body where it would defeat the DROP matcher (doc-04 P2). Returns
    ``None`` when *code* (which must already be trivia-free) is not a guard.
    """
    head = _TSQL_GUARD_HEAD_RE.match(code)
    if not head:
        return None
    # Skip the balanced-parens condition (it may nest parentheses).
    depth = 0
    i = head.end() - 1
    n = len(code)
    while i < n:
        ch = code[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0:
        return None
    rest = code[i + 1 :]
    if head.group("objid"):
        is_clause = re.match(r"(?is)^\s*IS\s+(?P<not>NOT\s+)?NULL\b", rest)
        if not is_clause:
            return None
        polarity = "present" if is_clause.group("not") else "absent"
        rest = rest[is_clause.end() :]
    else:
        polarity = "absent" if head.group("neg") else "present"
    # A trailing comment on the guard line (or between condition and body) is
    # trivia: capture it for the caller and match on the code.
    inner_trivia, rest = split_leading_trivia(rest.strip())
    rest = rest.strip()
    # A guard commonly has an ELSE branch — usually a diagnostic ``PRINT '… already
    # exists'``. Keep only the THEN branch; cut at a line-starting ELSE (so an
    # ELSE inside a CASE expression is left intact).
    else_cut = re.search(r"(?im)^\s*ELSE\b", rest)
    if else_cut:
        rest = rest[: else_cut.start()].strip()
    unwrapped = re.match(r"(?is)^BEGIN\b(.*)\bEND\b\s*;?\s*$", rest)
    if unwrapped:
        rest = unwrapped.group(1).strip()
        # Comments can also follow the BEGIN keyword itself.
        block_trivia, rest = split_leading_trivia(rest)
        if block_trivia.strip():
            inner_trivia += block_trivia
    # A guard body often opens with a diagnostic ``PRINT 'Creating X'`` (or a
    # SET) before the DDL; drop those leading noise lines so the DDL is what gets
    # transpiled (the message is not worth carrying, and mixing it in would make
    # sqlglot degrade the whole block to a Command carrier).
    while True:
        noise = re.match(r"(?is)^\s*(?:PRINT|SET)\b[^\n]*(?:\n|$)", rest)
        if not noise:
            break
        rest = rest[noise.end() :].lstrip()
    if not rest:
        return None
    return polarity, inner_trivia, rest


# A MySQL routine whose body contains ';' statement terminators must be wrapped
# in a DELIMITER block so a client doesn't cut the script at the first inner
# ';'. Matches the leading keyword of a compound routine definition (any
# leading line comments are allowed before it).
_MYSQL_ROUTINE_RE = re.compile(
    r"(?s)^(?:\s*--[^\n]*\n)*\s*" r"CREATE\s+(?:PROCEDURE|FUNCTION|TRIGGER)\b",
    re.IGNORECASE,
)


def _warn(message: str, feature: str, source: str, target: str) -> TransformWarning:
    """Build a TransformWarning with dialect context."""
    return TransformWarning(
        message=message,
        feature=feature,
        source_dialect=source,
        target_dialect=target,
    )


def _aggregate_warnings(warnings: list[TransformWarning]) -> list[TransformWarning]:
    """Collapse duplicate warnings into one entry with a count (doc 04, M1c).

    A real migration dump repeats the same lossy construct hundreds of times
    (e.g. ``SET NOEXEC OFF`` per revision block); one warning per occurrence
    buries the signal the no-silent-loss invariant depends on. Duplicates —
    same feature and message — keep the first occurrence's position and gain
    an ``(xN)`` suffix.
    """
    counts: dict[tuple[str, str], int] = {}
    order: list[TransformWarning] = []
    for warning in warnings:
        key = (warning.feature, warning.message)
        if key in counts:
            counts[key] += 1
        else:
            counts[key] = 1
            order.append(warning)
    result: list[TransformWarning] = []
    for warning in order:
        count = counts[(warning.feature, warning.message)]
        if count == 1:
            result.append(warning)
        else:
            result.append(
                TransformWarning(
                    message=f"{warning.message} (x{count})",
                    feature=warning.feature,
                    source_dialect=warning.source_dialect,
                    target_dialect=warning.target_dialect,
                )
            )
    return result


_QI_OFF_RE = re.compile(r"(?im)^\s*SET\s+QUOTED_IDENTIFIER\s+OFF\b")
_QI_ON_RE = re.compile(r"(?im)^\s*SET\s+QUOTED_IDENTIFIER\s+ON\b")

# No-silent-loss invariant (audit 2026-07-02): a "UNIQUE:" carrier comment in
# the output marks a lossy conversion, and every such carrier must be mirrored
# in TranspileResult.warnings so API/CLI consumers get a programmatic signal.
_CARRIER_RE = re.compile(r"UNIQUE:\s*(?P<frag>[^\n]*)")


def _carrier_fragments(sql: str) -> list[str]:
    """Extract the message fragment of each UNIQUE carrier comment in *sql*.

    The fragment is the carrier text up to (excluding) a trailing
    "Original:" marker, deduplicated preserving order.
    """
    seen: set[str] = set()
    fragments: list[str] = []
    for match in _CARRIER_RE.finditer(sql):
        frag = match.group("frag").strip()
        frag = re.sub(r"\s*Original:\s*$", "", frag).rstrip(" .;")
        frag = frag.rstrip("*/ ").rstrip()
        if frag and frag not in seen:
            seen.add(frag)
            fragments.append(frag)
    return fragments


def _warning_covers(fragment: str, messages: list[str]) -> bool:
    """Return True if any warning message already reports *fragment*.

    Coverage is a 3-consecutive-word overlap between the carrier fragment and
    a warning message: warnings and carriers phrase the same fact differently,
    but a real match always shares a distinctive run of words (e.g. "system
    procedure sp_rename"). This keeps the synthesized warnings from
    duplicating an already-registered one.
    """
    words = re.findall(r"[a-z0-9_]+", fragment.lower())
    if len(words) < 3:
        return any(fragment.lower() in m.lower() for m in messages)
    shingles = {" ".join(words[i : i + 3]) for i in range(len(words) - 2)}
    for message in messages:
        mwords = re.findall(r"[a-z0-9_]+", message.lower())
        msg_shingles = {" ".join(mwords[i : i + 3]) for i in range(len(mwords) - 2)}
        if shingles & msg_shingles:
            return True
    return False


def _double_quoted_to_strings(sql: str) -> str:
    """Rewrite ``"..."`` double-quoted tokens to ``'...'`` string literals.

    Under T-SQL ``SET QUOTED_IDENTIFIER OFF``, double quotes delimit a string
    literal (not an identifier), so ``CHARINDEX(",", s)`` searches for a comma.
    The downstream parser (sqlglot) assumes QUOTED_IDENTIFIER ON and would read
    ``","`` as an identifier. When OFF is in effect we convert every
    double-quoted token to a single-quoted string, escaping embedded single
    quotes (``'`` -> ``''``) and unescaping doubled double-quotes (``""`` ->
    ``"``). Single-quoted strings and ``[bracketed]`` identifiers are left
    untouched.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        # Copy comments verbatim so a '"' inside them is not converted.
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            j = sql.find("\n", i)
            j = n if j == -1 else j
            out.append(sql[i:j])
            i = j
            continue
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(sql[i:j])
            i = j
            continue
        if ch == "'":
            # Copy a single-quoted string verbatim, honoring '' escapes.
            out.append(ch)
            i += 1
            while i < n:
                out.append(sql[i])
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        out.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if ch == '"':
            i += 1
            content: list[str] = []
            while i < n:
                if sql[i] == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        content.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                content.append(sql[i])
                i += 1
            out.append("'" + "".join(content).replace("'", "''") + "'")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# T-SQL adds a column default with a *named or unnamed* constraint:
# ``ALTER TABLE t ADD [CONSTRAINT n] DEFAULT <val> FOR <col>``. sqlglot passes
# this through unchanged (invalid elsewhere), so rewrite it to each target's
# set-default form before parsing.
_TSQL_ADD_DEFAULT_RE = re.compile(
    r"(?is)^(?P<head>\s*ALTER\s+TABLE\s+[\w\[\].\"]+)\s+ADD\s+"
    r'(?:CONSTRAINT\s+[\w\[\]"]+\s+)?DEFAULT\s+(?P<val>.+?)\s+FOR\s+'
    r'(?P<col>[\w\[\]"]+)\s*;?\s*$'
)


def _rewrite_tsql_default_constraint(sql: str) -> str:
    """``ALTER TABLE t ADD [CONSTRAINT n] DEFAULT v FOR c`` -> the ANSI
    ``ALTER TABLE t ALTER COLUMN c SET DEFAULT v`` (which sqlglot parses and
    whose value it translates). Oracle's ``MODIFY`` form is a post-emit fixup."""
    m = _TSQL_ADD_DEFAULT_RE.match(sql)
    if not m:
        return sql
    head, val, col = m.group("head"), m.group("val").strip(), m.group("col")
    return f"{head} ALTER COLUMN {col} SET DEFAULT {val}"


# Oracle sets a column default with ``MODIFY col DEFAULT v`` (no SET); sqlglot
# leaves the ANSI ``ALTER COLUMN … SET DEFAULT`` unchanged, so fix it up.
_ORACLE_ALTER_DEFAULT_RE = re.compile(
    r"(?i)\bALTER\s+COLUMN\s+(?P<col>[\w\[\]\".]+)\s+SET\s+DEFAULT\b"
)


# A (possibly schema-qualified) identifier: a [bracketed] name may hold any char
# but ']' (SSMA constraint names embed '$'), a "quoted" one any but '"'.
_TSQL_ID = r'(?:\[[^\]]+\]|"[^"]+"|[\w$]+)'
_TSQL_QNAME = rf"(?:{_TSQL_ID}\.)*{_TSQL_ID}"

# T-SQL enables/disables constraint checking: ``ALTER TABLE t [WITH [NO]CHECK]
# {CHECK|NOCHECK} CONSTRAINT {name|ALL}`` (SSMA emits these around bulk loads).
_TSQL_CHECK_CONSTRAINT_RE = re.compile(
    rf"(?is)^(?P<head>\s*ALTER\s+TABLE\s+{_TSQL_QNAME})\s+"
    r"(?:WITH\s+(?:NO)?CHECK\s+)?(?P<op>NOCHECK|CHECK)\s+CONSTRAINT\s+"
    rf"(?P<name>{_TSQL_QNAME}|ALL)\s*;?\s*$"
)


def _rewrite_tsql_constraint_state(sql: str, target: str) -> str | None:
    """``ALTER TABLE t {CHECK|NOCHECK} CONSTRAINT c`` -> the target's
    enable/disable form. Returns ``None`` if *sql* is not that shape, or ``""``
    when the target has no equivalent (caller emits a restorable note)."""
    m = _TSQL_CHECK_CONSTRAINT_RE.match(sql)
    if not m:
        return None
    head, op, name = m.group("head"), m.group("op").upper(), m.group("name")
    if name.upper() == "ALL":
        return ""  # no clean per-target "all constraints" form
    # We bypass sqlglot here, so convert the T-SQL [brackets] to bare identifiers
    # (as sqlglot would for these targets); the note keeps the original.
    head = re.sub(r"\[([^\]]+)\]", r"\1", head)
    name = re.sub(r"\[([^\]]+)\]", r"\1", name)
    if target == "oracle":
        return f"{head} {'ENABLE' if op == 'CHECK' else 'DISABLE'} CONSTRAINT {name}"
    if target == "postgresql" and op == "CHECK":
        return f"{head} VALIDATE CONSTRAINT {name}"
    return ""  # PostgreSQL NOCHECK / MySQL: no equivalent


def _parses_in_target(sql: str, target: str) -> bool:
    """Whether every statement in *sql* parses as valid target SQL. Used to fall
    back to a documented carrier when a rewrite would emit invalid output."""
    import sqlglot

    from unique.core.converter import sqlglot_dialect_name

    try:
        dialect = sqlglot_dialect_name(target)
        for part in sql.split(";"):
            stmt = part.strip()
            if not stmt or stmt.startswith("--"):
                continue
            sqlglot.parse_one(
                stmt, dialect=dialect, error_level=sqlglot.ErrorLevel.RAISE
            )
        return True
    except Exception:
        return False


# A PL/SQL block or stored program unit: Oracle needs a ``/`` terminator to run
# it (its internal ``;`` do not terminate the statement). A plain ``;``-ended
# DML/DDL statement must NOT be followed by ``/`` — that re-executes it.
_ORACLE_PLSQL_RE = re.compile(
    r"(?is)^\s*(?:"
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
    r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b"
    r"|DECLARE\b|BEGIN\b"
    r")"
)


# A stored program unit CREATE anywhere in the chunk (a table-variable GTT is
# hoisted as plain ``;``-terminated DDL *before* the CREATE PROCEDURE, so the
# block still needs a trailing ``/`` even though the chunk starts with DDL).
_ORACLE_PLSQL_UNIT_RE = re.compile(
    r"(?im)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
    r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b"
)


def _harvest_split_tvf_names(sql: str) -> set[str]:
    """Names of T-SQL inline table-valued functions that split a string (a
    ``RETURNS TABLE`` body using ``STRING_SPLIT``) — emitted on Oracle as
    ``SYS.ODCIVARCHAR2LIST`` functions whose callers need ``TABLE(fn(…))``."""
    return {
        m.lower()
        for m in re.findall(
            r"(?is)(?:CREATE|ALTER)\s+FUNCTION\s+(?:\[?\w+\]?\.)?\[?(\w+)\]?\s*"
            r"\((?:[^()]|\([^()]*\))*\)\s*RETURNS\s+TABLE\b.{0,300}?\bSTRING_SPLIT\b",
            sql,
        )
    }


def _rewrite_tvf_callers(sql: str, names: set[str]) -> str:
    """Wrap a split-TVF call in a FROM clause with ``TABLE(…)`` and read its
    single column as ``COLUMN_VALUE`` (the ODCIVARCHAR2LIST column)."""
    for name in names:
        n = re.escape(name)
        sql = re.sub(
            rf"(?i)\bSELECT\s+\w+\s+FROM\s+({n}\s*\([^)]*\))",
            r"SELECT column_value FROM TABLE(\1)",
            sql,
        )
        sql = re.sub(rf"(?i)\bFROM\s+({n}\s*\([^)]*\))", r"FROM TABLE(\1)", sql)
    return sql


def _oracle_needs_slash(sql: str) -> bool:
    """Whether an emitted Oracle statement is a PL/SQL block needing a ``/``.

    Leading trivia (line AND block comments) is stripped first — a section
    header in front of a guard block must not suppress the terminator, or
    every statement after it is swallowed into the block (audit 2026-07-08,
    A3)."""
    _, code = split_leading_trivia(sql)
    body = "\n".join(
        line for line in code.splitlines() if not line.lstrip().startswith("--")
    ).strip()
    return bool(body) and (
        bool(_ORACLE_PLSQL_RE.match(body)) or bool(_ORACLE_PLSQL_UNIT_RE.search(body))
    )


# SQLite source functions sqlglot leaves untranslated. Rewritten per target in
# the emitted output (SQLite is import-only, so these only ever run source-side).
_SQLITE_RANDOM = {
    "postgresql": "RANDOM()",
    "oracle": "DBMS_RANDOM.VALUE",
    "mysql": "RAND()",
    "tsql": "RAND()",
}
_SQLITE_CURRENT_DATE = {
    "tsql": "CAST(GETDATE() AS DATE)",
    "oracle": "TRUNC(SYSDATE)",
    "postgresql": "CURRENT_DATE",
    "mysql": "CURRENT_DATE",
}


def _rewrite_sqlite_functions(sql: str, target: str) -> str:
    """Rewrite SQLite-only functions in emitted output to the target's form."""
    from unique.core.mappings import CURRENT_TIMESTAMP_EXPR, LAST_IDENTITY_EXPR

    # last_insert_rowid() -> the target's last-identity expression (Oracle has no
    # session function for it, so leave the SQLite call as a visible marker).
    last_id = LAST_IDENTITY_EXPR.get(target, "")
    if last_id and not last_id.startswith("/*"):
        sql = re.sub(r"(?i)\blast_insert_rowid\s*\(\s*\)", last_id, sql)
    # datetime('now') / date('now') -> current timestamp / current date.
    sql = re.sub(
        r"(?i)\bdatetime\s*\(\s*'now'\s*\)",
        CURRENT_TIMESTAMP_EXPR.get(target, "CURRENT_TIMESTAMP"),
        sql,
    )
    sql = re.sub(
        r"(?i)\bdate\s*\(\s*'now'\s*\)",
        _SQLITE_CURRENT_DATE.get(target, "CURRENT_DATE"),
        sql,
    )
    # SQLite random() -> RAND() via sqlglot; fix the engines that spell it
    # differently (PostgreSQL RANDOM(), Oracle DBMS_RANDOM.VALUE).
    if target in ("postgresql", "oracle"):
        sql = re.sub(r"(?i)\bRAND\s*\(\s*\)", _SQLITE_RANDOM[target], sql)
    return sql


def _is_comment_only(sql: str) -> bool:
    """Whether ``sql`` consists solely of blank lines and ``--`` comments."""
    stripped = sql.strip()
    if not stripped:
        return False
    return all(
        not line.strip() or line.lstrip().startswith("--")
        for line in stripped.splitlines()
    )


# SQL Server keeps comments that precede a CREATE PROCEDURE/FUNCTION/TRIGGER as
# part of the stored module text; Oracle, PostgreSQL and MySQL store a routine
# only from the CREATE keyword on, so those leading comments are lost on load.
# For these targets we re-home them inside the routine body (see
# _transpile_procedural) instead of emitting them before the CREATE.
_ROUTINE_COMMENT_TARGETS = ("oracle", "postgresql", "mysql")


def _leading_comment_nodes(text: str) -> list[CommentStatement]:
    """Parse a run of leading ``--`` / ``/* … */`` comments into IR nodes."""
    nodes: list[CommentStatement] = []
    for match in re.finditer(r"--[^\n]*|/\*.*?\*/", text, re.S):
        raw = match.group(0)
        nodes.append(
            CommentStatement(
                text=raw,
                style="block" if raw.startswith("/*") else "line",
                header=True,
            )
        )
    return nodes


_COMPOUND_ASSIGN_RE = re.compile(
    # column (optionally schema/table-qualified or [bracketed]) then one of the
    # T-SQL compound assignment operators, captured so we can expand it.
    r"(?P<col>(?:\[[^\]]+\]|[A-Za-z_][\w$]*)(?:\.(?:\[[^\]]+\]|[A-Za-z_][\w$]*))*)"
    r"\s*(?P<op>\+=|-=|\*=|/=|%=|&=|\|=|\^=)\s*"
)


def _expand_tsql_compound_assignment(sql: str) -> str:
    """Expand T-SQL compound assignment in an UPDATE SET list.

    sqlglot does not parse ``SET a += 1`` and silently drops the column
    (yielding ``SET = 1`` — invalid SQL and data loss). Rewrite each
    ``col <op>= expr`` to the portable ``col = col <op> expr`` form before
    sqlglot sees it. Only applied to UPDATE statements, and only to the SET
    list, so comparison operators elsewhere are untouched.
    """
    m = re.search(r"(?i)\bUPDATE\b.*?\bSET\b", sql, re.DOTALL)
    if not m:
        return sql
    set_start = m.end()
    # The SET list ends at WHERE / FROM / the statement end.
    tail = re.search(r"(?i)\b(WHERE|FROM)\b", sql[set_start:])
    set_end = set_start + tail.start() if tail else len(sql)
    head, set_list, rest = sql[:set_start], sql[set_start:set_end], sql[set_end:]

    def repl(mo: re.Match[str]) -> str:
        col, op = mo.group("col"), mo.group("op")[0]  # "+=" -> "+"
        return f"{col} = {col} {op} "

    return head + _COMPOUND_ASSIGN_RE.sub(repl, set_list) + rest


def _extract_tsql_output(sql: str) -> tuple[str, str | None]:
    """Extract a T-SQL OUTPUT clause from a single DML statement.

    Returns ``(base_sql_without_output, output_columns)`` or
    ``(sql, None)`` if there is no OUTPUT clause. The OUTPUT clause in T-SQL
    appears after the target/SET list and before WHERE/VALUES/FROM, so it is
    removed in place, preserving the rest of the statement (crucially the
    WHERE clause, whose loss would change DELETE/UPDATE semantics).

    Only the simple ``OUTPUT <cols>`` form is handled (not ``OUTPUT ... INTO
    <table>``); the latter returns ``(sql, None)`` so it is left untouched.
    """
    # OUTPUT ... INTO is a different construct (insert into a target table);
    # do not treat it as a returning clause.
    if re.search(r"(?i)\bOUTPUT\b.*\bINTO\b", sql):
        return sql, None
    m = re.search(r"(?i)\bOUTPUT\b\s+(.*?)(?=\s+\b(?:WHERE|VALUES|FROM)\b|;|$)", sql)
    if not m:
        return sql, None
    output_cols = m.group(1).strip()
    if not output_cols:
        return sql, None
    base = (sql[: m.start()].rstrip() + " " + sql[m.end() :].lstrip()).strip()
    return base, output_cols


@dataclass(frozen=True)
class TranspileOptions:
    """Options controlling transpilation behavior."""

    preserve_comments: bool = True
    include_warnings: bool = True
    format_output: bool = True
    db_url: str | None = None


@dataclass
class TranspileResult:
    """Result of a transpilation operation."""

    sql: str
    warnings: list[TransformWarning] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        """Whether the result includes any warnings."""
        return len(self.warnings) > 0

    @property
    def has_unsupported(self) -> bool:
        """Whether any features were unsupported."""
        return len(self.unsupported) > 0


class Transpiler:
    """Orchestrates SQL transpilation between dialects.

    The transpilation pipeline:
    0. Split input into batches using dialect-specific separators.
    1. Classify each batch as procedural or DML/DDL.
    2. Route procedural batches through the procedural engine.
    3. Route DML/DDL batches through the sqlglot-based pipeline.
    4. Join results into a single output script.
    """

    def __init__(self, registry: DialectRegistry | None = None) -> None:
        """Initialize the transpiler.

        Args:
            registry: A DialectRegistry to use. If None, auto-discovers
                      built-in dialects.
        """
        self.registry = registry or DialectRegistry.with_builtins()

    def transpile(
        self,
        sql: str,
        source: str,
        target: str,
        options: TranspileOptions | None = None,
    ) -> TranspileResult:
        """Transpile SQL from one dialect to another.

        Args:
            sql: The source SQL text.
            source: The source dialect name (e.g. 'tsql').
            target: The target dialect name (e.g. 'postgresql').
            options: Optional transpilation options.

        Returns:
            A TranspileResult with the target SQL, warnings, and
            unsupported feature list.

        Raises:
            UnknownDialectError: If source or target dialect is not registered.
            ParseError: If the source SQL cannot be parsed.
            EmitError: If the IR cannot be emitted as the target dialect.
        """
        options = options or TranspileOptions()

        # Validate dialects
        source_dialect = self.registry.get(source)
        target_dialect = self.registry.get(target)
        if target_dialect.source_only:
            raise UnsupportedFeatureError(
                f"{target} is import-only (a source only, never a target)",
                source,
                target,
            )

        logger.info("Transpiling from %s to %s", source, target)

        # Optional metadata resolver for %TYPE references
        metadata_resolver = None
        if options.db_url:
            try:
                from unique.core.metadata import MetadataResolver

                metadata_resolver = MetadataResolver.from_url(options.db_url)
                logger.info("Connected to metadata database")
            except Exception as e:
                logger.warning("Could not connect to metadata database: %s", e)

        # T-SQL alias types (CREATE TYPE x FROM base) defined anywhere in the
        # script: harvest them up front so columns typed with an alias resolve
        # to the base type on engines without alias types.
        alias_token = None
        bit_token = None
        date_token = None
        identity_token = None
        proc_date_token = None
        func_token = None
        if source == "tsql" and target != "tsql":
            aliases = harvest_tsql_alias_types(sql)
            if aliases:
                alias_token = TSQL_ALIAS_TYPES.set(aliases)
            if target == "postgresql":
                bit_columns = harvest_tsql_bit_columns(sql)
                if bit_columns:
                    bit_token = TSQL_BIT_COLUMNS.set(bit_columns)
        # Oracle can't read a bare ISO date string into a date column; harvest
        # date columns (any source dialect) so their literals are wrapped.
        if target == "oracle" and source != "oracle":
            date_columns = harvest_date_columns(sql)
            if date_columns:
                date_token = DATE_COLUMNS.set(date_columns)
            proc_date_params = harvest_proc_date_params(sql)
            if proc_date_params:
                proc_date_token = PROC_DATE_PARAMS.set(proc_date_params)
        # A row-level trigger becomes a T-SQL statement-level trigger keyed on the
        # table's identity/PK (``… WHERE <pk> IN (SELECT <pk> FROM inserted)``),
        # and its scalar-UDF calls must be qualified ``dbo.<fn>``; harvest both
        # (also identity for the Oracle target's compound-trigger synthesis).
        if target in ("oracle", "tsql") and source != target:
            identity_columns = harvest_identity_columns(sql)
            if identity_columns:
                identity_token = IDENTITY_COLUMNS.set(identity_columns)
        pg_trigger_fn_token = None
        if target == "tsql" and source != "tsql":
            user_functions = harvest_user_functions(sql)
            if user_functions:
                func_token = USER_FUNCTIONS.set(user_functions)
        # A PostgreSQL trigger function is inlined into its T-SQL trigger.
        if target == "tsql" and source == "postgresql":
            pg_trigger_fns = harvest_pg_trigger_functions(sql)
            if pg_trigger_fns:
                pg_trigger_fn_token = PG_TRIGGER_FN_BODIES.set(pg_trigger_fns)

        try:
            # Step 0: Split into batches
            batches = BatchSplitter.split(sql, source)
            logger.debug("Split into %d batches", len(batches))

            all_warnings: list[TransformWarning] = []
            all_unsupported: list[str] = []
            output_parts: list[tuple[str, bool]] = []  # (sql, is_comment)
            # Carrier fragments already reconciled against the warnings, so a
            # fragment repeated across thousands of batches (a big migration dump)
            # is checked once, not O(carriers × warnings) — that reconciliation
            # was the dominant super-linear cost on very large scripts.
            reconciled_frags: set[str] = set()
            unsupported_seen: set[str] = set()
            # Running T-SQL QUOTED_IDENTIFIER state: under OFF, double-quoted
            # tokens are string literals, so subsequent batches are preprocessed
            # to convert "..." -> '...' before parsing.
            quoted_identifier_off = False

            for batch in batches:
                # Skip empty batches, but keep explicit COMMENT batches: they
                # have no executable SQL yet carry information worth preserving
                # (e.g. Oracle 'rem'/'prompt' notices) in the output.
                if batch.is_empty and batch.batch_type != BatchType.COMMENT:
                    continue

                # Track SET QUOTED_IDENTIFIER ON/OFF so later batches read
                # double quotes correctly (T-SQL source only).
                if source == "tsql":
                    if _QI_OFF_RE.search(batch.sql):
                        quoted_identifier_off = True
                    elif _QI_ON_RE.search(batch.sql):
                        quoted_identifier_off = False
                    if quoted_identifier_off and '"' in batch.sql:
                        batch = replace(batch, sql=_double_quoted_to_strings(batch.sql))

                if batch.batch_type == BatchType.PROCEDURAL:
                    result = self._transpile_procedural(
                        batch.sql, source, target, metadata_resolver
                    )
                elif batch.batch_type == BatchType.SET_OPTION:
                    # T-SQL catalog migration guards (IF OBJECT_ID()/EXISTS()
                    # …) are not SET options — extract and translate the intent.
                    # Match on the trivia-free code (comments are trivia, doc-04
                    # P2 — a section-header comment must never defeat a guard
                    # recognizer) and re-attach the trivia to the result.
                    trivia, code = split_leading_trivia(batch.sql)
                    guard = (
                        _extract_catalog_guard(code)
                        if source == "tsql" and target != "tsql"
                        else None
                    )
                    if guard is not None:
                        polarity, inner_trivia, body = guard
                        if inner_trivia.strip():
                            trivia = (
                                f"{trivia.rstrip()}\n{inner_trivia}"
                                if trivia.strip()
                                else inner_trivia
                            )
                        drop_stmt = (
                            _DROP_STMT_RE.match(body) if polarity == "present" else None
                        )
                        if drop_stmt:
                            # IF EXISTS/IS NOT NULL + DROP: the target's own
                            # conditional drop keeps the re-runnable intent.
                            result = self._transpile_drop_guard(
                                drop_stmt.group("kind"),
                                drop_stmt.group("name"),
                                source,
                                target,
                            )
                        else:
                            # Any other guarded statement: transpile the body
                            # (the catalog condition has no target form) and
                            # restore the idempotent intent where the target
                            # has one (CREATE … IF NOT EXISTS / Oracle probe).
                            result = self._transpile_dml(
                                body, source, target, source_dialect, target_dialect
                            )
                            if polarity == "absent":
                                result = self._guard_idempotent(result, source, target)
                    else:
                        trivia = ""  # the fallback keeps the whole batch text
                        result = self._transpile_set_option(batch.sql, source, target)
                    if trivia.strip():
                        result = TranspileResult(
                            sql=f"{trivia.rstrip()}\n{result.sql}",
                            warnings=result.warnings,
                            unsupported=result.unsupported,
                        )
                elif batch.batch_type == BatchType.COMMENT:
                    # Comments carry no executable SQL; preserve them verbatim
                    # (already normalized to '-- ...' line comments).
                    result = TranspileResult(sql=batch.sql, warnings=[], unsupported=[])
                else:
                    result = self._transpile_dml(
                        batch.sql, source, target, source_dialect, target_dialect
                    )

                # Output validity gate (doc 04, M1): never ship output we can
                # tell is invalid on the target — degrade it to the documented
                # carrier + warning + unsupported entry instead. The gate only
                # detects; the fix belongs in the AST paths.
                if batch.batch_type != BatchType.COMMENT and not _is_comment_only(
                    result.sql
                ):
                    gate = gate_reason(result.sql, target)
                    if gate is not None:
                        message = (
                            f"output failed the {target} validity check "
                            f"({gate}); original {source} batch preserved"
                        )
                        result = TranspileResult(
                            sql=degrade_to_carrier(batch.sql, gate, source, target),
                            warnings=[
                                *result.warnings,
                                _warn(message, "validity_gate", source, target),
                            ],
                            unsupported=[*result.unsupported, message],
                        )

                terminated = self._ensure_terminated(
                    result.sql, target, batch.batch_type
                )
                if target == "mysql":
                    terminated = self._wrap_mysql_routine(terminated)
                # Treat output that is *entirely* comments as a comment part,
                # even if the batch wasn't classified as COMMENT (e.g. an
                # unsupported SET we turned into a '-- ...' note). This avoids
                # emitting a GO/';' separator after a pure comment.
                is_comment = batch.batch_type == BatchType.COMMENT or _is_comment_only(
                    terminated
                )
                output_parts.append((terminated, is_comment))
                all_warnings.extend(result.warnings)
                all_unsupported.extend(result.unsupported)

                # No-silent-loss invariant: every UNIQUE carrier in this
                # batch's output must be mirrored programmatically. Synthesize
                # a warning for any carrier not already covered, and register
                # an unsupported entry when an executable batch was reduced to
                # comments (i.e. the statement was dropped from the output).
                if batch.batch_type != BatchType.COMMENT:
                    frags = _carrier_fragments(terminated)
                    new_frags = [f for f in frags if f not in reconciled_frags]
                    if new_frags:
                        existing = [w.message for w in all_warnings]
                        for frag in new_frags:
                            reconciled_frags.add(frag)
                            if not _warning_covers(frag, existing):
                                all_warnings.append(
                                    _warn(frag, "lossy_conversion", source, target)
                                )
                                existing.append(frag)
                    if is_comment:
                        for frag in frags:
                            if frag not in unsupported_seen:
                                unsupported_seen.add(frag)
                                all_unsupported.append(frag)

            output_sql = self._join_parts(output_parts, target)

            # A T-SQL split TVF becomes an Oracle ODCIVARCHAR2LIST function; its
            # callers must read COLUMN_VALUE FROM TABLE(fn(…)). Rewrite them once
            # the whole (multi-object) script is assembled.
            if target == "oracle":
                tvf_names = _harvest_split_tvf_names(sql)
                if tvf_names:
                    output_sql = _rewrite_tvf_callers(output_sql, tvf_names)

            return TranspileResult(
                sql=output_sql,
                warnings=_aggregate_warnings(all_warnings),
                unsupported=all_unsupported,
            )
        finally:
            if alias_token is not None:
                TSQL_ALIAS_TYPES.reset(alias_token)
            if bit_token is not None:
                TSQL_BIT_COLUMNS.reset(bit_token)
            if date_token is not None:
                DATE_COLUMNS.reset(date_token)
            if identity_token is not None:
                IDENTITY_COLUMNS.reset(identity_token)
            if proc_date_token is not None:
                PROC_DATE_PARAMS.reset(proc_date_token)
            if func_token is not None:
                USER_FUNCTIONS.reset(func_token)
            if pg_trigger_fn_token is not None:
                PG_TRIGGER_FN_BODIES.reset(pg_trigger_fn_token)
            if metadata_resolver:
                metadata_resolver.close()

    def _join_parts(self, parts: list[tuple[str, bool]], target: str) -> str:
        """Join emitted parts, choosing the right delimiter between each pair.

        A comment part is attached to what follows with a plain newline rather
        than the batch separator, so we don't emit a useless ``GO`` (T-SQL) or
        ``/`` (Oracle) after a comment. The batch separator is only used
        between two executable parts.

        Oracle's ``/`` executes the SQL*Plus buffer, so it must follow **only**
        PL/SQL blocks (which internal ``;`` don't terminate); after a plain
        ``;``-terminated DML/DDL statement a ``/`` would re-run it. So for Oracle
        the delimiter is chosen per preceding statement, and a trailing PL/SQL
        block still gets its own ``/``.
        """
        if not parts:
            return ""
        default_sep = self._get_batch_separator(target)
        oracle = target == "oracle"
        # Accumulate pieces and join once: repeated ``out += …`` copies the whole
        # (multi-MB) accumulator each time — O(n²) — which dominated very large
        # scripts. The trailing-newline rstrip only affects the previous piece.
        pieces = [parts[0][0]]
        for i in range(1, len(parts)):
            prev_text, prev_is_comment = parts[i - 1]
            text, _ = parts[i]
            if prev_is_comment:
                # Glue the comment to the following part with a newline.
                pieces[-1] = pieces[-1].rstrip("\n")
                pieces.append("\n" + text)
            elif oracle:
                sep = "\n/\n\n" if _oracle_needs_slash(prev_text) else "\n\n"
                pieces.append(sep + text)
            else:
                pieces.append(default_sep + text)
        if oracle:
            last_text, last_is_comment = parts[-1]
            if not last_is_comment and _oracle_needs_slash(last_text):
                pieces.append("\n/")
        return "".join(pieces)

    def _transpile_procedural(
        self,
        sql: str,
        source: str,
        target: str,
        metadata_resolver: object | None = None,
    ) -> TranspileResult:
        """Transpile a procedural batch through the procedural engine."""
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        # The procedural parser starts at the first keyword and drops any comment
        # lines/blocks that precede the routine (e.g. a "-- <codegen> …" header).
        # Capture them here so they are re-attached to the emitted output.
        lead = re.match(r"(?s)^([ \t]*(?:--[^\n]*\n|/\*.*?\*/[ \t]*\n?)+)", sql)
        leading_comments = lead.group(1).rstrip("\n") + "\n" if lead else ""

        try:
            # Parse
            parser = ProceduralParser(source)
            parse_result = parser.parse(sql)

            if parse_result.errors:
                for err in parse_result.errors:
                    warnings.append(
                        _warn(
                            f"Parse error: {err.message}",
                            "procedural_parse",
                            source,
                            target,
                        )
                    )

            if parse_result.warnings:
                for w in parse_result.warnings:
                    warnings.append(_warn(w, "procedural_parse", source, target))

            if parse_result.node is None:
                return TranspileResult(
                    sql=f"/* PARSE ERROR */\n{sql}",
                    warnings=warnings,
                    unsupported=unsupported,
                )

            # Transform
            if source != target:
                transformer = ProceduralTransformer(source, target, metadata_resolver)
                node = transformer.transform(parse_result.node)
                for w in transformer.warnings:
                    warnings.append(_warn(w, "procedural_transform", source, target))
            else:
                node = parse_result.node

            # A routine's header comment lives where each engine stores it: SQL
            # Server keeps comments that precede CREATE as part of the module;
            # Oracle/PostgreSQL/MySQL store a routine only from CREATE on, so the
            # comment must sit inside. Move it to the target's home so it survives
            # the round-trip (T-SQL ⇄ Oracle) instead of being dropped.
            if isinstance(
                node,
                (
                    CreateProcedureStatement,
                    CreateFunctionStatement,
                    CreateTriggerStatement,
                ),
            ):
                if target in _ROUTINE_COMMENT_TARGETS and leading_comments:
                    # Forward: pull the pre-CREATE comments inside (flagged so the
                    # emitter hoists them to the head of the declaration section).
                    homed = _leading_comment_nodes(leading_comments)
                    if homed:
                        node = replace(node, body=(*homed, *node.body))
                        leading_comments = ""
                elif target == "tsql":
                    # Reverse: a header comment the source kept inside the routine
                    # belongs before the CREATE in the T-SQL module — pull it out.
                    inside = [
                        c
                        for c in node.body
                        if isinstance(c, CommentStatement) and c.header
                    ]
                    if inside:
                        leading_comments += "".join(c.text + "\n" for c in inside)
                        node = replace(
                            node,
                            body=tuple(
                                c
                                for c in node.body
                                if not (isinstance(c, CommentStatement) and c.header)
                            ),
                        )

            # Emit
            emitter = ProceduralEmitter(target)
            output_sql = emitter.emit(node)

            return TranspileResult(
                sql=leading_comments + output_sql,
                warnings=warnings,
                unsupported=unsupported,
            )

        except Exception as e:
            logger.warning("Procedural transpilation failed: %s", e)
            warnings.append(
                _warn(
                    f"Procedural transpilation failed: {e}",
                    "procedural",
                    source,
                    target,
                )
            )
            return TranspileResult(
                sql=f"/* TRANSPILATION ERROR: {e} */\n{sql}",
                warnings=warnings,
                unsupported=unsupported,
            )

    def _transpile_alter_column(
        self,
        sql: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> TranspileResult | None:
        """Build the target's column-modify form for a T-SQL ``ALTER TABLE t ALTER
        COLUMN c <type> [NULL|NOT NULL]``. Reuses the CREATE-TABLE column mapping
        (name + type, incl. ``VARBINARY(MAX)`` -> ``BLOB``) via a synthetic
        one-column table; returns ``None`` (keep the sqlglot path) if it can't be
        matched/mapped cleanly."""
        m = _TSQL_ALTER_COLUMN_RE.match(sql)
        if not m:
            return None
        nullability = " ".join((m.group("null") or "").upper().split())
        synth = self._transpile_dml(
            f"CREATE TABLE {m.group('table')} ({m.group('col')} {m.group('type')})",
            source,
            target,
            source_dialect,
            target_dialect,
        ).sql
        cm = re.search(
            r"(?is)CREATE\s+TABLE\s+(?P<table>[^\s(]+)\s*\((?P<body>.*)\)", synth
        )
        if not cm:
            return None
        coldef = " ".join(cm.group("body").split()).rstrip(",").strip()
        parts = coldef.split(None, 1)
        if len(parts) != 2:
            return None
        colname, coltype = parts
        warnings = []
        if target == "oracle" and nullability == "NULL":
            warnings.append(
                _warn(
                    "Oracle MODIFY keeps the column's current nullability; the "
                    "redundant NULL is omitted (an explicit NULL raises ORA-01451 "
                    "when the column is already nullable)",
                    "alter_column_null",
                    source,
                    target,
                )
            )
        return TranspileResult(
            sql=(m.group("lead") or "")
            + self._alter_column_stmt(
                target, cm.group("table"), colname, coltype, nullability
            ),
            warnings=warnings,
            unsupported=[],
        )

    @staticmethod
    def _alter_column_stmt(
        target: str, table: str, colname: str, coltype: str, nullability: str
    ) -> str:
        """The target's spelling of a column type/nullability change."""
        null = f" {nullability}" if nullability else ""
        if target == "oracle":
            # MODIFY (c type NULL) raises ORA-01451 when the column is already
            # nullable, and MODIFY (c type) keeps the current nullability — so
            # emit an explicit NOT NULL only, never a redundant NULL.
            nn = " NOT NULL" if nullability == "NOT NULL" else ""
            return f"ALTER TABLE {table} MODIFY ({colname} {coltype}{nn});"
        if target == "mysql":
            return f"ALTER TABLE {table} MODIFY COLUMN {colname} {coltype}{null};"
        if target == "postgresql":
            stmt = f"ALTER TABLE {table} ALTER COLUMN {colname} TYPE {coltype};"
            if nullability == "NOT NULL":
                stmt += f"\nALTER TABLE {table} ALTER COLUMN {colname} SET NOT NULL;"
            elif nullability == "NULL":
                stmt += f"\nALTER TABLE {table} ALTER COLUMN {colname} DROP NOT NULL;"
            return stmt
        return f"ALTER TABLE {table} ALTER COLUMN {colname} {coltype}{null};"

    def _transpile_create_schema(
        self, sql: str, source: str, target: str
    ) -> TranspileResult | None:
        """T-SQL ``CREATE SCHEMA <name> [AUTHORIZATION <owner>]`` (often wrapped in
        ``EXEC('…')`` dynamic SQL, which sqlglot leaves opaque). PostgreSQL/MySQL
        have ``CREATE SCHEMA``; Oracle has no namespace object — a schema is a
        database user — so it degrades to a documented carrier. Returns ``None``
        when unmatched."""
        m = _TSQL_CREATE_SCHEMA_RE.match(sql)
        if not m:
            return None
        name = m.group("name").strip('[]"')
        if target == "oracle":
            body = "\n".join(f"-- {ln}" for ln in sql.strip().splitlines())
            return TranspileResult(
                sql=(
                    "-- UNIQUE: T-SQL CREATE SCHEMA has no Oracle equivalent — an "
                    "Oracle schema is a database user. Create it manually, e.g. "
                    f"CREATE USER {name} …; original:\n{body}"
                ),
                warnings=[
                    _warn(
                        f"CREATE SCHEMA {name} carried (an Oracle schema is a user; "
                        "create it with CREATE USER)",
                        "create_schema",
                        source,
                        target,
                    )
                ],
                unsupported=[f"CREATE SCHEMA {name} has no Oracle equivalent"],
            )
        # PostgreSQL has schemas; MySQL's CREATE SCHEMA is CREATE DATABASE. Emit an
        # idempotent CREATE SCHEMA; the T-SQL owner rarely maps, so drop it + warn.
        warnings = []
        if m.group("owner"):
            warnings.append(
                _warn(
                    "CREATE SCHEMA AUTHORIZATION <owner> dropped (the T-SQL owner "
                    f"has no {target} counterpart)",
                    "create_schema",
                    source,
                    target,
                )
            )
        return TranspileResult(
            sql=f"CREATE SCHEMA IF NOT EXISTS {name};",
            warnings=warnings,
            unsupported=[],
        )

    def _transpile_dml(
        self,
        sql: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> TranspileResult:
        """Transpile a DML/DDL batch through the sqlglot pipeline."""
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        if source == "tsql" and target != "tsql":
            altered = self._transpile_alter_column(
                sql, source, target, source_dialect, target_dialect
            )
            if altered is not None:
                return altered
            schema = self._transpile_create_schema(sql, source, target)
            if schema is not None:
                return schema

        # T-SQL compound assignment (SET a += 1) is not understood by sqlglot,
        # which would drop the column; expand it to "SET a = a + 1" first.
        was_default_constraint = False
        default_original = ""
        if source == "tsql":
            sql = _expand_tsql_compound_assignment(sql)
            rewritten = _rewrite_tsql_default_constraint(sql)
            if rewritten != sql:
                was_default_constraint = True
                default_original = sql
                sql = rewritten
            # TEXTIMAGE_ON <filegroup> (physical placement of a table's LOB
            # columns) is a storage clause sqlglot cannot parse: left in, it
            # degrades the whole CREATE TABLE to a Command passthrough (columns
            # and constraints lost). Like ON <filegroup> / WITH (...) — dropped in
            # the emitter — it carries no logical schema, so strip it pre-parse.
            sql, n_lob = re.subn(
                r"(?is)\s+TEXTIMAGE_ON\s+(?:\[[^\]]+\]|\"[^\"]+\"|\w+)", "", sql
            )
            if n_lob:
                warnings.append(
                    _warn(
                        "T-SQL TEXTIMAGE_ON filegroup clause dropped (physical "
                        "storage, no logical-schema impact)",
                        "physical_clause",
                        source,
                        target,
                    )
                )
            # "ALTER TABLE t WITH [NO]CHECK ADD CONSTRAINT …": the WITH
            # CHECK/NOCHECK modifier precedes ADD and makes sqlglot fall back to a
            # Command (losing the constraint). Strip it so the constraint
            # transpiles. WITH CHECK just re-asserts the default (validate), but
            # NOCHECK (add without validating existing rows) has no portable form,
            # so warn — the target will validate on add.
            sql = re.sub(r"(?is)\bWITH\s+CHECK\s+ADD\b", "ADD", sql)
            sql, n_nocheck = re.subn(r"(?is)\bWITH\s+NOCHECK\s+ADD\b", "ADD", sql)
            if n_nocheck:
                warnings.append(
                    _warn(
                        "T-SQL WITH NOCHECK dropped; the constraint is added and "
                        "the target validates existing rows (no NOVALIDATE applied)",
                        "constraint_check",
                        source,
                        target,
                    )
                )

        # Oracle ORGANIZATION INDEX/HEAP: a physical-storage clause sqlglot
        # cannot parse, which would degrade the whole CREATE TABLE (columns
        # and constraints included) to a commented passthrough. The clause
        # carries no logical schema, so strip it and document the drop.
        org_carrier = ""
        if (
            source == "oracle"
            and target != "oracle"
            and re.match(r"(?is)^\s*CREATE\s+TABLE\b", sql)
        ):
            stripped_sql, n_org = re.subn(
                r"(?is)\)\s*ORGANIZATION\s+(INDEX|HEAP)\s*(;?)\s*$",
                r")\2",
                sql,
            )
            if n_org:
                sql = stripped_sql
                org_carrier = (
                    "\n-- UNIQUE: Oracle ORGANIZATION INDEX/HEAP is a "
                    "physical-storage clause with no equivalent here; dropped."
                )
                warnings.append(
                    _warn(
                        "Oracle ORGANIZATION INDEX/HEAP physical clause "
                        "dropped (no logical-schema impact)",
                        "physical_clause",
                        source,
                        target,
                    )
                )

        # T-SQL constraint check-state toggles (ALTER TABLE t CHECK/NOCHECK
        # CONSTRAINT c): translate to the target's enable/disable, else keep a
        # restorable note. Runs before physical stripping (which would eat the
        # leading WITH CHECK) and bypasses sqlglot, which cannot parse the form.
        if (
            source == "tsql"
            and target != "tsql"
            and re.match(r"(?is)^\s*ALTER\s+TABLE\b", sql)
        ):
            state = _rewrite_tsql_constraint_state(sql, target)
            if state:
                return TranspileResult(
                    sql=state + ";", warnings=warnings, unsupported=unsupported
                )
            if state == "":
                return TranspileResult(
                    sql=f"/* UNIQUE: {sql.strip().rstrip(';')} -- tsql-only, no "
                    f"{target} equivalent (constraint check-state) */",
                    warnings=[
                        _warn(
                            "T-SQL constraint check-state toggle preserved as a "
                            "restorable note",
                            "constraint_state",
                            source,
                            target,
                        )
                    ],
                    unsupported=unsupported,
                )

        # System stored-procedure calls (e.g. EXEC sp_addextendedproperty,
        # sp_rename) are SQL Server metadata operations with no portable
        # equivalent. Emit them as an informational comment instead of
        # letting sqlglot fail on the proprietary syntax.
        if source == "tsql" and target != "tsql":
            stripped = sql.lstrip()
            m = re.match(r"(?i)^EXEC(?:UTE)?\s+(?:\[?\w+\]?\.)*\[?(sp_\w+)", stripped)
            if m and m.group(1).lower() in _TSQL_SYSTEM_PROCS:
                proc = m.group(1)
                unsupported.append(f"System procedure {proc} has no equivalent")
                return TranspileResult(
                    sql=(
                        f"-- UNIQUE: {proc} is a SQL Server system procedure "
                        f"with no {target} equivalent; original call omitted:\n"
                        + "\n".join(f"-- {ln}" for ln in sql.strip().splitlines())
                    ),
                    warnings=[
                        _warn(
                            f"System procedure {proc} skipped (no {target} "
                            "equivalent)",
                            "system_proc",
                            source,
                            target,
                        )
                    ],
                    unsupported=unsupported,
                )

        # T-SQL OUTPUT clause: sqlglot cannot parse it on DELETE/UPDATE (it
        # sits before WHERE) and would drop the rest of the statement,
        # including the WHERE — a dangerous data-loss bug. Extract it safely,
        # transpile the base statement, then re-attach as RETURNING
        # (PostgreSQL/Oracle) or a documented comment (MySQL, which lacks it).
        if source == "tsql":
            base_sql, output_cols = _extract_tsql_output(sql)
            if output_cols is not None:
                base_result = self._transpile_dml(
                    base_sql, source, target, source_dialect, target_dialect
                )
                # Map the OUTPUT columns (strip INSERTED./DELETED. prefixes).
                cols = re.sub(r"(?i)\b(INSERTED|DELETED)\.", "", output_cols).strip()
                body = base_result.sql.rstrip().rstrip(";")
                if target in ("postgresql", "oracle"):
                    new_sql = f"{body} RETURNING {cols}"
                else:  # mysql: no RETURNING/OUTPUT
                    new_sql = (
                        f"{body}\n-- UNIQUE: MySQL has no OUTPUT/RETURNING; "
                        f"the statement returned: {cols}"
                    )
                return TranspileResult(
                    sql=new_sql,
                    warnings=base_result.warnings,
                    unsupported=base_result.unsupported,
                )

        try:
            ir_nodes = source_dialect.parse(sql)

            if source != target:
                transformer = Transformer(source, target)
                ir_nodes = transformer.transform(ir_nodes)
                warnings.extend(transformer.warnings)
                unsupported = transformer.unsupported

            output_sql = target_dialect.emit(ir_nodes) + org_carrier
            if source == "sqlite":
                output_sql = _rewrite_sqlite_functions(output_sql, target)
            if was_default_constraint and target == "oracle":
                # Oracle spells a column default change ``MODIFY col DEFAULT v``.
                output_sql = _ORACLE_ALTER_DEFAULT_RE.sub(
                    r"MODIFY \g<col> DEFAULT", output_sql
                )
            if was_default_constraint and not _parses_in_target(output_sql, target):
                # The default value did not translate to valid target SQL (e.g. a
                # T-SQL-only NEWID()); keep the original as a documented carrier
                # rather than emit invalid SQL.
                return TranspileResult(
                    sql="-- UNIQUE: T-SQL default constraint value has no "
                    f"{target} equivalent:\n"
                    + "\n".join(f"-- {ln}" for ln in default_original.splitlines()),
                    warnings=[
                        _warn(
                            "T-SQL default-constraint value has no target form",
                            "ddl_default",
                            source,
                            target,
                        )
                    ],
                    unsupported=unsupported,
                )

            return TranspileResult(
                sql=output_sql,
                warnings=warnings,
                unsupported=unsupported,
            )
        except Exception as e:
            logger.warning("DML transpilation failed: %s", e)
            warnings.append(
                _warn(f"DML transpilation failed: {e}", "dml", source, target)
            )
            return TranspileResult(
                sql=f"/* TRANSPILATION ERROR: {e} */\n{sql}",
                warnings=warnings,
                unsupported=unsupported,
            )

    def _guard_idempotent(
        self, result: TranspileResult, source: str, target: str
    ) -> TranspileResult:
        """Restore a catalog CREATE-guard's re-runnable intent on the target.

        Oracle wraps the DDL in the ``user_objects`` probe + ``EXECUTE
        IMMEDIATE`` (see ``_oracle_idempotent_create``); PostgreSQL/MySQL use
        their native ``CREATE TABLE/INDEX IF NOT EXISTS`` clause. Where the
        target has no form (MySQL ``CREATE INDEX``), the guard is dropped
        with an explicit warning — never silently (audit 2026-07-08, A5)."""
        if target == "oracle":
            wrapped = _oracle_idempotent_create(result.sql)
            if wrapped is None:
                return result
            return TranspileResult(
                sql=wrapped, warnings=result.warnings, unsupported=result.unsupported
            )
        if target in ("postgresql", "mysql"):
            sql, n = re.subn(
                r"(?i)^(\s*)CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)",
                r"\1CREATE TABLE IF NOT EXISTS ",
                result.sql,
                count=1,
            )
            if n:
                return TranspileResult(
                    sql=sql, warnings=result.warnings, unsupported=result.unsupported
                )
            if target == "postgresql":
                sql, n = re.subn(
                    r"(?i)^(\s*)CREATE\s+(UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)",
                    r"\1CREATE \2INDEX IF NOT EXISTS ",
                    result.sql,
                    count=1,
                )
                if n:
                    return TranspileResult(
                        sql=sql,
                        warnings=result.warnings,
                        unsupported=result.unsupported,
                    )
            elif re.match(r"(?is)^\s*CREATE\s+(UNIQUE\s+)?INDEX\b", result.sql):
                return TranspileResult(
                    sql=result.sql,
                    warnings=[
                        *result.warnings,
                        _warn(
                            "existence guard dropped: MySQL has no CREATE INDEX "
                            "IF NOT EXISTS, so a re-run of this statement errors",
                            "guard_dropped",
                            source,
                            target,
                        ),
                    ],
                    unsupported=result.unsupported,
                )
        return result

    def _transpile_drop_guard(
        self, kind: str, name: str, source: str, target: str
    ) -> TranspileResult:
        """Convert a T-SQL 'IF OBJECT_ID(...) IS NOT NULL DROP x' guard."""
        kind = kind.upper()
        # Bare object name: brackets/quotes and the dbo qualifier are T-SQL-only.
        clean = re.sub(r'[\[\]"]', "", name)
        clean = re.sub(r"(?i)^dbo\.", "", clean)
        if target == "mysql" and kind == "SEQUENCE":
            # MySQL has no sequences; keep the documented degradation the
            # CREATE SEQUENCE counterpart also emits.
            return self._transpile_set_option(
                f"IF OBJECT_ID DROP SEQUENCE {clean}", source, target
            )
        if target == "oracle":
            # No DROP ... IF EXISTS before 23c; a tolerant block is the idiom.
            return TranspileResult(
                sql=(
                    "BEGIN\n"
                    f"    EXECUTE IMMEDIATE 'DROP {kind} {clean}';\n"
                    "EXCEPTION\n"
                    "    WHEN OTHERS THEN NULL;  -- object did not exist\n"
                    "END;"
                )
            )
        if target == "postgresql" and kind == "TRIGGER":
            # PostgreSQL's DROP TRIGGER needs the table name, which the T-SQL
            # guard does not carry; resolve it from the catalog.
            return TranspileResult(
                sql=(
                    "DO $$\n"
                    "DECLARE r RECORD;\n"
                    "BEGIN\n"
                    "    FOR r IN SELECT tgname, tgrelid::regclass AS tbl\n"
                    "             FROM pg_trigger\n"
                    f"             WHERE tgname = '{clean.lower()}'"
                    " AND NOT tgisinternal LOOP\n"
                    "        EXECUTE format('DROP TRIGGER %I ON %s',"
                    " r.tgname, r.tbl);\n"
                    "    END LOOP;\n"
                    "END $$;"
                )
            )
        return TranspileResult(sql=f"DROP {kind} IF EXISTS {clean}")

    def _transpile_set_option(
        self, sql: str, source: str, target: str
    ) -> TranspileResult:
        """Handle SET options like SET NOCOUNT ON.

        This is also the comment-out fallback for batches the guard
        recognizers could not extract; those must be labelled honestly (an
        unrecognized batch, not a "SET option") and registered as unsupported
        — an executable statement reduced to a comment with a misleading
        warning is a no-silent-loss violation (audit 2026-07-08, RC1/RC4).
        """
        if source == "tsql" and target != "tsql":
            commented = "\n".join(
                f"-- {line}" if line.strip() else ""
                for line in sql.strip().splitlines()
            )
            _, code = split_leading_trivia(sql)
            head = " ".join(code.strip().split())[:60]
            if re.match(r"(?i)^\s*SET\b", code):
                return TranspileResult(
                    sql=commented,
                    warnings=[
                        _warn(
                            f"SET option commented out: {head}",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                )
            message = (
                f"batch commented out (unrecognized migration-guard shape): {head}"
            )
            return TranspileResult(
                sql=commented,
                warnings=[_warn(message, "unhandled_batch", source, target)],
                unsupported=[message],
            )
        return TranspileResult(sql=sql)

    @staticmethod
    def _ensure_terminated(sql: str, target: str, batch_type: BatchType) -> str:
        """Ensure an emitted statement is properly delimited for re-parsing.

        For PostgreSQL/MySQL/Oracle the statement terminator is ``;`` and we
        append one when missing so the output stays re-parseable (round-trips,
        downstream tools).

        For T-SQL the batch separator ``GO`` does that job, and idiomatic
        T-SQL does not terminate statements with ``;`` (it is only required in
        specific cases such as before a CTE's ``WITH``). Appending ``;`` here
        would produce ``... ;`` followed by ``GO`` -- noisy and non-idiomatic,
        and harmful after an ``IF`` guard, whose scope is a single statement.
        So for T-SQL we leave the statement unterminated.
        """
        if target == "tsql":
            return sql
        if batch_type == BatchType.COMMENT:
            # A comment batch (incl. a whole /* … */ block) carries no statement to
            # terminate; appending ``;`` would corrupt it (``*/;``).
            return sql
        stripped = sql.rstrip()
        if not stripped:
            return sql
        lines = stripped.splitlines()
        # Pure comment output: do not append a semicolon.
        if all(not line.strip() or line.lstrip().startswith("--") for line in lines):
            return sql
        # Trailing explanatory comments may follow the statement (e.g. a
        # documented unsupported generated column). Find the last line that
        # isn't a comment and terminate there, leaving the comments after it.
        last_code_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() and not lines[i].lstrip().startswith("--"):
                last_code_idx = i
                break
        if last_code_idx is None:
            return sql
        if lines[last_code_idx].rstrip().endswith(";"):
            return sql
        lines[last_code_idx] = lines[last_code_idx].rstrip() + ";"
        return "\n".join(lines)

    @staticmethod
    def _wrap_mysql_routine(sql: str) -> str:
        """Wrap a MySQL compound routine in a DELIMITER block.

        MySQL stored routines contain ``;`` statement terminators inside their
        body. A client that uses ``;`` as the statement delimiter would cut the
        definition at the first inner ``;``, so the routine must be wrapped::

            DELIMITER $$
            CREATE PROCEDURE ... BEGIN ... END$$
            DELIMITER ;

        Any leading line comments are kept above the ``DELIMITER $$`` line so
        they remain associated with the routine. Non-routine statements are
        returned unchanged.
        """
        if not _MYSQL_ROUTINE_RE.match(sql):
            return sql

        lines = sql.splitlines()
        # Separate any leading comment lines from the routine body.
        head: list[str] = []
        idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("--") or not line.strip():
                head.append(line)
                idx = i + 1
            else:
                break
        body = "\n".join(lines[idx:]).rstrip()
        # The body was terminated with ';' by _ensure_terminated; swap that
        # trailing ';' for the '$$' routine delimiter.
        if body.endswith(";"):
            body = body[:-1].rstrip()
        # A batch may hold several routines (e.g. a multi-event trigger split
        # into one trigger per event); each needs its own '$$' terminator.
        body = re.sub(
            r"(?m)^END\n\n(?=CREATE\s+(?:TRIGGER|PROCEDURE|FUNCTION)\b)",
            "END$$\n\n",
            body,
        )
        wrapped = f"DELIMITER $$\n{body}$$\nDELIMITER ;"
        if head:
            # Drop a trailing blank line in the comment head for tidiness.
            while head and not head[-1].strip():
                head.pop()
            return "\n".join(head + [wrapped]) if head else wrapped
        return wrapped

    @staticmethod
    def _get_batch_separator(target: str) -> str:
        """Get the batch separator for a target dialect."""
        separators = {
            "tsql": "\nGO\n\n",
            "oracle": "\n/\n\n",
            "postgresql": "\n\n",
            "mysql": "\n\n",
        }
        return separators.get(target, "\n\n")

    def available_dialects(self) -> list[str]:
        """List all available dialect names (valid as a transpilation source)."""
        return self.registry.available()

    def source_only_dialects(self) -> list[str]:
        """Dialects that may only be a source (import-only), never a target."""
        return [
            name
            for name in self.registry.available()
            if self.registry.get(name).source_only
        ]


def transpile(
    sql: str,
    source: str,
    target: str,
    db_url: str | None = None,
) -> TranspileResult:
    """Convenience function for one-shot transpilation.

    Args:
        sql: The source SQL text.
        source: The source dialect name.
        target: The target dialect name.
        db_url: Optional database connection URL for metadata resolution.

    Returns:
        A TranspileResult.
    """
    options = TranspileOptions(db_url=db_url)
    return Transpiler().transpile(sql, source, target, options)
