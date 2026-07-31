# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""B37b — spelling-general implicit-``ROW_COUNT`` hoist for the PostgreSQL target.

B37 hoisted a ``GET DIAGNOSTICS uq_rowcount = ROW_COUNT;`` ahead of an Oracle
``SQL%ROWCOUNT`` used in expression position → PostgreSQL. PostgreSQL has no
inline row-count expression, so the *other* two source spellings must go
through the SAME hoist:

* MySQL's ``ROW_COUNT()`` (a function) — previously left untranslated, so the
  whole routine degraded with UNIQUE-1151 at the pg validity gate; and
* T-SQL's ``@@ROWCOUNT`` (a global) — previously mapped to a bare ``ROW_COUNT``
  identifier, which is not valid standalone PL/pgSQL (a latent silent-invalid).

Both now converge on the ``ROW_COUNT()`` spelling that the B37 recognizer
consumes, so a single hoist mechanism serves all three source dialects.
"""

from __future__ import annotations

import re

import sqlglot

from unique.core.transpiler import Transpiler


def _t(src: str, source: str, target: str = "postgresql") -> object:
    return Transpiler().transpile(src, source, target)


def _flat(sql: str) -> str:
    return " ".join(sql.split())


def _parse_pg(out: str) -> None:
    sqlglot.parse(out, read="postgres", error_level=sqlglot.ErrorLevel.RAISE)


_MYSQL_IF = (
    "CREATE PROCEDURE p()\n"
    "BEGIN\n"
    "    UPDATE t SET x = 1 WHERE id = 5;\n"
    "    IF ROW_COUNT() = 0 THEN\n"
    "        UPDATE t SET x = 2 WHERE id = 6;\n"
    "    END IF;\n"
    "END"
)

_MYSQL_ASSIGN = (
    "CREATE PROCEDURE p()\n"
    "BEGIN\n"
    "    DECLARE v INT;\n"
    "    UPDATE t SET x = 1 WHERE id = 5;\n"
    "    SET v = ROW_COUNT();\n"
    "END"
)

_TSQL_IF = (
    "CREATE PROCEDURE p AS\n"
    "BEGIN\n"
    "    UPDATE t SET x = 1 WHERE id = 5;\n"
    "    IF @@ROWCOUNT <> 1\n"
    "        UPDATE t SET x = 2 WHERE id = 6;\n"
    "END"
)


class TestMysqlRowCountExpression:
    def test_if_condition_hoisted(self) -> None:
        out = _t(_MYSQL_IF, "mysql").sql
        flat = _flat(out)
        # Target idiom appeared, source spelling gone.
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in flat, out
        assert "IF uq_rowcount = 0 THEN" in flat, out
        assert "ROW_COUNT()" not in out, out
        _parse_pg(out)

    def test_no_untranslated_builtin_degrade(self) -> None:
        result = _t(_MYSQL_IF, "mysql")
        codes = [w.code for w in result.warnings]
        # The whole routine no longer degrades to the untranslated-builtin
        # carrier, and the routine text itself carries no UNIQUE-1151.
        assert "UNIQUE-1151" not in codes, codes
        assert "UNIQUE-1151" not in result.sql, result.sql

    def test_capture_point_between_dml_and_use(self) -> None:
        out = _flat(_t(_MYSQL_IF, "mysql").sql)
        upd = out.index("UPDATE t SET x = 1")
        cap = out.index("GET DIAGNOSTICS uq_rowcount")
        use = out.index("IF uq_rowcount = 0")
        assert upd < cap < use, out

    def test_standalone_assignment_hoisted(self) -> None:
        out = _t(_MYSQL_ASSIGN, "mysql").sql
        flat = _flat(out)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in flat, out
        assert "v := uq_rowcount;" in flat, out
        assert "ROW_COUNT()" not in out, out
        _parse_pg(out)

    def test_temp_local_declared_once(self) -> None:
        out = _t(_MYSQL_IF, "mysql").sql
        assert len(re.findall(r"(?i)\buq_rowcount\s+bigint\b", out)) == 1, out


class TestTsqlRowCountExpression:
    def test_if_condition_hoisted(self) -> None:
        out = _t(_TSQL_IF, "tsql").sql
        flat = _flat(out)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in flat, out
        assert "IF uq_rowcount <> 1 THEN" in flat, out
        # The T-SQL global is gone and no bare/invalid ROW_COUNT remains
        # (the only surviving ROW_COUNT is the GET DIAGNOSTICS diagnostic item).
        assert "@@ROWCOUNT" not in out.upper(), out
        residue = flat.replace("GET DIAGNOSTICS uq_rowcount = ROW_COUNT;", "")
        assert not re.search(r"(?i)\bROW_COUNT\b", residue), out
        _parse_pg(out)

    def test_no_silent_invalid_bare_identifier(self) -> None:
        # The pre-B37b behavior substituted a bare ``ROW_COUNT`` identifier,
        # invalid in standalone PL/pgSQL — it must be hoisted instead.
        out = _t(_TSQL_IF, "tsql").sql
        assert "IF ROW_COUNT <> 1" not in _flat(out), out

    def test_alter_procedure_hoisted(self) -> None:
        # T-SQL's idempotent ``… ALTER PROCEDURE`` stub pattern lands the body
        # on an ALTER node; the hoist must cover it too (the real fixtures use
        # exactly this shape).
        src = (
            "ALTER PROCEDURE dbo.p\n"
            "    @a INT = NULL\n"
            "AS\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = @a;\n"
            "    IF @@ROWCOUNT <> 1\n"
            "    BEGIN\n"
            "        RAISERROR (16947, 16, 1)\n"
            "    END\n"
            "END\n"
            "GO"
        )
        out = _t(src, "tsql").sql
        flat = _flat(out)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in flat, out
        assert "IF uq_rowcount <> 1 THEN" in flat, out
        assert "@@ROWCOUNT" not in out.upper(), out
        residue = flat.replace("GET DIAGNOSTICS uq_rowcount = ROW_COUNT;", "")
        assert not re.search(r"(?i)\bROW_COUNT\b", residue), out
        _parse_pg(out)


class TestLoopConditionUnchanged:
    """A T-SQL ``@@ROWCOUNT`` in a re-evaluated WHILE condition must not be
    frozen into a single capture — the honest behavior (no hoist) is kept."""

    _WHILE = (
        "CREATE PROCEDURE p AS\n"
        "BEGIN\n"
        "    WHILE @@ROWCOUNT > 0\n"
        "        DELETE TOP (100) FROM t;\n"
        "END"
    )

    def test_while_condition_not_hoisted(self) -> None:
        out = _t(self._WHILE, "tsql").sql
        assert "GET DIAGNOSTICS uq_rowcount" not in out, out


class TestOtherTargetsUnchanged:
    def test_tsql_rowcount_to_mysql_inline(self) -> None:
        out = _flat(_t(_TSQL_IF, "tsql", "mysql").sql)
        assert "ROW_COUNT()" in out, out
        assert "GET DIAGNOSTICS" not in out, out


class TestMysqlChangedRowsDivergence:
    """MySQL's ``ROW_COUNT()`` counts rows CHANGED; PostgreSQL's
    ``GET DIAGNOSTICS ROW_COUNT`` counts rows MATCHED (base.py N11/B12). When
    the hoist consumes a MySQL-source reference the divergence must be warned —
    not shipped silently. Oracle ``SQL%ROWCOUNT`` and T-SQL ``@@ROWCOUNT`` both
    count matched rows, so those sources do NOT warn.
    """

    _DIVERGENCE = "ROW_COUNT() counts rows CHANGED"

    def test_mysql_hoist_warns_divergence(self) -> None:
        r = _t(_MYSQL_IF, "mysql")
        assert any(self._DIVERGENCE in w.message for w in r.warnings), r.warnings

    def test_mysql_assignment_hoist_warns_divergence(self) -> None:
        r = _t(_MYSQL_ASSIGN, "mysql")
        assert any(self._DIVERGENCE in w.message for w in r.warnings), r.warnings

    def test_warning_does_not_alter_sql_output(self) -> None:
        # The divergence is a warning only — no carrier lands in the SQL, the
        # hoist output is unchanged (still a clean GET DIAGNOSTICS capture).
        out = _t(_MYSQL_IF, "mysql").sql
        assert "UNIQUE-1192" not in out, out
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in _flat(out), out

    def test_warning_deduplicated(self) -> None:
        # Two MySQL rowcount checks in one routine warn once (guardrail 5).
        src = (
            "CREATE PROCEDURE p()\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = 5;\n"
            "    IF ROW_COUNT() = 0 THEN\n"
            "        UPDATE t SET x = 2 WHERE id = 6;\n"
            "    END IF;\n"
            "    DELETE FROM t WHERE id = 7;\n"
            "    IF ROW_COUNT() = 0 THEN\n"
            "        UPDATE t SET x = 3 WHERE id = 8;\n"
            "    END IF;\n"
            "END"
        )
        r = _t(src, "mysql")
        matches = [w for w in r.warnings if self._DIVERGENCE in w.message]
        assert len(matches) == 1, r.warnings

    def test_tsql_hoist_no_divergence_warning(self) -> None:
        r = _t(_TSQL_IF, "tsql")
        assert "GET DIAGNOSTICS uq_rowcount" in r.sql, r.sql
        assert not any(self._DIVERGENCE in w.message for w in r.warnings), r.warnings

    def test_oracle_hoist_no_divergence_warning(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = 5;\n"
            "    IF SQL%ROWCOUNT <> 1 THEN\n"
            "        RAISE_APPLICATION_ERROR(-20001, 42);\n"
            "    END IF;\n"
            "END;\n/"
        )
        r = Transpiler().transpile(src, "oracle", "postgresql")
        assert "GET DIAGNOSTICS uq_rowcount" in r.sql, r.sql
        assert not any(self._DIVERGENCE in w.message for w in r.warnings), r.warnings


class TestRoundTripPgDiagnosticsToMysql:
    """The pg ``GET DIAGNOSTICS x = ROW_COUNT`` form must still translate back
    out to MySQL's ``ROW_COUNT()`` — the reverse direction of the hoist."""

    _PG = (
        "CREATE PROCEDURE p()\n"
        "LANGUAGE plpgsql\n"
        "AS $$\n"
        "DECLARE\n"
        "    n bigint;\n"
        "BEGIN\n"
        "    UPDATE t SET x = 1 WHERE id = 5;\n"
        "    GET DIAGNOSTICS n = ROW_COUNT;\n"
        "    IF n = 0 THEN\n"
        "        UPDATE t SET x = 2 WHERE id = 6;\n"
        "    END IF;\n"
        "END;\n"
        "$$;"
    )

    def test_pg_diagnostics_to_mysql(self) -> None:
        out = _flat(_t(self._PG, "postgresql", "mysql").sql)
        assert "ROW_COUNT()" in out, out
        assert "GET DIAGNOSTICS" not in out, out


def _parse_dialect(out: str, dialect: str) -> None:
    sqlglot.parse(out, read=dialect, error_level=sqlglot.ErrorLevel.RAISE)


class TestMysqlRowCountToTsqlOracleInline:
    """B43: mysql ROW_COUNT() inside an IF condition (or a plain assignment)
    reaching T-SQL/Oracle used to degrade the WHOLE routine with a warned
    UNIQUE-1151 (untranslated builtin): the shell-context substitution
    (``_ROWCOUNT_FN_EXPR``) only ran on the raw-text fallback path, which
    the IR-first scalar pipeline pre-empted by "successfully" (mis)parsing
    ``ROW_COUNT()`` as a plain unmapped function call. Unlike PostgreSQL
    (B37b, above), T-SQL and Oracle read the last statement's row count as
    an inline expression (``@@ROWCOUNT`` / ``SQL%ROWCOUNT``) — no hoist
    needed, just a name substitution before the IR gets a chance to
    mishandle it.
    """

    def test_if_condition_translates_to_tsql(self) -> None:
        out = _t(_MYSQL_IF, "mysql", "tsql").sql
        assert "IF @@ROWCOUNT = 0" in _flat(out), out
        assert "ROW_COUNT()" not in out, out
        _parse_dialect(out, "tsql")

    def test_if_condition_translates_to_oracle(self) -> None:
        # sqlglot's oracle dialect does not parse a full CREATE PROCEDURE ...
        # BEGIN ... END PL/SQL body (unrelated to this fix — no other test
        # in this file sqlglot-parses an oracle-TARGET routine either); the
        # live compile check below is the real validity gate for Oracle.
        out = _t(_MYSQL_IF, "mysql", "oracle").sql
        assert "IF SQL%ROWCOUNT = 0 THEN" in _flat(out), out
        assert "ROW_COUNT()" not in out, out

    def test_no_untranslated_builtin_degrade_tsql(self) -> None:
        result = _t(_MYSQL_IF, "mysql", "tsql")
        codes = [w.code for w in result.warnings]
        assert "UNIQUE-1151" not in codes, codes
        assert "UNIQUE-1151" not in result.sql, result.sql

    def test_no_untranslated_builtin_degrade_oracle(self) -> None:
        result = _t(_MYSQL_IF, "mysql", "oracle")
        codes = [w.code for w in result.warnings]
        assert "UNIQUE-1151" not in codes, codes
        assert "UNIQUE-1151" not in result.sql, result.sql

    def test_assignment_neighbor_translates_to_tsql(self) -> None:
        # Neighbor test (circuit breaker 2): the same construct in a plain
        # assignment, not just an IF condition.
        out = _t(_MYSQL_ASSIGN, "mysql", "tsql").sql
        assert "SET @v = @@ROWCOUNT;" in _flat(out), out
        assert "ROW_COUNT()" not in out, out
        _parse_dialect(out, "tsql")

    def test_assignment_neighbor_translates_to_oracle(self) -> None:
        out = _t(_MYSQL_ASSIGN, "mysql", "oracle").sql
        assert "v := SQL%ROWCOUNT;" in _flat(out), out
        assert "ROW_COUNT()" not in out, out

    def test_divergence_warning_fires_for_tsql(self) -> None:
        r = _t(_MYSQL_IF, "mysql", "tsql")
        assert any(
            "ROW_COUNT() counts rows CHANGED" in w.message for w in r.warnings
        ), r.warnings

    def test_divergence_warning_fires_for_oracle(self) -> None:
        r = _t(_MYSQL_IF, "mysql", "oracle")
        assert any(
            "ROW_COUNT() counts rows CHANGED" in w.message for w in r.warnings
        ), r.warnings
