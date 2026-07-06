#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Cut a release: bump the single-sourced version, verify, commit, tag, and push.

The version lives in exactly one place — ``__version__`` in
``src/unique/__init__.py`` (``pyproject.toml`` reads it dynamically). This script
bumps it, runs the quick gate, makes the ``chore(release)`` commit, creates the
annotated ``vX.Y.Z`` tag (message ``unique X.Y.Z``, matching the repo convention),
and pushes both — so a release is one command instead of several hand edits.

Usage:
    scripts/release.py 0.20.0        # explicit version
    scripts/release.py minor         # 0.19.3 -> 0.20.0
    scripts/release.py patch         # 0.19.3 -> 0.19.4
    scripts/release.py major         # 0.19.3 -> 1.0.0

    scripts/release.py minor --dry-run     # print the plan, change nothing
    scripts/release.py 0.20.0 --no-push    # commit + tag locally, don't push
    scripts/release.py patch --skip-checks # skip the black/ruff/mypy/pytest gate
    scripts/release.py patch -y            # don't prompt for confirmation
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "unique" / "__init__.py"
_VERSION_RE = re.compile(r'(?m)^(__version__\s*=\s*)"([^"]+)"')


def _fail(msg: str) -> None:
    raise SystemExit(f"release: {msg}")


def _out(*cmd: str) -> str:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _run(*cmd: str) -> None:
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def _read_version() -> str:
    m = _VERSION_RE.search(INIT.read_text(encoding="utf-8"))
    if not m:
        _fail(f"no __version__ in {INIT}")
    assert m is not None
    return m.group(2)


def _write_version(new: str) -> None:
    text = INIT.read_text(encoding="utf-8")
    INIT.write_text(_VERSION_RE.sub(rf'\g<1>"{new}"', text, count=1), encoding="utf-8")


def _next_version(current: str, spec: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", spec):
        return spec
    try:
        major, minor, patch = (int(p) for p in current.split("."))
    except ValueError:
        _fail(f"current version {current!r} is not X.Y.Z; pass an explicit version")
    bumps = {
        "major": f"{major + 1}.0.0",
        "minor": f"{major}.{minor + 1}.0",
        "patch": f"{major}.{minor}.{patch + 1}",
    }
    if spec not in bumps:
        _fail(f"version must be major|minor|patch or X.Y.Z, got {spec!r}")
    return bumps[spec]


def _as_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def _verify() -> None:
    """Run the quick gate (format, lint, types, tests). Live DB tests skip without
    their URLs; CI runs the full live matrix on the pushed commit."""
    py = sys.executable
    checks = (
        (py, "-m", "black", "--check", "src", "tests"),
        (py, "-m", "isort", "--check-only", "src", "tests"),
        (py, "-m", "ruff", "check", "src", "tests"),
        (py, "-m", "mypy", "src/unique/", "--ignore-missing-imports"),
        (py, "-m", "pytest", "-q"),
    )
    for cmd in checks:
        _run(*cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("version", help="major | minor | patch | an explicit X.Y.Z")
    ap.add_argument("--dry-run", action="store_true", help="print the plan only")
    ap.add_argument("--no-push", action="store_true", help="commit + tag, don't push")
    ap.add_argument("--skip-checks", action="store_true", help="skip the gate")
    ap.add_argument("--allow-dirty", action="store_true", help="skip clean-tree check")
    ap.add_argument("-y", "--yes", action="store_true", help="don't prompt")
    args = ap.parse_args()

    branch = _out("git", "rev-parse", "--abbrev-ref", "HEAD")
    current = _read_version()
    new = _next_version(current, args.version)
    tag = f"v{new}"

    # Correctness checks (always apply, even to a dry-run).
    if _as_tuple(new) <= _as_tuple(current):
        _fail(f"new version {new} is not greater than current {current}")
    if _out("git", "tag", "--list", tag):
        _fail(f"tag {tag} already exists")

    push = "" if args.no_push else f"; push origin {branch} + {tag}"
    print(f"\nRelease {current} -> {new}")
    print(f'  edit    {INIT.relative_to(ROOT)}  __version__ = "{new}"')
    print(
        "  verify  black/isort/ruff/mypy/pytest"
        + (" (skipped)" if args.skip_checks else "")
    )
    print(f"  commit  chore(release): bump version to {new}")
    print(f'  tag     {tag}  (annotated: "unique {new}"){push}\n')

    dirty = bool(_out("git", "status", "--porcelain"))
    if args.dry_run:
        if branch != "main":
            print(f"  note: on branch {branch!r} (a real run must be on main)")
        if dirty:
            print("  note: working tree is dirty (a real run needs it clean)")
        print("dry-run: nothing changed.")
        return

    # Preconditions for an actual release.
    if branch != "main":
        _fail(f"on branch {branch!r}, releases are cut from main (checkout main first)")
    if dirty and not args.allow_dirty:
        _fail("working tree is not clean (commit/stash first, or --allow-dirty)")
    if not args.yes and input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("aborted.")
        return

    original = INIT.read_text(encoding="utf-8")
    _write_version(new)
    if not args.skip_checks:
        try:
            _verify()
        except subprocess.CalledProcessError:
            INIT.write_text(original, encoding="utf-8")
            _fail("gate failed — version change reverted, nothing committed")

    _run("git", "add", str(INIT.relative_to(ROOT)))
    _run("git", "commit", "-m", f"chore(release): bump version to {new}")
    _run("git", "tag", "-a", tag, "-m", f"unique {new}")
    if not args.no_push:
        _run("git", "push", "origin", branch)
        _run("git", "push", "origin", tag)

    where = "committed + tagged locally" if args.no_push else "pushed"
    print(f"\nReleased {tag} ({where}).")
    print(
        "Reminder: refresh the version line in docs/STATUS.md if this is a milestone."
    )


if __name__ == "__main__":
    main()
