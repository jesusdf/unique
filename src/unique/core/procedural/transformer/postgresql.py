# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — postgresql target."""

from __future__ import annotations

import dataclasses
import re

from unique.core.ast_nodes import (
    ASTNode,
    DataType,
    DeclareStatement,
    EmbeddedDML,
    ForLoopStatement,
    RawSQL,
    StatementList,
)
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
        result = self._rename_shadowed_loop_var(result)
        if (
            isinstance(result, ForLoopStatement)
            and result.cursor is not None
            and result.variable.lower() not in self._declared_loop_records
        ):
            # plpgsql requires the row-loop variable to be *declared* (only
            # integer range loops auto-declare); PL/SQL declares it
            # implicitly. Emit a record declaration — the emitter hoists it
            # into the DECLARE section.
            self._declared_loop_records.add(result.variable.lower())
            return StatementList(
                statements=(
                    DeclareStatement(
                        name=result.variable, data_type=DataType(name="record")
                    ),
                    result,
                )
            )
        return result

    @property
    def _declared_loop_records(self) -> set[str]:
        if not hasattr(self, "_declared_loop_records_"):
            self._declared_loop_records_: set[str] = set()
        return self._declared_loop_records_

    def _rename_shadowed_loop_var(self, result: ASTNode) -> ASTNode:
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
                reverse=result.reverse,
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
        sql = self._rewrite_alter_trigger(sql)
        sql = self._map_oracle_catalogs(sql)
        sql = self._pg_string_concat(sql)
        sql = self._pg_clean_dml(sql)
        return sql

    def _update_predicate(self, col: str) -> str | None:
        return f"(NEW.{col} IS DISTINCT FROM OLD.{col})"

    def _map_oracle_catalogs(self, sql: str) -> str:
        """Oracle user_* catalog probes -> information_schema (found live:
        column-existence guards). Unquoted Oracle identifiers are stored
        uppercase but PostgreSQL folds to lowercase — compare case-folded."""
        if self._source != "oracle" or not re.search(
            r"(?i)\buser_tab_col(?:umn)?s\b|\buser_tables\b", sql
        ):
            return sql
        sql = re.sub(
            r"(?i)\buser_tab_col(?:umn)?s\b", "information_schema.columns", sql
        )
        sql = re.sub(r"(?i)\buser_tables\b", "information_schema.tables", sql)
        sql = re.sub(
            r"(?i)\b(table_name|column_name)\s*=\s*('(?:[^']|'')*')",
            lambda m: f"{m.group(1)} = lower({m.group(2)})",
            sql,
        )
        return sql

    _ALTER_TRIGGER_RE = re.compile(
        r"(?is)^\s*ALTER\s+TRIGGER\s+([\w\"]+)\s+(ENABLE|DISABLE)\s*;?\s*$"
    )

    def _rewrite_alter_trigger(self, sql: str) -> str:
        """Oracle's ALTER TRIGGER x ENABLE names only the trigger; PostgreSQL
        needs the table (ALTER TABLE t ENABLE TRIGGER x) — resolved from
        pg_trigger at run time; a missing trigger degrades to a no-op."""
        m = self._ALTER_TRIGGER_RE.match(sql)
        if not m or self._source == self._target:
            return sql
        name, action = m.group(1).strip('"'), m.group(2).upper()
        return (
            "EXECUTE COALESCE((SELECT format("
            f"'ALTER TABLE %s {action} TRIGGER %I', tgrelid::regclass, tgname)"
            f" FROM pg_trigger WHERE tgname = lower('{name}')"
            " AND NOT tgisinternal LIMIT 1), 'SELECT 1');"
        )

    def _fix_select_into_rest(self, sql: str) -> str:
        return self._map_oracle_catalogs(sql)

    def _fix_raw_sql_target(self, sql: str) -> str:
        from unique.core.converter import map_sequence_refs

        sql = map_sequence_refs(sql, "postgresql")
        sql = self._rewrite_alter_trigger(sql)
        sql = self._map_oracle_catalogs(sql)
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
