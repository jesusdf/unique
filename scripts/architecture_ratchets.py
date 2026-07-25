#!/usr/bin/env python3
# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Architecture-ratchet gate (audit 2026-07-24 doc 04 / 09-fix-briefs.md B17 T3).

A monotonic *non-growth* gate for the converter-emitter debt the audit flagged
(F1–F5): emitter module size, the post-emit regex surface, dialect
string-dispatch, and cyclomatic-complexity offenders. Each metric carries a
hard-coded floor measured at a base commit; the gate FAILS when a metric
*exceeds* its floor and prints current-vs-floor for every metric. The numbers
only ever go DOWN: ``--update-floors`` lowers each floor to the current
measurement (never raises), locking in a burn-down so the cascade cannot
silently re-grow.

Wired into ``.github/workflows/ci.yaml`` next to the identity-mutation gate.

The pure comparator (:func:`evaluate`, :func:`lowered_floors`) is unit-tested
independently of the file-system measurement in
``tests/unit/test_architecture_ratchets.py``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"

# --- FLOORS: architecture-ratchet baselines ---------------------------------
# Measured 2026-07-25 at base commit 4008d7d (audit B17 T3). Monotonic
# downward only: lower with
#   python scripts/architecture_ratchets.py --update-floors
# after a change that reduces one. NEVER raise a floor by hand — head-room is
# exactly the regression the ratchet exists to deny.
FLOORS: dict[str, int] = {
    # Total lines across converter/emit*.py (the flat 9,992-line module plus
    # the emit_functions/emit_passthrough/emit_ddl/emit_expr split façade).
    "emit_total_lines": 10485,
    # ``re.sub`` / ``re.search`` / ``re.match`` calls in those emitter modules
    # (the F1–F3 post-emit regex surface guardrail 2 bans on emitted text).
    "converter_emitter_re_calls": 182,
    # ``== "<dialect>"`` string-dispatch in the shared modules (converter
    # emitter + procedural transformer/emitter base) — F6/§7 debt.
    "shared_dialect_compares": 577,
    # Functions over cyclomatic complexity 10 across src/ (F4/F5).
    "c901_offenders": 114,
}
# --- END FLOORS -------------------------------------------------------------

# Emitter modules: emit.py today, emit_*.py after the B17 step-4 split.
_EMIT_GLOB = "unique/core/converter/emit*.py"
# Shared modules that also carry dialect string-dispatch (F6/§7).
_EXTRA_SHARED = (
    "unique/core/procedural/transformer/base.py",
    "unique/core/procedural/emitter/base.py",
)

_RE_CALL = re.compile(r"\bre\.(?:sub|search|match)\b")
_DIALECT_CMP = re.compile(r'==\s*"(?:tsql|oracle|postgresql|mysql|sqlite)"')


def _emit_modules() -> list[Path]:
    return sorted(_SRC.glob(_EMIT_GLOB))


def _line_count(paths: list[Path]) -> int:
    return sum(len(p.read_text().splitlines()) for p in paths)


def _re_calls(paths: list[Path]) -> int:
    return sum(len(_RE_CALL.findall(p.read_text())) for p in paths)


def _dialect_compares(paths: list[Path]) -> int:
    return sum(len(_DIALECT_CMP.findall(p.read_text())) for p in paths)


def _c901_offenders() -> int:
    """Count functions over cyclomatic complexity 10 across ``src/``.

    Pins the threshold to 10 via an inline config override so the count is
    independent of the pyproject ceiling T6 sets (which only bars *new* code
    above the current worst offender).
    """
    proc = subprocess.run(
        [
            "ruff",
            "check",
            "--select",
            "C901",
            "--config",
            "lint.mccabe.max-complexity=10",
            "--output-format",
            "concise",
            str(_SRC),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"ruff failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout.count("C901")


def measure() -> dict[str, int]:
    """Measure every ratchet metric against the working tree."""
    emit = _emit_modules()
    shared = emit + [_SRC / p for p in _EXTRA_SHARED]
    return {
        "emit_total_lines": _line_count(emit),
        "converter_emitter_re_calls": _re_calls(emit),
        "shared_dialect_compares": _dialect_compares(shared),
        "c901_offenders": _c901_offenders(),
    }


def evaluate(current: dict[str, int], floors: dict[str, int]) -> tuple[int, list[str]]:
    """Decide the gate's exit code + a per-metric report (pure function).

    Fails (exit 1) if any metric *exceeds* its floor or is missing.
    """
    failed = False
    lines: list[str] = []
    for name, floor in floors.items():
        cur = current.get(name)
        if cur is None:
            failed = True
            lines.append(f"  {name}: MISSING measurement (floor {floor})")
            continue
        if cur > floor:
            failed = True
            lines.append(f"  {name}: {cur} > floor {floor}  REGRESSED (+{cur - floor})")
        else:
            lines.append(f"  {name}: {cur} <= floor {floor}  ok (slack {floor - cur})")
    return (1 if failed else 0), lines


def lowered_floors(current: dict[str, int], floors: dict[str, int]) -> dict[str, int]:
    """New floor set: each floor lowered to the current value, never raised."""
    return {k: min(current.get(k, floors[k]), floors[k]) for k in floors}


def _rewrite_floors_in_source(new: dict[str, int]) -> None:
    """Rewrite the ``FLOORS`` values in this file in place (preserving comments)."""
    path = Path(__file__)
    text = path.read_text()
    for name, value in new.items():
        text, n = re.subn(rf'("{name}":\s*)\d+', rf"\g<1>{value}", text)
        if n != 1:
            raise RuntimeError(f"could not rewrite floor {name!r} ({n} matches)")
    path.write_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-floors",
        action="store_true",
        help="lower each floor to the current measurement (never raises)",
    )
    args = parser.parse_args(argv)
    current = measure()

    if args.update_floors:
        new = lowered_floors(current, FLOORS)
        changed = {k: (FLOORS[k], new[k]) for k in FLOORS if new[k] != FLOORS[k]}
        _rewrite_floors_in_source(new)
        if changed:
            for name, (old, low) in changed.items():
                print(f"lowered {name}: {old} -> {low}")
        else:
            print("floors already at or below every current measurement")
        return 0

    code, lines = evaluate(current, FLOORS)
    print("architecture ratchets (current vs floor):")
    print("\n".join(lines))
    if code:
        print(
            "FAIL: a metric grew past its floor. Emitter size, post-emit regex "
            "and dialect string-dispatch must not increase (audit doc 04 / B17). "
            "Fix at the AST level, or if the floor legitimately dropped run "
            "`python scripts/architecture_ratchets.py --update-floors`."
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
