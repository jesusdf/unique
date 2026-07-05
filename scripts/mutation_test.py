#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Lightweight AST mutation tester for measuring test-assertion quality.

For each target module it applies one small mutation at a time (swap a
comparison/boolean/arithmetic operator, flip a bool, bump an int, drop a
``not``), runs a fast test selection, and records whether any test *killed* the
mutant. The mutation score and the list of *survivors* (mutations no test
caught) are a precise, objective map of where the tests assert nothing — what
line coverage cannot see (a covered line may still be un-asserted).

Usage:
    python scripts/mutation_test.py src/unique/core/converter/emit.py [more.py ...]
    python scripts/mutation_test.py <module> --tests "tests/unit/core" --limit 50

Exit code is the number of surviving mutants (0 = every mutation caught).
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import time
from pathlib import Path

_CMP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.Gt: ast.LtE,
    ast.LtE: ast.Gt, ast.GtE: ast.Lt, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
}
_BOOL = {ast.And: ast.Or, ast.Or: ast.And}
_ARITH = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}

_DEFAULT_TESTS = ["tests/unit/core", "tests/integration/test_cross_dialect.py"]


def _sites(tree: ast.Module) -> list[tuple[str, object, object]]:
    """Collect (description, apply, restore) one-node mutation sites."""
    sites: list[tuple[str, object, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in _CMP:
                    nk, ok = _CMP[type(op)], type(op)
                    sites.append((
                        f"L{node.lineno} cmp {ok.__name__}->{nk.__name__}",
                        (lambda n, i, k: lambda: n.ops.__setitem__(i, k()))(node, i, nk),
                        (lambda n, i, k: lambda: n.ops.__setitem__(i, k()))(node, i, ok),
                    ))
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            nk, ok = _BOOL[type(node.op)], type(node.op)
            sites.append((
                f"L{node.lineno} bool {ok.__name__}->{nk.__name__}",
                (lambda n, k: lambda: setattr(n, "op", k()))(node, nk),
                (lambda n, k: lambda: setattr(n, "op", k()))(node, ok),
            ))
        elif isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
            nk, ok = _ARITH[type(node.op)], type(node.op)
            sites.append((
                f"L{node.lineno} arith {ok.__name__}->{nk.__name__}",
                (lambda n, k: lambda: setattr(n, "op", k()))(node, nk),
                (lambda n, k: lambda: setattr(n, "op", k()))(node, ok),
            ))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append((
                f"L{node.lineno} drop-not",
                (lambda n: lambda: setattr(n, "op", ast.UAdd()))(node),
                (lambda n: lambda: setattr(n, "op", ast.Not()))(node),
            ))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            v = node.value
            sites.append((
                f"L{node.lineno} const {v}->{not v}",
                (lambda n, x: lambda: setattr(n, "value", x))(node, not v),
                (lambda n, x: lambda: setattr(n, "value", x))(node, v),
            ))
        elif isinstance(node, ast.Constant) and isinstance(node.value, int):
            v = node.value
            sites.append((
                f"L{node.lineno} int {v}->{v + 1}",
                (lambda n, x: lambda: setattr(n, "value", x))(node, v + 1),
                (lambda n, x: lambda: setattr(n, "value", x))(node, v),
            ))
    return sites


def _run(tests: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *tests,
         "-q", "-x", "--tb=no", "-p", "no:cacheprovider", "--no-header"],
        capture_output=True, text=True,
    )


def mutate_module(path: Path, tests: list[str], limit: int | None) -> list[str]:
    """Mutate *path* one node at a time; return the surviving-mutation list."""
    original = path.read_text()
    tree = ast.parse(original)
    sites = _sites(tree)
    if limit:
        sites = sites[:limit]
    print(f"\n=== {path}  ({len(sites)} mutants) ===", flush=True)
    killed = survived = 0
    survivors: list[str] = []
    t0 = time.time()
    try:
        for i, (desc, apply, restore) in enumerate(sites):
            apply()
            mutated = ast.unparse(tree)
            restore()
            path.write_text(mutated)
            result = _run(tests)
            if result.returncode != 0:
                killed += 1
            else:
                survived += 1
                survivors.append(desc)
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(sites)} killed={killed} survived={survived}"
                      f" ({time.time() - t0:.0f}s)", flush=True)
    finally:
        path.write_text(original)
    total = killed + survived
    score = killed / total if total else 1.0
    print(f"  score {killed}/{total} killed ({score:.0%}), {survived} survivors,"
          f" {time.time() - t0:.0f}s", flush=True)
    return survivors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="+", help="source files to mutate")
    parser.add_argument("--tests", nargs="*", default=_DEFAULT_TESTS,
                        help="pytest selection run per mutant")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap mutants per module (quick runs)")
    args = parser.parse_args()

    baseline = _run(args.tests)
    if baseline.returncode != 0:
        print("FAIL: baseline test selection is not green; aborting.")
        print(baseline.stdout[-800:])
        return 2

    all_survivors: dict[str, list[str]] = {}
    for mod in args.modules:
        all_survivors[mod] = mutate_module(Path(mod), args.tests, args.limit)

    print("\n=== SURVIVORS (mutations no test caught) ===")
    total = 0
    for mod, survivors in all_survivors.items():
        if survivors:
            print(f"\n{mod}:")
            for s in survivors:
                print(f"  {s}")
            total += len(survivors)
    print(f"\nTOTAL survivors: {total}")
    return total


if __name__ == "__main__":
    raise SystemExit(main())
