# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Transpilation tests over real-world public sample schemas.

These exercise the full pipeline against substantial, real databases
(see tests/fixtures/real_world/SOURCES.md). They are regression guards:
the goal is that transpilation of a real schema never crashes, always
produces non-empty output, and preserves the bulk of the structural
statements (e.g. CREATE TABLE counts) across every dialect pair.

They are intentionally lenient about exact output — dialect-specific
rewrites and unsupported constructs are expected — but strict about not
losing or corrupting whole statements.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from helpers.invariants import assert_no_silent_loss, jaccard_similarity

from unique.core.batch_splitter import BatchSplitter, BatchType
from unique.core.transpiler import transpile

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
        sql = _load(filename)
        result = transpile(sql, source, target)
        assert result.sql is not None
        assert result.sql.strip()

    def test_output_is_substantial(
        self, filename: str, source: str, target: str, n_tables: int
    ) -> None:
        # Output should be on the same order of magnitude as the input,
        # never a near-empty collapse (which would indicate a parser/
        # emitter swallowing the script).
        sql = _load(filename)
        result = transpile(sql, source, target)
        assert len(result.sql) > len(sql) * 0.3

    def test_create_table_count_preserved(
        self, filename: str, source: str, target: str, n_tables: int
    ) -> None:
        # The transpiler must not drop table definitions. Allow a small
        # tolerance for dialect rewrites that fold or comment a table, but
        # the vast majority must survive.
        sql = _load(filename)
        result = transpile(sql, source, target)
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
        sql = _load(filename)
        forward = transpile(sql, source, via).sql
        back = transpile(forward, via, source).sql
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
            ("northwind_postgresql.sql", "postgresql", 10.0),
        ],
    )
    def test_transpile_within_budget(
        self, filename: str, source: str, budget_s: float
    ) -> None:
        import time

        sql = _load(filename)
        target = "tsql" if source != "tsql" else "postgresql"
        start = time.perf_counter()
        transpile(sql, source, target)
        elapsed = time.perf_counter() - start
        assert elapsed < budget_s, (
            f"{filename} took {elapsed:.2f}s (budget {budget_s}s) — "
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
    _RT_FLOOR = {
        "postgresql": 0.90,
        "mysql": 0.45,
        "oracle": 0.35,
        "tsql": 0.30,
    }

    @pytest.mark.parametrize(
        "filename,source,target,_n",
        PAIRS,
        ids=[f"{src}->{tgt}" for (_, src, tgt, _) in PAIRS],
    )
    def test_no_silent_ddl_loss(
        self, filename: str, source: str, target: str, _n: int
    ) -> None:
        sql = _load(filename)
        out = transpile(sql, source, target).sql
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
        forward = transpile(sql, source, via).sql
        back = transpile(forward, via, source).sql
        sim = jaccard_similarity(sql, back)
        floor = self._RT_FLOOR[source]
        assert sim >= floor, (
            f"{source} -> {via} -> {source} similarity {sim:.2f} "
            f"below floor {floor} (possible new information loss)"
        )
