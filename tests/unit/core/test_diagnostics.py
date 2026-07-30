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
from unique.core.rationales import RATIONALES, Rationale

_SRC = Path(diagnostics.__file__).parent.parent  # …/src/unique
_ROOT = _SRC.parent.parent  # repo root
_CHALLENGE_DIR = _ROOT / "tests" / "fixtures" / "challenge"
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
    """A registered template must be referenced by an emission site.

    A code reaches the output two ways: as a ``-- UNIQUE-NNNN:`` carrier in the
    emitted SQL, or as a ``code="UNIQUE-NNNN"`` argument on a direct warning
    (B32 wave 3 — non-carrier error/tripwire/guard paths). Either counts as a
    reference; an orphaned template (neither) is dead metadata.
    """
    referenced: set[str] = set()
    for path in _src_files():
        for num in _CODE_RE.findall(path.read_text(encoding="utf-8")):
            referenced.add(f"UNIQUE-{num}")
    unreferenced = sorted(set(DIAGNOSTICS) - referenced)
    assert not unreferenced, f"registered but never referenced: {unreferenced}"


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


# ---------------------------------------------------------------------------
# Rationale side-table coverage (B31).
#
# The number of diagnostic codes WITHOUT a registered rationale is a ratchet:
# it may only go DOWN. A new code lands uncovered (no rationale yet) — fine,
# as long as the total uncovered count does not RISE above the committed
# floor. Future rationale work lowers the floor; it is never raised. Mirrors
# the architecture ratchets (scripts/architecture_ratchets.py).
#
# To lower it: add honestly-sourced entries to unique.core.rationales.RATIONALES
# (each traceable to a docs/rationale/ page, a docs/03-unsupported.md section,
# or an emission-site docstring — never invented), then set this to the new,
# smaller count. Current: 232 registered − 118 with a rationale = 114 (a
# ddl/expression/procedural sourcing pass added 86 entries, corpus-verified
# and/or live-probed; codes with no traceable corpus case or test were left
# pending rather than invented — see the pass's report).
# ---------------------------------------------------------------------------
_RATIONALE_UNCOVERED_FLOOR = 114

_CASE_HEADER_RE = re.compile(
    r"^--\s*CASE\[[a-z]+\](?:\[[^\]]*\])*:\s*([A-Za-z0-9][A-Za-z0-9_-]*)\b"
)


def _corpus_case_ids() -> set[str]:
    ids: set[str] = set()
    for path in _CHALLENGE_DIR.glob("challenge_*.sql"):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _CASE_HEADER_RE.match(line)
            if m:
                ids.add(m.group(1))
    return ids


def test_rationale_keys_are_registered_codes():
    """A rationale must key on a real UNIQUE-NNNN diagnostic (no orphans)."""
    orphans = sorted(set(RATIONALES) - set(DIAGNOSTICS))
    assert not orphans, f"rationale for unregistered code(s): {orphans}"


def test_every_rationale_field_is_populated():
    for code, r in RATIONALES.items():
        assert isinstance(r, Rationale), code
        for field_name, value in r._asdict().items():
            assert value and value.strip(), (code, field_name)


def test_rationale_example_case_is_traceable():
    """``example_case`` must name a real corpus slug or a ``path::test`` ref —
    the traceability rule (never an invented example)."""
    case_ids = _corpus_case_ids()
    assert case_ids, "no challenge corpus found — cannot verify traceability"
    for code, r in RATIONALES.items():
        ex = r.example_case
        if "::" in ex:  # a named test where no corpus case exists
            rel_path = ex.split("::", 1)[0]
            assert (_ROOT / rel_path).is_file(), (code, ex)
        else:  # a challenge-corpus case slug
            assert ex in case_ids, f"{code}: unknown corpus case {ex!r}"


def test_rationale_coverage_ratchets_down():
    """Codes without a rationale must not exceed the committed floor."""
    uncovered = sorted(set(DIAGNOSTICS) - set(RATIONALES))
    assert len(uncovered) <= _RATIONALE_UNCOVERED_FLOOR, (
        f"{len(uncovered)} diagnostic codes have no rationale "
        f"(floor {_RATIONALE_UNCOVERED_FLOOR}); a new code without a rationale "
        "raised the count. Add an honestly-sourced entry to "
        "unique.core.rationales.RATIONALES, or lower the floor if you removed a "
        "code. The ratchet is monotonic downward."
    )
