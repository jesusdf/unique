# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Corpus × live-execution sweep.

Every corpus statement is transpiled to each valid target and the output is
*executed* against the real engine (rolled back). A permissive parser accepts
things a real engine rejects (e.g. Oracle ``SELECT NULL`` without ``FROM DUAL``),
so executing is what actually catches the bugs. Statements that are documented
gaps carry an inline ``-- @xfail: <targets>`` directive; only *unexpected*
failures fail this test.

Skipped unless at least one ``UNIQUE_TEST_*_URL`` is set, so the default run
(and CI without databases) stays green. Runs in the syntax-live CI job.
"""

from __future__ import annotations

import pytest

from tests.helpers.corpus import load_corpus
from tests.helpers.corpus_sweep import run_sweep, urls_from_env


@pytest.mark.integration
def test_corpus_executes_on_live_engines() -> None:
    urls = urls_from_env()
    if not urls:
        pytest.skip("no UNIQUE_TEST_*_URL configured (set at least one to run)")

    entries = load_corpus()
    xfail = {e.id: e.xfail for e in entries}
    failures, executed, skipped = run_sweep(entries, urls)

    unexpected = [
        f for f in failures if f.target not in xfail.get(f.entry_id, frozenset())
    ]
    # xfail entries that now pass — the annotation is stale and should be removed.
    failed_pairs = {(f.entry_id, f.target) for f in failures}
    stale = [
        (eid, tgt)
        for eid, targets in xfail.items()
        for tgt in targets
        if (eid, tgt) not in failed_pairs and tgt in urls
    ]

    if stale:
        print(
            "\nNOTE: these -- @xfail annotations now pass; remove them:\n  "
            + "\n  ".join(f"{eid} -> {tgt}" for eid, tgt in sorted(stale))
        )

    if unexpected:
        detail = "\n".join(
            f"  [{f.source} -> {f.target}] {f.entry_id}: {f.error}\n"
            f"      output: {f.output[:120]!r}"
            for f in unexpected[:25]
        )
        pytest.fail(
            f"{len(unexpected)} unexpected corpus failure(s) out of {executed} "
            f"executed (engines: {sorted(urls)}; skipped: {skipped}).\n"
            "A real engine rejected transpiled output that is not a documented "
            f"gap — likely a new bug or a regression:\n{detail}"
        )
