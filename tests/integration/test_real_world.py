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

    def test_northwind_to_tsql_keeps_tables(self) -> None:
        sql = _load("northwind_postgresql.sql")
        result = transpile(sql, "postgresql", "tsql")
        assert _count_create_table(result.sql) >= 10
