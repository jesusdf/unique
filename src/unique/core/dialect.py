# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Abstract dialect interface that all engine plugins must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

from unique.core.ast_nodes import ASTNode


class Dialect(ABC):
    """Base class for SQL dialect plugins.

    Each dialect provides a parser (SQL text → IR) and an emitter (IR → SQL text).
    Dialects are discovered via Python entry points and registered automatically.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this dialect (e.g. 'tsql', 'oracle')."""

    @property
    def source_only(self) -> bool:
        """Whether this dialect can only be a transpilation *source*, never a
        target (e.g. SQLite, which has no procedural language). Default: False."""
        return False

    @abstractmethod
    def parse(self, sql: str) -> list[ASTNode]:
        """Parse raw SQL text into a list of IR nodes.

        Args:
            sql: The source SQL text in this dialect's syntax.

        Returns:
            A list of ASTNode instances representing the parsed script.

        Raises:
            ParseError: If the SQL cannot be parsed.
        """

    @abstractmethod
    def emit(self, nodes: list[ASTNode]) -> str:
        """Emit IR nodes as SQL text in this dialect's syntax.

        Args:
            nodes: A list of ASTNode instances to convert to SQL.

        Returns:
            Formatted SQL text in this dialect's syntax.

        Raises:
            EmitError: If a node cannot be emitted.
        """

    @abstractmethod
    def supported_features(self) -> set[str]:
        """Return the set of feature tags this dialect supports.

        Feature tags are strings like 'cte', 'window_functions',
        'merge', 'recursive_cte', etc. They are used to determine
        whether a transpilation path is feasible.
        """
