# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for the command-line interface."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from unique.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestDialectsCommand:
    def test_lists_all_dialects(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["dialects"])
        assert result.exit_code == 0
        for d in ("tsql", "oracle", "postgresql", "mysql"):
            assert d in result.output


class TestTranspileCommand:
    _MALFORMED = "INSERT INTO t VALUES (1)\nCREATE PROCEDURE p AS BEGIN SELECT 1 END"

    def test_transpile_from_stdin(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["transpile", "--from", "tsql", "--to", "postgresql"],
            input="SELECT TOP 1 * FROM t;",
        )
        assert result.exit_code == 0
        assert result.output.strip()

    def test_refuses_malformed_source(self, runner: CliRunner) -> None:
        # A CREATE PROCEDURE with no preceding GO is a source syntax error: refuse
        # (exit 1) and report it, rather than silently transpile garbage.
        result = runner.invoke(
            cli,
            ["transpile", "--from", "tsql", "--to", "oracle"],
            input=self._MALFORMED,
        )
        assert result.exit_code == 1
        assert "syntax error" in result.output.lower()
        assert "line 2" in result.output

    def test_ignore_syntax_errors_forces_transpile(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["transpile", "--from", "tsql", "--to", "oracle", "--ignore-syntax-errors"],
            input=self._MALFORMED,
        )
        assert result.exit_code == 0

    def test_transpile_from_file(self, runner: CliRunner, tmp_path: Path) -> None:
        f = tmp_path / "in.sql"
        f.write_text("SELECT 1;")
        result = runner.invoke(
            cli,
            ["transpile", str(f), "--from", "tsql", "--to", "oracle"],
        )
        assert result.exit_code == 0

    def test_transpile_to_output_file(self, runner: CliRunner, tmp_path: Path) -> None:
        f = tmp_path / "in.sql"
        f.write_text("SELECT 1;")
        out = tmp_path / "out.sql"
        result = runner.invoke(
            cli,
            [
                "transpile",
                str(f),
                "--from",
                "tsql",
                "--to",
                "oracle",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert out.exists()
        assert out.read_text().strip()

    def test_empty_input_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["transpile", "--from", "tsql", "--to", "oracle"],
            input="   ",
        )
        assert result.exit_code != 0

    def test_db_url_option_accepted(self, runner: CliRunner, tmp_path: Path) -> None:
        # An unreachable URL should not crash transpilation of plain SQL;
        # the resolver fails to connect and the engine proceeds.
        f = tmp_path / "in.sql"
        f.write_text("SELECT 1;")
        result = runner.invoke(
            cli,
            [
                "transpile",
                str(f),
                "--from",
                "tsql",
                "--to",
                "oracle",
                "--db-url",
                "postgresql://u:p@127.0.0.1:1/none",
            ],
        )
        # Either succeeds (resolver skipped) — must not raise unhandled.
        assert result.exit_code == 0


class TestTranspileIgnore:
    # SET lock_timeout is a PostgreSQL session GUC with no T-SQL form; it
    # degrades with a UNIQUE-1218 warning.
    _GUC = "SET lock_timeout = 0;"

    def test_warning_shows_its_code_by_default(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["transpile", "--from", "postgresql", "--to", "tsql"],
            input=self._GUC,
        )
        assert result.exit_code == 0
        assert "WARNING [UNIQUE-1218]:" in result.output
        assert "suppressed" not in result.output

    def test_ignore_suppresses_matching_warning(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "transpile",
                "--from",
                "postgresql",
                "--to",
                "tsql",
                "--ignore",
                "UNIQUE-1218",
            ],
            input=self._GUC,
        )
        assert result.exit_code == 0
        # The WARNING line is gone from the channel...
        assert "WARNING [UNIQUE-1218]:" not in result.output
        assert "1 warning(s) suppressed by --ignore" in result.output
        # ...but the carrier stays in the SQL — --ignore governs only the
        # warning channel, the SQL text is the artifact.
        assert "-- UNIQUE-1218:" in result.output

    def test_ignore_is_case_insensitive(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "transpile",
                "--from",
                "postgresql",
                "--to",
                "tsql",
                "--ignore",
                "unique-1218",
            ],
            input=self._GUC,
        )
        assert result.exit_code == 0
        assert "1 warning(s) suppressed by --ignore" in result.output

    def test_unknown_ignore_code_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "transpile",
                "--from",
                "postgresql",
                "--to",
                "tsql",
                "--ignore",
                "UNIQUE-9999",
            ],
            input=self._GUC,
        )
        assert result.exit_code == 1
        assert "unknown diagnostic code" in result.output.lower()
        assert "UNIQUE-9999" in result.output

    def test_ignore_non_matching_code_keeps_warning(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "transpile",
                "--from",
                "postgresql",
                "--to",
                "tsql",
                "--ignore",
                "UNIQUE-1001",
            ],
            input=self._GUC,
        )
        assert result.exit_code == 0
        assert "WARNING [UNIQUE-1218]:" in result.output
        assert "suppressed" not in result.output


class TestValidateCommand:
    def test_valid_sql(self, runner: CliRunner, tmp_path: Path) -> None:
        f = tmp_path / "ok.sql"
        f.write_text("SELECT 1;")
        result = runner.invoke(cli, ["validate", str(f), "--dialect", "tsql"])
        assert result.exit_code == 0
        assert "Valid" in result.output

    def test_reports_located_syntax_error(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        f = tmp_path / "bad.sql"
        f.write_text("SELECT * FROM (SELECT 1")
        result = runner.invoke(cli, ["validate", str(f), "--dialect", "tsql"])
        assert result.exit_code == 1
        assert "Invalid" in result.output and "line 1" in result.output

    def test_pg_table_shorthand_is_valid(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # B20/N13: PostgreSQL's ``TABLE t`` shorthand must not be flagged.
        f = tmp_path / "ok.sql"
        f.write_text("TABLE t")
        result = runner.invoke(cli, ["validate", str(f), "--dialect", "postgresql"])
        assert result.exit_code == 0
        assert "Valid" in result.output


class TestHelp:
    def test_top_level_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "transpile" in result.output
        assert "validate" in result.output

    def test_transpile_help_shows_db_url(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["transpile", "--help"])
        assert result.exit_code == 0
        assert "--db-url" in result.output
