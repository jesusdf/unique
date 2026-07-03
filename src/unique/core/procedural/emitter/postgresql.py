# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — postgresql target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    AnonymousBlock,
    ASTNode,
    CreateTriggerStatement,
    CursorDeclaration,
    DeclareStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    ReturnStatement,
    needs_procedural_wrapper,
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
        # Keep the human-readable message, not the error number (audit
        # 2026-07-02, S2-2). The '%%'-format form is safe for texts that
        # contain literal % characters.
        text, number, _ = self._raise_parts(msg)
        payload = text or number or msg
        return f"RAISE EXCEPTION '%', {payload};"

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
        #
        # Transition-table rules (surfaced by the live FE harness): NEW TABLE
        # is only legal on INSERT/UPDATE triggers, OLD TABLE only on
        # UPDATE/DELETE, and a trigger declaring transition tables must have
        # exactly ONE event — so a set-based multi-event trigger is split into
        # one trigger (and function) per event.
        events = tuple(node.events) if node.events else ("UPDATE",)
        if not node.set_based_transition:
            return self._emit_trigger_variant(node, events, suffix="")
        if len(events) == 1:
            return self._emit_trigger_variant(node, events, suffix="")
        parts = [
            self._emit_trigger_variant(node, (ev,), suffix=f"_{ev[:3].lower()}")
            for ev in events
        ]
        return "\n\n".join(parts)

    def _emit_trigger_variant(
        self,
        node: CreateTriggerStatement,
        events: tuple[str, ...],
        suffix: str,
    ) -> str:
        """Emit one trigger-function + CREATE TRIGGER pair for *events*."""
        name = self._qualified_name(node.schema, node.name + suffix)
        func_name = f"{node.name}{suffix}_func"
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
        body_lines = self._emit_indented_stmts(trg_body)
        self._indent_level = 0
        body_text = "\n".join(body_lines)
        refs_inserted = re.search(r"\binserted\b", body_text) is not None
        refs_deleted = re.search(r"\bdeleted\b", body_text) is not None
        referencing: list[str] = []
        preamble: list[str] = []
        if node.set_based_transition:
            # T-SQL does not re-fire a trigger from its own statements
            # (RECURSIVE_TRIGGERS is OFF by default); PostgreSQL always
            # does, so a set-based body that updates its own table would
            # recurse until the stack limit. Bail out on nested firings.
            preamble.append("    IF pg_trigger_depth() > 1 THEN")
            preamble.append("        RETURN NULL;")
            preamble.append("    END IF;")
            event = events[0]
            if refs_inserted:
                if event in ("INSERT", "UPDATE"):
                    referencing.append("NEW TABLE AS inserted")
                else:
                    # T-SQL's inserted is EMPTY (not absent) on DELETE.
                    preamble.append(
                        "    CREATE TEMP TABLE IF NOT EXISTS inserted "
                        f"(LIKE {node.table}) ON COMMIT DROP;"
                    )
            if refs_deleted:
                if event in ("UPDATE", "DELETE"):
                    referencing.append("OLD TABLE AS deleted")
                else:
                    # T-SQL's deleted is EMPTY (not absent) on INSERT.
                    preamble.append(
                        "    CREATE TEMP TABLE IF NOT EXISTS deleted "
                        f"(LIKE {node.table}) ON COMMIT DROP;"
                    )
        fn_lines.extend(preamble)
        fn_lines.extend(body_lines)
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
            f"{node.timing} {' OR '.join(events)} ON {node.table}",
        ]
        if node.set_based_transition:
            if referencing:
                trg_lines.append("REFERENCING " + " ".join(referencing))
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

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        return self._emit_pg_execute(expr, params, immediate)

    def _emit_anonymous_block(self, node: AnonymousBlock) -> str:
        """PostgreSQL runs a top-level anonymous block inside ``DO $$ … $$;``.

        A block that only calls procedures (no declarations, no control flow)
        needs no wrapper — a bare ``CALL`` runs standalone — so it is emitted
        directly, matching the standalone-EXEC path. Anything with declarations
        or control flow is wrapped in a ``DO $$ [DECLARE …] BEGIN … END $$;``
        PL/pgSQL block.
        """
        if node.degraded:
            return self._emit_degraded_anonymous_block(node)
        decls = [s for s in node.statements if isinstance(s, DeclareStatement)]
        body = [s for s in node.statements if not isinstance(s, DeclareStatement)]
        needs_wrapper = needs_procedural_wrapper(node.statements)
        if not needs_wrapper:
            return "\n".join(self._emit_node(s) for s in body)

        lines = ["DO $$"]
        if decls:
            lines.append("DECLARE")
            self._indent_level += 1
            lines.extend(self._emit_indented_stmts(tuple(decls)))
            self._indent_level -= 1
        lines.append("BEGIN")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(tuple(body)))
        self._indent_level -= 1
        lines.append("END $$;")
        return "\n".join(lines)

    def _translate_cursor_attrs(self, expr: str) -> str:
        if not expr:
            return expr
        expr = re.sub(r"\w+\s*%\s*NOTFOUND", "NOT FOUND", expr, flags=re.I)
        expr = re.sub(r"\w+\s*%\s*FOUND", "FOUND", expr, flags=re.I)
        return expr


register_emitter(PostgresEmitter.dialect_name, PostgresEmitter)
