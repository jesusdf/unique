# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — mysql target."""

from __future__ import annotations

from unique.core.ast_nodes import ASTNode, RawSQL
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class MySqlTransformer(ProceduralTransformer):
    """Transforms toward MySQL."""

    target_name = "mysql"

    def _system_var_map(self) -> dict[str, str]:
        return {
            "@@ROWCOUNT": "ROW_COUNT()",
            "@@IDENTITY": "LAST_INSERT_ID()",
            "@@ERROR": self._neutral_global("@@ERROR", "use a DECLARE ... HANDLER"),
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "the routine manages its transaction"
            ),
        }

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "LONGTEXT"

    def _uses_set_statement(self) -> bool:
        return True

    def _noop_statement(self) -> ASTNode:
        # DO evaluates an expression and discards it; the cheapest valid
        # statement to keep a block non-empty. Terminator included since the
        # IF/loop emitters don't add one for RawSQL.
        return RawSQL(sql="DO 0;", reason="no-op")

    def _noop_sql(self) -> str:
        return "DO 0;"

    def _fix_target_dml(self, sql: str) -> str:
        sql = self._mysql_string_concat(sql)
        sql = self._mysql_clean_dml(sql)
        sql = self._mysql_fix_cast_max(sql)
        sql = self._mysql_string_split(sql)
        return sql

    def _update_predicate(self, col: str) -> str | None:
        return f"NOT (NEW.{col} <=> OLD.{col})"

    def _fix_raw_sql_target(self, sql: str) -> str:
        sql = self._mysql_normalize_funcs(sql)
        sql = self._mysql_string_concat(sql)
        sql = self._mysql_clean_dml(sql)
        sql = self._mysql_fix_cast_max(sql)
        sql = self._mysql_string_split(sql)
        return sql


register_transformer(MySqlTransformer.target_name, MySqlTransformer)
