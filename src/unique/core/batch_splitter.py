# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Batch splitter for multi-statement SQL scripts.

Splits SQL scripts into individual executable batches respecting
dialect-specific batch separators and string/comment boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class BatchType(Enum):
    """Classification of a batch's content."""

    EMPTY = auto()
    COMMENT = auto()
    SET_OPTION = auto()
    DML = auto()
    DDL = auto()
    PROCEDURAL = auto()
    UNKNOWN = auto()


@dataclass
class Batch:
    """A single executable batch from a script."""

    sql: str
    batch_type: BatchType = BatchType.UNKNOWN
    line_offset: int = 0

    @property
    def is_empty(self) -> bool:
        """Whether this batch has no meaningful content."""
        stripped = self.sql.strip()
        if not stripped:
            return True
        lines = stripped.split("\n")
        return all(
            line.strip() == "" or line.strip().startswith("--") for line in lines
        )


_PROCEDURAL_PATTERNS = {
    "tsql": re.compile(
        r"(?i)^\s*(?:CREATE|ALTER)\s+(?:PROCEDURE|FUNCTION|TRIGGER)\b",
        re.MULTILINE,
    ),
    "oracle": re.compile(
        r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b",
        re.MULTILINE,
    ),
    "postgresql": re.compile(
        r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|TRIGGER)\b",
        re.MULTILINE,
    ),
    "mysql": re.compile(
        r"(?i)^\s*CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?(?:PROCEDURE|FUNCTION|TRIGGER)\b",
        re.MULTILINE,
    ),
    # SQLite has only triggers (no stored procedures or functions).
    "sqlite": re.compile(
        r"(?i)^\s*CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TRIGGER\b",
        re.MULTILINE,
    ),
}

# A T-SQL session/config option: ``SET <option> …`` where the option is an
# identifier (NOCOUNT, ANSI_NULLS, NOEXEC, DATEFORMAT, IDENTITY_INSERT, …), i.e.
# anything but a ``SET @var = …`` assignment (which is procedural). None of these
# options has a cross-engine equivalent, so they are documented, not executed.
_SET_PATTERN = re.compile(r"(?i)^\s*SET\s+(?!@)[A-Za-z_]\w*")

# SQL*Plus session directives: ``SET <option> [value]`` lines a real Oracle
# dump opens its blocks with. They are *client* commands (line-oriented, often
# no ``;``) with no cross-engine meaning. ``SET TRANSACTION`` / ``SET
# CONSTRAINTS`` are real Oracle SQL and deliberately NOT listed.
_SQLPLUS_SET_RE = re.compile(
    r"(?i)^\s*SET\s+(?:SERVEROUTPUT|DEFINE|ECHO|FEEDBACK|VERIFY|TERMOUT|TIMING|"
    r"SQLBLANKLINES|LINESIZE|PAGESIZE|HEADING|TRIMSPOOL|TRIMOUT|SCAN|"
    r"AUTOCOMMIT|WRAP|LONG|LONGCHUNKSIZE|APPINFO|ARRAYSIZE|COLSEP|COPYCOMMIT|"
    r"ERRORLOGGING|EXITCOMMIT|FLUSH|NEWPAGE|NULL|NUMFORMAT|NUMWIDTH|PAUSE|"
    r"RECSEP|SHOWMODE|SQLCASE|SQLCONTINUE|SQLNUMBER|SQLPROMPT|SUFFIX|TAB|"
    r"UNDERLINE|XQUERY)\b"
)

# A migration guard: ``IF [NOT] EXISTS (…)`` / ``IF OBJECT_ID(…) IS [NOT] NULL``.
# Routed to the SET_OPTION path, which extracts and transpiles the guarded DDL.
_IF_OBJECT_PATTERN = re.compile(r"(?i)^\s*IF\s+(?:NOT\s+)?(?:OBJECT_ID|EXISTS)\b")

# The guard-drop is only correct when the condition queries a *system catalog*
# (it has no target form, so the idempotent intent is kept by running the guarded
# DDL). A real-data condition must not have its guard dropped.
_CATALOG_REF_RE = re.compile(
    r"(?i)\b(?:OBJECT_ID|sysobjects|syscolumns|sysindexes|INFORMATION_SCHEMA)\b"
    r"|\bsys\.\w"
)
_TSQL_BEGIN_BLOCK_RE = re.compile(r"(?i)\bBEGIN\b")

# Well-known SQL Server system stored procedures (Microsoft-shipped) with no
# portable equivalent — routed to the DML pipeline, which documents/passes them
# through. The ``sp_`` prefix ALONE is not a reliable signal: user code legally
# names procedures ``sp_*`` too (this repo's ``sp_helperproc``/``sp_customproc`` synonym
# helpers, for one), so only these known names are treated as system; any other
# ``sp_*`` is a normal procedure call routed to the procedural engine (-> CALL).
_TSQL_SYSTEM_PROCS = frozenset(
    {
        "sp_executesql",
        "sp_rename",
        "sp_refreshview",
        "sp_recompile",
        "sp_addextendedproperty",
        "sp_updateextendedproperty",
        "sp_dropextendedproperty",
        "sp_bindrule",
        "sp_unbindrule",
        "sp_bindefault",
        "sp_unbindefault",
        "sp_addtype",
        "sp_droptype",
        "sp_settriggerorder",
        "sp_changeobjectowner",
        "sp_addmessage",
        "sp_dropmessage",
        "sp_configure",
        "sp_dboption",
        "sp_tableoption",
        "sp_depends",
        "sp_help",
        "sp_helptext",
        "sp_helpindex",
        "sp_helpconstraint",
        "sp_columns",
        "sp_tables",
        "sp_stored_procedures",
        "sp_spaceused",
        "sp_who",
        "sp_lock",
        "sp_addlinkedserver",
        "sp_addlinkedsrvlogin",
        "sp_serveroption",
        "sp_msforeachtable",
        "sp_msforeachdb",
        "sp_addrole",
        "sp_addrolemember",
        "sp_droprolemember",
        "sp_grantdbaccess",
        "sp_revokedbaccess",
        "sp_addlogin",
        "sp_droplogin",
        "sp_adduser",
        "sp_dropuser",
        "sp_password",
        "sp_defaultdb",
        "sp_addsrvrolemember",
        "sp_dropsrvrolemember",
        "sp_grantlogin",
        "sp_revokelogin",
        "sp_fulltext_database",
        "sp_fulltext_table",
        "sp_fulltext_column",
        "sp_fulltext_catalog",
        "sp_reset_connection",
    }
)

# A standalone EXEC/EXECUTE of a stored procedure. The captured group is the
# procedure's final (unqualified) name, so a known system procedure (possibly
# schema-qualified like sys.sp_x) can be excluded — the DML pipeline
# documents/passes those through.
_TSQL_EXEC_PROC_PATTERN = re.compile(
    r"(?i)^\s*EXEC(?:UTE)?\s+"
    r"(?:\[?\w+\]?\s*\.\s*)*"  # optional schema/database qualifiers
    r"\[?(\w+)\]?",  # group 1: the final procedure name
)

# A batch-level DECLARE (a local variable used by following statements) is an
# anonymous procedural block, not DML.
_TSQL_DECLARE_PATTERN = re.compile(r"(?i)^\s*DECLARE\s+@", re.MULTILINE)

# A top-level PRINT and a variable assignment (``SET @v = …``, distinct from a
# session option like ``SET NOCOUNT ON``) are procedural: route them to the
# procedural engine so PRINT becomes each target's message form and the
# assignment is translated, instead of a DML "Unhandled expression" carrier.
_TSQL_PRINT_PATTERN = re.compile(r"(?i)^\s*PRINT\b")
_TSQL_SET_VAR_PATTERN = re.compile(r"(?i)^\s*SET\s+@\w+\s*=(?![=])")

# A top-level Oracle anonymous PL/SQL block opens with BEGIN or DECLARE.
_ORACLE_ANON_BLOCK_PATTERN = re.compile(r"(?i)^\s*(?:BEGIN|DECLARE)\b")

# A standalone stored-procedure call: CALL proc(...) (MySQL/PostgreSQL/Oracle).
_CALL_PROC_PATTERN = re.compile(r"(?i)^\s*CALL\s+\w")

# A ``GO`` batch terminator on its own line (case-insensitive, optional surrounding
# horizontal whitespace). Matched only at true top level by _split_on_toplevel_go.
_GO_LINE = re.compile(r"[ \t]*GO[ \t]*(?:\r?\n|\Z)", re.IGNORECASE)


def _split_on_toplevel_go(sql: str) -> list[str]:
    """Split T-SQL at ``GO`` separators, ignoring any ``GO`` that sits inside a
    ``/* … */`` block comment, a ``--`` line comment, or a string literal — a naive
    line split would break a multi-batch block comment and transpile its (commented
    out) content as live code."""
    parts: list[str] = []
    start = i = 0
    n = len(sql)
    line_start = True
    while i < n:
        pair = sql[i : i + 2]
        if pair == "/*":  # block comment: skip to the closing */
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            line_start = False
            continue
        if pair == "--":  # line comment: skip to the newline (kept for the split)
            nl = sql.find("\n", i + 2)
            i = n if nl == -1 else nl
            line_start = False
            continue
        if sql[i] == "'":  # string literal: skip to the closing quote ('' escapes)
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if sql[j + 1 : j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            line_start = False
            continue
        if line_start:
            m = _GO_LINE.match(sql, i)
            if m:
                parts.append(sql[start:i])
                start = i = m.end()
                line_start = True
                continue
        line_start = sql[i] == "\n"
        i += 1
    parts.append(sql[start:])
    return parts


def classify_batch(sql: str, dialect: str) -> BatchType:
    """Classify a batch's content type.

    Args:
        sql: The batch SQL text.
        dialect: The source dialect name.

    Returns:
        The BatchType classification.
    """
    stripped = sql.strip()
    if not stripped:
        return BatchType.EMPTY

    # Comments — a leading ``/* … */`` section header, a ``--`` line, or a whole
    # commented-out block — must not drive classification, or a batch like
    # ``/* header */ SET ANSI_NULLS ON`` or ``/* header */ IF OBJECT_ID(…) DROP``
    # is mis-typed (its real statement isn't the first line) and emitted as mangled
    # code. Classify against the comment-stripped text; the batch is emitted whole.
    without_comments = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.S)
    without_comments = re.sub(r"(?m)^[ \t]*--.*$", "", without_comments)
    if not without_comments.strip():
        return BatchType.COMMENT

    lines = [line for line in without_comments.split("\n") if line.strip()]
    if not lines:
        return BatchType.COMMENT

    first_meaningful = lines[0].strip()

    # For Oracle, only the SQL*Plus client directives are "SET options";
    # SET TRANSACTION / SET CONSTRAINTS are real SQL and flow to the DML
    # path (the targets have their own spellings for them).
    if _SET_PATTERN.match(first_meaningful) and (
        dialect != "oracle" or _SQLPLUS_SET_RE.match(first_meaningful)
    ):
        return BatchType.SET_OPTION

    if _IF_OBJECT_PATTERN.match(first_meaningful):
        # A non-catalog ``IF EXISTS(…) …`` is procedural control flow, not an
        # idempotent-DDL guard: dropping its condition (as the guard path
        # does) silently changes semantics — with OR without a ``BEGIN`` block
        # (the unbracketed single-statement form is the common spelling in
        # real migration scripts; audit 2026-07-08, N1). Route it to the
        # procedural engine, which translates the IF faithfully per target.
        if dialect == "tsql" and not _CATALOG_REF_RE.search(without_comments):
            return BatchType.PROCEDURAL
        return BatchType.SET_OPTION

    if dialect == "tsql":
        exec_match = _TSQL_EXEC_PROC_PATTERN.match(first_meaningful)
        if exec_match and exec_match.group(1).lower() not in _TSQL_SYSTEM_PROCS:
            return BatchType.PROCEDURAL
        if _TSQL_DECLARE_PATTERN.match(first_meaningful):
            return BatchType.PROCEDURAL
        if _TSQL_PRINT_PATTERN.match(first_meaningful):
            return BatchType.PROCEDURAL
        if _TSQL_SET_VAR_PATTERN.match(first_meaningful):
            return BatchType.PROCEDURAL

    if dialect == "oracle" and _TSQL_EXEC_PROC_PATTERN.match(first_meaningful):
        # SQL*Plus ``EXEC proc(args)`` — shorthand for ``BEGIN proc(args);
        # END;``. sqlglot has no model for it (it parses as an *alias* and
        # ships as T-SQL impersonation syntax, ``EXEC AS proc``, with the
        # arguments dropped — audit 2026-07-08, D1). Route it to the
        # procedural engine, which models the call per target.
        return BatchType.PROCEDURAL

    if _CALL_PROC_PATTERN.match(first_meaningful):
        # A standalone stored-procedure call (MySQL/PostgreSQL/Oracle
        # ``CALL proc(args)``). Route it to the procedural engine so it becomes
        # each target's call form instead of an "unhandled Command" comment.
        return BatchType.PROCEDURAL

    if dialect == "oracle" and _ORACLE_ANON_BLOCK_PATTERN.match(first_meaningful):
        # A top-level ``BEGIN … END;`` / ``DECLARE … BEGIN … END;`` is an
        # anonymous PL/SQL block (Oracle has no ``BEGIN TRANSACTION``), not DML.
        # Route it to the procedural engine so its loops / EXECUTE IMMEDIATE are
        # translated, instead of letting the DML path mangle it.
        return BatchType.PROCEDURAL

    pattern = _PROCEDURAL_PATTERNS.get(dialect)
    if pattern and pattern.search(without_comments):
        return BatchType.PROCEDURAL

    ddl_keywords = ("CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE")
    upper = first_meaningful.upper()
    for kw in ddl_keywords:
        if upper.startswith(kw):
            return BatchType.DDL

    dml_keywords = ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "WITH")
    for kw in dml_keywords:
        if upper.startswith(kw):
            return BatchType.DML

    return BatchType.UNKNOWN


class BatchSplitter:
    """Splits SQL scripts into batches based on dialect separators."""

    @staticmethod
    def split(sql: str, dialect: str) -> list[Batch]:
        """Split a SQL script into individual batches.

        Args:
            sql: The complete SQL script text.
            dialect: The source dialect name.

        Returns:
            A list of Batch objects.
        """
        sql = sql.replace("\r\n", "\n").replace("\r", "\n")

        if dialect == "tsql":
            return BatchSplitter._split_tsql(sql)
        elif dialect == "oracle":
            return BatchSplitter._split_oracle(sql)
        elif dialect == "postgresql":
            return BatchSplitter._split_postgresql(sql)
        elif dialect == "mysql":
            return BatchSplitter._split_mysql(sql)
        else:
            return [Batch(sql=sql, batch_type=classify_batch(sql, dialect))]

    @staticmethod
    def _split_tsql(sql: str) -> list[Batch]:
        """Split T-SQL on GO batch separators."""
        # GO is a case-insensitive batch terminator (``go`` is valid) and may
        # carry leading whitespace; split only at top-level GO (a GO inside a
        # block/line comment or a string literal is not a separator).
        parts = _split_on_toplevel_go(sql)
        batches = []
        line_offset = 0
        for part in parts:
            stripped = part.strip()
            if stripped:
                batch = Batch(
                    sql=stripped,
                    batch_type=classify_batch(stripped, "tsql"),
                    line_offset=line_offset,
                )
                batches.append(batch)
            line_offset += part.count("\n") + 1
        return batches

    @staticmethod
    def _split_oracle(sql: str) -> list[Batch]:
        """Split Oracle SQL into batches.

        Oracle terminates simple statements with ``;`` and PL/SQL blocks
        (CREATE PROCEDURE/FUNCTION/TRIGGER/PACKAGE, anonymous DECLARE/BEGIN
        blocks) with a line containing only ``/``. This splitter honors
        both: a lone ``/`` always ends the current batch, and otherwise a
        ``;`` ends a statement unless we are inside a PL/SQL block, where we
        wait for the slash. SQL*Plus directives (SET, PROMPT, etc.) are kept
        as their own single-line batches.
        """
        batches: list[Batch] = []
        current: list[str] = []
        batch_start = 0
        in_plsql = False
        in_comment = False
        begin_depth = 0

        plsql_start = re.compile(
            r"(?i)\bCREATE\s+(OR\s+REPLACE\s+)?"
            r"(PROCEDURE|FUNCTION|TRIGGER|PACKAGE|TYPE)\b"
        )
        anon_start = re.compile(r"(?i)^\s*(DECLARE|BEGIN)\b")
        begin_re = re.compile(r"(?i)\bBEGIN\b")
        end_re = re.compile(r"(?i)\bEND\b")

        def comment_state_after(line: str, state: bool) -> bool:
            """Block-comment state after *line* (strings and ``--`` respected)."""
            i = 0
            in_string = False
            while i < len(line):
                two = line[i : i + 2]
                if state:
                    if two == "*/":
                        state = False
                        i += 2
                        continue
                    i += 1
                    continue
                if in_string:
                    if line[i] == "'":
                        in_string = False
                    i += 1
                    continue
                if line[i] == "'":
                    in_string = True
                    i += 1
                    continue
                if two == "--":
                    break
                if two == "/*":
                    state = True
                    i += 2
                    continue
                i += 1
            return state

        def flush(end_line: int) -> None:
            nonlocal current, batch_start
            text = "\n".join(current).strip()
            if text.endswith(";"):
                text = text[:-1].rstrip()
            if text:
                batches.append(
                    Batch(
                        sql=text,
                        batch_type=classify_batch(text, "oracle"),
                        line_offset=batch_start,
                    )
                )
            current = []
            batch_start = end_line + 1

        for i, line in enumerate(sql.split("\n")):
            stripped = line.strip()

            # Inside a /* */ block comment nothing is structural: not a lone
            # '/', not a directive, not a PL/SQL head. A commented-out block
            # with its '/' terminator inside the comment used to desync the
            # splitter into orphan '*/ …' batches (real-dump finding).
            if in_comment:
                current.append(line)
                in_comment = comment_state_after(line, True)
                continue

            # SQL*Plus 'rem' (remark) and 'prompt' (echo) directives are not
            # SQL, but they carry useful information (copyright notices,
            # progress messages). Preserve them as SQL line comments in their
            # own batch rather than dropping them or letting them corrupt the
            # following statement's batch.
            rem_match = re.match(r"(?i)^(rem|prompt)\b[ \t]?(.*)$", stripped)
            if not in_plsql and rem_match:
                # Flush any statement accumulated so far so the comment keeps
                # its position relative to surrounding statements.
                if current:
                    flush(i - 1)
                directive = rem_match.group(1).lower()
                text = rem_match.group(2).rstrip()
                comment = f"-- {text}" if text else "--"
                if directive == "prompt" and text:
                    comment = f"-- PROMPT: {text}"
                batches.append(
                    Batch(
                        sql=comment,
                        batch_type=BatchType.COMMENT,
                        line_offset=i,
                    )
                )
                batch_start = i + 1
                continue

            # A SQL*Plus ``SET <option>`` directive is line-oriented (usually
            # no ``;``): left inline it glues to the following statement and
            # corrupts it on every target. Peel it into its own SET_OPTION
            # batch — but only at a statement boundary (nothing but trivia
            # accumulated), since a line starting with SET *inside* a
            # statement is an UPDATE's SET clause.
            if not in_plsql and _SQLPLUS_SET_RE.match(stripped):
                from unique.core.sql_split import split_leading_trivia

                accumulated = "\n".join(current)
                if not split_leading_trivia(accumulated)[1].strip():
                    batches.append(
                        Batch(
                            sql=stripped.rstrip(";").rstrip(),
                            batch_type=BatchType.SET_OPTION,
                            line_offset=i,
                        )
                    )
                    continue

            # A lone slash terminates the current (PL/SQL) batch.
            if stripped == "/":
                flush(i)
                in_plsql = False
                begin_depth = 0
                continue

            current.append(line)
            in_comment = comment_state_after(line, False)
            if in_comment:
                continue

            if not in_plsql and (plsql_start.search(line) or anon_start.match(line)):
                in_plsql = True
                begin_depth = 0

            if in_plsql:
                begin_depth += len(begin_re.findall(line))
                for m in end_re.finditer(line):
                    rest = line[m.end() :].lstrip().upper()
                    if rest.startswith(("IF", "LOOP", "WHILE", "CASE")):
                        continue
                    begin_depth -= 1
                # Inside a PL/SQL block we wait for the terminating slash,
                # so do not split on semicolons here.
                continue

            if stripped.endswith(";"):
                flush(i)

        remaining = "\n".join(current).strip()
        if remaining:
            if remaining.endswith(";"):
                remaining = remaining[:-1].rstrip()
            batches.append(
                Batch(
                    sql=remaining,
                    batch_type=classify_batch(remaining, "oracle"),
                    line_offset=batch_start,
                )
            )
        return batches

    @staticmethod
    def _split_postgresql(sql: str) -> list[Batch]:
        """Split PostgreSQL respecting $$ dollar-quoting.

        Procedural blocks are wrapped in $$ ... $$ and use CREATE FUNCTION
        with LANGUAGE plpgsql. We split on semicolons outside dollar-quoted
        strings.
        """
        batches: list[Batch] = []
        current: list[str] = []
        in_dollar_quote = False
        dollar_tag = ""
        batch_start = 0

        for i, line in enumerate(sql.split("\n")):
            current.append(line)

            if in_dollar_quote:
                if dollar_tag in line:
                    # The closing $$ may be followed by "LANGUAGE plpgsql;" that
                    # ends the statement, so fall through to the ;-split check
                    # instead of swallowing the next statement into this batch.
                    in_dollar_quote = False
                else:
                    continue
            else:
                dollar_match = re.search(r"\$([a-zA-Z_]*)\$", line)
                if dollar_match:
                    dollar_tag = dollar_match.group(0)
                    rest = line[dollar_match.end() :]
                    if dollar_tag not in rest:
                        # Body opens here and continues on later lines.
                        in_dollar_quote = True
                        continue

            stripped_line = line.rstrip()
            if stripped_line.endswith(";") and not in_dollar_quote:
                text = "\n".join(current).strip()
                if text:
                    batches.append(
                        Batch(
                            sql=text,
                            batch_type=classify_batch(text, "postgresql"),
                            line_offset=batch_start,
                        )
                    )
                current = []
                batch_start = i + 1

        remaining = "\n".join(current).strip()
        if remaining:
            batches.append(
                Batch(
                    sql=remaining,
                    batch_type=classify_batch(remaining, "postgresql"),
                    line_offset=batch_start,
                )
            )

        return batches

    @staticmethod
    def _split_mysql(sql: str) -> list[Batch]:
        """Split MySQL statements.

        Honors explicit DELIMITER changes, and—crucially for scripts that
        omit them—tracks CREATE PROCEDURE/FUNCTION/TRIGGER bodies so that
        the semicolons inside a BEGIN ... END block do not split the
        routine into fragments.
        """
        delimiter = ";"
        batches: list[Batch] = []
        current: list[str] = []
        batch_start = 0
        begin_depth = 0
        in_routine = False

        routine_re = re.compile(
            r"(?i)\bCREATE\s+(?:DEFINER\s*=\s*\S+\s+)?"
            r"(?:PROCEDURE|FUNCTION|TRIGGER)\b"
        )
        begin_re = re.compile(r"(?i)\bBEGIN\b")
        end_re = re.compile(r"(?i)\bEND\b")

        def flush(upto_line: int) -> None:
            nonlocal current, batch_start
            text = "\n".join(current).strip()
            if text.endswith(";"):
                text = text[:-1].rstrip()
            if text:
                batches.append(
                    Batch(
                        sql=text,
                        batch_type=classify_batch(text, "mysql"),
                        line_offset=batch_start,
                    )
                )
            current = []
            batch_start = upto_line + 1

        for i, line in enumerate(sql.split("\n")):
            stripped = line.strip()

            delimiter_match = re.match(r"(?i)^DELIMITER\s+(\S+)\s*$", stripped)
            if delimiter_match:
                if current:
                    flush(i - 1)
                delimiter = delimiter_match.group(1)
                batch_start = i + 1
                # A custom delimiter delimits routine bodies itself, so any
                # BEGIN/END tracking state is stale — reset it so it can't leak
                # past the directive (a lingering in_routine would stop every
                # following ``;`` statement from splitting).
                in_routine = False
                begin_depth = 0
                continue

            # Track routine bodies (BEGIN/END nesting) only when no custom
            # delimiter is in effect (a custom delimiter marks the boundaries).
            if delimiter == ";" and routine_re.search(line):
                in_routine = True
            if in_routine and delimiter == ";":
                # Count BEGIN/END on this line, ignoring END IF/END LOOP etc.
                begin_depth += len(begin_re.findall(line))
                for m in end_re.finditer(line):
                    rest = line[m.end() :].lstrip().upper()
                    if rest.startswith(("IF", "LOOP", "WHILE", "CASE", "REPEAT")):
                        continue
                    begin_depth -= 1
                    if begin_depth <= 0:
                        begin_depth = 0
                        in_routine = False

            current.append(line)

            if delimiter != ";":
                if stripped.endswith(delimiter):
                    text = "\n".join(current).strip()
                    text = text[: -len(delimiter)].rstrip()
                    if text:
                        batches.append(
                            Batch(
                                sql=text,
                                batch_type=classify_batch(text, "mysql"),
                                line_offset=batch_start,
                            )
                        )
                    current = []
                    batch_start = i + 1
            elif stripped.endswith(";") and not in_routine and begin_depth == 0:
                flush(i)

        remaining = "\n".join(current).strip()
        if remaining:
            batches.append(
                Batch(
                    sql=remaining,
                    batch_type=classify_batch(remaining, "mysql"),
                    line_offset=batch_start,
                )
            )

        return batches
