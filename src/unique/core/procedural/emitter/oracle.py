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
    CreateFunctionStatement,
    CreateTriggerStatement,
    DeclareStatement,
    EmbeddedDML,
    ExceptionBlock,
    ForLoopStatement,
    ParameterDefinition,
    PerformStatement,
    PragmaDeclaration,
    PrintStatement,
    RaiseErrorStatement,
    RawSQL,
    ReturnStatement,
    SelectIntoStatement,
    StatementList,
    TryCatchBlock,
)
from unique.core.procedural.emitter.base import (
    _SQL_ONLY_IN_PLSQL,
    ProceduralEmitter,
    register_emitter,
)

_SIZE_RE = re.compile(r"\(\s*\d+\s*(?:,\s*\d+\s*)?\)")

# The IF-EXISTS guard emulation names its probe loop this (see the oracle
# transformer's _exists_probe_loop). A top-level block that is only such loop(s)
# is rendered compact — ``BEGIN FOR … END LOOP; END;`` — to match the catalog
# guard's shape instead of putting BEGIN/END on their own lines.
_GUARD_LOOP_VAR = "unique_guard"


def _is_exists_guard_body(body: list[ASTNode]) -> bool:
    """True when a top-level block body is an ``IF EXISTS`` guard lowered to cursor
    FOR-loop probe(s): a single loop, or a THEN/ELSE pair wrapped in a
    ``StatementList``, each over the ``unique_guard`` variable."""
    stmts: tuple[ASTNode, ...] | list[ASTNode] = body
    if len(body) == 1 and isinstance(body[0], StatementList):
        stmts = body[0].statements
    return bool(stmts) and all(
        isinstance(s, ForLoopStatement) and s.variable == _GUARD_LOOP_VAR for s in stmts
    )


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

    def _emit_pragma(self, node: PragmaDeclaration) -> str:
        return f"PRAGMA {node.name};"

    def _emit_try_catch(self, node: TryCatchBlock) -> str:
        # PL/SQL error handling is a nested block: BEGIN <try> EXCEPTION WHEN
        # OTHERS THEN <catch> END;. (The old transformer-level rewrite kept
        # only the handlers and silently dropped the TRY body.)
        lines = ["BEGIN"]
        self._indent_level += 1
        lines.extend(self._emit_indented_stmts(node.try_body))
        self._indent_level -= 1
        lines.append("EXCEPTION")
        self._indent_level += 1
        lines.append(f"{self._indent()}WHEN OTHERS THEN")
        self._indent_level += 1
        if node.catch_body:
            lines.extend(self._emit_indented_stmts(node.catch_body))
        else:
            lines.append(f"{self._indent()}NULL;")
        self._indent_level -= 2
        lines.append("END;")
        return "\n".join(lines)

    #: PostgreSQL / standard predefined-condition names that Oracle spells
    #: differently (the inverse of the PostgreSQL emitter's map); unknowns —
    #: OTHERS, NO_DATA_FOUND, user-defined names — pass through unchanged.
    _PG_EXCEPTION_CONDITIONS = {
        "DIVISION_BY_ZERO": "ZERO_DIVIDE",
        "UNIQUE_VIOLATION": "DUP_VAL_ON_INDEX",
        "TOO_MANY_ROWS": "TOO_MANY_ROWS",
        "NO_DATA_FOUND": "NO_DATA_FOUND",
        "CASE_NOT_FOUND": "CASE_NOT_FOUND",
    }

    def _map_exception_name(self, name: str) -> str:
        return self._PG_EXCEPTION_CONDITIONS.get(name.upper(), name)

    #: PG conditions with a definite ORA error code but NO predefined named
    #: Oracle exception — handled via WHEN OTHERS + SQLCODE (a PRAGMA
    #: EXCEPTION_INIT declaration would need DECLARE-section surgery).
    _PG_CONDITION_SQLCODES = {
        "CHECK_VIOLATION": -2290,
        "FOREIGN_KEY_VIOLATION": -2291,
        "NOT_NULL_VIOLATION": -1400,
    }

    def _emit_exception_block(self, node: ExceptionBlock) -> str:
        coded = [
            h
            for h in node.handlers
            if h.exception_name.upper() in self._PG_CONDITION_SQLCODES
        ]
        if not coded:
            return super()._emit_exception_block(node)
        lines = ["EXCEPTION"]
        for handler in node.handlers:
            if handler in coded:
                continue
            lines.append(
                f"WHEN {self._map_exception_name(handler.exception_name)} THEN"
            )
            self._indent_level += 1
            for stmt in handler.body:
                for line in self._emit_node(stmt).split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
        # One WHEN OTHERS discriminating by SQLCODE; unmatched errors re-raise.
        lines.append("WHEN OTHERS THEN")
        self._indent_level += 1
        kw = "IF"
        for handler in coded:
            code = self._PG_CONDITION_SQLCODES[handler.exception_name.upper()]
            lines.append(f"{self._indent()}{kw} SQLCODE = {code} THEN")
            self._indent_level += 1
            for stmt in handler.body:
                for line in self._emit_node(stmt).split("\n"):
                    lines.append(f"{self._indent()}{line}" if line.strip() else "")
            self._indent_level -= 1
            kw = "ELSIF"
        lines.append(f"{self._indent()}ELSE")
        self._indent_level += 1
        lines.append(f"{self._indent()}RAISE;")
        self._indent_level -= 1
        lines.append(f"{self._indent()}END IF;")
        self._indent_level -= 1
        return "\n".join(lines)

    def _procedure_header(self, name: str, or_replace: bool) -> str:
        prefix = "CREATE OR REPLACE " if or_replace else "CREATE "
        return f"{prefix}PROCEDURE {name}"

    def _keep_schema(self, schema: str) -> bool:
        # 'dbo' is T-SQL's default schema and has no Oracle counterpart.
        return schema.lower() != "dbo"

    def _assignment_via_select(
        self, target: str, val: str, value_node: ASTNode | None = None
    ) -> str | None:
        # Oracle PL/SQL forbids a subquery inside an expression (PLS-00405) and
        # rejects a SQL-only operator like CAST in a procedural expression
        # (PLS-00103), so `x := (SELECT …)` / `x := LOWER(CAST(…))` is invalid.
        # Evaluate the whole expression in SQL context instead:
        #   SELECT <expr> INTO x FROM DUAL;
        # DUAL yields exactly one row (NULL for a no-row scalar subquery), matching
        # T-SQL's `SET @x = …` and avoiding NO_DATA_FOUND.
        # Structure first (M3-prereq increment 4a): a value tree carrying a
        # subquery or CAST decides by NODE; the spelling regex remains only
        # for raw text fragments the IR does not model.
        if value_node is not None and self._needs_sql_context(value_node):
            return f"SELECT {val.strip()} INTO {target} FROM DUAL;"
        if re.search(_SQL_ONLY_IN_PLSQL, val):
            return f"SELECT {val.strip()} INTO {target} FROM DUAL;"
        return None

    @classmethod
    def _needs_sql_context(cls, value: object) -> bool:
        """Whether the value TREE contains a construct PL/SQL cannot
        evaluate in an expression (subquery, CAST)."""
        import dataclasses as _dc

        from unique.core.ast_nodes import CastExpression, SubqueryExpression

        if isinstance(value, (SubqueryExpression, CastExpression)):
            return True
        if isinstance(value, RawSQL):
            return False  # raw fragments stay on the regex path
        if _dc.is_dataclass(value) and not isinstance(value, type):
            return any(
                cls._needs_sql_context(getattr(value, f.name))
                for f in _dc.fields(value)
            )
        if isinstance(value, tuple):
            return any(cls._needs_sql_context(item) for item in value)
        return False

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
        # PG coerces a numeric RETURN into a boolean function; Oracle's
        # BOOLEAN takes no numbers (PLS-00382) — the comparison IS the
        # boolean (wave 227).
        rt_bool = getattr(self, "_oracle_fn_return_type", None)
        if (
            node.value is not None
            and rt_bool
            and rt_bool.upper() in ("BOOLEAN", "BOOL")
        ):
            val_b = self._emit_node(node.value).strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", val_b):
                return f"RETURN ({val_b} <> 0);"
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

    #: DDL verbs that PL/SQL cannot run statically (ORA/PLS-00103 at the
    #: CREATE) — they need EXECUTE IMMEDIATE (wave 178).
    _PLSQL_DDL_RE = re.compile(r"(?is)^\s*(CREATE|DROP|ALTER|TRUNCATE)\b")

    def _emit_embedded_dml(self, node: EmbeddedDML) -> str:
        sql = node.sql.rstrip(";").strip()
        if self._PLSQL_DDL_RE.match(sql):
            # A bare NULLS FIRST/LAST in an index column list is invalid on
            # Oracle (ORA-00907); sqlglot injects it emulating the default
            # nulls ordering. Strip it from an embedded CREATE INDEX (the
            # standalone path already does — this is the EXECUTE IMMEDIATE one).
            if re.match(r"(?is)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b", sql):
                sql = re.sub(r"(?i)\s+NULLS\s+(?:FIRST|LAST)", "", sql)
            quoted = sql.replace("'", "''")
            return f"EXECUTE IMMEDIATE '{quoted}';"
        return f"{sql};"

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
        # Oracle spells the bidirectional mode ``IN OUT`` — a MySQL
        # INOUT shipped verbatim was PLS-00103 (wave 177).
        direction = "IN OUT" if p.direction == "INOUT" else (p.direction or "IN")
        return f"{p.name} {direction} {dt}{default_str}"

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

    def _empty_block_filler(self) -> str | None:
        return "NULL;"

    def _emit_perform(self, node: PerformStatement) -> str:
        # PL/SQL cannot call a function as a statement: a nested block
        # with its own discard local keeps evaluate-and-discard exact.
        expr = self._emit_node(node.expression) if node.expression else "0"
        return (
            "DECLARE\n    uq_discard VARCHAR2(4000);\nBEGIN\n"
            f"    SELECT TO_CHAR({expr}) INTO uq_discard FROM DUAL;\nEND;"
        )

    def _emit_raise_error(self, node: RaiseErrorStatement) -> str:
        if node.reraise:
            return "RAISE;"
        msg = self._emit_node(node.message) if node.message else "'Error'"
        # Message text preserved; T-SQL user error numbers 50000-50999 map
        # onto Oracle's -20000..-20999 user range (audit 2026-07-02, S2-2).
        text, number, _ = self._raise_parts(msg)
        code = -20001
        # Token-joined negatives arrive spaced ('- 20001'); parse tolerantly.
        num_text = str(number).replace(" ", "") if number is not None else None
        if (
            num_text is not None
            and re.fullmatch(r"-?\d+", num_text)
            and (50000 <= int(num_text) <= 50999)
        ):
            code = -(20000 + (int(num_text) - 50000))
        payload = text or number or msg
        return f"RAISE_APPLICATION_ERROR({code}, {payload});"

    def _emit_function_impl(self, node: CreateFunctionStatement) -> str:
        # A routine with no return type — a PostgreSQL function with only OUT
        # params — is a PROCEDURE on Oracle: a FUNCTION must RETURN a type, and
        # ``RETURN void`` raises PLS-00201. (A plain RETURNS void body maps to the
        # neutral scalar form instead — see TestReturnsVoid.)
        if node.return_type is None:
            name = self._qualified_name(node.schema, node.name)
            header = self._procedure_header(name, node.or_replace)
            self._indent_level += 1
            params_str = self._emit_params(node.parameters)
            self._indent_level -= 1
            if params_str:
                header += f"\n(\n{params_str}\n)"
            declarations, body_stmts = self._split_declarations(node.body)
            self._in_oracle_procedure = True
            return self._emit_oracle_procedure_body(header, declarations, body_stmts)
        return super()._emit_function_impl(node)

    def _emit_function_body(
        self,
        header: str,
        declarations: list[ASTNode],
        body_stmts: list[ASTNode],
    ) -> str:
        self._in_oracle_procedure = False
        return self._emit_oracle_procedure_body(header, declarations, body_stmts)

    def _emit_table_valued_function(self, node: CreateFunctionStatement) -> str:
        # A T-SQL inline table-valued function that splits a string (STRING_SPLIT
        # body) becomes an Oracle function returning the built-in
        # SYS.ODCIVARCHAR2LIST collection — no custom type or pipelining needed.
        # Callers read ``COLUMN_VALUE FROM TABLE(fn(...))``. Any other TVF shape
        # stays a documented carrier (the base implementation).
        body_text = " ".join(self._emit_node(s) for s in node.body).upper()
        if "STRING_SPLIT" not in body_text or len(node.parameters) < 2:
            return super()._emit_table_valued_function(node)
        name = self._qualified_name(node.schema, node.name)
        s, delim = node.parameters[0].name, node.parameters[1].name
        self._indent_level += 1
        params_str = self._emit_params(node.parameters)
        self._indent_level -= 1
        split = f"REGEXP_SUBSTR({s}, '[^' || {delim} || ']+', 1, LEVEL)"
        return (
            f"CREATE OR REPLACE FUNCTION {name}\n(\n{params_str}\n)\n"
            "RETURN SYS.ODCIVARCHAR2LIST IS\n"
            "    v_result SYS.ODCIVARCHAR2LIST := SYS.ODCIVARCHAR2LIST();\n"
            "BEGIN\n"
            f"    SELECT TRIM({split})\n"
            "    BULK COLLECT INTO v_result FROM DUAL\n"
            f"    CONNECT BY {split} IS NOT NULL;\n"
            "    RETURN v_result;\n"
            "END;"
        )

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
        if node.update_of:
            events = self._events_with_update_of(events, node.update_of)
        note, timing = self._adjust_trigger_timing(node.timing)
        header_lines = self._trigger_header(name, node, events, timing)
        header_lines = [ln for ln in header_lines if ln != "BEGIN"]
        declarations, body_stmts = self._split_declarations(node.body)
        self._in_oracle_procedure = True  # a trigger RETURN cannot carry a value
        return self._degrade_pseudo_table_trigger(
            note
            + self._emit_oracle_procedure_body(
                "\n".join(header_lines),
                declarations,
                body_stmts,
                decl_keyword="DECLARE",
                no_decl_keyword="",
            )
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
        if not decls and _is_exists_guard_body(body):
            # Hug BEGIN/END onto the guard loop(s): `BEGIN FOR … END LOOP; END;`,
            # matching the catalog-guard form (top-level, so indent is 0).
            body_lines = self._emit_indented_stmts(tuple(body))
            body_lines[0] = f"BEGIN {body_lines[0]}"
            body_lines[-1] = f"{body_lines[-1]} END;"
            return "\n".join(body_lines)
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
