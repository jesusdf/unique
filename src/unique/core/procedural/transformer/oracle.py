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

    # Type names Oracle's CAST wants instead of the T-SQL spelling.
    _CAST_TYPE_MAP = {
        "DECIMAL": "NUMBER",
        "NUMERIC": "NUMBER",
        "DEC": "NUMBER",
        "VARCHAR": "VARCHAR2",
        "NVARCHAR": "NVARCHAR2",
    }
    _CAST_CONSTRAINED_RE = re.compile(
        r"(?i)\bAS\s+(DECIMAL|NUMERIC|DEC|NUMBER|FLOAT|VARCHAR2?|NVARCHAR2?|CHAR|NCHAR)"
        r"\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\)"
    )

    def _fix_raw_sql_target(self, sql: str) -> str:
        # dbo doesn't exist in Oracle; drop a dbo. qualifier on calls within
        # expressions (e.g. dbo.func1() in an assignment, RETURN or COALESCE).
        sql = re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)

        # T-SQL string ``+`` in an assignment/return expression -> Oracle ``||``.
        sql = self._rewrite_string_concat(sql, "oracle")

        # A MySQL/PostgreSQL-source trigger body's NEW./OLD. row reference in an
        # assignment value becomes Oracle's :NEW./:OLD.
        if self._in_trigger:
            sql = self._to_oracle_row_ref(sql)

        # A PL/SQL expression CAST rejects a constrained type (PLS-00103):
        # CAST(x AS NUMBER(12,2)) / VARCHAR2(10) must drop the length, and
        # DECIMAL/NUMERIC must become NUMBER. Only the numeric-constrained
        # ``AS <type>(...)`` form (never an alias or function call) is matched.
        def _unconstrained_cast_type(m: re.Match[str]) -> str:
            typ = m.group(1).upper()
            return f"AS {self._CAST_TYPE_MAP.get(typ, typ)}"

        return self._CAST_CONSTRAINED_RE.sub(_unconstrained_cast_type, sql)

    def _named_arg_op(self) -> str | None:
        # Oracle passes a procedure's named argument as ``name => value``.
        return "=>"

    def _trigger_new_ref(self) -> str:
        return ":NEW."

    def _trigger_old_ref(self) -> str:
        return ":OLD."

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "NCLOB" if is_unicode else "CLOB"


register_transformer(OracleTransformer.target_name, OracleTransformer)
