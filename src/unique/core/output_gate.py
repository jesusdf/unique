# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Output validity gate — never ship output known to be invalid (doc 04, M1).

The transpiler's honesty invariant: when the emitted SQL for a batch can be
*detected* as invalid on the target, the batch degrades to the documented
carrier comment (original source preserved) plus a ``validity_gate`` warning
and an ``unsupported`` entry — the same contract as every other lossy
conversion. Callers then see the gap programmatically instead of shipping a
syntax error to a production migration.

Two detectors, both deliberately conservative (a false "invalid" would degrade
working output, which is worse than missing a broken one):

- **Target-dialect parse** (plain DML/DDL only): each statement must parse
  under sqlglot in the target dialect. Procedural units are exempt — sqlglot
  cannot parse PL/SQL / T-SQL blocks / ``DO $$`` bodies.
- **Leftover scan** (all output): source-dialect tokens that can never be
  valid on the target (``ROWNUM`` off Oracle, ``GETDATE()`` off T-SQL,
  backticks off MySQL, …), checked outside comments and string literals.

The gate detects; it does not fix. Every degradation is a measured, honest
entry in the validity sweep — the fix belongs in the AST paths (guardrails in
``skills/SKILL-development-workflow.md``).
"""

from __future__ import annotations

import re
from functools import cache

from unique.core.builtins import is_builtin
from unique.core.sql_split import is_executable, split_statements


@cache
def _synthetic_sqlglot_functions() -> frozenset[str]:
    """sqlglot canonical function names that are a built-in in NO supported
    engine. sqlglot renders these internal names for functions it cannot map to
    the target dialect (DATETIMEFROMPARTS→TIMESTAMP_FROM_PARTS, FORMAT→
    NUMBER_TO_STR, STR_TO_TIME, GETBIT, BITWISE_COUNT, …); any that reaches the
    output runs on no engine, so it is an unmapped leak — degrade it honestly
    rather than ship silent-invalid. A user object never collides with sqlglot's
    canonical set, so this cannot mistake a UDF for a leak."""
    from sqlglot import expressions as _exp

    names: set[str] = set()
    for cls in vars(_exp).values():
        if (
            isinstance(cls, type)
            and issubclass(cls, _exp.Func)
            and cls is not _exp.Func
        ):
            for n in cls.sql_names():
                names.add(n.upper())
    engines = ("tsql", "oracle", "postgresql", "mysql")
    return frozenset(
        n
        for n in names
        if n not in _KEYWORD_FUNC_NAMES and not any(is_builtin(n, e) for e in engines)
    )


#: sqlglot models these operators / constructs / clauses as ``exp.Func``
#: subclasses, but they appear in valid output as keywords (``a AND (b OR c)``,
#: ``CROSS APPLY (…)``, ``ARRAY(SELECT …)``, ``… FILTER (WHERE …)``) — never as a
#: callable function — so they must not be mistaken for an unmapped leak.
_KEYWORD_FUNC_NAMES = frozenset(
    {
        "AND",
        "OR",
        "XOR",
        "NOT",
        "APPLY",
        "ARRAY",
        "CASE",
        "FILTER",
        "MAP",
        "STRUCT",
        "IN",
        "IS",
        "LIKE",
        "ILIKE",
        "RLIKE",
        "GLOB",
        "SIMILAR",
        "BETWEEN",
        "EXISTS",
        "ALL",
        "ANY",
        "SOME",
        "INTERVAL",
        "COLLATE",
        "DISTINCT",
        "OVER",
        "OVERLAPS",
        "PRIOR",
        "CONNECTBYROOT",
        "PLACEHOLDER",
        "STAR",
        "COLUMN",
        "TABLE",
        "TUPLE",
        "SLICE",
        "BRACKET",
        "PAREN",
        "KWARG",
        "JSONPATH",
    }
)


# A procedural unit marker: any of these anywhere in the executable text means
# sqlglot cannot be trusted to parse the output, so only the leftover scan
# applies. Matched on comment/string-scrubbed text.
_PROCEDURAL_MARKER_RE = re.compile(
    r"(?imx)"
    r"^\s*DO\s+\$\$"
    r"|\bDELIMITER\b"
    r"|^\s*(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
    r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b|DECLARE\b|BEGIN\b|IF\b)"
)

#: Engine-specific types with no cross-engine equivalent — a whole-statement
#: carrier is the honest outcome (the skill's documented degrade), never a
#: silent invalid type. Grouped by native engine and added to the targets that
#: lack them.
_PG_ONLY_TYPE = (
    re.compile(
        r"(?i)\b(?:INET|CIDR|MACADDR8?|(?:INT4|INT8|NUM|TS|TSTZ|DATE)RANGE"
        r"|TSVECTOR|TSQUERY)\b"
    ),
    "PostgreSQL-only type",
)
_TSQL_ONLY_TYPE = (
    re.compile(r"(?i)\b(?:ROWVERSION|SQL_VARIANT|HIERARCHYID)\b"),
    "T-SQL-only type",
)
_ORACLE_ONLY_TYPE = (re.compile(r"(?i)\bXMLTYPE\b"), "XMLTYPE (Oracle)")

#: Per-target deny-list: (compiled pattern, human label). A hit outside
#: comments/strings is a source-dialect leftover that cannot run on the
#: target. Keep this list conservative — every entry must be impossible in
#: valid output for that target.
_LEFTOVERS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "postgresql": [
        _TSQL_ONLY_TYPE,
        _ORACLE_ONLY_TYPE,
        (re.compile(r"(?i)\bROWNUM\b"), "ROWNUM"),
        (re.compile(r"(?i)\bN?VARCHAR2\b"), "VARCHAR2"),
        (re.compile(r"(?i)\bEXECUTE\s+IMMEDIATE\b"), "EXECUTE IMMEDIATE"),
        (re.compile(r"(?i)\bSYS_REFCURSOR\b"), "SYS_REFCURSOR"),
        (re.compile(r"(?i)\bFROM\s+DUAL\b"), "FROM DUAL"),
        (re.compile(r"(?i)\bGETDATE\s*\("), "GETDATE()"),
        (re.compile(r"`\w+`"), "backtick identifier"),
        (re.compile(r"(?m)^\s*GO\s*$"), "GO separator"),
        (re.compile(r"(?m)^\s*/\s*$"), "slash terminator"),
    ],
    "mysql": [
        _PG_ONLY_TYPE,
        _TSQL_ONLY_TYPE,
        _ORACLE_ONLY_TYPE,
        (re.compile(r"(?i)\bROWNUM\b"), "ROWNUM"),
        (re.compile(r"(?i)\bN?VARCHAR2\b"), "VARCHAR2"),
        (re.compile(r"(?i)\bEXECUTE\s+IMMEDIATE\b"), "EXECUTE IMMEDIATE"),
        (re.compile(r"(?i)\bSYS_REFCURSOR\b"), "SYS_REFCURSOR"),
        (re.compile(r"(?i)\bGETDATE\s*\("), "GETDATE()"),
        (re.compile(r"\[\w+\]"), "[bracket] identifier"),
        (re.compile(r"(?m)^\s*GO\s*$"), "GO separator"),
        (re.compile(r"(?m)^\s*/\s*$"), "slash terminator"),
    ],
    "tsql": [
        _PG_ONLY_TYPE,
        _ORACLE_ONLY_TYPE,
        (re.compile(r"(?i)\bROWNUM\b"), "ROWNUM"),
        # No REGEXP_* functions before SQL Server 2025; the project targets
        # 2012+ (live validation runs 2022).
        (
            re.compile(r"(?i)\bREGEXP_(?:LIKE|REPLACE|SUBSTR|INSTR|COUNT)\s*\("),
            "REGEXP_* function",
        ),
        (re.compile(r"(?i)\bN?VARCHAR2\b"), "VARCHAR2"),
        (re.compile(r"(?i)\bEXECUTE\s+IMMEDIATE\b"), "EXECUTE IMMEDIATE"),
        (re.compile(r"(?i)\bSYSDATE\b"), "SYSDATE"),
        (re.compile(r"(?i)\bNVL\s*\("), "NVL()"),
        (re.compile(r"(?i)\bFROM\s+DUAL\b"), "FROM DUAL"),
        (re.compile(r"`\w+`"), "backtick identifier"),
        (re.compile(r"(?m)^\s*/\s*$"), "slash terminator"),
        # NEW./OLD. row references inside a trigger are an incomplete
        # row→statement conversion (T-SQL only has inserted/deleted).
        # Trigger-scoped so a table alias named NEW elsewhere never trips.
        (
            re.compile(r"(?is)\bCREATE\s+TRIGGER\b.*\b(?:NEW|OLD)\s*\.\s*\w"),
            "NEW./OLD. row reference",
        ),
    ],
    "oracle": [
        _PG_ONLY_TYPE,
        _TSQL_ONLY_TYPE,
        (re.compile(r"(?i)\bGETDATE\s*\("), "GETDATE()"),
        (re.compile(r"(?i)\bISNULL\s*\("), "ISNULL()"),
        (re.compile(r"\[\w+\]"), "[bracket] identifier"),
        (re.compile(r"`\w+`"), "backtick identifier"),
        (re.compile(r"(?m)^\s*GO\s*$"), "GO separator"),
    ],
}

_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}


def scrub(sql: str) -> str:
    """Blank out comments and string-literal contents, preserving layout.

    One left-to-right scan so a ``--`` inside a string does not start a
    comment and an apostrophe inside a comment does not open a string.
    Newlines are kept so line-anchored patterns still work.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        two = sql[i : i + 2]
        if two == "--":
            nl = sql.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if two == "/*":
            close = sql.find("*/", i + 2)
            end = n if close == -1 else close + 2
            out.append("\n" * sql.count("\n", i, end))
            i = end
            continue
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            # Preserve the empty-vs-non-empty distinction: a genuinely empty ''
            # stays '' (the empty-string divergence rules key on it), but a
            # non-empty literal becomes 'x' so those rules don't false-fire on
            # an ordinary string (e.g. COMMENT='my table', 'abc' IS NULL).
            out.append("''" if j == i + 1 else "'x'")
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def find_leftover_tokens(sql: str, target: str) -> list[str]:
    """Labels of source-dialect leftovers present in *sql*'s executable text."""
    text = scrub(sql)
    found: list[str] = []
    for pattern, label in _LEFTOVERS.get(target, []):
        if pattern.search(text):
            found.append(label)
    return found


_TSQL_OUTPUT_CLAUSE_RE = re.compile(
    r"(?i)\bOUTPUT\s+(?:INSERTED|DELETED)\.(?:\*|\w+)"
    r"(?:\s*,\s*(?:INSERTED|DELETED)\.(?:\*|\w+))*"
)


#: Type names that appear as ``TYPE(n)`` constructors (in a CAST or a column
#: definition) and so read like a function call in text but are not. Excluded
#: from the built-in leak scan so a cast/column type never false-trips it.
_TYPE_CONSTRUCTOR_NAMES = frozenset(
    {
        "CHAR",
        "NCHAR",
        "VARCHAR",
        "NVARCHAR",
        "VARCHAR2",
        "NVARCHAR2",
        "CHARACTER",
        "NUMBER",
        "NUMERIC",
        "DECIMAL",
        "DEC",
        "FLOAT",
        "DOUBLE",
        "REAL",
        "BINARY",
        "VARBINARY",
        "BLOB",
        "CLOB",
        "NCLOB",
        "RAW",
        "DATETIME",
        "DATETIME2",
        "SMALLDATETIME",
        "TIMESTAMP",
        "TIME",
        "DATETIMEOFFSET",
    }
)

#: SQL keywords that are followed by ``(`` but are not function calls. ``VALUES``
#: is the trap — it heads the ``INSERT … VALUES (…)`` clause yet is also a
#: catalogued MySQL function; the rest are cheap insurance.
_KEYWORD_HEADS = frozenset(
    {
        "VALUES",
        "IN",
        "EXISTS",
        "ALL",
        "ANY",
        "SOME",
        "OVER",
        "FILTER",
        "WITHIN",
        "ROW",
        "ROWS",
        "USING",
        "RETURNING",
    }
)

#: A function-call head: an identifier (its last segment, so ``dbo.SOUNDEX``
#: matches ``SOUNDEX``) immediately followed by ``(``.
_FUNC_CALL_RE = re.compile(r"(?<!\w)([A-Za-z_][A-Za-z0-9_$]*)\s*\(")

#: The ``(`` after a table-position name heads a column list, not call args —
#: ``INSERT INTO line (…)`` / ``CREATE TABLE point (…)`` — and such a table name
#: may collide with a built-in (PostgreSQL ``line``/``point``). Matched against
#: the text immediately before the name (a schema qualifier is allowed). A
#: function relation ``FROM generate_series(…)`` is never in this position.
_TABLE_POSITION_RE = re.compile(r"(?i)\b(?:INTO|TABLE|UPDATE)\s+[\w.]*$")


def _untranslated_source_builtin(scrubbed: str, source: str, target: str) -> str | None:
    """First source built-in that leaked into the output untranslated.

    A call whose emitted name is a built-in of *source* but not of *target*
    can never run there — it is an unmapped built-in the emit paths passed
    through verbatim (sqlglot parses it happily, being lenient across dialects,
    so the target-parse check alone misses it). A name that is *not* a source
    built-in is a user object (UDF / stored proc) and is left alone. The scan
    reads the emitted **text** (not sqlglot's canonicalised AST name, which
    turns a valid ``STRING_AGG`` back into ``GROUP_CONCAT``), on
    comment/string-scrubbed output, skipping ``TYPE(n)`` constructors.
    """
    for m in _FUNC_CALL_RE.finditer(scrubbed):
        name = m.group(1).upper()
        if name in _TYPE_CONSTRUCTOR_NAMES or name in _KEYWORD_HEADS:
            continue
        # A bounded look-back is enough for ``INTO <schema.>?name (``.
        if _TABLE_POSITION_RE.search(scrubbed[max(0, m.start() - 64) : m.start()]):
            continue
        if is_builtin(name, source) and not is_builtin(name, target):
            return name
        # sqlglot rendered a function it could not map to an internal canonical
        # that no engine has (never a source built-in, so the check above misses
        # it): an unmapped leak that runs nowhere.
        if name in _synthetic_sqlglot_functions() and not is_builtin(name, target):
            return name
    return None


def gate_reason(sql: str, target: str, source: str | None = None) -> str | None:
    """Why *sql* must not ship as ``target`` output, or None if it may.

    Runs the leftover scan on everything, and the sqlglot target-dialect parse
    only on output with no procedural markers (sqlglot cannot judge those).
    When *source* is given, the parsed output is also scanned for a source
    built-in that leaked through untranslated (invalid on the target, no
    warning) — the class the sqlglot leniency lets slip past the parse check.
    """
    leftovers = find_leftover_tokens(sql, target)
    if leftovers:
        return f"source-dialect leftovers: {', '.join(leftovers)}"
    scrubbed = scrub(sql)
    if source is not None and source != target:
        # Runs on all output, procedural bodies included: an unmapped built-in
        # is equally invalid inside a routine, and sqlglot cannot parse those to
        # catch it. The name-based filter (source built-in and not target
        # built-in, minus type/keyword heads) keeps procedural constructs — user
        # proc calls, cursors, declarations — from tripping it.
        leaked = _untranslated_source_builtin(scrubbed, source, target)
        if leaked is not None:
            if is_builtin(leaked, source):
                return f"untranslated {source} built-in {leaked}() (no {target} form)"
            return f"unmapped function {leaked}() (no {target} form)"
    if _PROCEDURAL_MARKER_RE.search(scrubbed):
        return None
    import sqlglot

    dialect = _SQLGLOT_DIALECT.get(target)
    if dialect is None:
        return None
    for stmt in split_statements(sql, target):
        if not is_executable(stmt):
            continue
        if target == "tsql":
            # sqlglot's tsql reader cannot parse a (valid) OUTPUT clause
            # followed by WHERE; drop it for the parse check only.
            stmt = _TSQL_OUTPUT_CLAUSE_RE.sub(" ", stmt)
            # Nor (valid) SAVE TRANSACTION name (wave 123).
            if re.fullmatch(r"(?is)\s*SAVE\s+TRAN(?:SACTION)?\s+\w+\s*;?\s*", stmt):
                continue
        if (
            target == "postgresql"
            # PG 14's recursive-CTE SEARCH/CYCLE ordering clause is valid
            # PG that sqlglot cannot parse (wave 191).
            and re.search(
                r"(?is)\)\s*(SEARCH\s+(?:DEPTH|BREADTH)\s+FIRST\s+BY|CYCLE\s+)",
                stmt,
            )
            and re.search(r"(?is)\bWITH\s+RECURSIVE\b", stmt)
        ):
            continue
        if target == "mysql" and re.match(
            # MySQL 8 functional indexes (double-paren key parts) are
            # valid MySQL that sqlglot cannot parse (wave 204).
            r"(?is)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+\S+\s+ON\s+\S+?\s*\(\s*\(",
            stmt,
        ):
            continue
        try:
            sqlglot.parse(stmt, read=dialect, error_level=sqlglot.ErrorLevel.RAISE)
        except Exception as e:
            first = str(e).split("\n", 1)[0][:120]
            return f"does not parse as {target} ({first})"
    return None


#: Known value divergences with NO statement-level compensation (a per-column
#: collation / encoding property is absent from the statement text), approved as
#: documented limits in docs/03-unsupported.md. The output stays VALID; it must
#: not ship silently, so it is flagged with a warning + a leading UNIQUE comment.
#: Each rule: (source engine, source-SQL pattern, reason template). ``{target}``
#: is filled per target.
#: ``(source_engine, target_engine, pattern, reason)`` — ``"*"`` = any engine.
_DIVERGENCE_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "mysql",
        "*",
        # LENGTH (not CHAR_/OCTET_/BIT_LENGTH) counts BYTES on MySQL.
        re.compile(r"(?<![_\w])LENGTH\s*\(", re.I),
        "MySQL LENGTH() counts bytes; {target} counts characters — the result "
        "differs for multi-byte/encoded text",
    ),
    (
        # ``*`` = any source. Two string literals compared: ``'Ä' = 'A'``,
        # ``'apple' < 'Banana'``, ``'ABC' LIKE 'abc'``, ``'a ' = 'a'``. Runs on
        # scrubbed text so the blanked-content quotes still show ``'…' <op> '``.
        # A literal-vs-column (``'x' = col``) does NOT match — kept narrow.
        "*",
        "*",
        re.compile(r"'[^']*'\s*(?:<=|>=|<>|!=|=|<|>|(?:NOT\s+)?I?R?LIKE)\s*'", re.I),
        "string comparison result depends on each engine's default collation "
        "(case/accent sensitivity) and trailing-space handling, which differ "
        "between {source} and {target} — the boolean result may differ",
    ),
    (
        # IFNULL/NVL/COALESCE of an empty string: Oracle stores '' AS NULL, so
        # the empty string cannot survive as a distinct return value there. Only
        # Oracle diverges (T-SQL/PG return '' faithfully).
        "mysql",
        "oracle",
        re.compile(r"(?i)IFNULL\s*\(\s*''"),
        "MySQL IFNULL of an empty string returns '', but Oracle stores '' as "
        "NULL, so the result is NULL on {target} — Oracle cannot represent an "
        "empty string distinct from NULL, so there is no faithful workaround",
    ),
    (
        # An empty string literal in a numeric/boolean context: ``'' = 0``,
        # ``x = ''``, ``0 OR ''``. MySQL implicitly reads '' as 0/false; Oracle
        # stores '' as NULL, so the comparison/OR is NULL there.
        "mysql",
        "oracle",
        re.compile(
            r"(?i)''\s*(?:=|<>|!=|<|>|<=|>=)|"
            r"(?:=|<>|!=|<|>|<=|>=|\bOR\b|\bAND\b)\s*''"
        ),
        "MySQL reads an empty string as 0/false in a numeric/boolean context, "
        "but Oracle stores '' as NULL, so the result is NULL on {target} — no "
        "faithful workaround (Oracle's '' = NULL)",
    ),
    (
        # The reverse: an Oracle source whose empty-string literal is read as
        # NULL. ``'' IS NULL`` is true, ``NVL('', x)`` is x, ``INSTR(s, '')`` is
        # NULL on Oracle — but on every other engine '' is a real empty string,
        # so those results differ. Narrowed to those three contexts (a bare ''
        # elsewhere often does not diverge). Scrub keeps a genuine '' empty (a
        # blanked non-empty literal shows '…'). Oracle can't represent '' apart
        # from NULL, so there is no faithful workaround.
        "oracle",
        "*",
        re.compile(
            r"(?i)''\s+IS\s+(?:NOT\s+)?NULL"
            r"|(?:NVL|COALESCE|IFNULL)\s*\(\s*''"
            r"|INSTR\s*\([^)]*,\s*''\s*\)"
        ),
        "Oracle stores an empty string as NULL, so the '' literal is NULL on "
        "Oracle but a real empty string on {target} — IS NULL / NVL / INSTR "
        "results diverge, and there is no faithful workaround (Oracle '' = NULL)",
    ),
    (
        # The mirror: a NON-Oracle source whose '' is a real empty string (so
        # ``'' IS NULL`` is false) sent to Oracle, where '' is stored as NULL
        # (so it is true). Oracle can't represent '' apart from NULL, so the
        # boolean result has no faithful workaround. (oracle->oracle is excluded
        # by the source==target guard; a MySQL source also matches here.)
        "*",
        "oracle",
        re.compile(r"(?i)''\s+IS\s+(?:NOT\s+)?NULL"),
        "an empty string is a real value on {source} (so '' IS NULL is false), "
        "but Oracle stores '' as NULL (so it is true) — the boolean result "
        "diverges on {target}, with no faithful workaround (Oracle '' = NULL)",
    ),
    (
        # MySQL evaluates bitwise operators on an UNSIGNED 64-bit integer, so
        # ``~0`` is 18446744073709551615 and ``~5`` is 18446744073709551610;
        # every other engine uses a signed integer (~0 = -1, ~5 = -6). The
        # high-bit results differ and there is no faithful unsigned-64 type to
        # map onto. Keyed on the ``~`` (bitwise NOT) operator, which is where the
        # sign bit always shows.
        "mysql",
        "*",
        re.compile(r"~\s*[\d(]"),
        "MySQL bitwise operators return an unsigned 64-bit integer (bitwise NOT "
        "of 0 is 18446744073709551615), but {target} uses a signed integer (it "
        "is -1) — results using the high bit differ, with no faithful "
        "unsigned-64 mapping",
    ),
]


#: Case-folding of non-ASCII text is locale/collation-dependent (MySQL leaves
#: ``ß`` as-is, others may fold ``ß``→``SS`` or vary by accent) — needs the
#: ORIGINAL text (scrub blanks the literal), so it is checked separately.
_CASEFOLD_NONASCII_RE = re.compile(r"(?i)(?:UPPER|LOWER)\s*\(\s*'[^']*[^\x00-\x7f]")


def annotate_divergence(source_sql: str, source: str, target: str) -> str | None:
    """A human-approved value divergence with no statement-level fix — return the
    reason to flag (a warning + a ``UNIQUE:`` output comment), or None. The SQL
    itself stays valid; this only makes the known difference non-silent."""
    if source == target:
        return None
    scrubbed = scrub(source_sql)
    for src_eng, tgt_eng, pat, reason in _DIVERGENCE_RULES:
        if (
            (src_eng == "*" or source == src_eng)
            and (tgt_eng == "*" or target == tgt_eng)
            and pat.search(scrubbed)
        ):
            return (
                reason.format(source=source, target=target)
                + " (docs/03-unsupported.md)"
            )
    if source == "mysql" and _CASEFOLD_NONASCII_RE.search(source_sql):
        return (
            "MySQL case-folding of non-ASCII text (e.g. ß→ß, accents) is "
            f"locale/collation-dependent and differs from {target}'s (ß→SS, …) "
            "— the result may differ (docs/03-unsupported.md)"
        )
    return None


def degrade_to_carrier(original_sql: str, reason: str, source: str, target: str) -> str:
    """Build the carrier comment that replaces invalid output.

    The *source* batch (not the broken output) is preserved — it is the
    recoverable artifact a human needs to port the statement by hand.
    """
    header = (
        f"-- UNIQUE: output failed the {target} validity check ({reason}); "
        f"original {source} batch preserved:"
    )
    body = "\n".join(f"-- {line}" for line in original_sql.strip().splitlines())
    return f"{header}\n{body}"
