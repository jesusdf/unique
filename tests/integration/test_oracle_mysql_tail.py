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


class TestNumericRangeForLoop:
    """``FOR i IN 1..13 LOOP`` is a counting loop, not a cursor loop; MySQL
    used to receive ``DECLARE i_cur CURSOR FOR 1..13`` (a 1064 error)."""

    _SRC = (
        "create or replace PROCEDURE p_rng AS\nBEGIN\n"
        "  FOR i IN 1..13 LOOP\n"
        "    INSERT INTO t (a) VALUES (i);\n"
        "  END LOOP;\n"
        "END;\n/"
    )

    def test_mysql_expands_to_while(self) -> None:
        out = _flat(_t(self._SRC, "mysql"))
        assert "WHILE i <= 13 DO" in out, out
        assert "SET i = i + 1;" in out, out
        assert "DECLARE i INT DEFAULT 1;" in out, out
        assert "CURSOR" not in out.upper(), out
        assert ".." not in out, out

    def test_tsql_expands_to_while(self) -> None:
        out = _flat(_t(self._SRC, "tsql"))
        assert "WHILE @i <= 13" in out, out
        assert re.search(r"DECLARE @i INT = 1", out), out
        assert "VALUES (@i)" in out, out
        assert "CURSOR" not in out.upper(), out

    def test_postgresql_keeps_native_range_loop(self) -> None:
        out = _flat(_t(self._SRC, "postgresql"))
        assert re.search(r"(?i)FOR i IN 1\s*\.\.\s*13 LOOP", out), out

    def test_oracle_identity_keeps_range_loop(self) -> None:
        out = _flat(_t(self._SRC, "oracle"))
        assert re.search(r"(?i)FOR i IN 1\s*\.\.\s*13 LOOP", out), out

    def test_reverse_range_mysql_counts_down(self) -> None:
        src = self._SRC.replace("IN 1..13", "IN REVERSE 1..13")
        out = _flat(_t(src, "mysql"))
        assert "DECLARE i INT DEFAULT 13;" in out, out
        assert "WHILE i >= 1 DO" in out, out
        assert "SET i = i - 1;" in out, out


class TestMySqlCursorForLoopExpansion:
    """The MySQL cursor FOR-loop expansion used to emit a scaffold that never
    parses: ``DECLARE r_cur CURSOR FOR curES`` (a cursor cannot alias another
    cursor), an empty ``FETCH INTO /* col1, ... */`` and DECLAREs mid-block.
    When the select list is resolvable the expansion must be complete."""

    _NAMED = (
        "create or replace PROCEDURE p_cur AS\n"
        "  CURSOR curES IS SELECT accion, codigo AS codpostal FROM t_dir;\n"
        "BEGIN\n"
        "  FOR r IN curES LOOP\n"
        "    INSERT INTO t_out (a, b) VALUES (r.accion, r.codpostal);\n"
        "  END LOOP;\n"
        "END;\n/"
    )

    def test_named_cursor_drives_directly(self) -> None:
        out = _flat(_t(self._NAMED, "mysql"))
        assert "FETCH curES INTO r_accion, r_codpostal;" in out, out
        assert "VALUES (r_accion, r_codpostal)" in out, out
        assert "OPEN curES;" in out, out
        assert "CLOSE curES;" in out, out
        # No second cursor aliasing the named one, no empty FETCH.
        assert "CURSOR FOR curES" not in out, out
        assert "/* col1" not in out, out

    def test_named_cursor_declares_vars_at_block_start(self) -> None:
        out = _t(self._NAMED, "mysql")
        # The expansion opens its own block so its DECLAREs are legal.
        m = re.search(
            r"BEGIN\s*\n\s*DECLARE r_accion TEXT;\s*\n\s*DECLARE r_codpostal TEXT;",
            out,
        )
        assert m, out

    _INLINE = (
        "create or replace PROCEDURE p_cur2 AS\n"
        "BEGIN\n"
        "  FOR r IN (SELECT accion FROM t_dir) LOOP\n"
        "    INSERT INTO t_out (a) VALUES (r.accion);\n"
        "  END LOOP;\n"
        "END;\n/"
    )

    def test_inline_query_expands_completely(self) -> None:
        out = _flat(_t(self._INLINE, "mysql"))
        assert "DECLARE r_cur CURSOR FOR SELECT accion FROM t_dir;" in out, out
        assert "FETCH r_cur INTO r_accion;" in out, out
        assert "VALUES (r_accion)" in out, out
        assert "/* col1" not in out, out

    def test_unresolvable_list_keeps_documented_scaffold(self) -> None:
        src = self._INLINE.replace("SELECT accion", "SELECT *")
        result = Transpiler().transpile(src, "oracle", "mysql")
        assert "-- UNIQUE:" in result.sql, result.sql
        assert result.warnings, result.warnings


class TestDottedFunctionReturnType:
    """``RETURN tbl.col%TYPE`` / ``RETURN pkg.type`` in a function header used
    to desync the parser: the leftover ``.col%TYPE`` shattered the declaration
    section into garbage (``DECLARE . LONGTEXT;``, ``DECLARE AS v;``)."""

    _TYPE_SRC = (
        "create or replace FUNCTION f_lookup(v_a IN NUMBER)\n"
        "RETURN t_ident.id_col%TYPE\nAS\n"
        "  v_id t_ident.id_col%TYPE;\n"
        "BEGIN\n"
        "  SELECT id_col INTO v_id FROM t_ident WHERE a = v_a;\n"
        "  RETURN v_id;\n"
        "END;\n/"
    )

    def test_mysql_return_type_lowered_to_carrier(self) -> None:
        result = Transpiler().transpile(self._TYPE_SRC, "oracle", "mysql")
        out = result.sql
        assert re.search(r"(?i)RETURNS LONGTEXT /\* UNIQUE: t_ident", out), out
        # No shattered declarations.
        assert not re.search(r"(?im)^\s*DECLARE (\.|AS|TYPE)\b", out), out
        assert "DECLARE v_id LONGTEXT" in out, out

    def test_oracle_identity_keeps_type_reference(self) -> None:
        out = _t(self._TYPE_SRC, "oracle")
        assert re.search(r"(?i)RETURN t_ident\.id_col%TYPE", out), out

    _PKG_SRC = (
        "create or replace FUNCTION f_pkg(v_a IN NUMBER)\n"
        "RETURN pkg_ret.my_type\nAS\n"
        "  v_r pkg_ret.my_type;\n"
        "BEGIN\n"
        "  RETURN v_r;\n"
        "END;\n/"
    )

    def test_mysql_package_type_lowered_to_carrier(self) -> None:
        result = Transpiler().transpile(self._PKG_SRC, "oracle", "mysql")
        out = result.sql
        assert re.search(r"(?i)RETURNS LONGTEXT /\* UNIQUE: pkg_ret\.my_type", out), out
        assert "DECLARE v_r LONGTEXT" in out, out
        assert not re.search(r"(?im)^\s*DECLARE pkg_ret\b", out), out
        assert any(
            "pkg_ret.my_type" in w.message for w in result.warnings
        ), result.warnings


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
