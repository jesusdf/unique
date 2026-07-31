# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""B38: a procedural batch that carries a routine's companion DDL ahead of it.

The BatchSplitter's PL/SQL-block heuristic folds a routine's companion DDL —
e.g. the global temporary table that backs a former T-SQL table variable —
into the same batch as the routine. The procedural parser only understands a
routine at the head, so the whole batch (DDL and routine both) used to degrade
to a single UNIQUE-1170 "could not parse procedural construct" carrier: the DDL
never converted and the routine was lost.

The procedural pipeline now peels the leading complete statement(s) off, routes
them through the standalone DML/DDL pipeline, and transpiles the routine alone.
"""

from __future__ import annotations

import re

import sqlglot

from unique.core.output_gate import _SQLGLOT_DIALECT
from unique.core.transpiler import Transpiler

# An Oracle procedural batch shaped like the generated fixture: a codegen
# comment header (one line of which mentions ``CREATE PROCEDURE`` and so trips
# the splitter's PL/SQL heuristic and folds the DDL in), the companion global
# temporary table, then the routine that uses it.
_ORACLE_SRC = (
    "-- codegen header\n"
    "-- EXECUTE([CREATE PROCEDURE my_proc AS SELECT 1])\n"
    "/* UNIQUE-1196: was T-SQL table variable V_TMP */\n"
    "CREATE GLOBAL TEMPORARY TABLE my_proc_v_tmp (\n"
    "  c1 RAW(16)\n"
    ") ON COMMIT DELETE ROWS;\n"
    "CREATE OR REPLACE PROCEDURE my_proc\n"
    "(\n"
    "    p1 IN NUMBER DEFAULT NULL,\n"
    "    result_cursor OUT SYS_REFCURSOR\n"
    ")\n"
    "IS\n"
    "    v_d DATE;\n"
    "BEGIN\n"
    "    v_d := SYSDATE;\n"
    "    OPEN result_cursor FOR SELECT c1 FROM my_proc_v_tmp;\n"
    "END;"
)

# A MySQL batch of the same shape (the companion temp table folds into the
# DELIMITER-less routine's batch too).
_MYSQL_SRC = (
    "-- codegen header\n"
    "-- helper CREATE PROCEDURE my_proc note\n"
    "CREATE TEMPORARY TABLE my_proc_tmp (\n"
    "  c1 INT\n"
    ");\n"
    "CREATE PROCEDURE my_proc(IN p1 INT)\n"
    "BEGIN\n"
    "  INSERT INTO my_proc_tmp VALUES (p1);\n"
    "  SELECT c1 FROM my_proc_tmp;\n"
    "END"
)


def _transpile(sql: str, source: str, target: str) -> object:
    return Transpiler().transpile(sql, source=source, target=target)


def _codes(result: object) -> list[str]:
    return [w.code for w in result.warnings]  # type: ignore[attr-defined]


def _parses(sql: str, target: str) -> None:
    sqlglot.parse(
        sql, read=_SQLGLOT_DIALECT[target], error_level=sqlglot.ErrorLevel.RAISE
    )


class TestOracleSource:
    def test_oracle_to_postgresql_converts_both_ddl_and_routine(self) -> None:
        result = _transpile(_ORACLE_SRC, "oracle", "postgresql")
        out = result.sql  # type: ignore[attr-defined]
        # The whole-batch giveup is gone.
        assert "UNIQUE-1170" not in _codes(result), out
        assert "could not translate" not in out, out
        # The companion GTT converted through the DDL pipeline.
        assert re.search(r"(?i)CREATE TEMPORARY TABLE my_proc_v_tmp", out), out
        assert not re.search(r"(?i)GLOBAL TEMPORARY", out), out
        assert not re.search(r"(?i)\bRAW\s*\(", out), out  # RAW(16) -> BYTEA
        assert not re.search(r"(?i)ON COMMIT DELETE ROWS", out), out
        # The routine transpiled to plpgsql (source idioms gone).
        assert re.search(r"(?i)CREATE OR REPLACE PROCEDURE my_proc", out), out
        assert re.search(r"(?i)LANGUAGE plpgsql", out), out
        assert not re.search(r"(?i)SYS_REFCURSOR", out), out
        assert not re.search(r"(?i)SYSDATE", out), out
        _parses(out, "postgresql")

    def test_oracle_to_tsql_converts_both_ddl_and_routine(self) -> None:
        result = _transpile(_ORACLE_SRC, "oracle", "tsql")
        out = result.sql  # type: ignore[attr-defined]
        assert "UNIQUE-1170" not in _codes(result), out
        # DDL became a T-SQL table (no Oracle GTT storage clause survives).
        assert re.search(r"(?i)CREATE TABLE my_proc_v_tmp", out), out
        assert not re.search(r"(?i)ON COMMIT DELETE ROWS", out), out
        # Routine present as a T-SQL module, Oracle idioms gone.
        assert re.search(r"(?i)PROCEDURE my_proc", out), out
        assert not re.search(r"(?i)SYS_REFCURSOR", out), out
        assert not re.search(r"(?i)\bIS\b\s*\n", out) or "AS" in out.upper(), out
        _parses(out, "tsql")


class TestMySQLSource:
    def test_mysql_to_postgresql_converts_both_ddl_and_routine(self) -> None:
        result = _transpile(_MYSQL_SRC, "mysql", "postgresql")
        out = result.sql  # type: ignore[attr-defined]
        assert "UNIQUE-1170" not in _codes(result), out
        assert re.search(r"(?i)CREATE TEMPORARY TABLE my_proc_tmp", out), out
        # Routine reached plpgsql rather than dying in the whole-batch carrier.
        assert re.search(r"(?i)CREATE (OR REPLACE )?PROCEDURE my_proc", out), out
        assert re.search(r"(?i)LANGUAGE plpgsql", out), out
        _parses(out, "postgresql")

    def test_mysql_to_oracle_converts_both_ddl_and_routine(self) -> None:
        result = _transpile(_MYSQL_SRC, "mysql", "oracle")
        out = result.sql  # type: ignore[attr-defined]
        assert "UNIQUE-1170" not in _codes(result), out
        # MySQL temp table becomes an Oracle global temporary table.
        assert re.search(r"(?i)GLOBAL TEMPORARY TABLE my_proc_tmp", out), out
        # Routine present as an Oracle module (MySQL BEGIN body is not wrapped
        # in a DELIMITER directive on Oracle).
        assert re.search(r"(?i)PROCEDURE my_proc", out), out
        assert not re.search(r"(?i)DELIMITER", out), out


class TestWholeUnitDegradeContractPreserved:
    """A genuinely unparseable single-routine batch still degrades whole."""

    def test_single_routine_no_leading_ddl_is_not_peeled(self) -> None:
        # No leading statement -> split yields one statement -> no peel; a
        # normal routine still transpiles as one unit.
        src = "CREATE OR REPLACE PROCEDURE solo\n" "IS\nBEGIN\n  NULL;\nEND;"
        result = _transpile(src, "oracle", "postgresql")
        out = result.sql  # type: ignore[attr-defined]
        assert re.search(r"(?i)CREATE OR REPLACE PROCEDURE solo", out), out
        _parses(out, "postgresql")
