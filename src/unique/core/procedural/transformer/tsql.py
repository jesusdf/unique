# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — tsql target."""

from __future__ import annotations

import re
from collections.abc import Callable

from unique.core.ast_nodes import (
    AssignmentStatement,
    ASTNode,
    CreateTriggerStatement,
    EmbeddedDML,
    ExceptionBlock,
    IfStatement,
    Literal,
    LoopStatement,
    NullStatement,
    RawSQL,
    ReturnStatement,
    SetVariableStatement,
    StatementList,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.converter import IDENTITY_COLUMNS, PG_TRIGGER_FN_BODIES, USER_FUNCTIONS
from unique.core.converter.emit import _convert_date_format
from unique.core.mappings import (
    ORACLE_DATE_FORMAT_STYLES,
    TSQL_OBJECT_CONTEXT_WORDS,
    tsql_call_needs_schema,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)
from unique.core.sql_split import qualify_function_calls


def _strip_wrapping_parens(text: str) -> str:
    """Remove a single fully-enclosing ``(...)`` pair, if present.

    Unlike ``str.strip("()")``, this only peels a matched outer pair — a
    predicate whose outermost token is a function call (``isnull(j)``) keeps
    its closing paren instead of being corrupted into ``isnull(j``.
    """
    text = text.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return text
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            # The first ``)`` that closes the opening paren must be the LAST
            # character for the whole string to be one wrapping pair.
            if depth == 0:
                return text[1:-1].strip() if i == len(text) - 1 else text
    return text


class TSqlTransformer(ProceduralTransformer):
    #: Uniquifies the sys.indexes lookup variables across a batch.
    _drop_index_n = 0
    """Transforms toward T-SQL (SQL Server)."""

    target_name = "tsql"

    #: ``a - b`` between two identifiers (used to rewrite date subtraction).
    _SUBTRACT_RE = re.compile(r"(@?\w+)\s*-\s*(@?\w+)")

    @staticmethod
    def _pipes_to_plus(sql: str) -> str:
        """Rewrite ``||`` concatenation to T-SQL ``+`` outside string literals
        (356 dynamic-SQL assignments on the real dump leaked ``||``)."""
        out: list[str] = []
        in_string = False
        i = 0
        while i < len(sql):
            ch = sql[i]
            if in_string:
                out.append(ch)
                if ch == "'":
                    if i + 1 < len(sql) and sql[i + 1] == "'":
                        out.append("'")
                        i += 2
                        continue
                    in_string = False
                i += 1
                continue
            if ch == "'":
                in_string = True
                out.append(ch)
                i += 1
                continue
            if ch == "|" and sql[i : i + 2] == "||":
                out.append("+")
                i += 2
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    #: Oracle/VB-style datepart spellings -> the T-SQL keyword.
    _QUOTED_DATEPARTS = {
        "Y": "YEAR",
        "YY": "YEAR",
        "YYYY": "YEAR",
        "Q": "QUARTER",
        "M": "MONTH",
        "MM": "MONTH",
        "D": "DAY",
        "DD": "DAY",
        "W": "WEEK",
        "WW": "WEEK",
        "H": "HOUR",
        "HH": "HOUR",
        "N": "MINUTE",
        "MI": "MINUTE",
        "S": "SECOND",
        "SS": "SECOND",
    }

    #: Common unambiguous Oracle TO_DATE formats -> T-SQL CONVERT style
    #: (a trailing HH24:MI:SS is stripped before lookup; the datetime styles
    #: parse an appended time-of-day).
    _TO_DATE_STYLES = ORACLE_DATE_FORMAT_STYLES

    #: SYS_CONTEXT('USERENV', '<attr>') attributes with a direct T-SQL form.
    _SYS_CONTEXT_MAP = {
        "HOST": "HOST_NAME()",
        "OS_USER": "SUSER_SNAME()",
        "SESSION_USER": "SYSTEM_USER",
        "CURRENT_USER": "CURRENT_USER",
        "SID": "@@SPID",
        "DB_NAME": "DB_NAME()",
    }
    _SYS_CONTEXT_RE = re.compile(
        r"(?is)\bSYS_CONTEXT\s*\(\s*'USERENV'\s*,\s*'(\w+)'\s*\)"
    )
    _DBMS_LOB_SUBSTR3_RE = re.compile(
        r"(?is)\bDBMS_LOB\s*\.\s*SUBSTR(?:ING)?\s*\(\s*([^(),]+?)\s*,"
        r"\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)"
    )
    _DBMS_LOB_SUBSTR2_RE = re.compile(
        r"(?is)\bDBMS_LOB\s*\.\s*SUBSTR(?:ING)?\s*\(\s*([^(),]+?)\s*,"
        r"\s*([^(),]+?)\s*\)"
    )

    @staticmethod
    def _three_arg_substring(sql: str) -> str:
        """Give every 2-argument SUBSTRING an explicit length and a
        sign-aware start (Oracle SUBSTR(s, -n) reads from the end)."""
        from unique.core.sql_split import split_top_level_commas

        out: list[str] = []
        i = 0
        pat = re.compile(r"(?is)\bSUBSTRING\s*\(")
        while True:
            m = pat.search(sql, i)
            if not m:
                out.append(sql[i:])
                break
            depth, j = 1, m.end()
            while j < len(sql) and depth:
                c = sql[j]
                if c == "'":
                    j += 1
                    while j < len(sql):
                        if sql[j] == "'":
                            if j + 1 < len(sql) and sql[j + 1] == "'":
                                j += 2
                                continue
                            break
                        j += 1
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner = sql[m.end() : j]
            args = split_top_level_commas(inner)
            out.append(sql[i : m.start()])
            if len(args) == 2:
                s, pos = args[0].strip(), args[1].strip()
                start = (
                    f"CASE WHEN ({pos}) < 0 THEN LEN({s}) + ({pos}) + 1 "
                    f"ELSE ({pos}) END"
                )
                out.append(f"SUBSTRING({s}, {start}, LEN({s}))")
            else:
                out.append(sql[m.start() : j + 1])
            i = j + 1
        return "".join(out)

    def _map_oracle_builtins(self, sql: str) -> str:
        """Oracle/PG built-ins with a direct T-SQL form that leak through
        the raw-expression path (found live in the 13 MB corpus,
        2026-07-10; plpgsql shares SQLERRM and adds SQLSTATE)."""
        if self._source not in ("oracle", "postgresql"):
            return sql
        # Oracle's ALTER TRIGGER x ENABLE names only the trigger; T-SQL
        # needs the table (resolved from sys.triggers at run time).
        mt = re.match(
            r"(?is)^\s*ALTER\s+TRIGGER\s+([\w\[\]]+)\s+(ENABLE|DISABLE)" r"\s*;?\s*$",
            sql,
        )
        if mt:
            trg = mt.group(1).strip("[]")
            action = mt.group(2).upper()
            self._drop_index_n += 1
            var = f"@uq_trgtbl{self._drop_index_n}"
            return (
                f"DECLARE {var} sysname = (SELECT TOP (1) "
                f"OBJECT_NAME(parent_id) FROM sys.triggers "
                f"WHERE name = '{trg}');\n"
                f"IF {var} IS NOT NULL "
                f"EXEC(N'ALTER TABLE [' + {var} + '] {action} "
                f"TRIGGER [{trg}]');"
            )
        # Oracle's DROP INDEX names only the index; T-SQL requires the table
        # (error 159). Resolve it from sys.indexes at run time.
        m = re.match(r"(?is)^\s*DROP\s+INDEX\s+([A-Za-z_]\w*)\s*;?\s*$", sql)
        if m:
            ix = m.group(1)
            self._drop_index_n += 1
            var = f"@uq_ixtbl{self._drop_index_n}"
            return (
                f"DECLARE {var} sysname = (SELECT TOP (1) "
                f"OBJECT_NAME(object_id) FROM sys.indexes "
                f"WHERE name = '{ix}');\n"
                f"IF {var} IS NOT NULL "
                f"EXEC(N'DROP INDEX [{ix}] ON [' + {var} + ']');"
            )
        # sqlglot pairs Oracle index keys with a NULLS-ordering CASE
        # emulation; a T-SQL index key cannot be an expression (error 156).
        if re.search(r"(?i)\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", sql):
            sql = re.sub(
                r"(?is)CASE\s+WHEN\s+.+?\s+IS\s+NULL\s+THEN\s+1\s+ELSE\s+0"
                r"\s+END(?:\s+(?:ASC|DESC))?\s*,\s*",
                "",
                sql,
            )
        # Oracle user_* catalog probes -> the sys.* equivalents (the column
        # renames are gated on the catalog's presence in the same text so a
        # user column named index_name is never touched).
        if re.search(r"(?i)\buser_tab_col(?:umn)?s\b", sql):
            sql = re.sub(r"(?i)\buser_tab_col(?:umn)?s\b", "sys.columns", sql)
            sql = re.sub(r"(?i)\btable_name\b", "OBJECT_NAME(object_id)", sql)
            sql = re.sub(r"(?i)\bcolumn_name\b", "name", sql)
        if re.search(r"(?i)\buser_indexes\b", sql):
            sql = re.sub(r"(?i)\buser_indexes\b", "sys.indexes", sql)
            sql = re.sub(r"(?i)\bindex_name\b", "name", sql)
        if re.search(r"(?i)\buser_tables\b", sql):
            sql = re.sub(r"(?i)\buser_tables\b", "sys.tables", sql)
            sql = re.sub(r"(?i)\btable_name\b", "name", sql)
        if re.search(r"(?i)\buser_objects\b", sql):
            sql = re.sub(r"(?i)\buser_objects\b", "sys.objects", sql)
            sql = re.sub(r"(?i)\bobject_name\b(?!\s*\()", "name", sql)
        from unique.core.converter import map_sequence_refs

        sql = map_sequence_refs(sql, "tsql")
        # The implicit-cursor row count reads from @@ROWCOUNT.
        sql = re.sub(r"(?i)\bSQL\s*%\s*ROWCOUNT\b", "@@ROWCOUNT", sql)
        # Implicit-cursor success attributes read the affected-row count;
        # named-cursor %FOUND/%NOTFOUND read the last FETCH's status (T-SQL
        # has ONE global @@FETCH_STATUS — correct right after that cursor's
        # FETCH, the shape these loops take).
        sql = re.sub(r"(?i)\bSQL\s*%\s*NOTFOUND\b", "@@ROWCOUNT = 0", sql)
        sql = re.sub(r"(?i)\bSQL\s*%\s*FOUND\b", "@@ROWCOUNT > 0", sql)
        sql = re.sub(r"(?i)\b\w+\s*%\s*NOTFOUND\b", "@@FETCH_STATUS <> 0", sql)
        sql = re.sub(r"(?i)\b\w+\s*%\s*FOUND\b", "@@FETCH_STATUS = 0", sql)
        # MONTHS_BETWEEN(a, b) -> DATEDIFF(MONTH, b, a). Whole months only
        # (T-SQL has no fractional form); the boundary-counting difference
        # is the standard accepted approximation.
        arg = r"((?:[^(),]|\([^()]*\))+?)"
        sql = re.sub(
            rf"(?is)\bMONTHS_BETWEEN\s*\(\s*{arg}\s*,\s*{arg}\s*\)",
            r"DATEDIFF(MONTH, \2, \1)",
            sql,
        )

        # Oracle-style QUOTED dateparts in DATEDIFF/DATEADD (live 1023:
        # DATEDIFF('Y', a, b)): T-SQL takes a bare keyword.
        def _bare_datepart(m: re.Match[str]) -> str:
            part = self._QUOTED_DATEPARTS.get(m.group(2).upper())
            if part is None:
                return m.group(0)
            return f"{m.group(1).upper()}({part}, "

        sql = re.sub(
            r"(?is)\b(DATEDIFF|DATEADD)\s*\(\s*'(\w+)'\s*,", _bare_datepart, sql
        )
        # EXTRACT(part FROM x): T-SQL has no EXTRACT (error 195) — DATEPART.
        sql = re.sub(
            r"(?is)\bEXTRACT\s*\(\s*(YEAR|MONTH|DAY|HOUR|MINUTE|SECOND)\s+FROM\s+"
            rf"{arg}\s*\)",
            r"DATEPART(\1, \2)",
            sql,
        )
        # TO_NUMBER(x) -> CAST(x AS DECIMAL(38, 10)) (the project's NUMBER
        # carrier). A bare name rename would produce ``CAST(x)`` without AS.
        sql = re.sub(
            rf"(?is)\bTO_NUMBER\s*\(\s*{arg}\s*\)",
            r"CAST(\1 AS DECIMAL(38, 10))",
            sql,
        )

        # Formatted TO_DATE(x, 'fmt'): the common unambiguous Oracle formats
        # map to a fixed T-SQL CONVERT style; anything else stays visible.
        def _to_date_style(m: re.Match[str]) -> str:
            fmt = m.group(2).strip().upper()
            style = self._TO_DATE_STYLES.get(re.sub(r"\s*HH24:MI:SS$", "", fmt))
            if style is None:
                return m.group(0)
            return f"CONVERT(DATETIME, {m.group(1).strip()}, {style})"

        sql = re.sub(
            rf"(?is)\bTO_DATE\s*\(\s*{arg}\s*,\s*'([^']*)'\s*\)",
            _to_date_style,
            sql,
        )

        # Formatted TO_CHAR(x, '<date fmt>') -> FORMAT(x, '<.NET fmt>') via
        # the shared token table; numeric masks (no date tokens) stay put.
        def _to_char_format(m: re.Match[str]) -> str:
            fmt = m.group(2)
            if not re.search(r"(?i)YY|MM|DD|HH|MI|SS", fmt):
                return m.group(0)
            net = _convert_date_format(fmt, "oracle", "tsql")
            return f"FORMAT({m.group(1).strip()}, '{net}')"

        sql = re.sub(
            rf"(?is)\bTO_CHAR\s*\(\s*{arg}\s*,\s*'([^']*)'\s*\)",
            _to_char_format,
            sql,
        )
        # Two-argument SUBSTRING (Oracle SUBSTR(s, p): from p to the end;
        # negative p counts from the end): T-SQL requires 3 arguments
        # (error 174). Balanced-paren scan — the arguments may nest calls
        # deeper than the one-level {arg} regex tolerates.
        sql = self._three_arg_substring(sql)
        # RPAD/LPAD have no T-SQL builtin: build from REPLICATE (LEFT/RIGHT
        # truncate to the target length, matching Oracle when the input is
        # longer than the pad length). Mirrors the IR emitter's expansion.
        sql = re.sub(
            rf"(?is)\bRPAD\s*\(\s*{arg}\s*,\s*{arg}\s*,\s*{arg}\s*\)",
            r"LEFT(\1 + REPLICATE(\3, \2), \2)",
            sql,
        )
        sql = re.sub(
            rf"(?is)\bLPAD\s*\(\s*{arg}\s*,\s*{arg}\s*,\s*{arg}\s*\)",
            r"RIGHT(REPLICATE(\3, \2) + \1, \2)",
            sql,
        )
        sql = re.sub(
            rf"(?is)\bRPAD\s*\(\s*{arg}\s*,\s*{arg}\s*\)",
            r"LEFT(\1 + REPLICATE(' ', \2), \2)",
            sql,
        )
        sql = re.sub(
            rf"(?is)\bLPAD\s*\(\s*{arg}\s*,\s*{arg}\s*\)",
            r"RIGHT(REPLICATE(' ', \2) + \1, \2)",
            sql,
        )
        # TO_CHAR(x, <int>) — a numeric CONVERT style in Oracle spelling
        # (client code ported FROM T-SQL): restore the CONVERT form.
        sql = re.sub(
            rf"(?is)\bTO_CHAR\s*\(\s*{arg}\s*,\s*(\d+)\s*\)",
            r"CONVERT(VARCHAR(4000), \1, \2)",
            sql,
        )
        # One-argument TO_CHAR/TO_DATE: plain conversions. The formatted
        # two-argument forms stay visible (format models differ per engine).
        sql = re.sub(
            rf"(?is)\bTO_CHAR\s*\(\s*{arg}\s*\)",
            r"CONVERT(VARCHAR(4000), \1)",
            sql,
        )
        sql = re.sub(
            rf"(?is)\bTO_DATE\s*\(\s*{arg}\s*\)",
            r"CONVERT(DATETIME, \1)",
            sql,
        )

        # Exception context: T-SQL reads it from the ERROR_* functions.
        # String-safe: a literal like 'SQLSTATE: ' must never be rewritten.
        def _diagnostics(seg: str) -> str:
            if self._source == "postgresql":
                # plpgsql's FOUND flag -> T-SQL's row-count predicate.
                seg = re.sub(r"(?i)\bFOUND\b", "(@@ROWCOUNT > 0)", seg)
            seg = re.sub(r"(?i)\bSQLERRM\b", "ERROR_MESSAGE()", seg)
            # CAST keeps the ubiquitous ``SQLCODE || ' ' || SQLERRM`` concat
            # working (INT + varchar raises 245 at runtime); a numeric
            # context converts the string back implicitly.
            seg = re.sub(
                r"(?i)\bSQLCODE\b", "CAST(ERROR_NUMBER() AS NVARCHAR(20))", seg
            )
            return re.sub(
                r"(?i)\bSQLSTATE\b",
                "CAST(ERROR_STATE() AS NVARCHAR(5))",
                seg,
            )

        before = sql
        sql = self._map_outside_strings(sql, _diagnostics)
        if "ERROR_STATE()" in sql and "ERROR_STATE()" not in before:
            self._warnings.append(
                "SQLSTATE (5-char class code) mapped to T-SQL ERROR_STATE() "
                "(an integer state) — different value domain"
            )
        sql = self._SYS_CONTEXT_RE.sub(
            lambda m: self._SYS_CONTEXT_MAP.get(m.group(1).upper(), m.group(0)),
            sql,
        )
        # DBMS_LOB.SUBSTR(lob, amount, offset) -> SUBSTRING(lob, offset, amount)
        sql = self._DBMS_LOB_SUBSTR3_RE.sub(r"SUBSTRING(\1, \3, \2)", sql)
        sql = self._DBMS_LOB_SUBSTR2_RE.sub(r"SUBSTRING(\1, 1, \2)", sql)
        sql = re.sub(
            r"(?is)\bUTL_RAW\s*\.\s*CAST_TO_VARCHAR2\s*\(",
            "CONVERT(VARCHAR(MAX), ",
            sql,
        )
        sql = re.sub(r"(?is)\bDBMS_LOB\s*\.\s*GETLENGTH\s*\(", "DATALENGTH(", sql)
        # CHR(n) -> CHAR(n)
        sql = re.sub(r"(?i)\bCHR\s*\(", "CHAR(", sql)
        # TRUNC(a, b) -> ROUND(a, b, 1) (truncate toward zero); TRUNC(x) is
        # the Oracle strip-the-time idiom on dates -> CAST(x AS DATE) when
        # the argument looks like a date (a known date variable or a
        # fecha/date-named expression), numeric truncation otherwise.
        sql = re.sub(
            r"(?is)\bTRUNC\s*\(\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)",
            r"ROUND(\1, \2, 1)",
            sql,
        )

        def trunc1(m: re.Match[str]) -> str:
            arg = m.group(1).strip()
            bare = arg.lstrip("@")
            if arg in self._date_vars or re.search(r"(?i)\b(?:fecha|date|fec)", bare):
                return f"CAST({arg} AS DATE)"
            return f"ROUND({arg}, 0, 1)"

        sql = re.sub(r"(?is)\bTRUNC\s*\(\s*([^(),]+?)\s*\)", trunc1, sql)
        sql = self._rownum_to_top(sql)
        return sql

    _ROWNUM_TAIL_RE = re.compile(
        r"(?is)\s+(?:WHERE|AND)\s+ROWNUM\s*(=|<=|<)\s*(\d+)\s*(\)?)\s*$"
    )

    def _rownum_to_top(self, sql: str) -> str:
        """Rewrite the Oracle top-n idiom for T-SQL.

        ``SELECT ... FROM (SELECT ... ORDER BY ...) WHERE ROWNUM = 1`` puts
        ``TOP (1)`` on the *inner* select (whose ORDER BY is otherwise
        illegal in a derived table — error 1033); the flat
        ``... WHERE ROWNUM <= n`` form gets TOP on its own head."""
        if "ROWNUM" not in sql.upper():
            return sql
        m = self._ROWNUM_TAIL_RE.search(sql)
        if not m:
            return sql
        op, n_txt, closing = m.group(1), m.group(2), m.group(3)
        n = int(n_txt) - 1 if op == "<" else int(n_txt)
        if n < 1:
            return sql
        head = sql[: m.start()] + closing
        derived = re.search(r"(?is)\bFROM\s*\(\s*SELECT\b(?!\s+TOP\b)", head)
        if derived:
            # The ROWNUM filtered an (ordered) derived table: the limit
            # belongs inside, with the ORDER BY (a derived table may not
            # carry ORDER BY without TOP — error 1033). Oracle needs no
            # derived-table alias but T-SQL does — add one if missing.
            insert_at = derived.end()
            out = f"{head[:insert_at]} TOP ({n}){head[insert_at:]}"
            if out.rstrip().endswith(")"):
                out = out.rstrip() + " AS uq_top"
            return out
        sel = re.match(r"(?is)^(\s*SELECT\b)(?!\s+TOP\b)", head)
        if sel:
            return f"{head[:sel.end(1)]} TOP ({n}){head[sel.end(1):]}"
        if n == 1:
            # A FROM/WHERE fragment (a SELECT INTO's tail): with a 1-row
            # limit and no ordering, dropping the predicate matches the
            # assignment semantics (both pick an arbitrary single row).
            return head
        return sql

    def _fix_target_dml(self, sql: str) -> str:
        # Embedded DML shares the raw-expression leaks (a DBMS_LOB.SUBSTR in
        # a WHERE clause, SQLERRM in a SELECT list).
        return self._map_oracle_builtins(sql)

    def _fix_ir_dml(self, sql: str) -> str:
        return self._map_oracle_builtins(sql)

    def _fix_select_into_rest(self, sql: str) -> str:
        return self._map_oracle_builtins(sql)

    def _fix_raw_sql_target(self, sql: str) -> str:
        sql = self._map_oracle_builtins(sql)
        # PL/SQL string concatenation: T-SQL spells it ``+``.
        if "||" in sql:
            sql = self._pipes_to_plus(sql)
        # Scalar-UDF calls must be schema-qualified on T-SQL (error 195).
        # Runs after the builtin mapping so anything still bare and unknown
        # is a user function (a client-DB-resident one included).
        sql = self._qualify_tsql_udfs(sql)
        # PL/SQL event predicates inside a trigger body (audit D6): T-SQL
        # tests the pseudo-tables instead.
        if self._in_trigger:
            for pattern, repl_text in self._EVENT_PREDICATES:
                sql = pattern.sub(repl_text, sql)
        # T-SQL has no date ``-`` operator (error 8117 / 257). ``d2 - d1`` over
        # two DATE/DATETIME vars/params becomes ``DATEDIFF(DAY, d1, d2)`` (days
        # from d1 to d2), matching the source's date-difference semantics.
        if not self._date_vars:
            return sql

        def repl(m: re.Match[str]) -> str:
            a, b = m.group(1), m.group(2)
            if a in self._date_vars and b in self._date_vars:
                return f"DATEDIFF(DAY, {b}, {a})"
            return m.group(0)

        return self._SUBTRACT_RE.sub(repl, sql)

    # ---------------------------------------------------------------
    # Row-level trigger -> T-SQL statement-level (inserted/deleted) trigger
    # ---------------------------------------------------------------

    def _rowlevel_trigger_override(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        """A row-level source trigger (``FOR EACH ROW`` with ``NEW``/``OLD``) has
        no T-SQL equivalent — T-SQL triggers are statement-level over the
        ``inserted``/``deleted`` pseudo-tables. Rewrite each body statement to its
        set-based form and drop the BEFORE/AFTER distinction (both become AFTER;
        a ``SET NEW.col`` becomes an UPDATE of the affected rows)."""
        if node.for_each != "ROW" or self._source == "tsql" or node.execute_function:
            return None
        return self._tsql_statement_trigger(node, node.body)

    def _lower_compound_for_statement_target(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        # An Oracle COMPOUND trigger's AFTER STATEMENT re-aggregation (captured
        # as ``compound_row_body`` keyed on ``:NEW.<fk>``) is the same set-based
        # UPDATE a T-SQL statement-level trigger runs over ``inserted``.
        if not node.compound_row_body:
            return None
        return self._tsql_statement_trigger(node, node.compound_row_body)

    def _inline_delegating_trigger(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        # A PostgreSQL trigger delegates to a ``RETURNS TRIGGER`` function; T-SQL
        # has no trigger functions, so inline the harvested function body. Its
        # statement-level ``inserted``/``deleted`` UPDATEs map straight to T-SQL;
        # the ``pg_trigger_depth()`` guard (T-SQL: RECURSIVE_TRIGGERS OFF) and
        # ``RETURN`` are dropped.
        bodies = PG_TRIGGER_FN_BODIES.get() or {}
        src = bodies.get((node.execute_function or "").lower())
        if src is None:
            return None
        from unique.core.procedural.parser import ProceduralParser

        fn_node = ProceduralParser(self._source).parse(src).node
        body = tuple(getattr(fn_node, "body", ()) or ())
        kept = tuple(b for b in body if not self._is_pg_trigger_noise(b))
        # The inline path bypasses the routine-level degrade scan: an
        # unconvertible body (dynamic FOR/EXECUTE, record vars …) must
        # degrade the TRIGGER whole, not inline garbage.
        if self._has_dynamic_for(kept):
            reason = (
                "trigger function body iterates dynamic EXECUTE (engine "
                "introspection); no tsql equivalent — trigger preserved "
                "as a comment"
            )
            self._warnings.append(reason)
            from unique.core.procedural.emitter import ProceduralEmitter

            original = ProceduralEmitter("postgresql").emit(node)
            return RawSQL(sql=original, reason=reason)
        kept = self._rename_transition_aliases(kept, node.referencing)
        kept = self._substitute_tg_constants(kept, node)
        if self._contains_raw_text(kept, "TG_ARGV"):
            # An argument reference the substitution could not resolve
            # (non-literal index, out of range) — degrade whole, never
            # inline a bare TG_ARGV.
            reason = (
                "trigger function references TG_ARGV with an unresolvable "
                "index; trigger preserved as a comment"
            )
            self._warnings.append(reason)
            from unique.core.procedural.emitter import ProceduralEmitter

            original = ProceduralEmitter("postgresql").emit(node)
            return RawSQL(sql=original, reason=reason)
        return self._tsql_statement_trigger(node, kept)

    def _contains_raw_text(self, body: tuple[ASTNode, ...], needle: str) -> bool:
        found = False

        def scan(segment: str) -> str:
            nonlocal found
            if needle.upper() in segment.upper():
                found = True
            return segment

        for b in body:
            self._rewrite_raw_text_fields(b, scan)
        return found

    def _substitute_tg_constants(
        self, body: tuple[ASTNode, ...], node: CreateTriggerStatement
    ) -> tuple[ASTNode, ...]:
        """plpgsql's TG_* context variables are compile-time constants
        once the function is inlined into a NAMED trigger."""
        event = node.events[0] if node.events else "INSERT"
        consts = {
            "TG_NAME": f"'{node.name}'",
            "TG_TABLE_NAME": f"'{node.table}'",
            "TG_OP": f"'{event.upper()}'",
            "TG_WHEN": f"'{node.timing.upper()}'",
            "TG_LEVEL": f"'{node.for_each.upper()}'",
            "TG_NARGS": str(len(node.execute_args)),
        }
        args = node.execute_args

        def sub(segment: str) -> str:
            def argv(m: re.Match[str]) -> str:
                idx = int(m.group(1))
                return args[idx] if idx < len(args) else m.group(0)

            segment = re.sub(r"(?i)\bTG_ARGV\s*\[\s*(\d+)\s*\]", argv, segment)
            for k, v in consts.items():
                segment = re.sub(rf"(?i)\b{k}\b", v, segment)
            return segment

        return tuple(self._rewrite_raw_text_fields(b, sub) for b in body)

    _REF_NEW_RE = re.compile(r"(?i)\bNEW\s+TABLE\s+AS\s+(\w+)")
    _REF_OLD_RE = re.compile(r"(?i)\bOLD\s+TABLE\s+AS\s+(\w+)")

    def _rename_transition_aliases(
        self, body: tuple[ASTNode, ...], referencing: str
    ) -> tuple[ASTNode, ...]:
        """PG transition-table aliases map to T-SQL's fixed
        inserted/deleted pseudo-tables (outside string literals)."""
        if not referencing:
            return body
        renames: dict[str, str] = {}
        m = self._REF_NEW_RE.search(referencing)
        if m:
            renames[m.group(1)] = "inserted"
        m = self._REF_OLD_RE.search(referencing)
        if m:
            renames[m.group(1)] = "deleted"
        if not renames:
            return body

        def rn(segment: str) -> str:
            for old_name, new_name in renames.items():
                segment = re.sub(rf"(?i)\b{re.escape(old_name)}\b", new_name, segment)
            return segment

        return tuple(self._rewrite_raw_text_fields(b, rn) for b in body)

    def _rewrite_raw_text_fields(
        self, node: ASTNode, fn: Callable[[str], str]
    ) -> ASTNode:
        """Apply *fn* (outside string literals) to every raw-SQL text
        field reachable from *node*."""
        import dataclasses as _dc

        changes: dict[str, object] = {}
        for f in _dc.fields(node):
            val = getattr(node, f.name)
            if f.name == "sql" and isinstance(val, str) and val:
                new_text = self._map_outside_strings(val, fn)
                if new_text != val:
                    changes[f.name] = new_text
            elif isinstance(val, ASTNode):
                new_node = self._rewrite_raw_text_fields(val, fn)
                if new_node is not val:
                    changes[f.name] = new_node
            elif isinstance(val, tuple) and val and isinstance(val[0], ASTNode):
                new_items = tuple(self._rewrite_raw_text_fields(v, fn) for v in val)
                if any(a is not b for a, b in zip(new_items, val, strict=True)):
                    changes[f.name] = new_items
        if not changes:
            return node
        return _dc.replace(node, **changes)  # type: ignore[arg-type]

    def _trigger_function_is_inlined(self, name: str) -> bool:
        bodies = PG_TRIGGER_FN_BODIES.get() or {}
        return name.strip('[]"`').split(".")[-1].lower() in bodies

    @staticmethod
    def _is_pg_trigger_noise(node: ASTNode) -> bool:
        """A ``RETURN`` (T-SQL triggers do not return) or the ``pg_trigger_depth``
        recursion guard, both dropped when inlining a PG trigger function."""
        if isinstance(node, ReturnStatement):
            return True
        if isinstance(node, IfStatement):
            cond = getattr(node.condition, "sql", "") or ""
            return "pg_trigger_depth" in cond.lower()
        return False

    def _tsql_statement_trigger(
        self, node: CreateTriggerStatement, body_nodes: tuple[ASTNode, ...]
    ) -> ASTNode | None:
        prev = self._in_trigger
        self._in_trigger = True
        try:
            stmts = [self._rowlevel_body_to_tsql(b, node.table) for b in body_nodes]
        finally:
            self._in_trigger = prev
        kept = [s for s in stmts if s is not None]
        if not kept:
            return None
        if node.update_of:
            # T-SQL has no UPDATE OF event list; the same firing condition is
            # an IF UPDATE(c1) OR UPDATE(c2) ... wrapper around the body.
            cond = " OR ".join(f"UPDATE({c})" for c in node.update_of)
            kept = [
                IfStatement(
                    condition=RawSQL(sql=cond, reason="UPDATE OF columns"),
                    then_body=tuple(kept),
                )
            ]
        return CreateTriggerStatement(
            name=self._translate_ident_quoting(node.name) or node.name,
            table=self._translate_ident_quoting(node.table) or node.table,
            timing="AFTER",
            events=node.events,
            for_each="STATEMENT",
            body=tuple(kept),
            or_replace=node.or_replace,
            schema=self._target_schema(node.schema),
        )

    _NEW_ASSIGN_RE = re.compile(r"(?i)^\s*(NEW|OLD)\s*\.\s*(\w+)\s*$")

    #: PL/SQL trigger event predicates -> the T-SQL inserted/deleted idiom.
    _EVENT_PREDICATES = (
        (
            re.compile(r"(?i)\bUPDATING\s*\(\s*'(\w+)'\s*\)"),
            r"UPDATE(\1)",
        ),
        (
            re.compile(r"(?i)\bINSERTING\b"),
            "(EXISTS (SELECT 1 FROM inserted) "
            "AND NOT EXISTS (SELECT 1 FROM deleted))",
        ),
        (
            re.compile(r"(?i)\bDELETING\b"),
            "(EXISTS (SELECT 1 FROM deleted) "
            "AND NOT EXISTS (SELECT 1 FROM inserted))",
        ),
        (
            re.compile(r"(?i)\bUPDATING\b(?!\s*\()"),
            "(EXISTS (SELECT 1 FROM inserted) " "AND EXISTS (SELECT 1 FROM deleted))",
        ),
    )

    def _rowlevel_body_to_tsql(self, node: ASTNode, table: str) -> ASTNode | None:
        bare_table = table.strip('[]"`').split(".")[-1]
        # A per-row IF folds into the converted statements: a NEW/OLD-based
        # condition scopes the inserted-rows subquery; an event predicate (or
        # any other condition) wraps them in a statement-level IF.
        if isinstance(node, IfStatement) and not node.else_body:
            then_conv: list[ASTNode] = []
            for child in node.then_body:
                conv = self._rowlevel_body_to_tsql(child, table)
                if conv is not None:
                    then_conv.append(conv)
            cond_text = (
                node.condition.sql if isinstance(node.condition, RawSQL) else None
            )
            if (
                cond_text
                and re.search(r"(?i):?\s*\b(?:NEW|OLD)\s*\.", cond_text)
                and then_conv
                and all(
                    isinstance(s, EmbeddedDML) and "FROM inserted)" in s.sql
                    for s in then_conv
                )
            ):
                clean = re.sub(r"(?i):\s*(?=(?:NEW|OLD)\s*\.)", "", cond_text)
                clean = re.sub(r"(?i)\b(?:NEW|OLD)\s*\.\s*", "", clean).strip()
                clean = _strip_wrapping_parens(clean).strip() or "1=1"
                clean = self._condition_via_ir(clean)
                folded = tuple(
                    EmbeddedDML(
                        sql=s.sql.replace(
                            "FROM inserted)", f"FROM inserted WHERE {clean})"
                        ),
                        dialect=s.dialect,
                    )
                    for s in then_conv
                    if isinstance(s, EmbeddedDML)
                )
                if len(folded) == 1:
                    return folded[0]
                return StatementList(statements=folded)
            new_cond = self._transform_node(node.condition)
            return IfStatement(
                condition=new_cond,
                then_body=self._ensure_non_empty_body(tuple(then_conv)),
                else_body=(),
            )
        # Pattern (a): ``SET NEW.col = expr`` (a per-row derived/stamped column).
        # T-SQL has no BEFORE trigger and cannot write ``inserted``, so update the
        # affected rows: ``UPDATE t SET col = <expr> WHERE <pk> IN (SELECT <pk>
        # FROM inserted)``. The expr's own-row NEW./OLD. references become the
        # table's bare columns.
        target = None
        value = None
        if isinstance(node, AssignmentStatement):
            target, value = node.target, node.value
        elif isinstance(node, SetVariableStatement):
            target, value = node.name, node.value
        if target is not None and value is not None:
            m = self._NEW_ASSIGN_RE.match(target)
            if m:
                col = m.group(2)
                expr = value.sql if isinstance(value, RawSQL) else self._lit(value)
                # An own-row NEW./OLD. (Oracle ``:NEW.``) reference becomes the
                # table's bare column. Drop the Oracle bind colon (only when it
                # precedes NEW/OLD) and the NEW./OLD. qualifier — anchored so a
                # preceding operator's whitespace is not swallowed.
                expr = re.sub(r"(?i):\s*(?=(?:NEW|OLD)\s*\.)", "", expr)
                expr = re.sub(r"(?i)\b(?:NEW|OLD)\s*\.\s*", "", expr)
                expr = self._qualify_tsql_udfs(self._expr._map_now_in_sql(expr))
                pk = self._tsql_pk(bare_table)
                sql = (
                    f"UPDATE {bare_table} SET {col} = {expr} "
                    f"WHERE {pk} IN (SELECT {pk} FROM inserted)"
                )
                return EmbeddedDML(sql=sql, dialect="tsql")
        # Pattern (b): embedded DML keyed on NEW.<fk> -> set-based over inserted.
        if isinstance(node, EmbeddedDML):
            transformed = self._transform_embedded_dml(node)
            sql = self._tsql_setbased_rewrite(transformed.sql, bare_table)
            return EmbeddedDML(sql=self._qualify_tsql_udfs(sql), dialect="tsql")
        # Anything else (IF, etc.): fall back to the normal transform.
        return self._transform_node(node)

    def _tsql_setbased_rewrite(self, sql: str, trigger_table: str) -> str:
        """Rewrite a row-level ``UPDATE <tgt> <alias> SET … WHERE <alias>.<key> =
        NEW.<fk>`` into a set-based T-SQL update scoped to ``inserted``."""
        from unique.core.sql_split import split_leading_trivia

        # Match on the code, re-attach the trivia: a leading comment must not
        # hide the UPDATE (audit doc 04, P2).
        trivia, sql = split_leading_trivia(sql)
        # The IR emitter spells an aliased single-table update as
        # ``UPDATE alias SET … FROM tgt alias`` (the only alias form T-SQL
        # accepts); normalize the trigger table's own updates back to the
        # classic shape this rewriter matches on. Greedy ``.*`` binds to the
        # LAST matching FROM, so a subquery's FROM inside SET is skipped.
        m2 = re.match(
            r"(?is)^\s*UPDATE\s+(\w+)\s+SET\b(.*)\bFROM\s+"
            r"([\w\[\]\"`.]+)(?:\s+AS)?\s+\1(\s+WHERE\b.*|\s*;?\s*)$",
            sql,
        )
        if m2:
            alias2, sets2, tgt2, tail2 = m2.groups()
            sql = f"UPDATE {tgt2} {alias2} SET{sets2.rstrip()}{tail2}"
        m = re.match(r"(?is)\s*UPDATE\s+([\w\[\]\"`.]+)(?:\s+AS)?\s+(\w+)\s+SET\b", sql)
        if not m:
            return trivia + sql
        tgt, alias = m.group(1), m.group(2)
        bare = tgt.strip('[]"`').split(".")[-1]
        # Drop the target alias (T-SQL rejects ``UPDATE t AS a``); refer to the
        # target by its table name so a correlated subquery still resolves.
        sql = re.sub(
            rf"(?is)^(\s*)UPDATE\s+{re.escape(tgt)}(?:\s+AS)?\s+{re.escape(alias)}"
            r"\s+SET\b",
            rf"\g<1>UPDATE {bare} SET",
            sql,
            count=1,
        )
        sql = re.sub(rf"(?i)\b{re.escape(alias)}\s*\.", f"{bare}.", sql)
        # The outer correlation ``<tgt>.<key> = NEW.<fk>`` selects the affected
        # parent rows -> ``<tgt>.<key> IN (SELECT <fk> FROM inserted)``; a NEW.<fk>
        # left in a subquery correlates to the target row (``<tgt>.<key>``).
        mp = re.search(
            rf"(?i)\b{re.escape(bare)}\.(\w+)\s*=\s*(?:NEW|OLD)\s*\.\s*(\w+)", sql
        )
        if mp:
            key, fk = mp.group(1), mp.group(2)
            sql = (
                sql[: mp.start()]
                + f"{bare}.{key} IN (SELECT {fk} FROM inserted)"
                + sql[mp.end() :]
            )
            sql = re.sub(
                rf"(?i)\b(?:NEW|OLD)\s*\.\s*{re.escape(fk)}\b", f"{bare}.{key}", sql
            )
        return trivia + sql

    def _condition_via_ir(self, cond: str) -> str:
        """Transpile a boolean predicate fragment through the shared IR so a
        source-dialect predicate builtin maps correctly in predicate position
        (MySQL ``ISNULL(x)`` → ``x IS NULL``, not the scalar CASE form). Falls
        back to the fragment unchanged when the IR declines it."""
        ir = self._ir_transpile_dml(f"SELECT 1 WHERE {cond}")
        if ir:
            m = re.search(r"(?is)\bWHERE\b(.*)$", ir)
            if m:
                return m.group(1).strip().rstrip(";").strip()
        return cond

    def _tsql_pk(self, table: str) -> str:
        registry = IDENTITY_COLUMNS.get() or {}
        return registry.get(table.lower(), "id")

    def _qualify_tsql_udfs(self, sql: str) -> str:
        """Qualify a bare scalar-UDF call ``fn(…)`` as ``dbo.fn(…)`` (T-SQL
        rejects an unqualified scalar UDF as an unknown built-in, error 195,
        even when the function exists). A name in the harvested
        USER_FUNCTIONS registry is qualified outright; otherwise the shared
        structural decision applies — neither a T-SQL builtin (callable
        bare) nor a known foreign builtin (an unmapped one stays a visible
        gap) means user function. String/comment-aware; object-name
        positions (``INSERT INTO t (``) are not calls."""
        funcs = USER_FUNCTIONS.get() or frozenset()

        def decide(name: str, prev_word: str | None) -> str | None:
            if prev_word and prev_word.upper() in TSQL_OBJECT_CONTEXT_WORDS:
                return None
            if name.lower() in funcs or tsql_call_needs_schema(name):
                return "dbo."
            return None

        return qualify_function_calls(sql, decide)

    def _lit(self, value: ASTNode) -> str:
        if isinstance(value, Literal):
            if value.value is None:
                return "NULL"
            if value.dtype in ("string", "str"):
                return "'" + str(value.value).replace("'", "''") + "'"
            return str(value.value)
        return self._emit_fallback(value)

    def _emit_fallback(self, value: ASTNode) -> str:
        return value.sql if isinstance(value, RawSQL) else ""

    def _alter_becomes_create(self) -> bool:
        # T-SQL keeps ALTER PROCEDURE as-is.
        return False

    def _rewrites_trigger_pseudotables(self) -> bool:
        # T-SQL keeps inserted/deleted pseudo-tables as-is.
        return False

    # No blanket FOR-loop warning (audit N5): a guard FOR-loop converts to a
    # clean IF and a resolvable cursor loop expands completely — a warning on
    # a successful conversion is a bug. The degraded paths carry their own
    # ``-- UNIQUE:`` markers, which the carrier reconciliation turns into
    # warnings exactly when they fire.

    def _transform_loop(self, node: LoopStatement) -> ASTNode:
        # T-SQL has no bare LOOP; express it as WHILE 1=1.
        return WhileStatement(
            condition=RawSQL(sql="1=1", reason="infinite loop"),
            body=self._ensure_non_empty_body(self._transform_body(node.body)),
        )

    def _transform_null(self, node: NullStatement) -> ASTNode:
        return RawSQL(sql="-- NULL statement (no-op)", reason="no T-SQL equivalent")

    def _noop_statement(self) -> ASTNode:
        # The empty-body filler must be EXECUTABLE on T-SQL (a comment-only
        # BEGIN END is still error 102); SET NOCOUNT ON is the canonical
        # side-effect-free statement.
        return RawSQL(sql="SET NOCOUNT ON;", reason="no-op filler")

    def _has_update_predicate(self) -> bool:
        # T-SQL keeps UPDATE(col) as-is.
        return False

    def _uses_set_statement(self) -> bool:
        return True

    def _assignment_becomes_set(self) -> bool:
        return True

    def _folds_exception_scope(self) -> bool:
        return True

    def _noop_sql(self) -> str:
        # T-SQL has no NULL statement; SET NOCOUNT ON is the canonical
        # side-effect-free filler for a carrier's block position.
        return "SET NOCOUNT ON;"

    def _transform_exception_block(self, node: ExceptionBlock) -> ASTNode:
        # Reached only when the EXCEPTION section had no preceding siblings
        # to protect (see _fold_exception_scope); flatten the handlers into
        # the CATCH block — the emitter backfills the empty TRY.
        body: list[ASTNode] = []
        for handler in node.handlers:
            body.extend(handler.body)
        return TryCatchBlock(
            try_body=(),
            catch_body=self._transform_body(tuple(body)),
        )


register_transformer(TSqlTransformer.target_name, TSqlTransformer)
