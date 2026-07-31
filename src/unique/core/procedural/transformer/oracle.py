# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — oracle target."""

from __future__ import annotations

import dataclasses
import re
from typing import Any, TypeVar

import sqlglot
from sqlglot import expressions as exp

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AssignmentStatement,
    ASTNode,
    CreateFunctionStatement,
    CreateProcedureStatement,
    DataType,
    DeclareStatement,
    ForLoopStatement,
    IfStatement,
    NullStatement,
    ParameterDefinition,
    RawSQL,
    SelectIntoStatement,
    StatementList,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)

#: A routine whose reassigned IN parameters can be shadowed (both carry
#: ``parameters`` and ``body``); the TypeVar preserves the concrete type.
_Routine = TypeVar("_Routine", CreateProcedureStatement, CreateFunctionStatement)


class OracleTransformer(ProceduralTransformer):
    """Transforms toward Oracle PL/SQL."""

    target_name = "oracle"

    def _void_return_type(self) -> DataType:
        """Oracle's neutral scalar for PG's ``void`` (NUMBER is callable
        from SQL and its value is ignorable)."""
        return DataType(name="NUMBER")

    def _void_return_value(self) -> ASTNode:
        return RawSQL(sql="NULL", reason="expression")

    def _transform_procedure(self, node: CreateProcedureStatement) -> ASTNode:
        # A T-SQL procedure returns a result set with a bare ``SELECT``. Oracle
        # has no equivalent inside PL/SQL, so give the procedure a ``SYS_REFCURSOR``
        # OUT parameter per result set and ``OPEN`` it FOR that query — the
        # procedure body then works; only the *call sites* need adapting (vs a
        # carrier, where the whole body must also be rewritten by hand).
        proc = super()._transform_procedure(node)
        if isinstance(proc, CreateProcedureStatement):
            proc = self._shadow_reassigned_params(proc)
            return self._hoist_table_variables(self._result_selects_to_refcursors(proc))
        return proc

    def _transform_alter_procedure(self, node: AlterProcedureStatement) -> ASTNode:
        # An idempotent T-SQL routine is often a stub CREATE + the real body in
        # ALTER PROCEDURE, which lowers to CREATE OR REPLACE on Oracle. Apply the
        # same result-set → SYS_REFCURSOR and table-variable → GTT rewrites.
        proc = super()._transform_alter_procedure(node)
        if isinstance(proc, CreateProcedureStatement):
            proc = self._shadow_reassigned_params(proc)
            return self._hoist_table_variables(self._result_selects_to_refcursors(proc))
        return proc

    @staticmethod
    def _table_var_gtt(node: ASTNode) -> tuple[str, str] | None:
        """The ``(name, columns)`` of a T-SQL ``@table`` variable's CREATE
        marker, or None if ``node`` is not one."""
        if not (
            isinstance(node, RawSQL)
            and node.reason == "table variable -> temporary table"
        ):
            return None
        m = re.match(
            r"(?is)\s*CREATE\s+TEMPORARY\s+TABLE\s+(\w+)\s*(\(.*\))\s*;", node.sql
        )
        return (m.group(1), m.group(2).strip()) if m else None

    @staticmethod
    def _select_into_gtt_var(node: ASTNode) -> tuple[str, str] | None:
        """The ``(name, CREATE sql)`` of a ``SELECT … INTO #tmp`` GTT hoist
        marker (B28a), or None if ``node`` is not one."""
        if not (isinstance(node, RawSQL) and node.reason == "select-into temp table"):
            return None
        m = re.match(r"(?is)\s*CREATE\s+GLOBAL\s+TEMPORARY\s+TABLE\s+(\w+)\b", node.sql)
        return (m.group(1), node.sql) if m else None

    def _hoist_table_variables(self, proc: CreateProcedureStatement) -> ASTNode:
        """A T-SQL table variable has no in-block Oracle form (a CREATE cannot
        live in PL/SQL, and the body references it statically). Lift it to a
        schema-level Global Temporary Table emitted *before* the procedure, with
        a per-procedure-unique name (the same ``@t`` in two procedures would
        clash), and rename the body references."""
        gtts: list[tuple[str, str, str]] = []  # (var, gtt_name, columns)
        # (var, gtt_name, full CREATE sql) for ``SELECT … INTO #tmp`` temp
        # tables lowered to a GTT (B28a): the CREATE is a CTAS with a
        # column-less structure, so it is hoisted verbatim (renamed) rather
        # than rebuilt from a column list.
        ctas_gtts: list[tuple[str, str, str]] = []

        def strip(node: ASTNode) -> ASTNode | None:
            # The declaration may sit inside an IF/WHILE/TRY block (T-SQL
            # scopes DECLARE to the batch, not the block): recurse. A hoist
            # marker (a table-variable CREATE, or a SELECT-INTO temp-table
            # GTT) is collected and dropped from the body.
            tvar = self._table_var_gtt(node)
            if tvar is not None:
                var, cols = tvar
                gtts.append((var, f"{proc.name}_{var}"[:120], cols))
                return None  # drop the in-body CREATE
            ctas = self._select_into_gtt_var(node)
            if ctas is not None:
                ctas_var, ctas_sql = ctas
                ctas_gtts.append((ctas_var, f"{proc.name}_{ctas_var}"[:120], ctas_sql))
                return None  # drop the in-body CREATE (hoisted below)
            changes: dict[str, object] = {}
            for f in dataclasses.fields(node):
                val = getattr(node, f.name)
                if (
                    isinstance(val, tuple)
                    and val
                    and all(isinstance(x, ASTNode) for x in val)
                ):
                    new_items = tuple(y for x in val if (y := strip(x)) is not None)
                    if new_items != val:
                        if not new_items:
                            # A block that held only the declaration must not
                            # collapse to an empty (invalid) body.
                            new_items = (NullStatement(),)
                        changes[f.name] = new_items
            if changes:
                return dataclasses.replace(node, **changes)  # type: ignore[arg-type]
            return node

        kept = [y for stmt in proc.body if (y := strip(stmt)) is not None]
        if not gtts and not ctas_gtts:
            return proc

        renames = {var: gtt for var, gtt, _ in gtts}
        renames.update({var: gtt for var, gtt, _ in ctas_gtts})
        new_proc = dataclasses.replace(
            proc, body=tuple(self._rename_idents(s, renames) for s in kept)
        )
        ddls: list[ASTNode] = [
            RawSQL(
                # The documenting comment leads the statement — a trailing comment
                # after the ``;`` splits off as its own (invalid) statement.
                sql=(
                    f"/* UNIQUE-1196: was T-SQL table variable {var} */\n"
                    f"CREATE GLOBAL TEMPORARY TABLE {gtt} {cols} "
                    "ON COMMIT DELETE ROWS;"
                )
            )
            for var, gtt, cols in gtts
        ]
        ddls += [
            RawSQL(
                sql=(
                    f"/* UNIQUE-1205: was T-SQL temp table #{var} */\n"
                    f"{re.sub(rf'\b{re.escape(var)}\b', gtt, create_sql)};"
                )
            )
            for var, gtt, create_sql in ctas_gtts
        ]
        return StatementList(statements=tuple([*ddls, new_proc]))

    def _transform_function(self, node: CreateFunctionStatement) -> ASTNode:
        fn = super()._transform_function(node)
        if isinstance(fn, CreateFunctionStatement):
            return self._shadow_reassigned_params(fn)
        return fn

    def _transform_if(self, node: IfStatement) -> ASTNode:
        stmt = super()._transform_if(node)
        # `IF EXISTS (<subquery>) THEN …` is invalid PL/SQL — EXISTS is a SQL
        # operator, not a boolean expression (PLS-00204). Emulate it with a cursor
        # FOR loop over a one-row probe: the body runs once iff the subquery
        # returns a row (`SELECT 1 FROM DUAL WHERE [NOT] EXISTS (…)`).
        if not isinstance(stmt, IfStatement):
            return stmt
        cond = stmt.condition
        if not (
            isinstance(cond, RawSQL)
            and re.match(r"(?is)^\s*(?:NOT\s+)?EXISTS\s*\(", cond.sql)
        ):
            return stmt
        then_loop = self._exists_probe_loop(cond.sql, stmt.then_body)
        if not stmt.else_body:
            return then_loop
        # ELSE: a second FOR over the *negated* probe — EXISTS and NOT EXISTS are
        # mutually exclusive, so exactly one body fires.
        else_loop = self._exists_probe_loop(
            self._negate_exists(cond.sql), stmt.else_body
        )
        return StatementList(statements=(then_loop, else_loop))

    @staticmethod
    def _exists_probe_loop(
        where_sql: str, body: tuple[ASTNode, ...]
    ) -> ForLoopStatement:
        return ForLoopStatement(
            variable="unique_guard",
            cursor=RawSQL(sql=OracleTransformer._probe_cursor(where_sql)),
            body=body,
        )

    @staticmethod
    def _probe_cursor(where_sql: str) -> str:
        """``(SELECT 1 FROM DUAL WHERE <cond>)`` — the one-row guard probe.

        Every SELECT needs a FROM clause on Oracle, so a FROM-less subquery in the
        condition (e.g. ``EXISTS (SELECT NULL)``, or ``SELECT 1`` with no source)
        must get ``FROM DUAL`` too, not just the outer probe — otherwise the cursor
        is invalid (ORA-00923). If the condition can't be parsed, fall back to the
        raw wrap (the prior behaviour) so nothing is lost.
        """
        probe = f"SELECT 1 FROM DUAL WHERE {where_sql.strip()}"
        try:
            tree = sqlglot.parse_one(probe, read="oracle")
        except Exception:
            return f"({probe})"
        fromless = [
            s
            for s in tree.find_all(exp.Select)
            if not (s.args.get("from") or s.args.get("from_"))
        ]
        for select in fromless:
            select.from_("DUAL", copy=False)
        return f"({tree.sql(dialect='oracle')})"

    @staticmethod
    def _negate_exists(sql: str) -> str:
        """Negate an ``EXISTS``/``NOT EXISTS`` predicate."""
        m = re.match(r"(?is)^\s*NOT\s+(EXISTS\b.*)$", sql)
        return m.group(1).strip() if m else f"NOT {sql.strip()}"

    def _shadow_reassigned_params(self, node: _Routine) -> _Routine:
        """T-SQL freely reassigns a routine's parameters; an Oracle IN parameter
        is read-only (PLS-00363). For each IN parameter the body assigns to, rename
        the parameter (``p`` -> ``p_IN``) and add a local ``p := p_IN`` shadow, so
        the body reads/writes the local and the call sites (positional) are
        unaffected."""
        params = node.parameters
        in_params = {p.name: p for p in params if p.direction == "IN"}
        if not in_params:
            return node
        assigned = self._collect_assigned_targets(node.body) & set(in_params)
        if not assigned:
            return node
        new_params = tuple(
            dataclasses.replace(p, name=f"{p.name}_IN") if p.name in assigned else p
            for p in params
        )
        shadows = tuple(
            DeclareStatement(
                name=p.name,
                data_type=in_params[p.name].data_type,
                default=RawSQL(sql=f"{p.name}_IN"),
            )
            for p in params
            if p.name in assigned
        )
        return dataclasses.replace(
            node, parameters=new_params, body=shadows + node.body
        )

    def _collect_assigned_targets(self, stmts: tuple[ASTNode, ...]) -> set[str]:
        """Every variable name that appears as an assignment target anywhere in a
        statement tree (recursing into control-flow blocks)."""
        found: set[str] = set()

        def walk(node: ASTNode) -> None:
            if isinstance(node, AssignmentStatement):
                found.add(node.target)
            for f in dataclasses.fields(node):
                val = getattr(node, f.name)
                if (
                    isinstance(val, tuple)
                    and val
                    and hasattr(val[0], "__dataclass_fields__")
                ):
                    for item in val:
                        walk(item)
                elif hasattr(val, "__dataclass_fields__"):
                    walk(val)

        for stmt in stmts:
            walk(stmt)
        return found

    def _rename_idents(self, node: ASTNode, renames: dict[str, str]) -> ASTNode:
        """Rename bare identifiers (word-boundary) in every ``sql`` string of a
        node tree — used to point table-variable references at the hoisted GTT."""
        changes: dict[str, Any] = {}
        for f in dataclasses.fields(node):
            val = getattr(node, f.name)
            if f.name == "sql" and isinstance(val, str):
                new = val
                for old, gtt in renames.items():
                    new = re.sub(rf"\b{re.escape(old)}\b", gtt, new)
                if new != val:
                    changes[f.name] = new
            elif (
                isinstance(val, tuple)
                and val
                and hasattr(val[0], "__dataclass_fields__")
            ):
                changes[f.name] = tuple(self._rename_idents(c, renames) for c in val)
            elif hasattr(val, "__dataclass_fields__"):
                changes[f.name] = self._rename_idents(val, renames)
        return dataclasses.replace(node, **changes) if changes else node

    def _result_refcursor_param(self, name: str) -> ParameterDefinition:
        # A bare result SELECT returns rows only through a SYS_REFCURSOR OUT
        # parameter the body OPENs FOR the query (the base rewrite handles the
        # body and the call-site propagation).
        return ParameterDefinition(
            name=name, data_type=DataType(name="SYS_REFCURSOR"), direction="OUT"
        )

    def _fetch_status_forms(self) -> tuple[str, str] | None:
        # %FOUND/%NOTFOUND need the cursor's name: use the one from the most
        # recent FETCH (the T-SQL idiom checks the fetch that just ran).
        cur = self._last_fetch_cursor
        if cur is None:
            return None
        return (f"{cur}%FOUND", f"{cur}%NOTFOUND")

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

    def _trigger_forces_or_replace(self) -> bool:
        return True

    def _is_native_bool_type(self, dt: DataType) -> bool:
        # Oracle's PL/SQL BOOLEAN is native (kept only when the source's
        # own boolean maps to it — a pg-source ``boolean``; mysql-source's
        # BOOLEAN always maps to NUMBER(1), see PROCEDURAL_TYPE_MAPS).
        # PLS-00382 rejects a 1/0 literal against it (wave B45).
        return dt.name.upper() == "BOOLEAN"

    # No _transform_try_catch override: the old one rebuilt an ExceptionBlock
    # from the CATCH body alone and silently DROPPED the TRY body (the node
    # has no body slot). The base keeps the TryCatchBlock with transformed
    # bodies; the Oracle emitter renders the nested
    # ``BEGIN … EXCEPTION WHEN OTHERS THEN … END;`` block.

    def _fix_target_dml(self, sql: str) -> str:
        return self._fix_oracle_dml(sql)

    def _update_predicate(self, col: str) -> str | None:
        return f"UPDATING('{col}')"

    def _fix_unwrapped_scalar(self, sql: str) -> str:
        return self._fix_oracle_dml(sql)

    # Type names Oracle's CAST wants instead of the T-SQL spelling.
    _CAST_TYPE_MAP = {
        "DECIMAL": "NUMBER",
        "NUMERIC": "NUMBER",
        "DEC": "NUMBER",
        "VARCHAR": "VARCHAR2",
        "NVARCHAR": "NVARCHAR2",
    }
    _CAST_CONSTRAINED_RE = re.compile(
        r"(?i)\bAS\s+(DECIMAL|NUMERIC|DEC|NUMBER|FLOAT|VARCHAR2?|NVARCHAR2?|CHAR|NCHAR)"
        r"(\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))"
    )
    #: A CAST to these keeps its length — a character CAST with none is ORA-00906
    #: (only a numeric CAST's precision is dropped, for PLS-00103).
    _CAST_KEEP_LENGTH = frozenset(
        {"VARCHAR", "VARCHAR2", "NVARCHAR", "NVARCHAR2", "CHAR", "NCHAR"}
    )

    def _transform_select_into(self, node: SelectIntoStatement) -> ASTNode:
        result = super()._transform_select_into(node)
        # T-SQL's aggregation assignment ``SELECT @v = @v + <expr> FROM …``
        # concatenates <expr> across ALL rows; a plain SELECT INTO reads ONE
        # row (and raises on more). Rewrite to LISTAGG over the rows — the
        # variable prefix and its NULL propagation are preserved.
        if (
            isinstance(result, SelectIntoStatement)
            and result.tsql_assignment
            and self._source == "tsql"
            and len(result.into_vars) == 1
            and len(result.columns) == 1
            and isinstance(result.columns[0], RawSQL)
            and result.rest_sql.upper().startswith("FROM")
        ):
            var = result.into_vars[0]
            m = re.match(
                rf"(?is)^\s*CASE\s+WHEN\s+{re.escape(var)}\s+IS\s+NULL\s+THEN\s+"
                rf"NULL\s+ELSE\s+{re.escape(var)}\s*\|\|\s*(.+?)\s+END\s*$",
                result.columns[0].sql,
            ) or re.match(
                rf"(?is)^\s*{re.escape(var)}\s*\|\|\s*(.+)$",
                result.columns[0].sql,
            )
            if m:
                agg_expr = m.group(1).strip()
                # The T-SQL catalog's ``name`` column is TABLE_NAME on the
                # mapped user_tables/all_tables view.
                if re.search(r"(?i)\b(?:user|all)_tables\b", result.rest_sql):
                    agg_expr = self._map_outside_strings(
                        agg_expr,
                        lambda seg: re.sub(r"(?i)\bname\b", "table_name", seg),
                    )
                agg = (
                    f"CASE WHEN {var} IS NULL THEN NULL ELSE {var} || "
                    f"LISTAGG({agg_expr}, '') "
                    "WITHIN GROUP (ORDER BY ROWNUM) END"
                )
                result = dataclasses.replace(
                    result,
                    columns=(RawSQL(sql=agg, reason="aggregation assignment"),),
                )
        return result

    def _fix_select_into_rest(self, sql: str) -> str:
        # Cross-engine catalog views in a SELECT INTO's FROM tail: Oracle has
        # no information_schema and no sys.tables.
        sql = re.sub(r"(?i)\binformation_schema\s*\.\s*tables\b", "all_tables", sql)
        return re.sub(r"(?i)\bsys\s*\.\s*tables\b", "user_tables", sql)

    def _fix_raw_sql_target(self, sql: str) -> str:
        if self._source == "postgresql":
            # plpgsql's FOUND flag (set by the last DML): this
            # target's row-count predicate, outside string literals.
            sql = self._map_outside_strings(
                sql,
                lambda seg: re.sub(r"(?i)\bFOUND\b", "SQL%FOUND", seg),
            )
        # T-SQL ``TOP (n)`` has no Oracle keyword; sqlglot rewrites the enclosing
        # SELECT to ``FETCH FIRST n ROWS ONLY`` (ORA-00907 otherwise). Only pay
        # the round-trip on a real row limit (``TOP <digits>``), not a column
        # named "top"; fall back to the original on any parse failure.
        if re.search(r"(?i)\bTOP\s*\(?\s*\d", sql):
            sql = self._top_to_oracle(sql)

        # T-SQL ERROR_MESSAGE() inside a CATCH -> SQLERRM in the EXCEPTION
        # handler (parameterless; the empty parens would not parse).
        sql = re.sub(r"(?i)\bERROR_MESSAGE\s*\(\s*\)", "SQLERRM", sql)

        # Cross-engine catalog views: Oracle has no information_schema and no
        # sys.tables — ALL_TABLES/USER_TABLES are the accessible-tables views
        # (a name map; row counts are environment-dependent on every engine).
        sql = re.sub(r"(?i)\binformation_schema\s*\.\s*tables\b", "all_tables", sql)
        sql = re.sub(r"(?i)\bsys\s*\.\s*tables\b", "user_tables", sql)

        # dbo doesn't exist in Oracle; drop a dbo. qualifier on calls within
        # expressions (e.g. dbo.func1() in an assignment, RETURN or COALESCE).
        sql = re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)

        # T-SQL string ``+`` in an assignment/return expression -> Oracle ``||``.
        sql = self._expr._rewrite_string_concat(sql, "oracle")

        # A MySQL/PostgreSQL-source trigger body's NEW./OLD. row reference in an
        # assignment value becomes Oracle's :NEW./:OLD.
        if self._in_trigger:
            sql = self._expr._to_oracle_row_ref(sql)

        # A PL/SQL expression CAST rejects a constrained type (PLS-00103):
        # CAST(x AS NUMBER(12,2)) / VARCHAR2(10) must drop the length, and
        # DECIMAL/NUMERIC must become NUMBER. Only the numeric-constrained
        # ``AS <type>(...)`` form (never an alias or function call) is matched.
        def _unconstrained_cast_type(m: re.Match[str]) -> str:
            typ = m.group(1).upper()
            mapped = self._CAST_TYPE_MAP.get(typ, typ)
            length = m.group(2) if typ in self._CAST_KEEP_LENGTH else ""
            return f"AS {mapped}{length}"

        sql = self._CAST_CONSTRAINED_RE.sub(_unconstrained_cast_type, sql)
        # Last: after the concat re-pass (which can drop a CAST's length) and the
        # constraint strip — TRY_CAST, a bare character CAST needing a length, etc.
        sql = self._expr._oracle_function_fixes(sql)
        if self._expr_position:
            # A pure PL/SQL *expression* position (PRINT argument): ANY
            # constrained CAST type is PLS-00103 — char included, the exact
            # reverse of a SQL statement (ORA-00906 without a length). The
            # caller marks the position; the fragment text cannot tell.
            def _bare(m: re.Match[str]) -> str:
                typ = m.group(1).upper()
                return f"AS {self._CAST_TYPE_MAP.get(typ, typ)})"

            sql = self._map_outside_strings(
                sql,
                lambda seg: re.sub(
                    r"(?i)\bAS\s+(N?VARCHAR2?|N?CHAR|NUMBER|DECIMAL|NUMERIC|DEC"
                    r"|FLOAT)\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\)\s*\)",
                    _bare,
                    seg,
                ),
            )
        return sql

    @staticmethod
    def _top_to_oracle(sql: str) -> str:
        """Rewrite a fragment's ``SELECT TOP (n) …`` to Oracle via sqlglot."""
        import sqlglot

        try:
            out = sqlglot.transpile(sql, read="tsql", write="oracle")
        except Exception:
            return sql
        return out[0] if out else sql

    def _named_arg_op(self) -> str | None:
        # Oracle passes a procedure's named argument as ``name => value``.
        return "=>"

    def _trigger_new_ref(self) -> str:
        return ":NEW."

    def _trigger_old_ref(self) -> str:
        return ":OLD."

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        # VARCHAR(MAX)/NVARCHAR(MAX) -> CLOB/NCLOB cannot be a comparison or join
        # key in PL/SQL (ORA-22848). A procedure parameter/variable is a scalar,
        # so map it to a bounded VARCHAR2/NVARCHAR2 (Oracle's largest) — this is
        # comparable and sufficient for scalar use. (A value beyond the bound
        # would need Oracle's MAX_STRING_SIZE = EXTENDED.)
        return "NVARCHAR2(2000)" if is_unicode else "VARCHAR2(4000)"


register_transformer(OracleTransformer.target_name, OracleTransformer)
