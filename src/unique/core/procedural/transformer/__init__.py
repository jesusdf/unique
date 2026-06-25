# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer package.

``ProceduralTransformer(source, target)`` returns the per-target transformer
subclass for the target dialect. Each target lives in its own module
({tsql,oracle,postgresql,mysql}.py) and registers itself on import; importing
this package imports them all so the registry is populated. Adding a new engine
means adding one module and one import line here — no change to the shared
transform logic.
"""

from __future__ import annotations

from unique.core.procedural.transformer.base import ProceduralTransformer

# Importing the engine modules registers each subclass in the base registry.
from unique.core.procedural.transformer.mysql import MySqlTransformer
from unique.core.procedural.transformer.oracle import OracleTransformer
from unique.core.procedural.transformer.postgresql import PostgresTransformer
from unique.core.procedural.transformer.tsql import TSqlTransformer

__all__ = [
    "ProceduralTransformer",
    "TSqlTransformer",
    "OracleTransformer",
    "PostgresTransformer",
    "MySqlTransformer",
]
