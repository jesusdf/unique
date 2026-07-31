# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""The transpile orchestrator: split -> classify -> route -> join.

``Transpiler`` and its options/result types. Text-level batch rules live in
``_text_rules.py``; this module hosts the pipeline orchestration only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import SqlglotError as _SqlglotError

from unique.core.ast_nodes import (
    CommentStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
)
from unique.core.batch_splitter import _TSQL_SYSTEM_PROCS, BatchSplitter, BatchType
from unique.core.converter import (
    COLUMN_NOT_NULL,
    COLUMN_TYPES,
    DATE_COLUMNS,
    DEGRADED_ROUTINES,
    ENUM_COLUMNS,
    IDENTITY_COLUMNS,
    PG_COMPOSITE_TYPES,
    PG_DOMAIN_TYPES,
    PG_TRIGGER_FN_BODIES,
    PK_UNIQUE_COLUMNS,
    PROC_DATE_PARAMS,
    REFCURSOR_PROCS,
    SOURCE_DIALECT,
    TEMP_TABLES,
    TSQL_ALIAS_TYPES,
    TSQL_BIT_COLUMNS,
    USER_FUNCTIONS,
    harvest_column_not_null,
    harvest_column_types,
    harvest_date_columns,
    harvest_enum_columns,
    harvest_identity_columns,
    harvest_pg_composite_types,
    harvest_pg_domains,
    harvest_pg_trigger_functions,
    harvest_pk_unique_columns,
    harvest_proc_date_params,
    harvest_temp_tables,
    harvest_tsql_alias_types,
    harvest_tsql_bit_columns,
    harvest_user_functions,
    rewrite_oracle_modify,
)
from unique.core.converter._unread_args import WARNING_FEATURE as _UNREAD_FEATURE
from unique.core.converter._unread_args import drain_sink as _drain_unread_arg_sink
from unique.core.converter._unread_args import reset_sink as _reset_unread_arg_sink
from unique.core.dialect import Dialect
from unique.core.errors import UnsupportedFeatureError
from unique.core.output_gate import (
    _SQLGLOT_DIALECT,
    annotate_divergence,
    degrade_to_carrier,
    gate_reason,
)
from unique.core.procedural.emitter import ProceduralEmitter
from unique.core.procedural.parser import PARSE_FALLBACK_WARNING, ProceduralParser
from unique.core.procedural.transformer import ProceduralTransformer
from unique.core.registry import DialectRegistry
from unique.core.sql_split import split_leading_trivia, split_statements
from unique.core.transformer import Transformer, TransformWarning

from ._text_rules import (  # noqa: F401
    _DROP_STMT_RE,
    _MYSQL_ROUTINE_RE,
    _ORACLE_ALTER_DEFAULT_RE,
    _QI_OFF_RE,
    _QI_ON_RE,
    _ROUTINE_COMMENT_TARGETS,
    _TSQL_ALTER_COLUMN_RE,
    _TSQL_CREATE_SCHEMA_RE,
    _aggregate_warnings,
    _carrier_fragments,
    _covering_warnings,
    _double_quoted_to_strings,
    _expand_tsql_compound_assignment,
    _extract_catalog_guard,
    _extract_tsql_output,
    _harvest_split_tvf_names,
    _is_comment_only,
    _leading_comment_nodes,
    _mysql_safe_comments,
    _normalize_oracle_multicolumn_drop,
    _oracle_idempotent_create,
    _oracle_needs_slash,
    _parses_in_target,
    _qualify_tsql_udfs_in_sql,
    _rewrite_sqlite_functions,
    _rewrite_tsql_constraint_state,
    _rewrite_tsql_default_constraint,
    _rewrite_tvf_callers,
    _statement_is_merge,
    _warn,
    _warning_covers,
)

logger = logging.getLogger(__name__)

#: A routine-definition head (``CREATE [OR REPLACE|OR ALTER] PROCEDURE|FUNCTION|
#: TRIGGER`` or T-SQL ``ALTER PROCEDURE|FUNCTION``). Matched against the
#: trivia-stripped code of a single statement to tell the routine apart from a
#: companion DDL statement that the batch splitter folded ahead of it.
_ROUTINE_HEAD_RE = re.compile(
    r"(?i)^\s*(?:CREATE(?:\s+OR\s+(?:REPLACE|ALTER))?|ALTER)\s+"
    r"(?:PROC(?:EDURE)?|FUNCTION|TRIGGER)\b"
)


def _is_routine_head(statement: str) -> bool:
    """Whether *statement* (trivia stripped) begins a routine definition."""
    _, code = split_leading_trivia(statement)
    return bool(_ROUTINE_HEAD_RE.match(code))


#: The leading keyword of a bare transaction opener (``begin`` / ``begin
#: transaction`` / ``start transaction``). Only consulted for a batch that
#: fails to parse — the very case that makes an opener degrade to a carrier.
_TX_OPEN_LEADING = ("begin", "start")


def _batch_transaction_role(sql: str, dialect: str) -> str | None:
    """Classify a batch's top-level transaction effect: ``"open"``, ``"close"``
    or ``None``.

    Used only for degrade-coherence: when an opener batch dies in a
    parse-failure carrier, its sibling closer must degrade too rather than ship
    an orphan COMMIT (T-SQL error 3902). Classification is on the parsed AST via
    sqlglot; on a parse failure — the situation that makes the opener degrade —
    only the leading keyword is reliable.
    """
    read = _SQLGLOT_DIALECT.get(dialect)
    if read is None:
        return None
    _, code = split_leading_trivia(sql)
    code = code.strip()
    if not code:
        return None
    try:
        parsed = [e for e in sqlglot.parse(code, read=read) if e]
    except _SqlglotError:
        head = code.split(None, 1)[0].lower().rstrip(";")
        return "open" if head in _TX_OPEN_LEADING else None
    if len(parsed) != 1:
        return None
    if isinstance(parsed[0], exp.Transaction):
        return "open"
    if isinstance(parsed[0], (exp.Commit, exp.Rollback)):
        return "close"
    return None


@dataclass(frozen=True)
class TranspileOptions:
    """Options controlling transpilation behavior."""

    preserve_comments: bool = True
    include_warnings: bool = True
    format_output: bool = True
    db_url: str | None = None
    #: Target-engine URL for opt-in LIVE output validation: statements the
    #: real engine rejects degrade to documented carriers with the engine's
    #: error (catches what the sqlglot gate's leniency lets through).
    #: DEVELOPMENT-FACING ONLY — a code-refinement hook for the sweep/tuning
    #: loops; deliberately not exposed in the CLI or the API (decision
    #: 2026-07-17).
    validate_live_url: str | None = None


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


def _mysql_single_quoted(s: str) -> str:
    """Escape *s* for embedding in a MySQL single-quoted literal.

    Backslashes are escape characters in MySQL strings (unless
    NO_BACKSLASH_ESCAPES is set), so they must be doubled along with the
    quotes."""
    return s.replace("\\", "\\\\").replace("'", "''")


def _warn_guard_else_dropped(
    result: TranspileResult, else_body: str, source: str, target: str
) -> TranspileResult:
    """Record that a guard's ELSE branch was dropped (no-silent-loss).

    Only a single diagnostic ``PRINT`` can ride in the target conditional's
    ELSE slot; any other branch (or one whose expression does not translate
    cleanly) is cut, and that loss must be reported. A falsy *else_body*
    passes the result through untouched (no branch existed)."""
    if not else_body:
        return result
    head = " ".join(else_body.strip().split())[:60]
    return TranspileResult(
        sql=result.sql,
        warnings=[
            *result.warnings,
            _warn(
                "guard ELSE branch dropped (only a diagnostic PRINT can be "
                f"carried into the {target} conditional): {head}",
                "guard_dropped",
                source,
                target,
                code="UNIQUE-1226",
            ),
        ],
        unsupported=result.unsupported,
    )


def _pg_column_guard(
    body: str,
    table: str,
    column: str,
    default_pred: bool,
    exists: str,
    else_stmt: str | None,
) -> str:
    """The PostgreSQL ``DO $$`` block for a recognized column-probe guard."""
    probe_sql = (
        "SELECT 1 FROM information_schema.columns\n"
        f"        WHERE table_name = lower('{table}') "
        f"AND column_name = lower('{column}')"
    )
    if default_pred:
        probe_sql += "\n          AND column_default IS NOT NULL"
    body_stmt = body if body.endswith(";") else body + ";"
    body_block = "\n".join(f"        {line.strip()}" for line in body_stmt.splitlines())
    else_block = f"    ELSE\n        {else_stmt};\n" if else_stmt else ""
    return (
        "DO $$\n"
        "BEGIN\n"
        f"    IF {exists} (\n"
        f"        {probe_sql}\n"
        "    ) THEN\n"
        f"{body_block}\n"
        f"{else_block}"
        "    END IF;\n"
        "END $$;"
    )


def _mysql_column_guard(
    body: str,
    table: str,
    column: str,
    default_pred: bool,
    exists: str,
    else_stmt: str | None,
) -> str:
    """The MySQL ``information_schema`` + ``IF()`` + ``PREPARE`` form.

    MySQL has no anonymous blocks; a catalog-conditional single statement
    runs by choosing the SQL text with ``IF()`` and executing it prepared
    (user report 2026-07-29)."""
    probe_sql = (
        "SELECT 1 FROM information_schema.columns\n"
        f"    WHERE table_schema = DATABASE() AND table_name = '{table}' "
        f"AND column_name = '{column}'"
    )
    if default_pred:
        probe_sql += "\n      AND column_default IS NOT NULL"
    then_sql = _mysql_single_quoted(body.rstrip(";"))
    alt_sql = _mysql_single_quoted(else_stmt) if else_stmt else "DO 0"
    return (
        f"SET @unique_guard_sql = (SELECT IF({exists} (\n"
        f"    {probe_sql}\n"
        f"), '{then_sql}', '{alt_sql}'));\n"
        "PREPARE unique_guard_stmt FROM @unique_guard_sql;\n"
        "EXECUTE unique_guard_stmt;\n"
        # DROP PREPARE == DEALLOCATE PREPARE; the DEALLOCATE spelling
        # fails the output gate's mysql parse (sqlglot rejects it).
        "DROP PREPARE unique_guard_stmt;"
    )


def _oracle_column_guard(
    body: str,
    table: str,
    column: str,
    default_pred: bool,
    polarity: str,
    else_stmt: str | None,
) -> str:
    """The Oracle PL/SQL form for a recognized column-probe guard.

    Without an ELSE the guard rides in the same compact FOR-loop form as the
    other Oracle guards (user report 2026-07-29); a carried ELSE diagnostic
    needs the block form (the FOR loop has no ELSE slot)."""
    stmt = body.rstrip(";").replace("'", "''")
    if else_stmt:
        count_probe = (
            "SELECT COUNT(*) INTO unique_guard_n FROM user_tab_columns\n"
            f"    WHERE table_name = UPPER('{table}') "
            f"AND column_name = UPPER('{column}')"
        )
        if default_pred:
            # data_default is a LONG (unusable in WHERE); default_length
            # is its NUMBER shadow.
            count_probe += "\n      AND default_length IS NOT NULL"
        check = "> 0" if polarity == "present" else "= 0"
        return (
            "DECLARE\n"
            "    unique_guard_n NUMBER;\n"
            "BEGIN\n"
            f"    {count_probe};\n"
            f"    IF unique_guard_n {check} THEN\n"
            f"        EXECUTE IMMEDIATE '{stmt}';\n"
            "    ELSE\n"
            f"        {else_stmt};\n"
            "    END IF;\n"
            "END;"
        )
    probe_sql = (
        f"SELECT 1 FROM user_tab_columns\n"
        f"      WHERE table_name = UPPER('{table}') "
        f"AND column_name = UPPER('{column}')"
    )
    if default_pred:
        probe_sql += "\n        AND default_length IS NOT NULL"
    exists = "EXISTS" if polarity == "present" else "NOT EXISTS"
    return (
        f"BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE {exists} (\n"
        f"      {probe_sql})) LOOP\n"
        f"    EXECUTE IMMEDIATE '{stmt}';\n"
        "  END LOOP; END;"
    )


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
        if target_dialect.source_only:
            raise UnsupportedFeatureError(
                f"{target} is import-only (a source only, never a target)",
                source,
                target,
            )

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

        # T-SQL alias types (CREATE TYPE x FROM base) defined anywhere in the
        # script: harvest them up front so columns typed with an alias resolve
        # to the base type on engines without alias types.
        alias_token = None
        bit_token = None
        date_token = None
        identity_token = None
        proc_date_token = None
        func_token = None
        if source == "tsql" and target != "tsql":
            aliases = harvest_tsql_alias_types(sql)
            if aliases:
                alias_token = TSQL_ALIAS_TYPES.set(aliases)
            if target == "postgresql":
                bit_columns = harvest_tsql_bit_columns(sql)
                if bit_columns:
                    bit_token = TSQL_BIT_COLUMNS.set(bit_columns)
        # Oracle can't read a bare ISO date string into a date column; harvest
        # date columns (any source dialect) so their literals are wrapped.
        if target == "oracle" and source != "oracle":
            date_columns = harvest_date_columns(sql)
            if date_columns:
                date_token = DATE_COLUMNS.set(date_columns)
            proc_date_params = harvest_proc_date_params(sql)
            if proc_date_params:
                proc_date_token = PROC_DATE_PARAMS.set(proc_date_params)
        # A row-level trigger becomes a T-SQL statement-level trigger keyed on the
        # table's identity/PK (``… WHERE <pk> IN (SELECT <pk> FROM inserted)``),
        # and its scalar-UDF calls must be qualified ``dbo.<fn>``; harvest both
        # (also identity for the Oracle target's compound-trigger synthesis).
        if target in ("oracle", "tsql") and source != target:
            identity_columns = harvest_identity_columns(sql)
            if identity_columns:
                identity_token = IDENTITY_COLUMNS.set(identity_columns)
        temp_tables_token = None
        if target == "tsql" and source in ("postgresql", "mysql"):
            temp_tables = harvest_temp_tables(sql)
            if temp_tables:
                temp_tables_token = TEMP_TABLES.set(temp_tables)
        # MySQL ENUM columns sort by declaration index; the degrade to
        # VARCHAR+CHECK loses that order, so the transformer rewrites
        # ordering-sensitive uses into an ordinal CASE (B29).
        enum_columns_token = None
        if source == "mysql" and target != "mysql":
            enum_columns = harvest_enum_columns(sql)
            if enum_columns:
                enum_columns_token = ENUM_COLUMNS.set(enum_columns)
        # Cross-statement column-type metadata from the script's own CREATE
        # TABLEs (MySQL/T-SQL ALTERs re-state the type; LOB expression
        # indexes degrade).
        column_types_token = None
        column_not_null_token = None
        pk_unique_token = None
        if source != target:
            column_types = harvest_column_types(sql)
            if column_types:
                column_types_token = COLUMN_TYPES.set(column_types)
            # NOT NULL knowledge feeds the T-SQL ALTER COLUMN re-statement and
            # is folded (with the types) in statement order as ALTERs emit.
            column_not_null = harvest_column_not_null(sql)
            if column_not_null:
                column_not_null_token = COLUMN_NOT_NULL.set(column_not_null)
            # PK/UNIQUE keys let an upsert with no explicit conflict target
            # (MySQL ON DUPLICATE KEY / INSERT IGNORE) lower to a PG conflict
            # target or a T-SQL/Oracle MERGE ON condition.
            pk_unique = harvest_pk_unique_columns(sql)
            if pk_unique:
                pk_unique_token = PK_UNIQUE_COLUMNS.set(pk_unique)
        source_dialect_token = SOURCE_DIALECT.set(source)
        degraded_routines_token = DEGRADED_ROUTINES.set(set())
        refcursor_procs_token = REFCURSOR_PROCS.set({})
        pg_trigger_fn_token = None
        pg_composite_token = None
        pg_domain_token = None
        if source == "postgresql" and target != "postgresql":
            composite_types = harvest_pg_composite_types(sql)
            if composite_types:
                pg_composite_token = PG_COMPOSITE_TYPES.set(composite_types)
            domains = harvest_pg_domains(sql)
            if domains:
                pg_domain_token = PG_DOMAIN_TYPES.set(domains)
        if target == "tsql" and source != "tsql":
            user_functions = harvest_user_functions(sql)
            if user_functions:
                func_token = USER_FUNCTIONS.set(user_functions)
        # A PostgreSQL trigger function is inlined into its T-SQL trigger.
        if target == "tsql" and source == "postgresql":
            pg_trigger_fns = harvest_pg_trigger_functions(sql)
            if pg_trigger_fns:
                pg_trigger_fn_token = PG_TRIGGER_FN_BODIES.set(pg_trigger_fns)

        try:
            # Step 0: Split into batches
            batches = BatchSplitter.split(sql, source)
            logger.debug("Split into %d batches", len(batches))

            all_warnings: list[TransformWarning] = []
            all_unsupported: list[str] = []
            output_parts: list[tuple[str, bool]] = []  # (sql, is_comment)
            # Carrier fragments already reconciled against the warnings, so a
            # fragment repeated across thousands of batches (a big migration dump)
            # is checked once, not O(carriers × warnings) — that reconciliation
            # was the dominant super-linear cost on very large scripts.
            reconciled_frags: set[str] = set()
            unsupported_seen: set[str] = set()
            # Running T-SQL QUOTED_IDENTIFIER state: under OFF, double-quoted
            # tokens are string literals, so subsequent batches are preprocessed
            # to convert "..." -> '...' before parsing.
            quoted_identifier_off = False
            # Transaction-coherence stack: one entry per open transaction, True
            # if its opener emitted executable SQL, False if the opener degraded
            # to a carrier. A closer whose opener is False must degrade too,
            # never ship a bare COMMIT/ROLLBACK (T-SQL error 3902).
            tx_stack: list[bool] = []

            for batch in batches:
                # Skip empty batches, but keep explicit COMMENT batches: they
                # have no executable SQL yet carry information worth preserving
                # (e.g. Oracle 'rem'/'prompt' notices) in the output.
                if batch.is_empty and batch.batch_type != BatchType.COMMENT:
                    continue

                # Track SET QUOTED_IDENTIFIER ON/OFF so later batches read
                # double quotes correctly (T-SQL source only).
                if source == "tsql":
                    if _QI_OFF_RE.search(batch.sql):
                        quoted_identifier_off = True
                    elif _QI_ON_RE.search(batch.sql):
                        quoted_identifier_off = False
                    if quoted_identifier_off and '"' in batch.sql:
                        batch = replace(batch, sql=_double_quoted_to_strings(batch.sql))

                if batch.batch_type == BatchType.PROCEDURAL:
                    result = self._transpile_procedural(
                        batch.sql, source, target, metadata_resolver
                    )
                elif batch.batch_type == BatchType.SET_OPTION:
                    # T-SQL catalog migration guards (IF OBJECT_ID()/EXISTS()
                    # …) are not SET options — extract and translate the intent.
                    # Match on the trivia-free code (comments are trivia, doc-04
                    # P2 — a section-header comment must never defeat a guard
                    # recognizer) and re-attach the trivia to the result.
                    trivia, code = split_leading_trivia(batch.sql)
                    guard = (
                        _extract_catalog_guard(code)
                        if source == "tsql" and target != "tsql"
                        else None
                    )
                    if guard is not None:
                        polarity, inner_trivia, body, condition, else_body = guard
                        if inner_trivia.strip():
                            trivia = (
                                f"{trivia.rstrip()}\n{inner_trivia}"
                                if trivia.strip()
                                else inner_trivia
                            )
                        drop_stmt = (
                            _DROP_STMT_RE.match(body) if polarity == "present" else None
                        )
                        if drop_stmt:
                            # IF EXISTS/IS NOT NULL + DROP: the target's own
                            # conditional drop keeps the re-runnable intent.
                            result = self._transpile_drop_guard(
                                drop_stmt.group("kind"),
                                drop_stmt.group("name"),
                                source,
                                target,
                            )
                            result = _warn_guard_else_dropped(
                                result, else_body, source, target
                            )
                        else:
                            # Any other guarded statement: transpile the body
                            # (the catalog condition has no target form) and
                            # restore the idempotent intent where the target
                            # has one (CREATE … IF NOT EXISTS / Oracle probe).
                            # A guard that cannot be restored is dropped WITH
                            # a warning — never silently (no-silent-loss).
                            result = self._transpile_dml(
                                body, source, target, source_dialect, target_dialect
                            )
                            else_stmt = self._guard_else_print(
                                else_body,
                                source,
                                target,
                                source_dialect,
                                target_dialect,
                            )
                            if polarity == "absent":
                                result = self._guard_idempotent(
                                    result,
                                    source,
                                    target,
                                    condition,
                                    polarity,
                                    else_body,
                                    else_stmt,
                                )
                            else:
                                result = self._faithful_catalog_guard(
                                    result,
                                    condition,
                                    polarity,
                                    source,
                                    target,
                                    else_body,
                                    else_stmt,
                                ) or self._warn_guard_dropped(
                                    result, source, target, else_body
                                )
                    else:
                        trivia = ""  # the fallback keeps the whole batch text
                        result = self._transpile_set_batch(
                            batch.sql, source, target, source_dialect, target_dialect
                        )
                    if trivia.strip():
                        result = TranspileResult(
                            sql=f"{trivia.rstrip()}\n{result.sql}",
                            warnings=result.warnings,
                            unsupported=result.unsupported,
                        )
                elif batch.batch_type == BatchType.COMMENT:
                    # Comments carry no executable SQL; preserve them verbatim
                    # (already normalized to '-- ...' line comments).
                    result = TranspileResult(sql=batch.sql, warnings=[], unsupported=[])
                else:
                    result = self._transpile_dml(
                        batch.sql, source, target, source_dialect, target_dialect
                    )

                # Output validity gate (doc 04, M1): never ship output we can
                # tell is invalid on the target — degrade it to the documented
                # carrier + warning + unsupported entry instead. The gate only
                # detects; the fix belongs in the AST paths.
                if batch.batch_type != BatchType.COMMENT and not _is_comment_only(
                    result.sql
                ):
                    gate = gate_reason(result.sql, target, source)
                    # PG U&'…' Unicode-escape literals are mis-parsed by the
                    # parser (``U & '…'`` — a column named U), silently
                    # producing a wrong expression; a source-text detection is
                    # the only possible catch (docs/03-unsupported.md §3.22).
                    if (
                        gate is None
                        and source == "postgresql"
                        and target != "postgresql"
                        and re.search(r"(?i)\bU&'", batch.sql)
                    ):
                        gate = (
                            "PostgreSQL U&'…' Unicode-escape literal is not "
                            "supported by the parser (mis-parsed as a column "
                            "reference); rewrite it as a plain literal or CHR()"
                        )
                    if gate is not None:
                        message = (
                            f"output failed the {target} validity check "
                            f"({gate}); original {source} batch preserved"
                        )
                        result = TranspileResult(
                            sql=degrade_to_carrier(batch.sql, gate, source, target),
                            warnings=[
                                *result.warnings,
                                _warn(message, "validity_gate", source, target),
                            ],
                            unsupported=[*result.unsupported, message],
                        )
                    else:
                        # Valid output, but a known human-approved value
                        # divergence with no statement-level fix (collation /
                        # encoding): keep the SQL, flag it non-silently with a
                        # leading UNIQUE comment + a warning.
                        reason = annotate_divergence(batch.sql, source, target)
                        if reason is not None:
                            result = TranspileResult(
                                sql=f"-- UNIQUE-1207: {reason}\n{result.sql}",
                                warnings=[
                                    *result.warnings,
                                    _warn(reason, "value_divergence", source, target),
                                ],
                                unsupported=result.unsupported,
                            )

                # Transaction-opener/closer coherence: track each open
                # transaction; if its opener degraded to a carrier, degrade the
                # matching closer too rather than orphan a COMMIT/ROLLBACK
                # (T-SQL error 3902). Procedural/comment batches manage their
                # own BEGIN…END and are handled inside their engine.
                if batch.batch_type not in (BatchType.PROCEDURAL, BatchType.COMMENT):
                    tx_role = _batch_transaction_role(batch.sql, source)
                    if tx_role == "open":
                        tx_stack.append(not _is_comment_only(result.sql))
                    elif tx_role == "close" and tx_stack and not tx_stack.pop():
                        reason = (
                            "transaction closer preserved as a comment: its opener "
                            "degraded to a parse-failure carrier, so a bare "
                            "COMMIT/ROLLBACK would orphan the transaction "
                            "(T-SQL error 3902)"
                        )
                        body = "\n".join(
                            f"-- {ln}" for ln in batch.sql.strip().splitlines()
                        )
                        result = TranspileResult(
                            sql=f"-- UNIQUE-1233: {reason}\n{body}",
                            warnings=[
                                *result.warnings,
                                _warn(
                                    reason,
                                    "lossy_conversion",
                                    source,
                                    target,
                                    code="UNIQUE-1233",
                                ),
                            ],
                            unsupported=[*result.unsupported, reason],
                        )

                terminated = self._ensure_terminated(
                    result.sql, target, batch.batch_type
                )
                if target == "mysql":
                    terminated = self._wrap_mysql_routine(terminated)
                    terminated = _mysql_safe_comments(terminated)
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

                # No-silent-loss invariant: every UNIQUE carrier in this
                # batch's output must be mirrored programmatically. Synthesize
                # a warning for any carrier not already covered, and register
                # an unsupported entry when an executable batch was reduced to
                # comments (i.e. the statement was dropped from the output).
                if batch.batch_type != BatchType.COMMENT:
                    frags = _carrier_fragments(terminated)
                    for frag, carrier_code in frags:
                        # Backfill (B32 wave 3): a direct warning from THIS batch
                        # already reports the carrier but shipped code=None; stamp
                        # the carrier's code onto it so the code lives once (in the
                        # carrier) yet reaches the result object. Scoped to this
                        # batch's warnings (not all_warnings) so a carrier that
                        # recurs across batches — its fragment is then already in
                        # reconciled_frags — still codes every batch's warning,
                        # and the scan stays O(batch) rather than O(script²).
                        if carrier_code is not None:
                            for w in _covering_warnings(frag, result.warnings):
                                if w.code is None:
                                    w.code = carrier_code
                        if frag in reconciled_frags:
                            continue
                        reconciled_frags.add(frag)
                        # Synthesize a warning for a carrier no warning covers.
                        # "Covers" also includes an identically-coded warning
                        # from THIS batch (B40): the parse-fallback warning is
                        # stamped UNIQUE-1170 by exact-literal match (see
                        # PARSE_FALLBACK_WARNING above), not the shingle
                        # heuristic, and its wording legitimately differs from
                        # the carrier's own text enough that
                        # ``_warning_covers`` sees no overlap — without this
                        # check that mismatch synthesized a second,
                        # identically-coded warning for the same carrier.
                        already_coded = carrier_code is not None and any(
                            w.code == carrier_code for w in result.warnings
                        )
                        if not already_coded and not _covering_warnings(
                            frag, all_warnings
                        ):
                            all_warnings.append(
                                _warn(
                                    frag,
                                    "lossy_conversion",
                                    source,
                                    target,
                                    code=carrier_code,
                                )
                            )
                    if is_comment:
                        for frag, _code in frags:
                            if frag not in unsupported_seen and not _warning_covers(
                                frag, all_unsupported
                            ):
                                # The same construct often registers an explicit
                                # unsupported entry AND leaves a carrier; keep
                                # one (audit 2026-07-08, N8).
                                unsupported_seen.add(frag)
                                all_unsupported.append(frag)

                # Honest fallback (B39): a procedural parse/transform warning
                # ships with code=None (see _transpile_procedural) so the
                # backfill above can stamp the SPECIFIC carrier code onto it
                # when one exists in this batch's rendered output (e.g.
                # UNIQUE-1171/1193). Only once no carrier covered it do we
                # fall back to the generic "parse note"/"transform note"
                # code — this also covers cases with no carrier at all (a
                # same-dialect SET-option warning has nothing to backfill
                # from).
                for w in result.warnings:
                    if w.code is not None:
                        continue
                    if w.feature == "procedural_parse":
                        w.code = "UNIQUE-1230"
                    elif w.feature == "procedural_transform":
                        w.code = "UNIQUE-1231"

            output_sql = self._join_parts(output_parts, target)

            # A T-SQL split TVF becomes an Oracle ODCIVARCHAR2LIST function; its
            # callers must read COLUMN_VALUE FROM TABLE(fn(…)). Rewrite them once
            # the whole (multi-object) script is assembled.
            if target == "oracle":
                tvf_names = _harvest_split_tvf_names(sql)
                if tvf_names:
                    output_sql = _rewrite_tvf_callers(output_sql, tvf_names)

            if options.validate_live_url:
                output_sql, live_warnings = self._validate_output_live(
                    output_sql, target, options.validate_live_url
                )
                all_warnings.extend(live_warnings)

            return TranspileResult(
                sql=output_sql,
                warnings=_aggregate_warnings(all_warnings),
                unsupported=all_unsupported,
            )
        finally:
            if alias_token is not None:
                TSQL_ALIAS_TYPES.reset(alias_token)
            if bit_token is not None:
                TSQL_BIT_COLUMNS.reset(bit_token)
            if date_token is not None:
                DATE_COLUMNS.reset(date_token)
            if identity_token is not None:
                IDENTITY_COLUMNS.reset(identity_token)
            if temp_tables_token is not None:
                TEMP_TABLES.reset(temp_tables_token)
            if enum_columns_token is not None:
                ENUM_COLUMNS.reset(enum_columns_token)
            if column_types_token is not None:
                COLUMN_TYPES.reset(column_types_token)
            if column_not_null_token is not None:
                COLUMN_NOT_NULL.reset(column_not_null_token)
            if pk_unique_token is not None:
                PK_UNIQUE_COLUMNS.reset(pk_unique_token)
            if proc_date_token is not None:
                PROC_DATE_PARAMS.reset(proc_date_token)
            if func_token is not None:
                USER_FUNCTIONS.reset(func_token)
            if pg_trigger_fn_token is not None:
                PG_TRIGGER_FN_BODIES.reset(pg_trigger_fn_token)
            if pg_composite_token is not None:
                PG_COMPOSITE_TYPES.reset(pg_composite_token)
            if pg_domain_token is not None:
                PG_DOMAIN_TYPES.reset(pg_domain_token)
            DEGRADED_ROUTINES.reset(degraded_routines_token)
            REFCURSOR_PROCS.reset(refcursor_procs_token)
            SOURCE_DIALECT.reset(source_dialect_token)
            if metadata_resolver:
                metadata_resolver.close()

    def _join_parts(self, parts: list[tuple[str, bool]], target: str) -> str:
        """Join emitted parts, choosing the right delimiter between each pair.

        A comment part is attached to what follows with a plain newline rather
        than the batch separator, so we don't emit a useless ``GO`` (T-SQL) or
        ``/`` (Oracle) after a comment. The batch separator is only used
        between two executable parts.

        Oracle's ``/`` executes the SQL*Plus buffer, so it must follow **only**
        PL/SQL blocks (which internal ``;`` don't terminate); after a plain
        ``;``-terminated DML/DDL statement a ``/`` would re-run it. So for Oracle
        the delimiter is chosen per preceding statement, and a trailing PL/SQL
        block still gets its own ``/``.
        """
        if not parts:
            return ""
        default_sep = self._get_batch_separator(target)
        oracle = target == "oracle"
        # Accumulate pieces and join once: repeated ``out += …`` copies the whole
        # (multi-MB) accumulator each time — O(n²) — which dominated very large
        # scripts. The trailing-newline rstrip only affects the previous piece.
        pieces = [parts[0][0]]
        for i in range(1, len(parts)):
            prev_text, prev_is_comment = parts[i - 1]
            text, _ = parts[i]
            if prev_is_comment:
                # Glue the comment to the following part with a newline.
                pieces[-1] = pieces[-1].rstrip("\n")
                pieces.append("\n" + text)
            elif oracle:
                sep = "\n/\n\n" if _oracle_needs_slash(prev_text) else "\n\n"
                pieces.append(sep + text)
            else:
                pieces.append(default_sep + text)
        if oracle:
            last_text, last_is_comment = parts[-1]
            if not last_is_comment and _oracle_needs_slash(last_text):
                pieces.append("\n/")
        return "".join(pieces)

    def _peel_leading_statements(
        self,
        sql: str,
        source: str,
        target: str,
        metadata_resolver: object | None,
    ) -> TranspileResult | None:
        """Split a folded ``<leading statements> … <routine>`` procedural batch.

        Returns a composed result when the batch has one or more complete
        non-routine statements ahead of its routine (the splitter folds a
        routine's companion DDL into its batch); the leading statements go
        through the standalone DML/DDL pipeline and the routine through the
        procedural engine. Returns ``None`` for an ordinary procedural batch
        (a single routine or an anonymous block), which then parses whole so
        the whole-unit degrade contract is unchanged for batches that truly
        cannot parse.
        """
        statements = split_statements(sql, source)
        if len(statements) < 2:
            return None
        routine_idx = next(
            (i for i, st in enumerate(statements) if _is_routine_head(st)), None
        )
        # No routine, or the routine is already first: nothing to peel.
        if not routine_idx:
            return None

        # Locate the routine's start in the ORIGINAL text so both the leading
        # part and the routine keep their verbatim formatting and comments
        # (split_statements trims each piece). The pieces are in order, so scan
        # forward past the leading ones before locating the routine.
        search_from = 0
        for st in statements[:routine_idx]:
            found = sql.find(st, search_from)
            if found >= 0:
                search_from = found + len(st)
        routine_start = sql.find(statements[routine_idx], search_from)
        if routine_start <= 0:
            return None
        leading_sql = sql[:routine_start].rstrip()
        routine_sql = sql[routine_start:]

        source_dialect = self.registry.get(source)
        target_dialect = self.registry.get(target)
        lead_result = self._transpile_dml(
            leading_sql, source, target, source_dialect, target_dialect
        )
        # The batch-loop validity gate runs once over the composed batch, but a
        # routine's procedural body defeats it (sqlglot can't parse the whole
        # thing), so the leading DDL would never be gated. Gate it here — the
        # same check a standalone leading statement gets — so an unmappable DDL
        # degrades to an honest carrier instead of shipping invalid.
        gate = gate_reason(lead_result.sql, target, source)
        if gate is not None:
            message = (
                f"output failed the {target} validity check ({gate}); "
                f"original {source} statement preserved"
            )
            lead_result = TranspileResult(
                sql=degrade_to_carrier(leading_sql, gate, source, target),
                warnings=[
                    *lead_result.warnings,
                    _warn(message, "validity_gate", source, target),
                ],
                unsupported=[*lead_result.unsupported, message],
            )
        routine_result = self._transpile_procedural(
            routine_sql, source, target, metadata_resolver
        )

        # Compose: the leading DDL is a self-contained statement (terminated for
        # ``;``-delimited targets; ``GO``-separated for T-SQL). The routine keeps
        # the un-terminated shape a normal single-routine batch returns so the
        # batch loop's _ensure_terminated / _join_parts finalize it as usual —
        # except a MySQL routine must carry its own DELIMITER wrapper here (the
        # batch loop's _wrap_mysql_routine only fires when the WHOLE batch begins
        # with the routine, which it no longer does once the DDL leads).
        ddl_sql = lead_result.sql
        routine_sql_out = routine_result.sql
        if target == "tsql":
            separator = "\nGO\n"
        else:
            ddl_sql = self._ensure_terminated(ddl_sql, target, BatchType.DDL)
            separator = "\n\n"
        if target == "mysql":
            routine_sql_out = self._wrap_mysql_routine(
                self._ensure_terminated(routine_sql_out, target, BatchType.PROCEDURAL)
            )
        return TranspileResult(
            sql=f"{ddl_sql}{separator}{routine_sql_out}",
            warnings=[*lead_result.warnings, *routine_result.warnings],
            unsupported=[*lead_result.unsupported, *routine_result.unsupported],
        )

    def _transpile_procedural(
        self,
        sql: str,
        source: str,
        target: str,
        metadata_resolver: object | None = None,
    ) -> TranspileResult:
        """Transpile a procedural batch through the procedural engine."""
        # A procedural batch may carry one or more complete non-routine
        # statements ahead of the routine: the BatchSplitter's PL/SQL-block
        # heuristic folds a routine's companion DDL (e.g. the global temporary
        # table backing a former T-SQL table variable) into the same batch. The
        # procedural parser only understands a routine at the head, so such a
        # leading statement would fail the WHOLE batch (DDL and routine both)
        # into a UNIQUE-1170 carrier. Peel the leading statements off and route
        # them through the standalone DML/DDL pipeline (the same IR path a
        # standalone CREATE TABLE takes), then transpile the routine alone.
        peeled = self._peel_leading_statements(sql, source, target, metadata_resolver)
        if peeled is not None:
            return peeled

        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        # The procedural parser starts at the first keyword and drops any comment
        # lines/blocks that precede the routine (e.g. a "-- <codegen> …" header).
        # Capture them here so they are re-attached to the emitted output.
        lead = re.match(r"(?s)^([ \t]*(?:--[^\n]*\n|/\*.*?\*/[ \t]*\n?)+)", sql)
        leading_comments = lead.group(1).rstrip("\n") + "\n" if lead else ""

        try:
            # Parse
            parser = ProceduralParser(source)
            parse_result = parser.parse(sql)

            if parse_result.errors:
                for err in parse_result.errors:
                    # code=None: the outer batch loop's carrier reconciliation
                    # (B39) backfills the specific code embedded in this
                    # batch's rendered carrier when one exists, falling back
                    # to the generic UNIQUE-1230 only when no carrier covers
                    # this warning (see the fallback pass in _core.py's main
                    # transpile loop).
                    warnings.append(
                        _warn(
                            f"Parse error: {err.message}",
                            "procedural_parse",
                            source,
                            target,
                            code=None,
                        )
                    )

            if parse_result.warnings:
                for w in parse_result.warnings:
                    # The parse-fallback ("could not parse, preserved as a
                    # carrier") warning maps 1:1 to the RawSQL node's own
                    # UNIQUE-1170 carrier, but its wording differs enough from
                    # the carrier text that the shingle-based backfill below
                    # can miss it — this is an exact match against a literal
                    # this module owns (PARSE_FALLBACK_WARNING), not a scan of
                    # arbitrary SQL, so it stays a structural, not fragile,
                    # check. Other parse warnings fall through to code=None
                    # for the same reconciliation/fallback reason as errors.
                    code = "UNIQUE-1170" if w == PARSE_FALLBACK_WARNING else None
                    warnings.append(
                        _warn(w, "procedural_parse", source, target, code=code)
                    )

            if parse_result.node is None:
                return TranspileResult(
                    sql=f"/* PARSE ERROR */\n{sql}",
                    warnings=warnings,
                    unsupported=unsupported,
                )

            # Attach the routine's ORIGINAL text (sans the captured leading
            # comments) so a whole-routine degrade carrier quotes it verbatim
            # instead of a re-render of the tree (audit 2026-07-24 N12).
            parsed_node = replace(
                parse_result.node,
                source_text=sql[lead.end() if lead else 0 :].strip(),
            )

            # Transform
            if source != target:
                transformer = ProceduralTransformer(source, target, metadata_resolver)
                node = transformer.transform(parsed_node)
                for w in transformer.warnings:
                    # code=None: same B39 reconciliation/fallback contract as
                    # the parse warnings above (falls back to UNIQUE-1231).
                    warnings.append(
                        _warn(
                            w,
                            "procedural_transform",
                            source,
                            target,
                            code=None,
                        )
                    )
            else:
                node = parsed_node

            # A routine's header comment lives where each engine stores it: SQL
            # Server keeps comments that precede CREATE as part of the module;
            # Oracle/PostgreSQL/MySQL store a routine only from CREATE on, so the
            # comment must sit inside. Move it to the target's home so it survives
            # the round-trip (T-SQL ⇄ Oracle) instead of being dropped.
            if isinstance(
                node,
                (
                    CreateProcedureStatement,
                    CreateFunctionStatement,
                    CreateTriggerStatement,
                ),
            ):
                if target in _ROUTINE_COMMENT_TARGETS and leading_comments:
                    # Forward: pull the pre-CREATE comments inside (flagged so the
                    # emitter hoists them to the head of the declaration section).
                    homed = _leading_comment_nodes(leading_comments)
                    if homed:
                        node = replace(node, body=(*homed, *node.body))
                        leading_comments = ""
                elif target == "tsql":
                    # Reverse: a header comment the source kept inside the routine
                    # belongs before the CREATE in the T-SQL module — pull it out.
                    inside = [
                        c
                        for c in node.body
                        if isinstance(c, CommentStatement) and c.header
                    ]
                    if inside:
                        leading_comments += "".join(c.text + "\n" for c in inside)
                        node = replace(
                            node,
                            body=tuple(
                                c
                                for c in node.body
                                if not (isinstance(c, CommentStatement) and c.header)
                            ),
                        )

            # Emit
            emitter = ProceduralEmitter(target)
            output_sql = emitter.emit(node)

            return TranspileResult(
                sql=leading_comments + output_sql,
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
                    code="UNIQUE-1232",
                )
            )
            return TranspileResult(
                sql=f"/* TRANSPILATION ERROR: {e} */\n{sql}",
                warnings=warnings,
                unsupported=unsupported,
            )

    def _transpile_alter_column(
        self,
        sql: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> TranspileResult | None:
        """Build the target's column-modify form for a T-SQL ``ALTER TABLE t ALTER
        COLUMN c <type> [NULL|NOT NULL]``. Reuses the CREATE-TABLE column mapping
        (name + type, incl. ``VARBINARY(MAX)`` -> ``BLOB``) via a synthetic
        one-column table; returns ``None`` (keep the sqlglot path) if it can't be
        matched/mapped cleanly."""
        m = _TSQL_ALTER_COLUMN_RE.match(sql)
        if not m:
            return None
        nullability = " ".join((m.group("null") or "").upper().split())
        synth = self._transpile_dml(
            f"CREATE TABLE {m.group('table')} ({m.group('col')} {m.group('type')})",
            source,
            target,
            source_dialect,
            target_dialect,
        ).sql
        cm = re.search(
            r"(?is)CREATE\s+TABLE\s+(?P<table>[^\s(]+)\s*\((?P<body>.*)\)", synth
        )
        if not cm:
            return None
        coldef = " ".join(cm.group("body").split()).rstrip(",").strip()
        parts = coldef.split(None, 1)
        if len(parts) != 2:
            return None
        colname, coltype = parts
        warnings = []
        if target == "oracle" and nullability == "NULL":
            warnings.append(
                _warn(
                    "Oracle MODIFY keeps the column's current nullability; the "
                    "redundant NULL is omitted (an explicit NULL raises ORA-01451 "
                    "when the column is already nullable)",
                    "alter_column_null",
                    source,
                    target,
                    code="UNIQUE-1227",
                )
            )
        return TranspileResult(
            sql=(m.group("lead") or "")
            + self._alter_column_stmt(
                target, cm.group("table"), colname, coltype, nullability
            ),
            warnings=warnings,
            unsupported=[],
        )

    @staticmethod
    def _alter_column_stmt(
        target: str, table: str, colname: str, coltype: str, nullability: str
    ) -> str:
        """The target's spelling of a column type/nullability change."""
        null = f" {nullability}" if nullability else ""
        if target == "oracle":
            # MODIFY (c type NULL) raises ORA-01451 when the column is already
            # nullable, and MODIFY (c type) keeps the current nullability — so
            # emit an explicit NOT NULL only, never a redundant NULL.
            nn = " NOT NULL" if nullability == "NOT NULL" else ""
            return f"ALTER TABLE {table} MODIFY ({colname} {coltype}{nn});"
        if target == "mysql":
            return f"ALTER TABLE {table} MODIFY COLUMN {colname} {coltype}{null};"
        if target == "postgresql":
            stmt = f"ALTER TABLE {table} ALTER COLUMN {colname} TYPE {coltype};"
            if nullability == "NOT NULL":
                stmt += f"\nALTER TABLE {table} ALTER COLUMN {colname} SET NOT NULL;"
            elif nullability == "NULL":
                stmt += f"\nALTER TABLE {table} ALTER COLUMN {colname} DROP NOT NULL;"
            return stmt
        return f"ALTER TABLE {table} ALTER COLUMN {colname} {coltype}{null};"

    def _transpile_create_schema(
        self, sql: str, source: str, target: str
    ) -> TranspileResult | None:
        """T-SQL ``CREATE SCHEMA <name> [AUTHORIZATION <owner>]`` (often wrapped in
        ``EXEC('…')`` dynamic SQL, which sqlglot leaves opaque). PostgreSQL/MySQL
        have ``CREATE SCHEMA``; Oracle has no namespace object — a schema is a
        database user — so it degrades to a documented carrier. Returns ``None``
        when unmatched."""
        m = _TSQL_CREATE_SCHEMA_RE.match(sql)
        if not m:
            return None
        name = m.group("name").strip('[]"')
        if target == "oracle":
            body = "\n".join(f"-- {ln}" for ln in sql.strip().splitlines())
            return TranspileResult(
                sql=(
                    "-- UNIQUE-1208: T-SQL CREATE SCHEMA has no Oracle equivalent — an "
                    "Oracle schema is a database user. Create it manually, e.g. "
                    f"CREATE USER {name} …; original:\n{body}"
                ),
                warnings=[
                    _warn(
                        f"CREATE SCHEMA {name} carried (an Oracle schema is a user; "
                        "create it with CREATE USER)",
                        "create_schema",
                        source,
                        target,
                    )
                ],
                unsupported=[f"CREATE SCHEMA {name} has no Oracle equivalent"],
            )
        # PostgreSQL has schemas; MySQL's CREATE SCHEMA is CREATE DATABASE. Emit an
        # idempotent CREATE SCHEMA; the T-SQL owner rarely maps, so drop it + warn.
        warnings = []
        if m.group("owner"):
            warnings.append(
                _warn(
                    "CREATE SCHEMA AUTHORIZATION <owner> dropped (the T-SQL owner "
                    f"has no {target} counterpart)",
                    "create_schema",
                    source,
                    target,
                )
            )
        return TranspileResult(
            sql=f"CREATE SCHEMA IF NOT EXISTS {name};",
            warnings=warnings,
            unsupported=[],
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
        result = self._transpile_dml_inner(
            sql, source, target, source_dialect, target_dialect
        )
        # Oracle sequence references (seq.NEXTVAL/CURRVAL) and the CHR/TO_NUMBER/
        # MONTHS_BETWEEN scalar builtins are now translated on the AST (converter
        # _convert_sequence_ref + the function emitters) — the former post-emit
        # regex rewrites (audit doc 04 F1/F2) are gone.
        if target == "tsql" and source != "tsql":
            # T-SQL rejects an unqualified scalar-UDF call as an unknown
            # built-in (error 195); the procedural paths already qualify —
            # standalone DML must too.
            qualified = _qualify_tsql_udfs_in_sql(result.sql)
            if qualified != result.sql:
                result = TranspileResult(
                    sql=qualified,
                    warnings=result.warnings,
                    unsupported=result.unsupported,
                )
        return result

    def _transpile_dml_inner(
        self,
        sql: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> TranspileResult:
        """The sqlglot pipeline proper (see ``_transpile_dml``)."""
        warnings: list[TransformWarning] = []
        unsupported: list[str] = []

        if source == "oracle" and target != "oracle":
            # Oracle's multi-column ``ALTER TABLE t DROP (a, b)`` parses as an
            # opaque Command (the whole statement then leaks verbatim);
            # normalize to the DROP COLUMN list every engine reads. T-SQL
            # additionally wants one DROP COLUMN with a comma list.
            sql = _normalize_oracle_multicolumn_drop(sql, target)
            # Same story for ALTER TABLE ... MODIFY (neither form parses).
            modified = rewrite_oracle_modify(sql, target)
            if modified is not None:
                return TranspileResult(
                    sql=modified, warnings=warnings, unsupported=unsupported
                )

        if source == "tsql" and target != "tsql":
            altered = self._transpile_alter_column(
                sql, source, target, source_dialect, target_dialect
            )
            if altered is not None:
                return altered
            schema = self._transpile_create_schema(sql, source, target)
            if schema is not None:
                return schema

        # T-SQL compound assignment (SET a += 1) is not understood by sqlglot,
        # which would drop the column; expand it to "SET a = a + 1" first.
        was_default_constraint = False
        default_original = ""
        if source == "tsql":
            sql = _expand_tsql_compound_assignment(sql)
            rewritten = _rewrite_tsql_default_constraint(sql)
            if rewritten != sql:
                was_default_constraint = True
                default_original = sql
                sql = rewritten
            # TEXTIMAGE_ON <filegroup> (physical placement of a table's LOB
            # columns) is a storage clause sqlglot cannot parse: left in, it
            # degrades the whole CREATE TABLE to a Command passthrough (columns
            # and constraints lost). Like ON <filegroup> / WITH (...) — dropped in
            # the emitter — it carries no logical schema, so strip it pre-parse.
            sql, n_lob = re.subn(
                r"(?is)\s+TEXTIMAGE_ON\s+(?:\[[^\]]+\]|\"[^\"]+\"|\w+)", "", sql
            )
            if n_lob:
                warnings.append(
                    _warn(
                        "T-SQL TEXTIMAGE_ON filegroup clause dropped (physical "
                        "storage, no logical-schema impact)",
                        "physical_clause",
                        source,
                        target,
                        code="UNIQUE-1221",
                    )
                )
            # "ALTER TABLE t WITH [NO]CHECK ADD CONSTRAINT …": the WITH
            # CHECK/NOCHECK modifier precedes ADD and makes sqlglot fall back to a
            # Command (losing the constraint). Strip it so the constraint
            # transpiles. WITH CHECK just re-asserts the default (validate), but
            # NOCHECK (add without validating existing rows) has no portable form,
            # so warn — the target will validate on add.
            sql = re.sub(r"(?is)\bWITH\s+CHECK\s+ADD\b", "ADD", sql)
            sql, n_nocheck = re.subn(r"(?is)\bWITH\s+NOCHECK\s+ADD\b", "ADD", sql)
            if n_nocheck:
                warnings.append(
                    _warn(
                        "T-SQL WITH NOCHECK dropped; the constraint is added and "
                        "the target validates existing rows (no NOVALIDATE applied)",
                        "constraint_check",
                        source,
                        target,
                        code="UNIQUE-1222",
                    )
                )

        # Oracle ORGANIZATION INDEX/HEAP: a physical-storage clause sqlglot
        # cannot parse, which would degrade the whole CREATE TABLE (columns
        # and constraints included) to a commented passthrough. The clause
        # carries no logical schema, so strip it and document the drop.
        org_carrier = ""
        if (
            source == "oracle"
            and target != "oracle"
            and re.match(r"(?is)^\s*CREATE\s+TABLE\b", sql)
        ):
            stripped_sql, n_org = re.subn(
                r"(?is)\)\s*ORGANIZATION\s+(INDEX|HEAP)\s*(;?)\s*$",
                r")\2",
                sql,
            )
            if n_org:
                sql = stripped_sql
                org_carrier = (
                    "\n-- UNIQUE-1209: Oracle ORGANIZATION INDEX/HEAP is a "
                    "physical-storage clause with no equivalent here; dropped."
                )
                warnings.append(
                    _warn(
                        "Oracle ORGANIZATION INDEX/HEAP physical clause "
                        "dropped (no logical-schema impact)",
                        "physical_clause",
                        source,
                        target,
                    )
                )

        # T-SQL constraint check-state toggles (ALTER TABLE t CHECK/NOCHECK
        # CONSTRAINT c): translate to the target's enable/disable, else keep a
        # restorable note. Runs before physical stripping (which would eat the
        # leading WITH CHECK) and bypasses sqlglot, which cannot parse the form.
        if (
            source == "tsql"
            and target != "tsql"
            and re.match(r"(?is)^\s*ALTER\s+TABLE\b", sql)
        ):
            state = _rewrite_tsql_constraint_state(sql, target)
            if state:
                return TranspileResult(
                    sql=state + ";", warnings=warnings, unsupported=unsupported
                )
            if state == "":
                return TranspileResult(
                    sql=f"/* UNIQUE-1210: {sql.strip().rstrip(';')} -- tsql-only, no "
                    f"{target} equivalent (constraint check-state) */",
                    warnings=[
                        _warn(
                            "T-SQL constraint check-state toggle preserved as a "
                            "restorable note",
                            "constraint_state",
                            source,
                            target,
                        )
                    ],
                    unsupported=unsupported,
                )

        # System stored-procedure calls (e.g. EXEC sp_addextendedproperty,
        # sp_rename) are SQL Server metadata operations with no portable
        # equivalent. Emit them as an informational comment instead of
        # letting sqlglot fail on the proprietary syntax.
        if source == "tsql" and target != "tsql":
            # Guardrail 3: match on the trivia-free code, not raw text, so a
            # leading ``-- CASE …`` / section-header comment does not hide the
            # EXEC.
            _sp_trivia, _sp_code = split_leading_trivia(sql)
            _sp_re = r"(?i)^\s*EXEC(?:UTE)?\s+(?:\[?\w+\]?\.)*\[?(sp_\w+)"
            m = re.match(_sp_re, _sp_code)
            if m and m.group(1).lower() in _TSQL_SYSTEM_PROCS:
                # A ``;``-separated statement AFTER the system proc must still
                # transpile — folding the whole batch into the proc's carrier
                # silently dropped it (no-silent-loss). Split on top-level ``;``
                # and degrade only the sp_ call(s); every other statement goes
                # through the normal path.
                from unique.core.sql_split import _split_semicolons

                def _sp_carrier(stmt: str) -> str | None:
                    sm = re.match(_sp_re, stmt.lstrip())
                    if not (sm and sm.group(1).lower() in _TSQL_SYSTEM_PROCS):
                        return None
                    sp = sm.group(1)
                    unsupported.append(f"System procedure {sp} has no equivalent")
                    warnings.append(
                        _warn(
                            f"System procedure {sp} skipped (no {target} "
                            "equivalent)",
                            "system_proc",
                            source,
                            target,
                        )
                    )
                    return (
                        f"-- UNIQUE-1211: {sp} is a SQL Server system procedure with "
                        f"no {target} equivalent; original call omitted:\n"
                        + "\n".join(f"-- {ln}" for ln in stmt.strip().splitlines())
                    )

                parts: list[str] = []
                for st in _split_semicolons(_sp_code, dollar_quote=False):
                    carrier = _sp_carrier(st)
                    if carrier is not None:
                        parts.append(carrier)
                    else:
                        sub = self._transpile_dml(
                            st, source, target, source_dialect, target_dialect
                        )
                        parts.append(sub.sql)
                        warnings.extend(sub.warnings)
                        unsupported.extend(sub.unsupported)
                body = "\n".join(parts)
                return TranspileResult(
                    sql=f"{_sp_trivia}{body}" if _sp_trivia.strip() else body,
                    warnings=warnings,
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
                if target == "postgresql" and not _statement_is_merge(base_sql):
                    # Only PostgreSQL has a standalone RETURNING result set —
                    # but NOT on MERGE (PG16 has none; PG17 spells $action as
                    # merge_action()). A MERGE OUTPUT degrades like the others
                    # rather than emit invalid RETURNING or re-attach the tail
                    # to a follow-up statement / comment (audit N3).
                    new_sql = f"{body} RETURNING {cols}"
                else:
                    # MySQL has no OUTPUT/RETURNING; Oracle's RETURNING needs INTO
                    # variables (PL/SQL only) — a bare RETURNING is ORA-63809. Both
                    # degrade with a documented carrier.
                    new_sql = (
                        f"{body}\n-- UNIQUE-1212: {target} has no standalone "
                        f"OUTPUT/RETURNING result set; the statement returned: "
                        f"{cols} (docs/03-unsupported.md)"
                    )
                return TranspileResult(
                    sql=new_sql,
                    warnings=base_result.warnings,
                    unsupported=base_result.unsupported,
                )

        try:
            # Unread-args tripwire (guardrail 7 / brief B2): the converter
            # records any semantic sqlglot arg a ``_convert_*`` never read
            # (an ON CONFLICT / OUTPUT / DO NOTHING clause silently dropped).
            _reset_unread_arg_sink()
            ir_nodes = source_dialect.parse(sql)
            for msg in _drain_unread_arg_sink():
                warnings.append(
                    _warn(msg, _UNREAD_FEATURE, source, target, code="UNIQUE-1228")
                )

            if source != target:
                transformer = Transformer(source, target)
                ir_nodes = transformer.transform(ir_nodes)
                warnings.extend(transformer.warnings)
                unsupported = transformer.unsupported

            output_sql = target_dialect.emit(ir_nodes) + org_carrier
            if source == "sqlite":
                output_sql = _rewrite_sqlite_functions(output_sql, target)
            if was_default_constraint and target == "oracle":
                # Oracle spells a column default change ``MODIFY col DEFAULT v``.
                output_sql = _ORACLE_ALTER_DEFAULT_RE.sub(
                    r"MODIFY \g<col> DEFAULT", output_sql
                )
            if was_default_constraint and not _parses_in_target(output_sql, target):
                # The default value did not translate to valid target SQL (e.g. a
                # T-SQL-only NEWID()); keep the original as a documented carrier
                # rather than emit invalid SQL.
                return TranspileResult(
                    sql="-- UNIQUE-1213: T-SQL default constraint value has no "
                    f"{target} equivalent:\n"
                    + "\n".join(f"-- {ln}" for ln in default_original.splitlines()),
                    warnings=[
                        _warn(
                            "T-SQL default-constraint value has no target form",
                            "ddl_default",
                            source,
                            target,
                        )
                    ],
                    unsupported=unsupported,
                )

            return TranspileResult(
                sql=output_sql,
                warnings=warnings,
                unsupported=unsupported,
            )
        except Exception as e:
            # gate mode aborts the conversion with an UnreadArgError before the
            # post-parse drain runs — surface the recorded residue too.
            for msg in _drain_unread_arg_sink():
                warnings.append(
                    _warn(msg, _UNREAD_FEATURE, source, target, code="UNIQUE-1228")
                )
            # exc_info: a rare escaping error (e.g. the one-off KeyError
            # 'into', audit 2026-07-24 N16) is undiagnosable from str(e) alone.
            logger.warning("DML transpilation failed: %s", e, exc_info=True)
            warnings.append(
                _warn(
                    f"DML transpilation failed: {e}",
                    "dml",
                    source,
                    target,
                    code="UNIQUE-1229",
                )
            )
            return TranspileResult(
                sql=f"/* TRANSPILATION ERROR: {e} */\n{sql}",
                warnings=warnings,
                unsupported=unsupported,
            )

    def _guard_idempotent(
        self,
        result: TranspileResult,
        source: str,
        target: str,
        condition: str = "",
        polarity: str = "absent",
        else_body: str = "",
        else_stmt: str | None = None,
    ) -> TranspileResult:
        """Restore a catalog CREATE-guard's re-runnable intent on the target.

        Oracle wraps the DDL in the ``user_objects`` probe + ``EXECUTE
        IMMEDIATE`` (see ``_oracle_idempotent_create``); PostgreSQL/MySQL use
        their native ``CREATE TABLE/INDEX IF NOT EXISTS`` clause. Where the
        target has no conditional form (MySQL ``CREATE INDEX``, or a body or
        condition the faithful catalog guard cannot express), the guard is
        dropped with an explicit warning — never silently (audit 2026-07-08
        A5; user report 2026-07-09). A carried ELSE diagnostic
        (``else_stmt``) needs a conditional with an ELSE slot, so the
        faithful catalog guard is preferred over the idempotent-clause
        rewrites when one exists."""
        if else_stmt:
            faithful = self._faithful_catalog_guard(
                result, condition, polarity, source, target, else_body, else_stmt
            )
            if faithful is not None:
                return faithful
        if target == "oracle":
            wrapped = _oracle_idempotent_create(result.sql)
            if wrapped is None:
                return self._faithful_catalog_guard(
                    result, condition, polarity, source, target, else_body, else_stmt
                ) or self._warn_guard_dropped(result, source, target, else_body)
            wrapped_result = TranspileResult(
                sql=wrapped, warnings=result.warnings, unsupported=result.unsupported
            )
            return _warn_guard_else_dropped(wrapped_result, else_body, source, target)
        if target in ("postgresql", "mysql"):
            sql, n = re.subn(
                r"(?i)^(\s*)CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)",
                r"\1CREATE TABLE IF NOT EXISTS ",
                result.sql,
                count=1,
            )
            if n:
                rewritten = TranspileResult(
                    sql=sql, warnings=result.warnings, unsupported=result.unsupported
                )
                return _warn_guard_else_dropped(rewritten, else_body, source, target)
            if target == "postgresql":
                sql, n = re.subn(
                    r"(?i)^(\s*)CREATE\s+(UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)",
                    r"\1CREATE \2INDEX IF NOT EXISTS ",
                    result.sql,
                    count=1,
                )
                if n:
                    rewritten = TranspileResult(
                        sql=sql,
                        warnings=result.warnings,
                        unsupported=result.unsupported,
                    )
                    return _warn_guard_else_dropped(
                        rewritten, else_body, source, target
                    )
            elif re.match(r"(?is)^\s*CREATE\s+(UNIQUE\s+)?INDEX\b", result.sql):
                dropped = TranspileResult(
                    sql=result.sql,
                    warnings=[
                        *result.warnings,
                        _warn(
                            "existence guard dropped: MySQL has no CREATE INDEX "
                            "IF NOT EXISTS, so a re-run of this statement errors",
                            "guard_dropped",
                            source,
                            target,
                            code="UNIQUE-1225",
                        ),
                    ],
                    unsupported=result.unsupported,
                )
                return _warn_guard_else_dropped(dropped, else_body, source, target)
            return self._faithful_catalog_guard(
                result, condition, polarity, source, target, else_body, else_stmt
            ) or self._warn_guard_dropped(result, source, target, else_body)
        return self._faithful_catalog_guard(
            result, condition, polarity, source, target, else_body, else_stmt
        ) or self._warn_guard_dropped(result, source, target, else_body)

    _COLUMN_PROBE_TABLE_RE = re.compile(
        r"(?is)^(?:object_)?id\s*=\s*OBJECT_ID\s*\(\s*N?'(?P<t>[^']+)'\s*\)$"
    )
    _COLUMN_PROBE_NAME_RE = re.compile(r"(?is)^name\s*=\s*N?'(?P<c>[^']+)'$")
    _COLUMN_PROBE_DEFAULT_RE = re.compile(r"(?is)^default_object_id\s*(?:<>|!=)\s*0$")

    @classmethod
    def _parse_column_probe(cls, condition: str) -> dict[str, object] | None:
        """Recognize a T-SQL sys.columns/syscolumns existence probe.

        Returns ``{"table", "column", "has_default"}`` for conditions of the
        shape ``SELECT … FROM sys.columns WHERE object_id = OBJECT_ID('t')
        AND name = 'c' [AND default_object_id <> 0]``; None when any
        predicate falls outside that set (never guess a catalog mapping).
        """
        cond = re.sub(r"[\[\]]", "", condition).strip()
        if cond.startswith("(") and cond.endswith(")"):
            cond = cond[1:-1].strip()
        m = re.search(
            r"(?is)\bFROM\s+(?:sys\s*\.\s*columns|syscolumns)\b\s*"
            r"(?:AS\s+\w+\s*)?WHERE\b(?P<preds>.*)$",
            cond,
        )
        if m is None:
            return None
        table = column = None
        has_default = False
        for pred in re.split(r"(?i)\bAND\b", m.group("preds")):
            pred = pred.strip()
            if not pred:
                continue
            if t := cls._COLUMN_PROBE_TABLE_RE.match(pred):
                table = t.group("t").rpartition(".")[2]
            elif c := cls._COLUMN_PROBE_NAME_RE.match(pred):
                column = c.group("c")
            elif cls._COLUMN_PROBE_DEFAULT_RE.match(pred):
                has_default = True
            else:
                return None  # unrecognized predicate: no faithful mapping
        if not table or not column:
            return None
        return {"table": table, "column": column, "has_default": has_default}

    _GUARD_ELSE_PRINT_RE = re.compile(r"(?is)^PRINT\s+(?P<expr>.+?)\s*;?\s*$")

    def _guard_else_print(
        self,
        else_body: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> str | None:
        """Translate a guard's PRINT-only ELSE branch into the target's
        diagnostic statement (DBMS_OUTPUT / RAISE NOTICE / SELECT), routing
        the message expression through the normal DML pipeline so operators
        like the T-SQL ``+`` concatenation are converted. Returns None when
        the branch is not a single PRINT or its expression does not translate
        cleanly — the caller then warns it as dropped."""
        if not else_body:
            return None
        m = self._GUARD_ELSE_PRINT_RE.match(else_body.strip())
        if m is None or ";" in m.group("expr"):
            return None
        probe = self._transpile_dml(
            f"SELECT {m.group('expr')}", source, target, source_dialect, target_dialect
        )
        if probe.warnings or probe.unsupported:
            return None
        sql = probe.sql.strip().rstrip(";").strip()
        sm = re.match(r"(?is)^SELECT\s+(?P<e>.+?)(?:\s+FROM\s+DUAL)?\s*$", sql)
        if sm is None:
            return None
        expr = sm.group("e").strip()
        if target == "oracle":
            return f"DBMS_OUTPUT.PUT_LINE({expr})"
        if target == "postgresql":
            return f"RAISE NOTICE '%', {expr}"
        if target == "mysql":
            return f"SELECT {expr}"
        return None

    def _faithful_catalog_guard(
        self,
        result: TranspileResult,
        condition: str,
        polarity: str,
        source: str,
        target: str,
        else_body: str = "",
        else_stmt: str | None = None,
    ) -> TranspileResult | None:
        """Translate a recognized catalog probe to the target's catalog and
        wrap the transpiled body in the target's conditional block (doc-04
        P2: the guard's *condition* survives, not just its idempotent
        intent). A carried ELSE diagnostic (``else_stmt``) rides in the
        conditional's ELSE slot; an ELSE branch with no carried form is
        warned as dropped. Returns None when the condition or body has no
        faithful form (the caller then warns the guard as dropped)."""
        if target not in ("postgresql", "oracle", "mysql") or not condition:
            return None
        probe = self._parse_column_probe(condition)
        if probe is None:
            return None
        body = result.sql.strip()
        # Plain statements only: a body that is itself a block cannot be
        # nested mechanically. Oracle and MySQL additionally allow just one
        # statement (it goes through a single EXECUTE IMMEDIATE / PREPARE).
        if not body or "$$" in body or body.startswith("--"):
            return None
        if target in ("oracle", "mysql") and body.count(";") > 1:
            return None
        table, column = str(probe["table"]), str(probe["column"])
        default_pred = bool(probe["has_default"])
        exists = "EXISTS" if polarity == "present" else "NOT EXISTS"
        if target == "postgresql":
            sql = _pg_column_guard(body, table, column, default_pred, exists, else_stmt)
        elif target == "mysql":
            sql = _mysql_column_guard(
                body, table, column, default_pred, exists, else_stmt
            )
        else:
            sql = _oracle_column_guard(
                body, table, column, default_pred, polarity, else_stmt
            )
        guarded = TranspileResult(
            sql=sql, warnings=result.warnings, unsupported=result.unsupported
        )
        if not else_stmt:
            guarded = _warn_guard_else_dropped(guarded, else_body, source, target)
        return guarded

    @staticmethod
    def _warn_guard_dropped(
        result: TranspileResult, source: str, target: str, else_body: str = ""
    ) -> TranspileResult:
        """Record that a catalog guard's condition was dropped.

        The guarded statement itself is emitted (its {target} form is usually
        re-runnable, which was the guard's main purpose), but the condition is
        gone: a statement like ``SET DEFAULT`` now runs unconditionally and
        would overwrite state the T-SQL guard preserved. That semantic
        difference must be reported, never silent (no-silent-loss)."""
        head = " ".join(result.sql.strip().split())[:60]
        dropped = TranspileResult(
            sql=result.sql,
            warnings=[
                *result.warnings,
                _warn(
                    "existence guard dropped: the guarded statement has no "
                    f"conditional form on {target} and now runs "
                    f"unconditionally: {head}",
                    "guard_dropped",
                    source,
                    target,
                    code="UNIQUE-1225",
                ),
            ],
            unsupported=result.unsupported,
        )
        return _warn_guard_else_dropped(dropped, else_body, source, target)

    def _transpile_drop_guard(
        self, kind: str, name: str, source: str, target: str
    ) -> TranspileResult:
        """Convert a T-SQL 'IF OBJECT_ID(...) IS NOT NULL DROP x' guard."""
        kind = kind.upper()
        # Bare object name: brackets/quotes and the dbo qualifier are T-SQL-only.
        clean = re.sub(r'[\[\]"]', "", name)
        clean = re.sub(r"(?i)^dbo\.", "", clean)
        # T-SQL's DROP INDEX names the index as <table>.<index>; every other
        # engine wants the bare index name (MySQL takes the table in an ON
        # clause instead).
        index_table = ""
        if kind == "INDEX" and "." in clean:
            index_table, _, clean = clean.rpartition(".")
        if target == "mysql" and kind == "INDEX":
            # MySQL has no DROP INDEX IF EXISTS: emit the unconditional form
            # with the guard-dropped warning (same policy as its CREATE INDEX
            # guard).
            on_clause = f" ON {index_table}" if index_table else ""
            return self._warn_guard_dropped(
                TranspileResult(sql=f"DROP INDEX {clean}{on_clause};"),
                source,
                target,
            )
        if target == "mysql" and kind == "SEQUENCE":
            # MySQL has no sequences; keep the documented degradation the
            # CREATE SEQUENCE counterpart also emits.
            return self._transpile_set_option(
                f"IF OBJECT_ID DROP SEQUENCE {clean}", source, target
            )
        if target == "oracle":
            # No DROP ... IF EXISTS before 23c; a tolerant block is the idiom.
            return TranspileResult(
                sql=(
                    "BEGIN\n"
                    f"    EXECUTE IMMEDIATE 'DROP {kind} {clean}';\n"
                    "EXCEPTION\n"
                    "    WHEN OTHERS THEN NULL;  -- object did not exist\n"
                    "END;"
                )
            )
        if target == "postgresql" and kind == "TRIGGER":
            # PostgreSQL's DROP TRIGGER needs the table name, which the T-SQL
            # guard does not carry; resolve it from the catalog.
            return TranspileResult(
                sql=(
                    "DO $$\n"
                    "DECLARE r RECORD;\n"
                    "BEGIN\n"
                    "    FOR r IN SELECT tgname, tgrelid::regclass AS tbl\n"
                    "             FROM pg_trigger\n"
                    f"             WHERE tgname = '{clean.lower()}'"
                    " AND NOT tgisinternal LOOP\n"
                    "        EXECUTE format('DROP TRIGGER %I ON %s',"
                    " r.tgname, r.tbl);\n"
                    "    END LOOP;\n"
                    "END $$;"
                )
            )
        return TranspileResult(sql=f"DROP {kind} IF EXISTS {clean}")

    def _transpile_set_batch(
        self,
        sql: str,
        source: str,
        target: str,
        source_dialect: Dialect,
        target_dialect: Dialect,
    ) -> TranspileResult:
        """Degrade a SET-option batch, but first split any ``;``-separated
        statement that FOLLOWS a session-option SET so it still transpiles.

        ``SET NOCOUNT ON; SELECT 1`` used to comment BOTH lines out, dropping
        the valid SELECT (no-silent-loss). This is the direct neighbor of the
        EXEC-system-proc ``;``-split above: peel each statement, degrade only
        the SET(s), and route every other statement through the normal path.
        Only fires for a T-SQL source whose leading segment is a real session
        SET and that has a following statement — a lone SET or a guard batch
        keeps its existing whole-batch handling.
        """
        if source == "tsql" and target != "tsql":
            from unique.core.batch_splitter import _SET_PATTERN
            from unique.core.sql_split import _split_semicolons

            trivia, code = split_leading_trivia(sql)
            segs = [s for s in _split_semicolons(code, dollar_quote=False) if s.strip()]
            if len(segs) > 1 and _SET_PATTERN.match(segs[0]):
                parts: list[str] = []
                warnings: list[TransformWarning] = []
                unsupported: list[str] = []
                for st in segs:
                    _, seg_code = split_leading_trivia(st)
                    if _SET_PATTERN.match(seg_code):
                        sub = self._transpile_set_option(st, source, target)
                    else:
                        sub = self._transpile_dml(
                            st, source, target, source_dialect, target_dialect
                        )
                    parts.append(sub.sql)
                    warnings.extend(sub.warnings)
                    unsupported.extend(sub.unsupported)
                body = "\n".join(parts)
                return TranspileResult(
                    sql=f"{trivia.rstrip()}\n{body}" if trivia.strip() else body,
                    warnings=warnings,
                    unsupported=unsupported,
                )
        return self._transpile_set_option(sql, source, target)

    def _transpile_set_option(
        self, sql: str, source: str, target: str
    ) -> TranspileResult:
        """Handle SET options like SET NOCOUNT ON.

        This is also the comment-out fallback for batches the guard
        recognizers could not extract; those must be labelled honestly (an
        unrecognized batch, not a "SET option") and registered as unsupported
        — an executable statement reduced to a comment with a misleading
        warning is a no-silent-loss violation (audit 2026-07-08, RC1/RC4).
        """
        if target == "oracle" and source != "oracle":
            _, _rc_code = split_leading_trivia(sql)
            # READ COMMITTED is Oracle's DEFAULT isolation level, and its SET
            # TRANSACTION must be the transaction's FIRST statement — keeping
            # this one would block a following mapped SET TRANSACTION mode
            # statement (ORA-01453). Note the no-op.
            if re.match(
                r"(?is)^\s*SET\s+TRANSACTION\s+ISOLATION\s+LEVEL\s+READ\s+"
                r"COMMITTED\s*;?\s*$",
                _rc_code,
            ):
                return TranspileResult(
                    sql=(
                        "-- UNIQUE-1214: READ COMMITTED is Oracle's default "
                        "isolation level (no-op; noted so a following SET "
                        "TRANSACTION mode statement can still open the "
                        "transaction)"
                    ),
                    warnings=[
                        _warn(
                            "SET TRANSACTION ISOLATION LEVEL READ COMMITTED "
                            "is Oracle's default — noted as a comment",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                    unsupported=[],
                )
        if target == "tsql" and source != "tsql":
            # SET ROLE is real SQL on PG/MySQL/Oracle but T-SQL has no
            # such statement (role membership / EXECUTE AS) — wave 139.
            _, role_code = split_leading_trivia(sql)
            if re.match(r"(?is)^\s*SET\s+ROLE\b", role_code):
                commented = "\n".join(
                    f"-- {line}" if line.strip() else ""
                    for line in sql.strip().splitlines()
                )
                return TranspileResult(
                    sql=(
                        "-- UNIQUE-1215: T-SQL has no SET ROLE (use role "
                        "membership / EXECUTE AS); statement preserved "
                        f"as a comment.\n{commented}"
                    ),
                    warnings=[
                        _warn(
                            "SET ROLE commented out (no T-SQL equivalent)",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                )
        if source == "postgresql" and target != "postgresql":
            _, sc_code = split_leading_trivia(sql)
            # SET CONSTRAINTS is real SQL on PG and Oracle; MySQL/T-SQL have
            # no deferred-constraint toggling (zero push).
            if re.match(r"(?is)^\s*SET\s+CONSTRAINTS?\b", sc_code) and target in (
                "mysql",
                "tsql",
            ):
                commented = "\n".join(
                    f"-- {line}" if line.strip() else ""
                    for line in sql.strip().splitlines()
                )
                return TranspileResult(
                    sql=(
                        f"-- UNIQUE-1216: {target} has no deferred-constraint "
                        f"toggling (SET CONSTRAINTS); statement preserved "
                        f"as a comment.\n{commented}"
                    ),
                    warnings=[
                        _warn(
                            "SET CONSTRAINTS commented out "
                            f"(no {target} equivalent)",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                )
            # PostgreSQL session GUCs (SET name = v / TO v, RESET name):
            # engine-local knobs with no meaning elsewhere — the largest
            # class of the pg-source baseline (they error on every engine).
            _, code = split_leading_trivia(sql)
            if re.match(r"(?is)^\s*SET\s+SESSION\s+AUTHORIZATION\b", code):
                commented = "\n".join(
                    f"-- {line}" if line.strip() else ""
                    for line in sql.strip().splitlines()
                )
                return TranspileResult(
                    sql=(
                        f"-- UNIQUE-1217: SET SESSION AUTHORIZATION has no "
                        f"{target} equivalent; switch users natively.\n"
                        f"{commented}"
                    ),
                    warnings=[
                        _warn(
                            "SET SESSION AUTHORIZATION commented out "
                            f"(no {target} equivalent)",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                )
            if re.match(
                r"(?is)^\s*(?:SET\s+(?:LOCAL\s+|SESSION\s+(?!AUTHORIZATION\b))?"
                r"(?!TRANSACTION\b|CONSTRAINTS\b|ROLE\b|TIME\s+ZONE\b)"
                r"[A-Za-z_][\w.]*\s*(?:=|\bTO\b)|RESET\s+[A-Za-z_])",
                code,
            ):
                commented = "\n".join(
                    f"-- {line}" if line.strip() else ""
                    for line in sql.strip().splitlines()
                )
                head = " ".join(code.strip().split())[:60]
                return TranspileResult(
                    sql=(
                        f"-- UNIQUE-1218: PostgreSQL session setting has no "
                        f"{target} equivalent; configure the session "
                        f"natively.\n{commented}"
                    ),
                    warnings=[
                        _warn(
                            f"PostgreSQL session setting commented out: {head}",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                )
        if source == "mysql" and target != "mysql":
            # MySQL session knobs: SET @@var / SET GLOBAL|SESSION|PERSIST /
            # bare SET name = (system variables — user vars need '@'), and
            # any SET whose value reads an @@ system variable (the
            # save/restore pattern). Engine-local; no meaning elsewhere.
            _, code = split_leading_trivia(sql)
            is_knob = bool(
                re.match(
                    r"(?is)^\s*SET\s+(?:@@|(?:GLOBAL|SESSION|LOCAL|PERSIST)\b)",
                    code,
                )
                or re.match(r"(?is)^\s*SET\s+[A-Za-z_][\w.]*\s*=", code)
                or re.match(r"(?is)^\s*SET\s+(?:NAMES|CHARACTER\s+SET|CHARSET)\b", code)
                or (re.match(r"(?is)^\s*SET\b", code) and "@@" in code)
                or re.match(
                    r"(?is)^(?:FLUSH|LOCK\s+TABLES|UNLOCK\s+TABLES|"
                    r"ANALYZE\s+TABLE|OPTIMIZE\s+TABLE|REPAIR\s+TABLE|"
                    r"CHECK\s+TABLE|CHECKSUM\s+TABLE)\b",
                    code,
                )
            )
            if is_knob:
                commented = "\n".join(
                    f"-- {line}" if line.strip() else ""
                    for line in sql.strip().splitlines()
                )
                head = " ".join(code.strip().split())[:60]
                return TranspileResult(
                    sql=(
                        f"-- UNIQUE-1219: MySQL session setting has no {target} "
                        f"equivalent; configure the session natively.\n"
                        f"{commented}"
                    ),
                    warnings=[
                        _warn(
                            f"MySQL session setting commented out: {head}",
                            "set_option",
                            source,
                            target,
                        )
                    ],
                )
        if source == "tsql" and target != "tsql":
            commented = "\n".join(
                f"-- {line}" if line.strip() else ""
                for line in sql.strip().splitlines()
            )
            _, code = split_leading_trivia(sql)
            head = " ".join(code.strip().split())[:60]
            if re.match(r"(?i)^\s*SET\b", code):
                return TranspileResult(
                    sql=commented,
                    warnings=[
                        _warn(
                            f"SET option commented out: {head}",
                            "set_option",
                            source,
                            target,
                            code="UNIQUE-1223",
                        )
                    ],
                )
            message = (
                f"batch commented out (unrecognized migration-guard shape): {head}"
            )
            return TranspileResult(
                sql=commented,
                warnings=[
                    _warn(
                        message,
                        "unhandled_batch",
                        source,
                        target,
                        code="UNIQUE-1224",
                    )
                ],
                unsupported=[message],
            )
        if source == "oracle" and target != "oracle":
            # A SQL*Plus client directive (SET SERVEROUTPUT ON, SET DEFINE
            # OFF, …): no server-side meaning anywhere, including Oracle
            # itself. Document it instead of shipping it raw (it is a syntax
            # error on every target — ~940 statements per direction on the
            # real dump, audit 2026-07-08 sweep).
            commented = "\n".join(
                f"-- {line}" if line.strip() else ""
                for line in sql.strip().splitlines()
            )
            head = " ".join(sql.strip().split())[:60]
            return TranspileResult(
                sql=commented,
                warnings=[
                    _warn(
                        f"SQL*Plus directive commented out: {head}",
                        "set_option",
                        source,
                        target,
                        code="UNIQUE-1223",
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
        if batch_type == BatchType.COMMENT:
            # A comment batch (incl. a whole /* … */ block) carries no statement to
            # terminate; appending ``;`` would corrupt it (``*/;``).
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
        # A batch may hold several routines (e.g. a multi-event trigger split
        # into one trigger per event); each needs its own '$$' terminator.
        body = re.sub(
            r"(?m)^END\n\n(?=CREATE\s+(?:TRIGGER|PROCEDURE|FUNCTION)\b)",
            "END$$\n\n",
            body,
        )
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
        """List all available dialect names (valid as a transpilation source)."""
        return self.registry.available()

    def source_only_dialects(self) -> list[str]:
        """Dialects that may only be a source (import-only), never a target."""
        return [
            name
            for name in self.registry.available()
            if self.registry.get(name).source_only
        ]

    def _validate_output_live(
        self, output_sql: str, target: str, url: str
    ) -> tuple[str, list[TransformWarning]]:
        """Degrade statements the live target engine rejects to carriers.

        The sqlglot output gate is lenient; the engine's verdict is final.
        Side-effect free per engine (see ``core.live_validate``)."""
        from unique.core.live_validate import validate_statements
        from unique.core.sql_split import is_executable, split_statements

        statements = [
            st for st in split_statements(output_sql, target) if is_executable(st)
        ]
        if not statements:
            return output_sql, []
        verdicts = validate_statements(url, target, statements)
        warnings: list[TransformWarning] = []
        for st, err in zip(statements, verdicts, strict=True):
            if err is None:
                continue
            first_err = err.splitlines()[0][:160]
            commented = "\n".join(f"-- {line}" for line in st.strip().splitlines())
            carrier = (
                f"-- UNIQUE-1220: live {target} validation rejected this "
                f"statement ({first_err}); preserved as a comment:\n"
                f"{commented}"
            )
            if st in output_sql:
                output_sql = output_sql.replace(st, carrier, 1)
            warnings.append(
                _warn(
                    f"live {target} validation rejected a statement: " f"{first_err}",
                    "live_validation",
                    "",
                    target,
                )
            )
        return output_sql, warnings


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
