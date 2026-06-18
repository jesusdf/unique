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

"""Main transpiler orchestrator: parse → transform → emit.

Supports two pipelines:
  1. DML/DDL pipeline: sqlglot-based parsing and emission.
  2. Procedural pipeline: custom lexer/parser for stored procedures,
     functions, triggers, and anonymous blocks.

The transpiler automatically routes each batch to the appropriate
pipeline based on content classification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from unique.core.batch_splitter import BatchSplitter, BatchType
from unique.core.dialect import Dialect
from unique.core.procedural.emitter import ProceduralEmitter
from unique.core.procedural.parser import ProceduralParser
from unique.core.procedural.transformer import ProceduralTransformer
from unique.core.registry import DialectRegistry
from unique.core.transformer import Transformer, TransformWarning

logger = logging.getLogger(__name__)


def _warn(message: str, feature: str, source: str, target: str) -> TransformWarning:
    """Build a TransformWarning with dialect context."""
    return TransformWarning(
        message=message,
        feature=feature,
        source_dialect=source,
        target_dialect=target,
    )


@dataclass(frozen=True)
class TranspileOptions:
    """Options controlling transpilation behavior."""

    preserve_comments: bool = True
    include_warnings: bool = True
    format_output: bool = True
    db_url: str | None = None


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
    0. Split input into batches using dialect-specific separators.
    1. Classify each batch as procedural or DML/DDL.
    2. Route procedural batches through the procedural engine.
    3. Route DML/DDL batches through the sqlglot-based pipeline.
    4. Join results into a single output script.
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

        # Validate dialects
        source_dialect = self.registry.get(source)
        target_dialect = self.registry.get(target)

        logger.info("Transpiling from %s to %s", source, target)

        # Optional metadata resolver for %TYPE references
        metadata_resolver = None
        if options.db_url:
            try:
                from unique.core.metadata import MetadataResolver

                metadata_resolver = MetadataResolver.from_url(options.db_url)
                logger.info("Connected to metadata database")
            except Exception as e:
                logger.warning("Could not connect to metadata database: %s", e)

        try:
            # Step 0: Split into batches
            batches = BatchSplitter.split(sql, source)
            logger.debug("Split into %d batches", len(batches))

            all_warnings: list[TransformWarning] = []
            all_unsupported: list[str] = []
            output_parts: list[str] = []

            for batch in batches:
                # Skip empty batches, but keep explicit COMMENT batches: they
                # have no executable SQL yet carry information worth preserving
                # (e.g. Oracle 'rem'/'prompt' notices) in the output.
                if batch.is_empty and batch.batch_type != BatchType.COMMENT:
                    continue

                if batch.batch_type == BatchType.PROCEDURAL:
                    result = self._transpile_procedural(
                        batch.sql, source, target, metadata_resolver
                    )
                elif batch.batch_type == BatchType.SET_OPTION:
                    result = self._transpile_set_option(batch.sql, source, target)
                elif batch.batch_type == BatchType.COMMENT:
                    # Comments carry no executable SQL; preserve them verbatim
                    # (already normalized to '-- ...' line comments).
                    result = TranspileResult(sql=batch.sql, warnings=[], unsupported=[])
                else:
                    result = self._transpile_dml(
                        batch.sql, source, target, source_dialect, target_dialect
                    )

                output_parts.append(result.sql)
                all_warnings.extend(result.warnings)
                all_unsupported.extend(result.unsupported)

            # Join with appropriate separator
            separator = self._get_batch_separator(target)
            output_sql = separator.join(output_parts)

            return TranspileResult(
                sql=output_sql,
                warnings=all_warnings,
                unsupported=all_unsupported,
            )
        finally:
            if metadata_resolver:
                metadata_resolver.close()

    def _transpile_procedural(
        self,
        sql: str,
        source: str,
        target: str,
        metadata_resolver: object | None = None,
    ) -> TranspileResult:
        """Transpile a procedural batch through the procedural engine."""
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        try:
            # Parse
            parser = ProceduralParser(source)
            parse_result = parser.parse(sql)

            if parse_result.errors:
                for err in parse_result.errors:
                    warnings.append(
                        _warn(
                            f"Parse error: {err.message}",
                            "procedural_parse",
                            source,
                            target,
                        )
                    )

            if parse_result.warnings:
                for w in parse_result.warnings:
                    warnings.append(_warn(w, "procedural_parse", source, target))

            if parse_result.node is None:
                return TranspileResult(
                    sql=f"/* PARSE ERROR */\n{sql}",
                    warnings=warnings,
                    unsupported=unsupported,
                )

            # Transform
            if source != target:
                transformer = ProceduralTransformer(source, target, metadata_resolver)
                node = transformer.transform(parse_result.node)
                for w in transformer.warnings:
                    warnings.append(_warn(w, "procedural_transform", source, target))
            else:
                node = parse_result.node

            # Emit
            emitter = ProceduralEmitter(target)
            output_sql = emitter.emit(node)

            return TranspileResult(
                sql=output_sql,
                warnings=warnings,
                unsupported=unsupported,
            )

        except Exception as e:
            logger.warning("Procedural transpilation failed: %s", e)
            warnings.append(
                _warn(
                    f"Procedural transpilation failed: {e}",
                    "procedural",
                    source,
                    target,
                )
            )
            return TranspileResult(
                sql=f"/* TRANSPILATION ERROR: {e} */\n{sql}",
                warnings=warnings,
                unsupported=unsupported,
            )

    def _transpile_dml(
        self,
        sql: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> TranspileResult:
        """Transpile a DML/DDL batch through the sqlglot pipeline."""
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        try:
            ir_nodes = source_dialect.parse(sql)

            if source != target:
                transformer = Transformer(source, target)
                ir_nodes = transformer.transform(ir_nodes)
                warnings = transformer.warnings
                unsupported = transformer.unsupported

            output_sql = target_dialect.emit(ir_nodes)

            return TranspileResult(
                sql=output_sql,
                warnings=warnings,
                unsupported=unsupported,
            )
        except Exception as e:
            logger.warning("DML transpilation failed: %s", e)
            warnings.append(
                _warn(f"DML transpilation failed: {e}", "dml", source, target)
            )
            return TranspileResult(
                sql=f"/* TRANSPILATION ERROR: {e} */\n{sql}",
                warnings=warnings,
                unsupported=unsupported,
            )

    def _transpile_set_option(
        self, sql: str, source: str, target: str
    ) -> TranspileResult:
        """Handle SET options like SET NOCOUNT ON."""
        if source == "tsql" and target != "tsql":
            return TranspileResult(
                sql=f"-- {sql.strip()}",
                warnings=[
                    _warn(
                        f"SET option commented out: {sql.strip()[:60]}",
                        "set_option",
                        source,
                        target,
                    )
                ],
            )
        return TranspileResult(sql=sql)

    @staticmethod
    def _get_batch_separator(target: str) -> str:
        """Get the batch separator for a target dialect."""
        separators = {
            "tsql": "\nGO\n\n",
            "oracle": "\n/\n\n",
            "postgresql": "\n\n",
            "mysql": "\n\n",
        }
        return separators.get(target, "\n\n")

    def available_dialects(self) -> list[str]:
        """List all available dialect names."""
        return self.registry.available()


def transpile(
    sql: str,
    source: str,
    target: str,
    db_url: str | None = None,
) -> TranspileResult:
    """Convenience function for one-shot transpilation.

    Args:
        sql: The source SQL text.
        source: The source dialect name.
        target: The target dialect name.
        db_url: Optional database connection URL for metadata resolution.

    Returns:
        A TranspileResult.
    """
    options = TranspileOptions(db_url=db_url)
    return Transpiler().transpile(sql, source, target, options)
