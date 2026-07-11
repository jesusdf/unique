# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""PG-source wave 1 (baseline 2026-07-11): session GUC settings.

PostgreSQL's ``SET <guc> = <v>`` / ``SET <guc> TO <v>`` / ``RESET <guc>``
are engine-local session knobs with no meaning elsewhere — shipped raw they
were the largest single class of the pg→tsql baseline (111x near-'=' plus
29x near-'to') and error on every other engine. They degrade to the
documented carrier, like SQL*Plus directives do. Real SQL SET forms
(TRANSACTION, CONSTRAINTS, ROLE, SESSION AUTHORIZATION) keep their path.
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler


def _t(sql: str, target: str) -> str:
    return Transpiler().transpile(sql, source="postgresql", target=target).sql


class TestPgGucSettings:
    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_guc_assignment_degrades(self, target: str) -> None:
        out = _t("SET extra_float_digits = 0;", target)
        assert "UNIQUE:" in out, out
        assert not re.search(r"(?im)^\s*SET\s+extra_float_digits", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_guc_to_spelling_degrades(self, target: str) -> None:
        out = _t("set enable_presorted_aggregate to off;", target)
        assert "UNIQUE:" in out, out
        assert not re.search(r"(?im)^\s*set\s+enable_", out), out

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle"])
    def test_reset_degrades(self, target: str) -> None:
        out = _t("RESET enable_seqscan;", target)
        assert "UNIQUE:" in out, out
        assert not re.search(r"(?im)^\s*RESET\b", out), out

    def test_guc_kept_on_pg_target(self) -> None:
        out = _t("SET extra_float_digits = 0;", "postgresql")
        assert re.search(r"(?im)^\s*SET\s+extra_float_digits\s*=\s*0", out), out

    def test_set_transaction_keeps_its_path(self) -> None:
        out = _t("SET TRANSACTION ISOLATION LEVEL READ COMMITTED;", "tsql")
        assert "UNIQUE:" not in out or "TRANSACTION" in out.upper(), out
        assert re.search(r"(?i)TRANSACTION", out), out


class TestValuesRelation:
    """``FROM (VALUES (1,'x'),(2,'y')) v(a,b)`` converted to NOTHING — the
    FROM emitted empty (silent loss caught by the gate; the whole
    'Expected table name but got CROSS/ON/GROUP_BY' family of the
    baseline). Lowered to a UNION ALL chain of row-SELECTs, valid on all
    four engines."""

    _SRC = "select a, b from (values (1,'x'),(2,'y')) v(a,b);"

    @pytest.mark.parametrize("target", ["tsql", "mysql", "oracle", "postgresql"])
    def test_values_relation_survives(self, target: str) -> None:
        import sqlglot

        out = _t(self._SRC, target)
        assert re.search(r"(?i)FROM\s*\(SELECT\s+1\s+AS\s+a", out), out
        assert re.search(r"(?i)UNION ALL", out), out
        assert re.search(r"(?i)\)\s*v\b", out), out
        read = {
            "tsql": "tsql",
            "mysql": "mysql",
            "oracle": "oracle",
            "postgresql": "postgres",
        }[target]
        sqlglot.parse(out, read=read)

    def test_oracle_arms_get_from_dual(self) -> None:
        out = _t(self._SRC, "oracle")
        assert out.upper().count("FROM DUAL") == 2, out

    def test_values_with_string_agg(self) -> None:
        out = _t("select string_agg(a, ',') from (values ('aa'),('bb')) g(a);", "tsql")
        assert "UNIQUE:" not in out, out
        assert re.search(r"(?i)STRING_AGG", out), out
