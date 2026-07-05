# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Property-based invariants for the DML/SELECT path.

Hypothesis generates portable SELECT statements (tests/helpers/sql_gen.py) and
asserts, for every source→target pair, invariants that must always hold:

  * the transpiler never crashes and emits non-empty output;
  * no Python ``None`` leaks into the SQL (the ``LIMIT None`` class of bug);
  * the output is valid SQL for the target (parses under sqlglot RAISE — this
    catches structural breakage like a dropped derived-table alias or an empty
    ``INNER JOIN  ON``);
  * a leading comment is preserved (never dropped);
  * derived-table aliases are conserved (no silent loss);
  * a source→target→source round-trip stays valid.

Any failure shrinks to a minimal reproducing statement.
"""

from __future__ import annotations

import re

import sqlglot
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tests.helpers.sql_gen import select_query
from unique.core.transpiler import transpile

DIALECTS = ["tsql", "oracle", "postgresql", "mysql"]
_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}

_SETTINGS = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)


def _parses(sql: str, dialect: str) -> bool:
    try:
        sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)
        return True
    except Exception:
        return False


def _assert_valid(sql: str, dialect: str, ctx: object) -> None:
    try:
        sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)
    except Exception as e:  # pragma: no cover - failure path
        raise AssertionError(f"invalid {dialect} output ({ctx}): {e}\n{sql}") from None


@_SETTINGS
@given(select_query(), st.sampled_from(DIALECTS))
def test_output_is_valid_target_sql(sql: str, source: str) -> None:
    assume(_parses(sql, source))
    for target in DIALECTS:
        if target == source:
            continue
        out = transpile(sql, source, target).sql
        assert out.strip(), (source, target, sql)
        assert "None" not in out, (source, target, sql, out)
        # An IR node's repr must never leak into the SQL (a str()/repr() fallback).
        assert "SourceLocation(" not in out, (source, target, sql, out)
        _assert_valid(out, target, (source, target, sql))


@_SETTINGS
@given(select_query(with_comment=True), st.sampled_from(DIALECTS))
def test_leading_comment_preserved(sql: str, source: str) -> None:
    assume(_parses(sql, source))
    note = sql.splitlines()[0].strip()
    for target in DIALECTS:
        if target == source:
            continue
        out = transpile(sql, source, target).sql
        assert note in out, (source, target, note, out)


@_SETTINGS
@given(select_query(), st.sampled_from(DIALECTS))
def test_derived_table_aliases_conserved(sql: str, source: str) -> None:
    assume(_parses(sql, source))
    # Every derived-table alias in the source must survive to the output.
    src_aliases = {"t"} | ({"u"} if " u ON " in sql else set())
    for target in DIALECTS:
        if target == source:
            continue
        out = transpile(sql, source, target).sql
        for alias in src_aliases:
            assert re.search(rf"\b{alias}\b", out), (source, target, alias, out)


@_SETTINGS
@given(select_query())
def test_round_trip_stays_valid(sql: str) -> None:
    assume(_parses(sql, "tsql"))
    for target in ["postgresql", "mysql", "oracle"]:
        mid = transpile(sql, "tsql", target).sql
        back = transpile(mid, target, "tsql").sql
        _assert_valid(back, "tsql", f"round-trip via {target}: {sql}")
