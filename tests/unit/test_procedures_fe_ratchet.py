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

# Measured 2026-07-31 (brief A10-P1, +proc_14 at B58). Enrolled set = 13 routines:
#   func3 (scalar); proc_13/14 (out — proc_13 degrades on 1152 -> skipped live,
#   proc_14 compares its INOUT @query); proc_11/10/15 (tbl_7 DML), proc_16/18
#   (tbl_8), proc_19/21 (tbl_6), proc_22/24 (tbl_3 GUID), proc_27 (4-table cascade).
# Ledger = 20 routines (33 - 13): 6 nondeterministic-clock, 3 resultset-pg-invalid,
# 4 dynamic-sql, 2 degrade-output-clause, 1 generated-key, 1 encoding-inherent,
# 1 tvf-no-pg-equiv, 1 trigger-complex. proc_14 (OUTPUT INOUT dropped) left the
# ledger when the B58 OUTPUT -> IN OUT/INOUT mapping landed and it enrolled.
#
# Updated 2026-08-01 (brief A10-P3, the func1-freeze lever). Enrolled set = 15:
# +proc_4 (all 3 targets) and +proc_26 (oracle/postgresql only — MySQL hits an
# independent, live-verified defect, UNIQUE-1093-class self-referencing UPDATE
# subquery, reported not fixed here; see procedures_fe_spec.py). Both need
# `freeze_func1` (func1() pinned to a fixed constant on every engine so the
# columns it feeds compare equal) + `resultset_tail` (their bodies also end in
# a bare-SELECT report that this harness calls-and-discards, not compares).
# The other clock-dependent routines were re-verified and each has an
# INDEPENDENT blocker the freeze does not touch, so they stay ledgered with
# updated tags/reasons: proc_2 -> degrade-output-clause (UNIQUE-1191, same
# class as proc_8/9); proc_6, func2 -> encoding-inherent (both ultimately
# persist/return func4's hash); proc_25 -> embedded-dml-fallback (new tag,
# UNIQUE-1231 "review the statement" on every target + UNIQUE-1202 on MySQL).
# func5 (TVF) and col_173 (trigger) were re-verified live and their blockers
# stand unchanged; func1 itself stays ledgered (the freeze is for its
# dependents, not for testing func1's own nondeterministic body).
ENROLLED_FLOOR = 15


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
