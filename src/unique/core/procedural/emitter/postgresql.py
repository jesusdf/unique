# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — postgresql target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    ASTNode,
    CreateTriggerStatement,
    CursorDeclaration,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    ReturnStatement,
)
from unique.core.procedural.emitter.base import ProceduralEmitter, register_emitter


class PostgresEmitter(ProceduralEmitter):
    """PostgreSQL PL/pgSQL procedural emitter."""

    dialect_name = "postgresql"

    def _keep_default(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
    ) -> bool:
        # Only IN parameters may carry a DEFAULT, and an OUT/INOUT parameter
        # cannot appear after a parameter that has a default. Drop the default
        # from any OUT/INOUT param and from any IN param positioned before the
        # last OUT/INOUT, keeping the routine creatable.
        if not p.default:
            return False
        pg_last_out = -1
        for i, q in enumerate(params):
            if q.direction in ("OUT", "INOUT"):
                pg_last_out = i
        return not (p.direction in ("OUT", "INOUT") or idx < pg_last_out)

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        # PL/pgSQL: name CURSOR FOR <select>;
        query_str = (
            self._emit_node(node.query).rstrip().rstrip(";") if node.query else ""
        )
        body = f" CURSOR FOR {query_str}" if query_str else " CURSOR"
        return f"{node.name}{body};"

    def _emit_print(self, node: PrintStatement) -> str:
        return f"RAISE NOTICE '%', {self._emit_node(node.expression)};"

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        first, _ = self._split_raise_args(msg)
        return f"RAISE EXCEPTION '%', {first};"

    def _procedure_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}PROCEDURE {name}"

    def _keep_schema(self, schema: str) -> bool:
        # 'dbo' is T-SQL's default schema and has no PostgreSQL counterpart.
        return schema.lower() != "dbo"

    def _tvf_unsupported_note(self) -> str:
        return (
            "PostgreSQL needs RETURNS TABLE(col type ...) with RETURN QUERY; "
            "review the column list"
        )

    def _wants_empty_parens(self) -> bool:
        return True

    def _emit_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_pg_procedure_body(header, declarations, body_stmts)

    def _function_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}FUNCTION {name}"

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_pg_procedure_body(
            header, declarations, body_stmts, is_function=True
        )

    def _emit_trigger(self, node: CreateTriggerStatement) -> str:
        # PostgreSQL triggers call a separate trigger function that returns a
        # trigger and contains the body. Emit both the function and the CREATE
        # TRIGGER that invokes it.
        name = self._qualified_name(node.schema, node.name)
        events = ", ".join(node.events) if node.events else "UPDATE"
        func_name = f"{node.name}_func"
        qfunc = self._qualified_name(node.schema, func_name)
        fn_lines = [
            f"CREATE OR REPLACE FUNCTION {qfunc}()",
            "RETURNS TRIGGER",
            "LANGUAGE plpgsql",
            "AS $$",
        ]
        # Variable declarations must live in a DECLARE section before BEGIN
        # (PostgreSQL has no inline DECLARE), so hoist them like a routine.
        trg_decls, trg_body = self._split_declarations(tuple(node.body))
        if trg_decls:
            fn_lines.append("DECLARE")
            self._indent_level = 1
            for decl in trg_decls:
                fn_lines.append(f"{self._indent()}{self._emit_node(decl)}")
            self._indent_level = 0
        fn_lines.append("BEGIN")
        self._indent_level = 1
        fn_lines.extend(self._emit_indented_stmts(trg_body))
        self._indent_level = 0
        # A statement-level (set-based) trigger function has no NEW row, so it
        # returns NULL; a row-level AFTER returns NULL too and BEFORE returns
        # NEW. Default to NEW (safe for BEFORE, ignored for AFTER row-level);
        # for the set-based form return NULL.
        fn_lines.append(
            "    RETURN NULL;" if node.set_based_transition else "    RETURN NEW;"
        )
        fn_lines.append("END;")
        fn_lines.append("$$;")
        trg_lines = [
            f"CREATE OR REPLACE TRIGGER {name}",
            f"{node.timing} {events} ON {node.table}",
        ]
        if node.set_based_transition:
            # Expose the affected rows as the set-based transition tables the
            # body references (named to match T-SQL's inserted/deleted).
            trg_lines.append("REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted")
            trg_lines.append("FOR EACH STATEMENT")
        elif node.for_each == "ROW":
            trg_lines.append("FOR EACH ROW")
        trg_lines.append(f"EXECUTE FUNCTION {qfunc}();")
        return "\n".join(fn_lines) + "\n\n" + "\n".join(trg_lines)

    def _emit_return(self, node: ReturnStatement) -> str:
        # A PostgreSQL procedure cannot RETURN a value; emit a bare RETURN and
        # document the discarded code (a T-SQL RETURN <code> has no PG meaning).
        if self._in_pg_procedure and node.value:
            val = self._emit_node(node.value)
            return f"RETURN;  -- UNIQUE: discarded procedure RETURN value ({val})"
        if node.value:
            val = self._emit_node(node.value)
            return f"RETURN {val};"
        return "RETURN;"

    def _emit_begin_transaction(self, name: str | None) -> str:
        # Inside a plpgsql function transaction control is illegal; a procedure
        # starts its transaction implicitly. Document the dropped BEGIN.
        return (
            "/* UNIQUE: BEGIN TRANSACTION dropped -- PostgreSQL manages "
            "the routine transaction implicitly */"
        )

    def _sleep_call(self, secs: str) -> str:
        return f"PERFORM pg_sleep({secs});"

    def _emit_execute_stmt(self, expr: str, params: list[str]) -> str:
        return self._emit_pg_execute(expr, params)

    def _translate_cursor_attrs(self, expr: str) -> str:
        if not expr:
            return expr
        expr = re.sub(r"\w+\s*%\s*NOTFOUND", "NOT FOUND", expr, flags=re.I)
        expr = re.sub(r"\w+\s*%\s*FOUND", "FOUND", expr, flags=re.I)
        return expr


register_emitter(PostgresEmitter.dialect_name, PostgresEmitter)
