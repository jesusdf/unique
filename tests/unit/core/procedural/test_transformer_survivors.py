# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Targeted assertions for procedural-transformer mutation survivors:
each pins a trigger/function transform decision the survivor map showed
un-asserted."""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str):
    return Transpiler().transpile(sql, source=source, target=target)


class TestTriggerTransformDecisions:
    def test_tsql_for_timing_becomes_after(self) -> None:
        r = _t(
            "CREATE TRIGGER trg1 ON t1 FOR INSERT AS BEGIN "
            "UPDATE t2 SET n = n + 1 WHERE id IN (SELECT id FROM inserted) "
            "END",
            "tsql",
            "postgresql",
        )
        assert re.search(r"(?i)AFTER INSERT", r.sql), r.sql
        assert not re.search(r"(?im)^\s*FOR INSERT", r.sql), r.sql

    def test_delegating_trigger_warns_off_pg(self) -> None:
        src = (
            "create trigger tg after update on r1 for each row "
            "execute function tg_fn();"
        )
        r = _t(src, "postgresql", "mysql")
        joined = " ".join(w.message for w in r.warnings)
        assert "delegates to trigger function" in joined, r.warnings

    def test_delegating_trigger_no_false_warning_on_pg(self) -> None:
        src = (
            "create trigger tg after update on r1 for each row "
            "execute function tg_fn();"
        )
        r = _t(src, "postgresql", "postgresql")
        joined = " ".join(w.message for w in r.warnings)
        assert "delegates to trigger function" not in joined, r.warnings

    def test_non_trigger_function_not_inlined_comment(self) -> None:
        r = _t(
            "create function nf2(a int) returns int as $$\n"
            "begin\n  return a;\nend$$ language plpgsql;",
            "postgresql",
            "tsql",
        )
        assert "inlined into its" not in r.sql, r.sql
        assert re.search(r"(?i)CREATE FUNCTION nf2", r.sql), r.sql

    def test_update_of_becomes_if_update_on_tsql(self) -> None:
        r = _t(
            "create trigger tu before update of c1 on t3 for each row "
            "begin :new.c2 := 1; end;\n/",
            "oracle",
            "tsql",
        )
        assert re.search(r"(?i)IF UPDATE\(c1\)", r.sql), r.sql
        assert "UPDATE OF" not in r.sql.upper(), r.sql
