# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""T-SQL cursor variables (``SET @c = CURSOR ... FOR q`` + bare ``OPEN @c``).

These used to fall through to sqlglot as embedded DML, which shipped invalid
``v_cur := CURSOR LOCAL FAST_FORWARD FOR ...`` assignments and mangled the
cursor operations into ``OPEN AS v_cur`` / ``CLOSE AS v_cur`` on every target
(test2 sweep residue, 2026-07-10).
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler

_CURSOR_VAR_SRC = """CREATE PROCEDURE dbo.p9 AS
BEGIN
  DECLARE @cur CURSOR;
  DECLARE @id INT;
  SET @cur = CURSOR LOCAL FAST_FORWARD FOR SELECT id FROM t1;
  OPEN @cur;
  FETCH NEXT FROM @cur INTO @id;
  CLOSE @cur;
  DEALLOCATE @cur;
END"""

_CLASSIC_SRC = """CREATE PROCEDURE dbo.p10 AS
BEGIN
  DECLARE @id INT;
  DECLARE c1 CURSOR FOR SELECT id FROM t1;
  OPEN c1;
  FETCH NEXT FROM c1 INTO @id;
  CLOSE c1;
  DEALLOCATE c1;
END"""


def _one_line(sql: str) -> str:
    return " ".join(sql.split())


def test_cursor_variable_to_postgresql_opens_for_query() -> None:
    out = Transpiler().transpile(_CURSOR_VAR_SRC, "tsql", "postgresql").sql
    up = _one_line(out)
    assert re.search(r"(?i)v_cur\s+REFCURSOR", up), out
    assert re.search(r"(?i)OPEN v_cur FOR\s+SELECT id FROM t1", up), out
    # The binding must not leak as an assignment, and the later bare OPEN
    # must not double-open the (already open) cursor.
    assert "CURSOR LOCAL" not in up.upper(), out
    assert not re.search(r"(?i)OPEN v_cur\s*;", up), out
    assert re.search(r"(?i)FETCH v_cur INTO v_id", up), out
    assert ";;" not in out, out


def test_cursor_variable_to_oracle_opens_for_query() -> None:
    out = Transpiler().transpile(_CURSOR_VAR_SRC, "tsql", "oracle").sql
    up = _one_line(out)
    assert re.search(r"(?i)V_CUR\s+SYS_REFCURSOR", up), out
    assert re.search(r"(?i)OPEN V_CUR FOR\s+SELECT id FROM t1", up), out
    assert "CURSOR LOCAL" not in up.upper(), out
    assert not re.search(r"(?i)OPEN v_cur\s*;", up), out
    assert ";;" not in out, out


def test_cursor_variable_to_mysql_merges_query_into_declaration() -> None:
    # MySQL has no cursor variables: the query moves onto the declaration
    # and the bare OPEN stays (that is where the query actually runs).
    out = Transpiler().transpile(_CURSOR_VAR_SRC, "tsql", "mysql").sql
    up = _one_line(out)
    assert re.search(r"(?i)DECLARE v_cur CURSOR FOR\s+SELECT id FROM t1", up), out
    assert re.search(r"(?i)OPEN v_cur\s*;", up), out
    # Exactly one declaration survives (the query-less one is superseded).
    assert len(re.findall(r"(?i)DECLARE v_cur CURSOR", up)) == 1, out
    assert "SET v_cur" not in up, out
    assert "CURSOR LOCAL" not in up.upper(), out


def test_cursor_variable_tsql_identity_keeps_variable_form() -> None:
    out = Transpiler().transpile(_CURSOR_VAR_SRC, "tsql", "tsql").sql
    up = _one_line(out)
    # The variable keeps its '@' everywhere (DECLARE cur CURSOR; without a
    # FOR query is a syntax error, and OPEN cur would not match SET @cur).
    assert "DECLARE @cur CURSOR;" in up, out
    assert re.search(r"(?i)SET @cur = CURSOR LOCAL FAST_FORWARD FOR", up), out
    assert "OPEN @cur;" in up, out
    assert re.search(r"(?i)FETCH NEXT FROM @cur INTO @id", up), out
    assert "DEALLOCATE @cur;" in up, out


def test_classic_cursor_ops_no_longer_mangled() -> None:
    # OPEN/FETCH/CLOSE/DEALLOCATE fell to embedded DML before: sqlglot
    # emitted ``OPEN AS c1`` / ``CLOSE AS c1`` (alias mis-parse).
    for target, opened in (
        ("postgresql", "v_c1"),
        ("oracle", "V_C1"),
        ("mysql", "v_c1"),
    ):
        out = Transpiler().transpile(_CLASSIC_SRC, "tsql", target).sql
        up = _one_line(out)
        assert f"OPEN {opened};" in up, (target, out)
        assert " AS " not in up.replace("AS $$", "").replace("LANGUAGE plpgsql", ""), (
            target,
            out,
        )
        assert re.search(rf"(?i)FETCH {opened} INTO", up), (target, out)
        assert f"CLOSE {opened};" in up, (target, out)


def test_open_symmetric_key_not_treated_as_cursor() -> None:
    src = (
        "CREATE PROCEDURE dbo.p11 AS\nBEGIN\n"
        "  OPEN SYMMETRIC KEY sk DECRYPTION BY CERTIFICATE c1;\n"
        "END"
    )
    out = Transpiler().transpile(src, "tsql", "tsql").sql
    assert "SYMMETRIC" in out.upper(), out
