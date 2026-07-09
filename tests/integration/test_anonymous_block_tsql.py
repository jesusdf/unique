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
