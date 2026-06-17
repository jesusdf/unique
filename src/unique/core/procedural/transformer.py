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

import sqlglot

from unique.core.ast_nodes import (
    ASTNode,
    AlterProcedureStatement,
    AssignmentStatement,
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
    Literal,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    Script,
    SelectIntoStatement,
    SetVariableStatement,
    TryCatchBlock,
    TypeReference,
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

# Function mapping tables
_TSQL_TO_ORACLE_FUNCS: dict[str, str] = {
    "GETDATE": "SYSDATE",
    "ISNULL": "NVL",
    "LEN": "LENGTH",
    "CHARINDEX": "INSTR",
    "NEWID": "SYS_GUID",
    "SCOPE_IDENTITY": "SEQUENCE_NAME.CURRVAL",
    "DATEDIFF": "-- DATEDIFF requires manual conversion",
    "DATEADD": "-- DATEADD requires manual conversion",
}

_ORACLE_TO_TSQL_FUNCS: dict[str, str] = {
    "SYSDATE": "GETDATE()",
    "NVL": "ISNULL",
    "LENGTH": "LEN",
    "INSTR": "CHARINDEX",
    "SYS_GUID": "NEWID",
    "TO_CHAR": "CONVERT",
    "TO_DATE": "CONVERT",
    "TO_NUMBER": "CAST",
    "DECODE": "-- DECODE requires CASE conversion",
    "TRUNC": "-- TRUNC requires manual conversion",
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
        handlers = {
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
            new_default = (
                self._transform_node(p.default) if p.default else None
            )
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
        elif self._source in ("oracle", "postgresql") and self._target == "tsql":
            # V_VARNAME or v_varname → @VarName
            clean = name
            if clean.upper().startswith("V_"):
                clean = clean[2:]
            return f"@{clean.lower()}"
        return name

    def _transform_var_in_sql(self, sql: str) -> str:
        """Transform variable references within raw SQL text."""
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
        elif self._source in ("oracle", "postgresql") and self._target == "tsql":
            for old_name, new_name in self._var_map.items():
                sql = re.sub(
                    rf"\b{re.escape(old_name)}\b", new_name, sql
                )
        return sql

    def _transform_system_var(self, var: str) -> str:
        """Transform system variables like @@ROWCOUNT."""
        upper = var.upper()
        if self._target == "oracle":
            mapping = {
                "@@ROWCOUNT": "SQL%ROWCOUNT",
                "@@IDENTITY": "SEQUENCE_NAME.CURRVAL",
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
        return var

    # ---------------------------------------------------------------
    # Data type transformations
    # ---------------------------------------------------------------

    def _transform_data_type(self, dt: DataType) -> DataType:
        """Transform a data type between dialects."""
        type_name = dt.name.upper()

        # Handle %TYPE references
        if "%TYPE" in type_name or "%ROWTYPE" in type_name:
            if self._target == "tsql":
                self._warnings.append(
                    f"%%TYPE reference '{dt.name}' has no T-SQL equivalent. "
                    "Manual type resolution required."
                )
                return DataType(name="SQL_VARIANT")
            return dt

        # Handle VARCHAR(MAX) → CLOB/TEXT
        if type_name in ("VARCHAR", "NVARCHAR") and dt.params == (-1,):
            if self._target == "oracle":
                return DataType(name="CLOB" if type_name == "VARCHAR" else "NCLOB")
            elif self._target == "postgresql":
                return DataType(name="TEXT")

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
            "tsql_postgresql": _TSQL_TO_PG_TYPES,
        }
        return maps.get(key, {})

    # ---------------------------------------------------------------
    # Node-specific transformations
    # ---------------------------------------------------------------

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
            schema=node.schema,
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
                schema=node.schema,
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
            self._transform_data_type(node.return_type)
            if node.return_type
            else None
        )
        return CreateFunctionStatement(
            name=node.name,
            parameters=new_params,
            return_type=new_return,
            body=new_body,
            or_replace=True if self._target != "tsql" else node.or_replace,
            schema=node.schema,
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
            schema=node.schema,
        )

    def _transform_declare(self, node: DeclareStatement) -> DeclareStatement:
        new_name = self._transform_var_name(node.name)
        new_type = self._transform_data_type(node.data_type)
        new_default = (
            self._transform_node(node.default) if node.default else None
        )
        self._var_map[node.name] = new_name
        return DeclareStatement(
            name=new_name, data_type=new_type, default=new_default
        )

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
        return IfStatement(
            condition=new_cond, then_body=new_then, else_body=new_else
        )

    def _transform_while(self, node: WhileStatement) -> WhileStatement:
        new_cond = self._transform_node(node.condition)
        new_body = self._transform_body(node.body)
        return WhileStatement(condition=new_cond, body=new_body)

    def _transform_begin_end(self, node: BeginEndBlock) -> BeginEndBlock:
        return BeginEndBlock(statements=self._transform_body(node.statements))

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
        return ExecuteStatement(sql_expression=new_expr, params=node.params)

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
        if self._target == "tsql":
            return RawSQL(sql="BREAK", reason="EXIT → BREAK")
        new_cond = self._transform_node(node.condition) if node.condition else None
        return ExitStatement(condition=new_cond)

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
        return EmbeddedDML(sql=sql, dialect=self._target)

    def _transform_null(self, node: NullStatement) -> ASTNode:
        if self._target == "tsql":
            return RawSQL(sql="-- NULL statement (no-op)", reason="no T-SQL equivalent")
        return node

    def _transform_raw_sql(self, node: RawSQL) -> RawSQL:
        sql = self._transform_var_in_sql(node.sql)
        # Apply function name transformations
        sql = self._transform_functions_in_sql(sql)
        return RawSQL(sql=sql, reason=node.reason)

    def _transform_functions_in_sql(self, sql: str) -> str:
        """Transform function names in raw SQL text."""
        func_map = self._get_func_map()
        for old, new in func_map.items():
            if not new.startswith("--"):
                sql = re.sub(
                    rf"\b{re.escape(old)}\b", new, sql, flags=re.IGNORECASE
                )
        return sql

    def _get_func_map(self) -> dict[str, str]:
        key = f"{self._source}_{self._target}"
        maps = {
            "tsql_oracle": _TSQL_TO_ORACLE_FUNCS,
            "oracle_tsql": _ORACLE_TO_TSQL_FUNCS,
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
