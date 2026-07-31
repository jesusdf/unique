# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Monotonic-downward ratchet for the FE auto-enrollment exclusions (audit A10-H).

Offline (no DB): the enrolled set of the live result-diff is mechanical — every
``[fixed]``, comparable, self-contained challenge case MINUS the exclusions
ledger — so the ledger size IS the count of comparable-but-unenrolled cases, and
it is exactly the debt this ratchet drives to zero. The floor only ever moves
DOWN: when a transpiler fix (or a comparator upgrade) removes a ledger entry,
lower ``LEDGER_SIZE_FLOOR`` to match in the same change. NEVER raise it — head-
room is precisely the regression the ratchet exists to deny (same discipline as
``scripts/architecture_ratchets.py`` / ``tests/unit/test_architecture_ratchets.py``).
"""

from __future__ import annotations

from tests.helpers.challenge_cases import is_self_contained, load_challenge_cases
from tests.helpers.challenge_fe_exclusions import LEDGER, VALID_TAGS
from tests.helpers.corpus import CorpusEntry
from tests.helpers.corpus_diff import is_comparable

# Measured 2026-07-31 at the B36b/B45 merge base (43 excluded cases: 25
# defect-pending-fix, 12 precision-policy-pending, 4 documented-inherent, 2
# session-dependent).
#
# 2026-07-31 (brief A10-T2): the comparator gained a coarser-operand-precision
# numeric tolerance (see ``tests/helpers/corpus_diff.py`` module docstring),
# live-verified to clear 11 of the 12 precision-policy-pending cases (removed
# from the ledger); the 12th (``my-num-to-str``) survives — its numbers are
# embedded in text, out of the comparator's scope by design — and moved to
# ``documented-inherent``. New count: 25 defect-pending-fix, 0
# precision-policy-pending, 5 documented-inherent, 2 session-dependent = 32.
# Monotonic downward only.
LEDGER_SIZE_FLOOR = 32


def _eligible_cases() -> list[CorpusEntry]:
    """[fixed], result-comparable, self-contained cases — the enrollable pool."""
    pool: list[CorpusEntry] = []
    for c in load_challenge_cases():
        if c.status != "fixed":
            continue
        entry = CorpusEntry(id=c.id, sql=c.sql, source=c.source)
        if is_comparable(entry) and is_self_contained(c.sql, c.source):
            pool.append(entry)
    return pool


def test_ledger_size_does_not_exceed_floor() -> None:
    assert len(LEDGER) <= LEDGER_SIZE_FLOOR, (
        f"exclusions ledger grew to {len(LEDGER)} > floor {LEDGER_SIZE_FLOOR}. "
        "The ledger is monotonic downward: an entry may only be REMOVED (a fix "
        "landed). If you must add one, a defect was found — fix it instead, or "
        "escalate; do not raise the floor."
    )


def test_comparable_unenrolled_count_equals_ledger_and_is_under_floor() -> None:
    """Enrollment is mechanical, so unenrolled-comparable == ledger size."""
    excluded = {(e.id, e.sql) for e in LEDGER}
    unenrolled = [e for e in _eligible_cases() if (e.id, e.sql) in excluded]
    assert len(unenrolled) == len(LEDGER), (
        "every ledger entry must match exactly one comparable, self-contained "
        f"[fixed] case (matched {len(unenrolled)} of {len(LEDGER)}) — a "
        "mismatch means a stale ledger entry or a duplicate key."
    )
    assert len(unenrolled) <= LEDGER_SIZE_FLOOR


def test_ledger_entries_are_well_formed() -> None:
    keys = [(e.id, e.sql) for e in LEDGER]
    assert len(set(keys)) == len(keys), "duplicate (id, sql) ledger key"
    for e in LEDGER:
        assert e.tag in VALID_TAGS, f"{e.id}: unknown tag {e.tag!r}"
        assert e.reason.strip(), f"{e.id}: empty reason"


def test_no_stale_ledger_entries() -> None:
    """Every ledger (id, sql) must still correspond to an enrollable case."""
    pool = {(e.id, e.sql) for e in _eligible_cases()}
    stale = [e.id for e in LEDGER if (e.id, e.sql) not in pool]
    assert not stale, (
        f"stale ledger entries (case gone or no longer comparable/self-contained): "
        f"{stale}. Remove them and lower the floor."
    )
