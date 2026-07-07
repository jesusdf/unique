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


class TestGuardConditionDual:
    """Every SELECT needs a FROM on Oracle; a FROM-less subquery in the guard
    condition gets FROM DUAL going in and loses it coming back."""

    def test_fromless_exists_subquery_gets_dual(self) -> None:
        # Not just the outer probe — the inner ``EXISTS (SELECT NULL)`` needs a
        # FROM DUAL too, else the cursor is invalid PL/SQL (ORA-00923).
        out = transpile(
            "IF EXISTS (SELECT NULL)\nBEGIN\n  PRINT 'x'\nEND", "tsql", "oracle"
        ).sql
        assert "SELECT NULL FROM DUAL" in out.upper()

    def test_subquery_with_real_from_is_untouched(self) -> None:
        # A subquery that already has a source keeps it — DUAL must not replace it.
        out = transpile(
            "IF EXISTS (SELECT 1 FROM t WHERE id = 1)\nBEGIN\n  PRINT 'x'\nEND",
            "tsql",
            "oracle",
        ).sql
        assert "FROM t" in out and "SELECT 1 FROM DUAL WHERE" in out

    def test_condition_dual_stripped_on_reverse(self) -> None:
        # Round-trip: the inner FROM DUAL the forward pass added is dropped again
        # on T-SQL/PostgreSQL (neither has a DUAL table).
        guard = (
            "BEGIN FOR unique_guard IN "
            "(SELECT 1 FROM DUAL WHERE EXISTS (SELECT NULL FROM DUAL)) LOOP\n"
            "  DBMS_OUTPUT.PUT_LINE('run');\nEND LOOP; END;\n/"
        )
        for target in ("tsql", "postgresql"):
            out = transpile(guard, "oracle", target).sql
            assert "DUAL" not in out.upper(), target
            assert "EXISTS" in out.upper(), target
        assert not out.strip().startswith("IF (")
