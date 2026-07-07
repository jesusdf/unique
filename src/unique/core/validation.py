# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Source-syntax validation.

Report syntax errors in the *input* SQL before transpiling, so a malformed script
(an unclosed parenthesis, a ``CREATE PROCEDURE`` with no preceding ``GO``, stray
tokens) is caught and located up front rather than silently producing garbage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot.errors import ParseError

from unique.core.batch_splitter import BatchSplitter, BatchType
from unique.core.converter import sqlglot_dialect_name

# SQL*Plus / client directives that are not SQL statements. sqlglot rejects them,
# but they are valid in a script run via SQL*Plus/SQLcl, so neutralize them (as
# comments, keeping the line count) before parsing rather than flag a false error.
_SQLPLUS_LINE = re.compile(
    r"(?im)^([ \t]*)"
    r"(PROMPT|SPOOL|WHENEVER|ACCEPT|DEFINE|UNDEFINE|COLUMN|CONNECT|DISCONNECT|PAUSE)\b"
)


@dataclass(frozen=True)
class SyntaxIssue:
    """A syntax error found in the source SQL."""

    line: int  # 1-based source line
    column: int
    message: str
    snippet: str  # the start of the offending statement, for context

    def __str__(self) -> str:
        where = f"line {self.line}" + (f", col {self.column}" if self.column else "")
        tail = f" — near: {self.snippet}" if self.snippet else ""
        return f"{where}: {self.message}{tail}"


def _neutralize_sqlplus(sql: str) -> str:
    """Comment out SQL*Plus directive lines (not SQL) while keeping the line count,
    so reported error line numbers stay accurate."""
    return _SQLPLUS_LINE.sub(r"\1-- \2", sql)


# A stored-program CREATE must be the first statement in its T-SQL batch; a
# preceding DML statement means a GO is missing between them.
_PROC_START = re.compile(
    r"(?im)^[ \t]*(?:CREATE|ALTER)\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?"
    r"(?:PROCEDURE|FUNCTION|TRIGGER)\b"
)
_DML_START = re.compile(r"(?im)^[ \t]*(?:INSERT|UPDATE|DELETE|MERGE|SELECT)\b")
# A line-starting statement keyword; more than one means several statements share
# a batch (T-SQL allows no ``;`` between them), which sqlglot cannot parse as one.
_STMT_START = re.compile(r"(?im)^[ \t]*(?:SELECT|INSERT|UPDATE|DELETE|MERGE|WITH)\b")


def _strip_noise(sql: str) -> str:
    """Blank out comments and SQL*Plus directives (keeping the line count) so a
    scan for real statements is not fooled by commented-out code."""
    sql = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), sql, flags=re.S)
    sql = re.sub(r"/\*.*", "", sql, flags=re.S)  # an unclosed /* runs to the end
    sql = re.sub(r"(?m)--.*$", "", sql)
    return _neutralize_sqlplus(sql)


def _missing_go_issue(batch: object) -> SyntaxIssue | None:
    """The one structural error worth flagging in a procedural batch: a
    ``CREATE PROCEDURE``/``FUNCTION``/``TRIGGER`` that does not start its batch
    (a DML statement precedes it, so a ``GO`` is missing). Everything else in a
    procedural batch (``BEGIN TRY``, batch ``BEGIN``/``END``, ``DECLARE`` …) is
    valid T-SQL that sqlglot cannot parse, so it is left to the procedural engine
    rather than mis-reported as a syntax error."""
    sql: str = batch.sql  # type: ignore[attr-defined]
    match = _PROC_START.search(sql)
    if not match:
        return None
    before = _strip_noise(sql[: match.start()])
    if not _DML_START.search(before):
        return None
    err_line = sql[: match.start()].count("\n") + 1
    lines = sql.splitlines()
    return SyntaxIssue(
        line=batch.line_offset + err_line,  # type: ignore[attr-defined]
        column=0,
        message="CREATE must be the first statement in its batch — a GO is missing",
        snippet=(lines[err_line - 1].strip()[:80] if err_line <= len(lines) else ""),
    )


def validate_source(sql: str, dialect: str) -> list[SyntaxIssue]:
    """Return the syntax errors in *sql* (parsed as *dialect*), per ``GO`` batch,
    with source line numbers.

    sqlglot in RAISE mode flags genuine errors while tolerating constructs it
    Command-fallbacks (which the transpiler preprocesses), so valid T-SQL does not
    false-positive. Returns an empty list when the input is syntactically sound.
    """
    sg = sqlglot_dialect_name(dialect)
    issues: list[SyntaxIssue] = []
    for batch in BatchSplitter.split(sql, dialect):
        if batch.is_empty:
            continue
        if batch.batch_type == BatchType.PROCEDURAL:
            # sqlglot cannot parse T-SQL procedural bodies, so RAISE would
            # false-positive on valid code; validate only the missing-GO shape.
            issue = _missing_go_issue(batch)
            if issue:
                issues.append(issue)
            continue
        if batch.batch_type not in (BatchType.DML, BatchType.DDL):
            # Only DML/DDL parse cleanly under sqlglot. Control-flow batches
            # (BEGIN TRY, IF/ELSE, WHILE) classify as UNKNOWN/SET_OPTION and would
            # false-positive, so they are left to the transpiler's engines.
            continue
        if len(_STMT_START.findall(_strip_noise(batch.sql))) > 1:
            # Several statements in one batch with no ``;`` between them — valid
            # T-SQL that sqlglot cannot parse as a unit; don't false-positive.
            continue
        try:
            sqlglot.parse(
                _neutralize_sqlplus(batch.sql),
                dialect=sg,
                error_level=sqlglot.ErrorLevel.RAISE,
            )
        except ParseError as exc:
            err = exc.errors[0] if exc.errors else {}
            err_line = int(err.get("line", 1))
            batch_lines = batch.sql.splitlines()
            snippet = (
                batch_lines[err_line - 1].strip()
                if 0 < err_line <= len(batch_lines)
                else next((ln.strip() for ln in batch_lines if ln.strip()), "")
            )
            # sqlglot sometimes embeds a full Token repr in the message; trim it.
            message = re.sub(
                r"<Token[^>]*>", "that token", str(err.get("description", str(exc)))
            ).strip()
            issues.append(
                SyntaxIssue(
                    line=batch.line_offset + err_line,
                    column=int(err.get("col", 0)),
                    message=message,
                    snippet=snippet[:80],
                )
            )
    return issues
