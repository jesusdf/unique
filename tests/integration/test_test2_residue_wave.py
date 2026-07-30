# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""The 2026-07-10 sweep-closing wave (private test2/test corpora at 100%).

Each test pins one defect class found by live-executing the transpiled
corpora: semicolon-less T-SQL boundaries (ELSE / statement verbs / cursor
ops / MERGE actions / CTE main statements), the cursor-loop idiom
(@@FETCH_STATUS), MERGE per-target fixes, the base64-XML idiom, table
variables inside blocks, and CATCH-block content (ERROR_MESSAGE / RAISERROR
with a variable message).
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(src: str, target: str) -> str:
    return Transpiler().transpile(src, "tsql", target).sql


def _one_line(sql: str) -> str:
    return " ".join(sql.split())


def _executable_text(sql: str) -> str:
    """The output with full-line comments removed (a documentation carrier
    may legitimately mention the source construct's name)."""
    return " ".join(
        line.split(" -- UNIQUE-")[0]
        for line in sql.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    )


class TestSemicolonlessBoundaries:
    def test_if_else_assignment_select(self) -> None:
        # The assignment-select's tail used to swallow the bare ELSE.
        src = (
            "CREATE PROCEDURE dbo.p_a @nd VARCHAR(20), @no INT OUTPUT AS\n"
            "BEGIN\n"
            "    IF @nd IS NULL\n"
            "        SELECT @no = ord FROM dbo.t_h WHERE nd = 'x'\n"
            "    ELSE\n"
            "        SELECT @no = ord FROM dbo.t_h WHERE nd = @nd\n"
            "END\nGO"
        )
        out = _one_line(_t(src, "postgresql"))
        assert re.search(r"(?i)IF v_nd IS NULL THEN", out), out
        assert re.search(r"(?i)ELSE\s+SELECT ord INTO v_no", out), out
        assert "v_nd ELSE" not in out, out

    def test_case_else_not_treated_as_boundary(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_b @no INT OUTPUT AS\n"
            "BEGIN\n"
            "    SELECT @no = CASE WHEN a > 0 THEN a ELSE 0 END FROM dbo.t_h\n"
            "END\nGO"
        )
        out = _one_line(_t(src, "postgresql"))
        assert re.search(r"(?i)CASE WHEN a > 0 THEN a ELSE 0 END INTO v_no", out), out

    def test_if_condition_stops_at_rollback(self) -> None:
        # IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION swallowed the ROLLBACK
        # (and every following statement) into the condition.
        src = (
            "CREATE PROCEDURE dbo.p_t AS\nBEGIN\n"
            "    BEGIN TRY\n        UPDATE t_z SET x = 1\n    END TRY\n"
            "    BEGIN CATCH\n"
            "        IF @@TRANCOUNT > 0\n            ROLLBACK TRANSACTION\n"
            "        DECLARE @msg NVARCHAR(2048) = ERROR_MESSAGE()\n"
            "        RAISERROR(@msg, 16, 1)\n"
            "    END CATCH\nEND\nGO"
        )
        for target in ("postgresql", "oracle", "mysql"):
            raw = _t(src, target)
            out = _one_line(raw)
            if target == "postgresql":
                # The parse boundary still holds (the IF body got exactly the
                # ROLLBACK), but on PG the exception-guarded block is a
                # subtransaction where ROLLBACK is a runtime error — it is
                # dropped to a documented carrier inside the IF (2026-07-30).
                assert re.search(
                    r"(?i)THEN\s+/\* UNIQUE-1206: ROLLBACK dropped", out
                ), (
                    target,
                    out,
                )
            else:
                assert re.search(r"(?i)THEN\s+ROLLBACK;", out), (target, out)
            assert "RAISERROR" not in _executable_text(raw).upper(), (target, raw)

    def test_merge_when_then_update_stays_inside(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_m @u VARCHAR(10) AS\nBEGIN\n"
            "    MERGE dbo.t_l AS t\n"
            "    USING (SELECT 1 AS ida) AS s\n"
            "    ON t.ida = s.ida\n"
            "    WHEN MATCHED THEN\n"
            "        UPDATE SET um = @u, fm = GETDATE()\n"
            "    WHEN NOT MATCHED THEN\n"
            "        INSERT (ida, um) VALUES (s.ida, @u);\nEND\nGO"
        )
        out = _one_line(_t(src, "postgresql"))
        assert re.search(r"(?i)WHEN MATCHED THEN UPDATE SET", out), out
        assert re.search(r"(?i)WHEN NOT MATCHED THEN INSERT", out), out

    def test_cte_main_select_not_split_off(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_c AS\nBEGIN\n"
            "    ;WITH cte AS\n    (\n        SELECT 1 AS n FROM t_g\n    )\n"
            "    UPDATE t_z SET x = (SELECT MAX(n) FROM cte)\nEND\nGO"
        )
        out = _one_line(_t(src, "postgresql"))
        assert re.search(
            r"(?i)WITH cte AS \(SELECT 1 AS n FROM t_g\)\s+UPDATE", out
        ), out


class TestCursorLoopIdiom:
    _SRC = (
        "CREATE PROCEDURE dbo.p_c AS\nBEGIN\n"
        "    DECLARE @d NVARCHAR(100)\n"
        "    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR\n"
        "        SELECT d FROM t_s WHERE d IS NOT NULL\n"
        "    OPEN cur\n"
        "    FETCH NEXT FROM cur INTO @d\n"
        "    WHILE @@FETCH_STATUS = 0\n"
        "    BEGIN\n"
        "        UPDATE t_z SET x = @d\n"
        "        FETCH NEXT FROM cur INTO @d\n"
        "    END\n"
        "    CLOSE cur\n    DEALLOCATE cur\nEND\nGO"
    )

    def test_cursor_options_consumed(self) -> None:
        # DECLARE c CURSOR LOCAL FAST_FORWARD FOR <q> lost its query (the
        # options blocked the FOR match) and the loop body desynced.
        out = _one_line(_t(self._SRC, "postgresql"))
        assert re.search(r"(?i)v_cur CURSOR FOR SELECT d FROM t_s", out), out
        assert "FAST_FORWARD" not in out.upper(), out

    def test_fetch_status_postgresql_found(self) -> None:
        out = _one_line(_t(self._SRC, "postgresql"))
        assert re.search(r"(?i)WHILE FOUND LOOP", out), out
        assert "@@FETCH_STATUS" not in out, out

    def test_fetch_status_oracle_cursor_found(self) -> None:
        out = _one_line(_t(self._SRC, "oracle"))
        assert re.search(r"(?i)WHILE V_CUR%FOUND LOOP", out), out

    def test_fetch_status_mysql_done_flag_with_handler(self) -> None:
        out = _t(self._SRC, "mysql")
        flat = _one_line(out)
        assert re.search(r"(?i)WHILE NOT v_fetch_done DO", flat), out
        assert "DECLARE v_fetch_done INT DEFAULT FALSE;" in flat, out
        assert (
            "DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fetch_done = TRUE;" in flat
        ), out
        # Declaration order: variables, cursor, then the handler.
        assert flat.index("v_fetch_done INT") < flat.index("CURSOR FOR"), out
        assert flat.index("CURSOR FOR") < flat.index("CONTINUE HANDLER"), out

    def test_fetch_status_failure_form(self) -> None:
        src = self._SRC.replace("@@FETCH_STATUS = 0", "@@FETCH_STATUS <> 0")
        out = _one_line(_t(src, "postgresql"))
        assert re.search(r"(?i)WHILE NOT FOUND LOOP", out), out


class TestMergePerTarget:
    _SRC = (
        "CREATE PROCEDURE dbo.p_m @u VARCHAR(10) AS\nBEGIN\n"
        "    MERGE dbo.t_l AS t\n"
        "    USING (SELECT 1 AS ida, 2 AS idb) AS s\n"
        "    ON t.ida = s.ida AND t.idb = s.idb\n"
        "    WHEN MATCHED THEN\n"
        "        UPDATE SET v = s.idb, um = @u\n"
        "    WHEN NOT MATCHED THEN\n"
        "        INSERT (ida, idb, um) VALUES (s.ida, s.idb, @u);\nEND\nGO"
    )

    def test_oracle_on_condition_parenthesized(self) -> None:
        out = _one_line(_t(self._SRC, "oracle"))
        assert re.search(r"(?i)ON \(t\.ida = s\.ida AND t\.idb = s\.idb\)", out), out

    def test_mysql_upsert_without_target_alias(self) -> None:
        raw = _t(self._SRC, "mysql")
        out = _one_line(raw)
        assert "MERGE" not in _executable_text(raw).upper(), raw
        assert re.search(r"(?i)INSERT INTO t_l \(ida, idb, um\)", out), out
        assert "ON DUPLICATE KEY UPDATE" in out, out
        assert not re.search(r"(?i)INSERT INTO \w+ AS ", out), out

    def test_mysql_non_canonical_merge_becomes_carrier(self) -> None:
        # An UPDATE assignment that is not an inserted column and not a
        # literal has no ON DUPLICATE KEY form: a documented carrier plus a
        # no-op (never an invalid MERGE INTO), and a warning.
        src = (
            "CREATE PROCEDURE dbo.p_n AS\nBEGIN\n"
            "    MERGE dbo.t_l AS t\n"
            "    USING (SELECT 1 AS ida) AS s\n"
            "    ON t.ida = s.ida\n"
            "    WHEN MATCHED THEN\n        UPDATE SET um = othercol\n"
            "    WHEN NOT MATCHED THEN\n        INSERT (ida) VALUES (s.ida);\n"
            "END\nGO"
        )
        result = Transpiler().transpile(src, "tsql", "mysql")
        body = [
            line
            for line in result.sql.splitlines()
            if line.strip() and not line.lstrip().startswith("--")
        ]
        assert not any("MERGE" in line.upper() for line in body), result.sql
        assert any("DO 0;" in line for line in body), result.sql
        assert any("no MERGE" in w.message for w in result.warnings), result.warnings


class TestScalarIdioms:
    def test_base64_xml_idiom_per_target(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_i @picture NVARCHAR(MAX) AS\nBEGIN\n"
            "    DECLARE @img VARBINARY(MAX) =\n"
            "        CAST(N'' AS XML).value("
            "'xs:base64Binary(sql:variable(\"@picture\"))', 'VARBINARY(MAX)')\n"
            "    UPDATE t_hi SET imagen = @img WHERE n = 1\nEND\nGO"
        )
        for target, expected in (
            ("postgresql", "DECODE(v_picture, 'base64')"),
            ("mysql", "FROM_BASE64(v_picture)"),
            ("oracle", "UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW(V_PICTURE))"),
        ):
            out = _one_line(_t(src, target))
            assert expected in out, (target, out)
            assert "base64Binary" not in out, (target, out)

    def test_error_message_maps_per_target(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_e AS\nBEGIN\n"
            "    BEGIN TRY\n        UPDATE t_z SET x = 1\n    END TRY\n"
            "    BEGIN CATCH\n"
            "        DECLARE @msg NVARCHAR(2048) = ERROR_MESSAGE()\n"
            "        RAISERROR(@msg, 16, 1)\n"
            "    END CATCH\nEND\nGO"
        )
        pg = _one_line(_t(src, "postgresql"))
        assert "v_msg := SQLERRM;" in pg, pg
        assert re.search(r"(?i)RAISE EXCEPTION '%', v_msg", pg), pg
        ora = _one_line(_t(src, "oracle"))
        assert "V_MSG := SQLERRM;" in ora, ora
        assert "RAISE_APPLICATION_ERROR(-20001, V_MSG)" in ora, ora
        my = _one_line(_t(src, "mysql"))
        assert "GET DIAGNOSTICS CONDITION 1 v_msg = MESSAGE_TEXT;" in my, my
        assert re.search(r"(?i)SET MESSAGE_TEXT = v_msg", my), my

    def test_varbinary_max_declarations(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_v AS\nBEGIN\n"
            "    DECLARE @b VARBINARY(MAX)\n    SET @b = NULL\nEND\nGO"
        )
        assert re.search(r"(?i)v_b BYTEA;", _t(src, "postgresql"))
        assert re.search(r"(?i)V_B BLOB;", _t(src, "oracle"))
        assert re.search(r"(?i)DECLARE v_b LONGBLOB;", _t(src, "mysql"))


class TestTableVariableInBlock:
    _SRC = (
        "CREATE PROCEDURE dbo.p_v @a NVARCHAR(100) AS\nBEGIN\n"
        "    IF @a IS NOT NULL\n    BEGIN\n"
        "        DECLARE @trad TABLE (campo VARCHAR(20) NOT NULL)\n"
        "        INSERT INTO @trad (campo) VALUES ('nombre')\n"
        "    END\nEND\nGO"
    )

    def test_oracle_hoists_nested_table_variable_to_gtt(self) -> None:
        # The GTT hoist only scanned the top level: a table variable inside
        # an IF left an inline CREATE (invalid in PL/SQL).
        out = _t(self._SRC, "oracle")
        flat = _one_line(out)
        assert re.search(r"(?i)CREATE GLOBAL TEMPORARY TABLE P_V_V_TRAD", flat), out
        # The CREATE precedes the procedure; nothing DDL remains in the body.
        proc_at = flat.upper().index("CREATE OR REPLACE PROCEDURE")
        assert flat.upper().index("GLOBAL TEMPORARY") < proc_at, out
        assert "CREATE TEMPORARY TABLE" not in flat.upper(), out

    def test_mysql_keeps_inline_temporary_table(self) -> None:
        out = _one_line(_t(self._SRC, "mysql"))
        assert re.search(r"(?i)CREATE TEMPORARY TABLE v_trad", out), out


class TestCteAssignmentSelect:
    _SRC = (
        "CREATE PROCEDURE dbo.p_w @b VARCHAR(64), @f VARCHAR(80) OUTPUT AS\n"
        "BEGIN\n"
        "    ;WITH existentes AS\n    (\n"
        "        SELECT n = CONVERT(int, c)\n"
        "        FROM t_g WITH (UPDLOCK, HOLDLOCK)\n"
        "        WHERE co LIKE @b + '_%'\n    )\n"
        "    SELECT @f = @b + '_' + CAST(ISNULL(MAX(n), 0) + 1 AS varchar(10))\n"
        "    FROM existentes\n"
        "END\nGO"
    )

    def test_assignment_survives_as_into(self) -> None:
        # sqlglot turns SELECT @f = ... into an alias; the CTE form must take
        # the same SELECT ... INTO path as the plain assignment-select.
        for target, into in (
            ("postgresql", "INTO v_f"),
            ("mysql", "INTO v_f"),
            ("oracle", "INTO V_F"),
        ):
            out = _one_line(_t(self._SRC, target))
            assert re.search(r"(?i)WITH existentes AS \(", out), (target, out)
            assert into in out, (target, out)
            assert "AS v_f" not in out and "AS V_F" not in out, (target, out)

    def test_cte_body_is_translated(self) -> None:
        # Hints stripped, CONVERT mapped, string '+' rewritten per target.
        pg = _one_line(_t(self._SRC, "postgresql"))
        assert "UPDLOCK" not in pg.upper(), pg
        assert re.search(r"(?i)CAST\(c AS INT\) AS n", pg), pg
        assert "v_b || '_%'" in pg, pg
        my = _one_line(_t(self._SRC, "mysql"))
        assert "UPDLOCK" not in my.upper(), my
        assert "CONCAT(v_b, '_%')" in my, my

    def test_tsql_identity_keeps_assignment(self) -> None:
        out = _one_line(_t(self._SRC, "tsql"))
        assert re.search(r"(?i)SELECT @f = ", out), out
        assert re.search(r"(?i)WITH existentes AS", out), out


class TestCteDml:
    def test_updatable_cte_becomes_carrier(self) -> None:
        # T-SQL updates *through* the CTE; nothing else can — the WITH used
        # to be silently dropped (UPDATE re-targeted the bare CTE name).
        src = (
            "WITH n AS (SELECT orden, ROW_NUMBER() OVER (ORDER BY id) AS rn "
            "FROM u_det) UPDATE n SET orden = rn;"
        )
        for target in ("postgresql", "mysql", "oracle"):
            result = Transpiler().transpile(src, "tsql", target)
            assert "UPDATE" not in _executable_text(result.sql).upper(), (
                target,
                result.sql,
            )
            assert any("CTE" in w.message for w in result.warnings), (
                target,
                result.warnings,
            )

    def test_cte_in_subquery_kept_where_valid(self) -> None:
        src = (
            "WITH cte AS (SELECT 1 AS n FROM t_g) "
            "UPDATE t_z SET x = (SELECT MAX(n) FROM cte);"
        )
        for target in ("postgresql", "mysql"):
            out = _one_line(Transpiler().transpile(src, "tsql", target).sql)
            assert re.search(r"(?i)WITH cte AS \(SELECT 1 AS n FROM t_g\)", out), (
                target,
                out,
            )
            assert re.search(r"(?i)\) UPDATE t_z SET", out), (target, out)
        # Oracle has no WITH on UPDATE at all: documented carrier.
        ora = Transpiler().transpile(src, "tsql", "oracle")
        assert "UPDATE" not in _executable_text(ora.sql).upper(), ora.sql


class TestFinalSweepClasses:
    def test_paren_join_from_not_lost(self) -> None:
        # Access-style FROM ((a JOIN b) JOIN c) parsed as nested Subquery
        # nodes and the IR silently dropped the WHOLE FROM clause.
        src = (
            "CREATE PROCEDURE dbo.p_j @a VARCHAR(9) AS\nBEGIN\n"
            "    SELECT t1.c1 FROM ((t_a t1 INNER JOIN t_b t2 ON t1.k = t2.k)"
            " INNER JOIN t_c t3 ON t1.k = t3.k) WHERE t1.c1 = @a\nEND\nGO"
        )
        for target in ("mysql", "postgresql", "oracle"):
            out = _one_line(_t(src, target))
            assert re.search(r"(?i)FROM \(\(t_a", out), (target, out)
            assert "t_b" in out and "t_c" in out, (target, out)
            assert not re.search(r"(?i)FROM\s+WHERE", out), (target, out)

    def test_drop_index_guard_per_target(self) -> None:
        src = (
            "IF EXISTS(SELECT * FROM sysindexes WHERE id ="
            " object_id('dbo.s_tab') AND name = 'ix_t01')\n"
            "    DROP INDEX dbo.s_tab.ix_t01\nELSE\n"
            "    PRINT 'no existe'\nGO"
        )
        my = Transpiler().transpile(src, "tsql", "mysql")
        assert "DROP INDEX ix_t01 ON s_tab;" in my.sql, my.sql
        assert "IF EXISTS" not in my.sql.upper(), my.sql
        assert any("guard" in w.message for w in my.warnings), my.warnings
        pg = _t(src, "postgresql")
        assert "DROP INDEX IF EXISTS ix_t01;" in pg, pg
        ora = _t(src, "oracle")
        assert "EXECUTE IMMEDIATE 'DROP INDEX ix_t01'" in ora, ora

    def test_table_hint_stripped_from_if_condition(self) -> None:
        src = (
            "CREATE PROCEDURE dbo.p_h @a VARCHAR(9) AS\nBEGIN\n"
            "    IF EXISTS (SELECT 1 FROM t_g WITH (UPDLOCK, HOLDLOCK)"
            " WHERE co = @a)\n    BEGIN\n"
            "        UPDATE t_g SET x = 1 WHERE co = @a\n    END\nEND\nGO"
        )
        for target in ("mysql", "postgresql", "oracle"):
            out = _one_line(_t(src, target))
            assert "UPDLOCK" not in out.upper(), (target, out)
            # PG/MySQL keep IF EXISTS; Oracle lowers it to its FOR-guard
            # idiom — either way the probe query survives hint-free.
            assert re.search(r"(?i)EXISTS\s*\(\s*SELECT 1 FROM t_g WHERE", out), (
                target,
                out,
            )


class TestSetBasedCursorTrigger:
    _SRC = (
        "CREATE TRIGGER dbo.trg_x ON dbo.t_d AFTER INSERT AS\nBEGIN\n"
        "    DECLARE @d NVARCHAR(100)\n"
        "    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR SELECT d FROM inserted\n"
        "    OPEN cur\n"
        "    FETCH NEXT FROM cur INTO @d\n"
        "    WHILE @@FETCH_STATUS = 0\n    BEGIN\n"
        "        UPDATE t_z SET x = @d\n"
        "        FETCH NEXT FROM cur INTO @d\n    END\n"
        "    CLOSE cur\nEND\nGO"
    )

    def test_postgresql_uses_transition_table(self) -> None:
        # Purely set-based (cursor over FROM inserted): PG rewrites with
        # REFERENCING transition tables instead of the documented carrier.
        out = _t(self._SRC, "postgresql")
        assert "REFERENCING NEW TABLE AS inserted" in out, out
        assert "FOR EACH STATEMENT" in out, out
        assert re.search(r"(?i)CURSOR FOR SELECT d FROM inserted", out), out

    def test_mysql_and_oracle_degrade_whole_trigger(self) -> None:
        # No transition tables there: shipping a half-empty body per row
        # would be wrong; the whole trigger is preserved commented out.
        for target in ("mysql", "oracle"):
            out = _t(self._SRC, target)
            body = [
                line
                for line in out.splitlines()
                if line.strip() and not line.lstrip().startswith("--")
            ]
            assert not body, (target, out)
            assert "cannot express" in out, (target, out)
