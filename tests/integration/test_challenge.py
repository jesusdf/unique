# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Regression guard over the curated ``tests/fixtures/challenge`` corpus.

Each challenge fixture holds anonymized tricky source constructs (one per
``-- CASE:`` entry) that the transpiler once handled wrong. Transpiling each
case to every other engine must not fall back to an *unrecognized-construct*
carrier (``UNIQUE: Unhandled`` / ``could not translate``) — a documented degrade
for an intrinsically unsupported feature is fine, an unhandled construct is not.
Plus per-case assertions that the specific fix holds.
"""

from __future__ import annotations

import pathlib
import re

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


def _cases(fname: str) -> list[str]:
    """Split a fixture into its ``-- CASE:`` blocks (each self-contained)."""
    blocks = re.split(r"(?m)^(?=-- CASE:)", _read(fname))
    return [b.strip() for b in blocks if b.strip().startswith("-- CASE:")]


def _case(fname: str, keyword: str) -> str:
    for block in _cases(fname):
        if keyword.lower() in block.splitlines()[0].lower():
            return block
    raise KeyError(f"no CASE matching {keyword!r} in {fname}")


def _tx(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _all_cases() -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    for fname, src in _SOURCE_BY_FILE.items():
        for i in range(len(_cases(fname))):
            out.append((fname, src, i))
    return out


@pytest.mark.parametrize("fname,source,case_idx", _all_cases())
def test_case_has_no_unrecognized_construct(
    fname: str, source: str, case_idx: int
) -> None:
    sql = _cases(fname)[case_idx]
    for target in _ALL_ENGINES:
        if target == source:
            continue
        out = _tx(sql, source, target)
        for marker in _UNRECOGNIZED_MARKERS:
            assert (
                marker not in out
            ), f"{fname}[{case_idx}] -> {target}: {marker!r}\n{out}"


class TestOracleSelfQualifiedParam:
    """``get_top_rows.row_limit`` (Oracle self-qualified parameter) resolves to
    the target variable and never leaks the ``<routine>.`` qualifier."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_oracle.sql", "self-qualified"), "oracle", target)

    def test_tsql_resolves_to_at_variable(self) -> None:
        out = self._out("tsql")
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

    @pytest.mark.parametrize("target", ("postgresql", "oracle", "mysql"))
    def test_proc_becomes_procedure(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "PROC abbreviation"), "tsql", target)
        assert "PROCEDURE" in out.upper(), out
        assert not re.search(
            r"\bPROC\b(?!EDURE)", _exec_lines(out), re.IGNORECASE
        ), f"leaked PROC abbreviation ({target}):\n{out}"


class TestTsqlCreateOrAlter:
    """``CREATE OR ALTER`` (T-SQL 2016+) routes to the procedural engine and maps
    to the other engines' ``CREATE OR REPLACE`` — never an Unhandled carrier."""

    @pytest.mark.parametrize("target", ("postgresql", "oracle"))
    def test_maps_to_create_or_replace(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "CREATE OR ALTER"), "tsql", target)
        assert "CREATE OR REPLACE PROCEDURE" in out, out
        assert "UNIQUE: Unhandled" not in out, out

    def test_tsql_roundtrip_preserves_or_alter(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "CREATE OR ALTER"), "tsql", "tsql")
        assert "CREATE OR ALTER PROCEDURE" in out, out


class TestTsqlBeginTransaction:
    """``BEGIN TRANSACTION`` maps to each engine's transaction-open form; Oracle
    (implicit transactions) drops it with a documented carrier + warning."""

    def _case_sql(self) -> str:
        return _case("challenge_sqlserver.sql", "BEGIN TRANSACTION")

    def test_tsql_keeps_begin_transaction(self) -> None:
        assert "BEGIN TRANSACTION" in _tx(self._case_sql(), "tsql", "tsql")

    @pytest.mark.parametrize("target", ("postgresql", "mysql"))
    def test_other_engines_open_a_transaction(self, target: str) -> None:
        body = _exec_lines(_tx(self._case_sql(), "tsql", target))
        assert re.search(r"(?i)\bBEGIN\b|\bSTART TRANSACTION\b", body), body

    def test_oracle_drops_with_warning(self) -> None:
        result = Transpiler().transpile(
            self._case_sql(), source="tsql", target="oracle"
        )
        assert "BEGIN" not in _exec_lines(result.sql), result.sql
        assert any("BEGIN TRANSACTION dropped" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]
