# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Auto-enrolled differential *execution* over the challenge corpus (audit A10).

``test_challenge_live.py`` compares the VALUES of ~12 hand-curated ``FuncCase``
entries; this generalizes that to the whole corpus **mechanically**. The enrolled
set is derived, never hand-listed:

    every ``[fixed]`` case that is result-comparable (single-statement,
    deterministic SELECT — ``corpus_diff.is_comparable``) and self-contained
    (needs no pre-existing table — ``challenge_cases.is_self_contained``),
    MINUS the named exclusions ledger (``challenge_fe_exclusions.LEDGER``).

For each enrolled case and each target engine: transpile; if the transpile
carries any warning or unsupported entry the pair is SKIPPED (a warned degrade is
the documented, acceptable outcome — the corpus rule, checked live, not from a
static list); otherwise the source SQL runs on its engine, the transpiled output
on the target, and the normalized result sets must match. A value mismatch or a
target-side execution error is a semantic defect and FAILS the test.

Skipped unless at least two engines' ``UNIQUE_TEST_*_URL`` env vars are set, so
the default offline suite stays green; it runs in the syntax-live CI job next to
``test_corpus_results_live.py`` and ``test_challenge_live.py``.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from tests.functional_equivalence.engine_runner import connect
from tests.helpers.challenge_cases import (
    ChallengeCase,
    is_self_contained,
    load_challenge_cases,
)
from tests.helpers.challenge_fe_exclusions import LEDGER
from tests.helpers.corpus import CorpusEntry, targets_for
from tests.helpers.corpus_diff import is_comparable, normalize_rows, urls_from_env
from unique.core.transpiler import transpile

_EXCLUDED = {(e.id, e.sql) for e in LEDGER}


def enrolled_cases() -> list[ChallengeCase]:
    """The mechanically-derived enrolled set (see the module docstring)."""
    out: list[ChallengeCase] = []
    for c in load_challenge_cases():
        if c.status != "fixed":
            continue
        if not is_comparable(CorpusEntry(id=c.id, sql=c.sql, source=c.source)):
            continue
        if not is_self_contained(c.sql, c.source):
            continue
        if (c.id, c.sql) in _EXCLUDED:
            continue
        out.append(c)
    return out


@pytest.mark.integration
def test_enrolled_challenge_outputs_return_same_result() -> None:
    urls = urls_from_env()
    if len(urls) < 2:
        pytest.skip("differential result testing needs >= 2 engine URLs")

    conns: dict[str, Any] = {}
    for eng, url in urls.items():
        with contextlib.suppress(Exception):  # driver/DB unavailable
            conns[eng] = connect(eng, url)
    if len(conns) < 2:
        pytest.skip("could not connect to >= 2 engines")

    def run(engine: str, sql: str) -> tuple[list[tuple] | None, str | None]:
        cur = conns[engine].cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            conns[engine].rollback()
            return normalize_rows(rows), None
        except Exception as exc:  # noqa: BLE001 - reported, then rolled back
            with contextlib.suppress(Exception):
                conns[engine].rollback()
            return None, str(exc).splitlines()[0][:120]

    failures: list[str] = []
    checked = matched = warned = source_skipped = 0
    try:
        for case in enrolled_cases():
            if case.source not in conns:
                continue
            source_rows, serr = run(case.source, case.sql)
            if serr is not None:
                # The case's own source SQL did not execute here — a case-quality
                # issue (e.g. it reads session state), not a transpiler defect.
                # Counted and reported, not failed (matches run_result_diff).
                source_skipped += 1
                continue
            for target in targets_for(case.source):
                if target not in conns:
                    continue
                result = transpile(case.sql, case.source, target)
                if result.warnings or result.unsupported:
                    warned += 1
                    continue
                target_rows, terr = run(target, result.sql)
                if terr is not None:
                    failures.append(
                        f"  [{case.source} -> {target}] {case.id}: EXEC-FAIL\n"
                        f"      error : {terr}\n"
                        f"      output: {result.sql[:120]!r}"
                    )
                    continue
                checked += 1
                if source_rows != target_rows:
                    failures.append(
                        f"  [{case.source} -> {target}] {case.id}: DIFF\n"
                        f"      source: {source_rows}\n"
                        f"      target: {target_rows}\n"
                        f"      output: {result.sql[:120]!r}"
                    )
                else:
                    matched += 1
    finally:
        for conn in conns.values():
            with contextlib.suppress(Exception):
                conn.close()

    if failures:
        pytest.fail(
            f"{len(failures)} enrolled challenge pair(s) diverged "
            f"({checked} compared, {matched} matched, {warned} warned-skipped, "
            f"{source_skipped} source-skipped, engines {sorted(conns)}). The "
            f"transpiled output executed but returned a different answer, or the "
            f"target rejected it at runtime — a semantic defect that the "
            f"parse-only challenge gate cannot see. Fix the transpiler, or (if "
            f"it is a documented divergence) add the case to the exclusions "
            f"ledger with its class tag:\n" + "\n".join(failures)
        )
