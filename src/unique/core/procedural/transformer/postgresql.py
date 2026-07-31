# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — postgresql target."""

from __future__ import annotations

import dataclasses
import re

from unique.core.ast_nodes import (
    AlterProcedureStatement,
    AnonymousBlock,
    ASTNode,
    CommentStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    DataType,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
    ExitStatement,
    ForeachStatement,
    ForLoopStatement,
    GetDiagnosticsStatement,
    LoopStatement,
    RawSQL,
    StatementList,
    TransactionAction,
    TransactionStatement,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class PostgresTransformer(ProceduralTransformer):
    """Transforms toward PostgreSQL PL/pgSQL."""

    target_name = "postgresql"

    def _system_var_map(self) -> dict[str, str]:
        return {
            # PostgreSQL has no inline row-count expression — a bare
            # ``ROW_COUNT`` identifier is not valid standalone PL/pgSQL. Map to
            # the function-shaped ``ROW_COUNT()`` spelling that the B37b hoist
            # (below) recognizes and lifts into a ``GET DIAGNOSTICS`` capture.
            "@@ROWCOUNT": "ROW_COUNT()",
            "@@IDENTITY": "LASTVAL()",
            # SQLSTATE is only available inside an EXCEPTION handler in plpgsql,
            # so it cannot stand in for an inline @@ERROR check.
            "@@ERROR": self._neutral_global("@@ERROR", "use an EXCEPTION handler"),
            "@@TRANCOUNT": self._neutral_global(
                "@@TRANCOUNT", "the routine manages its transaction"
            ),
        }

    # -- Implicit row-count in expression position (B37 / B37b) --------------
    #
    # PostgreSQL reads the last statement's row count only through the
    # ``GET DIAGNOSTICS x = ROW_COUNT`` *statement* — it has no inline form,
    # so ``emit.py`` degrades an inline ``SQL%ROWCOUNT`` to a carrier. Where
    # the reference is single-evaluated (an assignment, an ``IF`` condition, a
    # call argument, a ``RETURN``) we hoist a ``GET DIAGNOSTICS`` capturing the
    # row count into a declared local immediately before the referencing
    # statement, then substitute the local. The source names the last executed
    # DML; in straight-line code that DML is the previous statement, so a
    # capture placed right before the use (``GET DIAGNOSTICS`` does not itself
    # alter ROW_COUNT) reads exactly the value the source would. A re-evaluated
    # loop/exit condition cannot be captured once — it degrades honestly,
    # keeping the existing carrier.
    #
    # The hoist is spelling-general (B37b): all three source spellings of the
    # implicit row count reach PostgreSQL in a form the recognizer below
    # matches — Oracle's ``SQL%ROWCOUNT`` (carrier or raw), MySQL's
    # ``ROW_COUNT()`` (left as-is, no pg inline form), and T-SQL's
    # ``@@ROWCOUNT`` (mapped to ``ROW_COUNT()`` by ``_system_var_map``).
    #: The reference to substitute: emit.py's degrade carrier (the usual case,
    #: e.g. an IF condition), the raw Oracle source spelling that some positions
    #: ship untouched (a CALL argument's text), or the ``ROW_COUNT()`` function
    #: spelling (MySQL source / mapped T-SQL global). The carrier alternative is
    #: listed first so it consumes the whole ``0 /* … */`` span — the source
    #: spelling nested inside the comment is never matched on its own.
    _ROWCOUNT_CARRIER_RE = re.compile(
        r"0\s*/\*\s*UNIQUE-1033:[^*]*\*/"
        r"|\bSQL\s*%\s*ROWCOUNT\b"
        r"|\bROW_COUNT\s*\(\s*\)",
        re.IGNORECASE,
    )
    _ROWCOUNT_TMP = "uq_rowcount"
    #: Fields whose value is a nested statement body (recursed into so a
    #: reference inside an IF/loop/EXCEPTION body hoists at its own level).
    _ROWCOUNT_BODY_FIELDS = (
        "body",
        "then_body",
        "else_body",
        "try_body",
        "catch_body",
        "statements",
    )

    def _transform_procedure(self, node: CreateProcedureStatement) -> ASTNode:
        return self._hoist_implicit_rowcount(super()._transform_procedure(node))

    def _transform_alter_procedure(self, node: AlterProcedureStatement) -> ASTNode:
        # T-SQL's idempotent ``EXEC('CREATE PROCEDURE … AS SELECT 1') … ALTER
        # PROCEDURE`` stub pattern lands the real body on an ALTER node, so the
        # hoist must cover it too (else ``@@ROWCOUNT`` ships an invalid inline
        # ``ROW_COUNT()``).
        return self._hoist_implicit_rowcount(super()._transform_alter_procedure(node))

    def _transform_function(self, node: CreateFunctionStatement) -> ASTNode:
        return self._hoist_implicit_rowcount(super()._transform_function(node))

    def _transform_trigger(self, node: CreateTriggerStatement) -> ASTNode:
        return self._hoist_implicit_rowcount(super()._transform_trigger(node))

    def _transform_anonymous_block(self, node: AnonymousBlock) -> ASTNode:
        return self._hoist_implicit_rowcount(super()._transform_anonymous_block(node))

    def _hoist_implicit_rowcount(self, node: ASTNode) -> ASTNode:
        """Hoist a ``GET DIAGNOSTICS`` capture ahead of every single-evaluated
        ``SQL%ROWCOUNT`` reference in *node*'s body and declare the local once.
        A no-op when the body carries no such carrier."""
        field = "body" if hasattr(node, "body") else "statements"
        body = getattr(node, field, None)
        if not isinstance(body, tuple):
            return node
        self._rowcount_hoisted = False
        new_body = self._inject_rowcount(body)
        if not self._rowcount_hoisted:
            return node
        if self._source == "mysql":
            # MySQL's ROW_COUNT() counts rows CHANGED by the last DML; the
            # PostgreSQL ``GET DIAGNOSTICS ROW_COUNT`` it hoists to counts rows
            # MATCHED (base.py N11/B12) — a value-wise no-op UPDATE diverges.
            # Warn (do not ship silently). Oracle/T-SQL sources count matched
            # rows too, so they do not diverge.
            self._warn_mysql_rowcount_divergence()
        decl = DeclareStatement(
            name=self._ROWCOUNT_TMP, data_type=DataType(name="bigint")
        )
        return dataclasses.replace(node, **{field: (decl, *new_body)})  # type: ignore[arg-type]

    def _inject_rowcount(self, stmts: tuple[ASTNode, ...]) -> tuple[ASTNode, ...]:
        out: list[ASTNode] = []
        for stmt in stmts:
            stmt = self._recurse_rowcount_bodies(stmt)
            if isinstance(
                stmt,
                (
                    WhileStatement,
                    LoopStatement,
                    ForLoopStatement,
                    ForeachStatement,
                    ExitStatement,
                ),
            ):
                # A loop/exit condition is re-evaluated (or loop-scoped); a
                # single capture cannot stand in for it — degrade honestly.
                # The body was already handled by _recurse_rowcount_bodies.
                out.append(stmt)
                continue
            new_stmt, found = self._substitute_rowcount_expr(stmt)
            if found:
                out.append(
                    GetDiagnosticsStatement(items=((self._ROWCOUNT_TMP, "ROW_COUNT"),))
                )
                self._rowcount_hoisted = True
            out.append(new_stmt)
        return tuple(out)

    def _recurse_rowcount_bodies(self, stmt: ASTNode) -> ASTNode:
        """Recurse the hoist into *stmt*'s nested statement bodies so a
        reference inside a control-flow block captures at its own level."""
        changes: dict[str, object] = {}
        for name in self._ROWCOUNT_BODY_FIELDS:
            val = getattr(stmt, name, None)
            if (
                isinstance(val, tuple)
                and val
                and all(isinstance(x, ASTNode) for x in val)
            ):
                new = self._inject_rowcount(val)
                if new != val:
                    changes[name] = new
        if isinstance(stmt, ExceptionBlock):
            new_handlers = tuple(
                dataclasses.replace(h, body=self._inject_rowcount(h.body))
                for h in stmt.handlers
            )
            if new_handlers != stmt.handlers:
                changes["handlers"] = new_handlers
        if changes:
            return dataclasses.replace(stmt, **changes)  # type: ignore[arg-type]
        return stmt

    def _substitute_rowcount_expr(self, stmt: ASTNode) -> tuple[ASTNode, bool]:
        """Replace the UNIQUE-1033 carrier with the captured local in *stmt*'s
        own expression parts (scalar sub-nodes and ``sql``/``args`` text) —
        never in nested bodies, which ``_recurse_rowcount_bodies`` owns."""
        found = False
        changes: dict[str, object] = {}
        for f in dataclasses.fields(stmt):
            val = getattr(stmt, f.name)
            if isinstance(val, str) and f.name in ("sql", "args"):
                new = self._ROWCOUNT_CARRIER_RE.sub(self._ROWCOUNT_TMP, val)
                if new != val:
                    changes[f.name] = new
                    found = True
            elif isinstance(val, ASTNode):
                new_node, sub_found = self._substitute_rowcount_expr(val)
                if sub_found:
                    changes[f.name] = new_node
                    found = True
        if changes:
            return dataclasses.replace(stmt, **changes), True  # type: ignore[arg-type]
        return stmt, found

    def _transform_try_catch(self, node: TryCatchBlock) -> ASTNode:
        """plpgsql lowers TRY/CATCH to ``BEGIN … EXCEPTION``, which runs the
        protected body inside a subtransaction: a plain COMMIT/ROLLBACK there
        raises ``cannot commit while a subtransaction is active`` at runtime
        (live 2026-07-30). The subtransaction already gives the T-SQL
        semantics — entering the handler rolls the protected work back, and
        the routine/DO block commits on success — so transaction control
        inside the block is dropped with a documented ``/* UNIQUE: */``
        carrier (auto-warned, no-silent-loss)."""
        result = super()._transform_try_catch(node)
        if not isinstance(result, TryCatchBlock):
            return result
        return dataclasses.replace(
            result,
            try_body=tuple(self._neutralize_txn(s) for s in result.try_body),
            catch_body=tuple(self._neutralize_txn(s) for s in result.catch_body),
        )

    def _neutralize_txn(self, node: ASTNode) -> ASTNode:
        """Replace a plain COMMIT/ROLLBACK (recursively, e.g. inside an IF)
        with a documented carrier comment; savepoints and named forms pass
        through untouched."""
        if (
            isinstance(node, TransactionStatement)
            and node.name is None
            and node.action in (TransactionAction.COMMIT, TransactionAction.ROLLBACK)
        ):
            word = "COMMIT" if node.action is TransactionAction.COMMIT else "ROLLBACK"
            return CommentStatement(
                text=(
                    f"/* UNIQUE-1206: {word} dropped -- the exception-guarded "
                    "block is a subtransaction (transaction control there "
                    "is a runtime error); it rolls back on error and "
                    "commits with the surrounding transaction */"
                ),
                style="block",
            )
        changes: dict[str, object] = {}
        for f in dataclasses.fields(node):
            val = getattr(node, f.name)
            if (
                isinstance(val, tuple)
                and val
                and all(isinstance(x, ASTNode) for x in val)
            ):
                new = tuple(self._neutralize_txn(x) for x in val)
                if new != val:
                    changes[f.name] = new
        if changes:
            return dataclasses.replace(node, **changes)  # type: ignore[arg-type]
        return node

    def _transform_for_loop(self, node: ForLoopStatement) -> ASTNode:
        result = super()._transform_for_loop(node)
        result = self._rename_shadowed_loop_var(result)
        if (
            isinstance(result, ForLoopStatement)
            and result.cursor is not None
            and result.variable.lower() not in self._declared_loop_records
        ):
            # plpgsql requires the row-loop variable to be *declared* (only
            # integer range loops auto-declare); PL/SQL declares it
            # implicitly. Emit a record declaration — the emitter hoists it
            # into the DECLARE section.
            self._declared_loop_records.add(result.variable.lower())
            return StatementList(
                statements=(
                    DeclareStatement(
                        name=result.variable, data_type=DataType(name="record")
                    ),
                    result,
                )
            )
        return result

    @property
    def _declared_loop_records(self) -> set[str]:
        if not hasattr(self, "_declared_loop_records_"):
            self._declared_loop_records_: set[str] = set()
        return self._declared_loop_records_

    def _rename_shadowed_loop_var(self, result: ASTNode) -> ASTNode:
        if (
            isinstance(result, ForLoopStatement)
            and result.cursor is not None
            and result.variable.lower() in self._declared_scalar_names
        ):
            # PL/SQL lets a row FOR-loop shadow a declared scalar; plpgsql
            # rejects a scalar loop variable over rows — rename the loop
            # variable and its row references (the declared scalar keeps its
            # meaning outside the loop, exactly as in Oracle).
            new_var = f"{result.variable}_rec"
            ref = re.compile(rf"(?i)\b{re.escape(result.variable)}\s*\.\s*")

            def rename(stmt: ASTNode) -> ASTNode:
                if isinstance(stmt, RawSQL):
                    return RawSQL(
                        sql=ref.sub(f"{new_var}.", stmt.sql), reason=stmt.reason
                    )
                if isinstance(stmt, EmbeddedDML):
                    return EmbeddedDML(
                        sql=ref.sub(f"{new_var}.", stmt.sql), dialect=stmt.dialect
                    )
                changes: dict[str, object] = {}
                for f in dataclasses.fields(stmt):
                    val = getattr(stmt, f.name)
                    if isinstance(val, ASTNode):
                        changes[f.name] = rename(val)
                    elif (
                        isinstance(val, tuple)
                        and val
                        and all(isinstance(x, ASTNode) for x in val)
                    ):
                        changes[f.name] = tuple(rename(x) for x in val)
                if changes:
                    return dataclasses.replace(stmt, **changes)  # type: ignore[arg-type]
                return stmt

            return ForLoopStatement(
                variable=new_var,
                range_start=result.range_start,
                range_end=result.range_end,
                cursor=rename(result.cursor) if result.cursor else None,
                body=tuple(rename(x) for x in result.body),
                reverse=result.reverse,
            )
        return result

    def _package_refcursor_type(self) -> str | None:
        return "REFCURSOR"

    def _fetch_status_forms(self) -> tuple[str, str] | None:
        # plpgsql sets FOUND after every FETCH.
        return ("FOUND", "NOT FOUND")

    def _varchar_max_type(self, is_unicode: bool) -> str | None:
        return "TEXT"

    def _named_arg_op(self) -> str | None:
        # PostgreSQL passes a procedure's named argument as ``name => value``.
        return "=>"

    def _supports_transition_tables(self) -> bool:
        # A statement-level trigger with REFERENCING NEW/OLD TABLE sees all rows.
        return True

    def _fix_target_dml(self, sql: str) -> str:
        sql = self._rewrite_alter_trigger(sql)
        sql = self._map_oracle_catalogs(sql)
        sql = self._expr._pg_string_concat(sql)
        sql = self._expr._pg_numeric_concat_cast(sql)
        sql = self._pg_clean_dml(sql)
        return sql

    def _update_predicate(self, col: str) -> str | None:
        return f"(NEW.{col} IS DISTINCT FROM OLD.{col})"

    def _map_oracle_catalogs(self, sql: str) -> str:
        """Oracle user_* catalog probes -> information_schema (found live:
        column-existence guards). Unquoted Oracle identifiers are stored
        uppercase but PostgreSQL folds to lowercase — compare case-folded."""
        if self._source != "oracle" or not re.search(
            r"(?i)\buser_tab_col(?:umn)?s\b|\buser_tables\b", sql
        ):
            return sql
        sql = re.sub(
            r"(?i)\buser_tab_col(?:umn)?s\b", "information_schema.columns", sql
        )
        sql = re.sub(r"(?i)\buser_tables\b", "information_schema.tables", sql)
        sql = re.sub(
            r"(?i)\b(table_name|column_name)\s*=\s*('(?:[^']|'')*')",
            lambda m: f"{m.group(1)} = lower({m.group(2)})",
            sql,
        )
        return sql

    _ALTER_TRIGGER_RE = re.compile(
        r"(?is)^\s*ALTER\s+TRIGGER\s+([\w\"]+)\s+(ENABLE|DISABLE)\s*;?\s*$"
    )

    def _rewrite_alter_trigger(self, sql: str) -> str:
        """Oracle's ALTER TRIGGER x ENABLE names only the trigger; PostgreSQL
        needs the table (ALTER TABLE t ENABLE TRIGGER x) — resolved from
        pg_trigger at run time; a missing trigger degrades to a no-op."""
        m = self._ALTER_TRIGGER_RE.match(sql)
        if not m or self._source == self._target:
            return sql
        name, action = m.group(1).strip('"'), m.group(2).upper()
        return (
            "EXECUTE COALESCE((SELECT format("
            f"'ALTER TABLE %s {action} TRIGGER %I', tgrelid::regclass, tgname)"
            f" FROM pg_trigger WHERE tgname = lower('{name}')"
            " AND NOT tgisinternal LIMIT 1), 'SELECT 1');"
        )

    def _fix_select_into_rest(self, sql: str) -> str:
        return self._map_oracle_catalogs(sql)

    def _fix_raw_sql_target(self, sql: str) -> str:
        sql = self._rewrite_alter_trigger(sql)
        sql = self._map_oracle_catalogs(sql)
        sql = self._expr._pg_string_concat(sql)
        sql = self._expr._pg_numeric_concat_cast(sql)
        if self._in_trigger:
            # PL/SQL trigger event predicates: plpgsql reads TG_OP.
            sql = re.sub(
                r"(?i)\bUPDATING\s*\(\s*'(\w+)'\s*\)",
                r"(TG_OP = 'UPDATE' AND NEW.\1 IS DISTINCT FROM OLD.\1)",
                sql,
            )
            sql = re.sub(r"(?i)\bINSERTING\b", "(TG_OP = 'INSERT')", sql)
            sql = re.sub(r"(?i)\bUPDATING\b", "(TG_OP = 'UPDATE')", sql)
            sql = re.sub(r"(?i)\bDELETING\b", "(TG_OP = 'DELETE')", sql)
        # T-SQL ERROR_MESSAGE() inside a CATCH -> SQLERRM in the EXCEPTION
        # handler (parameterless; the empty parens would not parse).
        sql = re.sub(r"(?i)\bERROR_MESSAGE\s*\(\s*\)", "SQLERRM", sql)
        # dbo doesn't exist in PostgreSQL; drop a dbo. qualifier on calls.
        return re.sub(r"(?i)\bdbo\s*\.\s*", "", sql)


register_transformer(PostgresTransformer.target_name, PostgresTransformer)
