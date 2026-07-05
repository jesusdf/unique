# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""SQLite dialect plugin — import-only.

SQLite is supported as a transpilation **source only** (SQLite → the four server
engines). It has no procedural language (no stored procedures/functions/anonymous
blocks), so it can never be a faithful procedural *target*; ``emit`` therefore
raises. Its DML/DDL surface is read via sqlglot and converted through the shared
IR like any other source.
"""

from __future__ import annotations

from unique.core.ast_nodes import ASTNode
from unique.core.converter import parse_sql
from unique.core.dialect import Dialect
from unique.core.errors import EmitError


class SQLiteDialect(Dialect):
    """SQLite dialect implementation (import-only)."""

    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def source_only(self) -> bool:
        return True

    def parse(self, sql: str) -> list[ASTNode]:
        """Parse SQLite text into IR nodes."""
        return parse_sql(sql, "sqlite")

    def emit(self, nodes: list[ASTNode]) -> str:
        """SQLite is import-only — it is never a transpilation target."""
        raise EmitError(
            "SQLite is supported as a source only (import-only); it cannot be a "
            "transpilation target."
        )

    def supported_features(self) -> set[str]:
        """SQLite's (source-side) feature surface — DML/DDL and simple triggers,
        no stored routines or procedural control flow."""
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
            "cte",
            "recursive_cte",
            "window_functions",
            "transactions",
            "triggers",
        }
