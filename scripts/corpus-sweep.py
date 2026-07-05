#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Transpile the corpus and execute every output against the real engines.

The automated form of "run a query and see if it breaks": it sweeps the whole
corpus (and, with --private, the gitignored real-world fixtures) against whatever
engines are configured, then prints a report grouped by error signature so new
bugs are easy to triage.

    UNIQUE_TEST_PG_URL=...  UNIQUE_TEST_MYSQL_URL=...  \\
    UNIQUE_TEST_ORACLE_URL=...  UNIQUE_TEST_MSSQL_URL=...  \\
    python scripts/corpus-sweep.py [--private]

Exit code is the number of *unexpected* failures (0 = clean), so it can gate CI.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

logging.disable(logging.CRITICAL)

from helpers.corpus import (  # noqa: E402
    CorpusEntry,
    load_corpus,
    load_private_statements,
)
from helpers.corpus_sweep import run_sweep, urls_from_env  # noqa: E402


def _signature(error: str) -> str:
    """Collapse an engine error to a coarse signature for grouping."""
    e = error.lower()
    m = re.search(r"ora-\d+", e)
    if m:
        return m.group(0).upper()
    m = re.search(r"\((\d+)", error)  # MySQL / DB-Lib numeric codes
    if m:
        return f"code {m.group(1)}"
    m = re.search(r"function ([a-z_]+)\(", e)
    if m:
        return f"missing function {m.group(1)}"
    if "does not exist" in e:
        return e.split("does not exist")[0].strip()[:40] + " does not exist"
    return error.split("\n")[0][:50]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private",
        action="store_true",
        help="also sweep the gitignored fixtures-private/ scripts",
    )
    args = parser.parse_args()

    urls = urls_from_env()
    if not urls:
        print("No UNIQUE_TEST_*_URL configured; nothing to sweep.", file=sys.stderr)
        return 0

    entries: list[CorpusEntry] = load_corpus()
    if args.private:
        priv = list(load_private_statements())
        print(f"including {len(priv)} private-fixture statements")
        entries += priv

    xfail = {e.id: e.xfail for e in entries}
    print(f"sweeping {len(entries)} entries against {sorted(urls)} ...\n")
    failures, executed, skipped = run_sweep(entries, urls)

    expected = [f for f in failures if f.target in xfail.get(f.entry_id, frozenset())]
    unexpected = [
        f for f in failures if f.target not in xfail.get(f.entry_id, frozenset())
    ]

    print(f"executed {executed} (entry x target); skipped targets: {skipped}")
    print(
        f"failures: {len(failures)}  (expected/xfail: {len(expected)}, "
        f"UNEXPECTED: {len(unexpected)})\n"
    )

    if unexpected:
        print("=== UNEXPECTED failures (new bugs / regressions) ===")
        by_sig: dict[str, list] = defaultdict(list)
        for f in unexpected:
            by_sig[_signature(f.error)].append(f)
        for sig, group in sorted(by_sig.items(), key=lambda kv: -len(kv[1])):
            print(f"\n[{len(group)}] {sig}")
            for f in group[:4]:
                print(f"    {f.source} -> {f.target}  ({f.entry_id})")
                print(f"      out: {f.output[:90]!r}")
                print(f"      err: {f.error[:90]}")

    if expected:
        print("\n=== documented gaps hit (xfail), by construct ===")
        by_pair = Counter((f.entry_id, f.target) for f in expected)
        for (eid, tgt), _ in sorted(by_pair.items()):
            print(f"    {eid} -> {tgt}")

    return len(unexpected)


if __name__ == "__main__":
    raise SystemExit(main())
