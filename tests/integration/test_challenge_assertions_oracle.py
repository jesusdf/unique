# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Dedicated per-case assertions for the Oracle-source challenge corpus.

``tests/integration/test_challenge.py`` guards ``challenge_oracle.sql`` with
generic looping checks (no unrecognized carrier / target-parse / limit warnings)
plus a hand-written class per *some* cases. This module covers the long tail:
every ``[fixed]``/untagged Oracle-source case that lacked a dedicated assertion
(audit ``09-fix-briefs.md`` B16 step 2). Cases already asserted in
``test_challenge.py`` are intentionally skipped here; ``[limit]`` cases are out
of scope (the generic limit contract in ``test_challenge.py`` covers them).

Design (mirrors the postgresql/mysql worker modules):

* One declarative :data:`CASES` table; a single parametrized runner per case ×
  foreign target (tsql / postgresql / mysql).
* Each expectation is checked on the **comment-stripped** output (``--`` lines
  and ``/* … */`` carriers removed) so the source header prose and the carrier
  message cannot satisfy a "present"/"absent" token by accident (the comment-
  prose trap from the development-workflow skill).
* A *faithful* target asserts the target idiom is **present** AND the source
  idiom is **absent** — both fail under the identity transpiler, so each row
  raises the identity-mutation kill rate.
* A *degrade-expected* target asserts a ``validity_gate`` warning fired AND a
  ``UNIQUE:`` carrier is present (which also disappears under identity).

Targets a case handles as a pure pass-through (output byte-equal to the Oracle
source once ``FROM DUAL`` normalisation is applied, e.g. ``LOG(2, 8)`` into
PostgreSQL) are omitted for that case — a passthrough has no idiom that identity
would not also produce, so an assertion there would be vacuous and dilute the
gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest

# Reuse the challenge loader/splitter helpers rather than re-implementing them.
from tests.integration.test_challenge import _case
from unique.core.transpiler import Transpiler

_SOURCE = "oracle"
_ALL3 = ("tsql", "postgresql", "mysql")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)


def _body(sql: str) -> str:
    """Executable text only: drop ``/* … */`` carriers then whole ``--`` lines."""
    no_block = _COMMENT_BLOCK.sub("", sql)
    return "\n".join(
        ln for ln in no_block.splitlines() if not ln.lstrip().startswith("--")
    )


@dataclass(frozen=True)
class Expect:
    """What a single (case, target) transpilation must satisfy at HEAD."""

    present: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    warn: bool = False  # a validity_gate warning + a UNIQUE: carrier is expected

    def vacuous(self) -> bool:
        return not (self.present or self.absent or self.warn)


@dataclass(frozen=True)
class Case:
    kw: str  # keyword handed to test_challenge._case (matches the case header)
    targets: dict[str, Expect] = field(default_factory=dict)


def _degrade_all3(slug: str) -> Case:
    """An Oracle-only construct with no cross-engine form: warned carrier on every
    foreign target (whole statement replaced by a UNIQUE: carrier)."""
    return Case(kw=slug + " ", targets={t: Expect(warn=True) for t in _ALL3})


# Oracle-only built-ins / pseudo-functions with no equivalent on any foreign
# target: the whole statement degrades to a warned ``UNIQUE:`` carrier. One
# assertion class covers all three targets — the warning + carrier vanish under
# the identity transpiler.
_FULL_DEGRADE = (
    "ora-agg-median",
    "ora-asciistr",
    "ora-baseconv",
    "ora-bit-fns",
    "ora-char-encoding",
    "ora-clob-coalesce",
    "ora-clob-ops",
    "ora-compose",
    "ora-date-arith2",
    "ora-dump",
    "ora-dump2",
    "ora-extract",
    "ora-extractvalue",
    "ora-from-tz",
    "ora-hash-all",
    "ora-interval-out",
    "ora-lnnvl",
    "ora-lob-length",
    "ora-median-mode",
    "ora-misc-num",
    "ora-nanvl",
    "ora-nchr-unistr",
    "ora-next-day",
    "ora-nls-case",
    "ora-nlssort",
    "ora-numtodsinterval",
    "ora-numtointerval",
    "ora-ora-hash",
    "ora-ratio-to-report",
    "ora-ratio2",
    "ora-rawtohex",
    "ora-round-fns",
    "ora-sys-extract-utc",
    "ora-sys-fns",
    "ora-tz-fns",
    "ora-user-context",
    "ora-vsize",
    "ora-window-analytic",
)


CASES: dict[str, Case] = {slug: _degrade_all3(slug) for slug in _FULL_DEGRADE}

# Mixed / faithful cases: explicit per-target expectations derived from the HEAD
# output. A missing target = pure pass-through for that direction (omitted so the
# row is not vacuous under identity).
CASES.update(
    {
        # ------- SELECT DISTINCT / ORDER BY NULL & collation semantics -------
        "or-distinct-null": Case(
            "or-distinct-null ",
            {
                # Oracle sorts NULLs high; tsql/mysql sort low -> NULL-ordering CASE.
                "tsql": Expect(
                    ("CASE WHEN x IS NULL THEN 1 ELSE 0 END",), ("FROM DUAL",)
                ),
                "postgresql": Expect(("ORDER BY x ASC",), ("FROM DUAL",)),
                "mysql": Expect(("CASE WHEN x IS NULL THEN 1 ELSE 0 END",)),
            },
        ),
        "or-order-strings": Case(
            "or-order-strings ",
            {
                # Oracle default binary string order -> BIN2 / *_bin collation.
                "tsql": Expect(
                    (
                        "COLLATE Latin1_General_BIN2",
                        "CASE WHEN x IS NULL THEN 1 ELSE 0 END",
                    ),
                    ("FROM DUAL",),
                ),
                "postgresql": Expect(("ORDER BY x ASC",), ("FROM DUAL",)),
                "mysql": Expect(("COLLATE utf8mb4_bin",)),
            },
        ),
        # ------------------------- date / time functions -------------------------
        "ora-add-months": Case(
            "ora-add-months ",
            {
                "tsql": Expect(
                    ("DATEADD(MONTH, 3, GETDATE())", "EOMONTH"), ("ADD_MONTHS",)
                ),
                "postgresql": Expect(
                    ("DATE_TRUNC('month'", "INTERVAL '1 month'"), ("ADD_MONTHS",)
                ),
                "mysql": Expect(
                    ("DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 3 MONTH)", "LAST_DAY"),
                    ("ADD_MONTHS",),
                ),
            },
        ),
        "ora-last-day": Case(
            "ora-last-day ",
            {
                "tsql": Expect(("EOMONTH(GETDATE())",), ("LAST_DAY", "SYSDATE")),
                "postgresql": Expect(
                    ("DATE_TRUNC('month', CURRENT_TIMESTAMP)",), ("LAST_DAY", "SYSDATE")
                ),
                "mysql": Expect(("LAST_DAY(CURRENT_TIMESTAMP)",), ("SYSDATE",)),
            },
        ),
        "ora-lastday-leap": Case(
            "ora-lastday-leap ",
            {
                "tsql": Expect(("EOMONTH('2020-02-01')",), ("LAST_DAY",)),
                "postgresql": Expect(
                    ("DATE_TRUNC('month', DATE '2020-02-01')",), ("LAST_DAY",)
                ),
                "mysql": Expect(("LAST_DAY('2020-02-01')",), ("DATE '2020-02-01'",)),
            },
        ),
        "ora-frac-seconds": Case(
            "ora-frac-seconds ",
            {
                "tsql": Expect(
                    (
                        "CAST('2020-01-01 10:20:30.123456' AS DATETIME2)",
                        "DATEPART(SECOND",
                    ),
                    ("TO_TIMESTAMP",),
                ),
                "postgresql": Expect(
                    (
                        "TIMESTAMP '2020-01-01 10:20:30.123456'",
                        "EXTRACT(SECOND FROM",
                    ),
                    ("TO_TIMESTAMP",),
                ),
                "mysql": Expect(
                    ("CAST('2020-01-01 10:20:30.123456' AS DATETIME(6))",),
                    ("TO_TIMESTAMP",),
                ),
            },
        ),
        "ora-now-variants": Case(
            "ora-now-variants ",
            {
                # NB: SYSDATETIME() (from LOCALTIMESTAMP) contains "SYSDATE" as a
                # substring, so tsql cannot assert "SYSDATE" absent.
                "tsql": Expect(
                    ("GETDATE()", "SYSDATETIME()", "CAST(GETDATE() AS DATE)"),
                    ("LOCALTIMESTAMP",),
                ),
                "postgresql": Expect(("CURRENT_DATE",), ("SYSDATE", "SYSTIMESTAMP")),
                "mysql": Expect(("CURDATE()",), ("SYSDATE", "LOCALTIMESTAMP")),
            },
        ),
        # ------------------------------ CAST / types ------------------------------
        "ora-cast-expr": Case(
            "ora-cast-expr ",
            {
                "tsql": Expect(
                    (
                        "CAST('123' AS DECIMAL(38, 10))",
                        "CAST(GETDATE() AS DATETIME2)",
                    ),
                    ("AS NUMBER", "SYSDATE"),
                ),
                "postgresql": Expect(
                    (
                        "CAST('123' AS DECIMAL)",
                        "CAST(CURRENT_TIMESTAMP AS TIMESTAMP)",
                    ),
                    ("AS NUMBER", "SYSDATE"),
                ),
                "mysql": Expect(
                    (
                        "CAST('123' AS DECIMAL(38, 10))",
                        "CAST(CURRENT_TIMESTAMP AS DATETIME)",
                    ),
                    ("AS NUMBER", "SYSDATE"),
                ),
            },
        ),
        "ora-decimal-scale": Case(
            "ora-decimal-scale ",
            {
                "tsql": Expect(("CAST(10 AS DECIMAL(10, 4))",), ("AS NUMBER",)),
                "postgresql": Expect(("CAST(10 AS DECIMAL(10, 4))",), ("AS NUMBER",)),
                "mysql": Expect(("CAST(10 AS DECIMAL(10, 4))",), ("AS NUMBER",)),
            },
        ),
        "ora-float-precision": Case(
            "ora-float-precision ",
            {
                "tsql": Expect(("CAST(0.1 AS FLOAT)",), ("BINARY_DOUBLE",)),
                "postgresql": Expect(
                    ("CAST(0.1 AS DOUBLE PRECISION)",), ("BINARY_DOUBLE",)
                ),
                "mysql": Expect(("CAST(0.1 AS DOUBLE)",), ("BINARY_DOUBLE",)),
            },
        ),
        "ora-tonumber2": Case(
            "ora-tonumber2 ",
            {
                "postgresql": Expect(("CAST('123.45' AS DECIMAL)",), ("AS NUMBER",)),
                "tsql": Expect(warn=True),
                "mysql": Expect(warn=True),
            },
        ),
        "ora-dttypes": Case(
            "ora-dttypes ",
            {
                # WITH LOCAL TIME ZONE -> timestamptz (a real PG type), warned;
                # the invalid TIMESTAMPLTZ token must be gone.
                "postgresql": Expect(("d TIMESTAMPTZ",), ("TIMESTAMPLTZ",), warn=True),
                "tsql": Expect(("DATETIMEOFFSET",), ("WITH TIME ZONE",), warn=True),
                "mysql": Expect(("e VARCHAR(30)",), ("INTERVAL YEAR",), warn=True),
            },
        ),
        # ---------------------------- integer division ----------------------------
        "ora-div": Case(
            "ora-div ",
            {
                "tsql": Expect(("(5 * 1.0 / 2)",)),
                "postgresql": Expect(("(5 * 1.0 / 2)",)),
            },
        ),
        "ora-div-mult2": Case(
            "ora-div-mult2 ",
            {
                "tsql": Expect(("(1 * 1.0 / 3) * 3",)),
                "postgresql": Expect(("(1 * 1.0 / 3) * 3",)),
            },
        ),
        "ora-div-precision": Case(
            "ora-div-precision ",
            {
                "tsql": Expect(("(1 * 1.0 / 3)",)),
                "postgresql": Expect(("(1 * 1.0 / 3)",)),
            },
        ),
        # ---------------------------- string functions ----------------------------
        "ora-concat-null": Case(
            # Oracle folds NULL out of || concatenation; keep that (warns FUNC-DIFF).
            "ora-concat-null ",
            {
                "tsql": Expect(("'a' + 'b'",), ("NULL", "||")),
                "postgresql": Expect(("'a' || 'b'",), ("NULL",)),
                "mysql": Expect(("CONCAT('a', 'b')",), ("NULL", "||")),
            },
        ),
        "ora-fconcat": Case(
            "ora-fconcat ",
            {
                "tsql": Expect(("'a' + 'b'", "CONCAT(2, 3)"), ("||",)),
                # PG has no integer||integer operator: both-numeric || -> TEXT casts.
                "postgresql": Expect(
                    ("'a' || 'b'", "CAST(2 AS TEXT) || CAST(3 AS TEXT)")
                ),
                "mysql": Expect(("CONCAT('a', 'b')", "CONCAT(2, 3)"), ("||",)),
            },
        ),
        "ora-num-to-str": Case(
            "ora-num-to-str ",
            {
                "tsql": Expect(
                    ("CONCAT('n=', 5)", "CONVERT(VARCHAR(4000), 5.50)"),
                    ("TO_CHAR", "||"),
                ),
                "postgresql": Expect(("'n=' || 5", "CAST(5.50 AS TEXT)"), ("TO_CHAR",)),
                "mysql": Expect(
                    ("CONCAT('n=', 5)", "CAST(5.50 AS CHAR)"), ("TO_CHAR", "||")
                ),
            },
        ),
        "ora-ltrim-set": Case(
            "ora-ltrim-set ",
            {
                "tsql": Expect(("TRIM(LEADING 'x' FROM 'xxabc')",), ("LTRIM",)),
                "postgresql": Expect(("TRIM(LEADING 'x' FROM 'xxabc')",), ("LTRIM",)),
                "mysql": Expect(("TRIM(LEADING 'x' FROM 'xxabc')",), ("LTRIM",)),
            },
        ),
        "ora-rtrim-chars": Case(
            "ora-rtrim-chars ",
            {
                "tsql": Expect(("TRIM(TRAILING 'x' FROM 'axxx')",), ("RTRIM",)),
                "postgresql": Expect(("TRIM(TRAILING 'x' FROM 'axxx')",), ("RTRIM",)),
                "mysql": Expect(("TRIM(TRAILING 'x' FROM 'axxx')",), ("RTRIM",)),
            },
        ),
        "ora-trim-translate": Case(
            "ora-trim-translate ",
            {
                "tsql": Expect(
                    (
                        "TRIM(LEADING '0' FROM '007')",
                        "TRIM(TRAILING '!' FROM 'hi!!')",
                        "TRANSLATE('abc', 'ac', 'XZ')",
                    ),
                    ("LTRIM", "RTRIM"),
                ),
                "postgresql": Expect(
                    (
                        "TRIM(TRAILING '!' FROM 'hi!!')",
                        "TRANSLATE('abc', 'ac', 'XZ')",
                    ),
                    ("LTRIM", "RTRIM"),
                ),
                # MySQL has no TRANSLATE -> that expression degrades to NULL + warn.
                "mysql": Expect(
                    ("TRIM(TRAILING '!' FROM 'hi!!')",), ("TRANSLATE",), warn=True
                ),
            },
        ),
        "ora-lpad-multichar": Case(
            # postgresql / mysql keep LPAD (multichar pad) -> pass-through, omitted.
            "ora-lpad-multichar ",
            {"tsql": Expect(("REPLICATE('xy', 5)",), ("LPAD",))},
        ),
        "ora-lpad-tochar": Case(
            "ora-lpad-tochar ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        "ora-substr-edge": Case(
            "ora-substr-edge ",
            {
                "tsql": Expect(
                    (
                        "SUBSTRING('hello', LEN('hello') + (-3) + 1, LEN('hello'))",
                        "SUBSTRING('hello', 1, 2)",
                    ),
                    ("SUBSTR(",),
                ),
                "postgresql": Expect(
                    (
                        "SUBSTRING('hello', LENGTH('hello') + (-3) + 1)",
                        "SUBSTRING('hello', 1, 2)",
                    ),
                    ("SUBSTR(",),
                ),
                "mysql": Expect(
                    ("SUBSTRING('hello', -3)", "SUBSTRING('hello', 1, 2)"),
                    ("SUBSTR(",),
                ),
            },
        ),
        "ora-soundex": Case(
            # tsql / mysql have SOUNDEX -> pass-through, omitted. PG has none.
            "ora-soundex ",
            {"postgresql": Expect(warn=True)},
        ),
        "ora-soundex3": Case(
            "ora-soundex3 ",
            {"postgresql": Expect(warn=True)},
        ),
        # ------------------------- math / aggregate ------------------------------
        "ora-agg-collect": Case(
            "ora-agg-collect ",
            {
                "tsql": Expect(
                    ("STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x)",), ("LISTAGG",)
                ),
                "postgresql": Expect(
                    ("STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)",), ("LISTAGG",)
                ),
                "mysql": Expect(
                    ("GROUP_CONCAT(x ORDER BY x SEPARATOR ',')",), ("LISTAGG",)
                ),
            },
        ),
        "ora-percentile": Case(
            "ora-percentile ",
            {
                "postgresql": Expect(
                    ("PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)",), ("MEDIAN",)
                ),
                "tsql": Expect(warn=True),
                "mysql": Expect(warn=True),
            },
        ),
        "ora-logexp": Case(
            # Oracle LOG(b, x) -> tsql LOG(x, b) (argument order flips); LN -> LOG.
            # postgresql / mysql keep LOG/LN as-is -> pass-through, omitted.
            "ora-logexp ",
            {"tsql": Expect(("LOG(8, 2)", "LOG(2.718)"), ("LN(",))},
        ),
        "ora-width-bucket": Case(
            # postgresql has WIDTH_BUCKET -> pass-through, omitted.
            "ora-width-bucket ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        "ora-trig": Case(
            # postgresql accepts COSH/SINH/TANH -> pass-through, omitted.
            "ora-trig ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        "ora-trig-suite": Case(
            "ora-trig-suite ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        "ora-regex-suite": Case(
            # postgresql has the REGEXP_* family -> pass-through, omitted.
            "ora-regex-suite ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        "ora-regexp-cnt": Case(
            "ora-regexp-cnt ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        "ora-regexp-count": Case(
            "ora-regexp-count ",
            {"tsql": Expect(warn=True), "mysql": Expect(warn=True)},
        ),
        # ------------------------------- DDL / procedural -------------------------
        "ora-fk-and-check": Case(
            "ora-fk-and-check ",
            {
                "tsql": Expect(
                    ("id BIGINT", "CONSTRAINT fk2 CHECK (pid > 0)"), ("NUMBER",)
                ),
                "postgresql": Expect(("id BIGINT",), ("NUMBER",)),
                "mysql": Expect(("id BIGINT",), ("NUMBER",)),
            },
        ),
        "ora-gen-expr": Case(
            "ora-gen-expr ",
            {
                "tsql": Expect(
                    ("hyp AS (SQRT(a * a + b * b))",), ("GENERATED ALWAYS",)
                ),
                "postgresql": Expect(
                    ("GENERATED ALWAYS AS (SQRT(a * a + b * b)) STORED",), ("NUMBER",)
                ),
                "mysql": Expect(
                    ("hyp BIGINT GENERATED ALWAYS AS (SQRT(a * a + b * b))",),
                    ("NUMBER",),
                ),
            },
        ),
        "ora-insert-append": Case(
            # The /*+ APPEND */ hint is advisory and dropped (warns); the executable
            # signal is NUMBER -> BIGINT and FROM DUAL removal.
            "ora-insert-append ",
            {
                "tsql": Expect(("a BIGINT",), ("NUMBER", "FROM DUAL")),
                "postgresql": Expect(("a BIGINT",), ("NUMBER", "FROM DUAL")),
                "mysql": Expect(("a BIGINT",), ("NUMBER",)),
            },
        ),
        "ora-for-update-nowait": Case(
            # postgresql / mysql keep FOR UPDATE NOWAIT -> pass-through, omitted.
            "ora-for-update-nowait ",
            {"tsql": Expect(absent=("FOR UPDATE",), warn=True)},
        ),
        "ora-recursive-func": Case(
            "ora-recursive-func ",
            {
                "tsql": Expect(
                    ("@n * dbo.f(@n - 1)", "RETURN NULL"), ("RETURN NUMBER",)
                ),
                "postgresql": Expect(
                    ("LANGUAGE plpgsql", "RETURNS NUMERIC"), ("RETURN NUMBER",)
                ),
                "mysql": Expect(
                    ("DELIMITER $$", "RETURNS DECIMAL"), ("RETURN NUMBER",)
                ),
            },
        ),
        # BLUE 2026-07-30: row-value IN expanded to OR-of-AND-pairs on T-SQL
        # (neighbour of pg-row-value-comparison; PG/MySQL keep the native form).
        "reda-ora-rowvalue-in": Case(
            "reda-ora-rowvalue-in ",
            {
                "tsql": Expect(
                    ("(a = 1 AND b = 2) OR (a = 3 AND b = 4)",),
                    ("(a, b) IN",),
                ),
            },
        ),
        # BLUE 2026-07-30 (lying-warning): Oracle ``||`` treats NULL as ''; a
        # provably-NULL operand (CAST(NULL AS ...)) is now dropped so the value
        # survives ('a'||'b' = 'ab' everywhere), not just a bare NULL literal.
        "reda-ora-concat-null-cast": Case(
            "reda-ora-concat-null-cast ",
            {
                "postgresql": Expect(("'a' || 'b'",), ("CAST(NULL",)),
                "tsql": Expect(("'a' + 'b'",), ("CAST(NULL",)),
                "mysql": Expect(("CONCAT('a', 'b')",), ("CAST(NULL",)),
            },
        ),
        # BLUE 2026-07-30 (lying-warning): REGEXP_LIKE maps to PG ``~`` and MySQL
        # REGEXP (both live-verified); only T-SQL genuinely lacks POSIX regex and
        # degrades to a warned carrier. Previously ALL three were falsely dropped.
        "reda-ora-regexp-like": Case(
            "reda-ora-regexp-like ",
            {
                "postgresql": Expect(
                    ("a ~ '^[0-9]+$'",), ("REGEXP_LIKE", "unmapped operator")
                ),
                "mysql": Expect(
                    ("a REGEXP '^[0-9]+$'",), ("REGEXP_LIKE", "unmapped operator")
                ),
                "tsql": Expect(warn=True),
            },
        ),
    }
)


# Cases whose current HEAD output is questionable — recorded with evidence, NOT
# blessed by an assertion (per the challenge skill: a suspect gets documented, a
# fix belongs to a src/ change, and blessing wrong output would lock in a defect).
SUSPECT_CASES: dict[str, str] = {}


_PARAMS = [
    pytest.param(case_id, target, id=f"{case_id}-{target}")
    for case_id, case in CASES.items()
    for target in _ALL3
    if target in case.targets and not case.targets[target].vacuous()
]


def test_no_vacuous_expectations() -> None:
    """Every declared expectation must assert something (else it passes under the
    identity transpiler and silently dilutes the mutation gate)."""
    vacuous = [
        f"{cid}/{t}"
        for cid, case in CASES.items()
        for t, exp in case.targets.items()
        if exp.vacuous()
    ]
    assert not vacuous, f"vacuous expectations: {vacuous}"


def test_every_case_keyword_resolves() -> None:
    """Each case keyword must still match a live block (a renamed/removed case
    fails loudly instead of silently skipping)."""
    missing = []
    for cid, case in CASES.items():
        try:
            _case("challenge_oracle.sql", case.kw)
        except KeyError:
            missing.append(cid)
    assert not missing, f"case keyword no longer resolves: {missing}"


@pytest.mark.parametrize("case_id,target", _PARAMS)
def test_ora_case(case_id: str, target: str) -> None:
    case = CASES[case_id]
    block = _case("challenge_oracle.sql", case.kw)
    result = Transpiler().transpile(block, source=_SOURCE, target=target)
    exp = case.targets[target]
    body = _body(result.sql)
    if exp.warn:
        assert (
            result.warnings
        ), f"{case_id} -> {target}: expected a warning\n{result.sql}"
        assert (
            "UNIQUE:" in result.sql
        ), f"{case_id} -> {target}: expected a UNIQUE carrier\n{result.sql}"
    for tok in exp.present:
        assert tok in body, f"{case_id} -> {target}: missing {tok!r}\n{result.sql}"
    for tok in exp.absent:
        assert tok not in body, f"{case_id} -> {target}: leaked {tok!r}\n{result.sql}"
