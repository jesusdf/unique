# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — mysql target."""

from __future__ import annotations

import dataclasses
import re

from unique.core.ast_nodes import (
    ASTNode,
    CallStatement,
    CreateTriggerStatement,
    CursorDeclaration,
    ExitStatement,
    ParameterDefinition,
    ReturnStatement,
    TryCatchBlock,
)
from unique.core.procedural.emitter.base import ProceduralEmitter, register_emitter


class MySqlEmitter(ProceduralEmitter):
    """MySQL procedural emitter."""

    dialect_name = "mysql"

    # Built-in function names MySQL/MariaDB only recognize when the opening
    # parenthesis follows immediately (default sql_mode, no IGNORE_SPACE).
    # Token-joined expression text ("CAST ( x AS ... )") must be collapsed.
    _NO_SPACE_FUNCS = re.compile(
        r"(?i)\b(CAST|CONVERT|COUNT|SUM|MIN|MAX|AVG|COALESCE|IFNULL|NULLIF|"
        r"CONCAT|SUBSTRING|SUBSTR|TRIM|UPPER|LOWER|ABS|ROUND|NOW|CURDATE|"
        r"CURTIME|LENGTH|CHAR_LENGTH|GROUP_CONCAT|LAST_INSERT_ID)\s+\("
    )

    def emit(self, node: ASTNode) -> str:
        return self._NO_SPACE_FUNCS.sub(lambda m: f"{m.group(1)}(", super().emit(node))

    def _keep_schema(self, schema: str) -> bool:
        # MySQL has no schema layer (a schema is a database); drop all.
        return False

    def _emit_trigger(self, node: CreateTriggerStatement) -> str:
        # MySQL allows exactly one event per trigger; split AFTER INSERT,
        # UPDATE into one trigger per event (MariaDB rejects the multi-event
        # shell outright).
        events = tuple(node.events) if node.events else ()
        if len(events) <= 1:
            return super()._emit_trigger(node)
        parts = [
            super()._emit_trigger(
                dataclasses.replace(
                    node, name=f"{node.name}_{ev[:3].lower()}", events=(ev,)
                )
            )
            for ev in events
        ]
        return "\n\n".join(parts)

    def _tvf_unsupported_note(self) -> str:
        return (
            "MySQL has no table-returning functions; use a view or a procedure "
            "with a result set"
        )

    def _emit_loop_body(self, body_lines: list[str]) -> str:
        return "\n".join(["loop_lbl: LOOP", *body_lines, "END LOOP loop_lbl;"])

    def _assignment_form(self, target: str, val: str) -> str:
        return f"SET {target} = {val};"

    def _emit_guard_if(self, cond: str, body_lines: list[str]) -> str | None:
        # MySQL's IF accepts an EXISTS/subquery condition, so the guard is an
        # IF … THEN … END IF; rather than a scanned cursor.
        return "\n".join([f"IF {cond} THEN", *body_lines, "END IF;"])

    def _emit_for_loop_body(
        self, variable: str, cursor_str: str, body_lines: list[str]
    ) -> str:
        # MySQL: explicit cursor inside a BEGIN ... END with a NOT FOUND handler
        # driving a loop.
        cur = f"{variable}_cur"
        done = f"{variable}_done"
        lines = [
            "-- UNIQUE: Oracle implicit cursor FOR-loop expanded to an "
            "explicit MySQL cursor.",
            "-- Declare one variable per selected column and complete the "
            "FETCH INTO list.",
            f"DECLARE {done} INT DEFAULT FALSE;",
            f"DECLARE {cur} CURSOR FOR {cursor_str};",
            f"DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE;",
            f"OPEN {cur};",
            f"{variable}_loop: LOOP",
            f"{self._indent()}FETCH {cur} INTO /* col1, col2, ... */;",
            f"{self._indent()}IF {done} THEN LEAVE {variable}_loop; END IF;",
        ]
        lines.extend(body_lines)
        lines.append("END LOOP;")
        lines.append(f"CLOSE {cur};")
        return "\n".join(lines)

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        # MySQL puts the direction *before* the parameter name and does not
        # support per-parameter DEFAULT values; callers must always pass every
        # argument. The default is dropped (and surfaced as a warning by the
        # caller) rather than emitted as invalid syntax. Stored functions forbid
        # direction keywords entirely.
        dt = self._emit_data_type(p.data_type)
        direction_str = ""
        if not is_function:
            if p.direction in ("OUT", "INOUT"):
                direction_str = f"{p.direction} "
            elif p.direction == "IN":
                direction_str = "IN "
        return f"{direction_str}{p.name} {dt}"

    def _declare_default_op(self) -> str:
        return "DEFAULT"

    def _declare_prefix(self) -> str:
        return "DECLARE "

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        # MySQL: DECLARE name CURSOR FOR <select>;
        query_str = (
            self._emit_node(node.query).rstrip().rstrip(";") if node.query else ""
        )
        body = f" FOR {query_str}" if query_str else ""
        return f"DECLARE {node.name} CURSOR{body};"

    def _wants_empty_parens(self) -> bool:
        return True

    def _emit_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_mysql_procedure_body(header, declarations, body_stmts)

    def _returns_clause(self, ret_type: str) -> str:
        return f"\nRETURNS {ret_type}\nDETERMINISTIC"

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_mysql_procedure_body(
            header, declarations, body_stmts, is_function=True
        )

    def _adjust_trigger_timing(self, timing: str) -> tuple[str, str]:
        # MySQL has no INSTEAD OF triggers (they apply to views in T-SQL/PG and
        # have no MySQL form). Document the substitution and fall back to BEFORE
        # so the trigger is at least syntactically valid for review.
        if timing.upper().startswith("INSTEAD OF"):
            note = (
                "-- UNIQUE: MySQL has no INSTEAD OF trigger; emitted as BEFORE "
                "for review (original was INSTEAD OF, typically on a view).\n"
            )
            return note, "BEFORE"
        return "", timing

    def _trigger_header(
        self,
        name: str,
        node: CreateTriggerStatement,
        events: str,
        timing: str,
    ) -> list[str]:
        return [
            f"CREATE TRIGGER {name}",
            f"{timing} {events} ON {node.table}",
            "FOR EACH ROW",
            "BEGIN",
        ]

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        # MySQL has no EXCEPTION block; the catch logic goes into a
        # DECLARE ... HANDLER declared at the top of the block, before the
        # protected (try) statements.
        lines = ["BEGIN"]
        self._indent_level += 1
        lines.append(f"{self._indent()}DECLARE EXIT HANDLER FOR SQLEXCEPTION")
        lines.append(f"{self._indent()}BEGIN")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.catch_body))
        self._indent_level -= 1
        lines.append(f"{self._indent()}END;")
        lines.extend(self._emit_indented_stmts(node.try_body))
        self._indent_level -= 1
        lines.append("END;")
        return "\n".join(lines)

    def _emit_return(self, node: ReturnStatement) -> str:
        # In a MySQL procedure, RETURN is illegal whether or not it has a value
        # (a T-SQL procedure RETURN <code> has no MySQL equivalent). Translate
        # to LEAVE of the labeled procedure block; document a discarded value.
        if not self._in_mysql_function and self._proc_leave_label:
            if node.value:
                val = self._emit_node(node.value)
                return (
                    f"LEAVE {self._proc_leave_label};  "
                    f"-- UNIQUE: discarded procedure RETURN value ({val})"
                )
            return f"LEAVE {self._proc_leave_label};"
        if node.value:
            val = self._emit_node(node.value)
            return f"RETURN {val};"
        return "RETURN;"

    def _emit_begin_transaction(self, name: str | None) -> str:
        return "START TRANSACTION;"

    def _sleep_call(self, secs: str) -> str:
        return f"DO SLEEP({secs});"

    def _emit_call(self, node: CallStatement) -> str:
        # MySQL has no schema layer, so any qualifier is dropped by name lookup.
        return f"CALL {node.name}({node.args});"

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        # MySQL: distinguish three forms that all arrive as a captured
        # expression here:
        #   1. EXEC sp_executesql @sql, N'<decls>', @p1, ...  -> dynamic SQL
        #   2. EXEC proc_name @a OUTPUT, 'b', ...             -> a routine call
        #   3. EXEC @sql / EXEC ('...')                       -> dynamic SQL
        return self._emit_mysql_execute(expr, params, immediate)

    def _emit_exit(self, node: ExitStatement) -> str:
        cond = self._emit_node(node.condition) if node.condition else ""
        cond = self._translate_cursor_attrs(cond)
        # MySQL uses LEAVE with a loop label; emit a guarded LEAVE.
        if cond:
            return f"IF {cond} THEN LEAVE loop_lbl; END IF;"
        return "LEAVE loop_lbl;"

    def _translate_cursor_attrs(self, expr: str) -> str:
        if not expr:
            return expr
        # MySQL signals end-of-cursor via a NOT FOUND handler; flag it.
        expr = re.sub(
            r"\w+\s*%\s*NOTFOUND",
            "done /* set by CONTINUE HANDLER FOR NOT FOUND */",
            expr,
            flags=re.I,
        )
        return expr


register_emitter(MySqlEmitter.dialect_name, MySqlEmitter)
