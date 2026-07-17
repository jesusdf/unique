# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Text-level batch rules and shared helpers for the transpiler.

The module-level recognizers and pre/post-processing helpers the orchestrator
applies around the AST pipelines (the audited M2/P3 single guard recognizer,
Oracle idempotent-guard emission, carrier/warning reconciliation, SQLite
source rewrites, batch termination details). Split out of the former
``transpiler.py`` module (module-growth backlog); the orchestrator lives in
``_core.py``.
"""

from __future__ import annotations

import logging
import re

from unique.core.ast_nodes import CommentStatement
from unique.core.converter import USER_FUNCTIONS
from unique.core.sql_split import qualify_function_calls, split_leading_trivia
from unique.core.transformer import TransformWarning

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


def _normalize_oracle_multicolumn_drop(sql: str, target: str) -> str:
    """Rewrite ``ALTER TABLE t DROP (a, b)`` to the target's DROP COLUMN form."""
    m = re.match(r"(?is)^\s*(ALTER\s+TABLE\s+\S+\s+)DROP\s*\(([^)]+)\)\s*;?\s*$", sql)
    if not m:
        return sql
    cols = [c.strip() for c in m.group(2).split(",") if c.strip()]
    if not cols:
        return sql
    dropped = ", ".join(f"DROP COLUMN {c}" for c in cols)
    return f"{m.group(1)}{dropped}"


_SCALAR_ARG = r"((?:[^(),]|\([^()]*\))+?)"


def _map_oracle_scalars_for_tsql(sql: str) -> str:
    """Oracle scalar builtins with a direct T-SQL spelling that sqlglot
    passes through untranslated in plain DML (found live in the 13 MB
    corpus): CHR, TO_NUMBER, MONTHS_BETWEEN."""
    sql = re.sub(r"(?i)\bCHR\s*\(", "CHAR(", sql)
    sql = re.sub(
        rf"(?is)\bTO_NUMBER\s*\(\s*{_SCALAR_ARG}\s*\)",
        r"CAST(\1 AS DECIMAL(38, 10))",
        sql,
    )
    sql = re.sub(
        rf"(?is)\bMONTHS_BETWEEN\s*\(\s*{_SCALAR_ARG}\s*,\s*{_SCALAR_ARG}\s*\)",
        r"DATEDIFF(MONTH, \2, \1)",
        sql,
    )
    return sql


def _qualify_tsql_udfs_in_sql(sql: str) -> str:
    """Qualify bare scalar-UDF calls as ``dbo.fn(`` using the harvested
    USER_FUNCTIONS registry (mirror of the procedural transformer's
    ``_qualify_tsql_udfs``; T-SQL error 195 otherwise). Registry names only:
    this runs over the whole final script, where the broad structural
    decision would have to reason about every DDL context — the expression
    paths (IR emitter, procedural raw expressions) carry that decision.
    String/comment-aware via the shared walker."""
    funcs = USER_FUNCTIONS.get()
    if not funcs:
        return sql

    def decide(name: str, prev_word: str | None) -> str | None:
        del prev_word
        return "dbo." if name.lower() in funcs else None

    return qualify_function_calls(sql, decide)


def _extract_catalog_guard(code: str) -> tuple[str, str, str, str] | None:
    """Parse a T-SQL catalog migration guard into ``(polarity, trivia, body,
    condition)``.

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
    condition = code[head.end() - 1 : i + 1]
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
    return polarity, inner_trivia, rest, condition


# A MySQL routine whose body contains ';' statement terminators must be wrapped
# in a DELIMITER block so a client doesn't cut the script at the first inner
# ';'. Matches the leading keyword of a compound routine definition (any
# leading line comments are allowed before it).
_MYSQL_ROUTINE_RE = re.compile(
    r"(?s)^(?:\s*--[^\n]*\n)*\s*" r"CREATE\s+(?:PROCEDURE|FUNCTION|TRIGGER)\b",
    re.IGNORECASE,
)


# MySQL's '--' comment style requires the dashes to be followed by whitespace:
# a divider line of pure dashes ('-----') is NOT a comment there and glues to
# the next statement (~1.4k failures on the real dump's MySQL direction).
_MYSQL_BAD_COMMENT_RE = re.compile(r"(?m)^(\s*)--(?=\S)")


def _mysql_safe_comments(sql: str) -> str:
    """Insert the space MySQL requires after a line-comment's ``--``."""
    return _MYSQL_BAD_COMMENT_RE.sub(r"\1-- ", sql)


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
