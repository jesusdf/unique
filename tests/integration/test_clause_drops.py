# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""RC-3 — clause drops (data-integrity constraints must not vanish silently).

Inline column-level constraints (``c INT REFERENCES p(id) ON DELETE CASCADE``,
``c INT CHECK (c > 0)``) used to be dropped by the CREATE TABLE converter — it
read only NOT NULL / IDENTITY / PRIMARY KEY / UNIQUE / DEFAULT. They are
equivalent to a table-level constraint and are now routed there, so the
referential-integrity / validation rule survives on every target.
"""

from __future__ import annotations

import sqlglot

from unique.core.transpiler import Transpiler

_SG = {"mysql": "mysql", "tsql": "tsql", "oracle": "oracle", "postgresql": "postgres"}


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source, target).sql


def _parses(sql: str, target: str) -> bool:
    try:
        sqlglot.parse(sql, read=_SG[target], error_level=sqlglot.ErrorLevel.RAISE)
        return True
    except Exception:
        return False


def test_inline_fk_with_on_delete_survives_to_every_target() -> None:
    src = "CREATE TABLE t (a INT, b INT REFERENCES p(id) ON DELETE CASCADE)"
    for tgt in ("mysql", "tsql", "oracle"):
        out = _t(src, "postgresql", tgt)
        assert "REFERENCES" in out.upper(), (tgt, out)  # FK not dropped
        assert "ON DELETE CASCADE" in out.upper(), (tgt, out)  # action kept
        assert _parses(out, tgt), (tgt, out)


def test_inline_check_survives() -> None:
    for src_dialect in ("postgresql", "mysql"):
        out = _t("CREATE TABLE t (a INT CHECK (a > 0))", src_dialect, "tsql")
        assert "CHECK (a > 0)" in out, (src_dialect, out)
        assert _parses(out, "tsql"), (src_dialect, out)


def test_inline_fk_without_action_survives() -> None:
    out = _t("CREATE TABLE t (b INT REFERENCES p(id))", "mysql", "postgresql")
    assert "REFERENCES" in out.upper(), out
    assert _parses(out, "postgresql"), out
