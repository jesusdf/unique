# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Exclusions ledger for the procedures functional-equivalence harness (A10-P1).

Every routine in ``tests/fixtures/procedures/procedures_sqlserver.sql`` that is
NOT enrolled in ``procedures_fe_spec.ROUTINE_CASES`` is named here, once, with a
class ``tag`` and a one-line ``reason`` — the ledger IS the visibility, there is
no silent cap. The invariant ``len(ENROLLED) + len(LEDGER) == 33`` (checked by
``tests/unit/test_procedures_fe_ratchet.py``) guarantees nothing falls through:
a routine is either compared or accounted for.

Tags (audit ``2026-07-31-a10p-procedures-fe-design.md`` §4, plus
``defect-pending-fix`` for a real gap this harness surfaced):

- ``nondeterministic-clock`` — depends on ``func1`` / ``GETDATE`` (removable via
  the P3 ``func1``-freeze lever).
- ``generated-key`` — the observable is a ``NEWSEQUENTIALID`` / ``IDENTITY`` value.
- ``degrade-output-clause`` — ``UNIQUE-1191`` (OUTPUT ... INTO dropped) makes the
  effect wrong; a real defect that feeds BLUE.
- ``dynamic-sql`` — ``sp_executesql`` / ``EXEC``-orchestrated body.
- ``resultset-pg-invalid`` — a bare ``SELECT`` result-set procedure; capture is
  A10-P2, and its PG output is runtime-invalid (SQLSTATE 42601, backlog B56).
- ``tvf-no-pg-equiv`` — inline table-valued function (``UNIQUE-1154``), A10-P3.
- ``encoding-inherent`` — a genuine cross-engine value divergence with no faithful
  mapping (NVARCHAR/UTF-16 vs UTF-8 hash bytes).
- ``trigger-complex`` — a trigger side-effect needing the update chain, A10-P3.
- ``embedded-dml-fallback`` — ``UNIQUE-1231`` "Embedded DML not modeled by the
  IR converter; converted with raw sqlglot (review the statement)": an honest
  "needs review" degrade, not (yet) proven wrong, so treated as non-benign per
  project policy ("default: degrade until proven benign").
- ``defect-pending-fix`` — a real, unwarned functional gap surfaced by the
  harness; a ready-made RED finding backlogged for BLUE.

Monotonic: an entry leaves this ledger only when the routine ENROLLS (a fix or a
new capture path lands) — never the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_TAGS = frozenset(
    {
        "nondeterministic-clock",
        "generated-key",
        "degrade-output-clause",
        "dynamic-sql",
        "resultset-pg-invalid",
        "tvf-no-pg-equiv",
        "encoding-inherent",
        "trigger-complex",
        "embedded-dml-fallback",
        "defect-pending-fix",
    }
)


@dataclass(frozen=True)
class Excluded:
    """One non-enrolled routine: named, classified, and explained."""

    name: str
    tag: str
    reason: str


LEDGER: tuple[Excluded, ...] = (
    # -- functions ----------------------------------------------------------- #
    Excluded(
        name="func1",
        tag="nondeterministic-clock",
        reason="RETURN DATEADD(day,-3,GETDATE()); fixture stub, comparable only "
        "under the P3 func1-freeze lever",
    ),
    Excluded(
        name="func2",
        tag="encoding-inherent",
        reason="A10-P3 re-verification 2026-08-01: the P3 func1-freeze lever "
        "resolves the clock, but func2's own RETURN is `dbo.func4(@col_74, "
        "@col_79)` -- the SAME NVARCHAR/UTF-16 vs UTF-8 hash-byte divergence "
        "as func4 itself, permanently non-comparable. Also needs-seed "
        "(tbl_9, tbl_13, tbl_1, tbl_2, tbl_10)",
    ),
    Excluded(
        name="func4",
        tag="encoding-inherent",
        reason="HASHBYTES('SHA2_256', NVARCHAR) hashes UTF-16LE bytes on SQL "
        "Server but the Oracle/PG/MySQL forms hash UTF-8 bytes -> a different "
        "digest with ZERO warnings (the canonical '0-warning, still wrong' "
        "specimen). PG additionally errors sha256(text) at call (backlog B57)",
    ),
    Excluded(
        name="func5",
        tag="tvf-no-pg-equiv",
        reason="STRING_SPLIT inline table-valued function, UNIQUE-1154. A10-P3 "
        "re-verification 2026-08-01 (live transpile against current main): the "
        "blocker stands and is WIDER than the original note -- UNIQUE-1154 "
        "fires on BOTH PostgreSQL ('RETURNS TABLE' has no direct equivalent') "
        "and MySQL ('MySQL has no table-returning functions'), fully "
        "commenting out the routine on both; only the Oracle translation "
        "(SYS.ODCIVARCHAR2LIST via REGEXP_SUBSTR/CONNECT BY) is a real "
        "function. No B56/B57-adjacent change touched this path. A TVF "
        "capture kind (SELECT ... FROM TABLE(fn(...)) on Oracle only) is new "
        "harness machinery this brief does not add for a single-target "
        "routine -- kept ledgered",
    ),
    # -- result-set procedures (capture is A10-P2) --------------------------- #
    Excluded(
        name="proc_1",
        tag="resultset-pg-invalid",
        reason="TOP-1 UNION-ALL result set; capture is A10-P2, and PG emits a "
        "bare SELECT-in-PROCEDURE that runtime-fails 42601 (backlog B56)",
    ),
    Excluded(
        name="proc_3",
        tag="resultset-pg-invalid",
        reason="single-table result set; capture is A10-P2, PG runtime-invalid "
        "42601 (backlog B56)",
    ),
    Excluded(
        name="proc_5",
        tag="resultset-pg-invalid",
        reason="6-table NOLOCK join result set; capture is A10-P2, PG "
        "runtime-invalid 42601 (backlog B56)",
    ),
    # -- clock-dependent procedures (func1) ---------------------------------- #
    # proc_4 and proc_26 left this section under the P3 func1-freeze lever (see
    # procedures_fe_spec.ROUTINE_CASES); both live-verified 2026-08-01. The rest
    # below are re-verified: the freeze resolves their clock dependency, but
    # each has an INDEPENDENT blocker the freeze does not touch.
    Excluded(
        name="proc_2",
        tag="degrade-output-clause",
        reason="A10-P3 re-verification 2026-08-01: func1-freeze resolves the "
        "clock, but proc_2 carries the SAME UNIQUE-1191 (OUTPUT "
        "inserted.col_6 INTO @col_16 dropped) defect as proc_8/proc_9 on "
        "every target -- a real, independent defect, not a clock issue",
    ),
    Excluded(
        name="proc_6",
        tag="encoding-inherent",
        reason="A10-P3 re-verification 2026-08-01: func1-freeze resolves the "
        "clock, but proc_6 (a) statically carries UNIQUE-1177 (a "
        "value-carrying early RETURN a target PROCEDURE has no channel for) "
        "on every target, and (b) even disregarding that, persists func4's "
        "encoding-inherent hash into tbl_6.col_74 via func2 -- permanently "
        "non-comparable. Also needs-seed across many tables",
    ),
    Excluded(
        name="proc_25",
        tag="embedded-dml-fallback",
        reason="A10-P3 re-verification 2026-08-01: func1-freeze resolves the "
        "clock, but proc_25 gets UNIQUE-1231 ('Embedded DML not modeled by "
        "the IR converter; converted with raw sqlglot (review the "
        "statement)') on every target, plus UNIQUE-1202 (func5 TVF "
        "unsupported) on MySQL -- independent of the clock",
    ),
    # -- generated keys ------------------------------------------------------ #
    Excluded(
        name="proc_7",
        tag="generated-key",
        reason="OUT @col_6 is a NEWSEQUENTIALID GUID; the tbl_3 INSERT effect is "
        "comparable with a PK-excluding probe but deferred (A10 decision #5)",
    ),
    # -- OUTPUT-clause degrade (real defects, feed BLUE) --------------------- #
    Excluded(
        name="proc_8",
        tag="degrade-output-clause",
        reason="UNIQUE-1191: OUTPUT inserted.col_93 INTO dropped -> the IDENTITY "
        "capture is lost, so the OUT is wrong. Real defect",
    ),
    Excluded(
        name="proc_9",
        tag="degrade-output-clause",
        reason="UNIQUE-1191: OUTPUT inserted.col_31 INTO dropped -> IDENTITY "
        "capture lost (same class as proc_8). Real defect",
    ),
    # -- dynamic SQL orchestrators ------------------------------------------- #
    Excluded(
        name="proc_12",
        tag="dynamic-sql",
        reason="sp_executesql + EXEC proc_13/proc_14 WHERE-builder orchestration",
    ),
    Excluded(
        name="proc_17",
        tag="dynamic-sql",
        reason="sp_executesql-driven result set",
    ),
    Excluded(
        name="proc_20",
        tag="dynamic-sql",
        reason="sp_executesql-driven result set",
    ),
    Excluded(
        name="proc_23",
        tag="dynamic-sql",
        reason="sp_executesql-driven result set",
    ),
    # -- trigger ------------------------------------------------------------- #
    Excluded(
        name="col_173",
        tag="trigger-complex",
        reason="A10-P3 live-verified 2026-08-01 (design item 2 scenario: UPDATE "
        "tbl_6 SET col_32 = 1 on a seeded row, then read tbl_8): the WHOLE "
        "INSERT-into-tbl_8 body is a commented-out, whole-unit degrade on "
        "every target (Oracle UNIQUE-1179, PG/MySQL UNIQUE-1155 -- 'the T-SQL "
        "set-based inserted/deleted pseudo-tables have no row-level NEW/OLD "
        "equivalent') -- confirmed on live PostgreSQL: after firing the "
        "tracked UPDATE, tbl_8 stays EMPTY (0 rows) where T-SQL inserts 1. "
        "This is the documented, warned architecture limit (not a hidden "
        "defect); a faithful fix needs a NEW/OLD row-level rewrite of an "
        "inserted/deleted JOIN per engine, out of P3 scope",
    ),
)
