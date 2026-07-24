# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

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
    ("procedures_mysql.sql", "mysql"),
    ("procedures_postgresql.sql", "postgresql"),
]

# Domain terms that must never appear (anonymization guard). The term list is
# itself confidential, so it lives OUTSIDE the repo in the untracked
# fixtures-private/ directory (one regex fragment per line, "#" comments
# allowed); when the private corpus is absent there is nothing to guard, so
# the check skips (audit 2026-07-24 B3/F8).
_FRAGMENTS_FILE = (
    Path(__file__).parent.parent.parent / "fixtures-private" / "leak_fragments.txt"
)


def _forbidden_pattern() -> re.Pattern[str] | None:
    if not _FRAGMENTS_FILE.is_file():
        return None
    fragments = [
        line.strip()
        for line in _FRAGMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not fragments:
        return None
    return re.compile(r"(?i)\b(" + "|".join(fragments) + ")")


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
    pattern = _forbidden_pattern()
    if pattern is None:
        pytest.skip("private fragment list not available (fixtures-private/)")
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
    leak = pattern.search(text)
    assert leak is None, f"domain term leaked in {filename}: {leak!r}"


@pytest.mark.parametrize("filename,dialect", _FIXTURES)
def test_fixture_splits_into_batches(filename: str, dialect: str) -> None:
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
    batches = BatchSplitter.split(text, dialect)
    # Every fixture contains many statements/batches. PostgreSQL groups each
    # dollar-quoted routine body into a single batch, so it yields fewer than
    # the others; a lower floor still confirms the splitter is working.
    floor = 15 if dialect == "postgresql" else 20
    assert len(batches) > floor


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
    pattern = _forbidden_pattern()
    if pattern is not None:
        assert pattern.search(result.sql) is None


# Constructs that must never appear as *executable* MySQL in the committed
# fixture (they may still appear inside a /* UNIQUE: ... */ comment, which is
# how a preserved original type is documented).
_MYSQL_NON_PORTABLE = re.compile(
    r"(?i)\b(NEWSEQUENTIALID|HASHBYTES|STRING_SPLIT)\b"
    r"|CHAR\(MAX\)|VARCHAR\(MAX\)|WITH\s*\(\s*NOLOCK"
)


def _strip_comments(sql: str) -> str:
    no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", no_block)


def test_mysql_fixture_has_no_executable_non_portable_constructs() -> None:
    text = (FIXTURE_DIR / "procedures_mysql.sql").read_text(encoding="utf-8")
    code = _strip_comments(text)
    leak = _MYSQL_NON_PORTABLE.search(code)
    assert leak is None, f"non-portable construct in MySQL fixture: {leak!r}"
    # dbo schema must not survive in executable code either.
    assert not re.search(r"(?i)\bdbo\s*\.", code), "dbo. left in MySQL fixture"


def test_mysql_fixture_wraps_routines_in_delimiter() -> None:
    text = (FIXTURE_DIR / "procedures_mysql.sql").read_text(encoding="utf-8")
    # Every routine body is wrapped; openers and closers must balance.
    assert text.count("DELIMITER $$") == text.count("DELIMITER ;")
    assert text.count("DELIMITER $$") == text.count("END$$")
    assert text.count("DELIMITER $$") > 20


# Constructs that must never appear as executable PostgreSQL in the committed
# fixture (they may still appear inside a /* UNIQUE: ... */ comment).
_PG_NON_PORTABLE = re.compile(
    r"(?i)\b(NVARCHAR|UNIQUEIDENTIFIER|SQL_VARIANT|NEWSEQUENTIALID|HASHBYTES)\b"
    r"|\bdbo\s*\.|RETURNING\s+(?:inserted|deleted)\b|DECLARE\s+@"
)


def test_pg_fixture_has_no_executable_non_portable_constructs() -> None:
    text = (FIXTURE_DIR / "procedures_postgresql.sql").read_text(encoding="utf-8")
    code = _strip_comments(text)
    leak = _PG_NON_PORTABLE.search(code)
    assert leak is None, f"non-portable construct in PG fixture: {leak!r}"


def test_pg_fixture_uses_plpgsql() -> None:
    text = (FIXTURE_DIR / "procedures_postgresql.sql").read_text(encoding="utf-8")
    # Routines are PL/pgSQL with dollar-quoted bodies.
    assert "LANGUAGE plpgsql" in text
    assert text.count("AS $$") == text.count("$$;")
    assert text.count("LANGUAGE plpgsql") > 20
