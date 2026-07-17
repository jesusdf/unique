# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Main transpiler orchestrator: parse → transform → emit.

Supports two pipelines:
  1. DML/DDL pipeline: sqlglot-based parsing and emission.
  2. Procedural pipeline: custom lexer/parser for stored procedures,
     functions, triggers, and anonymous blocks.

The transpiler automatically routes each batch to the appropriate
pipeline based on content classification.
"""

from ._core import TranspileOptions, Transpiler, TranspileResult, transpile

__all__ = [
    "TranspileOptions",
    "TranspileResult",
    "Transpiler",
    "transpile",
]
