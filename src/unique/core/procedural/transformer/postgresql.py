# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — postgresql target."""

from __future__ import annotations

import re

from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class PostgresTransformer(ProceduralTransformer):
    """Transforms toward PostgreSQL PL/pgSQL."""

    target_name = "postgresql"

    def _system_var_map(self) -> dict[str, str]:
        return {
            "@@ROWCOUNT": "ROW_COUNT",
            "@@IDENTITY": "LASTVAL()",
            # SQLSTATE is only available inside an EXCEPTION handler in plpgsql,
            # so it cannot stand in for an inline @@ERROR check.
            "@@ERROR": self._neutral_global("@@ERROR", "use an EXCEPTION handler"),
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "the routine manages its transaction"
            ),
        }

    def _fetch_status_forms(self) -> tuple[str, str] | None:
        # plpgsql sets FOUND after every FETCH.
        return ("FOUND", "NOT FOUND")

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "TEXT"

    def _named_arg_op(self) -> str | None:
        # PostgreSQL passes a procedure's named argument as ``name => value``.
        return "=>"

    def _supports_transition_tables(self) -> bool:
        # A statement-level trigger with REFERENCING NEW/OLD TABLE sees all rows.
        return True

    def _fix_target_dml(self, sql: str) -> str:
        sql = self._pg_string_concat(sql)
        sql = self._pg_clean_dml(sql)
        return sql

    def _update_predicate(self, col: str) -> str | None:
        return f"(NEW.{col} IS DISTINCT FROM OLD.{col})"

    def _fix_raw_sql_target(self, sql: str) -> str:
        sql = self._pg_string_concat(sql)
        # T-SQL ERROR_MESSAGE() inside a CATCH -> SQLERRM in the EXCEPTION
        # handler (parameterless; the empty parens would not parse).
        sql = re.sub(r"(?i)\bERROR_MESSAGE\s*\(\s*\)", "SQLERRM", sql)
        # dbo doesn't exist in PostgreSQL; drop a dbo. qualifier on calls.
        return re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)


register_transformer(PostgresTransformer.target_name, PostgresTransformer)
