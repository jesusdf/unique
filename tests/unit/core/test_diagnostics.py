# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Registry integrity for the ``UNIQUE-NNNN`` diagnostic catalog (B32 wave 1).

This is the CI collision/coverage check the brief asks for: codes are unique
and well-formed, every registered code is emitted somewhere in ``src/``, and
every ``UNIQUE-NNNN`` carrier emitted in ``src/`` is registered here (so a new
carrier cannot ship with an unregistered code).
"""

from __future__ import annotations

import re
from pathlib import Path

from unique.core import diagnostics
from unique.core.diagnostics import DIAGNOSTICS

_SRC = Path(diagnostics.__file__).parent.parent  # …/src/unique
_REGISTRY_FILE = Path(diagnostics.__file__)
_CODE_RE = re.compile(r"UNIQUE-(\d{4})")
_CARRIER_RE = re.compile(r"(?:--|/\*)\s*UNIQUE-(\d{4}):")
_ALLOWED_CATEGORIES = {
    "statement",
    "ddl",
    "expression",
    "procedural",
    "validation",
    "orchestration",
}


def _src_files() -> list[Path]:
    return [p for p in _SRC.rglob("*.py") if p != _REGISTRY_FILE]


def test_codes_are_unique_and_well_formed():
    for code in DIAGNOSTICS:
        assert re.fullmatch(r"UNIQUE-\d{4}", code), code
    # dict keys are unique by construction; guard against duplicate *numbers*
    numbers = [code.split("-")[1] for code in DIAGNOSTICS]
    assert len(numbers) == len(set(numbers)), "duplicate diagnostic number"


def test_every_diagnostic_has_category_and_message():
    for code, diag in DIAGNOSTICS.items():
        assert diag.category in _ALLOWED_CATEGORIES, (code, diag.category)
        assert diag.message.strip(), code


def test_every_registered_code_is_emitted_in_src():
    """A registered template must be referenced by an emission site."""
    emitted: set[str] = set()
    for path in _src_files():
        for num in _CARRIER_RE.findall(path.read_text(encoding="utf-8")):
            emitted.add(f"UNIQUE-{num}")
    unreferenced = sorted(set(DIAGNOSTICS) - emitted)
    assert not unreferenced, f"registered but never emitted: {unreferenced}"


def test_every_emitted_carrier_code_is_registered():
    """A carrier emitted in src must have a registry entry (no drift)."""
    for path in _src_files():
        for num in _CARRIER_RE.findall(path.read_text(encoding="utf-8")):
            code = f"UNIQUE-{num}"
            assert code in DIAGNOSTICS, f"{code} emitted in {path.name}, unregistered"


def test_marker_regex_accepts_legacy_and_coded_forms():
    assert re.search(diagnostics.MARKER, "-- UNIQUE: legacy")
    m = re.search(diagnostics.MARKER, "-- UNIQUE-1042: coded")
    assert m and m.group("code") == "1042"


def test_is_registered():
    assert diagnostics.is_registered("UNIQUE-1001")
    assert not diagnostics.is_registered("UNIQUE-9999")
