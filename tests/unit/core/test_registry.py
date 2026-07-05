"""Tests for the dialect registry."""

import pytest

from unique.core.errors import UnknownDialectError
from unique.core.registry import DialectRegistry


class TestDialectRegistry:
    def test_register_and_get(self) -> None:
        registry = DialectRegistry()
        from unique.dialects.tsql import TSQLDialect

        dialect = TSQLDialect()
        registry.register(dialect)
        assert registry.get("tsql") is dialect

    def test_get_unknown_raises(self) -> None:
        registry = DialectRegistry()
        with pytest.raises(UnknownDialectError, match="sqlite"):
            registry.get("sqlite")

    def test_available_lists_registered(self) -> None:
        registry = DialectRegistry()
        from unique.dialects.mysql import MySQLDialect
        from unique.dialects.tsql import TSQLDialect

        registry.register(TSQLDialect())
        registry.register(MySQLDialect())
        available = registry.available()
        assert available == ["mysql", "tsql"]

    def test_is_registered(self) -> None:
        registry = DialectRegistry()
        from unique.dialects.postgresql import PostgreSQLDialect

        registry.register(PostgreSQLDialect())
        assert registry.is_registered("postgresql") is True
        assert registry.is_registered("oracle") is False

    def test_with_builtins_loads_all_dialects(self) -> None:
        registry = DialectRegistry.with_builtins()
        available = registry.available()
        # Four full engines + SQLite (import-only source).
        assert len(available) == 5
        for name in ("tsql", "oracle", "postgresql", "mysql", "sqlite"):
            assert name in available
        # SQLite is a source-only dialect; the four servers are not.
        assert registry.get("sqlite").source_only
        assert not registry.get("postgresql").source_only

    def test_auto_discover(self) -> None:
        """auto_discover should find entry-point registered dialects."""
        registry = DialectRegistry.auto_discover()
        # Should find at least the 4 built-in dialects since
        # the package is installed in editable mode.
        assert len(registry.available()) >= 4
