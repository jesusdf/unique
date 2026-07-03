"""Pytest plugin: replace the transpiler with an identity function.

Used by scripts/identity_mutation_check.py to measure how many tests can
detect a completely broken transpiler (audit 2026-07-02). A translation
test that passes under this mutation verifies nothing about translation.

Usage: ``pytest tests/integration -p tests.mutation.identity_plugin``
"""

import pytest

from unique.core import transpiler as _transpiler_module


def _identity(self, sql, source, target, options=None):  # noqa: ANN001, ARG001
    return _transpiler_module.TranspileResult(sql=sql, warnings=[], unsupported=[])


@pytest.fixture(autouse=True)
def _identity_transpiler(monkeypatch):  # noqa: ANN001
    monkeypatch.setattr(_transpiler_module.Transpiler, "transpile", _identity)
