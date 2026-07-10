# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Recursive descent parser for procedural SQL.

Parses stored procedures, functions, and triggers into IR AST nodes;
embedded DML/DQL delegates to sqlglot. The statement families live in one
module each (audit 2026-07-02 doc 03: split along the dispatch seams):
``_base`` holds the shared machinery, ``_tsql`` and ``_plsql`` the
dialect-specific statement parsers, combined here into the public class.
"""

from __future__ import annotations

from unique.core.procedural.parser._base import ParseError, ParserBase, ParseResult
from unique.core.procedural.parser._plsql import PlsqlStatementsMixin
from unique.core.procedural.parser._tsql import TsqlStatementsMixin


class ProceduralParser(TsqlStatementsMixin, PlsqlStatementsMixin):
    """The procedural parser: shared base + both statement families."""


__all__ = [
    "ParseError",
    "ParseResult",
    "ParserBase",
    "PlsqlStatementsMixin",
    "ProceduralParser",
    "TsqlStatementsMixin",
]
