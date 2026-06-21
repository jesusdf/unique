# Copyright (C) 2026 Unique Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Functional-equivalence guards for stored-procedure transpilation.

Beyond "does it parse", a transpiled procedure must do the *same thing*. These
tests fingerprint a routine's structure (DML verb counts, fields per DML,
condition counts, IF branches and loops/cursors) before and after
transpilation and assert the dimensions that must be conserved. They are the
safety net against silent semantic drift — a dropped WHERE clause, a lost
column, a collapsed branch — that a syntax-only check would miss.

See tests/helpers/functional_equivalence.py for how the fingerprint is built.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.functional_equivalence import (
    assert_functionally_equivalent,
    fingerprint,
)
from unique.core.transpiler import Transpiler

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "procedures"

_TARGETS = ["oracle", "postgresql", "mysql"]


@pytest.fixture
def transpiler() -> Transpiler:
    return Transpiler()


# ---------------------------------------------------------------------------
# Fingerprint correctness on known inputs
# ---------------------------------------------------------------------------


class TestFingerprintCounts:
    def test_counts_dml_verbs(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    SELECT a FROM t\n"
            "    INSERT INTO u (x) VALUES (1)\n"
            "    UPDATE v SET y = 1 WHERE z = 2\n"
            "    DELETE FROM w WHERE k = 3\n"
            "END"
        )
        fp = fingerprint(src, "tsql")
        assert fp.selects == 1
        assert fp.inserts == 1
        assert fp.updates == 1
        assert fp.deletes == 1

    def test_counts_fields_per_dml(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    SELECT a, b, c FROM t\n"
            "    INSERT INTO u (x, y) VALUES (1, 2)\n"
            "    UPDATE v SET m = 1, n = 2, o = 3 WHERE z = 9\n"
            "END"
        )
        fp = fingerprint(src, "tsql")
        assert fp.select_field_counts == [3]
        assert fp.insert_field_counts == [2]
        assert fp.update_field_counts == [3]

    def test_counts_conditions(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    SELECT a FROM t WHERE x = 1 AND y > 2 AND z IN (3, 4)\n"
            "END"
        )
        fp = fingerprint(src, "tsql")
        # x = 1, y > 2, z IN (...) -> 3 predicates.
        assert fp.conditions == 3

    def test_counts_if_and_loops(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    IF @a > 0\n        SELECT 1\n"
            "    WHILE @i < 10\n    BEGIN\n        SELECT 2\n    END\n"
            "END"
        )
        fp = fingerprint(src, "tsql")
        assert fp.if_branches == 1
        assert fp.loops == 1


# ---------------------------------------------------------------------------
# The fingerprint actually catches a silent change
# ---------------------------------------------------------------------------


class TestDetectsSilentChange:
    def test_dropped_column_detected(self) -> None:
        src = "CREATE PROCEDURE p AS BEGIN SELECT a, b, c FROM t END"
        bad = "CREATE PROCEDURE p AS BEGIN SELECT a, b FROM t END"
        violations = assert_functionally_equivalent(src, "tsql", bad, "tsql")
        assert any("SELECT field counts" in v for v in violations)

    def test_dropped_condition_detected(self) -> None:
        src = "CREATE PROCEDURE p AS BEGIN SELECT a FROM t WHERE x = 1 AND y = 2 END"
        bad = "CREATE PROCEDURE p AS BEGIN SELECT a FROM t WHERE x = 1 END"
        violations = assert_functionally_equivalent(src, "tsql", bad, "tsql")
        assert any("condition counts" in v for v in violations)

    def test_dropped_dml_detected(self) -> None:
        src = (
            "CREATE PROCEDURE p AS BEGIN "
            "SELECT a FROM t UPDATE u SET x = 1 WHERE y = 2 END"
        )
        bad = "CREATE PROCEDURE p AS BEGIN SELECT a FROM t END"
        violations = assert_functionally_equivalent(src, "tsql", bad, "tsql")
        assert any("DML verbs" in v for v in violations)

    def test_dropped_branch_detected(self) -> None:
        src = "CREATE PROCEDURE p AS BEGIN " "IF @a > 0 SELECT 1 IF @b > 0 SELECT 2 END"
        bad = "CREATE PROCEDURE p AS BEGIN IF @a > 0 SELECT 1 END"
        violations = assert_functionally_equivalent(src, "tsql", bad, "tsql")
        assert any("IF branch" in v for v in violations)


# ---------------------------------------------------------------------------
# Real transpilations preserve the fingerprint
# ---------------------------------------------------------------------------


class TestTranspilationPreservesStructure:
    SAMPLES = [
        # name -> T-SQL source
        (
            "select_update_in_if",
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    IF @a > 0\n    BEGIN\n"
            "        SELECT x, y, z FROM t WHERE a = 1 AND b = 2\n"
            "        UPDATE u SET m = 1, n = 2 WHERE k = 3\n"
            "    END\n"
            "END",
        ),
        (
            "insert_select",
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    INSERT INTO dst (a, b) SELECT a, b FROM src WHERE c = 1\n"
            "END",
        ),
        (
            "multi_condition_delete",
            "CREATE PROCEDURE dbo.p AS\nBEGIN\n"
            "    DELETE FROM t WHERE a = 1 AND b > 2 AND c IN (3, 4)\n"
            "END",
        ),
    ]

    @pytest.mark.parametrize("name,src", SAMPLES, ids=[s[0] for s in SAMPLES])
    @pytest.mark.parametrize("target", _TARGETS)
    def test_sample_preserves_structure(
        self, transpiler: Transpiler, name: str, src: str, target: str
    ) -> None:
        out = transpiler.transpile(src, "tsql", target).sql
        violations = assert_functionally_equivalent(
            src,
            "tsql",
            out,
            target,
            # A FOR cursor loop can legitimately expand to OPEN/FETCH/CLOSE on
            # some targets, so control-flow counts are checked only where the
            # construct maps 1:1; these samples use IF/WHILE which are 1:1.
            check_control_flow=True,
        )
        assert not violations, f"{name} -> {target}: {violations}"


# ---------------------------------------------------------------------------
# Whole-fixture conservation (DML verbs and fields are the strict invariants)
# ---------------------------------------------------------------------------


class TestFixtureStructureConservation:
    @pytest.mark.parametrize("target", _TARGETS)
    def test_tsql_fixture_conserves_dml_verbs(self, target: str) -> None:
        text = (FIXTURE_DIR / "procedures_sqlserver.sql").read_text(encoding="utf-8")
        out = Transpiler().transpile(text, "tsql", target).sql
        src_fp = fingerprint(text, "tsql")
        out_fp = fingerprint(out, target)
        # DML verb totals must be conserved across the whole fixture. (Field
        # and condition multisets are asserted on the focused samples above,
        # where the expected counts are unambiguous; over the full fixture,
        # dynamic SQL and TVF expansions make exact field equality too strict.)
        assert src_fp.dml_verb_counts() == out_fp.dml_verb_counts(), (
            f"DML verbs not conserved tsql->{target}: "
            f"{src_fp.dml_verb_counts()} != {out_fp.dml_verb_counts()}"
        )
