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

"""MySQL dialect plugin for Unique."""

from unique.core.ast_nodes import ASTNode
from unique.core.converter import emit_sql, parse_sql
from unique.core.dialect import Dialect


class MySQLDialect(Dialect):
    """MySQL dialect implementation."""

    @property
    def name(self) -> str:
        return "mysql"

    def parse(self, sql: str) -> list[ASTNode]:
        """Parse MySQL text into IR nodes."""
        return parse_sql(sql, "mysql")

    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as MySQL text."""
        return emit_sql(nodes, "mysql")

    def supported_features(self) -> set[str]:
        """Return features supported by MySQL."""
        return {
            "select",
            "insert",
            "update",
            "delete",
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
            "handler_error",
            "transactions",
            "variables",
            "if_else",
            "while_loop",
            "cursors",
            "dynamic_sql",
            "auto_increment",
            "triggers",
            "on_duplicate_key",
        }
