# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — tsql target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    ASTNode,
    ExceptionBlock,
    LoopStatement,
    NullStatement,
    RawSQL,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class TSqlTransformer(ProceduralTransformer):
    """Transforms toward T-SQL (SQL Server)."""

    target_name = "tsql"

    #: ``a - b`` between two identifiers (used to rewrite date subtraction).
    _SUBTRACT_RE = re.compile(r"(@?\w+)\s*-\s*(@?\w+)")

    def _fix_raw_sql_target(self, sql: str) -> str:
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

    def _alter_becomes_create(self) -> bool:
        # T-SQL keeps ALTER PROCEDURE as-is.
        return False

    def _rewrites_trigger_pseudotables(self) -> bool:
        # T-SQL keeps inserted/deleted pseudo-tables as-is.
        return False

    def _warn_for_loop_unsupported(self) -> None:
        self._warnings.append(
            "FOR loop has no direct T-SQL equivalent. "
            "Manual conversion to WHILE loop required."
        )

    def _transform_loop(self, node: LoopStatement) -> ASTNode:
        # T-SQL has no bare LOOP; express it as WHILE 1=1.
        return WhileStatement(
            condition=RawSQL(sql="1=1", reason="infinite loop"),
            body=self._ensure_non_empty_body(self._transform_body(node.body)),
        )

    def _transform_null(self, node: NullStatement) -> ASTNode:
        return RawSQL(sql="-- NULL statement (no-op)", reason="no T-SQL equivalent")

    def _has_update_predicate(self) -> bool:
        # T-SQL keeps UPDATE(col) as-is.
        return False

    def _uses_set_statement(self) -> bool:
        return True

    def _assignment_becomes_set(self) -> bool:
        return True

    def _transform_exception_block(self, node: ExceptionBlock) -> ASTNode:
        # T-SQL's only structured-handler form is TRY/CATCH; flatten the
        # EXCEPTION handlers' bodies into the CATCH block.
        body: list[ASTNode] = []
        for handler in node.handlers:
            body.extend(handler.body)
        return TryCatchBlock(
            try_body=(),
            catch_body=self._transform_body(tuple(body)),
        )


register_transformer(TSqlTransformer.target_name, TSqlTransformer)
