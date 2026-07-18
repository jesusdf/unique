# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Function-translation audit for standalone DML.

sqlglot models most specialized functions with their arguments in *named slots*
(Substring -> this/start/length, Replace -> this/expression/replacement, ...),
not in ``expressions``. The converter previously read only ``this`` +
``expressions``, so every named slot was dropped: ``SUBSTRING(a, 1, 3)`` became
``SUBSTR(a)``. These tests pin that all arguments survive, across engines.
"""

from __future__ import annotations

import re

import pytest

from tests.helpers.validity import assert_translated, executable_lines
from unique.core.transpiler import Transpiler

_TARGETS = ("oracle", "postgresql", "mysql")


def _t(sql: str, target: str, source: str = "tsql") -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _expr(out: str) -> str:
    """The select-list expression, whitespace-normalized."""
    head = out.split("FROM")[0]
    head = re.sub(r"(?i)^\s*SELECT\s+", "", head)
    return re.sub(r"\s+", " ", head).strip()


class TestArgumentsPreserved:
    """No argument may be dropped on the way through the IR."""

    @pytest.mark.parametrize("target", _TARGETS)
    def test_substring_keeps_three_args(self, target: str) -> None:
        out = _expr(_t("SELECT SUBSTRING(a, 1, 3) FROM t", target))
        assert "1" in out and "3" in out and "a" in out
        assert out.count(",") == 2
        expected = {
            "oracle": "SUBSTR(",
            "mysql": "SUBSTRING(",
            "postgresql": "SUBSTRING(",
        }[target]
        assert out.upper().startswith(expected), out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_replace_keeps_three_args(self, target: str) -> None:
        out = _expr(_t("SELECT REPLACE(a, 'x', 'y') FROM t", target))
        assert "'x'" in out and "'y'" in out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_round_keeps_precision(self, target: str) -> None:
        out = _expr(_t("SELECT ROUND(a, 2) FROM t", target))
        assert "2" in out and out.count(",") == 1

    @pytest.mark.parametrize("target", _TARGETS)
    def test_stuff_keeps_four_args(self, target: str) -> None:
        # Full output (not _expr): PostgreSQL's OVERLAY(... FROM 1 FOR 2) rewrite
        # contains a FROM that the naive expr-splitter would cut on.
        out = _t("SELECT STUFF(a, 1, 2, 'xy') FROM t", target)
        assert "1" in out and "2" in out and "'xy'" in out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_replicate_keeps_count(self, target: str) -> None:
        out = _expr(_t("SELECT REPLICATE('x', 5) FROM t", target))
        assert "5" in out
        assert out.upper().startswith(("REPEAT(", "RPAD(", "REPLICATE(")), out
        if target in ("mysql", "postgresql"):
            assert "REPLICATE" not in out.upper(), out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_dateadd_keeps_all_args(self, target: str) -> None:
        out = _expr(_t("SELECT DATEADD(day, 1, a) FROM t", target))
        assert "1" in out and "a" in out
        expected = {
            "oracle": "a + NUMTODSINTERVAL(1, 'DAY')",
            "mysql": "DATE_ADD(a, INTERVAL 1 DAY)",
            "postgresql": "a + INTERVAL '1 DAY'",
        }[target]
        assert out == expected, out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_coalesce_variadic(self, target: str) -> None:
        out = _expr(_t("SELECT COALESCE(a, b, 0) FROM t", target))
        assert out.upper().startswith("COALESCE(")
        assert out.count(",") == 2

    @pytest.mark.parametrize("target", _TARGETS)
    def test_concat_variadic(self, target: str) -> None:
        out = _expr(_t("SELECT CONCAT(a, b, c) FROM t", target))
        assert out.count(",") == 2


class TestUnmappedFunctionNamePreserved:
    """A function with no direct equivalent keeps its original name rather than
    degrading to the internal ``ANONYMOUS`` placeholder, so the output is
    reviewable SQL rather than something obviously broken."""

    @pytest.mark.parametrize(
        "fn",
        ["PATINDEX('%x%', a)", "CHOOSE(2, 'a', 'b')", "STR(1.5, 6, 2)"],
    )
    @pytest.mark.parametrize("target", _TARGETS)
    def test_name_not_anonymous(self, fn: str, target: str) -> None:
        out = _t(f"SELECT {fn} FROM t", target)
        assert "ANONYMOUS" not in out.upper()
        assert fn.split("(")[0] in out.upper()


class TestKnownGoodMappings:
    """Spot-check functions that do have clean cross-engine mappings."""

    def test_getutcdate_maps_to_utc_timestamp_on_mysql(self) -> None:
        # Shared pair map (PROCEDURAL_FUNC_MAPS) consumed by the IR too
        # (M3-final): GETUTCDATE is no longer an unmapped passthrough.
        out = _t("SELECT GETUTCDATE() FROM t", "mysql")
        assert "UTC_TIMESTAMP" in out.upper()
        assert "GETUTCDATE" not in out.upper()

    def test_charindex_to_instr_oracle(self) -> None:
        out = _t("SELECT CHARINDEX('x', a) FROM t", "oracle")
        assert_translated(
            out, "oracle", present=("INSTR(a, 'x')",), absent=("CHARINDEX",)
        )

    def test_isnull_to_coalesce(self) -> None:
        for target in _TARGETS:
            out = _t("SELECT ISNULL(a, 0) FROM t", target)
            assert_translated(
                out, target, present=("COALESCE(a, 0)",), absent=("ISNULL",)
            )

    def test_newid_to_uuid(self) -> None:
        out = _t("SELECT NEWID() FROM t", "postgresql")
        assert_translated(
            out, "postgresql", present=("gen_random_uuid()",), absent=("NEWID",)
        )


class TestConditionalFunction:
    """MySQL IF() / T-SQL IIF() translate to each target's conditional.

    Found on the sakila views: IF(cu.active, ...) leaked verbatim into
    T-SQL/PostgreSQL/Oracle output, where no such function exists.
    """

    @pytest.mark.parametrize(
        "source,expr",
        [("mysql", "IF(a > 0, 'y', 'n')"), ("tsql", "IIF(a > 0, 'y', 'n')")],
    )
    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql", "mysql"))
    def test_conditional_translated(self, source: str, expr: str, target: str) -> None:
        if source == target:
            pytest.skip("same-dialect passthrough")
        out = Transpiler().transpile(f"SELECT {expr} FROM t;", source, target).sql
        idiom = {
            "tsql": "IIF(",
            "mysql": "IF(",
            "oracle": "CASE WHEN",
            "postgresql": "CASE WHEN",
        }[target]
        absent = {
            "tsql": ("IF(",),  # IIF( contains IF( — checked via idiom below
            "mysql": ("IIF(", "CASE WHEN"),
            "oracle": ("IIF(", "IF("),
            "postgresql": ("IIF(", "IF("),
        }[target]
        assert_translated(out, target, present=(idiom, "'y'", "'n'"))
        body = executable_lines(out).upper()
        for needle in absent:
            if target == "tsql" and needle == "IF(":
                # IIF( legitimately contains IF(; ensure no bare IF( remains.
                assert not re.search(r"(?<!I)\bIF\(", body), out
            else:
                assert needle not in body, out
