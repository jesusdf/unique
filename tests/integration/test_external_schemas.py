"""Real-world schema validity against the vendored MediaWiki 1.46 schemas.

The schema files live under ``tests/fixtures/real_world/mediawiki/`` (see that
directory's ``SOURCES.md`` for provenance and the GPL-2.0+ attribution). Each is
the MediaWiki core schema for one engine — 64 CREATE TABLEs exercising
AUTO_INCREMENT/AUTOINCREMENT, UNSIGNED, VARBINARY/BLOB, integer-affinity columns,
inline unique/plain indexes and composite keys — transpiled to every *other*
target and checked for validity in that dialect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.validity import assert_statements_parse
from unique.core.transpiler import Transpiler

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "real_world" / "mediawiki"

# (fixture file, its source dialect). SQLite is added once import support lands.
_SCHEMAS = [
    ("mysql-tables.sql", "mysql"),
    ("postgres-tables.sql", "postgresql"),
]
_TARGETS = ["tsql", "oracle", "postgresql", "mysql"]


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# Known real limitation: the MediaWiki *PostgreSQL* schema declares
# ``CREATE TYPE … AS ENUM`` and types a column with it; that has no faithful
# MySQL form (MySQL's ENUM is an inline column type, not a named type), so the
# enum-typed column can't be rebuilt. Documented, not a regression.
_KNOWN_GAPS = {("postgresql", "mysql")}


@pytest.mark.parametrize("fixture,source", _SCHEMAS)
@pytest.mark.parametrize("target", _TARGETS)
def test_mediawiki_schema_transpiles_valid(
    fixture: str, source: str, target: str
) -> None:
    if source == target:
        pytest.skip("same-dialect pass is a no-op")
    if (source, target) in _KNOWN_GAPS:
        pytest.skip(f"{source}->{target}: named-ENUM type has no faithful form")
    result = Transpiler().transpile(_load(fixture), source=source, target=target)
    # Every transpiled statement must parse in the target dialect.
    assert_statements_parse(result.sql, target, context=f"mediawiki {source}->{target}")


@pytest.mark.parametrize("fixture,source", _SCHEMAS)
def test_mediawiki_schema_all_tables_survive(fixture: str, source: str) -> None:
    # Transpiling to another server engine must preserve every CREATE TABLE.
    schema = _load(fixture)
    n_tables = schema.upper().count("CREATE TABLE")
    for target in _TARGETS:
        if target == source:
            continue
        out = Transpiler().transpile(schema, source=source, target=target).sql
        assert out.upper().count("CREATE TABLE") == n_tables, f"{source}->{target}"
