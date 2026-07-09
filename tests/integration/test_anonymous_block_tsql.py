# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Oracle top-level anonymous blocks flatten to a plain T-SQL batch (audit D2).

T-SQL has no ``DECLARE … BEGIN … END;`` shell — a batch *is* the block. The
emitter used to keep the PL/SQL skeleton (a bare ``DECLARE`` header line and
an unterminated ``BEGIN``/``END`` pair), ~500 invalid statements on the real
dump's T-SQL direction.
"""

from __future__ import annotations

import re

import sqlglot

from unique.core.transpiler import Transpiler

_SRC = """\
DECLARE
  v_cnt NUMBER := 0;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM t;
  IF v_cnt = 0 THEN
    INSERT INTO t (id) VALUES (1);
  END IF;
END;
/"""


def test_anonymous_block_flattens_to_tsql_batch() -> None:
    out = Transpiler().transpile(_SRC, "oracle", "tsql").sql
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # No bare PL/SQL DECLARE header line (T-SQL DECLARE always names a @var).
    assert not any(re.fullmatch(r"(?i)DECLARE", ln) for ln in lines), out
    # The declaration itself survives, flattened.
    assert any(re.match(r"(?i)DECLARE\s+@\w+", ln) for ln in lines), out
    # Body statements survive.
    assert any("SELECT @" in ln for ln in lines), out
    assert any("INSERT INTO t" in ln for ln in lines), out
    # And the whole batch parses as T-SQL.
    sqlglot.parse(out, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)


def test_block_without_declarations_flattens_too() -> None:
    src = "BEGIN\n  INSERT INTO t (id) VALUES (1);\nEND;\n/"
    out = Transpiler().transpile(src, "oracle", "tsql").sql
    assert "INSERT INTO t" in out
    sqlglot.parse(out, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)


_MULTI_DECL = """\
DECLARE
v_stamp DATE;
v_webid NUMBER(9,0);
BEGIN
v_stamp := SYSDATE ;
select COUNT(c1) into V_WEBID from t1 where c2 = 'x';
if (v_webid=0) then
INSERT INTO t1(c2, c3) SELECT 'x', v_stamp FROM DUAL;
end if;
END;
/"""


def test_declare_section_with_multiple_declarations() -> None:
    # PL/SQL DECLARE opens a SECTION (every declaration until BEGIN); the
    # parser used to take only the first one, leaking 'v_webid NUMBER(9,0)'
    # as raw text and leaving later references unrenamed (audit D9 shape B,
    # ~39 statements on the real dump).
    out = Transpiler().transpile(_MULTI_DECL, "oracle", "tsql").sql
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    decls = [ln for ln in lines if re.match(r"(?i)DECLARE\s+@", ln)]
    assert len(decls) == 2, out
    # Every reference renamed — no bare v_webid survives outside comments.
    executable = " ".join(ln for ln in lines if not ln.startswith("--"))
    assert "v_webid" not in executable.lower().replace("@webid", ""), out
    assert "@webid" in executable or "@v_webid" in executable, out
    sqlglot.parse(out, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)
