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

"""Regression tests over the anonymized procedural fixtures.

These fixtures (tests/fixtures/procedures/, see SOURCES.md) cover the
stored-procedure surface — variables, cursors, control flow, dynamic SQL and
batch separators — that the schema-only fixtures don't. The checks here are
parsing/transpilation guards; execution against real engines happens in the
live CI job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from unique.core.batch_splitter import BatchSplitter
from unique.core.transpiler import Transpiler

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "procedures"

_FIXTURES = [
    ("procedures_sqlserver.sql", "tsql"),
    ("procedures_oracle.sql", "oracle"),
]

# Domain terms that must never appear (anonymization guard).
_FORBIDDEN = re.compile(
    r"(?i)\b(svp_|svf_|svk_|salastel|citas|telemed|paciente|encuesta|"
    r"idsalastel|usuariomod|fechamod)",
)


@pytest.fixture
def transpiler() -> Transpiler:
    return Transpiler()


@pytest.mark.parametrize("filename,dialect", _FIXTURES)
def test_fixture_exists_and_nonempty(filename: str, dialect: str) -> None:
    path = FIXTURE_DIR / filename
    assert path.is_file(), f"missing fixture {filename}"
    assert path.stat().st_size > 1000


@pytest.mark.parametrize("filename,dialect", _FIXTURES)
def test_fixture_is_anonymized(filename: str, dialect: str) -> None:
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
    leak = _FORBIDDEN.search(text)
    assert leak is None, f"domain term leaked in {filename}: {leak!r}"


@pytest.mark.parametrize("filename,dialect", _FIXTURES)
def test_fixture_splits_into_batches(filename: str, dialect: str) -> None:
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
    batches = BatchSplitter.split(text, dialect)
    # Both fixtures contain dozens of statements/batches.
    assert len(batches) > 20


@pytest.mark.parametrize("filename,dialect", _FIXTURES)
def test_fixture_has_procedures(filename: str, dialect: str) -> None:
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8").upper()
    assert "PROCEDURE" in text
    assert "FUNC1" in text  # the renamed function stubs are present


@pytest.mark.parametrize("filename,source", _FIXTURES)
@pytest.mark.parametrize("target", ["tsql", "oracle", "postgresql", "mysql"])
def test_fixture_transpiles_without_crashing(
    transpiler: Transpiler, filename: str, source: str, target: str
) -> None:
    if source == target:
        pytest.skip("no transpilation needed")
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
    result = transpiler.transpile(text, source, target)
    # Must produce substantial output and never leak domain terms.
    assert len(result.sql) > 500
    assert _FORBIDDEN.search(result.sql) is None
