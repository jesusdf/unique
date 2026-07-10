#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Fetch a curated PostgreSQL-source test corpus from the PG regression suite.

Downloads selected files from ``src/test/regress/sql/`` of the PostgreSQL
repository at a pinned tag, strips the psql-specific noise (backslash
meta-commands; ``COPY … FROM stdin`` statements together with their inline
data blocks), prepends an attribution header (the files are under the
permissive PostgreSQL License), and writes plain-SQL files ready for
``scripts/validity_sweep.py --from postgresql``.

The default selection is the portable-SQL core of the suite; engine-internal
suites (catalog/statistics/privilege tests) are deliberately excluded. Known
residual noise: psql variable substitution (``:'var'``) is NOT rewritten —
the default files barely use it, and the transpiler degrades an unparseable
source statement to an honest carrier.

Usage:
    scripts/fetch_pg_corpus.py [--ref REL_17_5] [--out fixtures-corpus/pg] [FILE ...]
"""

from __future__ import annotations

import argparse
import re
import urllib.request
from pathlib import Path

RAW_URL = "https://raw.githubusercontent.com/postgres/postgres/{ref}/src/test/regress/sql/{name}.sql"
DEFAULT_REF = "REL_17_5"
DEFAULT_OUT = Path("fixtures-corpus/pg")

#: The portable-SQL core of the regression suite: DML/DDL/queries/procedural
#: constructs that make sense as transpiler *source* material.
DEFAULT_FILES = (
    "insert",
    "update",
    "delete",
    "join",
    "select",
    "select_distinct",
    "select_having",
    "aggregates",
    "window",
    "case",
    "union",
    "subselect",
    "with",
    "triggers",
    "plpgsql",
)

_COPY_STDIN_RE = re.compile(r"^\s*copy\b.*\bfrom\s+stdin\b", re.IGNORECASE)

_HEADER = """\
-- Curated from the PostgreSQL regression suite ({ref}), file {name}.sql:
-- https://github.com/postgres/postgres/blob/{ref}/src/test/regress/sql/{name}.sql
-- Portions Copyright (c) 1996-2026, PostgreSQL Global Development Group
-- Portions Copyright (c) 1994, The Regents of the University of California
-- Distributed under the PostgreSQL License (see the project's COPYRIGHT file).
-- psql meta-commands and COPY-FROM-stdin data blocks were stripped by
-- scripts/fetch_pg_corpus.py; the SQL itself is unmodified.

"""


def strip_psql_noise(sql: str) -> str:
    """Strip psql client constructs, keeping every SQL line verbatim.

    Backslash meta-commands (``\\d``, ``\\set``, …) are line-oriented client
    commands with no server-side meaning — dropped. A ``COPY … FROM stdin``
    statement cannot be separated from the raw data lines that follow it, so
    the statement and its data are dropped whole, through the ``\\.``
    terminator (inside the block nothing is interpreted, mirroring psql).
    """
    kept: list[str] = []
    in_copy_data = False
    for line in sql.splitlines(keepends=True):
        if in_copy_data:
            if line.strip() == "\\.":
                in_copy_data = False
            continue
        if _COPY_STDIN_RE.match(line):
            in_copy_data = True
            continue
        if line.lstrip().startswith("\\"):
            continue
        kept.append(line)
    return "".join(kept)


def fetch_one(name: str, ref: str, out_dir: Path) -> Path:
    """Download, curate and write one regression file; return the output path."""
    url = RAW_URL.format(ref=ref, name=name)
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    curated = _HEADER.format(ref=ref, name=name) + strip_psql_noise(raw)
    out_path = out_dir / f"{name}.sql"
    out_path.write_text(curated, encoding="utf-8")
    return out_path


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files", nargs="*", default=None, help="regression file names (no .sql)"
    )
    parser.add_argument(
        "--ref", default=DEFAULT_REF, help=f"git tag/branch (default {DEFAULT_REF})"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output dir (default {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    names = tuple(args.files) or DEFAULT_FILES
    args.out.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = fetch_one(name, args.ref, args.out)
        print(f"fetched {name}.sql -> {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
