# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Differential result testing over the corpus.

The corpus sweep proves the transpiled output *executes*; this proves it returns
the *same answer*. Each result-comparable corpus SELECT is executed on its source
engine and its transpiled output on each target engine, and the normalized result
sets are compared. A divergence is a semantic bug that syntactic validity misses
(argument order swapped, precedence changed, off-by-one, ``+`` vs concat, …).
"""

from __future__ import annotations

import contextlib
import datetime
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from helpers.corpus import LIVE_ENGINES, CorpusEntry, targets_for

_ENV = {
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
}
# Functions whose value depends on the wall clock / randomness — the two engines
# legitimately differ, so these entries are executed but not result-compared.
_NONDETERMINISTIC = re.compile(
    r"(?i)\b(NOW|SYSDATE|SYSTIMESTAMP|CURDATE|CURRENT_DATE|CURRENT_TIMESTAMP|"
    r"GETDATE|SYSDATETIME|RANDOM|RAND|NEWID|UUID|SYS_GUID)\b|DATE\('now'\)"
)


@dataclass(frozen=True)
class Mismatch:
    entry_id: str
    source: str
    target: str
    source_result: Any
    target_result: Any
    output: str


def normalize_cell(v: Any) -> Any:
    """Canonicalize a cell so equal values compare equal across engines."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (Decimal, float)):
        return round(float(v), 6)
    if isinstance(v, int):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, datetime.datetime):
        # A DATE often materializes as a midnight datetime (Oracle); collapse it
        # to the date so DATE-vs-DATETIME rendering is not a false mismatch.
        if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0):
            return v.date().isoformat()
        return v.isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    return str(v).strip()


def normalize_rows(rows: list[tuple], *, empty_as_null: bool = False) -> list[tuple]:
    # Order-insensitive: compare the multiset of rows (ORDER BY differences and
    # engine default ordering must not cause a false mismatch).
    # ``empty_as_null`` collapses '' into NULL — Oracle folds empty VARCHAR to
    # NULL intrinsically, so when ONE side of a comparison is Oracle the two are
    # indistinguishable there and both sides must be folded alike (maintainer
    # decision 2026-07-30). The sort key tolerates the None/str mix this creates.
    out = []
    for row in rows:
        cells = tuple(normalize_cell(c) for c in row)
        if empty_as_null:
            cells = tuple(None if c == "" else c for c in cells)
        out.append(cells)
    return sorted(out, key=lambda r: [(c is None, str(c)) for c in r])


def is_comparable(entry: CorpusEntry) -> bool:
    """A single-statement, deterministic, row-returning SELECT."""
    sql = entry.sql.strip()
    return (
        sql.upper().startswith("SELECT")
        and ";" not in sql.rstrip(";")
        and not _NONDETERMINISTIC.search(sql)
    )


def urls_from_env() -> dict[str, str]:
    return {eng: os.environ[var] for eng, var in _ENV.items() if os.environ.get(var)}


def run_result_diff(
    entries: list[CorpusEntry], urls: dict[str, str]
) -> tuple[list[Mismatch], int, list[str]]:
    """Compare source vs target results for every comparable entry.

    Returns ``(mismatches, pairs_checked, engines_used)``. Execution *failures*
    are ignored here — those are the corpus sweep's job; this only compares when
    both sides executed.
    """
    from tests.functional_equivalence.engine_runner import connect
    from unique.core.transpiler import transpile

    conns = {}
    for eng in LIVE_ENGINES:
        url = urls.get(eng)
        if not url:
            continue
        with contextlib.suppress(Exception):  # driver/DB unavailable
            conns[eng] = connect(eng, url)

    def run(engine: str, sql: str) -> tuple[Any, str | None]:
        cur = conns[engine].cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            conns[engine].rollback()
            return normalize_rows(rows), None
        except Exception as exc:
            with contextlib.suppress(Exception):
                conns[engine].rollback()
            return None, str(exc).splitlines()[0][:80]

    mismatches: list[Mismatch] = []
    checked = 0
    try:
        for entry in entries:
            if not is_comparable(entry) or entry.source not in conns:
                continue
            source_result, err = run(entry.source, entry.sql)
            if err is not None:
                continue
            for target in targets_for(entry.source):
                if target not in conns:
                    continue
                output = transpile(entry.sql, entry.source, target).sql
                target_result, terr = run(target, output)
                if terr is not None:
                    continue
                checked += 1
                if source_result != target_result:
                    mismatches.append(
                        Mismatch(
                            entry.id,
                            entry.source,
                            target,
                            source_result,
                            target_result,
                            output,
                        )
                    )
    finally:
        for conn in conns.values():
            with contextlib.suppress(Exception):
                conn.close()
    return mismatches, checked, sorted(conns)
