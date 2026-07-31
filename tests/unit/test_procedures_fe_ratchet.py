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

# Measured 2026-08-01 (briefs A10-P2 + A10-P3 combined at integration).
# Enrolled = 18 routines: func3 (scalar); proc_13/14 (out); proc_11/10/15,
# proc_16/18, proc_19/21, proc_22/24, proc_27 (table_state); proc_1/3/5
# (result sets — refcursor OUT on Oracle, refcursor INOUT on PG since B56,
# direct on MySQL); proc_4 + proc_26 (func1-freeze table_state; proc_26 on
# all four targets since brief B60 fixed the MySQL 1093 self-ref-subquery
# defect — see the spec comment).
# Ledger = 15 (33 - 18): 4 nondeterministic-clock (func1/func2 kept for
# inherent reasons + proc_6 encoding, proc_25 embedded-dml-fallback), 4
# dynamic-sql, 3 degrade-output-clause (incl. proc_2 retagged), 1
# generated-key, 1 encoding-inherent, 1 tvf-no-pg-equiv, 1 trigger-complex.
ENROLLED_FLOOR = 18


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


def test_defect_pending_fix_harvest_enrolls_when_fixed() -> None:
    """The ``defect-pending-fix`` ledger is a ready-made RED backlog for BLUE; a
    fixed defect leaves it and ENROLLS. proc_14 (T-SQL OUTPUT INOUT dropped, B58)
    was the A10-P1 harvest — once the OUTPUT -> IN OUT/INOUT mapping landed it
    enrolled and its ledger entry was removed."""
    assert "proc_14" in ENROLLED
    defects = [e.name for e in LEDGER if e.tag == "defect-pending-fix"]
    assert "proc_14" not in defects
