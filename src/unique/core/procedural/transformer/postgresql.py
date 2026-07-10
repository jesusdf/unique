# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — postgresql target."""

from __future__ import annotations

import dataclasses
import re

from unique.core.ast_nodes import ASTNode, EmbeddedDML, ForLoopStatement, RawSQL
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

    def _transform_for_loop(self, node: ForLoopStatement) -> ASTNode:
        result = super()._transform_for_loop(node)
        if (
            isinstance(result, ForLoopStatement)
            and result.cursor is not None
            and result.variable.lower() in self._declared_scalar_names
        ):
            # PL/SQL lets a row FOR-loop shadow a declared scalar; plpgsql
            # rejects a scalar loop variable over rows — rename the loop
            # variable and its row references (the declared scalar keeps its
            # meaning outside the loop, exactly as in Oracle).
            new_var = f"{result.variable}_rec"
            ref = re.compile(rf"(?i)\b{re.escape(result.variable)}\s*\.\s*")

            def rename(stmt: ASTNode) -> ASTNode:
                if isinstance(stmt, RawSQL):
                    return RawSQL(
                        sql=ref.sub(f"{new_var}.", stmt.sql), reason=stmt.reason
                    )
                if isinstance(stmt, EmbeddedDML):
                    return EmbeddedDML(
                        sql=ref.sub(f"{new_var}.", stmt.sql), dialect=stmt.dialect
                    )
                changes: dict[str, object] = {}
                for f in dataclasses.fields(stmt):
                    val = getattr(stmt, f.name)
                    if isinstance(val, ASTNode):
                        changes[f.name] = rename(val)
                    elif (
                        isinstance(val, tuple)
                        and val
                        and all(isinstance(x, ASTNode) for x in val)
                    ):
                        changes[f.name] = tuple(rename(x) for x in val)
                if changes:
                    return dataclasses.replace(stmt, **changes)  # type: ignore[arg-type]
                return stmt

            return ForLoopStatement(
                variable=new_var,
                range_start=result.range_start,
                range_end=result.range_end,
                cursor=rename(result.cursor) if result.cursor else None,
                body=tuple(rename(x) for x in result.body),
            )
        return result

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
        if self._in_trigger:
            # PL/SQL trigger event predicates: plpgsql reads TG_OP.
            sql = re.sub(
                r"(?i)\bUPDATING\s*\(\s*'(\w+)'\s*\)",
                r"(TG_OP = 'UPDATE' AND NEW.\1 IS DISTINCT FROM OLD.\1)",
                sql,
            )
            sql = re.sub(r"(?i)\bINSERTING\b", "(TG_OP = 'INSERT')", sql)
            sql = re.sub(r"(?i)\bUPDATING\b", "(TG_OP = 'UPDATE')", sql)
            sql = re.sub(r"(?i)\bDELETING\b", "(TG_OP = 'DELETE')", sql)
        # T-SQL ERROR_MESSAGE() inside a CATCH -> SQLERRM in the EXCEPTION
        # handler (parameterless; the empty parens would not parse).
        sql = re.sub(r"(?i)\bERROR_MESSAGE\s*\(\s*\)", "SQLERRM", sql)
        # dbo doesn't exist in PostgreSQL; drop a dbo. qualifier on calls.
        return re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)


register_transformer(PostgresTransformer.target_name, PostgresTransformer)
