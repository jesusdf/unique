# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""D6 (trigger event predicates → T-SQL), D7 (`TRUNC(date)`), D10
(`DBMS_SCHEDULER` → carrier)."""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str):
    return Transpiler().transpile(sql, source=source, target=target)


_MULTI_EVENT_TRG = """\
CREATE OR REPLACE TRIGGER trg1 AFTER INSERT OR DELETE ON t1 FOR EACH ROW
BEGIN
  IF INSERTING THEN
    INSERT INTO log_t (op) VALUES ('I');
  END IF;
  IF DELETING THEN
    INSERT INTO log_t (op) VALUES ('D');
  END IF;
END;
/"""


def test_inserting_deleting_predicates_map_to_tsql() -> None:
    r = _t(_MULTI_EVENT_TRG, "oracle", "tsql")
    up = " ".join(r.sql.split()).upper()
    assert "INSERTING" not in up, r.sql
    assert "DELETING" not in up, r.sql
    assert "EXISTS (SELECT 1 FROM INSERTED)" in up.replace("EXISTS(", "EXISTS (")
    assert "EXISTS (SELECT 1 FROM DELETED)" in up.replace("EXISTS(", "EXISTS (")


def test_new_assignment_inside_if_converts_to_setbased() -> None:
    # The row-level -> set-based conversion must recurse into IF bodies:
    # ':NEW.col := 1' nested in a condition used to leak as 'SET @new.col'.
    src = (
        "CREATE OR REPLACE TRIGGER trg2 BEFORE UPDATE ON t1 FOR EACH ROW\n"
        "BEGIN\n  IF :NEW.col_a > 0 THEN\n    :NEW.col_b := 1;\n  END IF;\nEND;\n/"
    )
    r = _t(src, "oracle", "tsql")
    up = " ".join(r.sql.split())
    assert "@new" not in up.lower(), r.sql
    assert re.search(r"(?i)UPDATE t1 SET col_b = 1", up), r.sql
    assert "FROM inserted" in up, r.sql


@pytest.mark.parametrize(
    ("target", "expected", "banned"),
    [
        ("tsql", r"(?i)CAST\s*\(\s*GETDATE\s*\(\s*\)\s+AS\s+DATE\s*\)", "DATE_TRUNC"),
        ("postgresql", r"(?i)DATE_TRUNC\s*\(\s*'day'", "'DD'"),
        ("mysql", r"(?i)\bDATE\s*\(", "DATE_TRUNC"),
    ],
)
def test_trunc_date_maps_per_target(target: str, expected: str, banned: str) -> None:
    # Oracle TRUNC(date) truncates to midnight; T-SQL (2012+) spells it
    # CAST(x AS DATE), PostgreSQL DATE_TRUNC('day', x), MySQL DATE(x).
    r = _t("UPDATE t1 SET d = TRUNC(SYSDATE) WHERE id = 1;", "oracle", target)
    assert re.search(expected, r.sql), r.sql
    assert banned not in r.sql.upper(), r.sql


@pytest.mark.parametrize("target", ["postgresql", "mysql", "tsql"])
def test_dbms_scheduler_degrades_to_carrier(target: str) -> None:
    src = (
        "BEGIN\n  DBMS_SCHEDULER.CREATE_JOB(job_name => 'j1', "
        "job_type => 'PLSQL_BLOCK', job_action => 'BEGIN NULL; END;');\nEND;\n/"
    )
    r = _t(src, "oracle", target)
    executable = [
        ln
        for ln in r.sql.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ]
    assert not any("DBMS_SCHEDULER" in ln.upper() for ln in executable), r.sql
    assert r.warnings or r.unsupported


# ---------------------------------------------------------------------------
# C1/C3 residue — unbracketed WHILE, hoisted initializer order, MySQL DO form
# ---------------------------------------------------------------------------

_UNBRACKETED_WHILE = """\
CREATE FUNCTION dbo.f1(@json NVARCHAR(4000)) RETURNS INT
AS
BEGIN
  DECLARE @i INT = 1
  WHILE @i <= LEN(@json) AND SUBSTRING(@json, @i, 1) IN (N' ', CHAR(9))
    SET @i = @i + 1

  DECLARE @ch NCHAR(1) = SUBSTRING(@json, @i, 1)
  IF @ch = N'"'
  BEGIN
    SET @i = @i + 1
  END
  RETURN @i
END"""


@pytest.mark.parametrize("target", ["postgresql", "oracle"])
def test_unbracketed_while_body_does_not_swallow_statements(target: str) -> None:
    r = _t(_UNBRACKETED_WHILE, "tsql", target)
    up = " ".join(r.sql.split()).upper()
    # The WHILE keeps only its condition; the loop closes properly.
    assert re.search(r"(?i)WHILE .*CHR\(9\)\S*\s+LOOP", up), r.sql
    assert "END LOOP" in up
    # And the mid-body DECLARE's initializer runs AFTER the loop (an
    # assignment at its original position), not hoisted before it.
    assert re.search(r"(?i)END LOOP.*V_CH\s*:=", up), r.sql


def test_mysql_while_uses_do_end_while() -> None:
    r = _t(_UNBRACKETED_WHILE, "tsql", "mysql")
    up = " ".join(r.sql.split()).upper()
    assert re.search(r"WHILE .* DO ", up), r.sql
    assert "END WHILE" in up
    assert "END LOOP" not in up


_TRY_CATCH_FN = """\
CREATE FUNCTION dbo.trg_f() RETURNS INT
AS
BEGIN
  DECLARE @cur CURSOR;
  DECLARE @tipodoc VARCHAR(1)
  SET @tipodoc = NULL

  BEGIN TRY
    INSERT INTO t1 (a) VALUES (1)
  END TRY
  BEGIN CATCH
    RETURN 0
  END CATCH
  RETURN 1
END"""


@pytest.mark.parametrize(
    ("target", "refcur"),
    [("oracle", "SYS_REFCURSOR"), ("postgresql", "REFCURSOR")],
)
def test_try_body_survives_and_cursor_var_maps(target: str, refcur: str) -> None:
    # The Oracle transform used to keep only the CATCH handlers and silently
    # DROP the TRY body; and a query-less cursor VARIABLE emitted the invalid
    # bare 'v_cur CURSOR;'. Also pins the 'SET @v = NULL' / 'BEGIN TRY'
    # statement boundary (the value used to swallow the block).
    r = _t(_TRY_CATCH_FN, "tsql", target)
    up = " ".join(r.sql.split()).upper()
    assert "INSERT INTO T1 (A) VALUES (1)" in up, r.sql  # TRY body survives
    assert "EXCEPTION" in up and "WHEN OTHERS" in up
    assert f"V_CUR {refcur};" in up, r.sql
    assert re.search(r"V_TIPODOC\s*:=\s*NULL\s*;", up), r.sql


_EXEC_IMMEDIATE_INTO = """\
DECLARE
  X NUMBER(9);
  SQLSTMT    VARCHAR2(4000);
BEGIN
  SQLSTMT := 'SELECT COUNT(*) TOTAL FROM cfg WHERE k = ''a''';
  EXECUTE IMMEDIATE SQLSTMT INTO X ;
  IF X >= 1 THEN
    EXECUTE IMMEDIATE 'update t1 set a = 1';
  END IF;
END;
/"""


def test_execute_immediate_into_tsql_capture() -> None:
    # ~344 statements on the real dump: 'EXEC sp_executesql @s INTO @x' is
    # not T-SQL — the capture is INSERT ... EXEC into a table variable.
    r = _t(_EXEC_IMMEDIATE_INTO, "oracle", "tsql")
    up = " ".join(r.sql.split())
    assert "INSERT INTO @_dyn_result_1 EXEC sp_executesql @sqlstmt" in up, r.sql
    assert re.search(r"SELECT TOP \(1\) @x = c1 FROM @_dyn_result_1", up), r.sql
    assert "INTO @x;" not in up


def test_execute_immediate_into_postgres_native() -> None:
    r = _t(_EXEC_IMMEDIATE_INTO, "oracle", "postgresql")
    assert re.search(r"(?i)EXECUTE SQLSTMT INTO X;", r.sql), r.sql


def test_execute_immediate_into_oracle_identity() -> None:
    r = _t(_EXEC_IMMEDIATE_INTO, "oracle", "oracle")
    assert "EXECUTE IMMEDIATE SQLSTMT INTO X;" in r.sql, r.sql


def test_pipe_concat_becomes_plus_in_tsql_assignments() -> None:
    # 356 dynamic-SQL assignments on the dump leaked '||' into T-SQL.
    src = (
        "DECLARE\n  S VARCHAR2(100);\n  V VARCHAR2(30);\nBEGIN\n"
        "  V := 'T1';\n  S := 'a||b: ' || V || ' done';\nEND;\n/"
    )
    r = _t(src, "oracle", "tsql")
    up = " ".join(r.sql.split())
    assert "'a||b: ' + @v + ' done'" in up, r.sql  # literal '||' preserved
