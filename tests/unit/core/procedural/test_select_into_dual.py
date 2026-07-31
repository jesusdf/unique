# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Oracle ``SELECT <expr> INTO v FROM DUAL`` → PostgreSQL ``SELECT <expr>
INTO v`` (PostgreSQL has no DUAL pseudo-table; a one-row scalar SELECT needs
no FROM). Before the B36 fix the ``FROM DUAL`` tail survived into the emitted
body and the output gate degraded the whole routine (UNIQUE-1151).

The strip is deliberately narrow: it fires only when the FROM/WHERE tail is
*exactly* ``FROM DUAL`` (a pure one-row scalar select). A statement that uses
DUAL as the driver of a real query (``BULK COLLECT … FROM DUAL CONNECT BY …``,
the Oracle string-split idiom) is a genuine no-equivalent and must keep
degrading — stripping only its FROM DUAL would ship invalid PostgreSQL.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler

t = Transpiler()


def _pg(oracle: str) -> object:
    return t.transpile(oracle, "oracle", "postgresql")


class TestSelectIntoFromDual:
    def test_scalar_select_into_dual_drops_from(self) -> None:
        res = _pg(
            "CREATE OR REPLACE FUNCTION f RETURN NUMBER AS\nBEGIN\n"
            "    SELECT ROUND(x * 86400) INTO v FROM DUAL;\n    RETURN v;\nEND;"
        )
        up = res.sql.upper()
        assert "FROM DUAL" not in up, res.sql
        assert "INTO V" in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql

    def test_nested_scalar_subquery_dual_also_stripped(self) -> None:
        # The column is itself a ``(SELECT … FROM DUAL)`` scalar subquery; both
        # the inner and the outer FROM DUAL must go.
        res = _pg(
            "CREATE OR REPLACE PROCEDURE p AS\nBEGIN\n"
            "    SELECT (SELECT CASE WHEN a = 1 THEN 2 ELSE 0 END FROM DUAL)"
            " INTO v_col_12 FROM DUAL;\nEND;"
        )
        up = res.sql.upper()
        assert "FROM DUAL" not in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql

    def test_bulk_collect_connect_by_still_degrades(self) -> None:
        # A genuine Oracle-only string-split idiom: keep degrading honestly
        # rather than ship invalid PostgreSQL by stripping only its FROM DUAL.
        res = _pg(
            "CREATE OR REPLACE FUNCTION func5 (v_s IN NVARCHAR2)\n"
            "RETURN SYS.ODCIVARCHAR2LIST IS\n"
            "    v_result SYS.ODCIVARCHAR2LIST := SYS.ODCIVARCHAR2LIST();\n"
            "BEGIN\n"
            "    SELECT TRIM(v_s) BULK COLLECT INTO v_result FROM DUAL\n"
            "    CONNECT BY LEVEL <= 3;\n    RETURN v_result;\nEND;"
        )
        # The whole routine must still carry the honest degrade, and must NOT
        # emit a half-converted BULK COLLECT/CONNECT BY as executable PG.
        assert any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql
