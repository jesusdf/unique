# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Differential result testing over the corpus.

The corpus sweep proves the transpiled output *executes*; this proves it returns
the *same answer*. Each result-comparable corpus SELECT is executed on its source
engine and its transpiled output on each target engine, and the normalized result
sets are compared. A divergence is a semantic bug that syntactic validity misses
(argument order swapped, precedence changed, off-by-one, ``+`` vs concat, …).

Numeric-tolerance policy (maintainer decision, 2026-07-31, brief A10-T2)
--------------------------------------------------------------------------
The historical BLUE rule for triaging FE mismatches was "same value + precision
diff = acceptable" — applied by hand, never encoded. This module now encodes it:

    Two numeric cells (``int``/``float``/``Decimal``, and a cell that is
    ENTIRELY a fractional numeric literal delivered as text, e.g. a CONCAT
    result) match when they are equal after each is rounded to the COARSER
    (fewer-decimal-digits) of the two operands' OWN precision, read from the
    value's own representation (``Decimal.as_tuple().exponent``, or a float's
    shortest round-tripping ``repr``) — never a guessed/fixed digit count.

Why "coarser operand's precision" rather than a fixed epsilon: the divergence
this rule targets is display/default-scale (``AVG`` returning 4 vs 10 decimal
digits, ``1/3*3`` landing on ``1.0`` via exact decimal division on one engine
vs ``0.999999`` via a float chain on another) — the LOW-precision side is the
one that lost information, so rounding the more precise side down to it is
the faithful "would these look the same if both engines used the same
display scale" test. A fixed epsilon would either be too loose for large
values or too tight for coarse ones; reading each operand's own precision
adapts automatically (``1.6667`` vs ``1.666666`` -> round to 4 places;
``5.5`` vs ``5.50`` -> round to 1). This also transparently absorbs the
"float chain" case (``1.0`` vs ``0.999999``): no separate relative-epsilon
path is needed because the LOW-precision side (``1.0``, 1 decimal digit)
already forces both down to 1 decimal place, where they agree.

A tight relative-epsilon fallback (``1e-9``) IS still needed, for a case the
coarser-precision rule alone cannot see: two operands that BOTH report full
float precision (16-17 significant digits) yet disagree in the last couple —
raw floating-point/transcendental noise (``TAN``/``COT`` computed by two
engines' math libraries, e.g. ``0.6420926159343306`` vs
``...343308``: a live regression caught by the ``ts-trig``/``my-trig-suite``
challenge cases, already-known "precision-only" divergences per their case
headers). Neither side LOOKS coarse here, so rounding to "the coarser one's
digit count" is a no-op; only a relative check bridges it. The bound is kept
two orders of magnitude looser than machine epsilon but nine orders tighter
than the smallest genuine-difference pair in this policy's own test set
(``0.3333`` vs ``0.3433``, a ~3% relative gap) — wide enough for a few ULPs
of accumulated transcendental error, nowhere near wide enough to mask a real
difference.

Zero-adjacent guard: an exact (or near-exact) zero is not "coarse" in the
sense above — it is *exactly known*, not a low-precision display of some
other value — so treating it as the coarser operand would let it swallow any
small-but-real nonzero result (``0`` vs ``0.4`` must NOT match just because
``0`` "looks like" 0 decimal places). Whenever either operand is (numerically)
zero, the comparison instead uses a tight absolute epsilon (``1e-9``) — enough
to fold pure floating-point noise (``0.1+0.2-0.3`` ~ ``5.5e-17``) without
matching a genuinely different small value.

Scope note — numeric-looking strings: a cell that is ENTIRELY a fractional
numeric literal (``^-?\\d+\\.\\d+$``, e.g. ``"5.50"``) gets the same tolerant
comparison as a typed numeric cell (a value is a value, whether the driver
returned it as ``Decimal`` or as text). A number embedded in longer text
(``"d=0.333333"``) is deliberately left untouched — canonicalizing a
substring of prose is a different, much riskier operation than canonicalizing
a cell that IS a number, and no corpus case needs it. Bare-integer strings
(``"12"``, no decimal point) are also left untouched: they need no tolerance
(exact string equality already works) and leaving them alone keeps the change
minimal. Datetime/date/time strings are matched and returned FIRST by
``_canonical_temporal_str`` above, so this never reinterprets a date as a
number (and the datetime fractional-seconds case — ``.123456`` vs
``.123457`` — stays a real mismatch: a different normalizer, untouched here).
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from helpers.corpus import LIVE_ENGINES, CorpusEntry, targets_for

_ENV = {
    "tsql": "UNIQUE_TEST_MSSQL_URL",
    "oracle": "UNIQUE_TEST_ORACLE_URL",
    "postgresql": "UNIQUE_TEST_PG_URL",
    "mysql": "UNIQUE_TEST_MYSQL_URL",
}
# Functions whose value depends on the wall clock / randomness — the two engines
# legitimately differ, so these entries are executed but not result-compared.
_NONDETERMINISTIC = re.compile(
    r"(?i)\b(NOW|SYSDATE|SYSTIMESTAMP|CURDATE|CURRENT_DATE|CURRENT_TIMESTAMP|"
    r"GETDATE|SYSDATETIME|RANDOM|RAND|NEWID|UUID|SYS_GUID)\b|DATE\('now'\)"
)


@dataclass(frozen=True)
class Mismatch:
    entry_id: str
    source: str
    target: str
    source_result: Any
    target_result: Any
    output: str


# ISO date / datetime / time recognizers for values that arrive as *strings*
# (one driver returns a datetime object, another the same instant as text). Only
# these strict shapes are canonicalized — a numeric string like '12' or a comma
# list '1,2' does not match, so they are never mis-parsed as temporals.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2})?$"
)
_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}(\.\d+)?$")


def _canonical_datetime(dt: datetime.datetime) -> str:
    """One canonical text form for a datetime, timezone dropped (wall clock).

    Timezone-awareness is a driver artifact (psycopg returns aware datetimes for
    ``timestamptz`` where every other driver returns naive), not a value the SQL
    computed, so it is normalized away. A midnight time collapses to the bare
    date so DATE-vs-DATETIME rendering is not a false mismatch (pre-existing)."""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    if (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0):
        return dt.date().isoformat()
    return dt.isoformat()


def _canonical_time(t: datetime.time) -> str:
    return t.replace(tzinfo=None).isoformat()


def _parse_fraction_us(frac: str | None) -> int:
    """Sub-second text ('.1234567') -> microseconds, truncated to 6 digits."""
    if not frac:
        return 0
    return int((frac.lstrip(".") + "000000")[:6])


def _canonical_temporal_str(s: str) -> str | None:
    """Canonicalize an ISO date/datetime/time *string*, else ``None``."""
    if _DATE_RE.match(s):
        return s
    m = _DATETIME_RE.match(s)
    if m:
        head = s[:19].replace(" ", "T")
        dt = datetime.datetime.fromisoformat(head).replace(
            microsecond=_parse_fraction_us(m.group(1))
        )
        return _canonical_datetime(dt)
    m = _TIME_RE.match(s)
    if m:
        t = datetime.time.fromisoformat(s[:8]).replace(
            microsecond=_parse_fraction_us(m.group(1))
        )
        return _canonical_time(t)
    return None


def _canonical_json(obj: Any) -> str:
    """Canonical (sorted-key, tight) JSON dump of a parsed structure."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _is_year_month_interval(v: Any) -> bool:
    """oracledb ``IntervalYM`` (year-month interval) — duck-typed, no import."""
    return (
        not isinstance(v, datetime.timedelta)
        and hasattr(v, "years")
        and hasattr(v, "months")
    )


# A cell that is ENTIRELY a fractional numeric literal (never a substring of
# longer text — see the module docstring's numeric-tolerance policy).
_PURE_FRACTIONAL_RE = re.compile(r"^-?\d+\.\d+$")
_ZERO_EPSILON = 1e-9
# Tight relative-epsilon fallback for genuine floating-point/transcendental
# noise (e.g. TAN/COT computed by different math libraries agreeing to ~15
# significant digits but not bit-for-bit) — see the module docstring.
_REL_EPSILON = 1e-9


def _decimal_places(v: Decimal | float | int) -> int:
    """Count of meaningful fractional digits in *v*'s own representation.

    Read from the value's own digits (``Decimal``'s exponent, or a float/int's
    shortest round-tripping ``repr``) rather than assumed — this is what lets
    the coarser-operand rule tell ``1.6667`` (4 digits given) apart from
    ``1.666666`` (6 digits given) instead of guessing.
    """
    if isinstance(v, Decimal):
        exponent = v.as_tuple().exponent
        return -exponent if isinstance(exponent, int) and exponent < 0 else 0
    s = repr(v)
    if "e" in s or "E" in s:
        return 15  # scientific notation: treat as high-precision (the other
        # operand's own, usually coarser, digit count wins via min() below)
    if "." not in s:
        return 0
    return len(s.split(".", 1)[1])


class _Num:
    """A numeric cell that matches another within the coarser-precision
    tolerance (see the module docstring, 2026-07-31 policy)."""

    __slots__ = ("value", "places")

    def __init__(self, value: float, places: int) -> None:
        self.value = value
        self.places = places

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Num):
            other_value, other_places = other.value, other.places
        elif isinstance(other, bool):
            return NotImplemented
        elif isinstance(other, (int, float, Decimal)):
            other_value, other_places = float(other), _decimal_places(other)
        else:
            return NotImplemented
        if self.value == other_value:
            return True
        if self.value == 0.0 or other_value == 0.0:
            # Zero-adjacent guard: an exact zero is not "coarse" — it is
            # exactly known — so only genuine near-zero noise may match it.
            return abs(self.value - other_value) < _ZERO_EPSILON
        places = min(self.places, other_places)
        if round(self.value, places) == round(other_value, places):
            return True
        # Neither operand LOOKS coarse (e.g. two 16-digit transcendental
        # function results) yet may still be the same value modulo per-engine
        # floating-point noise — a tight relative epsilon catches that without
        # loosening the real-difference cases (0.3333 vs 0.3433 is a ~3%
        # relative gap, far above this bound).
        denom = max(abs(self.value), abs(other_value))
        return abs(self.value - other_value) / denom < _REL_EPSILON

    def __hash__(self) -> int:
        return hash(round(self.value, 4))

    def __repr__(self) -> str:
        return repr(round(self.value, 6))


def normalize_cell(v: Any) -> Any:
    """Canonicalize a cell so equal values compare equal across engines."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (Decimal, float)):
        return _Num(float(v), _decimal_places(v))
    if isinstance(v, int):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, (dict, list)):
        # A JSON column parsed to a Python object by the driver (psycopg does
        # this) — canonicalize so '{"a":1}' and {'a': 1} compare equal.
        return _canonical_json(v)
    if isinstance(v, datetime.datetime):
        return _canonical_datetime(v)
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.time):
        return _canonical_time(v)
    if isinstance(v, datetime.timedelta):
        # Day/second interval — tagged distinctly from a year-month interval so
        # '1 year 2 months' can never compare equal to a fixed day count.
        return f"interval_dt:{v.total_seconds()}"
    if _is_year_month_interval(v):
        return f"interval_ym:{v.years * 12 + v.months}"
    s = str(v).strip()
    temporal = _canonical_temporal_str(s)
    if temporal is not None:
        return temporal
    if _PURE_FRACTIONAL_RE.match(s):
        # A numeric VALUE that arrived as text (e.g. through a CONCAT) and is
        # NOTHING but the number — same tolerance as a typed numeric cell.
        with contextlib.suppress(ArithmeticError, ValueError):
            d = Decimal(s)
            return _Num(float(d), _decimal_places(d))
    if s[:1] in "{[":  # a JSON payload delivered as text
        with contextlib.suppress(ValueError, TypeError):
            return _canonical_json(json.loads(s))
    return s


def normalize_rows(rows: list[tuple], *, empty_as_null: bool = False) -> list[tuple]:
    # Order-insensitive: compare the multiset of rows (ORDER BY differences and
    # engine default ordering must not cause a false mismatch).
    # ``empty_as_null`` collapses '' into NULL — Oracle folds empty VARCHAR to
    # NULL intrinsically, so when ONE side of a comparison is Oracle the two are
    # indistinguishable there and both sides must be folded alike (maintainer
    # decision 2026-07-30). The sort key tolerates the None/str mix this creates.
    out = []
    for row in rows:
        cells = tuple(normalize_cell(c) for c in row)
        if empty_as_null:
            cells = tuple(None if c == "" else c for c in cells)
        out.append(cells)
    return sorted(out, key=lambda r: [(c is None, str(c)) for c in r])


def is_comparable(entry: CorpusEntry) -> bool:
    """A single-statement, deterministic, row-returning SELECT."""
    sql = entry.sql.strip()
    return (
        sql.upper().startswith("SELECT")
        and ";" not in sql.rstrip(";")
        and not _NONDETERMINISTIC.search(sql)
    )


def urls_from_env() -> dict[str, str]:
    return {eng: os.environ[var] for eng, var in _ENV.items() if os.environ.get(var)}


def run_result_diff(
    entries: list[CorpusEntry], urls: dict[str, str]
) -> tuple[list[Mismatch], int, list[str]]:
    """Compare source vs target results for every comparable entry.

    Returns ``(mismatches, pairs_checked, engines_used)``. Execution *failures*
    are ignored here — those are the corpus sweep's job; this only compares when
    both sides executed.
    """
    from tests.functional_equivalence.engine_runner import connect
    from unique.core.transpiler import transpile

    conns = {}
    for eng in LIVE_ENGINES:
        url = urls.get(eng)
        if not url:
            continue
        with contextlib.suppress(Exception):  # driver/DB unavailable
            conns[eng] = connect(eng, url)

    def run(engine: str, sql: str) -> tuple[Any, str | None]:
        cur = conns[engine].cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            conns[engine].rollback()
            return normalize_rows(rows), None
        except Exception as exc:
            with contextlib.suppress(Exception):
                conns[engine].rollback()
            return None, str(exc).splitlines()[0][:80]

    mismatches: list[Mismatch] = []
    checked = 0
    try:
        for entry in entries:
            if not is_comparable(entry) or entry.source not in conns:
                continue
            source_result, err = run(entry.source, entry.sql)
            if err is not None:
                continue
            for target in targets_for(entry.source):
                if target not in conns:
                    continue
                output = transpile(entry.sql, entry.source, target).sql
                target_result, terr = run(target, output)
                if terr is not None:
                    continue
                checked += 1
                if source_result != target_result:
                    mismatches.append(
                        Mismatch(
                            entry.id,
                            entry.source,
                            target,
                            source_result,
                            target_result,
                            output,
                        )
                    )
    finally:
        for conn in conns.values():
            with contextlib.suppress(Exception):
                conn.close()
    return mismatches, checked, sorted(conns)
