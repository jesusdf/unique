# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Regression guard over the curated ``tests/fixtures/challenge`` corpus.

Each challenge fixture holds anonymized tricky source constructs (one per
``-- CASE:`` entry) that the transpiler once handled wrong. Transpiling them to
every other engine must not fall back to an *unrecognized-construct* carrier
(``UNIQUE: Unhandled`` / ``could not translate``) — a documented degrade for an
intrinsically unsupported feature is fine, an unhandled construct is not. Plus
per-case assertions that the specific fix holds.
"""

from __future__ import annotations

import pathlib

import pytest

from unique.core.transpiler import Transpiler

_CHALLENGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "challenge"
_SOURCE_BY_FILE = {
    "challenge_sqlserver.sql": "tsql",
    "challenge_oracle.sql": "oracle",
    "challenge_postgresql.sql": "postgresql",
    "challenge_mysql.sql": "mysql",
}
_ALL_ENGINES = ("tsql", "oracle", "postgresql", "mysql")
_UNRECOGNIZED_MARKERS = ("UNIQUE: Unhandled", "could not translate")


def _read(fname: str) -> str:
    return (_CHALLENGE_DIR / fname).read_text(encoding="utf-8")


def _exec_lines(sql: str) -> str:
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def _populated_fixtures() -> list[tuple[str, str]]:
    return [
        (fname, src)
        for fname, src in _SOURCE_BY_FILE.items()
        if "-- CASE:" in _read(fname)
    ]


@pytest.mark.parametrize("fname,source", _populated_fixtures())
def test_challenge_fixture_has_no_unrecognized_construct(
    fname: str, source: str
) -> None:
    sql = _read(fname)
    for target in _ALL_ENGINES:
        if target == source:
            continue
        out = Transpiler().transpile(sql, source=source, target=target).sql
        for marker in _UNRECOGNIZED_MARKERS:
            assert marker not in out, f"{fname} -> {target} left {marker!r}:\n{out}"


class TestOracleSelfQualifiedParam:
    """``get_top_rows.row_limit`` (Oracle self-qualified parameter) resolves to
    the target variable and never leaks the ``<routine>.`` qualifier."""

    def _out(self, target: str) -> str:
        return (
            Transpiler()
            .transpile(_read("challenge_oracle.sql"), source="oracle", target=target)
            .sql
        )

    def test_tsql_resolves_to_at_variable(self) -> None:
        out = self._out("tsql")
        assert "@row_limit" in out, out
        assert "SELECT TOP (@row_limit)" in out, out
        assert "get_top_rows." not in _exec_lines(out), out

    def test_mysql_resolves_to_bare_param(self) -> None:
        out = self._out("mysql")
        body = _exec_lines(out)
        assert "get_top_rows." not in body, out
        assert "LIMIT row_limit" in body, out


class TestTsqlCreateProcAbbreviation:
    """``CREATE PROC`` transpiles like ``CREATE PROCEDURE`` and never leaks the
    T-SQL-only ``PROC`` keyword to another engine."""

    def _out(self, target: str) -> str:
        return (
            Transpiler()
            .transpile(_read("challenge_sqlserver.sql"), source="tsql", target=target)
            .sql
        )

    @pytest.mark.parametrize("target", ("postgresql", "oracle", "mysql"))
    def test_proc_becomes_procedure(self, target: str) -> None:
        out = self._out(target)
        assert "PROCEDURE" in out.upper(), out
        # the bare abbreviation must not survive as a keyword
        import re

        assert not re.search(
            r"\bPROC\b(?!EDURE)", _exec_lines(out), re.IGNORECASE
        ), f"leaked PROC abbreviation ({target}):\n{out}"
