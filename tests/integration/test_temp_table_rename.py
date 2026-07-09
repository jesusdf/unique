# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""N2: the PG→T-SQL temp-table rename must be script-wide.

``SELECT * INTO TEMPORARY tmp; SELECT a FROM tmp; DROP TABLE tmp`` used to
emit ``INTO #tmp`` but leave ``FROM tmp``/``DROP tmp`` — the output created
one table and read another, silently.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler

_SRC = (
    "SELECT * INTO TEMPORARY tmp FROM src_t WHERE k = 1;\n"
    "SELECT a FROM tmp WHERE b = 2;\n"
    "DROP TABLE tmp;"
)


def test_temp_table_rename_is_script_wide() -> None:
    out = Transpiler().transpile(_SRC, "postgresql", "tsql").sql
    up = " ".join(out.split())
    assert "INTO #tmp" in up, out
    assert re.search(r"(?i)FROM #tmp\b", up), out
    assert re.search(r"(?i)DROP TABLE (IF EXISTS )?#tmp\b", up), out
    # No bare reference survives (word-boundary: '#tmp' is fine, ' tmp' not).
    assert not re.search(r"(?i)(?<!#)\btmp\b", up.replace("#tmp", "#T")), out


def test_create_temporary_table_form_also_renames() -> None:
    src = (
        "CREATE TEMPORARY TABLE stage (id INT);\n"
        "INSERT INTO stage (id) VALUES (1);\n"
        "SELECT id FROM stage;"
    )
    out = Transpiler().transpile(src, "postgresql", "tsql").sql
    up = " ".join(out.split())
    assert re.search(r"(?i)CREATE TABLE #stage\b", up), out
    assert re.search(r"(?i)INSERT INTO #stage\b", up), out
    assert re.search(r"(?i)FROM #stage\b", up), out


def test_round_trip_restores_pg_temp_semantics() -> None:
    # PG -> T-SQL -> PG: the table must stay one coherent temp relation.
    mid = Transpiler().transpile(_SRC, "postgresql", "tsql").sql
    back = Transpiler().transpile(mid, "tsql", "postgresql").sql
    up = " ".join(back.split())
    # One consistent name throughout (no #, and no split tmp/#tmp pair).
    assert "#" not in up, back
    names = set(
        re.findall(
            r"(?i)\b(?:INTO|FROM|TABLE)\s+(?:IF EXISTS\s+)?(?:TEMP(?:ORARY)?\s+)?"
            r"([\w#]+)",
            up,
        )
    )
    names.discard("src_t")
    assert len({n.lower().lstrip('"') for n in names}) == 1, back


def test_non_temp_tables_untouched() -> None:
    src = "SELECT a FROM tmp WHERE b = 2;"  # no temp declaration anywhere
    out = Transpiler().transpile(src, "postgresql", "tsql").sql
    assert "#tmp" not in out
