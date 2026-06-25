# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter package.

``ProceduralEmitter(dialect)`` returns the per-engine emitter subclass for the
target dialect. Each engine lives in its own module ({tsql,oracle,postgresql,
mysql}.py) and registers itself on import; importing this package imports them
all so the registry is populated. Adding a new engine means adding one module
and one import line here — no change to the core emission logic.
"""

from __future__ import annotations

from unique.core.procedural.emitter.base import ProceduralEmitter

# Importing the engine modules registers each subclass in the base registry.
from unique.core.procedural.emitter.mysql import MySqlEmitter
from unique.core.procedural.emitter.oracle import OracleEmitter
from unique.core.procedural.emitter.postgresql import PostgresEmitter
from unique.core.procedural.emitter.tsql import TSqlEmitter

__all__ = [
    "ProceduralEmitter",
    "TSqlEmitter",
    "OracleEmitter",
    "PostgresEmitter",
    "MySqlEmitter",
]
