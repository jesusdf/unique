# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""T-SQL requires scalar UDF calls to be schema-qualified (``dbo.fn(…)``).

An unqualified scalar-UDF call is error 195 ("not a recognized built-in
function name") at parse time — even when the function exists in the target
database, so "it resolves on the real DB" was never true. The 2026-07-11
sweep counted ~15 such calls (functions resident in the client DB, not
defined in the script, so the harvested USER_FUNCTIONS registry cannot know
them). The decision is now structural: an unqualified call whose name is
neither a T-SQL builtin nor a known other-dialect builtin (an unmapped
foreign builtin must stay a *visible* failure, not be masked as
``dbo.TO_NUMBER``) is qualified with ``dbo.`` — in the IR emitter for
standalone/embedded DML, and via the string-aware rewriter for procedural
raw expressions.
"""

from __future__ import annotations

import re

import pytest
import sqlglot

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestStandaloneDml:
    def test_update_assignment_value_is_qualified(self) -> None:
        out = _t("UPDATE h SET c = my_fn_guid();", "oracle", "tsql")
        assert "dbo.my_fn_guid(" in out, out
        assert not re.search(r"(?<!\.)\bmy_fn_guid\s*\(", out), out
        sqlglot.parse(out, read="tsql")

    def test_select_list_and_where_are_qualified(self) -> None:
        out = _t("SELECT my_fn(a) FROM t WHERE other_fn(b) = 1;", "oracle", "tsql")
        assert "dbo.my_fn(" in out, out
        assert "dbo.other_fn(" in out, out

    def test_known_builtin_mapping_is_not_qualified(self) -> None:
        out = _t("UPDATE h SET c = SYSDATE;", "oracle", "tsql")
        assert "GETDATE()" in out, out
        assert "dbo.GETDATE" not in out, out

    def test_unmapped_foreign_builtin_stays_visible(self) -> None:
        # Masking an unmapped Oracle builtin as dbo.REGEXP_SUBSTR would turn
        # a mapping gap into a phantom user function.
        out = _t("UPDATE h SET c = REGEXP_SUBSTR(a, 'x');", "oracle", "tsql")
        assert "dbo.REGEXP_SUBSTR" not in out, out

    def test_already_qualified_call_is_untouched(self) -> None:
        out = _t("UPDATE h SET c = other_schema.fn(a);", "oracle", "tsql")
        assert "other_schema.fn(" in out, out
        assert "dbo.other_schema" not in out, out
        assert "other_schema.dbo" not in out, out

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
    def test_other_targets_never_qualify(self, target: str) -> None:
        out = _t("UPDATE h SET c = my_fn_guid();", "oracle", target)
        assert "dbo." not in out, out


class TestProceduralRawExpressions:
    _ASSIGN = (
        "CREATE OR REPLACE PROCEDURE p_q(m_out OUT VARCHAR2) AS\n"
        "BEGIN\n"
        "  m_out := my_conf_fn('k', 'd');\n"
        "END;\n/"
    )

    def test_assignment_value_is_qualified(self) -> None:
        out = _t(self._ASSIGN, "oracle", "tsql")
        assert re.search(r"dbo\.my_conf_fn\s*\(", out), out
        assert not re.search(r"(?<!\.)\bmy_conf_fn\s*\(", out), out

    def test_if_condition_call_is_qualified(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_q2(m_a IN VARCHAR2) AS\n"
            "BEGIN\n"
            "  IF my_check_fn(m_a) = 1 THEN\n"
            "    NULL;\n"
            "  END IF;\n"
            "END;\n/"
        )
        out = _t(src, "oracle", "tsql")
        assert re.search(r"dbo\.my_check_fn\s*\(", out), out

    def test_string_literals_are_never_rewritten(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_q3(m_out OUT VARCHAR2) AS\n"
            "BEGIN\n"
            "  m_out := 'CALL (555)' || my_conf_fn(1);\n"
            "END;\n/"
        )
        out = _t(src, "oracle", "tsql")
        assert "'CALL (555)'" in out, out
        assert re.search(r"dbo\.my_conf_fn\s*\(", out), out

    def test_types_in_cast_are_not_qualified(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p_q4(m_out OUT NUMBER) AS\n"
            "BEGIN\n"
            "  m_out := CAST(my_num_fn(2) AS DECIMAL(10, 2));\n"
            "END;\n/"
        )
        out = _t(src, "oracle", "tsql")
        assert "dbo.DECIMAL" not in out, out
        assert "dbo.CAST" not in out, out
        assert re.search(r"dbo\.my_num_fn\s*\(", out), out
