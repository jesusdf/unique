# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Transpilation tests over real-world public sample schemas.

These exercise the full pipeline against substantial, real databases
(see tests/fixtures/real_world/SOURCES.md). They are regression guards:
the goal is that transpilation of a real schema never crashes, always
produces non-empty output, and preserves the bulk of the structural
statements (e.g. CREATE TABLE counts) across every dialect pair.

The structural classes are intentionally lenient about exact output —
dialect-specific rewrites and unsupported constructs are expected — but
strict about not losing or corrupting whole statements.
``TestOutputValidity`` adds the hardened gates (audit doc 02): every
non-procedural transpiled statement must parse in the target dialect, no
source-only quoting/separators may leak, and each fixture's signature
construct must arrive in the target idiom.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import pytest
from helpers.invariants import (
    assert_carrier_bodies_parse_as_source,
    assert_no_silent_loss,
    jaccard_similarity,
)
from helpers.validity import assert_statements_parse, executable_body

from unique.core.batch_splitter import BatchSplitter, BatchType
from unique.core.transpiler import TranspileResult, transpile

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "real_world"

# (filename, source dialect, expected CREATE TABLE count in the source)
FIXTURES = [
    ("adventureworks_lt_sqlserver.sql", "tsql", 10),
    ("hr_create_oracle.sql", "oracle", 7),
    ("sakila_schema_mysql.sql", "mysql", 16),
    ("northwind_postgresql.sql", "postgresql", 14),
]

ALL_DIALECTS = ("tsql", "oracle", "postgresql", "mysql")


def _load(filename: str) -> str:
    path = FIXTURE_DIR / filename
    if not path.exists():
        pytest.skip(f"fixture missing: {filename}")
    return path.read_text(encoding="utf-8", errors="replace")


@cache
def _transpiled(filename: str, source: str, target: str) -> TranspileResult:
    """Transpile a fixture once per (file, source, target), shared across tests.

    The forward direction of each pair is asserted by ~7 different test methods
    (crash/output/table-count/no-silent-loss/parse/quoting/signature) and the
    real-world corpora are large, so re-transpiling per method dominated the
    suite runtime. Caching collapses it to one transpile per pair. (Transpiling
    is a pure function of the inputs and the results are only read, so sharing is
    safe. The performance-budget test deliberately calls ``transpile`` directly.)
    """
    return transpile(_load(filename), source, target)


@cache
def _round_tripped(filename: str, source: str, via: str) -> tuple[str, str]:
    """A -> via -> A round-trip SQL (forward, back), cached — both round-trip
    test classes re-run identical legs."""
    forward = _transpiled(filename, source, via).sql
    back = transpile(forward, via, source).sql
    return forward, back


def _count_create_table(sql: str) -> int:
    return len(re.findall(r"(?i)\bCREATE\s+TABLE\b", sql))


# All 12 directional pairs (source fixture × 3 other targets).
PAIRS = [
    (filename, src, tgt, n_tables)
    for (filename, src, n_tables) in FIXTURES
    for tgt in ALL_DIALECTS
    if tgt != src
]


@pytest.mark.parametrize(
    "filename,source,target,n_tables",
    PAIRS,
    ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
)
class TestRealWorldTranspilation:
    def test_does_not_crash_and_outputs(
        self, filename: str, source: str, target: str, n_tables: int
    ) -> None:
        result = _transpiled(filename, source, target)
        assert result.sql is not None
        assert result.sql.strip()

    def test_output_is_substantial(
        self, filename: str, source: str, target: str, n_tables: int
    ) -> None:
        # Output should be on the same order of magnitude as the input,
        # never a near-empty collapse (which would indicate a parser/
        # emitter swallowing the script).
        sql = _load(filename)
        result = _transpiled(filename, source, target)
        assert len(result.sql) > len(sql) * 0.3

    def test_create_table_count_preserved(
        self, filename: str, source: str, target: str, n_tables: int
    ) -> None:
        # The transpiler must not drop table definitions. Allow a small
        # tolerance for dialect rewrites that fold or comment a table, but
        # the vast majority must survive.
        result = _transpiled(filename, source, target)
        out_tables = _count_create_table(result.sql)
        assert out_tables >= max(1, int(n_tables * 0.8))


class TestRealWorldBatchSplitting:
    """The splitter must segment each real schema into many batches."""

    @pytest.mark.parametrize(
        "filename,source,n_tables",
        [(f, s, n) for (f, s, n) in FIXTURES],
        ids=[s for (_, s, _) in FIXTURES],
    )
    def test_splits_into_many_batches(
        self, filename: str, source: str, n_tables: int
    ) -> None:
        sql = _load(filename)
        batches = [b for b in BatchSplitter.split(sql, source) if not b.is_empty]
        # At least one batch per table (real schemas have far more).
        assert len(batches) >= n_tables

    @pytest.mark.parametrize(
        "filename,source,n_tables",
        [(f, s, n) for (f, s, n) in FIXTURES],
        ids=[s for (_, s, _) in FIXTURES],
    )
    def test_has_ddl_batches(self, filename: str, source: str, n_tables: int) -> None:
        sql = _load(filename)
        batches = BatchSplitter.split(sql, source)
        ddl = [b for b in batches if b.batch_type == BatchType.DDL]
        assert len(ddl) >= 1


class TestRealWorldSpecific:
    """Targeted checks on individual fixtures."""

    def test_adventureworks_has_procedures(self) -> None:
        sql = _load("adventureworks_lt_sqlserver.sql")
        batches = BatchSplitter.split(sql, "tsql")
        proc = [b for b in batches if b.batch_type == BatchType.PROCEDURAL]
        assert len(proc) >= 1

    def test_sakila_has_procedures(self) -> None:
        sql = _load("sakila_schema_mysql.sql")
        batches = BatchSplitter.split(sql, "mysql")
        proc = [b for b in batches if b.batch_type == BatchType.PROCEDURAL]
        assert len(proc) >= 1

    def test_oracle_hr_splits_without_slash(self) -> None:
        # The HR schema uses ';' terminators and no '/'; the splitter must
        # still produce many batches (regression for the slash-only bug).
        sql = _load("hr_create_oracle.sql")
        batches = [b for b in BatchSplitter.split(sql, "oracle") if not b.is_empty]
        assert len(batches) >= 20

    def test_oracle_hr_rem_prompt_preserved_as_comments(self) -> None:
        # 'rem' (copyright) and 'prompt' (progress) directives should survive
        # transpilation as SQL comments, not be dropped.
        sql = _load("hr_create_oracle.sql")
        result = transpile(sql, "oracle", "tsql")
        comments = [
            line for line in result.sql.split("\n") if line.strip().startswith("--")
        ]
        assert any("Copyright" in c for c in comments)
        assert any("PROMPT:" in c for c in comments)

    def test_northwind_to_tsql_keeps_tables(self) -> None:
        sql = _load("northwind_postgresql.sql")
        result = transpile(sql, "postgresql", "tsql")
        assert _count_create_table(result.sql) >= 10

    def test_adventureworks_system_procs_become_comments(self) -> None:
        # EXEC sp_addextendedproperty (and other sp_* system procedures) have
        # no cross-dialect equivalent and must be emitted as comments rather
        # than raising sqlglot errors.
        sql = _load("adventureworks_lt_sqlserver.sql")
        result = transpile(sql, "tsql", "oracle")
        assert "TRANSPILATION ERROR" not in result.sql
        assert any("System procedure" in u for u in result.unsupported)


class TestRoundTripPreservation:
    """A -> B -> A round-trips must not lose table definitions."""

    @pytest.mark.parametrize(
        "filename,source,n_tables",
        [(f, s, n) for (f, s, n) in FIXTURES],
        ids=[s for (_, s, _) in FIXTURES],
    )
    @pytest.mark.parametrize("via", ["tsql", "oracle", "postgresql", "mysql"])
    def test_table_count_survives_round_trip(
        self, filename: str, source: str, via: str, n_tables: int
    ) -> None:
        if via == source:
            pytest.skip("round-trip via the same dialect is trivial")
        _forward, back = _round_tripped(filename, source, via)
        # Most table definitions must survive the round-trip. The threshold is
        # lenient (50%) because schemas with heavy engine-specific DDL (e.g.
        # AdventureWorks index WITH (PAD_INDEX = ...) options) lose some
        # statements to commented passthrough on the intermediate hop.
        assert _count_create_table(back) >= max(1, int(n_tables * 0.5))


class TestPerformance:
    """Lightweight performance-regression guard (generous thresholds).

    The transpiler's cost is dominated by sqlglot parsing and is proportional
    to the number of statements; these bounds are loose to avoid CI flakiness
    while still catching gross regressions (e.g. accidental re-parsing).
    """

    @pytest.mark.parametrize(
        "filename,source,budget_s",
        [
            ("hr_create_oracle.sql", "oracle", 2.0),
            ("sakila_schema_mysql.sql", "mysql", 2.0),
            ("adventureworks_lt_sqlserver.sql", "tsql", 4.0),
            # 12.0: measured baseline ~5-8s CPU; under an 8-way parallel
            # suite cache contention still inflated CPU past a 10.0 budget
            # once (10.4s) — the margin keeps the regression signal without
            # the flake.
            ("northwind_postgresql.sql", "postgresql", 12.0),
        ],
    )
    def test_transpile_within_budget(
        self, filename: str, source: str, budget_s: float
    ) -> None:
        import time

        sql = _load(filename)
        target = "tsql" if source != "tsql" else "postgresql"
        # CPU time, not wall clock: the transpile is single-threaded pure
        # CPU, so process_time keeps the regression signal while staying
        # stable under parallel-suite/machine load — the wall-clock version
        # flaked on every loaded run (audit 2026-07-24 B25).
        start = time.process_time()
        transpile(sql, source, target)
        elapsed = time.process_time() - start
        assert elapsed < budget_s, (
            f"{filename} took {elapsed:.2f}s CPU (budget {budget_s}s) — "
            "possible performance regression"
        )


class TestGenericInvariants:
    """Dialect-agnostic sanity checks (see tests/helpers/invariants.py).

    Two content-based validations that catch broad classes of bugs without
    per-construct assertions: (1) structural elements are not dropped without
    a documented ``-- UNIQUE:`` note, and (2) an A->B->A round-trip preserves
    most of the original content (token-set similarity).
    """

    # Round-trip similarity floors, calibrated per *source* dialect. PostgreSQL
    # is sqlglot's base dialect and round-trips almost perfectly; Oracle/T-SQL
    # fixtures carry heavy proprietary DDL (PL/SQL, sp_addextendedproperty,
    # XML schemas) that is legitimately turned into comments, so their floors
    # are lower. These guard against *regressions*, not perfection.
    # The Oracle floor was recalibrated (0.35 -> 0.25) when degraded
    # passthroughs started commenting *every* line: the raw lines that used
    # to leak into the output inflated the old similarity (jaccard ignores
    # comments). Honest post-fix values are 0.27-0.31.
    _RT_FLOOR = {
        "postgresql": 0.90,
        "mysql": 0.45,
        "oracle": 0.25,
        # 0.30 until 2026-07-17: the XQuery-prolog view (vProductModel
        # CatalogDescription) used to round-trip as SILENTLY SHREDDED fake
        # declares (DECLARE @= http://…;) that happened to score higher on
        # raw token overlap; the parser now fails that unit into an honest
        # whole-unit carrier (unrepresentable-token guard), which comments
        # the text and costs similarity. Honesty outranks the metric.
        "tsql": 0.23,
    }

    @pytest.mark.parametrize(
        "filename,source,target,_n",
        PAIRS,
        ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
    )
    def test_carrier_bodies_parse_as_source(
        self, filename: str, source: str, target: str, _n: int
    ) -> None:
        """Every "preserved as a comment" carrier quotes real SOURCE SQL.

        A body that does not parse in the source dialect is a mid-transform
        hybrid, not a preserved statement (audit 2026-07-24 N12).
        """
        out = _transpiled(filename, source, target).sql
        assert_carrier_bodies_parse_as_source(out, source)

    @pytest.mark.parametrize(
        "filename,source,target,_n",
        PAIRS,
        ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
    )
    def test_no_silent_ddl_loss(
        self, filename: str, source: str, target: str, _n: int
    ) -> None:
        sql = _load(filename)
        out = _transpiled(filename, source, target).sql
        # Tables and key constraints must survive or be explicitly documented.
        violations = assert_no_silent_loss(
            sql,
            out,
            keywords=("CREATE TABLE", "PRIMARY KEY", "FOREIGN KEY"),
            tolerance=0.20,
        )
        assert not violations, "Silent DDL loss detected:\n" + "\n".join(violations)

    @pytest.mark.parametrize(
        "filename,source",
        [(f, s) for (f, s, _) in FIXTURES],
        ids=[s for (_, s, _) in FIXTURES],
    )
    @pytest.mark.parametrize("via", ALL_DIALECTS)
    def test_round_trip_content_similarity(
        self, filename: str, source: str, via: str
    ) -> None:
        if via == source:
            pytest.skip("round-trip via same dialect is trivial")
        sql = _load(filename)
        _forward, back = _round_tripped(filename, source, via)
        sim = jaccard_similarity(sql, back)
        floor = self._RT_FLOOR[source]
        assert sim >= floor, (
            f"{source} -> {via} -> {source} similarity {sim:.2f} "
            f"below floor {floor} (possible new information loss)"
        )


class TestOutputValidity:
    """Hardened output gates (audit doc 02, test_real_world hardening).

    Unlike the lenient structural checks above, these fail under an identity
    (no-op) transpiler: every non-procedural transpiled statement must parse
    in the *target* dialect, no source-only identifier quoting or batch
    separators may leak into executable output, and each fixture's signature
    construct must arrive in the target's own idiom.
    """

    @pytest.mark.parametrize(
        "filename,source,target,_n",
        PAIRS,
        ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
    )
    def test_statements_parse_in_target_dialect(
        self, filename: str, source: str, target: str, _n: int
    ) -> None:
        out = _transpiled(filename, source, target).sql
        assert_statements_parse(out, target, context=f"{source}->{target}")

    @pytest.mark.parametrize(
        "filename,source,target,_n",
        PAIRS,
        ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
    )
    def test_no_foreign_quoting_or_separators(
        self, filename: str, source: str, target: str, _n: int
    ) -> None:
        out = _transpiled(filename, source, target).sql
        body = executable_body(out)
        if target != "tsql":
            leaked = [
                line
                for line in body.splitlines()
                if re.search(r"\[[A-Za-z_][\w ]*\]", line)
            ]
            assert not leaked, f"bracket identifiers leaked: {leaked[:3]}"
            assert not re.search(r"(?m)^\s*GO\s*;?\s*$", body), "GO separator leaked"
        if target != "mysql":
            leaked = [line for line in body.splitlines() if "`" in line]
            assert not leaked, f"backtick identifiers leaked: {leaked[:3]}"

    # Signature construct of each fixture, per target: the idiom that MUST
    # appear (in executable output) and the source-only spelling that must
    # be gone. An identity transpiler fails every row.
    _IDIOMS: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
        # AdventureWorksLT: IDENTITY(1,1) columns.
        ("tsql", "postgresql"): (("SERIAL",), ("IDENTITY(1,1)",)),
        ("tsql", "mysql"): (("AUTO_INCREMENT",), ("IDENTITY(1,1)",)),
        ("tsql", "oracle"): (
            ("GENERATED BY DEFAULT AS IDENTITY",),
            ("IDENTITY(1,1)",),
        ),
        # HR: VARCHAR2 columns.
        ("oracle", "tsql"): ((), ("VARCHAR2",)),
        ("oracle", "postgresql"): ((), ("VARCHAR2",)),
        ("oracle", "mysql"): ((), ("VARCHAR2",)),
        # sakila: AUTO_INCREMENT columns and ENGINE= table options.
        ("mysql", "tsql"): (("IDENTITY(1,1)",), ("AUTO_INCREMENT", "ENGINE=")),
        ("mysql", "postgresql"): (("SERIAL",), ("AUTO_INCREMENT", "ENGINE=")),
        ("mysql", "oracle"): (
            ("GENERATED BY DEFAULT AS IDENTITY",),
            ("AUTO_INCREMENT", "ENGINE="),
        ),
        # northwind: "character varying" columns; T-SQL output gains GO.
        ("postgresql", "tsql"): ((), ("CHARACTER VARYING",)),
        ("postgresql", "oracle"): (("VARCHAR2",), ("CHARACTER VARYING",)),
        ("postgresql", "mysql"): (("VARCHAR(",), ("CHARACTER VARYING",)),
    }

    @pytest.mark.parametrize(
        "filename,source,target,_n",
        PAIRS,
        ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
    )
    def test_signature_construct_translated(
        self, filename: str, source: str, target: str, _n: int
    ) -> None:
        out = _transpiled(filename, source, target).sql
        body = executable_body(out).upper()
        present, absent = self._IDIOMS[(source, target)]
        for needle in present:
            assert needle.upper() in body, f"expected {needle!r} in output"
        for needle in absent:
            assert needle.upper() not in body, f"source idiom {needle!r} survived"
        if source == "postgresql" and target == "tsql":
            # The T-SQL emitter separates batches with GO; raw PostgreSQL
            # input has none, so this alone kills an identity transpiler.
            assert re.search(r"(?m)^GO\b", body), "expected GO batch separators"
