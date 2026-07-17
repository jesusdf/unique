# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""The T-SQL procedure emitter injects ``SET NOCOUNT ON`` as a best-practice
default, but must not do so when the body already manages ``NOCOUNT``.

Two ways a body already manages it: an explicit ``SET NOCOUNT ON``/``OFF`` the
author wrote, and the ``/* UNIQUE: SET NOCOUNT ON -- tsql-only … */`` carrier
restored on a round-trip back from another engine. Either way the injected copy
would duplicate (or, for ``OFF``, contradict) the body's own directive.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler


def _tx(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _exec_body(sql: str) -> str:
    """Executable (non-comment) lines, upper-cased."""
    return "\n".join(
        ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")
    ).upper()


class TestNoCountNotDuplicated:
    def test_restored_carrier_not_duplicated(self) -> None:
        # Oracle procedure whose T-SQL origin's SET NOCOUNT ON is carried in
        # the restorable comment; transpiling back to T-SQL must restore it
        # exactly once, not once + the injected default.
        oracle = (
            "CREATE OR REPLACE PROCEDURE p\n"
            "(\n"
            "    RESULT_CURSOR OUT SYS_REFCURSOR\n"
            ")\n"
            "AS\nBEGIN\n"
            "    -- best practice\n"
            "    /* UNIQUE: SET NOCOUNT ON -- tsql-only, no oracle equivalent */\n"
            "    OPEN RESULT_CURSOR FOR SELECT * FROM a_tbl;\n"
            "END;\n/"
        )
        out = _tx(oracle, "oracle", "tsql")
        assert _exec_body(out).count("SET NOCOUNT ON") == 1, out

    def test_explicit_set_nocount_on_not_duplicated(self) -> None:
        tsql = "CREATE PROCEDURE p AS BEGIN\n" "  SET NOCOUNT ON;\n" "  SELECT 1;\nEND"
        out = _tx(tsql, "tsql", "tsql")
        assert _exec_body(out).count("SET NOCOUNT ON") == 1, out

    def test_explicit_set_nocount_off_respected(self) -> None:
        # The author chose OFF; the emitter must not force ON in front of it.
        tsql = "CREATE PROCEDURE p AS BEGIN\n" "  SET NOCOUNT OFF;\n" "  SELECT 1;\nEND"
        out = _tx(tsql, "tsql", "tsql")
        body = _exec_body(out)
        assert "SET NOCOUNT OFF" in body, out
        assert "SET NOCOUNT ON" not in body, out

    def test_injection_still_happens_without_body_directive(self) -> None:
        # A procedure that does not manage NOCOUNT still gets the best-practice
        # default injected (regression guard for the suppression logic).
        oracle = (
            "CREATE OR REPLACE PROCEDURE p\n"
            "(\n"
            "    RESULT_CURSOR OUT SYS_REFCURSOR\n"
            ")\n"
            "AS\nBEGIN\n"
            "    OPEN RESULT_CURSOR FOR SELECT * FROM a_tbl;\n"
            "END;\n/"
        )
        out = _tx(oracle, "oracle", "tsql")
        assert _exec_body(out).count("SET NOCOUNT ON") == 1, out
