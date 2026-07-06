# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""The release helper's pure version-bump logic (scripts/release.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release", _PATH)
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


class TestNextVersion:
    def test_explicit_version_passes_through(self) -> None:
        assert release._next_version("0.19.0", "1.2.3") == "1.2.3"

    def test_patch_increments_last(self) -> None:
        assert release._next_version("0.19.3", "patch") == "0.19.4"

    def test_minor_resets_patch(self) -> None:
        assert release._next_version("0.19.3", "minor") == "0.20.0"

    def test_major_resets_minor_and_patch(self) -> None:
        assert release._next_version("0.19.3", "major") == "1.0.0"

    def test_invalid_spec_aborts(self) -> None:
        with pytest.raises(SystemExit):
            release._next_version("0.19.0", "nope")
