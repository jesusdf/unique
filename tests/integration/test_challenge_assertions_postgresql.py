# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Dedicated per-case assertions for the PostgreSQL-source challenge corpus.

``tests/integration/test_challenge.py`` guards ``challenge_postgresql.sql`` with
generic looping checks (no unrecognized carrier / target-parse / limit warnings)
plus a hand-written class per *some* cases. This module covers the long tail:
every ``[fixed]`` PostgreSQL-source case that lacked a dedicated assertion (audit
``09-fix-briefs.md`` B16 step 2). Cases already asserted in ``test_challenge.py``
are intentionally skipped here.

Design (mirrors the mysql worker's module):

* One declarative :data:`CASES` table; a single parametrized runner per case ×
  foreign target (tsql / oracle / mysql).
* Each expectation is checked on the **comment-stripped** output (``--`` lines
  and ``/* … */`` carriers removed) so the source header prose and the carrier
  message cannot satisfy a "present"/"absent" token by accident (the comment-
  prose trap from the development-workflow skill).
* A *faithful* target asserts the target idiom is **present** AND the source
  idiom is **absent** — both fail under the identity transpiler, so each row
  raises the identity-mutation kill rate.
* A *degrade-expected* target asserts a ``validity_gate`` warning fired AND a
  ``UNIQUE:`` carrier is present (which also disappears under identity).

Targets a case handles as a pure pass-through (output byte-equal to the PG
source, e.g. ``SELECT ~0`` into T-SQL) are omitted for that case — a passthrough
has no idiom that identity would not also produce, so an assertion there would
be vacuous and dilute the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest

# Reuse the challenge loader/splitter helpers rather than re-implementing them.
from tests.integration.test_challenge import _case
from unique.core.transpiler import Transpiler

_SOURCE = "postgresql"
_ALL3 = ("tsql", "oracle", "mysql")
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
    deny_warn: tuple[str, ...] = ()  # these warning substrings must NOT fire

    def vacuous(self) -> bool:
        return not (self.present or self.absent or self.warn or self.deny_warn)


@dataclass(frozen=True)
class Case:
    kw: str  # keyword handed to test_challenge._case (matches the case header)
    targets: dict[str, Expect] = field(default_factory=dict)


def _degrade_all3(slug: str) -> Case:
    """A PG-only construct with no cross-engine form: warned carrier everywhere."""
    return Case(kw=slug + " ", targets={t: Expect(warn=True) for t in _ALL3})


# PG-only built-ins / types that degrade to a warned ``UNIQUE:`` carrier on every
# foreign target (no equivalent exists anywhere). One assertion class covers all
# three targets: the warning + carrier vanish under the identity transpiler.
_FULL_DEGRADE = (
    "pg-admin-fns",
    "pg-age",
    "pg-age-epoch",
    "pg-arr-str-roundtrip",
    "pg-attz2",
    "pg-char-encoding",
    "pg-check-array-len",
    "pg-check-jsonb",
    "pg-convert-roundtrip",
    "pg-convert-to",
    "pg-date-bin",
    "pg-encode-base64",
    "pg-encode-decode",
    "pg-fulltext",
    "pg-fulltext2",
    "pg-gen-months",
    "pg-hash-all",
    "pg-hexcast",
    "pg-inet-ops",
    "pg-interval-out",
    "pg-json-build",
    "pg-json-meta",
    "pg-json-mod",
    "pg-json-path",
    "pg-jsonb-agg",
    "pg-jsonb-build",
    "pg-jsonb-each",
    "pg-jsonb-elements-ord",
    "pg-jsonb-fns2",
    "pg-jsonb-modify",
    "pg-jsonb-path-query",
    "pg-jsonb-recordset",
    "pg-justify",
    "pg-make-date",
    "pg-network-types",
    "pg-now-fns",
    "pg-now-variants",
    "pg-num-nonnulls",
    "pg-numnulls",
    "pg-quote",
    "pg-range-types",
    "pg-scale",
    "pg-seq-use",
    "pg-serial-bit",
    "pg-setweight",
    "pg-size-funcs",
    "pg-spectypes",
    "pg-split-part",
    "pg-string-fns2",
    "pg-string-fns3",
    "pg-string-split-fns",
    "pg-string-to-array",
    "pg-trig",
    "pg-ts-headline",
    "pg-ts-rank",
    "pg-tstzrange",
    "pg-xpath",
)


CASES: dict[str, Case] = {slug: _degrade_all3(slug) for slug in _FULL_DEGRADE}

# Mixed / faithful cases: explicit per-target expectations derived from the HEAD
# output. A missing target = pure pass-through for that direction (omitted so the
# row is not vacuous under identity).
CASES.update(
    {
        # PG sequence access now maps symmetrically (red2-pg-nextval, 2026-07-30):
        # Oracle seq.NEXTVAL/CURRVAL (faithful, no warning); T-SQL NEXT VALUE FOR
        # (currval has no T-SQL form -> warned carrier); MySQL has no sequences
        # (whole-statement degrade).
        "pg-sequence": Case(
            "pg-sequence ",
            {
                "oracle": Expect(
                    ("seq.NEXTVAL", "seq.CURRVAL"),
                    ("nextval", "NEXT_VALUE_FOR"),
                ),
                "tsql": Expect(("NEXT VALUE FOR seq",), warn=True),
                "mysql": Expect(warn=True),
            },
        ),
        # invalid: a multi-field INTERVAL literal has no single-count form on
        # T-SQL/MySQL/Oracle; decompose into chained per-unit date math.
        "pg-multifield-interval-arith": Case(
            "pg-multifield-interval-arith ",
            {
                "tsql": Expect(
                    ("DATEADD(DAY, 3, DATEADD(MONTH, 2, DATEADD(YEAR, 1,",),
                    ("INTERVAL",),
                ),
                "mysql": Expect(
                    ("+ INTERVAL 1 YEAR + INTERVAL 2 MONTH + INTERVAL 3 DAY",),
                    ("1 year 2 months",),
                ),
                "oracle": Expect(
                    ("+ INTERVAL '1' YEAR + INTERVAL '2' MONTH + INTERVAL '3' DAY",),
                    ("1 year 2 months",),
                ),
            },
        ),
        "pg-avg-null": Case(
            "pg-avg-null ",
            {
                "tsql": Expect(("AVG((x) * 1.0)", "UNION ALL"), ("VALUES (1)",)),
                "oracle": Expect(("AVG(x)", "FROM DUAL"), ("VALUES (1)",)),
                "mysql": Expect(("AVG(x)", "UNION ALL"), ("VALUES (1)",)),
            },
        ),
        "pg-baseconv": Case(
            "pg-baseconv ",
            {
                "tsql": Expect(warn=True),
                "oracle": Expect(warn=True),
                "mysql": Expect(
                    ("HEX(255)", "CAST(CAST(255 AS SIGNED) AS CHAR)"), ("to_hex(255)",)
                ),
            },
        ),
        "pg-bit-negative": Case(
            "pg-bit-negative ",
            {
                "tsql": Expect(("-5 & 3",), ("(-5) & 3",)),
                "oracle": Expect(("BITAND(-5, 3)", "-(0) - 1"), ("& 3",)),
                "mysql": Expect(("CAST(~0 AS SIGNED)", "CAST(~5 AS SIGNED)")),
            },
        ),
        "pg-bitnot": Case(
            "pg-bitnot ",
            {
                "oracle": Expect(("-(0) - 1 AS r",), ("~0 AS r",)),
                "mysql": Expect(("CAST(~0 AS SIGNED) AS r",)),
            },
        ),
        "pg-bitops": Case(
            "pg-bitops ",
            {
                "tsql": Expect(("5 ^ 3",), ("5 # 3",)),
                "oracle": Expect(("BITAND(5, 3)", "POWER(2, 1)"), ("5 # 3",)),
                "mysql": Expect(("5 ^ 3", "CAST(~5 AS SIGNED)"), ("5 # 3",)),
            },
        ),
        "pg-bool-week": Case(
            "pg-bool-week ",
            {
                "tsql": Expect(
                    (
                        "CAST(1 AS BIT)",
                        "DATEPART(ISO_WEEK, CAST('2020-01-01' AS DATE))",
                    ),
                    ("::boolean",),
                ),
                "oracle": Expect(
                    (
                        "CAST(1 AS NUMBER(1))",
                        "TO_NUMBER(TO_CHAR(DATE '2020-01-01', 'IW'))",
                    ),
                    ("::boolean",),
                ),
                "mysql": Expect(
                    ("CAST(1 AS SIGNED)", "WEEK(CAST('2020-01-01' AS DATE), 3)"),
                    ("::boolean",),
                ),
            },
        ),
        "pg-bulk-insert": Case(
            "pg-bulk-insert ",
            {
                "tsql": Expect(
                    ("ROW_NUMBER() OVER", "sys.all_objects"),
                    ("generate_series(1, 1000)",),
                ),
                "oracle": Expect(
                    ("CONNECT BY LEVEL", "FROM DUAL"), ("generate_series(1, 1000)",)
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-cast-chain2": Case(
            "pg-cast-chain2 ",
            {
                "tsql": Expect(warn=True),
                "oracle": Expect(warn=True),
                "mysql": Expect(
                    ("CAST(CAST('10:00' AS TIME) AS CHAR)",), ("'10:00'::time::text",)
                ),
            },
        ),
        "pg-chr-concat": Case(
            "pg-chr-concat ",
            {
                "tsql": Expect(("CHAR(65) + CHAR(66)",), ("chr(65) || chr(66)",)),
                "oracle": Expect(("CHR(65) || CHR(66)",), ("chr(65) || chr(66)",)),
                "mysql": Expect(
                    ("CONCAT(CHAR(65 USING latin1), CHAR(66 USING latin1))",),
                    ("chr(65)",),
                ),
            },
        ),
        "pg-decimal-scale": Case(
            "pg-decimal-scale ",
            {
                "tsql": Expect(("CAST(10 AS DECIMAL(10, 4))",), ("10::numeric(10,4)",)),
                "oracle": Expect(
                    ("CAST(10 AS DECIMAL(10, 4))", "FROM DUAL"), ("10::numeric(10,4)",)
                ),
                "mysql": Expect(
                    ("CAST(10 AS DECIMAL(10, 4))",), ("10::numeric(10,4)",)
                ),
            },
        ),
        "pg-div-precision": Case(
            "pg-div-precision ",
            {"oracle": Expect(("FROM DUAL",))},
        ),
        # lying-warning: every window fn false-fired the unread-args tripwire on
        # Window.args['over'] (sqlglot 30.14). OVER is emitted faithfully; no
        # warning is due.
        "pg-window-over-falsewarn": Case(
            "pg-window-over-falsewarn ",
            {
                t: Expect(
                    present=("SUM(a) OVER (ORDER BY a ASC)",),
                    deny_warn=("unread sqlglot arg 'over' on Window",),
                )
                for t in _ALL3
            },
        ),
        # lying-warning: INSERT ... DEFAULT VALUES is honestly translated to
        # MySQL () VALUES (); the unread-args tripwire on Insert.args['default']
        # must not fire there. (Oracle still degrades with its own real warning
        # — covered separately below.)
        "pg-insert-default-values-falsewarn": Case(
            "pg-insert-default-values-falsewarn ",
            {
                "mysql": Expect(
                    present=("INSERT INTO redb_dv () VALUES ()",),
                    absent=("DEFAULT VALUES",),
                    deny_warn=("unread sqlglot arg 'default' on Insert",),
                ),
            },
        ),
        # func: PG date_trunc('week') is ISO/Monday. T-SQL DATETRUNC(week) is
        # Sunday-based -> use ISO_WEEK; Oracle 'WEEK' is invalid -> 'IW'; MySQL
        # via WEEKDAY. All three now return 2020-06-15 (live-diffed).
        "pg-date-trunc-week": Case(
            "pg-date-trunc-week ",
            {
                "tsql": Expect(
                    present=("DATETRUNC(ISO_WEEK,",), absent=("date_trunc", "week,")
                ),
                "oracle": Expect(
                    present=("TRUNC(DATE '2020-06-17', 'IW')",),
                    absent=("date_trunc", "'WEEK'"),
                ),
                "mysql": Expect(present=("INTERVAL WEEKDAY(",), absent=("date_trunc",)),
            },
        ),
        # func: PG ``date - int`` is day arithmetic; MySQL numerically coerces
        # (garbage) and T-SQL rejects it. Rewrite to DATE_SUB / DATEADD (mirrors
        # the '+' path). All targets return 2020-02-23 (live-diffed).
        "pg-date-minus-integer": Case(
            "pg-date-minus-integer ",
            {
                "tsql": Expect(present=("DATEADD(DAY, -7,",), absent=("- 7",)),
                "mysql": Expect(
                    present=("DATE_SUB(", "INTERVAL 7 DAY"), absent=("- 7",)
                ),
            },
        ),
        # func: repeat(s, n<=0) is '' on PG/MySQL; T-SQL REPLICATE returned NULL
        # (clamp the count to 0), Oracle can't store '' -> warned empty-string
        # limit. MySQL is a passthrough (already '').
        "pg-repeat-negative": Case(
            "pg-repeat-negative ",
            {
                "tsql": Expect(
                    present=("CASE WHEN ROUND(-1, 0) < 0 THEN 0",),
                    absent=("REPLICATE('ab', -1)",),
                ),
                "oracle": Expect(warn=True),
            },
        ),
        # func: 3-arg SUBSTRING with a negative start is '' on PG (positions <1
        # shorten the run); MySQL/Oracle read it from the END. Rewrite to the
        # start=1 length-adjusted form (empty here). Oracle '' -> warned limit.
        "pg-substring-neg-from-for": Case(
            "pg-substring-neg-from-for ",
            {
                "mysql": Expect(present=("''",), absent=("SUBSTR('abcde', -2, 2)",)),
                "oracle": Expect(warn=True),
            },
        ),
        # invalid: ROUND on a bare fractional literal became T-SQL ROUND(0.5, 0),
        # overflowing numeric(1,1) (error 8115). Widen the operand.
        "pg-round-bare-half-literal": Case(
            "pg-round-bare-half-literal ",
            {
                "tsql": Expect(
                    present=("ROUND(CAST(0.5 AS DECIMAL(38, 6)), 0)",),
                    absent=("ROUND(0.5, 0)",),
                ),
            },
        ),
        # invalid: a boolean predicate cast to int — T-SQL/Oracle have no boolean
        # value type, so emit the 1/0 CASE form (MySQL takes it natively).
        "pg-bool-to-int-cast": Case(
            "pg-bool-to-int-cast ",
            {
                "tsql": Expect(
                    present=("CASE WHEN a > 1 THEN 1 ELSE 0 END",),
                    absent=("CAST(a > 1 AS",),
                ),
                "oracle": Expect(
                    present=("CASE WHEN a > 1 THEN 1 ELSE 0 END",),
                    absent=("CAST(a > 1 AS",),
                ),
            },
        ),
        # invalid: a boolean predicate cast to TEXT — T-SQL/Oracle have no
        # boolean value type and reject the predicate as a CAST operand (156 /
        # ORA-02000 "missing AS"). PG renders a boolean text as 'true'/'false',
        # so emit that CASE form (live-verified value 'true').
        "pg-bool-repr": Case(
            "pg-bool-repr ",
            {
                "tsql": Expect(
                    present=("CASE WHEN 1 > 0 THEN 'true' ELSE 'false' END",),
                    absent=("CAST(1 > 0 AS",),
                ),
                "oracle": Expect(
                    present=("CASE WHEN 1 > 0 THEN 'true' ELSE 'false' END",),
                    absent=("CAST(1 > 0 AS",),
                ),
            },
        ),
        # composition: bool_or + FILTER — the FILTER CASE's boolean THEN-value
        # must be wrapped 1/0 on T-SQL/Oracle (the bool_agg 1/0 form composes
        # with the FILTER rewrite). Result = 1 (True).
        "pg-boolagg-filter": Case(
            "pg-boolagg-filter ",
            {
                "tsql": Expect(
                    present=("WHEN a > 5 THEN 1",),
                    absent=("FILTER", "bool_or"),
                ),
                "oracle": Expect(
                    present=("WHEN a > 5 THEN 1",),
                    absent=("FILTER", "bool_or"),
                ),
            },
        ),
        "pg-drop-default": Case(
            "pg-drop-default ",
            {
                "tsql": Expect(("sys.default_constraints",)),
                "oracle": Expect(("MODIFY a DEFAULT NULL",), ("DROP DEFAULT",)),
            },
        ),
        "pg-dttypes": Case(
            "pg-dttypes ",
            {
                "tsql": Expect(warn=True),
                "oracle": Expect(
                    ("INTERVAL DAY TO SECOND", "TIMESTAMP WITH TIME ZONE"), warn=True
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-fetch-ties2": Case(
            "pg-fetch-ties2 ",
            {
                "tsql": Expect(
                    ("TOP 5 WITH TIES", "data NVARCHAR(MAX)"),
                    ("FETCH FIRST", "data JSON"),
                ),
                "oracle": Expect(
                    ("data CLOB", "FETCH FIRST 5 ROWS WITH TIES"), ("data JSON",)
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-filter-subquery": Case(
            "pg-filter-subquery ",
            {
                "tsql": Expect(("COUNT(CASE",), ("FILTER",)),
                "oracle": Expect(("COUNT(CASE", "NUMBER(10)"), ("FILTER",)),
                "mysql": Expect(("COUNT(CASE",), ("FILTER",)),
            },
        ),
        "pg-fk-full": Case(
            "pg-fk-full ",
            {
                "tsql": Expect(
                    ("ON DELETE NO ACTION",), ("ON DELETE CASCADE",), warn=True
                ),
                "oracle": Expect(
                    ("ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED",),
                    ("ON UPDATE RESTRICT",),
                ),
            },
        ),
        "pg-float-precision": Case(
            "pg-float-precision ",
            {
                "tsql": Expect(("CAST(0.1 AS FLOAT)",), ("0.1::float",)),
                "oracle": Expect(
                    ("CAST(0.1 AS BINARY_DOUBLE)", "FROM DUAL"), ("0.1::float",)
                ),
                "mysql": Expect(("CAST(0.1 AS DOUBLE)",), ("0.1::float",)),
            },
        ),
        "pg-for-update": Case(
            "pg-for-update ",
            {
                "tsql": Expect(absent=("FOR UPDATE",), warn=True),
                "oracle": Expect(("NUMBER(10)", "FOR UPDATE")),
            },
        ),
        "pg-format2": Case(
            "pg-format2 ",
            {
                "tsql": Expect(
                    ("CONCAT_WS('|', 'a', NULL, 'b')",), ("format(",), warn=True
                ),
                "oracle": Expect(warn=True),
                "mysql": Expect(
                    ("CONCAT_WS('|', 'a', NULL, 'b')",), ("format(",), warn=True
                ),
            },
        ),
        "pg-fsubstr": Case(
            "pg-fsubstr ",
            {
                "tsql": Expect(
                    ("SUBSTRING('abc', 1, LEN('abc'))",), ("substring('abc',0)",)
                ),
                "oracle": Expect(
                    ("SUBSTR('abc', 1)", "FROM DUAL"), ("substring('abc',0)",)
                ),
                "mysql": Expect(("SUBSTR('abc', 1)",), ("substring('abc',0)",)),
            },
        ),
        "pg-gencol2": Case(
            "pg-gencol2 ",
            {
                "tsql": Expect(
                    ("c INT IDENTITY(1,1)", "b AS (a * 2)"),
                    ("GENERATED ALWAYS AS IDENTITY",),
                ),
                "oracle": Expect(
                    ("NUMBER(10) GENERATED ALWAYS AS IDENTITY",), ("INT GENERATED",)
                ),
                "mysql": Expect(
                    ("c INT AUTO_INCREMENT", "KEY (`c`)"), ("AS IDENTITY",)
                ),
            },
        ),
        "pg-grouping-sets2": Case(
            "pg-grouping-sets2 ",
            {
                "tsql": Expect(("data NVARCHAR(MAX)", "GROUPING(id)"), ("data JSON",)),
                "oracle": Expect(("data CLOB", "GROUPING(id)"), ("data JSON",)),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-groups2": Case(
            "pg-groups2 ",
            {
                "tsql": Expect(("data NVARCHAR(MAX)",), ("data JSON", "GROUPS")),
                "oracle": Expect(("data CLOB",), ("data JSON",)),
                # A GROUPS window frame has no MySQL form; it degrades to a
                # warned NULL carrier (was silently emitting an invalid GROUPS).
                "mysql": Expect(("id, n, NULL",), ("GROUPS",), warn=True),
            },
        ),
        "pg-left-round": Case(
            "pg-left-round ",
            {
                "tsql": Expect(("CAST(ROUND(2.9, 0) AS INT)",), ("2.9::int",)),
                "oracle": Expect(
                    ("SUBSTR('hello', 1, CAST(2.9 AS INT))",), ("2.9::int",)
                ),
                "mysql": Expect(("CAST(2.9 AS SIGNED)",), ("2.9::int",)),
            },
        ),
        "pg-like-escape": Case(
            "pg-like-escape ",
            {t: Expect(warn=True) for t in _ALL3},
        ),
        "pg-ltrim-set": Case(
            "pg-ltrim-set ",
            {
                "tsql": Expect(("TRIM(LEADING 'x' FROM 'xxabc')",), ("ltrim('xxabc'",)),
                "oracle": Expect(
                    ("LTRIM('xxabc', 'x')", "FROM DUAL"), ("ltrim('xxabc'",)
                ),
                "mysql": Expect(
                    ("TRIM(LEADING 'x' FROM 'xxabc')",), ("ltrim('xxabc'",)
                ),
            },
        ),
        "pg-md5": Case(
            "pg-md5 ",
            {
                "tsql": Expect(("HASHBYTES('MD5', 'abc')",), ("MD5('abc')",)),
                "oracle": Expect(("STANDARD_HASH('abc', 'MD5')",), ("MD5('abc')",)),
            },
        ),
        "pg-mod-decimal": Case(
            "pg-mod-decimal ",
            {
                "tsql": Expect(
                    ("10 % CAST(3.5 AS DECIMAL(38, 10))",), ("3.5::numeric",)
                ),
                "oracle": Expect(
                    ("MOD(10, CAST(3.5 AS DECIMAL(38, 10)))", "FROM DUAL"),
                    ("3.5::numeric",),
                ),
                "mysql": Expect(
                    ("10 % CAST(3.5 AS DECIMAL(38, 10))",), ("3.5::numeric",)
                ),
            },
        ),
        "pg-named-window2": Case(
            "pg-named-window2 ",
            {
                "tsql": Expect(
                    ("LAG(n) OVER (PARTITION BY s ORDER BY id ASC)",), ("OVER w",)
                ),
                "oracle": Expect(
                    ("LAG(n) OVER (PARTITION BY s ORDER BY id ASC)", "VARCHAR2(50)"),
                    ("OVER w",),
                ),
                "mysql": Expect(
                    ("LAG(n) OVER (PARTITION BY s ORDER BY id ASC)",), ("OVER w",)
                ),
            },
        ),
        "pg-num-to-str": Case(
            "pg-num-to-str ",
            {
                "tsql": Expect(
                    ("CAST(5.50 AS VARCHAR(MAX))", "CONCAT('n=', 5)"), ("5.50::text",)
                ),
                "oracle": Expect(
                    ("CAST(5.50 AS VARCHAR2(4000))", "'n=' || 5"), ("5.50::text",)
                ),
                "mysql": Expect(
                    ("CAST(5.50 AS CHAR)", "CONCAT('n=', 5)"), ("5.50::text",)
                ),
            },
        ),
        "pg-pad-repeat": Case(
            "pg-pad-repeat ",
            {
                "tsql": Expect(
                    ("REPLICATE('0', 3)", "REVERSE('abc')"), ("lpad('7',3,'0')",)
                ),
                "oracle": Expect(
                    ("LPAD('7', 3, '0')", "RPAD('ab', LENGTH('ab') * 3, 'ab')"),
                    ("lpad('7',3,'0')",),
                ),
                "mysql": Expect(
                    ("LPAD('7', 3, '0')", "REPEAT('ab', 3)"), ("lpad('7',3,'0')",)
                ),
            },
        ),
        "pg-pi-fns": Case(
            "pg-pi-fns ",
            {
                "tsql": Expect(
                    ("ROUND(CAST(PI() AS DECIMAL(38, 10)), 4, 1)",), ("trunc(pi()",)
                ),
                "oracle": Expect(
                    ("ACOS(-1)", "TRUNC(CAST(ACOS(-1) AS DECIMAL(38, 10)), 4)"),
                    ("pi()",),
                ),
                "mysql": Expect(
                    ("TRUNCATE(CAST(PI() AS DECIMAL(38, 10)), 4)",), ("trunc(pi()",)
                ),
            },
        ),
        "pg-recursive-func": Case(
            "pg-recursive-func ",
            {
                "tsql": Expect(("@n * dbo.f(@n - 1)", "RETURN NULL"), ("n * f(n-1)",)),
                "oracle": Expect(
                    ("CREATE OR REPLACE FUNCTION",), ("LANGUAGE plpgsql",)
                ),
                "mysql": Expect(("DELIMITER $$",), ("LANGUAGE plpgsql",)),
            },
        ),
        "pg-regexp-cnt": Case(
            "pg-regexp-cnt ",
            {
                "tsql": Expect(warn=True),
                "oracle": Expect(
                    (
                        "REGEXP_COUNT('a1b2', '[0-9]')",
                        "REGEXP_INSTR('a1b2', '[0-9]', 1, 2)",
                    )
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-repeat-left-right": Case(
            "pg-repeat-left-right ",
            {
                "tsql": Expect(("REPLICATE('ab', 3)",), ("REPEAT('ab', 3)",)),
                "oracle": Expect(warn=True),
            },
        ),
        "pg-stragg-order": Case(
            "pg-stragg-order ",
            {
                "tsql": Expect(
                    ("STRING_AGG(CAST(x AS NVARCHAR(MAX)), ',') WITHIN GROUP",),
                    ("string_agg(x::text",),
                ),
                "oracle": Expect(
                    ("LISTAGG(CAST(x AS VARCHAR2(4000)), ',') WITHIN GROUP",),
                    ("string_agg",),
                ),
                "mysql": Expect(
                    ("GROUP_CONCAT(CAST(x AS CHAR) ORDER BY x SEPARATOR ',')",),
                    ("string_agg",),
                ),
            },
        ),
        "pg-tochar-iso": Case(
            "pg-tochar-iso ",
            {
                "tsql": Expect(
                    ("FORMAT(CAST('2020-06-15 14:30:45' AS DATETIME2)",), ("to_char(",)
                ),
                "oracle": Expect(
                    ("TO_CHAR(TIMESTAMP '2020-06-15 14:30:45'",), ("to_char(",)
                ),
                "mysql": Expect(
                    (
                        "DATE_FORMAT(CAST('2020-06-15 14:30:45' AS DATETIME), "
                        "'%Y-%m-%dT%H:%i:%s')",
                    ),
                    ("to_char(",),
                ),
            },
        ),
        "pg-translate": Case(
            "pg-translate ",
            {
                "oracle": Expect(("FROM DUAL",)),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-trim-both-chars": Case(
            "pg-trim-both-chars ",
            {
                "tsql": Expect(("TRIM('x' FROM 'xxabcxx')",), ("TRIM(BOTH",)),
                "oracle": Expect(
                    ("LTRIM(RTRIM('xxabcxx', 'x'), 'x')",), ("TRIM(BOTH",)
                ),
            },
        ),
        "pg-trim-translate": Case(
            "pg-trim-translate ",
            {
                "tsql": Expect(
                    ("TRIM('x' FROM 'xxhixx')", "TRANSLATE('abc', 'ac', 'XZ')"),
                    ("trim(both 'x'",),
                ),
                "oracle": Expect(
                    (
                        "LTRIM(RTRIM('xxhixx', 'x'), 'x')",
                        "TRANSLATE('abc', 'ac', 'XZ')",
                    ),
                    ("trim(both",),
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "pg-width-bucket": Case(
            "pg-width-bucket ",
            {
                "tsql": Expect(warn=True),
                "oracle": Expect(
                    ("WIDTH_BUCKET(5, 0, 10, 5)",), ("width_bucket(5, 0, 10, 5)",)
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "pg15-merge": Case(
            "pg15-merge ",
            {
                "tsql": Expect(("data NVARCHAR(MAX)", "t.id = s.id"), ("data JSON",)),
                "oracle": Expect(("data CLOB", "ON (t.id = s.id)"), ("data JSON",)),
                "mysql": Expect(warn=True),
            },
        ),
        "po-order-strings": Case(
            "po-order-strings ",
            {
                "tsql": Expect(
                    ("COLLATE Latin1_General_BIN2",), ("VALUES ('banana')",)
                ),
                "oracle": Expect(("FROM DUAL",), ("VALUES ('banana')",)),
                "mysql": Expect(("COLLATE utf8mb4_bin",), ("VALUES ('banana')",)),
            },
        ),
        "postgresql-drop2-100": Case(
            "drop2-100",
            {
                "tsql": Expect(("IDENTITY(100,5)",), ("GENERATED BY DEFAULT",)),
                "oracle": Expect(
                    ("NUMBER(10) GENERATED BY DEFAULT AS IDENTITY",), ("INT GENERATED",)
                ),
                "mysql": Expect(warn=True),
            },
        ),
        "postgresql-drop4-by": Case(
            "drop4-by",
            {
                "tsql": Expect(
                    ("a INT IDENTITY(1,1)",), ("GENERATED BY DEFAULT AS IDENTITY",)
                ),
                "oracle": Expect(
                    ("a NUMBER(10) GENERATED BY DEFAULT AS IDENTITY",), ("a INT",)
                ),
                "mysql": Expect(("a INT AUTO_INCREMENT",), ("GENERATED BY DEFAULT",)),
            },
        ),
        "postgresql-drop4-collate": Case(
            "drop4-collate",
            {t: Expect(warn=True) for t in _ALL3},
        ),
        "postgresql-drop4-match": Case(
            "drop4-match",
            {
                # Oracle silently omits MATCH FULL — see SUSPECT_CASES; not asserted.
                # The inline column-constraint REFERENCES is promoted to an
                # out-of-line FOREIGN KEY that keeps MATCH FULL (a swap identity
                # cannot reproduce; source has the inline ``REFERENCES p(id)``).
                "tsql": Expect(("FOREIGN KEY (pid) REFERENCES p (id) MATCH FULL",)),
                "mysql": Expect(("FOREIGN KEY (pid) REFERENCES p (id) MATCH FULL",)),
            },
        ),
        "postgresql-qdrop-for": Case(
            "qdrop-for",
            {
                "tsql": Expect(absent=("FOR UPDATE",), warn=True),
                "oracle": Expect(("AS v(x) FOR UPDATE",)),
                "mysql": Expect(("AS v FOR UPDATE",)),
            },
        ),
        "postgresql-qdrop-rows": Case(
            "qdrop-rows",
            {
                "tsql": Expect(("UNION ALL",), ("VALUES (1)",)),
                "oracle": Expect(("UNION ALL", "FROM DUAL"), ("VALUES (1)",)),
                "mysql": Expect(("UNION ALL",), ("VALUES (1)",)),
            },
        ),
        # func: DISTINCT ON (a) keeps one row per a (first by ORDER BY); a plain
        # SELECT DISTINCT would keep every (a,b) pair. Rewrite to ROW_NUMBER()
        # OVER (PARTITION BY a ORDER BY …) = 1 in a derived table. All = 2 rows.
        "pg-distinct-on": Case(
            "pg-distinct-on ",
            {
                "tsql": Expect(
                    ("ROW_NUMBER() OVER (PARTITION BY a ORDER BY", "uq_rn = 1"),
                    ("DISTINCT",),
                ),
                "mysql": Expect(
                    ("ROW_NUMBER() OVER (PARTITION BY a ORDER BY", "uq_rn = 1"),
                    ("DISTINCT",),
                ),
                "oracle": Expect(
                    ("ROW_NUMBER() OVER (PARTITION BY a ORDER BY", "uq_rn = 1"),
                    ("DISTINCT",),
                ),
            },
        ),
    }
)


# Cases whose current HEAD output is questionable — recorded with evidence, NOT
# blessed by an assertion (per the challenge skill: a suspect gets documented, a
# fix belongs to a src/ change, and blessing wrong output would lock in a defect).
SUSPECT_CASES: dict[str, str] = {
    "postgresql-drop4-match/oracle": (
        "MATCH FULL is dropped from the FK with no warning (RED's original "
        "'silent clause drop' finding). Believed safe because MATCH FULL only "
        "differs from MATCH SIMPLE for multi-column FKs with some NULL columns, "
        "and this FK is single-column — so the drop is semantically a no-op. Left "
        "unasserted rather than blessed: if a multi-column MATCH FULL case is ever "
        "added, the omission would be a real defect."
    ),
}


# BLUE 2026-07-30 (statement/DDL-structure cluster) — these are REAL, executed
# assertions; they were mistakenly appended to SUSPECT_CASES (a str-valued dict
# the runner never iterates), leaving them dead. Moved into CASES (2026-07-30).
CASES.update(
    {
        "pg-groupby-multi-cube-rollup": Case(
            "pg-groupby-multi-cube-rollup ",
            {
                "tsql": Expect(
                    ("GROUP BY CUBE(a, b), ROLLUP(c)", "UNION ALL"), ("VALUES",)
                ),
                "oracle": Expect(
                    ("GROUP BY CUBE(a, b), ROLLUP(c)", "FROM DUAL"), ("VALUES",)
                ),
                "mysql": Expect(("GROUP BY a, b, c",), warn=True),
            },
        ),
        "pg-group-by-ordinal": Case(
            "pg-group-by-ordinal ",
            {
                "tsql": Expect(("GROUP BY a",), ("GROUP BY 1",)),
                "oracle": Expect(("GROUP BY a",), ("GROUP BY 1",)),
            },
        ),
        "pg-fk-onupdate-oracle": Case(
            "pg-fk-onupdate-oracle ",
            {
                "oracle": Expect(warn=True),
                "mysql": Expect(
                    ("FOREIGN KEY (pid) REFERENCES redb_p (id) ON UPDATE CASCADE",),
                    ("pid INT REFERENCES",),
                ),
            },
        ),
        "pg-serial-identity-oracle": Case(
            "pg-serial-identity-oracle ",
            {
                "oracle": Expect(
                    ("id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",),
                    ("SERIAL",),
                ),
            },
        ),
        "pg-temp-oncommit-oracle": Case(
            "pg-temp-oncommit-oracle ",
            {
                "oracle": Expect(
                    ("GLOBAL TEMPORARY TABLE redb_tmp", "ON COMMIT PRESERVE ROWS"),
                    ("CREATE TEMP TABLE",),
                ),
            },
        ),
        "pg-row-value-comparison": Case(
            "pg-row-value-comparison ",
            {
                "tsql": Expect(("a > 1 OR (a = 1 AND (b > 5))",), ("(a, b) > (1, 5)",)),
            },
        ),
    }
)


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
            _case("challenge_postgresql.sql", case.kw)
        except KeyError:
            missing.append(cid)
    assert not missing, f"case keyword no longer resolves: {missing}"


@pytest.mark.parametrize("case_id,target", _PARAMS)
def test_pg_case(case_id: str, target: str) -> None:
    case = CASES[case_id]
    block = _case("challenge_postgresql.sql", case.kw)
    result = Transpiler().transpile(block, source=_SOURCE, target=target)
    exp = case.targets[target]
    body = _body(result.sql)
    if exp.warn:
        assert (
            result.warnings
        ), f"{case_id} -> {target}: expected a warning\n{result.sql}"
        assert (
            "UNIQUE-" in result.sql
        ), f"{case_id} -> {target}: expected a UNIQUE carrier\n{result.sql}"
    for tok in exp.present:
        assert tok in body, f"{case_id} -> {target}: missing {tok!r}\n{result.sql}"
    for tok in exp.absent:
        assert tok not in body, f"{case_id} -> {target}: leaked {tok!r}\n{result.sql}"
    msgs = [
        w if isinstance(w, str) else getattr(w, "message", str(w))
        for w in result.warnings
    ]
    for bad in exp.deny_warn:
        assert not any(
            bad in m for m in msgs
        ), f"{case_id} -> {target}: false warning {bad!r} fired\n{msgs}"
