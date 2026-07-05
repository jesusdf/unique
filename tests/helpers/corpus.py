# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Loader for the SQL corpus swept by the live-execution tests.

The corpus lives in ``tests/fixtures/corpus/<dialect>.sql``. Each file holds
statements — table-less or otherwise self-contained, so the transpiled output
executes on a target engine without a pre-seeded schema — separated by a line
that is exactly ``-- @@@``. Every file is tagged with the source dialect(s) it is
swept from.

``load_private_statements`` additionally splits the (gitignored) real-world
fixtures under ``fixtures-private/`` into statements, for ad-hoc local sweeps.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_CORPUS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
_PRIVATE_DIR = Path(__file__).resolve().parents[2] / "fixtures-private"

# The four engines that can execute transpiled output (SQLite is import-only,
# never a target).
LIVE_ENGINES: tuple[str, ...] = ("tsql", "oracle", "postgresql", "mysql")

# corpus file -> the source dialect(s) it is swept from.
_SOURCES: dict[str, tuple[str, ...]] = {
    "portable.sql": ("tsql", "postgresql", "mysql"),
    "tsql.sql": ("tsql",),
    "oracle.sql": ("oracle",),
    "postgresql.sql": ("postgresql",),
    "mysql.sql": ("mysql",),
    "sqlite.sql": ("sqlite",),
}

# Real-world private fixtures and their source dialect (local sweeps only).
_PRIVATE_FILES: dict[str, str] = {
    "test.sql": "tsql",
    "bigtest.sql": "oracle",
}

_SEP_RE = re.compile(r"(?m)^-- @@@[ \t]*$")
# "-- @xfail: mysql oracle  # optional reason" as the first line of an entry
# (a split block keeps the leading newline, so allow leading whitespace).
_XFAIL_RE = re.compile(r"(?m)\A\s*-- @xfail:[ \t]*([a-z ]+?)[ \t]*(?:#.*)?$\n?")


@dataclass(frozen=True)
class CorpusEntry:
    """One corpus statement tagged with the source dialect to read it as.

    ``xfail`` lists targets the statement is a *known* documented gap for (a
    function/type with no faithful mapping yet); the sweep expects those to fail
    and flags them if they start passing so the annotation can be removed.
    """

    id: str
    sql: str
    source: str
    xfail: frozenset[str] = frozenset()


def _is_only_comments(block: str) -> bool:
    """True when *block* has no executable line (all lines blank or ``--``)."""
    for line in block.splitlines():
        s = line.strip()
        if s and not s.startswith("--"):
            return False
    return True


def _parse_block(block: str) -> tuple[str, frozenset[str]]:
    """Split a corpus block into (sql, xfail-targets), stripping the directive."""
    xfail: frozenset[str] = frozenset()
    m = _XFAIL_RE.match(block)
    if m:
        xfail = frozenset(m.group(1).split())
        block = block[m.end() :]
    return block.strip(), xfail


def _split(text: str) -> list[tuple[str, frozenset[str]]]:
    out = []
    for b in _SEP_RE.split(text):
        if not b.strip() or _is_only_comments(b):
            continue
        sql, xfail = _parse_block(b)
        if sql:
            out.append((sql, xfail))
    return out


def targets_for(source: str) -> tuple[str, ...]:
    """Live engines to sweep a *source* statement to (all but the source)."""
    return tuple(t for t in LIVE_ENGINES if t != source)


def load_corpus() -> list[CorpusEntry]:
    """Load the committed corpus as a flat list of (source-tagged) entries."""
    entries: list[CorpusEntry] = []
    for fname, sources in _SOURCES.items():
        path = _CORPUS_DIR / fname
        if not path.exists():
            continue
        for i, (stmt, xfail) in enumerate(_split(path.read_text())):
            for src in sources:
                entries.append(
                    CorpusEntry(id=f"{fname}#{i}", sql=stmt, source=src, xfail=xfail)
                )
    return entries


def load_private_statements() -> Iterator[CorpusEntry]:
    """Yield statements from the gitignored ``fixtures-private/`` scripts, if any.

    Uses the transpiler's own statement splitter. Absent in CI (the directory is
    gitignored), so callers must treat an empty result as "not available".
    """
    from tests.functional_equivalence.engine_runner import split_statements

    for fname, src in _PRIVATE_FILES.items():
        path = _PRIVATE_DIR / fname
        if not path.exists():
            continue
        text = path.read_text(errors="replace")
        for i, stmt in enumerate(split_statements(text, src)):
            if stmt.strip():
                yield CorpusEntry(id=f"private/{fname}#{i}", sql=stmt, source=src)
