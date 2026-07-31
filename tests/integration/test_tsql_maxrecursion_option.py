# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""T-SQL's trailing ``OPTION (...)`` query-hint clause (B51).

sqlglot models every hint as a ``options`` arg on the ``Select`` node; before
this fix the converter never read it, so it fell through the generic
unread-args tripwire (``UNIQUE-1228: internal: unread sqlglot arg 'options'``)
instead of a real diagnostic. ``MAXRECURSION`` is the one hint with an actual
semantic effect (a recursion-depth guard: T-SQL errors past ``n``, the other
three engines recurse unbounded), so it gets its own divergence warning
(``UNIQUE-1238``); every other hint (``MAXDOP``, ``RECOMPILE``, ``FORCE
ORDER``, ...) is a pure optimizer directive with no effect on the result set,
so it gets a lighter drop notice (``UNIQUE-1239``). A T-SQL target keeps the
clause verbatim (same dialect, no divergence, no warning needed).
"""

from __future__ import annotations

import sqlglot
import sqlglot.errors

from unique.core.transpiler import Transpiler

_SQLGLOT_DIALECT = {
    "tsql": "tsql",
    "oracle": "oracle",
    "postgresql": "postgres",
    "mysql": "mysql",
}

_RECURSIVE_CTE = (
    "WITH cte AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM cte WHERE n < 10) "
    "SELECT * FROM cte OPTION (MAXRECURSION 500);"
)


def _tx(sql: str, target: str):
    return Transpiler().transpile(sql, source="tsql", target=target)


def _assert_parses(sql: str, target: str) -> None:
    sqlglot.parse(
        sql,
        read=_SQLGLOT_DIALECT[target],
        error_level=sqlglot.errors.ErrorLevel.RAISE,
    )


class TestMaxRecursionDroppedWithSemanticWarning:
    """PG/MySQL/Oracle targets: the hint is dropped with the real
    divergence message, and the generic tripwire (UNIQUE-1228) no longer
    fires for this shape."""

    def test_pg_target(self) -> None:
        self._assert_dropped_and_warned("postgresql")

    def test_mysql_target(self) -> None:
        self._assert_dropped_and_warned("mysql")

    def test_oracle_target(self) -> None:
        self._assert_dropped_and_warned("oracle")

    def _assert_dropped_and_warned(self, target: str) -> None:
        r = _tx(_RECURSIVE_CTE, target)
        assert "MAXRECURSION" not in r.sql.upper(), r.sql
        assert "OPTION" not in r.sql.upper(), r.sql
        codes = [w.code for w in r.warnings]
        assert "UNIQUE-1228" not in codes, r.warnings
        assert codes.count("UNIQUE-1238") == 1, r.warnings
        (w,) = [w for w in r.warnings if w.code == "UNIQUE-1238"]
        assert "MAXRECURSION 500" in w.message, w.message
        assert "100" in w.message, w.message  # the T-SQL implicit default
        assert "PostgreSQL" in w.message and "MySQL" in w.message, w.message
        assert "T-SQL OPTION (...) query hint" in r.unsupported, r.unsupported
        _assert_parses(r.sql, target)


class TestTsqlIdentityKeepsOptionNative:
    """A T-SQL target is the same dialect — the hint is faithful, so it is
    kept verbatim and needs no warning at all."""

    def test_option_survives_identity(self) -> None:
        r = _tx(_RECURSIVE_CTE, "tsql")
        assert "OPTION (MAXRECURSION 500)" in r.sql, r.sql
        assert not r.warnings, r.warnings
        assert not r.unsupported, r.unsupported
        _assert_parses(r.sql, "tsql")


class TestGenericHintDroppedWithLighterWarning:
    """A non-MAXRECURSION hint has no result-correctness effect, so it gets
    the generic UNIQUE-1239 drop notice, not the divergence message."""

    def test_maxdop_and_recompile_dropped(self) -> None:
        sql = "SELECT * FROM t OPTION (MAXDOP 4, RECOMPILE, FORCE ORDER);"
        r = _tx(sql, "postgresql")
        for token in ("MAXDOP", "RECOMPILE", "FORCE ORDER", "OPTION"):
            assert token not in r.sql.upper(), r.sql
        codes = [w.code for w in r.warnings]
        assert "UNIQUE-1228" not in codes, r.warnings
        assert "UNIQUE-1238" not in codes, r.warnings
        assert codes.count("UNIQUE-1239") == 3, r.warnings
        messages = " ".join(w.message for w in r.warnings)
        assert "MAXDOP 4" in messages, messages
        assert "RECOMPILE" in messages, messages
        assert "FORCE ORDER" in messages, messages
        _assert_parses(r.sql, "postgresql")

    def test_maxdop_and_recompile_kept_on_tsql_identity(self) -> None:
        sql = "SELECT * FROM t OPTION (MAXDOP 4, RECOMPILE);"
        r = _tx(sql, "tsql")
        assert "OPTION (MAXDOP 4, RECOMPILE)" in r.sql, r.sql
        assert not r.warnings, r.warnings
        _assert_parses(r.sql, "tsql")


class TestMixedHintsGetDistinctMessages:
    """MAXRECURSION and a plain hint in the same OPTION() clause each get
    their own diagnostic, not a merged/lost one."""

    def test_maxrecursion_and_maxdop_together(self) -> None:
        sql = (
            "WITH cte AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM cte WHERE n < 5) "
            "SELECT n FROM cte OPTION (MAXDOP 2, MAXRECURSION 50);"
        )
        r = _tx(sql, "mysql")
        codes = sorted(w.code for w in r.warnings)
        assert codes == ["UNIQUE-1238", "UNIQUE-1239"], r.warnings
        (maxrec,) = [w for w in r.warnings if w.code == "UNIQUE-1238"]
        (maxdop,) = [w for w in r.warnings if w.code == "UNIQUE-1239"]
        assert "MAXRECURSION 50" in maxrec.message, maxrec.message
        assert "MAXDOP 2" in maxdop.message, maxdop.message
        _assert_parses(r.sql, "mysql")
