"""Shared fixtures for the Unique test suite."""

import pytest

from unique.core.registry import DialectRegistry
from unique.core.transpiler import Transpiler


@pytest.fixture
def registry() -> DialectRegistry:
    """Return a registry loaded with all built-in dialects."""
    return DialectRegistry.with_builtins()


@pytest.fixture
def transpiler(registry: DialectRegistry) -> Transpiler:
    """Return a Transpiler ready to use."""
    return Transpiler(registry=registry)
