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

"""Procedural SQL transformer.

Transforms procedural IR AST nodes between dialects, handling
differences in variable naming, control flow syntax, data types,
built-in functions, and idiomatic patterns.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import sqlglot

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
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
    """

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
            # Filter out SET NOCOUNT and similar when going to Oracle/PG
            if isinstance(transformed, RawSQL) and "SET option" in transformed.reason:
                continue
            result.append(transformed)
        return tuple(result)

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
        """Transform system variables like @@ROWCOUNT, @@IDENTITY."""
        upper = var.upper()
        if self._target == "oracle":
            mapping = {
                "@@ROWCOUNT": "SQL%ROWCOUNT",
                "@@IDENTITY": "/* @@IDENTITY: use <sequence>.CURRVAL */",
                "@@ERROR": "SQLCODE",
                "@@TRANCOUNT": "-- @@TRANCOUNT has no Oracle equivalent",
            }
            return mapping.get(upper, f"/* {var} */")
        elif self._target == "postgresql":
            mapping = {
                "@@ROWCOUNT": "ROW_COUNT",
                "@@IDENTITY": "LASTVAL()",
                "@@ERROR": "SQLSTATE",
            }
            return mapping.get(upper, f"/* {var} */")
        elif self._target == "mysql":
            mapping = {
                "@@ROWCOUNT": "ROW_COUNT()",
                "@@IDENTITY": "LAST_INSERT_ID()",
            }
            return mapping.get(upper, f"/* {var} */")
        return var

    # ---------------------------------------------------------------
    # Data type transformations
    # ---------------------------------------------------------------

    def _transform_data_type(self, dt: DataType) -> DataType:
        """Transform a data type between dialects."""
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
            if self._target == "tsql":
                self._warnings.append(
                    f"%%TYPE reference '{dt.name}' has no T-SQL equivalent. "
                    "Manual type resolution required."
                )
                return DataType(name="SQL_VARIANT")
            if self._target in ("postgresql", "mysql"):
                self._warnings.append(
                    f"%%TYPE reference '{dt.name}' could not be resolved "
                    "without a database connection (use --db-url). Emitted "
                    "as-is for manual review."
                )
            return dt

        # Handle VARCHAR(MAX) → CLOB/TEXT
        if type_name in ("VARCHAR", "NVARCHAR") and dt.params == (-1,):
            if self._target == "oracle":
                return DataType(name="CLOB" if type_name == "VARCHAR" else "NCLOB")
            elif self._target == "postgresql":
                return DataType(name="TEXT")
            elif self._target == "mysql":
                return DataType(name="LONGTEXT")

        # Lookup in mapping table
        type_map = self._get_type_map()
        base_type = type_name.split("(")[0].strip()
        if base_type in type_map:
            new_name = type_map[base_type]
            # If the mapping includes params (e.g., NUMBER(10)),
            # parse them out
            if "(" in new_name:
                match = re.match(r"(\w+)\((.+)\)", new_name)
                if match:
                    name = match.group(1)
                    params_str = match.group(2).split(",")
                    params = tuple(int(p.strip()) for p in params_str)
                    return DataType(name=name, params=params)
                return DataType(name=new_name)
            return DataType(name=new_name, params=dt.params)

        return dt

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
        """Return schema for target dialect; strip SQL Server's 'dbo' for Oracle."""
        if self._target == "oracle" and schema and schema.lower() == "dbo":
            return None
        return schema

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
        if self._target in ("oracle", "postgresql", "mysql"):
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
        new_body = self._transform_body(node.body)
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

    def _transform_declare(self, node: DeclareStatement) -> DeclareStatement:
        new_name = self._transform_var_name(node.name)
        new_type = self._transform_data_type(node.data_type)
        new_default = self._transform_node(node.default) if node.default else None
        self._var_map[node.name] = new_name
        return DeclareStatement(name=new_name, data_type=new_type, default=new_default)

    def _transform_set_variable(self, node: SetVariableStatement) -> ASTNode:
        new_name = self._transform_var_name(node.name)
        new_value = self._transform_node(node.value)
        if self._target in ("oracle", "postgresql"):
            return AssignmentStatement(target=new_name, value=new_value)
        return SetVariableStatement(name=new_name, value=new_value)

    def _transform_assignment(self, node: AssignmentStatement) -> ASTNode:
        new_name = self._transform_var_name(node.target)
        new_value = self._transform_node(node.value)
        if self._target == "tsql":
            return SetVariableStatement(name=new_name, value=new_value)
        return AssignmentStatement(target=new_name, value=new_value)

    def _transform_if(self, node: IfStatement) -> IfStatement:
        new_cond = self._transform_node(node.condition)
        new_then = self._transform_body(node.then_body)
        new_else = self._transform_body(node.else_body)
        return IfStatement(condition=new_cond, then_body=new_then, else_body=new_else)

    def _transform_while(self, node: WhileStatement) -> WhileStatement:
        new_cond = self._transform_node(node.condition)
        new_body = self._transform_body(node.body)
        return WhileStatement(condition=new_cond, body=new_body)

    def _transform_begin_end(self, node: BeginEndBlock) -> BeginEndBlock:
        return BeginEndBlock(statements=self._transform_body(node.statements))

    def _transform_statement_list(self, node: StatementList) -> StatementList:
        return StatementList(statements=self._transform_body(node.statements))

    def _transform_try_catch(self, node: TryCatchBlock) -> ASTNode:
        if self._target == "oracle":
            return ExceptionBlock(
                handlers=(
                    ExceptionHandler(
                        exception_name="OTHERS",
                        body=self._transform_body(node.catch_body),
                    ),
                )
            )
        new_try = self._transform_body(node.try_body)
        new_catch = self._transform_body(node.catch_body)
        return TryCatchBlock(try_body=new_try, catch_body=new_catch)

    def _transform_exception_block(self, node: ExceptionBlock) -> ASTNode:
        if self._target == "tsql":
            body: list[ASTNode] = []
            for handler in node.handlers:
                body.extend(handler.body)
            return TryCatchBlock(
                try_body=(),
                catch_body=self._transform_body(tuple(body)),
            )
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
        new_body = self._transform_body(node.body)
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
                body=self._transform_body(node.body),
            )
        return LoopStatement(body=self._transform_body(node.body))

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
        return EmbeddedDML(sql=sql, dialect=self._target)

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
        if (
            self._source == "tsql"
            and self._target in ("oracle", "postgresql")
            and _dml_count == 1
            and re.search(r"\bSELECT\b", sql, re.IGNORECASE)
        ):
            try:
                source_dialect = self._get_sqlglot_dialect(self._source)
                target_dialect = self._get_sqlglot_dialect(self._target)
                results = sqlglot.transpile(
                    f"SELECT {sql}",
                    read=source_dialect,
                    write=target_dialect,
                    error_level=sqlglot.ErrorLevel.RAISE,
                )
                if results and results[0].upper().startswith("SELECT "):
                    sql = results[0][len("SELECT ") :].rstrip().rstrip(";")
                    if self._target == "oracle":
                        sql = self._fix_oracle_dml(sql)
            except Exception:
                pass
        return RawSQL(sql=sql, reason=node.reason)

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
