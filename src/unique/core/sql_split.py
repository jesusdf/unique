# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared per-dialect SQL statement splitter.

One implementation, four consumers: the output validity gate
(``unique.core.output_gate``, audit doc 04 M1), the functional-equivalence
engine runner, the live validators and the validity sweep
(``scripts/validity_sweep.py``). It exists because two independent splitters
drifted apart and the weaker one mis-split statements whose *string literals*
contained ``;`` or ``--`` (audit 2026-07-08 doc 03, E1) — the exact class of
bug the architecture guardrails ban ("one shared place").

Dialect shapes handled:

- **tsql** — batches separated by a line containing only ``GO``.
- **oracle** — PL/SQL units terminated by a line containing only ``/``; plain
  statements by top-level ``;``. A ``/``-chunk may hold leading ``;``-DDL plus
  one PL/SQL block (re-runnable scripts); the block head is located outside
  strings/comments and kept whole.
- **postgresql** — top-level ``;`` with ``$$``-quoted bodies kept intact.
- **mysql** — client-side ``DELIMITER`` directives honored (a routine body is
  one statement); plain regions split on top-level ``;`` with MySQL's
  backslash string escapes recognized.

Splitting is string-, comment- and BEGIN/END-depth aware. It is a script
splitter for the transpiler's own output and real dumps — not a full SQL
parser.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_ORACLE_PLSQL_HEAD_RE = re.compile(
    r"(?is)^\s*(?:DECLARE\b|BEGIN\b|CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE|TYPE)\b)"
)


def split_statements(sql: str, dialect: str) -> list[str]:
    """Split a script into individually executable statements for ``dialect``."""
    if dialect == "tsql":
        parts = re.split(r"(?im)^\s*GO\s*$", sql)
        return [p.strip() for p in parts if p.strip()]
    if dialect == "oracle":
        return _split_oracle(sql)
    if dialect == "mysql":
        return _split_mysql(sql)
    return _split_semicolons(sql, dollar_quote=(dialect == "postgresql"))


def is_executable(stmt: str) -> bool:
    """Whether a statement has real SQL (not blank/comment-only)."""
    return re.sub(r"(?s)--[^\n]*|/\*.*?\*/", "", stmt).strip() != ""


def _split_mysql(sql: str) -> list[str]:
    """Split a MySQL script, honoring ``DELIMITER`` directives.

    Routine bodies are wrapped in ``DELIMITER $$ … END$$ DELIMITER ;`` so their
    inner ``;`` don't split them. Segment the script by the active delimiter,
    dropping the directives; plain regions are split on top-level ``;``.
    """
    statements: list[str] = []
    delimiter = ";"
    buf: list[str] = []

    def flush_plain(text: str) -> None:
        statements.extend(
            _split_semicolons(text, dollar_quote=False, backslash_escapes=True)
        )

    for raw_line in sql.splitlines():
        directive = re.match(r"(?i)^\s*DELIMITER\s+(\S+)\s*$", raw_line)
        if directive:
            chunk = "\n".join(buf)
            buf = []
            if delimiter == ";":
                flush_plain(chunk)
            else:
                statements.extend(_split_on_token(chunk, delimiter))
            delimiter = directive.group(1)
            continue
        buf.append(raw_line)

    chunk = "\n".join(buf)
    if delimiter == ";":
        flush_plain(chunk)
    else:
        statements.extend(_split_on_token(chunk, delimiter))
    return [s for s in statements if s.strip()]


def _split_on_token(text: str, token: str) -> list[str]:
    """Split ``text`` on a literal delimiter token (e.g. ``$$``), trimming it."""
    parts = text.split(token)
    return [p.strip() for p in parts if p.strip()]


def _split_oracle(sql: str) -> list[str]:
    """Split an Oracle script on ``/`` block terminators and top-level ``;``."""
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip() == "/":
            block = "\n".join(buf).strip()
            if block:
                statements.extend(_split_oracle_block(block))
            buf = []
            continue
        buf.append(line)
    tail = "\n".join(buf).strip()
    if tail:
        statements.extend(_split_oracle_block(tail))
    return [s for s in statements if s.strip() and is_executable(s)]


def _split_oracle_block(block: str) -> list[str]:
    """Split one ``/``-delimited chunk. It is a single PL/SQL block, plain
    ``;``-terminated DDL, or (re-runnable scripts) ``;``-DDL followed by a
    PL/SQL unit — SQL*Plus runs the DDL at ``;`` and the block at ``/``, but a
    programmatic client must send them separately (else ORA-03405). A leading
    comment before a PL/SQL block keeps it whole; otherwise split the leading
    DDL at ``;`` and keep the PL/SQL unit whole (its ``END;`` is required;
    ``;``-splitting would strip it, PLS-00103)."""
    core = re.sub(r"(?s)^(?:\s|--[^\n]*|/\*.*?\*/)+", "", block)
    if _ORACLE_PLSQL_HEAD_RE.match(core):
        return [block]
    pos = _first_toplevel_plsql_head(block)
    if pos < 0:
        return _split_semicolons(block, dollar_quote=False)
    ddl, plsql = block[:pos], block[pos:].strip()
    parts = _split_semicolons(ddl, dollar_quote=False) if ddl.strip() else []
    if plsql:
        parts.append(plsql)
    return parts


def _first_toplevel_plsql_head(text: str) -> int:
    """Index of the first PL/SQL unit head (CREATE PROCEDURE/FUNCTION/… or a
    bare BEGIN/DECLARE) at a line start and outside any string/comment, or -1."""
    i, n, in_string, line_start = 0, len(text), False, True
    while i < n:
        if not in_string:
            if text[i : i + 2] == "--":
                nl = text.find("\n", i)
                i = n if nl == -1 else nl
                continue
            if text[i : i + 2] == "/*":
                close = text.find("*/", i + 2)
                i = n if close == -1 else close + 2
                continue
        ch = text[i]
        if ch == "'":
            in_string = not in_string
            line_start = False
        elif ch == "\n":
            line_start = True
        elif not ch.isspace():
            if line_start and not in_string and _ORACLE_PLSQL_HEAD_RE.match(text[i:]):
                return i
            line_start = False
        i += 1
    return -1


def _split_semicolons(
    sql: str, *, dollar_quote: bool, backslash_escapes: bool = False
) -> list[str]:
    """Split on top-level ``;``, keeping $$-quoted / BEGIN…END bodies intact.

    String literals are respected: a ``;``/``--``/``/*`` inside one never acts
    as a separator or comment. ``''`` doubling is handled by the quote toggle;
    ``backslash_escapes`` additionally treats ``\\'`` as escaped (MySQL's
    default sql_mode).
    """
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False
    in_string = False
    depth_begin = 0
    i = 0
    text = sql
    while i < len(text):
        ch = text[i]
        two = text[i : i + 2]
        # Skip comments outside of strings/dollar-quotes so an apostrophe or
        # the word BEGIN/END inside a comment can't desync the splitter.
        if not in_dollar and not in_string:
            if two == "--":
                nl = text.find("\n", i)
                end = len(text) if nl == -1 else nl
                buf.append(text[i:end])
                i = end
                continue
            if two == "/*":
                close = text.find("*/", i + 2)
                end = len(text) if close == -1 else close + 2
                buf.append(text[i:end])
                i = end
                continue
        if dollar_quote and two == "$$":
            in_dollar = not in_dollar
            buf.append(two)
            i += 2
            continue
        if in_string and backslash_escapes and ch == "\\":
            # An escaped character (e.g. \') never closes the string.
            buf.append(text[i : i + 2])
            i += 2
            continue
        if ch == "'" and not in_dollar:
            in_string = not in_string
        if not in_dollar and not in_string:
            # Track BEGIN/END nesting (MySQL routine bodies have no $$). The
            # slice hides the previous character from ``\b``, so require a real
            # word start here or 'trend'/'xbegin' would desync the depth.
            at_word_start = i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")
            word = re.match(r"(?i)(BEGIN|END)\b", text[i:]) if at_word_start else None
            if word:
                kw = word.group(1).upper()
                if kw == "BEGIN":
                    depth_begin += 1
                elif kw == "END" and depth_begin > 0:
                    depth_begin -= 1
        if ch == ";" and not in_dollar and not in_string and depth_begin == 0:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def split_top_level_commas(text: str) -> list[str]:
    """Split *text* on commas at parenthesis depth zero, outside strings.

    ONE implementation for every list-shaped fragment (select lists, argument
    lists): a naive ``split(",")`` cuts inside a function call
    (``MAX(COALESCE(a, 0)) + 1`` — audit 2026-07-08, D8) and silently corrupts
    the expression.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            buf.append(ch)
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail or parts:
        parts.append(tail)
    return parts


_LEADING_TRIVIA_RE = re.compile(r"(?s)\A(?:\s*(?:--[^\n]*(?:\n|\Z)|/\*.*?\*/))*\s*")


def split_leading_trivia(sql: str) -> tuple[str, str]:
    """Split leading comments/blank lines (trivia) from the code of a batch.

    ONE implementation for every consumer (audit doc 04, P2 — comments are
    trivia): classification, guard extraction and terminator decisions must
    operate on the code, and emitters re-attach the trivia. Returns
    ``(trivia, code)`` where ``trivia + code == sql``.
    """
    m = _LEADING_TRIVIA_RE.match(sql)
    if not m or m.end() == 0:
        return "", sql
    return sql[: m.end()], sql[m.end() :]


def qualify_function_calls(
    sql: str, decide: Callable[[str, str | None], str | None]
) -> str:
    """Insert a schema prefix before selected function-call names in ``sql``.

    Walks the text outside string literals, comments and bracket/quote-
    delimited identifiers; for every bare identifier directly followed by
    ``(`` (whitespace allowed) it calls ``decide(name, prev_word)`` — the
    previous bare word, or ``None`` — and, when that returns a prefix string
    (e.g. ``"dbo."``), inserts it before the name. A name preceded by ``.``
    (already qualified) or ``@`` (a variable) is never offered.

    This replaces regex substitution over SQL text, which rewrote matches
    inside string literals (``'CALL (555)'``).
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    prev_word: str | None = None
    while i < n:
        ch = sql[i]
        # Comments.
        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j == -1 else j
            out.append(sql[i:j])
            i = j
            continue
        if ch == "/" and sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(sql[i:j])
            i = j
            continue
        # String literals / quoted identifiers (doubled-quote escapes).
        if ch in ("'", '"', "`"):
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
            prev_word = None
            continue
        if ch == "[":  # T-SQL bracketed identifier
            j = sql.find("]", i + 1)
            j = n if j == -1 else j + 1
            out.append(sql[i:j])
            i = j
            prev_word = None
            continue
        # Identifier run.
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] in "_$#"):
                j += 1
            word = sql[i:j]
            # Directly qualified (x.fn) or a variable (@fn)?
            preceded = sql[i - 1] if i > 0 else " "
            k = j
            while k < n and sql[k] in " \t":
                k += 1
            if k < n and sql[k] == "(" and preceded not in ".@:":
                prefix = decide(word, prev_word)
                if prefix:
                    out.append(prefix)
            out.append(word)
            i = j
            prev_word = word
            continue
        if ch.isdigit():  # a number (incl. trailing idents) — not a call
            j = i
            while j < n and (sql[j].isalnum() or sql[j] in "._"):
                j += 1
            out.append(sql[i:j])
            i = j
            prev_word = None
            continue
        out.append(ch)
        if ch not in " \t\r\n":
            prev_word = None
        i += 1
    return "".join(out)
