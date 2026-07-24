# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural AST transformer — mysql target."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import replace

from unique.core.ast_nodes import (
    AssignmentStatement,
    ASTNode,
    CallStatement,
    CreateFunctionStatement,
    CreateProcedureStatement,
    CreateTriggerStatement,
    CursorDeclaration,
    DataType,
    DeclareStatement,
    ExceptionBlock,
    ExecuteStatement,
    RawSQL,
    SelectIntoStatement,
    SetVariableStatement,
    StatementList,
    TryCatchBlock,
)
from unique.core.procedural.transformer.base import (
    ProceduralTransformer,
    register_transformer,
)


class MySqlTransformer(ProceduralTransformer):
    """Transforms toward MySQL."""

    target_name = "mysql"

    def _supports_top_level_anonymous_block(self) -> bool:
        # MySQL has no procedural code (BEGIN … END, loops, dynamic SQL in a
        # cursor) outside a stored routine, so a control-flow anonymous block
        # cannot run at the top level; it is documented instead.
        return False

    _ERROR_MESSAGE_RE = re.compile(r"(?i)^\s*ERROR_MESSAGE\s*\(\s*\)\s*$")

    def _error_message_assignment(self, name: str, value: ASTNode) -> ASTNode | None:
        """T-SQL ``SET @msg = ERROR_MESSAGE()`` inside a CATCH: MySQL reads
        the handler's condition via GET DIAGNOSTICS (a statement, not a
        function)."""
        if not isinstance(value, RawSQL) or not self._ERROR_MESSAGE_RE.match(value.sql):
            return None
        new_name = self._transform_var_name(name)
        return RawSQL(
            sql=f"GET DIAGNOSTICS CONDITION 1 {new_name} = MESSAGE_TEXT;",
            reason="ERROR_MESSAGE() capture",
        )

    def _transform_set_variable(self, node: SetVariableStatement) -> ASTNode:
        replaced = self._error_message_assignment(node.name, node.value)
        if replaced is not None:
            return replaced
        return super()._transform_set_variable(node)

    def _transform_assignment(self, node: AssignmentStatement) -> ASTNode:
        replaced = self._error_message_assignment(node.target, node.value)
        if replaced is not None:
            return replaced
        return super()._transform_assignment(node)

    def _folds_exception_scope(self) -> bool:
        return True

    def _transform_exception_block(self, node: ExceptionBlock) -> ASTNode:
        # Reached only when the EXCEPTION section had no preceding siblings
        # (see _fold_exception_scope): flatten to a handler-only block.
        body: list[ASTNode] = []
        for handler in node.handlers:
            body.extend(handler.body)
        return TryCatchBlock(
            try_body=(),
            catch_body=self._transform_body(tuple(body)),
        )

    #: MySQL's table value constructor needs a ROW() per row: ``(VALUES (1),(2))``
    #: is a syntax error (1064); ``(VALUES ROW(1), ROW(2))`` is the valid form.
    #: The SELECT INTO tail is a FROM context, so any VALUES here is a table
    #: constructor (never an INSERT's value list).
    _VALUES_CTOR_RE = re.compile(r"(?i)(\bVALUES\s+)(\([^)]*\)(?:\s*,\s*\([^)]*\))*)")

    @classmethod
    def _mysql_values_row(cls, sql: str) -> str:
        def _wrap(m: re.Match[str]) -> str:
            rows = re.findall(r"\([^)]*\)", m.group(2))
            return m.group(1) + ", ".join("ROW" + r for r in rows)

        return cls._VALUES_CTOR_RE.sub(_wrap, sql)

    def _transform_select_into(self, node: SelectIntoStatement) -> ASTNode:
        result = super()._transform_select_into(node)
        if not isinstance(result, SelectIntoStatement):
            return result
        if "VALUES" in result.rest_sql.upper():
            result = dataclasses.replace(
                result, rest_sql=self._mysql_values_row(result.rest_sql)
            )
        if not any(re.match(r"(?i)^(?:NEW|OLD)\s*\.", v) for v in result.into_vars):
            return result
        # MySQL's SELECT ... INTO cannot target the trigger pseudo-row:
        # route through session variables, then SET NEW.col = @var.
        tmp_vars = [f"@uq_sel{i}" for i in range(len(result.into_vars))]
        assigns = tuple(
            RawSQL(sql=f"SET {target} = {tmp};", reason="pseudo-row INTO")
            for target, tmp in zip(result.into_vars, tmp_vars, strict=True)
            if re.match(r"(?i)^(?:NEW|OLD)\s*\.", target)
        )
        keeps = tuple(
            RawSQL(sql=f"SET {target} = {tmp};", reason="pseudo-row INTO")
            for target, tmp in zip(result.into_vars, tmp_vars, strict=True)
            if not re.match(r"(?i)^(?:NEW|OLD)\s*\.", target)
        )
        select_stmt = dataclasses.replace(result, into_vars=tuple(tmp_vars))
        return StatementList(statements=(select_stmt, *assigns, *keeps))

    def _fetch_status_forms(self) -> tuple[str, str] | None:
        # MySQL signals cursor exhaustion via a NOT FOUND handler: lower the
        # check to a flag; _inject_fetch_done adds the flag + handler.
        self._used_fetch_done = True
        return ("NOT v_fetch_done", "v_fetch_done")

    def _inject_fetch_done(self, result: ASTNode) -> ASTNode:
        """Insert ``v_fetch_done`` and its CONTINUE HANDLER after the last
        top-level declaration of a routine whose body checks the flag
        (handlers must follow variable/cursor declarations in MySQL)."""
        used, self._used_fetch_done = self._used_fetch_done, False
        body = getattr(result, "body", None)
        if not used or not isinstance(body, tuple):
            return result

        def is_decl(stmt: ASTNode) -> bool:
            return isinstance(stmt, (DeclareStatement, CursorDeclaration)) or (
                isinstance(stmt, StatementList)
                and all(
                    isinstance(x, (DeclareStatement, CursorDeclaration))
                    for x in stmt.statements
                )
            )

        # MySQL declaration order: variables, then cursors, then handlers —
        # the flag goes before the first declaration (safely ahead of any
        # cursor) and the handler after the last one.
        first = next((i for i, x in enumerate(body) if is_decl(x)), 0)
        last = max((i + 1 for i, x in enumerate(body) if is_decl(x)), default=0)
        flag = DeclareStatement(
            name="v_fetch_done",
            data_type=DataType(name="INT"),
            default=RawSQL(sql="FALSE", reason="cursor end-of-data flag"),
        )
        handler = RawSQL(
            sql="DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done = TRUE;",
            reason="cursor end-of-data handler",
        )
        new_body = body[:first] + (flag,) + body[first:last] + (handler,) + body[last:]
        return replace(result, body=new_body)  # type: ignore[call-arg]

    @staticmethod
    def _reorder_declarations(result: ASTNode) -> ASTNode:
        """MySQL requires DECLARE <variable> before DECLARE <cursor> (error 1337,
        "variable declaration after cursor"). Oracle/T-SQL allow either order, so
        reorder the routine's leading declaration block — variables first, then
        cursors — preserving relative order within each group."""
        body = getattr(result, "body", None)
        if not isinstance(body, tuple):
            return result
        lead: list[ASTNode] = []
        rest_start = 0
        for i, s in enumerate(body):
            if isinstance(s, (DeclareStatement, CursorDeclaration)):
                lead.append(s)
                rest_start = i + 1
            elif (
                isinstance(s, StatementList)
                and s.statements
                and all(
                    isinstance(x, (DeclareStatement, CursorDeclaration))
                    for x in s.statements
                )
            ):
                lead.extend(s.statements)
                rest_start = i + 1
            else:
                break
        variables = [d for d in lead if isinstance(d, DeclareStatement)]
        cursors = [d for d in lead if isinstance(d, CursorDeclaration)]
        if not variables or not cursors:
            return result
        # Already in the right order? (all variables precede all cursors)
        if lead == variables + cursors:
            return result
        new_body = (*variables, *cursors, *body[rest_start:])
        return replace(result, body=new_body)  # type: ignore[call-arg]

    def _map_cursor_attributes(self, sql: str) -> str:
        if self._source != "oracle":
            return sql
        sql = re.sub(r"(?i)\bSQL\s*%\s*ROWCOUNT\b", "ROW_COUNT()", sql)
        sql = re.sub(r"(?i)\bSQL\s*%\s*NOTFOUND\b", "(ROW_COUNT() = 0)", sql)
        sql = re.sub(r"(?i)\bSQL\s*%\s*FOUND\b", "(ROW_COUNT() > 0)", sql)
        if re.search(r"(?i)\b\w+\s*%\s*(?:NOT)?FOUND\b", sql):
            _forms = self._fetch_status_forms()
            if _forms is not None:
                found, notfound = _forms
                sql = re.sub(r"(?i)\b\w+\s*%\s*NOTFOUND\b", notfound, sql)
                sql = re.sub(r"(?i)\b\w+\s*%\s*FOUND\b", found, sql)
        if re.search(r"(?i)\b\w+\s*%\s*ROWCOUNT\b", sql):
            self._used_fetch_done = True  # the increment guards on it
            sql = re.sub(
                r"(?i)\b(\w+)\s*%\s*ROWCOUNT\b",
                lambda m: f"uq_{m.group(1).lower()}_rc",
                sql,
            )
        return sql

    def _rc_declare(self, name: str) -> ASTNode | None:
        return DeclareStatement(
            name=f"uq_{name}_rc",
            data_type=DataType(name="INT"),
            default=RawSQL(sql="0", reason="cursor rowcount counter"),
        )

    def _rc_increment_sql(self, name: str) -> str:
        # Guarded on the NOT FOUND flag: a FETCH past the end must not count.
        return (
            f"IF v_fetch_done = FALSE THEN SET uq_{name}_rc = uq_{name}_rc + 1; "
            "END IF;"
        )

    def _transform_procedure(self, node: CreateProcedureStatement) -> ASTNode:
        return self._inject_fetch_done(
            self._reorder_declarations(
                self._emulate_cursor_rowcounts(super()._transform_procedure(node))
            )
        )

    @classmethod
    def _has_dynamic_sql(cls, node: ASTNode) -> bool:
        """Whether a routine body runs dynamic SQL (EXECUTE / EXECUTE IMMEDIATE),
        anywhere including nested control flow."""
        if isinstance(node, ExecuteStatement):
            return True
        for value in vars(node).values():
            items = value if isinstance(value, tuple) else (value,)
            for item in items:
                if isinstance(item, ASTNode) and cls._has_dynamic_sql(item):
                    return True
        return False

    def _transform_function(self, node: CreateFunctionStatement) -> ASTNode:
        # A void PG function that runs dynamic SQL must become a MySQL PROCEDURE:
        # a MySQL function forbids dynamic SQL (error 1336), a procedure allows it.
        # (A plain void function without dynamic SQL keeps the neutral scalar form
        # — see TestReturnsVoid.)
        is_void = node.return_type is None or node.return_type.name.upper() == "VOID"
        if is_void and any(self._has_dynamic_sql(s) for s in node.body):
            proc = CreateProcedureStatement(
                name=node.name,
                schema=node.schema,
                parameters=node.parameters,
                body=node.body,
                or_replace=node.or_replace,
            )
            return self._transform_procedure(proc)
        return self._inject_fetch_done(
            self._reorder_declarations(super()._transform_function(node))
        )

    def _transform_trigger(self, node: CreateTriggerStatement) -> ASTNode:
        return self._inject_fetch_done(
            self._reorder_declarations(super()._transform_trigger(node))
        )

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

    def _noop_sql(self) -> str:
        return "DO 0;"

    def _fix_target_dml(self, sql: str) -> str:
        sql = self._expr._mysql_string_concat(sql)
        sql = self._mysql_clean_dml(sql)
        sql = self._mysql_fix_cast_max(sql)
        sql = self._mysql_cast_types(sql)
        sql = self._mysql_string_split(sql)
        return sql

    def _transform_call(self, node: CallStatement) -> ASTNode:
        """MySQL CALL has no named-argument association (audit 2026-07-08,
        C5): lower ``name => value`` arguments to positional, warned — the
        values keep their order, which matches the declaration order in
        generated migration scripts but is not guaranteed in hand-written
        calls."""
        out = super()._transform_call(node)
        if isinstance(out, CallStatement) and out.args and "=>" in out.args:
            self._warnings.append(
                "MySQL CALL has no named arguments; passed positionally "
                "(verify the argument order matches the declaration)"
            )
            args = re.sub(r"\w+\s*=>\s*", "", out.args)
            return CallStatement(name=out.name, args=args, schema=out.schema)
        return out

    def _update_predicate(self, col: str) -> str | None:
        return f"NOT (NEW.{col} <=> OLD.{col})"

    #: MySQL CAST accepts a fixed target set (SIGNED/CHAR/…); foreign
    #: spellings in procedural expression text (the DML pipeline maps
    #: them via _CAST_TYPE_MAP — this is its dual-pipeline mirror,
    #: wave 146: ``RETURN CAST(p1 AS text)`` was a hard 1064).
    _MYSQL_CAST_TYPE_MAP = {
        "text": "CHAR",
        "varchar": "CHAR",
        "int": "SIGNED",
        "integer": "SIGNED",
        "bigint": "SIGNED",
        "smallint": "SIGNED",
        "tinyint": "SIGNED",
        "boolean": "SIGNED",
        "bool": "SIGNED",
    }

    _MYSQL_CAST_RE = re.compile(
        r"(?i)(\bCAST\s*\([^()]*?\bAS\s+)"
        r"(text|varchar|int|integer|bigint|smallint|tinyint|boolean|bool)"
        r"(\s*[\)\(])"
    )

    def _mysql_cast_types(self, sql: str) -> str:
        def fix(seg: str) -> str:
            return self._MYSQL_CAST_RE.sub(
                lambda m: m.group(1)
                + self._MYSQL_CAST_TYPE_MAP[m.group(2).lower()]
                + m.group(3),
                seg,
            )

        return self._map_outside_strings(sql, fix)

    def _fix_raw_sql_target(self, sql: str) -> str:
        if self._source == "postgresql":
            # plpgsql's FOUND flag (set by the last DML): this
            # target's row-count predicate, outside string literals.
            sql = self._map_outside_strings(
                sql,
                lambda seg: re.sub(r"(?i)\bFOUND\b", "(ROW_COUNT() > 0)", seg),
            )
        mt = re.match(
            r"(?is)^\s*ALTER\s+TRIGGER\s+(\w+)\s+(ENABLE|DISABLE)\s*;?\s*$",
            sql,
        )
        if mt:
            # MySQL cannot enable/disable triggers (only DROP/recreate).
            self._warnings.append(
                f"ALTER TRIGGER {mt.group(1)} {mt.group(2).upper()} has no "
                "MySQL equivalent (triggers cannot be disabled); preserved "
                "as a comment"
            )
            return (
                f"-- UNIQUE: no MySQL equivalent: ALTER TRIGGER "
                f"{mt.group(1)} {mt.group(2).upper()}\nDO 0;"
            )
        sql = self._expr._mysql_trunc(sql)
        sql = self._expr._mysql_pipes_to_concat(sql)
        sql = self._expr._mysql_normalize_funcs(sql)
        sql = self._expr._mysql_string_concat(sql)
        sql = self._mysql_clean_dml(sql)
        sql = self._mysql_fix_cast_max(sql)
        sql = self._mysql_cast_types(sql)
        sql = self._mysql_string_split(sql)
        return sql


register_transformer(MySqlTransformer.target_name, MySqlTransformer)
