# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Faithful T-SQL expansion of PL/SQL cursor FOR loops (P1, ~350 statements
on the real dump once D9 let these routines parse whole).

The previous scaffold was invalid by construction: it re-declared a cursor
FOR <cursor-name> (T-SQL FOR needs a SELECT), fetched INTO a comment
placeholder, and left ``rec.col`` record references unrewritten. When the
cursor's select list is resolvable, the loop now expands to a complete,
valid cursor pattern; the documented scaffold remains only for unresolvable
lists (e.g. ``SELECT *``).
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler

_NAMED = """\
DECLARE
  v_total NUMBER := 0;
  CURSOR cur1 IS SELECT id, amount, name FROM src_t WHERE flag = 1;
BEGIN
  FOR rec IN cur1 LOOP
    IF rec.amount > 0 THEN
      INSERT INTO dst_t (id, label) VALUES (rec.id, rec.name || '!');
    END IF;
    v_total := v_total + rec.amount;
  END LOOP;
END;
/"""


def _tsql(src: str):
    return Transpiler().transpile(src, source="oracle", target="tsql")


def test_named_cursor_loop_expands_completely() -> None:
    out = _tsql(_NAMED).sql
    up = " ".join(out.split())
    # The declared cursor keeps its (classic, un-@) declaration…
    assert re.search(r"(?i)DECLARE\s+cur1\s+CURSOR\b[^;]*FOR\s+SELECT", up), out
    # …and the loop drives THAT cursor — no second cursor over its name.
    assert "OPEN cur1" in up
    assert not re.search(r"(?i)CURSOR[^;]*FOR\s+cur1\b", up), out
    # Loop variables are declared and fetched positionally.
    assert re.search(
        r"(?i)FETCH NEXT FROM cur1 INTO @rec_id\s*,\s*@rec_amount\s*,\s*@rec_name",
        up,
    ), out
    assert "/* @col1" not in out
    # Record references are rewritten.
    assert re.search(r"(?i)IF\s+\(?\s*@rec_amount\s*>\s*0", up), out
    assert "@rec_id" in up and "@rec_name + '!'" in up
    assert not re.search(r"(?i)\brec\s*\.\s*\w", up), out
    assert "CLOSE cur1" in up and "DEALLOCATE cur1" in up


def test_inline_query_loop_expands_completely() -> None:
    src = (
        "BEGIN\n"
        "  FOR r IN (SELECT a, b FROM t WHERE k = 1) LOOP\n"
        "    UPDATE d SET x = r.a WHERE y = r.b;\n"
        "  END LOOP;\n"
        "END;\n/"
    )
    out = _tsql(src).sql
    up = " ".join(out.split())
    assert re.search(r"(?i)DECLARE\s+r_cur\s+CURSOR\b", up), out
    assert re.search(r"(?i)FETCH NEXT FROM r_cur INTO @r_a\s*,\s*@r_b", up), out
    assert "/* @col1" not in out
    assert re.search(r"(?i)SET\s+x\s*=\s*@r_a", up), out
    assert not re.search(r"(?i)\br\s*\.\s*\w", up), out


def test_unresolvable_select_star_keeps_documented_scaffold() -> None:
    src = (
        "BEGIN\n"
        "  FOR r IN (SELECT * FROM t) LOOP\n"
        "    UPDATE d SET x = r.a;\n"
        "  END LOOP;\n"
        "END;\n/"
    )
    r = _tsql(src)
    # The documented degradation (developer completes the FETCH) survives,
    # and it is warned — never silent.
    assert "UNIQUE" in r.sql
    assert r.warnings
