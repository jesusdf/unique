# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Isolation helpers of scripts/mutation_test.py (B24).

The harness must mutate a temporary copy of ``src/``, never the real source
tree, so a concurrent local test run can't read a mutant. These unit tests
cover the pure copy/path-mapping/env-building helpers; the end-to-end subprocess
behavior is covered by running the script for real (see docs/TODO.md B24 note).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "mutation_test.py"
_spec = importlib.util.spec_from_file_location("mutation_test", _PATH)
assert _spec is not None and _spec.loader is not None
mutation_test = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mutation_test)


class TestCopySrcTree:
    def test_copies_into_a_src_subdir_without_touching_the_real_tree(
        self, tmp_path: Path
    ) -> None:
        real_registry = mutation_test._SRC_ROOT / "unique" / "core" / "registry.py"
        before = real_registry.read_text()

        temp_src = mutation_test._copy_src_tree(tmp_path)

        assert temp_src == tmp_path / "src"
        copied_registry = temp_src / "unique" / "core" / "registry.py"
        assert copied_registry.read_text() == before
        # Writing to the copy must never touch the real file.
        copied_registry.write_text("mutated")
        assert real_registry.read_text() == before


class TestMutatedPath:
    def test_maps_a_real_src_path_into_the_temp_copy(self, tmp_path: Path) -> None:
        temp_src = tmp_path / "src"
        real = mutation_test._SRC_ROOT / "unique" / "core" / "registry.py"
        mapped = mutation_test._mutated_path(str(real), temp_src)
        assert mapped == temp_src / "unique" / "core" / "registry.py"

    def test_accepts_a_repo_relative_path(self, tmp_path: Path) -> None:
        temp_src = tmp_path / "src"
        mapped = mutation_test._mutated_path("src/unique/core/registry.py", temp_src)
        assert mapped == temp_src / "unique" / "core" / "registry.py"

    def test_rejects_a_path_outside_src(self, tmp_path: Path) -> None:
        temp_src = tmp_path / "src"
        with pytest.raises(ValueError):
            mutation_test._mutated_path("docs/TODO.md", temp_src)


class TestMutationEnv:
    def test_pythonpath_points_at_the_temp_copy_first(self, tmp_path: Path) -> None:
        temp_src = tmp_path / "src"
        env = mutation_test._mutation_env(temp_src)
        assert env["PYTHONPATH"].split(os.pathsep)[0] == str(temp_src)

    def test_preserves_a_pre_existing_pythonpath(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PYTHONPATH", "/some/other/path")
        temp_src = tmp_path / "src"
        env = mutation_test._mutation_env(temp_src)
        parts = env["PYTHONPATH"].split(os.pathsep)
        assert parts[0] == str(temp_src)
        assert "/some/other/path" in parts
