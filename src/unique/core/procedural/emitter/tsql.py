# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — tsql target."""

from __future__ import annotations

import dataclasses
import re

from unique.core.ast_nodes import (
    AnonymousBlock,
    ASTNode,
    CallStatement,
    ContinueStatement,
    CursorDeclaration,
    CursorOperation,
    DataType,
    ExitStatement,
    IfStatement,
    NullStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    SelectIntoStatement,
    TryCatchBlock,
    WaitForStatement,
    WhileStatement,
)
from unique.core.procedural.emitter.base import (
    ProceduralEmitter,
    _select_list_columns,
    _strip_outer_parens,
    register_emitter,
)


class TSqlEmitter(ProceduralEmitter):
    """T-SQL (SQL Server) procedural emitter."""

    dialect_name = "tsql"

    def __init__(self, dialect: str) -> None:
        super().__init__(dialect)
        # Names RAISERROR message variables uniquely across the script.
        self._raise_msg_n = 0
        # Cursor *variables* (``DECLARE @c CURSOR;`` — no query): unlike
        # classic cursors these keep their '@' on OPEN/FETCH/CLOSE.
        self._cursor_variables: set[str] = set()
        # Loop variables already DECLAREd in the current unit (T-SQL DECLARE
        # is batch-scoped; a re-declaration is error 134). Reset per emit().
        self._loop_vars_emitted: set[str] = set()

    def emit(self, node: ASTNode) -> str:
        self._loop_vars_emitted = set()
        return super().emit(node)

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        dt = self._tsql_scaled_numeric(self._emit_data_type(p.data_type))
        default_str = f" = {self._emit_node(p.default)}" if p.default else ""
        direction_str = " OUTPUT" if p.direction in ("OUT", "INOUT") else ""
        name = p.name if p.name.startswith("@") else f"@{p.name}"
        return f"{name} {dt}{default_str}{direction_str}"

    def _returns_clause(self, ret_type: str) -> str:
        return f"\nRETURNS {self._tsql_scaled_numeric(ret_type)}"

    _BARE_NUMERIC_RE = re.compile(r"(?i)^\s*(DECIMAL|NUMERIC|DEC)\s*$")

    def _tsql_scaled_numeric(self, type_str: str) -> str:
        """A bare T-SQL ``DECIMAL``/``NUMERIC`` is ``(18, 0)`` — it rounds to an
        integer. A routine parameter/return from an unconstrained source
        ``NUMBER`` must keep a fractional scale, or e.g. a tax of 5.55 comes back
        as 6. Give it a wide exact scale."""
        if self._BARE_NUMERIC_RE.match(type_str):
            return f"{type_str.strip()}(38, 10)"
        return type_str

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        """A T-SQL scalar function forbids ``SET NOCOUNT`` (a side-effecting SET
        option, error 443), so — unlike a procedure — its body carries no such
        preamble: ``AS BEGIN [DECLARE …] … RETURN … END``."""
        lines = [f"{header}\nAS\nBEGIN"]
        self._indent_level = 1
        for decl in declarations:
            lines.append(f"{self._indent()}{self._emit_node(decl)}")
        if declarations:
            lines.append("")
        for stmt in body_stmts:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0
        lines.append("END")
        return "\n".join(lines)

    _ANSI_DATE_LITERAL_RE = re.compile(r"(?i)\b(?:DATE|TIMESTAMP)\s+(?=')")

    def _emit_anonymous_block(self, node: AnonymousBlock) -> str:
        """A T-SQL batch *is* the anonymous block: emit declarations and
        statements flattened, with no PL/SQL ``DECLARE``-header/``BEGIN``/
        ``END`` shell (a bare ``DECLARE`` line and an unterminated block are
        syntax errors — audit 2026-07-08, D2)."""
        if node.degraded:
            return self._emit_degraded_anonymous_block(node)
        return "\n".join(
            text for s in node.statements if (text := self._emit_node(s)).strip()
        )

    #: EXEC argument values that are expressions must be hoisted: T-SQL
    #: accepts only literals/variables there (error 102 at the call's
    #: parens otherwise). GETDATE()/SYSDATETIME() dominate the corpus.
    _EXEC_NOW_ARG_RE = re.compile(
        r"(?i)\b(GETDATE|SYSDATETIME|SYSUTCDATETIME)\s*\(\s*\)"
    )

    def _emit_call(self, node: CallStatement) -> str:
        # An ANSI ``DATE '…'`` / ``TIMESTAMP '…'`` literal argument (from an
        # Oracle/PG source) has no T-SQL form; pass the bare string, which T-SQL
        # implicitly converts to the parameter's date type.
        args = self._ANSI_DATE_LITERAL_RE.sub("", node.args) if node.args else node.args
        # PL/SQL / PostgreSQL named association ``name => value`` is spelled
        # ``@name = value`` in a T-SQL EXEC.
        if args and "=>" in args:
            args = re.sub(r"(\w+)\s*=>\s*", r"@\1 = ", args)
        prelude = ""
        now_call = self._EXEC_NOW_ARG_RE.search(args) if args else None
        if args and now_call:
            # EXEC arguments take no expressions — hoist the now() call.
            self._raise_msg_n += 1
            var = f"@uq_now{self._raise_msg_n}"
            args = self._EXEC_NOW_ARG_RE.sub(var, args)
            prelude = f"DECLARE {var} DATETIME = {now_call.group(0)};\n"
        name = self._qualified_name(node.schema, node.name)
        call = f"EXEC {name} {args};" if args else f"EXEC {name};"
        return prelude + call

    def _supports_table_valued_function(self) -> bool:
        return True

    def _declare_default_op(self) -> str:
        return "="

    def _declare_prefix(self) -> str:
        return "DECLARE "

    def _emit_data_type(self, dt: DataType) -> str:
        out = super()._emit_data_type(dt)
        # A bare (N)VARCHAR defaults to length 1 in declarations and 30 in
        # casts — silent truncation. Oracle's unsized VARCHAR2 parameters are
        # unbounded; 4000 is the widest non-MAX form.
        if not dt.params and out.upper() in ("NVARCHAR", "VARCHAR"):
            return f"{out}(4000)"
        # A size beyond T-SQL's row limits (NVARCHAR > 4000, VARCHAR > 8000
        # — Oracle's extended VARCHAR2(20000)) only exists as MAX.
        if dt.params and len(dt.params) == 1:
            name = re.match(r"(?i)^(NVARCHAR|VARCHAR|VARBINARY)\b", out)
            limit = {"NVARCHAR": 4000, "VARCHAR": 8000, "VARBINARY": 8000}
            if (
                name
                and isinstance(dt.params[0], int)
                and dt.params[0] > limit[name.group(1).upper()]
            ):
                return f"{name.group(1)}(MAX)"
        return out

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        # Classic T-SQL cursors are not variables: no '@' on the name (the
        # generic variable rename adds one). Record the query so a FOR loop
        # over this cursor can derive its FETCH INTO variable list.
        if node.query is None and node.name.startswith("@"):
            # A cursor variable: the classic un-@ form would be invalid
            # without a FOR query (and the SET binding references @name).
            self._cursor_variables.add(node.name.lstrip("@").lower())
            return f"DECLARE {node.name} CURSOR;"
        name = node.name.lstrip("@")
        query_str = (
            self._emit_node(node.query).rstrip().rstrip(";") if node.query else ""
        )
        if query_str:
            self._cursor_queries[name.lower()] = query_str
        body = f" LOCAL FAST_FORWARD FOR {query_str}" if query_str else ""
        return f"DECLARE {name} CURSOR{body};"

    def _emit_print(self, node: PrintStatement) -> str:
        return f"PRINT {self._emit_node(node.expression)};"

    def _emit_while(self, node: WhileStatement) -> str:
        cond = self._emit_node(node.condition)
        lines = [f"WHILE {cond}", "BEGIN"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.body))
        self._indent_level -= 1
        lines.append("END")
        return "\n".join(lines)

    def _emit_loop_body(self, body_lines: list[str]) -> str:
        # Unconditional loop → WHILE 1 = 1 ... (exit via BREAK).
        return "\n".join(["WHILE 1 = 1", "BEGIN", *body_lines, "END"])

    def _block_end(self) -> str:
        return "END"

    def _assignment_form(self, target: str, val: str) -> str:
        return f"SET {target} = {val};"

    def _emit_select_into(self, node: SelectIntoStatement) -> str:
        select_list = ""
        if node.columns:
            first = node.columns[0]
            select_list = first.sql if isinstance(first, RawSQL) else ""
        rest = node.rest_sql.rstrip(";").strip()
        # Top-level commas only: a plain split cuts inside a function call
        # (``MAX(COALESCE(a, 0)) + 1`` — audit 2026-07-08, D8).
        from unique.core.sql_split import split_top_level_commas

        cols = split_top_level_commas(select_list)
        targets = list(node.into_vars)
        pairs = []
        for i, var in enumerate(targets):
            col = cols[i] if i < len(cols) else (cols[-1] if cols else "")
            pairs.append(f"{var} = {col}")
        assignments = ", ".join(pairs)
        prefix = f"{node.with_sql}\n" if node.with_sql else ""
        return f"{prefix}SELECT {assignments} {rest};"

    def _emit_guard_if(self, cond: str, body_lines: list[str]) -> str | None:
        # T-SQL's IF takes a SQL condition (incl. EXISTS), so the guard is a
        # plain IF … BEGIN … END — no cursor, no FROM DUAL.
        return "\n".join([f"IF ({cond})", "BEGIN", *body_lines, "END"])

    def _emit_numeric_for_loop(
        self, variable: str, start: str, end: str, reverse: bool, body_lines: list[str]
    ) -> str:
        # T-SQL has no counting FOR; expand to DECLARE @v + WHILE. Bare
        # loop-variable references in the body are rewritten to @v (they were
        # never a declared variable, so the transformer's rename missed them).
        var = f"@{variable.lstrip('@')}"
        rewritten = [
            re.sub(rf"(?<!@)\b{re.escape(variable.lstrip('@'))}\b", var, line)
            for line in body_lines
        ]
        init, cond, step = (
            (end, f"{var} >= {start}", f"SET {var} = {var} - 1;")
            if reverse
            else (start, f"{var} <= {end}", f"SET {var} = {var} + 1;")
        )
        lines = [
            f"DECLARE {var} INT = {init};",
            f"WHILE {cond}",
            "BEGIN",
            *rewritten,
            f"{self._indent()}{step}",
            "END;",
        ]
        return "\n".join(lines)

    def _emit_for_loop_body(
        self, variable: str, cursor_str: str, body_lines: list[str]
    ) -> str:
        # T-SQL has no implicit cursor FOR loop: expand to an explicit cursor.
        # When the select list is resolvable (a named cursor recorded at its
        # declaration, or an inline query), the expansion is complete and
        # valid: one @<var>_<col> per column, positional FETCH INTO, and the
        # body's rec.col references rewritten. Otherwise the documented
        # scaffold (developer completes the FETCH) remains.
        named = re.fullmatch(r"@?[A-Za-z_]\w*", cursor_str.strip())
        if named:
            cur = cursor_str.strip().lstrip("@")
            select_text = self._cursor_queries.get(cur.lower())
            declares_cursor = False
        else:
            cur = f"{variable}_cur"
            # The inline ``FOR r IN (SELECT ...)`` form arrives with its
            # parens; T-SQL's DECLARE CURSOR FOR takes a bare select.
            select_text = _strip_outer_parens(cursor_str)
            declares_cursor = True

        cols = _select_list_columns(select_text) if select_text else None
        if cols:
            fields = {
                m.group(1).lower()
                for line in body_lines
                for m in re.finditer(rf"(?i)\b{re.escape(variable)}\s*\.\s*(\w+)", line)
            }
            if not fields.issubset(set(cols)):
                cols = None  # a referenced field the list doesn't expose

        if not cols:
            lines = [
                "-- UNIQUE: Oracle implicit cursor FOR-loop expanded to an "
                "explicit T-SQL cursor.",
                "-- Declare one @var per selected column and complete the "
                "FETCH INTO list.",
                f"DECLARE {cur} CURSOR LOCAL FAST_FORWARD FOR",
                f"{cursor_str};",
                f"OPEN {cur};",
                f"FETCH NEXT FROM {cur} INTO /* @col1, @col2, ... */;",
                "WHILE @@FETCH_STATUS = 0",
                "BEGIN",
                *body_lines,
                f"{self._indent()}FETCH NEXT FROM {cur} "
                "INTO /* @col1, @col2, ... */;",
                "END;",
                f"CLOSE {cur};",
                f"DEALLOCATE {cur};",
            ]
            return "\n".join(lines)

        fetch_vars = ", ".join(f"@{variable}_{c}" for c in cols)
        # ``@?``: the loop variable may also be DECLAREd (``<cur>%ROWTYPE``),
        # in which case the var rename already @-prefixed the record ref —
        # consume that @ or the rewrite would emit ``@@var_col``.
        rewritten = [
            re.sub(
                rf"(?i)@?\b{re.escape(variable)}\s*\.\s*(\w+)",
                lambda m: f"@{variable}_{str(m.group(1)).lower()}",
                line,
            )
            for line in body_lines
        ]
        # T-SQL DECLARE is batch-scoped: several loops reusing one record
        # name must declare each @var_col ONCE (error 134 otherwise).
        new_vars = [
            c for c in cols if f"@{variable}_{c}".lower() not in self._loop_vars_emitted
        ]
        self._loop_vars_emitted.update(f"@{variable}_{c}".lower() for c in cols)
        lines = [
            "-- UNIQUE: cursor FOR-loop expanded; loop variables are "
            "NVARCHAR(4000) (exact column types need --db-url metadata).",
        ]
        if new_vars:
            decls = ", ".join(f"@{variable}_{c} NVARCHAR(4000)" for c in new_vars)
            lines.append(f"DECLARE {decls};")
        if declares_cursor:
            lines += [
                f"DECLARE {cur} CURSOR LOCAL FAST_FORWARD FOR",
                f"{select_text};",
            ]
        lines += [
            f"OPEN {cur};",
            f"FETCH NEXT FROM {cur} INTO {fetch_vars};",
            "WHILE @@FETCH_STATUS = 0",
            "BEGIN",
            *rewritten,
            f"{self._indent()}FETCH NEXT FROM {cur} INTO {fetch_vars};",
            "END;",
            f"CLOSE {cur};",
            f"DEALLOCATE {cur};",
        ]
        return "\n".join(lines)

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        # An Oracle RAISE_APPLICATION_ERROR(-20xxx, <msg>) arrives as one
        # argument blob; RAISERROR takes the message text alone (a tuple in
        # its place is a syntax error). Keep the human-readable part.
        text, number, _rest = self._raise_parts(msg)
        payload = (text or number or msg).strip()
        # RAISERROR's message accepts only a literal, a variable or a msg id
        # — an expression (ERROR_NUMBER() + ' ' + ...) must go through a
        # variable. The counter keeps names unique across the script (T-SQL
        # variables are batch-scoped; two DECLAREs of one name collide).
        is_direct = (
            payload.startswith(("'", "@"))
            or re.fullmatch(r"-?\s*\d+", payload) is not None
        )
        if is_direct:
            return f"RAISERROR({payload}, 16, 1);"
        self._raise_msg_n += 1
        var = f"@unique_errmsg{self._raise_msg_n}"
        return (
            f"DECLARE {var} NVARCHAR(2048) = {payload};\n" f"RAISERROR({var}, 16, 1);"
        )

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        lines = ["BEGIN TRY"]
        self._indent_level += 1
        body_lines = self._emit_indented_stmts(node.try_body)
        if not any(
            line.strip() and not line.lstrip().startswith("--") for line in body_lines
        ):
            # An empty BEGIN TRY is a syntax error; SET NOCOUNT ON is the
            # canonical side-effect-free filler.
            body_lines.append(f"{self._indent()}SET NOCOUNT ON;")
        lines.extend(body_lines)
        self._indent_level -= 1
        lines.append("END TRY")
        lines.append("BEGIN CATCH")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.catch_body))
        self._indent_level -= 1
        lines.append("END CATCH")
        return "\n".join(lines)

    def _emit_begin_transaction(self, name: str | None) -> str:
        return f"BEGIN TRANSACTION{' ' + name if name else ''};"

    def _rollback_to_savepoint(self, name: str) -> str:
        return f"ROLLBACK TRANSACTION {name};"

    def _emit_savepoint(self, name: str | None) -> str:
        return f"SAVE TRANSACTION {name};" if name else "SAVE TRANSACTION;"

    def _emit_waitfor(self, node: WaitForStatement) -> str:
        return f"WAITFOR {node.kind} '{node.value}';"

    def _emit_cursor_op(self, node: CursorOperation) -> str:
        # Classic cursors are not variables: the generic '@' rename must not
        # leak into OPEN/FETCH/CLOSE or the reference won't match DECLARE.
        bare = node.cursor_name.lstrip("@")
        name = "@" + bare if bare.lower() in self._cursor_variables else bare
        return super()._emit_cursor_op(dataclasses.replace(node, cursor_name=name))

    def _emit_cursor_open(self, cursor_name: str, query_str: str) -> str:
        # In T-SQL the query lives on DECLARE CURSOR, so OPEN takes no query.
        return f"OPEN {cursor_name};"

    def _emit_cursor_fetch(self, cursor_name: str, into_str: str) -> str:
        return f"FETCH NEXT FROM {cursor_name} INTO {into_str};"

    def _emit_cursor_deallocate(self, cursor_name: str) -> str:
        return f"DEALLOCATE {cursor_name};"

    def _emit_exit(self, node: ExitStatement) -> str:
        cond = self._emit_node(node.condition) if node.condition else ""
        cond = self._translate_cursor_attrs(cond)
        # T-SQL has no EXIT WHEN; use IF <cond> BREAK.
        if cond:
            return f"IF {cond} BREAK;"
        return "BREAK;"

    def _translate_cursor_attrs(self, expr: str) -> str:
        if not expr:
            return expr
        # cur%NOTFOUND -> @@FETCH_STATUS <> 0 ; cur%FOUND -> = 0
        expr = re.sub(r"\w+\s*%\s*NOTFOUND", "@@FETCH_STATUS <> 0", expr, flags=re.I)
        expr = re.sub(r"\w+\s*%\s*FOUND", "@@FETCH_STATUS = 0", expr, flags=re.I)
        return expr

    def _emit_continue(self, node: ContinueStatement) -> str:
        # T-SQL CONTINUE takes no WHEN clause.
        return "CONTINUE;"

    def _emit_null(self, _node: NullStatement) -> str:
        # T-SQL has no NULL statement; emit a no-op comment.
        return "-- NULL (no-op)"

    def _emit_if_body(
        self,
        cond: str,
        then_body: tuple[ASTNode, ...],
        else_body: tuple[ASTNode, ...],
    ) -> str:
        lines = [f"IF {cond}", "BEGIN"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(then_body))
        self._indent_level -= 1
        lines.append("END")

        if else_body:
            if len(else_body) == 1 and isinstance(else_body[0], IfStatement):
                lines.append(f"ELSE {self._emit_node(else_body[0])}")
            else:
                lines.append("ELSE")
                lines.append("BEGIN")
                self._indent_level += 1
                lines.extend(self._emit_indented_stmts(else_body))
                self._indent_level -= 1
                lines.append("END")

        return "\n".join(lines)

    def _emit_execute_into(
        self, expr: str, params: list[str], into_vars: list[str], immediate: bool
    ) -> str:
        # T-SQL cannot capture a dynamic SELECT into variables directly;
        # INSERT ... EXEC materializes the result set into a table variable
        # and a SELECT TOP (1) assigns it (one column per INTO target).
        self._dyn_capture_seq = getattr(self, "_dyn_capture_seq", 0) + 1
        tbl = f"@_dyn_result_{self._dyn_capture_seq}"
        cols = [f"c{i + 1}" for i in range(len(into_vars))]
        col_defs = ", ".join(f"{c} NVARCHAR(4000)" for c in cols)
        assigns = ", ".join(f"{v} = {c}" for v, c in zip(into_vars, cols, strict=True))
        note = ""
        if params:
            note = (
                "\n-- UNIQUE: EXECUTE IMMEDIATE USING bindings dropped; "
                "inline them or use sp_executesql parameters: " + ", ".join(params)
            )
        return (
            f"DECLARE {tbl} TABLE ({col_defs});\n"
            f"INSERT INTO {tbl} EXEC sp_executesql {expr};\n"
            f"SELECT TOP (1) {assigns} FROM {tbl};{note}"
        )

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        if params:
            # Map Oracle USING binds to sp_executesql positional params.
            # The dynamic SQL placeholders (:1, :2 / ?) should be replaced
            # by @p1, @p2 manually; we emit a parameterized sp_executesql
            # call and flag it for review.
            names = [f"@p{i + 1}" for i in range(len(params))]
            decl = ", ".join(f"{n} SQL_VARIANT" for n in names)
            assigns = ", ".join(
                f"{n} = {val}" for n, val in zip(names, params, strict=False)
            )
            return (
                f"EXEC sp_executesql {expr}, N'{decl}', {assigns}; "
                f"-- UNIQUE: verify dynamic SQL placeholders match "
                f"{', '.join(names)}"
            )
        return f"EXEC sp_executesql {expr};"


register_emitter(TSqlEmitter.dialect_name, TSqlEmitter)
