# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Q1 brief B35 (audit/2026-07-30-q1-triage.md finding E).

A DELIMITER-less MySQL routine whose body contained a ``CASE ... END`` expression
was torn by the batch splitter: the CASE's closing ``END`` decremented the
BEGIN/END depth to zero and ended the routine batch early. The remaining body
statements leaked as top-level batches — each ``SET v_local = expr`` local
assignment was mis-classified as a MySQL session setting (UNIQUE-1219) and the
trailing ``END`` was emitted as the invalid ``"END" AS IF;`` fragment (silent
corruption). Keeping the body whole (counting CASE as a balanced block) is the
root fix: local SETs stay assignments inside the body and the dollar-quote is
never closed early.
"""

from __future__ import annotations

import re

import sqlglot

from unique.core.transpiler import Transpiler


def _pg(sql: str) -> str:
    return Transpiler().transpile(sql, source="mysql", target="postgresql").sql


def _code_lines(out: str) -> list[str]:
    """Executable lines only — line/block comments are trivia and excluded."""
    lines = []
    for ln in out.splitlines():
        s = ln.strip()
        if not s or s.startswith("--"):
            continue
        if s.startswith("/*") and s.endswith("*/"):
            continue
        lines.append(ln)
    return lines


class TestB35DelimiterlessCaseBodyIntegrity:
    """A DELIMITER-less routine body containing a CASE...END expression must
    stay whole — no premature batch split, no session-setting mis-classification
    of local SETs, no invalid ``"END" AS IF;`` leak."""

    _DELIMLESS = (
        "CREATE FUNCTION f_case (v_a INT) RETURNS VARCHAR(10)\n"
        "BEGIN\n"
        "    DECLARE v_m VARCHAR(10);\n"
        "    DECLARE v_r VARCHAR(10);\n"
        "    SET v_m = CASE WHEN v_a = 1 THEN 'yes' ELSE 'no' END;\n"
        "    SET v_r = REPLACE(v_m, 'n', 'N');\n"
        "    RETURN v_r;\n"
        "END\n"
    )

    def test_local_set_after_case_assigns_inside_body(self) -> None:
        out = _pg(self._DELIMLESS)
        # The whole routine is one plpgsql function, dollar-quote balanced.
        assert out.count("$$") % 2 == 0 and out.count("$$") >= 2, out
        assert re.search(r"(?i)CREATE (?:OR REPLACE )?FUNCTION f_case", out), out
        # The local SET is an assignment, not a session-setting carrier.
        assert "UNIQUE-1219" not in out, out
        assert re.search(r"(?i)\bv_r\s*:=\s*REPLACE", out), out

    def test_no_end_as_if_leak(self) -> None:
        out = _pg(self._DELIMLESS)
        assert '"END" AS IF' not in out, out
        assert not re.search(r'(?m)^\s*"END"\s*;', out), out

    def test_output_target_parses(self) -> None:
        out = _pg(self._DELIMLESS)
        # The whole emitted script must parse as PostgreSQL — the corruption
        # produced bare "END" AS IF; fragments that do not.
        sqlglot.parse(out, read="postgres", error_level=sqlglot.ErrorLevel.RAISE)

    def test_real_session_set_in_body_degrades_without_breaking_body(self) -> None:
        # A REAL session setting inside a routine body degrades honestly (whole
        # routine) — never a torn body that leaks fragments as top-level SQL.
        src = (
            "DELIMITER $$\n"
            "CREATE PROCEDURE p_sess ()\n"
            "BEGIN\n"
            "    SET @@sql_mode = 'STRICT_ALL_TABLES';\n"
            "    SELECT 1;\n"
            "END$$\n"
            "DELIMITER ;\n"
        )
        out = _pg(src)
        # Dollar-quote balanced (0 or an even number — never a dangling opener).
        assert out.count("$$") % 2 == 0, out
        assert '"END" AS IF' not in out, out
        # No executable code leaked outside a carrier: an honest whole-routine
        # degrade is entirely commented.
        assert not _code_lines(out), out

    def test_nested_case_body_stays_whole(self) -> None:
        # Neighbor: two CASE...END expressions on one line must still balance.
        src = (
            "CREATE FUNCTION f_nest (v_a INT) RETURNS INT\n"
            "BEGIN\n"
            "    DECLARE v_x INT;\n"
            "    SET v_x = CASE WHEN v_a > 0 THEN CASE WHEN v_a > 9 THEN 2 "
            "ELSE 1 END ELSE 0 END;\n"
            "    SET v_x = v_x + 1;\n"
            "    RETURN v_x;\n"
            "END\n"
        )
        out = _pg(src)
        assert "UNIQUE-1219" not in out, out
        assert '"END" AS IF' not in out, out
        assert re.search(r"(?i)CREATE (?:OR REPLACE )?FUNCTION f_nest", out), out

    def test_case_statement_form_still_splits_correctly(self) -> None:
        # Regression guard: the CASE *statement* form (END CASE) must remain
        # balanced too — the routine body is one unit and its END does not tear
        # it prematurely.
        src = (
            "CREATE PROCEDURE p_stmt (v_a INT)\n"
            "BEGIN\n"
            "    CASE v_a\n"
            "        WHEN 1 THEN SELECT 'one';\n"
            "        ELSE SELECT 'other';\n"
            "    END CASE;\n"
            "END\n"
        )
        out = _pg(src)
        assert re.search(r"(?i)CREATE (?:OR REPLACE )?PROCEDURE p_stmt", out), out
        assert '"END" AS IF' not in out, out
