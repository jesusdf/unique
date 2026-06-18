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

"""T-SQL (SQL Server) dialect plugin for Unique."""

import re

from unique.core.ast_nodes import ASTNode
from unique.core.converter import emit_sql, parse_sql
from unique.core.dialect import Dialect


class TSQLDialect(Dialect):
    """SQL Server (T-SQL) dialect implementation."""

    # Proprietary T-SQL column attributes that sqlglot cannot parse and that
    # have no equivalent in other engines. Stripping them lets the rest of
    # the CREATE TABLE parse cleanly. (ROWGUIDCOL marks a GUID column for
    # merge replication; NOT FOR REPLICATION suppresses identity/constraint
    # behavior during replication.)
    _STRIP_ATTRS = re.compile(r"(?i)\s+(ROWGUIDCOL|NOT\s+FOR\s+REPLICATION)\b")

    @property
    def name(self) -> str:
        return "tsql"

    def parse(self, sql: str) -> list[ASTNode]:
        """Parse T-SQL text into IR nodes."""
        sql = self._STRIP_ATTRS.sub("", sql)
        return parse_sql(sql, "tsql")

    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as T-SQL text."""
        return emit_sql(nodes, "tsql")

    def supported_features(self) -> set[str]:
        """Return features supported by T-SQL."""
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
            "top",
            "offset_fetch",
            "cross_apply",
            "outer_apply",
            "try_catch",
            "transactions",
            "variables",
            "if_else",
            "while_loop",
            "cursors",
            "dynamic_sql",
            "identity",
            "sequences",
            "triggers",
        }
