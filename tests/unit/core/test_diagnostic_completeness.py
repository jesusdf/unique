# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Completeness gate: no warning ships uncoded (B32 wave 3).

Every warning the transpiler surfaces must carry a stable ``UNIQUE-NNNN``
code so a user can grep/suppress/telemeter it. Two mechanisms code them:

* **carrier-backed** warnings (the bulk) get their code from the
  ``-- UNIQUE-NNNN:`` carrier in the emitted SQL via the reconciliation
  *backfill* (``_core.py``: ``_covering_warnings``);
* **non-carrier** warnings (error paths, tripwires, guard drops, dropped
  physical clauses, session/client directives) pass ``code=`` at the emission
  site.

This test sweeps the offline corpus and counts the DISTINCT
``(feature, normalized-message)`` signatures that still ship ``code=None``.
The count is a **ratchet**: it may only go DOWN. Lower it (never raise it) as
uncoded emission paths are coded; a NEW uncoded path pushes the count above the
floor and fails the gate. Mirrors the unread-args tripwire and the architecture
ratchets.

The remaining floor is the **procedural-layer carrier residual**: the T-SQL /
MySQL / Oracle procedural emitters still emit legacy uncoded ``/* UNIQUE: … */``
/ ``-- UNIQUE: …`` carriers (e.g. ``SET NOCOUNT ON`` notes, ``was T-SQL table
variable``, ``discarded procedure RETURN value``). Those constructs already own
registry codes (1140/1163/1177/1193/1196/1201/1202/…); coding them at the
procedural emitters — and regenerating ``tests/fixtures/procedures/*`` — is a
follow-up migration (same shape as the DML/converter coding of waves 1–2). Each
carrier coded there lowers this floor by one, toward 0.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from unique.core.transpiler import Transpiler

# Distinct code=None signatures still shipping over the swept corpus. Measured
# 2026-07-30; RATCHET DOWN ONLY (never raise — head-room is exactly the
# regression this gate denies). All 14 are the procedural-carrier residual
# described in the module docstring.
_UNCODED_WARNING_FLOOR = 14

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

# Both pipelines: ``sql`` exercises the standalone-DML path (now fully coded),
# ``procedures`` the procedural path (the residual). Kept off the heavy
# ``corpus``/``real_world`` trees so the sweep stays a few seconds.
_SWEEP_SUBDIRS = ("sql", "procedures")

_DIRECTIONS = [
    ("tsql", "postgresql"),
    ("postgresql", "tsql"),
    ("oracle", "mysql"),
    ("mysql", "oracle"),
    ("tsql", "oracle"),
    ("oracle", "tsql"),
    ("postgresql", "mysql"),
    ("mysql", "postgresql"),
    ("tsql", "mysql"),
    ("mysql", "tsql"),
    ("oracle", "postgresql"),
    ("postgresql", "oracle"),
]


def _detect_source(path: str) -> str | None:
    low = path.lower()
    if "sqlserver" in low or "tsql" in low or "mssql" in low:
        return "tsql"
    if "oracle" in low or "plsql" in low:
        return "oracle"
    if "postgres" in low or "_pg" in low:
        return "postgresql"
    if "mysql" in low:
        return "mysql"
    return None


def _normalize(message: str) -> str:
    """Collapse identifiers/literals/counts so one construct = one signature."""
    m = message.lower()
    m = re.sub(r"'[^']*'", "S", m)  # string literals
    m = re.sub(r"@?\b\w*\d\w*\b", "V", m)  # @vars, v_col_16, …
    m = re.sub(r"\d+", "#", m)  # residual counts (x27)
    m = re.sub(r"\s+", " ", m).strip()
    return m[:80]


def _uncoded_signatures() -> dict[tuple[str, str], str]:
    transpiler = Transpiler()
    files = [
        p
        for sub in _SWEEP_SUBDIRS
        if (_FIXTURES / sub).is_dir()
        for p in sorted((_FIXTURES / sub).rglob("*.sql"))
    ]
    offenders: dict[tuple[str, str], str] = {}
    for path in files:
        src = _detect_source(str(path))
        sql = path.read_text(encoding="utf-8", errors="ignore")
        for source, target in _DIRECTIONS:
            if src is not None and src != source:
                continue
            try:
                result = transpiler.transpile(sql, source=source, target=target)
            except Exception:
                continue
            for warning in result.warnings:
                if warning.code is None:
                    key = (warning.feature, _normalize(warning.message))
                    offenders.setdefault(key, f"{path.name} [{source}->{target}]")
    return offenders


def test_no_warning_ships_uncoded_beyond_floor() -> None:
    offenders = _uncoded_signatures()
    assert len(offenders) <= _UNCODED_WARNING_FLOOR, (
        f"{len(offenders)} distinct uncoded warning signatures ship "
        f"(floor {_UNCODED_WARNING_FLOOR}); a new emission path shipped a "
        "code=None warning. Code it: pass code= at the emission site, or (if it "
        "is carrier-backed) ensure the carrier is a UNIQUE-NNNN carrier so the "
        "reconciliation backfill can stamp it. The ratchet is monotonic "
        "downward — never raise the floor.\n"
        + "\n".join(
            f"  {feat} :: {sig}  first: {where}"
            for (feat, sig), where in sorted(offenders.items())
        )
    )


@pytest.mark.parametrize(
    "sql,source,target,expected_code",
    [
        # Non-carrier direct sites now carry codes (backfill cannot reach them:
        # they leave no coded carrier in the SQL).
        ("SET lock_timeout = 0;", "postgresql", "tsql", "UNIQUE-1218"),
        ("SET SERVEROUTPUT ON;", "oracle", "postgresql", "UNIQUE-1223"),
    ],
)
def test_representative_warnings_are_coded(
    sql: str, source: str, target: str, expected_code: str
) -> None:
    result = Transpiler().transpile(sql, source=source, target=target)
    codes = {w.code for w in result.warnings}
    assert expected_code in codes, (sql, codes)
    assert None not in codes, [
        (w.feature, w.message) for w in result.warnings if w.code is None
    ]
