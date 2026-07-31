# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Shared reader for the ``tests/fixtures/challenge`` corpus.

One place that turns the four challenge fixtures into structured
:class:`ChallengeCase` entries (id, source, status, class, executable SQL), so
the auto-enrollment FE harness (``test_challenge_results_live.py``) and any
future consumer share a single parser instead of re-splitting the fixtures.

The block-splitting itself is *not* re-implemented here: it reuses the
authoritative ``-- CASE`` splitter in ``tests.integration.test_challenge``
(``_cases`` / ``_status`` / ``_slug`` / ``_SOURCE_BY_FILE``) — the same reuse
``test_challenge_live.py`` already relies on — so there is exactly one splitter
in the tree. This module only adds the case *model* and the enrollment
predicates (class tag, executable-SQL extraction, self-containment).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from tests.integration.test_challenge import _SOURCE_BY_FILE, _cases, _slug, _status

# sqlglot read-dialect per source engine (mirrors output_gate._SQLGLOT_DIALECT).
_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}

_CLASS_RE = re.compile(r"^-- CASE(?:\[[a-z]+\])?\[class=([a-z-]+)\]:")


@dataclass(frozen=True)
class ChallengeCase:
    """One ``-- CASE`` block, structured.

    ``id`` is the stable ``xx-yyy`` slug; ``status`` is ``open``/``fixed``/
    ``limit``; ``klass`` is the ``[class=…]`` tag if present else ``None``;
    ``sql`` is the executable body (its ``--`` header/comment lines stripped).
    """

    id: str
    fixture: str
    source: str
    status: str
    klass: str | None
    sql: str


def _class_of(block: str) -> str | None:
    m = _CLASS_RE.match(block.strip())
    return m.group(1) if m else None


def _exec_sql(block: str) -> str:
    """The executable SQL of a case block (its ``--`` header/comments removed)."""
    return "\n".join(
        ln for ln in block.splitlines() if not ln.lstrip().startswith("--")
    ).strip()


def load_challenge_cases() -> list[ChallengeCase]:
    """Every ``-- CASE`` block across the four fixtures, as structured entries."""
    cases: list[ChallengeCase] = []
    for fixture, source in _SOURCE_BY_FILE.items():
        for block in _cases(fixture):
            cases.append(
                ChallengeCase(
                    id=_slug(block),
                    fixture=fixture,
                    source=source,
                    status=_status(block),
                    klass=_class_of(block),
                    sql=_exec_sql(block),
                )
            )
    return cases


def is_self_contained(sql: str, source: str) -> bool:
    """True when a SELECT needs no pre-existing table to execute.

    Self-contained = no top-level ``FROM`` of a real table: ``FROM DUAL``,
    derived tables (``FROM (SELECT …)``), ``VALUES`` and CTE references are all
    fine; a reference to any other named table is not. Parsed structurally with
    sqlglot (robust against ``FROM`` inside ``EXTRACT``/``SUBSTRING``/``TRIM``,
    which a bare regex would misread); if the source will not parse, the case is
    treated as NOT self-contained (conservative — an unparseable source degrades
    to a warned carrier at transpile time and would be skipped anyway).
    """
    try:
        tree = sqlglot.parse_one(sql, read=_SQLGLOT_DIALECT.get(source, source))
    except Exception:
        return False
    if tree is None:
        return False
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name and name != "dual" and name not in cte_names:
            return False
    return True
