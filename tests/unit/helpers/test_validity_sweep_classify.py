# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Unit tests for the validity sweep's pure error classifiers.

The sweep's value is separating transpiler defects (syntax-class) from the
noise of running against an empty database (missing tables/objects); these
pin the classification rules for each engine.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "validity_sweep",
    Path(__file__).resolve().parents[3] / "scripts" / "validity_sweep.py",
)
assert _SPEC is not None and _SPEC.loader is not None
validity_sweep = importlib.util.module_from_spec(_SPEC)
sys.modules["validity_sweep"] = validity_sweep
_SPEC.loader.exec_module(validity_sweep)


class TestClassifyPostgres:
    def test_syntax_error_is_syntax_class(self) -> None:
        assert validity_sweep.classify_pg("42601") == "SYNTAX"

    def test_missing_table_is_expected(self) -> None:
        assert validity_sweep.classify_pg("42P01") == "expected"

    def test_missing_function_is_expected(self) -> None:
        # The schema (incl. its routines) is not loaded; a CALL to a missing
        # procedure is not a transpiler defect.
        assert validity_sweep.classify_pg("42883") == "expected"

    def test_unknown_state_is_other(self) -> None:
        assert validity_sweep.classify_pg("55006") == "other"


class TestClassifyMySQL:
    def test_parse_error_is_syntax_class(self) -> None:
        assert validity_sweep.classify_mysql(1064) == "SYNTAX"

    def test_missing_table_is_expected(self) -> None:
        assert validity_sweep.classify_mysql(1146) == "expected"


class TestClassifyOracle:
    def test_invalid_statement_is_syntax_class(self) -> None:
        assert validity_sweep.classify_oracle("ORA-00900: invalid SQL") == "SYNTAX"

    def test_plsql_compile_error_is_syntax_class(self) -> None:
        msg = "ORA-06550: line 3\nPLS-00103: Encountered the symbol"
        assert validity_sweep.classify_oracle(msg) == "SYNTAX"

    def test_missing_table_is_expected(self) -> None:
        assert validity_sweep.classify_oracle("ORA-00942: table or view") == "expected"

    def test_unclassified_is_other(self) -> None:
        assert validity_sweep.classify_oracle("ORA-12345: whatever") == "other"

    def test_missing_identifier_inside_6550_is_expected(self) -> None:
        # ORA-06550 wraps *any* PL/SQL compile problem. A call to a routine
        # that is simply not loaded (PLS-00201) is empty-database noise, not a
        # transpiler defect. (Trade-off: an undeclared *variable* is also
        # PLS-00201 — schema-less runs cannot tell them apart.)
        msg = (
            "ORA-06550: line 2, column 5: PLS-00201: identifier "
            "'MY_PROC' must be declared"
        )
        assert validity_sweep.classify_oracle(msg) == "expected"

    def test_missing_table_inside_6550_is_expected(self) -> None:
        msg = (
            "ORA-06550: line 2, column 77: PL/SQL: ORA-00942: "
            "table or view does not exist"
        )
        assert validity_sweep.classify_oracle(msg) == "expected"
