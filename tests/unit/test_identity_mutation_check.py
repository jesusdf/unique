# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Threshold logic of scripts/identity_mutation_check.py.

Unit tests for the ``evaluate`` function; the subprocess-driving ``main`` is
covered by running the script for real against the integration suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "identity_mutation_check.py"
_spec = importlib.util.spec_from_file_location("identity_mutation_check", _PATH)
assert _spec is not None and _spec.loader is not None
identity_mutation_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(identity_mutation_check)


class TestEvaluate:
    def test_below_floor_fails(self) -> None:
        code, message = identity_mutation_check.evaluate(0.50, floor=0.60)
        assert code == 1
        assert "too many tests pass" in message

    def test_at_floor_passes(self) -> None:
        code, message = identity_mutation_check.evaluate(0.60, floor=0.60)
        assert code == 0
        assert message == ""

    def test_within_stale_margin_passes(self) -> None:
        # 0.15 above the floor is exactly the margin, not past it.
        code, message = identity_mutation_check.evaluate(0.75, floor=0.60)
        assert code == 0
        assert message == ""

    def test_past_stale_margin_fails_distinctly(self) -> None:
        code, message = identity_mutation_check.evaluate(0.76, floor=0.60)
        assert code == 3
        assert "floor is stale — raise it" in message

    def test_current_floor_not_stale_against_measured_baseline(self) -> None:
        # 2026-07-25 measured kill rate (B16-step-2 campaign): 0.76 vs floor
        # 0.70 — inside the margin, so the real floor must not trip T7.
        # (Historic note: the 0.60 floor DID trip T7 at 0.76 — the backstop
        # forced this raise, which is the mechanism working.)
        code, message = identity_mutation_check.evaluate(0.76)
        assert code == 0
        assert message == ""
