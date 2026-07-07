# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""A ``FROM DUAL`` guard FOR-loop round-trips to an ``IF`` (not a dead cursor).

``FOR <var> IN (SELECT 1 FROM DUAL WHERE <cond>) LOOP … END LOOP`` runs its body
0 or 1 times — it is exactly the idempotent guard Unique emits for Oracle. On
engines whose IF takes a SQL condition it must come back as ``IF <cond> …``, not
an explicit cursor scanning ``FROM DUAL`` (which is invalid off Oracle).
"""

from __future__ import annotations

from unique.core.transpiler import transpile

_GUARD = (
    "BEGIN FOR unique_guard IN "
    "(SELECT 1 FROM DUAL WHERE NOT EXISTS (SELECT NULL FROM t WHERE id = 1)) LOOP\n"
    "  DBMS_OUTPUT.PUT_LINE('run');\n"
    "END LOOP; END;\n/"
)


class TestDualGuardForLoop:
    def test_guard_becomes_if_on_tsql(self) -> None:
        out = transpile(_GUARD, "oracle", "tsql").sql
        assert out.strip().startswith("IF (")
        assert "NOT EXISTS" in out
        assert "DUAL" not in out
        assert "CURSOR" not in out

    def test_guard_becomes_if_on_postgresql(self) -> None:
        out = transpile(_GUARD, "oracle", "postgresql").sql
        assert "IF NOT EXISTS" in out
        assert "END IF;" in out
        assert "DUAL" not in out

    def test_guard_kept_as_for_loop_on_oracle(self) -> None:
        # Oracle expresses the guard *as* the FOR-loop over DUAL — keep it.
        out = transpile(_GUARD, "oracle", "oracle").sql
        assert "FOR unique_guard IN" in out
        assert "FROM DUAL" in out

    def test_real_cursor_loop_stays_a_cursor(self) -> None:
        # A loop that binds real rows must not collapse to an IF.
        real = (
            "BEGIN FOR r IN (SELECT id FROM customers WHERE active = 1) LOOP\n"
            "  DBMS_OUTPUT.PUT_LINE(r.id);\nEND LOOP; END;\n/"
        )
        out = transpile(real, "oracle", "tsql").sql
        assert "CURSOR" in out
        assert not out.strip().startswith("IF (")
