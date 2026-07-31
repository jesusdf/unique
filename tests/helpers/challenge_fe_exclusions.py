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
  scale/precision. Awaiting the maintainer's numeric-tolerance policy decision.
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
        id="my-avg-precision2",
        tag="precision-policy-pending",
        reason="AVG display scale differs across engines (same value)",
        sql="SELECT AVG(x) FROM (SELECT 1 x UNION ALL SELECT 2 UNION ALL SELECT 2) t",
    ),
    Excluded(
        id="my-decimal-scale",
        tag="precision-policy-pending",
        reason="division/decimal result scale differs (same value)",
        sql="SELECT 10.00/3, 10/3.0, CAST(10 AS DECIMAL(10,4))/3, 1.5*1.5, 0.1*0.1",
    ),
    Excluded(
        id="my-div-mult2",
        tag="precision-policy-pending",
        reason="1/3*3 rounds to 1.0 vs 0.999999 (precision)",
        sql="SELECT 1/3*3 AS r",
    ),
    Excluded(
        id="my-div-precision",
        tag="precision-policy-pending",
        reason="division result scale differs (same value)",
        sql="SELECT 1.0 / 3 AS r",
    ),
    Excluded(
        id="my-float-precision",
        tag="precision-policy-pending",
        reason="float/division display precision differs",
        sql="SELECT 0.1+0.2, CAST(0.1 AS DOUBLE)+CAST(0.2 AS DOUBLE), 1.0/3, 2/3",
    ),
    Excluded(
        id="my-num-to-str",
        tag="precision-policy-pending",
        reason="numeric->string default scale differs across engines",
        sql="SELECT CONCAT('n=',5), CONCAT('x=',5.50), CONCAT('d=',1.0/3), CONCAT('b=',TRUE), 5.50+0",
    ),
    Excluded(
        id="ora-decimal-scale",
        tag="precision-policy-pending",
        reason="division/decimal result scale differs (same value)",
        sql="SELECT 10.00/3, 10/3.0, CAST(10 AS NUMBER(10,4))/3, 1.5*1.5 FROM DUAL",
    ),
    Excluded(
        id="ora-div-mult2",
        tag="precision-policy-pending",
        reason="1/3*3 rounds to 1.0 vs 0.999999 (precision)",
        sql="SELECT 1/3*3 AS r FROM DUAL",
    ),
    Excluded(
        id="ora-div-precision",
        tag="precision-policy-pending",
        reason="division result scale differs (same value)",
        sql="SELECT 1 / 3 AS r FROM DUAL",
    ),
    Excluded(
        id="ora-float-precision",
        tag="precision-policy-pending",
        reason="float/division display precision differs",
        sql="SELECT 0.1+0.2, CAST(0.1 AS BINARY_DOUBLE)+CAST(0.2 AS BINARY_DOUBLE), 1.0/3 FROM DUAL",
    ),
    Excluded(
        id="pg-avg-null",
        tag="precision-policy-pending",
        reason="AVG display scale differs across engines (same value)",
        sql="SELECT AVG(x) FROM (VALUES (1),(2),(NULL),(4)) v(x)",
    ),
    Excluded(
        id="pg-scientific",
        tag="precision-policy-pending",
        reason="float scientific vs exact numeric precision",
        sql="SELECT 1e20::float, 1e-20::float, 123456789012345678901234567890::numeric",
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
        id="my-bool-char",
        tag="defect-pending-fix",
        reason="CAST(bool AS CHAR) emits invalid target CAST (missing AS)",
        sql="SELECT CAST((1=1) AS CHAR) AS r",
    ),
    Excluded(
        id="my-cast-binary2",
        tag="defect-pending-fix",
        reason="fixed-width BINARY padding not reproduced on T-SQL",
        sql="SELECT CONVERT('abc',BINARY), CONVERT('abc' USING latin1), CAST('abc' AS BINARY)",
    ),
    Excluded(
        id="my-dateadd",
        tag="defect-pending-fix",
        reason="string-typed date + INTERVAL needs a date cast on targets",
        sql="SELECT DATE_ADD('2020-01-31',INTERVAL 1 MONTH), DATE_ADD('2020-01-01',INTERVAL 1 DAY), DATE_SUB('2020-03-01',INTERVAL 1 DAY), '2020-01-01'+INTERVAL 1 HOUR",
    ),
    Excluded(
        id="my-having-noagg",
        tag="defect-pending-fix",
        reason="HAVING without GROUP BY lowers to an unnamed derived column",
        sql="SELECT x, RANK() OVER (ORDER BY x) FROM (SELECT 1 x UNION ALL SELECT 2) t HAVING x>0",
    ),
    Excluded(
        id="my-insert-oob",
        tag="defect-pending-fix",
        reason="out-of-bounds INSERT() emulation not guarded",
        sql="SELECT INSERT('abc', 10, 1, 'X') AS r",
    ),
    Excluded(
        id="my-insert-zeropos",
        tag="defect-pending-fix",
        reason="INSERT() at position 0 / negative substring length",
        sql="SELECT INSERT('abcdef', 0, 2, 'XY') AS r",
    ),
    Excluded(
        id="my-left-float",
        tag="defect-pending-fix",
        reason="float length arg: MySQL rounds, emulation truncates / left(unknown,numeric)",
        sql="SELECT LEFT('hello', 2.9) AS r",
    ),
    Excluded(
        id="my-repeat-float",
        tag="defect-pending-fix",
        reason="float count arg: MySQL rounds, emulation truncates",
        sql="SELECT REPEAT('ab', 2.9) AS r",
    ),
    Excluded(
        id="my-str-plus-interval",
        tag="defect-pending-fix",
        reason="string date + INTERVAL needs a date cast on targets",
        sql="SELECT '2020-01-01' + INTERVAL 1 DAY AS r",
    ),
    Excluded(
        id="my-ts-to-date",
        tag="defect-pending-fix",
        reason="Oracle DATE keeps the time component (DATE() should drop it)",
        sql="SELECT DATE(TIMESTAMP '2020-01-01 14:30') AS r",
    ),
    Excluded(
        id="ora-cast-int-edge",
        tag="defect-pending-fix",
        reason="CAST('3.9' AS INT): Oracle rounds, targets reject",
        sql="SELECT CAST('3.9' AS INT), TRUNC(3.9), ROUND(3.9), CAST(3.9 AS NUMBER(1)) FROM DUAL",
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
        id="pg-bool-repr",
        tag="defect-pending-fix",
        reason="boolean cast emits invalid target CAST (missing AS)",
        sql="SELECT (1>0), (1>0)::int, (1>0)::text, NOT (1>0), true AND NULL",
    ),
    Excluded(
        id="pg-chr-ascii-unicode",
        tag="defect-pending-fix",
        reason="multibyte CHR/ASCII not reproduced on MySQL",
        sql="SELECT chr(233), ascii('é')",
    ),
    Excluded(
        id="po-distinct-case",
        tag="defect-pending-fix",
        reason="DISTINCT lowers to an unnamed derived-table column",
        sql="SELECT DISTINCT x FROM (VALUES ('a'),('A'),('a'),('B')) v(x) ORDER BY x",
    ),
    Excluded(
        id="postgresql-qdrop",
        tag="defect-pending-fix",
        reason="FOR UPDATE over a derived table rejected on Oracle (ORA-02014)",
        sql="SELECT x FROM (VALUES (1),(2)) v(x) FOR UPDATE",
    ),
    Excluded(
        id="reda-ora-decode-mixed-type",
        tag="defect-pending-fix",
        reason="DECODE mixed-type default lowers to a rejected int CAST",
        sql="SELECT DECODE(1, 1, 'a', 2, 'b', 99) AS r FROM DUAL",
    ),
    Excluded(
        id="ts-cast-int-datetime",
        tag="defect-pending-fix",
        reason="CAST(int AS DATETIME): date vs integer on MySQL",
        sql="SELECT CAST(1 AS DATETIME) AS r",
    ),
    Excluded(
        id="ts-compress",
        tag="defect-pending-fix",
        reason="COMPRESS GZIP vs ZLIB container on MySQL",
        sql="SELECT COMPRESS('data') AS r",
    ),
    Excluded(
        id="ts-frac-seconds",
        tag="defect-pending-fix",
        reason="fractional-second rounding .123456 vs .123457",
        sql="SELECT CAST('2020-01-01 10:20:30.1234567' AS DATETIME2), CAST('2020-01-01 10:20:30.123' AS DATETIME)",
    ),
)
