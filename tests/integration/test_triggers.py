# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Trigger transpilation across engines.

Covers the firing-mode surface that differs between dialects:

- timing: BEFORE / AFTER / INSTEAD OF
- granularity: row-level (FOR EACH ROW) vs statement-level

and the structural differences in how each engine declares a trigger
(PostgreSQL needs a separate trigger function; MySQL has no INSTEAD OF).

Engine hazards such as Oracle's mutating-table error (a row-level trigger that
queries or modifies its own table) are documented here as known limitations;
a faithful automatic rewrite is not generally possible, so the transpiler
should preserve the body rather than silently "fix" it.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestTriggerTiming:
    AFTER_INSERT = (
        "CREATE TRIGGER trg ON dbo.t\n"
        "AFTER INSERT\n"
        "AS\nBEGIN\n    UPDATE dbo.t SET n = 1 WHERE id = 1\nEND"
    )

    def test_after_insert_oracle(self) -> None:
        out = _t(self.AFTER_INSERT, "tsql", "oracle")
        assert "AFTER INSERT ON t" in out
        assert "dbo." not in out

    def test_after_insert_mysql(self) -> None:
        out = _t(self.AFTER_INSERT, "tsql", "mysql")
        assert "AFTER INSERT ON t" in out
        assert "FOR EACH ROW" in out

    def test_after_insert_postgresql_emits_function_and_trigger(self) -> None:
        out = _t(self.AFTER_INSERT, "tsql", "postgresql")
        # PostgreSQL needs a trigger function the trigger calls.
        assert "CREATE OR REPLACE FUNCTION trg_func()" in out
        assert "RETURNS TRIGGER" in out
        assert "EXECUTE FUNCTION trg_func();" in out
        # The body must be carried into the function, not dropped.
        assert "UPDATE t SET n = 1" in out
        # The old templating bug must not reappear.
        assert "{name}" not in out


class TestInsteadOfTrigger:
    INSTEAD_OF = (
        "CREATE TRIGGER trg ON dbo.v\n"
        "INSTEAD OF UPDATE\n"
        "AS\nBEGIN\n    SELECT 1\nEND"
    )

    def test_instead_of_documented_on_mysql(self) -> None:
        out = _t(self.INSTEAD_OF, "tsql", "mysql")
        # MySQL has no INSTEAD OF; it must be documented in a comment, not
        # emitted as an executable INSTEAD OF clause.
        code_lines = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("INSTEAD OF" not in ln for ln in code_lines)
        assert "-- UNIQUE: MySQL has no INSTEAD OF trigger" in out
        assert "BEFORE UPDATE ON v" in out

    def test_instead_of_kept_on_postgresql(self) -> None:
        # PostgreSQL supports INSTEAD OF (on views); it should be preserved.
        out = _t(self.INSTEAD_OF, "tsql", "postgresql")
        assert "INSTEAD OF UPDATE ON v" in out


class TestTriggerGranularity:
    def test_row_level_kept_oracle(self) -> None:
        src = (
            "CREATE TRIGGER trg\n"
            "BEFORE INSERT ON t\n"
            "FOR EACH ROW\n"
            "BEGIN\n    NULL;\nEND;"
        )
        out = _t(src, "oracle", "postgresql")
        assert "FOR EACH ROW" in out


class TestMutatingTableHazard:
    """Oracle raises ORA-04091 when a row-level trigger queries/modifies its
    own table. We can't auto-rewrite that faithfully, so the body must be
    preserved (so a human can apply a compound-trigger / statement-level fix),
    not silently altered."""

    def test_self_referencing_body_preserved(self) -> None:
        src = (
            "CREATE TRIGGER trg ON dbo.t\n"
            "AFTER INSERT\n"
            "AS\nBEGIN\n"
            "    UPDATE dbo.t SET n = (SELECT COUNT(*) FROM dbo.t)\nEND"
        )
        out = _t(src, "tsql", "oracle")
        # The self-referencing UPDATE/SELECT on the same table is preserved.
        assert "UPDATE t SET" in out
        assert "SELECT COUNT(*) FROM t" in out.replace("  ", " ")


def _tr(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestTriggerUpdatePredicate:
    """T-SQL UPDATE(col) inside a trigger tests whether a column changed; it
    must be rewritten per engine, not emitted verbatim (invalid elsewhere)."""

    SRC = (
        "CREATE TRIGGER dbo.trg ON dbo.t\n"
        "FOR UPDATE\nAS\nBEGIN\n"
        "    IF UPDATE(col_32)\n"
        "    BEGIN\n        INSERT INTO dbo.log (a) VALUES (1)\n    END\n"
        "END"
    )

    def test_mysql(self) -> None:
        out = _tr(self.SRC, "tsql", "mysql")
        assert "NOT (NEW.col_32 <=> OLD.col_32)" in out
        assert "UPDATE(col_32)" not in out.replace(" ", "")

    def test_postgresql(self) -> None:
        out = _tr(self.SRC, "tsql", "postgresql")
        assert "NEW.col_32 IS DISTINCT FROM OLD.col_32" in out

    def test_oracle(self) -> None:
        out = _tr(self.SRC, "tsql", "oracle")
        assert "UPDATING('col_32')" in out

    def test_plain_update_statement_untouched(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN UPDATE t SET a = 1 END"
        out = _tr(src, "tsql", "mysql")
        assert "UPDATE t SET a = 1" in out
        assert "NEW." not in out
