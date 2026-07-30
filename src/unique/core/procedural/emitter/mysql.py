# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — mysql target."""

from __future__ import annotations

import dataclasses
import re

from unique.core.ast_nodes import (
    ASTNode,
    BeginEndBlock,
    CallStatement,
    ContinueStatement,
    CreateTriggerStatement,
    CursorDeclaration,
    DataType,
    ExitStatement,
    GotoStatement,
    IfStatement,
    LabelStatement,
    LoopStatement,
    NullStatement,
    ParameterDefinition,
    ReturnStatement,
    TryCatchBlock,
    WhileStatement,
)
from unique.core.procedural.emitter.base import (
    ProceduralEmitter,
    _select_list_columns,
    _strip_outer_parens,
    register_emitter,
)


class MySqlEmitter(ProceduralEmitter):
    """MySQL procedural emitter."""

    dialect_name = "mysql"

    # Built-in function names MySQL/MariaDB only recognize when the opening
    # parenthesis follows immediately (default sql_mode, no IGNORE_SPACE).
    # Token-joined expression text ("CAST ( x AS ... )") must be collapsed.
    # The second alternation is MySQL's documented space-sensitive keyword
    # functions (EXTRACT ( YEAR FROM x ) is a hard 1064 — sweep wave 15).
    _NO_SPACE_FUNCS = re.compile(
        r"(?i)\b(CAST|CONVERT|COUNT|SUM|MIN|MAX|AVG|COALESCE|IFNULL|NULLIF|"
        r"CONCAT|SUBSTRING|SUBSTR|TRIM|UPPER|LOWER|ABS|ROUND|NOW|CURDATE|"
        r"CURTIME|LENGTH|CHAR_LENGTH|GROUP_CONCAT|LAST_INSERT_ID|"
        r"EXTRACT|POSITION|ADDDATE|SUBDATE|DATE_ADD|DATE_SUB|BIT_AND|BIT_OR|"
        r"BIT_XOR|STD|STDDEV|STDDEV_POP|STDDEV_SAMP|VARIANCE|VAR_POP|"
        r"VAR_SAMP|MID|SYSDATE)\s+\("
    )

    def emit(self, node: ASTNode) -> str:
        return self._NO_SPACE_FUNCS.sub(lambda m: f"{m.group(1)}(", super().emit(node))

    #: Builtin names MySQL's parser claims at a routine-definition site:
    #: ``CREATE FUNCTION NOW()`` is a 1064 unless the name is backticked
    #: (an Oracle compatibility shim named ``now`` exists in real schemas).
    _BUILTIN_NAMES = frozenset(
        {"NOW", "SYSDATE", "CURDATE", "CURTIME", "POSITION", "TRIM", "REPLACE"}
    )

    def _keep_schema(self, schema: str) -> bool:
        # MySQL has no schema layer (a schema is a database); drop all.
        return False

    def _qualified_name(self, schema: str | None, name: str) -> str:
        out = super()._qualified_name(schema, name)
        if out.upper() in self._BUILTIN_NAMES:
            return f"`{out}`"
        return out

    def _emit_trigger(self, node: CreateTriggerStatement) -> str:
        # RETURN is illegal anywhere in a MySQL trigger; label the body block
        # so _emit_return can translate it to LEAVE (same as procedures).
        prev_label = self._proc_leave_label
        if self._body_has_any_return(list(node.body)):
            self._proc_leave_label = "trg_exit"
        else:
            self._proc_leave_label = None
        try:
            return self._emit_trigger_events(node)
        finally:
            self._proc_leave_label = prev_label

    def _emit_trigger_events(self, node: CreateTriggerStatement) -> str:
        # MySQL allows exactly one event per trigger; split AFTER INSERT,
        # UPDATE into one trigger per event (MariaDB rejects the multi-event
        # shell outright).
        events = tuple(node.events) if node.events else ()
        if len(events) <= 1:
            out = super()._emit_trigger(node)
            return self._resolve_event_predicates(out, events[0] if events else "")
        parts = [
            self._resolve_event_predicates(
                super()._emit_trigger(
                    dataclasses.replace(
                        node, name=f"{node.name}_{ev[:3].lower()}", events=(ev,)
                    )
                ),
                ev,
            )
            for ev in events
        ]
        return "\n\n".join(parts)

    @staticmethod
    def _resolve_event_predicates(sql: str, event: str) -> str:
        """Resolve PL/SQL INSERTING/UPDATING/DELETING inside a (split,
        single-event) MySQL trigger: the event is statically known, so the
        predicates become constants — except ``UPDATING('col')`` in an
        UPDATE trigger, which tests the column change null-safely."""
        if not event or not re.search(r"(?i)\b(?:INSERTING|UPDATING|DELETING)\b", sql):
            return sql
        event = event.upper()
        sql = re.sub(
            r"(?i)\bUPDATING\s*\(\s*'(\w+)'\s*\)",
            r"(NOT (NEW.\1 <=> OLD.\1))" if event == "UPDATE" else "(1 = 0)",
            sql,
        )
        for pred, ev in (
            ("INSERTING", "INSERT"),
            ("UPDATING", "UPDATE"),
            ("DELETING", "DELETE"),
        ):
            sql = re.sub(
                rf"(?i)\b{pred}\b",
                "(1 = 1)" if event == ev else "(1 = 0)",
                sql,
            )
        return sql

    def _tvf_unsupported_note(self) -> str:
        return (
            "MySQL has no table-returning functions; use a view or a procedure "
            "with a result set"
        )

    def _emit_loop(self, node: LoopStatement) -> str:
        # Each emitted loop gets a unique label (finding N5a: two nested loops
        # both named ``loop_lbl`` is MySQL error 1309). The label is pushed
        # before the body emits so an unlabeled LEAVE/ITERATE inside resolves
        # to this loop.
        label = self._push_loop_label(node.label)
        self._indent_level += 1
        body_lines = self._emit_indented_stmts(node.body)
        self._indent_level -= 1
        self._pop_loop_label()
        return "\n".join([f"{label}: LOOP", *body_lines, f"END LOOP {label};"])

    def _assignment_form(self, target: str, val: str) -> str:
        # A hoisted DECLARE default of ERROR_MESSAGE() (T-SQL CATCH): MySQL
        # reads the handler's condition via GET DIAGNOSTICS, not a function.
        # (The plain SET form is rewritten by the transformer; this covers
        # the assignment the emitter itself synthesizes when it splits a
        # mid-body DECLARE @v = <default>.)
        if re.fullmatch(r"(?is)\s*ERROR_MESSAGE\s*\(\s*\)\s*", val):
            return f"GET DIAGNOSTICS CONDITION 1 {target} = MESSAGE_TEXT;"
        return f"SET {target} = {val};"

    def _elsif_keyword(self) -> str:
        return "ELSEIF"

    def _emit_null(self, _node: NullStatement) -> str:
        # MySQL has no PL/SQL-style NULL statement; DO 0 is its no-op.
        return "DO 0;"

    def _emit_goto(self, node: GotoStatement) -> str:
        # MySQL has no GOTO. A bare comment carrier would leave an empty
        # THEN/loop body (1064), so pair the carrier with the DO 0 no-op.
        return (
            f"DO 0; /* UNIQUE-1172: GOTO {node.label} dropped -- MySQL has no GOTO; "
            "control flow not replicated (docs/03-unsupported.md) */"
        )

    def _emit_label(self, node: LabelStatement) -> str:
        # MySQL has no GOTO/label; carrier + DO 0 no-op (see _emit_goto).
        return (
            f"DO 0; /* UNIQUE-1173: label {node.name} dropped -- MySQL has no "
            "GOTO/label (docs/03-unsupported.md) */"
        )

    def _emit_guard_if(self, cond: str, body_lines: list[str]) -> str | None:
        # MySQL's IF accepts an EXISTS/subquery condition, so the guard is an
        # IF … THEN … END IF; rather than a scanned cursor.
        return "\n".join([f"IF {cond} THEN", *body_lines, "END IF;"])

    def _emit_numeric_for_loop(
        self, variable: str, start: str, end: str, reverse: bool, body_lines: list[str]
    ) -> str:
        # MySQL has no counting FOR; expand to WHILE inside a nested block so
        # the counter's DECLARE sits at a block start (required placement).
        init, cond, step = (
            (end, f"{variable} >= {start}", f"SET {variable} = {variable} - 1;")
            if reverse
            else (start, f"{variable} <= {end}", f"SET {variable} = {variable} + 1;")
        )
        indent = self._indent()
        lines = [
            "BEGIN",
            f"{indent}DECLARE {variable} INT DEFAULT {init};",
            f"{indent}WHILE {cond} DO",
            *body_lines,
            f"{indent}{indent}{step}",
            f"{indent}END WHILE;",
            "END;",
        ]
        return "\n".join(lines)

    def _emit_for_loop_body(
        self, variable: str, cursor_str: str, body_lines: list[str]
    ) -> str:
        # MySQL: explicit cursor with a NOT FOUND handler driving a loop. When
        # the select list is resolvable (a named cursor recorded at its
        # declaration, or an inline query) the expansion is complete and lives
        # in its own BEGIN ... END so the DECLAREs sit at a block start.
        # Otherwise the documented scaffold remains (developer completes it).
        named = re.fullmatch(r"[A-Za-z_]\w*", cursor_str.strip())
        if named:
            cur = cursor_str.strip()
            select_text = self._cursor_queries.get(cur.lower())
            declares_cursor = False
        else:
            cur = f"{variable}_cur"
            select_text = _strip_outer_parens(cursor_str)
            declares_cursor = True

        cols = _select_list_columns(select_text) if select_text else None
        if cols:
            fields = {
                m.group(1).lower()
                for line in body_lines
                for m in re.finditer(rf"(?i)\b{re.escape(variable)}\s*\.\s*(\w+)", line)
            }
            if not fields.issubset(set(cols)):
                cols = None  # a referenced field the list doesn't expose

        done = f"{variable}_done"
        if not cols:
            lines = [
                "-- UNIQUE-1174: Oracle implicit cursor FOR-loop expanded to an "
                "explicit MySQL cursor.",
                "-- Declare one variable per selected column and complete the "
                "FETCH INTO list.",
                f"DECLARE {done} INT DEFAULT FALSE;",
                f"DECLARE {cur} CURSOR FOR {cursor_str};",
                f"DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE;",
                f"OPEN {cur};",
                f"{variable}_loop: LOOP",
                f"{self._indent()}FETCH {cur} INTO /* col1, col2, ... */;",
                f"{self._indent()}IF {done} THEN LEAVE {variable}_loop; END IF;",
                *body_lines,
                "END LOOP;",
                f"CLOSE {cur};",
            ]
            return "\n".join(lines)

        fetch_vars = ", ".join(f"{variable}_{c}" for c in cols)
        rewritten = [
            re.sub(
                rf"(?i)\b{re.escape(variable)}\s*\.\s*(\w+)",
                lambda m: f"{variable}_{str(m.group(1)).lower()}",
                line,
            )
            for line in body_lines
        ]
        indent = self._indent()
        lines = [
            "-- UNIQUE-1175: cursor FOR-loop expanded; loop variables are TEXT "
            "(exact column types need --db-url metadata).",
            "BEGIN",
            *(f"{indent}DECLARE {variable}_{c} TEXT;" for c in cols),
            f"{indent}DECLARE {done} INT DEFAULT FALSE;",
        ]
        if declares_cursor:
            lines.append(f"{indent}DECLARE {cur} CURSOR FOR {select_text};")
        lines += [
            f"{indent}DECLARE CONTINUE HANDLER FOR NOT FOUND SET {done} = TRUE;",
            f"{indent}OPEN {cur};",
            f"{indent}{variable}_loop: LOOP",
            f"{indent}{indent}FETCH {cur} INTO {fetch_vars};",
            f"{indent}{indent}IF {done} THEN LEAVE {variable}_loop; END IF;",
            *rewritten,
            f"{indent}END LOOP;",
            f"{indent}CLOSE {cur};",
            "END;",
        ]
        return "\n".join(lines)

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        # MySQL puts the direction *before* the parameter name and does not
        # support per-parameter DEFAULT values; callers must always pass every
        # argument. The default is dropped (and surfaced as a warning by the
        # caller) rather than emitted as invalid syntax. Stored functions forbid
        # direction keywords entirely.
        dt = self._emit_data_type(p.data_type)
        direction_str = ""
        if not is_function:
            if p.direction in ("OUT", "INOUT"):
                direction_str = f"{p.direction} "
            elif p.direction == "IN":
                direction_str = "IN "
        return f"{direction_str}{p.name} {dt}"

    def _declare_default_op(self) -> str:
        return "DEFAULT"

    def _declare_prefix(self) -> str:
        return "DECLARE "

    def _not_null_spelling(self) -> str:
        # No NOT NULL variable modifier here; safe relaxation.
        return ""

    def _constant_spelling(self) -> str:
        # MySQL has no constant variables; the mutable declaration is a
        # safe relaxation (docs/03-unsupported.md).
        return ""

    def _emit_data_type(self, dt: DataType) -> str:
        out = super()._emit_data_type(dt)
        # MySQL rejects VARCHAR without a length; the unsized source form
        # (an Oracle VARCHAR2 parameter) is unbounded, so TEXT is faithful.
        if not dt.params and out.upper() in ("VARCHAR", "NVARCHAR"):
            return "TEXT"
        return out

    def _emit_cursor_decl(self, node: CursorDeclaration) -> str:
        # MySQL: DECLARE name CURSOR FOR <select>;
        query_str = (
            self._emit_node(node.query).rstrip().rstrip(";") if node.query else ""
        )
        if query_str:
            self._cursor_queries[node.name.lower()] = query_str
        body = f" FOR {query_str}" if query_str else ""
        return f"DECLARE {node.name} CURSOR{body};"

    def _wants_empty_parens(self) -> bool:
        return True

    def _emit_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_mysql_procedure_body(header, declarations, body_stmts)

    def _returns_clause(self, ret_type: str) -> str:
        return f"\nRETURNS {ret_type}\nDETERMINISTIC"

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        return self._emit_mysql_procedure_body(
            header, declarations, body_stmts, is_function=True
        )

    def _adjust_trigger_timing(self, timing: str) -> tuple[str, str]:
        # MySQL has no INSTEAD OF triggers (they apply to views in T-SQL/PG and
        # have no MySQL form). Document the substitution and fall back to BEFORE
        # so the trigger is at least syntactically valid for review.
        if timing.upper().startswith("INSTEAD OF"):
            note = (
                "-- UNIQUE-1176: MySQL has no INSTEAD OF trigger; emitted as BEFORE "
                "for review (original was INSTEAD OF, typically on a view).\n"
            )
            return note, "BEFORE"
        return "", timing

    def _trigger_header(
        self,
        name: str,
        node: CreateTriggerStatement,
        events: str,
        timing: str,
    ) -> list[str]:
        begin = (
            f"{self._proc_leave_label}: BEGIN" if self._proc_leave_label else "BEGIN"
        )
        return [
            f"CREATE TRIGGER {name}",
            f"{timing} {events} ON {node.table}",
            "FOR EACH ROW",
            begin,
        ]

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        # MySQL has no EXCEPTION block; the catch logic goes into a
        # DECLARE ... HANDLER declared at the top of the block, before the
        # protected (try) statements.
        lines = ["BEGIN"]
        self._indent_level += 1
        condition = (
            "NOT FOUND" if node.catch_kind == "NO_DATA_FOUND" else "SQLEXCEPTION"
        )
        lines.append(f"{self._indent()}DECLARE EXIT HANDLER FOR {condition}")
        lines.append(f"{self._indent()}BEGIN")
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.catch_body))
        self._indent_level -= 1
        lines.append(f"{self._indent()}END;")
        lines.extend(self._emit_indented_stmts(node.try_body))
        self._indent_level -= 1
        lines.append("END;")
        return "\n".join(lines)

    def _emit_return(self, node: ReturnStatement) -> str:
        # In a MySQL procedure, RETURN is illegal whether or not it has a value
        # (a T-SQL procedure RETURN <code> has no MySQL equivalent). Translate
        # to LEAVE of the labeled procedure block; document a discarded value.
        if not self._in_mysql_function and self._proc_leave_label:
            if node.value:
                val = self._emit_node(node.value)
                return (
                    f"LEAVE {self._proc_leave_label};  "
                    f"-- UNIQUE-1177: discarded procedure RETURN value ({val})"
                )
            return f"LEAVE {self._proc_leave_label};"
        if node.value:
            val = self._emit_node(node.value)
            return f"RETURN {val};"
        return "RETURN;"

    def _emit_begin_transaction(self, name: str | None) -> str:
        return "START TRANSACTION;"

    def _sleep_call(self, secs: str) -> str:
        return f"DO SLEEP({secs});"

    @classmethod
    def _has_loop_control(cls, stmts: tuple[ASTNode, ...]) -> bool:
        """Whether ``stmts`` contain a LEAVE/ITERATE (from BREAK/CONTINUE) that
        belongs to *this* loop — i.e. reachable without crossing a nested loop
        (a break inside a nested loop targets that inner loop)."""
        for s in stmts:
            if isinstance(s, (ExitStatement, ContinueStatement)):
                return True
            if isinstance(s, IfStatement):
                if cls._has_loop_control(s.then_body) or cls._has_loop_control(
                    s.else_body
                ):
                    return True
            elif isinstance(s, BeginEndBlock) and cls._has_loop_control(s.statements):
                return True
        return False

    def _emit_while(self, node: WhileStatement) -> str:
        # MySQL spells it WHILE … DO … END WHILE; (the PL/SQL LOOP form is a
        # syntax error here — audit 2026-07-08, C3). A LEAVE/ITERATE needs a loop
        # label, so label the loop ``loop_lbl`` (matching _emit_exit/_emit_continue)
        # when the body contains one.
        cond = self._emit_node(node.condition)
        labeled = node.label is not None or self._has_loop_control(node.body)
        label = self._push_loop_label(node.label) if labeled else None
        prefix = f"{label}: " if label else ""
        lines = [f"{prefix}WHILE {cond} DO"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.body))
        self._indent_level -= 1
        if label:
            self._pop_loop_label()
        lines.append(f"END WHILE{f' {label}' if label else ''};")
        return "\n".join(lines)

    def _emit_call(self, node: CallStatement) -> str:
        # MySQL has no schema layer, so any qualifier is dropped by name lookup.
        # Named arguments were already lowered to positional by the transformer
        # (MySQL has no ``name => value`` association — audit 2026-07-08, C5).
        return f"CALL {node.name}({node.args});"

    def _emit_execute_into(
        self,
        expr: str,
        params: list[str],
        into_vars: list[str],
        immediate: bool,
        strict: bool = False,
    ) -> str:
        # MySQL PREPARE/EXECUTE cannot capture a result into variables unless
        # the dynamic string itself selects INTO session variables — which we
        # cannot rewrite reliably. Document instead of shipping invalid SQL.
        original = f"EXECUTE IMMEDIATE {expr} INTO {', '.join(into_vars)}"
        commented = "\n".join(f"-- {ln}" for ln in original.splitlines())
        return (
            "-- UNIQUE-1178: dynamic SELECT INTO variable has no direct MySQL "
            "form (rewrite the dynamic string to select INTO @session "
            f"variables); original:\n{commented}\nDO 0;"
        )

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        # MySQL: distinguish three forms that all arrive as a captured
        # expression here:
        #   1. EXEC sp_executesql @sql, N'<decls>', @p1, ...  -> dynamic SQL
        #   2. EXEC proc_name @a OUTPUT, 'b', ...             -> a routine call
        #   3. EXEC @sql / EXEC ('...')                       -> dynamic SQL
        return self._emit_mysql_execute(expr, params, immediate)

    def _emit_exit(self, node: ExitStatement) -> str:
        cond = self._emit_node(node.condition) if node.condition else ""
        cond = self._translate_cursor_attrs(cond)
        # MySQL uses LEAVE with a loop label; a bare EXIT targets the nearest
        # enclosing loop's unique label (finding N5a).
        label = self._resolve_loop_label(node.label)
        if cond:
            return f"IF {cond} THEN LEAVE {label}; END IF;"
        return f"LEAVE {label};"

    def _emit_continue(self, node: ContinueStatement) -> str:
        # MySQL spells CONTINUE as ITERATE <label>.
        return f"ITERATE {self._resolve_loop_label(node.label)};"

    def _translate_cursor_attrs(self, expr: str) -> str:
        if not expr:
            return expr
        # MySQL signals end-of-cursor via a NOT FOUND handler; flag it.
        expr = re.sub(
            r"\w+\s*%\s*NOTFOUND",
            "done /* set by CONTINUE HANDLER FOR NOT FOUND */",
            expr,
            flags=re.I,
        )
        return expr


register_emitter(MySqlEmitter.dialect_name, MySqlEmitter)
