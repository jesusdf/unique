#!/usr/bin/env python3
"""Identity-mutation gate for test-assertion quality (audit 2026-07-02).

Runs the integration suite with Transpiler.transpile replaced by an
identity function and fails if too few tests notice. Tests that pass under
this mutation cannot detect a broken transpiler; this gate stops the suite
from regressing back to keyword-presence-only assertions.

The threshold is a floor, not a target: raise it as assertions are
hardened (v0.7.0 baseline was a 28% kill rate).
"""

from __future__ import annotations

import re
import subprocess
import sys

# Minimum fraction of integration tests that must FAIL under the mutation.
# Raised 0.33 -> 0.40 with the 2026-07-10 sweep-closing wave (measured
# 0.44: test_test2_residue_wave.py / test_cursor_variable_binding.py assert
# transformed shapes, which a no-op transpiler cannot satisfy).
# Raised 0.30 -> 0.33 when test_real_world.py gained the hardened
# TestOutputValidity gates (per-statement target-dialect parsing, foreign
# quoting, per-fixture idiom checks); measured kill rate after: 36%.
# Raised 0.40 -> 0.45 on 2026-07-11 (measured 0.49 after the M4-closing
# and M3-prereq waves' shape-asserting tests).
# Raised 0.45 -> 0.60 on 2026-07-24 (audit/2026-07-24/09-fix-briefs.md B15;
# measured 0.66, margin 6 points). The release checklist in
# skills/SKILL-development-workflow.md governs future raises; STALE_MARGIN
# below is the automated backstop for a floor that goes un-raised too long.
# Raised 0.60 -> 0.70 on 2026-07-25: the B16-step-2 campaign added the four
# challenge assertion modules (+1,073 identity-killing tests, measured 0.76)
# and the stale backstop itself demanded the raise — the ratchet ratcheting.
KILL_RATE_FLOOR = 0.70

# T7 (audit B15): if measured kill rate outruns the floor by more than this,
# the floor has gone stale (head-room that would silently absorb a
# regression) — fail loudly instead of waiting for someone to notice.
STALE_MARGIN = 0.15


def evaluate(kill_rate: float, floor: float = KILL_RATE_FLOOR) -> tuple[int, str]:
    """Decide the gate's exit code + message for a measured kill rate.

    Pure function (no subprocess) so it is unit-testable independently of
    running the integration suite.
    """
    if kill_rate < floor:
        return 1, (
            "FAIL: too many tests pass with the transpiler disabled — "
            "assertions must check the target idiom is present AND the "
            "source idiom is absent (see skills/SKILL-development-workflow.md)."
        )
    if round(kill_rate - floor, 9) > STALE_MARGIN:
        return 3, (
            f"FAIL: floor is stale — raise it (measured {kill_rate:.0%} is "
            f">{STALE_MARGIN:.0%} above floor {floor:.0%}; see the release "
            "checklist in skills/SKILL-development-workflow.md)."
        )
    return 0, ""


def main() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.mutation.identity_plugin",
            "--tb=no",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", tail)) else 0
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", tail)) else 0
    total = failed + passed
    if total == 0:
        print(f"identity-mutation: could not parse pytest summary: {tail!r}")
        return 2
    kill_rate = failed / total
    print(
        f"identity-mutation: {failed}/{total} tests detect a no-op transpiler "
        f"(kill rate {kill_rate:.0%}, floor {KILL_RATE_FLOOR:.0%})"
    )
    code, message = evaluate(kill_rate)
    if message:
        print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
