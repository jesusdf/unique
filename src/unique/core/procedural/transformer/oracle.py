# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — oracle target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    ASTNode,
    ExceptionBlock,
    ExceptionHandler,
    TryCatchBlock,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class OracleTransformer(ProceduralTransformer):
    """Transforms toward Oracle PL/SQL."""

    target_name = "oracle"

    def _system_var_map(self) -> dict[str, str]:
        return {
            "@@ROWCOUNT": "SQL%ROWCOUNT",
            "@@IDENTITY": "/* @@IDENTITY: use <sequence>.CURRVAL */",
            # SQLCODE is a valid Oracle function (0 in normal flow, the last
            # error code inside an exception handler).
            "@@ERROR": "SQLCODE",
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "transactions are implicit"
            ),
        }

    def _supports_type_reference(self) -> bool:
        # Oracle supports %TYPE/%ROWTYPE natively.
        return True

    def _strip_dbo_schema(self) -> bool:
        # Oracle objects live in the current user's schema; 'dbo' has no meaning.
        return True

    def _trigger_forces_or_replace(self) -> bool:
        return True

    def _transform_try_catch(self, node: TryCatchBlock) -> ASTNode:
        # Oracle expresses error handling as a PL/SQL EXCEPTION block.
        return ExceptionBlock(
            handlers=(
                ExceptionHandler(
                    exception_name="OTHERS",
                    body=self._transform_body(node.catch_body),
                ),
            )
        )

    def _fix_target_dml(self, sql: str) -> str:
        return self._fix_oracle_dml(sql)

    def _update_predicate(self, col: str) -> str | None:
        return f"UPDATING('{col}')"

    def _fix_unwrapped_scalar(self, sql: str) -> str:
        return self._fix_oracle_dml(sql)

    def _fix_raw_sql_target(self, sql: str) -> str:
        # dbo doesn't exist in Oracle; drop a dbo. qualifier on calls within
        # expressions (e.g. dbo.func1() in an assignment, RETURN or COALESCE).
        return re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)

    def _trigger_new_ref(self) -> str:
        return ":NEW."

    def _trigger_old_ref(self) -> str:
        return ":OLD."

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "NCLOB" if is_unicode else "CLOB"


register_transformer(OracleTransformer.target_name, OracleTransformer)
