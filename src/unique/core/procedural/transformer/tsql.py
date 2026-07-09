# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — tsql target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    AssignmentStatement,
    ASTNode,
    CreateTriggerStatement,
    EmbeddedDML,
    ExceptionBlock,
    IfStatement,
    Literal,
    LoopStatement,
    NullStatement,
    RawSQL,
    ReturnStatement,
    SetVariableStatement,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.converter import IDENTITY_COLUMNS, PG_TRIGGER_FN_BODIES, USER_FUNCTIONS
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class TSqlTransformer(ProceduralTransformer):
    """Transforms toward T-SQL (SQL Server)."""

    target_name = "tsql"

    #: ``a - b`` between two identifiers (used to rewrite date subtraction).
    _SUBTRACT_RE = re.compile(r"(@?\w+)\s*-\s*(@?\w+)")

    def _fix_raw_sql_target(self, sql: str) -> str:
        # T-SQL has no date ``-`` operator (error 8117 / 257). ``d2 - d1`` over
        # two DATE/DATETIME vars/params becomes ``DATEDIFF(DAY, d1, d2)`` (days
        # from d1 to d2), matching the source's date-difference semantics.
        if not self._date_vars:
            return sql

        def repl(m: re.Match[str]) -> str:
            a, b = m.group(1), m.group(2)
            if a in self._date_vars and b in self._date_vars:
                return f"DATEDIFF(DAY, {b}, {a})"
            return m.group(0)

        return self._SUBTRACT_RE.sub(repl, sql)

    # ---------------------------------------------------------------
    # Row-level trigger -> T-SQL statement-level (inserted/deleted) trigger
    # ---------------------------------------------------------------

    def _rowlevel_trigger_override(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        """A row-level source trigger (``FOR EACH ROW`` with ``NEW``/``OLD``) has
        no T-SQL equivalent — T-SQL triggers are statement-level over the
        ``inserted``/``deleted`` pseudo-tables. Rewrite each body statement to its
        set-based form and drop the BEFORE/AFTER distinction (both become AFTER;
        a ``SET NEW.col`` becomes an UPDATE of the affected rows)."""
        if node.for_each != "ROW" or self._source == "tsql" or node.execute_function:
            return None
        return self._tsql_statement_trigger(node, node.body)

    def _lower_compound_for_statement_target(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        # An Oracle COMPOUND trigger's AFTER STATEMENT re-aggregation (captured
        # as ``compound_row_body`` keyed on ``:NEW.<fk>``) is the same set-based
        # UPDATE a T-SQL statement-level trigger runs over ``inserted``.
        if not node.compound_row_body:
            return None
        return self._tsql_statement_trigger(node, node.compound_row_body)

    def _inline_delegating_trigger(
        self, node: CreateTriggerStatement
    ) -> ASTNode | None:
        # A PostgreSQL trigger delegates to a ``RETURNS TRIGGER`` function; T-SQL
        # has no trigger functions, so inline the harvested function body. Its
        # statement-level ``inserted``/``deleted`` UPDATEs map straight to T-SQL;
        # the ``pg_trigger_depth()`` guard (T-SQL: RECURSIVE_TRIGGERS OFF) and
        # ``RETURN`` are dropped.
        bodies = PG_TRIGGER_FN_BODIES.get() or {}
        src = bodies.get((node.execute_function or "").lower())
        if src is None:
            return None
        from unique.core.procedural.parser import ProceduralParser

        fn_node = ProceduralParser(self._source).parse(src).node
        body = tuple(getattr(fn_node, "body", ()) or ())
        kept = tuple(b for b in body if not self._is_pg_trigger_noise(b))
        return self._tsql_statement_trigger(node, kept)

    def _trigger_function_is_inlined(self, name: str) -> bool:
        bodies = PG_TRIGGER_FN_BODIES.get() or {}
        return name.strip('[]"`').split(".")[-1].lower() in bodies

    @staticmethod
    def _is_pg_trigger_noise(node: ASTNode) -> bool:
        """A ``RETURN`` (T-SQL triggers do not return) or the ``pg_trigger_depth``
        recursion guard, both dropped when inlining a PG trigger function."""
        if isinstance(node, ReturnStatement):
            return True
        if isinstance(node, IfStatement):
            cond = getattr(node.condition, "sql", "") or ""
            return "pg_trigger_depth" in cond.lower()
        return False

    def _tsql_statement_trigger(
        self, node: CreateTriggerStatement, body_nodes: tuple[ASTNode, ...]
    ) -> ASTNode | None:
        prev = self._in_trigger
        self._in_trigger = True
        try:
            stmts = [self._rowlevel_body_to_tsql(b, node.table) for b in body_nodes]
        finally:
            self._in_trigger = prev
        kept = [s for s in stmts if s is not None]
        if not kept:
            return None
        return CreateTriggerStatement(
            name=self._translate_ident_quoting(node.name) or node.name,
            table=self._translate_ident_quoting(node.table) or node.table,
            timing="AFTER",
            events=node.events,
            for_each="STATEMENT",
            body=tuple(kept),
            or_replace=node.or_replace,
            schema=self._target_schema(node.schema),
        )

    _NEW_ASSIGN_RE = re.compile(r"(?i)^\s*(NEW|OLD)\s*\.\s*(\w+)\s*$")

    def _rowlevel_body_to_tsql(self, node: ASTNode, table: str) -> ASTNode | None:
        bare_table = table.strip('[]"`').split(".")[-1]
        # Pattern (a): ``SET NEW.col = expr`` (a per-row derived/stamped column).
        # T-SQL has no BEFORE trigger and cannot write ``inserted``, so update the
        # affected rows: ``UPDATE t SET col = <expr> WHERE <pk> IN (SELECT <pk>
        # FROM inserted)``. The expr's own-row NEW./OLD. references become the
        # table's bare columns.
        target = None
        value = None
        if isinstance(node, AssignmentStatement):
            target, value = node.target, node.value
        elif isinstance(node, SetVariableStatement):
            target, value = node.name, node.value
        if target is not None and value is not None:
            m = self._NEW_ASSIGN_RE.match(target)
            if m:
                col = m.group(2)
                expr = value.sql if isinstance(value, RawSQL) else self._lit(value)
                # An own-row NEW./OLD. (Oracle ``:NEW.``) reference becomes the
                # table's bare column. Drop the Oracle bind colon (only when it
                # precedes NEW/OLD) and the NEW./OLD. qualifier — anchored so a
                # preceding operator's whitespace is not swallowed.
                expr = re.sub(r"(?i):\s*(?=(?:NEW|OLD)\s*\.)", "", expr)
                expr = re.sub(r"(?i)\b(?:NEW|OLD)\s*\.\s*", "", expr)
                expr = self._qualify_tsql_udfs(self._map_now_in_sql(expr))
                pk = self._tsql_pk(bare_table)
                sql = (
                    f"UPDATE {bare_table} SET {col} = {expr} "
                    f"WHERE {pk} IN (SELECT {pk} FROM inserted)"
                )
                return EmbeddedDML(sql=sql, dialect="tsql")
        # Pattern (b): embedded DML keyed on NEW.<fk> -> set-based over inserted.
        if isinstance(node, EmbeddedDML):
            transformed = self._transform_embedded_dml(node)
            sql = self._tsql_setbased_rewrite(transformed.sql, bare_table)
            return EmbeddedDML(sql=self._qualify_tsql_udfs(sql), dialect="tsql")
        # Anything else (IF, etc.): fall back to the normal transform.
        return self._transform_node(node)

    def _tsql_setbased_rewrite(self, sql: str, trigger_table: str) -> str:
        """Rewrite a row-level ``UPDATE <tgt> <alias> SET … WHERE <alias>.<key> =
        NEW.<fk>`` into a set-based T-SQL update scoped to ``inserted``."""
        from unique.core.sql_split import split_leading_trivia

        # Match on the code, re-attach the trivia: a leading comment must not
        # hide the UPDATE (audit doc 04, P2).
        trivia, sql = split_leading_trivia(sql)
        m = re.match(r"(?is)\s*UPDATE\s+([\w\[\]\"`.]+)(?:\s+AS)?\s+(\w+)\s+SET\b", sql)
        if not m:
            return trivia + sql
        tgt, alias = m.group(1), m.group(2)
        bare = tgt.strip('[]"`').split(".")[-1]
        # Drop the target alias (T-SQL rejects ``UPDATE t AS a``); refer to the
        # target by its table name so a correlated subquery still resolves.
        sql = re.sub(
            rf"(?is)^(\s*)UPDATE\s+{re.escape(tgt)}(?:\s+AS)?\s+{re.escape(alias)}"
            r"\s+SET\b",
            rf"\g<1>UPDATE {bare} SET",
            sql,
            count=1,
        )
        sql = re.sub(rf"(?i)\b{re.escape(alias)}\s*\.", f"{bare}.", sql)
        # The outer correlation ``<tgt>.<key> = NEW.<fk>`` selects the affected
        # parent rows -> ``<tgt>.<key> IN (SELECT <fk> FROM inserted)``; a NEW.<fk>
        # left in a subquery correlates to the target row (``<tgt>.<key>``).
        mp = re.search(
            rf"(?i)\b{re.escape(bare)}\.(\w+)\s*=\s*(?:NEW|OLD)\s*\.\s*(\w+)", sql
        )
        if mp:
            key, fk = mp.group(1), mp.group(2)
            sql = (
                sql[: mp.start()]
                + f"{bare}.{key} IN (SELECT {fk} FROM inserted)"
                + sql[mp.end() :]
            )
            sql = re.sub(
                rf"(?i)\b(?:NEW|OLD)\s*\.\s*{re.escape(fk)}\b", f"{bare}.{key}", sql
            )
        return trivia + sql

    def _tsql_pk(self, table: str) -> str:
        registry = IDENTITY_COLUMNS.get() or {}
        return registry.get(table.lower(), "id")

    def _qualify_tsql_udfs(self, sql: str) -> str:
        """Qualify a bare scalar-UDF call ``fn(…)`` as ``dbo.fn(…)`` (T-SQL rejects
        an unqualified scalar UDF as an unknown built-in)."""
        funcs = USER_FUNCTIONS.get()
        if not funcs:
            return sql

        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            if name.lower() in funcs:
                return f"dbo.{name}("
            return m.group(0)

        return re.sub(r"(?i)(?<![.\w])(\w+)\s*\(", repl, sql)

    def _lit(self, value: ASTNode) -> str:
        if isinstance(value, Literal):
            if value.value is None:
                return "NULL"
            if value.dtype in ("string", "str"):
                return "'" + str(value.value).replace("'", "''") + "'"
            return str(value.value)
        return self._emit_fallback(value)

    def _emit_fallback(self, value: ASTNode) -> str:
        return value.sql if isinstance(value, RawSQL) else ""

    def _alter_becomes_create(self) -> bool:
        # T-SQL keeps ALTER PROCEDURE as-is.
        return False

    def _rewrites_trigger_pseudotables(self) -> bool:
        # T-SQL keeps inserted/deleted pseudo-tables as-is.
        return False

    def _warn_for_loop_unsupported(self) -> None:
        self._warnings.append(
            "FOR loop has no direct T-SQL equivalent. "
            "Manual conversion to WHILE loop required."
        )

    def _transform_loop(self, node: LoopStatement) -> ASTNode:
        # T-SQL has no bare LOOP; express it as WHILE 1=1.
        return WhileStatement(
            condition=RawSQL(sql="1=1", reason="infinite loop"),
            body=self._ensure_non_empty_body(self._transform_body(node.body)),
        )

    def _transform_null(self, node: NullStatement) -> ASTNode:
        return RawSQL(sql="-- NULL statement (no-op)", reason="no T-SQL equivalent")

    def _has_update_predicate(self) -> bool:
        # T-SQL keeps UPDATE(col) as-is.
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


register_transformer(TSqlTransformer.target_name, TSqlTransformer)
