#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Challenge-corpus stats + batch scoring (audit 2026-07-24 T5 / 09-fix-briefs.md B19).

Parses the ``-- CASE[status][class=<class>]: <desc>`` headers across
``tests/fixtures/challenge/challenge_*.sql`` (see skills/SKILL-challenge-corpus.md
"Case status tags" and "Finding classes and batch scoring") and reports
per-status / per-class / per-source counts.

``--batch-since <git-ref>`` additionally scores the ``[open]`` cases added
since ``<git-ref>`` against the skill's mechanical A9 batch rules:

- points table: func/composition 5, silent-drop/consistency 4, crash 3,
  invalid/lying-warning 2;
- no single class may exceed 50% of the batch's points (concentration cap);
- the batch must span >= 3 distinct classes.

Legacy cases without a ``[class=...]`` tag are counted as ``unclassified`` in
the corpus-wide report but **excluded from batch scoring** (no retro-tagging
required — this only applies going forward). Exits non-zero when a batch
violates a rule, printing which rule and why.

Pure stdlib; the only external process invoked is ``git`` (for
``--batch-since``).

Usage::

    python scripts/challenge_stats.py                       # corpus-wide report
    python scripts/challenge_stats.py --batch-since HEAD~20  # + batch gate
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DIR = _ROOT / "tests" / "fixtures" / "challenge"

_HEADER_RE = re.compile(
    r"^--\s*CASE(?:\[(?P<status>[a-z]+)\])?"
    r"(?:\[class=(?P<klass>[a-z][a-z-]*)\])?:\s*(?P<desc>.*)$"
)

# Skill "Finding classes and batch scoring" points table.
POINTS = {
    "func": 5,
    "composition": 5,
    "silent-drop": 4,
    "consistency": 4,
    "crash": 3,
    "invalid": 2,
    "lying-warning": 2,
}

UNCLASSIFIED = "unclassified"
_MIN_DISTINCT_CLASSES = 3
_MAX_CONCENTRATION = 0.5


@dataclass(frozen=True)
class CaseHeader:
    """One parsed ``-- CASE...:`` header line."""

    source: str  # dialect stem from the filename, e.g. "postgresql"
    status: str  # "open" | "fixed" | "limit" (untagged defaults to "fixed")
    klass: str  # a POINTS key, or UNCLASSIFIED
    desc: str
    path: str = ""
    lineno: int = 0


def source_from_filename(path: Path) -> str:
    """``challenge_postgresql.sql`` -> ``"postgresql"``."""
    stem = path.stem
    prefix = "challenge_"
    return stem[len(prefix) :] if stem.startswith(prefix) else stem


def parse_header_line(
    line: str, source: str = "", path: str = "", lineno: int = 0
) -> CaseHeader | None:
    """Parse one line; ``None`` if it is not a ``-- CASE...:`` header."""
    match = _HEADER_RE.match(line.rstrip("\n"))
    if match is None:
        return None
    status = match.group("status") or "fixed"
    klass = match.group("klass") or UNCLASSIFIED
    return CaseHeader(
        source=source,
        status=status,
        klass=klass,
        desc=match.group("desc"),
        path=path,
        lineno=lineno,
    )


def parse_file(path: Path) -> list[CaseHeader]:
    source = source_from_filename(path)
    headers = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        header = parse_header_line(line, source=source, path=str(path), lineno=i)
        if header is not None:
            headers.append(header)
    return headers


def parse_corpus(directory: Path) -> list[CaseHeader]:
    headers: list[CaseHeader] = []
    for path in sorted(directory.glob("challenge_*.sql")):
        headers.extend(parse_file(path))
    return headers


def format_report(headers: list[CaseHeader]) -> str:
    lines = [f"Total cases: {len(headers)}", ""]
    lines.append("By status:")
    for status, count in sorted(Counter(h.status for h in headers).items()):
        lines.append(f"  {status}: {count}")
    lines.append("")
    lines.append("By class:")
    for klass, count in sorted(Counter(h.klass for h in headers).items()):
        lines.append(f"  {klass}: {count}")
    lines.append("")
    lines.append("By source:")
    for source, count in sorted(Counter(h.source for h in headers).items()):
        lines.append(f"  {source}: {count}")
    return "\n".join(lines)


@dataclass(frozen=True)
class BatchScore:
    points_by_class: dict[str, int]
    total_points: int
    distinct_classes: int
    unclassified_excluded: int
    violations: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations


def score_batch(headers: list[CaseHeader]) -> BatchScore:
    """Score a set of newly-added ``[open]`` cases against the A9 rules.
    Cases with no ``[class=...]`` tag (``UNCLASSIFIED``) are excluded from
    both the point total and the distinct-class count."""
    classified = [h for h in headers if h.klass != UNCLASSIFIED]
    unclassified_excluded = len(headers) - len(classified)

    points_by_class: dict[str, int] = {}
    for h in classified:
        points_by_class[h.klass] = points_by_class.get(h.klass, 0) + POINTS.get(
            h.klass, 0
        )

    total = sum(points_by_class.values())
    distinct = len(points_by_class)
    violations: list[str] = []

    unknown_classes = sorted({h.klass for h in classified} - set(POINTS))
    for klass in unknown_classes:
        violations.append(f"unknown class '{klass}' (not in the points table)")

    if distinct < _MIN_DISTINCT_CLASSES:
        violations.append(
            f"only {distinct} distinct class(es) scored "
            f"(need >= {_MIN_DISTINCT_CLASSES}): {sorted(points_by_class)}"
        )

    if total > 0:
        for klass, pts in sorted(points_by_class.items()):
            share = pts / total
            if share > _MAX_CONCENTRATION:
                violations.append(
                    f"class '{klass}' is {share:.0%} of batch points "
                    f"({pts}/{total}) — exceeds the 50% concentration cap"
                )

    return BatchScore(
        points_by_class=points_by_class,
        total_points=total,
        distinct_classes=distinct,
        unclassified_excluded=unclassified_excluded,
        violations=violations,
    )


# --- --batch-since: git-diff-derived added cases ----------------------------

_NEW_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_case_headers_from_diff(diff_text: str) -> list[CaseHeader]:
    """Parse ``-- CASE...:`` headers off every added (``+``) line of a
    unified git diff. Exposed separately from :func:`added_cases_since` so
    batch scoring is testable without a real git repo — inject a diff string
    (or, more directly, a list of :class:`CaseHeader` straight into
    :func:`score_batch`)."""
    headers: list[CaseHeader] = []
    path: str | None = None
    in_hunk = False
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git ") or raw.startswith("index "):
            in_hunk = False
            continue
        new_file_match = _NEW_FILE_RE.match(raw)
        if new_file_match:
            path = new_file_match.group(1)
            in_hunk = False
            continue
        if raw.startswith("--- "):
            continue
        if _HUNK_RE.match(raw):
            in_hunk = True
            continue
        if not in_hunk or path is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            source = source_from_filename(Path(path))
            header = parse_header_line(raw[1:], source=source, path=path)
            if header is not None:
                headers.append(header)
        # removed/context lines carry no new headers; nothing to do.
    return headers


def _git_diff(ref: str, root: Path, paths: list[str]) -> str:
    result = subprocess.run(
        ["git", "diff", ref, "--", *paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def added_cases_since(ref: str, root: Path, directory: Path) -> list[CaseHeader]:
    """Cases added in ``directory`` since ``ref`` (committed history plus
    staged/working-tree changes — the batch being scored need not be
    committed yet)."""
    try:
        rel_dir = directory.resolve().relative_to(root.resolve())
    except ValueError:
        rel_dir = directory
    diff_text = _git_diff(ref, root, [str(rel_dir)])
    return added_case_headers_from_diff(diff_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        type=Path,
        default=_DEFAULT_DIR,
        help="challenge fixtures directory (default: tests/fixtures/challenge)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_ROOT,
        help="git repo root to run diff in (default: this repo)",
    )
    parser.add_argument(
        "--batch-since",
        metavar="REF",
        default=None,
        help="score [open] cases added since REF against the A9 batch rules",
    )
    args = parser.parse_args(argv)

    headers = parse_corpus(args.dir)
    print(format_report(headers))

    if args.batch_since is None:
        return 0

    print()
    print(f"Batch scoring (open cases added since {args.batch_since}):")
    added = added_cases_since(args.batch_since, args.root, args.dir)
    open_added = [h for h in added if h.status == "open"]
    score = score_batch(open_added)

    print(f"  cases added: {len(open_added)}")
    if score.unclassified_excluded:
        print(f"  unclassified (excluded from scoring): {score.unclassified_excluded}")
    print(
        f"  total points: {score.total_points} across "
        f"{score.distinct_classes} class(es)"
    )
    for klass, pts in sorted(score.points_by_class.items()):
        print(f"    {klass}: {pts}")

    if score.violations:
        print("  VIOLATIONS:")
        for violation in score.violations:
            print(f"    - {violation}")
        return 1

    print("  OK: batch rules satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
