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
import re
from dataclasses import dataclass, field

from unique.core.batch_splitter import BatchSplitter, BatchType
from unique.core.dialect import Dialect
from unique.core.procedural.emitter import ProceduralEmitter
from unique.core.procedural.parser import ProceduralParser
from unique.core.procedural.transformer import ProceduralTransformer
from unique.core.registry import DialectRegistry
from unique.core.transformer import Transformer, TransformWarning

logger = logging.getLogger(__name__)

# T-SQL DDL guard: "IF OBJECT_ID(...) IS NULL CREATE TABLE/INDEX ..."
# The guard is T-SQL-only idiom; for other targets we drop it and emit
# only the CREATE statement (CREATE TABLE IF NOT EXISTS is used where supported;
# for Oracle pre-23c we just emit CREATE TABLE since the fixture starts fresh).
_TSQL_DDL_GUARD_RE = re.compile(
    r"(?s)^(?:--[^\n]*\n\s*)*"
    r"IF\s+(?:OBJECT_ID|EXISTS)\s*\([^)]+\)\s*IS\s+NULL\s+"
    r"(CREATE\s+(?:TABLE|(?:UNIQUE\s+)?INDEX)\b.*)",
    re.IGNORECASE,
)

# A MySQL routine whose body contains ';' statement terminators must be wrapped
# in a DELIMITER block so a client doesn't cut the script at the first inner
# ';'. Matches the leading keyword of a compound routine definition (any
# leading line comments are allowed before it).
_MYSQL_ROUTINE_RE = re.compile(
    r"(?s)^(?:\s*--[^\n]*\n)*\s*" r"CREATE\s+(?:PROCEDURE|FUNCTION|TRIGGER)\b",
    re.IGNORECASE,
)


def _warn(message: str, feature: str, source: str, target: str) -> TransformWarning:
    """Build a TransformWarning with dialect context."""
    return TransformWarning(
        message=message,
        feature=feature,
        source_dialect=source,
        target_dialect=target,
    )


def _is_comment_only(sql: str) -> bool:
    """Whether ``sql`` consists solely of blank lines and ``--`` comments."""
    stripped = sql.strip()
    if not stripped:
        return False
    return all(
        not line.strip() or line.lstrip().startswith("--")
        for line in stripped.splitlines()
    )


def _extract_tsql_output(sql: str) -> tuple[str, str | None]:
    """Extract a T-SQL OUTPUT clause from a single DML statement.

    Returns ``(base_sql_without_output, output_columns)`` or
    ``(sql, None)`` if there is no OUTPUT clause. The OUTPUT clause in T-SQL
    appears after the target/SET list and before WHERE/VALUES/FROM, so it is
    removed in place, preserving the rest of the statement (crucially the
    WHERE clause, whose loss would change DELETE/UPDATE semantics).

    Only the simple ``OUTPUT <cols>`` form is handled (not ``OUTPUT ... INTO
    <table>``); the latter returns ``(sql, None)`` so it is left untouched.
    """
    # OUTPUT ... INTO is a different construct (insert into a target table);
    # do not treat it as a returning clause.
    if re.search(r"(?i)\bOUTPUT\b.*\bINTO\b", sql):
        return sql, None
    m = re.search(r"(?i)\bOUTPUT\b\s+(.*?)(?=\s+\b(?:WHERE|VALUES|FROM)\b|;|$)", sql)
    if not m:
        return sql, None
    output_cols = m.group(1).strip()
    if not output_cols:
        return sql, None
    base = (sql[: m.start()].rstrip() + " " + sql[m.end() :].lstrip()).strip()
    return base, output_cols


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
            output_parts: list[tuple[str, bool]] = []  # (sql, is_comment)

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
                    # T-SQL DDL guards (IF OBJECT_ID() IS NULL CREATE TABLE ...)
                    # are not SET options — extract the DDL and transpile it.
                    ddl_match = (
                        _TSQL_DDL_GUARD_RE.match(batch.sql)
                        if source == "tsql" and target != "tsql"
                        else None
                    )
                    if ddl_match:
                        result = self._transpile_dml(
                            ddl_match.group(1),
                            source,
                            target,
                            source_dialect,
                            target_dialect,
                        )
                    else:
                        result = self._transpile_set_option(batch.sql, source, target)
                elif batch.batch_type == BatchType.COMMENT:
                    # Comments carry no executable SQL; preserve them verbatim
                    # (already normalized to '-- ...' line comments).
                    result = TranspileResult(sql=batch.sql, warnings=[], unsupported=[])
                else:
                    result = self._transpile_dml(
                        batch.sql, source, target, source_dialect, target_dialect
                    )

                terminated = self._ensure_terminated(
                    result.sql, target, batch.batch_type
                )
                if target == "mysql":
                    terminated = self._wrap_mysql_routine(terminated)
                # Treat output that is *entirely* comments as a comment part,
                # even if the batch wasn't classified as COMMENT (e.g. an
                # unsupported SET we turned into a '-- ...' note). This avoids
                # emitting a GO/';' separator after a pure comment.
                is_comment = batch.batch_type == BatchType.COMMENT or _is_comment_only(
                    terminated
                )
                output_parts.append((terminated, is_comment))
                all_warnings.extend(result.warnings)
                all_unsupported.extend(result.unsupported)

            output_sql = self._join_parts(output_parts, target)

            return TranspileResult(
                sql=output_sql,
                warnings=all_warnings,
                unsupported=all_unsupported,
            )
        finally:
            if metadata_resolver:
                metadata_resolver.close()

    def _join_parts(self, parts: list[tuple[str, bool]], target: str) -> str:
        """Join emitted parts, choosing the right delimiter between each pair.

        A comment part is attached to what follows with a plain newline rather
        than the batch separator, so we don't emit a useless ``GO`` (T-SQL) or
        ``/`` (Oracle) after a comment. The batch separator is only used
        between two executable parts.
        """
        if not parts:
            return ""
        separator = self._get_batch_separator(target)
        out = parts[0][0]
        for i in range(1, len(parts)):
            prev_is_comment = parts[i - 1][1]
            text, _ = parts[i]
            if prev_is_comment:
                # Glue the comment to the following part with a newline.
                out = out.rstrip("\n") + "\n" + text
            else:
                out += separator + text
        return out

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

        # System stored-procedure calls (e.g. EXEC sp_addextendedproperty,
        # sp_rename) are SQL Server metadata operations with no portable
        # equivalent. Emit them as an informational comment instead of
        # letting sqlglot fail on the proprietary syntax.
        if source == "tsql" and target != "tsql":
            stripped = sql.lstrip()
            m = re.match(r"(?i)^EXEC(?:UTE)?\s+(?:\[?\w+\]?\.)*\[?(sp_\w+)", stripped)
            if m:
                proc = m.group(1)
                unsupported.append(f"System procedure {proc} has no equivalent")
                return TranspileResult(
                    sql=(
                        f"-- UNIQUE: {proc} is a SQL Server system procedure "
                        f"with no {target} equivalent; original call omitted:\n"
                        + "\n".join(f"-- {ln}" for ln in sql.strip().splitlines())
                    ),
                    warnings=[
                        _warn(
                            f"System procedure {proc} skipped (no {target} "
                            "equivalent)",
                            "system_proc",
                            source,
                            target,
                        )
                    ],
                    unsupported=unsupported,
                )

        # T-SQL OUTPUT clause: sqlglot cannot parse it on DELETE/UPDATE (it
        # sits before WHERE) and would drop the rest of the statement,
        # including the WHERE — a dangerous data-loss bug. Extract it safely,
        # transpile the base statement, then re-attach as RETURNING
        # (PostgreSQL/Oracle) or a documented comment (MySQL, which lacks it).
        if source == "tsql":
            base_sql, output_cols = _extract_tsql_output(sql)
            if output_cols is not None:
                base_result = self._transpile_dml(
                    base_sql, source, target, source_dialect, target_dialect
                )
                # Map the OUTPUT columns (strip INSERTED./DELETED. prefixes).
                cols = re.sub(r"(?i)\b(INSERTED|DELETED)\.", "", output_cols).strip()
                body = base_result.sql.rstrip().rstrip(";")
                if target in ("postgresql", "oracle"):
                    new_sql = f"{body} RETURNING {cols}"
                else:  # mysql: no RETURNING/OUTPUT
                    new_sql = (
                        f"{body}\n-- UNIQUE: MySQL has no OUTPUT/RETURNING; "
                        f"the statement returned: {cols}"
                    )
                return TranspileResult(
                    sql=new_sql,
                    warnings=base_result.warnings,
                    unsupported=base_result.unsupported,
                )

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
            commented = "\n".join(
                f"-- {line}" if line.strip() else ""
                for line in sql.strip().splitlines()
            )
            return TranspileResult(
                sql=commented,
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
    def _ensure_terminated(sql: str, target: str, batch_type: BatchType) -> str:
        """Ensure an emitted statement is properly delimited for re-parsing.

        For PostgreSQL/MySQL/Oracle the statement terminator is ``;`` and we
        append one when missing so the output stays re-parseable (round-trips,
        downstream tools).

        For T-SQL the batch separator ``GO`` does that job, and idiomatic
        T-SQL does not terminate statements with ``;`` (it is only required in
        specific cases such as before a CTE's ``WITH``). Appending ``;`` here
        would produce ``... ;`` followed by ``GO`` -- noisy and non-idiomatic,
        and harmful after an ``IF`` guard, whose scope is a single statement.
        So for T-SQL we leave the statement unterminated.
        """
        if target == "tsql":
            return sql
        stripped = sql.rstrip()
        if not stripped:
            return sql
        lines = stripped.splitlines()
        # Pure comment output: do not append a semicolon.
        if all(not line.strip() or line.lstrip().startswith("--") for line in lines):
            return sql
        # Trailing explanatory comments may follow the statement (e.g. a
        # documented unsupported generated column). Find the last line that
        # isn't a comment and terminate there, leaving the comments after it.
        last_code_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() and not lines[i].lstrip().startswith("--"):
                last_code_idx = i
                break
        if last_code_idx is None:
            return sql
        if lines[last_code_idx].rstrip().endswith(";"):
            return sql
        lines[last_code_idx] = lines[last_code_idx].rstrip() + ";"
        return "\n".join(lines)

    @staticmethod
    def _wrap_mysql_routine(sql: str) -> str:
        """Wrap a MySQL compound routine in a DELIMITER block.

        MySQL stored routines contain ``;`` statement terminators inside their
        body. A client that uses ``;`` as the statement delimiter would cut the
        definition at the first inner ``;``, so the routine must be wrapped::

            DELIMITER $$
            CREATE PROCEDURE ... BEGIN ... END$$
            DELIMITER ;

        Any leading line comments are kept above the ``DELIMITER $$`` line so
        they remain associated with the routine. Non-routine statements are
        returned unchanged.
        """
        if not _MYSQL_ROUTINE_RE.match(sql):
            return sql

        lines = sql.splitlines()
        # Separate any leading comment lines from the routine body.
        head: list[str] = []
        idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("--") or not line.strip():
                head.append(line)
                idx = i + 1
            else:
                break
        body = "\n".join(lines[idx:]).rstrip()
        # The body was terminated with ';' by _ensure_terminated; swap that
        # trailing ';' for the '$$' routine delimiter.
        if body.endswith(";"):
            body = body[:-1].rstrip()
        wrapped = f"DELIMITER $$\n{body}$$\nDELIMITER ;"
        if head:
            # Drop a trailing blank line in the comment head for tidiness.
            while head and not head[-1].strip():
                head.pop()
            return "\n".join(head + [wrapped]) if head else wrapped
        return wrapped

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
