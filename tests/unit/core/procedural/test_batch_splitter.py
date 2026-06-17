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

"""Tests for the batch splitter."""

from __future__ import annotations

from unique.core.batch_splitter import (
    BatchSplitter,
    BatchType,
    classify_batch,
)


class TestTSQLSplitting:
    def test_split_on_go(self) -> None:
        sql = "SELECT 1;\nGO\nSELECT 2;\nGO"
        batches = BatchSplitter.split(sql, "tsql")
        assert len(batches) == 2

    def test_go_not_split_inside_statement(self) -> None:
        sql = "SELECT 'GONE';"
        batches = BatchSplitter.split(sql, "tsql")
        assert len(batches) == 1

    def test_empty_batches_dropped(self) -> None:
        sql = "SELECT 1;\nGO\n\nGO\nSELECT 2;"
        batches = BatchSplitter.split(sql, "tsql")
        assert len(batches) == 2


class TestOracleSplitting:
    def test_split_on_slash(self) -> None:
        sql = "BEGIN\n  NULL;\nEND;\n/\nSELECT 1 FROM dual;\n/"
        batches = BatchSplitter.split(sql, "oracle")
        assert len(batches) == 2


class TestMySQLSplitting:
    def test_delimiter_change(self) -> None:
        sql = (
            "DELIMITER //\n"
            "CREATE PROCEDURE p()\nBEGIN\n  SELECT 1;\nEND//\n"
            "DELIMITER ;"
        )
        batches = BatchSplitter.split(sql, "mysql")
        assert len(batches) >= 1
        # The procedure body should be in one batch
        assert any("CREATE PROCEDURE" in b.sql for b in batches)


class TestClassification:
    def test_procedural_tsql(self) -> None:
        sql = "CREATE PROCEDURE dbo.x AS BEGIN SELECT 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_alter_procedure_is_procedural(self) -> None:
        sql = "ALTER PROCEDURE dbo.x AS BEGIN SELECT 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_procedural_oracle_with_or_replace(self) -> None:
        sql = "CREATE OR REPLACE PROCEDURE x IS BEGIN NULL; END;"
        assert classify_batch(sql, "oracle") == BatchType.PROCEDURAL

    def test_function_is_procedural(self) -> None:
        sql = "CREATE FUNCTION dbo.f() RETURNS INT AS BEGIN RETURN 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_trigger_is_procedural(self) -> None:
        sql = "CREATE TRIGGER t ON tbl AFTER INSERT AS BEGIN SELECT 1 END"
        assert classify_batch(sql, "tsql") == BatchType.PROCEDURAL

    def test_dml_select(self) -> None:
        assert classify_batch("SELECT * FROM t", "tsql") == BatchType.DML

    def test_dml_insert(self) -> None:
        assert classify_batch("INSERT INTO t VALUES (1)", "tsql") == BatchType.DML

    def test_ddl_create_table(self) -> None:
        assert classify_batch("CREATE TABLE t (id INT)", "tsql") == BatchType.DDL

    def test_set_option(self) -> None:
        assert classify_batch("SET NOCOUNT ON", "tsql") == BatchType.SET_OPTION

    def test_empty(self) -> None:
        assert classify_batch("", "tsql") == BatchType.EMPTY

    def test_comment_only(self) -> None:
        assert classify_batch("-- just a comment", "tsql") == BatchType.COMMENT


class TestBatchProperties:
    def test_is_empty_for_whitespace(self) -> None:
        batches = BatchSplitter.split("   \n  ", "tsql")
        assert all(b.is_empty for b in batches) or not batches

    def test_is_empty_for_comment_only(self) -> None:
        sql = "-- comment\n-- another"
        batches = BatchSplitter.split(sql, "tsql")
        assert all(b.is_empty for b in batches)
