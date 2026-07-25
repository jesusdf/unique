# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for scripts/private_leak_check.py (audit B18).

All private-corpus state here is synthetic, built under ``tmp_path`` — the
real (gitignored) ``fixtures-private/`` is never read or written by these
tests.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "private_leak_check.py"
_spec = importlib.util.spec_from_file_location("private_leak_check", _PATH)
assert _spec is not None and _spec.loader is not None
plc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plc)


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(root: Path) -> str:
    """A throwaway git repo with one commit; returns its short sha."""
    root.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-q"], root)
    _run_git(["config", "user.email", "t@example.com"], root)
    _run_git(["config", "user.name", "Test"], root)
    (root / "f.sql").write_text("SELECT 1;\n", encoding="utf-8")
    _run_git(["add", "f.sql"], root)
    _run_git(["commit", "-q", "-m", "init"], root)
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class TestBuildTokenSet:
    def test_drops_short_tokens(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text("short\n", encoding="utf-8")
        tokens = plc.build_token_set(private, drop=frozenset())
        assert "short" not in tokens  # 5 chars, below the length-6 floor

    def test_drops_stopwords(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text("SELECT column_name\n", encoding="utf-8")
        tokens = plc.build_token_set(private, drop=plc.stopwords())
        assert "select" not in tokens
        assert "column" not in tokens

    def test_keeps_distinctive_token(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        tokens = plc.build_token_set(private, drop=plc.stopwords())
        assert "zzqfrobnicate" in tokens

    def test_case_folded(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text("ZzQfrobnicateXY\n", encoding="utf-8")
        tokens = plc.build_token_set(private, drop=frozenset())
        assert "zzqfrobnicatexy" in tokens

    def test_ignores_leak_fragments_file_itself(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "leak_fragments.txt").write_text("zzqfrobnicate\n", encoding="utf-8")
        tokens = plc.build_token_set(private, drop=frozenset())
        # leak_fragments.txt is fragment input, not corpus text -- excluded
        # from token derivation to avoid double-processing it as raw SQL.
        assert "zzqfrobnicate" not in tokens

    def test_missing_dir_yields_empty_set(self, tmp_path: Path) -> None:
        tokens = plc.build_token_set(tmp_path / "does-not-exist")
        assert tokens == frozenset()


class TestBuildFragmentList:
    def test_reads_fragments_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "leak_fragments.txt").write_text(
            "# a comment\n\nfoo_\nBar-Baz\n", encoding="utf-8"
        )
        fragments = plc.build_fragment_list(private)
        assert fragments == ("foo_", "bar-baz")

    def test_missing_file_yields_empty_tuple(self, tmp_path: Path) -> None:
        private = tmp_path / "fixtures-private"
        private.mkdir()
        assert plc.build_fragment_list(private) == ()


class TestFindHits:
    def test_finds_token_hit(self) -> None:
        hits = plc.find_hits("value = zzqfrobnicate", frozenset({"zzqfrobnicate"}), ())
        assert hits == ["zzqfrobnicate"]

    def test_finds_fragment_substring_hit(self) -> None:
        hits = plc.find_hits("col zzq-frag_flag", frozenset(), ("zzq-frag",))
        assert hits == ["zzq-frag"]

    def test_clean_line_no_hits(self) -> None:
        assert plc.find_hits("SELECT 1", frozenset({"zzqfrobnicate"}), ()) == []

    def test_case_insensitive(self) -> None:
        hits = plc.find_hits("ZZQFROBNICATE", frozenset({"zzqfrobnicate"}), ())
        assert hits == ["zzqfrobnicate"]


class TestIterAddedLines:
    def test_parses_single_hunk(self) -> None:
        diff = (
            "diff --git a/f.sql b/f.sql\n"
            "index 111..222 100644\n"
            "--- a/f.sql\n"
            "+++ b/f.sql\n"
            "@@ -1,2 +1,3 @@\n"
            " SELECT 1;\n"
            "+SELECT zzqfrobnicate;\n"
            " SELECT 2;\n"
        )
        added = list(plc.iter_added_lines(diff))
        assert added == [("f.sql", 2, "SELECT zzqfrobnicate;")]

    def test_multiple_files_and_hunks(self) -> None:
        diff = (
            "diff --git a/a.sql b/a.sql\n"
            "--- a/a.sql\n"
            "+++ b/a.sql\n"
            "@@ -1,1 +1,2 @@\n"
            " SELECT 1;\n"
            "+SELECT 2;\n"
            "diff --git a/b.sql b/b.sql\n"
            "--- a/b.sql\n"
            "+++ b/b.sql\n"
            "@@ -5,0 +6,1 @@\n"
            "+SELECT 3;\n"
        )
        added = list(plc.iter_added_lines(diff))
        assert added == [("a.sql", 2, "SELECT 2;"), ("b.sql", 6, "SELECT 3;")]

    def test_removed_lines_not_yielded(self) -> None:
        diff = (
            "diff --git a/f.sql b/f.sql\n"
            "--- a/f.sql\n"
            "+++ b/f.sql\n"
            "@@ -1,2 +1,1 @@\n"
            "-SELECT old;\n"
            " SELECT 1;\n"
        )
        assert list(plc.iter_added_lines(diff)) == []

    def test_empty_diff(self) -> None:
        assert list(plc.iter_added_lines("")) == []


class TestScanRepoEndToEnd:
    """Exercises the real git plumbing against a throwaway temp repo + a
    synthetic (never-real) private-corpus fixture."""

    def test_clean_tree_reports_no_hits(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        hits = plc.scan_repo(repo, private, base_sha)
        assert hits == []

    def test_staged_change_with_known_token_is_flagged(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        (repo / "f.sql").write_text(
            "SELECT 1;\n-- refers to zzqfrobnicate\n", encoding="utf-8"
        )
        _run_git(["add", "f.sql"], repo)

        hits = plc.scan_repo(repo, private, base_sha)
        assert any("zzqfrobnicate" in h and "f.sql" in h for h in hits)

    def test_unstaged_working_tree_change_is_flagged(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        # Not staged -- git diff HEAD must still see it.
        (repo / "f.sql").write_text(
            "SELECT 1;\n-- refers to zzqfrobnicate\n", encoding="utf-8"
        )

        hits = plc.scan_repo(repo, private, base_sha)
        assert any("zzqfrobnicate" in h for h in hits)

    def test_committed_message_since_base_ref_is_flagged(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        (repo / "g.sql").write_text("SELECT 2;\n", encoding="utf-8")
        _run_git(["add", "g.sql"], repo)
        _run_git(["commit", "-q", "-m", "touches zzqfrobnicate in the message"], repo)

        hits = plc.scan_repo(repo, private, base_sha)
        assert any("commit" in h and "zzqfrobnicate" in h for h in hits)

    def test_fragment_only_hit_is_flagged(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        # "med-flag" is below the 6-char whole-token floor once hyphenated
        # ("med" / "flag" split), so only the fragment list catches it.
        (private / "leak_fragments.txt").write_text("med-flag\n", encoding="utf-8")
        (repo / "f.sql").write_text(
            "SELECT 1;\n-- internal med-flag column\n", encoding="utf-8"
        )
        _run_git(["add", "f.sql"], repo)

        hits = plc.scan_repo(repo, private, base_sha)
        assert any("med-flag" in h for h in hits)


class TestMain:
    def test_absent_private_dir_exits_zero(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        repo = tmp_path / "repo"
        _init_repo(repo)
        code = plc.main(
            [
                "--root",
                str(repo),
                "--private-dir",
                str(tmp_path / "does-not-exist"),
            ]
        )
        assert code == 0
        assert "absent" in capsys.readouterr().out

    def test_clean_tree_exits_zero(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        code = plc.main(
            [
                "--root",
                str(repo),
                "--private-dir",
                str(private),
                "--base-ref",
                base_sha,
            ]
        )
        assert code == 0
        assert "clean" in capsys.readouterr().out

    def test_leak_exits_nonzero(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        repo = tmp_path / "repo"
        base_sha = _init_repo(repo)
        private = tmp_path / "fixtures-private"
        private.mkdir()
        (private / "dump.sql").write_text(
            "CREATE TABLE zzqfrobnicate (id INT);\n", encoding="utf-8"
        )
        (repo / "f.sql").write_text("SELECT 1;\n-- zzqfrobnicate\n", encoding="utf-8")
        _run_git(["add", "f.sql"], repo)

        code = plc.main(
            [
                "--root",
                str(repo),
                "--private-dir",
                str(private),
                "--base-ref",
                base_sha,
            ]
        )
        assert code == 1
        assert "zzqfrobnicate" in capsys.readouterr().out
