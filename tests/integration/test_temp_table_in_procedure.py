# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""B28a: ``SELECT … INTO #tmp`` inside a converted T-SQL procedure.

The composition ``CREATE PROCEDURE … SELECT INTO #w … cursor over #w`` used to
degrade piecemeal: plpgsql got ``SELECT … INTO TEMPORARY w`` (INTO means a
variable there), Oracle got a ``SELECT … INTO <table>`` PLS error, all under
one generic "review the statement" warning. Each target now grows a real
temp-table idiom: PG/MySQL a ``CREATE TEMPORARY TABLE … AS SELECT`` (recreated
per call), Oracle a session Global Temporary Table hoisted before the routine
with a per-call ``DELETE``/``INSERT``.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler

_SRC = (
    "CREATE PROCEDURE dbo.rollup_report\n"
    "AS\n"
    "BEGIN\n"
    "    SELECT cust_id, amount INTO #w FROM orders WHERE amount > 0;\n"
    "    DECLARE @cid INT, @amt INT;\n"
    "    DECLARE c CURSOR FOR SELECT cust_id, amount FROM #w;\n"
    "    OPEN c;\n"
    "    FETCH NEXT FROM c INTO @cid, @amt;\n"
    "    WHILE @@FETCH_STATUS = 0\n"
    "    BEGIN\n"
    "        PRINT @cid;\n"
    "        FETCH NEXT FROM c INTO @cid, @amt;\n"
    "    END\n"
    "    CLOSE c;\n"
    "    DEALLOCATE c;\n"
    "END"
)


def _transpile(source: str, target: str, sql: str = _SRC) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _warnings(source: str, target: str, sql: str = _SRC) -> list[str]:
    return [w.message for w in Transpiler().transpile(sql, source, target).warnings]


class TestPostgreSQL:
    def test_creates_temp_table_not_select_into_variable(self) -> None:
        out = _transpile("tsql", "postgresql")
        up = " ".join(out.split())
        # The temp table is real DDL, not the invalid plpgsql ``INTO`` form.
        assert re.search(r"(?i)CREATE TEMPORARY TABLE w AS\s+SELECT", up), out
        assert not re.search(r"(?i)INTO TEMPORARY", up), out
        assert not re.search(r"(?i)SELECT[^;]*\bINTO w\b", up), out
        # A second CALL in the same session must recreate it.
        assert re.search(r"(?i)DROP TABLE IF EXISTS w\b", up), out
        # The cursor reads the same relation.
        assert re.search(r"(?i)FROM w\b", up), out

    def test_no_generic_embedded_dml_warning(self) -> None:
        assert not any(
            "Embedded DML not modeled" in w for w in _warnings("tsql", "postgresql")
        )


class TestMySQL:
    def test_creates_temp_table(self) -> None:
        out = _transpile("tsql", "mysql")
        up = " ".join(out.split())
        assert re.search(r"(?i)CREATE TEMPORARY TABLE w AS\s+SELECT", up), out
        assert re.search(r"(?i)DROP TEMPORARY TABLE IF EXISTS w\b", up), out

    def test_not_found_handler_precedes_the_temp_ddl(self) -> None:
        # MySQL declarations (incl. the NOT FOUND handler) must precede every
        # executable statement — the CREATE TEMPORARY TABLE is executable.
        out = _transpile("tsql", "mysql")
        handler = out.upper().find("DECLARE CONTINUE HANDLER FOR NOT FOUND")
        create = out.upper().find("CREATE TEMPORARY TABLE")
        assert handler != -1 and create != -1, out
        assert handler < create, out


class TestOracle:
    def test_hoists_global_temporary_table(self) -> None:
        out = _transpile("tsql", "oracle")
        up = " ".join(out.split())
        # GTT declared before the procedure (a CREATE cannot live in PL/SQL).
        gtt = re.search(
            r"(?i)CREATE GLOBAL TEMPORARY TABLE (\w+) ON COMMIT PRESERVE ROWS", up
        )
        assert gtt is not None, out
        name = gtt.group(1)
        assert up.index("CREATE GLOBAL TEMPORARY TABLE") < up.index(
            "CREATE OR REPLACE PROCEDURE"
        ), out
        # Body clears + repopulates the GTT (no ``SELECT … INTO <table>``).
        assert re.search(rf"(?i)DELETE FROM {name}\b", up), out
        assert re.search(rf"(?i)INSERT INTO {name}\b", up), out
        assert not re.search(r"(?i)SELECT[^;]*\bINTO w\b", up), out
        # References renamed to the hoisted GTT, none left bare ``w``.
        assert re.search(rf"(?i)FROM {name}\b", up), out


class TestFunctionNotHoisted:
    """A ``SELECT … INTO #tmp`` outside a procedure (here inside a function)
    must NOT emit an un-hoistable Oracle CREATE into the body — it falls back
    to the honest warned degrade."""

    _FN = (
        "CREATE FUNCTION dbo.f() RETURNS INT\n"
        "AS\n"
        "BEGIN\n"
        "    SELECT id INTO #w FROM t;\n"
        "    RETURN 1;\n"
        "END"
    )

    def test_oracle_function_does_not_emit_body_create(self) -> None:
        out = _transpile("tsql", "oracle", self._FN)
        # No naked CREATE GLOBAL TEMPORARY TABLE stranded inside the PL/SQL body.
        assert "CREATE GLOBAL TEMPORARY TABLE" not in out.upper(), out
