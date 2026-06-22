# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""PostgreSQL dialect plugin for Unique."""

from unique.core.ast_nodes import ASTNode
from unique.core.converter import emit_sql, parse_sql
from unique.core.dialect import Dialect


class PostgreSQLDialect(Dialect):
    """PostgreSQL dialect implementation."""

    @property
    def name(self) -> str:
        return "postgresql"

    def parse(self, sql: str) -> list[ASTNode]:
        """Parse PostgreSQL text into IR nodes."""
        return parse_sql(sql, "postgresql")

    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as PostgreSQL text."""
        return emit_sql(nodes, "postgresql")

    def supported_features(self) -> set[str]:
        """Return features supported by PostgreSQL."""
        return {
            "select",
            "insert",
            "update",
            "delete",
            "merge",
            "create_table",
            "alter_table",
            "drop",
            "create_view",
            "create_index",
            "create_procedure",
            "create_function",
            "cte",
            "recursive_cte",
            "window_functions",
            "limit_offset",
            "fetch_first",
            "lateral_join",
            "exception_handling",
            "transactions",
            "variables",
            "if_else",
            "while_loop",
            "for_loop",
            "cursors",
            "ref_cursors",
            "dynamic_sql",
            "serial",
            "sequences",
            "triggers",
            "materialized_views",
            "returning_clause",
            "on_conflict",
        }
