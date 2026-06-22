# Copyright (c) 2026 Unique Contributors
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for heuristic SQL dialect detection."""

from __future__ import annotations

import pytest

from unique.core.detection import detect_dialect

_SAMPLES = {
    "tsql": (
        "CREATE TABLE [dbo].[t] ([id] INT IDENTITY(1,1) NOT NULL);\n"
        "GO\n"
        "SELECT TOP 10 * FROM [t] WHERE created = GETDATE();"
    ),
    "oracle": (
        "CREATE OR REPLACE PROCEDURE p IS\n"
        "  v NUMBER;\n"
        "BEGIN\n"
        "  SELECT NVL(x, 0) INTO v FROM dual;\n"
        "END;\n/"
    ),
    "postgresql": (
        "CREATE FUNCTION f() RETURNS TRIGGER AS $$\n"
        "BEGIN RETURN NEW; END;\n"
        "$$ LANGUAGE plpgsql;\n"
        "CREATE TABLE t (id SERIAL PRIMARY KEY);"
    ),
    "mysql": (
        "CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY) ENGINE=InnoDB;\n"
        "DELIMITER //\n"
        "CREATE PROCEDURE p() BEGIN SELECT LAST_INSERT_ID(); END //"
    ),
}


class TestDetectDialect:
    @pytest.mark.parametrize("expected,sql", list(_SAMPLES.items()))
    def test_detects_each_dialect(self, expected: str, sql: str) -> None:
        result = detect_dialect(sql)
        assert result.dialect == expected
        assert result.confidence > 0.5

    def test_empty_input_returns_none(self) -> None:
        result = detect_dialect("")
        assert result.dialect is None
        assert result.confidence == 0.0

    @pytest.mark.parametrize(
        "prose",
        [
            "hello world this is just prose",
            "the quick brown fox jumps",
            "random notes no database keywords 12345",
        ],
    )
    def test_non_sql_prose_is_not_detected(self, prose: str) -> None:
        # A stray common word (e.g. "text") must not trigger a false match.
        result = detect_dialect(prose)
        assert result.dialect is None

    def test_scores_present_for_all_candidates(self) -> None:
        result = detect_dialect("SELECT 1")
        assert set(result.scores) == {"tsql", "oracle", "postgresql", "mysql"}

    def test_pg_dump_data_only_detected(self) -> None:
        # pg_dump output (data-heavy) lacks SERIAL/$$ but has SET signatures.
        sql = (
            "SET statement_timeout = 0;\n"
            "SET client_encoding = 'UTF8';\n"
            "SET standard_conforming_strings = on;\n"
            "INSERT INTO public.t VALUES (1, 'a');"
        )
        assert detect_dialect(sql).dialect == "postgresql"

    def test_backticks_signal_mysql(self) -> None:
        assert detect_dialect("SELECT `col` FROM `tbl`").dialect == "mysql"

    def test_bracket_identifiers_signal_tsql(self) -> None:
        sql = "SELECT [col] FROM [dbo].[tbl] WHERE [x] = 1"
        assert detect_dialect(sql).dialect == "tsql"
