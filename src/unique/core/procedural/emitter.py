# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter.

Generates target-dialect procedural SQL code from IR AST nodes.
Each target dialect has its own emission rules for procedures,
functions, triggers, and control flow constructs.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CommentStatement,
    ContinueStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    CursorDeclaration,
    CursorOperation,
    DataType,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
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
    SelectIntoStatement,
    SetVariableStatement,
    StatementList,
    TryCatchBlock,
    WhileStatement,
)

logger = logging.getLogger(__name__)


class ProceduralEmitter:
    """Emits procedural SQL code for a target dialect.

    Generates syntactically correct procedural code from IR AST nodes,
    using the conventions and syntax of the target dialect.
    """

    def __init__(self, dialect: str) -> None:
        self._dialect = dialect
        self._indent_level = 0
        self._indent_str = "    "
        # Label of the current MySQL procedure block, used to translate a bare
        # RETURN (early exit) into LEAVE <label>; None when not applicable.
        self._proc_leave_label: str | None = None
        # Whether the MySQL routine body currently being emitted is a function
        # (RETURN <value> valid) vs a procedure (RETURN illegal -> LEAVE).
        self._in_mysql_function = False
        # Whether a PostgreSQL *procedure* body is being emitted. A PG procedure
        # cannot RETURN a value (only RETURN; to exit early), unlike a function.
        self._in_pg_procedure = False

    def emit(self, node: ASTNode) -> str:
        """Emit a procedural AST node as target-dialect SQL.

        Args:
            node: The AST node to emit.

        Returns:
            The generated SQL text.
        """
        return self._emit_node(node)

    def _indent(self) -> str:
        return self._indent_str * self._indent_level

    def _emit_node(self, node: ASTNode) -> str:
        """Dispatch emission based on node type."""
        emitters: dict[type, Callable[..., str]] = {
            CreateProcedureStatement: self._emit_procedure,
            AlterProcedureStatement: self._emit_alter_procedure,
            CreateFunctionStatement: self._emit_function,
            CreateTriggerStatement: self._emit_trigger,
            DeclareStatement: self._emit_declare,
            SetVariableStatement: self._emit_set_variable,
            AssignmentStatement: self._emit_assignment,
            IfStatement: self._emit_if,
            WhileStatement: self._emit_while,
            ForLoopStatement: self._emit_for_loop,
            LoopStatement: self._emit_loop,
            BeginEndBlock: self._emit_begin_end,
            StatementList: self._emit_statement_list,
            TryCatchBlock: self._emit_try_catch,
            ExceptionBlock: self._emit_exception_block,
            ExecuteStatement: self._emit_execute,
            PrintStatement: self._emit_print,
            RaiseErrorStatement: self._emit_raise_error,
            ReturnStatement: self._emit_return,
            CursorDeclaration: self._emit_cursor_decl,
            CursorOperation: self._emit_cursor_op,
            ExitStatement: self._emit_exit,
            ContinueStatement: self._emit_continue,
            NullStatement: self._emit_null,
            CommentStatement: self._emit_comment,
            EmbeddedDML: self._emit_embedded_dml,
            SelectIntoStatement: self._emit_select_into,
            RawSQL: self._emit_raw_sql,
            Literal: self._emit_literal,
        }

        emitter = emitters.get(type(node))
        if emitter:
            return emitter(node)
        return f"/* UNSUPPORTED: {type(node).__name__} */"

    def _emit_body(self, stmts: tuple[ASTNode, ...], separator: str = "\n") -> str:
        """Emit a sequence of body statements."""
        lines: list[str] = []
        for stmt in stmts:
            text = self._emit_node(stmt)
            if text.strip():
                lines.append(text)
        return separator.join(lines)

    def _emit_data_type(self, dt: DataType) -> str:
        """Emit a data type, appending a /* UNIQUE */ marker when the original
        source type was preserved for documentation/round-tripping."""
        if dt.params:
            params = ", ".join("MAX" if p == -1 else str(p) for p in dt.params)
            base = f"{dt.name}({params})"
        else:
            base = dt.name
        if dt.origin_comment:
            return f"{base} /* UNIQUE: {dt.origin_comment} */"
        return base

    def _emit_params(
        self,
        params: tuple[ParameterDefinition, ...],
        is_function: bool = False,
    ) -> str:
        """Emit parameter list.

        ``is_function`` matters for MySQL, whose stored *functions* forbid the
        IN/OUT/INOUT direction keywords that procedures require.
        """
        # PostgreSQL: only IN parameters may carry a DEFAULT, and an OUT/INOUT
        # parameter cannot appear after a parameter that has a default. Compute
        # the position of the last OUT/INOUT param so we can drop the default
        # from any IN param before it (and from every OUT/INOUT param), keeping
        # the routine creatable.
        pg_last_out = -1
        if self._dialect == "postgresql":
            for i, q in enumerate(params):
                if q.direction in ("OUT", "INOUT"):
                    pg_last_out = i

        parts: list[str] = []
        for idx, p in enumerate(params):
            dt = self._emit_data_type(p.data_type)
            default_str = ""
            keep_default = bool(p.default)
            if self._dialect == "postgresql" and p.default:
                if p.direction in ("OUT", "INOUT") or idx < pg_last_out:
                    keep_default = False
            if keep_default and p.default:
                val = self._emit_node(p.default)
                if self._dialect == "tsql":
                    default_str = f" = {val}"
                else:
                    default_str = f" DEFAULT {val}"

            if self._dialect == "tsql":
                direction_str = " OUTPUT" if p.direction in ("OUT", "INOUT") else ""
                parts.append(
                    f"{self._indent()}{p.name} {dt}{default_str}{direction_str}"
                )
            elif self._dialect == "mysql":
                # MySQL puts the direction *before* the parameter name and does
                # not support per-parameter DEFAULT values; callers must always
                # pass every argument. The default is dropped (and surfaced as a
                # warning by the caller) rather than emitted as invalid syntax.
                # Stored functions forbid direction keywords entirely.
                direction_str = ""
                if not is_function:
                    if p.direction in ("OUT", "INOUT"):
                        direction_str = f"{p.direction} "
                    elif p.direction == "IN":
                        direction_str = "IN "
                parts.append(f"{self._indent()}{direction_str}{p.name} {dt}")
            else:
                direction_str = ""
                if p.direction != "IN":
                    direction_str = f"{p.direction} "
                elif self._dialect == "oracle":
                    direction_str = "IN "
                parts.append(
                    f"{self._indent()}{p.name} {direction_str}{dt}{default_str}"
                )
        return ",\n".join(parts)

    # ---------------------------------------------------------------
    # Procedure / Function / Trigger
    # ---------------------------------------------------------------

    def _qualified_name(self, schema: str | None, name: str) -> str:
        """Build a schema-qualified object name.

        T-SQL's default ``dbo`` schema has no counterpart in the other engines:
        MySQL has no schema layer (a schema is a database), and in Oracle and
        PostgreSQL ``dbo`` names a schema that doesn't exist. So drop a ``dbo``
        qualifier for those targets and emit the bare name; preserve any other
        (intentional) schema. For MySQL, drop any schema qualifier.
        """
        if not schema:
            return name
        if self._dialect == "mysql":
            return name
        if schema.lower() == "dbo" and self._dialect in ("oracle", "postgresql"):
            return name
        return f"{schema}.{name}"

    @staticmethod
    def _split_declarations(
        body: tuple[ASTNode, ...],
    ) -> tuple[list[ASTNode], list[ASTNode]]:
        """Split a routine body into (declarations, executable statements).

        A multi-variable ``DECLARE @a X, @b Y`` is parsed into a ``StatementList``
        of ``DeclareStatement``s; flatten such lists so every declaration is
        hoisted. Oracle and PostgreSQL require all declarations in a section
        before ``BEGIN`` (PostgreSQL has no ``DECLARE`` keyword inside the body),
        so a declaration left inline produces invalid SQL.
        """
        declarations: list[ASTNode] = []
        body_stmts: list[ASTNode] = []
        for stmt in body:
            if isinstance(stmt, (DeclareStatement, CursorDeclaration)):
                declarations.append(stmt)
            elif isinstance(stmt, StatementList) and stmt.statements and all(
                isinstance(s, (DeclareStatement, CursorDeclaration))
                for s in stmt.statements
            ):
                declarations.extend(stmt.statements)
            else:
                body_stmts.append(stmt)
        return declarations, body_stmts

    def _emit_procedure(self, node: CreateProcedureStatement) -> str:
        name = self._qualified_name(node.schema, node.name)

        if self._dialect == "tsql":
            header = f"CREATE PROCEDURE {name}"
        elif self._dialect == "oracle" or self._dialect == "postgresql":
            prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
            header = f"{prefix}PROCEDURE {name}"
        else:
            header = f"CREATE PROCEDURE {name}"

        self._indent_level += 1
        params_str = self._emit_params(node.parameters)
        self._indent_level -= 1

        if params_str:
            header += f"\n(\n{params_str}\n)"
        elif self._dialect in ("mysql", "postgresql"):
            # MySQL and PostgreSQL require the parameter parentheses even when
            # empty (CREATE PROCEDURE p() ...); omitting them is a syntax error.
            header += "()"

        # Separate declarations from body statements
        declarations, body_stmts = self._split_declarations(node.body)

        if self._dialect == "tsql":
            return self._emit_tsql_procedure_body(header, declarations, body_stmts)
        elif self._dialect == "oracle":
            return self._emit_oracle_procedure_body(header, declarations, body_stmts)
        elif self._dialect == "postgresql":
            return self._emit_pg_procedure_body(header, declarations, body_stmts)
        else:
            return self._emit_mysql_procedure_body(header, declarations, body_stmts)

    def _emit_tsql_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        lines = [f"{header}\nAS\nBEGIN"]
        self._indent_level = 1
        lines.append(f"{self._indent()}SET NOCOUNT ON;\n")
        for decl in declarations:
            lines.append(f"{self._indent()}{self._emit_node(decl)}")
        if declarations:
            lines.append("")
        for stmt in body_stmts:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0
        lines.append("END")
        return "\n".join(lines)

    def _emit_oracle_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        lines = [f"{header}"]
        if declarations:
            lines.append("IS")
            self._indent_level = 1
            for decl in declarations:
                lines.append(f"{self._indent()}{self._emit_node(decl)}")
            self._indent_level = 0
        else:
            lines.append("AS")

        lines.append("BEGIN")
        self._indent_level = 1
        for stmt in body_stmts:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0
        lines.append("END;")
        return "\n".join(lines)

    def _emit_pg_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
        is_function: bool = False,
    ) -> str:
        prev_in_proc = self._in_pg_procedure
        self._in_pg_procedure = not is_function
        lines = [f"{header}"]
        lines.append("LANGUAGE plpgsql")
        lines.append("AS $$")
        if declarations:
            lines.append("DECLARE")
            self._indent_level = 1
            for decl in declarations:
                lines.append(f"{self._indent()}{self._emit_node(decl)}")
            self._indent_level = 0
        lines.append("BEGIN")
        self._indent_level = 1
        for stmt in body_stmts:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0
        lines.append("END;")
        lines.append("$$;")
        self._in_pg_procedure = prev_in_proc
        return "\n".join(lines)

    def _emit_mysql_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
        is_function: bool = False,
    ) -> str:
        # RETURN in a MySQL *procedure* is illegal ("RETURN is only allowed in a
        # FUNCTION") — both a bare early-exit RETURN and a RETURN <value> (a
        # T-SQL procedure status code, which MySQL has no concept of). In a
        # procedure, translate any RETURN to LEAVE of a labeled block. In a
        # function, RETURN <value> is valid and kept as-is.
        prev_is_fn = self._in_mysql_function
        self._in_mysql_function = is_function
        needs_label = (not is_function) and self._body_has_any_return(body_stmts)
        prev_label = self._proc_leave_label
        lines = [f"{header}"]
        if needs_label:
            self._proc_leave_label = "proc_exit"
            lines.append(f"{self._proc_leave_label}: BEGIN")
        else:
            self._proc_leave_label = None
            lines.append("BEGIN")
        self._indent_level = 1
        for decl in declarations:
            lines.append(f"{self._indent()}{self._emit_node(decl)}")
        if declarations:
            lines.append("")
        for stmt in body_stmts:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0
        lines.append("END")
        self._proc_leave_label = prev_label
        self._in_mysql_function = prev_is_fn
        return "\n".join(lines)

    def _body_has_any_return(self, stmts: list[ASTNode]) -> bool:
        """Whether any statement (recursively) is a RETURN (with or without a
        value). In a MySQL procedure even ``RETURN <value>`` is invalid."""
        for s in stmts:
            if isinstance(s, ReturnStatement):
                return True
            for attr in ("body", "then_body", "else_body", "try_body", "catch_body"):
                child = getattr(s, attr, None)
                if child and self._body_has_any_return(list(child)):
                    return True
        return False

    def _emit_alter_procedure(self, node: AlterProcedureStatement) -> str:
        """Emit ALTER PROCEDURE (T-SQL only)."""
        proc = CreateProcedureStatement(
            name=node.name,
            parameters=node.parameters,
            body=node.body,
            or_replace=False,
            schema=node.schema,
        )
        result = self._emit_procedure(proc)
        return result.replace("CREATE PROCEDURE", "ALTER PROCEDURE", 1)

    def _emit_function(self, node: CreateFunctionStatement) -> str:
        # T-SQL inline/multi-statement table-valued functions (RETURNS TABLE)
        # have no faithful, uniform equivalent: MySQL has no table-returning
        # functions at all; PostgreSQL needs RETURNS TABLE(col type ...) with
        # RETURN QUERY; Oracle needs a pipelined function over a declared
        # collection type. Rather than emit invalid SQL, document it for the
        # other engines and comment out the (non-portable) translation so the
        # surrounding script stays valid.
        if (
            node.return_type is not None
            and node.return_type.name.upper() == "TABLE"
            and self._dialect != "tsql"
        ):
            return self._emit_table_valued_function(node)
        return self._emit_function_impl(node)

    def _emit_table_valued_function(self, node: CreateFunctionStatement) -> str:
        engine = {
            "mysql": "MySQL has no table-returning functions; use a view or a "
            "procedure with a result set",
            "postgresql": "PostgreSQL needs RETURNS TABLE(col type ...) with "
            "RETURN QUERY; review the column list",
            "oracle": "Oracle needs a pipelined function over a declared "
            "collection type; review manually",
        }.get(self._dialect, "no direct equivalent on this engine")
        note = (
            f"-- UNIQUE: inline table-valued function ('RETURNS TABLE') has no "
            f"direct equivalent. {engine}.\n"
            f"-- The non-portable translation is commented out below for "
            f"review:\n"
        )
        body = self._emit_function_impl(node)
        commented = "\n".join(
            f"-- {line}" if line.strip() else "--" for line in body.split("\n")
        )
        return note + commented

    def _emit_function_impl(self, node: CreateFunctionStatement) -> str:
        name = self._qualified_name(node.schema, node.name)
        ret_type = (
            self._emit_data_type(node.return_type) if node.return_type else "void"
        )

        if self._dialect == "tsql":
            header = f"CREATE FUNCTION {name}"
        elif self._dialect == "oracle":
            prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
            header = f"{prefix}FUNCTION {name}"
        elif self._dialect == "mysql":
            # MySQL stored functions do not support CREATE OR REPLACE; the
            # idempotent DROP is emitted separately by the transpiler when
            # needed. Always a plain CREATE here.
            header = f"CREATE FUNCTION {name}"
        else:
            prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
            header = f"{prefix}FUNCTION {name}"

        self._indent_level += 1
        params_str = self._emit_params(node.parameters, is_function=True)
        self._indent_level -= 1

        if params_str:
            header += f"\n(\n{params_str}\n)"
        elif self._dialect in ("mysql", "postgresql"):
            # MySQL and PostgreSQL require the parameter parentheses even when
            # empty (CREATE FUNCTION f() ...); omitting them is a syntax error.
            # Oracle allows a parameterless function with no parentheses.
            header += "()"

        if self._dialect in ("tsql", "postgresql"):
            header += f"\nRETURNS {ret_type}"
        elif self._dialect == "mysql":
            header += f"\nRETURNS {ret_type}\nDETERMINISTIC"
        elif self._dialect == "oracle":
            header += f"\nRETURN {ret_type}"

        declarations, body_stmts = self._split_declarations(node.body)

        if self._dialect == "tsql":
            return self._emit_tsql_procedure_body(header, declarations, body_stmts)
        elif self._dialect == "oracle":
            return self._emit_oracle_procedure_body(header, declarations, body_stmts)
        elif self._dialect == "postgresql":
            return self._emit_pg_procedure_body(
                header, declarations, body_stmts, is_function=True
            )
        else:
            return self._emit_mysql_procedure_body(
                header, declarations, body_stmts, is_function=True
            )

    def _emit_trigger(self, node: CreateTriggerStatement) -> str:
        name = self._qualified_name(node.schema, node.name)
        events = ", ".join(node.events) if node.events else "UPDATE"
        timing = node.timing

        # MySQL has no INSTEAD OF triggers (they apply to views in T-SQL/PG and
        # have no MySQL form). Document the substitution and fall back to BEFORE
        # so the trigger is at least syntactically valid for review.
        instead_of_note = ""
        if self._dialect == "mysql" and timing.upper().startswith("INSTEAD OF"):
            instead_of_note = (
                "-- UNIQUE: MySQL has no INSTEAD OF trigger; emitted as BEFORE "
                "for review (original was INSTEAD OF, typically on a view).\n"
            )
            timing = "BEFORE"

        if self._dialect == "tsql":
            lines = [f"CREATE TRIGGER {name} ON {node.table}"]
            lines.append(f"{node.timing} {events}")
            lines.append("AS")
            lines.append("BEGIN")
        elif self._dialect == "oracle":
            prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
            lines = [f"{prefix}TRIGGER {name}"]
            lines.append(f"{node.timing} {events} ON {node.table}")
            if node.for_each == "ROW":
                lines.append("FOR EACH ROW")
            lines.append("BEGIN")
        elif self._dialect == "postgresql":
            # PostgreSQL triggers call a separate trigger function that returns
            # a trigger and contains the body. Emit both the function and the
            # CREATE TRIGGER that invokes it.
            func_name = f"{node.name}_func"
            qfunc = self._qualified_name(node.schema, func_name)
            fn_lines = [
                f"CREATE OR REPLACE FUNCTION {qfunc}()",
                "RETURNS TRIGGER",
                "LANGUAGE plpgsql",
                "AS $$",
            ]
            # Variable declarations must live in a DECLARE section before BEGIN
            # (PostgreSQL has no inline DECLARE), so hoist them like a routine.
            trg_decls, trg_body = self._split_declarations(tuple(node.body))
            if trg_decls:
                fn_lines.append("DECLARE")
                self._indent_level = 1
                for decl in trg_decls:
                    fn_lines.append(f"{self._indent()}{self._emit_node(decl)}")
                self._indent_level = 0
            fn_lines.append("BEGIN")
            self._indent_level = 1
            for stmt in trg_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    fn_lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level = 0
            # A row-level AFTER trigger conventionally returns NULL; a BEFORE
            # trigger returns NEW. Default to NEW, which is safe for BEFORE and
            # ignored for AFTER row-level triggers.
            fn_lines.append("    RETURN NEW;")
            fn_lines.append("END;")
            fn_lines.append("$$;")
            trg_lines = [
                f"CREATE OR REPLACE TRIGGER {name}",
                f"{node.timing} {events} ON {node.table}",
            ]
            if node.for_each == "ROW":
                trg_lines.append("FOR EACH ROW")
            trg_lines.append(f"EXECUTE FUNCTION {qfunc}();")
            return "\n".join(fn_lines) + "\n\n" + "\n".join(trg_lines)
        else:
            lines = [f"CREATE TRIGGER {name}"]
            lines.append(f"{timing} {events} ON {node.table}")
            lines.append("FOR EACH ROW")
            lines.append("BEGIN")

        self._indent_level = 1
        for stmt in node.body:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0

        if self._dialect == "oracle":
            lines.append("END;")
        else:
            lines.append("END")
        return instead_of_note + "\n".join(lines)

    # ---------------------------------------------------------------
    # Declarations
    # ---------------------------------------------------------------

    def _emit_declare(self, node: DeclareStatement) -> str:
        dt = self._emit_data_type(node.data_type)
        default_str = ""
        if node.default:
            val = self._emit_node(node.default)
            if self._dialect == "tsql":
                default_str = f" = {val}"
            elif self._dialect == "mysql":
                default_str = f" DEFAULT {val}"
            else:
                default_str = f" := {val}"

        if self._dialect in ("tsql", "mysql"):
            return f"DECLARE {node.name} {dt}{default_str};"
        else:
            return f"{node.name} {dt}{default_str};"

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        query_str = ""
        if node.query:
            # The query may be an EmbeddedDML that emits its own trailing
            # semicolon; strip it to avoid a double ';'.
            query_str = self._emit_node(node.query).rstrip().rstrip(";")

        if self._dialect == "tsql":
            body = f" FOR {query_str}" if query_str else ""
            return f"DECLARE {node.name} CURSOR{body};"
        elif self._dialect == "postgresql":
            # PL/pgSQL: name CURSOR FOR <select>;
            body = f" CURSOR FOR {query_str}" if query_str else " CURSOR"
            return f"{node.name}{body};"
        elif self._dialect == "mysql":
            # MySQL: DECLARE name CURSOR FOR <select>;
            body = f" FOR {query_str}" if query_str else ""
            return f"DECLARE {node.name} CURSOR{body};"
        else:
            # Oracle PL/SQL: CURSOR name IS <select>;
            body = f" IS {query_str}" if query_str else ""
            return f"CURSOR {node.name}{body};"

    # ---------------------------------------------------------------
    # Variable operations
    # ---------------------------------------------------------------

    def _emit_set_variable(self, node: SetVariableStatement) -> str:
        val = self._emit_node(node.value)
        return f"SET {node.name} = {val};"

    def _emit_assignment(self, node: AssignmentStatement) -> str:
        val = self._emit_node(node.value)
        if self._dialect in ("tsql", "mysql"):
            return f"SET {node.target} = {val};"
        return f"{node.target} := {val};"

    # ---------------------------------------------------------------
    # Control flow
    # ---------------------------------------------------------------

    def _emit_if(self, node: IfStatement) -> str:
        cond = self._emit_node(node.condition)

        if self._dialect == "tsql":
            return self._emit_tsql_if(cond, node.then_body, node.else_body)
        else:
            return self._emit_plsql_if(cond, node.then_body, node.else_body)

    def _emit_tsql_if(
        self,
        cond: str,
        then_body: tuple[ASTNode, ...],
        else_body: tuple[ASTNode, ...],
    ) -> str:
        lines = [f"IF {cond}"]
        lines.append("BEGIN")
        self._indent_level += 1
        for stmt in then_body:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level -= 1
        lines.append("END")

        if else_body:
            if len(else_body) == 1 and isinstance(else_body[0], IfStatement):
                lines.append(f"ELSE {self._emit_node(else_body[0])}")
            else:
                lines.append("ELSE")
                lines.append("BEGIN")
                self._indent_level += 1
                for stmt in else_body:
                    text = self._emit_node(stmt)
                    for line in text.split("\n"):
                        lines.append(f"{self._indent()}{line}" if line.strip() else "")
                self._indent_level -= 1
                lines.append("END")

        return "\n".join(lines)

    def _emit_plsql_if(
        self,
        cond: str,
        then_body: tuple[ASTNode, ...],
        else_body: tuple[ASTNode, ...],
    ) -> str:
        lines = [f"IF {cond} THEN"]
        self._indent_level += 1
        for stmt in then_body:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level -= 1

        if else_body:
            if len(else_body) == 1 and isinstance(else_body[0], IfStatement):
                nested_cond = self._emit_node(else_body[0].condition)
                lines.append(f"ELSIF {nested_cond} THEN")
                self._indent_level += 1
                for stmt in else_body[0].then_body:
                    text = self._emit_node(stmt)
                    for line in text.split("\n"):
                        lines.append(f"{self._indent()}{line}" if line.strip() else "")
                self._indent_level -= 1
                if else_body[0].else_body:
                    lines.append("ELSE")
                    self._indent_level += 1
                    for stmt in else_body[0].else_body:
                        text = self._emit_node(stmt)
                        for line in text.split("\n"):
                            lines.append(
                                f"{self._indent()}{line}" if line.strip() else ""
                            )
                    self._indent_level -= 1
            else:
                lines.append("ELSE")
                self._indent_level += 1
                for stmt in else_body:
                    text = self._emit_node(stmt)
                    for line in text.split("\n"):
                        lines.append(f"{self._indent()}{line}" if line.strip() else "")
                self._indent_level -= 1

        lines.append("END IF;")
        return "\n".join(lines)

    def _emit_while(self, node: WhileStatement) -> str:
        cond = self._emit_node(node.condition)
        if self._dialect == "tsql":
            lines = [f"WHILE {cond}"]
            lines.append("BEGIN")
            self._indent_level += 1
            for stmt in node.body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("END")
        else:
            lines = [f"WHILE {cond} LOOP"]
            self._indent_level += 1
            for stmt in node.body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("END LOOP;")
        return "\n".join(lines)

    def _emit_for_loop(self, node: ForLoopStatement) -> str:
        cursor_str = self._emit_node(node.cursor) if node.cursor else ""
        cursor_str = cursor_str.rstrip().rstrip(";")

        body_lines: list[str] = []
        self._indent_level += 1
        for stmt in node.body:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                body_lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level -= 1

        if self._dialect in ("oracle", "postgresql"):
            # Native cursor FOR loop.
            lines = [f"FOR {node.variable} IN {cursor_str} LOOP"]
            lines.extend(body_lines)
            lines.append("END LOOP;")
            return "\n".join(lines)

        # T-SQL and MySQL have no implicit cursor FOR loop. Emit an explicit
        # cursor scaffold (structurally complete) so the developer only needs
        # to fill the per-column fetch variables.
        if self._dialect == "tsql":
            cur = f"{node.variable}_cur"
            lines = [
                "-- UNIQUE: Oracle implicit cursor FOR-loop expanded to an "
                "explicit T-SQL cursor.",
                "-- Declare one @var per selected column and complete the "
                "FETCH INTO list.",
                f"DECLARE {cur} CURSOR LOCAL FAST_FORWARD FOR",
                f"{cursor_str};",
                f"OPEN {cur};",
                f"FETCH NEXT FROM {cur} INTO /* @col1, @col2, ... */;",
                "WHILE @@FETCH_STATUS = 0",
                "BEGIN",
            ]
            lines.extend(body_lines)
            lines.append(
                f"{self._indent()}FETCH NEXT FROM {cur} INTO "
                "/* @col1, @col2, ... */;"
            )
            lines.append("END;")
            lines.append(f"CLOSE {cur};")
            lines.append(f"DEALLOCATE {cur};")
            return "\n".join(lines)

        # mysql: explicit cursor inside a BEGIN ... END with a NOT FOUND
        # handler driving a loop.
        cur = f"{node.variable}_cur"
        done = f"{node.variable}_done"
        lines = [
            "-- UNIQUE: Oracle implicit cursor FOR-loop expanded to an "
            "explicit MySQL cursor.",
            "-- Declare one variable per selected column and complete the "
            "FETCH INTO list.",
            f"DECLARE {done} INT DEFAULT FALSE;",
            f"DECLARE {cur} CURSOR FOR {cursor_str};",
            f"DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE;",
            f"OPEN {cur};",
            f"{node.variable}_loop: LOOP",
            f"{self._indent()}FETCH {cur} INTO /* col1, col2, ... */;",
            f"{self._indent()}IF {done} THEN LEAVE {node.variable}_loop; END IF;",
        ]
        lines.extend(body_lines)
        lines.append("END LOOP;")
        lines.append(f"CLOSE {cur};")
        return "\n".join(lines)

    def _emit_loop(self, node: LoopStatement) -> str:
        body_lines: list[str] = []
        self._indent_level += 1
        for stmt in node.body:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                body_lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level -= 1

        if self._dialect == "tsql":
            # Unconditional loop → WHILE 1 = 1 ... (exit via BREAK).
            lines = ["WHILE 1 = 1", "BEGIN"]
            lines.extend(body_lines)
            lines.append("END")
            return "\n".join(lines)
        if self._dialect == "mysql":
            lines = ["loop_lbl: LOOP"]
            lines.extend(body_lines)
            lines.append("END LOOP loop_lbl;")
            return "\n".join(lines)
        # Oracle / PostgreSQL
        lines = ["LOOP"]
        lines.extend(body_lines)
        lines.append("END LOOP;")
        return "\n".join(lines)

    def _emit_begin_end(self, node: BeginEndBlock) -> str:
        lines = ["BEGIN"]
        self._indent_level += 1
        for stmt in node.statements:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level -= 1
        if self._dialect == "tsql":
            lines.append("END")
        else:
            lines.append("END;")
        return "\n".join(lines)

    def _emit_statement_list(self, node: StatementList) -> str:
        """Emit a transparent statement sequence (no wrapper)."""
        return "\n".join(self._emit_node(stmt) for stmt in node.statements)

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        if self._dialect == "tsql":
            lines = ["BEGIN TRY"]
            self._indent_level += 1
            for stmt in node.try_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("END TRY")
            lines.append("BEGIN CATCH")
            self._indent_level += 1
            for stmt in node.catch_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("END CATCH")
        elif self._dialect == "mysql":
            # MySQL has no EXCEPTION block; the catch logic goes into a
            # DECLARE ... HANDLER declared at the top of the block, before the
            # protected (try) statements.
            lines = ["BEGIN"]
            self._indent_level += 1
            lines.append(f"{self._indent()}DECLARE EXIT HANDLER FOR SQLEXCEPTION")
            lines.append(f"{self._indent()}BEGIN")
            self._indent_level += 1
            for stmt in node.catch_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append(f"{self._indent()}END;")
            for stmt in node.try_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("END;")
        else:
            lines = ["BEGIN"]
            self._indent_level += 1
            for stmt in node.try_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("EXCEPTION")
            lines.append("WHEN OTHERS THEN")
            self._indent_level += 1
            for stmt in node.catch_body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            lines.append("END;")
        return "\n".join(lines)

    def _emit_exception_block(self, node: ExceptionBlock) -> str:
        lines = ["EXCEPTION"]
        for handler in node.handlers:
            lines.append(f"WHEN {handler.exception_name} THEN")
            self._indent_level += 1
            for stmt in handler.body:
                text = self._emit_node(stmt)
                for line in text.split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
        return "\n".join(lines)

    # ---------------------------------------------------------------
    # Simple statements
    # ---------------------------------------------------------------

    def _emit_execute(self, node: ExecuteStatement) -> str:
        expr = self._emit_node(node.sql_expression)
        params = [self._emit_node(p) for p in node.params]

        if self._dialect == "tsql":
            if params:
                # Map Oracle USING binds to sp_executesql positional params.
                # The dynamic SQL placeholders (:1, :2 / ?) should be replaced
                # by @p1, @p2 manually; we emit a parameterized sp_executesql
                # call and flag it for review.
                names = [f"@p{i + 1}" for i in range(len(params))]
                decl = ", ".join(f"{n} SQL_VARIANT" for n in names)
                assigns = ", ".join(
                    f"{n} = {val}" for n, val in zip(names, params, strict=False)
                )
                return (
                    f"EXEC sp_executesql {expr}, N'{decl}', {assigns}; "
                    f"-- UNIQUE: verify dynamic SQL placeholders match "
                    f"{', '.join(names)}"
                )
            return f"EXEC sp_executesql {expr};"
        elif self._dialect == "oracle":
            if params:
                using = ", ".join(params)
                return f"EXECUTE IMMEDIATE {expr} USING {using};"
            return f"EXECUTE IMMEDIATE {expr};"
        elif self._dialect == "postgresql":
            return self._emit_pg_execute(expr, params)
        # MySQL: distinguish three forms that all arrive as a captured
        # expression here:
        #   1. EXEC sp_executesql @sql, N'<decls>', @p1, ...  -> dynamic SQL
        #   2. EXEC proc_name @a OUTPUT, 'b', ...             -> a routine call
        #   3. EXEC @sql / EXEC ('...')                       -> dynamic SQL
        return self._emit_mysql_execute(expr, params)

    def _emit_pg_execute(self, expr: str, params: list[str]) -> str:
        """Emit a T-SQL EXEC for PostgreSQL.

        Like MySQL, a captured EXEC arrives as one of three shapes: a
        ``sp_executesql`` dynamic call, a named stored-procedure call, or a bare
        dynamic-SQL string/variable. PostgreSQL invokes procedures with
        ``CALL name(args)`` and runs dynamic SQL with plpgsql ``EXECUTE <text>``.
        """
        stripped = expr.strip()

        # Case 1: sp_executesql — run the first argument (the SQL text); the
        # N'...' parameter-declaration string and bindings can't be mapped to
        # USING reliably from captured text, so document and drop them.
        if re.match(r"(?i)^sp_executesql\b", stripped):
            rest = stripped[len("sp_executesql") :].strip()
            sql_arg = self._first_arg(rest)
            note = (
                " -- UNIQUE: sp_executesql parameter declarations/bindings "
                "dropped; pass them via EXECUTE ... USING manually"
                if "," in rest
                else ""
            )
            return f"EXECUTE {sql_arg};{note}"

        # Case 3: a bare variable/string/parenthesized expression is dynamic SQL.
        if stripped.startswith(("@", "v_", "'", "(", "N'")):
            if params:
                using = ", ".join(params)
                return f"EXECUTE {expr} USING {using};"
            return f"EXECUTE {expr};"

        # Case 2: a named stored-procedure call → CALL name(args). The trailing
        # T-SQL OUTPUT keyword on an argument is dropped (an INOUT argument is
        # already passed by reference).
        m = re.match(r"(?i)^([A-Za-z_]\w*)\s*(.*)$", stripped)
        if m:
            proc_name = m.group(1)
            args = self._split_exec_args(m.group(2).strip())
            return f"CALL {proc_name}({', '.join(args)});"

        if params:
            return f"EXECUTE {expr} USING {', '.join(params)};"
        return f"EXECUTE {expr};"

    def _emit_mysql_execute(self, expr: str, params: list[str]) -> str:
        stripped = expr.strip()

        # Case 1: sp_executesql. The first comma-separated argument is the SQL
        # text to run; the second (an N'...' parameter-declaration string) and
        # the remaining @name = value bindings cannot be mapped to MySQL's
        # positional PREPARE ... USING reliably from captured text, so emit the
        # dynamic execution of the SQL argument and flag the bindings for
        # review rather than emitting invalid SQL.
        if re.match(r"(?i)^sp_executesql\b", stripped):
            rest = stripped[len("sp_executesql") :].strip()
            sql_arg = self._first_arg(rest)
            note = (
                " -- UNIQUE: sp_executesql parameter declarations/bindings "
                "dropped; pass them via PREPARE ... USING manually"
                if "," in rest
                else ""
            )
            return (
                f"SET @_stmt = {sql_arg}; PREPARE _dyn FROM @_stmt; "
                f"EXECUTE _dyn; DEALLOCATE PREPARE _dyn;{note}"
            )

        # Case 3: a bare variable or string literal is genuine dynamic SQL.
        if stripped.startswith(("@", "v_", "'", "(", "N'")):
            if params:
                using = ", ".join(params)
                return (
                    f"SET @_stmt = {expr}; PREPARE _dyn FROM @_stmt; "
                    f"EXECUTE _dyn USING {using}; DEALLOCATE PREPARE _dyn;"
                )
            return (
                f"SET @_stmt = {expr}; PREPARE _dyn FROM @_stmt; "
                f"EXECUTE _dyn; DEALLOCATE PREPARE _dyn;"
            )

        # Case 2: a named stored-procedure call. MySQL invokes procedures with
        # CALL name(args). T-SQL's trailing OUTPUT keyword on an argument has
        # no inline equivalent and is dropped (the @var is already passed by
        # reference for an OUT parameter).
        m = re.match(r"(?i)^([A-Za-z_][\w]*)\s*(.*)$", stripped)
        if m:
            proc_name = m.group(1)
            arg_text = m.group(2).strip()
            args = self._split_exec_args(arg_text)
            joined = ", ".join(args)
            return f"CALL {proc_name}({joined});"

        # Fallback: keep the dynamic workflow rather than dropping the call.
        return (
            f"SET @_stmt = {expr}; PREPARE _dyn FROM @_stmt; "
            f"EXECUTE _dyn; DEALLOCATE PREPARE _dyn;"
        )

    @staticmethod
    def _first_arg(text: str) -> str:
        """Return the first top-level comma-separated argument of ``text``."""
        depth = 0
        in_str = False
        for i, ch in enumerate(text):
            if ch == "'":
                in_str = not in_str
            elif not in_str:
                if ch in "([":
                    depth += 1
                elif ch in ")]":
                    depth -= 1
                elif ch == "," and depth == 0:
                    return text[:i].strip()
        return text.strip()

    @staticmethod
    def _split_exec_args(text: str) -> list[str]:
        """Split a procedure-call argument list on top-level commas.

        Drops a trailing ``OUTPUT``/``OUT`` keyword on any argument (MySQL has
        no inline OUTPUT marker) and skips empty results.
        """
        if not text:
            return []
        args: list[str] = []
        depth = 0
        in_str = False
        start = 0
        for i, ch in enumerate(text):
            if ch == "'":
                in_str = not in_str
            elif not in_str:
                if ch in "([":
                    depth += 1
                elif ch in ")]":
                    depth -= 1
                elif ch == "," and depth == 0:
                    args.append(text[start:i])
                    start = i + 1
        args.append(text[start:])
        cleaned: list[str] = []
        for a in args:
            a = re.sub(r"(?i)\s+(?:OUTPUT|OUT)\s*$", "", a.strip())
            if a:
                cleaned.append(a)
        return cleaned

    def _emit_print(self, node: PrintStatement) -> str:
        expr = self._emit_node(node.expression)
        if self._dialect == "tsql":
            return f"PRINT {expr};"
        elif self._dialect == "oracle":
            return f"DBMS_OUTPUT.PUT_LINE({expr});"
        elif self._dialect == "postgresql":
            return f"RAISE NOTICE '%', {expr};"
        return f"SELECT {expr};"

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        if self._dialect == "tsql":
            return f"RAISERROR({msg}, 16, 1);"
        elif self._dialect == "oracle":
            first, _ = self._split_raise_args(msg)
            return f"RAISE_APPLICATION_ERROR(-20001, {first});"
        elif self._dialect == "postgresql":
            first, _ = self._split_raise_args(msg)
            return f"RAISE EXCEPTION '%', {first};"
        # MySQL SIGNAL requires MESSAGE_TEXT to be a string and the error number
        # in MYSQL_ERRNO; the raw T-SQL argument tuple "(msg_or_id, severity,
        # state)" is invalid there. Split the first argument from the rest.
        first, rest = self._split_raise_args(msg)
        if first.startswith("'") or first.startswith('"'):
            # A literal/expression message text.
            sig = f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = {first}"
        else:
            # A numeric message id (or a variable) — MySQL can't resolve a
            # message-id to text, so use it as the error number and document it.
            sig = (
                f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = "
                f"'Application error', MYSQL_ERRNO = {first}"
            )
        comment = ""
        if rest:
            comment = (
                f"  -- UNIQUE: original RAISERROR/THROW severity/state args "
                f"dropped: {rest}"
            )
        return f"{sig};{comment}"

    @staticmethod
    def _split_raise_args(msg: str) -> tuple[str, str]:
        """Split a RAISERROR/THROW argument blob into (first_arg, rest).

        Handles an optional wrapping paren and respects nested parens and
        quotes so commas inside a string/expression don't split it.
        """
        s = msg.strip()
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1].strip()
        depth = 0
        in_str = False
        quote = ""
        for i, ch in enumerate(s):
            if in_str:
                if ch == quote:
                    in_str = False
                continue
            if ch in ("'", '"'):
                in_str = True
                quote = ch
            elif ch in ("(", "["):
                depth += 1
            elif ch in (")", "]"):
                depth -= 1
            elif ch == "," and depth == 0:
                return s[:i].strip(), s[i + 1 :].strip()
        return s, ""

    def _emit_return(self, node: ReturnStatement) -> str:
        # In a MySQL procedure, RETURN is illegal whether or not it has a value
        # (a T-SQL procedure RETURN <code> has no MySQL equivalent). Translate
        # to LEAVE of the labeled procedure block; document a discarded value.
        if (
            self._dialect == "mysql"
            and not self._in_mysql_function
            and self._proc_leave_label
        ):
            if node.value:
                val = self._emit_node(node.value)
                return (
                    f"LEAVE {self._proc_leave_label};  "
                    f"-- UNIQUE: discarded procedure RETURN value ({val})"
                )
            return f"LEAVE {self._proc_leave_label};"
        # A PostgreSQL procedure cannot RETURN a value; emit a bare RETURN and
        # document the discarded code (a T-SQL RETURN <code> has no PG meaning).
        if self._dialect == "postgresql" and self._in_pg_procedure and node.value:
            val = self._emit_node(node.value)
            return f"RETURN;  -- UNIQUE: discarded procedure RETURN value ({val})"
        if node.value:
            val = self._emit_node(node.value)
            return f"RETURN {val};"
        return "RETURN;"

    def _emit_cursor_op(self, node: CursorOperation) -> str:
        op = node.operation.upper()
        if op == "OPEN":
            if node.query:
                query_str = self._emit_node(node.query)
                if self._dialect == "tsql":
                    return f"OPEN {node.cursor_name};"
                return f"OPEN {node.cursor_name} FOR\n{query_str};"
            return f"OPEN {node.cursor_name};"
        elif op == "FETCH":
            into_str = ", ".join(node.into_vars)
            if self._dialect == "tsql":
                return f"FETCH NEXT FROM {node.cursor_name} INTO {into_str};"
            return f"FETCH {node.cursor_name} INTO {into_str};"
        elif op == "CLOSE":
            return f"CLOSE {node.cursor_name};"
        elif op == "DEALLOCATE":
            if self._dialect == "tsql":
                return f"DEALLOCATE {node.cursor_name};"
            return f"-- DEALLOCATE not needed in {self._dialect}"
        return f"{op} {node.cursor_name};"

    def _emit_exit(self, node: ExitStatement) -> str:
        cond = self._emit_node(node.condition) if node.condition else ""
        # Cursor %NOTFOUND / %FOUND have dialect-specific equivalents.
        cond = self._translate_cursor_attrs(cond)

        if self._dialect == "tsql":
            # T-SQL has no EXIT WHEN; use IF <cond> BREAK.
            if cond:
                return f"IF {cond} BREAK;"
            return "BREAK;"
        if self._dialect == "mysql":
            # MySQL uses LEAVE with a loop label; emit a guarded LEAVE.
            if cond:
                return f"IF {cond} THEN LEAVE loop_lbl; END IF;"
            return "LEAVE loop_lbl;"
        # Oracle / PostgreSQL
        if cond:
            return f"EXIT WHEN {cond};"
        return "EXIT;"

    def _translate_cursor_attrs(self, expr: str) -> str:
        """Translate Oracle cursor attributes to the target dialect."""
        if not expr:
            return expr

        if self._dialect == "tsql":
            # cur%NOTFOUND -> @@FETCH_STATUS <> 0 ; cur%FOUND -> = 0
            expr = re.sub(
                r"\w+\s*%\s*NOTFOUND", "@@FETCH_STATUS <> 0", expr, flags=re.I
            )
            expr = re.sub(r"\w+\s*%\s*FOUND", "@@FETCH_STATUS = 0", expr, flags=re.I)
        elif self._dialect == "postgresql":
            expr = re.sub(r"\w+\s*%\s*NOTFOUND", "NOT FOUND", expr, flags=re.I)
            expr = re.sub(r"\w+\s*%\s*FOUND", "FOUND", expr, flags=re.I)
        elif self._dialect == "mysql":
            # MySQL signals end-of-cursor via a NOT FOUND handler; flag it.
            expr = re.sub(
                r"\w+\s*%\s*NOTFOUND",
                "done /* set by CONTINUE HANDLER FOR NOT FOUND */",
                expr,
                flags=re.I,
            )
        return expr
        return "EXIT;"

    def _emit_continue(self, node: ContinueStatement) -> str:
        if self._dialect == "tsql":
            return "CONTINUE;"
        if node.condition:
            cond = self._emit_node(node.condition)
            return f"CONTINUE WHEN {cond};"
        return "CONTINUE;"

    def _emit_null(self, _node: NullStatement) -> str:
        if self._dialect == "tsql":
            return "-- NULL (no-op)"
        return "NULL;"

    def _emit_comment(self, node: CommentStatement) -> str:
        """Emit a preserved source comment verbatim.

        Line comments were already normalized to one space after ``--`` when
        captured; block comments are emitted exactly as written. Comments carry
        no statement terminator.
        """
        return node.text

    def _emit_embedded_dml(self, node: EmbeddedDML) -> str:
        sql = node.sql.rstrip(";").strip()
        return f"{sql};"

    def _emit_select_into(self, node: SelectIntoStatement) -> str:
        """Emit SELECT INTO in the target dialect's syntax.

        T-SQL:    SELECT @v1 = col1, @v2 = col2 FROM ...
        Oracle/PG: SELECT col1, col2 INTO v1, v2 FROM ...
        """
        select_list = ""
        if node.columns:
            first = node.columns[0]
            select_list = first.sql if isinstance(first, RawSQL) else ""
        rest = node.rest_sql.rstrip(";").strip()

        if self._dialect == "tsql":
            cols = [c.strip() for c in select_list.split(",")]
            targets = list(node.into_vars)
            pairs = []
            for i, var in enumerate(targets):
                col = cols[i] if i < len(cols) else (cols[-1] if cols else "")
                pairs.append(f"{var} = {col}")
            assignments = ", ".join(pairs)
            return f"SELECT {assignments} {rest};"
        else:
            into_clause = ", ".join(node.into_vars)
            return f"SELECT {select_list} INTO {into_clause} {rest};"

    def _emit_raw_sql(self, node: RawSQL) -> str:
        return node.sql

    def _emit_literal(self, node: Literal) -> str:
        if node.value is None:
            return "NULL"
        if node.dtype == "string":
            return f"'{node.value}'"
        return str(node.value)
