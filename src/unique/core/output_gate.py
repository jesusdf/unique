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

from unique.core.sql_split import is_executable, split_statements

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

#: Per-target deny-list: (compiled pattern, human label). A hit outside
#: comments/strings is a source-dialect leftover that cannot run on the
#: target. Keep this list conservative — every entry must be impossible in
#: valid output for that target.
_LEFTOVERS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "postgresql": [
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
            out.append("''")
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


def gate_reason(sql: str, target: str) -> str | None:
    """Why *sql* must not ship as ``target`` output, or None if it may.

    Runs the leftover scan on everything, and the sqlglot target-dialect parse
    only on output with no procedural markers (sqlglot cannot judge those).
    """
    leftovers = find_leftover_tokens(sql, target)
    if leftovers:
        return f"source-dialect leftovers: {', '.join(leftovers)}"
    scrubbed = scrub(sql)
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
