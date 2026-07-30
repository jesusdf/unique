# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Dedicated per-case assertions for the ``[fixed]`` tsql-source challenge cases.

Companion to ``test_challenge.py`` (audit ``09-fix-briefs.md`` B16 step 2). The
generic loops there only prove a fixed case does not fall back to an
*unrecognized* carrier; they pass under an identity transpiler, so they carry no
identity-mutation weight. This module adds a **dedicated** present/absent
assertion for every ``[fixed]``/untagged ``challenge_sqlserver.sql`` case that
does not already have one in ``test_challenge.py`` — each one distinguishes the
correct output from the source, so it kills the identity mutant and raises the
measured kill rate.

Design (per B16 / the workflow skill's test-assertion bar):
- ``CASES`` is declarative: ``{slug: {target: spec}}``. A spec is either a
  translation (``present`` target idiom + ``absent`` source idiom, both checked
  on **comment-stripped** output so a ``UNIQUE:`` carrier or ``-- CASE`` header
  can never satisfy it) or a warned degrade (``{"degrade": True}`` → assert a
  warning AND a ``UNIQUE:`` carrier).
- One parametrized runner test per ``(case, target)`` pair — per-case
  parametrization is intentional: each dedicated assertion is its own test node,
  which is what raises the identity kill rate.
- A target whose output equals the source (native passthrough — e.g. CONCAT_WS
  on PG/MySQL, TRANSLATE on Oracle/PG) is deliberately **omitted**: it has no
  distinguishing idiom, so an assertion there would pass under the identity
  mutant and *lower* the kill rate.

Fragments below were read off the HEAD transpiler output — the assertions are a
lock-in of current behavior (they pass at HEAD), not TDD.

No case's current output was a silent loss / invalid emission, so
``SUSPECT_CASES`` is empty. (``ts-float-precision`` emits a stray
``Unsupported query option.`` line to *stdout* during transpilation, but its
returned ``.sql`` is valid Oracle — a logging nit, not an output defect.)
"""

from __future__ import annotations

import re

import pytest

from tests.integration.test_challenge import _cases, _slug
from unique.core.transpiler import Transpiler

_FIX = "challenge_sqlserver.sql"
_SOURCE = "tsql"

_BY_SLUG = {_slug(b): b for b in _cases(_FIX)}


def _block(slug: str) -> str:
    return _BY_SLUG[slug]


def _tx(slug: str, target: str):  # noqa: ANN202
    return Transpiler().transpile(_block(slug), source=_SOURCE, target=target)


def _exec(sql: str) -> str:
    """Executable text only: strip ``/* … */`` blocks and ``--`` comment lines.

    This is the comment-prose guard — present/absent fragments are matched here
    so neither the ``-- CASE`` header nor a ``UNIQUE:`` carrier comment can
    accidentally satisfy (or defeat) an assertion.
    """
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


# Every entry below transpiles at HEAD to output matching its spec. ``present``
# is the target idiom proving the translation; ``absent`` is the source idiom
# that must be gone; ``degrade`` marks a warned/annotated documented limit.
CASES: dict[str, dict[str, dict[str, object]]] = {
    # --- genuine translations ------------------------------------------------
    # func: T-SQL ``datetime + int`` adds days; MySQL numerically coerces
    # (20200101000001) and PG has no ``timestamp + int``. Rewrite to
    # DATE_ADD / ``+ INTERVAL 'n day'`` (Oracle native). All = 2020-01-02.
    "reda-ts-date-plus-int": {
        "mysql": {"present": ["DATE_ADD(", "INTERVAL 1 DAY"], "absent": ["+ 1"]},
        "postgresql": {"present": ["+ INTERVAL '1 day'"], "absent": ["+ 1 AS"]},
    },
    # crash: DATEDIFF(QUARTER,…) raised KeyError in the epoch map; now a
    # boundary count = 3 on every target (WEEK already worked). No crash carrier.
    "reda-ts-datediff-quarter": {
        "mysql": {
            "present": ["YEAR(", "* 4 + QUARTER("],
            "absent": ["DATEDIFF(QUARTER", "TRANSPILATION ERROR"],
        },
        "postgresql": {
            "present": ["EXTRACT(QUARTER FROM", "* 4 +"],
            "absent": ["DATEDIFF(QUARTER", "TRANSPILATION ERROR"],
        },
        "oracle": {
            "present": ["TO_CHAR(", "'Q'", "* 4 +"],
            "absent": ["DATEDIFF(QUARTER", "TRANSPILATION ERROR"],
        },
    },
    # func: SUBSTRING(s, start<1, len) counts leading out-of-range positions
    # toward the length on T-SQL/PG (='he'); MySQL returned '' / Oracle 'hel'.
    # Rewrite to the start=1 length-adjusted form. PG is a passthrough (='he').
    "reda-ts-substring-zero-start": {
        "mysql": {"present": ["SUBSTR('hello', 1, 2)"], "absent": [", 0, 3)"]},
        "oracle": {"present": ["SUBSTR('hello', 1, 2)"], "absent": [", 0, 3)"]},
    },
    "ts-bitops": {
        "oracle": {"present": ["BITAND(5, 3)", "-(5) - 1"], "absent": ["5 & 3", "~5"]},
        "postgresql": {"present": ["5 # 3"], "absent": ["5 ^ 3"]},
        "mysql": {"present": ["CAST(~5 AS SIGNED)"], "absent": [", ~5"]},
    },
    "ts-cast-trycast": {
        "oracle": {
            "present": ["VARCHAR2(10)", "DEFAULT NULL ON CONVERSION ERROR"],
            "absent": ["TRY_CAST", "CONVERT("],
        },
        "postgresql": {
            "present": ["CAST(CURRENT_TIMESTAMP AS DATE)"],
            "absent": ["TRY_CAST", "GETDATE", "CONVERT("],
        },
        "mysql": {
            "present": ["CAST(123 AS CHAR(10))", "CAST(CURRENT_TIMESTAMP AS DATE)"],
            "absent": ["TRY_CAST", "GETDATE"],
        },
    },
    "ts-cursor": {
        "oracle": {
            "present": ["CURSOR V_C IS", "WHILE V_C%FOUND LOOP"],
            "absent": ["@@FETCH_STATUS"],
        },
        "postgresql": {
            "present": ["v_c CURSOR FOR", "WHILE FOUND LOOP"],
            "absent": ["@@FETCH_STATUS"],
        },
        "mysql": {
            "present": ["DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done"],
            "absent": ["@@FETCH_STATUS"],
        },
    },
    "ts-decimal-scale": {
        # Additive-only Oracle transform (bare SELECT gains FROM DUAL); no source
        # idiom is removed, so present-only. PG/MySQL are byte-identity — omitted.
        "oracle": {"present": ["FROM DUAL"]},
    },
    "ts-float-precision": {
        "oracle": {"present": ["FROM DUAL"]},
    },
    "ts-maxrecursion": {
        "oracle": {"present": ["WITH s(n) AS"], "absent": ["MAXRECURSION", "OPTION ("]},
        "postgresql": {
            "present": ["WITH RECURSIVE s AS"],
            "absent": ["MAXRECURSION", "OPTION ("],
        },
        "mysql": {
            "present": ["WITH RECURSIVE s AS"],
            "absent": ["MAXRECURSION", "OPTION ("],
        },
    },
    "ts-recursion-limit": {
        "oracle": {"present": ["WITH n(v) AS"], "absent": ["MAXRECURSION", "OPTION ("]},
        "postgresql": {
            "present": ["WITH RECURSIVE n AS"],
            "absent": ["MAXRECURSION", "OPTION ("],
        },
        "mysql": {
            "present": ["WITH RECURSIVE n AS"],
            "absent": ["MAXRECURSION", "OPTION ("],
        },
    },
    "ts-money": {
        "oracle": {
            "present": ["NUMBER(19,4)", "NUMBER(10,4)"],
            "absent": ["MONEY", "SMALLMONEY"],
        },
        "postgresql": {
            "present": ["NUMERIC(19,4)", "NUMERIC(10,4)"],
            "absent": ["MONEY", "SMALLMONEY"],
        },
        "mysql": {
            "present": ["DECIMAL(19,4)", "DECIMAL(10,4)"],
            "absent": ["MONEY", "SMALLMONEY"],
        },
    },
    "ts-month-overflow": {
        "oracle": {
            "present": ["ADD_MONTHS(DATE '2020-01-31', 1)"],
            "absent": ["DATEADD"],
        },
        "postgresql": {
            "present": ["DATE '2020-01-31' + INTERVAL '1 MONTH'"],
            "absent": ["DATEADD"],
        },
        "mysql": {
            "present": ["DATE_ADD('2020-01-31', INTERVAL 1 MONTH)"],
            "absent": ["DATEADD"],
        },
    },
    "ts-nolock-hint": {
        "oracle": {"present": ["id NUMBER(10)"], "absent": ["NOLOCK", "WITH ("]},
        "postgresql": {"present": ["FROM t"], "absent": ["NOLOCK", "WITH ("]},
        "mysql": {"present": ["FROM t"], "absent": ["NOLOCK", "WITH ("]},
    },
    "ts-replicate-space": {
        "oracle": {
            "present": ["RPAD('ab', LENGTH('ab') * 3, 'ab')", "RPAD(' ', 5)"],
            "absent": ["REPLICATE", "SPACE("],
        },
        "postgresql": {
            "present": ["REPEAT('ab', 3)", "REPEAT(' ', 5)"],
            "absent": ["REPLICATE", "SPACE("],
        },
        "mysql": {"present": ["REPEAT('ab', 3)"], "absent": ["REPLICATE"]},
    },
    "ts-select-into-temp": {
        "oracle": {
            "present": ["CREATE GLOBAL TEMPORARY TABLE t2 AS SELECT"],
            "absent": ["#t2"],
        },
        "postgresql": {"present": ["INTO TEMPORARY t2"], "absent": ["#t2"]},
        "mysql": {
            "present": ["CREATE TEMPORARY TABLE t2 AS SELECT"],
            "absent": ["#t2"],
        },
    },
    "ts-stragg-order": {
        "oracle": {
            "present": ["LISTAGG(x, ',') WITHIN GROUP (ORDER BY x DESC)"],
            "absent": ["STRING_AGG"],
        },
        "postgresql": {
            "present": ["STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x DESC)"],
            "absent": ["WITHIN GROUP"],
        },
        "mysql": {
            "present": ["GROUP_CONCAT(x ORDER BY x DESC SEPARATOR ',')"],
            "absent": ["STRING_AGG", "WITHIN GROUP"],
        },
    },
    "ts-string-agg-within": {
        "oracle": {
            "present": ["LISTAGG(x, ',') WITHIN GROUP (ORDER BY x)"],
            "absent": ["STRING_AGG"],
        },
        "postgresql": {
            "present": ["STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)"],
            "absent": ["WITHIN GROUP"],
        },
        "mysql": {
            "present": ["GROUP_CONCAT(x ORDER BY x SEPARATOR ',')"],
            "absent": ["STRING_AGG", "WITHIN GROUP"],
        },
    },
    "ts-stuff": {
        "oracle": {
            "present": ["SUBSTR('abcdef', 1, 2 - 1)", "|| 'XY' ||"],
            "absent": ["STUFF"],
        },
        "postgresql": {
            "present": ["OVERLAY('abcdef' PLACING 'XY' FROM 2 FOR 3)"],
            "absent": ["STUFF"],
        },
        "mysql": {"present": ["INSERT('abcdef', 2, 3, 'XY')"], "absent": ["STUFF"]},
    },
    "ts-trig": {
        "oracle": {
            "present": ["ATAN2(1, 1)", "(1 / TAN(1))"],
            "absent": ["ATN2", "COT("],
        },
        "postgresql": {"present": ["ATAN2(1, 1)"], "absent": ["ATN2"]},
        "mysql": {"present": ["ATAN2(1, 1)"], "absent": ["ATN2"]},
    },
    "ts-while-break-continue": {
        "oracle": {"present": ["V_I := V_I + 1", "EXIT;"], "absent": ["BREAK"]},
        "postgresql": {"present": ["v_i := v_i + 1", "EXIT;"], "absent": ["BREAK"]},
        "mysql": {
            "present": ["LEAVE loop_lbl_1", "ITERATE loop_lbl_1"],
            "absent": ["BREAK"],
        },
    },
    # --- mixed: translation on some targets, warned degrade on others --------
    "ts-default-nextval": {
        "oracle": {"present": ["s.NEXTVAL"], "absent": ["NEXT VALUE FOR"]},
        "postgresql": {"present": ["nextval('s')"], "absent": ["NEXT VALUE FOR"]},
        "mysql": {"degrade": True},
    },
    "ts-translate": {
        # Oracle/PG have native TRANSLATE (byte-identity) — omitted; only MySQL,
        # which has none, is a distinguishing (degrade) outcome.
        "mysql": {"degrade": True, "absent": ["TRANSLATE("]},
    },
    "ts-compress": {
        # MySQL has native COMPRESS (identity) — omitted.
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "ts-concat-ws": {
        # CONCAT_WS is native on PG/MySQL (identity) — only Oracle degrades.
        "oracle": {"degrade": True},
    },
    "ts-concatws2": {
        "oracle": {"degrade": True},
    },
    # --- warned degrades on every foreign target (unmapped built-in/type) -----
    **{
        slug: {t: {"degrade": True} for t in ("oracle", "postgresql", "mysql")}
        for slug in (
            "ts-cast-suite",
            "ts-char-encoding",
            "ts-checksum-agg",
            "ts-checksum-fns",
            "ts-choose",
            "ts-compress2",
            "ts-cond-all",
            "ts-conditional",
            "ts-date-bucket2",
            "ts-dyn-count",
            "ts-error-functions",
            "ts-formatmessage",
            "ts-host-db",
            "ts-is-fns",
            "ts-metadata-funcs",
            "ts-now-variants",
            "ts-pad-repeat",
            "ts-patindex",
            "ts-quotename",
            "ts-rowversion",
            "ts-session-ctx",
            "ts-soundex-diff",
            "ts-soundex3",
            "ts-spectypes",
            "ts-split-agg",
            "ts-str-func",
            "ts-str-misc",
            "ts-string-fns2",
            "ts-string-fns3",
            "ts-string-split2",
            "ts-sysdatetime",
            "ts-try-catch-raiserror",
            "ts-try-parse",
            "ts-tz-fns",
            "ts-tz-offset",
        )
    },
}

CASES.update(
    {
        # BLUE 2026-07-30 (statement/DDL-structure cluster).
        "reda-ts-fk-on-update": {
            "oracle": {"degrade": True},
            "mysql": {
                "present": [
                    "FOREIGN KEY (pid) REFERENCES p (id) "
                    "ON DELETE CASCADE ON UPDATE CASCADE"
                ],
                "absent": ["pid INT REFERENCES"],
            },
            "postgresql": {
                "present": [
                    "FOREIGN KEY (pid) REFERENCES p (id) "
                    "ON DELETE CASCADE ON UPDATE CASCADE"
                ],
                "absent": ["pid INT REFERENCES"],
            },
        },
        "reda-ts-delete-top": {
            "mysql": {"present": ["DELETE FROM t", "LIMIT 2"], "absent": ["TOP (2)"]},
            "oracle": {"present": ["ROWNUM <= 2"], "absent": ["TOP (2)"]},
            "postgresql": {
                "present": ["ctid IN (SELECT ctid FROM t WHERE a > 0 LIMIT 2)"],
                "absent": ["TOP (2)"],
            },
        },
        "reda-ts-setop-orderby": {
            "postgresql": {"present": ["EXCEPT", "ORDER BY a ASC NULLS FIRST"]},
            "oracle": {
                "present": ["MINUS", "ORDER BY a ASC NULLS FIRST"],
                "absent": ["EXCEPT"],
            },
            "mysql": {"present": ["ORDER BY a ASC"]},
        },
        # invalid: multi-table DELETE-join preserves the join per target, and
        # the case's comment (whose prose contains "output") no longer corrupts
        # the batch (guardrail-3 fix in _extract_tsql_output).
        "reda-ts-delete-join": {
            "postgresql": {
                "present": ["DELETE FROM t", "USING s", "s.flag = 1"],
                "absent": ["INNER JOIN"],
            },
            "mysql": {
                "present": ["DELETE t FROM t, s", "s.flag = 1"],
                "absent": ["INNER JOIN"],
            },
            "oracle": {
                "present": ["WHERE EXISTS (SELECT 1 FROM s", "s.flag = 1"],
                "absent": ["INNER JOIN"],
            },
        },
        "reda-ts-pivot": {
            "oracle": {
                "present": ["PIVOT (SUM(v) FOR dept IN ('A' AS A, 'B' AS B))"],
                "absent": ["IN ([A]"],
            },
            "postgresql": {
                "present": [
                    "SUM(CASE WHEN dept = 'A' THEN v END) AS A",
                    "SUM(CASE WHEN dept = 'B' THEN v END) AS B",
                ],
                "absent": ["PIVOT"],
            },
            "mysql": {
                "present": [
                    "SUM(CASE WHEN dept = 'A' THEN v END) AS A",
                    "SUM(CASE WHEN dept = 'B' THEN v END) AS B",
                ],
                "absent": ["PIVOT"],
            },
        },
        "reda-ts-for-json": {
            "postgresql": {"degrade": True},
            "oracle": {"degrade": True},
            "mysql": {"degrade": True},
        },
    }
)


# Current output is a silent loss / invalid emission (no blessing assertion).
# Empty: the HEAD sweep of all covered cases found none.
SUSPECT_CASES: dict[str, str] = {}


_PARAMS = [
    (slug, target, spec)
    for slug, targets in CASES.items()
    for target, spec in targets.items()
]


def test_all_case_slugs_resolve() -> None:
    """Every slug in ``CASES``/``SUSPECT_CASES`` must still exist in the fixture
    (catches a renamed or deleted case turning an assertion into dead weight)."""
    missing = [s for s in {**CASES, **SUSPECT_CASES} if s not in _BY_SLUG]
    assert not missing, f"stale slugs (no matching case): {missing}"


@pytest.mark.parametrize(
    "slug,target,spec",
    _PARAMS,
    ids=[f"{slug}-{target}" for slug, target, _ in _PARAMS],
)
def test_tsql_case(slug: str, target: str, spec: dict[str, object]) -> None:
    result = _tx(slug, target)
    body = _exec(result.sql)
    if spec.get("degrade"):
        assert result.warnings, f"{slug} -> {target}: expected a degrade warning"
        assert (
            "UNIQUE:" in result.sql
        ), f"{slug} -> {target}: expected a UNIQUE carrier\n{result.sql}"
    present = spec.get("present", [])
    absent = spec.get("absent", [])
    assert isinstance(present, list) and isinstance(absent, list)
    assert (
        spec.get("degrade") or present or absent
    ), f"{slug} -> {target}: spec has no assertion"
    for frag in present:
        assert frag in body, f"{slug} -> {target}: missing {frag!r}\n{result.sql}"
    for frag in absent:
        assert frag not in body, f"{slug} -> {target}: leaked {frag!r}\n{result.sql}"
