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

from unique.core.batch_splitter import BatchSplitter
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
