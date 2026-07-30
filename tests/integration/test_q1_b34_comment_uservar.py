# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Q1 brief B34 (audit/2026-07-30-q1-triage.md finding B).

The MySQL ``@user`` / ``@@system`` variable gates scanned raw routine text after
scrubbing string literals but NOT comments, so an ``@name`` living only inside an
inherited ``/* UNIQUE-1193: ... */`` carrier comment (or its ``restore_sql``
round-trip payload) degraded the whole routine to a UNIQUE-1171 carrier even
though no executable ``@`` reference exists. Comments are trivia.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _pg(sql: str) -> str:
    return Transpiler().transpile(sql, source="mysql", target="postgresql").sql


def _code_lines(out: str) -> list[str]:
    """Executable lines only — line (``--``) and single-line block (``/* */``)
    comments are trivia and excluded."""
    lines = []
    for ln in out.splitlines():
        s = ln.strip()
        if not s or s.startswith("--"):
            continue
        if s.startswith("/*") and s.endswith("*/"):
            continue
        lines.append(ln)
    return lines


class TestB34CommentBlindUserVarScan:
    """The @name/@@name gates must treat comments as trivia — an @ that lives
    only inside a carrier comment is not an executable variable reference."""

    _COMMENT_ONLY = (
        "DELIMITER $$\n"
        "CREATE PROCEDURE proc_cmt (IN v_a INT, IN v_b INT)\n"
        "BEGIN\n"
        "    /* UNIQUE-1193: SET NOCOUNT ON -- tsql-only, no mysql equivalent */\n"
        "    IF NOT (v_b IS NULL) THEN\n"
        "        /* UNIQUE-1193: SET ROWCOUNT @col_2 -- tsql-only, no mysql "
        "equivalent */\n"
        "        DO 0;\n"
        "    END IF;\n"
        "    SELECT c1 FROM t1 WHERE c1 = v_a;\n"
        "END$$\n"
        "DELIMITER ;\n"
    )

    def test_at_name_only_in_block_comment_does_not_degrade_routine(self) -> None:
        out = _pg(self._COMMENT_ONLY)
        # Routine is emitted as real code, not a whole-routine carrier.
        assert re.search(
            r"(?i)CREATE (?:OR REPLACE )?(?:PROCEDURE|FUNCTION) proc_cmt", out
        )
        assert _code_lines(out), out
        # The false-positive user-var degrade is gone.
        assert "UNIQUE-1171" not in out, out
        # The @ survives only inside the preserved comment, never as code.
        assert not any("@" in ln for ln in _code_lines(out)), out

    def test_at_name_only_in_line_comment_does_not_degrade_routine(self) -> None:
        src = (
            "DELIMITER $$\n"
            "CREATE PROCEDURE proc_line (IN v_a INT)\n"
            "BEGIN\n"
            "    -- UNIQUE-1193: SET ROWCOUNT @col_2 -- tsql-only, no equivalent\n"
            "    SELECT c1 FROM t1 WHERE c1 = v_a;\n"
            "END$$\n"
            "DELIMITER ;\n"
        )
        out = _pg(src)
        assert re.search(
            r"(?i)CREATE (?:OR REPLACE )?(?:PROCEDURE|FUNCTION) proc_line", out
        )
        assert "UNIQUE-1171" not in out, out

    def test_real_user_var_still_degrades_routine(self) -> None:
        # A genuine executable @user reference must STILL degrade the whole
        # routine — the fix removes false positives, not the real gate.
        src = (
            "DELIMITER $$\n"
            "CREATE PROCEDURE proc_real (IN v_a INT)\n"
            "BEGIN\n"
            "    SET @cnt = @cnt + 1;\n"
            "    SELECT c1 FROM t1 WHERE c1 = v_a;\n"
            "END$$\n"
            "DELIMITER ;\n"
        )
        out = _pg(src)
        assert "UNIQUE-1171" in out, out
        assert not any("@" in ln for ln in _code_lines(out)), out

    def test_at_sign_in_string_literal_never_degrades(self) -> None:
        # Neighbor: an '@' inside a string literal (email pattern) is not a var.
        src = (
            "DELIMITER $$\n"
            "CREATE PROCEDURE proc_str (IN v_a VARCHAR(50))\n"
            "BEGIN\n"
            "    SELECT CONCAT(v_a, '@example.com');\n"
            "END$$\n"
            "DELIMITER ;\n"
        )
        out = _pg(src)
        assert re.search(
            r"(?i)CREATE (?:OR REPLACE )?(?:PROCEDURE|FUNCTION) proc_str", out
        )
        assert "UNIQUE-1171" not in out, out
