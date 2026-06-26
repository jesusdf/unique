# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Functional-equivalence state checking.

The pure (no-database) core of the harness: load ``expected_state.yaml``, and
compare a database's actual rows against it after normalizing every value so the
four engines are comparable. Keeping this engine-agnostic and free of any driver
makes it unit-testable on its own (the bulk of the harness work, and where the
subtle false positives/negatives live — see ``README.md``).

Normalization (per the README's comparison mechanism):

- bool      — BIT/BOOLEAN/NUMBER(1) 0/1/true/false → Python bool
- int       — INT/NUMBER integers → Python int
- decimal   — fixed to the column's declared scale, compared as a string
- str       — CHAR/VARCHAR/TEXT/CLOB → trimmed str
- date      — date / 'YYYY-MM-DD...' → ISO 'YYYY-MM-DD' string
- null      — a single sentinel

Values in ``expected_state.yaml`` drive the *expected* type of each column: the
YAML already carries decimals as strings ("10.00"), booleans as true/false,
dates as "YYYY-MM-DD", ints as ints. So the actual DB value is coerced to match
the expected value's kind, which avoids a separate per-column type registry.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

NULL = "\u2400"  # a single, printable NULL sentinel (␀)


@dataclass(frozen=True)
class TableExpectation:
    """Expected contents of one table."""

    name: str
    row_count: int
    rows: tuple[dict[str, Any], ...]
    primary_key: str


@dataclass(frozen=True)
class ExpectedState:
    """The whole engine-agnostic expected state."""

    tables: tuple[TableExpectation, ...]

    def table(self, name: str) -> TableExpectation:
        for t in self.tables:
            if t.name == name:
                return t
        raise KeyError(name)


def _infer_primary_key(rows: list[dict[str, Any]]) -> str:
    """Pick the primary-key column for deterministic ordering.

    Uses ``id`` when present (every table in the canonical schema has one),
    otherwise the first key of the first row.
    """
    if not rows:
        return "id"
    if "id" in rows[0]:
        return "id"
    return next(iter(rows[0]))


def load_expected_state(path: str | Path) -> ExpectedState:
    """Parse ``expected_state.yaml`` into an :class:`ExpectedState`."""
    data = yaml.safe_load(Path(path).read_text())
    tables: list[TableExpectation] = []
    for name, spec in (data.get("tables") or {}).items():
        rows = [dict(r) for r in (spec.get("rows") or [])]
        tables.append(
            TableExpectation(
                name=name,
                row_count=int(spec["row_count"]),
                rows=tuple(rows),
                primary_key=_infer_primary_key(rows),
            )
        )
    return ExpectedState(tables=tuple(tables))


def _scale_of(expected_decimal: str) -> int:
    """Number of fractional digits in an expected decimal string ("10.00"→2)."""
    return len(expected_decimal.split(".")[1]) if "." in expected_decimal else 0


def normalize(actual: Any, expected: Any) -> Any:
    """Coerce a database value to a canonical form comparable to ``expected``.

    The *kind* of ``expected`` (from the YAML spec) selects the coercion, so the
    same DB value (e.g. Oracle NUMBER(1) coming back as Decimal('1')) compares
    equal to the engine-agnostic expectation (``True``).
    """
    if actual is None:
        return NULL

    # Boolean expected — accept 0/1, Decimal, bool, or 'true'/'false' text.
    if isinstance(expected, bool):
        if isinstance(actual, str):
            return actual.strip().lower() in ("1", "true", "t", "y", "yes")
        return bool(int(actual)) if not isinstance(actual, bool) else actual

    # Decimal expected (carried as a string like "10.00") — fix to that scale.
    if isinstance(expected, str) and _looks_decimal(expected):
        scale = _scale_of(expected)
        return str(Decimal(str(actual)).quantize(Decimal(1).scaleb(-scale)))

    # Date expected ("YYYY-MM-DD") — normalize to ISO date.
    if isinstance(expected, str) and _looks_date(expected):
        if isinstance(actual, (_dt.date, _dt.datetime)):
            return actual.strftime("%Y-%m-%d")
        return str(actual)[:10]

    # Integer expected.
    if isinstance(expected, int) and not isinstance(expected, bool):
        return int(actual)

    # String expected — trim (handles CHAR(n) padding).
    if isinstance(expected, str):
        return str(actual).strip()

    return actual


def _looks_decimal(s: str) -> bool:
    if not s or s in ("true", "false"):
        return False
    try:
        Decimal(s)
    except Exception:
        return False
    # A bare integer string is treated as int elsewhere; decimals carry a dot.
    return "." in s


def _looks_date(s: str) -> bool:
    try:
        _dt.date.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


@dataclass
class Mismatch:
    """A single difference found while checking a table."""

    table: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.table}] {self.detail}"


def check_table(
    expectation: TableExpectation,
    actual_rows: list[dict[str, Any]],
) -> list[Mismatch]:
    """Compare one table's actual rows against its expectation.

    ``actual_rows`` is a list of column→value dicts (already read from the DB,
    in any order). Both sides are ordered by the primary key and every asserted
    column is normalized and compared. Columns not present in the expectation
    are ignored (e.g. clock-stamped ``created_at`` is presence-checked
    separately, not value-asserted).
    """
    mismatches: list[Mismatch] = []

    if len(actual_rows) != expectation.row_count:
        mismatches.append(
            Mismatch(
                expectation.name,
                f"row_count: expected {expectation.row_count}, "
                f"got {len(actual_rows)}",
            )
        )

    pk = expectation.primary_key
    expected_by_pk = {r[pk]: r for r in expectation.rows}
    actual_by_pk = {}
    for r in actual_rows:
        if pk in r:
            actual_by_pk[normalize(r[pk], 0)] = r

    for pk_val, exp_row in expected_by_pk.items():
        act_row = actual_by_pk.get(pk_val)
        if act_row is None:
            mismatches.append(Mismatch(expectation.name, f"missing row {pk}={pk_val}"))
            continue
        for col, exp_val in exp_row.items():
            if col not in act_row:
                mismatches.append(
                    Mismatch(
                        expectation.name,
                        f"row {pk}={pk_val}: column '{col}' missing",
                    )
                )
                continue
            got = normalize(act_row[col], exp_val)
            want = NULL if exp_val is None else exp_val
            if got != want:
                mismatches.append(
                    Mismatch(
                        expectation.name,
                        f"row {pk}={pk_val}: {col} expected {want!r}, got {got!r}",
                    )
                )

    return mismatches


def check_state(
    expected: ExpectedState,
    read_table: Any,
) -> list[Mismatch]:
    """Check every expected table using a ``read_table(name) -> rows`` callable.

    ``read_table`` returns a list of column→value dicts for the named table.
    Returns all mismatches across all tables (empty list == functional
    equivalence holds for this engine).
    """
    all_mismatches: list[Mismatch] = []
    for expectation in expected.tables:
        rows = read_table(expectation.name)
        all_mismatches.extend(check_table(expectation, rows))
    return all_mismatches
