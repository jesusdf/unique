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
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.GtE: ast.Lt,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}
_BOOL = {ast.And: ast.Or, ast.Or: ast.And}
_ARITH = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}

_DEFAULT_TESTS = ["tests/unit/core", "tests/integration/test_cross_dialect.py"]


# Closure factories (bind their arguments, so the loop variable is not captured).
def _set_compare(node: ast.Compare, idx: int, op_cls: type) -> object:
    return lambda: node.ops.__setitem__(idx, op_cls())


def _set_op(node: ast.AST, op_cls: type) -> object:
    return lambda: setattr(node, "op", op_cls())


def _set_value(node: ast.Constant, value: object) -> object:
    return lambda: setattr(node, "value", value)


def _sites(tree: ast.Module) -> list[tuple[str, object, object]]:
    """Collect (description, apply, restore) one-node mutation sites."""
    sites: list[tuple[str, object, object]] = []
    for node in ast.walk(tree):
        line = node.lineno if hasattr(node, "lineno") else 0
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in _CMP:
                    nk, ok = _CMP[type(op)], type(op)
                    sites.append(
                        (
                            f"L{line} cmp {ok.__name__}->{nk.__name__}",
                            _set_compare(node, i, nk),
                            _set_compare(node, i, ok),
                        )
                    )
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            nk, ok = _BOOL[type(node.op)], type(node.op)
            sites.append(
                (
                    f"L{line} bool {ok.__name__}->{nk.__name__}",
                    _set_op(node, nk),
                    _set_op(node, ok),
                )
            )
        elif isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
            nk, ok = _ARITH[type(node.op)], type(node.op)
            sites.append(
                (
                    f"L{line} arith {ok.__name__}->{nk.__name__}",
                    _set_op(node, nk),
                    _set_op(node, ok),
                )
            )
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append(
                (f"L{line} drop-not", _set_op(node, ast.UAdd), _set_op(node, ast.Not))
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            v = node.value
            sites.append(
                (
                    f"L{line} const {v}->{not v}",
                    _set_value(node, not v),
                    _set_value(node, v),
                )
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, int):
            v = node.value
            sites.append(
                (
                    f"L{line} int {v}->{v + 1}",
                    _set_value(node, v + 1),
                    _set_value(node, v),
                )
            )
    return sites


#: A mutant that hangs a loop or balloons memory must die as a KILLED mutant,
#: not take the runner down ("The hosted runner lost communication with the
#: server", nightly 2026-07-09: a mutated character-scan loop starved the VM).
_MUTANT_TIMEOUT_S = 300
_MUTANT_MEM_BYTES = 4 * 1024**3


def _limit_resources() -> None:  # pragma: no cover - runs in the child process
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (_MUTANT_MEM_BYTES, _MUTANT_MEM_BYTES))


def _run(tests: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *tests,
        "-q",
        "-x",
        "--tb=no",
        "-p",
        "no:cacheprovider",
        "--no-header",
    ]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_MUTANT_TIMEOUT_S,
            preexec_fn=_limit_resources if sys.platform != "win32" else None,
        )
    except subprocess.TimeoutExpired:
        # A hang is a detected (killed) mutant: the behavior change is fatal.
        return subprocess.CompletedProcess(
            args=cmd, returncode=124, stdout="", stderr="mutant timed out"
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
                print(
                    f"  {i + 1}/{len(sites)} killed={killed} survived={survived}"
                    f" ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    finally:
        path.write_text(original)
    total = killed + survived
    score = killed / total if total else 1.0
    print(
        f"  score {killed}/{total} killed ({score:.0%}), {survived} survivors,"
        f" {time.time() - t0:.0f}s",
        flush=True,
    )
    return survivors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="+", help="source files to mutate")
    parser.add_argument(
        "--tests",
        nargs="*",
        default=_DEFAULT_TESTS,
        help="pytest selection run per mutant",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="cap mutants per module (quick runs)"
    )
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
