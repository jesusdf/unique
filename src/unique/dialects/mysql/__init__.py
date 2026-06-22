# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""MySQL dialect plugin for Unique."""

import re

from unique.core.ast_nodes import ASTNode
from unique.core.converter import emit_sql, parse_sql
from unique.core.dialect import Dialect


class MySQLDialect(Dialect):
    """MySQL dialect implementation."""

    # The short column attribute "<type> BINARY" (a synonym for CHARACTER SET
    # binary) is not parsed by sqlglot and has no portable equivalent. Strip
    # it when it follows a character type, but never the BINARY(n) data type
    # or BINARY(expr) function call (those are followed by '(').
    _STRIP_BINARY_ATTR = re.compile(
        r"(?i)((?:VAR)?CHAR\s*\(\s*\d+\s*\))\s+BINARY\b(?!\s*\()"
    )

    @property
    def name(self) -> str:
        return "mysql"

    def parse(self, sql: str) -> list[ASTNode]:
        """Parse MySQL text into IR nodes."""
        sql = self._STRIP_BINARY_ATTR.sub(r"\1", sql)
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
