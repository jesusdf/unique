# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""M4 oracle→MySQL tail classes (2026-07-10, the last 18 sweep failures).

Each test pins one live-measured defect class from executing the transpiled
13 MB Oracle dump on MySQL 8.4: reserved-word identifiers (MANUAL is reserved
since 8.4), keyword functions emitted with a space before ``(`` (EXTRACT),
bare RETURN inside nested blocks/handlers of procedures and triggers,
PRAGMA AUTONOMOUS_TRANSACTION leaking as a declaration, DROP SEQUENCE (MySQL
has no sequences), EXECUTE ... USING with routine-local variables (MySQL
binds only session variables), and a routine defined with a builtin's name.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(src: str, target: str) -> str:
    return Transpiler().transpile(src, "oracle", target).sql


def _flat(sql: str) -> str:
    return " ".join(sql.split())


class TestMySqlReservedIdentifiers:
    """MANUAL/PARALLEL/QUALIFY are reserved words in MySQL 8.4; unquoted
    column references are a hard 1064 parse error."""

    def test_insert_column_list_quotes_reserved(self) -> None:
        src = "INSERT INTO t (a, manual) VALUES (1, 2);"
        out = _t(src, "mysql")
        assert "`manual`" in out, out
        assert not re.search(r"(?<!`)\bmanual\b(?!`)", out), out

    def test_update_assignment_quotes_reserved(self) -> None:
        src = "UPDATE t SET manual = 1 WHERE a = 2;"
        out = _t(src, "mysql")
        assert "`manual` = 1" in out, out

    def test_non_reserved_columns_stay_bare(self) -> None:
        src = "INSERT INTO t (a, activo) VALUES (1, 2);"
        out = _t(src, "mysql")
        assert "`" not in out, out

    def test_other_targets_unaffected(self) -> None:
        src = "INSERT INTO t (a, manual) VALUES (1, 2);"
        for target in ("postgresql", "tsql"):
            out = _t(src, target)
            assert "`" not in out, (target, out)


class TestMySqlKeywordFunctionSpacing:
    """MySQL only recognizes keyword functions (EXTRACT, POSITION, ...) when
    the parenthesis follows immediately; ``EXTRACT ( YEAR FROM x )`` is 1064."""

    _SRC = (
        "create or replace FUNCTION f_age(p_ref DATE) RETURN NUMBER AS\n"
        "  v NUMBER;\n"
        "BEGIN\n"
        "  v := EXTRACT(YEAR FROM p_ref) - EXTRACT(MONTH FROM p_ref);\n"
        "  RETURN v;\n"
        "END;\n/"
    )

    def test_extract_has_no_space_before_paren(self) -> None:
        out = _t(self._SRC, "mysql")
        assert "EXTRACT(" in out, out
        assert not re.search(r"(?i)\bEXTRACT\s+\(", out), out


class TestMySqlReturnBecomesLeave:
    """RETURN is illegal anywhere in a MySQL procedure or trigger. The nested
    exception-handler RETURN (a BeginEndBlock child) used to slip through the
    label detection and ship as a bare ``RETURN;``."""

    _PROC = (
        "create or replace PROCEDURE p_ex(p_no IN NUMBER, p_out OUT VARCHAR2)\n"
        "AS\nBEGIN\n"
        "  BEGIN\n"
        "    SELECT c INTO p_out FROM t WHERE a = p_no;\n"
        "  EXCEPTION\n"
        "    WHEN NO_DATA_FOUND THEN\n"
        "      p_out := 'x';\n"
        "      RETURN;\n"
        "  END;\n"
        "  UPDATE t SET c = p_out WHERE a = p_no;\n"
        "END;\n/"
    )

    def test_procedure_nested_handler_return_leaves_label(self) -> None:
        out = _flat(_t(self._PROC, "mysql"))
        assert "proc_exit: BEGIN" in out, out
        assert "LEAVE proc_exit;" in out, out
        assert not re.search(r"(?i)\bRETURN\s*;", out), out

    _TRIGGER = (
        "create or replace TRIGGER trg_ex AFTER UPDATE ON t FOR EACH ROW\n"
        "BEGIN\n"
        "  BEGIN\n"
        "    INSERT INTO t_log (a) VALUES (:NEW.a);\n"
        "  EXCEPTION\n"
        "    WHEN NO_DATA_FOUND THEN\n"
        "      RETURN;\n"
        "  END;\n"
        "END;\n/"
    )

    def test_trigger_return_leaves_label(self) -> None:
        out = _flat(_t(self._TRIGGER, "mysql"))
        assert "LEAVE" in out, out
        assert not re.search(r"(?i)\bRETURN\s*;", out), out


class TestPragmaAutonomousTransaction:
    _SRC = (
        "create or replace PROCEDURE p_at(p_x IN NUMBER)\nAS\n"
        "  PRAGMA AUTONOMOUS_TRANSACTION;\n"
        "  v_c NUMBER;\n"
        "BEGIN\n"
        "  INSERT INTO t_log (a) VALUES (p_x);\n"
        "  COMMIT;\n"
        "END;\n/"
    )

    def test_off_oracle_pragma_never_ships_executable(self) -> None:
        for target in ("mysql", "postgresql", "tsql"):
            result = Transpiler().transpile(self._SRC, "oracle", target)
            # No executable PRAGMA fragment (a comment carrier is fine).
            for line in result.sql.splitlines():
                if "AUTONOMOUS_TRANSACTION" in line.upper():
                    assert line.lstrip().startswith("--"), (target, line)
            assert any(
                "AUTONOMOUS_TRANSACTION" in w.message for w in result.warnings
            ), (target, result.warnings)
            # The surrounding declarations survive (T-SQL renames v_c → @c).
            assert "v_c" in result.sql or "@c" in result.sql, (target, result.sql)

    def test_oracle_identity_keeps_pragma(self) -> None:
        out = _t(self._SRC, "oracle")
        assert re.search(r"(?i)^\s*PRAGMA AUTONOMOUS_TRANSACTION;", out, re.M), out


class TestDropSequenceMySql:
    _SRC = "DROP SEQUENCE IF EXISTS seq_batch_ins;"

    def test_mysql_degrades_to_documented_carrier(self) -> None:
        result = Transpiler().transpile(self._SRC, "oracle", "mysql")
        for line in result.sql.splitlines():
            if "DROP SEQUENCE" in line.upper():
                assert line.lstrip().startswith("--"), line
        assert "seq_batch_ins" in result.sql, result.sql
        assert result.warnings or result.unsupported, result

    def test_postgresql_keeps_native_drop(self) -> None:
        out = _t(self._SRC, "postgresql")
        assert re.search(r"(?i)^\s*DROP SEQUENCE", out, re.M), out


class TestMySqlExecuteUsingSessionVars:
    """MySQL's EXECUTE ... USING accepts only @session variables; routine
    locals/parameters must be copied into @vars first."""

    _SRC = (
        "create or replace PROCEDURE p_dyn(v_a IN NUMBER, v_b IN VARCHAR2)\n"
        "AS\nBEGIN\n"
        "  EXECUTE IMMEDIATE 'BEGIN other_p(:1, :2); END;' USING v_a, v_b;\n"
        "END;\n/"
    )

    def test_using_binds_are_session_variables(self) -> None:
        out = _flat(_t(self._SRC, "mysql"))
        m = re.search(r"(?i)EXECUTE _dyn USING ([^;]+);", out)
        assert m, out
        binds = [b.strip() for b in m.group(1).split(",")]
        assert all(b.startswith("@") for b in binds), out
        # Each local is copied into its session variable before the EXECUTE.
        assert re.search(r"SET @\w+ = v_a;", out), out
        assert re.search(r"SET @\w+ = v_b;", out), out


class TestRoutineNamedAsMySqlBuiltin:
    _SRC = (
        "create or replace FUNCTION now RETURN DATE AS\n"
        "BEGIN\n"
        "  RETURN SYSDATE;\n"
        "END;\n/"
    )

    def test_definition_is_backtick_quoted(self) -> None:
        out = _t(self._SRC, "mysql")
        assert re.search(r"(?i)CREATE FUNCTION `now`", out), out
