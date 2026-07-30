# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for ``unique.core.similarity`` — structural similarity scoring.

Every assertion here must fail under both a ``compare -> 100`` stub and a
``compare -> 0`` stub (assertion-quality bar): the floor tests fail at 0, the
ceiling/edge tests fail at 100.

The four ``tests/fixtures/procedures`` variants are the same routines in the
four dialects — the acceptance corpus. Same-function pairs must clear a high
floor; unrelated scripts must stay under a low ceiling. The floors below are
calibrated to the measured distribution (2026-07-30, HEAD of F1): same-function
overall spans 17.1–99.0, unrelated 0.0–2.5. They are ratchet floors — a
regression that narrows the gap should trip them.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import pytest
from click.testing import CliRunner

from unique.cli.main import cli
from unique.core.similarity import SimilarityReport, compare

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "procedures"
_DIALECT = {
    "sqlserver": "tsql",
    "oracle": "oracle",
    "postgresql": "postgresql",
    "mysql": "mysql",
}
# Ratchet floors: calibrated to the measured 4-dialect corpus distribution.
_SAME_FUNCTION_FLOOR = 15.0
_UNRELATED_CEILING = 8.0


def _read(name: str) -> str:
    return (_FIXTURES / f"procedures_{name}.sql").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Identity and normalization idempotence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,dialect", list(_DIALECT.items()))
def test_identity_scores_100_on_every_dimension(name: str, dialect: str) -> None:
    sql = _read(name)
    report = compare(sql, sql, dialect, dialect)
    assert report.overall == 100.0
    for dimension, score in report.dimensions.items():
        assert score == 100.0, f"{dimension} was {score}, expected 100"


def test_normalization_is_idempotent_small() -> None:
    sql = "SELECT a, b FROM t WHERE x = 1"
    assert compare(sql, sql, "postgresql", "postgresql").overall == 100.0


def test_cross_dialect_identity_is_high() -> None:
    # T-SQL and its PostgreSQL transpilation share the same pivot: near-perfect.
    report = compare(_read("sqlserver"), _read("postgresql"), "tsql", "postgresql")
    assert report.overall > 90.0


# ---------------------------------------------------------------------------
# Acceptance corpus: same-function high, unrelated low
# ---------------------------------------------------------------------------


def test_same_function_pairs_clear_the_floor() -> None:
    scores = {
        (a, b): compare(_read(a), _read(b), _DIALECT[a], _DIALECT[b]).overall
        for a, b in combinations(_DIALECT, 2)
    }
    for pair, score in scores.items():
        assert score >= _SAME_FUNCTION_FLOOR, f"{pair} scored {score}"


def test_unrelated_scripts_stay_below_the_ceiling() -> None:
    fixtures = Path(__file__).parent.parent / "fixtures"
    pg_schema = (fixtures / "sql" / "pg_schema.sql").read_text()
    corpus_pg = (fixtures / "corpus" / "postgresql.sql").read_text()
    corpus_tsql = (fixtures / "corpus" / "tsql.sql").read_text()
    corpus_oracle = (fixtures / "corpus" / "oracle.sql").read_text()
    unrelated = [
        compare(_read("sqlserver"), pg_schema, "tsql", "postgresql").overall,
        compare(_read("mysql"), pg_schema, "mysql", "postgresql").overall,
        compare(_read("postgresql"), corpus_pg, "postgresql", "postgresql").overall,
        compare(corpus_tsql, corpus_oracle, "tsql", "oracle").overall,
    ]
    for score in unrelated:
        assert score <= _UNRELATED_CEILING, f"unrelated pair scored {score}"


def test_same_function_separates_from_unrelated() -> None:
    same = min(
        compare(_read(a), _read(b), _DIALECT[a], _DIALECT[b]).overall
        for a, b in combinations(_DIALECT, 2)
    )
    unrelated = compare(
        _read("sqlserver"),
        (
            Path(__file__).parent.parent / "fixtures" / "sql" / "pg_schema.sql"
        ).read_text(),
        "tsql",
        "postgresql",
    ).overall
    assert same > unrelated + 10.0


# ---------------------------------------------------------------------------
# Weight table: a dropped predicate costs more than a renamed alias
# ---------------------------------------------------------------------------


def test_dropping_a_where_costs_more_than_renaming_an_alias() -> None:
    base = "SELECT a, b FROM t WHERE x = 1 AND y = 2"
    dropped_where = "SELECT a, b FROM t"
    renamed_alias = "SELECT a AS z, b FROM t WHERE x = 1 AND y = 2"
    drop = compare(base, dropped_where, "postgresql", "postgresql")
    rename = compare(base, renamed_alias, "postgresql", "postgresql")
    assert drop.dimensions["tree_match"] < rename.dimensions["tree_match"]
    assert drop.overall < rename.overall
    # An alias rename is comparison-only noise: it stays near-perfect.
    assert rename.dimensions["tree_match"] > 85.0


# ---------------------------------------------------------------------------
# Alignment: reordering tolerated, extra statements count against
# ---------------------------------------------------------------------------


def test_statement_reordering_is_tolerated() -> None:
    a = "CREATE TABLE t (a INT); INSERT INTO t VALUES (1); SELECT a FROM t WHERE a > 0"
    b = "SELECT a FROM t WHERE a > 0; CREATE TABLE t (a INT); INSERT INTO t VALUES (1)"
    assert compare(a, b, "postgresql", "postgresql").overall > 90.0


def test_extra_unmatched_statement_lowers_the_score() -> None:
    base = "CREATE TABLE t (a INT); INSERT INTO t VALUES (1)"
    plus_one = base + "; DELETE FROM t WHERE a < 0"
    report = compare(base, plus_one, "postgresql", "postgresql")
    assert report.overall < 100.0
    assert report.unmatched_a + report.unmatched_b >= 1


def test_n_by_m_alignment_partial_overlap() -> None:
    a = "SELECT a FROM t1 WHERE a > 0; SELECT b FROM t2 WHERE b < 9"
    b = "SELECT a FROM t1 WHERE a > 0; DELETE FROM t3; UPDATE t4 SET c = 1 WHERE c > 0"
    report = compare(a, b, "postgresql", "postgresql")
    # One shared statement out of a 2-vs-3 script: neither 100 nor 0.
    assert 0.0 < report.overall < 90.0


# ---------------------------------------------------------------------------
# Degraded statements never score as matched
# ---------------------------------------------------------------------------


def test_degraded_statement_does_not_score_as_matched() -> None:
    # A T-SQL construct with no PostgreSQL equivalent degrades to a carrier on
    # the pivot; comparing it against a plain, clean statement must not match.
    degrading = "CREATE TABLE t (a INT); EXEC sp_addextendedproperty 'x', 'y'"
    clean = "CREATE TABLE t (a INT); SELECT a FROM t WHERE a > 0"
    report = compare(degrading, clean, "tsql", "postgresql")
    # The degraded unit is unmatched on at least one side.
    assert report.unmatched_a + report.unmatched_b >= 1
    assert report.overall < 100.0


# ---------------------------------------------------------------------------
# Edge semantics
# ---------------------------------------------------------------------------


def test_empty_vs_empty_is_100() -> None:
    assert compare("", "", "postgresql", "postgresql").overall == 100.0


def test_empty_vs_nonempty_is_0() -> None:
    assert compare("", "SELECT 1", "postgresql", "postgresql").overall == 0.0
    assert compare("SELECT 1", "   ", "postgresql", "postgresql").overall == 0.0


def test_auto_detect_records_detected_flag() -> None:
    report = compare(_read("sqlserver"), _read("sqlserver"))
    assert report.detected_a is True
    assert report.detected_b is True
    assert report.dialect_a == "tsql"


def test_undetectable_dialect_raises_naming_the_input() -> None:
    with pytest.raises(ValueError, match="input A"):
        compare("!!! not sql at all ???", "SELECT 1", None, "postgresql")


# ---------------------------------------------------------------------------
# Report shape and the re-export shim
# ---------------------------------------------------------------------------


def test_report_to_dict_schema_is_stable() -> None:
    report = compare("SELECT a FROM t", "SELECT a FROM t", "postgresql", "postgresql")
    payload = report.to_dict()
    assert set(payload) == {
        "overall",
        "dimensions",
        "dialect_a",
        "dialect_b",
        "detected_a",
        "detected_b",
        "statement_pairs",
        "unmatched_a",
        "unmatched_b",
        "warnings",
    }
    assert set(payload["dimensions"]) == {
        "tree_match",
        "dml_structure",
        "predicates",
        "control_flow",
    }
    assert isinstance(report, SimilarityReport)


def test_functional_equivalence_helper_reexports_fingerprint() -> None:
    from tests.helpers.functional_equivalence import (
        ProcedureFingerprint,
        assert_functionally_equivalent,
        fingerprint,
    )
    from unique.core import similarity

    assert fingerprint is similarity.fingerprint
    assert ProcedureFingerprint is similarity.ProcedureFingerprint
    assert assert_functionally_equivalent is similarity.assert_functionally_equivalent


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write(tmp_path: Path, name: str, sql: str) -> str:
    path = tmp_path / name
    path.write_text(sql, encoding="utf-8")
    return str(path)


def test_cli_compare_human_output(runner: CliRunner, tmp_path: Path) -> None:
    a = _write(tmp_path, "a.sql", "SELECT a FROM t WHERE a > 0")
    b = _write(tmp_path, "b.sql", "SELECT a FROM t WHERE a > 0")
    result = runner.invoke(
        cli, ["compare", a, b, "--dialect-a", "postgresql", "--dialect-b", "postgresql"]
    )
    assert result.exit_code == 0
    assert "Structural similarity: 100.0%" in result.output
    assert "not a probability" in result.output


def test_cli_compare_json_schema(runner: CliRunner, tmp_path: Path) -> None:
    a = _write(tmp_path, "a.sql", "SELECT a, b FROM t WHERE x = 1")
    b = _write(tmp_path, "b.sql", "SELECT a FROM t")
    result = runner.invoke(
        cli,
        [
            "compare",
            a,
            b,
            "--dialect-a",
            "postgresql",
            "--dialect-b",
            "postgresql",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["file_a"] == a and payload["file_b"] == b
    assert 0.0 < payload["overall"] < 100.0
    assert set(payload["dimensions"]) == {
        "tree_match",
        "dml_structure",
        "predicates",
        "control_flow",
    }


def test_cli_compare_auto_detect_echo(runner: CliRunner, tmp_path: Path) -> None:
    a = _write(tmp_path, "a.sql", "SELECT TOP 1 * FROM t WHERE @@ROWCOUNT > 0")
    b = _write(tmp_path, "b.sql", "SELECT TOP 1 * FROM t WHERE @@ROWCOUNT > 0")
    result = runner.invoke(cli, ["compare", a, b])
    assert result.exit_code == 0
    assert "auto-detected" in result.output
    assert "tsql" in result.output


def test_cli_parse_failure_exit_code_distinct_from_low_similarity(
    runner: CliRunner, tmp_path: Path
) -> None:
    a = _write(tmp_path, "a.sql", "%%% not sql %%%")
    b = _write(tmp_path, "b.sql", "SELECT 1")
    result = runner.invoke(cli, ["compare", a, b, "--dialect-b", "postgresql"])
    # Undetectable dialect -> exit 2 (distinct from a successful low-score run).
    assert result.exit_code == 2
    assert "Error" in result.output
