# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""RC-1b — the unmapped-built-in gate (source-side decision).

A scalar call in the source SQL is one of three things, and the transpiler must
tell them apart from the *source* catalog (where the source dialect is known):

1. a source built-in that HAS a target form   -> translate it;
2. a source built-in with NO target equivalent -> degrade the WHOLE statement to
   a carrier + warning (honest, never silently invalid);
3. a name that is NOT a source built-in         -> a user object (UDF / stored
   proc / user type) -> pass it through verbatim, never degrade.

Case (2) is the defect this gate closes: an unmapped built-in used to ship
verbatim with ``warnings == []`` (invalid on the target, silently). Case (3) is
the guard that the gate must not over-reach and break valid user-object calls.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str):
    return Transpiler().transpile(sql, source, target)


def test_unmapped_source_builtin_degrades_to_carrier() -> None:
    """MySQL SOUNDEX has no core PostgreSQL built-in -> carrier + warning."""
    r = _t("SELECT SOUNDEX('x') AS r", "mysql", "postgresql")
    # Honest degrade: the statement is preserved as a UNIQUE carrier comment,
    # and the gap is reported programmatically (no silent invalid output).
    assert "-- UNIQUE:" in r.sql, r.sql
    assert r.warnings, "unmapped built-in must report a warning"
    # The source built-in survives only inside the (commented) carrier body,
    # never as live output that PostgreSQL would reject.
    live = "\n".join(
        line for line in r.sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert "SOUNDEX" not in live.upper(), f"shipped invalid live SOUNDEX: {r.sql!r}"


def test_user_function_passes_through_untouched() -> None:
    """A non-built-in name is a user object: passthrough, no warning, no carrier."""
    r = _t("SELECT my_custom_fn(x) AS r FROM t", "mysql", "postgresql")
    assert "my_custom_fn(" in r.sql, r.sql
    assert "-- UNIQUE:" not in r.sql, f"user function wrongly degraded: {r.sql!r}"
    assert not r.warnings, f"user function must not warn: {r.warnings!r}"


def test_mapped_source_builtin_still_translates() -> None:
    """A built-in with a target form still translates (gate must not intercept)."""
    r = _t("SELECT IFNULL(a, 0) AS r FROM t", "mysql", "postgresql")
    assert "COALESCE" in r.sql.upper(), r.sql  # target idiom present
    assert "IFNULL" not in r.sql.upper(), r.sql  # source idiom gone
    assert "-- UNIQUE:" not in r.sql, r.sql  # not degraded


def test_degrade_reports_warning_and_unsupported() -> None:
    """The honest degrade is visible programmatically, not only in the SQL text."""
    r = _t("SELECT SOUNDEX('x') AS r", "mysql", "postgresql")
    assert r.warnings, r
    assert getattr(r, "unsupported", None), r  # API/CLI consumers see the gap


def test_degrade_is_per_target_not_blanket() -> None:
    """SOUNDEX has no PostgreSQL form but *is* a T-SQL/Oracle built-in."""
    assert "-- UNIQUE:" in _t("SELECT SOUNDEX('x') AS r", "mysql", "postgresql").sql
    for tgt in ("tsql", "oracle"):
        out = _t("SELECT SOUNDEX('x') AS r", "mysql", tgt).sql
        assert "-- UNIQUE:" not in out, (tgt, out)
        assert "SOUNDEX" in out.upper(), (tgt, out)


def test_mapped_aggregate_not_degraded() -> None:
    """GROUP_CONCAT emits STRING_AGG on PostgreSQL — a target form, not a gap.

    Guards the sqlglot-canonicalisation trap: the emitted STRING_AGG parses back
    to GROUP_CONCAT in sqlglot's AST, so the scan must read the emitted text.
    """
    r = _t("SELECT GROUP_CONCAT(x) AS r FROM t", "mysql", "postgresql")
    assert "STRING_AGG" in r.sql.upper(), r.sql
    assert "-- UNIQUE:" not in r.sql, r.sql


def test_values_clause_and_cast_not_flagged() -> None:
    """VALUES (a keyword, also a MySQL function) and CAST are never false-degraded."""
    r = _t("INSERT INTO t (a, b) VALUES (1, 2)", "mysql", "tsql")
    assert "-- UNIQUE:" not in r.sql, r.sql
    r2 = _t("SELECT CAST(a AS CHAR(10)) AS r FROM t", "mysql", "postgresql")
    assert "-- UNIQUE:" not in r2.sql, r2.sql


def test_table_name_colliding_with_builtin_not_flagged() -> None:
    """A table named `line`/`point` (PostgreSQL geometric built-ins) is not a call."""
    for tbl in ("line", "point"):
        r = _t(f"INSERT INTO {tbl} (a) VALUES (1)", "postgresql", "mysql")
        assert "-- UNIQUE:" not in r.sql, (tbl, r.sql)


def test_unmapped_builtin_in_procedure_body_degrades() -> None:
    """An unmapped built-in inside a routine body degrades too (not only DML)."""
    r = _t(
        "CREATE PROCEDURE p() BEGIN SELECT SOUNDEX('x'); END", "mysql", "postgresql"
    )
    assert "-- UNIQUE:" in r.sql, r.sql
    assert r.warnings, r


def test_user_function_in_procedure_body_passes_through() -> None:
    """A user function inside a routine body is preserved (not a source built-in)."""
    r = _t(
        "CREATE PROCEDURE p() BEGIN SELECT my_custom_fn(1); END", "mysql", "postgresql"
    )
    assert "my_custom_fn" in r.sql, r.sql
    assert "-- UNIQUE:" not in r.sql, r.sql
