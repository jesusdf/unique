# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the output validity gate (audit doc 04, M1).

The gate enforces the honesty invariant: the transpiler must never ship
output it can tell is invalid on the target. A batch whose emitted SQL fails
the target-dialect parse (plain DML/DDL) or the structural leftover checks
(procedural units) degrades to the documented carrier + warning + unsupported
entry, exactly like any other lossy conversion.
"""

from __future__ import annotations

import sqlglot

from unique.core.output_gate import find_leftover_tokens, gate_reason
from unique.core.transpiler import Transpiler


def _parses(sql: str, dialect: str) -> bool:
    executable = [
        s for s in sql.split("\n") if s.strip() and not s.strip().startswith("--")
    ]
    if not executable:
        return True
    try:
        sqlglot.parse(
            "\n".join(executable), read=dialect, error_level=sqlglot.ErrorLevel.RAISE
        )
        return True
    except Exception:
        return False


class TestGateReason:
    """The pure check: given emitted output, is there a reason to degrade?"""

    def test_valid_dml_passes(self) -> None:
        assert gate_reason("SELECT 1;", "postgresql") is None

    def test_string_with_semicolon_passes(self) -> None:
        assert gate_reason("INSERT INTO t (v) VALUES ('a;b');", "postgresql") is None

    def test_unparseable_ddl_is_flagged(self) -> None:
        bad = (
            "ALTER TABLE u ADD CONSTRAINT pk "
            "PRIMARY KEY, CLUSTERED (c ASC NULLS FIRST);"
        )
        assert gate_reason(bad, "postgresql") is not None

    def test_procedural_unit_skips_the_parse_check(self) -> None:
        # sqlglot cannot parse PL/SQL; a guard loop must not be flagged by it.
        guard = (
            "BEGIN FOR unique_guard IN (SELECT 1 FROM DUAL WHERE NOT "
            "EXISTS(SELECT 1 FROM cfg WHERE k = 'x')) LOOP\n"
            "    INSERT INTO cfg (k) VALUES ('x');\nEND LOOP; END;\n/"
        )
        assert gate_reason(guard, "oracle") is None

    def test_pg_do_block_skips_the_parse_check(self) -> None:
        block = "DO $$\nBEGIN\n    INSERT INTO cfg (k) VALUES ('x');\nEND $$;"
        assert gate_reason(block, "postgresql") is None

    def test_leftover_in_procedural_unit_is_flagged(self) -> None:
        # A routine that leaked Oracle's ROWNUM into PostgreSQL output.
        bad = (
            "CREATE OR REPLACE PROCEDURE p1() LANGUAGE plpgsql AS $$\n"
            "BEGIN\n    SELECT id INTO v_x FROM t WHERE ROWNUM = 1;\nEND;\n$$;"
        )
        reason = gate_reason(bad, "postgresql")
        assert reason is not None
        assert "ROWNUM" in reason


class TestLeftoverTokens:
    def test_rownum_flagged_off_oracle(self) -> None:
        assert find_leftover_tokens("SELECT 1 WHERE ROWNUM = 1", "postgresql")
        assert not find_leftover_tokens("SELECT 1 WHERE ROWNUM = 1", "oracle")

    def test_tokens_inside_strings_and_comments_ignored(self) -> None:
        sql = "SELECT 'ROWNUM literal' -- ROWNUM comment\nFROM t"
        assert not find_leftover_tokens(sql, "postgresql")

    def test_varchar2_flagged_off_oracle(self) -> None:
        assert find_leftover_tokens("v_x AS VARCHAR2", "tsql")

    def test_execute_immediate_flagged_off_oracle(self) -> None:
        assert find_leftover_tokens("EXECUTE IMMEDIATE 'DROP TABLE t'", "tsql")

    def test_getdate_flagged_off_tsql(self) -> None:
        assert find_leftover_tokens("SELECT GETDATE()", "postgresql")
        assert not find_leftover_tokens("SELECT GETDATE()", "tsql")

    def test_backtick_identifier_flagged_off_mysql(self) -> None:
        assert find_leftover_tokens("SELECT `x` FROM t", "postgresql")
        assert not find_leftover_tokens("SELECT `x` FROM t", "mysql")


class TestGateEndToEnd:
    """Through the public API: invalid output degrades to carrier + signals."""

    def test_pk_clustered_now_translates_cleanly(self) -> None:
        # This shape used to degrade to a carrier; since the B1 fix
        # (2026-07-09) it translates outright — the gate must have nothing
        # to catch and no false signals may fire.
        src = (
            "ALTER TABLE u ADD CONSTRAINT pk_u "
            "PRIMARY KEY CLUSTERED (codigo ASC);\nGO\n"
        )
        result = Transpiler().transpile(src, "tsql", "postgresql")
        assert _parses(result.sql, "postgres")
        assert "UNIQUE:" not in result.sql
        assert "CLUSTERED" not in result.sql.upper()
        assert 'PRIMARY KEY ("codigo")' in result.sql
        assert not any(w.feature == "validity_gate" for w in result.warnings)
        assert not result.unsupported

    def test_rownum_leak_in_routine_degrades_to_carrier(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p1 AS\n  v_x NUMBER(9);\nBEGIN\n"
            "  SELECT id INTO v_x FROM t WHERE ROWNUM = 1;\nEND;\n/\n"
        )
        result = Transpiler().transpile(src, "oracle", "postgresql")
        executable = "\n".join(
            line
            for line in result.sql.splitlines()
            if line.strip() and not line.strip().startswith("--")
        )
        assert "ROWNUM" not in executable
        assert any(w.feature == "validity_gate" for w in result.warnings)
        assert result.unsupported

    def test_valid_output_is_untouched(self) -> None:
        result = Transpiler().transpile(
            "INSERT INTO t (v) VALUES ('a;b');\nGO\n", "tsql", "postgresql"
        )
        assert "UNIQUE:" not in result.sql
        assert "INSERT INTO t" in result.sql
        assert not result.warnings


class TestWarningAggregation:
    """M1(c): duplicate warnings collapse into one entry with a count."""

    def test_repeated_warning_is_aggregated(self) -> None:
        src = (
            "SET NOEXEC OFF\nGO\nSELECT 1;\nGO\n"
            "SET NOEXEC OFF\nGO\nSET NOEXEC OFF\nGO\n"
        )
        result = Transpiler().transpile(src, "tsql", "postgresql")
        matching = [w for w in result.warnings if "SET NOEXEC OFF" in w.message]
        assert len(matching) == 1
        assert "x3" in matching[0].message

    def test_single_warning_keeps_plain_message(self) -> None:
        result = Transpiler().transpile(
            "SET NOEXEC OFF\nGO\nSELECT 1;\nGO\n", "tsql", "postgresql"
        )
        matching = [w for w in result.warnings if "SET NOEXEC OFF" in w.message]
        assert len(matching) == 1
        assert "x1" not in matching[0].message
