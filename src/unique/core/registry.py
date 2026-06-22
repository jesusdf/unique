# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Dialect registry with auto-discovery via Python entry points."""

from __future__ import annotations

import importlib.metadata
import logging

from unique.core.dialect import Dialect
from unique.core.errors import UnknownDialectError

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "unique.dialects"


class DialectRegistry:
    """Manages registration and lookup of SQL dialect plugins."""

    def __init__(self) -> None:
        self._dialects: dict[str, Dialect] = {}

    def register(self, dialect: Dialect) -> None:
        """Register a dialect instance.

        Args:
            dialect: A Dialect instance to register.
        """
        self._dialects[dialect.name] = dialect
        logger.debug("Registered dialect: %s", dialect.name)

    def get(self, name: str) -> Dialect:
        """Retrieve a registered dialect by name.

        Args:
            name: The dialect identifier (e.g. 'tsql', 'postgresql').

        Returns:
            The registered Dialect instance.

        Raises:
            UnknownDialectError: If no dialect with that name is registered.
        """
        if name not in self._dialects:
            raise UnknownDialectError(name)
        return self._dialects[name]

    def available(self) -> list[str]:
        """List all registered dialect names."""
        return sorted(self._dialects.keys())

    def is_registered(self, name: str) -> bool:
        """Check whether a dialect is registered."""
        return name in self._dialects

    @classmethod
    def auto_discover(cls) -> DialectRegistry:
        """Create a registry with all dialects found via entry points.

        Scans the 'unique.dialects' entry point group and instantiates
        each discovered dialect class.

        Returns:
            A populated DialectRegistry.
        """
        registry = cls()
        try:
            entry_points = importlib.metadata.entry_points()
            # Python 3.12+ EntryPoints supports .select(); '.get()' was removed.
            eps = entry_points.select(group=ENTRY_POINT_GROUP)

            for ep in eps:
                try:
                    dialect_class = ep.load()
                    dialect_instance = dialect_class()
                    registry.register(dialect_instance)
                except Exception:
                    logger.warning(
                        "Failed to load dialect from entry point: %s",
                        ep.name,
                        exc_info=True,
                    )
        except Exception:
            logger.warning("Entry point discovery failed", exc_info=True)

        return registry

    @classmethod
    def with_builtins(cls) -> DialectRegistry:
        """Create a registry with the four built-in dialects.

        This is a convenience method that directly imports the built-in
        dialect classes without relying on entry points. Useful for
        testing and when the package is not installed via pip.
        """
        registry = cls()

        from unique.dialects.mysql import MySQLDialect
        from unique.dialects.oracle import OracleDialect
        from unique.dialects.postgresql import PostgreSQLDialect
        from unique.dialects.tsql import TSQLDialect

        for dialect_cls in [
            TSQLDialect,
            OracleDialect,
            PostgreSQLDialect,
            MySQLDialect,
        ]:
            registry.register(dialect_cls())  # type: ignore[abstract]

        return registry
