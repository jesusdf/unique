#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Find SILENT output gaps: statements the live target engine rejects that the
transpiler shipped with NO carrier and NO warning (sqlglot-leniency escapes
and silent mangles). A development-facing refinement tool.

Usage::

    UNIQUE_TEST_PG_URL=... python scripts/discover_silent_gaps.py \\
        [corpus.sql] [--source pg] [--target pg]

CRITICAL: uses the dollar-quote-aware splitter (``tests.helpers.sql_split``),
never a naive ``;\\n`` split — the latter shreds plpgsql bodies into standalone
``return …`` fragments that are FALSE POSITIVES. This tool also CANNOT see
silent DATA LOSS that stays syntactically valid (the wave-85 class): it
complements, never replaces, the no-silent-loss gates.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.helpers.sql_split import is_executable, split_statements  # noqa: E402
from unique.core.live_validate import validate_statements  # noqa: E402
from unique.core.transpiler import Transpiler  # noqa: E402

_ENV = {
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "corpus",
        nargs="?",
        default=str(REPO_ROOT / "fixtures-corpus" / "pg_corpus_valid.sql"),
    )
    ap.add_argument("--source", default="postgresql")
    ap.add_argument("--target", default="postgresql")
    args = ap.parse_args()

    url = os.environ.get(_ENV[args.target])
    if not url:
        print(f"set {_ENV[args.target]} for the target engine", file=sys.stderr)
        return 2

    corpus = Path(args.corpus).read_text()
    src_stmts = [s for s in split_statements(corpus, args.source) if is_executable(s)]
    tr = Transpiler()
    gaps: list[tuple[str, str]] = []
    for src in src_stmts:
        try:
            result = tr.transpile(src + ";", source=args.source, target=args.target)
        except Exception:  # noqa: BLE001 - a hard failure is not a silent gap
            continue
        if "UNIQUE-" in result.sql or result.warnings:
            continue  # already handled honestly (carrier or warning)
        emitted = [
            s for s in split_statements(result.sql, args.target) if is_executable(s)
        ]
        if not emitted:
            continue
        for st, err in zip(
            emitted, validate_statements(url, args.target, emitted), strict=False
        ):
            if err:
                gaps.append((st[:100].replace("\n", " "), err.splitlines()[0][:60]))

    print(f"SILENT GAPS ({args.source}->{args.target}): {len(gaps)}")
    for err, n in collections.Counter(g[1] for g in gaps).most_common(15):
        print(f"  {n:4d}  {err}")
    print("--- samples ---")
    for st, err in gaps[:12]:
        print(f"  {st!r}  ::  {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
