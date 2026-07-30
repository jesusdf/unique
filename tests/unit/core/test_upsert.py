# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Upsert clause modeling (audit 2026-07-24 B1 / N1).

``INSERT … ON CONFLICT`` (PG) / ``ON DUPLICATE KEY UPDATE`` / ``INSERT IGNORE``
(MySQL) used to be silently dropped on every target — the whole upsert became a
plain INSERT with zero warnings. These tests lock in the IR modeling: native on
PG/MySQL, lowered to a MERGE on T-SQL/Oracle, degraded WHOLE (carrier + warning)
where no conflict key can be resolved — never a bare INSERT that would raise or
duplicate at runtime.
"""

from __future__ import annotations

import sqlglot

from unique.core.ast_nodes import ExcludedColumn, InsertStatement, OnConflictClause
from unique.core.converter import parse_sql
from unique.core.transpiler import Transpiler

_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}


def _tx(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _result(sql: str, source: str, target: str):
    return Transpiler().transpile(sql, source=source, target=target)


def _exec(sql: str) -> str:
    """Executable text only (drop -- lines and /* */ blocks) — so a source-idiom
    'absent' assertion is not defeated by the annotation comments."""
    import re

    no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return "\n".join(
        ln for ln in no_block.splitlines() if not ln.lstrip().startswith("--")
    )


def _parses(sql: str, target: str) -> bool:
    try:
        for stmt in sqlglot.parse(_exec(sql), read=_SQLGLOT_DIALECT[target]):
            if stmt is None:
                continue
        return True
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# Conversion: the IR field is populated for both source spellings.
# --------------------------------------------------------------------------


def test_pg_on_conflict_do_update_populates_ir() -> None:
    (node,) = parse_sql(
        "INSERT INTO kv (k, v) VALUES ('a', 1) "
        "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1",
        "postgresql",
    )
    assert isinstance(node, InsertStatement)
    oc = node.on_conflict
    assert isinstance(oc, OnConflictClause)
    assert oc.action == "update"
    assert oc.key_columns == ("k",)
    assert oc.assignments[0][0] == "v"
    # EXCLUDED.v maps to the incoming-row marker, even nested in an expression.
    assert any(isinstance(n, ExcludedColumn) for n in _walk(oc.assignments[0][1]))


def test_mysql_on_duplicate_key_update_populates_ir() -> None:
    (node,) = parse_sql(
        "INSERT INTO kv (k, v) VALUES ('a', 1) "
        "ON DUPLICATE KEY UPDATE v = VALUES(v) + 1",
        "mysql",
    )
    assert isinstance(node, InsertStatement)
    oc = node.on_conflict
    assert isinstance(oc, OnConflictClause)
    assert oc.action == "update"
    # MySQL states no explicit target (fires on any unique key).
    assert oc.key_columns == ()
    # VALUES(v) maps to the SAME incoming-row marker as PG's EXCLUDED.v.
    assert any(isinstance(n, ExcludedColumn) for n in _walk(oc.assignments[0][1]))


def test_pg_do_nothing_populates_ir() -> None:
    (node,) = parse_sql(
        "INSERT INTO kv (k, v) VALUES ('b', 2) ON CONFLICT DO NOTHING",
        "postgresql",
    )
    assert isinstance(node.on_conflict, OnConflictClause)
    assert node.on_conflict.action == "nothing"


def test_mysql_insert_ignore_populates_ir() -> None:
    (node,) = parse_sql("INSERT IGNORE INTO kv (k, v) VALUES ('a', 1)", "mysql")
    assert isinstance(node.on_conflict, OnConflictClause)
    assert node.on_conflict.action == "nothing"
    assert node.on_conflict.from_ignore is True


def _walk(node):
    import dataclasses

    yield node
    if dataclasses.is_dataclass(node):
        for f in dataclasses.fields(node):
            v = getattr(node, f.name)
            if dataclasses.is_dataclass(v):
                yield from _walk(v)
            elif isinstance(v, tuple):
                for item in v:
                    if dataclasses.is_dataclass(item):
                        yield from _walk(item)


# --------------------------------------------------------------------------
# Per-direction emission: target idiom present, source idiom absent, parses.
# (Table has a PRIMARY KEY so MySQL-source lowerings can resolve the key.)
# --------------------------------------------------------------------------

_PG_UPDATE = (
    "CREATE TABLE kv (k VARCHAR(10) PRIMARY KEY, v INT);\n"
    "INSERT INTO kv (k, v) VALUES ('a', 1) "
    "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1"
)
_MY_UPDATE = (
    "CREATE TABLE kv (k VARCHAR(10) PRIMARY KEY, v INT);\n"
    "INSERT INTO kv (k, v) VALUES ('a', 1) "
    "ON DUPLICATE KEY UPDATE v = VALUES(v) + 1"
)


def test_pg_update_to_tsql_lowers_to_merge() -> None:
    out = _tx(_PG_UPDATE, "postgresql", "tsql")
    assert "MERGE INTO" in out
    assert "WHEN MATCHED THEN UPDATE" in out
    assert "WHEN NOT MATCHED THEN INSERT" in out
    assert "ON CONFLICT" not in _exec(out).upper()
    assert "EXCLUDED" not in _exec(out).upper()  # mapped to the src alias
    assert "uq_s.v" in out
    assert _parses(out, "tsql")


def test_pg_update_to_oracle_lowers_to_merge_from_dual() -> None:
    out = _tx(_PG_UPDATE, "postgresql", "oracle")
    assert "MERGE INTO" in out
    assert "FROM DUAL" in out.upper()
    assert "ON CONFLICT" not in _exec(out).upper()
    assert _parses(out, "oracle")


def test_pg_update_to_mysql_uses_on_duplicate_key() -> None:
    out = _tx(_PG_UPDATE, "postgresql", "mysql")
    assert "ON DUPLICATE KEY UPDATE" in out
    assert "VALUES(v)" in out.replace(" ", "")
    assert "ON CONFLICT" not in _exec(out).upper()
    # Honesty annotation + warning for the any-key semantics.
    assert "UNIQUE-" in out
    assert _result(_PG_UPDATE, "postgresql", "mysql").warnings
    assert _parses(out, "mysql")


def test_pg_update_to_pg_is_native() -> None:
    out = _tx(_PG_UPDATE, "postgresql", "postgresql")
    assert "ON CONFLICT (k) DO UPDATE" in out
    assert "EXCLUDED.v" in out
    assert _parses(out, "postgresql")


def test_mysql_update_to_pg_needs_harvested_key() -> None:
    out = _tx(_MY_UPDATE, "mysql", "postgresql")
    assert "ON CONFLICT (k) DO UPDATE" in out
    assert "EXCLUDED.v" in out
    assert "ON DUPLICATE KEY" not in _exec(out).upper()
    # It assumed a key from the table — that must warn.
    assert _result(_MY_UPDATE, "mysql", "postgresql").warnings
    assert _parses(out, "postgresql")


def test_mysql_update_to_tsql_lowers_to_merge_with_harvested_key() -> None:
    out = _tx(_MY_UPDATE, "mysql", "tsql")
    assert "MERGE INTO" in out
    assert "uq_t.k = uq_s.k" in out
    assert "ON DUPLICATE KEY" not in _exec(out).upper()
    assert _parses(out, "tsql")


# --------------------------------------------------------------------------
# DO NOTHING / INSERT IGNORE per target.
# --------------------------------------------------------------------------

_PG_NOTHING = (
    "CREATE TABLE kv (k VARCHAR(10) PRIMARY KEY, v INT);\n"
    "INSERT INTO kv (k, v) VALUES ('b', 2) ON CONFLICT DO NOTHING"
)


def test_pg_do_nothing_to_mysql_is_insert_ignore() -> None:
    out = _tx(_PG_NOTHING, "postgresql", "mysql")
    assert "INSERT IGNORE INTO" in out
    assert "swallows other errors" in out  # honesty annotation
    assert _result(_PG_NOTHING, "postgresql", "mysql").warnings
    assert _parses(out, "mysql")


def test_pg_do_nothing_to_tsql_is_insert_only_merge() -> None:
    out = _tx(_PG_NOTHING, "postgresql", "tsql")
    assert "MERGE INTO" in out
    assert "WHEN NOT MATCHED THEN INSERT" in out
    assert "WHEN MATCHED" not in out  # DO NOTHING adds no update branch
    assert _parses(out, "tsql")


def test_pg_do_nothing_to_oracle_is_insert_only_merge() -> None:
    out = _tx(_PG_NOTHING, "postgresql", "oracle")
    assert "MERGE INTO" in out
    assert "WHEN NOT MATCHED THEN INSERT" in out
    assert _parses(out, "oracle")


# --------------------------------------------------------------------------
# No-silent-loss: an upsert with no resolvable key degrades WHOLE, warned —
# never a plain INSERT (which would raise a duplicate-key error at runtime).
# --------------------------------------------------------------------------


def test_mysql_upsert_without_known_key_degrades_whole() -> None:
    # No in-script CREATE TABLE, so no key can be harvested.
    sql = "INSERT INTO kv (k, v) VALUES ('a', 1) ON DUPLICATE KEY UPDATE v = VALUES(v)"
    for target in ("postgresql", "tsql", "oracle"):
        result = _result(sql, "mysql", target)
        body = _exec(result.sql).strip()
        # The executable INSERT must NOT survive bare (it would duplicate-key).
        assert not body or body.lstrip().upper().startswith("--") or "MERGE" not in body
        assert "preserved as a comment" in result.sql
        assert result.warnings, f"{target}: silent drop"


def test_no_upsert_is_unchanged() -> None:
    # A plain INSERT (no conflict clause) is untouched by the new path.
    out = _tx("INSERT INTO kv (k, v) VALUES ('a', 1)", "mysql", "postgresql")
    assert "ON CONFLICT" not in out
    assert "ON DUPLICATE" not in out
    assert "INSERT INTO kv" in out


# --------------------------------------------------------------------------
# Dual-pipeline: an upsert embedded in a routine body routes through the same
# IR model (not the raw-sqlglot fallback that ships the source spelling).
# --------------------------------------------------------------------------


def test_upsert_inside_procedure_body_models_via_ir() -> None:
    proc = (
        "CREATE PROCEDURE p() LANGUAGE plpgsql AS $$\n"
        "BEGIN\n"
        "  INSERT INTO kv (k, v) VALUES ('a', 1) "
        "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v + 1;\n"
        "END\n"
        "$$"
    )
    tsql = _tx(proc, "postgresql", "tsql")
    assert "MERGE INTO" in tsql
    assert "ON CONFLICT" not in _exec(tsql).upper()
    mysql = _tx(proc, "postgresql", "mysql")
    assert "ON DUPLICATE KEY UPDATE" in mysql
    assert "ON CONFLICT" not in _exec(mysql).upper()
