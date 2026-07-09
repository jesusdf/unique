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
