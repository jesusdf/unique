# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Transpile a corpus and execute every output against the real target engine.

This turns manual "run a query and see if it breaks" into an automated sweep:
each corpus statement is transpiled to every valid target and the output is
executed on that engine (rolled back), so any engine complaint is a caught bug.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from helpers.corpus import LIVE_ENGINES, CorpusEntry, targets_for

_ENV = {
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
}


@dataclass(frozen=True)
class Failure:
    entry_id: str
    source: str
    target: str
    error: str
    output: str


def urls_from_env() -> dict[str, str]:
    """Map each engine to its configured URL (absent engines are skipped)."""
    return {eng: os.environ[var] for eng, var in _ENV.items() if os.environ.get(var)}


def run_sweep(
    entries: list[CorpusEntry], urls: dict[str, str]
) -> tuple[list[Failure], int, list[str]]:
    """Sweep *entries* against the engines in *urls*.

    Returns ``(failures, executed_count, skipped_targets)``. One validator (and
    connection) is reused per target for the whole sweep.
    """
    from helpers.live_validation import make_validator

    from unique.core.transpiler import transpile

    validators = {}
    skipped: list[str] = []
    for tgt in LIVE_ENGINES:
        url = urls.get(tgt)
        if not url:
            skipped.append(tgt)
            continue
        try:
            validators[tgt] = make_validator(tgt, url)
        except Exception as e:  # pragma: no cover - driver/DB unavailable
            skipped.append(f"{tgt} ({str(e)[:40]})")

    failures: list[Failure] = []
    executed = 0
    try:
        for entry in entries:
            for tgt in targets_for(entry.source):
                validator = validators.get(tgt)
                if validator is None:
                    continue
                try:
                    output = transpile(entry.sql, entry.source, tgt).sql
                except Exception as exc:  # a transpiler crash is a bug too
                    failures.append(
                        Failure(
                            entry.id,
                            entry.source,
                            tgt,
                            f"TRANSPILE {type(exc).__name__}: {exc}",
                            "",
                        )
                    )
                    continue
                executed += 1
                verdict = validator.validate(output)
                if not verdict.ok:
                    failures.append(
                        Failure(
                            entry.id,
                            entry.source,
                            tgt,
                            str(verdict.error).split("\n")[0],
                            output,
                        )
                    )
    finally:
        for validator in validators.values():
            validator.close()
    return failures, executed, skipped
