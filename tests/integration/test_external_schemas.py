"""Real-world schema validation against externally-hosted databases.

These tests transpile a genuine, complex production schema and assert the output
is valid in every target dialect. The schema is **not vendored** — this project
is MIT-licensed and MediaWiki is GPL-2.0-or-later — so it is fetched on demand
from the official release and the tests are **opt-in**: they run only when
``UNIQUE_EXTERNAL_FIXTURES`` is set (network access + external source), and skip
cleanly when offline.

Run with::

    UNIQUE_EXTERNAL_FIXTURES=1 pytest tests/integration/test_external_schemas.py
"""

from __future__ import annotations

import os
import urllib.request

import pytest

from tests.helpers.validity import assert_statements_parse
from unique.core.transpiler import Transpiler

pytestmark = pytest.mark.skipif(
    not os.environ.get("UNIQUE_EXTERNAL_FIXTURES"),
    reason="external-fixture tests are opt-in (set UNIQUE_EXTERNAL_FIXTURES=1)",
)

# MediaWiki 1.46 core schema, generated from sql/tables.json (MySQL flavour is
# the canonical source). 64 CREATE TABLEs exercising AUTO_INCREMENT, UNSIGNED,
# VARBINARY/BINARY, inline UNIQUE/plain indexes, and composite keys.
_MEDIAWIKI_SCHEMA_URL = (
    "https://raw.githubusercontent.com/wikimedia/mediawiki/"
    "1.46.0/sql/mysql/tables-generated.sql"
)

_schema_cache: str | None = None


def _mediawiki_schema() -> str:
    global _schema_cache
    if _schema_cache is None:
        try:
            with urllib.request.urlopen(_MEDIAWIKI_SCHEMA_URL, timeout=30) as resp:
                _schema_cache = resp.read().decode("utf-8")
        except OSError as exc:  # network unavailable / source moved
            pytest.skip(f"could not fetch MediaWiki schema: {exc}")
    return _schema_cache


@pytest.mark.parametrize("target", ["postgresql", "oracle", "tsql"])
def test_mediawiki_schema_transpiles_valid(target: str) -> None:
    schema = _mediawiki_schema()
    result = Transpiler().transpile(schema, source="mysql", target=target)
    # Every transpiled statement must parse in the target dialect.
    assert_statements_parse(result.sql, target, context=f"mediawiki mysql->{target}")


@pytest.mark.parametrize("target", ["postgresql", "oracle", "tsql"])
def test_mediawiki_schema_has_no_carriers(target: str) -> None:
    # The MediaWiki core schema is plain DDL with a cross-engine form on every
    # target; a UNIQUE carrier here would flag a real translation regression.
    schema = _mediawiki_schema()
    result = Transpiler().transpile(schema, source="mysql", target=target)
    assert "UNIQUE:" not in result.sql, f"unexpected carrier for mysql->{target}"
    assert "TRANSPILATION ERROR" not in result.sql
