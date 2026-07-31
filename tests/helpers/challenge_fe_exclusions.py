# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Exclusions ledger for the auto-enrollment FE harness (audit A10 / brief A10-H).

The result-diff harness (``test_challenge_results_live.py``) enrolls EVERY
``[fixed]``, result-comparable, self-contained challenge case mechanically, then
subtracts the cases named here. One entry per excluded case — the ledger IS the
visibility: there is no silent cap. Each entry carries the case's ``id``, a
class ``tag``, a one-line ``reason``, and the exact ``sql`` it matches on (the
match key: two distinct cases can share a truncated slug — e.g. two
``postgresql-qdrop`` cases — so matching on the executable text pins exactly the
excluded one and keeps its clean twin enrolled).

Tags (seeded from the A10 taxonomy, re-derived by the live sweep, not the prose):

- ``precision-policy-pending`` (T2): same mathematical value at a different
  scale/precision. **Resolved 2026-07-31 (brief A10-T2)** — the comparator
  (``tests/helpers/corpus_diff.py``, see its module docstring) now applies a
  coarser-operand-precision numeric tolerance, which cleared 11 of the 12
  cases seeded under this tag; kept in ``VALID_TAGS`` for any future case that
  needs a policy call the comparator doesn't already cover, currently unused
  (0 entries) — the one survivor (``my-num-to-str``) moved to
  ``documented-inherent`` because its numbers are embedded in text, outside
  the comparator's deliberately narrow scope, not awaiting a decision.
- ``documented-inherent`` (T3): a known, already-documented cross-engine
  divergence (Oracle ``'' == NULL``, nondeterministic ``GROUP_CONCAT`` order,
  supplementary-plane NCHAR, boolean text rendering) that is missing its warning.
- ``session-dependent``: the value depends on session/connection identity
  (``@@IDENTITY``, ``USER``) — not result-comparable across engines by nature.
- ``defect-pending-fix`` (T4): a real, unwarned functional gap — a ready-made
  RED-grade finding, backlogged for a BLUE round.

Monotonic downward: entries leave when the transpiler (or the comparator) makes
the case match; nothing is added without a fix landing elsewhere. The size floor
is guarded by ``tests/unit/test_challenge_fe_ratchet.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_TAGS = frozenset(
    {
        "precision-policy-pending",
        "documented-inherent",
        "session-dependent",
        "defect-pending-fix",
    }
)


@dataclass(frozen=True)
class Excluded:
    """One excluded challenge case: matched on ``sql``, documented by the rest."""

    id: str
    tag: str
    reason: str
    sql: str


LEDGER: tuple[Excluded, ...] = (
    Excluded(
        id="my-num-to-str",
        tag="documented-inherent",
        reason=(
            "numeric->string default precision differs across engines, but the "
            "numbers are embedded in text ('d=0.33333' vs 'd=0.333333'), not a "
            "bare numeric cell — out of the numeric-tolerance comparator's scope "
            "by design (2026-07-31: never touch a substring of longer text; "
            "live-checked, the other 11 precision-policy cases now match and "
            "were removed from this ledger)"
        ),
        sql="SELECT CONCAT('n=',5), CONCAT('x=',5.50), CONCAT('d=',1.0/3), CONCAT('b=',TRUE), 5.50+0",
    ),
    Excluded(
        id="my-gc-order",
        tag="documented-inherent",
        reason="GROUP_CONCAT source order is nondeterministic by contract",
        sql="SELECT GROUP_CONCAT(x) FROM (SELECT 3 x UNION ALL SELECT 1 x UNION ALL SELECT 2 x) t",
    ),
    Excluded(
        id="my-left-neg",
        tag="documented-inherent",
        reason="Oracle folds '' to NULL (strings-collation rationale)",
        sql="SELECT LEFT('abc', -1) AS r",
    ),
    Excluded(
        id="pg-bool-text2",
        tag="documented-inherent",
        reason="boolean->text renders 'true' vs '1' by engine",
        sql="SELECT true::text AS r",
    ),
    Excluded(
        id="ts-nchar-hex",
        tag="documented-inherent",
        reason="supplementary-plane NCHAR: SQL Server NULL vs target emoji",
        sql="SELECT NCHAR(0x1F600) AS r",
    ),
    Excluded(
        id="red2-ts-at-identity-passthrough",
        tag="session-dependent",
        reason="@@IDENTITY/lastval depends on session insert state",
        sql="SELECT @@IDENTITY AS id",
    ),
    Excluded(
        id="reda-ora-user-function",
        tag="session-dependent",
        reason="USER returns the connection's own user, differs per engine",
        sql="SELECT USER AS r FROM DUAL",
    ),
    Excluded(
        id="my-agg-boolean",
        tag="defect-pending-fix",
        reason="SUM/AVG over boolean predicate unsupported/precision on targets",
        sql="SELECT SUM(x>1), COUNT(x>1), AVG(x>1), MAX(x>1) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 3) t",
    ),
    Excluded(
        id="ora-frac-seconds",
        tag="defect-pending-fix",
        reason="EXTRACT(SECOND) fractional vs integer DATEPART on targets",
        sql="SELECT TO_TIMESTAMP('2020-01-01 10:20:30.123456','YYYY-MM-DD HH24:MI:SS.FF6'), EXTRACT(SECOND FROM TIMESTAMP '2020-01-01 10:20:30.123456') FROM DUAL",
    ),
    Excluded(
        id="ora-interval-out",
        tag="defect-pending-fix",
        reason="year-month interval flattened to a day count on PG",
        sql="SELECT NUMTOYMINTERVAL(14,'MONTH'), NUMTODSINTERVAL(90000,'SECOND') FROM DUAL",
    ),
    Excluded(
        id="ora-lpad-tochar",
        tag="defect-pending-fix",
        reason="TO_CHAR '#' overflow mask fidelity",
        sql="SELECT LPAD(TO_CHAR(5,'FMB'), 8, '0') FROM DUAL",
    ),
    Excluded(
        id="ora-numtointerval",
        tag="defect-pending-fix",
        reason="year-month interval flattened to a day count on PG",
        sql="SELECT NUMTODSINTERVAL(1.5,'DAY'), NUMTOYMINTERVAL(18,'MONTH') FROM DUAL",
    ),
    Excluded(
        id="pg-baseconv",
        tag="defect-pending-fix",
        reason="base-conversion argument mapping wrong on MySQL",
        sql="SELECT 255::bit(8)::text,to_hex(255),255::text",
    ),
    Excluded(
        id="ts-frac-seconds",
        tag="defect-pending-fix",
        reason="fractional-second rounding .123456 vs .123457",
        sql="SELECT CAST('2020-01-01 10:20:30.1234567' AS DATETIME2), CAST('2020-01-01 10:20:30.123' AS DATETIME)",
    ),
)
