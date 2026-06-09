# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Main transpiler orchestrator: parse → transform → emit."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from unique.core.registry import DialectRegistry
from unique.core.transformer import Transformer, TransformWarning

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranspileOptions:
    """Options controlling transpilation behavior."""

    preserve_comments: bool = True
    include_warnings: bool = True
    format_output: bool = True


@dataclass
class TranspileResult:
    """Result of a transpilation operation."""

    sql: str
    warnings: list[TransformWarning] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        """Whether the result includes any warnings."""
        return len(self.warnings) > 0

    @property
    def has_unsupported(self) -> bool:
        """Whether any features were unsupported."""
        return len(self.unsupported) > 0


class Transpiler:
    """Orchestrates SQL transpilation between dialects.

    The transpilation pipeline:
    1. Parse source SQL into IR nodes using the source dialect.
    2. Transform IR nodes to normalize dialect-specific constructs.
    3. Emit target SQL from the transformed IR using the target dialect.
    """

    def __init__(self, registry: DialectRegistry | None = None) -> None:
        """Initialize the transpiler.

        Args:
            registry: A DialectRegistry to use. If None, auto-discovers
                      built-in dialects.
        """
        self.registry = registry or DialectRegistry.with_builtins()

    def transpile(
        self,
        sql: str,
        source: str,
        target: str,
        options: TranspileOptions | None = None,
    ) -> TranspileResult:
        """Transpile SQL from one dialect to another.

        Args:
            sql: The source SQL text.
            source: The source dialect name (e.g. 'tsql').
            target: The target dialect name (e.g. 'postgresql').
            options: Optional transpilation options.

        Returns:
            A TranspileResult with the target SQL, warnings, and
            unsupported feature list.

        Raises:
            UnknownDialectError: If source or target dialect is not registered.
            ParseError: If the source SQL cannot be parsed.
            EmitError: If the IR cannot be emitted as the target dialect.
        """
        options = options or TranspileOptions()

        source_dialect = self.registry.get(source)
        target_dialect = self.registry.get(target)

        logger.info("Transpiling from %s to %s", source, target)

        # Step 1: Parse
        ir_nodes = source_dialect.parse(sql)
        logger.debug("Parsed %d IR nodes", len(ir_nodes))

        # Step 2: Transform (skip if source == target)
        if source != target:
            transformer = Transformer(source, target)
            ir_nodes = transformer.transform(ir_nodes)
            warnings = transformer.warnings
            unsupported = transformer.unsupported
        else:
            warnings = []
            unsupported = []

        # Step 3: Emit
        output_sql = target_dialect.emit(ir_nodes)
        logger.debug("Emitted %d characters of SQL", len(output_sql))

        return TranspileResult(
            sql=output_sql,
            warnings=warnings,
            unsupported=unsupported,
        )

    def available_dialects(self) -> list[str]:
        """List all available dialect names."""
        return self.registry.available()


def transpile(sql: str, source: str, target: str) -> TranspileResult:
    """Convenience function for one-shot transpilation.

    Args:
        sql: The source SQL text.
        source: The source dialect name.
        target: The target dialect name.

    Returns:
        A TranspileResult.
    """
    return Transpiler().transpile(sql, source, target)
