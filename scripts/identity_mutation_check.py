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
KILL_RATE_FLOOR = 0.45


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
    if kill_rate < KILL_RATE_FLOOR:
        print(
            "FAIL: too many tests pass with the transpiler disabled — "
            "assertions must check the target idiom is present AND the "
            "source idiom is absent (see skills/SKILL-development-workflow.md)."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
