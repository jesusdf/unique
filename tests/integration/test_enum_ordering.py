# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""MySQL ENUM declaration-order sort key (B29).

A MySQL ``ENUM('lo','mid','hi')`` orders by its declaration index (lo<mid<hi)
in a SORT context; the ENUM->VARCHAR+CHECK degrade makes every other target
sort alphabetically (hi<lo<mid). The transformer rewrites ``ORDER BY`` on the
column into the ordinal ``CASE`` sort key, keeping the plain value everywhere
else.

Only the SORT is index-ordered. MySQL 8.4 compares an ENUM to a string literal
(``a > 'lo'`` returns only 'mid', not {'mid','hi'}) and aggregates it
(``MIN(a)`` returns 'hi', ``MAX(a)`` returns 'mid') by STRING value — verified
live below — which is exactly what the VARCHAR degrade already does. So the
comparison/MIN/MAX neighbors assert the value is LEFT PLAIN (rewriting them
would diverge from MySQL); the brief's index-order legs for those were an
over-extrapolation of the ORDER-BY finding.

This module covers the challenge case's combinatorial neighbors (the corpus
carries only the bare ``ORDER BY``): ``WHERE c > 'lo'``, ``MIN``/``MAX``, and
two ENUM columns in one table. Each offline assertion names the target idiom
that must appear AND the source idiom that must be gone, and parses the output
in the target dialect. The live test executes the source on MySQL and each
transpiled output on the target engine and compares the *ordered* result (the
whole point is order), which ``test_challenge_live``'s order-insensitive diff
cannot see.
"""

from __future__ import annotations

import contextlib

import pytest

from tests.helpers.corpus_diff import urls_from_env
from tests.helpers.validity import assert_statements_parse
from unique.core.transpiler import Transpiler

_TARGETS = ("postgresql", "tsql", "oracle")

_DDL = "CREATE TABLE b29_en (a ENUM('lo','mid','hi'));\n"
_DDL2 = "CREATE TABLE b29_two (a ENUM('lo','mid','hi'), b ENUM('s','m','l'));\n"


def _exe(sql: str) -> str:
    """Output with ``--`` comment lines dropped (no comment-prose matches)."""
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def _tx(sql: str, target: str) -> str:
    return Transpiler().transpile(sql, source="mysql", target=target).sql


# One ordinal CASE arm the rewrite must emit for the a-column value list. The
# WHEN condition proves the value->index mapping happened.
_ORDINAL = ("WHEN 'lo' THEN 1", "WHEN 'mid' THEN 2", "WHEN 'hi' THEN 3")


@pytest.mark.parametrize("target", _TARGETS)
def test_order_by_enum_uses_ordinal_case(target: str) -> None:
    out = _exe(_tx(_DDL + "SELECT a FROM b29_en ORDER BY a;", target))
    assert "ORDER BY CASE a" in out, out
    for arm in _ORDINAL:
        assert arm in out, out
    assert "ORDER BY a " not in out and "ORDER BY a\n" not in out, out
    assert_statements_parse(out, target, context="enum order-by")


@pytest.mark.parametrize("target", _TARGETS)
def test_inequality_enum_stays_string_comparison(target: str) -> None:
    # Neighbor: MySQL compares ``a > 'lo'`` by STRING (only 'mid' > 'lo'), which
    # the VARCHAR degrade already matches — so it must be LEFT PLAIN, not turned
    # into an ordinal CASE (that would wrongly also return 'hi').
    out = _exe(_tx(_DDL + "SELECT a FROM b29_en WHERE a > 'lo';", target))
    assert "a > 'lo'" in out, out
    assert "CASE a" not in out, out
    assert_statements_parse(out, target, context="enum inequality")


@pytest.mark.parametrize("target", _TARGETS)
def test_min_max_enum_stays_string_aggregate(target: str) -> None:
    # Neighbor: MySQL MIN/MAX over an ENUM is by STRING value (MIN='hi'), which
    # the VARCHAR degrade already matches — so it must be LEFT PLAIN.
    out = _exe(_tx(_DDL + "SELECT MIN(a), MAX(a) FROM b29_en;", target))
    assert "MIN(a)" in out and "MAX(a)" in out, out
    assert "CASE" not in out, out
    assert_statements_parse(out, target, context="enum min/max")


@pytest.mark.parametrize("target", _TARGETS)
def test_two_enum_columns_each_get_own_sort_key(target: str) -> None:
    out = _exe(_tx(_DDL2 + "SELECT a, b FROM b29_two ORDER BY a, b;", target))
    assert "CASE a" in out and "WHEN 'hi' THEN 3" in out, out
    assert "CASE b" in out and "WHEN 's' THEN 1" in out and "WHEN 'l' THEN 3" in out
    # Projection keeps the plain values (only the ORDER BY is a sort key).
    assert "SELECT a, b" in out, out
    assert_statements_parse(out, target, context="enum two-columns")


@pytest.mark.parametrize("target", _TARGETS)
def test_equality_and_group_by_keep_plain_value(target: str) -> None:
    out = _exe(_tx(_DDL + "SELECT a FROM b29_en WHERE a = 'lo' GROUP BY a;", target))
    # Equality and GROUP BY are NOT ordering-sensitive — no CASE injected.
    assert "CASE a" not in out, out
    assert "a = 'lo'" in out and "GROUP BY a" in out, out


@pytest.mark.parametrize("target", _TARGETS)
def test_order_by_rewrite_emits_no_warning(target: str) -> None:
    # The ORDER BY rewrite is faithful, so it must not spam a carrier/warning
    # (the maintainer rejected blanket ENUM-degrade warnings on real schemas).
    result = Transpiler().transpile(
        _DDL + "SELECT a FROM b29_en ORDER BY a;", source="mysql", target=target
    )
    assert not result.warnings, [w.message for w in result.warnings]


# --- live order-sensitive differential (four engines) -----------------------

# (label, source SQL run on MySQL, expected ordered result). The transpiled
# output is executed on each target and its ordered result must equal MySQL's.
_LIVE_SHAPES: tuple[tuple[str, str], ...] = (
    ("order-by", "SELECT a FROM b29_en ORDER BY a"),
    ("inequality", "SELECT a FROM b29_en WHERE a > 'lo' ORDER BY a"),
    ("min-max", "SELECT MIN(a), MAX(a) FROM b29_en"),
)

_LIVE_DDL = (
    "CREATE TABLE b29_en (a ENUM('lo','mid','hi'))",
    "INSERT INTO b29_en VALUES ('hi'),('lo'),('mid')",
)


def _norm(rows: object) -> list[tuple]:
    """Order-PRESERVING normalization: stringify + strip cells, keep row order."""
    out: list[tuple] = []
    for row in rows or []:  # type: ignore[union-attr]
        out.append(tuple(c.strip() if isinstance(c, str) else c for c in row))
    return out


def _drop_b29(conn: object) -> None:
    """Drop the scratch table, rolling back on failure so a missing-table error
    does not leave the connection's transaction aborted (PostgreSQL)."""
    cur = conn.cursor()  # type: ignore[attr-defined]
    try:
        cur.execute("DROP TABLE b29_en")
        conn.commit()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - stale/absent table; clear the tx state
        with contextlib.suppress(Exception):
            conn.rollback()  # type: ignore[attr-defined]


def _run_ordered(engine: str, url: str, ddl_setup: str, query: str) -> list[tuple]:
    from tests.functional_equivalence.engine_runner import connect, split_statements

    conn = connect(engine, url)
    try:
        _drop_b29(conn)
        cur = conn.cursor()
        for stmt in split_statements(ddl_setup, engine):
            if stmt.strip():
                cur.execute(stmt)
        conn.commit()
        cur.execute(query)
        rows = cur.fetchall()
        return _norm(rows)
    finally:
        _drop_b29(conn)
        conn.close()


@pytest.mark.integration
@pytest.mark.parametrize("label,query", _LIVE_SHAPES, ids=[s[0] for s in _LIVE_SHAPES])
@pytest.mark.parametrize("target", _TARGETS)
def test_enum_order_result_matches_mysql_live(
    label: str, query: str, target: str
) -> None:
    urls = urls_from_env()
    if "mysql" not in urls or target not in urls:
        pytest.skip(f"needs live URLs for mysql and {target}")

    source_ddl = ";\n".join(_LIVE_DDL) + ";\n" + query + ";"
    expected = _run_ordered("mysql", urls["mysql"], ";\n".join(_LIVE_DDL) + ";", query)

    result = Transpiler().transpile(source_ddl, source="mysql", target=target)
    assert not result.warnings, [w.message for w in result.warnings]
    # Re-split the transpiled DDL+query: run the DDL for effect, the last
    # statement is the observable query.
    from tests.functional_equivalence.engine_runner import split_statements

    stmts = [s for s in split_statements(result.sql, target) if s.strip()]
    setup = ";\n".join(stmts[:-1])
    actual = _run_ordered(target, urls[target], setup, stmts[-1])

    assert actual == expected, (
        f"{label} mysql->{target}: transpiled output ordered differently.\n"
        f"  mysql : {expected}\n  {target:>6}: {actual}\n  output: {result.sql!r}"
    )
