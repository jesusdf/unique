# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Oracle dialect plugin for Unique."""

from unique.core.ast_nodes import ASTNode
from unique.core.converter import emit_sql, parse_sql
from unique.core.dialect import Dialect


class OracleDialect(Dialect):
    """Oracle dialect implementation."""

    @property
    def name(self) -> str:
        return "oracle"

    def parse(self, sql: str) -> list[ASTNode]:
        """Parse Oracle SQL text into IR nodes."""
        return parse_sql(sql, "oracle")

    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as Oracle SQL text."""
        return emit_sql(nodes, "oracle")

    def supported_features(self) -> set[str]:
        """Return features supported by Oracle."""
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
            "rownum",
            "fetch_first",
            "packages",
            "overloading",
            "exception_handling",
            "transactions",
            "variables",
            "if_else",
            "while_loop",
            "for_loop",
            "cursors",
            "ref_cursors",
            "dynamic_sql",
            "identity",
            "sequences",
            "triggers",
            "materialized_views",
            "connect_by",
        }
