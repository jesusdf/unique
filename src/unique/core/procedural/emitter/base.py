# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — base class.

Holds the engine-agnostic emission logic and the default (T-SQL-leaning)
behavior. Per-engine specifics live in sibling modules ({tsql,oracle,
postgresql,mysql}.py), each overriding only what differs. The factory in this
module dispatches ``ProceduralEmitter(dialect)`` to the right subclass via a
registry the engine modules populate on import (see ``__init__``).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import fields as dataclass_fields
from dataclasses import replace

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AnonymousBlock,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CallStatement,
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
    ForeachStatement,
    ForLoopStatement,
    GetDiagnosticsStatement,
    HandlerDeclaration,
    IfStatement,
    LastIdentityCapture,
    Literal,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    PerformStatement,
    PragmaDeclaration,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SelectIntoStatement,
    SetVariableStatement,
    StatementList,
    TransactionAction,
    TransactionStatement,
    TryCatchBlock,
    WaitForStatement,
    WhileStatement,
)

logger = logging.getLogger(__name__)

#: A SQL-only operator that Oracle rejects in a *procedural* expression — a scalar
#: subquery (PLS-00405) or CAST (PLS-00103). An assignment/declaration whose value
#: contains one must be evaluated in SQL context (``SELECT … INTO v FROM DUAL``).
_SQL_ONLY_IN_PLSQL = re.compile(r"(?i)\(\s*SELECT\b|\bCAST\s*\(")

#: A guard idiom: ``FOR <var> IN (SELECT … FROM DUAL [WHERE <cond>]) LOOP … END``
#: runs its body 0 or 1 times, gating on <cond>. On engines whose IF takes a SQL
#: condition it round-trips to ``IF <cond> …`` rather than a scanned cursor. This
#: is exactly the shape Unique emits for an idempotent guard, so it round-trips.
_DUAL_GUARD_RE = re.compile(
    r"(?is)^SELECT\b.+?\bFROM\s+DUAL\b\s*(?:WHERE\s+(?P<cond>.+))?$"
)


def _strip_wrapping_parens(s: str) -> str:
    """Drop one balanced pair of parentheses that wraps the whole string."""
    s = s.strip()
    while len(s) >= 2 and s.startswith("(") and s.endswith(")"):
        depth = 0
        wraps_all = False
        for pos, ch in enumerate(s):
            depth += (ch == "(") - (ch == ")")
            if depth == 0:
                # A wrapper only if the opening "(" closes at the very end.
                wraps_all = pos == len(s) - 1
                break
        if not wraps_all:
            break
        s = s[1:-1].strip()
    return s


def _dual_guard_condition(cursor_str: str) -> str | None:
    """The WHERE condition of a ``SELECT … FROM DUAL [WHERE <cond>]`` guard cursor
    (``1 = 1`` when there is no WHERE), or ``None`` when *cursor_str* is not that
    shape (so the caller keeps a real cursor loop)."""
    m = _DUAL_GUARD_RE.match(_strip_wrapping_parens(cursor_str))
    if not m:
        return None
    cond = (m.group("cond") or "").strip() or "1 = 1"
    # A FROM-less subquery in the condition carries an Oracle-only ``FROM DUAL``
    # (the forward pass adds it so ``EXISTS (SELECT NULL)`` is valid PL/SQL). This
    # path only feeds engines whose ``IF`` takes a SQL condition (T-SQL/PostgreSQL/
    # MySQL) — none needs DUAL there, and T-SQL/PostgreSQL have no such table — so
    # drop it, keeping the round-trip faithful (``EXISTS (SELECT NULL)``).
    return re.sub(r"(?i)\s+FROM\s+DUAL\b", "", cond)


def _for_var_referenced(variable: str, body_lines: list[str]) -> bool:
    """Whether the loop variable is used in the emitted body — if so the loop
    binds real row data and must stay a cursor loop, not collapse to an IF."""
    pat = re.compile(rf"\b{re.escape(variable)}\b")
    return any(pat.search(line) for line in body_lines)


#: Populated by the per-engine modules via ``register_emitter``.
_EMITTER_REGISTRY: dict[str, type[ProceduralEmitter]] = {}


def register_emitter(name: str, cls: type[ProceduralEmitter]) -> None:
    """Register a per-engine emitter subclass under its dialect name."""
    _EMITTER_REGISTRY[name] = cls


def _strip_outer_parens(text: str) -> str:
    """Remove balanced outer parentheses wrapping the whole text."""
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        balanced = True
        for i, ch in enumerate(text):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and i < len(text) - 1:
                balanced = False
                break
        if not balanced:
            break
        text = text[1:-1].strip()
    return text


def _select_list_columns(select_text: str) -> list[str] | None:
    """Column/alias names of a SELECT's top-level select list, or None.

    Used to derive a cursor FOR-loop's FETCH INTO variables. Returns None
    when any item has no derivable name (``*``, an expression without an
    alias) or names collide — the caller then keeps the documented scaffold.
    """
    from unique.core.sql_split import split_top_level_commas

    text = select_text.strip()
    # Unwrap outer parens (the inline `FOR r IN (SELECT …)` form).
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        balanced = True
        for i, ch in enumerate(text):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and i < len(text) - 1:
                balanced = False
                break
        if not balanced:
            break
        text = text[1:-1].strip()
    m = re.match(r"(?is)^\s*SELECT\s+(?:DISTINCT\s+)?(.*)$", text)
    if not m:
        return None
    rest = m.group(1)
    # Find the top-level FROM (outside parens/strings).
    depth = 0
    in_string = False
    from_at = -1
    i = 0
    while i < len(rest):
        ch = rest[i]
        if in_string:
            if ch == "'":
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif depth == 0 and rest[i : i + 4].upper() == "FROM":
            before_ok = i == 0 or not (rest[i - 1].isalnum() or rest[i - 1] == "_")
            after = rest[i + 4 : i + 5]
            if before_ok and (not after or not (after.isalnum() or after == "_")):
                from_at = i
                break
        i += 1
    select_list = rest[:from_at] if from_at >= 0 else rest
    names: list[str] = []
    for item in split_top_level_commas(select_list):
        item = item.strip()
        if not item or re.fullmatch(r"(?:[\w\[\]\"`]+\.)?\*", item):
            # A bare star (or t.*) has no derivable column list; an
            # aliased expression that merely CONTAINS one (COUNT(*) TOTAL)
            # resolves through its alias below.
            return None
        plain = re.fullmatch(r"[\w.\[\]\"`]+", item)
        if plain:
            name = item.split(".")[-1].strip('[]"`')
        else:
            alias = re.search(r"(?is)\s(?:AS\s+)?([A-Za-z_]\w*)\s*$", item)
            if not alias:
                return None
            name = alias.group(1)
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            return None
        names.append(name.lower())
    if not names or len(set(names)) != len(names):
        return None
    return names


class ProceduralEmitter:
    """Emits procedural SQL code for a target dialect.

    Generates syntactically correct procedural code from IR AST nodes,
    using the conventions and syntax of the target dialect.

    This base class holds the engine-agnostic emission logic and the default
    (T-SQL-leaning) behavior. Per-engine specifics live in subclasses
    (`TSqlEmitter`, `OracleEmitter`, `PostgresEmitter`, `MySqlEmitter`), which
    override only the methods that differ. Instantiating
    ``ProceduralEmitter(dialect)`` returns the right subclass via ``__new__``,
    so existing call sites need no change.
    """

    #: Set on each subclass; maps to the dialect string it handles.
    dialect_name: str | None = None

    def __new__(cls, dialect: str) -> ProceduralEmitter:
        # When constructed as the base class, dispatch to the engine subclass.
        if cls is ProceduralEmitter:
            subclass = _EMITTER_REGISTRY.get(dialect)
            if subclass is not None:
                return object.__new__(subclass)
        return object.__new__(cls)

    def __init__(self, dialect: str) -> None:
        self._dialect = dialect
        self._indent_level = 0
        self._indent_str = "    "
        #: Declared-cursor queries by lowercase name, recorded as their
        #: declarations emit, so a FOR loop over a named cursor can derive
        #: its FETCH INTO variable list (T-SQL and MySQL expansions).
        self._cursor_queries: dict[str, str] = {}
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
            PragmaDeclaration: self._emit_pragma,
            SetVariableStatement: self._emit_set_variable,
            AssignmentStatement: self._emit_assignment,
            IfStatement: self._emit_if,
            WhileStatement: self._emit_while,
            ForLoopStatement: self._emit_for_loop,
            ForeachStatement: self._emit_foreach,
            LoopStatement: self._emit_loop,
            BeginEndBlock: self._emit_begin_end,
            StatementList: self._emit_statement_list,
            AnonymousBlock: self._emit_anonymous_block,
            TryCatchBlock: self._emit_try_catch,
            HandlerDeclaration: self._emit_handler_declaration,
            LastIdentityCapture: self._emit_last_identity_capture,
            ExceptionBlock: self._emit_exception_block,
            ExecuteStatement: self._emit_execute,
            CallStatement: self._emit_call,
            GetDiagnosticsStatement: self._emit_get_diagnostics,
            PerformStatement: self._emit_perform,
            PrintStatement: self._emit_print,
            RaiseErrorStatement: self._emit_raise_error,
            ReturnStatement: self._emit_return,
            CursorDeclaration: self._emit_cursor_decl,
            CursorOperation: self._emit_cursor_op,
            ExitStatement: self._emit_exit,
            ContinueStatement: self._emit_continue,
            NullStatement: self._emit_null,
            CommentStatement: self._emit_comment,
            TransactionStatement: self._emit_transaction,
            WaitForStatement: self._emit_waitfor,
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

    #: Mapped types that take no length/precision modifier: a source length
    #: carried through the map (VARBINARY(MAX) -> BYTEA) is invalid there.
    _PARAMLESS_TYPES = frozenset(
        {
            "BYTEA",
            "TEXT",
            "LONGTEXT",
            "MEDIUMTEXT",
            "CLOB",
            "NCLOB",
            "BLOB",
            "LONGBLOB",
            "XML",
            "XMLTYPE",
            "JSON",
            "JSONB",
            "UUID",
            "SYS_REFCURSOR",
            "REFCURSOR",
            "BOOLEAN",
        }
    )

    def _emit_data_type(self, dt: DataType) -> str:
        """Emit a data type, appending a /* UNIQUE */ marker when the original
        source type was preserved for documentation/round-tripping."""
        if dt.params and dt.name.upper() not in self._PARAMLESS_TYPES:
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
        """Emit a parameter list. The per-parameter formatting differs per
        engine and is delegated to ``_emit_param``; the base provides the
        default ``_keep_default`` policy (always keep)."""
        parts = [
            f"{self._indent()}{self._emit_param(p, idx, params, is_function)}"
            for idx, p in enumerate(params)
        ]
        return ",\n".join(parts)

    def _keep_default(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
    ) -> bool:
        """Whether a parameter's DEFAULT should be emitted. Default: keep it if
        present. PostgreSQL overrides (OUT/INOUT and pre-OUT params drop it)."""
        return bool(p.default)

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        """Format a single parameter. Default is the PL/SQL form
        ``name [DIR ]type[ DEFAULT v]``; T-SQL and MySQL override."""
        dt = self._emit_data_type(p.data_type)
        default_str = ""
        if self._keep_default(p, idx, params) and p.default:
            default_str = f" DEFAULT {self._emit_node(p.default)}"
        direction_str = f"{p.direction} " if p.direction != "IN" else ""
        variadic_str = "VARIADIC " if p.variadic else ""
        return f"{variadic_str}{p.name} {direction_str}{dt}{default_str}".strip()

    # ---------------------------------------------------------------
    # Procedure / Function / Trigger
    # ---------------------------------------------------------------

    def _qualified_name(self, schema: str | None, name: str) -> str:
        """Build a schema-qualified object name.

        T-SQL's default ``dbo`` schema has no counterpart in the other engines:
        MySQL has no schema layer (a schema is a database), and in Oracle and
        PostgreSQL ``dbo`` names a schema that doesn't exist. Whether a schema
        qualifier survives is decided per engine by ``_keep_schema``.
        """
        if not schema:
            return name
        if self._keep_schema(schema):
            return f"{schema}.{name}"
        return name

    def _keep_schema(self, schema: str) -> bool:
        """Whether to keep a schema qualifier on an object name. Default (T-SQL)
        keeps any schema; Oracle/PostgreSQL drop ``dbo``; MySQL drops all."""
        return True

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

        def hoist_declare(decl: ASTNode) -> None:
            # A mid-body declaration's initializer must stay an assignment at
            # its original position: hoisting it to the section would run it
            # BEFORE the statements that precede it in the source (e.g. a
            # SUBSTRING over a variable a loop advances first) — silently
            # wrong values.
            if (
                body_stmts
                and isinstance(decl, DeclareStatement)
                and decl.default is not None
            ):
                declarations.append(replace(decl, default=None))
                body_stmts.append(
                    AssignmentStatement(target=decl.name, value=decl.default)
                )
            else:
                declarations.append(decl)

        for stmt in body:
            if isinstance(stmt, CommentStatement) and stmt.header:
                # A header comment re-homed from before the CREATE (SQL Server
                # keeps those in the stored module; Oracle/PostgreSQL/MySQL store
                # a routine from CREATE on) belongs at the head of the declaration
                # section, right after the CREATE — not below the declarations
                # after BEGIN. Only these flagged comments are hoisted; an ordinary
                # body comment (e.g. a UNIQUE restore note) stays in place.
                declarations.append(stmt)
                continue
            if isinstance(stmt, (DeclareStatement, CursorDeclaration)):
                hoist_declare(stmt)
            elif (
                isinstance(stmt, StatementList)
                and stmt.statements
                and all(
                    isinstance(s, (DeclareStatement, CursorDeclaration))
                    for s in stmt.statements
                )
            ):
                for sub in stmt.statements:
                    hoist_declare(sub)
            else:
                body_stmts.append(stmt)

        # Declarations NESTED in control-flow bodies (a DECLARE inside an IF)
        # are invalid outside T-SQL: hoist the bare declaration to the section
        # and leave the initializer as an assignment at its original,
        # conditional position (audit C1 residue, 2026-07-10).
        seen = {getattr(d, "name", None) for d in declarations}

        def pull_nested(node: ASTNode) -> ASTNode | None:
            if isinstance(node, DeclareStatement):
                if node.name not in seen:
                    seen.add(node.name)
                    declarations.append(replace(node, default=None))
                if node.default is not None:
                    return AssignmentStatement(target=node.name, value=node.default)
                return None
            if isinstance(node, CursorDeclaration):
                if node.name not in seen:
                    seen.add(node.name)
                    declarations.append(node)
                return None
            changes: dict[str, object] = {}
            for f in dataclass_fields(node):
                val = getattr(node, f.name)
                if (
                    isinstance(val, tuple)
                    and val
                    and all(isinstance(x, ASTNode) for x in val)
                ):
                    new_items = tuple(
                        y for x in val if (y := pull_nested(x)) is not None
                    )
                    if new_items != val:
                        if not new_items:
                            # A body that held only declarations must not
                            # collapse to an empty (invalid) block.
                            new_items = (NullStatement(),)
                        changes[f.name] = new_items
            if changes:
                return replace(node, **changes)  # type: ignore[arg-type]
            return node

        body_stmts = [y for x in body_stmts if (y := pull_nested(x)) is not None]
        # A cursor-variable binding (``SET @c = CURSOR ... FOR q``) merged into
        # a declaration supersedes the query-less ``DECLARE @c CURSOR`` that
        # preceded it (MySQL path: cursors have no variable form there).
        bound = {
            d.name
            for d in declarations
            if isinstance(d, CursorDeclaration) and d.query is not None
        }
        if bound:
            declarations = [
                d
                for d in declarations
                if not (
                    isinstance(d, CursorDeclaration)
                    and d.query is None
                    and d.name in bound
                )
            ]
        return declarations, body_stmts

    def _emit_procedure(self, node: CreateProcedureStatement) -> str:
        name = self._qualified_name(node.schema, node.name)
        header = self._procedure_header(name, node.or_replace)

        self._indent_level += 1
        params_str = self._emit_params(node.parameters)
        self._indent_level -= 1

        if params_str:
            header += f"\n(\n{params_str}\n)"
        elif self._wants_empty_parens():
            # Some engines require the parameter parentheses even when empty
            # (CREATE PROCEDURE p() ...); omitting them is a syntax error.
            header += "()"

        # Separate declarations from body statements
        declarations, body_stmts = self._split_declarations(node.body)
        return self._emit_procedure_body(header, declarations, body_stmts)

    def _procedure_header(self, name: str, or_replace: bool) -> str:
        """The ``CREATE … PROCEDURE <name>`` header line. Overridden by engines
        that support ``CREATE OR REPLACE``."""
        return f"CREATE PROCEDURE {name}"

    def _wants_empty_parens(self) -> bool:
        """Whether a parameterless routine must still emit ``()``. Overridden by
        engines that require it (MySQL, PostgreSQL)."""
        return False

    def _wants_empty_parens_function(self) -> bool:
        """Like ``_wants_empty_parens`` but for functions, where T-SQL also
        requires the parentheses (CREATE FUNCTION f() … — error 102 without
        them) although its procedures stay paren-less."""
        return self._wants_empty_parens()

    def _emit_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        """Emit the procedure body. Default is the T-SQL shape; each engine
        subclass overrides this with its own block structure."""
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
        decl_keyword: str = "IS",
        no_decl_keyword: str = "AS",
    ) -> str:
        # A procedure's declare section opens with IS (else AS); a trigger's opens
        # with DECLARE and is omitted entirely when there are no declarations.
        lines = [f"{header}"]
        # A declaration initialised from a subquery (`v TYPE := (SELECT …)`) is
        # invalid in the Oracle declare section (PLS-00405); declare the variable
        # bare and run the SELECT … INTO at the top of the body instead.
        hoisted: list[str] = []
        if declarations:
            lines.append(decl_keyword)
            self._indent_level = 1
            for decl in declarations:
                split = self._oracle_split_subquery_default(decl)
                if split is not None:
                    decl_line, select_into = split
                    lines.append(f"{self._indent()}{decl_line}")
                    hoisted.append(select_into)
                else:
                    lines.append(f"{self._indent()}{self._emit_node(decl)}")
            self._indent_level = 0
        elif no_decl_keyword:
            lines.append(no_decl_keyword)

        lines.append("BEGIN")
        self._indent_level = 1
        texts = [
            t
            for t in (*hoisted, *(self._emit_node(stmt) for stmt in body_stmts))
            # A bare ``;`` (an empty source statement) is PLS-00103.
            if t.strip() != ";"
        ]

        def executable(text: str) -> bool:
            return any(
                ln.strip() and not ln.lstrip().startswith(("--", "/*", "*"))
                for ln in text.split("\n")
            )

        if not any(executable(t) for t in texts):
            # PL/SQL requires at least one statement in a block — an
            # empty MySQL body (``BEGIN END``, wave 177) or one whose
            # only statement degraded to a comment carrier (wave 183)
            # was PLS-00103.
            texts.append("NULL;")
        for text in texts:
            for line in text.split("\n"):
                lines.append(f"{self._indent()}{line}" if line.strip() else "")
        self._indent_level = 0
        lines.append("END;")
        return "\n".join(lines)

    def _oracle_split_subquery_default(self, decl: ASTNode) -> tuple[str, str] | None:
        """If *decl* is a variable initialised from a SQL-only expression (a
        subquery or CAST), return ``(bare_declaration, "SELECT … INTO v FROM
        DUAL;")`` — such an expression is invalid in the declare section; else
        ``None``."""
        if not isinstance(decl, DeclareStatement) or not decl.default:
            return None
        val = self._emit_node(decl.default)
        if not _SQL_ONLY_IN_PLSQL.search(val):
            return None
        dt = self._emit_data_type(decl.data_type)
        return (
            f"{self._declare_prefix()}{decl.name} {dt};",
            f"SELECT {val.strip()} INTO {decl.name} FROM DUAL;",
        )

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
        value). In a MySQL procedure even ``RETURN <value>`` is invalid.

        Walks every dataclass field holding nodes — an attribute-name list
        missed ``BeginEndBlock.statements``, so a RETURN inside a nested
        block/handler shipped as a bare ``RETURN;`` (a 1064 parse error)."""
        for s in stmts:
            if isinstance(s, ReturnStatement):
                return True
            for f in dataclass_fields(s):
                child = getattr(s, f.name, None)
                if isinstance(child, tuple):
                    nodes = [c for c in child if isinstance(c, ASTNode)]
                    if nodes and self._body_has_any_return(nodes):
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
            and not self._supports_table_valued_function()
        ):
            return self._emit_table_valued_function(node)
        # A PostgreSQL trigger function ('RETURNS TRIGGER') is the body of a
        # trigger, not a callable function; engines without trigger functions
        # (MySQL/Oracle/T-SQL) cannot create it, so document it rather than emit
        # an invalid ``RETURNS TRIGGER``.
        if (
            node.return_type is not None
            and node.return_type.name.upper() == "TRIGGER"
            and not self._supports_trigger_function()
        ):
            return self._emit_trigger_function_unsupported(node)
        return self._emit_function_impl(node)

    def _supports_table_valued_function(self) -> bool:
        """Whether the engine has a native table-valued function. Only T-SQL
        does; the others document and comment it out."""
        return False

    def _supports_trigger_function(self) -> bool:
        """Whether the engine has PostgreSQL-style trigger functions (a
        ``RETURNS TRIGGER`` routine holding a trigger body). Only PostgreSQL
        does; the others document and comment it out."""
        return False

    def _emit_trigger_function_unsupported(self, node: CreateFunctionStatement) -> str:
        note = (
            "-- UNIQUE: PostgreSQL trigger function ('RETURNS TRIGGER') has no "
            f"{self.dialect_name} equivalent (no trigger functions; the body "
            "belongs to a CREATE TRIGGER). The non-portable translation is "
            "commented out below for review:\n"
        )
        body = self._emit_function_impl(node)
        commented = "\n".join(
            f"-- {line}" if line.strip() else "--" for line in body.split("\n")
        )
        return note + commented

    def _tvf_unsupported_note(self) -> str:
        """Per-engine explanation of why a table-valued function can't be
        emitted natively. Overridden by each non-T-SQL engine."""
        return "no direct equivalent on this engine"

    def _emit_table_valued_function(self, node: CreateFunctionStatement) -> str:
        note = (
            f"-- UNIQUE: inline table-valued function ('RETURNS TABLE') has no "
            f"direct equivalent. {self._tvf_unsupported_note()}.\n"
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
        header = self._function_header(name, node.or_replace)

        self._indent_level += 1
        params_str = self._emit_params(node.parameters, is_function=True)
        self._indent_level -= 1

        if params_str:
            header += f"\n(\n{params_str}\n)"
        elif self._wants_empty_parens_function():
            # MySQL, PostgreSQL and T-SQL require the parameter parentheses
            # on a function even when empty. Oracle allows omitting them.
            header += "()"

        header += self._returns_clause(ret_type)

        declarations, body_stmts = self._split_declarations(node.body)
        return self._emit_function_body(header, declarations, body_stmts)

    def _function_header(self, name: str, or_replace: bool) -> str:
        """The ``CREATE … FUNCTION <name>`` header. Default is plain CREATE
        (T-SQL, MySQL); Oracle/PostgreSQL override to add OR REPLACE."""
        return f"CREATE FUNCTION {name}"

    def _returns_clause(self, ret_type: str) -> str:
        """The return-type clause appended to a function header. Default
        ``\\nRETURNS <type>`` (T-SQL/PostgreSQL); Oracle and MySQL override."""
        return f"\nRETURNS {ret_type}"

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        """Emit a function body. Default is the T-SQL procedure-body shape;
        engine subclasses override (PG/MySQL pass is_function=True)."""
        return self._emit_procedure_body(header, declarations, body_stmts)

    def _emit_trigger(self, node: CreateTriggerStatement) -> str:
        """Emit a CREATE TRIGGER. The base covers the engines that share a
        ``header → body → END`` shape (T-SQL, Oracle, MySQL); PostgreSQL, whose
        trigger body lives in a separate function, overrides this entirely.
        """
        if node.compound:
            return self._emit_compound_trigger_unsupported(node)
        # A PostgreSQL trigger that delegates its body to a trigger function
        # (``EXECUTE FUNCTION fn()``) has no inline body to emit here, and these
        # engines have no statement-level transition-table triggers. Document
        # the binding rather than emit an empty/invalid trigger.
        if node.execute_function:
            return self._emit_delegating_trigger_unsupported(node)
        name = self._qualified_name(node.schema, node.name)
        events = self._join_trigger_events(node.events)
        if node.update_of:
            events = self._events_with_update_of(events, node.update_of)
        timing = node.timing

        note, timing = self._adjust_trigger_timing(timing)
        lines = self._trigger_header(name, node, events, timing)

        self._indent_level = 1
        lines.extend(self._emit_indented_stmts(node.body))
        self._indent_level = 0
        lines.append(self._trigger_end())
        return self._degrade_pseudo_table_trigger(note + "\n".join(lines))

    #: Left by the transformer inside a trigger whose body reads the T-SQL
    #: inserted/deleted pseudo-tables in a set-based way the target cannot
    #: express (see _rewrite_trigger_pseudotables).
    _PSEUDO_TABLE_CARRIER_MARKER = "set-based inserted/deleted"

    def _degrade_pseudo_table_trigger(self, text: str) -> str:
        """A trigger carrying the set-based pseudo-table note is not runnable
        (its cursor/DML source was replaced by the documentation carrier):
        shipping it partially executable would run a half-empty body per row.
        Preserve the WHOLE trigger commented out for a manual rewrite."""
        if self._PSEUDO_TABLE_CARRIER_MARKER not in text:
            return text
        note = (
            "-- UNIQUE: trigger reads the T-SQL inserted/deleted pseudo-tables "
            f"in a set-based way {self.dialect_name} cannot express; the "
            "translation is preserved commented out for a manual rewrite:\n"
        )
        commented = "\n".join(
            f"-- {line}" if line.strip() else "--" for line in text.split("\n")
        )
        return note + commented

    def _emit_compound_trigger_unsupported(self, node: CreateTriggerStatement) -> str:
        """Document an Oracle COMPOUND TRIGGER, which has no mechanical
        cross-engine equivalent (it accumulates affected rows in a PL/SQL
        collection and re-aggregates in AFTER STATEMENT)."""
        events = self._join_trigger_events(node.events)
        return (
            f"-- UNIQUE: Oracle COMPOUND TRIGGER {node.name} ({node.timing} "
            f"{events} ON {node.table}) has no automatic {self.dialect_name} "
            "equivalent — it collects affected rows in a PL/SQL collection and "
            "re-aggregates in AFTER STATEMENT. Rewrite manually (PostgreSQL: a "
            "statement-level trigger with REFERENCING NEW TABLE; MySQL: a "
            "row-level trigger that re-reads the table)."
        )

    def _emit_delegating_trigger_unsupported(self, node: CreateTriggerStatement) -> str:
        """Document a PostgreSQL delegating trigger (``EXECUTE FUNCTION fn()``)
        that this engine cannot express (no statement-level transition-table
        triggers). Reconstructs the binding as a ``-- UNIQUE:`` carrier; the
        transformer records the loss in ``result.warnings``."""
        events = " OR ".join(node.events) if node.events else "UPDATE"
        ref = f" REFERENCING {node.referencing}" if node.referencing else ""
        binding = (
            f"CREATE TRIGGER {node.name} {node.timing} {events} ON {node.table}"
            f"{ref} FOR EACH {node.for_each} EXECUTE FUNCTION "
            f"{node.execute_function}();"
        )
        return (
            "-- UNIQUE: PostgreSQL statement-level trigger delegating to a "
            f"trigger function has no {self.dialect_name} equivalent (no "
            "transition tables / trigger functions). Original binding:\n"
            f"-- {binding}"
        )

    def _adjust_trigger_timing(self, timing: str) -> tuple[str, str]:
        """Return (note, timing). Engines that can't honor the requested timing
        (MySQL has no INSTEAD OF) override to document and rewrite it."""
        return "", timing

    @staticmethod
    def _events_with_update_of(events: str, columns: tuple[str, ...]) -> str:
        """Attach an ``UPDATE OF c1, c2`` column list to the joined events."""
        return re.sub(
            r"(?i)\bUPDATE\b", f"UPDATE OF {', '.join(columns)}", events, count=1
        )

    def _join_trigger_events(self, events: tuple[str, ...]) -> str:
        """Join a trigger's DML events. T-SQL and MySQL use a comma list;
        Oracle overrides to ``INSERT OR UPDATE`` (a comma there is ORA-00969)."""
        return ", ".join(events) if events else "UPDATE"

    def _trigger_header(
        self,
        name: str,
        node: CreateTriggerStatement,
        events: str,
        timing: str,
    ) -> list[str]:
        """The opening lines of a trigger, up to and including ``BEGIN``.
        Default is the T-SQL form; Oracle and MySQL override."""
        return [
            f"CREATE TRIGGER {name} ON {node.table}",
            f"{node.timing} {events}",
            "AS",
            "BEGIN",
        ]

    def _trigger_end(self) -> str:
        """The closing line of a trigger body. Default ``END``; Oracle overrides
        with ``END;``."""
        return "END"

    # ---------------------------------------------------------------
    # Declarations
    # ---------------------------------------------------------------

    def _emit_declare(self, node: DeclareStatement) -> str:
        dt = self._emit_data_type(node.data_type)
        default_str = ""
        if node.default:
            val = self._emit_node(node.default)
            default_str = f" {self._declare_default_op()} {val}"
        const = self._constant_spelling() if node.constant else ""
        nn = self._not_null_spelling() if node.not_null else ""
        return f"{self._declare_prefix()}{node.name} {const}{dt}{nn}{default_str};"

    def _constant_spelling(self) -> str:
        """``CONSTANT `` on the PL/SQL-family targets (Oracle/PG). T-SQL and
        MySQL have no constant variables and override with "" — the plain
        mutable declaration is a safe relaxation for valid programs."""
        return "CONSTANT "

    def _not_null_spelling(self) -> str:
        """`` NOT NULL`` on PG/Oracle declares; T-SQL/MySQL have no such
        modifier and override with "" (same relaxation as CONSTANT)."""
        return " NOT NULL"

    def _emit_foreach(self, node: ForeachStatement) -> str:
        """plpgsql FOREACH … IN ARRAY — PG-only (its emitter overrides).
        Elsewhere arrays have no equivalent: the loop degrades to the
        documented carrier (the containing routine normally degrades
        whole before reaching here via the array-body gate)."""
        slice_str = f" SLICE {node.slice_depth}" if node.slice_depth else ""
        header = f"FOREACH {node.variable}{slice_str} IN ARRAY {node.array_expr}"
        return (
            f"-- UNIQUE: {header} LOOP … has no {self._dialect} equivalent "
            "(no array type); statement preserved as a comment:\n"
            f"-- {header} LOOP … END LOOP;"
        )

    def _emit_pragma(self, node: PragmaDeclaration) -> str:
        """A PL/SQL compiler directive. Only Oracle can execute it (its emitter
        overrides); everywhere else it is documented, never shipped executable
        (``DECLARE PRAGMA AUTONOMOUS_TRANSACTION;`` was a hard parse error)."""
        return (
            f"-- UNIQUE: PRAGMA {node.name} has no {self.dialect_name} "
            "equivalent; dropped."
        )

    def _declare_default_op(self) -> str:
        """Operator that introduces a variable's default. Default PL/SQL ``:=``;
        T-SQL (``=``) and MySQL (``DEFAULT``) override."""
        return ":="

    def _declare_prefix(self) -> str:
        """Leading keyword of a variable declaration. Default none (Oracle/PG
        DECLARE section); T-SQL and MySQL override with ``DECLARE ``."""
        return ""

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        query_str = ""
        if node.query:
            # The query may be an EmbeddedDML that emits its own trailing
            # semicolon; strip it to avoid a double ';'.
            query_str = self._emit_node(node.query).rstrip().rstrip(";")
        if not query_str:
            # A query-less cursor VARIABLE (T-SQL ``DECLARE @cur CURSOR;``):
            # PL/SQL's counterpart is a ref cursor (``CURSOR name;`` needs IS).
            return f"{node.name} SYS_REFCURSOR;"
        # Default: Oracle PL/SQL: CURSOR name[(params)] IS <select>;
        params = ""
        if node.parameters:
            rendered = ", ".join(
                f"{p.name} {self._emit_data_type(p.data_type)}" for p in node.parameters
            )
            params = f"({rendered})"
        return f"CURSOR {node.name}{params} IS {query_str};"

    # ---------------------------------------------------------------
    # Variable operations
    # ---------------------------------------------------------------

    def _emit_set_variable(self, node: SetVariableStatement) -> str:
        val = self._emit_node(node.value)
        return f"SET {node.name} = {val};"

    def _emit_assignment(self, node: AssignmentStatement) -> str:
        val = self._emit_node(node.value)
        via_select = self._assignment_via_select(node.target, val, node.value)
        if via_select is not None:
            return via_select
        return self._assignment_form(node.target, val)

    def _assignment_via_select(
        self, target: str, val: str, value_node: ASTNode | None = None
    ) -> str | None:
        """Some engines cannot assign the result of a subquery with ``:=``.
        Default: no rewrite (PostgreSQL/MySQL allow a scalar subquery in the
        assigned expression); Oracle overrides — structure-first (the value
        NODE), spelling regex only for raw text fragments."""
        return None

    def _assignment_form(self, target: str, val: str) -> str:
        """Variable assignment form. Default (Oracle/PostgreSQL) ``x := v;``;
        T-SQL and MySQL override with ``SET x = v;``."""
        return f"{target} := {val};"

    # ---------------------------------------------------------------
    # Control flow
    # ---------------------------------------------------------------

    def _emit_if(self, node: IfStatement) -> str:
        cond = self._emit_node(node.condition)
        return self._emit_if_body(cond, node.then_body, node.else_body)

    def _emit_if_body(
        self,
        cond: str,
        then_body: tuple[ASTNode, ...],
        else_body: tuple[ASTNode, ...],
    ) -> str:
        """Default (PL/SQL) IF … THEN … [ELSIF …] [ELSE …] END IF;. T-SQL
        overrides with the BEGIN/END block form."""
        lines = [f"IF {cond} THEN"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(then_body))
        self._indent_level -= 1

        if else_body:
            if len(else_body) == 1 and isinstance(else_body[0], IfStatement):
                nested = else_body[0]
                nested_cond = self._emit_node(nested.condition)
                lines.append(f"{self._elsif_keyword()} {nested_cond} THEN")
                self._indent_level += 1
                lines.extend(self._emit_indented_stmts(nested.then_body))
                self._indent_level -= 1
                if nested.else_body:
                    lines.append("ELSE")
                    self._indent_level += 1
                    lines.extend(self._emit_indented_stmts(nested.else_body))
                    self._indent_level -= 1
            else:
                lines.append("ELSE")
                self._indent_level += 1
                lines.extend(self._emit_indented_stmts(else_body))
                self._indent_level -= 1

        lines.append("END IF;")
        return "\n".join(lines)

    def _elsif_keyword(self) -> str:
        """The chained-ELSE-IF keyword: PL/SQL and plpgsql spell it ELSIF;
        MySQL overrides with ELSEIF."""
        return "ELSIF"

    def _emit_while(self, node: WhileStatement) -> str:
        """Default (PL/SQL/MySQL) ``WHILE cond LOOP … END LOOP;``. T-SQL
        overrides with the ``WHILE cond BEGIN … END`` block form."""
        cond = self._emit_node(node.condition)
        lines = [f"WHILE {cond} LOOP"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.body))
        self._indent_level -= 1
        lines.append("END LOOP;")
        return "\n".join(lines)

    def _emit_for_loop(self, node: ForLoopStatement) -> str:
        cursor_str = self._emit_node(node.cursor) if node.cursor else ""
        cursor_str = cursor_str.rstrip().rstrip(";")

        self._indent_level += 1
        body_lines = self._emit_indented_stmts(node.body)
        self._indent_level -= 1

        if node.range_start is not None and node.range_end is not None:
            return self._emit_numeric_for_loop(
                node.variable,
                self._emit_node(node.range_start).strip(),
                self._emit_node(node.range_end).strip(),
                node.reverse,
                body_lines,
            )

        # A ``FROM DUAL`` guard loop (runs 0/1 times, never binds a row) becomes an
        # IF on engines that support it — no dead cursor, and no stray FROM DUAL.
        cond = _dual_guard_condition(cursor_str)
        if cond is not None and not _for_var_referenced(node.variable, body_lines):
            guard = self._emit_guard_if(cond, body_lines)
            if guard is not None:
                return guard

        return self._emit_for_loop_body(node.variable, cursor_str, body_lines)

    def _emit_numeric_for_loop(
        self, variable: str, start: str, end: str, reverse: bool, body_lines: list[str]
    ) -> str:
        """Emit a counting ``FOR v IN [REVERSE] a..b`` loop. Default is the
        native PL/SQL / PL-pgSQL form; T-SQL and MySQL expand to WHILE."""
        rev = "REVERSE " if reverse else ""
        lines = [f"FOR {variable} IN {rev}{start}..{end} LOOP"]
        lines.extend(body_lines)
        lines.append("END LOOP;")
        return "\n".join(lines)

    def _emit_guard_if(self, cond: str, body_lines: list[str]) -> str | None:
        """Render a ``FROM DUAL`` guard FOR-loop as an ``IF``. Default returns
        ``None`` — keep the native FOR-loop (Oracle, where the FOR-loop over DUAL
        *is* how the guard is expressed). T-SQL/PostgreSQL/MySQL override."""
        return None

    def _emit_for_loop_body(
        self, variable: str, cursor_str: str, body_lines: list[str]
    ) -> str:
        """Emit a cursor FOR-loop. Default is the native PL/SQL/PL-pgSQL form;
        T-SQL and MySQL override with an explicit-cursor scaffold."""
        lines = [f"FOR {variable} IN {cursor_str} LOOP"]
        lines.extend(body_lines)
        lines.append("END LOOP;")
        return "\n".join(lines)

    def _emit_loop(self, node: LoopStatement) -> str:
        self._indent_level += 1
        body_lines = self._emit_indented_stmts(node.body)
        self._indent_level -= 1
        result = self._emit_loop_body(body_lines)
        if node.label:
            # PL/SQL and plpgsql spell loop labels ``<<label>> LOOP …
            # END LOOP label;``.
            result = f"<<{node.label}>>\n{result}"
            if result.rstrip().endswith("END LOOP;"):
                result = result.rstrip()[: -len(";")] + f" {node.label};"
        return result

    def _emit_loop_body(self, body_lines: list[str]) -> str:
        """Emit an unconditional loop. Default (Oracle/PostgreSQL) ``LOOP …
        END LOOP;``. T-SQL and MySQL override."""
        lines = ["LOOP", *body_lines, "END LOOP;"]
        return "\n".join(lines)

    def _emit_begin_end(self, node: BeginEndBlock) -> str:
        lines = ["BEGIN"]
        self._indent_level += 1
        body = self._emit_indented_stmts(node.statements)
        filler = self._empty_block_filler()
        if filler and not any(
            ln.strip() and not ln.lstrip().startswith("--") for ln in body
        ):
            # A comment-only block is a syntax error on targets that
            # require at least one statement (T-SQL 156, PLS-00103).
            body.append(f"{self._indent()}{filler}")
        lines.extend(body)
        self._indent_level -= 1
        lines.append(self._block_end())
        return "\n".join(lines)

    def _empty_block_filler(self) -> str | None:
        """No-op statement for a comment-only block; None = block may be
        empty on this target (MySQL)."""
        return None

    def _block_end(self) -> str:
        """The closing keyword of a BEGIN…END block. Default ``END;``; T-SQL
        overrides with ``END`` (no semicolon)."""
        return "END;"

    def _emit_statement_list(self, node: StatementList) -> str:
        """Emit a transparent statement sequence (no wrapper)."""
        return "\n".join(self._emit_node(stmt) for stmt in node.statements)

    def _emit_anonymous_block(self, node: AnonymousBlock) -> str:
        """Emit a top-level anonymous block.

        Default (Oracle / T-SQL style): if the block declares variables, wrap it
        in a PL/SQL-style ``[DECLARE …] BEGIN … END;``; otherwise emit the
        statements directly (a bare ``CALL`` needs no wrapper). PostgreSQL and
        MySQL override for their own anonymous-block rules.
        """
        if node.degraded:
            return self._emit_degraded_anonymous_block(node)
        decls = [s for s in node.statements if isinstance(s, DeclareStatement)]
        body = [s for s in node.statements if not isinstance(s, DeclareStatement)]
        if not decls:
            return "\n".join(self._emit_node(s) for s in body)
        lines: list[str] = []
        if decls:
            lines.append("DECLARE")
            self._indent_level += 1
            lines.extend(self._emit_indented_stmts(tuple(decls)))
            self._indent_level -= 1
        lines.append("BEGIN")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(tuple(body)))
        self._indent_level -= 1
        lines.append(self._block_end())
        return "\n".join(lines)

    def _emit_degraded_anonymous_block(self, node: AnonymousBlock) -> str:
        """Render a block the target cannot run at the top level as a
        ``-- UNIQUE:`` carrier comment (the transformer already recorded the
        loss in ``result.warnings``), preserving the original for the reader
        instead of emitting invalid SQL. The inner statements are rendered in a
        BEGIN…END shell so the whole thing round-trips if fed back to an engine
        that does support anonymous blocks."""
        inner = self._emit_anonymous_block(
            AnonymousBlock(statements=node.statements, degraded=False)
        )
        body = inner if inner.strip() else "BEGIN\nEND;"
        commented = "\n".join(
            f"-- {line}" if line.strip() else "--" for line in body.split("\n")
        )
        return (
            "-- UNIQUE: anonymous PL/SQL block has no top-level "
            f"{self.dialect_name} equivalent; preserved below:\n{commented}"
        )

    def _emit_indented_stmts(
        self, stmts: tuple[ASTNode, ...] | list[ASTNode]
    ) -> list[str]:
        """Emit a sequence of statements at the current indent, one output line
        per source line, blanking whitespace-only lines. Shared by the block
        constructs (TRY/CATCH, IF, loops) across engines."""
        out: list[str] = []
        for stmt in stmts:
            text = self._emit_node(stmt)
            for line in text.split("\n"):
                out.append(f"{self._indent()}{line}" if line.strip() else "")
        return out

    def _emit_last_identity_capture(self, node: LastIdentityCapture) -> str:
        # Unpaired fallback (the pairing pass consumed the paired ones):
        # a valid NULL assignment plus the documented note — the old text
        # path emitted the invalid ``v := /* … */;``.
        return f"{node.target} := NULL; " "/* last identity: use <sequence>.CURRVAL */"

    def _emit_handler_declaration(self, node: HandlerDeclaration) -> str:
        # MySQL-only spelling; other targets fold it into TryCatchBlock
        # in the transformer and never reach here.
        conds = ", ".join(node.conditions)
        action = self._emit_node(node.body[0]) if node.body else ";"
        return f"DECLARE {node.kind} HANDLER FOR {conds} {action}"

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        """Default (PL/SQL-style) TRY/CATCH: a BEGIN … EXCEPTION WHEN OTHERS
        block. T-SQL and MySQL override this with their own shapes."""
        lines = ["BEGIN"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.try_body))
        self._indent_level -= 1
        lines.append("EXCEPTION")
        lines.append("WHEN OTHERS THEN")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.catch_body))
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

    def _emit_call(self, node: CallStatement) -> str:
        """Emit a stored-procedure call. Default is T-SQL ``EXEC name args``;
        PostgreSQL/MySQL (``CALL name(args)``) and Oracle (``name(args);``)
        override with their own call syntax."""
        name = self._qualified_name(node.schema, node.name)
        return f"EXEC {name} {node.args};" if node.args else f"EXEC {name};"

    def _emit_execute(self, node: ExecuteStatement) -> str:
        expr = self._emit_node(node.sql_expression)
        params = [self._emit_node(p) for p in node.params]
        if node.into_vars:
            return self._emit_execute_into(
                expr, params, list(node.into_vars), node.immediate, node.strict
            )
        return self._emit_execute_stmt(expr, params, node.immediate)

    def _emit_execute_into(
        self,
        expr: str,
        params: list[str],
        into_vars: list[str],
        immediate: bool,
        strict: bool = False,
    ) -> str:
        """Dynamic SQL whose scalar result is captured (Oracle ``EXECUTE
        IMMEDIATE <expr> INTO v``). Default is Oracle's native form (which is
        inherently strict); each engine overrides with its capture idiom."""
        using = f" USING {', '.join(params)}" if params else ""
        return f"EXECUTE IMMEDIATE {expr} INTO {', '.join(into_vars)}{using};"

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        """Emit an EXEC/EXECUTE for this engine. Default is Oracle's
        ``EXECUTE IMMEDIATE [USING …]``; each engine subclass overrides.
        ``immediate`` marks a dynamic-SQL run (Oracle EXECUTE IMMEDIATE)."""
        if params:
            using = ", ".join(params)
            return f"EXECUTE IMMEDIATE {expr} USING {using};"
        return f"EXECUTE IMMEDIATE {expr};"

    def _emit_pg_execute(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        """Emit a T-SQL EXEC for PostgreSQL.

        Like MySQL, a captured EXEC arrives as one of three shapes: a
        ``sp_executesql`` dynamic call, a named stored-procedure call, or a bare
        dynamic-SQL string/variable. PostgreSQL invokes procedures with
        ``CALL name(args)`` and runs dynamic SQL with plpgsql ``EXECUTE <text>``.
        An Oracle ``EXECUTE IMMEDIATE`` (``immediate``) is always dynamic SQL, so
        it maps straight to ``EXECUTE <expr>`` without the named-proc heuristics.
        """
        stripped = expr.strip()

        # Oracle EXECUTE IMMEDIATE: unconditionally a dynamic-SQL run (the
        # expression may be a record field like r.cmd, which the named-proc
        # heuristic below would wrongly read as CALL cmd()).
        if immediate:
            if params:
                return f"EXECUTE {expr} USING {', '.join(params)};"
            return f"EXECUTE {expr};"

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

        # Case 2: a named stored-procedure call → CALL name(args). The proc name
        # may be schema-qualified (dbo.create_invoice); the dbo default schema is
        # dropped for PostgreSQL. The trailing T-SQL OUTPUT keyword on an
        # argument is dropped (an INOUT argument is already passed by reference).
        m = re.match(
            r"(?i)^(?:\[?\w+\]?\s*\.\s*)*\[?(\w+)\]?\s*(.*)$",
            stripped,
        )
        if m:
            proc_name = m.group(1)
            args = self._split_exec_args(m.group(2).strip())
            return f"CALL {proc_name}({', '.join(args)});"

        if params:
            return f"EXECUTE {expr} USING {', '.join(params)};"
        return f"EXECUTE {expr};"

    def _emit_mysql_execute(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        stripped = expr.strip()

        # Oracle EXECUTE IMMEDIATE: dynamic SQL run via the PREPARE workflow (a
        # record field like r.cmd must not be read as a named-proc CALL). Any
        # USING binds carry over to the EXECUTE.
        if immediate:
            copies, using = self._mysql_using_binds(params)
            return (
                f"SET @_stmt = {expr}; PREPARE _dyn FROM @_stmt; "
                f"{copies}EXECUTE _dyn{using}; DEALLOCATE PREPARE _dyn;"
            )

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
            copies, using = self._mysql_using_binds(params)
            return (
                f"SET @_stmt = {expr}; PREPARE _dyn FROM @_stmt; "
                f"{copies}EXECUTE _dyn{using}; DEALLOCATE PREPARE _dyn;"
            )

        # Case 2: a named stored-procedure call. MySQL invokes procedures with
        # CALL name(args). The proc name may be schema-qualified
        # (dbo.create_invoice); the dbo default schema is dropped. T-SQL's
        # trailing OUTPUT keyword on an argument has no inline equivalent and is
        # dropped (the @var is already passed by reference for an OUT parameter).
        m = re.match(
            r"(?i)^(?:\[?\w+\]?\s*\.\s*)*\[?(\w+)\]?\s*(.*)$",
            stripped,
        )
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
    def _mysql_using_binds(params: list[str]) -> tuple[str, str]:
        """Bindings for MySQL's ``EXECUTE ... USING``, which accepts only
        session (``@``) variables: each routine local/parameter is copied into
        an ``@_b<n>`` session variable first. Returns ``(copies, using)`` —
        ``copies`` is the ``SET @_b1 = v; `` prefix, ``using`` the clause."""
        if not params:
            return "", ""
        copies: list[str] = []
        binds: list[str] = []
        for i, p in enumerate(params, start=1):
            if p.strip().startswith("@"):
                binds.append(p.strip())
                continue
            binds.append(f"@_b{i}")
            copies.append(f"SET @_b{i} = {p.strip()}; ")
        return "".join(copies), f" USING {', '.join(binds)}"

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

    def _emit_get_diagnostics(self, node: GetDiagnosticsStatement) -> str:
        """MySQL native form (condition items need CONDITION 1); the PG
        emitter overrides with its own spelling."""
        pairs = ", ".join(f"{v} = {item}" for v, item in node.items)
        cond = "CONDITION 1 " if node.stacked else ""
        stacked = "STACKED " if node.stacked else ""
        return f"GET {stacked}DIAGNOSTICS {cond}{pairs};"

    def _emit_perform(self, node: PerformStatement) -> str:
        """Default (MySQL): ``DO <expr>;`` evaluates and discards —
        plpgsql PERFORM's exact semantics for an expression. T-SQL,
        Oracle and PostgreSQL override."""
        expr = self._emit_node(node.expression) if node.expression else "0"
        return f"DO {expr};"

    def _emit_print(self, node: PrintStatement) -> str:
        """Default print is MySQL's ``SELECT <expr>;`` (no PRINT statement).
        Inside a MySQL FUNCTION a bare SELECT is invalid (functions cannot
        return result sets, error 1415), so the message diverts to a user
        variable with a documented carrier. T-SQL, Oracle and PostgreSQL
        override."""
        expr = self._emit_node(node.expression)
        if self._in_mysql_function:
            return (
                f"SET @uq_notice = {expr};  -- UNIQUE: notice has no output "
                "channel inside a MySQL function; message kept in @uq_notice"
            )
        return f"SELECT {expr};"

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        """Default raise is MySQL's SIGNAL. T-SQL, Oracle and PostgreSQL
        override with their own raise form."""
        if node.reraise:
            return "RESIGNAL;"
        msg = self._emit_node(node.message) if node.message else ""
        if not msg.strip():
            # A bare re-RAISE inside a handler: MySQL's spelling is
            # RESIGNAL (an empty MESSAGE_TEXT was a syntax error AND a
            # broken re-raise).
            return "RESIGNAL;"
        # MySQL SIGNAL requires MESSAGE_TEXT to be a string and the error number
        # in MYSQL_ERRNO; the raw T-SQL argument tuple "(msg_or_id, severity,
        # state)" is invalid there. Keep the human-readable message AND the
        # error number when both exist (audit 2026-07-02, S2-2).
        text, number, rest = self._raise_parts(msg)
        if number is not None:
            # MYSQL_ERRNO takes an unsigned 1..65535 literal; Oracle's
            # RAISE_APPLICATION_ERROR codes are negative (-20000..-20999) —
            # keep their magnitude.
            magnitude = abs(int(re.sub(r"\s+", "", number)))
            number = str(magnitude) if 1 <= magnitude <= 65535 else None
        if text is not None:
            errno = f", MYSQL_ERRNO = {number}" if number is not None else ""
            # SIGNAL's MESSAGE_TEXT accepts only a literal or a variable —
            # an expression (a formatted CONCAT(...) message) must be
            # hoisted through a user variable first.
            if not (text.startswith(("'", '"', "@")) or re.fullmatch(r"\w+", text)):
                return (
                    f"SET @uq_errmsg = {text};\n"
                    f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = @uq_errmsg{errno};"
                )
            sig = f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = {text}{errno}"
        elif number is not None:
            # A numeric message id only — MySQL can't resolve a message-id to
            # text, so use it as the error number and document it.
            sig = (
                f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = "
                f"'Application error', MYSQL_ERRNO = {number}"
            )
        else:
            sig = f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = {msg}"
        comment = ""
        if rest:
            comment = (
                f"  -- UNIQUE: original RAISERROR/THROW severity/state args "
                f"dropped: {rest}"
            )
        return f"{sig};{comment}"

    @classmethod
    def _raise_parts(cls, msg: str) -> tuple[str | None, str | None, str]:
        """Classify a RAISERROR/THROW argument blob.

        Returns ``(message_text, error_number, remaining_args)``. T-SQL THROW
        is ``errno, 'msg', state``; RAISERROR is ``('msg'|msg_id, severity,
        state)``. The message is the first quoted argument, the number the
        first purely-numeric one; the rest (severity/state) is returned for
        documentation. Using the number as the message loses the
        operator-facing text (audit 2026-07-02, S2-2).
        """
        remaining = msg.strip()
        if remaining.startswith("(") and remaining.endswith(")"):
            remaining = remaining[1:-1].strip()
        args: list[str] = []
        while remaining:
            first, remaining = cls._split_raise_args(remaining)
            args.append(first)
        text = next((a for a in args if a.startswith("'") or a.startswith('"')), None)
        number = next((a for a in args if re.fullmatch(r"-?\s*\d+", a)), None)
        if text is None:
            # RAISERROR(@msg, severity, state): the message is a variable or
            # expression, not a literal — using the severity number as the
            # message would discard the operator-facing text. A (possibly
            # negative) error code is never the message.
            text = next((a for a in args if not re.fullmatch(r"-?\s*\d+", a)), None)
        rest = [a for a in args if a is not text and a is not number]
        return text, number, ", ".join(rest)

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
        """Default RETURN: ``RETURN [value];``. MySQL and PostgreSQL override
        this where a procedure cannot return a value."""
        if node.value:
            val = self._emit_node(node.value)
            return f"RETURN {val};"
        return "RETURN;"

    def _emit_transaction(self, node: TransactionStatement) -> str:
        """Emit a transaction-control statement for the target dialect.

        The overall shape is shared; the parts that differ per engine are small
        hooks (`_emit_begin_transaction`, `_rollback_to_savepoint`,
        `_emit_savepoint`) that subclasses override.
        """
        name = node.name
        if node.action == TransactionAction.BEGIN:
            return self._emit_begin_transaction(name)
        if node.action == TransactionAction.COMMIT:
            return "COMMIT;"
        if node.action == TransactionAction.ROLLBACK:
            # ROLLBACK to a savepoint name keeps the name; a plain rollback does
            # not. T-SQL "ROLLBACK TRAN name" rolls back to a save point.
            if name:
                return self._rollback_to_savepoint(name)
            return "ROLLBACK;"
        return self._emit_savepoint(name)

    def _emit_begin_transaction(self, name: str | None) -> str:
        """BEGIN-transaction form. Default: implicit, document the dropped
        statement (Oracle/PostgreSQL). T-SQL and MySQL override."""
        return (
            f"/* UNIQUE: BEGIN TRANSACTION dropped -- {self._dialect} starts a "
            "transaction implicitly */"
        )

    def _rollback_to_savepoint(self, name: str) -> str:
        """ROLLBACK to a named savepoint. Default standard SQL; T-SQL overrides."""
        return f"ROLLBACK TO SAVEPOINT {name};"

    def _emit_savepoint(self, name: str | None) -> str:
        """SAVEPOINT form. Default standard SQL; T-SQL overrides."""
        return f"SAVEPOINT {name};" if name else "SAVEPOINT;"

    def _emit_waitfor(self, node: WaitForStatement) -> str:
        """Emit a T-SQL WAITFOR for the target dialect.

        DELAY (a relative pause) maps to each engine's sleep; TIME (wait until
        an absolute clock time) has no portable equivalent and is documented.
        The base handles the non-T-SQL engines; TSqlEmitter overrides to emit
        the native WAITFOR. The per-engine sleep call is the `_sleep_call` hook.
        """
        if node.kind == "TIME":
            return (
                f"/* UNIQUE: WAITFOR TIME '{node.value}' has no {self._dialect} "
                "equivalent (wait until an absolute time) */"
            )
        secs = node.seconds if node.seconds is not None else 0
        # Render whole seconds without a trailing .0 where possible.
        secs_str = str(int(secs)) if float(secs).is_integer() else str(secs)
        return self._sleep_call(secs_str)

    def _sleep_call(self, secs: str) -> str:
        """The engine's "sleep for N seconds" statement. Default is Oracle's
        DBMS_LOCK.SLEEP; MySQL and PostgreSQL override."""
        return f"DBMS_LOCK.SLEEP({secs});"

    def _emit_cursor_op(self, node: CursorOperation) -> str:
        op = node.operation.upper()
        if op == "OPEN":
            if node.query:
                query_str = self._emit_node(node.query)
                return self._emit_cursor_open(
                    node.cursor_name, query_str, scroll=node.scroll
                )
            if node.args:
                return f"OPEN {node.cursor_name}({node.args});"
            return f"OPEN {node.cursor_name};"
        elif op == "FETCH":
            into_str = ", ".join(node.into_vars)
            return self._emit_cursor_fetch(
                node.cursor_name, into_str, direction=node.direction
            )
        elif op == "CLOSE":
            return f"CLOSE {node.cursor_name};"
        elif op == "DEALLOCATE":
            return self._emit_cursor_deallocate(node.cursor_name)
        return f"{op} {node.cursor_name};"

    def _emit_cursor_open(
        self, cursor_name: str, query_str: str, scroll: str | None = None
    ) -> str:
        """OPEN a cursor with an inline query. Default (PL/SQL) binds the
        query with FOR and drops the PG-only scroll modifier (forward-only
        cursors); the PG and T-SQL emitters override."""
        return f"OPEN {cursor_name} FOR\n{query_str.rstrip().rstrip(';')};"

    def _emit_cursor_fetch(
        self, cursor_name: str, into_str: str, direction: str | None = None
    ) -> str:
        """FETCH a row INTO variables. Default standard form; T-SQL overrides
        with FETCH NEXT FROM and PG re-emits the direction. This default
        serves the forward-only engines (Oracle/MySQL): a non-NEXT
        direction has no equivalent and degrades to the documented
        carrier."""
        if direction and direction.upper() != "NEXT":
            return (
                f"-- UNIQUE: FETCH {direction} has no {self._dialect} "
                "equivalent (cursors are forward-only); statement "
                f"preserved as a comment:\n"
                f"-- FETCH {direction} FROM {cursor_name} INTO {into_str};"
            )
        return f"FETCH {cursor_name} INTO {into_str};"

    def _emit_cursor_deallocate(self, cursor_name: str) -> str:
        """DEALLOCATE a cursor. Only T-SQL needs it; default documents the
        no-op."""
        return f"-- DEALLOCATE not needed in {self._dialect}"

    def _emit_exit(self, node: ExitStatement) -> str:
        cond = self._emit_node(node.condition) if node.condition else ""
        # Cursor %NOTFOUND / %FOUND have dialect-specific equivalents.
        cond = self._translate_cursor_attrs(cond)
        # Default: Oracle / PostgreSQL EXIT [WHEN cond]. T-SQL and MySQL override.
        label = f" {node.label}" if node.label else ""
        if cond:
            return f"EXIT{label} WHEN {cond};"
        return f"EXIT{label};"

    def _translate_cursor_attrs(self, expr: str) -> str:
        """Translate Oracle cursor attributes to the target dialect.

        Default leaves the expression unchanged; engines that have an
        equivalent (T-SQL @@FETCH_STATUS, PostgreSQL FOUND, MySQL handler flag)
        override this.
        """
        return expr

    def _emit_continue(self, node: ContinueStatement) -> str:
        """Default (PL/SQL) CONTINUE [WHEN cond]. T-SQL overrides (no WHEN)."""
        if node.condition:
            cond = self._emit_node(node.condition)
            return f"CONTINUE WHEN {cond};"
        return "CONTINUE;"

    def _emit_null(self, _node: NullStatement) -> str:
        """Default no-op statement is ``NULL;`` (PL/SQL). T-SQL overrides with a
        comment (T-SQL has no NULL statement)."""
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
        """Emit SELECT … INTO in the target dialect's syntax. Default is the
        standard ``SELECT col1, col2 INTO v1, v2 FROM …`` (Oracle/PG/MySQL);
        T-SQL overrides with ``SELECT @v1 = col1, … FROM …``.
        """
        select_list = ""
        if node.columns:
            first = node.columns[0]
            select_list = first.sql if isinstance(first, RawSQL) else ""
        rest = node.rest_sql.rstrip(";").strip()
        into_clause = ", ".join(node.into_vars)
        prefix = f"{node.with_sql}\n" if node.with_sql else ""
        return f"{prefix}SELECT {select_list} INTO {into_clause} {rest};"

    def _emit_raw_sql(self, node: RawSQL) -> str:
        # A construct the parser could not understand is preserved as a documented
        # carrier comment rather than emitted as (invalid) executable SQL, so it
        # never silently changes behaviour or breaks the target script.
        if node.reason == "Could not parse procedural construct":
            body = "\n".join(f"-- {line}" for line in node.sql.splitlines() or [""])
            return f"-- UNIQUE: could not translate; preserved for review\n{body}"
        # Transformer-degraded whole units share the same carrier contract.
        if "preserved as a comment" in node.reason:
            body = "\n".join(f"-- {line}" for line in node.sql.splitlines() or [""])
            return f"-- UNIQUE: {node.reason}\n{body}"
        return node.sql

    def _emit_literal(self, node: Literal) -> str:
        if node.value is None:
            return "NULL"
        if node.dtype == "string":
            return f"'{node.value}'"
        return str(node.value)
