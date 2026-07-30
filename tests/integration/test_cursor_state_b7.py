# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Per-cursor state emulation (audit 2026-07-24 B7 — findings N5a/b/c + N6).

Oracle cursor attributes have no cross-engine global: a single ``@@FETCH_STATUS``
(T-SQL) or a single shared ``v_fetch_done`` handler flag (MySQL) is clobbered by
a FETCH on another cursor, and two nested loops both named ``loop_lbl`` collide
on MySQL. The class fix gives each cursor its own state variables, mirroring the
existing ``%ROWCOUNT`` counter, and emits a unique label per loop.

Structural tests run always; the value/row-set tests execute the produced
routine on the real engines and are skipped unless the matching
``UNIQUE_TEST_*_URL`` is set (like ``test_live_syntax``).
"""

from __future__ import annotations

import contextlib
import os
import re

import pytest

from unique.core.transpiler import Transpiler

# ---- source procedures (compile VALID on live Oracle) ----------------------

NESTED = """CREATE OR REPLACE PROCEDURE wtb7_nested IS
  CURSOR c1 IS SELECT id FROM wtb7_parent ORDER BY id;
  CURSOR c2 IS SELECT cid FROM wtb7_child ORDER BY cid;
  v_p NUMBER; v_c NUMBER;
BEGIN
  OPEN c1;
  LOOP
    FETCH c1 INTO v_p;
    EXIT WHEN c1%NOTFOUND;
    OPEN c2;
    LOOP
      FETCH c2 INTO v_c;
      EXIT WHEN c2%NOTFOUND;
    END LOOP;
    CLOSE c2;
    INSERT INTO wtb7_seen(pid) VALUES (v_p);
  END LOOP;
  CLOSE c1;
END;"""

# A FETCH on c2 intervenes between FETCH c1 and the c1%NOTFOUND check: the
# single global @@FETCH_STATUS would then reflect c2 (finding N5c).
INTERLEAVED = """CREATE OR REPLACE PROCEDURE wtb7_inter IS
  CURSOR c1 IS SELECT id FROM wtb7_parent ORDER BY id;
  CURSOR c2 IS SELECT cid FROM wtb7_child ORDER BY cid;
  v1 NUMBER; v2 NUMBER;
BEGIN
  OPEN c1;
  LOOP
    FETCH c1 INTO v1;
    OPEN c2; FETCH c2 INTO v2; CLOSE c2;
    EXIT WHEN c1%NOTFOUND;
    INSERT INTO wtb7_seen(pid) VALUES (v1);
  END LOOP;
  CLOSE c1;
END;"""

ISOPEN = """CREATE OR REPLACE PROCEDURE wtb7_iso IS
  CURSOR c IS SELECT id FROM wtb7_parent;
  v NUMBER;
BEGIN
  OPEN c;
  FETCH c INTO v;
  IF c%ISOPEN THEN CLOSE c; END IF;
END;"""


def _t(src: str, target: str) -> str:
    return Transpiler().transpile(src, "oracle", target).sql


# --------------------------------------------------------------------------- #
# Structural tests (no database)                                              #
# --------------------------------------------------------------------------- #


class TestNestedLoopMysql:
    def test_labels_are_unique_and_matched(self) -> None:
        out = _t(NESTED, "mysql")
        labels = re.findall(r"(loop_lbl_\d+): LOOP", out)
        assert len(labels) == 2, out
        assert len(set(labels)) == 2, out  # N5a: no duplicate label (error 1309)
        # Each loop is closed with its own label and its EXIT leaves it.
        for lab in labels:
            assert f"END LOOP {lab};" in out, out
            assert f"LEAVE {lab};" in out, out

    def test_per_cursor_done_flag_transfer_and_reset(self) -> None:
        out = _t(NESTED, "mysql")
        # N5b: each cursor gets its own done flag, transferred from the shared
        # handler flag right after its FETCH, and the shared flag is reset.
        assert "DECLARE v_uq_c1_done INT DEFAULT FALSE;" in out, out
        assert "DECLARE v_uq_c2_done INT DEFAULT FALSE;" in out, out
        assert "SET v_uq_c1_done = v_fetch_done; SET v_fetch_done = FALSE;" in out, out
        assert "SET v_uq_c2_done = v_fetch_done; SET v_fetch_done = FALSE;" in out, out
        assert "IF v_uq_c1_done THEN LEAVE" in out, out
        assert "IF v_uq_c2_done THEN LEAVE" in out, out
        # The shared handler still exists (it drives the transfer).
        assert "DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done" in out, out


class TestInterleavedFetchTsql:
    def test_per_cursor_status_captured_adjacent_to_fetch(self) -> None:
        out = _t(INTERLEAVED, "tsql")
        # N5c: the c1 status is captured immediately after FETCH c1 into its
        # own variable, so the intervening FETCH c2 cannot corrupt the check.
        assert "SET @uq_c1_fs = @@FETCH_STATUS;" in out, out
        assert "IF @uq_c1_fs <> 0 BREAK;" in out, out
        assert "DECLARE @uq_c1_fs INT = 0;" in out, out
        # The capture sits right after FETCH c1, before the c2 lifecycle.
        after_fetch = out.split("FETCH NEXT FROM c1 INTO @v1;", 1)[1]
        assert after_fetch.lstrip().startswith("SET @uq_c1_fs = @@FETCH_STATUS;"), out


class TestIsOpen:
    def test_tsql_open_flag(self) -> None:
        out = _t(ISOPEN, "tsql")
        assert "% ISOPEN" not in out and "%ISOPEN" not in out.upper(), out
        assert "DECLARE @uq_c_open BIT = 0;" in out, out
        assert "SET @uq_c_open = 1;" in out, out  # after OPEN
        assert "SET @uq_c_open = 0;" in out, out  # after CLOSE
        assert "IF @uq_c_open = 1" in out, out

    def test_mysql_open_flag(self) -> None:
        out = _t(ISOPEN, "mysql")
        assert "% ISOPEN" not in out and "%ISOPEN" not in out.upper(), out
        assert "DECLARE v_uq_c_open INT DEFAULT 0;" in out, out
        assert "SET v_uq_c_open = 1;" in out, out
        assert "SET v_uq_c_open = 0;" in out, out
        assert "IF v_uq_c_open = 1 THEN" in out, out


class TestUnknownAttributeWarns:
    """A cursor attribute the transformer does not recognize must degrade with
    a warning, never lex through as ``%`` modulo arithmetic (finding N6)."""

    SRC = (
        "CREATE OR REPLACE PROCEDURE wtb7_unk IS\n"
        "  CURSOR c IS SELECT id FROM t;\n"
        "BEGIN\n"
        "  IF c%FOO THEN NULL; END IF;\n"
        "END;"
    )

    @pytest.mark.parametrize("target", ("tsql", "mysql"))
    def test_unknown_attribute_warns_and_does_not_leak_modulo(
        self, target: str
    ) -> None:
        result = Transpiler().transpile(self.SRC, "oracle", target)
        assert any(
            "cursor attribute" in w.message.lower() for w in result.warnings
        ), result.warnings
        assert re.search(
            re.escape("UNIQUE")
            + r"(?:-\d{4})?"
            + re.escape(": unmapped cursor attribute"),
            result.sql,
        ), result.sql
        # Never ship the bare ``c % FOO`` as EXECUTABLE arithmetic — the only
        # surviving occurrence is inside the carrier comment (strip it first,
        # per the comment-prose trap).
        executable = re.sub(r"/\*.*?\*/", "", result.sql, flags=re.S)
        assert not re.search(r"(?i)\bc\s*%\s*FOO\b", executable), result.sql


# --------------------------------------------------------------------------- #
# Live value / row-set tests (skipped without the engine URLs)               #
# --------------------------------------------------------------------------- #

_MYSQL_URL = os.environ.get("UNIQUE_TEST_MYSQL_URL")
_MSSQL_URL = os.environ.get("UNIQUE_TEST_MSSQL_URL")
_ORACLE_URL = os.environ.get("UNIQUE_TEST_ORACLE_URL")


def _mysql_conn(url: str):  # type: ignore[no-untyped-def]
    from urllib.parse import urlparse

    import pymysql

    u = urlparse(url)
    return pymysql.connect(
        host=u.hostname or "127.0.0.1",
        port=u.port or 3306,
        user=u.username or "root",
        password=u.password or "",
        database=(u.path or "/").lstrip("/") or None,
        autocommit=True,
    )


def _mssql_conn(url: str):  # type: ignore[no-untyped-def]
    from urllib.parse import urlparse

    import pymssql

    u = urlparse(url)
    return pymssql.connect(
        server=u.hostname or "127.0.0.1",
        port=str(u.port or 1433),
        user=u.username,
        password=u.password,
        database=(u.path or "/").lstrip("/") or "master",
        autocommit=True,
    )


def _oracle_conn(url: str):  # type: ignore[no-untyped-def]
    from urllib.parse import urlparse

    import oracledb

    u = urlparse(url)
    return oracledb.connect(
        user=u.username, password=u.password, dsn=f"{u.hostname}:{u.port}{u.path}"
    )


@pytest.mark.skipif(_MYSQL_URL is None, reason="UNIQUE_TEST_MYSQL_URL not set")
def test_nested_loop_processes_all_parents_live_mysql() -> None:
    out = _t(NESTED, "mysql")
    body = (
        out.replace("DELIMITER $$", "")
        .replace("DELIMITER ;", "")
        .replace("END$$", "END")
        .strip()
    )
    conn = _mysql_conn(_MYSQL_URL)  # type: ignore[arg-type]
    cur = conn.cursor()
    try:
        for t in ("wtb7_seen", "wtb7_child", "wtb7_parent"):
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute("CREATE TABLE wtb7_parent(id INT)")
        cur.execute("CREATE TABLE wtb7_child(cid INT)")
        cur.execute("CREATE TABLE wtb7_seen(pid INT)")
        cur.executemany("INSERT INTO wtb7_parent VALUES (%s)", [(1,), (2,), (3,)])
        cur.executemany("INSERT INTO wtb7_child VALUES (%s)", [(10,), (11,)])
        cur.execute("DROP PROCEDURE IF EXISTS wtb7_nested")
        cur.execute(body)
        cur.execute("CALL wtb7_nested()")
        cur.execute("SELECT pid FROM wtb7_seen ORDER BY pid")
        assert [r[0] for r in cur.fetchall()] == [1, 2, 3]
    finally:
        for t in ("wtb7_seen", "wtb7_child", "wtb7_parent"):
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute("DROP PROCEDURE IF EXISTS wtb7_nested")
        conn.close()


@pytest.mark.skipif(
    _MSSQL_URL is None or _ORACLE_URL is None,
    reason="UNIQUE_TEST_MSSQL_URL / UNIQUE_TEST_ORACLE_URL not set",
)
def test_interleaved_fetch_matches_oracle_row_count_live() -> None:
    # child is EMPTY: with the old global @@FETCH_STATUS the c1 check would read
    # c2's exhausted status and exit before any parent — the discriminating case.
    oc = _oracle_conn(_ORACLE_URL)  # type: ignore[arg-type]
    ocur = oc.cursor()

    def drop_quiet(stmt: str) -> None:
        with contextlib.suppress(Exception):
            ocur.execute(stmt)

    try:
        for t in ("wtb7_seen", "wtb7_child", "wtb7_parent"):
            drop_quiet(f"DROP TABLE {t}")
        ocur.execute("CREATE TABLE wtb7_parent(id NUMBER)")
        ocur.execute("CREATE TABLE wtb7_child(cid NUMBER)")
        ocur.execute("CREATE TABLE wtb7_seen(pid NUMBER)")
        ocur.executemany("INSERT INTO wtb7_parent VALUES (:1)", [(1,), (2,), (3,)])
        oc.commit()
        ocur.execute(INTERLEAVED.rstrip().rstrip("/"))
        ocur.execute("BEGIN wtb7_inter; END;")
        oc.commit()
        ocur.execute("SELECT COUNT(*) FROM wtb7_seen")
        ora_n = ocur.fetchone()[0]
    finally:
        for t in ("wtb7_seen", "wtb7_child", "wtb7_parent"):
            drop_quiet(f"DROP TABLE {t}")
        drop_quiet("DROP PROCEDURE wtb7_inter")
        oc.commit()
        oc.close()

    ts = _t(INTERLEAVED, "tsql")
    mc = _mssql_conn(_MSSQL_URL)  # type: ignore[arg-type]
    mcur = mc.cursor()
    try:
        for t in ("wtb7_seen", "wtb7_child", "wtb7_parent"):
            mcur.execute(f"IF OBJECT_ID('{t}','U') IS NOT NULL DROP TABLE {t}")
        mcur.execute(
            "IF OBJECT_ID('wtb7_inter','P') IS NOT NULL DROP PROCEDURE wtb7_inter"
        )
        mcur.execute("CREATE TABLE wtb7_parent(id INT)")
        mcur.execute("CREATE TABLE wtb7_child(cid INT)")
        mcur.execute("CREATE TABLE wtb7_seen(pid INT)")
        mcur.executemany("INSERT INTO wtb7_parent VALUES (%d)", [(1,), (2,), (3,)])
        for b in re.split(r"(?im)^\s*GO\s*$", ts):
            if b.strip():
                mcur.execute(b)
        mcur.execute("EXEC wtb7_inter")
        mcur.execute("SELECT COUNT(*) FROM wtb7_seen")
        ts_n = mcur.fetchone()[0]
    finally:
        for t in ("wtb7_seen", "wtb7_child", "wtb7_parent"):
            mcur.execute(f"IF OBJECT_ID('{t}','U') IS NOT NULL DROP TABLE {t}")
        mcur.execute(
            "IF OBJECT_ID('wtb7_inter','P') IS NOT NULL DROP PROCEDURE wtb7_inter"
        )
        mc.close()

    assert ts_n == ora_n == 3
