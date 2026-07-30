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
    assert "UNIQUE-" not in r.sql


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


# ---------------------------------------------------------------------------
# TO_CHAR single-arg + MERGE terminator (real-dump classes, 14x + 11x)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("tsql", r"(?i)CONVERT\s*\(\s*VARCHAR"),
        ("postgresql", r"(?i)CAST\s*\(\s*c2\s+AS\s+TEXT\s*\)"),
        ("mysql", r"(?i)CAST\s*\(\s*c2\s+AS\s+CHAR\s*\)"),
    ],
)
def test_single_arg_to_char_maps_per_target(target: str, expected: str) -> None:
    # Oracle's one-argument TO_CHAR(x) (number/date -> string) exists nowhere
    # else; it used to pass through verbatim (14 statements on the dump).
    r = _t("UPDATE t1 SET c1 = TO_CHAR(c2) WHERE id = 1;", "oracle", target)
    assert re.search(expected, r.sql), r.sql
    assert "TO_CHAR" not in r.sql.upper()


def test_merge_gets_tsql_terminator_and_no_dual() -> None:
    # T-SQL requires MERGE to end with ';' (error 10713 otherwise — 11
    # statements on the dump), and the USING subquery must lose FROM DUAL.
    src = (
        "MERGE INTO t1 a USING (SELECT 1 AS id FROM DUAL) b ON (a.id = b.id) "
        "WHEN MATCHED THEN UPDATE SET a.c = 2 "
        "WHEN NOT MATCHED THEN INSERT (id, c) VALUES (b.id, 2);"
    )
    r = _t(src, "oracle", "tsql")
    assert "UNIQUE-" not in r.sql, r.sql
    assert "DUAL" not in r.sql.upper()
    body = r.sql.strip()
    assert body.rstrip("GO").rstrip().endswith(";"), r.sql


# ---------------------------------------------------------------------------
# B1 — ALTER TABLE ADD CONSTRAINT ... PRIMARY KEY CLUSTERED (col ASC) WITH (...)
# ---------------------------------------------------------------------------

_B1 = (
    "ALTER TABLE [dbo].[t1] ADD CONSTRAINT [PK_t1] PRIMARY KEY CLUSTERED \n"
    "(\n\t[id] ASC,\n\t[rev] DESC\n"
    ")WITH (PAD_INDEX = OFF, IGNORE_DUP_KEY = OFF) ON [PRIMARY]"
)


@pytest.mark.parametrize("target", ["oracle", "postgresql", "mysql"])
def test_add_pk_clustered_normalizes(target: str) -> None:
    r = _t(_B1, "tsql", target)
    up = " ".join(r.sql.split()).upper()
    assert "UNIQUE-" not in r.sql, r.sql
    assert re.search(r"ADD CONSTRAINT \S*PK_T1\S* PRIMARY KEY", up), r.sql
    # Storage clauses and per-column sort order are T-SQL-only.
    for tok in ("CLUSTERED", "PAD_INDEX", "NULLS", " ASC", " DESC", "ON [PRIMARY]"):
        assert tok not in up, (tok, r.sql)
    assert re.search(r"PRIMARY KEY \(\S*ID\S*, \S*REV\S*\)", up), r.sql


def test_add_pk_clustered_inside_guard_stays_valid_oracle() -> None:
    src = (
        "IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'PK_t1')\n"
        "BEGIN\n" + _B1 + "\nEND\nGO"
    )
    r = _t(src, "tsql", "oracle")
    up = " ".join(r.sql.split()).upper()
    assert "PRIMARY KEY," not in up, r.sql  # the comma-mangled form
    assert "WITH (PAD_INDEX" not in up, r.sql
    assert "PRIMARY KEY (" in up


# ---------------------------------------------------------------------------
# B3 — named DEFAULT constraint (T-SQL-only) + B4 comment after bare RETURN
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["mysql", "postgresql", "oracle"])
def test_named_default_constraint_dropped_with_note(target: str) -> None:
    r = _t(
        "ALTER TABLE t1 ADD col_x INT CONSTRAINT df_x DEFAULT 0 NOT NULL;",
        "tsql",
        target,
    )
    executable = " ".join(
        ln
        for ln in r.sql.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ).upper()
    assert "CONSTRAINT DF_X" not in executable, r.sql
    assert re.search(r"DEFAULT 0", executable), r.sql
    assert any("df_x" in w.message for w in r.warnings), [w.message for w in r.warnings]


def test_comment_after_bare_return_survives() -> None:
    # B4: the comment following a bare RETURN used to be swallowed (with a
    # false 'discarded RETURN value' warning).
    src = (
        "CREATE OR REPLACE PROCEDURE p1 AS\nBEGIN\n"
        "  IF 1 = 0 THEN\n    RETURN;\n  END IF;\n"
        "  -- important note\n  INSERT INTO t (id) VALUES (1);\nEND;\n/"
    )
    r = _t(src, "oracle", "postgresql")
    assert "important note" in r.sql
    assert "INSERT INTO t" in r.sql
    assert not any("RETURN" in w.message for w in r.warnings)
