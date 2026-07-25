# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""CREATE VIEW modifiers: WITH CHECK OPTION and non-portable attributes.

RED seed (B2 unread-args sweep, 2026-07-24): ``Create.properties`` bundled view
modifiers the CREATE VIEW converter dropped silently. ``WITH CHECK OPTION`` is
portable across all four engines and must survive; non-portable single-engine
modifiers (SCHEMABINDING, ALGORITHM=, DEFINER=, SQL SECURITY, …) must degrade
with a warning — never silently, per the no-silent-loss invariant.
"""

from __future__ import annotations

import sqlglot

from unique.core.converter._base import sqlglot_dialect_name
from unique.core.transpiler import Transpiler


def _parse_ok(sql: str, target: str) -> None:
    body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    sqlglot.parse(
        body,
        read=sqlglot_dialect_name(target),
        error_level=sqlglot.ErrorLevel.RAISE,
    )


class TestCheckOption:
    SRC = "CREATE VIEW v AS SELECT id, val FROM t WHERE val > 0 WITH CHECK OPTION;"

    def _assert_transpiled(self, out: str, target: str) -> str:
        # The view must transpile as real code (not a Command carrier that
        # merely comments the untranslated original).
        code = _code_lines(out).upper()
        assert "UNHANDLED" not in out.upper(), out
        assert "CREATE" in code and "VIEW" in code and "SELECT" in code, out
        _parse_ok(out, target)
        return code

    def test_pg_to_mysql_keeps_check_option(self) -> None:
        out = Transpiler().transpile(self.SRC, "postgresql", "mysql").sql
        assert "WITH CHECK OPTION" in self._assert_transpiled(out, "mysql"), out

    def test_mysql_to_postgresql_keeps_check_option(self) -> None:
        out = Transpiler().transpile(self.SRC, "mysql", "postgresql").sql
        assert "WITH CHECK OPTION" in self._assert_transpiled(out, "postgresql"), out

    def test_pg_to_oracle_keeps_check_option(self) -> None:
        out = Transpiler().transpile(self.SRC, "postgresql", "oracle").sql
        assert "WITH CHECK OPTION" in self._assert_transpiled(out, "oracle"), out

    def test_pg_to_tsql_keeps_check_option(self) -> None:
        out = Transpiler().transpile(self.SRC, "postgresql", "tsql").sql
        assert "WITH CHECK OPTION" in self._assert_transpiled(out, "tsql"), out

    def test_mysql_scoped_check_option_downgraded_for_oracle(self) -> None:
        src = (
            "CREATE VIEW v AS SELECT id FROM t WHERE id > 0 "
            "WITH CASCADED CHECK OPTION;"
        )
        out = Transpiler().transpile(src, "mysql", "oracle").sql
        code = self._assert_transpiled(out, "oracle")
        # Oracle has no LOCAL/CASCADED scope — the plain form remains.
        assert "WITH CHECK OPTION" in code, out
        assert "CASCADED" not in code, out

    def test_mysql_scoped_check_option_kept_for_postgresql(self) -> None:
        src = (
            "CREATE VIEW v AS SELECT id FROM t WHERE id > 0 "
            "WITH CASCADED CHECK OPTION;"
        )
        out = Transpiler().transpile(src, "mysql", "postgresql").sql
        code = self._assert_transpiled(out, "postgresql")
        # PostgreSQL supports the scoped form.
        assert "CASCADED CHECK OPTION" in code, out


class TestNonPortableModifiersWarn:
    def test_schemabinding_dropped_with_warning(self) -> None:
        src = "CREATE VIEW v WITH SCHEMABINDING AS SELECT id, val FROM t;"
        for target in ("postgresql", "oracle", "mysql"):
            res = Transpiler().transpile(src, "tsql", target)
            out = res.sql
            # The portable view still emits...
            assert "CREATE" in out.upper() and "VIEW" in out.upper(), out
            # ...but SCHEMABINDING is gone and a warning fired.
            assert "SCHEMABINDING" not in _code_lines(out).upper(), out
            assert res.warnings, f"{target}: expected a warning, got none"
            assert any("schemabinding" in w.message.lower() for w in res.warnings), [
                w.message for w in res.warnings
            ]
            _parse_ok(out, target)

    def test_mysql_algorithm_modifier_dropped_with_warning(self) -> None:
        src = "CREATE ALGORITHM=MERGE VIEW v AS SELECT id FROM t;"
        res = Transpiler().transpile(src, "mysql", "postgresql")
        out = res.sql
        assert "CREATE" in out.upper() and "VIEW" in out.upper(), out
        assert "ALGORITHM" not in _code_lines(out).upper(), out
        assert res.warnings, "expected a warning for ALGORITHM= drop"
        _parse_ok(out, "postgresql")


class TestSameEngineModifiersKept:
    def test_tsql_schemabinding_survives_tsql_target(self) -> None:
        src = "CREATE VIEW v WITH SCHEMABINDING AS SELECT id, val FROM t;"
        res = Transpiler().transpile(src, "tsql", "tsql")
        code = _code_lines(res.sql).upper()
        assert "WITH SCHEMABINDING" in code, res.sql
        assert not res.warnings, [w.message for w in res.warnings]
        _parse_ok(res.sql, "tsql")

    def test_mysql_algorithm_survives_mysql_target(self) -> None:
        src = "CREATE ALGORITHM=MERGE VIEW v AS SELECT id FROM t;"
        res = Transpiler().transpile(src, "mysql", "mysql")
        code = _code_lines(res.sql).upper()
        assert "ALGORITHM=MERGE" in code, res.sql
        assert not res.warnings, [w.message for w in res.warnings]
        _parse_ok(res.sql, "mysql")


def _code_lines(sql: str) -> str:
    """Return only the non-comment lines (carriers legitimately name the drop)."""
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
