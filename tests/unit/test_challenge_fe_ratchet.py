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
#
# 2026-07-31 (brief T4-A, first BLUE round over the defect-pending-fix family):
# the STRUCTURAL/invalid-emission mechanisms fixed at the emitter/IR layer —
# boolean-to-char casts (pg-bool-repr, my-bool-char), Oracle string-to-int
# rounding (ora-cast-int-edge), synthesized derived-table column names
# (po-distinct-case, my-having-noagg), string-date + INTERVAL promotion
# (my-dateadd, my-str-plus-interval), and Oracle FOR UPDATE over an unlockable
# view (postgresql-qdrop). 8 cases removed: 17 defect-pending-fix, 5
# documented-inherent, 2 session-dependent = 24. Monotonic downward only.
#
# 2026-07-31 (brief T4-B, second BLUE round over defect-pending-fix): MySQL
# string-function value fidelity — the INSERT() out-of-range bounds guard
# generalized to Oracle/PG targets (my-insert-oob, my-insert-zeropos) and float
# length/count operands rounded on every target (my-left-float, my-repeat-float:
# Oracle SUBSTR/RPAD truncated, PG rejected the numeric length). 4 removed: 13
# defect-pending-fix, 5 documented-inherent, 2 session-dependent = 20.
#
# 2026-07-31 (brief T4-B cont.): date-value shapes — MySQL DATE() drops the time
# but Oracle's DATE type keeps it, so the CAST is now TRUNC-wrapped
# (my-ts-to-date); and T-SQL CAST(int AS DATETIME) day arithmetic reached MySQL
# as NUMERIC ``DATE + int`` (19000102) — switched to ADDDATE (ts-cast-int-
# datetime). 2 removed: 11 defect-pending-fix, 5 documented-inherent, 2
# session-dependent = 18.
#
# 2026-07-31 (brief T4-B cont.): DECODE mixed-type coercion extended to T-SQL —
# a text first-result with a numeric ELSE tried to convert the text branch to
# int (T-SQL precedence) and errored; the numeric branches now cast to
# VARCHAR(4000) as PG already did to TEXT (reda-ora-decode-mixed-type). 1
# removed: 10 defect-pending-fix, 5 documented-inherent, 2 session-dependent = 17.
#
# 2026-07-31 (brief T4-B cont.): MySQL lengthless CAST(x AS BINARY) is
# variable-width, but T-SQL's bare BINARY is fixed BINARY(30) and pads with
# 0x00; mapped the source-MySQL lengthless form to VARBINARY (my-cast-binary2;
# BINARY(n) keeps its width, Oracle stays a documented warned degrade). 1
# removed: 9 defect-pending-fix, 5 documented-inherent, 2 session-dependent = 16.
#
# 2026-07-31 (brief T4-B cont.): T-SQL COMPRESS/DECOMPRESS use the GZIP container
# but MySQL's same-named functions use zlib + a length prefix (bytes not
# interchangeable) — no faithful mapping, so the MySQL target now warns +
# carriers (UNIQUE-1238) instead of silently shipping different bytes
# (ts-compress). 1 removed: 8 defect-pending-fix, 5 documented-inherent, 2
# session-dependent = 15.
#
# 2026-07-31 (brief T4-B cont.): PG ascii() returns the Unicode code point but
# MySQL ASCII returns the first BYTE (ASCII('é')=195, not 233); read the code
# point via ORD(CONVERT(x USING utf32)) on the MySQL target (pg-chr-ascii-
# unicode; the ASCII-range and CHR legs already matched). 1 removed: 7
# defect-pending-fix, 5 documented-inherent, 2 session-dependent = 14.
#
# 2026-07-31 (brief T4-B cont.): ledger housekeeping over the tail. Removed
# ora-frac-seconds — the A10-T2 numeric-tolerance comparator already equates
# EXTRACT(SECOND)=30.123456 with integer DATEPART=30 (coarser-operand rounding),
# so it now MATCHES on all targets (comparator-cleared, no transpile change).
# Retagged 4 as documented-inherent with live evidence: ts-frac-seconds
# (DATETIME2(7) driver-truncation vs TIMESTAMP(6) rounding of the 7th digit),
# ora-lpad-tochar (Oracle TO_CHAR '#'/'B' number-format overflow has no PG form),
# ora-interval-out + ora-numtointerval (transpiler faithful — PG INTERVAL
# 'n MONTH' equals Oracle's year-month interval, but oracledb IntervalYM vs
# psycopg's timedelta flattening are not comparable across drivers). New count:
# 2 defect-pending-fix (my-agg-boolean, pg-baseconv), 9 documented-inherent, 2
# session-dependent = 13.
#
# 2026-07-31 (brief T4-B cont.): PG base-conversion to MySQL — x::bit(n)::text
# (an n-digit binary string) now emits RIGHT(LPAD(CONV(x,10,2),n,'0'),n) via the
# transformer (pre-order, before the inner BIT->BOOLEAN remap), and PG to_hex()
# (lowercase) becomes LOWER(HEX(x)) (MySQL HEX is uppercase). 1 removed: 1
# defect-pending-fix (my-agg-boolean), 9 documented-inherent, 2 session-dependent
# = 12.
#
# 2026-07-31 (brief T4-B cont.): MySQL aggregates a boolean predicate as 0/1, but
# T-SQL/PG reject a predicate as an aggregate value (8114 / "function sum(boolean)
# does not exist"); SUM/AVG/MIN/MAX/COUNT over a comparison now materialize the
# predicate as a tri-state 0/1 CASE (NULL predicate -> NULL, preserving COUNT/AVG
# semantics) on those targets (my-agg-boolean; Oracle 23c takes it natively). 1
# removed: 0 defect-pending-fix, 9 documented-inherent, 2 session-dependent = 11.
# The entire defect-pending-fix family from the A10-T4 harvest is now cleared.
LEDGER_SIZE_FLOOR = 11


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
