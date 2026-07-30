# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Dedicated per-case assertions for the ``challenge_mysql.sql`` corpus.

``tests/integration/test_challenge.py`` guards most ``[fixed]`` MySQL-source
cases only with the generic carrier-absence loop (``test_fixed_cases_have_no_
unrecognized_construct``) — a check that passes under an identity transpiler and
so cannot detect a broken translation. This module upgrades every ``[fixed]``
MySQL case that lacks a dedicated assertion elsewhere to a *focused* per-target
check: at least one PRESENT fragment (the target idiom that proves the
translation happened) AND one ABSENT fragment (the source idiom that must be
gone), on comment-stripped output. Cases whose correct outcome on a target is a
warned degrade assert the carrier + warning instead.

Structure (audit ``09-fix-briefs.md`` B16 step 2): a declarative ``CASES`` table
keyed by the case slug, one entry per foreign target, driven by a per-target
parametrized runner. These are per-case dedicated assertions (unlike the generic
loops in ``test_challenge.py``), so per-case parametrization is correct and every
runner item fails under the identity transpiler.

The table locks in *current-good* HEAD behaviour (not TDD of new behaviour); it
was built by transpiling each case and reading the output. Cases whose current
output looked wrong are parked in ``SUSPECT_CASES`` and skipped for the architect
to triage — never blessed with an assertion.
"""

from __future__ import annotations

import re
from typing import cast

import pytest

from tests.integration.test_challenge import _cases, _slug, _status
from unique.core.transpiler import Transpiler

_FNAME = "challenge_mysql.sql"
_SOURCE = "mysql"

# slug -> case block (first occurrence wins; slugs are unique among the fixed
# cases this module covers). Reuses test_challenge's loader/splitter.
_BLOCKS: dict[str, str] = {}
for _b in _cases(_FNAME):
    if _status(_b) == "fixed":
        _BLOCKS.setdefault(_slug(_b), _b)

# A handful of case headers share a ``_slug`` prefix (e.g. mysql-drop-CHECK /
# -GENERATED / -'note' all slug to "mysql-drop"). Resolve those by a unique
# source-text marker so the CASES key selects the intended block.
_SLUG_MARKER: dict[str, str] = {"mysql-drop-check": "email VARCHAR(255) CHECK"}


def _block_for(slug: str) -> str:
    if slug in _SLUG_MARKER:
        marker = _SLUG_MARKER[slug]
        for block in _cases(_FNAME):
            if _status(block) == "fixed" and marker in block:
                return block
        raise KeyError(f"no fixed case containing {marker!r} in {_FNAME}")
    return _BLOCKS[slug]


_CARRIER_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _exe(sql: str) -> str:
    """Executable text: drop ``--`` comment lines AND ``/* … */`` carrier spans
    so a PRESENT/ABSENT fragment can never match comment prose (the comment-prose
    trap from the workflow skill's test-assertion bar)."""
    no_line = "\n".join(
        ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")
    )
    return _CARRIER_RE.sub("", no_line)


# Cases whose HEAD output looks wrong (silent loss / invalid). Empty at authoring
# time — every covered case produced faithful output or an honest warned degrade.
SUSPECT_CASES: dict[str, str] = {}


# For each slug, per target either {"present": [...], "absent": [...]} (a real
# translation) or {"degrade": True} (correct outcome is a warned carrier). A
# target with no meaningful transformation (output ~= source) is omitted.
CASES: dict[str, dict[str, dict[str, object]]] = {
    "my-adddate": {
        "tsql": {"present": ["DATEADD(DAY, 30, '2020-01-01')"], "absent": ["ADDDATE"]},
        "oracle": {"present": ["NUMTODSINTERVAL(30, 'DAY')"], "absent": ["ADDDATE"]},
        "postgresql": {"present": ["INTERVAL '30 DAY'"], "absent": ["ADDDATE"]},
    },
    "my-aes": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-agg-boolean": {
        "tsql": {"present": ["AVG((x > 1) * 1.0)"], "absent": ["AVG(x > 1)"]},
    },
    "my-arr-json": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-avg-precision2": {
        "tsql": {"present": ["AVG((x) * 1.0)"], "absent": ["AVG(x)"]},
    },
    "my-base64": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-baseconv": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-benchmark": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-binary-substr": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-bitand-prec": {
        "tsql": {"present": ["10 & (6 + 1)"], "absent": ["10 & 6 + 1"]},
        "oracle": {"present": ["BITAND(10, (6 + 1))"], "absent": ["10 & 6"]},
        "postgresql": {"present": ["10 & (6 + 1)"], "absent": ["10 & 6 + 1"]},
    },
    "my-blob-length": {
        "tsql": {"present": ["VARBINARY(MAX)"], "absent": ["BLOB"]},
        "postgresql": {"present": ["data BYTEA"], "absent": ["BLOB"]},
    },
    "my-cast-int": {
        "tsql": {
            "present": ["CAST(ROUND(2.7, 0) AS BIGINT)"],
            "absent": ["CAST(2.7 AS SIGNED)"],
        },
        "oracle": {"present": ["CAST(2.7 AS INTEGER)"], "absent": ["SIGNED"]},
        "postgresql": {"present": ["CAST(2.7 AS BIGINT)"], "absent": ["SIGNED"]},
    },
    "my-cast-suite": {
        "tsql": {
            "present": ["CAST('2020-01-01' AS DATE)", "CAST(65 AS VARCHAR(8000))"],
            "absent": ["SIGNED"],
        },
        "oracle": {
            "present": ["DATE '2020-01-01'", "CAST(65 AS VARCHAR2(4000))"],
            "absent": ["SIGNED"],
        },
        "postgresql": {"present": ["CAST(65 AS TEXT)"], "absent": ["SIGNED"]},
    },
    "my-char-encoding": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-compress": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-compress2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-computed-json": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    # func: MySQL CONCAT propagates NULL (any NULL arg -> NULL) while PG/T-SQL/
    # Oracle CONCAT ignore NULL. A runtime-nullable operand is now NULL-guarded
    # with a CASE so the result matches MySQL (all three targets = NULL live).
    "my-concat-null-col": {
        "postgresql": {
            "present": ["WHEN a IS NULL OR b IS NULL THEN NULL", "CONCAT(a, b)"],
            "absent": [],
        },
        "tsql": {
            "present": ["WHEN a IS NULL OR b IS NULL THEN NULL", "CONCAT(a, b)"],
            "absent": [],
        },
        "oracle": {
            "present": ["WHEN a IS NULL OR b IS NULL THEN NULL", "CONCAT(a, b)"],
            "absent": [],
        },
    },
    "my-concat-ws": {
        "oracle": {"degrade": True},
    },
    # invalid: MySQL TO_DAYS lowers to DATEDIFF(x, '0000-01-01') + 1; year 0000
    # is rejected by every target (and Oracle Julian-shifts pre-1582). Rebase on
    # the post-reform epoch '1970-01-01' + 719528 = 737790 on all engines.
    "my-to-days-year-zero": {
        "postgresql": {"present": ["1970-01-01", "719528"], "absent": ["0000-01-01"]},
        "tsql": {"present": ["1970-01-01", "719528"], "absent": ["0000-01-01"]},
        "oracle": {"present": ["1970-01-01", "719528"], "absent": ["0000-01-01"]},
    },
    "my-concatws3": {
        "oracle": {"degrade": True},
    },
    "my-conv2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-convert-signed": {
        "tsql": {"present": ["CAST(123 AS BIGINT)"], "absent": ["CONVERT"]},
        "oracle": {"present": ["CAST(123 AS INTEGER)"], "absent": ["CONVERT"]},
        "postgresql": {"present": ["CAST(123 AS BIGINT)"], "absent": ["CONVERT"]},
    },
    "my-crc32": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-crypto2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-date-add-month": {
        "tsql": {
            "present": ["DATEADD(MONTH, 1, '2020-01-31')"],
            "absent": ["DATE_ADD"],
        },
        "oracle": {
            "present": ["ADD_MONTHS(DATE '2020-01-31', 1)"],
            "absent": ["DATE_ADD"],
        },
        "postgresql": {"present": ["INTERVAL '1 MONTH'"], "absent": ["DATE_ADD"]},
    },
    "my-dateadd": {
        "tsql": {
            "present": ["DATEADD(MONTH, 1, '2020-01-31')"],
            "absent": ["DATE_ADD"],
        },
        "oracle": {
            "present": ["ADD_MONTHS(DATE '2020-01-31', 1)"],
            "absent": ["DATE_ADD"],
        },
        "postgresql": {"present": ["INTERVAL '1 MONTH'"], "absent": ["DATE_SUB"]},
    },
    "my-dayparts": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-decimal-scale": {
        "tsql": {"present": ["(10.00 * 1.0 / NULLIF(3, 0))"], "absent": ["10.00/3"]},
        "postgresql": {
            "present": ["(10.00 * 1.0 / NULLIF(3, 0))"],
            "absent": ["10.00/3"],
        },
    },
    "my-div": {
        "tsql": {"present": ["(5 * 1.0 / NULLIF(2, 0))"], "absent": ["5 / 2"]},
        "postgresql": {"present": ["(5 * 1.0 / NULLIF(2, 0))"], "absent": ["5 / 2"]},
    },
    "my-div-mult2": {
        "tsql": {"present": ["(1 * 1.0 / NULLIF(3, 0)) * 3"], "absent": ["1/3*3"]},
        "postgresql": {
            "present": ["(1 * 1.0 / NULLIF(3, 0)) * 3"],
            "absent": ["1/3*3"],
        },
    },
    "my-div-precision": {
        "tsql": {"present": ["(1.0 * 1.0 / NULLIF(3, 0))"], "absent": ["1.0 / 3 AS"]},
        "postgresql": {
            "present": ["(1.0 * 1.0 / NULLIF(3, 0))"],
            "absent": ["1.0 / 3 AS"],
        },
    },
    "my-dttypes": {
        "tsql": {"present": ["DATETIME2(6)", "DATETIMEOFFSET"], "absent": ["YEAR"]},
        "oracle": {"present": ["INTERVAL DAY TO SECOND"], "absent": ["YEAR"]},
        "postgresql": {"present": ["TIMESTAMPTZ"], "absent": ["YEAR"]},
    },
    "my-elt": {
        "tsql": {
            "present": ["CASE 2 WHEN 1 THEN 'a' WHEN 2 THEN 'b' WHEN 3 THEN 'c' END"],
            "absent": ["ELT"],
        },
        "oracle": {
            "present": ["CASE 2 WHEN 1 THEN 'a' WHEN 2 THEN 'b' WHEN 3 THEN 'c' END"],
            "absent": ["ELT"],
        },
        "postgresql": {
            "present": ["CASE 2 WHEN 1 THEN 'a' WHEN 2 THEN 'b' WHEN 3 THEN 'c' END"],
            "absent": ["ELT"],
        },
    },
    "my-epoch": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-export-set": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-export-set2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-field": {
        "tsql": {
            "present": [
                "CASE 'b' WHEN 'a' THEN 1 WHEN 'b' THEN 2 WHEN 'c' THEN 3 ELSE 0 END"
            ],
            "absent": ["FIELD"],
        },
        "oracle": {
            "present": [
                "CASE 'b' WHEN 'a' THEN 1 WHEN 'b' THEN 2 WHEN 'c' THEN 3 ELSE 0 END"
            ],
            "absent": ["FIELD"],
        },
        "postgresql": {
            "present": [
                "CASE 'b' WHEN 'a' THEN 1 WHEN 'b' THEN 2 WHEN 'c' THEN 3 ELSE 0 END"
            ],
            "absent": ["FIELD"],
        },
    },
    "my-file-lock": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-fk-full": {
        "oracle": {
            "present": ["ON DELETE SET NULL"],
            "absent": ["ON UPDATE"],
        },
    },
    "my-float-precision": {
        "tsql": {"present": ["CAST(0.1 AS FLOAT)"], "absent": ["DOUBLE"]},
        "oracle": {"present": ["CAST(0.1 AS BINARY_DOUBLE)"], "absent": ["AS DOUBLE)"]},
        "postgresql": {
            "present": ["CAST(0.1 AS DOUBLE PRECISION)"],
            "absent": ["AS DOUBLE)"],
        },
    },
    "my-format-fns2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-full-select": {
        "tsql": {
            "present": ["OFFSET 5 ROWS", "FETCH NEXT 10 ROWS ONLY", "NVARCHAR(MAX)"],
            "absent": ["LIMIT"],
        },
        "oracle": {
            "present": ["FETCH FIRST 10 ROWS ONLY", "data CLOB"],
            "absent": ["LIMIT"],
        },
    },
    "my-get-format": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-get-lock": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-getformat2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-greatest-null": {
        "tsql": {
            "present": ["CASE WHEN 1 IS NULL OR NULL IS NULL OR 3 IS NULL THEN NULL"],
            "absent": ["SELECT GREATEST(1, NULL, 3) AS r"],
        },
        "postgresql": {
            "present": ["CASE WHEN 1 IS NULL OR NULL IS NULL OR 3 IS NULL THEN NULL"],
            "absent": ["SELECT GREATEST(1, NULL, 3) AS r"],
        },
    },
    "my-greatest-null2": {
        "tsql": {
            "present": ["CASE WHEN NULL IS NULL OR 1 IS NULL THEN NULL"],
            "absent": ["SELECT GREATEST(NULL, 1) AS r"],
        },
        "postgresql": {
            "present": ["CASE WHEN NULL IS NULL OR 1 IS NULL THEN NULL"],
            "absent": ["SELECT GREATEST(NULL, 1) AS r"],
        },
    },
    "my-group-concat": {
        "tsql": {
            "present": ["STRING_AGG(x, '|') WITHIN GROUP (ORDER BY x)"],
            "absent": ["GROUP_CONCAT"],
        },
        "oracle": {
            "present": ["LISTAGG(x, '|') WITHIN GROUP (ORDER BY x)"],
            "absent": ["GROUP_CONCAT"],
        },
        "postgresql": {
            "present": ["STRING_AGG(CAST(x AS TEXT), '|' ORDER BY x)"],
            "absent": ["GROUP_CONCAT"],
        },
    },
    "my-groupconcat-order": {
        "tsql": {
            "present": ["STRING_AGG(x, ',') WITHIN GROUP (ORDER BY x)"],
            "absent": ["GROUP_CONCAT"],
        },
        "oracle": {
            "present": ["LISTAGG(x, ',') WITHIN GROUP (ORDER BY x)"],
            "absent": ["GROUP_CONCAT"],
        },
        "postgresql": {
            "present": ["STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)"],
            "absent": ["GROUP_CONCAT"],
        },
    },
    "my-hash": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-hash-all": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-hex-bin": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-hexcast": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-index-fns": {
        "tsql": {
            "present": ["CASE WHEN 3 IS NULL THEN -1 WHEN 3 < 1 THEN 0"],
            "absent": ["FIELD(", "ELT("],
        },
        "oracle": {
            "present": ["CASE WHEN 3 IS NULL THEN -1 WHEN 3 < 1 THEN 0"],
            "absent": ["FIELD(", "ELT("],
        },
        "postgresql": {
            "present": ["CASE WHEN 3 IS NULL THEN -1 WHEN 3 < 1 THEN 0"],
            "absent": ["FIELD(", "ELT("],
        },
    },
    "my-inet": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-inet3": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-inet6": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-insert-oob": {
        "tsql": {
            "present": ["STUFF('abc', 10, 1, 'X')"],
            "absent": ["INSERT("],
        },
        "oracle": {
            "present": ["(SUBSTR('abc', 1, 10 - 1) || 'X' || SUBSTR('abc', 10 + 1))"],
            "absent": ["INSERT("],
        },
        "postgresql": {
            "present": ["OVERLAY('abc' PLACING 'X' FROM 10 FOR 1)"],
            "absent": ["INSERT("],
        },
    },
    "my-insert-zeropos": {
        "tsql": {
            "present": ["STUFF('abcdef', 0, 2, 'XY')"],
            "absent": ["INSERT("],
        },
        "oracle": {
            "present": ["SUBSTR('abcdef', 1, 0 - 1) || 'XY'"],
            "absent": ["INSERT("],
        },
        "postgresql": {
            "present": ["OVERLAY('abcdef' PLACING 'XY' FROM 0 FOR 2)"],
            "absent": ["INSERT("],
        },
    },
    "my-insert2": {
        "tsql": {
            "present": ["STUFF('Quadratic', 3, 4, 'What')"],
            "absent": ["INSERT("],
        },
        "oracle": {
            "present": ["SUBSTR('Quadratic', 1, 3 - 1) || 'What'"],
            "absent": ["INSERT("],
        },
        "postgresql": {
            "present": ["OVERLAY('Quadratic' PLACING 'What' FROM 3 FOR 4)"],
            "absent": ["INSERT("],
        },
    },
    "my-json-array-ops": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-arrayagg": {
        "tsql": {"degrade": True},
        "postgresql": {"present": ["JSON_AGG(x)"], "absent": ["JSON_ARRAYAGG"]},
    },
    "my-json-fns2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-keys": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-meta": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-mod": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-modify": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-search": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-json-search2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-least-greatest-null": {
        "tsql": {
            "present": ["'a' IS NULL THEN NULL ELSE LEAST(NULL, 'a')"],
            "absent": ["SELECT LEAST(NULL, 'a') AS r"],
        },
        "postgresql": {
            "present": ["'a' IS NULL THEN NULL ELSE LEAST(NULL, 'a')"],
            "absent": ["SELECT LEAST(NULL, 'a') AS r"],
        },
    },
    "my-least-null2": {
        "tsql": {
            "present": ["OR NULL IS NULL OR 3 IS NULL THEN NULL ELSE LEAST"],
            "absent": ["SELECT LEAST(1, 2, NULL, 3) AS r"],
        },
        "postgresql": {
            "present": ["OR NULL IS NULL OR 3 IS NULL THEN NULL ELSE LEAST"],
            "absent": ["SELECT LEAST(1, 2, NULL, 3) AS r"],
        },
    },
    "my-len-trio": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"present": ["BIT_LENGTH(s)"], "absent": ["CHAR_LENGTH"]},
    },
    "my-loadfile": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-locate-case": {
        "tsql": {"present": ["CHARINDEX('a', 'ABC')"], "absent": ["LOCATE"]},
        "oracle": {
            "present": ["INSTR(LOWER('ABC'), LOWER('a'))"],
            "absent": ["LOCATE"],
        },
        "postgresql": {
            "present": ["POSITION(LOWER('a') IN LOWER('ABC'))"],
            "absent": ["LOCATE"],
        },
    },
    "my-locate-empty": {
        "tsql": {
            "present": ["CASE WHEN '' = '' THEN 1 ELSE CHARINDEX('', '') END"],
            "absent": ["LOCATE"],
        },
        "oracle": {
            "present": ["COALESCE(INSTR(LOWER(''), LOWER('')), 1)"],
            "absent": ["LOCATE"],
        },
        "postgresql": {
            "present": ["POSITION(LOWER('') IN LOWER(''))"],
            "absent": ["LOCATE"],
        },
    },
    "my-locate-empty2": {
        "tsql": {
            "present": ["CASE WHEN '' = '' THEN 1 ELSE CHARINDEX('', 'abc') END"],
            "absent": ["LOCATE"],
        },
        "oracle": {
            "present": ["COALESCE(INSTR(LOWER('abc'), LOWER('')), 1)"],
            "absent": ["LOCATE"],
        },
        "postgresql": {
            "present": ["POSITION(LOWER('') IN LOWER('abc'))"],
            "absent": ["LOCATE"],
        },
    },
    "my-log-2arg": {
        "tsql": {"present": ["LOG(8, 2)"], "absent": ["LOG(2, 8)"]},
    },
    "my-logexp": {
        "tsql": {"present": ["LOG(8, 2)"], "absent": ["LOG2"]},
        "oracle": {"present": ["LOG(2, 8)", "LOG(10, 100)"], "absent": ["LOG2"]},
        "postgresql": {"present": ["LOG(2, 8)", "LOG(10, 100)"], "absent": ["LOG2"]},
    },
    "my-lpad-conv": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-lpad-multichar": {
        "tsql": {"present": ["LEFT(REPLICATE('xy', 5)"], "absent": ["LPAD"]},
    },
    "my-make-set": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-make-set2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-makedate": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-misc-num": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-mod-edge": {
        "tsql": {
            "present": ["CASE WHEN 5 = 0 THEN NULL ELSE 0 % 5 END"],
            "absent": ["MOD(0,5)"],
        },
        "oracle": {
            "present": ["CASE WHEN 5 = 0 THEN NULL ELSE MOD(0, 5) END"],
            "absent": ["MOD(0,5)"],
        },
        "postgresql": {
            "present": ["CASE WHEN 5 = 0 THEN NULL ELSE 0 % 5 END"],
            "absent": ["MOD(0,5)"],
        },
    },
    "my-mod-zero": {
        "tsql": {
            "present": ["CASE WHEN 0 = 0 THEN NULL ELSE 5 % 0 END"],
            "absent": ["5 MOD 0"],
        },
        "oracle": {
            "present": ["CASE WHEN 0 = 0 THEN NULL ELSE MOD(5, 0) END"],
            "absent": ["5 MOD 0"],
        },
        "postgresql": {
            "present": ["CASE WHEN 0 = 0 THEN NULL ELSE 5 % 0 END"],
            "absent": ["5 MOD 0"],
        },
    },
    "my-month-overflow": {
        "tsql": {
            "present": ["DATEADD(MONTH, 1, '2020-01-31')"],
            "absent": ["DATE_ADD"],
        },
        "oracle": {
            "present": ["ADD_MONTHS(DATE '2020-01-31', 1)"],
            "absent": ["DATE_ADD"],
        },
        "postgresql": {"present": ["INTERVAL '1 MONTH'"], "absent": ["DATE_ADD"]},
    },
    "my-name-const": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-now-fns": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-now-variants": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-num-to-str": {
        "tsql": {"present": ["CONCAT('b=', 1)"], "absent": ["TRUE"]},
        "oracle": {"present": ["CONCAT('b=', 1)"], "absent": ["TRUE"]},
        "postgresql": {"present": ["CONCAT('b=', 1)"], "absent": ["TRUE"]},
    },
    "my-numeric-conv": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-optimizer-hints": {
        "tsql": {
            "present": ["WHERE n > (SELECT AVG((n) * 1.0)"],
            "absent": ["QB_NAME", "SEMIJOIN"],
        },
        "oracle": {
            "present": ["WHERE n > (SELECT AVG(n)"],
            "absent": ["QB_NAME", "SEMIJOIN"],
        },
        "postgresql": {
            "present": ["WHERE n > (SELECT AVG(n)"],
            "absent": ["QB_NAME", "SEMIJOIN"],
        },
    },
    "my-pad-repeat": {
        "tsql": {"present": ["REPLICATE('ab', 3)"], "absent": ["REPEAT"]},
        "oracle": {
            "present": ["RPAD('ab', LENGTH('ab') * 3, 'ab')"],
            "absent": ["REPEAT("],
        },
        "postgresql": {"present": ["REPEAT(' ', 3)"], "absent": ["SPACE("]},
    },
    "my-period-diff": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-period2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-quote2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-rand": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-realworld-orders": {
        "tsql": {
            "present": ["IDENTITY(1,1)", "AFTER INSERT"],
            "absent": ["AUTO_INCREMENT"],
        },
        "oracle": {
            "present": ["GENERATED BY DEFAULT AS IDENTITY", ":NEW.created := SYSDATE"],
            "absent": ["AUTO_INCREMENT"],
        },
        "postgresql": {
            "present": ["SERIAL PRIMARY KEY", "EXECUTE FUNCTION trg_func()"],
            "absent": ["AUTO_INCREMENT"],
        },
    },
    "my-recursive-cte2": {
        "tsql": {"present": ["WITH seq AS ("], "absent": ["RECURSIVE"]},
        "oracle": {"present": ["WITH seq(n) AS ("], "absent": ["RECURSIVE"]},
    },
    "my-recursive-func": {
        "tsql": {"present": ["RETURN NULL;"], "absent": ["DETERMINISTIC"]},
        "oracle": {
            "present": ["CREATE OR REPLACE FUNCTION"],
            "absent": ["DETERMINISTIC"],
        },
        "postgresql": {"present": ["LANGUAGE plpgsql"], "absent": ["DETERMINISTIC"]},
    },
    "my-round-fns": {
        "tsql": {"degrade": True},
        "oracle": {"present": ["CEIL(3.2)", "TRUNC(3.567, 1)"], "absent": ["TRUNCATE"]},
        "postgresql": {
            "present": ["CEIL(3.2)", "TRUNC(3.567, 1)"],
            "absent": ["TRUNCATE"],
        },
    },
    "my-seq-concat": {
        "tsql": {"present": ["STRING_AGG(n, ',')"], "absent": ["GROUP_CONCAT"]},
        "oracle": {
            "present": [
                "LISTAGG(n, ',') WITHIN GROUP (ORDER BY n)",
                "WITH seq(n) AS (",
            ],
            "absent": ["GROUP_CONCAT"],
        },
        "postgresql": {
            "present": ["STRING_AGG(CAST(n AS TEXT), ',')"],
            "absent": ["GROUP_CONCAT"],
        },
    },
    "my-session-fns": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-set-fns": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-soundex-eq": {
        "tsql": {
            "present": ["CASE WHEN SOUNDEX('hello') = SOUNDEX('hallo') THEN 1"],
            "absent": ["SELECT SOUNDEX('hello') = SOUNDEX('hallo') AS r"],
        },
        "oracle": {
            "present": ["CASE WHEN SOUNDEX('hello') = SOUNDEX('hallo') THEN 1"],
            "absent": ["SELECT SOUNDEX('hello') = SOUNDEX('hallo') AS r"],
        },
        "postgresql": {"degrade": True},
    },
    "my-spatial": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-st-distance": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-st-geojson": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-status-funcs": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-stmt-digest": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-str-misc": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-str-null": {
        "tsql": {
            "present": ["SELECT LEN(NULL), NULL, NULL, SUBSTRING(NULL, 1, 2)"],
            "absent": ["CONCAT("],
        },
        "oracle": {
            "present": ["SELECT LENGTH(NULL), NULL, NULL, SUBSTR(NULL, 1, 2)"],
            "absent": ["CONCAT("],
        },
        "postgresql": {
            "present": ["SELECT LENGTH(NULL), NULL, NULL, SUBSTRING(NULL, 1, 2)"],
            "absent": ["CONCAT("],
        },
    },
    "my-str-plus-interval": {
        "tsql": {
            "present": ["DATEADD(DAY, 1, '2020-01-01')"],
            "absent": ["INTERVAL 1 DAY"],
        },
        "oracle": {
            "present": ["'2020-01-01' + INTERVAL '1' DAY"],
            "absent": ["INTERVAL 1 DAY"],
        },
        "postgresql": {
            "present": ["'2020-01-01' + INTERVAL '1' DAY"],
            "absent": ["INTERVAL 1 DAY"],
        },
    },
    "my-subdate": {
        "tsql": {
            "present": ["DATEADD(MONTH, -1, '2020-01-31')"],
            "absent": ["SUBDATE"],
        },
        "oracle": {
            "present": ["ADD_MONTHS(DATE '2020-01-31', -1)"],
            "absent": ["SUBDATE"],
        },
        "postgresql": {
            "present": ["DATE '2020-01-31' - INTERVAL '1 MONTH'"],
            "absent": ["SUBDATE"],
        },
    },
    "my-substr-neg": {
        "tsql": {
            "present": ["SUBSTRING('abcdef', LEN('abcdef') + (-3) + 1, LEN('abcdef'))"],
            "absent": ["'abcdef', -3)"],
        },
        "oracle": {"present": ["SUBSTR('abcdef', -3)"], "absent": ["SUBSTRING"]},
        "postgresql": {
            "present": ["SUBSTRING('abcdef', LENGTH('abcdef') + (-3) + 1)"],
            "absent": ["'abcdef', -3)"],
        },
    },
    "my-substr3": {
        "tsql": {
            "present": ["SUBSTRING('abcdef', LEN('abcdef') + (-2) + 1, LEN('abcdef'))"],
            "absent": ["SUBSTR("],
        },
        "oracle": {"present": ["SUBSTR('abcdef', -2)"], "absent": ["'abcdef',2)"]},
        "postgresql": {
            "present": ["SUBSTRING('abcdef', LENGTH('abcdef') + (-2) + 1)"],
            "absent": ["SUBSTR("],
        },
    },
    "my-substridx-agg": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-substridx-nested": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-substring-index": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-system-funcs": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-time-build": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-timestampdiff": {
        "tsql": {
            "present": ["DATEDIFF(DAY, '2020-01-01', '2020-01-10')"],
            "absent": ["TIMESTAMPDIFF"],
        },
        "oracle": {
            "present": ["TRUNC(CAST(DATE '2020-01-10' AS DATE))"],
            "absent": ["TIMESTAMPDIFF"],
        },
        "postgresql": {
            "present": [
                "(CAST(DATE '2020-01-10' AS DATE) - CAST(DATE '2020-01-01' AS DATE))"
            ],
            "absent": ["TIMESTAMPDIFF"],
        },
    },
    "my-timestampdiff-year": {
        "tsql": {
            "present": ["DATEDIFF(YEAR, '2019-12-31', '2020-01-01')"],
            "absent": ["TIMESTAMPDIFF"],
        },
        "oracle": {
            "present": ["- EXTRACT(YEAR FROM DATE '2019-12-31')"],
            "absent": ["TIMESTAMPDIFF"],
        },
        "postgresql": {
            "present": ["- EXTRACT(YEAR FROM DATE '2019-12-31')"],
            "absent": ["TIMESTAMPDIFF"],
        },
    },
    "my-trim-both": {
        "tsql": {"present": ["TRIM('x' FROM 'xxabcxx')"], "absent": ["TRIM(BOTH"]},
        "oracle": {
            "present": ["LTRIM(RTRIM('xxabcxx', 'x'), 'x')"],
            "absent": ["TRIM(BOTH"],
        },
    },
    "my-trim-edge": {
        "tsql": {"present": ["TRIM('x' FROM 'xxhixx')"], "absent": ["TRIM(BOTH"]},
        "oracle": {
            "present": ["LTRIM(RTRIM('xxhixx', 'x'), 'x')", "RTRIM('hi!!', '!')"],
            "absent": ["TRIM(BOTH"],
        },
    },
    "my-trim-len": {
        "tsql": {
            "present": ["LEN(TRIM(' ' FROM '  hi  '))"],
            "absent": ["CHAR_LENGTH"],
        },
        "oracle": {
            "present": ["LENGTH(LTRIM(RTRIM('  hi  ', ' '), ' '))"],
            "absent": ["CHAR_LENGTH"],
        },
        "postgresql": {
            "present": ["LENGTH(TRIM(BOTH ' ' FROM '  hi  '))"],
            "absent": ["CHAR_LENGTH"],
        },
    },
    "my-trim-trailing": {
        "oracle": {"present": ["RTRIM('abc...', '.')"], "absent": ["TRIM(TRAILING"]},
    },
    # func: TIMESTAMPDIFF(MONTH) counts COMPLETE months; the PG/Oracle naive
    # year*12+month boundary overcounted (2020-01-31..2020-03-30 = 1, not 2).
    # Port the T-SQL 'drop the incomplete final period' adjustment. All = 1.
    "my-timestampdiff-mon-pgora": {
        "postgresql": {
            "present": ["CASE WHEN DATE '2020-01-31' +", "INTERVAL '1 month'"],
            "absent": ["TIMESTAMPDIFF"],
        },
        "oracle": {
            "present": ["ADD_MONTHS(DATE '2020-01-31'", "CASE WHEN"],
            "absent": ["TIMESTAMPDIFF"],
        },
    },
    "my-tsadd-quarter": {
        "tsql": {
            "present": ["DATEADD(QUARTER, 1, GETDATE())"],
            "absent": ["TIMESTAMPADD"],
        },
        # QUARTER now translates faithfully (was a warned degrade): ADD_MONTHS by
        # 3 months + a year*4+quarter boundary diff.
        "oracle": {
            "present": ["ADD_MONTHS(SYSDATE, 3)", "TO_CHAR(SYSDATE, 'Q')"],
            "absent": ["TIMESTAMPADD", "TIMESTAMPDIFF"],
        },
        "postgresql": {
            "present": [
                "INTERVAL '3 months'",
                "EXTRACT(QUARTER FROM CURRENT_TIMESTAMP)",
            ],
            "absent": ["TIMESTAMPADD", "TIMESTAMPDIFF"],
        },
    },
    "my-unix-timestamp": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-unixtime2": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-uuid-bin": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-uuid-funcs": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-week-mode": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-week-modes": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-week-quarter": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my-weight-string": {
        "tsql": {"degrade": True},
        "oracle": {"degrade": True},
        "postgresql": {"degrade": True},
    },
    "my8-lag-nth": {
        "tsql": {"degrade": True},
        "oracle": {"present": ["data CLOB"], "absent": ["data JSON"]},
    },
    "my8-recursive": {
        "tsql": {
            "present": ["data NVARCHAR(MAX)", "WITH cte AS ("],
            "absent": ["data JSON"],
        },
        "oracle": {"present": ["WITH cte(n) AS ("], "absent": ["RECURSIVE"]},
    },
    "mysql-drop-check": {
        "tsql": {
            "present": ["CHECK (email LIKE '%@%')"],
            "absent": ["VARCHAR(255) CHECK"],
        },
        "oracle": {"present": ["VARCHAR2(255)"], "absent": ["VARCHAR(255) CHECK"]},
        "postgresql": {
            "present": ["CHECK (email LIKE '%@%')"],
            "absent": ["VARCHAR(255) CHECK"],
        },
    },
    "mysql-drop4-50": {
        "tsql": {"present": ["a INT PRIMARY KEY"], "absent": ["AUTO_INCREMENT"]},
        "oracle": {
            "present": ["a NUMBER(10) PRIMARY KEY"],
            "absent": ["AUTO_INCREMENT"],
        },
        "postgresql": {"present": ["a INT PRIMARY KEY"], "absent": ["AUTO_INCREMENT"]},
    },
    "mysql-prec-64": {
        "tsql": {"present": ["a NUMERIC(20)"], "absent": ["BIT(64)"]},
        "oracle": {"present": ["a NUMBER(20)"], "absent": ["BIT(64)"]},
    },
    # BLUE 2026-07-30 (B29): a MySQL ENUM sorts by declaration index; the
    # VARCHAR+CHECK degrade loses that, so ORDER BY on the column is rewritten
    # into the ordinal CASE sort key (every target now orders lo<mid<hi). The
    # projected column stays the plain value.
    "my-enum-order": {
        "postgresql": {
            "present": ["ORDER BY CASE a", "WHEN 'lo' THEN 1", "WHEN 'hi' THEN 3"],
            "absent": ["ORDER BY a ", "ORDER BY a\n"],
        },
        "tsql": {
            "present": ["ORDER BY CASE a", "WHEN 'lo' THEN 1", "WHEN 'hi' THEN 3"],
            "absent": ["ORDER BY a ", "ORDER BY a\n"],
        },
        "oracle": {
            "present": ["ORDER BY CASE a", "WHEN 'lo' THEN 1", "WHEN 'hi' THEN 3"],
            "absent": ["ORDER BY a ", "ORDER BY a\n"],
        },
    },
    # BLUE 2026-07-30: multi-table DELETE join modelled per target.
    "my-multitable-delete-join": {
        "postgresql": {
            "present": ["DELETE FROM redb_d1 t1", "USING redb_d2 t2", "t2.flag = 1"],
            "absent": ["JOIN redb_d2"],
        },
        "tsql": {
            "present": ["DELETE t1 FROM redb_d1 t1, redb_d2 t2"],
            "absent": ["JOIN redb_d2"],
        },
        "oracle": {
            "present": ["WHERE EXISTS (SELECT 1 FROM redb_d2 t2"],
            "absent": ["JOIN redb_d2"],
        },
    },
}


def _slugs_for(target: str) -> list[str]:
    return sorted(
        slug
        for slug, spec in CASES.items()
        if target in spec and slug not in SUSPECT_CASES
    )


def _run(slug: str, target: str) -> None:
    spec = CASES[slug][target]
    block = _block_for(slug)
    result = Transpiler().transpile(block, source=_SOURCE, target=target)
    if spec.get("degrade"):
        assert result.warnings, f"{slug} -> {target}: expected a warned degrade"
        assert (
            "UNIQUE-" in result.sql
        ), f"{slug} -> {target}: no UNIQUE carrier\n{result.sql}"
        return
    exe = _exe(result.sql)
    for fragment in cast("list[str]", spec["present"]):
        assert fragment in exe, f"{slug} -> {target}: missing {fragment!r}\n{exe}"
    for fragment in cast("list[str]", spec["absent"]):
        assert fragment not in exe, f"{slug} -> {target}: leaked {fragment!r}\n{exe}"


@pytest.mark.parametrize("slug", _slugs_for("tsql"))
def test_mysql_to_tsql(slug: str) -> None:
    _run(slug, "tsql")


@pytest.mark.parametrize("slug", _slugs_for("oracle"))
def test_mysql_to_oracle(slug: str) -> None:
    _run(slug, "oracle")


@pytest.mark.parametrize("slug", _slugs_for("postgresql"))
def test_mysql_to_postgresql(slug: str) -> None:
    _run(slug, "postgresql")
