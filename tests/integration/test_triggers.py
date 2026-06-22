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
