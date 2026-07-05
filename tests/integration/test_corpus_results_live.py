# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Differential result testing: transpiled output must return the same answer.

Executes each result-comparable corpus SELECT on its source engine and its
transpiled output on each target engine, comparing normalized result sets. This
catches *semantic* bugs (wrong result) that the corpus sweep — which only checks
the output executes — cannot. Needs at least two engine URLs (a source and a
target); skipped otherwise. Runs in the syntax-live CI job.
"""

from __future__ import annotations

import pytest

from tests.helpers.corpus import load_corpus
from tests.helpers.corpus_diff import run_result_diff, urls_from_env


@pytest.mark.integration
def test_transpiled_output_returns_same_result() -> None:
    urls = urls_from_env()
    if len(urls) < 2:
        pytest.skip("differential result testing needs >= 2 engine URLs")

    mismatches, checked, engines = run_result_diff(load_corpus(), urls)

    if mismatches:
        detail = "\n".join(
            f"  [{m.source} -> {m.target}] {m.entry_id}\n"
            f"      source result: {m.source_result}\n"
            f"      target result: {m.target_result}\n"
            f"      output: {m.output[:100]!r}"
            for m in mismatches[:20]
        )
        pytest.fail(
            f"{len(mismatches)} result mismatch(es) out of {checked} pairs "
            f"(engines: {engines}). Transpiled output executed but returned a "
            f"different answer — a semantic bug:\n{detail}"
        )
