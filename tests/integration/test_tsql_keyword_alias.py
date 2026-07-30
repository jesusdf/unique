# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""T-SQL keyword-abbreviation handling.

T-SQL accepts ``PROC`` as a documented abbreviation of ``PROCEDURE`` in
``CREATE``/``ALTER``/``DROP`` (Microsoft T-SQL reference). The abbreviated
spelling must transpile identically to the full one — routed to the
procedural engine for CREATE/ALTER, and normalized to ``PROCEDURE`` for the
DROP DDL path (``DROP PROC`` is not valid on any other engine).
"""

from __future__ import annotations

import re

from tests.helpers.validity import assert_statements_parse
from unique.core.transpiler import Transpiler

_TARGETS = ("postgresql", "oracle", "mysql")


def _tx(sql: str, target: str) -> object:
    return Transpiler().transpile(sql, source="tsql", target=target)


class TestCreateProcAlias:
    """``CREATE PROC`` == ``CREATE PROCEDURE``."""

    FULL = "CREATE PROCEDURE dbo.p @a INT AS BEGIN SELECT @a; END"
    ABBR = "CREATE PROC dbo.p @a INT AS BEGIN SELECT @a; END"

    def test_abbreviation_matches_full_spelling_all_targets(self) -> None:
        for target in _TARGETS:
            full = _tx(self.FULL, target)
            abbr = _tx(self.ABBR, target)
            assert abbr.sql == full.sql, f"{target}: PROC differs from PROCEDURE"

    def test_abbreviation_reaches_procedural_engine(self) -> None:
        for target in _TARGETS:
            out = _tx(self.ABBR, target)
            assert not re.search(
                re.escape("UNIQUE") + r"(?:-\d{4})?" + re.escape(": Unhandled"), out.sql
            ), out.sql
            assert not out.unsupported, out.unsupported
            assert "PROCEDURE" in out.sql.upper()
            assert_statements_parse(out.sql, target, context=f"CREATE PROC->{target}")

    def test_lowercase_abbreviation(self) -> None:
        out = _tx("create proc p as begin select 1; end", "postgresql")
        assert not re.search(
            re.escape("UNIQUE") + r"(?:-\d{4})?" + re.escape(": Unhandled"), out.sql
        ), out.sql
        assert "CREATE OR REPLACE PROCEDURE" in out.sql


class TestAlterProcAlias:
    """``ALTER PROC`` == ``ALTER PROCEDURE``."""

    FULL = "ALTER PROCEDURE dbo.p @a INT AS BEGIN SELECT @a; END"
    ABBR = "ALTER PROC dbo.p @a INT AS BEGIN SELECT @a; END"

    def test_abbreviation_matches_full_spelling(self) -> None:
        for target in _TARGETS:
            full = _tx(self.FULL, target)
            abbr = _tx(self.ABBR, target)
            assert abbr.sql == full.sql, f"{target}: ALTER PROC differs"

    def test_abbreviation_reaches_procedural_engine(self) -> None:
        out = _tx(self.ABBR, "postgresql")
        assert not re.search(
            re.escape("UNIQUE") + r"(?:-\d{4})?" + re.escape(": Unhandled"), out.sql
        ), out.sql
        assert not out.unsupported, out.unsupported
        assert "PROCEDURE" in out.sql.upper()


class TestDropProcAlias:
    """``DROP PROC`` normalizes to ``DROP PROCEDURE`` on every target.

    ``PROC`` is a T-SQL-only spelling; leaking it into the output is invalid
    SQL on PostgreSQL/Oracle/MySQL.
    """

    def test_drop_proc_emits_procedure_all_targets(self) -> None:
        for target in _TARGETS:
            out = _tx("DROP PROC dbo.my_proc", target)
            assert not out.unsupported, out.unsupported
            body = "\n".join(
                ln for ln in out.sql.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "DROP PROCEDURE" in body.upper(), out.sql
            # the bare PROC abbreviation must not survive as a keyword
            assert not re.search(
                r"\bPROC\b(?!EDURE)", body, re.IGNORECASE
            ), f"{target}: leaked PROC abbreviation:\n{out.sql}"

    def test_drop_proc_matches_full_spelling(self) -> None:
        for target in _TARGETS:
            full = _tx("DROP PROCEDURE dbo.my_proc", target)
            abbr = _tx("DROP PROC dbo.my_proc", target)
            assert abbr.sql == full.sql, f"{target}: DROP PROC differs"
