# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""D5 (`RENAME COLUMN` → T-SQL `sp_rename`) and B2 (`DROP INDEX` per target).

Real-dump findings (audit 2026-07-08 sweep): `ALTER TABLE … RENAME COLUMN`
passed through to T-SQL verbatim (T-SQL has no such clause — it renames via
`sp_rename`), and `DROP INDEX` shipped without the table name T-SQL/MySQL
require (24 + 23 statements on the T-SQL direction).
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str):
    return Transpiler().transpile(sql, source=source, target=target)


# ---------------------------------------------------------------------------
# D5 — RENAME COLUMN
# ---------------------------------------------------------------------------


def test_rename_column_becomes_sp_rename_on_tsql() -> None:
    r = _t("ALTER TABLE t1 RENAME COLUMN old_c TO new_c;", "oracle", "tsql")
    up = " ".join(r.sql.split())
    assert re.search(
        r"(?i)EXEC\s+sp_rename\s+'t1\.old_c'\s*,\s*'new_c'\s*,\s*'COLUMN'", up
    ), r.sql
    assert "RENAME COLUMN" not in up.upper()


@pytest.mark.parametrize("target", ["postgresql", "mysql"])
def test_rename_column_stays_native_elsewhere(target: str) -> None:
    r = _t("ALTER TABLE t1 RENAME COLUMN old_c TO new_c;", "oracle", target)
    assert "RENAME COLUMN" in r.sql.upper()
    assert "UNIQUE:" not in r.sql


# ---------------------------------------------------------------------------
# B2 — DROP INDEX
# ---------------------------------------------------------------------------


def test_tsql_drop_index_on_form_keeps_table_for_mysql() -> None:
    r = _t("DROP INDEX ix_c1 ON t1;", "tsql", "mysql")
    up = " ".join(r.sql.split()).upper()
    assert re.search(r"DROP INDEX\s+\S*IX_C1\S*\s+ON\s+\S*T1", up), r.sql


def test_tsql_drop_index_on_form_round_trips_to_tsql() -> None:
    # tsql → pg drops the ON (PG index names are schema-global) …
    pg = _t("DROP INDEX ix_c1 ON t1;", "tsql", "postgresql")
    up = " ".join(pg.sql.split()).upper()
    assert "ON T1" not in up and "IX_C1" in up, pg.sql


@pytest.mark.parametrize("target", ["tsql", "mysql"])
def test_drop_index_without_table_never_ships_invalid(target: str) -> None:
    # Oracle's DROP INDEX carries no table; T-SQL and MySQL REQUIRE one.
    # Without it the statement must degrade honestly, never ship broken.
    r = _t("DROP INDEX ix_c1;", "oracle", target)
    executable = [
        ln
        for ln in r.sql.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ]
    assert not any("DROP INDEX" in ln.upper() for ln in executable), r.sql
    assert r.warnings or r.unsupported


def test_legacy_tsql_two_part_drop_index() -> None:
    # Legacy T-SQL spelling: DROP INDEX table.index — table travels in the
    # qualifier. MySQL needs it back as ON <table>.
    r = _t("DROP INDEX t1.ix_c1;", "tsql", "mysql")
    up = " ".join(r.sql.split()).upper()
    assert re.search(r"DROP INDEX\s+\S*IX_C1\S*\s+ON\s+\S*T1", up), r.sql
