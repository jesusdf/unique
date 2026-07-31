# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Offline ratchet for the procedures FE harness (audit A10-P1).

No database. Enrollment here is *curated* (a hand-picked start set), not
corpus-derived, so the invariant is two-sided:

- ``len(ENROLLED) >= ENROLLED_FLOOR`` — the floor only ever moves UP as routines
  land; a regression that drops a routine from the enrolled set fails. NEVER lower
  it (same monotonic discipline as ``test_challenge_fe_ratchet``, opposite
  direction because *more* enrolled is *better* here).
- ``len(ENROLLED) + len(LEDGER) == <routines in the fixture>`` — the no-silent-loss
  invariant: every routine is either compared or named on the ledger, and the two
  sets are disjoint. A routine added to the fixture must be classified or this
  fails.

The ``defect-pending-fix`` count is reported (it drives BLUE) but does not floor.
"""

from __future__ import annotations

from tests.helpers.procedures_fe_exclusions import LEDGER, VALID_TAGS
from tests.helpers.procedures_fe_spec import ENROLLED, discover_routines

# Measured 2026-07-31 (brief A10-P1). Enrolled start set = 12 routines:
#   func3 (scalar); proc_13 (out, degrades on 1152 -> skipped-with-reason live);
#   proc_11/10/15 (tbl_7 DML), proc_16/18 (tbl_8), proc_19/21 (tbl_6),
#   proc_22/24 (tbl_3 GUID), proc_27 (4-table cascade).
# Ledger = 21 routines (33 - 12): 6 nondeterministic-clock, 3 resultset-pg-invalid,
# 4 dynamic-sql, 2 degrade-output-clause, 1 generated-key, 1 encoding-inherent,
# 1 tvf-no-pg-equiv, 1 trigger-complex, 1 defect-pending-fix (proc_14, OUTPUT
# INOUT semantics dropped — surfaced live by this harness).
ENROLLED_FLOOR = 12


def test_enrolled_count_at_or_above_floor() -> None:
    assert len(ENROLLED) >= ENROLLED_FLOOR, (
        f"enrolled routines dropped to {len(ENROLLED)} < floor {ENROLLED_FLOOR}. "
        "The floor is monotonic UPWARD: a routine may only be ADDED (a capture "
        "path or a fix landed). If one genuinely had to leave the enrolled set, a "
        "regression occurred — investigate; do not lower the floor to hide it."
    )


def test_no_silent_loss_every_routine_classified() -> None:
    """enrolled ∪ ledger == all fixture routines, and the two are disjoint."""
    enrolled = set(ENROLLED)
    ledgered = {e.name for e in LEDGER}
    routines = set(discover_routines())

    overlap = enrolled & ledgered
    assert not overlap, f"routines both enrolled and ledgered: {sorted(overlap)}"

    classified = enrolled | ledgered
    missing = routines - classified
    assert not missing, (
        f"fixture routines neither enrolled nor ledgered: {sorted(missing)} — "
        "classify each (enroll it, or add a ledger entry with a reason)."
    )
    unknown = classified - routines
    assert not unknown, (
        f"enrolled/ledgered names not in the fixture: {sorted(unknown)} — a "
        "renamed or removed routine leaves a stale entry."
    )
    assert len(enrolled) + len(ledgered) == len(routines)


def test_ledger_entries_are_well_formed() -> None:
    names = [e.name for e in LEDGER]
    assert len(set(names)) == len(names), "duplicate routine on the ledger"
    for e in LEDGER:
        assert e.tag in VALID_TAGS, f"{e.name}: unknown tag {e.tag!r}"
        assert e.reason.strip(), f"{e.name}: empty reason"


def test_enrolled_has_no_duplicates() -> None:
    assert len(set(ENROLLED)) == len(ENROLLED), "duplicate enrolled routine"


def test_defect_pending_fix_count_is_reported() -> None:
    """A ready-made RED backlog for BLUE (reported, not floored)."""
    defects = [e.name for e in LEDGER if e.tag == "defect-pending-fix"]
    # proc_14 (OUTPUT INOUT dropped) is the A10-P1 harvest; degrade-output-clause
    # (proc_8/9) and resultset-pg-invalid (B56) are separately tagged real defects.
    assert "proc_14" in defects
