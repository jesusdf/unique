# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Procedural SQL emitter — oracle target."""

from __future__ import annotations

import re

from unique.core.ast_nodes import (
    AnonymousBlock,
    ASTNode,
    CallStatement,
    CreateTriggerStatement,
    DeclareStatement,
    ParameterDefinition,
    PrintStatement,
    RaiseErrorStatement,
    ReturnStatement,
    SelectIntoStatement,
)
from unique.core.procedural.emitter.base import (
    _SQL_ONLY_IN_PLSQL,
    ProceduralEmitter,
    register_emitter,
)

_SIZE_RE = re.compile(r"\(\s*\d+\s*(?:,\s*\d+\s*)?\)")

# A *bare* Oracle DECIMAL/NUMERIC/DEC is NUMBER(38, 0) — it silently rounds to an
# integer. Once the length/precision is stripped for a parameter/RETURN position,
# these must become NUMBER (unconstrained, so the value keeps its own scale);
# otherwise e.g. a tax function returning 5.55 comes back as 6 (PLS-00103 aside).
_BARE_NUMERIC_TO_NUMBER = {"DECIMAL": "NUMBER", "NUMERIC": "NUMBER", "DEC": "NUMBER"}


def _unconstrained(data_type: str) -> str:
    """Strip length/precision from a type for parameter/RETURN position.

    Oracle rejects constrained types on formal parameters and function
    return clauses (PLS-00103); ``NUMBER(5, 2)`` must become ``NUMBER``. A bare
    ``DECIMAL``/``NUMERIC``/``DEC`` further becomes ``NUMBER`` so it does not
    default to integer scale.
    """
    stripped = _SIZE_RE.sub("", data_type).strip()
    return _BARE_NUMERIC_TO_NUMBER.get(stripped.upper(), stripped)


class OracleEmitter(ProceduralEmitter):
    """Oracle PL/SQL procedural emitter."""

    dialect_name = "oracle"

    def _procedure_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}PROCEDURE {name}"

    def _keep_schema(self, schema: str) -> bool:
        # 'dbo' is T-SQL's default schema and has no Oracle counterpart.
        return schema.lower() != "dbo"

    def _assignment_via_select(self, target: str, val: str) -> str | None:
        # Oracle PL/SQL forbids a subquery inside an expression (PLS-00405) and
        # rejects a SQL-only operator like CAST in a procedural expression
        # (PLS-00103), so `x := (SELECT …)` / `x := LOWER(CAST(…))` is invalid.
        # Evaluate the whole expression in SQL context instead:
        #   SELECT <expr> INTO x FROM DUAL;
        # DUAL yields exactly one row (NULL for a no-row scalar subquery), matching
        # T-SQL's `SET @x = …` and avoiding NO_DATA_FOUND.
        if re.search(_SQL_ONLY_IN_PLSQL, val):
            return f"SELECT {val.strip()} INTO {target} FROM DUAL;"
        return None

    def _tvf_unsupported_note(self) -> str:
        return (
            "Oracle needs a pipelined function over a declared collection type; "
            "review manually"
        )

    def _emit_procedure_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        self._in_oracle_procedure = True
        return self._emit_oracle_procedure_body(header, declarations, body_stmts)

    def _emit_return(self, node: ReturnStatement) -> str:
        # An Oracle procedure's RETURN cannot carry a value (PLS-00372); a T-SQL
        # ``RETURN <code>`` has no equivalent. Emit a bare RETURN and document the
        # discarded value. A function keeps ``RETURN <value>``.
        if getattr(self, "_in_oracle_procedure", False) and node.value:
            val = self._emit_node(node.value)
            return f"RETURN;  -- UNIQUE: discarded procedure RETURN value ({val})"
        # A function RETURN whose value uses a SQL-only operator (CAST, a SQL-only
        # builtin like STANDARD_HASH, a scalar subquery) is invalid in a PL/SQL
        # expression (PLS-00201/00103). Evaluate it in SQL context and return the
        # result via a nested block.
        if node.value:
            val = self._emit_node(node.value)
            rt = getattr(self, "_oracle_fn_return_type", None)
            if rt and _SQL_ONLY_IN_PLSQL.search(val):
                return (
                    "DECLARE\n"
                    f"    v_unique_ret {rt};\n"
                    "BEGIN\n"
                    f"    SELECT {val} INTO v_unique_ret FROM DUAL;\n"
                    "    RETURN v_unique_ret;\n"
                    "END;"
                )
        return super()._emit_return(node)

    def _function_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}FUNCTION {name}"

    def _returns_clause(self, ret_type: str) -> str:
        # Keep the constrained type for a possible RETURN-via-SELECT-INTO local
        # (the RETURN clause itself must be unconstrained).
        self._oracle_fn_return_type = ret_type
        return f"\nRETURN {_unconstrained(ret_type)}"

    def _emit_param(
        self,
        p: ParameterDefinition,
        idx: int,
        params: tuple[ParameterDefinition, ...],
        is_function: bool,
    ) -> str:
        # Oracle spells out IN for every parameter direction. Formal
        # parameters (and RETURN types) must use unconstrained types:
        # NUMBER(10) or VARCHAR2(50) raise PLS-00103 in a parameter list
        # (audit 2026-07-02, S1-11).
        dt = _unconstrained(self._emit_data_type(p.data_type))
        # Oracle rejects a DEFAULT on an OUT/IN OUT parameter (PLS-00230); T-SQL
        # allows one (``@p type = NULL OUTPUT``). Keep it only for IN.
        default_str = (
            f" DEFAULT {self._emit_node(p.default)}"
            if p.default and p.direction == "IN"
            else ""
        )
        direction_str = f"{p.direction} " if p.direction != "IN" else "IN "
        return f"{p.name} {direction_str}{dt}{default_str}"

    def _emit_select_into(self, node: SelectIntoStatement) -> str:
        base = super()._emit_select_into(node)
        if not node.tsql_assignment:
            return base
        # T-SQL "SELECT @v = col ..." leaves @v unchanged when no row
        # matches; Oracle SELECT INTO raises NO_DATA_FOUND instead, which
        # would make a following "IF v IS NULL" guard unreachable (audit
        # 2026-07-02, S2-3). A nested block with an empty handler restores
        # the T-SQL semantics.
        return (
            "BEGIN\n"
            f"    {base}\n"
            "EXCEPTION\n"
            "    WHEN NO_DATA_FOUND THEN\n"
            "        NULL;  -- T-SQL leaves the variables unchanged\n"
            "END;"
        )

    def _emit_print(self, node: PrintStatement) -> str:
        return f"DBMS_OUTPUT.PUT_LINE({self._emit_node(node.expression)});"

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        msg = self._emit_node(node.message) if node.message else "'Error'"
        # Message text preserved; T-SQL user error numbers 50000-50999 map
        # onto Oracle's -20000..-20999 user range (audit 2026-07-02, S2-2).
        text, number, _ = self._raise_parts(msg)
        code = -20001
        if number is not None and 50000 <= int(number) <= 50999:
            code = -(20000 + (int(number) - 50000))
        payload = text or number or msg
        return f"RAISE_APPLICATION_ERROR({code}, {payload});"

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        self._in_oracle_procedure = False
        return self._emit_oracle_procedure_body(header, declarations, body_stmts)

    def _join_trigger_events(self, events: tuple[str, ...]) -> str:
        """Oracle separates trigger events with ``OR`` (``INSERT OR UPDATE``);
        a comma list is a syntax error (ORA-00969)."""
        return " OR ".join(events) if events else "UPDATE"

    #: A ``:NEW.col`` / ``:OLD.col`` pseudo-record reference in emitted PL/SQL.
    _ROW_REF_RE = re.compile(r"(?i):\s*(NEW|OLD)\s*\.\s*(\w+)")

    def _emit_trigger(self, node: CreateTriggerStatement) -> str:
        # A row-level AFTER trigger whose body re-reads its own triggering table
        # (a child→parent re-aggregation, legal on MySQL/PostgreSQL) raises
        # ORA-04091 (mutating table) on Oracle. Synthesize a COMPOUND TRIGGER
        # that collects the affected keys per row and re-aggregates once in AFTER
        # STATEMENT, when the table is no longer mutating.
        if (
            not node.compound
            and not node.execute_function
            and node.for_each == "ROW"
            and node.timing.upper() == "AFTER"
        ):
            synthesized = self._synthesize_mutating_safe_trigger(node)
            if synthesized is not None:
                return synthesized
        if node.compound or node.execute_function:
            return super()._emit_trigger(node)
        # Oracle requires trigger-local variables in a DECLARE section before
        # BEGIN (T-SQL declares them inline in the body). Split them out and reuse
        # the procedure-body emitter (DECLARE instead of IS; subquery-initialised
        # declarations are hoisted to SELECT … INTO the same way).
        name = self._qualified_name(node.schema, node.name)
        events = self._join_trigger_events(node.events)
        note, timing = self._adjust_trigger_timing(node.timing)
        header_lines = self._trigger_header(name, node, events, timing)
        header_lines = [ln for ln in header_lines if ln != "BEGIN"]
        declarations, body_stmts = self._split_declarations(node.body)
        self._in_oracle_procedure = True  # a trigger RETURN cannot carry a value
        return note + self._emit_oracle_procedure_body(
            "\n".join(header_lines),
            declarations,
            body_stmts,
            decl_keyword="DECLARE",
            no_decl_keyword="",
        )

    def _body_reads_table(self, body_text: str, table: str) -> bool:
        """Whether the trigger body reads/writes its own triggering *table* (in a
        FROM/JOIN/UPDATE/INTO position, not via the ``:NEW.``/``:OLD.`` record) —
        the mutating-table hazard on a row-level Oracle trigger."""
        bare = table.strip('[]"`').split(".")[-1]
        return bool(
            re.search(
                rf"(?i)\b(?:FROM|JOIN|UPDATE|INTO)\s+{re.escape(bare)}\b", body_text
            )
        )

    def _synthesize_mutating_safe_trigger(
        self, node: CreateTriggerStatement
    ) -> str | None:
        """Rewrite a mutating-table-prone row-level trigger into a COMPOUND
        TRIGGER, or ``None`` when it is not the recognized re-aggregation shape
        (no self-read, or no ``:NEW.``/``:OLD.`` key to collect)."""
        self._indent_level = 0
        body_text = "\n".join(self._emit_node(s) for s in node.body).strip()
        if not self._body_reads_table(body_text, node.table):
            return None
        # Collect the distinct :NEW./:OLD. column refs (first-appearance order),
        # each backed by its own PLS_INTEGER-indexed collection.
        keys: dict[tuple[str, str], str] = {}
        for m in self._ROW_REF_RE.finditer(body_text):
            k = (m.group(1).upper(), m.group(2))
            if k not in keys:
                keys[k] = f"unique_key_{len(keys) + 1}"
        if not keys:
            return None
        loop_body = self._ROW_REF_RE.sub(
            lambda m: f"{keys[(m.group(1).upper(), m.group(2))]}(unique_i)", body_text
        )
        name = self._qualified_name(node.schema, node.name)
        events = self._join_trigger_events(node.events)
        bare_table = node.table.strip('[]"`').split(".")[-1]

        decls: list[str] = []
        collects = ["        g_n := g_n + 1;"]
        for idx, ((kind, col), var) in enumerate(keys.items(), start=1):
            typ = f"unique_kt_{idx}"
            decls.append(
                f"    TYPE {typ} IS TABLE OF {bare_table}.{col}%TYPE "
                "INDEX BY PLS_INTEGER;"
            )
            decls.append(f"    {var} {typ};")
            collects.append(f"        {var}(g_n) := :{kind}.{col};")
        decls.append("    g_n PLS_INTEGER := 0;")

        loop_lines = [f"            {line}" for line in loop_body.split("\n")]
        prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
        lines = [
            f"{prefix}TRIGGER {name}",
            f"FOR {events} ON {node.table}",
            "COMPOUND TRIGGER",
            *decls,
            "",
            "    AFTER EACH ROW IS",
            "    BEGIN",
            *collects,
            "    END AFTER EACH ROW;",
            "",
            "    AFTER STATEMENT IS",
            "    BEGIN",
            "        FOR unique_i IN 1 .. g_n LOOP",
            *loop_lines,
            "        END LOOP;",
            "    END AFTER STATEMENT;",
            "END;",
        ]
        return "\n".join(lines)

    def _trigger_header(
        self,
        name: str,
        node: CreateTriggerStatement,
        events: str,
        timing: str,
    ) -> list[str]:
        prefix = "CREATE OR REPLACE " if node.or_replace else "CREATE "
        lines = [f"{prefix}TRIGGER {name}", f"{node.timing} {events} ON {node.table}"]
        if node.for_each == "ROW":
            lines.append("FOR EACH ROW")
        lines.append("BEGIN")
        return lines

    def _trigger_end(self) -> str:
        return "END;"

    def _emit_anonymous_block(self, node: AnonymousBlock) -> str:
        """Oracle runs a top-level statement sequence as a PL/SQL anonymous
        block: ``[DECLARE …] BEGIN … END;``. Procedure calls and assignments are
        only valid inside such a block, so always wrap (even a single call)."""
        decls = [s for s in node.statements if isinstance(s, DeclareStatement)]
        body = [s for s in node.statements if not isinstance(s, DeclareStatement)]
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
        lines.append("END;")
        return "\n".join(lines)

    def _emit_call(self, node: CallStatement) -> str:
        # Oracle invokes a procedure by bare name inside a PL/SQL block; the
        # surrounding anonymous block supplies BEGIN/END.
        name = self._qualified_name(node.schema, node.name)
        if not node.args.strip():
            return f"{name}();"
        args = self._wrap_date_args(node.name, self._split_exec_args(node.args))
        return f"{name}({', '.join(args)});"

    def _wrap_date_args(self, proc_name: str, args: list[str]) -> list[str]:
        """Wrap ISO date-string arguments at a procedure's date-parameter
        positions in ANSI ``DATE``/``TIMESTAMP`` literals (Oracle won't
        implicitly convert them, ORA-01861)."""
        from unique.core.converter import PROC_DATE_PARAMS, wrap_oracle_date_arg

        registry = PROC_DATE_PARAMS.get()
        if not registry:
            return args
        key = proc_name.strip('[]"`').split(".")[-1].lower()
        positions = registry.get(key)
        if not positions:
            return args
        return [
            wrap_oracle_date_arg(a) if i in positions else a for i, a in enumerate(args)
        ]

    def _emit_execute_stmt(
        self, expr: str, params: list[str], immediate: bool = False
    ) -> str:
        """Oracle EXEC handling.

        A named stored-procedure call becomes ``name(args);`` (Oracle invokes a
        procedure by name inside a PL/SQL block; the surrounding anonymous block
        supplies BEGIN/END). A bare dynamic-SQL string/variable keeps
        ``EXECUTE IMMEDIATE [USING …]``. The proc name may be schema-qualified
        (dbo.create_invoice); the dbo default schema is dropped.
        """
        stripped = expr.strip()
        # T-SQL ``sp_executesql @stmt, N'<paramdefs>', @a, @b, …`` -> Oracle
        # parameterized dynamic SQL ``EXECUTE IMMEDIATE @stmt USING @a, @b, …``.
        # The paramdef string is dropped (Oracle infers bind types positionally).
        if re.match(r"(?i)^sp_executesql\b", stripped):
            args = self._split_exec_args(stripped[len("sp_executesql") :].strip())
            if args:
                stmt = args[0]
                binds = args[2:]  # args[1] is the N'<paramdefs>' string — dropped
                if binds:
                    return f"EXECUTE IMMEDIATE {stmt} USING {', '.join(binds)};"
                return f"EXECUTE IMMEDIATE {stmt};"
        # An Oracle EXECUTE IMMEDIATE (or a dynamic-SQL string/bind/expression)
        # keeps ``EXECUTE IMMEDIATE`` — the ``immediate`` flag settles the case a
        # record field (r.cmd) would otherwise misread as a named-proc call.
        if immediate or stripped.startswith(("'", "@", "v_", "(", "N'", ":")):
            if params:
                return f"EXECUTE IMMEDIATE {expr} USING {', '.join(params)};"
            return f"EXECUTE IMMEDIATE {expr};"
        # Named procedure call.
        m = re.match(r"(?i)^(?:\[?\w+\]?\s*\.\s*)*\[?(\w+)\]?\s*(.*)$", stripped)
        if m:
            proc_name = m.group(1)
            args = self._wrap_date_args(
                proc_name, self._split_exec_args(m.group(2).strip())
            )
            return f"{proc_name}({', '.join(args)});"
        if params:
            return f"EXECUTE IMMEDIATE {expr} USING {', '.join(params)};"
        return f"EXECUTE IMMEDIATE {expr};"


register_emitter(OracleEmitter.dialect_name, OracleEmitter)
