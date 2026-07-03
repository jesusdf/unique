# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — oracle target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    AnonymousBlock,
    ASTNode,
    CallStatement,
    CreateTriggerStatement,
    DeclareStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    SelectIntoStatement,
)
from unique.core.procedural.emitter.base import ProceduralEmitter, register_emitter

_SIZE_RE = re.compile(r"\(\s*\d+\s*(?:,\s*\d+\s*)?\)")


def _unconstrained(data_type: str) -> str:
    """Strip length/precision from a type for parameter/RETURN position.

    Oracle rejects constrained types on formal parameters and function
    return clauses (PLS-00103); ``NUMBER(5, 2)`` must become ``NUMBER``.
    """
    return _SIZE_RE.sub("", data_type).strip()


class OracleEmitter(ProceduralEmitter):
    """Oracle PL/SQL procedural emitter."""

    dialect_name = "oracle"

    def _procedure_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}PROCEDURE {name}"

    def _keep_schema(self, schema: str) -> bool:
        # 'dbo' is T-SQL's default schema and has no Oracle counterpart.
        return schema.lower() != "dbo"

    def _tvf_unsupported_note(self) -> str:
        return (
            "Oracle needs a pipelined function over a declared collection type; "
            "review manually"
        )

    def _emit_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_oracle_procedure_body(header, declarations, body_stmts)

    def _function_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}FUNCTION {name}"

    def _returns_clause(self, ret_type: str) -> str:
        return f"\nRETURN {_unconstrained(ret_type)}"

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        # Oracle spells out IN for every parameter direction. Formal
        # parameters (and RETURN types) must use unconstrained types:
        # NUMBER(10) or VARCHAR2(50) raise PLS-00103 in a parameter list
        # (audit 2026-07-02, S1-11).
        dt = _unconstrained(self._emit_data_type(p.data_type))
        default_str = f" DEFAULT {self._emit_node(p.default)}" if p.default else ""
        direction_str = f"{p.direction} " if p.direction != "IN" else "IN "
        return f"{p.name} {direction_str}{dt}{default_str}"

    def _emit_select_into(self, node: SelectIntoStatement) -> str:
        base = super()._emit_select_into(node)
        if not node.tsql_assignment:
            return base
        # T-SQL "SELECT @v = col ..." leaves @v unchanged when no row
        # matches; Oracle SELECT INTO raises NO_DATA_FOUND instead, which
        # would make a following "IF v IS NULL" guard unreachable (audit
        # 2026-07-02, S2-3). A nested block with an empty handler restores
        # the T-SQL semantics.
        return (
            "BEGIN\n"
            f"    {base}\n"
            "EXCEPTION\n"
            "    WHEN NO_DATA_FOUND THEN\n"
            "        NULL;  -- T-SQL leaves the variables unchanged\n"
            "END;"
        )

    def _emit_print(self, node: PrintStatement) -> str:
        return f"DBMS_OUTPUT.PUT_LINE({self._emit_node(node.expression)});"

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        # Message text preserved; T-SQL user error numbers 50000-50999 map
        # onto Oracle's -20000..-20999 user range (audit 2026-07-02, S2-2).
        text, number, _ = self._raise_parts(msg)
        code = -20001
        if number is not None and 50000 <= int(number) <= 50999:
            code = -(20000 + (int(number) - 50000))
        payload = text or number or msg
        return f"RAISE_APPLICATION_ERROR({code}, {payload});"

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_oracle_procedure_body(header, declarations, body_stmts)

    def _trigger_header(
        self,
        name: str,
        node: CreateTriggerStatement,
        events: str,
        timing: str,
    ) -> list[str]:
        prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
        lines = [f"{prefix}TRIGGER {name}", f"{node.timing} {events} ON {node.table}"]
        if node.for_each == "ROW":
            lines.append("FOR EACH ROW")
        lines.append("BEGIN")
        return lines

    def _trigger_end(self) -> str:
        return "END;"

    def _emit_anonymous_block(self, node: AnonymousBlock) -> str:
        """Oracle runs a top-level statement sequence as a PL/SQL anonymous
        block: ``[DECLARE …] BEGIN … END;``. Procedure calls and assignments are
        only valid inside such a block, so always wrap (even a single call)."""
        decls = [s for s in node.statements if isinstance(s, DeclareStatement)]
        body = [s for s in node.statements if not isinstance(s, DeclareStatement)]
        lines: list[str] = []
        if decls:
            lines.append("DECLARE")
            self._indent_level += 1
            lines.extend(self._emit_indented_stmts(tuple(decls)))
            self._indent_level -= 1
        lines.append("BEGIN")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(tuple(body)))
        self._indent_level -= 1
        lines.append("END;")
        return "\n".join(lines)

    def _emit_call(self, node: CallStatement) -> str:
        # Oracle invokes a procedure by bare name inside a PL/SQL block; the
        # surrounding anonymous block supplies BEGIN/END.
        name = self._qualified_name(node.schema, node.name)
        return f"{name}({node.args});"

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        """Oracle EXEC handling.

        A named stored-procedure call becomes ``name(args);`` (Oracle invokes a
        procedure by name inside a PL/SQL block; the surrounding anonymous block
        supplies BEGIN/END). A bare dynamic-SQL string/variable keeps
        ``EXECUTE IMMEDIATE [USING …]``. The proc name may be schema-qualified
        (dbo.create_invoice); the dbo default schema is dropped.
        """
        stripped = expr.strip()
        # An Oracle EXECUTE IMMEDIATE (or a dynamic-SQL string/bind/expression)
        # keeps ``EXECUTE IMMEDIATE`` — the ``immediate`` flag settles the case a
        # record field (r.cmd) would otherwise misread as a named-proc call.
        if immediate or stripped.startswith(("'", "@", "v_", "(", "N'", ":")):
            if params:
                return f"EXECUTE IMMEDIATE {expr} USING {', '.join(params)};"
            return f"EXECUTE IMMEDIATE {expr};"
        # Named procedure call.
        m = re.match(r"(?i)^(?:\[?\w+\]?\s*\.\s*)*\[?(\w+)\]?\s*(.*)$", stripped)
        if m:
            proc_name = m.group(1)
            args = self._split_exec_args(m.group(2).strip())
            return f"{proc_name}({', '.join(args)});"
        if params:
            return f"EXECUTE IMMEDIATE {expr} USING {', '.join(params)};"
        return f"EXECUTE IMMEDIATE {expr};"


register_emitter(OracleEmitter.dialect_name, OracleEmitter)
