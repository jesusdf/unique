# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for scripts/challenge_stats.py (audit B19)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "challenge_stats.py"
_spec = importlib.util.spec_from_file_location("challenge_stats", _PATH)
assert _spec is not None and _spec.loader is not None
cs = importlib.util.module_from_spec(_spec)
# dataclass() resolves string-form annotations (PEP 563) via
# sys.modules[cls.__module__] -- register before exec_module so it can find
# this module's own namespace.
sys.modules["challenge_stats"] = cs
_spec.loader.exec_module(cs)


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class TestParseHeaderLine:
    def test_fixed_with_class(self) -> None:
        header = cs.parse_header_line(
            "-- CASE[fixed][class=func]: pg-avg-int — averages as decimal."
        )
        assert header is not None
        assert header.status == "fixed"
        assert header.klass == "func"
        assert header.desc == "pg-avg-int — averages as decimal."

    def test_open_with_class(self) -> None:
        header = cs.parse_header_line("-- CASE[open][class=crash]: some desc")
        assert header is not None
        assert header.status == "open"
        assert header.klass == "crash"

    def test_limit_no_class(self) -> None:
        header = cs.parse_header_line("-- CASE[limit]: approved divergence")
        assert header is not None
        assert header.status == "limit"
        assert header.klass == cs.UNCLASSIFIED

    def test_untagged_defaults_to_fixed(self) -> None:
        header = cs.parse_header_line("-- CASE: legacy case, no status tag")
        assert header is not None
        assert header.status == "fixed"
        assert header.klass == cs.UNCLASSIFIED

    def test_non_header_line_returns_none(self) -> None:
        assert cs.parse_header_line("SELECT 1;") is None
        assert cs.parse_header_line("-- just a regular comment") is None

    def test_carries_source_path_lineno(self) -> None:
        header = cs.parse_header_line(
            "-- CASE[fixed]: x", source="mysql", path="f.sql", lineno=7
        )
        assert header is not None
        assert (header.source, header.path, header.lineno) == ("mysql", "f.sql", 7)


class TestSourceFromFilename:
    def test_strips_challenge_prefix(self) -> None:
        assert cs.source_from_filename(Path("challenge_postgresql.sql")) == (
            "postgresql"
        )
        assert cs.source_from_filename(Path("challenge_sqlserver.sql")) == "sqlserver"

    def test_unrecognized_name_passthrough(self) -> None:
        assert cs.source_from_filename(Path("other.sql")) == "other"


class TestParseFileAndCorpus:
    def test_parse_file_counts_headers_only(self, tmp_path: Path) -> None:
        f = tmp_path / "challenge_mysql.sql"
        f.write_text(
            "-- CASE[fixed][class=func]: a\nSELECT 1;\n"
            "-- CASE[open][class=crash]: b\nSELECT 2;\n"
            "-- not a case header\n",
            encoding="utf-8",
        )
        headers = cs.parse_file(f)
        assert len(headers) == 2
        assert [h.source for h in headers] == ["mysql", "mysql"]
        assert headers[0].lineno == 1
        assert headers[1].lineno == 3

    def test_parse_corpus_reads_all_challenge_files(self, tmp_path: Path) -> None:
        (tmp_path / "challenge_mysql.sql").write_text(
            "-- CASE[fixed]: a\n", encoding="utf-8"
        )
        (tmp_path / "challenge_oracle.sql").write_text(
            "-- CASE[open][class=func]: b\n", encoding="utf-8"
        )
        (tmp_path / "not_a_challenge_file.sql").write_text(
            "-- CASE[fixed]: ignored\n", encoding="utf-8"
        )
        headers = cs.parse_corpus(tmp_path)
        assert len(headers) == 2
        assert {h.source for h in headers} == {"mysql", "oracle"}


class TestFormatReport:
    def test_reports_status_class_source_counts(self) -> None:
        headers = [
            cs.CaseHeader("mysql", "fixed", "func", "a"),
            cs.CaseHeader("mysql", "open", "crash", "b"),
            cs.CaseHeader("oracle", "limit", cs.UNCLASSIFIED, "c"),
        ]
        report = cs.format_report(headers)
        assert "Total cases: 3" in report
        assert "fixed: 1" in report
        assert "open: 1" in report
        assert "limit: 1" in report
        assert "func: 1" in report
        assert "crash: 1" in report
        assert "unclassified: 1" in report
        assert "mysql: 2" in report
        assert "oracle: 1" in report


class TestScoreBatch:
    def _mk(self, klass: str, status: str = "open") -> cs.CaseHeader:
        return cs.CaseHeader("mysql", status, klass, "d")

    def test_diverse_batch_passes(self) -> None:
        headers = [
            self._mk("func"),  # 5
            self._mk("silent-drop"),  # 4
            self._mk("crash"),  # 3
        ]
        score = cs.score_batch(headers)
        assert score.ok
        assert score.total_points == 12
        assert score.distinct_classes == 3
        assert score.violations == []

    def test_too_few_classes_violates(self) -> None:
        headers = [self._mk("func"), self._mk("silent-drop")]
        score = cs.score_batch(headers)
        assert not score.ok
        assert any("distinct class" in v for v in score.violations)

    def test_concentration_violation(self) -> None:
        # func=5 four times (20) vs crash=3, consistency=4, invalid=2 (9 total)
        # func share = 20/29 ~ 69% > 50%.
        headers = [self._mk("func")] * 4 + [
            self._mk("crash"),
            self._mk("consistency"),
            self._mk("invalid"),
        ]
        score = cs.score_batch(headers)
        assert not score.ok
        assert any("concentration" in v for v in score.violations)

    def test_unclassified_excluded_from_scoring(self) -> None:
        headers = [
            self._mk("func"),
            self._mk("silent-drop"),
            self._mk("crash"),
            self._mk(cs.UNCLASSIFIED),
            self._mk(cs.UNCLASSIFIED),
        ]
        score = cs.score_batch(headers)
        assert score.unclassified_excluded == 2
        assert score.distinct_classes == 3
        assert score.ok

    def test_unknown_class_flagged(self) -> None:
        headers = [
            self._mk("func"),
            self._mk("silent-drop"),
            self._mk("crash"),
            self._mk("not-a-real-class"),
        ]
        score = cs.score_batch(headers)
        assert not score.ok
        assert any("unknown class" in v for v in score.violations)

    def test_empty_batch_violates_class_count(self) -> None:
        score = cs.score_batch([])
        assert not score.ok
        assert score.total_points == 0


class TestAddedCaseHeadersFromDiff:
    def test_extracts_added_case_headers_only(self) -> None:
        diff = (
            "diff --git a/tests/fixtures/challenge/challenge_mysql.sql "
            "b/tests/fixtures/challenge/challenge_mysql.sql\n"
            "--- a/tests/fixtures/challenge/challenge_mysql.sql\n"
            "+++ b/tests/fixtures/challenge/challenge_mysql.sql\n"
            "@@ -10,0 +11,4 @@\n"
            "+-- CASE[open][class=func]: new finding\n"
            "+SELECT 1;\n"
            "+-- a plain added comment, not a header\n"
            "-old removed line\n"
        )
        headers = cs.added_case_headers_from_diff(diff)
        assert len(headers) == 1
        assert headers[0].klass == "func"
        assert headers[0].status == "open"
        assert headers[0].source == "mysql"

    def test_no_hunks_yields_nothing(self) -> None:
        assert cs.added_case_headers_from_diff("") == []

    def test_multiple_files(self) -> None:
        diff = (
            "diff --git a/tests/fixtures/challenge/challenge_oracle.sql "
            "b/tests/fixtures/challenge/challenge_oracle.sql\n"
            "--- a/tests/fixtures/challenge/challenge_oracle.sql\n"
            "+++ b/tests/fixtures/challenge/challenge_oracle.sql\n"
            "@@ -1,0 +2,1 @@\n"
            "+-- CASE[open][class=crash]: a\n"
            "diff --git a/tests/fixtures/challenge/challenge_postgresql.sql "
            "b/tests/fixtures/challenge/challenge_postgresql.sql\n"
            "--- a/tests/fixtures/challenge/challenge_postgresql.sql\n"
            "+++ b/tests/fixtures/challenge/challenge_postgresql.sql\n"
            "@@ -1,0 +2,1 @@\n"
            "+-- CASE[open][class=invalid]: b\n"
        )
        headers = cs.added_case_headers_from_diff(diff)
        assert {(h.source, h.klass) for h in headers} == {
            ("oracle", "crash"),
            ("postgresql", "invalid"),
        }


class TestAddedCasesSinceRealGitRepo:
    """--batch-since's git-facing half, exercised against a throwaway repo."""

    def _init_repo(self, root: Path) -> str:
        root.mkdir(parents=True, exist_ok=True)
        _run_git(["init", "-q"], root)
        _run_git(["config", "user.email", "t@example.com"], root)
        _run_git(["config", "user.name", "Test"], root)
        challenge_dir = root / "tests" / "fixtures" / "challenge"
        challenge_dir.mkdir(parents=True)
        (challenge_dir / "challenge_mysql.sql").write_text(
            "-- CASE[fixed][class=func]: pre-existing\nSELECT 1;\n",
            encoding="utf-8",
        )
        _run_git(["add", "-A"], root)
        _run_git(["commit", "-q", "-m", "init"], root)
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_committed_addition_since_base_ref(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = self._init_repo(repo)
        challenge_dir = repo / "tests" / "fixtures" / "challenge"
        with (challenge_dir / "challenge_mysql.sql").open("a", encoding="utf-8") as fh:
            fh.write("-- CASE[open][class=crash]: new finding\nSELECT 2;\n")
        _run_git(["add", "-A"], repo)
        _run_git(["commit", "-q", "-m", "red: add a crash case"], repo)

        added = cs.added_cases_since(base_sha, repo, challenge_dir)
        open_added = [h for h in added if h.status == "open"]
        assert len(open_added) == 1
        assert open_added[0].klass == "crash"

    def test_working_tree_addition_not_yet_committed(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = self._init_repo(repo)
        challenge_dir = repo / "tests" / "fixtures" / "challenge"
        with (challenge_dir / "challenge_mysql.sql").open("a", encoding="utf-8") as fh:
            fh.write("-- CASE[open][class=invalid]: uncommitted finding\n")

        added = cs.added_cases_since(base_sha, repo, challenge_dir)
        open_added = [h for h in added if h.status == "open"]
        assert len(open_added) == 1
        assert open_added[0].klass == "invalid"

    def test_no_new_cases_yields_empty(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = self._init_repo(repo)
        challenge_dir = repo / "tests" / "fixtures" / "challenge"
        added = cs.added_cases_since(base_sha, repo, challenge_dir)
        assert added == []


class TestMain:
    def test_report_only_exits_zero(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        (tmp_path / "challenge_mysql.sql").write_text(
            "-- CASE[fixed][class=func]: a\n", encoding="utf-8"
        )
        code = cs.main(["--dir", str(tmp_path)])
        assert code == 0
        assert "Total cases: 1" in capsys.readouterr().out

    def test_batch_since_violation_exits_nonzero(
        self, tmp_path: Path, capsys  # type: ignore[no-untyped-def]
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _run_git(["init", "-q"], repo)
        _run_git(["config", "user.email", "t@example.com"], repo)
        _run_git(["config", "user.name", "Test"], repo)
        challenge_dir = repo / "tests" / "fixtures" / "challenge"
        challenge_dir.mkdir(parents=True)
        (challenge_dir / "challenge_mysql.sql").write_text(
            "-- CASE[fixed]: baseline\n", encoding="utf-8"
        )
        _run_git(["add", "-A"], repo)
        _run_git(["commit", "-q", "-m", "init"], repo)
        base_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # A single-class batch: violates both the concentration cap and the
        # >= 3 distinct classes rule.
        with (challenge_dir / "challenge_mysql.sql").open("a", encoding="utf-8") as fh:
            fh.write("-- CASE[open][class=func]: a\n" "-- CASE[open][class=func]: b\n")
        _run_git(["add", "-A"], repo)
        _run_git(["commit", "-q", "-m", "red batch"], repo)

        code = cs.main(
            [
                "--dir",
                str(challenge_dir),
                "--root",
                str(repo),
                "--batch-since",
                base_sha,
            ]
        )
        assert code == 1
        assert "VIOLATIONS" in capsys.readouterr().out
