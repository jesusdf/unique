# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — tsql target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    ASTNode,
    ContinueStatement,
    CursorDeclaration,
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
from unique.core.procedural.emitter.base import ProceduralEmitter, register_emitter


class TSqlEmitter(ProceduralEmitter):
    """T-SQL (SQL Server) procedural emitter."""

    dialect_name = "tsql"

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        dt = self._emit_data_type(p.data_type)
        default_str = f" = {self._emit_node(p.default)}" if p.default else ""
        direction_str = " OUTPUT" if p.direction in ("OUT", "INOUT") else ""
        return f"{p.name} {dt}{default_str}{direction_str}"

    def _supports_table_valued_function(self) -> bool:
        return True

    def _declare_default_op(self) -> str:
        return "="

    def _declare_prefix(self) -> str:
        return "DECLARE "

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        query_str = (
            self._emit_node(node.query).rstrip().rstrip(";") if node.query else ""
        )
        body = f" FOR {query_str}" if query_str else ""
        return f"DECLARE {node.name} CURSOR{body};"

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
        cols = [c.strip() for c in select_list.split(",")]
        targets = list(node.into_vars)
        pairs = []
        for i, var in enumerate(targets):
            col = cols[i] if i < len(cols) else (cols[-1] if cols else "")
            pairs.append(f"{var} = {col}")
        assignments = ", ".join(pairs)
        return f"SELECT {assignments} {rest};"

    def _emit_for_loop_body(
        self, variable: str, cursor_str: str, body_lines: list[str]
    ) -> str:
        # T-SQL has no implicit cursor FOR loop. Emit an explicit cursor
        # scaffold (structurally complete) so the developer only needs to fill
        # the per-column fetch variables.
        cur = f"{variable}_cur"
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
        ]
        lines.extend(body_lines)
        lines.append(
            f"{self._indent()}FETCH NEXT FROM {cur} INTO /* @col1, @col2, ... */;"
        )
        lines.append("END;")
        lines.append(f"CLOSE {cur};")
        lines.append(f"DEALLOCATE {cur};")
        return "\n".join(lines)

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        return f"RAISERROR({msg}, 16, 1);"

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        lines = ["BEGIN TRY"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.try_body))
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
