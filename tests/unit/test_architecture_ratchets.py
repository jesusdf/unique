# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Comparator logic of scripts/architecture_ratchets.py.

Unit tests for the pure ``evaluate`` / ``lowered_floors`` helpers; the
file-system ``measure`` and the ruff subprocess are covered by running the
gate for real in CI.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "architecture_ratchets.py"
_spec = importlib.util.spec_from_file_location("architecture_ratchets", _PATH)
assert _spec is not None and _spec.loader is not None
ratchets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratchets)


class TestEvaluate:
    def test_all_at_floor_passes(self) -> None:
        floors = {"a": 10, "b": 5}
        code, lines = ratchets.evaluate({"a": 10, "b": 5}, floors)
        assert code == 0
        assert all("ok" in line for line in lines)

    def test_below_floor_passes_with_slack(self) -> None:
        code, lines = ratchets.evaluate({"a": 3}, {"a": 10})
        assert code == 0
        assert "slack 7" in lines[0]

    def test_above_floor_fails(self) -> None:
        code, lines = ratchets.evaluate({"a": 11}, {"a": 10})
        assert code == 1
        assert "REGRESSED" in lines[0]
        assert "+1" in lines[0]

    def test_missing_measurement_fails(self) -> None:
        code, lines = ratchets.evaluate({}, {"a": 10})
        assert code == 1
        assert "MISSING" in lines[0]

    def test_one_regression_fails_the_whole_gate(self) -> None:
        code, _ = ratchets.evaluate({"a": 10, "b": 6}, {"a": 10, "b": 5})
        assert code == 1


class TestLoweredFloors:
    def test_lowers_when_current_is_smaller(self) -> None:
        new = ratchets.lowered_floors({"a": 4, "b": 5}, {"a": 10, "b": 5})
        assert new == {"a": 4, "b": 5}

    def test_never_raises_when_current_is_larger(self) -> None:
        # A metric that regressed must NOT lift its floor (the gate would then
        # bless the regression). The floor stays; the gate still fails.
        new = ratchets.lowered_floors({"a": 99}, {"a": 10})
        assert new == {"a": 10}

    def test_missing_current_keeps_floor(self) -> None:
        new = ratchets.lowered_floors({}, {"a": 10})
        assert new == {"a": 10}


class TestBaselineFloorsAreMonotonic:
    def test_current_measurement_does_not_exceed_committed_floors(self) -> None:
        # The committed baselines must describe the current tree (else CI is
        # already red or already stale). This exercises the real measurement.
        current = ratchets.measure()
        code, lines = ratchets.evaluate(current, ratchets.FLOORS)
        assert code == 0, "\n".join(lines)
