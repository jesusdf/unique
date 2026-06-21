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

"""Unit tests for the live-validation statement splitters.

These exercise pure splitting logic (no database driver needed), in
particular the MySQL splitter's handling of client-side ``DELIMITER`` blocks,
which a driver cannot interpret on its own.
"""

from __future__ import annotations

from tests.helpers.live_validation import _split_mysql_statements


class TestSplitMySQLStatements:
    def test_plain_statements_split_on_semicolon(self) -> None:
        sql = "CREATE TABLE t (id INT); INSERT INTO t VALUES (1);"
        stmts = [s.strip() for s in _split_mysql_statements(sql) if s.strip()]
        assert stmts == ["CREATE TABLE t (id INT)", "INSERT INTO t VALUES (1)"]

    def test_delimiter_block_is_one_statement(self) -> None:
        sql = (
            "DELIMITER $$\n"
            "CREATE PROCEDURE p()\n"
            "BEGIN\n"
            "    SELECT 1;\n"
            "    SELECT 2;\n"
            "END$$\n"
            "DELIMITER ;\n"
        )
        stmts = _split_mysql_statements(sql)
        # The whole routine is a single statement; inner ';' did not split it.
        assert len(stmts) == 1
        body = stmts[0]
        assert body.startswith("CREATE PROCEDURE p()")
        assert "SELECT 1;" in body
        assert "SELECT 2;" in body
        # The DELIMITER lines and the trailing '$$' are removed.
        assert "DELIMITER" not in body.upper()
        assert not body.rstrip().endswith("$$")

    def test_mixed_ddl_and_routine(self) -> None:
        sql = (
            "CREATE TABLE t (id INT);\n"
            "DELIMITER $$\n"
            "CREATE PROCEDURE p()\nBEGIN\n    UPDATE t SET id = id + 1;\nEND$$\n"
            "DELIMITER ;\n"
            "INSERT INTO t VALUES (1);\n"
        )
        stmts = [s.strip() for s in _split_mysql_statements(sql) if s.strip()]
        assert any(s.startswith("CREATE TABLE t") for s in stmts)
        assert any(s.startswith("CREATE PROCEDURE p()") for s in stmts)
        assert any(s.startswith("INSERT INTO t") for s in stmts)
        # No DELIMITER directive leaks into any executable statement.
        assert all("DELIMITER" not in s.upper() for s in stmts)

    def test_multiple_routines(self) -> None:
        sql = (
            "DELIMITER $$\n"
            "CREATE PROCEDURE a()\nBEGIN\n    SELECT 1;\nEND$$\n"
            "CREATE PROCEDURE b()\nBEGIN\n    SELECT 2;\nEND$$\n"
            "DELIMITER ;\n"
        )
        stmts = [s for s in _split_mysql_statements(sql) if s.strip()]
        assert len(stmts) == 2
        assert stmts[0].startswith("CREATE PROCEDURE a()")
        assert stmts[1].startswith("CREATE PROCEDURE b()")
