# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""B39: procedural warning-code fidelity.

``ProceduralParser``/``ProceduralTransformer`` warnings used to be stamped
with the flat generic ``UNIQUE-1230``/``UNIQUE-1231`` codes at emission time
(``_core.py``), even when the same batch's rendered carrier already carried a
more specific ``UNIQUE-NNNN`` code (e.g. ``UNIQUE-1171`` for a whole routine
preserved as a comment, ``UNIQUE-1193`` for a dropped dialect-specific SET
option). Consumers of ``result.warnings[].code`` — similarity reports, the
web UI's code links, code-frequency triage — read the wrong code.

The fix: these warnings now ship ``code=None`` and rely on the existing
carrier-reconciliation backfill (``_core.py``'s per-batch loop) to stamp the
SPECIFIC code embedded in the rendered carrier; only when no carrier covers
the warning does it fall back to the generic ``UNIQUE-1230``/``UNIQUE-1231``.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler


def test_specific_carrier_code_survives_into_warning_code() -> None:
    """A MySQL user-variable whole-routine degrade reports UNIQUE-1171, not
    the generic UNIQUE-1231, matching the code embedded in its own carrier."""
    sql = (
        "CREATE PROCEDURE my_proc()\n"
        "BEGIN\n"
        "    DECLARE v INT;\n"
        "    SET @my_var = 'x';\n"
        "    SET v = 1;\n"
        "END"
    )
    result = Transpiler().transpile(sql, source="mysql", target="postgresql")

    assert "-- UNIQUE-1171:" in result.sql, result.sql
    matching = [w for w in result.warnings if "my_var" in w.message]
    assert matching, [(w.code, w.message) for w in result.warnings]
    for w in matching:
        assert w.code == "UNIQUE-1171", (w.code, w.message)
        assert w.code != "UNIQUE-1231", (w.code, w.message)


def test_dropped_set_option_reports_its_own_specific_code() -> None:
    """SET NOCOUNT ON has no target equivalent; the parser's parse-warning
    must carry the SAME UNIQUE-1193 code as the carrier the transformer
    builds for it, not the generic UNIQUE-1230 parse-note code."""
    sql = (
        "CREATE PROCEDURE dbo.my_proc\n"
        "AS\n"
        "BEGIN\n"
        "    SET NOCOUNT ON;\n"
        "    SELECT 1;\n"
        "END"
    )
    result = Transpiler().transpile(sql, source="tsql", target="postgresql")

    assert "UNIQUE-1193:" in result.sql, result.sql
    matching = [w for w in result.warnings if "NOCOUNT" in w.message]
    assert matching, [(w.code, w.message) for w in result.warnings]
    for w in matching:
        assert w.code == "UNIQUE-1193", (w.code, w.message)
        assert w.code != "UNIQUE-1230", (w.code, w.message)


def test_genuinely_generic_transform_warning_keeps_fallback_code() -> None:
    """A table-valued-function reference in FROM position has no carrier of
    its own (the routine degrades separately, at the whole-batch validity
    gate, under an unrelated UNIQUE-1151 code) — the "Embedded DML not
    modeled" transform warning has no more specific code to inherit, so it
    must keep the honest UNIQUE-1231 fallback."""
    sql = (
        "CREATE PROCEDURE dbo.my_proc\n"
        "AS\n"
        "BEGIN\n"
        "    SELECT value FROM STRING_SPLIT('a,b,c', ',');\n"
        "END"
    )
    result = Transpiler().transpile(sql, source="tsql", target="postgresql")

    matching = [w for w in result.warnings if "Embedded DML not modeled" in w.message]
    assert matching, [(w.code, w.message) for w in result.warnings]
    for w in matching:
        assert w.code == "UNIQUE-1231", (w.code, w.message)


def test_genuinely_generic_parse_warning_keeps_fallback_code() -> None:
    """The same SET-option construct, transpiled to its OWN source dialect
    (a no-op transform), leaves no carrier at all in the output — the parse
    warning has nothing to inherit a specific code from, so it must keep
    the honest UNIQUE-1230 fallback."""
    sql = (
        "CREATE PROCEDURE dbo.my_proc\n"
        "AS\n"
        "BEGIN\n"
        "    SET NOCOUNT ON;\n"
        "    SELECT 1;\n"
        "END"
    )
    result = Transpiler().transpile(sql, source="tsql", target="tsql")

    assert "UNIQUE-" not in result.sql, result.sql
    matching = [w for w in result.warnings if "NOCOUNT" in w.message]
    assert matching, [(w.code, w.message) for w in result.warnings]
    for w in matching:
        assert w.code == "UNIQUE-1230", (w.code, w.message)
