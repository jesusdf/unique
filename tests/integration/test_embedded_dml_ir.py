# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Embedded DML goes through the IR pipeline (audit doc-04 P4 / milestone M3).

Two defect classes from the 2026-07-08 private-fixture sweep are probed here:

- **D3** — ``INSERT … SELECT … FROM DUAL WHERE NOT EXISTS (…)`` must lose
  ``FROM DUAL`` on engines that have no ``dual`` relation (PostgreSQL, T-SQL).
  The SELECT is *nested* (an INSERT source, a scalar subquery), which the
  transform passes previously never visited: pass recursion stopped at
  top-level SelectStatements.
- **D4** — ``ROWNUM`` inside DML embedded in a *routine body* must translate
  exactly as the standalone DML pipeline translates it (``LIMIT`` / ``TOP``).
  Before M3 the procedural engine ran embedded DML through raw
  ``sqlglot.transpile`` + text fixups, so every mapping the IR converter knew
  was silently absent from routine bodies (the "mapped in one pipeline, not
  the other" genre).

Every assertion pair states the target idiom is present AND the source idiom
is absent, so the tests fail under an identity transpiler; standalone outputs
are additionally parsed in the target dialect.
"""

from __future__ import annotations

import re

import pytest
import sqlglot

from unique.core.transpiler import Transpiler

_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "postgresql": "postgres",
    "mysql": "mysql",
    "oracle": "oracle",
}


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _assert_parses(out: str, target: str) -> None:
    sqlglot.parse(
        out,
        read=_SQLGLOT_DIALECT[target],
        error_level=sqlglot.ErrorLevel.RAISE,
    )


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


# ---------------------------------------------------------------------------
# D3 — FROM DUAL in nested query positions (standalone DML pipeline)
# ---------------------------------------------------------------------------

_D3_INSERT = (
    "INSERT INTO cfg (k, v) SELECT 'x', 1 FROM DUAL "
    "WHERE NOT EXISTS (SELECT 1 FROM cfg WHERE k = 'x')"
)


@pytest.mark.parametrize("target", ["postgresql", "tsql"])
def test_insert_select_from_dual_guard_drops_dual(target: str) -> None:
    out = _t(_D3_INSERT, "oracle", target)
    up = _norm(out).upper()
    assert "DUAL" not in up
    assert "INSERT INTO CFG" in up  # statement survived, no carrier degrade
    assert "NOT EXISTS" in up  # the guard condition survived
    assert "UNIQUE:" not in out  # not degraded to a carrier comment
    _assert_parses(out, target)


@pytest.mark.parametrize("target", ["postgresql", "tsql"])
def test_scalar_subquery_from_dual_drops_dual(target: str) -> None:
    # Neighbor: DUAL inside a scalar subquery in an UPDATE assignment.
    out = _t(
        "UPDATE t SET v = (SELECT SYSDATE FROM DUAL) WHERE id = 1", "oracle", target
    )
    up = _norm(out).upper()
    assert "DUAL" not in up
    assert up.startswith("UPDATE T SET")
    assert "WHERE ID = 1" in up
    _assert_parses(out, target)


@pytest.mark.parametrize("target", ["postgresql", "tsql"])
def test_rownum_in_subquery_becomes_limit(target: str) -> None:
    # Neighbor: ROWNUM inside a DELETE's IN-subquery (nested position).
    out = _t(
        "DELETE FROM t WHERE id IN (SELECT id FROM old_t WHERE ROWNUM <= 10)",
        "oracle",
        target,
    )
    up = _norm(out).upper()
    assert "ROWNUM" not in up
    assert "DELETE FROM T" in up
    assert (
        ("LIMIT 10" in up)
        or ("TOP 10" in up)
        or ("TOP (10)" in up)
        or ("FETCH FIRST 10" in up)
    )
    _assert_parses(out, target)


# ---------------------------------------------------------------------------
# D3/D4 — the same shapes inside a routine body (procedural pipeline)
# ---------------------------------------------------------------------------

_ORACLE_PROC_D3 = """\
CREATE OR REPLACE PROCEDURE seed_cfg AS
BEGIN
  INSERT INTO cfg (k, v)
  SELECT 'x', 1 FROM DUAL
  WHERE NOT EXISTS (SELECT 1 FROM cfg WHERE k = 'x');
END;
"""

_ORACLE_PROC_D4 = """\
CREATE OR REPLACE PROCEDURE copy_top AS
BEGIN
  INSERT INTO log_t (id)
  SELECT id FROM src_t WHERE ROWNUM <= 10;
END;
"""


@pytest.mark.parametrize("target", ["postgresql", "tsql"])
def test_procedural_insert_dual_guard_drops_dual(target: str) -> None:
    out = _t(_ORACLE_PROC_D3, "oracle", target)
    up = _norm(out).upper()
    assert "DUAL" not in up
    assert "INSERT INTO CFG" in up
    assert "NOT EXISTS" in up
    assert "UNIQUE:" not in out  # neither degraded nor warned-invalid


@pytest.mark.parametrize("target", ["postgresql", "tsql"])
def test_procedural_rownum_translates_like_standalone(target: str) -> None:
    out = _t(_ORACLE_PROC_D4, "oracle", target)
    up = _norm(out).upper()
    assert "ROWNUM" not in up
    assert "INSERT INTO LOG_T" in up
    assert (
        ("LIMIT 10" in up)
        or ("TOP 10" in up)
        or ("TOP (10)" in up)
        or ("FETCH FIRST 10" in up)
    )
    assert "UNIQUE:" not in out


# ---------------------------------------------------------------------------
# IR core regressions surfaced by routing more traffic through it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
def test_boolean_parens_preserved(target: str) -> None:
    # The converter drops explicit paren nodes; the emitter must restore them
    # by precedence or `a = 1 AND (b OR (c AND d))` silently re-associates.
    out = _t(
        "SELECT 1 FROM t WHERE a = 1 AND (b IS NULL OR (c = 1 AND d = 2))",
        "tsql",
        target,
    )
    up = _norm(out).upper()
    # The parens around the OR-group are the semantically required ones
    # (without them the AND re-associates); the inner AND needs none.
    assert "AND (B IS NULL OR C = 1 AND D = 2)" in up
    _assert_parses(out, target)


@pytest.mark.parametrize("target", ["postgresql", "mysql"])
def test_derived_table_where_not_duplicated(target: str) -> None:
    # find(exp.Where) descended into the derived table and re-emitted ITS
    # where on the outer SELECT (invalid SQL: aliases out of scope).
    out = _t(
        "SELECT * FROM (SELECT x, y FROM t WHERE x = 1 "
        "UNION ALL SELECT 1, 2) AS d ORDER BY y DESC",
        "tsql",
        target,
    )
    up = _norm(out).upper()
    assert up.count("WHERE") == 1
    assert "ORDER BY Y DESC" in up
    _assert_parses(out, target)


def test_tsql_desc_null_ordering_preserved_on_postgresql() -> None:
    # T-SQL sorts NULLs low (DESC puts them last); PostgreSQL's DESC default
    # is NULLS FIRST, so the source order must be spelled out.
    out = _t("SELECT a FROM t ORDER BY a DESC", "tsql", "postgresql")
    assert "NULLS LAST" in _norm(out).upper()
    _assert_parses(out, "postgresql")


def test_procedural_inline_comment_does_not_eat_terminator() -> None:
    # An inline comment harvested from the statement is re-emitted as a line
    # comment; it must land BEFORE the statement, or the terminator the
    # procedural emitter appends would end up commented out.
    src = (
        "CREATE OR REPLACE PROCEDURE note_p AS\n"
        "BEGIN\n"
        "  UPDATE t SET a = 1 WHERE b = 2 /* keep me */;\n"
        "END;\n"
    )
    out = _t(src, "oracle", "postgresql")
    assert "keep me" in out  # comment preserved (no silent loss)
    assert re.search(r"WHERE b = 2\s*;", out)  # terminator on the statement
    assert not re.search(r"--[^\n]*;\s*\n\s*END", out)  # ... not on a comment


@pytest.mark.parametrize("target", ["postgresql", "mysql"])
def test_procedural_getdate_maps_inside_body_dml(target: str) -> None:
    # T-SQL source neighbor: a function mapping (GETDATE) inside embedded DML
    # must come out as the target's spelling via the shared IR mappings.
    src = (
        "CREATE PROCEDURE dbo.touch_row AS\n"
        "BEGIN\n"
        "  UPDATE t SET updated_at = GETDATE() WHERE id = 1;\n"
        "END"
    )
    out = _t(src, "tsql", target)
    up = _norm(out).upper()
    assert "GETDATE" not in up
    assert "CURRENT_TIMESTAMP" in up or "NOW()" in up
    assert "UPDATE T SET" in up
