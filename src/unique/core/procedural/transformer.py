# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL transformer.

Transforms procedural IR AST nodes between dialects, handling
differences in variable naming, control flow syntax, data types,
built-in functions, and idiomatic patterns.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import cast

import sqlglot

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CommentStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    CursorDeclaration,
    CursorOperation,
    DataType,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
    ExceptionHandler,
    ExecuteStatement,
    ExitStatement,
    ForLoopStatement,
    IfStatement,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SelectIntoStatement,
    SetVariableStatement,
    StatementList,
    TryCatchBlock,
    WhileStatement,
)

logger = logging.getLogger(__name__)

# Data type mapping tables
_TSQL_TO_ORACLE_TYPES: dict[str, str] = {
    "INT": "NUMBER(10)",
    "INTEGER": "NUMBER(10)",
    "BIGINT": "NUMBER(19)",
    "SMALLINT": "NUMBER(5)",
    "TINYINT": "NUMBER(3)",
    "BIT": "NUMBER(1)",
    "FLOAT": "FLOAT",
    "REAL": "FLOAT",
    "DECIMAL": "NUMBER",
    "NUMERIC": "NUMBER",
    "MONEY": "NUMBER(19,4)",
    "SMALLMONEY": "NUMBER(10,4)",
    "VARCHAR": "VARCHAR2",
    "NVARCHAR": "NVARCHAR2",
    "CHAR": "CHAR",
    "NCHAR": "NCHAR",
    "TEXT": "CLOB",
    "NTEXT": "NCLOB",
    "IMAGE": "BLOB",
    "BINARY": "RAW",
    "VARBINARY": "RAW",
    "DATETIME": "DATE",
    "DATETIME2": "TIMESTAMP",
    "DATE": "DATE",
    "TIME": "TIMESTAMP",
    "SMALLDATETIME": "DATE",
    "UNIQUEIDENTIFIER": "RAW(16)",
    "XML": "XMLTYPE",
    "SQL_VARIANT": "ANYDATA",
}

_ORACLE_TO_TSQL_TYPES: dict[str, str] = {
    "NUMBER": "DECIMAL",
    "VARCHAR2": "NVARCHAR",
    "NVARCHAR2": "NVARCHAR",
    "CLOB": "NVARCHAR(MAX)",
    "NCLOB": "NVARCHAR(MAX)",
    "BLOB": "VARBINARY(MAX)",
    "RAW": "VARBINARY",
    "DATE": "DATETIME",
    "TIMESTAMP": "DATETIME2",
    "XMLTYPE": "XML",
    "BOOLEAN": "BIT",
    "PLS_INTEGER": "INT",
    "BINARY_INTEGER": "INT",
    "ANYDATA": "SQL_VARIANT",
}

_ORACLE_TO_PG_TYPES: dict[str, str] = {
    "NUMBER": "NUMERIC",
    "VARCHAR2": "VARCHAR",
    "NVARCHAR2": "VARCHAR",
    "CLOB": "TEXT",
    "NCLOB": "TEXT",
    "BLOB": "BYTEA",
    "RAW": "BYTEA",
    "LONG": "TEXT",
    "DATE": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
    "XMLTYPE": "XML",
    "BOOLEAN": "BOOLEAN",
    "PLS_INTEGER": "INTEGER",
    "BINARY_INTEGER": "INTEGER",
    "BINARY_FLOAT": "REAL",
    "BINARY_DOUBLE": "DOUBLE PRECISION",
}

_ORACLE_TO_MYSQL_TYPES: dict[str, str] = {
    "NUMBER": "DECIMAL",
    "VARCHAR2": "VARCHAR",
    "NVARCHAR2": "VARCHAR",
    "CLOB": "LONGTEXT",
    "NCLOB": "LONGTEXT",
    "BLOB": "LONGBLOB",
    "RAW": "VARBINARY",
    "LONG": "LONGTEXT",
    "DATE": "DATETIME",
    "TIMESTAMP": "DATETIME",
    "XMLTYPE": "TEXT",
    "BOOLEAN": "TINYINT(1)",
    "PLS_INTEGER": "INT",
    "BINARY_INTEGER": "INT",
    "BINARY_FLOAT": "FLOAT",
    "BINARY_DOUBLE": "DOUBLE",
}

_TSQL_TO_PG_TYPES: dict[str, str] = {
    "INT": "INTEGER",
    "BIGINT": "BIGINT",
    "SMALLINT": "SMALLINT",
    "TINYINT": "SMALLINT",
    "BIT": "BOOLEAN",
    "FLOAT": "DOUBLE PRECISION",
    "REAL": "REAL",
    "MONEY": "NUMERIC(19,4)",
    "DATETIME": "TIMESTAMP",
    "DATETIME2": "TIMESTAMP",
    "SMALLDATETIME": "TIMESTAMP",
    "UNIQUEIDENTIFIER": "UUID",
    "TEXT": "TEXT",
    "NTEXT": "TEXT",
    "IMAGE": "BYTEA",
    "BINARY": "BYTEA",
    "VARBINARY": "BYTEA",
    "VARCHAR": "VARCHAR",
    "NVARCHAR": "VARCHAR",
    "XML": "XML",
}

_TSQL_TO_MYSQL_TYPES: dict[str, str] = {
    "INT": "INT",
    "INTEGER": "INT",
    "BIGINT": "BIGINT",
    "SMALLINT": "SMALLINT",
    "TINYINT": "TINYINT",
    "BIT": "TINYINT(1)",
    "FLOAT": "DOUBLE",
    "REAL": "FLOAT",
    "DECIMAL": "DECIMAL",
    "NUMERIC": "DECIMAL",
    "MONEY": "DECIMAL(19,4)",
    "SMALLMONEY": "DECIMAL(10,4)",
    "DATETIME": "DATETIME",
    "DATETIME2": "DATETIME",
    "SMALLDATETIME": "DATETIME",
    "DATE": "DATE",
    "TIME": "TIME",
    "UNIQUEIDENTIFIER": "CHAR(36)",
    "VARCHAR": "VARCHAR",
    "NVARCHAR": "VARCHAR",
    "CHAR": "CHAR",
    "NCHAR": "CHAR",
    "TEXT": "TEXT",
    "NTEXT": "LONGTEXT",
    "IMAGE": "LONGBLOB",
    "BINARY": "BINARY",
    "VARBINARY": "VARBINARY",
    "XML": "TEXT",
    # SQL_VARIANT stores values of various scalar types. MySQL has no variant
    # type; LONGTEXT is the most permissive carrier that preserves arbitrary
    # scalar values (callers compare/convert as needed), keeping functionality
    # rather than dropping the column/parameter.
    "SQL_VARIANT": "LONGTEXT",
}

# Function mapping tables
_TSQL_TO_ORACLE_FUNCS: dict[str, str] = {
    "GETUTCDATE": "SYS_EXTRACT_UTC(SYSTIMESTAMP)",
    "ISNULL": "NVL",
    "LEN": "LENGTH",
    "NEWID": "SYS_GUID",
    "UPPER": "UPPER",
    "LOWER": "LOWER",
    "LTRIM": "LTRIM",
    "RTRIM": "RTRIM",
    "REPLACE": "REPLACE",
    "SUBSTRING": "SUBSTR",
    "CEILING": "CEIL",
    "SQUARE": "-- SQUARE(x) -> x*x",
    "DATEDIFF": "-- DATEDIFF requires manual conversion",
    "DATEADD": "-- DATEADD requires manual conversion",
}

_ORACLE_TO_TSQL_FUNCS: dict[str, str] = {
    "NVL": "ISNULL",
    "LENGTH": "LEN",
    "SYS_GUID": "NEWID",
    "SUBSTR": "SUBSTRING",
    "CEIL": "CEILING",
    "TO_CHAR": "CONVERT",
    "TO_DATE": "CONVERT",
    "TO_NUMBER": "CAST",
    "TRUNC": "-- TRUNC requires manual conversion",
}

_TSQL_TO_PG_FUNCS: dict[str, str] = {
    "GETUTCDATE": "NOW() AT TIME ZONE 'UTC'",
    "ISNULL": "COALESCE",
    "LEN": "LENGTH",
    "NEWID": "GEN_RANDOM_UUID",
    "SUBSTRING": "SUBSTRING",
    "UPPER": "UPPER",
    "LOWER": "LOWER",
    "REPLACE": "REPLACE",
    "CEILING": "CEIL",
    "DATEDIFF": "-- DATEDIFF requires manual conversion",
    "DATEADD": "-- DATEADD requires interval arithmetic",
}

_PG_TO_TSQL_FUNCS: dict[str, str] = {
    "COALESCE": "COALESCE",
    "LENGTH": "LEN",
    "GEN_RANDOM_UUID": "NEWID",
    "CEIL": "CEILING",
}

_TSQL_TO_MYSQL_FUNCS: dict[str, str] = {
    "GETUTCDATE": "UTC_TIMESTAMP",
    "ISNULL": "IFNULL",
    "LEN": "CHAR_LENGTH",
    "NEWID": "UUID",
    "SUBSTRING": "SUBSTRING",
    "UPPER": "UPPER",
    "LOWER": "LOWER",
    "REPLACE": "REPLACE",
    "CEILING": "CEILING",
    "DATEDIFF": "-- DATEDIFF differs (MySQL DATEDIFF returns days)",
    "DATEADD": "-- DATEADD -> DATE_ADD with INTERVAL",
}

_MYSQL_TO_TSQL_FUNCS: dict[str, str] = {
    "IFNULL": "ISNULL",
    "CHAR_LENGTH": "LEN",
    "LENGTH": "LEN",
    "UUID": "NEWID",
}

_ORACLE_TO_PG_FUNCS: dict[str, str] = {
    "NVL": "COALESCE",
    "LENGTH": "LENGTH",
    "SYS_GUID": "GEN_RANDOM_UUID",
    "SUBSTR": "SUBSTRING",
    "TO_CHAR": "TO_CHAR",
    "TO_DATE": "TO_DATE",
    "TO_NUMBER": "-- TO_NUMBER -> CAST(... AS NUMERIC)",
}

_ORACLE_TO_MYSQL_FUNCS: dict[str, str] = {
    "NVL": "IFNULL",
    "LENGTH": "CHAR_LENGTH",
    "SYS_GUID": "UUID",
    "SUBSTR": "SUBSTRING",
}


class ProceduralTransformer:
    """Transforms procedural AST nodes between SQL dialects.

    Handles variable naming conventions, data type mappings,
    control flow syntax differences, and built-in function translations.

    This base holds the engine-agnostic and source-dependent logic plus the
    default behavior. Target-specific specifics live in per-target subclasses
    (`TSqlTransformer`, `OracleTransformer`, `PostgresTransformer`,
    `MySqlTransformer`), which override only what differs for that target.
    Unlike the emitter, the transformer is a source→target operation: logic
    that depends on the *pair* or only on the *source* stays in the base and is
    parameterized by ``self._source`` rather than pushed into a target subclass.
    Instantiating ``ProceduralTransformer(source, target)`` returns the right
    target subclass via ``__new__``, so existing call sites need no change.
    """

    #: Set on each subclass; the target dialect it handles.
    target_name: str | None = None

    def __new__(
        cls,
        source: str,
        target: str,
        metadata_resolver: object | None = None,
    ) -> ProceduralTransformer:
        if cls is ProceduralTransformer:
            subclass = _TRANSFORMER_REGISTRY.get(target)
            if subclass is not None:
                return object.__new__(subclass)
        return object.__new__(cls)

    def __init__(
        self,
        source: str,
        target: str,
        metadata_resolver: object | None = None,
    ) -> None:
        self._source = source
        self._target = target
        self._metadata = metadata_resolver
        self._warnings: list[str] = []
        self._var_map: dict[str, str] = {}
        # Names (transformed form) of variables/parameters declared with a
        # string type. Used to disambiguate T-SQL '+' as concatenation when no
        # string literal is present (e.g. SHA2(@a + @b) over two text vars).
        self._string_vars: set[str] = set()
        # True while transforming a trigger body, so embedded DML maps the
        # T-SQL inserted/deleted pseudo-tables to NEW/OLD (or documents a
        # set-based use that has no row-level equivalent).
        self._in_trigger = False

    @staticmethod
    def _is_string_type(dt: DataType) -> bool:
        base = dt.name.split("(")[0].strip().upper()
        return base in {
            "CHAR",
            "NCHAR",
            "VARCHAR",
            "NVARCHAR",
            "VARCHAR2",
            "NVARCHAR2",
            "TEXT",
            "NTEXT",
            "LONGTEXT",
            "MEDIUMTEXT",
            "TINYTEXT",
            "CLOB",
            "NCLOB",
        }

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def transform(self, node: ASTNode) -> ASTNode:
        """Transform a procedural AST node from source to target dialect.

        Args:
            node: The source-dialect AST node.

        Returns:
            The target-dialect AST node.
        """
        if self._source == self._target:
            return node
        return self._transform_node(node)

    def _transform_node(self, node: ASTNode) -> ASTNode:
        """Dispatch transformation based on node type."""
        handlers: dict[type, Callable[..., ASTNode]] = {
            CreateProcedureStatement: self._transform_procedure,
            AlterProcedureStatement: self._transform_alter_procedure,
            CreateFunctionStatement: self._transform_function,
            CreateTriggerStatement: self._transform_trigger,
            DeclareStatement: self._transform_declare,
            SetVariableStatement: self._transform_set_variable,
            AssignmentStatement: self._transform_assignment,
            IfStatement: self._transform_if,
            WhileStatement: self._transform_while,
            BeginEndBlock: self._transform_begin_end,
            StatementList: self._transform_statement_list,
            TryCatchBlock: self._transform_try_catch,
            ExceptionBlock: self._transform_exception_block,
            ExecuteStatement: self._transform_execute,
            PrintStatement: self._transform_print,
            RaiseErrorStatement: self._transform_raise_error,
            ReturnStatement: self._transform_return,
            CursorDeclaration: self._transform_cursor_decl,
            CursorOperation: self._transform_cursor_op,
            ForLoopStatement: self._transform_for_loop,
            LoopStatement: self._transform_loop,
            ExitStatement: self._transform_exit,
            EmbeddedDML: self._transform_embedded_dml,
            SelectIntoStatement: self._transform_select_into,
            NullStatement: self._transform_null,
            RawSQL: self._transform_raw_sql,
        }

        handler = handlers.get(type(node))
        if handler:
            return handler(node)
        return node

    def _transform_body(self, stmts: tuple[ASTNode, ...]) -> tuple[ASTNode, ...]:
        """Transform a sequence of body statements."""
        result: list[ASTNode] = []
        for stmt in stmts:
            transformed = self._transform_node(stmt)
            result.append(self._preserve_dropped_set_option(transformed))
        return tuple(result)

    def _preserve_dropped_set_option(self, node: ASTNode) -> ASTNode:
        """Turn a dropped dialect-specific SET option into a comment.

        Options like ``SET NOCOUNT ON`` have no equivalent in the target, but
        silently removing them can leave an empty block (e.g. ``IF ... THEN END
        IF``) that the engine rejects, and erases information. Replace the
        statement with a ``/* UNIQUE: <original> */`` comment so the original is
        documented and the block keeps a (no-op) body.
        """
        if isinstance(node, RawSQL) and "SET option" in node.reason:
            return CommentStatement(
                text=f"/* UNIQUE: {node.sql} -- no {self._target} equivalent */",
                style="block",
            )
        return node

    def _transform_params(
        self, params: tuple[ParameterDefinition, ...]
    ) -> tuple[ParameterDefinition, ...]:
        """Transform parameter definitions between dialects."""
        result: list[ParameterDefinition] = []
        for p in params:
            new_name = self._transform_var_name(p.name)
            new_type = self._transform_data_type(p.data_type)
            new_default = self._transform_node(p.default) if p.default else None
            self._var_map[p.name] = new_name
            if self._is_string_type(p.data_type):
                self._string_vars.add(new_name)
            result.append(
                ParameterDefinition(
                    name=new_name,
                    data_type=new_type,
                    direction=p.direction,
                    default=new_default,
                )
            )
        return tuple(result)

    # ---------------------------------------------------------------
    # Variable name transformations
    # ---------------------------------------------------------------

    def _transform_var_name(self, name: str) -> str:
        """Transform variable names between naming conventions."""
        if self._source == "tsql" and self._target in ("oracle", "postgresql"):
            # @varName → V_VARNAME (Oracle) or v_varname (PG)
            clean = name.lstrip("@")
            if self._target == "oracle":
                return f"V_{clean.upper()}"
            return f"v_{clean.lower()}"
        elif self._source == "tsql" and self._target == "mysql":
            # MySQL local variables have no sigil (a leading @ denotes a
            # session variable, which is different). Use a plain name.
            clean = name.lstrip("@")
            return f"v_{clean.lower()}"
        elif self._source in ("oracle", "postgresql") and self._target == "tsql":
            # V_VARNAME or v_varname → @VarName
            clean = name
            if clean.upper().startswith("V_"):
                clean = clean[2:]
            return f"@{clean.lower()}"
        return name

    def _transform_var_in_sql(self, sql: str) -> str:
        """Transform variable references within raw SQL text."""
        if self._source == "tsql" and self._target == "oracle":
            # Strip SQL Server's default schema prefix — Oracle objects live in
            # the current user's schema and don't use "dbo." qualification.
            sql = re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)
        if self._source == "tsql" and self._target in ("oracle", "postgresql"):

            def replace_var(m: re.Match[str]) -> str:
                var = m.group(0)
                if var.startswith("@@"):
                    return self._transform_system_var(var)
                clean = var.lstrip("@")
                if self._target == "oracle":
                    return f"V_{clean.upper()}"
                return f"v_{clean.lower()}"

            sql = re.sub(r"@@?\w+", replace_var, sql)
        elif self._source == "tsql" and self._target == "mysql":

            def replace_var_mysql(m: re.Match[str]) -> str:
                var = m.group(0)
                if var.startswith("@@"):
                    return self._transform_system_var(var)
                clean = var.lstrip("@")
                return f"v_{clean.lower()}"

            sql = re.sub(r"@@?\w+", replace_var_mysql, sql)
        elif self._source in ("oracle", "postgresql") and self._target == "tsql":
            for old_name, new_name in self._var_map.items():
                sql = re.sub(rf"\b{re.escape(old_name)}\b", new_name, sql)
        return sql

    def _transform_system_var(self, var: str) -> str:
        """Transform system variables like @@ROWCOUNT, @@IDENTITY, @@ERROR.

        ``@@ERROR``/``@@TRANCOUNT`` express T-SQL's imperative per-statement
        error/transaction-depth checks, which the other engines have no direct
        equivalent for (they use exception handlers). Emitting a bare comment in
        their place left an invalid expression (e.g. ``IF /* @@ERROR */ <> 0``),
        so a neutral ``0`` carrying an inline block comment is used instead — the
        routine stays syntactically valid and the limitation is documented.
        """
        upper = var.upper()
        mapping = self._system_var_map()
        if not mapping:
            return var
        return mapping.get(upper, f"/* {var} */")

    def _neutral_global(self, name: str, hint: str) -> str:
        """A neutral, syntactically-valid placeholder for a global with no
        faithful equivalent: ``0`` plus an inline block comment (never a line
        comment, which would swallow the rest of an inline condition)."""
        return f"0 /* UNIQUE: {name} has no {self._target} equivalent; {hint} */"

    def _system_var_map(self) -> dict[str, str]:
        """Per-target mapping of T-SQL system globals (@@ROWCOUNT, …). The base
        returns an empty map (no translation); each target subclass overrides."""
        return {}

    def _supports_type_reference(self) -> bool:
        """Whether the target supports ``%TYPE``/``%ROWTYPE`` natively (Oracle).
        Others lower an unresolved reference to a carrier type."""
        return False

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        """Target type for T-SQL ``VARCHAR(MAX)``/``NVARCHAR(MAX)``. The base
        returns None (no change); each target subclass overrides."""
        return None

    # ---------------------------------------------------------------
    # Data type transformations
    # ---------------------------------------------------------------

    def _unknown_type_carrier(self) -> str:
        """Permissive carrier type for an unresolved/non-portable source type.

        Chosen per target so the emitted routine still compiles while the
        original type is preserved in a /* UNIQUE */ comment for the user and
        for a faithful reverse transpilation.
        """
        return {
            "tsql": "SQL_VARIANT",
            "oracle": "ANYDATA",
            "postgresql": "TEXT",
            "mysql": "LONGTEXT",
        }.get(self._target, "VARCHAR")

    def _transform_data_type(self, dt: DataType) -> DataType:
        """Transform a data type between dialects."""
        # A carrier type parsed with its original preserved in a `/* UNIQUE: … */`
        # comment: re-map the *original* for this target. The result keeps the
        # original where the target supports it (faithful round-trip) and
        # re-applies a carrier where it doesn't — handled by the normal path
        # below. (origin_comment is cleared to avoid infinite recursion.)
        if dt.origin_comment:
            return self._transform_data_type(
                DataType(name=dt.origin_comment, params=dt.params)
            )

        type_name = dt.name.upper()

        # Handle %TYPE references
        if "%TYPE" in type_name or "%ROWTYPE" in type_name:
            # If a metadata connection is available, try to resolve to a real
            # column type first.
            if self._metadata is not None and "%TYPE" in type_name:
                try:
                    resolved = self._metadata.resolve_type_reference(  # type: ignore[attr-defined]
                        dt.name
                    )
                    if resolved is not None:
                        return self._transform_data_type(resolved)
                except Exception:  # pragma: no cover - defensive
                    pass
            # Oracle supports %TYPE/%ROWTYPE natively, so keep the reference
            # as-is for an Oracle target (also makes a carrier round-trip back
            # to Oracle faithful) instead of lowering it to a carrier.
            if self._supports_type_reference():
                return DataType(name=dt.name, params=dt.params)
            # Unresolved without a connection: emit a permissive carrier type
            # and preserve the original reference as a comment so the
            # substitution is documented and reversible.
            self._warnings.append(
                f"%TYPE reference '{dt.name}' could not be resolved without a "
                "database connection (use --db-url). Emitted as a carrier type "
                "with the original preserved in a /* UNIQUE */ comment."
            )
            carrier = self._unknown_type_carrier()
            return DataType(name=carrier, origin_comment=dt.name)

        # Handle VARCHAR(MAX) → CLOB/TEXT/LONGTEXT (per target)
        if type_name in ("VARCHAR", "NVARCHAR") and dt.params == (-1,):
            mapped = self._varchar_max_type(type_name == "NVARCHAR")
            if mapped is not None:
                return DataType(name=mapped)

        # Lookup in mapping table
        type_map = self._get_type_map()
        base_type = type_name.split("(")[0].strip()
        if base_type in type_map:
            new_name = type_map[base_type]
            # Source-specific types with no faithful target equivalent: preserve
            # the original in a /* UNIQUE */ comment so the substitution is
            # documented and a reverse transpilation can restore it exactly.
            origin = dt.name if base_type in self._LOSSY_SOURCE_TYPES else None
            # If the mapping includes params (e.g., NUMBER(10)),
            # parse them out
            if "(" in new_name:
                match = re.match(r"(\w+)\((.+)\)", new_name)
                if match:
                    name = match.group(1)
                    params_str = match.group(2).split(",")
                    params = tuple(int(p.strip()) for p in params_str)
                    return DataType(name=name, params=params, origin_comment=origin)
                return DataType(name=new_name, origin_comment=origin)
            return DataType(name=new_name, params=dt.params, origin_comment=origin)

        # A source-specific type with no entry in the target type map (e.g.
        # SQL_VARIANT for PostgreSQL): emit the permissive carrier type and
        # preserve the original in a /* UNIQUE */ comment so it is documented
        # and reversible, instead of leaking an unknown type the engine rejects.
        if base_type in self._LOSSY_SOURCE_TYPES:
            carrier = self._unknown_type_carrier()
            # If the target's carrier is the original type itself, the target
            # supports it natively (e.g. SQL_VARIANT → T-SQL, ANYDATA → Oracle):
            # emit it plainly, with no redundant carrier comment.
            if carrier.upper() == base_type:
                return DataType(name=dt.name, params=dt.params)
            return DataType(name=carrier, origin_comment=dt.name)

        return dt

    # Source types with no faithful equivalent in the other engines: the
    # mapping is a best-effort carrier, so the original is worth preserving.
    _LOSSY_SOURCE_TYPES: frozenset[str] = frozenset(
        {
            "SQL_VARIANT",  # T-SQL variant -> carrier text type
            "ANYDATA",  # Oracle ANYDATA -> carrier
            "XML",  # mapped to TEXT on MySQL (no native XML)
            "XMLTYPE",
            "HIERARCHYID",
            "GEOGRAPHY",
            "GEOMETRY",
        }
    )

    def _get_type_map(self) -> dict[str, str]:
        """Get the appropriate type mapping for source→target."""
        key = f"{self._source}_{self._target}"
        maps = {
            "tsql_oracle": _TSQL_TO_ORACLE_TYPES,
            "oracle_tsql": _ORACLE_TO_TSQL_TYPES,
            "oracle_postgresql": _ORACLE_TO_PG_TYPES,
            "oracle_mysql": _ORACLE_TO_MYSQL_TYPES,
            "tsql_postgresql": _TSQL_TO_PG_TYPES,
            "tsql_mysql": _TSQL_TO_MYSQL_TYPES,
        }
        return maps.get(key, {})

    # ---------------------------------------------------------------
    # Node-specific transformations
    # ---------------------------------------------------------------

    def _target_schema(self, schema: str | None) -> str | None:
        """Return the schema for the target dialect; strip SQL Server's default
        ``dbo`` where the target has no such schema (Oracle)."""
        if schema and schema.lower() == "dbo" and self._strip_dbo_schema():
            return None
        return schema

    def _strip_dbo_schema(self) -> bool:
        """Whether to drop a ``dbo`` schema qualifier for this target. Default
        keep; Oracle overrides to strip."""
        return False

    def _transform_procedure(self, node: CreateProcedureStatement) -> ASTNode:
        new_params = self._transform_params(node.parameters)
        new_body = self._transform_body(node.body)
        or_replace = node.or_replace
        if self._source == "tsql" and self._target in ("oracle", "postgresql"):
            or_replace = True
        return CreateProcedureStatement(
            name=node.name,
            parameters=new_params,
            body=new_body,
            or_replace=or_replace,
            schema=self._target_schema(node.schema),
        )

    def _transform_alter_procedure(self, node: AlterProcedureStatement) -> ASTNode:
        """Transform ALTER PROCEDURE (T-SQL) → CREATE OR REPLACE (others)."""
        new_params = self._transform_params(node.parameters)
        new_body = self._transform_body(node.body)
        if self._alter_becomes_create():
            return CreateProcedureStatement(
                name=node.name,
                parameters=new_params,
                body=new_body,
                or_replace=True,
                schema=self._target_schema(node.schema),
            )
        return AlterProcedureStatement(
            name=node.name,
            parameters=new_params,
            body=new_body,
            schema=node.schema,
        )

    def _alter_becomes_create(self) -> bool:
        """Whether ALTER PROCEDURE should become CREATE OR REPLACE on this
        target. Default yes (Oracle/PostgreSQL/MySQL); T-SQL overrides to keep
        ALTER."""
        return True

    def _transform_function(self, node: CreateFunctionStatement) -> ASTNode:
        new_params = self._transform_params(node.parameters)
        new_body = self._transform_body(node.body)
        new_return = (
            self._transform_data_type(node.return_type) if node.return_type else None
        )
        return CreateFunctionStatement(
            name=node.name,
            parameters=new_params,
            return_type=new_return,
            body=new_body,
            or_replace=True if self._target != "tsql" else node.or_replace,
            schema=self._target_schema(node.schema),
        )

    def _transform_trigger(self, node: CreateTriggerStatement) -> ASTNode:
        prev_in_trigger = self._in_trigger
        self._in_trigger = True
        try:
            new_body = self._transform_body(node.body)
        finally:
            self._in_trigger = prev_in_trigger
        timing = node.timing
        if self._source == "tsql" and timing == "FOR":
            timing = "AFTER"
        return CreateTriggerStatement(
            name=node.name,
            table=node.table,
            timing=timing,
            events=node.events,
            for_each=node.for_each,
            body=new_body,
            or_replace=True if self._target == "oracle" else node.or_replace,
            schema=self._target_schema(node.schema),
        )

    def _transform_declare(self, node: DeclareStatement) -> ASTNode:
        new_name = self._transform_var_name(node.name)
        # T-SQL table variables (DECLARE @t TABLE (cols)) have no equivalent
        # declaration in MySQL/Oracle/PostgreSQL. Rewrite to a CREATE TEMPORARY
        # TABLE in the executable body (returning a non-Declare node moves it
        # out of the declaration section). References to @t as a table resolve
        # to the same transformed name.
        if node.data_type.name.upper().startswith("TABLE") and self._target != "tsql":
            self._var_map[node.name] = new_name
            return self._table_variable_to_temp_table(new_name, node.data_type.name)
        new_type = self._transform_data_type(node.data_type)
        new_default = self._transform_node(node.default) if node.default else None
        self._var_map[node.name] = new_name
        if self._is_string_type(node.data_type):
            self._string_vars.add(new_name)
        return DeclareStatement(name=new_name, data_type=new_type, default=new_default)

    def _table_variable_to_temp_table(self, name: str, type_text: str) -> ASTNode:
        """Build a CREATE TEMPORARY TABLE from a captured ``TABLE (cols)`` type.

        The column list is mapped through the project's own DDL converter so
        column data types use the target dialect's portable names (e.g.
        UNIQUEIDENTIFIER → CHAR(36) on MySQL, UUID on PostgreSQL), which is more
        faithful than a raw sqlglot pass. A documenting comment records the
        original table-variable.
        """
        # type_text looks like: "TABLE ( col TYPE, ... )"
        cols = type_text[len("TABLE") :].strip()
        ddl = f"CREATE TABLE {name} {cols}"
        translated = ddl
        try:
            from unique.core.ast_nodes import CreateTableStatement
            from unique.core.converter import _emit_create_table, parse_sql

            nodes = parse_sql(ddl, self._source)
            if nodes and isinstance(nodes[0], CreateTableStatement):
                translated = _emit_create_table(nodes[0], self._target)
        except Exception:
            # Fall back to a raw sqlglot pass if the converter path fails.
            try:
                import sqlglot

                write_dialect = self._get_sqlglot_dialect(self._target)
                out = sqlglot.transpile(ddl, read="tsql", write=write_dialect)
                if out and out[0].strip():
                    translated = out[0]
            except Exception:
                translated = ddl
        # Make it a TEMPORARY table and keep the (already valid) column list.
        translated = re.sub(
            r"(?i)^\s*CREATE\s+TABLE\b",
            "CREATE TEMPORARY TABLE",
            translated.strip(),
            count=1,
        )
        sql = (
            f"{translated.rstrip(';')};  "
            f"/* UNIQUE: was T-SQL table variable {name} */"
        )
        return RawSQL(sql=sql, reason="table variable -> temporary table")

    def _transform_set_variable(self, node: SetVariableStatement) -> ASTNode:
        new_name = self._transform_var_name(node.name)
        new_value = self._transform_node(node.value)
        # SET keeps a SET statement on engines that have one (T-SQL, MySQL);
        # Oracle/PostgreSQL lower it to a ``:=`` assignment.
        if self._uses_set_statement():
            return SetVariableStatement(name=new_name, value=new_value)
        return AssignmentStatement(target=new_name, value=new_value)

    def _transform_assignment(self, node: AssignmentStatement) -> ASTNode:
        new_name = self._transform_var_name(node.target)
        new_value = self._transform_node(node.value)
        # A T-SQL target re-expresses an assignment as SET; the others keep an
        # assignment node (MySQL's is rendered as SET by its emitter).
        if self._assignment_becomes_set():
            return SetVariableStatement(name=new_name, value=new_value)
        return AssignmentStatement(target=new_name, value=new_value)

    def _uses_set_statement(self) -> bool:
        """Whether the target keeps a ``SET`` statement (T-SQL, MySQL) rather
        than lowering it to a ``:=`` assignment (Oracle, PostgreSQL)."""
        return False

    def _assignment_becomes_set(self) -> bool:
        """Whether a bare assignment is re-expressed as a ``SET`` statement.
        Only T-SQL does; the base default keeps it an assignment."""
        return False

    def _transform_if(self, node: IfStatement) -> IfStatement:
        new_cond = self._transform_node(node.condition)
        new_then = self._ensure_non_empty_body(self._transform_body(node.then_body))
        # An ELSE that becomes empty is dropped entirely (valid everywhere);
        # only a non-empty else is kept, and if it has only comments it gets a
        # no-op so the engine accepts it.
        new_else_raw = self._transform_body(node.else_body)
        new_else = self._ensure_non_empty_body(new_else_raw) if node.else_body else ()
        return IfStatement(condition=new_cond, then_body=new_then, else_body=new_else)

    def _ensure_non_empty_body(self, body: tuple[ASTNode, ...]) -> tuple[ASTNode, ...]:
        """Guarantee a block has at least one executable statement.

        A block whose only statement was dropped (e.g. ``SET NOCOUNT ON``)
        becomes comment-only or empty, which ``IF ... THEN END IF`` rejects on
        engines like MySQL. Append a dialect-appropriate no-op so the block
        stays syntactically valid while preserving any documenting comment.
        """
        has_executable = any(not isinstance(s, CommentStatement) for s in body)
        if has_executable:
            return body
        return (*body, self._noop_statement())

    def _noop_statement(self) -> ASTNode:
        """A no-op statement valid in the target dialect. Default is PL/SQL /
        PL-pgSQL ``NULL;``; MySQL overrides with ``DO 0;``."""
        return NullStatement()

    def _transform_while(self, node: WhileStatement) -> WhileStatement:
        new_cond = self._transform_node(node.condition)
        new_body = self._ensure_non_empty_body(self._transform_body(node.body))
        return WhileStatement(condition=new_cond, body=new_body)

    def _transform_begin_end(self, node: BeginEndBlock) -> BeginEndBlock:
        return BeginEndBlock(
            statements=self._ensure_non_empty_body(
                self._transform_body(node.statements)
            )
        )

    def _transform_statement_list(self, node: StatementList) -> StatementList:
        return StatementList(statements=self._transform_body(node.statements))

    def _transform_try_catch(self, node: TryCatchBlock) -> ASTNode:
        """Default keeps a TRY/CATCH block (T-SQL/MySQL/PostgreSQL handle it in
        the emitter); Oracle overrides to a PL/SQL EXCEPTION block."""
        new_try = self._transform_body(node.try_body)
        new_catch = self._transform_body(node.catch_body)
        return TryCatchBlock(try_body=new_try, catch_body=new_catch)

    def _transform_exception_block(self, node: ExceptionBlock) -> ASTNode:
        """Default keeps an EXCEPTION block (Oracle/PostgreSQL); T-SQL overrides
        to a TRY/CATCH (its only structured-handler form)."""
        handlers = tuple(
            ExceptionHandler(
                exception_name=h.exception_name,
                body=self._transform_body(h.body),
            )
            for h in node.handlers
        )
        return ExceptionBlock(handlers=handlers)

    def _transform_execute(self, node: ExecuteStatement) -> ASTNode:
        new_expr = self._transform_node(node.sql_expression)
        new_params = tuple(self._transform_node(p) for p in node.params)
        return ExecuteStatement(sql_expression=new_expr, params=new_params)

    def _transform_print(self, node: PrintStatement) -> PrintStatement:
        return PrintStatement(expression=self._transform_node(node.expression))

    def _transform_raise_error(self, node: RaiseErrorStatement) -> ASTNode:
        new_msg = self._transform_node(node.message) if node.message else None
        return RaiseErrorStatement(
            message=new_msg, severity=node.severity, state=node.state
        )

    def _transform_return(self, node: ReturnStatement) -> ReturnStatement:
        new_value = self._transform_node(node.value) if node.value else None
        return ReturnStatement(value=new_value)

    def _transform_cursor_decl(self, node: CursorDeclaration) -> CursorDeclaration:
        new_name = self._transform_var_name(node.name)
        new_query = self._transform_node(node.query) if node.query else None
        return CursorDeclaration(name=new_name, query=new_query)

    def _transform_cursor_op(self, node: CursorOperation) -> CursorOperation:
        new_name = self._transform_var_name(node.cursor_name)
        new_into = tuple(self._transform_var_name(v) for v in node.into_vars)
        new_query = self._transform_node(node.query) if node.query else None
        return CursorOperation(
            operation=node.operation,
            cursor_name=new_name,
            into_vars=new_into,
            query=new_query,
        )

    def _transform_for_loop(self, node: ForLoopStatement) -> ASTNode:
        if self._target == "tsql":
            self._warnings.append(
                "FOR loop has no direct T-SQL equivalent. "
                "Manual conversion to WHILE loop required."
            )
        new_body = self._ensure_non_empty_body(self._transform_body(node.body))
        new_cursor = self._transform_node(node.cursor) if node.cursor else None
        return ForLoopStatement(
            variable=node.variable,
            range_start=node.range_start,
            range_end=node.range_end,
            cursor=new_cursor,
            body=new_body,
        )

    def _transform_loop(self, node: LoopStatement) -> ASTNode:
        if self._target == "tsql":
            return WhileStatement(
                condition=RawSQL(sql="1=1", reason="infinite loop"),
                body=self._ensure_non_empty_body(self._transform_body(node.body)),
            )
        return LoopStatement(
            body=self._ensure_non_empty_body(self._transform_body(node.body))
        )

    def _transform_exit(self, node: ExitStatement) -> ASTNode:
        # Keep the ExitStatement (with its condition) so the emitter can
        # produce the dialect-correct form (e.g. T-SQL: IF <cond> BREAK).
        new_cond = self._transform_node(node.condition) if node.condition else None
        return ExitStatement(condition=new_cond, label=node.label)

    def _transform_select_into(self, node: SelectIntoStatement) -> ASTNode:
        """Transform SELECT INTO, adjusting variables and the embedded SQL."""
        new_into = tuple(self._transform_var_name(v) for v in node.into_vars)
        # Transform the select list and rest via variable + function mapping
        new_cols = tuple(self._transform_node(c) for c in node.columns)
        rest = self._transform_var_in_sql(node.rest_sql)
        rest = self._transform_functions_in_sql(rest)
        return SelectIntoStatement(
            columns=new_cols,
            into_vars=new_into,
            from_clause=node.from_clause,
            where=node.where,
            rest_sql=rest,
        )

    _DATE_ADD_START_RE = re.compile(r"DATE_ADD\s*\(", re.IGNORECASE)

    @classmethod
    def _replace_oracle_date_add(cls, sql: str) -> str:
        """Replace sqlglot's MySQL-style DATE_ADD(d, n, 'UNIT') with Oracle arithmetic.

        Uses paren-depth tracking to correctly split nested arguments.
        """
        result: list[str] = []
        i = 0
        while True:
            m = cls._DATE_ADD_START_RE.search(sql, i)
            if not m:
                result.append(sql[i:])
                break
            result.append(sql[i : m.start()])
            # Walk forward to find the matching closing paren.
            j = m.end()
            depth = 1
            while j < len(sql) and depth > 0:
                if sql[j] == "(":
                    depth += 1
                elif sql[j] == ")":
                    depth -= 1
                j += 1
            inner = sql[m.end() : j - 1]
            # Split inner at top-level commas.
            args: list[str] = []
            d = 0
            start = 0
            for k, ch in enumerate(inner):
                if ch == "(":
                    d += 1
                elif ch == ")":
                    d -= 1
                elif ch == "," and d == 0:
                    args.append(inner[start:k].strip())
                    start = k + 1
            args.append(inner[start:].strip())
            if len(args) == 3:
                date_expr, amount, unit = args[0], args[1], args[2].strip("'").upper()
                if unit in ("SECOND", "MINUTE", "HOUR"):
                    repl = f"({date_expr} + NUMTODSINTERVAL({amount}, '{unit}'))"
                elif unit == "DAY":
                    repl = f"({date_expr} + {amount})"
                elif unit == "WEEK":
                    repl = f"({date_expr} + ({amount}) * 7)"
                elif unit == "MONTH":
                    repl = f"ADD_MONTHS({date_expr}, {amount})"
                elif unit == "QUARTER":
                    repl = f"ADD_MONTHS({date_expr}, ({amount}) * 3)"
                elif unit == "YEAR":
                    repl = f"ADD_MONTHS({date_expr}, ({amount}) * 12)"
                else:
                    repl = f"DATE_ADD({inner})"
            else:
                repl = f"DATE_ADD({inner})"
            result.append(repl)
            i = j
        return "".join(result)

    def _fix_oracle_dml(self, sql: str) -> str:
        """Post-process sqlglot Oracle output to correct unsupported constructs."""
        sql = self._replace_oracle_date_add(sql)
        # Strip T-SQL RECOMPILE query hint that sqlglot leaves in Oracle output
        sql = re.sub(r"\s+RECOMPILE\b", "", sql, flags=re.IGNORECASE)
        return sql

    def _transform_embedded_dml(self, node: EmbeddedDML) -> EmbeddedDML:
        """Transform embedded DML using sqlglot."""
        sql = self._transform_var_in_sql(node.sql)
        try:
            source_dialect = self._get_sqlglot_dialect(self._source)
            target_dialect = self._get_sqlglot_dialect(self._target)
            results = sqlglot.transpile(
                sql,
                read=source_dialect,
                write=target_dialect,
                error_level=sqlglot.ErrorLevel.WARN,
            )
            if results:
                sql = results[0]
        except Exception as e:
            logger.debug("sqlglot transpile failed for DML: %s", e)
            self._warnings.append(f"Could not transpile DML: {e}")
        if self._target == "oracle":
            sql = self._fix_oracle_dml(sql)
        if self._target == "mysql":
            sql = self._mysql_string_concat(sql)
            sql = self._mysql_clean_dml(sql)
            sql = self._mysql_fix_cast_max(sql)
            sql = self._mysql_string_split(sql)
        if self._target == "postgresql":
            sql = self._pg_string_concat(sql)
            sql = self._pg_clean_dml(sql)
        if self._in_trigger and self._target != "tsql":
            sql = self._rewrite_trigger_pseudotables(sql)
        return EmbeddedDML(sql=sql, dialect=self._target)

    # FROM/JOIN <pseudo-table> — a *set-based* use of inserted/deleted, which has
    # no row-level (NEW/OLD) equivalent.
    _PSEUDO_TABLE_SOURCE_RE = re.compile(
        r"(?i)\b(?:FROM|JOIN)\s+(?:inserted|deleted)\b"
    )

    def _rewrite_trigger_pseudotables(self, sql: str) -> str:
        """Map T-SQL inserted/deleted pseudo-tables in a trigger body.

        - Column qualifiers (``inserted.col``/``deleted.col``) become the
          row-level ``NEW.col``/``OLD.col`` (``:NEW``/``:OLD`` for Oracle).
        - A *set-based* use (``FROM inserted``/``JOIN deleted``) has no row-level
          equivalent; document the statement with a ``-- UNIQUE:`` note pointing
          to a transition-table (PostgreSQL) / compound-trigger (Oracle) rewrite,
          rather than emit SQL that fails at runtime. MySQL has no equivalent at
          all (no transition tables).
        """
        if self._PSEUDO_TABLE_SOURCE_RE.search(sql):
            note = (
                "-- UNIQUE: trigger uses the T-SQL set-based inserted/deleted "
                "pseudo-tables, which have no row-level (NEW/OLD) equivalent. "
                "Rewrite manually (PostgreSQL: a statement-level trigger with "
                "REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted; Oracle: "
                "a compound trigger; MySQL: no transition tables). Original:"
            )
            body = "\n".join(f"-- {line}" for line in sql.splitlines())
            # Leave a dialect no-op so an enclosing IF/loop is not left with only
            # comments (an empty block is a syntax error). Harmless if redundant.
            noop = "DO 0;" if self._target == "mysql" else "NULL;"
            return f"{note}\n{body}\n{noop}"
        # Column-qualifier form: map to NEW/OLD (row-level).
        new_ref = ":NEW." if self._target == "oracle" else "NEW."
        old_ref = ":OLD." if self._target == "oracle" else "OLD."
        sql = re.sub(r"(?i)\binserted\s*\.\s*", new_ref, sql)
        sql = re.sub(r"(?i)\bdeleted\s*\.\s*", old_ref, sql)
        return sql

    def _pg_clean_dml(self, sql: str) -> str:
        """Strip T-SQL leftovers that PostgreSQL rejects.

        - The ``dbo`` schema qualifier on tables/functions: PostgreSQL has no
          ``dbo`` schema, so the bare name resolves in ``public`` (or the
          search_path) instead of a non-existent schema.
        - ``inserted.``/``deleted.`` pseudo-table qualifiers in a RETURNING
          clause (from a T-SQL OUTPUT): PostgreSQL RETURNING references the
          target's own columns, so the qualifier is dropped.
        """
        # RETURNING inserted.col / deleted.col -> RETURNING col. Only outside a
        # trigger body: inside a trigger these qualifiers map to NEW/OLD (handled
        # by _rewrite_trigger_pseudotables), not stripped.
        if not self._in_trigger:
            sql = re.sub(r"(?i)\b(?:inserted|deleted)\s*\.\s*", "", sql)
        # dbo. qualifier (tables and function calls)
        sql = re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)
        # (N)VARCHAR(MAX) in a CAST/expression -> TEXT (sqlglot leaves the T-SQL
        # MAX length untranslated for PostgreSQL, which has no such form).
        sql = re.sub(r"(?i)\bN?VARCHAR\s*\(\s*MAX\s*\)", "TEXT", sql)
        return sql

    def _from_clause_has_function(self, sql: str) -> bool:
        """Whether a SELECT references a function call in FROM/JOIN position
        that MySQL cannot use as a table source.

        MySQL has no general table-valued functions, so a call like
        ``FROM func5(@s, ',')`` is a syntax error. A few functions *are* valid
        table sources (``JSON_TABLE``) or are rewritten by a later pass into a
        valid one (``STRING_SPLIT`` -> ``JSON_TABLE``); those are allowed.
        """
        import sqlglot
        from sqlglot import exp

        if "(" not in sql or not re.search(r"(?i)\bFROM\b", sql):
            return False
        # Functions MySQL accepts (or that we rewrite) in FROM position.
        allowed = {"JSON_TABLE", "STRING_SPLIT"}

        def func_name(node: object) -> str:
            if isinstance(node, exp.Anonymous):
                return str(node.this).upper()
            return type(node).__name__.upper()

        try:
            trees = sqlglot.parse(sql, read="mysql")
        except Exception:
            return False
        for tree in trees:
            if tree is None:
                continue
            for node in tree.find_all(exp.From, exp.Join):
                this = node.this
                if this is None:
                    continue
                target = this.this if isinstance(this, exp.Alias) else this
                candidate = None
                if isinstance(target, (exp.Anonymous, exp.Func)):
                    candidate = target
                elif isinstance(target, exp.Table):
                    inner = target.this
                    if isinstance(inner, (exp.Anonymous, exp.Func)):
                        candidate = inner
                if candidate is not None and func_name(candidate) not in allowed:
                    return True
        return False

    def _mysql_clean_dml(self, sql: str) -> str:
        """Strip T-SQL leftovers sqlglot keeps but MySQL rejects.

        - A table-valued function in FROM/JOIN (no MySQL equivalent): the whole
          statement is commented out with a note.
        - A ``RETURNING`` clause (from a T-SQL ``OUTPUT``): MySQL has no
          RETURNING, so emit the base statement plus a documented comment.
        - The ``dbo`` schema qualifier and ``WITH (NOLOCK)`` hints.

        Only re-parses through sqlglot when there is something to clean.
        """
        import sqlglot
        from sqlglot import exp

        if self._from_clause_has_function(sql):
            commented = "\n".join(
                f"-- {line}" if line.strip() else "--" for line in sql.split("\n")
            )
            return (
                "-- UNIQUE: statement uses a table-valued function in FROM, "
                "which MySQL does not support; commented out for review:\n"
                f"{commented}"
            )

        if re.search(r"(?i)\bRETURNING\b", sql):
            m = re.search(r"(?i)\bRETURNING\b\s+(.*?)\s*;?\s*$", sql)
            cols = m.group(1).strip().rstrip(";").strip() if m else ""
            base = re.sub(r"(?i)\s*\bRETURNING\b.*$", "", sql).rstrip()
            sql = (
                f"{base};\n-- UNIQUE: MySQL has no RETURNING/OUTPUT; "
                f"the original statement returned: {cols}"
            )
            return sql

        has_dbo = bool(re.search(r"(?i)\bdbo\s*\.", sql))
        has_hint = bool(re.search(r"(?i)\bWITH\s*\(\s*NOLOCK", sql))
        if not has_dbo and not has_hint:
            return sql

        cleaned = sql
        # The AST pass handles tables and table hints; a bare expression
        # fragment may not parse as a statement, in which case we fall back to
        # the original text and let the textual dbo strip below still apply.
        if has_dbo or has_hint:
            try:
                tree = sqlglot.parse_one(sql, read="mysql")
                if not isinstance(tree, exp.Command):
                    for table in tree.find_all(exp.Table):
                        db = table.args.get("db")
                        if db is not None and db.name.lower() == "dbo":
                            table.set("db", None)
                        catalog = table.args.get("catalog")
                        if catalog is not None and catalog.name.lower() == "dbo":
                            table.set("catalog", None)
                    for hint in list(tree.find_all(exp.WithTableHint)):
                        hint.pop()
                    cleaned = tree.sql(dialect="mysql")
            except Exception:
                cleaned = sql
        # Scalar/table function calls keep a ``dbo.`` prefix that the AST table
        # pass above doesn't reach (they parse as Dot/Anonymous, and a bare
        # ``dbo.func(...)`` fragment may not parse as a statement at all).
        # The functions are created without a schema in MySQL, so drop any
        # remaining ``dbo.`` qualifier textually — this also preserves the
        # original identifier case, which re-emitting through sqlglot would
        # upper-case.
        cleaned = re.sub(r"(?i)\bdbo\s*\.\s*", "", cleaned)
        return cleaned

    def _mysql_fix_cast_max(self, sql: str) -> str:
        """Rewrite CAST targets MySQL rejects.

        T-SQL ``CAST(x AS NVARCHAR(MAX))`` lands as ``CAST(x AS VARCHAR(MAX))``
        or ``CHAR(MAX)``; MySQL's CAST does not accept a ``MAX`` length (or any
        VARCHAR length), so collapse those to a bare ``CHAR``, which MySQL
        accepts for casting to text. Sized casts like ``CHAR(50)`` are kept.
        """
        if "(MAX)" not in sql.upper():
            return sql
        import sqlglot
        from sqlglot import exp

        for wrap, is_wrapped in ((sql, False), (f"SELECT {sql}", True)):
            try:
                tree = sqlglot.parse_one(wrap, read="mysql")
            except Exception:
                continue
            if isinstance(tree, exp.Command):
                continue
            changed = False
            for cast_node in tree.find_all(exp.Cast):
                to_sql = cast_node.to.sql(dialect="mysql").upper()
                if to_sql.endswith("(MAX)") or to_sql == "MAX":
                    cast_node.set("to", exp.DataType.build("CHAR", dialect="mysql"))
                    changed = True
            if not changed:
                return sql
            out = tree.sql(dialect="mysql").rstrip().rstrip(";")
            if is_wrapped:
                if out.upper().startswith("SELECT "):
                    return out[len("SELECT ") :].strip()
                continue
            return out
        return sql

    def _mysql_string_split(self, sql: str) -> str:
        """Map T-SQL STRING_SPLIT(s, delim) to a MySQL JSON_TABLE expansion.

        MySQL has no native table-valued split. The portable equivalent builds
        a JSON array from the string (replacing the delimiter with ``","`` and
        wrapping in brackets) and expands it with JSON_TABLE, exposing a
        ``value`` column so existing references to STRING_SPLIT's ``value``
        keep working::

            FROM STRING_SPLIT(s, d)
            -> FROM JSON_TABLE(
                   CONCAT('["', REPLACE(s, d, '","'), '"]'),
                   '$[*]' COLUMNS (value VARCHAR(4000) PATH '$')
               ) AS _ss

        Note: this assumes the split values do not themselves contain JSON
        metacharacters; that holds for the delimiter-joined keys this targets.
        Multi-character delimiters are supported via REPLACE.
        """
        if "STRING_SPLIT" not in sql.upper():
            return sql
        import sqlglot
        from sqlglot import exp

        for wrap, is_wrapped in ((sql, False), (f"SELECT {sql}", True)):
            try:
                tree = sqlglot.parse_one(wrap, read="mysql")
            except Exception:
                continue
            if isinstance(tree, exp.Command):
                continue
            changed = False
            for tbl in list(tree.find_all(exp.Table)):
                inner = tbl.this
                if (
                    isinstance(inner, exp.Anonymous)
                    and inner.this
                    and inner.this.upper() == "STRING_SPLIT"
                    and len(inner.expressions) == 2
                ):
                    s_expr = inner.expressions[0].sql(dialect="mysql")
                    d_expr = inner.expressions[1].sql(dialect="mysql")
                    alias = tbl.alias or "_ss"
                    json_arr = (
                        "CONCAT('[\"', REPLACE("
                        + s_expr
                        + ", "
                        + d_expr
                        + ", '\",\"'), '\"]')"
                    )
                    jt = (
                        f"JSON_TABLE({json_arr}, '$[*]' "
                        f"COLUMNS (value VARCHAR(4000) PATH '$')) AS {alias}"
                    )
                    try:
                        probe = sqlglot.parse_one(f"SELECT 1 FROM {jt}", read="mysql")
                        from_node = probe.find(exp.From)
                        if from_node is not None:
                            tbl.replace(from_node.this)
                            changed = True
                    except Exception:
                        continue
            if not changed:
                return sql
            out = tree.sql(dialect="mysql").rstrip().rstrip(";")
            if is_wrapped:
                if out.upper().startswith("SELECT "):
                    return out[len("SELECT ") :].strip()
                continue
            return out
        return sql

    def _transform_null(self, node: NullStatement) -> ASTNode:
        if self._target == "tsql":
            return RawSQL(sql="-- NULL statement (no-op)", reason="no T-SQL equivalent")
        return node

    def _transform_raw_sql(self, node: RawSQL) -> RawSQL:
        sql = self._transform_var_in_sql(node.sql)
        # Apply function name transformations
        sql = self._transform_functions_in_sql(sql)
        # If the expression contains exactly one subquery (no other DML), try
        # to transpile it via sqlglot so TOP → FETCH FIRST, CONVERT → CAST, etc.
        # Guard: multiple DML verbs mean this is a multi-statement block that
        # should not be wrapped in SELECT and sent to sqlglot.
        _dml_count = len(
            re.findall(r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE)\b", sql, re.IGNORECASE)
        )
        # CONVERT/HASHBYTES and the T-SQL CHAR(n) character function have no
        # direct PG/Oracle form; DATEDIFF with a non-DAY part is left untranslated
        # by the dedicated handler (which only covers a few parts). Route these
        # through sqlglot, which renders them correctly. DATEADD is deliberately
        # excluded: its dedicated handler intentionally leaves unknown parts as-is.
        _has_tsql_scalar = bool(
            re.search(r"(?i)\b(?:CONVERT|HASHBYTES|DATEDIFF|CHAR)\s*\(", sql)
        )
        if (
            self._source == "tsql"
            and self._target in ("oracle", "postgresql")
            and _dml_count <= 1
            and (re.search(r"\bSELECT\b", sql, re.IGNORECASE) or _has_tsql_scalar)
        ):
            try:
                source_dialect = self._get_sqlglot_dialect(self._source)
                target_dialect = self._get_sqlglot_dialect(self._target)
                # Wrap as a SELECT so a bare scalar expression (e.g. a RETURN
                # value) parses; unwrap afterwards.
                had_select = bool(re.search(r"\bSELECT\b", sql, re.IGNORECASE))
                to_parse = sql if had_select else f"SELECT {sql}"
                results = sqlglot.transpile(
                    to_parse,
                    read=source_dialect,
                    write=target_dialect,
                    error_level=sqlglot.ErrorLevel.RAISE,
                )
                if results and results[0].upper().startswith("SELECT "):
                    out = results[0][len("SELECT ") :].rstrip().rstrip(";")
                    out = self._unwrap_spurious_hash_format(out)
                    sql = out
                    if self._target == "oracle":
                        sql = self._fix_oracle_dml(sql)
            except Exception:
                pass
        sql = self._rewrite_trigger_update_predicate(sql)
        if self._target == "mysql":
            sql = self._mysql_normalize_funcs(sql)
            sql = self._mysql_string_concat(sql)
            sql = self._mysql_clean_dml(sql)
            sql = self._mysql_fix_cast_max(sql)
            sql = self._mysql_string_split(sql)
        if self._target == "postgresql":
            sql = self._pg_string_concat(sql)
        if self._target in ("postgresql", "oracle"):
            # Functions/procedures are created without the T-SQL "dbo" schema
            # in these targets (dbo doesn't exist), so drop a dbo. qualifier on
            # calls within expressions (e.g. ``dbo.func1()`` in an assignment,
            # RETURN or COALESCE). The lexer may have split it as ``dbo . f``.
            sql = re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)
        return RawSQL(sql=sql, reason=node.reason)

    def _rewrite_trigger_update_predicate(self, sql: str) -> str:
        """Rewrite the T-SQL trigger predicate ``UPDATE(col)`` per dialect.

        Inside a trigger, T-SQL ``UPDATE(col)`` tests whether a column was
        affected by the statement. The equivalents are:
          - MySQL:      NOT (NEW.col <=> OLD.col)   (null-safe "changed")
          - PostgreSQL: (NEW.col IS DISTINCT FROM OLD.col)
          - Oracle:     UPDATING('col')

        Only matches ``UPDATE(<identifier>)`` as a function-style predicate (a
        single column name in parens), never an ``UPDATE … SET`` statement.
        """
        if self._target == "tsql":
            return sql
        pattern = re.compile(r"(?i)\bUPDATE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")

        def repl(m: re.Match[str]) -> str:
            col = m.group(1)
            if self._target == "mysql":
                return f"NOT (NEW.{col} <=> OLD.{col})"
            if self._target == "postgresql":
                return f"(NEW.{col} IS DISTINCT FROM OLD.{col})"
            if self._target == "oracle":
                return f"UPDATING('{col}')"
            return m.group(0)

        return pattern.sub(repl, sql)

    def _unwrap_spurious_hash_format(self, sql: str) -> str:
        """Undo sqlglot's misreading of a T-SQL hash-stringify CONVERT.

        ``CONVERT(varchar(max), HASHBYTES('SHA2_256', x), 2)`` stringifies a
        hash; sqlglot maps HASHBYTES to SHA256 but treats the style code ``2``
        as a date format, producing e.g.
        ``CAST(TO_CHAR(SHA256(x), 'YY.MM.DD') AS VARCHAR(MAX))``. The hash
        already returns a hex/text value, so strip the spurious TO_CHAR/format
        and the (MAX) cast, leaving the bare hash call.
        """
        # CAST(TO_CHAR(<inner>, '...') AS VARCHAR(MAX)) -> <inner>
        sql = re.sub(
            r"(?i)CAST\s*\(\s*TO_CHAR\s*\(\s*(.+?)\s*,\s*'[^']*'\s*\)\s*"
            r"AS\s+VARCHAR\s*\(\s*MAX\s*\)\s*\)",
            r"\1",
            sql,
        )
        # Bare TO_CHAR(<hash>, '...') with no surrounding cast.
        sql = re.sub(
            r"(?i)TO_CHAR\s*\(\s*(SHA\d*\s*\(.+?\))\s*,\s*'[^']*'\s*\)",
            r"\1",
            sql,
        )
        return sql

    # direct MySQL equivalents that sqlglot knows, but the procedural pipeline
    # captures expressions as text that often parses as an opaque Command. Re-
    # transpile the fragment from T-SQL to MySQL so CONVERT(t, x) -> CAST(x AS
    # t), CONVERT(date, s, 120) -> STR_TO_DATE(...), HASHBYTES('SHA2_256', x)
    # -> SHA2(x, 256), and similar conversions are applied. The '+' string
    # concatenation is handled separately afterwards (sqlglot can't tell
    # arithmetic from concat without type info).
    def _mysql_normalize_funcs(self, sql: str) -> str:
        import sqlglot
        from sqlglot import exp

        # Cheap guard: only worth the round-trip when a known T-SQL-ism is
        # present. Keeps already-valid fragments byte-for-byte identical.
        if not re.search(r"(?i)\b(CONVERT|HASHBYTES|DATEPART|DATENAME)\s*\(", sql):
            return sql

        def normalize(tree: exp.Expression) -> exp.Expression:
            # T-SQL hashes the binary with HASHBYTES and stringifies it with an
            # outer CONVERT(<type>, ..., 2) (style 2 = hex, no 0x). sqlglot maps
            # HASHBYTES('SHA2_256', x) to SHA2(x, 256) — which already returns a
            # hex string — but mis-handles the wrapping CONVERT's style code,
            # emitting a spurious DATE_FORMAT. Drop the CONVERT wrapper around a
            # hash so just SHA2(...) remains.
            # If the CONVERT is the whole expression (e.g. RETURN CONVERT(...)),
            # it is the tree root and Node.replace() can't substitute it, so
            # return the inner expression directly.
            if isinstance(tree, exp.Convert):
                expr = tree.args.get("expression")
                if expr is not None and (
                    isinstance(expr, exp.SHA2) or expr.find(exp.SHA2)
                ):
                    return cast(exp.Expression, expr.copy())
            wrappers = [
                conv
                for conv in tree.find_all(exp.Convert)
                if (expr := conv.args.get("expression")) is not None
                and (isinstance(expr, exp.SHA2) or expr.find(exp.SHA2))
            ]
            for conv in wrappers:
                expr = conv.args.get("expression")
                if expr is not None:
                    conv.replace(expr.copy())
            return tree

        for wrap, is_wrapped in ((sql, False), (f"SELECT {sql}", True)):
            try:
                tree = sqlglot.parse_one(wrap, read="tsql")
            except Exception:
                continue
            if isinstance(tree, exp.Command):
                continue
            try:
                out = (
                    normalize(cast(exp.Expression, tree))
                    .sql(dialect="mysql")
                    .rstrip()
                    .rstrip(";")
                )
            except Exception:
                continue
            if is_wrapped and not sql.upper().startswith("SELECT"):
                if out.upper().startswith("SELECT "):
                    return out[len("SELECT ") :].strip()
                continue
            return out
        return sql

    # MySQL has no string ``+`` operator and no ``N'...'`` literal prefix.
    # T-SQL uses ``+`` for both arithmetic and string concatenation, so the
    # operator alone is ambiguous; we treat a ``+`` chain as concatenation
    # only when one of its operands is a string literal (the unambiguous
    # signal), rewriting the whole chain to ``CONCAT(...)`` and dropping any
    # ``N`` prefixes. Pure arithmetic (``a + b``, ``x + 1``) is left intact.
    def _mysql_string_concat(self, sql: str) -> str:
        return self._rewrite_string_concat(sql, "mysql")

    def _pg_string_concat(self, sql: str) -> str:
        return self._rewrite_string_concat(sql, "postgresql")

    def _rewrite_string_concat(self, sql: str, target: str) -> str:
        """Rewrite T-SQL string `+` concatenation for the target dialect.

        T-SQL overloads `+` for both arithmetic and string concatenation. When
        an operand is (or is known to be) a string, the chain is concatenation
        and must use the target's construct: `CONCAT(...)` for MySQL, the `||`
        operator for PostgreSQL (where `+` on text is an error). Numeric `+`
        chains are left untouched.
        """
        import sqlglot
        from sqlglot import exp

        read = "mysql" if target == "mysql" else "postgres"

        def is_string_atom(n: exp.Expression) -> bool:
            return isinstance(n, exp.National) or (
                isinstance(n, exp.Literal) and bool(n.args.get("is_string"))
            )

        def denationalize(n: exp.Expression) -> exp.Expression:
            if isinstance(n, exp.National):
                return exp.Literal.string(n.this)
            for nat in list(n.find_all(exp.National)):
                nat.replace(exp.Literal.string(nat.this))
            return n

        def flatten_add(n: exp.Expression, parts: list[exp.Expression]) -> None:
            if isinstance(n, exp.Add):
                flatten_add(cast(exp.Expression, n.left), parts)
                flatten_add(cast(exp.Expression, n.right), parts)
            else:
                parts.append(n)

        def is_known_string_var(n: exp.Expression) -> bool:
            # A bare identifier known (from its DECLARE/parameter type) to be a
            # string variable signals concatenation even with no string literal
            # present (e.g. SHA2(@a + @b) over two text columns).
            if isinstance(n, exp.Column) and not n.table:
                return n.name in self._string_vars
            return False

        def has_string_operand(parts: list[exp.Expression]) -> bool:
            for p in parts:
                if is_string_atom(p) or p.find(exp.National):
                    return True
                if is_known_string_var(p):
                    return True
                if any(
                    isinstance(lit, exp.Literal) and lit.args.get("is_string")
                    for lit in p.find_all(exp.Literal)
                ):
                    return True
            return False

        def build_concat(parts: list[exp.Expression]) -> exp.Expression:
            if target == "mysql":
                return cast(exp.Expression, exp.func("CONCAT", *parts))
            # PostgreSQL: chain with the || (DPipe) operator.
            node = parts[0]
            for nxt in parts[1:]:
                node = exp.DPipe(this=node, expression=nxt)
            return node

        def convert(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Add):
                parts: list[exp.Expression] = []
                flatten_add(node, parts)
                if has_string_operand(parts):
                    new_parts = [convert(denationalize(p.copy())) for p in parts]
                    return build_concat(new_parts)
            for key, value in list(node.args.items()):
                if isinstance(value, exp.Expression):
                    node.set(key, convert(value))
                elif isinstance(value, list):
                    node.set(
                        key,
                        [
                            convert(c) if isinstance(c, exp.Expression) else c
                            for c in value
                        ],
                    )
            return node

        # Only attempt the rewrite when a '+' is present at all (the parse cost
        # is otherwise wasted). A string literal OR a known string variable is
        # what later marks a chain as concatenation; require '+' plus one of
        # those signals so already-numeric fragments are skipped cheaply.
        if "+" not in sql:
            return sql
        if "'" not in sql and not self._string_vars:
            return sql
        # The raw SQL may be a complete statement (SELECT ... FROM ...) or a
        # bare expression (the right-hand side of a SET). Try the statement
        # form first; if it doesn't parse — or parses as an opaque Command,
        # which sqlglot falls back to for things like ``REPLACE ( ... )`` and
        # which exposes no Add nodes to rewrite — wrap it in a SELECT so a lone
        # expression becomes parseable, and unwrap afterwards.
        wrapped = False
        tree = None
        try:
            parsed = sqlglot.parse_one(sql, read=read)
            if not isinstance(parsed, exp.Command):
                tree = parsed
        except Exception:
            tree = None
        if tree is None:
            try:
                tree = sqlglot.parse_one(f"SELECT {sql}", read=read)
                wrapped = True
            except Exception:
                return sql
        try:
            tree = convert(cast(exp.Expression, tree))
            rendered = tree.sql(dialect=read)
        except Exception:
            return sql
        if wrapped and rendered.upper().startswith("SELECT "):
            return rendered[len("SELECT ") :].rstrip().rstrip(";")
        return rendered

    def _transform_functions_in_sql(self, sql: str) -> str:
        """Transform function names in raw SQL text.

        Applies all mappings in a single pass (alternation regex) so that a
        replacement's output cannot be re-matched by a later mapping. Only
        function-call positions (name followed by '(') are rewritten, and
        commented placeholder mappings are skipped.
        """
        sql = self._transform_niladic_datetime(sql)

        func_map = {
            old: new
            for old, new in self._get_func_map().items()
            if not new.startswith("--") and old.upper() != new.upper()
        }
        if not func_map:
            return sql

        # Longest names first to avoid partial-overlap surprises.
        names = sorted(func_map, key=len, reverse=True)
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in names) + r")\b(\s*\()",
            flags=re.IGNORECASE,
        )

        lookup = {k.upper(): v for k, v in func_map.items()}

        def repl(m: re.Match[str]) -> str:
            return lookup[m.group(1).upper()] + m.group(2)

        return pattern.sub(repl, sql)

    # Current-timestamp expressions, by dialect. Oracle/PG use a bare
    # keyword; T-SQL/MySQL use a function call.
    _NOW_EXPR = {
        "tsql": "GETDATE()",
        "oracle": "SYSDATE",
        "postgresql": "NOW()",
        "mysql": "NOW()",
    }

    def _transform_niladic_datetime(self, sql: str) -> str:
        """Translate current-timestamp expressions across dialects.

        Handles the forms that differ in whether they take parentheses:
        GETDATE() (T-SQL), SYSDATE (Oracle), NOW() (PG/MySQL).
        """
        target_expr = self._NOW_EXPR.get(self._target)
        if target_expr:
            # Match GETDATE(), SYSDATE, NOW() (optional parens/spaces).
            pattern = re.compile(
                r"\b(GETDATE\s*\(\s*\)|SYSDATE\b(?!\s*\()|NOW\s*\(\s*\))",
                flags=re.IGNORECASE,
            )
            sql = pattern.sub(target_expr, sql)
        # Argument-aware function rewrites run regardless of the niladic
        # datetime mapping above.
        sql = self._transform_dateadd(sql)
        sql = self._transform_datediff(sql)
        sql = self._transform_substring_position(sql)
        sql = self._transform_decode(sql)
        sql = self._transform_string_agg(sql)
        sql = self._transform_scope_identity(sql)
        sql = self._transform_nvl2(sql)
        sql = self._transform_oracle_date_funcs(sql)
        sql = self._transform_mysql_date_funcs(sql)
        return sql

    def _map_mysql_datefmt_to_oracle(self, fmt: str) -> str:
        """Map a MySQL date-format string to Oracle/PostgreSQL specifiers."""
        out = fmt
        # Reverse of the Oracle->MySQL table; longest specifiers first.
        for ora, mysql in self._ORACLE_TO_MYSQL_DATEFMT:
            out = out.replace(mysql, ora)
        # MySQL %T is HH24:MI:SS.
        out = out.replace("%T", "HH24:MI:SS")
        return out

    def _transform_mysql_date_funcs(self, sql: str) -> str:
        """Translate MySQL DATE_FORMAT/STR_TO_DATE to Oracle/PostgreSQL.

        DATE_FORMAT(d, fmt) -> TO_CHAR(d, mapped_fmt)
        STR_TO_DATE(s, fmt) -> TO_DATE(s, mapped_fmt)
        Targets Oracle and PostgreSQL (both use TO_CHAR/TO_DATE with the same
        format patterns); T-SQL has no direct TO_CHAR, so it is left for the
        CONVERT path / manual review.
        """
        if self._source != "mysql" or self._target not in ("oracle", "postgresql"):
            return sql

        def map_fmt_arg(arg: str) -> str:
            s = arg.strip()
            if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                return "'" + self._map_mysql_datefmt_to_oracle(s[1:-1]) + "'"
            return arg

        def build_date_format(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"TO_CHAR({args[0]}, {map_fmt_arg(args[1])})"

        def build_str_to_date(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"TO_DATE({args[0]}, {map_fmt_arg(args[1])})"

        sql = self._rewrite_calls(sql, "DATE_FORMAT", build_date_format)
        sql = self._rewrite_calls(sql, "STR_TO_DATE", build_str_to_date)
        return sql

    # Oracle date-format pattern -> MySQL/strftime specifier.
    _ORACLE_TO_MYSQL_DATEFMT = [
        ("YYYY", "%Y"),
        ("YY", "%y"),
        ("MONTH", "%M"),
        ("MON", "%b"),
        ("MM", "%m"),
        ("DDD", "%j"),
        ("DD", "%d"),
        ("DY", "%a"),
        ("DAY", "%W"),
        ("HH24", "%H"),
        ("HH12", "%h"),
        ("HH", "%h"),
        ("MI", "%i"),
        ("SS", "%s"),
        ("AM", "%p"),
        ("PM", "%p"),
    ]

    def _map_oracle_datefmt_to_mysql(self, fmt: str) -> str:
        """Map an Oracle date-format string literal to MySQL's specifiers."""
        out = fmt
        # Replace longest tokens first to avoid partial overlaps.
        for ora, mysql in self._ORACLE_TO_MYSQL_DATEFMT:
            out = re.sub(ora, mysql, out, flags=re.IGNORECASE)
        return out

    def _transform_oracle_date_funcs(self, sql: str) -> str:
        """Translate Oracle TO_CHAR/TO_DATE with date-format strings.

        Oracle -> MySQL:
          TO_CHAR(d, fmt)  -> DATE_FORMAT(d, mapped_fmt)
          TO_DATE(s, fmt)  -> STR_TO_DATE(s, mapped_fmt)
        The format-pattern mapping covers the common specifiers; uncommon
        ones are left as-is for review.
        """
        if self._source != "oracle" or self._target != "mysql":
            return sql

        def map_fmt_arg(arg: str) -> str:
            s = arg.strip()
            if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                inner = s[1:-1]
                return "'" + self._map_oracle_datefmt_to_mysql(inner) + "'"
            return arg

        def build_to_char(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"DATE_FORMAT({args[0]}, {map_fmt_arg(args[1])})"

        def build_to_date(args: list[str]) -> str | None:
            if len(args) != 2:
                return None
            return f"STR_TO_DATE({args[0]}, {map_fmt_arg(args[1])})"

        sql = self._rewrite_calls(sql, "TO_CHAR", build_to_char)
        sql = self._rewrite_calls(sql, "TO_DATE", build_to_date)
        return sql

    def _transform_nvl2(self, sql: str) -> str:
        """Translate Oracle NVL2(expr, if_not_null, if_null) to CASE.

        NVL2(e, a, b) == CASE WHEN e IS NOT NULL THEN a ELSE b END.
        Applies when translating away from Oracle.
        """
        if self._source != "oracle" or self._target == "oracle":
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) != 3:
                return None
            expr, if_not_null, if_null = args
            return (
                f"CASE WHEN {expr} IS NOT NULL "
                f"THEN {if_not_null} ELSE {if_null} END"
            )

        return self._rewrite_calls(sql, "NVL2", build)

    def _transform_scope_identity(self, sql: str) -> str:
        """Translate T-SQL SCOPE_IDENTITY()/IDENT_CURRENT(...) last-id calls.

        SCOPE_IDENTITY() returns the most recent identity value. Targets:
        - PostgreSQL: LASTVAL()
        - MySQL:      LAST_INSERT_ID()
        - Oracle:     no portable form; emit a documented comment (the value
          comes from <sequence>.CURRVAL, which needs the sequence name).
        """
        if self._source != "tsql" or self._target == "tsql":
            return sql

        replacement = {
            "postgresql": "LASTVAL()",
            "mysql": "LAST_INSERT_ID()",
            "oracle": "/* SCOPE_IDENTITY: use <sequence>.CURRVAL */",
        }.get(self._target)
        if replacement is None:
            return sql

        # SCOPE_IDENTITY() takes no arguments.
        sql = re.sub(
            r"\bSCOPE_IDENTITY\s*\(\s*\)", replacement, sql, flags=re.IGNORECASE
        )
        return sql

    def _transform_string_agg(self, sql: str) -> str:
        """Translate string-aggregation functions across dialects.

        - T-SQL / PostgreSQL: STRING_AGG(col, sep)
        - Oracle:             LISTAGG(col, sep)
        - MySQL:              GROUP_CONCAT(col SEPARATOR sep)

        Only the basic ``(col, sep)`` form is handled; an Oracle/T-SQL
        ``WITHIN GROUP (ORDER BY ...)`` suffix or MySQL ``ORDER BY`` inside
        the call is left for manual review.
        """
        source_fn = {
            "tsql": "STRING_AGG",
            "postgresql": "STRING_AGG",
            "oracle": "LISTAGG",
            "mysql": "GROUP_CONCAT",
        }.get(self._source)
        if not source_fn or self._source == self._target:
            return sql

        def build(args: list[str]) -> str | None:
            # MySQL uses "col SEPARATOR sep" as a single arg; normalize.
            col: str
            sep: str | None
            if self._source == "mysql":
                if len(args) != 1 or "SEPARATOR" not in args[0].upper():
                    return None
                m = re.split(r"(?i)\bSEPARATOR\b", args[0], maxsplit=1)
                col, sep = m[0].strip(), m[1].strip()
            else:
                if len(args) != 2:
                    return None
                col, sep = args[0], args[1]

            if self._target in ("tsql", "postgresql"):
                return f"STRING_AGG({col}, {sep})"
            if self._target == "oracle":
                return f"LISTAGG({col}, {sep})"
            return f"GROUP_CONCAT({col} SEPARATOR {sep})"

        return self._rewrite_calls(sql, source_fn, build)

    def _transform_decode(self, sql: str) -> str:
        """Translate Oracle DECODE(expr, s1, r1, [s2, r2, ...], [default]).

        Equivalent to a searched CASE expression:
            CASE WHEN expr = s1 THEN r1 [WHEN expr = s2 THEN r2 ...]
                 [ELSE default] END
        Only applies when translating away from Oracle.
        """
        if self._source != "oracle" or self._target == "oracle":
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) < 3:
                return None
            expr = args[0]
            pairs = args[1:]
            parts = ["CASE"]
            i = 0
            while i + 1 < len(pairs):
                parts.append(f"WHEN {expr} = {pairs[i]} THEN {pairs[i + 1]}")
                i += 2
            if i < len(pairs):  # trailing default
                parts.append(f"ELSE {pairs[i]}")
            parts.append("END")
            return " ".join(parts)

        return self._rewrite_calls(sql, "DECODE", build)

    def _transform_substring_position(self, sql: str) -> str:
        """Translate substring-position functions with argument reordering.

        The three engines express "position of needle in haystack" with
        different argument orders:
        - T-SQL:  CHARINDEX(needle, haystack)
        - MySQL:  LOCATE(needle, haystack)        (same order as T-SQL)
        - Oracle: INSTR(haystack, needle)         (reversed)
        - PostgreSQL: STRPOS(haystack, needle) / POSITION(needle IN haystack)

        An optional third argument (start position) is preserved as the
        trailing argument in every dialect.
        """
        # Identify the source function name and how to read (needle, haystack).
        source_fn = {
            "tsql": "CHARINDEX",
            "mysql": "LOCATE",
            "oracle": "INSTR",
            "postgresql": "STRPOS",
        }.get(self._source)
        if not source_fn or self._source == self._target:
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) < 2:
                return None
            # Read needle/haystack per source order.
            if self._source in ("tsql", "mysql"):
                needle, haystack = args[0], args[1]
            else:  # oracle, postgresql: haystack first
                haystack, needle = args[0], args[1]
            start = args[2] if len(args) >= 3 else None

            if self._target == "tsql":
                out = f"CHARINDEX({needle}, {haystack}"
                return (out + f", {start})") if start else (out + ")")
            if self._target == "mysql":
                out = f"LOCATE({needle}, {haystack}"
                return (out + f", {start})") if start else (out + ")")
            if self._target == "oracle":
                out = f"INSTR({haystack}, {needle}"
                return (out + f", {start})") if start else (out + ")")
            # postgresql
            if start:
                # STRPOS has no start arg; fall back to POSITION + offset note.
                return f"STRPOS({haystack}, {needle})"
            return f"STRPOS({haystack}, {needle})"

        return self._rewrite_calls(sql, source_fn, build)

    @staticmethod
    def _split_top_level_args(arglist: str) -> list[str]:
        """Split a comma-separated argument list at top-level commas only.

        Commas inside parentheses or string literals (single or double
        quotes) are not split points.
        """
        parts: list[str] = []
        depth = 0
        cur: list[str] = []
        quote: str | None = None
        for ch in arglist:
            if quote is not None:
                cur.append(ch)
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
                cur.append(ch)
            elif ch == "(":
                depth += 1
                cur.append(ch)
            elif ch == ")":
                depth -= 1
                cur.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        if cur:
            parts.append("".join(cur).strip())
        return parts

    def _rewrite_calls(
        self, sql: str, func_name: str, builder: Callable[[list[str]], str | None]
    ) -> str:
        """Rewrite every top-level call ``func_name(...)`` using ``builder``.

        ``builder`` receives the list of argument strings and returns the
        replacement text, or None to leave the call unchanged. Calls are
        rewritten right-to-left so earlier indices stay valid.
        """
        pattern = re.compile(rf"\b{re.escape(func_name)}\s*\(", re.IGNORECASE)
        result = sql
        for match in reversed(list(pattern.finditer(result))):
            start = match.end()
            depth = 1
            i = start
            while i < len(result) and depth > 0:
                if result[i] == "(":
                    depth += 1
                elif result[i] == ")":
                    depth -= 1
                i += 1
            inner = result[start : i - 1]
            args = self._split_top_level_args(inner)
            replacement = builder(args)
            if replacement is None:
                continue
            result = result[: match.start()] + replacement + result[i:]
        return result

    # T-SQL date parts → canonical interval unit name.
    _DATEPART_UNITS = {
        "year": "YEAR",
        "yy": "YEAR",
        "yyyy": "YEAR",
        "quarter": "QUARTER",
        "qq": "QUARTER",
        "q": "QUARTER",
        "month": "MONTH",
        "mm": "MONTH",
        "m": "MONTH",
        "day": "DAY",
        "dd": "DAY",
        "d": "DAY",
        "week": "WEEK",
        "wk": "WEEK",
        "ww": "WEEK",
        "hour": "HOUR",
        "hh": "HOUR",
        "minute": "MINUTE",
        "mi": "MINUTE",
        "n": "MINUTE",
        "second": "SECOND",
        "ss": "SECOND",
        "s": "SECOND",
    }

    def _transform_dateadd(self, sql: str) -> str:
        """Translate simple T-SQL DATEADD(part, n, date) calls.

        Only the common, unambiguous form with a recognized date part is
        converted; anything else is left untouched. Source must be T-SQL;
        targets Oracle/PostgreSQL/MySQL.
        """
        if self._source != "tsql" or self._target not in (
            "oracle",
            "postgresql",
            "mysql",
        ):
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) != 3:
                return None
            part, num, date = args
            unit = self._DATEPART_UNITS.get(part.strip().lower())
            if not unit:
                return None
            if self._target == "oracle":
                if unit == "DAY":
                    return f"({date} + {num})"
                if unit == "MONTH":
                    return f"ADD_MONTHS({date}, {num})"
                if unit == "YEAR":
                    return f"ADD_MONTHS({date}, ({num}) * 12)"
                if unit in ("HOUR", "MINUTE", "SECOND"):
                    return f"({date} + NUMTODSINTERVAL({num}, '{unit}'))"
                return None
            if self._target == "postgresql":
                return f"({date} + INTERVAL '{num} {unit}')"
            return f"DATE_ADD({date}, INTERVAL {num} {unit})"

        return self._rewrite_calls(sql, "DATEADD", build)

    def _transform_datediff(self, sql: str) -> str:
        """Translate simple T-SQL DATEDIFF(part, start, end) calls.

        T-SQL returns ``end - start`` in the given unit. Conversions:
        - Oracle: day -> (end - start); month -> MONTHS_BETWEEN(end, start);
          year -> MONTHS_BETWEEN(end, start)/12
        - PostgreSQL: day -> (end::date - start::date)
        - MySQL: day -> DATEDIFF(end, start); else TIMESTAMPDIFF(unit, ...)
        """
        if self._source != "tsql" or self._target not in (
            "oracle",
            "postgresql",
            "mysql",
        ):
            return sql

        def build(args: list[str]) -> str | None:
            if len(args) != 3:
                return None
            part, start, end = args
            unit = self._DATEPART_UNITS.get(part.strip().lower())
            if not unit:
                return None
            if self._target == "oracle":
                if unit == "DAY":
                    return f"({end} - {start})"
                if unit == "MONTH":
                    return f"MONTHS_BETWEEN({end}, {start})"
                if unit == "YEAR":
                    return f"(MONTHS_BETWEEN({end}, {start}) / 12)"
                return None
            if self._target == "postgresql":
                if unit == "DAY":
                    return f"({end}::date - {start}::date)"
                return None
            # mysql
            if unit == "DAY":
                return f"DATEDIFF({end}, {start})"
            return f"TIMESTAMPDIFF({unit}, {start}, {end})"

        return self._rewrite_calls(sql, "DATEDIFF", build)

    def _get_func_map(self) -> dict[str, str]:
        key = f"{self._source}_{self._target}"
        maps = {
            "tsql_oracle": _TSQL_TO_ORACLE_FUNCS,
            "oracle_tsql": _ORACLE_TO_TSQL_FUNCS,
            "tsql_postgresql": _TSQL_TO_PG_FUNCS,
            "postgresql_tsql": _PG_TO_TSQL_FUNCS,
            "tsql_mysql": _TSQL_TO_MYSQL_FUNCS,
            "mysql_tsql": _MYSQL_TO_TSQL_FUNCS,
            "oracle_postgresql": _ORACLE_TO_PG_FUNCS,
            "oracle_mysql": _ORACLE_TO_MYSQL_FUNCS,
        }
        return maps.get(key, {})

    @staticmethod
    def _get_sqlglot_dialect(dialect: str) -> str:
        mapping = {
            "tsql": "tsql",
            "oracle": "oracle",
            "postgresql": "postgres",
            "mysql": "mysql",
        }
        return mapping.get(dialect, dialect)


# ---------------------------------------------------------------------------
# Per-target transformer subclasses
# ---------------------------------------------------------------------------
#
# Each subclass overrides only the transform rules that are specific to its
# *target* engine. Source-dependent and pair-dependent logic stays in the base
# (parameterized by self._source), because a transform is a source→target
# operation and a target subclass alone cannot know the source.


class TSqlTransformer(ProceduralTransformer):
    """Transforms toward T-SQL (SQL Server)."""

    target_name = "tsql"

    def _alter_becomes_create(self) -> bool:
        # T-SQL keeps ALTER PROCEDURE as-is.
        return False

    def _uses_set_statement(self) -> bool:
        return True

    def _assignment_becomes_set(self) -> bool:
        return True

    def _transform_exception_block(self, node: ExceptionBlock) -> ASTNode:
        # T-SQL's only structured-handler form is TRY/CATCH; flatten the
        # EXCEPTION handlers' bodies into the CATCH block.
        body: list[ASTNode] = []
        for handler in node.handlers:
            body.extend(handler.body)
        return TryCatchBlock(
            try_body=(),
            catch_body=self._transform_body(tuple(body)),
        )


class OracleTransformer(ProceduralTransformer):
    """Transforms toward Oracle PL/SQL."""

    target_name = "oracle"

    def _system_var_map(self) -> dict[str, str]:
        return {
            "@@ROWCOUNT": "SQL%ROWCOUNT",
            "@@IDENTITY": "/* @@IDENTITY: use <sequence>.CURRVAL */",
            # SQLCODE is a valid Oracle function (0 in normal flow, the last
            # error code inside an exception handler).
            "@@ERROR": "SQLCODE",
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "transactions are implicit"
            ),
        }

    def _supports_type_reference(self) -> bool:
        # Oracle supports %TYPE/%ROWTYPE natively.
        return True

    def _strip_dbo_schema(self) -> bool:
        # Oracle objects live in the current user's schema; 'dbo' has no meaning.
        return True

    def _transform_try_catch(self, node: TryCatchBlock) -> ASTNode:
        # Oracle expresses error handling as a PL/SQL EXCEPTION block.
        return ExceptionBlock(
            handlers=(
                ExceptionHandler(
                    exception_name="OTHERS",
                    body=self._transform_body(node.catch_body),
                ),
            )
        )

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "NCLOB" if is_unicode else "CLOB"


class PostgresTransformer(ProceduralTransformer):
    """Transforms toward PostgreSQL PL/pgSQL."""

    target_name = "postgresql"

    def _system_var_map(self) -> dict[str, str]:
        return {
            "@@ROWCOUNT": "ROW_COUNT",
            "@@IDENTITY": "LASTVAL()",
            # SQLSTATE is only available inside an EXCEPTION handler in plpgsql,
            # so it cannot stand in for an inline @@ERROR check.
            "@@ERROR": self._neutral_global("@@ERROR", "use an EXCEPTION handler"),
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "the routine manages its transaction"
            ),
        }

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "TEXT"


class MySqlTransformer(ProceduralTransformer):
    """Transforms toward MySQL."""

    target_name = "mysql"

    def _system_var_map(self) -> dict[str, str]:
        return {
            "@@ROWCOUNT": "ROW_COUNT()",
            "@@IDENTITY": "LAST_INSERT_ID()",
            "@@ERROR": self._neutral_global("@@ERROR", "use a DECLARE ... HANDLER"),
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "the routine manages its transaction"
            ),
        }

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "LONGTEXT"

    def _uses_set_statement(self) -> bool:
        return True

    def _noop_statement(self) -> ASTNode:
        # DO evaluates an expression and discards it; the cheapest valid
        # statement to keep a block non-empty. Terminator included since the
        # IF/loop emitters don't add one for RawSQL.
        return RawSQL(sql="DO 0;", reason="no-op")


_TRANSFORMER_REGISTRY: dict[str, type[ProceduralTransformer]] = {
    TSqlTransformer.target_name: TSqlTransformer,
    OracleTransformer.target_name: OracleTransformer,
    PostgresTransformer.target_name: PostgresTransformer,
    MySqlTransformer.target_name: MySqlTransformer,
}
