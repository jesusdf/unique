# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Oracle SQL*Plus ``EXEC proc(args)`` → each target's call form (audit D1).

Before the fix, an Oracle-source ``EXEC my_proc('a', 1)`` parsed in sqlglot as
an *alias* expression and shipped as ``EXEC AS my_proc;`` — T-SQL impersonation
syntax with the arguments silently dropped — on every target (~6,500
statements on the real dump's PG direction). The batch classifier now routes
Oracle ``EXEC``/``EXECUTE`` batches to the procedural engine, which models the
call and emits per-target syntax.
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


@pytest.mark.parametrize("spelling", ["EXEC", "EXECUTE"])
@pytest.mark.parametrize("target", ["postgresql", "mysql"])
def test_oracle_exec_with_args_becomes_call(target: str, spelling: str) -> None:
    out = _t(f"{spelling} my_proc('a', 1);", "oracle", target)
    up = _norm(out).upper()
    assert "CALL MY_PROC('A', 1)" in up.replace('"', "")
    assert "EXEC" not in up  # no EXEC leaks (also excludes EXEC AS)
    assert "UNIQUE:" not in out


@pytest.mark.parametrize("target", ["postgresql", "mysql"])
def test_oracle_exec_no_args_becomes_call(target: str) -> None:
    out = _t("EXEC my_proc;", "oracle", target)
    up = _norm(out).upper()
    assert re.search(r"CALL MY_PROC\s*\(\s*\)", up)
    assert "EXEC" not in up
    assert "UNIQUE:" not in out


def test_oracle_exec_with_args_becomes_tsql_exec() -> None:
    # T-SQL EXEC passes arguments positionally, without parentheses.
    out = _t("EXEC my_proc('a', 1);", "oracle", "tsql")
    up = _norm(out).upper()
    assert re.search(r"EXEC(?:UTE)?\s+MY_PROC\s+'A'\s*,\s*1", up)
    assert "EXEC AS" not in up
    assert "UNIQUE:" not in out


def test_oracle_exec_no_args_becomes_tsql_exec() -> None:
    out = _t("EXEC my_proc;", "oracle", "tsql")
    up = _norm(out).upper()
    assert re.search(r"EXEC(?:UTE)?\s+MY_PROC\s*;?", up)
    assert "EXEC AS" not in up
    assert "UNIQUE:" not in out


def test_oracle_exec_arguments_never_dropped() -> None:
    # The original defect dropped the argument list silently — the worst
    # part of D1. Every argument must survive on every target.
    for target in ("postgresql", "mysql", "tsql"):
        out = _t("EXEC my_proc('alpha', 42, 'omega');", "oracle", target)
        for token in ("'alpha'", "42", "'omega'"):
            assert token in out, (target, out)
