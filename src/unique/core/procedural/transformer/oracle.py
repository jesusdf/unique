# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — oracle target."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    ASTNode,
    BeginEndBlock,
    CreateProcedureStatement,
    DataType,
    EmbeddedDML,
    ExceptionBlock,
    ExceptionHandler,
    ForLoopStatement,
    IfStatement,
    LoopStatement,
    ParameterDefinition,
    RawSQL,
    StatementList,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class OracleTransformer(ProceduralTransformer):
    """Transforms toward Oracle PL/SQL."""

    target_name = "oracle"

    def _transform_procedure(self, node: CreateProcedureStatement) -> ASTNode:
        # A T-SQL procedure returns a result set with a bare ``SELECT``. Oracle
        # has no equivalent inside PL/SQL, so give the procedure a ``SYS_REFCURSOR``
        # OUT parameter per result set and ``OPEN`` it FOR that query — the
        # procedure body then works; only the *call sites* need adapting (vs a
        # carrier, where the whole body must also be rewritten by hand).
        proc = super()._transform_procedure(node)
        if isinstance(proc, CreateProcedureStatement):
            return self._hoist_table_variables(self._result_selects_to_refcursors(proc))
        return proc

    def _transform_alter_procedure(self, node: AlterProcedureStatement) -> ASTNode:
        # An idempotent T-SQL routine is often a stub CREATE + the real body in
        # ALTER PROCEDURE, which lowers to CREATE OR REPLACE on Oracle. Apply the
        # same result-set → SYS_REFCURSOR and table-variable → GTT rewrites.
        proc = super()._transform_alter_procedure(node)
        if isinstance(proc, CreateProcedureStatement):
            return self._hoist_table_variables(self._result_selects_to_refcursors(proc))
        return proc

    def _hoist_table_variables(self, proc: CreateProcedureStatement) -> ASTNode:
        """A T-SQL table variable has no in-block Oracle form (a CREATE cannot
        live in PL/SQL, and the body references it statically). Lift it to a
        schema-level Global Temporary Table emitted *before* the procedure, with
        a per-procedure-unique name (the same ``@t`` in two procedures would
        clash), and rename the body references."""
        gtts: list[tuple[str, str, str]] = []  # (var, gtt_name, columns)
        kept: list[ASTNode] = []
        for stmt in proc.body:
            if (
                isinstance(stmt, RawSQL)
                and stmt.reason == "table variable -> temporary table"
            ):
                m = re.match(
                    r"(?is)\s*CREATE\s+TEMPORARY\s+TABLE\s+(\w+)\s*(\(.*\))\s*;",
                    stmt.sql,
                )
                if m:
                    var, cols = m.group(1), m.group(2).strip()
                    gtts.append((var, f"{proc.name}_{var}"[:120], cols))
                    continue  # drop the in-body CREATE
            kept.append(stmt)
        if not gtts:
            return proc

        renames = {var: gtt for var, gtt, _ in gtts}
        new_proc = dataclasses.replace(
            proc, body=tuple(self._rename_idents(s, renames) for s in kept)
        )
        ddls: list[ASTNode] = [
            RawSQL(
                sql=(
                    f"CREATE GLOBAL TEMPORARY TABLE {gtt} {cols} ON COMMIT DELETE"
                    f" ROWS;  /* UNIQUE: was T-SQL table variable {var} */"
                )
            )
            for var, gtt, cols in gtts
        ]
        return StatementList(statements=tuple([*ddls, new_proc]))

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

    def _result_selects_to_refcursors(
        self, proc: CreateProcedureStatement
    ) -> CreateProcedureStatement:
        cursors: list[str] = []
        new_body = self._rewrite_result_selects(proc.body, cursors)
        if not cursors:
            return proc
        cursor_params = tuple(
            ParameterDefinition(
                name=c, data_type=DataType(name="SYS_REFCURSOR"), direction="OUT"
            )
            for c in cursors
        )
        return dataclasses.replace(
            proc, parameters=proc.parameters + cursor_params, body=new_body
        )

    def _rewrite_result_selects(
        self, stmts: tuple[ASTNode, ...], cursors: list[str]
    ) -> tuple[ASTNode, ...]:
        """Replace each bare result ``SELECT`` with ``OPEN <cursor> FOR …``,
        recursing into control-flow blocks; append allocated cursor names."""
        out: list[ASTNode] = []
        for stmt in stmts:
            if isinstance(stmt, EmbeddedDML) and self._is_result_select(stmt.sql):
                name = (
                    "RESULT_CURSOR"
                    if not cursors
                    else f"RESULT_CURSOR_{len(cursors) + 1}"
                )
                cursors.append(name)
                query = stmt.sql.rstrip(";").strip()
                out.append(RawSQL(sql=f"OPEN {name} FOR {query};"))
            elif isinstance(stmt, IfStatement):
                out.append(
                    dataclasses.replace(
                        stmt,
                        then_body=self._rewrite_result_selects(stmt.then_body, cursors),
                        else_body=self._rewrite_result_selects(stmt.else_body, cursors),
                    )
                )
            elif isinstance(stmt, (WhileStatement, ForLoopStatement, LoopStatement)):
                out.append(
                    dataclasses.replace(
                        stmt, body=self._rewrite_result_selects(stmt.body, cursors)
                    )
                )
            elif isinstance(stmt, (BeginEndBlock, StatementList)):
                out.append(
                    dataclasses.replace(
                        stmt,
                        statements=self._rewrite_result_selects(
                            stmt.statements, cursors
                        ),
                    )
                )
            else:
                out.append(stmt)
        return tuple(out)

    @staticmethod
    def _is_result_select(sql: str) -> bool:
        """A top-level result-set SELECT (returns rows, no INTO target)."""
        s = sql.strip()
        return bool(re.match(r"(?i)^SELECT\b", s)) and not re.search(r"(?i)\bINTO\b", s)

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

    def _fix_raw_sql_target(self, sql: str) -> str:
        # T-SQL ``TOP (n)`` has no Oracle keyword; sqlglot rewrites the enclosing
        # SELECT to ``FETCH FIRST n ROWS ONLY`` (ORA-00907 otherwise). Only pay
        # the round-trip on a real row limit (``TOP <digits>``), not a column
        # named "top"; fall back to the original on any parse failure.
        if re.search(r"(?i)\bTOP\s*\(?\s*\d", sql):
            sql = self._top_to_oracle(sql)

        # dbo doesn't exist in Oracle; drop a dbo. qualifier on calls within
        # expressions (e.g. dbo.func1() in an assignment, RETURN or COALESCE).
        sql = re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)

        # T-SQL string ``+`` in an assignment/return expression -> Oracle ``||``.
        sql = self._rewrite_string_concat(sql, "oracle")

        # A MySQL/PostgreSQL-source trigger body's NEW./OLD. row reference in an
        # assignment value becomes Oracle's :NEW./:OLD.
        if self._in_trigger:
            sql = self._to_oracle_row_ref(sql)

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
        return self._oracle_function_fixes(sql)

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
