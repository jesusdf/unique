# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — base class and shared dialect maps.

Holds the engine-agnostic and source-dependent transform logic plus the default
behavior, and the type/function mapping tables shared by all targets. Per-target
specifics live in sibling modules ({tsql,oracle,postgresql,mysql}.py). Because
a transform is a source->target operation, pair- and source-dependent logic
stays here parameterized by ``self._source``; only target-only logic is
overridden per target. The factory dispatches
``ProceduralTransformer(source, target)`` to the right target subclass via a
registry the engine modules populate on import.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
from collections.abc import Callable

import sqlglot

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AnonymousBlock,
    AssignmentStatement,
    ASTNode,
    BeginEndBlock,
    CallStatement,
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
    ForeachStatement,
    ForLoopStatement,
    GetDiagnosticsStatement,
    IfStatement,
    LastIdentityCapture,
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
    TryCatchBlock,
    UpdateStatement,
    WhileStatement,
    needs_procedural_wrapper,
)
from unique.core.mappings import (
    LAST_IDENTITY_EXPR,
    PROCEDURAL_FUNC_MAPS,
    PROCEDURAL_TYPE_MAPS,
)
from unique.core.sql_split import split_leading_trivia

from ._expr import ExpressionRewriter

logger = logging.getLogger(__name__)


def _one_line_sql(sql: str) -> str:
    """Collapse a statement's whitespace runs to single spaces, preserving
    the content of string literals (a newline inside ``'…'`` is data)."""
    out: list[str] = []
    in_string = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if in_string:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch in " \t\r\n":
            while i < n and sql[i] in " \t\r\n":
                i += 1
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out).strip()


#: Populated by the per-engine modules via ``register_transformer``.
_TRANSFORMER_REGISTRY: dict[str, type[ProceduralTransformer]] = {}


def register_transformer(name: str, cls: type[ProceduralTransformer]) -> None:
    """Register a per-target transformer subclass under its target name."""
    _TRANSFORMER_REGISTRY[name] = cls


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
        # Ref-cursor parameters dropped on result-set targets: OPEN ... FOR
        # on these names becomes the procedure's result-set SELECT.
        self._dropped_cursor_params: set[str] = set()
        # Cursor variables bound via ``SET @c = CURSOR … FOR <q>`` and
        # rewritten to ``OPEN c FOR <q>``: the later bare ``OPEN @c`` must
        # then drop (the OPEN already happened at the binding site).
        self._cursor_bound_opens: set[str] = set()
        # The cursor named by the most recent FETCH (already transformed):
        # Oracle rewrites ``@@FETCH_STATUS`` checks to ``<cursor>%FOUND``.
        self._last_fetch_cursor: str | None = None
        # Names of scalar variables seen in declarations (lowercased): a
        # PL/SQL row FOR-loop may shadow one; plpgsql refuses a scalar loop
        # variable over rows, so PG renames the loop variable instead.
        self._declared_scalar_names: set[str] = set()
        # Whether a ``@@FETCH_STATUS`` check was lowered to the MySQL
        # ``v_fetch_done`` flag (the routine then needs the flag declaration
        # and its CONTINUE HANDLER injected).
        self._used_fetch_done = False
        self._var_map: dict[str, str] = {}
        # Parameter names (transformed, lowercase) of the routine being
        # transformed — Oracle forbids a local shadowing a parameter
        # (PLS-00410; wave 181), so colliding declares rename.
        self._param_names: set[str] = set()
        # Names (transformed form) of variables/parameters declared with a
        # string type. Used to disambiguate T-SQL '+' as concatenation when no
        # string literal is present (e.g. SHA2(@a + @b) over two text vars).
        self._string_vars: set[str] = set()
        # Names (transformed form) of DATE/DATETIME variables/parameters. Used to
        # rewrite ``d2 - d1`` (legal date subtraction on the source) to
        # ``DATEDIFF(DAY, d1, d2)`` for the T-SQL target, which rejects the ``-``.
        self._date_vars: set[str] = set()
        # True while transforming a trigger body, so embedded DML maps the
        # T-SQL inserted/deleted pseudo-tables to NEW/OLD (or documents a
        # set-based use that has no row-level equivalent).
        self._in_trigger = False
        # True while transforming a *purely* set-based trigger that the target
        # can express via transition tables; the set-based DML is then kept
        # as-is (inserted/deleted survive) instead of being documented.
        self._preserve_set_based_dml = False
        # The composed text-level expression engine (see _expr.py).
        self._expr = ExpressionRewriter(self)

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

    @staticmethod
    def _is_date_type(dt: DataType) -> bool:
        base = dt.name.split("(")[0].strip().upper()
        return base in {
            "DATE",
            "DATETIME",
            "DATETIME2",
            "SMALLDATETIME",
            "TIMESTAMP",
            "TIMESTAMPTZ",
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
            PragmaDeclaration: self._transform_pragma,
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
            GetDiagnosticsStatement: self._transform_get_diagnostics,
            PerformStatement: self._transform_perform,
            ReturnStatement: self._transform_return,
            CursorDeclaration: self._transform_cursor_decl,
            CursorOperation: self._transform_cursor_op,
            ForLoopStatement: self._transform_for_loop,
            ForeachStatement: self._transform_foreach,
            LoopStatement: self._transform_loop,
            ExitStatement: self._transform_exit,
            EmbeddedDML: self._transform_embedded_dml,
            SelectIntoStatement: self._transform_select_into,
            NullStatement: self._transform_null,
            RawSQL: self._transform_raw_sql,
            CommentStatement: self._transform_comment,
            AnonymousBlock: self._transform_anonymous_block,
            CallStatement: self._transform_call,
        }

        handler = handlers.get(type(node))
        if handler:
            return handler(node)
        return node

    def _folds_exception_scope(self) -> bool:
        """Whether a PL/SQL EXCEPTION section must physically wrap its block's
        statements on this target (T-SQL TRY/CATCH, MySQL DECLARE ... HANDLER
        blocks); Oracle/PostgreSQL keep the trailing EXCEPTION form."""
        return False

    @staticmethod
    def _fold_exception_scope(stmts: tuple[ASTNode, ...]) -> tuple[ASTNode, ...]:
        """Fold an EXCEPTION section's preceding siblings into a TryCatchBlock
        (the handlers protect the whole block in PL/SQL)."""
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, ExceptionBlock):
                handlers_body: list[ASTNode] = []
                for handler in stmt.handlers:
                    handlers_body.extend(handler.body)
                names = {h.exception_name.upper() for h in stmt.handlers}
                folded = TryCatchBlock(
                    try_body=tuple(stmts[:i]),
                    catch_body=tuple(handlers_body),
                    catch_kind=("NO_DATA_FOUND" if names == {"NO_DATA_FOUND"} else ""),
                )
                return (folded, *stmts[i + 1 :])
        return stmts

    def _transform_body(self, stmts: tuple[ASTNode, ...]) -> tuple[ASTNode, ...]:
        """Transform a sequence of body statements."""
        if self._folds_exception_scope():
            stmts = self._fold_exception_scope(stmts)
        result: list[ASTNode] = []
        for stmt in stmts:
            # A dropped dialect-specific SET option is documented from its
            # *original* text; transforming it first (e.g. Oracle's dbo-stripping
            # or DML fixups) would corrupt the text we want to preserve, so
            # short-circuit before _transform_node touches it.
            if isinstance(stmt, RawSQL) and "SET option" in stmt.reason:
                result.append(self._preserve_dropped_set_option(stmt))
                continue
            transformed = self._transform_node(stmt)
            result.append(self._preserve_dropped_set_option(transformed))
        if self._target == "oracle":
            result = self._capture_identity_via_returning(result)
        return tuple(result)

    def _capture_identity_via_returning(self, stmts: list[ASTNode]) -> list[ASTNode]:
        """Rewrite the T-SQL ``INSERT; SET v = SCOPE_IDENTITY()`` pair into
        Oracle's ``INSERT … RETURNING <idcol> INTO v`` (dropping the now-empty
        assignment).

        Oracle has no session-scoped last-identity function, so the id of an
        identity column must be captured on the INSERT itself. Matches an
        assignment whose value is only the last-identity placeholder and pairs
        it with the most recent single-row ``INSERT … VALUES`` into a table
        whose identity column is known.
        """
        from unique.core.converter import IDENTITY_COLUMNS

        registry = IDENTITY_COLUMNS.get()
        if not registry:
            return stmts
        out: list[ASTNode] = []
        last_insert_idx: int | None = None
        for stmt in stmts:
            var = self._identity_assignment_var(stmt)
            if var is not None and last_insert_idx is not None:
                insert = out[last_insert_idx]
                assert isinstance(insert, EmbeddedDML)
                rewritten = self._append_returning_into(insert.sql, var, registry)
                if rewritten is not None:
                    out[last_insert_idx] = EmbeddedDML(
                        sql=rewritten, dialect=insert.dialect
                    )
                    last_insert_idx = None
                    continue  # drop the assignment; the INSERT now captures it
            if isinstance(stmt, EmbeddedDML) and re.match(
                r"(?is)\s*INSERT\s+INTO\b.*\bVALUES\b",
                # Match on the code: a leading comment must not hide the INSERT.
                split_leading_trivia(stmt.sql)[1],
            ):
                last_insert_idx = len(out)
            out.append(stmt)
        return out

    def _identity_assignment_var(self, stmt: ASTNode) -> str | None:
        """Return the assigned variable when ``stmt`` is a last-identity
        capture node, else ``None``."""
        if isinstance(stmt, LastIdentityCapture):
            return stmt.target
        return None

    def _append_returning_into(
        self, insert_sql: str, var: str, registry: dict[str, str]
    ) -> str | None:
        """Append ``RETURNING <idcol> INTO <var>`` to an INSERT when its target
        table has a known identity column, else ``None``."""
        m = re.match(r"(?is)\s*INSERT\s+INTO\s+([`\"\[]?\w+[`\"\]]?)", insert_sql)
        if not m:
            return None
        table = m.group(1).strip('`"[]').lower()
        idcol = registry.get(table)
        if not idcol:
            return None
        return f"{insert_sql.rstrip().rstrip(';')} RETURNING {idcol} INTO {var}"

    def _transform_comment(self, node: CommentStatement) -> ASTNode:
        """Restore a documented source-only construct when transpiling back to
        its source engine.

        A forward pass that dropped a construct with no equivalent on the target
        left a ``/* UNIQUE: <orig> -- <dialect>-only … */`` note carrying the
        original and its source dialect. If we are now transpiling *to* that
        dialect, re-inject the original statement (a faithful round-trip);
        otherwise keep the note unchanged so the documentation survives onward
        transpilation to a third engine.
        """
        if node.restore_sql and node.restore_dialect == self._target:
            sql = node.restore_sql.rstrip()
            if not sql.endswith(";"):
                sql += ";"
            return RawSQL(sql=sql, reason="restored source-only construct")
        return node

    def _preserve_dropped_set_option(self, node: ASTNode) -> ASTNode:
        """Turn a dropped dialect-specific SET option into a comment.

        Options like ``SET NOCOUNT ON`` have no equivalent in the target, but
        silently removing them can leave an empty block (e.g. ``IF ... THEN END
        IF``) that the engine rejects, and erases information. Replace the
        statement with a ``/* UNIQUE: <original> -- <source>-only, no <target>
        equivalent */`` comment so the original is documented and the block keeps
        a (no-op) body. Recording the *source* engine lets a later transpilation
        back to that engine restore the original (see ``_transform_comment``).
        """
        if isinstance(node, RawSQL) and "SET option" in node.reason:
            return CommentStatement(
                text=(
                    f"/* UNIQUE: {node.sql} -- {self._source}-only, "
                    f"no {self._target} equivalent */"
                ),
                style="block",
            )
        return node

    _REFCURSOR_TYPE_RE = re.compile(r"(?i)(?:^|\.)\w*(?:REF)?CURSOR$|^SYS_REFCURSOR$")

    def _package_refcursor_type(self) -> str | None:
        """The target type standing in for a package-qualified ref-cursor
        type. Default None (fall through to the generic carrier); PostgreSQL
        overrides with REFCURSOR."""
        return None

    def _returns_result_sets_directly(self) -> bool:
        """Whether the target's procedures return result sets by SELECTing
        (T-SQL, MySQL) — a ref-cursor OUT parameter then has no place and its
        OPEN ... FOR query becomes the procedure's result set."""
        return self._target in ("tsql", "mysql")

    def _transform_params(
        self, params: tuple[ParameterDefinition, ...]
    ) -> tuple[ParameterDefinition, ...]:
        """Transform parameter definitions between dialects."""
        result: list[ParameterDefinition] = []
        for p in params:
            if self._returns_result_sets_directly() and self._REFCURSOR_TYPE_RE.search(
                p.data_type.name.strip()
            ):
                # OPEN <p> FOR <q> in the body becomes a plain result-set
                # SELECT (see _transform_cursor_op); the parameter itself has
                # no target form.
                self._dropped_cursor_params.add(
                    self._transform_var_name(p.name).lower().lstrip("@")
                )
                self._warnings.append(
                    f"ref-cursor parameter {p.name!r} dropped: {self._target} "
                    "procedures return the result set directly (callers read "
                    "it instead of fetching from the cursor)"
                )
                continue
            new_name = self._transform_var_name(p.name)
            new_type = self._transform_data_type(p.data_type)
            new_default = self._transform_node(p.default) if p.default else None
            self._var_map[p.name] = new_name
            self._param_names.add(new_name.lower().lstrip("@"))
            if self._is_string_type(p.data_type):
                self._string_vars.add(new_name)
            if self._is_date_type(p.data_type):
                self._date_vars.add(new_name)
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
        # An Oracle trigger body assigns to the affected row via ``:NEW.col``;
        # a MySQL/PostgreSQL source spells the assignment target ``NEW.col``.
        if (
            self._target == "oracle"
            and self._in_trigger
            and re.match(r"(?i)^(?:NEW|OLD)\s*\.", name)
        ):
            return self._expr._to_oracle_row_ref(name)
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
            candidate = f"@{clean.lower()}"
            # Prefix-stripping may collide with another variable (param p_x
            # vs local v_p_x — live error 134, and a silent aliasing risk):
            # on collision the name keeps its full source spelling.
            taken = {
                v.lower() for k, v in self._var_map.items() if k.lower() != name.lower()
            }
            if candidate.lower() in taken:
                candidate = f"@{name.lower()}"
            return candidate
        elif self._source == "mysql" and self._target == "tsql":
            # MySQL local variables/params have no sigil; T-SQL requires ``@``.
            return name if name.startswith("@") else f"@{name}"
        if self._target == "oracle" and name.startswith("_"):
            # Oracle rejects a leading underscore unquoted (ORA-00911 /
            # PLS-00103); quoting would have to reach every raw-text
            # reference, so rename instead (the _var_map rewrite keeps
            # references consistent).
            return f"uq{name}"
        return name

    def _transform_var_in_sql(self, sql: str) -> str:
        """Transform variable references within raw SQL text."""
        if self._source == "tsql" and self._target != "tsql":
            # Strip SQL Server's default schema prefix — none of the other
            # engines has a "dbo" schema (Oracle objects live in the current
            # user's schema, PostgreSQL's default is public, and a MySQL
            # qualifier would name a database).
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
        elif self._source in ("oracle", "postgresql", "mysql") and self._target in (
            "tsql",
            "oracle",
        ):
            # Prefix known variable/parameter names with T-SQL's ``@`` (the map
            # holds source-name → transformed ``@name``); a bare column of the
            # same name is not in the map, so it is left alone. Only outside
            # string literals — a message text mentioning the variable must
            # stay verbatim.
            def rename_names(segment: str) -> str:
                for old_name, new_name in self._var_map.items():
                    # Case-insensitive: Oracle/PG identifiers fold case, so a
                    # body reference may be spelled differently than its
                    # declaration (live: PRINT referencing v_x vs V_X).
                    # A name followed by ``(`` is a FUNCTION CALL, not the
                    # variable — ``count(*)`` became ``@count(*)`` when a
                    # local named count existed (wave 219). Dotted names
                    # (t.count) are columns, not the variable either.
                    # An optional ``<qualifier> .`` prefix (possibly
                    # space-separated, as the token rejoin spells
                    # ``t1 . data``) marks a COLUMN, not the variable —
                    # capture and preserve it so the fixed-width
                    # lookbehind's blind spot across spaces is closed
                    # (wave 237).
                    def _rn(m: re.Match[str], _new: str = new_name) -> str:
                        return m.group(0) if m.group(1) else _new

                    segment = re.sub(
                        rf"(?i)(?<![@\w])(\w+\s*\.\s*)?{re.escape(old_name)}\b(?!\s*\()",
                        _rn,
                        segment,
                    )
                return segment

            sql = self._map_outside_strings(sql, rename_names)
        return sql

    _STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")

    @classmethod
    def _map_outside_strings(cls, sql: str, fn: Callable[[str], str]) -> str:
        """Apply *fn* to the parts of *sql* outside string literals."""
        parts: list[str] = []
        last = 0
        for m in cls._STRING_LITERAL_RE.finditer(sql):
            parts.append(fn(sql[last : m.start()]))
            parts.append(m.group(0))
            last = m.end()
        parts.append(fn(sql[last:]))
        return "".join(parts)

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
        if upper == "@@FETCH_STATUS" and os.environ.get("UNIQUE_IR_FIRST"):
            # IR-first mode maps the comparison via FETCH_STATUS_FORMS (M3
            # precondition (a)); commenting the token here would hand the IR
            # a headless ``/* … */ = 0``.
            return var
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

        # SSMS scripts bracket-quote even type names ([tinyint], [nvarchar]).
        # The quoting is source identifier syntax, not part of the type name,
        # so strip it before any mapping (audit S1-1, procedural pipeline).
        unquoted = self._QUOTED_IDENT_SEGMENT.sub(
            lambda m: m.group(1) or m.group(2) or m.group(3) or "", dt.name
        )
        if unquoted != dt.name:
            dt = DataType(name=unquoted, params=dt.params)

        # A PG DOMAIN name resolves to its harvested base type off PG
        # (the CREATE DOMAIN itself degrades, so the name exists nowhere).
        if self._source == "postgresql" and self._target != "postgresql":
            from unique.core.converter import PG_DOMAIN_TYPES

            domains = PG_DOMAIN_TYPES.get() or {}
            base = domains.get(dt.name.lower())
            if base is not None:
                return self._transform_data_type(DataType(name=base))

        type_name = dt.name.upper()

        # Handle %TYPE / %ROWTYPE references
        if "%TYPE" in type_name or "%ROWTYPE" in type_name:
            is_rowtype = "%ROWTYPE" in type_name
            # %TYPE: resolve to the concrete column type when a DB is connected.
            if self._metadata is not None and not is_rowtype:
                try:
                    resolved = self._metadata.resolve_type_reference(  # type: ignore[attr-defined]
                        dt.name
                    )
                    if resolved is not None:
                        return self._transform_data_type(resolved)
                except Exception:  # pragma: no cover - defensive
                    pass
            # %ROWTYPE: consult the DB for the record's columns so the carrier
            # (below) documents the concrete shape the row stands for.
            resolved_cols = None
            if self._metadata is not None and is_rowtype:
                try:
                    table_ref = dt.name.split("%")[0]
                    resolved_cols = self._metadata.resolve_table_columns(  # type: ignore[attr-defined]
                        table_ref
                    )
                except Exception:  # pragma: no cover - defensive
                    resolved_cols = None
            # Oracle supports %TYPE/%ROWTYPE natively, so keep the reference
            # as-is for an Oracle target (also makes a carrier round-trip back
            # to Oracle faithful) instead of lowering it to a carrier.
            if self._supports_type_reference():
                return DataType(name=dt.name, params=dt.params)
            # No native support: emit a permissive carrier type and preserve the
            # original reference as a comment so the substitution is documented
            # and reversible.
            kind = "%ROWTYPE" if is_rowtype else "%TYPE"
            if is_rowtype and resolved_cols:
                cols_desc = ", ".join(
                    f"{c.column_name} {c.data_type}" for c in resolved_cols
                )
                self._warnings.append(
                    f"%ROWTYPE reference '{dt.name}' resolved via --db-url to "
                    f"{len(resolved_cols)} columns ({cols_desc}); the target has "
                    "no record type, so it is emitted as a carrier with the "
                    "original preserved in a /* UNIQUE */ comment."
                )
            else:
                self._warnings.append(
                    f"{kind} reference '{dt.name}' could not be resolved without "
                    "a database connection (use --db-url). Emitted as a carrier "
                    "type with the original preserved in a /* UNIQUE */ comment."
                )
            carrier = self._unknown_type_carrier()
            return DataType(name=carrier, origin_comment=dt.name)

        # A package/schema-qualified type (``pkg.ref_cursor_type``): only
        # Oracle can reference it. Elsewhere lower it to the carrier like
        # %TYPE — leaving it dotted shipped ``DECLARE x pkg.type;``, a hard
        # parse error on every other engine. Only a clean identifier chain
        # qualifies — mangled fragments (URLs from shredded string content)
        # must keep their old shape rather than gain a lying carrier.
        if re.fullmatch(r"\w+(?:\.\w+)+", dt.name):
            if self._supports_type_reference():
                return DataType(name=dt.name, params=dt.params)
            # A package ref-cursor type (pkg.my_cursor): the target's own
            # ref-cursor type is faithful — the generic carrier turned the
            # later ``OPEN v FOR`` into a type error (42804 on PG).
            if self._REFCURSOR_TYPE_RE.search(dt.name.strip()):
                refcur = self._package_refcursor_type()
                if refcur:
                    return DataType(name=refcur, origin_comment=dt.name)
            self._warnings.append(
                f"qualified type '{dt.name}' has no {self._target} "
                "equivalent; emitted as a carrier type with the original "
                "preserved in a /* UNIQUE */ comment."
            )
            carrier = self._unknown_type_carrier()
            return DataType(name=carrier, origin_comment=dt.name)

        # Handle VARCHAR(MAX) → CLOB/TEXT/LONGTEXT (per target)
        if type_name in ("VARCHAR", "NVARCHAR") and dt.params == (-1,):
            mapped = self._varchar_max_type(type_name == "NVARCHAR")
            if mapped is not None:
                return DataType(name=mapped)

        # VARBINARY(MAX) has no sized equivalent outside T-SQL: the plain
        # name map would ship RAW(MAX) / VARBINARY(MAX), both invalid.
        if type_name == "VARBINARY" and dt.params == (-1,):
            mapped = {
                "oracle": "BLOB",
                "mysql": "LONGBLOB",
                "postgresql": "BYTEA",
            }.get(self._target)
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
                    params = tuple(
                        -1 if p.strip().upper() == "MAX" else int(p.strip())
                        for p in params_str
                    )
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
        return PROCEDURAL_TYPE_MAPS.get((self._source, self._target), {})

    # ---------------------------------------------------------------
    # Node-specific transformations
    # ---------------------------------------------------------------

    # A source-quoted identifier segment: [x] (T-SQL), "x" (Oracle/PG),
    # `x` (MySQL). Used to translate quoting on routine headers.
    _QUOTED_IDENT_SEGMENT = re.compile(r'\[([^\]]*)\]|"([^"]*)"|`([^`]*)`')

    def _translate_ident_quoting(self, name: str | None) -> str | None:
        """Translate source identifier quoting on a (possibly dot-qualified)
        object name (audit S1-1, procedural pipeline).

        SSMS scripts quote every header identifier ([dbo].[fn]); leaking the
        brackets into another engine's routine header is invalid SQL there.
        A plain-word segment is emitted bare; a segment that genuinely needs
        quoting (non-word characters) is re-quoted with the target's own
        convention.
        """
        if not name:
            return name

        def repl(m: re.Match[str]) -> str:
            inner = m.group(1) or m.group(2) or m.group(3) or ""
            if re.fullmatch(r"\w+", inner):
                return inner
            left, right = {"tsql": ("[", "]"), "mysql": ("`", "`")}.get(
                self._target, ('"', '"')
            )
            return f"{left}{inner}{right}"

        return self._QUOTED_IDENT_SEGMENT.sub(repl, name)

    def _target_schema(self, schema: str | None) -> str | None:
        """Return the schema for the target dialect; strip SQL Server's default
        ``dbo`` where the target has no such schema (Oracle)."""
        schema = self._translate_ident_quoting(schema)
        if schema and schema.lower() == "dbo" and self._strip_dbo_schema():
            return None
        return schema

    def _strip_dbo_schema(self) -> bool:
        """Whether to drop a ``dbo`` schema qualifier for this target. Default
        keep; Oracle overrides to strip."""
        return False

    def _drop_param_shadowing_locals(
        self,
        body: tuple[ASTNode, ...],
        params: tuple[ParameterDefinition, ...],
    ) -> tuple[ASTNode, ...]:
        """Drop local declarations that shadow a same-named parameter.

        Oracle allows a local variable shadowing a parameter; T-SQL forbids
        the re-DECLARE (error 134). T-SQL parameters are assignable local
        copies, so the parameter itself plays the shadowed local's role.
        """
        if self._target != "tsql" or not params:
            return body
        param_names = {p.name.lstrip("@").lower() for p in params}

        def keep(stmt: ASTNode) -> bool:
            if (
                isinstance(stmt, DeclareStatement)
                and stmt.name.lstrip("@").lower() in param_names
            ):
                self._warnings.append(
                    f"local variable {stmt.name} shadowed parameter; "
                    "the T-SQL parameter (an assignable copy) is reused"
                )
                return False
            return True

        out: list[ASTNode] = []
        for stmt in body:
            if isinstance(stmt, StatementList) and any(
                not keep(s) for s in stmt.statements
            ):
                kept = tuple(s for s in stmt.statements if keep(s))
                if kept:
                    out.append(StatementList(statements=kept))
                continue
            if keep(stmt):
                out.append(stmt)
        return tuple(out)

    _MYSQL_USER_VAR_RE = re.compile(r"(?<!@)@(\w+)")

    @staticmethod
    def _register_degraded_routine(name: str | None) -> None:
        from unique.core.converter import DEGRADED_ROUTINES

        registry = DEGRADED_ROUTINES.get()
        if registry is not None and name:
            registry.add(name.lower())

    _ROUTINE_NAME_RE = re.compile(
        r"(?is)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:DEFINER\s*=\s*\S+\s+)?"
        r"(?:PROCEDURE|FUNCTION|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:`?\w+`?\.)?`?(\w+)`?"
    )

    def _degrade_mysql_uservar(self, node: ASTNode) -> RawSQL | None:
        """A MySQL routine referencing @user variables — WHOLE degrade
        off MySQL (session-scoped state with no target equivalent; the
        DML pipeline gates the same class at wave 59, this is its
        procedural twin)."""
        if self._source != "mysql" or self._target == "mysql":
            return None
        kind = "user"
        found = self._find_uservar_text(node)
        if found is None:
            # MySQL @@system variables (@@server_id, …) shipped raw and
            # T-SQL rejects an unknown @@name (wave 167).
            found = self._find_sysvar_text(node)
            kind = "system"
        if found is None:
            return None
        sigil = "@" if kind == "user" else "@@"
        reason = (
            f"MySQL {kind} variable {sigil}{found} has no {self._target} "
            "equivalent; routine preserved as a comment"
        )
        self._warnings.append(reason)
        self._register_degraded_routine(getattr(node, "name", None))
        from unique.core.procedural.emitter import ProceduralEmitter

        original = ProceduralEmitter(self._source).emit(node)
        return RawSQL(sql=original, reason=reason)

    def _find_uservar_text(self, value: object) -> str | None:
        import dataclasses as _dc

        if isinstance(value, str):
            scrubbed = re.sub(r"'(?:[^']|'')*'", "''", value)
            m = self._MYSQL_USER_VAR_RE.search(scrubbed)
            return m.group(1) if m else None
        if _dc.is_dataclass(value) and not isinstance(value, type):
            for f in _dc.fields(value):
                found = self._find_uservar_text(getattr(value, f.name))
                if found is not None:
                    return found
        if isinstance(value, tuple):
            for item in value:
                found = self._find_uservar_text(item)
                if found is not None:
                    return found
        return None

    _MYSQL_SYS_VAR_RE = re.compile(r"@@(?:(?:GLOBAL|SESSION|LOCAL)\.)?(\w+)", re.I)

    def _find_sysvar_text(self, value: object) -> str | None:
        import dataclasses as _dc

        if isinstance(value, str):
            scrubbed = re.sub(r"'(?:[^']|'')*'", "''", value)
            m = self._MYSQL_SYS_VAR_RE.search(scrubbed)
            return m.group(1) if m else None
        if _dc.is_dataclass(value) and not isinstance(value, type):
            for f in _dc.fields(value):
                found = self._find_sysvar_text(getattr(value, f.name))
                if found is not None:
                    return found
        if isinstance(value, tuple):
            for item in value:
                found = self._find_sysvar_text(item)
                if found is not None:
                    return found
        return None

    def _fold_mysql_handlers(
        self, body: tuple[ASTNode, ...]
    ) -> tuple[tuple[ASTNode, ...], str | None]:
        """Fold a MySQL EXIT-for-SQLEXCEPTION handler into the block's
        TryCatchBlock; anything else reports the culprit for a whole
        degrade (CONTINUE resumes at the next statement — no target
        equivalent; specific conditions have no cross-engine names)."""
        from unique.core.ast_nodes import HandlerDeclaration

        if self._source != "mysql" or self._target == "mysql":
            return body, None
        handlers = [s for s in body if isinstance(s, HandlerDeclaration)]
        if not handlers:
            if self._contains_handler(body):
                return body, "handler declared in a nested block"
            return body, None
        for h in handlers:
            if (
                h.kind != "EXIT"
                or not h.conditions
                or not all(c in ("SQLEXCEPTION", "SQLWARNING") for c in h.conditions)
            ):
                what = ", ".join(h.conditions) or "an unrecognized condition"
                return body, f"{h.kind} handler for {what}"
        if len(handlers) > 1:
            return body, "multiple handlers in one block"
        rest = tuple(s for s in body if not isinstance(s, HandlerDeclaration))
        if self._contains_handler(rest):
            return body, "handler declared in a nested block"
        return (TryCatchBlock(try_body=rest, catch_body=handlers[0].body),), None

    def _contains_handler(self, value: object) -> bool:
        from unique.core.ast_nodes import HandlerDeclaration

        if isinstance(value, HandlerDeclaration):
            return True
        if isinstance(value, ASTNode):
            import dataclasses as _dc

            return any(
                self._contains_handler(getattr(value, f.name))
                for f in _dc.fields(value)
            )
        if isinstance(value, tuple):
            return any(self._contains_handler(item) for item in value)
        return False

    def _degrade_for_handler(self, node: ASTNode, culprit: str) -> RawSQL:
        reason = (
            f"MySQL {culprit} has no {self._target} equivalent; "
            "routine preserved as a comment"
        )
        self._warnings.append(reason)
        self._register_degraded_routine(getattr(node, "name", None))
        from unique.core.procedural.emitter import ProceduralEmitter

        original = ProceduralEmitter(self._source).emit(node)
        return RawSQL(sql=original, reason=reason)

    def _transform_procedure(self, node: CreateProcedureStatement) -> ASTNode:
        degraded_uv = self._degrade_mysql_uservar(node)
        if degraded_uv is not None:
            return degraded_uv
        folded_body, handler_culprit = self._fold_mysql_handlers(node.body)
        if handler_culprit is not None:
            return self._degrade_for_handler(node, handler_culprit)
        node = dataclasses.replace(node, body=folded_body)
        new_params = self._transform_params(node.parameters)
        new_body = self._transform_body(
            self._drop_param_shadowing_locals(node.body, node.parameters)
        )
        or_replace = node.or_replace
        if self._source == "tsql" and self._target in ("oracle", "postgresql"):
            or_replace = True
        return CreateProcedureStatement(
            name=self._translate_ident_quoting(node.name) or node.name,
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
                name=self._translate_ident_quoting(node.name) or node.name,
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

    def _void_return_type(self) -> DataType:
        """Neutral scalar replacing PG's ``void`` (Oracle overrides)."""
        return DataType(name="INT")

    def _void_return_value(self) -> ASTNode:
        """Value for the guaranteed trailing RETURN of a void function."""
        return RawSQL(sql="0", reason="expression")

    @staticmethod
    def _ends_with_return(body: tuple[ASTNode, ...]) -> bool:
        for stmt in reversed(body):
            if isinstance(stmt, CommentStatement):
                continue
            return isinstance(stmt, ReturnStatement)
        return False

    #: PG pseudo-types a routine cannot carry anywhere else: ``record``
    #: (row shape unknown until runtime) and the polymorphic family
    #: (un-instantiable outside PG's type system).
    #: Scalar spellings a routine parameter may legitimately carry
    #: (native names, PG aliases, and anything the type maps know).
    _KNOWN_SCALAR_TYPES = frozenset(
        {
            "SMALLINT",
            "INT",
            "INTEGER",
            "BIGINT",
            "TINYINT",
            "INT2",
            "INT4",
            "INT8",
            "DECIMAL",
            "NUMERIC",
            "NUMBER",
            "FLOAT",
            "REAL",
            "DOUBLE",
            "DOUBLE PRECISION",
            "FLOAT4",
            "FLOAT8",
            "MONEY",
            "CHAR",
            "NCHAR",
            "VARCHAR",
            "NVARCHAR",
            "VARCHAR2",
            "NVARCHAR2",
            "TEXT",
            "NTEXT",
            "CLOB",
            "NCLOB",
            "CHARACTER",
            "CHARACTER VARYING",
            "BPCHAR",
            "NAME",
            "BYTEA",
            "BLOB",
            "BINARY",
            "VARBINARY",
            "RAW",
            "IMAGE",
            "BOOLEAN",
            "BOOL",
            "BIT",
            "DATE",
            "TIME",
            "TIMETZ",
            "TIMESTAMP",
            "TIMESTAMPTZ",
            "DATETIME",
            "DATETIME2",
            "SMALLDATETIME",
            "DATETIMEOFFSET",
            "INTERVAL",
            "UUID",
            "UNIQUEIDENTIFIER",
            "XML",
            "JSON",
            "JSONB",
            "SERIAL",
            "BIGSERIAL",
            "SMALLSERIAL",
            "OID",
            "REFCURSOR",
            "SYS_REFCURSOR",
            "CURSOR",
            "SQL_VARIANT",
            "ROWVERSION",
            "VOID",
            "TRIGGER",
            "LANGUAGE_HANDLER",
            "CSTRING",
            "INET",
            "CIDR",
            "MACADDR",
            "POINT",
            "ENUM",
            "SET",
        }
    )

    def _is_unknown_scalar_type(self, name: str) -> bool:
        """True when a parameter type is resolvable nowhere: not a known
        scalar, not %TYPE/%ROWTYPE, not array-suffixed (its own gate),
        not a harvested domain/composite."""
        from unique.core.converter import PG_COMPOSITE_TYPES, PG_DOMAIN_TYPES

        base = name.strip()
        if not base or "%" in base or base.endswith("[]"):
            return False
        upper = base.upper().split("(")[0].strip()
        if upper in self._KNOWN_SCALAR_TYPES or upper in self._PG_PSEUDO_TYPES:
            return False
        if base.lower() in (PG_COMPOSITE_TYPES.get() or frozenset()):
            # Harvested composites have their OWN degrade message.
            return False
        if base.lower() in (PG_DOMAIN_TYPES.get() or {}):
            return False
        # Multi-word spellings (DOUBLE PRECISION …) already normalized.
        return " " not in base

    _PG_PSEUDO_TYPES = frozenset(
        {
            "RECORD",
            "ANYELEMENT",
            "ANYARRAY",
            "ANYNONARRAY",
            "ANYENUM",
            "ANYRANGE",
            "ANYMULTIRANGE",
            "ANYCOMPATIBLE",
            "ANYCOMPATIBLEARRAY",
            "ANYCOMPATIBLENONARRAY",
            "ANYCOMPATIBLERANGE",
        }
    )

    def _degrade_record_function(self, node: CreateFunctionStatement) -> ASTNode | None:
        """Degrade a routine using a PG pseudo-type — WHOLE.

        ``record`` variables (row shape unknown until runtime) and
        polymorphic parameter/return types (``anyelement`` …) have no
        mechanical equivalent; shipping them is a guaranteed engine
        error, and fragments would follow."""
        if self._target == "postgresql":
            return None
        culprit: str | None = None
        from unique.core.converter import PG_COMPOSITE_TYPES

        composites = PG_COMPOSITE_TYPES.get() or frozenset()
        if any(
            isinstance(s, DeclareStatement)
            and s.data_type.name.upper() in self._PG_PSEUDO_TYPES
            for s in node.body
        ):
            culprit = "'record' variable"
        elif composites and (
            any(
                isinstance(s, DeclareStatement)
                and s.data_type.name.lower() in composites
                for s in node.body
            )
            or (
                node.return_type is not None
                and node.return_type.name.lower() in composites
            )
            or any(p.data_type.name.lower() in composites for p in node.parameters)
        ):
            culprit = "composite-type variable"
        elif self._source == "postgresql" and (
            unknown := next(
                (
                    p.data_type.name
                    for p in node.parameters
                    if self._is_unknown_scalar_type(p.data_type.name)
                ),
                None,
            )
        ):
            # A param type that is neither a known scalar nor a harvested
            # domain/composite is a rowtype or custom type defined OUTSIDE
            # this script (pg_regress setup tables like ``onek``): it
            # cannot exist on the target either (wave 152).
            culprit = f"parameter of unresolvable type '{unknown}'"
        elif self._target in ("tsql", "mysql") and any(
            isinstance(s, CursorDeclaration) and s.parameters for s in node.body
        ):
            culprit = "parameterized cursor"
        elif self._target != "postgresql" and self._has_dynamic_for(node.body):
            culprit = "FOR loop over dynamic EXECUTE"
        elif any(
            p.data_type.name.upper() in self._PG_PSEUDO_TYPES for p in node.parameters
        ):
            culprit = "polymorphic parameter type"
        elif node.return_type is not None and (
            node.return_type.name.upper() in self._PG_PSEUDO_TYPES
            or node.return_type.name.upper().startswith("SETOF")
        ):
            culprit = f"'{node.return_type.name}' return type"
        elif (
            self._target in ("mysql", "tsql")
            and node.return_type is not None
            and self._REFCURSOR_TYPE_RE.search(node.return_type.name.strip())
        ):
            # Neither engine has cursor-valued functions (wave 202).
            culprit = f"cursor-valued return type '{node.return_type.name}'"
        elif (
            self._target == "tsql"
            and node.return_type is not None
            and node.return_type.name.upper() == "TABLE"
            and not any(isinstance(s, ReturnStatement) for s in node.body)
        ):
            # A bare RETURNS TABLE needs the inline ``AS RETURN
            # (select)`` form on T-SQL; a body without one has no
            # faithful spelling (wave 224).
            culprit = "RETURNS TABLE without a returnable query body"
        elif self._target == "mysql" and any(
            isinstance(s, DeclareStatement)
            and self._REFCURSOR_TYPE_RE.search(s.data_type.name.strip())
            for s in node.body
        ):
            # MySQL cursors bind to a fixed query at declaration; a
            # refcursor VARIABLE (opened later, dynamically) has no
            # form there (wave 221).
            culprit = "refcursor variable"
        elif "[]" in (
            (node.return_type.name if node.return_type else "")
            + "".join(p.data_type.name for p in node.parameters)
            + "".join(
                s.data_type.name for s in node.body if isinstance(s, DeclareStatement)
            )
        ):
            culprit = "array-typed parameter/return/variable"
        elif self._target != "postgresql" and self._body_builds_arrays(node.body):
            culprit = "ARRAY constructor in the body"
        elif self._target != "postgresql" and self._body_has_paren_cast(node.body):
            culprit = "cast of a parenthesized/composite expression"
        if culprit is None:
            return None
        from unique.core.procedural.emitter import ProceduralEmitter

        original = ProceduralEmitter("postgresql").emit(node)
        reason = (
            f"PostgreSQL {culprit} has no {self._target} equivalent; "
            "the routine is preserved as a comment"
        )
        self._warnings.append(reason)
        self._register_degraded_routine(getattr(node, "name", None))
        return RawSQL(sql=original, reason=reason)

    _ARRAY_CONSTRUCT_RE = re.compile(r"(?i)\bARRAY\s*\[")
    #: ``(expr)::type`` — the simple-operand ANSI rewrite cannot resolve
    #: it, and the target of a ROW cast is a composite anyway.
    _PAREN_CAST_RE = re.compile(r"\)\s*:\s*:\s*\w+")

    def _body_has_paren_cast(self, value: object) -> bool:
        import dataclasses as _dc

        if isinstance(value, str):
            scrubbed = re.sub(r"'(?:[^']|'')*'", "''", value)
            return self._PAREN_CAST_RE.search(scrubbed) is not None
        if _dc.is_dataclass(value) and not isinstance(value, type):
            return any(
                self._body_has_paren_cast(getattr(value, f.name))
                for f in _dc.fields(value)
            )
        if isinstance(value, tuple):
            return any(self._body_has_paren_cast(item) for item in value)
        return False

    def _body_builds_arrays(self, value: object) -> bool:
        """Raw body text building PG arrays — no mechanical form off PG."""
        import dataclasses as _dc

        if isinstance(value, str):
            scrubbed = re.sub(r"'(?:[^']|'')*'", "''", value)
            return self._ARRAY_CONSTRUCT_RE.search(scrubbed) is not None
        if _dc.is_dataclass(value) and not isinstance(value, type):
            return any(
                self._body_builds_arrays(getattr(value, f.name))
                for f in _dc.fields(value)
            )
        if isinstance(value, tuple):
            return any(self._body_builds_arrays(item) for item in value)
        return False

    def _has_dynamic_for(self, value: object) -> bool:
        """A FOR loop whose source is EXECUTE of a NON-literal (real
        dynamic SQL) — no cursor-over-dynamic form off PostgreSQL."""
        if isinstance(value, ForLoopStatement):
            raw = getattr(value.cursor, "sql", "") if value.cursor else ""
            if raw and re.match(r"(?is)^\s*execute\b", raw):
                m = self._FOR_EXECUTE_LITERAL_RE.match(raw)
                if m is None:
                    return True  # variable source: real dynamic SQL
                inner = m.group(1)[1:-1].replace("''", "'").strip()
                if not re.match(r"(?is)^(?:SELECT|VALUES|WITH)\b", inner):
                    return True  # non-query literal (dynamic EXPLAIN …)
        if isinstance(value, ASTNode):
            return any(
                self._has_dynamic_for(getattr(value, f.name))
                for f in dataclasses.fields(value)
            )
        if isinstance(value, tuple):
            return any(self._has_dynamic_for(v) for v in value)
        return False

    def _transform_function(self, node: CreateFunctionStatement) -> ASTNode:
        degraded_uv = self._degrade_mysql_uservar(node)
        if degraded_uv is not None:
            return degraded_uv
        # T-SQL functions cannot access temporary tables (error 2772);
        # a routine creating one inside its body degrades whole (wave 144).
        if self._target == "tsql" and self._source == "postgresql":
            from unique.core.output_gate import scrub
            from unique.core.procedural.emitter import ProceduralEmitter

            original = ProceduralEmitter(self._source).emit(node)
            scrubbed_fn = scrub(original)
            if re.search(r"(?is)\bcreate\s+temp(?:orary)?\s+table\b", scrubbed_fn):
                reason = (
                    "T-SQL functions cannot access temporary tables (2772); "
                    "routine preserved as a comment"
                )
                self._warnings.append(reason)
                self._register_degraded_routine(getattr(node, "name", None))
                return RawSQL(sql=original, reason=reason)
            # A PG function may WRITE; T-SQL functions take no
            # side-effecting DML (error 443) — a writing function IS a
            # procedure semantically, but its callers use it as a value:
            # degrade honestly (wave 230). The body scan skips the
            # CREATE line itself.
            body_only = re.sub(r"(?is)^.*?\bBEGIN\b", "", scrubbed_fn, count=1)
            stays_function = (
                node.return_type is not None
                and node.return_type.name.upper() not in ("VOID", "TRIGGER")
                and not any(p_.direction in ("OUT", "INOUT") for p_ in node.parameters)
            )
            if stays_function and (
                re.search(r"(?is)^\s*(INSERT|UPDATE|DELETE|MERGE)\b", body_only)
                or re.search(r"(?is);\s*(INSERT|UPDATE|DELETE|MERGE)\b", body_only)
            ):
                reason = (
                    "T-SQL functions cannot contain side-effecting DML "
                    "(443); rewrite as a procedure. Routine preserved as "
                    "a comment"
                )
                self._warnings.append(reason)
                self._register_degraded_routine(getattr(node, "name", None))
                return RawSQL(sql=original, reason=reason)
        degraded = self._degrade_record_function(node)
        if degraded is not None:
            return degraded
        folded_fn_body, handler_culprit = self._fold_mysql_handlers(node.body)
        if handler_culprit is not None:
            return self._degrade_for_handler(node, handler_culprit)
        node = dataclasses.replace(node, body=folded_fn_body)
        is_void = (
            node.return_type is not None
            and node.return_type.name.upper() == "VOID"
            and self._target != "postgresql"
        )
        new_params = self._transform_params(node.parameters)
        prev_void = getattr(self, "_in_void_function", False)
        self._in_void_function = is_void
        try:
            new_body = self._transform_body(
                self._drop_param_shadowing_locals(node.body, node.parameters)
            )
        finally:
            self._in_void_function = prev_void
        new_return = (
            self._transform_data_type(node.return_type) if node.return_type else None
        )
        # PG's ``RETURNS void`` has no equivalent: MySQL/T-SQL/Oracle
        # functions must declare AND return a real value. Map to the
        # target's neutral scalar and guarantee a trailing RETURN.
        if is_void:
            new_return = self._void_return_type()
            if not self._ends_with_return(new_body):
                new_body = (
                    *new_body,
                    ReturnStatement(value=self._void_return_value()),
                )
        # A PostgreSQL trigger function (``RETURNS TRIGGER``) is not a
        # general-purpose function; without a trigger-function concept the target
        # can't run it (the emitter documents it). Record the loss.
        is_trigger_fn = (
            node.return_type is not None and node.return_type.name.upper() == "TRIGGER"
        )
        if is_trigger_fn and self._trigger_function_is_inlined(node.name):
            # Its body has been merged into the T-SQL trigger; drop the standalone
            # function rather than leave a redundant carrier comment.
            return CommentStatement(
                text=f"-- UNIQUE: trigger function {node.name} inlined into its "
                "T-SQL trigger",
                style="line",
            )
        if is_trigger_fn and not self._target_supports_delegating_trigger():
            self._warnings.append(
                f"PostgreSQL trigger function {node.name!r} ('RETURNS TRIGGER') "
                f"has no {self._target} equivalent; documented."
            )
        if (
            self._target in ("tsql", "mysql")
            and (is_void or node.return_type is None)
            and any(p.direction in ("OUT", "INOUT") for p in new_params)
        ):
            # Also PG's RETURNS-less form: the return is INFERRED from
            # the OUT params there (``function f1(in i int, out j int)``).
            # T-SQL functions cannot take OUTPUT parameters — and MySQL
            # functions take only IN (wave 201); a void function WITH
            # them IS a procedure on both. The synthesized trailing
            # RETURN 0 is a valid proc status code on T-SQL.
            return CreateProcedureStatement(
                name=self._translate_ident_quoting(node.name) or node.name,
                parameters=new_params,
                body=new_body,
                or_replace=node.or_replace,
                schema=node.schema,
            )
        return CreateFunctionStatement(
            name=self._translate_ident_quoting(node.name) or node.name,
            parameters=new_params,
            return_type=new_return,
            body=new_body,
            or_replace=True if self._target != "tsql" else node.or_replace,
            schema=self._target_schema(node.schema),
        )

    def _transform_trigger(self, node: CreateTriggerStatement) -> ASTNode:
        degraded_uv = self._degrade_mysql_uservar(node)
        if degraded_uv is not None:
            return degraded_uv
        # A BARE whole-row OLD/NEW reference (``'x' + OLD``) has no
        # equivalent off PG — the other engines only address columns
        # (inserted/deleted tables, :NEW.col, NEW.col). Qualified refs
        # and the idiomatic RETURN NEW/OLD are handled; scan scrubbed
        # text so string contents can't false-positive (wave 138).
        if self._target != "postgresql" and self._source == "postgresql":
            from unique.core.output_gate import scrub
            from unique.core.procedural.emitter import ProceduralEmitter

            original = ProceduralEmitter(self._source).emit(node)
            # A PG trigger DELEGATES to a function; the bare row ref
            # lives in the harvested body, not the CREATE TRIGGER shell.
            from unique.core.converter import PG_TRIGGER_FN_BODIES

            bodies = PG_TRIGGER_FN_BODIES.get() or {}
            fn_body = bodies.get(
                (getattr(node, "execute_function", None) or "").lower(), ""
            )
            if re.search(
                r"(?i)(?<!return\s)(?<!\breturns\s)\b(?:old|new)\b"
                r"(?!\s*[.(])(?!\s+table\b)",
                scrub(original + "\n" + fn_body),
            ):
                reason = (
                    f"a whole-row OLD/NEW reference has no {self._target} "
                    "equivalent (rows are addressed per column there); "
                    "routine preserved as a comment"
                )
                self._warnings.append(reason)
                self._register_degraded_routine(getattr(node, "name", None))
                return RawSQL(sql=original, reason=reason)
        # TRUNCATE trigger events exist only on PostgreSQL (wave 125).
        if self._target != "postgresql" and any(
            e.upper() == "TRUNCATE" for e in (node.events or ())
        ):
            reason = (
                f"TRUNCATE trigger events exist only on PostgreSQL (no "
                f"{self._target} equivalent); routine preserved as a comment"
            )
            self._warnings.append(reason)
            self._register_degraded_routine(getattr(node, "name", None))
            from unique.core.procedural.emitter import ProceduralEmitter

            original = ProceduralEmitter(self._source).emit(node)
            return RawSQL(sql=original, reason=reason)
        # An Oracle COMPOUND TRIGGER exists to dodge the mutating-table error
        # (ORA-04091) when re-aggregating a parent row after child rows change.
        # A target without that restriction (PostgreSQL) runs the same
        # aggregation as a plain row-level AFTER trigger that re-reads the table;
        # lower the recognized idiom to it. Targets that either share the
        # restriction (Oracle) or have no equivalent (MySQL) keep a documented
        # carrier.
        if node.compound:
            if self._target_lowers_compound_to_row_level() and node.compound_row_body:
                return self._lower_compound_trigger(node)
            # A statement-level target (T-SQL) expresses the same re-aggregation
            # as an ``inserted``/``deleted`` trigger.
            statement_form = self._lower_compound_for_statement_target(node)
            if statement_form is not None:
                return statement_form
            if self._source != self._target:
                self._warnings.append(
                    f"Oracle COMPOUND TRIGGER {node.name!r} on {node.table} has "
                    f"no automatic {self._target} equivalent (statement-level "
                    "aggregation over a PL/SQL collection); documented."
                )
            return node
        # A row-level trigger (NEW/OLD, per row) has no equivalent on a target
        # whose triggers are only statement-level (T-SQL): rewrite it to a
        # set-based ``inserted``/``deleted`` trigger. Other targets keep it.
        converted = self._rowlevel_trigger_override(node)
        if converted is not None:
            return converted
        # A PostgreSQL trigger delegating to a ``RETURNS TRIGGER`` function is
        # inlined into a T-SQL trigger (which has no separate trigger function).
        if node.execute_function:
            inlined = self._inline_delegating_trigger(node)
            if inlined is not None:
                return inlined
        prev_in_trigger = self._in_trigger
        self._in_trigger = True
        # A purely set-based T-SQL trigger (only FROM/JOIN inserted/deleted, no
        # row-level qualifier or UPDATE(col) predicate) can be rewritten to a
        # target's set-based trigger form (PG transition tables / Oracle compound
        # trigger) instead of being documented. Decide this over the *whole*
        # body before transforming it, and suppress the per-statement
        # documentation while doing so.
        set_based = (
            self._source == "tsql"
            and self._supports_transition_tables()
            and self._is_pure_set_based_trigger(node.body)
        )
        prev_rewrite = self._preserve_set_based_dml
        self._preserve_set_based_dml = set_based
        try:
            new_body = self._transform_body(node.body)
        finally:
            self._in_trigger = prev_in_trigger
            self._preserve_set_based_dml = prev_rewrite
        timing = node.timing
        if self._source == "tsql" and timing == "FOR":
            timing = "AFTER"
        # A PostgreSQL trigger delegating its body to a trigger function
        # (``EXECUTE FUNCTION fn()``) has no equivalent on an engine that inlines
        # the body and lacks statement-level transition tables (MySQL/Oracle/
        # T-SQL): the emitter documents it, and the loss is recorded here.
        if node.execute_function and not self._target_supports_delegating_trigger():
            self._warnings.append(
                f"PostgreSQL trigger {node.name!r} delegates to trigger function "
                f"{node.execute_function}() and has no {self._target} equivalent "
                "(no statement-level transition-table trigger); documented."
            )
        update_of = node.update_of
        if update_of and not self._supports_update_of_columns():
            update_of = ()
            if self._target == "tsql":
                # T-SQL has no UPDATE OF event; the emitter wraps the body in
                # IF UPDATE(c1) OR ... instead (same firing condition).
                update_of = node.update_of
            else:
                self._warnings.append(
                    f"trigger {node.name!r}: UPDATE OF "
                    f"({', '.join(node.update_of)}) has no {self._target} "
                    "form; the trigger now fires on every UPDATE"
                )
        return CreateTriggerStatement(
            name=self._translate_ident_quoting(node.name) or node.name,
            table=self._translate_ident_quoting(node.table) or node.table,
            timing=timing,
            events=node.events,
            for_each="STATEMENT" if set_based else node.for_each,
            body=new_body,
            or_replace=self._trigger_forces_or_replace() or node.or_replace,
            schema=self._target_schema(node.schema),
            set_based_transition=set_based,
            execute_function=node.execute_function,
            referencing=node.referencing,
            update_of=update_of,
        )

    def _supports_update_of_columns(self) -> bool:
        """Whether the target's CREATE TRIGGER takes ``UPDATE OF c1, c2``
        natively (Oracle and PostgreSQL do)."""
        return self._target in ("oracle", "postgresql")

    def _rowlevel_trigger_override(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        """Hook: rewrite a row-level source trigger into the target's own form.
        Only the T-SQL target (statement-level triggers only) overrides this; the
        default keeps the row-level trigger."""
        return None

    def _lower_compound_for_statement_target(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        """Hook: express an Oracle COMPOUND trigger's re-aggregation as a
        statement-level trigger. Only the T-SQL target overrides this."""
        return None

    def _inline_delegating_trigger(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        """Hook: inline a PostgreSQL trigger function's body into the trigger.
        Only the T-SQL target overrides this."""
        return None

    def _trigger_function_is_inlined(self, name: str) -> bool:
        """Whether a ``RETURNS TRIGGER`` function of this name is merged into its
        trigger (so the standalone definition is dropped). True only on T-SQL."""
        return False

    def _target_lowers_compound_to_row_level(self) -> bool:
        """Whether the target can run an Oracle COMPOUND TRIGGER's re-aggregation
        as a plain row-level AFTER trigger. True only where a trigger may re-read
        its own table without the mutating-table error — PostgreSQL. (MySQL also
        allows the re-read but the aggregation is a documented divergence there;
        Oracle shares the restriction and keeps the compound form.)"""
        return self._target == "postgresql"

    def _lower_compound_trigger(
        self, node: CreateTriggerStatement
    ) -> CreateTriggerStatement:
        """Lower a recognized Oracle COMPOUND TRIGGER to a row-level AFTER trigger
        whose body is the AFTER STATEMENT aggregation keyed on the collected
        ``:NEW.<fk>`` (see the parser's ``_compound_row_body``)."""
        prev_in_trigger = self._in_trigger
        self._in_trigger = True
        try:
            new_body = self._transform_body(node.compound_row_body)
        finally:
            self._in_trigger = prev_in_trigger
        return CreateTriggerStatement(
            name=self._translate_ident_quoting(node.name) or node.name,
            table=self._translate_ident_quoting(node.table) or node.table,
            timing="AFTER",
            events=node.events,
            for_each="ROW",
            body=new_body,
            or_replace=self._trigger_forces_or_replace() or node.or_replace,
            schema=self._target_schema(node.schema),
        )

    def _target_supports_delegating_trigger(self) -> bool:
        """Whether the target expresses a trigger whose body lives in a separate
        trigger function (PostgreSQL's ``EXECUTE FUNCTION``). Only PostgreSQL
        does; the others inline the body and document the delegating form."""
        return self._target == "postgresql"

    def _supports_transition_tables(self) -> bool:
        """Whether the target can faithfully express a set-based trigger via
        *named* transition tables matching T-SQL's inserted/deleted. Only
        PostgreSQL can (a statement-level trigger with ``REFERENCING NEW TABLE AS
        inserted OLD TABLE AS deleted``). Oracle has no named transition tables
        (a compound trigger would need a manual PL/SQL collection, not a
        mechanical rewrite), and MySQL has none at all, so both document the
        set-based use instead."""
        return False

    def _is_pure_set_based_trigger(self, body: tuple[ASTNode, ...]) -> bool:
        """A trigger is *purely* set-based when its body references the T-SQL
        ``inserted``/``deleted`` pseudo-tables only via ``FROM``/``JOIN`` (a
        set operation) and never via a row-level column qualifier
        (``inserted.col`` outside FROM) or an ``UPDATE(col)`` predicate. Such a
        trigger maps cleanly onto transition tables; a *mixed* one cannot be a
        single trigger and must stay documented.
        """
        text = self._trigger_body_text(body)
        if not self._PSEUDO_TABLE_SOURCE_RE.search(text):
            return False  # not set-based at all
        if re.search(r"(?i)\bUPDATE\s*\(", text):
            return False  # row-level UPDATE(col) predicate -> mixed
        # A column qualifier that is not the FROM/JOIN source is a row-level use;
        # its presence alongside the set use makes the trigger mixed.
        without_sources = self._PSEUDO_TABLE_SOURCE_RE.sub(" ", text)
        return not re.search(r"(?i)\b(?:inserted|deleted)\s*\.", without_sources)

    def _trigger_body_text(self, body: tuple[ASTNode, ...]) -> str:
        """Flatten a trigger body to the raw SQL text of its statements, for
        set-based/mixed classification (best-effort; recurses into blocks)."""
        parts: list[str] = []

        def walk(node: ASTNode) -> None:
            sql = getattr(node, "sql", None)
            if isinstance(sql, str):
                parts.append(sql)
            # The IF predicate (e.g. UPDATE(col)) lives in `condition`; include
            # it so a row-level predicate marks the trigger as mixed.
            cond = getattr(node, "condition", None)
            if isinstance(cond, ASTNode):
                walk(cond)
            # A cursor's query (DECLARE c CURSOR FOR SELECT ... FROM inserted)
            # is where a set-based pseudo-table read typically lives.
            query = getattr(node, "query", None)
            if isinstance(query, ASTNode):
                walk(query)
            for attr in ("body", "statements", "then_body", "else_body"):
                for child in getattr(node, attr, ()) or ():
                    if isinstance(child, ASTNode):
                        walk(child)

        for stmt in body:
            walk(stmt)
        return "\n".join(parts)

    def _trigger_forces_or_replace(self) -> bool:
        """Whether a CREATE TRIGGER is forced to OR REPLACE on this target. Only
        Oracle does; others keep the source flag."""
        return False

    def _transform_pragma(self, node: PragmaDeclaration) -> ASTNode:
        if self._target != "oracle":
            self._warnings.append(
                f"PRAGMA {node.name} has no {self._target} equivalent; "
                "dropped (documented in a comment)"
            )
        return node

    def _transform_declare(self, node: DeclareStatement) -> ASTNode:
        new_name = self._transform_var_name(node.name)
        if (
            self._target == "oracle"
            and new_name.lower().lstrip("@") in self._param_names
        ):
            # Oracle forbids a local shadowing a parameter (PLS-00410).
            # MySQL's shadowing semantics: the default still sees the
            # parameter; body references after the declare mean the
            # local — the rename preserves both (wave 181).
            new_default_shadow = (
                self._transform_node(node.default) if node.default else None
            )
            renamed = f"uq_{new_name.lstrip('@')}"
            self._var_map[node.name] = renamed
            self._declared_scalar_names.add(renamed.lower())
            new_type_shadow = self._transform_data_type(node.data_type)
            if self._is_string_type(node.data_type):
                self._string_vars.add(renamed)
            return DeclareStatement(
                name=renamed,
                data_type=new_type_shadow,
                default=new_default_shadow,
            )
        self._declared_scalar_names.add(new_name.lower().lstrip("@"))
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
        if self._is_date_type(node.data_type):
            self._date_vars.add(new_name)
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

    _CURSOR_BINDING_RE = re.compile(r"(?is)^\s*CURSOR\b(?:\s+[A-Z_]+)*?\s+FOR\s+(.+)$")

    def _cursor_binding_to_open(self, name: str, value: ASTNode) -> ASTNode | None:
        """Rewrite a T-SQL cursor-variable binding (``SET @c = CURSOR [opts]
        FOR <q>``) into the target's ``OPEN c FOR <q>`` (PL/pgSQL and PL/SQL
        open a ref cursor with its query; the T-SQL cursor options are
        client/storage hints with no counterpart)."""
        if self._target not in ("postgresql", "oracle", "mysql") or not isinstance(
            value, RawSQL
        ):
            return None
        m = self._CURSOR_BINDING_RE.match(value.sql)
        if not m:
            return None
        query = EmbeddedDML(sql=m.group(1).strip(), dialect=self._source)
        if self._target == "mysql":
            # MySQL has no cursor variables: the query belongs on the cursor
            # declaration (hoisted to the DECLARE section; _split_declarations
            # drops the earlier query-less declaration of the same name) and
            # the original bare OPEN stays where it is.
            return self._transform_cursor_decl(
                CursorDeclaration(name=name, query=query)
            )
        bare = self._transform_var_name(name)
        self._cursor_bound_opens.add(bare.lower())
        return self._transform_cursor_op(
            CursorOperation(operation="OPEN", cursor_name=name, query=query)
        )

    #: A value that is ONLY the source's last-identity call.
    _LAST_IDENTITY_ONLY_RE = re.compile(
        r"(?is)^\s*(?:SCOPE_IDENTITY\s*\(\s*\)|@@IDENTITY"
        r"|LASTVAL\s*\(\s*\)|LAST_INSERT_ID\s*\(\s*\))\s*;?\s*$"
    )

    def _last_identity_capture(self, name: str, value: ASTNode) -> ASTNode | None:
        """Oracle has no session-scoped last-identity form: an assignment
        whose value is only that call becomes a LastIdentityCapture node
        (paired with its INSERT later, or emitted as a documented
        fallback)."""
        if self._target != "oracle":
            return None
        if isinstance(value, RawSQL) and self._LAST_IDENTITY_ONLY_RE.match(value.sql):
            return LastIdentityCapture(target=self._transform_var_name(name))
        return None

    def _transform_set_variable(self, node: SetVariableStatement) -> ASTNode:
        bound = self._cursor_binding_to_open(node.name, node.value)
        if bound is not None:
            return bound
        capture = self._last_identity_capture(node.name, node.value)
        if capture is not None:
            return capture
        new_name = self._transform_var_name(node.name)
        new_value = self._transform_node(node.value)
        # SET keeps a SET statement on engines that have one (T-SQL, MySQL);
        # Oracle/PostgreSQL lower it to a ``:=`` assignment.
        if self._uses_set_statement():
            return SetVariableStatement(name=new_name, value=new_value)
        return AssignmentStatement(target=new_name, value=new_value)

    #: MySQL session options that look like plain variables inside a
    #: routine body (``SET sql_mode = …``); assigned cross-dialect they
    #: shipped a fake local (``SET @sql_mode = …`` — wave 162).
    _MYSQL_SESSION_OPTIONS = frozenset(
        {
            "SQL_MODE",
            "AUTOCOMMIT",
            "SQL_SAFE_UPDATES",
            "FOREIGN_KEY_CHECKS",
            "UNIQUE_CHECKS",
            "SQL_LOG_BIN",
            "SQL_NOTES",
            "SQL_WARNINGS",
            "SQL_SELECT_LIMIT",
            "SQL_QUOTE_SHOW_CREATE",
            "TIME_ZONE",
            "MAX_SORT_LENGTH",
            "SORT_BUFFER_SIZE",
            "GROUP_CONCAT_MAX_LEN",
            "DIV_PRECISION_INCREMENT",
            "DEFAULT_STORAGE_ENGINE",
            "OPTIMIZER_SWITCH",
            "CHARACTER_SET_CLIENT",
            "CHARACTER_SET_RESULTS",
            "CHARACTER_SET_CONNECTION",
            "COLLATION_CONNECTION",
        }
    )

    def _transform_assignment(self, node: AssignmentStatement) -> ASTNode:
        if (
            self._source == "mysql"
            and self._target != "mysql"
            and node.target.lstrip("@").upper() in self._MYSQL_SESSION_OPTIONS
        ):
            option = node.target.lstrip("@")
            self._warnings.append(
                f"MySQL session option {option} has no {self._target} "
                "equivalent; statement preserved as a comment"
            )
            value = (
                node.value.sql
                if isinstance(node.value, RawSQL)
                else getattr(node.value, "sql", str(node.value))
            )
            return CommentStatement(
                text=(
                    f"/* UNIQUE: SET {option} = {value} -- {self._source}-only, "
                    f"no {self._target} equivalent */"
                ),
                style="block",
            )
        bound = self._cursor_binding_to_open(node.target, node.value)
        if bound is not None:
            return bound
        capture = self._last_identity_capture(node.target, node.value)
        if capture is not None:
            return capture
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

    def _transform_if(self, node: IfStatement) -> ASTNode:
        new_cond = self._wrap_bare_truth_condition(self._transform_node(node.condition))
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
        new_cond = self._wrap_bare_truth_condition(new_cond)
        new_body = self._ensure_non_empty_body(self._transform_body(node.body))
        return WhileStatement(condition=new_cond, body=new_body)

    def _wrap_bare_truth_condition(self, cond: ASTNode) -> ASTNode:
        """MySQL's control flow takes a numeric truth value (``WHILE x``,
        ``IF level``); every other engine demands a boolean condition
        (PLS-00382 / 42804 — and T-SQL's BIT fixup spelled it ``= 1``,
        silently changing a countdown loop's semantics; waves 184, 188)."""
        if (
            self._source == "mysql"
            and self._target != "mysql"
            and isinstance(cond, RawSQL)
            and re.fullmatch(r"\s*@?\w+\s*", cond.sql)
            and not re.fullmatch(r"(?i)\s*(TRUE|FALSE)\s*", cond.sql)
        ):
            return dataclasses.replace(cond, sql=f"{cond.sql.strip()} <> 0")
        return cond

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
        return TryCatchBlock(
            try_body=new_try, catch_body=new_catch, catch_kind=node.catch_kind
        )

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

    _CONSTANT_SQL_STRING_RE = re.compile(r"(?s)^\s*N?'((?:[^']|'')*)'\s*$")

    def _transform_execute(self, node: ExecuteStatement) -> ASTNode:
        expr = node.sql_expression
        # EXECUTE IMMEDIATE of a *constant* string is just that statement:
        # unwrap it and route it through the normal DML pipeline (dynamic
        # SQL leaks the source dialect verbatim otherwise, and PostgreSQL
        # has no top-level EXECUTE '<sql>' form at all).
        if (
            self._source != self._target
            and node.immediate
            and not node.into_vars
            and not node.params
            and isinstance(expr, RawSQL)
        ):
            m = self._CONSTANT_SQL_STRING_RE.match(expr.sql)
            if m:
                inner = m.group(1).replace("''", "'").strip()
                if inner and re.match(
                    r"(?is)\s*CREATE\s+(?:OR\s+REPLACE\s+)?"
                    r"(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b",
                    inner,
                ):
                    # Routine DDL cannot be inlined: neither PG nor T-SQL
                    # allows CREATE PROCEDURE/FUNCTION inside a block — it
                    # must STAY dynamic. The string still holds the source
                    # dialect's routine text; converting a whole routine
                    # through the string layer is manual work.
                    self._warnings.append(
                        "dynamic routine DDL (EXECUTE of a constant CREATE "
                        "PROCEDURE/FUNCTION/TRIGGER string) kept verbatim; "
                        "convert the routine text manually"
                    )
                elif inner:
                    return self._transform_node(
                        EmbeddedDML(sql=inner, dialect=self._source)
                    )
        op = self._named_arg_op()
        if op and isinstance(expr, RawSQL):
            # A T-SQL ``EXEC proc @param = value`` uses named-parameter syntax;
            # Oracle/PostgreSQL spell it ``proc(param => value)``. Convert the LHS
            # parameter names (dropping the ``@`` sigil) *before* the generic
            # ``@var → V_var`` rename mangles them into local-variable names; an
            # RHS variable value keeps its own transformation.
            rewritten = re.sub(r"@(\w+)\s*=(?![=>])\s*", rf"\1 {op} ", expr.sql)
            expr = RawSQL(sql=rewritten, reason=expr.reason)
        new_expr = self._transform_node(expr)
        new_params = tuple(self._transform_node(p) for p in node.params)
        return ExecuteStatement(
            sql_expression=new_expr,
            params=new_params,
            immediate=node.immediate,
            into_vars=tuple(self._transform_var_name(v) for v in node.into_vars),
        )

    def _named_arg_op(self) -> str | None:
        """The named-argument operator in a procedure call, or ``None`` when the
        target has no named-argument syntax. Oracle/PostgreSQL use ``=>``; T-SQL
        keeps ``@name = value`` and MySQL's CALL is positional-only."""
        return None

    def _supports_top_level_anonymous_block(self) -> bool:
        """Whether the target can run a wrapped anonymous procedural block at the
        top level. Default yes (Oracle/PostgreSQL/T-SQL); MySQL overrides to no
        (it has no procedural code outside a stored routine)."""
        return True

    #: Oracle built-in package prefixes: calls into them have no counterpart
    #: on other engines (DBMS_SCHEDULER.CREATE_JOB, UTL_FILE, …).
    _ORACLE_PACKAGE_RE = re.compile(r"(?i)^(?:DBMS_|UTL_|CTX_|APEX_|OWA_)")

    def _transform_call(self, node: CallStatement) -> ASTNode:
        """Transform a stored-procedure call. The ``dbo`` default schema is
        meaningful only on T-SQL, so drop it for the other targets; the argument
        text gets the same niladic-now / string fixups as embedded DML."""
        degraded_uv = self._degrade_mysql_uservar(node)
        if degraded_uv is not None:
            return degraded_uv
        from unique.core.converter import DEGRADED_ROUTINES, REFCURSOR_PROCS

        registry = DEGRADED_ROUTINES.get() or set()
        callee = node.name.split(".")[-1].strip('`"[]').lower()
        rc_procs = REFCURSOR_PROCS.get() or {}
        if self._target == "oracle" and callee in rc_procs:
            # The converted signature gained SYS_REFCURSOR OUT params;
            # adapt the call with local cursor variables.
            n = rc_procs[callee]
            names = [f"uq_rc{i + 1}" for i in range(n)]
            decls = "\n".join(f"    {c} SYS_REFCURSOR;" for c in names)
            args = node.args.strip()
            all_args = ", ".join(filter(None, [args, ", ".join(names)]))
            return RawSQL(
                sql=(
                    f"DECLARE\n{decls}\nBEGIN\n" f"    {node.name}({all_args});\nEND;"
                ),
                reason="refcursor call-site adapter",
            )
        if callee in registry:
            reason = (
                f"CALL of routine {node.name} whose definition could not be "
                "converted; statement preserved as a comment"
            )
            self._warnings.append(reason)
            from unique.core.procedural.emitter import ProceduralEmitter

            original = ProceduralEmitter(self._source).emit(node)
            return RawSQL(sql=original, reason=reason)
        # An Oracle built-in package call shipped raw is a guaranteed runtime
        # error off Oracle (audit D10: DBMS_SCHEDULER.CREATE_JOB became a raw
        # CALL on PostgreSQL, unwarned). Preserve it as a documented carrier.
        if (
            self._source == "oracle"
            and self._target != "oracle"
            and node.schema
            and self._ORACLE_PACKAGE_RE.match(node.schema)
        ):
            original = f"{node.schema}.{node.name}({node.args})"
            self._warnings.append(
                f"Oracle package call {node.schema}.{node.name} has no "
                f"{self._target} equivalent; preserved as a comment"
            )
            commented = "\n".join(f"-- {ln}" for ln in original.splitlines())
            return RawSQL(
                sql=(
                    "-- UNIQUE: Oracle package call has no "
                    f"{self._target} equivalent; original:\n{commented}\n"
                    f"{self._noop_sql()}"
                ),
                reason="oracle package call",
            )
        schema = self._target_schema(node.schema)
        args = node.args
        if args:
            if self._source == "oracle" and self._in_trigger:
                # :NEW./:OLD. row references in the argument list map to the
                # target's row qualifier like everywhere else in the body.
                args = self._normalize_oracle_pseudorecords(args)
            args = self._transform_call_args(args)
            args = self._expr._map_now_in_sql(args)
        return CallStatement(name=node.name, args=args, schema=schema)

    def _transform_call_args(self, args: str) -> str:
        """Rename variables in a call's argument list — but never the LHS of
        a named association (``V_ID => value``): that is the callee's
        parameter name, not a local (a same-named local otherwise turned
        ``V_ID =>`` into ``@id =>`` and the T-SQL spelling into ``@@id``)."""
        from unique.core.sql_split import split_top_level_commas

        parts = []
        for part in split_top_level_commas(args):
            m = re.match(r"(?s)^(\s*\w+\s*=>\s*)(.*)$", part)
            if m:
                parts.append(m.group(1) + self._transform_var_in_sql(m.group(2)))
            else:
                parts.append(self._transform_var_in_sql(part))
        return ", ".join(p.strip() for p in parts)

    #: Oracle data-dictionary views (USER_*/ALL_*/DBA_*). A block querying them
    #: (a catalog-driven re-runnable DROP guard) has no portable equivalent —
    #: the views don't exist on any other engine, so even a valid DO $$ block
    #: fails at runtime.
    _ORACLE_CATALOG_RE = re.compile(
        r"(?i)\b(?:user|all|dba)_(?:tab|obj|col|con|ind|seq|view|trigger|source|proc)\w*\b"
    )

    def _references_oracle_catalog(self, statements: tuple[ASTNode, ...]) -> bool:
        """Whether any statement (recursively) queries an Oracle data-dictionary
        view — detected on the raw SQL text carried by RawSQL / EmbeddedDML /
        FOR-loop cursors."""

        def walk(node: ASTNode) -> bool:
            text = getattr(node, "sql", None)
            if isinstance(text, str) and self._ORACLE_CATALOG_RE.search(text):
                return True
            for attr in ("cursor", "query", "sql_expression", "value", "condition"):
                child = getattr(node, attr, None)
                if isinstance(child, ASTNode) and walk(child):
                    return True
            for attr in ("statements", "body", "then_body", "else_body", "params"):
                for child in getattr(node, attr, ()) or ():
                    if isinstance(child, ASTNode) and walk(child):
                        return True
            return False

        return any(walk(s) for s in statements)

    def _transform_anonymous_block(self, node: AnonymousBlock) -> ASTNode:
        degraded_uv = self._degrade_mysql_uservar(node)
        if degraded_uv is not None:
            return degraded_uv
        new_stmts = self._transform_body(node.statements)
        if new_stmts and all(
            isinstance(s, RawSQL) and "preserved as a comment" in s.reason
            for s in new_stmts
        ):
            # Every statement degraded: wrapping comment-only carriers in
            # BEGIN/END ships an empty block (PLS-00103 / error 156).
            if len(new_stmts) == 1:
                return new_stmts[0]
            first = new_stmts[0]
            assert isinstance(first, RawSQL)
            return RawSQL(
                sql="\n".join(s.sql for s in new_stmts if isinstance(s, RawSQL)),
                reason=first.reason,
            )
        if (
            self._source == "oracle"
            and self._target != "oracle"
            and self._references_oracle_catalog(node.statements)
        ):
            # A catalog-driven DROP guard: valid syntax on the target (PG DO $$)
            # but its USER_*/ALL_* views don't exist there, so it can't run.
            # Document it (the harness recreates a clean schema itself).
            self._warnings.append(
                "Oracle anonymous block querying the data dictionary "
                f"(USER_*/ALL_* views) has no {self._target} equivalent; "
                "preserved as a comment."
            )
            return AnonymousBlock(statements=new_stmts, degraded=True)
        needs_wrapper = needs_procedural_wrapper(new_stmts)
        if needs_wrapper and not self._supports_top_level_anonymous_block():
            # No faithful top-level form on this target: document the loss in the
            # result object and emit the block as a carrier comment, never as
            # invalid executable SQL.
            self._warnings.append(
                f"{self._source} anonymous PL/SQL block with control flow has no "
                f"top-level {self._target} equivalent (no procedural code outside "
                "a stored routine); preserved as a comment."
            )
            return AnonymousBlock(statements=new_stmts, degraded=True)
        return AnonymousBlock(statements=new_stmts, degraded=node.degraded)

    def _transform_print(self, node: PrintStatement) -> PrintStatement:
        return PrintStatement(expression=self._transform_node(node.expression))

    def _transform_raise_error(self, node: RaiseErrorStatement) -> ASTNode:
        new_msg = self._transform_node(node.message) if node.message else None
        # replace, not reconstruction (a rebuild drops reraise — wave 118's
        # field-eating lesson, hit again on wave 119's first run).
        return dataclasses.replace(node, message=new_msg)

    #: GET DIAGNOSTICS item -> target expression (None = no equivalent,
    #: the item degrades to a carrier line). MySQL keeps condition items
    #: native (GET STACKED DIAGNOSTICS CONDITION 1 …).
    _DIAG_ITEMS: dict[str, dict[str, str | None]] = {
        "oracle": {
            "ROW_COUNT": "SQL%ROWCOUNT",
            "MESSAGE_TEXT": "SQLERRM",
            "RETURNED_SQLSTATE": "TO_CHAR(SQLCODE)",
            "PG_EXCEPTION_CONTEXT": "DBMS_UTILITY.FORMAT_ERROR_BACKTRACE",
            "PG_CONTEXT": "DBMS_UTILITY.FORMAT_ERROR_BACKTRACE",
        },
        "tsql": {
            "ROW_COUNT": "@@ROWCOUNT",
            "MESSAGE_TEXT": "ERROR_MESSAGE()",
            "RETURNED_SQLSTATE": "CAST(ERROR_STATE() AS NVARCHAR(5))",
            "PG_EXCEPTION_CONTEXT": (
                "CONCAT(ERROR_PROCEDURE(), ' line ', ERROR_LINE())"
            ),
            "PG_CONTEXT": "CONCAT(ERROR_PROCEDURE(), ' line ', ERROR_LINE())",
        },
        "mysql": {
            "ROW_COUNT": "ROW_COUNT()",
        },
    }

    def _transform_get_diagnostics(self, node: GetDiagnosticsStatement) -> ASTNode:
        """PG/MySQL keep the native GET DIAGNOSTICS; Oracle/T-SQL become
        plain assignments through the existing emitters. Items with no
        equivalent degrade to a carrier line with a warning."""
        if self._target == "postgresql":
            return node
        table = self._DIAG_ITEMS.get(self._target, {})
        out: list[ASTNode] = []
        native_items: list[tuple[str, str]] = []
        for var, item in node.items:
            new_var = self._transform_var_name(var)
            expr = table.get(item)
            if expr is not None:
                if item == "RETURNED_SQLSTATE":
                    self._warnings.append(
                        "RETURNED_SQLSTATE mapped to the target's error "
                        "code/state — different value domain"
                    )
                out.append(
                    AssignmentStatement(
                        target=new_var,
                        value=RawSQL(sql=expr, reason="expression"),
                    )
                )
            elif self._target == "mysql" and item in (
                "MESSAGE_TEXT",
                "RETURNED_SQLSTATE",
                "CLASS_ORIGIN",
                "SUBCLASS_ORIGIN",
            ):
                native_items.append((new_var, item))
            else:
                reason = (
                    f"GET DIAGNOSTICS item {item} has no {self._target} "
                    "equivalent; preserved as a comment"
                )
                self._warnings.append(reason)
                out.append(
                    RawSQL(sql=f"GET DIAGNOSTICS {var} = {item};", reason=reason)
                )
        if native_items:
            out.append(GetDiagnosticsStatement(items=tuple(native_items), stacked=True))
        if len(out) == 1:
            return out[0]
        from unique.core.ast_nodes import StatementList

        return StatementList(statements=tuple(out))

    def _transform_perform(self, node: PerformStatement) -> ASTNode:
        """PERFORM with a FROM tail (multi-row discard, side-effect
        scans) has no mechanical equivalent off PG — degrade with a
        warning; the expression form flows to the emitters' discard
        idiom."""
        expr = self._transform_node(node.expression) if node.expression else None
        raw = getattr(expr, "sql", "") if expr is not None else ""
        if self._target != "postgresql" and re.search(
            r"(?is)\bFROM\b", self._strip_strings(raw)
        ):
            reason = (
                f"PERFORM over a FROM clause has no {self._target} "
                "equivalent (multi-row discard); preserved as a comment"
            )
            self._warnings.append(reason)
            return RawSQL(sql=f"PERFORM {raw};", reason=reason)
        return PerformStatement(expression=expr)

    @classmethod
    def _line_comments_to_block(cls, sql: str) -> str:
        """Convert ``-- text`` line comments to inline ``/* text */`` blocks.

        Applied to IR-emitted expression fragments (they may be joined onto
        one line downstream). ``-- UNIQUE:`` carrier lines are left alone —
        the no-silent-loss gates match on exactly that spelling.
        """
        if "--" not in sql:
            return sql

        def sub(segment: str) -> str:
            def repl(m: re.Match[str]) -> str:
                body = m.group(1).strip()
                if body.upper().startswith("UNIQUE:"):
                    return m.group(0)
                body = body.replace("*/", "* /")
                return f"/* {body} */" if body else "/* */"

            return re.sub(r"--([^\n]*)", repl, segment)

        return cls._map_outside_strings(sql, sub)

    @staticmethod
    def _strip_strings(sql: str) -> str:
        return re.sub(r"'(?:[^']|'')*'", "''", sql)

    def _transform_return(self, node: ReturnStatement) -> ReturnStatement:
        new_value = self._transform_node(node.value) if node.value else None
        if new_value is None and getattr(self, "_in_void_function", False):
            # A bare ``RETURN;`` is invalid in a MySQL/T-SQL/Oracle
            # function; the void mapping gives it the neutral value.
            new_value = self._void_return_value()
        return ReturnStatement(value=new_value)

    def _transform_cursor_decl(self, node: CursorDeclaration) -> CursorDeclaration:
        new_name = self._transform_var_name(node.name)
        new_query = self._transform_node(node.query) if node.query else None
        # parameters must ride along (the field existed but was dropped
        # here — latent silent loss found by the wave-32 analysis pass).
        new_params = tuple(
            ParameterDefinition(
                name=p.name,
                data_type=self._transform_data_type(p.data_type),
                direction=p.direction,
                default=p.default,
            )
            for p in node.parameters
        )
        # dataclasses.replace, not reconstruction: a rebuild silently drops
        # fields this method does not know about (scroll — wave 118).
        return dataclasses.replace(
            node, name=new_name, query=new_query, parameters=new_params
        )

    def _transform_cursor_op(self, node: CursorOperation) -> ASTNode:
        new_name = self._transform_var_name(node.cursor_name)
        new_args = self._transform_var_in_sql(node.args) if node.args else ""
        bare = new_name.lower().lstrip("@").lstrip(":")
        if bare in self._dropped_cursor_params:
            if node.operation.upper() == "OPEN" and node.query is not None:
                # The ref-cursor's query IS the procedure's result set.
                return self._transform_node(node.query)
            # CLOSE/FETCH on a dropped cursor have nothing to act on.
            return NullStatement()
        if node.operation.upper() == "FETCH":
            self._last_fetch_cursor = new_name
        if (
            node.operation.upper() == "OPEN"
            and node.query is None
            and new_name.lower().lstrip("@")
            in {n.lstrip("@") for n in self._cursor_bound_opens}
        ):
            # Already opened at the binding site (SET @c = CURSOR ... FOR).
            return NullStatement()
        new_into = tuple(self._transform_var_name(v) for v in node.into_vars)
        new_query = self._transform_node(node.query) if node.query else None
        # dataclasses.replace, not reconstruction (drops scroll/direction).
        return dataclasses.replace(
            node,
            cursor_name=new_name,
            into_vars=new_into,
            query=new_query,
            args=new_args,
        )

    _FOR_EXECUTE_LITERAL_RE = re.compile(r"(?is)^\s*execute\s+('(?:[^']|'')*')\s*$")

    def _transform_for_loop(self, node: ForLoopStatement) -> ASTNode:
        self._warn_for_loop_unsupported()
        # FOR v IN EXECUTE <source>: with a LITERAL string the EXECUTE is
        # unnecessary (the dollar-quote lexing already made it a plain
        # literal) — inline the query, faithful everywhere. A variable
        # source is real dynamic SQL: no cursor-over-dynamic form off PG.
        cursor = node.cursor
        raw = getattr(cursor, "sql", "") if cursor is not None else ""
        if raw and self._target != "postgresql":
            m = self._FOR_EXECUTE_LITERAL_RE.match(raw)
            if m:
                inner = m.group(1)[1:-1].replace("''", "'").strip()
                # only a QUERY literal can inline as a cursor source; a
                # non-query (dynamic EXPLAIN — engine introspection) is
                # caught by the whole-routine degrade scan.
                if re.match(r"(?is)^(?:SELECT|VALUES|WITH)\b", inner):
                    cursor = RawSQL(sql=inner, reason="expression")
            # a variable EXECUTE source is caught by the whole-routine
            # degrade scan before the transform reaches this point
        node = ForLoopStatement(
            variable=node.variable,
            range_start=node.range_start,
            range_end=node.range_end,
            cursor=cursor,
            body=node.body,
            reverse=node.reverse,
        )
        new_body = self._ensure_non_empty_body(self._transform_body(node.body))
        new_cursor = self._transform_node(node.cursor) if node.cursor else None
        return ForLoopStatement(
            variable=node.variable,
            range_start=node.range_start,
            range_end=node.range_end,
            cursor=new_cursor,
            body=new_body,
            reverse=node.reverse,
        )

    def _warn_for_loop_unsupported(self) -> None:
        """Hook for targets with no native FOR loop to record a warning. Default
        does nothing; T-SQL overrides."""

    def _transform_foreach(self, node: ForeachStatement) -> ASTNode:
        # replace, not reconstruction (the field-eating lesson).
        return dataclasses.replace(
            node,
            variable=self._transform_var_name(node.variable),
            array_expr=self._transform_var_in_sql(node.array_expr),
            body=self._transform_body(node.body),
        )

    def _transform_loop(self, node: LoopStatement) -> ASTNode:
        """Default keeps an unconditional LOOP (Oracle/PG/MySQL); T-SQL
        overrides to a ``WHILE 1=1`` (it has no bare LOOP)."""
        return LoopStatement(
            body=self._ensure_non_empty_body(self._transform_body(node.body)),
            label=node.label,
        )

    def _transform_exit(self, node: ExitStatement) -> ASTNode:
        # Keep the ExitStatement (with its condition) so the emitter can
        # produce the dialect-correct form (e.g. T-SQL: IF <cond> BREAK).
        new_cond = self._transform_node(node.condition) if node.condition else None
        return ExitStatement(condition=new_cond, label=node.label)

    def _transform_select_into(self, node: SelectIntoStatement) -> ASTNode:
        """Transform SELECT INTO, adjusting variables and the embedded SQL."""
        into_vars = node.into_vars
        if self._source == "oracle" and self._in_trigger:
            # :NEW./:OLD. row references (in the INTO targets and the
            # FROM/WHERE tail) map to the target's row qualifier.
            into_vars = tuple(
                self._normalize_oracle_pseudorecords(v) for v in into_vars
            )
        new_into = tuple(
            v if re.match(r"(?i)^(?:NEW|OLD)\s*\.", v) else self._transform_var_name(v)
            for v in into_vars
        )
        # Transform the select list and rest via variable + function mapping
        new_cols = tuple(self._transform_node(c) for c in node.columns)
        rest_src = node.rest_sql
        if self._source == "oracle" and self._in_trigger:
            rest_src = self._normalize_oracle_pseudorecords(rest_src)
        rest = self._transform_var_in_sql(rest_src)
        rest = self._expr._transform_functions_in_sql(rest)
        rest = self._fix_select_into_rest(rest)
        with_sql = node.with_sql
        if with_sql:
            with_sql = self._transpile_cte_prefix(self._transform_var_in_sql(with_sql))
            if self._target != "tsql":
                with_sql = self._strip_tsql_table_hints(with_sql)
        return SelectIntoStatement(
            columns=new_cols,
            into_vars=new_into,
            from_clause=node.from_clause,
            where=node.where,
            rest_sql=rest,
            tsql_assignment=node.tsql_assignment,
            with_sql=with_sql,
        )

    _TSQL_TABLE_HINT_RE = re.compile(
        r"(?i)\s+WITH\s*\(\s*(?:NOLOCK|UPDLOCK|HOLDLOCK|ROWLOCK|READPAST|"
        r"TABLOCKX?|XLOCK|PAGLOCK|READUNCOMMITTED|READCOMMITTED(?:LOCK)?|"
        r"REPEATABLEREAD|SERIALIZABLE|SNAPSHOT|FORCESEEK|FORCESCAN|NOWAIT|"
        r"INDEX\s*\([^)]*\))(?:\s*,\s*(?:NOLOCK|UPDLOCK|HOLDLOCK|ROWLOCK|"
        r"READPAST|TABLOCKX?|XLOCK|PAGLOCK|READUNCOMMITTED|"
        r"READCOMMITTED(?:LOCK)?|REPEATABLEREAD|SERIALIZABLE|SNAPSHOT|"
        r"FORCESEEK|FORCESCAN|NOWAIT|INDEX\s*\([^)]*\)))*\s*\)"
    )

    def _strip_tsql_table_hints(self, sql: str) -> str:
        """Drop T-SQL table hints (``WITH (UPDLOCK, HOLDLOCK)``) that sqlglot
        writers other than PG/Oracle leave in place — locking hints have no
        cross-engine equivalent (each engine locks via its own isolation)."""
        return self._TSQL_TABLE_HINT_RE.sub("", sql)

    def _transpile_cte_prefix(self, with_sql: str) -> str:
        """Translate a captured CTE clause to the target dialect by giving
        sqlglot a complete statement (``<ctes> SELECT 1``) and stripping the
        probe back off — table hints, T-SQL aliases (``n = expr``), CONVERT
        and string ``+`` inside the CTE bodies are all handled there."""
        if self._source == self._target:
            return with_sql
        probe = f"{with_sql} SELECT 1"
        try:
            out = sqlglot.transpile(
                probe,
                read=self._get_sqlglot_dialect(self._source),
                write=self._get_sqlglot_dialect(self._target),
                error_level=sqlglot.ErrorLevel.RAISE,
            )[0]
        except Exception:  # noqa: BLE001 - keep the original on any failure
            return with_sql
        # The per-target expression fixups (string '+', dbo., TOP) parse their
        # input as a full statement — run them while the probe still makes
        # this one, then strip the probe.
        out = self._fix_raw_sql_target(out)
        m = re.search(r"(?is)\s*SELECT\s+1\s*;?\s*$", out)
        return out[: m.start()].strip() if m else with_sql

    def _fix_oracle_dml(self, sql: str) -> str:
        """Post-process sqlglot Oracle output to correct unsupported constructs."""
        sql = self._expr._replace_oracle_date_add(sql)
        # Oracle has no string ``+``; a chain with a string operand must use ``||``
        # (PLS-00306 otherwise). sqlglot leaves ``+`` since it can't tell concat
        # from arithmetic without type info — do it here as for PostgreSQL/MySQL.
        sql = self._expr._rewrite_string_concat(sql, "oracle")
        # Strip T-SQL RECOMPILE query hint that sqlglot leaves in Oracle output
        sql = re.sub(r"\s+RECOMPILE\b", "", sql, flags=re.IGNORECASE)
        if self._in_trigger:
            sql = self._expr._to_oracle_row_ref(sql)
        # Last: _rewrite_string_concat re-parses through sqlglot, which re-adds an
        # ``AS`` before a subquery's table alias — so run the spelling fixes after.
        sql = self._expr._oracle_function_fixes(sql)
        return sql

    def _transform_embedded_dml(self, node: EmbeddedDML) -> EmbeddedDML:
        """Transform embedded DML using sqlglot.

        A cross-table ``UPDATE ... FROM ... JOIN`` is routed through the IR
        converter/emitter instead, because sqlglot leaves it in the invalid
        T-SQL ``UPDATE alias SET alias.col ... FROM tbl alias JOIN ...`` shape on
        the other engines; the IR emitter renders each engine's idiomatic form.
        """
        sql = self._transform_var_in_sql(node.sql)
        # Oracle's ``:NEW.``/``:OLD.`` pseudo-records must be normalized to the
        # target's row qualifier *before* sqlglot, which would otherwise read
        # ``:NEW`` as a bind placeholder and emit ``%(NEW)s`` for PostgreSQL.
        if self._source == "oracle":
            sql = self._normalize_oracle_pseudorecords(sql)
        # ``INSERT … RETURNING <col> INTO <var>`` captures a generated id. MySQL
        # has no RETURNING, and sqlglot drops the ``INTO <var>`` target, so peel
        # the capture off first and re-express it as ``SET <var> =
        # LAST_INSERT_ID()`` after the INSERT (faithful id capture, not a
        # silently dropped assignment).
        sql, capture_suffix = self._peel_returning_capture(sql)
        rewritten = self._transform_cross_table_update(sql)
        if rewritten is not None:
            sql = rewritten
            # The IR-emitted UPDATE bypasses _fix_target_dml; still apply the
            # Oracle spelling fixes (e.g. AS before a subquery's table alias).
            if self._target == "oracle":
                sql = self._expr._oracle_function_fixes(sql)
            if self._in_trigger and self._rewrites_trigger_pseudotables():
                sql = self._rewrite_trigger_pseudotables(sql)
            return EmbeddedDML(sql=sql + capture_suffix, dialect=self._target)
        # Primary path (audit doc-04 P4 / M3): the same parse → transform →
        # emit IR pipeline standalone DML uses, so both pipelines share ONE
        # mapping engine. Raw sqlglot below remains only as a warned fallback
        # for statements the IR cannot model yet.
        ir_sql = self._ir_transpile_dml(sql)
        if ir_sql is not None:
            sql = self._fix_ir_dml(ir_sql)
            if self._target == "oracle":
                # A MySQL/PostgreSQL-source trigger's NEW./OLD. row reference
                # must become Oracle's :NEW./:OLD. (as on the fallback path).
                if self._in_trigger:
                    sql = self._expr._to_oracle_row_ref(sql)
                sql = self._expr._oracle_function_fixes(sql)
            if self._in_trigger and self._rewrites_trigger_pseudotables():
                sql = self._rewrite_trigger_pseudotables(sql)
            return EmbeddedDML(sql=sql + capture_suffix, dialect=self._target)
        self._warnings.append(
            "Embedded DML not modeled by the IR converter; converted with raw "
            "sqlglot (review the statement)"
        )
        try:
            source_dialect = self._get_sqlglot_dialect(self._source)
            target_dialect = self._get_sqlglot_dialect(self._target)
            # Pretty-print only long embedded DML (a result-set SELECT with many
            # columns/joins, a wide UPDATE): a one-liner of 2 000+ chars is
            # unreadable, while a short statement reads best on one line. The
            # emitter indents each output line by the block level, so the
            # multi-line form stays aligned with the surrounding procedural code.
            results = sqlglot.transpile(
                sql,
                read=source_dialect,
                write=target_dialect,
                error_level=sqlglot.ErrorLevel.WARN,
                pretty=len(sql) > 200,
            )
            # WARN keeps partially-parsed trees usable (a hard RAISE leaves
            # source-dialect text in the output), but a partial tree can
            # CORRUPT the statement: an INSERT whose SELECT failed to parse
            # re-emits as INSERT ... DEFAULT VALUES. Detect that signature
            # and keep the original text (warned) instead.
            if results:
                corrupted = re.search(
                    r"(?i)\bDEFAULT\s+VALUES\s*;?\s*$", results[0]
                ) and not re.search(r"(?i)\bDEFAULT\s+VALUES\b", sql)
                if corrupted:
                    self._warnings.append(
                        "embedded INSERT lost its source rows in a partial "
                        "parse; original statement preserved (review)"
                    )
                else:
                    sql = results[0]
        except Exception as e:
            logger.debug("sqlglot transpile failed for DML: %s", e)
            self._warnings.append(f"Could not transpile DML: {e}")
        # 0/1 literals written to a BIT column must become booleans on
        # PostgreSQL (the standalone-DML emitter does the same).
        from unique.core.converter import coerce_bit_literals_in_sql

        sql = coerce_bit_literals_in_sql(sql, self._target)
        # sqlglot passes Oracle SYSTIMESTAMP through as an invalid SYSTIMESTAMP()
        # on the other engines; map any niladic "now" spelling to the target's.
        sql = self._expr._map_now_in_sql(sql)
        sql = self._fix_target_dml(sql)
        if self._in_trigger and self._rewrites_trigger_pseudotables():
            sql = self._rewrite_trigger_pseudotables(sql)
        return EmbeddedDML(sql=sql + capture_suffix, dialect=self._target)

    def _peel_returning_capture(self, sql: str) -> tuple[str, str]:
        """Split an ``INSERT … RETURNING <col> INTO <var>`` into the base
        statement and a target-appropriate id-capture suffix.

        sqlglot silently drops the ``INTO <var>`` target, so it must be peeled
        off before transpiling and re-expressed:

        - MySQL/T-SQL have no ``RETURNING … INTO``; capture the id with
          ``SET <var> = LAST_INSERT_ID()`` / ``SCOPE_IDENTITY()`` after the
          INSERT (T-SQL's ``OUTPUT … INTO`` needs a *table* variable, not the
          scalar the source declared).
        - Oracle/PostgreSQL support ``RETURNING … INTO`` natively; re-append it
          to the (transpiled) INSERT so the target is not lost (ORA-00925).

        Returns ``(sql, suffix)``; ``suffix`` is empty when nothing is peeled.
        """
        m = re.search(r"(?is)\bRETURNING\b\s+(.+?)\s+INTO\s+(@?[\w.]+)\s*;?\s*$", sql)
        if not m:
            return sql, ""
        cols, var = m.group(1).strip(), m.group(2)
        base = sql[: m.start()].rstrip().rstrip(";").rstrip()
        if self._target in ("mysql", "tsql"):
            return base, f";\nSET {var} = {LAST_IDENTITY_EXPR[self._target]};"
        if self._target in ("oracle", "postgresql"):
            return base, f" RETURNING {cols} INTO {var}"
        return sql, ""

    def _ir_transpile_dml(self, sql: str) -> str | None:
        """Transpile one embedded DML statement through the shared IR pipeline.

        This is the same ``parse_sql → Transformer → emit_node`` path that
        standalone DML takes (audit doc-04 P4): one mapping engine, two
        callers — so a mapping added for standalone DML applies inside routine
        bodies by construction, and vice versa.

        Returns None when the IR cannot faithfully model the statement (parse
        failure, unmodeled construct, or emit error), so the caller falls back
        to the warned raw-sqlglot path.
        """
        if self._source == self._target:
            return None
        from unique.core import converter as _conv

        if self._source == "oracle":
            # Oracle's ALTER ... MODIFY parses as an opaque Command in
            # sqlglot; the shared rewriter owns the per-target form.
            modified = _conv.rewrite_oracle_modify(sql.strip(), self._target)
            if modified is not None:
                return modified

        # A function call in FROM/JOIN position (table-valued function) has
        # curated per-target handling on the fallback path (JSON_TABLE
        # rewrite, documented carrier); the IR does not model it.
        if self._function_relation_names(sql, self._source):
            return None
        # Publish the routine's declared variable types so the shared
        # converter can classify a T-SQL ``+`` over bare variables (the raw
        # path reads self._string_vars; the IR needs the same knowledge —
        # M3-prereq: the IR gains procedural context). Covers every exit.
        str_token = _conv.STRING_VARIABLES.set(
            frozenset(v.lstrip("@").lower() for v in self._string_vars)
        )
        date_token = _conv.DATE_VARIABLES.set(
            frozenset(v.lstrip("@").lower() for v in self._date_vars)
        )
        # The source dialect drives shared-map lookups (pair renames,
        # source-owned globals). The transpiler publishes it per run; set it
        # here too so direct IR calls (tests, tools) see the same context.
        src_token = _conv.SOURCE_DIALECT.set(self._source)
        # Cursor state for @@FETCH_STATUS comparisons (M3 precondition (a)).
        # Guarded on the token so MySQL's form lookup (which flags the
        # NOT FOUND handler injection) only fires when the idiom is present.
        fetch_token = _conv.FETCH_STATUS_FORMS.set(
            self._fetch_status_forms() if "@@FETCH_STATUS" in sql.upper() else None
        )
        # Embedded text is mid-transform (variables already target-spelled);
        # RawSQL fallbacks must not re-render it in the source dialect.
        emb_token = _conv.IR_EMBEDDED.set(True)
        try:
            return self._ir_transpile_dml_inner(sql)
        finally:
            _conv.IR_EMBEDDED.reset(emb_token)
            _conv.STRING_VARIABLES.reset(str_token)
            _conv.FETCH_STATUS_FORMS.reset(fetch_token)
            _conv.SOURCE_DIALECT.reset(src_token)
            _conv.DATE_VARIABLES.reset(date_token)

    def _ir_transpile_dml_inner(self, sql: str) -> str | None:
        from unique.core import converter as _conv
        from unique.core.ast_nodes import CommentStatement as IRComment
        from unique.core.ast_nodes import PassthroughSQL as IRPassthrough
        from unique.core.ast_nodes import RawSQL as IRRawSQL
        from unique.core.transformer import Transformer

        try:
            nodes = _conv.parse_sql(sql, self._source)
        except Exception as e:  # noqa: BLE001 - fall back to sqlglot path
            logger.debug("IR parse failed for embedded DML: %s", e)
            return None
        statements = [n for n in nodes if not isinstance(n, IRComment)]
        # A top-level Alias is not a statement — it is a fragment of shell
        # machinery text (an EXEC tail like ``sp_executesql @s`` parses as
        # ``sp_executesql AS @s`` — the validate_source bare-Alias class);
        # the IR does not apply.
        from unique.core.ast_nodes import Alias as IRAlias

        if any(isinstance(n, IRAlias) for n in statements):
            return None
        # An EmbeddedDML node holds exactly one statement; a RawSQL result is
        # a parse failure and a PassthroughSQL an unmodeled construct — the IR
        # would just re-run sqlglot on those, without the target fixups the
        # fallback applies, so hand them back. Exception: MERGE, CTE-DML and
        # ALTER, where the IR emitter owns the target fixes raw sqlglot lacks
        # (MySQL's upsert rewrite, Oracle's mandatory ON parens, the
        # updatable-CTE carrier, the DUAL/';' cleanups, and
        # _portable_alter_add — raw sqlglot spells Oracle's multi-column ADD
        # as the invalid ``ADD COLUMNS (…)`` on every other engine).
        owned_passthrough = bool(statements) and all(
            isinstance(n, IRPassthrough) and n.kind in ("MERGE", "CTE DML", "ALTER")
            for n in statements
        )
        if len(statements) != 1 or (
            not owned_passthrough
            and any(isinstance(n, (IRRawSQL, IRPassthrough)) for n in statements)
        ):
            return None
        try:
            transformer = Transformer(self._source, self._target)
            nodes = transformer.transform(nodes)
            for warning in transformer.warnings:
                self._warnings.append(warning.message)
            # Comments first, the statement last: the procedural emitter
            # appends the statement terminator to the *end* of this text, and
            # a trailing ``-- comment`` line would comment the terminator out.
            nodes.sort(key=lambda n: not isinstance(n, IRComment))
            pieces = [_conv.emit_node(n, self._target) for n in nodes]
        except Exception as e:  # noqa: BLE001 - fall back to sqlglot path
            logger.debug("IR transform/emit failed for embedded DML: %s", e)
            return None
        # Short embedded DML reads best on one line inside a routine body (the
        # emitter's multi-line layout is kept only for long statements — same
        # heuristic as the previous sqlglot ``pretty=len > 200`` path).
        if len(sql) <= 200:
            pieces = [
                p if p.lstrip().startswith(("--", "/*")) else _one_line_sql(p)
                for p in pieces
            ]
        out = "\n".join(p for p in pieces if p)
        if not out.strip():
            return None
        if owned_passthrough:
            lines = out.splitlines()
            body = [x for x in lines if x.strip() and not x.lstrip().startswith("--")]
            if not body:
                # Comment-only carrier (an unexpressible MERGE or updatable
                # CTE): keep it — the sqlglot fallback would ship invalid
                # SQL — plus a no-op so an enclosing block does not end up
                # empty, and surface the carrier's note as the warning.
                note = next(
                    (
                        x.lstrip("- ").removeprefix("UNIQUE:").strip()
                        for x in lines
                        if x.lstrip().startswith("-- UNIQUE:")
                    ),
                    "statement preserved as a comment for manual rewrite",
                )
                self._warnings.append(note)
                return out + "\n" + self._noop_sql()
            # A documentation note trailing the statement would swallow the
            # terminator the routine emitter appends — move it ahead.
            trailing: list[str] = []
            while lines and lines[-1].lstrip().startswith("--"):
                trailing.insert(0, lines.pop())
            return "\n".join(trailing + lines)
        # The IR pipeline emits RawSQL fragments (an unconvertible expression
        # deep in the tree) verbatim; a leaked LINE carrier means the result
        # is not a faithful conversion — use the fallback instead. Inline
        # ``/* UNIQUE: … */`` notes are documented FAITHFUL mappings
        # (VALUES(col)→NULL, wave 223) and pass.
        if "-- UNIQUE:" in out:
            return None
        return out

    def _transform_cross_table_update(self, sql: str) -> str | None:
        """Render a cross-table ``UPDATE ... FROM/JOIN`` via the IR emitter.

        Returns the target SQL when ``sql`` is exactly one UPDATE statement that
        carries a FROM/JOIN (the shape sqlglot mishandles), else ``None`` so the
        caller falls back to the normal sqlglot path.
        """
        from unique.core import converter as _conv

        try:
            parsed = sqlglot.parse(sql, read=self._get_sqlglot_dialect(self._source))
        except Exception:  # noqa: BLE001 - fall back to sqlglot path
            return None
        statements = [s for s in parsed if s is not None]
        if len(statements) != 1 or not isinstance(statements[0], sqlglot.exp.Update):
            return None
        update_expr = statements[0]
        from_expr = update_expr.args.get("from_") or update_expr.args.get("from")
        if from_expr is None:
            return None
        # Only handle joins against plain tables. A join against a subquery
        # (e.g. an aggregate "JOIN (SELECT ... GROUP BY) agg") is not converted
        # faithfully by the IR yet, so fall back to the documented degradation
        # path rather than emit a broken "FROM <empty>".
        source_table = from_expr.this
        if isinstance(source_table, sqlglot.exp.Table):
            for join_expr in source_table.args.get("joins") or []:
                if not isinstance(join_expr.this, sqlglot.exp.Table):
                    return None
        try:
            ir_node = _conv._convert_update(update_expr)
            if not isinstance(ir_node, UpdateStatement):
                # The conversion degraded (derived-table FROM, wave 193)
                # — take the documented fallback path.
                return None
            if ir_node.from_clause is None and not ir_node.joins:
                return None
            return _conv._emit_update(ir_node, self._target)
        except Exception as e:  # noqa: BLE001 - fall back to sqlglot path
            logger.debug("IR cross-table UPDATE rewrite failed: %s", e)
            return None

    def _fix_target_dml(self, sql: str) -> str:
        """Apply target-specific cleanups to sqlglot-transpiled DML. The base
        (T-SQL) needs none; each target subclass overrides with its fixups."""
        return sql

    def _fix_select_into_rest(self, sql: str) -> str:
        """Target-specific cleanups for a SELECT INTO's FROM/WHERE tail.
        The base is a no-op; T-SQL maps the Oracle leftovers (ROWNUM,
        TRUNC, ...)."""
        return sql

    def _fix_ir_dml(self, sql: str) -> str:
        """Cleanups applied to IR-emitted embedded DML. Unlike
        ``_fix_target_dml`` (whose sqlglot re-runs assume raw fallback text),
        this must be cheap and idempotent; the base is a no-op."""
        return sql

    def _rewrites_trigger_pseudotables(self) -> bool:
        """Whether inserted/deleted pseudo-tables get rewritten to NEW/OLD in a
        trigger body. True for every target except T-SQL (which keeps them)."""
        return True

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
            if self._preserve_set_based_dml:
                # The trigger is being rewritten with transition tables that are
                # literally named ``inserted``/``deleted`` (PG REFERENCING /
                # Oracle compound trigger), so the set-based DML is valid as-is.
                return sql
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
            return f"{note}\n{body}\n{self._noop_sql()}"
        # Column-qualifier form: map to NEW/OLD (row-level).
        sql = re.sub(r"(?i)\binserted\s*\.\s*", self._trigger_new_ref(), sql)
        sql = re.sub(r"(?i)\bdeleted\s*\.\s*", self._trigger_old_ref(), sql)
        return sql

    def _normalize_oracle_pseudorecords(self, sql: str) -> str:
        """Map Oracle ``:NEW.``/``:OLD.`` (possibly lexed as ``: NEW .``) to the
        target's row qualifier, so sqlglot doesn't misread ``:NEW`` as a bind
        placeholder (``%(NEW)s`` on PostgreSQL)."""
        sql = re.sub(r"(?i):\s*NEW\s*\.\s*", self._trigger_new_ref(), sql)
        sql = re.sub(r"(?i):\s*OLD\s*\.\s*", self._trigger_old_ref(), sql)
        return sql

    def _noop_sql(self) -> str:
        """A no-op statement as raw SQL text. Default ``NULL;``; MySQL ``DO 0;``."""
        return "NULL;"

    def _trigger_new_ref(self) -> str:
        """Row-level NEW-row qualifier in a trigger. Default ``NEW.``; Oracle
        ``:NEW.``."""
        return "NEW."

    def _trigger_old_ref(self) -> str:
        """Row-level OLD-row qualifier in a trigger. Default ``OLD.``; Oracle
        ``:OLD.``."""
        return "OLD."

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
        allowed = {"JSON_TABLE", "STRING_SPLIT"}
        return bool(self._function_relation_names(sql, "mysql") - allowed)

    def _function_relation_names(self, sql: str, dialect: str) -> set[str]:
        """Names of function calls used as a FROM/JOIN relation in *sql*
        (table-valued functions), parsed in *dialect*. Empty set when there
        are none or the text does not parse."""
        import sqlglot
        from sqlglot import exp

        if "(" not in sql or not re.search(r"(?i)\bFROM\b|\bJOIN\b", sql):
            return set()

        def func_name(node: object) -> str:
            if isinstance(node, exp.Anonymous):
                return str(node.this).upper()
            return type(node).__name__.upper()

        try:
            trees = sqlglot.parse(sql, read=self._get_sqlglot_dialect(dialect))
        except Exception:
            return set()
        names: set[str] = set()
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
                if candidate is not None:
                    names.add(func_name(candidate))
        return names

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
        """Default keeps the NULL no-op (Oracle/PG have ``NULL;``); T-SQL
        overrides to a comment (it has no NULL statement)."""
        return node

    #: Trigger event-predicate spellings (either family's source form):
    #: T-SQL ``UPDATE(col)`` and PL/SQL INSERTING/UPDATING/DELETING.
    _TRIGGER_PREDICATE_RE = re.compile(
        r"(?i)\bUPDATE\s*\(\s*\w+\s*\)|\b(?:INSERTING|UPDATING|DELETING)\b"
    )

    _FETCH_STATUS_OK_RE = re.compile(r"(?i)@@FETCH_STATUS\s*=\s*0\b")
    _FETCH_STATUS_FAIL_RE = re.compile(
        r"(?i)@@FETCH_STATUS\s*(?:<>|!=)\s*0\b|@@FETCH_STATUS\s*=\s*-\s*[12]\b"
    )

    def _fetch_status_forms(self) -> tuple[str, str] | None:
        """(success, failure) target expressions for the T-SQL
        ``@@FETCH_STATUS = 0`` / ``<> 0`` cursor-loop idiom. None (the base)
        leaves it to the generic system-var handling."""
        return None

    def _fix_fetch_status(self, sql: str) -> str:
        if "@@FETCH_STATUS" not in sql.upper():
            return sql
        forms = self._fetch_status_forms()
        if forms is None:
            return sql
        ok, fail = forms
        sql = self._FETCH_STATUS_FAIL_RE.sub(fail, sql)
        return self._FETCH_STATUS_OK_RE.sub(ok, sql)

    # The T-SQL base64-decode idiom: an empty XML document's ``value()``
    # evaluating ``xs:base64Binary(sql:variable("@v"))``. Each target has a
    # native base64 decoder.
    _BASE64_XML_RE = re.compile(
        r"(?is)CAST\s*\(\s*N?''\s*AS\s+XML\s*\)\s*\.\s*value\s*\(\s*"
        r"'xs:base64Binary\(sql:variable\(\"(@?\w+)\"\)\)'\s*,\s*'[^']*'\s*\)"
    )

    def _fix_base64_xml_idiom(self, sql: str) -> str:
        if self._target == "tsql" or ":base64Binary" not in sql:
            return sql
        template = {
            "postgresql": "DECODE({v}, 'base64')",
            "mysql": "FROM_BASE64({v})",
            # BASE64_DECODE takes/returns RAW (32k PL/SQL cap) — enough for
            # the typical use and it assigns implicitly to a BLOB.
            "oracle": "UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW({v}))",
        }.get(self._target)
        if template is None:
            return sql
        return self._BASE64_XML_RE.sub(lambda m: template.format(v=m.group(1)), sql)

    #: ``operand::type`` with a simple operand (identifier, @var, literal,
    #: or number) — parenthesized operands stay untouched.
    _PG_SIMPLE_CAST_RE = re.compile(
        r"([@\w']+)\s*:\s*:\s*(\w+(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)"
    )

    @classmethod
    def _pg_cast_to_ansi(cls, sql: str) -> str:
        """Rewrite PG ``expr::type`` casts (simple operands) to ANSI
        CAST — the raw spelling ships as ``x : : type`` off PG."""

        def sub(segment: str) -> str:
            prev = None
            while prev != segment:
                prev = segment
                segment = cls._PG_SIMPLE_CAST_RE.sub(r"CAST(\1 AS \2)", segment)
            return segment

        return cls._map_outside_strings(sql, sub)

    @classmethod
    def _string_agg_within_group(cls, sql: str) -> str:
        """PG's in-call aggregate ORDER BY — ``STRING_AGG(x, ',' ORDER
        BY a)`` — spells ``… ) WITHIN GROUP (ORDER BY a)`` on T-SQL.
        Paren-aware: the ORDER BY split happens at call depth only."""
        out: list[str] = []
        i, n = 0, len(sql)
        while i < n:
            m = re.compile(r"(?i)\bSTRING_AGG\s*\(").search(sql, i)
            if m is None:
                out.append(sql[i:])
                break
            out.append(sql[i : m.end()])
            depth = 1
            j = m.end()
            order_at = None
            while j < n and depth > 0:
                c = sql[j]
                if c == "'":
                    k = j + 1
                    while k < n:
                        if sql[k] == "'":
                            if k + 1 < n and sql[k + 1] == "'":
                                k += 2
                                continue
                            break
                        k += 1
                    j = k + 1
                    continue
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif depth == 1 and order_at is None:
                    om = re.compile(r"(?i)\border\s+by\b").match(sql, j)
                    if om:
                        order_at = (j, om.end())
                j += 1
            if order_at is None:
                out.append(sql[m.end() : j])
            else:
                start, kw_end = order_at
                inner_order = sql[kw_end : j - 1].strip()
                out.append(sql[m.end() : start].rstrip())
                out.append(f") WITHIN GROUP (ORDER BY {inner_order})")
            i = j
        return "".join(out)

    @staticmethod
    def _mysql_dq_to_sq(sql: str) -> str:
        """Rewrite MySQL double-quoted STRING literals to single-quoted
        (double quotes delimit identifiers on every other engine).
        Single-quoted regions pass through untouched."""
        out: list[str] = []
        i, n = 0, len(sql)
        while i < n:
            ch = sql[i]
            if ch == "'":
                j = i + 1
                while j < n:
                    if sql[j] == "'":
                        if j + 1 < n and sql[j + 1] == "'":
                            j += 2
                            continue
                        break
                    j += 1
                out.append(sql[i : j + 1])
                i = j + 1
                continue
            if ch == '"':
                j = i + 1
                content: list[str] = []
                while j < n:
                    c = sql[j]
                    if c == "\\" and j + 1 < n:
                        content.append(sql[j + 1])
                        j += 2
                        continue
                    if c == '"':
                        if j + 1 < n and sql[j + 1] == '"':
                            content.append('"')
                            j += 2
                            continue
                        break
                    content.append(c)
                    j += 1
                text = "".join(content).replace("'", "''")
                out.append(f"'{text}'")
                i = j + 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    def _transform_raw_sql(self, node: RawSQL) -> RawSQL:
        # A non-SQL-language routine (LANGUAGE C/internal/plperl…) has no
        # transpilable body — and a plpgsql block label (<<label>>) has no
        # model: both are valid verbatim on their own engine, a documented
        # carrier anywhere else (waves 122, 126).
        if node.reason == "COMMENT ON statement":
            # PG/Oracle SQL; MySQL/T-SQL have no COMMENT ON (wave 225).
            if self._target in ("postgresql", "oracle"):
                return node
            reason = (
                f"COMMENT ON has no {self._target} equivalent; "
                "statement preserved as a comment"
            )
            self._warnings.append(reason)
            return RawSQL(sql=node.sql, reason=reason)
        if node.reason.startswith("MySQL admin statement"):
            # Verbatim on MySQL; a documented in-body carrier elsewhere
            # (FLUSH/RESET/PURGE have no cross-engine form — wave 166).
            if self._target == "mysql":
                return node
            reason = (
                f"{node.reason} has no {self._target} equivalent; "
                "statement preserved as a comment"
            )
            self._warnings.append(reason)
            return RawSQL(sql=node.sql, reason=reason)
        if node.reason.startswith(
            (
                "non-SQL language function",
                "plpgsql block label",
                "plpgsql # compiler",
                "plpgsql unmodeled body shape",
            )
        ):
            if self._source == self._target:
                return node
            reason = (
                f"{node.reason} cannot be transpiled to {self._target}; "
                "statement preserved as a comment"
            )
            self._warnings.append(reason)
            m = self._ROUTINE_NAME_RE.search(node.sql)
            if m:
                self._register_degraded_routine(m.group(1))
            return RawSQL(sql=node.sql, reason=reason)
        # A whole-unit parse fallback must not ship raw across dialects:
        # the source-dialect body would leak as top-level fragments on the
        # target. Rewrite to the carrier contract the emitter comments out.
        if node.reason.startswith("Parse error"):
            reason = (
                f"{self._source} routine could not be parsed "
                f"({node.reason}); statement preserved as a comment"
            )
            self._warnings.append(reason)
            m = self._ROUTINE_NAME_RE.search(node.sql)
            if m:
                self._register_degraded_routine(m.group(1))
            return RawSQL(sql=node.sql, reason=reason)
        # M3-final migration switch (docs/TODO.md §2 P0): scalar fragments
        # route IR-first when UNIQUE_IR_FIRST is set — the development loop
        # that burns the remaining text-path/IR divergences family by
        # family. Off (the default) keeps the text path as the expression
        # engine until the families below it migrate. The switch replaces
        # the EXPRESSION-MAPPING layers only: the procedural-shell text
        # passes above it (variable renames, source-spelling parse aids,
        # pseudorecords) still run — that context is the shell's, not the
        # expression engine's. Cursor state travels via FETCH_STATUS_FORMS
        # (precondition (a)), so the text fetch-status fix is skipped.
        ir_first = bool(os.environ.get("UNIQUE_IR_FIRST"))
        sql = node.sql
        if not ir_first:
            sql = self._fix_fetch_status(sql)
        sql = self._fix_base64_xml_idiom(sql)
        if self._source == "mysql" and self._target != "mysql":
            sql = self._mysql_dq_to_sq(sql)
        if self._source == "postgresql" and self._target == "mysql":
            # PG E-strings: MySQL's backslash escapes are compatible, so
            # the prefix simply drops (other targets treat backslashes
            # literally — semantic change, left alone).
            sql = re.sub(r"(?i)\bE\s*(?=')", "", sql)
        if self._source == "postgresql" and self._target != "postgresql":
            sql = self._pg_cast_to_ansi(sql)
            if self._target == "tsql" and not ir_first:
                # A TARGET-spelling text step: IR-first handles the in-call
                # aggregate ORDER BY natively from the ORIGINAL spelling —
                # pre-rewriting hands the IR an unparseable hybrid.
                sql = self._string_agg_within_group(sql)
            from unique.core.converter import PG_DOMAIN_TYPES

            domains = PG_DOMAIN_TYPES.get() or {}
            for dom, base in domains.items():

                def _sub_domain(seg: str, d: str = dom, b: str = base) -> str:
                    return re.sub(rf"(?i)\b{re.escape(d)}\b", b, seg)

                sql = self._map_outside_strings(sql, _sub_domain)
        sql = self._transform_var_in_sql(sql)
        # An Oracle trigger body's assignment value carries ``:NEW.``/``:OLD.``
        # row references; map them to the target's row qualifier (a no-op for the
        # Oracle target). Mirrors _transform_embedded_dml so a value captured as a
        # scalar expression is normalized the same as one inside embedded DML.
        if self._source == "oracle" and self._in_trigger:
            sql = self._normalize_oracle_pseudorecords(sql)
        if ir_first:
            # Trigger event predicates are shell spellings the SOURCE parse
            # corrupts (T-SQL ``UPDATE(col)`` parses as a DML statement,
            # INSERTING as a bare identifier) — those fragments stay on the
            # text path, whose per-target trigger mapping owns them.
            has_trigger_predicate = (
                self._in_trigger
                and self._TRIGGER_PREDICATE_RE.search(self._strip_strings(sql))
            )
            if not has_trigger_predicate:
                ir = self._ir_transpile_dml(sql)
                if ir is not None:
                    if self._in_trigger and self._target == "oracle":
                        # The row-ref spelling is per-target shell context
                        # (Oracle binds :NEW./:OLD.) — IR output gets the
                        # same normalization as text output.
                        ir = self._expr._to_oracle_row_ref(ir)
                    # Comments are trivia, but a LINE comment in an
                    # expression fragment swallows the rest of the line once
                    # the emitter joins the statement (the _flat_value rule;
                    # M3 precondition (b)). Carrier lines keep their form —
                    # the output gate rejects on them by design.
                    ir = self._line_comments_to_block(ir)
                    return dataclasses.replace(node, sql=ir)
        # Apply function name transformations
        sql = self._expr._transform_functions_in_sql(sql)
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
                    out = self._expr._unwrap_spurious_hash_format(out)
                    sql = self._fix_unwrapped_scalar(out)
            except Exception:
                pass
        sql = self._rewrite_trigger_update_predicate(sql)
        sql = self._fix_raw_sql_target(sql)
        if self._source == "tsql" and self._target != "tsql":
            # Locking hints inside a captured condition (IF EXISTS (SELECT 1
            # FROM t WITH (UPDLOCK)) ...) survive the sqlglot attempt when it
            # bails; they have no cross-engine form.
            sql = self._strip_tsql_table_hints(sql)
        return RawSQL(sql=sql, reason=node.reason)

    def _fix_raw_sql_target(self, sql: str) -> str:
        """Apply target-specific cleanups to a transformed raw-SQL expression.
        The base (T-SQL) needs none; each target subclass overrides."""
        return sql

    def _fix_unwrapped_scalar(self, sql: str) -> str:
        """Post-process a scalar expression just unwrapped from a sqlglot
        SELECT. The base returns it unchanged; Oracle overrides to apply its
        DML fixups."""
        return sql

    def _rewrite_trigger_update_predicate(self, sql: str) -> str:
        """Rewrite the T-SQL trigger predicate ``UPDATE(col)`` per dialect.

        Inside a trigger, T-SQL ``UPDATE(col)`` tests whether a column was
        affected by the statement. The per-target equivalent is provided by
        ``_update_predicate``:
          - MySQL:      NOT (NEW.col <=> OLD.col)   (null-safe "changed")
          - PostgreSQL: (NEW.col IS DISTINCT FROM OLD.col)
          - Oracle:     UPDATING('col')

        Only matches ``UPDATE(<identifier>)`` as a function-style predicate (a
        single column name in parens), never an ``UPDATE … SET`` statement.
        T-SQL keeps the predicate as-is.
        """
        if not self._has_update_predicate():
            return sql
        pattern = re.compile(r"(?i)\bUPDATE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")

        def repl(m: re.Match[str]) -> str:
            return self._update_predicate(m.group(1)) or m.group(0)

        return pattern.sub(repl, sql)

    def _has_update_predicate(self) -> bool:
        """Whether this target rewrites the T-SQL ``UPDATE(col)`` trigger
        predicate. True for all but T-SQL (which keeps it)."""
        return True

    def _update_predicate(self, col: str) -> str | None:
        """Per-target rewrite of ``UPDATE(col)``. Overridden by each non-T-SQL
        target; None means leave unchanged."""
        return None

    def _get_func_map(self) -> dict[str, str]:
        return PROCEDURAL_FUNC_MAPS.get((self._source, self._target), {})

    @staticmethod
    def _get_sqlglot_dialect(dialect: str) -> str:
        mapping = {
            "tsql": "tsql",
            "oracle": "oracle",
            "postgresql": "postgres",
            "mysql": "mysql",
        }
        return mapping.get(dialect, dialect)
