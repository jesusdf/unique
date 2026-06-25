# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — oracle target."""

from __future__ import annotations

from unique.core.ast_nodes import (
    ASTNode,
    CreateTriggerStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
)
from unique.core.procedural.emitter.base import ProceduralEmitter, register_emitter


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
        return f"\nRETURN {ret_type}"

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        # Oracle spells out IN for every parameter direction.
        dt = self._emit_data_type(p.data_type)
        default_str = f" DEFAULT {self._emit_node(p.default)}" if p.default else ""
        direction_str = f"{p.direction} " if p.direction != "IN" else "IN "
        return f"{p.name} {direction_str}{dt}{default_str}"

    def _emit_print(self, node: PrintStatement) -> str:
        return f"DBMS_OUTPUT.PUT_LINE({self._emit_node(node.expression)});"

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        first, _ = self._split_raise_args(msg)
        return f"RAISE_APPLICATION_ERROR(-20001, {first});"

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


register_emitter(OracleEmitter.dialect_name, OracleEmitter)
