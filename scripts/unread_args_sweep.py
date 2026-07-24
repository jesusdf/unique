#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unread-args sweep (audit 2026-07-24 T1 / brief B2).

Runs the standard fixtures through the transpiler with the unread-args
tripwire in ``warn`` mode and prints the unique ``(NodeType, arg)`` pairs a
``_convert_*`` left on the floor. That list seeds RED clause-level challenge
cases (see the challenge-corpus skill, "Where to hunt") and drives the
per-node-type allowlist in ``unique.core.converter._unread_args``.

Usage::

    python scripts/unread_args_sweep.py --sweep          # fixtures + challenge
    python scripts/unread_args_sweep.py --sweep --verbose # + first-seen site
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

# Default mode: the tripwire must be on for the sweep to see anything.
os.environ.setdefault("UNIQUE_UNREAD_ARGS", "warn")

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from unique.core.transpiler import Transpiler  # noqa: E402

_TARGETS = ("tsql", "oracle", "postgresql", "mysql")
_PAIR_RE = re.compile(r"unread sqlglot arg '([^']+)' on (\w+)")


def _detect_src(path: pathlib.Path) -> str | None:
    low = path.name.lower()
    if "sqlserver" in low or "tsql" in low or "mssql" in low:
        return "tsql"
    if "oracle" in low or "plsql" in low:
        return "oracle"
    if "postgres" in low or "postgresql" in low or low.endswith("_pg.sql"):
        return "postgresql"
    if "mysql" in low:
        return "mysql"
    return None


def _fixture_files() -> list[pathlib.Path]:
    fx = _ROOT / "tests" / "fixtures"
    out: list[pathlib.Path] = []
    for sub in ("sql", "corpus", "real_world", "challenge"):
        d = fx / sub
        if d.is_dir():
            out.extend(sorted(d.rglob("*.sql")))
    return out


def sweep(verbose: bool) -> int:
    transpiler = Transpiler()
    pairs: dict[tuple[str, str], str] = {}
    counts: dict[tuple[str, str], int] = {}
    for path in _fixture_files():
        sql = path.read_text(encoding="utf-8", errors="ignore")
        src = _detect_src(path)
        sources = (src,) if src else _TARGETS
        for source in sources:
            for target in _TARGETS:
                if source == target:
                    continue
                try:
                    result = transpiler.transpile(sql, source=source, target=target)
                except Exception:
                    continue
                for w in result.warnings:
                    if w.feature != "unread_args":
                        continue
                    m = _PAIR_RE.search(w.message)
                    if m is None:
                        continue
                    key = (m.group(2), m.group(1))  # (NodeType, arg)
                    counts[key] = counts.get(key, 0) + 1
                    pairs.setdefault(key, f"{path.name} [{source}->{target}]")

    if not pairs:
        print("No unread-args residue over the fixture corpus.")
        return 0

    print(f"Unique (NodeType, arg) pairs with unread residue: {len(pairs)}\n")
    for (node_type, arg), where in sorted(pairs.items()):
        line = f"  {node_type:<22} {arg:<20} x{counts[(node_type, arg)]}"
        if verbose:
            line += f"    first: {where}"
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="run the fixture corpus and print unique (NodeType, arg) pairs",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="also print the first fixture/direction that produced each pair",
    )
    args = parser.parse_args()
    if not args.sweep:
        parser.print_help()
        return 2
    return sweep(args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
