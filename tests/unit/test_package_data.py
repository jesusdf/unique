# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Packaging tripwire: every non-.py file under src/unique must ship in the wheel.

The repo checkout always has the data files, so nothing in the regular suite
notices when a file is missing from ``[tool.setuptools.package-data]`` — the
installed wheel (and the Docker image built from it) then crashes at runtime
instead (v0.32.0 shipped without ``unique/core/data/builtins/*.txt`` and the
web API 500'd on every transpile whose output gate scanned for unmapped
built-ins). This test recomputes the mapping from disk and fails the suite,
naming the uncovered file, whenever a data file is added without a matching
package-data glob.
"""

from __future__ import annotations

import tomllib
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PACKAGE = SRC / "unique"


def _package_data_patterns() -> dict[str, list[str]]:
    with (ROOT / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)
    return pyproject["tool"]["setuptools"]["package-data"]


def _data_files() -> list[Path]:
    return [
        p
        for p in PACKAGE.rglob("*")
        if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts
    ]


def test_every_data_file_is_covered_by_package_data() -> None:
    patterns = _package_data_patterns()
    uncovered = []
    for path in _data_files():
        rel = path.relative_to(SRC)
        # The owning package is the deepest ancestor directory with an
        # __init__.py; package-data globs are relative to that package.
        pkg_dir = path.parent
        while pkg_dir != SRC and not (pkg_dir / "__init__.py").exists():
            pkg_dir = pkg_dir.parent
        pkg = ".".join(pkg_dir.relative_to(SRC).parts)
        rel_to_pkg = path.relative_to(pkg_dir).as_posix()
        if not any(fnmatch(rel_to_pkg, pattern) for pattern in patterns.get(pkg, [])):
            uncovered.append(f"{rel} (package {pkg!r})")
    assert not uncovered, (
        "Files under src/unique are missing from [tool.setuptools.package-data] "
        "in pyproject.toml; the installed wheel/Docker image will not contain "
        "them:\n  " + "\n  ".join(uncovered)
    )
